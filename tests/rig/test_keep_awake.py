"""keep_awake must never move the character, and must stand down during a run."""
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
fake.to_axis = lambda v: int(v * 32767)
sys.modules["analog_replay"] = fake

import keep_awake as ka

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# Hard off under the test flag, like every other input path here.
SENT.clear()
check("does nothing under BASEBALL_TEST_RUN", ka.nudge(log=lambda *a: None) is False)
check("and sent nothing", SENT == [])

had = os.environ.pop("BASEBALL_TEST_RUN")
try:
    SENT.clear()
    ka.nudge(log=lambda *a: None)
    flat = [l for lines in SENT for l in lines]
    check("it nudges the camera (right stick)",
          any(l.startswith("right_x ") and not l.startswith("right_x 0") for l in flat))
    check("it NEVER touches the left stick — the character must not move",
          not any(l.startswith("left_x") or l.startswith("left_y") for l in flat))

    xs = [float(l.split()[1]) for l in flat if l.startswith("right_x ")]
    moved = [v for v in xs if v != 0]
    check("the nudge is self-cancelling (equal and opposite)",
          len(moved) == 2 and abs(moved[0] + moved[1]) < 1e-6)
    check("every hold carries a duration so chiaki releases it",
          all(len(l.split()) == 3 for l in flat if l.startswith("right_")))
    check("it releases at the end", flat[-1] == "clear")
finally:
    os.environ["BASEBALL_TEST_RUN"] = had

# Stands down when a real run owns the console.
real = ka.subprocess.run
try:
    ka.subprocess.run = lambda *a, **k: types.SimpleNamespace(
        stdout="999 python /x/ab_leg_tolerance.py\n")
    check("stands down while an A/B is running", ka.something_else_is_running())
    ka.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout="999 python /x/unrelated.py\n")
    check("pokes when nothing project-related is running",
          not ka.something_else_is_running())
    def boom(*a, **k):
        raise OSError("pgrep gone")
    ka.subprocess.run = boom
    check("if it cannot tell, it stays QUIET rather than interfering",
          ka.something_else_is_running())
finally:
    ka.subprocess.run = real

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
