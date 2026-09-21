#!/usr/bin/env python3
"""Summarise overnight/run_one_match_*.log files into one row per run (I-19).

Usage: run_census.py [<log> ...] [--json]
Defaults to overnight/run_one_match_*.log, sorted by name.

I-19b: `deal_timeouts` used to grep only the pre-I-09 combined message
("no replacement card seen"), which commit 028e78f split in two
(orchestrator.wait_for_hand_deal). Both old and new wordings are counted here
so old and new logs agree. Also adds the refusal-shape columns the 2026-09-20
census (agent_progress/census-20260920/progress.md) had to count by hand.

QA round 4 / I-26: `stray_guard` used to grep only "went unreadable DURING
this", which I-26 (commit cb5f26d, merged 67f3851) reworded away -- a census
run against a post-I-26 log would silently score zero stray-guard events
forever, the same dead-pattern shape I-19b already fixed once for
`deal_timeouts`. `_clear_strays` (input_controller.py) now prints two
different lines: one re-look after a slot reads unreadable ("re-looking once
before refusing"), and, only if it is STILL unreadable afterwards, a refusal
("still unreadable after"). The refusal is counted under `stray_guard`
alongside the old wording (so old and new logs still agree); the re-look gets
its own `stray_relook` column, so a flicker that recovered on the re-look is
visible instead of invisible.
"""
import argparse
import glob
import json
import re
import sys

COLUMNS = [
    "log", "hands_read", "decisions", "plays_confirmed", "plays_refused",
    "discards_refused", "stall_breaks", "cursor_blind", "nudges",
    "false_cursor", "stray_guard", "stray_relook", "pre_press_guard",
    "inferred_select", "excluded", "confirm_verify_fail",
    "deal_timeouts", "deal_timeouts_with_edge", "reveals_not_logged",
    "unreadable_polls", "stop_reason",
]
_COUNT_COLUMNS = [c for c in COLUMNS if c not in ("log", "stop_reason")]

# "... Threshold 15, biggest delta 6.5: ..." -- both numbers on the same line.
# Only the pre-I-09 combined "no replacement card seen" message needs this
# arithmetic; the two post-I-09 messages below say which case it is directly.
_EDGE_RE = re.compile(r"Threshold (\d+(?:\.\d+)?).*biggest delta (\d+(?:\.\d+)?)")


def census_one(path):
    """Read one run log and return its row of counts."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    row = {k: 0 for k in _COUNT_COLUMNS}
    row["log"] = path
    diagnostics_reason = None
    saw_stopped_early = False
    saw_keyboard_interrupt = False

    in_play = False           # between a "Decision: Playing" and the next Decision
    play_confirmed = False    # a "[reveal] episode" line was seen in that window

    for raw in lines:
        line = raw.rstrip("\n")

        if line.lstrip().startswith("[hand] "):
            row["hands_read"] += 1

        if "Decision:" in line:
            if in_play and play_confirmed:
                row["plays_confirmed"] += 1
            row["decisions"] += 1
            in_play = "Decision: Playing" in line
            play_confirmed = False
            continue

        if in_play and "[reveal] episode" in line:
            play_confirmed = True

        if "play REFUSED" in line:
            row["plays_refused"] += 1
        if "discard NOT CONFIRMED" in line:
            row["discards_refused"] += 1
        if "REFUSED 3x" in line:
            row["stall_breaks"] += 1
        if "cannot see the cursor" in line or "lost the cursor" in line:
            row["cursor_blind"] += 1
        if "nudging off" in line:
            row["nudges"] += 1

        # Refusal shapes the 2026-09-20 census counted by hand
        # (agent_progress/census-20260920/progress.md, I-25/I-21 shapes).
        if "presses — refusing" in line:            # input_controller.py:1047
            row["false_cursor"] += 1
        if "went unreadable DURING this" in line:    # pre-I-26 wording (old logs)
            row["stray_guard"] += 1
        if "still unreadable after" in line:         # I-26's refusal, :1346
            row["stray_guard"] += 1
        if "re-looking once before refusing" in line:  # I-26's re-look, :1322-3
            row["stray_relook"] += 1
        if "position is unreadable, so whether it is" in line:  # :1116
            row["pre_press_guard"] += 1
        if "selected by inference" in line or "inferred" in line:  # :1171
            row["inferred_select"] += 1
        if "x running on hand_index" in line:        # orchestrator.py:7907
            row["excluded"] += 1
        if "confirm_play: FAILED after" in line:     # press_verified give-up
            row["confirm_verify_fail"] += 1

        # Deal-gate timeouts. Pre-I-09 logs carry one combined message whose
        # edge/no-edge split needs the delta-vs-threshold arithmetic; I-09
        # (commit 028e78f) split it into two messages that say which case it
        # is directly, so no arithmetic is needed for those.
        if "no replacement card seen" in line:
            row["deal_timeouts"] += 1
            m = _EDGE_RE.search(line)
            if m and float(m.group(2)) >= float(m.group(1)):
                row["deal_timeouts_with_edge"] += 1
        elif "no motion seen in" in line:
            row["deal_timeouts"] += 1
        elif "the hand never read stable" in line:
            row["deal_timeouts"] += 1
            row["deal_timeouts_with_edge"] += 1

        if "turn not logged" in line.lower():
            row["reveals_not_logged"] += 1
        if "Couldn't read the screen" in line:
            row["unreadable_polls"] += 1

        if "[diagnostics] reason:" in line:
            diagnostics_reason = line.split("reason:", 1)[1].strip()
        if "Stopped early" in line:
            saw_stopped_early = True
        if "KeyboardInterrupt" in line:
            saw_keyboard_interrupt = True

    if in_play and play_confirmed:
        row["plays_confirmed"] += 1

    if diagnostics_reason:
        row["stop_reason"] = diagnostics_reason
    elif saw_stopped_early:
        row["stop_reason"] = "Stopped early"
    elif saw_keyboard_interrupt:
        row["stop_reason"] = "KeyboardInterrupt"
    else:
        row["stop_reason"] = "running"

    return row


def total_row(rows):
    total = {"log": "TOTAL", "stop_reason": "-"}
    for k in _COUNT_COLUMNS:
        total[k] = sum(r[k] for r in rows)
    return total


def print_table(rows):
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in COLUMNS}
    print("  ".join(c.ljust(widths[c]) for c in COLUMNS))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in COLUMNS))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*", help="log files (default: overnight/run_one_match_*.log)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    logs = args.logs or sorted(glob.glob("overnight/run_one_match_*.log"))
    if not logs:
        print("no logs found", file=sys.stderr)
        return 1

    rows = [census_one(p) for p in logs]
    rows.append(total_row(rows))

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
