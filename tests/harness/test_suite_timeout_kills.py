"""A hung test must be reported as HUNG, not as an ordinary FAIL.

WHY THIS EXISTS
---------------
run_tests.sh used to enforce its per-test ceiling with

    perl -e 'alarm shift; exec @ARGV' "$TEST_TIMEOUT" python3 "$f"

`exec` REPLACES the perl process, so SIGALRM was delivered to the test itself.
cysignals — pulled in transitively through the vision stack — installs a SIGALRM
handler that raises AlarmInterrupt, so the test died with a normal Python
traceback and exit 1. The suite then printed FAIL, and the branch that explains
"killed after Ns — it never finished, so it proved nothing" could never run.

That is this project's signature failure exactly: a slow step and a hung step
with identical output. It cost a real diagnosis on 2026-09-05, when
tests/routing/test_leg_turn_tolerance.py hit the ceiling under load and was read
as an ordinary assertion failure.

The fix is to keep the alarm in a PARENT process and SIGKILL the child. Nothing
can install a handler for SIGKILL. This test pins that, using a child that
installs the very handler which defeated the old wrapper.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import re
import subprocess
import tempfile

fails = []


def check(cond, msg):
    print(f"{'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        fails.append(msg)


SH = _os.path.join(_ROOT, "run_tests.sh")
src = open(SH, encoding="utf-8").read()

# 1. The defeated wrapper must not come back. `alarm shift; exec` is the exact
#    shape that failed, and it reads as obviously correct, so it will be
#    reintroduced by anyone simplifying this file.
check("alarm shift" not in src,
      "run_tests.sh no longer uses `alarm shift; exec` (SIGALRM into the test)")
check("TIMEOUT_PL" in src and "kill 'KILL'" in src,
      "run_tests.sh kills the child with SIGKILL from a parent")
check("export OUT TEST_TIMEOUT TIMEOUT_PL" in src,
      "TIMEOUT_PL is exported, so xargs' subshell can see it")
check(len(re.findall(r'perl -e "\$TIMEOUT_PL"', src)) >= 2,
      "both the per-test run and the side-effect check use the hard timeout")

# 2. THE WRAPPER ITSELF MUST WORK. Extracted from run_tests.sh rather than
#    copied here — a copy would drift, and then this file would pass while the
#    suite still mistook hangs for failures.
m = re.search(r"TIMEOUT_PL=\$\(cat <<'PERL'\n(.*?)\nPERL\n\)", src, re.S)
check(m is not None, "the timeout wrapper can be extracted from run_tests.sh")

if m:
    pl = m.group(1)
    py = _sys.executable

    def run(timeout, code, want_import_cysignals=False):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            if want_import_cysignals:
                # The handler that defeated the old wrapper.
                fh.write("import cysignals.signals\n")
            fh.write(code)
            path = fh.name
        try:
            return subprocess.run(["perl", "-e", pl, str(timeout), py, "-B", path],
                                  capture_output=True, text=True, timeout=60)
        finally:
            _os.unlink(path)

    # A hang must be 142 even when the child owns a SIGALRM handler.
    r = run(2, "import time\ntime.sleep(90)\n", want_import_cysignals=True)
    check(r.returncode == 142,
          f"a hang that handles SIGALRM is still killed and reports 142 "
          f"(got {r.returncode})")
    check("AlarmInterrupt" not in (r.stderr or ""),
          "the killed child does not get to raise AlarmInterrupt")

    # A hang with no handler at all must behave the same.
    r = run(2, "import time\ntime.sleep(90)\n")
    check(r.returncode == 142, f"a plain hang reports 142 (got {r.returncode})")

    # Ordinary outcomes must pass straight through, or every test would look
    # like a hang.
    r = run(30, "print('fine')\n")
    check(r.returncode == 0 and "fine" in r.stdout,
          "a passing test still exits 0 and its stdout survives")
    r = run(30, "raise SystemExit(3)\n")
    check(r.returncode == 3, f"an exit code passes through (got {r.returncode})")
    r = run(30, "import sys\nsys.stderr.write('boom\\n')\nraise SystemExit(1)\n")
    check(r.returncode == 1 and "boom" in r.stderr,
          "a failing test still exits non-zero and its stderr survives")

print()
if fails:
    raise SystemExit(f"{len(fails)} FAILED")
print("OK: a hung test is killed and reported as HUNG, not as a FAIL")
