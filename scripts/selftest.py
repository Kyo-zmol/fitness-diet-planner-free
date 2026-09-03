#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-test suite for fitness-diet-planner. Run: python scripts/selftest.py
Exit code 0 = all pass. Used by CI (.github/workflows/ci.yml)."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_calculator as pc


def gen(profile):
    errors, warnings = pc.validate_profile(profile)
    if errors:
        return None, errors
    tg = pc.calc_targets(profile)
    used = set()
    training = pc.build_training(profile, used)
    pc.apply_injuries(training["sessions"], profile.get("injuries", []))
    week = pc.build_week_meals(profile, tg)
    tot = {"kcal": 0, "p": 0, "c": 0, "f": 0}
    for day in week:
        for meal in day:
            for it in meal["items"]:
                for k in tot:
                    tot[k] += it[k]
    for k in tot:
        tot[k] = tot[k] / 7
    return {"profile": profile, "targets": tg, "training": training, "week": week, "avg": tot}, warnings


LIX = {"name": "T1", "sex": "male", "age": 31, "height_cm": 176, "weight_kg": 84,
       "activity_level": "light", "goal": "cut", "goal_intensity": "standard",
       "training_days": 4, "experience": "intermediate",
       "equipment": ["dumbbell", "bench", "pullup_bar", "bands"],
       "diet": "omnivore", "allergies": ["lactose"], "disliked_foods": [],
       "meals_per_day": 3, "injuries": [], "conditions": []}

VEGAN = {"name": "T2", "sex": "female", "age": 27, "height_cm": 162, "weight_kg": 58,
         "activity_level": "moderate", "goal": "recomp", "goal_intensity": "standard",
         "training_days": 3, "experience": "beginner", "equipment": ["bands", "bodyweight"],
         "diet": "vegan", "allergies": ["nuts"], "disliked_foods": [],
         "meals_per_day": 5, "injuries": ["knee"], "conditions": []}

BULK = {"name": "T3", "sex": "male", "age": 25, "height_cm": 178, "weight_kg": 70,
        "body_fat_pct": 14, "activity_level": "moderate", "goal": "bulk",
        "goal_intensity": "standard", "training_days": 5, "experience": "advanced",
        "equipment": ["full_gym"], "diet": "omnivore", "allergies": [], "disliked_foods": [],
        "meals_per_day": 4, "injuries": [], "conditions": []}

ANIMAL_NAMES = {"鸡胸肉(熟)", "瘦牛肉(熟)", "猪里脊(熟)", "三文鱼(熟)", "鳕鱼(熟)", "虾仁(熟)",
                "金枪鱼罐头(水浸)", "全蛋(水煮)", "蛋白", "希腊酸奶(脱脂)", "低脂牛奶", "乳清蛋白粉"}


class TestEnergy(unittest.TestCase):
    def test_mifflin_st_jeor(self):
        self.assertEqual(pc.calc_bmr(LIX), 1790)  # 10*84+6.25*176-5*31+5

    def test_katch_mcardle(self):
        self.assertEqual(pc.calc_bmr(BULK), round(370 + 21.6 * (70 * 0.86)))

    def test_cut_deficit(self):
        plan, _ = gen(LIX)
        tg = plan["targets"]
        self.assertAlmostEqual(tg["target_kcal"], tg["tdee"] * 0.82, delta=2)
        self.assertEqual(tg["protein_g"], 185)  # 2.2 g/kg

    def test_bulk_surplus(self):
        plan, _ = gen(BULK)
        tg = plan["targets"]
        self.assertAlmostEqual(tg["target_kcal"], tg["tdee"] * 1.12, delta=2)
        self.assertEqual(tg["protein_g"], 126)  # 1.8 g/kg


class TestMeals(unittest.TestCase):
    def test_macro_accuracy(self):
        for prof in (LIX, VEGAN, BULK):
            plan, _ = gen(prof)
            tg, a = plan["targets"], plan["avg"]
            self.assertLess(abs(a["kcal"] - tg["target_kcal"]) / tg["target_kcal"], 0.08, prof["name"])
            self.assertLess(abs(a["p"] - tg["protein_g"]) / tg["protein_g"], 0.10, prof["name"])

    def test_allergen_and_diet_filters(self):
        plan, _ = gen(LIX)
        names = {it["name"] for d in plan["week"] for m in d for it in m["items"]}
        self.assertFalse(names & {"希腊酸奶(脱脂)", "低脂牛奶", "乳清蛋白粉"})  # lactose
        plan, _ = gen(VEGAN)
        names = {it["name"] for d in plan["week"] for m in d for it in m["items"]}
        self.assertFalse(names & ANIMAL_NAMES)
        self.assertFalse(names & {"混合坚果", "花生酱"})  # nuts

    def test_meal_count(self):
        plan, _ = gen(VEGAN)
        self.assertTrue(all(len(d) == 5 for d in plan["week"]))


