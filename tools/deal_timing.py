"""Does the number of base-movements predict how long the deal takes?

THE QUESTION THIS EXISTS FOR. bases_to_travel counts BASE-MOVEMENTS for a play
(0 for a routine out with empty bases, 10 for a bases-loaded home run) and the
theory is that more movements means more animation means a longer wait before
the hand is readable. That theory has never been tested: until 2026-09-13 the
prediction was PRINTED and changed no delay, and no run had ever produced the
line, so the dataset was empty rather than thin.

It still changes no delay. This reads the rows and says whether the effect is
there -- and REFUSES to report a coefficient it cannot support, because an
invented seconds-per-base is the same bug wearing a fix's clothes.

NEITHER COLUMN CURRENTLY CARRIES THE SIGNAL, AND THAT IS THE FIRST THING TO FIX.
An earlier version of this docstring said "settled_at is the floor-free probe:
when the hand actually stopped changing... regress on settled_at". That was
written confidently and it is FALSE. Measured over the 31 archived
`hand first settled at` lines in overnight/:

    settled_at   min 0.70   p50 0.90   max 2.30      29 of 31 at or under 1.5 s
    released     min 3.60   p50 4.20   max 9.50
    pearson(settled_at, released) = 0.226

settled_at is pinned near the probe's own physical minimum -- two polls plus a
read_hand each -- because the probe runs from the FIRST poll with no edge
requirement, and by the time the gate starts the hand has already moved a median
53.5 from its at-the-play state (the gate's own comment records this). It locks
onto the pre-deal fan, already static. It does not measure the deal.

`waited` is no better: it is floor + ~0.6 s on nearly every turn (24 of 32 rows
at floor 3.0 released exactly 0.60 s past it), i.e. "the floor expired, two polls,
go". Neither quantity varies with animation length.

So this tool will correctly report NO EFFECT on today's rows, and that verdict
would be an artefact of the instrument, not a fact about the game. It prints the
correlation above every run so the artefact cannot be mistaken for a finding.
Fixing the instrument -- measuring from the deal's own onset rather than from the
gate's first poll -- comes before believing any slope this produces.

    .venv/bin/python -B tools/deal_timing.py [path/to/deal_timing.jsonl]
    .venv/bin/python -B tools/deal_timing.py --selftest
"""
import json
import os
import random
import sys

# Enough rows that a slope is worth quoting at all. Not a significance
# threshold -- the permutation test below does that -- just a floor under
# "this is a number, not an anecdote". CLAUDE.md 10.3: n=3 cannot detect the
# effects this project looks for; n=10 has power 0.94 for a 1-sigma effect.
MIN_ROWS = 12
MIN_DISTINCT_X = 3          # a slope through one or two x values is not a slope
PERMUTATIONS = 10000


def load(path):
    """Rows from the JSONL, SYNTHETIC ONES EXCLUDED and counted.

    Test rows are stamped `_synthetic` (log_matchup's convention, inherited).
    Silently mixing them into a live dataset is how 30 fabricated rows reached
    match_log.jsonl; silently DROPPING them without saying so is how an n
    becomes a lie. Both counts are returned.
    """
    rows, synthetic, malformed = [], 0, 0
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                malformed += 1
                continue
            if r.get("_synthetic"):
                synthetic += 1
            else:
                rows.append(r)
    return rows, synthetic, malformed


def x_of(row):
    """(prediction, which field it came from) for one row, or (None, None).

    A single predicted_bases does not exist at the moment of the play: bases_to_travel
    needs the MARGIN, and the margin is only known at the reveal. So the gate records
    the BOUNDS the outcome must fall between, and the midpoint is the best single
    number available without a join to match_log.jsonl -- which has no shared key
    (both sides carry only a second-resolution ts, written seconds apart). The field
    used is reported every run so nobody mistakes the midpoint for the truth.
    """
    v = row.get("predicted_bases")
    if isinstance(v, (int, float)):
        return v, "predicted_bases"
    lo, hi = row.get("bases_lo"), row.get("bases_hi")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return (lo + hi) / 2.0, "bounds midpoint"
    return None, None


