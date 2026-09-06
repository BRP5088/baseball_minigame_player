"""Stitch drive frames into a top-down floor plan.

THE USER'S IDEA, AND WHY IT WORKS WHERE TRIANGULATION DID NOT. Two reconstructions
failed because the camera never translated: without a baseline, every depth fits,
and 196,198 candidate matches collapsed to 3 surviving points.

Stitching onto the FLOOR has no such requirement. The floor is a known plane, so
the image-to-floor map is a HOMOGRAPHY, and a homography needs only the camera's
pose -- not parallax. A camera spinning on the spot warps onto the floor just as
exactly as one walking across it. That inverts the earlier verdict: the 46% of the
office drive spent turning, useless for triangulation, is fully usable here.

WHAT IS ASSUMED, AND WHAT IS SOLVED. The pinhole model and the 102 deg FOV are
given (camera_fov.json). The camera HEIGHT sets nothing but scale, so it is fixed
at 1 and the trajectory is scaled to match. That leaves two unknowns -- the pitch
and that scale -- and both are FITTED, not guessed, by the one criterion that
does not need ground truth: a patch of floor seen from two poses must land in the
same world place. Wrong pitch shears it, wrong scale slides it, and either way
the overlap disagrees.

WHY DISAGREEMENT IS THE SIGNAL AND NOT THE NOISE. Anything standing ON the floor
-- a stool, a wall, an NPC -- breaks the plane assumption, so it warps to a
different world place from each pose and never agrees. So the same score that
calibrates the geometry also finds the obstacles: floor is what stitches, and
everything that refuses to stitch is what the router has to walk around.

HEADING COMES FROM THE COMPASS, NOT FROM THE IMAGES. Rotational drift is what
ruins long monocular maps; section 7's compass reads an absolute world yaw, so it
cannot accumulate. Frames without a reading are dropped rather than interpolated.
"""
import glob
import json
import math
import os
import sys

import cv2
import numpy as np

DRIVES = [a for a in sys.argv[1:] if not a.startswith("--out=")]
DRIVE = DRIVES[0]
OUT = next((a[6:] for a in sys.argv[1:] if a.startswith("--out=")),
           os.path.join(DRIVE, "floor"))
FOV_DEG = 102.0
GRID = 900              # canvas is GRID x GRID cells
STRIDE = 4              # sample every Nth pixel: the floor is smooth, detail is waste
MAX_RANGE = 3.2         # camera heights. 6.0 was tried: at a near-level camera
                        # the far floor is stretched to a few pixels per metre and
                        # smears the map into fans. Nearer and honest beats wider.
MIN_RANGE = 0.35        # right under the camera the projection blows up


def load(drive):
    """A recorder drive, or one of the archived route walks.

    The route walks predate the recorder and carry no meta.json; their poses were
    solved separately into traj_stick.json. Reading both here means the method can
    be tested on a walk that actually TRAVELS without anyone driving again -- and
    a walk across four rooms is a far better test of a floor plan than a drive
    that never left one spot.
    """
    mp = os.path.join(drive, "meta.json")
    if os.path.exists(mp):
        meta = json.load(open(mp))
        fr = [f for f in meta["frames"] if f.get("bearing") is not None]
        return meta, fr
    key = os.path.basename(drive.rstrip("/"))
    traj = json.load(open("agent_progress/room-map/traj_stick.json"))
    if key not in traj:
        raise SystemExit(f"no meta.json and no solved pose for {key}")
    fs = sorted(glob.glob(os.path.join(drive, "f_*.jpg")))
    poses = traj[key]
    n = min(len(fs), len(poses))
    fr = [{"frame": os.path.basename(fs[i]), "t": i / 6.0,
           "bearing": poses[i][2], "tx": poses[i][0], "ty": poses[i][1],
           "solved": True}
          for i in range(n)]
    return {"room": key, "frames": fr}, fr


