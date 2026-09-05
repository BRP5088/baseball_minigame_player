"""Align two views using STRUCTURE ONLY — walls and doorframes, not people.

WHY
---
Matching whole frames fails in this game because the world moves on its own.
Wanda walks, the bar patrons shift, pedestrians cross the windows. When the
recorded frame has an NPC somewhere and the live frame has them somewhere else,
the best whole-frame match is "line the NPC up", not "point the camera where
the recording pointed it". The correlation score keeps improving while the
camera steers somewhere the recording never looked — which is why a divergence
guard does not catch it, and why a replay confidently walks into the wrong
room.

WHAT THIS DOES INSTEAD
----------------------
Two changes, both aimed at ignoring anything that can walk:

1. MATCH ON EDGES. Architecture is straight lines and hard corners; characters
   are soft rounded blobs that mostly vanish under a gradient. Correlating
   gradient magnitude weights the room and discards the actors.

2. MASK WHERE PEOPLE ARE. The player character occupies the bottom centre of
   frame in this third-person view, and NPCs are approached head-on, so they
   land centre-frame too. Those regions are zeroed before correlating.

The remaining signal is walls, door surrounds, window frames and furniture —
things that are where the recording left them.
"""

import numpy as np
from PIL import Image

HUD_LEFT = 0.26           # quest log
HUD_TOP = 0.11            # compass strip
THUMB = (160, 90)

# Zeroed before correlating, as fractions of the cropped view.
PLAYER_BOX = (0.30, 0.55, 0.75, 1.00)    # third-person character, bottom centre
NPC_BOX = (0.35, 0.25, 0.70, 0.75)       # where an approached NPC appears

MAX_SHIFT = 40
SHIFT_STEP = 2
VERT_RANGE = 12
VERT_STEP = 3


def _edges(img):
    """Gradient magnitude of the HUD-free view, people masked out."""
    g = img.convert("L")
    w, h = g.size
    g = g.crop((int(w * HUD_LEFT), int(h * HUD_TOP), w, h))
    a = np.asarray(g.resize(THUMB, Image.BILINEAR), dtype=float)

    # gradient magnitude: keeps hard architectural edges, drops soft shading
    gy, gx = np.gradient(a)
    e = np.hypot(gx, gy)

    th, tw = e.shape
    for box in (PLAYER_BOX, NPC_BOX):
        x0, y0, x1, y1 = box
        e[int(th * y0):int(th * y1), int(tw * x0):int(tw * x1)] = 0.0

    e -= e.mean()
    n = np.linalg.norm(e)
    return e / n if n > 1e-6 else e


def offset(live, want):
    """(dx, dy, score) aligning `live` onto `want`, using structure only."""
    a, b = _edges(live), _edges(want)
    best, bx, by = -2.0, 0, 0
    for dy in range(-VERT_RANGE, VERT_RANGE + 1, VERT_STEP):
        rb = np.roll(b, dy, axis=0)
        for dx in range(-MAX_SHIFT, MAX_SHIFT + 1, SHIFT_STEP):
            v = float((a * np.roll(rb, dx, axis=1)).sum())
            if v > best:
                best, bx, by = v, dx, dy
    return bx, by, best


def confident(score, min_score=0.25):
    """Is this match trustworthy enough to steer by?

    A low score means the views have little structure in common — a dark
    corridor, or the camera pointing somewhere entirely different. Steering on
    that is worse than not steering, because it is confident noise.
    """
    return score >= min_score
