"""Measure CONSECUTIVE arrivals with the verified executor.

The requirement is 25 in a row. Mean depth cannot express that: a 90% success
rate with an independent failure every tenth run never produces 25
consecutively. So this reports the longest STREAK.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]
TRIALS = 10
OUT = os.path.dirname(os.path.abspath(__file__))

SHOTS = os.path.join(OUT, "streak_failframes")

if __name__ == "__main__":
    import graph_walk as gw, worldmap as wm
    import console_lock

    # THIS SCRIPT DRIVES THE CONSOLE DIRECTLY, NOT THROUGH _harness.run_trial,
    # so it does not inherit run_trial's declaration and must make its own. A
    # background nudge landing mid-leg ends the push early and the short leg is
    # indistinguishable from a routing failure in every log written here.
    with console_lock.held("measure_streak"):
        m = wm.WorldMap.load()
        t0 = time.time()
        try:
            # shots= writes at_<node>_<epoch_ms>.jpg at the moment each leg's
            # last push settled, which is the only admissible frame for a
            # failure census (OPEN-1). It costs nothing on a run that is
            # happening anyway.
            r = gw.consecutive_arrivals(m, ROUTE, TRIALS, log=print, shots=SHOTS)
        finally:
            try:
                import analog_replay as ar; ar.send(["clear"])
            except Exception:
                pass
        # per-node detail, so a failure says WHICH leg and how long it cost
        r["route"] = ROUTE
        r["seconds"] = round(time.time() - t0, 1)
        _harness.save_result(os.path.join(OUT, "streak.json"), r)
        print(f"\n--- STREAK ---\n  arrived {r['arrived']}/{r['valid']} valid"
              f"\n  BEST CONSECUTIVE: {r['best_streak']}  (need 25)")
