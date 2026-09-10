"""THE FULL POWER/SPEED RATIO SWEEP: 100/0 through 0/100 in steps of 1.

The first attempt compared two CORNERS and read the loss as "speed loses" -- the user's
correction: the game is a hybrid, so the question is where on the spectrum the optimum sits.
A coarse 10-point sweep found a PLATEAU (w=0..0.5 indistinguishable, w>=1 a cliff). This is
the fine version, at every whole percent, with enough matches to resolve the plateau.

    score(batter, tactics) = (1-a) * effective_power + a * effective_speed

a = 0.00 is pure power (the incumbent's rule). a = 1.00 is pure speed.
"""
import os, sys, json, random, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball")
import simulate as s
from decision_engine import Decision, TacticsType

N = int(os.environ.get("N", "2000"))
SEEDS = tuple(range(int(os.environ.get("SEEDS", "5"))))


def ratio_play(a: float):
    def play(hand_players, hand_tactics, state) -> Decision:
        best, bs = None, None
        for batter in hand_players:
            for tac in [None] + list(hand_tactics):
                power = batter.power + s.power_bonus(tac)
                speed = (batter.secondary or 0)
                if tac is not None and tac.kind == TacticsType.SPEED_BOOST:
                    speed += tac.bonus
                sc = (1.0 - a) * power + a * speed
                if bs is None or sc > bs:
                    best, bs = (batter, tac), sc
        b, t = best
        return Decision(b, t, f"ratio a={a:.2f}")
    return play


def team(a):
    return {"batting": ratio_play(a), "pitching": s.best_pitching_play}


def score_vs(a, opponent, n=N, seeds=SEEDS):
    t = team(a); wins = []
    for sd in seeds:
        random.seed(sd); w = 0
        for _ in range(n):
            x, y = s.simulate_match(t, opponent)
            if x > y: w += 1
        wins.append(100.0 * w / n)
    return statistics.mean(wins), (statistics.stdev(wins) if len(wins) > 1 else 0.0)


if __name__ == "__main__":
    grid = [i / 100.0 for i in range(101)]
    print(f"# {len(grid)} ratios x {len(SEEDS)} seeds x {N} matches "
          f"= {len(grid)*len(SEEDS)*N:,} matches, vs naive always-boost", flush=True)
    rows = []
    for a in grid:
        m, sd = score_vs(a, s.ALWAYS_BOOST)
        rows.append({"a": a, "power_pct": round(100*(1-a)), "speed_pct": round(100*a),
                     "win": m, "sd": sd})
        print(f"  power {100*(1-a):3.0f} / speed {100*a:3.0f}   {m:6.2f}%  (sd {sd:.2f})", flush=True)
    json.dump(rows, open("agent_progress/ratio_sweep.json", "w"), indent=1)
    best = max(rows, key=lambda r: r["win"])
    top = [r for r in rows if r["win"] >= best["win"] - best["sd"]]
    print(f"\n  BEST: power {best['power_pct']} / speed {best['speed_pct']} at {best['win']:.2f}%")
    print(f"  within 1 sd of best: power {max(r['power_pct'] for r in top)}"
          f"..{min(r['power_pct'] for r in top)} / speed "
          f"{min(r['speed_pct'] for r in top)}..{max(r['speed_pct'] for r in top)}")
    print(f"  pure power (100/0) = {rows[0]['win']:.2f}%   pure speed (0/100) = {rows[-1]['win']:.2f}%")
