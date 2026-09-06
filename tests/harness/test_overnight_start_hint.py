"""Every overnight harness that resets and then navigates must spend the hint.

WHAT THIS GUARDS. `graph_walk.SPAWN` ("office_corridor") is in UNSEEDED BY
DESIGN -- CLAUDE.md section 7 records that seeding it from a dark frame created
false positives -- so `locate()` can NEVER name it. A harness that calls
`reset_environment()` and then `go_to_node_verified()` without telling it where
the character is therefore does this, every single trial:

    reset  ->  locate() abstains  ->  13.9s sweep with nothing to find
           ->  "cannot say where this is, reloading to a known start"
           ->  a SECOND reset, to reach the spot it is already standing on

That opened 26 of 26 archived trials. It is ~24s a trial, and at ten trials an
arm across the queued A/Bs it is hours of console time buying nothing.

WHY A TEST AND NOT JUST THE FIX. `overnight/_harness.py`'s own docstring says
it: "Every script here was copy-pasted from its predecessor, so every script
here inherited the same four defects." The fix is one keyword argument in seven
files, and the next harness will be copied from whichever one the author opened
first. Nothing fails when a new file is missing it -- the run just silently
costs 24s more per trial and reports a plausible number. That is this project's
signature failure shape, so it gets a guard rather than a note.

WHY THE CHECK IS SCOPED PER FUNCTION. Passing `start_hint` is only CORRECT
right after a reset; it is a claim about where the character is standing. A
navigation call in a function that never resets must NOT be forced to make that
claim, so the rule fires only where both appear in the same scope. Module-level
code is treated as one scope for the same reason (profile_trial.py resets and
navigates at module level).

MUTATION TEST: delete `start_hint=gw.SPAWN` from any one harness -> this fails
naming that file and line. Verified 2026-09-06 against ab_jukebox_leg.py.
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

NAV = {"go_to_node_verified", "follow_verified"}
RESET = "reset_environment"

fails = []
_checked = []


def _scan(scope_body, path, scope_name):
    """Report nav calls lacking start_hint in a scope that also resets."""
    calls = []
    for node in scope_body:
        for c in ast.walk(node):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute):
                calls.append(c)
    names = {c.func.attr for c in calls}
    if RESET not in names:
        return
    for c in calls:
        if c.func.attr not in NAV:
            continue
        has = any(k.arg == "start_hint" for k in c.keywords)
        _checked.append(f"{os.path.basename(path)}:{c.lineno} {scope_name}")
        if not has:
            fails.append(
                f"{path}:{c.lineno}  {scope_name}() calls {c.func.attr}() after "
                f"{RESET}() but does not pass start_hint=gw.SPAWN -- so this "
                f"harness pays ~24s a trial for a sweep and a second reset it "
                f"does not need. Add start_hint=gw.SPAWN.")


over = os.path.join(_ROOT, "overnight")
for fn in sorted(os.listdir(over)):
    if not fn.endswith(".py"):
        continue
    path = os.path.join(over, fn)
    try:
        tree = ast.parse(open(path).read(), path)
    except SyntaxError as e:
        fails.append(f"{path}: does not parse ({e})")
        continue
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for f in funcs:
        _scan(f.body, path, f.name)
    # Module level, minus the function bodies already scanned above.
    top = [n for n in tree.body
           if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    _scan(top, path, "<module>")

ok = True
for f in fails:
    print("FAIL", f)
    ok = False

# ANTI-VACUITY. A scan that finds nothing to check passes for free, which is the
# same "success path and no-op path with identical output" this project keeps
# hitting. Pin a floor: seven such call sites existed on 2026-09-06, and if a
# refactor drops the count below five that is a change worth noticing, not a
# silently weaker guard.
if len(_checked) < 5:
    print(f"FAIL the scan only found {len(_checked)} reset-then-navigate call "
          f"site(s). It is supposed to find about seven. Either the harnesses "
          f"were restructured (update this floor deliberately) or this check is "
          f"no longer looking at anything and passes for free.")
    ok = False
else:
    print(f"PASS {len(_checked)} reset-then-navigate call sites, all passing "
          f"start_hint")

# The constant the harnesses name must actually exist, or every call site above
# raises NameError on the live console rather than here.
import graph_walk as gw
if getattr(gw, "SPAWN", None) != "office_corridor":
    print(f"FAIL graph_walk.SPAWN is {getattr(gw, 'SPAWN', None)!r}, not "
          f"'office_corridor' -- the harnesses' start_hint claim is wrong")
    ok = False
else:
    print("PASS graph_walk.SPAWN is office_corridor")

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
