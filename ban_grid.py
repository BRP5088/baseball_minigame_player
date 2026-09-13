"""WHERE THE BAN-GRID CARDS ACTUALLY ARE, measured in the frame.

WHY THIS EXISTS. BAN_CARD_ROW_TOP_FRAC pins the two visible rows at fixed fractions. THE
ROWS MOVE: at the top of the grid the card tops sit at 0.282 / 0.609, and two scroll
presses later the same rows are at 0.231 / 0.558. So no fixed pair can frame every scroll
position, and the shipped box only "works" by being loose enough to contain the card
wherever it drifts to -- which is why it reads more names than any tighter box while
visibly clipping the card on screen.

The user's requirement is forward-looking and settles the design (2026-09-13): "this needs
to work with all cards... when the player unlocks this, this script needs to detect them.
meaning, I need to see the bounding boxes fit perfectly around all cards." A constant
tuned to today's collection cannot promise that. A box derived from the frame can.

THE LANDMARK IS THE NAME BANNER, not the card's outline. The banner is a dark ribbon with
light text across the card's full width -- the strongest, most repeatable horizontal edge
pair on the card -- while the card's own border is a thin light line that vanishes on a
faded (locked) card. Everything else is a fixed offset from it, expressed in BANNER HEIGHTS
so the geometry stays relative and survives a different capture size (CLAUDE.md section 3:
an offset or distance is scaled, never a raw pixel).

A faded row still gets a correct box: the rows are found by a VOTE across all five columns
and the second row is derived from the first plus the measured pitch, so a locked card is
framed by its neighbours' evidence.
"""
import numpy as np

# Measured on a live 2000x1125 ban frame against a ruler, in BANNER HEIGHTS:
#   name banner 0.518-0.557 (height 0.039);  card top 0.282;  card bottom 0.578
# EVERY CARD IS THE SAME SIZE, so every box is too (the user, 2026-09-13: "all the cards
# have the same height and width so keep them nice and clean"). Only the vertical OFFSET is
# unknown per frame. Deriving each box from its own banner's height made them vary -- 0.263
# on one frame against 0.297 on another -- which is the "weird bounded boxes" on cards the
# reader could not pin down. The height is now CANONICAL, from the column width and the
# card's aspect, and the banner supplies the OFFSET only.
BANNER_TOP_IN_CARD = 0.795        # banner top, as a fraction of card height below the card top
BANNER_H_IN_CARD = 0.132          # the ribbon's own height, same units (0.039 of 0.297)
BANNER_H_RANGE = (0.020, 0.060)   # a plausible banner height, as a fraction of frame height
# THE CARD'S SHAPE IS THE CONSTRAINT THAT PICKS THE RIGHT BANNER PAIR. A card is a fixed
# shape, so its height follows from the COLUMN WIDTH the grid already defines:
#     height_frac = CARD_ASPECT * column_width_frac * (w / h)
# Measured on the ruler frame: 337 px tall over 260 px wide = 1.296. Without this, a pair
# of unrelated grid lines 0.058 apart passes as a banner and the box comes out a third too
# tall -- which it did, on 6 of 16 scroll positions.
# THE CARD'S OWN COLUMNS, tighter than orchestrator.BAN_GRID_COL_X_FRAC.
#
# The shipped constant is 0.130 wide on a 0.135 pitch, so adjacent boxes almost touch: a
# box contains its card, the gap, and a sliver of both neighbours. That is harmless for
# reading a NAME out of the middle of it and fatal for anything that looks at the card's
# EDGE -- the user, 2026-09-13: "I bet there would be bleed through of neighbors because
# they would overlap." They were right, and it was already visible in the data: the cursor
# glow separated at 33x and 99x on two frames and only 1.7x on a third, where a neighbour
# was also lit.
#
# RE-FITTED 2026-09-13 OVER 520 ROW BANDS, because one card is not a lattice. The previous
# numbers (start 0.165, pitch 0.135, width 0.108) were read off ONE card -- col1, whose
# edges do sit at 0.300 and 0.408 -- and a start and a pitch cannot be measured from one
# sample. They were both slightly wrong, and the error ACCUMULATES across the row:
#
#     shipped left-edge error, in card widths:  +0.085  +0.062  +0.040  +0.017  -0.005
#
# Column 4 was right and column 0 was off by a twelfth of a card. That is why a badge box
# tuned on one card broke on another -- the user, 2026-09-13: "I moved them so they fit
# some of the boxes better and that caused them to be wrong else where." Nothing was wrong
# with the badge fractions; they were fractions of a card box that was in the wrong place.
#
# HOW IT WAS FITTED. The columns do not move -- same x at every scroll position, on every
# row, in every frame -- so the vertical-edge profile is POOLED over 520 row bands from 260
# ban frames. A card's borders and its art both make edges, but only the borders are at the
# same x every time, so the art averages away. What survives is unmistakable: the page
# BETWEEN cards is DEAD FLAT (under 0.020 of the pooled maximum) while every card band is
# alive, so the card spans fall out of the gaps without any peak-picking at all.
#
#     gaps   0.1160-0.1550  0.2750-0.2930  0.4085-0.4305  0.5575-0.5685
#            0.6835-0.7055  0.8210-0.8455
#     cards  0.1550-0.2750  0.2930-0.4085  0.4305-0.5575  0.5685-0.6835  0.7055-0.8210
#
# A uniform lattice fits those five to a residual of +-0.0004 of frame width, which is the
# grid confirming it really is one. (Peak-picking the same profile does NOT work and was
# tried first: it returns two interleaved lattices 0.033 apart, because a card's outer
# border and its inner art frame are both strong and both regular.)
CARD_COL_START = 0.1552           # fitted, residual +-0.0004
CARD_COL_PITCH = 0.1376
CARD_COL_WIDTH = 0.1155
CARD_COL_X_FRAC = [(round(CARD_COL_START + k * CARD_COL_PITCH, 4),
                    round(CARD_COL_START + k * CARD_COL_PITCH + CARD_COL_WIDTH, 4))
                   for k in range(5)]

