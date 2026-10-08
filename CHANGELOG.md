# Changelog

All notable changes to **fitness-diet-planner-free**. Dates are ISO-8601.
The engine is pure standard library, so `python scripts/selftest.py` reproduces every number below locally.

## [1.2.0] - 2026-10-08

### Fixed
- **Check-in verdicts no longer drift with the wall clock.** `checkin()` computed its
  review window as `date.today() - generated_at`, so the same weigh-in produced a
  different answer depending on which day it was replayed. The self-test suite pinned a
  `2026-08-20` fixture and quietly rotted with it: green on 2026-09-03, red on
  2026-10-08 once the window had stretched from 2.0 to 7.0 weeks and every band read
  "losing too slowly". `checkin()` now takes an explicit `as_of` date
  (CLI: `--as-of YYYY-MM-DD`), defaulting to today, and the tests pin it.
- **`--save` records every review, not only the ones that change calories.**
  `plan["last_checkin"]` was written only when `delta_kcal != 0`, so a
  "maintain current targets" review left the *next* review measuring against plan
  generation -- the same window-dilution bug, seen from the user's side.
- **Clean one-line errors instead of tracebacks** for a malformed `--as-of`,
  an unreadable `--plan` path, or invalid JSON in the plan file (exit code 1).

### Added
- **Baseline auto-advance.** A repeat check-in now measures the change since the previous
  saved check-in, falling back to `generated_at` + `start_weight` for a first review.
  Weekly reviews stay weekly instead of averaging the whole plan away.
- `checkin_history` in `plan.json` -- every data point with its verdict, so the
  trend survives repeated reviews.
- A 12-week cap on the review window (`MAX_CHECKIN_WEEKS`); beyond it the rate is
 prorated and an action item tells you to regenerate the plan rather than trust a diluted number.
- 10 new tests (20 -> 30), including a **time-bomb canary**: it replays the whole
  check-in matrix under four fake system clocks and fails if the clock ever leaks into
  results again. Verified by mutation testing -- reintroducing the wall-clock read,
  dropping the baseline, or removing the cap each turn the suite red.

### Changed
- Review report shows `对比基线` (weight + date) and `基线以来` (weeks) instead of
  `起始体重 -> 当前`.
- `SKILL.md`, `README.md` and `references/progress-adjustment.md` document
  `--as-of`, the auto-baseline, and the `checkin_history` field.

## [1.1.0] - 2026-09-03

- Real-photo hero banner replacing the emoji header; table-of-contents navigation.
- Preview restyled as editorial "ledger" rows (right-aligned numerals, single accent,
  asymmetric layout); the rules behind it are now written down in
  `references/ui-design.md`.
- Discoverability: release + CI badges, skills.sh badge, `npx` install path, star call-to-action.

## [1.0.0] - 2026-09-03

- First public release: deterministic calorie/macro engine (Mifflin-St Jeor and
  Katch-McArdle BMR, TDEE 1.2-1.9, cut/bulk/recomp/health targets with safety floors),
  weekly training splits with equipment filtering and injury-safe exercise swaps,
  7-day meal plans built from a 50-ingredient / 26-dish Chinese food DB,
  `template / generate / checkin` subcommands, photo-based meal logging
  (`log / summary`), and a self-test suite running on Python 3.10-3.13 in CI.
