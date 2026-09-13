"""NOTHING may reach a real input device while BASEBALL_TEST_RUN is set.

THE CLAIM THIS FILE EXISTS TO STOP BEING A CLAIM. can_use_background_input()'s
docstring said refusing under the flag "means a test run can never move the
character". It did not. It meant a test run could not use the BACKGROUND path,
and each caller then fell through to pyautogui, which types into whatever window
is FRONTMOST. On 2026-09-13 a mutation run of the offline suite sent "c"
(confirm_play/Triangle) into the user's own window with a paid match parked on
the console; the user reported the keystrokes before any log did.

Three separate paths reach the console and EACH needs its own lockout, because a
guard in one protects none of the others:

    input_controller  keyboard   press / hold_combo / walk_at -> pyautogui
                                 press_background            -> CGEventPostToPid
    analog_replay     sticks     send()                      -> the FIFO
    ensure_stream     recovery   _key()                      -> CGEventPostToPid

ensure_stream was found the same evening with NO lockout of any kind, and
resolving its own pid with a loose `pgrep -f chiaki-ng-build` that a /bin/sh
could win. Both halves are fixed; this pins them.

The structural half below is the point: it fails when a NEW emission site
appears anywhere, so the next one is a failing test rather than a keystroke in
someone's editor.
"""
import ast
import os
import sys
import types

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


# ---------------------------------------------------------------- behavioural
import input_controller as ic
import analog_replay as ar

# A pyautogui that RECORDS instead of typing. If any guard is missing, the call
# lands here and the count is non-zero -- which is exactly what the real module
# would have done to the user's frontmost window.
_typed = []
_fake_gui = types.SimpleNamespace(
    keyDown=lambda k: _typed.append(("down", k)),
    keyUp=lambda k: _typed.append(("up", k)),
    press=lambda *a, **k: _typed.append(("press", a)),
    PAUSE=0.0)
_saved_gui, ic.pyautogui = ic.pyautogui, _fake_gui
_saved_focus = ic.FOCUS_PRESS_IN_TESTS
ic.FOCUS_PRESS_IN_TESTS = False          # the shipped default; tests opt IN, never out
try:
    check(ic.can_use_background_input() is False,
          "can_use_background_input() must refuse under the flag (the Quartz path)")
    check(ic.focus_input_allowed("cross") is False,
          "focus_input_allowed() must refuse under the flag (the pyautogui path)")

    _typed.clear()
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
    check(not _typed, f"press() reached the real keyboard under the flag: {_typed}")

    _typed.clear()
    ic.hold_combo(["walk_up", "walk_right"], 0.0)
    check(not _typed, f"hold_combo() reached the real keyboard under the flag: {_typed}")

    _typed.clear()
    _spent = ic.walk_at(20.0, 0.05)      # 20 deg: the BLENDED branch, which had no guard
    check(not _typed, f"walk_at() reached the real keyboard under the flag: {_typed}")
    check(_spent == 0.0,
          f"walk_at() reported {_spent}s travelled while refusing to move — a caller "
          "cannot tell a refused walk from a walked one (10.1)")

    # ...and the control: with the opt-in set, the path is REACHABLE. Without this the
    # four checks above would pass just as well on a press() that did nothing at all.
    ic.FOCUS_PRESS_IN_TESTS = True
    _typed.clear()
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
    check(len(_typed) == 2,
          f"CONTROL: with FOCUS_PRESS_IN_TESTS the keys must still flow, got {_typed} — "
          "if this fails the checks above prove nothing")
    ic.FOCUS_PRESS_IN_TESTS = False
finally:
    ic.pyautogui = _saved_gui
    ic.FOCUS_PRESS_IN_TESTS = _saved_focus

# --- the stick path ---------------------------------------------------------
_opened = []
_saved_open, ar.open_stream = ar.open_stream, lambda *a, **k: _opened.append(1)
try:
    ar.send(["left_y -32767"])
    check(not _opened, "analog_replay.send() opened the FIFO under the flag")
finally:
    ar.open_stream = _saved_open

# --- the recovery path ------------------------------------------------------
# ensure_stream._key does `import Quartz` INSIDE the function, so a fake in
# sys.modules is what it will pick up.
_posted = []
sys.modules["Quartz"] = types.SimpleNamespace(
    CGEventPostToPid=lambda pid, ev: _posted.append(pid),
    CGEventCreateKeyboardEvent=lambda a, b, c: object())
import ensure_stream
ensure_stream._key(12345, 36, after=0.0)
check(not _posted, f"ensure_stream._key() posted a real key event under the flag: {_posted}")

# --- and its pid must come from the resolver that checks IDENTITY ------------
# BEHAVIOURAL, not a source substring. The first version of this check asserted
# "pgrep" was absent from the source and failed on the docstring that EXPLAINS the
# bug -- a source-substring check is how mutants survive on this project. So spawn
# the decoy that actually reproduced it and watch what _pid() picks.
import subprocess as _sp, time as _t
_decoy = _sp.Popen(["/bin/sh", "-c", "sleep 5; : chiaki-ng-build"])
try:
    _t.sleep(0.4)
    _picked = ensure_stream._pid()
finally:
    _decoy.kill()
    _decoy.wait()
check(_picked != _decoy.pid,
      f"ensure_stream._pid() returned {_picked}, a /bin/sh whose argv merely CONTAINS "
      f"'chiaki-ng-build' — _key() posts straight to whatever this returns, so the "
      f"recovery ladder would type into that shell and report that nothing moved")

# ------------------------------------------------------------------ structural
# EVERY emission site, by (module, enclosing function). A new one changes this set
# and fails the test, which is the whole point: the three above were found by
# accident, twice, and the second time it reached the user's keyboard.
EXPECTED = {
    ("input_controller.py", "press"),
    ("input_controller.py", "hold_combo"),
    ("input_controller.py", "walk_at"),
    ("input_controller.py", "_bg_hold_keys"),
    ("input_controller.py", "press_background"),
    ("ensure_stream.py", "_key"),
}
EMITTERS = {"keyDown", "keyUp", "typewrite", "hotkey", "CGEventPostToPid"}


def sites(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = set()
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in EMITTERS):
                out.add((os.path.basename(path), fn.name))
    return out


found = set()
for mod in ("input_controller.py", "analog_replay.py", "ensure_stream.py",
            "walk_steps.py", "slow_traverse.py", "graph_walk.py", "orchestrator.py",
            "reset_env.py", "turn_calibrated.py"):
    p = os.path.join(_ROOT, mod)
    if os.path.exists(p):
        found |= sites(p)

check(found, "the scanner found NO emission sites at all — it is not scanning anything")
_new = found - EXPECTED
_gone = EXPECTED - found
check(not _new,
      f"NEW real-input emission site(s) {sorted(_new)} — add a BASEBALL_TEST_RUN "
      "lockout AND a behavioural check above, then list it in EXPECTED")
check(not _gone,
      f"expected emission site(s) {sorted(_gone)} vanished — if they were removed on "
      "purpose, drop them from EXPECTED; if renamed, the new name is unguarded")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else
              "all three input paths are locked out under BASEBALL_TEST_RUN, "
              "the control proves the path is reachable, and the site census is exact"))
sys.exit(1 if fails else 0)
