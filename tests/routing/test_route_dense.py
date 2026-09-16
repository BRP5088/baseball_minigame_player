
import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

#!/usr/bin/env python3
"""Self-consistency checks for route_dense.DENSE_ROUTE.

Offline: reads no frames, sends no input, makes no API calls. Asserts the dense
trajectory is internally coherent -- bearings in range, durations positive,
windows monotonic and non-overlapping, totals reconciling with the segmentation
in route_data. It cannot verify the trajectory is CORRECT against the game.
"""
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import route_dense as rd

RECORDING_LENGTH = 67.61

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def adiff(a, b):
    d = (a - b) % 360
    return d - 360 if d > 180 else d


# --- shape ----------------------------------------------------------------
check(isinstance(rd.DENSE_ROUTE, list) and rd.DENSE_ROUTE, "DENSE_ROUTE is empty or not a list")
check(len(rd.DENSE_WINDOWS) == len(rd.DENSE_ROUTE),
      f"DENSE_WINDOWS has {len(rd.DENSE_WINDOWS)} entries, DENSE_ROUTE has {len(rd.DENSE_ROUTE)}")

for i, entry in enumerate(rd.DENSE_ROUTE):
    check(isinstance(entry, tuple) and len(entry) == 2,
          f"entry {i}: expected (bearing, seconds), got {entry!r}")
    if not (isinstance(entry, tuple) and len(entry) == 2):
        continue
    bearing, secs = entry
    check(isinstance(bearing, (int, float)) and 0.0 <= bearing < 360.0,
          f"entry {i}: bearing {bearing!r} outside [0, 360)")
    check(isinstance(secs, (int, float)) and secs > 0,
          f"entry {i}: seconds {secs!r} is not positive")
    check(secs <= 6.0, f"entry {i}: seconds {secs!r} too long for a dense segment")

# --- windows monotonic, non-overlapping, inside the moving span ------------
prev_end = 0.0
for i, w in enumerate(rd.DENSE_WINDOWS[:len(rd.DENSE_ROUTE)]):
    check(isinstance(w, tuple) and len(w) == 2, f"DENSE_WINDOWS[{i}]: expected (t0, t1), got {w!r}")
    if not (isinstance(w, tuple) and len(w) == 2):
        continue
    t0, t1 = w
    check(t1 > t0, f"entry {i}: window ({t0}, {t1}) does not advance in time")
    check(t0 >= prev_end - 1e-9,
          f"entry {i}: window starts at {t0} but entry {i-1} ended at {prev_end} (must be ordered, non-overlapping)")
    prev_end = t1

check(rd.DENSE_WINDOWS[0][0] >= rd.FIRST_MOVING_T - 1e-9,
      f"dense route starts at {rd.DENSE_WINDOWS[0][0]}, before FIRST_MOVING_T {rd.FIRST_MOVING_T} "
      f"-- the typewriter oscillation must stay excluded")
check(abs(rd.DENSE_WINDOWS[-1][1] - rd.LAST_MOVING_T) < 1e-6,
      f"dense route ends at {rd.DENSE_WINDOWS[-1][1]}, expected LAST_MOVING_T {rd.LAST_MOVING_T}")

# --- a segment's moving time cannot exceed its own wall clock ---------------
for i, (entry, w) in enumerate(zip(rd.DENSE_ROUTE, rd.DENSE_WINDOWS)):
    span = w[1] - w[0]
    check(entry[1] <= span + 1e-6,
          f"entry {i}: {entry[1]}s of movement in a {span:.3f}s window")

# --- contiguous neighbours were split for a reason, so must differ ---------
for i in range(len(rd.DENSE_ROUTE) - 1):
    if abs(rd.DENSE_WINDOWS[i][1] - rd.DENSE_WINDOWS[i + 1][0]) < 1e-9:
        sep = abs(adiff(rd.DENSE_ROUTE[i][0], rd.DENSE_ROUTE[i + 1][0]))
        check(sep > 1.0,
              f"entries {i} and {i+1} are contiguous in time with bearing sep {sep:.2f} deg; "
              f"they should have been merged into one segment")

