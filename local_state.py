"""LOCAL READERS for game-state fields the paid vision call currently supplies.

Four readers, the first three built and then re-derived by an INDEPENDENT SKEPTIC who
rewrote the scoring before reading the original. Every one ABSTAINS rather than guesses: None means
ASK THE PAID MODEL, because an abstention costs one API call while a wrong answer plays
the wrong card in a $50 match.

    read_discards_left(scoreboard)       61 of 61 against a by-eye truth built from the
                                         crops. THE PAID MODEL GOT 28 OF 61 -- here it is
                                         not merely replaceable, it is worse.
    read_phase(hand)                     203 of 205 cards, 60 of 61 hands, ZERO wrong,
                                         leave-one-phase-run-out AND on a train-early /
                                         test-late split.
    read_runners(third, second, first)   15 of 15 occupied bases, 168 of 168 empty.
    read_result(full_frame)              31 held-out result screens across four sessions
                                         and three geometries, every class right, and ZERO
                                         false positives in 72,318 frames.

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

  * result     the word must be found at a correlation no non-result frame in a 72,318-frame
               census reaches. The fade in and out of the banner scores below that and comes
               back "not a result screen", which is right: the banner then sits fully opaque
               for at least 4.0 s (median 7.0 s over 25 sightings) and the caller polls.

STILL NEEDING THE PAID MODEL: the ban-screen collection, and batters_used. `screen` is now
answered locally for the two screens the turn loop meets -- "result" and "turn" -- and
anything else is a NAMED GAP rather than a guess.
"""
import base64
import os

