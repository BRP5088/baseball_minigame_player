"""is_pause_screen must not fire on a blown-out white wall.

MEASURED 2026-09-03 — a gameplay frame with the character facing a bright wall:

    gameplay bright wall   page 0.927   dark menu text 0.0000
    real pause menu        page 0.944   dark menu text 0.0465

page_fraction alone cannot separate those, so is_pause_screen returned True on
open world. reset_environment then waited for the menu, tried to read the
selection, got nothing, and aborted — the root cause of five consecutive
ResetErrors that invalidated half of that day's streak run.
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


FIX = os.path.join(ROOT, "test_fixtures", "pause_menu")
wall = os.path.join(FIX, "gameplay_bright_wall.png")
book = os.path.join(FIX, "load_last_save_selected.png")

for f in (wall, book):
    if not os.path.exists(f):
        print(f"FAIL fixture missing: {f}")
        sys.exit(1)

w, b = Image.open(wall), Image.open(book)

check("a blown-out wall is NOT a pause screen", not pm.is_pause_screen(w))
check("the real pause book still IS one", pm.is_pause_screen(b))

# The discriminator must be the TEXT, not the brightness — brightness alone
# cannot separate them and that is the whole point.
check("brightness alone does NOT separate them (so it cannot be the test)",
      abs(pm.page_fraction(w) - pm.page_fraction(b)) < 0.05)
check("dark menu text DOES separate them",
      pm.menu_text_fraction(b) > 5 * max(pm.menu_text_fraction(w), 1e-6))
check("the threshold sits between the two measured classes",
      pm.menu_text_fraction(w) < pm.MENU_TEXT_MIN_FRAC < pm.menu_text_fraction(b))

# And nothing downstream may name a selection on the wall.
check("no selection is offered for the wall", pm.selected_item(w) is None)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
