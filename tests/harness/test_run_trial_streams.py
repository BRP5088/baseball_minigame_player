"""A trial's log must arrive WHILE it runs, and a hung trial must be killed.

WHAT THIS GUARDS. `_harness.run_trial` used subprocess.run(capture_output=True),
which holds every line until the child exits. Trials here take 90-340s, so an
overnight harness printed nothing for minutes and a slow trial looked exactly
like a wedged one. That is "a slow step and a hung step with identical output",
item seven in CLAUDE.md's catalogue -- and it is the same defect run_tests.sh
grew its live progress line to fix, one level up. The operator's only signal
that an unattended two-hour run is alive is this log.

The second half is CLAUDE.md 10.14: a timeout must be enforced from OUTSIDE the
process, and it must be SIGKILL. signal.alarm did not interrupt a 590s trial
blocked inside a capture, and the signal handlers in this stack swallow the
polite signals.

HOW THE TIMING CHECK AVOIDS BEING FLAKY. It never compares against a wall-clock
constant. It compares the arrival time of the FIRST log line against the trial's
OWN total duration, both measured by this process in the same run -- so load
inflates both and can only make the margin safer, never produce a false pass.
The child holds a long fixed sleep after its first line, which puts a floor
under the total that load cannot erode.
"""
import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import _harness

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


SCRATCH = os.environ.get("TMPDIR", "/tmp").rstrip("/")
CHILD = os.path.join(SCRATCH, f"_rt_child_{os.getpid()}.py")

# stdout early, then a long sleep, then the JSON result. stderr too, so the two
# prefixes can be told apart.
open(CHILD, "w").write(
    "import json, sys, time\n"
    "if len(sys.argv) > 2 and sys.argv[1] == '--one-trial':\n"
    "    print('EARLY-STDOUT', flush=True)\n"
    "    print('EARLY-STDERR', file=sys.stderr, flush=True)\n"
    "    time.sleep(float(sys.argv[2]))\n"
    "    print(json.dumps({'arrived': True, 'marker': 'RESULT-JSON'}))\n"
    "    sys.exit(0)\n")

HANG = os.path.join(SCRATCH, f"_rt_hang_{os.getpid()}.py")
open(HANG, "w").write(
    "import sys, time\n"
    "if len(sys.argv) > 2 and sys.argv[1] == '--one-trial':\n"
    "    print('STARTED', flush=True)\n"
    "    time.sleep(30)\n")

try:
    # --- 1. output arrives DURING the trial -------------------------------
    SLEEP = 4.0
    t0 = time.time()
    stamped = []
    r, secs = _harness.run_trial(CHILD, str(SLEEP), 60, cwd=SCRATCH,
                                 log=lambda m: stamped.append(
                                     (time.time() - t0, str(m))))
    check("the trial's result is parsed", r == {"arrived": True,
                                                "marker": "RESULT-JSON"})
    # ANTI-VACUITY: if the child produced no output at all, every timing check
    # below passes for free.
    check("the child actually produced log output", len(stamped) >= 2)

    first = min((t for t, m in stamped if "EARLY-STDOUT" in m), default=None)
    check("stdout was forwarded", first is not None)
    if first is not None:
        # The child sleeps SLEEP seconds AFTER its first line, so a buffered
        # implementation cannot deliver that line before ~SLEEP. Half of it is
        # a wide margin that load can only widen.
        check(f"the first line arrived at t+{first:.1f}s, well before the "
              f"{secs}s trial ended (buffered would be ~{SLEEP}s)",
              first < secs - SLEEP / 2)

    joined = "\n".join(m for _, m in stamped)
    check("stderr was forwarded too", "EARLY-STDERR" in joined)
    check("stdout and stderr are distinguishable",
          any("| " in m and "EARLY-STDOUT" in m for _, m in stamped)
          and any("! " in m and "EARLY-STDERR" in m for _, m in stamped))
    check("the JSON result line is NOT echoed as log output",
          "RESULT-JSON" not in joined)

    # --- 2. a hung trial is killed, and is INVALID not a failure ----------
    t0 = time.time()
    lines = []
    r, secs = _harness.run_trial(HANG, "x", 3, cwd=SCRATCH, log=lines.append)
    took = time.time() - t0
    check("a hung trial returns None -- INVALID, never a failure", r is None)
    check(f"and was killed near its 3s deadline (took {took:.1f}s), not left "
          f"to run for 30", took < 20)
    check("its pre-hang output was still forwarded",
          any("STARTED" in l for l in lines))
    check("and the log says it was killed, not that it failed",
          any("INVALID" in l and "killed" in l for l in lines))

    leftover = subprocess.run(["pgrep", "-f", os.path.basename(HANG)],
                              capture_output=True, text=True)
    check("no orphaned child survives the kill", not leftover.stdout.strip())

    # --- 3. a child that prints nothing parseable is INVALID --------------
    BAD = os.path.join(SCRATCH, f"_rt_bad_{os.getpid()}.py")
    open(BAD, "w").write("import sys\nprint('no json here')\nsys.exit(3)\n")
    try:
        r, secs = _harness.run_trial(BAD, "x", 30, cwd=SCRATCH, log=None)
        check("a child printing no JSON is INVALID, not a failure", r is None)
    finally:
        os.remove(BAD)

    # --- 4. temp files are cleaned up ------------------------------------
    leaked = [f for f in os.listdir(SCRATCH)
              if f.startswith(f"trial_{os.getpid()}_")]
    check("run_trial leaves no temp files behind", not leaked)

finally:
    for f in (CHILD, HANG):
        try:
            os.remove(f)
        except OSError:
            pass

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
