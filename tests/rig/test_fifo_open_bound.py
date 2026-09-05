"""open_stream() must not HANG when nothing is reading the FIFO.

WHY THIS EXISTS
---------------
analog_replay.open_stream() used to be `open(FIFO, "w")`, and on a POSIX FIFO
that blocks FOREVER until a reader attaches. Measured against a scratch FIFO:
the call had not returned after 3.0s, and returned the instant a reader
appeared.

restart_chiaki.sh kill -9s chiaki but leaves the FIFO NODE on disk, so between
chiaki dying and the next chiaki starting there is a real window where the path
exists with nobody reading it. A send() in that window never comes back.

It is the diagnosis-catalogue shape at its worst: a hang and a working call have
identical output until the run simply stops. And the fallbacks written for this
path cannot see it — input_controller._inject_press wraps the call in
`except OSError` and degrades to the keyboard, but A HANG RAISES NOTHING, so
that branch is unreachable; the stick callers (walk_steps, brett_walk,
graph_walk, slow_traverse) call ar.send() with no guard at all.

WHAT IS PINNED HERE
-------------------
1. reader-less FIFO      -> raises OSError/ENXIO, and does it PROMPTLY
2. reader attached       -> still works, byte for byte (the positive control,
                            without which test 1 could pass on a send() that
                            was simply broken)
3. reader arrives LATE   -> still works. This is what stops the fix from being
                            a bare non-blocking open: measured against a live
                            separate-process reader, 315 of 400 opens hit ENXIO
                            first because chiaki's reader is momentarily between
                            fclose and fopen, and every one cleared on retry.
4. O_NONBLOCK cleared    -> it is wanted for the OPEN and is a bug on the
                            WRITES. Measured: left set, a 260000-char write
                            raised BlockingIOError with only 8192 bytes
                            delivered; cleared, all 260000 arrived.
5. a non-ENXIO error     -> raises straight away rather than being retried for
                            the whole timeout.

NOTHING HERE TOUCHES THE REAL PIPE. Every case runs against a FIFO created in a
private temp directory; /tmp/chiaki_input is never opened, and the child process
in test 1 asserts its own FIFO path before it writes anything.

THE HANG TEST IS BOUNDED FROM OUTSIDE THE PROCESS. It runs in a subprocess under
subprocess.run(timeout=...), so a regression fails this file in seconds instead
of hanging it — SIGALRM would not be trustworthy here, since the thing being
bounded is a blocking open inside the interpreter's own syscall.
"""
import errno
import fcntl
import os
import subprocess
import sys
import tempfile
import threading
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import analog_replay as ar

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# The child that performs the actual reader-less send. It runs with
# BASEBALL_TEST_RUN cleared (send() is hard off under it) and with
# CHIAKI_INJECT_INPUT pointed at the scratch FIFO, which analog_replay reads at
# import — so the module under test is exercised exactly as shipped, on a pipe
# nothing else can be listening to.
_CHILD = r'''
import errno, os, sys, time
sys.path.insert(0, sys.argv[1])
import analog_replay as ar
want = os.environ["CHIAKI_INJECT_INPUT"]
if ar.FIFO != want:                      # never write to the real pipe
    print("WRONG_FIFO %r" % (ar.FIFO,)); sys.exit(3)
t = time.monotonic()
try:
    ar.send(["left_x 17694"])
except OSError as e:
    print("RAISED %s %s %.3f" % (type(e).__name__,
                                 errno.errorcode.get(e.errno, e.errno),
                                 time.monotonic() - t))
    sys.exit(0)
print("RETURNED %.3f" % (time.monotonic() - t))
sys.exit(1)
'''

