"""Offline analysis of match_log.jsonl — does `secondary` (fielding/speed) matter?

    python3 analyze_match_log.py [path] [--include-legacy]

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
6. LEGACY ROWS (I-18a). `outcome` was manufactured by the withdrawn "score went
   up" classifier on every row before `classify_outcome`/`outcome_basis` landed
   (CLAUDE.md section 4: "26 such rows ... all came from the old ... classifier").
   369 of 373 rows in match_log.jsonl have no `outcome_basis` at all; only 4
   (all 2026-09-20) carry one, in {"margin", "tie"}. So by default any OUTCOME
   statistic (the outcomes tally, the baseline, and anything scored against
   `u["outcome"]`) is computed over rows WITH `outcome_basis` only, and the
   count/reason of what was excluded is printed. `--include-legacy` puts the
   369 back, for anyone who wants the old (unreliable) behaviour.

   THIS DOES NOT TOUCH THE MARGIN/SECONDARY ANALYSIS BELOW. `effective_power`
   reads `*_power`, `*_tactics_bonus`, `*_tactics_kind` — the SAME local reader
   in every era (CLAUDE.md section 3) — never `outcome`, so `margin` and
   `secondary` are computed from ALL genuine rows regardless of `outcome_basis`
   and stay legacy-inclusive always. Excluding them too would throw away 369
   rows of a question they can still answer honestly.

No dependency on scipy: the p-value is a permutation test, which also avoids
assuming normality on tiny samples.
"""

import json
import random
import statistics
import sys
from collections import Counter

PERMUTATIONS = 20000
random.seed(20260826)


def has_outcome_basis(row):
    """True for a row `outcome`-based statistics may trust (I-18a)."""
    return bool(row.get("outcome_basis"))


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


def main(path=None, include_legacy=None):
    # RESOLVED AT CALL TIME, NOT IMPORT TIME (CLAUDE.md 10.18): a module-level
    # `LOG`/`INCLUDE_LEGACY` bound from sys.argv when the module loads cannot be
    # redirected by a caller in the same process, which is exactly the trap a
    # test needs this function NOT to have. `None` means "read argv now".
    if path is None:
        _positional = [a for a in sys.argv[1:] if not a.startswith("--")]
        path = _positional[0] if _positional else "match_log.jsonl"
    if include_legacy is None:
        include_legacy = "--include-legacy" in sys.argv

    rows, synthetic, bad = load(path)
    print(f"=== {path} ===")
    print(f"  {len(rows)} genuine rows"
          + (f", {synthetic} synthetic dropped" if synthetic else "")
          + (f", {bad} unparseable" if bad else ""))
    if not rows:
        return

    # --- I-18a: legacy rows (no outcome_basis) are excluded from OUTCOME
    # statistics by default. `rows` itself stays legacy-inclusive -- the
    # margin/secondary analysis below reads POWERS, not `outcome`, and powers
    # are read by the same local reader in every era (CLAUDE.md section 3), so
    # that half of the question is not degraded by this filter. -------------
    legacy = [r for r in rows if not has_outcome_basis(r)]
    outcome_rows = rows if include_legacy else [r for r in rows if has_outcome_basis(r)]
    if legacy:
        print(f"  {len(legacy)} legacy rows (no outcome_basis -- predate "
              f"classify_outcome, CLAUDE.md section 4) "
              + ("INCLUDED (--include-legacy)" if include_legacy else
                 "EXCLUDED from outcome statistics below (pass --include-legacy "
                 "to put them back). The margin/secondary analysis further down "
                 "still uses all rows: it is read from POWERS, not `outcome`."))

    phases = Counter(r.get("phase") for r in rows)
    print(f"  phases: {dict(phases)}")
    print(f"  outcomes (MANUFACTURED, not observed) over "
          f"{len(outcome_rows)} outcome-eligible rows: "
          f"{dict(Counter(r.get('outcome') for r in outcome_rows))}")

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
                       "phase": r["phase"], "outcome": r.get("outcome"),
                       "outcome_eligible": include_legacy or has_outcome_basis(r)})

    print(f"\n  usable for analysis (margin/secondary, powers-only, legacy "
          f"included): {len(usable)}/{len(rows)}")
    for k, v in reasons.most_common():
        print(f"    excluded {v:3d}: {k}")

    # --- the baseline, always -- OUTCOME-eligible rows only ----------------
    usable_outcome = [u for u in usable if u["outcome_eligible"]]
    if usable_outcome:
        oc = Counter(u["outcome"] for u in usable_outcome)
        top, n_top = oc.most_common(1)[0]
        print(f"\n  BASELINE (outcome-eligible rows only) — always predict "
              f"{top!r}: {n_top}/{len(usable_outcome)} "
              f"({100*n_top/len(usable_outcome):.0f}%). Any rule scoring below "
              "this is an artefact, not a finding.")

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
        # permutation_p needs >=2 on EACH side; `if not (_l and _h)` above only
        # checked non-empty, so a 1-vs-N split reached `{_p:.3f}` with _p None
        # and crashed -- found writing I-18a's own tiny-log test, unrelated to
        # outcome_basis but a real bug in the same function.
        _pstr = f"p={_p:.3f}" if _p is not None else "p=NOT COMPUTABLE (n<2 on a side)"
        print(f"    [{_ph}] sec==0 n={len(_l)} {statistics.mean(_l):+.2f} | "
              f"sec>0 n={len(_h)} {statistics.mean(_h):+.2f} | {_pstr}"
              + ("" if _p is not None and _p < 0.05 else "  <- nothing here"))

    _lop = [u["ours"] for u in usable if u["secondary"] == 0]
    _hip = [u["ours"] for u in usable if u["secondary"] > 0]
    if _lop and _hip:
        _pp = permutation_p(_lop, _hip)
        _ppstr = f"{_pp:.3f}" if _pp is not None else "NOT COMPUTABLE (n<2 on a side)"
        print(f"\n    CONFOUND CHECK — our own power by group: "
              f"sec==0 {statistics.mean(_lop):.2f} vs sec>0 {statistics.mean(_hip):.2f}"
              f" (p={_ppstr})")
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
