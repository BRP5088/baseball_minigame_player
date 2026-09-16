"""Every test file must set BASEBALL_TEST_RUN before it imports a project module.

`run_tests.sh` exports the flag, so the SUITE has always been safe. A file run on
its own is not, and that is how tests are actually debugged -- one file, from the
IDE or the shell. Without the flag `can_use_background_input()` returns True, and
then `input_controller.press()` posts real keystrokes to chiaki. CLAUDE.md records
the version of this that already happened: a mutation run drove the verified ban
navigator with `confirm_play` on "c", the user watched "c" appear in their own
window, and a paid match was parked on the console at the time.

Found 2026-09-17 by running one harness file standalone: it reached
`_harness.alive()` -> `compass.fast_capture()` and failed because chiaki was down.
The same file passes inside the suite. A test whose verdict depends on whether the
rig happens to be running is not an offline test. 58 of 223 files were in that
state, 32 of them importing a rig or input module -- including
`test_reset_sequence.py`, which imports `input_controller` AND `reset_env`, whose
sequence is OPTIONS then CROSS: mid-match that is "Give up?" answered YES.

ORDER, NOT PRESENCE. Some modules read the flag at import (orchestrator's
`_SYNTHETIC_LOG` was bound at import and left an unstamped row in the real
match log) and some at call time. Setting it after the import only fixes the
second kind, and looks identical to doing it right.
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def _project_modules():
    """Top-level module names this repo defines, so an import of one is detectable."""
    names = set()
    for f in os.listdir(_ROOT):
        if f.endswith(".py"):
            names.add(f[:-3])
    for d in ("overnight", "tools"):
        p = os.path.join(_ROOT, d)
        if os.path.isdir(p):
            names.add(d)
    return names


PROJECT = _project_modules()


def offenders(root):
    """(relpath, why) for every test file that imports a project module too early."""
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {"__pycache__"}]
        for f in sorted(files):
            if not (f.startswith("test_") and f.endswith(".py")):
                continue
            p = os.path.join(dirpath, f)
            try:
                tree = ast.parse(open(p, encoding="utf-8", errors="replace").read())
            except SyntaxError:
                continue
            flag_at = None
            import_at = None
            for node in tree.body:          # module level only: that is the risk
                if flag_at is None and _sets_flag(node):
                    flag_at = node.lineno
                if import_at is None and _imports_project(node):
                    import_at = node.lineno
            rel = os.path.relpath(p, _ROOT)
            if import_at is None:
                continue                    # imports nothing of ours: nothing to race
            if flag_at is None:
                out.append((rel, f"never sets the flag, imports ours at :{import_at}"))
            elif flag_at > import_at:
                out.append((rel, f"sets the flag at :{flag_at}, too late for the "
                                 f"import at :{import_at}"))
    return out


def _sets_flag(node):
    """os.environ["BASEBALL_TEST_RUN"] = "1"  or  os.environ.setdefault(...).

    setdefault is accepted and is arguably the better form: it lets a caller that
    has DELIBERATELY unset the flag keep it unset, which is how the negative half
    of test_state_io's stamp check works.
    """
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if (isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Attribute)
                    and t.value.attr == "environ"):
                try:
                    if ast.literal_eval(t.slice) == "BASEBALL_TEST_RUN":
                        return True
                except Exception:
                    pass
        return False
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        fn = node.value.func
        if (isinstance(fn, ast.Attribute) and fn.attr == "setdefault"
                and isinstance(fn.value, ast.Attribute) and fn.value.attr == "environ"
                and node.value.args):
            try:
                return ast.literal_eval(node.value.args[0]) == "BASEBALL_TEST_RUN"
            except Exception:
                return False
    return False


def _imports_project(node):
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] in PROJECT for a in node.names)
    if isinstance(node, ast.ImportFrom):
        return bool(node.module) and node.module.split(".")[0] in PROJECT
    return False


TESTS = os.path.join(_ROOT, "tests")
_n = sum(1 for dp, dn, fn in os.walk(TESTS) for f in fn
         if f.startswith("test_") and f.endswith(".py"))

check(_n > 150, f"CONTROL: {_n} test files found to scan (a broken walk finds none "
                "and reports a clean result)")
check(len(PROJECT) > 50, f"CONTROL: {len(PROJECT)} project module names known, so "
                         "a project import is actually recognisable")

# CONTROL: the two violations must both be caught, on a planted file.
import tempfile
with tempfile.TemporaryDirectory() as td:
    open(os.path.join(td, "test_never.py"), "w").write(
        "import os, sys\nimport decision_engine\n")
    open(os.path.join(td, "test_late.py"), "w").write(
        "import os, sys\nimport decision_engine\n"
        'os.environ["BASEBALL_TEST_RUN"] = "1"\n')
    open(os.path.join(td, "test_fine.py"), "w").write(
        "import os, sys\n"
        'os.environ["BASEBALL_TEST_RUN"] = "1"\n'
        "import decision_engine\n")
    open(os.path.join(td, "test_setdefault.py"), "w").write(
        "import os, sys\n"
        'os.environ.setdefault("BASEBALL_TEST_RUN", "1")\n'
        "import decision_engine\n")
    planted = {r for r, _ in offenders(td)}
check(planted == {"test_never.py", "test_late.py"} or
      {os.path.basename(x) for x in planted} == {"test_never.py", "test_late.py"},
      f"CONTROL: a missing flag AND a late flag are both caught, a correct one is not "
      f"(caught {sorted(os.path.basename(x) for x in planted)})")

bad = offenders(TESTS)
for rel, why in bad:
    print(f"      {rel}: {why}")
check(not bad, f"every test file sets BASEBALL_TEST_RUN before its first project "
               f"import ({len(bad)} do not)")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
