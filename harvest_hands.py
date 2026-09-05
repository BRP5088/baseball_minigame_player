"""
Harvest distinct hand strips from screenshot_log/ for offline analysis of
the PaddleOCR digit-grouping problem (see LOCAL_VISION_EXPERIMENTS.md).

Detection is solved; what needs more data is the geometry of pairing a
card's power badge with its own shield badge. Two hands wasn't enough to
fit a rule without overfitting, so this pulls every distinct hand the
10Hz logger captured during real play.

Dedupes near-identical frames (at 10Hz the same hand appears dozens of
times) by comparing downscaled grayscale pixels, so what lands in the
output directory is roughly one sample per actually-different hand.
"""

import os
import sys

import numpy as np
from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-harvest")
from orchestrator import GAMEPLAY_REGIONS_FRAC

LOG_DIR = "screenshot_log"
# I6: the output directory name encodes the crop geometry. hand_samples/ holds
# 1020x298 crops from the OLD y0=0.770 region, and hand_labels*.json are keyed
# to those filenames. The current y0=0.716 produces 1020x367 — mixing the two
# silently mixes coordinate systems, and normalised y fractions differ by ~1.23
# between them, exactly the scale of the SHIELD_DY / pair-spacing constants.
_Y0 = GAMEPLAY_REGIONS_FRAC["hand"][1]
OUT_DIR = f"hand_samples_y{_Y0:.3f}".replace(".", "")
# Mean per-pixel difference below this on a 64x24 thumbnail = same hand.
# Tuned loose enough to collapse 10Hz duplicates, tight enough to keep a
# hand where a single card changed.
DUPE_THRESHOLD = 6.0


def hand_crop(img):
    w, h = img.size
    x0, y0, x1, y1 = GAMEPLAY_REGIONS_FRAC["hand"]
    return img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


def is_turn_screen(hand_img):
    """Cheap reject of non-turn frames (ban screen, result overlays, the
    world map): a real hand strip is busy with card art, while other
    screens leave this region either near-black or near-uniform."""
    arr = np.asarray(hand_img.convert("L"), dtype=float)
    return arr.std() > 35 and 25 < arr.mean() < 210


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(LOG_DIR) if f.endswith(".jpg"))
    print(f"scanning {len(files)} logged frames...")

    kept = []
    for i, fname in enumerate(files):
        try:
            img = Image.open(os.path.join(LOG_DIR, fname))
        except Exception:
            continue
        hand = hand_crop(img)
        if not is_turn_screen(hand):
            continue
        thumb = np.asarray(hand.convert("L").resize((64, 24)), dtype=float)
        if any(np.abs(thumb - k).mean() < DUPE_THRESHOLD for k in kept):
            continue
        kept.append(thumb)
        # M14: save PNG. These are the calibration images for OCR work; the
        # source is already JPEG, so re-encoding adds generation loss to the
        # exact pixels being measured.
        hand.save(os.path.join(OUT_DIR, f"hand_{os.path.splitext(fname)[0]}.png"))
        if len(kept) % 10 == 0:
            print(f"  {len(kept)} distinct hands so far (frame {i}/{len(files)})")

    print(f"done: {len(kept)} distinct hand samples -> {OUT_DIR}/")


if __name__ == "__main__":
    sys.exit(main())
