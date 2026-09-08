"""Does the LEFT stick still move the character at LOW magnitude?

The user's question: instead of a short push at high magnitude, which does
nothing under ~0.10 s, push LONGER at LOWER magnitude for the same impulse.
That only works if the stick responds below the lowest magnitude ever measured
here (0.25, giving 35 px over 0.4 s -- CLAUDE.md 6). Below that is unknown; the
camera stick has a dead zone at 0.35, the walking stick may have one too.

The instrument is the paired MATCH-COUNT RATIO that the user's own crawl-mode
labels validated tonight: a push that moved the character reads 0.05-0.18, a
push that did not reads 0.74-0.90. So "did it move" is decided by the one
signal on this rig that has been shown to separate those two populations.

Method: reset to the spawn, face the corridor, then for each magnitude push
for a FIXED 0.6 s and measure. Magnitudes are interleaved low/high so drift
along the corridor is not confounded with the sweep.

    .venv/bin/python -B tools/stick_floor.py
"""
import os, sys, time, subprocess, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAGS = [0.05, 0.25, 0.10, 0.20, 0.15, 0.30, 0.08, 0.12]   # interleaved
HOLD = 0.6

if subprocess.run(["pgrep","-f","overnight/chain_trials.py"],capture_output=True).stdout.strip():
    raise SystemExit("REFUSING: a harness is running")

import numpy as np
import analog_replay as ar, compass, reset_env, slow_traverse as st, walk_steps as ws
import cv2, places

def grey():
    im = compass.fast_capture(); return im, np.asarray(im.convert("L"), dtype=float)

def pair_inliers(a, b):
    """matches between two frames, RANSAC-filtered -- the crawl-mode signal."""
    ka, da = places.keypoints(a); kb, db = places.keypoints(b)
    if da is None or db is None or len(ka) < 8 or len(kb) < 8: return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    m = bf.match(da, db)
    if len(m) < 8: return len(m)
    src = np.float32([ka[x.queryIdx].pt for x in m]); dst = np.float32([kb[x.trainIdx].pt for x in m])
    _, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
    return int(mask.sum()) if mask is not None else 0

reset_env.reset_environment(log=lambda *a: None, progress_file="progress_testing.json")
time.sleep(1.5)
st.turn_to(271.3, ws.read_heading, compass.fast_capture, log=lambda *a: None)
print(f"facing {ws.read_heading():.0f}; each push holds {HOLD}s\n")
print(f"{'mag':>5s} {'null':>6s} {'push':>6s} {'ratio':>7s}   verdict (moved < ~0.3, blocked > ~0.7)")
rows = []
for mag in MAGS:
    a0, _ = grey(); time.sleep(HOLD); a1, _ = grey()
    null = pair_inliers(a0, a1)
    b0, _ = grey()
    ar.send(["left_x 0", f"left_y {ar.to_axis(-abs(mag))}", "right_x 0", "right_y 0"])
    time.sleep(HOLD); ar.send(["left_x 0", "left_y 0"]); time.sleep(0.35)
    b1, _ = grey()
    push = pair_inliers(b0, b1)
    ratio = None if not null else round(push / null, 2)
    verdict = "?" if ratio is None else ("MOVED" if ratio < 0.3 else "blocked/no move" if ratio > 0.7 else "in between")
    print(f"{mag:5.2f} {null!s:>6s} {push!s:>6s} {ratio!s:>7s}   {verdict}")
    rows.append({"mag": mag, "null": null, "push": push, "ratio": ratio})
os.makedirs("overnight/census", exist_ok=True)
json.dump(rows, open("overnight/census/stick_floor.json", "w"), indent=1)
print("\n-> overnight/census/stick_floor.json")
