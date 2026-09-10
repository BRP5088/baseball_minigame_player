"""
Local heuristic-vs-heuristic match simulator.

Runs entirely offline — two decision-making strategies play each other
using the CONFIRMED game rules (verified live 2026-08-23):
  - A hit just needs the active card's power to beat the opposing card's
    power.
  - Beating it by 3+ triggers a home run: clears every runner on base
    plus the batter, all at once.
This sidesteps the "we don't know the real opponent's AI" problem —
since both sides here are OUR OWN heuristics under rules we've actually
verified, a relative comparison (does heuristic A beat heuristic B more
often?) is honest, even though it can't tell you your real win rate
against the actual in-game opponent.

Simplifications, clearly flagged rather than hidden:
  - Hands are drawn randomly from the real 33-card collection scanned
    live from this save on 2026-08-23 (see CARD_POOL), not the true
    unknown draw distribution.
  - Runner-capacity and exact discard-redraw odds beyond "draw one random
    replacement card" aren't confirmed rules — modeled as the simplest
    reasonable guess.
  - SPEED IS NOT MODELLED AT ALL, and that is load-bearing. A hit is
    `runners.append(batter_card)`; the batter's speed stat is never read, so
    a SPEED_BOOST is worth exactly zero in here. Any tournament run in this
    model can show that a swing boost beats NOTHING; none of them can compare
    a swing boost against a speed boost. The rules the user supplied on
    2026-09-10 (CLAUDE.md §4) say speed decides how many bases a runner takes,
    that a tie is a coin flip capped at first base, and that a losing at-bat
    can still advance runners. None of those exist here. Do not quote this
    model's win rates on any question that touches baserunning.
  - Both simulated teams draw from the identical CARD_POOL/TACTICS pools,
    so the comparison is apples-to-apples even where these guesses are
    imperfect.
"""

import random

from decision_engine import (
    PlayerCard, TacticsCard, TacticsType, GameState, Decision,
    best_batting_play, best_pitching_play, should_redraw,
)

# Real card collection scanned live from this save (2026-08-23).
# NOTE: this duplicates KNOWN_BAN_ROSTER (orchestrator.py). They must agree —
# test_known_ban_roster.py enforces it. Harold "Fisto" Blunt was 9/1 here while
# the roster held 9/3, corrected from a live capture on 2026-08-24; the stale
# copy silently fed every tournament that reasons about `secondary`.
# Papa Jody Gain remains disputed (roster 5/0, here 5/2) with no evidence
# either way — see the _DISPUTED set in test_known_ban_roster.py.
CARD_POOL = [
    PlayerCard("Johnny Drawers", 7, 1), PlayerCard("Mama Jody Gain", 5, 1),
    PlayerCard("Harold \"Fisto\" Blunt", 9, 3), PlayerCard("Jenny Jody Gain", 6, 0),
    PlayerCard("Donny Mekesz", 5, 3), PlayerCard("Claude Ewer", 7, 0),
    PlayerCard("William Lee-Gains", 4, 0), PlayerCard("Brandon \"Binger\" Ortiz", 5, 2),
    PlayerCard("Joshua Diaz", 4, 0), PlayerCard("Justin Young", 6, 0),
    PlayerCard("Zachary Lee", 6, 2), PlayerCard("Johnny \"Blaze\" Sweets", 4, 3),
    PlayerCard("Johnny C-Train Goudenberg", 7, 0), PlayerCard("Charlie Pepper", 8, 0),
    PlayerCard("Josef Bunz-Konicky", 9, 2), PlayerCard("Rube Sharp", 8, 1),
    PlayerCard("Austin \"Cur\" Bunz", 8, 1), PlayerCard("Jacob \"Cheesehead\" McQueen", 9, 1),
    PlayerCard("William Brown", 4, 3), PlayerCard("Jeremiah Curd", 7, 0),
    PlayerCard("Marian Bunz-Twarog", 4, 1), PlayerCard("Jedediah Wetters", 4, 2),
    PlayerCard("Brian Coker", 8, 1), PlayerCard("Timmeh Rattycum", 4, 3),
    PlayerCard("Joe Jody Gain", 6, 0), PlayerCard("Papa Jody Gain", 5, 2),
    PlayerCard("Daniel \"The Rat-Ta-Train\" Cruz", 4, 3), PlayerCard("Noah \"The Rat Baron\" Kelly", 6, 2),
    PlayerCard("Joel Blunt", 9, 0), PlayerCard("Bartholomew Creasley", 5, 1),
    PlayerCard("Jake Saucepan Black", 5, 3), PlayerCard("Mickey Brown", 5, 0),
    PlayerCard("Thomas Thomas", 5, 3),
]

