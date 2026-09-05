"""Walk to the bar and map what is around it, slowly and deliberately.

Targets the OVERSHOT class: a quarter of route failures are the character
standing somewhere detailed the map cannot name. This goes and looks at that
ground on purpose, instead of catching one frame of it by accident.

Coverage, not speed. Nothing is added to the map — frames go to disk for an
offline pass to judge.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

START = "bar_pool_room"          # the last node reliably reachable before trouble
FAN = [2.1, 340.0, 20.0, 60.0]   # the recorded heading, plus either side
STEPS_OUT = 4                    # short pushes per direction
OUT = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    import explore, graph_walk as gw, worldmap as wm, analog_replay as ar

    m = wm.WorldMap.load()
    e = explore.Explorer("bar_area", log=print)
    result = {"start": START, "legs": []}
    try:
        for bearing in FAN:
            print(f"\n=== fan {bearing:.0f} deg ===", flush=True)
            if not gw.go_to_node_verified(m, START, log=lambda *a: None):
                print("  could not reach the start node — skipping this arm")
                result["legs"].append({"bearing": bearing, "reached": False})
                continue
            e.sweep(note=f"at {START}, before fan {bearing:.0f}")
            for k in range(STEPS_OUT):
                e.step(bearing)
                e.sweep(note=f"fan {bearing:.0f}, step {k+1}")
            result["legs"].append({"bearing": bearing, "reached": True,
                                   "steps": STEPS_OUT})
            _harness.save_result(os.path.join(OUT, "map_unknown.json"), result)
    finally:
        try:
            ar.send(["clear"])
        except Exception:
            pass
        s = e.summary()
        result["summary"] = s
        _harness.save_result(os.path.join(OUT, "map_unknown.json"), result)
        print(f"\n--- {s['frames']} frames over {s['stops']} stops, "
              f"{s['unmapped_rich_views']} rich views the map cannot name ---")
        print(f"    {s['dir']}")
