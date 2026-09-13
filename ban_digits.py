"""THE POWER DIGIT AND THE SHIELD DIGIT, read off a card in the BAN GRID.

WHY THIS EXISTS. Every other field of a ban card has a local reader; these two did not.
orchestrator.ocr_ban_card_name resolves the NAME BANNER against KNOWN_BAN_ROSTER and gets
power and secondary from the roster -- which works only for a card already catalogued, and
the user's requirement is explicitly forward-looking ("when the player unlocks this, this
script needs to detect them"). A card the roster has never seen has to be read off its own
face. orchestrator's own docstring records that tesseract cannot read this font at all --
"7 thresholds x 5 psm modes, zero correct reads" -- and CLAUDE.md section 3 records that the
HAND's digit bank is right on only 3 of 7 ban cards. Both are true. Neither is the whole
story: the glyphs are SPRITES, and a sprite is matched, not recognised.

THE METHOD, and the two rules it exists to obey.

  SEARCH FOR THE SPRITE (CLAUDE.md 10.23). Nothing is cropped at an anchor. Both readers
  matchTemplate over a generous window in CARD-BOX coordinates, so the answer survives the
  badge moving -- and it does move: the cursor lifts a card and the badges ride with it.

  NATIVE SIZE, ONE TEMPLATE PER EXAMPLE, NEVER AVERAGED (CLAUDE.md 10.30). The bank holds
  12 separate crops per digit, cut from 25 different cards; the score is the max over them.
  The one resize that happens is by the CARD BOX's own width against REF_CARD_W, because a
  2000x1125 capture draws the same sprite ~5% larger -- that is scaling to the object, not
  the "stretch every word to one box" mistake 10.30 is about.

TWO STAGES, AND THE REASON IS MEASURED. A first version matched the whole sprite and took
the digit off the winning template. Leave-one-card-out over 913 cells it scored 591 right
and 322 WRONG, with the two score populations flat on top of each other (correct min 0.869,
wrong max 0.968) -- one population, no gate (10.4). The confusion says why: 6 read as 8 on
119 cells and 7 as 4 on 120. A whole power disc is ~85% white circle, so TM_CCOEFF_NORMED
is dominated by the circle and the digit barely moves the number.

So: LOCATE with the whole sprite -- every digit shares the outline, so the location is
reliable even when the digit choice is not -- then CLASSIFY on the GLYPH ALONE at the
located position, +-3 px. The located score answers "is there a badge at all"; the glyph
score answers "which digit". Same bank, two crops of it.

WHAT IT MEASURES, leave-one-CARD-out (a template never saw the card it is scored on, let
alone the frame), 913 cells over 25 cards, labels from the name banner via the roster:

    POWER    913 right   0 wrong   0 abstained
    SHIELD   913 right   0 wrong   0 abstained          (427 of them genuinely secondary 0)

EVERY GATE SITS IN AN EMPTY BAND BETWEEN TWO MEASURED POPULATIONS (10.4):

    power glyph score    locked cards          n=  500   max 0.454
                         tactics cards         n=  394   max 0.429
                         A DIGIT NOT IN THE BANK  n=262   max 0.824
                         a real digit          n=1,105   MIN 0.911   <- band 0.824 .. 0.911
    shield sprite score  tactics cards         n=  394   max 0.471
                         a card with NO badge (secondary 0, real pixels, an empty corner)
                                               n=  427   max 0.564
                         locked cards          n=  500   max 0.576
                         a real badge          n=  486   MIN 0.822   <- band 0.576 .. 0.822
    shield glyph score   A DIGIT NOT IN THE BANK  n=153   max 0.914
                         a real badge          n=  153   MIN 0.982   <- band 0.914 .. 0.982

The shield's presence gate is TWO-SIDED because its band is only 0.25 wide and the two
errors do not cost the same: this reader's answer picks which card to ban in a match that
costs $50, so a score inside the band abstains instead of guessing "no badge". Zero held-out
cells land there today.

THE MISSING-CLASS ROWS ARE THE POINT OF THE HIGH GATES, and they are measured, not feared.
CLAUDE.md 10.31: a classifier with a missing class does not abstain, it manufactures an
answer. Dropping one digit from the bank and re-reading the cells that really are that digit
is the direct test. At a power gate of 0.70 -- which separates locked and tactics cards
perfectly well -- a held-out 8 read as a 5 at 0.809, on all three power-8 cards in the
corpus. At 0.87 all 262 such cells are refused and not one of the 1,105 held-out correct
reads is.

WHAT THIS DOES NOT DO, STATED EXACTLY, because the shield's cheap failure is silent.

A LOCKED card is refused here rather than left to the caller: ban_grid.is_locked is one std
over the card crop and its two populations do not overlap, so the check is free and the
alternative is a guard the caller has to remember (this project's signature bug). Both
readers return None on a locked card, and on one is_locked is unsure about.

A TACTICS card is NOT refused, and read_shield answers 0 on it. Measured on
test_fixtures/ban_grid/tactics_row.png: every cell scores 0.42-0.51, well inside the
absent band, so it reads "no badge" -- which is true of the pixels and meaningless as a
secondary. The caller separates tactics with ban_grid.read_card_type.

A CARD BOX THAT IS NOT ON A CARD -- a mid-scroll frame, where the row has slid half a card
-- reads "no badge" for the same reason. NO THRESHOLD ON THE SPRITE SCORE CAN SEPARATE
THOSE: a displaced window scores 0.40 and a genuine secondary-0 card scores up to 0.564,
one population. read_power DOES catch it (it abstained on exactly this, the single
abstention in 1,105 held-out cells, at 0.486 against a gate of 0.70), so a caller that
wants a trustworthy shield 0 should require read_power to have answered on the same cell.

SECONDARY 0 IS A REAL CLASS AND IS NOT IN THE BANK, deliberately. It is the ABSENCE of the
sprite: the mean of 400 disc-aligned secondary-0 cards has no badge in it and the corner
behind it is mush, because it is 400 different pieces of card art. A template of "nothing"
would be a template of one card's art. 0 is answered by the presence gate, the way
local_hand.read_shield answers it.
"""
import os
import numpy as np

