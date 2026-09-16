"""The reveal's announcement banner: PLAY BALL! and HOME RUN!, read locally.

WHY BOTH. The game prints the outcome on screen, so a home run does not have to
be inferred from a margin -- which needs BOTH cards read, and on 2026-09-16 a
sampler that spent its budget on the diamond could not say whether a hit was a
tie or a fielding subtraction because nothing captured the opponent's card.
And PLAY BALL! marks the reveal's ONSET, which CLAUDE.md's deal-timing entry
asks for by name: "a probe that starts at the deal's onset rather than the
gate's first poll".

THE SEARCH IS OVER A BAND, NOT AT AN ANCHOR (10.23). The banner animates in and
its letters shift; a fixed crop reads the wrong pixels the moment the thing
moves and reports that as "not sure".

TAKES THE WHOLE FRAME. Handed a crop, the templates would be larger than the
image and matchTemplate would either raise or -- worse -- be handed a resized
one and return a number anyway, which is 10.1's "a success path and a no-op path
with identical output". There is a floor on the input width for that reason.
"""
import os

import numpy as np

# The announcement sits in the centre of the table, above the played cards.
# Generous on purpose: the words are 328-578 px wide and move as they animate.
BAND = (0.28, 0.40, 0.75, 0.63)      # x0, y0, x1, y1 as fractions

# THE LIVE WIDTH IS 1920, NOT 2000. An earlier version of this comment said
# "orchestrator._fast_grab asks game_capture.grab for SETTLE_CALIBRATION_WIDTH =
# 2000, so the geometry that breaks this reader is the rig's own". THAT IS FALSE:
# SETTLE_CALIBRATION_WIDTH is 1920 (orchestrator.py), changed by 27cd4ae -- "the
# width it was actually measured at" -- and the 2000 was read out of a stale
# CLAUDE.md note instead of out of the source. At 1920 the scale factor is exactly
# 1.0 and this fix does nothing at all.
#
# IT IS STILL LOAD-BEARING, at the OTHER geometry the rig has actually produced.
# CLAUDE.md records 1867x1050 captures from this machine (the chiaki window grab),
# and on a HELD-OUT frame, against BANNER_MIN 0.80:
#
#     width   unscaled   scaled
#     1920     0.974      0.974     s = 1.0, no change, as it must be
#     1867     0.706      0.978     <- MISSED before, read after
#
# So the reader really was breaking on a real rig geometry; it was not the one
# originally claimed. 2000 stays in the test's width sweep as a plain
# scale-invariance case, not as a claim about what the rig captures.
#
# THE TEMPLATES ARE PIXELS AND THE BAND IS A FRACTION, SO THE TEMPLATES MUST SCALE.
# BAND scales with the capture; the bank is a fixed uint8 array handed to
# matchTemplate at native size. A 4% change in width therefore puts the word and
# the template at different scales and the correlation collapses. Measured on the
# two fixtures, against BANNER_MIN 0.80:
#
#     frame width   HOME RUN!   PLAY BALL!
#       1920          1.000       1.000     (their own source, so 1.000 proves nothing)
#       2000          0.517       0.638     <- MISSED
#       1867          0.679       0.723     <- MISSED
#       1600          0.328       0.197     <- MISSED
#
# CLAUDE.md section 3's named family: "a new window written in raw pixels works
# perfectly on the machine it was tuned on and silently lands on the wrong thing
# everywhere else". The 2000 row above is a scale-invariance case, not the rig's width.
REF_W = 1920                         # the geometry every template was cut at