# --- totals reconcile ------------------------------------------------------
total = sum(s for _, s in rd.DENSE_ROUTE)
check(abs(total - rd.TOTAL_MOVING_SECONDS) < 0.02,
      f"DENSE_ROUTE durations sum to {total:.3f} but TOTAL_MOVING_SECONDS says {rd.TOTAL_MOVING_SECONDS}")

pause_total = sum(p[2] for p in rd.PAUSES)
grand = rd.TYPEWRITER_OSCILLATION + rd.TOTAL_MOVING_SECONDS + pause_total
check(abs(grand - RECORDING_LENGTH) < 0.02,
      f"typewriter {rd.TYPEWRITER_OSCILLATION} + moving {rd.TOTAL_MOVING_SECONDS} + pauses "
      f"{pause_total:.2f} = {grand:.2f}, but the recording is {RECORDING_LENGTH}s")

# --- pauses ----------------------------------------------------------------
prev_end = 0.0
for i, p in enumerate(rd.PAUSES):
    check(len(p) == 3, f"PAUSES[{i}]: expected (t0, t1, seconds), got {p!r}")
    if len(p) != 3:
        continue
    t0, t1, secs = p
    check(secs > 0, f"PAUSES[{i}]: duration {secs} is not positive")
    check(abs((t1 - t0) - secs) < 0.02,
          f"PAUSES[{i}]: window ({t0}, {t1}) spans {t1-t0:.2f}s but claims {secs}s")
    check(t0 >= prev_end, f"PAUSES[{i}]: starts at {t0}, before the previous pause ended at {prev_end}")
    prev_end = t1

# a pause must not overlap any moving window
for i, (pt0, pt1, _) in enumerate(rd.PAUSES):
    for j, (wt0, wt1) in enumerate(rd.DENSE_WINDOWS):
        check(not (pt0 < wt1 - 1e-9 and wt0 < pt1 - 1e-9),
              f"PAUSES[{i}] ({pt0}, {pt1}) overlaps moving window {j} ({wt0}, {wt1})")

# --- the flagged curve -----------------------------------------------------
a, b = rd.CURVE_313_TO_67
check(0 <= a < b <= len(rd.DENSE_ROUTE), f"CURVE_313_TO_67 {rd.CURVE_313_TO_67} is not a valid slice")
if 0 <= a < b <= len(rd.DENSE_ROUTE):
    curve = rd.DENSE_ROUTE[a:b]
    check(len(curve) >= 8,
          f"the flagged curve has only {len(curve)} entries; it was supposed to be densely sampled")
    swept = sum(abs(adiff(curve[i + 1][0], curve[i][0])) for i in range(len(curve) - 1))
    check(swept > 60.0,
          f"the flagged curve sweeps only {swept:.1f} deg; expected a large sweep")
    check(max(s for _, s in curve) <= 0.75,
          f"the flagged curve has a {max(s for _,s in curve)}s entry; curvature needs short segments")

# --- L&B sightings ---------------------------------------------------------
check(rd.LB_SIGHTINGS == sorted(rd.LB_SIGHTINGS), "LB_SIGHTINGS is not in increasing time order")
check(len(set(rd.LB_SIGHTINGS)) == len(rd.LB_SIGHTINGS), "LB_SIGHTINGS contains duplicates")
check(rd.LB_WINDOW[0] <= rd.LB_WINDOW[1], f"LB_WINDOW {rd.LB_WINDOW} does not advance")
for t in rd.LB_SIGHTINGS:
    check(rd.LB_WINDOW[0] <= t <= rd.LB_WINDOW[1], f"LB sighting {t} falls outside LB_WINDOW {rd.LB_WINDOW}")
check(rd.LB_SIGHTINGS[0] == rd.LB_WINDOW[0],
      f"LB_WINDOW starts at {rd.LB_WINDOW[0]} but the first sighting is {rd.LB_SIGHTINGS[0]}")
check(rd.LB_SIGHTINGS[-1] == rd.LB_WINDOW[1],
      f"LB_WINDOW ends at {rd.LB_WINDOW[1]} but the last sighting is {rd.LB_SIGHTINGS[-1]}")