import ban_grid as bg

_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(_HERE, "ban_digit_templates.npz")

# The card-box width, in pixels, that the bank was cut at (0.1155 * 1920). Templates are
# NATIVE there and are resized by card_width / REF_CARD_W at any other capture size.
REF_CARD_W = 221.0

# Search windows, as fractions of the CARD BOX. Measured positions, with slack either side:
# the disc spans x 0.743-0.923 / y 0.060-0.185 of the card box and the shield
# x 0.753-0.943 / y 0.207-0.367 (from a disc-aligned mean over 400 examples per class).
POWER_WIN = (0.62, 0.00, 1.00, 0.27)
SHIELD_WIN = (0.60, 0.12, 1.00, 0.46)

# The glyph, as a fraction of the WHOLE-SPRITE template. Swept over four boxes each on 180
# dev cells: every box scored 180/180 on both fields, so this is not a tuning knob and the
# middle one ships.
POWER_GLYPH = (0.28, 0.24, 0.72, 0.76)
SHIELD_GLYPH = (0.34, 0.28, 0.86, 0.80)

# IS THIS WINDOW ON A CARD? A POSITIVE ANSWER, NOT AN ABSENCE.
#
# read_shield used to answer 0 whenever no badge sprite cleared the gate -- and a window that
# is NOT ON A CARD scores the same ~0.40 as a card that simply has no badge. Measured: a
# displaced window reaches 0.564 and a genuine no-badge card tops out at 0.564 too. ONE
# POPULATION; no threshold on that quantity can separate them, which is what the first
# version of this module recorded as its honest limit.
#
# WHAT IT COSTS, measured by shifting a real card box and re-reading 250 labelled cells:
#
#     shift (card heights)   power right/WRONG/abstain   shield right/WRONG/abstain
#      0.00 .. +-0.05             250 / 0 /   0               250 /   0 /  0
#           +-0.08               249 / 0 /   1 (and 4/0/246)  249 /   0 /  1
#           +-0.10 and beyond      0 / 0 / 250                116 / 134 /  0
#
# read_power is SAFE at every displacement -- it abstains. read_shield answers "no badge" for
# 134 of 250 cards that HAVE one. That is the confidently-wrong answer being closed here, and
# it is why only read_shield pays for this check.
#
# THE LANDMARK IS THE CARD'S TOP-LEFT CORNER, and it had to be a 2D corner. Six boxes were
# swept (`agent_progress/ban-digit-bank/oncard_sweep.py`): the top-RIGHT corner and the top
# strip both fail, scoring up to 0.997 on a window shifted UP, because each is dominated by a
# straight border RUN and a line looks the same at every y. The top-left corner carries the
# rounded arc AND the type ribbon's pointed tip, which only fit together in one place.
#
# Matched in a TINY window on purpose. The question is not "is there a card near here" but
# "is the card WHERE THE BOX SAYS IT IS"; a generous search finds the displaced card and
# answers yes, which is the bug. At a search slack of 0.080 card heights the displaced
# population climbs back to 0.989.
CORNER_CUT = (-0.02, -0.015, 0.24, 0.130)
CORNER_SEARCH = 0.020       # card widths/heights of slack around the cut

