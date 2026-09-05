"""Tonight's session: Taylere's save, hard-capped at 3 matches.

    source ~/.zshrc.secrets && python3 run_tonight.py

Runs preflight first and REFUSES to start if it reports a blocker — the whole
point of the checks is that the failures they catch are silent, so a run that
skips them looks fine for twenty minutes and then isn't.

Why the caps are what they are:

* `progress_file` is Taylere's, so her wins/losses/balance stay separate from
  the default save. Passing the wrong file here mixes two people's trophy
  progress with no way to unpick it afterwards.
* `max_spend=150` is 3 matches at $50. This is independent of her real balance
  ($246, i.e. 4 affordable) — the cap is what stops the session, not the money
  running out, so an overrun costs nothing real.
* `target_wins` is set high on purpose: the spend cap is the intended stopping
  condition. A low win target that happened to be met early would end the
  session before the 3 matches this run exists to observe.
"""

import os
import shutil
import subprocess
import sys
import time

# NOTE: orchestrator is imported inside __main__, not here. It builds an
# Anthropic client at module scope, so importing it up top makes a missing
# PERSONAL_ANTHROPIC_API_KEY raise a bare KeyError traceback BEFORE preflight
# can run — hiding the clean, actionable message preflight exists to print.

PROGRESS_FILE = "progress_taylere.json"
MATCHES = 3
ENTRY_COST = 50

# State this script WRITES, and can therefore corrupt. Backed up before every
# run because it is someone else's record.
#
# NOTE ON SCOPE, so this isn't mistaken for more than it is: the game's own
# saves are NOT here and cannot be. This is a PS5 title played over Chiaki-ng
# remote play — Chiaki streams video and forwards input, while the game and its
# save data live entirely on the console. Nothing on this Mac can read or
# restore a PS5 save; that is PS Plus cloud storage or a USB export, done from
# the console. So an in-game loss or a spent entry fee is NOT recoverable by
# anything here, which is exactly why max_spend is the real protection.
# What IS recoverable is our own bookkeeping, below.
BACKUP_FILES = [PROGRESS_FILE, "match_log.jsonl",
                "known_ban_roster_learned.json"]


def backup_state():
    """Timestamped copy of our own tracked state. Returns the directory."""
    d = os.path.join("state_backups", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(d, exist_ok=True)
    saved = []
    for f in BACKUP_FILES:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(d, os.path.basename(f)))
            saved.append(f)
    print(f"Backed up {len(saved)} state file(s) to {d}/")
    for f in saved:
        print(f"    {f}")
    if not saved:
        print("    (nothing to back up yet — first run)")
    return d


if __name__ == "__main__":
    print("Running preflight...\n")
    if subprocess.run([sys.executable, "preflight.py", PROGRESS_FILE]).returncode:
        print("Preflight found a blocker — not starting. Fix the above and rerun.")
        sys.exit(1)

    print()
    backup_dir = backup_state()
    print(f"\nIf this run corrupts her record, restore with:\n"
          f"    cp {backup_dir}/* .\n")

    import orchestrator  # after preflight, so a missing key reports cleanly

    print(f"\nStarting: {PROGRESS_FILE}, capped at {MATCHES} matches "
          f"(${MATCHES * ENTRY_COST}).\n")
    orchestrator.run(
        target_wins=99,
        progress_file=PROGRESS_FILE,
        max_spend=MATCHES * ENTRY_COST,
        # Audit mode: logs what the local readers WOULD have said next to the
        # vision read, without letting them drive anything. This is the data
        # that decides whether the §4c reader self-validation can be trusted to
        # replace the per-turn API call.
        compare_local_reads=True,
        # Frames for tuning the settle/motion thresholds afterwards.
        log_screenshots=True,
    )
