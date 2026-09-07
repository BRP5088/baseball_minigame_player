# Closed-loop navigation — build spec (2026-09-07, manager: the main session)

**Why.** Dead reckoning (replay recorded bearing/duration, look only at the leg's
end) arrives 5/10 per route after 13 measured changes. The user has paused it
and asked for a closed loop: LOOK AFTER EVERY PUSH, decide the next push from
what was seen. Position comes from the screen, never from the stick.

**Goal.** From the reset spawn, reach the dealer prompt (`table_prompt.at_table()`
True) by servoing along a recorded CHAIN of reference frames. Scored like the
fast harness: arrived / timed out (>400 s) / failed, 10 trials, against dead
reckoning's 5/10.

## Hard rules (CLAUDE.md is the authority; these are the ones that bite here)

- **NEW FILES ONLY.** Never edit `graph_walk.py`, `places.py`, `pose.py`,
  `slow_traverse.py`, `walk_steps.py`, `table_prompt.py`, `compass.py`,
  `input_controller.py`, `analog_replay.py`, `overnight/_harness.py`. A live
  harness may still be re-importing them (CLAUDE.md §10.21). Import and REUSE
  them (ponytail ladder rung 2): the HUD crop, ORB, the Hamming filter, RANSAC,
  turn_to, walk_leg, at_table already exist and each reimplementation on this
  project has been wrong at least once (a validation script that mirrored
  `_as_gray` without its crop scored an unmapped corpus above the references).
- **Every input path is OFF under `BASEBALL_TEST_RUN=1`.** Tests never touch the
  console. Any live driver asserts the flag is UNSET at call time before it
  sends, and NEVER sets the flag at import (§5: an import switched stick
  injection off inside a live harness; `tests/harness/test_no_import_time_test_run_flag.py`
  scans `tools/` and `overnight/`).
- **Do not run a CPU-bound sweep (ORB over hundreds of frames) until the manager
  says the console is free.** Write the script; smoke-test on <= 5 frames.
- **No constant is invented.** A threshold sits BETWEEN two measured populations
  (§10.4). Where the measurement does not exist yet, expose the knob, default it
  to "off" (None = never abstain), and log the quantity so the first live run
  measures it.
- **Nothing that matters in /tmp.** Progress notes to
  `agent_progress/<label>/progress.md` EVERY FEW TOOL CALLS (§10.16), split
  Established / Assumed. Scripts and numbers next to the notes.
- **Read `GRAVEYARD.md` before any design decision.** Two families are closed:
  steering mid-push (heading lag -> metres), and blind chunking (re-accelerates,
  walks short). The closed loop is neither: it STOPS, LOOKS, DECIDES, PUSHES. It
  moves nothing while thinking, and walking short does not matter because the
  picture, not a timer, says when a waypoint is reached.
- Mutation-test every test: at least two named mutants, each caught. Delete
  `__pycache__` between mutants (same-size edits run stale bytecode).

## Facts you can build on (verified by the manager 2026-09-07)

    places.keypoints(img, cache_key=None) -> (kps, des)     A PAIR. len() of it is 2.
    places.match_count(des_a, des_b)                        Hamming-filtered match count
    places._as_gray(img)                                    crops the HUD (compass, coin, quest list)
    pose.offset(a, b) -> (dx, dy) | None                    RANSAC estimateAffinePartial2D; dx > 0 = scene
                                                            moved RIGHT in the image = camera moved LEFT
    pose.ALIGN_TOL_PX = 35.0  (1.8 deg at 18.6-20.8 px/deg) pose.SAME_POSE_PX = 16.85
    slow_traverse.walk_leg(lx, ly, seconds, capture, read_heading, label="", log=print, step_sec=None)
        one CONTINUOUS push when step_sec == seconds; ly NEGATIVE = forward; lx = strafe
    slow_traverse.turn_to(target, read_heading, capture, log=print, tolerance=TURN_TOLERANCE, ...)
    slow_traverse.SETTLE_SEC = 0.35                         do NOT shorten (OPEN-8)
    walk_steps.walk_forward(speed, seconds, strafe=0.0)     raw push, returns view motion
    graph_walk.SPAWN = "office_corridor", GOAL = "dealer_table", TRUST_RESET_SPAWN = True
        the reset spawn is deterministic: bearing 86.9/87/87
    table_prompt.at_table(img) -> bool                      the arrival authority; mask OR OCR
    console_lock.acquire(name) / release() / `with console_lock.held(name):`
    compass.read_bearing(img) -> float | None               abstains ~6-15% live; NEVER re-read a
                                                            saved JPEG for a bearing (can flip 90 deg)
    Walking (§6): linear to ~0.75 magnitude; repeatability collapses above 0.60.
        0.45 mag: 70.6 px per 0.40 s push, spread 15.  A push under ~0.10 s does not move.
    Turning (§6): full stick is the worst place; USABLE_MAX 0.90; one-frame floor ~3.8 deg.
    Paired did-I-move probe (2026-09-06): push inliers / same-heading null inliers:
        moved 0.10-0.34, blocked 0.82 (n=6 headings, one spot). `overnight/probe_calib.py`.