TACTICS_POOL_BATTING = [
    TacticsCard("Power Swing", TacticsType.SWING_BOOST, b) for b in (1, 2, 3)
] + [
    TacticsCard("Speed Boost", TacticsType.SPEED_BOOST, b) for b in (1, 2, 3)
]
TACTICS_POOL_PITCHING = [
    TacticsCard("Pitch Focus", TacticsType.PITCH_BOOST, b) for b in (1, 2, 3)
] + [
    TacticsCard("Fielding Play", TacticsType.FIELDING_BOOST, b) for b in (1, 2)
]

TACTICS_FRACTION = 0.5  # rough match to observed real hands (roughly half tactics cards)


def draw_hand(phase: str, player_pool=CARD_POOL):
    """Draw a simplified 5-card hand: each slot is independently a
    player or tactics card: reroll if a hand ends up with zero player
    cards, since every real hand has at least one. player_pool lets ban
    experiments draw from a collection with some cards removed."""
    pool = TACTICS_POOL_BATTING if phase == "batting" else TACTICS_POOL_PITCHING
    while True:
        players, tactics = [], []
        for _ in range(5):
            if random.random() < TACTICS_FRACTION:
                tactics.append(random.choice(pool))
            else:
                players.append(random.choice(player_pool))
        if players:
            return players, tactics


def replace_weakest(hand_players, player_pool):
    """A discard: swap the weakest player card for a fresh draw, keep the rest.

    CORRECTED 2026-08-26. This simulator previously modelled a discard as
    "throw the whole hand away and play one random card, no tactics" — which
    trades the best of five draws for a single average one and makes redrawing
    a losing move at any threshold. That is not this game: you KEEP your
    at-bat, exactly ONE selected card is replaced, and the other four are
    untouched (confirmed by the user watching a live match).

    Every redraw conclusion drawn before this date — including the shipped
    `<= 4` threshold, which the corrected model then beat 58.5% at 6 — was
    measured against a mechanic the game does not have.
    """
    if not hand_players:
        return hand_players
    worst = min(range(len(hand_players)), key=lambda i: hand_players[i].power)
    out = list(hand_players)
    out[worst] = random.choice(player_pool)
    return out


def power_bonus(tactics_card) -> int:
    """
    Only a swing/pitch boost's bonus affects resolve()'s power comparison
    — a speed or fielding boost's real effect isn't a confirmed rule, so
    it must NOT silently inflate power here (fixed 2026-08-23; it
    previously added any tactics card's bonus regardless of type, which
    overstated the speed-boost fallback's value in early runs).
    """
    if tactics_card is None:
        return 0
    if tactics_card.kind in (TacticsType.SWING_BOOST, TacticsType.PITCH_BOOST):
        return tactics_card.bonus
    return 0


# ---------------------------------------------------------------------------------------
# BASERUNNING. Added 2026-09-10 from rules the user supplied against a community guide and
# a Reddit write-up. Before this, a hit was `runners.append(batter_card)` and SPEED WAS
# NEVER READ -- so a speed boost was worth exactly zero in here by construction, and every
# tournament that compared tactics was really comparing "a boost" against "nothing".
#
# WHAT IS CONFIRMED (rule, sourced, and where noted observed live on 2026-09-10):
#   * a batter's `secondary` is SPEED: how many bases they run.
#     Observed: a speed-1 batter advanced exactly 1 base, and a speed-1 runner advanced
#     exactly 1 base on the next hit. Speed >= 2 is UNTESTED.
#   * a TIE (equal power) is a coin flip, and winning one is CAPPED AT FIRST BASE for the
#     batter regardless of speed.
#   * a LOSING at-bat can still advance runners.
#   * black pitcher buffs (FIELDING) SUBTRACT movement from the batting side's runners.
#
# WHAT IS NOT CONFIRMED, and is therefore a KNOB rather than a number invented here:
#   * how far runners advance on a losing at-bat            -> OUT_RUNNER_ADVANCE
#   * how many bases a point of fielding removes            -> FIELDING_SUBTRACT_PER_POINT
#   * whether existing runners advance on a TIE win         -> TIE_RUNNERS_ADVANCE
#     (observed once: on our 5-v-5 tie a speed-1 runner DID move first -> second, so the
#      default is True -- but that is n=1)
# Every one of them is swept by `python3 simulate.py --sweep`, which prints how the answer
# moves across the grid. A conclusion that changes with a knob is not a conclusion.

