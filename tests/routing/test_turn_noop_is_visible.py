"""A turn that never happened must SAY so, and a real one must not be counted
as one.

WHY THIS EXISTS
---------------
`slow_traverse.turn_to` returns as soon as the heading is inside `tolerance`,
and with TURN_TOLERANCE = 4.0 that is usually true on the FIRST iteration: the
leg portrait_room -> bar_pool_room commands 286.6 / 292.2 / 285.6 / 287.6, a
6.6 degree curve, so a character standing at 289.1 is inside tolerance for all
four and the recorded curve is discarded four times over. The caller's line
still reads

    step 2/4 bearing  292.2 (got  289.1) 0.79s -> walked 0.79s

which looks exactly like a turn that happened — and the step line alone can
never separate the two, because an executed turn also ENDS inside tolerance.
"The code did nothing, and doing nothing looked exactly like working."

So the NO-OP line is the whole point: it makes no-op turns COUNTABLE from logs
that already exist, which is the evidence OPEN-3 (`LEG_TURN_TOLERANCE`, the
project's highest-value open experiment) needs.

This file pins BOTH directions, because either half alone is worthless:
  - a no-op turn must be named a no-op   (else the evidence is missing)
  - a real turn must NOT be named one    (else every leg looks like a no-op and
                                          the count is noise)

Observability only. Nothing here asserts a tolerance, a threshold or any
control-flow decision — those belong to an A/B, not to a diagnostic.
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

import slow_traverse as st
import walk_steps as ws

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class NoSleep:
    """Stands in for a module's `time`, so a turn costs no wall clock.

    Patching `time.sleep` itself would patch it for the whole process; swapping
    the module's own reference is local and is restored in a `finally`.
    """

    @staticmethod
    def sleep(_):
        pass


def _headings(seq):
    """A read_heading yielding `seq`, then repeating its last value forever."""
    box = list(seq)

    def read():
        return box.pop(0) if len(box) > 1 else box[0]

    return read


FRAME = Image.fromarray(
    (np.random.RandomState(0).rand(64, 96, 3) * 255).astype("uint8"))


def st_turn(seq, target, **kw):
    lines = []
    real = st.time
    st.time = NoSleep
    try:
        st.turn_to(target, _headings(seq), lambda: FRAME,
                   log=lines.append, **kw)
    finally:
        st.time = real
    return "\n".join(lines)


def ws_turn(seq, target, **kw):
    lines = []
    real_time, real_read = ws.time, ws.read_heading
    ws.time, ws.read_heading = NoSleep, _headings(seq)
    try:
        ws.turn_to(target, log=lines.append, **kw)
    finally:
        ws.time, ws.read_heading = real_time, real_read
    return "\n".join(lines)


# --- slow_traverse: the module OPEN-3 is about -----------------------------
#
# 289.1 against a commanded 292.2 is the real pair from the leg's own log: an
# error of +3.1 deg, inside the 4.0 default, so nothing is sent.
noop = st_turn([289.1], 292.2)
print(f"  no-op log: {noop!r}")
check("slow_traverse names a first-iteration no-op", "NO-OP" in noop)
check("it says the recorded curve was discarded", "discarded" in noop)
check("the no-op line carries the numbers to count from",
      "292.2" in noop and "289.1" in noop and "+3.1" in noop)
check("a no-op does not claim to have turned", "TURNED" not in noop)

# A turn that RUNS: 200.0 is 92.2 deg out, so a push is planned; the second
# read lands on target and the loop exits from iteration 1, not 0.
real = st_turn([200.0, 292.2], 292.2)
print(f"  real-turn log: {real!r}")
check("a real turn is NOT reported as a no-op", "NO-OP" not in real)
check("a real turn says it turned, so no-ops can be counted against it",
      "TURNED" in real)

# The other two silent exits. Neither is a no-op and neither may look like one.
blind = st_turn([None], 292.2)
check("an unreadable compass is reported, not silently underturned",
      "compass" in blind and "NO-OP" not in blind)

# max_steps=1 with a heading that never converges: the turn RAN and failed.
spun = st_turn([200.0], 292.2, max_steps=1)
check("a turn that ran to exhaustion says so, and is not a no-op",
      "did not converge" in spun and "NO-OP" not in spun)

# --- walk_steps: the same shape, documented in its own docstring -----------
noop_ws = ws_turn([289.1], 291.0)          # err +1.9, inside 3.5
print(f"  walk_steps no-op log: {noop_ws!r}")
check("walk_steps names a first-iteration no-op", "NO-OP" in noop_ws)
check("walk_steps' no-op line carries its numbers",
      "289.1" in noop_ws and "+1.9" in noop_ws)

real_ws = ws_turn([200.0, 291.0], 291.0)
check("walk_steps does not call a real turn a no-op", "NO-OP" not in real_ws)

spun_ws = ws_turn([200.0], 291.0, max_steps=1)
check("walk_steps reports a turn that ran and did not converge",
      "did NOT converge" in spun_ws and "NO-OP" not in spun_ws)

# --- walk_leg: the per-chunk series, which only the log ever sees ----------
#
# Chunk 1 travels, chunk 2 does not. The caller is handed `best`, which is 100
# either way, so an even walk and one that jammed halfway are identical there.
A = Image.fromarray(np.zeros((32, 32, 3), dtype="uint8"))
B = Image.fromarray(np.full((32, 32, 3), 100, dtype="uint8"))
frames = [A, B, B]


def _capture():
    return frames.pop(0) if len(frames) > 1 else frames[0]


lines = []
real = st.time
st.time = NoSleep
try:
    spent, best, haz = st.walk_leg(0.0, -0.25, 0.5, _capture, lambda: 289.1,
                                   label="a->b step 1/1", log=lines.append,
                                   step_sec=0.25)
finally:
    st.time = real
leg = "\n".join(lines)
print(f"  walk_leg log: {leg!r}")
check("walk_leg logs at all (it accepted `log` and never called it)", bool(leg))
check("walk_leg reports EVERY chunk's travel, not just the best",
      "100.0" in leg and "/0.0" in leg)
check("walk_leg names the leg, so the line can be attributed",
      "a->b step 1/1" in leg)
check("walk_leg still returns what it always returned",
      abs(spent - 0.5) < 1e-6 and abs(best - 100.0) < 1e-6)

# --- unstick: three measurements that used to be thrown away ---------------
#
# `return 0.0` discarded all three, so a failed escape logged NOTHING and was
# indistinguishable from an escape that never ran.
lines = []
real_fw = ws.walk_forward
ws.walk_forward = lambda speed, seconds, strafe=0.0: 0.4
try:
    freed = ws.unstick(0.25, 0.35, log=lines.append)
finally:
    ws.walk_forward = real_fw
stuck = "\n".join(lines)
print(f"  unstick log: {stuck!r}")
check("a failed escape reports all three crabs it actually tried",
      stuck.count("0.4") == 3 and "did NOT free it" in stuck)
check("unstick still returns 0.0 when it fails", freed == 0.0)

# --- run(): the re-aim after crabbing, whose result used to be discarded ---
import atexit
import json
import shutil
import tempfile

_steps_dir = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _steps_dir, ignore_errors=True)
_steps = os.path.join(_steps_dir, "steps.json")
with open(_steps, "w") as fh:
    json.dump([{"bearing": 291.0, "dur": 0.2, "speed": 0.25}], fh)

lines = []
_real = (ws.turn_to, ws.walk_forward, ws.unstick)
ws.turn_to = lambda target, log=print, **kw: 111.0     # re-aim lands nowhere
ws.walk_forward = lambda speed, seconds, strafe=0.0: 0.0        # always stuck
ws.unstick = lambda speed, seconds, log=print: 99.0          # crabbed free
try:
    ws.run(steps_path=_steps, final_cam=None, log=lines.append)
finally:
    ws.turn_to, ws.walk_forward, ws.unstick = _real
reaim = next((l for l in lines if "re-aimed" in l), "")
print(f"  re-aim log: {reaim!r}")
check("the re-aim after crabbing reports where it ended up",
      "291.0" in reaim and "111.0" in reaim)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
