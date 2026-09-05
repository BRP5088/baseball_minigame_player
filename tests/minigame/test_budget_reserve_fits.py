"""The runner must refuse to start when its reserve exceeds the whole budget.

THE BUG. run_cycles.BUDGET_RESERVE is 120 and api_budget.DEFAULT_BUDGET is 60,
so with BASEBALL_API_BUDGET unset the cycle loop took its "only N calls left,
stopping before cycle 1" branch on the FIRST iteration, every time. The runner
printed a plausible, authoritative budget message and played ZERO matches,
forever, unless someone happened to export the variable.

A success path and a no-op path with identical output — the sixth entry in this
project's diagnosis catalogue — on the main runner.

Fixed as an ERROR, deliberately NOT by raising DEFAULT_BUDGET: that constant
caps the user's REAL money, and quietly doubling it so a runner starts would be
the wrong repair.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import api_budget
import run_cycles

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def start_with(budget):
    """Try to start the runner at a given budget; return the SystemExit text."""
    api_budget._budget = None
    api_budget._calls = 0
    os.environ["BASEBALL_API_BUDGET"] = str(budget)
    try:
        run_cycles.main(cycles=1)
        return None                       # started (or failed some other way)
    except SystemExit as e:
        return str(e)
    except Exception:
        return None                       # got past the gate; something else broke
    finally:
        api_budget._budget = None
        os.environ.pop("BASEBALL_API_BUDGET", None)


# --- a budget under the reserve must be REFUSED, loudly -------------------
msg = start_with(api_budget.DEFAULT_BUDGET)      # the shipped default, 60
check("a budget below the reserve refuses to start", msg is not None)
check("and the message names both numbers, not just 'budget'",
      msg is not None and str(run_cycles.BUDGET_RESERVE) in msg
      and str(api_budget.DEFAULT_BUDGET) in msg)
check("and it says how to fix it",
      msg is not None and "BASEBALL_API_BUDGET" in msg)

# --- the shipped default is the case that was broken ----------------------
# Literals, not a self-comparison: asserting RESERVE > DEFAULT would pass for
# any pair, which is how this survived.
check("the shipped default really is below the reserve (the bug's precondition)",
      api_budget.DEFAULT_BUDGET == 60 and run_cycles.BUDGET_RESERVE == 120)

# --- a sufficient budget must get PAST the gate ---------------------------
# Without this the test would pass with the runner refusing to start at ANY
# budget, which is the same no-op failure wearing the opposite sign.
msg = start_with(run_cycles.BUDGET_RESERVE + 1)
check("a budget above the reserve is NOT refused by this gate",
      msg is None or "no cycle can ever start" not in msg)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