# THE CARD HEIGHT IS 0.2995 OF THE FRAME AND HAS NEVER MOVED. This constant does not say
# what the height IS; it says how to get there from the column WIDTH, so every time the
# width is re-measured this has to be re-derived or the row solve locks onto a wrong phase.
# It has happened twice now: at the loose 0.130 it was 1.296, at 0.108 it was 1.560, and at
# the fitted 0.1155 it is 0.2995 / (0.1155 * 16/9) = 1.4587.
#
# The height itself is the one number in this file validated against a HAND-READ RULER --
# phase error +0.000 to +0.003 on 17 of 17 archived frames -- so when the width changes,
# the height is what is held fixed and the aspect is what moves.
CARD_ASPECT = 1.4587
CARD_H_TOLERANCE = 0.14           # accept a derived box within +-14% of that height
ROW_PITCH_RANGE = (0.25, 0.40)    # plausible distance between two rows
MIN_COLS_AGREEING = 3             # of five, before an edge counts as a grid line
MAX_EXTRAPOLATE = 3               # rows to step either side of the located pair
# THE PITCH IS THE PART THAT IS ACTUALLY CONSTANT. The rows' POSITION moves with scroll, but
# their SPACING does not: measured 0.327 / 0.328 / 0.329 across scroll positions and both
# capture sizes. It is a distance expressed as a fraction of frame height, so it scales like
# every other offset here. Used only when a single row is located and there is no second one
# to measure against -- which is the case on a TACTICS row, where the only detectable
# banner belongs to the player row above it.
# CONFIRMED INDEPENDENTLY, by the user's pointer (2026-09-13: "to figure out the spacing
# between rows, look at Row0 col 3 and Row 1 Col 3"). A single column's intensity profile is
# PERIODIC with the row pitch, so autocorrelating it reads the spacing with no landmark and
# nothing to identify. On a live frame three of four columns peaked at exactly 0.3280 --
# matching the banner-pair estimate to four decimals, by a completely different method. The
# fourth column held the cursor-highlighted card and is not periodic; it said 0.3867.
#
# IT IS NOT A BETTER ESTIMATOR, THOUGH, AND WAS TRIED AS ONE. Over 16 archived scroll
# frames autocorrelation returned 0.254 / 0.281 / 0.262 on faded rows -- it answers even
# when there is no card structure to find, locking onto the page texture -- and requiring
# three columns to agree within 2% still left three frames confidently wrong. A constant
# measured at 0.327-0.329 across every scroll position and both capture sizes beats a
# per-frame measurement that is wrong one time in five, so the constant stays and the
# autocorrelation code is deleted rather than kept as an unused trap.
ROW_PITCH_DEFAULT = 0.328
# A NAME BANNER IS A DARK RIBBON. The page's own ornate title border is a pair of light
# lines the right distance apart, and the single-banner fallback anchored on it -- every
# row then extrapolated from the page title instead of a card. Requiring the ribbon to be
# DARKER than the card around it rejects that without inventing a brightness threshold:
# it is a comparison between two regions of the same frame, so it survives any exposure.
BANNER_DARKER_BY = 18.0
EDGE_SIGMA = 2.2                  # gradient peak threshold, in sigma above the mean


