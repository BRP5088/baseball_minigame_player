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
            return [(max(0.0, t), min(1.0, b)) for t, b in rows]
    return None                              # NOT FOUND -- the caller falls back, never guesses


def card_box(img, rows, rel_row, col, cols):
    """Pixel box for one card, from find_card_rows' output."""
    w, h = img.size
    x0, x1 = cols[col]
    top, bot = rows[rel_row]
    return (int(w * x0), int(h * top), int(w * x1), int(h * bot))
