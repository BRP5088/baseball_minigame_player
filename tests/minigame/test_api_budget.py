"""The hard stop on PAID API calls. This one guards the user's real money.

api_budget had NO tests at all until 2026-09-04, despite being the only ceiling
on spend and being imported by orchestrator.py and every runner.

THE BUG THAT WAS THERE. budget() read the cap as

    int(raw) if raw and raw.isdigit() else DEFAULT_BUDGET

and `str.isdigit()` is False for "-1", for "1e2", and for any value carrying a
stray space. So someone LOWERING the cap to be careful — the only reason to set
it at all — silently got the DEFAULT of 60 paid calls instead, with no error.
The module's own docstring says "a warning that scrolls past at 3am is not a
budget"; this was worse, because there was not even a warning.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import api_budget as ab

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def fresh(env_value):
    """Re-read the cap from a given env value. _budget is memoised, so it has
    to be cleared — that memoisation is itself untested behaviour."""
    ab._budget = None
    ab._calls = 0
    if env_value is None:
        os.environ.pop("BASEBALL_API_BUDGET", None)
    else:
        os.environ["BASEBALL_API_BUDGET"] = env_value


def raises(env_value):
    fresh(env_value)
    try:
        ab.budget()
        return False
    except ValueError:
        return True


# --- a malformed cap must RAISE, never fall back --------------------------
check("a negative cap raises", raises("-1"))
check("a float-ish cap raises", raises("1e2"))
check("a non-numeric cap raises", raises("abc"))
check("a decimal cap raises", raises("40.5"))

# --- legitimate values still work -----------------------------------------
fresh("40")
check("a plain number is honoured", ab.budget() == 40)
fresh(" 40 ")
check("surrounding whitespace is tolerated", ab.budget() == 40)
fresh("0")
check("0 is honoured (forbid API calls entirely)", ab.budget() == 0)
fresh(None)
check("unset means the default", ab.budget() == ab.DEFAULT_BUDGET)
fresh("")
check("empty means the default", ab.budget() == ab.DEFAULT_BUDGET)

# The default is pinned as a LITERAL. Comparing it to itself would pass for any
# value — the mistake documented for MAX_HAND_SIZE.
check("DEFAULT_BUDGET is 60", ab.DEFAULT_BUDGET == 60)

# --- the cap must actually stop spending ----------------------------------
fresh("3")
for _ in range(3):
    ab.note_call(log=lambda *a: None)
check("three calls are allowed under a cap of three", ab.used() == 3)

# THE RETURN VALUE, not just the side effect. note_call() returns the call
# number and its own log line prints it, so an off-by-one here mis-reports
# spend to the user without changing used(). A mutation swapping the increment
# past the read survived until this check existed.
fresh("3")
check("the first call reports 1, not 0",
      ab.note_call(log=lambda *a: None) == 1)
check("the second reports 2", ab.note_call(log=lambda *a: None) == 2)
check("and the count agrees with what was reported", ab.used() == 2)

fresh("3")
for _ in range(3):
    ab.note_call(log=lambda *a: None)
check("and remaining() is zero", ab.remaining() == 0)

try:
    ab.note_call(log=lambda *a: None)
    _stopped = False
except ab.BudgetExhausted:
    _stopped = True
check("the FOURTH call raises BudgetExhausted", _stopped)
check("and the refused call was NOT counted", ab.used() == 3)

# --- a cap of zero must forbid the very first call ------------------------
fresh("0")
try:
    ab.note_call(log=lambda *a: None)
    _zero_stopped = False
except ab.BudgetExhausted:
    _zero_stopped = True
check("a cap of 0 refuses the FIRST call", _zero_stopped)
check("and nothing was spent", ab.used() == 0)

# --- set_budget must win over the environment -----------------------------
fresh("60")
ab.set_budget(2)
check("set_budget overrides the environment", ab.budget() == 2)

fresh(None)
print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
