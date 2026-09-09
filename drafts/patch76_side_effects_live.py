"""patch76 -- test_no_side_effects must not blame the suite for a LIVE RUN's own writes.

CLAUDE.md 10.13a says explicitly that the SUITE MAY RUN during a live console run: measured
over 30,787 samples, the suite moves sleep overrun from a 1.21 ms median to 1.26 ms and
never past 50 ms. But this test snapshots tracked files, runs the suite, and calls any
change a side effect -- and `match_log.jsonl` is TRACKED and is written by the game itself,
one row per played turn. So the two rules contradict each other, and on 2026-09-09 the
suite went red with 39 rows the live match had appended while it ran.

Failing there is WRONG, and passing silently would be worse: the message it prints ("this
is how 30 synthetic rows got into match_log.jsonl") names a real defect this test caught
once. So the third answer -- INCONCLUSIVE, loudly -- which is the shape tests/cpp already
uses when load makes a timing check unmeasurable.

It is narrow on purpose: only while a console process is actually running, and only for the
files a live run legitimately writes. Every other file, and any change with no live process
to explain it, still FAILS.
"""
import io

P = "tests/harness/test_no_side_effects.py"
s = io.open(P, encoding="utf-8").read()

ANCHOR = """failures = []
for key in sorted(set(before) | set(after)):"""
assert s.count(ANCHOR) == 1, f"loop anchor x{s.count(ANCHOR)}"

NEW = '''# THE FILES A LIVE RUN WRITES ITSELF, one row or one save per played turn. A change to
# one of these while a console process is running is the GAME's doing, not the suite's --
# see the module note above. Anything not in this set still fails, and so does a change to
# one of these with no live process to explain it.
LIVE_WRITTEN = {"match_log.jsonl", "progress.json", "progress_testing.json"}


def _live_console():
    """The names of any console-driving processes running right now."""
    import subprocess
    out = []
    for pat in ("run_cycles.py", "chain_trials.py", "run_tonight.py", "run_testing.py",
                "run_one_match.py", "play_now.py", "record_stream.py"):
        try:
            r = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True,
                               timeout=10)
        except Exception:
            continue
        if r.returncode == 0 and r.stdout.strip():
            out.append(pat)
    return out


_LIVE = _live_console()

failures = []
inconclusive = []
for key in sorted(set(before) | set(after)):'''

s = s.replace(ANCHOR, NEW, 1)

OLD_TAIL = '''    else:
        failures.append(
            f"{key} was MODIFIED by the suite. This is how 30 synthetic rows "
            f"got into match_log.jsonl. Redirect the write with an env var and "
            f"point the test at a temp path.")

if failures:'''
assert s.count(OLD_TAIL) == 1, "tail anchor"
NEW_TAIL = '''    elif _LIVE and key in LIVE_WRITTEN:
        # The game is playing RIGHT NOW and this is a file it writes per turn. The
        # suite cannot be blamed and cannot be cleared -- say so, do not pass quietly.
        inconclusive.append(
            f"{key} changed while a live run was active ({', '.join(_LIVE)}). "
            f"The game writes this file per turn, so this run cannot tell a test's "
            f"write from the game's. Re-run with the console idle to check it.")
    else:
        failures.append(
            f"{key} was MODIFIED by the suite. This is how 30 synthetic rows "
            f"got into match_log.jsonl. Redirect the write with an env var and "
            f"point the test at a temp path.")

for line in inconclusive:
    print(f"INCONCLUSIVE: {line}")

if failures:'''
s = s.replace(OLD_TAIL, NEW_TAIL, 1)
assert "INCONCLUSIVE" in s and "_live_console" in s
io.open(P, "w", encoding="utf-8").write(s)
print("test_no_side_effects: a live run's own writes are now INCONCLUSIVE, not a failure")
