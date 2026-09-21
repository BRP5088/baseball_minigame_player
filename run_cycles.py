"""Unattended training loop: play until broke, reload the save, repeat.

    python3 run_cycles.py [cycles]

One CYCLE is: reload the last save (which restores the in-game balance to
whatever that save holds), walk to the table, then play matches until the money
runs out.
That is the largest unit of work that needs no human, which is why it is the
unit here.

WHY A SCRIPT AND NOT A SHELL LOOP
---------------------------------
Two things have to happen BETWEEN a reset and the next match, and neither is
obvious from outside:

  1. The progress file's balance must be made to match the reloaded save.
     Reloading restores the money in-game, but orchestrator trusts its own
     persisted balance over anything on screen (see run()'s docstring), so
     leaving it alone means the next cycle thinks it is still broke and stops
     immediately. The amount is READ, not assumed — see _read_balance().
  2. match_in_progress must be cleared. It is the guard against double-debiting
     a match, and a save reload abandons whatever match it was protecting.

HOW IT WALKS
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

THE API BUDGET IS THE REAL STOP
-------------------------------
Every read costs money. api_budget is a hard ceiling for the whole process, so
set BASEBALL_API_BUDGET once and every cycle draws from the same pool: an early
cycle that burns through it stops the run rather than quietly spending more.
Cycles remaining is NOT the binding constraint and should not be treated as one.
"""

import json
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
from chain_trials import walk_attempts

# What "Load Last Save" restores the wallet to -- CLAUDE.md section 4: "Load Last
# Save restores the wallet to $246", the same figure every reload, not a guess.
# _read_balance() still READS the pause menu rather than assuming this outright
# -- a read is the only way to CATCH a reader gone wrong, and I-40 is a reader
# gone wrong: a live reload read $286 off a screen CLAUDE.md's own record says
# holds $246, and it was trusted, so run()'s max_spend was set from the bad
# number. A reload's OWN wallet cannot itself be $286 -- only the reader can be
# -- so the read is now used to DETECT a disagreement, never to override this
# constant; see _read_balance's disagreement guard.
#
# DO NOT read money off the coin in the bottom-left corner. That is HEALTH.
# Mistaking it for the balance on 2026-08-31 produced a confident, wrong
# "the save only restores $100" and a progress file edited to match it.
# Money is visible ONLY on the pause menu, which is what _read_balance() uses.
RELOAD_WALLET = 246
PROGRESS_FILE = "progress_testing.json"
MATCH_FEE = 50

