"""
Local hand-card stat reading via PaddleOCR.

WHY PADDLEOCR AND NOT THE MAIN ENV'S TESSERACT/EASYOCR
------------------------------------------------------
Hand cards are the one surface where the "read the name, look the stats
up in KNOWN_BAN_ROSTER" trick doesn't work: the game cuts hand cards off
at the screen edge, so they show only the role banner and the two stat
badges — never a name. That forces actual digit recognition on a bold,
hand-inked cartoon font, on cards that are fanned (overlapping,
individually rotated ~±8°, edge cards shifting position AND scale
between frames).

Measured on real captures (see LOCAL_VISION_EXPERIMENTS.md):
  - tesseract:  0 correct badge digits, both polarities, 7 thresholds
                x 5 psm modes. Font defeats it entirely.
  - EasyOCR:    excellent when it fires (0.99+), but its DETECTOR is
                brittle — same image reads perfectly at 3x upscale and
                returns nothing at 2x or 4x. 2-3/5 on a real hand.
  - templates:  Hough-circle + MAD matching hit 75%, and a confidence
                threshold looked clean until messier glyph extractions
                started matching WRONG digits at score 1.000. Unusable
                for a value that drives card selection.
  - PaddleOCR:  5/5 power digits on one real hand, 8/8 power+shield on
                another, all at 0.99-1.00 confidence.

PaddleOCR is explicitly built for stylized/rotated text in the wild,
which is exactly this problem, and it needs NO per-card de-rotation or
badge isolation — it localizes the digits itself from the whole hand
strip.

RUNS IN A SEPARATE VENV (subprocess, not import)
------------------------------------------------
paddlepaddle has no wheels for the main environment's Python 3.14, so it
lives in a Python 3.11 venv and is called via subprocess. That also
keeps a heavy ML dependency out of the main orchestrator process.
Set PADDLE_VENV_PYTHON to point at that venv's interpreter.

STATUS: wired in as an AUDIT-ONLY cross-read (log_local_read_comparison in
orchestrator.py, enabled with run(..., compare_local_reads=True)). Its
output is printed and compared against vision, never acted on. Vision
remains authoritative for every gameplay decision.
"""

import json
import os
import subprocess

PADDLE_VENV_PYTHON = os.environ.get(
    "PADDLE_VENV_PYTHON",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "paddle_venv", "bin", "python"),
)


class PaddleVenvMissing(RuntimeError):
    """Raised once, loudly, rather than failing silently every turn."""


def check_paddle_venv():
    """Verify the PaddleOCR interpreter exists. Call once at startup — a
    missing venv otherwise surfaces as a swallowed per-turn exception that
    looks like an OCR failure rather than a setup problem."""
    if not os.path.isfile(PADDLE_VENV_PYTHON):
        raise PaddleVenvMissing(
            f"PaddleOCR interpreter not found at {PADDLE_VENV_PYTHON}.\n"
            "paddlepaddle has no wheels for this project's main Python, so it "
            "lives in a separate venv. Recreate it with:\n"
            "  python3.11 -m venv paddle_venv && "
            "./paddle_venv/bin/pip install paddlepaddle paddleocr\n"
            "or point PADDLE_VENV_PYTHON at an interpreter that has paddleocr."
        )
    return True