BANNER_EDGES = (0.79, 0.93)       # the name banner's top and bottom, in card heights
PHASE_STEP = 0.001                # how finely the phase is searched, in frame heights
MIN_EDGE_SAMPLES = 4              # edge samples that must land on screen before we answer
# A FLOOR ON "IS THERE ANY STRUCTURE HERE", and nothing more. On a flat frame the edge
# profile is all zeros, normalising leaves zeros, and every phase ties at 0.0 -- so the
# first one tried won and the function answered about a frame with no grid in it.
# Measured: a flat frame scores 0.000, every real ban frame 0.46-0.91.
#
# IT IS NOT A BAN-SCREEN TEST AND MUST NOT BE USED AS ONE. Over a non-ban control the same
# score runs 0.535-0.858, right through the ban range -- one population, no gate (10.4).
# read_ban_counter answers that question; this only refuses to answer about nothing.
MIN_PHASE_SCORE = 0.15
# THE GRID SCROLLS INSIDE A VIEWPORT, AND ONLY TWO WHOLE ROWS EVER FIT IN IT.
#
# The phase places rows wherever the array says they are, including above the top of the
# viewport and below the bottom of the frame. Reporting those part-rows is what made
# everything downstream complicated, and the user called it, 2026-09-13:
#
#     "you are trying to capture a non existent row -1 (it's in the banned cards header
#      area) ... a row that can barely be seen ... wouldn't it be better to just have 2
#      rows be captured and scroll to get everything else?"
#
# They are right, and the frames agree. At the BOTTOM of the collection the top row's card
# art is not drawn at all -- only its name banner, hanging under the header -- and at the
# TOP the third row shows one sliver of banner at the bottom edge.
#
# WHERE THE VIEWPORT CLIPS, MEASURED. Per-pixel-row variance across 150 ban frames at many
# scroll positions, over the card COLUMNS only: the grid scrolls, the header does not, so
# variance is near zero above the clip and large below it.
#
#     above    0.0000 - 0.2463    sd max  6.04
#     below    0.2481 - 0.9800    sd min  8.69
#     the step is 4.92 -> 20.91 between two adjacent sampled rows
#
# HOW MUCH OF A ROW IS INSIDE THAT VIEWPORT separates the two kinds of row completely.
# Measured over 2,072 ban frames -- every 1920x1080 frame the counter census labelled a
# ban screen -- 6,211 candidate rows:
#
#     PART-VISIBLE   n=2068   0.197 - 0.442
#     WHOLE          n=4137   0.881 - 1.000
#     in between     n=3      0.553, 0.669, 0.771 -- two MID-SCROLL frames, cards motion-
#                             blurred and half-drawn; reporting fewer rows there is right
#
# At the gate, 2,069 of 2,072 frames give exactly TWO rows and 3 give one. Never zero,
# never three. Everything else is reached by SCROLLING.
#
# This replaces a card-edge-energy gate that told a clipped row of cards from empty page.
# That gate worked; it was the wrong question. A part-visible row is not readable whether
# or not it holds cards, and every consumer had to special-case it.
GRID_TOP_FRAC = 0.247             # between the two measured populations above
ROW_VISIBLE_MIN = 0.65            # between 0.442 and 0.881, clear by 1.5x and 1.4x


def _edge_profile(img, cols):
    """Horizontal-edge energy per row of pixels, averaged across the card COLUMNS only.

    The page between columns carries the notebook's own rules and shadows; averaging it in
    adds a constant that varies with scroll. Restricting to the columns is what makes the
    profile a statement about CARDS.
    """
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape
    idx = np.concatenate([np.arange(int(w * a), int(w * b)) for a, b in cols])
    prof = np.abs(np.diff(g, axis=0))[:, idx].mean(axis=1)
    m = float(prof.max())
    return (prof / m) if m > 0 else prof


def find_card_rows(img, cols=None):
    """Every visible card row, as fractions of frame height, or None.

    THE GRID IS A UNIFORM 2D ARRAY, so it has exactly one unknown: the vertical PHASE.
    Column positions are fixed (pitch 0.135, width 0.130, measured identical across all
    four gaps), the card size is fixed, and the row pitch is fixed at ROW_PITCH_DEFAULT.
    Solve the phase and every row follows -- including rows too faded to detect on their
    own, which is the whole point (a locked card measures sd 16-19 against an owned card's
    62-66, so it has almost no edges to offer).

    THE PHASE IS SOLVED BY POOLING THE NAME BANNER ACROSS EVERY ROW AT ONCE. Measured
    inside a card whose position was known from a ruler, the only dominant horizontal edges
    are the name banner's top and bottom -- 0.98 and 1.00 normalised at 0.79 and 0.93 of
    card height, with everything else under 0.25. Earlier attempts scored the card's OUTER
    top and bottom, which are thin light lines, and the solver slid until its lower sample
    hit the banner instead: a systematic error of 0.187 card-heights, exactly what was
    observed. Scoring the banner directly, and summing it over all rows, lets faint rows
    contribute evidence they could never carry alone.

    Exact where truth is known: phase error +0.000, +0.000, +0.001, +0.002, +0.003 on the
    five frames measured against a hand-read ruler.

    TWO THINGS THIS DELIBERATELY DOES NOT DO. It does not decide whether the frame IS a ban
    screen -- read_ban_counter does that, and it must, because the phase score cannot: over
    a non-ban control the score runs 0.535-0.858 against a ban screen's 0.46-0.91, one
    population with no gate between them (CLAUDE.md 10.4). And it does not measure the
    pitch per frame; autocorrelation was tried and is wrong one frame in five.
    """
    cols = cols or CARD_COL_X_FRAC
    prof = _edge_profile(img, cols)
    n_px = len(prof)

    def at(frac):
        y = int(n_px * frac)
        if y < 0 or y >= n_px:
            return None
        return float(prof[max(0, y - 2):y + 3].max())

    want = CARD_ASPECT * (cols[0][1] - cols[0][0]) * (img.size[0] / float(img.size[1]))
    best = (-1.0, None)
    ph = -ROW_PITCH_DEFAULT
    while ph < 1.0:
        total = seen = 0.0
        for k in range(-1, MAX_EXTRAPOLATE + 2):
            top = ph + k * ROW_PITCH_DEFAULT
            for e in BANNER_EDGES:
                v = at(top + e * want)
                if v is not None:
                    total += v
                    seen += 1
        if seen >= MIN_EDGE_SAMPLES and total / seen > best[0]:
            best = (total / seen, ph)
        ph += PHASE_STEP
    if best[1] is None or best[0] < MIN_PHASE_SCORE:
        return None
    phase = best[1] % ROW_PITCH_DEFAULT

    rows = []
    for k in range(-1, MAX_EXTRAPOLATE + 2):
        top = phase + k * ROW_PITCH_DEFAULT - ROW_PITCH_DEFAULT
        bot = top + want
        # ONLY WHOLE ROWS, and `whole` is measured against the VIEWPORT, not the frame:
        # the header clips the top of the grid at GRID_TOP_FRAC. See that constant.
        visible = (min(1.0, bot) - max(GRID_TOP_FRAC, top)) / want
        if visible < ROW_VISIBLE_MIN:
            continue
        bt = top + BANNER_EDGES[0] * want
        bb = top + BANNER_EDGES[1] * want
        # `measured` means THIS row's own banner is visible, not that the phase came from
        # it: the phase is a whole-frame answer, but a caller still wants to know which
        # rows carried evidence and which were placed by the pitch.
        own = [at(bt), at(bb)]
        rows.append({"top": top, "bottom": bot, "banner_top": bt, "banner_bottom": bb,
                     "visible": round(visible, 4),
                     "measured": all(v is not None and v >= 0.35 for v in own)})
    return rows or None