observed_gap = max(b - a for a, b in zip(rd.LB_SIGHTINGS, rd.LB_SIGHTINGS[1:]))
check(abs(observed_gap - rd.LB_MAX_GAP) < 0.02,
      f"largest gap between LB sightings is {observed_gap:.2f}s but LB_MAX_GAP says {rd.LB_MAX_GAP}")
check(0.0 < rd.LB_FIRE_RATE < 1.0,
      f"LB_FIRE_RATE {rd.LB_FIRE_RATE} should be a fraction strictly between 0 and 1 "
      f"-- it is a confirm-only detector that misses about half its window")

# --- table checkpoint ------------------------------------------------------
check(rd.DENSE_WINDOWS[-1][0] <= rd.TABLE_FIRST_SEEN <= rd.DENSE_WINDOWS[-1][1],
      f"TABLE_FIRST_SEEN {rd.TABLE_FIRST_SEEN} is not inside the final moving window "
      f"{rd.DENSE_WINDOWS[-1]}")

# --- translation / rotation classification ---------------------------------
check(len(rd.SEGMENT_CLASSIFIED) == len(rd.DENSE_ROUTE),
      f"SEGMENT_CLASSIFIED has {len(rd.SEGMENT_CLASSIFIED)} entries, DENSE_ROUTE has {len(rd.DENSE_ROUTE)}")

for i, entry in enumerate(rd.SEGMENT_CLASSIFIED):
    check(isinstance(entry, tuple) and len(entry) == 3,
          f"SEGMENT_CLASSIFIED[{i}]: expected (bearing, seconds, is_translation), got {entry!r}")
    if not (isinstance(entry, tuple) and len(entry) == 3):
        continue
    b, secs, is_tr = entry
    check(0.0 <= b < 360.0, f"SEGMENT_CLASSIFIED[{i}]: bearing {b!r} outside [0, 360)")
    check(secs > 0, f"SEGMENT_CLASSIFIED[{i}]: seconds {secs!r} is not positive")
    check(isinstance(is_tr, bool), f"SEGMENT_CLASSIFIED[{i}]: is_translation {is_tr!r} is not a bool")

# the labelled list must agree with DENSE_ROUTE entry for entry
for i, (dense, lab) in enumerate(zip(rd.DENSE_ROUTE, rd.SEGMENT_CLASSIFIED)):
    check(abs(dense[0] - lab[0]) < 1e-9 and abs(dense[1] - lab[1]) < 1e-9,
          f"SEGMENT_CLASSIFIED[{i}] {lab[:2]} disagrees with DENSE_ROUTE[{i}] {dense}")

# TRAVEL_ONLY is exactly the translation-labelled subset, in order
expected = [(b, s) for b, s, k in rd.SEGMENT_CLASSIFIED if k]
check(rd.TRAVEL_ONLY == expected,
      f"TRAVEL_ONLY ({len(rd.TRAVEL_ONLY)} entries) is not the is_translation subset of "
      f"SEGMENT_CLASSIFIED ({len(expected)} entries)")

for i, entry in enumerate(rd.TRAVEL_ONLY):
    check(isinstance(entry, tuple) and len(entry) == 2,
          f"TRAVEL_ONLY[{i}]: expected (bearing, seconds), got {entry!r}")
    if isinstance(entry, tuple) and len(entry) == 2:
        check(0.0 <= entry[0] < 360.0, f"TRAVEL_ONLY[{i}]: bearing {entry[0]!r} outside [0, 360)")
        check(entry[1] > 0, f"TRAVEL_ONLY[{i}]: seconds {entry[1]!r} is not positive")

travel_total = sum(s for _, s in rd.TRAVEL_ONLY)
check(abs(travel_total - rd.TRAVEL_ONLY_SECONDS) < 0.02,
      f"TRAVEL_ONLY sums to {travel_total:.3f} but TRAVEL_ONLY_SECONDS says {rd.TRAVEL_ONLY_SECONDS}")

