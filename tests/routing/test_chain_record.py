"""chain_record.record() must never lose a frame it has already written.

The whole point of the module is that a chain survives being interrupted, so
these checks are about DURABILITY and ORDER, not about pretty output:

  * N ticks -> N lines and N jpegs, and the jpeg is the frame that was captured
  * a second call APPENDS and CONTINUES the numbering (two calls, one chain)
  * a capture that raises on tick k leaves k-1 complete records on disk
  * every line carries exactly the agreed fields, with the LIVE heading stored
    as-is including its abstentions
  * the heading reader is handed THE IN-MEMORY FRAME, never the saved JPEG
  * a stick axis is always a real number, so the chain stays loadable
  * importing the module does not so much as import the FIFO writer

WHY THE FIELD SET IS PINNED AS LITERALS. `set(rec) == chain_record.FIELDS`
would rise with the constant it is guarding and pass forever (CLAUDE.md 10.11).
The names are written out here; changing the format must be an edit in this
file too.
"""
import ast
import hashlib
import json
import os
import sys
import atexit
import shutil
import tempfile

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

# BEFORE any import that might reach analog_replay: its FIFO path is read at
# import time, so pointing it somewhere harmless afterwards would prove nothing.
_fifo_dir = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _fifo_dir, ignore_errors=True)
_FIFO = os.path.join(_fifo_dir, "fifo_that_must_stay_absent")
os.environ["CHIAKI_INJECT_INPUT"] = _FIFO

import numpy as np
from PIL import Image

import chain_record as cr

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def fresh():
    d = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    return os.path.join(d, "chain")


def lines(directory):
    """Parsed meta lines, never raising: a mutant that corrupts the file must
    produce clean FAILs, not a traceback that hides every check after it."""
    out = []
    try:
        with open(cr.meta_path(directory)) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:                              # noqa: BLE001
                        out.append({"UNPARSEABLE": line})
    except FileNotFoundError:
        pass
    return out


def jpegs(directory):
    try:
        return sorted(f for f in os.listdir(directory) if f.endswith(".jpg"))
    except FileNotFoundError:
        return []


def after(n):
    """A stop_fn that counts its OWN calls.

    It must never ask the file how far it has got. The first version did
    (`len(lines(d)) >= N`), and under the truncation mutant the file stops
    growing, so the loop ran FOREVER: the mutant hung the test instead of
    failing it, and a hang reports nothing. That is CLAUDE.md 10's "a loop
    bound that cannot be reached", planted by the test itself.
    """
    box = {"n": 0}

    def stop(img):
        box["n"] += 1
        return box["n"] >= n

    return stop


def frame(seed, w=32, h=24):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)


class Stub:
    """A capture that hands out known frames, and can be told to blow up."""

    def __init__(self, raise_on=None):
        self.n, self.raise_on, self.last = 0, raise_on, None

    def __call__(self):
        self.n += 1
        if self.raise_on is not None and self.n == self.raise_on:
            raise RuntimeError("stream died")
        self.last = frame(self.n)
        return self.last


# --- 1. import-time behaviour ----------------------------------------------
#
# The module is imported at the top of this file. Nothing below it has run yet,
# so these say what IMPORTING chain_record did on its own.

check("importing chain_record does not import the FIFO writer",
      "analog_replay" not in sys.modules)
check("importing chain_record writes no FIFO", not os.path.exists(_FIFO))

src = open(os.path.join(_ROOT, "chain_record.py")).read()
tree = ast.parse(src)


def _is_environ(node):
    """`os.environ` or a bare `environ`."""
    return ((isinstance(node, ast.Attribute) and node.attr == "environ")
            or (isinstance(node, ast.Name) and node.id == "environ"))


