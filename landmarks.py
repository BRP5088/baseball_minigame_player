"""Recognise the walk's waypoints from ONE captured frame.

WHY THIS EXISTS
---------------
reset_walk.walk_route() prints a CHECKPOINT line and saves a frame at each
landmark, and then does absolutely nothing with either. On 2026-08-26 the walk
"succeeded" while the detective stood facing a blank wall: every checkpoint
printed, every frame saved, the run reported arrival, and the frames showed
plasterwork. A failed walk and a successful walk produced byte-identical logs.

That is worse than an unreliable walk. reset_walk's own docstring says so --
"an 80%-reliable walk with 100%-reliable checkpoints is a working system; a
100%-reliable walk with no checkpoints is one patch away from silently
breaking" -- but the checkpoints were only ever comments. This module is the
missing half: it turns each CHECKPOINT line into an actual assertion.

THE DESIGN RULE THAT MATTERS
----------------------------
A detector that fires on almost everything is worse than no detector, because
it converts a visible failure into an invisible one. So every function here
would rather abstain (None) than guess, and every threshold below sits in a
gap that was MEASURED against labelled frames, with the numbers written down
next to it. Where no gap was found, the function says so by returning None
forever rather than shipping a coin flip -- see in_lb_interior.

    at_baseball_table(img) -> True / False / None    strong; the one that gates
    sees_lb_building(img)  -> True / None            confirms only; never denies
    in_lb_interior(img)    -> None                   NOT IMPLEMENTABLE, see below

THE GAMEPLAY GATE COMES FIRST
-----------------------------
screenshot_log/reset_load_00.jpg is a LOADING SCREEN whose artwork is the
Little & Big building, with "LITTLE & BIG", "L&B" and "LITTLE & BIG BAR" all
larger and crisper than they ever are in the world. Any sign-reading detector
fires TRUE on it -- while the game is loading, i.e. exactly when the walk has
gone wrong. So nothing here answers a landmark question until the compass HUD
proves we are in the walkable world at all. That single gate also throws out
the in-match card table, which is where a stale frame would otherwise come
from.

MEASUREMENTS
------------
Labelled frames from three recorded walks -- 60 @2000x1292 windowed, 652
@1400x904 windowed, 378 @1400x904 FULLSCREEN (how the system captures now) --
plus screenshot_log/ (1937 in-match frames, 4 reset_facing_*, 14 reset_load_*).
A sampled sweep of 156 + 95 of those frames gave:

  at_baseball_table   37/37 at-table frames True; 0 false positives across 108
                      world frames that are not the table; abstained on all 11
                      off-world frames. (The 37th was found BY the detector on
                      a frame this analysis had mislabelled -- the prompt was
                      showing 0.7s earlier than the hand-drawn boundary said.)
  sees_lb_building    20/38 shop-front frames confirmed; 0 false positives
                      across 57 frames that are not the shop front, the
                      loading screen included. Recall is proximity-dependent:
                      13/19 once the facade fills the street, 1/9 while it is
                      still down the block. Hence confirm-only.
  in_lb_interior      no separation found at all -- see the function.

test_landmarks.py re-derives the gate margin and both landmark verdicts from a
34-frame fixture set, and has been mutation-checked: each detector, each
threshold and the prompt box were broken in turn and the test caught all ten.

HOW TO WIRE THIS IN (reset_walk.py is yours to edit, not mine)
--------------------------------------------------------------
walk_route() already captures a frame at each checkpoint and saves it. The
change is to look at it -- roughly, in the `if check:` block:

    verdict = {"lb_building": landmarks.sees_lb_building,
               "lb_interior": landmarks.in_lb_interior,
               "start_game_text": landmarks.at_baseball_table}[check](shot)
    if verdict is not True:
        raise WalkError(f"checkpoint {check}: not confirmed ({verdict!r}) -- "
                        f"see {path}")

Note `is not True`, so None stops the walk too. That is deliberate and matches
walk_route's existing stance: an unconfirmed position is not a position worth
pressing buttons from, and an aborted walk costs nothing. in_lb_interior always
returns None, so wiring it up as written would abort every walk -- either skip
that checkpoint or treat it as advisory until there is something real behind
it. Both other checkpoints are safe to enforce.
"""
import re

import numpy as np
from PIL import Image, ImageFilter

