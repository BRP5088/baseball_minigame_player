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

ATTEMPTS PER TRIAL (patch52). A trial may spend more than one walk, each after
its OWN reset, stopping at the first arrival: at the measured per-walk 0.874
(n=207, batch 16 on) a single walk gives P(25 consecutive) = 3.5%, and CLAUDE.md
8(c) records retrying as the only lever with the leverage to close that. It
DEFAULTS TO ONE, so a run without `--attempts` is exactly the run it was. The
first attempt of every trial is its own control -- same session, same build --
so `arrived_first_attempt` stays comparable with every batch before it and no
interleaved A/B is needed (10.5).

    .venv/bin/python -B overnight/chain_trials.py <chain-name> [--trials N] [--no-shots]
                                                  [--attempts N]

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
# 180 s: every arrival so far took 90-126 s (batches 4-5, n=21) and nothing that ran
# past 150 s ever arrived; the user watched a wanderer burn the old 400 s cap and
# asked for a tighter one (2026-09-07 20:35). Over the cap scores TIMED_OUT.
TIME_CAP = 180.0                 # walk()'s own cap — the ">400 s" of the spec,
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
# WALKS ONE TRIAL MAY SPEND (patch52), each after its OWN reset, stopping at the
# first arrival. ONE is today's behaviour exactly; the value reaches the child
# through the environment, set inside main(). Per-walk arrival is 0.874 over 207
# trials (batch 16 on), so a single walk gives P(25 consecutive) = 3.5%, and
# CLAUDE.md 8(c) measured retrying as the lever that closes that gap for the
# dead-reckoning executor (attempts=9 9/9 vs attempts=3 5/10, p = 0.0325).
# WHETHER IT TRANSFERS IS THE OPEN QUESTION: it rests on the obstacle not still
# standing there after the reload, and the evidence for that is one weak
# conditional (P(fail | previous trial failed) 1/24 against 23/173, p = 0.32).
# The first attempt of every trial is its own control, so the batch measures
# both halves at once.
ATTEMPTS = 1
ATTEMPTS_ENV = "BASEBALL_CHAIN_ATTEMPTS"
# A MISSING GAME WINDOW is not a trial result (patch48). game_window_rect()
# lists ON-SCREEN windows only, so a Space switch or a fullscreen app in front
# of chiaki makes it None; the child then dies in reset_environment within a
# second and the parent scored INVALID and moved on -- 12 of an A/B's 20
# trial numbers went that way in ~15 s on 2026-09-08. The child now waits for
# the window before its reset; the parent re-runs an INVALID number after
# waiting, a bounded number of times, keeping the INVALID row marked.
WINDOW_WAIT_SEC = 120.0
WINDOW_POLL_SEC = 3.0
WINDOW_RETRY_MAX = 2


def wait_for_game_window(log, probe=None, sleep=time.sleep, clock=time.monotonic,
                         max_sec=None):
    """True once a chiaki game window is on screen, False after max_sec."""
    if probe is None:
        import input_controller
        probe = input_controller.game_window_rect
    if max_sec is None:
        max_sec = WINDOW_WAIT_SEC
    t0 = clock()
    waited = False
    while True:
        if probe() is not None:
            if waited:
                log(f"  chiaki game window back after {clock() - t0:.0f}s")
            return True
        if clock() - t0 >= max_sec:
            log(f"  no chiaki game window on screen for {max_sec:.0f}s")
            return False
        if not waited:
            log(f"  no chiaki game window on screen (another Space, a fullscreen "
                f"app in front, or the stream reconnecting); waiting up to "
                f"{max_sec:.0f}s")
            waited = True
        sleep(WINDOW_POLL_SEC)


def retry_this_trial(outcome, retries):
    """Re-run an INVALID trial number, at most WINDOW_RETRY_MAX times."""
    return outcome == INVALID and retries < WINDOW_RETRY_MAX


def attempts_from_argv(argv=None):
    """`--attempts N` from the PARENT's command line, or ATTEMPTS.

    Read at CALL time from argv, never captured in a default (CLAUDE.md 10.18).
    """
    argv = list(sys.argv if argv is None else argv)
    if "--attempts" not in argv:
        return ATTEMPTS
    i = argv.index("--attempts")
    if i + 1 >= len(argv):
        raise SystemExit("--attempts takes a count, e.g. --attempts 2")
    return _attempts_value(argv[i + 1], "--attempts")


