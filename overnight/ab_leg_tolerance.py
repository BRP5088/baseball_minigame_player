"""A/B: does tightening the leg turn tolerance make the route land?

THE HYPOTHESIS, written before the run:
  slow_traverse's 4.0 deg tolerance is WIDER than the curvature of most legs, so
  turn_to returns without turning and the leg is walked straight at whatever
  heading the character arrived with. Measured on portrait_room ->
  bar_pool_room: four commanded bearings spanning 6.6 deg, all four no-ops, the
  character sitting at 289.1 the whole way.

  IF THE HYPOTHESIS IS RIGHT: tightening the tolerance walks the recorded curve
  and verified depth improves.
  IF IT IS WRONG: depth is unchanged or worse, and the recorded curve was never
  what mattered.

MEASURED ON VERIFIED POSITIONS, never on follow()'s "reached" — that is a
ROUTING CLAIM, and measuring with it is how "the four legs before it land every
time" became a published wrong finding.

ARMS ARE INTERLEAVED, not blocked. The console drifts over a session (NPCs
move, the stream degrades); running all of arm A then all of arm B would
confound the arm with the hour.
"""
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]
TRIALS = 10                     # per arm, interleaved => 20 route walks.
                                # 10 is the MINIMUM that can resolve a 1.0-depth
                                # effect (power 0.94). n=3 has power 0.00 and is
                                # what every reversed A/B on this project used.
TRIAL_TIMEOUT = 240             # seconds; a wedged trial is dropped, not waited on
ARMS = [("baseline_4.0", None), ("tight_1.0", 1.0)]
OUT = os.path.dirname(os.path.abspath(__file__))

res = {"route": ROUTE, "trials_per_arm": TRIALS, "runs": [],
       "started": time.strftime("%H:%M:%S")}


# _quiet, NOT the bare lambda. Silencing the RESET is defensible — reset noise
# is not the measurement — but writing `log=lambda *a: None` here puts the exact
# literal that means "bug" everywhere else in this project one line above the
# measurement call, which is how it kept getting copied onto the measurement.
def _quiet(*a, **k):
    pass


def log(m):
    print(m, flush=True)


def save():
    _harness.save_result(os.path.join(OUT, "ab_leg_tolerance.json"), res)


def fingerprint():
    import hashlib
    h = hashlib.sha256()
    for f in ("graph_walk.py", "slow_traverse.py", "walk_steps.py"):
        h.update(open(f, "rb").read())
    return h.hexdigest()[:16]


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def stream_alive(gap=1.0):
    """Is the picture actually updating? 0.00 means the console is asleep.

    Added 2026-09-03: a whole confirmation run was taken while the PS5 was
    switching itself off. Every trial recorded depth 1 — "the first node
    verified, then nothing" — which is what a FROZEN picture looks like, not a
    routing failure. The harness recorded CANNOT SEE as DID NOT ARRIVE and the
    result read as a clean refutation.
    """
    import compass
    import numpy as np
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) > 0.35


def one_run(arm, tol):
    """Walk the route from a reset spawn. Returns how many nodes were VERIFIED.

    Hard-capped: on 2026-09-03 a trial wedged in a retry loop for 25 minutes
    with the console perfectly healthy, and the run lost its last two trials to
    it. A dropped trial costs one data point; a wedged one costs the night.
    """
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    if not stream_alive():
        raise RuntimeError("stream is not updating — console asleep; "
                           "refusing to record a depth")
    gw.LEG_TURN_TOLERANCE = tol
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet)
    time.sleep(1.5)

    depth, where = 0, gw.SPAWN
    for node in ROUTE:
        gw.follow(m, where, node, log=log)
        got, detail = gw.locate(m, log=log)
        if got == node:
            depth += 1
            where = node
            log(f"    verified {node}")
        else:
            log(f"    lost at {node} (here: {got!r} {detail})")
            break
    return depth


def main():
    fp = fingerprint()
    res["code_fingerprint"] = fp
    log(f"code fingerprint {fp}\narms: {[a for a, _ in ARMS]}, "
        f"{TRIALS} interleaved trials each\n")
    for t in range(TRIALS):
        for arm, tol in ARMS:
            log(f"  [{arm}] trial {t + 1}/{TRIALS}")
            signal.signal(signal.SIGALRM, _alarm)
            signal.alarm(TRIAL_TIMEOUT)
            try:
                d = one_run(arm, tol)
            except _Timeout:
                log(f"    trial exceeded {TRIAL_TIMEOUT}s — dropped")
                d = None
            except Exception as e:
                log(f"    run raised {type(e).__name__}: {e}")
                d = None
            signal.alarm(0)
            # NULL THE DEPTH BEFORE RECORDING IT, NOT AFTER. This used to append
            # the row first and then set `d = None`, so the row kept the
            # contaminated depth while the log said "discarding this depth". The
            # analysis below reads res["runs"], not `d`, so every trial the
            # console slept through was scored as a real result — in the one arm
            # that had been running longest. CLAUDE.md 10.6 exists because a
            # sleeping console once made BOTH arms degrade together; this is the
            # same failure with the evidence deleted.
            if d is not None and not stream_alive():
                log("    stream died DURING the trial — discarding this depth")
                d = None
            res["runs"].append({"arm": arm, "trial": t + 1, "depth": d})
            log(f"    depth {d} of {len(ROUTE)}")
            save()
    if fingerprint() != fp:
        res["INVALID"] = "source changed mid-run; discard"
        log("*** SOURCE CHANGED MID-RUN — measurement INVALID ***")
    save()


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        try:
            import graph_walk as gw
            gw.LEG_TURN_TOLERANCE = None
        except Exception:
            pass
        save()
    print("\n--- A/B RESULT (verified depth of %d) ---" % len(ROUTE))
    for arm, _ in ARMS:
        ds = [r["depth"] for r in res["runs"]
              if r["arm"] == arm and r["depth"] is not None]
        if ds:
            print(f"  {arm:14} {ds}  mean {sum(ds) / len(ds):.2f}")
        else:
            print(f"  {arm:14} no completed runs")
    print("\n  n is small. Treat this as a DIRECTION, not a coefficient.")
