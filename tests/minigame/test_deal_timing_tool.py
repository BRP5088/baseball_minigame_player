"""The deal-timing analysis must find a real effect and REFUSE a fake one.

This tool decides whether base-movements predict the deal wait -- a question the
project has carried unanswered because the archived data is floor-censored. The
danger is not that it under-reports; it is that it reports a coefficient from
noise, and this project has shipped an invented constant before. So the checks
below are symmetric: a planted slope must come back, and everything that cannot
support a slope must come back as a REFUSAL with a reason, never as a number.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
os.environ["BASEBALL_TEST_RUN"] = "1"

import random
import deal_timing as dt

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


# The tool's own self-check: planted slope recovered, flat refused, thin refused,
# synthetic excluded. It asserts, so reaching the next line means it passed.
dt.selftest()
check(True, "the tool's selftest passes (planted slope recovered, fakes refused)")

rng = random.Random(11)

# --- a REAL effect must be found, with its sign ------------------------------
planted = [{"predicted_bases": b, "settled_at": 1.0 + 0.25 * b + rng.gauss(0, 0.08)}
           for b in list(range(11)) * 3]
f = dt.fit(planted)
check(f["slope"] is not None and abs(f["slope"] - 0.25) < 0.05,
      f"a planted 0.25 s/base came back as {f['slope']}")
check(f["p"] < 0.01, f"a planted effect scored p={f['p']} — the test is not sensitive")

# --- NOISE must not become a coefficient -------------------------------------
# The failure that matters. 40 rows of pure noise: a slope will be non-zero by
# chance, and the p-value is the only thing standing between that and a constant
# getting written into the gate.
noise = [{"predicted_bases": rng.choice(range(11)), "settled_at": rng.gauss(2.0, 0.6)}
         for _ in range(40)]
fn = dt.fit(noise)
check(fn["p"] is not None and fn["p"] > 0.05,
      f"pure noise scored p={fn['p']} — at p<=0.05 the tool would report a "
      "seconds-per-base coefficient fitted from nothing")

# --- and every refusal must SAY WHY, not return a silent None ----------------
thin = [{"predicted_bases": b, "settled_at": 1.0 + b} for b in range(4)]
ft = dt.fit(thin)
check(ft["slope"] is None and ft["refusal"] and "usable rows" in ft["refusal"],
      f"a 4-row set: slope={ft['slope']} refusal={ft['refusal']!r}")

one_x = [{"predicted_bases": 3, "settled_at": 1.0 + rng.gauss(0, 0.1)} for _ in range(30)]
fo = dt.fit(one_x)
check(fo["slope"] is None and fo["refusal"] and "distinct" in fo["refusal"],
      f"30 rows at ONE x value: slope={fo['slope']} refusal={fo['refusal']!r}")

# --- rows that cannot contribute are COUNTED, not silently dropped -----------
# An n that quietly excludes half its input is how a rate becomes a lie
# (CLAUDE.md 10.22: report how many samples were excluded, never just the rate).
mixed = planted + [{"predicted_bases": None, "settled_at": 2.0}] * 5 \
                + [{"predicted_bases": 4, "settled_at": None}] * 7
fm = dt.fit(mixed)
check(fm["no_prediction"] == 5 and fm["no_settled_at"] == 7
      and fm["usable"] == len(planted),
      f"excluded rows are not reported: {fm['no_prediction']=} {fm['no_settled_at']=} "
      f"{fm['usable']=} of {fm['rows']=}")

# --- the BOUNDS are the x-axis when no single prediction exists --------------
# predicted_bases was never passed in production -- the one call site is
# wait_for_hand_deal(baseline=pop_hand_baseline()) -- so every real row would have
# had no x at all and this tool would have refused forever, however many matches
# were played. The gate now records the bounds bases_to_travel can produce, because
# the margin that would collapse them to one number is not known until the reveal.
bounded = [{"bases_lo": b, "bases_hi": b + 2,
            "settled_at": 1.0 + 0.25 * (b + 1) + rng.gauss(0, 0.08)}
           for b in list(range(9)) * 4]
fb = dt.fit(bounded)
check(fb["usable"] == len(bounded) and fb["x_from"] == ["bounds midpoint"],
      f"rows with only bounds were unusable: {fb['usable']}/{len(bounded)} "
      f"x_from={fb['x_from']}")
check(fb["slope"] is not None and fb["p"] < 0.01,
      f"a planted effect expressed through the BOUNDS was not found: {fb['slope']}, "
      f"p={fb['p']}")
_x, _src = dt.x_of({"predicted_bases": 6, "bases_lo": 0, "bases_hi": 10})
check(_x == 6 and _src == "predicted_bases",
      f"an exact prediction must win over the bounds midpoint, got {_x} from {_src}")

# --- a REUSED diamond must be dropped, and counted ---------------------------
# The stash is popped only when the gate RUNS, and the gate does not always run:
# play_one_turn raising does `continue`, and a refused play leaves the diamond in
# place, so the NEXT turn's row describes an at-bat that never happened. The gate
# stamps a sequence number so that is visible instead of silently mislabelling.
dupes = ([{"play_seq": 1, "bases_lo": 0, "bases_hi": 2, "settled_at": 1.0}] * 3
         + [{"play_seq": 2, "bases_lo": 4, "bases_hi": 6, "settled_at": 2.0}])
kept, dropped = dt.dedupe(dupes)
check(len(kept) == 2 and dropped == 2,
      f"a reused diamond was not dropped: kept {len(kept)}, dropped {dropped}")
check(dt.fit(dupes)["reused_diamond"] == 2,
      "fit() does not report how many rows carried a reused diamond — an n that "
      "quietly excludes rows is how a rate becomes a lie")
# rows with NO seq (older rows, or a gate that never stashed) must survive
_noseq, _d2 = dt.dedupe([{"settled_at": 1.0}] * 5)
check(len(_noseq) == 5 and _d2 == 0,
      f"rows without a play_seq were dropped as duplicates: kept {len(_noseq)}")

# --- the permutation test must be deterministic across runs ------------------
# A p-value that wanders run to run cannot be quoted in a finding.
#
# ON THE NOISE SET, NOT THE PLANTED ONE. The first version of this check used
# `planted`, where the effect is so strong that ZERO of the 10,000 permutations
# ever beat it -- so p is pinned at its floor 1/10001 whatever the seed, and the
# check passed even with the seed removed entirely. A mutant proved it. The
# quantity has to be one that actually varies before equality means anything.
_p1 = dt.fit(noise, seed=99)["p"]
_p2 = dt.fit(noise, seed=99)["p"]
_p3 = dt.fit(noise, seed=1234)["p"]
check(0.0 < _p1 < 1.0,
      f"the reproducibility check is running on a SATURATED p-value ({_p1}); equality "
      "would hold with no seed at all and prove nothing")
check(_p1 == _p2, f"same seed gave different p-values: {_p1} vs {_p2}")
check(_p1 != _p3,
      f"seeds 99 and 1234 gave p={_p1} and p={_p3}; identical would mean the seed never "
      "reaches the shuffle, which makes the equality check above vacuous")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)