def attempts_per_trial(env=None):
    """How many walks THIS CHILD may spend, from the environment it inherited.

    The environment is read at CALL time so a test can hand it one, and the
    parent sets it inside main(): a flag set at import is how stick injection
    was silently switched off inside a live harness (CLAUDE.md 5, 10.1).
    """
    env = os.environ if env is None else env
    raw = env.get(ATTEMPTS_ENV)
    if raw is None:
        return ATTEMPTS
    return _attempts_value(raw, ATTEMPTS_ENV)


def _attempts_value(raw, where):
    """A whole number of walks, >= 1. REFUSED rather than silently defaulted.

    A typo that fell back to 1 would run a plain batch while the log, the
    result file and the reader all said `--attempts 2` -- 10.1's no-op that
    reports like a change, in the place where it costs the whole measurement.
    """
    try:
        n = int(str(raw).strip())
    except ValueError:
        raise SystemExit(f"{where} takes a whole number of walks, not {raw!r}")
    if n < 1:
        raise SystemExit(f"{where} must be at least 1, not {n}")
    return n


def ceiling_for(attempts):
    """The external kill for a trial allowed `attempts` walks.

    A TIMEOUT MUST NOT CENSOR THE ARM THAT SPENDS LONGER (CLAUDE.md 10.14).
    Two attempts is legitimately two resets, two setups and two walks, and a
    ceiling sized for one would kill exactly the trials the retry exists to
    produce -- which is how OPEN-5's 420s ceiling censored 3 of 6 deep-arm
    trials, and how this file's own 420s-against-a-400s-cap started.
    """
    return int((TIME_CAP + SETUP_BUDGET) * attempts)


def attempt_journal(journal, attempt):
    """Where attempt N writes its rows. Attempt 1 keeps the parent's path.

    chain_walk APPENDS, so two walks sharing one file would interleave two
    sequences of iteration numbers and `recover()` would read the pair as one
    walk -- a killed trial's evidence quietly wrong rather than absent, which
    is worse. Attempt 1 is byte for byte the path the parent set, so nothing
    about a single-attempt trial changes on disk.
    """
    if not journal or attempt <= 1:
        return journal
    return f"{journal}.a{attempt}"


def walk_attempts(attempts, reset, load, walk, log):
    """Up to `attempts` (reset, walk) cycles; stop at the first arrival.

    THE SEAM, deliberately with no console in it: `reset(attempt)` reloads the
    world, `load()` returns the chain and is called ONCE (Chain.load runs ORB
    over every waypoint), `walk(attempt, chain)` returns walk()'s own result.
    Its tests drive it with stubs.

    Returns the LAST walk's result with the attempt bookkeeping added, so a
    retried arrival can never be mistaken for a first-walk one (10.1).
    """
    chain = None
    walks = []
    res = None
    for attempt in range(1, attempts + 1):
        reset(attempt)
        if chain is None:
            chain = load()
        try:
            res = walk(attempt, chain)
        except Exception as exc:                               # noqa: BLE001
            # A CRASH IS A FAILURE A RELOAD CAN ALSO FIX -- chain_walk raising
            # is not evidence the world is unwalkable -- but it is never
            # swallowed. The traceback goes to the log, the attempt is recorded
            # as an exception, and IF THIS WAS THE LAST ALLOWED ATTEMPT it is
            # RE-RAISED, so a default one-attempt run dies exactly as it dies
            # today: no JSON, the parent's run_trial returns None, INVALID.
            import traceback
            log(f"  walk {attempt} raised {type(exc).__name__}: {exc}")
            for line in traceback.format_exc().rstrip().splitlines():
                log(f"    {line}")
            if attempt >= attempts:
                raise
            res = {"arrived": False, "seconds": None, "exception": True,
                   "failure": f"exception: {type(exc).__name__}: {exc}"}
        row = {"attempt": attempt,
               "arrived": bool(res.get("arrived")),
               "walk_seconds": res.get("seconds"),
               "failure": res.get("failure"),
               "k_final": res.get("k_final")}
        for key in ("shots", "journal", "setup_seconds", "iterations",
                    "pushes", "setup_over_budget", "exception"):
            if key in res:
                row[key] = res[key]
        walks.append(row)
        if row["arrived"]:
            break
        if res.get("setup_over_budget"):
            # A slow console is not something a second walk can fix, and it is
            # never a navigation result (10.6). End the trial; classify() maps
            # it to INVALID either way.
            break
        if attempt < attempts:
            log(f"  walk {attempt} did not arrive ({res.get('failure')}); "
                f"attempt {attempt + 1} of {attempts} reloads and walks again")
    res = dict(res if res is not None else {})
    arrived_on = next((w["attempt"] for w in walks if w["arrived"]), None)
    res["attempts_allowed"] = attempts
    res["attempts_used"] = len(walks)
    res["arrived_on_attempt"] = arrived_on
    res["first_walk_arrived"] = bool(walks and walks[0]["arrived"])
    res["retried"] = len(walks) > 1
    res["walks"] = walks
    res["walk_exceptions"] = sum(1 for w in walks if w.get("exception"))
    res["walk_seconds_total"] = round(
        sum(w["walk_seconds"] or 0.0 for w in walks), 1)
    return res

