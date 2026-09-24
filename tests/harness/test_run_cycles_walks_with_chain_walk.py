"""run_cycles walks with the CLOSED LOOP, in a child it can kill -- and refuses
to play when it did not arrive.

WHAT THIS GUARDS, in order of what it would cost:

  1. THE MONEY. `_walk_to_table` used to call the dead-reckoning walker and
     read `reached` out of a (wins, best_streak) TUPLE. A tuple is always true
     -- (0, 0) included -- so believing it marched a missed walk on to press
     Square at nothing and spend $50. The replacement returns a DICT, which is
     true exactly the same way, so the money guard here is not decoration: the
     MONEY GUARD block is the whole point of the file.

  2. THE EXTERNAL KILL. `chain_walk.walk` tests its time cap at the top of its
     loop, so a capture blocked inside the loop body never reaches it, and
     CLAUDE.md 10.14 measured that a process blocked in a capture does not
     answer SIGALRM. The walk therefore runs in a CHILD spawned through
     `_harness.run_trial`, which kills from outside at a deadline. A test that
     only checked "it walks" would pass with the walk back in-process, so this
     file asserts the parent NEVER walks in-process, and that the deadline is
     the per-attempt ceiling rather than a one-walk one.

  3. THE HIDDEN GAME WINDOW. chiaki keeps heartbeating with its window on
     another Space, so the stream check cannot see it. Counted as a failed
     walk, three in a row end an unattended night blaming navigation. main()
     must re-run the SAME cycle number, bounded, without touching
     route_failures.

HOW IT IS SAFE TO RUN. Every module that can touch the console or spend money
is a FAKE installed in sys.modules BEFORE run_cycles is imported, so the real
ones are never loaded: ensure_stream, orchestrator, reset_env, chain,
chain_walk, compass, walk_steps. The old dead-reckoning walker is faked too and
its main() RAISES -- if a mutant puts it back, this file finds out by exploding
rather than by driving the console. `_harness.run_trial` is replaced on the
real module object, so no subprocess is ever spawned.

Every assertion is on CALLS THROUGH THE STUBS, not on outcomes: the arriving
path and the missing path both end with cycle() returning something, and only
the call record can tell them apart.
"""
import ast
import json
import os
import sys
import types

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ---- the fakes, installed BEFORE run_cycles is imported -------------------
CALLS = []
STATE = {"stream": True, "balance": 246, "script": [], "walks": [],
         "child": None, "trial_secs": 12.3, "window": True,
         "reset_raises": 0}


