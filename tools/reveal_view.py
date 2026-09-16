"""Annotate a reveal frame with what the reader actually saw. Read-only.

A LIVE VIEW OF THE SETUP, at the user's request. Every box drawn here is a
region the code genuinely used and every number is what it genuinely read -- so
a wrong zone or a missed disc is visible at a glance instead of being inferred
from a None three layers down. CLAUDE.md 10.23's contact sheet, pointed at the
reader's own geometry.
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reveal_cards as rc
import reveal_banner as rb


def annotate(frame, phase="batting"):
    im = frame.convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    r = rc.read_reveal(im)
    label, detail = rb.read_banner(im)
    margin, why = rc.margin_from(r, phase)

    for name, zone, side in (("THEIRS (mound)", rc.ZONE_THEIRS, r["theirs"]),
                             ("OURS (home)", rc.ZONE_OURS, r["ours"])):
        x0, y0, x1, y1 = (int(w * zone[0]), int(h * zone[1]),
                          int(w * zone[2]), int(h * zone[3]))
        d.rectangle([x0, y0, x1, y1], outline=(255, 255, 255), width=3)
        txt = (f"{name}  power={side['power']} ({side['power_score']:.2f})  "
               f"bonus={'+' + str(side['bonus']) if side['bonus'] else None} "
               f"({side['bonus_score']:.2f})  discs={side['discs']}")
        d.rectangle([x0, y0 - 22, x0 + 8 * len(txt) + 8, y0], fill=(255, 255, 255))
        d.text((x0 + 4, y0 - 18), txt, fill=(0, 0, 0))
        for c in rc._discs(im, zone):
            d.ellipse([c[0] - c[2], c[1] - c[2], c[0] + c[2], c[1] + c[2]],
                      outline=(255, 255, 255), width=2)

    # the banner band the other reader searches
    bx0, by0, bx1, by1 = (int(w * rb.BAND[0]), int(h * rb.BAND[1]),
                          int(w * rb.BAND[2]), int(h * rb.BAND[3]))
    d.rectangle([bx0, by0, bx1, by1], outline=(180, 180, 180), width=2)

    lines = [f"banner : {label}  ({detail})",
             f"margin : {margin}",
             f"         {why}"]
    d.rectangle([20, h - 90, 20 + 11 * max(len(x) for x in lines), h - 10],
                fill=(255, 255, 255))
    for i, ln in enumerate(lines):
        d.text((26, h - 84 + i * 24), ln, fill=(0, 0, 0))
    return im, r, (label, detail), (margin, why)


if __name__ == "__main__":
    os.environ["BASEBALL_TEST_RUN"] = "1"
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "reveal_view.png"
    phase = sys.argv[3] if len(sys.argv) > 3 else "batting"
    im, r, b, m = annotate(Image.open(src), phase)
    im.save(out)
    print(f"ours  : {r['ours']}")
    print(f"theirs: {r['theirs']}")
    print(f"banner: {b}")
    print(f"margin: {m}")
    print(f"-> {out}")