class TestTraining(unittest.TestCase):
    def test_equipment_and_no_weekly_repeat(self):
        plan, _ = gen(LIX)
        eq = {"dumbbell", "bench", "pullup_bar", "bands"}
        allnames = []
        for s in plan["training"]["sessions"]:
            self.assertGreaterEqual(len(s["exercises"]), 5)
            for e in s["exercises"]:
                allnames.append(e["name"])
                for pat, exs in pc.EXERCISES.items():
                    m = next((x for x in exs if x["name"] == e["name"]), None)
                    if m:
                        self.assertTrue(m["need"] <= eq, e["name"])
        self.assertEqual(len(allnames), len(set(allnames)))

    def test_knee_injury_swaps(self):
        plan, _ = gen(VEGAN)
        banned = {"杠铃深蹲", "高脚杯深蹲", "保加利亚分腿蹲", "徒手深蹲", "腿举",
                  "负重箭步蹲", "徒手箭步蹲", "登阶"}
        names = {e["name"] for s in plan["training"]["sessions"] for e in s["exercises"]}
        self.assertFalse(names & banned)


class TestSafety(unittest.TestCase):
    def test_pregnancy_cut_rejected(self):
        p = dict(LIX, sex="female", height_cm=165, weight_kg=60, conditions=["pregnant"])
        errors, _ = pc.validate_profile(p)
        self.assertTrue(any("孕期" in e for e in errors))

    def test_low_bmi_cut_rejected(self):
        p = dict(LIX, sex="female", height_cm=170, weight_kg=48.8, goal="cut")
        errors, _ = pc.validate_profile(p)
        self.assertTrue(any("BMI" in e for e in errors))

    def test_invalid_equipment_rejected(self):
        p = dict(LIX, equipment=["震动甩脂机"])
        errors, _ = pc.validate_profile(p)
        self.assertTrue(any("器械" in e for e in errors))


class TestCheckin(unittest.TestCase):
    def _plan(self):
        plan, _ = gen(LIX)
        return {"version": 1, "generated_at": "2026-08-20", "profile": LIX,
                "targets": plan["targets"], "start_weight": 84}

    def test_slow_loss_cuts_calories(self):
        r, _ = pc.checkin(self._plan(), 83.6, 90)
        self.assertEqual(r["delta_kcal"], -150)

    def test_normal_maintains(self):
        r, _ = pc.checkin(self._plan(), 82.8, 85)
        self.assertEqual(r["delta_kcal"], 0)

    def test_fast_loss_raises(self):
        r, _ = pc.checkin(self._plan(), 81.2, 95)
        self.assertEqual(r["delta_kcal"], 150)

    def test_low_adherence_no_change(self):
        r, _ = pc.checkin(self._plan(), 83.9, 50)
        self.assertEqual(r["delta_kcal"], 0)

    def test_floor_respected(self):
        p = self._plan()
        p["targets"]["target_kcal"] = p["targets"]["floor"]  # already at floor
        r, _ = pc.checkin(p, 83.9, 90)
        self.assertGreaterEqual(r["new_kcal"], p["targets"]["floor"])


class TestFoodLog(unittest.TestCase):
    def test_db_match_and_totals(self):
        with tempfile.TemporaryDirectory() as d:
            logp = str(Path(d) / "food_log.csv")
            rows, tot = pc.log_meal([{"name": "米饭", "grams": 200}, {"name": "番茄炒蛋", "grams": 150}], logp, "午餐")
            self.assertEqual(rows[0]["name"], "米饭(蒸)")
            self.assertEqual(rows[0]["source"], "db")
            self.assertAlmostEqual(tot["kcal"], 440, delta=3)
            self.assertEqual(len(pc.read_log(logp)), 2)

    def test_vision_est_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            logp = str(Path(d) / "food_log.csv")
            rows, tot = pc.log_meal([{"name": "食堂神秘菜", "kcal": 450, "p": 28, "c": 12, "f": 32}], logp)
            self.assertEqual(rows[0]["source"], "vision-est")
            self.assertEqual(tot["kcal"], 450)
            self.assertEqual(tot["p"], 28)


if __name__ == "__main__":
    unittest.main(verbosity=2)

