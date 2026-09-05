"""The stall gate must sit BELOW the moving population, not inside it.

MEASURED over 20 runs of office_corridor -> office_door step 7/7:

    3.1 | 5.5 5.7 5.7 5.8 | 6.1 6.3 6.3 6.5 6.5 6.6 6.9 6.9 7.0 7.1 7.2 7.3
        7.3 7.6 7.9

One population, no low cluster. At 6.0 the gate fired on 5 of 20 as FALSE
POSITIVES, each running the escape ladder, which injects unaccounted forward
push. Runs with a clean office leg reached bar_pool_room 14/15; runs where the
gate fired reached it 0/5 (Fisher p = 0.00039).
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# The real observed values for a step that was MOVING every time.
MOVING = [3.1, 5.5, 5.7, 5.7, 5.8, 6.1, 6.3, 6.3, 6.5, 6.5, 6.6, 6.9, 6.9,
          7.0, 7.1, 7.2, 7.3, 7.3, 7.6, 7.9]
# A genuinely blocked push barely moves the view at all — observed on the
# jukebox leg's failures, whose arrival frames held 0-19 keypoints.
BLOCKED = [0.0, 0.4, 0.9, 1.2, 1.6]

# A/B'd 2026-09-03 AND REVERTED: 2.5 arrived 6/10 against 6.0's 8/10
# (p = 0.63). The strong observational association that motivated the change
# (clean office leg -> 14/15, stalled -> 0/5, p = 0.00039) did NOT survive
# intervention, so the low view-change was a SYMPTOM of an already-bad run, not
# its cause. STALL_CHANGE is back at 6.0 and this test now documents the shape
# of the data rather than asserting the threshold's position.
fires_moving = [v for v in MOVING if v < gw.STALL_CHANGE]
fires_blocked = [v for v in BLOCKED if v < gw.STALL_CHANGE]

check("the gate still fires on a genuinely blocked push",
      len(fires_blocked) == len(BLOCKED))
# NOT asserted: that it never fires on MOVING. At 6.0 it fires on 5 of those 20,
# which LOOKS wrong and measured BETTER. Pinning "no false positives" here would
# encode a change the A/B rejected.
# PIN THE LITERAL. The check here used to be
#     min(MOVING) < gw.STALL_CHANGE < max(MOVING)
# which passes for ANY value in (3.1, 7.9). At 7.8 the gate fires on 19 of the
# 20 measured moving pushes — every healthy walk declared stalled — and this
# file stayed green. Reading the constant under test makes the assertion true
# by construction; the same mistake is documented for MAX_HAND_SIZE.
check("STALL_CHANGE is the value the A/B settled on", gw.STALL_CHANGE == 6.0)
check("the moving population is documented so the next person sees the overlap",
      min(MOVING) < gw.STALL_CHANGE < max(MOVING))
# The false-positive count is the number the A/B actually chose, so it is the
# thing worth pinning: 6.0 fires on 5 of 20 moving pushes and measured BETTER
# than a threshold with none.
check("the false-positive count is the measured one",
      len(fires_moving) == 5)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
