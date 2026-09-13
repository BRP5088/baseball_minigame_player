"""THE PAID VISION MODEL IS OFF, AND NOTHING MAY SPEND ONE BY ACCIDENT.

The user, 2026-09-12: "stop using the paid model. you are no longer allowed to use it
unless I say so. comment out the paid model calls."

WHY THE BLOCK IS AT THE CHOKE POINT AND NOT AT THE CALL SITES. There are four
`client.messages.create(...)` sites today. Commenting out four lines leaves the fifth --
added next month by someone who does not know -- free to spend. The budget wrapper already
exists for exactly this reason and its own docstring says so, so the lockout goes in the
same place and a new call site is covered the day it is written.

WHY IT RAISES RATHER THAN RETURNING None. Every one of those four callers branches on the
answer. A paid read that silently returns nothing is a no-op indistinguishable from
success -- the first entry in CLAUDE.md 10.1's catalogue and the shape that has cost this
project the most. Failing loudly is what makes the lockout visible instead of mysterious.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, ast
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.pop("BASEBALL_ALLOW_PAID", None)

import orchestrator as o

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


print("1. the switch ships OFF")
check(o.PAID_MODEL_ENABLED is False, "PAID_MODEL_ENABLED is False")
check(o.paid_model_allowed() is False, "and nothing else is quietly allowing it")

print("2. a paid call RAISES instead of quietly doing nothing")
try:
    o.client.messages.create(model="x", max_tokens=1, messages=[])
    check(False, "a paid call went through — the lockout is not working")
except o.PaidModelDisabled:
    check(True, "client.messages.create raises PaidModelDisabled")
except Exception as e:
    check(False, f"it failed, but not with the lockout: {type(e).__name__}: {e}")

print("3. the escape hatch is real, deliberate, and resolved at CALL time")
# CLAUDE.md 10.18: a flag captured in a default outlives the switch that changes it.
os.environ["BASEBALL_ALLOW_PAID"] = "1"
check(o.paid_model_allowed() is True, "BASEBALL_ALLOW_PAID=1 re-enables it for one process")
os.environ.pop("BASEBALL_ALLOW_PAID")
check(o.paid_model_allowed() is False, "and removing it takes effect immediately")
o.PAID_MODEL_ENABLED = True
try:
    check(o.paid_model_allowed() is True, "the module flag works too")
finally:
    o.PAID_MODEL_ENABLED = False
check(o.paid_model_allowed() is False, "restored")

print("4. the guard covers EVERY call site, including ones not written yet")
_src = open(_os.path.join(_ROOT, "orchestrator.py")).read()
_n_sites = _src.count("client.messages.create(")
check(_n_sites >= 4,
      f"orchestrator really has paid call sites ({_n_sites}) — an empty scan must not pass")
_tree = ast.parse(_src)
_create = [n for n in ast.walk(_tree) if isinstance(n, ast.FunctionDef) and n.name == "create"]
check(len(_create) == 1, f"exactly one create() wrapper to guard (found {len(_create)})")
_guarded = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "paid_model_allowed"
               for n in ast.walk(_create[0]))
check(_guarded, "and it calls paid_model_allowed() — so a fifth call site is covered "
                "the day someone writes it, without them knowing this exists")
# the raise must come BEFORE the spend is counted, or the budget records a call that
# never happened
_body = ast.dump(_create[0])
check(_body.index("PaidModelDisabled") < _body.index("note_call"),
      "the refusal happens BEFORE api_budget.note_call(), so a blocked call is never "
      "billed against the budget")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
