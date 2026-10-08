#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-test suite for fitness-diet-planner. Run: python scripts/selftest.py
Exit code 0 = all pass. Used by CI (.github/workflows/ci.yml)."""
import argparse
import io
import json
import sys
import tempfile
import unittest
from datetime import date
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
    """Every case pins the review date (as_of), because that date drives the
    rate math. A fixture that relied on the machine clock silently rotted and
    broke CI on 2026-10-08: plan generated 2026-08-20 -> 7.0 weeks elapsed ->
    every band read as 'losing too slowly'. Keep as_of explicit in any new
    check-in test.
    """
    GEN = "2026-08-20"     # plan generation date
    AS_OF = "2026-09-03"   # exactly 2.0 weeks later -- the calibration window

    def _plan(self, **over):
        plan, _ = gen(LIX)
        d = {"version": 1, "generated_at": self.GEN, "profile": LIX,
             "targets": plan["targets"], "start_weight": 84}
        d.update(over)
        return d

    PIN = object()   # sentinel: "pin the review date", the default for this suite

    def _ci(self, weight, adherence=90, as_of=PIN, plan=None):
        if as_of is self.PIN:
            as_of = self.AS_OF        # pass None instead to exercise the clock
        r, _ = pc.checkin(plan if plan is not None else self._plan(),
                          weight, adherence, as_of=as_of)
        return r

    def test_slow_loss_cuts_calories(self):
        # -0.4 kg over 2 weeks = -0.24 %/wk vs expected -0.70 %/wk -> too slow
        self.assertEqual(self._ci(83.6, 90)["delta_kcal"], -150)

    def test_normal_maintains(self):
        # -1.2 kg / 2 wk = -0.71 %/wk -> on target
        self.assertEqual(self._ci(82.8, 85)["delta_kcal"], 0)

    def test_fast_loss_raises(self):
        # -2.8 kg / 2 wk = -1.67 %/wk -> past the -1.2 %/wk safety line
        self.assertEqual(self._ci(81.2, 95)["delta_kcal"], 150)

    def test_low_adherence_no_change(self):
        self.assertEqual(self._ci(83.9, 50)["delta_kcal"], 0)

    def test_floor_respected(self):
        plan = self._plan()
        plan["targets"]["target_kcal"] = plan["targets"]["floor"]  # already at floor
        r = self._ci(83.9, 90, plan=plan)
        self.assertGreaterEqual(r["new_kcal"], plan["targets"]["floor"])

    def test_elapsed_window_changes_the_verdict(self):
        """Same 1.2 kg drop: on target over 2 weeks, too slow over 6."""
        self.assertEqual(self._ci(82.8, 85)["delta_kcal"], 0)
        late = self._ci(82.8, 85, as_of="2026-10-01")   # 6.0 weeks
        self.assertEqual(late["actual_pct_per_week"], -0.24)
        self.assertEqual(late["delta_kcal"], -150)

    def test_time_bomb_canary(self):
        """Results must not depend on the wall clock when as_of is supplied."""
        real = pc.date

        class FakeDate(date):
            _t = date(2026, 9, 3)

            @classmethod
            def today(cls):
                return cls._t

        try:
            pc.date = FakeDate
            seen = {}
            for ymd in [(2026, 9, 3), (2027, 1, 1), (2031, 5, 17), (2024, 2, 29)]:
                FakeDate._t = date(*ymd)
                seen[ymd] = [(w, self._ci(w, 90)["delta_kcal"])
                             for w in (83.6, 82.8, 81.2, 83.9)]
        finally:
            pc.date = real
        first = seen[(2026, 9, 3)]
        for k, v in seen.items():
            self.assertEqual(v, first, "system clock %s leaked into results" % (k,))
        self.assertEqual([d for _, d in first], [-150, 0, 150, -150])

    def test_default_as_of_falls_back_to_today(self):
        """No as_of -> today. A plan from 7 days ago must read as 1.0 week."""
        real = pc.date

        class FakeDate(date):
            _t = date(2026, 8, 27)

            @classmethod
            def today(cls):
                return cls._t

        try:
            pc.date = FakeDate
            r = self._ci(83.6, 90, as_of=None, plan=self._plan(generated_at="2026-08-20"))
        finally:
            pc.date = real
        self.assertEqual(r["weeks_elapsed"], 1.0)
        self.assertEqual(r["date"], "2026-08-27")

    def test_repeat_checkin_uses_previous_checkin_as_baseline(self):
        """Weekly re-check-ins measure the last week, not the whole plan."""
        plan = self._plan(last_checkin={"date": self.AS_OF, "current_weight": 82.8})
        r = self._ci(82.4, 90, as_of="2026-09-10", plan=plan)
        self.assertEqual(r["baseline_weight"], 82.8)
        self.assertEqual(r["baseline_date"], self.AS_OF)
        self.assertEqual(r["weeks_elapsed"], 1.0)
        self.assertEqual(r["actual_pct_per_week"], -0.48)
        # without that baseline the same drop is diluted across 3.0 weeks
        naive = self._ci(82.4, 90, as_of="2026-09-10")
        self.assertEqual(naive["weeks_elapsed"], 3.0)
        # (82.4 - 84) / 84 over 3.0 weeks = -0.63 %/wk -- the dilution this fixes
        self.assertEqual(naive["actual_pct_per_week"], -0.63)

    def test_stale_plan_window_is_capped(self):
        r = self._ci(83.6, 90, as_of="2027-08-20")   # 52 weeks after generation
        self.assertEqual(r["weeks_elapsed"], pc.MAX_CHECKIN_WEEKS)
        self.assertTrue(any("重新生成" in a for a in r["actions"]))


class TestCheckinCli(unittest.TestCase):
    """cmd_checkin --save is the path the agent actually drives. It must keep
    every review data point, including the ones that change no calories --
    that was the second bug behind the 2026-10-08 CI failure."""

    def _plan_file(self, d):
        plan, _ = gen(LIX)
        doc = {"version": 1, "generated_at": "2026-08-20", "profile": LIX,
               "targets": plan["targets"], "start_weight": 84}
        path = str(Path(d) / "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        return path, dict(doc)

    def _run(self, path, weight, as_of, save=True, adherence=90):
        args = argparse.Namespace(plan=path, weight=weight, adherence=adherence,
                                  strength_stalled=False, as_of=as_of, save=save,
                                  out_md=None)
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            pc.cmd_checkin(args)
        finally:
            sys.stdout = real
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), buf.getvalue()

    def test_zero_delta_review_still_records_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            path, base = self._plan_file(d)
            kcal0 = base["targets"]["target_kcal"]
            doc, _ = self._run(path, 82.8, "2026-09-03")        # on target -> delta 0
            self.assertEqual(doc["last_checkin"]["delta_kcal"], 0)
            self.assertEqual(doc["checkin_history"][0]["weight"], 82.8)
            self.assertEqual(doc["targets"]["target_kcal"], kcal0)   # untouched
            # the following week must span 1 week from 82.8, not 3 weeks from 84
            doc2, md = self._run(path, 82.4, "2026-09-10")
            r2 = doc2["last_checkin"]
            self.assertEqual(r2["weeks_elapsed"], 1.0)
            self.assertEqual(r2["baseline_weight"], 82.8)
            self.assertEqual(r2["baseline_date"], "2026-09-03")
            self.assertIn("82.8 kg（2026-09-03）", md)
            self.assertEqual(len(doc2["checkin_history"]), 2)

    def test_changed_review_updates_targets_keeps_history(self):
        with tempfile.TemporaryDirectory() as d:
            path, base = self._plan_file(d)
            t0 = base["targets"]
            doc, _ = self._run(path, 83.9, "2026-09-03")        # too slow -> -150
            self.assertEqual(doc["last_checkin"]["delta_kcal"], -150)
            self.assertEqual(doc["targets"]["target_kcal"], t0["target_kcal"] - 150)
            self.assertLess(doc["targets"]["carb_g"], t0["carb_g"])   # carbs absorb it
            self.assertEqual(doc["targets"]["protein_g"], t0["protein_g"])  # protein held
            doc2, _ = self._run(path, 83.5, "2026-09-10")
            self.assertEqual(len(doc2["checkin_history"]), 2)
            self.assertEqual(doc2["last_checkin"]["old_kcal"], t0["target_kcal"] - 150)

    def test_save_off_leaves_plan_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            path, base = self._plan_file(d)
            self._run(path, 83.9, "2026-09-03", save=False)
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertNotIn("last_checkin", doc)
            self.assertEqual(doc["targets"]["target_kcal"],
                             base["targets"]["target_kcal"])

    def test_bad_as_of_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            path, _ = self._plan_file(d)
            with self.assertRaises(SystemExit) as cm:
                self._run(path, 82.8, "09/10/2026")
            self.assertIn("YYYY-MM-DD", str(cm.exception))

    def test_missing_plan_exits_cleanly(self):
        missing = str(Path(tempfile.gettempdir()) / "no-such-plan-fdp.json")
        args = argparse.Namespace(plan=missing, weight=80.0, adherence=None,
                                  strength_stalled=False, as_of=None,
                                  save=False, out_md=None)
        with self.assertRaises(SystemExit) as cm:
            pc.cmd_checkin(args)
        self.assertIn("cannot read", str(cm.exception))


class TestFoodLog(unittest.TestCase):
    def test_db_match_and_totals(self):
        with tempfile.TemporaryDirectory() as d:
            logp = str(Path(d) / "food_log.csv")
            rows, tot = pc.log_meal([{"name": "米饭", "grams": 200}, {"name": "番茄炒蛋", "grams": 150}], logp, "午餐")
            self.assertEqual(rows[0]["name"], "米饭(蒸)")
            self.assertEqual(rows[0]["source"], "db")
            self.assertAlmostEqual(tot["kcal"], 440, delta=3)
            self.assertEqual(len(pc.read_log(logp)), 2)

    def test_new_foods_from_photos(self):
        for name in ("紫米饭", "南瓜", "玉米粒", "胡萝卜", "苦菊", "嫩豆腐", "油醋汁"):
            self.assertIsNotNone(pc.find_food(name), name)

    def test_vision_est_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            logp = str(Path(d) / "food_log.csv")
            rows, tot = pc.log_meal([{"name": "食堂神秘菜", "kcal": 450, "p": 28, "c": 12, "f": 32}], logp)
            self.assertEqual(rows[0]["source"], "vision-est")
            self.assertEqual(tot["kcal"], 450)
            self.assertEqual(tot["p"], 28)


if __name__ == "__main__":
    unittest.main(verbosity=2)

