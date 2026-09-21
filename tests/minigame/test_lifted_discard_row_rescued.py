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

FIX, in `orchestrator.hand_cursor_look` only (nothing else touched): a row is
ALSO treated as position-unknown when `kind == 'tactics'` AND `digit is None`
AND `type is None` -- a genuine tactics card almost always has its `type`
read from its own banner (that is the normal case, not the exception; `digit`
is None for every tactics row by construction, garbled or not, so it adds no
selectivity of its own but is kept per the exact shape observed in the
frames). This lets the EXISTING I-21 "selected by inference" rescue in
`_select_verified` catch the case, without adding new machinery there.

THE CONTROL THIS EARNS SPECIAL ATTENTION. A genuine tactics card whose type
genuinely fails to read (a `find_tactics`/banner miss unrelated to any lift)
would ALSO get its y nulled by this rule, since `type is None` cannot tell
"garbled by an overlapping lift" from "this card's own banner did not read
this frame" -- `hand_cursor_look` sees one fresh frame with no memory of
prior reads, so a baseline-vs-current comparison (which WOULD disambiguate
the two) is not available without touching `_select_verified`/`_clear_strays`
to pass it in, which this fix is scoped not to do. Traced downstream in
`input_controller._clear_strays`: for a slot OUTSIDE `want`, a newly-None y
triggers the SAME one-look-then-refuse path (I-26) an unrelated flicker
already goes through -- never a wrong commit, only an extra re-look and, in
the worst case, one refuse-and-retry cycle a poll later. For a slot INSIDE
`want` (I-28), a newly-None y is read as "expected, not a stray" and, if
readable at baseline, rescued by the SAME I-21 inference this ticket needs --
which is the intended effect for the actual target. The residual risk (a
transient type-read miss on a NON-target tactics card causing one extra
re-look) is real, narrow, UNMEASURED, and always resolves in the safe
direction (refuse/retry, never a wrong play) -- CLAUDE.md 10.32 says so
rather than asserting it is zero.

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

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the I-36 lift/overlap misread (kind='tactics', digit=None, "
      "type=None on a fallback y) is now treated as position-unknown, so "
      "the existing I-21 rescue names the target selected by inference "
      "instead of pressing select_card a second time and toggling the "
      "just-lifted card back down; a genuine tactics card whose banner DID "
      "read keeps its measured position on the very same frame.")
