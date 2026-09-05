"""selected_item must name the entry a HUMAN can see is highlighted.

Fixture: a real 1867x1050 window capture where "Load Last Save" is visibly
highlighted (larger, pure white).

WHAT WENT WRONG. WHITE_LEVEL was 200, but unselected menu text peaks at
201-210 — the threshold sat BELOW the population it was discriminating
against. So grey letters counted and the score measured how much TEXT a row
had, not whether it was highlighted:

    level >200:  Resume 0.0003  LoadLast 0.0771  Load 0.0006  Quit 0.1075
    level >225:  Resume 0.0000  LoadLast 0.0586  Load 0.0000  Quit 0.0000

At 200 the long unselected "Quit to Main Menu" won and was returned
CONFIDENTLY. The caller presses cross on that — an unattended run would have
quit the game to the main menu.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
ROOT = _ROOT
sys.path.insert(0, ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import pause_menu as pm

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


FIX = os.path.join(ROOT, "test_fixtures", "pause_menu",
                   "load_last_save_selected.png")

# Must not silently skip: a fixture that vanished is a test that stopped
# testing, and this project has been bitten by exactly that.
if not os.path.exists(FIX):
    print(f"FAIL fixture missing: {FIX}")
    sys.exit(1)

img = Image.open(FIX)

check("the fixture is recognised as a pause screen", pm.is_pause_screen(img))
check("the HIGHLIGHTED entry is named",
      pm.selected_item(img) == "Load Last Save")
check("and specifically NOT the long unselected one",
      pm.selected_item(img) != "Quit to Main Menu")

fr = dict(zip([n for n, _ in pm.menu_items(img)], pm.white_fractions(img)))
check("the selected row scores well above the bar",
      fr["Load Last Save"] >= 2 * pm.SELECTED_MIN_FRAC)
for name in ("Resume", "Load", "Quit to Main Menu"):
    check(f"unselected {name!r} scores essentially zero", fr[name] < 0.005)

# The threshold must sit BETWEEN the two measured populations, not under one.
check("WHITE_LEVEL clears the unselected text's own brightness (peaks 201-210)",
      pm.WHITE_LEVEL > 210)

# A GAMEPLAY frame must never be given a selection. At WHITE_LEVEL 225 one
# still reaches 0.0448 on a row (arrival_bar_jukebox.jpg) against the selected
# entry's 0.0586 — only 1.3x apart, so THE FRACTION THRESHOLD ALONE CANNOT
# SEPARATE THEM.
#
# What actually rejects them, established by mutation rather than assumed:
# NEITHER the is_pause_screen() gate NOR the SELECTED_MARGIN check. Deleting
# both leaves these frames still rejected. The work is done by the
# "exactly one row above the bar" rule — on that frame TWO rows clear it
# (0.0361 and 0.0448), and on the others ZERO do.
#
# So this asserts the OUTCOME, which is what matters, and deliberately claims
# nothing about which guard delivers it.
import glob

gameplay = [f for f in glob.glob(os.path.join(ROOT, "overnight", "phase1", "*.jpg"))]
checked = 0
for f in gameplay:
    g = Image.open(f)
    if pm.is_pause_screen(g):
        continue                     # not a gameplay frame after all
    checked += 1
    check(f"gameplay frame {os.path.basename(f)} is never given a selection",
          pm.selected_item(g) is None)
check("at least one gameplay frame was actually checked", checked > 0)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
