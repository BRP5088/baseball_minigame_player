"""Every arm in tools/ab_engine_i15_16_17.py (I-15/I-16/I-17) must have a control
setting that reproduces the shipped baseline EXACTLY -- CLAUDE.md sec 4's own lesson,
from the tie_w experiment's first (wrong) version: a knob whose tie_w=0 control did not
reproduce the shipped number was silently measuring something other than what it claimed.

This is an EXACT equality check on a small n, not a statistical one -- determinism (same
seed, same RNG call sequence) is what makes a small n sufficient here. The 12,000-half x
3-seed runs that produced the reported findings do not belong in a unit suite (see
test_tie_risk_is_closed.py's own docstring for the same rule).
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import simulate as sim
import tools.ab_engine_i15_16_17 as ab_engine
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
# I-47: a fallback honestly reports the LIVE log's own n_used_for_distribution, which
# can legitimately be 0 (this checkout's own match_log.jsonl has 0 qualifying rows as of
# this writing) -- so "nonzero" is only required when NOT falling back. On fallback, the
# pinned snapshot's own n must still be nonzero, under its own separate key.
check(meta["fallback"] or meta["n_used_for_distribution"] > 0,
      f"log-derived distribution was built from a nonzero number of qualifying rows, or "
      f"is honestly reporting a fallback with a live n_used_for_distribution of 0 "
      f"(fallback={meta['fallback']}, n_used_for_distribution={meta['n_used_for_distribution']}, "
      f"of {meta['rows_with_outcome_basis_or_margin']} with a local reveal read, "
      f"{meta['rows_excluded_no_local_reveal_read']} excluded)")
check(not meta["fallback"] or meta["n_used_for_distribution_pinned"] > 0,
      f"fallback meta carries the pinned snapshot's own nonzero n under a separate key "
      f"(got n_used_for_distribution_pinned={meta.get('n_used_for_distribution_pinned')!r})")
# Base player power runs 4-9 (CLAUDE.md sec 4); a swing/pitch tactics bonus adds at most
# +2, so effective power can reach 11. Whichever branch load_log_distribution() took
# (computed from this checkout's own qualifying rows, or the pinned fallback), its keys
# must stay inside that range.
check(all(4 <= p <= 11 for p, _ in log_dist),
      f"log-derived distribution keys are plausible effective powers 4-11 "
      f"(got {[p for p, _ in log_dist]})")

# F3 (QA7): the checks above call load_log_distribution() with whatever this checkout's
# OWN match_log.jsonl happens to contain, which -- as of this writing -- already takes
# the fallback branch (0 batting rows with opp_power). But nothing FORCES that branch to
# run, so a checkout with qualifying live rows would silently skip covering it. Drive it
# on purpose with a synthetic log (2 pitching rows, 1 batting row with opp_power null --
# 3 "qualifying" rows, 0 usable), through load_log_distribution() ITSELF rather than
# re-reading the pinned JSON directly (that only checks the pin's own bytes, not the
# fallback branch's own code -- a mutant that returns the pinned probs with STRING keys
# instead of int would pass every check above and still corrupt every (power, prob) pair
# a caller relies on being int-keyed).
_synthetic_log = (
    '{"phase": "pitching", "outcome_basis": "x", "opp_power": 5}\n'
    '{"phase": "pitching", "margin": 2, "opp_power": 6}\n'
    '{"phase": "batting", "outcome_basis": "y", "opp_power": null}\n'
)
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as _tf:
    _tf.write(_synthetic_log)
    _synthetic_path = _tf.name
_real_log_path = ab_engine._MATCH_LOG_PATH
try:
    ab_engine._MATCH_LOG_PATH = _synthetic_path
    fb_dist, fb_meta = ab_engine.load_log_distribution()
finally:
    ab_engine._MATCH_LOG_PATH = _real_log_path
    os.remove(_synthetic_path)

check(fb_meta["fallback"] is True,
      f"synthetic all-pitching/null-opp_power log (3 qualifying rows, 0 usable) drives "
      f"the REAL fallback branch: meta['fallback'] is True (got {fb_meta['fallback']!r})")
check(fb_meta["n_used_for_distribution"] == 0,
      f"fallback honestly reports THIS (synthetic) log's own n_used_for_distribution as "
      f"0, not the pinned snapshot's (got {fb_meta['n_used_for_distribution']})")
check(all(isinstance(p, int) for p, _ in fb_dist),
      f"fallback distribution keys are ints, not strings "
      f"(got {[type(p).__name__ for p, _ in fb_dist]})")
check(all(4 <= p <= 11 for p, _ in fb_dist),
      f"fallback distribution keys are plausible effective powers 4-11 "
      f"(got {[p for p, _ in fb_dist]})")
check(abs(sum(p for _, p in fb_dist) - 1.0) < 1e-9,
      f"fallback distribution sums to 1.0 (got {sum(p for _, p in fb_dist):.6f})")

# match_log.jsonl GROWS as matches are played (CLAUDE.md sec 2/10.16c's lesson applied to
# a data file), so asserting the live derivation bit-matches a dated snapshot is false by
# construction the moment a match is logged -- main's own tracked log already diverges
# from a clean checkout's 369 rows. What the pin is actually FOR is the fallback branch of
# load_log_distribution(): the exact bytes it returns verbatim when the live log has zero
# qualifying rows. So the pin itself -- not equality with today's log -- is what must stay
# a valid probability distribution. Loading it here keeps the fails-loudly behaviour: a
# missing or unparsable pinned file raises (both here and inside load_log_distribution()'s
# own fallback) instead of silently passing.
_PINNED_PATH = os.path.join(_ROOT, "tools", "ab_data", "opp_pitcher_dist_20260921.json")
with open(_PINNED_PATH) as _f:
    _pinned = json.load(_f)
_pinned_probs = _pinned["effective_power_probs"]
check(abs(sum(_pinned_probs.values()) - 1.0) < 1e-9,
      f"pinned snapshot {os.path.relpath(_PINNED_PATH, _ROOT)} probabilities sum to 1.0 "
      f"(got {sum(_pinned_probs.values()):.6f})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
