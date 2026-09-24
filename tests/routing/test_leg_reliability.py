"""Speed must follow PROVEN reliability, and fall away when it lapses.

Three more things pinned here (2026-09-07), because they stand between the
module and SPEED_FROM_RELIABILITY ever being switched on (CLAUDE.md OPEN-6):

  1. STORE is resolved at CALL time. `def rate(a, b, path=STORE)` bound the
     import-time string, so redirecting `leg_reliability.STORE` — the only way
     to give an A/B arm its own record — silently did nothing. The redirect
     checks below FAIL on that code, and are gated so that failing cannot write
     the real project-root store.
  2. THE CLIFF is pinned in literals: 12/12 -> 3.0, 11/12 -> 1.0. A check that
     asserts against lr.FAST_SCALE or lr.MIN_RATE rises with the constant and
     passes forever (CLAUDE.md 10.11); moving the cliff must be an edit HERE.
  3. A corrupt store is quarantined AND said, never silently "no history", and
     never fatal. The atomic write is observed (temp + one os.replace), a
     crash-orphaned temp is survived, and a dying write WARNS before it
     propagates — graph_walk swallows that exception with `except Exception:
     pass`, so the warning is the only trace a lost record leaves.

test_reliability_store_durability.py pins the neighbouring facts (truncated
store visible, write goes only to the temp path, a dying write propagates and
leaves the original intact). Nothing here contradicts it; it is the file to
read for WHY the raise stays.
"""
import atexit
import contextlib
import hashlib
import io
import json
import os
import os as _os
import shutil
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
    d = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    return os.path.join(d, "rel.json")


