"""Stitch a 360-degree view of where the character is standing.

    python3 panorama.py <name>     sweep in place and write places/<name>/pano.jpg

WHY THIS CAN BE DONE WITHOUT FEATURE MATCHING
---------------------------------------------
Normal panorama stitching has to work out how far the camera turned between
shots. Here that is already known to a fraction of a degree: the compass is
read from the frame itself, and go.py measured the horizontal field of view at
102 degrees across a full circle recording. Knowing both, each capture can be
placed at its true angular position directly.

So this takes a narrow SLIT from the middle of each frame and lays the slits
side by side on a cylinder. Slits rather than whole frames because the centre
of the frame is the least distorted part, and because overlapping whole frames
would need blending to avoid seams that are not really there.

THE HUD IS CROPPED, not masked. The compass bar and the quest list are drawn in
screen space, so they do not turn with the camera — left in, they would smear
across the panorama as a repeating band that belongs to no direction. The
quest list is avoided for free by taking a CENTRE slit; the top bar is cut.

WHAT IT IS FOR. Two things: a picture a person can look at and name, and a
wider fingerprint of a place than any single frame provides. It is not a
floorplan — it says what is visible in every direction from one spot, not
where the walls are.
"""

import os
import sys
import time

import numpy as np
from PIL import Image

FOV_DEGREES = 102.0        # measured in go.py from a full-circle recording
SWEEP_STEPS = 12           # 30 degrees apart; each slit is 30 degrees wide
TOP_CROP = 0.12            # compass bar
BOTTOM_CROP = 0.04         # drop shadow / letterboxing
PANO_WIDTH = 3600          # 10 px per degree


def _slit(img, degrees):
    """The centre `degrees` of a frame, HUD-free."""
    w, h = img.size
    slit_w = max(1, int(round(w * degrees / FOV_DEGREES)))
    x0 = (w - slit_w) // 2
    y0, y1 = int(h * TOP_CROP), int(h * (1.0 - BOTTOM_CROP))
    return img.crop((x0, y0, x0 + slit_w, y1))


def stitch(shots, width=PANO_WIDTH):
    """shots: [(heading_deg, PIL.Image)] -> one cylindrical panorama.

    Placed by MEASURED heading, so an uneven sweep still lands correctly and a
    turn that overshot does not shear the result.
    """
    shots = [(h % 360.0, im) for h, im in shots if h is not None]
    if not shots:
        return None
    shots.sort(key=lambda s: s[0])
    n = len(shots)
    sample = _slit(shots[0][1], 360.0 / n)
    canvas = Image.new("RGB", (width, sample.height), "black")

    # EACH SLIT TAKES ITS OWN ANGULAR SHARE, from the midpoint to the previous
    # heading to the midpoint to the next — a Voronoi partition of the circle.
    #
    # Uniform 360/n slits assume the sweep turned evenly, and it never does:
    # turn_to lands within about half a degree, and any jitter beyond that
    # leaves stripes of canvas that no slit reaches. Measured on a synthetic
    # sweep with a few degrees of overshoot: 420 of 3600 columns uncovered,
    # 12% of the view simply missing. Sharing by measured heading tiles exactly
    # whatever the sweep actually did.
    for i, (heading, im) in enumerate(shots):
        prev_h = shots[i - 1][0]
        next_h = shots[(i + 1) % n][0]
        back = ((heading - prev_h) % 360.0) / 2.0
        fwd = ((next_h - heading) % 360.0) / 2.0
        if n == 1:
            back = fwd = 180.0
        degrees = back + fwd
        s = _slit(im, degrees).resize(
            (max(1, int(round(width * degrees / 360.0))), sample.height))
        # Left edge of this slit's share, in canvas pixels.
        x = int(round(width * (((heading - back) % 360.0) / 360.0)))
        canvas.paste(s, (x, 0))
        if x + s.width > width:                   # wrap across the seam
            canvas.paste(s, (x - width, 0))
    return canvas


def sweep(steps=SWEEP_STEPS, log=print, settle=0.45):
    """Turn a full circle in place, returning [(heading, frame)].

    Heading is READ after each turn rather than assumed, because turn_to lands
    within about half a degree but "about" is what smears a panorama.
    """
    import compass
    import walk_steps as ws

    start = compass.read_bearing(compass.fast_capture())
    if start is None:
        raise RuntimeError("no compass reading — not in the world")
    shots = []
    for i in range(steps):
        target = (start + i * (360.0 / steps)) % 360
        ws.turn_to(target, log=lambda m: None)
        time.sleep(settle)
        img = compass.fast_capture()
        h = compass.read_bearing(img)
        if h is None:
            log(f"  step {i}: no compass reading, skipping this slit")
            continue
        shots.append((h, img))
        log(f"  step {i:2d}: wanted {target:6.1f}  got {h:6.1f}")
    ws.turn_to(start, log=lambda m: None)
    return shots


def main(name):
    shots = sweep()
    pano = stitch(shots)
    if pano is None:
        print("nothing captured")
        return 1
    d = os.path.join("places", name)
    os.makedirs(d, exist_ok=True)
    # The individual frames are worth keeping: they are labelled views of this
    # place from every angle, which is exactly what places.identify() wants.
    for i, (h, im) in enumerate(shots):
        im.convert("RGB").save(os.path.join(d, f"sweep{i:02d}_{int(h):03d}.jpg"),
                               quality=88)
    p = os.path.join(d, "pano.jpg")
    pano.save(p, quality=90)
    print(f"wrote {p}  ({len(shots)} slits)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "unnamed"))
