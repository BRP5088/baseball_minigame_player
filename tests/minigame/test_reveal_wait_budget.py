"""The reveal wait must cover every reveal that comes, and nothing more.

WHY THIS FILE EXISTS. REVEAL_MAX_WAIT was 75 s, chosen from the TURN PERIOD distribution --
the wrong quantity. What it actually bounds is how long AFTER THE PLAY a reveal appears.
Measured over every log on disk (4 logs, 72 real reveals): min 0.90, p50 3.80, p95 5.80,
p99 7.90, MAX 7.90. The other population never arrives at any budget: 67 of 139 plays
produce no reveal at all, and each one paid the full wait.

On the 2026-09-09 cycle that was 1,650 s of 3,037 -- 54% OF THE RUN -- against 457 s (15%)
for every paid vision call put together. The wait for a thing that is not coming was the
single largest item on the clock, and it did not look like one because the run was busy.

The checks below pin the two properties that matter and NOT the constant against itself
(CLAUDE.md 10.11): the budget must clear the slowest reveal ever seen, with margin, and it
must stay far under the old value, or the saving is gone.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# The measured maximum over 72 pooled reveals. A literal, so raising the constant cannot
# raise the bar with it.
SLOWEST_REVEAL_SEEN = 7.9
OLD_BUDGET = 75.0

w = orchestrator.REVEAL_MAX_WAIT
check("the budget covers the slowest reveal ever measured", w > SLOWEST_REVEAL_SEEN,
      f"{w}s against {SLOWEST_REVEAL_SEEN}s")
check("with at least 1.5x margin, because 72 samples is not the world",
      w >= SLOWEST_REVEAL_SEEN * 1.5, f"{w}s, margin {w / SLOWEST_REVEAL_SEEN:.2f}x")
# The saving is the whole point: 67 of 139 plays wait the FULL budget, so the budget IS the
# cost. A value near the old one gives the time back.
check("and it is well under the old 75s, or the saving is gone", w <= OLD_BUDGET / 3.0,
      f"{w}s against {OLD_BUDGET}s")
check("the watcher's episode timeout tracks the same budget",
      orchestrator.REVEAL_EPISODE_TIMEOUT == w,
      f"{orchestrator.REVEAL_EPISODE_TIMEOUT} vs {w}")

# A turn with no reveal must FAIL rather than hang: the caller treats a missing reveal as
# "this turn is not logged", which is correct and cheap. What is not acceptable is waiting.
check("the poll's default is the budget, not a hardcoded number",
      orchestrator.wait_for_reveal_cards.__defaults__[0] == w,
      str(orchestrator.wait_for_reveal_cards.__defaults__))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
