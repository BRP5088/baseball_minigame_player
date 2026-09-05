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

THE API BUDGET IS THE REAL STOP
-------------------------------
Every read costs money. api_budget is a hard ceiling for the whole process, so
set BASEBALL_API_BUDGET once and every cycle draws from the same pool: an early
cycle that burns through it stops the run rather than quietly spending more.
Cycles remaining is NOT the binding constraint and should not be treated as one.
"""

import os
import sys
import time
import traceback

import api_budget
import ensure_stream
import go
import orchestrator
import reset_env

# What "Load Last Save" restores the wallet to, per the user. Only a FALLBACK:
# the real figure is READ, because a stale one silently mis-sizes the run.
#
# DO NOT read money off the coin in the bottom-left corner. That is HEALTH.
# Mistaking it for the balance on 2026-08-31 produced a confident, wrong
# "the save only restores $100" and a progress file edited to match it.
# Money is visible ONLY on the pause menu, which is what _read_balance() uses.
RESET_BALANCE_FALLBACK = 246
PROGRESS_FILE = "progress_testing.json"
MATCH_FEE = 50

# Walking to the table succeeds ~85% of the time (go.py), so a single failure
# is normal and not a reason to end a cycle. Three in a row is a real problem
# — a changed spawn, a stuck character, a dead stream — and burning further
# attempts on it just wastes wall-clock.
ROUTE_ATTEMPTS = 3

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
    # **kw because this gets passed as go.main(log=...), and go calls it with
    # flush=True — the default `print` swallows that, a bare def does not, and
    # the TypeError surfaced as "could not reach the table" three times over.
    print(f"[cycles] {msg}", flush=True)


def _read_balance():
    """What the reloaded save ACTUALLY holds, not what it used to hold.

    Reading beats assuming here regardless of what the number turns out to be:
    run() trusts its persisted balance over anything on screen, so a stale
    figure has it buying matches the wallet cannot cover, or stopping early on
    money it actually has.

    One vision call per cycle, and it must be the PAUSE MENU one — the coin in
    the bottom-left of the world HUD is health, not money, and reading it as
    money on 2026-08-31 produced a confident wrong answer twice over.
    """
    try:
        bal = orchestrator.read_balance_from_pause_menu()
        log(f"read ${bal} off the pause menu")
        return bal
    except Exception as e:
        log(f"could not read the balance ({type(e).__name__}: {e}) — assuming "
            f"${RESET_BALANCE_FALLBACK}, which may be wrong in either direction")
        return RESET_BALANCE_FALLBACK


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


def _walk_to_table(n):
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
    return False


def cycle(n):
    log(f"=== cycle {n} ===")
    if not ensure_stream.ensure(log=log):
        log("stream is down and would not come back — stopping")
        return False

    log("reloading the last save")
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
        return "route"

    # max_spend is the whole restored wallet, whatever it actually turned out
    # to be: run() stops on its own once the balance cannot cover the next fee.
    orchestrator.run(target_wins=999, max_spend=balance,
                     progress_file=PROGRESS_FILE, compare_local_reads=True)
    return True


def main(cycles=5):
    route_failures = 0
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
    for n in range(1, cycles + 1):
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
    w, l, d, bal, _, _ = orchestrator.load_progress(PROGRESS_FILE)
    log(f"DONE: {w}W/{l}L/{d}D, ${bal} on hand, {api_budget.used()} API calls "
        f"(~${api_budget.used() * api_budget.APPROX_COST_PER_CALL:.2f})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
