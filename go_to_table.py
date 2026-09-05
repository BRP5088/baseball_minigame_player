"""Reset, then walk the demonstrated route to the Baseball Cards table."""
import os
import sys
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-goto")

D = sys.argv[1] if len(sys.argv) > 1 else "."
APPROACH_STEPS = 8
APPROACH_SEC = 0.6

import compass
import input_controller as ic
import reset_env
import reset_walk

cap = compass.fast_capture
ic.focus_chiaki_window(force=True)
time.sleep(1.0)

t0 = time.time()
try:
    spawn = reset_env.reset_environment(log=lambda *a: None)
    print(f"  reset {time.time()-t0:.0f}s, spawn {compass.describe(spawn)}", flush=True)
except reset_env.ResetError as exc:
    raise SystemExit(f"  RESET FAILED: {exc}")

# ANCHOR the heading against the known spawn. The reload is deterministic and
# every clean reset has read 87-91, so a spawn reading of, say, 177 is a
# labelling shift rather than a different spawn — and starting 90 degrees wrong
# walks the whole route perpendicular to itself.
anchor = reset_walk.read_heading_near(cap, reset_walk.SPAWN_FACING, log=print)
if anchor is None:
    raise SystemExit(f"  spawn heading never read near "
                     f"{reset_walk.SPAWN_FACING:.0f} — refusing to walk")
print(f"  spawn heading confirmed {compass.describe(anchor)}", flush=True)

# NO PITCH LEVELLING before the walk. Pitch does not affect where walking
# takes you — movement is camera-YAW relative and pitch is independent — but
# levelling drove the camera down at a bright floor, where only one compass
# letter cleared the blob filter, so the bearing became unreadable and the
# walk aborted at step 1. The reset already restores a workable pitch.

try:
    # The VERIFIED route, walked step by step with every landmark confirmed by
    # eye. The earlier spliced_route (since deleted) came from demo timings
    # and never replayed:
    # it treated the office door as an obstacle to walk around, when it is the
    # waypoint you walk INTO.
    import route_verified
    route = [("until_blocked" if mode == "until_blocked" else "travel",
              bearing, secs, None)
             for bearing, mode, secs, _ in route_verified.TO_BAR]
    b = reset_walk.walk_route(log=lambda m: print(m, flush=True), save_dir=D,
                              route=route)
    print(f"  DENSE ROUTE COMPLETE in {time.time()-t0:.0f}s, facing "
          f"{compass.describe(b)}", flush=True)
except reset_walk.WalkError as exc:
    print(f"  walk did not confirm: {exc}", flush=True)

# GUIDED FINAL APPROACH: look around rather than demand a precise arrival.
try:
    import landmarks
    if landmarks.at_baseball_table(cap()) is True:
        print("  TABLE REACHED by the route itself", flush=True)
    elif reset_walk.find_table(cap, log=lambda m: print(m, flush=True)):
        print("  TABLE REACHED by search", flush=True)
    else:
        print("  table not found by route or search", flush=True)
except ImportError:
    pass

cap().save(os.path.join(D, "table_attempt.jpg"), quality=88)
print("  saved table_attempt.jpg", flush=True)
