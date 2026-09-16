"""Score the reveal-banner bank over the archive. Read-only.

THE POSITIVES HERE ARE WORTH MORE THAN THE ONES IT WAS CUT FROM. A template
matches its own source at 1.000 (CLAUDE.md 30), so the frames the bank came from
say nothing. These recordings are OTHER sessions on other days, so any genuine
HOME RUN! they contain is the cross-session validation the result reader needed
and got from exactly this corpus.

AND THE HIGHEST-SCORING NEGATIVES ARE EXTRACTED TO BE LOOKED AT (10.31). The
result reader's census listed its top four "non-result" frames and TWO WERE
DRAWS -- a class the labeller did not have, ranked highest precisely because it
could not name them, and reported as healthy headroom. So this saves the top
frames rather than trusting the number.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reveal_banner as rb

STRIDE = 12


def census(path, stride=STRIDE, keep_top=12):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    rows, top, i = [], [], 0
    while True:
        if not cap.grab():
            break
        if i % stride == 0:
            ok, fr = cap.retrieve()
            if ok:
                im = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
                try:
                    s = rb.scores(im)
                except Exception:
                    i += 1
                    continue
                best = max(s, key=s.get)
                rows.append((i, best, round(s[best], 4),
                             round(s.get("home_run", 0), 4), round(s.get("play_ball", 0), 4)))
                top.append((s[best], i, best, im))
                top.sort(key=lambda r: -r[0])
                top[:] = top[:keep_top]
        i += 1
    cap.release()
    return rows, top, fps, i


if __name__ == "__main__":
    os.environ["BASEBALL_TEST_RUN"] = "1"
    path = sys.argv[1]
    outroot = sys.argv[2] if len(sys.argv) > 2 else "agent_progress/banner-census"
    os.makedirs(outroot, exist_ok=True)
    name = os.path.basename(os.path.dirname(path))
    rows, top, fps, total = census(path)
    arr = np.array([r[2] for r in rows]) if rows else np.array([0.0])
    print(f"{name}: {total} frames, {len(rows)} sampled", flush=True)
    print("  best-score percentiles: "
          + ", ".join(f"p{q}={np.percentile(arr, q):.3f}" for q in (50, 90, 99))
          + f", MAX={arr.max():.3f}")
    d = os.path.join(outroot, name)
    os.makedirs(d, exist_ok=True)
    for rank, (sc, idx, label, im) in enumerate(top):
        im.save(os.path.join(d, f"top{rank:02d}_{label}_{sc:.3f}_f{idx:07d}.jpg"), quality=90)
    hits = [r for r in rows if r[2] >= rb.BANNER_MIN]
    print(f"  frames at or above BANNER_MIN {rb.BANNER_MIN}: {len(hits)}"
          + (f"  -> {[(h[0], h[1], h[2]) for h in hits[:8]]}" if hits else ""))
    with open(os.path.join(d, "rows.json"), "w") as fh:
        json.dump({"video": path, "fps": fps, "rows": rows}, fh)