import cv2
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
# --------------------------------------------------------------------------------------
# THE RUNNERS READER -- rebuilt 2026-09-09 after an independent skeptic refuted the first
# one. It answers ONE question per base: is a player card standing on it.
#
# THE PREMISE IS THE USER'S AND IT IS CORRECT: a card on a base carries the SAME white
# power disc as a card in hand, so "is there a runner here" is a DISC question, not an
# OCR-a-name question. WHAT THE FIRST VERSION GOT WRONG is the other half: it treated
# "I found no disc" as EVIDENCE OF AN EMPTY BASE and returned a confident False, with
# nothing behind that branch at all. Measured on 600 frames sampled at random from
# overnight/runs/*/stream.mp4 (agent_progress/runners-fix/, 32_videoneg.py): on
# 233 of 1800 base regions -- a ban screen, a reveal, a cutscene, a black frame, an NPC
# filling the shot -- the old reader answered "no runner on this base".
#
# SO THERE ARE TWO DETECTORS NOW AND THEY MUST AGREE.
#
#   A CARD IS HERE   a white blob of the power disc's size, with a dark mark inside.
#   THE BASE IS BARE an empty base is a dark embossed COIN in a socket, in the same place
#                    in every frame; matched against a 16x16 template of it.
#
# occupied when the disc is seen and the coin is not; empty when the coin is seen and the
# disc is not; NOT READ when they contradict each other or when neither fires -- which is
# what a card flying across the base, or a screen that is not the board at all, looks
# like. None is never "no runner". The caller asks the paid model.
#
# MEASURED over 1080 base crops (360 turns x 3 bases) from overnight/local_hand/, every
# crop adjudicated BY EYE off contact sheets (agent_progress/runners-fix/progress.md):
#
#                                        n     CORRECT   WRONG   ABSTAINED
#     a player card on the base         143       143       0        0
#     the bare coin                     929       929       0        0
#     a card back flying across it        8         2       0        6
#
#   HELD OUT -- the coin templates are built from the empty crops of the FIRST 100 turns
#   only, so rows 100-359 never touched them: 124/124 occupied, 649/649 bare, 1/7 of the
#   card-back crops answered, ZERO wrong. 1.03 ms for all three bases.
#
#   Against the PAID MODEL over the same 360 turns the runner COUNT agrees 345, differs 9,
#   abstains 6 -- and ALL NINE DIFFERENCES ARE THE PAID MODEL'S ERROR, adjudicated by eye
#   (it misses a second-base runner in seven turns and invents one in two, once naming it
#   "Runner" and once "second_base_runner"). Agreement with it is not the target.
#
# THE TWO POPULATIONS BEHIND EVERY CONSTANT (all 1080 crops; the sweep is 34_ablate.py,
# which moves one constant at a time and re-scores end to end):
#
#   BASE_COIN_MIN     the coin visible in its socket   n=931   min 0.9175  p05 0.9803
#                     a card back across the coin      n=  6   max 0.6876
#                     a player card on the base        n=143   max 0.3888
#                     0.70 .. 0.90 all give the same answer on all 1080; 0.95 costs 11
#                     bare crops, 0.60 starts answering crops whose coin is half covered.
#
#   BASE_DISC_H       the disc AS THE CROP PRESENTS IT   n=143   12 .. 27
#                       (measured by POSITION -- the blob in the disc's own place on
#                        the card -- so the population is not defined by this gate)
#                       (26-27 at second base; 12-23 at first and third, where the crop
#                        box CUTS it -- see the note on GAMEPLAY_REGIONS_FRAC below)
#                     every other blob of disc width on a base with no card on it
#                                                        n=  6   6, 6, 62, 62, 62, 62
#                                                        (a sliver at the crop's bottom
#                                                         edge; the OPPONENT'S TURN banner)
#                     7 .. 12 all identical; 13 loses 8 real cards, 6 costs 2 bare crops,
#                     62 lets the banner letter in. 9 and 40 are the middles of those runs.
#                     THE OLD (11, 31) SAT ONE STEP FROM THE EDGE: 12 is the last floor
#                     that reads every card, and its own lowest disc is 12 px tall.
#
#   BASE_DISC_W       the disc          n=143   26 .. 29
#                     everything else that passes fill+ink   19 (h 9), 23 (h 6), 25 (h 6),
#                                                            then 43 .. 71 (banner letters)
#                     20 .. 26 identical; 27 loses 83 cards, 18 costs a bare crop.
#
#   BASE_DISC_WHITE   200 .. 220 identical. 190 puts a CARD BACK's white rabbit head
#                     through the size gate and answers "occupied" on it (1 wrong at 190,
#                     4 at 170). 230 loses a card. This one is load-bearing.
#
#   BASE_DISC_FILL, BASE_DISC_INK, BASE_DARK are REDUNDANT on this corpus: 0.45 -> 0.0,
#   15 -> 0, and both together, change no answer among 1080. They are shape insurance
#   against art these 360 turns do not contain, and they are not evidence. Say so rather
#   than credit them.
#
# SCALE. Every constant is in the units of the crop's own width and scaled by it, so the
# reader does not assume 1920x1080. Resampling all 1080 crops to 0.75x, 0.90x, 0.972x
# (= a 1867-wide capture) and 1.10x costs exactly ONE occupied crop, turned into an
# abstention, and produces no wrong answer at any scale (35_scale.py). That is a
# resampling test, NOT a real capture at another geometry -- none exists on disk.
#
# THE CROP BOXES ARE WRONG AND THIS READER WORKS AROUND THEM. Measured on full frames
# recovered from the recorded video (13_discgeom.py): the power disc of a card on FIRST
# base spans y 0.3056-0.3343 of the frame and on THIRD 0.3102-0.3380, while
# orchestrator.GAMEPLAY_REGIONS_FRAC starts both crops at y0 = 0.320 -- so the crop cuts
# the disc in half, 88 of 143 discs arrive clipped, and BASE_DISC_H's floor has to reach
# down to 12 to see them. second_base (y0 = 0.080) is whole and its discs are 26-27.
# Re-cutting those two crops from the video at y0 = 0.295 makes the disc WHOLE on 26 of
# 26 re-cuts and reads its POWER on 18 of 22 first-base cards, against 0 of 88 today
# (37_boxfix.py). It is a separate change: it moves what the PAID model sees, invalidates
# every constant here that is measured in crop pixels, and needs its own collection pass.
BASE_ANCHOR_W = {"third": 221.0, "second": 288.0, "first": 220.0}
BASE_DISC_WHITE = 210
BASE_DISC_W = (22.0, 36.0)
BASE_DISC_H = (9.0, 40.0)
BASE_DISC_FILL = 0.45
BASE_DISC_INK = 15.0
BASE_DARK = 110
# The coin's own box inside each crop, and its 16x16 template: the mean of every bare crop
# in the first 100 sampled turns, so turns 100-359 are held out. Rebuild with
# agent_progress/runners-fix/build_templates.py -- it is deterministic.
BASE_COIN_BOX = {"third": (64.0, 37.0, 140.0, 116.0),
                 "first": (94.0, 44.0, 174.0, 122.0),
                 "second": (86.0, 76.0, 166.0, 150.0)}