def _fake(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class ResetError(RuntimeError):
    pass


def _reset_environment(log=None, progress_file=None):
    CALLS.append(("reset", progress_file))
    if STATE["reset_raises"]:
        STATE["reset_raises"] -= 1
        raise ResetError("the confirm dialog never appeared")


def _ensure(log=print):
    CALLS.append(("stream",))
    return STATE["stream"]


def _orch_run(**kw):
    CALLS.append(("run", kw.get("max_spend"), kw.get("progress_file")))


def _load_progress(path):
    return (0, 0, 0, None, False, False)


def _save_progress(w, l, d, bal, path, **kw):
    CALLS.append(("save_progress", bal, kw.get("match_in_progress")))


def _read_balance_from_pause_menu():
    CALLS.append(("balance_read",))
    return STATE["balance"]


class _Chain:
    @staticmethod
    def load(d, log=None):
        CALLS.append(("chain_load", d))
        return "CHAIN-OBJECT"


def _walk(chain, capture, read_heading, **kw):
    CALLS.append(("walk", kw.get("shots")))
    STATE["walks"].append(kw)
    arrived = STATE["script"].pop(0) if STATE["script"] else False
    return {"arrived": arrived, "seconds": 1.0,
            "failure": None if arrived else "did not arrive"}


def _never(*a, **kw):
    raise AssertionError("the dead-reckoning walker must never be called")


_fake("ensure_stream", ensure=_ensure)
_fake("orchestrator", run=_orch_run, load_progress=_load_progress,
      save_progress=_save_progress,
      read_balance_from_pause_menu=_read_balance_from_pause_menu)
_fake("reset_env", ResetError=ResetError, reset_environment=_reset_environment)
_fake("chain", Chain=_Chain)
_fake("chain_walk", walk=_walk)
_fake("compass", fast_capture=lambda *a, **k: None)
_fake("walk_steps", read_heading=lambda *a, **k: None)
_fake("go", main=_never)

import api_budget
import run_cycles

print("module under test:", run_cycles.__file__)

# Captured BEFORE anything is redirected: the SHIPPED roots are what the last
# block judges.
SHIPPED_SHOTS = run_cycles.SHOTS_ROOT
SHIPPED_JOURNALS = run_cycles.JOURNAL_ROOT
SRC = open(run_cycles.__file__).read()

import atexit
import shutil
import tempfile
_TMP = tempfile.mkdtemp(prefix="run_cycles_test_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
run_cycles.SHOTS_ROOT = os.path.join(_TMP, "frames")
run_cycles.JOURNAL_ROOT = os.path.join(_TMP, "journals")
# No sleeping, a controllable window probe, and a chain directory that exists
# without touching the checkout.
run_cycles.time = types.SimpleNamespace(sleep=lambda s: None)
run_cycles.chain_trials.CHAINS = _TMP
os.makedirs(os.path.join(_TMP, run_cycles.CHAIN), exist_ok=True)

WINDOW_WAITS = []


def _wait_for_game_window(log, **kw):
    WINDOW_WAITS.append(1)
    return STATE["window"]


run_cycles.chain_trials.wait_for_game_window = _wait_for_game_window


# NO SUBPROCESS IS EVER SPAWNED. run_trial is replaced on the real module
# object, so `_harness.run_trial(...)` inside _walk_to_table resolves to this.
def _run_trial(script, arg, timeout, cwd=None, log=None, check_stream=True):
    CALLS.append(("run_trial", script, arg, timeout, cwd,
                  os.environ.get(run_cycles.WALK_ATTEMPTS_ENV)))
    child = STATE["child"]
    return (dict(child) if isinstance(child, dict) else None), STATE["trial_secs"]


run_cycles._harness.run_trial = _run_trial


def run_cycle(child, attempts_env=None, stream=True, n=1):
    """One cycle() with the CHILD'S REPORT scripted. Returns (outcome, calls)."""
    CALLS[:] = []
    STATE["child"] = child
    STATE["walks"] = []
    STATE["stream"] = stream
    if attempts_env is None:
        os.environ.pop(run_cycles.WALK_ATTEMPTS_ENV, None)
    else:
        os.environ[run_cycles.WALK_ATTEMPTS_ENV] = str(attempts_env)
    try:
        return run_cycles.cycle(n), list(CALLS)
    finally:
        os.environ.pop(run_cycles.WALK_ATTEMPTS_ENV, None)


def run_child(script, attempts_env=None, n=1, window=True, reset_raises=0):
    """The CHILD'S BODY with chain_walk scripted. Returns (result, calls)."""
    CALLS[:] = []
    STATE["script"] = list(script)
    STATE["walks"] = []
    STATE["window"] = window
    STATE["reset_raises"] = reset_raises
    if attempts_env is None:
        os.environ.pop(run_cycles.WALK_ATTEMPTS_ENV, None)
    else:
        os.environ[run_cycles.WALK_ATTEMPTS_ENV] = str(attempts_env)
    try:
        return run_cycles._walk_once(n), list(CALLS)
    finally:
        os.environ.pop(run_cycles.WALK_ATTEMPTS_ENV, None)
        STATE["window"] = True
        STATE["reset_raises"] = 0


def run_main(outcomes, cycles=3):
    """main() with cycle() scripted. Returns the cycle numbers it ran."""
    seq = list(outcomes)
    seen = []
    WINDOW_WAITS[:] = []
    real = run_cycles.cycle

    def fake_cycle(k):
        seen.append(k)
        return seq.pop(0) if seq else True

    api_budget._budget = None
    api_budget._calls = 0
    os.environ["BASEBALL_API_BUDGET"] = "100000"
    run_cycles.cycle = fake_cycle
    try:
        run_cycles.main(cycles=cycles)
    finally:
        run_cycles.cycle = real
        api_budget._budget = None
        os.environ.pop("BASEBALL_API_BUDGET", None)
    return seen, list(WINDOW_WAITS)


def kinds(calls, kind):
    return [c for c in calls if c[0] == kind]


def where(calls, kind, last=False):
    """Index of a call of this kind, or -1. It must NEVER raise: an assertion
    that explodes ends the file and every block after it is silently never
    run, which is the "a slow step and a hung step with identical output"
    shape one level up. The first draft of this file did exactly that under
    the hardcoded-attempts mutant."""
    hits = [i for i, c in enumerate(calls) if c[0] == kind]
    if not hits:
        return -1
    return hits[-1] if last else hits[0]


CEIL = run_cycles.chain_trials.ceiling_for
OWN_DIR = os.path.dirname(os.path.abspath(run_cycles.__file__))

# --- 1. THE EXTERNAL KILL: the walk is a child, killed from outside --------
out, calls = run_cycle({"arrived": True, "arrived_on_attempt": 1,
                        "attempts_allowed": 3, "attempts_used": 1},
                       attempts_env=3)
rt = kinds(calls, "run_trial")
check("the walk is spawned as a CHILD PROCESS, exactly once", len(rt) == 1)
check("...and it is THIS file that is re-invoked as the child",
      len(rt) == 1 and rt[0][1] == run_cycles.__file__)
check("...with the cycle number as its argument", len(rt) == 1 and rt[0][2] == 1)
check("THE KILL IS SIZED PER ATTEMPT -- a one-walk ceiling would kill exactly "
      "the retries it bounds (CLAUDE.md 10.14)",
      len(rt) == 1 and rt[0][3] == CEIL(3))
check("ANTI-VACUITY: the per-attempt ceiling really differs from the one-walk "
      "ceiling, so the check above can fail", CEIL(3) != CEIL(1))
check("the child runs in the CHECKOUT, not run_trial's default parent-of-"
      "parent -- PROGRESS_FILE is a relative path", len(rt) == 1
      and rt[0][4] == OWN_DIR)
check("THE PARENT NEVER WALKS IN-PROCESS: a capture that blocks there could "
      "not be killed from anywhere", not STATE["walks"])
check("the child is told how many walks it may spend, through the environment "
      "it inherits", len(rt) == 1 and rt[0][5] == "3")
check("the environment is read at CALL time, never captured in a def line "
      "(10.18)", run_cycles.walks_per_cycle({"BASEBALL_CYCLE_WALK_ATTEMPTS":
                                             "7"}) == 7)

out, calls_d = run_cycle({"arrived": True}, attempts_env=None)
rt_d = kinds(calls_d, "run_trial")
check("with the variable unset it spends the shipped default, 2 walks",
      len(rt_d) == 1 and rt_d[0][5] == "2" and rt_d[0][3] == CEIL(2))
check("and the shipped default is literally 2 (10.11: pin the literal)",
      run_cycles.WALK_ATTEMPTS == 2)
check("THE SHIPPED CHAIN IS THE USER'S OWN RECORDED DRIVE -- a silent edit to "
      "an unvalidated chain would otherwise pass every check here",
      run_cycles.CHAIN == "route_user_1853")

# the dead-reckoning walker is gone from the file, by AST and by source
tree = ast.parse(SRC)
imported = set()
attr_bases = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for a in node.names:
            imported.add(a.name)
    elif isinstance(node, ast.ImportFrom):
        imported.add(node.module or "")
    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        attr_bases.add(node.value.id)
check("ANTI-VACUITY: the AST scan finds the imports that ARE there",
      "reset_env" in imported and "chain_trials" in imported
      and "_harness" in imported and "orchestrator" in attr_bases)
check("nothing imports the dead-reckoning walker any more", "go" not in imported)
check("and nothing calls an attribute on it", "go" not in attr_bases)
check("the string 'go.main' does not survive in a comment either",
      "go.main" not in SRC)
check("what it walks with instead is chain_walk, through walk_attempts",
      "chain_walk.walk(" in SRC and "walk_attempts(" in SRC)
check("and the child entry is wired to the argument shape run_trial spawns",
      "--one-trial" in SRC and "one_walk(int(sys.argv[2]))" in SRC)

# --- 2. a retried arrival still plays, once, for the whole wallet -----------
out, calls = run_cycle({"arrived": True, "arrived_on_attempt": 2,
                        "attempts_allowed": 2, "attempts_used": 2,
                        "walk_seconds_total": 91.4, "shots": "/somewhere"},
                       attempts_env=2)
runs = kinds(calls, "run")
check("a walk that arrived on the SECOND attempt still plays", out is True)
check("orchestrator.run is called exactly ONCE", len(runs) == 1)
check("max_spend is the balance read off the pause menu",
      len(runs) == 1 and runs[0][1] == STATE["balance"])
check("and it plays into the progress file the cycle resets",
      len(runs) == 1 and runs[0][2] == run_cycles.PROGRESS_FILE)
i_walk = where(calls, "run_trial", last=True)
i_bal = where(calls, "balance_read")
i_run = where(calls, "run")
check("the balance is read AFTER the walk and BEFORE the match -- read before "
      "the walk it would be the previous cycle's empty wallet",
      0 <= i_walk < i_bal < i_run)
check("the progress record is written with match_in_progress cleared",
      any(c[0] == "save_progress" and c[2] is False for c in calls))

# --- 3. THE MONEY GUARD: the walk missed, so nothing is ever bought --------
out, calls = run_cycle({"arrived": False, "attempts_used": 2,
                        "failure": "did not arrive"}, attempts_env=2)
check("MONEY GUARD: the walk missed -> orchestrator.run is NEVER called",
      not kinds(calls, "run"))
check("MONEY GUARD: it does not even open the pause menu to read money",
      not kinds(calls, "balance_read"))
check("MONEY GUARD: no progress record is written on a missed walk",
      not kinds(calls, "save_progress"))
check("a missed walk SKIPS THE CYCLE and does not end the run", out == "route")
check("ANTI-VACUITY: it did try -- the child was spawned",
      len(kinds(calls, "run_trial")) == 1)

# --- 3b. THE HANG: a child killed at the ceiling reports NOTHING -----------
out, calls = run_cycle(None, attempts_env=2)
check("MONEY GUARD: a KILLED or silent child -> orchestrator.run is NEVER "
      "called", not kinds(calls, "run"))
check("...and no balance is read", not kinds(calls, "balance_read"))
check("a killed child SKIPS THE CYCLE rather than ending the run",
      out == "route")

# --- 3c. a reload that will not happen still ENDS the run ------------------
out, calls = run_cycle({"arrived": False, "reset_failed": True,
                        "failure": "reset: no confirm dialog"}, attempts_env=2)
check("a reload that will not happen ends the run, as it did before the patch",
      out is False)
check("...and plays nothing on the way out", not kinds(calls, "run"))

# --- 4. the stream check still gates everything ----------------------------
out, calls = run_cycle({"arrived": True}, attempts_env=2, stream=False)
check("stream down -> no child is spawned", not kinds(calls, "run_trial"))
check("stream down -> nothing plays", not kinds(calls, "run"))
check("stream down -> cycle() returns False, which stops the run", out is False)

# --- 5. A HIDDEN GAME WINDOW IS NOT A NAVIGATION FAILURE -------------------
out, calls = run_cycle({"arrived": False, "window_missing": True,
                        "failure": "no chiaki game window for 120s"},
                       attempts_env=2)
check("a hidden game window is NOT scored as a missed walk", out == "window")
check("...and plays nothing", not kinds(calls, "run"))

seen, waits = run_main(["window", "window", "window", True], cycles=2)
check("main() RE-RUNS THE SAME CYCLE NUMBER when the window was hidden",
      seen[:3] == [1, 1, 1])
check("...bounded by the harness's own WINDOW_RETRY_MAX",
      len(waits) == run_cycles.chain_trials.WINDOW_RETRY_MAX)
check("...and it waits for the window between re-runs",
      run_cycles.chain_trials.WINDOW_RETRY_MAX == 2 and len(waits) == 2)
check("...then moves on rather than looping forever", seen == [1, 1, 1, 2])

seen, waits = run_main(["window", True, "window", True, "window", True],
                       cycles=3)
check("HIDDEN WINDOWS DO NOT ACCUMULATE ROUTE FAILURES: three of them, each "
      "retried into an arrival, and all three cycles run",
      seen == [1, 1, 2, 2, 3, 3])

seen, waits = run_main(["route", "route", "route", True, True], cycles=5)
check("CONTROL: three genuinely missed walks in a row DO stop the run",
      seen == [1, 2, 3])

# --- 6. THE CHILD'S BODY: it walks through walk_attempts -------------------
res, calls = run_child([False, False, False, False], attempts_env=3)
check("the child spends the walks the environment allows, at CALL time",
      len(kinds(calls, "walk")) == 3)
check("one reload per walk, which is what makes a retry worth anything",
      len(kinds(calls, "reset")) == 3)
check("the chain is loaded ONCE however many walks (Chain.load runs ORB over "
      "every waypoint)", len(kinds(calls, "chain_load")) == 1)
check("each attempt gets its OWN shots dir, so they cannot overwrite",
      len(set(c[1] for c in kinds(calls, "walk"))) == 3)
check("the reload is told which progress file to clear match_in_progress in",
      all(c[1] == run_cycles.PROGRESS_FILE for c in kinds(calls, "reset")))
check("a child that never arrived says so by KEY, not by truthiness",
      res.get("arrived") is False)

res, calls = run_child([False, True], attempts_env=2)
check("it stops at the first arrival", len(kinds(calls, "walk")) == 2)
check("and records WHICH walk arrived, so a retry is never read as a first "
      "walk", res.get("arrived") is True and res.get("arrived_on_attempt") == 2)
check("ANTI-VACUITY: the stubbed walk really ran and was given a shots dir",
      len(STATE["walks"]) == 2 and all(w.get("shots") for w in STATE["walks"]))
check("ANTI-VACUITY: it walked with the FAKE chain_walk",
      sys.modules["chain_walk"].walk is _walk)
_last = STATE["walks"][-1] if STATE["walks"] else {}
check("it walks with the trial harness's own cap and end budget, so the "
      "40-of-40 and this are the same walk",
      _last.get("time_cap") == run_cycles.chain_trials.TIME_CAP
      and _last.get("end_iterations") == run_cycles.chain_trials.END_ITERATIONS)
check("every walk journals, so a killed run keeps its evidence",
      all(w.get("journal") for w in STATE["walks"]))

res, calls = run_child([True], attempts_env=2, window=False)
check("a hidden window is reported as such, not as a missed walk",
      res.get("window_missing") is True and res.get("arrived") is False)
check("...and it does not walk", not kinds(calls, "walk"))
check("...and it does not burn a second attempt's 120s wait on it",
      not kinds(calls, "reset"))

res, calls = run_child([True], attempts_env=2, reset_raises=99)
check("a reload that fails RESET_ATTEMPTS times is reported as reset_failed",
      res.get("reset_failed") is True and res.get("arrived") is False)
check("...after exactly RESET_ATTEMPTS tries",
      len(kinds(calls, "reset")) == run_cycles.RESET_ATTEMPTS)

# --- 7. what the child sends back is one small JSON line -------------------
p = run_cycles._payload({"arrived": 1, "k_final": 5, "fixes": [object()],
                         "seconds": 3.0})
check("the payload is curated, not the whole walk result (fixes is a row per "
      "iteration)", "fixes" not in p)
check("...it is JSON, so run_trial can parse it back",
      json.loads(json.dumps(p))["k_final"] == 5)
check("...and `arrived` is always a bool, so a parent reading it can only "
      "read False when the walk did not arrive", p["arrived"] is True
      and run_cycles._payload({})["arrived"] is False)
try:
    run_cycles.one_walk(1)
    _refused = False
except SystemExit:
    _refused = True
check("the CHILD ENTRY refuses to walk while BASEBALL_TEST_RUN is set -- every "
      "input path is OFF under it, so it would report a character that never "
      "moved as data", _refused)

# --- 8. the evidence does not go in the system temp directory --------------
check("the shot root is the checkout's own overnight/cycle_frames",
      SHIPPED_SHOTS == os.path.join(OWN_DIR, "overnight", "cycle_frames"))
check("the journal root is the checkout's own overnight/cycle_journals",
      SHIPPED_JOURNALS == os.path.join(OWN_DIR, "overnight", "cycle_journals"))
check("no /tmp path is written anywhere in run_cycles -- CLAUDE.md forbids it "
      "and the chiaki tree there was once found as 825 empty directories",
      "/tmp" not in SRC)
check("ANTI-VACUITY: the source really was read", len(SRC) > 2000
      and "overnight" in SRC)

print("")
print("all green" if not FAILS else f"{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