CHAINS = os.path.join(ROOT, "chains")
OUT = os.path.join(HERE, "chain_trials.json")
SHOTS_ROOT = os.path.join(HERE, "chain_frames")
JOURNAL_ROOT = os.path.join(HERE, "chain_journals")
JOURNAL_ENV = "BASEBALL_CHAIN_JOURNAL"
# `--arms off,on` interleaves STOP_PAN_FROM_RUN across trials. The arm reaches
# the child through this variable and is applied INSIDE one_trial(), so process
# death is the restore and no cleanup can reinstate a stale default (§10.17).
PAN_ENV = "BASEBALL_CHAIN_PAN"
# ... and WHICH chain_walk attribute that value sets. `--flag NAME` names it;
# the default is the flag the option was built for, so every invocation
# written before `--flag` behaves exactly as it did. The name travels to the
# child beside the value, for the same reason (process death is the restore).
ARM_FLAG_ENV = "BASEBALL_CHAIN_ARM_FLAG"
DEFAULT_ARM_FLAG = "STOP_PAN_FROM_RUN"

ARRIVED, TIMED_OUT, FAILED, INVALID = "ARRIVED", "TIMED_OUT", "FAILED", "INVALID"

USAGE = (".venv/bin/python -B overnight/chain_trials.py <chain-name> "
         "[--trials N] [--attempts N] [--no-shots] [--arms off,on] "
         "[--flag CHAIN_WALK_FLAG]")


def arm_flag_name(argv=None):
    """The chain_walk attribute `--arms` switches, from `--flag NAME`.

    Read at CALL time from argv, never captured in a default (CLAUDE.md
    10.18): a module-level knob a test or a harness may redirect is resolved
    when it is used.
    """
    argv = list(sys.argv if argv is None else argv)
    if "--flag" in argv:
        i = argv.index("--flag")
        if i + 1 >= len(argv):
            raise SystemExit("--flag takes a chain_walk attribute name")
        return argv[i + 1]
    return DEFAULT_ARM_FLAG


def arm_label(flag):
    """The TEXT an arm's row and its tally line carry, from the flag it sets.

    THE DEFAULT FLAG KEEPS THE LABEL IT HAS ALWAYS HAD. Every `--arms off,on`
    written before `--flag` must produce the same bytes it did, so an old
    chain_trials.json's `pan-on` rows and tonight's compare row for row and a
    reader watching the log by eye sees no change -- the same rule this patch
    already applies to `res["pan"]`, which it leaves untouched beside the new
    `res["arm_flag"]`. A NAMED flag carries its own name, which is the point
    of naming it.
    """
    return "pan" if flag == DEFAULT_ARM_FLAG else flag