# A generous LITERAL bound on how long a reader-less send() may take before it
# gives up. Pinned as a number, NOT as `<= ar.OPEN_TIMEOUT_SEC`: an assertion
# against the constant it is guarding rises with that constant and passes
# forever, so a change to 600s would sail through it. This is the statement
# "the shipped default is bounded and small", and it is the whole point of the
# fix, so it has to be independent of the value being defended.
MAX_GIVE_UP_SEC = 10.0
# How long the harness waits before declaring the child hung. Far above
# MAX_GIVE_UP_SEC so a slow-but-bounded give-up reports as a FAILED ASSERTION
# with a number in it, not as an ambiguous timeout.
CHILD_KILL_SEC = 45.0

_tmp = tempfile.mkdtemp(prefix="baseball_fifo_bound_")
_fifo = os.path.join(_tmp, "chiaki_input")
os.mkfifo(_fifo, 0o600)

_real_fifo = ar.FIFO
_had_flag = os.environ.pop("BASEBALL_TEST_RUN", None)
_readers = []


def _read_lines(path, out, delay=0.0):
    """Stand in for chiaki's Listen(): hold the read end open and drain it."""
    if delay:
        time.sleep(delay)
    try:
        with open(path, "r") as fh:
            for line in fh:
                out.append(line)
    except OSError as e:                       # pragma: no cover - diagnostic
        out.append("READER_ERROR %r" % (e,))


def _start_reader(path, out, delay=0.0):
    th = threading.Thread(target=_read_lines, args=(path, out, delay),
                          daemon=True)
    th.start()
    _readers.append(th)
    return th