# Digits are read at THREE scales and merged (1x, 2x, 4x). Different
# digits surface at different scales — measured on a real hand, 1x found
# 4/6/7/9, 2x additionally found the 5, and only 4x found the two shields.
# No single scale was complete.
_WORKER = r'''
import json, sys
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

img_path = sys.argv[1]
ocr = PaddleOCR(use_textline_orientation=False, lang="en")
img = Image.open(img_path).convert("RGB")
W_IMG, H_IMG = img.size

def detect(im, scale):
    big = im.resize((im.width*scale, im.height*scale)) if scale > 1 else im
    W, H = big.size
    out = []
    for r in ocr.predict(np.array(big)):
        for box, t, s in zip(r["rec_polys"], r["rec_texts"], r["rec_scores"]):
            if t.isdigit() and len(t) == 1 and float(s) > 0.9:
                xs = [p[0] for p in box]; ys = [p[1] for p in box]
                out.append((sum(xs)/4/W, sum(ys)/4/H, t, float(s)))
    return out

hits = detect(img, 1) + detect(img, 2) + detect(img, 4)
# Dedupe the same physical digit found at both scales. The radius must
# stay TIGHT: badges from adjacent fanned cards can sit ~0.03 apart in x
# (one card's shield next to the neighbour's power badge), so a generous
# radius silently swallows a real, distinct digit. Same-digit detections
# across scales land within ~0.01, so this is comfortably enough.
merged = []
for x, y, t, s in sorted(hits, key=lambda h: -h[3]):
    if not any(abs(x-mx) < 0.015 and abs(y-my) < 0.05 for mx, my, _, _ in merged):
        merged.append((x, y, t, s))

# PASS 2 — targeted shield recovery.
# The global pass's dominant error is a MISSED shield, which silently
# reads as secondary=0 and is indistinguishable from a card that has no
# shield. For every power badge with nothing found below it, look
# directly at the expected shield position instead of relying on the
# detector to volunteer it.
#
# Patch size is critical and NON-MONOTONIC (measured, 50 shields):
#   +-0.050/0.075 (tight)  -> 20% correct, 38 missed  (too little context;
#                             the detector fails to localize at all)
#   +-0.090/0.130 (medium) -> 76% correct, 10 missed  <-- best
#   +-0.140/0.200 (wide)   -> 54% correct, 8 WRONG    (pulls in neighbours)
# Combined with the global pass this took cards from 95% -> 98% correct
# and exact hands from 10/13 -> 12/13.
SHIELD_DY = 0.175          # measured power->shield offset, tall-crop fractions
SHIELD_PAD_X, SHIELD_PAD_Y = 0.090, 0.130

# Snapshot before the loop: the body appends recovered shields to `merged`,
# and testing "already found" against the live list would let a shield
# recovered for one card suppress recovery for a later card whose power
# badge happens to sit above it. Compare against what the GLOBAL pass found.
_global = list(merged)
for x, y, t, s in _global:
    if not 4 <= int(t) <= 9:
        continue                      # only player power badges carry shields
    if any(abs(mx-x) < 0.06 and 0.10 < (my-y) < 0.30 for mx, my, _, _ in _global):
        continue                      # global pass already found this shield
    cx, cy = x, y + SHIELD_DY
    box = (max(0, int(W_IMG*(cx-SHIELD_PAD_X))), max(0, int(H_IMG*(cy-SHIELD_PAD_Y))),
           min(W_IMG, int(W_IMG*(cx+SHIELD_PAD_X))), min(H_IMG, int(H_IMG*(cy+SHIELD_PAD_Y))))
    if box[2] <= box[0] or box[3] <= box[1]:
        continue
    patch = img.crop(box)
    best = None
    for scale in (4, 6):
        big = patch.resize((patch.width*scale, patch.height*scale))
        for r in ocr.predict(np.array(big)):
            for tt, ss in zip(r["rec_texts"], r["rec_scores"]):
                if len(tt) == 1 and tt.isdigit() and 0 <= int(tt) <= 3:
                    if best is None or float(ss) > best[1]:
                        best = (tt, float(ss))
    if best:
        merged.append((cx, cy, best[0], best[1]))
merged.sort()
print(json.dumps([{"x": x, "y": y, "digit": t, "conf": s} for x, y, t, s in merged]))
'''


