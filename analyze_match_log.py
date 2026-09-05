"""Offline analysis of match_log.jsonl — does `secondary` (fielding/speed) matter?

    python3 analyze_match_log.py [path]

This is the question the whole log exists to answer, and it is still open. The
script exists so that answering it is a command rather than a research project,
and so the SAME caveats get applied every time instead of being rediscovered.

WHAT IT ENCODES (each of these was a mistake made once already)
--------------------------------------------------------------
1. `outcome` is MANUFACTURED, not observed. orchestrator infers it from deltas:
   home_run if the score rose, hit if the runner count rose, else out. Its error
   is one-directional — an RBI single that scores a runner looks like a home run,
   and a hit whose runner wasn't detected looks like an out. So `outcome` is
   reported but never used as ground truth for a p-value.
2. The PITCHING half must be flipped. On those rows we are the pitcher, the
   opponent is batting, and the outcome is scored off `opp_score`. Comparing raw
   margins across halves without flipping mixes two opposite signs.
3. Effective power needs the tactics TYPE, not just the bonus: only
   SWING_BOOST/PITCH_BOOST add power (simulate.py power_bonus). Rows predating
   `our_tactics_kind` cannot be corrected and are excluded, not guessed at.
4. Synthetic rows (`_synthetic: true`) are dropped. 30 of 69 rows were once test
   fixtures indistinguishable from real ones.
5. A baseline is always printed. A "discovered" rule that scores below the
   trivial always-out baseline is an artefact, and one such rule was believed
   for a while.

No dependency on scipy: the p-value is a permutation test, which also avoids
assuming normality on tiny samples.
"""

import json
import random
import statistics
import sys
from collections import Counter

LOG = sys.argv[1] if len(sys.argv) > 1 else "match_log.jsonl"
PERMUTATIONS = 20000
random.seed(20260826)


def load(path):
    rows, synthetic, bad = [], 0, 0
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if r.get("_synthetic"):
                    synthetic += 1
                    continue
                rows.append(r)
    except FileNotFoundError:
        print(f"{path} not found."); sys.exit(1)
    return rows, synthetic, bad


def effective_power(row, side):
    """Power actually brought to the matchup, or None if uncomputable."""
    p = row.get(f"{side}_power")
    if not isinstance(p, int):
        return None
    bonus = row.get(f"{side}_tactics_bonus", 0) or 0
    if not bonus:
        return p
    kind = row.get(f"{side}_tactics_kind")
    if kind is None:
        return None                     # bonus with unknown type: uncomputable
    return p + bonus if kind in ("swing_boost", "pitch_boost") else p


def permutation_p(a, b, n=PERMUTATIONS):
    """Two-sided p for a difference in means. No scipy, no normality assumption."""
    if len(a) < 2 or len(b) < 2:
        return None
    obs = abs(statistics.mean(a) - statistics.mean(b))
    pool = list(a) + list(b)
    k = len(a)
    hits = 0
    for _ in range(n):
        random.shuffle(pool)
        if abs(statistics.mean(pool[:k]) - statistics.mean(pool[k:])) >= obs:
            hits += 1
    return (hits + 1) / (n + 1)


