"""A runner stranded on HOME PLATE is counted as a sixth card in the hand.

His card lies inside the hand crop (which starts at y 0.716) carrying its own
BATTER banner, power disc and shield, so read_hand finds those discs and counts
it. `_look_settled` requires EXACTLY five rows, so a fifth of every read is
rejected -- measured over 76 live frames, 60 read five rows and 16 read six or
seven -- and the shifted indices produced every input failure of the evening:
a lost cursor, five "select_card did not land" retries, a phantom "raised [4]",
and a selection state that flickered every two seconds on a still screen.

Blanking the stranded card's column takes the row count to 76/76 with IDENTICAL
digits, so only the COUNT was ever unstable.

AND NO DISCARD CAN REVEAL THE COVERED SLOT. The occluder is a runner on the
diamond, not a hand card, so CLAUDE.md 10.34's "discard the occluder" does not
apply. should_redraw therefore abstains: max() over the slots that SURVIVED is not
the hand's maximum, and measured live the hidden slot WAS the best card -- an 8
against a threshold of 6, with a discard spent on a hand that was never weak.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import glob
from PIL import Image
import orchestrator as o
from decision_engine import GameState, PlayerCard, should_redraw

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


FIX = sorted(glob.glob(os.path.join(_ROOT, "test_fixtures", "homeplate_runner", "hr_*.jpg")))
check(len(FIX) >= 10, f"the stranded-runner frames are committed ({len(FIX)})")

# 1. THE DETECTOR fires on every one of them.
hit = 0
for p in FIX:
    crops = dict(o.crop_gameplay_regions(Image.open(p)))
    if o.homeplate_runner_present(crops):
        hit += 1
check(hit == len(FIX), f"a card on home plate is detected on {hit}/{len(FIX)} frames")

# 2. THE ROW COUNT. Without the flag a fifth of these frames read six or seven rows
# and local_hand_cards cannot return a hand at all; with it, every frame parses.
import local_hand as lh
bad_raw = sum(1 for p in FIX
              if len(lh.read_hand(dict(o.crop_gameplay_regions(Image.open(p)))["hand"])) != 5)
bad_fixed = 0
for p in FIX:
    hand = dict(o.crop_gameplay_regions(Image.open(p)))["hand"]
    if len(lh.read_hand(o._blank_homeplate_strip(hand))) != 5:
        bad_fixed += 1
check(bad_raw > 0, f"WITHOUT the fix, {bad_raw} of {len(FIX)} frames read the wrong row count")
check(bad_fixed == 0, f"WITH it, {bad_fixed} do -- every frame parses as five rows")

# 3. should_redraw ABSTAINS when a slot is hidden, however weak the visible cards are.
weak = [PlayerCard(None, 4, 3), PlayerCard(None, 4, 1), PlayerCard(None, 5, 2)]
hidden = GameState(half="batting", batters_used=0, your_score=0, opp_score=0,
                   redraws_left=2, hidden_by_homeplate_runner=True)
seen = GameState(half="batting", batters_used=0, your_score=0, opp_score=0,
                 redraws_left=2)
check(should_redraw(weak, hidden) is False,
      "a hand with a slot hidden by a home-plate runner does NOT redraw")
check(should_redraw(weak, seen) is True,
      "CONTROL: the same weak cards with nothing hidden DO redraw -- so the "
      "abstention above is the flag, not the cards")

# 4. And a STRONG hand is unaffected either way, so the flag cannot cause a discard.
strong = [PlayerCard(None, 9, 2)]
check(should_redraw(strong, hidden) is False and should_redraw(strong, seen) is False,
      "a strong hand never redraws, flag or no flag")

# 5. THE DEFAULT IS OFF, so every existing caller behaves exactly as before.
check(GameState(half="batting", batters_used=0, your_score=0,
                opp_score=0).hidden_by_homeplate_runner is False,
      "the flag defaults to False -- existing callers are untouched")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
