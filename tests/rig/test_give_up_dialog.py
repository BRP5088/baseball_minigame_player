"""OPTIONS opens "Give up?" during a match, not the pause menu.

WHY THIS EXISTS
---------------
reset_environment pressed OPTIONS, saw no pause menu, and raised "the pause
menu will not open and NO input is reaching the game". That was exactly
backwards — the press HAD worked and put the Give up? dialog on screen. Two
runs died on it on 2026-09-01 with a healthy stream and working input, and the
misleading half of the message ("no input is reaching the game") is what sent
the investigation at the input path instead of the screen.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

from PIL import Image

import reset_env

FIX = os.path.join(_ROOT, "test_fixtures", "give_up")
fails = []

CASES = [("give_up_dialog.jpg", True),
         # Both negatives are mid-match-ish screens that must NOT be mistaken
         # for the dialog: answering YES to a phantom Give up? forfeits a paid
         # match.
         ("negative_gameplay_turn.jpg", False),
         ("negative_ban_screen.jpg", False)]

for name, expect in CASES:
    p = os.path.join(FIX, name)
    if not os.path.exists(p):
        fails.append(f"missing fixture {name} — this test must not silently "
                     "skip; a detector test passing on zero frames is how the "
                     "ban counter went untested")
        continue
    got = reset_env.give_up_dialog(Image.open(p))
    if got is not expect:
        fails.append(f"{name}: give_up_dialog returned {got}, expected {expect}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  give_up_dialog: recognises the in-match dialog and is not fooled by "
      f"{len(CASES)-1} other match screens")
