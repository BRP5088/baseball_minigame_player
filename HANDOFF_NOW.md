# HANDOFF — what is running and what happens next

**Updated 2026-09-07 late evening. DEAD RECKONING IS PAUSED BY THE USER; the closed loop is being built.**

## Now

- **Batch 2 of closed-loop trials RUNNING (launched 19:36)**: `overnight/chain_trials.py --chain route_user_1853
  --trials 10` -> `overnight/chain_trials.json` / `.log`, frames `overnight/chain_frames/t*/`, journals
  `overnight/chain_journals/route_user_1853_t*.jsonl`. Batch 1 (archived as `overnight/chain_trials_batch1.*`):
  2 ARRIVED (98 s, 121 s), 2 TIMED OUT at the door turn taken short; stopped at 4 of 10, fix landed (3ae35aa):
  verified turn stops with retry, real weak gate, LOST early exit. Review a trial with
  `tools/turn_review.py <shots dir> <journal>` -- look at the turns first. The user is at dinner; the run needs
  no supervision.
- **CLOSED-LOOP TRIALS RUNNING** (relaunched after trial 1's lesson): `overnight/chain_trials.py --chain
  route_user_1853 --trials 10` -> `overnight/chain_trials.json`, `.log`, frames `overnight/chain_frames/t*/`,
  journals `overnight/chain_journals/`. Chain = the USER's own drive (`chains/route_user_1853`, 205 waypoints,
  plan 102 pushes + 6 turn stops). Trial 1 of the first launch ran k ahead of the character on weak fits and
  strafed into the wall; fixed (ADVANCE_MAX 1, FIX_MIN_INLIERS 29, look-back). Scored arrived / timed_out /
  failed, 400 s cap, 580 s external ceiling.
- **Fast (a) A/B (`overnight/ab_fast.py --experiment extend`) KILLED at trial 5 of 20 on the user's
  instruction** ("data on a potential dead method isn't useful"). Partial record kept:
  `overnight/ab_fast_extend.json` / `.log` — extended 2/2 arrived (25 s each), recorded 0/2 + 1 INVALID
  (jukebox setup 356 s). Not a result; n=2. `--resume` restarts it at trial 6 if ever wanted.
  Nothing dead-reckoning is deleted: `drafts/pending_after_ab/` holds the stop-early and
  no-return-after-arrival patches, unapplied.
- **Closed-loop build in flight** (workflow `wf_1a357a4f-1a7`, 3 Opus builders + 3 Opus skeptics,
  bounded fix loop). Spec, the fixed interfaces and the rules: `agent_progress/closed-loop/SPEC.md`.
  New files only: `chain.py` (sensor), `chain_record.py` (recorder), `chain_walk.py` (controller),
  `overnight/chain_trials.py` (harness), `tools/chain_validate.py`, `tests/routing/test_chain_*.py`.
  Progress notes: `agent_progress/closed-loop/<role>/progress.md`.
- Console: idle, lock free, sticks cleared. chiaki alive as of 23:00.

## Next, in order

1. Read the builders' reports; run the full suite; commit the modules.
2. **Go/no-go = the sensor's offline validation** on `overnight/drives/20260906_172413_office`
   (walking frames placed within 1 chain step?) — `agent_progress/closed-loop/sensor/`.
3. Record a chain live: `chain_record.py --executor` (reset, dead-reckoning route with the recorder in
   a thread, kept only if `at_table()` at the end; up to 3 tries) → `chains/route_<stamp>/`.
4. `overnight/chain_trials.py --chain chains/route_<stamp>` — 10 trials, 420 s ceiling, arrived /
   timed_out / failed. Compare with dead reckoning's 5/10. Report by outcome and by where k stalled.
5. Offline CPU sweeps while trials run go to Snoopy (`Snoopy_testing.md`), never beside the console.

## Previous handoff (dead reckoning, paused)

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