def _env_writes(stmts):
    """Every `os.environ[...] = ...`, `os.environ.setdefault/update(...)` and
    `os.putenv(...)` reachable from these statements.

    CLAUDE.md §5: `tools/prompt_ocr_ab.py` set BASEBALL_TEST_RUN at module
    level for its own offline run, `overnight/prompt_zone.py` imported it after
    walking a leg, and from that import every stick send in a LIVE harness was
    dropped silently -- fifty readings of a camera that never turned. The
    project's AST scanner covers tools/ and overnight/; chain_record.py is at
    the root, so it is covered here.
    """
    bad = []
    for stmt in stmts:
        for sub in ast.walk(stmt):
            if (isinstance(sub, ast.Subscript) and isinstance(sub.ctx, ast.Store)
                    and _is_environ(sub.value)):
                bad.append("environ[...] = ...")
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if (sub.func.attr in ("setdefault", "update", "pop")
                        and _is_environ(sub.func.value)):
                    bad.append("environ." + sub.func.attr)
                if sub.func.attr in ("putenv", "unsetenv"):
                    bad.append("os." + sub.func.attr)
    return bad


# The detector must be able to fire, or "no writes found" means nothing.
check("the env-write detector fires on a real module-level write",
      _env_writes(ast.parse(
          "import os\nos.environ['BASEBALL_TEST_RUN'] = '1'\n").body) != [])
check("...and on os.environ.setdefault",
      _env_writes(ast.parse("os.environ.setdefault('X', '1')\n").body) != [])

_import_time = [s_ for s_ in tree.body
                if not isinstance(s_, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef))]
check("chain_record sets no environment variable at IMPORT time",
      _env_writes(_import_time) == [])
check("chain_record never assigns BASEBALL_TEST_RUN anywhere",
      "BASEBALL_TEST_RUN\"] =" not in src
      and "BASEBALL_TEST_RUN'] =" not in src)
check("main() is guarded behind __main__",
      "if __name__ ==" in src and "main()" in src)

# --- 1b. the console gate: BOTH driver flags refuse under the test flag -----
#
# `_refuse_if_test_run()` is the only thing standing between this suite and the
# console. Under BASEBALL_TEST_RUN every downstream guard is vacuous at once --
# `analog_replay.send` discards stick commands silently (CLAUDE.md §5) and
# `console_lock` moves to a per-pid path, so the lock that stops two things
# driving at once locks nothing -- and a recording taken in that state is a
# picture of a character that never moved. CLAUDE.md 10.1's whole catalogue is
# guards that could not fire; an untested one on the file's only path to the
# console is that shape exactly.
#
# WHY A TRIPWIRE IMPORTER AND NOT JUST "did it raise SystemExit". Two reasons.
# (a) It makes the assertion stronger: the refusal must come BEFORE any live
# import, not merely somewhere. (b) It makes the MUTANT safe. Delete the guard
# and `main("--executor")` walks straight into `_drive_executor`, whose first
# statement is `import console_lock`, and then it acquires the console lock,
# reloads the save and walks the route -- from inside the offline suite. With
# this installed that import raises instead, so the mutant fails in
# milliseconds and touches nothing.
#
# It must run HERE, before `import chain` below: chain.Chain.load imports
# `places` (and places imports compass), so from that point the live modules
# are in sys.modules and an import inside main() would be served from the cache
# without the tripwire ever being consulted.


class Tripwire:
    """A `sys.meta_path` finder that refuses the live modules and remembers
    every name that was asked for."""

    LIVE = ("console_lock", "compass", "graph_walk", "reset_env",
            "table_prompt", "worldmap", "analog_replay", "record_drive")

    def __init__(self):
        self.asked = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.LIVE:
            self.asked.append(fullname)
            raise ImportError(f"tripwire refused {fullname}")
        return None                     # everything else: the usual finders


# ANTI-VACUITY. sys.modules is consulted before sys.meta_path, so a live module
# already imported would make the tripwire unreachable and the whole section
# would pass by not being able to see anything.
check("no live module is loaded yet, so the tripwire below can actually fire",
      [m for m in Tripwire.LIVE if m in sys.modules] == [])

_trip = Tripwire()
_gate = {}
sys.meta_path.insert(0, _trip)
try:
    for _flag in ("--executor", "--user"):
        try:
            _gate[_flag] = ("RETURNED", cr.main([_flag]))
        except BaseException as _exc:                               # noqa: BLE001
            _gate[_flag] = ("RAISED", _exc)
