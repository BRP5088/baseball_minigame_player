"""Recover a bearing timeline from a recorded demo, fast.

OCR'ing every frame is not viable: a bearing read costs ~4s, so 652 frames is
45 minutes. But consecutive frames are 0.125s apart, and turning simply SLIDES
the compass bar sideways — the same pattern of ticks and letters, translated.
That shift is a cross-correlation, which costs milliseconds, and the scale
(px per 90 degrees) is already known from the bar's letter spacing.

So: OCR a few anchor frames for absolute truth, correlate everything in
between for the shape, and re-anchor periodically so integration drift cannot
accumulate. Where the two disagree, the anchor wins.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-decode")


def bar_strip(img, compass):
    bar = compass.find_bar(img)
    if bar is None:
        return None
    y, x0, x1 = bar
    h = img.size[1]
    band = max(10, int(h * 0.016))
    a = np.asarray(img.convert("L").crop((0, y - band, img.size[0], y + band)),
                   dtype=float)
    return a.mean(axis=0)          # collapse to a 1-D profile along x


def shift_between(p0, p1, span=160):
    """Horizontal shift of p1 relative to p0, in pixels."""
    best, bestv = 0, None
    n = len(p0)
    for s in range(-span, span + 1):
        a = p0[span:n - span]
        b = p1[span + s:n - span + s]
        m = min(len(a), len(b))
        if m < 50:
            continue
        v = float(np.abs(a[:m] - b[:m]).mean())
        if bestv is None or v < bestv:
            bestv, best = v, s
    return best, bestv


def decode(folder, anchor_every=60):
    import compass
    files = sorted(glob.glob(os.path.join(folder, "f_*.jpg")))
    out = []
    prev_profile = None
    bearing = None
    pitch = 295.0
    for i, f in enumerate(files):
        t = float(os.path.basename(f)[2:-4])
        img = Image.open(f).convert("RGB")
        prof = bar_strip(img, compass)
        if prof is None:
            out.append((t, None, "no-bar"))
            prev_profile = None
            continue
        if bearing is None or i % anchor_every == 0:
            b = compass.read_bearing(img)
            if b is not None:
                bearing = b
                out.append((t, bearing, "ocr"))
                prev_profile = prof
                continue
        if prev_profile is not None and bearing is not None:
            px, _ = shift_between(prev_profile, prof)
            # bar slides LEFT as heading increases
            bearing = (bearing - px / pitch * 90.0) % 360.0
            out.append((t, bearing, "corr"))
        else:
            out.append((t, bearing, "hold"))
        prev_profile = prof
    return out


if __name__ == "__main__":
    rows = decode(sys.argv[1])
    for t, b, how in rows:
        print(f"{t:7.2f}\t{'' if b is None else round(b, 1)}\t{how}")
