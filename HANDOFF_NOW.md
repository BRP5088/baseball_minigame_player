# HANDOFF — what is running and what happens next

**Updated 2026-09-07 22:16. DEAD RECKONING IS PAUSED BY THE USER; the closed loop is running its 25.**

## Now

- **THE PAN A/B, SECOND ATTEMPT, RUNNING (22:13:30, commit 45436a0):** same harness and arms as below, on
  top of the ladder round. **The first attempt (21:59-22:05, 2f27596) was stopped at 4 trials (off 0/2, on
  1/2; `overnight/chain_trials_ab_pan_try1.*`): Wanda Fuller, an NPC, stood on the route at k=112 in the
  portrait room and trials 1-3 walked into her face in BOTH arms** (frames: `overnight/chain_frames/
  t1788832781074/it_040_k112.jpg`, `t1788832862511/it_038_k112.jpg` — "Wanda Fuller [] Talk" filling the
  screen). Trial 4 (pan on) arrived once she had moved. **Tonight's failure census by reader** (one reader per
  failed trial, `agent_progress/closed-loop/review/notes_cur_t0*.md`): NPC in view 5 (Wanda x3, a matron at
  173, the patron at 196-200), Pete at the stop 166 then a sideways veer 1, the jukebox at 171 1. Every one
  ended "lost after 9" or "stuck after 12" having tried one or two ladder rungs: LOST_MAX 9 reached the third
  rung on the iteration it ended the walk, and the rung counter carried across the trial. **The ladder round
  (45436a0):** the ladder restarts at jump after any progress; LOST_MAX 13 / NO_PROGRESS_MAX 17 (one full
  cycle); a sidestep rung is a 0.6 s detour (0.3 s measured a sliver of clearance), the RIGHT rung doubled
  after a LEFT, and the correction that would walk back into the obstacle is held for 3 plan targets. Eight
  mutants caught. A Talk-prompt detector was tried and abandoned: OCR misses "Talk" over a white glove and
  template-matching the button glyph scores wedge frames 0.94 (`scratchpad/npc_probe.py`, `glyph_probe.py`).
- **THE PAN A/B, FIRST ATTEMPT, STOPPED (21:59:30, commit 2f27596):** `overnight/chain_trials.py --chain route_user_1853
  --trials 20 --arms off,on` — `STOP_PAN_FROM_RUN` off/on interleaved, 10 trials an arm, the arm applied INSIDE
  the trial child from `BASEBALL_CHAIN_PAN`, per-arm tally and a Fisher exact in `overnight/chain_trials.json`
  (`arms`, `tally`, `fisher_p`; each run row carries `arm` and `pan`). The judge's first item. Monitor on
  `overnight/chain_trials.log`. **Why now, not after the 25:** the ninth launch (80182ac, pan off,
  `overnight/chain_trials_batch9.*`) went 1 of 5 valid — trials 1, 2, 4 lost or stuck at k=171-173 right after the
  bar-tables stop 166, trial 5 lost at 200 — against the eighth launch's 2/2 an hour earlier with one fewer rule;
  session variance that size (§10.5) means only an interleaved A/B says anything, and its off arm IS the control
  measurement the 25 was giving. The stop-166 census over every journal tonight (the table is in this session's
  notes; rebuild it from `overnight/chain_journals/*.jsonl`, rows with target 166): head-on verification at 166
  succeeded in nearly every trial of batches 4-5e and has FAILED in 8 of the last 9 since batch 6 (d7ac88d), the
  ±25 look then verifies it with 55-147 inliers, and in trial 2 the look's un-yawed strafe (+78 px, right) and
  the next head-on fit (-230 px, left) disagreed by 300 px — the un-yaw arithmetic on a 25-degree look is not
  trustworthy, which is what matching each look against ITS OWN frame removes. The readers on trials 1, 2, 4, 5
  (`agent_progress/closed-loop/review/notes_cur_t0*.md`) are the frame-level account; trial 1's reader says NPC
  in view at the stop (Pete), then a sideways veer into the pool-table corner while the estimate blind-advanced.
  Batch 9 trial 6 is INVALID by my own hand: a patch script wrote `chain_trials.py` while the batch ran (rule 21;
  the script wrote one file before the next file's anchor assert fired — rule 19 means ALL asserts before ANY
  write) and the next child hit a SyntaxError. Eighth launch (5bdb479): 2/2, 155 s / 104 s
  (`_batch8.*`). Seventh: 1/2 (`_batch7.*`). Sixth: 4/7 valid. Earlier: batch 4 8/10; 5b 2/6; 5c 2/3; 5e 6/14.
  Each stop's cause and fix: `git log -- chain_walk.py`. Review a trial: `tools/trial_sheet.py <n>` then a
  reader (the user's standing rule: a reader on EVERY failed trial; look at the turns first).
- **Open candidates, none built** (the judge's PLAN.md order stands): (1) the pan A/B; (2) the reader's
  secondary finding from batch 7 trial 1 — `escape()`'s jump/back/left/right rung counter is never reset
  between stops, so at a late wedge only the sidestep rungs remain while jump/back had already worked twice
  in the same trial; (3) the Snoopy sweep's 14 surviving mutants are being pinned by a background agent
  (tests only, `agent_progress/closed-loop/sweep_pins/progress.md`; mutants confirmed on Snoopy, never here);
  (4) watch `STRONG_MIN_INLIERS` 165 (8 of 17 live relocalisations sat below it).
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
