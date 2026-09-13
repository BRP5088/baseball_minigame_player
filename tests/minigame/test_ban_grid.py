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


COLS = o.BAN_GRID_COL_X_FRAC
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
check(round(COLS[0][1] - COLS[0][0], 4) == 0.130, "and the card is 0.130 wide")

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

print("6. THE TACTICS FRAME — the case that forced this design")
tac = rows["tactics_row.png"]
check(tac is not None and len(tac) >= 3,
      f"it fits ({len(tac) if tac else 0} rows), though most of its cards are LOCKED and "
      f"per-row detection finds nothing there")
check(any(not r["measured"] for r in tac),
      "and at least one row is placed by the pitch rather than by its own banner")

print("7. a box that is off screen is None, not a rectangle that is not there")
found_none = False
for f in FRAMES:
    for i, r in enumerate(rows[f]):
        cb = bg.card_box(IMG[f], rows[f], i, 0, COLS)
        nb = bg.name_box(IMG[f], rows[f], i, 0, COLS)
        for box in (cb, nb):
            if box is None:
                found_none = True
            else:
                check(box[3] > box[1] and box[2] > box[0],
                      f"{f} row{i}: box is not inverted ({box})") if False else None
                if not (box[3] > box[1] and box[2] > box[0]):
                    check(False, f"{f} row{i}: INVERTED box {box}")
check(found_none,
      "at least one off-screen banner returned None — this is what crashed the viewer "
      "when each end was clamped independently and gave y1 < y0")

print("8. CONTROL: it must not answer on a frame with no grid at all")
blank = Image.new("RGB", (1920, 1080), (128, 128, 128))
check(bg.find_card_rows(blank, COLS) is None,
      "a flat frame gets no fit — without this, every check above could pass on noise")

print("9. locked and owned are separated, and the gate sits BETWEEN them")
check(bg.LOCKED_SD_MAX < bg.OWNED_SD_MIN,
      f"the two gates do not overlap ({bg.LOCKED_SD_MAX} < {bg.OWNED_SD_MIN})")
p00 = rows["scroll_p00.png"]
r1 = [i for i, r in enumerate(p00) if abs(r["top"] - 0.280) < 0.01][0]
# read by eye off the frame: col 2 of that row is faded, cols 0/1/3/4 are not
verdicts = {c: bg.is_locked(IMG["scroll_p00.png"], bg.card_box(IMG["scroll_p00.png"], p00, r1, c, COLS))
            for c in range(5)}
check(verdicts[2] is True, f"the faded card in that row reads locked ({verdicts[2]})")
check(all(verdicts[c] is False for c in (0, 1, 3, 4)),
      f"and the four beside it read owned ({verdicts})")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
