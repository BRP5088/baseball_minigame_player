"""Is a claimed streak real? Check a batch result against its own evidence.

WHY THIS EXISTS. The target is 25 consecutive arrivals at the dealer's prompt,
and `at_table()` is both the arrival authority AND the gate that spends $50, so
a streak claim has to be checkable rather than asserted. This project has
already recorded one streak wrongly: OPEN-14's harness printed 2 of 3 and a
best streak of 2, and one of those "arrivals" was `identify()` naming a POSE it
must never name, with the independent re-read 0.8 s later saying False.

WHAT IT CHECKS, per trial:
  - outcome ARRIVED and arrived True agree;
  - `at_table_recheck` -- a SECOND at_table() 0.8 s after the verdict, recorded
    beside it and never used to score -- also says True. A verdict that holds on
    one frame and not on the next one is a marginal call, not an arrival;
  - the walk ended near the chain's end rather than somewhere odd;
  - the run's own flags are recorded, so the streak names the build it was made
    on (10.7: a result and the change that invalidates it once shared a commit).

It reports the LONGEST RUN OF CONSECUTIVE TRIALS that pass every check, which is
not the same as the count of arrivals, and prints every trial that breaks one.

    .venv/bin/python -B tools/verify_streak.py overnight/chain_trials.json
    .venv/bin/python -B tools/verify_streak.py --selftest
"""
import json
import sys


def audit(d):
    """-> (rows, longest_clean_run). A row is (trial, ok, [complaints])."""
    rows = []
    for r in d.get("runs", []):
        bad = []
        if r.get("outcome") != "ARRIVED":
            bad.append(f"outcome {r.get('outcome')}")
        if not r.get("arrived"):
            bad.append("arrived False")
        rc = r.get("at_table_recheck")
        if rc is not True:
            bad.append(f"recheck {rc!r} — the prompt did not hold 0.8 s later")
        k, n = r.get("k_final"), r.get("waypoints")
        if isinstance(k, int) and isinstance(n, int) and n and k < n - 12:
            bad.append(f"ended at waypoint {k} of {n}")
        rows.append((r.get("trial"), not bad, bad))
    best = run = 0
    for _, ok, _ in rows:
        run = run + 1 if ok else 0
        best = max(best, run)
    return rows, best


def selftest():
    good = lambda t: {"trial": t, "outcome": "ARRIVED", "arrived": True,
                      "at_table_recheck": True, "k_final": 200, "waypoints": 205}
    rows, best = audit({"runs": [good(1), good(2), good(3)]})
    assert best == 3 and all(ok for _, ok, _ in rows), rows
    # a recheck that says False BREAKS the streak even though the harness scored
    # it ARRIVED -- the whole reason this file exists
    bad = dict(good(2), at_table_recheck=False)
    rows, best = audit({"runs": [good(1), bad, good(3), good(4)]})
    assert best == 2, (rows, best)
    assert any("did not hold" in c for _, _, cs in rows for c in cs)
    # ...and a missing recheck is not a pass
    missing = {k: v for k, v in good(1).items() if k != "at_table_recheck"}
    rows, best = audit({"runs": [missing]})
    assert best == 0, rows
    rows, best = audit({"runs": []})
    assert best == 0 and rows == []
    print("selftest OK: a clean run, a false recheck breaking it, a missing "
          "recheck failing, and the empty case")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); raise SystemExit(0)
    path = sys.argv[1] if len(sys.argv) > 1 else "overnight/chain_trials.json"
    d = json.load(open(path))
    rows, best = audit(d)
    cfg = d.get("config", {})
    flags = {k: v for k, v in cfg.items() if isinstance(v, bool)}
    print(f"{path}: {len(rows)} trials, LONGEST FULLY-VERIFIED STREAK {best}")
    print(f"  flags on this build: {flags or 'NONE RECORDED — patch53 adds them'}")
    for t, ok, bad in rows:
        if not ok:
            print(f"  trial {t}: " + "; ".join(bad))
    if best == len(rows) and rows:
        print(f"  every trial passes every check.")
