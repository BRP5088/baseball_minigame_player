"""Ten trials of the closed loop: reset, then servo along a recorded chain.

WHAT IS BEING MEASURED. Dead reckoning reaches the dealer prompt 5/10 per route
(CLAUDE.md §8(a)) after 13 measured changes, none of which moved the number
(GRAVEYARD.md). `chain_walk.walk()` replaces the replay with a loop that LOOKS
AFTER EVERY PUSH: position comes from the picture, never from the stick. This
scores it the same way, so the two are comparable: 10 trials, arrived / timed
out / failed, from the reset spawn to `table_prompt.at_table()`.

WHAT COUNTS AS WHAT, and why the distinctions are not pedantry:

    ARRIVED     walk() returned arrived=True — the PROMPT was on screen.
    TIMED_OUT   walk() hit its own 400s cap, or the child was killed at the
                420s external ceiling with the stream still alive. A slow walk
                is a result; it is not an arrival and it is not a dead console.
    FAILED      walk() returned without arriving for a reason of its own.
    INVALID     the stream was down, or the trial could not be measured at all.
                NEVER a failure. A console that falls asleep mid-run makes
                every arm degrade at once and looks exactly like a bad change;
                that has already cost one overnight run (CLAUDE.md §10.6).

METHOD, every clause a scar. The ceiling is enforced from OUTSIDE the process
via `_harness.run_trial`, because `signal.alarm` did not interrupt a 590s trial
blocked inside a screen capture (§10.14).

THE CEILING MUST COVER THE SETUP AS WELL AS THE WALK, and it did not. It was
420s against walk()'s own 400s cap — but the child spends its interpreter
start, the reset, sleep(1.2) and `Chain.load` (which runs ORB over EVERY
waypoint) BEFORE walk() starts its clock. All of that is inside the ceiling and
outside the cap, so walk() would have been killed at ~350s of its own 400s and
could never have reported its own timeout — and a killed child prints no JSON,
so the per-iteration `fixes` were lost on exactly the trials that needed
explaining. That is §10.14's other half: a ceiling censoring the very thing
being measured. The ceiling is now TIME_CAP + SETUP_BUDGET, the setup is timed
and reported, a setup that overruns its budget is INVALID rather than a
navigation failure, and chain_walk journals every iteration to disk as it
happens so a kill can no longer take the evidence with it.

Results are saved atomically after EVERY trial (§ the module docstring of
_harness): `open(path, "w")` truncates, and a crash in that window destroys an
hour of console time that cannot be re-run, because route performance has a
large session-to-session component. The console lock is held for the whole run
so a background nudger cannot end a push early and have the short leg scored as
a routing failure (see console_lock).

WHAT THIS NEVER DOES: it never edits world_map.json (chain_walk does not even
import it), never presses Square/Triangle/OPTIONS, and never starts a match.
The only money path in this project is the Square press at the prompt, and
nothing here presses it — reaching the prompt is the whole measurement.

    .venv/bin/python -B overnight/chain_trials.py <chain-name> [--trials N] [--no-shots]

`<chain-name>` is a directory under `chains/`, written by chain_record.py.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import _harness

TRIALS = _harness.TRIALS         # 10; n=3 has power 0.00 here
# Iterations the walk may spend ON the last waypoint before giving up. walk()
# derives 1 from OPEN-22's 0.05 u; 3 adds one push (0.18 u) for each side of
# the sensor's own +-1 waypoint placement error, so a fix that says "at the end"
# one waypoint early is not scored as a walk that landed off the prompt.
END_ITERATIONS = 3
TIME_CAP = 400.0                 # walk()'s own cap — the ">400 s" of the spec,
                                 # and it clocks THE WALK, nothing before it

# Everything the child spends before walk() starts its clock: interpreter start
# plus the cv2/numpy/tesserocr imports, `reset_env.reset_environment` (10-20s),
# sleep(1.2), and `Chain.load`, which runs ORB over every waypoint (~33ms a
# frame at 1920x1080, so ~45s for a 1360-waypoint chain).
#
# THIS IS A BUDGET, NOT A THRESHOLD. It is deliberately generous rather than
# sitting between two measured populations, because nothing here depends on it
# being tight: overrunning it costs one INVALID trial and says why, and the
# real distribution is reported (`setup_seconds` per trial) so the first live
# run measures it. §10.4 governs gates that DECIDE something; this one only
# decides how long to wait.
SETUP_BUDGET = 180.0
CEILING = int(TIME_CAP + SETUP_BUDGET)   # 580 — the external kill

CHAINS = os.path.join(ROOT, "chains")
OUT = os.path.join(HERE, "chain_trials.json")
SHOTS_ROOT = os.path.join(HERE, "chain_frames")
JOURNAL_ROOT = os.path.join(HERE, "chain_journals")
JOURNAL_ENV = "BASEBALL_CHAIN_JOURNAL"

ARRIVED, TIMED_OUT, FAILED, INVALID = "ARRIVED", "TIMED_OUT", "FAILED", "INVALID"

USAGE = (".venv/bin/python -B overnight/chain_trials.py <chain-name> "
         "[--trials N] [--no-shots]")


def _assert_live():
    """Refuse to send anything while the test flag is set.

    Set at CALL time, never at import: `tools/prompt_ocr_ab.py` set it at module
    level for its own offline run, `overnight/prompt_zone.py` imported it after
    walking a leg, and from that import every stick send was dropped silently —
    fifty "readings" of a camera that never turned (CLAUDE.md §5, §10.1).
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit(
            "BASEBALL_TEST_RUN is set: every input path is OFF, so this would "
            "walk a character that never moves and report the result as data.")