# THE GATES. Each sits in an EMPTY BAND between two measured populations (10.4), and each
# is set so that a digit THE BANK DOES NOT HOLD abstains instead of becoming the nearest
# digit it does hold -- CLAUDE.md 10.31, measured here rather than assumed. Dropping one
# digit's templates and re-reading the cells that really are that digit:
#
#     power glyph      missing class  n=262   MAX 0.824   |   a real read  n=1,105  MIN 0.911
#     shield glyph     missing class  n=153   MAX 0.914   |   a real badge n=  153  MIN 0.982
#
# Both bands are empty. At 0.70 the power gate let a held-out 8 read as a 5 at 0.809, on all
# three power-8 cards; at 0.87 all 262 missing-class cells are refused and NOT ONE of the
# 1,105 held-out correct reads is (their minimum is 0.911).
# ON_CARD_MIN, and the three populations it sits between (n=1,200 player cells with their own
# card dropped, 200 owned tactics cells, 1,200 cells x 12 displacements):
#
#     displaced by >= 0.08 card heights   max 0.708      <- the shifts that break the read
#     an owned TACTICS card               max 0.728      <- on a card, but it has no secondary
#     ON_CARD_MIN 0.79
#     a player card                       MIN 0.859      (p01 0.915, median 0.988)
#
# Displacement UNDER 0.08 is deliberately accepted (+0.05 reaches 0.931): the reader is
# 250 / 0 / 0 there, so rejecting it would be refusing reads that are right. A LOCKED card
# scores up to 0.979 and that is correct -- it IS on a card -- but is_locked refuses those
# first. The single lowest player cell in 1,200 is -0.173, and it is the known mid-scroll
# cell (test_fixtures/ban_digits/midscroll_1920.jpg): the detector found the one genuinely
# displaced box in the corpus by itself.
ON_CARD_MIN = 0.79
POWER_MIN = 0.87            # in the empty band 0.824 .. 0.911
SHIELD_ABSENT_MAX = 0.65    # in the empty band 0.576 .. 0.822 (the SPRITE score: is there a badge)
SHIELD_PRESENT_MIN = 0.75   # ditto; between them is "cannot say", not "no badge"
SHIELD_GLYPH_MIN = 0.95     # in the empty band 0.914 .. 0.982 (WHICH digit is in the badge)
GLYPH_PAD = 3               # px of slack around the located sprite, before scaling

# CLAUDE.md section 4: player powers run 4-9 and there is no 1, 2 or 3 power card in the
# game, so a digit outside this is a misread whatever it scored. Cheap, and it is the rule
# that catches a search that landed on the card ART -- several cards carry a stadium fence
# with a legible 5 and 4 painted on it, inside the shield's own search window.
POWER_RANGE = (4, 9)

_GLYPH = {"power": POWER_GLYPH, "shield": SHIELD_GLYPH, "corner": (0.0, 0.0, 1.0, 1.0)}
_BANK = None


