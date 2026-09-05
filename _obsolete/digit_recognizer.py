"""Digit recognition for this game's stylized badge font, via Hough circle
detection + normalized template matching against a learned glyph set.

Built after both tesseract and EasyOCR proved unreliable on these
specific digits (bold hand-inked style; EasyOCR only fired at one narrow
upscale factor and missed entirely on several plainly-legible digits)."""

import os

import cv2
import numpy as np
from PIL import Image

GLYPH_SIZE = (32, 48)


def find_badge_digit(pil_img, upscale=6, thresh=110):
    """Locate the round badge via Hough, return its binarized interior
    normalized to GLYPH_SIZE, or None."""
    g = np.array(pil_img.convert("L"))
    g = cv2.resize(g, (g.shape[1] * upscale, g.shape[0] * upscale), interpolation=cv2.INTER_CUBIC)
    blur = cv2.medianBlur(g, 5)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1, minDist=50, param1=100, param2=30,
        minRadius=int(g.shape[0] * 0.18), maxRadius=int(g.shape[0] * 0.55),
    )
    if circles is None:
        return None
    x, y, r = np.uint16(np.around(circles[0][0]))
    r_in = int(r * 0.55)
    y0, y1 = max(0, int(y) - r_in), min(g.shape[0], int(y) + r_in)
    x0, x1 = max(0, int(x) - r_in), min(g.shape[1], int(x) + r_in)
    crop = g[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    _, bw = cv2.threshold(crop, thresh, 255, cv2.THRESH_BINARY)
    # tighten onto the glyph's ink so size/position normalize consistently
    cols = np.where(bw.max(axis=0) > 0)[0]
    rows = np.where(bw.max(axis=1) > 0)[0]
    if len(cols) and len(rows):
        bw = bw[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    if bw.size == 0:
        return None
    return cv2.resize(bw, GLYPH_SIZE, interpolation=cv2.INTER_AREA)


def match_digit(glyph, templates):
    """templates: {digit_str: [glyph_arrays]}. Returns (digit, score)."""
    if glyph is None:
        return None, 0.0
    best, best_score = None, -1.0
    gf = glyph.astype(np.float32) / 255.0
    for digit, tmpls in templates.items():
        for t in tmpls:
            tf = t.astype(np.float32) / 255.0
            score = float(1.0 - np.mean(np.abs(gf - tf)))
            if score > best_score:
                best, best_score = digit, score
    return best, best_score
