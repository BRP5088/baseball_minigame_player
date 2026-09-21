"""A/B engine for ISSUES.md I-15 (card sequencing), I-16 (deck-aware discard) and
I-17 (opponent model from the log instead of our own pool).

OFFLINE ONLY. Reuses simulate.py's own machinery (simulate_match, CARD_POOL,
for_phase, power_bonus, advance_runners) rather than re-deriving it, and follows the
tie_w experiment's shape (CLAUDE.md sec 4, sec 10.2/10.3/10.7): one change per arm, a
control that must reproduce the shipped baseline to the printed precision, n large
enough to detect what is being looked for (12,000 halves x 3 seeds, matching the
tie_w sweep), and every arm reports how many simulated decisions it actually changed
-- a knob that changes zero decisions is not measuring what its name says.

No decision_engine.py / simulate.py shipped constant is changed by this file. It
measures; shipping is the user's call.

Run:
    .venv/bin/python -B tools/ab_engine_i15_16_17.py --arm baseline
    .venv/bin/python -B tools/ab_engine_i15_16_17.py --arm i15
    .venv/bin/python -B tools/ab_engine_i15_16_17.py --arm i16
    .venv/bin/python -B tools/ab_engine_i15_16_17.py --arm i17
    .venv/bin/python -B tools/ab_engine_i15_16_17.py --arm decisions   (decision-diff counts)
    .venv/bin/python -B tools/ab_engine_i15_16_17.py --arm all
"""
import argparse
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simulate as sim
from decision_engine import (
    Decision, TacticsType, GameState, PlayerCard,
    best_batting_play, best_pitching_play, should_redraw,
    POWER_WEIGHT, SPEED_WEIGHT, REDRAW_POWER_THRESHOLD,
)

N_MATCHES = 12000
SEEDS = (1, 2, 3)

_HERE = os.path.dirname(os.path.abspath(__file__))
_LOG_DIST_PATH = os.path.join(_HERE, "..", "agent_progress", "issues", "I-15-16-17",
                               "opp_pitcher_dist.json")


# ---------------------------------------------------------------------------------------
# The measurement harness itself: runs/half + win%/draw% for `team`'s OWN batting half
# against a fixed `opponent`, exactly simulate.sweep_ratio's methodology (the tie_w
# harness). Per-seed stats are kept so a sigma can be computed on the ARM vs CONTROL
# per-match score arrays.
def run_arm(team, opponent, n_matches=None, seeds=SEEDS):
    # n_matches defaults to None, resolved to the CURRENT global at call time -- a
    # module-level default captured at def-time is exactly CLAUDE.md 10.18's trap
    # (leg_reliability's `path=STORE`), and it bit this file's own first draft: with
    # `n_matches=N_MATCHES` in the signature, --n_matches was silently ignored because
    # the default had already been bound to 12000 when this module was imported.
    if n_matches is None:
        n_matches = N_MATCHES
    scores = []
    wins = draws = losses = 0
    for sd in seeds:
        random.seed(sd)
        for _ in range(n_matches):
            x, y = sim.simulate_match(team, opponent)
            scores.append(x)
            if x > y:
                wins += 1
            elif x == y:
                draws += 1
            else:
                losses += 1
    n = n_matches * len(seeds)
    return {
        "n": n,
        "runs_per_half": statistics.mean(scores),
        "runs_sd": statistics.pstdev(scores),
        "win_pct": 100 * wins / n,
        "draw_pct": 100 * draws / n,
        "scores": scores,
    }


def sigma_runs(control, arm):
    """Two-sample z on the per-match score arrays (large n, treat as normal)."""
    c, a = control["scores"], arm["scores"]
    mc, ma = statistics.mean(c), statistics.mean(a)
    vc, va = statistics.pvariance(c), statistics.pvariance(a)
    se = math.sqrt(vc / len(c) + va / len(a))
    return (ma - mc) / se if se else float("inf")


def fmt_row(label, res, control=None):
    line = (f"  {label:34s} n={res['n']:6d}  runs/half={res['runs_per_half']:.4f}  "
            f"win%={res['win_pct']:5.2f}  draw%={res['draw_pct']:5.2f}")
    if control is not None:
        d = res["runs_per_half"] - control["runs_per_half"]
        s = sigma_runs(control, res)
        line += f"   delta={d:+.4f}  sigma={s:+.2f}"
    return line


