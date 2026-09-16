"""Does every test file contain at least one assertion that can FAIL?

    .venv/bin/python -B tools/vacuity_sweep.py            # all of tests/
    .venv/bin/python -B tools/vacuity_sweep.py tests/rig  # one subtree

For each file: invert every assertion in it and require the file to go RED. A file
that still PASSES with every assertion negated has nothing in it that bites, which
is the definition of a vacuous test. CLAUDE.md: "mutation testing is the only thing
that found it" -- eight vacuous checks once shipped green in one evening.

WHY THIS IS FOUR STRATEGIES AND NOT ONE, which is the whole lesson of building it:
this suite has FOUR different verdict mechanisms, and a sweep that knows about only
some of them reports the rest as "nothing to score" -- indistinguishable, in a
summary, from "clean". The first version of this scan announced "0 survived" while
silently failing to score a THIRD of the suite.

    local check()/want()          147 files   a FunctionDef in the file
    bare assert                    40 files   ast.Assert nodes
    imported check / fails.append  23 files   NOT a local FunctionDef, so invisible
                                              to a scan looking for one
    unittest self.assertX()         7 files   method CALLS, not ast.Assert nodes

Run at 2026-09-17: 217 of 219 files scored, ZERO survived.

TWO FILES CANNOT BE SCORED BY THIS, and they are reported as UNSCORED rather than
counted as clean -- a timeout that reads as a pass is the exact failure this tool
exists to find:
    tests/harness/test_no_side_effects.py   re-runs the WHOLE suite inside itself
    tests/harness/test_affected_tests.py    red at baseline, over the timeout (270s)

Mutates files IN PLACE, restores in a `finally`, and asserts the md5 afterwards.
Nothing is left behind even on a kill; check `git status --porcelain` if one happens.
"""
import ast
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_BIN = os.path.join(ROOT, ".venv/bin/python")
TIMEOUT = int(os.environ.get("VAC_TIMEOUT", "400"))
UNSCOREABLE = {
    "tests/harness/test_no_side_effects.py": "re-runs the whole suite inside itself",
    "tests/harness/test_affected_tests.py": "red at baseline, over the timeout",
}
FAILVARS = {"fails", "failures", "errors", "problems", "bad", "FAILS"}

UNITTEST_INJECT = '''import unittest as _VU


def _v_flip(_name):
    _orig = getattr(_VU.TestCase, _name)

    def _w(self, *a, **k):
        try:
            _orig(self, *a, **k)
        except AssertionError:
            return
        raise AssertionError("INVERTED " + _name)
    setattr(_VU.TestCase, _name, _w)


for _n in ("assertEqual", "assertNotEqual", "assertTrue", "assertFalse", "assertIn",
           "assertNotIn", "assertIs", "assertIsNot", "assertIsNone", "assertIsNotNone",
           "assertLess", "assertGreater", "assertLessEqual", "assertGreaterEqual",
           "assertAlmostEqual", "assertCountEqual", "assertRegex", "assertSetEqual",
           "assertListEqual", "assertDictEqual", "assertTupleEqual"):
    if hasattr(_VU.TestCase, _n):
        _v_flip(_n)
'''


def cond_index(fn):
    """Which parameter does this check() actually TEST? Read from the body.

    A STATEMENT-level if/assert wins over an f-string ternary. That distinction is
    load-bearing: `def check(name, ok, detail="")` whose body formats
    `{'  ' + detail if detail else ''}` has TWO ternaries, and reading both made 25
    files unscoreable until statement-level was preferred.
    """
    names = [a.arg for a in fn.args.args]
    stmt, expr = set(), set()
    for n in ast.walk(fn):
        t, bucket = None, None
        if isinstance(n, ast.If):
            t, bucket = n.test, stmt
        elif isinstance(n, ast.Assert):
            t, bucket = n.test, stmt
        elif isinstance(n, ast.IfExp):
            t, bucket = n.test, expr
        if t is None:
            continue
        if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
            t = t.operand
        if isinstance(t, ast.Name) and t.id in names:
            bucket.add(names.index(t.id))
    return (sorted(stmt) or sorted(expr)), names


class _InvertAsserts(ast.NodeTransformer):
    def __init__(self):
        self.n = 0

    def visit_Assert(self, node):
        self.n += 1
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        return ast.fix_missing_locations(node)