def apply_arm(chain_walk, log, env=None):
    """Set the armed flag INSIDE the child and say which one it was.

    Returns the attribute name, or None when no arm was requested. The
    environment is read at CALL time so a test can hand it one. A name that
    is not a chain_walk attribute is REFUSED rather than set: `setattr` on a
    typo binds something nothing reads, both arms then run the shipped
    default, and the A/B reports a clean interleave of one arm with itself --
    CLAUDE.md 10.1's no-op that logs like a change, in the one place where it
    costs the whole measurement.
    """
    env = os.environ if env is None else env
    arm = env.get(PAN_ENV)
    if arm is None:
        return None
    name = env.get(ARM_FLAG_ENV) or DEFAULT_ARM_FLAG
    if not hasattr(chain_walk, name):
        raise SystemExit(f"--flag names no chain_walk attribute: {name}")
    setattr(chain_walk, name, arm == "on")
    log(f"  arm: {name} = {getattr(chain_walk, name)}")
    return name


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
            # The stop-yaw family and the door step DECIDE something in the
            # walk, so a log that does not name them cannot be compared with
              # the next one -- this function's own reason for existing.
            "STOP_LOOK_YAW": chain_walk.STOP_LOOK_YAW,
            "STOP_YAW_NEAR_FIT_ONLY": chain_walk.STOP_YAW_NEAR_FIT_ONLY,
            "STOP_YAW_SKIP_LAST_STOP": chain_walk.STOP_YAW_SKIP_LAST_STOP,
            "DOOR_STOP_EXTRA_PUSH": chain_walk.DOOR_STOP_EXTRA_PUSH,
            "end_iteration_budget": chain_walk.end_iteration_budget()}


def one_trial(name):
    """The CHILD. Reset, load the chain, walk it. Prints one JSON line.

    Up to `attempts_per_trial()` walks (patch52), each after its OWN reset,
    stopping at the first arrival. The default is ONE, and with one this is
    the trial it has always been: one reset, one Chain.load, one walk.
    """
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

    armed = apply_arm(chain_walk, log)
    attempts = attempts_per_trial()

    d = chain_dir(name)
    if not os.path.isdir(d):
        raise SystemExit(f"no such chain: {d}")

    held = {}                     # the chain, loaded once and reused
    clock = {}                    # this attempt's setup timings

    def do_reset(attempt):
        # ATTEMPT 1'S CLOCK STARTS AT THE PROCESS START, so `setup_seconds`
        # keeps the meaning every earlier batch recorded (interpreter, the
        # cv2/tesserocr imports, the reset, Chain.load). A later attempt pays
        # only its own reset, and its row says so.
        clock["t0"] = t_start if attempt == 1 else time.time()
        if attempt > 1:
            log(f"  attempt {attempt}/{attempts}: resetting again")
        if not wait_for_game_window(log):
            raise SystemExit(f"no chiaki game window for "
                             f"{WINDOW_WAIT_SEC:.0f}s")
        reset_env.reset_environment(log=log,
                                    progress_file="progress_testing.json")
        time.sleep(1.2)           # the world has to finish appearing
        clock["t_reset"] = time.time()

    def do_load():
        held["chain"] = chain_mod.Chain.load(d, log=log)
        return held["chain"]

    def do_walk(attempt, ch):
        t_loaded = time.time()
        setup = t_loaded - clock["t0"]
        log(f"  setup {setup:.1f}s (reset {clock['t_reset'] - clock['t0']:.1f}s, "
            f"Chain.load {t_loaded - clock['t_reset']:.1f}s for "
            f"{len(ch.waypoints)} waypoints) of a {SETUP_BUDGET:.0f}s budget")
        over = setup_verdict(setup, waypoints=len(ch.waypoints))
        if over is not None:
            log(f"  {over['failure']}")
            return over
        shots_dir = None
        if shots:
            shots_dir = os.path.join(SHOTS_ROOT, f"t{int(time.time() * 1000)}")
        r = chain_walk.walk(ch, compass.fast_capture, ws.read_heading, log=log,
                            time_cap=TIME_CAP, shots=shots_dir,
                            journal=attempt_journal(journal, attempt),
                            end_iterations=END_ITERATIONS)
        r["shots"] = shots_dir
        r["journal"] = attempt_journal(journal, attempt)
        r["setup_seconds"] = round(setup, 1)
        r["reset_seconds"] = round(clock["t_reset"] - clock["t0"], 1)
        r["load_seconds"] = round(t_loaded - clock["t_reset"], 1)
        return r

    res = walk_attempts(attempts, do_reset, do_load, do_walk, log)
    if res.get("setup_over_budget"):
        res["chain"] = name
        return res
    ch = held["chain"]
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
    res["pan"] = bool(chain_walk.STOP_PAN_FROM_RUN)
    # WHICH flag this trial's arm set, and to what. `pan` above is kept
    # unchanged so every result recorded before `--flag` still reads the same.
    res["arm_flag"] = armed or DEFAULT_ARM_FLAG
    res["arm_value"] = bool(getattr(chain_walk, res["arm_flag"], False))
    res["waypoints"] = len(ch.waypoints)
    res["journal"] = journal
    # NAMED FOR WHAT IT MEASURES. `res["seconds"]` is the LAST walk's own clock
    # and the parent renames it `walk_seconds`; `setup_seconds`, `reset_seconds`
    # and `load_seconds` are that same attempt's, set beside it in do_walk, and
    # every attempt's own copy is in `walks`. `walk_seconds_total` is the sum
    # over the attempts, which is the quantity that grew -- two numbers that
    # differ must not share a name (10.1).
    res["child_seconds"] = round(time.time() - t_start, 1)
    return res


