"""Drive the character around and record where it CAN and CANNOT go.

WHY PROBING BEATS RECONSTRUCTION HERE. A metric map from monocular video needs
structure-from-motion, and this game's art makes that hard. But the question
navigation actually asks is not "what does the room look like" -- it is "can I
go that way". That is answerable directly: push the stick briefly and measure
whether the view changed. A push that moves nothing is an obstacle, whatever it
is made of, and it costs one second to find out.

It also handles the case reconstruction cannot. NPCs move. A wall probed twice a
minute apart is blocked both times; an NPC is blocked once. Nothing here assumes
the world is static, and re-probing is cheap.

WHAT IS RECORDED PER SAMPLE POINT
    the frame, the compass bearing, and for each probed direction:
    the frame delta and the ORB inlier count across the push.

    frame delta   standing still measures 0.9-6.4 (CLAUDE.md section 8g);
                  a dead stream measures 0.00 and is INVALID, not blocked.
    inliers       two frames of the same view share ~1500 (the ORB cap);
                  a walking pair shares a median of 751. High means nothing
                  moved.

Two independent signals, because on this project a single one has repeatedly
turned out to be measuring something else.

SAFETY. Turning is the only input measured never to move the character, so the
character is returned to its entry heading after every probe and walked BACK
along any direction that proved free. It resets to the spawn every RESET_EVERY
points, so a wander cannot compound. Nothing here presses a button: no menus,
no table, no money.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image

import analog_replay as ar
import compass
import places
import reset_env
import slow_traverse as st

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_probe")
PROBE_SEC = 0.45          # long enough to move, short enough to stop safely
PROBE_SPEED = 0.35        # well inside the linear range (section 6)
DIRECTIONS = 8            # every 45 degrees
POINTS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
RESET_EVERY = 6
STILL_DELTA = 6.5         # at or below this the view did not change
DEAD_DELTA = 0.35         # at or below this the STREAM is dead, not the path


def cap():
    return compass.fast_capture()


def delta(a, b):
    a = np.asarray(a.convert("L"), float); b = np.asarray(b.convert("L"), float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean())


def inliers(a, b):
    import cv2
    (k1, d1), (k2, d2) = places.keypoints(a), places.keypoints(b)
    if d1 is None or d2 is None or len(d1) < 8 or len(d2) < 8:
        return 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    m = bf.match(d1, d2)
    if len(m) < 8:
        return 0
    p1 = np.float32([k1[x.queryIdx].pt for x in m]).reshape(-1, 1, 2)
    p2 = np.float32([k2[x.trainIdx].pt for x in m]).reshape(-1, 1, 2)
    _, mask = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC,
                                          ransacReprojThreshold=6.0)
    return 0 if mask is None else int(mask.sum())


def push(seconds, speed):
    """One continuous forward push. Forward is left_y NEGATIVE."""
    ar.send([f"left_y {int(-abs(speed) * 32767)} {int(seconds * 1000)}"])
    time.sleep(seconds + 0.55)          # let the character settle before capture
    ar.send(["clear"])


def log(m):
    print(m, flush=True)


def main():
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit("refusing to drive the console under BASEBALL_TEST_RUN")
    os.makedirs(OUT, exist_ok=True)
    ar.open_stream()
    samples = []
    log(f"collecting {POINTS} points x {DIRECTIONS} directions")
    for i in range(POINTS):
        if i % RESET_EVERY == 0:
            log(f"  reset ({i}/{POINTS})")
            reset_env.reset_environment(log=lambda *a: None,
                                        progress_file="progress_testing.json")
            time.sleep(1.2)
        here = cap()
        base = compass.read_bearing(here)
        stamp = int(time.time() * 1000)
        fp = os.path.join(OUT, f"p{stamp}.jpg")
        here.convert("RGB").save(fp, quality=88)
        rec = {"stamp": stamp, "frame": os.path.basename(fp),
               "bearing": base, "probes": []}
        log(f"  point {i+1}/{POINTS}  bearing "
            f"{'--' if base is None else f'{base:.1f}'}")
        for k in range(DIRECTIONS):
            want = None if base is None else (base + k * (360 / DIRECTIONS)) % 360
            if want is not None:
                st.turn_to(want, lambda: compass.read_bearing(cap()), cap,
                           log=lambda *a: None, tolerance=6.0)
            a = cap()
            push(PROBE_SEC, PROBE_SPEED)
            b = cap()
            dl, inl = delta(a, b), inliers(a, b)
            if dl <= DEAD_DELTA:
                verdict = "INVALID"          # the stream, not the path
            elif dl <= STILL_DELTA:
                verdict = "blocked"
            else:
                verdict = "free"
                push(PROBE_SEC, -PROBE_SPEED)   # walk back, keep the point fixed
            rec["probes"].append({"dir": k, "want": want, "delta": round(dl, 2),
                                  "inliers": inl, "verdict": verdict})
            log(f"     dir {k} @{'--' if want is None else f'{want:5.1f}'}  "
                f"delta {dl:6.2f}  inliers {inl:4}  {verdict}")
            if verdict == "INVALID":
                log("     stream is not updating — stopping rather than "
                    "recording a map of nothing")
                json.dump(samples, open(os.path.join(OUT, "probes.json"), "w"),
                          indent=1)
                return
        samples.append(rec)
        json.dump(samples, open(os.path.join(OUT, "probes.json"), "w"), indent=1)
    ar.send(["clear"])
    log(f"\n  {len(samples)} points -> {OUT}/probes.json")


main()