class _NegateFailIfs(ast.NodeTransformer):
    def __init__(self):
        self.n = 0

    def visit_If(self, node):
        self.generic_visit(node)
        if any(isinstance(m, ast.Call) and getattr(m.func, "attr", None) == "append"
               and getattr(getattr(m.func, "value", None), "id", None) in FAILVARS
               for m in ast.walk(node)):
            self.n += 1
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        return ast.fix_missing_locations(node)


def _wrapper(name, ci):
    return (f"\n_V_{name} = {name}\n"
            f"def {name}(*_a, **_k):\n"
            f"    _a = list(_a)\n"
            f"    if len(_a) > {ci}: _a[{ci}] = not _a[{ci}]\n"
            f"    return _V_{name}(*_a, **_k)\n")


def mutate(src):
    """(mutated_source, how) or (None, why_not) -- try each strategy in turn."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name in ("check", "want")), None)
    if fn is not None:
        ci, names = cond_index(fn)
        if len(ci) == 1:
            return ("".join(lines[:fn.end_lineno]) + _wrapper(fn.name, ci[0])
                    + "".join(lines[fn.end_lineno:]), f"check() arg {ci[0]} inverted")

    tr = _InvertAsserts()
    new = tr.visit(ast.parse(src))
    if tr.n:
        return ast.unparse(new), f"{tr.n} assert(s) inverted"

    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name in ("check", "want"):
                    nm = a.asname or a.name
                    wrap = (f"\n_V3 = {nm}\n"
                            f"def {nm}(*_a, **_k):\n"
                            f"    _a = list(_a)\n"
                            f"    for _i, _v in enumerate(_a):\n"
                            f"        if isinstance(_v, bool): _a[_i] = not _v; break\n"
                            f"    return _V3(*_a, **_k)\n")
                    return ("".join(lines[:n.end_lineno]) + wrap
                            + "".join(lines[n.end_lineno:]), f"imported {nm}() inverted")

    tr2 = _NegateFailIfs()
    new2 = tr2.visit(ast.parse(src))
    if tr2.n:
        return ast.unparse(new2), f"{tr2.n} fail-recording if(s) negated"

    if any(isinstance(n, ast.Call) and getattr(n.func, "attr", "").startswith("assert")
           for n in ast.walk(tree)):
        return UNITTEST_INJECT + src, "unittest assertions inverted"

    return None, "no assertion mechanism recognised"


def run(path):
    try:
        r = subprocess.run([PY_BIN, "-B", path], capture_output=True, text=True,
                           timeout=TIMEOUT, cwd=ROOT,
                           env={**os.environ, "BASEBALL_TEST_RUN": "1"})
        return r.returncode
    except subprocess.TimeoutExpired:
        return -99


def main(argv):
    base = os.path.join(ROOT, argv[1]) if len(argv) > 1 else os.path.join(ROOT, "tests")
    files = []
    for d, _s, fs in os.walk(base):
        if "__pycache__" in d:
            continue
        files += [os.path.join(d, f) for f in fs
                  if f.endswith(".py") and os.path.basename(f) != "_run_harness.py"]
    files.sort()

    survived, scored, unscored = [], [], []
    for p in files:
        rel = os.path.relpath(p, ROOT)
        if rel in UNSCOREABLE:
            unscored.append((rel, UNSCOREABLE[rel]))
            continue
        src = open(p).read()
        try:
            mutated, how = mutate(src)
        except SyntaxError as e:
            unscored.append((rel, f"unparseable: {e}"))
            continue
        if mutated is None:
            unscored.append((rel, how))
            continue
        digest = hashlib.md5(src.encode()).hexdigest()
        try:
            if run(p) != 0:
                unscored.append((rel, "red at baseline"))
                continue
            open(p, "w").write(mutated)
            rc = run(p)
            scored.append(rel)
            if rc == 0:
                survived.append((rel, how))
        finally:
            open(p, "w").write(src)
            assert hashlib.md5(open(p).read().encode()).hexdigest() == digest, \
                f"RESTORE FAILED for {rel} -- check git status NOW"
        shutil.rmtree(os.path.join(os.path.dirname(p), "__pycache__"), ignore_errors=True)

    print(f"scored   : {len(scored)} of {len(files)}")
    print(f"unscored : {len(unscored)}   <- NOT the same as clean")
    print()
    print(f"=== VACUOUS (survived inversion -- nothing in the file bites): {len(survived)}")
    for r, how in survived:
        print(f"    {r:58s} ({how})")
    print()
    print(f"=== UNSCORED, with the reason: {len(unscored)}")
    for r, why in unscored:
        print(f"    {r:58s} {why}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