def fisher_exact(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]] (stdlib; the tables here
    are tiny). Sums the probability of every table at least as extreme."""
    import math
    n = a + b + c + d
    r1, c1 = a + b, a + c
    def prob(x):
        return (math.comb(r1, x) * math.comb(n - r1, c1 - x)) / math.comb(n, c1)
    p_obs = prob(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p_obs + 1e-12))


def recover(path, attempts=1):
    """The journal of the attempt that was IN FLIGHT when the child was killed.

    THE BASE PATH IS ALWAYS ATTEMPT 1'S. With more than one attempt (patch52)
    each walk journals to `attempt_journal(journal, n)`, so once attempt 1 has
    failed its file holds a COMPLETE, already-superseded walk. Reading it after
    a kill during attempt 2 returns a full `fixes` list and a clean k_final
    describing the wrong walk -- evidence that parses cleanly and is not about
    the thing that happened, which this project has already paid for twice
    (§10.15: check WHICH moment the frame captures; §10.1: a no-op path whose
    output looks like the working one). So scan from the HIGHEST attempt down.

    THE TEST IS EXISTENCE, NOT CONTENT. chain_walk creates the file with its
    first row, so a `.a2` that exists but holds nothing parseable still proves
    attempt 2 started; the row then carries `recovered_attempt` and NO `fixes`.
    Absent evidence, never the wrong evidence -- falling back to attempt 1's
    rows there would reintroduce exactly the defect this docstring describes.
    """
    if not path:
        return {}
    for attempt in range(max(1, int(attempts or 1)), 0, -1):
        p = attempt_journal(path, attempt)
        if not os.path.exists(p):
            continue
        out = {"recovered_attempt": attempt, "recovered_journal": p}
        out.update(_recover_rows(p))
        return out
    return {}


def _recover_rows(path):
    """Read back what a KILLED child managed to write to ONE journal file.

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


def trial_row(i, outcome, secs, r, journal=None, attempts=1):
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
    else:
        # A KILLED CHILD PRINTS NO JSON, so none of walk_attempts' attempt
        # bookkeeping reaches the row -- and the tally would then read the
        # trial as un-retried whatever it actually spent. The parent knows how
        # many attempts it ALLOWED, and the journal that exists says which one
        # was in flight, so both are recorded from this side.
        row["attempts_allowed"] = attempts
        if journal:
            row.update(recover(journal, attempts=attempts))
            a = row.get("recovered_attempt")
            if a is not None:
                row["attempts_used"] = a
                row["retried"] = a > 1
                if a > 1:
                    # PROVABLE: attempt 2 only ever starts after walk 1 came
                    # back without arriving. At attempt 1 it is NOT provable --
                    # a child can arrive and be killed before it prints -- so
                    # the key is left ABSENT rather than guessed False.
                    row["first_walk_arrived"] = False
    row.update({"trial": i, "outcome": outcome, "seconds": secs})
    return row


