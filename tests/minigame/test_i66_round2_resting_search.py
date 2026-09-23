"""I-66 ROUND 2: a SEPARATE, small RESTING-position search, added alongside the
existing RAISED search (unchanged, I-46/I-62), for a player slot whose disc was
never a circle_finder candidate at all AND is not raised.

ROUND 1 (agent_progress/issues/I-66/, on a sibling branch, REFUTED) tried widening
RAISED_SEARCH_DY/DX to also reach the resting row. It was correct on accuracy
(40/40 by eye on the skeptic's 7,688-frame census, 0 wrong) but REFUTED on
runtime: the window went from 12x14=168 grid points to 26x17=442, and median
read_hand() nearly doubled (92 -> 168ms) against the ~150ms live poll budget
(skeptic.md). The skeptic's own census found the fix does not need a wider RAISED
window: all 40 winning positions land within dx -24..+18, dy -12..+9 of the slot
anchor -- a resting-height band, not a raised one.

THIS FIX (local_hand.py, RESTING_SEARCH_DY/DX/COARSE_STEP/FINE_STEP/REFINE_HALF,
_resting_digit_search, _raised_or_resting_search): a second, independent, much
smaller window, tried ONLY when the (unchanged) raised search already failed. It
also does not run read_digit's full DIGIT_RADII sweep (7 correlations) at every
grid point -- a cheap single-radius pass (_cheap_localize_score) first RANKS the
grid to find roughly where the digit is, and only a small box around that point
pays the full, MIN_SCORE-gated read_digit price. Both the window size and the
localize-then-refine shape were required to fit the runtime budget -- see
agent_progress/issues/I-66/progress.md, round 2, for the measurements (a plain
step-3 grid over the same window, all real read_digit calls, still cost +36%
median; this shape costs ~52 full-read_digit-equivalent points and fits).

A resting hit must NOT be reported as a raised/selected card -- its y sits near
the slot anchor (dy -12..+9), far under SELECTED_MIN_RISE (25). The row carries
digit_from_resting_search (not digit_from_raised_search) so a caller -- and
selected_cards() by construction, since it only looks at y -- tells the two apart.
"""
import os as _os
import sys as _sys

_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

from PIL import Image                                                 # noqa: E402

import local_hand as lh                                               # noqa: E402

fails = []


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


FIX = _os.path.join(_ROOT, "test_fixtures", "digit_misses")

# name                                      slot  expected digit   source frame
PRIMARY_FIXTURES = [
    ("i66r2_dropped59149646432_slot3.png", 3, "7"),   # dropped_1789959149646432000
    ("i66r2_dropped29606596089_slot1.png", 1, "7"),   # dropped_1790029606596089000
    ("i66r2_dropped59765279422_slot0.png", 0, "7"),   # dropped_1790059765279422000
    ("i66r2_dropped57496800374_slot3.png", 3, "9"),   # dropped_1790057496800374000
    ("i66r2_dropped56349936104_slot4.png", 4, "6"),   # dropped_1790056349936104000
]

for name, _slot, _expected in PRIMARY_FIXTURES:
    check(f"fixture exists: {name}", _os.path.exists(_os.path.join(FIX, name)))
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)

# =========================================================================
print("(a) five slots recovered ONLY by the new RESTING search (main and the "
      "unchanged RAISED search both leave them None) now read the census's own "
      "winning digit, tagged digit_from_resting_search and NOT SELECTED")
# =========================================================================
for name, slot, expected in PRIMARY_FIXTURES:
    img = Image.open(_os.path.join(FIX, name)).convert("RGB")
    rows = lh.read_hand(img)
    row = rows[slot] if slot < len(rows) else {}
    check(f"{name} slot {slot} reads {expected!r}; got digit={row.get('digit')!r} "
          f"score={row.get('score')!r}",
          row.get("digit") == expected)
    check(f"{name} slot {slot} score clears MIN_SCORE ({lh.MIN_SCORE}); "
          f"got {row.get('score')!r}",
          row.get("score", 0.0) >= lh.MIN_SCORE)
    check(f"{name} slot {slot} is tagged digit_from_resting_search=True; got "
          f"{row.get('digit_from_resting_search')!r}",
          row.get("digit_from_resting_search") is True)
    check(f"{name} slot {slot} is NOT tagged digit_from_raised_search; got "
          f"{row.get('digit_from_raised_search')!r}",
          not row.get("digit_from_raised_search"))
    check(f"{name} slot {slot} is not reported SELECTED (a resting card is not "
          f"raised); selected_cards={lh.selected_cards(rows, img.width / lh.ANCHOR_W)!r}",
          slot not in lh.selected_cards(rows, img.width / lh.ANCHOR_W))

# =========================================================================
print("(b) CONTROL: on the SAME frame as the slot-3 recovery, slots 0/1/2 -- "
      "already read correctly before this change, via other passes -- are "
      "byte-identical after it, and are not tagged as a resting recovery")
# =========================================================================
CONTROL = _os.path.join(FIX, "i66r2_dropped59149646432_slot3.png")
_rows = lh.read_hand(Image.open(CONTROL).convert("RGB"))
check(f"CONTROL: still a 5-slot fan; got {len(_rows)} rows", len(_rows) == 5)
for _i, _expected in ((0, "5"), (1, "5"), (2, "6")):
    check(f"CONTROL slot {_i} reads {_expected!r} unchanged; got "
          f"digit={_rows[_i].get('digit')!r}",
          _rows[_i].get("digit") == _expected)
    check(f"CONTROL slot {_i} is not tagged digit_from_resting_search; got "
          f"{_rows[_i].get('digit_from_resting_search')!r}",
          not _rows[_i].get("digit_from_resting_search"))

# =========================================================================
print("(c) BUDGET: _resting_digit_search spends a bounded, small number of "
      "positions -- guards against widening the window back to round 1's size "
      "(442 points) or dropping the coarse step to 1 (thousands of points), both "
      "refuted on runtime")
# =========================================================================
_cheap_calls = [0]
_full_calls = [0]
_orig_cheap = lh._cheap_localize_score
_orig_full = lh.read_digit


def _counting_cheap(img, cx, cy, r):
    _cheap_calls[0] += 1
    return _orig_cheap(img, cx, cy, r)


def _counting_full(img, circle):
    _full_calls[0] += 1
    return _orig_full(img, circle)


_img = Image.open(CONTROL).convert("RGB")
_s = _img.width / lh.ANCHOR_W
_ax, _ay = lh.SLOT_PLAYER[3][0] * _s, lh.SLOT_PLAYER[3][1] * _s
lh._cheap_localize_score = _counting_cheap
lh.read_digit = _counting_full
try:
    lh._resting_digit_search(_img, _ax, _ay, _s)
finally:
    lh._cheap_localize_score = _orig_cheap
    lh.read_digit = _orig_full

# Measured (agent_progress/issues/I-66/progress.md, round 2): coarse=7/half=2 spends
# 18 cheap-localize calls and up to 25 full read_digit calls on this window. Budget
# generously above that (round 1's widened RAISED window alone was 442 points) so a
# legitimate small tuning tweak does not spuriously fail this test, but FAR below
# what either "widen to round 1's size" or "step=1" would spend.
check(f"cheap-localize calls bounded; got {_cheap_calls[0]}", _cheap_calls[0] <= 60)
check(f"full read_digit (refine) calls bounded; got {_full_calls[0]}",
      _full_calls[0] <= 60)

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  five previously-UNKNOWN resting player digits now read correctly via the "
      "new small window, an already-reading frame's other slots are untouched, and "
      "the search stays within its measured position budget")
