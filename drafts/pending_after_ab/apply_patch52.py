"""patch52: ATTEMPTS PER TRIAL -- the closed loop gets its retry back.

WHAT IS MISSING. `overnight/chain_trials.py`'s `one_trial()` resets, loads the
chain and calls `chain_walk.walk()` EXACTLY ONCE; if that walk does not arrive
the trial is FAILED and the harness moves on. The dead-reckoning architecture
this replaced retried up to NINE times per node, and CLAUDE.md 8(c) calls
retrying "the only lever with the leverage" to reach 25 consecutive -- measured
there at attempts=9 9/9 against attempts=3 5/10, Fisher p = 0.0325, with the
DEEP arm's median LOWER because arriving is cheaper than exhausting attempts.
The closed loop dropped that lever when it dropped the executor.

THE ARITHMETIC (overnight/chain_trials_batch*.log, batch16 onward, n=207):

    per-walk arrival                     0.874  (181/207)
    P(25 consecutive) at 1 attempt        3.5%
    P(25 consecutive) at 2 attempts        67%   <- assuming independence
    P(25 consecutive) at 3 attempts        95%   <- assuming independence

A retry rests on the obstacle NOT still standing there after the reload. The
evidence that it is not:

    P(fail | the previous trial FAILED)    1/24  = 0.042
    P(fail | the previous trial ARRIVED)  23/173 = 0.133   Fisher p = 0.32

...which is the right direction and is WEAK. Twenty-four failures cannot
separate 0.04 from 0.13, and consecutive TRIALS are not the same thing as two
walks inside one trial. So the 67% and the 95% above are a projection, not a
measurement, and this patch does not claim them. What it claims is narrower:
the second walk is worth measuring, and this is the cheapest way to measure it.

WHY NO INTERLEAVED A/B IS NEEDED. THE FIRST ATTEMPT OF EVERY TRIAL IS ITS OWN
CONTROL. It runs in the same session, on the same build, under the same NPC
traffic, and it is scored separately (`first_walk_arrived`), so the
first-attempt rate is directly comparable to the 0.874 above and the second
attempt's CONDITIONAL rate -- arrivals among the walks that follow a failure --
is measured beside it in the same batch. That sidesteps CLAUDE.md 10.5's ban on
comparing across sessions entirely, and it is why `--attempts 2` is a plain
batch rather than `--arms`.

WHAT IT DOES.

  1. `ATTEMPTS = 1` and `BASEBALL_CHAIN_ATTEMPTS`. THE DEFAULT IS ONE, so the
     shipped behaviour is unchanged: the loop body runs once and the trial is
     exactly today's trial. The count reaches the child through the environment,
     set INSIDE main(), the same way `BASEBALL_CHAIN_SHOTS` and the arm flag
     already travel (never at import -- CLAUDE.md 5 and 10.17).
  2. `walk_attempts()` is the loop, and it is a SEAM with no console in it:
     reset, load and walk are passed in. Each attempt does its OWN reset --
     that is the entire mechanism, because a reload re-spawns the world and
     moves whatever was standing in the doorway. The chain is loaded ONCE
     outside the loop and reused; `Chain.load` runs ORB over every waypoint
     (~3 s at 205, ~45 s at 1360) and paying that twice would be pure waste.
  3. It stops at the FIRST arrival. A trial that arrives on attempt 1 costs
     exactly what it costs today, to the millisecond.
  4. THE RECORD DISTINGUISHES A RETRIED ARRIVAL FROM A FIRST-WALK ONE. This is
     CLAUDE.md 10.1, this project's signature failure -- a working path and a
     no-op path with identical output. The result carries `attempts_allowed`,
     `attempts_used`, `arrived_on_attempt` (None when none did),
     `first_walk_arrived`, `retried`, `walk_seconds_total`, and a per-attempt
     `walks` list holding each walk's own arrived/seconds/failure/k_final and
     its own shots directory and journal. Without those the first-attempt rate
     -- the only number comparable with every batch before tonight -- would be
     unrecoverable from the result file.
  5. THE CEILING SCALES WITH THE ATTEMPTS. `ceiling_for(n)` is
     `(TIME_CAP + SETUP_BUDGET) * n`, and main() passes it to `run_trial` and
     to `classify`. A ceiling sized for one walk would kill precisely the arm
     whose mechanism is "spend longer" -- CLAUDE.md 10.14, a mistake already
     made on this project once (OPEN-5's 420 s ceiling censored 3 of 6
     deep-arm trials) and again in this very file (the 420 s against a 400 s
     cap that the header paragraph records). The header line reports the
     scaled value, so what was spent is on the first line of the log.
  6. `--attempts N` on the parent, parsed the way `--trials` is, defaulting to
     ATTEMPTS so every invocation written before it behaves as it did.
  7. The tally reports BOTH `arrived` and `arrived_first_attempt`, so history
     stays comparable at a glance. With `--attempts 1` they are equal, which is
     a free consistency check on the bookkeeping.

WHAT IT IS NOT. No change to chain_walk, to any navigation rule or constant, to
TIME_CAP, SETUP_BUDGET or CEILING themselves, to `classify`'s verdicts, to the
row labels, or to what any existing field means. A setup that overruns its
budget still ends the TRIAL at once and still scores INVALID rather than a
navigation failure (10.6) -- it does not consume the remaining attempts, because
a slow console is not a thing a second walk can fix. Later attempts journal to
`<journal>.a2`, `.a3` ... so a killed child's `recover()` cannot splice two
walks' iteration numbers into one sequence; attempt 1 keeps the parent's exact
path, so nothing about a single-attempt trial changes on disk either.

WHAT THE SKEPTIC ROUND ADDED, each item a place where the record would have
been readable, well-formed and about the wrong thing:

  a. `recover()` READS THE ATTEMPT THAT WAS IN FLIGHT. The parent hands
     `trial_row` the canonical journal path, which is always ATTEMPT 1'S, and
     by the time attempt 2 is walking that file holds a COMPLETE, already-
     failed walk. A kill during attempt 2 therefore recovered a full `fixes`
     list and a clean `k_final` describing a different walk -- and it parses,
     so nothing downstream can tell. `recover(path, attempts=)` now scans from
     the highest attempt DOWN and takes the first journal that EXISTS.
     Existence, not content: chain_walk creates the file with its first row,
     so an empty `.a2` still proves attempt 2 started, and the row then
     carries `recovered_attempt` with NO `fixes` -- absent evidence, never the
     wrong evidence.
  b. THE PER-TRIAL LINE SAYS WHEN A RETRY WAS SPENT. A first-walk arrival and
     a reload-and-arrive printed the same bytes; the JSON told them apart and
     the line a human scans a batch by did not (10.1 at the log-reading
     layer). The line moved into `trial_line()` -- which also makes it
     testable at all, because main() cannot run offline -- and carries
     `attempt N/M` before `failure=`, because tools/trial_sheet.py's LINE_RE
     ends `.*?failure=(.*)` and anything after it joins the failure text.
  c. A WALK THAT RAISES NO LONGER FORFEITS THE REMAINING ATTEMPTS, and is
     never hidden: the traceback is logged, the attempt is recorded with
     `exception: True`, and on the LAST allowed attempt it is RE-RAISED -- so
     a default one-attempt run dies exactly as it dies today.
  d. A KILLED TRIAL KEEPS WHAT CAN BE PROVED. The row gets `attempts_allowed`
     from the parent and `attempts_used`/`retried` from the journal that was in
     flight; `first_walk_arrived` is set only when the recovered attempt is
     >= 2, where it follows from attempt 2 having started at all. At attempt 1
     it is left ABSENT rather than guessed, because a child can arrive and be
     killed before it prints.
  e. THE BATCH TALLY'S KEY IS `trials_retried`, not `retried`, and it and
     `retries_that_arrived` are always present as ints. Every ROW carries
     `retried` as a bool; the same name over two types at two scopes is the
     collision this project has already paid for.

WHAT IS STILL NOT COVERED, said plainly: `one_trial()` itself is never
EXECUTED by a test. It opens with `_assert_live()`, which refuses while
`BASEBALL_TEST_RUN` is set -- and clearing that flag to run it is the exact
accident CLAUDE.md 5 and 10.1 record (an import cleared it inside a live
harness and fifty "readings" came from a camera that never turned). The LOOP
is executed through `walk_attempts` with stubs; the closures one_trial builds
are pinned as SOURCE, one assertion per wire, and the test says so in its name.

    .venv/bin/python -B overnight/chain_trials.py <chain> --trials 25 --attempts 2

Usage: python apply_patch52.py [ROOT]      (asserts every anchor, THEN writes)
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
H = os.path.join(ROOT, "overnight", "chain_trials.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
h = open(H).read()
t = open(T).read()

edits_h = [
 # (1) the module docstring gains the retry and its usage line.
 ("""    .venv/bin/python -B overnight/chain_trials.py <chain-name> [--trials N] [--no-shots]

