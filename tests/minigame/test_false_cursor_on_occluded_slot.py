"""I-25: an occluded disc's false argmax deadlocks a live match.

Live 2026-09-20, mid-match: slot 0's power disc was hidden under slot 1's card,
the disc finder locked onto a blob low on slot 0 and never read a digit off it,
and the glow window it anchored (still measuring the wrong pixels) read 68.6 --
the brightest slot on screen, ON A CARD's own white art (CLAUDE.md 10.35: "any
box placed ON a card reads 60-88% bright whether or not the cursor is there").
The TRUE cursor sat on slot 4, reading 22.8 -- inside cursor_slot's own docstring
population (20.7 .. 36.1) and well under slot 0's false reading. `cursor_slot`
took the argmax and answered 0; `_walk_cursor_to` pressed move_right eight times
toward whatever target it was walking to, never saw the reading move off 0, and
refused. The play-stall fallback then excluded slots one at a time and every one
refused the same way -- a total deadlock on a paid match.

TWO LAYERS, TWO FIXES:
  (1) local_hand.cursor_glow / cursor_slot -- a row whose disc was found but
      never read a digit (y_from == "disc", digit is None) cannot win the
      argmax, and neither can a glow above CURSOR_GLOW_MAX (a box on card art,
      not a halo). The raw glow is kept in the returned list for diagnostics.
  (2) input_controller._walk_cursor_to -- if the reading has not changed at all
      across CURSOR_MAX_STEPS presses, that slot is a FALSE cursor: exclude it
      and re-read: cursor_slot(glow, sel, exclude={...}) so a slot beneath the
      gate can win instead, and continue the walk from wherever it lands.

Uses the same check(cond, msg) shape as tests/minigame/test_verified_selection.py
and tests/rig/test_blind_slot_probe_select.py (checked with
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

FIX = _os.path.join(_ROOT, "test_fixtures", "hand_reads",
                     "i25_false_cursor_slot0_live_20260920.png")

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


# =========================================================================
print("(a) the live fixture: cursor_slot answers 4, not the false 0")
# =========================================================================
_full = Image.open(FIX)
_hand = dict(orch.crop_gameplay_regions(_full))["hand"]
_rows = lh.read_hand(_hand)
check(_rows[0].get("digit") is None and _rows[0].get("y_from") == "disc",
      f"slot 0's disc was found but never read a digit (the occluded-card "
      f"shape this fixture exists for); row 0 = {_rows[0]!r}")
_idx, _glow, _ = lh.cursor_glow(_hand, rows=_rows)
check(_glow[0] > lh.CURSOR_GLOW_MAX,
      f"slot 0's RAW glow is kept for diagnostics and is still the false "
      f"on-card reading, above CURSOR_GLOW_MAX ({lh.CURSOR_GLOW_MAX}): "
      f"glow={_glow}")
check(_idx == 4, f"cursor_glow must not win on slot 0's false reading; got {_idx} "
      f"(glow={_glow})")
_sel = lh.selected_cards(_rows, _hand.width / lh.ANCHOR_W)
check(lh.cursor_slot(_glow, _sel) == 4,
      f"cursor_slot must agree, from the raw glow list alone; got "
      f"{lh.cursor_slot(_glow, _sel)} (glow={_glow})")

# THE DIGIT/y_from RULE MUST BITE ON ITS OWN, NOT ONLY BACKED BY THE CEILING. On the
# i25 fixture above, 68.6 clears CURSOR_GLOW_MAX by itself, so a mutant that deletes
# ONLY the digit/y_from exclusion would still pass every check above -- the ceiling
# alone happens to catch that particular value. Faking a REAL winning row's own
# digit to None (keeping y_from == "disc", exactly the occluded-card shape) on
# cursor_on_1.png, whose true winner (index 1, glow 28.8) sits comfortably UNDER the
# ceiling, isolates the digit rule from the ceiling.
_im1 = Image.open(_os.path.join(_ROOT, "test_fixtures", "hand_cursor", "cursor_on_1.png"))
_rows1 = lh.read_hand(_im1)
check(_rows1[1].get("digit") == "6" and _rows1[1].get("y_from") == "disc",
      f"cursor_on_1's true winner is index 1, a real disc read -- row 1 = {_rows1[1]!r}")
_idx1, _glow1, _ = lh.cursor_glow(_im1, rows=_rows1)
check(_idx1 == 1 and _glow1[1] <= lh.CURSOR_GLOW_MAX,
      f"and its glow is UNDER the ceiling, so only the digit rule can exclude it "
      f"(idx={_idx1}, glow={_glow1}, ceiling={lh.CURSOR_GLOW_MAX})")
_faked1 = [dict(r) for r in _rows1]
_faked1[1]["digit"] = None
_idx1_faked, _glow1_faked, _ = lh.cursor_glow(_im1, rows=_faked1)
check(_glow1_faked[1] == _glow1[1],
      f"the RAW glow is unchanged by faking digit alone (diagnostics preserved): "
      f"{_glow1_faked} vs {_glow1}")
check(_idx1_faked != 1,
      f"but a disc-read row whose digit reads None must not win the argmax even "
      f"though its glow clears the ceiling; got {_idx1_faked} (glow={_glow1_faked})")

# THE RULE MUST NOT BE THE BLANKET "digit is None", OR A LEGITIMATE cursor on a
# tactics slot goes blind too (skeptic review, 2026-09-20). Tactics cards never
# carry a digit -- digit is None on EVERY tactics-slot-0 fixture on disk -- but
# their y comes from y_from == "fallback", not "disc": no false circle was ever
# found there, so the row must stay ELIGIBLE. sweep_f02_slot0.png is the user-
# labelled ground truth for exactly this: the cursor is really on slot 0, a
# tactics card, digit None throughout.
_im_tac = Image.open(_os.path.join(_ROOT, "test_fixtures", "hand_cursor", "sweep_f02_slot0.png"))
_rows_tac = lh.read_hand(_im_tac)
check(_rows_tac[0].get("digit") is None and _rows_tac[0].get("kind") == "tactics"
      and _rows_tac[0].get("y_from") == "fallback",
      f"sweep_f02_slot0's row 0 is a legitimate digit-None, y_from='fallback' "
      f"tactics row -- row 0 = {_rows_tac[0]!r}")
_idx_tac, _glow_tac, _ = lh.cursor_glow(_im_tac, rows=_rows_tac)
check(_idx_tac == 0,
      f"and the cursor is STILL named there -- the row stays eligible because "
      f"y_from is 'fallback', not 'disc'; got {_idx_tac} (glow={_glow_tac})")
_sel_tac = lh.selected_cards(_rows_tac, _im_tac.width / lh.ANCHOR_W)
check(lh.cursor_slot(_glow_tac, _sel_tac) == 0,
      f"cursor_slot agrees from the raw glow list alone; got "
      f"{lh.cursor_slot(_glow_tac, _sel_tac)} (glow={_glow_tac})")


# =========================================================================
print("(b) cursor_slot: the ceiling, on synthetic glow lists")
# =========================================================================
check(lh.cursor_slot([68.6, 0.3, 0.6, 0.3, 22.8], []) == 4,
      "a false on-card 68.6 at slot 0 must not beat a true 22.8 at slot 4")
check(lh.cursor_slot([68.6, 0, 0, 0, 0], []) is None,
      "an on-card false reading with nothing else lit must abstain, not name "
      "the false slot")
check(lh.cursor_slot([30, 0, 0, 0, 0], []) == 0,
      "CONTROL: a legitimate reading under the ceiling still names its slot")


# =========================================================================
print("(c) _walk_cursor_to: a false slot is excluded and the walk continues")
# =========================================================================
N = ic.MAX_HAND_SIZE


class FalseCursorScreen:
    """The reader ALWAYS answers a fixed false slot, regardless of presses --
    the i25 shape one layer deeper than the ceiling reaches. CURSOR_GLOW_MAX
    already excludes an on-card reading THIS bright (part 1 of the fix), so a
    glow UNDER the ceiling is used here on purpose: this exercises the walk's
    OWN exclusion logic in _walk_cursor_to, not local_hand's ceiling, for a
    persistently-wrong reading the ceiling alone cannot catch."""

    def __init__(self, glow, exclude=()):
        self.glow = list(glow)
        self.sent = []
        self.exclude = set(exclude)

    def selected(self):
        return []

    def _ys(self):
        return [100] * N

    def look(self):
        return self.glow, self._ys(), N, self.selected()

    def press(self, key):
        self.sent.append(key)


_real_press = ic.press
try:
    # The false cursor sits at slot 0 (15.0, UNDER CURSOR_GLOW_MAX so local_hand's
    # ceiling cannot catch it); the real one sits at slot 4 (12.0). Neither value
    # ever changes on a re-look, which is what makes it false: a real cursor moves
    # with the presses toward it.
    check(15.0 <= lh.CURSOR_GLOW_MAX and 12.0 >= lh.CURSOR_GLOW_MIN,
          f"the synthetic false/true pair must sit UNDER the ceiling and OVER the "
          f"floor, or this test exercises the ceiling instead of the walk's own "
          f"exclusion logic (ceiling={lh.CURSOR_GLOW_MAX}, floor={lh.CURSOR_GLOW_MIN})")
    s = FalseCursorScreen([15.0, 0.3, 0.6, 0.3, 12.0])
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(4, s.look)
    check(ok is True,
          f"a false cursor pinned at slot 0 must not deadlock a walk toward the "
          f"real cursor at slot 4; got {ok!r}")
    check(s.sent.count("move_right") == ic.CURSOR_MAX_STEPS,
          f"the walk must spend its full budget pressing toward the target "
          f"before concluding the reading is false, not give up early or skip "
          f"straight to exclusion; move_right count={s.sent.count('move_right')}")

    # CONTROL: a reader that answers correctly needs no exclusion and walks as
    # it always did -- one press per slot crossed.
    class RealCursorScreen:
        def __init__(self, start):
            self.cur = start
            self.sent = []

        def selected(self):
            return []

        def look(self):
            glow = [0.2] * N
            glow[self.cur] = 27.0
            return glow, [100] * N, N, self.selected()

        def press(self, key):
            self.sent.append(key)
            if key == "move_right":
                self.cur = min(N - 1, self.cur + 1)
            elif key == "move_left":
                self.cur = max(0, self.cur - 1)

    r = RealCursorScreen(0)
    ic.press = r.press
    ok2, sel2 = ic._walk_cursor_to(4, r.look)
    check(ok2 is True, f"CONTROL: a genuinely moving cursor must still walk to "
          f"its target; got {ok2!r}")
    check(r.sent.count("move_right") == 4,
          f"CONTROL: exactly 4 presses cross the whole fan from slot 0 to slot "
          f"4 -- no exclusion budget spent; got {r.sent.count('move_right')} "
          f"in {r.sent!r}")
finally:
    ic.press = _real_press

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a false on-card glow reading cannot win the argmax, the live fixture "
      "reads slot 4 instead of slot 0, and a walk pinned on a false slot "
      "excludes it and reaches the real cursor rather than deadlocking")
