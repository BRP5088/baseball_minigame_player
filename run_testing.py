"""Throwaway-save runs: a COPY of Taylere's save, so losses cost nothing real.

    python3 run_testing.py --reset      # after (re-)copying the save on console
    python3 run_testing.py              # run until the cap or the money runs out

WHY A COPY BEATS A FRESH SAVE
------------------------------
Same story progress, so the minigame is already available — no setup play
needed. Same card collection, so KNOWN_BAN_ROSTER is exactly right and every
grid position resolves from the roster with identical lock state: no extra
vision calls, and none of the "does the catalogue still apply" doubt a fresh
save would introduce.

WHY THE WIN RATE STOPS MATTERING
---------------------------------
The record so far is 0W/3L/3D, and on a real save that drains the balance and
ends the session. On a copy it doesn't matter: when the money runs out, copy
her save again and the throwaway is back to its starting balance.

    per copy : $246 -> 4 matches -> ~72 logged turns

That is what makes the project's headline question reachable. Whether
`secondary` (fielding / speed) affects outcomes still reads "cannot conclude",
but the target moved a long way once the tactics TYPE started being logged and
the pitching-half margins were flipped correctly. Re-measured 2026-08-26 by
`analyze_match_log.py` on the same 39 rows:

    usable rows      19/39  (was 12 under the old accounting)
    secondary == 0   n=11, mean margin +0.27
    secondary >  0   n=8,  mean margin +1.25
    permutation p    0.192  -- still CANNOT CONCLUDE
    effect size      0.64 sd -> ~156 more logged turns, about 8 matches

So roughly two re-copies, not the seven this file used to claim. Run
`python3 analyze_match_log.py` after any session for the current numbers rather
than trusting this comment — that is exactly the staleness this project keeps
getting burned by.

Losing every match still produces the data, because a logged turn is a logged
turn regardless of who won it.

THE ONE OPERATIONAL TRAP
-------------------------
`progress_testing.json` is authoritative for balance — the script cannot see
the console's real coins. Re-copy the save WITHOUT re-seeding this file and the
two silently diverge: the script thinks it has $46 left and stops, while the
game actually has $246. Hence `--reset`, which must be run every time the save
is re-copied.
"""

import json
import os
import subprocess
import sys

PROGRESS_FILE = "progress_testing.json"
ENTRY_COST = 50
# Taylere's save balance, which every copy therefore starts at. If the copy
# shows something different in the pause menu, pass it: --reset <coins>
COPY_START_BALANCE = 246
# NEVER set this to exactly one match's cost. `max_spend` is checked as
# `spent + 50 > max_spend` on EVERY match_start_prompt, and the loop sees that
# prompt more than once per match (the ROUND transition overlay is classified as
# one). With max_spend=50 the 2026-08-25 run paid $50, applied 3/3 bans, the
# match began — and then the cap stopped it before a single turn was played.
#
# C5 now refuses the second debit, so a cap above one match is safe; this just
# stops the cap itself from ending a match it already paid for.
DEFAULT_SPEND = 250          # 5 matches; more than one $246 copy can afford anyway
MIN_SAFE_SPEND = 100         # two matches: one to play, one of headroom


def reset(balance):
    """Re-seed tracking to a freshly copied save's starting state."""
    prior = None
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                prior = json.load(f)
        except Exception:
            pass
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"wins": 0, "losses": 0, "draws": 0, "balance": balance}, f)
    if prior:
        print(f"Previous throwaway state: {prior['wins']}W/{prior['losses']}L/"
              f"{prior['draws']}D, ${prior['balance']} left.")
    print(f"Reset {PROGRESS_FILE} to ${balance} "
          f"({balance // ENTRY_COST} matches).")
    print("\nNOTE: the cumulative data lives in match_log.jsonl, which is NOT "
          "reset — that is the point. Only the per-copy bookkeeping restarts.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--reset" in args:
        i = args.index("--reset")
        bal = int(args[i + 1]) if len(args) > i + 1 else COPY_START_BALANCE
        reset(bal)
        sys.exit(0)

    if not os.path.exists(PROGRESS_FILE):
        print(f"{PROGRESS_FILE} does not exist. Copy her save on the console, "
              f"then:\n\n    python3 run_testing.py --reset\n")
        sys.exit(1)

    spend = int(args[0]) if args and args[0].isdigit() else DEFAULT_SPEND
    if spend < MIN_SAFE_SPEND:
        print(f"max_spend ${spend} is below ${MIN_SAFE_SPEND}. A one-match cap "
              "stops the run at the SECOND match_start_prompt — which arrives "
              "mid-match, after the fee is paid and the bans are placed. "
              f"Raising to ${MIN_SAFE_SPEND}.")
        spend = MIN_SAFE_SPEND

    # `-u`, and say what is happening first. Preflight runs the whole offline
    # suite (~4 minutes) before anything touches the game, and without -u its
    # stdout is block-buffered into the parent's redirected output — so a live
    # run showed FOUR MINUTES of complete silence between "go" and the first
    # keypress. The parent's own -u does not propagate to a subprocess. On
    # 2026-08-26 the user reasonably concluded it had hung.
    print("Running preflight (includes the full offline test suite, ~40s)...",
          flush=True)
    if subprocess.run([sys.executable, "-u", "preflight.py", PROGRESS_FILE]).returncode:
        print("Preflight found a blocker — not starting.")
        sys.exit(1)

    with open(PROGRESS_FILE) as f:
        bal = json.load(f)["balance"]
    if bal < ENTRY_COST:
        print(f"\nThrowaway save is down to ${bal}. Re-copy her save on the "
              f"console, then:\n\n    python3 run_testing.py --reset\n")
        sys.exit(1)

    import orchestrator
    print(f"\nTHROWAWAY SAVE: ${bal} on hand, cap ${spend}. "
          f"Losses cost nothing — be aggressive.\n")
    orchestrator.run(
        target_wins=999,          # the cap or the balance is the stopping point
        progress_file=PROGRESS_FILE,
        max_spend=spend,
        compare_local_reads=True,
        log_screenshots=True,
    )
