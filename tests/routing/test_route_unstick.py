"""The route's three movement decisions, faked at the boundary.

None of go.py had behavioural coverage before 2026-09-01, which is precisely
the code that failed every cycle that night. Each block here corresponds to a
real failure:

  * a step that walks into an NPC looked identical to one that worked;
  * pushing forward when already PAST the table made the overshoot worse;
  * arrival was judged on a frame captured while still moving.
"""
import os
import os as _os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import numpy as np
from PIL import Image

import go
import walk_steps as ws

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


class Fake:
    """Records what was asked of the movement layer and what it answered."""

    def __init__(self, moves, unstick_moves=None):
        self.moves = list(moves)          # what each walk_forward reports
        self.unstick_moves = list(unstick_moves or [])
        self.walks = 0
        self.unsticks = 0

    def walk_forward(self, speed, seconds, strafe=0.0):
        self.walks += 1
        return self.moves.pop(0) if self.moves else 0.0

    def unstick(self, speed, seconds, log=print):
        self.unsticks += 1
        return self.unstick_moves.pop(0) if self.unstick_moves else 0.0


def _install(fake):
    go.ws = types.SimpleNamespace(walk_forward=fake.walk_forward,
                                  unstick=fake.unstick,
                                  STUCK_CHANGE=ws.STUCK_CHANGE,
                                  turn_to=lambda *a, **k: None)
    return fake


_REAL_WS = go.ws

# --- a step that moves is left alone --------------------------------------
f = _install(Fake([20.0]))
moved = go._step_forward(log=lambda m: None)
check(f.unsticks == 0, f"a step that moved {moved} called unstick {f.unsticks}x "
                       "— crabbing after a good step wastes the nudge budget")
check(moved == 20.0, f"_step_forward reported {moved}, expected the 20.0 walk_forward gave")

# --- a blocked step crabs free, and REPORTS WHAT THE CRAB ACHIEVED ---------
# The caller needs to distinguish "an NPC stepped aside" from "this is a wall",
# so the return value must reflect the recovery, not the blocked step.
f = _install(Fake([0.4], unstick_moves=[18.0]))
moved = go._step_forward(log=lambda m: None)
check(f.unsticks == 1, "a step below STUCK_CHANGE must try to crab free")
check(moved == 18.0,
      f"_step_forward reported {moved} after crabbing free (18.0) — reporting "
      "the blocked step instead hides the recovery from the caller")

# --- A CRAB THAT ONLY JIGGLES IS NOT AN ESCAPE ----------------------------
# ws.unstick() calls itself successful at STUCK_CHANGE (2.5), which only means
# "that step was not completely dead". Measured 2026-09-01 against a wall:
# every crab landed 2.5-3.0, while walking moves the frame 16-59 and a real
# escape measured 34.8. At 2.6 the pinned counter reset on every step, so the
# nudge twitched away all twelve of them instead of handing back to the retrace.
f = _install(Fake([0.9], unstick_moves=[2.6]))
moved = go._step_forward(log=lambda m: None)
check(moved < ws.STUCK_CHANGE,
      f"a crab of 2.6 was reported as {moved} — treated as having got free, "
      "when it is inside the jiggle band and must not reset the pinned counter")
check(go.ESCAPED_CHANGE > ws.STUCK_CHANGE,
      f"ESCAPED_CHANGE ({go.ESCAPED_CHANGE}) must sit above STUCK_CHANGE "
      f"({ws.STUCK_CHANGE}), or 'escaped' means no more than 'not dead'")

# --- still pinned after crabbing reports the low value --------------------
f = _install(Fake([0.3], unstick_moves=[0.5]))
moved = go._step_forward(log=lambda m: None)
check(moved < ws.STUCK_CHANGE,
      f"still pinned but reported {moved} — the caller would think it got free")

# --- the threshold is the shared one, not a private copy ------------------
check(ws.STUCK_CHANGE == 2.5,
      f"ws.STUCK_CHANGE is {ws.STUCK_CHANGE}; the route's stuck detection was "
      "calibrated against it (walking moves the frame 16-59, a pinned "
      "character 0.5-2.3) and a new value silently changes that")

go.ws = _REAL_WS

# --- _wait_until_still returns once the view stops changing ----------------
# Arrival must be judged AFTER the sticks stop: a frame taken mid-walk shows
# where the character was passing through, not where it came to rest.
class FakeCompass:
    def __init__(self, series):
        self.series = list(series)
        self.calls = 0

    def fast_capture(self):
        self.calls += 1
        v = self.series.pop(0) if self.series else self.series_last
        self.series_last = v
        return Image.new("RGB", (64, 64), (v, v, v))


_REAL_COMPASS = go.compass
# Two identical frames in a row = still. 10,10 differ by 0 -> returns on the
# second capture.
fc = FakeCompass([10, 10, 200, 200])
go.compass = types.SimpleNamespace(fast_capture=fc.fast_capture)
go._wait_until_still(log=lambda m: None, timeout=5.0)
check(fc.calls == 2,
      f"_wait_until_still took {fc.calls} captures on an already-still screen, "
      "expected 2 — it must return as soon as two frames agree")

# A screen that never settles must give up at the timeout rather than hang.
fc = FakeCompass([0, 120, 0, 120, 0, 120, 0, 120, 0, 120, 0, 120, 0, 120])
go.compass = types.SimpleNamespace(fast_capture=fc.fast_capture)
go._wait_until_still(log=lambda m: None, timeout=1.2)
check(fc.calls >= 2, "a never-settling screen must still return a frame")

go.compass = _REAL_COMPASS

if fails:
    for f_ in fails:
        print("  FAIL:", f_)
    sys.exit(1)
print("  route movement: good steps are not crabbed, blocked steps crab and "
      "report the RECOVERY, a still-pinned step stays below the bar, and "
      "arrival waits for the view to settle (bounded)")