def trial_line(i, outcome, secs, row, armtxt=""):
    """The ONE LINE a human scans a batch by. A RETRY MUST BE VISIBLE ON IT.

    A trial that arrived on its first walk and one that failed, reloaded and
    arrived on its second printed the SAME BYTES: the structured record told
    them apart and the line a reader actually reads did not. That is CLAUDE.md
    10.1 -- a working path and a no-op path with identical output -- recurring
    at the log-reading layer, in a project whose habit is to read a batch as
    `outcomes [T,T,T,F,...]` off the log.

    THE MARKER GOES BEFORE `failure=`. tools/trial_sheet.py's LINE_RE ends
    `.*?failure=(.*)`, so anything appended AFTER it becomes part of the
    failure text of every row.
    """
    used = row.get("attempts_used") or 1
    mark = ""
    if used > 1:
        on = row.get("arrived_on_attempt")
        allowed = row.get("attempts_allowed", used)
        mark = (f"attempt {on}/{allowed}  " if on
                else f"attempts {used}/{allowed}  ")
    tail = ""
    if row.get("recovered"):
        a = row.get("recovered_attempt", 1)
        where = f"attempt {a}'s journal" if a > 1 else "the journal"
        tail = f"  [rows RECOVERED from {where}]"
    return (f"[{i:2d}] {outcome:9s} {armtxt}"
            f"k={row.get('k_final', '--')}/{row.get('waypoints', '--')}  "
            f"it={row.get('iterations', '--')}  "
            f"pushes={row.get('pushes', '--')}  "
            f"seconds={secs:.1f} (walk {row.get('walk_seconds', '--')}, "
            f"setup {row.get('setup_seconds', '--')})  "
            f"{mark}failure={row.get('failure')}" + tail)


def classify(r, secs, log, ceiling=None):
    """One trial's outcome. `r` is None when nothing could be parsed.

    `ceiling` is the external kill this trial actually ran under -- with more
    than one attempt it is `ceiling_for(attempts)`, not the single-walk
    CEILING, or a trial killed at its real ceiling would be read as a crash.
    Resolved at CALL time, never captured in a default (10.18).
    """
    if ceiling is None:
        ceiling = CEILING
    if r is None:
        # run_trial returns None for a kill, a crash AND a dead stream, so ask
        # the console which it was rather than guessing. A killed trial on a
        # LIVE stream is a real (slow) result; anything else is unmeasurable.
        try:
            live = _harness.alive()
        except Exception as e:
            log(f"    could not check the stream: {type(e).__name__}: {e}")
            live = False
        if live and secs >= ceiling:
            return TIMED_OUT
        return INVALID
    if r.get("setup_over_budget"):
        return INVALID
    if r.get("arrived"):
        return ARRIVED
    if r.get("failure") == "timed out" or secs >= ceiling:
        return TIMED_OUT
    return FAILED