def _bank(drop_cards=()):
    """{'power': {d: [(whole, glyph, (gx, gy))]}, 'shield': {...}} or {} if the file is gone.

    `drop_cards` removes every template cut from those roster cards. The npz carries that
    provenance for one reason: a template matches its own source crop at 1.000 (CLAUDE.md
    10.22 / 10.30), so a measurement -- or a test -- that lets a card be read by its own
    template is decorative. This is how a card the bank has never seen gets scored.
    """
    global _BANK
    if _BANK is None:
        try:
            z = np.load(TEMPLATES)
            src = dict(zip(z["_keys"].tolist(), z["_src"].tolist())) if "_keys" in z.files else {}
            out = {}
            for k in z.files:
                if k.startswith("_"):
                    continue
                field, d, _ = k.split("_")
                out.setdefault(field, {}).setdefault(int(d), []).append(
                    _with_glyph(z[k], _GLYPH[field]) + (src.get(k, ""),))
            _BANK = out
        except Exception:
            _BANK = {}
    if not drop_cards:
        return _BANK
    drop = set(drop_cards)
    return {f: {d: [t for t in ts if t[3] not in drop] for d, ts in v.items()}
            for f, v in _BANK.items()}


def _with_glyph(t, gf):
    h, w = t.shape
    x0, y0 = int(round(w * gf[0])), int(round(h * gf[1]))
    x1, y1 = int(round(w * gf[2])), int(round(h * gf[3]))
    return t, t[y0:y1, x0:x1].copy(), (x0, y0)



def _window(img, rows, rel_row, col, cols, frac):
    """The search window for one card sub-box, and the template scale.

    THE CARD'S HEIGHT COMES FROM THE ROW, NOT FROM card_box. `card_box` CLAMPS its box to
    the frame, so a row clipped at the bottom edge -- which ban_grid still reports, down to
    ROW_VISIBLE_MIN 0.65 -- comes back a third short, and every fraction measured against a
    card height then lands somewhere else. Found by a real mid-scroll frame
    (`midscroll_video_1920.jpg`), whose third row read powers fine by luck (the disc sits
    high enough that a squashed window still covered it) while on_card returned "nothing to
    measure" on four cards that are plainly there. The x axis is taken from card_box because
    the columns are never clipped.
    """
    box = bg.card_box(img, rows, rel_row, col, cols)
    if box is None:
        return None, None
    if bg.is_locked(img, box) is not False:
        return None, None            # faded, or unsure: there is nothing there to read
    w, h = img.size
    x0, bw = box[0], box[2] - box[0]
    r = rows[rel_row]
    if "top" in r and "bottom" in r:
        y0, bh = r["top"] * h, (r["bottom"] - r["top"]) * h
    else:
        y0, bh = box[1], box[3] - box[1]
    b = (max(0, x0 + int(bw * frac[0])), max(0, int(y0 + bh * frac[1])),
         min(w, x0 + int(bw * frac[2])), min(h, int(y0 + bh * frac[3])))
    if b[2] - b[0] < 8 or b[3] - b[1] < 8:
        return None, None
    return np.asarray(img.crop(b).convert("L"), dtype=np.uint8), bw / float(REF_CARD_W)