# DERIVED, NOT WRITTEN. The floor exists so a CROP cannot be handed in, and it has
# to be the width at which the widest template still fits the band. It was 1200
# while BAND spans 0.47 and the widest template is 578 px, i.e. it needs 1230 --
# so on a frame 1200-1229 px wide the play_ball templates hit the size skip, `out`
# came back holding only home_run, read_banner's `if not s` guard did NOT fire
# because the dict was non-empty, and the reader answered about a ballot with a
# MISSING CLASS (10.31) with nothing in the detail to say so.
#
# Now that templates scale with the frame the arithmetic is scale-free, but the
# floor stays derived rather than written: a wider template added to the bank
# raises it automatically instead of silently reopening the same hole.
def _min_frame_w():
    widest = max(t.shape[1] for _l, t in _bank())
    return int(-(-widest // (BAND[2] - BAND[0])))      # ceil

# A FRAGMENT IS NOT A WORD, ENFORCED AT MATCH TIME AND NOT ONLY AT BUILD TIME.
# tools/build_banner_templates.py refuses to CUT anything narrower, but that
# guard lives in a script nothing runs at import -- so a template that became a
# fragment by any other route would still be matched. A tiny template correlates
# with anything: on the result reader a 14x39 crop made a turn frame with no
# banner read DRAW at 0.935 and every negative rose. Caught by a mutant that
# truncated the bank inside scores(), which the build-time floor could not see.
FRAGMENT_MIN_W = 300

# THE GATE, MEASURED (tools/banner_census.py), over 6,833 sampled frames from
# THREE OTHER SESSIONS -- not the frames the bank was cut from, which match their
# own source at 1.000 and prove nothing (CLAUDE.md 30).
#
#     non-banner frames   n=6800   p50 0.306   p99 0.331   MAX 0.589
#     real banners        n=  33   min 0.626   settled >= 0.80
#     at 0.80: 0 false positives in 6,833 frames, 0.21 clear of the non-banner MAX
#
# AND THE HEADROOM LOOKED LIKE 0.018 UNTIL THE FRAMES WERE OPENED. Scored naively
# the "negative" population reached 0.782 -- and all 18 frames between 0.60 and
# 0.80 turned out to be REAL HOME RUN banners caught mid-sweep ("HOME RU",
# "ME RUN!", "HOME R"). They are not false positives; they are the reader
# abstaining during the animation, which costs nothing because the settled banner
# holds for several frames. That is CLAUDE.md 31 exactly, and it is the second
# time on this project that opening the top-scoring negatives turned an apparently
# marginal gate into a comfortable one.
#
# 0.80 rather than the 0.694 midpoint: an abstention costs one poll, a false
# positive writes a home run that never happened into the record.
BANNER_MIN = 0.80

_BANK = None


def _bank():
    global _BANK
    if _BANK is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "reveal_banner_templates.npz")
        with np.load(p) as z:
            _BANK = [(k.split("__")[0], z[k]) for k in z.files]
    return _BANK


def scores(full_frame):
    """{label: best correlation} over the band. Raises on too small an input."""
    import cv2
    floor = _min_frame_w()
    if full_frame.width < floor:
        raise ValueError(
            f"reveal_banner needs the WHOLE frame; got {full_frame.width}px wide, "
            f"under the {floor}px floor. A crop cannot hold the templates.")
    w, h = full_frame.size
    x0, y0, x1, y1 = BAND
    band = np.asarray(full_frame.convert("L").crop(
        (int(w * x0), int(h * y0), int(w * x1), int(h * y1))), dtype=np.uint8)
    s = full_frame.width / REF_W
    out = {}
    for label, tpl in _bank():
        if s != 1.0:
            tpl = cv2.resize(tpl, (max(1, int(round(tpl.shape[1] * s))),
                                   max(1, int(round(tpl.shape[0] * s)))),
                             interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        if tpl.shape[0] > band.shape[0] or tpl.shape[1] > band.shape[1]:
            continue
        # IMMEDIATELY BEFORE THE MATCH, deliberately. Placed earlier it guards
        # what was LOADED rather than what is USED, and a mutant that truncated
        # the template after the check sailed straight through it.
        #
        # AND THE FLOOR SCALES WITH THE TEMPLATE. FRAGMENT_MIN_W is a PIXEL width
        # measured at REF_W; comparing a scaled template against the raw literal
        # would reject every legitimate template on a smaller capture and accept
        # fragments on a larger one.
        if tpl.shape[1] < FRAGMENT_MIN_W * s:
            continue
        r = cv2.matchTemplate(band, tpl, cv2.TM_CCOEFF_NORMED)
        out[label] = max(out.get(label, -1.0), float(r.max()))
    return out


def read_banner(full_frame):
    """(label, detail) -- 'home_run', 'play_ball', or (None, detail).

    None means NOT READ. It never guesses: the caller must treat an abstention as
    "no banner seen", never as "no home run happened".
    """
    try:
        s = scores(full_frame)
    except Exception as exc:
        return None, f"banner reader could not run ({exc})"
    if not s:
        return None, "no template fitted the band"
    label = max(s, key=s.get)
    if s[label] < BANNER_MIN:
        return None, f"best {label} {s[label]:.3f} under {BANNER_MIN}"
    return label, f"{label} {s[label]:.3f}"
