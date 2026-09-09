"""LOCAL READERS for game-state fields the paid vision call currently supplies.

Three readers, each built and then re-derived by an INDEPENDENT SKEPTIC who rewrote the
scoring before reading the original. Every one ABSTAINS rather than guesses: None means
ASK THE PAID MODEL, because an abstention costs one API call while a wrong answer plays
the wrong card in a $50 match.

    read_discards_left(scoreboard)       61 of 61 against a by-eye truth built from the
                                         crops. THE PAID MODEL GOT 28 OF 61 -- here it is
                                         not merely replaceable, it is worse.
    read_phase(hand)                     203 of 205 cards, 60 of 61 hands, ZERO wrong,
                                         leave-one-phase-run-out AND on a train-early /
                                         test-late split.
    read_runners(third, second, first)   15 of 15 occupied bases, 168 of 168 empty.

WHY EACH ABSTAINS, in its own terms:
  * discards   every dot must read clearly lit or clearly spent, the lit ones must form a
               prefix run, and the panel behind them must be dark. A counter caught
               mid-animation fails those and returns None.
  * phase      a VOTE across the hand's cards, and it must be UNANIMOUS. Across 59 settings
               of every constant -- including settings that cost the per-card reader 90 of
               its 205 cards -- the hand vote NEVER returned a wrong phase. It turns a card
               error into an abstention.
  * runners    a base is occupied only when a real power disc is found there; anything
               ambiguous is not called empty, it is not called at all.

STILL NEEDING THE PAID MODEL: the SCREEN type, result_won, the ban-screen collection, and
batters_used.
"""
import os

import numpy as np
import scipy.ndimage as _ndi
from PIL import Image

import local_hand
import local_hand as lh

_HERE = os.path.dirname(os.path.abspath(__file__))
SEP = "# " + "-" * 86


# --------------------------------------------------------------------------------------
# THE DISCARD DOT COUNTER
# --------------------------------------------------------------------------------------
SCOREBOARD_ANCHOR_W = 359.0
ROUND_DOTS = ((212.0,126.0),(239.0,126.0),(265.5,126.0),(292.0,126.0),(318.5,126.0))
DISCARD_DOTS = ((213.0,158.0),(239.0,158.0))
PANEL_GAPS = ((226.0,158.0),(225.5,126.0),(252.0,126.0),(278.5,126.0),(305.0,126.0))
DOT_SAMPLE_R=5.0; PANEL_SAMPLE_R=1.5
DOT_LIT_MIN=160; DOT_SPENT_MAX=100; PANEL_GAP_MAX=75
GATES=dict(panel=True, ambig=True, prefix=True, nonzero=True, leftfirst=True)

def _win_max(g,cx,cy,r):
    H,W=g.shape
    y0,y1=int(round(cy-r)),int(round(cy+r))+1
    x0,x1=int(round(cx-r)),int(round(cx+r))+1
    if y0<0 or x0<0 or y1>H or x1>W: return None
    return int(g[y0:y1,x0:x1].max())

