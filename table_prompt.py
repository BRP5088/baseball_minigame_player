"""Recognise the BASEBALL CARDS prompt specifically, not just "a prompt".

WHY THIS EXISTS
---------------
final_approach.prompt_score measures how much bright text sits in a fixed box
near the bottom centre of the screen. That answers "is an interaction prompt on
screen", which is not the question. Standing in front of Wanda produces
"Wanda Fuller [] Talk" in exactly that box and scores 0.375 — comfortably over
the 0.10 threshold — so a run that stopped at the wrong interactable was being
counted as having reached the table.

That mattered more than a mislabelled log line: the whole "six consecutive
successful runs" criterion is meaningless if a success can be a different NPC.

WHAT THIS DOES INSTEAD
----------------------
Correlates the prompt's TEXT REGION against reference crops of the real
"Baseball Cards [] Play ($50)" prompt taken from the recording. Different words
give a different pattern of strokes, so the correlation separates them even
though both are white text in the same place.
"""

import glob
import os
import re

import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter

import final_approach as fa

# The prompt text sits just below centre. Slightly wider than the brightness
# box so the whole phrase is included — the words are what distinguish it.
# Tall enough to contain the whole phrase with room to spare. The prompt does
# not sit at the same height in every capture: measured, the text spans
# y 0.559-0.677 in the recorded frames (1400x787) and y 0.589-0.700 live
# (1920x1080). The old box (0.605-0.660) clipped BOTH, and clipped them
# differently, so the two never correlated even when both plainly read
# "Baseball Cards [] Play ($50)". That is what made the detector reject a
# genuine arrival at 0.224.
TEXT_BOX = (0.36, 0.535, 0.72, 0.725)
THUMB = (240, 64)
VSHIFTS = tuple(range(-16, 17, 2))   # must span the live/recorded offset
REFERENCE_DIR = "test_fixtures/table_prompt"
# MEASURED 2026-09-04 over all 3262 archived demo frames, after this fired on a
# frame with NO prompt on screen.
#
#   score < 0.15        1817 frames   the bulk of the route
#   0.15 - 0.25           52 frames   INCLUDES A CONFIRMED FALSE POSITIVE
#   0.25 - 0.40          366 frames   genuine prompts start here
#   0.40 - 0.60           28 frames   trough
#   0.60 +               924 frames   clear prompts
#
# The two anchors are eyeballed, not inferred:
#   NEGATIVE  demos/walk2_pauses_20260828_044514/f_0049.22.jpg  score 0.1757
#             The quest log is open and its text supplies both the ink and the
#             stroke correlation. The user confirmed the player is not close
#             enough for the game to offer the prompt at all.
#   POSITIVE  demos/spawn_to_table_20260827_212516/f_0054.32.jpg score 0.3503
#             "Baseball Cards [] Play ($50)" plainly legible.
#
# 0.15 sat BELOW the confirmed negative, so at_table() returned True on frames
# with no prompt. That matters twice over: it is the authority for "arrived at
# the dealer table", and it gates the Square press that spends $50.
#
# 0.25 sits between the two anchors. The 0.20-0.30 band (57 frames) is NOT
# individually classified — if this needs tightening, classify those first.
# The risk is asymmetric and this errs the safe way: a false negative only
# keeps the character approaching, a false positive spends money at nothing.
#
# The docstring below still quotes a 0.669/0.860 gap from an older reference
# set, when the threshold was 0.79. Genuine approach frames now score 0.30-0.39,
# so do NOT restore that value — it would reject real prompts.
MATCH_MIN = 0.25           # stroke-shape correlation
# A correlation this high is believed when the OCR also reads at least ONE
# prompt word. Two arrivals on 2026-09-08 were scored failed with the prompt
# plainly on screen at 0.220-0.237 (dark captures). Over all 7,885 route
# frames on disk the score alone overlaps (negatives reach 0.218) but every
# negative at or above 0.17 reads 0 prompt words, one excepted at 0.189, while
# the missed prompts read 1-3: the conjunction fires on 0 route frames and
# recovers 16 of the 24 prompt frames under MATCH_MIN.
MATCH_MIN_WITH_WORD = 0.20
INK_MIN = 0.024            # fraction of the band that is thin bright stroke
STROKE_BRIGHT = 175
STROKE_LOCAL = 140
STROKE_WIN = 11
MIN_CONTRAST = 6.0        # std-dev of the raw patch; below this there is no text