def _box_px(img, cols, col, top, bot):
    """A pixel box, clamped to the frame. None when the band is entirely off screen.

    find_card_rows only reports WHOLE rows now (see GRID_TOP_FRAC), so a card box never
    lands off screen. The clamp and the None stay for the SUB-boxes: a fraction a few
    percent outside its card, on the top row, once produced y1 < y0, which PIL raises on
    and the viewer's tick swallowed into a label. Returning None makes "there is nothing
    to draw" a value the caller can act on.
    """
    w, h = img.size
    x0, x1 = cols[col]
    y0, y1 = int(h * max(0.0, min(1.0, top))), int(h * max(0.0, min(1.0, bot)))
    if y1 <= y0:
        return None
    return (int(w * x0), y0, int(w * x1), y1)


def card_box(img, rows, rel_row, col, cols=None):
    """Pixel box for one card, or None if it is entirely off screen."""
    r = rows[rel_row]
    return _box_px(img, cols or CARD_COL_X_FRAC, col, r["top"], r["bottom"])


def name_box(img, rows, rel_row, col, cols=None):
    """Pixel box of the NAME BANNER, or None if it is off screen."""
    return _sub(img, rows, rel_row, col, cols, NAME_BANNER_BOX)


# Measured as fractions of the FITTED CARD BOX, off a ruler laid on a known BATTER cell
# (Johnny Drawers, 7/1). They are NOT interchangeable with the fractions used against
# get_ban_grid_card_crop's box: that box is 0.400 of frame height starting at 0.195, the
# fitted one is ~0.297 starting at ~0.282, so the same fraction lands somewhere else
# entirely. Carrying the old numbers over made the type OCR read '-' and '--'.
# SWEPT, 2026-09-13, after the user saw it clipping: "The bounding boxes for the cards
# type isn't correct for column 0 and 1. they are slightly cropped off which is causing
# unknowns." The ribbon itself measures 0.00-0.79 of the card box, so the shipped
# 0.16-0.66 did cut both ends. Widening it only helps up to a point -- past the ribbon the
# crop takes in the card border and PSM 11 does worse -- so the box was swept over 31
# readable cells on four frames, counting how many RETURN A TYPE:
#
#     x0   0.16  0.10  0.06  0.02      (at x1 0.66)      reads  24  26  20  17
#     y    0.04-0.15 is already the best band by a distance: 26 against 22 at 0.02-0.15,
#          8 at 0.06-0.15, and 14 at 0.00-0.15
#
# So x0 0.10 and nothing else. HONEST LIMIT: this is YIELD, not accuracy -- the attempt to
# label each cell from the roster by its OCR'd name matched 0 of 31, so how many of the 26
# are RIGHT is unmeasured. Tune it live against the screen (tools/state_viewer.py, key 1).
# RE-SWEPT ON THE CORRECTED CARD BOX. Every earlier value for this -- the shipped
# 0.16-0.66, the swept 0.10, and the one the user tuned live to 0.045-0.605 -- was a
# fraction of a card box that was in the wrong place, so all three were compensating for
# the column error rather than framing the ribbon. Re-swept over 33 owned cells on five
# frames, 96 boxes: the top ten all read 25-27 of 33 and the best is below. That flatness
# is the finding -- with the lattice right, this box barely matters.
# RE-SWEPT ON 244 CELLS, 2026-09-13, after a contact sheet of the cards this reader called
# unknown showed every one of them PLAINLY LEGIBLE -- CLAUDE.md 10.23's cheapest diagnostic,
# and its verdict every time: a recogniser that cannot read legible text is being handed the
# wrong crop. The reads were TAILS -- 'ER', 'HER', 'TTE', 'PIER' -- so x0 was too far RIGHT
# and the front of the word was outside the box.
#
# The 0.14 it replaces was swept over 33 cells on ONE screen and overfit to them. On 244:
#
#     x0   0.14   0.10   0.06   0.02        reads 193  217  170  202  of 244
#
# 0.06 is WORSE than 0.10, so this is a real optimum rather than "wider is better" -- past
# the ribbon the crop takes in the card border and PSM 11 does worse.
TYPE_BANNER_BOX = (0.10, 0.04, 0.66, 0.13)    # BATTER / PITCHER ribbon, upper left
# READ IT AT PSM 11 (sparse text), not 7. Measured against a hand-labelled row: PSM 7 and 6
# score 3 of 7 on this banner and PSM 11 scores 6 of 7, and the single miss is the card the
# CURSOR is highlighting -- its white glow floods the ribbon. Same crop, same whitelist; the
# page-segmentation mode was the whole difference, and three rounds of moving the box could
# not find what one mode change did.
TYPE_BANNER_PSM = 11

