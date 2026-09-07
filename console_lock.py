"""Who is driving the console right now. One writer at a time.

WHY THIS EXISTS. `keep_awake` nudges the right stick and then sends `clear`
every 120s. `clear` zeroes left_x/left_y in the injector, while
`slow_traverse.walk_leg` holds the stick UNTIMED and sleeps out the leg's full
duration -- so a nudge landing mid-leg ends the push early. The leg walks short,
the character stops somewhere it was not meant to be, and NOTHING IN ANY LOG
DISTINGUISHES THAT FROM A ROUTING FAILURE. It would be scored as an arm's
failure and it is not one. CLAUDE.md records this as the reason keep_awake was
deleted once already.

The 2026-09-06 leg-1 A/B avoided it because keep_awake was killed by hand first.
That is not a guard, it is a memory, and the user said as much: "make sure to
turn it off when you do the navigation part."

WHY A PROTOCOL AND NOT A PROCESS-NAME CHECK. The obvious guard is "refuse to run
if a process called keep_awake is alive". That is exactly the shape that killed
the original: its BUSY_PATTERNS was a hand-kept list of seven script names, it
matched no A/B harness, and nothing failed when a new name was missing. A list
of names rots silently because absence is invisible.

WHY NOT lsof ON THE FIFO, which would be name-free. Measured: keep_awake holds
the FIFO open only for the ~2s of a nudge, once every 120s, so a snapshot sees
nothing 98% of the time. A check that is right 2% of the time is worse than
none. FIFOs also permit many concurrent writers, so holding it proves nothing.

So: a positive DECLARATION. Anything that drives the console announces itself
for as long as it is driving, and anything about to drive refuses while someone
else holds it. A new nudger that ignores this is a new bug rather than a guard
that quietly stopped working -- and the failure is loud at the moment it starts,
not silent for the length of a run.

A STALE LOCK MUST NEVER BLOCK A RUN. A crashed holder leaves the file behind, so
the record carries its pid and a dead pid is ignored and cleaned up. A lock is
only real while its process is.
"""
import json
import os
import time

def _default_path():
    """Where the declaration lives.

    PER-PROCESS UNDER BASEBALL_TEST_RUN, and in the system temp dir. The offline
    suite runs at JOBS=4 and several tests drive run_trial, so a single shared
    path made them contend for a lock that models a PHYSICAL console none of
    them is touching: test_run_trial_streams.py passed alone and failed in the
    suite, which is the worst way for a test to fail. Keeping it out of the
    project tree also keeps test_no_side_effects.py honest.

    BASEBALL_CONSOLE_LOCK overrides both, so a test can point two "processes" at
    one file deliberately and exercise the contention this exists for.
    """
    env = os.environ.get("BASEBALL_CONSOLE_LOCK")
    if env:
        return env
    if os.environ.get("BASEBALL_TEST_RUN"):
        import tempfile
        return os.path.join(tempfile.gettempdir(), f"console_busy_{os.getpid()}")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".console_busy")


PATH = _default_path()


class ConsoleBusy(RuntimeError):
    """Raised when something else is already driving."""


def _read():
    try:
        with open(PATH) as fh:
            return json.load(fh)
    except Exception:
        return None


def holder():
    """The live holder's record, or None. Cleans a stale lock as a side effect."""
    rec = _read()
    if not rec:
        return None
    pid = rec.get("pid")
    if not isinstance(pid, int):
        return None
    try:
        os.kill(pid, 0)          # sends nothing; just asks whether it is there
    except OSError:
        try:
            os.unlink(PATH)
        except OSError:
            pass
        return None
    return rec


def acquire(name, force=False):
    """Declare that this process is driving. Raises ConsoleBusy if someone is.

    Not atomic against a simultaneous acquire, deliberately: the race is two
    operators starting two runs in the same millisecond, which is not the
    failure this exists for and would cost a lockfile dance to close.
    """
    cur = holder()
    if cur and cur.get("pid") != os.getpid() and not force:
        raise ConsoleBusy(
            f"{cur.get('name')!r} (pid {cur.get('pid')}) has been driving the "
            f"console since {time.strftime('%H:%M:%S', time.localtime(cur.get('since', 0)))}. "
            f"Stop it before driving: a background nudge landing mid-leg ends "
            f"the push early, and the short leg is indistinguishable from a "
            f"routing failure in every log this project writes.")
    with open(PATH, "w") as fh:
        json.dump({"name": name, "pid": os.getpid(), "since": time.time()}, fh)
    return True


def release():
    """Give up the lock, but only if it is ours. Never raises."""
    rec = _read()
    if rec and rec.get("pid") == os.getpid():
        try:
            os.unlink(PATH)
        except OSError:
            pass


class held:
    """`with console_lock.held("name"):` for the duration of a run."""

    def __init__(self, name, force=False):
        self.name, self.force = name, force

    def __enter__(self):
        acquire(self.name, force=self.force)
        return self

    def __exit__(self, *exc):
        release()
        return False
