"""patch58: run_cycles walks with the CLOSED LOOP, in a child this one can kill.

THE ASK, from the user: "could you wire in the correct navigation code? I would
like to smoke test the continuous loop." The loop is already there and its
shape is right -- walk to the table, play until the wallet is empty, reload,
repeat -- and exactly one thing in it was wrong.

THE ONE DEFECT. `_walk_to_table` called `go.main(...)`, the dead-reckoning
route, which arrives roughly half the time per route (CLAUDE.md 8(a): 5/10 over
thirteen measured changes, none of which moved it). `chain_walk.walk` arrived
40 of 40 on 2026-09-08 (27 consecutive with no reload, 39 of 40 on the FIRST
walk) and was wired into nothing but the trial harness.

WHAT THIS CHANGES, and nothing else:

  * `_walk_once(n)` walks with `chain_walk.walk`, retrying through
    `overnight/chain_trials.walk_attempts` -- REUSED, never re-implemented. It
    already resets per attempt, loads the chain ONCE (Chain.load runs ORB over
    every waypoint), stops at the first arrival, and records
    `arrived_on_attempt` so a retried arrival is never read as a first-walk one.
  * `_walk_to_table(n)` SPAWNS that as a child process and kills it from
    outside at a deadline, through `overnight/_harness.run_trial` -- see the
    next section, which is the whole reason this file grew a `--one-trial`
    mode.
  * The verdict is `res["arrived"]`, never the truthiness of what the walker
    returned. The old body read `reached` out of go.main's (wins, best_streak)
    TUPLE and its own comment records why: a tuple is always true, (0, 0)
    included, and believing it marches a missed walk on to spend $50 at nothing.
  * A MISSING GAME WINDOW is retried at the parent, a bounded number of times,
    and never counted as a navigation failure.
  * `_reset_progress()` MOVES, from before the walk to after it arrives. It is
    the only place it can be: it reads the wallet off the pause menu, the
    reloads now live inside `walk_attempts`, so left where it was it would read
    the wallet from BEFORE this cycle's reload -- the empty one the previous
    cycle left -- write it to the progress file, and `run()` (which trusts the
    persisted balance over the screen, per its own docstring) would stop having
    played nothing. That is precisely the failure run_cycles' module docstring
    was written to warn about.
  * RESET_ATTEMPTS moves with the reset, into the callback handed to
    walk_attempts. A ResetError that survives its retries still ENDS THE RUN,
    as it did before; anything else the walk raises is still a SKIPPED CYCLE.
  * The shot root leaves /tmp for `overnight/cycle_frames`, per cycle AND
    attempt, and a journal per walk lands in `overnight/cycle_journals`.
  * `import go` is gone, along with the four comments that named it.

THE EXTERNAL KILL, WHICH v1 OF THIS PATCH DID NOT HAVE (a reviewer's finding,
and it is CLAUDE.md 10.14 exactly). `chain_walk.walk`'s own `time_cap` is
tested at the TOP of its loop (chain_walk.py:1600-1603), so it cannot fire
while a `capture()` inside the loop body is itself blocked -- and 10.14 was
measured on precisely that: a 590s trial did not answer `signal.alarm` because
the process was blocked inside a capture. `_harness.run_trial` exists for this
one reason: `subprocess.Popen`, a deadline, and `p.kill()` (never `terminate`)
FROM OUTSIDE THE PROCESS. So the walk is spawned as
`run_cycles.py --one-trial <cycle>` through `run_trial`, with
`timeout=chain_trials.ceiling_for(attempts)` -- the project's own formula,
sized per attempt so it cannot censor the retry it is bounding (10.14 again).
A killed, crashed or silent child is `(None, secs)`: a SKIPPED CYCLE, never a
played match. THE PARENT MUST NEVER WALK IN-PROCESS, and a test asserts it does
not, because a frozen stream there would hang the whole unattended run with no
log line and nothing outside it able to end the walk.

`run_trial` also checks the stream AFTER the child finishes and re-reports a
dead console as unmeasurable rather than as a navigation failure (10.6), and it
takes the console lock in the parent, so a run started while a trial harness is
driving is refused loudly instead of fighting it for the stick.

THE SECOND WINDOW LAYER, ALSO A REVIEWER'S FINDING. `chain_trials` guards a
hidden chiaki window twice: the child waits up to `WINDOW_WAIT_SEC` before its
reset, AND `main()` waits again and re-runs the SAME trial number, bounded by
`WINDOW_RETRY_MAX`, without counting it. v1 reused only the first, so once the
120s wait expired the RuntimeError came back as an ordinary failed walk --
indistinguishable from a navigation miss and counted toward
`MAX_CONSECUTIVE_ROUTE_FAILURES`. `ensure_stream.ensure()` cannot cover this:
chiaki keeps heartbeating with its window on another Space, and 12 of an A/B's
20 trial numbers went that way in ~15s on 2026-09-08. Both layers now exist
here: `WindowMissing` from the child, `"window"` out of `cycle()`, and a
bounded re-run of the same cycle number in `main()` that leaves
`route_failures` untouched.

NOTHING HERE LEAVES A HOOK FOR EDITING NAVIGATION. The user's rule is that the
loop's 'improve' step may only ever touch minigame PLAY. Navigation reaches
this file as one constant naming a recorded chain and three callbacks that
forward to chain_walk; there is no navigation parameter to tune from here.

PRE-REGISTERED ACCEPTANCE FOR THE LIVE SMOKE TEST THAT FOLLOWS (stated here so
it cannot be moved afterwards; this script does NOT run it). One cycle, with
BASEBALL_API_BUDGET capped, must show in its log, in order: the walk ARRIVED
and on which attempt; `orchestrator.run` started; at least one match RESULT was
scored; and the loop stopped ON ITS OWN -- the balance could not cover the next
$50 fee, or the budget was exhausted -- never by a crash or a traceback. An
arrival that plays nothing is a FAILED smoke test.

Applies to: run_cycles.py, and creates
tests/harness/test_run_cycles_walks_with_chain_walk.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch58.py [ROOT]
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
R = os.path.join(ROOT, "run_cycles.py")
T = os.path.join(ROOT, "tests", "harness",
                 "test_run_cycles_walks_with_chain_walk.py")
r = open(R).read()

DOC = '''HOW IT WALKS
-----------
With the CLOSED LOOP (`chain_walk.walk`), servoing along a recorded chain and
looking after every push -- 40 arrivals of 40 on 2026-09-08 against dead
reckoning's 5/10 per route. The retry loop is
`overnight/chain_trials.walk_attempts`, reused rather than copied: it reloads
before every attempt, loads the chain once, stops at the first arrival, and
says which attempt arrived.

AND THE WALK RUNS IN A CHILD THIS PROCESS CAN KILL
--------------------------------------------------
`chain_walk.walk` tests its own time cap at the TOP of its loop, so the cap
cannot fire while a capture inside the loop body is blocked -- and CLAUDE.md
10.14 measured that: a 590s trial did not answer SIGALRM because it was blocked
inside a capture. So the walk is spawned as `run_cycles.py --one-trial <cycle>`
through `overnight/_harness.run_trial`, the project's one external kill: Popen,
a deadline, and p.kill() from OUTSIDE. A killed, crashed or silent child is a
SKIPPED CYCLE, never a played match. NOTHING IN THIS FILE MAY WALK IN-PROCESS:
a frozen stream there hangs the whole unattended run with no log line and
nothing able to end it.

A HIDDEN GAME WINDOW IS NOT A NAVIGATION RESULT
-----------------------------------------------
chiaki keeps heartbeating with its window on another Space, so the stream check
cannot see this; 12 of an A/B's 20 trial numbers went that way in ~15s on
2026-09-08. Guarded twice, as the trial harness guards it: the child waits for
the window before its reload, and main() waits again and re-runs the SAME cycle
number, bounded by chain_trials.WINDOW_RETRY_MAX, without counting it as a
failed walk.

Navigation is not tunable from this file, deliberately. It arrives as one
constant naming a recorded chain plus three callbacks that forward to
chain_walk, so the loop's 'improve' step has nothing here to edit but the
minigame.

PRE-REGISTERED ACCEPTANCE FOR THE FIRST LIVE SMOKE TEST
-------------------------------------------------------
One cycle, BASEBALL_API_BUDGET capped. The log must show, in order:
  1. the walk ARRIVED, and on which attempt;
  2. orchestrator.run started;
  3. at least one match RESULT was scored;
  4. the loop stopped ON ITS OWN -- the balance could not cover the next $50
     fee, or the API budget was exhausted -- and NEVER by a crash.
An arrival that plays nothing is a FAILED smoke test, not a partial pass.

THE API BUDGET IS THE REAL STOP'''

IMPORTS = '''import json
import os
import sys
import time
import traceback

import api_budget
import ensure_stream
import orchestrator
import reset_env

# THE CLOSED LOOP'S RETRY SEAM, AND THE PROJECT'S EXTERNAL KILL. `overnight/`
# is not a package -- its scripts put their own directory on the path -- so
# this does the same rather than inventing an __init__.py under a directory
# full of one-off harnesses.
#
# chain_trials and _harness are stdlib-only at import: nothing here starts a
# capture, opens the console or reads a frame. The heavy modules (chain,
# chain_walk, compass, walk_steps) are imported INSIDE the walk callbacks, so
# importing this file costs nothing and anything that never walks never loads
# cv2.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "overnight"))
import _harness
import chain_trials
from chain_trials import walk_attempts'''

LOGFN = '''def log(msg, **kw):
    # **kw because this is handed to walkers and helpers that call it with
    # flush=True -- the default `print` swallows that, a bare def does not, and
    # the TypeError surfaced as "could not reach the table" three times over.
    print(f"[cycles] {msg}", flush=True)'''

CONSTS = '''# THE CHAIN the closed loop servos along: the user's own recorded drive, and
# the only chain any measured batch has used (41 of 41 runs in
# overnight/chain_trials.json).
CHAIN = "route_user_1853"

# WALKS ONE CYCLE MAY SPEND, each after its OWN reload, stopping at the first
# arrival. Two rather than one because the reload is the whole point of a
# retry: a second walk from the same stuck pose is not a second chance, and a
# reload is the one thing that clears the NPC or the doorway post that lost the
# first. Read at CALL time from the environment, never captured in a default
# (CLAUDE.md 10.18), and a typo is REFUSED rather than silently falling back to
# one -- that is 10.1's no-op that reports like a change, in the place where it
# would cost the whole smoke test.
WALK_ATTEMPTS = 2
WALK_ATTEMPTS_ENV = "BASEBALL_CYCLE_WALK_ATTEMPTS"

# WHERE THE WALK'S EVIDENCE GOES, and it is NOT the system temp directory --
# which is where the root this replaces put it. CLAUDE.md forbids anything that
# matters there, and the chiaki tree under it was once found as 825 empty
# directories with every file gone.
# PER CYCLE AND ATTEMPT, because these folders used to overwrite each other:
# the old walker named its folder from its own loop counter and every call
# passed n=1, so cycle 1's route evidence was already gone by the time its
# stall was investigated on 2026-08-31 and the frames sitting there belonged to
# cycle 2.
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS_ROOT = os.path.join(HERE, "overnight", "cycle_frames")
JOURNAL_ROOT = os.path.join(HERE, "overnight", "cycle_journals")

# WHAT THE CHILD REPORTS BACK, and only this. chain_walk's own result carries a
# `fixes` row per iteration; a cycle needs the verdict and the bookkeeping, and
# the journal on disk keeps the rest. Curated rather than dumped so a new key
# of some unserialisable type can never make an arrived walk unreadable.
PAYLOAD_KEYS = ("arrived", "arrived_on_attempt", "attempts_allowed",
                "attempts_used", "first_walk_arrived", "retried",
                "walk_seconds_total", "walk_exceptions", "failure",
                "timeout_diagnosis", "k_final", "shots", "journal",
                "window_missing", "reset_failed")


class WindowMissing(RuntimeError):
    """No chiaki game window on screen, so nothing could be reloaded.

    NOT a navigation result and NOT a reset that will not happen: chiaki is
    alive and heartbeating, its window is merely on another macOS Space or
    behind a fullscreen app, which is why `ensure_stream.ensure()` is perfectly
    happy at the top of the cycle. Scored as a failed walk it would count
    toward MAX_CONSECUTIVE_ROUTE_FAILURES, and three of them in a row would end
    an unattended night with "something is wrong that a reset does not fix"
    while nothing about navigation was wrong at all.
    """'''

WALK = '''def walks_per_cycle(env=None):
    """How many walks one cycle may spend, read at CALL time (10.18).

    A module-level knob a harness or a test may redirect is resolved when it is
    used, never captured in a `def` line: `leg_reliability` declared every
    function as `def rate(a, b, path=STORE)` and redirecting STORE changed
    nothing, silently. The value is validated by chain_trials' own
    `_attempts_value`, which REFUSES a typo instead of quietly running one walk
    while the log says two.
    """
    env = os.environ if env is None else env
    raw = env.get(WALK_ATTEMPTS_ENV)
    if raw is None:
        return WALK_ATTEMPTS
    return chain_trials._attempts_value(raw, WALK_ATTEMPTS_ENV)


def _walk_once(n):
    """THE CHILD'S BODY. Walk to the dealer table, reloading on a miss.

    Returns `walk_attempts`'s result dict. THE VERDICT IS res["arrived"] AND
    NOTHING ELSE. What this replaced read `reached` out of a
    (wins, best_streak) TUPLE, and a tuple is always true -- (0, 0) included --
    so one wrong line here walks a missed route straight on to spend $50 at
    nothing. A dict is true exactly the same way, which is why the caller names
    the key.

    The retry loop is `overnight/chain_trials.walk_attempts`, not a second copy
    of it: it already resets before every attempt, calls `load()` ONCE because
    `Chain.load` runs ORB over every waypoint, stops at the first arrival, and
    records `arrived_on_attempt` so a retried arrival is never mistaken for a
    first-walk one. The three callbacks below are all this file owns.

    THIS RUNS IN A CHILD PROCESS, never in the loop's own. See _walk_to_table.
    """
    attempts = walks_per_cycle()
    log(f"walking to the table with the closed loop ({CHAIN}), up to "
        f"{attempts} attempt(s)")

    def do_reset(attempt):
        # RESET_ATTEMPTS LIVES HERE NOW. reset_env is deliberately fail-fast --
        # its own tests pin it to one YES press and a 60s ceiling, so an
        # unattended caller is never left hanging -- which makes retrying the
        # CALLER's job, and the caller of the reset is now this callback. A
        # dropped keystroke on the confirm dialog is transient and cost a whole
        # 5-cycle run on 2026-08-31.
        if attempt > 1:
            log(f"walk {attempt}/{attempts}: reloading and walking again")
        if not chain_trials.wait_for_game_window(log):
            # WindowMissing, deliberately its own type: it is neither a
            # navigation result nor a reset that will not happen, and the
            # parent retries the same cycle number for it rather than counting
            # a failed walk. Raised BEFORE the reload, so a hidden window never
            # burns a second attempt's 120s wait either.
            raise WindowMissing(
                f"no chiaki game window for "
                f"{chain_trials.WINDOW_WAIT_SEC:.0f}s")
        for a in range(1, RESET_ATTEMPTS + 1):
            try:
                # progress_file, which the old call omitted: reset_env clears
                # match_in_progress on a CONFIRMED reset, and that flag is the
                # guard against double-debiting $50.
                reset_env.reset_environment(log=log, progress_file=PROGRESS_FILE)
                break
            except reset_env.ResetError as e:
                log(f"reset attempt {a}/{RESET_ATTEMPTS} failed: {e}")
                if a == RESET_ATTEMPTS:
                    raise
                time.sleep(3.0)
        time.sleep(1.2)               # the world has to finish appearing

    def do_load():
        # ONCE per cycle, however many attempts it takes: Chain.load runs ORB
        # over every waypoint. Imported here rather than at module scope so
        # nothing that does not walk pays for cv2.
        import chain as chain_mod
        d = chain_trials.chain_dir(CHAIN)
        if not os.path.isdir(d):
            raise RuntimeError(f"no such chain: {d}")
        return chain_mod.Chain.load(d, log=log)

    def do_walk(attempt, ch):
        import chain_walk
        import compass
        import walk_steps as ws
        shots = os.path.join(SHOTS_ROOT, f"cycle{n:02d}_try{attempt}")
        journal = os.path.join(JOURNAL_ROOT,
                               f"cycle{n:02d}_try{attempt}.jsonl")
        os.makedirs(JOURNAL_ROOT, exist_ok=True)
        # The same arguments the trial harness walks with, so the 40-of-40 that
        # justifies this wiring and what runs here are the same walk.
        res = chain_walk.walk(ch, compass.fast_capture, ws.read_heading,
                              log=log, time_cap=chain_trials.TIME_CAP,
                              shots=shots, journal=journal,
                              end_iterations=chain_trials.END_ITERATIONS)
        res["shots"] = shots
        res["journal"] = journal
        return res

    try:
        return walk_attempts(attempts, do_reset, do_load, do_walk, log)
    except WindowMissing as e:
        log(f"{e} -- this is not a navigation result; the cycle number will be "
            f"re-run rather than counted as a failed walk")
        return {"arrived": False, "window_missing": True, "failure": str(e),
                "attempts_allowed": attempts, "attempts_used": 0}
    except reset_env.ResetError as e:
        # A reload that will not happen is not something the next cycle fixes.
        # It ended the run before this patch and it still does -- the parent
        # reads this key and stops.
        log(f"the reload failed {RESET_ATTEMPTS} times: {e}")
        return {"arrived": False, "reset_failed": True,
                "failure": f"reset: {e}",
                "attempts_allowed": attempts, "attempts_used": 0}
    except Exception as e:                                     # noqa: BLE001
        # walk_attempts re-raises a crash on the LAST attempt. That has to stay
        # a SKIPPED CYCLE and not the end of the run -- the body this replaces
        # caught the same thing per attempt and returned False -- but the
        # traceback is never swallowed.
        log(f"the walk raised {type(e).__name__}: {e}")
        for line in traceback.format_exc().rstrip().splitlines():
            log(f"  {line}")
        return {"arrived": False, "arrived_on_attempt": None,
                "attempts_allowed": attempts, "attempts_used": attempts,
                "failure": f"exception: {type(e).__name__}: {e}"}


def _payload(res):
    """The one JSON line the child prints, curated to PAYLOAD_KEYS."""
    out = {k: res.get(k) for k in PAYLOAD_KEYS if k in res}
    # NEVER the truthiness of the object, here either: a bool, always present,
    # so a parent reading a missing key can only read False.
    out["arrived"] = bool(res.get("arrived"))
    return out


def one_walk(n):
    """THE CHILD ENTRY POINT: `run_cycles.py --one-trial <cycle>`.

    Walks and prints ONE JSON object on its LAST line, which is the shape
    `_harness.run_trial` parses. It never plays a match, never reads the
    balance and never spends a dollar -- the money stays in the parent, on the
    far side of the arrival check.
    """
    # Refuse while the offline flag is set: every input path is OFF under it,
    # so this would walk a character that never moves and report the result as
    # data (CLAUDE.md 5, 10.1). chain_trials' own child guard, reused.
    chain_trials._assert_live()
    print(json.dumps(_payload(_walk_once(n))), flush=True)


def _walk_to_table(n):
    """THE PARENT: spawn the walk, and kill it from OUTSIDE if it hangs.

    `chain_walk.walk` checks its own time cap at the top of its loop, so the
    cap cannot fire while a capture inside the loop body is blocked -- and
    CLAUDE.md 10.14 was measured on exactly that, a 590s trial that did not
    answer SIGALRM because the process sat inside a capture. An in-process walk
    here would hang the whole unattended run on a frozen stream, silently, with
    nothing outside it able to end the loop.

    So the walk is a CHILD, and `_harness.run_trial` is the kill: Popen, a
    deadline, p.kill() (never terminate), the child's log forwarded live, and
    one JSON line parsed back. `(None, secs)` -- killed, crashed, or a console
    that was dead when it finished -- is a SKIPPED CYCLE, never a played match.

    The ceiling is `chain_trials.ceiling_for(attempts)`, the project's own
    formula, sized PER ATTEMPT: a ceiling sized for one walk would kill exactly
    the retries it exists to bound, which is how OPEN-5's 420s ceiling censored
    3 of 6 deep-arm trials (10.14 again).

    `cwd=HERE` is not decoration. run_trial defaults `cwd` to the parent of the
    script's directory, which is right for `overnight/chain_trials.py` and
    WRONG for a script at the checkout root -- and PROGRESS_FILE is a relative
    path, so the child would reload against a file that is not there.
    """
    attempts = walks_per_cycle()
    ceiling = chain_trials.ceiling_for(attempts)
    # Set HERE, inside a function, never at import (CLAUDE.md 5, 10.1). The
    # child inherits it, so the walks it may spend and the ceiling bounding
    # them are resolved from one number rather than read twice.
    os.environ[WALK_ATTEMPTS_ENV] = str(attempts)
    log(f"walking to the table in a child process: up to {attempts} walk(s), "
        f"killed from outside after {ceiling}s")
    res, secs = _harness.run_trial(__file__, n, ceiling, cwd=HERE, log=log)
    if res is None:
        # run_trial says None for a kill, a crash, no parseable JSON, or a
        # stream that was dead when the child finished. None of those is
        # evidence about navigation, and none of them may play a match.
        return {"arrived": False, "invalid": True, "seconds": secs,
                "attempts_allowed": attempts, "attempts_used": None,
                "failure": f"the walk reported nothing in {secs}s -- killed at "
                           f"the {ceiling}s ceiling, crashed, or the stream was "
                           f"dead when it finished"}
    res["seconds"] = secs
    return res'''

CYCLE = '''    # THE WALK OWNS THE RELOAD NOW: walk_attempts resets before EVERY attempt,
    # so a reset here would be a duplicate one and would spend a reload the
    # retry is about to spend again.
    walk = _walk_to_table(n)
    if walk.get("reset_failed"):
        # As before this patch: a reload that will not happen ends the run.
        log(f"the reload failed and will not be retried further "
            f"({walk.get('failure')}) -- stopping")
        return False
    if walk.get("window_missing"):
        # NOT a navigation failure. main() waits for the window and re-runs
        # this same cycle number, bounded, without counting it.
        log("the chiaki game window was not on screen, so nothing could be "
            "reloaded -- this cycle number will be re-run")
        return "window"
    if not walk.get("arrived"):
        # NOT fatal to the whole run. The closed loop misses about one walk in
        # eight and its failures are position-dependent, so the single most
        # effective fix is a fresh reload -- which is exactly what the next
        # cycle starts with. Ending 20 cycles because one cycle's walks missed
        # wastes a whole unattended night; the consecutive-failure count in
        # main() is the real guard against walking in circles forever.
        log(f"could not reach the table in "
            f"{walk.get('attempts_used')} walk(s) "
            f"({walk.get('failure')}) -- skipping to the next cycle")
        return "route"
    log(f"at the table: arrived on walk {walk.get('arrived_on_attempt')} of "
        f"{walk.get('attempts_allowed')}, "
        f"{walk.get('walk_seconds_total')}s walking, "
        f"shots {walk.get('shots')}")

    # _reset_progress AFTER THE WALK, AND IT CANNOT GO BEFORE IT. It reads the
    # wallet off the PAUSE MENU, and the reloads now live inside
    # walk_attempts -- so run before the walk it would read the wallet from
    # before this cycle's reload, i.e. the empty one the previous cycle left,
    # write that to the progress file, and run() (which trusts its persisted
    # balance over anything on screen) would stop immediately having played
    # nothing. After the walk is also the only point where the reload that
    # happened is the LAST one. The reload restores the same wallet on every
    # attempt, so the figure recorded here is right however many were used.
    balance = _reset_progress()'''

MAINLOOP = '''    n = 1
    window_retries = 0
    while n <= cycles:
        if api_budget.remaining() < BUDGET_RESERVE:
            log(f"only {api_budget.remaining()} API calls left (reserve is "
                f"{BUDGET_RESERVE}) — stopping before cycle {n} rather than "
                "abandoning a paid match halfway")
            break
        try:
            outcome = cycle(n)
            # THE SECOND WINDOW LAYER, and it is the trial harness's own:
            # wait for the window, then RE-RUN THE SAME NUMBER, bounded, and
            # never let it reach route_failures. chiaki keeps heartbeating
            # with its window on another Space, so the stream check at the top
            # of cycle() is perfectly happy while nothing can be reloaded --
            # 12 of an A/B's 20 trial numbers went that way in ~15s on
            # 2026-09-08. Scored as failed walks, three of these in a row
            # would end an unattended night with "something is wrong that a
            # reset does not fix" and nothing wrong with navigation.
            if outcome == "window":
                if window_retries < chain_trials.WINDOW_RETRY_MAX:
                    window_retries += 1
                    log(f"waiting for the game window, then re-running cycle "
                        f"{n} ({window_retries}/"
                        f"{chain_trials.WINDOW_RETRY_MAX}) — NOT counted as a "
                        f"failed walk")
                    chain_trials.wait_for_game_window(log)
                    continue
                # Bounded, so this cannot loop forever on a window that is
                # never coming back: once the retries are spent it is treated
                # as a missed cycle like any other and the run moves on.
                log(f"the game window was still missing after "
                    f"{window_retries} re-runs — counting cycle {n} as a "
                    f"missed walk")
                outcome = "route"
            window_retries = 0
            if outcome == "route":
                route_failures += 1
                if route_failures >= MAX_CONSECUTIVE_ROUTE_FAILURES:
                    log(f"{route_failures} cycles in a row could not reach the "
                        "table — something is wrong that a reset does not fix")
                    break
                n += 1
                continue
            route_failures = 0
            if not outcome:
                break'''

TAIL = '''        w, l, d, bal, _, _ = orchestrator.load_progress(PROGRESS_FILE)
        log(f"after cycle {n}: {w}W/{l}L/{d}D, ${bal} left, "
            f"{api_budget.used()} API calls used "
            f"(~${api_budget.used() * api_budget.APPROX_COST_PER_CALL:.2f})")
        n += 1'''

ENTRY = '''if __name__ == "__main__":
    # THE CHILD ENTRY. `--one-trial <cycle>` is the argument shape
    # `_harness.run_trial` spawns, which is why it is spelled that way here;
    # it is the ONLY path in this file that walks, and it never plays a match
    # or spends a dollar.
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        one_walk(int(sys.argv[2]))
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)'''

edits_r = [
 ('THE API BUDGET IS THE REAL STOP', DOC),
 ('''import os
import sys
import time
import traceback

import api_budget
import ensure_stream
import go
import orchestrator
import reset_env''', IMPORTS),
 ('''def log(msg, **kw):
    # **kw because this gets passed as go.main(log=...), and go calls it with
    # flush=True — the default `print` swallows that, a bare def does not, and
    # the TypeError surfaced as "could not reach the table" three times over.
    print(f"[cycles] {msg}", flush=True)''', LOGFN),
 ('''# Walking to the table succeeds ~85% of the time (go.py), so a single failure
# is normal and not a reason to end a cycle. Three in a row is a real problem
# — a changed spawn, a stuck character, a dead stream — and burning further
# attempts on it just wastes wall-clock.
ROUTE_ATTEMPTS = 3''', CONSTS),
 ('''def _walk_to_table(n):
    for i in range(1, ROUTE_ATTEMPTS + 1):
        try:
            # go.main returns (wins, best_streak). Truth-testing the TUPLE is
            # always True — (0, 0) included — which would march on to buy a
            # match without being at the table. Read the count.
            #
            # A shot_root PER CYCLE AND ATTEMPT. go names its folders
            # attempt{i} from its own loop counter, and since every call here
            # passes n=1 they all write to attempt01 — so each cycle silently
            # overwrote the previous one's frames. Cycle 1's route evidence was
            # already gone by the time its stall was investigated on
            # 2026-08-31, and the frames sitting there belonged to cycle 2.
            reached, _best = go.main(n=1, log=log, stop_on_fail=False,
                                     shot_root=f"/tmp/go_shots/cycle{n:02d}_try{i}")
            if reached:
                return True
        except Exception as e:
            log(f"route attempt {i} raised {type(e).__name__}: {e}")
        log(f"route attempt {i}/{ROUTE_ATTEMPTS} did not reach the table")
    return False''', WALK),
 ('''    log("reloading the last save")
    # reset_env is deliberately fail-fast — its own tests pin it to one YES
    # press and a 60s ceiling, so an unattended caller is never left hanging.
    # That makes retrying the CALLER's job. A dropped keystroke on the confirm
    # dialog is transient and cost a whole 5-cycle run on 2026-08-31.
    for attempt in range(1, RESET_ATTEMPTS + 1):
        try:
            reset_env.reset_environment(log=log)
            break
        except reset_env.ResetError as e:
            log(f"reset attempt {attempt}/{RESET_ATTEMPTS} failed: {e}")
            if attempt == RESET_ATTEMPTS:
                raise
            time.sleep(3.0)
    balance = _reset_progress()

    if not _walk_to_table(n):
        # NOT fatal to the whole run. The route is ~85% per attempt and its
        # failures are position-dependent, so the single most effective fix is
        # a fresh reset — which is exactly what the next cycle starts with.
        # Ending 20 cycles because one walk missed three times wastes a whole
        # unattended night; the consecutive-failure count below is the real
        # guard against walking in circles forever.
        log(f"could not reach the table in {ROUTE_ATTEMPTS} attempts — "
            "skipping to the next cycle")
        return "route"''', CYCLE),
 ('''    for n in range(1, cycles + 1):
        if api_budget.remaining() < BUDGET_RESERVE:
            log(f"only {api_budget.remaining()} API calls left (reserve is "
                f"{BUDGET_RESERVE}) — stopping before cycle {n} rather than "
                "abandoning a paid match halfway")
            break
        try:
            outcome = cycle(n)
            if outcome == "route":
                route_failures += 1
                if route_failures >= MAX_CONSECUTIVE_ROUTE_FAILURES:
                    log(f"{route_failures} cycles in a row could not reach the "
                        "table — something is wrong that a reset does not fix")
                    break
                continue
            route_failures = 0
            if not outcome:
                break''', MAINLOOP),
 ('''        w, l, d, bal, _, _ = orchestrator.load_progress(PROGRESS_FILE)
        log(f"after cycle {n}: {w}W/{l}L/{d}D, ${bal} left, "
            f"{api_budget.used()} API calls used "
            f"(~${api_budget.used() * api_budget.APPROX_COST_PER_CALL:.2f})")''', TAIL),
 ('''if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)''', ENTRY),
]

NEW_TEST = '''"""run_cycles walks with the CLOSED LOOP, in a child it can kill -- and refuses
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