dropped_total = sum(s for _, s, k in rd.SEGMENT_CLASSIFIED if not k)
check(abs(dropped_total - rd.DROPPED_SECONDS) < 0.02,
      f"dropped segments sum to {dropped_total:.3f} but DROPPED_SECONDS says {rd.DROPPED_SECONDS}")

check(abs((rd.TRAVEL_ONLY_SECONDS + rd.DROPPED_SECONDS) - rd.TOTAL_MOVING_SECONDS) < 0.02,
      f"travel {rd.TRAVEL_ONLY_SECONDS} + dropped {rd.DROPPED_SECONDS} != "
      f"TOTAL_MOVING_SECONDS {rd.TOTAL_MOVING_SECONDS}")

# the headline sanity check: travel must sit strictly between the steady-heading
# legs and all movement. Equal to the steady-heading total would mean the curves
# contributed nothing, i.e. the classifier ate them.
check(rd.STEADY_HEADING_SECONDS < rd.TRAVEL_ONLY_SECONDS < rd.TOTAL_MOVING_SECONDS,
      f"TRAVEL_ONLY_SECONDS {rd.TRAVEL_ONLY_SECONDS} must be strictly between "
      f"STEADY_HEADING_SECONDS {rd.STEADY_HEADING_SECONDS} and "
      f"TOTAL_MOVING_SECONDS {rd.TOTAL_MOVING_SECONDS}")
check(abs((rd.TRAVEL_ONLY_SECONDS - rd.STEADY_HEADING_SECONDS) - rd.CURVE_CONTRIBUTION) < 0.02,
      f"CURVE_CONTRIBUTION {rd.CURVE_CONTRIBUTION} does not equal TRAVEL_ONLY_SECONDS - "
      f"STEADY_HEADING_SECONDS ({rd.TRAVEL_ONLY_SECONDS - rd.STEADY_HEADING_SECONDS:.2f})")

# the dropped run must be exactly one contiguous block at the front
d0, d1 = rd.DROPPED_SEGMENTS
dropped_idx = [i for i, (_, _, k) in enumerate(rd.SEGMENT_CLASSIFIED) if not k]
check(dropped_idx == list(range(d0, d1)),
      f"dropped indices {dropped_idx[:5]}..{dropped_idx[-3:] if dropped_idx else []} are not the "
      f"contiguous block DROPPED_SEGMENTS {rd.DROPPED_SEGMENTS}")
check(rd.DROPPED_SPAN[0] == rd.DENSE_WINDOWS[d0][0] and rd.DROPPED_SPAN[1] == rd.DENSE_WINDOWS[d1 - 1][1],
      f"DROPPED_SPAN {rd.DROPPED_SPAN} does not match the windows of segments {rd.DROPPED_SEGMENTS}")

# THE CURVE MUST SURVIVE -- it is turning AND translating, and is replayable
ca, cb = rd.CURVE_313_TO_67
for i in range(ca, cb):
    check(rd.SEGMENT_CLASSIFIED[i][2] is True,
          f"curve segment {i} was classified as rotation-only; the 313->67 curve is "
          f"genuine travel and must be retained")

# every segment after the first verified full stop is travel
for i, (_, _, k) in enumerate(rd.SEGMENT_CLASSIFIED):
    if rd.DENSE_WINDOWS[i][0] >= rd.DROPPED_SPAN[1]:
        check(k is True, f"segment {i} starts after the drop boundary {rd.DROPPED_SPAN[1]} "
                         f"but is classified as rotation-only")

if fails:
    for f in fails:
        print(f"  FAIL: {f}")
    sys.exit(1)

print(f"route_dense OK: {len(rd.DENSE_ROUTE)} segments / {total:.2f}s moving; "
      f"TRAVEL_ONLY {len(rd.TRAVEL_ONLY)} segments / {travel_total:.2f}s "
      f"({rd.DROPPED_SECONDS:.2f}s rotation-only dropped, t={rd.DROPPED_SPAN[0]}-{rd.DROPPED_SPAN[1]}); "
      f"curve retained; {len(rd.LB_SIGHTINGS)} L&B sightings")
