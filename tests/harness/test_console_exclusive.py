"""A live run must refuse to start while something else is driving the console.

THE HAZARD, in the project's own words. keep_awake nudges the right stick and
sends `clear` every 120s. `clear` zeroes left_x/left_y in the injector, while
slow_traverse.walk_leg holds the stick UNTIMED and sleeps out the push -- so a
nudge landing mid-leg ends it early, the leg walks short, and NOTHING IN ANY LOG
DISTINGUISHES THAT FROM A ROUTING FAILURE. It would be recorded as an arm's
failure and it is not one. CLAUDE.md records this as why keep_awake was deleted
once already; it exists again, and the 2026-09-06 leg-1 A/B was protected only
by someone remembering to kill it first.

WHAT IS ASSERTED HERE IS BEHAVIOUR, NOT SOURCE TEXT. A grep for "console_lock"
in _harness.py would pass while the call sat behind an `if False`. These drive
run_trial for real and check whether the child was executed.
"""
import os
import subprocess
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))

import console_lock
import _harness

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


tmp = tempfile.mkdtemp(prefix=f"conex_{os.getpid()}_")
MARKER = os.path.join(tmp, "child_ran")
CHILD = os.path.join(tmp, "child.py")
with open(CHILD, "w") as fh:
    fh.write("import json, os, sys\n"
             f"open({MARKER!r}, 'a').write('x')\n"
             "print(json.dumps({'arrived': True, 'seconds': 0.0}))\n")

console_lock.release()
if os.path.exists(console_lock.PATH):
    os.unlink(console_lock.PATH)


def run_once():
    """One run_trial against the throwaway child. Returns (result, raised)."""
    try:
        r, _ = _harness.run_trial(CHILD, "arm", 30, cwd=tmp,
                                  log=lambda *a: None, check_stream=False)
        return r, None
    except Exception as exc:                                   # noqa: BLE001
        return None, exc


# --- 1. POSITIVE CONTROL: with nobody driving, the child really does run ----
# Without this the file could pass by never executing anything at all.
before = os.path.exists(MARKER)
res, exc = run_once()
check(f"with no holder the child ran (marker={os.path.exists(MARKER)}, "
      f"exc={exc!r})", os.path.exists(MARKER) and exc is None)
console_lock.release()

# --- 2. A LIVE FOREIGN HOLDER BLOCKS, AND BLOCKS BEFORE SPAWNING -----------
os.remove(MARKER)
sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
try:
    import json
    with open(console_lock.PATH, "w") as fh:
        json.dump({"name": "keep_awake", "pid": sleeper.pid,
                   "since": time.time()}, fh)
    res, exc = run_once()
    check(f"a live foreign holder raises ConsoleBusy (got {type(exc).__name__ if exc else None})",
          isinstance(exc, console_lock.ConsoleBusy))
    check("...and the child was never spawned — refusing AFTER starting the "
          "trial would still corrupt it", not os.path.exists(MARKER))
    check("...and the message names the holder",
          exc is not None and "keep_awake" in str(exc))
finally:
    sleeper.terminate()
    sleeper.wait(timeout=10)

# --- 3. A STALE LOCK MUST NOT BLOCK ---------------------------------------
# A crashed holder leaves the file behind. If that blocked runs, the guard
# would be worse than the hazard: every future run would refuse until someone
# deleted a file nobody documents.
import json
with open(console_lock.PATH, "w") as fh:
    json.dump({"name": "crashed", "pid": sleeper.pid, "since": time.time()}, fh)
check("a dead holder's pid is not a live holder", console_lock.holder() is None)
res, exc = run_once()
check(f"a stale lock does not block a run (exc={exc!r})",
      exc is None and os.path.exists(MARKER))
console_lock.release()

# --- 4. THE LOCK MUST NOT LEAK ---------------------------------------------
check("run_trial left no lock behind for this pid",
      console_lock.holder() is None or
      console_lock.holder().get("pid") == os.getpid())
console_lock.release()
if os.path.exists(console_lock.PATH):
    os.unlink(console_lock.PATH)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
