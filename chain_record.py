"""Record a CHAIN: one frame, one live compass read and one stick sample per tick.

A chain is what the closed loop servos along (`chain.py`, `chain_walk.py`). It
is a directory:

    <dir>/meta.jsonl      one JSON object per line, append-only
    <dir>/0000.jpg ...    the frame that line describes, quality 88

Nothing here decides anything. It watches, and it writes. The decisions live in
chain_walk.

WHY APPEND-ONE-LINE-AT-A-TIME, AND NEVER TRUNCATE
-------------------------------------------------
`record_drive.py` learned this the expensive way: written once at the end, a
drive killed at 4:30 of 5:00 leaves the jpegs and NO metadata -- and a frame
without its heading cannot be placed, so a full-looking directory is worthless.
Here every line is a separate open/write/flush/close, so a crash at minute four
keeps four minutes. `flush()` and not `fsync()` on purpose: the threat model is
a killed process (flushed data survives that), not a power cut, and fsync per
line would put a disk round trip inside a 4 Hz loop.

THE FRAME IS WRITTEN BEFORE ITS META LINE, ALWAYS
-------------------------------------------------
So a line always implies its jpeg exists. Dying between the two leaves an
orphan jpeg, which every reader ignores because meta.jsonl is the index. The
other order would leave `Chain.load` opening a file that is not there.

THE HEADING IS READ LIVE, FROM THE IN-MEMORY FRAME, NEVER FROM THE JPEG
-----------------------------------------------------------------------
CLAUDE.md: re-encoding a frame as JPEG changed `read_bearing`'s answer by
exactly 90 degrees -- cardinal letter confusion, a confident wrong answer, not
a degraded one. A bearing derived from a saved chain frame is therefore not
evidence about the moment that frame was taken. `heading` here is the reader's
answer on the array that came out of `capture()`, and `None` when it abstains
(~6-15% live). It is never back-filled.

TWO HEADINGS, DELIBERATELY
--------------------------
`heading` is what the compass SAID. `cam` is what the driver COMMANDED (the
target of the turn in flight, when the driver can see one). They answer
different questions and the executor's failures live in the gap between them,
so both are stored and neither is derived from the other.

WHAT A DRIVER MUST DO BEFORE STARTING A RECORDER THREAD
-------------------------------------------------------
1. Warm the OCR on the MAIN thread. `ocr_glyphs._import_tesserocr` degrades the
   WHOLE PROCESS to the CLI backend (261ms a read against 31ms) when a worker
   thread is the first to ask, silently. One `read_bearing` on the main thread
   first removes that. Measured here (offline, fixtures `three_letters_1920` /
   `two_letters_1920`): warm-then-worker gives byte-identical bearings, and 75
   concurrent reads across three threads gave 0 errors, 0 disagreements, and
   `ocr_glyphs.backend()` still `tesserocr`.
2. Serialise the captures. `compass.fast_capture` grabs through a MODULE-GLOBAL
   `mss` handle (`compass._MSS`) and mss is not thread-safe, so the recorder
   thread and the route walk must not grab at once. `serialised_capture()`
   below wraps one capture in a lock; pass THE SAME wrapper to whatever else is
   capturing (`go_to_node_verified(capture=...)` threads it down).
"""
import json
import os
import sys
import time

from PIL import Image

JPEG_QUALITY = 88          # what places.py and play_now.py already save at
META = "meta.jsonl"

# Fields on every line. Named once so the writer and the test agree, and so a
# reader can check a chain was written by this version rather than discovering
# a missing key three modules later.
#
# `path` is NOT in this agent's brief and IS in the SPEC's Waypoint. It is
# written because an extra key cannot break a reader that ignores it, while a
# missing one breaks a reader that needs it. It is the BASENAME: Chain.load is
# given the directory, and a basename keeps working when the chain is moved or
# shipped to another machine.
FIELDS = ("index", "t", "heading", "cam", "lx", "ly", "note", "path")

# `lx` and `ly` are ALWAYS REAL NUMBERS, never null. The SPEC types them float
# and `chain.Chain.load` calls `float()` on them, so ONE null line raises
# TypeError and the WHOLE chain becomes unloadable -- reproduced 2026-09-07 on
# a chain from `--user` with no controller attached, which is the ordinary case
# (the DualSense is paired to the PS5, not to this Mac). An axis the driver
# could not read is written 0.0 AND SAID IN `note` as `stick:unknown`, so the
# distinction between "centred" and "never measured" survives in the record
# instead of being lost in a null that no reader can load.


