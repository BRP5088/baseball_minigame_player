"""Pins tools/run_census.py's counts on the three 2026-09-20 fixture logs.

I-19 (ISSUES.md): the tool summarises overnight/run_one_match_*.log into one row
per run. ISSUES.md's own expected numbers for two of the runs: run b has 8
refused plays and 3 refused discards; run c has 3 plays, 3 deal timeouts with an
edge, stop reason unreadable_screens. Cross-checked by hand against the log text
before being pinned here (see agent_progress/issues/I-19/progress.md).

Shape follows tests/harness/test_state_files_are_real.py: check(label, cond),
confirmed by `grep -m1 -o "def check(.*)" tests/harness/test_state_files_are_real.py`
before writing any assertion here, per CLAUDE.md's "nine different check()
signatures" warning -- a reversed call would pass vacuously on every input.
"""
import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOL = os.path.join(_ROOT, "tools", "run_census.py")
_LOGS = [
    os.path.join(_ROOT, "overnight", "run_one_match_20260920.log"),
    os.path.join(_ROOT, "overnight", "run_one_match_20260920b.log"),
    os.path.join(_ROOT, "overnight", "run_one_match_20260920c.log"),
]

os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import; the tool
                                        # imports nothing project-specific, but
                                        # every harness script sets this first.

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


for p in _LOGS:
    check(f"fixture log present: {p}", os.path.exists(p))

out = subprocess.run(
    [sys.executable, _TOOL, *_LOGS, "--json"],
    capture_output=True, text=True, timeout=30,
)
check(f"run_census.py exits 0 (rc={out.returncode}, stderr={out.stderr!r})",
      out.returncode == 0)

try:
    rows = json.loads(out.stdout)
except json.JSONDecodeError as e:
    rows = []
    check(f"stdout is valid JSON ({e})", False)

check(f"one row per log plus a TOTAL row (got {len(rows)})", len(rows) == 4)

if len(rows) == 4:
    by_log = {os.path.basename(r["log"]): r for r in rows[:3]}
    total = rows[3]

    a = by_log.get("run_one_match_20260920.log", {})
    b = by_log.get("run_one_match_20260920b.log", {})
    c = by_log.get("run_one_match_20260920c.log", {})

    # ISSUES.md's own numbers, the ones this tool exists to reproduce.
    check(f"run b: 8 refused plays (got {b.get('plays_refused')})",
          b.get("plays_refused") == 8)
    check(f"run b: 3 refused discards (got {b.get('discards_refused')})",
          b.get("discards_refused") == 3)
    check(f"run c: 3 plays confirmed (got {c.get('plays_confirmed')})",
          c.get("plays_confirmed") == 3)
    check(f"run c: 3 deal timeouts with an edge (got {c.get('deal_timeouts_with_edge')})",
          c.get("deal_timeouts_with_edge") == 3)
    check(f"run c: stop reason unreadable_screens (got {c.get('stop_reason')!r})",
          c.get("stop_reason") == "unreadable_screens")

    # Hand-verified against the log text directly (see progress.md), not from
    # ISSUES.md's prose -- these are the columns ISSUES.md did not quote.
    check(f"run a: 24 hands read (got {a.get('hands_read')})", a.get("hands_read") == 24)
    check(f"run a: 7 plays confirmed (got {a.get('plays_confirmed')})",
          a.get("plays_confirmed") == 7)
    check(f"run a: 9 discards refused (got {a.get('discards_refused')})",
          a.get("discards_refused") == 9)
    check(f"run a: 5 reveals not logged (got {a.get('reveals_not_logged')})",
          a.get("reveals_not_logged") == 5)
    check(f"run a: stop reason unhandled_KeyboardInterrupt (got {a.get('stop_reason')!r})",
          a.get("stop_reason") == "unhandled_KeyboardInterrupt")
    check(f"run b: 8 stall-breaks (got {b.get('stall_breaks')})", b.get("stall_breaks") == 8)
    check(f"run c: 7 nudges (got {c.get('nudges')})", c.get("nudges") == 7)
    check(f"run c: 15 unreadable polls (got {c.get('unreadable_polls')})",
          c.get("unreadable_polls") == 15)

    # ANTI-VACUITY: the TOTAL row must actually sum the per-log rows, not just
    # print zeros or copy one row -- a total that never checks anything would
    # pass this test for free.
    check(f"TOTAL plays_refused sums the rows (got {total.get('plays_refused')})",
          total.get("plays_refused") == 8)
    check(f"TOTAL deal_timeouts sums the rows (got {total.get('deal_timeouts')})",
          total.get("deal_timeouts") == 26)
    check(f"TOTAL stop_reason is not summed (got {total.get('stop_reason')!r})",
          total.get("stop_reason") == "-")

# Default-glob path: run from the project root with no log args and confirm it
# picks up the same three fixtures sorted by name (the --json call above passed
# them explicitly, which does not exercise the glob default at all).
out2 = subprocess.run(
    [sys.executable, _TOOL, "--json"],
    capture_output=True, text=True, cwd=_ROOT, timeout=30,
)
check(f"default glob exits 0 (rc={out2.returncode}, stderr={out2.stderr!r})",
      out2.returncode == 0)
try:
    rows2 = json.loads(out2.stdout)
    names2 = [os.path.basename(r["log"]) for r in rows2[:-1]]
except json.JSONDecodeError:
    names2 = []
check(f"default glob found all three fixtures, sorted (got {names2})",
      names2 == ["run_one_match_20260920.log", "run_one_match_20260920b.log",
                 "run_one_match_20260920c.log"])

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
