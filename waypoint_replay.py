"""Replay a walk the way it was performed: AIM at a target, then MOVE.

THE MODEL, as described by the person who recorded it
-----------------------------------------------------
    "In the office, I didn't move until the reticle was on the door. I did that
     by moving the camera, not the player. Then I moved towards the open
     doorway, then moved it to Wanda, then to an NPC on the bar, then another
     NPC that generally stays still, then the table."

Aim, then move. Every aim phase re-anchors the camera on a landmark before the
next stretch of walking, which is why a human can do this reliably and why
replaying inputs continuously cannot: error accumulates through the walk with
nothing to re-anchor against.

The recording segments cleanly this way. The office sequence is 5.77-9.07s of
camera-only movement — over three seconds with the left stick untouched — and
walking does not begin until 9.31s.

WHY AIM PHASES ARE SERVOED AND WALK PHASES ARE NOT
--------------------------------------------------
An aim phase has a definite goal: the view at the end of it. That is a picture,
and the live view can be steered until it matches. A walk phase has no such
target — it is just travel — so it replays its recorded sticks directly, and
stays short enough that little error accumulates before the next re-anchor.

SOME TARGETS MOVE. Wanda and the bar NPCs are not fixed scenery, so a match
will sometimes be imperfect. Aim phases therefore stop on "close enough or out
of budget" rather than insisting, and a missed match costs alignment, not the
run.
"""

import json
import math
import os
import time

from PIL import Image

import analog_replay as ar
import visual_replay as vr

DEADZONE = 0.15
MIN_SEG = 0.15

AIM_TOLERANCE_PX = 4          # thumbnail px; below this the views agree
AIM_MAX_STEPS = 12
AIM_STEP_SEC = 0.10
AIM_GAIN_X = 0.030
AIM_GAIN_Y = 0.024
AIM_MAX_STICK = 0.55


def segments(demo_dir, t0=5.0, t1=26.5):
    """Split the recording into aim / walk / both / still phases."""
    inp = json.load(open(os.path.join(demo_dir, "input.json")))
    out, cur = [], None
    for s in inp:
        if not (t0 <= s["t"] <= t1):
            continue
        a = s["axes"]
        walking = math.hypot(a.get("lx", 0), a.get("ly", 0)) > DEADZONE
        aiming = abs(a.get("rx", 0)) > DEADZONE or abs(a.get("ry", 0)) > DEADZONE
        p = "both" if (walking and aiming) else \
            "walk" if walking else "aim" if aiming else "still"
        if cur and cur["p"] == p:
            cur["t1"] = s["t"]
        else:
            if cur:
                out.append(cur)
            cur = {"p": p, "t0": s["t"], "t1": s["t"]}
    if cur:
        out.append(cur)
    return [x for x in out if x["t1"] - x["t0"] >= MIN_SEG]


def aim_to(target_img, capture, log=print):
    """Steer the camera until the live view matches `target_img`.

    ABORTS IF THE ERROR GROWS. The correction sign is verified against shifted
    images offline, but the in-game sign convention is not something a static
    test can prove. If steering makes the match worse twice running, the sign
    is wrong for this axis and continuing would walk the camera away from the
    target — which is precisely how a replay ends up in the wrong room.
    """
    prev_err = None
    worse = 0
    for i in range(AIM_MAX_STEPS):
        live = capture()
        dx, dy, score = vr.offset(live, target_img)
        err = abs(dx) + abs(dy)
        if prev_err is not None and err > prev_err + 1:
            worse += 1
            if worse >= 2:
                log(f"      ABORTING aim: error grew {prev_err}->{err} twice; "
                    f"correction sign is wrong for this view")
                ar.send(["right_x 0", "right_y 0"])
                return False
        else:
            worse = 0
        prev_err = err
        if abs(dx) <= AIM_TOLERANCE_PX and abs(dy) <= AIM_TOLERANCE_PX:
            log(f"      aimed after {i} steps (dx={dx} dy={dy} score={score:.2f})")
            return True
        rx = max(-AIM_MAX_STICK, min(AIM_MAX_STICK, dx * AIM_GAIN_X))
        ry = max(-AIM_MAX_STICK, min(AIM_MAX_STICK, dy * AIM_GAIN_Y))
        ar.send([f"right_x {ar.to_axis(rx)}", f"right_y {ar.to_axis(ry)}",
                 "left_x 0", "left_y 0"])
        time.sleep(AIM_STEP_SEC)
        ar.send(["right_x 0", "right_y 0"])
        time.sleep(0.12)
    live = capture()
    dx, dy, score = vr.offset(live, target_img)
    log(f"      aim gave up (dx={dx} dy={dy} score={score:.2f}) — target may have moved")
    return False


def play_sticks(samples, t0, t1, log=None):
    """Replay the recorded sticks over a time range, at their original rate."""
    win = [s for s in samples if t0 <= s["t"] <= t1]
    if not win:
        return
    start = win[0]["t"]
    began = time.time()
    for s in win:
        a = s["axes"]
        ar.send([f"left_x {ar.to_axis(a.get('lx', 0))}",
                 f"left_y {ar.to_axis(a.get('ly', 0))}",
                 f"right_x {ar.to_axis(a.get('rx', 0))}",
                 f"right_y {ar.to_axis(a.get('ry', 0))}"])
        behind = (s["t"] - start) - (time.time() - began)
        if behind > 0:
            time.sleep(behind)
    ar.send(["left_x 0", "left_y 0", "right_x 0", "right_y 0"])


def replay(demo_dir, capture, log=print):
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    frames = vr.load_frames(demo_dir)
    segs = segments(demo_dir)
    log(f"  {len(segs)} phases to replay")

    for i, seg in enumerate(segs, 1):
        dur = seg["t1"] - seg["t0"]
        if seg["p"] == "still":
            continue
        if seg["p"] == "aim":
            # steer to the view this aim phase ENDED on — that is the target
            ft, fp = min(frames, key=lambda f: abs(f[0] - seg["t1"]))
            log(f"    [{i}] AIM to the view at {ft:.2f}s ({dur:.2f}s recorded)")
            aim_to(Image.open(fp), capture, log=log)
        else:
            log(f"    [{i}] {seg['p'].upper()} {dur:.2f}s")
            play_sticks(samples, seg["t0"], seg["t1"])
    ar.clear()
    log("  done")
