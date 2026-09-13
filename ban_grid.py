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
CARD_ASPECT = 1.296
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


def find_card_rows(img, cols):
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
    if best[1] is None:
        return None
    phase = best[1] % ROW_PITCH_DEFAULT

    rows = []
    for k in range(-1, MAX_EXTRAPOLATE + 2):
        top = phase + k * ROW_PITCH_DEFAULT - ROW_PITCH_DEFAULT
        bot = top + want
        if bot <= 0.02 or top >= 0.98:
            continue
        bt = top + BANNER_EDGES[0] * want
        bb = top + BANNER_EDGES[1] * want
        # `measured` means THIS row's own banner is visible, not that the phase came from
        # it: the phase is a whole-frame answer, but a caller still wants to know which
        # rows carried evidence and which were placed by the pitch.
        own = [at(bt), at(bb)]
        rows.append({"top": top, "bottom": bot, "banner_top": bt, "banner_bottom": bb,
                     "measured": all(v is not None and v >= 0.35 for v in own),
                     "clipped": top < 0.0 or bot > 1.0})
    return rows or None


def card_box(img, rows, rel_row, col, cols):
    """Pixel box for one card, from find_card_rows' output."""
    w, h = img.size
    x0, x1 = cols[col]
    r = rows[rel_row]
    return (int(w * x0), int(h * max(0.0, r["top"])),
            int(w * x1), int(h * min(1.0, r["bottom"])))


def name_box(img, rows, rel_row, col, cols):
    """Pixel box of the NAME BANNER -- the strip the card's name is printed on."""
    w, h = img.size
    x0, x1 = cols[col]
    r = rows[rel_row]
    return (int(w * x0), int(h * max(0.0, r["banner_top"])),
            int(w * x1), int(h * min(1.0, r["banner_bottom"])))


# Measured as fractions of the FITTED CARD BOX, off a ruler laid on a known BATTER cell
# (Johnny Drawers, 7/1). They are NOT interchangeable with the fractions used against
# get_ban_grid_card_crop's box: that box is 0.400 of frame height starting at 0.195, the
# fitted one is ~0.297 starting at ~0.282, so the same fraction lands somewhere else
# entirely. Carrying the old numbers over made the type OCR read '-' and '--'.
TYPE_BANNER_BOX = (0.16, 0.04, 0.66, 0.15)    # BATTER / PITCHER ribbon, upper left
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


def _sub(img, rows, rel_row, col, cols, frac):
    x0, y0, x1, y1 = card_box(img, rows, rel_row, col, cols)
    bw, bh = x1 - x0, y1 - y0
    fx0, fy0, fx1, fy1 = frac
    return (x0 + int(bw * fx0), y0 + int(bh * fy0),
            x0 + int(bw * fx1), y0 + int(bh * fy1))


def type_box(img, rows, rel_row, col, cols):
    """Pixel box of the card's TYPE banner (BATTER / PITCHER, or a tactics label)."""
    return _sub(img, rows, rel_row, col, cols, TYPE_BANNER_BOX)


def power_box(img, rows, rel_row, col, cols):
    """Pixel box of the power disc."""
    return _sub(img, rows, rel_row, col, cols, POWER_DISC_BOX)


def shield_box(img, rows, rel_row, col, cols):
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


def read_card_type(img, rows, rel_row, col, cols, ocr, max_edits=2):
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
