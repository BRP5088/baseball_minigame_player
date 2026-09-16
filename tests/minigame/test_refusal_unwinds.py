"""A refused play puts back down whatever IT raised -- and nothing else.

OBSERVED LIVE 2026-09-16. The engine chose 8/0 + a fielding boost. The player
card selected fine; the TACTICS select could not be verified -- local_hand's own
comment records why, find_tactics stops matching a card once it is selected, so
a tactics target goes unreadable AT THE MOMENT IT LIFTS. _select_verified then
pressed again, and select_card is a TOGGLE, so the second press put it back
down. The call refused honestly and committed nothing... and left the 8/0
LIFTED on a board the next caller would read as clean.

_verified_select_and_play's own comment already names the consequence: the retry
selects its own target and confirm_play commits BOTH. It was reproduced once
with [0, 2] going in together.

Plain asserts: four incompatible check() signatures live in this suite.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import input_controller as ic

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


class Board:
    """A fake fan. `lifted` is the truth; presses toggle it."""

    def __init__(self, lifted=(), select_works=True):
        self.lifted = set(lifted)
        self.select_works = select_works
        self.cursor = 0
        self.presses = []

    def look(self):
        ys = [100 if i in self.lifted else 160 for i in range(ic.MAX_HAND_SIZE)]
        glow = [30.0 if i == self.cursor else 0.0 for i in range(ic.MAX_HAND_SIZE)]
        return glow, ys, ic.MAX_HAND_SIZE, sorted(self.lifted)

    def press(self, action, **kw):
        self.presses.append(action)
        if action == "move_right":
            self.cursor = min(self.cursor + 1, ic.MAX_HAND_SIZE - 1)
        elif action == "move_left":
            self.cursor = max(self.cursor - 1, 0)
        elif action == "select_card":
            # THE TOGGLE. A select on a lifted card puts it DOWN -- which is the
            # mechanism that made the live failure look like "never landed".
            if self.select_works or self.cursor in self.lifted:
                self.lifted.symmetric_difference_update({self.cursor})


real_press, real_sleep = ic.press, None
import time as _t
_real_sleep = _t.sleep
try:
    _t.sleep = lambda *a, **k: None

    # 1. THE LIVE CASE: the player card goes up, the TACTICS select never verifies,
    #    and the call must refuse WITH THE BOARD AS IT FOUND IT.
    b = Board()
    hard = {"n": 0}

    def press_tactics_fails(action, **kw):
        # slot 0 is the tactics card here: every select on it is swallowed
        if action == "select_card" and b.cursor == 0:
            b.presses.append(action)
            return
        b.press(action, **kw)

    ic.press = press_tactics_fails
    ok = ic._verified_select_and_play(1, 0, b.look)
    want("the play is refused", ok is False, str(ok))
    want("and NOTHING is left lifted", not b.lifted,
         f"slot(s) {sorted(b.lifted)} left up -- the next caller would commit them")

    # 2. A CARD THAT WAS ALREADY UP IS NOT OURS TO CLEAR. Clearing it would be the
    #    same overreach in the other direction.
    b2 = Board(lifted={3})
    ic.press = lambda a, **k: (b2.presses.append(a) if (a == "select_card" and b2.cursor == 0)
                               else b2.press(a, **k))
    ok = ic._verified_select_and_play(1, 0, b2.look)
    want("a pre-existing selection survives a refusal", 3 in b2.lifted,
         f"lifted={sorted(b2.lifted)} -- slot 3 was up before this call ran")
    want("but ours is still cleared", 1 not in b2.lifted, f"lifted={sorted(b2.lifted)}")
    # 3. THE WALK REFUSAL, which is the OTHER early return and which the two cases
    #    above never touch -- a mutant that stopped unwinding there SURVIVED them.
    #    Here the player card selects, then the cursor cannot reach the tactics
    #    slot at all (every move press is swallowed), so _walk_cursor_to gives up.
    b3 = Board()

    def press_moves_fail(action, **kw):
        if action in ("move_left", "move_right"):
            b3.presses.append(action)          # sent, but the cursor never moves
            return
        b3.press(action, **kw)

    ic.press = press_moves_fail
    b3.cursor = 1                               # already on the player card
    ok = ic._verified_select_and_play(1, 4, b3.look)
    want("a walk that cannot reach its target refuses", ok is False, str(ok))
    want("and the card it had already raised is put back down", not b3.lifted,
         f"slot(s) {sorted(b3.lifted)} left up after a WALK refusal")

    # 4. A CARD THAT WENT UP WITHOUT BEING AIMED AT IS NOT UNWOUND. _select_verified's
    #    own comment: "something that was NOT up before has gone up, and it is not the
    #    target. Pressing again compounds it." test_verified_selection pins exactly ONE
    #    select press on that path, and a first version of this unwind pressed on the
    #    stray and took it to three.
    b4 = Board()

    def press_lifts_wrong(action, **kw):
        if action == "select_card":
            b4.presses.append(action)
            b4.lifted.symmetric_difference_update({(b4.cursor + 1) % ic.MAX_HAND_SIZE})
            return
        b4.press(action, **kw)

    ic.press = press_lifts_wrong
    ok = ic._verified_select_and_play(2, None, b4.look)
    want("a wrong-card lift is refused", ok is False, str(ok))
    want("and the unwind does NOT press on the stray",
         b4.presses.count("select_card") == 1,
         f"{b4.presses.count('select_card')} select presses -- pressing again compounds it")

finally:
    ic.press = real_press
    _t.sleep = _real_sleep

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
