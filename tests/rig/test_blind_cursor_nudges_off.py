"""An UNLOCATABLE cursor must be recovered by moving, not by refusing forever.

Live 2026-09-20, pitching half of a paid match. The cursor sat on hand slot 4 and
local_hand.cursor_slot answered None, because slot 4 read 6.9-9.8 against
CURSOR_GLOW_MIN 10.0 while every other slot read 0.0-1.0. _walk_cursor_to refused,
and the engine could neither discard slot 4 NOR navigate away from it to play slots
1 and 2. One unreadable position deadlocked the whole match.

CLAUDE.md 10.35 measured the cause and it is permanent, not a bad frame:
"slot 4 never exceeds 11.0 at ANY offset, while slots 0-3 read 26-28 at the shipped
position." Four attempts to move or reshape that window were tried and ALL raised
the FALSE reading as much as the TRUE one, so the window is not the lever.

THE RECOVERY IS FREE BECAUSE MOVING COMMITS NOTHING. move_left / move_right are
navigation; select_card is the only toggle and nothing lands until confirm_play. So
a nudge cannot select, deselect, play or discard -- it risks nothing that the refusal
was protecting -- while landing the cursor on any of slots 0-3 makes it readable by
roughly 3x the gate.

WHAT THIS FILE PINS:
  1. a readable cursor is NEVER nudged (the control -- otherwise the fix is just
     "press extra buttons", and a reader that works would be disturbed);
  2. an unlocatable cursor on a READABLE FAN is nudged and recovered;
  3. an unreadable FAN still refuses immediately, because there is nothing to
     navigate and pressing blind into an unknown screen is how cards get thrown;
  4. the nudging is BOUNDED, so a genuinely dead reader cannot press forever --
     which would be the original deadlock wearing the fix's clothes.
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

import input_controller as ic                                        # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


N = ic.MAX_HAND_SIZE
_presses = []


def _fake_press(action, *a, **k):
    _presses.append(action)


class Screen:
    """A fan whose cursor sits at `slot`, reported with `gain` brightness.

    gain below CURSOR_GLOW_MIN reproduces the live slot-4 case: the fan reads
    perfectly, every row has a y, and cursor_slot still cannot name a slot.
    """

    def __init__(self, slot, gain, rows=None):
        self.slot, self.gain, self.rows = slot, gain, rows if rows is not None else N

    def look(self):
        glow = [0.2] * N
        if 0 <= self.slot < N:
            glow[self.slot] = self.gain
        return glow, [100] * N, self.rows, []

    def moved(self, action, *a, **k):
        _presses.append(action)
        if action == "move_left":
            self.slot = max(0, self.slot - 1)
            # leaving the blind slot makes it legible, exactly as 10.35 measured
            if self.slot != 4:
                self.gain = 27.0
        elif action == "move_right":
            self.slot = min(N - 1, self.slot + 1)


_real_press = ic.press
try:
    # --- 1. CONTROL: a readable cursor is never nudged -------------------------
    _presses.clear()
    s = Screen(slot=2, gain=27.0)
    ic.press = _fake_press
    ok, _sel = ic._walk_cursor_to(2, s.look)
    check(ok is True, f"a readable cursor already on target must succeed; got {ok!r}")
    check("move_left" not in _presses,
          f"CONTROL: a readable cursor must NOT be nudged; pressed {_presses!r}. "
          "Without this the fix is indistinguishable from pressing extra buttons.")

    # --- 2. THE BUG: unlocatable cursor on a readable fan is recovered ----------
    _presses.clear()
    s = Screen(slot=4, gain=8.0)          # the live reading: fan fine, slot 4 blind
    ic.press = s.moved
    ok, _sel = ic._walk_cursor_to(2, s.look)
    check("move_left" in _presses,
          f"an unlocatable cursor on a READABLE fan must be nudged off the blind "
          f"slot; pressed {_presses!r}. Refusing here is the 2026-09-20 deadlock.")
    check(ok is True,
          f"after recovering, the walk to the target must succeed; got {ok!r}")

    # --- 3. an unreadable FAN still refuses, with no presses -------------------
    # Nudging into a screen we cannot read is how a card gets thrown by accident.
    _presses.clear()
    s = Screen(slot=4, gain=8.0, rows=0)
    ic.press = _fake_press
    ok, _sel = ic._walk_cursor_to(2, s.look)
    check(ok is False, f"an unreadable fan must still refuse; got {ok!r}")
    check(_presses == [],
          f"an unreadable fan must press NOTHING; pressed {_presses!r}")

    # --- 4. the nudging is BOUNDED ---------------------------------------------
    # A cursor that never becomes readable must not press forever -- that is the
    # original deadlock with a different log line.
    _presses.clear()

    class NeverReadable(Screen):
        def moved(self, action, *a, **k):
            _presses.append(action)      # moves, but never becomes legible

    s = NeverReadable(slot=4, gain=8.0)
    ic.press = s.moved
    ok, _sel = ic._walk_cursor_to(2, s.look)
    check(ok is False,
          f"a cursor that never becomes readable must end in a refusal; got {ok!r}")
    check(len(_presses) <= ic.CURSOR_BLIND_NUDGES,
          f"nudging is unbounded: {len(_presses)} presses against a budget of "
          f"{ic.CURSOR_BLIND_NUDGES}. An unbounded recovery is the deadlock again.")
    # PIN THE LITERAL (10.11): a bound read from the constant it guards rises with it
    # and the check can never fail. A sibling test shipped exactly that mistake today
    # and a mutant setting the bound to 999 survived.
    check(ic.CURSOR_BLIND_NUDGES == 8,
          f"CURSOR_BLIND_NUDGES is {ic.CURSOR_BLIND_NUDGES}, not 8. It is derived in "
          "input_controller's comment from MAX_HAND_SIZE and the 15.20% press-drop "
          "rate; moving it needs that derivation redone.")
finally:
    ic.press = _real_press

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a blind cursor is nudged onto a readable slot, a readable one is left alone, "
      "an unreadable fan still refuses, and the nudging is bounded")
