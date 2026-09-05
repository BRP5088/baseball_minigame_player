
import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)

#!/usr/bin/env python3
"""Self-consistency checks for route_data.DEMO_ROUTE.

Offline: reads no frames, sends no input, makes no API calls. This asserts the
extracted route is internally coherent -- bearings in range, durations positive
and physically possible, legs ordered in time, totals reconciling with the
segmentation they were derived from. It cannot verify the route is CORRECT
against the game; only a live walk can do that.
"""
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import route_data as rd

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# --- shape ----------------------------------------------------------------
check(isinstance(rd.DEMO_ROUTE, list), "DEMO_ROUTE is not a list")
check(len(rd.DEMO_ROUTE) > 0, "DEMO_ROUTE is empty")

for i, leg in enumerate(rd.DEMO_ROUTE):
    check(isinstance(leg, tuple) and len(leg) == 3,
          f"leg {i}: expected a 3-tuple (bearing, seconds, checkpoint), got {leg!r}")
    if not (isinstance(leg, tuple) and len(leg) == 3):
        continue
    bearing, secs, cp = leg
    check(isinstance(bearing, (int, float)) and 0.0 <= bearing < 360.0,
          f"leg {i}: bearing {bearing!r} outside [0, 360)")
    check(isinstance(secs, (int, float)) and secs > 0,
          f"leg {i}: moving_seconds {secs!r} is not positive")
    check(secs <= 30.0,
          f"leg {i}: moving_seconds {secs!r} implausibly long for one leg")
    check(cp is None or isinstance(cp, str),
          f"leg {i}: checkpoint {cp!r} is neither None nor a str")

# --- checkpoints name real landmark detectors ------------------------------
KNOWN = {"sees_lb_building", "at_baseball_table", "in_lb_interior"}
for i, (_, _, cp) in enumerate(rd.DEMO_ROUTE):
    if cp is not None:
        check(cp in KNOWN, f"leg {i}: unknown checkpoint {cp!r}, expected one of {sorted(KNOWN)}")
        check(cp in rd.LANDMARK_FIRST_SEEN,
              f"leg {i}: checkpoint {cp!r} has no LANDMARK_FIRST_SEEN entry")

# --- spawn bearing ---------------------------------------------------------
check(0.0 <= rd.SPAWN_BEARING < 360.0,
      f"SPAWN_BEARING {rd.SPAWN_BEARING!r} outside [0, 360)")

# --- windows: one per leg, ordered, non-overlapping, inside the recording ---
check(len(rd.LEG_WINDOWS) == len(rd.DEMO_ROUTE),
      f"LEG_WINDOWS has {len(rd.LEG_WINDOWS)} entries but DEMO_ROUTE has {len(rd.DEMO_ROUTE)}")

prev_end = 0.0
for i, w in enumerate(rd.LEG_WINDOWS[:len(rd.DEMO_ROUTE)]):
    check(isinstance(w, tuple) and len(w) == 2, f"LEG_WINDOWS[{i}]: expected (t0, t1), got {w!r}")
    if not (isinstance(w, tuple) and len(w) == 2):
        continue
    t0, t1 = w
    check(t1 > t0, f"leg {i}: window ({t0}, {t1}) does not advance in time")
    check(t0 >= prev_end, f"leg {i}: window starts at {t0} but leg {i-1} ended at {prev_end} (legs must be ordered and disjoint)")
    check(t1 <= rd.TOTAL_ELAPSED,
          f"leg {i}: window ends at {t1}, past the end of the recording ({rd.TOTAL_ELAPSED})")
    prev_end = t1

# --- moving_seconds must fit inside its own wall-clock window --------------
for i, (leg, w) in enumerate(zip(rd.DEMO_ROUTE, rd.LEG_WINDOWS)):
    secs = leg[1]
    span = w[1] - w[0]
    check(secs <= span + 1e-6,
          f"leg {i}: moving_seconds {secs} exceeds its wall-clock window {span:.2f}s")

