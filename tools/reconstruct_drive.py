"""Reconstruct one driven room: trajectory, then a 3D cloud.

DIFFERENT INPUT FROM THE ARCHIVED WALKS, same idea. A drive carries meta.json
with a per-frame bearing AND a per-frame stick reading, so both halves of a pose
come from instruments rather than from solving for them:

    heading   the game's compass, on ~95% of frames. Rotational drift, which is
              what ruins long monocular trajectories, cannot accumulate.
    distance  the real left stick, logged at the capture rate. The vision-only
              alternative was measured against the four archived recordings that
              carry both, and correlates only 0.55-0.58 on walks and 0.14 on
              turns -- good enough to sanity-check, not to build a map on.

THE STICK IS SAMPLED AT THE FRAME RATE (5 Hz), not the 50 Hz of the archived
input.json. So a push shorter than 0.2s is invisible here. That is a real limit
of driving-while-recording and it is stated rather than hidden: the integral is
a lower bound on distance travelled.

FEATURELESS FRAMES STILL COUNT FOR POSITION. A frame pressed against a wall has
no usable features and cannot contribute a 3D point, but the character was still
somewhere, and the stick still says how far it moved. Dropping them would
shorten the trajectory.
"""
import glob
import json
import math
import os
import sys

import cv2
import numpy as np

DRIVE = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DRIVE, "reconstruction.json")
FOV = 102.0
DEAD = 0.08
MIN_BASELINE = 0.02        # in stick-units; a drive covers far less ground
MIN_PARALLAX_DEG = 2.0
MAX_PAIR_GAP = 40

orb = cv2.ORB_create(nfeatures=3000)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def hud(w, h):
    m = np.full((h, w), 255, np.uint8)
    m[:int(h*.10), :] = 0; m[int(h*.90):, :] = 0; m[:, :int(w*.28)] = 0
    return m


def pose_matrix(x, y, heading_deg):
    a = math.radians(heading_deg)
    fwd = np.array([math.sin(a), math.cos(a), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up); right /= (np.linalg.norm(right) + 1e-9)
    up2 = np.cross(right, fwd)
    R = np.vstack([right, -up2, fwd])
    return R, (-R @ np.array([x, y, 0.0])).reshape(3, 1)


def main():
    meta = json.load(open(os.path.join(DRIVE, "meta.json")))
    frames = meta["frames"] if isinstance(meta, dict) else meta
    room = meta.get("room", "?") if isinstance(meta, dict) else "?"
    print(f"room {room!r}: {len(frames)} frames, complete="
          f"{meta.get('complete') if isinstance(meta, dict) else '?'}", flush=True)

    # --- trajectory -------------------------------------------------------
    head = next((f["bearing"] for f in frames if f.get("bearing") is not None), None)
    if head is None:
        raise SystemExit("no compass fix anywhere in this drive — no world frame")
    x = y = 0.0
    path, no_head = [], 0
    for i, f in enumerate(frames):
        if f.get("bearing") is not None:
            head = f["bearing"]
        else:
            no_head += 1
        st = f.get("stick") or {}
        ly = st.get("ly", 0.0)
        dt = (f["t"] - frames[i-1]["t"]) if i else 0.0
        # Forward is NEGATIVE ly on this controller, matching the injector.
        step = (-ly) * dt if (-ly) > DEAD else 0.0
        r = math.radians(head)
        x += step * math.sin(r); y += step * math.cos(r)
        path.append((round(x, 5), round(y, 5), round(head, 2)))
    xs = [p[0] for p in path]; ys = [p[1] for p in path]
    total = sum(math.dist(path[i][:2], path[i+1][:2]) for i in range(len(path)-1))
    print(f"  trajectory: {total:.3f} units walked, extent "
          f"{max(xs)-min(xs):.3f} x {max(ys)-min(ys):.3f}, "
          f"{no_head} frames carried a stale heading", flush=True)

    # --- cloud ------------------------------------------------------------
    fs = [os.path.join(DRIVE, f["frame"]) for f in frames]
    g0 = cv2.imread(fs[0], cv2.IMREAD_GRAYSCALE)
    h, w = g0.shape[:2]
    fl = (w/2)/math.tan(math.radians(FOV/2))
    K = np.array([[fl,0,w/2],[0,fl,h/2],[0,0,1]], float)
    m_ = hud(w, h)
    cloud, hist, pairs = [], {}, 0
    for i, fp in enumerate(fs):
        g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        k, d = orb.detectAndCompute(g, m_)
        hist[i] = (k, d)
        j = None
        for c in range(i-1, max(-1, i-MAX_PAIR_GAP)-1, -1):
            if math.dist(path[c][:2], path[i][:2]) >= MIN_BASELINE:
                j = c; break
        if j is not None and d is not None and hist.get(j, (None,None))[1] is not None:
            k0, d0 = hist[j]
            if len(d0) > 20 and len(d) > 20:
                mm = bf.match(d0, d)
                if len(mm) >= 40:
                    pairs += 1
                    x0,y0,h0 = path[j]; x1,y1,h1 = path[i]
                    base = math.dist((x0,y0),(x1,y1))
                    R0,t0 = pose_matrix(x0,y0,h0); R1,t1 = pose_matrix(x1,y1,h1)
                    P0 = K @ np.hstack([R0,t0]); P1 = K @ np.hstack([R1,t1])
                    p1 = np.float32([k0[z.queryIdx].pt for z in mm]).T
                    p2 = np.float32([k[z.trainIdx].pt for z in mm]).T
                    X = cv2.triangulatePoints(P0,P1,p1,p2)
                    X = (X[:3]/np.where(abs(X[3])<1e-9,1e-9,X[3])).T
                    for pt in X:
                        if not np.all(np.isfinite(pt)):
                            continue
                        d1 = math.dist(pt[:2], (x1,y1))
                        if d1 < 1e-6:
                            continue
                        par = math.degrees(math.atan2(base, d1))
                        if par >= MIN_PARALLAX_DEG and d1 < 8.0:
                            cloud.append([round(float(v),4) for v in pt])
        if i % 200 == 0:
            print(f"    {i}/{len(fs)} frames, {len(cloud)} points", flush=True)
    print(f"  cloud: {len(cloud)} points from {pairs} usable pairs")
    if cloud:
        a = np.array(cloud)
        for n, ix in (("X",0),("Y",1),("Z",2)):
            print(f"    {n}: p05 {np.percentile(a[:,ix],5):7.3f}  "
                  f"median {np.median(a[:,ix]):7.3f}  p95 {np.percentile(a[:,ix],95):7.3f}")
    json.dump({"room": room, "path": path, "cloud": cloud}, open(OUT, "w"))
    print(f"  -> {OUT}")


main()
