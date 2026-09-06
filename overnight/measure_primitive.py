"""OPEN-4: how often does go_to_node_verified ACTUALLY arrive?

THE QUESTION, from CLAUDE.md section 11:

    "Is arrival at bar_pool_room really ~55%, and does go_to_node_verified
     really approach 100%? 11/20 for a single walk vs 4/4 at ~75s for the
     3-attempt primitive. Different quantities; the second is the one that
     matters. Everything downstream needs a verified start pose, and one
     re-record attempt reached its start node 0 of 20 and another 4 of 20.
     Measure the primitive, n>=10, one leg not a full route."

WHY IT IS FIRST IN THE QUEUE. This is the INSTRUMENT, not a result. Every A/B
still queued — the jukebox leg, RECOVER_MISSED, yaw nulling, attempts depth —
starts by walking to a node and then measuring something from there. If the
primitive is not near 100%, those experiments are measuring the noise in their
own start pose, and the 4/4 that everything rests on is n=4.

ONE LEG, NOT A ROUTE, deliberately. A route's arrival rate is the product of its
legs and hides which one failed; section 8(f) says to report by class for the
same reason.

WHAT IS SCORED. `go_to_node_verified` returning True is already a verified
arrival — it believes only locate(). But section 8(e) records that follow()'s
"reached" is a ROUTING CLAIM that once reported bar_jukebox while the character
stood in a stairwell, so this ALSO calls locate() independently afterwards and
records both. If the two ever disagree, that disagreement is the finding.

INVALID IS NOT FAILURE. _harness.run_trial checks the stream after the trial and
returns None if it died, so a console that fell asleep is recorded as None
rather than as a non-arrival. CLAUDE.md 10.6: a run where every arm degrades at
once is the console, not the change.

    .venv/bin/python overnight/measure_primitive.py

Do NOT set BASEBALL_TEST_RUN: that holds every input path off, and the whole
point is to drive the console.
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

TARGET = "bar_pool_room"
TRIALS = 10
ATTEMPTS = 3
TIMEOUT = 420                    # generous: the primitive is ~75-90s
OUT = os.path.join(HERE, "primitive_open4.json")
SHOTS = os.path.join(HERE, "primitive_failframes")


def one_trial():
    import graph_walk as gw
    import worldmap as wm
    import reset_env

    def log(m):
        print(m, flush=True)

    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()

    t0 = time.time()
    ok = gw.go_to_node_verified(m, TARGET, log=log, attempts=ATTEMPTS,
                                shots=SHOTS, start_hint=gw.SPAWN)
    secs = round(time.time() - t0, 1)

    # INDEPENDENT CONFIRMATION. go_to_node_verified already believes only
    # locate(), so this is not a second opinion on the same evidence — it is a
    # check that the primitive's answer still holds a moment later, from a
    # settled pose. A disagreement here is worth more than the arrival rate.
    where, detail = gw.locate(m, log=log)

    return {"arrived": bool(ok), "seconds": secs,
            "located": where, "detail": str(detail)[:140],
            "agrees": bool(ok) == (where == TARGET),
            "kinds": list(gw._LAST_FAILURE_KINDS),
            "measurable": gw._LAST_TRIAL_MEASURABLE}


def main():
    def log(m):
        print(m, flush=True)

    res = {"question": "OPEN-4: go_to_node_verified arrival rate",
           "target": TARGET, "attempts": ATTEMPTS, "trials": TRIALS,
           "config": {}, "runs": []}

    import graph_walk as gw
    res["config"] = {
        "TRUST_RESET_SPAWN": gw.TRUST_RESET_SPAWN,
        "RECOVER_MISSED": gw.RECOVER_MISSED,
        "NULL_YAW_BEFORE_ALIGN": gw.NULL_YAW_BEFORE_ALIGN,
        "REFERENCE_POSE": gw.REFERENCE_POSE,
    }
    log(f"  config: {res['config']}")

    if not _harness.alive():
        raise SystemExit("the stream is not delivering frames — fix that first; "
                         "a dead stream records as a failure and invalidates "
                         "every trial (CLAUDE.md 10.6)")

    for t in range(TRIALS):
        log(f"\n=== trial {t + 1}/{TRIALS} ===")
        r, secs = _harness.run_trial(__file__, "go", TIMEOUT, log=log)
        row = {"trial": t + 1, "wall": secs}
        row.update(r or {"arrived": None, "invalid": "trial produced no result"})
        res["runs"].append(row)
        _harness.save_result(OUT, res)
        log(f"  -> arrived={row.get('arrived')} located={row.get('located')} "
            f"in {row.get('seconds')}s (wall {secs}s)")

    valid = [r for r in res["runs"] if r.get("arrived") is not None]
    hit = [r for r in valid if r["arrived"]]
    res["summary"] = {
        "valid": len(valid), "invalid": len(res["runs"]) - len(valid),
        "arrived": len(hit),
        "rate": None if not valid else round(len(hit) / len(valid), 3),
        "median_seconds": None if not hit else
            sorted(r["seconds"] for r in hit)[len(hit) // 2],
        "disagreements": [r["trial"] for r in valid if not r.get("agrees", True)],
    }
    _harness.save_result(OUT, res)
    log(f"\n--- OPEN-4 ---\n  {json.dumps(res['summary'], indent=2)}")
    if res["summary"]["disagreements"]:
        log("  *** go_to_node_verified and locate() DISAGREED on trials "
            f"{res['summary']['disagreements']} — that is the finding, not the "
            "rate")
    return res


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        try:
            print(json.dumps(one_trial()))
        except Exception as e:
            print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
    else:
        main()