finally:
    sys.meta_path.remove(_trip)

for _flag in ("--executor", "--user"):
    _how, _what = _gate[_flag]
    check(f"{_flag} refuses to drive while BASEBALL_TEST_RUN is set",
          _how == "RAISED" and isinstance(_what, SystemExit)
          and "BASEBALL_TEST_RUN" in str(_what))

# The strong half: not "it refused eventually" but "it refused before it had
# imported anything that can reach the console".
check("...and the refusal comes BEFORE any live import is even attempted",
      _trip.asked == [])
check("...so no live module was loaded by either driver flag",
      [m for m in Tripwire.LIVE if m in sys.modules] == [])

# The control: the tripwire is a real barrier, not a no-op that would let a
# missing guard through unnoticed.
sys.meta_path.insert(0, _trip)
try:
    _blocked = None
    try:
        import console_lock                                          # noqa: F401
    except BaseException as _exc:                                    # noqa: BLE001
        _blocked = _exc
finally:
    sys.meta_path.remove(_trip)
    _trip.asked.clear()
check("control: the tripwire really does block a live import",
      isinstance(_blocked, ImportError))

# --- 2. N ticks -> N lines, N frames ---------------------------------------

def sig(img):
    """A number the JPEG CANNOT preserve.

    Pixel std of uniform noise: 72.5-74.4 in memory, 51.7-53.1 after a
    quality-88 round trip -- a gap of ~21 over five seeds, measured. The mean
    would NOT do (it moves by 0.01-0.15), which is why the reader's answer is
    keyed to std and not to something a lossy encoder happens to preserve.
    """
    return round(float(np.asarray(img).astype(float).std()), 4)


N = 5
ABSTAIN = {1, 3}                                # a live reader abstains
d = fresh()
cap = Stub()
seen = {"i": 0, "same_object": [], "read": []}


def heading_fn(img):
    """Answers FROM THE FRAME IT IS GIVEN.

    THIS IS THE POINT OF THE STUB. The previous version returned a canned list
    and ignored its argument, so it proved only that a return value is passed
    through -- a module that opened the saved JPEG and read the compass off
    THAT passed the whole suite. CLAUDE.md: a re-encoded frame made
    read_bearing answer 90 degrees differently, confidently. So the answer here
    is a function of the pixels, and the expected values below are computed
    from the frames capture() actually handed out.
    """
    seen["same_object"].append(img is cap.last)
    seen["read"].append(sig(img))
    v = None if (seen["i"] % N) in ABSTAIN else sig(img)
    seen["i"] += 1
    return v


HEADINGS = [None if i in ABSTAIN else sig(frame(i + 1)) for i in range(N)]

n1 = cr.record(d, cap, heading_fn, lambda: (0.0, -0.45), period=0.0,
               stop_fn=after(N))

recs = lines(d)
check(f"{N} ticks wrote {N} meta lines", len(recs) == N and n1 == N)
check(f"{N} ticks wrote {N} jpegs", jpegs(d) == [f"{i:04d}.jpg" for i in range(N)])
check("indices are 0..N-1 in order",
      [r.get("index") for r in recs] == list(range(N)))

EXPECT = {"index", "t", "heading", "cam", "lx", "ly", "note", "path"}
check("every line carries exactly the agreed fields",
      all(set(r) == EXPECT for r in recs))
check("chain_record.FIELDS advertises that same set",
      set(cr.FIELDS) == EXPECT)
check("the LIVE heading is stored as read, abstentions included",
      [r.get("heading") for r in recs] == HEADINGS)

# THE HEADING COMES OFF THE IN-MEMORY FRAME, NOT THE JPEG BESIDE IT.
# CLAUDE.md: re-encoding a frame changed read_bearing's answer by exactly 90
# degrees -- cardinal letter confusion, a CONFIDENT wrong answer. A recorder
# that read the heading off the file it had just written would look perfect
# (right count, right names, plausible numbers) and be wrong that way.
check("the compass reader is handed the very frame capture() returned",
      seen["same_object"] == [True] * N and len(seen["read"]) == N)
