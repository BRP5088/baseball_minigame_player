"""Tie-awareness cannot beat max power, so the engine is right not to model it.

CLAUDE.md called this "a real gap" until it was measured. It is not one, and the
reason is worth keeping because the question looks live: 17.2% of simulated at-bats
are TIES, and the coin is worth 0.30 runs/half of spread.

    tie_w  0.0          1.7903   +0.0000   control: must equal shipped
    tie_w  0.05 .. 10   1.7903   +0.0000   ZERO decisions changed
    tie_w 25.0          1.6588   -0.1315   the first weight that changes anything

A TIE IS A 50% WIN. The only way off a tie at power P is to play P-1 or lower, which
turns a coin flip against those same cards into a certain loss.

WHAT THIS FILE PINS is the arithmetic that makes it true, not the simulation --
20,000-half runs do not belong in a unit suite. POWER_WEIGHT must stay large enough
that no plausible tie term can outvote one point of power. If someone rebalances the
weights, this fails and points at the measurement rather than letting the conclusion
rot silently.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from decision_engine import (POWER_WEIGHT, SPEED_WEIGHT, PlayerCard, TacticsCard,
                             TacticsType, GameState, best_batting_play)

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


# The measured defence distribution (what the pitcher actually shows, since it also
# plays max power). Its PEAK is what a tie term would be multiplied by.
DEF_PEAK = 0.23          # power 7 at 23.0%, measured over 3,000 halves

check(POWER_WEIGHT > DEF_PEAK * 4,
      f"one point of power ({POWER_WEIGHT}) outvotes a tie term at any weight under "
      f"{POWER_WEIGHT / DEF_PEAK:.1f}x the peak tie probability ({DEF_PEAK}) — the "
      "measured sweep found ZERO changed decisions up to tie_w=10")

check(POWER_WEIGHT > SPEED_WEIGHT * 50,
      f"power still dominates speed ({POWER_WEIGHT} vs {SPEED_WEIGHT}), so the 99/1 "
      "split stays a tie-break rather than a trade")

# And the behaviour that follows: a higher-power card is chosen even when its power
# is the single most likely one to be tied.
hand = [PlayerCard("common", 7, 1),      # 7 is the defence's MOST likely power
        PlayerCard("rarer", 6, 3)]       # 6 is less likely to be tied
state = GameState(half="batting", batters_used=0, your_score=0, opp_score=0)
d = best_batting_play(hand, [], state)
check(d.player_card.power == 7,
      f"the engine plays the 7 even though 7 is the most-tied power "
      f"(chose {d.player_card.power}) — dropping to 6 to dodge a tie turns a coin "
      "flip into a certain loss against every 7")

# CONTROL: it is not simply always picking the first card.
d2 = best_batting_play([PlayerCard("low", 5, 3), PlayerCard("high", 9, 1)], [], state)
check(d2.player_card.power == 9,
      f"CONTROL: it still maximises power when the order is reversed "
      f"(chose {d2.player_card.power})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