# --- checkpoint landmark must become visible within its own leg's window ----
for i, (_, _, cp) in enumerate(rd.DEMO_ROUTE):
    if cp is None or cp not in rd.LANDMARK_FIRST_SEEN:
        continue  # already reported above as an unknown / unlisted checkpoint
    seen = rd.LANDMARK_FIRST_SEEN[cp]
    t0, t1 = rd.LEG_WINDOWS[i]
    check(t0 <= seen <= t1,
          f"leg {i}: checkpoint {cp!r} first seen at t={seen}, outside the leg window ({t0}, {t1})")

# --- totals reconcile ------------------------------------------------------
walk_sum = sum(leg[1] for leg in rd.DEMO_ROUTE)
check(abs(walk_sum - rd.TOTAL_WALKING) < 0.02,
      f"sum of DEMO_ROUTE moving_seconds is {walk_sum:.2f} but TOTAL_WALKING says {rd.TOTAL_WALKING}")

check(abs((rd.TOTAL_MOVING + rd.TOTAL_STATIONARY) - rd.TOTAL_ELAPSED) < 0.02,
      f"TOTAL_MOVING {rd.TOTAL_MOVING} + TOTAL_STATIONARY {rd.TOTAL_STATIONARY} "
      f"!= TOTAL_ELAPSED {rd.TOTAL_ELAPSED}")

# every moving second is walking, turning, or the excluded typewriter wobble
accounted = rd.TOTAL_WALKING + rd.TOTAL_TURNING + rd.TYPEWRITER_OSCILLATION
check(abs(accounted - rd.TOTAL_MOVING) < 0.02,
      f"walking {rd.TOTAL_WALKING} + turning {rd.TOTAL_TURNING} + typewriter "
      f"{rd.TYPEWRITER_OSCILLATION} = {accounted:.2f}, but TOTAL_MOVING is {rd.TOTAL_MOVING}")

check(rd.TOTAL_WALKING < rd.TOTAL_ELAPSED,
      "TOTAL_WALKING is not less than TOTAL_ELAPSED -- moving time cannot exceed elapsed time")

# --- the threshold really does sit in the measured gap ---------------------
check(rd.STILL_MAX_OBSERVED < rd.MOVE_THRESHOLD < rd.MOVE_MIN_OBSERVED,
      f"MOVE_THRESHOLD {rd.MOVE_THRESHOLD} is not inside the measured separation "
      f"({rd.STILL_MAX_OBSERVED}, {rd.MOVE_MIN_OBSERVED})")

# --- uncertainty table is consistent with the route ------------------------
for i, (b0, b1, span) in rd.BEARING_UNCERTAIN.items():
    check(0 <= i < len(rd.DEMO_ROUTE), f"BEARING_UNCERTAIN names leg {i}, which does not exist")
    check(span > 0, f"BEARING_UNCERTAIN[{i}]: span {span} is not positive")
    if 0 <= i < len(rd.DEMO_ROUTE):
        # the leg's stated bearing should lie within the drift it is flagged for
        bearing = rd.DEMO_ROUTE[i][0]
        lo_gap = min((bearing - b0) % 360, (b0 - bearing) % 360)
        hi_gap = min((bearing - b1) % 360, (b1 - bearing) % 360)
        check(lo_gap <= span + 1e-6 and hi_gap <= span + 1e-6,
              f"leg {i}: stated bearing {bearing} is not within the flagged drift {b0}->{b1}")

# --- consecutive legs should actually be distinct headings -----------------
for i in range(len(rd.DEMO_ROUTE) - 1):
    a = rd.DEMO_ROUTE[i][0]
    b = rd.DEMO_ROUTE[i + 1][0]
    sep = min((a - b) % 360, (b - a) % 360)
    check(sep > 1.0,
          f"legs {i} and {i+1} have effectively the same bearing ({a} vs {b}); "
          f"they should have been merged into one leg")

if fails:
    for f in fails:
        print(f"  FAIL: {f}")
    sys.exit(1)

print(f"route_data OK: {len(rd.DEMO_ROUTE)} legs, {sum(l[1] for l in rd.DEMO_ROUTE):.2f}s walking "
      f"of {rd.TOTAL_ELAPSED:.2f}s elapsed, spawn {rd.SPAWN_BEARING} deg, "
      f"{len(rd.BEARING_UNCERTAIN)} leg(s) flagged uncertain")
