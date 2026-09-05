"""PHASE 1 STEP 4 — re-record bar_pool_room -> bar_jukebox from the BOT's pose.

GATED. Runs only when explicitly told to, because the plan says step 4 happens
only if step 3 converged. Pass --force to override, and say why in the report.

WHY THIS LEG. The recorded leg is a human's:

    bearing 2.1 / 1.2 / 0.8 / 359.4 / 359.6, total 3.30s, dead straight north

but a search from the EXECUTOR'S own arrival found 337.1 deg for 0.80s reaches
bar_jukebox. 25 degrees apart and FOUR TIMES the distance — not a leg needing
correction, a different journey. The human's bar_pool_room and the bot's are far
apart inside one large room, and identify() cannot tell them apart because it
answers "which room", not "where in it".

HOW IT WORKS. Stand at bar_pool_room VERIFIED, search a small fan of
(bearing, duration) for one that lands on bar_jukebox VERIFIED, repeat it to
check it is repeatable rather than lucky, and only then write it into the map.

IT REFUSES TO WRITE A LEG IT COULD NOT REPEAT. A leg recorded from one lucky
trip is exactly what is already in the map, and planning through a bad edge
poisons every future route.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

A, B = "bar_pool_room", "bar_jukebox"
BEARINGS = [337.1, 345.0, 353.0, 2.1, 11.0]
DURS = [0.8, 1.3]
CONFIRMS = 2            # a candidate must land this many times, from scratch
OUT = os.path.dirname(os.path.abspath(__file__))
res = {"leg": f"{A} -> {B}", "candidates": [], "written": False}


def log(m):
    print(m, flush=True)


def save():
    _harness.save_result(os.path.join(OUT, "step4_result.json"), res)


def try_once(m, bearing, dur):
    """From a VERIFIED A, walk one (bearing, dur). True if B verifies."""
    import graph_walk as gw
    import walk_steps as ws

    if not gw.go_to_node_verified(m, A, log=lambda *a: None):
        return None                      # could not even start; not a vote
    ws.turn_to(bearing, log=lambda *a: None, tolerance=1.0)
    ws.walk_forward(0.30, dur)
    time.sleep(0.6)
    got, _ = gw.locate(m, log=lambda *a: None)
    return got == B


def main(force=False):
    import graph_walk as gw
    import worldmap as wm

    if not force:
        s3 = os.path.join(OUT, "phase1", "step3_result.json")
        ok = False
        if os.path.exists(s3):
            d = json.load(open(s3))
            got = [t["final_dx"] for t in d.get("trials", [])
                   if t.get("final_dx") is not None]
            import pose
            ok = bool(got) and all(g <= pose.ALIGN_TOL_PX for g in got)
        if not ok:
            log("step 3 did not converge (or produced no measurement) — "
                "NOT re-recording. Pass --force with a stated reason.")
            return
    m = wm.WorldMap.load()
    for bearing in BEARINGS:
        for dur in DURS:
            hits, tries = 0, 0
            for _ in range(CONFIRMS):
                r = try_once(m, bearing, dur)
                if r is None:
                    continue
                tries += 1
                hits += bool(r)
                log(f"  {bearing:6.1f} for {dur:.2f}s -> "
                    f"{'ARRIVED' if r else 'missed'}")
            res["candidates"].append({"bearing": bearing, "dur": dur,
                                      "hits": hits, "tries": tries})
            save()
            if tries >= CONFIRMS and hits == tries:
                log(f"  REPEATABLE: {bearing} for {dur}s, {hits}/{tries}")
                m.connect(A, B, [{"bearing": bearing, "dur": dur, "speed": 0.30}],
                          one_way=True,
                          note=f"re-recorded from the executor's own pose "
                               f"{time.strftime('%Y-%m-%d')}, {hits}/{tries}")
                m.save()
                res["written"] = {"bearing": bearing, "dur": dur}
                save()
                return
    log("no candidate landed twice — leaving the map alone. A leg recorded "
        "from one lucky trip is what is already broken.")


if __name__ == "__main__":
    try:
        main(force="--force" in sys.argv)
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        save()