TIE_WIN_PROB = 0.5                 # confirmed shape: a coin flip
TIE_RUNNERS_ADVANCE = True         # n=1 observation
OUT_RUNNER_ADVANCE = "one"         # "none" | "one" | "speed"   -- UNMEASURED
FIELDING_SUBTRACT_PER_POINT = 1    # bases removed per point of fielding -- UNMEASURED
MODEL_SPEED = True                 # False reproduces the pre-2026-09-10 model exactly


def fielding_of(pitcher_card, tactics_card) -> int:
    """The defence's movement-subtracting stat: the pitcher's own fielding plus a
    FIELDING_BOOST if one was attached. A pitch boost does NOT count -- that is power."""
    f = getattr(pitcher_card, "secondary", 0) or 0
    if tactics_card is not None and tactics_card.kind == TacticsType.FIELDING_BOOST:
        f += tactics_card.bonus
    return f


def _step(card, fielding) -> int:
    """How many bases this runner takes, after the defence subtracts movement."""
    if not MODEL_SPEED:
        return 1
    speed = getattr(card, "secondary", 0) or 0
    return max(0, speed - FIELDING_SUBTRACT_PER_POINT * fielding)


def advance_runners(runners, fielding, mode="speed"):
    """Move every runner. Returns (still_on_base, runs_scored).

    `runners` is a list of (card, base) with base in 1..3. A runner reaching 4 scores.
    Runners can be lapped in the real game (CLAUDE.md 4), so no attempt is made to stop
    one passing another -- bases are not treated as exclusive.
    """
    still, scored = [], 0
    for card, base in runners:
        if mode == "none":
            step = 0
        elif mode == "one":
            step = 1
        else:
            step = _step(card, fielding)
        nb = base + step
        if nb >= 4:
            scored += 1
        else:
            still.append((card, nb))
    return still, scored


def resolve(offense_power: int, defense_power: int) -> str:
    """Confirmed rule: a hit needs offense > defense; beating it by 3+ is a home run.
    EQUAL power is a TIE -- a coin flip -- which this used to fold into "out"."""
    if offense_power < defense_power:
        return "out"
    if offense_power == defense_power:
        return "tie"
    if offense_power - defense_power >= 3:
        return "home_run"
    return "hit"


