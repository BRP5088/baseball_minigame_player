"""Self-check for ocr_ban_card_name() against real ban-screen screenshots —
no API call. 18 known cards across 3 independent frames.

SAFETY PROPERTY, not an accuracy target: this must never return the WRONG
card. Returning None is acceptable — the caller falls back to the vision
read, which is correct behaviour for anything it cannot resolve confidently.

Why abstention has to be allowed: name similarity alone cannot separate a
garbled read of a KNOWN card from a clean read of an UNKNOWN one. Measured
on real data — the garbled 'oanige THE RAT TA TRAN CRUZ' scores 0.807
against its true name, while 'Frank Coker' (not in the roster) scores 0.818
against 'Brian Coker'. The ranges overlap, so any cutoff either admits false
matches or rejects some true ones. We choose to reject: a false match banned
the wrong physical card in a paid match (QA_FINDINGS_R2.md N1); an abstention
just costs one vision call."""

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
from orchestrator import (BAN_CARD_ROW_TOP_FRAC, BAN_GRID_ROW_Y_FRAC,
                          get_ban_grid_card_crop, ocr_ban_card_name)

# N23: this suite is pass/abstain based, so REVERTING to the pre-N6 geometry
# (reusing BAN_GRID_ROW_Y_FRAC for card crops) actually scores slightly BETTER
# here — 17/18 vs 16/18 — while silently reinstating the row-1 cliff, where a
# 10px frame shift took row 1 from 6/6 to 0/6. A green suite would hide that.
# Assert the row geometry directly: card rows must use their own constant,
# derived from the real ~366px pitch (0.283 of a 1292px frame).
_pitch = BAN_CARD_ROW_TOP_FRAC[1] - BAN_CARD_ROW_TOP_FRAC[0]
assert abs(_pitch - 0.283) < 0.01, (
    f"card-crop row pitch is {_pitch:.3f}, expected ~0.283 (the measured 366px "
    "row pitch). Reverting to BAN_GRID_ROW_Y_FRAC's ~0.200 reinstates the "
    "row-1 cliff — see QA_FINDINGS_R3.md N6.")
# The `or _pitch > 0.25` tail made this dead: the assertion above pins _pitch
# to (0.273, 0.293), so the right-hand side is always true and the or
# short-circuits. But the first strengthening I tried was also wrong — the two
# constants genuinely SHARE their first value (both 0.195); they start at the
# same row and diverge in PITCH. That is the real claim.
_grid_pitch = BAN_GRID_ROW_Y_FRAC[1][0] - BAN_GRID_ROW_Y_FRAC[0][0]
assert abs(_pitch - _grid_pitch) > 0.05, (
    f"card-crop pitch ({_pitch:.3f}) has converged on the grid pitch "
    f"({_grid_pitch:.3f}). They are separately measured: BAN_GRID_ROW_Y_FRAC "
    "is read as WIDTH fractions by detect_ban_grid_locked(), and reusing it "
    "for card crops reinstates the row-1 cliff (row 1 went 6/6 -> 0/6 on a "
    "10px frame shift) while SCORING BETTER on this pass/abstain suite.")

# N10: these live in test_fixtures/, NOT screenshot_log/. The screenshot
# logger's pruner deletes oldest-first from screenshot_log/, which would
# eventually eat the only regression fixtures for ban-card OCR.
SRC_DIR = "test_fixtures"

CASES = [
    ("20260824_200520_984.jpg", 0, 0, "Johnny Drawers"),
    ("20260824_200520_984.jpg", 0, 1, "Mama Jody Gain"),
    ("20260824_200520_984.jpg", 0, 3, "Jenny Jody Gain"),
    ("20260824_200520_984.jpg", 0, 4, "Donny Mekesz"),
    ("20260824_200601_124.jpg", 0, 0, "Rube Sharp"),
    ("20260824_200601_124.jpg", 0, 1, 'Austin "Cur" Bunz'),
    ("20260824_200601_124.jpg", 0, 3, "William Brown"),
    ("20260824_200601_124.jpg", 0, 4, "Jeremiah Curd"),
    ("20260824_200601_124.jpg", 1, 0, "Marian Bunz-Twarog"),
    ("20260824_200601_124.jpg", 1, 1, "Jedediah Wetters"),
    ("20260824_200601_124.jpg", 1, 3, "Timmeh Rattycum"),
    ("20260824_200601_124.jpg", 1, 4, "Joe Jody Gain"),
    ("20260824_200604_139.jpg", 0, 0, "Papa Jody Gain"),
    ("20260824_200604_139.jpg", 0, 1, 'Daniel "The Rat-Ta-Train" Cruz'),
    ("20260824_200604_139.jpg", 0, 3, "Joel Blunt"),
    ("20260824_200604_139.jpg", 0, 4, "Bartholomew Creasley"),
    ("20260824_200604_139.jpg", 1, 0, "Jake Saucepan Black"),
    ("20260824_200604_139.jpg", 1, 1, "Mickey Brown"),
]

