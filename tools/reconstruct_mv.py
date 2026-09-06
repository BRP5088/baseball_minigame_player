"""Multi-view reconstruction: tracks, not pairs, with the checks that were missing.

WHY THE PAIRWISE VERSION PRODUCED NOTHING. Three standard filters were absent,
and their absence produces exactly the starburst it produced:

  CHEIRALITY. A triangulated point must be IN FRONT of both cameras. Nothing
  checked it, and an audit of the pairwise cloud found 19.6% of kept points
  lying between or behind the two camera centres. A point behind the camera is
  not a mistake to be averaged out, it is a sign the depth was never determined.

  REPROJECTION ERROR. The strongest filter there is, and it was not applied at
  all. If a triangulated point does not project back onto the pixels it was
  observed at, the triangulation failed. Everything else is a proxy for this.

  TWO VIEWS BARELY CONSTRAIN A POINT. With a short baseline the depth slides
  along the ray, which is why the median kept depth equalled the baseline --
  the points were sitting on the camera path. A track seen from THREE or more
  positions is over-determined, and disagreement becomes detectable instead of
  being absorbed.

SO THIS TRACKS FEATURES ACROSS FRAMES. Consecutive frames are matched, matches
are chained into tracks, and only tracks seen from enough distinct positions are
triangulated -- by DLT over all their views at once, then verified.

WHAT IT CANNOT FIX. The camera POSES come from the compass and the stick and
carry their own error. Reprojection will reject points whose views disagree, but
a systematically wrong trajectory bends the whole cloud together, and no filter
here can see that. If the output is sparse but clean, the poses are fine and the
old cloud was noise. If it is empty, the poses are the problem.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

DRIVE = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DRIVE, "cloud_mv.json")
FOV = 102.0
DEAD = 0.08

MIN_VIEWS = 3            # a track must be seen from this many camera positions
MIN_SPREAD = 0.05        # ...and those positions must span this much ground
MAX_REPROJ_PX = 3.0      # a point must land back on the pixels it was seen at
MIN_DEPTH = 0.15         # nearer than this and it is on the camera, not a wall
MAX_DEPTH = 8.0

orb = cv2.ORB_create(nfeatures=2000)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def hud(w, h):
    m = np.full((h, w), 255, np.uint8)
    m[:int(h*.10), :] = 0; m[int(h*.90):, :] = 0; m[:, :int(w*.28)] = 0
    return m


def pose(x, y, heading_deg):
    a = math.radians(heading_deg)
    fwd = np.array([math.sin(a), math.cos(a), 0.0])
    right = np.cross(fwd, [0.0, 0.0, 1.0]); right /= np.linalg.norm(right)+1e-9
    up2 = np.cross(right, fwd)
    R = np.vstack([right, -up2, fwd])
    return R, (-R @ np.array([x, y, 0.0])).reshape(3, 1)


def main():
    meta = json.load(open(os.path.join(DRIVE, "meta.json")))
    frames = meta["frames"] if isinstance(meta, dict) else meta
    room = meta.get("room", "?") if isinstance(meta, dict) else "?"

    head = next((f["bearing"] for f in frames if f.get("bearing") is not None), None)
    x = y = 0.0
    path = []
    for i, f in enumerate(frames):
        if f.get("bearing") is not None:
            head = f["bearing"]
        st = f.get("stick") or {}
        ly = -(st.get("ly", 0.0))
        dt = (f["t"] - frames[i-1]["t"]) if i else 0.0
        step = ly * dt if ly > DEAD else 0.0
        r = math.radians(head)
        x += step*math.sin(r); y += step*math.cos(r)
        path.append((x, y, head))
    print(f"room {room!r}: {len(frames)} frames, "
          f"{sum(math.dist(path[i][:2],path[i+1][:2]) for i in range(len(path)-1)):.2f} units walked",
          flush=True)

    fs = [os.path.join(DRIVE, f["frame"]) for f in frames]
    g0 = cv2.imread(fs[0], cv2.IMREAD_GRAYSCALE); h, w = g0.shape[:2]
    fl = (w/2)/math.tan(math.radians(FOV/2))
    K = np.array([[fl,0,w/2],[0,fl,h/2],[0,0,1]], float)
    m_ = hud(w, h)
    P = []
    for (px, py, ph) in path:
        R, t = pose(px, py, ph)
        P.append((R, t, K @ np.hstack([R, t])))

    # ---- chain matches into tracks --------------------------------------
    tracks = {}          # track id -> {frame index: (u, v)}
    live = {}            # keypoint index in the previous frame -> track id
    nxt = 0
    prev = None
    for i, fp in enumerate(fs):
        g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if g is None:
            prev, live = None, {}
            continue
        k, d = orb.detectAndCompute(g, m_)
        cur = {}
        if prev is not None and d is not None and prev[1] is not None \
                and len(d) > 20 and len(prev[1]) > 20:
            for m in bf.match(prev[1], d):
                tid = live.get(m.queryIdx)
                if tid is None:
                    tid = nxt; nxt += 1
                    tracks[tid] = {i-1: prev[0][m.queryIdx].pt}
                tracks.setdefault(tid, {})[i] = k[m.trainIdx].pt
                cur[m.trainIdx] = tid
        prev, live = (k, d), cur
        if i % 250 == 0:
            print(f"    {i}/{len(fs)} frames, {len(tracks)} tracks", flush=True)

    print(f"  {len(tracks)} tracks built", flush=True)

    # ---- triangulate each long-enough track over ALL its views ----------
    cloud = []
    stats = dict(short=0, tight=0, dlt=0, cheir=0, depth=0, reproj=0, kept=0)
    for tid, obs in tracks.items():
        if len(obs) < MIN_VIEWS:
            stats["short"] += 1; continue
        idx = sorted(obs)
        pts = [path[j][:2] for j in idx]
        spread = max(math.dist(a, b) for a in pts for b in pts)
        if spread < MIN_SPREAD:
            stats["tight"] += 1; continue
        A = []
        for j in idx:
            u, v = obs[j]; Pj = P[j][2]
            A.append(u*Pj[2] - Pj[0]); A.append(v*Pj[2] - Pj[1])
        _, _, Vt = np.linalg.svd(np.array(A))
        Xh = Vt[-1]
        if abs(Xh[3]) < 1e-9:
            stats["dlt"] += 1; continue
        X = Xh[:3]/Xh[3]
        # CHEIRALITY and depth, in every view
        ok, worst = True, 0.0
        for j in idx:
            R, t, Pj = P[j]
            z = float((R @ X).reshape(3) [2] + t[2, 0])
            if z <= 0:
                ok = False; stats["cheir"] += 1; break
            if not (MIN_DEPTH <= z <= MAX_DEPTH):
                ok = False; stats["depth"] += 1; break
            pr = Pj @ np.append(X, 1.0)
            uv = pr[:2]/pr[2]
            worst = max(worst, float(np.linalg.norm(uv - np.array(obs[j]))))
        if not ok:
            continue
        if worst > MAX_REPROJ_PX:
            stats["reproj"] += 1; continue
        cloud.append([round(float(v), 4) for v in X])
        stats["kept"] += 1

    print(f"\n  tracks rejected: too few views {stats['short']}, "
          f"positions too close {stats['tight']}, degenerate {stats['dlt']},\n"
          f"                   BEHIND a camera {stats['cheir']}, "
          f"bad depth {stats['depth']}, reprojection {stats['reproj']}")
    print(f"  KEPT {stats['kept']} points")
    if cloud:
        a = np.array(cloud)
        for n, ix in (("X",0),("Y",1),("Z",2)):
            print(f"    {n}: p05 {np.percentile(a[:,ix],5):7.3f}  "
                  f"median {np.median(a[:,ix]):7.3f}  p95 {np.percentile(a[:,ix],95):7.3f}")
    json.dump({"room": room, "path": [[round(v,5) for v in q] for q in path],
               "cloud": cloud, "stats": stats}, open(OUT, "w"))
    print(f"  -> {OUT}")


main()
