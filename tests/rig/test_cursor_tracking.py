"""Exhaustive correctness check for cursor tracking.

Saving presses is worthless if it selects the wrong card. This simulates the
REAL cursor (clamped 0..4, as the game clamps at the ends) through the presses
that input_controller actually emits, and asserts the selected index is the
requested one — from every true starting position, cold and warm.
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
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import input_controller as ic

ACTS = []
ic.press = lambda a, *x, **k: ACTS.append(a)
N = ic.MAX_HAND_SIZE


def emit(fn, *a):
    ACTS.clear()
    fn(*a)
    return list(ACTS)


def simulate(seq, start):
    """Real cursor position through a press sequence; returns indices selected."""
    pos, picks = start, []
    for act in seq:
        if act == "move_left":
            pos = max(0, pos - 1)
        elif act == "move_right":
            pos = min(N - 1, pos + 1)
        elif act == "select_card":
            picks.append(pos)
    return picks


bad = []

# --- COLD: belief unknown, cursor could genuinely be anywhere --------------
for true_start in range(N):
    for target in range(N):
        ic.invalidate_cursor()
        picks = simulate(emit(ic.select_and_play, target), true_start)
        if picks != [target]:
            bad.append(f"COLD true_start={true_start} target={target} -> {picks}")

# --- WARM: belief is correct because we just navigated there ---------------
# Model the real sequence: navigate to `first` (cold), then to `second` with
# the belief carried over. The simulated cursor carries over identically.
for true_start in range(N):
    for first in range(N):
        for second in range(N):
            ic.invalidate_cursor()
            seq1 = emit(ic.select_and_play, first)
            pos_after = simulate(seq1, true_start)
            if pos_after != [first]:
                continue                      # cold failure already recorded
            seq2 = emit(ic.select_and_play, second)
            picks = simulate(seq2, first)     # cursor really is at `first`
            if picks != [second]:
                bad.append(f"WARM at={first} target={second} -> {picks}")

# --- with a tactics card: two selections, both must be right --------------
for card in range(N):
    for tac in range(N):
        if tac == card:
            continue
        ic.invalidate_cursor()
        picks = simulate(emit(ic.select_and_play, card, tac), 0)
        if picks != [card, tac]:
            bad.append(f"TACTICS card={card} tac={tac} -> {picks}")

# --- discard, then the belief MUST be invalidated -------------------------
for true_start in range(N):
    for target in range(N):
        ic.invalidate_cursor()
        emit(ic.select_and_discard, target)
        if ic._cursor_col is not None:
            bad.append("discard left a cursor belief behind — the game deals "
                       "a replacement and auto-lifts it, so the position is "
                       "not ours to predict")

print(f"  cold {N*N}, warm {N*N*N}, tactics {N*(N-1)}, discard {N*N} cases")
if bad:
    for b in bad[:12]:
        print("  WRONG:", b)
    print(f"  {len(bad)} FAILURES")
    sys.exit(1)
print("  all navigations select the requested card")


# --- a misfire must drop the belief --------------------------------------
# A misfire means a keystroke may have been swallowed, which is precisely the
# event that leaves the real cursor somewhere other than where we think. A
# stale belief would turn one dropped press into a run of wrong cards.
ic.invalidate_cursor()
emit(ic.select_and_play, 2)
assert ic._cursor_col == 2, "belief not established"
for _ in range(ic.MISFIRES_BEFORE_BACKOFF):
    ic.report_misfire()
assert ic._cursor_col is None, (
    "a misfire left the cursor belief intact — the next selection would "
    "navigate from a position the game may not be at")

# --- worst case is never worse than the old blind homing -----------------
ic.invalidate_cursor()
cold = len(emit(ic.select_and_play, 4))
# LITERAL 4, not MAX_HAND_SIZE - 1. Computing the expectation from the
# constant under test makes this true for ANY value: MAX_HAND_SIZE = 3 survived
# the whole suite while homing two presses short of the left edge, so every
# index landed on the wrong card (QA, 2026-08-26). test_input_timing.py:407-413
# records that incident and fixed itself; this file was left as it was.
assert ic.MAX_HAND_SIZE == 5, (
    f"MAX_HAND_SIZE is {ic.MAX_HAND_SIZE}; the press counts below are pinned "
    "to 5 and must be re-derived, not silently rescaled")
assert cold == 4 + 4 + 2, (
    f"cold path is {cold} presses; it must still home (4) then navigate, "
    "i.e. exactly the old behaviour")
warm = len(emit(ic.select_and_play, 4))
assert warm < cold, f"warm path ({warm}) saves nothing over cold ({cold})"

print(f"  cold path {cold} presses (unchanged), warm path {warm} — "
      f"{cold - warm} saved per selection")
