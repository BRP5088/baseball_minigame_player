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
        # AN INVALID TRIAL NEITHER BREAKS NOR EXTENDS A STREAK -- this project's
        # convention, and it matters because the goal is 25 IN A ROW WITHIN ONE
        # BATCH. An invalid means the trial could not be measured (the game
        # window went behind Mission Control, the stream dropped), not that the
        # walk failed. Counting it as a break would have cost a real streak of
        # 17 today, reported as 16.
        if r.get("outcome") == "INVALID":
            rows.append((r.get("trial"), None, ["INVALID — not measured; "
                                                "neither breaks nor extends"]))
            continue
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
        if ok is None:          # INVALID: skipped entirely
            continue
        run = run + 1 if ok else 0
        best = max(best, run)
    return rows, best


def both_numbers(d):
    """(trials, arrived, first-walk arrivals) -- the retry's honest pair.

    A run that allows a reload after a lost walk must report the FIRST walk's
    rate too, or it hides a regression: a controller that fell from 87% to 70%
    would still show ~91% with two attempts and look healthy. The first attempt
    is its own control, measured in the same session.
    """
    runs = d.get("runs", [])
    scored = [r for r in runs if r.get("outcome") in ("ARRIVED", "FAILED")]
    arrived = sum(1 for r in scored if r.get("outcome") == "ARRIVED")
    firsts = [r.get("first_walk_arrived") for r in scored]
    known = [f for f in firsts if f is not None]
    return len(scored), arrived, (sum(1 for f in known if f), len(known))


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
    assert any("did not hold" in c for _, _, cs in rows for c in cs), rows
    # An INVALID between two arrivals must JOIN them, not split them. Declared
    # AFTER the assertion above, because reassigning `rows` first left that
    # check reading this case instead -- it failed loudly, which is the point.
    inv = {"trial": 2, "outcome": "INVALID", "arrived": False}
    rows_i, best_i = audit({"runs": [good(1), inv, good(3), good(4)]})
    assert best_i == 3, (rows_i, best_i)
    assert rows_i[1][1] is None and "INVALID" in rows_i[1][2][0], rows_i[1]
    # ...and a missing recheck is not a pass
    missing = {k: v for k, v in good(1).items() if k != "at_table_recheck"}
    rows, best = audit({"runs": [missing]})
    assert best == 0, rows
    # OUTCOME AND `arrived` DISAGREEING is the case OPEN-14 actually hit: the
    # harness scored a trial ARRIVED while the walk itself had not arrived.
    # Without this case the check is decorative (a mutant deleting it survived).
    liar = dict(good(2), arrived=False)
    rows, best = audit({"runs": [good(1), liar, good(3)]})
    assert best == 1, (rows, best)
    assert any("arrived False" in c for _, _, cs in rows for c in cs), rows
    # A BAD OUTCOME WITH EVERYTHING ELSE CLEAN. Only the outcome check can
    # catch this one; without it a mutant deleting that check survived, because
    # every other failing case here also trips a different check.
    wrong = dict(good(2), outcome="FAILED")
    rows, best = audit({"runs": [good(1), wrong, good(3)]})
    assert best == 1, (rows, best)
    assert any("outcome FAILED" in c for _, _, cs in rows for c in cs), rows
    # AN "ARRIVAL" THAT ENDED FAR SHORT OF THE CHAIN'S END, everything else
    # clean. Without this the end-of-chain check is decorative.
    short = dict(good(2), k_final=140)
    rows, best = audit({"runs": [good(1), short, good(3)]})
    assert best == 1, (rows, best)
    assert any("ended at waypoint 140" in c for _, _, cs in rows for c in cs), rows
    # ...and a walk that ends a few waypoints early is NORMAL, not a break:
    # arrivals in the record legitimately stop at 197-203 of 205.
    rows, best = audit({"runs": [good(1), dict(good(2), k_final=197), good(3)]})
    assert best == 3, (rows, best)
    # both_numbers: a retried arrival must NOT inflate the first-walk rate.
    n, arr, (fok, fn) = both_numbers({"runs": [
        dict(good(1), first_walk_arrived=True),
        dict(good(2), first_walk_arrived=False),      # arrived only on the retry
        {"trial": 3, "outcome": "FAILED", "first_walk_arrived": False}]})
    assert (n, arr) == (3, 2), (n, arr)
    assert (fok, fn) == (1, 3), (fok, fn)
    n2, arr2, (fok2, fn2) = both_numbers({"runs": [good(1)]})
    assert fn2 == 0, "a single-attempt run records no first-walk field"
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
    n, arrived, (first_ok, first_n) = both_numbers(d)
    print(f"{path}: {len(rows)} trials, LONGEST FULLY-VERIFIED STREAK {best}")
    if n:
        print(f"  trial arrival     {arrived}/{n} = {arrived/n:.0%}")
    if first_n:
        print(f"  FIRST-WALK arrival {first_ok}/{first_n} = {first_ok/first_n:.0%}"
              f"   <- the control; compare this with history, not the line above")
    elif n:
        print("  first-walk arrival: not recorded (a single-attempt run, where "
              "the two are the same number)")
    print(f"  flags on this build: {flags or 'NONE RECORDED — patch53 adds them'}")
    for t, ok, bad in rows:
        if not ok:
            print(f"  trial {t}: " + "; ".join(bad))
    if best == len(rows) and rows:
        print(f"  every trial passes every check.")
