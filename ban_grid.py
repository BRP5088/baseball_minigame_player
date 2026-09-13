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
# MEASURED off the intensity profile across one card, away from its banners. The notebook
# page sits at ~200 grey and the card body is darker:
#     page 199.5 at x=0.295  ->  160.4 at 0.300  ... 160.8 at 0.405  ->  201.0 at 0.410
# so the card spans 0.300-0.408 and the pitch is the shipped 0.135, giving starts at
# 0.165 + k*0.135. The shipped box is 0.022 too wide and sits 0.009 left of centre.
#
# Scored against the shipped columns on what the loose box was good at -- resolving NAMES
# over 32 ban frames -- it costs 4 of 170 and finds the same 16 distinct cards. Noise,
# against geometry that is correct.
CARD_COL_X_FRAC = [(round(0.165 + k * 0.135, 4), round(0.165 + k * 0.135 + 0.108, 4))
                   for k in range(5)]

# RE-DERIVED WITH THE TIGHT COLUMNS (2026-09-13). The card height follows from the column
# WIDTH, so changing the width changes the height: at the loose 0.130 the aspect was 1.296,
# and carrying that number over to the tight 0.108 made every card 0.249 tall instead of
# 0.2995 -- the row solve then locked onto the wrong phase entirely. Measured on a
# 2000x1125 frame: the card is 337 px tall and 216 px wide (0.2995 of height, 0.108 of
# width), so 337/216 = 1.560. Check: 1.560 * 0.108 * (2000/1125) = 0.2995.
CARD_ASPECT = 1.560
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
TYPE_BANNER_BOX = (0.10, 0.04, 0.66, 0.15)    # BATTER / PITCHER ribbon, upper left
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
POWER_DISC_BOX = (0.72, 0.04, 0.96, 0.22)     # the white power disc, upper right
SHIELD_BOX = (0.70, 0.21, 0.96, 0.41)         # the shield badge below it
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
    box = type_box(img, rows, rel_row, col, cols)
    if box is None:
        return None
    best_d, best_w, best_txt = 99, None, ""
    for invert in (False, True):
        crop = img.crop(box).convert("L")
        if invert:
            crop = crop.point(lambda p: 255 - p)
        crop = crop.resize((crop.width * 4, crop.height * 4))
        txt = (ocr(crop) or "").strip().upper()
        letters = "".join(ch for ch in txt if ch.isalpha())
        if not letters:
            continue
        if len(letters) > len(best_txt):
            best_txt = letters
        for want in ("BATTER", "PITCHER"):
            d = _lev(letters, want)
            if d < best_d:
                best_d, best_w = d, want
    if best_d <= max_edits and best_w:
        return best_w.lower()
    for want in TACTICS_NAMES:
        squished = want.replace(" ", "")
        if best_txt and _lev(best_txt, squished) <= max_edits:
            return ("tactics", want)
    return None


# LOCKED vs OWNED, and the two populations do not overlap. A locked card is drawn faded:
# measured on one ban frame's tactics rows, contrast (standard deviation of grey) is
#     owned    62-66   range 15-255
#     locked   16-19   range 156-233
# a 3.5x gap with nothing in between, so the gate sits between two measured populations
# rather than inside one (CLAUDE.md 10.4). It is also WHY a locked row cannot be box-fitted:
# find_card_rows votes on edges, and a card with sd 16 has none to offer.
#
# Reported as "locked" rather than "unknown", because they are different answers: locked
# means the card is there and the game is hiding it, unknown means the reader failed.
LOCKED_SD_MAX = 24.0
OWNED_SD_MIN = 40.0


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
