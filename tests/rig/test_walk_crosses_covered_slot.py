"""The cursor walk must cross a slot whose HALO is covered, and must still refuse
when it genuinely cannot tell where the cursor is.

A batter stranded on home plate -- a hit the pitcher's FIELDING pinned to zero
base-movements (RULES.md) -- leaves his card lying over the hand. The glow window
for the slot beneath then samples his NAME BANNER instead of a halo: measured live
2026-09-17 at 3.6-5.0 against CURSOR_GLOW_MIN 10.0, where a real cursor on the
slots either side read 22.4 and 28.2. The walk refused, and a $50 turn could not
be played twice over with nothing wrong but the view.

THE SAFETY ARGUMENT IS ONE INFERENCE: we press FROM a slot we can SEE, so had the
press been ignored we would still be on that visible slot and the next read would
not be blind. A blind read therefore PROVES the press landed, and one step of dead
reckoning is exact. From the covered slot we can no longer tell "ignored" from
"moved" -- both look blind -- so a SECOND consecutive blind read refuses.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import input_controller as ic
import local_hand

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


class Fan:
    """A five-slot fan with a real cursor and some slots whose halo is covered."""

    def __init__(self, cursor, covered=(), ignore_at=()):
        self.cursor = cursor
        self.covered = set(covered)
        self.ignore_at = list(ignore_at)   # press indices the GAME ignores
        self.presses = 0

    def press(self, key):
        self.presses += 1
        if self.presses in self.ignore_at:
            return
        if key == "move_right":
            self.cursor = min(4, self.cursor + 1)
        elif key == "move_left":
            self.cursor = max(0, self.cursor - 1)

    def look(self):
        # a covered slot shows the banner's white text, not a halo
        glow = [25.0 if (i == self.cursor and i not in self.covered)
                else (4.5 if i in self.covered else 0.3) for i in range(5)]
        return glow, [100] * 5, 5, []


def walk(fan, target):
    saved = (ic.press, ic.MOVE_SETTLE_SEC, ic.LOOK_RETRIES)
    try:
        ic.press = fan.press
        ic.MOVE_SETTLE_SEC = 0.0
        ok, _sel = ic._walk_cursor_to(target, fan.look)
    finally:
        ic.press, ic.MOVE_SETTLE_SEC, ic.LOOK_RETRIES = saved
    return ok, fan


# 1. THE CONTROL: an ordinary walk is unchanged.
ok, f = walk(Fan(cursor=0), 3)
check(ok is True and f.cursor == 3, f"an ordinary walk still arrives (ok={ok}, at {f.cursor})")

# 2. THE LIVE CASE: slot 2 covered, walk 0 -> 3 straight across it.
ok, f = walk(Fan(cursor=0, covered={2}), 3)
check(ok is True and f.cursor == 3,
      f"the walk CROSSES a covered slot and lands on the target (ok={ok}, at {f.cursor})")

# 3. Starting ON the covered slot, which is exactly where the live cursor sat.
ok, f = walk(Fan(cursor=2, covered={2}), 3)
check(ok is True and f.cursor == 3,
      f"a cursor that starts on a covered slot is FOUND and walked (ok={ok}, at {f.cursor})")
ok, f = walk(Fan(cursor=2, covered={2}), 0)
check(ok is True and f.cursor == 0,
      f"...and can be walked the other way too (ok={ok}, at {f.cursor})")

# 4. THE SAFETY BOUND. Two covered slots side by side means a second consecutive
# blind read, where "ignored" and "moved" are indistinguishable. It must refuse.
ok, f = walk(Fan(cursor=0, covered={2, 3}), 4)
check(ok is False,
      f"two adjacent covered slots REFUSE rather than dead-reckon twice (ok={ok})")

# 5. AN IGNORED PRESS WHILE ON THE COVERED SLOT is the same ambiguity, and the
# measured ignore rate is 15.2%, so this case is common enough to pin.
ok, f = walk(Fan(cursor=1, covered={2}, ignore_at=[2]), 3)
check(ok is False,
      f"a press ignored while ON the covered slot refuses, never guesses (ok={ok})")

# 6. CONTROL FOR 5: the same walk without the ignored press succeeds, so the
# refusal above is the ignore and not the crossing.
ok, f = walk(Fan(cursor=1, covered={2}), 3)
check(ok is True and f.cursor == 3,
      f"CONTROL: the same walk with no ignored press arrives (ok={ok}, at {f.cursor})")

# 7. TARGETING THE COVERED SLOT ITSELF must refuse. The loop exits on `cur ==
# target`, and after a dead-reckoned step `cur` is a BELIEF -- so without a guard this
# returns True and prints "verified" for a slot that was never seen, and the caller
# commits a card on it. Found by a SURVIVING mutant: replacing the dead-reckoning
# assignment changed no test, because every other path has a readable slot after it.
ok, f = walk(Fan(cursor=1, covered={2}), 2)
check(ok is False,
      f"walking TO a covered slot refuses -- arriving blind is not arriving (ok={ok})")
ok, f = walk(Fan(cursor=3, covered={2}), 2)
check(ok is False, f"...from either side (ok={ok})")

# 8. A cursor nobody can see anywhere still refuses -- the old behaviour, preserved.
ok, f = walk(Fan(cursor=2, covered={0, 1, 2, 3, 4}), 0)
check(ok is False, f"an invisible-everywhere cursor still refuses (ok={ok})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
