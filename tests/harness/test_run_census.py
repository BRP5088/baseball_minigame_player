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

I-19b (agent_progress/issues/I-19b/progress.md): the run_live_20260920{d,g,h}.log
census found two defects: `deal_timeouts` only matched the pre-I-09 combined
message, and five refusal shapes (I-25/I-21) had no column and were counted by
hand. Both fixed in tools/run_census.py; pinned below against run_live_20260920h.log
(and, for the deal-timeout regex specifically, run_live_20260920d.log, the only
one of the three that actually contains a post-I-09 "no motion seen" line --
h.log has zero deal-timeout lines of any wording, verified by direct grep, so its
own deal_timeouts pin cannot by itself discriminate the fix from the pre-fix
tool; d.log and the synthetic CONTROL below are what actually catch that mutant).

QA round 4 / I-26 (commit cb5f26d, merged 67f3851): `stray_guard`'s pattern went
dead the same way `deal_timeouts` did in I-19b -- I-26 reworded
`_clear_strays`'s refusal from "went unreadable DURING this" to "still
unreadable after" (the re-look), and added a *second* line, "re-looking once
before refusing", for the re-look itself, which recovers on a flicker and is
not a refusal at all. `stray_guard` now counts EITHER the old wording (for logs
that predate I-26) or the new refusal wording; the new re-look line gets its
own `stray_relook` column. h.log PREDATES I-26 (its refusals are what I-26's
own ISSUES.md entry cites as evidence), so it only ever carries the old
wording -- its `stray_guard` pin is unchanged at 4 and it has no `stray_relook`
lines to pin.
"""
import json
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOL = os.path.join(_ROOT, "tools", "run_census.py")
_LOGS = [
    os.path.join(_ROOT, "overnight", "run_one_match_20260920.log"),
    os.path.join(_ROOT, "overnight", "run_one_match_20260920b.log"),
    os.path.join(_ROOT, "overnight", "run_one_match_20260920c.log"),
]
_D_LOG = os.path.join(_ROOT, "overnight", "run_live_20260920d.log")
_H_LOG = os.path.join(_ROOT, "overnight", "run_live_20260920h.log")

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

# --- I-19b: run_live_20260920{d,h}.log -------------------------------------

check(f"fixture log present: {_D_LOG}", os.path.exists(_D_LOG))
check(f"fixture log present: {_H_LOG}", os.path.exists(_H_LOG))


def _grep_count(path, *needles):
    """Count lines in `path` containing any of `needles` -- the "compute the
    expected with grep" half of the pin, done in Python so it needs no shell."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if any(n in line for n in needles))


out3 = subprocess.run(
    [sys.executable, _TOOL, _D_LOG, _H_LOG, "--json"],
    capture_output=True, text=True, timeout=30,
)
check(f"run_census.py exits 0 on d/h logs (rc={out3.returncode}, stderr={out3.stderr!r})",
      out3.returncode == 0)
try:
    rows3 = json.loads(out3.stdout)
except json.JSONDecodeError as e:
    rows3 = []
    check(f"d/h stdout is valid JSON ({e})", False)

if len(rows3) == 3:
    d, h, _total3 = rows3

    expected_h_deal = _grep_count(_H_LOG, "no motion seen in", "the hand never read stable")
    check(f"h.log: deal timeouts equal the grep-computed count "
          f"(got {h.get('deal_timeouts')}, expected {expected_h_deal})",
          h.get("deal_timeouts") == expected_h_deal)
    check(f"h.log: 4 stray_guard (got {h.get('stray_guard')})", h.get("stray_guard") == 4)
    # h.log predates I-26 (see module docstring): it only ever carries the OLD
    # "went unreadable DURING this" wording, never the new re-look line, so it
    # has no re-looks to count.
    check(f"h.log: 0 stray_relook -- it predates I-26's re-look line "
          f"(got {h.get('stray_relook')})", h.get("stray_relook") == 0)
    check(f"h.log: 3 pre_press_guard (got {h.get('pre_press_guard')})",
          h.get("pre_press_guard") == 3)
    check(f"h.log: 3 inferred_select (got {h.get('inferred_select')})",
          h.get("inferred_select") == 3)
    check(f"h.log: 8 plays_refused (got {h.get('plays_refused')})",
          h.get("plays_refused") == 8)

    # d.log is the one of the three tonight's logs that actually contains a
    # post-I-09 "no motion seen" line (verified by direct grep) -- unlike
    # h.log's deal_timeouts pin above, this one DOES change if the tool is
    # reverted to matching the pre-I-09 string alone.
    expected_d_deal = _grep_count(_D_LOG, "no motion seen in", "the hand never read stable")
    check(f"d.log: deal timeouts equal the grep-computed count "
          f"(got {d.get('deal_timeouts')}, expected {expected_d_deal})",
          d.get("deal_timeouts") == expected_d_deal)
