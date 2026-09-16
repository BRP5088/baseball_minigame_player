"""Score the tactics-kind bank on frames that did NOT supply a template.

CLAUDE.md 30: a template matches its own source at 1.000, so the frames the bank
was cut from say nothing. The gate has to sit between the RIGHT population and
the WRONG one, measured on held-out frames (10.4).

GROUND TRUTH IS WHAT WE PLAYED, not what a reader says:
    reveal6  we PITCHED a fielding boost; they BATTED a speed boost
    reveal   we BATTED a power swing;     they PITCHED a pitch focus
The badge position per side is found by the shipped disc search, so a frame where
the card has not landed yet simply yields nothing rather than a wrong label.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reveal_cards as rc

SOURCES = {"f_001503.jpg", "f_002645.jpg", "f_003571.jpg",
           "r_003660.jpg", "r_006285.jpg"}
SETS = [
    ("test_fixtures/reveal_kind_truth/reveal6/f_*.jpg", "fielding_boost", "speed_boost"),
    ("test_fixtures/reveal_kind_truth/reveal/r_*.jpg", "pitch_boost", "swing_boost"),
]


def badge_of(im, zone):
    d = rc._discs(im, zone)
    if len(d) < 2:
        return None
    player = max(d, key=lambda c: c[1])
    up = [c for c in d if c[1] < player[1] - 20]
    return min(up, key=lambda c: c[1]) if up else None


if __name__ == "__main__":
    os.environ["BASEBALL_TEST_RUN"] = "1"
    right, wrong, skipped = [], [], 0
    rows = []
    for pat, mound_kind, home_kind in SETS:
        for p in sorted(glob.glob(pat)):
            if os.path.basename(p) in SOURCES:
                continue
            im = Image.open(p)
            for zone, truth in ((rc.ZONE_MOUND, mound_kind), (rc.ZONE_HOME, home_kind)):
                sc = rc.tactics_kind_scores(im, zone)
                if not sc:
                    skipped += 1
                    continue
                right.append(sc.get(truth, 0.0))
                wrong.extend(v for k, v in sc.items() if k != truth)
                rows.append({"file": os.path.basename(p), "truth": truth,
                             "scores": {k: round(v, 4) for k, v in sc.items()}})
    r, w = np.array(right), np.array(wrong)
    print(f"held-out readings: {r.size} right-kind, {w.size} wrong-kind, {skipped} skipped\n")
    if r.size:
        print(f"RIGHT kind   min {r.min():.3f}  p05 {np.percentile(r,5):.3f}  "
              f"p50 {np.percentile(r,50):.3f}  max {r.max():.3f}")
    if w.size:
        print(f"WRONG kind   p50 {np.percentile(w,50):.3f}  p95 {np.percentile(w,95):.3f}  "
              f"p99 {np.percentile(w,99):.3f}  MAX {w.max():.3f}")
    if r.size and w.size:
        print(f"\ngap = {r.min() - w.max():+.3f}   (right min {r.min():.3f} vs wrong MAX {w.max():.3f})")
        print(f"midpoint {(r.min()+w.max())/2:.3f}   shipped gate {rc.TACTICS_KIND_MIN}")
        bad = (w >= rc.TACTICS_KIND_MIN).sum()
        miss = (r < rc.TACTICS_KIND_MIN).sum()
        print(f"at {rc.TACTICS_KIND_MIN}: {bad} wrong-kind readings clear it, "
              f"{miss} right-kind readings fall under it")
    os.makedirs("agent_progress/banner-kind", exist_ok=True)
    with open("agent_progress/banner-kind/census.json", "w") as fh:
        json.dump({"right": right, "wrong": wrong, "rows": rows}, fh)
