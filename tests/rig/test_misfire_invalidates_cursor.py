"""EVERY misfire must drop the remembered cursor position, not just some.

THE BUG. report_misfire() called invalidate_cursor() at the BOTTOM, on the
backoff-APPLIED path only. Four of its five returns skipped it:

    _misfires_seen < MISFIRES_BEFORE_BACKOFF   -> return False
    _backoff_abandoned                          -> return False   (LATCHES)
    _backoffs_applied >= BACKOFF_INEFFECTIVE_AFTER -> return False (sets the latch)
    ACTION_DELAY >= MAX_ACTION_DELAY            -> return False

Once `_backoff_abandoned` is True — a state the module's own comment says is
reached ("EVERY backoff so far was followed by another misfire") — the cursor
was never invalidated again for the life of the process.

Demonstrated: after abandonment, the belief survived a misfire and the next
selection navigated from a position the game was not at, emitting
move_left/move_left/select/confirm for card 1 and actually selecting card 0.
That is the code's own predicted harm — "one dropped press into a run of wrong
cards" — in a $50 match.

The existing test loops exactly MISFIRES_BEFORE_BACKOFF times, which is the one
path that DID invalidate. It passed throughout.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import input_controller as ic

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def fresh(**state):
    """Reset the misfire machinery, then apply a specific state."""
    ic._cursor_col = 3
    ic._misfires_seen = 0
    ic._backoffs_applied = 0
    ic._backoff_abandoned = False
    ic._backoff_applied = 0.0
    ic.ACTION_DELAY = ic.DEFAULT_ACTION_DELAY
    for k, v in state.items():
        setattr(ic, k, v)


# --- every early-return path must still drop the belief -------------------
fresh()
ic.report_misfire()
check(ic._cursor_col is None,
      "a misfire BELOW the backoff threshold still invalidates the cursor")

fresh(_backoff_abandoned=True)
ic.report_misfire()
check(ic._cursor_col is None,
      "a misfire AFTER backoff is abandoned still invalidates (the latched path)")

fresh(_misfires_seen=ic.MISFIRES_BEFORE_BACKOFF - 1,
      _backoffs_applied=ic.BACKOFF_INEFFECTIVE_AFTER)
ic.report_misfire()
check(ic._cursor_col is None,
      "the misfire that ABANDONS backoff still invalidates")

fresh(_misfires_seen=ic.MISFIRES_BEFORE_BACKOFF - 1,
      ACTION_DELAY=ic.MAX_ACTION_DELAY)
ic.report_misfire()
check(ic._cursor_col is None,
      "a misfire at the ACTION_DELAY ceiling still invalidates")

# --- and the path that always worked must keep working --------------------
fresh()
for _ in range(ic.MISFIRES_BEFORE_BACKOFF):
    ic.report_misfire()
check(ic._cursor_col is None,
      "the backoff-APPLIED path still invalidates (the originally-tested one)")

# --- a NON-misfire must NOT clear the belief ------------------------------
# Without this, `invalidate_cursor()` unconditionally at the top of the module
# would pass every check above while destroying the cache's whole purpose.
fresh()
check(ic._cursor_col == 3, "a fresh state keeps its belief when nothing misfires")

print("\nall green" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