BASE_COIN_N = 16
BASE_COIN_MIN = 0.80
BASE_COINS_B64 = (
    "XFRJQDk0MzU8QEZRYGtxcE1BMykjJjlMWFpYVlZfbHA7MCYeNGJgT0dGT11kYGFtLiQcPHJR"
    "QE9FQEs5QVxlaCceLnVRO2xlTHVxSDM8XWYjHFxhO057ZmqAbFI3OUNeISNxRkJgfYB6c11T"
    "Qjs5Uh0ubkJHbXJxdWVhW1NEP0kcMG1ESVdxY3BmVV1KQT1IHixtSkVIX1+AcFlUQDk7SCMc"
    "Y1ZBT3BvfHNbVUM8OlcuFkhpSV18ZVtdT1k9PEFvOiIlZWRQW1dkWkVHPTtjdUs8JTVkaVdE"
    "Q0dEQ05reF1dUEAsN1hsbmZhZm91bVtoYmFaTz03QlFaYF1ZV1lsdjMjGBk4XFRIT0lTYj4d"
    "IzEyIBhDWjhBXEo5NT5oSSItMh83XjhAU3hSM0I8PnY7KTAiW0NOYE9uZF1sUDpNayQtMFg9"
    "Q1hthGBlbYpDN20xLUFMP0RKdYp9d36Ehz9cRDJJTEBWWGRucX+GfHFsWFA5Sk9EO2RXW2lz"
    "j2BeYVtaQkhVRzk9VGRgZ4mBT0lfUUxEYkNEN0FfamJ4hUQ+aUZVQGdPNkhCQTo9U08yT21A"
    "WkpWb0YvOzw5Mi4wR3BZSl1YRWNyWT0zMC83VW9mQ1ljX1RIY3RzbWhsdHZlR1RcZmZhVUdQ"
    "XmptaFxSRlVgZFlmY2FcT0dGRkhJUFxjZWx0dXVxamFXWltbRicpMTc8e3RxZkU7WE9GQGBc"
    "JygvN3hxYEJJUXdXOj08W1ojKDRvakdUYVNvZk1aQzxpQiIxcFNIRll2gllvcGs4SmMhLXFN"
    "S1laeop1c36HUTxqJiduUEdmXHBxdoOJcn89ZysjblBKVW5oZW6EgVx8TWguJHJRUkBIXWRg"
    "f4pVY1JnKih0XEdRTFtoYHWGV0RYXSQva3pJRE9HQkZZXEJHaEMmN1p7eEpBREVBP0FOaVwq"
    "MEhsWHqBaVZJSE5ga2I5O09demhTYXR7eHJybFpETV9maX97cF1QT1NRTElQZm5ucW+Bf3x5"
    "dGliYGNsdHV1dXd0"
)
BASE_COIN_ORDER = ("third", "second", "first")

_base_coins = None


