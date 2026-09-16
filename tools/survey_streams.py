"""Which recorded streams actually contain TURN screens? Read-only.

Sampling a handful of frames per video is enough to tell a match recording from
a Control Center recording -- the first video tried held 101 s of the PS5 home
overlay and returned max rows 0 on every frame, which reads identically to "the
reader is broken" (10.1). This separates the two before any mining starts.
"""
import json
import os
import sys

import cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import orchestrator as o
import local_hand

HAND_FRAC = o.GAMEPLAY_REGIONS_FRAC["hand"]
SAMPLES = 60


def survey(path, samples=SAMPLES):
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    hits, rows_seen, turnish = 0, [], []
    for k in range(samples):
        idx = int(n * (k + 0.5) / samples)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        x0, y0, x1, y1 = HAND_FRAC
        crop = fr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
        im = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        tw = int(local_hand.ANCHOR_W)
        if im.width != tw:
            im = im.resize((tw, max(1, round(im.height * tw / im.width))), Image.LANCZOS)
        try:
            got = local_hand.read_hand(im)
        except Exception:
            got = []
        rows_seen.append(len(got))
        if len(got) >= 4:
            hits += 1
            turnish.append(idx)
    cap.release()
    return {"path": path, "frames": n, "fps": round(fps, 1),
            "seconds": round(n / max(fps, 1)),
            "sampled": len(rows_seen), "turn_frames": hits,
            "max_rows": max(rows_seen, default=0),
            "turn_indices": turnish[:12]}


if __name__ == "__main__":
    # SET INSIDE __main__, NEVER AT IMPORT. tests/harness/test_no_import_time_
    # test_run_flag.py AST-scans tools/ for exactly that, because an import-time
    # flag once silently disabled stick injection inside a LIVE harness. Here it
    # marks this process as offline analysis, so the readers do not write the
    # rig's hand_memory.json with a recording's cards.
    os.environ["BASEBALL_TEST_RUN"] = "1"
    out = []
    for p in sys.argv[1:]:
        r = survey(p)
        out.append(r)
        print(f"{r['turn_frames']:3}/{r['sampled']:3} turn-ish  max_rows {r['max_rows']}  "
              f"{r['seconds']:5}s  {p}", flush=True)
    print(json.dumps(out))