_from_jpeg = [sig(Image.open(os.path.join(d, f"{i:04d}.jpg")).convert("RGB"))
              for i in range(N)]
check("...and the saved JPEG would have answered differently (control: the "
      "check above cannot pass by the two being equal)",
      all(abs(a_ - b_) > 5.0 for a_, b_ in zip(seen["read"], _from_jpeg)))
check("no stored heading equals what the JPEG would have said",
      all(r.get("heading") not in _from_jpeg for r in recs))
check("the stick sample is stored",
      all(r.get("lx") == 0.0 and r.get("ly") == -0.45 for r in recs))
check("cam is null when the driver supplies none",
      all(r.get("cam") is None for r in recs))
check("t is a float and does not go backwards",
      all(isinstance(r.get("t"), float) for r in recs)
      and [r["t"] for r in recs] == sorted(r["t"] for r in recs))
check("note is empty when nothing went wrong",
      all(r.get("note") == "" for r in recs))
check("path names the frame beside the line",
      all(r.get("path") == f"{r['index']:04d}.jpg" for r in recs))

# THE JPEG IS THE FRAME THAT WAS CAPTURED, not a placeholder. A recorder that
# writes the right number of correctly-named files of the wrong moment is this
# project's own catalogued failure ("four jpegs, correctly written, of the
# wrong moment").
im0 = Image.open(os.path.join(d, "0000.jpg"))
check("the jpeg has the captured frame's geometry", im0.size == (32, 24))
a = np.asarray(im0.convert("RGB")).astype(int)
b = frame(1).astype(int)
check("the jpeg IS the first captured frame (not a later one)",
      abs(a - b).mean() < abs(a - frame(2).astype(int)).mean())

# --- 3. a second call appends and continues the numbering ------------------

before = open(cr.meta_path(d), "rb").read()
n2 = cr.record(d, Stub(), lambda img: 1.0, lambda: (None, None), period=0.0,
               stop_fn=after(3))
recs = lines(d)
check("the second call appended, it did not truncate",
      open(cr.meta_path(d), "rb").read().startswith(before))
check("two calls give one continuous chain",
      [r.get("index") for r in recs] == list(range(N + 3)) and n2 == 3)
check("the second call's frames sit beside the first's",
      jpegs(d) == [f"{i:04d}.jpg" for i in range(N + 3)])
check("the first call's lines are unchanged",
      lines(d)[:N] == json.loads(json.dumps([json.loads(l) for l in
                                             before.decode().splitlines()])))

# next_index() is the rule the append relies on; pin it directly too.
check("next_index() reads one past the last recorded line",
      cr.next_index(d) == N + 3)
check("next_index() of an empty directory is 0", cr.next_index(fresh()) == 0)

# A torn final line (a crash mid-write) must not restart the numbering.
torn = fresh()
os.makedirs(torn)
with open(cr.meta_path(torn), "a") as fh:
    fh.write(json.dumps({"index": 0, "t": 1.0}) + "\n")
    fh.write('{"index": 1, "t":')
check("a torn last line does not reset the numbering", cr.next_index(torn) == 1)

# --- 4. an interrupted recording keeps everything already written ----------

K = 4                                   # capture blows up on its 4th call
d2 = fresh()
raised = None
try:
    cr.record(d2, Stub(raise_on=K), lambda img: 5.0, lambda: (0.1, 0.2),
              period=0.0, stop_fn=after(50))
except Exception as exc:                                           # noqa: BLE001
    raised = exc
check("a dead capture propagates rather than looping on a frozen stream",
      isinstance(raised, RuntimeError))
check(f"the {K-1} records written before the failure all persist",
      len(lines(d2)) == K - 1 and jpegs(d2) == [f"{i:04d}.jpg" for i in range(K - 1)])
check("every surviving line is complete and parseable",
      all(set(r) == EXPECT for r in lines(d2)))
check("a chain can be resumed after the failure",
      cr.next_index(d2) == K - 1)

