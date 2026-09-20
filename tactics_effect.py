#!/usr/bin/env python3
"""Do SPEED and FIELDING tactics affect the outcome at all?

    .venv/bin/python tactics_effect.py [match_log.jsonl] [--include-legacy]

The game's rule (CLAUDE.md): only SWING_BOOST and PITCH_BOOST add power. Speed
and fielding boosts carry a nonzero bonus that adds NO power. So the question
this answers is whether they help through some OTHER channel, or not at all.

It reuses analyze_match_log's load(), effective_power() and permutation_p()
rather than reimplementing them — effective_power already encodes the
kind-vs-bonus rule, and getting that wrong is the whole trap.

IT REFUSES TO PRODUCE A P-VALUE IT CANNOT SUPPORT. On the log as of
2026-09-03 there are 3 speed_boost and 2 fielding_boost rows out of 143, and
39 rows have no tactics_kind at all. A p-value on n=2 is not a weak result, it
is not a result, and printing one invites exactly the confident wrong finding
this project keeps producing.

I-18a: EVERY ROW HERE IS SCORED ON `outcome`, so this whole script is an
outcome statistic — unlike analyze_match_log.py, there is no powers-only half
to keep. By default rows with no `outcome_basis` (the withdrawn "score went
up" classifier's output, CLAUDE.md section 4) are dropped before anything
else runs; `--include-legacy` puts them back for the old (unreliable) reading.
On match_log.jsonl as of 2026-09-20 that is 369 of 373 rows, so every arm
prints INSUFFICIENT by default — which is the honest answer, not a bug: this
script cannot yet support a win-rate p-value on real evidence, and reporting
one built on the old classifier would be the exact mistake OPEN-24/I-18 exists
to stop repeating.
"""
import collections
import json
import sys

import analyze_match_log as aml

MIN_N = 8          # per arm, below which no p-value is reported
WIN = ("hit", "home_run")


def win_rate(rows):
    if not rows:
        return None
    return sum(1 for r in rows if r.get("outcome") in WIN) / len(rows)


def main(path="match_log.jsonl", include_legacy=False):
    rows, synthetic, bad = aml.load(path)
    print(f"{len(rows)} rows  ({synthetic} synthetic skipped, {bad} unparseable)\n")

    legacy = [r for r in rows if not aml.has_outcome_basis(r)]
    if legacy:
        if include_legacy:
            print(f"{len(legacy)} legacy rows (no outcome_basis) INCLUDED "
                  f"(--include-legacy) -- every win rate below is the OLD, "
                  f"unreliable 'score went up' classifier's opinion.\n")
        else:
            rows = [r for r in rows if aml.has_outcome_basis(r)]
            print(f"{len(legacy)} legacy rows (no outcome_basis -- predate "
                  f"classify_outcome, CLAUDE.md section 4) EXCLUDED; "
                  f"{len(rows)} outcome-eligible rows remain (pass "
                  f"--include-legacy to put them back).\n")

    kinds = collections.Counter(r.get("our_tactics_kind") for r in rows)
    missing = kinds.get(None, 0)
    print("our_tactics_kind coverage:")
    for k, n in kinds.most_common():
        print(f"  {str(k):16} {n:4}")
    if missing:
        print(f"\n  {missing} of {len(rows)} rows have NO tactics_kind. Those "
              f"cannot be attributed to any tactic and are excluded, not\n"
              f"  treated as 'no tactic' — a bonus with an unknown type is "
              f"uncomputable, not zero.")

    known = [r for r in rows if r.get("our_tactics_kind") is not None]

    print(f"\n{'tactic':16} {'n':>4} {'win rate':>9} {'baseline':>9} "
          f"{'diff':>7} {'p':>8}")
    print("-" * 60)
    verdicts = {}
    for kind in ("speed_boost", "fielding_boost", "swing_boost", "pitch_boost"):
        arm = [r for r in known if r.get("our_tactics_kind") == kind]
        others = [r for r in known if r.get("our_tactics_kind") != kind]
        wr, base = win_rate(arm), win_rate(others)
        n = len(arm)
        if n < MIN_N or len(others) < MIN_N:
            print(f"{kind:16} {n:4} {'--':>9} {'--':>9} {'--':>7} "
                  f"{'INSUFFICIENT':>8}")
            verdicts[kind] = {"n": n, "verdict": "insufficient data",
                              "compared_against": len(others)}
            continue
        a = [1.0 if r.get("outcome") in WIN else 0.0 for r in arm]
        b = [1.0 if r.get("outcome") in WIN else 0.0 for r in others]
        p = aml.permutation_p(a, b)
        print(f"{kind:16} {n:4} {wr:9.3f} {base:9.3f} {wr - base:+7.3f} "
              f"{p:8.4f}")
        verdicts[kind] = {"n": n, "win_rate": wr, "baseline": base, "p": p,
                          "compared_against": len(others)}

    print(f"\nMIN_N = {MIN_N} per arm. Anything below it prints INSUFFICIENT "
          f"rather than a number:\na p-value on two samples is not a weak "
          f"result, it is not a result.")

    thin = [k for k, v in verdicts.items() if v.get("verdict")]
    if thin:
        print(f"\nTO ANSWER THIS TOMORROW, farm matches that actually PLAY "
              f"these tactics:\n  " + ", ".join(thin) +
              f"\n  Each needs >= {MIN_N} rows; the binomial noise floor on a "
              f"~0.4 win rate means\n  a real 10-point effect needs roughly 100 "
              f"per arm to separate from chance.")
    return verdicts


if __name__ == "__main__":
    _include_legacy = "--include-legacy" in sys.argv
    _positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(_positional[0] if _positional else "match_log.jsonl",
         include_legacy=_include_legacy)
