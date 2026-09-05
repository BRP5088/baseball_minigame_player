"""Replay a recorded walk into chiaki as REAL ANALOG stick values.

Requires a chiaki-ng built with the injectinput patch, launched with:

    CHIAKI_INJECT_INPUT=/tmp/chiaki_input /Applications/chiaki-ng.app/Contents/MacOS/chiaki

WHY THIS EXISTS
---------------
Every earlier replay drove chiaki through the keyboard, where a key is full
deflection and nothing else. The recording of 2026-08-27 walks at a median
stick magnitude of 0.54 and never exceeds 0.77, so keyboard replay traveled
at roughly twice the recorded speed on every leg. Approximating 0.54 by
pulsing a key does not work either — each pulse re-accelerates from a
standstill, and it measurably under-travels.

Here the recorded value is sent as the number it is. 0.54 becomes 17694 in the
same int16 field a real DualSense writes, so there is nothing left to
approximate.

The replay is still OPEN-LOOP IN POSITION: it reproduces the inputs, not the
outcome. If the character starts somewhere slightly different, it ends
somewhere slightly different, and no amount of input fidelity fixes that.
Closing that loop needs the compass, and is a separate problem from this one.
"""

import errno
import fcntl
import json
import math
import os
import time

FIFO = os.environ.get("CHIAKI_INJECT_INPUT", "/tmp/chiaki_input")
AXIS_MAX = 32767

# How long open_stream() will wait for a reader to attach to the FIFO before
# giving up and raising. See _open_write_end() for why waiting AT ALL is
# necessary and why waiting FOREVER (what open(FIFO, "w") does) is not.
#
# THIS IS A SAFETY BOUND, NOT A DISCRIMINATING THRESHOLD, and the difference
# matters because a bar that sits inside one population has been the bug here
# six times. Nothing is being classified: any finite value is strictly better
# than the unbounded wait it replaces, and the only way to get this wrong is to
# make it too SHORT and fail an open that would have succeeded. So it is set
# far above every measured and every structural figure that bears on it:
#
#   1.2ms    worst open latency measured with a reader attached, over 400 opens
#            against a separate-process reader reopening as fast as it can
#            (315 of those 400 hit ENXIO first and every one cleared on retry)
#   242ms    worst Python sleep measured on this machine under CPU saturation
#            (CLAUDE.md: normally 4.7-5.7ms) — the retry loop and chiaki's
#            reader thread are both scheduled, so both stretch under load
#   1000ms   chiaki's own reader retry: injectinput.cpp Listen() sleeps 1s and
#            reopens if its fopen fails, so a reader recovering from that is
#            genuinely absent for ~1s and then comes back
#   5000ms   chiaki's INJECT_TIMEOUT_MS — it drops injected state after 5s of
#            silence, so an open that waited longer than this would come back
#            to a controller that had already been released
#
# 2.0s clears the first three and stays under the fourth. What is NOT
# known is the tail of the reader-attached population on a saturated machine:
# it was measured on an idle one, n=400. If an open ever times out with chiaki
# demonstrably alive and reading, that tail is the thing to measure — raise
# this via the environment rather than guessing at a new literal.
OPEN_TIMEOUT_SEC = float(os.environ.get("CHIAKI_INJECT_OPEN_TIMEOUT", "2.0"))

# Gap between ENXIO retries. Small because the measured gap it is covering is
# sub-millisecond, so this dominates the latency of a retried open; not zero,
# because a 2s spin at full tilt would compete with the walk it is serving.
_OPEN_RETRY_SEC = 0.002


def to_axis(v):
    """Stick float (-1..1) to the int16 a real controller sends."""
    return max(-32768, min(AXIS_MAX, int(round(v * AXIS_MAX))))


_fh = None

_warned = set()


def _warn_once(key, msg):
    """Print `msg` the first time `key` is seen in this process, then never.

    send() is the hottest path in the project — every stick update, 30-50 times
    a second for the length of a walk — so anything printed per call would be
    the log. The condition warned about is process-wide (an environment
    variable), so once carries all of it.
    """
    if key in _warned:
        return
    _warned.add(key)
    print(msg)


