"""I-36: the half's second discard was refused 3x running, then the stall
breaker played -- a TOGGLE bug in the same family as I-21/I-37.

Live 2026-09-21, `overnight/run_live_20260921n.log` (the last "the discard was
REFUSED 3x on this exact hand" block, pitching half, 1 discard left, hand
"0: 5/1  1: 6/0  2: fielding_boost +1  3: 5/0  4: 6/0", target slot 3, the
weakest card by (power, secondary)). `agent_progress/issues/I-36/progress.md`
(read-only investigator's diagnosis, ESTABLISHED from
`screenshot_log/run_20260921_080311/`) traced the exact frames: slot 3
genuinely lifts on the first select_card press, but for 2-5 seconds the
overlapping neighbour card makes `read_hand` misclassify slot 3's row as
`kind='tactics', digit=None, type=None, y_from='fallback'` -- a REAL (wrong)
y, not a None one.

I-37 (merged into this branch, `worktree-agent-a6d8c8aabe7906748`) widened
`read_hand`'s FAN-PRESENCE gate so a lifted card is not dropped from the read
entirely. It does NOT fix this: I-37 is about whether the fan is admitted at
all, not about how one row inside it gets TYPED. Measured directly against
this ticket's own failing window (`agent_progress/issues/I-36/progress.md`'s
378-frame block, `screenshot_log/run_20260921_080311/`, 08:14:49-08:15:27):
167 of 378 frames still misread slot 3 exactly this way even with I-37 in
place.

ROOT CAUSE, unchanged from the investigator's diagnosis. `orchestrator.
hand_cursor_look`'s null rule (~line 7465, pre-fix) only treats a row as
"position unknown" when `y_measured is False` OR the row is NOT typed
'tactics' and came from a fallback position. A row that flips to `kind ==
'tactics'` during the overlap keeps its (wrong) fallback y, so `_ys[3]` reads
a real number, `_select_verified` concludes the press "did not land", and
presses select_card AGAIN -- a TOGGLE, which puts the just-lifted card back
down. Three consecutive 5-attempt exhaustions on this exact target (never
seen elsewhere in the same run) is the shape of a TOGGLE loop, not the
measured ~15.2%-clustered ordinary press-drop rate (CLAUDE.md 5).

FIX v1, in `orchestrator.hand_cursor_look` only: a row is ALSO treated as
position-unknown when `kind == 'tactics'` AND `type is None` -- a genuine
tactics card almost always has its `type` read from its own banner (the
normal case, not the exception). This lets the EXISTING I-21 "selected by
inference" rescue in `_select_verified` catch the case, with no new machinery
there. (An earlier draft also required `digit is None`; DROPPED, not pinned
-- see "MUTANT (c)" below.)

**v1 WAS REFUTED, NARROWLY, BY AN INDEPENDENT SKEPTIC**
(`agent_progress/issues/I-36-skeptic/progress.md`, two working repros against
the real code, not committed): v1's widened null rule makes `_ys[i]` go None
for ANY `kind=='tactics'`/`type is None` row, genuine or garbled, and BEFORE
v1 that could never happen for a tactics row at all (the pre-I-36 rule
explicitly excluded `kind == "tactics"`), so I-21's inference branch in
`_select_verified` (and the identical heuristic in `_clear_strays`'s
`_want_inferred`) was newly REACHABLE on a TACTICS TARGET, not just a
misclassified player lift. A genuine tactics target whose select press is
DROPPED and whose banner transiently misreads `type=None` on the SAME look
that follows is then named "selected by inference" although it never lifted
-- `confirm_play`/`confirm_discard` then commits the OTHER card only, silent
(a lost boost, not a wrong card). Measured on real frames
(`screenshot_log/run_20260921_080311/`): the ambient (genuinely-at-rest)
version of this misread is RARE, ~0.4% of tactics-row instances (5 of
~1,145), longest observed run 4 consecutive frames -- well under
`SELECT_RETRY_CONFIRM_SEC` (1.6s) -- but reachable, not hypothetical.

FIX v2 (this file). The widened null rule in `hand_cursor_look` is UNCHANGED
from v1 -- it still cannot tell "garbled by an overlap" from "this banner
just missed a read" from one frame alone, and does not try to. Instead the
INFERENCE that CONSUMES the null is gated on what the row was typed AT
BASELINE, before any press: `_select_verified` now also asks whether the
target's row read `kind == 'tactics'` on the very first, pre-press look, and
refuses to trust the inference if it did -- I-36's actual bug (a PLAYER card
mid-lift, misread as tactics) always has a baseline kind of 'player', so it
is unaffected; the skeptic's exploit (a genuine tactics card, untouched)
always has a baseline kind of 'tactics', so it is now refused and the ordinary
retry-and-look loop runs instead, exactly as it did before I-36 existed.
`_clear_strays`'s two `_want_inferred` sites get the identical gate, sourced
from the SAME baseline look its callers already take (threaded through as a
new `kinds0` parameter, the same way `ys0` already is).

THE PLUMBING. `hand_cursor_look`'s 4-element return (`glow, ys, n, sel`) is
unchanged in SHAPE -- ~20 call sites in `input_controller.py` alone unpack it
positionally, and so does every test's own `look()` stub, so widening it to 5
elements would be a breaking change everywhere rather than a fix in one
place. Instead `sel` (already a `list`) is an `orchestrator._CursorSel`, a
`list` subclass that behaves as a plain list to every existing consumer and
ALSO carries `.kinds`, the per-slot kind from the SAME look, for a caller
that asks. `getattr(sel, "kinds", None)` is how `_select_verified`/
`_clear_strays` read it; a `look()` that returns a plain list (any test stub,
any caller written before this) supplies no kinds, and the gate is then
PERMISSIVE -- i.e. unchanged, pre-tightening behaviour -- which is why every
sibling test below (and I-21's own) still passes unmodified: none of them
exercises a tactics target, so none of them has anything to gate.

MUTANT (c), asked and resolved: is the (already-redundant) `digit is None`
clause in the null rule worth PINNING with its own mutant, or dropping? The
skeptic's own mutant -- drop ONLY `digit is None`, keep `type is None` --
SURVIVED the full v1 suite, confirming it never varies for a tactics row
(no disc to read a digit from, by construction) and contributes no
selectivity. DROPPED here, not pinned: an untested clause that looks
load-bearing is worse than none (CLAUDE.md 10.9), and `type is None` is the
semantically correct discriminator on its own -- what makes a row "genuinely
tactics" is that its banner read, not that an unrelated field is empty.

Uses the same `check(cond, msg)` shape as
`tests/minigame/test_hand_read_two_lifted.py` and
`tests/minigame/test_select_stops_when_lift_unreadable.py` (checked with
`grep -m1 -o "def check(.*)"` on both before writing this one).
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

from PIL import Image                                                 # noqa: E402

import input_controller as ic                                         # noqa: E402
import local_hand as lh                                               # noqa: E402
import orchestrator as orch                                           # noqa: E402

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


FIX_DIR = _os.path.join(_ROOT, "test_fixtures", "hand_reads")
BEFORE = _os.path.join(FIX_DIR, "i36_lifted_discard_before.jpg")
GARBLED = _os.path.join(FIX_DIR, "i36_lifted_discard_garbled.jpg")
AFTER = _os.path.join(FIX_DIR, "i36_lifted_discard_after.jpg")

for fp in (BEFORE, GARBLED, AFTER):
    check(_os.path.exists(fp), f"fixture exists: {fp}")
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)


def _regions(fp):
    """The same two-key dict orchestrator.hand_cursor_look asks
    _grab_settle_regions for, built from a real archived frame -- these are
    FULL 1920x1080 captures, not pre-cropped hand strips (I-37's own lesson:
    an earlier probe here opened fixtures directly and scored raw-pixel gates
    at the wrong scale)."""
    full = Image.open(fp)
    return dict(orch.crop_gameplay_regions(full))


_real_grab = orch._grab_settle_regions
_real_press = ic.press

# =========================================================================
print("(1) the real before/garbled/garbled sequence is rescued by inference, "
      "one press only")
# =========================================================================
_queue = [_regions(BEFORE), _regions(GARBLED), _regions(GARBLED)]
_presses = []
try:
    orch._grab_settle_regions = lambda names: _queue.pop(0)
    ic.press = lambda key: _presses.append(key)
    ok, sel = ic._select_verified(3, orch.hand_cursor_look)
finally:
    orch._grab_settle_regions = _real_grab
    ic.press = _real_press

check(ok is True,
      f"the real I-36 before/garbled/garbled sequence must be rescued by "
      f"I-21's inference, not exhaust its retries; got {ok!r}")
check(sel == [3], f"slot 3 must be named selected; got {sel!r}")
check(_presses.count("select_card") == 1,
      f"exactly one select_card press -- a second would TOGGLE the "
      f"already-lifted card back down, which is the I-36 bug itself; got "
      f"{_presses.count('select_card')} in {_presses!r}")

# =========================================================================
print("(2) CONTROL: a genuine tactics card (its banner DID read) keeps its "
      "measured y on the same garbled frame")
# =========================================================================
try:
    orch._grab_settle_regions = lambda names: _regions(GARBLED)
    glow2, ys2, n2, sel2 = orch.hand_cursor_look()
finally:
    orch._grab_settle_regions = _real_grab

check(n2 == 5, f"expected a 5-row fan on the garbled frame; got {n2}")
check(ys2[2] is not None,
      f"CONTROL: slot 2 (fielding_boost, a genuine tactics card whose banner "
      f"DID read) must keep its measured y -- the widened null must not "
      f"touch a real tactics row just because it sits on a frame with a "
      f"garbled neighbour; got ys={ys2!r}")
check(ys2[3] is None,
      f"and slot 3 (the garbled lift, kind='tactics' with no type read) must "
      f"be nulled on the SAME frame; got ys={ys2!r}")

# =========================================================================
print("(3) SYNTHETIC: a before/after pair where slot 3 reads "
      "tactics/None/None after the press must be named selected by "
      "inference, with no second select_card press")
# =========================================================================
_hand_img = _regions(BEFORE)["hand"]


def _row(kind, digit, y, y_from, type_=None):
    return {"kind": kind, "digit": digit, "y": y, "y_measured": True,
            "y_from": y_from, "type": type_, "secondary": 0 if kind == "player" else None}


BASELINE_ROWS = [
    _row("player", "5", 203, "disc"),
    _row("player", "6", 152, "disc"),
    _row("tactics", None, 135, "fallback", type_="fielding_boost"),
    _row("player", "5", 156, "disc"),        # slot 3, target, at rest
    _row("player", "6", 208, "disc"),
]
GARBLED_ROWS = list(BASELINE_ROWS)
GARBLED_ROWS[3] = _row("tactics", None, 235, "fallback", type_=None)  # the I-36 shape

_synthetic_queue = [BASELINE_ROWS, GARBLED_ROWS, GARBLED_ROWS]


def _fake_cursor_glow(hand_img, rows=None, _boxes=None):
    return None, [0.0] * 5, _synthetic_queue.pop(0)


_real_cursor_glow = lh.cursor_glow
_presses3 = []
try:
    orch._grab_settle_regions = lambda names: {"hand": _hand_img, "home_plate": None}
    lh.cursor_glow = _fake_cursor_glow
    ic.press = lambda key: _presses3.append(key)
    ok3, sel3 = ic._select_verified(3, orch.hand_cursor_look)
finally:
    orch._grab_settle_regions = _real_grab
    lh.cursor_glow = _real_cursor_glow
    ic.press = _real_press

check(ok3 is True,
      f"the synthetic tactics/None/None-after-press pair must also be "
      f"rescued by inference; got {ok3!r}")
check(sel3 == [3], f"slot 3 must be named selected; got {sel3!r}")
check(_presses3.count("select_card") == 1,
      f"exactly one select_card press on the synthetic pair too; got "
      f"{_presses3.count('select_card')} in {_presses3!r}")

# =========================================================================
print("(4) THE SKEPTIC'S REPRO: a GENUINE tactics target, its select press "
      "DROPPED, misreads type=None twice running while its y never leaves "
      "REST -- must NOT be named selected by inference. The walker retries; "
      "when the retry actually lands and the lift is read, it succeeds.")
# =========================================================================
REST_Y = lh.SLOT_TACTICS[3][1]           # 150 at scale 1 -- genuinely AT REST
LIFT_Y = REST_Y - lh.SELECTED_MIN_RISE - 25   # comfortably past the lift gate

TACTICS_BASELINE_ROWS = [
    _row("player", "5", 203, "disc"),
    _row("player", "6", 152, "disc"),
    _row("tactics", None, 135, "fallback", type_="fielding_boost"),
    _row("tactics", None, REST_Y, "fallback", type_="fielding_boost"),  # slot 3
    _row("player", "6", 208, "disc"),
]
# The DROPPED press: nothing moved (still REST_Y), only the banner glitched.
GARBLED_AT_REST_ROWS = list(TACTICS_BASELINE_ROWS)
GARBLED_AT_REST_ROWS[3] = _row("tactics", None, REST_Y, "fallback", type_=None)
# The RETRY actually lands: genuinely lifted, banner reads fine again.
GENUINE_LIFT_ROWS = list(TACTICS_BASELINE_ROWS)
GENUINE_LIFT_ROWS[3] = _row("tactics", None, LIFT_Y, "fallback", type_="fielding_boost")

# baseline, attempt-1 post-press (garbled), attempt-1 recheck (still garbled),
# attempt-2 post-press (genuinely lifted this time)
_skeptic_queue = [TACTICS_BASELINE_ROWS, GARBLED_AT_REST_ROWS,
                  GARBLED_AT_REST_ROWS, GENUINE_LIFT_ROWS]


def _fake_cursor_glow_skeptic(hand_img, rows=None, _boxes=None):
    return None, [0.0] * 5, _skeptic_queue.pop(0)


_presses4 = []
try:
    orch._grab_settle_regions = lambda names: {"hand": _hand_img, "home_plate": None}
    lh.cursor_glow = _fake_cursor_glow_skeptic
    ic.press = lambda key: _presses4.append(key)
    ok4, sel4 = ic._select_verified(3, orch.hand_cursor_look)
finally:
    orch._grab_settle_regions = _real_grab
    lh.cursor_glow = _real_cursor_glow
    ic.press = _real_press

check(ok4 is True,
      f"a genuine tactics target must still be selected once the retry "
      f"actually lands and the lift is read; got {ok4!r}")
check(sel4 == [3],
      f"slot 3 must be named selected on the GENUINE, geometric read (not "
      f"inference); got {sel4!r}")
check(_presses4.count("select_card") == 2,
      f"the dropped first press must be RETRIED (not inferred-selected) and "
      f"the second must land for real -- exactly 2 presses; got "
      f"{_presses4.count('select_card')} in {_presses4!r}")
check(len(_skeptic_queue) == 0,
      f"every scripted frame must have been consumed -- if the inference had "
      f"wrongly fired on the garbled-at-rest frame, the function would have "
      f"returned early and left frames in the queue; {len(_skeptic_queue)} "
      f"unconsumed")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the I-36 lift/overlap misread (kind='tactics', type=None on a "
      "fallback y) is treated as position-unknown, so a PLAYER-baseline "
      "target is named selected by inference instead of toggled back down "
      "by a second press; a genuine tactics card whose banner DID read "
      "keeps its measured position on the same frame; and -- the skeptic's "
      "gap -- a TACTICS-baseline target is never trusted on inference alone, "
      "so a dropped press against a genuine, untouched tactics card is "
      "retried rather than falsely reported selected.")
