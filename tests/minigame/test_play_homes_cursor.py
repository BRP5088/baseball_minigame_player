"""select_and_play must HOME before it moves and FORGET after it commits.

Without this the cursor belief survives a play, and a play re-deals the hand, so
every move on the next turn is counted from a position the cursor no longer holds.
Measured on run 20260908_235423: play turns that happened to home first logged the
right card 4 of 4; those that did not, 0 of 6 (Fisher exact p = 0.0048).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import input_controller as ic

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def run(card_index, tactics_index=None, start_col=None):
    """Drive select_and_play with press() stubbed; return the actions it emitted."""
    sent = []
    real_press = ic.press
    ic.press = lambda action, *a, **k: sent.append(action)
    ic._cursor_col = start_col
    try:
        ic.select_and_play(card_index, tactics_index, allow_blind=True)
    finally:
        ic.press = real_press
    return sent


# 1. A play from an UNKNOWN cursor homes: four blind move_left presses first.
sent = run(2, start_col=None)
lead = sent[:4]
check(lead == ["move_left"] * 4,
      f"an unknown cursor homes with four move_left first (got {sent[:6]})")
check("confirm_play" in sent, "...and still commits the play")

# 2. THE BUG ITSELF: a play from a STALE BELIEF must still home. Before the fix the
#    belief was trusted, so the cursor moved from a position it no longer held.
sent = run(2, start_col=3)
check(sent[:4] == ["move_left"] * 4,
      f"a play homes even when a cursor position is remembered (got {sent[:6]})")

# 2b. THE CASE THAT force EXISTS FOR, and which a mutation test caught this test
#     missing. reset_hand_cursor() skips the four presses only when the belief says 0,
#     so a believed-0 is the one position where an unforced home does nothing at all.
#     It is also a position the loop reaches often: play the leftmost card and the
#     belief becomes 0. If the deal then moves the cursor, the next play trusts a zero
#     that is no longer true and every move is counted from the wrong place.
sent = run(2, start_col=0)
check(sent[:4] == ["move_left"] * 4,
      f"a play homes even when the belief says 0, which an unforced home would skip "
      f"(got {sent[:6]})")

# 3. The belief is dropped AFTER the commit, because the play re-deals the hand.
ic._cursor_col = None
sent = run(1)
check(ic._cursor_col is None,
      f"the cursor belief is forgotten after the play (got {ic._cursor_col!r})")

# 4. Two plays in a row: the SECOND one must home too. This is the six-turn run
#    that lost every card in the measured match.
calls = []
real_press = ic.press
ic.press = lambda action, *a, **k: calls.append(action)
ic._cursor_col = None
try:
    ic.select_and_play(2, allow_blind=True)
    first = list(calls)
    calls.clear()
    ic.select_and_play(2, allow_blind=True)
    second = list(calls)
finally:
    ic.press = real_press
check(second[:4] == ["move_left"] * 4,
      f"the SECOND consecutive play homes as well (got {second[:6]})")
check(first.count("move_left") == second.count("move_left"),
      f"both plays take the same route to the same index "
      f"({first.count('move_left')} vs {second.count('move_left')} move_left)")

# 5. Anti-vacuity: the stub really ran, and a tactics card still gets selected.
sent = run(0, tactics_index=3)
check(sent.count("select_card") == 2, f"a tactics card is still selected (got {sent})")
check(len(sent) >= 6, "the stub captured a real sequence, not an empty one")

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\nall green")
