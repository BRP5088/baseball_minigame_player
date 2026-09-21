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
  * A TACTICS CARD'S TYPE IS READ FROM ITS BANNER, and it ABSTAINS rather than guess.
    CLAUDE.md section 4: only swing and pitch boosts add power, while speed and fielding
    boosts carry a nonzero bonus that adds NONE, so a speed boost read as a swing boost
    plays the wrong card for $50. Measured leave-one-HAND-out over 83 cards in 30 hands:
    the right answers score 0.773 and above, every one of the 10 errors scores 0.761 or
    below, and MIN_TYPE_SCORE sits in that gap. A card below it returns type None.
  * A TACTICS CARD'S BONUS is read only when its digit happens to be isolated enough for
    the digit finder: measured 23 of 83, with ZERO wrong. The other 60 come back None.
  * The tactics BONUS is not read either. Its digit sits fused inside the wreath.
  * The shield digit is white on a DARK shield, the exact inverse of this detector's
    target. It is not read here at all.
  * Which cards are PLAYER and which are TACTICS is decided by WHERE the disc sits in its
    slot, and only on the fan path. When the fan does not fit -- a short hand, an empty
    table -- there is no such evidence and every position comes back "unknown".
  * Templates cover 1, 2, 4, 5, 6, 7, 8, 9. THE GAME HAS NO 3 (the user, 2026-09-09) and no
    player card has ever shown a power of 1, 2 or 3: powers run 4 to 9, and 1 and 2 appear
    only as tactics bonuses. A digit that matches nothing comes back None, which the caller
    must treat as NOT READ -- never as absent.
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


# THE FITTED RADIUS IS NOT RELIABLE TO A PIXEL, AND ONE PIXEL DECIDES THE ANSWER.
# Found by filming a hand that was NOT MOVING: over 28 consecutive frames of a settled
# hand, one card read 7 / unread / 7 / unread with the score swinging 0.57 to 0.91. The
# picture was identical to the eye; what changed was the circle the finder fitted, which
# alternated between r=19 and r=20. read_digit resamples the crop to a fixed 24x24, so a
# one-pixel radius rescales the digit inside the tile and the correlation moves ~0.1-0.25.
#
# The same lesson as the shield and the banner (CLAUDE.md 10.23): do not trust one crop
# position. Here it is the SCALE that has to be searched rather than the position.
#
# Measured on the REAL saved captures -- not video, which has compression the live path
# does not -- over 1,181 player cards:
#
#     unread by the single-radius reader            24
#     recovered by searching r-3 .. r+3             16   all 16 agreeing with the paid model
#     answers CHANGED on cards that already read     0   of 1,157
#
# So it is free: it recovers two thirds of the misses and cannot alter an answer that was
# already being given. The best score sits at dr -1 or -2 on nearly every card, which says
# the 1.05 expansion below is slightly too generous -- but a search is robust to that in a
# way that re-tuning one constant is not, and re-tuning would have to be re-done per
# capture geometry.
DIGIT_RADII = (-3, -2, -1, 0, 1, 2, 3)


def read_digit(img, circle):
    """(digit, score) for one located circle, or (None, score) when nothing matches.

    The circle's RADIUS is searched, because the finder's fit is only good to a pixel or
    two and a pixel decides the answer -- see DIGIT_RADII above.
    """
    cx, cy, r = circle[0], circle[1], circle[2]
    vecs, digits = _templates()
    best_d, best = None, 0.0
    for dr in DIGIT_RADII:
        rr = int((r + dr) * 1.05)
        if rr < 4:
            continue
        v = _vector(img, (max(0, cx - rr), max(0, cy - rr),
                          min(img.width, cx + rr), min(img.height, cy + rr)))
        if v is None:
            continue
        scores = vecs @ v
        k = int(scores.argmax())
        if float(scores[k]) > best:
            best_d, best = digits[k], float(scores[k])
    return (best_d if best >= MIN_SCORE else None), best


# A SELECTED TACTICS CARD BRIGHTENS, AND find_tactics WENT BLIND TO IT BY ONE GREYLEVEL.
# The wreath is located as a DARK blob, and 110 was measured on unselected cards. Selecting
# a card lifts and brightens it; measured on the same card in the same hand
# (test_fixtures/hand_cursor/tactics_{un,}selected_slot0.png):
#
#     unselected wreath   min   0   p05  55   median 106     found at 110
#     SELECTED   wreath   min 111   p05 119   median 127     found at NOTHING under 111
#
# One greylevel. The card then dropped out of the fan entirely, its row fell through to a
# branch that fills y from a SLOT CONSTANT -- which for slot 0 equals the card's own resting
# position -- and a completely lost card reported a perfectly stable y. That is what hid a
# selected card moving 44 px, and why the lift check could never fire on a tactics card.
#
# The existing threshold is NOT moved: it decides every frame this reader has ever handled.
# SELECTED_DARK_MAX is a SECOND PASS, run only for a slot the first pass left empty, so it
# can add a reading but never change one.
SELECTED_DARK_MAX = 150        # between the selected p05 of 119 and the card face above it
RAISED_DARK_MAX = 150          # a raised card's disc only fits at this threshold, see _read_fan
TACTICS_PROMOTE_MIN = 0.80     # above the 0.695 max seen on any PLAYER slot; see _read_fan


def find_tactics(img, dark_max=110):
    """Locate a TACTICS card's circle, which the player-card reader cannot see.

    A tactics card wraps its circle in an ornate dark wreath and the digit's ink FUSES with
    it, so the player reader -- which looks for isolated ink on clean white -- finds nothing
    there. Measured: on hand 015 that fused shape is one blob 36x40 px, far too big for a
    digit, and eroding it does not separate the two (it stays 33x38, then fragments).

    So stop separating them. The wreath is a fixed game asset too, which makes "digit plus
    wreath" a fixed shape in its own right. Located this way it is found on 15 of 15 hands,
    including every one the player reader misses.

    This is why there are several readers rather than one: each card type presents the digit
    differently, and at about 2 ms a reader the cost of running them all is nothing. A reader
    that tried to cover both lost more than it gained -- merging a disc-hole detector into
    the player reader took disagreements from 0 to 1.
    """
    import numpy as _np
    import scipy.ndimage as _ndi
    g = _np.asarray(img.convert("L"), dtype=_np.uint8)
    H, W = g.shape
    lab, n = _ndi.label(g <= dark_max)
    out = []
    for sl, i in zip(_ndi.find_objects(lab), range(1, n + 1)):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        # The fused shape, measured across 15 hands: 33-37 wide, 38-41 tall.
        if not (28 <= w <= 48 and 30 <= h <= 50):
            continue
        if ys.start == 0 or xs.start == 0 or ys.stop >= H or xs.stop >= W:
            continue
        out.append({"x": int((xs.start + xs.stop) / 2),
                    "y": int((ys.start + ys.stop) / 2),
                    "box": (int(xs.start), int(ys.start), int(xs.stop), int(ys.stop))})
    out.sort(key=lambda c: c["x"])
    return out


# ---------------------------------------------------------------------------------------
# THE HAND IS FIVE CARDS IN A FIXED FAN, so segment the CARDS and give each at most one
# disc. Searching the whole strip for discs can return any number of positions: measured
# over the 57 labelled hands in overnight/local_hand/agreement.jsonl it returned 3 to 8,
# 30 of 57 hands had the wrong CARD COUNT and another 17 put the tactics cards in the wrong
# slots -- only 10 of 57 agreed with the paid model about the positions.
#
# The fan is a UI layout, not a scene: over two independent corpora (57 hands here, 15 in
# agent_progress/bakeoff) each slot's power disc lands within about +-15 px of the same
# spot, and the y positions trace the fan's arc. So a card slot is a MEASURED 2D anchor,
# every candidate is assigned to the nearest one, and the count cannot then be wrong.
#
# MEASURED per slot (medians of every candidate that landed on a card the paid model named):
SLOT_PLAYER = [(195, 195), (382, 160), (546, 143), (729, 169), (886, 205)]
# A TACTICS card carries its disc 60-83 px further LEFT, inside the wreath. That offset is
# what tells the two kinds apart -- and it is the ONLY thing that does. A gate on the card's
# dark fraction was measured over 2,688 windows (4 widths x 14 offsets x 16 bands x 3
# heights) against 202 player and 83 tactics slots and the populations OVERLAP in every one,
# so no such gate exists. Slot 4 has no tactics sample in either corpus; its anchor is
# extrapolated and is the weakest entry here.
SLOT_TACTICS = [(132, 194), (299, 150), (486, 134), (661, 150), (826, 190)]
SLOT_TOL = 34
# The crop is a FRACTIONAL region (orchestrator.GAMEPLAY_REGIONS_FRAC["hand"]), so its
# PIXEL size follows the capture: 979x307 is a 1920x1080 capture, and CLAUDE.md section 3
# records 1867x1050 captures in the same session (a 952x298 crop). The anchors above were
# measured at 979 wide, so they are scaled to whatever crop arrives.
ANCHOR_W = 979.0

