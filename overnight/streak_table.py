"""Ten-trial streak of the FULL route, office to the dealer table, at attempts=9.

WHY THIS RUN. OPEN-5 (2026-09-07) measured attempts=9 at 9/9 against attempts=3
at 5/10 on the three-node route ending at bar_jukebox. That is one leg short of
the goal, and the goal is a different check: dealer_table is a POSE, confirmed
by table_prompt.at_table() reading the "Baseball Cards" prompt, never by
identify() (CLAUDE.md 7). This run adds that leg and that check, at the retry
depth that arrives, and reports the LONGEST CONSECUTIVE streak -- the quantity
the requirement ("25 in a row") is actually stated in.

HOW THE GOAL IS SCORED. follow() handles the last leg with approach_goal then
reach_table (graph_walk.py:1855-1878), and confirm() returns at_table() for the
goal node (graph_walk.py:175-180). So "arrived" here means the prompt was on
screen after the aim sweep. Nothing on that path presses Square: no match is
started and no money moves.

METHOD, every clause a scar: one attempt sequence per trial through
follow_verified at attempts=9; start_hint=SPAWN so the reset is not paid twice
(OPEN-8); shots= so each leg's end frame is written (OPEN-1); each trial in a
run_trial child with the timeout enforced from OUTSIDE (10.14) at a ceiling no
attempts=9 trial can reach -- the deepest OPEN-5 trial took 780s on three legs;
a trial that cannot be measured is INVALID, never a failure (10.6); and
run_trial holds the console lock, so keep_awake stands down for the whole run.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import _harness

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox", "dealer_table"]
TRIALS = 10
ATTEMPTS = 9
TIMEOUT = 1800
OUT = os.path.join(HERE, "streak_table.json")
SHOTS = os.path.join(HERE, "streak_table_failframes")


def one_trial():
    import compass
    import graph_walk as gw
    import reset_env
    import table_prompt
    import worldmap as wm

    def log(m):
        print(m, flush=True)

    assert gw.GOAL == "dealer_table", gw.GOAL
    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()
    t0 = time.time()
    ok, reached = gw.follow_verified(m, ROUTE, log=log, attempts=ATTEMPTS,
                                     shots=SHOTS, start_hint=gw.SPAWN)
    secs = round(time.time() - t0, 1)
    # Independent second look from a settled pose, as measure_primitive did:
    # the primitive already believes only the prompt, so this asks whether it
    # still holds a moment later. A disagreement is worth more than the rate.
    time.sleep(0.8)
    recheck = bool(table_prompt.at_table(compass.fast_capture()))
    return {"arrived": bool(ok), "depth": len(reached), "seconds": secs,
            "at_table_recheck": recheck, "agrees": bool(ok) == recheck,
            **_harness.census_kinds(gw),
            "measurable": gw._LAST_TRIAL_MEASURABLE}


def main():
    def log(m):
        print(m, flush=True)

    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")
    import graph_walk as gw
    res = {"question": "full-route streak to the dealer table at attempts=9",
           "route": ROUTE, "attempts": ATTEMPTS, "trials": TRIALS,
           "config": {"TRUST_RESET_SPAWN": gw.TRUST_RESET_SPAWN,
                      "RECOVER_MISSED": gw.RECOVER_MISSED,
                      "NULL_YAW_BEFORE_ALIGN": gw.NULL_YAW_BEFORE_ALIGN,
                      "LEG_SPEED_BY_LEG": {str(k): v for k, v in gw.LEG_SPEED_BY_LEG.items()},
                      "MERGE_STEPS_BY_LEG": [str(x) for x in gw.MERGE_STEPS_BY_LEG]},
           "runs": []}
    log(f"streak: {TRIALS} trials, route {ROUTE}, attempts={ATTEMPTS}, ceiling {TIMEOUT}s")
    log(f"  config {res['config']}")
    streak = best = 0
    for i in range(1, TRIALS + 1):
        r, secs = _harness.run_trial(__file__, "trial", TIMEOUT, log=log)
        if r is None or "error" in r:
            log(f"[{i:2d}] INVALID after {secs:.0f}s — {r.get('error') if r else 'timeout/crash/stream'}; not a failure")
            res["runs"].append({"trial": i, "arrived": None, "seconds": secs,
                                "reason": (r or {}).get("error", "unmeasurable")})
            # An invalid trial neither extends nor breaks the streak: it was not observed.
        else:
            r["trial"] = i; res["runs"].append(r)
            streak = streak + 1 if r["arrived"] else 0
            best = max(best, streak)
            log(f"[{i:2d}] {'ARRIVED' if r['arrived'] else 'missed '} depth {r['depth']}/{len(ROUTE)} "
                f"in {r['seconds']:.0f}s  recheck at_table={r['at_table_recheck']}"
                f"{'' if r['agrees'] else '  DISAGREED'}  streak {streak}  best {best}")
        res["best_streak"] = best
        _harness.save_result(OUT, res)
    val = [r for r in res["runs"] if r.get("arrived") is not None]
    arr = [r for r in val if r["arrived"]]
    log(f"\n--- STREAK TO THE TABLE ---\n  arrived {len(arr)}/{len(val)} valid "
        f"({len(res['runs']) - len(val)} invalid)\n  BEST CONSECUTIVE: {best}  (need 25)")
    _harness.report_kinds(val, out=log)
    log(f"  -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        try:
            print(json.dumps(one_trial()), flush=True)
        except Exception as e:
            print(json.dumps({"error": f"{type(e).__name__}: {e}"}), flush=True)
        finally:
            try:
                import analog_replay as ar
                ar.send(["clear"])
            except Exception:
                pass
    else:
        main()
