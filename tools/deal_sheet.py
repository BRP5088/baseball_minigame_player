"""Contact sheet across one dumped event, cropped to the slot in question.

CLAUDE.md 10.23: build a contact sheet of the cards the reader called unsure and
LOOK. It is the cheapest diagnostic on this project, and it has already
overturned one conclusion in this investigation -- an event that measured as a
1.6 s occlusion turned out, on one glance, to be the hand TURNING OVER.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deal_frames as df


def sheet(event_dir, out, n=9):
    rows = json.load(open(os.path.join(event_dir, "rows.json")))
    slot = int(event_dir.rstrip("/").split("slot")[-1])

    def at(r):
        for c in r["cards"]:
            if c.get("slot") == slot:
                return c
        return None

    def ok(c):
        if not c:
            return False
        return ((c["digit"] is not None and c["secondary"] is not None)
                if c["kind"] == "player" else c["type"] is not None)

    flags = [ok(at(r)) for r in rows]
    # SAMPLE AROUND THE EDGE, not evenly: the interesting frames are the last
    # readable one and the first dark one, and an even spread walks past them.
    edge = next((i for i in range(1, len(flags)) if flags[i - 1] and not flags[i]), len(flags) // 2)
    picks = sorted(set([0, max(0, edge - 60), max(0, edge - 20), max(0, edge - 3),
                        edge, min(len(rows) - 1, edge + 3), min(len(rows) - 1, edge + 30),
                        min(len(rows) - 1, edge + 90), len(rows) - 1]))[:n]
    ax = df._ANCHOR_X[slot]
    tiles = []
    for i in picks:
        r = rows[i]
        f = os.path.join(event_dir, f"f{r['frame']:07d}.png")
        if not os.path.exists(f):
            continue
        im = Image.open(f).convert("RGB")
        c = at(r)
        x = (c or {}).get("x") or ax
        y = (c or {}).get("y") or 170
        box = im.crop((max(0, int(x - 80)), max(0, int(y - 90)),
                       min(im.width, int(x + 150)), min(im.height, int(y + 110))))
        box = box.resize((460, 400), Image.LANCZOS)
        d = ImageDraw.Draw(box)
        lbl = (f"t={r['t']:.2f}s  rows={r['n_rows']}  "
               + (f"READ {c.get('digit')}/{c.get('secondary')} s={c.get('score')}"
                  if ok(c) else
                  (f"UNREAD s={c.get('score')}" if c else "NO CARD IN SLOT")))
        d.rectangle([0, 0, 460, 24], fill=(255, 255, 255))
        d.text((6, 6), lbl, fill=(0, 0, 0))
        tiles.append(box)
    W = 3
    H = (len(tiles) + W - 1) // W
    out_im = Image.new("RGB", (460 * W, 400 * H), (25, 25, 25))
    for k, t in enumerate(tiles):
        out_im.paste(t, ((k % W) * 460, (k // W) * 400))
    out_im.save(out)
    return len(tiles), sum(flags), len(flags)


if __name__ == "__main__":
    n, good, total = sheet(sys.argv[1], sys.argv[2])
    print(f"{n} tiles; slot readable in {good}/{total} frames -> {sys.argv[2]}")