else:
    check(f"one row per d/h log plus a TOTAL row (got {len(rows3)})", False)

# --- CONTROL: one line of each new wording, exactly one hit per column -----
#
# I-26 wording, exact strings from input_controller.py's own print()s (grepped
# above the module docstring, not retyped from memory): the re-look
# (":1322-3", recovers on a flicker) and the refusal that follows only when
# the slot is STILL unreadable after it (":1346-9"). One line of each, plus
# the pre-I-26 wording kept below for old-log backward compatibility.

_CONTROL_LOG = (
    '    [cursor] still at 2 after 8 presses — refusing\n'
    '    [cursor] slot(s) [3] went unreadable DURING this operation ([None]) '
    '— refusing.\n'
    '    [cursor] slot(s) [1] read unreadable ([None, 100, 100, 100, 100]) — '
    're-looking once before refusing\n'
    '    [cursor] slot(s) [1] still unreadable after the re-look ([None, '
    '100, 100, 100, 100]) — refusing. They were measurable when this '
    'operation started, so something we pressed lifted them, and a raised '
    'card would go in with the commit.\n'
    "    [cursor] slot 4's position is unreadable, so whether it is already "
    'selected cannot be told — refusing rather than pressing a TOGGLE blind\n'
    "    [cursor] 2's disc is unreadable after the press and was readable "
    'before it — selected by inference (disc unreadable after lift)\n'
    '  play REFUSED 3x running on hand_index 1 on this exact hand — '
    'excluding it\n'
    '    [verify] confirm_play: FAILED after 5 attempts, state never left (2,)\n'
    '  [deal] no motion seen in 20s — nothing dealt. Threshold 15, biggest '
    'delta 5.0: under threshold.\n'
    '  [deal] replacement card seen but the hand never read stable twice in '
    '20s — a reader problem. Threshold 15, biggest delta 40.0.\n'
)
_CONTROL_EXPECTED = {
    "false_cursor": 1, "stray_guard": 2, "stray_relook": 1,
    "pre_press_guard": 1, "inferred_select": 1, "excluded": 1,
    "confirm_verify_fail": 1, "deal_timeouts": 2, "deal_timeouts_with_edge": 1,
}

with tempfile.TemporaryDirectory() as tmpdir:
    control_path = os.path.join(tmpdir, "control.log")
    with open(control_path, "w", encoding="utf-8") as f:
        f.write(_CONTROL_LOG)
    out4 = subprocess.run(
        [sys.executable, _TOOL, control_path, "--json"],
        capture_output=True, text=True, timeout=30,
    )
    check(f"run_census.py exits 0 on the control log (rc={out4.returncode}, "
          f"stderr={out4.stderr!r})", out4.returncode == 0)
    try:
        rows4 = json.loads(out4.stdout)
        control_row = rows4[0]
    except (json.JSONDecodeError, IndexError) as e:
        control_row = {}
        check(f"control stdout is valid JSON with one row ({e})", False)
    for col, want in _CONTROL_EXPECTED.items():
        check(f"control log: {col} == {want} (got {control_row.get(col)})",
              control_row.get(col) == want)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