def _open_write_end(path, timeout):
    """Open the write end of the FIFO, waiting AT MOST `timeout` for a reader.

    WHY NOT open(path, "w")
    -----------------------
    That is what this used to be, and on a POSIX FIFO it BLOCKS FOREVER until a
    reader attaches. Measured on this machine: a blocking open against a
    reader-less FIFO had not returned after 3.0s and had to be killed, and it
    returns the instant a reader appears.

    That is the exact failure shape catalogued in CLAUDE.md — a hang and a
    working call have identical output until the run simply stops. It is worse
    than an ordinary hang because the fallbacks that exist for this path cannot
    see it: input_controller._inject_press wraps the call in `except OSError`
    and degrades to the keyboard, but A HANG RAISES NOTHING, so that fallback is
    unreachable. Every stick caller (walk_steps, brett_walk, graph_walk,
    slow_traverse) has no guard at all and simply stops.

    The window is real, not theoretical: restart_chiaki.sh kill -9s chiaki and
    leaves the FIFO node on disk, so between chiaki dying and the next chiaki
    starting the node exists with nobody reading it.

    WHY NOT A BARE NON-BLOCKING OPEN EITHER
    ---------------------------------------
    O_WRONLY|O_NONBLOCK raises ENXIO when no process holds the FIFO open for
    reading, which is precisely the signal wanted — but "no reader right now"
    is NOT the same as "chiaki is gone". chiaki's reader loop is
    fopen / fgets-until-EOF / fclose / fopen (injectinput.cpp Listen()), so
    every time this side closes the pipe the reader spends a moment between
    fclose and its next fopen. Measured, separate-process reader, 400 opens
    reopening immediately: 315 of them hit ENXIO first. EVERY ONE cleared on
    retry, worst case 1.2ms. A bare non-blocking open would therefore have
    failed most opens against a perfectly healthy chiaki.

    So: retry ENXIO until OPEN_TIMEOUT_SEC, then let it raise. A reader that is
    alive is back within about a millisecond; a reader that is gone gives ENXIO
    on every attempt for as long as anyone cares to ask (measured: hundreds of
    consecutive ENXIO in 0.5s, never once succeeding). The two populations do
    not overlap and the timeout sits far outside both.

    WHY O_NONBLOCK IS THEN CLEARED
    ------------------------------
    It is wanted for the OPEN and would be a bug on the WRITES. Left set, a
    write that cannot fit in the pipe buffer does not wait for the reader — it
    fails. Measured with a reader that stalls 1s before draining, writing 260000
    chars in the production shape (text mode, buffering=1):

        O_NONBLOCK left set    BlockingIOError, and only 8192 bytes arrived
        O_NONBLOCK cleared     all 260000 bytes arrived, the write took 1.00s

    A truncated write is half a stick line, which the listener's sscanf cannot
    parse, so the character silently keeps its previous stick value. Clearing
    the flag restores exactly the blocking write semantics every walk the router
    makes was built on.

    O_CREAT|O_TRUNC reproduce what open(path, "w") did, deliberately: the
    offline tests point FIFO at a scratch REGULAR FILE and depend on it being
    created and truncated. O_TRUNC is ignored on a FIFO (verified here).
    """
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        try:
            fd = os.open(path,
                         os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NONBLOCK,
                         0o666)
            break
        except OSError as e:
            # ENXIO is the one and only "nobody is reading" answer. Anything
            # else (a missing directory, a permission problem) is a real error
            # and must not be retried into a 2-second stall.
            if e.errno != errno.ENXIO or time.monotonic() >= deadline:
                raise
            time.sleep(_OPEN_RETRY_SEC)
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
    except OSError:
        # Never hand back a descriptor still in non-blocking mode: a partial
        # write is worse than no write, because it looks like it worked.
        os.close(fd)
        raise
    return os.fdopen(fd, "w", buffering=1)


