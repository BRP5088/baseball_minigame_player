# What 72 logged turns say about the secondary stat

Analysed 2026-08-27 against `match_log.jsonl` (72 turns: 40 batting, 32
pitching). No synthetic markers present; this is real logged play.

`orchestrator.py` carries this instrumentation for exactly one purpose — to
find out whether the secondary stat (speed on a batter, fielding on a pitcher)
affects outcomes — and its removal plan sets the bar at ~150-200 turns.

## Answer: not yet. Keep logging. Do not change strategy.

## What happened, in order

Batting alone looked like a strong result: 62% good outcomes when our secondary
was at or above the opponent's, 18% when below. A 44-point gap, permutation
p = 0.015.

It did not survive. Two things killed it:

**1. It reverses on held-out data.** Pitching was not used to form the
hypothesis. There the same comparison runs the other way: 36% outs when our
secondary was ahead, 71% when behind (p = 0.99 in the hypothesised direction).

That reversal is not a paradox — it is the giveaway. `secondary` means
different things on different cards, speed on a batter and fielding on a
pitcher, so "our secondary minus theirs" silently flips meaning between phases.
Restated in ONE frame (batter_speed - pitcher_fielding), all 72 turns give:

    batter behind   4/15 = 27% batter success
    batter tied    11/15 = 73%
    batter ahead   18/42 = 43%

Non-monotonic. "Tied" beating "ahead" is not a mechanic anyone would design.

**2. Power confounds it.** That winning "tied" group carries a mean batter
power edge of +1.07, against +0.27 and +0.31 for the other two. Power is the
known driver, and it is not balanced across the groups being compared.

Stratifying by power edge, batter success rate:

    power edge |   sec behind     sec tied    sec ahead
           <=0 |   3/9 =  33%   5/9 =  56%  6/23 =  26%
        +1..+2 |   0/3 =   0%   2/2 = 100%  4/10 =  40%
          >=+3 |   1/3 =  33%   4/4 = 100%   8/9 =  89%

Power separates cleanly down the rows. Secondary does not separate across them,
and the cells carrying the strongest claims hold 2, 3 and 4 samples.

## What IS established

Power drives outcomes. That much is unambiguous across every slice.

## Method note

I tested several predicates on the batting half before one came back
significant, which inflates a p-value on its own. The held-out pitching half is
what settles it, and it went the wrong way. A p of 0.015 found that way is not
evidence.

## Consequences

* **Do not strip the matchup logging.** Its removal plan is not met — 72 turns,
  not 150-200 — and the question it exists to answer is still open.
* **Do not weight secondary in card selection.** There is no support for it.
* A separate data-quality problem: 22 of 40 batting turns logged our card as
  the generic type name ("Batter"/"Pitcher") rather than a real name. Card
  identity is therefore unusable for analysis, though power/secondary are fine.
