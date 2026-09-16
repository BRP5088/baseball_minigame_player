"""The blind ban fallback must home the cursor, and must not report the intent as placed.

QA round 4, and it reaches CLAUDE.md's named "worst outcome available": three cards
banned, ALL WRONG, with read_ban_counter reading 3/3 and the run printing a clean
result.

Two defects in one branch.

  RETURNED THE INTENT. `return sorted(banned_positions)` on the on_blind path, so
  run()'s completeness check `sorted(_placed) != sorted(banned_positions)` was False
  BY CONSTRUCTION and ban_nav_incomplete was never recorded. A success path and a
  failure path with identical output (10.1) -- inside the guard added to prevent
  exactly this.

  HANDED OVER AN UNHOMED CURSOR. The gate is `toggled == 0`, which is a fact about
  SELECT presses and says nothing about MOVE presses: the navigator can spend
  BAN_NAV_MAX_STEPS per target without toggling anything. select_bans_and_start_full's
  own docstring says "Assumes the caller starts at (0, 0)" and it does not home, so
  every one of its counted presses then lands on the wrong card.

Saturation is the only homing available with a blind cursor: move_up at row 0 and
move_left at column 0 are no-ops, so over-pressing costs presses, never position.
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
TARGETS = {(1, 3), (4, 0), (4, 1)}


def drive(cursor_reads, confirm=False):
    """Run the real select_bans_verified with every screen/input call stubbed."""
    rec = {"presses": [], "blind_called": 0, "selects": []}
    saved = {n: getattr(ic, n) for n in ("press", "time")}

    class _T:
        @staticmethod
        def sleep(_): pass
    try:
        ic.press = lambda a, *r, **k: (rec["presses"].append(a),
                                       rec["selects"].append(a) if a == "select_card" else None)
        # snapshot the press list AT HANDOVER, so the tail check below cannot be
        # satisfied by the navigator's own moves earlier in the run
        ic.time = _T
        placed = ic.select_bans_verified(
            GRID, set(TARGETS),
            look=cursor_reads,
            confirm_ban=lambda *a, **k: confirm,
            on_blind=lambda: (rec.update(blind_called=rec["blind_called"] + 1,
                                         at_blind=list(rec["presses"]))),
            log=lambda *a, **k: None)
    finally:
        for n, v in saved.items():
            setattr(ic, n, v)
    return placed, rec


# A cursor that READS but never arrives: the navigator moves toward each target,
# re-reads the same stale position, and gives up without ever toggling. That is
# precisely the state the on_blind gate was written for.
placed, rec = drive(lambda: (6, 4))

check(rec["blind_called"] == 1,
      f"the fallback fired once ({rec['blind_called']})")

check(placed == [],
      f"it returns what it VERIFIED, which is nothing: {placed} "
      f"(it used to return the intent {sorted(TARGETS)}, making run()'s "
      "completeness check unreachable)")

check(sorted(placed) != sorted(TARGETS),
      "the return is distinguishable from success, so run() can record "
      "ban_nav_incomplete")

# The cursor must be HOMED before the dead-reckoned path is handed control. Its
# presses are counted from (0, 0), so an unhomed handover bans the wrong cards.
# ASSERT THE TAIL AT HANDOVER, not a total. A count over the whole run is
# satisfied by the navigator's own 42 moves toward the targets, so `count >= 14`
# passes with the saturation DELETED -- the same vacuous-check shape this suite
# keeps producing. What must be true is that the LAST presses before on_blind are
# the saturation, in order: N move_ups then N move_lefts.
N = ic.BAN_NAV_MAX_STEPS
tail = rec.get("at_blind", [])[-2 * N:]
check(tail == ["move_up"] * N + ["move_left"] * N,
      f"the {2 * N} presses immediately before handover are the saturation "
      f"({N} up then {N} left); got {tail[:4]}...{tail[-4:]} "
      f"(len {len(tail)})")

check(rec["selects"] == [],
      f"and it toggled NOTHING itself: {rec['selects']}")

# CONTROL. Without this every check above passes on a function that always returns
# [] and never places anything -- which would be a worse bug than the one fixed.
seq = {"at": None}


def walking_cursor():
    """A cursor that actually arrives wherever the navigator is heading."""
    return seq["at"]


def drive_success():
    rec = {"presses": [], "blind_called": 0}
    saved = {n: getattr(ic, n) for n in ("press", "time")}

    class _T:
        @staticmethod
        def sleep(_): pass
    order = sorted(TARGETS)
    seq["i"] = 0
    seq["at"] = order[0]

    def look():
        return seq["at"]

    def confirm(*a, **k):
        seq["i"] += 1
        if seq["i"] < len(order):
            seq["at"] = order[seq["i"]]
        return True
    try:
        ic.press = lambda a, *r, **k: rec["presses"].append(a)
        ic.time = _T
        placed = ic.select_bans_verified(
            GRID, set(TARGETS), look=look, confirm_ban=confirm,
            on_blind=lambda: rec.update(blind_called=rec["blind_called"] + 1),
            log=lambda *a, **k: None)
    finally:
        for n, v in saved.items():
            setattr(ic, n, v)
    return placed, rec


ok_placed, ok_rec = drive_success()
check(sorted(ok_placed) == sorted(TARGETS),
      f"CONTROL: a cursor that ARRIVES places all three and says so: {sorted(ok_placed)}")
check(ok_rec["blind_called"] == 0,
      f"CONTROL: and the fallback does not fire ({ok_rec['blind_called']})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