`<chain-name>` is a directory under `chains/`, written by chain_record.py.
""",
  """ATTEMPTS PER TRIAL (patch52). A trial may spend more than one walk, each after
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
"""),
 # (2) the constant and the env var, beside the ceiling they scale.
 ("""SETUP_BUDGET = 180.0
CEILING = int(TIME_CAP + SETUP_BUDGET)   # 580 — the external kill
""",
  """SETUP_BUDGET = 180.0
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
"""),
 # (3) the three helpers, after the last of the window-retry ones.
 ("""def retry_this_trial(outcome, retries):
    \"\"\"Re-run an INVALID trial number, at most WINDOW_RETRY_MAX times.\"\"\"
    return outcome == INVALID and retries < WINDOW_RETRY_MAX
""",
  """def retry_this_trial(outcome, retries):
    \"\"\"Re-run an INVALID trial number, at most WINDOW_RETRY_MAX times.\"\"\"
    return outcome == INVALID and retries < WINDOW_RETRY_MAX


def attempts_from_argv(argv=None):
    \"\"\"`--attempts N` from the PARENT's command line, or ATTEMPTS.

    Read at CALL time from argv, never captured in a default (CLAUDE.md 10.18).
    \"\"\"
    argv = list(sys.argv if argv is None else argv)
    if "--attempts" not in argv:
        return ATTEMPTS
    i = argv.index("--attempts")
    if i + 1 >= len(argv):
        raise SystemExit("--attempts takes a count, e.g. --attempts 2")
    return _attempts_value(argv[i + 1], "--attempts")


def attempts_per_trial(env=None):
    \"\"\"How many walks THIS CHILD may spend, from the environment it inherited.

    The environment is read at CALL time so a test can hand it one, and the
    parent sets it inside main(): a flag set at import is how stick injection
    was silently switched off inside a live harness (CLAUDE.md 5, 10.1).
    \"\"\"
    env = os.environ if env is None else env
    raw = env.get(ATTEMPTS_ENV)
    if raw is None:
        return ATTEMPTS
    return _attempts_value(raw, ATTEMPTS_ENV)


def _attempts_value(raw, where):
    \"\"\"A whole number of walks, >= 1. REFUSED rather than silently defaulted.

    A typo that fell back to 1 would run a plain batch while the log, the
    result file and the reader all said `--attempts 2` -- 10.1's no-op that
    reports like a change, in the place where it costs the whole measurement.
    \"\"\"
    try:
        n = int(str(raw).strip())
    except ValueError:
        raise SystemExit(f"{where} takes a whole number of walks, not {raw!r}")
    if n < 1:
        raise SystemExit(f"{where} must be at least 1, not {n}")
    return n


def ceiling_for(attempts):
    \"\"\"The external kill for a trial allowed `attempts` walks.

    A TIMEOUT MUST NOT CENSOR THE ARM THAT SPENDS LONGER (CLAUDE.md 10.14).
    Two attempts is legitimately two resets, two setups and two walks, and a
    ceiling sized for one would kill exactly the trials the retry exists to
    produce -- which is how OPEN-5's 420s ceiling censored 3 of 6 deep-arm
    trials, and how this file's own 420s-against-a-400s-cap started.
    \"\"\"
    return int((TIME_CAP + SETUP_BUDGET) * attempts)


