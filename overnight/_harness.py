"""Shared pieces for the A/B harnesses in this directory.

Every script here was copy-pasted from its predecessor, so every script here
inherited the same four defects. They are fixed once, here, so they cannot be
re-copied.

1. TIMEOUTS MUST BE ENFORCED FROM OUTSIDE THE PROCESS. `signal.alarm` does not
   interrupt a trial blocked inside a screen capture — measured 2026-09-03, a
   590s trial sailed past a 260s alarm. Six scripts still arm one. `run_trial`
   spawns the work as a subprocess so the kill is real.

2. NEVER PASS `log=lambda *a: None` TO THE MEASUREMENT CALL. It is the first
   entry in this project's own diagnosis catalogue. follow_verified reports
   failure_kind.classify(), per-node detail, align dx and commanded-vs-achieved
   bearings ONLY through log, so discarding it throws away everything needed to
   report arrival BY CLASS — and reporting only the total is the leading
   explanation for why so many changes measured flat.

3. CHECK THE STREAM BEFORE AND AFTER EVERY TRIAL. A console that falls asleep
   mid-run makes both arms degrade together and looks exactly like a failed
   change. Record None, never a failure. This already invalidated one whole A/B.

4. RESULTS MUST BE WRITTEN ATOMICALLY. Every script saved with
   `json.dump(res, open(path, "w"))`: `open(..., "w")` TRUNCATES first, so the
   file is empty or half-written for the duration of the dump. A Ctrl-C, a
   crash, or a full disk in that window destroys the whole run — which here is
   up to two hours of console time that cannot simply be re-run, because route
   performance has a large session-to-session component. `save_result` writes a
   temp file, fsyncs it, and renames it into place, exactly as
   `orchestrator._atomic_write_json` does for progress.json.

TRIALS is 10 because n=3 has power 0.00 here and n=10 has 0.94.
"""
import json
import os
import shutil
import subprocess
import sys
import time

TRIALS = 10                 # the documented minimum; n=3 has power 0.00
STREAM_DELTA_MIN = 0.35     # below this the picture is not updating


def alive(gap=1.0):
    """Is the stream actually delivering new frames?

    Deliberately NOT compass.read_bearing(): that has to identify a LETTER and
    fails on ~6% of healthy world frames, so it answers a different question
    and answers it wrongly. This asks only whether pixels changed.
    """
    import numpy as np
    import compass
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) > STREAM_DELTA_MIN


def run_trial(script, arg, timeout, cwd=None):
    """Run one trial as a subprocess and return (result_dict_or_None, seconds).

    `script` is re-invoked as `python3 <script> --one-trial <arg>` and must
    print a single JSON object on its last line. A trial that times out, dies,
    or prints nothing parseable returns None — an INVALID trial, never a
    failure. Conflating "could not measure" with "did not arrive" is how a
    dying console got recorded as a navigation result.
    """
    cwd = cwd or os.path.dirname(os.path.dirname(os.path.abspath(script)))
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, os.path.abspath(script), "--one-trial", str(arg)],
            cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, round(time.time() - t0, 1)
    secs = round(time.time() - t0, 1)
    for line in reversed((r.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line), secs
            except ValueError:
                continue
    return None, secs


_ROTATED = set()


def save_result(path, obj):
    """Write a run's results to `path` so an interrupted write cannot destroy
    what is already on disk.

    Same guarantee, and the same three steps, as
    `orchestrator._atomic_write_json`: write a temp file, flush + fsync it, then
    `os.replace` it over the destination. `os.replace` is atomic, so a reader
    (or the next run, or a human) sees either the complete previous file or the
    complete new one, never a truncated one. On any failure the temp is removed
    rather than left orphaned next to the real result inviting the question of
    which one is real — and the exception is re-raised, because the callers
    already propagated a failed `json.dump` and this must not quietly start
    swallowing a disk that is full.

    TWO THINGS THIS DOES THAT THE ORCHESTRATOR'S VERSION DOES NOT, both because
    these files are written repeatedly by long-lived, restartable runs:

    * THE TEMP NAME CARRIES THE PID. A shared `<path>.tmp` is not safe against
      two runs of one script: writer A truncates the temp while B is mid-dump,
      and B then renames a spliced file into place — atomic, and wrong. A
      per-process temp means the file that lands is always one whole run's
      results. (The result PATH deliberately does NOT carry a run id: see the
      note at the bottom of this docstring.)

    * THE PREVIOUS RUN'S FILE IS KEPT ONCE, as `<path>.prev`, on this process's
      first save to that path. Today the first trial of a new run overwrites a
      finished run's results outright; `overnight/ab_leg_tolerance_run1.json`
      is a copy somebody took by hand to stop exactly that. Keeping it is never
      worse than not keeping it — it costs the archive one extra restart before
      it is overwritten — and it can never break a run: every failure here is
      swallowed, because bookkeeping must not end a two-hour measurement.

      It is a COPY, not a rename, and that is not a detail. A mutation test
      caught the rename version: it moved the finished run aside and THEN
      started writing, so an interrupt during that first write left no result
      file at all — the exact failure this function exists to prevent, merely
      relocated. Copying keeps `path` complete and valid at every instant.

    WHY THE PATH HAS NO RUN ID. It was considered and declined. Nothing globs
    these files; the one cross-script read is by fixed name
    (`phase1_step4_rerecord.py` reads `phase1/step3_result.json`), and the
    write-ups in CLAUDE.md cite them by fixed name too, so a timestamped file
    is a file nobody can find. More importantly these A/Bs drive ONE console:
    two concurrent runs corrupt each other's MEASUREMENT, not just their file,
    and giving them separate filenames would hide that behind two
    plausible-looking result sets.
    """
    path = os.path.abspath(path)
    if path not in _ROTATED:
        _ROTATED.add(path)
        keep = f"{path}.{os.getpid()}.keep"
        try:
            if os.path.getsize(path) > 0:
                shutil.copyfile(path, keep)       # COPY: `path` stays valid...
                os.replace(keep, path + ".prev")  # ...even if this run dies now
        except OSError:
            try:
                os.remove(keep)
            except OSError:
                pass                  # absent, or unreadable — either is fine
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(obj, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def interleave(arms, trials=TRIALS):
    """Yield (trial_index, arm) with the arms alternating.

    Interleaving is not optional here. Route performance has a large
    session-to-session component that dwarfs the effects being measured, so
    blocking the arms would confound the arm with the hour.
    """
    for t in range(trials):
        for arm in arms:
            yield t, arm
