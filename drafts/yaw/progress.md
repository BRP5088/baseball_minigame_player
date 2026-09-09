# TASK 3 — yaw-nulling static audit — progressStarted 2026-09-07. Read-only on all existing files; writes only under drafts/yaw/.## Established
- Read CLAUDE.md (in context), GRAVEYARD.md, STAIRS_APPROACH.md, pose.py (345 lines).
- pose.py: offset() and displacement() both fit cv2.estimateAffinePartial2D on ORB matches,
  neither reads the compass; offset() docstring says "Null the yaw with the compass first".
- pose.py has NO import of compass; yaw nulling, if any, must live in the CALLER.## Assumed (to verify)
- graph_walk.py is the only production caller of pose.* (grep pending).## Next
- read graph_walk.py fully; grep consumers.## 2026-09-07 — after reading graph_walk.py (2308 lines) in full
### Established (by reading the file; line numbers are graph_walk.py at HEAD 643d1f6)
- Pixel-offset paths in graph_walk.py: _slip_past.moved_since (:563-575, pose.displacement, vs SLIP_PROGRESS_PX :482 = 20.0);
  align_at_node (:1734-1807) -> pose.align_lateral (pose.py:253) -> pose.offset, vs ALIGN_TOL_PX (pose.py:165 = 35.0).
- Yaw null lives ONLY in align_at_node :1764-1802: st.turn_to(want, tolerance=YAW_NULL_TOLERANCE_DEG=0.5) (:1783-1785).
  Three fall-through branches CONTINUE to align_lateral with yaw NOT nulled: want is None (:1766-1769),
  got_h is None (:1786-1789), exception (:1800-1802). Residual after a partial turn is LOGGED (:1795-1799) and not acted on.
- _slip_past: `before` is captured immediately after ws.turn_to(bearing) (:584-585, :597-598, :613-614) with NO settle sleep;
  the after-frame follows a LEFT-STICK push + sleep 0.3. No right-stick input between the pair.
- pose.same_pose / SAME_POSE_PX: grep finds ZERO production callers (only tests + a comment at graph_walk.py:117).
- pose.displacement consumers: _slip_past (live), overnight/walk_curve.py (the §6 walking table), tests.
- face_the_table / approach_goal / home_to_table / reach_table / recover_to_node / confirm / locate: NO pixel offset;
  they use at_table()/ink()/identify()/match_count. home_to_table and the goaround loop are unreachable (return at :1043).
- stream_is_live: grey-level mean |diff| vs FROZEN_DELTA 0.35 — yaw would only INCREASE it (fails safe).
- walk_link 'best' is GREY LEVELS (slow_traverse._change) vs STALL_CHANGE 6.0 — not pixels.
### Assumed (to check next)
- slow_traverse.turn_to returns after a SETTLED read (closed loop) — so the frame after it is at the reported heading.
- walk_forward/walk_leg drive left stick only.
- turn_curve.plan_turn floor 0.5 deg vs YAW_NULL_TOLERANCE_DEG 0.5 (boundary semantics).