def simulate_batting_half(batting_heuristic, pitching_heuristic, defender_target_score=None,
                           redraw_fn=should_redraw, player_pool=CARD_POOL,
                           defender_player_pool=CARD_POOL, defender_redraw_fn=should_redraw) -> int:
    """
    Simulate one team's 5-round batting half against the opposing team's
    pitching heuristic defending every round. defender_target_score is
    the defender's own already-known batting score from their half (None
    if they haven't batted yet this match) — mirrors the real
    target_score mechanic used by best_pitching_play(). redraw_fn /
    defender_redraw_fn let experiments swap in a different redraw
    threshold than the real should_redraw() for either side, without
    duplicating this whole loop. player_pool / defender_player_pool let
    ban experiments draw each side's hands from a collection with some
    cards removed.
    """
    score = 0
    runners = []
    redraws_left = 2
    defender_redraws_left = 2

    for round_idx in range(5):
        hand_players, hand_tactics = draw_hand("batting", player_pool)
        state = GameState(half="batting", batters_used=round_idx, your_score=score,
                           opp_score=0, runners=[c for c, _ in runners], redraws_left=redraws_left)

        if redraw_fn(hand_players, state):
            redraws_left -= 1
            hand_players = replace_weakest(hand_players, player_pool)
            state = GameState(half="batting", batters_used=round_idx, your_score=score,
                              opp_score=0, runners=[c for c, _ in runners], redraws_left=redraws_left)
        decision = batting_heuristic(hand_players, hand_tactics, state)
        batter_card = decision.player_card
        batter_power = batter_card.power + power_bonus(decision.tactics_card)

        p_hand_players, p_hand_tactics = draw_hand("pitching", defender_player_pool)
        p_state = GameState(half="pitching", batters_used=round_idx, your_score=0, opp_score=score,
                             target_score=defender_target_score, runners=[c for c, _ in runners],
                             redraws_left=defender_redraws_left)

        # Fixed 2026-08-23 (caught in QA + Gemini review): the real game's
        # should_redraw() fires on either phase — orchestrator.py's
        # play_one_turn() calls it unconditionally — but this simulator
        # previously only ever checked it for the batting hand, never the
        # defending pitcher's. Every earlier result implicitly assumed the
        # pitcher never discards; now both sides get a real redraw check.
        if defender_redraw_fn(p_hand_players, p_state):
            defender_redraws_left -= 1
            p_hand_players = replace_weakest(p_hand_players, defender_player_pool)
            p_state = GameState(half="pitching", batters_used=round_idx, your_score=0,
                                opp_score=score, target_score=defender_target_score,
                                runners=[c for c, _ in runners], redraws_left=defender_redraws_left)
        p_decision = pitching_heuristic(p_hand_players, p_hand_tactics, p_state)
        pitcher_card = p_decision.player_card
        pitcher_power = pitcher_card.power + power_bonus(p_decision.tactics_card)

        outcome = resolve(batter_power, pitcher_power)
        fielding = fielding_of(pitcher_card, p_decision.tactics_card)
        batter_speed = getattr(batter_card, "secondary", 0) or 0

        if outcome == "tie":
            # A coin flip. Losing it is an out; winning it is a hit whose batter is CAPPED
            # at first base regardless of speed.
            if random.random() < TIE_WIN_PROB:
                if TIE_RUNNERS_ADVANCE:
                    runners, gained = advance_runners(runners, fielding, "speed")
                    score += gained
                runners.append((batter_card, 1))
            else:
                outcome = "out"

        if outcome == "home_run":
            score += 1 + len(runners)
            runners = []
        elif outcome == "hit":
            runners, gained = advance_runners(runners, fielding, "speed")
            score += gained
            # the batter runs their OWN speed; at least one base, or it was not a hit
            steps = max(1, _step(batter_card, fielding)) if MODEL_SPEED else 1
            if steps >= 4:
                score += 1
            else:
                runners.append((batter_card, steps))
        elif outcome == "out":
            # A losing at-bat can still advance runners (rule, magnitude unmeasured).
            runners, gained = advance_runners(runners, fielding, OUT_RUNNER_ADVANCE)
            score += gained

    return score


def simulate_match(team_a: dict, team_b: dict):
    """
    team_a/team_b: {"batting": fn, "pitching": fn, "redraw": fn (optional,
    defaults to should_redraw), "pool": list[PlayerCard] (optional,
    defaults to the full CARD_POOL — a banned-down pool for ban
    experiments)}. Returns (a_score, b_score).
    """
    a_redraw = team_a.get("redraw", should_redraw)
    b_redraw = team_b.get("redraw", should_redraw)
    a_pool = team_a.get("pool", CARD_POOL)
    b_pool = team_b.get("pool", CARD_POOL)
    a_score = simulate_batting_half(team_a["batting"], team_b["pitching"], defender_target_score=None,
                                     redraw_fn=a_redraw, player_pool=a_pool, defender_player_pool=b_pool,
                                     defender_redraw_fn=b_redraw)
    b_score = simulate_batting_half(team_b["batting"], team_a["pitching"], defender_target_score=a_score,
                                     redraw_fn=b_redraw, player_pool=b_pool, defender_player_pool=a_pool,
                                     defender_redraw_fn=a_redraw)
    return a_score, b_score


def run_tournament(team_a: dict, team_b: dict, name_a: str, name_b: str, n_matches: int = 500):
    a_wins = b_wins = draws = 0
    a_total_score = b_total_score = 0

    for _ in range(n_matches):
        a_score, b_score = simulate_match(team_a, team_b)
        a_total_score += a_score
        b_total_score += b_score
        if a_score > b_score:
            a_wins += 1
        elif b_score > a_score:
            b_wins += 1
        else:
            draws += 1

    print(f"{name_a} vs {name_b} over {n_matches} matches:")
    print(f"  {name_a}: {a_wins} wins ({100 * a_wins / n_matches:.1f}%), avg score {a_total_score / n_matches:.2f}")
    print(f"  {name_b}: {b_wins} wins ({100 * b_wins / n_matches:.1f}%), avg score {b_total_score / n_matches:.2f}")
    print(f"  Draws: {draws} ({100 * draws / n_matches:.1f}%)")


