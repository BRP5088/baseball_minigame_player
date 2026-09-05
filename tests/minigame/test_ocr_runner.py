"""Self-check for ocr_runner_card() against real occupied-base crops —
no API call."""

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

from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import GAMEPLAY_REGIONS_FRAC, ocr_runner_card

SRC_DIR = "Photos to train on"
CASES = [
    # (filename pattern, region, expected name)
    ("9.49", "first_base", "Rube Sharp"),
    ("9.49", "second_base", "Brian Coker"),
    ("9.46", "first_base", "Brian Coker"),
]

for pattern, region, expected in CASES:
    name = next(f for f in os.listdir(SRC_DIR) if pattern in f)
    img = Image.open(os.path.join(SRC_DIR, name))
    w, h = img.size
    x0, y0, x1, y1 = GAMEPLAY_REGIONS_FRAC[region]
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    card = ocr_runner_card(crop)
    got = card.name if card else None
    assert got == expected, f"{name} {region}: expected {expected!r}, got {got!r}"
    print(f"OK: {pattern} {region} -> {got} (power={card.power}, secondary={card.secondary})")

# empty-base sanity check: third_base is bare-coin in this photo, should be None
name = next(f for f in os.listdir(SRC_DIR) if "9.49" in f)
img = Image.open(os.path.join(SRC_DIR, name))
w, h = img.size
x0, y0, x1, y1 = GAMEPLAY_REGIONS_FRAC["third_base"]
crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
card = ocr_runner_card(crop)
assert card is None, f"empty third_base should read as None, got {card}"
print("OK: empty third_base (bare coin) correctly read as no runner")
