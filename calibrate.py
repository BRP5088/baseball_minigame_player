"""Draw every fractional region onto a screenshot, so a wrong one is VISIBLE.

WHY THIS EXISTS
---------------
The region constants in orchestrator are fractions of the whole capture,
hand-calibrated on a 1728x1117 Mac (aspect 1.547). The ROG Ally is 1920x1080
(aspect 1.778), and preflight blocks that difference — correctly. Measured on
the Mac, a mere 110px horizontal displacement silently FLIPS a ban-grid cell:
the automation bans a different card and raises nothing.

So the regions have to be re-derived on the Ally, and the first thing anyone
needs is to SEE where the current ones land. Guessing which of 41 constants
moved, from a run that just misbehaves, is the slow way.

    python3 calibrate.py shot.png            -> shot.calibrated.png
    python3 calibrate.py shot.png --json     -> the numbers, for diffing

Overlay only. It changes nothing and derives nothing: a tool that silently
"fixed" the constants would be indistinguishable from one that broke them.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-calibrate")


def regions():
    """Every fractional box as (label, x0, y0, x1, y1), all in 0..1.

    Read from orchestrator at call time rather than copied, so this cannot
    drift away from the constants it is supposed to be checking.
    """
    import orchestrator as o
    out = []
    for label, box in o.GAMEPLAY_REGIONS_FRAC.items():
        out.append((label, *box))
    for i, (x0, x1) in enumerate(o.BAN_GRID_COL_X_FRAC):
        for j, (y0, y1) in enumerate(o.BAN_GRID_ROW_Y_FRAC):
            out.append((f"ban[{j}][{i}]", x0, y0, x1, y1))
    out.append(("ban_counter", *o.BAN_COUNTER_BOX_FRAC))
    out.append(("ban_scrollbar", *o.BAN_SCROLLBAR_BOX_FRAC))
    return out


def annotate(img):
    """Return a copy with every region outlined and labelled."""
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    for label, x0, y0, x1, y1 in regions():
        # ban cells in one colour, everything else in another, so a shifted
        # grid reads as a group rather than as ten unrelated boxes
        colour = (255, 90, 90) if label.startswith("ban[") else (90, 220, 255)
        px = (int(w * x0), int(h * y0), int(w * x1), int(h * y1))
        d.rectangle(px, outline=colour, width=3)
        d.text((px[0] + 5, px[1] + 4), label, fill=colour)
    aspect = w / h
    d.text((10, 10), f"{w}x{h}  aspect {aspect:.3f}", fill=(255, 255, 0))
    return out


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = argv[0]
    if "--json" in argv:
        print(json.dumps([dict(zip(("label", "x0", "y0", "x1", "y1"), r))
                          for r in regions()], indent=1))
        return 0
    img = Image.open(path)
    dest = os.path.splitext(path)[0] + ".calibrated.png"
    annotate(img).save(dest)
    w, h = img.size
    print(f"  {os.path.basename(path)}  {w}x{h}  aspect {w / h:.3f}")
    print(f"  {len(regions())} regions drawn -> {dest}")
    if abs(w / h - 1728 / 1117) > 0.15:
        print(f"  NOTE: this aspect is outside what the constants were "
              f"calibrated for (1.547). Expect the boxes to be wrong — that is "
              f"what this image is for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