def read_discards_left(scoreboard_img, debug=None):
    g=np.asarray(scoreboard_img.convert("L"),dtype=np.uint8)
    s=scoreboard_img.width/SCOREBOARD_ANCHOR_W
    r=max(2.0,DOT_SAMPLE_R*s); rg=max(1.0,PANEL_SAMPLE_R*s)
    d={} if debug is None else debug
    def note(w):
        d["why"]=w; return None
    gaps=[_win_max(g,x*s,y*s,rg) for x,y in PANEL_GAPS]; d["panel_gap"]=gaps
    if any(v is None for v in gaps): return note("crop too small")
    if GATES["panel"] and max(gaps)>PANEL_GAP_MAX:
        return note(f"no dark panel behind the counters ({max(gaps)})")
    d["round_peak"]=[_win_max(g,x*s,y*s,r) for x,y in ROUND_DOTS]
    d["discard_peak"]=[_win_max(g,x*s,y*s,r) for x,y in DISCARD_DOTS]
    def st(p):
        if p is None: return None
        if p>=DOT_LIT_MIN: return True
        if p<=DOT_SPENT_MAX: return False
        return None if GATES["ambig"] else (p>=(DOT_LIT_MIN+DOT_SPENT_MAX)//2)
    rnd=[st(p) for p in d["round_peak"]]; dsc=[st(p) for p in d["discard_peak"]]
    d["round"],d["discard"]=rnd,dsc
    if any(v is None for v in rnd) or any(v is None for v in dsc):
        return note("a dot is neither lit nor spent")
    k=sum(rnd)
    if GATES["nonzero"] and k==0: return note("no round dot is lit")
    if GATES["prefix"] and rnd!=[True]*k+[False]*(len(rnd)-k):
        return note(f"round row is not a prefix run: {rnd}")
    if GATES["leftfirst"] and dsc!=sorted(dsc,reverse=True):
        return note(f"discards are not spent right-to-left: {dsc}")
    return sum(dsc)


# --------------------------------------------------------------------------------------
# THE PHASE READER (batting or pitching, from the card banners)
# --------------------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
PHASE_TEMPLATES = os.path.join(_HERE, "phase_templates.npz")

# THE INK. A banner pixel is bright AND its neighbourhood is dark -- the same shape as
# table_prompt's stroke mask. Measured over the whole corpus by sweeping each constant
# and re-scoring end to end (agent_progress/phase-banner/progress.md):
#     BRIGHT  165..205 all give 60/61 or 59/61 hands, 0 wrong; 185 is the coverage peak
#     LOCAL   122..170 all give 0 wrong hands; coverage peaks 128..142 (56-60 of 61) and
#             falls away either side -- this is a RAMP, not a gap, and it is the one
#             constant here that is. It is safe because what falls off is COVERAGE.
#     NBR      9..21 all 0 wrong; 13 and 21 are the peak
BANNER_BRIGHT = 185
BANNER_LOCAL = 130
BANNER_NBR = 13
# The search window relative to the DETECTED power disc, in the 979-wide crop the fan
# anchors were measured in (local_hand.ANCHOR_W) and scaled with it. Three other windows
# were scored; only one 15-px-tighter one lost anything (58/61 hands, still 0 wrong).
BANNER_WIN = (-215.0, -55.0, -40.0, 15.0)
# Letters are joined into one word by a horizontal closing. 5..8 px all give 60/61.
BANNER_CLOSE = 6.0
# A WORD, NOT A FRAGMENT -- and this gate comes from the ALPHABET, not from a fit.
# "BATTER" and "PITCHER" share the suffix "ER" and first differ at the THIRD letter from
# the right (T against H), so a patch showing fewer than three letters cannot answer the
# question and must abstain. Measured at the 979-wide crop: a correctly-read word is
# 32-66 px wide (p01 33), about 7.7 px a letter; the ONE card in the corpus that was read
# wrong showed a 22-px fragment, opened and confirmed by eye as "ER". 28 px is about 3.6
# letters and sits in the 22-to-32 gap. THE NEGATIVE POPULATION IS ONE CARD: the
# justification is the alphabet, and the hand vote is what actually carries the safety.
BANNER_MIN_W = 28.0
BANNER_MIN_INK = 60          # mask pixels at 979 scale; 30..100 all give 60/61
# The patch cut leftwards from the word's right edge, and its raster.
BANNER_PATCH = (78.0, 26.0)
BANNER_SIZE = (52, 18)
# THE VOTE. At least this many located cards, and they must be unanimous. Two is the
# whole plateau: 3 costs 7 of the 61 hands and buys nothing (53 correct / 0 wrong /
# 8 abstained), 4 costs 31.
PHASE_MIN_CARDS = 2

_phase_cache = None


def _phase_templates():
    global _phase_cache
    if _phase_cache is None:
        if not os.path.exists(PHASE_TEMPLATES):
            return None
        z = np.load(PHASE_TEMPLATES)
        _phase_cache = (z["vectors"], [str(t) for t in z["banners"]])
    return _phase_cache


def player_discs(img):
    """[(x, y) or None] x5 -- where each fan slot's PLAYER disc is, or None.

    This is local_hand._read_fan's own slot assignment, kept because read_hand throws the
    y away and the banner sits above the disc. It returns None on the short-hand /
    empty-table path, exactly where read_hand falls back to the ungated search and there
    is no fan to hang a banner box on. IT MUST STAY IN STEP WITH _read_fan: the check is
    that it reports the same kind and the same x as read_hand on every frame.
    """
    strong = lh._strong_discs(img)
    if len(strong) < lh.FIT_MIN_DISCS:
        return None
    s = img.width / lh.ANCHOR_W
    fit = sorted(lh._slot(c[0], c[1], s)[0] / s for c in strong)
    if fit[len(fit) // 2] > lh.FIT_MAX:
        return None
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    taken = [(c[0], c[1]) for c in strong]
    cands = [(3, (c[3], c[2]), c[0], c[1]) for c in strong]
    for x, y, area, box in lh._white_discs(g):
        if lh._free(x, y, taken):
            taken.append((x, y))
            cands.append((2, (area, 0), x, y))
    for t in lh.find_tactics(img):
        if lh._free(t["x"], t["y"], taken):
            taken.append((t["x"], t["y"]))
            cands.append((1, (0, 0), t["x"], t["y"]))
    best = [None] * 5
    for rank, key, x, y in cands:
        cost, i, kind = lh._slot(x, y, s)
        if cost > lh.SLOT_TOL * s:
            continue
        if best[i] is None or (rank, key, -cost) > best[i][0]:
            best[i] = ((rank, key, -cost), x, y, kind)
    return [None if b is None or b[3] != "player" else (b[1], b[2]) for b in best]


def phase_banner_vector(img, cx, cy):
    """The banner's ink, right-aligned on its own right edge, as a unit vector, or None.

    None means NOT READ: no ink at all (a washed-out card whose ribbon is grey rather
    than black), or ink too narrow to carry the third letter from the right.
    """
    s = img.width / lh.ANCHOR_W
    x0 = max(0, int(round(cx + BANNER_WIN[0] * s)))
    y0 = max(0, int(round(cy + BANNER_WIN[1] * s)))
    x1 = min(img.width, int(round(cx + BANNER_WIN[2] * s)))
    y1 = min(img.height, int(round(cy + BANNER_WIN[3] * s)))
    if x1 - x0 < 20 or y1 - y0 < 12:
        return None
    g = np.asarray(img.crop((x0, y0, x1, y1)).convert("L"), dtype=np.float32)
    k = max(3, int(round(BANNER_NBR * s)) | 1)
    ink = (g >= BANNER_BRIGHT) & (_ndi.uniform_filter(g, size=k) <= BANNER_LOCAL)

    joined = _ndi.binary_closing(ink, structure=np.ones((1, max(3, int(round(
        BANNER_CLOSE * s))))))
    lab, n = _ndi.label(joined)
    best = None
    for i, sl in enumerate(_ndi.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        w, h = xs.stop - xs.start, ys.stop - ys.start
        if w < BANNER_MIN_W * s or h < 8 * s or h > 34 * s:
            continue
        got = int((ink[sl] & (lab[sl] == i)).sum())
        if got < BANNER_MIN_INK * s * s:
            continue
        if best is None or got > best[0]:
            best = (got, xs.start, ys.start, xs.stop, ys.stop)
    if best is None:
        return None
    _, wx0, wy0, wx1, wy1 = best

    pw, ph = BANNER_PATCH
    my = (wy0 + wy1) / 2.0
    px0, px1 = int(round(wx1 - pw * s)), int(round(wx1))
    py0, py1 = int(round(my - ph * s / 2)), int(round(my + ph * s / 2))
    H, W = ink.shape
    a0, b0, a1, b1 = max(px0, 0), max(py0, 0), min(px1, W), min(py1, H)
    if a1 <= a0 or b1 <= b0:
        return None
    patch = np.zeros((py1 - py0, px1 - px0), dtype=np.uint8)
    patch[b0 - py0:b1 - py0, a0 - px0:a1 - px0] = ink[b0:b1, a0:a1] * 255
    v = np.asarray(Image.fromarray(patch).resize(BANNER_SIZE, Image.BILINEAR),
                   dtype=np.float32).ravel()
    v = v - v.mean()
    nn = np.linalg.norm(v)
    return None if nn < 1e-6 else v / nn


def read_phase(img, bank=None):
    """('batting'|'pitching', detail) for a hand strip, or (None, detail) when unsure.

    None means NOT READ and the caller must ask the paid model -- an abstention costs one
    paid call, a wrong answer plays the wrong card type for $50. It never guesses: the
    whole value of this reader is that its answer can be trusted without a second opinion.

    `detail` carries {"votes", "cards", "scores"} so a caller or a log can see WHY.
    """
    bank = bank if bank is not None else _phase_templates()
    detail = {"votes": {}, "cards": 0, "scores": []}
    if bank is None:
        return None, detail
    vecs, banners = bank
    discs = player_discs(img)
    if discs is None:
        return None, detail                     # a short hand: no fan to hang a box on
    for d in discs:
        if d is None:
            continue
        v = phase_banner_vector(img, d[0], d[1])
        if v is None:
            continue
        scores = vecs @ v
        k = int(scores.argmax())
        detail["votes"][banners[k]] = detail["votes"].get(banners[k], 0) + 1
        detail["scores"].append(round(float(scores[k]), 3))
        detail["cards"] += 1
    if detail["cards"] < PHASE_MIN_CARDS or len(detail["votes"]) != 1:
        return None, detail                     # too few cards, or they disagree
    return {"batter": "batting", "pitcher": "pitching"}[next(iter(detail["votes"]))], detail


# --------------------------------------------------------------------------------------
# THE RUNNERS READER (is there a card on this base)
# --------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------
# THE RUNNERS READER. Belongs beside local_hand.read_tactics_type; same shape, same rule --
# it ABSTAINS rather than guess, because its answer picks the card played in a $50 match.
#
# THE PREMISE IS THE USER'S AND IT IS CORRECT: a card sitting on a base carries the SAME
# white power disc as a card in hand, so "is there a runner here" is a DISC-DETECTION
# question, not an OCR-a-name question. Checked against the frames: an EMPTY base is a dark
# round coin medallion in its socket; an OCCUPIED one is a face-up player card with the
# power disc at its top-right.
#
# MEASURED over 183 base crops (61 turns x 3 bases) from overnight/local_hand/, every crop
# adjudicated BY EYE from a contact sheet: 15 occupied, 168 empty.
#
#   THE TWO POPULATIONS, brightness            THE TWO POPULATIONS, the blob's own width
#     occupied crops, max grey   255 (15/15)     the power disc          26 - 28  (n=15)
#     empty crops,    max grey   157 - 211       the empty medallion     31 - 34  at 2nd base
#       (only 13 of 168 reach 210, and 6 of      the OPPONENT'S TURN     59 - 71
#        those are the OPPONENT'S TURN banner      banner letters
#        at 255 -- excluded by SIZE, not          the card back's toe    28 - 34
#        brightness)                               ovals (a card flying in)
#
#   fill (white area / bbox)      the disc 0.512 - 0.737    everything else at disc size
#                                                           0.211 - 0.235
#   ink (largest dark part inside) the disc 17 - 100 px     everything else 0 - 6 px
#
# The SECONDARY cannot be mistaken for the power: the shield is WHITE-ON-DARK (a thin white
# annulus, fill 0.10-0.15) while the power disc is filled white with the digit punched out.
# local_hand's own docstring records the same inversion for hand cards.
DISC_WHITE = 210
DISC_W = (23, 31)
DISC_H = (11, 31)
DISC_FILL = 0.45
DISC_INK = 15
DARK = 110

# THE GATE THAT DOES THE WORK: the digit must be ENCLOSED by its disc -- its ink may not
# reach the blob's own bounding box on a side that is not the image border (the border
# exemption is what lets a disc the crop box has CLIPPED still count).
#
# MEASURED, 26_mutants.py / 27_ablate.py, on all 183 crops:
#     shipped                       14 hit / 0 wrong / 1 abstain | 0 false positives
#     ENCLOSE off, DISC_WHITE 210   15 hit / 0 wrong / 0 abstain | 0 false positives
#     ENCLOSE off, DISC_WHITE 190   15 hit                       | 5 FALSE POSITIVES
#     ENCLOSE off, DISC_WHITE 185   15 hit                       | 12 FALSE POSITIVES
#     size window off, ENCLOSE on   15 hit                       | 3 FALSE POSITIVES
# So ENCLOSE costs ONE detection (turned into an abstention, not a wrong answer) and buys
# a DISC_WHITE that can move from 170 to 220 without changing any answer. DISC_FILL and
# DISC_INK are REDUNDANT on this corpus -- removing either changes nothing -- and are kept
# only as insurance against shapes 183 crops do not contain. Say so rather than credit them.
ENCLOSE = True


def _disc_candidates(g):
    """(enclosed, eligible) power-disc blobs in a greyscale base crop.

    `eligible` is the superset: disc-sized, disc-filled, with a dark mark inside.
    `enclosed` are the ones whose dark mark does not run off the blob's own edge.
    """
    import numpy as np
    import scipy.ndimage as _ndi
    H, W = g.shape
    lab, n = _ndi.label(g >= DISC_WHITE)
    enclosed, eligible = [], []
    for k, sl in enumerate(_ndi.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if not (DISC_W[0] <= w <= DISC_W[1] and DISC_H[0] <= h <= DISC_H[1]):
            continue
        area = int((lab[sl] == k).sum())
        fill = area / float(w * h)
        if fill < DISC_FILL:
            continue
        sub = g[ys.start:ys.stop, xs.start:xs.stop] <= DARK
        l2, n2 = _ndi.label(sub)
        if not n2:
            continue
        sizes = _ndi.sum(sub, l2, range(1, n2 + 1))
        j = int(np.argmax(sizes)) + 1
        ink = int(sizes[j - 1])
        if ink < DISC_INK:
            continue
        cand = {"box": (int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)),
                "w": w, "h": h, "fill": round(fill, 3), "ink": ink,
                "clipped": bool(ys.start == 0 or xs.start == 0
                                or ys.stop >= H or xs.stop >= W)}
        eligible.append(cand)
        if ENCLOSE:
            iy, ix = np.where(l2 == j)
            if (iy.min() == 0 and ys.start != 0) or (iy.max() == h - 1 and ys.stop < H):
                continue
            if (ix.min() == 0 and xs.start != 0) or (ix.max() == w - 1 and xs.stop < W):
                continue
        enclosed.append(cand)
    return enclosed, eligible


def read_base(img):
    """Is a runner standing on this base, and what is his power.

    Returns {"occupied": True | False | None, "power": int | None, "score": float,
             "clipped": bool}. `occupied` None and `power` None both mean NOT READ: the
    caller asks the paid model. None is never "no runner" and never "power unknown".

    A base is OCCUPIED when a power disc is found. A blob that is disc-sized and
    disc-filled but whose ink runs off its own edge is card art, a card back, or a disc the
    crop box has cut too hard to recognise -- it ABSTAINS rather than decide either way.

    The POWER is read only from an UNCLIPPED disc, through local_hand.read_digit and its
    template bank (cut from HAND crops in a different archive, so a base disc is held out
    by construction), which abstains below local_hand.MIN_SCORE. A clipped disc is never
    read: measured, every one scores 0.216-0.534 against a MIN_SCORE of 0.80, so it
    abstains on its own -- but the check is explicit so a future template set cannot start
    guessing at half a glyph.
    """
    import numpy as np
    import local_hand
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    enclosed, eligible = _disc_candidates(g)
    if not enclosed:
        return {"occupied": None if eligible else False,
                "power": None, "score": 0.0, "clipped": False}
    disc = max(enclosed, key=lambda d: d["ink"])
    out = {"occupied": True, "power": None, "score": 0.0, "clipped": disc["clipped"]}
    if disc["clipped"]:
        return out
    circle = local_hand._digit_in_disc(g, disc["box"])
    if circle is None:
        return out
    digit, score = local_hand.read_digit(img, circle)
    out["score"] = round(float(score), 3)
    if digit is not None and digit.isdigit():
        out["power"] = int(digit)
    return out


def read_runners(third_img, second_img, first_img):
    """The three bases, and the runner COUNT the decision engine branches on.

    `count` is None when any base abstained: a count with a hole in it is a WRONG count,
    not a partial one. decision_engine reads state.runners only through
    `len(state.runners) > 0` (line 182) and `state.runners` truthiness (line 104), so the
    count is the whole of what it consumes. orchestrator.exclude_runners matches the reveal
    by roster NAME, which a disc reader cannot supply -- see the report.
    """
    bases = {"third": read_base(third_img), "second": read_base(second_img),
             "first": read_base(first_img)}
    vals = [b["occupied"] for b in bases.values()]
    count = None if any(v is None for v in vals) else sum(1 for v in vals if v)
    return {"bases": bases, "count": count}


