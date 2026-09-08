"""Tile a chain walk's frame at every TURN STOP beside the chain's own frame there.

The user's review rule (2026-09-07): look at the turns first. If the scene after
a turn is not the chain's scene at that stop, the character did not move far
enough before the plan said "turn" -- a turn taken on dead reckoning. One tile
per trial answers that in a glance; reasoning about it from the log did not.

    .venv/bin/python -B tools/turn_review.py <shots dir> <journal.jsonl> <chain dir> [out.jpg]
    .venv/bin/python -B tools/turn_review.py --latest                 # newest shots dir + journal
"""
import glob, json, os, re, sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def newest(pattern):
    fs = glob.glob(pattern)
    return max(fs, key=os.path.getmtime) if fs else None


def turn_rows(journal):
    rows = [json.loads(l) for l in open(journal) if l.strip()]
    return [r for r in rows if str(r.get("action", "")).startswith(
        ("turned", "turn-retry", "rescued"))]


def frame_for(shots, iteration):
    fs = sorted(glob.glob(os.path.join(shots, f"it_{iteration:03d}_k*.jpg")))
    return fs[0] if fs else None


def label(im, text):
    im = cv2.resize(im, (480, 270))
    cv2.putText(im, text, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return im


def review(shots, journal, chain_dir, out=None):
    rows = turn_rows(journal)
    tiles = []
    for r in rows:
        live = frame_for(shots, int(r["iteration"]))
        ref = os.path.join(chain_dir, f"{int(r['target']):04d}.jpg")
        a = cv2.imread(live) if live else None
        b = cv2.imread(ref)
        if a is None or b is None:
            continue
        tiles.append(cv2.hconcat([label(a, f"it {r['iteration']} {r['action']} k={r['k']}"),
                                  label(b, f"chain {r['target']}")]))
    if not tiles:
        print("no turn rows with frames"); return None
    out = out or os.path.join(os.path.dirname(shots.rstrip("/")), "turn_review_" + os.path.basename(shots.rstrip("/")) + ".jpg")
    cv2.imwrite(out, cv2.vconcat(tiles))
    print(f"{len(tiles)} turn(s) -> {out}")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    chain_dir = os.path.join(ROOT, "chains", "route_user_1853")
    if a and a[0] == "--latest":
        shots = newest(os.path.join(ROOT, "overnight", "chain_frames", "t*"))
        journal = newest(os.path.join(ROOT, "overnight", "chain_journals", "*.jsonl"))
        review(shots, journal, chain_dir)
    else:
        review(a[0], a[1], a[2] if len(a) > 2 else chain_dir, a[3] if len(a) > 3 else None)