def frame_name(index):
    """`0000.jpg`. Four digits is 10,000 frames, ~41 minutes at 4 Hz -- past
    that the name widens and stops sorting lexically, which is cosmetic: the
    `index` field, not the filename, is the order."""
    return f"{index:04d}.jpg"


def meta_path(directory):
    return os.path.join(directory, META)


def heading_coverage(directory):
    """(frames with a compass heading, frames with a commanded cam)."""
    h = c = 0
    try:
        with open(meta_path(directory)) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:                                  # noqa: BLE001
                    continue
                h += r.get("heading") is not None
                c += r.get("cam") is not None
    except FileNotFoundError:
        pass
    return h, c


def next_index(directory):
    """One past the last index in meta.jsonl, or 0.

    THE META FILE IS THE AUTHORITY, and this is the only rule -- deliberately.
    A second, independent rule (say "also look at the jpegs") would mask a
    mutation of this one, and a guard that another guard covers cannot be
    tested.

    A torn final line is skipped rather than fatal: the one way to get one is
    a crash mid-write, which is exactly when the rest of the file matters most.
    """
    top = -1
    try:
        with open(meta_path(directory)) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    i = json.loads(line)["index"]
                except Exception:                                  # noqa: BLE001
                    continue
                if isinstance(i, int) and i > top:
                    top = i
    except FileNotFoundError:
        return 0
    return top + 1


def _to_image(img):
    """A PIL RGB image from whatever capture() returned (PIL or ndarray)."""
    if hasattr(img, "convert"):
        return img.convert("RGB")
    import numpy as np
    a = np.asarray(img)
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(a).convert("RGB")


