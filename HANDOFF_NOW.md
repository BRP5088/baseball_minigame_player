# State at 2026-09-07 09:40 — read this first

## Running now
`overnight/prompt_zone.py` (detached; THIRD design, launched after two grid
attempts wedged in the furniture and measured nothing): a STAR around the
recorded leg's endpoint -- the endpoint measured FIRST, then 0.05u left/right,
0.10/0.20u back, 0.05u forward, stick-relative, wedge-checked -- five headings
a point, mask + OCR verdicts; 3 walks, 1800s ceiling each. Log
`overnight/prompt_zone.log` (`[walk n]` lines), result `overnight/prompt_zone.json`
after every walk, every point appended to `overnight/prompt_zone_points.jsonl`
as it is measured, frames under `overnight/prompt_zone_frames/pz_w*`. The two
grid attempts: `overnight/prompt_zone_grid_attempt.json` (rows -2..+1 wedged or
invalid; the zone is bounded by geometry within 0.1u right and 0.3u left/back).
TODAY'S SETUP IS BAD: reaching bar_jukebox failed 3 of 3 rows in the second
attempt (12 geometry wedges in one row), against 9/9 in OPEN-5 -- session
variance (§10.5/10.6); the setup frames are on disk for a census.
NOTHING ELSE CPU-bound while it runs.
Suite after the OCR path + frame-test fixes: **144/144 green** (840s under
BASEBALL_NICE=1, `overnight/suite_after_frame_tests.log`). Load reached 15
with the suite beside the console run, above what 10.13a measured; the
suite is done and nothing else runs beside the map.

The goal-leg A/B is DONE: shipped 1/8, recorded 1/9, p = 1.0; the recorded leg
is 3x cheaper. Written up under CLAUDE.md OPEN-21.

## After the prompt-zone run (in order)
1. Apply `drafts/pending_after_ab/` (README there): the control-frame fix the
   suite caught (142/143, test_success_control_frames.py). Mutation-test it.
2. `table_prompt` OCR path: apply `drafts/pending_after_ab/patch_at_table_ocr.py`
   (README there). The mask cannot see the prompt over the light table top or
   over the dealer's body; OCR reads both with 0 false positives on every
   negative on disk (overnight/census/prompt_ocr_ab.json). Local-contrast masks
   were measured and refused (prompt_mask_ab.json).
3. Score the A/B TWICE (below), then RUN THE PROMPT-ZONE MAP -- agreed with
   the user 2026-09-07, harness written and committed, never run:
       nohup .venv/bin/python -B overnight/prompt_zone.py > overnight/prompt_zone.log 2>&1 &
   5x5 grid around the recorded leg's endpoint, 5 headings a point, mask + OCR
   verdicts, frames under overnight/prompt_zone_frames/. Needs the OCR path
   landed first (item 2) and a free console. ~1 hour if setups behave.
   Occupancy-grid and 3D mapping were offered and DROPPED by the user.
3b. Score the A/B TWICE: (a) as the harness scored it (overnight/ab_goal_leg.json,
   at_table() after the sweep, Fisher p); (b) post hoc with
   `tools/goal_leg_sheet.py`, which re-reads every PRE-sweep frame with the mask
   AND OCR and reports "prompt on screen at the leg's end" per arm -- the
   leg-level criterion the shipped detector cannot see (5 legs in: shipped 1/3,
   recorded 1/2, harness 0/5). Write OPEN-21 with both and say which is which.

## Done this morning (all committed)
- `locate()` may never confirm the GOAL by appearance (dfb1b6e, 697c7ac): the
  OPEN-14 trial-6 hole, with trial 6's own frame as a fixture.
- Goal leg: `GOAL_LEG_AS_RECORDED` flag (ships False), the goal's leg-end frame
  is now PRE-sweep, the success frame is the leg end and not `before` (da5b7ec).
- Hand-walk entry points deleted at the user's request; `tools/doctor.py` and
  `tools/calibrate_window.py` keep the two subcommands that guard the rig and
  a money path (ab5c1fe).

## Rules in force
No flagship sub-agents for routine work (Haiku); no drafting; never mutate the
checkout while `console_lock` is held (10.17/10.21); no mutation sweeps on the
Mac while the console is live (Snoopy_testing.md); save patch scripts before
running them (10.19).

## Tonight's results, committed
- Leg-1 flags cost 8/10 arrivals; reverted (aa773dc, p = 0.000714).
- OPEN-5: attempts=9 9/9 vs attempts=3 5/10 to bar_jukebox (d0b6143, p = 0.0325).
- OPEN-14: 1 real arrival of 3 valid; 7/10 censored; the `locate()` hole (38a17af).
- Reset diagnostic measured the wrong transport; fixed at the root (d3bf513).
- Console interlock (`console_lock.py`); keep_awake stands down during runs.
- QA_AUDIT.md: four guards no test can reach, by mutant (2251c49); orphans (f0de600).
- A test globbed a live run's sink and broke overnight (7b8f918).