# --- geometry ---------------------------------------------------------------
# All boxes are FRACTIONS of the captured frame, because the same landmark has
# to be found in three different framings: the chiaki window at 2000x1292, the
# whole desktop at 1400x904, and fullscreen at 1400x904. Measured prompt-text
# bounding boxes in those three, as fractions:
#     demo   x 0.388-0.585   y 0.631-0.652
#     demo2  x 0.384-0.587   y 0.631-0.650
#     demo3  x 0.396-0.604   y 0.619-0.644
# The box below contains all three with margin on every side.
PROMPT_BOX = (0.36, 0.605, 0.64, 0.660)

# The compass tick bar, the one HUD element that is drawn across every world
# frame and no other screen. Same band compass.COMPASS_BOX_FRAC uses, opened up
# slightly top and bottom so a frame does not fall out of gameplay because the
# bar sat two pixels low.
HUD_BOX = (0.27, 0.115, 0.72, 0.190)

# The shop front. The sign climbs the frame as you approach -- it is low and
# small at 12m and clipped by the top edge at 2m -- so this box is deliberately
# tall. x starts at 0.28 to keep the quest-log overlay out of the crop.
LB_BOX = (0.28, 0.10, 0.78, 0.55)

# --- thresholds, each with the gap it sits in -------------------------------
# HUD_WHITE/HUD_MIN_RUN: fraction of the widest bright row in HUD_BOX.
#   world frames (n=1090, every frame of all three demos): 0.387 .. 0.659
#   non-world frames: loading artwork 0.000; in-match card UI (n=49) max 0.204
#   -> gap 0.204 .. 0.387, threshold in the middle.
HUD_WHITE = 170
HUD_MIN_RUN = 0.30
# ...and the band must not be SOLID bright, or a white flash (or a blown-out
# capture) satisfies "widest bright row" trivially. The compass bar is a hairline
# with scene behind it, so the band is mostly not bright:
#   world frames: 0.023 .. 0.117 of the band bright
#   a uniform white frame: 1.000
#   -> 0.40 is 3.4x the worst real frame and far under a flash.
HUD_MAX_FILL = 0.40

# PROMPT_WHITE: the prompt is drawn near-white. Measured glyph fill >= 215;
# the L&B sign by contrast peaks at 135-145, which is why that landmark cannot
# use the same trick (see _local_contrast).
PROMPT_WHITE = 200

# PROMPT_GATE: cheap "there is nothing bright enough to be text here" test, so
# the common case costs no OCR. Purely a speed gate -- it is set far below the
# positives so it cannot be the thing that decides.
#   frames at the table: bright fraction 0.082 .. 0.142 (n=263, min 0.082)
#   -> 0.03 is under half the smallest positive; 0 positives lost at 0.05 even.
PROMPT_GATE = 0.03

# Aspect ratio of every capture this has been validated against: 2000/1292 and
# 1400/904 are both 1.548. Outside this band the fractional boxes point
# somewhere else entirely and the honest answer is "cannot tell".
ASPECT_RANGE = (1.30, 1.90)
MIN_WIDTH = 600


def _gray(img):
    """PIL image -> 8-bit grayscale. The game renders in black and white, so
    colour carries no information here and every check is a luminance check."""
    return img if img.mode == "L" else img.convert("L")


def _crop(img, box):
    w, h = img.size
    return img.crop((int(box[0] * w), int(box[1] * h),
                     int(box[2] * w), int(box[3] * h)))


def _usable(img):
    """False when the fractional boxes cannot be trusted to point at anything."""
    w, h = img.size
    if w < MIN_WIDTH or h < 1:
        return False
    return ASPECT_RANGE[0] <= w / h <= ASPECT_RANGE[1]


