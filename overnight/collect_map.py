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

import _harness
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
# MEASURED 2026-09-06, six headings from the spawn. push-inliers divided by
# that heading's own null-inliers: 0.10 0.11 0.26 0.30 0.34 against 0.82. The
# gate sits in the 0.49-wide gap between those two populations, which is what
# CLAUDE.md 10.4 requires and what frame delta could never provide here.
MOVED_MAX_RATIO = 0.50

# A RATIO NEEDS A DENOMINATOR WORTH DIVIDING BY. A null of 9 inliers means the
# view holds almost no structure -- pressed against geometry, or a dark frame --
# and 0/9 is noise, not "it moved". Below this the probe is UNMEASURABLE and is
# recorded as such rather than being scored. Section 8(f): a wedged frame holds
# 9-11 keypoints and the next lowest non-wedged frame holds 744, so this floor
# sits between two measured populations rather than inside one.
MIN_NULL_INLIERS = 100

# How far to travel between sample points. Longer than a probe, so points are
# genuinely different places rather than the same one measured twice.
TRAVEL_SEC = 1.4
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


def back(seconds, speed):
    """Walk back the same distance, so a point stays a point."""
    ar.send([f"left_y {int(abs(speed) * 32767)} {int(seconds * 1000)}"])
    time.sleep(seconds + 0.55)
    ar.send(["clear"])


def measure(do_push):
    """(frame delta, inliers) across an interval with or without a push.

    The NULL arm takes the identical capture pair and waits the identical time
    without pushing, so the two are comparable. Anything that changes on its own
    -- an NPC, a flickering light -- appears in both.
    """
    a = cap()
    if do_push:
        ar.send([f"left_y {int(-PROBE_SPEED * 32767)} {int(PROBE_SEC * 1000)}"])
    time.sleep(PROBE_SEC + 0.55)
    ar.send(["clear"])
    b = cap()
    return delta(a, b), inliers(a, b)


def log(m):
    print(m, flush=True)


def main():
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit("refusing to drive the console under BASEBALL_TEST_RUN")
    os.makedirs(OUT, exist_ok=True)
    ar.open_stream()
    samples = []
    prev_heading = None
    log(f"collecting {POINTS} points x {DIRECTIONS} directions")
    for i in range(POINTS):
        if i % RESET_EVERY == 0:
            log(f"  reset ({i}/{POINTS})")
            reset_env.reset_environment(log=lambda *a: None,
                                        progress_file="progress_testing.json")
            time.sleep(1.2)
        here = cap()
        base = compass.read_bearing(here)
        if base is None:
            # WITHOUT A HEADING THERE IS NO DIRECTION CONTROL, so every probe
            # would go the same way and be recorded as eight different ones.
            # That happened on the first trial run and produced a point whose
            # eight "directions" were one direction eight times.
            log("  no compass at this point — turning to re-acquire rather "
                "than probing eight times in one direction")
            for _ in range(6):
                ar.send(["right_x 12000 220"]); time.sleep(1.1)
                ar.send(["clear"])
                base = compass.read_bearing(cap())
                if base is not None:
                    break
            if base is None:
                log("  still no heading — skipping this point")
                continue
            here = cap()
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

            # PAIRED NULL AND PUSH, at this heading, in this order.
            #
            # An ABSOLUTE gate cannot work and that is measured, not assumed:
            # over six headings the null inlier count ranged 353-1366 and the
            # push 35-908, so the same number means "blocked" in one place and
            # "moved" in another. Dividing by THIS heading's own null removes
            # the local scene animation -- and an NPC wandering through the
            # shot lowers both halves, so it cannot fake a verdict either.
            n_d, n_i = measure(False)
            p_d, p_i = measure(True)
            ratio = p_i / max(n_i, 1)
            if n_d <= DEAD_DELTA and p_d <= DEAD_DELTA:
                verdict = "INVALID"          # the stream, not the path
            elif n_i < MIN_NULL_INLIERS:
                verdict = "unmeasurable"     # nothing to divide by
            elif ratio >= MOVED_MAX_RATIO:
                verdict = "blocked"
            else:
                verdict = "free"
                back(PROBE_SEC, PROBE_SPEED)   # return, so the point stays fixed

            rec["probes"].append({"dir": k, "want": want, "ratio": round(ratio, 3),
                                  "null_delta": round(n_d, 2), "null_inl": n_i,
                                  "push_delta": round(p_d, 2), "push_inl": p_i,
                                  "verdict": verdict})
            log(f"     dir {k} @{'--' if want is None else f'{want:5.1f}'}  "
                f"null {n_i:4} push {p_i:4}  ratio {ratio:5.2f}  {verdict}")
            if verdict == "INVALID":
                log("     stream is not updating — stopping rather than "
                    "recording a map of nothing")
                _harness.save_result(os.path.join(OUT, "probes.json"), samples)
                return
        samples.append(rec)
        _harness.save_result(os.path.join(OUT, "probes.json"), samples)

        # TRAVEL TO A NEW POINT. Without this every "point" is the same place:
        # the probe walks back after each free direction, so nothing ever moves,
        # and a first run of 24 points collected 24 samples of the spawn. Caught
        # by the user noticing every photo was the office.
        #
        # It walks a FREE direction, preferring one it has not just come from,
        # so coverage follows open space instead of repeatedly testing a wall.
        free = [q for q in rec["probes"] if q["verdict"] == "free"
                and q["want"] is not None]
        if not free:
            log("  nowhere free to go from here — resetting")
            reset_env.reset_environment(log=lambda *a: None,
                                        progress_file="progress_testing.json")
            time.sleep(1.2)
            continue
        # furthest from the reverse of the way we arrived, i.e. keep going
        want = max(free, key=lambda q: min(
            abs((q["want"] - prev_heading + 180) % 360 - 180), 180)
            if prev_heading is not None else q["ratio"])["want"]
        st.turn_to(want, lambda: compass.read_bearing(cap()), cap,
                   log=lambda *a: None, tolerance=6.0)
        push(TRAVEL_SEC, PROBE_SPEED)
        prev_heading = want
        log(f"  travelled {TRAVEL_SEC:.1f}s along {want:.0f} to the next point")
    ar.send(["clear"])
    log(f"\n  {len(samples)} points -> {OUT}/probes.json")


main()
