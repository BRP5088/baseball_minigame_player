"""Offline A/B of table_prompt's stroke mask: shipped vs local-contrast variants.

WHY. overnight/goal_leg_failframes/at_dealer_table_1788787236276.jpg (goal-leg
A/B trial 1, 2026-09-07) shows the character AT the dealer's table with the
prompt "Baseball Cards [] Play ($50)" plainly on screen, inside TEXT_BOX, and
at_table() scored it -0.001 with ink 0.0001. The camera was pitched down onto
the LIGHT table top, and the shipped mask keeps a pixel only if it is > 175 and
its 11x11 neighbourhood averages < 140 -- white text on a bright background is
invisible to it by construction. That rule exists to exclude the dealer's white
face (bright pixels whose surroundings are bright). A local-contrast rule --
pixel minus neighbourhood mean above a delta -- excludes her too and admits
text on any background. Whether it lets the quest log or anything else through
is measured here, not argued.

The detector on disk is NOT modified: the variant is monkeypatched into this
process only, so this can run while a live A/B imports table_prompt fresh.

CORPORA (every frame on disk that can say something):
  POS_KNOWN   the three frames known to carry the prompt: the recorded anchor
              (score 0.3503), the OPEN-14 trial-2 arrival, and the bright-table
              frame above (shipped score -0.001)
  DEMO        all demo archive frames; the shipped detector's own verdicts
              split them into old-positives (at_table True) and the rest
  NEG_NODES   every leg-end frame at a non-table node under overnight/
              (office_door, portrait_room, bar_pool_room, bar_jukebox): the
              prompt cannot exist there, so any hit is a false positive
  NEG_QL      demos/walk2_pauses_20260828_044514/f_0049.22.jpg, the quest-log
              false positive that set MATCH_MIN

    taskpolicy -b .venv/bin/python -B tools/prompt_mask_ab.py
      -> overnight/census/prompt_mask_ab.json (never overwritten)
"""
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter
import table_prompt as tp

OUT = "overnight/census/prompt_mask_ab.json"
POS_KNOWN = {
    "anchor_recorded": "demos/spawn_to_table_20260827_212516/f_0054.32.jpg",
    "open14_trial2_arrival": "overnight/streak_table_failframes/at_dealer_table_1788765494244.jpg",
    "bright_table_goalleg_t1": "overnight/goal_leg_failframes/at_dealer_table_1788787236276.jpg",
}
NEG_QL = "demos/walk2_pauses_20260828_044514/f_0049.22.jpg"
VARIANTS = {"shipped": None, "delta20": 20, "delta30": 30, "delta40": 40, "delta50": 50, "delta60": 60}


def make_mask(delta):
    def mask(img):
        a = tp._raw_patch(img)
        if a.std() < 1.0:
            return np.zeros_like(a)
        local = uniform_filter(a, size=tp.STROKE_WIN)
        if delta is None:
            return ((a > tp.STROKE_BRIGHT) & (local < tp.STROKE_LOCAL)).astype(float)
        return ((a > tp.STROKE_BRIGHT) & ((a - local) > delta)).astype(float)
    return mask


def measure(img):
    std = float(tp._raw_patch(img).std())
    k = float(tp.ink(img))
    s = float(tp.score(img))
    return {"std": round(std, 2), "ink": round(k, 4), "score": round(s, 4),
            "at_table": bool(std >= tp.MIN_CONTRAST and k >= tp.INK_MIN and s >= tp.MATCH_MIN)}


