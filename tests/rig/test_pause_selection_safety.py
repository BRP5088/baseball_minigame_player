"""selected_item must never confidently name the WRONG menu entry.

Measured 2026-09-03 on a real frame where "Load Last Save" was visibly
highlighted:

    Resume             0.0003
    Load Last Save     0.0771   <- actually selected, BELOW the 0.1 bar
    Load               0.0006
    Quit to Main Menu  0.1075   <- was returned, ABOVE the bar

The score is a white FRACTION, so it rises with how much text a row contains: a
long unselected entry beat a short selected one. Exactly one row cleared the
bar, so the function returned a confident wrong answer, and the caller commits a
`cross` on it — an unattended run would have quit to the main menu.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import pause_menu as pm

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


ITEMS = [("Resume", None), ("Load Last Save", None), ("Load", None),
         ("Quit to Main Menu", None)]


def verdict(fracs):
    real_items, real_fracs, real_pause = pm.menu_items, pm.white_fractions, pm.is_pause_screen
    try:
        pm.menu_items = lambda img: ITEMS
        pm.white_fractions = lambda img: fracs
        pm.is_pause_screen = lambda img: True
        return pm.selected_item(object())
    finally:
        pm.menu_items, pm.white_fractions, pm.is_pause_screen = (
            real_items, real_fracs, real_pause)


# The exact measured failure. Must NOT name Quit to Main Menu.
got = verdict([0.0003, 0.0771, 0.0006, 0.1075])
check("the measured ambiguous frame is refused, not answered",
      got != "Quit to Main Menu")
check("and specifically abstains", got is None)

# A genuine, unambiguous highlight must still be named.
check("a clear highlight is still named",
      verdict([0.0003, 0.0006, 0.0004, 0.4000]) == "Quit to Main Menu")
check("a clear highlight on a short entry is still named",
      verdict([0.5000, 0.0006, 0.0004, 0.0100]) == "Resume")

# Nothing selected, or several, still abstains.
check("nothing above the bar abstains", verdict([0.0, 0.0, 0.0, 0.0]) is None)
check("two entries above the bar abstains",
      verdict([0.4, 0.0, 0.0, 0.4]) is None)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
