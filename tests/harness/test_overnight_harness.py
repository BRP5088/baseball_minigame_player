"""The A/B harness's timeout must actually kill a blocked trial.

WHY THIS EXISTS. Six overnight scripts enforced their per-trial timeout with
`signal.alarm`. Measured 2026-09-03: a 590s trial sailed straight past a 260s
alarm, because the process was blocked inside a screen capture and never
returned to Python to take the signal. The run produced nothing and the ceiling
looked like it was working.

That defect is invisible from inside — a timeout that never fires and a trial
that never needed one produce identical output. So this test asserts against a
child that is DELIBERATELY blocked.
"""
import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ["BASEBALL_TEST_RUN"] = "1"

import _harness as h

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


import tempfile
TMP = tempfile.mkdtemp(prefix="harness_")


def child(name, body):
    p = os.path.join(TMP, name)
    with open(p, "w") as fh:
        fh.write(body)
    return p


# --- a blocked child must be KILLED, not waited on ------------------------
blocker = child("blocker.py", "import time\ntime.sleep(300)\n")
t0 = time.time()
res, secs = h.run_trial(blocker, 1, timeout=3, cwd=TMP)
elapsed = time.time() - t0
check("a blocked trial is killed", res is None)
check("and it is killed NEAR the deadline, not after the sleep",
      elapsed < 15)

# --- a healthy child's JSON comes back ------------------------------------
good = child("good.py", 'import json,sys\nprint(json.dumps({"arrived": True, "depth": 3}))\n')
res, secs = h.run_trial(good, 1, timeout=30, cwd=TMP)
check("a healthy trial returns its JSON", res == {"arrived": True, "depth": 3})

# --- a crashing child is INVALID, never a failure -------------------------
crasher = child("crasher.py", "raise SystemExit(3)\n")
res, secs = h.run_trial(crasher, 1, timeout=30, cwd=TMP)
check("a crashed trial is INVALID (None), not a False arrival", res is None)

# --- a child printing garbage is INVALID ----------------------------------
noisy = child("noisy.py", 'print("not json at all")\n')
res, secs = h.run_trial(noisy, 1, timeout=30, cwd=TMP)
check("unparseable output is INVALID", res is None)

# --- the arm interleaving must alternate ----------------------------------
seq = [a for _t, a in h.interleave(["A", "B"], trials=3)]
check("arms alternate", seq == ["A", "B", "A", "B", "A", "B"])

# --- n is pinned to the documented minimum --------------------------------
# Literal, not compared to itself: n=3 has power 0.00 here and n=10 has 0.94.
check("TRIALS is the documented minimum of 10", h.TRIALS == 10)

# --- signal.alarm: a RATCHET, not a snapshot ------------------------------
#
# `signal.alarm` does not interrupt a trial blocked inside a capture, so a
# script using it has no working timeout. Five scripts still do. Migrating them
# all today would be a large change to code that may never run again, so this
# is a ratchet instead: the list may SHRINK, never GROW.
#
# A plain "none are armed" assertion would be red until every script is
# migrated, and a red suite gets ignored. A plain snapshot of the current state
# would silently bless a sixth. This does neither.
import glob

# THE RATCHET IS CLOSED. It was five files, then a list that could only shrink;
# on 2026-09-17 all four that still armed it were migrated to run_trial and the
# fifth (ab_local_recovery.py) turned out never to have armed it at all -- it was
# in the list on the strength of a docstring mentioning the call. So the allowed
# set is EMPTY and the check is now simply "no harness arms signal.alarm".
KNOWN_ARMED = set()

# GREP THE CODE HALF, NOT THE WHOLE LINE (CLAUDE.md 10b). Every migrated file
# explains in a comment what it replaced, and a bare substring test cannot tell a
# comment from a call -- it reported a correctly-migrated ab_stall.py as STILL
# ARMED because its new comment quoted the thing it had just deleted. One agent
# then contorted its prose to dodge this test, which is the test bullying the
# code. A lesson must be free to name what it is about.
armed = set()
for f in sorted(glob.glob(os.path.join(_ROOT, "overnight", "ab_*.py"))):
    code = "\n".join(l.split("#", 1)[0]
                     for l in open(f, encoding="utf-8").read().splitlines())
    if "signal.alarm(" in code:
        armed.add(os.path.basename(f))

new = armed - KNOWN_ARMED
check(f"NO harness arms signal.alarm (armed: {sorted(new) or 'none'})", not new)

# CONTROL: the code-half split must not have blinded the check entirely. A real
# call still has to be seen, or this passes by looking at nothing.
_probe = "x = 1\nsignal.alarm(30)  # a real call, with a trailing comment\n"
_probe_code = "\n".join(l.split("#", 1)[0] for l in _probe.splitlines())
check("CONTROL: a real signal.alarm call is still detected through the split",
      "signal.alarm(" in _probe_code)
check("CONTROL: the same call INSIDE a comment is not",
      "signal.alarm(" not in "\n".join(
          l.split("#", 1)[0] for l in "# we used to signal.alarm(30) here\n".splitlines()))
check("ab_attempts.py is timed out-of-process", "ab_attempts.py" not in armed)

fixed = KNOWN_ARMED - armed
if fixed:
    print(f"    NOTE: {sorted(fixed)} no longer arm it — "
          f"remove them from KNOWN_ARMED so the ratchet keeps tightening")

# And the measurement calls must not discard their logger. Silencing the RESET
# is fine; silencing the thing being measured is the first entry in this
# project's diagnosis catalogue.
discarding = []
for f in sorted(glob.glob(os.path.join(_ROOT, "overnight", "ab_*.py"))):
    for i, line in enumerate(open(f), 1):
        if "log=lambda *a: None" in line and not line.lstrip().startswith("#"):
            if "reset_environment" not in line:
                discarding.append(f"{os.path.basename(f)}:{i}")
check(f"no A/B discards the logger on a measurement call "
      f"({discarding or 'none'})", not discarding)

import shutil
shutil.rmtree(TMP, ignore_errors=True)
print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