def base_coins():
    """{base: 16x16 float array}, the bare-coin templates, decoded once."""
    global _base_coins
    if _base_coins is None:
        raw = np.frombuffer(base64.b64decode(BASE_COINS_B64), dtype=np.uint8)
        n = BASE_COIN_N * BASE_COIN_N
        _base_coins = {b: raw[k * n:(k + 1) * n].reshape(BASE_COIN_N, BASE_COIN_N)
                       .astype(np.float32)
                       for k, b in enumerate(BASE_COIN_ORDER)}
    return _base_coins


def base_coin_score(img, base):
    """Zero-mean normalised correlation of the coin's box against its template, or None.

    None means the crop cannot hold the box at all -- a geometry this reader has no
    anchor for. It is NOT a low score, and it must never be read as "no coin".
    """
    t = base_coins().get(base)
    if t is None:
        return None
    # SEARCH, DO NOT ANCHOR. BASE_COIN_BOX is still used -- for the coin's SIZE, which
    # scales with the crop width -- but not for its POSITION, which does not survive a
    # crop-box change. patch83 moved two boxes 0.030 of frame height and the anchored
    # version died: third +0.995 -> -0.048, first +0.989 -> +0.008, while second (the box
    # patch83 left alone) was unchanged. The searched version reads the same under both.
    import cv2
    g = np.asarray(img.convert("L"), dtype=np.float32)
    s = img.width / BASE_ANCHOR_W[base]
    x0, y0, x1, y1 = BASE_COIN_BOX[base]
    side = int(round(max(x1 - x0, y1 - y0) * s))
    if side < 8 or side > min(g.shape):
        return None
    tt = cv2.resize(t.astype(np.float32), (side, side), interpolation=cv2.INTER_LINEAR)
    return float(cv2.matchTemplate(g, tt, cv2.TM_CCOEFF_NORMED).max())


def base_discs(g, s):
    """Every white blob in a base crop that is shaped like a card's POWER DISC.

    `g` is the greyscale crop, `s` its width over this base's anchor width. A blob
    qualifies on SIZE, on being solid, and on carrying a dark mark inside -- the digit.
    The SECONDARY cannot be mistaken for it: the shield is a thin WHITE ANNULUS around a
    dark interior (fill 0.10-0.15) while the power disc is filled white with the digit
    punched out (fill 0.51-0.74), the same inversion local_hand records for hand cards.
    """
    out = []
    H, W = g.shape
    lab, _ = _ndi.label(g >= BASE_DISC_WHITE)
    for k, sl in enumerate(_ndi.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if not (BASE_DISC_W[0] * s <= w <= BASE_DISC_W[1] * s):
            continue
        if not (BASE_DISC_H[0] * s <= h <= BASE_DISC_H[1] * s):
            continue
        area = int((lab[sl] == k).sum())
        if area / float(w * h) < BASE_DISC_FILL:
            continue
        sub = g[ys.start:ys.stop, xs.start:xs.stop] <= BASE_DARK
        l2, n2 = _ndi.label(sub)
        if not n2:
            continue
        ink = float(max(_ndi.sum(sub, l2, range(1, n2 + 1))))
        if ink < BASE_DISC_INK * s * s:
            continue
        out.append({"box": (int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)),
                    "w": int(w), "h": int(h), "ink": int(ink),
                    "clipped": bool(ys.start == 0 or xs.start == 0
                                    or ys.stop >= H or xs.stop >= W)})
    return out


