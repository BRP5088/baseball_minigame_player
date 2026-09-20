"""No module may define the same top-level name twice. Python rebinds in SILENCE.

2026-09-20: a discard-stall helper was added to orchestrator.py as
`_hand_signature(hand)` -- seventeen hundred lines below an existing
`_hand_signature(hand_img)` that the deal gate calls. Same module, same scope, so
the later def simply won. wait_for_hand_deal then passed a PIL Image to a function
expecting a list, the iteration raised, the except set readable False, and EVERY
DEAL timed out at the full 20 s while the gate's own log line reported a frame
delta of 55.7 against a threshold of 15 -- "nothing moved" about a screen that
plainly had.

NOTHING FAILED. No NameError, no TypeError reaching the caller, no import warning.
The only symptom was deals getting slower, which is indistinguishable from a slow
console -- section 10.1 reached through the NAMESPACE instead of the control flow.
It was found by a different session reading deal_timing.jsonl, not by this suite.

A duplicate top-level def is never intentional in this codebase: if two things
want the same name they belong in different modules or want different names. This
scans the Module body only, so a def inside `if/else`, a try/except fallback, or a
nested function is untouched -- those are real patterns and are not duplicates at
module scope.
"""
import ast as _ast
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# ".claude" HOLDS OTHER AGENTS' GIT WORKTREES -- five full copies of this repo on
# 2026-09-20, each with its own test_simulate_rules.py. Scanning them reports another
# checkout's code as this one's, which is CLAUDE.md 10.36b's too-wide failure: the
# find|xargs recipe there fixed grep's too-NARROW problem and created a too-WIDE one,
# and both give a confident wrong answer. A worktree is a different tree; it is not
# this tree's duplicate definition.
SKIP_DIRS = {".venv", "paddle_venv", "agent_progress", "drafts", "backups",
             "_obsolete", "tests_quarantine", "chiaki-ng-src", "chiaki-ng-build",
             "__pycache__", ".git", ".claude", "demos", "screenshot_log",
             "diagnostics"}


def duplicate_top_level_defs(path):
    """[(name, [lineno, ...]), ...] for names def'd/class'd twice in Module body."""
    try:
        tree = _ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, UnicodeDecodeError):
        return []
    seen = {}
    for node in tree.body:                     # MODULE BODY ONLY -- see the docstring
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            seen.setdefault(node.name, []).append(node.lineno)
    return [(n, ls) for n, ls in seen.items() if len(ls) > 1]


scanned = 0
offenders = []
for dirpath, dirnames, filenames in _os.walk(_ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        p = _os.path.join(dirpath, fn)
        scanned += 1
        for name, lines in duplicate_top_level_defs(p):
            offenders.append((_os.path.relpath(p, _ROOT), name, lines))

# A SCAN THAT LOOKED AT NOTHING PROVES NOTHING (10.1). Pin a floor on coverage so a
# broken walk or an over-eager skip list fails here instead of reporting success.
check(scanned >= 150,
      f"only {scanned} python files scanned — the walk or SKIP_DIRS is wrong, and a "
      "clean result from a scan that looked at almost nothing is not a clean result")

check(not offenders,
      "top-level name defined more than once (the later def silently wins):\n" +
      "\n".join(f"      {f}: {n} at lines {ls}" for f, n, ls in offenders))

# --- POSITIVE CONTROL: the detector must actually fire ------------------------
# Without this the whole file passes on a scanner that can never find anything.
import tempfile                                                      # noqa: E402
with tempfile.TemporaryDirectory() as _td:
    _p = _os.path.join(_td, "planted.py")
    with open(_p, "w") as _f:
        _f.write("def twice(a):\n    return a\n\n\ndef twice(b, c):\n    return b\n")
    _found = duplicate_top_level_defs(_p)
    check(_found and _found[0][0] == "twice",
          f"CONTROL: the detector did not find a planted duplicate def; got {_found!r}. "
          "Every result above is meaningless if this fails.")
    # and it must NOT fire on the legitimate conditional-def pattern
    _q = _os.path.join(_td, "conditional.py")
    with open(_q, "w") as _f:
        _f.write("import sys\nif sys.platform == 'x':\n    def f():\n        pass\n"
                 "else:\n    def f():\n        pass\n")
    check(duplicate_top_level_defs(_q) == [],
          "CONTROL: the detector fired on an if/else fallback def, which is a real "
          "pattern and not a shadow — it would be switched off for noise")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print(f"  {scanned} modules scanned, no top-level name is defined twice")