def _local_contrast(crop, radius=14, k=11):
    """Binarise by contrast against a blurred copy, not by absolute brightness.

    The interaction prompt is near-white (>=215) and a flat threshold reads it
    perfectly. The Little & Big sign is not: its letters top out at 135-145
    because the street is lit by two gas lamps at night, so a flat threshold at
    190 erases the sign completely -- measured, that is why the first attempt
    at sees_lb_building returned nothing at all. Subtracting a blurred copy
    keeps the letters and drops the lighting.

    Returns black-on-white, which is the polarity tesseract expects.
    """
    a = np.asarray(crop, dtype=np.float32)
    bg = np.asarray(crop.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
    return Image.fromarray(np.where(a - bg > k, 0, 255).astype(np.uint8))


def hud_score(img):
    """Fraction of the widest bright row in the compass band. See HUD_MIN_RUN."""
    a = np.asarray(_crop(_gray(img), HUD_BOX), dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float((a >= HUD_WHITE).mean(axis=1).max())


def hud_fill(img):
    """Fraction of the whole compass band that is bright. See HUD_MAX_FILL."""
    a = np.asarray(_crop(_gray(img), HUD_BOX), dtype=np.int16)
    if a.size == 0:
        return 1.0
    return float((a >= HUD_WHITE).mean())


def in_gameplay(img):
    """True when the compass HUD is drawn, i.e. we are in the walkable world.

    Not a landmark -- a precondition. A loading screen, the pause menu and the
    in-match card table all fail it, and on any of those the landmark questions
    are unanswerable rather than false.

    Two conditions, because one is not enough: a long bright ROW (the bar is
    there) and a band that is mostly NOT bright (it is a bar and not a white
    screen). The second exists because the first alone accepts any blown-out
    frame, which is a plausible capture glitch and would wave a garbage frame
    straight through to the landmark checks.
    """
    if not _usable(img):
        return False
    return hud_score(img) >= HUD_MIN_RUN and hud_fill(img) <= HUD_MAX_FILL


def _normalise(text):
    return re.sub(r"[^a-z0-9&$()]", "", text.lower())


def read_prompt(img):
    """The interaction prompt at screen centre, as tesseract reads it.

    ONE tesseract call on a 392x50 crop (upscaled 2x). Measured cost 0.6-0.9s
    on an idle machine, and it is only paid when PROMPT_GATE has already found
    something bright enough to be text -- which is roughly half of all frames
    and, importantly, all of the positive ones.

    Returns '' when the gate rejected the frame outright.
    """
    import pytesseract

    crop = _crop(_gray(img), PROMPT_BOX)
    a = np.asarray(crop, dtype=np.int16)
    if a.size == 0 or float((a >= PROMPT_WHITE).mean()) < PROMPT_GATE:
        return ""
    b = np.where(a >= PROMPT_WHITE, 0, 255).astype(np.uint8)
    big = Image.fromarray(b).resize((crop.width * 2, crop.height * 2),
                                    Image.LANCZOS)
    return pytesseract.image_to_string(big, config="--psm 7").strip()


# What tesseract actually returns for this prompt, across the frames measured:
#   'Baseball Cards - playe$s@t'    'Baseball Card . a. an)'
#   'Baseball Cards Play Seow'      'Baseball carafh Ges 265)'
#   'Baseball any bia ($50)'        'Baseut Cands " Play ($50)'
# The name usually survives intact and the price usually does not -- except on
# the frame from the unrelated session, where it is the other way round. So
# neither half can be required alone. The rule is: the name, or any two of the
# four fragments. Two is what keeps it off the other prompts in the game, which
# read "Typewriter [] Save" in the same font at the same place and share none
# of these fragments.
_PROMPT_STRONG = "baseball"
_PROMPT_PARTS = ("base", "card", "play", "50")
_PROMPT_MIN_PARTS = 2


def prompt_says_baseball(text):
    """Does this OCR output name the baseball-card minigame? See above."""
    norm = _normalise(text)
    if _PROMPT_STRONG in norm:
        return True
    return sum(p in norm for p in _PROMPT_PARTS) >= _PROMPT_MIN_PARTS


def at_baseball_table(img):
    """Is the player standing at the baseball-card table, prompt showing?

    THE ONE THAT MATTERS. This is the checkpoint that gates pressing Square to
    spend $50, so it is the only place where a wrong answer costs anything.

    The signal is the prompt text itself, "Baseball Cards [] Play ($50)". It is
    the strongest available because it is white text at a predictable place and
    it exists ONLY here -- the game's other interaction prompts sit in the same
    font at the same spot and are rejected by the WORD, never by the geometry.
    That distinction is the whole point: two seconds from the spawn point the
    typewriter shows "Typewriter [] Save" in exactly this position, so anything
    keying on "white text in the middle of the screen" reports arrival before
    the walk has even started.

    Returns True / False, or None when the frame cannot answer the question
    (wrong shape, or not a world frame at all -- see in_gameplay).
    """
    if not _usable(img):
        return None
    if not in_gameplay(img):
        return None
    return prompt_says_baseball(read_prompt(img))


# Tesseract's rendering of the two signs on the shop front, over the frames
# measured: the valance "L & B" comes back as LeB, Le B, L&B, L&eB, Lab -- the
# stylised ampersand is never read as '&' twice running. The cartouche
# "LITTLE & BIG" comes back as fragments: UTTLe, Tle, TTLE, BIG. So the rule
# accepts an L and a B separated by one ampersand-ish glyph, or a distinctive
# fragment of the cartouche. Word boundaries on both sides keep it from firing
# inside a longer noise token.
_LB_VALANCE = re.compile(r"(?<![a-z])l\W{0,2}[&eé«¢ca]\W{0,2}b(?![a-z])")
_LB_CARTOUCHE = re.compile(r"(?<![a-z])(?:little|[ut]ttle|ttle|big)(?![a-z])")


def read_lb_sign(img):
    """The shop front, as tesseract reads it. ONE call, --psm 11 (sparse text).

    Costs 1.2-1.5s on an idle machine because the crop is large and sparse-text
    mode is slow. That is affordable once per walk and nowhere else.
    """
    import pytesseract

    crop = _crop(_gray(img), LB_BOX)
    if crop.width < 40 or crop.height < 40:
        return ""
    return pytesseract.image_to_string(_local_contrast(crop),
                                       config="--psm 11").strip()


def sees_lb_building(img):
    """Is the Little & Big shop front ahead, close enough to read its sign?

    CONFIRMS ONLY -- returns True or None, never False. That asymmetry is the
    measurement, not laziness. Over 38 shop-front frames spanning the whole
    approach it confirmed 20; broken down by distance that is 13/19 once the
    facade fills the street and 1/9 while it is still down the block, because
    at that range the whole cartouche is about forty pixels wide. Against 57
    frames that are NOT the shop front -- including the interior, the table,
    and both loading screens -- it confirmed none. So a True means the building
    is there and a None means nothing at all, which is why there is no False.

    Treat None as "not confirmed" and stop, exactly as reset_walk's docstring
    already prescribes -- a walk that has drifted is harmless, a walk that
    drifts and keeps pressing buttons is not.
    """
    if not _usable(img) or not in_gameplay(img):
        return None
    text = read_lb_sign(img).lower()
    flat = re.sub(r"[^a-z&é«¢ ]", " ", text)
    if _LB_VALANCE.search(flat) or _LB_CARTOUCHE.search(flat):
        return True
    return None


def in_lb_interior(img):
    """NOT IMPLEMENTED, ON PURPOSE. Always None.

    The inside of Little & Big carries no text, and nothing else about it is
    distinctive enough to separate from the rest of the route. Eight global
    statistics were measured over all 1090 labelled frames -- mean, std,
    lower-third mean and std, upper-band mean, gradient energy, bright fraction
    and dark fraction -- and the interior's p5..p95 range sits INSIDE the
    p5..p95 range of the non-landmark frames on every single one. The clearest,
    frame mean, gives interior 26.9..73.2 against non-landmark 24.7..73.4:
    those are the same distribution.

    The reason is structural rather than a tuning failure. The L&B interior is
    a dim, wood-panelled room with warm lamps and a patterned floor, and so is
    the detective's own office two minutes earlier on the same route. The one
    genuinely distinctive fixture, the arc of oval portraits, is out of frame
    in half the interior frames because the run-to-run spread in where the
    player ends up is wider than the room.

    A brightness-and-texture rule COULD be fitted to the frames above. It would
    also fire on the office, which is the specific failure this module exists
    to make visible, so it is not shipped. If this checkpoint is wanted, the
    honest fix is a distinctive marker chosen in-game -- stand somewhere the
    dartboard or the jukebox is reliably in frame -- not a better statistic.
    """
    return None


def describe(img):
    """Everything the detectors looked at, for debugging a checkpoint failure.

    No decisions, just the raw numbers and strings, so a saved frame can be
    interrogated after the fact without re-running the walk. Costs three
    tesseract calls, which is fine for a human staring at one bad frame and
    is why walk_route should call the individual detectors instead.
    """
    usable = _usable(img)
    out = {
        "size": img.size,
        "usable": usable,
        "hud_score": round(hud_score(img), 4) if usable else None,
        "hud_fill": round(hud_fill(img), 4) if usable else None,
        "in_gameplay": in_gameplay(img),
        "prompt_text": "",
        "lb_sign_text": "",
        "sees_lb_building": sees_lb_building(img),
        "at_baseball_table": at_baseball_table(img),
        "in_lb_interior": in_lb_interior(img),
    }
    if out["in_gameplay"]:
        out["prompt_text"] = read_prompt(img)
        out["lb_sign_text"] = " ".join(read_lb_sign(img).split())
    return out
