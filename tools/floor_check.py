"""Score a floor plan against the one thing a recording proves.

THE PLAYER WALKED THERE. Every cell the camera passed through is free floor --
not by inference, by the fact that a character occupied it. So a map that paints
the walked path as an obstacle is wrong, and the fraction it gets wrong is a
scalar that does not depend on anyone's opinion of the picture.

This exists because the fit was being chosen by eye, which is how this project
has repeatedly ended up with a confident wrong answer. Half-vs-half agreement
says the geometry is self-consistent; it cannot say the geometry is RIGHT. A
consistently wrong pitch smears every frame the same way and still agrees with
itself.

It is deliberately not folded into the fit's own objective. A score used to
choose the fit cannot also test it -- optimise against this and it stops being
evidence and becomes the thing being maximised.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_mosaic as fm


def check(drive, pitch, scale, quiet=False):
    meta, fr = fm.load(drive)
    fr = fm.dead_reckon(fr)
    probe = cv2.imread(os.path.join(drive, fr[0]["frame"]), cv2.IMREAD_GRAYSCALE)
    h, w = probe.shape[:2]
    rays = fm.floor_rays(w, h, pitch)

    px, py, pc = [], [], []
    for f in fr:
        img = cv2.imread(os.path.join(drive, f["frame"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        f["dir"] = drive
        a, b, c = fm.project([f], [img], pitch, scale, rays, w, h)
        px.append(a); py.append(b); pc.append(c)
    px = np.concatenate(px); py = np.concatenate(py); pc = np.concatenate(pc)
    lo = (np.percentile(px, 0.5), np.percentile(py, 0.5))
    hi = (np.percentile(px, 99.5), np.percentile(py, 99.5))
    n, s, sq = fm.raster(px, py, pc, lo, hi)
    m = n >= 3
    sd = np.zeros_like(s)
    sd[m] = np.sqrt(np.maximum(sq[m] / n[m] - (s[m] / n[m]) ** 2, 0.0))
    obst = m & (sd > 34.0)

    # The walked path, in the same cells.
    tx = np.array([f["tx"] for f in fr]) * scale
    ty = np.array([f["ty"] for f in fr]) * scale
    G = fm.GRID
    ix = ((tx - lo[0]) / (hi[0] - lo[0]) * (G - 1))
    iy = ((ty - lo[1]) / (hi[1] - lo[1]) * (G - 1))
    inside = (ix >= 0) & (ix < G) & (iy >= 0) & (iy < G)
    ix = ix[inside].astype(int); iy = iy[inside].astype(int)
    if len(ix) < 20:
        return None
    judged = m[iy, ix]
    if judged.sum() < 20:
        return None
    wrong = float(obst[iy, ix][judged].mean())
    if not quiet:
        print(f"  pitch {pitch:3d}  scale {scale:6.2f}  "
              f"path cells judged {judged.sum():4d}  "
              f"called BLOCKED {100*wrong:5.1f}%")
    return wrong, int(judged.sum()), int(m.sum())


if __name__ == "__main__":
    drive = sys.argv[1]
    cands = [(int(a.split(",")[0]), float(a.split(",")[1])) for a in sys.argv[2:]]
    print(f"{os.path.basename(drive.rstrip('/'))}: how much of the WALKED PATH "
          f"does each fit call blocked?")
    print("  (the player stood in every one of these cells, so the right answer "
          "is near zero)\n")
    best = None
    for p, sc in cands:
        r = check(drive, p, sc)
        if r and (best is None or r[0] < best[0][0]):
            best = (r, p, sc)
    if best:
        (wrong, npath, ncells), p, sc = best
        print(f"\n  BEST: pitch {p}, scale {sc} -> {100*wrong:.1f}% of the walked "
              f"path wrongly called blocked")
