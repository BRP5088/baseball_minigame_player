"""KEYMAP must agree with the keys chiaki is ACTUALLY listening for.

Nothing checked this. KEYMAP is a table of what we believe chiaki binds, and
chiaki's own table lives in gui/src/settings.cpp -- two tables that must agree,
with nothing making them. A chiaki update that remaps a button would leave every
press landing on a different control, silently, and the failure would look like
"the console ignored us".

WHAT THIS FOUND THE DAY IT WAS WRITTEN (2026-09-13), by reading the config rather
than pressing anything:

    the running app     chiaki-ng-build/chiaki.app, bundle org.streetpea.chiaking
    its settings        QSettings org "Chiaki" / app "Chiaki"  ->  com.chiaki.Chiaki
    keymap overrides    ZERO. It is running on the compiled-in defaults.
    the profiles        com.chiaki.Chiaki-Taylere holds keymap.left_stick_up = W
                        and its siblings -- but that profile is NOT running, and
                        restart_chiaki.sh launches with no profile argument.

So WASD is bound in a profile nobody is using, and the four walk_* entries in
KEYMAP name keys the running chiaki does not listen for. Those presses post
cleanly through CGEventPostToPid and do nothing -- 10.1's "a success path and a
no-op path with identical output", at the input layer.

IT IS NARROW, and the narrowness is why this file reports rather than fixes.
Production walking goes over the FIFO (slow_traverse -> analog_replay, left_x /
left_y), which is CLAUDE.md section 5's "buttons go to the KEYBOARD, sticks go
over the FIFO" and is unaffected. Only probe.py and reset_walk.py call walk_at.
Changing an input binding that cannot be verified live is how this project gets
a confident wrong diagnosis, so the mismatch is PINNED, not silently corrected:
if it changes in either direction -- someone fixes it, or a new key drifts --
this test fails and says so.
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import input_controller as ic

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


SETTINGS = os.path.join(_ROOT, "chiaki-ng-src", "gui", "src", "settings.cpp")

# FAIL, never skip, when the source tree is absent -- the same rule tests/cpp/
# uses. An unverifiable claim is not a passing one, and this file's whole job is
# to compare against that source.
check(os.path.exists(SETTINGS),
      f"chiaki source present, so KEYMAP can be verified against it ({SETTINGS}). "
      "Absent, this FAILS rather than skipping: an unverifiable claim is not a passing one.")
if not os.path.exists(SETTINGS):
    print("\nFAILED: no chiaki source to compare against")
    sys.exit(1)

QT_KEY_TO_OURS = {
    "Key_Return": "enter", "Key_Backspace": "backspace", "Key_Backslash": "\\",
    "Key_C": "c", "Key_O": "o", "Key_F": "f", "Key_T": "t", "Key_Escape": "esc",
    "Key_Left": "left", "Key_Right": "right", "Key_Up": "up", "Key_Down": "down",
    "Key_1": "1", "Key_2": "2", "Key_3": "3", "Key_4": "4", "Key_5": "5", "Key_6": "6",
    "Key_BracketRight": "]", "Key_BracketLeft": "[",
    "Key_Insert": "insert", "Key_Delete": "delete",
    "Key_Equal": "=", "Key_Minus": "-",
    "Key_PageUp": "pageup", "Key_PageDown": "pagedown",
}

# Our action -> chiaki's button token. Several actions share a button on purpose
# (start_match and confirm_discard are both Square); each is checked.
ACTION_TO_BUTTON = {
    "cross": "CROSS", "select_card": "CROSS",
    "moon": "MOON", "close_result": "MOON",
    "box": "BOX", "confirm_discard": "BOX", "start_match": "BOX",
    "pyramid": "PYRAMID", "confirm_play": "PYRAMID",
    "dpad_left": "DPAD_LEFT", "move_left": "DPAD_LEFT",
    "dpad_right": "DPAD_RIGHT", "move_right": "DPAD_RIGHT",
    "dpad_up": "DPAD_UP", "move_up": "DPAD_UP",
    "dpad_down": "DPAD_DOWN", "move_down": "DPAD_DOWN",
    "l1": "L1", "r1": "R1", "l3": "L3", "r3": "R3",
    "l2": "ANALOG_BUTTON_L2", "r2": "ANALOG_BUTTON_R2",
    "options": "OPTIONS", "toggle_pause": "OPTIONS",
    "share": "SHARE", "touchpad": "TOUCHPAD", "ps_button": "PS",
    "walk_up": "ANALOG_STICK_LEFT_Y_UP", "walk_down": "ANALOG_STICK_LEFT_Y_DOWN",
    "walk_left": "ANALOG_STICK_LEFT_X_DOWN", "walk_right": "ANALOG_STICK_LEFT_X_UP",
    "look_up": "ANALOG_STICK_RIGHT_Y_UP", "look_down": "ANALOG_STICK_RIGHT_Y_DOWN",
    "look_left": "ANALOG_STICK_RIGHT_X_DOWN", "look_right": "ANALOG_STICK_RIGHT_X_UP",
}

raw = open(SETTINGS, encoding="utf-8").read()

# SCOPE IT, AND STRIP COMMENTS. Two failures a mutant proved:
#
#   1. settings.cpp holds TWO 26-entry tables -- GetControllerMapping (the
#      defaults, authoritative) and ClearKeyMapping (removal only). They are
#      byte-identical today, so the right one won purely by file order. A change
#      to one and not the other would be read from whichever came first.
#   2. A commented-out `// {CHIAKI_CONTROLLER_BUTTON_CROSS, Qt::Key_Return},` left
#      above a CHANGED live row was parsed as the live binding and the test PASSED.
#      setdefault takes the first regex hit and the regex has no idea what a
#      comment is.
_start = raw.index("QMap<int, Qt::Key> Settings::GetControllerMapping()")
_end = raw.index("\n}", _start)
src = raw[_start:_end]
check("ClearKeyMapping" not in src,
      "the parsed region reaches into ClearKeyMapping — that table REMOVES bindings "
      "and must never be read as the defaults")
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)      # block comments
src = re.sub(r"//[^\n]*", "", src)                    # line comments
chiaki = {}
for token, qt in re.findall(
        r"(?:CHIAKI_CONTROLLER_(?:BUTTON_|)|ControllerButtonExt::)([A-Z0-9_]+)\)?\s*,"
        r"\s*Qt::Key::(Key_\w+)", src):
    chiaki.setdefault(token, QT_KEY_TO_OURS.get(qt, f"<{qt}>"))

check(len(chiaki) >= 24,
      f"parsed {len(chiaki)} bindings from chiaki's default map (need >= 24) — too few "
      "means the parser drifted from the source format and is checking almost nothing")

# KNOWN MISMATCH, pinned with its evidence. Not a waiver: if the set changes in
# either direction this fails, so a fix and a regression are equally visible.
KNOWN_MISMATCH = {"walk_up", "walk_down", "walk_left", "walk_right"}

agree, disagree, unparsed = [], [], []
for action, button in sorted(ACTION_TO_BUTTON.items()):
    ours = ic.KEYMAP.get(action)
    theirs = chiaki.get(button)
    if theirs is None or theirs.startswith("<"):
        unparsed.append((action, button, theirs))
    elif ours == theirs:
        agree.append(action)
    else:
        disagree.append((action, ours, theirs))

check(not unparsed, f"could not resolve chiaki's binding for {unparsed} — a key name is "
                    "missing from QT_KEY_TO_OURS, so those actions are UNCHECKED")

_bad = {a for a, _o, _t in disagree}
check(_bad == KNOWN_MISMATCH,
      f"KEYMAP/chiaki disagreement changed. now: "
      f"{sorted((a, o, t) for a, o, t in disagree)}; pinned: {sorted(KNOWN_MISMATCH)}. "
      "If a walk_* key was corrected, drop it from KNOWN_MISMATCH. If a NEW action "
      "drifted, every press of it is landing on a different control or on nothing.")

# EVERY KEYMAP ENTRY MUST BE COMPARED. A mutant added `"scroll_ban": "p"` to
# KEYMAP and this file passed: ACTION_TO_BUTTON happened to cover all 36 entries,
# but nothing asserted that it does, so a new action would be silently unchecked --
# and an unchecked action is one whose presses land wherever chiaki decides.
_uncovered = set(ic.KEYMAP) - set(ACTION_TO_BUTTON)
check(not _uncovered,
      f"KEYMAP actions {sorted(_uncovered)} are not in ACTION_TO_BUTTON, so nothing "
      "compares them against chiaki. Add them (with the chiaki button they mean) or "
      "they are unverified.")
_stale = set(ACTION_TO_BUTTON) - set(ic.KEYMAP)
check(not _stale,
      f"ACTION_TO_BUTTON names {sorted(_stale)}, which KEYMAP no longer has — the "
      "table is checking actions that do not exist, which inflates the agree count")

check(len(agree) >= 25,
      f"{len(agree)} actions compared and agree (need >= 25) — fewer means this file is "
      "not checking enough to catch a remap")

print(f"\n  {len(agree)} actions agree with chiaki's compiled-in defaults")
if disagree:
    print("  KNOWN MISMATCH (left stick only; production walking uses the FIFO):")
    for a, o, t in disagree:
        print(f"    {a:12s} KEYMAP {o!r:12s} chiaki default {t!r}")
print("\n" + ("FAILED: " + "; ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)
