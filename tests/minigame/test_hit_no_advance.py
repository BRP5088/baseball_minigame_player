"""A WINNING AT-BAT CAN ADVANCE NOBODY, and the record must be able to say so.

Seen live 2026-09-17 and captured in test_fixtures/blocked_runner/: our
Donny Mekesz 5/3 + POWER SWING +1 = 6 beat their 5, margin +1, a HIT by the
game's own rule -- and Rube Sharp (8/1) did not leave first, the score stayed
2-0, and the batter stood on HOME PLATE. Two players cannot occupy the same
base, so pinning the runner pins the batter behind him.

classify_outcome returned plain "hit": true, and indistinguishable from a
bases-clearing one.

THE GUARD THAT MATTERS IS THE ABSTENTION. `rose` is False both when nothing
moved AND when the runner reader could not read the bases, and collapsing those
into one label would invent a finding out of a failed read (10.1). So
hit_no_advance is claimed ONLY when both counts were actually taken.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


# THE LIVE CASE. margin +1, no runs, one runner before and one after.
out, basis = o.classify_outcome(1, 0, 1, 1)
check((out, basis) == ("hit_no_advance", "margin"),
      f"the blocked hit is named hit_no_advance -> {out}/{basis}")

# AN ORDINARY HIT still reads as one: the batter reached base, so the count rose.
out, basis = o.classify_outcome(1, 0, 1, 2)
check((out, basis) == ("hit", "margin"), f"a hit that advances is still 'hit' -> {out}/{basis}")

# A hit that drove a run in: the count did not rise but RUNS did.
out, basis = o.classify_outcome(1, 1, 1, 1)
check((out, basis) == ("hit", "margin"),
      f"a hit that scores is still 'hit' even with the count unchanged -> {out}/{basis}")

# THE ABSTENTION. Bases unread -> we do NOT know that nobody moved.
out, basis = o.classify_outcome(1, 0, None, None)
check((out, basis) == ("hit", "margin"),
      f"with the bases UNREAD it stays 'hit', never hit_no_advance -> {out}/{basis}")
out, basis = o.classify_outcome(1, 0, 1, None)
check((out, basis) == ("hit", "margin"),
      f"...and a half-read count is also not evidence -> {out}/{basis}")

# CONTROLS -- the other branches are untouched.
check(o.classify_outcome(3, 1, 0, 0) == ("home_run", "margin"), "a 3+ margin is still a home run")
check(o.classify_outcome(-2, 0, 1, 1) == ("out", "margin"), "a losing margin is still an out")
check(o.classify_outcome(0, 0, 1, 1) == ("out", "tie"), "a tie that moved nobody is still an out")
check(o.classify_outcome(None, 1, 0, 1) == ("scored", "delta"), "no margin still falls back to the delta")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
