"""I-37: a fan the gate could see (and read_hand could not) stalled TWO live plays.

Live 2026-09-21, 07:50: `overnight/run_live_20260921j.log:844-849` -- hand
`0: UNKNOWN 1: swing_boost +1 2: 5/3 3: 5/2 4: 4/3`, the engine selected slot 2
then slot 1 (attaching the boost to the batter), both verified, and the very
next read stalled: "cannot read the fan after select_card (rows=0) --
refusing". A second live occurrence at 08:00, ONE card lifted, hand
`0: Fielding Play +1 | 1: Pitcher 9/2 LIFTED | 2: Pitcher 7 | 3: Pitcher 9 |
4: Pitcher 6`, same shape: `read_hand` returned 3 rows, none with a measured y.

ROOT CAUSE. `read_hand`'s "is the fan there" gate (the 2026-09-20 COUNT fix,
`tests/minigame/test_two_selected_cards_still_read.py`) counted only
`_strong_discs(img)` -- discs found as an isolated dark digit ringed by white,
at DARK_THRESHOLDS. A SELECTED card's own disc often needs a threshold ABOVE
that range to register at all (it brightens on lift), so it can be entirely
absent from `strong` while sitting, at the right position, in the WHITE-DISC
or WREATH candidates `_read_fan` itself already pools from (`_white_discs`,
`find_tactics`). On the two-lifted fixture below, `_strong_discs` finds 4
candidates and only ONE clears FIT_MAX; `_white_discs` finds the selected
player card's own disc at cost 15.7 (well under FIT_MAX -- a pure vertical
lift is cheap under the `|dx| + |dy|/3` cost, and the white-disc blob's x is
cleaner than a noisy partial digit-in-disc crop), which the gate never saw.

THE FIX. `local_hand._fan_looks_present` pools the SAME candidates
`_read_fan` reads from (strong + white discs + tactics wreaths, deduped via
the existing `_free` bookkeeping), takes the best cost PER SLOT, and gates on
that -- same two constants (FIT_MAX, FIT_MIN_DISCS), nothing invented.
`_read_fan`/`_read_ungated` themselves are untouched.

REGRESSION CHECK (not re-run here, too slow for the suite; see
agent_progress/issues/I-37/probe6_corpus_regression.py): over 2,396 archived
hand crops plus the fixtures below, the broadened gate agrees with the OLD
gate on every frame except 4 -- both fixtures here, and 2 archived corpus
frames whose paid-model "vision" label (never trusted for VALUES, fine for
card COUNT) confirms are genuine five-card fans the old gate dropped. ZERO
frames flip the other way (old admits, new rejects).

Uses the same `check(cond, msg)` shape as
`tests/minigame/test_two_selected_cards_still_read.py` (checked with
`grep -m1 -o "def check(.*)"` before writing this one).
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

from PIL import Image                                                 # noqa: E402

import local_hand as lh                                               # noqa: E402
import orchestrator as orch                                           # noqa: E402

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


TWO_LIFTED = _os.path.join(_ROOT, "test_fixtures", "hand_reads",
                            "i37_two_lifted_20260921.png")
ONE_LIFTED = _os.path.join(_ROOT, "test_fixtures", "hand_reads",
                            "i37_one_lifted_20260921.png")
CONTROL = _os.path.join(_ROOT, "test_fixtures", "hand_cursor",
                         "cursor_on_1.png")

for fp in (TWO_LIFTED, ONE_LIFTED, CONTROL):
    check(_os.path.exists(fp), f"fixture exists: {fp}")
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)


def read(fp):
    full = Image.open(fp)
    hand = dict(orch.crop_gameplay_regions(full))["hand"]
    rows = lh.read_hand(hand)
    scale = hand.width / lh.ANCHOR_W
    sel = lh.selected_cards(rows, scale) if len(rows) == 5 else None
    return rows, sel


# =========================================================================
print("(a) two cards selected (slots 1 tactics, 2 player) -- the 07:50 stall")
# =========================================================================
rows, sel = read(TWO_LIFTED)
check(len(rows) == 5, f"expected a 5-slot fan, got {len(rows)} rows: {rows!r}")
check(all(r.get("y_measured") for r in rows),
      f"every row must have a measured y; got "
      f"{[r.get('y_measured') for r in rows]!r}")
check(sel == [1, 2], f"both selected cards must be seen; got {sel!r}")
check(rows[1].get("kind") == "tactics" and rows[1].get("type") == "swing_boost",
      f"slot 1 must read as the swing_boost tactics card; got {rows[1]!r}")
check(rows[2].get("kind") == "player" and rows[2].get("digit") == "5"
      and rows[2].get("secondary") == 3,
      f"slot 2 must read as the 5/3 player card; got {rows[2]!r}")
check(rows[3].get("digit") == "5" and rows[4].get("digit") == "4",
      f"CONTROL: the two untouched resting cards (3, 4) must still read "
      f"5 and 4; got {rows[3].get('digit')!r}, {rows[4].get('digit')!r}")

# =========================================================================
print("(b) one card selected (slot 1 player) -- the 08:00 stall")
# =========================================================================
rows1, sel1 = read(ONE_LIFTED)
check(len(rows1) == 5, f"expected a 5-slot fan, got {len(rows1)} rows: {rows1!r}")
check(all(r.get("y_measured") for r in rows1),
      f"every row must have a measured y; got "
      f"{[r.get('y_measured') for r in rows1]!r}")
check(sel1 == [1], f"the one selected card must be seen; got {sel1!r}")
check(rows1[1].get("kind") == "player" and rows1[1].get("digit") == "9"
      and rows1[1].get("secondary") == 2,
      f"slot 1 must read as the 9/2 player card; got {rows1[1]!r}")
check(rows1[0].get("kind") == "tactics" and rows1[0].get("type") == "fielding_boost",
      f"slot 0 must read as the Fielding Play tactics card; got {rows1[0]!r}")
check(rows1[3].get("digit") == "9" and rows1[4].get("digit") == "6",
      f"CONTROL: the untouched resting cards (3, 4) must still read 9 and 6; "
      f"got {rows1[3].get('digit')!r}, {rows1[4].get('digit')!r}")

# =========================================================================
print("(c) CONTROL: a normal (no selection) fan is unchanged")
# =========================================================================
_full = Image.open(CONTROL)
_rowsC = lh.read_hand(_full)
check(len(_rowsC) == 5, f"expected a 5-slot fan, got {len(_rowsC)} rows: {_rowsC!r}")
check([r.get("digit") for r in _rowsC] == [None, "6", "9", "5", "5"],
      f"CONTROL: an ordinary fan with no selection must read exactly as before "
      f"(this fixture predates the fix); got {[r.get('digit') for r in _rowsC]!r}")
check(lh.selected_cards(_rowsC, _full.width / lh.ANCHOR_W) == [],
      f"CONTROL: nothing is selected on this fixture; got "
      f"{lh.selected_cards(_rowsC, _full.width / lh.ANCHOR_W)!r}")

# =========================================================================
print("(d) CONTROL: a genuine non-fan is still rejected (not credulous)")
# =========================================================================
_NEG = _os.path.join(_ROOT, "overnight", "local_hand",
                      "hand_1788963163511615000.png")
if _os.path.exists(_NEG):
    _nimg = Image.open(_NEG)
    _nrows = lh.read_hand(_nimg)
    check(all(r.get("_slot_i") is None for r in _nrows),
          f"a frame whose discs land on NO slot must not be read as a fan; got "
          f"_slot_i = {[r.get('_slot_i') for r in _nrows]!r}")
else:
    check(False, f"negative fixture missing: {_NEG}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  two live stalls (one and two cards lifted) both now read a full "
      "5-card fan with every selection visible, an ordinary fan is unchanged, "
      "and a genuine non-fan is still rejected")
