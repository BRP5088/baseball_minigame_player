"""Backing off must stop when it is measurably not working.

Live 2026-09-01: six backoffs took ACTION_DELAY 0.25 -> 0.65, every input ran
2.6x slower for the rest of the session, and the misfire rate did not change.
The reveal reader was at fault (it returned power 0 for a card the roster puts
at 5), and no amount of settling time fixes a misread.

input_controller's own comment predicted this — "the signal is noisy in exactly
the direction that would ratchet the delay up forever on a vision problem that
more waiting cannot fix" — but the only escape was the 0.8s ceiling.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import input_controller as ic

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def _reset():
    ic._misfires_seen = 0
    ic._backoffs_applied = 0
    ic._backoff_abandoned = False
    ic._backoff_applied = 0.0
    ic.ACTION_DELAY = ic.DEFAULT_ACTION_DELAY
    ic.FOCUS_TTL = 3.0


# --- it still backs off at first: a real dropped keystroke must be absorbed --
_reset()
ic.report_misfire()                      # #1 is below the floor, no change
check(ic.ACTION_DELAY == ic.DEFAULT_ACTION_DELAY,
      f"one misfire changed the delay to {ic.ACTION_DELAY}; the floor is "
      f"{ic.MISFIRES_BEFORE_BACKOFF} because the signal is noisy")
ic.report_misfire()                      # #2 jumps to the known-safe value
check(ic.ACTION_DELAY == ic.BACKOFF_SAFE_DELAY,
      f"second misfire left the delay at {ic.ACTION_DELAY}, expected "
      f"{ic.BACKOFF_SAFE_DELAY} — a genuine input problem must still be fixed")

# --- but it gives up once the evidence says waiting is not the remedy -------
for _ in range(ic.BACKOFF_INEFFECTIVE_AFTER):
    ic.report_misfire()
check(ic._backoff_abandoned,
      f"after {ic.BACKOFF_INEFFECTIVE_AFTER} ineffective backoffs it is still "
      "raising the delay — that is the ratchet the module warns about")
check(ic.ACTION_DELAY == ic.DEFAULT_ACTION_DELAY,
      f"gave up but left ACTION_DELAY at {ic.ACTION_DELAY}; the slowness was "
      f"measured to buy nothing, so it must be handed back")

# --- and it stays given up, rather than ratcheting again --------------------
before = ic.ACTION_DELAY
for _ in range(5):
    check(ic.report_misfire() is False, "an abandoned backoff must not re-arm")
check(ic.ACTION_DELAY == before,
      f"delay drifted to {ic.ACTION_DELAY} after giving up")

_reset()

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  backoff: still absorbs a real dropped keystroke, but abandons and "
      "refunds the delay once backing off is measurably not working")
