"""Buttons must NOT be claimed by the FIFO path.

Measured on the live console 2026-09-03: `buttons 4096` (options) did nothing
after 4s, while the keyboard path opened the pause menu in 0.5s. The FIFO bit
values were never confirmed.

The bug this guards is not "buttons go to the wrong place" — it is that
_inject_press returned True because WRITING to the pipe succeeded, so press()
believed the button had been pressed and never fell through to the path that
works. Every button in the system was silently dead: resets, menu navigation,
card selection, match play.
"""
import os
import os as _os
import sys
import tempfile

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

# THE FIFO GOES TO A SCRATCH FILE, BEFORE ANY IMPORT.
# This file deliberately clears BASEBALL_TEST_RUN and then CALLS the injection
# path, so the only thing standing between it and the live console is the
# FakeAR stub in sys.modules. That is protection by statement ORDER: measured
# 2026-09-03, moving the stub below the calls sent 'right_x 26214' straight at
# /tmp/chiaki_input — a real camera swing on a parked console. Redirecting the
# transport here makes the safety structural instead of positional, the same
# way tests/test_injected_input.py does it.
# PID-SUFFIXED — see test_analog_replay.py.
_SINK = os.path.join(tempfile.gettempdir(),
                     f"baseball_buttons_fifo_sink_{os.getpid()}.txt")
os.environ["CHIAKI_INJECT_INPUT"] = _SINK
try:
    os.remove(_SINK)
except FileNotFoundError:
    pass

_os.environ.setdefault("BASEBALL_TEST_RUN", "1")   # the suite exports it; this file
# manipulates the flag itself below, so it must start from the same state standalone.
import input_controller as ic

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


sent = []


class FakeAR:
    @staticmethod
    def send(lines):
        sent.append(list(lines))

    @staticmethod
    def to_axis(v):
        return int(v * 32767)


sys.modules["analog_replay"] = FakeAR

# The test lockout sits ABOVE everything, so clear it to exercise the routing.
had = os.environ.pop("BASEBALL_TEST_RUN", None)
try:
    check("INJECT_BUTTONS is off", ic.INJECT_BUTTONS is False)

    for action in ("toggle_pause", "cross", "select_card", "confirm_play",
                   "move_left", "move_right", "start_match"):
        if action not in ic.BUTTON_BITS:
            continue
        sent.clear()
        took = ic._inject_press(action, 0.05)
        check(f"{action!r} is NOT claimed by the FIFO", took is False)
        check(f"{action!r} writes nothing to the FIFO", sent == [])

    # Sticks must still go over the FIFO — every walk depends on it.
    stick = next(iter(ic.STICK_AXES), None)
    if stick:
        sent.clear()
        took = ic._inject_press(stick, 0.05)
        check(f"stick {stick!r} IS still sent over the FIFO", took is True)
        check(f"stick {stick!r} actually wrote to the FIFO", sent != [])
finally:
    if had is not None:
        os.environ["BASEBALL_TEST_RUN"] = had

# Nothing may have reached the real transport. The stub above should have taken
# every write; if it ever does not, this says so instead of the console moving.
_leaked = open(_SINK).read() if os.path.exists(_SINK) else ""
check("nothing reached the real FIFO transport", _leaked == "")
if _leaked:
    print(f"  leaked: {_leaked!r}")

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