def _raw_patch(img):
    """A TALL strip containing the prompt, wherever in it the prompt sits.

    Deliberately taller than the text. The prompt is not at a fixed height: it
    spans y 0.559-0.677 in the recorded frames and y 0.589-0.700 in a live
    capture, because frame_worker and compass.fast_capture frame the game
    slightly differently. The strip covers both, and the correlation searches
    vertically within it — see VSHIFTS, which must be wide enough to cover that
    0.027-of-height offset (about 9 rows at this thumbnail size). An earlier
    version searched only +-6 rows, which was not enough, and the detector
    rejected a genuine arrival at 0.224 while scoring recorded frames of the
    same prompt at 0.88.

    Locating the glyphs by brightness instead was tried and is worse: the
    dealer is a large white character sitting directly behind the text, so a
    brightness bounding box grabs her too.
    """
    w, h = img.size
    x0, y0, x1, y1 = TEXT_BOX
    c = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    return np.asarray(c.resize(THUMB, Image.BILINEAR), dtype=float)


def _stroke_mask(img):
    """Thin bright strokes only — the text, without what is behind it.

    Correlating the raw strip does not work, and the reason took a long time to
    see: the DEALER is a large white character sitting directly behind the
    prompt, and she is in a different pose in every capture. She dominates the
    correlation, so two frames both plainly reading "Baseball Cards [] Play
    ($50)" scored 0.084 against each other while the detector happily rejected a
    genuine arrival.

    Text is thin: bright pixels whose surroundings are dark. The dealer's face
    is bright pixels whose surroundings are also bright. That distinction
    removes her and keeps the words.
    """
    a = _raw_patch(img)
    if a.std() < 1.0:
        return np.zeros_like(a)
    local = uniform_filter(a, size=STROKE_WIN)
    return ((a > STROKE_BRIGHT) & (local < STROKE_LOCAL)).astype(float)


def ink(img):
    """How much of the band is text. Presence, independent of which words."""
    return float(_stroke_mask(img).mean())


def _text_patch(img):
    a = _stroke_mask(img)
    a = a - a.mean()
    n = np.linalg.norm(a)
    return a / n if n > 1e-6 else a


def _references():
    refs = []
    for f in sorted(glob.glob(os.path.join(REFERENCE_DIR, "*.jpg"))):
        refs.append(_text_patch(Image.open(f)))
    return refs


_CACHE = None
_DIR_CACHE = {}


def score_against(img, ref_dir):
    """Same comparison, against any directory of reference prompt crops.

    Used to recognise landmarks other than the table — Wanda Fuller's prompt in
    particular, which the route reaches reliably and which therefore makes a
    useful mid-route checkpoint.
    """
    if ref_dir not in _DIR_CACHE:
        _DIR_CACHE[ref_dir] = [_text_patch(Image.open(f))
                               for f in sorted(glob.glob(os.path.join(ref_dir, "*.jpg")))]
    refs = _DIR_CACHE[ref_dir]
    if not refs:
        raise RuntimeError(f"no reference crops in {ref_dir}/")
    if _raw_patch(img).std() < MIN_CONTRAST:
        return -1.0
    if fa.prompt_score(img) < fa.PROMPT_MIN:
        return -1.0
    a = _text_patch(img)
    return max(float((a * r).sum()) for r in refs)



