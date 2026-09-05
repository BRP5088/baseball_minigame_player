"""A/B: do the office legs still ARRIVE when walked 3x faster?

The win condition is TIME, not arrival — so flat arrival with fewer seconds is
a WIN, not a null. Both are recorded.

The detector is unusually sensitive: `office_door -> portrait_room` has arrived
20/20, so any degradation shows immediately. The corridor leg has no reference
by design, but it does not need one — if speeding it up breaks anything,
portrait_room arrival falls off 20/20.

Capped at LEG_SPEED_MAX = 0.60, which is where measured repeatability collapses
(spread 15px through 0.45, 27 at 0.60, 124 at 0.75, 476 at 0.85).
"""
import json, os, signal, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

TARGET = "portrait_room"
TRIALS = 8
TIMEOUT = 240
FAST = {("office_corridor", "office_door"): 3.0,
        ("office_door", "portrait_room"): 3.0}
ARMS = [("fast_3x", FAST), ("normal", {})]
OUT = os.path.dirname(os.path.abspath(__file__))
res = {"target": TARGET, "runs": []}


# _quiet, NOT the bare lambda. Silencing the RESET is defensible — reset noise
# is not the measurement — but writing `log=lambda *a: None` here puts the exact
# literal that means "bug" everywhere else in this project one line above the
# measurement call, which is how it kept getting copied onto the measurement.
def _quiet(*a, **k):
    pass


def log(m): print(m, flush=True)
def save(): _harness.save_result(os.path.join(OUT, "ab_leg_speed.json"), res)


class _T(Exception): pass
def _al(s, f): raise _T()


def alive(gap=1.0):
    import compass, numpy as np
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float); time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) > 0.35


def one(overrides):
    import graph_walk as gw, reset_env, worldmap as wm
    if not alive(): raise RuntimeError("stream not updating")
    gw.LEG_SPEED_BY_LEG = dict(overrides)
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet); time.sleep(1.2)
    t0 = time.time()
    ok = gw.go_to_node_verified(m, TARGET, log=log)
    return bool(ok), round(time.time() - t0, 1)


if __name__ == "__main__":
    try:
        for t in range(TRIALS):
            for name, ov in ARMS:
                signal.signal(signal.SIGALRM, _al); signal.alarm(TIMEOUT)
                try:
                    ok, secs = one(ov)
                except _T:
                    ok, secs = None, None; log(f"  [{name}] {t+1}: timed out")
                except Exception as e:
                    ok, secs = None, None; log(f"  [{name}] {t+1}: {type(e).__name__}: {e}")
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
            import graph_walk as gw; gw.LEG_SPEED_BY_LEG = {}
        except Exception: pass
        save()
    import statistics
    print("\n--- RESULT ---")
    for name, _ in ARMS:
        v = [r for r in res["runs"] if r["arm"] == name and r["arrived"] is not None]
        if v:
            a = [r["arrived"] for r in v]; s = [r["seconds"] for r in v if r["seconds"]]
            print(f"  {name:8} arrived {sum(a)}/{len(a)}   median {statistics.median(s):.0f}s")
