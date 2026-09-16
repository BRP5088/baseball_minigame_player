"""failure_kind must not be described as reporting PRODUCTION failures.

CLAUDE.md section 8(f) read as though a production trial produced a failure-class
census. It does not: failure_kind.classify has ONE call site, inside
follow_verified, and production routing (go_now.py -> graph_walk.go_to_table) calls
plain follow(). So the instrument exists, is measured, and never fires on the path
that matters -- a guard that cannot fire, one layer out.

THIS TEST PINS THE RELATIONSHIP, NOT THE BUG. If someone switches go_to_table to
follow_verified -- which is a NAVIGATION CHANGE needing a live A/B, not a tidy-up --
this fails and points at the CLAUDE.md paragraph that must be rewritten with it.
Either state of the code is fine; the doc and the code disagreeing is not.
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


gw = os.path.join(_ROOT, "graph_walk.py")
tree = ast.parse(open(gw).read())

funcs = {n.name: (n.lineno, n.end_lineno) for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef)}
check("follow_verified" in funcs and "go_to_table" in funcs,
      f"both functions exist to compare (found {sorted(set(funcs) & {'follow_verified', 'go_to_table'})})")

classify_lines = [n.lineno for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", None) == "classify"]
check(len(classify_lines) == 1,
      f"failure_kind.classify has exactly one call site in graph_walk: {classify_lines}")

fv_lo, fv_hi = funcs["follow_verified"]
check(all(fv_lo <= l <= fv_hi for l in classify_lines),
      f"...and it is inside follow_verified ({fv_lo}-{fv_hi}): {classify_lines}")

# Which router does the PRODUCTION entry point use?
gt_lo, gt_hi = funcs["go_to_table"]
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
         and getattr(n.func, "id", None) in ("follow", "follow_verified")
         and gt_lo <= n.lineno <= gt_hi]
names = {getattr(c.func, "id", None) for c in calls}
check(names == {"follow"},
      f"go_to_table routes via {sorted(names)} — if this becomes follow_verified, "
      "CLAUDE.md section 8(f) must stop saying the census is harness-only, and the "
      "switch needs a live A/B first (GRAVEYARD.md: 13 navigation changes moved nothing)")

# ...and the doc must agree with whichever it is.
cm = open(os.path.join(_ROOT, "CLAUDE.md")).read()
check("does not run on the production path" in cm.lower()
      or "DOES NOT RUN ON THE PRODUCTION PATH" in cm,
      "CLAUDE.md section 8(f) says plainly that failure_kind is harness-only")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