def floor_rays(w, h, pitch_deg):
    """Where each sampled pixel lands on the floor, camera at origin, height 1.

    Returns (u, v, X, Y) with the above-horizon and out-of-range pixels already
    dropped -- so a caller cannot accidentally paint sky onto the floor plan.
    """
    f = (w / 2.0) / math.tan(math.radians(FOV_DEG / 2.0))
    cx, cy = w / 2.0, h / 2.0
    th = math.radians(pitch_deg)
    st, ct = math.sin(th), math.cos(th)

    vs, us = np.mgrid[0:h:STRIDE, 0:w:STRIDE]
    a = (us - cx) / f
    b = (vs - cy) / f
    denom = b * ct + st                     # >0 only below the horizon
    ok = denom > 1e-3
    t = np.where(ok, 1.0 / np.maximum(denom, 1e-3), 0.0)
    X = t * a
    Y = t * (ct - b * st)
    r = np.hypot(X, Y)
    ok &= (r > MIN_RANGE) & (r < MAX_RANGE) & (Y > 0)
    return us[ok], vs[ok], X[ok], Y[ok]


def hud_ok(u, v, w, h):
    """The HUD is pixel-identical every frame; painted down it becomes a smear."""
    return ~(((v < 0.12 * h) | (v > 0.88 * h)) | (u < 0.26 * w))


def project(fr_slice, imgs, pitch, scale, rays, w, h):
    """World-space (x, y, colour) for a set of frames. The whole geometry."""
    us, vs, X, Y = rays
    keep = hud_ok(us, vs, w, h)
    us, vs, X, Y = us[keep], vs[keep], X[keep], Y[keep]
    px, py, pc = [], [], []
    for f, img in zip(fr_slice, imgs):
        psi = math.radians(f["bearing"])
        cs, sn = math.cos(psi), math.sin(psi)
        # Compass bearing is clockwise-from-north; screen +Y is forward.
        wx = f["tx"] * scale + (X * cs + Y * sn)
        wy = f["ty"] * scale + (-X * sn + Y * cs)
        px.append(wx); py.append(wy); pc.append(img[vs, us])
    return np.concatenate(px), np.concatenate(py), np.concatenate(pc)


def raster(px, py, pc, lo, hi):
    """Mean colour and sample count per cell. Count is the confidence."""
    ix = np.clip(((px - lo[0]) / (hi[0] - lo[0]) * (GRID - 1)), 0, GRID - 1).astype(int)
    iy = np.clip(((py - lo[1]) / (hi[1] - lo[1]) * (GRID - 1)), 0, GRID - 1).astype(int)
    k = iy * GRID + ix
    n = np.bincount(k, minlength=GRID * GRID).astype(float)
    s = np.bincount(k, weights=pc.astype(float), minlength=GRID * GRID)
    sq = np.bincount(k, weights=pc.astype(float) ** 2, minlength=GRID * GRID)
    return n.reshape(GRID, GRID), s.reshape(GRID, GRID), sq.reshape(GRID, GRID)


def dead_reckon(fr):
    """Camera position per frame, from the logged stick and the compass heading.

    Scale is arbitrary and is fitted later; only the SHAPE of the path matters
    here. Section 6 measured walking as linear to ~0.75, which is what makes
    "distance = speed x duration" admissible at all -- above that the variance
    explodes and this would be fiction.
    """
    if fr and fr[0].get("solved"):
        return fr          # poses already solved; integrating again would erase them
    x = y = 0.0
    for i, f in enumerate(fr):
        dt = 0.0 if i == 0 else max(0.0, min(1.0, f["t"] - fr[i - 1]["t"]))
        s = f.get("stick") or {}
        ly, lx = -(s.get("ly", 0.0) or 0.0), (s.get("lx", 0.0) or 0.0)
        psi = math.radians(f["bearing"])
        cs, sn = math.cos(psi), math.sin(psi)
        fwd, side = ly * dt, lx * dt
        x += side * cs + fwd * sn
        y += -side * sn + fwd * cs
        f["tx"], f["ty"] = x, y
    return fr


