"""Does aiming the doorway traverse away from the door improve arrival?

THE OBSERVATION CAME FIRST, from the user watching the stream: "you slightly
bump into the door and that causes small amounts of drift which compounds."

THE MEASUREMENT. Off a labelled capture, the gap is ~455px wide with 180px of
clearance to the DOOR and 275px to the jamb, so the character walks nearer the
door. Corroborated in the OPEN-4 run: pre-alignment dx at portrait_room was
+49.4 +49.7 +51.0 +86.3 +133.9 +165.9 and one -48.8 — 6 of 7 positive, median
+51px, with a spread far larger than the bias. That is why the fix is CLEARANCE,
not a better aim.

WHY +4.0 AND NOT THE MEASURED 2.5. slow_traverse.TURN_TOLERANCE is 4.0 deg, so
any smaller correction is a NO-OP — turn_to finds the error inside tolerance and
sends nothing. 4.0 is the smallest offset the executor can perform at all.

INTERLEAVED, NOT BLOCKED (CLAUDE.md 10.5): route performance has a
session-to-session component that dwarfs the effects here — the same node
measured 3/3 one morning and 4/20 that afternoon with no code change. Blocking
the arms would confound the arm with the hour.

ONE VARIABLE (10.7). Leg 1 runs at LEG_SPEED_BY_LEG in BOTH arms; only
DOORWAY_CLEARANCE_DEG differs. The OPEN-4 baseline is NOT the control arm — it
predates the leg-1 speed change, and comparing to it would conflate the two.

    .venv/bin/python overnight/ab_doorway.py

Do NOT set BASEBALL_TEST_RUN.
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
TIMEOUT = 420
ARMS = [("clearance", 4.0), ("baseline", 0.0)]
OUT = os.path.join(HERE, "ab_doorway.json")
SHOTS = os.path.join(HERE, "doorway_failframes")


def one_trial(deg):
    import graph_walk as gw
    import worldmap as wm
    import reset_env

    def log(m):
        print(m, flush=True)

    gw.DOORWAY_CLEARANCE_DEG = float(deg)
    log(f"  arm: DOORWAY_CLEARANCE_DEG={gw.DOORWAY_CLEARANCE_DEG}")

    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()

    t0 = time.time()
    ok = gw.go_to_node_verified(m, TARGET, log=log, attempts=3,
                                shots=SHOTS, start_hint=gw.SPAWN)
    secs = round(time.time() - t0, 1)
    where, detail = gw.locate(m, log=log)
    return {"arrived": bool(ok), "seconds": secs, "located": where,
            "agrees": bool(ok) == (where == TARGET),
            "kinds": list(gw._LAST_FAILURE_KINDS),
            "measurable": gw._LAST_TRIAL_MEASURABLE,
            "deg": float(deg)}


def main():
    def log(m):
        print(m, flush=True)

    import graph_walk as gw
    res = {"question": "does doorway clearance improve arrival?",
           "arms": [a for a, _ in ARMS], "trials_per_arm": TRIALS,
           "leg1_speed": {str(k): v for k, v in gw.LEG_SPEED_BY_LEG.items()},
           "runs": []}

    if not _harness.alive():
        raise SystemExit("stream is not delivering frames — a dead stream "
                         "records as failure and invalidates every trial")

    for t, (arm, deg) in _harness.interleave(ARMS, TRIALS):
        log(f"\n=== {arm} (deg={deg}) trial {t + 1}/{TRIALS} ===")
        r, wall = _harness.run_trial(__file__, str(deg), TIMEOUT, log=log)
        row = {"arm": arm, "trial": t + 1, "wall": wall}
        row.update(r or {"arrived": None, "invalid": "no result"})
        res["runs"].append(row)
        _harness.save_result(OUT, res)
        log(f"  -> [{arm}] arrived={row.get('arrived')} "
            f"located={row.get('located')} in {row.get('seconds')}s")

    log("\n--- A/B RESULT ---")
    for arm, _ in ARMS:
        rows = [r for r in res["runs"] if r["arm"] == arm
                and r.get("arrived") is not None]
        hit = [r for r in rows if r["arrived"]]
        med = sorted(r["seconds"] for r in hit)[len(hit) // 2] if hit else None
        log(f"  {arm:10s} {len(hit)}/{len(rows)} arrived   median {med}s   "
            f"invalid {TRIALS - len(rows)}")
    res["summary"] = {a: {"arrived": sum(1 for r in res["runs"]
                                         if r["arm"] == a and r.get("arrived")),
                          "valid": sum(1 for r in res["runs"]
                                       if r["arm"] == a
                                       and r.get("arrived") is not None)}
                      for a, _ in ARMS}
    _harness.save_result(OUT, res)
    log(f"  {json.dumps(res['summary'])}")
    log("  n=10/arm gives power 0.94 for a full 1.0-depth effect (10.3); a null "
        "here is informative, a small difference is not.")
    return res


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        try:
            print(json.dumps(one_trial(sys.argv[2])))
        except Exception as e:
            print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
    else:
        main()
