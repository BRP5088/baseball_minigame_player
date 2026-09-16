"""
Baseball Card Mini-Game (Mouse: P.I. for Hire) - Decision Engine
==================================================================
Given the current hand and game state, decides the best Play or
Discard action for a turn.

Important honesty note: card selection each round is simultaneous
and blind — you commit to a card before seeing the opponent's. That
means there's no "solved" optimal policy without knowing the full
distribution of cards in the opponent's deck. What follows is a
heuristic strategy engine built from the game's stated rules and
community tips, not a game-theoretic optimum. It should play solidly
above-average, and the heuristics are cheap to retune once you see
how it performs over real games.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class TacticsType(Enum):
    SWING_BOOST = "swing_boost"        # batting: adds to swing power
    SPEED_BOOST = "speed_boost"        # batting: adds to speed rating
    PITCH_BOOST = "pitch_boost"        # pitching: adds to pitch focus
    FIELDING_BOOST = "fielding_boost"  # pitching: adds to fielding rating


@dataclass
class PlayerCard:
    """A Batter or Pitcher card."""
    name: str
    power: int          # swing power (batter) or pitch focus (pitcher)
    secondary: int = 0  # speed (batter) or fielding (pitcher); 0 if absent
    role: str = ""      # "batter" | "pitcher" | "" when not yet read off the card
    # ROLE IS NOT COSMETIC, AND ITS ABSENCE WAS A BUG. `secondary` means two different
    # stats and only `role` says which, so code that treats a pool of cards as
    # interchangeable reads a pitcher's FIELDING as a batter's SPEED. The user, 2026-09-13:
    # "it might be useful to also read the players type, so you don't mark a pitcher with
    # speed since that doesn't make sense."
    #
    # The two ranges are DISJOINT where it matters, measured over 131 hand-labelled cards
    # split by whether their hand was a batting or a pitching hand:
    #     batters   speed    1 x14   2 x14   3 x38     n=66   never 0
    #     pitchers  fielding 0 x39   1 x23   2 x3      n=65   never 3
    # so secondary 0 implies pitcher and 3 implies batter; 1 and 2 need the card's banner.
    # Default "" is deliberate: an unknown role must not silently read as either one.


@dataclass
class TacticsCard:
    name: str
    kind: TacticsType
    bonus: int  # read directly off the card, not assumed


@dataclass
class GameState:
    half: str                    # "batting" or "pitching"
    batters_used: int            # 0-4: how many of your 5 batters/pitchers have gone this half
    your_score: int
    opp_score: int
    target_score: Optional[int] = None       # known only while pitching (your final batting score)
    runners: List[PlayerCard] = field(default_factory=list)  # baserunners, in base order
    redraws_left: int = 2


@dataclass
class Decision:
    player_card: PlayerCard
    tactics_card: Optional[TacticsCard]
    reasoning: str


# THE POWER/SPEED RATIO, SWEPT (2026-09-10). Every whole percent from 100/0 to 0/100,
# 101 ratios x 5 seeds x 2000 matches = 1,010,000 simulated matches against the naive
# always-boost baseline, in a model that FINALLY implements speed, tie coin-flips and
# runners advancing on outs (simulate.py; before that a speed boost was worth zero here by
# construction, which is why the old "79%" only ever showed swing beats NOTHING):
#
#     pure POWER  100/0    37.95%  +/- 0.29
#     BEST         99/1    38.12%  +/- 0.33   <- +0.17 points, 0.4 sigma: NOT significant
#     plateau     100/0 .. 61/39   all statistically indistinguishable
#     first REAL drop      60/40   36.05%     <- >2 sigma below pure power
#     pure SPEED   0/100    6.69%
#
# 99/1 IS SHIPPED, AND IT IS NOT A TRADE. Powers are integers, so one point of power is
# 0.99 while the widest possible speed gap is about 0.06 -- power decides every comparison
# it can, and speed ONLY breaks an exact power tie. The sweep is what licenses that: inside
# a plateau 39 points wide, a tie-break on speed is free rather than a gamble.
#
# It is NOT evidence that speed is worth something. It is evidence that preferring the
# faster of two otherwise-equal cards costs nothing measurable, and the model is myopic
# about speed anyway -- a batter's speed pays off LATER, as a runner, and 5-round matches
# may be too short to show it. Do not read 99/1 as "speed weighting works".
POWER_WEIGHT = 0.99
SPEED_WEIGHT = 0.01


def power_bonus(tactics_card) -> int:
    """The power a tactics card actually adds. ONLY swing and pitch boosts do.

    simulate.py has had this rule since 2026-08-23, when adding any tactics bonus regardless
    of kind was found to overstate the speed-boost fallback. decision_engine never needed it
    because best_batting_play did not score power+tactics jointly; now it does, and the rule
    has to exist on this side too or a speed boost would silently inflate power here.
    """
    if tactics_card is None:
        return 0
    if tactics_card.kind in (TacticsType.SWING_BOOST, TacticsType.PITCH_BOOST):
        return tactics_card.bonus
    return 0


def best_batting_play(hand_players: List[PlayerCard],
                       hand_tactics: List[TacticsCard],
                       state: GameState) -> Decision:
    """
    Choose which batter (+ optional tactics card) to play this turn.

    Confirmed rule (community guides + verified live 2026-08-23): a hit
    just needs your batter's power to beat the pitcher's power — margin
    doesn't matter for that. But beating it by 3+ triggers an automatic
    home run that clears every runner on base plus the batter at once.
    Card selection is blind each round (the pitcher's card isn't known
    until after you commit), so there's no way to compute the exact
    margin in advance — only to raise the odds of clearing it.

    Heuristics:
    - Always play the highest-power batter — it raises both the odds of
      any hit and the odds of a 3+ margin for a home run.
    - Always attach a swing boost when one's available. BUT READ WHAT THAT
      NUMBER ACTUALLY COMPARES: simulate.py's 500-match tournament
      (2026-08-23) gave always-boosting a 79% win rate against holding
      tactics back "for a bigger payoff turn" — and in that simulation a
      hit is `runners.append(batter_card)` with SPEED NEVER CONSULTED, so
      a speed boost does nothing there BY CONSTRUCTION. The 79% therefore
      shows swing-boost beats NOTHING. It has never compared swing against
      speed, and it must not be cited as though it had.
      The power half of the reasoning does stand on the confirmed rule:
      extra power raises both hit odds and the odds of a 3+ margin.
    - THE SPEED ALTERNATIVE HAS NOW BEEN EVALUATED, and this paragraph used to
      say it had not. Speed IS modelled in simulate.py (MODEL_SPEED, since
      2026-09-12): _step reads the card's secondary, and speed_bonus reaches
      the batter's own advance. Measured there, a SWING boost is worth
      +0.614 runs/half and a SPEED boost +0.131 -- a factor of 4.7 -- which is
      the argument for power, made against a model that can finally see both.
      THE FIGURES THIS REPLACES (+0.726, +0.034, "a factor of 21") ARE
      WITHDRAWN and must not be re-cited. They were taken on the SCRAMBLED
      pool, before cards carried roles: pitchers were dealt as batters with
      their FIELDING read as SPEED, so a third of "batters" had speed 0 and a
      speed boost on them bought almost nothing. A speed measurement taken
      where a third of the batters are pitchers is not a speed measurement.
      The CONCLUSION survives -- swing still wins decisively, so the
      preference for power is unchanged -- but any argument that leaned on
      "21x" to call speed negligible was leaning on an artefact. See CLAUDE.md
      section 4, which carries the re-measurement.
    - AND THIS FUNCTION NO LONGER SORTS ON POWER ALONE. It scores every
      (batter, tactics) pair at POWER_WEIGHT * power + SPEED_WEIGHT * speed,
      99/1, so speed breaks ties between equal-power plays and decides nothing
      else: powers are integers, so one point of power is 0.99 while the widest
      possible speed gap is about 0.06. The older description -- power-only,
      with a speed boost reached for "as a fallback, and only when runners are
      already on base" -- describes code that is gone, and a reader acting on it
      would think the speed field is unread.
    - 99/1 IS A FREE TIE-BREAK, NOT A TRADE, and must not be read as "speed
      weighting works": the sweep that chose it measured +0.17 points at 0.4
      sigma, which is not significant. See POWER_WEIGHT above.
    """
    best = None
    best_score = None
    for batter in hand_players:
        for tac in [None] + list(hand_tactics):
            power = batter.power + power_bonus(tac)
            speed = batter.secondary or 0
            if tac is not None and tac.kind == TacticsType.SPEED_BOOST:
                speed += tac.bonus
            score = POWER_WEIGHT * power + SPEED_WEIGHT * speed
            if best_score is None or score > best_score:
                best, best_score = (batter, tac), score
    best_batter, tactics_choice = best

    reasoning_bits = [f"Playing {best_batter.name} (power {best_batter.power}, "
                      f"speed {best_batter.secondary})"]
    if tactics_choice is not None:
        if tactics_choice.kind == TacticsType.SWING_BOOST:
            reasoning_bits.append(
                f"attaching swing boost (+{tactics_choice.bonus}) — more power never hurts, "
                "and it raises the odds of a 3+ margin home run")
        elif tactics_choice.kind == TacticsType.SPEED_BOOST:
            reasoning_bits.append(
                f"no swing boost worth more — attaching speed boost (+{tactics_choice.bonus})")
        else:
            reasoning_bits.append(f"attaching {tactics_choice.name}")

    return Decision(best_batter, tactics_choice, "; ".join(reasoning_bits))


# How much pitch focus we are willing to trade for fielding when runners are on.
# THE QUESTION IS SETTLED, AND IT SETTLED THE OTHER WAY -- DO NOT ZERO THIS.
#
# This used to read "the fielding effect is UNCONFIRMED ... Set to 0 for pure power-first
# once the question is settled" (it measured p=0.192 on 19 usable rows, which is too few to
# tell). On 2026-09-10 the user supplied the rule from a community guide and a Reddit
# write-up: the BLACK PITCHER BUFFS subtract movement spaces from the batting side's
# runners. Fielding is that effect. So it is real, and it does something only when there
# ARE runners to slow -- which is exactly the condition best_pitching_play already gates on.
#
# 1 stays because the EFFECT is confirmed and its MAGNITUDE is not: nothing here has
# measured how many bases a point of fielding removes, so nothing justifies paying more than
# a point of power for it. Raise it only against a measurement, and do not lower it on the
# strength of the old comment, which is now wrong.
FIELDING_POWER_BUDGET = 1

# Redraw when the best card in hand is at or below this. Measured, not chosen:
# 58.5% head-to-head over 4000 matches against the previous 4, once
# simulate.py's discard model was corrected to match the real mechanic (keep
# the at-bat, replace ONE card). Sweep: 5 -> 56.4%, 6 -> 58.5%, 7 -> 56.5%,
# 8 -> 54.0%, always-redraw -> 49.3%. Moving this REQUIRES that discards throw
# away the weakest card (orchestrator.py) — at 4 that choice was irrelevant,
# above 4 it is not.
REDRAW_POWER_THRESHOLD = 6


def best_pitching_play(hand_players: List[PlayerCard],
                        hand_tactics: List[TacticsCard],
                        state: GameState) -> Decision:
    """
    Choose which pitcher (+ optional tactics card) to play this turn.

    Heuristics:
    - Maximise pitch focus (power). With runners on, fielding breaks a tie and
      may buy at most FIELDING_POWER_BUDGET power — never more.
    - Always attach a pitch boost when one's available (same simulation
      finding as best_batting_play — see simulate.py, 2026-08-23): more
      pitch focus never hurts, so there's no real reason to hold it back
      regardless of how contested the game looks.

    WHY THIS CHANGED (2026-08-25). It used to sort by `(secondary, power)` with
    secondary as the PRIMARY key, so one fielding pip outranked any amount of
    pitch focus: a 4/1 was played over a 9/0.

    Two independent measurements, and their DIFFERENCE is instructive:
      * 73.6% of runner turns gave up a stronger pitcher, mean 3.30 power —
        drawing 5 cards from KNOWN_BAN_ROSTER's stat distribution, all players.
      * 46.9% / 2.76 power — under simulate.py's own hand model, which mixes in
        tactics cards and so offers fewer players to choose between.
    Neither is "the" number; they bracket it, and the direction is the same
    either way. The earlier version of this comment quoted only the first
    without saying which model produced it, which is not reproducible.

    The head-to-head is the figure that matters and is model-independent within
    simulate.py: 800 matches, corrected vs original, **53.9% to 23.9%**.

    That is backwards with respect to what this project actually knows. The
    ONLY confirmed rule (HEURISTICS.md:4) is that a hit needs power greater
    than the opponent's, and a 3+ margin is a home run. The fielding/`secondary`
    effect is the open question `match_log.jsonl` exists to answer. Run
    `python3 analyze_match_log.py` for the live figure; on 2026-08-26 it read
    **p=0.192 on 19 usable rows — cannot conclude**. (An earlier version cited
    p=0.43, which was the BATTER-SPEED row of an older analysis quoted while
    discussing PITCHER FIELDING, whose p was 0.74. Three numbers were in
    circulation for one claim; the script is now the single source.)

    The old code sacrificed the confirmed mechanism to chase the unconfirmed
    one, on exactly the turns (runners on base) where conceding a home run
    costs most.

    The same inversion applied to tactics: a fielding boost adds ZERO power
    (`power_bonus()`, simulate.py:97), so preferring it over an available pitch
    boost discarded real, confirmed power for a speculative effect.

    FIELDING_POWER_BUDGET keeps a hedge rather than dropping fielding entirely:
    if the effect turns out to be real, a 1-power premium is cheap; if it is
    not, the cost is bounded and small. Set it to 0 for pure power-first once
    the fielding question is settled either way.
    """
    runners_on = len(state.runners) > 0

    pitch_boosts = [t for t in hand_tactics if t.kind == TacticsType.PITCH_BOOST]
    field_boosts = [t for t in hand_tactics if t.kind == TacticsType.FIELDING_BOOST]

    max_power = max(c.power for c in hand_players)
    if runners_on:
        # Only cards within the budget of the best are eligible; among those,
        # prefer fielding, then power. Bounded by construction — the worst case
        # is giving up FIELDING_POWER_BUDGET power, never 5.
        affordable = [c for c in hand_players
                      if c.power >= max_power - FIELDING_POWER_BUDGET]
        best_pitcher = max(affordable, key=lambda c: (c.secondary, c.power))
        if best_pitcher.power < max_power:
            reasoning_bits = [
                f"Playing {best_pitcher.name} (focus {best_pitcher.power}, "
                f"fielding {best_pitcher.secondary}) — runners on, paying "
                f"{max_power - best_pitcher.power} focus for fielding"]
        else:
            reasoning_bits = [f"Playing {best_pitcher.name} "
                              f"(focus {best_pitcher.power}) — runners on"]
    else:
        best_pitcher = max(hand_players, key=lambda c: (c.power, c.secondary))
        reasoning_bits = [f"Playing {best_pitcher.name} (pitch focus {best_pitcher.power})"]

    tactics_choice = None
    if pitch_boosts:
        # Pitch boost FIRST, even with runners on: it adds confirmed power, a
        # fielding boost adds none.
        tactics_choice = max(pitch_boosts, key=lambda t: t.bonus)
        reasoning_bits.append(f"attaching pitch boost (+{tactics_choice.bonus}) — more focus never hurts")
    elif runners_on and field_boosts:
        tactics_choice = max(field_boosts, key=lambda t: t.bonus)
        reasoning_bits.append("attaching fielding boost (no pitch boost held)")

    return Decision(best_pitcher, tactics_choice, "; ".join(reasoning_bits))


def should_redraw(hand_players: List[PlayerCard], state: GameState) -> bool:
    """
    Decide whether to burn a discard/redraw before playing this turn.

    Heuristic: redraw if your best available card is weak and you still
    have redraws left. Downside of losing one mediocre card is small
    relative to the upside of drawing something strong.

    THRESHOLD RAISED 4 -> 6 on 2026-08-26, measured at 58.5% head-to-head
    over 4000 matches. The old 4 was not a bad judgement call — it was
    correctly tuned for a mechanic this game does not have. simulate.py
    modelled a discard as "throw away your whole hand and play one random
    card", which makes redrawing a terrible deal at any threshold. The real
    mechanic keeps your at-bat and replaces ONE card, leaving the rest of
    the hand intact, so a redraw is far cheaper than the old model implied.
    Fixing the model and re-running the sweep gave 5:56.4%, 6:58.5%,
    7:56.5%, 8:54.0%. "Always redraw" is NOT better (49.3%) — burning both
    discards early leaves none for the hands that need them.

    Paired with discarding the WORST card in orchestrator.py, not the best.
    At threshold 4 that choice was a 100% tie (the pool minimum is 4, so any
    draw beats a qualifying hand outright); at 6 discarding the worst is
    changes the outcome in 17.0% of qualifying hands (5.9% of all hands
    dealt) and is worse in none. The two rules pick a different card 53.9% of
    the time, but usually to no effect, so that larger figure counts
    disagreements rather than wins. Measured over 200k hands. The two changes
    must move together — see test_decisions.py.
    """
    if state.redraws_left <= 0:
        return False
    return max(c.power for c in hand_players) <= REDRAW_POWER_THRESHOLD


def choose_bans(collection: List[PlayerCard], count: int = 3) -> List[PlayerCard]:
    """
    Choose which player cards to ban from your collection before a match.

    Heuristic: ban your weakest player cards by primary stat (swing
    power / pitch focus), breaking ties on `secondary`. Tactics cards are
    never in this pool to begin with — a boost is useful regardless of
    which base card you draw, so there'd be no reason to remove one even
    if they were eligible.

    THE TIE-BREAK IS NOT COSMETIC, AND IT IS ROLE-INDEPENDENT. Sorting on
    power alone left ties to scan order: on the 2026-09-16 collection that
    banned two 4/3 cards and KEPT a 4/1 and a 4/2, which are strictly worse
    cards to draw. `secondary` decides it without needing to know the role,
    because higher is better in BOTH of its meanings -- SPEED on a batter is
    bases run, FIELDING on a pitcher subtracts runner movement -- so
    ascending (power, secondary) is worst-first either way. See RULES.md.
    """
    return sorted(collection, key=lambda c: (c.power, c.secondary))[:count]


if __name__ == "__main__":
    # Quick sanity check against the hand from your first batting screenshot:
    # Speed Boost(+2), Batter 8/1, Batter 4/3, Batter 4/2, Batter 5/2 — bases empty
    hand = [
        PlayerCard("Batter A", 8, 1),
        PlayerCard("Batter B", 4, 3),
        PlayerCard("Batter C", 4, 2),
        PlayerCard("Batter D", 5, 2),
    ]
    tactics = [TacticsCard("Speed Boost", TacticsType.SPEED_BOOST, 2)]
    state = GameState(half="batting", batters_used=0, your_score=0, opp_score=0)

    decision = best_batting_play(hand, tactics, state)
    print(f"Play: {decision.player_card.name} (power {decision.player_card.power})")
    print(f"Tactics: {decision.tactics_card.name if decision.tactics_card else 'none'}")
    print(f"Why: {decision.reasoning}")

    # A swing boost should always get used when available — even off a
    # solid (not mediocre) batter with no runners on base. Simulation-
    # informed (see simulate.py): holding tactics back turned out to
    # lose far more often than always attaching them.
    solid_hand = [PlayerCard("Solid Batter", 6, 1)]
    swing = [TacticsCard("Power Swing", TacticsType.SWING_BOOST, 3)]
    always_boost_decision = best_batting_play(solid_hand, swing, state)
    assert always_boost_decision.tactics_card is not None, "expected the swing boost to always be used"
    print(f"\nAlways-boost check passed: {always_boost_decision.reasoning}")

    # No swing boost, but a speed boost with a runner on base: use it.
    speed = [TacticsCard("Speed Boost", TacticsType.SPEED_BOOST, 2)]
    runner_state = GameState(half="batting", batters_used=1, your_score=0, opp_score=0,
                              runners=[PlayerCard("On Base", 5, 1)])
    speed_decision = best_batting_play(solid_hand, speed, runner_state)
    assert speed_decision.tactics_card is not None, "expected the speed boost to be used with a runner on"
    print(f"Speed-boost check passed: {speed_decision.reasoning}")
