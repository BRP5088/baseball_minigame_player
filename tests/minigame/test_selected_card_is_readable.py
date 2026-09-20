"""A SELECTED card must read its power AND report itself selected.

A card BRIGHTENS when the game selects it, so the dark-threshold circle fit
shrinks and find_circles loses the disc's dark edge. Measured live 2026-09-20 in
a paid match, on a selected slot 0, over 25 STATIC frames:

    disc found at the shipped ladder (110, 90, 130)   0 / 25
    disc found at RAISED_DARK_MAX = 150              25 / 25
    darkest pixel in a 40px box, selected disc       113
    darkest pixel, resting discs                     31 and 34

_read_fan already carried an escalation for exactly this. IT COULD NOT FIRE. Its
gate asked whether the row was ALREADY raised, using row["y"] -- and when the disc
is the thing that was missed, that y is the SHIELD's, about 66 px BELOW the anchor.
So the apparent rise was NEGATIVE against a 25 px gate and the pass was skipped in
precisely the state it existed for:

    row y = 261 (shield)   apparent rise -66   -> escalation skipped
    true disc y = 154      true rise     +41   -> would have run

The visible cost was on the MONEY PATH. selected_cards() reported "nothing
selected" on 17 of those 25 frames while the card was plainly lifted on screen, so
select_and_play() could not verify its own selection and returned True on a play
the game never accepted.

THE FIXTURE IS A LIVE FRAME, and it had to be: every hand in overnight/local_hand
is a RESTING fan, so no archived frame contains a selected card and no census taken
from that corpus could have found this.
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

from PIL import Image                                            # noqa: E402
import local_hand                                                # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


FIX = _os.path.join(_ROOT, "test_fixtures", "selected_card",
                    "slot0_selected_979.png")

# A MISSING FIXTURE IS A FAILURE, NOT A SKIP. This file guards a money-path reader;
# exiting 0 because the frame is absent is the "silent skip" CLAUDE.md records as
# worse than no test.
check(_os.path.exists(FIX), f"fixture missing: {FIX}")
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)

img = Image.open(FIX)
scale = img.width / local_hand.ANCHOR_W
rows = local_hand.read_hand(img)

check(img.width == int(local_hand.ANCHOR_W),
      f"the fixture must be at ANCHOR_W ({local_hand.ANCHOR_W}); got {img.width} -- "
      "a different width silently rescales every raw-pixel gate in this reader")
check(len(rows) == 5, f"expected a 5-slot fan, got {len(rows)} rows")

# --- the digit on the SELECTED card ------------------------------------------
check(rows[0].get("digit") == "5",
      f"slot 0 is SELECTED and its power disc reads '5' by eye; the reader said "
      f"{rows[0].get('digit')!r} (score {rows[0].get('score')}). Before the raised "
      "pass was repaired this was None on 25 of 25 live frames.")

# --- and the row's y must MEAN the disc ---------------------------------------
# selected_cards compares y against the DISC anchor, so a y taken from the shield
# is not a worse answer, it is a different question answered confidently.
check(rows[0].get("y_from") == "disc",
      f"slot 0's y must be disc-derived for selected_cards to be comparing like "
      f"with like; got y_from={rows[0].get('y_from')!r} y={rows[0].get('y')!r}")
_anchor = local_hand.SLOT_PLAYER[0][1] * scale
check(_anchor - rows[0].get("y", _anchor) >= local_hand.SELECTED_MIN_RISE * scale,
      f"slot 0's disc sits at y={rows[0].get('y')} against anchor {_anchor}: a rise "
      f"of {_anchor - (rows[0].get('y') or _anchor):.0f}px, under the "
      f"{local_hand.SELECTED_MIN_RISE * scale:.0f}px gate")

# --- the headline behaviour ---------------------------------------------------
sel = local_hand.selected_cards(rows, scale)
check(sel == [0],
      f"selected_cards must report slot 0 selected; got {sel!r}. This is what "
      "select_and_play needs to verify a selection actually took -- it returned "
      "True on a play the game never accepted because this said 'nothing selected'.")

# --- CONTROL: the reader has not simply become credulous ----------------------
# Without this, every check above is satisfied by a reader that calls everything
# selected and every disc a 5.
check(rows[1].get("digit") == "4" and rows[4].get("digit") == "4",
      f"CONTROL: the two RESTING batters must still read '4'; got "
      f"{rows[1].get('digit')!r} and {rows[4].get('digit')!r} -- if this fails the "
      "checks above prove nothing about selection specifically")
check(1 not in sel and 4 not in sel,
      f"CONTROL: the resting slots must NOT be reported selected; got {sel!r}")
check(rows[2].get("digit") is None,
      f"CONTROL: slot 2 is occluded by the home-plate runner and must stay "
      f"UNREAD rather than be guessed; got {rows[2].get('digit')!r}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a selected card reads its power, reports itself selected, and the resting "
      "slots are unaffected")