# --- 4b. THE FRAME IS WRITTEN BEFORE ITS META LINE, ALWAYS -----------------
#
# The module's headline durability invariant (chain_record.py's docstring), and
# section 4 above CANNOT see it: on the normal path both writes happen whatever
# their order, so only a crash BETWEEN them tells the two apart. Swapping the
# two lines left this whole file green.
#
# It is not a cosmetic ordering. A meta line whose jpeg is missing is DROPPED by
# `chain.Chain.load` ("that waypoint is dropped, so chain positions after it
# shift by one"), so one orphan line puts every later waypoint off by one and
# the controller servos on the wrong reference for the rest of the run. The
# other order is safe by construction: an orphan JPEG with no line is invisible,
# because meta.jsonl is the index.
#
# Forced by making the SAVE fail, which is the one event that separates the two
# orders. `_to_image` hands back whatever `.convert()` returns, so this stands
# in for a full disk, a read-only directory, or the process dying mid-write.


class _Unsaveable:
    def convert(self, *a, **k):
        return self

    def save(self, *a, **k):
        raise OSError("no space left on device")


class SaveDies:
    """Frames that save normally until tick `boom_on`."""

    def __init__(self, boom_on):
        self.n, self.boom_on = 0, boom_on

    def __call__(self):
        self.n += 1
        return _Unsaveable() if self.n == self.boom_on else Image.fromarray(
            frame(self.n))


B = 4                                   # the jpeg write fails on the 4th tick
d7 = fresh()
boom = None
try:
    cr.record(d7, SaveDies(B), lambda img: 1.0, lambda: (0.0, -0.45),
              period=0.0, stop_fn=after(50))
except Exception as exc:                                           # noqa: BLE001
    boom = exc
check("a frame that cannot be written ends the recording rather than being "
      "quietly skipped", isinstance(boom, OSError))
recs7 = lines(d7)
check(f"the failed tick left {B-1} meta lines, not {B}: the jpeg is written "
      f"FIRST, so a line always implies its frame", len(recs7) == B - 1)
check("every meta line on disk has its jpeg beside it -- no orphan line, so "
      "no waypoint shift downstream",
      recs7 != [] and all(os.path.exists(os.path.join(d7, r.get("path") or ""))
                          for r in recs7))
check(f"...and the {B-1} frames written before it all survive",
      jpegs(d7) == [f"{i:04d}.jpg" for i in range(B - 1)])
check("the recorder can be resumed from exactly there",
      cr.next_index(d7) == B - 1)

# --- 5. a sensor that raises is recorded, not hidden ------------------------

d3 = fresh()


def angry(img):
    raise ValueError("no compass")


cr.record(d3, Stub(), angry, lambda: (None, None), period=0.0,
          stop_fn=after(2))
recs3 = lines(d3)
check("a heading reader that raises does not stop the recording",
      len(recs3) == 2)
check("...and it is SAID in the note, with a null heading",
      all(r.get("heading") is None and "heading:ValueError" in r.get("note", "")
          for r in recs3))

# --- 5b. a stick axis is ALWAYS a real number ------------------------------
#
# `chain.Chain.load` calls `float(lx)` on every line, so ONE null makes the
# WHOLE chain unloadable -- it raises, it does not skip. And (None, None) is
# the ORDINARY case, not an edge one: `--user` gets it whenever
# `record_drive._open_stick` finds no controller on this Mac (the DualSense is
# paired to the PS5), and `--executor --no-tap` passes it outright. Reproduced
# 2026-09-07: TypeError at Waypoint.__init__ on the first line.

d6 = fresh()
cr.record(d6, Stub(), lambda img: 1.0, lambda: (None, None), period=0.0,
          stop_fn=after(2))
cr.record(d6, Stub(), lambda img: 2.0, lambda: (float("nan"), 0.2), period=0.0,
          stop_fn=after(1))
recs6 = lines(d6)
check("an unreadable stick is stored as a number, never null",
      len(recs6) == 3 and all(isinstance(r.get("lx"), float)
                              and isinstance(r.get("ly"), float)
                              for r in recs6))
check("...as 0.0, the centred stick",
      [(r.get("lx"), r.get("ly")) for r in recs6[:2]] == [(0.0, 0.0), (0.0, 0.0)])