def agreement(fr, imgs, pitch, scale, rays, w, h):
    """Does a floor built from EARLY frames predict what the LATE frames see?

    THE OBVIOUS SCORE IS VACUOUS AND WAS TRIED FIRST. Scoring "cells painted by
    3+ frames hold one colour" rails the fit against the edge of every search
    range, because at 5Hz consecutive frames are nearly the SAME pose: they agree
    with each other whatever the geometry, so the score measures the frame rate.
    Section 10.12 -- a statistic that holds by construction looks devastating and
    measures nothing.

    So the drive is CUT IN HALF by time and the halves are held out from each
    other. Agreement now requires the floor seen minutes apart, from genuinely
    different poses, to land in the same world place. Nothing about the frame
    rate can satisfy that; only the pose and the plane can.
    """
    if len(fr) < 8:
        return 0.0
    mid = len(fr) // 2
    pa = project(fr[:mid], imgs[:mid], pitch, scale, rays, w, h)
    pb = project(fr[mid:], imgs[mid:], pitch, scale, rays, w, h)
    if len(pa[0]) < 2000 or len(pb[0]) < 2000:
        return 0.0
    allx = np.concatenate([pa[0], pb[0]]); ally = np.concatenate([pa[1], pb[1]])
    lo = (np.percentile(allx, 1), np.percentile(ally, 1))
    hi = (np.percentile(allx, 99), np.percentile(ally, 99))
    if hi[0] - lo[0] < 1e-6 or hi[1] - lo[1] < 1e-6:
        return 0.0
    na, sa, _ = raster(*pa, lo, hi)
    nb, sb, _ = raster(*pb, lo, hi)
    both = (na >= 2) & (nb >= 2)
    if both.sum() < 150:
        return 0.0          # no overlap between the halves: nothing was tested
    d = np.abs(sa[both] / na[both] - sb[both] / nb[both])
    # A geometry that overlaps almost nothing scores 100% on a handful of cells,
    # the same shape as an arrival rate on a denominator of two. So the tested
    # area is a GATE, not a weight: a fit either answers the question over enough
    # floor to mean something, or it does not compete. Multiplying by area was
    # tried first and is worse -- it lets a sloppy geometry buy its way back with
    # coverage, and the map visibly smeared.
    if both.sum() < 4000:
        return 0.0
    return float((d < 26.0).mean())