# ---------------------------------------------------------------------------------------
# BASELINE. CURRENT (best_batting_play + best_pitching_play) vs ALWAYS_BOOST, matching
# the tie_w harness's own opponent (simulate.ALWAYS_BOOST, sweep_ratio's default).
def baseline():
    return run_arm(sim.CURRENT, sim.ALWAYS_BOOST)


# ---------------------------------------------------------------------------------------
# I-15. Card sequencing: GameState.batters_used is plumbed and read by nothing.
# Arm: hold the single best batter back unless a runner is on base or it is the last
# round (batters_used >= 4), so a home run with the bases loaded is worth more than one
# with them empty. Control (hold=False) is bit-for-bit the shipped scorer -- same
# formula, same full hand -- so it must reproduce the baseline exactly.
def sequenced_batting_play(hold: bool):
    def play(hand_players, hand_tactics, state):
        pool = hand_players
        if hold and len(state.runners) == 0 and state.batters_used < 4 and len(hand_players) > 1:
            best_card = max(hand_players, key=lambda c: c.power)
            restricted = [c for c in hand_players if c is not best_card]
            if restricted:
                pool = restricted
        best, best_score = None, None
        for batter in pool:
            for tac in [None] + list(hand_tactics):
                power = batter.power + sim.power_bonus(tac)
                speed = batter.secondary or 0
                if tac is not None and tac.kind == TacticsType.SPEED_BOOST:
                    speed += tac.bonus
                score = POWER_WEIGHT * power + SPEED_WEIGHT * speed
                if best_score is None or score > best_score:
                    best, best_score = (batter, tac), score
        b, t = best
        return Decision(b, t, f"sequenced(hold={hold}): power {b.power} speed {b.secondary}")
    return play


def i15():
    control_team = {"batting": sequenced_batting_play(False), "pitching": best_pitching_play}
    arm_team = {"batting": sequenced_batting_play(True), "pitching": best_pitching_play}
    control = run_arm(control_team, sim.ALWAYS_BOOST)
    arm = run_arm(arm_team, sim.ALWAYS_BOOST)
    return control, arm


def i15_decisions_changed(n=4000, seed=7):
    """How many single decisions differ between hold=True and hold=False, on the same
    (hand, state) -- decoupled from a full match so a later divergence in card removal
    cannot blur the count."""
    random.seed(seed)
    hold_fn, no_hold_fn = sequenced_batting_play(True), sequenced_batting_play(False)
    changed = 0
    for _ in range(n):
        hand_players, hand_tactics = sim.draw_hand("batting")
        runners_empty = random.random() < 0.6
        runners = [] if runners_empty else [sim.CARD_POOL[random.randrange(len(sim.CARD_POOL))]]
        batters_used = random.randrange(5)
        state = GameState(half="batting", batters_used=batters_used, your_score=0,
                           opp_score=0, runners=runners)
        d1 = hold_fn(hand_players, hand_tactics, state)
        d2 = no_hold_fn(hand_players, hand_tactics, state)
        if d1.player_card is not d2.player_card:
            changed += 1
    return changed, n


# ---------------------------------------------------------------------------------------
# I-16. Deck-aware discard: REDRAW_POWER_THRESHOLD is a fixed 6 regardless of what is
# left in the deck. Arm: redraw when P(a fresh draw beats the current hand's max power)
# exceeds a swept threshold, computed from the ROLE-filtered pool minus the cards
# CURRENTLY in hand (the only per-turn "cards seen" signal available without threading
# extra state through simulate_batting_half -- ponytail: a fuller "every card seen this
# half" tracker would need a mutable per-half accumulator passed into redraw_fn; this
# uses the visible hand as the conditioning set instead, which is the cheap and testable
# version of the same idea). No bans are modelled here (I-13's own arms are closed), so
# the pool is the full 33-card CARD_POOL, role-filtered.
def deck_aware_redraw(threshold: float):
    def redraw_fn(hand_players, state):
        if state.redraws_left <= 0:
            return False
        if getattr(state, "hidden_by_homeplate_runner", False) or \
           getattr(state, "hand_incomplete", False):
            return False
        pool = sim.for_phase(sim.CARD_POOL, state.half)
        seen = {c.name for c in hand_players}
        remaining = [c for c in pool if c.name not in seen]
        if not remaining:
            return max(c.power for c in hand_players) <= REDRAW_POWER_THRESHOLD
        current_max = max(c.power for c in hand_players)
        p_improve = sum(1 for c in remaining if c.power > current_max) / len(remaining)
        return p_improve > threshold
    return redraw_fn