# The four tactics cards, from 299 HAND-LABELLED tactics cards in hand_labels*.json --
# there are no others. A banner is called tactics only when it matches one of these,
# never merely because it failed to read as BATTER or PITCHER: a FADED (locked) card
# returns garbage like "N HER", and calling that tactics puts a wrong label on a player
# card. "unknown" is the honest answer for a card that cannot be read yet.
TACTICS_NAMES = ("POWER SWING", "SPEED BOOST", "PITCH FOCUS", "FIELDING PLAY")

# A TACTICS CARD IS NOT A PLAYER CARD WITH DIFFERENT WORDS ON IT -- IT IS A DIFFERENT
# LAYOUT, and until now it was being read through the player boxes. The user, 2026-09-13:
# "can their also be detection when the a card isn't a player card, its a tactics card.
# which means it has different bounding boxes. look for yourself." Looking settles it:
#
#                        player card              tactics card
#     the words          upper LEFT, y 0.04-0.13  CENTRED, y 0.175-0.214, nearly full width
#     the number         top RIGHT, x 0.72-0.94   top CENTRE, x 0.429-0.623, y 0.000-0.142
#     a name banner      yes, at the foot         NO -- a decorative emblem sits there
#     a shield           yes, under the disc      NO -- the badge above IS the bonus
#
# The two number boxes are DISJOINT in x and the two word boxes are disjoint in y, so
# reading a tactics card through the player boxes cannot work and only ever half did: the
# player ribbon box ends at 0.13 and the tactics text starts at 0.175, so it was clipping
# the top of the letters and the fuzzy match was recovering the rest.
#
# Measured on the owned tactics cards of the tactics fixture: the label's bright text spans
# y 0.175-0.214 across essentially the whole card width, and the badge blob sits at
# x 0.429-0.623, y 0.000-0.142. Both boxes below are those extents with margin. n is small
# -- the collection holds only 10 tactics cards and most are locked -- so these are honest
# to a few hundredths and worth re-measuring if a tactics read starts failing.
TACTICS_TYPE_BOX = (0.02, 0.14, 0.98, 0.26)   # POWER SWING / SPEED BOOST / ... , centred
# SWEPT 2026-09-13 after the user called it: "the tactics number box is pretty wide when
# it doesn't need to be. maybe a very small increase in height would help with extracting
# the value." Both halves were right. Over 27 boxes on the three owned tactics cards of a
# live screen, scored on how many return a badge digit (1 or 2, the only values that exist):
#     x 0.40-0.66 y 0-0.17  (the old box)   1 of 3
#     x 0.47-0.64 y 0-0.19  (this one)      3 of 3   -- narrower AND taller
# n is 3, which is every owned tactics card on screen and still only 3; re-measure if a
# badge starts reading "-".
TACTICS_BONUS_BOX = (0.47, 0.00, 0.64, 0.19)  # the +1 / +2 badge, top centre
# MEASURED, not tuned: with the columns re-fitted the disc lands in the SAME place on
# every column. Found as the bright blob in the card's upper right over 28 owned cards on
# four frames: x 0.740-0.919, y 0.062-0.199, and the per-column spread of its centre is
# 0.0043 -- against a spread that used to force a compromise, which is what the user ran
# into: "I moved them so they fit some of the boxes better and that caused them to be wrong
# else where." The box below is that extent with a small margin.
POWER_DISC_BOX = (0.72, 0.04, 0.94, 0.22)     # the white power disc, upper right
# RE-MEASURED 2026-09-13 by the digit-bank build, which searches for the sprite instead of
# cropping at this box and so could measure where it actually is: x 0.753-0.943,
# y 0.207-0.367. The old box was ~0.07 card widths too wide on the left and ~0.04 card
# heights too deep at the bottom; its top and right edges were already right. Nothing
# READS through this box any more -- ban_digits searches a window -- so it exists only to
# draw the viewer's overlay, and an overlay that does not sit on the badge is a lie about
# where the reader is looking.
SHIELD_BOX = (0.75, 0.20, 0.95, 0.37)         # the shield badge below the disc
# The NAME ribbon, in the same units, so every card sub-box is one kind of thing and the
# live editor can tune them all the same way (tools/state_viewer.py, keys 1-4). It is
# deliberately NOT the same constant as BANNER_EDGES: those two numbers feed the PHASE
# SOLVER, and nudging the box you are looking at must not move where the rows are found.
NAME_BANNER_BOX = (0.00, 0.79, 1.00, 0.93)


