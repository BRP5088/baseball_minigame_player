"""THE POWER/SPEED BLEND: power decides, speed only breaks an exact tie.

WHY 99/1 AND NOT SOMETHING ELSE. Swept 2026-09-10 over every whole percent from 100/0 to
0/100 -- 101 ratios x 5 seeds x 2000 matches = 1,010,000 simulated matches -- in a model that
finally implements speed, tie coin-flips and runners advancing on outs:

    pure POWER  100/0    37.95%      plateau 100/0 .. 61/39, all indistinguishable
    BEST         99/1    38.12%      +0.17 points over pure power, 0.4 sigma: NOT significant
    first drop   60/40   36.05%      >2 sigma below pure power
    pure SPEED   0/100    6.69%

So 99/1 is not a trade, it is a FREE TIE-BREAK: powers are integers, one point of power is
0.99, and the widest speed gap available is about 0.06. Power wins every comparison it can.

WHAT THIS FILE GUARDS
  1. the weights are LITERALS (CLAUDE.md 10.11)
  2. one point of power beats ANY speed advantage -- the property that makes 99/1 safe
  3. speed does break an exact power tie -- otherwise the wiring is dead and 99/1 is a lie
  4. only swing/pitch boosts add power; a speed boost must not inflate it
  5. the ratio stays inside the measured plateau
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"

import decision_engine as de
from decision_engine import (PlayerCard, TacticsCard, TacticsType, GameState,
                             best_batting_play, power_bonus)

fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def state(runners=()):
    return GameState(half="batting", batters_used=0, your_score=0, opp_score=0,
                     runners=list(runners), redraws_left=2)


# --- 1. literals -----------------------------------------------------------------------
check(de.POWER_WEIGHT == 0.99, "POWER_WEIGHT is the literal 0.99")
check(de.SPEED_WEIGHT == 0.01, "SPEED_WEIGHT is the literal 0.01")

# --- 2. one point of power beats any speed edge -----------------------------------------
# This is the property that makes the ratio safe. MAX_SPEED is deliberately generous: even a
# speed far beyond anything in the real collection must not outweigh a single power point.
MAX_SPEED = 20
for spd in (1, 3, 9, MAX_SPEED):
    d = best_batting_play([PlayerCard("slow", 7, 0), PlayerCard("fast", 6, spd)], [], state())
    check(d.player_card.name == "slow",
          f"power 7/speed 0 beats power 6/speed {spd} -- one power point outweighs any speed")

# --- 3. ...but speed DOES break an exact tie ---------------------------------------------
d = best_batting_play([PlayerCard("slow", 7, 0), PlayerCard("fast", 7, 1)], [], state())
check(d.player_card.name == "fast",
      "on EQUAL power the faster card is taken -- otherwise the speed wiring is dead")

# --- 4. only swing/pitch boosts add power ------------------------------------------------
check(power_bonus(TacticsCard("sw", TacticsType.SWING_BOOST, 3)) == 3, "a swing boost adds power")
check(power_bonus(TacticsCard("pi", TacticsType.PITCH_BOOST, 2)) == 2, "a pitch boost adds power")
check(power_bonus(TacticsCard("sp", TacticsType.SPEED_BOOST, 3)) == 0, "a SPEED boost adds NO power")
check(power_bonus(TacticsCard("fi", TacticsType.FIELDING_BOOST, 2)) == 0, "a FIELDING boost adds NO power")
check(power_bonus(None) == 0, "no tactics card adds no power")

# a big speed boost must never be chosen over a smaller swing boost
d = best_batting_play([PlayerCard("a", 7, 1)],
                      [TacticsCard("sw", TacticsType.SWING_BOOST, 1),
                       TacticsCard("sp", TacticsType.SPEED_BOOST, 3)], state())
check(d.tactics_card.kind == TacticsType.SWING_BOOST,
      "swing +1 is taken over speed +3 -- a point of power beats three of speed")

# ...but a speed boost IS taken when nothing else is on offer: it is free.
d = best_batting_play([PlayerCard("a", 7, 1)],
                      [TacticsCard("sp", TacticsType.SPEED_BOOST, 2)], state())
check(d.tactics_card is not None and d.tactics_card.kind == TacticsType.SPEED_BOOST,
      "with only a speed boost available it is attached rather than wasted")

# --- 5. the ratio sits inside the measured plateau ---------------------------------------
# The sweep put the plateau at 0..39% speed weight and the first significant drop at 40%.
ratio = de.SPEED_WEIGHT / (de.POWER_WEIGHT + de.SPEED_WEIGHT)
check(ratio < 0.39,
      f"the speed share is {100*ratio:.0f}%, inside the measured plateau (drops at 40%)")

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
