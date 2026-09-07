"""Map the PROMPT ZONE around the dealer: where does the game offer "Play ($50)"?

Agreed with the user 2026-09-07 after the occupancy grid and 3D mapping were
dropped. The last leg's failures are position and heading failures against a
target nobody has measured: the region in which the game offers the prompt.
This measures it directly, with the console as the only source of truth.

DESIGN (third version; the two grids before it are recorded at the STAR
constant below)
  Origin   the recorded goal leg's END pose, reached the way the 'recorded'
           arm reaches it: verified bar_jukebox, then walk_link as recorded.
  Star     the endpoint is measured FIRST, then small moves relative to the
           camera facing the leg's direction (0.05u left/right, 0.10/0.20u
           back, 0.05u forward), stick-direct so a pinned camera cannot spoil
           the move, each wedge-checked with a back-off.
  Per point  HEADINGS around the leg's direction; at each: the mask verdict
           (score, ink, at_table), the OCR read (tools/prompt_ocr_ab.read),
           the compass bearing, whether the camera actually turned, ORB
           keypoints (< WEDGED_MAX = pressed into geometry), and one frame.
  Walks    one route walk per star, WALKS of them for consistency; each walk
           is a child process under an external ceiling, and every point is
           appended to prompt_zone_points.jsonl the moment it is measured.

NEVER PRESSES SQUARE. A True prompt verdict is recorded, nothing else.

    nohup .venv/bin/python -B overnight/prompt_zone.py > overnight/prompt_zone.log 2>&1 &
      -> overnight/prompt_zone.json (after every walk), prompt_zone_points.jsonl,
         frames in overnight/prompt_zone_frames/pz_w<walk>_x<dx>_y<dy>_h<k>_<ms>.jpg
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
# turn. SECOND RUN: 0.10u to the right of the endpoint is the chair; and the
# design measured nothing at the endpoint itself before moving. So: a STAR.
# The endpoint is measured FIRST, always; then small moves relative to the
# camera facing the leg's direction, each wedge-checked, each point written to
# disk the moment it is measured (10.16). Three walks for consistency.
WALKS = 3
UNIT_SPEED = 0.35                 # §6: linear response, spread 15px at 0.40s
HEADING_OFFSETS = (-40, -20, 0, 20, 40)
SETTLE = 0.5
TIMEOUT = 1800                    # per walk, enforced from OUTSIDE (10.14); today's setups reach 1000s
SETUP_ATTEMPTS = 9
OUT = os.path.join(HERE, "prompt_zone.json")
POINTS = os.path.join(HERE, "prompt_zone_points.jsonl")   # appended per point by the child
SHOTS = os.path.join(HERE, "prompt_zone_frames")
WEDGED_MAX = 50                   # §8(f): pressed into geometry reads 9-11, open space 744+
# The star, as (dx, dy) in walk-units relative to the endpoint, camera facing
# forward: dx right positive, dy forward positive. Visited in this order, each
# from the previous point, so the moves stay small.
STAR = ((0.0, 0.0), (-0.05, 0.0), (-0.10, 0.0), (0.0, 0.0), (0.05, 0.0), (0.0, 0.0),
        (0.0, -0.10), (0.0, -0.20), (0.0, 0.0), (0.0, 0.05))


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
    # places.keypoints returns (keypoints, descriptors) -- len() of that pair is
    # 2, which is what every "wedged" verdict in the first three runs was.
    try:
        kps, _des = places.keypoints(compass.fast_capture().convert("RGB"))
        return len(kps or ())
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


def measure_point(walk, xy, forward, log):
    row, col = walk, xy
    import compass
    import places
    import table_prompt as tp
    import walk_steps as ws
    import prompt_ocr_ab as ocr
    os.makedirs(SHOTS, exist_ok=True)
    out = []
    kp0 = _kp()
    if kp0 is not None and kp0 < WEDGED_MAX:
        log(f"      walk {walk} {col}: WEDGED ({kp0} keypoints) -- point recorded as blocked, no headings")
        return [{"walk": walk, "blocked": True, "keypoints": kp0}]
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
            kps, _des = places.keypoints(img)
            kp = len(kps or ())
        except Exception:
            kp = None
        f = os.path.join(SHOTS, f"pz_w{walk}_x{col[0]:+.2f}_y{col[1]:+.2f}_h{k}_{int(time.time() * 1000)}.jpg")
        img.save(f, quality=85)
        rec = {"walk": walk, "heading_cmd": round(h, 1), "bearing": bearing,
               "mask_score": round(score, 3), "ink": round(ink, 4), "at_table_mask": at,
               "ocr_words": words, "prompt": at or words >= 2,
               "keypoints": kp, "wedged": (kp is not None and kp < WEDGED_MAX),
               "turned": turned, "frame": os.path.relpath(f, ROOT)}
        out.append(rec)
        log(f"      w{walk} ({col[0]:+.2f},{col[1]:+.2f}) h{k} cmd {h:5.1f} read {bearing!s:6} mask {score:6.3f}/{ink:.4f} "
            f"ocr {words} kp {kp!s:5} -> {'PROMPT' if rec['prompt'] else '-'}{' WEDGED' if rec['wedged'] else ''}{'' if turned else ' CAMERA-DID-NOT-TURN'}")
    return out


def move_rel(ws, forward, dx, dy, log):
    """Stick-direct move of (dx right, dy forward) walk-units with the camera at `forward`.

    No turn for the move itself: a wedged camera cannot turn, and strafing keeps
    the heading. Returns (turned_ok, wedged)."""
    import analog_replay as ar
    got = ws.turn_to(forward, log=lambda *a: None)
    turned = got is not None and abs((got - forward + 180) % 360 - 180) <= 10
    time.sleep(0.2)
    dist = math.hypot(dx, dy)
    if dist > 0:
        secs = dist / UNIT_SPEED
        ar.send([f"left_x {ar.to_axis(UNIT_SPEED * dx / dist)}",
                 f"left_y {ar.to_axis(-UNIT_SPEED * dy / dist)}", "right_x 0", "right_y 0"])
        time.sleep(secs)
        ar.send(["left_x 0", "left_y 0"])
        time.sleep(SETTLE)
    kp = _kp()
    wedged = kp is not None and kp < WEDGED_MAX
    log(f"      move ({dx:+.2f}, {dy:+.2f})u camera {got!s:6}{'' if turned else ' NOT-TURNED'}: kp {kp}"
        f"{'  WEDGED -- backing off' if wedged else ''}")
    if wedged and dist > 0:
        ar.send([f"left_x {ar.to_axis(-UNIT_SPEED * dx / dist)}",
                 f"left_y {ar.to_axis(UNIT_SPEED * dy / dist)}"])
        time.sleep(secs)
        ar.send(["left_x 0", "left_y 0"])
        time.sleep(SETTLE)
    return turned, wedged


def one_walk(walk):
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
        return {"walk": walk, "reached": False, "setup_seconds": round(time.time() - t0, 1)}
    forward, length = leg_frame(m)
    log(f"  walk {walk}: leg frame forward {forward:.1f} (net {length:.2f}u)")
    gw.walk_link(m, START, GOAL, log=log)              # the recorded leg, as the 'recorded' arm walks it
    time.sleep(SETTLE)
    points, here = [], (0.0, 0.0)
    for (x, y) in STAR:
        dx, dy = x - here[0], y - here[1]
        turned, wedged = move_rel(ws, forward, dx, dy, log)
        if wedged:
            rec = {"walk": walk, "dx": x, "dy": y, "blocked": True, "turned": turned}
            points.append(rec); open(POINTS, "a").write(json.dumps(rec) + "\n")
            # we backed off, so we are still at `here`
            continue
        here = (x, y)
        for rec in measure_point(walk, (x, y), forward, log):
            rec.update({"dx": x, "dy": y, "turned_to_forward": turned})
            points.append(rec); open(POINTS, "a").write(json.dumps(rec) + "\n")
    return {"walk": walk, "reached": True, "setup_seconds": round(time.time() - t0, 1),
            "forward": round(forward, 1), "points": points}


def main():
    def log(m):
        print(m, flush=True)
    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")
    res = {"question": "where does the game offer the dealer prompt, around the recorded leg's endpoint",
           "design": {"star": STAR, "unit_speed": UNIT_SPEED, "heading_offsets": HEADING_OFFSETS, "walks": WALKS},
           "walks": []}
    for walk in range(1, WALKS + 1):
        r, secs = _harness.run_trial(__file__, str(walk), TIMEOUT, log=log)
        if r is None:
            log(f"[walk {walk}] INVALID after {secs:.0f}s (ceiling, crash, or the stream went down)")
            res["walks"].append({"walk": walk, "reached": None, "seconds": secs})
        elif not r.get("reached"):
            log(f"[walk {walk}] INVALID: never reached {START} (setup {r['setup_seconds']:.0f}s)")
            res["walks"].append(r)
        else:
            n = sum(p.get("prompt", False) for p in r["points"])
            log(f"[walk {walk}] {n} prompt checks over {len([p for p in r['points'] if not p.get('blocked')])} readings in {secs:.0f}s")
            res["walks"].append(r)
        _harness.save_result(OUT, res)
    log("\n  per star point: prompt checks / readings (turned), B = blocked, over all walks:")
    agg = {}
    for w in res["walks"]:
        for p in (w.get("points") or []):
            a = agg.setdefault((p["dx"], p["dy"]), {"n": 0, "prompt": 0, "turned": 0, "blocked": 0})
            if p.get("blocked"):
                a["blocked"] += 1
            else:
                a["n"] += 1; a["prompt"] += bool(p.get("prompt")); a["turned"] += bool(p.get("turned"))
    for (x, y), a in sorted(agg.items()):
        log(f"  ({x:+.2f}, {y:+.2f})  prompt {a['prompt']}/{a['n']}  turned {a['turned']}/{a['n']}  blocked x{a['blocked']}")
    log(f"\n  -> {OUT}  (per-point stream: {POINTS})")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        print(json.dumps(one_walk(int(sys.argv[2]))), flush=True)
    else:
        main()