def _sub(img, rows, rel_row, col, cols, frac):
    cols = cols or CARD_COL_X_FRAC
    box = card_box(img, rows, rel_row, col, cols)
    if box is None:
        return None                      # off screen: nothing to crop, and saying so beats
    x0, y0, x1, y1 = box                 # handing back a rectangle that is not there
    bw, bh = x1 - x0, y1 - y0
    fx0, fy0, fx1, fy1 = frac
    return (x0 + int(bw * fx0), y0 + int(bh * fy0),
            x0 + int(bw * fx1), y0 + int(bh * fy1))


def type_box(img, rows, rel_row, col, cols=None):
    """Pixel box of the card's TYPE banner (BATTER / PITCHER, or a tactics label)."""
    return _sub(img, rows, rel_row, col, cols, TYPE_BANNER_BOX)


def power_box(img, rows, rel_row, col, cols=None):
    """Pixel box of the power disc."""
    return _sub(img, rows, rel_row, col, cols, POWER_DISC_BOX)


def shield_box(img, rows, rel_row, col, cols=None):
    """Pixel box of the shield badge (speed on a batter, fielding on a pitcher)."""
    return _sub(img, rows, rel_row, col, cols, SHIELD_BOX)


def tactics_type_box(img, rows, rel_row, col, cols=None):
    """Pixel box of a TACTICS card's label. A different band from the player ribbon."""
    return _sub(img, rows, rel_row, col, cols, TACTICS_TYPE_BOX)


def tactics_bonus_box(img, rows, rel_row, col, cols=None):
    """Pixel box of a TACTICS card's bonus badge. Top CENTRE, not top right."""
    return _sub(img, rows, rel_row, col, cols, TACTICS_BONUS_BOX)


def _lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def read_card_type(img, rows, rel_row, col, cols=None, ocr=None, max_edits=2):
    """'batter' | 'pitcher' | ('tactics', text) | None for one card's type banner.

    `ocr` takes a PIL image and returns text (the caller owns the OCR handle; this module
    stays free of orchestrator).

    BOTH POLARITIES, then a FUZZY match against the only two words this banner can hold.
    The text is white on black, which tesseract reads less reliably than the inverse, and a
    tight crop drops a letter: real reads here include 'WTER', 'PIHER' and 'BATT R'. Those
    are 1-2 edits from the right answer and there is no third player type to confuse them
    with, so an edit-distance gate recovers them without inventing anything.

    A banner that is NEITHER word, but holds readable text, is reported as tactics with
    that text -- KNOWN_BAN_ROSTER is 33 player cards and no tactics at all, so the roster
    can never name one (CLAUDE.md section 4).
    """
    def _letters(box):
        """The longest run of letters this box yields, at either polarity."""
        if box is None:
            return ""
        best = ""
        for invert in (False, True):
            crop = img.crop(box).convert("L")
            if invert:
                crop = crop.point(lambda p: 255 - p)
            crop = crop.resize((crop.width * 4, crop.height * 4))
            txt = (ocr(crop) or "").strip().upper()
            got = "".join(ch for ch in txt if ch.isalpha())
            if len(got) > len(best):
                best = got
        return best

    # THE PLAYER RIBBON FIRST, in its own box.
    best_d, best_w = 99, None
    player = _letters(type_box(img, rows, rel_row, col, cols))
    if player:
        for want in ("BATTER", "PITCHER"):
            d = _lev(player, want)
            if d < best_d:
                best_d, best_w = d, want
    if best_d <= max_edits and best_w:
        return best_w.lower()
    # THEN THE TACTICS LABEL, IN THE TACTICS BOX -- a different band of the card entirely.
    # It used to be matched against whatever letters the PLAYER box happened to catch,
    # which is why it worked at all and why it worked badly.
    tac = _letters(tactics_type_box(img, rows, rel_row, col, cols))
    for cand in (tac, player):
        if not cand:
            continue
        for want in TACTICS_NAMES:
            if _lev(cand, want.replace(" ", "")) <= max_edits:
                return ("tactics", want)
    # A READ THAT CONTAINS A NAME IS THAT NAME. The tactics box is wider than the label and
    # takes in the card's border decoration, so real reads arrive as 'FFPITCHFOCUSYY' and
    # 'ZFPITCHFOCUSY' -- which hold PITCHFOCUS exactly and score 3 and 4 on a whole-string
    # edit distance, over a gate of 2. Trimming the box was tried and costs more than it
    # gains (0.02 and 0.06 both read worse than 0.10); reading the name out of the noise
    # costs nothing.
    #
    # ONLY WHEN EXACTLY ONE NAME IS CONTAINED. That is what keeps it safe: a fragment like
    # 'ER' sits inside both BATTER and PITCHER, so it stays an abstention instead of
    # becoming a coin flip on a card that decides a $50 ban.
    for cand, names in ((player, ("BATTER", "PITCHER")),
                        (tac, tuple(w.replace(" ", "") for w in TACTICS_NAMES)),
                        (player, tuple(w.replace(" ", "") for w in TACTICS_NAMES))):
        if not cand:
            continue
        hit = [w for w in names if w in cand]
        if len(hit) == 1:
            if hit[0] in ("BATTER", "PITCHER"):
                return hit[0].lower()
            for want in TACTICS_NAMES:
                if want.replace(" ", "") == hit[0]:
                    return ("tactics", want)
    return None


