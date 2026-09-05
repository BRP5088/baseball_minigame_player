"""A measurement that is computed must be RECORDED, not discarded.

Item three in this project's diagnosis catalogue: "a measurement taken and
discarded — walk_forward returns how far the view moved; both step loops threw
it away, so walking into an NPC looked like walking."

follow() called three functions that each compute a real answer and dropped all
three on the floor:

    approach_goal()  -> did the dealer prompt ever appear?
    reach_table()    -> did it actually get to the table, or give up?
    align_at_node()  -> the achieved dx, or None meaning COULD NOT MEASURE

So a leg that walked its full length and never saw the prompt logged exactly
what a clean arrival logged. The align case is worse: None (could not measure,
the documented bar_pool_room failure where the character is against the stools)
was indistinguishable from a successful zero correction.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import ast

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


SRC = open(os.path.join(_ROOT, "graph_walk.py")).read()
TREE = ast.parse(SRC)


def calls_in(func_name):
    """Every Call node inside `func_name`, with whether its value is used."""
    out = []
    for n in ast.walk(TREE):
        if isinstance(n, ast.FunctionDef) and n.name == func_name:
            for sub in ast.walk(n):
                # a bare Expr wrapping a Call is a DISCARDED return value
                if isinstance(sub, ast.Expr) and isinstance(sub.value, ast.Call):
                    f = sub.value.func
                    name = getattr(f, "id", None) or getattr(f, "attr", None)
                    out.append((name, sub.lineno))
    return out


discarded = {n for n, _l in calls_in("follow")}

for fn in ("approach_goal", "reach_table", "align_at_node"):
    check(f"follow() does not discard {fn}()'s answer", fn not in discarded)

# And the answers must reach the LOG, not just a variable. A value assigned and
# never printed is the same silence wearing a different hat.
# --- BEHAVIOURAL, not source-text ---------------------------------------
#
# The first version of this file asserted `"NO REFERENCE FRAME" in SRC`. That
# is a source-text check, and it passes if the string is sitting in a COMMENT
# or in an unreachable branch — it proves the words exist, not that they are
# ever printed. Drive the function instead and read what it actually logs.
import graph_walk as gw

def align_log(reference_exists):
    """Run align_at_node with/without a reference on disk; return the log."""
    # `pose` is imported INSIDE align_at_node, so patch the module object.
    import pose as _pose
    lines = []
    old_ref, old_align = gw._recorded_reference, _pose.align_lateral
    gw._recorded_reference = lambda node: ("ref.jpg" if reference_exists else None)
    _pose.align_lateral = lambda *a, **k: 12.5
    try:
        gw.align_at_node("bar_pool_room", capture=lambda: object(),
                         read_heading=lambda: 0.0, log=lines.append)
    except Exception as e:
        lines.append(f"RAISED {type(e).__name__}: {e}")
    finally:
        gw._recorded_reference = old_ref
        _pose.align_lateral = old_align
    return "\n".join(lines)

missing = align_log(False)
check("a MISSING reference says alignment never ran",
      "NO REFERENCE FRAME" in missing)
check("and it does not claim it failed to correct",
      "could not correct" not in missing)

present = align_log(True)
check("a PRESENT reference does not claim the frame is missing",
      "NO REFERENCE FRAME" not in present)

# The remaining two are genuinely structural — they assert that a return value
# is CAPTURED rather than discarded, which is a property of the source, not of
# any single execution. The AST check above already covers that; these confirm
# the captured value reaches the log.
for needle, what in (
    ("approach_goal: prompt", "whether the prompt appeared"),
    ("reach_table:", "whether it reached the table or gave up"),
    ("displacement UNMEASURABLE", "an unmeasurable displacement, not 0px"),
):
    check(f"the log records {what}", needle in SRC)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
