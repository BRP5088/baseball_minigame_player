"""Every arm in tools/ab_engine_i15_16_17.py (I-15/I-16/I-17) must have a control
setting that reproduces the shipped baseline EXACTLY -- CLAUDE.md sec 4's own lesson,
from the tie_w experiment's first (wrong) version: a knob whose tie_w=0 control did not
reproduce the shipped number was silently measuring something other than what it claimed.

This is an EXACT equality check on a small n, not a statistical one -- determinism (same
seed, same RNG call sequence) is what makes a small n sufficient here. The 12,000-half x
3-seed runs that produced the reported findings do not belong in a unit suite (see
test_tie_risk_is_closed.py's own docstring for the same rule).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import simulate as sim
from tools.ab_engine_i15_16_17 import (
    run_arm, sequenced_batting_play, deck_aware_redraw, make_expected_runs_play,
    load_log_distribution,
)

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


N = 300
SEEDS = (1,)

baseline = run_arm(sim.CURRENT, sim.ALWAYS_BOOST, n_matches=N, seeds=SEEDS)

# I-15 control: hold=False must be bit-identical to CURRENT's own scorer.
i15_control = run_arm(
    {"batting": sequenced_batting_play(False), "pitching": sim.best_pitching_play},
    sim.ALWAYS_BOOST, n_matches=N, seeds=SEEDS)
check(i15_control["scores"] == baseline["scores"],
      f"I-15 control (hold=False) reproduces the baseline's per-match scores exactly "
      f"({i15_control['runs_per_half']:.4f} vs {baseline['runs_per_half']:.4f})")

# CONTROL on the control: hold=True must actually differ from hold=False on SOME run,
# or the arm is vacuous (the same shape test_tie_risk_is_closed.py's own docstring warns
# about -- a knob that never changes anything is not measuring what its name says).
i15_arm = run_arm(
    {"batting": sequenced_batting_play(True), "pitching": sim.best_pitching_play},
    sim.ALWAYS_BOOST, n_matches=N, seeds=SEEDS)
check(i15_arm["scores"] != baseline["scores"],
      "CONTROL: I-15 arm (hold=True) actually changes SOME outcome vs the control "
      "(a no-op arm would pass the reproduction check for a vacuous reason)")

# I-16 control: no "redraw" key in the team dict must be bit-identical to the baseline
# (defaults to should_redraw for both phases, matching the shipped fixed-6 threshold).
i16_control = run_arm(
    {"batting": sim.best_batting_play, "pitching": sim.best_pitching_play},
    sim.ALWAYS_BOOST, n_matches=N, seeds=SEEDS)
check(i16_control["scores"] == baseline["scores"],
      f"I-16 control (no redraw override) reproduces the baseline's per-match scores "
      f"exactly ({i16_control['runs_per_half']:.4f} vs {baseline['runs_per_half']:.4f})")

i16_arm = run_arm(
    {"batting": sim.best_batting_play, "pitching": sim.best_pitching_play,
     "redraw": deck_aware_redraw(0.5)},
    sim.ALWAYS_BOOST, n_matches=N, seeds=SEEDS)
check(i16_arm["scores"] != baseline["scores"],
      "CONTROL: I-16 arm (P(improve) > 0.5) actually changes SOME outcome vs the control")

# I-17 control: the pool-derived distribution fed through the refactored, parametrised
# scorer must reproduce the SHIPPED expected_runs_play (which caches the same
# pool-derived distribution internally) exactly.
pool_dist = sim._pitcher_power_distribution(sim.CARD_POOL)
shipped = run_arm(sim.EXPECTED_RUNS, sim.CURRENT, n_matches=N, seeds=SEEDS)
i17_control = run_arm(
    {"batting": make_expected_runs_play(pool_dist), "pitching": sim.best_pitching_play},
    sim.CURRENT, n_matches=N, seeds=SEEDS)
check(i17_control["scores"] == shipped["scores"],
      f"I-17 control (pool dist through the refactored fn) reproduces the shipped "
      f"expected_runs_play exactly ({i17_control['runs_per_half']:.4f} vs "
      f"{shipped['runs_per_half']:.4f})")

# The log-based distribution must at least parse and be a valid probability distribution
# over plausible powers, whatever it does to the decision (measured separately: zero
# decisions changed at n=4000, see agent_progress/issues/I-15-16-17/progress.md).
log_dist, meta = load_log_distribution()
check(abs(sum(p for _, p in log_dist) - 1.0) < 1e-9,
      f"log-derived opponent-pitcher distribution sums to 1.0 (got "
      f"{sum(p for _, p in log_dist):.6f})")
check(meta["n_used_for_distribution"] > 0,
      f"log-derived distribution was built from a nonzero number of qualifying rows "
      f"({meta['n_used_for_distribution']} of {meta['rows_with_outcome_basis_or_margin']} "
      f"with a local reveal read, {meta['rows_excluded_no_local_reveal_read']} excluded)")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
