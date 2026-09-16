"""A discard must be PROVEN before confirm_play, or it plays the card.

REPRODUCED LIVE 2026-09-16. select_and_discard pressed confirm_discard and then
confirm_play with nothing in between -- its own comment said "there is nothing
left to verify". On this console presses get dropped, and a swallowed
confirm_discard leaves the card merely SELECTED, so confirm_play PLAYS it. The
worst card in the hand (a 5/0) was pitched at the opponent.

THE EVIDENCE WAS A COUNTER NOTHING READ: discards_left was 2 before and 2 after,
while the ROUND pips went 4 -> 5 and the diamond changed.

Plain asserts: four incompatible check() signatures live in this suite.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import time as _t

import input_controller as ic

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


class Game:
    """A fan plus a discards counter. confirm_discard may be swallowed."""

    def __init__(self, discards=2, discard_lands=True, counter_readable=True):
        self.lifted = set()
        self.cursor = 0
        self.sent = []
        self.discards = discards
        self.discard_lands = discard_lands
        self.counter_readable = counter_readable

    def look(self):
        ys = [100 if i in self.lifted else 160 for i in range(ic.MAX_HAND_SIZE)]
        glow = [30.0 if i == self.cursor else 0.0 for i in range(ic.MAX_HAND_SIZE)]
        return glow, ys, ic.MAX_HAND_SIZE, sorted(self.lifted)

    def discards_look(self):
        return self.discards if self.counter_readable else None

    def press(self, action, **kw):
        self.sent.append(action)
        if action == "move_right":
            self.cursor = min(self.cursor + 1, ic.MAX_HAND_SIZE - 1)
        elif action == "move_left":
            self.cursor = max(self.cursor - 1, 0)
        elif action == "select_card":
            self.lifted.symmetric_difference_update({self.cursor})
        elif action == "confirm_discard":
            if self.discard_lands:
                self.discards -= 1
                self.lifted.discard(self.cursor)


_real_press, _real_sleep = ic.press, _t.sleep
try:
    _t.sleep = lambda *a, **k: None

    # 1. THE LIVE FAILURE: confirm_discard is swallowed. confirm_play must NOT be
    #    sent, because sending it plays the card.
    g = Game(discard_lands=False)
    ic.press = g.press
    ok = ic.select_and_discard(1, look=g.look, discards_look=g.discards_look)
    want("a swallowed confirm_discard is refused", ok is False, str(ok))
    want("and confirm_play is NOT sent", "confirm_play" not in g.sent,
         f"sent={g.sent} -- confirm_play here PLAYS the card")
    want("the counter is untouched", g.discards == 2, str(g.discards))

    # 2. A DISCARD THAT LANDS still commits, exactly as before.
    g2 = Game(discard_lands=True)
    ic.press = g2.press
    ok = ic.select_and_discard(1, look=g2.look, discards_look=g2.discards_look)
    want("a landed discard is committed", ok is True, str(ok))
    want("confirm_play IS sent", "confirm_play" in g2.sent, str(g2.sent))
    want("the counter fell", g2.discards == 1, str(g2.discards))

    # 3. AN UNREADABLE COUNTER IS NOT THE SAME AS "IT DID NOT DROP", and the two
    #    want opposite actions: a landed discard left uncommitted strands the game
    #    on its own PLAY prompt. So commit, loudly, rather than refuse.
    g3 = Game(discard_lands=True, counter_readable=False)
    ic.press = g3.press
    # CAPTURE THE OUTPUT. Committing unverified is the right call here, but it must
    # not READ like a verified discard -- that is CLAUDE.md 10.1's whole family, a
    # success path and a silent path with identical output. A mutant that deleted the
    # warning changed nothing else and SURVIVED until this was checked.
    import contextlib, io as _io
    _cap = _io.StringIO()
    with contextlib.redirect_stdout(_cap):
        ok = ic.select_and_discard(1, look=g3.look, discards_look=g3.discards_look)
    _out = _cap.getvalue()
    want("an unreadable counter still commits", ok is True, str(ok))
    want("...and confirm_play is sent", "confirm_play" in g3.sent, str(g3.sent))
    want("...and it says the discard was UNVERIFIED", "UNVERIFIED" in _out,
         f"nothing warned; the caller cannot tell this from a checked discard: {_out!r}")

    # 4. NO SEAM AT ALL -> the old behaviour, unchanged, so existing callers and the
    #    blind path are not silently altered.
    g4 = Game(discard_lands=False)
    ic.press = g4.press
    ok = ic.select_and_discard(1, look=g4.look)
    want("with no counter seam the behaviour is unchanged", ok is True, str(ok))
finally:
    ic.press = _real_press
    _t.sleep = _real_sleep

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