def attempt_journal(journal, attempt):
    \"\"\"Where attempt N writes its rows. Attempt 1 keeps the parent's path.

    chain_walk APPENDS, so two walks sharing one file would interleave two
    sequences of iteration numbers and `recover()` would read the pair as one
    walk -- a killed trial's evidence quietly wrong rather than absent, which
    is worse. Attempt 1 is byte for byte the path the parent set, so nothing
    about a single-attempt trial changes on disk.
    \"\"\"
    if not journal or attempt <= 1:
        return journal
    return f"{journal}.a{attempt}"


def walk_attempts(attempts, reset, load, walk, log):
    \"\"\"Up to `attempts` (reset, walk) cycles; stop at the first arrival.

    THE SEAM, deliberately with no console in it: `reset(attempt)` reloads the
    world, `load()` returns the chain and is called ONCE (Chain.load runs ORB
    over every waypoint), `walk(attempt, chain)` returns walk()'s own result.
    Its tests drive it with stubs.

    Returns the LAST walk's result with the attempt bookkeeping added, so a
    retried arrival can never be mistaken for a first-walk one (10.1).
    \"\"\"
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
"""),
 # (4) the usage line the parent prints on a bad command line.
 ("""USAGE = (".venv/bin/python -B overnight/chain_trials.py <chain-name> "
         "[--trials N] [--no-shots] [--arms off,on] [--flag CHAIN_WALK_FLAG]")
""",
  """USAGE = (".venv/bin/python -B overnight/chain_trials.py <chain-name> "
         "[--trials N] [--attempts N] [--no-shots] [--arms off,on] "
         "[--flag CHAIN_WALK_FLAG]")
"""),
 # (5) classify takes the ceiling it should compare against.
 ("""def classify(r, secs, log):
    \"\"\"One trial's outcome. `r` is None when nothing could be parsed.\"\"\"
""",
  """def classify(r, secs, log, ceiling=None):
    \"\"\"One trial's outcome. `r` is None when nothing could be parsed.

    `ceiling` is the external kill this trial actually ran under -- with more
    than one attempt it is `ceiling_for(attempts)`, not the single-walk
    CEILING, or a trial killed at its real ceiling would be read as a crash.
    Resolved at CALL time, never captured in a default (10.18).
    \"\"\"
    if ceiling is None:
        ceiling = CEILING
"""),
 ("""        if live and secs >= CEILING:
            return TIMED_OUT
""",
  """        if live and secs >= ceiling:
            return TIMED_OUT
"""),
 ("""    if r.get("failure") == "timed out" or secs >= CEILING:
""",
  """    if r.get("failure") == "timed out" or secs >= ceiling:
"""),
 # (6) the child: the loop, its closures, and the chain loaded ONCE.
 ("""def one_trial(name):
    \"\"\"The CHILD. Reset, load the chain, walk it once. Prints one JSON line.\"\"\"
""",
  """def one_trial(name):
    \"\"\"The CHILD. Reset, load the chain, walk it. Prints one JSON line.

    Up to `attempts_per_trial()` walks (patch52), each after its OWN reset,
    stopping at the first arrival. The default is ONE, and with one this is
    the trial it has always been: one reset, one Chain.load, one walk.
    \"\"\"
"""),
 ("""    armed = apply_arm(chain_walk, log)

    d = chain_dir(name)
    if not os.path.isdir(d):
        raise SystemExit(f"no such chain: {d}")

    if not wait_for_game_window(log):
        raise SystemExit(f"no chiaki game window for {WINDOW_WAIT_SEC:.0f}s")
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
""",
  """    armed = apply_arm(chain_walk, log)
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
"""),
 ("""    res["waypoints"] = len(ch.waypoints)
    res["shots"] = shots_dir
    res["journal"] = journal
    # NAMED FOR WHAT IT MEASURES. `res["seconds"]` is walk()'s own clock and the
    # parent renames it `walk_seconds`; these three say where the rest went.
    res["setup_seconds"] = round(setup, 1)
    res["reset_seconds"] = round(t_reset - t_start, 1)
    res["load_seconds"] = round(t_loaded - t_reset, 1)
    res["child_seconds"] = round(time.time() - t_start, 1)
""",
  """    res["waypoints"] = len(ch.waypoints)
    res["journal"] = journal
    # NAMED FOR WHAT IT MEASURES. `res["seconds"]` is the LAST walk's own clock
    # and the parent renames it `walk_seconds`; `setup_seconds`, `reset_seconds`
    # and `load_seconds` are that same attempt's, set beside it in do_walk, and
    # every attempt's own copy is in `walks`. `walk_seconds_total` is the sum
    # over the attempts, which is the quantity that grew -- two numbers that
    # differ must not share a name (10.1).
    res["child_seconds"] = round(time.time() - t_start, 1)
"""),
 # (7) the parent: --attempts, exported to the child, and the scaled ceiling.
 ("""    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--trials" in sys.argv:
        args = [a for a in args if a != sys.argv[sys.argv.index("--trials") + 1]]
""",
  """    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--trials" in sys.argv:
        args = [a for a in args if a != sys.argv[sys.argv.index("--trials") + 1]]
    if "--attempts" in sys.argv:
        args = [a for a in args
                if a != sys.argv[sys.argv.index("--attempts") + 1]]
"""),
 ("""    if "--no-shots" in sys.argv:
        os.environ["BASEBALL_CHAIN_SHOTS"] = "0"
""",
  """    if "--no-shots" in sys.argv:
        os.environ["BASEBALL_CHAIN_SHOTS"] = "0"
    # ... and how many walks each trial may spend. Set HERE, inside main(),
    # for the same reason, and the ceiling scales with it (10.14).
    attempts = attempts_from_argv()
    os.environ[ATTEMPTS_ENV] = str(attempts)
    ceiling = ceiling_for(attempts)