def chain_dir(name):
    if os.sep in name or (os.altsep and os.altsep in name) or name in (".", ".."):
        # run_trial builds its temp filenames from this argument, so a path
        # separator here writes the child's log into a directory that does not
        # exist and the trial dies with nothing to show for it.
        raise SystemExit(f"chain name must be a bare directory name under "
                         f"chains/, not {name!r}")
    return os.path.join(CHAINS, name)


def chain_size(d):
    """How many waypoints `d` holds, counted from meta.jsonl without ORB.

    The parent prints the ARITHMETIC before it spends ten trials, because k
    rises by at most WINDOW per iteration: a chain recorded at 0.25s over a
    244s route is ~1000 waypoints and needs >= 332 iterations, and at any
    plausible per-iteration cost that does not fit a 400s cap. Ten TIMED_OUTs
    with nothing beside them cannot be told from ten navigation failures.
    """
    try:
        with open(os.path.join(d, "meta.jsonl")) as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return None


def setup_verdict(setup_seconds, waypoints=None):
    """None when the setup fitted its budget; otherwise the trial's result.

    The setup (imports + reset + `Chain.load`'s ORB pass) is spent INSIDE the
    external ceiling and OUTSIDE walk()'s cap. If it eats more than the budget
    the ceiling reserved for it, the walk that follows would be killed before
    it could reach its own cap and report its own timeout — so the trial cannot
    measure what it exists to measure. That is NOT a navigation failure and
    must never be scored as one (§10.6: a run where the environment degrades
    looks exactly like a bad change), hence `setup_over_budget`, which
    `classify` maps to INVALID.
    """
    if setup_seconds < SETUP_BUDGET:
        return None
    return {"arrived": False, "setup_over_budget": True,
            "setup_seconds": round(setup_seconds, 1),
            "waypoints": waypoints,
            "failure": (f"setup took {setup_seconds:.0f}s of the "
                        f"{SETUP_BUDGET:.0f}s the {CEILING}s ceiling reserves "
                        f"for it, so the {TIME_CAP:.0f}s walk could not have "
                        f"run to its own cap — INVALID, not a failure")}


