"""The reliability record must not be able to LOSE ITSELF QUIETLY.

leg_reliability.record() is a read-modify-write, and it used to be
`open(path, "w")` — truncate first, no lock, no atomic replace. Two failures
follow from that, and _load() swallowed both:

  1. A crash or a dropped mount mid-write leaves an empty or truncated file.
  2. _load() returned {} for it, which is indistinguishable from "nothing
     recorded yet" — so a leg silently lost its earned FAST scale, and the very
     next record() overwrote the evidence.

That is the diagnosis-catalogue shape: the code did nothing, and doing nothing
looked exactly like working. Note that RAISING cannot make it visible, because
graph_walk wraps both call sites in `except Exception` — so what is asserted
here is a WARNING plus LAST_CORRUPTION, not an exception.

The project had already solved this twice (input_controller._save_view_cache,
compass._save_scale_cache, and orchestrator._atomic_write_json). This pins that
leg_reliability now does the same.
"""
import builtins
import contextlib
import io
import json
import os
import os as _os
import sys
import tempfile

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import leg_reliability as lr

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def fresh():
    return os.path.join(tempfile.mkdtemp(), "rel.json")


def load_or_none(path):
    """Never let a check ABORT the run. A mutant that leaves the record
    unparseable must produce a clean FAIL, not a traceback that hides every
    check after it."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:                                             # noqa: BLE001
        return None


def perfect(path, n=20):
    """A record that has EARNED the fast scale, so a loss of it is visible."""
    for _ in range(n):
        lr.record("a", "b", True, path)
    return path


# --- 1. The store is anchored, so the cwd cannot select a different record ---
# It was "leg_reliability.json", resolved against whatever directory the process
# was started in. Same convention as compass._SCALE_CACHE_FILE and
# input_controller._VIEW_CACHE_FILE.
check("STORE is an absolute path, not cwd-relative",
      os.path.isabs(lr.STORE))
check("STORE resolves to the project root regardless of cwd",
      os.path.dirname(lr.STORE) == _ROOT)


# --- 2. A HEALTHY record reports no corruption (the positive control) --------
# Without this, every "corruption was detected" check below could pass simply
# because the flag is always set.
p = perfect(fresh())
check("a healthy 20/20 record earns the fast scale",
      lr.scale_for("a", "b", p) == lr.FAST_SCALE)
check("a healthy record sets no corruption flag",
      lr.LAST_CORRUPTION is None)


# --- 3. A TRUNCATED record is VISIBLE, not silent ---------------------------
good_bytes = open(p, "rb").read()
truncated = good_bytes[:len(good_bytes) // 2]
open(p, "wb").write(truncated)

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    scale = lr.scale_for("a", "b", p)
said = buf.getvalue()

check("a truncated record still degrades to the slow scale (never raises)",
      scale == lr.NORMAL_SCALE)
check("a truncated record SETS the corruption flag",
      lr.LAST_CORRUPTION is not None)
check("a truncated record WARNS, naming the file",
      "WARNING" in said and os.path.basename(p) in said)


# --- 4. record() PRESERVES what it could not read ---------------------------
# A plain write over an unreadable record destroys the only copy of whatever
# went wrong AND resets every leg to zero in the same stroke.
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    lr.record("a", "b", True, p)

check("the unreadable record is kept aside, not overwritten",
      os.path.exists(p + ".corrupt"))
check("the kept copy is the corrupt bytes themselves",
      os.path.exists(p + ".corrupt")
      and open(p + ".corrupt", "rb").read() == truncated)
check("the replacement record is valid JSON",
      load_or_none(p) == {"a->b": {"attempts": 1, "arrived": 1}})


# --- 5. Valid JSON of the WRONG SHAPE must not raise out of a walk ----------
# rate() and report() index e["attempts"] directly, so one malformed row used to
# raise a KeyError out of a module that promises never to end a run.
p = fresh()
open(p, "w").write(json.dumps({"a->b": {"attempts": 10}}))       # no "arrived"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        r = lr.rate("a", "b", p)
        s = lr.scale_for("a", "b", p)
        lr.report(p)
        raised = None
    except Exception as exc:                                      # noqa: BLE001
        r, s, raised = None, None, exc
check(f"a malformed entry does not raise ({raised!r})", raised is None)
check("a malformed entry is dropped, not half-read", r == (None, 0))
check("a malformed entry warns", "WARNING" in buf.getvalue())

# arrived > attempts is a rate above 1.0, which would EARN the fast scale off a
# row that cannot be true. Speed costs repeatability, so it must not be granted
# by nonsense.
p = fresh()
open(p, "w").write(json.dumps({"a->b": {"attempts": 10, "arrived": 30}}))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    impossible_rate = lr.rate("a", "b", p)
    impossible_scale = lr.scale_for("a", "b", p)
check("an impossible entry (30/10) is dropped",
      impossible_rate == (None, 0))
check("an impossible entry cannot earn the fast scale",
      impossible_scale == lr.NORMAL_SCALE)


# --- 6. ATOMIC: the real file is never opened for writing -------------------
# The whole point of write-then-rename. If the store itself is opened "w", a
# reader can observe it truncated no matter what happens afterwards.
p = perfect(fresh(), n=3)
opened_w = []
real_open = builtins.open


def spy_open(file, mode="r", *a, **kw):
    if "w" in mode or "a" in mode or "+" in mode:
        opened_w.append(os.fspath(file))
    return real_open(file, mode, *a, **kw)


builtins.open = spy_open
try:
    lr.record("a", "b", True, p)
finally:
    builtins.open = real_open

# Positive control FIRST: if nothing was written at all, "p not in opened_w"
# would pass vacuously and this test would guard nothing.
check(f"a write actually happened (paths: {[os.path.basename(x) for x in opened_w]})",
      len(opened_w) == 1)
check("the write went to the TEMP path",
      opened_w == [p + ".tmp"])
check("the real record was NEVER opened for writing",
      p not in opened_w)


# --- 7. ATOMIC: a write that dies partway leaves the ORIGINAL intact --------
# This is the failure the finding describes — a crash or a dropped mount in the
# middle of the write. Under the old truncate-first code the record was already
# destroyed by the time json.dump was called at all.
p = perfect(fresh(), n=5)
before_bytes = open(p, "rb").read()
real_dump = json.dump


def dying_dump(obj, fh, *a, **kw):
    fh.write('{"a->b": {"attempts": 5, "arri')    # a genuinely partial write
    raise OSError("simulated dropped mount")


json.dump = dying_dump
try:
    lr.record("a", "b", True, p)
    crashed = None
except OSError as exc:
    crashed = exc
finally:
    json.dump = real_dump

check(f"a dying write propagates rather than reporting success ({crashed!r})",
      isinstance(crashed, OSError))
check("the original record survives a write that died partway",
      load_or_none(p) is not None
      and open(p, "rb").read() == before_bytes)
check("the original record still parses after a dying write",
      load_or_none(p) == {"a->b": {"attempts": 5, "arrived": 5}})
check("the leg keeps the speed it had earned",
      lr.rate("a", "b", p) == (1.0, 5))
check("no orphan .tmp is left beside the record",
      not os.path.exists(p + ".tmp"))

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
