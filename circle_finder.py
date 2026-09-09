"""Find the POWER CIRCLES on a hand strip, without OCR.

WHY NOT OCR. Three general readers were measured on these same 22 hands and all three read
the banners well and the digits badly: Apple Vision found 2 of 8 digits, upscaling six-fold
raised it to 3 and cost eight times the wall clock, PaddleOCR found none in 33 s, and a
document transcriber emitted "2222222222". The reason is structural: every one of them is a
TEXT LINE recogniser, and each digit here is a lone glyph inside a circle with no line of
text around it. There is nothing for a line detector to lock onto.

WHAT THE TARGET ACTUALLY IS, and why it is easier than OCR: a filled WHITE DISC with a dark
digit printed on it. That shape has a property no mouse face or glove in this cartoon has --
the white region is an ANNULUS. The digit punches a hole in it. So the test is not "is this
white" (43 false circles for 5 cards, measured) and not a ring sampled with square boxes
(their corners land on dark card and dilute the ring, which lost the real discs). It is:
a white connected component, roughly as wide as it is tall, of about the right size, WITH A
HOLE IN IT.

This module ONLY LOCATES the circles. Reading the digit inside one is a separate step, so
the locating can be checked by eye before anything is built on top of it.

    .venv/bin/python -B agent_progress/bakeoff/circle_finder.py [--hands 15,16]

Writes agent_progress/bakeoff/circles/<hand>_marked.png and circles.json.
"""
import argparse
import json
import os
import time

import numpy as np
import scipy.ndimage as ndi
from PIL import Image, ImageDraw

BO = "agent_progress/bakeoff"
OUT = f"{BO}/circles"

# MEASURED FROM THE CROPS: on the 979x307 hand strips the power discs run about 34-40 px
# across. The band below covers them with margin while excluding the Ram Special medallion
# behind the fan (about 150 px) and speckle.
# HUNT THE DIGIT, NOT THE DISC. Two attempts failed on the same rock: a disc that touches
# the bright card edge behind it merges into one white blob, so any test on the disc's own
# shape loses it. Eroding to break the bridge ate the disc's thin white ring instead and
# took the count from 44 to 7. The digit has no such problem -- it is a dark mark entirely
# surrounded by white, and it touches nothing, whether or not its disc touches an edge.
#
# So: find dark blobs of digit size that do not reach the image border, and keep the ones
# ringed by white. Measured on the 979x307 strips, a power digit's ink is about 10-22 px
# wide and 14-28 px tall.
DARK = 110               # the digit's ink; the disc around it reads 200+
WHITE = 175
DIGIT_W = (6, 26)
DIGIT_H = (10, 32)
# THE ONLY GATE, measured: white must run at least this far from every edge of the ink.
# Real digits reach 6-13 in all four directions; name plates and card art collapse to 0-2
# on at least one side (measure_gates.py).
# 3, was 5. The gap measured between the two populations runs from junk's p95 of 2 to a
# digit's p05 of 6, and 5 sat at the very top of it. Pitching hands overlap more, so the
# card in front clips a disc's white margin to 3 px on one side and real digits were being
# thrown away: at 5 the finder returned 59 circles and 2 of 15 hands with an exact card
# count; at 3 it returns 65 and 4 of 15, with no change in the number of digits read wrong.
# Below 3 it starts admitting junk: at 2 the abstentions jump from 18 to 23.
ENCLOSED_MIN = 3
REACH_MAX = 40           # how far a ray looks before giving up, in pixels
# START THE RAYS CLEAR OF THE INK'S ANTI-ALIASED EDGE. Flush against it a single grey
# pixel stops the ray, and a real digit reads [8, 0, 13, 0].
HALO = 2


