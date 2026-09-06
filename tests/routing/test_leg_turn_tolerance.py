"""The leg executor must be able to tighten its turn tolerance.

Measured 2026-09-03: with slow_traverse's 4.0 default, every turn step on
portrait_room -> bar_pool_room is a no-op (the leg's whole curve is 6.6 deg), so
the recorded shape is discarded and the leg is walked straight at whatever
heading the character arrived with.
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

import numpy as np
from PIL import Image

import graph_walk as gw
import slow_traverse as st

# A real frame, not None: with None the leg raises after the turn and the test
# would be asserting through an exception.
#
# AND IT MUST CHANGE BETWEEN CALLS. A constant frame reads as ZERO view change,
# which is the stall signal, so walk_link took the blocked branch into
# `_slip_past` -> `walk_steps.turn_to` — which this test does NOT mock and which
# calls the real `compass.fast_capture()` in a sleep loop. The test then ran for
# over 280s and was written off as machine load; it is not load, and it did the
# same on an idle machine. It never reported either way, so the plumbing this
# file exists to guard was going UNCHECKED (2026-09-05).
_FRAMES = [Image.fromarray(
    (np.random.RandomState(k).rand(270, 480, 3) * 255).astype("uint8"))
    for k in range(64)]
_seq = {"i": 0}


def FRAME():
    _seq["i"] += 1
    return _FRAMES[_seq["i"] % len(_FRAMES)]

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


seen = []
real = st.turn_to


def fake_turn_to(target, read_heading, capture, log=None, tolerance=st.TURN_TOLERANCE,
                 max_steps=14):
    seen.append(tolerance)
    return target, []


class FakeMap:
    def steps_for(self, a, b):
        return [{"bearing": 286.6, "dur": 0.2, "speed": 0.25},
                {"bearing": 292.2, "dur": 0.2, "speed": 0.25}]


def run_leg():
    seen.clear()
    st.turn_to = fake_turn_to
    try:
        gw.walk_link(FakeMap(), "a", "b",
                     capture=FRAME,
                     read_heading=lambda: 289.1,
                     log=lambda *a: None)
    except Exception as e:
        print(f"  (walk_link raised {type(e).__name__}: {e})")
        FAILS.append(f"walk_link raised: {type(e).__name__}")
    finally:
        st.turn_to = real
    return list(seen)


# Default: unchanged behaviour, and CRUCIALLY never None — `abs(err) <= None`
# raises, and it would raise mid-leg on the live console.
gw.LEG_TURN_TOLERANCE = None
tols = run_leg()
check("default passes slow_traverse's own tolerance, not None",
      tols and all(t == st.TURN_TOLERANCE for t in tols))
check("None never reaches turn_to", None not in tols)

# Tightened: the flag actually reaches the turn.
gw.LEG_TURN_TOLERANCE = 1.0
tols = run_leg()
check("a tightened tolerance reaches turn_to",
      tols and all(t == 1.0 for t in tols))

gw.LEG_TURN_TOLERANCE = None
print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
