# State at 2026-09-06 23:25 — read this first

## Running right now (both survive this session dying)
- `overnight/measure_streak.py` -> `overnight/streak_postleg1.log`, result to
  `overnight/streak.json`, leg-end frames to `overnight/streak_failframes/`.
  10 trials of `portrait_room -> bar_pool_room -> bar_jukebox` from a reset
  spawn. ~56 min. **Baseline to beat: 6/10 arrived, best streak 3, 338s/trial
  (CLAUDE.md 8a) — measured BEFORE the leg-1 flags existed.**
- The offline suite under `BASEBALL_NICE=1`, concurrently. That is now known
  safe: 30,787 sleep-overrun samples during a real suite run, max 9.73ms, none
  over 50ms (CLAUDE.md 10.13a).

**If the streak run was killed**, the per-trial lines are still in
`overnight/streak_postleg1.log` even though `streak.json` is only written at the
end. Re-score from the log rather than re-running.

## The result that matters today (committed, aa773dc)
Leg 1's speed+merge flags cost 8 of 10 arrivals.

    leg 1 as recorded           10/10 arrived  median  51.6s
    leg 1 at speed 3.0, merged   2/10 arrived  median 323.7s
    Fisher p = 0.000714, interleaved, zero invalid

Both flags reverted. This explains the 10/10 -> 0/3 collapse that CLAUDE.md had
blamed on the console power cycle. The commit that RECORDED the 10/10 enabled
the first flag in the same breath.

## Next, in order
1. Read the streak result. If arrival moved above 6/10, leg 1 was costing the
   route and the remaining gap is the jukebox leg.
2. **OPEN-5** — `attempts=9` vs `3`. `overnight/ab_attempts.py` is prepared at
   TRIALS=10, TIMEOUT=900. The arithmetic is the whole argument: at the measured
   per-attempt 0.40 on the worst leg, attempts=3 gives P(25 consecutive) 1.2e-08
   and attempts=9 gives 0.47. Retry depth is the only lever with that leverage.
3. **OPEN-14** — the restored jukebox leg, still unmeasured. Unblocked now that
   the start node is 10/10 again.

## Do not redo
- The 3D map and the floor-plan mosaic are both dead. GRAVEYARD has the flat-grey
  control that killed the second one (seen-cell IoU 1.000 from a single constant
  value). Run that control before believing any accumulate-into-a-canvas result.
- `keep_awake` must not nudge during a run. This is now structural, not a note:
  `console_lock.py`, checked in `_harness.run_trial` and in
  `measure_streak.py`. Verified live at 23:23:48 ("a run is active — standing
  down"). Nothing needs remembering.
