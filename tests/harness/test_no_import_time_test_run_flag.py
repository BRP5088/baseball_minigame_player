"""No module under tools/ or overnight/ may set OR CLEAR BASEBALL_TEST_RUN at import time.

That flag holds every input path OFF. Set by an offline scorer at module
level, it switched stick injection off inside a LIVE harness that imported the
scorer for one function (overnight/prompt_zone.py importing
tools/prompt_ocr_ab.read, 2026-09-07): the leg walked, the import ran, and
fifty "readings" followed of a character and camera that never moved again.
The flag belongs in main(), under `if __name__ == "__main__"`, or in a test.

CLEARING it at import is the same hazard from the other side, and this file
missed it for a while: tools/crawl_sheet.py did
`os.environ.pop("BASEBALL_TEST_RUN", None)` at module level, unconditionally,
so importing it (tools/match_crawl.py did, for `panel` and for the module
itself) silently switched the lockout back ON for the rest of the process --
CLAUDE.md 10.1's guard-that-disables-itself. This scanner's own `_sets_flag`
only matched `os.environ[FLAG] = ...` and `os.environ.setdefault(FLAG, ...)`,
so a `.pop(FLAG, ...)` sailed straight through; that is the gap, and it is
fixed below by treating a top-level `.pop(FLAG` call the same as a set.

Static (AST): a top-level statement that assigns, setdefaults, or POPS the
flag on os.environ fails; the same inside a function is fine. Carries a
positive control so it cannot pass by scanning nothing.
"""
import ast
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)

FLAG = "BASEBALL_TEST_RUN"


def _is_flag_call(call, name):
    """True for os.environ.<name>(FLAG, ...) -- covers setdefault AND pop."""
    f = call.func
    return (isinstance(call, ast.Call) and isinstance(f, ast.Attribute) and f.attr == name
            and call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value == FLAG)


def _sets_flag(node):
    """True for os.environ[FLAG] = ..., os.environ.setdefault(FLAG, ...), or
    os.environ.pop(FLAG, ...) -- clearing the flag at import is the same hazard as
    setting it: it silently flips the lockout the OTHER way for every importer
    (tools/crawl_sheet.py's `os.environ.pop("BASEBALL_TEST_RUN", None)` is what this
    catches). A bare `.pop(...)` statement is an ast.Expr; `.pop(...)` used as a value
    (`x = os.environ.pop(FLAG, None)`) is an ast.Assign -- check both shapes."""
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                    and t.slice.value == FLAG):
                return True
        if isinstance(node.value, ast.Call) and _is_flag_call(node.value, "pop"):
            return True
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        if _is_flag_call(node.value, "setdefault") or _is_flag_call(node.value, "pop"):
            return True
    return False


def offenders(src):
    tree = ast.parse(src)
    return [n.lineno for n in tree.body if _sets_flag(n)]      # TOP LEVEL only


def main():
    files = sorted(glob.glob(os.path.join(_ROOT, "tools", "*.py")) + glob.glob(os.path.join(_ROOT, "overnight", "*.py")))
    assert len(files) >= 10, f"scanned only {len(files)} files; the glob is wrong"
    bad = []
    for f in files:
        try:
            lines = offenders(open(f, encoding="utf-8").read())
        except SyntaxError as e:
            bad.append((f, f"syntax error {e}")); continue
        if lines:
            bad.append((os.path.relpath(f, _ROOT), lines))
    # positive control: the shape must be detectable, at top level and not inside a def
    assert offenders(f'import os\nos.environ.setdefault("{FLAG}", "1")\n') == [2]
    assert offenders(f'import os\nos.environ["{FLAG}"] = "1"\n') == [2]
    assert offenders(f'import os\nos.environ.pop("{FLAG}", None)\n') == [2]
    assert offenders(f'import os\nx = os.environ.pop("{FLAG}", None)\n') == [2]
    assert offenders(f'import os\ndef main():\n    os.environ.setdefault("{FLAG}", "1")\n') == []
    assert offenders(f'import os\ndef main():\n    os.environ.pop("{FLAG}", None)\n') == []
    print(f"scanned {len(files)} modules under tools/ and overnight/")
    for f, where in bad:
        print(f"FAIL {f} sets {FLAG} at import time (line {where})")
    if bad:
        sys.exit(1)
    print(f"PASS no tool or harness sets {FLAG} at import time")


if __name__ == "__main__":
    main()
