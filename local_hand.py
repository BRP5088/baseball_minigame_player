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


def find_tactics(img):
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
    lab, n = _ndi.label(g <= 110)
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


def tactics_banner_vector(img, slot, cx=None, cy=None):
    """The normalised banner patch, or None when it falls off the crop.

    `cx`/`cy` are the card's FOUND position. Pass them whenever they are known: the
    slot anchor is only a fallback, and cropping at it costs more than half the
    coverage, because the cursor lifts a card and its banner rides with it.
    """
    if cx is None or cy is None:
        if not (0 <= slot < len(SLOT_TACTICS)):
            return None
        sc = img.width / ANCHOR_W
        cx, cy = SLOT_TACTICS[slot][0] * sc, SLOT_TACTICS[slot][1] * sc
    return _banner_at(img, cx, cy, 0, 0)


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
        if fit[len(fit) // 2] <= FIT_MAX:
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
    for rank, key, x, y, circle in cands:
        cost, i, kind = _slot(x, y, s)
        if cost > SLOT_TOL * s:
            continue
        if best[i] is None or (rank, key, -cost) > best[i][0]:
            best[i] = ((rank, key, -cost), x, kind, circle, y)
    out = []
    for i in range(5):
        if best[i] is None:
            # A slot no candidate reached. It is emitted anyway -- when the fan fits the
            # hand HAS five cards -- with no digit, which the caller reads as "ask the API".
            t, ts = read_tactics_type(img, i)
            out.append({"x": int(SLOT_PLAYER[i][0] * s), "kind": "tactics", "digit": None,
                        "score": 0.0, "type": t, "type_score": round(ts, 3),
                        "y": int(SLOT_PLAYER[i][1] * s)})
            continue
        _, x, kind, circle, cy = best[i]
        digit, sc = read_digit(img, circle) if circle else (None, 0.0)
        row = {"x": x, "kind": kind, "digit": digit, "score": round(sc, 3),
               "y": int(cy)}
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
        out.append(row)
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
                        "type": None})
    out.sort(key=lambda r: r["x"])
    return out
