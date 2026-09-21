"""I-46: on a RAISED (selected) player card, read_hand's every disc-finding pass could
still land on a small decorative icon (a baseball-seam on PITCHER, a bat on BATTER) that
sits over the top-left of the true power disc, and read_digit correctly refused it
(score under MIN_SCORE 0.80) -- but nothing then tried anywhere else, so the slot read
None on 23 of 287 raised player discs (8.0%), agent_progress/census/raised_disc/.

ROOT CAUSE, measured (agent_progress/issues/I-46/progress.md): the true digit is not a
candidate a SELECTION fix could rescue. On a raised card its ink either never clears any
of DARK_THRESHOLDS/RAISED_DARK_MAX (too bright) or MERGES with the brightened ring into a
blob too big for circle_finder's DIGIT_W/DIGIT_H gates (measured merged blobs 37x34 and
57x59 against a digit's 6-26 x 10-32) -- while the icon, a separate sprite unaffected by
the brightening, stays an isolated blob of exactly digit size and wins every pass. Over
the 23 failing frames: 20 of 22 nearby white-disc extractions land on the SAME icon (within
1-23px) as the circle-finder candidate, and the RAISED_DARK_MAX loop finds no candidate at
all in its own search window on all 23. There is no discarded correct candidate.

THE FIX (local_hand.py, RAISED_SEARCH_* and the loop after the RAISED_DARK_MAX pass in
`_read_fan`): search POSITION directly near the slot anchor, scored ONLY by read_digit's
own MIN_SCORE gate (untouched) -- the same shape DIGIT_RADII already uses to search SCALE.
It runs only where every candidate pass above still leaves a PLAYER slot unread, so it can
add a reading and never change one.

REGRESSION CHECK (not re-run here, too slow for the suite; see
agent_progress/issues/I-46/progress.md): over 2,409 archived hand crops
(overnight/local_hand/ + test_fixtures/hand_reads/), comparing HEAD's local_hand.py
against this fix: digits CHANGED 0, previously-read now None 0, previously None now
read 4 (all "9", scores 0.86-0.95, all confirmed correct by eye). On the 23-frame census
itself, run through the actual production `read_hand()`: 17 of 23 now read, every one
matching the digit legible on agent_progress/census/raised_disc/sheet.jpg by eye. The
remaining 6 sit outside the deliberately narrow, safety-margined search window (a near
duplicate frame's jitter, or one frame where the icon nearly fully covers the digit) and
correctly still abstain rather than guess.

SKEPTIC REVIEW (agent_progress/issues/I-46/skeptic.md): CONFIRMED WITH NOTES. Independently
reproduced the regression check and the 17/23 census result exactly, and found two small
defects, both fixed here: D1, the search wrote `y` but not `x`, so on 3 of 34 real hits
checked offline the row's `x` stayed on the icon the EARLIER pass had picked -- up to 67px
from the digit actually read. D2, a dead `x = r.get("x")` fetch (never used for anything
but its own None-check) removed. Section (a2) below pins D1 with the skeptic's own found
positions, recorded independently of this fix's own output.
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


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


HAND_READS = _os.path.join(_ROOT, "test_fixtures", "hand_reads")

# Five of the 23 I-46 census frames -- full 1920x1080 captures, copied verbatim from
# agent_progress/census/raised_disc/raised_none.json's file list, saved lossless as PNG.
# `expected_x` is the DISC'S OWN position -- read independently (a fixed x/y/radius grid
# search directly through read_digit, not through _read_fan) so this check does not just
# restate whatever the fix's own row happens to say. Recorded once and pinned here; it is
# what D1 (agent_progress/issues/I-46/skeptic.md) exists to keep the row's `x` equal to.
RAISED_FIXTURES = [
    # name                 slot  digit  expected_x (the disc's OWN x, not the icon's)
    ("i46_raised_1.png", 0, "9", 196),   # 20260921_075215_723.jpg, was score 0.384 -> None
    ("i46_raised_2.png", 1, "9", 377),   # 20260921_080552_771.jpg, was score 0.752 -> None
    ("i46_raised_3.png", 2, "5", 556),   # 20260921_080643_981.jpg, was score 0.092 -> None
    ("i46_raised_4.png", 2, "7", 547),   # 20260921_081027_853.jpg, was score 0.256 -> None
    ("i46_raised_5.png", 3, "9", 727),   # 20260921_081048_407.jpg, was score 0.793 -> None
]

for name, _slot, _expected, _expected_x in RAISED_FIXTURES:
    check(f"fixture exists: {name}", _os.path.exists(_os.path.join(HAND_READS, name)))
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)


def read_slot(name, slot):
    full = Image.open(_os.path.join(HAND_READS, name))
    hand = dict(orch.crop_gameplay_regions(full))["hand"]
    rows = lh.read_hand(hand)
    scale = hand.width / lh.ANCHOR_W
    return rows[slot], scale


# =========================================================================
print("(a) five raised slots that read None before the fix now read the digit "
      "legible on the census contact sheet")
# =========================================================================
for name, slot, expected, expected_x in RAISED_FIXTURES:
    row, scale = read_slot(name, slot)
    check(f"{name} slot {slot} reads {expected!r}; got digit={row.get('digit')!r} "
          f"score={row.get('score')!r} row={row!r}",
          row.get("digit") == expected)
    check(f"{name} slot {slot} score clears MIN_SCORE ({lh.MIN_SCORE}); "
          f"got {row.get('score')!r}",
          row.get("score", 0.0) >= lh.MIN_SCORE)
    check(f"{name} slot {slot} is flagged as coming from the new search pass",
          row.get("digit_from_raised_search") is True)

# =========================================================================
print("(a2) D1: row x sits on the DIGIT actually read, not on whatever the icon-based "
      "pass above left behind")
# =========================================================================
# expected_x was recorded independently of this fix (a fixed grid search through
# read_digit directly, not through _read_fan or this row) -- see the RAISED_FIXTURES
# comment. Without D1's `r["x"] = best_xy[0]`, three of these five keep the EARLIER
# pass's x (the icon's), 17-20px off on this fixture set and up to 67px on the fuller
# 34-hit sweep the skeptic checked offline. TOLERANCE IS 10*s, NOT the coordinator's
# 20*s: measured, the three affected fixtures miss by exactly 17-20px, so a 20*s gate
# does not reliably fail on the mutant it exists to catch (one diff lands AT 20,
# passing) -- confirmed by actually running the mutant below at each tolerance before
# choosing this one, not by assuming a looser number was safe.
for name, slot, expected, expected_x in RAISED_FIXTURES:
    row, scale = read_slot(name, slot)
    got_x = row.get("x")
    tol = 10 * scale
    check(f"{name} slot {slot} row x is within {tol:.1f}px of the disc actually read "
          f"(expected {expected_x}); got x={got_x!r}",
          got_x is not None and abs(got_x - expected_x) <= tol)

# =========================================================================
print("(b) CONTROL: a fixture that already read correctly before the fix reads "
      "identically after it -- this pass can only ADD a reading, never change one")
# =========================================================================
CONTROL = _os.path.join(_ROOT, "test_fixtures", "hand_cursor", "cursor_on_1.png")
check(f"control fixture exists: {CONTROL}", _os.path.exists(CONTROL))
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)

_control_img = Image.open(CONTROL)
_control_rows = lh.read_hand(_control_img)
check("CONTROL: still a 5-slot fan; got "
      f"{len(_control_rows)} rows: {_control_rows!r}",
      len(_control_rows) == 5)
_control_digits = [r.get("digit") for r in _control_rows]
check(f"CONTROL: digits unchanged from the pre-fix reading; got {_control_digits!r}",
      _control_digits == [None, "6", "9", "5", "5"])
check("CONTROL: the new pass never fired on this fixture (nothing was missing "
      f"a digit); got flags {[r.get('digit_from_raised_search') for r in _control_rows]!r}",
      all(not r.get("digit_from_raised_search") for r in _control_rows))

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  five census frames that used to abstain on a raised card's digit now read "
      "it correctly, and an ordinary already-reading fan is untouched")