# A REAL DISC AGAINST CARD ART, two populations with a gap, over 247 candidates:
#     radius r    junk  9-17  (38)     disc 18-22 (209)     only 1 at 17, 2 at 16
#     reach       junk  3-5   (41)     disc  6-8  (206)     only 1 at 5,  3 at 4
# The mouse's teeth and eyes are dark ink ringed by white face -- exactly what the digit
# finder hunts -- and this is what removes them. It costs ZERO real discs (per-card recall
# 204/285 with the gate and without it) while dropping 41 junk candidates.
DISC_MIN_R = 18
DISC_MIN_REACH = 6
# The second pass at 90 exists because a 9 or a 7 TOUCHES its disc's outline ring and the
# two label as one oversized component at 110. Recall 254/285 -> 265/285. The PRIMARY
# threshold must win a tie: a blob found at 90 has a tighter bounding box than the crop the
# templates were cut at, and letting it win read 5 digits exactly one too high.
#
# THE THIRD PASS AT 130 IS FOR THE CARD UNDER THE CURSOR, and the user found it. The game
# LIFTS and HIGHLIGHTS whichever card the cursor sits on, so that card renders BRIGHTER and
# its ink falls above DARK=110 -- the finder never sees the disc at all. Confirmed on four
# hands the user identified as having a selected card, every one of which was an abstention:
#
#     hand #9  the lifted PITCH FOCUS  disc invisible at 110 and 90, found at 130
#              at (486, 92) against a tactics anchor of (486, 134): a lift of 42 px
#     hand #17 the lifted POWER SWING  same, at (133, 152) against (132, 194): 42 px
#
# The LIFT itself needs no handling -- 42 px costs 14 in the slot cost (|dx| + |dy|/3)
# against SLOT_TOL 34, so the slot model already reaches it. Only the brightness lost it.
# Measured over the whole corpus, adding 130 LAST (so it only fills what the darker passes
# missed): aligned 133 -> 134, digits read 459 -> 464, unread 7 -> 5, and WRONG unchanged
# at 3 -- all three of which are the paid model's own errors, not the reader's.
DARK_THRESHOLDS = (110, 90, 130)

# THE DISC AS A WHITE BLOB, for the 9s and 7s whose ink fuses with the ring anyway. Its own
# shape features do NOT separate a disc from card art (w, h, area and fill all overlap
# between on-slot and off-slot blobs), so it is used ONLY to fill a slot nothing else
# claimed, never as a detector in its own right. Union recall: 281/285.
DISC_WHITE = 200
DISC_WHITE_SIZE = (30, 50)
DISC_INNER = 0.78          # the digit lives this far inside the disc; the ring is outside it

# DOES THE FIVE-CARD FAN FIT AT ALL? Late in a match a hand shrinks and a short fan
# RE-CENTRES -- agent_progress/bakeoff frames 018, 028 and 053 are 3- and 4-card hands whose
# cards sit nowhere near these anchors, and 003/027/052 are an empty table -- so the slot
# model must not be applied to one. Per-hand MEDIAN residual to the nearest anchor:
#     five-card hands, n=72   min 0.0   p50 3.0   p95 12.0   MAX 14.0
#     short hands,     n=3    28.5, 51.3, 32.3
# THE NEGATIVE SIDE IS THREE FRAMES, which is thin, and that is exactly why failing this
# gate costs nothing: the reader falls back to the ungated search that shipped before, so a
# short hand can only be as wrong as it already was. A per-CANDIDATE residual was tried
# first and CANNOT gate -- three of the seven short-hand candidates sit inside the five-card
# range (CLAUDE.md 10.4).
FIT_MAX = 20.0
FIT_MIN_DISCS = 2


