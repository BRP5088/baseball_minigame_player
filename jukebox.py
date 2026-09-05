"""Find a STATIC LANDMARK in a frame — the jukebox, or the dealer's table.

WHY A FIXED OBJECT MATTERS
--------------------------
Position feedback has been the blocker all along, and every candidate so far
turned out to move. Wanda Fuller looked like a checkpoint until she was found
at the arrival point despite appearing at t=17.95 in the recording — she walks.
The compass-strip markers looked world-fixed until a straight-line walk showed
their offsets constant to 0.0 degrees — they ride the camera.

The jukebox does not move (confirmed by the person who plays this), and it sits
immediately before the table. So the bearing to it is a genuine position signal:
when it is visible, where it appears on screen says which way the character has
drifted.

HOW IT IS MATCHED
-----------------
On GRADIENT MAGNITUDE rather than brightness, because the bar's lighting varies
a lot and edges do not. Normalised cross-correlation over a few scales, so the
match survives being nearer or further away than the template was taken from.
"""

import glob
import json
import os

import numpy as np
from PIL import Image
from scipy.signal import fftconvolve

TEMPLATE_DIR = "test_fixtures/jukebox"
WORK_WIDTH = 480           # frames are reduced to this before searching
# Wide range on purpose: the same object fills a small part of the frame from
# across the room and most of it when standing next to it. The dealer's table
# scored only 0.33 up close, against 0.47 on approach, purely because the
# largest scale was too small to cover it.
# DO NOT extend the low end below ~0.7. It was tried, on the reasoning that
# distant targets need small scales and that MIN_WINDOW_TEXTURE now makes small
# templates safe. It does not: with 0.5 permitted, a frame whose correct match
# is at y=0.596 instead matched at y=0.944 with a higher score, and a frame with
# no dealer in it at all scored 0.524. A template shrunk that far has too little
# structure left to be distinctive, whatever the texture of what it lands on.
#
# The right fix for distance is TEMPLATES CAPTURED AT DISTANCE, not shrinking
# close-up ones.
SCALES = (0.7, 0.85, 1.0, 1.2, 1.45, 1.75, 2.1)

# A match window with almost no texture must be REJECTED, not rewarded.
# Normalised cross-correlation divides by the window's own standard deviation,
# so a featureless wall divides by nearly nothing and scores arbitrarily high.
# Seen directly: boxes correctly on the dealer scored 0.40-0.43 while a box on a
# blank wall scored 0.598 and won, so every controller downstream steered at the
# wall. This is the fraction of the whole frame's texture a window must have
# before its score is believed.
MIN_WINDOW_TEXTURE = 0.35

