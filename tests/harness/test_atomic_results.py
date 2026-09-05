"""An interrupted result write must not destroy the results already on disk.

WHY THIS EXISTS. Every overnight A/B saved with

    json.dump(res, open(path, "w"), indent=2)

`open(path, "w")` TRUNCATES before json writes a single byte, and json.dump
streams chunks to the handle. So for the whole duration of the dump the result
file is empty or half-written. A Ctrl-C, a crash, or a failing disk in that
window loses the entire run — up to two hours of console time, and CLAUDE.md
records that route performance has a large session-to-session component, so a
lost run cannot simply be re-run and compared against the other arm.

That defect is INVISIBLE in normal use: an uninterrupted truncate-then-write and
an atomic write produce byte-identical files. The only way to see it is to
interrupt a write on purpose, which is what this test does.

WHAT THIS TEST DOES NOT COVER, said out loud so nobody assumes it does: the
`fsync` and the missing fsync of the PARENT DIRECTORY. Both matter only across
a power cut or a kernel panic, and neither is observable from a test process —
removing the fsync leaves every assertion below green. The threat this file
actually guards is the one that has happened here: a Ctrl-C, or an exception,
part way through a dump. (`orchestrator._atomic_write_json` does not fsync the
directory either, so this is the same guarantee progress.json already runs on.)

THE POSITIVE CONTROL AT THE BOTTOM IS LOAD-BEARING. It runs the SAME payload
through the OLD `json.dump(open(path, "w"))` and asserts that it really does
destroy the file. Without it, a payload that failed to interrupt anything would
make every assertion above pass vacuously — a test that is green because it
never exercised the thing it guards.
"""
import json
import os
import shutil
import sys
import tempfile

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


def scratch(where):
    """Every working file save_result may create. Checking only for `.tmp`
    would let the archive copy's temp leak unnoticed."""
    return sorted(f for f in os.listdir(where)
                  if f.endswith(".tmp") or f.endswith(".keep"))


TMP = tempfile.mkdtemp(prefix="atomic_results_")

# A finished run: 10 trials that took an hour of console time.
FINISHED = {"route": ["portrait_room", "bar_pool_room", "bar_jukebox"],
            "runs": [{"arm": "attempts_9", "arrived": True, "depth": 3}] * 10}


class Interrupted(dict):
    """A payload that dies PART WAY THROUGH being serialised.

    json.dump with indent=2 uses the pure-Python encoder, which iterates
    `dct.items()` and writes each chunk to the handle as it goes — so by the
    time this raises, real bytes have already been written. That is exactly a
    Ctrl-C landing mid-dump, and it is the only way to observe the difference
    between a truncating write and an atomic one.

    While it is part way through it also LOOKS AT THE DIRECTORY, so the test can
    see where the half-written bytes are actually going.
    """

    def __init__(self, seen, where):
        dict.__init__(self, {"runs": [1, 2, 3, 4, 5, 6, 7, 8]})
        self.seen, self.where = seen, where

    def items(self):
        for k, v in dict.items(self):
            yield k, v
        self.seen.extend(sorted(os.listdir(self.where)))
        raise KeyboardInterrupt("Ctrl-C, mid-write")


# --- the guarantee: an interrupted save leaves the old results intact --------
path = os.path.join(TMP, "ab_attempts.json")
h.save_result(path, FINISHED)
before = open(path).read()

seen = []
raised = None
try:
    h.save_result(path, Interrupted(seen, TMP))
except BaseException as e:          # KeyboardInterrupt is not an Exception
    raised = e

check("an interrupted save re-raises rather than swallowing the interrupt",
      isinstance(raised, KeyboardInterrupt))
check("the finished run's file is byte-identical afterwards",
      open(path).read() == before)
check("and it still parses as the completed run",
      json.load(open(path)) == FINISHED)
check(f"no orphan working file is left beside the result ({scratch(TMP)})",
      not scratch(TMP))

# --- the half-written bytes went to a PER-PROCESS temp, not the result -------
#
# A shared "<path>.tmp" is not safe against two runs of one script: writer A
# truncates the temp while B is mid-dump, and B then renames a spliced file into
# place — atomic, and wrong. `seen` is the directory as it looked mid-write.
tmps = [f for f in seen if f.endswith(".tmp")]
check(f"the write in progress was in a temp file ({tmps})", len(tmps) == 1)
check("whose name carries this process's pid, so two concurrent runs "
      "cannot share it",
      bool(tmps) and str(os.getpid()) in tmps[0])
check("and the result file itself was untouched while that was happening",
      os.path.basename(path) in seen)

# --- a successful save still writes what it was given ------------------------
LATER = {"runs": [{"arm": "attempts_3", "arrived": False}]}
h.save_result(path, LATER)
check("a normal save writes the object", json.load(open(path)) == LATER)
check(f"still no orphan working file after a normal save ({scratch(TMP)})",
      not scratch(TMP))

