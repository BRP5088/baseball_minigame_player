"""Two selected cards must not blind the hand reader.

THE ENGINE SELECTS TWO CARDS ON EVERY PLAY THAT ATTACHES A TACTICS CARD -- a
player plus a boost -- so this is the normal case, not an edge one.

A SELECTED card is displaced about 22-26 px HORIZONTALLY as well as lifted, so its
distance from its slot anchor clears FIT_MAX on its own. read_hand used to gate the
fan on the MEDIAN of those distances, which decides the whole frame from one
number: with ONE card selected the median still lands on a resting disc and the fan
is accepted, but with TWO selected it lands on a displaced one and the fan is
REJECTED. Measured live 2026-09-20 on a real hand with slots 0 and 1 up:

    residuals   26.3 (selected)   22.3 (selected)   12.7   0.0
    median      22.3   against FIT_MAX 20.0   -> fan rejected

read_hand then falls through to _read_ungated, whose rows carry NO slot identity
and NO y. selected_cards and cursor_slot therefore both answer nothing -- the
reader goes completely blind at exactly the moment the loop needs to verify a
two-card play. Live, every glow read 0.0 and every y None while the cards were
plainly on screen.

THE GATE ASKS THE WRONG QUESTION. Its job is "is the fan THERE", not "is every card
at rest". Counting the discs that land on a slot answers it and reuses the two
constants already fitted for the purpose, so nothing is invented. Measured over 540
archived hand crops: 459 accepted by both rules, 8 rejected by both, ZERO that the
count rule rejects and the median accepts, and exactly ONE newly admitted --
hand_1788969878714664000.png, a fully visible five-card fan (POWER SWING +2,
BATTER 7/1, SPEED BOOST +1, BATTER 5/2, BATTER 4/3) that the median was dropping.

THE FIXTURE IS A LIVE FRAME, and had to be: the whole 540-hand archive holds only
three frames with two cards selected, none at this pair of slots. Its ground truth
was confirmed by the user watching the screen -- "slot 0 and 1 are selected, slot 1
has the cursor" -- and the reader now reports exactly that.
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

from PIL import Image                                                # noqa: E402

import local_hand as lh                                              # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


FIX = _os.path.join(_ROOT, "test_fixtures", "selected_card",
                    "two_selected_slots01_979.png")

# A MISSING FIXTURE IS A FAILURE, NOT A SKIP -- this guards the reader the $50
# play path verifies itself with.
check(_os.path.exists(FIX), f"fixture missing: {FIX}")
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)

img = Image.open(FIX)
scale = img.width / lh.ANCHOR_W
rows = lh.read_hand(img)

check(img.width == int(lh.ANCHOR_W),
      f"the fixture must be at ANCHOR_W ({lh.ANCHOR_W}); got {img.width}")

# --- the fan must be RECOGNISED, not dropped to the ungated path -------------
# _read_ungated returns kind 'unknown' and _slot_i None. That is the blindness:
# without slot identity nothing downstream can name a card or a selection.
check(len(rows) == 5, f"expected a 5-slot fan, got {len(rows)} rows")
check([r.get("_slot_i") for r in rows] == [0, 1, 2, 3, 4],
      f"the fan fit was rejected and read_hand fell through to the UNGATED path: "
      f"_slot_i = {[r.get('_slot_i') for r in rows]!r}. Rows without slot identity "
      "are why selected_cards and cursor_slot both went blind live.")
check(all(r.get("kind") != "unknown" for r in rows),
      f"ungated rows report kind 'unknown': {[r.get('kind') for r in rows]!r}")

# --- and BOTH selections must be visible -------------------------------------
sel = lh.selected_cards(rows, scale)
check(sel == [0, 1],
      f"both selected cards must be seen; got {sel!r}. The engine selects two on "
      "every play that attaches a tactics card, so this is the normal case.")

# --- CONTROL: it has not simply become credulous ------------------------------
# Without this, the check above passes just as well on a reader that calls every
# slot selected.
check(2 not in sel and 3 not in sel and 4 not in sel,
      f"CONTROL: the three resting slots must NOT be reported selected; got {sel!r}")
check([r.get("digit") for r in rows[:4]] == ["6", "1", "6", "6"],
      f"CONTROL: the four readable cards must still read 6/1/6/6; got "
      f"{[r.get('digit') for r in rows[:4]]!r} -- if this fails the reader is not "
      "reading this fan, and the selection check above means nothing")

# --- the median rule would fail this frame, which is the point ---------------
_s = img.width / lh.ANCHOR_W
_res = sorted(lh._slot(c[0], c[1], _s)[0] / _s for c in lh._strong_discs(img))
check(_res[len(_res) // 2] > lh.FIT_MAX,
      f"this fixture no longer reproduces the defect: its median residual is "
      f"{_res[len(_res)//2]:.1f}, within FIT_MAX {lh.FIT_MAX}, so it would pass "
      "under the OLD rule too and pins nothing.")
check(sum(1 for r in _res if r <= lh.FIT_MAX) >= lh.FIT_MIN_DISCS,
      f"residuals {[round(r,1) for r in _res]}: fewer than FIT_MIN_DISCS "
      f"({lh.FIT_MIN_DISCS}) discs land within FIT_MAX, so the count rule could "
      "not have admitted this frame either")

# --- NEGATIVE CONTROL: a frame that is NOT a fan must still be REJECTED -------
# Without this the whole file passes on a gate that accepts everything, which
# would hand _read_fan frames it cannot place and put slot identity back on
# garbage. This frame's three discs sit 26-28 px from every anchor -- no disc
# lands on a slot, so neither rule admits it, and read_hand must fall to the
# ungated path.
_NEG = _os.path.join(_ROOT, "overnight", "local_hand",
                     "hand_1788963163511615000.png")
if _os.path.exists(_NEG):
    _nimg = Image.open(_NEG)
    _ns = _nimg.width / lh.ANCHOR_W
    _nres = sorted(lh._slot(c[0], c[1], _ns)[0] / _ns
                   for c in lh._strong_discs(_nimg))
    check(sum(1 for r in _nres if r <= lh.FIT_MAX) < lh.FIT_MIN_DISCS,
          f"the negative fixture no longer reproduces a non-fan: residuals "
          f"{[round(r,1) for r in _nres]} put at least {lh.FIT_MIN_DISCS} discs "
          "on slots, so it cannot pin a rejection")
    _nrows = lh.read_hand(_nimg)
    check(all(r.get("_slot_i") is None for r in _nrows),
          f"a frame whose discs land on NO slot must not be read as a fan; got "
          f"_slot_i = {[r.get('_slot_i') for r in _nrows]!r}. A gate that accepts "
          "everything gives slot identity to garbage.")
else:
    check(False, f"negative fixture missing: {_NEG}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a hand with TWO cards selected still reads as a fan, both selections are "
      "visible, and a non-fan is still rejected")
