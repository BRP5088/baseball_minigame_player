"""
The PaddleOCR venv check. The hand reader it was built for is GONE.

WHY PADDLEOCR WAS CHOSEN -- KEPT AS THE MEASUREMENT, NOT AS A DESCRIPTION
-------------------------------------------------------------------------
The bake-off below is why the pipeline existed. It is past tense now: the
TEMPLATE reader won in the end (local_hand.read_hand, 5600/5600 at ~2 ms), and
the row below calling templates "unusable" is the judgement that aged worst --
it was measured on Hough-circle + MAD matching, not on the per-digit banks the
shipped reader uses. Keep the numbers, not the conclusion.

Hand cards were the one surface where the "read the name, look the stats
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

THE VENV IS STILL LIVE, AND NOT FOR THIS FILE: result_ocr.py spawns it to read
the WINNER/LOSER/DRAW banner (orchestrator.py -> result_ocr.start()). That is
why check_paddle_venv() below is still worth calling and why paddle_venv must
not be deleted.

STATUS: THE HAND-DIGIT PIPELINE IS GONE (deleted 2026-09-20). It had zero
callers from commit 211c6bf (2026-09-09), which replaced it with
local_hand.read_hand -- the template reader, 5600/5600 at ~2 ms against this
one's subprocess-per-call. This docstring claimed until today that it was
"wired in as an AUDIT-ONLY cross-read"; log_local_read_comparison calls
local_hand.read_hand and never called anything here.

WHAT REMAINS, and why the file is not deleted: check_paddle_venv(). THE VENV
IS LIVE -- result_ocr.py spawns paddle_venv/bin/python to read the
WINNER/LOSER/DRAW banner (orchestrator.py:4113 -> result_ocr.start()), so the
interpreter this verifies is a real dependency. Only the consumer changed.

The value bounds that lived here are preserved where they are still enforced,
in orchestrator's CARD_POWER_MIN/MAX: powers 4-9 and secondary 0-3 across
1,159 observations (KNOWN_BAN_ROSTER's 33 cards plus 1,126 hand-labelled
player cards), none outside those ranges; tactics bonuses 1-3 are disjoint
from player powers, so the top badge digit alone identifies the card type.
"""

import os

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