I16_THRESHOLDS = (0.3, 0.4, 0.5, 0.6)


def i16():
    control_team = {"batting": best_batting_play, "pitching": best_pitching_play}
    control = run_arm(control_team, sim.ALWAYS_BOOST)
    arms = {}
    for t in I16_THRESHOLDS:
        team = {"batting": best_batting_play, "pitching": best_pitching_play,
                "redraw": deck_aware_redraw(t)}
        arms[t] = run_arm(team, sim.ALWAYS_BOOST)
    return control, arms


def i16_decisions_changed(threshold, n=4000, seed=11):
    random.seed(seed)
    arm_fn = deck_aware_redraw(threshold)
    changed = 0
    considered = 0
    for _ in range(n):
        phase = "batting" if random.random() < 0.5 else "pitching"
        hand_players, _ = sim.draw_hand(phase)
        redraws_left = random.choice([0, 1, 2])
        state = GameState(half=phase, batters_used=random.randrange(5), your_score=0,
                           opp_score=0, redraws_left=redraws_left)
        if redraws_left <= 0:
            continue
        considered += 1
        a = arm_fn(hand_players, state)
        b = should_redraw(hand_players, state)
        if a != b:
            changed += 1
    return changed, considered


# ---------------------------------------------------------------------------------------
# I-17. Opponent model: _pitcher_power_distribution is built from OUR OWN card pool
# (CARD_POOL), but RULES.md sec 2 says the two players hold separate decks. Build the
# distribution from match_log.jsonl's real opponent-pitcher powers instead (only rows
# with a local reveal read -- outcome_basis or margin present -- so a misread never
# enters the distribution) and rerun expected_runs_play against CURRENT (the documented
# earlier result, "39.8% vs 35.5%", used the pool and lost).
def load_log_distribution():
    with open(_LOG_DIST_PATH) as f:
        d = json.load(f)
    probs = d["effective_power_probs"]
    return [(int(k), v) for k, v in sorted(probs.items(), key=lambda kv: int(kv[0]))], d


def make_expected_runs_play(dist):
    def play(hand_players, hand_tactics, state):
        runners = [(c, 1) for c in state.runners]
        options = [None] + list(hand_tactics)
        best, best_ev, best_why = None, -1.0, ""
        for batter in hand_players:
            for tac in options:
                power = batter.power + sim.power_bonus(tac)
                speed = (batter.secondary or 0)
                if tac is not None and tac.kind == TacticsType.SPEED_BOOST:
                    speed += tac.bonus
                ev = 0.0
                for p, prob in dist:
                    if power < p:
                        _, gained = sim.advance_runners(runners, 0, sim.OUT_RUNNER_ADVANCE)
                        ev += prob * gained
                    elif power == p:
                        _, gained = sim.advance_runners(runners, 0, "speed")
                        ev += prob * sim.TIE_WIN_PROB * gained
                    elif power - p >= 3:
                        ev += prob * (1 + len(runners))
                    else:
                        _, gained = sim.advance_runners(runners, 0, "speed")
                        steps = max(1, speed)
                        ev += prob * (gained + (1 if steps >= 4 else 0))
                if ev > best_ev:
                    best, best_ev, best_why = (batter, tac), ev, f"EV {ev:.3f}"
        batter, tac = best
        return Decision(batter, tac, f"expected-runs(dist): {best_why}")
    return play