# LOCKED vs OWNED, and the two populations do not overlap. A locked card is drawn faded:
# RE-CENSUSED 2026-09-13 OVER 20,360 CELLS after the columns were re-fitted, because a
# gate is only a gate against the geometry it was measured on. The old pair came off ONE
# frame's tactics rows (owned 62-66, locked 16-19) and both numbers were too low:
#
#     sd histogram, 20,360 cells on 2,035 ban frames
#       12.9- 19.3   9358      <- locked
#       19.3- 25.7   1444      <- STILL locked, and the old gate cut through here
#       25.7- 32.1    547      <- still locked
#       32.1- 51.4     53      <- the real empty band
#       51.4- 70.7   8958      <- owned
#
# The old LOCKED_SD_MAX of 24.0 sat INSIDE the locked population -- 1,991 locked cells
# score above it -- so 1,225 of 20,360 cells (6%) fell in the dead band and answered None,
# which reads as "the reader failed" about a card that is simply locked. The band with 53
# cells in it is the one to straddle (CLAUDE.md 10.4).
#
# Reported as "locked" rather than "unknown", because they are different answers: locked
# means the card is there and the game is hiding it, unknown means the reader failed. It is
# also WHY a locked row cannot be box-fitted on its own: find_card_rows votes on edges, and
# a card with sd 16 has none to offer.
LOCKED_SD_MAX = 34.0
OWNED_SD_MIN = 48.0


def is_locked(img, box):
    """True / False / None for the card in `box`. None = between the populations, so unsure."""
    if box is None:
        return None
    import numpy as _np
    sub = _np.asarray(img.crop(box).convert("L"), dtype=_np.float32)
    if sub.size == 0:
        return None
    sd = float(sub.std())
    if sd <= LOCKED_SD_MAX:
        return True
    if sd >= OWNED_SD_MIN:
        return False
    return None


# ---------------------------------------------------------------------------------------
# THE CURSOR, AND WHAT IS BANNED
# ---------------------------------------------------------------------------------------
# The cursor is a bright WHITE HALO drawn around the card it sits on -- the same signal
# local_hand.cursor_glow reads in the hand, and read the same way: a white FRACTION in a
# window that is on the card's surround, never on its art. The art is full of white; the
# halo is not part of it.
#
# IT ONLY WORKS ON THE TIGHT COLUMNS. With orchestrator's 0.130-wide box on a 0.135 pitch
# the surrounds of adjacent cards overlap, and a lit neighbour bleeds into this card's
# window -- the user called it before it was measured, 2026-09-13: "I bet there would be
# bleed through of neighbors because they would overlap." Measured on three frames whose
# cursor was identified by eye, loose box then tight:
#
#     Charlie Pepper   1.7x  ->  6.9x
#     Pitch Focus     33.3x  ->  4.1x      (the 33x was the runner-up reading ~0, not skill)
#     Johnny Drawers  99.0x  ->  3.2x
#
# ARGMAX PLUS A MARGIN, NOT A THRESHOLD ALONE. Over 41 ban frames the ratio of the highest
# glow to the second highest is sharply bimodal:
#
#     1.02 - 1.39   12 frames    the BANNING PHASE splash: its white text lands in the
#                                windows of a whole row and lifts four cards at once
#     2.86 - 8.90   29 frames    a real cursor, alone
#     nothing between 1.39 and 2.86
#
# So CURSOR_MIN_MARGIN sits in a gap twice its own width, and the 12 abstentions are exactly
# the animation frames -- where the cursor genuinely cannot be trusted and saying so is the
# only honest answer.
GLOW_PAD = 0.09                   # how far outside the card the window reaches, in card widths
GLOW_WHITE = 235                  # a GREY LEVEL, so NOT scaled (CLAUDE.md section 3)
CURSOR_GLOW_MIN = 0.030           # non-cursor cards measured <= 0.0164 on clean frames
CURSOR_MIN_MARGIN = 2.0           # between the two measured populations above


def cell_glow(img, rows, rel_row, col, cols=None):
    """White fraction in the halo window around one card, or None if it is off screen."""
    box = card_box(img, rows, rel_row, col, cols)
    if box is None:
        return None
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    h, w = g.shape
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    gx, gy = int(bw * GLOW_PAD), int(bh * GLOW_PAD * 0.55)
    ox0, oy0 = max(0, x0 - gx), max(0, y0 - gy)
    ox1, oy1 = min(w, x1 + gx), min(h, y1 + gy)
    outer = g[oy0:oy1, ox0:ox1]
    if outer.size == 0:
        return None
    mask = np.ones(outer.shape, bool)
    mask[(y0 - oy0):(y1 - oy0), (x0 - ox0):(x1 - ox0)] = False   # the card itself is not the halo
    px = outer[mask]
    return float((px >= GLOW_WHITE).mean()) if px.size else 0.0