def config():
    """Every knob that DECIDES something in the walk, for the result file.

    A run whose own parameters are not in its own result file cannot be
    compared with the next one, and this project's record is that a constant
    changes and the comparison is made anyway (§10.7: the OPEN-4 10/10 and the
    flag that invalidated it share a commit message). `END_PUSH_UNITS` and the
    budget derived from it decide when the walk gives up at the last waypoint,
    so they belong here beside PUSH_MAG.
    """
    import chain_walk
    return {"PUSH_MAG": chain_walk.PUSH_MAG,
            "PUSH_SEC": chain_walk.PUSH_SEC,
            "MISS_MAX": chain_walk.MISS_MAX,
            "STALL_MAX": chain_walk.STALL_MAX,
            "WINDOW": chain_walk.WINDOW,
            "LATERAL_GAIN": chain_walk.LATERAL_GAIN,
            "LATERAL_MAG": chain_walk.LATERAL_MAG,
            "LATERAL_CAP_SEC": chain_walk.LATERAL_CAP_SEC,
            "LATERAL_TOL_PX": chain_walk.LATERAL_TOL_PX,
            "TABLE_CHECK_TAIL": chain_walk.TABLE_CHECK_TAIL,
            "END_PUSH_UNITS": chain_walk.END_PUSH_UNITS,
            "end_iteration_budget": chain_walk.end_iteration_budget()}


def one_trial(name):
    """The CHILD. Reset, load the chain, walk it once. Prints one JSON line."""
    _assert_live()
    t_start = time.time()
    shots = os.environ.get("BASEBALL_CHAIN_SHOTS", "1") != "0"
    journal = os.environ.get(JOURNAL_ENV) or None
    import compass
    import walk_steps as ws
    import chain as chain_mod
    import chain_walk
    import reset_env

    def log(m):
        print(m, flush=True)

    d = chain_dir(name)
    if not os.path.isdir(d):
        raise SystemExit(f"no such chain: {d}")

    reset_env.reset_environment(log=log, progress_file="progress_testing.json")
    time.sleep(1.2)               # the world has to finish appearing
    t_reset = time.time()

    ch = chain_mod.Chain.load(d, log=log)
    t_loaded = time.time()
    setup = t_loaded - t_start
    log(f"  setup {setup:.1f}s (reset {t_reset - t_start:.1f}s, "
        f"Chain.load {t_loaded - t_reset:.1f}s for {len(ch.waypoints)} "
        f"waypoints) of a {SETUP_BUDGET:.0f}s budget")
    over = setup_verdict(setup, waypoints=len(ch.waypoints))
    if over is not None:
        log(f"  {over['failure']}")
        over["chain"] = name
        return over

    shots_dir = None
    if shots:
        shots_dir = os.path.join(SHOTS_ROOT, f"t{int(time.time() * 1000)}")
    res = chain_walk.walk(ch, compass.fast_capture, ws.read_heading, log=log,
                          time_cap=TIME_CAP, shots=shots_dir, journal=journal,
                          end_iterations=END_ITERATIONS)
    # A second look 0.8 s later, recorded beside the verdict and never used to
    # score: at_table() measured 0 false positives on 693 clean frames, and
    # this is how the first live run measures it on ITS frames.
    time.sleep(0.8)
    try:
        import table_prompt
        res["at_table_recheck"] = bool(table_prompt.at_table(compass.fast_capture()))
    except Exception as exc:                                       # noqa: BLE001
        res["at_table_recheck"] = f"unreadable: {type(exc).__name__}"
    res["chain"] = name
    res["waypoints"] = len(ch.waypoints)
    res["shots"] = shots_dir
    res["journal"] = journal
    # NAMED FOR WHAT IT MEASURES. `res["seconds"]` is walk()'s own clock and the
    # parent renames it `walk_seconds`; these three say where the rest went.
    res["setup_seconds"] = round(setup, 1)
    res["reset_seconds"] = round(t_reset - t_start, 1)
    res["load_seconds"] = round(t_loaded - t_reset, 1)
    res["child_seconds"] = round(time.time() - t_start, 1)
    return res