def find_circles(img):
    """Every white disc that has a hole in it, left to right, as (cx, cy, r, fill, holes)."""
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    H, W = g.shape
    dark = g <= DARK
    lab, n = ndi.label(dark)
    if not n:
        return []
    white = g >= WHITE
    out = []
    for sl, i in zip(ndi.find_objects(lab), range(1, n + 1)):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if not (DIGIT_W[0] <= w <= DIGIT_W[1] and DIGIT_H[0] <= h <= DIGIT_H[1]):
            continue
        if ys.start == 0 or xs.start == 0 or ys.stop >= H or xs.stop >= W:
            continue                      # touches the border: not an enclosed mark
        # NO ASPECT GATE. It was measured against both populations (measure_gates.py) and
        # overlaps: real digits 1.00-1.90, everything else 0.54-4.96. It also made the
        # name-plate problem worse, by splitting "GAIN" into the digit-shaped "IN".
        cy = (ys.start + ys.stop) // 2
        cx = (xs.start + xs.stop) // 2
        # THE ONE GATE THAT SURVIVED MEASUREMENT: is this mark ENCLOSED BY WHITE?
        # Cast a ray from each edge of the ink and see how far the white runs. A digit sits
        # in a disc, so every direction reaches 6 or more; a name plate, a card ornament or
        # dark card art collapses to 0-2 on at least one side.
        #
        # Ring whiteness, isotropy, aspect ratio, width and height were all measured against
        # the same two populations (measure_gates.py, 64 enclosed marks against 504 others)
        # and ALL FIVE OVERLAP -- aspect 1.00-1.90 against 0.54-4.96, ring 0.75-0.88 against
        # 0.00-0.80, isotropy 1.14-2.12 against 0.00-24.0. A gate whose populations overlap
        # cannot separate them; it only costs real digits, which is what four rounds of
        # hand-tuning kept discovering the slow way. They are gone.
        #
        # The rays start HALO pixels clear of the ink, because flush against it a single
        # anti-aliased pixel stops the ray and a real digit reads [8, 0, 13, 0].
        reach = []
        for dy, dx, sy, sx in ((-1, 0, ys.start - HALO, cx), (1, 0, ys.stop + HALO, cx),
                               (0, -1, cy, xs.start - HALO), (0, 1, cy, xs.stop + HALO)):
            k, y, x = 0, sy, sx
            while k < REACH_MAX and 0 <= y < H and 0 <= x < W and white[y, x]:
                y += dy; x += dx; k += 1
            reach.append(k)
        if min(reach) < ENCLOSED_MIN:
            continue
        out.append((int(cx), int(cy), int(max(w, h) * 0.9), float(min(reach)), 1))

    # One per neighbourhood: a digit like 8 or 4 can label as several dark parts.
    out.sort(key=lambda c: -c[3])
    kept = []
    for c in out:
        if all((c[0] - k[0]) ** 2 + (c[1] - k[1]) ** 2 > (max(c[2], k[2]) * 1.4) ** 2 for k in kept):
            kept.append(c)
    kept.sort(key=lambda c: c[0])
    return kept


# THE CLI LIVES BEHIND A MAIN GUARD so this module can be imported for find_circles
# alone. Without it, argparse ran at import time and swallowed the caller's own
# arguments -- build_big_corpus.py could not accept a single flag.
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    AP = argparse.ArgumentParser()
    AP.add_argument("--hands", default="")
    A = AP.parse_args()

    hands = json.load(open(f"{BO}/corpus.json"))["hands"]
    if A.hands:
        want = {int(x) for x in A.hands.split(",")}
        hands = [h for h in hands if h["n"] in want]

    out = []
    for h in hands:
        img = Image.open(os.path.join(BO, h["hand_crop"])).convert("RGB")
        t = time.time()
        circles = find_circles(img)
        ms = (time.time() - t) * 1000
        expected = len(h["paid_api_answer"])
        d = ImageDraw.Draw(img)
        for i, (cx, cy, r, fill, holes) in enumerate(circles):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 0, 0), width=3)
            d.text((cx - 4, cy - r - 14), str(i), fill=(255, 0, 0))
        img.save(f"{OUT}/{h['n']:03d}_marked.png")
        out.append({"n": h["n"], "ms": round(ms, 1), "found": len(circles),
                    "cards_in_hand": expected, "circles": circles})
        print(f"hand {h['n']:03d}  {ms:6.1f}ms  {len(circles)} circles for {expected} cards", flush=True)
    json.dump(out, open(f"{BO}/circles.json", "w"), indent=1)
    if out:
        print(f"\nmedian {sorted(o['ms'] for o in out)[len(out) // 2]:.0f} ms per hand")
        print(f"marked images in {OUT} -- LOOK before trusting the counts")
