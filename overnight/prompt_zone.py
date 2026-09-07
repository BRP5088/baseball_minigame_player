"""Map the PROMPT ZONE around the dealer: where does the game offer "Play ($50)"?

Agreed with the user 2026-09-07 after the occupancy grid and 3D mapping were
dropped. The last leg's failures are position and heading failures against a
target nobody has measured: the region in which the game offers the prompt.
This measures it directly, with the console as the only source of truth.

DESIGN
  Origin   the recorded goal leg's END pose, reached the way the 'recorded'
           arm reaches it: verified bar_jukebox, then walk_link as recorded.
  Grid     5 rows (lateral, right positive) x 5 columns (forward), spaced
           STEP_UNITS walk-units apart, in the leg's own frame: forward is
           the leg's net bearing (86.1 deg over 0.79 units), lateral is +90.
  Moves    turn-then-walk only (the shape that survives GRAVEYARD): turn to
           the world bearing, push STEP_UNITS at UNIT_SPEED, where §6 says the
           response is linear. Positions are NOMINAL -- §6's spread is real --
           so every point also records its bearing, keypoints and frame.
  Per point  HEADINGS around the leg's direction; at each: the mask verdict
           (score, ink, at_table), the OCR read (tools/prompt_ocr_ab.read),
           the compass bearing, ORB keypoints (< WEDGED_MAX = pressed into
           geometry, so "no prompt" there is not evidence), and one frame.
  Rows     one route walk per row (reset -> jukebox -> leg -> offset to the
           row start), so dead-reckoning drift never spans more than five
           points. Each row is a child process under an external ceiling.

NEVER PRESSES SQUARE. A True prompt verdict is recorded, nothing else.

    nohup .venv/bin/python -B overnight/prompt_zone.py > overnight/prompt_zone.log 2>&1 &
      -> overnight/prompt_zone.json (saved after every row), frames in
         overnight/prompt_zone_frames/pz_r<row>_c<col>_h<k>_<ms>.jpg
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
# FIRST RUN (2026-09-07): a 5x5 grid at 0.15u put the row start 0.30u off the
# endpoint -- nearly half the leg's length -- straight into the furniture: the
# character wedged (2 keypoints) and the camera, pinned in geometry, could not
# turn, so every heading read the same bearing. The zone is bounded by
# geometry within 0.3u. Smaller grid, and every push is wedge-checked.
ROWS = (-1, 0, 1)                 # lateral, right positive
COLS = (-2, -1, 0, 1, 2)          # forward
STEP_UNITS = 0.10                 # walk-units between grid points
UNIT_SPEED = 0.35                 # §6: linear response, spread 15px at 0.40s
HEADING_OFFSETS = (-40, -20, 0, 20, 40)
SETTLE = 0.5
TIMEOUT = 900                     # per row, enforced from OUTSIDE (10.14)
SETUP_ATTEMPTS = 9
OUT = os.path.join(HERE, "prompt_zone.json")
SHOTS = os.path.join(HERE, "prompt_zone_frames")
WEDGED_MAX = 50                   # §8(f): pressed into geometry reads 9-11, open space 744+


def leg_frame(m):
    """(forward_bearing, length) of the recorded goal leg's net vector."""
    fx = fy = 0.0
    for s in m.steps_for(START, GOAL):
        d = s["dur"] * s.get("speed", 0.2)
        b = math.radians(s["bearing"])
        fx += d * math.sin(b)
        fy += d * math.cos(b)
    return math.degrees(math.atan2(fx, fy)) % 360, math.hypot(fx, fy)


def _kp():
    import compass
    import places
    try:
        return len(places.keypoints(compass.fast_capture().convert("RGB")))
    except Exception:
        return None


def push(ws, bearing, units, log):
    """Turn to `bearing`, walk `units` forward; back off stick-direct if wedged.

    Returns (view_change, wedged). A wedged character's camera does not turn,
    so the back-off cannot go through turn_to: it drives left_y backwards.
    """
    import analog_replay as ar
    got = ws.turn_to(bearing, log=lambda *a: None)
    time.sleep(0.2)
    change = ws.walk_forward(UNIT_SPEED, units / UNIT_SPEED)
    time.sleep(SETTLE)
    kp = _kp()
    wedged = kp is not None and kp < WEDGED_MAX
    log(f"      push {units:.2f}u at {bearing:.0f} (turned to {got!s:6}): view change {change:.1f}, kp {kp}"
        f"{'  WEDGED -- backing off' if wedged else ''}")
    if wedged:
        ar.send([f"left_y {ar.to_axis(UNIT_SPEED)}", "left_x 0"])
        time.sleep(units / UNIT_SPEED)
        ar.send(["left_x 0", "left_y 0"])
        time.sleep(SETTLE)
    return change, wedged


