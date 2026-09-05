"""The suite must not touch real project data. Runs every OTHER test and checks.

WHY THIS EXISTS
---------------
Twice in one session the test suite silently wrote into live project data:

  1. `diagnostics/` — the tests exercise all seven stall paths, so each run
     dumped ~20 synthetic bundles into the directory a live session watches for
     alerts. A real stall would have been buried.
  2. `match_log.jsonl` — the misfire tests drive real plays through the reveal
     path, appending rows to the dataset the whole project exists to collect.
     30 of 69 rows turned out to be synthetic, indistinguishable from genuine
     ones except by a field that happened to be new that day.

Both were found by noticing the DATA looked wrong, not by anything failing.
Both were fixed one at a time. Neither fix would have caught the next instance,
because the actual defect is not "match_log wasn't redirected" — it is that
nothing asserts the suite is side-effect free.

So this guards the CLASS. Any new test that writes to real project state fails
here, whether or not anyone thought about it.

Deliberately runs the other tests in SUBPROCESSES: an env-var override set by
one test module would otherwise leak into this one through a shared
interpreter and hide exactly what is being measured.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import concurrent.futures
import hashlib
import glob
import os
import subprocess
import sys

# Generous: the slowest legitimate test here runs well under a minute.
SUBPROCESS_TIMEOUT = 300

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(__file__)

# Real state the project depends on. Add to this when a new artefact appears —
# but note the directory scan below catches unlisted files too.
TRACKED_FILES = [
    "match_log.jsonl",
    "progress.json",
    "progress_taylere.json",
    "progress_testing.json",
    "known_ban_roster_learned.json",
    # The graph and the place database are real project state now.
    "world_map.json",
]
# Directories that must not gain entries. `diagnostics/` is watched live during
# a session; `screenshot_log/` is the frame corpus the thresholds came from.
TRACKED_DIRS = ["diagnostics", "state_backups", "screenshot_log", "test_fixtures",
                "places", "world_log"]


def digest(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot():
    # _ROOT, NOT HERE. This said HERE (= tests/), where none of the tracked
    # files or directories exist — so every entry was None before AND after and
    # the guard could not have caught anything. Verified 2026-09-01: all 9
    # entries None. Meanwhile the subprocesses run with cwd=_ROOT and write to
    # the ROOT paths, which is exactly what was supposed to be watched.
    state = {f: digest(os.path.join(_ROOT, f)) for f in TRACKED_FILES}
    for d in TRACKED_DIRS:
        p = os.path.join(_ROOT, d)
        state[f"<dir>{d}"] = (sorted(os.listdir(p)) if os.path.isdir(p) else None)
    return state


before = snapshot()

# WALK, do not glob siblings. This used to collect test_*.py next to itself,
# which was every test while they all sat in tests/. Once they were split into
# tests/routing, tests/minigame, tests/rig and tests/harness, that same line
# found only the two files in harness/ — and this guard would have gone on
# printing "all green" while checking 86 fewer tests. A guard that silently
# stops guarding is the catalogue's commonest shape.
tests = sorted(
    os.path.join(dirpath, f)
    for dirpath, _dirs, files in os.walk(os.path.join(_ROOT, "tests"))
    for f in files
    if f.startswith("test_") and f.endswith(".py")
    and os.path.join(dirpath, f) != os.path.abspath(__file__))
tests = [t for t in tests if t != SELF]

env = dict(os.environ)
env.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
# MUST be passed down. This file runs every other test in a subprocess, and
# BASEBALL_TEST_RUN is what holds the input paths OFF — both the background
# keyboard path and (since 2026-09-01) FIFO button injection. run_tests.sh sets
# it, but this file spawns its own children, so without it the "no side
# effects" guard was itself the one thing running the suite in the mode that
# drives the live console. It reached the FIFO before this was caught.
env["BASEBALL_TEST_RUN"] = "1"
# Deliberately NOT setting BASEBALL_MATCH_LOG / BASEBALL_DIAGNOSTICS_DIR here.
# Each test must redirect its own writes; setting the overrides from this side
# would mask a test that forgot to, which is the whole failure being guarded.
# Return codes are CHECKED, not discarded. QA_VACUOUS demonstrated this file
# passing while reporting "15 test file(s) ran" with all 15 replaced by a bare
# `raise SystemExit` — a crashed test writes to nothing, so the side-effect diff
# was trivially clean and the guard reported success on a suite that never ran.
#
# A file that fails here is not this test's business to diagnose (run_tests.sh
# reports that), but a file that could not RUN AT ALL means its side effects
# were never exercised, so this guard proved nothing about it.
_ran, _crashed = 0, []


def _run_one(t):
    # TIMEOUT IS MANDATORY. Without it a hung test blocks this file forever and
    # burns a full CPU core silently: found 2026-09-02, test_input_timing.py had
    # been spinning for 1 day 7 hours (1867 minutes of CPU) from a previous
    # session's code, held open by this very function, slowing the machine and
    # the game stream with it.
    try:
        r = subprocess.run([sys.executable, t], cwd=_ROOT,
                           env=env, capture_output=True, text=True,
                           timeout=SUBPROCESS_TIMEOUT)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(
            args=[t], returncode=1, stdout="",
            stderr=f"TIMED OUT after {SUBPROCESS_TIMEOUT}s — killed. A test that "
                   f"never finishes is a hang, not a slow test.")
    return t, r


# PARALLEL. This file re-runs the entire suite, so it costs about as much as
# every other test combined — measured 2026-08-26 at 117.3s of a 233.3s suite,
# i.e. HALF the total, and preflight blocks a live run on all of it.
#
# Safe to parallelise: each test already runs in its own subprocess with its
# own env overrides (that isolation is the point of this file), and the
# before/after snapshots bracket the whole batch rather than each test, so
# interleaved writes are caught exactly as well. Order was never meaningful —
# `tests` is just sorted by filename.
with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 4))) as _ex:
    for t, r in _ex.map(_run_one, tests):
        _ran += 1
        # Distinguish "asserted and failed" (still exercised its writes) from
        # "could not start" — an import error, missing fixture, bare SystemExit.
        # `raise SystemExit(...)` exits 0, so a returncode-only check let a
        # suite where NOTHING RAN pass clean — the exact regression the
        # comment above claims to have fixed (QA, 2026-08-26: demonstrated
        # with 15 stubs). A test that produced no stdout did not run.
        # STDOUT OR STDERR. `unittest` writes its entire report to STDERR, so
        # test_map_admit.py — the one unittest-style file in the suite — ran
        # fine (returncode 0, "Ran 5 tests ... OK") and was reported as
        # "produced no output and exited non-zero". Checking stdout alone made
        # this guard call a PASSING test a crash, which is the inverse of the
        # failure it exists to catch and cost a real diagnosis to find.
        _spoke = r.stdout.strip() or r.stderr.strip()
        if not _spoke or (r.returncode != 0 and "FAIL" not in r.stderr):
            _crashed.append((t, (r.stderr.strip().splitlines() or ["no output"])[-1]))

if _crashed:
    for _t, _err in _crashed:
        print(f"FAIL: {_t} produced no output on either stream, or exited "
              f"non-zero ({_err}) — it "
              "never ran, so this guard proved nothing about its side effects")
    raise SystemExit(
        f"{len(_crashed)} test file(s) did not execute; the side-effect check "
        "below is meaningless for them")

after = snapshot()

failures = []
for key in sorted(set(before) | set(after)):
    b, a = before.get(key), after.get(key)
    if b == a:
        continue
    if key.startswith("<dir>"):
        name = key[5:]
        added = sorted(set(a or []) - set(b or []))
        removed = sorted(set(b or []) - set(a or []))
        failures.append(
            f"{name}/ changed during the suite — added {added[:5]}"
            f"{'...' if len(added) > 5 else ''}, removed {removed[:5]}"
            f"{'...' if len(removed) > 5 else ''}. A test is writing to real "
            f"project state; redirect it (see BASEBALL_DIAGNOSTICS_DIR / "
            f"BASEBALL_MATCH_LOG for the pattern).")
    elif b is None:
        failures.append(f"{key} was CREATED by the suite — tests must not "
                        "create real project data files")
    elif a is None:
        failures.append(f"{key} was DELETED by the suite — tests must never "
                        "remove real project data")
    else:
        failures.append(
            f"{key} was MODIFIED by the suite. This is how 30 synthetic rows "
            f"got into match_log.jsonl. Redirect the write with an env var and "
            f"point the test at a temp path.")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} side-effect failure(s)")

print(f"OK: {_ran} test file(s) executed (return codes checked) without "
      f"touching any of "
      f"{len(TRACKED_FILES)} tracked files or {len(TRACKED_DIRS)} tracked "
      f"directories")
