# Heuristic testing log

Results from `simulate.py` (heuristic-vs-heuristic, offline, using the
confirmed rule: a hit needs power > opponent's power; beating it by 3+
is a home run that clears every runner + the batter). Two important
caveats that apply to every result below:

- **Noise floor**: running the *same* strategy against itself at
  n=400-600 matches still shows a ~2-6 percentage-point win-rate spread
  from pure randomness. Any gap smaller than that isn't a real finding.
- **Simulation blind spot**: `resolve()` only compares power. It has no
  model of what the fielding/speed secondary stat actually does, since
  that's never been confirmed live — only the power-margin rule has.
  Any result that looks better *by dropping something that reacts to
  secondary stat* is not real evidence that thing is bad; it's just
  evidence the simulation can't see its effect. Treat those results as
  "the simulation is blind here," not "this logic is wrong."
- **Pitcher-redraw modeling — FIXED 2026-08-23**: `redraw_fn` in
  `simulate_batting_half` used to only ever get called on the batting
  hand — the pitching side's drawn hand never got a redraw check, even
  though the real game lets `should_redraw()` fire on either phase
  (`orchestrator.py`'s `play_one_turn` calls it regardless of phase).
  Caught in QA while checking the batters_used/target_score variants
  below. Fixed by adding `defender_redraw_fn`/`defender_redraws_left` so
  the defending side gets a real redraw check too. Re-ran finding #1
  after the fix — numbers held (78.8% vs. no-tactics, consistent with
  the pre-fix 78.8%). §5's variants below were re-tested against the
  fixed simulator; their write-ups reflect the corrected numbers.

## 1. Always attach an available boost (APPLIED)

**Before**: `best_batting_play`/`best_pitching_play` held tactics cards
back situationally ("power already solid, no runners on — bank it for a
bigger payoff turn").

**Test**: current heuristic vs. a naive baseline that always plays
highest power with no tactics, vs. a naive baseline that always attaches
whatever boost is available.

**Result** (500 matches, seed 42):
| Matchup | Win rate |
|---|---|
| current (old, situational) vs. no-tactics | 72.2% |
| current (old, situational) vs. always-boost | 11.2% |
| no-tactics vs. always-boost | 3.0% |

The situational logic was losing badly to a strategy that just always
boosts. Makes sense given the confirmed rule: extra power is never
wasted (only raises hit odds and home-run-margin odds), and hands
redraw fresh each round rather than depleting a shared pool worth
conserving.

**Applied**: rewrote both functions to always attach the best available
swing/pitch boost. Re-tested after the fix (and after fixing the
`power_bonus` bug below): 78.6% vs. no-tactics, up from the old logic's
72.2% — real, validated improvement.

**Robustness check**: `TACTICS_FRACTION` (how often a hand slot is a
tactics vs. player card) is a modeling guess, currently 0.5. Re-ran
current vs. no-tactics at 0.2/0.35/0.65: 47.2%/67.2%/83.6% win rate
(scaling up as boosts get more available, as expected). Always-boost
wins at every value tested — not an artifact of the 0.5 assumption.

## 2. Fielding-priority pitcher selection — **CHANGED 2026-08-25**

> **This section previously said "NOT CHANGED ... Left as-is" and argued
> against the very change that has now shipped.** It is rewritten rather than
> deleted, because the reasoning it contains was wrong in an instructive way.

**What the code does now.** `best_pitching_play` maximises power. With runners
on, fielding breaks a tie and may buy at most `FIELDING_POWER_BUDGET` (=1)
power — never more. Tactics: a pitch boost is preferred over a fielding boost,
because only swing/pitch boosts add power at all (`power_bonus`, simulate.py).

**What it did before.** `max(key=(secondary, power))` with secondary as the
PRIMARY key, so a single fielding pip outranked any amount of pitch focus — a
4/1 was played over a 9/0.

**Why the old reasoning failed.** The argument below was that `resolve()`
doesn't model fielding, so a simulation preferring power is measuring its own
blind spot rather than the game. That is a fair objection to the EXPERIMENT
that was run — which only ever tested *removing* fielding priority entirely.
It is not a licence for the code, because:

* The project's ONE confirmed rule is the power margin (§1 of this file). The
  fielding effect is still unconfirmed — `analyze_match_log.py` read **p=0.192
  on 19 usable rows** on 2026-08-26, i.e. cannot conclude. The old code
  sacrificed the *confirmed* mechanism to chase the *unconfirmed* one.
* An unmodelled effect argues for a BOUNDED hedge, not for unbounded priority.
  Measured, the old rule gave up a stronger pitcher on 46.9-73.6% of runner
  turns (the range spans two hand models), a mean of 2.76-3.30 power — on
  exactly the turns where conceding a 3+ margin costs most.
* Head-to-head, 800 matches, corrected vs original: **53.9% to 23.9%**.

`FIELDING_POWER_BUDGET` keeps the hedge the old argument was really asking for,
at a price that is capped and known. Set it to 0 for pure power-first once the
fielding question is settled either way.

**Still open.** `match_log.jsonl` exists to answer whether `secondary` matters
at all. Current estimate: about **156 more logged turns (~8 matches)** would
settle it at the observed effect size — not the "150-200 turns" this file used
to cite for a differently-framed question. Run `python3 analyze_match_log.py`
for the live figure rather than trusting any number written here.

## 3. Redraw (discard) power threshold (NOT CHANGED — no clear winner)

**Test**: current heuristic's redraw threshold (`should_redraw`: redraw
if best hand power ≤4) vs. thresholds 3, 5, 6, and never-redraw. 400
matches per comparison, seed 42.

**Result**: every alternative lost to the current threshold=4 by
4-10 points, but the identical-strategy control (threshold=4 vs itself)
already showed a ~2-6 point spread from noise alone. Only threshold=6
and never-redraw showed a gap large enough to look like more than pure
noise (10.5 and losing consistently); 3 and 5 were within the noise
band. No alternative clearly beat 4. Left unchanged.

## 4. Ban strategy: weakest vs. random vs. none (CONFIRMED, no change needed)

**Test**: `choose_bans()` bans the 3 lowest-power cards from your
collection. Tested that against banning 3 random cards, and against not
banning at all, using the real 33-card collection scanned live from
this save on 2026-08-23.

**Result**:
- ban-weakest vs. no-bans (600 matches): 44.7% vs 32.5% — banning
  clearly helps.
- ban-weakest vs. ban-random, first run (600 matches): 37.5% vs 41.7% —
  looked like random won, which contradicts the math (removing the 3
  lowest values from a set can only raise or match the average vs.
  removing 3 random ones).
- Re-ran at 1000 matches across 3 different seeds to check: ban-weakest
  won all three (41.3/38.9, 45.1/35.2, 43.2/35.8). The first result was
  noise from an unlucky seed + smaller sample.

**Lesson**: don't trust a single 500-600-match run, even one that looks
clean — rerun with a different seed before believing a surprising
result. `choose_bans()`'s existing weakest-first logic is confirmed
correct; no change needed.

## Bug found and fixed along the way

`simulate.py`'s `resolve()` power calculation originally added *any*
tactics card's bonus to power, including Speed Boost — which should
only affect baserunning, not swing power. Added `power_bonus()` to only
apply the bonus for `SWING_BOOST`/`PITCH_BOOST`. Re-ran finding #1 after
the fix; it still held (78.6% vs. no-tactics, consistent with the
pre-fix number).
