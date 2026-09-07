# State at 2026-09-07 09:40 — read this first

## Running now (survives this session dying)
`overnight/ab_goal_leg.py`, detached with nohup, started 09:35. The goal-leg
A/B: `shipped` (approach_goal's straight-line walk) against `recorded`
(GOAL_LEG_AS_RECORDED=True: the goal leg through walk_link like every other
leg); reach_table's sweep follows in BOTH arms. 10 trials an arm, interleaved,
setup to bar_jukebox at attempts=9 (a setup miss is INVALID), one execution of
the leg, scored by confirm() = at_table() on the post-sweep frame, plus an
at_table() re-read. 1200s external ceiling per trial. Expect 2-3 hours.
  log     overnight/ab_goal_leg.log       (per-trial lines `[ n]`)
  result  overnight/ab_goal_leg.json      (saved after EVERY trial; Fisher p at the end)
  frames  overnight/goal_leg_failframes/  at_dealer_table_* = PRE-sweep leg end (admissible),
                                          at_dealer_table_postsweep_*, success/ok_*
While it runs: the checkout is READ-ONLY for anything a trial child imports
(graph_walk, _harness, slow_traverse, places, ...). Docs and tools/ are fine.
The suite may run at BASEBALL_NICE=1 (§10.13a); mutation sweeps may not.

Why this experiment: OPEN-14's 37 table-leg executions all exhausted
approach_goal's budget ("stepped 6.8s of a 6.5s budget"); the census of their
frames (overnight/census/table_leg_ends_20260907.json) is 17 wedged, and the
visual read is dark 12 / bar counter 8 / floor 5 / NPC 3. approach_goal predates
the jukebox-leg restoration and was never A/B'd against the recorded leg.

If the run is dead when you read this: `overnight/ab_goal_leg.json` holds
every completed trial; do not restart from scratch without reading it, and
read the last 40 lines of the log for the trial that was in flight.

## The overnight plan — status
0. **OPEN-14 scored and recorded** (38a17af): 3 valid of 10, 7 censored at the
   1800s ceiling, 2 "arrived" of which ONE was `identify()` naming
   `dealer_table` — a pose, which §7 says it may never confirm. Frames +
   contact sheets committed.
1. **Census migration done** (f9b9c56, ad13c6e): every harness reports
   `failures_by_kind_leg_end` split by provenance via `_harness.census_kinds`
   / `report_kinds`; foreign and blank rows are named, not dropped.
2. **Orphan audit done** (f0de600): 13 dead routing-generation modules and the
   floor-map cluster, flagged in QA_AUDIT.md, nothing deleted.
3. **Static QA on Haiku done**: one by-construction check removed from my own
   test, `report_kinds` made loud on foreign rows (ad13c6e).
4. **Suite certified**: 142/143 → cause fixed → **143/143 green** (752s).

## Waiting for the run to end (do these first, in order)
1. Apply `drafts/pending_after_ab/` (README there): the control-frame fix the
   suite caught (142/143, test_success_control_frames.py). Mutation-test it.
2. `table_prompt` OCR path: apply `drafts/pending_after_ab/patch_at_table_ocr.py`
   (README there). The mask cannot see the prompt over the light table top or
   over the dealer's body; OCR reads both with 0 false positives on every
   negative on disk (overnight/census/prompt_ocr_ab.json). Local-contrast masks
   were measured and refused (prompt_mask_ab.json).
3. Score the A/B: overnight/ab_goal_leg.json; write OPEN-21's result with n,
   Fisher p and the pre-sweep frame classes (tools/goal_leg_sheet.py).

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