# UNCALIBRATED, AND NO VALUE HERE CAN WORK. Measured 2026-09-04; pinned by
# tests/routing/test_jukebox_match_min.py.
#
# This line read "calibrated below; see tests/test_jukebox.py" until that date.
# THAT FILE HAS NEVER EXISTED, under any name, in any test directory — so the
# word "calibrated" was an assertion of evidence that was never taken. What
# follows is the measurement that should have been there.
#
# WHAT IT DECIDES TODAY: nothing. MATCH_MIN is the default `threshold=` of
# visible(), and visible() has NO CALLERS. Every module that imports jukebox
# (go, approach_table, go_to_landmark, run_anchored, aim_test, pitch_control)
# compares find()'s score against its own local constant instead.
#
# SCORED OVER 766 ARCHIVED FRAMES (demos/walk3_full, places/, route_frames/,
# overnight/failframes/, test_fixtures/landmarks/):
#
#     the whole corpus lies between 0.468 and 0.888
#
# 0.30 is below ALL of it, so visible() returns True on every frame ever
# captured here — a load screen, an outdoor street, an unlit office corridor.
# It is not a threshold; it is `True` wearing one as a disguise, which is the
# diagnosis-catalogue shape: the code does nothing and looks like it works.
#
# AND RAISING IT DOES NOT HELP. Ground truth by OPENING the frames and looking
# for the jukebox (all 22 are pinned in the test, with what each one shows):
#
#     jukebox IN the frame    n= 9   0.583 .. 0.766
#     jukebox NOT in it       n=13   0.523 .. 0.656
#
# The two populations OVERLAP across 0.583-0.656, a band holding 7 of the 9
# positives and 12 of the 13 negatives. A stretch of BAR COUNTER with no
# jukebox in it scores 0.656; an OUTDOOR STREET scores 0.616; an unlit office
# door scores 0.612 — all of them above frames where the jukebox fills a third
# of the screen (0.583-0.639). AUC is 0.590 against 0.500 for a coin flip, and
# the best cut anywhere on the sweep still keeps only 4 of 9 positives while
# admitting 2 of 13 negatives.
#
# So this is the RETICLE_MIN_CONTRAST case: NO THRESHOLD ON THIS QUANTITY
# SEPARATES THESE POPULATIONS. Substituting a different unsupported number is
# the same defect as the comment this replaces. The value is LEFT AT 0.30 —
# changing it would imply a calibration that does not exist, and nothing reads
# it anyway.
#
# THE RESULT SURVIVES RETUNING MIN_WINDOW_TEXTURE, which was the obvious
# escape. Sweeping that floor and re-scoring the same 22 frames:
#
#     0.35 (shipped)  AUC 0.590      0.70  AUC 0.701
#     0.50            AUC 0.667      0.80  AUC 0.718   <- peak
#     0.60            AUC 0.667      0.90  AUC 0.607
#                                    0.95  AUC 0.436
#
# The positives never clear the negatives at ANY of those values, so nothing
# there separates either. Treat the apparent peak as a LEAD AND NOTHING MORE:
# it is seven candidate values scored on the same 22 frames the metric is
# computed from, which is fitting the constant to its own evaluation set, and
# n=22 cannot resolve a difference that size. MIN_WINDOW_TEXTURE IS LEFT AT
# 0.35. Anything else needs a held-out set and an interventional A/B — this
# project has nine well-motivated navigation changes that reviewed well and
# then measured flat.
#
# WHAT IS NOT KNOWN: whether the score is useless or only its ABSOLUTE LEVEL
# is. Normalised cross-correlation on gradient magnitude rewards any cluttered
# window, so the level mostly reports how busy the frame is. A detector that
# worked would need a RELATIVE test — the peak against the rest of its own
# correlation surface, or against the same view a moment earlier — and that has
# not been measured. Do not read the negative result above as covering it.
MATCH_MIN = 0.30


def _edges(a):
    gy, gx = np.gradient(a.astype(float))
    return np.hypot(gx, gy)


def _prep(img, width):
    g = img.convert("L")
    h = max(1, int(g.height * width / g.width))
    return _edges(np.asarray(g.resize((width, h), Image.BILINEAR), dtype=float))


SOURCE_MANIFEST = "sources.json"
DEFAULT_SOURCE_WIDTH = 1920


def _source_widths(d):
    """{template filename: width of the frame it was cut from}.

    A template's on-screen size only means something relative to the frame it
    came from. Assuming they all came from a 1920-wide capture was wrong: the
    dealer_tight set was cut from 1400-wide RECORDING frames, so every one of
    them was scaled 37% off. The scale sweep hid it — which is worse than
    failing, because it meant the sweep had to be wide enough to cover a
    systematic error, and a wide sweep is what let tiny templates match blank
    walls in the first place.
    """
    path = os.path.join(d, SOURCE_MANIFEST)
    if os.path.exists(path):
        try:
            with open(path) as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def _templates(d):
    out = []
    widths = _source_widths(d)
    for f in sorted(glob.glob(os.path.join(d, "template*.jpg"))):
        img = Image.open(f)
        src = widths.get(os.path.basename(f), DEFAULT_SOURCE_WIDTH)
        # the template's size as a FRACTION of its source frame, then in the
        # working frame's terms — no assumption about where it was cut from
        base = int(img.width * WORK_WIDTH / float(src))
        for s in SCALES:
            w = max(8, int(base * s))
            h = max(8, int(img.height * w / img.width))
            t = _edges(np.asarray(img.convert("L").resize((w, h), Image.BILINEAR),
                                  dtype=float))
            t = t - t.mean()
            n = np.linalg.norm(t)
            if n > 1e-6:
                out.append((t / n, s))
    return out


_CACHE = {}


