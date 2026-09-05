"""Confirm a route leg ended where it was supposed to, by looking at the scene.

WHY NOT OCR
-----------
The obvious idea is to read the world text — "BRIE SHOT", "LITTLE & BIG" — and
check for it. Tried on a real frame where the menu board is plainly legible to
a human: tesseract returned nothing from the board at 3x, 5x and 8x upscaling,
and what it DID return ("sklot", "Ave.") was the quest-log HUD bleeding into
the crop. The world text is small, hand-lettered and low contrast.

WHAT THIS DOES INSTEAD
----------------------
Compares a heavily downscaled version of the scene against a reference frame
captured when the leg was known good. Structure — a doorway, a bar counter, a
menu board — survives downscaling; exact pixels, NPC positions and flicker do
not, which is the point.

THE HUD IS MASKED OUT, but NOT for the reason that first seemed obvious.
Measured on real frames, masking it slightly WORSENS discrimination — the gap
between same-place and different-place goes from +0.39 to +0.33 — because the
quest log is semi-transparent and the compass moves with heading, so the HUD
does carry some scene information.

It is masked anyway because it carries information that goes STALE. The quest
log lists active jobs and rewrites itself as they complete, so a reference frame
captured today stops matching the same spot tomorrow for a reason that has
nothing to do with position. The small loss of discrimination buys references
that keep working. Every frame here comes from one session with one quest state,
so no measurement available today can see that effect — this is a judgement
about what changes over time, not a measured result.
"""

import numpy as np
from PIL import Image

HUD_LEFT_PX = 480          # quest log; rewrites itself as quests complete
HUD_TOP_PX = 110           # compass strip; changes with heading, not position
THUMB = (64, 36)

# Measured 2026-08-27 over real frames from this route:
#   same place, consecutive frames : 0.84 - 0.98   (min 0.84)
#   different places               : up to 0.55    (two dark frames correlating)
# 0.70 sits in the gap with room on both sides. Note the floor is set by DARK
# scenes: two unrelated dark rooms correlate at 0.55 simply for being dark, so
# do not lower this expecting to catch more.
MATCH_THRESHOLD = 0.70


def signature(img):
    """Small, HUD-free, contrast-normalised fingerprint of the scene."""
    w, h = img.size
    scene = img.convert("L").crop((int(w * HUD_LEFT_PX / 1920), int(h * HUD_TOP_PX / 1080), w, h))
    a = np.asarray(scene.resize(THUMB, Image.LANCZOS), dtype=float)
    a -= a.mean()
    n = np.linalg.norm(a)
    return a / n if n > 1e-6 else a


def similarity(img_a, img_b):
    """1.0 identical, 0 unrelated. Normalised correlation of the signatures."""
    return float((signature(img_a) * signature(img_b)).sum())


def matches(img, reference, threshold=MATCH_THRESHOLD):
    """(ok, score) — is `img` looking at the same place as `reference`?"""
    s = similarity(img, reference)
    return s >= threshold, s
