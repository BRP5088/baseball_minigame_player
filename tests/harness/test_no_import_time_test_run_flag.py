"""No module under tools/ or overnight/ may set BASEBALL_TEST_RUN at import time.

That flag holds every input path OFF. Set by an offline scorer at module
level, it switched stick injection off inside a LIVE harness that imported the
scorer for one function (overnight/prompt_zone.py importing
tools/prompt_ocr_ab.read, 2026-09-07): the leg walked, the import ran, and
fifty "readings" followed of a character and camera that never moved again.
The flag belongs in main(), under `if __name__ == "__main__"`, or in a test.

Static (AST): a top-level statement that assigns or setdefaults the flag on
os.environ fails; the same inside a function is fine. Carries a positive
control so it cannot pass by scanning nothing.
"""
import ast
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)

FLAG = "BASEBALL_TEST_RUN"


def _sets_flag(node):
    """True for os.environ[FLAG] = ... or os.environ.setdefault(FLAG, ...)."""
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                    and t.slice.value == FLAG):
                return True
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        f = node.value.func
        if (isinstance(f, ast.Attribute) and f.attr == "setdefault" and node.value.args
                and isinstance(node.value.args[0], ast.Constant) and node.value.args[0].value == FLAG):
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
    assert offenders(f'import os\ndef main():\n    os.environ.setdefault("{FLAG}", "1")\n') == []
    print(f"scanned {len(files)} modules under tools/ and overnight/")
    for f, where in bad:
        print(f"FAIL {f} sets {FLAG} at import time (line {where})")
    if bad:
        sys.exit(1)
    print(f"PASS no tool or harness sets {FLAG} at import time")


if __name__ == "__main__":
    main()
