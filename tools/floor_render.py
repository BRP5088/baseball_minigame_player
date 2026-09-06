"""Render the floor plan, with the obstacle layer calibrated on known-free floor.

WHY THIS IS NOT A BINARY OBSTACLE MAP. The per-cell disagreement -- how differently
several poses painted the same patch of floor -- is UNIMODAL over 344,617 cells:
median 8.7, no gap anywhere, a smooth tail out to 115. Section 10.4 of CLAUDE.md
is explicit that a threshold must sit BETWEEN two measured populations, and there
are not two here. The earlier version drew everything over 34 in red and called
it obstacles; that number was picked by eye and 31% of the office map came out
red, which is not a room, it is a smear.

WHAT THE QUANTITY CAN DO. It still separates in the mean: cells the player
physically STOOD IN have a median disagreement of 2.5 against 8.7 for the map at
large. So it is a usable confidence, just not a classifier. The threshold is
therefore calibrated on the ONE population that is actually labelled -- the
walked path, which is free floor by definition -- at a stated quantile, so the
false-positive rate on free floor is chosen rather than discovered later.

Everything above it is drawn as "not confirmed floor", NOT as "obstacle". The
difference matters to whoever routes on this: unconfirmed means unknown, and the
right response to unknown is to look, not to plan around it.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_mosaic as fm

FREE_QUANTILE = 0.90      # keep 90% of known-free floor classified free


def build(drive, pitch, scale):
    meta, fr = fm.load(drive)
    fr = fm.dead_reckon(fr)
    for f in fr:
        f["dir"] = drive
    probe = cv2.imread(os.path.join(drive, fr[0]["frame"]), cv2.IMREAD_GRAYSCALE)
    h, w = probe.shape[:2]
    rays = fm.floor_rays(w, h, pitch)
    px, py, pc = [], [], []
    for f in fr:
        im = cv2.imread(os.path.join(drive, f["frame"]), cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        a, b, c = fm.project([f], [im], pitch, scale, rays, w, h)
        px.append(a); py.append(b); pc.append(c)
    px = np.concatenate(px); py = np.concatenate(py); pc = np.concatenate(pc)
    lo = (np.percentile(px, 0.5), np.percentile(py, 0.5))
    hi = (np.percentile(px, 99.5), np.percentile(py, 99.5))
    n, s, sq = fm.raster(px, py, pc, lo, hi)
    G = fm.GRID
    m = n >= 3
    sd = np.zeros((G, G))
    sd[m] = np.sqrt(np.maximum(sq[m] / n[m] - (s[m] / n[m]) ** 2, 0.0))

    tx = np.array([f["tx"] for f in fr]) * scale
    ty = np.array([f["ty"] for f in fr]) * scale
    ix = (tx - lo[0]) / (hi[0] - lo[0]) * (G - 1)
    iy = (ty - lo[1]) / (hi[1] - lo[1]) * (G - 1)
    ok = (ix >= 0) & (ix < G) & (iy >= 0) & (iy < G)
    ix = ix[ok].astype(int); iy = iy[ok].astype(int)
    free = sd[iy, ix][m[iy, ix]]
    if len(free) < 100:
        raise SystemExit("too few known-free cells to calibrate the threshold")
    thr = float(np.quantile(free, FREE_QUANTILE))
    return dict(n=n, s=s, sd=sd, m=m, lo=lo, hi=hi, thr=thr, free=free,
                path=(ix, iy), fr=fr, pitch=pitch, scale=scale)


def render(b, out):
    os.makedirs(out, exist_ok=True)
    G = fm.GRID
    n, s, sd, m, thr = b["n"], b["s"], b["sd"], b["m"], b["thr"]
    seen = n > 0
    grey = np.zeros((G, G), np.uint8)
    grey[seen] = np.clip(s[seen] / n[seen], 0, 255).astype(np.uint8)
    vis = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
    vis[~seen] = (24, 24, 24)

    # Confirmed floor: green. Unconfirmed: amber, scaled by how unlike floor it
    # is. Not red, and not called an obstacle -- see the module docstring.
    conf = m & (sd <= thr)
    vis[conf] = (0.55 * vis[conf] + np.array([40, 140, 40])).clip(0, 255).astype(np.uint8)
    unc = m & (sd > thr)
    heat = np.clip((sd[unc] - thr) / max(thr * 3.0, 1e-6), 0, 1)[:, None]
    vis[unc] = (0.5 * vis[unc] + heat * np.array([20, 150, 235])).clip(0, 255).astype(np.uint8)

    ix, iy = b["path"]
    for a, c in zip(ix, iy):
        cv2.circle(vis, (int(a), int(c)), 1, (255, 90, 90), -1)

    cv2.imwrite(os.path.join(out, "floor.png"), vis)
    big = cv2.resize(vis, (820, 820), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(out, "floor_view.png"), big)
    stats = dict(pitch=b["pitch"], scale=b["scale"], threshold=thr,
                 free_quantile=FREE_QUANTILE,
                 cells_seen=int(seen.sum()), cells_judged=int(m.sum()),
                 cells_confirmed_floor=int(conf.sum()),
                 cells_unconfirmed=int(unc.sum()),
                 known_free_median_sd=float(np.median(b["free"])),
                 all_judged_median_sd=float(np.median(sd[m])))
    json.dump(stats, open(os.path.join(out, "floor.json"), "w"), indent=1)
    return stats


if __name__ == "__main__":
    drive = sys.argv[1]
    pitch = int(sys.argv[2]); scale = float(sys.argv[3])
    out = sys.argv[4]
    b = build(drive, pitch, scale)
    st = render(b, out)
    print(f"{os.path.basename(drive.rstrip('/'))}  pitch {pitch}  scale {scale}")
    print(f"  threshold calibrated so {100*FREE_QUANTILE:.0f}% of KNOWN-FREE floor "
          f"stays free: sd <= {st['threshold']:.1f}")
    print(f"  known-free median disagreement {st['known_free_median_sd']:.1f}  "
          f"vs {st['all_judged_median_sd']:.1f} over the whole map")
    print(f"  confirmed floor   {st['cells_confirmed_floor']:7d} cells (green)")
    print(f"  not confirmed     {st['cells_unconfirmed']:7d} cells (amber) "
          f"-- unknown, NOT 'obstacle'")
    print(f"  -> {out}/floor_view.png")
