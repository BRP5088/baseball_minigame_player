"""The FIFO transport itself — to_axis, send, clear.

WHY THIS EXISTS
---------------
Every other test in this suite FAKES analog_replay (test_injected_input and
test_brett_walk both install a stub module), which is right — nothing offline
should open the real pipe. The side effect measured 2026-09-03 is that the real
module had NO coverage at all: removing the clamp from to_axis entirely was
caught by nothing, and neither was anything about the line format the C++
listener parses.

That matters because this is the last thing between a computed float and a
DualSense axis. `chiaki-patch/injectinput.cpp` reads each line with
`sscanf("%31s %ld %ld")` into an int16 field, so a value outside int16 is not a
big number — it is a wrapped one, and a wrapped stick points the character
somewhere it was never told to go, with no position feedback anywhere in the
path to notice.

Nothing here touches the real FIFO: analog_replay.FIFO is repointed at a scratch
file first, and the pipe at /tmp/chiaki_input is never opened.
"""
import os
import os as _os
import sys
import tempfile

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import analog_replay as ar

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# --- to_axis: the int16 wire range, pinned to the PROTOCOL, not to AXIS_MAX --
# These are the limits of the field injectinput.cpp writes (`clamp16`), so they
# are facts about the wire format rather than a tunable. Asserting
# `to_axis(v) <= ar.AXIS_MAX` instead would rise with the constant it is
# supposed to guard and pass forever.
check(ar.to_axis(0.0) == 0, f"to_axis(0.0) = {ar.to_axis(0.0)}, expected 0")
check(ar.to_axis(1.0) == 32767,
      f"to_axis(1.0) = {ar.to_axis(1.0)}, expected full positive deflection 32767")
check(ar.to_axis(0.54) == 17694,
      f"to_axis(0.54) = {ar.to_axis(0.54)}; the recorded walk's median stick "
      "magnitude is documented as 17694 in this module's own header")

# OUT OF RANGE MUST CLAMP, NOT WRAP. A caller computing a magnitude from a
# measurement lands outside -1..1 sooner or later — brett_walk.camera() has a
# whole warning about x=10 — and 10.0 unclamped is 327670, which does not fit
# the int16 the listener stores it in.
for v, want in ((1.5, 32767), (10.0, 32767), (1e9, 32767),
                (-1.5, -32768), (-10.0, -32768), (-1e9, -32768)):
    got = ar.to_axis(v)
    check(got == want,
          f"to_axis({v}) = {got}, expected it clamped to {want}. Outside "
          "int16 this is not a large value, it is a wrapped one.")

for v in [x / 40.0 for x in range(-120, 121)]:
    got = ar.to_axis(v)
    check(-32768 <= got <= 32767,
          f"to_axis({v}) = {got}, outside the int16 range the FIFO field holds")
    check(isinstance(got, int), f"to_axis({v}) returned {type(got).__name__}, "
                                "and a float would not parse as %ld")

# --- send(): one field per LINE, and flushed -------------------------------
# The listener is `while(fgets(...)) Apply(buf)`, so a batch that arrives
# without newlines is one unparseable line, and a batch that sits in a Python
# buffer arrives late — which is exactly the "follows the right path but does
# not travel far enough" failure open_stream() was written to fix.
# PID-SUFFIXED. test_no_side_effects.py re-runs every test file, so two copies
# of this one run concurrently — and this file asserts EXACT file content then
# os.removes the sink in `finally`. A fixed path lets copy A truncate or delete
# between copy B's send() and its read: a flake in the ONLY coverage of the real
# FIFO transport, which would get retried away rather than diagnosed.
sink = os.path.join(tempfile.gettempdir(),
                    f"baseball_test_analog_replay_{os.getpid()}.txt")
_real_fifo = ar.FIFO
ar.FIFO = sink
ar.close_stream()
# THE FLAG MUST BE CLEARED HERE. analog_replay.send() gained its own
# BASEBALL_TEST_RUN lockout on 2026-09-04 (15+ call sites reach it without
# going through input_controller, so a guard living only there covered none of
# them). This file exists to test the REAL transport, so it has to opt out —
# pointed at a plain file, not the live FIFO. Restored in the `finally`.
_had_flag = os.environ.pop("BASEBALL_TEST_RUN", None)
try:
    ar.send(["left_x 17694", "left_y -8000"])
    # read BEFORE anything is closed: an unflushed write is a late write
    with open(sink) as fh:
        got = fh.read()
    check(got == "left_x 17694\nleft_y -8000\n",
          f"send() wrote {got!r}; each field must be its own newline-terminated "
          "line, written through to the pipe rather than left in a buffer")

    # The optional THIRD field (hold in ms) added 2026-09-03 must survive
    # unchanged — the listener reads it with the same sscanf.
    ar.close_stream()
    ar.send(["right_x 32767 400"])
    with open(sink) as fh:
        got = fh.read()
    check(got == "right_x 32767 400\n",
          f"send() wrote {got!r}; a timed hold is 'axis value ms' on one line")

    # --- clear(): releases AND closes -------------------------------------
    # reopen so the sink holds only what clear() writes (a regular file is
    # truncated on open; the real FIFO is a stream and appends)
    ar.close_stream()
    ar.clear()
    with open(sink) as fh:
        got = fh.read()
    check(got == "clear\n", f"clear() wrote {got!r}, expected 'clear'")
    check(ar._fh is None,
          "clear() left the FIFO handle open. chiaki recreates the pipe on "
          "restart, so a held handle points at an unlinked inode and every "
          "later write succeeds into nothing.")
finally:
    if _had_flag is not None:
        os.environ["BASEBALL_TEST_RUN"] = _had_flag
    ar.close_stream()
    ar.FIFO = _real_fifo
    try:
        os.remove(sink)
    except OSError:
        pass

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  analog_replay: to_axis clamps to the int16 wire range, send() writes "
      "one line per field and it is readable without closing (timed holds "
      "included), clear() releases and closes")
