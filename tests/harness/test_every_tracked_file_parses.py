"""EVERY TRACKED .py MUST PARSE — the test the undefined-name scanner defers to.

`tests/harness/test_no_undefined_names.py` swallows a SyntaxError with

    except SyntaxError:
        return []                      # a syntax error is a different test

and THAT TEST DID NOT EXIST. So a file that cannot be parsed was invisible to the one
scanner that walks every module: it reported no undefined names in a file it had never
read, and five broken files sat in the repository unnoticed.

SCOPE IS WHAT GIT TRACKS, not a hand-kept directory list. `agent_progress/` is gitignored
scratch and is out by construction rather than by a list someone has to remember to update
-- CLAUDE.md's own lesson that a guard keyed on a hand-maintained list of NAMES rots
silently, because nothing fails when a new name is missing.

THE KNOWN-BROKEN LIST CAN ONLY SHRINK. Each entry must still exist AND still fail to parse;
repairing one turns this test red until it is removed from the list, so the exemption cannot
outlive the problem. That is the same shape as SKIP_FILES in the undefined-name scanner.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, ast, subprocess

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


# Broken when this test was written, 2026-09-13. The damage is the same in all five:
# BLANK LINES WERE STRIPPED, joining two statements into one --
#     `from collections import defaultdictROOT = os.path.dirname(...)`
# Left alone deliberately rather than repaired at a guess: they are drafts, and
# `pending_after_ab/apply_patch62.py` is a patch CLAUDE.md says is WAITING TO BE APPLIED,
# so mangling it further is worse than recording exactly what is wrong with it.
KNOWN_BROKEN = {
    "drafts/yaw/harvest_yaw_null.py": "line 17: cannot use name as import target",
    "drafts/merge/leg_table.py": "line 44: invalid decimal literal",
    "drafts/merge/log_legs.py": "line 9: invalid syntax",
    "drafts/pending_after_ab/apply_patch62.py": "line 929: invalid decimal literal",
    "drafts/doorway/parse_leg2.py": "line 30: invalid decimal literal",
}

try:
    tracked = subprocess.run(["git", "ls-files", "*.py"], cwd=_ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
except Exception as e:
    print(f"  FAIL could not list tracked files ({e})")
    raise SystemExit(1)

print("0. the scan has something to scan")
check(len(tracked) > 150,
      f"git lists {len(tracked)} tracked .py files — a short list would make every check "
      f"below pass by scanning almost nothing")

print("1. every tracked .py parses, except the ones recorded as broken")
broken = {}
for rel in tracked:
    path = _os.path.join(_ROOT, rel)
    if not _os.path.exists(path):
        continue                       # staged-for-deletion; git still lists it
    try:
        ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError as e:
        broken[rel] = f"line {e.lineno}: {e.msg}"
    except Exception as e:
        broken[rel] = type(e).__name__

new = sorted(set(broken) - set(KNOWN_BROKEN))
check(not new,
      f"no NEW unparseable file ({ {k: broken[k] for k in new} if new else 'none'})")

print("2. the known-broken list cannot outlive the problem")
fixed = sorted(set(KNOWN_BROKEN) - set(broken))
check(not fixed,
      f"every entry still fails to parse — REMOVE these, they are fixed: {fixed}"
      if fixed else "every entry still fails to parse")
gone = sorted(p for p in KNOWN_BROKEN if not _os.path.exists(_os.path.join(_ROOT, p)))
check(not gone, f"every entry still exists (delete these stale exemptions: {gone})")

print("3. and the scanner that defers to this test still defers to it")
scanner = open(_os.path.join(_ROOT, "tests", "harness",
                             "test_no_undefined_names.py"), encoding="utf-8").read()
check("except SyntaxError" in scanner,
      "test_no_undefined_names still returns early on a SyntaxError — which is fine ONLY "
      "because this file now exists to catch what it drops")

print(f"\n{len(tracked)} tracked .py files, {len(broken)} unparseable "
      f"({len(KNOWN_BROKEN)} of them recorded)")
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
