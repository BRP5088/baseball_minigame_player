"""PHASE 1 — capture reference frames at the EXECUTOR'S OWN verified poses.

Why: every route_*.jpg align_lateral aims at is a timestamped frame from a
HUMAN walk (38.23s, 45.49s, 52.76s, 61.89s into demos/walk3_full_20260828_...).
None is a pose the bot occupies, so at bar_pool_room alignment stalls at ~150px
against the stools — it is correcting toward somewhere it cannot stand.

Strictly non-destructive: originals are copied to places_backup_<stamp>/ before
anything is replaced, and a frame under MIN_KEYPOINTS is REJECTED rather than
adopted. A near-featureless reference matches every other blank frame; that is
how an upstairs door once scored 0.906 against the bar.
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

MIN_KEYPOINTS = 200
NODES = ["portrait_room", "bar_pool_room", "bar_jukebox"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase1")
os.makedirs(OUT, exist_ok=True)

result = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "nodes": {}, "notes": []}


def log(m):
    print(m, flush=True)
    result.setdefault("log", []).append(str(m))


def save(tag, obj=None):
    result["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _harness.save_result(os.path.join(OUT, "phase1_result.json"), result)


def main():
    import compass
    import graph_walk as gw
    import places
    import worldmap as wm

    m = wm.WorldMap.load()
    log(f"map: {len(m.links)} links, nodes {sorted(m.links)}")

    for node in NODES:
        entry = {"reached": False, "keypoints": None, "adopted": False}
        result["nodes"][node] = entry
        log(f"\n=== {node} ===")
        try:
            ok = gw.go_to_node_verified(m, node, log=log)
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            log(f"  go_to_node_verified raised: {entry['error']}")
            save("err")
            continue
        entry["reached"] = bool(ok)
        if not ok:
            log(f"  NOT verified at {node} — no capture (a frame from the wrong "
                f"place is worse than no frame)")
            save("miss")
            continue

        img = compass.fast_capture()
        _, desc = places.keypoints(img)
        n = 0 if desc is None else len(desc)
        entry["keypoints"] = n
        path = os.path.join(OUT, f"arrival_{node}.jpg")
        img.save(path)
        entry["frame"] = path
        entry["bearing"] = compass.read_bearing(img)
        log(f"  verified. arrival frame: {n} keypoints, bearing {entry['bearing']}")
        if n < MIN_KEYPOINTS:
            log(f"  REJECTED as a reference: {n} < {MIN_KEYPOINTS}. This is a "
                f"FINDING, not a failure — the bot's own landing spot is too "
                f"featureless to anchor on, so the fix is a standable pose "
                f"near it, not re-pointing alignment at this one.")
        save("cap")
    save("done")
    return result


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("interrupted")
        save("int")
    print("\n--- summary ---")
    for k, v in result["nodes"].items():
        print(f"  {k:16} reached={v['reached']}  keypoints={v['keypoints']}")