def i17():
    pool_dist = sim._pitcher_power_distribution(sim.CARD_POOL)
    log_dist, meta = load_log_distribution()

    control_team = {"batting": make_expected_runs_play(pool_dist), "pitching": best_pitching_play}
    arm_team = {"batting": make_expected_runs_play(log_dist), "pitching": best_pitching_play}
    # CONTROL AGAINST CONTROL: the pool-distribution function must reproduce the
    # shipped expected_runs_play's cached-distribution behaviour exactly.
    shipped_team = sim.EXPECTED_RUNS  # {"batting": expected_runs_play, "pitching": best_pitching_play}

    reproduces = run_arm(control_team, sim.CURRENT)
    shipped = run_arm(shipped_team, sim.CURRENT)
    arm = run_arm(arm_team, sim.CURRENT)
    return {"pool_dist": pool_dist, "log_dist": log_dist, "meta": meta,
            "reproduces_shipped": reproduces, "shipped": shipped, "arm": arm}


def i17_decisions_changed(n=4000, seed=13):
    pool_dist = sim._pitcher_power_distribution(sim.CARD_POOL)
    log_dist, _ = load_log_distribution()
    pool_fn = make_expected_runs_play(pool_dist)
    log_fn = make_expected_runs_play(log_dist)
    random.seed(seed)
    changed = 0
    for _ in range(n):
        hand_players, hand_tactics = sim.draw_hand("batting")
        runners_empty = random.random() < 0.6
        runners = [] if runners_empty else [sim.CARD_POOL[random.randrange(len(sim.CARD_POOL))]]
        state = GameState(half="batting", batters_used=random.randrange(5), your_score=0,
                           opp_score=0, runners=runners)
        d1 = pool_fn(hand_players, hand_tactics, state)
        d2 = log_fn(hand_players, hand_tactics, state)
        if d1.player_card is not d2.player_card or d1.tactics_card is not d2.tactics_card:
            changed += 1
    return changed, n


# ---------------------------------------------------------------------------------------
def main():
    global N_MATCHES
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "i15", "i16", "i17", "decisions", "all"],
                     default="all")
    ap.add_argument("--n_matches", type=int, default=N_MATCHES)
    args = ap.parse_args()
    N_MATCHES = args.n_matches

    if args.arm in ("baseline", "all"):
        print(f"=== BASELINE: CURRENT vs ALWAYS_BOOST, {N_MATCHES} halves x {len(SEEDS)} seeds ===")
        b = baseline()
        print(fmt_row("baseline (CURRENT)", b))
        print()

    if args.arm in ("i15", "all"):
        print("=== I-15: card sequencing (hold best batter) ===")
        control, arm = i15()
        print(fmt_row("control (hold=False)", control))
        print(fmt_row("arm (hold=True)", arm, control))
        c, n = i15_decisions_changed()
        print(f"  decisions changed: {c}/{n} ({100*c/n:.1f}%) sampled hands where "
              f"hold picked a different card than the shipped scorer")
        print()

    if args.arm in ("i16", "all"):
        print("=== I-16: deck-aware discard threshold sweep ===")
        control, arms = i16()
        print(fmt_row("control (fixed threshold=6)", control))
        for t in I16_THRESHOLDS:
            print(fmt_row(f"arm (P(improve) > {t})", arms[t], control))
            c, considered = i16_decisions_changed(t)
            print(f"      decisions changed vs should_redraw: {c}/{considered} "
                  f"redraw-eligible hands sampled")
        print()

    if args.arm in ("i17", "all"):
        print("=== I-17: opponent model from the log vs from our own pool ===")
        res = i17()
        print(f"  pool-derived pitcher dist:  {res['pool_dist']}")
        print(f"  log-derived pitcher dist:   {res['log_dist']}")
        m = res["meta"]
        print(f"  log rows: total={m['total_rows_in_log']}  "
              f"with local reveal (outcome_basis/margin)={m['rows_with_outcome_basis_or_margin']}  "
              f"excluded={m['rows_excluded_no_local_reveal_read']}  "
              f"used (batting-phase, opp pitching)={m['n_used_for_distribution']}")
        print(fmt_row("shipped expected_runs_play vs CURRENT", res["shipped"]))
        print(fmt_row("reproduces_shipped (pool dist, refactored fn)", res["reproduces_shipped"],
                       res["shipped"]))
        print(fmt_row("arm (log dist) vs CURRENT", res["arm"], res["shipped"]))
        c, n = i17_decisions_changed()
        print(f"  decisions changed: {c}/{n} ({100*c/n:.1f}%) sampled hands where the log "
              f"distribution picked a different (card, tactics) than the pool distribution")
        print()


if __name__ == "__main__":
    main()