# THE CHAIN the closed loop servos along: the user's own recorded drive, and
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
    """

# The confirm dialog can drop a keystroke. reset_env fails fast by design
# (one YES press, 60s ceiling) so the retry belongs here.
RESET_ATTEMPTS = 3

# A missed walk is normal; three cycles of missed walks is not, and
# repeating it all night would burn resets and learn nothing.
MAX_CONSECUTIVE_ROUTE_FAILURES = 3

# Leave enough budget to finish a match already paid for. A match has cost
# 20-89 calls; stopping a cycle with less than this in reserve means paying $50
# for a match that gets abandoned halfway through.
BUDGET_RESERVE = 120


def log(msg, **kw):
    # **kw because this is handed to walkers and helpers that call it with
    # flush=True -- the default `print` swallows that, a bare def does not, and
    # the TypeError surfaced as "could not reach the table" three times over.
    print(f"[cycles] {msg}", flush=True)


def _read_balance():
    """What a reloaded save holds -- READ, but checked against the one thing that
    is already known about it: CLAUDE.md section 4 says a reload restores the
    SAME $246 every time, so this is not a stale figure that might drift like a
    mid-match balance would; it is a constant.

    One vision call per cycle, and it must be the PAUSE MENU one — the coin in
    the bottom-left of the world HUD is health, not money, and reading it as
    money on 2026-08-31 produced a confident wrong answer twice over.

    I-40: a live read answered $286 right after a reload — CLAUDE.md's own
    record says that screen holds $246 — and it was trusted anyway: run()'s
    max_spend was set to $286, four matches were played, and the fifth found
    the game's actual wallet at $46. A reload's wallet cannot itself be $286;
    only the READER can be. So a read that disagrees with RELOAD_WALLET, or
    fails outright, is treated as the reader being wrong and RELOAD_WALLET is
    used instead — never the raw reading, in either failure mode.
    """
    try:
        bal = orchestrator.read_balance_from_pause_menu()
    except Exception as e:
        log(f"could not read the balance ({type(e).__name__}: {e}) — using the "
            f"known reload constant ${RELOAD_WALLET} (CLAUDE.md section 4)")
        return RELOAD_WALLET
    if bal != RELOAD_WALLET:
        log(f"[I-40] the local reader said ${bal}, which DISAGREES with the "
            f"known reload constant ${RELOAD_WALLET} (CLAUDE.md section 4: "
            f"'Load Last Save restores the wallet to $246') — a reload's own "
            f"wallet does not move, so the READER is wrong here, not the "
            f"wallet. Using ${RELOAD_WALLET} for max_spend, not ${bal}.")
        return RELOAD_WALLET
    log(f"read ${bal} off the pause menu")
    return bal


def _reset_progress():
    """Make the progress file agree with the save that was just reloaded."""
    wins, losses, draws, _bal, _mip, _bans = orchestrator.load_progress(PROGRESS_FILE)
    balance = _read_balance()
    orchestrator.save_progress(wins, losses, draws, balance, PROGRESS_FILE,
                               match_in_progress=False,
                               bans_done_this_match=False)
    log(f"progress reset: balance ${balance}, "
        f"record {wins}W/{losses}L/{draws}D carried forward")
    return balance


def walks_per_cycle(env=None):
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
    return res


def cycle(n):
    log(f"=== cycle {n} ===")
    if not ensure_stream.ensure(log=log):
        log("stream is down and would not come back — stopping")
        return False

    # THE WALK OWNS THE RELOAD NOW: walk_attempts resets before EVERY attempt,
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
    balance = _reset_progress()

    # max_spend is the whole restored wallet, whatever it actually turned out
    # to be: run() stops on its own once the balance cannot cover the next fee.
    orchestrator.run(target_wins=999, max_spend=balance,
                     progress_file=PROGRESS_FILE, compare_local_reads=True)
    return True


def main(cycles=5):
    route_failures = 0
    import event_log
    event_log.log_regions()
    log(f"{cycles} cycles, API budget {api_budget.budget()} calls "
        f"(~${api_budget.budget() * api_budget.APPROX_COST_PER_CALL:.2f})")

    # THE RESERVE MUST FIT INSIDE THE BUDGET, or nothing can ever run.
    #
    # BUDGET_RESERVE is 120 and api_budget.DEFAULT_BUDGET is 60, so with
    # BASEBALL_API_BUDGET unset the loop below took its "stopping before cycle
    # 1" branch every time: a plausible, authoritative budget message and ZERO
    # matches played, forever. A success path and a no-op path with identical
    # output — catalogue item six — sitting on the main runner.
    #
    # This is deliberately an ERROR and not a silent raise of DEFAULT_BUDGET:
    # that constant caps the user's REAL money, and quietly doubling it to make
    # a runner start would be exactly the wrong repair.
    if api_budget.budget() < BUDGET_RESERVE:
        raise SystemExit(
            f"API budget is {api_budget.budget()} calls but BUDGET_RESERVE is "
            f"{BUDGET_RESERVE}, so no cycle can ever start — the runner would "
            f"report a budget stop and play nothing.\n"
            f"A match costs 20-89 calls, so the reserve is right; the budget is "
            f"too small.\n"
            f"Set one explicitly, e.g.:  BASEBALL_API_BUDGET=300 python3 "
            f"run_cycles.py")
    n = 1
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
                break
        except api_budget.BudgetExhausted as e:
            log(f"API budget exhausted: {e}")
            break
        except Exception:
            # STOP, do not press on. Resets and routes already retry internally,
            # so anything reaching here is a failure those did not anticipate —
            # and repeating an unknown broken state four more times spends $50 a
            # match to learn nothing. The traceback must survive either way: an
            # unattended run nobody is watching is exactly where a swallowed
            # exception does its damage.
            log(f"cycle {n} failed:\n{traceback.format_exc()}")
            break
        w, l, d, bal, _, _ = orchestrator.load_progress(PROGRESS_FILE)
        log(f"after cycle {n}: {w}W/{l}L/{d}D, ${bal} left, "
            f"{api_budget.used()} API calls used "
            f"(~${api_budget.used() * api_budget.APPROX_COST_PER_CALL:.2f})")
        n += 1
    w, l, d, bal, _, _ = orchestrator.load_progress(PROGRESS_FILE)
    log(f"DONE: {w}W/{l}L/{d}D, ${bal} on hand, {api_budget.used()} API calls "
        f"(~${api_budget.used() * api_budget.APPROX_COST_PER_CALL:.2f})")


if __name__ == "__main__":
    # THE CHILD ENTRY. `--one-trial <cycle>` is the argument shape
    # `_harness.run_trial` spawns, which is why it is spelled that way here;
    # it is the ONLY path in this file that walks, and it never plays a match
    # or spends a dollar.
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        one_walk(int(sys.argv[2]))
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
