"""Run the route and SAVE A FRAME every time a node cannot be verified.

Cause B — the bar_pool_room -> bar_jukebox leg, which owns 9 of 9 of its own
failures and arrives ~40% — has never been diagnosed for one reason: no run
ever kept a picture of it. The obvious hypothesis (a bad pose at
bar_pool_room) was tested and REJECTED (p = 0.33), so the answer is not in the
numbers already collected. It has to be looked at.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]
TRIALS = 8
OUT = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(OUT, "failframes")

if __name__ == "__main__":
    import graph_walk as gw, worldmap as wm
    m = wm.WorldMap.load()
    t0 = time.time()
    try:
        r = gw.consecutive_arrivals(m, ROUTE, TRIALS, log=print, shots=SHOTS)
    finally:
        try:
            import analog_replay as ar; ar.send(["clear"])
        except Exception:
            pass
    r["seconds"] = round(time.time() - t0, 1)
    _harness.save_result(os.path.join(OUT, "failframes_result.json"), r)
    print(f"\n--- {r['arrived']}/{r['valid']} arrived, best streak "
          f"{r['best_streak']}, {len(os.listdir(SHOTS))} failure frames ---")