"""),
 ("""           "time_cap": TIME_CAP, "ceiling": CEILING,
           "setup_budget": SETUP_BUDGET,
""",
  """           "time_cap": TIME_CAP, "ceiling": ceiling,
           "setup_budget": SETUP_BUDGET,
           "attempts": attempts,
"""),
 ("""    log(f"chain trials: {trials} of {name} "
        f"(walk cap {TIME_CAP:.0f}s + setup budget {SETUP_BUDGET:.0f}s = "
        f"external ceiling {CEILING}s)")
""",
  """    log(f"chain trials: {trials} of {name} "
        f"(walk cap {TIME_CAP:.0f}s + setup budget {SETUP_BUDGET:.0f}s "
        f"x {attempts} attempt{'s' if attempts != 1 else ''} = "
        f"external ceiling {ceiling}s)")
"""),
 ("""            r, secs = _harness.run_trial(__file__, name, CEILING, log=log)
            outcome = classify(r, secs, log)
""",
  """            r, secs = _harness.run_trial(__file__, name, ceiling, log=log)
            outcome = classify(r, secs, log, ceiling=ceiling)
"""),
 # (8) the tally reports both rates, so history stays comparable.
 ("""    log(f"  arrived {arrived}/{len(got)} valid "
        f"({res['invalid']} invalid, never counted as failures)")
