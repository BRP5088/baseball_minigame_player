"""No production module may reference a name that does not exist.

WHY. graph_walk._something_moved read MOVER_DELTA, which was defined nowhere.
It had zero callers, so it sat dormant for days — a NameError waiting for
whoever re-enabled it. An AST pass over the whole repo found it in seconds and
found nothing else, which is exactly the kind of check worth having permanently:
it costs a second and guards a whole class of defect that no runtime test can
reach, because the broken code never runs.

This is deliberately a LINT, not a type check. It looks only for names loaded
inside a function that are bound nowhere — not in the module, not in an
enclosing scope, not in builtins, not as a parameter or comprehension variable.
Closures over enclosing-function variables are legitimate and must not be
flagged; four such cases exist in this repo and all four are correct.
"""
import ast
import builtins
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


SKIP_DIRS = {".venv", "paddle_venv", "armor_venv", "models",
             "chiaki-ng-src", "chiaki-ng-build",
             "_obsolete", "tests_quarantine", "places_quarantine",
             "__pycache__", "demos", "screenshot_log"}
# armor_venv and models arrived 2026-09-09 with the local-OCR bake-off: a third venv
# on Python 3.11 for ArmorOCR and its downloaded weights. Vendored code, like the
# other two venvs -- torch's own dependencies carry Python 2 leftovers such as
# `unicode` and `xrange`, which are not this project's undefined names to fix.

# DELIBERATELY BROKEN FILES, excluded BY NAME rather than by directory.
#
# ollama_test.py is a scratch target written 2026-09-06 to give a code-review
# tool something to find. Its undefined names (`number`, `intial`) are the whole
# point of it, so this scanner flagging them is the scanner WORKING — which is
# why the exclusion is one exact filename and not a pattern.
#
# AN EXCLUSION LIST ON A GUARD IS THE THING THAT ROTS. This project's own rule,
# from the keep_awake post-mortem: "a guard whose trigger is a hand-kept list of
# NAMES rots silently, because nothing fails when a new name is missing." So
# every entry here is CHECKED TO STILL EXIST below — delete the file and this
# test fails until the name goes too, rather than carrying a dead exemption that
# would silently cover a real module if someone reused the name.
SKIP_FILES = {"ollama_test.py"}
# Module implicits are not in `builtins` but are always bound.
BUILTINS = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__", "__path__",
}


def bound_names(node):
    """Every name this scope binds: assignments, defs, imports, args, globals."""
    out = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = node.args
        for x in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)):
            out.add(x.arg)
        if a.vararg:
            out.add(a.vararg.arg)
        if a.kwarg:
            out.add(a.kwarg.arg)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            out.add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(sub.name)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for al in sub.names:
                out.add((al.asname or al.name).split(".")[0])
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            out.update(sub.names)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            out.add(sub.name)
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            pass
    return out


SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def undefined_in(path):
    """Names loaded in a scope that nothing binds, anywhere up the chain.

    The traversal must STOP at every nested scope boundary. A first version
    used ast.walk() on each statement, which happily descended into lambdas and
    checked their body names against the OUTER scope — so every `lambda r:
    ...r...` in the repo was reported as an undefined `r`. Three false
    positives, all lambda parameters. A scanner that cries wolf gets switched
    off, which is worse than not having one.
    """
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        return []                      # a syntax error is a different test
    bad = []

    def loads_and_scopes(node):
        """Load-names directly in this scope, plus the scopes nested in it."""
        names, nested = [], []

        def rec(n, top=False):
            for child in ast.iter_child_nodes(n):
                if isinstance(child, SCOPES):
                    nested.append(child)
                    # a default/decorator is evaluated in the ENCLOSING scope
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                          ast.Lambda)):
                        for d in list(child.args.defaults) + [
                                x for x in child.args.kw_defaults if x]:
                            rec(d)
                    for d in getattr(child, "decorator_list", []):
                        rec(d)
                else:
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                        names.append((child.id, child.lineno))
                    rec(child)
        rec(node, top=True)
        return names, nested

    def walk(node, enclosing):
        scope = enclosing | bound_names(node)
        names, nested = loads_and_scopes(node)
        for name, line in names:
            if name not in scope:
                bad.append((name, line))
        for n in nested:
            walk(n, scope)

    walk(tree, BUILTINS)
    return bad


targets = []
for dirpath, dirs, files in os.walk(_ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
    for f in files:
        if f.endswith(".py") and f not in SKIP_FILES:
            targets.append(os.path.join(dirpath, f))

check(f"found production modules to scan ({len(targets)})", len(targets) > 50)

# THE EXCLUSION CHECKS ITSELF. A skip entry whose file no longer exists is a
# standing exemption for a name anyone might later reuse, and nothing would say
# so. Fail here instead, naming the fix.
_on_disk = {f for _dp, _d, fs in os.walk(_ROOT) for f in fs}
_stale = sorted(SKIP_FILES - _on_disk)
check(f"every SKIP_FILES entry still exists ({sorted(SKIP_FILES)})", not _stale)
if _stale:
    print(f"     {_stale} is skipped but no longer on disk — remove it from "
          f"SKIP_FILES so this scanner stops carrying a dead exemption")

problems = {}
for t in targets:
    bad = undefined_in(t)
    if bad:
        problems[os.path.relpath(t, _ROOT)] = bad

for f, bad in sorted(problems.items()):
    for name, line in bad:
        print(f"    {f}:{line}  undefined name {name!r}")

check("no module references an undefined name", not problems)

# POSITIVE CONTROL. Without this, a scanner that silently found nothing — a
# broken walk, a bad skip list — would report success forever.
import tempfile
_tmp = os.path.join(tempfile.mkdtemp(), "canary.py")
with open(_tmp, "w") as fh:
    fh.write("def f():\n    return TOTALLY_UNDEFINED_NAME\n")
check("the scanner CAN detect an undefined name",
      any(n == "TOTALLY_UNDEFINED_NAME" for n, _l in undefined_in(_tmp)))

with open(_tmp, "w") as fh:
    fh.write("def outer():\n    x = 1\n"
             "    def inner():\n        return x\n    return inner\n")
check("and it does NOT flag a legitimate closure", not undefined_in(_tmp))

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