## Recordings for OFFLINE validation of the sensor (no console needed)

    overnight/drives/20260906_172413_office   1064 frames 1920x1080  meta.json (per-frame heading + stick;
                                              the user's hand drive; 17% walking, 61% turning)
    demos/walk3_full_20260828_050731          710 frames 1400x787    input.json  (full route walk)
    demos/spawn_to_table_20260827_2123xx      124/214/254 frames 1400x787  no meta (spawn -> table)
    world_log/20260901_235855_anchor_calib    64 frames 1920x1080     index.jsonl
    explore/20260904_152521_bar_area          160 frames 1920x1080    index.jsonl (bar area explore)

A sequence of frames IS a chain. Build the chain from every Nth frame, hold the
rest out, and ask the sensor for each held-out frame's index given the previous
truth index as the hint. Report: |estimated - true| histogram, abstentions, and
the two populations that a min-inliers gate would have to separate (best-window
inliers on held-out frames vs inliers against frames > 2N away).

## Interfaces (FIXED — build to them so the three modules meet)

### chain.py  (owner: SENSOR agent)

    class Waypoint: index:int, heading:float|None, path:str, t:float, lx:float, ly:float, note:str, kps, des
    class Chain:
        @classmethod load(dir) -> Chain          # dir/meta.jsonl (one JSON object per line, fields above
                                                 # minus kps/des) + dir/NNNN.jpg; ORB precomputed on
                                                 # places._as_gray(img) via places.keypoints
        waypoints: list[Waypoint]
        def locate(self, img, k_hint:int, window:int=3) -> Fix | None
            # compare ONLY against waypoints[k_hint-1 .. k_hint+window] (sequence prior; a global
            # search is the localiser's known trap: unrelated rich frames score 100-155 anywhere)
            # per candidate: Hamming-filtered matches -> cv2.estimateAffinePartial2D RANSAC ->
            #   inliers, dx (pose.offset convention), scale (>1: the scene looks BIGGER than in the
            #   reference = we are CLOSER to it than the waypoint was = at/past it when walking toward it)
            # Fix: k:int (best by inliers), k_float:float (interpolate between neighbours by scale
            #   crossing 1.0 when both sides fit), inliers:int, dx:float, scale:float, second:int
            #   (runner-up inliers), detail:str
            # returns None when best inliers < MIN_INLIERS (default None = never abstain; MEASURE first)
        def reached(self, fix, k) -> bool         # fix.k > k, or fix.k == k and fix.scale >= 1.0
    MIN_INLIERS = None      # set from the offline validation's two populations, never invented

### chain_record.py  (owner: RECORDER agent)

    record(dir, capture, heading_fn, stick_fn, period=0.25, stop_fn) -> n_frames
        # appends ONE line per frame to dir/meta.jsonl (open-append-write-flush-close per line; a
        # crash at minute 4 keeps 4 minutes; NEVER truncate), frame as dir/NNNN.jpg quality 88.
        # heading = the LIVE compass read on the in-memory frame (None when it abstains) AND the
        # commanded camera heading if the driver knows it; both stored. Never derived from the JPEG.
    Drivers (each a CLI in the same file, flag set only inside main()):
      --executor  reset (reset_env.reset_environment), then walk the existing dead-reckoning route
                  (graph_walk.go_to_node_verified / follow_verified to GOAL, start_hint=SPAWN)
                  with the recorder running in a thread; keep chains/<name>/ only when at_table()
                  is True at the end, else rename chains/<name>_failed_<n>/ and retry (max 3)
      --user      the user drives (record_drive.py's shape: drives NOTHING); stop on at_table() or Ctrl-C
    Under `with console_lock.held("chain_record")`; assert BASEBALL_TEST_RUN unset before any send.

### chain_walk.py  (owner: CONTROLLER agent)

    walk(chain, capture, read_heading, log=print, time_cap=400.0, shots=None) -> dict
        # {arrived:bool, seconds, pushes, k_final, fixes:[per-iteration dicts], failure:str|None}
    loop (k = 0, the spawn, trusted — TRUST_RESET_SPAWN semantics):
        target = chain.waypoints[k+1]
        if target.heading is not None: slow_traverse.turn_to(target.heading, ...)   # camera to the recorded heading
        ONE push: slow_traverse.walk_leg(0.0, -PUSH_MAG, PUSH_SEC, ..., step_sec=PUSH_SEC)   PUSH_MAG=0.45, PUSH_SEC=0.40 (§6)
        (walk_leg settles SETTLE_SEC itself — check; do not add a second settle blindly)
        img = capture(); fix = chain.locate(img, k)
        if k+1 >= len-3 and at_table(img): arrived — STOP AT ONCE (the user watched the character win
            the table and walk away; nothing moves after the prompt is on screen)
        if fix is None: misses += 1; after MISS_MAX (3): escape = jump (input_controller.press("cross")
            — Cross IS jump, §8(g)) then alternate sidestep 0.3 s at 0.45 left/right; continue
        elif chain.reached(fix, k+1): k = min(fix.k, k+window); stall = 0
        else: stall += 1; if stall >= STALL_MAX (4): escape as above, stall = 0
        lateral: if abs(fix.dx) > pose.ALIGN_TOL_PX: ONE strafe push, magnitude/time from
            pose.align_lateral's closed-loop gain (~2400 px per unit-magnitude-second), capped at 0.3 s,
            direction per pose.offset's sign convention (dx > 0 = camera is LEFT of the reference ->
            strafe RIGHT). Never more than one lateral push per iteration; never steer mid-push.
        time_cap -> failure "timed out"
    NEVER: reset, press square/triangle/options, open the pause menu, touch world_map.json.
    Every iteration appends its fix to the result and, with shots=, saves the frame.

### Harness  (owner: CONTROLLER agent, second file: overnight/chain_trials.py)

    TRIALS=10: reset -> chain_walk.walk(...) with a 420 s external ceiling via
    `_harness.run_trial`'s subprocess pattern (`--one-trial`), outcomes arrived / timed_out / failed,
    JSON saved atomically (write tmp + os.replace) after every trial, log line per trial:
    `[ n] ARRIVED|TIMED_OUT|FAILED  k=..  pushes=..  seconds=..  failure=..`

## Definition of done, per agent

SENSOR: chain.py + tools/chain_validate.py + tests/routing/test_chain_locate.py (synthetic chain from
  one real frame shifted/scaled with cv2.warpAffine — held-out frames must land on the right index;
  two mutants named). Smoke-test the validator on 5 frames. Write the exact sweep command the manager
  will run.
RECORDER: chain_record.py + tests/routing/test_chain_record.py (record() with a stub capture writes
  N lines and N files, append-only across two calls, survives a stop mid-way; the flag holds every
  send off; two mutants). No console.
CONTROLLER: chain_walk.py + overnight/chain_trials.py + tests/routing/test_chain_walk.py (stubbed
  turn_to/walk_leg/capture/locate/at_table; asserts: stops the instant at_table is True with NO further
  push; advances k on reached; escapes after STALL_MAX; one lateral push max; time cap; two mutants).
  No console.