def _white_discs(g):
    """The power discs as white blobs, whatever their digit is doing."""
    import scipy.ndimage as _ndi
    H, W = g.shape
    lab, n = _ndi.label(g >= DISC_WHITE)
    lo, hi = DISC_WHITE_SIZE
    out = []
    for i, sl in enumerate(_ndi.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if not (lo <= w <= hi and lo <= h <= hi):
            continue
        if ys.start == 0 or xs.start == 0 or ys.stop >= H or xs.stop >= W:
            continue
        out.append(((xs.start + xs.stop) // 2, (ys.start + ys.stop) // 2,
                    int((lab[sl] == i).sum()), (xs.start, ys.start, xs.stop, ys.stop)))
    return out


def _digit_in_disc(g, box):
    """(cx, cy, r) for the digit inside a white disc, or None.

    Keeps only the dark pixels inside the disc's inner radius, which is what separates a
    fused 9 from its own ring.
    """
    import scipy.ndimage as _ndi
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rad = DISC_INNER * max(x1 - x0, y1 - y0) / 2.0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sub = (g[y0:y1, x0:x1] <= 110) & (((xx - cx) ** 2 + (yy - cy) ** 2) <= rad ** 2)
    lab, n = _ndi.label(sub)
    if not n:
        return None
    sizes = _ndi.sum(sub, lab, range(1, n + 1))
    ys, xs = np.where(lab == int(np.argmax(sizes)) + 1)
    if len(xs) < 20:
        return None
    bx0, bx1, by0, by1 = xs.min() + x0, xs.max() + x0 + 1, ys.min() + y0, ys.max() + y0 + 1
    w, h = bx1 - bx0, by1 - by0
    if not (5 <= w <= 28 and 9 <= h <= 34):
        return None
    return (int((bx0 + bx1) // 2), int((by0 + by1) // 2), int(max(w, h) * 0.9))


def _slot(x, y, s=1.0):
    """(cost, slot index, kind) for the nearest card anchor, at crop scale `s`."""
    return min((abs(x - t[i][0] * s) + abs(y - t[i][1] * s) / 3.0, i, k)
               for i in range(5)
               for k, t in (("player", SLOT_PLAYER), ("tactics", SLOT_TACTICS)))


def _free(x, y, taken):
    """Nothing already claims this spot. IN TWO DIMENSIONS: an x-only test let a junk white
    blob 117 px BELOW a real disc, in the same column, suppress it (hand_1788935911)."""
    return all((x - t[0]) ** 2 + (y - t[1]) ** 2 > 625 for t in taken)


def _strong_discs(img):
    """Disc-sized enclosed digits, both dark thresholds, primary first."""
    from circle_finder import find_circles
    seen, out = [], []
    for thr in DARK_THRESHOLDS:
        for c in find_circles(img, thr):
            if c[3] < DISC_MIN_REACH or c[2] < DISC_MIN_R:
                continue
            if _free(c[0], c[1], seen):
                seen.append((c[0], c[1]))
                out.append(c)
    out.sort(key=lambda c: c[0])
    return out


# ---------------------------------------------------------------------------------------
# THE TACTICS TYPE, FROM THE BANNER. This is the field that decides play -- CLAUDE.md
# section 4 records that only SWING_BOOST and PITCH_BOOST add power, while speed and
# fielding boosts carry a nonzero bonus that adds NONE -- so it is guarded harder than any
# digit here. The disc cannot answer it; the BANNER can, because each card writes its name
# across the middle in white on a dark band and that is a fixed game asset like the digits.
#
# MEASURED, leave-one-HAND-out over 83 located tactics cards in 30 distinct hands (a hand
# sampled twice is nearly the same picture; scoring across the pair measures JPEG, not
# recognition):
#
#     top score   RIGHT p05 0.773    WRONG MAX 0.761      no overlap
#     raw accuracy 73/83; all 10 errors fall below the worst right answer
#
# AND THAT CLEAN SEPARATION DID NOT SURVIVE A BIGGER BANK. Re-measured over 196 cards in 86
# hands with 117 templates: the right answers run down to 0.342 and the worst WRONG reaches
# 0.815, so the populations OVERLAP and no gate sits in a gap any more. Saying otherwise
# would be fitting a constant to this sample (CLAUDE.md 10.4).
#
# So the gate is set as a SAFETY TRADE instead, and the trade is asymmetric: an abstention
# costs one paid call, while a wrong type plays a speed boost as if it added power in a $50
# match. Sweep, leave-one-hand-out:
#
#     0.77   173/196 read (88%)   172 right,  1 WRONG      <- a speed boost read as swing
#     0.82   167/196 read (85%)   167 right,  0 wrong      but only 0.005 above the worst wrong
#     0.88   152/196 read (78%)   152 right,  0 wrong      8% clear of it
#
# 0.88 is the one with margin. The 1 wrong at 0.77 has NOT been adjudicated by eye and may
# itself be a paid-model error -- that model read three 6s as 5s on the same day.
# The MARGIN over the runner-up type does NOT separate (right p05 0.112 against wrong max
# 0.203) and is not used -- measured and dropped, per CLAUDE.md 10.4.
TACTICS_TEMPLATES = os.path.join(_HERE, "tactics_templates.npz")
# RE-MEASURED after the box was narrowed and the crop recentred on the found card.
# Cross-session (templates from the early half of the corpus, tested on the late half,
# 173 cards) the two populations are:
#
#     RIGHT (n=172)   p01 0.714   p05 0.830   p50 0.969
#     WRONG (n=1)     the single wrong answer in the whole test set scores 0.766
#
# They overlap in the tail, so this is a SAFETY TRADE and not a gap (CLAUDE.md 10.4):
#
#     gate 0.80   coverage 97.7%   0 wrong   margin over the worst wrong +0.034
#     gate 0.85   coverage 93.6%   0 wrong   margin +0.084          <- shipped
#     gate 0.88   coverage 87.3%   0 wrong   margin +0.114
#
# 0.85 keeps the ~8% margin this reader's previous gate was chosen for, at more than
# twice the coverage. The old value was 0.88 against a 180px box and read 40.5%.
MIN_TYPE_SCORE = 0.85

# AND A SECOND, LOWER GATE, BECAUSE "IS THIS A TACTICS CARD AT ALL" IS AN EASIER QUESTION
# THAN "WHICH TACTICS CARD IS IT".
#
# `kind` is decided BY POSITION -- the tactics disc sits 60-83px left of the player disc in
# the same slot -- and position is wrong on about 3% of hands: over 360 recorded hands the
# fan called a card `tactics` that the paid model called `player` eleven times, and opening
# those frames settled it against the fan every time. They are plainly player cards, with a
# BATTER or PITCHER banner, a power disc and a shield. This is the one field where the paid
# model was RIGHT and the local reader was WRONG.
#
# The banner separates them completely, because a player card has no tactics banner to find.
# Measured CROSS-SESSION (bank cut from the early half of the corpus, scored on the late
# half, so a card cannot score itself -- without that split every real tactics card scores
# 1.000 against its own template and the gap is an illusion):
#
#     really TACTICS (n=176)   MIN 0.595   p01 0.720   p05 0.823   p50 0.967
#     really PLAYER  (n=4)     p50 0.207   p95 0.481   MAX 0.524
#
# Pooling every real player card that has landed on a tactics anchor (14 of them, across
# both the in-sample and cross-session passes) against the cross-session tactics scores:
#
#     really PLAYER   MAX 0.560
#     really TACTICS  MIN 0.595   p01 0.720   p05 0.823
#
# The band 0.560 .. 0.595 is empty. TACTICS_PRESENT_MIN sits inside it, ABOVE the player
# maximum -- 0.56 was tried first and is exactly ON that maximum, which is the mistake
# CLAUDE.md 10.4 is about. The band is only 0.035 wide, so this is a genuine constraint
# and not a comfortable margin; it is reported here rather than rounded away.
#
# HONEST LIMIT: n = 4 in the cross-session player group (11 in sample). The direction is
# unambiguous and the band is empty, but the RATE is not established on four points. A
# player card mislabelled tactics is never played as a batter, so the cost of the old
# behaviour was a missing card rather than a wrong one -- which is why it stayed invisible.
TACTICS_PRESENT_MIN = 0.58
# The banner's box relative to the slot's TACTICS anchor, in the 979-wide crop the anchors
# were measured in, and scaled with them.
# THE BOX WAS 180px WIDE AND THAT WAS THE WHOLE PROBLEM. At 180 it reaches past the
# card and takes in the NEIGHBOUR's banner ("BATTER"), so the correlation was being
# asked to match two cards at once and collapsed whenever the neighbour differed. A
# contact sheet of the cards the reader called unsure settled it in one look: the
# banner text was PLAINLY LEGIBLE in nearly every one, sitting off to one side with a
# stranger's banner beside it. Narrowing to 120 and recentring on the FOUND card:
#
#     box    what it covers                cross-session coverage at zero wrong
#     180w   the banner + the neighbour            78.0%
#     140w   the banner + a sliver                 94.8%
#     120w   the banner                            95.4%      <- shipped
#     100w   part of the banner                    97.7%, but 1 WRONG
#
# (What actually shipped before this was worse than the 180w row, because it also
# cropped at the fixed SLOT anchor rather than the found card: 40.5% at gate 0.88.)
BANNER_BOX = (-62, 18, 58, 70)
BANNER_SIZE = (48, 20)
# How far to slide the crop looking for its best fit. Measured: +-12 is enough, and
# +-32 and +-48 buy nothing, because recentring on the found card has already done the
# work -- a located tactics card sits within 30px of its slot anchor in x, 7px in y.
BANNER_SEARCH = tuple((ox, oy) for ox in range(-12, 13, 4) for oy in range(-6, 7, 3))

_type_cache = None


def _type_templates():
    global _type_cache
    if _type_cache is None:
        if not os.path.exists(TACTICS_TEMPLATES):
            return None
        z = np.load(TACTICS_TEMPLATES)
        _type_cache = (z["vectors"], [str(t) for t in z["types"]])
    return _type_cache



def _banner_at(img, cx, cy, ox, oy):
    sc = img.width / ANCHOR_W
    x0, y0, x1, y1 = BANNER_BOX
    box = (int(cx + (x0 + ox) * sc), int(cy + (y0 + oy) * sc),
           int(cx + (x1 + ox) * sc), int(cy + (y1 + oy) * sc))
    if (box[0] < 0 or box[1] < 0 or box[2] > img.width or box[3] > img.height
            or box[2] - box[0] < 10 or box[3] - box[1] < 6):
        return None
    a = np.asarray(img.crop(box).convert("L").resize(BANNER_SIZE, Image.LANCZOS),
                   dtype=np.float32).ravel()
    a = a - a.mean()
    n = np.linalg.norm(a)
    return None if n < 1e-6 else a / n


def _best_banner(img, slot, cx, cy):
    """(type, score) for the best-fitting banner offset, or (None, 0.0).

    The crop is slid over BANNER_SEARCH and the best fit kept, so a card a few pixels
    off where it was expected is read rather than abstained on.
    """
    bank = _type_templates()
    if bank is None:
        return None, 0.0
    vecs, types = bank
    if cx is None or cy is None:
        if not (0 <= slot < len(SLOT_TACTICS)):
            return None, 0.0
        # NO CANDIDATE REACHED THIS SLOT, so there is no found position and both
        # anchors are guesses. Try each and keep the better fit -- measured over the
        # 17 corpus rows this branch emits, the tactics anchor reads 0 of them and the
        # player anchor's x reads 7, right, with none wrong. Trying both costs one
        # more search on a path that fires ~5% of the time.
        sc = img.width / ANCHOR_W
        starts = [(SLOT_TACTICS[slot][0] * sc, SLOT_TACTICS[slot][1] * sc),
                  (SLOT_PLAYER[slot][0] * sc, SLOT_PLAYER[slot][1] * sc)]
    else:
        starts = [(cx, cy)]
    best_t, best = None, 0.0
    for sx, sy in starts:
        for ox, oy in BANNER_SEARCH:
            v = _banner_at(img, sx, sy, ox, oy)
            if v is None:
                continue
            scores = vecs @ v
            k = int(scores.argmax())
            if float(scores[k]) > best:
                best_t, best = types[k], float(scores[k])
    return best_t, best


# THE TWO TYPES THAT ADD POWER. CLAUDE.md section 4: a speed or fielding boost carries a
# nonzero bonus that adds NONE, and decision_engine branches on exactly this.
ADDS_POWER = frozenset({"swing_boost", "pitch_boost"})
# The binary question is easier than the 4-way name and it is the one the caller asks.
# Measured across SESSIONS (train on one, test on another hours later, 198/61 cards):
#     gate 0.70   binary 42 right  9 WRONG   84% read      4-way 41 right 10 WRONG
#     gate 0.77   binary 38 right  0 WRONG   62% read      4-way 37 right  1 WRONG
#     gate 0.85   binary 22 right  0 WRONG   36% read
# 0.77 is the operating point: zero wrong on unseen data at the best coverage that holds.
MIN_ADDS_POWER_SCORE = 0.77


def reads_adds_power(img, slot, cx=None, cy=None):
    """(True|False, score) for "does this tactics card add power", or (None, score).

    None means NOT READ and the caller must ask the paid model. It never guesses: a speed
    boost played as if it added power is a wrong card in a $50 match, and an abstention is
    one API call.
    """
    t, best = _best_banner(img, slot, cx, cy)
    if t is None or best < MIN_ADDS_POWER_SCORE:
        return None, best
    return (t in ADDS_POWER), best


def read_tactics_type(img, slot, cx=None, cy=None):
    """(type, score) for the tactics card in `slot`, or (None, score) when unsure.

    None means NOT READ and the caller must ask the paid model. It never guesses: the
    whole value of this reader is that its answer can be trusted without a second opinion.
    """
    t, best = _best_banner(img, slot, cx, cy)
    return (t if (t is not None and best >= MIN_TYPE_SCORE) else None), best


def read_hand(img):
    """Every card position in a hand strip, left to right, from every reader.

    Each entry is {"x", "kind", "digit", "score"}. `kind` is "player" or "tactics".
    `digit` is None where nothing matched -- an unknown digit, an untemplated one, or a
    card element -- and the caller must treat that as NOT READ, never as absent. Nothing
    here ever guesses: that is what makes a partial answer safe to fall back on.

    Positions come from the FIVE-SLOT FAN above whenever the fan fits, so the card count
    cannot be wrong; when it does not fit -- a short hand, an empty table -- the older
    ungated search runs instead and the answer is no worse than it used to be.

    Tactics cards are located and their KIND is now decided by where their disc sits inside
    the slot, but their bonus is still not read.
    """
    strong = _strong_discs(img)
    if len(strong) >= FIT_MIN_DISCS:
        s = img.width / ANCHOR_W
        fit = sorted(_slot(c[0], c[1], s)[0] / s for c in strong)
        # COUNT THE DISCS THAT LAND ON A SLOT; DO NOT TAKE THE MEDIAN (2026-09-20).
        #
        # A SELECTED card is displaced ~22-26 px HORIZONTALLY as well as lifted, so
        # its residual clears FIT_MAX on its own. The median then decides the whole
        # frame: with ONE card selected it still lands on a resting disc and the fit
        # passes, but with TWO selected -- which is what the engine chooses on every
        # play that attaches a tactics card -- the median lands on a DISPLACED disc
        # and the fan is rejected. Measured live, a real hand with slots 0 and 1 up:
        #
        #     residuals 26.3 (sel)  22.3 (sel)  12.7  0.0   median 22.3 > 20.0
        #
        # read_hand then falls to _read_ungated, whose rows carry NO slot identity
        # and NO y -- so selected_cards and cursor_slot both go blind at exactly the
        # moment the loop needs to verify a two-card play.
        #
        # The question the gate is for is "is the fan THERE", not "is every card at
        # rest". FIT_MIN_DISCS discs landing on slots answers it, and reuses the two
        # constants already fitted for this -- nothing new is invented.
        #
        # Measured over 540 archived hand crops: 459 accepted by both rules, 8
        # rejected by both, ZERO that this rule rejects and the median accepts, and
        # exactly ONE newly admitted -- hand_1788969878714664000.png, which is a
        # fully visible five-card fan (POWER SWING +2, BATTER 7/1, SPEED BOOST +1,
        # BATTER 5/2, BATTER 4/3) that the median rule was dropping.
        if sum(1 for r in fit if r <= FIT_MAX) >= FIT_MIN_DISCS:
            return _read_fan(img, strong)
    return _read_ungated(img, strong)



# ---------------------------------------------------------------------------
# THE SHIELD (the `secondary` field): a white digit on a dark heraldic badge.
#
# Two locators failed before this one. The first hunted DARK blobs and found the
# neighbouring card's power disc (its contact sheet showed 4s and 5s; shields are
# 1-3). The second added a polarity test and over-corrected to 14 badges of 339.
# Both were searching for a thing and hoping.
#
# What works is what already fixed the runners reader: SEARCH for the asset. The
# badge is one sprite -- same outline, same rim, same fill -- so cv2.matchTemplate
# over the card's foot answers both questions at once, is there a badge and which
# digit is in it, without any assumption about where it sits. That matters,
# because the offset is NOT fixed: the cursor lifts a card and the badge rides
# with it, which is why a fixed-offset window measured 8% coverage on 3s.
#
# The templates are the MEAN of 120 / 51 / 135 aligned examples. Averaging that
# many and getting a SHARP digit is itself the evidence that the sprite is fixed.
#
# THE GATE SITS BETWEEN TWO MEASURED POPULATIONS (CLAUDE.md 10.4), peak
# correlation over 1,155 player cards:
#
#     paid says SHIELDED    (n=704)   p01 0.363   p05 0.843   p50 0.928
#     paid says UNSHIELDED  (n=451)   p50 0.381   p95 0.519   p99 0.541
#
# 0.541 -> 0.843 is empty. SHIELD_MIN is its midpoint. The tails that cross it
# are the paid model's own errors, not the reader's -- see below.
#
# Cross-session (templates from the early half of the corpus, scored on the late
# half, so a hand can never score itself): 589 of 600 correct, 98.2%.
#
# ALL TEN REMAINING DISAGREEMENTS WERE ADJUDICATED BY OPENING THE FRAMES, and
# nine of the ten cards HAVE NO BADGE AT ALL -- the paid model invented one. The
# mechanism is measured, not guessed: on the 684 cards where the badge IS found,
# the claimed `secondary` equals the card's own POWER 0 times; on the 20 where it
# is not, 5 times (25%), and every one of those cards has power 5 or 6 and a
# small edge number in its art. The paid model is reading the card frame.
# ---------------------------------------------------------------------------
SHIELD_TEMPLATES = os.path.join(_HERE, "shield_templates.npz")
SHIELD_SIZE = (34, 40)          # the badge, in ANCHOR_W pixels
SHIELD_MIN = 0.69               # the midpoint of the empty band 0.541 .. 0.843
_SHIELD = None


def _shield_templates():
    global _SHIELD
    if _SHIELD is None:
        try:
            z = np.load(SHIELD_TEMPLATES)
            _SHIELD = {int(k): z[k] for k in z.files}
        except Exception:
            _SHIELD = {}
    return _SHIELD


def read_shield(img, cx, cy):
    """(digit, score) for the shield under the power disc at (cx, cy).

    Returns (0, score) when no badge clears SHIELD_MIN -- an unshielded card is a
    real answer, not an abstention, because the two populations are separated.
    Returns (None, 0.0) only when the templates are missing or the crop is too
    small to search, which is the caller's cue to ask the paid model.
    """
    tpl = _shield_templates()
    if not tpl:
        return None, 0.0
    try:
        import cv2
    except Exception:
        return None, 0.0
    s = img.width / ANCHOR_W
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    h, w = g.shape
    x0, x1 = int(max(0, cx - 80 * s)), int(min(w, cx + 40 * s))
    y0, y1 = int(max(0, cy - 10 * s)), int(min(h, cy + 100 * s))
    sub = g[y0:y1, x0:x1]
    tw, th = int(round(SHIELD_SIZE[0] * s)), int(round(SHIELD_SIZE[1] * s))
    if tw < 4 or th < 4 or sub.shape[0] < th or sub.shape[1] < tw:
        return None, 0.0
    best_d, best = None, -1.0
    for d, t in tpl.items():
        tt = cv2.resize(t, (tw, th), interpolation=cv2.INTER_LANCZOS4)
        _, mx, _, _ = cv2.minMaxLoc(cv2.matchTemplate(sub, tt, cv2.TM_CCOEFF_NORMED))
        if mx > best:
            best_d, best = d, float(mx)
    if best < SHIELD_MIN:
        return 0, round(best, 3)
    return best_d, round(best, 3)


# ---------------------------------------------------------------------------
# THE TACTICS BONUS -- and there are TWO SPRITES, not one, which is why the digit
# reader was stuck at 41.8% on this field.
#
#     swing_boost / pitch_boost      a WHITE DISC with a BLACK digit. read_digit
#                                    already reads this one.
#     speed_boost / fielding_boost   a DARK HERALDIC SHIELD with a WHITE digit --
#                                    the same sprite family read_shield reads on
#                                    player cards, at the INVERSE polarity.
#
# Over 465 cards whose slot correspondence with the paid model is PROVEN (both sides
# emit five rows AND agree which slots are tactics -- CLAUDE.md 10.22): swing 137 +
# pitch 65 carry the disc and win their slot on the isolated-digit path every time;
# speed 127 + fielding 136 carry the shield and win it NEVER. This module's own
# docstring says the bonus "sits fused inside the wreath" -- true for the disc cards,
# WRONG for the shield cards, where nothing is fused and the polarity is simply
# inverted, so a dark-ink finder sees the badge as one blob and reads no digit from it.
# 236 of the 272 misses were LOCATED and never read, as a rank-1 candidate whose
# circle is None by construction.
#
# It reads the way the shield and the banner do (10.23): SEARCH for the sprite, because
# the cursor lifts a card and the badge rides with it -- measured at -40 to -43 px in y
# on every cursor-selected card.
#
# CROSS-SESSION (banks from the EARLY half of the corpus, split on a real ~1 h session
# gap; leave-one-out would leak because two hands in one match hold the same cards):
#
#     TRAIN  232 cards   right 229   WRONG 0   unsure 3
#     TEST   233 cards   right 227   WRONG 0   unsure 6      (245/246 with the slot fallback)
#
# Both gates sit in a MEASURED EMPTY BAND (10.4), on the test half:
#     DISC    positives min 0.831   negatives max 0.468   -> band 0.468 .. 0.831
#     SHIELD  positives p05 0.828   negatives max 0.596   -> band 0.596 .. 0.828
#
# AND IT CORRECTS THE PAID MODEL: the three cards it labels "bonus 0" are all FIELDING
# PLAY badges that plainly read 1. Adjudicated by eye on
# agent_progress/bonus-reader/sheet_zero.png -- CLAUDE.md already records that error.
#
# IT IS A BADGE READER, NOT A CARD-TYPE DETECTOR. Applied to a player card it happily
# reads that card's own shield, answering on 325 of 422. Only call it on a row the fan
# has already called tactics.
# ---------------------------------------------------------------------------
BONUS_TEMPLATES = os.path.join(_HERE, "bonus_templates.npz")
BONUS_WIN = (80, 90)            # half-window, anchor-px. Wider only lifts the NEGATIVES,
                                # because the search starts reaching the neighbour's badge.
BONUS_DISC_SIZE = (46, 46)
BONUS_SHIELD_MIN = 0.70
BONUS_DISC_MIN = 0.70
_bonus_bank = None


def _bonus_banks():
    """{"shield": {digit: tpl}, "disc": {digit: tpl}}.

    Shield digits 2 and 3 are borrowed from shield_templates.npz -- the SAME sprite, cut
    from player cards -- because no tactics card in the corpus carries a shield 2 or 3, so
    a bank built from tactics cards alone could only ever answer 1 and could never be
    wrong. Borrowing them is what makes the shield digit a real question.
    """
    global _bonus_bank
    if _bonus_bank is None:
        b = {"shield": {}, "disc": {}}
        try:
            z = np.load(BONUS_TEMPLATES)
            for k in z.files:
                fam, d = k.rsplit("_", 1)
                b[fam][int(d)] = z[k].astype(np.uint8)
        except Exception:
            pass
        for d, t in (_shield_templates() or {}).items():
            b["shield"].setdefault(int(d), np.asarray(t, dtype=np.uint8))
        _bonus_bank = b
    return _bonus_bank


def _bonus_search(g, cx, cy, s, tpls, size):
    import cv2
    h, w = g.shape
    x0, x1 = int(max(0, cx - BONUS_WIN[0] * s)), int(min(w, cx + BONUS_WIN[0] * s))
    y0, y1 = int(max(0, cy - BONUS_WIN[1] * s)), int(min(h, cy + BONUS_WIN[1] * s))
    sub = g[y0:y1, x0:x1]
    tw, th = int(round(size[0] * s)), int(round(size[1] * s))
    if tw < 4 or th < 4 or sub.shape[0] < th or sub.shape[1] < tw:
        return None, -1.0
    bd, bp = None, -1.0
    for d, t in sorted(tpls.items()):
        tt = cv2.resize(t, (tw, th), interpolation=cv2.INTER_LANCZOS4)
        _, mx, _, _ = cv2.minMaxLoc(cv2.matchTemplate(sub, tt, cv2.TM_CCOEFF_NORMED))
        if mx > bp:
            bd, bp = int(d), float(mx)
    return bd, bp


def _bonus_at(g, cx, cy, s, b):
    sd, sp = _bonus_search(g, cx, cy, s, b["shield"], SHIELD_SIZE)
    dd, dp = _bonus_search(g, cx, cy, s, b["disc"], BONUS_DISC_SIZE)
    # The families are INVERSE POLARITY, so the higher peak names the family and the loser
    # is noise: measured, the loser tops out at 0.596 / 0.468 while a winner starts at
    # 0.828 / 0.831.
    if sp >= dp:
        return (sd if sp >= BONUS_SHIELD_MIN else None), sp
    return (dd if dp >= BONUS_DISC_MIN else None), dp


def read_bonus(img, cx, cy, slot=None):
    """(bonus, score) for the tactics card at (cx, cy), or (None, score) when unsure.

    None means NOT READ, never "no bonus".

    Pass `slot` whenever it is known. When no candidate reached a slot, the fan emits the
    row at the PLAYER anchor, ~63px right of where the badge sits, and every such row in
    the corpus is a CURSOR-LIFTED card -- the lift brightens it so the dark-blob finder
    never saw it. All 8 abstain from the player anchor and all 8 read correctly from
    SLOT_TACTICS. The fallback runs ONLY after the first search abstained, so it can never
    overturn an answer.
    """
    try:
        import cv2  # noqa: F401
    except Exception:
        return None, 0.0
    b = _bonus_banks()
    if not b["shield"] or not b["disc"]:
        return None, 0.0
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    s = img.width / ANCHOR_W
    val, sc = _bonus_at(g, cx, cy, s, b)
    if val is None and slot is not None and 0 <= slot < len(SLOT_TACTICS):
        ax, ay = SLOT_TACTICS[slot][0] * s, SLOT_TACTICS[slot][1] * s
        if abs(ax - cx) > 8 * s or abs(ay - cy) > 8 * s:
            v2, s2 = _bonus_at(g, ax, ay, s, b)
            if v2 is not None:
                return v2, round(s2, 3)
    return val, round(sc, 3)

def _read_fan(img, strong):
    s = img.width / ANCHOR_W
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    taken = [(c[0], c[1]) for c in strong]
    # rank 3, an isolated digit: the only source whose crop is the geometry the templates
    # were cut at. rank 2, the bare white disc. rank 1, a fused wreath, which carries no
    # readable digit of its own.
    cands = [(3, (c[3], c[2]), c[0], c[1], (c[0], c[1], c[2])) for c in strong]
    for x, y, area, box in _white_discs(g):
        if _free(x, y, taken):
            taken.append((x, y))
            cands.append((2, (area, 0), x, y, _digit_in_disc(g, box)))
    for t in find_tactics(img):
        if _free(t["x"], t["y"], taken):
            taken.append((t["x"], t["y"]))
            cands.append((1, (0, 0), t["x"], t["y"], None))

    best = [None] * 5
    wreath = [None] * 5          # rank-1 candidates kept aside, for the promotion below
    for rank, key, x, y, circle in cands:
        cost, i, kind = _slot(x, y, s)
        if cost > SLOT_TOL * s:
            continue
        if rank == 1 and (wreath[i] is None or -cost > wreath[i][0][2]):
            wreath[i] = ((rank, key, -cost), x, kind, circle, y)
        if best[i] is None or (rank, key, -cost) > best[i][0]:
            best[i] = ((rank, key, -cost), x, kind, circle, y)

    # THE CURSOR'S OWN HALO CAN COUNTERFEIT A POWER DISC, AND IT OUTRANKED THE REAL CARD.
    # Measured 2026-09-11 on a blind labelled batch: with the cursor sitting on slot 0, a
    # bright round blob appears at (220,168) that find_circles accepts as a disc, r=22. It
    # is rank 3 (a strong disc) so it beat the tactics wreath at rank 1, and slot 0 -- a
    # SPEED BOOST -- was read as a PLAYER card at y=168 instead of a tactics card at 205.
    # Wrong kind chose the wrong anchor table, 168 then looked like a 35px rise, and the
    # card was reported SELECTED when nothing was. That is the first time a reader claimed
    # a selection that did not exist, which is the direction that costs a card.
    #
    # The banner knew: read_tactics_type scored 0.968 on that very slot, in that very
    # frame. The code never asked, because it only ever demoted tactics -> player.
    #
    # So a STRONG banner promotes the slot back -- and takes the WREATH's position with it,
    # because fixing the kind alone leaves y on the counterfeit disc and the card still
    # reads as raised. Measured over 260 hands at the slot anchor: slots read as PLAYER
    # score at most 0.695, slots read as TACTICS have a median of 0.938. The promotion bar
    # sits above every observed player slot, and is deliberately stricter than
    # TACTICS_PRESENT_MIN (0.58) because this overrides a disc that was actually found.
    for i in range(5):
        if best[i] is None or wreath[i] is None or best[i][2] == "tactics":
            continue
        _t, _ts = read_tactics_type(img, i)
        if _ts >= TACTICS_PROMOTE_MIN:
            best[i] = wreath[i]
    # SECOND PASS for slots nothing reached: a SELECTED tactics card is too bright for the
    # first pass. Only slots still empty are filled, so an existing reading cannot change.
    if any(b is None for b in best):
        for t in find_tactics(img, dark_max=SELECTED_DARK_MAX):
            if not _free(t["x"], t["y"], taken):
                continue
            cost, i, kind = _slot(t["x"], t["y"], s)
            if cost > SLOT_TOL * s or best[i] is not None:
                continue
            taken.append((t["x"], t["y"]))
            best[i] = ((1, (0, 0), -cost), t["x"], kind, None, t["y"])

    out = []
    for i in range(5):
        if best[i] is None:
            # A slot no candidate reached. It is emitted anyway -- when the fan fits the
            # hand HAS five cards -- with no digit, which the caller reads as "ask the API".
            # WHAT KIND IS A SLOT NOTHING REACHED? This branch used to answer
            # "tactics", unconditionally, and that is a fabricated reading rather than a
            # missing one: over the corpus it emits 17 rows and the paid model calls 10
            # of them PLAYER and 7 tactics, so the default was wrong more often than a
            # coin. It accounted for 10 of the 13 kind disagreements on the whole corpus,
            # and it is the shape CLAUDE.md 10.1 names -- a no-op path whose output is
            # indistinguishable from a real answer.
            #
            # The banner decides instead, and when the banner is not there the honest
            # answer is UNKNOWN. On those 17 rows the two populations are far apart:
            # really-player scores top out at 0.560 while really-tactics bottom out at
            # 0.936 in sample, 0.595 across sessions.
            t, ts = read_tactics_type(img, i)
            if ts < TACTICS_PRESENT_MIN:
                # No candidate AND no banner. Something is in this slot -- the fan only
                # emits five rows when it fits -- but nothing here can say what, so the
                # caller must ask the paid model rather than be handed a guess.
                # y HERE IS A SLOT CONSTANT, NOT A MEASUREMENT. Nothing reached this
                # slot, so there is no measured position to report -- and on slot 0 the
                # constant equals the card's own resting position, so a LOST card read as
                # a perfectly stable one. That is what hid a selected tactics card moving:
                # The row fell through to here, so the lift check would have compared a
                # constant with itself and could never fire (CLAUDE.md 10.1). Flagged so
                # a caller that needs a real position can refuse instead of being handed
                # furniture.
                #
                # THIS USED TO SAY "find_tactics stops matching a card once it is
                # selected", and that claim was used on 2026-09-16 to explain a discard
                # failure. It does not hold: a controlled test that same day pressed
                # select_card once on a PITCH FOCUS and read it back as
                # kind='tactics', type='pitch_boost', y measured, rise 43 px against a
                # 25 px gate -- comfortably visible, not marginal. The discard failure
                # was a DROPPED PRESS. The claim is removed rather than softened,
                # because its only recorded use was to explain something it did not
                # cause.
                out.append({"x": int(SLOT_PLAYER[i][0] * s), "kind": "unknown",
                            "digit": None, "score": 0.0, "y_measured": False,
                            "y": int(SLOT_PLAYER[i][1] * s)})
                continue
            # AND THE BINARY, which this branch used to leave unset -- so a row whose
            # TYPE was known still reported adds_power as "ask the paid model". It made
            # the easier question abstain MORE often than the harder one (7.6% against
            # 5.9% over the corpus), which is the wrong way round by construction.
            ap, aps = reads_adds_power(img, i)
            out.append({"x": int(SLOT_PLAYER[i][0] * s), "kind": "tactics", "digit": None,
                        "score": 0.0, "type": t, "type_score": round(ts, 3),
                        "adds_power": ap, "adds_power_score": round(aps, 3),
                        "y_measured": False,          # see the note above: a slot constant
                        "y": int(SLOT_PLAYER[i][1] * s)})
            continue
        _, x, kind, circle, cy = best[i]
        if kind == "tactics":
            # POSITION SAID TACTICS. ASK THE CARD. A slot at the tactics anchor whose
            # banner cannot be found is a player card sitting where a tactics card
            # usually sits -- see TACTICS_PRESENT_MIN above.
            _t, _present = _best_banner(img, i, x, cy)
            if _present < TACTICS_PRESENT_MIN:
                kind = "player"
        digit, sc = read_digit(img, circle) if circle else (None, 0.0)
        # y_from SAYS WHICH ASSET THE Y CAME FROM. It used to be implicit, and
        # selected_cards compares y against the DISC anchor -- so a y taken from
        # anywhere else produced a confident "not selected" rather than an
        # abstention. A caller can now tell the two apart.
        row = {"x": x, "kind": kind, "digit": digit, "score": round(sc, 3),
               "y": int(cy), "y_measured": True, "_slot_i": i,
               "y_from": "disc" if circle else "fallback"}
        if kind == "player":
            # hand_to_cards() requires `secondary` on every player card, so this
            # is read here rather than left for the caller to ask the API for.
            row["secondary"], ss = read_shield(img, x, cy)
            row["secondary_score"] = ss
        if kind == "tactics":
            # The type is what decides play, so it is read here and NEVER guessed.
            row["type"], ts = read_tactics_type(img, i, x, cy)
            row["type_score"] = round(ts, 3)
            # AND THE QUESTION THE DECISION ACTUALLY ASKS, which is easier and therefore
            # answered more often: does this card add power at all?
            row["adds_power"], aps = reads_adds_power(img, i, x, cy)
            row["adds_power_score"] = round(aps, 3)
            # hand_to_cards() indexes c["bonus"] on every tactics card, so it is read here
            # rather than left for the paid model.
            row["bonus"], bs = read_bonus(img, x, cy, slot=i)
            row["bonus_score"] = bs
        out.append(row)

    # A RAISED CARD'S DISC SHRINKS OUT OF DISC_MIN_R, so a SELECTED card's power could
    # not be read at all. Measured on one card in one hand, at rest and selected:
    #
    #     at rest    thr 110/90/130   disc r=20   reads '5' at 0.958
    #     SELECTED   thr 110          NO circle
    #                thr 130          r=13  -- under DISC_MIN_R 18, rejected
    #                thr 150          r=19  reads '5' at 0.969
    #
    # The card BRIGHTENS when selected, so the dark-threshold fit shrinks. Adding 150 to
    # DARK_THRESHOLDS globally is NOT the fix: over the 540 hands in overnight/local_hand
    # it gained 3 digits, LOST 1, and pushed one hand off the fan fit entirely into the
    # ungated path. So it runs per-slot, only where a digit is missing AND the card is
    # raised -- it can add a reading and cannot change one.
    # ...AND THAT GATE COULD NOT FIRE (fixed 2026-09-20). It asked whether the row
    # was ALREADY raised, using row["y"] -- which, when the disc is the thing that
    # was missed, is the SHIELD's y, about 66 px BELOW the anchor. The apparent rise
    # is then NEGATIVE, the gate reads "not raised", and the pass is skipped in
    # exactly the state it was written for. Measured live on a selected slot 0:
    #
    #     row y = 261 (shield)   apparent rise -66 px against a 25 px gate -> skipped
    #     true disc y = 154      true rise      +41 px                     -> would run
    #     over 25 static frames  disc found 0/25 shipped, 25/25 at RAISED_DARK_MAX
    #     selected_cards()       said "nothing selected" on 17 of those 25 frames
    #
    # The row's own y cannot decide this, because the disc position is what is being
    # established. So the pass now runs whenever a PLAYER slot has no digit, and
    # searches that slot's x column for a disc AT OR ABOVE the anchor -- a raised
    # card rises, so nothing below the anchor can be one.
    #
    # EVERY SAFETY PROPERTY ABOVE SURVIVES. Per-slot, only where a digit is missing,
    # still gated by DISC_MIN_R / DISC_MIN_REACH and by read_digit, so it can add a
    # reading and cannot change one. The shield does not survive those gates
    # (measured r=16, reach=4.0 against 18 and 6) and card art does not survive
    # read_digit (0.43-0.47 against a real disc's 0.99). DARK_THRESHOLDS is NOT
    # touched -- see the paragraph above for why raising it globally was rejected.
    from circle_finder import find_circles as _find_circles
    for r in out:
        if r.get("kind") != "player" or r.get("digit") is not None:
            continue
        x = r.get("x")
        i = r.get("_slot_i")
        if x is None or i is None or not (0 <= i < len(SLOT_PLAYER)):
            continue
        _anchor_y = SLOT_PLAYER[i][1] * s
        for c in _find_circles(img, RAISED_DARK_MAX):
            if abs(c[0] - x) > 25 * s:
                continue
            if c[1] > _anchor_y + 25 * s:
                continue              # below the anchor: a raised card cannot be there
            if c[2] < DISC_MIN_R or c[3] < DISC_MIN_REACH:
                continue
            d, sc2 = read_digit(img, (c[0], c[1], c[2]))
            if d is not None:
                r["digit"], r["score"] = d, round(sc2, 3)
                r["digit_from_raised_pass"] = True
                # THE Y NOW MEANS THE DISC, which is what selected_cards compares
                # against. Without this the digit was recovered and the row still
                # reported the shield's position, so the card read as NOT selected.
                r["y"], r["y_from"] = int(c[1]), "disc"
            break

    return out


def _read_ungated(img, strong):
    """What shipped before the fan: every disc found anywhere, in x order."""
    out = []
    for c in strong:
        d, s = read_digit(img, c)
        # NOT "player". Off the fan there is no positional evidence of kind, and
        # claiming it read a tactics card as a batter -- see KNOWN GAPS above.
        out.append({"x": c[0], "kind": "unknown", "digit": d, "score": round(s, 3)})
    for t in find_tactics(img):
        if all(abs(t["x"] - o["x"]) > 20 for o in out):
            out.append({"x": t["x"], "kind": "tactics", "digit": None, "score": 0.0,
                        "type": None, "y_measured": False})
    out.sort(key=lambda r: r["x"])
    return out


# ==========================================================================
# WHERE IS THE CURSOR, AND WHICH CARD IS ACTUALLY SELECTED
# ==========================================================================
# select_and_play() used to send eight BLIND presses -- home four left, walk
# N right, select, confirm -- and never look at the screen. On 2026-09-10 a
# swallowed move_right played a power-4 instead of a power-6, and the frame
# captured at the instant of that press shows the cursor sitting at index 0
# while the code believed 2. The same swallowed press one step later eats
# `select_card` instead, confirm_play fires into nothing, and the loop stalls
# ~35 s waiting for a deal that is never coming. One bug, two faces.
#
# THE GAME ANSWERS BOTH QUESTIONS ON SCREEN, and with two DIFFERENT signals
# (the user, watching the stream, 2026-09-10):
#
#     the cursor HOVERING a card  ->  the card GLOWS   (a white halo on its rim)
#     the card being SELECTED     ->  the card LIFTS   (it rises up the screen)
#
# so "where is the cursor" and "did the select land on the card I meant" are
# separate measurements, and the second one is the one that guards the
# irreversible press.
#
# THE FIRST VERSION OF THIS WAS SCORED AGAINST A CENSUS IT LABELLED ITSELF, and
# that is the whole reason the numbers below are the user's and not mine. It read
# 4 of 9 on a labelled sweep: 5/5 on player cards and 0/4 on TACTICS cards, whose
# halo it could not see at all. Every frame it could not read went into the
# "no cursor" pile -- so the negative population was built entirely out of the one
# class the detector was blind to, and scoring against it reported healthy headroom.
# CLAUDE.md 31, the same shape as the DRAW! screens topping the result reader's
# negatives. A census cannot discover a class its own labeller does not have.
#
# WHAT FIXED IT WAS GROUND TRUTH: the user parked the cursor on each slot in turn
# and named it, while a sweep captured a frame after every press (2026-09-10,
# test_fixtures/hand_cursor/sweep_f*_slot*.png, truth in each filename).
#
# TWO GEOMETRY ERRORS, both found by the user looking at the box drawn on a frame:
#   * IT WAS CENTRED ON THE DISC, and the disc sits on the card's RIGHT side, so
#     the box reached across into the NEIGHBOUR. What was documented here as
#     "the halo spills onto the left neighbour, 3.7-4.8%" was never a property of
#     the halo -- it was this box reading the next card along. The box now sits
#     LEFT of the disc (x-110 .. x-10) and that number is gone.
#   * IT SAT TOO HIGH, in the background above the cards rather than on the rim.
# A fixed offset cannot serve both card types: a tactics card's disc sits much
# closer to its own top edge than a player card's does. The window below is the
# one geometry, of 18 that pass, with the widest margin over all 12 labelled frames.
#
# MEASURED at this geometry over those 12 frames (9 the user labelled by slot,
# plus 3 earlier ones):
#
#     the card the cursor is on      9.1 - 16.1 %      argmax correct 12 of 12
#     every other card               0.0 -  6.2 %
#     a frame with NO cursor lit      0.0 %            n = 1
#
# THE GATE SITS BETWEEN THOSE TWO, AND THE FIRST VERSION DID NOT. It was set to 3.0
# and justified here as "a floor under the positives with 2x margin" -- true, and
# irrelevant: what decides a gate is the CEILING OF THE FALSE READINGS, which is 6.2
# and which I had not computed (CLAUDE.md 10.4, quoted in this same file hours
# earlier). The cost was live: a tactics card whose own white artwork reads a
# constant 6.1-6.5 in its box was named "the cursor" the moment the real cursor's
# card was selected and lifted out of its own box, and the loop then pressed
# select_card onto the card it had just selected, toggling it off.
#
# 7.5 sits between the 6.2 ceiling and the 9.1 floor. It is still not the
# load-bearing check -- argmax is, and the LIFT is what guards the irreversible
# press -- but it is now a separation rather than a floor.
#
# THE LIFT IS THE STRONGER SIGNAL BY A WIDE MARGIN: measured live, the selected card
# rose 44 px while every other card moved 0-1 px. That is why the lift, not the glow,
# gates confirm_play.
# EVERY OFFSET BELOW IS IN ANCHOR_W UNITS AND IS SCALED BY THE CAPTURE, exactly as
# SLOT_PLAYER / SLOT_TACTICS are. They were written as raw pixels first, which is a trap
# this project has already paid for: CLAUDE.md section 3 records one session producing both
# 1867x1050 and 1920x1080 captures, where every fixed region silently landed on the wrong
# thing. The user, 2026-09-10: "don't use exact pixels because that will screw you over the
# moment it's on a different screen."
# THE GATE WAS REJECTING CORRECT ANSWERS, AND THE "NEGATIVE POPULATION" IT GUARDED
# AGAINST WAS A FRAME I MISLABELLED. Settled 2026-09-11 against 54 frames the user
# labelled blind, plus one more they adjudicated by eye:
#
#     argmax alone                        55 / 55   including slot 0 at 8/8
#     argmax gated at 7.5                 47 / 55   every miss is slot 0
#
# Slot 0 reads 2.7-4.4 when the cursor is on it, where every other slot swings 0 -> 12-18.
# It is the leftmost card, rotated hardest by the fan, and its rim barely enters the
# window -- so on that slot argmax is right BY ELIMINATION (the others read ~0) rather
# than by detecting anything. That is worth knowing, but it is still right.
#
# I reported an OVERLAP here and it was an artefact: the frame I used as "nothing lit" was
# filed that way because THIS DETECTOR ABSTAINED ON IT, and the user looked and said the
# cursor is plainly on slot 0. CLAUDE.md 31, committed by me while quoting it. Corrected,
# there is no measured negative population at all: across 54 labelled turn frames, ZERO
# have no cursor. During a turn the cursor is always somewhere.
#
# So this is a FLOOR under the positives, not a separation, and it is honest to say so:
# 1.5 sits under the faintest true reading (2.70) with margin, and the real protection
# against an unreadable screen is upstream -- the row count and y_measured checks in
# input_controller._look_settled, which reject a frame the fan could not fit at all.
# ARGMAX is the load-bearing check; this only stops a black frame naming a slot.
# ALL OF WHICH WAS THE WINDOW, NOT THE CURSOR (2026-09-11, the user watching the stream:
# "should you move slot 0's box down a little more? it's barely covering it").  The window
# sat 70-30 anchor px ABOVE the disc, which is the BACKDROP; what it actually measured was
# how much of a card's own white top rim happened to fall inside, and that tracks how HIGH
# the card sits.  So a SELECTED card -- raised ~44 px -- out-read the card holding the
# cursor, the backdrop behind slot 4 read 9.7 where the true cursor read 7.5, and the turn
# refused.  Dropped onto the rim where the halo actually is (55-35), over 74 labelled
# frames -- 56 the user labelled BLIND plus the 18 curated fixtures:
#
#     window            argmax    true cursor card    every other card      gap
#     110,10,70,30       74/74        8.7 .. 36        0.0 ..  9.7        -1.0  OVERLAP
#      80, 0,55,35       74/74       20.7 .. 36.1      0.0 ..  8.4       +12.3
#
# Chosen leave-one-fold-out over all seven folds; every fold scored 74/74 on its held-out
# frames, and the by-slot true floors are s0 21.4 / s1 25.2 / s2 21.0 / s3 24.8 / s4 20.7.
# AND THE CURATED FIXTURES ARE WHY THE FOLDS ARE HONEST: an earlier pick (80,20,55,40) won
# all six folds of the 56 blind frames and then read 3.4 on sweep_f00, whose cursor is
# plainly on slot 2 -- it was in no fold.  CLAUDE.md's at_table lesson exactly.
# 2026-09-15: RE-MEASURED AT THIS GEOMETRY. The 15.0 was right for a corpus this
# rig no longer produces, and the number it rested on is the one that moved.
#
# THE FAILURE. Mid-match the cursor sat plainly on a card and every action refused:
#
#     live glow    [0.0, 0.1, 0.0, 12.4, 0.0]     argmax unambiguous, 100x margin
#     gate         15.0                            -> REFUSED, twice in two matches
#
# THE CENSUS (tools/glow_census.py, tools/glow_zone.py), over 2,535 slot readings
# from 507 archive frames at the CURRENT 979 px crop -- the recordings come from
# the frame dump, i.e. the decoded stream, so they carry this rig's geometry:
#
#     FALSE (the four unlit slots)  n=2028   p50 0.0   p99 1.2   MAX  2.0
#     TRUE  (the lit slot)          n= 507   min 20.1  p50 23.9  MAX 53.7
#     live true, n=1                                        12.4
#
# TWO CORPORA, AND THEY DISAGREE ABOUT THE FALSE CEILING. 15.0 was justified as
# "BETWEEN two measured populations: 8.4 and 20.7" on the 12 curated 1020 px
# fixtures -- which are USER-LABELLED, the only ground truth here, and on them a
# non-cursor card reaches 8.4. At 979 px the false population tops out at 2.0
# over 2,028 readings. The fixtures are the stricter corpus and they are not
# discarded just because the rig moved: section 3 requires a reader to be checked
# at BOTH geometries.
#
# So the gate must clear 8.4 AND admit 12.4, which leaves (8.4, 12.4) and almost
# no room. 10.0 is the midpoint, 1.19x above the highest false reading ever
# labelled and 1.24x below the lowest true one ever observed.
#
# A FIRST ATTEMPT AT 5.0 WAS WRONG AND THE SUITE CAUGHT IT. It was set from the
# 979 px false MAX of 2.0 alone, and test_verified_selection failed it against
# the fixtures' 8.4 -- a cursorless frame there tops out at 7.8, so 5.0 would
# have NAMED A CARD on a frame with no cursor on it. The floor is applied to the
# ARGMAX, so it only bites when the argmax is itself a false reading, and that is
# exactly the case it exists for. The census that said 2.0 could not see it
# because that corpus has no such frame.
#
# TWO LIMITS, STATED RATHER THAN HIDDEN.
#
# (1) THE TRUE FLOOR IS NOT PROPERLY MEASURED. The label here is "one slot beats
#     every other by 10x", which scores the ABSOLUTE value while labelling by the
#     RATIO -- different quantities, so the gate is not fitted to its own output
#     -- but it CANNOT sample a dim true card by construction (10.31's missing
#     class). Everything below 20 rests on the single live 12.4. A run that logs
#     the glow vector on every turn is what closes this, and costs nothing.
#
# (2) NO GATE PROTECTS AGAINST A MID-ANIMATION FRAME, and the control says so.
#     Over the 259 frames the confident label EXCLUDED -- which is exactly where
#     two bright slots would hide -- the RUNNER-UP glow runs p50 7.1, p99 13.6,
#     MAX 23.1. At a gate of 5.0, 57.9% of those frames have TWO slots clearing
#     it; even at 15.0, 1.2% do. So the floor was never the thing keeping a
#     moving hand from naming the wrong card, and raising it back would not make
#     that safe. What does is reading the cursor on a SETTLED hand -- which is
#     what the deal gate exists to deliver -- and the ARGMAX plus its margin,
#     not this floor, staying the load-bearing check.
#
# (3) THE MARGIN IS THIN, 1.19x and 1.24x, and that is the honest state rather
#     than a comfortable one. It is thin because the true side rests on ONE live
#     reading; logging the glow vector every turn is what widens it, and until
#     then a true card that reads under 10.0 refuses again.
CURSOR_GLOW_MIN = 10.0         # between 8.4 (fixture false MAX) and 12.4 (live true)
# CURSOR_GLOW_MAX -- A CEILING, NOT A FLOOR (I-25, 2026-09-20). CURSOR_GLOW_MIN answers
# "is anything lit at all"; nothing above it ever asked "is this reading even PLAUSIBLE
# as a cursor halo". CLAUDE.md 10.35 measured why a ceiling is needed: "any box placed
# ON a card reads 60-88% bright whether or not the cursor is there", because the cards
# are white cartoon art and the glow window is brightness-only. `cursor_slot`'s own
# docstring gives the TRUE population over 74 labelled frames: 20.7 .. 36.1. Reproduced
# live on test_fixtures/hand_reads/i25_false_cursor_slot0_live_20260920.png -- slot 0's
# disc finder locked onto a blob low on the card (its digit never read and its y sat at
# 259 against the fan's measured 139-205) and its glow window landed ON the card,
# scoring 68.6; the TRUE cursor at slot 4 read 22.8, inside the docstring's 20.7-36.1.
# No sweep of this specific window's false-on-card population is on disk (grepped
# test_fixtures/ and agent_progress/ for a glow census json -- none exists; tools/
# glow_census.py measures a DIFFERENT quantity, lift-labelled glow at CURSOR_GLOW_MIN's
# geometry, not this ceiling), so the two anchors above -- 36.1 true max, 60 on-card min
# -- are what CLAUDE.md 10.35 and cursor_slot's docstring actually measured, and the gate
# is their midpoint: 36.1 + (60 - 36.1) / 2 = 48.05, rounded to the whole number below it
# so the true side keeps its full margin.
CURSOR_GLOW_MAX = 48.0
GLOW_WHITE = 190               # a grey level, so NOT scaled
GLOW_XL, GLOW_XR = 80, 0       # the box sits on the card's own top-left RIM, where the
GLOW_DY0, GLOW_DY1 = 55, 35    # halo shows -- NOT in the backdrop above it
SELECT_LIFT_MIN_PX = 6         # measured 44 px of lift at reference scale, 0-1 px on the rest


def cursor_glow(hand_img, rows=None, _boxes=None):
    """(cursor_index or None, glow % per card, rows) for a hand crop.

    None means NOT READ -- nothing is lit clearly enough to act on. The caller
    must refuse to press rather than guess; a wrong guess here plays the wrong
    card in a $50 match, which is the exact failure this exists to stop.
    """
    rows = read_hand(hand_img) if rows is None else rows
    g = np.asarray(hand_img.convert("L"), dtype=float)
    sc = hand_img.width / ANCHOR_W          # the same scale the slot anchors use
    xl, xr = GLOW_XL * sc, GLOW_XR * sc
    dy0, dy1 = GLOW_DY0 * sc, GLOW_DY1 * sc
    # EVERY DISC IS MAPPED INTO ONE REFERENCE FRAME BEFORE ANY BOX IS PLACED OR BOUNDED.
    # `x` is the DISC, and a TACTICS disc sits 60-83 px LEFT of a player disc in the same
    # slot (SLOT_TACTICS, :215), so raw disc x means different things for the two kinds.
    # Live on 2026-09-11 a tactics card at slot 1 sat 93 px from its player neighbour
    # instead of ~180: the midpoint bound crushed its box 104 -> 36 px, left the halo
    # entirely, and read 7.5 where the true cursor card reads 10.3-19.1. The selected
    # card won the argmax and the turn refused. Scored over the 54 blind-labelled frames
    # plus that frame: raw x 54/55 with the true population reaching DOWN to 2.9;
    # canonical 55/55 with the true floor at 10.3 and every unselected false read <= 5.5.
    # THE SLOT TABLES HOLD FIVE ENTRIES AND read_hand CAN RETURN MORE ROWS THAN THAT.
    # _read_ungated appends one row per strong disc PLUS one per unmatched tactics blob and
    # is unbounded, so a frame that fools it into six rows indexed SLOT_PLAYER[5] and raised
    # IndexError -- a regression this comprehension introduced on 2026-09-11. selected_cards
    # already had the bound (`if i >= len(SLOT_PLAYER): break`); this one did not. A row past
    # the fan gets x None, which reads 0.0 and can never be named the cursor.
    xs = [None if r.get("x") is None or i >= len(SLOT_PLAYER) else
          r["x"] + (SLOT_PLAYER[i][0] -
                    (SLOT_TACTICS if r.get("kind") == "tactics" else SLOT_PLAYER)[i][0]) * sc
          for i, r in enumerate(rows)]
    glow = []
    for i, r in enumerate(rows):
        x, y = xs[i], r.get("y")
        # A ROW WHOSE y WAS NEVER MEASURED CANNOT ANCHOR THIS BOX. Its y is a slot
        # constant, so the window would sit wherever the card USED to be.
        if x is None or y is None or r.get("y_measured") is False:
            glow.append(0.0)
            if _boxes is not None:
                _boxes.append(None)
            continue
        # EACH CARD OWNS THE BAND BETWEEN THE MIDPOINTS TO ITS NEIGHBOURS, so a box can
        # never sample a neighbouring card. Without this bound a SELECTED card, which
        # rises 44 px, puts its bright rim exactly where the next slot's box sits: live
        # on 2026-09-10 slot 2 read 20.5% off slot 1's raised card and was named "the
        # cursor", while the user watching the screen could see only slot 1 lit. The
        # walk then believed it was already at the tactics slot and skipped its move.
        # Measured over the nine labelled sweep frames, the bound leaves the true
        # readings untouched and collapses the highest FALSE reading 6.2 -> 0.5.
        left = (xs[i - 1] + x) / 2 if i > 0 and xs[i - 1] is not None else 0
        right = (x + xs[i + 1]) / 2 if i + 1 < len(xs) and xs[i + 1] is not None else g.shape[1]
        x0, x1 = int(max(left, x - xl)), int(min(right, x - xr))
        if x1 <= x0:
            glow.append(0.0)
            if _boxes is not None:
                _boxes.append(None)
            continue
        y0b, y1b = max(0, int(y - dy0)), max(0, int(y - dy1))
        if _boxes is not None:
            # the windows actually sampled -- a test asserts THESE scale, because the
            # ANSWER does not change until the box has moved far enough to miss the
            # halo entirely, so an outcome-only check cannot see the scaling break.
            _boxes.append((x0, y0b, x1, y1b))
        p = g[y0b:y1b, x0:x1]
        glow.append(round(float((p > GLOW_WHITE).mean() * 100), 1) if p.size else 0.0)
    if not glow:
        return None, glow, rows
    # THE ARGMAX MUST NOT WIN ON A ROW WHOSE DISC WAS FOUND BUT NEVER READ A DIGIT
    # (I-25). y_from == "disc" means a circle sized and positioned like a real digit
    # disc WAS found there, so the box is anchored on it -- but digit is None means
    # nothing on it matched a digit template, which read_hand's own docstring already
    # names as one reading of "a card element". The fixture this fixes is exactly
    # that: slot 0's disc finder locked onto a blob low on the occluded card, never
    # read a digit off it, and the box it anchored scored 68.6 -- the highest slot on
    # screen, while the real cursor at slot 4 read 22.8. A row with NO disc read at
    # all (y_from == "fallback", where digit is always None) is untouched by this --
    # every tactics-slot-0 fixture on disk wins the argmax that way and must keep
    # doing so (tactics_selected_slot0.png, cursor_on_slot0_faint.png, ...).
    # `eligible` is a SEPARATE array so the raw `glow` returned to the caller for
    # diagnostics is unchanged.
    eligible = [
        g if (g <= CURSOR_GLOW_MAX and not (r.get("y_from") == "disc" and r.get("digit") is None))
        else 0.0
        for g, r in zip(glow, rows)
    ]
    i = int(np.argmax(eligible))
    return (i if eligible[i] >= CURSOR_GLOW_MIN else None), glow, rows


def cursor_slot(glow, lifted, exclude=None):
    """Which slot the cursor is on, from every card's glow. None means NOT READ.

    ONE RULE: the brightest card, if it clears CURSOR_GLOW_MIN and does not clear
    CURSOR_GLOW_MAX (I-25) -- a box that lands ON a card's own white art reads
    60-88% (CLAUDE.md 10.35) and must not win, because this function sees only the
    raw glow numbers `cursor_glow` returns for diagnostics, never the rows, so the
    digit/y_from check `cursor_glow` applies to its OWN argmax cannot run again
    here; the ceiling is what still catches the same false reading at this layer,
    which is the one `input_controller._walk_cursor_to` actually navigates by.

    `exclude` is a set of indices to treat as unlit regardless of their glow --
    for a slot `_walk_cursor_to` has confirmed is a FALSE cursor (pressed toward
    and away from with the reading never changing), so a walk can route around it.

    Two further rules lived here -- subtract the SELECTED cards, then require the winner to
    beat its runner-up by 2.0x -- and BOTH were describing a badly placed window rather
    than the screen. That window sampled the backdrop above each card and caught the card's
    own white top rim, so "glow" tracked how HIGH a card sat and a selected card, raised
    ~44 px, out-read the card holding the cursor; this docstring used to cite 14.8 on a
    merely-selected card as the reason. With the window on the rim, a selected card that
    is NOT hovered reads at most 5.7. There is nothing left for either rule to fix, and
    both cost real answers: the subtraction alone turned a live frame whose cursor sat on
    the one selected card into "the cursor is on slot 1", reading 4.5 off dark backdrop.

    Measured over 74 labelled frames (56 blind + 18 curated), window (80, 0, 55, 35):

        the card with the cursor          20.7 .. 36.1
        every other card                   0.0 ..  8.4     (selected ones at most 5.7)
        argmax + the gate                 74 / 74

    `lifted` is accepted because two call sites pass it and is deliberately UNUSED; the
    measurement above is why. Delete the argument only with those call sites.
    """
    if not glow:
        return None
    exclude = exclude or ()
    eligible = [g if (i not in exclude and g <= CURSOR_GLOW_MAX) else 0.0
                for i, g in enumerate(glow)]
    i = int(np.argmax(eligible))
    return i if eligible[i] >= CURSOR_GLOW_MIN else None


# WHICH CARDS ARE SELECTED, WITHOUT A BASELINE. lifted_cards needs a before/after pair,
# so every caller had to reach a clean board first -- and a baseline taken while something
# was already selected quietly made a lifted card the "resting" position, which cost two
# sweeps tonight. The fan already knows where a card RESTS: its slot anchor. Measured over
# the nine labelled sweep frames, anchor_y minus measured y is
#
#     at rest, every slot      -6.4 .. 9.1
#     a SELECTED card          43.1 and 51.7
#
# 34 points of empty band, so the gate sits between two measured populations (10.4) and the
# loop can start from ANY state -- including one with cards already selected, which is the
# robustness the user asked for.
SELECTED_MIN_RISE = 25         # in ANCHOR_W units; between the 9.1 rest ceiling and 43.1


def selected_cards(rows, scale):
    """Slots whose card is RAISED above its own fan anchor -- i.e. selected."""
    out = []
    for i, r in enumerate(rows):
        if i >= len(SLOT_PLAYER):
            break
        y = r.get("y")
        if y is None or r.get("y_measured") is False:
            continue
        # A PLAYER ROW WHOSE Y DID NOT COME FROM THE DISC CANNOT ANSWER THIS, and
        # saying "not selected" is a wrong answer rather than a missing one. When the
        # disc is missed the y is the SHIELD's, ~66 px BELOW the disc anchor, so the
        # comparison below reports a SELECTED card as unselected every time --
        # measured 17 of 25 static frames before the raised pass was repaired.
        if r.get("kind") != "tactics" and r.get("y_from") == "fallback":
            continue
        table = SLOT_TACTICS if r.get("kind") == "tactics" else SLOT_PLAYER
        if (table[i][1] * scale) - y >= SELECTED_MIN_RISE * scale:
            out.append(i)
    return out


def lifted_cards(y_before, y_after, scale=1.0):
    """Indices that ROSE by at least SELECT_LIFT_MIN_PX -- i.e. got selected.

    `scale` is the capture scale (img.width / ANCHOR_W). The gate is an offset in
    ANCHOR_W units, so a smaller capture needs a proportionally smaller gate or a real
    lift stops counting as one.
    """
    gate = SELECT_LIFT_MIN_PX * scale
    out = []
    for i in range(min(len(y_before), len(y_after))):
        a, b = y_before[i], y_after[i]
        if a is not None and b is not None and (a - b) >= gate:
            out.append(i)
    return out
