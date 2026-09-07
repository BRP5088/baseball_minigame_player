"""Contact sheet + post-hoc table of the goal-leg A/B frames, one row per EXECUTED leg.

    .venv/bin/python -B tools/goal_leg_sheet.py   -> overnight/goal_leg_sheet.jpg + a table

Frames are matched to trials from the LOG's own order: a trial that reached
`leg bar_jukebox -> dealer_table` wrote exactly one pre-sweep at_dealer_table
frame, whether or not it was later censored by the ceiling. Matching by
"one frame per valid trial" was wrong the moment trial 5 was killed during
its sweep with its pre-sweep frame already on disk.

The table re-scores every pre-sweep frame with the shipped mask AND with the
OCR read (tools/prompt_ocr_ab.read), because the mask cannot see the prompt
over a bright background (CLAUDE.md, at_table 2026-09-07): PROMPT ON SCREEN
at the leg's end is the leg-level arrival criterion, independent of the sweep.
Read-only over frames; writes one jpeg.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
FRAMES = os.path.join(ROOT, "overnight", "goal_leg_failframes")
RESULT = os.path.join(ROOT, "overnight", "ab_goal_leg.json")
LOG = os.path.join(ROOT, "overnight", "ab_goal_leg.log")
OUT = os.path.join(ROOT, "overnight", "goal_leg_sheet.jpg")
W, H = 480, 270


def executed_legs():
    """[(trial_no, arm, outcome_line)] for every trial whose goal leg RAN, in order."""
    out, arm, ran = [], None, False
    for line in open(LOG, encoding="utf-8", errors="replace"):
        m = re.search(r"arm=(\w+)", line)
        if m:
            arm, ran = m.group(1), False
        if "leg bar_jukebox -> dealer_table" in line:
            ran = True
        t = re.match(r"\[\s*(\d+)\]\s+(\w+)\s+(.*)", line)
        if t:
            if ran:
                out.append((int(t.group(1)), t.group(2), t.group(3).strip()))
            arm, ran = None, False
    return out


def main():
    from PIL import Image, ImageDraw
    import table_prompt as tp
    import places
    import prompt_ocr_ab as ocr
    legs = executed_legs()
    pre = sorted(glob.glob(os.path.join(FRAMES, "at_dealer_table_[0-9]*.jpg")))
    post = {os.path.basename(f)[:-4].rsplit("_", 1)[1]: f
            for f in glob.glob(os.path.join(FRAMES, "at_dealer_table_postsweep_*.jpg"))}
    n = min(len(legs), len(pre))
    if len(pre) != len(legs):
        print(f"  NOTE {len(pre)} pre-sweep frames for {len(legs)} executed legs "
              f"(one may be in flight); showing {n}")
    rows = []
    for k in range(n):
        t, arm, outcome = legs[k]
        im = Image.open(pre[k]).convert("RGB")
        o = ocr.read(im)
        room, sc, mg = places.identify(im)
        at = bool(tp.at_table(im))
        rows.append({"trial": t, "arm": arm, "outcome": outcome.split()[0], "pre": pre[k],
                     "mask_score": round(float(tp.score(im)), 3), "ink": round(float(tp.ink(im)), 4),
                     "mask_at_table": at, "ocr_words": o["words"], "ocr_text": o["text"],
                     "identify": (room, sc, round(mg, 2)), "prompt_on_screen": at or o["words"] >= 2})
    sheet = Image.new("RGB", (2 * W, max(1, n) * H), "black")
    d = ImageDraw.Draw(sheet)
    for k, r in enumerate(rows):
        # post-sweep frames pair with pre-sweep frames by order too
        posts = sorted(post.values())
        for col, f in ((0, r["pre"]), (1, posts[k] if k < len(posts) else None)):
            if f:
                sheet.paste(Image.open(f).convert("RGB").resize((W, H)), (col * W, k * H))
        d.rectangle((0, k * H, 2 * W, k * H + 18), fill="black")
        d.text((4, k * H + 3), f"t{r['trial']} {r['arm']} {r['outcome']}  prompt_on_screen={r['prompt_on_screen']}"
               f"  mask {r['mask_score']}/{r['ink']}  ocr {r['ocr_words']}   [pre-sweep | post-sweep]", fill="white")
    sheet.save(OUT, quality=80)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}  rows={n}")
    print(f"  {'trial':6}{'arm':10}{'harness':9}{'mask':>7}{'ink':>8}{'ocr':>4}  {'identify':22}  PROMPT ON SCREEN")
    for r in rows:
        room, sc, mg = r["identify"]
        print(f"  t{r['trial']:<5}{r['arm']:10}{r['outcome']:9}{r['mask_score']:7.3f}{r['ink']:8.4f}{r['ocr_words']:4}  "
              f"{str(room):12}{sc:5.0f}/{mg:<4}  {r['prompt_on_screen']}")
    by = {}
    for r in rows:
        a = by.setdefault(r["arm"], [0, 0, 0])
        a[0] += 1; a[1] += r["prompt_on_screen"]; a[2] += r["outcome"] == "ARRIVED"
    for arm, (nn, ps, hs) in by.items():
        print(f"  {arm:9} executed {nn}: harness ARRIVED {hs}, prompt on screen at leg end {ps}")


if __name__ == "__main__":
    main()
