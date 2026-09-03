#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fitness-diet-planner engine. Deterministic plan generation & progress check-in.

Subcommands:
  template   Print an empty profile JSON template.
  generate   Build a full weekly training + daily meal plan from a profile.
  checkin    Evaluate progress against a saved plan and adjust targets.

Pure standard library. All numbers are rounded deterministically.
"""
import argparse
import json
import sys
from datetime import date, datetime

# ---------------------------------------------------------------- constants
GOALS = ("cut", "bulk", "recomp", "health")
ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "athlete": 1.9}
EXPERIENCE = ("beginner", "intermediate", "advanced")
DIETS = ("omnivore", "no_pork", "pescatarian", "vegetarian", "vegan")
ALLERGENS = ("lactose", "gluten", "nuts", "seafood", "eggs", "soy")
EQUIPMENT = ("bodyweight", "dumbbell", "barbell", "kettlebell", "bands", "bench",
             "machine", "cable", "pullup_bar", "cardio_machine", "full_gym")
INJURIES = ("knee", "shoulder", "lower_back", "wrist")
CONDITIONS = ("diabetes", "hypertension", "kidney", "pregnant", "lactating", "eating_disorder_history")

GOAL_ZH = {"cut": "减脂", "bulk": "增肌", "recomp": "重组(减脂增肌并行)", "health": "健康维持"}
FULL_GYM_SET = set(EQUIPMENT)

# calories per gram
KCAL = {"p": 4.0, "c": 4.0, "f": 9.0}

# ---------------------------------------------------------------- food DB
# per 100 g edible portion; tags: meat/fish/animal/pork for diet filters
FOODS = [
    # proteins
    {"name": "鸡胸肉(熟)", "cat": "P", "kcal": 165, "p": 31.0, "c": 0.0, "f": 3.6, "tags": {"meat", "animal"}, "alg": set()},
    {"name": "瘦牛肉(熟)", "cat": "P", "kcal": 217, "p": 26.0, "c": 0.0, "f": 12.0, "tags": {"meat", "animal"}, "alg": set()},
    {"name": "猪里脊(熟)", "cat": "P", "kcal": 143, "p": 26.0, "c": 0.0, "f": 3.5, "tags": {"meat", "animal", "pork"}, "alg": set()},
    {"name": "三文鱼(熟)", "cat": "P", "kcal": 208, "p": 20.0, "c": 0.0, "f": 13.0, "tags": {"fish", "animal"}, "alg": {"seafood"}},
    {"name": "鳕鱼(熟)", "cat": "P", "kcal": 105, "p": 23.0, "c": 0.0, "f": 1.0, "tags": {"fish", "animal"}, "alg": {"seafood"}},
    {"name": "虾仁(熟)", "cat": "P", "kcal": 99, "p": 24.0, "c": 0.2, "f": 0.3, "tags": {"fish", "animal"}, "alg": {"seafood"}},
    {"name": "金枪鱼罐头(水浸)", "cat": "P", "kcal": 116, "p": 26.0, "c": 0.0, "f": 1.0, "tags": {"fish", "animal"}, "alg": {"seafood"}},
    {"name": "全蛋(水煮)", "cat": "P", "kcal": 155, "p": 13.0, "c": 1.1, "f": 11.0, "tags": {"animal"}, "alg": {"eggs"}},
    {"name": "蛋白", "cat": "P", "kcal": 52, "p": 11.0, "c": 0.7, "f": 0.2, "tags": {"animal"}, "alg": {"eggs"}},
    {"name": "北豆腐", "cat": "P", "kcal": 76, "p": 8.0, "c": 1.9, "f": 4.8, "tags": set(), "alg": {"soy"}},
    {"name": "豆腐干", "cat": "P", "kcal": 140, "p": 16.0, "c": 4.9, "f": 7.4, "tags": set(), "alg": {"soy"}},
    {"name": "无糖豆浆", "cat": "P", "kcal": 31, "p": 3.0, "c": 1.2, "f": 1.6, "tags": set(), "alg": {"soy"}},
    {"name": "希腊酸奶(脱脂)", "cat": "P", "kcal": 59, "p": 10.0, "c": 3.6, "f": 0.4, "tags": {"animal"}, "alg": {"lactose"}},
    {"name": "低脂牛奶", "cat": "P", "kcal": 42, "p": 3.4, "c": 5.0, "f": 1.0, "tags": {"animal"}, "alg": {"lactose"}},
    {"name": "乳清蛋白粉", "cat": "P", "kcal": 380, "p": 75.0, "c": 8.0, "f": 6.0, "tags": {"animal"}, "alg": {"lactose"}},
    # carbs
    {"name": "米饭(蒸)", "cat": "C", "kcal": 130, "p": 2.7, "c": 28.0, "f": 0.3, "tags": set(), "alg": set()},
    {"name": "糙米饭(蒸)", "cat": "C", "kcal": 123, "p": 2.7, "c": 26.0, "f": 1.0, "tags": set(), "alg": set()},
    {"name": "燕麦片(干)", "cat": "C", "kcal": 379, "p": 13.0, "c": 67.0, "f": 6.5, "tags": set(), "alg": {"gluten"}},
    {"name": "全麦面包", "cat": "C", "kcal": 247, "p": 13.0, "c": 41.0, "f": 3.4, "tags": set(), "alg": {"gluten"}},
    {"name": "红薯(蒸)", "cat": "C", "kcal": 90, "p": 2.0, "c": 21.0, "f": 0.1, "tags": set(), "alg": set()},
    {"name": "土豆(煮)", "cat": "C", "kcal": 87, "p": 1.9, "c": 20.0, "f": 0.1, "tags": set(), "alg": set()},
    {"name": "藜麦(煮)", "cat": "C", "kcal": 120, "p": 4.4, "c": 21.0, "f": 1.9, "tags": set(), "alg": set()},
    {"name": "意面(煮)", "cat": "C", "kcal": 158, "p": 5.8, "c": 31.0, "f": 0.9, "tags": set(), "alg": {"gluten"}},
    {"name": "玉米(煮)", "cat": "C", "kcal": 96, "p": 3.4, "c": 21.0, "f": 1.5, "tags": set(), "alg": set()},
    {"name": "馒头", "cat": "C", "kcal": 223, "p": 7.0, "c": 47.0, "f": 1.1, "tags": set(), "alg": {"gluten"}},
    # fruits
    {"name": "香蕉", "cat": "FR", "kcal": 89, "p": 1.1, "c": 23.0, "f": 0.3, "tags": set(), "alg": set()},
    {"name": "苹果", "cat": "FR", "kcal": 52, "p": 0.3, "c": 14.0, "f": 0.2, "tags": set(), "alg": set()},
    {"name": "蓝莓", "cat": "FR", "kcal": 57, "p": 0.7, "c": 14.0, "f": 0.3, "tags": set(), "alg": set()},
    {"name": "橙子", "cat": "FR", "kcal": 47, "p": 0.9, "c": 12.0, "f": 0.1, "tags": set(), "alg": set()},
    # vegetables
    {"name": "西兰花", "cat": "V", "kcal": 34, "p": 2.8, "c": 7.0, "f": 0.4, "tags": set(), "alg": set()},
    {"name": "菠菜", "cat": "V", "kcal": 23, "p": 2.9, "c": 3.6, "f": 0.4, "tags": set(), "alg": set()},
    {"name": "番茄", "cat": "V", "kcal": 18, "p": 0.9, "c": 3.9, "f": 0.2, "tags": set(), "alg": set()},
    {"name": "黄瓜", "cat": "V", "kcal": 15, "p": 0.7, "c": 3.6, "f": 0.1, "tags": set(), "alg": set()},
    {"name": "彩椒", "cat": "V", "kcal": 31, "p": 1.0, "c": 6.0, "f": 0.3, "tags": set(), "alg": set()},
    {"name": "蘑菇", "cat": "V", "kcal": 22, "p": 3.1, "c": 3.3, "f": 0.3, "tags": set(), "alg": set()},
    {"name": "四季豆", "cat": "V", "kcal": 31, "p": 1.8, "c": 7.0, "f": 0.2, "tags": set(), "alg": set()},
    {"name": "生菜", "cat": "V", "kcal": 15, "p": 1.4, "c": 2.9, "f": 0.2, "tags": set(), "alg": set()},
    # fats
    {"name": "牛油果", "cat": "F", "kcal": 160, "p": 2.0, "c": 8.5, "f": 15.0, "tags": set(), "alg": set()},
    {"name": "混合坚果", "cat": "F", "kcal": 607, "p": 20.0, "c": 21.0, "f": 54.0, "tags": set(), "alg": {"nuts"}},
    {"name": "花生酱", "cat": "F", "kcal": 588, "p": 25.0, "c": 20.0, "f": 50.0, "tags": set(), "alg": {"nuts"}},
    {"name": "橄榄油", "cat": "F", "kcal": 884, "p": 0.0, "c": 0.0, "f": 100.0, "tags": set(), "alg": set()},
    {"name": "芝麻", "cat": "F", "kcal": 559, "p": 19.0, "c": 24.0, "f": 46.0, "tags": set(), "alg": set()},
]

# ---------------------------------------------------------------- exercise DB
# need = required equipment set; an exercise is available if need <= equip_set
EXERCISES = {
    "squat": [
        {"name": "杠铃深蹲", "need": {"barbell"}},
        {"name": "高脚杯深蹲", "need": {"dumbbell"}},
        {"name": "保加利亚分腿蹲", "need": {"dumbbell", "bench"}},
        {"name": "腿举", "need": {"machine"}},
        {"name": "箱式深蹲", "need": {"barbell", "bench"}},
        {"name": "徒手深蹲", "need": set()},
    ],
    "hinge": [
        {"name": "传统硬拉", "need": {"barbell"}},
        {"name": "罗马尼亚硬拉", "need": {"barbell"}},
        {"name": "哑铃罗马尼亚硬拉", "need": {"dumbbell"}},
        {"name": "臀推", "need": {"bench"}},
        {"name": "壶铃摇摆", "need": {"kettlebell"}},
        {"name": "单腿罗马尼亚硬拉", "need": {"dumbbell"}},
        {"name": "俯卧背屈伸", "need": set()},
    ],
    "push_h": [
        {"name": "杠铃卧推", "need": {"barbell", "bench"}},
        {"name": "哑铃卧推", "need": {"dumbbell", "bench"}},
        {"name": "上斜哑铃卧推", "need": {"dumbbell", "bench"}},
        {"name": "俯卧撑", "need": set()},
        {"name": "器械推胸", "need": {"machine"}},
    ],
    "push_v": [
        {"name": "站姿杠铃推举", "need": {"barbell"}},
        {"name": "坐姿哑铃推举", "need": {"dumbbell", "bench"}},
        {"name": "器械推肩", "need": {"machine"}},
        {"name": "折刀俯卧撑", "need": set()},
    ],
    "pull_h": [
        {"name": "杠铃划船", "need": {"barbell"}},
        {"name": "单臂哑铃划船", "need": {"dumbbell", "bench"}},
        {"name": "坐姿绳索划船", "need": {"cable"}},
        {"name": "反向划船", "need": {"pullup_bar"}},
    ],
    "pull_v": [
        {"name": "引体向上", "need": {"pullup_bar"}},
        {"name": "高位下拉", "need": {"cable"}},
        {"name": "弹力带直臂下拉", "need": {"bands"}},
    ],
    "lunge": [
        {"name": "负重箭步蹲", "need": {"dumbbell"}},
        {"name": "登阶", "need": {"dumbbell", "bench"}},
        {"name": "徒手箭步蹲", "need": set()},
    ],
    "arms_bi": [
        {"name": "哑铃弯举", "need": {"dumbbell"}},
        {"name": "杠铃弯举", "need": {"barbell"}},
        {"name": "弹力带弯举", "need": {"bands"}},
    ],
    "arms_tri": [
        {"name": "绳索下压", "need": {"cable"}},
        {"name": "哑铃颈后臂屈伸", "need": {"dumbbell"}},
        {"name": "弹力带下压", "need": {"bands"}},
    ],
    "lateral": [
        {"name": "哑铃侧平举", "need": {"dumbbell"}},
        {"name": "弹力带侧平举", "need": {"bands"}},
    ],
    "rear_delt": [
        {"name": "俯身反向飞鸟", "need": {"dumbbell"}},
        {"name": "面拉", "need": {"cable"}},
        {"name": "弹力带面拉", "need": {"bands"}},
    ],
    "core": [
        {"name": "平板支撑", "need": set()},
        {"name": "死虫式", "need": set()},
        {"name": "悬垂举腿", "need": {"pullup_bar"}},
        {"name": "卷腹", "need": set()},
        {"name": "俄罗斯转体", "need": set()},
    ],
    "calf": [
        {"name": "负重站姿提踵", "need": {"dumbbell"}},
        {"name": "站姿提踵", "need": set()},
    ],
    "cardio": [
        {"name": "跑步机慢跑", "need": {"cardio_machine"}},
        {"name": "椭圆机", "need": {"cardio_machine"}},
        {"name": "动感单车", "need": {"cardio_machine"}},
        {"name": "划船机", "need": {"cardio_machine"}},
        {"name": "快走(坡度)", "need": set()},
        {"name": "跳绳", "need": set()},
    ],
}

SESSION_TEMPLATES = {
    "全身": ["squat", "hinge", "push_h", "pull_v", "lunge", "core"],
    "上肢": ["push_h", "pull_h", "push_v", "pull_v", "arms_bi", "arms_tri"],
    "下肢": ["squat", "hinge", "lunge", "calf", "core"],
    "腿": ["squat", "hinge", "lunge", "calf", "core"],
    "推": ["push_h", "push_v", "push_h", "lateral", "arms_tri"],
    "拉": ["pull_v", "pull_h", "hinge", "rear_delt", "arms_bi"],
}

INJURY_SWAP = {
    "knee": {"杠铃深蹲": ["臀推", "箱式深蹲"], "高脚杯深蹲": ["臀推", "单腿罗马尼亚硬拉"],
             "保加利亚分腿蹲": ["单腿罗马尼亚硬拉", "臀推"],
             "徒手深蹲": ["臀推", "俯卧背屈伸"], "箱式深蹲": ["臀推"],
             "腿举": ["臀推"],
             "负重箭步蹲": ["臀推", "俯卧背屈伸"], "徒手箭步蹲": ["臀推", "俯卧背屈伸"],
             "登阶": ["臀推", "俯卧背屈伸"],
             "传统硬拉": ["臀推"], "罗马尼亚硬拉": ["单腿罗马尼亚硬拉"],
             "哑铃罗马尼亚硬拉": ["单腿罗马尼亚硬拉"]},
    "shoulder": {"杠铃卧推": ["俯卧撑"], "哑铃卧推": ["俯卧撑"], "上斜哑铃卧推": ["俯卧撑"],
                 "站姿杠铃推举": ["折刀俯卧撑"], "坐姿哑铃推举": ["折刀俯卧撑"],
                 "器械推肩": ["折刀俯卧撑"], "引体向上": ["高位下拉", "弹力带直臂下拉"]},
    "lower_back": {"传统硬拉": ["臀推"], "罗马尼亚硬拉": ["臀推"], "哑铃罗马尼亚硬拉": ["臀推"],
                   "杠铃深蹲": ["高脚杯深蹲"], "杠铃划船": ["单臂哑铃划船"],
                   "站姿杠铃推举": ["坐姿哑铃推举"]},
    "wrist": {"杠铃卧推": ["哑铃卧推"], "杠铃划船": ["单臂哑铃划船"], "杠铃弯举": ["哑铃弯举"],
              "杠铃深蹲": ["高脚杯深蹲"]},
}

INJURY_NOTE = {
    "knee": "膝伤提示：已用髋主导动作替换膝主导动作；任何动作出现关节疼痛立即停止，并先咨询医生/物理治疗师。",
    "shoulder": "肩伤提示：已用中立位/自重推类动作替换杠铃推举与卧推；避免头后位动作，疼痛即停。",
    "lower_back": "腰部提示：已移除大重量轴向负荷（硬拉/杠铃深蹲），核心收紧、动作全程控制；疼痛即停并就医。",
    "wrist": "腕部提示：已改用哑铃等更易保持中立腕位的器械；可使用助力带，疼痛即停。",
}


# ---------------------------------------------------------------- validation
def validate_profile(p):
    """Return (errors, warnings). errors block generation."""
    errors, warnings = [], []

    def need(key, lo=None, hi=None, label=None):
        label = label or key
        v = p.get(key)
        if v is None:
            errors.append(f"缺少必填字段: {label} ({key})")
            return None
        if lo is not None and v < lo or hi is not None and v > hi:
            errors.append(f"{label} 超出合理范围 [{lo}, {hi}]: {v}")
            return None
        return v

    sex = p.get("sex")
    if sex not in ("male", "female"):
        errors.append("sex 必须是 male 或 female")
    age = need("age", 14, 90, "年龄")
    height = need("height_cm", 120, 230, "身高(cm)")
    weight = need("weight_kg", 35, 250, "体重(kg)")
    if age is not None and age < 18:
        warnings.append("未满18岁：青少年请以教练/儿科医生意见为准，本计划仅供参考。")
    if age is not None and age > 65:
        warnings.append("65岁以上：建议先做医学筛查，训练强度从保守端开始。")

    goal = p.get("goal")
    if goal not in GOALS:
        errors.append(f"goal 必须是 {GOALS} 之一，当前: {goal}")
    if p.get("goal_intensity", "standard") not in ("mild", "standard", "aggressive"):
        errors.append("goal_intensity 必须是 mild / standard / aggressive")

    days = p.get("training_days")
    if not isinstance(days, int) or not (2 <= days <= 6):
        errors.append("training_days 必须是 2-6 的整数")

    if p.get("experience", "beginner") not in EXPERIENCE:
        errors.append(f"experience 必须是 {EXPERIENCE}")
    if p.get("activity_level", "light") not in ACTIVITY:
        errors.append(f"activity_level 必须是 {list(ACTIVITY)}")
    if p.get("diet", "omnivore") not in DIETS:
        errors.append(f"diet 必须是 {DIETS}")

    bad_alg = [a for a in p.get("allergies", []) if a not in ALLERGENS]
    if bad_alg:
        errors.append(f"不支持的过敏原 {bad_alg}，可选: {list(ALLERGENS)}")
    bad_eq = [e for e in p.get("equipment", []) if e not in EQUIPMENT]
    if bad_eq:
        errors.append(f"不支持的器械 {bad_eq}，可选: {list(EQUIPMENT)}")
    bad_inj = [i for i in p.get("injuries", []) if i not in INJURIES]
    if bad_inj:
        errors.append(f"不支持的伤病类型 {bad_inj}，可选: {list(INJURIES)}")

    conds = p.get("conditions", [])
    bad_cond = [c for c in conds if c not in CONDITIONS]
    if bad_cond:
        errors.append(f"不支持的健康状况 {bad_cond}，可选: {list(CONDITIONS)}")

    if height and weight:
        bmi = weight / (height / 100) ** 2
        p["_bmi"] = round(bmi, 1)
        if bmi < 17.5:
            if goal == "cut":
                errors.append(f"BMI={bmi:.1f} 偏低，禁止生成减脂计划；请改用 health/recomp 并咨询医生。")
            else:
                warnings.append(f"BMI={bmi:.1f} 偏低，如有进食障碍风险请先就医。")
        if bmi >= 30:
            warnings.append("BMI≥30：蛋白质按校正体重计算；减重速度预期取保守端；建议先做基础体检。")
        if bmi >= 35:
            warnings.append("BMI≥35：强烈建议在医生监督下执行。")

    if "pregnant" in conds or "lactating" in conds:
        if goal in ("cut", "recomp"):
            errors.append("孕期/哺乳期禁止热量赤字计划；请使用 health 目标并咨询产科医生与注册营养师。")
        else:
            warnings.append("孕期/哺乳期：营养需求特殊，本计划仅作参考，请务必咨询专业人士。")
    if "eating_disorder_history" in conds:
        warnings.append("有进食障碍史：不采用激进热量缺口，弱化称重频率，建议配合专业营养师。")
        if p.get("goal_intensity") == "aggressive":
            errors.append("有进食障碍史时禁止 aggressive 强度。")
    if "kidney" in conds:
        warnings.append("肾脏疾病：高蛋白饮食可能不适用，请先咨询医生；蛋白质已下调至 1.2 g/kg。")
    if "diabetes" in conds:
        warnings.append("糖尿病：碳水均匀分配到各餐、避免空腹高强度训练；请遵医嘱监测血糖。")

    if p.get("meals_per_day", 3) not in (3, 4, 5):
        errors.append("meals_per_day 必须是 3 / 4 / 5")
    return errors, warnings


# ---------------------------------------------------------------- energy
def calc_bmr(p):
    """Katch-McArdle if body fat known, else Mifflin-St Jeor."""
    if p.get("body_fat_pct"):
        lbm = p["weight_kg"] * (1 - p["body_fat_pct"] / 100)
        return round(370 + 21.6 * lbm)
    base = 10 * p["weight_kg"] + 6.25 * p["height_cm"] - 5 * p["age"]
    return round(base + (5 if p["sex"] == "male" else -161))


def protein_basis_kg(p):
    """Use adjusted body weight when BMI >= 28 to avoid overshooting protein."""
    w = p["weight_kg"]
    if p.get("_bmi", 0) >= 28:
        h_m = p["height_cm"] / 100
        ibw = (22 if p["sex"] == "male" else 21) * h_m * h_m
        return round(ibw + 0.25 * (w - ibw), 1)
    return w


def calc_targets(p):
    goal, intensity = p["goal"], p.get("goal_intensity", "standard")
    bmr = calc_bmr(p)
    tdee = round(bmr * ACTIVITY[p.get("activity_level", "light")])

    pct = {
        "cut": {"mild": -0.10, "standard": -0.18, "aggressive": -0.25},
        "bulk": {"mild": 0.08, "standard": 0.12, "aggressive": 0.18},
        "recomp": {"mild": -0.03, "standard": -0.03, "aggressive": -0.05},
        "health": {"mild": 0.0, "standard": 0.0, "aggressive": 0.0},
    }[goal][intensity]
    target = tdee * (1 + pct)

    # floors
    floor = max(1200 if p["sex"] == "female" else 1500, bmr)
    if "eating_disorder_history" in p.get("conditions", []):
        floor = max(floor, tdee * 0.85)
    clamped = max(target, floor)
    if clamped != target:
        pct = clamped / tdee - 1

    # protein g/kg by goal
    ppk = {"cut": 2.2, "bulk": 1.8, "recomp": 2.0, "health": 1.6}[goal]
    if "kidney" in p.get("conditions", []):
        ppk = 1.2
    if p["experience"] == "advanced" and goal == "cut":
        ppk = 2.4
    protein_g = round(protein_basis_kg(p) * ppk)

    fat_g = max(round(clamped * 0.25 / KCAL["f"]), round(0.5 * p["weight_kg"]))
    carb_g = round((clamped - protein_g * KCAL["p"] - fat_g * KCAL["f"]) / KCAL["c"])
    if carb_g < 50:  # safety: never crash carbs
        fat_g = round((clamped - protein_g * KCAL["p"] - 50 * KCAL["c"]) / KCAL["f"])
        carb_g = 50

    weekly = {"cut": {"mild": -0.5, "standard": -0.7, "aggressive": -1.0},
              "bulk": {"mild": 0.15, "standard": 0.25, "aggressive": 0.4},
              "recomp": {"mild": -0.1, "standard": -0.1, "aggressive": -0.2},
              "health": {"mild": 0.0, "standard": 0.0, "aggressive": 0.0}}[goal][intensity]

    return {
        "bmr": bmr, "tdee": tdee, "target_kcal": round(clamped),
        "deficit_pct": round(pct * 100, 1), "floor": round(floor),
        "protein_g": protein_g, "fat_g": fat_g, "carb_g": carb_g,
        "protein_ppk": ppk, "protein_basis_kg": protein_basis_kg(p),
        "fiber_g": round(clamped / 1000 * 14), "water_ml": round(p["weight_kg"] * 35 / 10) * 10,
        "weekly_weight_change_pct": weekly,
    }


# ---------------------------------------------------------------- meals
def eligible_foods(p, cat=None):
    diet, alg = p.get("diet", "omnivore"), set(p.get("allergies", []))
    disliked = set(p.get("disliked_foods", []))
    out = []
    for f in FOODS:
        if cat and f["cat"] != cat:
            continue
        if f["name"] in disliked:
            continue
        if f["alg"] & alg:
            continue
        t = f["tags"]
        if diet == "vegan" and t & {"animal"}:
            continue
        if diet == "vegetarian" and t & {"meat", "fish"}:
            continue
        if diet == "pescatarian" and "meat" in t:
            continue
        if diet == "no_pork" and "pork" in t:
            continue
        out.append(f)
    return out


MEAL_SHARES = {3: [0.30, 0.40, 0.30], 4: [0.27, 0.35, 0.28, 0.10], 5: [0.25, 0.30, 0.25, 0.10, 0.10]}
MEAL_NAMES = {3: ["早餐", "午餐", "晚餐"], 4: ["早餐", "午餐", "晚餐", "加餐"],
              5: ["早餐", "午餐", "晚餐", "训练前加餐", "睡前加餐"]}


def _grams_for_kcal(food, kcal):
    return max(0, round(kcal / food["kcal"] * 100 / 5) * 5)


def build_meal(day_idx, meal_idx, meal_kcal, p_target_g, fat_g_budget, foods_by_cat, protein_pool, carb_pool):
    protein = protein_pool[(day_idx * 3 + meal_idx) % len(protein_pool)]
    carb = carb_pool[(day_idx * 2 + meal_idx) % len(carb_pool)]
    vegs = foods_by_cat["V"]
    fat_pool = foods_by_cat["F"]

    def macros(food, g):
        k = food["kcal"] * g / 100
        return {"name": food["name"], "grams": g, "kcal": round(k),
                "p": round(food["p"] * g / 100, 1), "c": round(food["c"] * g / 100, 1),
                "f": round(food["f"] * g / 100, 1)}

    items = []
    # protein slot sized by grams of protein, not kcal
    pg = round(p_target_g / (protein["p"] / 100) / 5) * 5
    pg = max(40, min(pg, 500))
    # fatty protein: cap its portion so the meal fat budget is not blown
    if protein["f"] > 5 and fat_g_budget > 0:
        max_pg_by_fat = fat_g_budget / (protein["f"] / 100)
        if pg > max_pg_by_fat:
            pg = max(40, round(max_pg_by_fat / 5) * 5)
    items.append(macros(protein, pg))
    # low-density protein: blend with a dense partner to hit the slot protein
    slot_p = p_target_g
    have_p = protein["p"] * pg / 100
    if have_p < slot_p * 0.8:
        partners = [f for f in protein_pool if f["p"] >= 15 and f["name"] != protein["name"]]
        if partners:
            partner = partners[(day_idx + meal_idx) % len(partners)]
            need = slot_p - have_p
            if need >= 3:
                bg = min(300, round(need / (partner["p"] / 100) / 5) * 5)
                if bg >= 15:
                    items.append(macros(partner, bg))

    # fat slot driven by the daily fat target, minus fat already in this meal
    fat_so_far = sum(i["f"] for i in items)
    slot = fat_g_budget - fat_so_far
    if fat_pool and slot > 2:
        fat = fat_pool[(day_idx + meal_idx) % len(fat_pool)]
        fg = max(5, min(60, round(slot / (fat["f"] / 100) / 5) * 5))
        items.append(macros(fat, fg))

    v1 = vegs[(day_idx + meal_idx) % len(vegs)]
    v2 = vegs[(day_idx + meal_idx + 3) % len(vegs)]
    vg = 100 if meal_kcal < 500 else 150
    items.append(macros(v1, vg))
    if v2["name"] != v1["name"]:
        items.append(macros(v2, vg))

    # carbs fill whatever kcal remains so the meal lands on target
    used = sum(i["kcal"] for i in items)
    rem = max(0.0, meal_kcal - used)
    cg = _grams_for_kcal(carb, rem)
    cg = max(60, min(cg, 600))
    items.insert(1, macros(carb, cg))

    # protein floor per meal
    psum = sum(i["p"] for i in items)
    if psum < 25 and pg < 400:
        extra = (25 - psum) / (protein["p"] / 100)
        new_pg = min(500, pg + round(extra / 5) * 5)
        items[0] = macros(protein, new_pg)
    return items


def build_day_meals(day_idx, p, targets):
    foods_by_cat = {c: eligible_foods(p, c) for c in ("P", "C", "V", "F", "FR")}
    if p.get("goal") == "bulk":
        foods_by_cat["F"] = sorted(foods_by_cat["F"], key=lambda f: f["p"])
        low_pf = [f for f in foods_by_cat["F"] if f["p"] <= 5]
        if len(low_pf) >= 2:
            foods_by_cat["F"] = low_pf
    protein_pool = foods_by_cat["P"] or [{"name": "北豆腐", "cat": "P", "kcal": 76, "p": 8, "c": 1.9, "f": 4.8, "tags": set(), "alg": set()}]
    if p.get("goal") in ("cut", "recomp"):
        protein_pool = sorted(protein_pool, key=lambda f: f["f"] / max(f["p"], 0.1))
    protein_pool = [f for f in protein_pool if f["p"] >= 6]  # too-low density cannot hit slots
    if p.get("goal") == "cut":
        lean = [f for f in protein_pool if f["f"] / max(f["p"], 0.1) <= 0.5]
        if len(lean) >= 5:
            protein_pool = lean
    carb_pool = foods_by_cat["C"] or [{"name": "米饭(蒸)", "cat": "C", "kcal": 130, "p": 2.7, "c": 28, "f": 0.3, "tags": set(), "alg": set()}]
    if p.get("goal") == "bulk":
        low_p = [f for f in carb_pool if f["p"] <= 3.0]
        if len(low_p) >= 3:
            carb_pool = low_p
        carb_pool = sorted(carb_pool, key=lambda f: f["p"])
    n = p.get("meals_per_day", 3)
    shares = MEAL_SHARES[n]

    def _build(p_target_total):
        built = []
        for i, share in enumerate(shares):
            meal_kcal = targets["target_kcal"] * share
            if i >= 3 and foods_by_cat["FR"]:  # snacks: capped protein + fruit
                snack = []
                fr = foods_by_cat["FR"][(day_idx + i) % len(foods_by_cat["FR"])]
                pr = protein_pool[(day_idx + i + 1) % len(protein_pool)]
                fg = _grams_for_kcal(fr, meal_kcal * 0.45)
                pg = _grams_for_kcal(pr, meal_kcal * 0.55)
                pg = min(pg, round(25 / (pr["p"] / 100) / 5) * 5)  # snack protein cap 25 g
                for food, g in ((fr, fg), (pr, pg)):
                    k = food["kcal"] * g / 100
                    snack.append({"name": food["name"], "grams": g, "kcal": round(k),
                                  "p": round(food["p"] * g / 100, 1), "c": round(food["c"] * g / 100, 1),
                                  "f": round(food["f"] * g / 100, 1)})
                items = snack
            else:
                items = build_meal(day_idx, i, meal_kcal, p_target_total * share,
                                   targets["fat_g"] * share, foods_by_cat, protein_pool, carb_pool)
            built.append({"meal": MEAL_NAMES[n][i], "items": items})
        return built

    def _totals_of(ms):
        t = {"kcal": 0, "p": 0, "c": 0, "f": 0}
        for m in ms:
            for it in m["items"]:
                for k in t:
                    t[k] += it[k]
        return t

    # measure background protein from staples/veg, then rebuild slots without it (iterate)
    meals = _build(targets["protein_g"])
    thr = 1.02 if p.get("goal") in ("cut", "recomp") else 1.10
    for _pass in range(2):
        tot0 = _totals_of(meals)
        if tot0["p"] <= targets["protein_g"] * thr:
            break
        bg0 = sum(it["p"] for m in meals for it in m["items"]
                  if not any(f["name"] == it["name"] and f["cat"] == "P" for f in FOODS))
        retry_target = max(targets["protein_g"] - bg0, targets["protein_g"] * 0.55)
        meals2 = _build(retry_target)
        if abs(_totals_of(meals2)["p"] - targets["protein_g"]) < abs(tot0["p"] - targets["protein_g"]):
            meals = meals2

    def recompute():
        t = {"kcal": 0, "p": 0, "c": 0, "f": 0}
        for m in meals:
            for it in m["items"]:
                for k in t:
                    t[k] += it[k]
        return t

    def item_food(it):
        return next((f for f in FOODS if f["name"] == it["name"]), None)

    def set_grams(m, it, ng):
        food = item_food(it)
        k = food["kcal"] * ng / 100
        it.update({"grams": ng, "kcal": round(k), "p": round(food["p"] * ng / 100, 1),
                   "c": round(food["c"] * ng / 100, 1), "f": round(food["f"] * ng / 100, 1)})

    # reconcile: protein first, then kcal via carbs; iterate
    shrink_thr = 1.02 if p.get("goal") in ("cut", "recomp") else 1.10
    totals = recompute()
    for _ in range(8):
        if totals["p"] > targets["protein_g"] * shrink_thr:
            # background protein from grains/veg/nuts overshoots: shrink protein dishes
            bg_p = sum(it["p"] for m in meals for it in m["items"]
                       if (item_food(it) or {}).get("cat") != "P")
            slot_p = totals["p"] - bg_p
            slot_target = max(targets["protein_g"] - bg_p, targets["protein_g"] * 0.6)
            factor = slot_target / max(slot_p, 1)
            for m in meals:
                for it in m["items"]:
                    food = item_food(it)
                    if food and food["cat"] == "P" and it["grams"] > 45:
                        ng = max(40, round(it["grams"] * factor / 5) * 5)
                        set_grams(m, it, ng)
            totals = recompute()
        if totals["p"] < targets["protein_g"] * 0.95:
            p_items = [(m, it) for m in meals for it in m["items"]
                       if (item_food(it) or {}).get("cat") == "P"]
            if p_items:
                m, it = max(p_items, key=lambda x: x[1]["grams"])
                food = item_food(it)
                need_p = targets["protein_g"] - totals["p"]
                ng = min(500, it["grams"] + round((need_p / (food["p"] / 100)) / 5) * 5)
                set_grams(m, it, ng)
                totals = recompute()
        # fat correction: protein shrinks free fat budget; refill from F items, then olive oil
        fdiff = targets["fat_g"] - totals["f"]
        if abs(fdiff) > max(3.0, targets["fat_g"] * 0.08):
            f_items = [(m, it) for m in meals for it in m["items"]
                       if (item_food(it) or {}).get("cat") == "F"]
            if fdiff > 0:
                for m, it in sorted(f_items, key=lambda x: x[1]["grams"]):
                    if fdiff <= 2:
                        break
                    food = item_food(it)
                    headroom = 60 - it["grams"]
                    if headroom >= 5:
                        add_g = min(headroom, fdiff / (food["f"] / 100))
                        add_g = round(add_g / 5) * 5
                        if add_g >= 5:
                            set_grams(m, it, it["grams"] + add_g)
                            fdiff -= food["f"] / 100 * add_g
                if fdiff > 4:
                    oil = next((f for f in FOODS if f["name"] == "\u6a44\u6984\u6cb9"), None)
                    if oil is not None:
                        largest_meal = max(meals, key=lambda m: sum(i["kcal"] for i in m["items"]))
                        oil_item = next((it for it in largest_meal["items"] if it["name"] == oil["name"]), None)
                        add_g = min(40, round(fdiff / (oil["f"] / 100) / 5) * 5)
                        if add_g >= 5:
                            if oil_item is not None and oil_item["grams"] + add_g <= 40:
                                set_grams(largest_meal, oil_item, oil_item["grams"] + add_g)
                            elif oil_item is None:
                                k = oil["kcal"] * add_g / 100
                                largest_meal["items"].append(
                                    {"name": oil["name"], "grams": add_g, "kcal": round(k),
                                     "p": 0.0, "c": 0.0, "f": round(oil["f"] * add_g / 100, 1)})
            else:
                for m, it in f_items:
                    if fdiff >= -2:
                        break
                    food = item_food(it)
                    cut_g = min(it["grams"] - 5, -fdiff / (food["f"] / 100))
                    cut_g = round(cut_g / 5) * 5
                    if cut_g >= 5:
                        set_grams(m, it, it["grams"] - cut_g)
                        fdiff += food["f"] / 100 * cut_g
            totals = recompute()
        diff = targets["target_kcal"] - totals["kcal"]
        if abs(diff) >= 60:
            c_items = [(m, it) for m in meals for it in m["items"]
                       if (item_food(it) or {}).get("cat") == "C"]
            if c_items:
                m, it = max(c_items, key=lambda x: x[1]["grams"])
                food = item_food(it)
                dg = round((diff / food["kcal"] * 100) / 5) * 5
                ng = max(50, min(600, it["grams"] + dg))
                set_grams(m, it, ng)
                totals = recompute()
        if abs(targets["target_kcal"] - totals["kcal"]) < 60 and totals["p"] >= targets["protein_g"] * 0.92:
            break
    for k in ("p", "c", "f"):
        totals[k] = round(totals[k], 1)
    totals["kcal"] = round(totals["kcal"])
    return meals, totals


def build_week_meals(p, targets):
    week = []
    for d in range(7):
        if d < p.get("training_days", 4) or True:  # meals every day
            meals, totals = build_day_meals(d, p, targets)
            week.append(meals)
    # rotate: 3 breakfast / lunch / dinner variants across the week
    return week


# ---------------------------------------------------------------- training
def split_for(days, experience):
    if days == 2:
        return ["全身", "全身"]
    if days == 3:
        return ["全身", "全身", "全身"] if experience == "beginner" else ["推", "拉", "腿"]
    if days == 4:
        return ["上肢", "下肢", "上肢", "下肢"]
    if days == 5:
        return ["推", "拉", "腿", "上肢", "下肢"]
    return ["推", "拉", "腿", "推", "拉", "腿"]


def equip_set(p):
    eq = set(p.get("equipment", []))
    if "full_gym" in eq:
        eq |= FULL_GYM_SET
    return eq


def pick_exercise(pattern, eq, used):
    for ex in EXERCISES[pattern]:
        if ex["need"] <= eq and ex["name"] not in used:
            return ex["name"]
    for ex in EXERCISES[pattern]:
        if ex["need"] <= eq:
            return ex["name"]
    return None


def sets_reps(goal, experience, pattern):
    compound = pattern in ("squat", "hinge", "push_h", "push_v", "pull_h", "pull_v")
    if experience == "beginner":
        return ("3×10-12", "60-90秒", "RPE 7，先学动作模式") if compound else ("2×12-15", "60秒", "控制节奏")
    if goal == "cut":
        return ("4×6-8", "2-3分钟", "维持力量强度，防止掉肌肉") if compound else ("3×10-12", "60-90秒", "RPE 8")
    if goal == "bulk":
        return ("4×6-10", "2-3分钟", "渐进超负荷优先") if compound else ("3×10-12", "60-90秒", "RPE 8-9")
    if goal == "recomp":
        return ("3×8-10", "2分钟", "每周尝试小幅加重") if compound else ("3×10-12", "60-90秒", "RPE 8")
    return ("2-3×12-15", "60秒", "RPE 6-7，以舒适和坚持为主")


def cardio_rx(p):
    goal, eq = p["goal"], equip_set(p)
    opts = [e["name"] for e in EXERCISES["cardio"] if e["need"] <= eq]
    if not opts:
        opts = ["快走(坡度)"]
    main = opts[0]
    alt = opts[1] if len(opts) > 1 else opts[0]
    if goal == "cut":
        return f"每周 2-3 次低强度有氧（{main}或{alt}）25-35 分钟，心率约最大心率 60-70%；可加 1 次 10-15 分钟 HIIT。建议安排在力量训练后或休息日。"
    if goal == "bulk":
        return f"每周 1 次 20 分钟低强度有氧（{main}），保持心肺即可，避免消耗过多恢复资源。"
    if goal == "recomp":
        return f"每周 2 次 20-25 分钟中等强度有氧（{main}或{alt}）。"
    return f"每周 2-3 次 30 分钟中等强度有氧（{main}或{alt}），达到微喘但能说话的程度。"


def build_training(p, used_names=None):
    used = used_names if used_names is not None else set()
    eq = equip_set(p)
    split = split_for(p["training_days"], p.get("experience", "beginner"))
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    rest_day_gap = 7 - len(split)
    schedule = []
    sessions = []
    for i, focus in enumerate(split):
        patterns = SESSION_TEMPLATES[focus]
        exercises = []
        for pat in patterns:
            name = pick_exercise(pat, eq, used)
            if not name:
                continue
            used.add(name)
            sr, rest, note = sets_reps(p["goal"], p.get("experience", "beginner"), pat)
            exercises.append({"name": name, "sets_reps": sr, "rest": rest, "note": note})
        sessions.append({"day": day_names[i], "focus": focus, "exercises": exercises})
    # distribute rest days
    idx = 0
    for d in range(7):
        if idx < len(sessions) and (d % (7 // max(1, len(sessions))) == 0 or len(sessions) >= 5) and idx < len(sessions):
            pass
        schedule.append(day_names[d])
    # simple: training days first, rest at end note
    return {"split": split, "sessions": sessions, "cardio": cardio_rx(p),
            "progression": ("每周尝试：复合动作加重 2.5%（上肢）/ 5%（下肢），或多做 1-2 次；"
                            "连续两次训练无法完成目标次数则维持重量。"),
            "deload": "每 4-6 周安排 1 周减载：所有组数减半、重量降至平时 60%，让结缔组织恢复。"}


def apply_injuries(sessions, injuries):
    notes = []
    for inj in injuries:
        swap = INJURY_SWAP.get(inj, {})
        if not swap:
            continue
        for s in sessions:
            names_in = {e["name"] for e in s["exercises"]}
            kept = []
            for e in s["exercises"]:
                if e["name"] in swap:
                    candidate = next((c for c in swap[e["name"]] if c not in names_in), None)
                    if candidate is None:
                        continue  # drop contraindicated exercise entirely
                    e["name"] = candidate
                    names_in.add(candidate)
                    e["note"] = (e["note"] + "；伤后替代动作，从轻重量开始").strip("；")
                kept.append(e)
            s["exercises"] = kept
        notes.append(INJURY_NOTE[inj])
    return notes


# ---------------------------------------------------------------- render
def render_plan_md(plan):
    pr, tg, t = plan["profile"], plan["targets"], plan["training"]
    L = []
    A = L.append
    A(f"# {pr.get('name', '用户')} 的个性化训练与饮食计划")
    A("")
    A(f"> 生成日期：{plan['generated_at']} ｜ 目标：{GOAL_ZH[pr['goal']]}（{pr.get('goal_intensity', 'standard')}）")
    A("")
    A("## 一、身体数据与能量目标")
    A("")
    A("| 指标 | 数值 |")
    A("|---|---|")
    A(f"| 基础代谢 BMR | {tg['bmr']} kcal |")
    A(f"| 日常总消耗 TDEE | {tg['tdee']} kcal |")
    A(f"| **每日目标热量** | **{tg['target_kcal']} kcal**（相对 TDEE {tg['deficit_pct']:+.1f}%） |")
    A(f"| 蛋白质 | {tg['protein_g']} g（{tg['protein_ppk']} g/kg × {tg['protein_basis_kg']} kg） |")
    A(f"| 脂肪 | {tg['fat_g']} g（≥20% 热量） |")
    A(f"| 碳水 | {tg['carb_g']} g（剩余热量） |")
    A(f"| 膳食纤维 | ≥{tg['fiber_g']} g |")
    A(f"| 饮水 | ≥{tg['water_ml'] // 1000 * 1000 // 1000:.1f} L |")
    A(f"| 预期体重变化 | 每周 {tg['weekly_weight_change_pct']:+.2f}% 体重 |")
    A("")
    A("## 二、每周训练计划")
    A("")
    A(f"分化：{' / '.join(t['split'])}（每周 {pr['training_days']} 练，其余为休息/有氧日）")
    A("")
    for s in t["sessions"]:
        A(f"### {s['day']} — {s['focus']}")
        A("")
        A("| 动作 | 组×次 | 组间休息 | 要点 |")
        A("|---|---|---|---|")
        for e in s["exercises"]:
            A(f"| {e['name']} | {e['sets_reps']} | {e['rest']} | {e['note']} |")
        A("")
    A(f"**热身**：每次训练前 5 分钟动态拉伸 + 目标肌群激活，正式组前做 1-2 组递增热身组。")
    A("")
    A(f"**有氧**：{t['cardio']}")
    A("")
    A(f"**渐进超负荷**：{t['progression']}")
    A("")
    A(f"**减载**：{t['deload']}")
    A("")
    A("## 三、每日食谱")
    A("")
    A(f"每日 {pr.get('meals_per_day', 3)} 餐，以下为 7 天循环示例（食材可同类互换，宏量保持不变）：")
    A("")
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for i, day in enumerate(plan["meals"]["week"]):
        A(f"### {day_names[i]}")
        A("")
        A("| 餐次 | 食物 | 份量(g) | 热量 |")
        A("|---|---|---|---|")
        for meal in day:
            first = True
            for it in meal["items"]:
                label = meal["meal"] if first else ""
                first = False
                A(f"| {label} | {it['name']} | {it['grams']} | {it['kcal']} kcal |")
        A("")
    at = plan["meals"]["actual_totals"]
    A(f"**食谱实际宏量（日均）**：热量 {at['kcal']} kcal ｜ 蛋白 {at['p']} g ｜ 碳水 {at['c']} g ｜ 脂肪 {at['f']} g")
    A("")
    if plan.get("warnings"):
        A("## 四、注意事项")
        A("")
        for w in plan["warnings"]:
            A(f"- ⚠️ {w}")
        A("")
    A("---")
    A("*免责声明：本计划由算法基于通用运动营养学规则生成，不构成医疗建议。如有慢性疾病、伤病史或特殊生理状态，请先咨询医生或注册营养师。*")
    return "\n".join(L)


# ---------------------------------------------------------------- checkin
def checkin(plan, current_weight, adherence, strength_stalled=False):
    pr, tg = plan["profile"], plan["targets"]
    start_w = plan.get("start_weight", pr["weight_kg"])
    start_date = datetime.strptime(plan["generated_at"], "%Y-%m-%d").date()
    weeks = max(0.5, (date.today() - start_date).days / 7)
    expected = tg["weekly_weight_change_pct"]
    actual = (current_weight - start_w) / start_w / weeks * 100

    delta_kcal, actions, verdict = 0, [], ""
    floor, tdee = tg["floor"], tg["tdee"]
    goal = pr["goal"]

    if adherence is not None and adherence < 70:
        verdict = "执行率不足，暂不调整热量"
        actions += [f"实际执行率 {adherence}%（<70%）：先解决执行问题再谈调整",
                    "建议：备餐 2-3 天份、固定训练时间、把零食换成清单内食物",
                    "维持当前目标热量与宏量，两周后复查"]
    elif goal == "cut":
        if actual > expected + 0.3:  # slower than expected (both negative)
            delta_kcal = -150 if pr.get("goal_intensity", "standard") != "aggressive" else -200
            if tg["target_kcal"] + delta_kcal < floor:
                delta_kcal = 0
                actions.append("已达热量下限，不再下调；改为每周增加 1-2 次 20 分钟有氧，或安排 1 周 diet break（吃到 TDEE）后再继续")
            else:
                verdict = "减重过慢，下调热量"
                actions.append(f"实际 {actual:+.2f}%/周，慢于预期 {expected:+.2f}%/周 → 每日热量 −{-delta_kcal} kcal")
        elif actual < -1.2:
            delta_kcal = +150
            verdict = "减重过快，上调热量保护肌肉"
            actions.append(f"实际 {actual:+.2f}%/周 快于安全线 −1.2%/周 → 每日热量 +150 kcal，优先保证睡眠与蛋白质")
        else:
            verdict = "进度正常，维持现状"
            actions.append(f"实际 {actual:+.2f}%/周，在预期区间内，维持当前热量与宏量")
    elif goal == "bulk":
        if actual < expected - 0.1:
            delta_kcal = +150
            verdict = "增重过慢，上调热量"
            actions.append(f"实际 {actual:+.2f}%/周，低于预期 {expected:+.2f}%/周 → 每日热量 +150 kcal（主要加碳水）")
        elif actual > 0.6:
            delta_kcal = -100
            verdict = "增重过快，防止脂肪堆积"
            actions.append(f"实际 {actual:+.2f}%/周 超过 +0.6%/周 → 每日热量 −100 kcal")
        else:
            verdict = "进度正常，维持现状"
            actions.append(f"实际 {actual:+.2f}%/周，在预期区间内")
    else:  # recomp / health
        if abs(actual) < 0.1 and weeks >= 2 and goal == "recomp":
            delta_kcal = -100
            verdict = "体重无变化，微调热量"
            actions.append("两周以上体重无变化 → 每日热量 −100 kcal，同时关注围度与力量变化")
        elif abs(actual) > 1.0:
            delta_kcal = -100 if actual > 0 else +100
            verdict = "体重波动超出健康维持区间"
            actions.append(f"每周变化 {actual:+.2f}%，回调 {delta_kcal:+d} kcal")
        else:
            verdict = "进度正常，维持现状"
            actions.append(f"每周变化 {actual:+.2f}%，维持当前方案")

    if strength_stalled:
        actions.append("力量连续 2 周停滞：下周安排减载（组数减半、重量 60%），并检查睡眠 ≥7h 与训练前碳水是否充足")

    new_kcal = tg["target_kcal"] + delta_kcal
    if delta_kcal:
        # keep protein fixed, adjust carbs, then fat
        p_g = tg["protein_g"]
        f_g = tg["fat_g"]
        c_g = round((new_kcal - p_g * 4 - f_g * 9) / 4)
        if c_g < 50:
            f_g = round((new_kcal - p_g * 4 - 50 * 4) / 9)
            c_g = 50
    else:
        p_g, c_g, f_g = tg["protein_g"], tg["carb_g"], tg["fat_g"]

    report = {
        "date": date.today().isoformat(),
        "weeks_elapsed": round(weeks, 1),
        "start_weight": start_w, "current_weight": current_weight,
        "expected_pct_per_week": expected, "actual_pct_per_week": round(actual, 2),
        "adherence_pct": adherence, "verdict": verdict, "actions": actions,
        "old_kcal": tg["target_kcal"], "new_kcal": new_kcal, "delta_kcal": delta_kcal,
        "new_macros": {"protein_g": p_g, "carb_g": c_g, "fat_g": f_g},
    }
    return report, report


def render_checkin_md(r):
    L = [f"# 进度复盘报告（{r['date']}）", "",
         "| 项目 | 数值 |", "|---|---|",
         f"| 已执行 | {r['weeks_elapsed']} 周 |",
         f"| 起始体重 → 当前 | {r['start_weight']} kg → {r['current_weight']} kg |",
         f"| 预期变化 | {r['expected_pct_per_week']:+.2f}% /周 |",
         f"| 实际变化 | {r['actual_pct_per_week']:+.2f}% /周 |",
         f"| 执行率 | {r['adherence_pct']}% |" if r["adherence_pct"] is not None else "| 执行率 | 未提供 |",
         f"| 判定 | **{r['verdict']}** |",
         f"| 热量调整 | {r['old_kcal']} → **{r['new_kcal']} kcal**（{r['delta_kcal']:+d}） |",
         f"| 新宏量 | 蛋白 {r['new_macros']['protein_g']} g / 碳水 {r['new_macros']['carb_g']} g / 脂肪 {r['new_macros']['fat_g']} g |",
         "", "## 行动项", ""]
    L += [f"- {a}" for a in r["actions"]]
    L += ["", "*调整后连续执行 2 周再复查；执行率低于 70% 时优先解决执行问题。*"]
    return "\n".join(L)


# ---------------------------------------------------------------- cli
def cmd_template(_args):
    tpl = {
        "name": "", "sex": "male|female", "age": 30, "height_cm": 175, "weight_kg": 80,
        "body_fat_pct": None, "activity_level": "sedentary|light|moderate|active|athlete",
        "goal": "cut|bulk|recomp|health", "goal_intensity": "mild|standard|aggressive",
        "training_days": 4, "session_minutes": 60, "experience": "beginner|intermediate|advanced",
        "equipment": ["dumbbell", "bench"], "diet": "omnivore",
        "allergies": [], "disliked_foods": [], "meals_per_day": 3,
        "injuries": [], "conditions": [],
    }
    print(json.dumps(tpl, ensure_ascii=False, indent=2))


def cmd_generate(args):
    with open(args.profile, encoding="utf-8") as fh:
        p = json.load(fh)
    errors, warnings = validate_profile(p)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        sys.exit(2)
    tg = calc_targets(p)
    used = set()
    training = build_training(p, used)
    injury_notes = apply_injuries(training["sessions"], p.get("injuries", []))
    warnings += injury_notes
    week = build_week_meals(p, tg)
    # average actual totals across week
    tot = {"kcal": 0, "p": 0, "c": 0, "f": 0}
    for day in week:
        for meal in day:
            for it in meal["items"]:
                for k in tot:
                    tot[k] += it[k]
    for k in tot:
        tot[k] = round(tot[k] / 7, 1 if k != "kcal" else 0)
    plan = {
        "version": 1, "generated_at": date.today().isoformat(),
        "profile": p, "targets": tg, "training": training,
        "meals": {"per_day": p.get("meals_per_day", 3), "week": week, "actual_totals": tot},
        "start_weight": p["weight_kg"], "warnings": warnings,
    }
    if args.out_plan:
        with open(args.out_plan, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2)
    md = render_plan_md(plan)
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as fh:
            fh.write(md)
    if not args.out_md:
        print(md)
    print(json.dumps({"ok": True, "target_kcal": tg["target_kcal"], "macros": {"p": tg["protein_g"], "c": tg["carb_g"], "f": tg["fat_g"]}, "warnings": len(warnings)}, ensure_ascii=False), file=sys.stderr)


def cmd_checkin(args):
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    report, _ = checkin(plan, args.weight, args.adherence, args.strength_stalled)
    if args.save and report["delta_kcal"]:
        tg = plan["targets"]
        tg["target_kcal"] = report["new_kcal"]
        tg.update({"protein_g": report["new_macros"]["protein_g"], "carb_g": report["new_macros"]["carb_g"], "fat_g": report["new_macros"]["fat_g"]})
        plan["last_checkin"] = report
        with open(args.plan, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2)
    md = render_checkin_md(report)
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as fh:
            fh.write(md)
    print(md)


def main():
    ap = argparse.ArgumentParser(prog="plan_calculator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("template")
    g = sub.add_parser("generate")
    g.add_argument("--profile", required=True)
    g.add_argument("--out-plan")
    g.add_argument("--out-md")
    c = sub.add_parser("checkin")
    c.add_argument("--plan", required=True)
    c.add_argument("--weight", type=float, required=True)
    c.add_argument("--adherence", type=float, default=None)
    c.add_argument("--strength-stalled", action="store_true")
    c.add_argument("--save", action="store_true")
    c.add_argument("--out-md")
    args = ap.parse_args()
    {"template": cmd_template, "generate": cmd_generate, "checkin": cmd_checkin}[args.cmd](args)


if __name__ == "__main__":
    main()
