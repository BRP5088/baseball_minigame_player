"""A/B: does searching locally beat resetting to the spawn?

METRIC: arrival at bar_pool_room, verified, AND seconds per trial. The second
number is the point — a reset re-walks the whole route, so if local search
arrives as often but faster, that alone multiplies how much can be measured
per hour.
"""
import json, os, signal, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

TARGET = "bar_pool_room"
TRIALS = 8
TIMEOUT = 260
OUT = os.path.dirname(os.path.abspath(__file__))
res = {"target": TARGET, "runs": []}

# _quiet, NOT the bare lambda. Silencing the RESET is defensible — reset noise
# is not the measurement — but writing `log=lambda *a: None` here puts the exact
# literal that means "bug" everywhere else in this project one line above the
# measurement call, which is how it kept getting copied onto the measurement.
def _quiet(*a, **k):
    pass


def log(m): print(m, flush=True)
def save(): _harness.save_result(os.path.join(OUT, "ab_local_recovery.json"), res)

class _T(Exception): pass
def _al(s, f): raise _T()

def alive(gap=1.0):
    import compass, numpy as np
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float); time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h,:w]-b[:h,:w]).mean()) > 0.35

def one(local):
    import graph_walk as gw, reset_env, worldmap as wm
    if not alive(): raise RuntimeError("stream not updating")
    gw.LOCAL_RECOVERY_FIRST = local
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet); time.sleep(1.2)
    t0 = time.time()
    ok = gw.go_to_node_verified(m, TARGET, log=log, start_hint=gw.SPAWN)
    return bool(ok), round(time.time() - t0, 1)

if __name__ == "__main__":
    try:
        for t in range(TRIALS):
            for name, local in (("local", True), ("reset", False)):
                signal.signal(signal.SIGALRM, _al); signal.alarm(TIMEOUT)
                try:
                    ok, secs = one(local)
                except _T:
                    ok, secs = None, TIMEOUT
                    log(f"  [{name}] {t+1}: timed out")
                except Exception as e:
                    ok, secs = None, None
                    log(f"  [{name}] {t+1}: {type(e).__name__}: {e}")
                finally:
                    signal.alarm(0)
                if ok is not None and not alive():
                    log("    stream died — discarding"); ok = None
                log(f"  [{name}] {t+1}/{TRIALS}: {ok} in {secs}s")
                res["runs"].append({"arm": name, "arrived": ok, "seconds": secs})
                save()
    finally:
        try:
            import analog_replay as ar; ar.send(["clear"])
            import graph_walk as gw; gw.LOCAL_RECOVERY_FIRST = True
        except Exception: pass
        save()
    import collections, statistics
    print("\n--- RESULT ---")
    for arm in ("local", "reset"):
        v = [r for r in res["runs"] if r["arm"] == arm and r["arrived"] is not None]
        if v:
            a = [r["arrived"] for r in v]; s = [r["seconds"] for r in v if r["seconds"]]
            print(f"  {arm:6} arrived {sum(a)}/{len(a)}   median {statistics.median(s):.0f}s")
