"""level_pitch reports whether the floor stop was CONFIRMED (patch57).

Until patch57 it returned a literal True on every path, so a caller branching
on the result was branching on a constant -- the docstring had already been
corrected to admit that, which left the information (home_pitch's own verdict)
measured and thrown away. This pins the branch that exists now:

  (a) a CONFIRMED home returns True;
  (b) an UNCONFIRMED home returns False -- the `return False` path this file
      exists to keep alive;
  (c) and False is NOT a refusal: every press still happens, in the same order
      and the same count, so the fix changed what is REPORTED and nothing that
      moves. level_pitch is the coarse variant that presses anyway;
      doorway_pitch is the one that refuses.

OFFLINE BY CONSTRUCTION: home_pitch, press and time.sleep are replaced on the
real module for the length of each run, so nothing can reach the console, and
the capture is a stub that is never looked at.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import input_controller as ic          # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (f"  -- {detail}" if detail else ""))
    if not cond:
        ok = False


def run(home_result):
    """One level_pitch() with home_pitch stubbed. Returns (result, presses)."""
    presses = []
    saved = (ic.home_pitch, ic.press)
    try:
        ic.home_pitch = lambda capture, action="look_up", log=None: home_result
        ic.press = lambda name, hold_seconds=0.05, post_delay=None: (
            presses.append((name, hold_seconds, post_delay)), True)[1]
        import time as _time
        slept = _time.sleep
        _time.sleep = lambda s: None
        try:
            return ic.level_pitch(lambda: None), presses
        finally:
            _time.sleep = slept
    finally:
        ic.home_pitch, ic.press = saved


got_true, presses_true = run(home_result=3)
got_false, presses_false = run(home_result=None)

check("(a) a CONFIRMED home returns True", got_true is True, repr(got_true))
check("(b) an UNCONFIRMED home returns False", got_false is False,
      repr(got_false))
check("(b) the two answers differ, so the return is not a constant",
      got_true is not got_false)

# (c) the behaviour is unchanged: the False run presses MORE, never less --
# four recovery look_downs then the same count-up.
ups_true = [p for p in presses_true if p[0] == "look_up"]
ups_false = [p for p in presses_false if p[0] == "look_up"]
downs_false = [p for p in presses_false if p[0] == "look_down"]
check("(c) a confirmed home counts up PITCH_STEPS_FROM_BOTTOM times",
      len(ups_true) == ic.PITCH_STEPS_FROM_BOTTOM,
      f"{len(ups_true)} vs {ic.PITCH_STEPS_FROM_BOTTOM}")
check("(c) a confirmed home presses look_down NOT AT ALL itself",
      [p for p in presses_true if p[0] == "look_down"] == [])
check("(c) an unconfirmed home still counts up the same number of times",
      len(ups_false) == len(ups_true), f"{len(ups_false)} vs {len(ups_true)}")
check("(c) ... after driving firmly to the floor 4 times",
      len(downs_false) == 4, f"{len(downs_false)}")
check("(c) every press uses PITCH_STEP_SEC",
      all(p[1] == ic.PITCH_STEP_SEC for p in presses_true + presses_false))

# ANTI-VACUITY: the stub was consulted at all, and the real one is what ran.
check("(d) the run actually pressed something (the stub was consulted)",
      len(presses_true) > 0 and len(presses_false) > 0)
check("(d) level_pitch is the real module's function",
      ic.level_pitch.__module__ == "input_controller")

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