# --- Baseline heuristics for comparison ---

def naive_no_tactics(hand_players, hand_tactics, state) -> Decision:
    """Always play the highest-power card, never use a tactics card."""
    best = max(hand_players, key=lambda c: c.power)
    return Decision(best, None, "naive: highest power, no tactics")


def naive_always_boost(hand_players, hand_tactics, state) -> Decision:
    """Always play the highest-power card, and always attach the
    best-available boost of the right kind, regardless of situation."""
    best = max(hand_players, key=lambda c: c.power)
    boosts = [t for t in hand_tactics if t.kind in (TacticsType.SWING_BOOST, TacticsType.PITCH_BOOST)]
    tactic = max(boosts, key=lambda t: t.bonus) if boosts else None
    return Decision(best, tactic, "naive: highest power, always boost")


CURRENT = {"batting": best_batting_play, "pitching": best_pitching_play}
NO_TACTICS = {"batting": naive_no_tactics, "pitching": naive_no_tactics}
ALWAYS_BOOST = {"batting": naive_always_boost, "pitching": naive_always_boost}


if __name__ == "__main__":
    random.seed(42)  # reproducible run-to-run for comparing code changes fairly
    run_tournament(CURRENT, NO_TACTICS, "current heuristic", "naive (no tactics)")
    print()
    run_tournament(CURRENT, ALWAYS_BOOST, "current heuristic", "naive (always boost)")
    print()
    run_tournament(NO_TACTICS, ALWAYS_BOOST, "naive (no tactics)", "naive (always boost)")


# ---------------------------------------------------------------------------------------
# THE SWEEP. Three of the baserunning inputs are RULES with unmeasured MAGNITUDES, so any
# single run of this model is one guess about them. This sweeps the grid and prints how the
# answer moves. A conclusion that flips across the grid is not a conclusion -- it is a
# statement about the guess (CLAUDE.md 10.4's shape, one level up).
def sweep(n_matches=400, seeds=(1, 2, 3)):
    import itertools, statistics
    global MODEL_SPEED, OUT_RUNNER_ADVANCE, FIELDING_SUBTRACT_PER_POINT, TIE_RUNNERS_ADVANCE
    saved = (MODEL_SPEED, OUT_RUNNER_ADVANCE, FIELDING_SUBTRACT_PER_POINT, TIE_RUNNERS_ADVANCE)
    grid = list(itertools.product([False, True], ["none", "one", "speed"], [0, 1], [True]))
    print(f"{'speed':6s} {'out-adv':8s} {'field/pt':9s} | current vs always-boost "
          f"(mean win% over {len(seeds)} seeds x {n_matches})")
    print("-" * 78)
    rows = []
    try:
        for ms, oa, fs, tr in grid:
            MODEL_SPEED, OUT_RUNNER_ADVANCE, FIELDING_SUBTRACT_PER_POINT, TIE_RUNNERS_ADVANCE = ms, oa, fs, tr
            cur, alt = [], []
            for sd in seeds:
                random.seed(sd)
                a = b = 0
                for _ in range(n_matches):
                    x, y = simulate_match(CURRENT, ALWAYS_BOOST)
                    if x > y: a += 1
                    elif y > x: b += 1
                cur.append(100 * a / n_matches); alt.append(100 * b / n_matches)
            c, t = statistics.mean(cur), statistics.mean(alt)
            rows.append((ms, oa, fs, c, t))
            flag = "current AHEAD" if c - t > 3 else ("always-boost AHEAD" if t - c > 3 else "tie")
            print(f"{str(ms):6s} {oa:8s} {str(fs):9s} | {c:5.1f}% vs {t:5.1f}%   {flag}")
    finally:
        MODEL_SPEED, OUT_RUNNER_ADVANCE, FIELDING_SUBTRACT_PER_POINT, TIE_RUNNERS_ADVANCE = saved
    spread = max(r[3] for r in rows) - min(r[3] for r in rows)
    print("-" * 78)
    print(f"  current-heuristic win% ranges {min(r[3] for r in rows):.1f}..{max(r[3] for r in rows):.1f} "
          f"across the grid (spread {spread:.1f} points)")
    print(f"  every cell: {'the two are within 3 points -- the heuristic does NOT beat the naive baseline' if all(abs(r[3]-r[4])<=3 for r in rows) else 'the ordering CHANGES across the grid -- unmeasured knobs decide the answer'}")
    return rows
