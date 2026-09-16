"""Every constant CLAUDE.md quotes must still match the source that defines it.

CLAUDE.md says its constants are COPIES and that the source `file:line` is the
authority. Nothing enforced that, and copies rot: on 2026-09-17 a sweep found FIVE
numbers in the file that no longer matched their source, including
`SETTLE_CALIBRATION_WIDTH = 2000` (it is 1920, and had been for a day) quoted in
three separate comment blocks. Another sweep the same evening took that stale figure
FROM this file and nearly reported it as a current measurement.

That is the expensive failure: a wrong constant in CLAUDE.md is not a typo, it is a
wrong premise handed to whoever reads it next, and nothing exercises it until someone
acts on it.

WHAT THIS SCANS. Every `NAME <number>` in CLAUDE.md where NAME is an uppercase
module-level constant defined somewhere in the tree. It passes when the quoted value
equals a defined one, or when the TRUE value appears ON THE SAME LINE -- which is how
this file legitimately records a change ("`WHITE_LEVEL` 200 -> **225**", "120 as first
written, it ships at 165"). Prose that states the move is correct; prose that quotes
only the dead value is the bug.

SAME LINE, not a window of nearby lines, and a surviving mutant is why. At two lines
either side, reverting `SETTLE_CALIBRATION_WIDTH` to its stale 2000 was EXCUSED by the
next line's "which a 1920 px frame produces" -- an unrelated sentence that happens to
contain the same digits. A rule that cannot tell a correction from a coincidence is
10.4 pointed at a test.

THE CONTROL matters more than usual here: this test would pass by finding nothing if
the regex broke or the AST walk returned no constants, so it asserts a floor on both
and plants a value it must reject.
"""
import ast
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

SKIP_DIRS = {".venv", "paddle_venv", "armor_venv", "models", "chiaki-ng-src",
             "chiaki-ng-build", "node_modules", "__pycache__", "_obsolete",
             "agent_progress", "drafts", "backups", "tests_quarantine"}

# NAME, optionally quoted/linked, then a number. Not NAME-<digit>: that is a ticket id
# (OPEN-18), not a value.
QUOTE = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b(?!-\d)[`\s]*(?:=|is|of|at)?[`\s]*(\d+\.?\d*)\b")
# The correcting value must sit on the SAME line as the stale one; see the docstring.

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def defined_constants():
    """{NAME: {(relpath, value)}} for every module-level numeric constant in the tree."""
    out = {}
    for dirpath, dirs, files in os.walk(_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            try:
                tree = ast.parse(open(p, encoding="utf-8", errors="replace").read())
            except (SyntaxError, ValueError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for t in node.targets:
                    if not (isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 3):
                        continue
                    try:
                        v = ast.literal_eval(node.value)
                    except Exception:
                        continue
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.setdefault(t.id, set()).add((os.path.relpath(p, _ROOT), v))
    return out


def stale_quotes(doc, defined):
    """Quotes whose value matches no definition and has no correction within WINDOW."""
    lines = doc.splitlines()
    out, seen = [], set()
    for m in QUOTE.finditer(doc):
        name, raw = m.group(1), m.group(2)
        if (name, raw) in seen or name not in defined:
            continue
        seen.add((name, raw))
        claimed = float(raw)
        values = {v for _, v in defined[name]}
        if any(abs(claimed - v) < 1e-9 for v in values):
            continue
        # anchor on the DIGITS, which can wrap onto the line after the name
        i = doc[:m.end()].count("\n")
        here = lines[i]
        # a line that also names the TRUE value is recording the change, not rotting
        if any(re.search(rf"\b{re.escape(_fmt(v))}\b", here) for v in values):
            continue
        out.append((i + 1, name, claimed, sorted(defined[name])))
    return out


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)


DEFINED = defined_constants()
DOC = open(os.path.join(_ROOT, "CLAUDE.md")).read()

# --- controls, first: this test must not be able to pass by scanning nothing ---
check(len(DEFINED) > 300,
      f"CONTROL: the AST walk found {len(DEFINED)} named constants in the tree "
      "(a broken walk would report zero stale quotes and look clean)")

_hits = {m.group(1) for m in QUOTE.finditer(DOC)} & set(DEFINED)
check(len(_hits) > 25,
      f"CONTROL: CLAUDE.md quotes {len(_hits)} constants this test can actually check")

_planted = DOC + "\n\nThe gate `POWER_WEIGHT` 0.42 decides every batting play.\n"
check(len(stale_quotes(_planted, DEFINED)) == len(stale_quotes(DOC, DEFINED)) + 1,
      "CONTROL: a planted wrong value (POWER_WEIGHT 0.42) IS caught")

_excused = DOC + "\n\n`POWER_WEIGHT` was 0.42 before it became 0.99.\n"
check(len(stale_quotes(_excused, DEFINED)) == len(stale_quotes(DOC, DEFINED)),
      "CONTROL: prose recording a change (0.42 -> 0.99) is NOT flagged")

# --- the check itself ---
stale = stale_quotes(DOC, DEFINED)
for line, name, claimed, defs in stale:
    where = ", ".join(f"{f}={_fmt(v)}" for f, v in defs)
    print(f"      CLAUDE.md:{line}  {name} quoted {_fmt(claimed)}  but source says {where}")
check(not stale,
      f"every constant CLAUDE.md quotes matches its source ({len(stale)} stale)")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