def dedupe(rows):
    """Drop rows whose diamond was REUSED, and say how many.

    The stash is popped only WHEN THE GATE RUNS, and the gate does not always run --
    play_one_turn raising does `continue`, and a refused play leaves the diamond in
    place. The next gate then consumes a diamond describing an at-bat that never
    happened. stash_deal_inputs stamps a sequence number so that is visible here
    instead of silently mislabelling a row.
    """
    seen, kept, dropped = set(), [], 0
    for r in rows:
        q = r.get("play_seq")
        if q is not None and q in seen:
            dropped += 1
            continue
        if q is not None:
            seen.add(q)
        kept.append(r)
    return kept, dropped


def _slope(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def fit(rows, seed=12345):
    """Slope of settled_at on predicted_bases, with a permutation p-value.

    Permutation rather than a t-test: no distributional assumption, no scipy,
    and it is the same instrument the project uses elsewhere. Returns None for
    `slope` when the data cannot support one, and SAYS WHY in `refusal`.
    """
    rows, reused = dedupe(rows)
    usable, sources = [], set()
    for r in rows:
        x, src = x_of(r)
        if x is not None and isinstance(r.get("settled_at"), (int, float)):
            usable.append((x, r["settled_at"]))
            sources.add(src)
    out = {
        "rows": len(rows),
        "usable": len(usable),
        "reused_diamond": reused,
        "x_from": sorted(sources),
        "no_prediction": sum(1 for r in rows if x_of(r)[0] is None),
        "no_settled_at": sum(1 for r in rows if r.get("settled_at") is None),
        "slope": None, "p": None, "refusal": None,
    }
    if len(usable) < MIN_ROWS:
        out["refusal"] = (f"only {len(usable)} usable rows (need {MIN_ROWS}). "
                          "A slope from fewer is an anecdote.")
        return out
    xs = [x for x, _ in usable]
    ys = [y for _, y in usable]
    if len(set(xs)) < MIN_DISTINCT_X:
        out["refusal"] = (f"predicted_bases takes only {len(set(xs))} distinct value(s) "
                          f"(need {MIN_DISTINCT_X}). A line through that is not a slope.")
        return out
    obs = _slope(xs, ys)
    if obs is None:
        out["refusal"] = "predicted_bases has zero variance"
        return out
    rng = random.Random(seed)
    shuffled = list(ys)
    hits = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(shuffled)
        s = _slope(xs, shuffled)
        if s is not None and abs(s) >= abs(obs):
            hits += 1
    out["slope"] = obs
    out["p"] = (hits + 1) / (PERMUTATIONS + 1)
    return out


def censoring(rows):
    """How much of `waited` the floor is hiding -- the reason the archive was useless."""
    at_floor = sum(1 for r in rows
                   if isinstance(r.get("waited"), (int, float))
                   and isinstance(r.get("floor"), (int, float))
                   and r["waited"] - r["floor"] <= 0.35)
    held = [round(r["waited"] - r["settled_at"], 2) for r in rows
            if isinstance(r.get("waited"), (int, float))
            and isinstance(r.get("settled_at"), (int, float))]
    held.sort()
    return {"at_floor": at_floor, "n": len(rows),
            "median_held": held[len(held) // 2] if held else None}


def instrument_health(rows):
    """Is settled_at measuring the deal at all?

    The check that would have stopped this tool being trusted. If settled_at
    barely correlates with the release it is pinned at the probe's own minimum,
    which is what the archive shows today (r = 0.226, 29 of 31 at or under
    1.5 s). A slope fitted on a pinned column is a fact about the probe.
    """
    pairs = [(r["settled_at"], r["waited"]) for r in rows
             if isinstance(r.get("settled_at"), (int, float))
             and isinstance(r.get("waited"), (int, float))]
    if len(pairs) < 5:
        return {"r": None, "n": len(pairs), "pinned": 0}
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = ((sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5)
    r = None if den == 0 else sum((a - mx) * (b - my)
                                  for a, b in zip(xs, ys)) / den
    return {"r": r, "n": len(pairs), "pinned": sum(1 for a in xs if a <= 1.5)}


def report(path):
    rows, synthetic, malformed = load(path)
    print(f"{path}: {len(rows)} live rows ({synthetic} synthetic excluded, "
          f"{malformed} malformed)")
    if not rows:
        print("  nothing to report — play some matches first")
        return 0
    by = {}
    for r in rows:
        by[r.get("outcome")] = by.get(r.get("outcome"), 0) + 1
    print(f"  by outcome: {by}")

    c = censoring(rows)
    print(f"  the floor held the gate a median {c['median_held']}s past the settle; "
          f"{c['at_floor']}/{c['n']} released within 0.35s of the floor")
    inst = instrument_health(rows)
    if inst["r"] is not None:
        print(f"  INSTRUMENT CHECK: pearson(settled_at, released) = {inst['r']:+.3f}, "
              f"{inst['pinned']}/{inst['n']} settled_at values at or under 1.5s")
        if abs(inst["r"]) < 0.5 or inst["pinned"] > 0.7 * inst["n"]:
            print("  -> settled_at is NOT tracking the release. It is measuring the "
                  "pre-deal fan, not the deal. Any slope below is about the instrument.")

    rows, _reused = dedupe(rows)
    if _reused:
        print(f"  {_reused} row(s) dropped: their diamond was REUSED from an earlier "
              "play whose gate never ran")
    groups = {}
    for r in rows:
        x, _src = x_of(r)
        y = r.get("settled_at")
        if x is not None and isinstance(y, (int, float)):
            groups.setdefault(x, []).append(y)
    if groups:
        print("  settled_at by predicted base-movements:")
        for x in sorted(groups):
            ys = sorted(groups[x])
            print(f"    {x:>3} bases  n={len(ys):<4} median {ys[len(ys)//2]:.2f}s  "
                  f"[{ys[0]:.2f}..{ys[-1]:.2f}]")

    f = fit(rows)
    print(f"  usable {f['usable']} of {f['rows']} "
          f"({f['no_prediction']} lack a prediction, {f['no_settled_at']} never settled)"
          + (f", x from {'/'.join(f['x_from'])}" if f["x_from"] else ""))
    if f["refusal"]:
        print(f"  NO COEFFICIENT: {f['refusal']}")
    else:
        print(f"  slope {f['slope']:+.4f} s per base-movement, permutation p = {f['p']:.4f}")
        if f["p"] > 0.05:
            print("  -> NOT significant. The prediction does not measurably move the wait.")
        else:
            print("  -> significant. Worth wiring into the gate's floor/ceiling.")
    return 0


def selftest():
    """A known slope must come back, and a flat set must be refused."""
    import tempfile
    rng = random.Random(7)
    # planted: 0.30 s per base, noise well under the effect
    planted = [{"predicted_bases": b, "settled_at": 1.0 + 0.30 * b + rng.gauss(0, 0.05),
                "waited": 3.0, "floor": 3.0, "outcome": "stable"}
               for b in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 3]
    f = fit(planted)
    assert f["slope"] is not None, f
    assert abs(f["slope"] - 0.30) < 0.05, f["slope"]
    assert f["p"] < 0.01, f["p"]

    flat = [{"predicted_bases": b, "settled_at": 2.0 + rng.gauss(0, 0.5),
             "waited": 3.0, "floor": 3.0, "outcome": "stable"}
            for b in [0, 1, 2, 3, 4, 5] * 6]
    f2 = fit(flat)
    assert f2["p"] > 0.05, f2          # no effect planted, none found
    # and it REFUSES rather than fitting noise
    assert fit(planted[:4])["slope"] is None
    assert fit([{"predicted_bases": 2, "settled_at": 1.0}] * 20)["slope"] is None

    fd, p = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for r in planted:
            fh.write(json.dumps(r) + "\n")
        fh.write(json.dumps({"predicted_bases": 99, "settled_at": 99.0,
                             "_synthetic": True}) + "\n")
    rows, syn, bad = load(p)
    os.unlink(p)
    assert len(rows) == len(planted) and syn == 1 and bad == 0, (len(rows), syn, bad)
    print("selftest: planted slope recovered, flat set refused, thin set refused, "
          "synthetic rows excluded and counted")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    arg = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = arg[0] if arg else (os.environ.get("BASEBALL_DEAL_LOG") or "deal_timing.jsonl")
    if not os.path.exists(path):
        print(f"{path} does not exist yet — no deal has been recorded. "
              "Play a match with the runner and this fills in.")
        raise SystemExit(0)
    raise SystemExit(report(path))