_cache = {}
failures = []
abstained = []
for fname, rel_row, col, expected_name in CASES:
    if fname not in _cache:
        _cache[fname] = Image.open(os.path.join(SRC_DIR, fname))
    card = get_ban_grid_card_crop(_cache[fname], rel_row, col)
    result = ocr_ban_card_name(card)
    got = result.name if result else None
    if got is not None and got != expected_name:
        # A WRONG name is a hard failure — this is the property that matters.
        failures.append((fname, rel_row, col, expected_name, got))
    elif got is None:
        abstained.append((fname, rel_row, col, expected_name))

if failures:
    for f in failures:
        print(f"WRONG NAME: {f[0]} ({f[1]},{f[2]}) expected {f[3]!r} got {f[4]!r}")
    raise SystemExit(f"{len(failures)} card(s) resolved to the WRONG name — unsafe")

# Abstentions are safe but shouldn't silently grow; keep them visible and bounded.
#
# 2026-09-03: this section now scores 18/18 with ZERO abstentions, because
# ocr_ban_card_name gained a confusion-aware second pass. So the ceiling below
# has no slack left and, more importantly, it cannot tell an improvement from a
# loosening — fewer abstentions is what it rewards, and a looser matcher
# produces fewer. That was already true when this was 16/18 (see the N23 note
# above); it is now unavoidable. The guard against loosening lives in
# tests/test_ban_ocr_confusion.py, which asserts from both sides over 110 cells
# and 23 strings that must be refused. Do not treat a green line here as
# evidence the ban matcher is still strict.
MAX_ABSTENTIONS = 2
for a in abstained:
    print(f"  abstained (falls back to vision): {a[0]} ({a[1]},{a[2]}) {a[3]!r}")
assert len(abstained) <= MAX_ABSTENTIONS, (
    f"{len(abstained)} abstentions exceeds the allowed {MAX_ABSTENTIONS} — "
    "local OCR is degrading, check the crop geometry")

print(f"OK: {len(CASES)-len(abstained)}/{len(CASES)} resolved correctly, "
      f"{len(abstained)} safely abstained, 0 wrong")


# --- N1 CALL-SITE GUARD ---------------------------------------------------
# Everything above measures OUTCOMES on real frames, and that is not enough:
# deleting `cutoff=0.85, allow_surname_fallback=False` from orchestrator.py:533
# makes the section above score BETTER (18/18, 0 abstentions), because the
# loose matcher force-resolves the two cards that should abstain. MAX_ABSTENTIONS
# only has a ceiling, so fewer abstentions is silently rewarded — the metric
# moves the wrong way for the one regression that sends wrong physical input
# into a paid match.
#
# So assert the behaviour DIRECTLY, through ocr_ban_card_name itself (not
# match_roster_name — test_roster_matching.py passes its own strictness args and
# therefore proves only that the matcher CAN be strict, never that the ban path
# ASKS it to be). The tesseract stage is stubbed so the roster resolution is the
# only thing under test.
import orchestrator

_probe = Image.new("L", (200, 300), 128)


def _resolve(ocr_text):
    # Stub `_ocr_text`, NOT `pytesseract.image_to_string`. OPEN-12 moved the
    # local reads onto the in-process Tesseract C API, and a stub left on
    # pytesseract goes UNUSED rather than failing: ocr_ban_card_name then
    # really OCRs the blank grey probe, reads nothing, and abstains. Every
    # MUST_ABSTAIN case below would have passed for the wrong reason — the
    # exact "a test that passes when the code is broken" shape CLAUDE.md warns
    # about, and it is why MUST_RESOLVE is here to catch it from the other side.
    real = orchestrator._ocr_text
    orchestrator._ocr_text = lambda *a, **k: ocr_text
    try:
        return orchestrator.ocr_ban_card_name(_probe)
    finally:
        orchestrator._ocr_text = real


# Two-sided on purpose. MUST_ABSTAIN are plausible names NOT in the roster:
# under the loose matcher every one resolves to a real but DIFFERENT player
# ('Frank Coker' -> 'Brian Coker', 'Jim Gain' -> 'Joe Jody Gain'), which is
# exactly the N1 mis-ban. MUST_RESOLVE are garbled reads of cards that ARE in
# the roster, and they pin the other end: they fail if someone "fixes" a future
# abstention by cranking the cutoff until the local path resolves nothing.
MUST_ABSTAIN = ["Frank Coker", "Harold Blunte", "Jim Gain"]
MUST_RESOLVE = {"Rube Sharpe": "Rube Sharp", "Timmy Rattycum": "Timmeh Rattycum"}

n1 = []
for text in MUST_ABSTAIN:
    got = _resolve(text)
    if got is not None:
        n1.append(f"{text!r} resolved to {got.name!r} — not in the roster, so this "
                  "is the N1 mis-ban: strictness is missing at orchestrator.py:533")
for text, want in MUST_RESOLVE.items():
    got = _resolve(text)
    if got is None or got.name != want:
        n1.append(f"{text!r} gave {got.name if got else None!r}, expected {want!r} — "
                  "the local path has gone too strict to be useful")

if n1:
    for f in n1:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(n1)} N1 call-site failure(s)")

print(f"OK (N1 call-site): {len(MUST_ABSTAIN)} uncatalogued names refused, "
      f"{len(MUST_RESOLVE)} garbled-but-known names still resolved")
