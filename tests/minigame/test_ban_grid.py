"""THE BAN GRID IS A UNIFORM 2D ARRAY WITH ONE UNKNOWN, AND THIS PINS IT.

`BAN_CARD_ROW_TOP_FRAC` pins the two visible rows at fixed fractions of frame height. THE
ROWS MOVE: at the top of the grid the card tops sit at 0.280 / 0.607, and four scroll
presses later the same rows are at 0.229 / 0.557. No fixed pair can frame both, which is
why the shipped constant only ever "worked" by being loose enough to contain the card
wherever it drifted.

Everything else about the grid IS fixed -- column pitch 0.135 across all four gaps, card
width 0.130, row pitch 0.328, card height 0.2995 -- so a frame has exactly one thing to
tell us: the vertical PHASE. ban_grid solves it by pooling the NAME BANNER's two edges
across every row at once, which is what lets a row of LOCKED cards (sd 16-19 against an
owned card's 62-66, so almost no edges of its own) be placed by its neighbours' evidence.

THE TRUTH IN THIS FILE WAS READ OFF A RULER BY HAND, not produced by the code under test.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

from PIL import Image
import orchestrator as o
import ban_grid as bg

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def F(name):
    return _os.path.join(_ROOT, "test_fixtures", "ban_grid", name)


# ban_grid owns TIGHTER columns than orchestrator: the shipped 0.130 on a 0.135 pitch makes
# adjacent boxes almost touch, which is harmless for reading a name out of the middle and
# fatal for anything that looks at a card's EDGE. See CARD_COL_X_FRAC.
COLS = bg.CARD_COL_X_FRAC
# Hand-read off a ruler laid on each frame. LITERALS, never the code's own output.
TRUTH = {"scroll_p00.png": (0.280, 0.607), "scroll_p04.png": (0.229, 0.557)}
FRAMES = ["scroll_p00.png", "scroll_p04.png", "tactics_row.png"]

missing = [f for f in FRAMES if not _os.path.exists(F(f))]
print("0. fixtures")
check(not missing, f"every named fixture is present (missing: {missing})")
if missing:
    raise SystemExit(1)
IMG = {f: Image.open(F(f)).convert("RGB") for f in FRAMES}

print("1. the columns are a uniform pitch — this is what makes it an ARRAY")
pitches = [round(COLS[i + 1][0] - COLS[i][0], 4) for i in range(len(COLS) - 1)]
check(len(set(pitches)) == 1 and pitches[0] == 0.135,
      f"all four column gaps are identical at 0.135 ({pitches})")
check(round(COLS[0][1] - COLS[0][0], 4) == 0.108,
      f"and the card is 0.108 wide ({round(COLS[0][1] - COLS[0][0], 4)}) — measured off the "
      f"intensity profile, page 200 grey against a card body at 160")
check(COLS[0][1] - COLS[0][0] < o.BAN_GRID_COL_X_FRAC[0][1] - o.BAN_GRID_COL_X_FRAC[0][0],
      "and it is TIGHTER than orchestrator's, which is the whole point: the shipped box "
      "contains its card, the gap, and a sliver of both neighbours")
gap = COLS[1][0] - COLS[0][1]
check(gap > 0.02,
      f"there is real space between adjacent boxes ({gap:.3f}) — without it a neighbour's "
      f"cursor glow bleeds into this card's band")

print("2. THE ROWS MOVE — a fixed fraction cannot frame every scroll position")
check(abs(TRUTH["scroll_p00.png"][0] - TRUTH["scroll_p04.png"][0]) > 0.04,
      f"the two fixtures' first rows differ by "
      f"{abs(TRUTH['scroll_p00.png'][0] - TRUTH['scroll_p04.png'][0]):.3f} of frame height "
      f"— this is the whole reason the fit exists")
shipped = o.BAN_CARD_ROW_TOP_FRAC[0]
off = [abs(shipped - t[0]) for t in TRUTH.values()]
check(min(off) > 0.03,
      f"and the SHIPPED constant {shipped} is wrong on both by {min(off):.3f}-{max(off):.3f}")

print("3. the phase is solved, on every fixture, to within a ruler's precision")
rows = {f: bg.find_card_rows(IMG[f], COLS) for f in FRAMES}
for f in FRAMES:
    check(rows[f] is not None, f"{f}: a fit was found")
for f, (t0, t1) in TRUTH.items():
    tops = [r["top"] for r in rows[f]]
    for want in (t0, t1):
        err = min(abs(t - want) for t in tops)
        check(err <= 0.01, f"{f}: a row within 0.01 of the hand-read {want:.3f} "
                           f"(closest is {err:.4f} away)")

print("4. every box on a frame is the SAME SIZE — the cards are")
for f in FRAMES:
    hs = {round(r["bottom"] - r["top"], 4) for r in rows[f]}
    check(len(hs) == 1, f"{f}: one distinct card height ({hs})")
allh = {round(r["bottom"] - r["top"], 4) for f in FRAMES for r in rows[f]}
check(len(allh) == 1, f"...and the same height on every fixture ({allh})")

print("5. the pitch between consecutive rows is the measured one")
for f in FRAMES:
    tops = sorted(r["top"] for r in rows[f])
    gaps = [round(tops[i + 1] - tops[i], 3) for i in range(len(tops) - 1)]
    check(all(abs(g - 0.328) <= 0.002 for g in gaps),
          f"{f}: consecutive rows are 0.328 apart ({gaps})")

print("5b. ONLY WHOLE ROWS — a part-visible row is not a card to read")
# The user, 2026-09-13: "you are trying to capture a non existent row -1 (it's in the
# banned cards header area) ... wouldn't it be better to just have 2 rows be captured and
# scroll to get everything else?" Two frames here carry the two ways a row goes bad.
for f in FRAMES:
    check(1 <= len(rows[f]) <= 2,
          f"{f}: one or two rows, never three ({len(rows[f])})")
    for r in rows[f]:
        vis = (min(1.0, r["bottom"]) - max(bg.GRID_TOP_FRAC, r["top"])) / (
            r["bottom"] - r["top"])
        check(vis >= 0.65,
              f"{f}: row at {r['top']:.3f} is {vis:.3f} inside the viewport")
# tactics_row.png is the BOTTOM of the collection: the array puts a row at 0.028, whose
# card art is not drawn at all — only its name banner shows, under the header. It is the
# frame that makes this test bite, and it is named so nothing can glob it away.
check(all(r["top"] > 0.2 for r in rows["tactics_row.png"]),
      f"tactics_row.png: the header-occluded row at 0.028 is gone "
      f"({[round(r['top'], 3) for r in rows['tactics_row.png']]})")
# scroll_p00.png is the TOP: the array puts a row at 0.937, of which only a sliver of
# banner is on screen.
check(all(r["bottom"] <= 1.0 for r in rows["scroll_p00.png"]),
      f"scroll_p00.png: the sliver row at 0.937 is gone "
      f"({[round(r['bottom'], 3) for r in rows['scroll_p00.png']]})")
# ...and scroll_p04.png's first row sits at 0.230, ABOVE the clip, with 6% of its height
# cut off and every readable feature intact. A rule of "top >= GRID_TOP_FRAC" would throw
# it away; the visible-fraction rule keeps it. LITERALS, so moving a constant fails here.
check(bg.GRID_TOP_FRAC == 0.247 and bg.ROW_VISIBLE_MIN == 0.65,
      f"the measured viewport clip and gate ({bg.GRID_TOP_FRAC}, {bg.ROW_VISIBLE_MIN})")
check(any(abs(r["top"] - 0.230) < 0.01 for r in rows["scroll_p04.png"]),
      f"scroll_p04.png: the 0.230 row is KEPT — clipped 6%, wholly readable "
      f"({[round(r['top'], 3) for r in rows['scroll_p04.png']]})")

print("6. THE TACTICS FRAME — the case that forced this design")
tac = rows["tactics_row.png"]
check(tac is not None and len(tac) == 2,
      f"it fits ({len(tac) if tac else 0} rows), though most of its cards are LOCKED and "
      f"per-row detection finds nothing there")
check(any(not r["measured"] for r in tac),
      "and at least one row is placed by the pitch rather than by its own banner")

print("7. a box that is off screen is None, not a rectangle that is not there")
# NOW THAT ONLY WHOLE ROWS ARE REPORTED, no CARD box can land off screen — and section 5b
# proves it, so checking card_box for None here would be checking a thing that cannot
# happen. The guard still has a job: a SUB-box (a fraction of a card, e.g. the power disc
# a few percent above its card's top) can, and clamping each end independently gave
# y1 < y0, which PIL raises on and the viewer's tick swallowed into a label.
im0 = IMG["scroll_p00.png"]
check(bg._box_px(im0, COLS, 0, -0.40, -0.10) is None,
      "a band entirely above the frame is None, not an inverted rectangle")
check(bg._box_px(im0, COLS, 0, 1.10, 1.40) is None,
      "a band entirely below the frame is None")
straddle = bg._box_px(im0, COLS, 0, -0.10, 0.20)
check(straddle is not None and straddle[3] > straddle[1] and straddle[1] == 0,
      f"a band that straddles the top edge is clamped, not dropped ({straddle})")
for f in FRAMES:
    for i in range(len(rows[f])):
        for box in (bg.card_box(IMG[f], rows[f], i, 0, COLS),
                    bg.name_box(IMG[f], rows[f], i, 0, COLS),
                    bg.type_box(IMG[f], rows[f], i, 0, COLS)):
            check(box is not None and box[3] > box[1] and box[2] > box[0],
                  f"{f} row{i}: every box on a WHOLE row is a real rectangle ({box})")

print("8. CONTROL: it must not answer on a frame with no grid at all")
blank = Image.new("RGB", (1920, 1080), (128, 128, 128))
check(bg.find_card_rows(blank, COLS) is None,
      "a flat frame gets no fit — without this, every check above could pass on noise")

print("9. locked and owned are separated, and the gate sits BETWEEN them")
check(bg.LOCKED_SD_MAX < bg.OWNED_SD_MIN,
      f"the two gates do not overlap ({bg.LOCKED_SD_MAX} < {bg.OWNED_SD_MIN})")
p00 = rows["scroll_p00.png"]
_cand = [i for i, r in enumerate(p00) if abs(r["top"] - 0.280) < 0.01]
check(bool(_cand), f"the 0.280 row is present ({[round(r['top'], 3) for r in p00]})")
r1 = _cand[0]
# read by eye off the frame: col 2 of that row is faded, cols 0/1/3/4 are not
verdicts = {c: bg.is_locked(IMG["scroll_p00.png"], bg.card_box(IMG["scroll_p00.png"], p00, r1, c, COLS))
            for c in range(5)}
check(verdicts[2] is True, f"the faded card in that row reads locked ({verdicts[2]})")
check(all(verdicts[c] is False for c in (0, 1, 3, 4)),
      f"and the four beside it read owned ({verdicts})")

print("10. THE CURSOR — a white halo on the card's surround, not on its art")
# Three cursors identified BY EYE off the frames, and one frame where the answer must be
# "unsure". The tight columns are what make this work: with orchestrator's 0.130 box on a
# 0.135 pitch the surrounds of adjacent cards overlap and a lit neighbour bleeds in.
CURSORS = [("cursor_charlie_pepper.jpg", 0.408, 3, "Charlie Pepper"),
           ("scroll_p00.png", 0.281, 0, "Johnny Drawers"),
           ("tactics_row.png", 0.684, 0, "Pitch Focus")]
for fn, top, col, who in CURSORS:
    if not _os.path.exists(F(fn)):
        check(False, f"{fn} is missing")
        continue
    img = Image.open(F(fn)).convert("RGB")
    rr = bg.find_card_rows(img)
    idx = [i for i, r in enumerate(rr) if abs(r["top"] - top) < 0.02]
    check(bool(idx), f"{fn}: the row at {top} is present")
    if not idx:
        continue
    cell, det = bg.cursor_cell(img, rr)
    check(cell == (idx[0], col),
          f"{fn}: the cursor is {who} at r{idx[0]}c{col} (got {cell}; {det['why']})")

print("11. and it ABSTAINS when more than one card is lit")
splash = Image.open(F("splash_banning_phase.png")).convert("RGB")
srows = bg.find_card_rows(splash)
scell, sdet = bg.cursor_cell(splash, srows)
check(scell is None,
      f"the BANNING PHASE splash gets no answer (got {scell}) — its white text lands in a "
      f"whole row's halo windows and lifts four cards at once")
check(sdet["best"] is not None and sdet["second"] is not None
      and sdet["best"] / sdet["second"] < bg.CURSOR_MIN_MARGIN,
      f"...and the reason recorded is the MARGIN, not the level "
      f"({sdet['best']} vs {sdet['second']})")
check(sdet["best"] >= bg.CURSOR_GLOW_MIN,
      f"...which matters: the splash frame's brightest halo ({sdet['best']}) CLEARS the "
      f"level gate, so a threshold alone would have answered confidently and wrongly")

print("12. the cursor gates sit between two measured populations")
check(bg.CURSOR_MIN_MARGIN == 2.0,
      f"the margin is 2.0 ({bg.CURSOR_MIN_MARGIN}) — measured over 41 ban frames the "
      f"argmax/second ratio is 1.02-1.39 on splash frames and 2.86-8.90 on clean ones, "
      f"with nothing in between")
check(bg.GLOW_WHITE == 235 and bg.CURSOR_GLOW_MIN == 0.030,
      f"the level gates are the measured ones ({bg.GLOW_WHITE}, {bg.CURSOR_GLOW_MIN})")

print("13. BANNED cards — a big dark X, and darkness alone cannot find it")
banned_img = Image.open(F("cursor_charlie_pepper.jpg")).convert("RGB")
brows = bg.find_card_rows(banned_img)
hits, scores = bg.banned_cells(banned_img, brows)
check(sorted(hits) == [(0, 2), (1, 3)],
      f"the two X'd cards are found and nothing else ({sorted(hits)})")
check(o.read_ban_counter(banned_img) == 3,
      "the counter on that frame reads 3 — two of the three are on screen and the third is "
      "scrolled away, which is why finding FEWER than the counter is normal")
# the card that defeats a darkness threshold, pinned by name
blaze = max((v for k, v in scores.items() if k == (0, 1)), default=None)
check(blaze is not None and blaze < bg.BAN_X_MIN,
      f"Johnny \"Blaze\" Sweets is NOT banned ({blaze}) though its art is dark — a "
      f"dark-fraction gate scored it 0.551 against a genuinely banned 0.642 and would "
      f"have called it banned")
check(max(scores[k] for k in hits) > 0.9 and blaze < 0.6,
      f"and the two populations are far apart (X'd {max(scores[k] for k in hits)}, "
      f"dark-but-clean {blaze})")

print("14. the X gate sits ABOVE a measured negative population")
check(bg.BAN_X_NEG_MAX < bg.BAN_X_MIN,
      f"the gate {bg.BAN_X_MIN} is above the counter-0 ceiling {bg.BAN_X_NEG_MAX} — "
      f"measured over 4,840 cells on frames whose counter reads 0, so NO card on them is "
      f"banned whatever the pixels look like")
check(bg.BAN_X_MIN >= 0.78,
      f"and it is not the 0.75 that was tried first ({bg.BAN_X_MIN}): that sat at the "
      f"counter-0 p99, inside the negative population, and fired on 47 of 323 frames")

print("15. a BANNED card does not glow — so it cannot be mistaken for the cursor")
# The user believed selection also made the card glow. Measured: it does not persist.
for cell in hits:
    gv = bg.cell_glow(banned_img, brows, cell[0], cell[1])
    check(gv is not None and gv < bg.CURSOR_GLOW_MIN,
          f"banned cell r{cell[0]}c{cell[1]} has glow {gv}, under the cursor gate "
          f"{bg.CURSOR_GLOW_MIN}")
ccell, _ = bg.cursor_cell(banned_img, brows)
check(ccell is not None and ccell not in hits,
      f"and the cursor ({ccell}) is not one of the banned cards — if selection left a "
      f"persistent glow these two readers would fight over the same cell")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