check("...and a NaN axis is not a stick reading either",
      (recs6[2].get("lx"), recs6[2].get("ly")) == (0.0, 0.2))
check("...and the loss is SAID, so 'centred' and 'never measured' stay apart",
      all("stick:unknown" in r.get("note", "") for r in recs6))
# The control. Section 2's first N lines were written with a readable
# (0.0, -0.45) -- if the note appeared on those too it would say nothing.
# (`recs` has since grown: section 3's second call passes (None, None), and
# those lines DO carry it, correctly.)
check("a stick that WAS read carries no such note",
      len(recs) > N and all("stick:unknown" not in r.get("note", "")
                            for r in recs[:N]))

# The end-to-end obligation: what this writes, the SENSOR's loader must read.
# Guarded on the IMPORT only -- chain.py belongs to another agent, and a
# module that will not import at all is their failure, not a pass here.
try:
    import chain as _chain
except Exception as _exc:                                          # noqa: BLE001
    _chain = None
    print(f"NOTE  chain.py did not import ({_exc!r}); the end-to-end load "
          f"check did not run. That module is not this agent's.")
if _chain is not None:
    try:
        _loaded = _chain.Chain.load(d6)
    except Exception as _exc:                                      # noqa: BLE001
        _loaded = _exc
    check("a chain recorded with NO controller loads (chain.Chain.load)",
          not isinstance(_loaded, BaseException)
          and len(_loaded.waypoints) == len(recs6))

# --- 6. the stop frame is IN the chain -------------------------------------
#
# --user stops on at_table(). Dropping the frame that satisfied the stop would
# throw away the one frame the whole chain exists to reach.

d4 = fresh()
cr.record(d4, Stub(), lambda img: 1.0, lambda: (None, None), period=0.0,
          stop_fn=after(1))
check("the frame that triggered the stop is recorded", len(lines(d4)) == 1)

# --- 7. nothing anywhere above touched the console -------------------------

import analog_replay as ar

check("the FIFO under test is the scratch one", ar.FIFO == _FIFO)
check("no FIFO was created by any of this", not os.path.exists(_FIFO))

sent = []
_orig_send = ar.send
ar.send = lambda lines_: sent.append(lines_)
try:
    d5 = fresh()
    cr.record(d5, Stub(), lambda img: 1.0, lambda: (0.0, 0.0), period=0.0,
              stop_fn=after(1))
    check("record() sends nothing to the stick", sent == [])
finally:
    ar.send = _orig_send

check("main() with no driver flag prints usage and drives nothing",
      cr.main([]) == 2 and not os.path.exists(_FIFO))

# --- 8. the Tap: it observes the live run and must not be able to break it ---
#
# Nothing exposes the current stick state, so the executor's lx/ly and cam come
# from watching `analog_replay.send` and `turn_to` go past. That wrapper sits in
# the path of EVERY stick command of a live run, so what matters is not that it
# observes well but that it cannot interfere: the original is always called and
# its value always returned, even when the observation blows up.

t = cr.Tap()
t._see_send(["left_x 32767", "left_y -16383", "right_x 0", "right_y 0"])
check("the tap reads the stick back out of the FIFO lines",
      t.stick() == (1.0, -0.5))
t._see_send(["clear"])
check("`clear` zeroes the tap, as it does the injector", t.stick() == (0.0, 0.0))
t._see_send(["left_x 32767", "left_y not-a-number"])
check("a line it cannot parse costs only that line, not the batch",
      t.stick() == (1.0, 0.0))


class FakeMod:
    calls = []

    @staticmethod
    def send(lines_):
        FakeMod.calls.append(lines_)
        return "sent"


_before = FakeMod.send
t2 = cr.Tap()
t2._wrap(FakeMod, "send", lambda a, k: 1 / 0)          # an observer that raises
out = FakeMod.send(["left_x 100"])
check("a broken observation still calls the original and returns its value",
      out == "sent" and FakeMod.calls == [["left_x 100"]])
t2.remove()
check("remove() puts the original back exactly", FakeMod.send is _before)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