# THE SHIELD BADGE ON A BASE CARD IS THE RUNNER'S SPEED, and it reads cleanly (2026-09-12).
# This is the field read_runners' docstring used to say was out of reach. Searched, not
# cropped (CLAUDE.md 10.23) -- it is a sprite, so matchTemplate over a scale sweep answers
# "is it there" and "which digit" at once. The bank is local_hand's, cut from HAND cards in
# a different archive, and the winning scale on a base crop is ~0.70, so no base crop can
# match itself (10.22's self-match trap).
#
# Measured over 1,278 saved base crops, with occupancy taken from the COIN and DISC
# detectors so the labels are not this reader's own answers (10.31):
#
#     EMPTY bases      n=1106   badge score max 0.592
#     OCCUPIED bases   n= 172   p05 0.857, median 0.892
#     the shipped SHIELD_MIN (0.69) sits between them -- no new constant is invented
#
# 171 of 172 occupied bases read a digit; the one abstention scores 0.492 and is the only
# occupied crop under the gate. ZERO of the 1,106 bare bases read a badge at all.
# Digits seen: 1 x129, 2 x22, 3 x20 -- never 0, and never above 3.
#
# AND IT IS NOT THE CARD'S ROSTER SECONDARY. The same named card shows different badge
# values at different moments (Bunz 1x31 and 2x8, Fisto 3x3 and 1x2, Sharp 1x22 and 2x1),
# and among roster cards sharing each one's POWER none carries the observed value, so a
# name mix-up cannot explain it. It is a LIVE number -- what this runner will advance now,
# which is what a speed boost changes for one turn. That is the whole reason to read it.
BADGE_SCALES = tuple(round(v, 3) for v in np.arange(0.40, 1.25, 0.05))


def base_badge(img):
    """(score, digit) for the best shield badge in a base crop, or (0.0, None).

    NO GATE HERE: the caller compares against local_hand.SHIELD_MIN. Returning the raw
    score means "cannot look" and "looked and saw nothing" stay distinguishable, which is
    the distinction this project keeps losing (10.1).
    """
    tpl = local_hand._shield_templates()
    if not tpl:
        return 0.0, None
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    H, W = g.shape
    best = (0.0, None)
    for sc in BADGE_SCALES:
        tw = int(round(local_hand.SHIELD_SIZE[0] * sc))
        th = int(round(local_hand.SHIELD_SIZE[1] * sc))
        if tw < 6 or th < 6 or th > H or tw > W:
            continue
        for d, t in tpl.items():
            tt = cv2.resize(t, (tw, th), interpolation=cv2.INTER_LANCZOS4)
            _, mx, _, _ = cv2.minMaxLoc(cv2.matchTemplate(g, tt, cv2.TM_CCOEFF_NORMED))
            if mx > best[0]:
                best = (float(mx), int(d))
    return best


