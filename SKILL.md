---
name: fitness-diet-planner
description: Generate personalized weekly training plans and daily meal plans from body data, fitness goals, diet preferences, and available equipment, with automatic calorie/macro calculation and progress-based adjustments. Also logs meals from food photos or text descriptions using the agent's own vision (no external API), matching a built-in ingredient + Chinese-dish database and comparing intake against plan targets. Use when someone asks for a workout/diet plan, wants to lose fat or build muscle with a concrete schedule and meals, shares a food photo to count calories, or asks to review/adjust an existing plan this skill generated. Do not use for medical nutrition therapy, injury rehabilitation prescriptions, or general one-off nutrition questions.
metadata:
  short-description: Personalized training + diet plan with calorie/macro math
---

# Fitness Diet Planner

Input body data, training goals, diet preferences, and available equipment; produce a weekly-cycled training plan plus daily meals with calories and macros computed by a deterministic script; support periodic check-ins that adjust targets.

## Applicable scenarios (适用场景)
- User wants a complete, executable plan: body data + goal → weekly training split + daily meals + calorie/macro targets.
- Goals: fat loss (cut), muscle gain (bulk), recomposition (recomp), general health.
- Revisiting a previously generated plan for progress review or target adjustment (checkin).
- NOT for: medical nutrition therapy, rehab prescriptions, eating-disorder treatment, pregnancy weight-loss requests (see exception rules).

## Inputs (输入)
Collect into a profile JSON (`scripts/plan_calculator.py template` prints the schema). Required: sex, age, height_cm, weight_kg, goal, goal_intensity, training_days (2-6), experience, equipment, diet, meals_per_day. Optional but valuable: body_fat_pct (switches BMR formula), allergies, disliked_foods, injuries, conditions, activity_level.
Ask conversationally, a few questions at a time; infer reasonable defaults (activity_level=light, meals_per_day=3) only when the user is unresponsive, and say what you assumed.

## Workflow (步骤)
1. Interview: collect the profile fields above. Keep it to 2-3 rounds of questions.
2. Write `profile.json` into a `fitness-plan/` folder in the user's workspace.
3. Run the engine (bundled-runtime or system python, stdlib only):
   ```
   python <skill>/scripts/plan_calculator.py generate --profile fitness-plan/profile.json --out-plan fitness-plan/plan.json --out-md fitness-plan/plan.md
   ```
   Exit code 2 means validation failed: the JSON on stdout lists `errors` (blocking) and `warnings`. Fix the profile with the user and rerun; never hand-craft numbers to bypass validation.
4. Copy `assets/progress_template.csv` to `fitness-plan/progress.csv`.
5. Show the user the rendered plan (present `plan.md`), summarize targets verbally, and list any warnings.
6. Check-in (when the user reports progress): append the weigh-in row to progress.csv, then:
   ```
   python <skill>/scripts/plan_calculator.py checkin --plan fitness-plan/plan.json --weight <weekly-average-kg> --adherence <0-100> [--strength-stalled] --save
   ```
   Present the report and apply the action items.

## Rules (规则)
- All calories/macros come from the script; do not recalculate by hand. Formulas and rationale: references/nutrition-guide.md.
- Training splits, exercise selection, sets/reps, and injury swaps are script-driven; details in references/training-guide.md.
- Adjustment decisions follow the matrix in references/progress-adjustment.md: one variable at a time, recheck after 2 weeks, never cut below the script's floor.
- Weight is always the 7-day average of fasted morning weigh-ins, never a single-day reading.
- Food swaps must stay within the same category and be scaled by calorie density (e.g. 100 g cooked rice ≈ 150 g sweet potato), not 1:1.

## Output format (输出格式)
`generate` writes plan.md with four sections: 能量目标表 (BMR/TDEE/target kcal/macro table) → 每周训练计划 (per-day exercise tables with sets, reps, rest) → 每日食谱 (7-day meal tables with grams and kcal, plus actual daily macro totals) → 注意事项 (warnings) + disclaimer. Checkin writes a report table + action list. When presenting, show the full plan.md content or save-and-link the file; do not paraphrase the numbers.

## Exception handling (异常处理)
- Script exit 2 + `errors`: blocking input problems (missing fields, out-of-range values, pregnancy+deficit, BMI<17.5 cut request, eating-disorder history + aggressive). Re-interview and fix; explain the health reason, don't just say "invalid".
- `warnings` (BMI≥30/35, age <18 or >65, diabetes, kidney disease, pregnancy on health goal, injuries): always surface them verbatim in the final answer.
- Injuries: the script auto-swaps risky exercises; add the injury note and tell the user pain = stop + see a professional.
- User refuses to answer required fields: state the assumption used and the risk (e.g. wrong TDEE), then proceed only if they accept.
- The plan is not medical advice; keep the disclaimer in every delivered plan.

## Acceptance criteria (验收标准)
A delivered plan is complete only if:
1. plan.json, plan.md, progress.csv all exist in the workspace fitness-plan/ folder.
2. Weekly-average plan kcal is within ±8% of the script's target and weekly-average protein within ±10% (worst single-day protein ≤10%); actual totals are printed in plan.md. Vegan and high-kcal bulk plans have known deviation patterns — see references/nutrition-guide.md before "fixing" anything.
3. Every training day has ≥5 exercises, all matching the declared equipment; no exercise appears twice in the same week.
4. Meals cover every day of the week, respect diet/allergy filters (no pork for no_pork, no animal products for vegan, zero allergen hits), and distribute kcal across the requested meals_per_day.
5. Expected weekly weight-change rate is stated, and the checkin command is explained to the user.
6. All warnings surfaced; disclaimer present.

## Photo meal logging (拍照记餐)
When the user shares a food photo (or describes a meal in text):
1. Use your own vision to identify each dish and estimate portions. Apply the portion cues in references/food-photo-guide.md (e.g. 1 household bowl of rice ≈ 150-200 g, 1 palm of meat/fish ≈ 100-120 g). List what you see and the estimated grams so the user can correct you.
2. Log deterministically:
   ```
   python <skill>/scripts/plan_calculator.py log --log fitness-plan/food_log.csv --meal 午餐 --plan fitness-plan/plan.json --items '[{"name":"米饭","grams":200},{"name":"番茄炒蛋","grams":150}]'
   ```
   Known names are matched against the built-in ingredient + Chinese-dish database (`source: db`); anything unrecognized is passed with explicit vision-estimated macros (`source: vision-est`). Never invent DB entries on the fly.
3. If `--plan` is given, the output shows intake vs. remaining targets for the day; end with `summary` for the daily verdict:
   ```
   python <skill>/scripts/plan_calculator.py summary --log fitness-plan/food_log.csv --plan fitness-plan/plan.json
   ```
4. Feeding check-ins: when the user asks for a progress check-in, compute average daily intake from food_log.csv (if present) as the adherence evidence instead of asking them to guess.

## Notes
- Engine: scripts/plan_calculator.py (stdlib-only, deterministic). Do not edit its formulas to fit a request; change the profile instead.
- This skill stores user health data in the workspace; do not upload it anywhere.
