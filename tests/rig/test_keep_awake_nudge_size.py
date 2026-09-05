"""The nudge must be BIG ENOUGH TO EXIST, and it must undo itself.

WHY THIS EXISTS
---------------
keep_awake shipped with

    NUDGE_MAG = 0.35   # above turn_curve.DEAD_BELOW (0.35) so it registers
    NUDGE_MS  = 90     # brief: ~7 degrees at this magnitude, undone at once

and BOTH comments were false. `0.35 > 0.35` is False, so the magnitude sat ON
the boundary turn_curve calls dead rather than above it, and rate_for(0.35) is
4.55 deg/s, so 90ms bought 0.41 DEGREES — not the ~7 claimed, out by 17x.

That is the diagnosis catalogue's #1 shape in the one module whose whole job is
to stop the console sleeping: a sub-degree deflection may well be nothing, and
the module would log "nudged at HH:MM:SS" every four minutes either way. The
failure it guards against has already killed one overnight run and contaminated
one A/B, and both times the harness read a frozen picture as a routing failure.

So this file pins the arithmetic to turn_curve, so a constant cannot drift away
from the curve it claims to come from without something failing. It pins the
LITERALS as well as the relationships (a test that asserts NUDGE_MAG >
tc.DEAD_BELOW passes forever if someone lowers DEAD_BELOW).

WHAT IT DELIBERATELY DOES NOT TEST: whether the PS5 counts any of this as
activity. That is the console's idle timer, it cannot be reached offline, and
it has never been measured live at any magnitude. See keep_awake's own notes for
the live test and, crucially, for the control arm it needs.
"""
import os
import os as _os
import sys
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

SENT = []
fake = types.ModuleType("analog_replay")
fake.send = lambda lines: SENT.append(list(lines))
fake.to_axis = lambda v: max(-32768, min(32767, int(round(v * 32767))))
sys.modules["analog_replay"] = fake

import keep_awake as ka
import turn_curve as tc

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------------------
# 1. THE LITERALS. Pinned, not derived — the whole defect was a number that
#    stopped matching its own justification while everything still ran.
# ---------------------------------------------------------------------------
check("NUDGE_MAG is 0.60", ka.NUDGE_MAG == 0.60)
check("NUDGE_MS is 300", ka.NUDGE_MS == 300)

# The two turn_curve constants the choice rests on. Pinned here as well, so
# lowering DEAD_BELOW cannot silently rescue a magnitude that stopped clearing
# it — the relationship checks below would otherwise pass forever.
check("turn_curve.DEAD_BELOW is still 0.35", tc.DEAD_BELOW == 0.35)
check("turn_curve.USABLE_MAX is still 0.90", tc.USABLE_MAX == 0.90)

# ---------------------------------------------------------------------------
# 2. THE EXACT BUG. Strictly above the dead zone, not merely equal to it.
#    `0.35 > 0.35` was False and the comment said otherwise.
# ---------------------------------------------------------------------------
check("the magnitude is STRICTLY above the dead zone",
      ka.NUDGE_MAG > 0.35)
check("...and strictly above it by the module's own constant too",
      ka.NUDGE_MAG > tc.DEAD_BELOW)
check("the magnitude stays inside the usable band (repeatability collapses "
      "above it)", ka.NUDGE_MAG <= 0.90)

# ---------------------------------------------------------------------------
# 3. THE ARITHMETIC. turn_curve.MEASURED entries are AVERAGE RATES OVER A 0.30s
#    HOLD, so rate x duration is a reading at 0.30s and an extrapolation
#    anywhere else. Holding for exactly 0.30s is what makes NUDGE_DEG honest.
# ---------------------------------------------------------------------------
check("the hold is the 0.30s the curve was measured at",
      ka.NUDGE_MS / 1000.0 == 0.30)
check("NUDGE_DEG is 6.75 degrees", abs(ka.NUDGE_DEG - 6.75) < 1e-9)
check("NUDGE_DEG is DERIVED from the curve, not typed in",
      abs(ka.NUDGE_DEG
          - tc.rate_for(ka.NUDGE_MAG) * (ka.NUDGE_MS / 1000.0)) < 1e-9)

