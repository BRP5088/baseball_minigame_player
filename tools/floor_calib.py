"""Measure the camera pitch and the trajectory scale. Locally, from motion.

WHY NOT FIT THEM WITH A GLOBAL SCORE. Three were tried and all three were gamed,
each in a different direction:

  maximise self-agreement  -> pitch 18, which calls 59.7% of the floor the player
                              STOOD ON an obstacle. A consistent error agrees
                              with itself perfectly.
  minimise path-error      -> scale 0.5, collapsing the whole walk into one
                              well-averaged blob where nothing can be blocked.
                              Scored 0.0% wrong and 0% agreement.
  both, as gate and score  -> scale 0.5 again. Small scale is systematically
                              favoured because it shrinks the question.

Every one of them is a global statistic over a map whose EXTENT the parameter
being fitted controls, so the parameter can always buy a better score by making
the map smaller. That is not a tuning problem, it is the wrong measurement.

WHAT THIS MEASURES INSTEAD. Warp two consecutive frames onto the floor plane and
the floor texture must move RIGIDLY between them -- the same shift everywhere,
equal to how far the camera walked. That has both unknowns in it and neither can
hide:

  WRONG PITCH shears the warp, so the texture does not move rigidly and the
  correlation peak collapses. Pitch is the value that makes the floor move like
  a floor.
  SCALE is then read straight off: measured shift in camera heights, divided by
  the trajectory's own predicted step. It is a ratio of two lengths on the same
  pair of frames, so shrinking the map does not change it.

It is local, so map extent cannot enter. It uses only frames where the character
was WALKING and NOT TURNING, because a turn moves the texture for reasons that
have nothing to do with distance.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

FOV_DEG = 102.0
PW, PH = 220, 220           # top-down patch, in cells
X_HALF, Y_NEAR, Y_FAR = 2.0, 0.45, 3.0      # camera heights


def topdown_maps(w, h, pitch_deg):
    """Inverse map: for each top-down floor cell, which source pixel."""
    f = (w / 2.0) / math.tan(math.radians(FOV_DEG / 2.0))
    cx, cy = w / 2.0, h / 2.0
    th = math.radians(pitch_deg)
    st, ct = math.sin(th), math.cos(th)
    X = np.linspace(-X_HALF, X_HALF, PW)[None, :].repeat(PH, 0)
    Y = np.linspace(Y_FAR, Y_NEAR, PH)[:, None].repeat(PW, 1)
    dz = Y * ct + st
    bad = dz <= 1e-3
    dz = np.maximum(dz, 1e-3)
    u = cx + f * (X / dz)
    v = cy + f * ((-Y * st + ct) / dz)
    u[bad] = -1; v[bad] = -1
    return u.astype(np.float32), v.astype(np.float32)


_HUD = {}


def hud_mask(drive, frames, load_img):
    """The HUD, MEASURED as the pixels that never change. Not guessed at.

    Guessing cost this calibration a whole wrong answer. A fixed "top 12%,
    bottom 12%, left 26%" mask threw away the clean bottom-centre floor -- 0%
    static -- and kept enough quest list that phase correlation locked onto it:
    every measured shift came back at half a cell, i.e. zero, because the HUD is
    pixel-identical between frames and outweighs the floor. Measured, the HUD is
    2.5% of the frame, not the ~40% the bands removed.
    """
    key = drive
    if key in _HUD:
        return _HUD[key]
    idx = np.linspace(0, len(frames) - 1, 40).astype(int)
    ims = [load_img(frames[i]).astype(np.float32) for i in idx]
    st = np.std(np.stack(ims), 0)
    m = (st < 3.0).astype(np.uint8)
    m = cv2.dilate(m, np.ones((9, 9), np.uint8))
    _HUD[key] = m
    return m


def warp(img, mu, mv, hud=None):
    """Top-down floor patch, with the HUD and the out-of-frame area marked NaN.

    NaN rather than zero: a zeroed region is a CONSTANT, and a constant region
    correlates most strongly at zero shift, which is the exact failure this is
    fixing. NaNs are filled with the patch's own mean so they carry no gradient
    and cannot vote for any particular displacement.
    """
    src = img.astype(np.float32)
    if hud is not None:
        src = src.copy()
        src[hud > 0] = np.nan
    out = cv2.remap(src, mu, mv, cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=float("nan"))
    bad = ~np.isfinite(out)
    if bad.all():
        return None
    out[bad] = np.nanmean(out)
    return out


def usable_pairs(fr, max_pairs=60):
    """Frames where the character walked and did NOT turn."""
    out = []
    for i in range(1, len(fr)):
        a, b = fr[i - 1], fr[i]
        dt = b["t"] - a["t"]
        if not (0.05 < dt < 0.6):
            continue
        if abs((b["bearing"] - a["bearing"] + 180) % 360 - 180) > 1.5:
            continue          # turning: texture moves for the wrong reason
        d = math.hypot(b["tx"] - a["tx"], b["ty"] - a["ty"])
        if d <= 1e-9:
            continue
        out.append((i - 1, i, d))
    out.sort(key=lambda p: -p[2])
    return out[:max_pairs]


def calibrate(drive, fr, load_img):
    pairs = usable_pairs(fr)
    if len(pairs) < 12:
        print(f"  only {len(pairs)} walking-and-not-turning frame pairs; "
              f"cannot calibrate from this recording")
        return None
    probe = load_img(fr[0])
    h, w = probe.shape[:2]
    hud = hud_mask(drive, fr, load_img)
    print(f"  HUD measured at {100*(hud>0).mean():.1f}% of the frame "
          f"(the pixels that never change)")
    cell_x = (2 * X_HALF) / PW
    cell_y = (Y_FAR - Y_NEAR) / PH
    print(f"  {len(pairs)} frame pairs where the character walked straight")

    results = []
    for pitch in range(0, 40, 2):
        mu, mv = topdown_maps(w, h, pitch)
        ratios, peaks = [], []
        for i, j, d in pairs:
            A = warp(load_img(fr[i]), mu, mv, hud)
            B = warp(load_img(fr[j]), mu, mv, hud)
            if A is None or B is None or A.std() < 4 or B.std() < 4:
                continue
            (sx, sy), pk = cv2.phaseCorrelate(A, B)
            shift = math.hypot(sx * cell_x, sy * cell_y)
            if shift < 1e-4:
                continue
            ratios.append(shift / d)
            peaks.append(pk)
        if len(ratios) < 8:
            continue
        r = np.array(ratios)
        med = float(np.median(r))
        # Spread of the ratio is the discriminator: at the right pitch every
        # pair agrees on one scale, because there IS one. At a wrong pitch the
        # implied scale depends on how far the texture happened to be.
        spread = float(np.median(np.abs(r - med)) / max(med, 1e-9))
        results.append((spread, pitch, med, float(np.mean(peaks)), len(r)))

    if not results:
        print("  no pitch produced a usable correlation")
        return None
    results.sort()
    print(f"\n  {'pitch':>6} {'scale':>9} {'spread':>8} {'peak':>7} {'pairs':>6}")
    for spread, pitch, med, pk, n in results[:8]:
        print(f"  {pitch:6d} {med:9.3f} {spread:8.3f} {pk:7.3f} {n:6d}")
    spread, pitch, med, pk, n = results[0]
    print(f"\n  -> pitch {pitch} deg, scale {med:.3f}  "
          f"({100*spread:.0f}% spread across {n} independent pairs)")
    return pitch, med, spread


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import floor_mosaic as fm
    d = sys.argv[1]
    meta, fr = fm.load(d)
    fr = fm.dead_reckon(fr)
    print(f"{os.path.basename(d.rstrip('/'))}: calibrating from floor motion")
    calibrate(d, fr, lambda f: cv2.imread(os.path.join(d, f["frame"]),
                                          cv2.IMREAD_GRAYSCALE))