def load_or_none(path):
    """Never let a check ABORT the run. A mutant that leaves the record
    unparseable must produce a clean FAIL, not a traceback that hides every
    check after it."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:                                             # noqa: BLE001
        return None


def digest(path):
    if not os.path.exists(path):
        return None
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


_tmpdir = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _tmpdir, ignore_errors=True)
tmp = os.path.join(_tmpdir, "rel.json")

# Unknown ground is slow. This is the default and the safe one.
check("an unrecorded leg is NOT sped up",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# A perfect but SHORT record is not enough — n=3 has no power here.
for _ in range(3):
    lr.record("a", "b", True, tmp)
check("3 perfect attempts do not earn speed (n too small)",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# A long perfect record does.
for _ in range(17):
    lr.record("a", "b", True, tmp)
r, n = lr.rate("a", "b", tmp)
check(f"20/20 earns speed (rate {r:.2f}, n={n})",
      lr.scale_for("a", "b", tmp) == lr.FAST_SCALE)

# A merely-decent leg does not. 0.667 is the best non-perfect leg measured.
for _ in range(14):
    lr.record("c", "d", True, tmp)
for _ in range(7):
    lr.record("c", "d", False, tmp)
r, n = lr.rate("c", "d", tmp)
check(f"a 0.667 leg stays slow (rate {r:.2f}, n={n})",
      lr.scale_for("c", "d", tmp) == lr.NORMAL_SCALE)

# THE POINT: a proven leg that starts failing LOSES its speed on its own.
for _ in range(4):
    lr.record("a", "b", False, tmp)
r, n = lr.rate("a", "b", tmp)
check(f"a leg that starts failing slows itself back down (rate {r:.2f})",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# The bar must sit clear of the best non-perfect leg actually measured.
check("MIN_RATE is well above the best imperfect leg (0.667)",
      lr.MIN_RATE > 0.9)
check("MIN_ATTEMPTS reflects the power analysis (n=3 has power 0.00)",
      lr.MIN_ATTEMPTS >= 10)

# A corrupt record must not stop a run.
open(tmp, "w").write("{ not json")
check("a corrupt record degrades to slow rather than raising",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)


# --- 1. STORE is resolved at CALL time, so a redirect actually redirects ----
# `def rate(a, b, path=STORE)` bound the import-time string into the default,
# so `lr.STORE = other` changed nothing and nothing said so (CLAUDE.md OPEN-6).
# This is the seam an A/B needs to put each arm on its own record.
#
# ON THE OLD CODE THESE CHECKS MUST FAIL WITHOUT WRITING THE REAL STORE. With
# the default still bound, record() aims at the project-root
# leg_reliability.json, which no test may create — and neither harness guard
# tracks that file, so nothing else would notice. So the writer is wrapped in a
# gate that refuses any path outside this test's own tempdir, and the real
# store's state is compared before and after. On the old code the gate fires,
# the checks fail, and the real store is untouched.
real_store = lr.STORE
real_store_before = digest(real_store)
arm_dir = tempfile.mkdtemp()
atexit.register(shutil.rmtree, arm_dir, ignore_errors=True)
arm = os.path.join(arm_dir, "arm_A.json")
written_to = []
real_writer = lr._atomic_write_json


def gated_writer(path, data):
    written_to.append(os.fspath(path))
    if not os.path.abspath(path).startswith(arm_dir + os.sep):
        raise AssertionError(f"refusing to write outside the tempdir: {path}")
    return real_writer(path, data)


lr._atomic_write_json = gated_writer
lr.STORE = arm
try:
    try:
        lr.record("a", "b", True)       # NO path: the redirect must carry it
        redirect_err = None
    except AssertionError as exc:
        redirect_err = exc
    check(f"record() with no path writes the REDIRECTED store ({redirect_err})",
          redirect_err is None and written_to == [arm])
    check("the redirected store exists on disk holding the attempt",
          load_or_none(arm) == {"a->b": {"attempts": 1, "arrived": 1}})
    # The READ side, independently of the write: plant a record the bound
    # default could not see, and ask each public reader without a path.
    with open(arm, "w") as fh:
        json.dump({"a->b": {"attempts": 12, "arrived": 12}}, fh)
    check("rate() with no path reads the REDIRECTED store",
          lr.rate("a", "b") == (1.0, 12))
    check("scale_for() with no path reads the REDIRECTED store",
          lr.scale_for("a", "b") == 3.0)
    check("report() with no path reads the REDIRECTED store",
          [row[0] for row in lr.report()] == ["a->b"])
finally:
    lr.STORE = real_store
    lr._atomic_write_json = real_writer
check("the real project-root store was neither created nor changed",
      digest(real_store) == real_store_before)
check("STORE is restored for the checks that follow", lr.STORE == real_store)


# --- 2. THE CLIFF, pinned in LITERALS ---------------------------------------
# CLAUDE.md OPEN-6: 12 recorded arrivals make scale_for return 3.0 and ONE
# failure returns it to 1.0 (11/12 = 0.917 < 0.95). Every number below is a
# literal, deliberately not lr.FAST_SCALE / lr.MIN_RATE / lr.MIN_ATTEMPTS — a
# check that asserts against the constant it guards rises with it and passes
# forever (CLAUDE.md 10.11). Moving the cliff is allowed; it must be a
# deliberate edit here as well as there.
def leg_with(arrived, failed):
    p = fresh()
    for _ in range(arrived):
        lr.record("p", "q", True, p)
    for _ in range(failed):
        lr.record("p", "q", False, p)
    return lr.scale_for("p", "q", p)


check("12/12 earns exactly 3.0", leg_with(12, 0) == 3.0)
check("11/12 (ONE failure) is exactly 1.0 — the cliff", leg_with(11, 1) == 1.0)
check("9/9 is 1.0: the floor is 10 attempts", leg_with(9, 0) == 1.0)
check("10/10 is 3.0: the first n that can earn speed", leg_with(10, 0) == 3.0)
# The shape of the cliff worth knowing before the flag goes on: a single
# failure is fatal until n = 20, where 19/20 = 0.95 first clears the bar.
check("18/19 is 1.0: one failure is fatal below n=20", leg_with(18, 1) == 1.0)
check("19/20 is 3.0: the first n that tolerates ONE failure",
      leg_with(19, 1) == 3.0)


# --- 3a. A CORRUPT STORE IS QUARANTINED AND SAID — never silent, never fatal -
# _load() degrades to {} on purpose (bookkeeping must never stop a walk). What
# it must not do is degrade SILENTLY: {} is also "nothing recorded yet", so a
# leg that had earned 3.0 would drop to 1.0 with nothing in the log to say why.
# _warn prints "WARNING: ..." to stdout because during a run stdout IS the log;
# _quarantine moves the bytes to <store>.corrupt so record()'s read-modify-write
# cannot destroy the only copy of whatever went wrong.
CORRUPT_SHAPES = [
    ("junk bytes", b"{ not json"),
    ("truncated mid-object", b'{"a->b": {"attempts": 12, "arri'),
    ("valid JSON, not an object", b"[1, 2, 3]"),
]
for label, payload in CORRUPT_SHAPES:
    p = fresh()
    open(p, "wb").write(payload)
    # THE READ PATH FIRST, on its own. scale_for is what graph_walk.leg_scale
    # calls, and it never quarantines — so the ONLY trace a corrupt store
    # leaves on a read is _load's warning plus LAST_CORRUPTION. record() below
    # warns twice (once from _load, once from _quarantine), so a check there
    # cannot tell whether the read-side warning still exists.
    lr.LAST_CORRUPTION = "stale from an earlier call"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            read_scale = lr.scale_for("a", "b", p)
            read_raised = None
        except Exception as exc:                                  # noqa: BLE001
            read_scale, read_raised = None, exc
    read_said = buf.getvalue()
    check(f"[{label}] scale_for() does not raise ({read_raised!r})",
          read_raised is None)
    check(f"[{label}] scale_for() degrades to exactly 1.0", read_scale == 1.0)
    check(f"[{label}] the READ flags the corruption (LAST_CORRUPTION set)",
          lr.LAST_CORRUPTION is not None
          and lr.LAST_CORRUPTION != "stale from an earlier call")
    check(f"[{label}] the READ warns, naming the store",
          "WARNING: " in read_said and os.path.basename(p) in read_said)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            got = lr.record("a", "b", True, p)
            raised = None
        except Exception as exc:                                  # noqa: BLE001
            got, raised = None, exc
    said = buf.getvalue()
    check(f"[{label}] record() does not raise ({raised!r})", raised is None)
    check(f"[{label}] the corruption is FLAGGED, not read as 'no history'",
          lr.LAST_CORRUPTION is not None)
    check(f"[{label}] a 'WARNING: ' line names the store",
          "WARNING: " in said and os.path.basename(p) in said)
    check(f"[{label}] the unreadable bytes are kept at <store>.corrupt",
          os.path.exists(p + ".corrupt")
          and open(p + ".corrupt", "rb").read() == payload)
    check(f"[{label}] the store restarts as a valid record holding the attempt",
          load_or_none(p) == {"a->b": {"attempts": 1, "arrived": 1}})
    check(f"[{label}] the attempt is reported back to the caller",
          got == {"attempts": 1, "arrived": 1})

# One malformed ROW quarantines the whole file, but the readable rows must
# SURVIVE into the fresh store — otherwise one bad row costs every other leg
# its record, which is the loss the quarantine exists to prevent.
p = fresh()
open(p, "w").write(json.dumps({"a->b": {"attempts": 12, "arrived": 12},
                               "c->d": {"attempts": "ten"}}))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        lr.record("e", "f", False, p)
        raised = None
    except Exception as exc:                                      # noqa: BLE001
        raised = exc
check(f"a malformed row does not raise out of record() ({raised!r})",
      raised is None)
check("a malformed row is quarantined with the whole file",
      os.path.exists(p + ".corrupt"))
check("the readable rows survive into the fresh store",
      load_or_none(p) == {"a->b": {"attempts": 12, "arrived": 12},
                          "e->f": {"attempts": 1, "arrived": 0}})
check("the proven leg keeps its 3.0 through a quarantine",
      lr.scale_for("a", "b", p) == 3.0)

# A quarantine that CANNOT move the file aside (permissions, a dropped mount)
# must warn and carry on. If _quarantine let the OSError out, the corrupt
# store would end a run through the one function graph_walk calls to note a
# result.
p = fresh()
open(p, "wb").write(b"{ not json")
real_replace = os.replace


def replace_refusing_quarantine(src, dst, *a, **kw):
    if os.fspath(dst).endswith(".corrupt"):
        raise OSError(13, "simulated: cannot move the record aside")
    return real_replace(src, dst, *a, **kw)


os.replace = replace_refusing_quarantine
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        try:
            lr.record("a", "b", True, p)
            raised = None
        except Exception as exc:                                  # noqa: BLE001
            raised = exc
finally:
    os.replace = real_replace
check(f"a quarantine that cannot move the file does not raise ({raised!r})",
      raised is None)
check("... and says it could not preserve the record",
      "WARNING: " in buf.getvalue() and "could not preserve" in buf.getvalue())
check("... and the store is still a valid record afterwards",
      load_or_none(p) == {"a->b": {"attempts": 1, "arrived": 1}})


# --- 3b. ATOMIC WRITE: temp file + ONE os.replace, observed not asserted ----
# The docstring promises temp + rename. Watch the swap itself: at the instant
# os.replace runs, the temp must already hold the COMPLETE new record, and the
# destination must be the store — so a reader sees the whole old file or the
# whole new one and never half of either.
p = fresh()
for _ in range(3):
    lr.record("a", "b", True, p)
seen = []


def spy_replace(src, dst, *a, **kw):
    seen.append((os.fspath(src), os.fspath(dst), load_or_none(src)))
    return real_replace(src, dst, *a, **kw)


os.replace = spy_replace
try:
    lr.record("a", "b", True, p)
finally:
    os.replace = real_replace
check("the swap is exactly ONE os.replace, temp -> store",
      len(seen) == 1 and seen[0][:2] == (p + ".tmp", p))
check("the temp already holds the complete new record at the swap",
      len(seen) == 1 and seen[0][2] == {"a->b": {"attempts": 4, "arrived": 4}})
check("no temp is left behind after a clean write",
      not os.path.exists(p + ".tmp"))

# A CRASH MID-WRITE — SIGKILL, power, a killed subagent — leaves the temp
# behind, because _atomic_write_json's cleanup never runs for that. The orphan
# must not be read as the record, must not block the next write (an exclusive
# "x" open would raise FileExistsError right here), and must be gone after.
p = fresh()
lr.record("a", "b", True, p)
record_before = open(p, "rb").read()
open(p + ".tmp", "wb").write(b'{"a->b": {"attempts": 99, "arri')
check("an orphan temp is not read as the record",
      lr.rate("a", "b", p) == (1.0, 1))
check("the record itself is untouched by the orphan",
      open(p, "rb").read() == record_before)
try:
    lr.record("a", "b", True, p)
    raised = None
except Exception as exc:                                          # noqa: BLE001
    raised = exc
check(f"record() writes through a stale orphan temp without raising "
      f"({raised!r})", raised is None)
check("the record after the orphan is correct",
      load_or_none(p) == {"a->b": {"attempts": 2, "arrived": 2}})
check("the orphan is gone, not left to confuse the next reader",
      not os.path.exists(p + ".tmp"))

# A DYING WRITE MUST SAY SO before it propagates. That it propagates is pinned
# by test_reliability_store_durability.py (a caller must not be told "recorded"
# when it was not). What was missing is the log line: graph_walk's call site is
# `except Exception: pass`, so a swallowed failure with no warning is the
# diagnosis-catalogue shape exactly — an attempt that was never recorded looks
# identical to one that was.
p = fresh()
lr.record("a", "b", True, p)
real_dump = json.dump


def dying_dump(obj, fh, *a, **kw):
    raise OSError("simulated dropped mount")


json.dump = dying_dump
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        try:
            lr.record("a", "b", True, p)
            crashed = None
        except OSError as exc:
            crashed = exc
finally:
    json.dump = real_dump
said = buf.getvalue()
check("a dying write still propagates (the durability test's contract)",
      isinstance(crashed, OSError))
check("a dying write WARNS, naming the store, before it propagates",
      "WARNING: " in said and os.path.basename(p) in said)
check("the warning says the attempt was NOT recorded",
      "NOT recorded" in said)
check("the original record survives the dying write",
      load_or_none(p) == {"a->b": {"attempts": 1, "arrived": 1}})


# WIRING into graph_walk: an explicit override must still win, and bookkeeping
# must never be able to stop a walk.
import graph_walk as gw

old_flag, old_by = gw.SPEED_FROM_RELIABILITY, dict(gw.LEG_SPEED_BY_LEG)
try:
    gw.SPEED_FROM_RELIABILITY = False
    check("with reliability off, an unproven leg is at the global scale",
          gw.leg_scale("x", "y") == gw.LEG_SPEED_SCALE)

    gw.LEG_SPEED_BY_LEG = {("x", "y"): 2.5}
    gw.SPEED_FROM_RELIABILITY = True
    check("an explicit override beats the earned scale",
          gw.leg_scale("x", "y") == 2.5)

    gw.LEG_SPEED_BY_LEG = {}
    check("an unproven leg earns nothing even with reliability on",
          gw.leg_scale("nope", "nowhere") == lr.NORMAL_SCALE)
finally:
    gw.SPEED_FROM_RELIABILITY, gw.LEG_SPEED_BY_LEG = old_flag, old_by

check("both reliability flags ship OFF",
      gw.SPEED_FROM_RELIABILITY is False and gw.RECORD_RELIABILITY is False)

# The last word: nothing above may have touched the real store.
check("the real project-root store is untouched at exit",
      digest(lr.STORE) == real_store_before)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
