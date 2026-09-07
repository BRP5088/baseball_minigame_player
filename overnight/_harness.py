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
import tempfile
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


def assert_map_pristine(path, log=print):
    """Refuse to start an A/B whose backup would bake in a previous run's arm.

    Every map-mutating harness does `shutil.copy(MAP, BACKUP)` at startup and
    restores from that backup at the end. If an earlier run CRASHED with its arm
    still installed, that backup is a copy of the arm — so the restore reinstates
    it, and the next run measures an arm against itself while reporting a clean
    A/B. Nothing errors; the map is valid JSON either way.

    The map is version-controlled, so "pristine" has an exact meaning: identical
    to the committed version. Set BASEBALL_ALLOW_DIRTY_MAP=1 to proceed anyway,
    which is correct when the map has been deliberately edited and committed-to-
    be — but it must be a decision, not a default.
    """
    if os.environ.get("BASEBALL_ALLOW_DIRTY_MAP"):
        log("  map cleanliness check SKIPPED (BASEBALL_ALLOW_DIRTY_MAP set)")
        return
    repo = os.path.dirname(os.path.abspath(path))
    try:
        r = subprocess.run(["git", "-C", repo, "diff", "--quiet", "--", path],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:
        # CANNOT TELL IS NOT CLEAN. Say so loudly rather than proceeding
        # silently, which is how the arm got baked in unnoticed.
        log(f"  WARNING: could not check whether {os.path.basename(path)} is "
            f"pristine ({type(e).__name__}: {e}). If a previous A/B crashed, "
            f"its arm may still be installed and this run will measure it.")
        return
    if r.returncode == 0:
        return
    raise SystemExit(
        f"{os.path.basename(path)} differs from the committed version. An A/B "
        f"backs the map up at startup and restores it at the end, so starting "
        f"from a modified map bakes whatever is in it into the backup and into "
        f"every trial of BOTH arms.\n"
        f"  git diff -- {path}          # see what changed\n"
        f"  git checkout -- {path}      # discard it and start clean\n"
        f"  BASEBALL_ALLOW_DIRTY_MAP=1  # proceed anyway, deliberately")


def _drain(fh, prefix, log, skip_json=False):
    """Emit whatever has been appended to `fh` since the last call.

    A partial final line is left in the file for the next poll: the reader's
    position only advances past a line once its newline has landed, so a line
    is never split across two log entries.
    """
    if log is None:
        return
    while True:
        pos = fh.tell()
        line = fh.readline()
        if not line.endswith("\n"):
            fh.seek(pos)          # incomplete — wait for the rest
            return
        line = line.rstrip("\n")
        # The trial's JSON result is the return value, not log output. Echoing
        # it would put a second `{`-line in the stream for the parser below to
        # trip over, and it is unreadable anyway.
        if skip_json and line.strip().startswith("{"):
            continue
        log(f"{prefix}{line}")


def run_trial(script, arg, timeout, cwd=None, log=None,
              check_stream=True):
    """Run one trial as a subprocess and return (result_dict_or_None, seconds).

    `script` is re-invoked as `python3 <script> --one-trial <arg>` and must
    print a single JSON object on its last line. A trial that times out, dies,
    or prints nothing parseable returns None — an INVALID trial, never a
    failure. Conflating "could not measure" with "did not arrive" is how a
    dying console got recorded as a navigation result.

    THE STREAM IS CHECKED AFTER THE TRIAL, HERE, ONCE. Every A/B harness checked
    it only BEFORE, so a console that fell asleep mid-leg produced a trial that
    ran to completion, arrived nowhere, and was scored as an ARM FAILURE. That is
    CLAUDE.md 10.6 exactly — a run where every arm degrades at once — and it has
    already cost one overnight run and contaminated one leg-tolerance A/B. Nine
    scripts had the hole; putting the check in the one function they all route
    through is the whole point of this module existing.

    THE CHILD'S OUTPUT IS FORWARDED LIVE, NOT SWALLOWED AND NOT BUFFERED. The
    child's stdout is the trial's own log — every `log(...)` call inside
    one_trial, including slow_traverse.turn_to's NO-OP/TURNED lines, which are
    the only instrument OPEN-3 has. Discarding it made `log=print` inside a
    trial functionally `lambda m: None`: the first entry in CLAUDE.md's
    catalogue, reintroduced one layer up in the harness that certifies every
    measurement. Pass `log=` to get it back.

    Holding it to the end was the same bug wearing a clock. See the streaming
    note in the body.
    """
    cwd = cwd or os.path.dirname(os.path.dirname(os.path.abspath(script)))

    # DECLARE THAT WE ARE DRIVING, AND REFUSE IF SOMETHING ELSE IS.
    #
    # This sits here rather than in each harness's main() because every live A/B
    # already routes through run_trial, so none of them has to remember -- and
    # "remember to turn keep_awake off first" is precisely the guard that failed
    # before. acquire() is idempotent for this pid, so calling it every trial
    # costs nothing and re-asserts the claim if a nudger cleared the file.
    #
    # The hazard is specific: a background nudge sends `clear`, which zeroes the
    # stick mid-leg while slow_traverse is sleeping out the push. The leg walks
    # short and NO LOG DISTINGUISHES THAT FROM A ROUTING FAILURE, so it would be
    # scored as an arm's failure. See console_lock.
    import console_lock
    console_lock.acquire(os.path.basename(script) + " (run_trial)")

    t0 = time.time()

    # THE CHILD'S OUTPUT IS STREAMED, NOT BUFFERED TO THE END.
    #
    # This used to be subprocess.run(capture_output=True), which holds every
    # line until the child exits. A trial takes 90-340s, so the harness printed
    # NOTHING for minutes at a time and a slow trial was indistinguishable from
    # a wedged one -- "a slow step and a hung step with identical output", which
    # is item seven in CLAUDE.md's own catalogue, and the exact thing
    # run_tests.sh grew a live progress line to fix one level up. Worse here:
    # the operator's only signal that an overnight run is alive is this log.
    #
    # Popen writing to real files rather than pipes, deliberately. Reading two
    # pipes from one thread deadlocks the moment either fills its buffer, and
    # threads-plus-kill is more moving parts than a two-hour measurement should
    # depend on. Files cannot deadlock, the whole stream is on disk for the JSON
    # parse at the end, and polling them costs a couple of stats a second.
    out_path = f"{tempfile.gettempdir()}/trial_{os.getpid()}_{arg}.out"
    err_path = f"{tempfile.gettempdir()}/trial_{os.getpid()}_{arg}.err"
    timed_out = False
    try:
        with open(out_path, "w") as ow, open(err_path, "w") as ew:
            p = subprocess.Popen(
                [sys.executable, os.path.abspath(script), "--one-trial", str(arg)],
                cwd=cwd, stdout=ow, stderr=ew, text=True)
            with open(out_path) as orr, open(err_path) as err:
                deadline = t0 + timeout
                while True:
                    _drain(orr, "      | ", log, skip_json=True)
                    _drain(err, "      ! ", log)
                    if p.poll() is not None:
                        break
                    if time.time() >= deadline:
                        # KILL, not terminate. CLAUDE.md 10.14: a trial blocked
                        # inside a capture did not answer SIGALRM, and signal
                        # handlers in this stack swallow the polite signals.
                        p.kill()
                        p.wait()
                        timed_out = True
                        break
                    time.sleep(0.5)
                _drain(orr, "      | ", log, skip_json=True)
                _drain(err, "      ! ", log)
        secs = round(time.time() - t0, 1)
        if timed_out:
            if log:
                log(f"    trial exceeded {timeout}s and was killed — INVALID, "
                    f"not a failure")
            return None, secs
        stdout = open(out_path).read()
    finally:
        for path in (out_path, err_path):
            try:
                os.remove(path)
            except OSError:
                pass

    parsed = None
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                break
            except ValueError:
                continue
    if parsed is None:
        return None, secs

    # Module-level `alive`, deliberately: a test can substitute it, and the
    # substitution is the only way to exercise this branch offline.
    if check_stream and not os.environ.get("BASEBALL_TEST_RUN"):
        if not alive():
            if log:
                log("    stream was DEAD after the trial — recording INVALID, "
                    "not a failure. The console cannot be told from the arm.")
            return None, secs
    return parsed, secs


_ROTATED = set()


def save_result(path, obj, indent=2):
    # `indent` matters for world_map.json, which humans read and which the map
    # audit compares by eye. Defaults to 2 for result files.
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
            json.dump(obj, fh, indent=indent)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def walk_leg_under_test(gw, m, start, target, shots=None, log=print,
                        attempts=1):
    """Walk ONE leg from a PROVEN `start` and return everything measurable.

    The caller must already have verified the character is standing at `start`;
    this walks a single execution of `start -> target` and reports it.

    WHY THIS IS NOT `gw.walk_link`. Two harnesses (ab_jukebox_leg,
    ab_stall_on_restored) called walk_link, which walks the leg and PUBLISHES NO
    LEG-END FRAME. `_LAST_LEG_END` is set inside follow(), immediately after its
    post-leg capture and BEFORE recover_to_node runs, and follow_verified is
    what pops it and classifies it. So both harnesses -- whose whole purpose is
    to report a leg's arrival BY FAILURE CLASS -- collected no evidence at all
    about the leg under test. There is no at_bar_jukebox frame anywhere on disk,
    and OPEN-1 says exactly that.

    ONE ATTEMPT BY DEFAULT, deliberately. The retrying primitive is a DIFFERENT
    quantity (OPEN-4 measured it at 10/10), and retries would hide precisely the
    difference a leg A/B exists to find. One attempt is one execution of the leg.

    `attempts` is raised only by an experiment whose SUBJECT is the retrying
    behaviour itself -- OPEN-7 compares two recovery strategies, so it must run
    the primitive as production runs it. Passing attempts>1 to a LEG comparison
    would be a measurement error, which is why the default is the safe one.

    `start_hint=start` is EVIDENCE, not an assumption: the caller proved it.

    THE FAN IS REPORTED SEPARATELY FROM ARRIVAL. recover_to_node travels roughly
    seven times the leg's own distance, so a trial it rescues is not evidence
    that the leg arrives. Scoring those as arrivals lets a bad leg pass by being
    rescued. It succeeded 2/31 historically, so the masking should be small --
    but "should be small" is not a measurement, so the count is recorded and the
    caller can subtract it.

    THE CENSUS CARRIES ITS PROVENANCE. A class counted off the pre-attempt view
    or the post-fan view is indistinguishable from one counted off the leg's own
    end, and a census that mixes them re-encodes WHICH node failed rather than
    HOW. `failure_kinds_leg_end` is the admissible subset; both are returned so
    that a shrinking denominator is visible rather than silent.
    """
    lines = []

    def tee(msg):
        lines.append(str(msg))
        log(msg)

    ok, _reached = gw.follow_verified(m, [target], log=tee, attempts=attempts,
                                      shots=shots, start_hint=start)

    # INDEPENDENT CONFIRMATION. follow_verified already believes only locate(),
    # so agreement is not news -- but a DISAGREEMENT would be, and it costs one
    # capture.
    where, detail = gw.locate(m, log=log)
    joined = "\n".join(lines)

    kinds = list(getattr(gw, "_LAST_FAILURE_KINDS", []))
    sources = list(getattr(gw, "_LAST_FAILURE_SOURCES", []))
    leg_end = [k for k, src in zip(kinds, sources)
               if src == getattr(gw, "LEG_END_SOURCE", None)]

    return {
        "reached_start": True,
        "arrived": where == target,
        "verified_arrived": bool(ok),
        "located": where,
        "detail": str(detail)[:120],
        "abandoned": "abandoning the rest of this leg" in joined,
        "stall_events": joined.count("stall score"),
        "steps_walked": joined.count("-> walked"),
        "fan_ran": ("recovery fan" in joined) or ("recovered " in joined),
        "fan_rescued": "recovered " in joined,
        "failure_kinds": kinds,
        "failure_sources": sources,
        "failure_kinds_leg_end": leg_end,
    }


# The measurements walk_leg_under_test produces, as recorded on a trial row.
# Named once so a harness cannot record a subset of them and then report a
# summary that silently omits whichever it forgot.
MEASURED_KEYS = ("located", "abandoned", "stall_events", "steps_walked",
                 "fan_ran", "fan_rescued", "verified_arrived",
                 "failure_kinds", "failure_sources", "failure_kinds_leg_end")


def leg_trial_row(arm, r, secs, arrived):
    """Build one result row from a walk_leg_under_test dict."""
    row = {"arm": arm, "arrived": arrived, "seconds": secs}
    row.update({k: r.get(k) for k in MEASURED_KEYS})
    return row


def report_leg_arm(name, rows, n_invalid, out=print):
    """Print one arm's result. Rows are the VALID trials for that arm.

    Reported BY CLASS and not only as a total, because an arrival rate averages
    several different failures together -- so a change that eliminates a whole
    class moves the overall rate by roughly a third of it, which is invisible at
    n=10. That is the leading explanation on this project for why so many
    well-motivated changes measured flat.
    """
    if not rows:
        out(f"  {name:9} NO VALID TRIALS ({n_invalid} invalid)")
        return
    n = len(rows)
    a = sum(1 for r in rows if r["arrived"])
    ab = sum(1 for r in rows if r.get("abandoned"))
    st = sum(r.get("stall_events") or 0 for r in rows)
    sw = sum(r.get("steps_walked") or 0 for r in rows)
    out(f"  {name:9} arrived {a}/{n} valid   ({n_invalid} invalid)")
    out(f"            abandoned by the stall gate: {ab}/{n}   "
        f"stall events {st}   steps walked {sw}")

    # ARRIVAL MINUS THE FAN. recover_to_node travels ~7x the leg's own distance,
    # so a trial it rescued is not evidence that the LEG arrives -- scoring
    # those as arrivals lets a bad leg pass by being rescued. Reported
    # alongside, never instead: dropping trials without saying so is how a
    # denominator goes missing.
    resc = sum(1 for r in rows if r.get("fan_rescued"))
    ran = sum(1 for r in rows if r.get("fan_ran"))
    out(f"            recovery fan ran {ran}/{n}, rescued {resc}"
        f"  -> arrived WITHOUT the fan: {a - resc}/{n}")

    # THE CENSUS, SPLIT BY PROVENANCE. `failure_kinds` mixes classes taken off
    # the pre-attempt view and the post-fan view in with the ones taken off the
    # leg's own end. OPEN-1 exists because a census built that way was reported
    # as evidence about a leg and was not. The leg-end line is the one to read;
    # both are printed so a shrinking denominator is visible, not silent.
    allk = tally_kinds(rows, "failure_kinds")
    legk = tally_kinds(rows, "failure_kinds_leg_end")
    n_all, n_leg = sum(allk.values()), sum(legk.values())
    if not n_all:
        out("            no failures classified (either none failed, or no "
            "frame was available -- check the per-trial log)")
        return
    out(f"            failures by class (ALL frames, n={n_all}): "
        + ", ".join(f"{k}={v}" for k, v in sorted(allk.items())))
    out(f"            failures by class (LEG-END frames only, n={n_leg}): "
        + (", ".join(f"{k}={v}" for k, v in sorted(legk.items())) or "none")
        + f"   [{n_all - n_leg} classified off a fallback frame and EXCLUDED "
          f"-- not evidence about the leg]")


def census_kinds(gw):
    """Per-trial failure classes SPLIT BY PROVENANCE. Report from `kinds_leg_end`.

    graph_walk appends `_LAST_FAILURE_KINDS` and `_LAST_FAILURE_SOURCES` in
    lockstep (graph_walk.py:2148-2151). The plain `kinds` list mixes frames
    taken at the leg's own end with FALLBACK frames -- `before` the attempt, or
    after the recovery fan -- which photograph a different moment and are not
    evidence about the leg (OPEN-1). Every harness used to record and report
    the mixed list; consecutive_arrivals split it in 2026-09-06 and nothing
    read the split. The honest headline is the leg-end subset, with the
    fallback count printed beside it so a shrinking denominator is visible
    rather than silent. `walk_leg_under_test` does the same split inline.

    If the two lists are not the same length the lockstep is broken and NOTHING
    is attributable: the leg-end list is empty and the mixed count is kept, so
    a corrupted census reads as "unattributed", never as "no failures".
    """
    kinds = list(getattr(gw, "_LAST_FAILURE_KINDS", []))
    sources = list(getattr(gw, "_LAST_FAILURE_SOURCES", []))
    leg_end = getattr(gw, "LEG_END_SOURCE", None)
    if len(sources) != len(kinds):
        return {"kinds": kinds, "kinds_leg_end": [], "kinds_fallback": [],
                "kinds_unattributed": len(kinds)}
    return {"kinds": kinds,
            "kinds_leg_end": [k for k, s in zip(kinds, sources) if s == leg_end],
            "kinds_fallback": [k for k, s in zip(kinds, sources) if s != leg_end]}


def report_kinds(rows, out=print, indent="  "):
    """Print the census the way it must be read: leg-end classes first."""
    le = tally_kinds(rows, "kinds_leg_end")
    fb = tally_kinds(rows, "kinds_fallback")
    legacy = [r for r in rows if r.get("kinds") and "kinds_leg_end" not in r]
    unatt = sum(r.get("kinds_unattributed", 0) for r in rows)
    out(f"{indent}failures by class, LEG-END frames only: {le or 'none'}")
    if fb:
        out(f"{indent}  plus {sum(fb.values())} classified from FALLBACK frames "
            f"(not evidence about the leg): {fb}")
    if unatt:
        out(f"{indent}  {unatt} failure(s) UNATTRIBUTED (kinds/sources lockstep broken)")
    if legacy:
        out(f"{indent}  {len(legacy)} row(s) carry only the legacy mixed 'kinds' key; not counted")


def tally_kinds(rows, key):
    """Count failure classes across trial rows. {} when there are none."""
    out = {}
    for r in rows:
        for k in (r.get(key) or []):
            out[k] = out.get(k, 0) + 1
    return out


def interleave(arms, trials=TRIALS):
    """Yield (trial_index, arm) with the arms alternating.

    Interleaving is not optional here. Route performance has a large
    session-to-session component that dwarfs the effects being measured, so
    blocking the arms would confound the arm with the hour.
    """
    for t in range(trials):
        for arm in arms:
            yield t, arm


# --- STRUCTURED TRIAL RECORDS ----------------------------------------------
#
# Every analysis on this project so far has meant grepping prose logs:
# `grep -c "NO-OP"`, counting "abandoning the rest of this leg", reading
# "arrived=False (located None, 4 step(s) walked, ABANDONED, 2 stall event(s))"
# back out of a line that was written for a human. That works once and does not
# compose — comparing two runs means writing a new regex, and comparing a run
# from last week means hoping the wording did not change.
#
# One JSONL row per trial fixes that. The schema is deliberately flat and
# additive: unknown keys are fine, missing keys are fine, and nothing here may
# ever raise into a trial. A harness that dies while recording a result is
# worse than one that records nothing.

TRIAL_SCHEMA_VERSION = 1


def record_trial(path, experiment, arm, trial, **fields):
    """Append one trial as a JSONL row. Never raises.

    `fields` carries whatever the experiment measured. The conventions that
    have earned their place, so cross-run queries can rely on them:

        arrived        True / False / None   None means INVALID, never failure
        invalid_reason str                   why, when arrived is None
        abandoned      bool                  the leg gave up partway
        stall_events   int                   how often the stall gate fired
        steps_walked   int                   of the leg's recorded steps
        seconds        float
        stream_alive   bool                  checked, not assumed

    The arrived=None convention is the important one. CLAUDE.md rule 6: CANNOT
    SEE is not DID NOT ARRIVE, and conflating them already invalidated a whole
    A/B on this project.
    """
    import json as _json
    import os as _os
    import time as _time
    try:
        row = {
            "v": TRIAL_SCHEMA_VERSION,
            "experiment": experiment,
            "arm": arm,
            "trial": trial,
            "t": _time.time(),
        }
        row.update(fields)
        _os.makedirs(_os.path.dirname(_os.path.abspath(path)), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(_json.dumps(row) + "\n")
            fh.flush()
            _os.fsync(fh.fileno())
    except Exception:
        pass          # bookkeeping must never end a run


def load_trials(path):
    """Read a JSONL trial file. Skips unreadable rows rather than dying."""
    import json as _json
    import os as _os
    out = []
    if not _os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(_json.loads(line))
        except ValueError:
            continue
    return out


def summarise(rows, experiment=None):
    """arm -> {arrived, valid, invalid, abandoned, stall_events, median_seconds}.

    Counts VALID trials in the denominator. A rate over a denominator that
    includes trials nobody could measure is the shape that has misled this
    project before.
    """
    import statistics
    by = {}
    for r in rows:
        if experiment and r.get("experiment") != experiment:
            continue
        a = by.setdefault(r.get("arm"), {"arrived": 0, "valid": 0, "invalid": 0,
                                         "abandoned": 0, "stall_events": 0,
                                         "seconds": []})
        if r.get("arrived") is None:
            a["invalid"] += 1
            continue
        a["valid"] += 1
        if r.get("arrived"):
            a["arrived"] += 1
        if r.get("abandoned"):
            a["abandoned"] += 1
        a["stall_events"] += r.get("stall_events") or 0
        if r.get("seconds"):
            a["seconds"].append(r["seconds"])
    for a in by.values():
        a["median_seconds"] = (round(statistics.median(a["seconds"]), 1)
                               if a["seconds"] else None)
        del a["seconds"]
    return by