def main():
    os.makedirs(OUT, exist_ok=True)
    fr = []
    for d in DRIVES:
        meta, sub = load(d)
        sub = dead_reckon(sub)
        for f in sub:
            f["dir"] = d
        print(f"{os.path.basename(d.rstrip('/')):40s} {len(sub):5d} frames with a heading")
        fr += sub
    if len(DRIVES) > 1:
        print(f"  merged: {len(fr)} frames. They share an origin because every reset "
              f"spawns\n  at the same place and bearing (section 8(d), 86.9/87/87).")

    probe = cv2.imread(os.path.join(fr[0]["dir"], fr[0]["frame"]), cv2.IMREAD_GRAYSCALE)
    h, w = probe.shape[:2]

    # Calibrate on a subset: every frame is not needed to fit two numbers.
    sub = fr[::max(1, len(fr) // 160)]
    imgs = [cv2.imread(os.path.join(f["dir"], f["frame"]), cv2.IMREAD_GRAYSCALE)
            for f in sub]
    print(f"fitting pitch and scale on {len(sub)} frames "
          f"(the floor must agree with itself)")

    # MEASURED, NOT SEARCHED. Three global objectives were tried and all three
    # railed against a search boundary, which read as "the score is being gamed"
    # and was really "the answer is outside the range you gave it": the true
    # scale is 0.164 and the search floor was 0.5. floor_calib measures both
    # numbers locally instead, from how far the floor texture slides between two
    # frames of straight walking -- a ratio of two lengths on the same pair, so
    # the extent of the map cannot enter it.
    import floor_calib
    cal = floor_calib.calibrate(DRIVES[0], fr,
                                lambda f: cv2.imread(os.path.join(f["dir"], f["frame"]),
                                                     cv2.IMREAD_GRAYSCALE))
    if cal is None:
        print("\n  Cannot calibrate, so not drawing a map. A floor plan with an")
        print("  unmeasured pitch is a picture, not a measurement.")
        return 1
    pitch, scale, spread = cal
    import floor_check
    chk = floor_check.check(DRIVES[0], pitch, scale, quiet=True)
    wrong = chk[0] if chk else 1.0
    sc = agreement(sub, imgs, pitch, scale, floor_rays(w, h, pitch), w, h)
    print(f"\n  validating that calibration against the two independent checks:")
    print(f"    walked path wrongly called blocked : {100*wrong:5.1f}%   "
          f"(the player stood there, so this should be near zero)")
    print(f"    first half confirmed by second     : {100*sc:5.0f}%")
    if wrong > 0.15:
        print("\n  REFUSING TO WRITE A MAP. More than 15% of the floor the player")
        print("  physically walked on comes out blocked, so the geometry is wrong")
        print("  and every obstacle drawn would be an artefact. A wrong map is")
        print("  worse than none: the router would plan around nothing.")
        return 1

    rays = floor_rays(w, h, pitch)
    px, py, pc = [], [], []
    for i in range(0, len(fr)):
        img = cv2.imread(os.path.join(fr[i]["dir"], fr[i]["frame"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        a, b, c = project([fr[i]], [img], pitch, scale, rays, w, h)
        px.append(a); py.append(b); pc.append(c)
    px, py, pc = np.concatenate(px), np.concatenate(py), np.concatenate(pc)
    lo = (np.percentile(px, 0.5), np.percentile(py, 0.5))
    hi = (np.percentile(px, 99.5), np.percentile(py, 99.5))
    n, s, sq = raster(px, py, pc, lo, hi)

    seen = n > 0
    floor = np.zeros((GRID, GRID), np.uint8)
    floor[seen] = np.clip(s[seen] / n[seen], 0, 255).astype(np.uint8)

    # Disagreement: a cell several poses paint DIFFERENTLY is not flat floor.
    m = n >= 3
    sd = np.zeros((GRID, GRID))
    sd[m] = np.sqrt(np.maximum(sq[m] / n[m] - (s[m] / n[m]) ** 2, 0.0))

    vis = cv2.cvtColor(floor, cv2.COLOR_GRAY2BGR)
    vis[~seen] = (28, 28, 28)
    obst = m & (sd > 34.0)
    vis[obst] = (60, 60, 235)
    cv2.imwrite(os.path.join(OUT, "floor.png"), vis)
    cv2.imwrite(os.path.join(OUT, "coverage.png"),
                np.clip(n / max(np.percentile(n[seen], 98), 1) * 255, 0, 255).astype(np.uint8))
    json.dump({"pitch_deg": pitch, "scale": scale, "agreement": sc,
               "grid": GRID, "extent": [lo[0], lo[1], hi[0], hi[1]],
               "cells_seen": int(seen.sum()), "cells_multi": int(m.sum()),
               "cells_obstacle": int(obst.sum())},
              open(os.path.join(OUT, "floor.json"), "w"), indent=1)

    print(f"\n  floor cells painted   {seen.sum():6d} of {GRID*GRID}")
    print(f"  seen from 3+ poses    {m.sum():6d}   <- the only cells that can be judged")
    print(f"  disagreeing (not flat){obst.sum():6d}   <- obstacles, in red")
    print(f"  -> {os.path.join(OUT,'floor.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
