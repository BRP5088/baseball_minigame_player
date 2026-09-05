"""Verify position against recorded frames at points that are visually unique.

WHY ONLY SOME POINTS
--------------------
Matching the live view against the recording does not work everywhere. Scanning
the whole route, only 10 of 32 sampled moments are SEPARABLE — meaning the worst
match at that place still beats the best match anywhere else on the route. The
rest are ambiguous: the game is full of repeated doorframes and similar
corridors, and a confident match at the wrong one is worse than no match.

Where the separable ones fall is itself the useful result:

  t = 9.1 - 13.2   seven anchors, gaps up to +0.44  (office, stairs, landing)
  t = 14.7 - 20.8  NONE                             (corridor and street)
  t = 22.3 - 23.9  three anchors, gaps +0.07..+0.10 (inside the bar)

The unanchorable middle is exactly the stretch where the route loses itself, so
this cannot fix the drift. What it can do is DETECT it: a run that fails its
anchor has gone wrong at a known point, which turns a confidently wrong arrival
into a failure that can be measured and retried.

Thresholds are the midpoint between the worst same-place score and the best
elsewhere score, both measured, not guessed.
"""

import glob
import json
import os
import time

from PIL import Image

import analog_replay as ar
import compass
import turn_curve as tc
import visual_replay as vr

DEMO = "demos/walk_20260827_214446"
ANCHORS = "route_anchors.json"


def _frame_at(t):
    best = None
    for f in glob.glob(os.path.join(DEMO, "f_*.jpg")):
        ft = float(os.path.basename(f)[2:-4])
        if best is None or abs(ft - t) < abs(best[0] - t):
            best = (ft, f)
    return best[1]


def load():
    """[{t, near, far, gap, threshold}] for every separable anchor."""
    out = json.load(open(ANCHORS))
    for a in out:
        a["threshold"] = round((a["near"] + a["far"]) / 2.0, 3)
    return out


def check(t, threshold, sweep=(-24, -12, 0, 12, 24), log=print):
    """Sweep the camera a little and report the best match with the anchor.

    The sweep exists because the character can be in the right PLACE with the
    camera a little off, and a straight comparison would call that a miss. It is
    deliberately narrow: a wide sweep would eventually find something that
    correlates somewhere, which is the failure this whole module is built to
    avoid.
    """
    want = Image.open(_frame_at(t))
    start = compass.read_bearing(compass.fast_capture())
    if start is None:
        return None, None
    best = (-2.0, None)
    for d in sweep:
        target = (start + d) % 360
        _turn(target)
        img = compass.fast_capture()
        s = vr.offset(img, want)[2]
        if s > best[0]:
            best = (s, compass.read_bearing(img))
    _turn(start)
    log(f"      anchor t={t}: best {best[0]:+.3f} vs threshold {threshold:+.3f} "
        f"-> {'MATCH' if best[0] >= threshold else 'no match'}")
    return best[0], best[0] >= threshold


def _turn(target, tolerance=3.5, max_steps=8):
    for _ in range(max_steps):
        now = compass.read_bearing(compass.fast_capture())
        if now is None:
            return
        e = (target - now + 540) % 360 - 180
        if abs(e) <= tolerance:
            return
        mag, secs = tc.plan_turn(e)
        if mag == 0.0:
            return
        ar.send([f"right_x {ar.to_axis(mag if e > 0 else -mag)}",
                 "right_y 0", "left_x 0", "left_y 0"])
        time.sleep(secs)
        ar.send(["right_x 0"])
        time.sleep(0.25)