def cursor_cell(img, rows, cols=None):
    """((row, col), detail) for the cursored card, or (None, detail) when unsure.

    None means NOT READ, never "no cursor": during the BANNING PHASE splash every card in a
    row lights up and no answer is trustworthy. `detail` carries the glow map and the two
    best values so a caller or a log can see WHY.
    """
    vals = {}
    for i in range(len(rows)):
        for c in range(len(cols or CARD_COL_X_FRAC)):
            v = cell_glow(img, rows, i, c, cols)
            if v is not None:
                vals[(i, c)] = round(v, 4)
    detail = {"glow": vals, "best": None, "second": None, "why": ""}
    if len(vals) < 2:
        detail["why"] = "fewer than two cells to compare"
        return None, detail
    order = sorted(vals.items(), key=lambda kv: -kv[1])
    (cell, best), (_, second) = order[0], order[1]
    detail["best"], detail["second"] = best, second
    if best < CURSOR_GLOW_MIN:
        detail["why"] = f"brightest halo {best:.4f} is under {CURSOR_GLOW_MIN}"
        return None, detail
    if second > 0 and best / second < CURSOR_MIN_MARGIN:
        detail["why"] = (f"{best:.4f} vs {second:.4f} is only {best / second:.2f}x — more "
                         f"than one card is lit, which is what the splash does")
        return None, detail
    detail["why"] = f"{best:.4f} against {second:.4f}"
    return cell, detail


# A BANNED CARD CARRIES A BIG DARK X, and darkness alone does not find it.
#
# The user, 2026-09-13: "I believe it shows a big black X over the card. I think it also
# makes the card glow." The X is right; the glow is NOT a persistent state -- on a settled
# frame with three cards banned, every banned card measured cell_glow 0.0000 while the
# cursor measured 0.0968. Whatever glows on selection is an animation, and it does not
# confuse the cursor.
#
# DARK FRACTION CANNOT DO THIS. On one frame the two genuinely banned cards scored 0.775
# and 0.642 -- and Johnny "Blaze" Sweets, which is NOT banned, scored 0.551 on a dark
# lightning background. It is a SHAPE, not a level (CLAUDE.md 10.23's family).
#
# THE X LIES ON THE CARD'S DIAGONALS, so that is where it is measured: the dark fraction
# inside two diagonal bands. A uniformly dark card is dark everywhere and scores no higher
# on the diagonals than off them; a banned card does.
#
# SCORED AGAINST THE BAN COUNTER, which is independent ground truth -- a frame reading 0/3
# has NO banned card, whatever the pixels look like:
#
#     counter-0 cells   n=4,840   max 0.761
#     banned cards                clustered 0.90 - 0.944
#     gate 0.82         ZERO false positives in 4,840, and catches 69 of the 70 cells
#                       that any looser gate finds
#
# A gate of 0.75 was tried first and fired on 47 of 323 counter-0 FRAMES: it sat at the
# counter-0 p99, which is inside the negative population, not above it.
#
# IT FINDS FEWER CARDS THAN THE COUNTER SAYS, and that is correct rather than a miss: the
# grid shows about fifteen cards of a collection of forty-plus, so a banned card is often
# scrolled off screen. The counter is the authority on HOW MANY; this says WHICH of the
# visible ones.
BAN_X_DARK = 95                   # a GREY LEVEL, so NOT scaled
BAN_X_BAND = 0.085                # half-width of each diagonal band, in card widths
BAN_X_MIN = 0.82                  # above a measured counter-0 ceiling of 0.761
BAN_X_NEG_MAX = 0.761             # that ceiling, recorded so the gate can be re-derived


def ban_x_score(img, rows, rel_row, col, cols=None):
    """Dark fraction along the card's two diagonals, where the ban X lies. None if off screen."""
    box = card_box(img, rows, rel_row, col, cols)
    if box is None:
        return None
    g = np.asarray(img.convert("L"), dtype=np.float32)
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    sub = g[y0 + int(bh * 0.16):y0 + int(bh * 0.80),
            x0 + int(bw * 0.06):x1 - int(bw * 0.06)]
    h, w = sub.shape
    if h < 10 or w < 10:
        return None
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = xx / (w - 1.0), yy / (h - 1.0)
    band = (np.abs(u - v) <= BAN_X_BAND) | (np.abs(u - (1.0 - v)) <= BAN_X_BAND)
    return float((sub <= BAN_X_DARK)[band].mean())


def banned_cells(img, rows, cols=None):
    """[(row, col), ...] for the visible cards showing a ban X, and the score map.

    Returns only what is ON SCREEN. Compare the count against read_ban_counter: fewer is
    normal (the rest are scrolled away); MORE would mean a false positive and is worth
    a second look.
    """
    scores, hits = {}, []
    for i in range(len(rows)):
        for c in range(len(cols or CARD_COL_X_FRAC)):
            s = ban_x_score(img, rows, i, c, cols)
            if s is None:
                continue
            scores[(i, c)] = round(s, 4)
            if s >= BAN_X_MIN:
                hits.append((i, c))
    return hits, scores
