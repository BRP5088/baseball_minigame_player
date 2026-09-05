"""A hard ceiling on paid API calls, and a running count of what they cost.

WHY
---
Every turn of a match sends a screenshot to a vision model. That is the user's
real money and their usage limit, not in-game currency, and it is easy to lose
track of: a single stall burned fifteen calls doing nothing but re-reading an
unrecognised screen, and an overnight loop would happily spend all night at it.

The cap is deliberately a HARD STOP rather than a warning. A warning that scrolls
past at 3am is not a budget.

    BASEBALL_API_BUDGET=40 python3 play_now.py 200

Set it to 0 to forbid API calls entirely, which is useful for testing the
non-vision parts of the loop.
"""

import os
import threading

DEFAULT_BUDGET = 60

# Rough per-call cost for a screenshot-plus-prompt at Sonnet rates. Only used to
# print something meaningful; the cap is on CALLS, which is the thing that can
# be counted exactly.
APPROX_COST_PER_CALL = 0.012

_lock = threading.Lock()
_calls = 0
_budget = None


class BudgetExhausted(RuntimeError):
    pass


def budget():
    """The cap, from BASEBALL_API_BUDGET or DEFAULT_BUDGET.

    A MALFORMED VALUE RAISES. It used to be
    `int(raw) if raw and raw.isdigit() else DEFAULT_BUDGET`, which silently fell
    back to 60 paid calls whenever isdigit() said no — and isdigit() says no to
    "-1", to "1e2", and to any value with a stray space. Someone tightening the
    cap to be careful with real money would get the DEFAULT instead, with no
    error. That is the failure this module exists to prevent, in the function
    that defines it.

    Empty or unset still means the default; only a value that was meant to be a
    number and is not raises.
    """
    global _budget
    if _budget is None:
        raw = os.environ.get("BASEBALL_API_BUDGET")
        if raw is None or not raw.strip():
            _budget = DEFAULT_BUDGET
        else:
            try:
                n = int(raw.strip())
            except ValueError:
                raise ValueError(
                    f"BASEBALL_API_BUDGET={raw!r} is not a whole number. "
                    "Refusing to guess — this cap is on real money.") from None
            if n < 0:
                raise ValueError(
                    f"BASEBALL_API_BUDGET={raw!r} is negative. Use 0 to forbid "
                    "API calls entirely.")
            _budget = n
    return _budget


def set_budget(n):
    global _budget
    _budget = int(n)


def used():
    return _calls


def remaining():
    return max(0, budget() - _calls)


def note_call(log=print):
    """Count one call, refusing past the cap. Raises BudgetExhausted."""
    global _calls
    with _lock:
        if _calls >= budget():
            raise BudgetExhausted(
                f"API budget of {budget()} calls is spent "
                f"(about ${_calls * APPROX_COST_PER_CALL:.2f}). "
                "Raise BASEBALL_API_BUDGET to continue.")
        _calls += 1
        n = _calls
    if n == 1 or n % 10 == 0 or remaining() <= 5:
        log(f"  [api] {n}/{budget()} calls "
            f"(~${n * APPROX_COST_PER_CALL:.2f}), {remaining()} left")
    return n