def find(img, template_dir=None):
    """(score, centre_x_fraction, scale) for the best match of a landmark.

    See find_xy for the vertical position as well. This wrapper is kept because
    callers that only steer yaw are common.

    `template_dir` selects which landmark. The jukebox and the dealer's table
    are both STATIC — confirmed by the person who plays this — which is what
    makes them usable where Wanda and the compass markers were not.
    """
    d = template_dir or TEMPLATE_DIR
    if d not in _CACHE:
        _CACHE[d] = _templates(d)
    if not _CACHE[d]:
        raise RuntimeError(f"no template in {d}/")
    f = _prep(img, WORK_WIDTH)
    best = (-2.0, None, None)
    for t, s in _CACHE[d]:
        th, tw = t.shape
        if th >= f.shape[0] or tw >= f.shape[1]:
            continue
        num = fftconvolve(f, t[::-1, ::-1], mode="valid")
        ones = np.ones_like(t)
        s2 = fftconvolve(f * f, ones, mode="valid")
        s1 = fftconvolve(f, ones, mode="valid")
        n = t.size
        var = np.maximum(s2 - (s1 * s1) / n, 0.0)
        sd = np.sqrt(var / n)
        floor = f.std() * MIN_WINDOW_TEXTURE
        denom = np.sqrt(np.maximum(var, 1e-9))
        corr = (num - s1 * t.mean()) / denom
        corr[sd < floor] = -1.0
        i = int(np.argmax(corr))
        y, x = np.unravel_index(i, corr.shape)
        v = float(corr[y, x])
        if v > best[0]:
            best = (v, (x + tw / 2.0) / f.shape[1], s,
                    (y + th / 2.0) / f.shape[0])
    return best[:3]


def find_xy(img, template_dir=None):
    """(score, x_fraction, y_fraction, scale) — BOTH axes.

    The vertical position was being computed and then discarded, so every aim
    was yaw-only: the reticle could be perfectly centred left-to-right and still
    sit above or below the target, which is what a person watching it sees as
    "still off" even when the numbers say CENTRED.
    """
    d = template_dir or TEMPLATE_DIR
    if d not in _CACHE:
        _CACHE[d] = _templates(d)
    if not _CACHE[d]:
        raise RuntimeError(f"no template in {d}/")
    f = _prep(img, WORK_WIDTH)
    best = (-2.0, 0.5, 0.5, None)
    for t, s in _CACHE[d]:
        th, tw = t.shape
        if th >= f.shape[0] or tw >= f.shape[1]:
            continue
        num = fftconvolve(f, t[::-1, ::-1], mode="valid")
        ones = np.ones_like(t)
        s2 = fftconvolve(f * f, ones, mode="valid")
        s1 = fftconvolve(f, ones, mode="valid")
        n = t.size
        var = np.maximum(s2 - (s1 * s1) / n, 0.0)
        sd = np.sqrt(var / n)
        floor = f.std() * MIN_WINDOW_TEXTURE
        denom = np.sqrt(np.maximum(var, 1e-9))
        corr = (num - s1 * t.mean()) / denom
        corr[sd < floor] = -1.0
        i = int(np.argmax(corr))
        y, x = np.unravel_index(i, corr.shape)
        v = float(corr[y, x])
        if v > best[0]:
            best = (v, (x + tw / 2.0) / f.shape[1],
                    (y + th / 2.0) / f.shape[0], s)
    return best


# A landmark can need more than one template set. Cutting a template from a
# close-up and shrinking it does NOT work at distance — the detail that makes it
# distinctive is lost, and it starts matching windows and wall lamps instead.
# Separate sets cut at each apparent size do work: at a distance where the
# close-up set scored 0.598 on a window, a set cut at that distance scored 0.925
# on the target itself.
SETS = {
    "dealer": ("test_fixtures/dealer_tight", "test_fixtures/dealer_far"),
}


def find_best_xy(img, name_or_dir):
    """Best match across every template set registered for a landmark.

    Scores are normalised correlations, so they are comparable between sets and
    the higher one can simply be taken.
    """
    dirs = SETS.get(name_or_dir, (name_or_dir,))
    best = (-2.0, 0.5, 0.5, None, None)
    for d in dirs:
        try:
            score, x, y, scale = find_xy(img, d)
        except RuntimeError:
            continue
        if score > best[0]:
            best = (score, x, y, scale, d)
    return best


def visible(img, template_dir=None, threshold=MATCH_MIN):
    return find(img, template_dir)[0] >= threshold