def score(img, exclude=None):
    """How much this frame's prompt text looks like the Baseball Cards prompt.

    `exclude` drops one reference by index. That exists for testing: scoring a
    reference against a set containing itself returns exactly 1.0 and proves
    nothing, which is how a detector can look perfect while being unable to
    distinguish anything at all.
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = _references()
    if not _CACHE:
        raise RuntimeError(
            f"no reference crops in {REFERENCE_DIR}/ — cannot tell the baseball "
            "prompt from any other prompt, so no run can be called a success")
    refs = [r for i, r in enumerate(_CACHE) if i != exclude]
    if not refs:
        raise RuntimeError("every reference was excluded")
    a = _text_patch(img)
    best = -2.0
    for dy in VSHIFTS:
        rolled = np.roll(a, dy, axis=0)
        for r in refs:
            v = float((rolled * r).sum())
            if v > best:
                best = v
    return best


def at_table(img):
    """Is the BASEBALL CARDS prompt on screen?

    One correlation and one contrast guard. It took four wrong versions to get
    here, and each extra condition tried along the way turned out to be the
    problem rather than the fix:

    * A brightness gate ("is any prompt visible") was the original detector.
      Measured across both recordings it REJECTS 24 of 67 genuine table frames
      while negatives score as high as 0.375 — the prompt was plainly readable
      in frames it scored at 0.06. It is gone.

    * Requiring the table to beat Wanda's prompt by a margin looked principled
      and does not separate: negatives whose Wanda score is very negative
      produce a huge margin, so the rule overlaps.

    What actually separates is the correlation itself, once the references cover
    more than one viewing angle. With four references drawn from each of the two
    recordings, held-out table frames score at least 0.915 and everything else —
    the whole route before arrival, plus clean Wanda, occluded Wanda, and dark
    scenery — tops out at 0.669. The threshold sits in that gap.

    The earlier references all came from a single traversal, which is why the
    detector kept failing on frames from a slightly different position: it had
    learned one angle, not the prompt. It failed the same way a second time with
    references from two recordings, scoring a plainly legible prompt in the
    third at 0.566 against a 0.79 threshold.

    References now span all THREE traversals. Held-out table frames score at
    least 0.860 and everything else tops out at 0.669, so the threshold sits in
    a 0.19 gap rather than being squeezed against one side of it. If a fourth
    recording ever scores low, the fix is more reference viewpoints — not a
    lower threshold.
    """
    if _raw_patch(img).std() < MIN_CONTRAST:
        return False
    # TWO independent signals, because each alone has a known failure:
    #   ink   — how much text is present. Measured 0.032-0.037 at the table and
    #           at most 0.017 anywhere else, INCLUDING Wanda's prompt, which is
    #           simply shorter text. Says "a long prompt is here", not which.
    #   score — the shape of the strokes, which says which words they are.
    # THE INK GATE IS GONE FROM THE VERDICT (2026-09-07). It was the "long
    # prompt is here" signal against Wanda's shorter prompt; Wanda now scores
    # 0.10 on these references, and every negative on disk tops out at 0.176
    # against MATCH_MIN 0.25 (693 clean-node frames 0.172, the quest-log anchor
    # 0.176, the fixture negatives 0.10). What the gate DID reject: 21 route
    # frames with the prompt plainly on screen (dealer_circle, ink 0.006-0.024),
    # the recorded arm's own arrival (trial 6, score 0.311, ink 0.006), and all
    # five readings at the prompt zone's edge (score 0.31-0.47, ink 0.011) --
    # white text over a bright body, a light table or a grey wall keeps the
    # correlation and loses the strokes. ink() stays as a signal for the sweep.
    s = score(img)
    if s >= MATCH_MIN:
        return True
    words = ocr_words(img)
    if words >= OCR_MIN_WORDS:
        return True
    if s >= MATCH_MIN_WITH_WORD and words >= 1:
        return True
    return ocr_reads_fee(img)
# THE STROKE MASK CANNOT SEE WHITE TEXT OVER A BRIGHT BACKGROUND, BY
# CONSTRUCTION. It keeps a pixel only if it is > STROKE_BRIGHT and its 11x11
# neighbourhood averages < STROKE_LOCAL -- the rule that removes the dealer's
# white face -- so the prompt over the LIGHT TABLE TOP (camera pitched down
# after walking into the table; goal-leg A/B trial 1, 2026-09-07, score -0.001,
# ink 0.0001) and the prompt over the DEALER'S BODY (demos/dealer_circle, 26
# frames) both score under MATCH_MIN with the prompt plainly on screen.
# Local-contrast masks were measured over 3,937 frames and refused: no delta
# clears the gate on the bright-table frame, and every delta loses old
# positives or admits new ones (tools/prompt_mask_ab.py).
#
# OCR is a different instrument. Measured over the same corpora plus 43
# table-leg end frames (tools/prompt_ocr_ab.py, overnight/census/prompt_ocr_ab.json):
#
#     words >= 2      recall on the 1289 frames the mask accepts   341   (26%)
#                     false positives on 693 frames at non-table nodes   0
#                     the quest-log false-positive anchor               0 words
#                     route frames the mask rejects                 26 hits, all
#                       dealer_circle frames whose OCR text reads the prompt
#
# So it is strictly an ADDITION: the mask stays first and OCR runs only when the
# mask says no. It is scale-sensitive (the recorded anchor reads one word at 3x
# and four at 2x or 4x), which is why its recall alone is poor and why it must
# never replace the mask. tesserocr is main-thread-only (CLAUDE.md §3); at_table
# is called from the main thread everywhere in production.
OCR_UPSCALE = 3
OCR_PSM = 6              # block mode; PSM 7 read nothing on the anchors
OCR_FUZZ = 0.75          # "Basehal" / "Candsy" on the bright-table frame
OCR_MIN_WORDS = 2        # of baseball / cards / play; 0 false positives at 2
OCR_WORDS = ("baseball", "cards", "play")


def ocr_words(img):
    """How many of OCR_WORDS the prompt band reads, over both polarities."""
    import difflib
    import re
    from PIL import ImageOps
    import ocr_glyphs
    w, h = img.size
    x0, y0, x1, y1 = TEXT_BOX
    c = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    c = c.resize((c.width * OCR_UPSCALE, c.height * OCR_UPSCALE), Image.BICUBIC)
    best = 0
    for cand in (c, ImageOps.invert(c)):
        txt = ocr_glyphs.image_to_text(cand, OCR_PSM, None) or ""
        toks = re.sub(r"[^a-z0-9$() ]+", " ", txt.lower().replace("|", " ")).split()
        hits = sum(1 for wanted in OCR_WORDS
                   if any(difflib.SequenceMatcher(None, wanted, t).ratio() >= OCR_FUZZ
                          for t in toks))
        best = max(best, hits)
    return best



# THE FEE TOKEN, "$50" / "(50)", IS THE SAFEST ADDITION ON RECORD (2026-09-08).
# Three batch-13 trial-5 arrivals stood at the prompt on a dark frame and were
# scored FAILED: score 0.147 under MATCH_MIN_WITH_WORD with one word. Measured
# over EVERY route frame on disk, 3x, PSM 6, both polarities, on FEE_BOX
# (overnight/census/at_table_ocr_tokens_20260908.json):
#
#     "$50" or "(50)" read on route frames (k < 185)    0 of 7,885
#     read on the known prompt frames                   58 of 81
#     prompt WORDS >= 1 on the same route frames        24 of 7,885
#
# So it runs LAST, only after the mask, the two-word rule and the
# word-plus-score rule have all said no, and it reads the census band exactly
# -- FEE_BOX is not TEXT_BOX, and the zero was measured on FEE_BOX.
FEE_BOX = (0.30, 0.58, 0.72, 0.70)
FEE_UPSCALE = 3
_FEE_RE = re.compile(r"\$ ?50|\(\s*\$?\s*5\s*0\s*\)|50\)|\(50")


def ocr_reads_fee(img):
    """Does the prompt band read the fee, "$50" or "(50)", in either polarity?"""
    from PIL import ImageOps
    import ocr_glyphs
    w, h = img.size
    x0, y0, x1, y1 = FEE_BOX
    c = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    c = c.resize((c.width * FEE_UPSCALE, c.height * FEE_UPSCALE), Image.BICUBIC)
    for cand in (c, ImageOps.invert(c)):
        txt = (ocr_glyphs.image_to_text(cand, OCR_PSM, None) or "").lower()
        if _FEE_RE.search(txt):
            return True
    return False
