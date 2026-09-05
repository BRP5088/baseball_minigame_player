"""A/B: does retrying harder reach the streak, as the arithmetic predicts?

PREDICTION, written before the run, from the measured per-attempt leg rates
(portrait 1.00, pool 0.667, jukebox 0.40):

    attempts=3   route 0.755   P(25 in a row) 0.001   <- today
    attempts=9   route 0.990   P(25 in a row) 0.775

The cost should barely move (110s -> 124s per route) because extra attempts only
fire when a leg actually misses, and most do not.

RUN 1 (2026-09-04) COULD NOT ANSWER THIS. Two flaws, both mine:
  - TIMEOUT was 420s and 3 of 6 attempts_9 trials hit it. The ceiling censored
    exactly the arm whose mechanism is "spend longer" — a bias built into the
    harness against the thing it was testing. Now 900s.
  - Both arms collapsed together partway through (trials 1-3: 5/5 arrived;
    trials 4-6: 0/5). A change to retry depth cannot degrade the arm that did
    not get it, so that was the environment, not the code. chiaki had logged
    32388 decoder-overflow lines.
  - n was 6; the documented minimum here is 10 per arm (n=3 has power 0.00).

THE ASSUMPTION THIS TESTS: that retries are INDEPENDENT. The reset restores a
known state, which is what should decorrelate them — but one measurement mildly
contradicts it (the pool leg predicted 0.963 at attempts=3, observed 0.800,
p~0.05). If retries correlate, the arithmetic above is optimistic and this run
will show it: arrival will fall short of 0.99 no matter how deep the retries go.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, and putting overnight/ at
# the END of sys.path means it can only ever add names, never shadow a project
# or stdlib module for the `--one-trial` child that inherits this line.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]
TRIALS = 10
TIMEOUT = 900
ARMS = [("attempts_9", 9), ("attempts_3", 3)]
OUT = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(OUT, "failframes")
res = {"route": ROUTE, "runs": []}


def log(m): print(m, flush=True)


def save():
    # Atomic: an interrupted write must not destroy a completed run. Imported
    # lazily so the `--one-trial` child, which never saves, does not pay for it.
    import _harness
    _harness.save_result(os.path.join(OUT, "ab_attempts.json"), res)


def alive(gap=1.0):
    import compass, numpy as np
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float); time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) > 0.35


def one(attempts):
    import graph_walk as gw, reset_env, worldmap as wm
    if not alive(): raise RuntimeError("stream not updating")
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=lambda *a: None); time.sleep(1.2)
    t0 = time.time()
    # log=print, NEVER log=lambda: None. follow_verified reports
    # failure_kind.classify(), per-node detail, align dx and commanded-vs-
    # achieved bearings ONLY through log (graph_walk.py:1568-1576). Run 1
    # discarded all of it — the first entry in this project's own diagnosis
    # catalogue is "a logger passed as lambda m: None", and I reproduced it.
    ok, reached = gw.follow_verified(m, ROUTE, log=log,
                                     attempts=attempts, shots=SHOTS)
    return bool(ok), len(reached), round(time.time() - t0, 1)


def _one_trial(attempts):
    """Run ONE trial and print its result as JSON. Invoked as a subprocess."""
    try:
        ok, depth, secs = one(attempts)
        print(json.dumps({"arrived": ok, "depth": depth, "seconds": secs}))
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass


if __name__ == "__main__":
    # Child mode: one trial, one JSON line, then exit. The parent enforces the
    # timeout from OUTSIDE, because signal.alarm does not interrupt a trial
    # blocked inside a capture — measured, a 590s trial sailed past a 260s
    # alarm. That is why this is a subprocess and not a try/except.
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        _one_trial(int(sys.argv[2]))
        sys.exit(0)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _harness

    log(f"attempts A/B: {TRIALS} interleaved trials per arm, "
        f"{TIMEOUT}s ceiling enforced out-of-process\n")
    try:
        for t, (name, att) in _harness.interleave(ARMS, trials=TRIALS):
            res_json, secs = _harness.run_trial(__file__, att, TIMEOUT, log=log)
            if res_json is None:
                ok, depth = None, None
                log(f"  [{name}] {t+1}/{TRIALS}: INVALID (timeout or crash) "
                    f"after {secs}s")
            elif "error" in res_json:
                ok, depth = None, None
                log(f"  [{name}] {t+1}/{TRIALS}: INVALID ({res_json['error']})")
            else:
                ok, depth = res_json["arrived"], res_json["depth"]
                log(f"  [{name}] {t+1}/{TRIALS}: arrived={ok} depth={depth}/3 "
                    f"in {secs}s")
            # A trial whose stream died is INVALID, not a failure. Conflating
            # "cannot see" with "did not arrive" is how a sleeping console got
            # recorded as a navigation result.
            if ok is not None:
                try:
                    if not _harness.alive():
                        log("    stream died — discarding")
                        ok, depth = None, None
                except Exception:
                    pass
            res["runs"].append({"arm": name, "arrived": ok, "depth": depth,
                                "seconds": secs})
            save()
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        save()

    import statistics
    print("\n--- RESULT ---")
    for name, _ in ARMS:
        v = [r for r in res["runs"] if r["arm"] == name and r["arrived"] is not None]
        inval = sum(1 for r in res["runs"] if r["arm"] == name and r["arrived"] is None)
        if v:
            a = [r["arrived"] for r in v]
            sec = [r["seconds"] for r in v if r["seconds"]]
            print(f"  {name:11} arrived {sum(a)}/{len(a)}   "
                  f"median {statistics.median(sec):.0f}s   invalid {inval}")
