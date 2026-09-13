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


def _edges(g, a, b, h):
    prof = g[:, a:b].mean(axis=1)
    d = np.abs(np.diff(prof))
    d = np.convolve(d, np.ones(5) / 5.0, mode="same")
    thr = d.mean() + EDGE_SIGMA * d.std()
    out, y = [], 1
    while y < len(d):
        if d[y] > thr:
            s = y
            while y < len(d) and d[y] > thr:
                y += 1
            out.append(((s + y) // 2) / h)
        else:
            y += 1
    return out


def _cluster(vals, tol):
    vals = sorted(vals)
    groups, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            groups.append(cur); cur = [v]
    groups.append(cur)
    return [(float(np.median(c)), len(c)) for c in groups]


def find_card_rows(img, cols):
    """[(top, bottom), ...] per visible row as fractions of height, or None.

    None means NOT FOUND and the caller must fall back -- never a guessed box, because a
    box in the wrong place reads the wrong card's numbers rather than failing (10.23).
    """
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape
    votes = []
    for x0, x1 in cols:
        a, b = int(w * (x0 + 0.012)), int(w * (x1 - 0.012))
        if b - a >= 20:
            votes.extend(_edges(g, a, b, h))
    if not votes:
        return None
    lines = [v for v, n in _cluster(votes, 0.008) if n >= MIN_COLS_AGREEING]
    if len(lines) < 2:
        return None
    # a NAME BANNER is a pair of grid lines a banner-height apart
    banners = [(t, b) for i, t in enumerate(lines) for b in lines[i + 1:]
               if BANNER_H_RANGE[0] <= b - t <= BANNER_H_RANGE[1]]
    if not banners:
        return None
    # keep the pair-set whose spacing matches a single consistent row pitch
    col_w = cols[0][1] - cols[0][0]
    want = CARD_ASPECT * col_w * (w / float(h))
    want_bh = want * BANNER_H_IN_CARD
    cands = []
    for i, p in enumerate(banners):
        for q in banners[i + 1:]:
            if not ROW_PITCH_RANGE[0] <= q[0] - p[0] <= ROW_PITCH_RANGE[1]:
                continue
            bh = ((p[1] - p[0]) + (q[1] - q[0])) / 2.0
            cands.append((abs((p[1] - p[0]) - (q[1] - q[0])) + abs(bh - want_bh), p, q))
    cands.sort(key=lambda c: c[0])

    def _box(t, _b):
        """Card box from a banner TOP. One canonical height, so every box is identical."""
        top = t - BANNER_TOP_IN_CARD * want
        return (top, top + want)

    # TRY EVERY CANDIDATE IN SCORE ORDER, do not reject on the best one alone. Scoring
    # picks a favourite; the card's height is what DECIDES. Returning None because the
    # top-scoring pair failed threw away frames where the second pair was the right one
    # (2 of 16 scroll positions, including the frame the offsets were measured on).
    for _score, p, q in cands:
        rows = [_box(*p), _box(*q)]
        if True:                         # height is canonical now, nothing to check
            # IT IS A 2D ARRAY, SO ONE ROW AND THE PITCH PLACE ALL OF THEM (the user's
            # observation, 2026-09-13). The columns are already fixed; the rows are evenly
            # spaced; so a single located row is the whole geometry. That matters because a
            # row of LOCKED cards offers no edges to detect -- measured sd 16-19 against an
            # owned card's 62-66 -- and a tactics row can be placed entirely by the player
            # row above it. Detecting every row independently was never necessary and, on a
            # faded row, is not possible.
            pitch = q[0] - p[0]
            bh = ((p[1] - p[0]) + (q[1] - q[0])) / 2.0
            out = []
            for k in range(-MAX_EXTRAPOLATE, MAX_EXTRAPOLATE + 1):
                bt, bb = p[0] + k * pitch, p[1] + k * pitch
                t, b = _box(bt, bb)
                if b <= 0.0 or t >= 1.0:
                    continue                 # entirely off screen
                out.append({"top": t, "bottom": b, "banner_top": bt, "banner_bottom": bb,
                            # a row the fit LOCATED, or one placed by the pitch alone
                            "measured": k in (0, 1),
                            # partly off the top or bottom edge of the frame
                            "clipped": t < 0.0 or b > 1.0})
            return out
    # ONE ROW IS ENOUGH. With no second banner to measure the pitch against, take the best
    # single banner whose derived card height matches and step by the measured default.
    def _is_dark_ribbon(t, b, top, bot):
        y0, y1 = int(h * max(0.0, t)), int(h * min(1.0, b))
        c0, c1 = int(h * max(0.0, top)), int(h * min(1.0, bot))
        if y1 - y0 < 3 or c1 - c0 < 10:
            return False
        for x0f, x1f in cols:
            a, bb = int(w * x0f), int(w * x1f)
            ribbon = g[y0:y1, a:bb]
            card = g[c0:c1, a:bb]
            if ribbon.size and card.size and ribbon.mean() <= card.mean() - BANNER_DARKER_BY:
                return True
        return False

    for t, b in sorted(banners, key=lambda pr: abs((pr[1] - pr[0]) - want_bh)):
        top, bot = _box(t, b)
        if not _is_dark_ribbon(t, b, top, bot):
            continue
        out = []
        for k in range(-MAX_EXTRAPOLATE, MAX_EXTRAPOLATE + 1):
            bt, bb = t + k * ROW_PITCH_DEFAULT, b + k * ROW_PITCH_DEFAULT
            rt, rb = _box(bt, bb)
            if rb <= 0.0 or rt >= 1.0:
                continue
            out.append({"top": rt, "bottom": rb, "banner_top": bt, "banner_bottom": bb,
                        "measured": k == 0, "clipped": rt < 0.0 or rb > 1.0})
        if out:
            return out
    return None                              # NOT FOUND -- the caller falls back, never guesses


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
