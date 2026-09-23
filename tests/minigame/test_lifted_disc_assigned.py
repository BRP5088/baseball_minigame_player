"""I-62: a card raised so far that no candidate ever lands within SLOT_TOL never
got a raised-digit search at all, because that search (the third pass in
_read_fan) only revisits a row already emitted with kind=="player" -- and a slot
with NO candidate is emitted through the "best[i] is None" branch, which never
called it. Full census: agent_progress/issues/I-62/progress.md.

THE 128-ROW HYPOTHESIS THE TICKET STARTED FROM IS REFUTED, NOT CONFIRMED. The
i21-census's 128 "position found via SLOT_TOL, no disc circle" rows (a candidate
WAS found, just with no circle to read) are a DIFFERENT population from the one
this fix touches. A brute-force digit search 3x wider than RAISED_SEARCH_DY/DX
recovers ZERO of the 69 player-kind rows in that population (max score 0.798,
under MIN_SCORE 0.80) and the tactics-kind "digit" field is not even what
orchestrator drops a tactics card on (it indexes "type"/"bonus", never "digit" --
orchestrator.py hand_to_cards/local_hand_cards). So RAISED_SEARCH_DY/DX/SLOT_TOL
are UNCHANGED here -- no new constant, and every existing gate (MIN_SCORE,
DISC_MIN_R/REACH via read_digit, SLOT_TOL) still governs every read.

What IS fixed is a different, narrower gap: the "no candidate at all" population
(the i21-census's "unknown" + "tactics,None" rows, 171 in the dropped_* corpus
alone), where the row is emitted with kind != "player" (or kind == "unknown") and
so the SAME raised-digit search -- unchanged RAISED_SEARCH_DY/DX/STEP/R -- is now
ALSO tried from that branch, before the banner decides kind. It can only ADD a
reading (gated by read_digit's own MIN_SCORE, the same guarantee the other two
raised-search call sites already rely on): a settled hand never even reaches the
branch (best[i] is already found for every slot), so nothing already-correct can
be overridden by it. Measured recovery: 1 of 171 dropped_* rows (score 0.966) and
the refused_select evidence frame below (score 0.868-0.882 depending on capture).

Fixtures are copies of the exact evidence frames (diagnostics/ is gitignored, so
a fresh checkout needs its own copy -- CLAUDE.md: "Fixtures live at the PROJECT
ROOT in test_fixtures/, never under tests/").
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "lifted_disc_i62")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


def _row(fname, slot):
    img = Image.open(os.path.join(FIX, fname)).convert("RGB")
    rows = local_hand.read_hand(img)
    check(f"{fname}: fan fits (5 rows)", len(rows) == 5, f"{len(rows)} rows")
    return rows[slot] if len(rows) == 5 else None


# ---- 1. the refused_select evidence frame now reads its raised card's digit ----
# target slot 3, misclassified kind="tactics" by a banner false-positive on a
# nearby wreath graphic before this fix (agent_progress/issues/lift-transition/),
# so the player-only raised search never ran for it at all.
r = _row("refused_select_1790046227383193000.png", 3)
if r is not None:
    check("refused_select_1790046227383193000 slot 3 reads its digit",
          r.get("digit") == "8", str(r))
    check("... via the new raised-digit search, not a stray earlier pass",
          r.get("digit_from_raised_search") is True, str(r))
    check("... and is now correctly typed player, not tactics",
          r.get("kind") == "player", str(r))

# ---- 2. a dropped_* frame from the SAME "no candidate at all" population -------
r = _row("dropped_1789956238428199000.png", 3)
if r is not None:
    check("dropped_1789956238428199000 slot 3 reads its digit",
          r.get("digit") == "6", str(r))
    check("... via the new raised-digit search",
          r.get("digit_from_raised_search") is True, str(r))

# ---- 3. SAFETY: two frames from the REFUTED 128-row population must NOT gain a
# spurious digit -- a candidate WAS found there (this fix's new branch never
# runs, because best[i] is not None for these slots), and the census found
# nothing genuinely readable nearby at any window width tried. -------------------
r = _row("dropped_1789623748871691000_still_blind.png", 2)
if r is not None:
    check("dropped_1789623748871691000 slot 2 stays unread (no invented digit)",
          r.get("digit") is None, str(r))
    check("... the fix's new branch did not fire on it",
          not r.get("digit_from_raised_search"), str(r))

r = _row("dropped_1789994617273763000_still_blind.png", 4)
if r is not None:
    check("dropped_1789994617273763000 slot 4 stays unread (no invented digit)",
          r.get("digit") is None, str(r))

# ---- 4. CONTROL: a fully-settled hand (nothing raised) is byte-for-byte the
# same read as before this change -- every slot's candidate already clears
# SLOT_TOL with a circle, so best[i] is never None and the new branch is a
# structural no-op here. ----------------------------------------------------------
img = Image.open(os.path.join(FIX, "control_settled_nothing_raised.png")).convert("RGB")
rows = local_hand.read_hand(img)
check("control: fan fits (5 rows)", len(rows) == 5, f"{len(rows)} rows")
if len(rows) == 5:
    check("control: every slot already had a disc (branch never touched)",
          all(r.get("y_from") == "disc" for r in rows),
          str([r.get("y_from") for r in rows]))
    check("control: no digit came from the new search path",
          not any(r.get("digit_from_raised_search") for r in rows),
          str(rows))
    expected_digits = ["1", "8", "5", "5", "4"]
    got_digits = [r.get("digit") for r in rows]
    check("control: digits unchanged", got_digits == expected_digits,
          f"got {got_digits}")

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