def main():
    if os.path.exists(OUT):
        sys.exit(f"refusing to overwrite {OUT}")
    demo = sorted(glob.glob("demos/*/*.jpg"))
    neg_nodes = sorted(f for f in glob.glob("overnight/*failframes*/at_*.jpg")
                       if not os.path.basename(f).startswith("at_dealer_table"))
    files = {"POS_KNOWN": list(POS_KNOWN.values()), "DEMO": demo, "NEG_NODES": neg_nodes, "NEG_QL": [NEG_QL]}
    for k, v in files.items():
        print(f"  {k:10} {len(v)} frames", flush=True)
    orig_mask = tp._stroke_mask
    rows = {}          # file -> {variant -> measure}
    t0 = time.time()
    try:
        for name, delta in VARIANTS.items():
            tp._stroke_mask = make_mask(delta)
            tp._CACHE = None                     # references are masked too
            n = 0
            for group, fl in files.items():
                for f in fl:
                    try:
                        m = measure(Image.open(f).convert("RGB"))
                    except Exception as e:
                        m = {"error": f"{type(e).__name__}: {e}"}
                    rows.setdefault(f, {"group": group})[name] = m
                    n += 1
            print(f"  {name:8} scored {n} frames  ({time.time() - t0:.0f}s)", flush=True)
    finally:
        tp._stroke_mask = orig_mask
        tp._CACHE = None

    # --- the numbers that decide ------------------------------------------
    summary = {}
    old_pos = [f for f, r in rows.items() if r["group"] == "DEMO" and r["shipped"].get("at_table")]
    demo_rest = [f for f, r in rows.items() if r["group"] == "DEMO" and not r["shipped"].get("at_table")]
    for name in VARIANTS:
        g = lambda f: rows[f][name]
        s = {
            "pos_known": {k: g(v) for k, v in POS_KNOWN.items()},
            "old_positives": {"n": len(old_pos),
                              "still_true": sum(1 for f in old_pos if g(f).get("at_table")),
                              "min_score": min((g(f)["score"] for f in old_pos), default=None),
                              "min_ink": min((g(f)["ink"] for f in old_pos), default=None)},
            "neg_nodes": {"n": len(neg_nodes),
                          "false_pos": sum(1 for f in neg_nodes if g(f).get("at_table")),
                          "max_score": max((g(f)["score"] for f in neg_nodes), default=None),
                          "top": sorted(((g(f)["score"], g(f)["ink"], f) for f in neg_nodes), reverse=True)[:5]},
            "demo_rest": {"n": len(demo_rest),
                          "newly_true": sum(1 for f in demo_rest if g(f).get("at_table")),
                          "top": sorted(((g(f)["score"], g(f)["ink"], f) for f in demo_rest), reverse=True)[:8]},
            "neg_ql": g(NEG_QL),
        }
        summary[name] = s
        print(f"\n== {name} ==")
        for k, v in s["pos_known"].items():
            print(f"  POS {k:26} score {v['score']:6.3f} ink {v['ink']:.4f} std {v['std']:5.1f} at_table {v['at_table']}")
        print(f"  old positives {s['old_positives']['still_true']}/{s['old_positives']['n']} still True; min score {s['old_positives']['min_score']}, min ink {s['old_positives']['min_ink']}")
        print(f"  NEG_NODES false positives {s['neg_nodes']['false_pos']}/{s['neg_nodes']['n']}; max score {s['neg_nodes']['max_score']}")
        for sc, k, f in s["neg_nodes"]["top"][:3]:
            print(f"      {sc:6.3f} ink {k:.4f} {f}")
        print(f"  DEMO rest newly True {s['demo_rest']['newly_true']}/{s['demo_rest']['n']}")
        for sc, k, f in s["demo_rest"]["top"][:5]:
            print(f"      {sc:6.3f} ink {k:.4f} {f}")
        print(f"  NEG_QL quest-log anchor: score {s['neg_ql']['score']:.3f} ink {s['neg_ql']['ink']:.4f} at_table {s['neg_ql']['at_table']}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({"question": "shipped stroke mask vs local-contrast variants for table_prompt",
                   "gates": {"MATCH_MIN": tp.MATCH_MIN, "INK_MIN": tp.INK_MIN, "MIN_CONTRAST": tp.MIN_CONTRAST,
                             "STROKE_BRIGHT": tp.STROKE_BRIGHT, "STROKE_LOCAL": tp.STROKE_LOCAL, "STROKE_WIN": tp.STROKE_WIN},
                   "variants": {k: (v if v is not None else "shipped: bright AND local<STROKE_LOCAL") for k, v in VARIANTS.items()},
                   "summary": summary, "frames": rows}, fh, indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