def main():
    rows, synthetic, bad = load(LOG)
    print(f"=== {LOG} ===")
    print(f"  {len(rows)} genuine rows"
          + (f", {synthetic} synthetic dropped" if synthetic else "")
          + (f", {bad} unparseable" if bad else ""))
    if not rows:
        return

    phases = Counter(r.get("phase") for r in rows)
    print(f"  phases: {dict(phases)}")
    print(f"  outcomes (MANUFACTURED, not observed): "
          f"{dict(Counter(r.get('outcome') for r in rows))}")

    # --- usability accounting: say what is unusable and why ---------------
    usable, reasons = [], Counter()
    for r in rows:
        ours = effective_power(r, "our")
        theirs = effective_power(r, "opp")
        if ours is None:
            reasons["our effective power uncomputable (tactics kind missing)"] += 1
            continue
        if theirs is None:
            reasons["opponent card not captured / kind missing"] += 1
            continue
        if r.get("phase") not in ("batting", "pitching"):
            reasons["phase missing"] += 1
            continue
        # Flip on the pitching half: there the OPPONENT is batting.
        margin = ours - theirs if r["phase"] == "batting" else theirs - ours
        # ALWAYS ours, both halves — the ternary that used to be here had two
        # identical branches, which read like a flip that never happened.
        # It is deliberate: batting, our secondary is the batter's speed;
        # pitching, it is our pitcher's fielding. Both are the stat under test.
        sec = r.get("our_secondary")
        if not isinstance(sec, int):
            reasons["secondary missing"] += 1
            continue
        usable.append({"margin": margin, "secondary": sec, "ours": ours,
                       "phase": r["phase"], "outcome": r.get("outcome")})

    print(f"\n  usable for analysis: {len(usable)}/{len(rows)}")
    for k, v in reasons.most_common():
        print(f"    excluded {v:3d}: {k}")

    # --- the baseline, always ---------------------------------------------
    if usable:
        oc = Counter(u["outcome"] for u in usable)
        top, n_top = oc.most_common(1)[0]
        print(f"\n  BASELINE — always predict {top!r}: {n_top}/{len(usable)} "
              f"({100*n_top/len(usable):.0f}%). Any rule scoring below this is "
              "an artefact, not a finding.")

    # --- the actual question ----------------------------------------------
    print("\n  DOES `secondary` AFFECT THE MARGIN NEEDED?")
    lo = [u["margin"] for u in usable if u["secondary"] == 0]
    hi = [u["margin"] for u in usable if u["secondary"] > 0]
    print(f"    secondary == 0 : n={len(lo)}"
          + (f", mean margin {statistics.mean(lo):+.2f}" if lo else ""))
    print(f"    secondary >  0 : n={len(hi)}"
          + (f", mean margin {statistics.mean(hi):+.2f}" if hi else ""))
    p = permutation_p(lo, hi)
    if p is None:
        print("    p-value: NOT COMPUTABLE — need at least 2 rows on each side.")
    else:
        print(f"    permutation p = {p:.3f}"
              + ("  <- significant at 0.05" if p < 0.05
                 else "  <- CANNOT CONCLUDE"))

    # --- the two ways this result lies ------------------------------------
    # Both were live on 2026-08-31, when the pooled figure first crossed 0.05
    # at p=0.006 and neither survived a look:
    #
    #   1. ONE HALF ONLY. Batting p=0.008, pitching p=1.00 (means -0.70 vs
    #      -0.78). Pooling them reported a whole-game effect that existed on
    #      one side of the ball. FIELDING_POWER_BUDGET is about the PITCHING
    #      half specifically, so the pooled number was answering a different
    #      question than the one being asked of it.
    #
    #   2. POWER CONFOUND. Batting rows with secondary>0 also averaged 8.23
    #      power against 7.22 — the margin gap is partly just stronger cards.
    #      The opponent's power drifted too (7.00 -> 6.05), and OUR batter's
    #      speed cannot cause the opponent to draw weaker pitchers, so that
    #      part is noise proving the split is not clean.
    #
    # Neither needs a statistician to spot, but both need someone to LOOK.
    # Printed every run so nobody has to remember to.
    for _ph in ("batting", "pitching"):
        _sub = [u for u in usable if u["phase"] == _ph]
        _l = [u["margin"] for u in _sub if u["secondary"] == 0]
        _h = [u["margin"] for u in _sub if u["secondary"] > 0]
        if not (_l and _h):
            print(f"    [{_ph}] n={len(_sub)} — not enough on both sides to split")
            continue
        _p = permutation_p(_l, _h)
        print(f"    [{_ph}] sec==0 n={len(_l)} {statistics.mean(_l):+.2f} | "
              f"sec>0 n={len(_h)} {statistics.mean(_h):+.2f} | p={_p:.3f}"
              + ("" if _p < 0.05 else "  <- nothing here"))

    _lop = [u["ours"] for u in usable if u["secondary"] == 0]
    _hip = [u["ours"] for u in usable if u["secondary"] > 0]
    if _lop and _hip:
        _pp = permutation_p(_lop, _hip)
        print(f"\n    CONFOUND CHECK — our own power by group: "
              f"sec==0 {statistics.mean(_lop):.2f} vs sec>0 {statistics.mean(_hip):.2f}"
              f" (p={_pp:.3f})")
        if _pp is not None and _pp < 0.20:
            print("      ^ the groups differ in RAW POWER too, so any margin "
                  "gap is partly just stronger cards. Not a clean test.")

    # --- how much more data would settle it -------------------------------
    if lo and hi and len(usable) >= 4:
        d = abs(statistics.mean(hi) - statistics.mean(lo))
        pooled = statistics.pstdev([u["margin"] for u in usable]) or 1.0
        eff = d / pooled
        need = int(16 / (eff ** 2)) if eff > 0.01 else 99999
        print(f"\n    observed effect size {eff:.2f} sd; roughly {need} usable rows "
              f"per group would be needed to detect it at 80% power.")
        rate = len(usable) / max(1, len(rows))
        print(f"    at the current {100*rate:.0f}% usable rate that is about "
              f"{int(2*need/max(rate,0.01))} logged turns "
              f"(~{int(2*need/max(rate,0.01)/18)} matches).")


if __name__ == "__main__":
    main()