def read_hand_digits(hand_crop_path: str) -> list:
    """Returns [{"x", "y", "digit", "conf"}, ...] for every confident
    single digit found in the hand strip, sorted left to right. x/y are
    fractions of the strip's own dimensions."""
    result = subprocess.run(
        [PADDLE_VENV_PYTHON, "-c", _WORKER, hand_crop_path],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PaddleOCR worker exited {result.returncode}: {result.stderr[-500:]}"
        )
    for line in reversed(result.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("["):
            return json.loads(line)
    raise RuntimeError(f"PaddleOCR worker produced no result: {result.stderr[-500:]}")


# Observed value bounds, confirmed across two fully independent sources:
#   - KNOWN_BAN_ROSTER: 33 cards read off the ban screen
#   - 1,126 player cards hand-labelled from gameplay by four independent
#     readers (100% inter-rater agreement, see LOCAL_VISION_EXPERIMENTS.md §18)
# 1,159 observations, none outside these ranges.
#
# These are useful as a cheap, independent correctness check. A "secondary"
# outside 0-3 in particular is a strong tell that a digit was mis-paired —
# it catches the known false pair from `live_hand` (power 6 + "secondary" 5)
# without relying on the Δy geometry at all.
MIN_POWER, MAX_POWER = 4, 9
MIN_SECONDARY, MAX_SECONDARY = 0, 3


# Tactics bonuses (1-3) and player powers (4-9) are DISJOINT — measured
# across 299 tactics cards and 1,126 player cards. So the top badge digit
# alone identifies the card type; no icon detection needed.
MIN_TACTICS_BONUS, MAX_TACTICS_BONUS = 1, 3


def validate_card(power: int, secondary: int) -> bool:
    """True if this reads as a legal card — either a player card
    (power 4-9, secondary 0-3) or a tactics card (bonus 1-3, no
    secondary). Anything else means a mis-pairing or a digit lifted from
    the card artwork."""
    if MIN_POWER <= power <= MAX_POWER:
        return MIN_SECONDARY <= secondary <= MAX_SECONDARY
    if MIN_TACTICS_BONUS <= power <= MAX_TACTICS_BONUS:
        return secondary == 0          # tactics cards carry no shield
    return False


def group_into_cards(digits: list, x_tolerance: float = 0.06) -> list:
    """Group detected digits into per-card (power, secondary) pairs.

    Each card shows its power badge above its own shield badge, both near
    the card's top-right, with the shield directly below and slightly
    right. Cluster left-to-right by x, then within a column the upper
    digit is power and the lower is secondary. A column with one digit
    means that card has no shield — secondary 0, which is normal (~29% of
    player cards).

    NOTE this clusters by x and takes upper=power / lower=secondary; it does
    NOT apply a Δy band. (§14 designed one against the older, shorter crop —
    Δy 0.204-0.253 there — but it was never implemented here, and those
    figures do not transfer: the same physical spacing is ~0.169-0.191 in
    the current taller crop. See §23.)

    Each returned card carries a `valid` flag from validate_card(). An
    invalid entry usually means a mis-pairing or a false-positive digit
    picked up from the card ARTWORK, which is genuinely adversarial here:
    painted scoreboard digits run down the right edge inside some card
    frames (exactly where a shield sits), and mugshot height-charts add
    stray tick digits. Callers should treat `valid=False` as "fall back
    to vision", never as a value to act on.
    """
    if not digits:
        return []

    # Cluster left-to-right into columns. A card's shield sits slightly
    # RIGHT of and below its power badge (the badges are stacked with a
    # small rightward offset), so cluster against the column's most
    # recent member rather than its first.
    cols = []
    for d in sorted(digits, key=lambda d: d["x"]):
        if cols and abs(d["x"] - cols[-1][-1]["x"]) <= x_tolerance:
            cols[-1].append(d)
        else:
            cols.append([d])

    out = []
    for col in cols:
        col.sort(key=lambda d: d["y"])
        power = int(col[0]["digit"])
        secondary = int(col[1]["digit"]) if len(col) > 1 else 0
        out.append({
            "power": power,
            "secondary": secondary,
            "x": col[0]["x"],
            "min_conf": min(d["conf"] for d in col),
            "valid": validate_card(power, secondary),
        })
    return out