def recover(path):
    """Read back what a KILLED child managed to write to its journal.

    `run_trial` returns None for a kill, so without this the per-iteration
    `fixes` — the whole point of a closed loop — are lost on precisely the
    trials that need explaining. chain_walk appends each row as it happens
    (§10.16: a file written on completion is lost in the case it exists for),
    so a truncated final line is expected and is skipped, not fatal.
    """
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass          # the kill landed mid-write; keep the rest
    except OSError:
        return {}
    if not rows:
        return {}
    return {"recovered": True, "fixes": rows,
            "k_final": rows[-1].get("k"),
            "iterations": max(r.get("iteration", 0) for r in rows),
            "pushes": sum(1 for r in rows if r.get("iteration", 0) >= 1)}


def trial_row(i, outcome, secs, r, journal=None):
    """One row of the result file. THE HARNESS-MEASURED FIELDS ALWAYS WIN.

    `row.update(r)` used to run LAST, and walk() returns a dict containing
    "seconds" — its own clock, which starts after the interpreter, the reset
    and `Chain.load`. So the trial's wall time was silently overwritten by a
    quantity a minute or more smaller, under the same name, and the summary
    median then averaged wall times (killed trials, which carry no `r`) with
    walk times (completed ones). Two different quantities reported as one is
    §10.1's "two paths with identical output"; the comparison this whole run
    exists for — against dead reckoning's 243.7s per trial, a WALL time — was
    against the wrong number.
    """
    row = {}
    if r is not None:
        row.update(r)
        if "seconds" in row:
            row["walk_seconds"] = row.pop("seconds")
    elif journal:
        row.update(recover(journal))
    row.update({"trial": i, "outcome": outcome, "seconds": secs})
    return row


def classify(r, secs, log):
    """One trial's outcome. `r` is None when nothing could be parsed."""
    if r is None:
        # run_trial returns None for a kill, a crash AND a dead stream, so ask
        # the console which it was rather than guessing. A killed trial on a
        # LIVE stream is a real (slow) result; anything else is unmeasurable.
        try:
            live = _harness.alive()
        except Exception as e:
            log(f"    could not check the stream: {type(e).__name__}: {e}")
            live = False
        if live and secs >= CEILING:
            return TIMED_OUT
        return INVALID
    if r.get("setup_over_budget"):
        return INVALID
    if r.get("arrived"):
        return ARRIVED
    if r.get("failure") == "timed out" or secs >= CEILING:
        return TIMED_OUT
    return FAILED


