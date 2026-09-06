"""Recover travel distance from vision alone, and check it against the stick.

WHY IT IS NEEDED. A drive recorded by record_drive.py has a HEADING for every
frame (the game's compass) but no stick input: pygame is deliberately absent
from this project's requirements, so a controller cannot be read. Heading
without distance gives a direction and no map.

THE METHOD, and it rests on a constant this project already measured. Between
two frames the matched features shift for two reasons: the camera turned, and
the camera moved. The turn's contribution is known -- 18.6-20.8 px per degree at
this geometry, corroborated by camera_fov.json's 1920/102 = 18.8 -- and the yaw
itself comes from the compass. So:

    predicted rotational shift = |yaw change| * PX_PER_DEG
    residual                   = observed median shift - predicted
    residual                   is translation, in pixels

THE CONTROL IS THE WHOLE POINT. Four archived recordings carry BOTH frames and
the real stick input, so the visually-derived distance can be scored against the
stick-derived one on identical data. Without that this would be another
plausible number nobody checked.
"""
import glob
import json
import math
import os
import sys

import cv2
import numpy as np

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
PX_PER_DEG = 18.8          # camera_fov.json: 1920 / 102 deg
DEAD = 0.08

orb = cv2.ORB_create(nfeatures=1500)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def kp(path):
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    h, w = g.shape[:2]
    m = np.full((h, w), 255, np.uint8)
    m[:int(h*.10), :] = 0; m[int(h*.90):, :] = 0; m[:, :int(w*.28)] = 0
    return orb.detectAndCompute(g, m)


def shift(k1, d1, k2, d2):
    """Median pixel displacement of RANSAC-verified matches, or None."""
    if d1 is None or d2 is None or len(d1) < 12 or len(d2) < 12:
        return None
    m = bf.match(d1, d2)
    if len(m) < 12:
        return None
    p1 = np.float32([k1[x.queryIdx].pt for x in m])
    p2 = np.float32([k2[x.trainIdx].pt for x in m])
    _, mask = cv2.estimateAffinePartial2D(p1.reshape(-1,1,2), p2.reshape(-1,1,2),
                                          method=cv2.RANSAC,
                                          ransacReprojThreshold=6.0)
    if mask is None or mask.sum() < 12:
        return None
    sel = mask.ravel().astype(bool)
    return float(np.median(np.linalg.norm(p2[sel] - p1[sel], axis=1)))


def stick_distance(run, ts):
    """Ground truth: cumulative |ly| dt at each frame time."""
    inp = json.load(open(os.path.join(ROOT, "demos", run, "input.json")))
    cum, acc, prev = [], 0.0, inp[0]["t"]
    for s in inp:
        ly = s["axes"].get("ly", 0.0)
        if abs(ly) > DEAD:
            acc += abs(ly) * (s["t"] - prev)
        cum.append((s["t"], acc)); prev = s["t"]
    out, i = [], 0
    for t in ts:
        while i + 1 < len(cum) and cum[i+1][0] <= t:
            i += 1
        out.append(cum[i][1])
    return out


def main():
    import re
    runs = [d for d in sorted(os.listdir(os.path.join(ROOT, "demos")))
            if os.path.exists(os.path.join(ROOT, "demos", d, "input.json"))]
    bearings = json.load(open(os.path.join(ROOT, "bearings.json")))
    print(f"{len(runs)} recordings carry BOTH frames and real stick input\n")
    print(f"{'recording':38} {'frames':>7} {'r':>7} {'slope':>8}  visual vs stick")
    for run in runs:
        fs = sorted(glob.glob(os.path.join(ROOT, "demos", run, "*.jpg")))
        bs = bearings.get(f"demos/{run}")
        if not bs or len(bs) != len(fs):
            print(f"  {run:36} no headings"); continue
        ts = [float(re.search(r"f_(\d+\.\d+)", os.path.basename(f)).group(1))
              for f in fs]
        truth = stick_distance(run, ts)
        prev, vis, gt = None, [], []
        for i, f in enumerate(fs):
            k, d = kp(f)
            if prev is not None and bs[i] is not None and bs[i-1] is not None:
                s = shift(prev[0], prev[1], k, d)
                if s is not None:
                    dyaw = abs((bs[i] - bs[i-1] + 180) % 360 - 180)
                    resid = max(0.0, s - dyaw * PX_PER_DEG)
                    vis.append(resid)
                    gt.append(max(0.0, truth[i] - truth[i-1]))
            prev = (k, d)
        if len(vis) < 30:
            print(f"  {run:36} too few pairs"); continue
        v, g = np.array(vis), np.array(gt)
        r = float(np.corrcoef(v, g)[0, 1]) if g.std() > 0 else float("nan")
        slope = float(np.polyfit(g, v, 1)[0]) if g.std() > 0 else float("nan")
        print(f"  {run:36} {len(v):7} {r:7.3f} {slope:8.1f}  "
              f"{'TRACKS' if r > 0.5 else 'DOES NOT TRACK'}")
    print("\n  r is the correlation between the visually-derived step and the")
    print("  stick-derived one on the SAME frames. Above ~0.5 means a drive")
    print("  with no stick log can still be placed; below means it cannot,")
    print("  and a driven session would need the controller logged instead.")


main()
