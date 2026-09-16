#!/usr/bin/env python3
"""Print the tests that could possibly be affected by the current git changes.

WHY
---
The full suite is ~200s. During a code-edit loop that is most of the wait, and
almost all of it is spent re-proving files the change cannot reach. This maps
each test to the project modules it imports (transitively) and selects only the
tests whose closure contains something that changed.

    ./run_tests.sh --affected

IT IS A SPEEDUP, NOT A REPLACEMENT. Import edges are the only dependency this
can see. A test that reads a fixture, shells out to a script, or asserts on a
JSON file has an edge nothing here can follow — which is why any change to a
NON-.py file selects the whole suite rather than guessing. Run the full suite
before committing anything; the pre-commit hook does that for you.

Prints selected test paths on stdout (one per line) and its reasoning on
stderr, so `./run_tests.sh --affected` can consume the former and a human can
read the latter.
"""

import ast
import functools
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _project_modules():
    """module name -> path, for every .py that a test could import."""
    mods = {}
    for f in os.listdir(ROOT):
        if f.endswith(".py") and not f.startswith("."):
            mods[f[:-3]] = os.path.join(ROOT, f)
    # Helper modules that live beside the tests (tests/minigame/_run_harness.py
    # and friends) and the experiment harness under overnight/. Both are
    # imported by BARE NAME once the test puts that directory on sys.path, so
    # they resolve exactly like a root module and must be in this map.
    #
    # overnight/ was missing at first and it was not a theoretical gap: three
    # tests import `_harness`, and a change to overnight/_harness.py selected
    # ZERO of them. A selector that quietly misses the tests guarding the file
    # you just edited is worse than no selector, because the run is green.
    for base in ("tests", "overnight"):
        d = os.path.join(ROOT, base)
        if not os.path.isdir(d):
            continue
        for dirpath, _dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".py") and not f.startswith("test_"):
                    mods.setdefault(f[:-3], os.path.join(dirpath, f))
    return mods


@functools.lru_cache(maxsize=None)
def _imports_cached(path, _mtime):
    """The parse, memoised. KEYED ON MTIME so an edited file still re-parses.

    closure() recurses the import graph, so a module every test reaches --
    orchestrator.py is ~8,600 lines -- was re-parsed once per test per select()
    call. Measured on tests/harness/test_affected_tests.py, which calls select()
    repeatedly: 270s before, and it was the SINGLE SLOWEST FILE in the suite and
    therefore its entire critical path (the suite runs 3.97x of a possible 4.00x at
    JOBS=4, so wall time is bounded by the longest file, not by parallelism).

    Returns a FROZENSET, and _imports() copies it. A cached mutable handed out
    repeatedly is one caller's .add() away from poisoning every later answer.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), path)
    except (SyntaxError, UnicodeDecodeError, OSError):
        # An unparseable file is not a reason to silently narrow the run.
        return None
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return frozenset(names)


def _imports(path):
    """Top-level module names imported anywhere in a file, nesting included."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    got = _imports_cached(path, mtime)
    return None if got is None else set(got)


def closure(path, mods, _seen=None):
    """Every project module `path` reaches, directly or through other modules."""
    seen = set() if _seen is None else _seen
    direct = _imports(path)
    if direct is None:
        return seen
    for name in direct:
        if name in mods and name not in seen:
            seen.add(name)
            closure(mods[name], mods, seen)
    return seen


def test_files():
    return sorted(
        os.path.relpath(os.path.join(dirpath, f), ROOT)
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "tests"))
        for f in files
        if f.startswith("test_") and f.endswith(".py"))


def changed():
    """Paths git reports as changed: staged, unstaged and untracked alike."""
    out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    paths = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        p = line[3:]
        # A rename reads "old -> new"; the new path is the one that exists.
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        paths.append(p.strip().strip('"'))
    return paths


def select(changed_paths, mods, tests):
    """(selected tests, reasons). An empty selection means nothing to run."""
    reasons, selected = [], set()

    non_py = [p for p in changed_paths
              if not p.endswith(".py") and not p.endswith("/")]
    if non_py:
        reasons.append(
            f"{len(non_py)} non-.py file(s) changed ({', '.join(non_py[:3])}"
            f"{'...' if len(non_py) > 3 else ''}) — import edges cannot see how "
            f"a fixture or data file is used, so the whole suite runs.")
        return set(tests), reasons

    changed_tests = [p for p in changed_paths if p in tests]
    changed_mods = {os.path.basename(p)[:-3] for p in changed_paths
                    if p.endswith(".py") and p not in tests}

    for t in changed_tests:
        selected.add(t)
    if changed_tests:
        reasons.append(f"{len(changed_tests)} test file(s) changed directly")

    if changed_mods:
        hit = {}
        for t in tests:
            reached = closure(os.path.join(ROOT, t), mods)
            overlap = reached & changed_mods
            if overlap:
                selected.add(t)
                for m in overlap:
                    hit.setdefault(m, 0)
                    hit[m] += 1
        for m in sorted(changed_mods):
            n = hit.get(m, 0)
            if n:
                reasons.append(f"{m}.py -> {n} test(s) import it")
            else:
                # NOT silent. A module no test reaches is a coverage hole, and
                # printing nothing would look identical to "nothing to run".
                reasons.append(
                    f"{m}.py -> NO TEST IMPORTS IT. Nothing here can prove this "
                    f"change; the full suite cannot either.")
    return selected, reasons


def main():
    paths = changed()
    if paths is None:
        print("not a git repo — cannot tell what changed, running everything",
              file=sys.stderr)
        for t in test_files():
            print(t)
        return 0
    if not paths:
        print("no changes since HEAD — nothing to run", file=sys.stderr)
        return 0

    mods = _project_modules()
    tests = test_files()
    selected, reasons = select(paths, mods, tests)
    for r in reasons:
        print(f"  {r}", file=sys.stderr)
    print(f"  selected {len(selected)} of {len(tests)} test files",
          file=sys.stderr)
    for t in sorted(selected):
        print(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
