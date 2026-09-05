"""Self-check for detect_ban_grid_locked() — no API call.

This function decides which ban-grid cells hold a usable card and which are
locked/faded. Everything downstream trusts it: a false "unlocked" feeds a
phantom position into the roster/vision path, and a false "locked" silently
drops a real card from the collection choose_bans() picks from.

It had no test until 2026-08-25 despite being load-bearing, and it is the one
consumer of BAN_GRID_ROW_Y_FRAC (width fractions) — a constant that must stay
independent of BAN_CARD_ROW_TOP_FRAC (height fractions, used for card crops).
This test is what makes an accidental "unification" of those two fail loudly.

Ground truth is read directly off the fixtures; see the per-frame comments.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import os

from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import (BAN_GRID_ROW_Y_FRAC, BAN_LOCKED_CONTRAST_THRESHOLD,
                          detect_ban_grid_locked)

SRC_DIR = "test_fixtures"

# (filename, expected 2x5 locked grid). True = locked/faded, False = usable.
CASES = [
    # Row 0: Johnny Drawers, Mama Jody Gain, [Harold "Fisto" Blunt LOCKED],
    #        Jenny Jody Gain, Donny Mekesz
    # Row 1: [Claude Ewer LOCKED], [William Lee-Gains LOCKED],
    #        Brandon "Binger" Ortiz, Joshua Diaz, Justin Young
    ("20260824_200520_984.jpg",
     [[False, False, True, False, False],
      [True, True, False, False, False]]),
    # Row 0: Rube Sharp, Austin "Cur" Bunz, [Jacob "Cheesehead" McQueen LOCKED],
    #        William Brown, Jeremiah Curd
    # Row 1: Marian Bunz-Twarog, Jedediah Wetters, [Brian Coker LOCKED],
    #        Timmeh Rattycum, Joe Jody Gain
    ("20260824_200601_124.jpg",
     [[False, False, True, False, False],
      [False, False, True, False, False]]),
]

failures = []
for fname, expected in CASES:
    img = Image.open(os.path.join(SRC_DIR, fname))
    got = detect_ban_grid_locked(img)
    if got != expected:
        failures.append((fname, expected, got))

if failures:
    for fname, exp, got in failures:
        print(f"FAIL {fname}")
        print(f"  expected {exp}")
        print(f"  got      {got}")
    raise SystemExit(f"{len(failures)}/{len(CASES)} frames misread")

# The width-vs-height distinction is load-bearing, so assert the separation is
# real rather than marginal: a height-aligned box straddles the threshold
# (measured 85-139) while the shipped width reading is cleanly separated.
img = Image.open(os.path.join(SRC_DIR, CASES[0][0]))
assert BAN_GRID_ROW_Y_FRAC[0][0] < 1.0, "row fractions must be fractions, not pixels"
# The threshold must sit INSIDE the measured empty gap, not merely at some
# remembered value. Re-measured 2026-08-26 over all 95 cached ban frames
# (950 cells):
#     locked cluster   ... 106.5
#     <-- empty, 35.9 wide -->
#     unlocked cluster 142.5 ...
# The previous 100.0 sat BELOW that gap, and 6 cells fell between 100.0 and
# 142.5 — each a LOCKED card whose contrast was lifted by the ban cursor
# highlighting it (+20-26 measured on one physical card as the cursor moved on
# and off). Those read as UNLOCKED, making a card the player does not own a ban
# candidate — and with TRUST_ROSTER_ONLY the lock detector is the ONLY live
# vision left on the ban path, so nothing downstream catches it.
_GAP_LO, _GAP_HI = 106.5, 142.5
assert _GAP_LO < BAN_LOCKED_CONTRAST_THRESHOLD < _GAP_HI, (
    f"BAN_LOCKED_CONTRAST_THRESHOLD={BAN_LOCKED_CONTRAST_THRESHOLD} is outside the measured "
    f"empty gap [{_GAP_LO}, {_GAP_HI}]. Below it, a cursor-highlighted LOCKED "
    f"card reads as unlocked and becomes a ban candidate; above it, genuine "
    f"unlocked cards read as locked and drop out of the collection.")
# And it should not hug either edge — the cursor effect is ~26, so leave room.
assert min(BAN_LOCKED_CONTRAST_THRESHOLD - _GAP_LO,
           _GAP_HI - BAN_LOCKED_CONTRAST_THRESHOLD) >= 10.0, (
    f"BAN_LOCKED_CONTRAST_THRESHOLD={BAN_LOCKED_CONTRAST_THRESHOLD} sits within 10 of a gap "
    "edge; the measured cursor lift alone is ~26")

print(f"OK: detect_ban_grid_locked matched all {len(CASES)} known frames "
      f"({sum(len(r) for _, e in CASES for r in e)} cells)")


# --- Vision-payload crop must contain the whole grid ---------------------
# read_ban_row_cards() sends only the card grid, not the full screen (~45%
# fewer image tokens on the one call the ban screen makes repeatedly).
#
# The box is derived from the geometry constants, and this asserts it. A
# hand-picked x1=0.78 was tried first and clipped column 4, whose cards end at
# 0.815 — hiding a fifth of every row from the model. That failure reads as
# "vision missed a card", not as a cropping bug, so it is exactly the kind that
# survives casual review.
from orchestrator import (BAN_CARD_ROW_TOP_FRAC, BAN_CROP_MARGIN,
                          BAN_GRID_CARD_HEIGHT_FRAC, BAN_GRID_COL_X_FRAC)

_cx0 = min(a for a, _ in BAN_GRID_COL_X_FRAC) - BAN_CROP_MARGIN
_cx1 = max(b for _, b in BAN_GRID_COL_X_FRAC) + BAN_CROP_MARGIN
_cy0 = min(BAN_CARD_ROW_TOP_FRAC) - BAN_CROP_MARGIN
_cy1 = max(BAN_CARD_ROW_TOP_FRAC) + BAN_GRID_CARD_HEIGHT_FRAC + BAN_CROP_MARGIN

_clip = []
for _i, (_x0, _x1) in enumerate(BAN_GRID_COL_X_FRAC):
    if _x0 < _cx0 or _x1 > _cx1:
        _clip.append(f"column {_i} (x {_x0:.3f}-{_x1:.3f}) falls outside the "
                     f"crop (x {_cx0:.3f}-{_cx1:.3f})")
for _i, _y0 in enumerate(BAN_CARD_ROW_TOP_FRAC):
    _y1 = _y0 + BAN_GRID_CARD_HEIGHT_FRAC
    if _y0 < _cy0 or _y1 > _cy1:
        _clip.append(f"row {_i} (y {_y0:.3f}-{_y1:.3f}) falls outside the "
                     f"crop (y {_cy0:.3f}-{_cy1:.3f})")
if _clip:
    for _m in _clip:
        print(f"FAIL: {_m}")
    raise SystemExit(f"{len(_clip)} ban-crop clipping failure(s)")

# And it must actually be a crop — a box covering the whole frame saves nothing.
assert (_cx1 - _cx0) * (_cy1 - _cy0) < 0.85, (
    "the ban crop covers essentially the whole frame; the payload saving is gone")

# --- The lock-detector crop margin is load-bearing -----------------------
# detect_ban_grid_locked() crops to the grid before two MaxFilter(MASK_KERNEL)
# passes (~1.9x faster). That is EXACT only while the margin exceeds the kernel
# radius: PIL zero-pads outside the image, so a pixel within radius of the crop
# edge sees fabricated black and its contrast reads high — flipping a locked
# card to "unlocked", i.e. changing which cards get banned.
#
# QA round 2 measured the crop as genuinely bit-identical, but noted margin=0
# survived every test. It no longer does.
from orchestrator import MASK_KERNEL

# Read the ACTUAL margin out of the source with ast and evaluate it. The old
# assertions were `"MASK_KERNEL // 2" in source` — a substring, satisfied by
# `MASK_KERNEL // 2 * 0` — and `_m = MASK_KERNEL // 2 + 2; assert _m > ...`,
# a tautology on a test-local variable that never touched production. Both
# mutations (margin = 0, and margin = radius - 1) survived the whole suite
# while the comment above claimed otherwise (QA, 2026-08-26).
import ast as _ast
import inspect as _inspect
import orchestrator as _o

_src = _inspect.getsource(_o.detect_ban_grid_locked)
_tree = _ast.parse(_ast.unparse(_ast.parse(_src)))   # normalise indentation
_margin_expr = None
for _node in _ast.walk(_tree):
    if (isinstance(_node, _ast.Assign) and len(_node.targets) == 1
            and isinstance(_node.targets[0], _ast.Name)
            and _node.targets[0].id == "margin"):
        _margin_expr = _node.value
assert _margin_expr is not None, (
    "no `margin = ...` assignment found in detect_ban_grid_locked — this test "
    "can no longer see the value it is guarding")

_margin_value = eval(compile(_ast.Expression(_margin_expr), "<margin>", "eval"),
                     {"MASK_KERNEL": MASK_KERNEL})
_radius = MASK_KERNEL // 2
assert _margin_value > _radius, (
    f"crop margin evaluates to {_margin_value}, which does not exceed the "
    f"kernel radius {_radius}. PIL zero-pads beyond the crop, so a margin "
    "at or below the radius leaks black into the sampled cells and a locked "
    "card can read as unlocked — which puts a card the player does not own "
    "into the ban candidates.")
_m = _margin_value

print(f"OK: lock-detector crop margin {_m} > kernel radius {MASK_KERNEL // 2} "
      f"(exact by construction)")
print(f"OK: ban vision crop x {_cx0:.3f}-{_cx1:.3f} y {_cy0:.3f}-{_cy1:.3f} "
      f"contains all {len(BAN_GRID_COL_X_FRAC)} columns and "
      f"{len(BAN_CARD_ROW_TOP_FRAC)} rows")


# --- The separable contrast filter must equal the naive one ---------------
# detect_ban_grid_locked used PIL's MaxFilter/MinFilter, which are the naive
# O(n*k^2) implementation: 6.27 s per frame at MASK_KERNEL=41, once per scroll
# iteration, ~36 s of blind CPU per ban screen. `_local_contrast` computes the
# same thing separably in 22 ms.
#
# "Same thing" is the whole claim, and this is where it is defended — the
# result decides which cards are bannable, so an approximation would silently
# change which physical cards get banned.
import numpy as _np
from PIL import ImageChops as _IC, ImageFilter as _IF

from orchestrator import MASK_KERNEL, _local_contrast

_rng = _np.random.default_rng(20260826)
for _label, _arr in (
        ("random noise", _rng.integers(0, 256, (140, 160), dtype=_np.uint8)),
        ("flat mid-grey", _np.full((90, 110), 128, dtype=_np.uint8)),
        ("hard edge", _np.hstack([_np.zeros((90, 55), _np.uint8),
                                  _np.full((90, 55), 255, _np.uint8)])),
):
    _img = Image.fromarray(_arr, mode="L")
    _pil = _np.asarray(_IC.difference(_img.filter(_IF.MaxFilter(MASK_KERNEL)),
                                      _img.filter(_IF.MinFilter(MASK_KERNEL))))
    _sep = _local_contrast(_arr, MASK_KERNEL)
    # Compare the INTERIOR: the caller crops with a margin wider than the
    # kernel radius, so no sampled cell ever sees the border, and PIL's own
    # border convention is not part of the contract.
    _r = MASK_KERNEL // 2
    _a = _pil[_r:-_r, _r:-_r].astype(int)
    _b = _sep[_r:-_r, _r:-_r].astype(int)
    _maxdiff = int(_np.abs(_a - _b).max())
    assert _maxdiff == 0, (
        f"_local_contrast disagrees with PIL on {_label}: max difference "
        f"{_maxdiff}. The separable filter is meant to be EXACT, not an "
        "approximation — a difference here changes which cards read as locked, "
        "and therefore which physical cards get banned.")

print(f"OK: separable _local_contrast is exact vs PIL on 3 synthetic patterns "
      f"(kernel {MASK_KERNEL}, interior compared)")


# --- The two contrast thresholds must stay SEPARATE -----------------------
# DOC_AUDIT: `MASK_CONTRAST_THRESHOLD` (mask_low_contrast_regions, PIL tile
# means, any frame) and `BAN_LOCKED_CONTRAST_THRESHOLD` (detect_ban_grid_locked,
# whole-cell _local_contrast, ban frames) measure DIFFERENT quantities on
# DIFFERENT inputs. They only ever coincidentally shared a value.
#
# Recalibrating the lock detector to 124.0 while they were unified silently
# regressed the masker: base crops on gameplay frames went from ~65-80% blacked
# out to ~95%. Same failure mode this file already guards for the row-geometry
# constants — independently measured values must not be merged.
import orchestrator as _o2

# `X or True` is True for every X — this assertion could never fire and had an
# empty message. The two thresholds are deliberately SEPARATE constants with
# separate consumers: unifying them silently regressed the masker, taking base
# crops from ~65-80% blacked out to ~95%.
assert _o2.MASK_CONTRAST_THRESHOLD != _o2.BAN_LOCKED_CONTRAST_THRESHOLD, (
    f"the masker threshold ({_o2.MASK_CONTRAST_THRESHOLD}) and the ban-lock "
    f"threshold ({_o2.BAN_LOCKED_CONTRAST_THRESHOLD}) are equal again. They "
    "were measured independently against different targets; unifying them "
    "regressed the masker from ~65-80% to ~95% blacked out.")
_masker_src = __import__("inspect").getsource(_o2.mask_low_contrast_regions)
_lock_src = __import__("inspect").getsource(_o2.detect_ban_grid_locked)
assert "MASK_CONTRAST_THRESHOLD" in _masker_src, (
    "mask_low_contrast_regions no longer uses MASK_CONTRAST_THRESHOLD")
assert "BAN_LOCKED_CONTRAST_THRESHOLD" in _lock_src, (
    "detect_ban_grid_locked no longer uses its own BAN_LOCKED_CONTRAST_THRESHOLD "
    "— if it shares the masker's constant again, recalibrating either one "
    "silently breaks the other")
assert "MASK_CONTRAST_THRESHOLD" not in _lock_src.replace(
    "BAN_LOCKED_CONTRAST_THRESHOLD", ""), (
    "detect_ban_grid_locked still references the masker's threshold")

print(f"OK: masker threshold {_o2.MASK_CONTRAST_THRESHOLD} and ban-lock "
      f"threshold {_o2.BAN_LOCKED_CONTRAST_THRESHOLD} are separate constants "
      "with separate consumers")


# --- the fade-in must not be read as a locked grid -----------------------
# A locked cell is detected by LOW CONTRAST, so a merely DIM cell reads as
# locked — and the ban screen fades in. Measured over the 2026-08-26 run,
# episode 105215: the first two frames reported 6/10 and 4/10 cells locked
# where the settled truth was 3/10 (row0 [0,0,1,0,0]). Four cards the player
# OWNS were marked locked, which removes them from the candidate set silently.
import orchestrator as _o

_SETTLED = [[False, False, True, False, False], [False] * 5]
_DIM1 = [[True, True, False, True, True], [False] * 5]
_DIM2 = [[True, False, True, False, False], [False] * 5]


def _with_reads(sequence):
    """Drive _settled_lock_grid over a scripted sequence of lock grids."""
    seq = list(sequence)
    calls = {"n": 0}

    def fake_detect(img):
        g = seq[min(calls["n"], len(seq) - 1)]
        calls["n"] += 1
        return g

    _cap, _det = _o.capture_screenshot_image, _o.detect_ban_grid_locked
    _o.capture_screenshot_image = lambda *a, **k: object()
    _o.detect_ban_grid_locked = fake_detect
    try:
        return _o._settled_lock_grid()[1], calls["n"]
    finally:
        _o.capture_screenshot_image, _o.detect_ban_grid_locked = _cap, _det


# The real live sequence: two bad frames, then it settles.
_grid, _n = _with_reads([_DIM1, _DIM2, _SETTLED, _SETTLED])
assert _grid == _SETTLED, (
    f"the fade-in was accepted as the lock grid ({_grid}) — owned cards are "
    "being dropped from the ban candidates")

# A grid that is stable from the first frame must not pay for extra captures
# beyond the single confirmation.
_grid, _n = _with_reads([_SETTLED])
assert _grid == _SETTLED and _n == 2, (
    f"a settled grid took {_n} reads, expected 2 (one plus one confirmation)")

# It must give up rather than wedge the run on a grid that never settles.
_alternating = [_DIM1, _DIM2] * 20
_grid, _n = _with_reads(_alternating)
assert _n <= _o.LOCK_CONFIRM_TRIES + 1, (
    f"a never-settling grid took {_n} reads — the loop is unbounded and a "
    "flickering ban screen would hang the run")

print("OK: lock grid requires two agreeing reads, is bounded, and rejects "
      "the measured fade-in frames")
