# HANDOFF — what is running and what happens next

**Updated 2026-09-08 00:15. DEAD RECKONING IS PAUSED BY THE USER; the closed loop is running its 25.**

## Now

**OVERNIGHT PLAN (the user went to bed 2026-09-07 ~23:50; their instructions verbatim):** "I will let you iterate
and figure out what changes need to be done so you make it to the mini game table more often. ideally it would
be nice if you didn't walk into walls/the bar since your wasting time doing that. do it if you found that it
does help. don't be afraid to spin up sub agents to investigate the failures. something I've noticed is that
you walk into a wanda, the wall near wanda and the bar a lot."

The loop for the night, in order, repeated:
1. Let the running batch finish (the monitor's final tally line wakes the session). Record its tally here and
   on the board (`tools/dashboard.py`, then write_db `dash/state`). Archive `overnight/chain_trials.{log,json}`
   as `overnight/chain_trials_<name>.*` before any relaunch overwrites them.
2. A reader on EVERY failed trial (`tools/trial_sheet.py <n>` -> the reader workflow script
   `bar-failure-readers-wf_6cfd54f8-649.js` with the manifest; notes land in `agent_progress/closed-loop/review/`).
3. Build the next rule from what the readers and the censuses show, as a PENDING patch script in
   `drafts/pending_after_ab/` (an Opus builder + two Sonnet skeptics + a fix round, scratch trees made with
   `cp` under the scratchpad, NEVER symlinks, module under test proven by `__file__`, every anchor asserted
   before any write). Queue as of 23:50: (a) `apply_patch34.py` END-TURN (past the last stop, |dx| > 400 px ->
   turn toward the scene, offset kept on the remaining pushes; being verified); (b) SHORT END STEPS: when the
   fit says "at the endpoint" and there is no prompt, push in ~0.09 u steps with at_table() between them and
   back off the moment the table leaves the view (ab3 trial 5: solid fit at 204, no prompt, then three full
   scheduled pushes into a window);
   (c) the COLLISION census (`tools/collision_census.py`, committed): whole evening 45% of walked seconds are
   escapes/stalls/misses; portrait room (Wanda) 11.7 s a trial, bar counter->tables 14.7, door->street 8.4;
   since the ladder round 38%. Two WASTE INVESTIGATORS + skeptics (workflow `waste-investigators`) are on
   the bar counter (129-142) and street + the wall near Wanda (40-114); notes land in
   `agent_progress/closed-loop/waste/`. (d) FAST-RUN STUDY (the user's idea, 23:58: study the fast arrivals'
   commands beside the frames): one agent ranks tonight's arrivals by walk time, tables the five fastest against
   the five slowest by region and by stop, and proposes at most three controller changes;
   `agent_progress/closed-loop/fast_runs/notes.md`. Usage at 23:58: 5-hour 39% (resets 02:02), weekly 42%.
   (e) STOPS: A LOOK THAT FITS WITH A LARGE dx IS A HEADING ERROR, NOT A PUSH SHORTFALL (ab4 trial 6 reader,
   `agent_progress/closed-loop/review/notes_ab4_t06.md`): at the 166 stop the looks fit with dx +518, +648,
   +704, +810 while three retry pushes were spent, the stop was accepted "turned-unverified" at 12 inliers,
   and the walk then headed north into a dartboard alcove the chain never faces, wedged there and was lost.
   The same shape as the end-turn rule, at every stop: when the best look fits with |dx| > END_TURN_PX, turn
   toward the scene (dx / px-per-degree, capped) and re-verify instead of retrying pushes or accepting.
   Candidate after (a); build only with the end-turn machinery already in.
   (f) READY: `drafts/pending_after_ab/apply_patch36.py` — no retry pushes at a stop when the last credible fit
   had WALL scale (the fast-vs-slow study, `agent_progress/closed-loop/fast_runs/notes.md`: every slow arrival
   lost 30-45 s at stops 88/129 to three empty retries then the ladder, at scale 2.2-2.6; the retries that
   helped carried 1.1-1.2; wall-scale fits: fast runs 0-2, slow 3-6, no overlap at n=5). Verified on a cp
   scratch copy with the module under test proven: 118 tests, mutants "gate removed" and "WALL_SCALE 3.5"
   caught. Lands with (a) at the batch end.
3b. EVERY RUN TEACHES SOMETHING (the user, 00:05: "if a run is faster than the current fast one, figure out
   why and see if you can incorporate those changes. ideally every run should teach you something new"): the
   evening's fastest walks are EARLY builds — batch 5e trial 4 67.9 s, 5e t5 72.9, batch 4 t3 74.2, batch 5 t1
   74.7 — while tonight's builds arrive in 92-135 s. A RULE-COST study (sonnet, `agent_progress/closed-loop/
   rule_costs/notes.md`) attributes the extra seconds to the rules added since 21:08 and proposes what to trim.
   Standing rule: an arrival that beats the current record (67.9 s walk) gets a "why faster" reader against the
   previous record; every arrival gets a one-lesson pass (Haiku) when the budget allows; every failure a reader.
4. At the batch end: apply the verified patch(es), run the test file, mutants in the checkout (the console is
   idle), commit, `ensure_stream.ensure_live()` (the PS5 may have dozed during the build; standing permission
   to wake it), relaunch `overnight/chain_trials.py --chain route_user_1853 --trials 20 --arms off,on` while
   the pan question is open; once the pan A/B has 10 valid an arm, decide the arm by Fisher/cost and run plain
   `--trials 25`. Every change is ONE round; report arrival by cause, never just the rate.
5. Keep this file, CLAUDE.md §8 and the board current after every batch. Never edit `chain_walk.py`,
   `chain.py`, `overnight/chain_trials.py` or `overnight/_harness.py` while a batch runs (the child re-imports
   them per trial). No mutation sweeps beside the console; the single test file is fine.


- **THE 25, TENTH LAUNCH, RUNNING (00:13:19, commit e49cd3e), plain `--trials 25`, pan OFF.** On the fourth
  A/B attempt's build plus patch36 (no retry pushes at a stop after a wall-scale fit) and patch38 (at_table()
  retries a dark frame brightness-normalised). **Pan A/B, fourth attempt, DONE (7fa0efa, 20 trials, 0
  invalid): pan off 9/10 (walk median 104.5 s), pan on 8/10 (99.7 s), Fisher p = 1.00** — no arrival
  difference, the flag stays off; `overnight/chain_trials_ab_pan_try4.*`. Its three failures: t6 (on) lost
  after the 166 stop was accepted unverified with its looks reading +518..+810 px (a dartboard alcove); t10
  (on) the prompt ON SCREEN for three iterations and the detector blind to a dark frame (fixed, patch38);
  t11 (off) a marginal 29-inlier look at the 39 stop strafed the character into an alcove with an NPC.
  Readers: `agent_progress/closed-loop/review/notes_ab4_t*.md`. **Still to land at the next boundary:**
  `apply_patch34.py` END-TURN (workflow recheck pending), `apply_patch37.py` STOP-TIE separation + look-around
  early exit (workflow `stop-tie-separation` building; the rule-cost study: two thirds of the +34 s per
  arrival is stop ceremony from STOP_TIE_FRAC firing on near-duplicate waypoints at every stop; the record-run
  study agrees and adds: STRONG_MIN_INLIERS 165 would have refused the record run's correct 154-inlier skip of
  stop 88). Studies: `agent_progress/closed-loop/{fast_runs,rule_costs,record_run}/notes.md`.
- **THE PAN A/B, FOURTH ATTEMPT, DONE (23:31:17, commit 7fa0efa):** the retry-skip landed at the user's
  request ("don't wait, land the retry fix now and relaunch"): a stop reached by turn-early takes NO retry pushes
  (`drafts/pending_after_ab/apply_patch35.py`). Third attempt (532825d, 6 trials): pan off 1/3, pan on 2/3
  (`overnight/chain_trials_ab_pan_try3.*`). Turn-early FIRED LIVE at Wanda in trials 2 and 3 (both arrived;
  trial 3 first pushed north three more times on the retry rule — the fix above). The three failures were all
  at the END: trials 1 and 5 "reached 204 without the prompt" (the walk-past-the-table shape, dx 460-777 px
  left after the 196 stop), trial 6 lost at the 196 stop. **The end-turn rule is being built** (workflow:
  Opus builder + two Sonnet skeptics; `drafts/pending_after_ab/apply_patch34.py` when done; notes in
  `agent_progress/closed-loop/end_turn/`): past the last stop, a fit with |dx| > END_TURN_PX 400 turns the
  camera toward the scene by dx/px-per-degree (cap 45 deg, at most 3 per walk) and keeps that yaw offset on
  every remaining push, instead of strafing. Readers on ab3 trials 1 and 5 are in flight
  (`agent_progress/closed-loop/review/notes_ab3_t0*.md`).
- **THE PAN A/B, THIRD ATTEMPT, STOPPED 23:31 (23:2x, commit with 'turn early when blind near a turn stop'):** the
  turn-early rule LANDED (`drafts/pending_after_ab/apply_patch33.py` applied; notes and every skeptic's scratch
  work under `agent_progress/closed-loop/turn_early/`; 117 tests; 8 mutants caught). Same harness:
  `overnight/chain_trials.py --chain route_user_1853 --trials 20 --arms off,on`. **Landing it cost 25 minutes
  of repair:** a skeptic's scratch-tree setup symlinked 65 tracked files under `tests/routing/` to themselves
  inside the checkout (CLAUDE.md §10.16a); restored with `git checkout --`, the full suite re-run afterwards.
- **THE PAN A/B, SECOND ATTEMPT, STOPPED 22:24:47 at 7 trials (`overnight/chain_trials_ab_pan_try2.*`): pan off
  1/4, pan on 1/2, 1 INVALID (the chiaki game window vanished mid-walk for a few seconds; chiaki itself never
  restarted).** Trials 5, 6, 7 were all lost at Wanda (k=112) with the FULL ladder — jump, back, a 0.6 s left
  detour — and the frames after the rungs show the camera pressed into dark geometry, so the sidestep is not
  the instrument there; the turn is (the user, from the stream: "you walked too close to her and should have
  turned left. It's okay that you got super close, you just didn't turn left enough"). **The turn-early rule
  is being built** (workflow: an Opus builder, two Sonnet skeptics, a fix round) as a PENDING patch script,
  `drafts/pending_after_ab/apply_patch33.py`, notes in `agent_progress/closed-loop/turn_early/`; it lands
  when the console is idle (it is), then the A/B relaunches: `--trials 20 --arms off,on`.
  **Trial 3 (pan off) walked right past the dealer's table to the windows** (the user saw it; reader:
  `agent_progress/closed-loop/review/notes_ab2_t03.md`): the 196 stop's head-on fit failed, the -25 look
  matched 199 at 117 inliers (runner-up 100), then every fit read the scene 460-591 px LEFT at 7-61 inliers
  while the loop strafed left at the cap eight times, and the plan ran to 204 by count. **Two censuses over
  all 83 journals, so nobody rebuilds them:** (1) the accepted fit's SCALE at a verified stop does NOT predict
  arrival — at 196, scale < 0.9 arrived 6/8 and >= 0.9 24/26; a "short by scale" rule is refuted (§10.4).
  (2) "the strafe is not taking" (three same-side corrections, |dx| > 150, never shrinking 20%) occurs in 23
  of 83 trials, 11 of which arrived — no signal in general, and the common site (k=129-136, bar entrance) is
  benign; but at the END (k >= 197) with |dx| > 450 it occurred 3 times tonight and none found the prompt,
  against one arrival with 286-342 px. Candidate, n = 3: a large offset at the end that strafing does not
  reduce means the character is passing the table on the wrong side; stop pushing and turn toward the scene.
- **THE PAN A/B, SECOND ATTEMPT, LAUNCH RECORD (22:13:30, commit 45436a0):** same harness and arms as below, on
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