def open_stream():
    """Hold the FIFO open for a whole replay.

    Opening and closing per update looked harmless and was not: at 50Hz it
    raised BrokenPipeError outright, and even at 30Hz each open/close added
    latency to every write, so commands arrived late and each stick value was
    applied for less time than recorded. The visible symptom is a replay that
    follows the right path but does not travel far enough.

    IT MEMOISES. `_fh` is held until close_stream(), so send() does NOT open the
    pipe on every call — a comment in input_controller._inject_press still says
    it does, and that is wrong. Two consequences worth having in mind:

    - The open COST is paid once per stream, not per stick update, so the
      bounded wait above cannot accumulate across a walk.
    - The HANDLE goes stale across a chiaki restart. injectinput.cpp does
      unlink() + mkfifo() at startup, so the path gets a NEW INODE and a cached
      handle points at the old one. That failure is loud (BrokenPipeError) and
      clear()'s `finally: close_stream()` heals it, which is why it has never
      cost a run — unlike the silent hang this function now refuses to perform.
    """
    global _fh
    if _fh is None:
        _fh = _open_write_end(FIFO, OPEN_TIMEOUT_SEC)
    return _fh


def close_stream():
    global _fh
    if _fh is not None:
        try:
            _fh.close()
        finally:
            _fh = None


def send(lines):
    """Write one batch of field updates to the listener.

    HARD OFF under BASEBALL_TEST_RUN, and it needs its own lockout rather than
    inheriting one. input_controller._inject_press guards the button path, but
    15+ call sites reach this function directly — walk_steps, brett_walk,
    route_follow, go_to_landmark, and the `finally:` block of every overnight
    harness — so a guard that lives only in input_controller protects none of
    them. The offline suite drove the live console once already through exactly
    this kind of gap.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        # SAY IT ONCE. The guard is correct, but EVERY stick command in the
        # system funnels through here, so a stray exported BASEBALL_TEST_RUN
        # turns an entire live walk into a no-op — silently. The character
        # never moves, walk_forward still returns a small view-change number
        # (standing still measures 0.91-6.41), and that number reads as "wedged
        # against geometry" or "the console is asleep". The diagnosis then goes
        # to the console, the stream or the leg constants, and the cause is a
        # shell variable.
        _warn_once(
            "test-run",
            "  [analog] BASEBALL_TEST_RUN is set — EVERY stick command for the "
            "rest of this process is DISCARDED and nothing will move. If this "
            "is a live run, the character is not stuck and the console is not "
            "asleep: unset BASEBALL_TEST_RUN.")
        return
    fh = open_stream()
    fh.write("".join(l + "\n" for l in lines))
    fh.flush()


def clear():
    try:
        send(["clear"])
    finally:
        close_stream()


def replay(demo_dir, rate_hz=30.0, log=print):
    """Feed the recording's stick values through at their original timing.

    Sends at a fixed rate rather than per recorded sample: the recording is
    ~50Hz and resampling to a steady 30Hz keeps the FIFO writes cheap while
    staying far above the ~6Hz at which the walk's shape would start to blur.
    """
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    live = [s for s in samples
            if math.hypot(s["axes"].get("lx", 0), s["axes"].get("ly", 0)) > 0.15
            or abs(s["axes"].get("rx", 0)) > 0.15]
    if not live:
        log("  nothing to replay")
        return
    t0, t1 = live[0]["t"], live[-1]["t"]
    log(f"  replaying {t0:.1f}s..{t1:.1f}s ({t1 - t0:.1f}s) as analog")

    step = 1.0 / rate_hz
    started = time.time()
    t = t0
    try:
        while t < t1:
            s = min(samples, key=lambda x: abs(x["t"] - t))
            a = s["axes"]
            send([
                f"left_x {to_axis(a.get('lx', 0))}",
                f"left_y {to_axis(a.get('ly', 0))}",
                f"right_x {to_axis(a.get('rx', 0))}",
                f"right_y {to_axis(a.get('ry', 0))}",
            ])
            t += step
            # keep replay wall-time aligned with the recording's own clock
            behind = (t - t0) - (time.time() - started)
            if behind > 0:
                time.sleep(behind)
    finally:
        # ALWAYS hand control back, even on Ctrl-C or an exception. Leaving a
        # stick value injected would keep the character walking into a wall
        # with no obvious cause.
        clear()
        log("  cleared; controller returned to normal")


if __name__ == "__main__":
    import sys
    replay(sys.argv[1] if len(sys.argv) > 1
           else "demos/walk_20260827_214446")
