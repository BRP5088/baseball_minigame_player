"""aim_doorway_pitch: home to the floor stop, then EXACTLY 22 look_up presses,
and refuse to press at all when the floor stop was not confirmed.

WHY THIS EXISTS. STAIRS_APPROACH.md (2026-09-06) measured the one pitch that
makes leg 2 work: home DOWN to the floor stop, then 22 presses UP. The project
already holds two other pitch numbers that contradict it (PITCH_STEPS_FROM_BOTTOM
= 14 and level_pitch's "4 positions"), and level_pitch presses on ANYWAY when
the home is not confirmed, merely reporting it (patch57). So the things worth
pinning are the ones a plausible edit would silently break:

  (a) the ORDER (home first, then count) and the COUNT (22, as a literal --
      CLAUDE.md 10.11: never assert against the constant being guarded);
  (b) that a failed home is a REFUSAL with zero presses, not level_pitch's
      "press down some more and count anyway" -- 22 from an unknown pitch is
      an unmeasured pose;
  (c) that the fake was actually consulted, so (a) and (b) cannot pass
      vacuously against a function that does nothing.

OFFLINE BY CONSTRUCTION. A fake input_controller is installed in sys.modules
BEFORE doorway_pitch is imported, recording every call. The real module
imports pyautogui at its top, so "pyautogui never loaded" is direct evidence
the real one was never touched -- no console input is possible from here.
"""
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (f"  -- {detail}" if detail else ""))
    if not cond:
        ok = False


# --- the fake, installed BEFORE the import ---------------------------------
class FakeInput:
    def __init__(self):
        self.calls = []          # every call, in order, as tuples
        self.home_result = 3     # what home_pitch "returns"

    def home_pitch(self, capture, action="look_up", log=None):
        self.calls.append(("home_pitch", action, capture))
        return self.home_result

    def press(self, action, hold_seconds=0.05, post_delay=None):
        self.calls.append(("press", action, hold_seconds, post_delay))


fake = FakeInput()
ic = types.ModuleType("input_controller")
# Distinctive on purpose (the real value is 0.05): proves the code READS the
# press length from input_controller rather than hard-coding its own copy.
ic.PITCH_STEP_SEC = 0.07
ic.home_pitch = fake.home_pitch
ic.press = fake.press
sys.modules["input_controller"] = ic

import doorway_pitch  # noqa: E402  (must follow the fake)

SENTINEL_CAPTURE = object()


def run(home_result, log_sink):
    fake.calls.clear()
    fake.home_result = home_result
    return doorway_pitch.aim_doorway_pitch(
        SENTINEL_CAPTURE,
        log=(log_sink.append if log_sink is not None else None))


def presses(calls):
    return [c for c in calls if c[0] == "press"]


# --- (a) homing succeeds: home first, then exactly 22 look_up presses -------
log_a = []
got_a = run(home_result=5, log_sink=log_a)
pa = presses(fake.calls)
check("(a) returns True when homing settled", got_a is True, f"got {got_a!r}")
check("(a) the FIRST call is home_pitch, before any press",
      len(fake.calls) > 0 and fake.calls[0][0] == "home_pitch",
      f"first call {fake.calls[:1]}")
check("(a) home_pitch homes DOWN (\"look_down\"), the only detectable stop",
      len(fake.calls) > 0 and fake.calls[0][:2] == ("home_pitch", "look_down"),
      f"{fake.calls[:1]}")
check("(a) home_pitch is handed the caller's capture, untouched",
      len(fake.calls) > 0 and fake.calls[0][2] is SENTINEL_CAPTURE)
check("(a) home_pitch is called exactly once",
      sum(1 for c in fake.calls if c[0] == "home_pitch") == 1)
# THE LITERAL 22, not doorway_pitch.DOORWAY_PRESSES_FROM_FLOOR (10.11).
check("(a) exactly 22 presses follow -- the STAIRS_APPROACH.md count",
      len(pa) == 22, f"{len(pa)} presses")
check("(a) every press is look_up (counting UP from the floor stop)",
      len(pa) > 0 and all(c[1] == "look_up" for c in pa),
      f"actions {sorted(set(c[1] for c in pa))}")
check("(a) every press holds for input_controller.PITCH_STEP_SEC, read live",
      len(pa) > 0 and all(c[2] == 0.07 for c in pa),
      f"holds {sorted(set(c[2] for c in pa))}")
check("(a) every press uses level_pitch's look_up post_delay of 0.30",
      len(pa) > 0 and all(c[3] == 0.30 for c in pa),
      f"post_delays {sorted(set(c[3] for c in pa))}")
check("(a) the success path says what it did (10.1: no silent success)",
      any("22" in line for line in log_a), f"log {log_a}")
check("the constant itself records the measured 22",
      doorway_pitch.DOORWAY_PRESSES_FROM_FLOOR == 22)

# --- (b) homing returns None: refuse, press nothing, say why ----------------
log_b = []
got_b = run(home_result=None, log_sink=log_b)
pb = presses(fake.calls)
check("(b) returns False when home_pitch returned None", got_b is False,
      f"got {got_b!r}")
check("(b) ZERO presses -- 22 from an unknown pitch is an unmeasured pose",
      len(pb) == 0, f"{len(pb)} presses")
check("(b) it still TRIED to home (the refusal is home_pitch's verdict)",
      any(c[0] == "home_pitch" for c in fake.calls))
check("(b) the refusal is logged and names the cause",
      any("REFUSING" in line and "home_pitch" in line for line in log_b),
      f"log {log_b}")
# The refusal must not itself crash when there is nowhere to log -- a guard
# that raises instead of returning False is a guard that cannot fire.
try:
    got_b_quiet = run(home_result=None, log_sink=None)
    check("(b) with log=None it still returns False without raising",
          got_b_quiet is False and len(presses(fake.calls)) == 0)
except Exception as exc:  # noqa: BLE001
    check("(b) with log=None it still returns False without raising", False,
          f"raised {exc!r}")

# --- (c) anti-vacuity: the fake was consulted, the real module never loaded --
check("(c) the fake input_controller recorded calls (it was consulted)",
      len(fake.calls) > 0)
check("(c) doorway_pitch resolved input_controller to THIS fake",
      sys.modules.get("input_controller") is ic)
check("(c) pyautogui never loaded, so the real input_controller never ran",
      "pyautogui" not in sys.modules)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
