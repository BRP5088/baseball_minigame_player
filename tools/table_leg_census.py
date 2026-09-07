"""Metric census of the table-leg END frames from the OPEN-14 streak run.

For every at_dealer_table_*.jpg (all 37 executions of bar_jukebox ->
dealer_table) and the two ok_dealer_table_*.jpg (the two trials scored as
arrivals), record what the project's own detectors say about the frame at the
moment the leg's last push finished, BEFORE reach_table's aim sweep:

    compass bearing, ORB keypoint count, places.identify(), table_prompt
    score / ink / at_table(), failure_kind.classify()

Read-only apart from ONE json under overnight/census/, never overwritten -- a
census is a record. Caveat carried in the output: these are q82 JPEGs, and
CLAUDE.md records that a saved JPEG can read a bearing differently from the
live capture; bearings here are evidence about the FILE.

    .venv/bin/python -B tools/table_leg_census.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FRAMES = ("overnight/streak_table_failframes/at_dealer_table_*.jpg",
          "overnight/streak_table_failframes/success/ok_dealer_table_*.jpg")
OUT = "overnight/census/table_leg_ends_20260907.json"
ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox", "dealer_table"]


def _safe(fn, *a):
    try:
        return fn(*a), None
    except Exception as e:                      # record, never hide
        return None, f"{type(e).__name__}: {e}"


def main():
    # Offline tool: hold every input path OFF -- but only when RUN as a script.
    # Set at import this flag disabled stick injection inside a live harness that
    # imported this module for its read() (prompt_zone, 2026-09-07).
    os.environ.setdefault("BASEBALL_TEST_RUN", "1")
    from PIL import Image
    import compass, places, table_prompt, failure_kind as fk
    out = os.path.join(ROOT, OUT)
    if os.path.exists(out):
        sys.exit(f"refusing to overwrite {OUT}")
    files = sorted(f for pat in FRAMES for f in glob.glob(os.path.join(ROOT, pat)))
    rows = []
    for f in files:
        img = Image.open(f)
        rel = os.path.relpath(f, ROOT)
        m = re.search(r"_(\d{13})\.jpg$", f)
        row = {"file": rel, "epoch_ms": int(m.group(1)) if m else None,
               "outcome_frame": "ok" if "/success/" in f else "leg_end"}
        row["bearing"], row["bearing_err"] = _safe(compass.read_bearing, img)
        kp, err = _safe(lambda im: len(places._orb().detect(places._as_gray(im), None)), img)
        if kp is None:
            import cv2
            kp, err = _safe(lambda im: len(cv2.ORB_create(nfeatures=1500).detect(places._as_gray(im), None)), img)
        row["keypoints"], row["keypoints_err"] = kp, err
        ident, err = _safe(places.identify, img)
        row["identify"] = ({"room": ident[0], "score": ident[1], "margin": ident[2]}
                           if ident else None)
        row["identify_err"] = err
        sc, err = _safe(table_prompt.score, img)
        row["prompt_score"] = sc if isinstance(sc, (int, float)) else (list(sc) if sc else None)
        row["prompt_score_err"] = err
        row["ink"], row["ink_err"] = _safe(table_prompt.ink, img)
        row["at_table"], row["at_table_err"] = _safe(table_prompt.at_table, img)
        kind, err = _safe(fk.classify, img, "dealer_table", ROUTE)
        row["kind"], row["kind_detail"], row["kind_err"] = (kind[0], kind[1], err) if kind else (None, None, err)
        rows.append(row)
        ident_s = f"{row['identify']['room']!s:12} {row['identify']['score']:6.1f}/{row['identify']['margin']:4.2f}" if row["identify"] else "identify ERR"
        b = f"{row['bearing']:6.1f}" if isinstance(row["bearing"], (int, float)) else "  None"
        ps = row["prompt_score"] if isinstance(row["prompt_score"], (int, float)) else -1
        print(f"{os.path.basename(rel):34} {row['outcome_frame']:7} brg {b} kp {row['keypoints']!s:5} "
              f"{ident_s} prompt {ps:5.3f} ink {row['ink'] if row['ink'] is not None else -1:5.3f} "
              f"at_table {row['at_table']!s:5} {row['kind']}")
    rows.sort(key=lambda r: r["epoch_ms"] or 0)
    doc = {"question": "what does the table leg's end frame look like to the detectors, before the aim sweep",
           "run": "overnight/streak_table.py 2026-09-07 02:26-06:45 (OPEN-14)",
           "caveats": ["q82 JPEGs: a saved JPEG can read a bearing differently from the live capture (CLAUDE.md, compass); bearings describe the FILE",
                       "leg_end frames precede reach_table's sweep; ok frames are the same moment for the two trials later scored as arrivals"],
           "n": len(rows), "frames": rows}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(doc, fh, indent=1)
    print(f"\nwrote {OUT}  n={len(rows)}")


if __name__ == "__main__":
    main()
