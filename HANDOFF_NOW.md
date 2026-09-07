# State at 2026-09-07 09:40 — read this first

## Running now
`overnight/ab_fast.py --experiment extend` (detached): candidate (a) re-run on
the FAST harness -- return loop instead of reset, 60 s leg cap and 400 s trial
cap both scored TIMED OUT (a failure of the arm), 420 s external kill, 3 setup
attempts (a setup miss is INVALID). Log `overnight/ab_fast_extend.log`, result
`overnight/ab_fast_extend.json` after every trial, frames under
`overnight/ab_fast_extend_frames/`. ~45 min. Then `--experiment trim` (c),
then `overnight/side_table_leg.py` (b's path). The slow (a) run was stopped at
14/20 by decision: recorded 2/6, extended 2/6 (`overnight/ab_goal_extend.json`).
(c)'s trim flag LANDED (cc09ca1), ships empty.

FAST RUN, FIRST ATTEMPT (2026-09-07 evening): trial 1's return walk ended
pressed into a dark wall facing north (locate 11 matches); trial 2's reset then
raised NoGameWindow ("no chiaki game window found") and the harness scored it
INVALID in 14 s -- the window was back by the time the doctor looked (same
chiaki pid, streaming, not frozen). Transient; relaunched from trial 1
(`overnight/ab_fast_extend_attempt1.json` keeps the two trials). Watch the
per-trial `setup_mode`: if the return walk rarely lands in the basin, the loop
earns nothing and should be dropped.

THE FAST HARNESS (overnight/ab_fast.py, user request 2026-09-07 evening: A/Bs
took 2-4 h, the setup was 60-1110 s of it): return loop instead of reset (walk
the leg backwards, let locate() find the node, reset only on failure), a
TIMED OUT outcome (arrival slower than 60 s is not an arrival), 3 setup
attempts. `--experiment trim` (c) and `--experiment extend` (a) exist; add the
next ones to EXPERIMENTS. Expect ~45 min for 10 an arm. Board follows its json.

(b) CLOSED AS A NAMED NODE (Snoopy, ten references): bar_side_table is
confusable with bar_jukebox (ratios 1.00-1.22 vs 1.35). Run only the PATH half
after (a): overnight/side_table_leg.py (landing recorded as 'unnamed').

REFUTED (Snoopy, 38 landing frames, tools/landing_signature.py): "identify()
names bar_jukebox after a side-table landing and dealer_table/None after a
dealer-table one". Most landings of BOTH kinds read None at 60-136 (walk 1 side:
75-115 None; walk 3 dealer: 59-104 None); only walk 2's side landings named the
jukebox (3 of 4). identify() is not a landing classifier. A (b) correction can
only fire unconditionally on "no prompt after the extension" and be A/B'd as
such; the path itself is still worth measuring (side_table_leg.py).

(c) SHARPENED while (a) runs: the nine darkest jukebox leg-end frames of today
are all the same picture -- the character pressed into the jukebox CABINET
(dark surface fills the frame, no compass strip), i.e. geometry, not an NPC;
the "MOVING -- an NPC in the passage" stalls at steps 3-4 are a separate
mid-leg event. So (c) is the goal leg's problem in reverse: the recorded
jukebox leg overshoots into the object it aims at. Candidate: trim the leg's
end by ~0.05u (its last step is 0.14s at 0.32 = 0.045u), A/B'd on single-
attempt arrival at bar_jukebox from bar_pool_room (walk_leg_under_test).
Needs a per-leg trim flag in graph_walk -- edit only after (a) ends (10.21).
VERIFIED ON SNOOPY (2026-09-07 evening): patch applies, 6/6 tests green,
mutants A/B/C all caught, restore by sha. Land here with
`drafts/pending_after_ab/patch_leg_trim.py` the moment (a) ends, then run
`overnight/ab_jukebox_trim.py`.

## Earlier plan (kept for the rules it carries)
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