def measure_point(row, col, forward, log):
    import compass
    import places
    import table_prompt as tp
    import walk_steps as ws
    import prompt_ocr_ab as ocr
    os.makedirs(SHOTS, exist_ok=True)
    out = []
    kp0 = _kp()
    if kp0 is not None and kp0 < WEDGED_MAX:
        log(f"      r{row:+d} c{col:+d}: WEDGED ({kp0} keypoints) -- point recorded as blocked, no headings")
        return [{"row": row, "col": col, "blocked": True, "keypoints": kp0}]
    for k, off in enumerate(HEADING_OFFSETS):
        h = (forward + off) % 360
        got = ws.turn_to(h, log=lambda *a: None)
        time.sleep(SETTLE)
        img = compass.fast_capture().convert("RGB")
        bearing = compass.read_bearing(img)
        turned = (bearing is not None and abs((bearing - h + 180) % 360 - 180) <= 10)
        score, ink, at = float(tp.score(img)), float(tp.ink(img)), bool(tp.at_table(img))
        words = ocr.read(img)["words"]
        try:
            kp = len(places.keypoints(img))
        except Exception:
            kp = None
        f = os.path.join(SHOTS, f"pz_r{row:+d}_c{col:+d}_h{k}_{int(time.time() * 1000)}.jpg")
        img.save(f, quality=85)
        rec = {"row": row, "col": col, "heading_cmd": round(h, 1), "bearing": bearing,
               "mask_score": round(score, 3), "ink": round(ink, 4), "at_table_mask": at,
               "ocr_words": words, "prompt": at or words >= 2,
               "keypoints": kp, "wedged": (kp is not None and kp < WEDGED_MAX),
               "turned": turned, "frame": os.path.relpath(f, ROOT)}
        out.append(rec)
        log(f"      r{row:+d} c{col:+d} h{k} cmd {h:5.1f} read {bearing!s:6} mask {score:6.3f}/{ink:.4f} "
            f"ocr {words} kp {kp!s:5} -> {'PROMPT' if rec['prompt'] else '-'}{' WEDGED' if rec['wedged'] else ''}{'' if turned else ' CAMERA-DID-NOT-TURN'}")
    return out


def one_row(row):
    import graph_walk as gw
    import reset_env
    import walk_steps as ws
    import worldmap as wm

    def log(m):
        print(m, flush=True)

    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()
    t0 = time.time()
    if not gw.go_to_node_verified(m, START, log=log, attempts=SETUP_ATTEMPTS,
                                  shots=SHOTS, start_hint=gw.SPAWN):
        return {"row": row, "reached": False, "setup_seconds": round(time.time() - t0, 1)}
    forward, length = leg_frame(m)
    lateral = (forward + 90) % 360
    log(f"  row {row:+d}: leg frame forward {forward:.1f} (net {length:.2f}u), lateral {lateral:.1f}")
    gw.walk_link(m, START, GOAL, log=log)              # the recorded leg, as the 'recorded' arm walks it
    time.sleep(SETTLE)
    # to the row start: lateral offset, then back to the first column. A wedge
    # on the way ends the row: the points beyond are geometry, and that is data.
    points = []
    if row:
        _c, w = push(ws, lateral if row > 0 else (lateral + 180) % 360, abs(row) * STEP_UNITS, log)
        if w:
            return {"row": row, "reached": True, "setup_seconds": round(time.time() - t0, 1),
                    "forward": round(forward, 1), "blocked_at": "lateral offset", "points": points}
    if COLS[0]:
        _c, w = push(ws, (forward + 180) % 360, abs(COLS[0]) * STEP_UNITS, log)
        if w:
            return {"row": row, "reached": True, "setup_seconds": round(time.time() - t0, 1),
                    "forward": round(forward, 1), "blocked_at": "back to first column", "points": points}
    for i, col in enumerate(COLS):
        if i:
            _c, w = push(ws, forward, STEP_UNITS, log)
            if w:
                points.append({"row": row, "col": col, "blocked": True})
                log(f"      r{row:+d} c{col:+d}: geometry -- row ends here")
                break
        points.extend(measure_point(row, col, forward, log))
    return {"row": row, "reached": True, "setup_seconds": round(time.time() - t0, 1),
            "forward": round(forward, 1), "points": points}


def main():
    def log(m):
        print(m, flush=True)
    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")
    res = {"question": "where does the game offer the dealer prompt, around the recorded leg's endpoint",
           "grid": {"rows": ROWS, "cols": COLS, "step_units": STEP_UNITS, "unit_speed": UNIT_SPEED,
                    "heading_offsets": HEADING_OFFSETS}, "rows": []}
    for row in ROWS:
        r, secs = _harness.run_trial(__file__, str(row), TIMEOUT, log=log)
        if r is None:
            log(f"[row {row:+d}] INVALID after {secs:.0f}s (ceiling, crash, or the stream went down)")
            res["rows"].append({"row": row, "reached": None, "seconds": secs})
        elif not r.get("reached"):
            log(f"[row {row:+d}] INVALID: never reached {START} (setup {r['setup_seconds']:.0f}s)")
            res["rows"].append(r)
        else:
            n = sum(p.get("prompt", False) for p in r["points"])
            log(f"[row {row:+d}] {n}/{len(r['points'])} checks saw the prompt in {secs:.0f}s")
            res["rows"].append(r)
        _harness.save_result(OUT, res)
    log("\n  prompt checks per point (of 5 headings), W = wedged at 3+ headings; rows = lateral, cols = forward:")
    log("         " + "".join(f"c{c:+d}   " for c in COLS))
    for r in res["rows"]:
        if not r.get("reached"):
            log(f"  r{r['row']:+d}   (no data)")
            continue
        cells = []
        for c in COLS:
            pts = [p for p in r["points"] if p["col"] == c]
            if not pts:
                cells.append("  --   "); continue
            if any(p.get("blocked") for p in pts):
                cells.append("BLOCK  "); continue
            n = sum(p.get("prompt", False) for p in pts)
            t = sum(p.get("turned", False) for p in pts)
            cells.append(f"{n}/5 t{t} ")
        log(f"  r{r['row']:+d}   " + "".join(cells))
    log(f"\n  -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        print(json.dumps(one_row(int(sys.argv[2]))), flush=True)
    else:
        main()
