"""The automation must never take the keyboard away from the user.

WHY THIS IS ITS OWN TEST
------------------------
It went wrong twice on 2026-08-27, both times while the user was working:

  1. focus_chiaki_window() raised the game window because the guard was
     evaluated per call site rather than inside the function.
  2. Disabling background input for the offline suite ALSO disabled that
     guard, so every test that pressed a key raised the window for real.

Both were invisible until a human noticed their window jump. Nothing else in
the suite fails when this breaks, which is exactly why it needs asserting.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)

import os
import subprocess
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
import input_controller as ic

fails = []
REAL_RUN = subprocess.run
REAL_CAN = ic.can_use_background_input
REAL_TEST_RUN = os.environ.pop("BASEBALL_TEST_RUN", None)

raised = []
ic.subprocess = types.SimpleNamespace(
    run=lambda *a, **k: raised.append(a[0] if a else None))

try:
    # 1. targeted delivery available -> the window must stay where it is
    ic.can_use_background_input = lambda action=None: True
    ic._last_focus_at = 0.0
    raised.clear()
    ic.focus_chiaki_window(force=True)
    if raised:
        fails.append("focus_chiaki_window RAISED THE WINDOW while input could "
                     "be delivered without it — this is what pulls the user "
                     "out of their work mid-session")

    # 2. no targeted path -> it must still work, or input reaches nothing
    ic.can_use_background_input = lambda action=None: False
    ic._last_focus_at = 0.0
    raised.clear()
    ic.focus_chiaki_window(force=True)
    if not raised:
        fails.append("with no targeted path available focus_chiaki_window did "
                     "nothing at all — presses would land nowhere")

    # 3. inside the offline suite it must never raise a real window, whatever
    #    can_use_background_input says
    os.environ["BASEBALL_TEST_RUN"] = "1"
    for available in (True, False):
        ic.can_use_background_input = lambda action=None, _a=available: _a
        ic._last_focus_at = 0.0
        raised.clear()
        ic.focus_chiaki_window(force=True)
        if raised:
            fails.append(f"the offline suite raised a real window "
                         f"(background_input={available}) — running tests must "
                         f"never disturb whatever the user is doing")
    os.environ.pop("BASEBALL_TEST_RUN", None)

    # 4. has_focus must not veto presses when focus is irrelevant
    ic.can_use_background_input = lambda action=None: True
    if not ic.has_focus():
        fails.append("has_focus() was False while targeted delivery was "
                     "available — every press would be refused for a reason "
                     "that no longer applies")
finally:
    ic.can_use_background_input = REAL_CAN
    ic.subprocess = subprocess
    subprocess.run = REAL_RUN
    if REAL_TEST_RUN is not None:
        os.environ["BASEBALL_TEST_RUN"] = REAL_TEST_RUN
    else:
        os.environ.pop("BASEBALL_TEST_RUN", None)

if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("  focus is never taken when input can be delivered without it, the "
      "fallback still works when it cannot, and the offline suite cannot raise "
      "a real window either way")
