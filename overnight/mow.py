"""Walk straight lines, capturing continuously. Data a 3D model can be built from.

WHY THIS EXISTS. Two reconstructions failed and both failed the same way: the
camera did not MOVE. A hand-driven office pass was 61% turning and 17% walking,
with a median of ZERO translation across three frames, and its reconstruction
kept 3 points of 196,198 tracks. That was the correct answer -- a camera that
pivots gathers no depth, because the rays stay parallel and every distance fits.

Stitching photographs into a MODEL needs the camera in a different PLACE between
shots, not a different direction. From one spot you get a panorama, which is
flat. So this drives the one pattern that produces parallax: walk in a straight
line, capture the whole way, turn only at the ends.

    walk LINE_SEC forward, capturing at HZ ......... translation, the useful part
    turn 90, step across, turn 90 ................. the corner, unavoidable
    repeat on a parallel line

NOTHING HERE PROBES. The explorer's push-measure-walk-back cycle is the opposite
of what a reconstruction wants: it returns to where it started, so consecutive
frames share no baseline. This never goes back.

BLOCKED IS HANDLED BY TURNING, NOT BY MEASURING. If a line stops making the view
change, something is in the way; it turns and starts a new line rather than
grinding. The frame delta is enough for that -- it needs to tell "moving" from
"stopped dead", not "moving" from "moving slightly less", and CLAUDE.md section
8(g) puts standing still at 0.91-6.41 against a dead stream's 0.00.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import _harness
import analog_replay as ar
import compass
import reset_env
import slow_traverse as st

MINUTES = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
NAME = sys.argv[2] if len(sys.argv) > 2 else "mow"

HZ = 5.0
SPEED = 0.35               # inside section 6's linear range
LINE_SEC = 6.0             # a long straight run: this is where the parallax is
STEP_ACROSS_SEC = 1.2      # the offset between parallel lines
STALL_DELTA = 6.5          # below this the view stopped changing -> turn
STALL_FRAMES = 6           # consecutive, before giving up on the line
RESET_EVERY_LINES = 8

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drives",
                   f"{time.strftime('%Y%m%d_%H%M%S')}_{NAME}")
META = os.path.join(OUT, "meta.json")


def cap():
    return compass.fast_capture()


def delta(a, b):
    a = np.asarray(a.convert("L"), float); b = np.asarray(b.convert("L"), float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean())


def log(m):
    print(m, flush=True)


def main():
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit("refusing to drive the console under BASEBALL_TEST_RUN")
    os.makedirs(OUT, exist_ok=True)
    ar.open_stream()
    meta, t0, lines, stalls = [], time.time(), 0, 0
    prev, n = None, 0

    def shoot():
        """One frame, its heading and the time. Called throughout a push."""
        nonlocal prev, n
        img = cap()
        t = time.time() - t0
        fn = f"f_{t:07.2f}.jpg"
        img.convert("RGB").save(os.path.join(OUT, fn), quality=88)
        d = None if prev is None else delta(prev, img)
        prev = img
        meta.append({"t": round(t, 2), "frame": fn,
                     "bearing": compass.read_bearing(img), "delta": d,
                     # The stick is KNOWN here rather than read: this script
                     # commands it, so there is no controller to poll.
                     "stick": {"ly": -SPEED, "lx": 0.0}})
        n += 1
        if n % 50 == 0:
            _harness.save_result(META, {"room": NAME, "hz": HZ, "complete": False,
                                        "frames": meta})
        return d

    log(f"mowing for {MINUTES:.0f} minutes into {OUT}")
    reset_env.reset_environment(log=lambda *a: None,
                               progress_file="progress_testing.json")
    time.sleep(1.2)

    while (time.time() - t0) / 60.0 < MINUTES:
        if lines and lines % RESET_EVERY_LINES == 0:
            log("  reset")
            reset_env.reset_environment(log=lambda *a: None,
                                        progress_file="progress_testing.json")
            time.sleep(1.2)
            prev = None

        # ---- one straight line, capturing all the way -------------------
        head = compass.read_bearing(cap())
        ar.send([f"left_y {int(-SPEED*32767)} {int(LINE_SEC*1000)}"])
        t_line, stall = time.time(), 0
        while time.time() - t_line < LINE_SEC:
            d = shoot()
            if d is not None and d <= STALL_DELTA:
                stall += 1
                if stall >= STALL_FRAMES:
                    ar.send(["clear"])
                    stalls += 1
                    log(f"  line {lines+1}: stopped moving after "
                        f"{time.time()-t_line:.1f}s — turning")
                    break
            else:
                stall = 0
            time.sleep(max(0.0, 1.0/HZ - 0.12))
        ar.send(["clear"])
        time.sleep(0.4)
        lines += 1
        moved = sum(1 for m in meta[-int(LINE_SEC*HZ):]
                    if (m.get("delta") or 0) > STALL_DELTA)
        log(f"  line {lines}: {moved} frames of real movement "
            f"({(time.time()-t0)/60:.0f}/{MINUTES:.0f} min, {n} frames)")

        # ---- the corner: across, then parallel --------------------------
        if head is not None:
            st.turn_to((head + 90) % 360, lambda: compass.read_bearing(cap()),
                       cap, log=lambda *a: None, tolerance=8.0)
            ar.send([f"left_y {int(-SPEED*32767)} {int(STEP_ACROSS_SEC*1000)}"])
            for _ in range(int(STEP_ACROSS_SEC*HZ)):
                shoot(); time.sleep(max(0.0, 1.0/HZ - 0.12))
            ar.send(["clear"]); time.sleep(0.3)
            st.turn_to((head + 180) % 360, lambda: compass.read_bearing(cap()),
                       cap, log=lambda *a: None, tolerance=8.0)

    ar.send(["clear"])
    _harness.save_result(META, {"room": NAME, "hz": HZ, "complete": True,
                                "frames": meta})
    got = sum(1 for m in meta if m.get("bearing") is not None)
    mv = sum(1 for m in meta if (m.get("delta") or 0) > STALL_DELTA)
    log(f"\n  {n} frames over {lines} lines, {stalls} blocked")
    log(f"  with a heading: {got}/{n} ({100*got/max(n,1):.0f}%)")
    log(f"  frames where the view actually changed: {mv}/{n} "
        f"({100*mv/max(n,1):.0f}%)  <- this is what triangulation needs")
    log(f"  -> {OUT}")
    log(f"\n  ask Snoopy:  .venv/bin/python tools/ask_snoopy.py {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