def _append_line(directory, rec):
    """One open, one write, one flush, one close. Never 'w'."""
    with open(meta_path(directory), "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush()


def _axis(v):
    """(float, was_it_readable). A stick axis that a reader can always load.

    Returns 0.0 for anything that is not a finite number -- None from a driver
    with no controller handle, a NaN, a string. The caller notes the loss; see
    FIELDS above for why a null is not an option.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0, False
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0, False
    return f, True


def _call(fn, *args):
    """(value, note). A sensor that raises must not end the recording -- but it
    must not be silent either, which is CLAUDE.md 10's first catalogue entry."""
    if fn is None:
        return None, ""
    try:
        return fn(*args), ""
    except Exception as exc:                                       # noqa: BLE001
        return None, type(exc).__name__


def record(directory, capture, heading_fn, stick_fn, period=0.25, stop_fn=None,
           cam_fn=None, log=print):
    """Append frames to `directory` until `stop_fn` says stop. Returns how many
    THIS call wrote (not the total in the directory).

    `capture()`        -> a frame. Anything it raises PROPAGATES: a recorder
                          that swallows capture errors records a frozen stream
                          forever, and everything already written is on disk.
    `heading_fn(img)`  -> degrees or None. LIVE, on this frame.
    `stick_fn()`       -> (lx, ly). Either may be None (no controller handle);
                          it is stored as 0.0 with `stick:unknown` in the note,
                          because a null axis makes the chain unloadable.
    `cam_fn()`         -> the commanded camera heading, or None.
    `stop_fn(img)`     -> True to stop. Called AFTER the frame is written, so
                          the frame that satisfied it (the dealer prompt, say)
                          is IN the chain -- it is the goal, losing it would be
                          absurd. None means "never stop", so the caller's own
                          stop condition is the only one.
    KeyboardInterrupt ends the loop and returns normally; that is how --user
    stops.
    """
    os.makedirs(directory, exist_ok=True)
    i = next_index(directory)
    written = 0
    try:
        while True:
            # `t` IS WHEN THE FRAME WAS TAKEN, not when its line was written.
            # The two are ~80ms apart (a capture plus an OCR), and a chain's
            # timestamps describe frames.
            tick = time.time()
            img = capture()
            note = []
            path = os.path.join(directory, frame_name(i))
            if os.path.exists(path):
                # An orphan from a crash between jpeg and meta line. Say it:
                # overwriting quietly is how a chain ends up describing a frame
                # nobody wrote.
                note.append("overwrote-orphan")
            _to_image(img).save(path, quality=JPEG_QUALITY)
            heading, h_note = _call(heading_fn, img)
            stick, s_note = _call(stick_fn)
            cam, c_note = _call(cam_fn)
            raw = (stick if isinstance(stick, (tuple, list))
                   and len(stick) == 2 else (None, None))
            (lx, lx_ok), (ly, ly_ok) = _axis(raw[0]), _axis(raw[1])
            if not (lx_ok and ly_ok):
                note.append("stick:unknown")
            for tag, n in (("heading", h_note), ("stick", s_note), ("cam", c_note)):
                if n:
                    note.append(f"{tag}:{n}")
            _append_line(directory, {
                "index": i, "t": tick, "heading": heading, "cam": cam,
                "lx": lx, "ly": ly, "note": " ".join(note),
                "path": frame_name(i)})
            written += 1
            i += 1
            if stop_fn is not None and stop_fn(img):
                break
            time.sleep(max(0.0, period - (time.time() - tick)))
    except KeyboardInterrupt:
        log("\n  recorder stopped by hand")
    return written


# --- live drivers -----------------------------------------------------------
#
# Everything below TOUCHES THE CONSOLE and nothing below runs at import. The
# flag check, the console lock and every live import sit inside main().

def _refuse_if_test_run():
    """A live driver must never run with BASEBALL_TEST_RUN set.

    Not because a recording would be wrong -- a passive recording is fine --
    but because every guard downstream goes vacuous at once: `analog_replay.send`
    discards every stick command silently (§5), and `console_lock` moves to a
    per-pid path in the temp dir, so the lock that is supposed to stop two
    things driving at once locks nothing. An explicit raise, not `assert`:
    `python -O` deletes asserts.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit(
            "BASEBALL_TEST_RUN is set. Every stick command would be discarded "
            "silently and console_lock would guard a per-pid path instead of "
            "the console. Unset it before driving.")


def serialised_capture(fn, lock):
    """`fn` behind `lock`. compass.fast_capture shares one global mss handle."""
    def cap():
        with lock:
            return fn()
    return cap


class Tap:
    """What the driver COMMANDED, observed without editing anything.

    Nothing in this project exposes the current stick state (grep: no
    `_LAST_STICK`, no `current_stick`, in analog_replay / walk_steps /
    slow_traverse / input_controller). `walk_leg` and `walk_forward` build the
    FIFO lines inline and keep nothing. So the only honest sources for `lx`,
    `ly` and `cam` are (a) nothing, or (b) watching the calls go past.

    This is (b): an in-process wrapper installed for the length of one run and
    removed in a `finally`. It EDITS NO FILE -- the SPEC forbids that, and this
    respects it. It also cannot break a run: the observation is inside its own
    try/except and the original callable is always invoked and its value
    returned.

    `cam` is the TARGET of the turn in flight, stamped when turn_to is called,
    so a frame taken mid-turn carries where the camera was going, not where it
    was. `heading` is where it was.
    """

    def __init__(self):
        self.axes = {"left_x": 0.0, "left_y": 0.0}
        self.cam = None
        self._undo = []

    def stick(self):
        return (self.axes["left_x"], self.axes["left_y"])

    def _see_send(self, lines):
        """PER LINE, so one line it cannot read does not cost it the rest.

        The wrapper below already swallows an exception from here, which is
        what keeps the run safe -- but swallowing it at that level would
        abandon the whole batch, and `left_x` and `left_y` arrive in ONE batch.
        Half a stick command is worse than none.
        """
        for line in lines:
            try:
                parts = str(line).split()
                if parts and parts[0] == "clear":
                    self.axes["left_x"] = self.axes["left_y"] = 0.0
                elif len(parts) >= 2 and parts[0] in self.axes:
                    self.axes[parts[0]] = round(int(parts[1]) / 32767.0, 4)
            except Exception:                                      # noqa: BLE001
                continue

    def install(self, log=print):
        import analog_replay
        self._wrap(analog_replay, "send", lambda a, k: self._see_send(a[0]))
        for mod_name in ("slow_traverse", "walk_steps"):
            try:
                mod = __import__(mod_name)
            except Exception:                                      # noqa: BLE001
                continue
            if hasattr(mod, "turn_to"):
                self._wrap(mod, "turn_to",
                           lambda a, k: setattr(self, "cam",
                                                a[0] if a else k.get("target")))
        log(f"  [tap] watching {len(self._undo)} call sites for lx/ly and cam")
        return self

    def _wrap(self, mod, attr, observe):
        orig = getattr(mod, attr)

        def wrapper(*a, **k):
            try:
                observe(a, k)
            except Exception:                                      # noqa: BLE001
                pass                    # observing must never break the run
            return orig(*a, **k)

        setattr(mod, attr, wrapper)
        self._undo.append((mod, attr, orig))

    def remove(self):
        while self._undo:
            mod, attr, orig = self._undo.pop()
            setattr(mod, attr, orig)

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.remove()
        return False


def _default_name():
    return "route_" + time.strftime("%Y%m%d_%H%M%S")


def _chains_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chains")


def _warm_ocr(capture, log=print):
    """One compass read ON THE MAIN THREAD, before any thread asks for one."""
    import compass
    import ocr_glyphs
    try:
        b = compass.read_bearing(capture())
    except Exception as exc:                                       # noqa: BLE001
        b = f"failed: {exc!r}"
    log(f"  OCR warmed on the main thread: backend {ocr_glyphs.backend()}, "
        f"first bearing {b}")


def _drive_executor(name, attempts, period, use_tap, log=print):
    """Reset, walk the EXISTING dead-reckoning route, record it as a chain.

    The reset is NOT recorded: the chain must start at the spawn, because
    chain_walk trusts waypoint 0 as the spawn pose. Frames of the pause menu at
    the head of a chain are frames the controller would try to servo through.
    """
    import console_lock
    import compass
    import graph_walk as gw
    import reset_env
    import table_prompt
    import threading
    import worldmap as wm

    lock = threading.Lock()
    capture = serialised_capture(compass.fast_capture, lock)
    kept = None
    # A RESET INSIDE THE WALK POISONS THE CHAIN: go_to_node_verified reloads
    # the save when it cannot name its position, and the recorder would then
    # hold pause-menu frames and a SECOND spawn mid-chain, which the controller
    # (which trusts waypoint 0 as the spawn and walks the sequence) cannot
    # servo through. Count every reset graph_walk performs and discard the
    # attempt if there was one. graph_walk calls `reset_env.reset_environment`
    # through the module attribute, so wrapping the attribute sees them all.
    resets = {"n": 0}
    real_reset = reset_env.reset_environment

    def counting_reset(*a, **kw):
        resets["n"] += 1
        return real_reset(*a, **kw)

    # The goal leg as RECORDED rather than the chunked straight-line approach
    # plus a 19-heading sweep: same arrival odds (OPEN-21, p = 1.0) at a third
    # of the time, and a chain without a sweep in its tail. Restored after.
    goal_flag = gw.GOAL_LEG_AS_RECORDED
    with console_lock.held("chain_record"):
        _warm_ocr(capture, log=log)
        m = wm.WorldMap.load()
        tap = Tap()
        try:
            if use_tap:
                tap.install(log=log)
            for attempt in range(1, 4):
                directory = os.path.join(_chains_dir(), name)
                log(f"\n=== attempt {attempt}/3 -> {directory}")
                reset_env.reset_environment(log=log,
                                            progress_file="progress_testing.json")
                stop = threading.Event()
                box = {}
                resets["n"] = 0

                def run(directory=directory, stop=stop, box=box):
                    # Bound PER ATTEMPT on purpose: the loop rebinds all three,
                    # and a recorder thread that outlived th.join() wrote its
                    # count into the NEXT attempt's box (skeptic, 2026-09-07).
                    try:
                        box["n"] = record(
                            directory, capture, compass.read_bearing,
                            tap.stick if use_tap else (lambda: (None, None)),
                            period=period, stop_fn=lambda img: stop.is_set(),
                            cam_fn=(lambda: tap.cam) if use_tap else None,
                            log=log)
                    except BaseException as exc:                   # noqa: BLE001
                        # A recorder thread that dies quietly leaves a short
                        # chain that looks like a short walk.
                        box["error"] = repr(exc)
                        log(f"  !! THE RECORDER DIED: {exc!r}")

                th = threading.Thread(target=run, daemon=True)
                th.start()
                reset_env.reset_environment = counting_reset
                gw.GOAL_LEG_AS_RECORDED = True
                try:
                    gw.go_to_node_verified(m, gw.GOAL, capture=capture,
                                           log=log, attempts=attempts,
                                           start_hint=gw.SPAWN)
                finally:
                    reset_env.reset_environment = real_reset
                    gw.GOAL_LEG_AS_RECORDED = goal_flag
                    stop.set()
                    th.join(timeout=30.0)
                n = box.get("n", 0)
                arrived = bool(table_prompt.at_table(capture()))
                # A dead compass yields a chain that LOOKS complete (Snoopy's
                # review, verified): count what the controller will have to
                # turn by, and refuse a chain with no heading of either kind.
                h_ok, c_ok = heading_coverage(directory)
                log(f"  headings: compass {h_ok}/{n}, commanded cam {c_ok}/{n}")
                if n and h_ok == 0 and c_ok == 0:
                    log("  NO HEADING ON ANY FRAME -- the controller could not "
                        "turn; not keeping this chain")
                    arrived = False
                if resets["n"]:
                    log(f"  {resets['n']} reset(s) INSIDE the walk -- the chain "
                        f"holds a second spawn; not keeping it")
                    arrived = False
                log(f"  {directory}: {n} frames, at_table={arrived}"
                    + (f", recorder error {box['error']}" if box.get("error") else ""))
                if arrived:
                    kept = directory
                    break
                failed = f"{directory}_failed_{attempt}"
                os.rename(directory, failed)
                log(f"  no prompt -- kept for evidence as {failed}")
        finally:
            tap.remove()
    return kept


def _drive_user(name, period, seconds, log=print):
    """The user drives. This sends NOTHING -- record_drive.py's shape."""
    import console_lock
    import compass
    import table_prompt

    directory = os.path.join(_chains_dir(), name)
    # The REAL controller, read the way record_drive already reads it, rather
    # than a second pygame path of my own. `_open_stick` returns None when no
    # controller is attached and never raises; that is not an error, it just
    # means lx/ly are null for this chain.
    rd, stick = None, None
    try:
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "overnight"))
        _ov = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overnight")
        if _ov not in sys.path:
            sys.path.insert(0, _ov)       # record_drive lives in overnight/
        # record_drive parses sys.argv AT IMPORT (its own CLI), so shield ours.
        _argv = sys.argv
        sys.argv = _argv[:1]
        try:
            import record_drive as rd
        finally:
            sys.argv = _argv
        stick = rd._open_stick()
    except Exception as exc:                                       # noqa: BLE001
        log(f"  no controller handle ({exc!r}) -- lx/ly will be null")
    log("  controller: " + ("found, logging the stick" if stick else
                            "NONE -- lx/ly will be 0.0 with note stick:unknown"))

    def stick_fn():
        v = rd._read_stick(stick) if (rd and stick) else None
        return (v["lx"], v["ly"]) if v else (None, None)

    t0 = time.time()
    verdict = {"arrived": False}

    def stop_fn(img):
        if table_prompt.at_table(img):
            verdict["arrived"] = True
            return True
        return time.time() - t0 > seconds

    with console_lock.held("chain_record"):
        _warm_ocr(compass.fast_capture, log=log)
        log(f"\n  recording to {directory} at {1.0/period:.1f} Hz -- "
            f"DRIVE NOW. It stops itself at the dealer prompt; Ctrl-C to stop.")
        n = record(directory, compass.fast_capture, compass.read_bearing,
                   stick_fn, period=period, stop_fn=stop_fn, log=log)
    log(f"  {directory}: {n} frames, at_table={verdict['arrived']}")
    return directory


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    def opt(flag, default):
        return argv[argv.index(flag) + 1] if flag in argv else default

    name = opt("--name", _default_name())
    period = float(opt("--period", 0.25))
    attempts = int(opt("--attempts", 3))
    seconds = float(opt("--seconds", 600.0))
    use_tap = "--no-tap" not in argv

    if "--executor" in argv:
        _refuse_if_test_run()
        kept = _drive_executor(name, attempts, period, use_tap)
        print(f"\nchain: {kept or 'NONE KEPT -- three attempts, no prompt'}")
        return 0 if kept else 1
    if "--user" in argv:
        _refuse_if_test_run()
        _drive_user(name, period, seconds)
        return 0
    print(__doc__.strip().splitlines()[0])
    print("\n  .venv/bin/python -B chain_record.py --executor [--name X] "
          "[--period 0.25] [--attempts 3] [--no-tap]")
    print("  .venv/bin/python -B chain_record.py --user [--name X] "
          "[--seconds 600]")
    return 2


# GUARDED so the module imports with no side effects: a test that imports it
# must not acquire the console lock or start a capture session.
if __name__ == "__main__":
    sys.exit(main())
