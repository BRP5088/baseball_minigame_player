"""(b) From the neighbouring table, where is the prompt? Record the path, walk by walk.

OPEN-22: the recorded goal leg lands at the round table beside the dealer's
two walks in three, with the dealer 60-70 deg to the LEFT of the leg's net
direction (86 deg). This harness lands there the same way, then searches:
for each of a few headings toward the dealer it pushes 0.10u at a time,
checking the prompt (correlation OR OCR) after every push, stops at the first
prompt, and records (heading, units). Every point is wedge-checked with a
real keypoint count, every push is written to disk as it happens, and a walk
that lands at the dealer's table (prompt already on screen) is recorded as
such and not searched. The measured paths become the recorded leg
bar_side_table -> dealer_table. NEVER PRESSES SQUARE.

    nohup .venv/bin/python -B overnight/side_table_leg.py > overnight/side_table_leg.log 2>&1 &
      -> overnight/side_table_leg.json (after every walk), side_table_leg_points.jsonl
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import _harness

START, GOAL = "bar_jukebox", "dealer_table"
WALKS = 4
HEADINGS = (15.0, 0.0, 30.0, 345.0)   # the dealer sits ~10-20 deg from the side-table pose
STEP_UNITS = 0.10
MAX_UNITS = 0.60
UNIT_SPEED = 0.35
SETTLE = 0.5
TIMEOUT = 1800
SETUP_ATTEMPTS = 9
OUT = os.path.join(HERE, "side_table_leg.json")
POINTS = os.path.join(HERE, "side_table_leg_points.jsonl")
SHOTS = os.path.join(HERE, "side_table_leg_frames")
WEDGED_MAX = 50


def _assert_inputs_live():
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise RuntimeError("BASEBALL_TEST_RUN is set inside a LIVE harness")


def prompt_now():
    """(prompt, mask_score, ocr_words, keypoints, bearing, frame_path) from a fresh capture."""
    import compass, places, table_prompt as tp
    import prompt_ocr_ab as ocr
    img = compass.fast_capture().convert("RGB")
    kps, _ = places.keypoints(img)
    os.makedirs(SHOTS, exist_ok=True)
    f = os.path.join(SHOTS, f"st_{int(time.time() * 1000)}.jpg"); img.save(f, quality=85)
    sc = float(tp.score(img)); words = ocr.read(img)["words"]
    return (sc >= tp.MATCH_MIN or words >= 2), sc, words, len(kps or ()), compass.read_bearing(img), os.path.relpath(f, ROOT)


def push_back(units):
    import analog_replay as ar
    ar.send([f"left_y {ar.to_axis(UNIT_SPEED)}", "left_x 0"]); time.sleep(units / UNIT_SPEED)
    ar.send(["left_x 0", "left_y 0"]); time.sleep(SETTLE)


def one_walk(walk):
    import graph_walk as gw, reset_env, walk_steps as ws, worldmap as wm, places
    def log(m): print(m, flush=True)
    _assert_inputs_live()
    reset_env.reset_environment(log=log, progress_file=None); time.sleep(1.2)
    m = wm.WorldMap.load(); t0 = time.time()
    if not gw.go_to_node_verified(m, START, log=log, attempts=SETUP_ATTEMPTS, shots=SHOTS, start_hint=gw.SPAWN):
        return {"walk": walk, "reached": False, "setup_seconds": round(time.time() - t0, 1)}
    gw.walk_link(m, START, GOAL, log=log); time.sleep(SETTLE)
    import compass
    img = compass.fast_capture().convert("RGB")
    room, score, margin = places.identify(img)
    p, sc, words, kp, brg, frame = prompt_now()
    rec = {"walk": walk, "stage": "landing", "identify": [room, score, round(margin, 2)], "prompt": p,
           "mask_score": round(sc, 3), "ocr_words": words, "keypoints": kp, "bearing": brg, "frame": frame}
    open(POINTS, "a").write(json.dumps(rec) + "\n")
    log(f"  walk {walk}: landed -- identify {room} {score:.0f}/{margin:.2f}, prompt {p}, kp {kp}, bearing {brg}")
    if p:
        return {"walk": walk, "reached": True, "landing": "dealer_table", "path": None, "points": [rec]}
    points, found = [rec], None
    for h in HEADINGS:
        _assert_inputs_live()
        got = ws.turn_to(h, log=lambda *a: None); time.sleep(0.2)
        walked = 0.0
        while walked < MAX_UNITS - 1e-9:
            ws.walk_forward(UNIT_SPEED, STEP_UNITS / UNIT_SPEED); time.sleep(SETTLE); walked += STEP_UNITS
            p, sc, words, kp, brg, frame = prompt_now()
            r = {"walk": walk, "stage": "search", "heading": h, "turned_to": got, "units": round(walked, 2),
                 "prompt": p, "mask_score": round(sc, 3), "ocr_words": words, "keypoints": kp, "bearing": brg, "frame": frame}
            points.append(r); open(POINTS, "a").write(json.dumps(r) + "\n")
            log(f"      heading {h:5.1f} (turned to {got!s:6}) {walked:.2f}u: mask {sc:.3f} ocr {words} kp {kp} -> {'PROMPT' if p else '-'}")
            if p:
                found = {"heading": h, "units": round(walked, 2)}; break
            if kp < WEDGED_MAX:
                log("      wedged -- this heading ends here"); break
        if found:
            break
        push_back(walked)                    # back to the landing point, stick-direct
    return {"walk": walk, "reached": True, "landing": ("bar_side_table" if room == "bar_side_table" else "unnamed"),
            "path": found, "points": points}


def main():
    def log(m): print(m, flush=True)
    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")
    res = {"question": "from the neighbouring table, which heading and how many units reach the prompt", "headings": HEADINGS,
           "step_units": STEP_UNITS, "max_units": MAX_UNITS, "walks": []}
    for walk in range(1, WALKS + 1):
        r, secs = _harness.run_trial(__file__, str(walk), TIMEOUT, log=log)
        if r is None:
            log(f"[walk {walk}] INVALID after {secs:.0f}s"); res["walks"].append({"walk": walk, "reached": None, "seconds": secs})
        elif not r.get("reached"):
            log(f"[walk {walk}] INVALID: never reached {START}"); res["walks"].append(r)
        else:
            log(f"[walk {walk}] landing {r['landing']}  path {r['path']}  ({secs:.0f}s)"); res["walks"].append(r)
        _harness.save_result(OUT, res)
    log(f"\n  -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        print(json.dumps(one_walk(int(sys.argv[2]))), flush=True)
    else:
        main()
