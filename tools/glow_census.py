"""Measure the cursor-glow populations at the CURRENT capture geometry.

CURSOR_GLOW_MIN was fitted on 12 curated fixtures whose hand crop was 1020 px --
the old upscaling _fast_grab (2000 px frame). The rig produces 979 px. Live on
2026-09-15 the true reading was 12.4 against a gate of 15.0 and every action
refused, so the gate was dropped to 5.0 PROVISIONALLY, on one match's evidence,
and its own comment says it is a stopgap and not a finding. This is the census
that comment asks for.

THE LABEL MUST NOT BE THE GLOW, or the threshold is fitted to its own output
(CLAUDE.md 10.22: a pipeline whose output defines the alignment cannot be scored
on that alignment). The cursor LIFTS the card it sits on -- section 10.23
records the badge riding up with it, and 10.28 records the card rising above its
neighbours when the cursor moves onto it. Lift is a GEOMETRIC measurement and
glow is a BRIGHTNESS one, so labelling by lift and scoring glow keeps the two
independent.

AMBIGUOUS FRAMES ARE EXCLUDED, NOT GUESSED, and the count is reported: a
SELECTED card also rises, so a frame with two raised slots cannot say which one
holds the cursor. 10.22 again -- report how many samples were excluded, never
just the rate.

Read-only. Operates on PNG crops already on disk; touches no console.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_hand as lh

LIFT_MIN = 12.0     # px at reference scale; SELECT_LIFT_MIN_PX is 6 and 44 px was
                    # measured for a full selection lift, so this sits between a
                    # jitter and a real rise rather than being picked for an answer.


def census(paths):
    true_g, false_g = [], []
    excluded = {"not_five_rows": 0, "no_lift": 0, "two_lifts": 0, "read_failed": 0}
    used = 0
    for p in paths:
        try:
            im = Image.open(p).convert("RGB")
            rows = lh.read_hand(im)
        except Exception:
            excluded["read_failed"] += 1
            continue
        if len(rows) != 5:
            excluded["not_five_rows"] += 1
            continue
        sc = im.width / lh.ANCHOR_W
        lifts = []
        for i, r in enumerate(rows):
            y = r.get("y")
            if y is None or r.get("y_measured") is False:
                lifts.append(None)
                continue
            lifts.append(lh.SLOT_PLAYER[i][1] * sc - y)
        raised = [i for i, L in enumerate(lifts) if L is not None and L >= LIFT_MIN]
        if not raised:
            excluded["no_lift"] += 1
            continue
        if len(raised) > 1:
            excluded["two_lifts"] += 1
            continue
        try:
            _, glow, _ = lh.cursor_glow(im, rows=rows)
        except Exception:
            excluded["read_failed"] += 1
            continue
        if len(glow) != 5:
            excluded["read_failed"] += 1
            continue
        used += 1
        k = raised[0]
        true_g.append(glow[k])
        false_g.extend(glow[i] for i in range(5) if i != k)
    return true_g, false_g, excluded, used


def report(true_g, false_g, excluded, used):
    t, f = np.array(true_g), np.array(false_g)
    out = {"used_frames": used, "excluded": excluded,
           "true_n": int(t.size), "false_n": int(f.size)}
    if t.size:
        out["true"] = {"min": float(t.min()), "p01": float(np.percentile(t, 1)),
                       "p05": float(np.percentile(t, 5)), "p50": float(np.percentile(t, 50)),
                       "max": float(t.max())}
    if f.size:
        out["false"] = {"p50": float(np.percentile(f, 50)), "p95": float(np.percentile(f, 95)),
                        "p99": float(np.percentile(f, 99)), "max": float(f.max())}
    if t.size and f.size:
        out["separated"] = bool(t.min() > f.max())
        out["gap"] = float(t.min() - f.max())
        out["midpoint"] = float((t.min() + f.max()) / 2)
    return out


if __name__ == "__main__":
    pats = sys.argv[1:] or ["agent_progress/deal-frames/*/loss_*/f*.png"]
    paths = sorted(set(sum([glob.glob(p) for p in pats], [])))
    # EVERY 3rd FRAME: neighbouring frames of a 60 fps dump are nearly the same
    # picture, and scoring across them measures the encoder, not the reader.
    paths = paths[::3]
    print(f"{len(paths)} crops", flush=True)
    t, f, ex, used = census(paths)
    r = report(t, f, ex, used)
    print(json.dumps(r, indent=1))
    os.makedirs("agent_progress/glow-recal", exist_ok=True)
    with open("agent_progress/glow-recal/census.json", "w") as fh:
        json.dump({**r, "true": t, "false": f}, fh)