""",
  """    log(f"  arrived {arrived}/{len(got)} valid "
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
"""),
 # (11) recover() reads the journal of the attempt that was IN FLIGHT.
 ('''def recover(path):
    """Read back what a KILLED child managed to write to its journal.
''',
  '''def recover(path, attempts=1):
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
'''),
 # (12) trial_row carries the attempt bookkeeping a killed child could not
 #      print, and the per-trial LINE says when a retry was spent.
 ("""def trial_row(i, outcome, secs, r, journal=None):
""",
  """def trial_row(i, outcome, secs, r, journal=None, attempts=1):
"""),
 ("""    row = {}
    if r is not None:
        row.update(r)
        if "seconds" in row:
            row["walk_seconds"] = row.pop("seconds")
    elif journal:
        row.update(recover(journal))
    row.update({"trial": i, "outcome": outcome, "seconds": secs})
    return row
""",
  '''    row = {}
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
'''),
 ("""            row = trial_row(i, outcome, secs, r, journal=journal)
""",
  """            row = trial_row(i, outcome, secs, r, journal=journal,
                            attempts=attempts)
"""),
 ("""            log(f"[{i:2d}] {outcome:9s} {armtxt}"
                f"k={row.get('k_final', '--')}/{row.get('waypoints', '--')}  "
                f"it={row.get('iterations', '--')}  "
                f"pushes={row.get('pushes', '--')}  "
                f"seconds={secs:.1f} (walk {row.get('walk_seconds', '--')}, "
                f"setup {row.get('setup_seconds', '--')})  "
                f"failure={row.get('failure')}"
                + ("  [rows RECOVERED from the journal]"
                   if row.get("recovered") else ""))
""",
  """            log(trial_line(i, outcome, secs, row, armtxt))
"""),
]

NEW_TESTS = '''    # -- patch52: attempts per trial ---------------------------------------
    #
    # walk_attempts() is the seam: reset, load and walk are injected, so the
    # loop is exercised with NO console, no chain and no chain_walk. Each
    # stubbed walk is a dict shaped like walk()'s own result.

    def _attempts(self, attempts, results):
        """Drive walk_attempts with stubs; return (result, call log)."""
        calls = []
        seq = list(results)

        def reset(attempt):
            calls.append(("reset", attempt))

        def load():
            calls.append(("load",))
            return "THE CHAIN"

        def walk(attempt, chain):
            calls.append(("walk", attempt, chain))
            return dict(seq.pop(0))

        return chain_trials.walk_attempts(attempts, reset, load, walk,
                                          self.log), calls

    ARRIVES = {"arrived": True, "seconds": 84.0, "k_final": 204}
    MISSES = {"arrived": False, "seconds": 180.0, "failure": "lost",
              "k_final": 129}

    def test_the_default_is_ONE_attempt_and_the_walk_runs_ONCE(self):
        # Literals (10.11): the shipped default, and the loop that honours it.
        self.assertEqual(chain_trials.ATTEMPTS, 1)
        self.assertEqual(chain_trials.attempts_per_trial(env={}), 1)
        res, calls = self._attempts(1, [self.MISSES])
        self.assertEqual(calls, [("reset", 1), ("load",),
                                 ("walk", 1, "THE CHAIN")])
        self.assertEqual(res["attempts_allowed"], 1)
        self.assertEqual(res["attempts_used"], 1)
        self.assertIsNone(res["arrived_on_attempt"])
        self.assertIs(res["retried"], False)
        self.assertIs(res["first_walk_arrived"], False)

    def test_an_arrival_on_the_first_walk_costs_no_second_walk(self):
        # A trial that arrives must cost exactly what it costs today. A wasted
        # second walk after an arrival would be 3 minutes of console time per
        # trial and a second $50 prompt approached for nothing.
        res, calls = self._attempts(2, [self.ARRIVES, self.MISSES])
        self.assertEqual([c[0] for c in calls], ["reset", "load", "walk"])
        self.assertEqual(res["attempts_used"], 1)
        self.assertEqual(res["arrived_on_attempt"], 1)
        self.assertIs(res["retried"], False)
        self.assertIs(res["first_walk_arrived"], True)
        self.assertEqual(len(res["walks"]), 1)

    def test_a_failed_first_walk_is_retried_after_its_OWN_reset(self):
        # THE MECHANISM: the reload is what moves the NPC out of the doorway,
        # so a retry without its own reset would re-walk the same world. And
        # the chain is loaded ONCE -- Chain.load runs ORB over every waypoint.
        res, calls = self._attempts(2, [self.MISSES, self.ARRIVES])
        self.assertEqual(calls, [("reset", 1), ("load",),
                                 ("walk", 1, "THE CHAIN"),
                                 ("reset", 2), ("walk", 2, "THE CHAIN")])
        self.assertEqual([c[0] for c in calls].count("load"), 1,
                         "Chain.load is 3-45s of ORB; paying it twice is waste")
        self.assertEqual([c[0] for c in calls].count("walk"), 2)
        self.assertEqual(res["attempts_used"], 2)
        self.assertEqual(res["arrived_on_attempt"], 2)
        self.assertTrue(res["arrived"], "the LAST walk's result is returned")
        self.assertTrue(any("attempt 2 of 2" in m for m in self.logs), self.logs)

    def test_a_RETRIED_arrival_is_distinguishable_from_a_FIRST_walk_one(self):
        # CLAUDE.md 10.1, this project's signature failure: a working path and
        # a no-op path with identical output. Without these fields the
        # first-attempt rate -- the only number comparable with the 0.874 over
        # n=207 -- would be unrecoverable from the result file.
        straight, _ = self._attempts(2, [self.ARRIVES])
        retried, _ = self._attempts(2, [self.MISSES, self.ARRIVES])
        self.assertTrue(straight["arrived"] and retried["arrived"])
        for key, a, b in (("arrived_on_attempt", 1, 2),
                          ("attempts_used", 1, 2),
                          ("first_walk_arrived", True, False),
                          ("retried", False, True)):
            self.assertEqual(straight[key], a, key)
            self.assertEqual(retried[key], b, key)
        # ... and each walk's own outcome and seconds, so the conditional rate
        # (arrivals among the walks that FOLLOW a failure) is countable.
        self.assertEqual([(w["attempt"], w["arrived"], w["walk_seconds"])
                          for w in retried["walks"]],
                         [(1, False, 180.0), (2, True, 84.0)])
        self.assertEqual(retried["walks"][0]["failure"], "lost")
        self.assertEqual(retried["walk_seconds_total"], 264.0)
        self.assertEqual(straight["walk_seconds_total"], 84.0)

    def test_a_setup_over_its_budget_ends_the_trial_and_spends_no_retry(self):
        # A slow console is not something a second walk can fix, and it is
        # never a navigation result (10.6). One reset, one walk, INVALID.
        over = chain_trials.setup_verdict(chain_trials.SETUP_BUDGET + 1,
                                          waypoints=205)
        res, calls = self._attempts(2, [over, self.ARRIVES])
        self.assertEqual([c[0] for c in calls], ["reset", "load", "walk"])
        self.assertEqual(res["attempts_used"], 1)
        self.assertIsNone(res["arrived_on_attempt"])
        self.assertEqual(
            chain_trials.classify(res, chain_trials.CEILING, self.log),
            chain_trials.INVALID)

    def test_the_ceiling_SCALES_with_the_attempts(self):
        # LITERALS, not recomputed from the constants under test (10.11) -- a
        # check that multiplies TIME_CAP + SETUP_BUDGET itself would pass
        # forever, including on a ceiling_for that ignores its argument.
        # A ceiling sized for one walk kills exactly the trials the retry
        # exists to produce (10.14; OPEN-5's 420s censored 3 of 6 deep trials).
        self.assertEqual(chain_trials.CEILING, 360)
        self.assertEqual(chain_trials.ceiling_for(1), 360)
        self.assertEqual(chain_trials.ceiling_for(2), 720)
        self.assertEqual(chain_trials.ceiling_for(3), 1080)
        # ... and classify compares against the ceiling the trial ACTUALLY ran
        # under: a two-attempt child killed at 700s of a 720s ceiling died on
        # its own, and reading it against the single-walk 360 would file it as
        # a slow arm's timeout. The three lines differ only in the ceiling.
        chain_trials._harness.alive = lambda: True
        self.assertEqual(chain_trials.classify(None, 700.0, self.log),
                         chain_trials.TIMED_OUT,
                         "at the SINGLE-walk ceiling, 700s is past the kill")
        self.assertEqual(
            chain_trials.classify(None, 700.0, self.log, ceiling=720),
            chain_trials.INVALID,
            "at the TWO-walk ceiling the same kill is a crash, not a timeout")
        self.assertEqual(
            chain_trials.classify(None, 720.0, self.log, ceiling=720),
            chain_trials.TIMED_OUT)

    def test_the_attempt_count_reaches_the_CHILD_through_the_environment(self):
        # The same road the arm and the shots flag already travel, and read at
        # CALL time (10.18). A junk value is REFUSED, never defaulted: a silent
        # fallback to 1 would run a plain batch while the log said --attempts 2.
        self.assertEqual(chain_trials.ATTEMPTS_ENV, "BASEBALL_CHAIN_ATTEMPTS")
        self.assertEqual(
            chain_trials.attempts_per_trial(
                env={chain_trials.ATTEMPTS_ENV: "3"}), 3)
        for bad in ("two", "", "0", "-1"):
            with self.assertRaises(SystemExit, msg=bad):
                chain_trials.attempts_per_trial(
                    env={chain_trials.ATTEMPTS_ENV: bad})
        self.assertEqual(chain_trials.attempts_from_argv(["chain_trials.py"]), 1)
        self.assertEqual(
            chain_trials.attempts_from_argv(
                ["chain_trials.py", "route", "--attempts", "2"]), 2)
        with self.assertRaises(SystemExit):
            chain_trials.attempts_from_argv(["chain_trials.py", "--attempts"])
        # ... and that main() exports it and uses the scaled ceiling. main()
        # cannot run offline (_assert_live, console_lock, run_trial), so this
        # half is a SOURCE check and says so; it pins the four sites.
        with open(os.path.join(_ROOT, "overnight", "chain_trials.py")) as fh:
            src = fh.read()
        self.assertIn("    attempts = attempts_from_argv()", src)
        self.assertIn("    os.environ[ATTEMPTS_ENV] = str(attempts)", src)
        self.assertIn("    ceiling = ceiling_for(attempts)", src)
        self.assertIn("_harness.run_trial(__file__, name, ceiling, log=log)",
                      src)
        self.assertIn("classify(r, secs, log, ceiling=ceiling)", src)
        self.assertNotIn("run_trial(__file__, name, CEILING", src)
        # ... and that the tally reports BOTH rates, under names that do not
        # collide with the per-ROW booleans (row["retried"] is a bool on every
        # row; a batch-level int of the same name is 10.1 again).
        self.assertIn('res["arrived_first_attempt"] = first', src)
        self.assertIn('r.get("first_walk_arrived")', src)
        self.assertIn('res["trials_retried"] = len(retried)', src)
        self.assertNotIn('res["retried"] = len(retried)', src)
        # ... and that the killed-trial row gets the attempts the parent
        # allowed, so recover() can name the attempt that was in flight.
        self.assertIn("attempts=attempts)", src)

    def test_one_trials_own_wiring_is_pinned_by_SOURCE_and_here_is_why(self):
        # WHY THIS IS A SOURCE CHECK AND NOT AN EXECUTION. one_trial() opens
        # with _assert_live(), which raises SystemExit while BASEBALL_TEST_RUN
        # is set -- and that flag is what holds every input path OFF for this
        # whole suite. Running one_trial here would mean clearing it, which is
        # the exact accident CLAUDE.md 5 and 10.1 record: an import cleared it
        # inside a live harness and fifty "readings" came from a camera that
        # never turned. So the LOOP is executed through walk_attempts (above,
        # with stubs) and the CLOSURES one_trial hands it are pinned as text.
        # A typo here -- a retry journalling over attempt 1's file, or a shots
        # directory not reaching the row -- would pass every other test.
        with open(os.path.join(_ROOT, "overnight", "chain_trials.py")) as fh:
            src = fh.read()
        self.assertIn("    attempts = attempts_per_trial()", src)
        self.assertIn(
            "    res = walk_attempts(attempts, do_reset, do_load, do_walk, log)",
            src)
        self.assertIn("    def do_reset(attempt):", src)
        self.assertIn("    def do_load():", src)
        self.assertIn("    def do_walk(attempt, ch):", src)
        self.assertIn('        held["chain"] = chain_mod.Chain.load(d, log=log)',
                      src)
        # EVERY attempt journals to its OWN file, and the walk's own outputs
        # are attached to THAT attempt's result, not to a shared variable.
        self.assertIn("journal=attempt_journal(journal, attempt),", src)
        self.assertIn('        r["journal"] = attempt_journal(journal, attempt)',
                      src)
        self.assertIn('        r["shots"] = shots_dir', src)
        self.assertIn('        r["setup_seconds"] = round(setup, 1)', src)
        # ... and the single-walk child is gone, not merely bypassed.
        self.assertNotIn("res = chain_walk.walk(ch, compass.fast_capture", src)

    def test_a_kill_during_a_RETRY_recovers_the_RETRYS_journal(self):
        # THE BASE PATH IS ALWAYS ATTEMPT 1'S. Once attempt 1 has failed its
        # journal holds a COMPLETE walk, so reading it after a kill during
        # attempt 2 returns a full fixes list and a clean k_final describing
        # the wrong walk -- evidence that parses cleanly and is not about what
        # happened, which is worse than none (10.15: check WHICH moment).
        d = tempfile.mkdtemp(prefix="chain_recover_a2_")
        try:
            p = os.path.join(d, "j.jsonl")
            with open(p, "w") as fh:                  # attempt 1: complete
                for i in range(5):
                    fh.write(json.dumps({"iteration": i, "k": 10 + i,
                                         "action": "advanced"}) + "\\n")
            with open(p + ".a2", "w") as fh:          # attempt 2: killed
                for i in range(2):
                    fh.write(json.dumps({"iteration": i, "k": 100 + i,
                                         "action": "advanced"}) + "\\n")
            row = chain_trials.trial_row(5, chain_trials.TIMED_OUT, 700.0,
                                         None, journal=p, attempts=2)
            self.assertEqual(row["k_final"], 101,
                             "the KILLED walk's evidence, not attempt 1's")
            self.assertEqual(row["recovered_attempt"], 2)
            self.assertEqual(len(row["fixes"]), 2)
            self.assertEqual(row["attempts_used"], 2)
            self.assertEqual(row["attempts_allowed"], 2)
            self.assertIs(row["retried"], True)
            # PROVABLE at attempt >= 2: walk 1 came back without arriving, or
            # attempt 2 would never have started.
            self.assertIs(row["first_walk_arrived"], False)
            # ... and the old, single-attempt reading is the one it replaces.
            old = chain_trials.trial_row(5, chain_trials.TIMED_OUT, 700.0,
                                         None, journal=p, attempts=1)
            self.assertEqual(old["k_final"], 14)
            self.assertEqual(old["recovered_attempt"], 1)
            self.assertNotIn("first_walk_arrived", old,
                             "a kill on attempt 1 may have arrived and died "
                             "before printing; that is UNKNOWN, not False")
            # AN EMPTY .a2 STILL PROVES ATTEMPT 2 STARTED. chain_walk creates
            # the file with its first row, so existence is the test -- and
            # falling back to attempt 1's rows here would be the same defect.
            open(p + ".a2", "w").close()
            row = chain_trials.trial_row(6, chain_trials.TIMED_OUT, 700.0,
                                         None, journal=p, attempts=2)
            self.assertEqual(row["recovered_attempt"], 2)
            self.assertEqual(row["attempts_used"], 2)
            self.assertNotIn("fixes", row, "absent evidence, never the wrong "
                                           "evidence")
            self.assertNotIn("k_final", row)
            # ... and an attempt that never started falls back cleanly.
            os.remove(p + ".a2")
            row = chain_trials.trial_row(7, chain_trials.TIMED_OUT, 700.0,
                                         None, journal=p, attempts=3)
            self.assertEqual(row["recovered_attempt"], 1)
            self.assertEqual(row["k_final"], 14)
            self.assertEqual(row["attempts_allowed"], 3)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_RETRIED_arrival_is_visible_on_the_LINE_a_human_scans(self):
        # 10.1 at the log-reading layer: the two rows below differ in every
        # way that matters and used to print the same bytes.
        first = {"k_final": 204, "waypoints": 205, "iterations": 60,
                 "pushes": 40, "walk_seconds": 84.0, "setup_seconds": 12.0,
                 "failure": None, "attempts_allowed": 2, "attempts_used": 1,
                 "arrived_on_attempt": 1}
        retried = dict(first, attempts_used=2, arrived_on_attempt=2)
        a = chain_trials.trial_line(5, chain_trials.ARRIVED, 190.0, first)
        b = chain_trials.trial_line(5, chain_trials.ARRIVED, 380.0, retried)
        self.assertNotEqual(a, b)
        self.assertNotIn("attempt", a)
        self.assertIn("attempt 2/2", b)
        # THE MARKER GOES BEFORE `failure=`: tools/trial_sheet.py's LINE_RE
        # ends `.*?failure=(.*)`, so anything after it joins the failure text.
        self.assertLess(b.index("attempt 2/2"), b.index("failure="))
        self.assertTrue(b.endswith("failure=None"), b)
        # A trial that spent every attempt and arrived on NONE says so too.
        lost = dict(first, attempts_used=2, arrived_on_attempt=None,
                    failure="lost")
        c = chain_trials.trial_line(5, chain_trials.FAILED, 380.0, lost)
        self.assertIn("attempts 2/2", c)
        # ... and all three are checked against the READER ITSELF, loaded by
        # path. trial_sheet is what the user's standing rule runs on every
        # failed trial, and a marker in the wrong place would not break it --
        # it would quietly become part of every row's failure text.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "trial_sheet_marker_check",
            os.path.join(_ROOT, "tools", "trial_sheet.py"))
        sheet = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sheet)
        for line in (a, b, c):
            m = sheet.LINE_RE.match(line)
            self.assertIsNotNone(m, f"the reader refused: {line}")
            self.assertEqual(int(m.group(4)), 204)
        self.assertEqual(sheet.LINE_RE.match(b).group(8), "None",
                         "the marker must not join the failure text")
        self.assertEqual(sheet.LINE_RE.match(c).group(8), "lost")
        # ... and a recovered row names WHICH attempt's journal it read.
        rec = chain_trials.trial_line(
            5, chain_trials.TIMED_OUT, 700.0,
            dict(lost, recovered=True, recovered_attempt=2))
        self.assertIn("[rows RECOVERED from attempt 2's journal]", rec)
        self.assertIn("[rows RECOVERED from the journal]",
                      chain_trials.trial_line(
                          5, chain_trials.TIMED_OUT, 700.0,
                          {"recovered": True, "failure": "x"}))
        # ... and today's single-attempt line is unchanged, to the byte.
        plain = {"k_final": 204, "waypoints": 205, "iterations": 60,
                 "pushes": 40, "walk_seconds": 84.0, "setup_seconds": 12.0,
                 "failure": None}
        self.assertEqual(
            chain_trials.trial_line(5, chain_trials.ARRIVED, 96.0, plain),
            "[ 5] ARRIVED   k=204/205  it=60  pushes=40  "
            "seconds=96.0 (walk 84.0, setup 12.0)  failure=None")

    def test_a_walk_that_RAISES_spends_the_next_attempt_and_is_never_hidden(self):
        # chain_walk raising is not evidence the world is unwalkable, so the
        # reload is worth spending -- but a swallowed crash is how a harness
        # reports a clean batch of nothing. The traceback is logged, the
        # attempt is recorded as an exception, and on the LAST allowed attempt
        # it is RE-RAISED, so a default one-attempt run dies exactly as today.
        calls = []

        def boom(attempt, chain):
            calls.append(attempt)
            if attempt == 1:
                raise RuntimeError("capture died")
            return dict(self.ARRIVES)

        res = chain_trials.walk_attempts(
            2, lambda a: None, lambda: "C", boom, self.log)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(res["arrived_on_attempt"], 2)
        self.assertIs(res["first_walk_arrived"], False)
        self.assertIs(res["walks"][0]["exception"], True)
        self.assertEqual(res["walks"][0]["failure"],
                         "exception: RuntimeError: capture died")
        self.assertEqual(res["walk_exceptions"], 1)
        self.assertTrue(any("RuntimeError: capture died" in m
                            for m in self.logs), self.logs)
        self.assertTrue(any("Traceback" in m for m in self.logs), self.logs)
        # ... and with ONE attempt it propagates, byte for byte as today.
        with self.assertRaises(RuntimeError):
            chain_trials.walk_attempts(
                1, lambda a: None, lambda: "C", boom, self.log)

    def test_a_later_attempt_journals_to_its_OWN_file(self):
        # chain_walk APPENDS, so two walks sharing one journal would splice two
        # sequences of iteration numbers and recover() would read the pair as
        # one walk. Attempt 1 keeps the parent's exact path, so a single-
        # attempt trial is unchanged on disk.
        self.assertEqual(chain_trials.attempt_journal("/j/t01.jsonl", 1),
                         "/j/t01.jsonl")
        self.assertEqual(chain_trials.attempt_journal("/j/t01.jsonl", 2),
                         "/j/t01.jsonl.a2")
        self.assertEqual(chain_trials.attempt_journal("/j/t01.jsonl", 3),
                         "/j/t01.jsonl.a3")
        self.assertIsNone(chain_trials.attempt_journal(None, 2))