# The old pair, kept as a regression witness. If anyone ever puts 0.35/90ms
# back believing the old comment, this states in one line what it buys.
check("the OLD constants really did produce under one degree",
      tc.rate_for(0.35) * 0.090 < 1.0)
check("~7 deg in 90ms would have needed the top of the band",
      tc.mag_for(7.0 / 0.090) >= 0.90)

# ---------------------------------------------------------------------------
# 4. SELF-UNDOING. This fires unattended every four minutes; a nudge that goes
#    out and does not come back leaves the camera rotated, which corrupts
#    exactly the runs the module exists to protect.
# ---------------------------------------------------------------------------
def axes(field="right_x"):
    return [float(l.split()[1]) for lines in SENT for l in lines
            if l.startswith(field + " ")]


had = os.environ.pop("BASEBALL_TEST_RUN")
real_time = ka.time
try:
    quiet = types.SimpleNamespace(sleep=lambda s: None,
                                  strftime=real_time.strftime)
    ka.time = quiet

    SENT.clear()
    ka.nudge(log=lambda *a: None)
    flat = [l for lines in SENT for l in lines]
    moved = [v for v in axes("right_x") if v != 0]
    check("the nudge is equal and opposite",
          len(moved) == 2 and moved[0] + moved[1] == 0)
    check("it nets to zero on the axis it moves", sum(axes("right_x")) == 0)
    check("it never tilts the camera vertically",
          all(v == 0 for v in axes("right_y")))
    check("it never touches the left stick — position cannot drift",
          not any(l.startswith("left_") for l in flat))
    check("every hold is timed, so chiaki releases it on its own clock",
          all(len(l.split()) == 3 for l in flat if l.startswith("right_")))
    check("it releases at the end", flat[-1] == "clear")

    # THE CASE THE HAPPY PATH CANNOT SHOW: the reverse must survive the process
    # being interrupted mid-nudge. Before this it lived on the happy path, so a
    # Ctrl-C or a killed session between the halves left the camera turned.
    SENT.clear()
    boom = types.SimpleNamespace(
        sleep=lambda s: (_ for _ in ()).throw(KeyboardInterrupt()),
        strftime=real_time.strftime)
    ka.time = boom
    try:
        ka.nudge(log=lambda *a: None)
    except KeyboardInterrupt:
        pass
    check("interrupted mid-nudge, the reverse is STILL sent",
          sum(axes("right_x")) == 0 and len([v for v in axes("right_x") if v]) == 2)
    check("...and the stick is still released",
          any("clear" in lines for lines in SENT))

    # THE INVERSE, which is why this is a flag and not a bare `finally`: if the
    # OUTWARD half never went out, nothing was applied, and "undoing" it would
    # rotate the camera the other way — turning a failed poke into a real
    # disturbance of an idle rig.
    SENT.clear()
    ka.time = quiet
    calls = {"n": 0}

    def fail_first(lines):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("FIFO gone")
        SENT.append(list(lines))

    real_send = fake.send
    try:
        fake.send = fail_first
        try:
            ka.nudge(log=lambda *a: None)
        except OSError:
            pass
    finally:
        fake.send = real_send
    check("a poke that never went out is NOT 'undone' into a real turn",
          not [v for v in axes("right_x") if v != 0])
finally:
    ka.time = real_time
    os.environ["BASEBALL_TEST_RUN"] = had

# ---------------------------------------------------------------------------
# 5. THE LOG MUST STATE THE SIZE. "nudged at 04:12:01" reads identically
#    whether the camera moved 6.8 degrees or 0.41 of one. That is how the old
#    constants stayed wrong through every overnight log they appeared in.
# ---------------------------------------------------------------------------
lines = []
real_busy, real_nudge, real_time = (ka.something_else_is_running, ka.nudge,
                                    ka.time)
try:
    ka.something_else_is_running = lambda: False
    ka.nudge = lambda log=print: True

    class _Stop(Exception):
        pass

    def stop(_s):
        raise _Stop()

    ka.time = types.SimpleNamespace(sleep=stop, strftime=real_time.strftime)
    try:
        ka.main(interval=0.0, log=lines.append)
    except _Stop:
        pass
    check("the log says how far it turned, not just that it turned",
          any("6.75" in l for l in lines))
finally:
    ka.something_else_is_running, ka.nudge, ka.time = (real_busy, real_nudge,
                                                       real_time)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
