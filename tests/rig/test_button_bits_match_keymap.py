"""The FIFO bit table and the keyboard KEYMAP must name the SAME button.

WHY THIS EXISTS
---------------
press() has two routes to the console: BUTTON_BITS over the inject FIFO
(preferred) and KEYMAP through chiaki's Qt keyboard (fallback). They are
separate tables for the same actions, so they can disagree — and on 2026-09-01,
the day BUTTON_BITS was added, they did:

    KEYMAP       "confirm_play": "c"  -> Pyramid/Triangle, confirmed live
                                        against the on-screen "PLAY" prompt
    BUTTON_BITS  "confirm_play": 1<<0 -> Cross

Every card play pressed Cross. Nothing was played, the faceoff never flipped,
and wait_for_reveal_cards spent its full 75 seconds per turn concluding "reveal
cards never appeared" — an entire paid match logged zero rows while the hand sat
visibly untouched at five cards. The detector was blamed twice before anyone
looked at the hand.

A wrong bit does not fail loudly. It presses some OTHER button on a live
console, so the only defence is pinning the two tables to each other.
"""
import os
import os as _os
import re
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import input_controller as ic

BIT = {"cross": 1 << 0, "circle": 1 << 1, "square": 1 << 2, "triangle": 1 << 3,
       "dpad_left": 1 << 4, "dpad_right": 1 << 5, "dpad_up": 1 << 6,
       "dpad_down": 1 << 7, "options": 1 << 12}

# The physical button each action means, taken from the KEYMAP comments in
# input_controller.py, which record how each was confirmed.
EXPECTED = {
    "select_card":     "cross",      # "Cross lifts a card"
    "confirm_play":    "triangle",   # on-screen "PLAY" prompt
    "confirm_discard": "square",     # on-screen "DISCARD" prompt
    "start_match":     "square",     # on-screen "Play ($50)" prompt
    "close_result":    "circle",     # on-screen "CLOSE" prompt
    "toggle_pause":    "options",    # Options opens the pause menu
    "move_left":       "dpad_left",
    "move_right":      "dpad_right",
    "move_up":         "dpad_up",
    "move_down":       "dpad_down",
}

fails = []

for action, button in EXPECTED.items():
    got = ic.BUTTON_BITS.get(action)
    want = BIT[button]
    if got != want:
        named = next((n for n, b in BIT.items() if b == got), f"bit {got}")
        fails.append(
            f"{action}: FIFO sends {named}, but KEYMAP documents it as "
            f"{button}. The two input paths would press DIFFERENT buttons for "
            f"the same action, and only one of them can be right.")

# Every action the FIFO can send must also survive the keyboard fallback, or a
# missing FIFO silently loses that action instead of degrading.
for action in ic.BUTTON_BITS:
    if action in EXPECTED and action not in ic.KEYMAP:
        fails.append(f"{action} is in BUTTON_BITS but not KEYMAP — with the "
                     f"FIFO gone it has no fallback at all")

# --- EVERY bit, pinned to chiaki's own enum -------------------------------
# EXPECTED above covers ten ACTION names. It says nothing about the ALIASES —
# "cross", "pyramid", "box", "moon", "dpad_left" and friends — which are what
# brett_walk.press() and every hand-written walk script use. Measured by
# mutation 2026-09-03: setting BUTTON_BITS["pyramid"] to the Cross bit and
# swapping dpad_left with dpad_right was caught by NOTHING in the suite. A
# hand-walk would then have pressed Cross where it asked for Triangle.
#
# The bits are not ours to choose: they are ChiakiControllerButtons in
# chiaki-ng's own header, which is vendored in this repo. Reading it makes this
# a check against the authority instead of against a second hand-copied table,
# and it covers the bits marked "the rest follow the enum's ordering" in
# input_controller.py, which were never fired on the console.
_ENUM_H = os.path.join(_ROOT,
                       "chiaki-ng-src", "lib", "include", "chiaki", "controller.h")

# The physical button each BUTTON_BITS key names, as the enum spells it. Every
# key must appear here — a new entry with no declared meaning is a bit nobody
# has checked, and that is the whole failure this file exists for.
MEANS = {
    "cross": "CROSS", "select_card": "CROSS",
    "moon": "MOON", "close_result": "MOON",
    "box": "BOX", "confirm_discard": "BOX", "start_match": "BOX",
    "pyramid": "PYRAMID", "confirm_play": "PYRAMID",
    "dpad_left": "DPAD_LEFT", "move_left": "DPAD_LEFT",
    "dpad_right": "DPAD_RIGHT", "move_right": "DPAD_RIGHT",
    "dpad_up": "DPAD_UP", "move_up": "DPAD_UP",
    "dpad_down": "DPAD_DOWN", "move_down": "DPAD_DOWN",
    "l1": "L1", "r1": "R1", "l3": "L3", "r3": "R3",
    "options": "OPTIONS", "toggle_pause": "OPTIONS",
    "share": "SHARE", "touchpad": "TOUCHPAD", "ps_button": "PS",
}

# NOT a skip. A missing header means this file checked nothing, and a test that
# quietly checks nothing is how read_ban_counter went uncovered for days while
# reporting a missing fixture.
if not os.path.exists(_ENUM_H):
    print(f"  FAIL: cannot read chiaki's button enum at {_ENUM_H} — the bit "
          f"values then have no authority to be checked against, and this "
          f"file would pass without testing anything")
    sys.exit(1)

ENUM = {}
for line in open(_ENUM_H):
    m = re.search(r"CHIAKI_CONTROLLER_BUTTON_(\w+)\s*=\s*\(1\s*<<\s*(\d+)\)", line)
    if m:
        ENUM[m.group(1)] = 1 << int(m.group(2))
if len(ENUM) < 16:
    fails.append(f"only parsed {len(ENUM)} buttons out of chiaki's enum "
                 f"({_ENUM_H}); the file's shape changed and this check has "
                 f"stopped covering what it claims to")

for action, bit in sorted(ic.BUTTON_BITS.items()):
    button = MEANS.get(action)
    if button is None:
        fails.append(f"{action} is in BUTTON_BITS but no physical button is "
                     f"declared for it here — an unchecked bit presses "
                     f"something nobody has named")
        continue
    want = ENUM.get(button)
    if want is None:
        fails.append(f"{action} claims to be {button}, which is not in "
                     f"chiaki's enum at all")
    elif bit != want:
        named = next((n for n, b in ENUM.items() if b == bit), None)
        fails.append(
            f"{action}: BUTTON_BITS sends {bit} "
            f"({'CHIAKI_CONTROLLER_BUTTON_' + named if named else 'no known button'}), "
            f"but it means {button} = {want} in chiaki's own enum "
            f"({_ENUM_H}). The FIFO would press a different physical button.")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  BUTTON_BITS agrees with KEYMAP on all {len(EXPECTED)} documented "
      f"actions, and all {len(ic.BUTTON_BITS)} entries match chiaki's own "
      f"ChiakiControllerButtons enum")
