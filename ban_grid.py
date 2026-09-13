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
CARD_TOP_ABOVE_BANNER = 6.05      # banner heights from the banner's TOP up to the card top
CARD_BOT_BELOW_BANNER = 0.54      # banner heights from the banner's BOTTOM down to the base
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
    want_bh = want / (CARD_TOP_ABOVE_BANNER + 1.0 + CARD_BOT_BELOW_BANNER)
    cands = []
    for i, p in enumerate(banners):
        for q in banners[i + 1:]:
            if not ROW_PITCH_RANGE[0] <= q[0] - p[0] <= ROW_PITCH_RANGE[1]:
                continue
            bh = ((p[1] - p[0]) + (q[1] - q[0])) / 2.0
            cands.append((abs((p[1] - p[0]) - (q[1] - q[0])) + abs(bh - want_bh), p, q))
    cands.sort(key=lambda c: c[0])

    def _box(t, b):
        bh = b - t
        return (t - CARD_TOP_ABOVE_BANNER * bh, b + CARD_BOT_BELOW_BANNER * bh)

    # TRY EVERY CANDIDATE IN SCORE ORDER, do not reject on the best one alone. Scoring
    # picks a favourite; the card's height is what DECIDES. Returning None because the
    # top-scoring pair failed threw away frames where the second pair was the right one
    # (2 of 16 scroll positions, including the frame the offsets were measured on).
    for _score, p, q in cands:
        rows = [_box(*p), _box(*q)]
        if all((1 - CARD_H_TOLERANCE) * want <= b - t <= (1 + CARD_H_TOLERANCE) * want
               for t, b in rows):
            # THE BANNER IS RETURNED WITH THE CARD, because it is the landmark the box was
            # derived FROM. A caller that wants the name strip should use the banner that
            # was actually found, not a fraction of the box -- re-deriving it loses the
            # only measurement here that is not an assumption.
            return [{"top": max(0.0, t), "bottom": min(1.0, b),
                     "banner_top": bt, "banner_bottom": bb}
                    for (t, b), (bt, bb) in zip(rows, (p, q))]
    return None                              # NOT FOUND -- the caller falls back, never guesses


def card_box(img, rows, rel_row, col, cols):
    """Pixel box for one card, from find_card_rows' output."""
    w, h = img.size
    x0, x1 = cols[col]
    r = rows[rel_row]
    return (int(w * x0), int(h * r["top"]), int(w * x1), int(h * r["bottom"]))


def name_box(img, rows, rel_row, col, cols):
    """Pixel box of the NAME BANNER -- the strip the card's name is printed on."""
    w, h = img.size
    x0, x1 = cols[col]
    r = rows[rel_row]
    return (int(w * x0), int(h * r["banner_top"]), int(w * x1), int(h * r["banner_bottom"]))


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
