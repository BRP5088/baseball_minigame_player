"""Find the frames whose top glow lands in the DECISION ZONE, and sheet them.

WHY NOT AN AUTOMATIC LABEL. The cursor does NOT reliably lift the card it sits
on -- measured over 83 archive frames with a lit card, the max-glow slot was
also the max-lift slot exactly 2 times, and frames read glow 22-26 with a lift
of -2 px. Lift is the SELECTION signal (selected_cards' own docstring says so),
so it cannot label the cursor, and there is no other offline signal that is
independent of the glow itself.

WHY NOT LABEL BY MARGIN EITHER. Taking "the slot beating every other by 20x" as
true is tempting and it is 10.31's missing-class trap: it can only ever sample
frames where the true reading is already HIGH, which excludes precisely the dim
true frames the gate has to admit. The live failure read 12.4 -- a value this
corpus's confident frames never contain.

SO: collect the frames whose top reading falls in the band where the answer is
actually in doubt, and ADJUDICATE THEM BY EYE (10.23's contact sheet, the
cheapest diagnostic on this project). The gate then sits between two eye-labelled
populations rather than between a reader and itself.

Read-only.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_hand as lh

ZONE = (1.0, 22.0)     # deliberately WIDE: it must contain the live 12.4 that
                       # failed, the old 8.4 false ceiling and the old 20.7 true
                       # floor, so the sheet cannot beg the question.


def scan(paths):
    rows_out = []
    for p in paths:
        try:
            im = Image.open(p).convert("RGB")
            rows = lh.read_hand(im)
            if len(rows) != 5:
                continue
            _, glow, _ = lh.cursor_glow(im, rows=rows)
        except Exception:
            continue
        if len(glow) != 5:
            continue
        top = max(glow)
        rows_out.append({"path": p, "glow": glow, "top": top,
                         "argmax": int(np.argmax(glow)),
                         "runner_up": float(sorted(glow)[-2])})
    return rows_out


def sheet(items, out, cols=3):
    tiles = []
    for it in items:
        im = Image.open(it["path"]).convert("RGB")
        im = im.resize((im.width, im.height))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, im.width, 22], fill=(255, 255, 255))
        d.text((4, 5), f"top={it['top']} at slot {it['argmax']}  glow={it['glow']}",
               fill=(0, 0, 0))
        tiles.append(im)
    if not tiles:
        return 0
    w, h = tiles[0].size
    sc = 560 / w
    w, h = int(w * sc), int(h * sc)
    tiles = [t.resize((w, h), Image.LANCZOS) for t in tiles]
    rows_n = (len(tiles) + cols - 1) // cols
    sheet_im = Image.new("RGB", (w * cols, h * rows_n), (20, 20, 20))
    for k, t in enumerate(tiles):
        sheet_im.paste(t, ((k % cols) * w, (k // cols) * h))
    sheet_im.save(out)
    return len(tiles)


if __name__ == "__main__":
    paths = sorted(glob.glob("agent_progress/deal-frames/*/loss_*/f*.png"))[::5]
    print(f"scanning {len(paths)} crops", flush=True)
    items = scan(paths)
    zone = [i for i in items if ZONE[0] <= i["top"] <= ZONE[1]]
    high = [i for i in items if i["top"] > ZONE[1]]
    low = [i for i in items if i["top"] < ZONE[0]]
    print(f"read ok: {len(items)}   below zone: {len(low)}   IN ZONE: {len(zone)}   above: {len(high)}")
    if items:
        tops = np.array([i["top"] for i in items])
        print("top-glow percentiles:",
              {q: round(float(np.percentile(tops, q)), 1) for q in (5, 25, 50, 75, 90, 95, 99)})
    os.makedirs("agent_progress/glow-recal", exist_ok=True)
    # SPREAD THE SAMPLE ACROSS THE BAND rather than taking the first N, which
    # would all come from one event and one match.
    zone.sort(key=lambda i: i["top"])
    pick = zone[:: max(1, len(zone) // 12)][:12]
    n = sheet(pick, "agent_progress/glow-recal/zone_sheet.png")
    with open("agent_progress/glow-recal/zone.json", "w") as fh:
        json.dump({"in_zone": len(zone), "picked": [i["path"] for i in pick],
                   "items": zone[:400]}, fh, indent=1)
    print(f"sheeted {n} frames -> agent_progress/glow-recal/zone_sheet.png")