# --- the archive is a COPY: the FIRST save of a run is interruptible too -----
#
# A mutation test caught the rename version of the archive. It moved the
# finished run to <path>.prev and THEN began writing, so an interrupt during
# that first write left NO result file — the very failure this function exists
# to prevent, merely relocated. The first save of a run is the dangerous one,
# because it is the only one that archives; interrupt exactly that.
fresh = os.path.join(TMP, "fresh_run.json")
h.save_result(fresh, FINISHED)
h._ROTATED.discard(os.path.abspath(fresh))      # pretend a NEW run starts here
try:
    h.save_result(fresh, Interrupted([], TMP))
except KeyboardInterrupt:
    pass
check("interrupting a new run's FIRST save leaves the old results in place",
      os.path.exists(fresh) and json.load(open(fresh)) == FINISHED)
check("and the archive copy is there as well",
      os.path.exists(fresh + ".prev")
      and json.load(open(fresh + ".prev")) == FINISHED)
check(f"with nothing left over ({scratch(TMP)})", not scratch(TMP))

# --- a NEW run keeps the old run's file once, next to it ---------------------
#
# Starting a run used to overwrite a finished one's results on trial 1.
# overnight/ab_leg_tolerance_run1.json is a copy somebody took by hand to stop
# exactly that. Rotation is per-process, so a long run's own repeated saves do
# not keep rolling the archive away.
rot = os.path.join(TMP, "rotate.json")
h.save_result(rot, FINISHED)
h._ROTATED.discard(os.path.abspath(rot))        # pretend this is a fresh run
h.save_result(rot, LATER)
check("a new run's first save keeps the previous run as <path>.prev",
      os.path.exists(rot + ".prev")
      and json.load(open(rot + ".prev")) == FINISHED)
check("and the new run's own later saves do NOT roll it away again",
      (h.save_result(rot, {"runs": []}) or True)
      and json.load(open(rot + ".prev")) == FINISHED)

# --- rotation must never be able to end a two-hour run -----------------------
#
# Bookkeeping is not the measurement. If the archive copy cannot be made, the
# run must still record its trial — so make the rotation impossible (a
# DIRECTORY sitting where <path>.prev goes) and require the save to land anyway.
blocked = os.path.join(TMP, "blocked.json")
h.save_result(blocked, FINISHED)
h._ROTATED.discard(os.path.abspath(blocked))
os.makedirs(blocked + ".prev")
saved = True
try:
    h.save_result(blocked, LATER)
except BaseException:
    saved = False
check("a rotation that cannot happen does not stop the run recording", saved)
check("and the new result still landed", json.load(open(blocked)) == LATER)

locked = os.path.join(TMP, "nested", "deep.json")
os.makedirs(os.path.dirname(locked))
h.save_result(locked, FINISHED)
h._ROTATED.discard(os.path.abspath(locked))
os.chmod(os.path.dirname(locked), 0o500)        # rename will be denied
try:
    h.save_result(locked, LATER)
    ok = False                                  # write should fail loudly...
except OSError:
    ok = True
finally:
    os.chmod(os.path.dirname(locked), 0o700)
check("a write that genuinely cannot happen raises, it is not swallowed", ok)
check("and the unrotatable file was left intact, not destroyed",
      json.load(open(locked)) == FINISHED)

# --- POSITIVE CONTROL --------------------------------------------------------
#
# Prove the payload above really does interrupt a write mid-stream, by running
# it through the code this replaced. If this check fails, every assertion above
# was vacuous and green for the wrong reason.
old = os.path.join(TMP, "old_style.json")
with open(old, "w") as fh:
    json.dump(FINISHED, fh, indent=2)
try:
    json.dump(Interrupted([], TMP), open(old, "w"), indent=2)
except KeyboardInterrupt:
    pass
destroyed = False
try:
    destroyed = json.load(open(old)) != FINISHED
except ValueError:
    destroyed = True
check("POSITIVE CONTROL: the old json.dump(open(path,'w')) really does "
      "destroy the finished run with this same payload", destroyed)

# --- every overnight script writes results through save_result ---------------
#
# The whole point is that this cannot be re-copied. A script reintroducing
# json.dump onto a result path gets the old defect back silently.
import glob
offenders = []
for f in sorted(glob.glob(os.path.join(_ROOT, "overnight", "*.py"))):
    if os.path.basename(f) == "_harness.py":
        continue
    for i, line in enumerate(open(f), 1):
        if "json.dump(" in line and not line.lstrip().startswith("#"):
            offenders.append(f"{os.path.basename(f)}:{i}")
check(f"no overnight script writes a result with json.dump "
      f"({offenders or 'none'})", not offenders)

# Nothing save_result created for its own use may outlive the calls above —
# including the archive copy's temp, on the paths where the archive FAILED.
check(f"no working file survived the whole test ({scratch(TMP)})",
      not scratch(TMP))

shutil.rmtree(TMP, ignore_errors=True)
print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
