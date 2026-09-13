"""press() must announce when it stops using targeted delivery.

_bg_hold_keys() returns False on a dead pid, an unmapped keycode, or a Quartz
raise — all three silently. Execution then falls through to
focus_chiaki_window() + pyautogui, which, per press()'s own comment, "sends to
whatever app is frontmost" and "is capable of typing into the user's work".

Unannounced, a run that had quietly stopped using background injection looked
exactly like one that never needed it — on the path that spends the money, on
the user's work machine.
"""
import io
import os
import os as _os
import sys
import contextlib

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import input_controller as ic

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


class _Fake:
    """Records key events instead of sending them anywhere."""

    def __init__(self):
        self.downs = []

    def keyDown(self, k):
        self.downs.append(k)

    def keyUp(self, k):
        pass


_real = (ic.pyautogui, ic.can_use_background_input, ic._bg_hold_keys,
         ic.focus_chiaki_window, ic.ACTION_DELAY)
fake = _Fake()
ic.pyautogui = fake
# This file drives the focus+pyautogui fallback ON PURPOSE, against the fake above.
# press() refuses that path under BASEBALL_TEST_RUN since 2026-09-13 -- it typed "c"
# into the frontmost window during a mutation run -- so opt in explicitly.
_saved_focus_flag = ic.FOCUS_PRESS_IN_TESTS
ic.FOCUS_PRESS_IN_TESTS = True
ic.focus_chiaki_window = lambda: False
ic.ACTION_DELAY = 0.0

# --- targeted delivery works: silent, and pyautogui is NOT used ------------
ic.can_use_background_input = lambda action=None: True
ic._bg_hold_keys = lambda keys, hold: True
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
check(not fake.downs,
      "pyautogui was used even though background injection succeeded — that "
      "path sends to the frontmost window")
check("FAILED" not in buf.getvalue(),
      f"announced a failure that did not happen: {buf.getvalue()!r}")

# --- injection FAILS: must fall back AND say so ---------------------------
ic._bg_hold_keys = lambda keys, hold: False
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
out = buf.getvalue()
check(fake.downs, "did not fall back to pyautogui when injection failed — the "
                  "press would simply not happen")
check("background injection FAILED" in out,
      f"fell back to the FRONTMOST-window path in silence; stdout was {out!r}. "
      "A run that stopped using targeted delivery must not look identical to "
      "one that never needed it")
check("frontmost" in out.lower(),
      f"the message must say WHERE the keys will go now; got {out!r}")

ic.FOCUS_PRESS_IN_TESTS = _saved_focus_flag
ic.pyautogui, ic.can_use_background_input, ic._bg_hold_keys, \
    ic.focus_chiaki_window, ic.ACTION_DELAY = _real

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  press(): silent when targeted delivery works, and announces the "
      "frontmost-window fallback when it does not")
