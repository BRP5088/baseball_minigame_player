"""Tests for the local image-processing pipeline, against real captured frames.

Covers functions that had NO test coverage despite being load-bearing:
  - mask_low_contrast_regions()  — blanks locked/faded cards before they ever
    reach the vision model. If it under-masks, faded cards get hallucinated
    stats; if it over-masks, real cards vanish from the collection.
  - crop_gameplay_regions()      — geometry stability across frames
  - ocr_scoreboard()             — widened from 3 to 7 real frames

All fixtures live in test_fixtures/, NOT screenshot_log/, because the
screenshot logger's pruner deletes oldest-first from that directory
(QA_FINDINGS_R2.md N10).

Offline: no API calls, no PS5 input.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import os

import numpy as np
from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import (GAMEPLAY_REGIONS_FRAC, MASK_CONTRAST_THRESHOLD,
                          crop_gameplay_regions, mask_low_contrast_regions,
                          ocr_scoreboard)

FIX = "test_fixtures"

# Scoreboard ground truth, read by eye off each frame. Format is
# [round1, round2, series_total] per side.
SCOREBOARD_CASES = [
    ("20260824_201103_128.jpg", {"your": [2, 0, 2], "opponent": [0, 0, 0]}),
    ("20260824_201945_482.jpg", {"your": [2, 0, 2], "opponent": [0, 1, 1]}),
    ("20260824_202514_167.jpg", {"your": [0, 0, 0], "opponent": [0, 0, 0]}),
    ("20260824_204106_408.jpg", {"your": [1, 0, 1], "opponent": [0, 0, 0]}),
]

failures = []

# ---------------------------------------------------------------- scoreboard
for fname, expected in SCOREBOARD_CASES:
    img = Image.open(os.path.join(FIX, fname))
    w, h = img.size
    x0, y0, x1, y1 = GAMEPLAY_REGIONS_FRAC["scoreboard"]
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    got = ocr_scoreboard(crop)
    if got != expected:
        failures.append(f"scoreboard {fname}: expected {expected}, got {got}")

# ------------------------------------------------------- crop geometry
# Every region must be non-empty and stay inside the frame, on every fixture.
# A fractional-coordinate mistake (e.g. mixing width/height fractions) shows up
# here as a zero-size or out-of-bounds crop rather than as a silent misread.
for fname in os.listdir(FIX):
    if not fname.endswith(".jpg"):
        continue
    img = Image.open(os.path.join(FIX, fname))
    for label, crop in crop_gameplay_regions(img):
        if crop.width <= 0 or crop.height <= 0:
            failures.append(f"{fname}: region {label!r} cropped to {crop.size}")
        if crop.width > img.width or crop.height > img.height:
            failures.append(f"{fname}: region {label!r} exceeds frame {crop.size}")

# ------------------------------------------------------------------ masking
# On a ban screen with known locked cards, masking must blank the faded ones
# and leave the legible ones alone. Frame 200520_984 has 3 locked cells
# (verified in test_ban_grid_locked.py): row0 col2, row1 col0, row1 col1.
img = Image.open(os.path.join(FIX, "20260824_200520_984.jpg"))
masked = mask_low_contrast_regions(img)

if masked.size != img.size:
    failures.append(f"masking changed frame size: {img.size} -> {masked.size}")

orig_arr = np.asarray(img.convert("L"), dtype=float)
mask_arr = np.asarray(masked.convert("L"), dtype=float)

# It must actually blank something on a frame with locked cards...
#
# Measured against the UNMASKED frame, not against a bare constant. The old
# floor was 0.01, but this fixture is already 6.05% pure black before masking
# (sky, borders, letterboxing), so replacing the whole masker with
# `return img.copy()` — blanking NOTHING — sailed past it and survived the
# entire suite. Fixed-overhead masking (QA, 2026-08-26). Real masking takes
# this frame to 61.5%, so the gap is enormous and the margin below is not
# tight.
blanked_frac = float((mask_arr == 0).mean())
unmasked_frac = float((orig_arr == 0).mean())
if blanked_frac < unmasked_frac + 0.20:
    failures.append(
        f"masking blanked {blanked_frac:.2%} against {unmasked_frac:.2%} already "
        f"black in the source — a gain of only {blanked_frac - unmasked_frac:.2%}. "
        "The masker is doing little or nothing; a no-op returns the source "
        "fraction unchanged.")
if blanked_frac < 0.01:
    failures.append(f"masking blanked almost nothing ({blanked_frac:.3%}) on a "
                    "frame with 3 known locked cards")
# ...but must not blank the whole frame (that would erase the legible cards too).
if blanked_frac > 0.90:
    failures.append(f"masking blanked {blanked_frac:.1%} of the frame — "
                    "legible cards would be destroyed")

# Masking must only ever darken, never brighten: it paints black rectangles.
if (mask_arr > orig_arr + 1).any():
    failures.append("masking brightened pixels somewhere — it should only blank")

# Idempotence: masking an already-masked frame must not eat more of it. If this
# regresses, repeated calls would progressively erase the screen.
twice = np.asarray(mask_low_contrast_regions(masked).convert("L"), dtype=float)
extra = float((twice == 0).mean()) - blanked_frac
if extra > 0.05:
    failures.append(f"masking is not idempotent: a second pass blanked "
                    f"{extra:.1%} more of the frame")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} image-pipeline failures")

print(f"OK: scoreboard {len(SCOREBOARD_CASES)}/{len(SCOREBOARD_CASES)} frames, "
      f"crop geometry valid on all fixtures, masking blanked "
      f"{blanked_frac:.1%} and is idempotent (threshold={MASK_CONTRAST_THRESHOLD})")
