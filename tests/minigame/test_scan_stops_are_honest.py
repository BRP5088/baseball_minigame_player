"""A scan that stopped EARLY must not be cached, and a blind budget must mean its comment.

  TWO BREAKS ENDED THE SCAN MID-COLLECTION WITHOUT RECORDING ANYTHING. A roster GAP
  fires the same `if not roster_hits: break` as the designed end-of-roster stop, and
  a MID-ANIMATION frame reads every cell as locked and fires the all-locked break.
  Neither set _saw_desync, so the cache gate accepted the fragment and served it to
  every later ban screen in the process with ZERO captures -- a one-match problem
  turned into a whole-process one.

  The all-locked door is the more reachable one and the code explicitly believed it
  closed: its comment says the dim-frame hazard is confined to the first batch
  because "every later one follows a keypress and is covered by the scrollbar
  check". The scrollbar check verifies the SCROLL POSITION. expected_positions comes
  from detect_ban_grid_locked, about which the scrollbar says nothing.

  BAN_NAV_MAX_BLIND said "consecutive unreadable frames per target" and counted
  CUMULATIVE ones -- `blind` was never reset on a good look. ban_cursor_absolute
  returns None BY DESIGN while the scrollbar is mid-travel, which is what a
  scrolling press produces, so blind frames arrive interleaved with good ones and
  the budget was spent across the whole approach. Same failure the separate
  move/blind budgets were introduced to fix.

NOTE ON WHAT IS *NOT* HERE: an earlier version gated the cache on the scan having
observed scroll level 7. That is an INVENTED CONSTANT -- a collection short enough
to fit the viewport never reaches the bottom clamp, and nothing has measured that
every real ban screen does. Both existing rigs rejected it instantly and their
controls said why. The suspect breaks are marked AT the break, where the reason is
known, instead.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import input_controller as ic

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


class Card:
    def __init__(self, n): self.name = n


GRID = [(r, c, Card(f"c{r}{c}")) for r in range(8) for c in range(5)]


class _T:
    @staticmethod
    def sleep(_): pass


# A FAR TARGET ON PURPOSE. The interleaved sequence below must contain MORE than
# BAN_NAV_MAX_BLIND blind frames for the cumulative-vs-consecutive distinction to
# bite at all, and one None can only sit between two good looks -- so the walk has
# to be long enough to supply that many good looks. (7, 4) is 7 downs + 4 rights =
# 11 moves, inside BAN_NAV_MAX_STEPS. A nearer target made the first mutant SURVIVE:
# six blind frames against a budget of ten passes either way.
TARGET = (7, 4)


def walk(look_seq, target=TARGET):
    """Run select_bans_verified against a scripted look() and report the presses."""
    it = iter(look_seq)
    rec = []
    saved = {n: getattr(ic, n) for n in ("press", "time")}
    try:
        ic.press = lambda a, *r, **k: rec.append(a)
        ic.time = _T
        ic.select_bans_verified(
            GRID, {target},
            look=lambda: next(it, None),
            confirm_ban=lambda *a, **k: True,
            log=lambda *a, **k: None)
    finally:
        for n, v in saved.items():
            setattr(ic, n, v)
    return rec


N = ic.BAN_NAV_MAX_BLIND

# INTERLEAVED blind frames: one None, one good reading, repeated. CUMULATIVELY that
# is more than N; CONSECUTIVELY it never exceeds one. The walk must keep going.
inter = []
for row in range(8):
    inter += [None, (row, 0)]
for col in range(1, 5):
    inter += [None, (7, col)]
inter += [(7, 4)] * 10
assert sum(1 for x in inter if x is None) > N, "the sequence must out-blind the budget"
rec = walk(inter)
check("select_card" in rec,
      f"interleaved blind frames do NOT exhaust the budget — the walk reached the "
      f"target and pressed ({rec.count('move_down')} move_down)")

# A genuine RUN of blind frames must still stop it. Without this the reset could be
# unconditional, which removes the budget entirely.
rec2 = walk([None] * (N + 5) + [(7, 4)] * 10)
check("select_card" not in rec2,
      f"CONTROL: {N + 5} CONSECUTIVE blind frames still exhaust the budget and the "
      f"walk refuses ({rec2})")

# And the un-mutated code must actually be able to place at all.
rec3 = walk([(7, 4)] * 12)
check("select_card" in rec3,
      f"CONTROL: a cursor already on the target places it: {rec3[:3]}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
