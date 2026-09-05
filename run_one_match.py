"""Finish the ONE match already paid for on the console, then stop.

Why this exists rather than `run_testing.py 100`:

`run_testing.py` floors max_spend at MIN_SAFE_SPEND (100), which buys TWO more
matches — and its startup check refuses to run at all when the tracked balance
is under $50, so the obvious brake (set balance low) blocks the run instead of
bounding it.

`max_spend=0` is the exact lever. At a match_start_prompt:
  * while `match_in_progress` is True, the C5 guard refuses to debit and the
    loop continues — so the in-progress match plays normally;
  * once that match's result is scored and the flag clears, the next prompt
    hits `spent + 50 > max_spend` (0 + 50 > 0) and the loop stops.

Net effect: play exactly the match that is already running, then exit. No new
money is ever spent, whatever the tracked balance says.

    BASEBALL_DEAL_WAIT=1 python3 run_one_match.py
"""

import json
import os
import sys

PROGRESS_FILE = "progress_testing.json"

if not os.path.exists(PROGRESS_FILE):
    sys.exit(f"{PROGRESS_FILE} does not exist")

with open(PROGRESS_FILE) as f:
    prog = json.load(f)

if not prog.get("match_in_progress"):
    sys.exit(
        "progress says no match is in progress, so there is nothing to finish "
        "and max_spend=0 would stop immediately. Use run_testing.py to buy a "
        "match, or set match_in_progress if one really is live on the console.")

import orchestrator

print(f"\nFINISHING THE MATCH ALREADY IN PROGRESS. "
      f"Tracked balance ${prog.get('balance')}, no new match will be bought "
      f"(max_spend=0).")
print(f"Deal gate: {'ON' if orchestrator.POST_PLAY_WAIT_FOR_DEAL else 'off'}\n")

orchestrator.run(
    target_wins=999,
    progress_file=PROGRESS_FILE,
    max_spend=0,              # the brake: never buy a NEW match
    compare_local_reads=True,
    log_screenshots=True,
)