def read_base(img, base):
    """Is a player card standing on this base, and what is its power.

    `base` is "third", "second" or "first" -- the coin template and its box are per base.
    Returns {"occupied": True | False | None, "power": int | None, "speed": int | None,
             "score": float, "coin": float | None, "clipped": bool, "why": str}. `occupied` None and
    `power` None both mean NOT READ: ask the paid model. None is never "no runner".

    THE ANSWER NEEDS BOTH DETECTORS TO AGREE. A disc and no coin is a card on the base.
    A coin and no disc is a bare base. Both, or neither, is not an answer: neither is
    what a card back sliding across the base looks like, and what a screen that is not
    the board at all looks like -- and the old reader called that second case EMPTY.

    The POWER is read only from an UNCLIPPED disc, through local_hand.read_digit and its
    template bank, which is cut from HAND crops in a different archive, so a base disc is
    held out of it by construction. With today's crop boxes the first- and third-base
    discs are always cut by the crop's top edge, so power comes back only from second
    base -- 38 of its 55 occupied crops, and where correspondence with the paid model can
    be PROVEN (exactly one runner labelled and exactly one base read occupied) it is
    15 correct, 0 wrong, 63 abstained.
    """
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    s = img.width / BASE_ANCHOR_W[base]
    coin = base_coin_score(img, base)
    out = {"occupied": None, "power": None, "speed": None, "speed_score": 0.0,
           "score": 0.0, "coin": coin, "clipped": False, "why": ""}
    if coin is None:
        out["why"] = "no coin box fits this crop"
        return out
    discs = base_discs(g, s)
    disc_seen = bool(discs)
    coin_seen = coin >= BASE_COIN_MIN
    if disc_seen == coin_seen:
        out["why"] = ("a disc AND the coin" if disc_seen
                      else f"neither a disc nor the coin (coin {coin:.3f})")
        return out
    if coin_seen:
        out["occupied"] = False
        out["why"] = f"the bare coin ({coin:.3f})"
        return out
    out["occupied"] = True
    out["why"] = f"a power disc, and no coin ({coin:.3f})"
    # SPEED is read only on an OCCUPIED base: on a bare base there is no card to carry a
    # badge, and scoring one anyway would invite exactly the false read the empty-base
    # population (max 0.592) exists to rule out.
    _bs, _bd = base_badge(img)
    out["speed_score"] = round(float(_bs), 3)
    out["speed"] = _bd if _bs >= local_hand.SHIELD_MIN else None
    disc = max(discs, key=lambda d: d["ink"])
    out["clipped"] = disc["clipped"]
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
    `len(state.runners) > 0` and its truthiness, and best_pitching_play only asks whether
    runners are on, so the count is the whole of what those consume.
    Each base also carries `speed` -- the runner's shield badge, a LIVE value and not the
    card's roster secondary (see base_badge). That is what a delay or a baserunning model
    needs: how far THIS runner moves on the next hit.

    orchestrator.exclude_runners is the one caller that needs a NAME, and a disc reader
    cannot supply one. (The claim that once stood here -- that this reader could never feed
    it -- was written before the badge and banner were read; the name is legible on the
    card and orchestrator.ocr_runner_card already reads banners. Unwiring that is open
    work, not a limit of the crop.)
    """
    bases = {"third": read_base(third_img, "third"),
             "second": read_base(second_img, "second"),
             "first": read_base(first_img, "first")}
    vals = [b["occupied"] for b in bases.values()]
    count = None if any(v is None for v in vals) else sum(1 for v in vals if v)
    # SPEEDS, in base order, for the runners actually on. None for a runner whose badge did
    # not read -- never 0, because 0 would be a distance and this is an absence.
    speeds = [b["speed"] for b in (bases["third"], bases["second"], bases["first"])
              if b.get("occupied")]
    return {"bases": bases, "count": count, "speeds": speeds}



# --------------------------------------------------------------------------------------
# THE RESULT SCREEN (is the match over, and did we win)
# --------------------------------------------------------------------------------------
# The last field with no local answer, and the one that kept a paid call in the turn loop.
#
# The word WINNER / LOSER is arched white text on a bright arc, dead centre, above the
# medallion. It is a SPRITE, so it is SEARCHED for, not cropped at an anchor -- it rides up
# and down and its arch FLATTENS as the medallion animates in.
#
# TWO WRONG TURNS, both settled by looking at the frames and not at the numbers
# (agent_progress/result-reader/):
#   1. The template was cut as "the union of every bright blob in a wide band". That union
#      swallowed the matchbox labels along the top edge, so the template was two thirds
#      scenery: result frames 0.497-0.547 against a non-result MAX of 0.603. OVERLAP.
#   2. Every example was then STRETCHED to one fixed size and the two class banks AVERAGED.
#      WINNER is wider than LOSER, so stretching made them the same shape, and the arch
#      flattens between frames (r1_0066's word is 95x14 where r1_0040's is 102x22), so
#      averaging blurred two different words together. Every WINNER frame then matched the
#      LOSER bank. Templates are kept at NATIVE size, one per example, never averaged.
#
# THE GATE SITS BETWEEN TWO MEASURED POPULATIONS, held out by RUN -- templates come from one
# run per class and are scored on every other, because a template matches its own source at
# 1.000 and frames from one sighting are near-duplicates of each other (CLAUDE.md 10.22).
#
#     HELD-OUT RESULT FRAMES, 342 from runs that supplied no template
#         winner  n=269   loser  n=22   draw  n=51        0 CLASS ERRORS
#         p05 0.954, median 0.983; exactly ONE frame falls under the gate, at 0.782, and it
#         was extracted and LOOKED AT: a half-transparent DRAW! ghosting in over the table
#         with the medallion not yet arrived (lowest_result.png). That is the abstention
#         this reader is supposed to make.
#     EVERY OTHER FRAME -- 72,725 scored, 998 at or above the gate
#         16,387 stills, four corpora at 768x432 / 960x540 / 1920x1080: 13 at or above the
#                        gate and ALL THIRTEEN are genuine result screens (4 of them are the
#                        template sources). Sub-gate max 0.735.
#         56,338 video, every 20th frame of all 18 run recordings. Sub-gate max 0.782 --
#                        and that frame is the DRAW fade described above, not a negative.
#
# THE HIGHEST NEGATIVES WERE EXTRACTED AND ADJUDICATED BY EYE (v2near.png, v2_nearmiss.png):
# the seven that top the list are all the WORLD -- the bar, the dealer prompt, the office
# door -- and the highest of them is 0.742. So the negative population genuinely reaches
# 0.742, and everything between there and the gate is a result screen fading in.
#
# WHY 0.80 AND NOT THE MIDPOINT. The two errors are not symmetric. A FALSE POSITIVE reports
# a finished match on a world frame and logs a win or a loss that never happened. A FALSE
# NEGATIVE costs nothing: the banner sits fully opaque for a measured 4.0 s at its shortest
# (25 sightings, median 7.0 s), so the next poll catches it. The gate is therefore biased
# AWAY from the negatives -- 0.058 clear of the highest adjudicated negative, against the
# 0.008 that 0.75 would have left, and still far below the result p05 of 0.954.
#
# TWO FRAMES IN THE ORIGINAL TWO-CLASS CENSUS WERE MISLABELLED, and both were DRAWS. They
# were filed as "the top non-result frames" precisely because the reader had no DRAW
# template and so could not see the word. That is why every frame near the gate, on BOTH
# sides, is opened and looked at before it is called anything.
RESULT_TEMPLATES = os.path.join(_HERE, "result_templates.npz")
RESULT_REF_W = 768.0
RESULT_SEARCH = (0.28, 0.12, 0.72, 0.42)
RESULT_MIN = 0.80
# THE THREE BANNERS. There is a DRAW! as well as WINNER and LOSER, and missing it is not a
# fade that the next poll recovers from -- a draw NEVER settles into a word a two-class
# reader knows, so it stalls the loop until the run gives up. 5 of the 52 matches on record
# are draws. It was found by looking at the frames a stalled run was staring at, not by any
# number: the reader called them "not a result screen" at 0.42-0.49 and the gap was reported
# against the hand.
RESULT_CLASSES = {"winner": "win", "loser": "loss", "draw": "draw"}
# `full_frame` means the WHOLE game frame. Handed a CROP instead, the scaled templates
# collapse to a few pixels and matchTemplate happily returns a number -- the shape
# CLAUDE.md 10.1 calls "a success path and a no-op path with identical output". Below half
# the reference width the word is under 51 px wide and 11 px tall and its strokes are
# sub-pixel, so there is nothing left to match. This is a validity floor on the INPUT
# geometry, not a discriminator between two populations, and it is written down as such.
RESULT_MIN_FRAME_W = RESULT_REF_W / 2
# ONE WORD AGAINST THE OTHER TWO is a different question from result-against-everything,
# and it has its own measured margin: on every held-out result frame the winning class beats
# the runner-up by a wide margin, and there are 0 class errors over 342 held-out frames.
# RESULT_MARGIN is NOT fitted to a population -- it is a tie-breaker floor, well below every
# real margin, so that two words scoring alike abstain rather than pick. That is stated
# plainly rather than dressed up as a measurement.
RESULT_MARGIN = 0.10

_result_tpls = None


def result_templates():
    """[(class, native template), ...] -- one per example frame, never averaged.

    The bank spans BOTH FORMS of each word. The first bank was cut entirely from the SETTLED
    form -- a small ARCHED word on a thin bright arc -- and mid-animation, before the arch
    sets, the same word is LARGER and FLAT and scores ~0.50, under the gate. Templates are
    taken evenly across the word's area at reference scale so the bank spans the animation
    rather than six frames of one moment.
    """
    global _result_tpls
    if _result_tpls is None:
        z = np.load(RESULT_TEMPLATES)
        _result_tpls = [(k.split("__")[0], z[k]) for k in z.files]
    return _result_tpls


def result_scores(img):
    """{"winner": float, "loser": float} -- the best correlation of each word, or {}.

    {} means the crop cannot hold a template at this scale. It is NOT a low score and must
    never be read as "not a result screen".
    """
    w = img.width
    if w < RESULT_MIN_FRAME_W:
        return {}
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    b = g[int(g.shape[0] * RESULT_SEARCH[1]):int(g.shape[0] * RESULT_SEARCH[3]),
          int(w * RESULT_SEARCH[0]):int(w * RESULT_SEARCH[2])]
    s = w / RESULT_REF_W
    out = {}
    for k, t in result_templates():
        tw, th = int(round(t.shape[1] * s)), int(round(t.shape[0] * s))
        if b.shape[0] < th or b.shape[1] < tw:
            continue
        tt = t if abs(s - 1.0) < 1e-6 else cv2.resize(t, (tw, th),
                                                      interpolation=cv2.INTER_LANCZOS4)
        mx = float(cv2.matchTemplate(b, tt, cv2.TM_CCOEFF_NORMED).max())
        out[k] = max(out.get(k, -1.0), mx)
    return out


def read_result(full_frame):
    """Is this the end-of-match RESULT screen, and what was the outcome.

    `full_frame` is the WHOLE game frame, not a crop -- the search window is a fraction of
    it. Returns {"is_result": True|False|None, "won": True|False|None,
                 "winner": float, "loser": float, "why": str}.

    None on either field means NOT READ: ask the paid model. `is_result` False is a real
    answer (no word is on screen); `won` None alongside `is_result` True means the screen is
    there but the two words scored too close to call, which has never been observed and is
    the abstention rather than a coin flip.

    HONEST LIMIT: the frame where the medallion is still animating in scores ~0.43 and comes
    back False. That is correct -- the banner is not up yet -- but it means a single frame
    grabbed at the wrong instant reads "not a result screen", so the caller polls.

    THE OUTCOME COMES FROM THE WORD, NOT FROM THE SCOREBOARD, and that is measured. run()
    prefers a score comparison because "won" cannot express a draw -- but on a RESULT screen
    orchestrator.ocr_scoreboard is not reliable: over the 76 harvested DRAW frames it reads
    both rows on only 12, and one of those 12 returns [0,1,5] against a scoreboard that
    plainly shows 1 0 1 / 0 1 1 (agent_progress/result-reader/draw_conflict.png). A wrong
    score is worse than no score, because run() would act on it. So this reader never
    supplies scores; it names the outcome directly.
    """
    sc = result_scores(full_frame)
    out = {"is_result": None, "outcome": None, "scores": dict(sc), "why": ""}
    if len(sc) < len(RESULT_CLASSES):
        out["why"] = (f"frame too small for the word templates "
                      f"({full_frame.width}px wide, floor {RESULT_MIN_FRAME_W:g})")
        return out
    best = max(sc, key=sc.get)
    top = sc[best]
    other = max(v for k, v in sc.items() if k != best)
    if top < RESULT_MIN:
        out["is_result"] = False
        out["why"] = f"no result word found (best {top:.3f} < {RESULT_MIN})"
        return out
    out["is_result"] = True
    if top - other < RESULT_MARGIN:
        ranked = ", ".join(f"{k} {v:.3f}" for k, v in sorted(sc.items(), key=lambda kv: -kv[1]))
        out["why"] = f"result screen, but the words are too close to call ({ranked})"
        return out
    out["outcome"] = RESULT_CLASSES[best]
    out["why"] = f"{best} -> {out['outcome']} ({top:.3f} against the next word at {other:.3f})"
    return out
