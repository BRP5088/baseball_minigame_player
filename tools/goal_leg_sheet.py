"""Contact sheet of the goal-leg A/B frames: one row per valid trial.

    .venv/bin/python -B tools/goal_leg_sheet.py   -> overnight/goal_leg_sheet.jpg

Row: [pre-sweep leg end | post-sweep] labelled `t<n> <arm> ARRIVED|missed`.
Frames are matched to trials BY ORDER: the goal leg runs exactly once per
valid trial (walk_leg_under_test, attempts=1), a setup miss writes no
at_dealer_table frame, and epoch order is trial order. Read-only over the
frames; writes one jpeg. Re-runnable while the A/B is in flight.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, "overnight", "goal_leg_failframes")
RESULT = os.path.join(ROOT, "overnight", "ab_goal_leg.json")
OUT = os.path.join(ROOT, "overnight", "goal_leg_sheet.jpg")
W, H = 480, 270


def main():
    from PIL import Image, ImageDraw
    runs = json.load(open(RESULT))["runs"]
    valid = [(i + 1, r) for i, r in enumerate(runs) if r.get("arrived") is not None]
    pre = sorted(glob.glob(os.path.join(FRAMES, "at_dealer_table_[0-9]*.jpg")))
    post = sorted(glob.glob(os.path.join(FRAMES, "at_dealer_table_postsweep_*.jpg")))
    n = min(len(valid), len(pre))
    if len(pre) != len(valid):
        print(f"  NOTE {len(pre)} pre-sweep frames for {len(valid)} valid trials "
              f"(a trial may still be in flight); showing {n}")
    sheet = Image.new("RGB", (2 * W, max(1, n) * H), "black")
    d = ImageDraw.Draw(sheet)
    for k in range(n):
        t, r = valid[k]
        label = f"t{t} {r['arm']} {'ARRIVED' if r['arrived'] else 'missed'}  recheck={r.get('recheck_at_table')}"
        for col, f in ((0, pre[k]), (1, post[k] if k < len(post) else None)):
            if f is None:
                continue
            im = Image.open(f).convert("RGB").resize((W, H))
            sheet.paste(im, (col * W, k * H))
        d.rectangle((0, k * H, 2 * W, k * H + 18), fill="black")
        d.text((4, k * H + 3), label + "    [pre-sweep | post-sweep]", fill="white")
    sheet.save(OUT, quality=80)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}  rows={n}")
    for t, r in valid:
        print(f"  t{t:<3}{r['arm']:9} {'ARRIVED' if r['arrived'] else 'missed '} "
              f"leg {r.get('seconds')}s setup {r.get('setup_seconds')}s "
              f"located={r.get('located')} kinds_leg_end={r.get('failure_kinds_leg_end')}")


if __name__ == "__main__":
    main()