import tempfile
_TMP = tempfile.mkdtemp(prefix="run_cycles_test_")
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
'''

# ---------------------------------------- assert EVERYTHING, then write
for a, b in edits_r:
    assert r.count(a) == 1, ("run_cycles anchor", a[:60], r.count(a))
assert not os.path.exists(T), f"{T} already exists"
assert os.path.isdir(os.path.dirname(T)), "tests/harness/ must exist"
assert os.path.isfile(os.path.join(ROOT, "overnight", "chain_trials.py"))
assert os.path.isfile(os.path.join(ROOT, "overnight", "_harness.py"))
assert os.path.isfile(os.path.join(ROOT, "chain_walk.py"))
assert "chain_walk" not in r and "walk_attempts" not in r
assert "_harness" not in r and "run_trial" not in r
assert "SHOTS_ROOT" not in r and "JOURNAL_ROOT" not in r
assert r.count("import go") == 1
assert r.count("/tmp/go_shots") == 1
assert r.count("ROUTE_ATTEMPTS") == 4, r.count("ROUTE_ATTEMPTS")
assert r.count("MAX_CONSECUTIVE_ROUTE_FAILURES") == 2
assert r.count("_reset_progress()") == 2
assert r.count("except api_budget.BudgetExhausted as e:") == 1
assert r.count("if not ensure_stream.ensure(log=log):") == 1
assert r.count("for n in range(1, cycles + 1):") == 1

for a, b in edits_r:
    r = r.replace(a, b)

ast.parse(r)
ast.parse(NEW_TEST)

# the walker is gone, with every comment that named it
assert "import go" not in r
assert "go.main" not in r
assert "ROUTE_ATTEMPTS" not in r
assert "/tmp" not in r
# ... and the closed loop is in
assert r.count("from chain_trials import walk_attempts") == 1
assert r.count("walk_attempts(attempts, do_reset, do_load, do_walk, log)") == 1
assert r.count("chain_walk.walk(ch, compass.fast_capture, ws.read_heading,") == 1
assert r.count("CHAIN = \"route_user_1853\"") == 1
assert r.count("WALK_ATTEMPTS = 2") == 1
assert r.count("def walks_per_cycle(env=None):") == 1
assert r.count("chain_trials._attempts_value(raw, WALK_ATTEMPTS_ENV)") == 1
assert r.count('SHOTS_ROOT = os.path.join(HERE, "overnight", "cycle_frames")') == 1
assert r.count('JOURNAL_ROOT = os.path.join(HERE, "overnight", "cycle_journals")') == 1
# THE EXTERNAL KILL: one spawn, sized per attempt, in the checkout, and the
# child entry that answers it
assert r.count("import _harness") == 1
assert r.count(
    "res, secs = _harness.run_trial(__file__, n, ceiling, cwd=HERE, log=log)") == 1
assert r.count("ceiling = chain_trials.ceiling_for(attempts)") == 1
assert r.count("def _walk_once(n):") == 1
assert r.count("def one_walk(n):") == 1
assert r.count("chain_trials._assert_live()") == 1
assert r.count('sys.argv[1] == "--one-trial"') == 1
# the parent must not walk: the only chain_walk call is inside the child's body
assert r.index("def _walk_once(n):") < r.index("chain_walk.walk(ch,") \
    < r.index("def _walk_to_table(n):")
# THE WINDOW: its own type, its own outcome, and a BOUNDED re-run of the same
# cycle number that never reaches route_failures
assert r.count("class WindowMissing(RuntimeError):") == 1
assert r.count("raise WindowMissing(") == 1
assert r.count("except WindowMissing as e:") == 1
assert r.count('return "window"') == 1
assert r.count('if outcome == "window":') == 1
assert r.count("if window_retries < chain_trials.WINDOW_RETRY_MAX:") == 1
# TWICE: the child probes before its reload, and main() waits again before
# re-running the same cycle number. Both layers, as the trial harness has.
assert r.count("chain_trials.wait_for_game_window(log)") == 2
assert r.count("        if not chain_trials.wait_for_game_window(log):\n") == 1
assert r.count("                    chain_trials.wait_for_game_window(log)\n") == 1
# every guard the file already had, still there
assert r.count("RESET_ATTEMPTS") == 6, r.count("RESET_ATTEMPTS")
# 3, not 2: WindowMissing's docstring and main()'s window comment both name
# it, because a hidden window counted as a failed walk is exactly what would
# trip it.
assert r.count("MAX_CONSECUTIVE_ROUTE_FAILURES") == 3
assert r.count("except api_budget.BudgetExhausted as e:") == 1
assert r.count("if not ensure_stream.ensure(log=log):") == 1
assert r.count('return "route"') == 1
assert r.count('                outcome = "route"\n') == 1
assert r.count("_reset_progress()") == 2
# the loop still advances on every path, so a window that never comes back
# cannot spin forever
assert r.count("while n <= cycles:") == 1
assert r.count("n += 1") == 2
# ... and _reset_progress runs AFTER the walk, which is the ordering the
# module docstring's whole argument rests on
assert (r.index("walk = _walk_to_table(n)")
        < r.index("balance = _reset_progress()")
        < r.index("orchestrator.run(target_wins=999"))

open(R, "w").write(r)
open(T, "w").write(NEW_TEST)
print("patch58 applied to", ROOT)
print("  run_cycles.py rewired to chain_walk via chain_trials.walk_attempts,")
print("  in a child process killed from outside by _harness.run_trial")
print("  new test:", T)