def _read(img, rows, rel_row, col, cols, field, frac, bank=None, locate_only=False):
    """(digit, sprite score, glyph score). digit is None when nothing could be located."""
    tpl = (bank or _bank()).get(field) if isinstance(bank or _bank(), dict) else None
    if not tpl:
        return None, 0.0, 0.0
    try:
        import cv2
    except Exception:
        return None, 0.0, 0.0
    sub, s = _window(img, rows, rel_row, col, cols, frac)
    if sub is None:
        return None, 0.0, 0.0

    def fit(t):
        tw, th = int(round(t.shape[1] * s)), int(round(t.shape[0] * s))
        if tw < 4 or th < 4 or sub.shape[0] < th or sub.shape[1] < tw:
            return None
        return t if (tw, th) == (t.shape[1], t.shape[0]) else \
            cv2.resize(t, (tw, th), interpolation=cv2.INTER_AREA)

    loc, sprite = None, -1.0
    for ts in tpl.values():
        for whole, _, _, _src in ts:
            tt = fit(whole)
            if tt is None:
                continue
            _, mx, _, ml = cv2.minMaxLoc(cv2.matchTemplate(sub, tt, cv2.TM_CCOEFF_NORMED))
            if mx > sprite:
                loc, sprite = (ml[0], ml[1]), float(mx)
    if loc is None:
        return None, 0.0, 0.0
    if locate_only:
        return 0, round(sprite, 4), 0.0

    pad = max(1, int(round(GLYPH_PAD * s)))
    digit, glyph = None, -1.0
    for d, ts in tpl.items():
        for _, g, (gx, gy), _src in ts:
            gg = fit(g)
            if gg is None:
                continue
            x0 = max(0, loc[0] + int(round(gx * s)) - pad)
            y0 = max(0, loc[1] + int(round(gy * s)) - pad)
            cell = sub[y0:y0 + gg.shape[0] + 2 * pad, x0:x0 + gg.shape[1] + 2 * pad]
            if cell.shape[0] < gg.shape[0] or cell.shape[1] < gg.shape[1]:
                continue
            v = float(cv2.minMaxLoc(cv2.matchTemplate(cell, gg, cv2.TM_CCOEFF_NORMED))[1])
            if v > glyph:
                digit, glyph = d, v
    return digit, round(sprite, 4), round(max(glyph, 0.0), 4)


def read_power(img, rows, rel_row, col, cols=None, bank=None):
    """(digit, score) for the power disc, or (None, score) when it cannot be read.

    `score` is the GLYPH correlation, which is what the gate is on. A digit outside 4-9 is
    refused whatever it scored (CLAUDE.md section 4).
    """
    d, _, g = _read(img, rows, rel_row, col, cols, "power", POWER_WIN, bank)
    if d is None or g < POWER_MIN or not (POWER_RANGE[0] <= d <= POWER_RANGE[1]):
        return None, g
    return d, g


def on_card(img, rows, rel_row, col, cols=None, bank=None):
    """(True / False / None, score) -- is this card box actually ON a drawn player card?

    A POSITIVE test, not an absence: it looks for the card's own top-left corner where the
    box says the corner should be. True means a player card is there and a badge read can be
    trusted, including a "there is no badge" read. False means the box is displaced, or the
    card is a TACTICS card -- which is on a card but has no secondary stat, so refusing it is
    the right answer rather than a miss. None means there was nothing to measure (off screen,
    or the card is locked).
    """
    d, sprite, _ = _read(img, rows, rel_row, col, cols, "corner",
                         (CORNER_CUT[0] - CORNER_SEARCH, CORNER_CUT[1] - CORNER_SEARCH,
                          CORNER_CUT[2] + CORNER_SEARCH, CORNER_CUT[3] + CORNER_SEARCH),
                         bank, locate_only=True)
    if d is None:
        return None, sprite
    return sprite >= ON_CARD_MIN, sprite


def read_shield(img, rows, rel_row, col, cols=None, bank=None):
    """(digit, score) for the shield badge -- speed on a batter, fielding on a pitcher.

    0 IS A REAL ANSWER and it is a POSITIVE one: the box is on a player card (`on_card`) AND
    no badge sprite is there. It is not "the score failed", which is what it used to be, and
    which answered 0 for 134 of 250 badge-carrying cards on a displaced box.

    None means cannot say, for any of four reasons: the box is not on a player card; the card
    is a TACTICS card, which has no secondary stat; the presence score landed in the empty
    band between the two measured populations; or a badge is there but which digit is in it is
    not settled. `score` is the SPRITE correlation, the one the presence gate is on, and it is
    0.0 when the on-card test is what refused.
    """
    ok, _ = on_card(img, rows, rel_row, col, cols, bank)
    if ok is not True:
        return None, 0.0          # not on a player card: "no badge" would be a guess
    d, sprite, glyph = _read(img, rows, rel_row, col, cols, "shield", SHIELD_WIN, bank)
    if d is None:
        return None, sprite
    if sprite <= SHIELD_ABSENT_MAX:
        return 0, sprite
    if sprite < SHIELD_PRESENT_MIN or glyph < SHIELD_GLYPH_MIN:
        return None, sprite       # a badge is there; which digit is in it is not settled
    return d, sprite
