"""Where do the ~75 seconds of a trial actually GO?

Measured component costs (median, this machine):
    fast_capture      32.1ms
    read_bearing     129.5ms   <- 4x a capture
    places.identify   43.4ms
    places.keypoints   7.5ms

Walking is only ~16-23s of a ~75s trial, so ~50s is something else. This wraps
the hot functions with counters instead of guessing which.
"""
import json, os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

OUT = os.path.dirname(os.path.abspath(__file__))
STATS = collections.defaultdict(lambda: [0, 0.0])   # name -> [calls, seconds]


def wrap(mod, name, label):
    real = getattr(mod, name)

    def timed(*a, **k):
        t = time.perf_counter()
        try:
            return real(*a, **k)
        finally:
            s = STATS[label]
            s[0] += 1
            s[1] += time.perf_counter() - t
    setattr(mod, name, timed)
    return real


if __name__ == "__main__":
    import compass, places, walk_steps as ws, graph_walk as gw, worldmap as wm
    import reset_env, analog_replay as ar

    wrap(compass, "fast_capture", "capture")
    wrap(compass, "read_bearing", "read_bearing")
    wrap(places, "identify", "identify")
    wrap(places, "keypoints", "keypoints")
    wrap(ws, "walk_forward", "walk_forward(incl sleeps)")
    wrap(ws, "turn_to", "turn_to(incl sleeps)")
    wrap(reset_env, "reset_environment", "reset")

    m = wm.WorldMap.load()
    t0 = time.perf_counter()
    try:
        reset_env.reset_environment(log=lambda *a: None)
        time.sleep(1.2)
        ok = gw.go_to_node_verified(m, "portrait_room", log=lambda *a: None,
                                    start_hint=gw.SPAWN)
    finally:
        try:
            ar.send(["clear"])
        except Exception:
            pass
    total = time.perf_counter() - t0

    rows = sorted(STATS.items(), key=lambda kv: -kv[1][1])
    out = {"total_sec": round(total, 1), "arrived": bool(ok),
           "components": {k: {"calls": v[0], "sec": round(v[1], 2)}
                          for k, v in rows}}
    _harness.save_result(os.path.join(OUT, "profile.json"), out)
    print(f"\n--- TRIAL PROFILE: {total:.1f}s total, arrived={ok} ---")
    for k, (n, sec) in rows:
        print(f"  {k:26} {n:4} calls  {sec:6.1f}s  {100*sec/total:5.1f}%")
    acc = sum(v[1] for k, v in STATS.items()
              if k in ("walk_forward(incl sleeps)", "turn_to(incl sleeps)", "reset"))
    print(f"  {'unaccounted':26} {'':4}        {total-acc:6.1f}s  {100*(total-acc)/total:5.1f}%")
