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

KNOWN_ARMED = {
    "ab_leg_speed.py",
    "ab_leg_tolerance.py",
    "ab_local_recovery.py",
    "ab_reference_pose.py",
    "ab_stall.py",
}

armed = set()
for f in sorted(glob.glob(os.path.join(_ROOT, "overnight", "ab_*.py"))):
    if "signal.alarm(" in open(f).read():
        armed.add(os.path.basename(f))

new = armed - KNOWN_ARMED
check(f"no NEW script arms signal.alarm (new: {sorted(new) or 'none'})", not new)
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
