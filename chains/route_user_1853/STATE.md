# The navigation state that arrived 40 of 40 (2026-09-08, batch 28)

- **Code:** git tag `nav-40-of-40` = commit 2c8fea7. `git checkout nav-40-of-40` restores it.
- **Route:** this directory, `chains/route_user_1853` -- the user's own recorded drive,
  205 waypoints at 0.25 s, compass on 94% of frames. The loop matches every live
  frame against these images. Without them there is no navigation.
- **Flags live on that build:** STOP_LOOK_YAW, STOP_YAW_SKIP_LAST_STOP, DOOR_STOP_EXTRA_PUSH
  ON; STOP_YAW_NEAR_FIT_ONLY, BAR_STOP_EARLY_TURN, BLIND_LOOK_AROUND, PITCH_CORRECT OFF.
- **Harness:** `overnight/chain_trials.py --chain route_user_1853 --trials 40 --attempts 2`.
- **Evidence:** `overnight/chain_trials_batch28_goal.{log,json}`, `overnight/goal_batch_arrivals.jpg`,
  verified by `tools/verify_streak.py` (40 with reloads allowed, 27 with none).
- **Rig:** the frame-dump chiaki build (`chiaki-ng-build/`, FrameDump symbols present),
  `CHIAKI_FRAME_DUMP=/tmp/chiaki_frame.bin`, capture via `frame_dump.read_frame`.