def main():
    _assert_live()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--trials" in sys.argv:
        args = [a for a in args if a != sys.argv[sys.argv.index("--trials") + 1]]
    if "--attempts" in sys.argv:
        args = [a for a in args
                if a != sys.argv[sys.argv.index("--attempts") + 1]]
    arms = []
    if "--arms" in sys.argv:
        spec = sys.argv[sys.argv.index("--arms") + 1]
        args = [a for a in args if a != spec]
        arms = spec.split(",")
        if any(a not in ("off", "on") for a in arms):
            raise SystemExit("--arms takes off/on values, e.g. --arms off,on")
    flag = arm_flag_name()
    label = arm_label(flag)
    if "--flag" in sys.argv:
        args = [a for a in args if a != flag]
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
    # ... and how many walks each trial may spend. Set HERE, inside main(),
    # for the same reason, and the ceiling scales with it (10.14).
    attempts = attempts_from_argv()
    os.environ[ATTEMPTS_ENV] = str(attempts)
    ceiling = ceiling_for(attempts)

    d = chain_dir(name)
    if not os.path.isdir(d):
        raise SystemExit(f"no such chain: {d}")

    def log(m):
        print(m, flush=True)

    import console_lock
    import chain_walk

    # Refused in the PARENT as well as the child, so a typo costs one second
    # rather than a whole interleaved batch of one arm against itself.
    if not hasattr(chain_walk, flag):
        raise SystemExit(f"--flag names no chain_walk attribute: {flag}")

    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")

    res = {"question": "closed-loop chain walk from the reset spawn to the "
                       "dealer prompt, scored like the dead-reckoning route",
           "chain": name, "chain_dir": d, "trials": trials,
           "time_cap": TIME_CAP, "ceiling": ceiling,
           "setup_budget": SETUP_BUDGET,
           "attempts": attempts,
           "config": config(),
           "arms": arms,
           "arm_flag": flag,
           "runs": []}
    log(f"chain trials: {trials} of {name} "
        f"(walk cap {TIME_CAP:.0f}s + setup budget {SETUP_BUDGET:.0f}s "
        f"x {attempts} attempt{'s' if attempts != 1 else ''} = "
        f"external ceiling {ceiling}s)")
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
        i = 1
        window_retries = 0
        while i <= trials:
            # The child inherits this environment, so the journal path reaches
            # it without a second CLI argument (run_trial spawns exactly
            # `--one-trial <arg>`). Set HERE, inside main(), never at import.
            journal = os.path.join(
                JOURNAL_ROOT, f"{name}_t{i:02d}_{int(time.time())}.jsonl")
            os.environ[JOURNAL_ENV] = journal
            arm = arms[(i - 1) % len(arms)] if arms else None
            if arm is not None:
                os.environ[PAN_ENV] = arm
                # ... and WHICH flag it sets. Set HERE, inside main(), never
                # at import (CLAUDE.md 5, and tests/harness scans for it).
                os.environ[ARM_FLAG_ENV] = flag
            r, secs = _harness.run_trial(__file__, name, ceiling, log=log)
            outcome = classify(r, secs, log, ceiling=ceiling)
            row = trial_row(i, outcome, secs, r, journal=journal,
                            attempts=attempts)
            row["journal"] = journal
            if arm is not None:
                row["arm"] = f"{label}-{arm}"
            res["runs"].append(row)
            armtxt = f"{row['arm']:8s} " if arm is not None else ""
            log(trial_line(i, outcome, secs, row, armtxt))
            if row.get("timeout_diagnosis"):
                log(f"     {row['timeout_diagnosis']}")
            _harness.save_result(OUT, res)
            if retry_this_trial(outcome, window_retries):
                window_retries += 1
                row["window_retry"] = window_retries
                log(f"     INVALID: waiting for the game window, then re-running "
                    f"trial {i} ({window_retries}/{WINDOW_RETRY_MAX})")
                wait_for_game_window(log)
                _harness.save_result(OUT, res)
                continue
            window_retries = 0
            i += 1

    got = [r for r in res["runs"] if r["outcome"] != INVALID]
    arrived = sum(1 for r in got if r["outcome"] == ARRIVED)
    res["arrived"] = arrived
    res["valid"] = len(got)
    res["invalid"] = len(res["runs"]) - len(got)
    log("")
    log(f"  arrived {arrived}/{len(got)} valid "
        f"({res['invalid']} invalid, never counted as failures)")
    # THE FIRST WALK OF EVERY TRIAL IS ITS OWN CONTROL, measured in this same
    # session on this same build, so this is the number that compares with
    # every batch recorded before --attempts (0.874 over n=207). With one
    # attempt the two lines are equal, which checks the bookkeeping for free.
    first = sum(1 for r in got if r.get("first_walk_arrived"))
    res["arrived_first_attempt"] = first
    retried = [r for r in got if r.get("retried")]
    log(f"  of which on the FIRST walk {first}/{len(got)} "
        f"(the rate comparable with every batch before --attempts)")
    # ALWAYS SET, and NOT named `retried`. Every row carries `retried` as a
    # BOOL; a batch-level INT under the same name is two quantities wearing one
    # name (10.1), and a key that is absent rather than 0 when nothing retried
    # makes "no retries" indistinguishable from "an older result file".
    res["trials_retried"] = len(retried)
    res["retries_that_arrived"] = sum(1 for r in retried
                                      if r["outcome"] == ARRIVED)
    if retried:
        log(f"  a second or later walk was spent on {len(retried)} trials "
            f"and arrived on {res['retries_that_arrived']} of them")
    for kind in (TIMED_OUT, FAILED):
        log(f"  {kind}: {sum(1 for r in got if r['outcome'] == kind)}")
    if arms:
        tally = {}
        for a in arms:
            rs = [r for r in got if r.get("arm") == f"{label}-{a}"]
            tally[a] = (sum(1 for r in rs if r["outcome"] == ARRIVED), len(rs))
            log(f"  {label}-{a}: arrived {tally[a][0]}/{tally[a][1]} valid")
        if len(arms) == 2:
            (a1, n1), (a2, n2) = tally[arms[0]], tally[arms[1]]
            res["fisher_p"] = fisher_exact(a1, n1 - a1, a2, n2 - a2)
            log(f"  Fisher exact p = {res['fisher_p']:.4f}")
        res["tally"] = {a: {"arrived": t[0], "valid": t[1]} for a, t in tally.items()}
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