try:
    # === 1. NO READER: raise, and raise PROMPTLY ==========================
    env = dict(os.environ)
    env["CHIAKI_INJECT_INPUT"] = _fifo
    env.pop("BASEBALL_TEST_RUN", None)
    t0 = time.monotonic()
    try:
        p = subprocess.run([sys.executable, "-c", _CHILD, _ROOT],
                           env=env, capture_output=True, text=True,
                           timeout=CHILD_KILL_SEC)
        out, rc, hung = p.stdout.strip(), p.returncode, False
    except subprocess.TimeoutExpired:
        out, rc, hung = "", None, True
    elapsed = time.monotonic() - t0

    check(not hung,
          f"send() against a READER-LESS FIFO never returned ({CHILD_KILL_SEC}s "
          "and killed). This is the original bug: open(FIFO, 'w') blocks "
          "forever with no reader, restart_chiaki.sh leaves the FIFO node on "
          "disk with chiaki dead, and a hang raises nothing so "
          "input_controller's `except OSError` fallback can never fire.")
    if not hung:
        check(rc == 0,
              f"the reader-less send() did not raise: child said {out!r} "
              f"(rc={rc}). It must raise OSError so _inject_press can fall back "
              "to the keyboard and so the unguarded stick callers fail fast "
              "instead of stopping forever.")
        check("ENXIO" in out,
              f"child reported {out!r}; the error must be ENXIO — 'nobody is "
              "reading this pipe'. ENOENT would mean the test pointed at a "
              "path that does not exist and proved nothing about a FIFO.")
        check(elapsed < MAX_GIVE_UP_SEC,
              f"the reader-less send() took {elapsed:.1f}s to give up, over the "
              f"{MAX_GIVE_UP_SEC}s this test allows. Bounded is the whole "
              "point; a wait long enough to outlive chiaki's 5s "
              "INJECT_TIMEOUT_MS is barely better than the hang.")

    # === 2. READER ATTACHED: unchanged, byte for byte ====================
    # POSITIVE CONTROL for test 1. Same module, same FIFO. Without it, a send()
    # that raised for any unrelated reason would make test 1 green.
    got = []
    ar.FIFO = _fifo
    ar.close_stream()
    _start_reader(_fifo, got)
    time.sleep(0.2)                 # the reader is now parked inside open('r')
    ar.send(["left_x 17694", "left_y -8000"])
    # The optional third field (a timed hold) must survive untouched — the
    # listener parses all three with one sscanf.
    ar.send(["right_x 32767 400"])

    # === 4. O_NONBLOCK MUST BE OFF ON THE LIVE HANDLE ====================
    # Wanted for the open, a bug on the writes: left set, a write that does not
    # fit the pipe buffer fails instead of waiting, and a half-written stick
    # line is one the listener's sscanf cannot parse — so the character
    # silently keeps its previous stick value.
    fl = fcntl.fcntl(ar._fh.fileno(), fcntl.F_GETFL)
    check(not (fl & os.O_NONBLOCK),
          "the FIFO handle is still in NON-BLOCKING mode. Measured: a 260000 "
          "char write then raises BlockingIOError with only 8192 bytes "
          "delivered, against all 260000 when the flag is cleared. O_NONBLOCK "
          "belongs to the open, never to the writes.")

    ar.close_stream()               # EOF, so the reader thread finishes
    _readers[-1].join(timeout=5.0)
    check(not _readers[-1].is_alive(),
          "the reader never saw EOF after close_stream()")
    check(got == ["left_x 17694\n", "left_y -8000\n", "right_x 32767 400\n"],
          f"with a reader attached the pipe carried {got!r}. Every walk the "
          "router makes depends on this path: one field per newline-terminated "
          "line, flushed, with the optional hold-in-ms third field intact.")

    # === 3. READER ARRIVES LATE: wait for it, do not fail ================
    # This is what separates a BOUNDED WAIT from a bare non-blocking open.
    # chiaki's reader loop is fopen / fgets-to-EOF / fclose / fopen, so it is
    # regularly between opens for a moment: measured against a live
    # separate-process reader, 315 of 400 opens hit ENXIO first and every one
    # cleared on retry within 1.2ms. A bare non-blocking open would fail most
    # opens against a perfectly healthy chiaki.
    late = []
    ar.close_stream()
    _start_reader(_fifo, late, delay=0.30)
    t0 = time.monotonic()
    try:
        ar.send(["left_x 4242"])
        raised = None
    except OSError as e:
        raised = e
    waited = time.monotonic() - t0
    ar.close_stream()
    _readers[-1].join(timeout=5.0)
    check(raised is None,
          f"send() raised {raised!r} against a reader that attached 0.30s "
          "later. A reader that is briefly absent is the NORMAL state of "
          "chiaki between its fclose and its next fopen — failing there would "
          "break the live stick path in exchange for fixing the hang.")
    check(late == ["left_x 4242\n"],
          f"the late reader received {late!r}, expected the stick line to have "
          "waited for it")
    check(waited >= 0.20,
          f"the send() completed in {waited:.3f}s, before the reader could "
          "have attached at 0.30s — this case did not exercise the wait, so it "
          "proves nothing about it")

    # === 5. A NON-ENXIO ERROR IS NOT RETRIED =============================
    # Only "nobody is reading" is worth waiting on. A missing directory or a
    # permission problem will still be there in two seconds, and retrying it
    # turns a clear error into a stall.
    ar.close_stream()
    ar.FIFO = os.path.join(_tmp, "no_such_dir", "chiaki_input")
    t0 = time.monotonic()
    try:
        ar.send(["left_x 1"])
        err = None
    except OSError as e:
        err = e
    spent = time.monotonic() - t0
    check(err is not None and err.errno == errno.ENOENT,
          f"a FIFO path under a missing directory raised {err!r}, expected "
          "ENOENT")
    check(spent < 1.0,
          f"a missing-directory open took {spent:.3f}s. Only ENXIO may be "
          "retried; anything else must surface immediately instead of being "
          "waited out for the whole open timeout.")
finally:
    if _had_flag is not None:
        os.environ["BASEBALL_TEST_RUN"] = _had_flag
    try:
        ar.close_stream()
    except OSError:
        pass
    ar.FIFO = _real_fifo
    for th in _readers:
        th.join(timeout=1.0)
    try:
        os.remove(_fifo)
    except OSError:
        pass
    try:
        os.rmdir(_tmp)
    except OSError:
        pass

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  fifo open bound: a reader-less FIFO raises ENXIO promptly instead of "
      "hanging forever, a reader that attaches late is still waited for, the "
      "handle is left in blocking mode, and a non-ENXIO error is not retried")
