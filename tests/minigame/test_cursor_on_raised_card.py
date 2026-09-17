"""A CURSOR ON A *RAISED* CARD READS HALF WHAT cursor_slot's CENSUS CLAIMS.

Ground truth for this frame comes from the user watching the live screen on
2026-09-17: the cursor is on SLOT 4, and slot 4 is RAISED (selected).

cursor_slot's docstring reports a census over 74 labelled frames:

    the card with the cursor     20.7 .. 36.1
    every other card              0.0 ..  8.4    (selected but not hovered: <= 5.7)

This frame's cursor reads about 10.9 -- LESS THAN HALF that lower bound, and a
whisker over CURSOR_GLOW_MIN. It is a true cursor by ground truth, so the 20.7
floor does not describe every cursor: those 74 frames appear to hold none where
the cursor sits on a card that is ALSO SELECTED, and the docstring states the band
as though it were the whole population (CLAUDE.md 10.31).

THE GUARD THAT MATTERS is the last one: raising the gate toward the census band
would reject a real cursor on every selected card, and the selection path REFUSES
when the cursor cannot be read -- which is how a live turn became unplayable twice
on the evening this frame was taken. The headroom is under one point.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image
import orchestrator as o
import local_hand as lh

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


FIX = os.path.join(_ROOT, "test_fixtures", "cursor_on_raised_card",
                   "cursor_slot4_raised.png")
check(os.path.exists(FIX), "the ground-truth frame is committed")

hand = dict(o.crop_gameplay_regions(Image.open(FIX)))["hand"]
rows = lh.read_hand(hand)
scale = hand.width / lh.ANCHOR_W
# cursor_glow returns (best_index, glow, rows); the middle one is the per-slot band.
_best, glow, _rows = lh.cursor_glow(hand, rows)

# GROUND TRUTH, from the user, on this exact frame.
check(lh.selected_cards(rows, scale) == [4],
      f"slot 4 is RAISED, as the user reported -> {lh.selected_cards(rows, scale)}")
check(lh.cursor_slot(glow, None) == 4,
      f"and the cursor is read as slot 4 -> {lh.cursor_slot(glow, None)} (glow={glow})")

# THE MARGIN, PINNED AS A LITERAL (10.11). This is the whole finding.
top = max(glow)
check(10.0 < top < 14.0,
      f"the true cursor reads {top} -- marginal, not the census's 20.7..36.1")
check(top < 20.7,
      f"...and BELOW that census floor ({top} < 20.7), so the census does not "
      "cover a cursor on a selected card")

# THE GUARD. Anyone raising the gate toward the census band breaks this frame, and
# with it every turn where the engine's own card is selected under the cursor.
check(lh.CURSOR_GLOW_MIN == 10.0,
      f"CURSOR_GLOW_MIN is 10.0, not {lh.CURSOR_GLOW_MIN}")
check(lh.CURSOR_GLOW_MIN < top,
      f"the gate ({lh.CURSOR_GLOW_MIN}) still admits this real cursor ({top}) -- "
      f"headroom {round(top - lh.CURSOR_GLOW_MIN, 1)}")

# AND THE COVERED SLOT IS GENUINELY UNREADABLE, so the two are not confused: a
# stranded batter's card lies over slot 2 in this same frame.
check(rows[2].get("digit") is None,
      f"slot 2 is covered by the stranded batter and does not read -> {rows[2].get('digit')}")
check(glow[2] < lh.CURSOR_GLOW_MIN,
      f"...and its glow ({glow[2]}) is the banner, not a halo")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
