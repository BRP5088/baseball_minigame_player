"""Read a hand's POWER DIGITS locally, in about two milliseconds, with no model.

WHY THIS EXISTS. The hand is read by a paid vision call, about 2-4 s and $0.012 each, 57 of
them in one measured match. Every general reader tried as a local replacement failed on the
same thing -- the digits. Measured on the same 22 hands: Apple Vision found 2 of 8 digits
(49 ms), upscaling six-fold raised that to 3 and cost 480 ms, GOT-OCR-2.0 emitted
"2222222222" (8.2 s), PaddleOCR found none (33 s), and ArmorOCR read them well but took
9.9 s. They are all TEXT LINE recognisers and a lone digit in a circle offers them no line.

WHAT WORKS INSTEAD. The digit is a fixed game asset: one font, one size, black on a white
disc. So it is found by SHAPE and read by TEMPLATE.

  finding   a dark mark whose surrounding white runs at least ENCLOSED_MIN pixels in all
            four directions. Five other gates -- aspect ratio, ring whiteness, isotropy,
            width, height -- were each measured against both populations and ALL FIVE
            OVERLAP, so they only ever cost real digits. See circle_finder.py.
  reading   normalised cross-correlation against templates cut from archived frames.

MEASURED, 5,600 digits from 1,807 archived turn frames, leave-one-frame-out so no patch was
ever matched against a template from its own frame:

    accuracy            5600 / 5600, no confusions
    non-digits rejected 853 / 853 at MIN_SCORE, none admitted
    real digit scores   p01 0.996        non-digit scores   max 0.521
    speed               about 2 ms to find, 0.07 ms to read each

KNOWN GAPS, stated because they decide whether this may replace the paid call:
  * the templates cover 1, 2, 4, 5, 7, 8. The roster says a power circle can also show
    6 and 9, and a tactics bonus can show 3. Those three have no template yet, so this
    reader ABSTAINS on them rather than guessing -- which is why read_hand returns None
    for a digit it cannot match, and why the caller must treat None as "ask the API".
  * the shield digit is white on a DARK shield, the exact inverse of this detector's
    target. It is not read here at all.
  * a tactic and a player card are told apart by the BANNER, not the circle, and no
    banner is read here.
"""
import json
import os

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(_HERE, "digit_templates.npz")

# MEASURED: real digits correlate 0.996 or better against a template of the same digit;
# the card elements the finder still emits top out at 0.521. Anything in between is
# nothing this reader has seen, so it abstains.
MIN_SCORE = 0.80
SIDE = 24

_cache = None


def _templates():
    global _cache
    if _cache is None:
        if not os.path.exists(TEMPLATES):
            raise FileNotFoundError(
                f"{TEMPLATES} is missing. Build it with "
                "agent_progress/bakeoff/build_templates.py")
        z = np.load(TEMPLATES)
        _cache = (z["vectors"], [str(s) for s in z["digits"]])
    return _cache


def _vector(img, box):
    p = img.crop(box).convert("L").resize((SIDE, SIDE), Image.LANCZOS)
    a = np.asarray(p, dtype=np.float32).ravel()
    a = a - a.mean()
    n = np.linalg.norm(a)
    return None if n < 1e-6 else a / n


def read_digit(img, circle):
    """(digit, score) for one located circle, or (None, score) when nothing matches."""
    cx, cy, r = circle[0], circle[1], circle[2]
    rr = int(r * 1.05)
    v = _vector(img, (max(0, cx - rr), max(0, cy - rr),
                      min(img.width, cx + rr), min(img.height, cy + rr)))
    if v is None:
        return None, 0.0
    vecs, digits = _templates()
    scores = vecs @ v
    k = int(scores.argmax())
    best = float(scores[k])
    return (digits[k] if best >= MIN_SCORE else None), best


def read_hand(img):
    """Every power digit in a hand strip, left to right.

    Returns a list of {"x", "digit", "score"}. `digit` is None where the mark did not
    match any template -- an unknown digit or a card element -- and the caller must treat
    that as "not read", never as "absent".
    """
    from circle_finder import find_circles           # local import: numpy + scipy only
    out = []
    for c in find_circles(img):
        d, s = read_digit(img, c)
        out.append({"x": c[0], "digit": d, "score": round(s, 3)})
    return out