def main():
    _assert_live()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--trials" in sys.argv:
        args = [a for a in args if a != sys.argv[sys.argv.index("--trials") + 1]]
    if not args:
        raise SystemExit(USAGE)
    name = args[0]
    trials = TRIALS
    if "--trials" in sys.argv:
        trials = int(sys.argv[sys.argv.index("--trials") + 1])
    # The child is a fresh process, so the switch reaches it through the
    # environment it inherits. Set HERE, inside main() -- a flag set at import
    # time is how stick injection was silently switched off inside a live
    # harness (CLAUDE.md §5), and tests/harness scans this directory for it.
    if "--no-shots" in sys.argv:
        os.environ["BASEBALL_CHAIN_SHOTS"] = "0"

    d = chain_dir(name)
    if not os.path.isdir(d):
        raise SystemExit(f"no such chain: {d}")

    def log(m):
        print(m, flush=True)

    import console_lock
    import chain_walk

    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")

    res = {"question": "closed-loop chain walk from the reset spawn to the "
                       "dealer prompt, scored like the dead-reckoning route",
           "chain": name, "chain_dir": d, "trials": trials,
           "time_cap": TIME_CAP, "ceiling": CEILING,
           "setup_budget": SETUP_BUDGET,
           "config": config(),
           "runs": []}
    log(f"chain trials: {trials} of {name} "
        f"(walk cap {TIME_CAP:.0f}s + setup budget {SETUP_BUDGET:.0f}s = "
        f"external ceiling {CEILING}s)")
    log(f"  config {res['config']}")

    n = chain_size(d)
    res["waypoints"] = n
    if n:
        need = chain_walk.min_iterations(n)
        res["min_iterations"] = need
        res["iteration_budget_sec"] = round(TIME_CAP / need, 3)
        log(f"  {n} waypoints -> >= {need} iterations "
            f"(k rises by at most {chain_walk.WINDOW} each), so the "
            f"{TIME_CAP:.0f}s cap allows {res['iteration_budget_sec']:.2f}s "
            f"per iteration. An iteration is one turn, one push, three "
            f"captures and a locate — if that budget looks impossible, the "
            f"chain is too dense and every trial will TIME OUT for a reason "
            f"that is not navigation.")
    else:
        log(f"  WARNING: could not count {d}/meta.jsonl, so the iteration "
            f"arithmetic is unknown before the first trial")

    os.makedirs(JOURNAL_ROOT, exist_ok=True)
    with console_lock.held("chain_trials"):
        for i in range(1, trials + 1):
            # The child inherits this environment, so the journal path reaches
            # it without a second CLI argument (run_trial spawns exactly
            # `--one-trial <arg>`). Set HERE, inside main(), never at import.
            journal = os.path.join(
                JOURNAL_ROOT, f"{name}_t{i:02d}_{int(time.time())}.jsonl")
            os.environ[JOURNAL_ENV] = journal
            r, secs = _harness.run_trial(__file__, name, CEILING, log=log)
            outcome = classify(r, secs, log)
            row = trial_row(i, outcome, secs, r, journal=journal)
            row["journal"] = journal
            res["runs"].append(row)
            log(f"[{i:2d}] {outcome:9s} "
                f"k={row.get('k_final', '--')}/{row.get('waypoints', '--')}  "
                f"it={row.get('iterations', '--')}  "
                f"pushes={row.get('pushes', '--')}  "
                f"seconds={secs:.1f} (walk {row.get('walk_seconds', '--')}, "
                f"setup {row.get('setup_seconds', '--')})  "
                f"failure={row.get('failure')}"
                + ("  [rows RECOVERED from the journal]"
                   if row.get("recovered") else ""))
            if row.get("timeout_diagnosis"):
                log(f"     {row['timeout_diagnosis']}")
            _harness.save_result(OUT, res)

    got = [r for r in res["runs"] if r["outcome"] != INVALID]
    arrived = sum(1 for r in got if r["outcome"] == ARRIVED)
    res["arrived"] = arrived
    res["valid"] = len(got)
    res["invalid"] = len(res["runs"]) - len(got)
    log("")
    log(f"  arrived {arrived}/{len(got)} valid "
        f"({res['invalid']} invalid, never counted as failures)")
    for kind in (TIMED_OUT, FAILED):
        log(f"  {kind}: {sum(1 for r in got if r['outcome'] == kind)}")
    if got:
        # WALL seconds, every trial measured the same way — that is what makes
        # this comparable with dead reckoning's 243.7s per trial (§8(a)).
        secs = sorted(r["seconds"] for r in got)
        log(f"  wall seconds median {secs[len(secs) // 2]:.0f} "
            f"[{secs[0]:.0f}..{secs[-1]:.0f}]")
        walked = sorted(r["walk_seconds"] for r in got
                        if r.get("walk_seconds") is not None)
        if walked:
            log(f"  of which WALKING, median {walked[len(walked) // 2]:.0f} "
                f"[{walked[0]:.0f}..{walked[-1]:.0f}] "
                f"(n={len(walked)}; the rest is reset + Chain.load)")
    # A TIMED_OUT whose chain was too long to finish is not a navigation
    # result, and the two need opposite responses. chain_walk says which.
    arith = [r for r in got if str(r.get("timeout_diagnosis", ""))
             .startswith("ARITHMETIC")]
    if arith:
        log(f"  WARNING: {len(arith)} of the timeouts were ARITHMETIC — the "
            f"chain needs more iterations than the cap allows, whatever the "
            f"navigation did. Record a sparser chain or raise the cap before "
            f"reading these as failures.")
        log(f"    {arith[0]['timeout_diagnosis']}")
    _harness.save_result(OUT, res)
    log(f"\n  -> {OUT}")
    log("  Every iteration's fix is in each run's 'fixes' — read them before "
        "changing a constant; that list is the whole point of a closed loop.")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        print(json.dumps(one_trial(sys.argv[2])), flush=True)
    else:
        main()
