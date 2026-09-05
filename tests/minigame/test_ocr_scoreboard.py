"""Self-check for ocr_scoreboard() against real screenshots — no API call."""

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
from orchestrator import GAMEPLAY_REGIONS_FRAC, ocr_scoreboard

SRC_DIR = "Photos to train on"
CASES = [
    ("9.32", {"your": [0, 0, 0], "opponent": [0, 0, 0]}),
    ("9.49", {"your": [2, 0, 2], "opponent": [0, 1, 1]}),
    ("9.46", {"your": [2, 0, 2], "opponent": [0, 1, 1]}),
]

for pattern, expected in CASES:
    name = next(f for f in os.listdir(SRC_DIR) if pattern in f)
    img = Image.open(os.path.join(SRC_DIR, name))
    w, h = img.size
    x0, y0, x1, y1 = GAMEPLAY_REGIONS_FRAC["scoreboard"]
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    got = ocr_scoreboard(crop)
    assert got == expected, f"{name}: expected {expected}, got {got}"

print("OK: ocr_scoreboard matched all 6 numbers on 3 real screenshots")