'''

edits_t = [
 # (9) the class docstring names the new half.
 ('''class HarnessScoring(unittest.TestCase):
    """(j) overnight/chain_trials.py: the scoring, offline, with no console."""
''',
  '''class HarnessScoring(unittest.TestCase):
    """(j) overnight/chain_trials.py: the scoring, offline, with no console.

    ... and (patch52) the ATTEMPTS loop: up to N walks per trial, each after
    its own reset, stopping at the first arrival, the chain loaded once, the
    ceiling scaled with N, and a record in which a retried arrival cannot be
    mistaken for a first-walk one. `walk_attempts` is the seam and takes its
    reset, load and walk as arguments, so none of this touches the console.
    """
'''),
 # (10) the tests, before the last method of the class.
 ("    def test_a_chain_name_may_not_be_a_path(self):\n",
  NEW_TESTS + "    def test_a_chain_name_may_not_be_a_path(self):\n"),
]

# ------------------------------------------------- assert EVERYTHING, then write
for a, b in edits_h:
    assert h.count(a) == 1, ("chain_trials anchor", a[:70], h.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:70], t.count(a))
# nothing of this patch is present yet
for token in ("ATTEMPTS_ENV", "walk_attempts", "attempt_journal", "ceiling_for",
              "attempts_per_trial", "first_walk_arrived", "trial_line",
              "_recover_rows", "trials_retried", "recovered_attempt",
              "walk_exceptions"):
    assert token not in h, ("already patched", token)
    assert token not in t, ("already patched", token)
# the constants the ceiling is built from, and the one that must not move
assert h.count("TIME_CAP = 180.0") == 1
assert h.count("SETUP_BUDGET = 180.0") == 1
assert h.count("CEILING = int(TIME_CAP + SETUP_BUDGET)") == 1
# every CEILING site this patch has to reach: the two in classify and the two
# in main. The fifth is setup_verdict's message, which is about the budget the
# ceiling reserves and is deliberately left alone.
assert h.count("CEILING") == 8, h.count("CEILING")
# the child's single walk, which becomes the loop
assert h.count("res = chain_walk.walk(ch, compass.fast_capture") == 1
assert h.count("ch = chain_mod.Chain.load(d, log=log)") == 1
# the test class the new tests join, and its neighbours
cls = t.index("class HarnessScoring(unittest.TestCase):")
nxt = t.index("\nclass ", cls + 1)
assert "def test_a_chain_name_may_not_be_a_path" in t[cls:nxt]
assert "def setUp(self):" in t[cls:nxt]
assert t.count("        self._alive = chain_trials._harness.alive") == 1
assert t.count("        self.assertEqual(chain_trials.CEILING, 360)") == 1

for a, b in edits_h:
    h = h.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(h)
ast.parse(t)
# post-conditions: the loop, its default, the scaled ceiling, the record
assert h.count("ATTEMPTS = 1\n") == 1
assert h.count('ATTEMPTS_ENV = "BASEBALL_CHAIN_ATTEMPTS"') == 1
assert h.count("def walk_attempts(attempts, reset, load, walk, log):") == 1
assert h.count("res = walk_attempts(attempts, do_reset, do_load, do_walk, log)") == 1
assert h.count("if chain is None:") == 1, "the chain is loaded ONCE"
assert h.count('if row["arrived"]:\n            break') == 1
assert h.count("def ceiling_for(attempts):") == 1
assert h.count("    ceiling = ceiling_for(attempts)") == 1
assert h.count("os.environ[ATTEMPTS_ENV] = str(attempts)") == 1
assert h.count("_harness.run_trial(__file__, name, ceiling, log=log)") == 1
assert h.count("classify(r, secs, log, ceiling=ceiling)") == 1
assert h.count("CEILING") == 5, h.count("CEILING")   # the header paragraph,
# the definition, setup_verdict's message, classify's docstring and its default
assert h.count("secs >= ceiling") == 2
assert h.count('res["arrived_on_attempt"] = arrived_on') == 1
assert h.count('res["first_walk_arrived"] = bool(walks and walks[0]["arrived"])') == 1
assert h.count('res["arrived_first_attempt"] = first') == 1
assert h.count("def attempt_journal(journal, attempt):") == 1
assert h.count("journal=attempt_journal(journal, attempt),") == 1
# ... and nothing of the single-walk child is left behind
assert "res = chain_walk.walk(ch, compass.fast_capture" not in h
assert 't_reset = time.time()\n\n    ch = chain_mod.Chain.load' not in h
assert t.count("def test_a_failed_first_walk_is_retried_after_its_OWN_reset") == 1
assert t.count("def test_the_ceiling_SCALES_with_the_attempts") == 1
assert t.count("self.assertEqual(chain_trials.ceiling_for(2), 720)") == 1
assert t.count("def _attempts(self, attempts, results):") == 1
# ... the skeptic round: the journal a kill actually leaves, the line a human
# reads, the crash that must not eat the remaining attempts, and the two names
# that must not collide.
assert h.count("def recover(path, attempts=1):") == 1
assert h.count("def _recover_rows(path):") == 1
assert h.count("        p = attempt_journal(path, attempt)") == 1
assert h.count("row.update(recover(journal, attempts=attempts))") == 1
assert "row.update(recover(journal))" not in h
assert h.count("def trial_row(i, outcome, secs, r, journal=None, attempts=1):") == 1
assert h.count('def trial_line(i, outcome, secs, row, armtxt=""):') == 1
assert h.count("            log(trial_line(i, outcome, secs, row, armtxt))") == 1
assert h.count("                            attempts=attempts)") == 1
assert "[rows RECOVERED from the journal]\"\n" not in h
assert h.count('res["trials_retried"] = len(retried)') == 1
assert 'res["retried"] = len(retried)' not in h
assert h.count('res["walk_exceptions"] = sum(1 for w in walks '
               'if w.get("exception"))') == 1
assert h.count("            if attempt >= attempts:\n                raise\n") == 1
assert h.count("        except Exception as exc:") == 1
assert t.count("def test_a_kill_during_a_RETRY_recovers_the_RETRYS_journal") == 1
assert t.count("def test_a_RETRIED_arrival_is_visible_on_the_LINE_a_human_scans") == 1
assert t.count("def test_a_walk_that_RAISES_spends_the_next_attempt_"
               "and_is_never_hidden") == 1
assert t.count("def test_one_trials_own_wiring_is_pinned_by_SOURCE_"
               "and_here_is_why") == 1

open(H, "w").write(h)
open(T, "w").write(t)
print("patch52 applied to", ROOT)
