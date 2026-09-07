# State at 2026-09-07 07:55 — read this first

## Running now
`BASEBALL_NICE=1 ./run_tests.sh` — the certification re-run of the whole
suite, log `overnight/suite_final_certify.log` (last line `--- ...`, then
`exit N`). Started 07:52, ~22 min under taskpolicy. **Nothing is on the
console**; `console_lock.holder()` was None when it started.

Why a re-run: the first certification (`overnight/suite_overnight_final.log`,
07:27) was 142/143. The one failure, `test_map_admit`, was NOT a weakened
gate: the test globbed `overnight/failframes/*.jpg` as its failure population
and the streak run had appended 165 leg-end frames there. Fixed by naming the
four fixture frames (7b8f918); passes alone in 52.9s. CLAUDE.md §2 now carries
the rule. If the re-run is anything but all-PASS, the failing file is the
first thing to read — do not re-run it hoping.

## The overnight plan — status
0. **OPEN-14 scored and recorded** (38a17af): 3 valid of 10, 7 censored at the
   1800s ceiling, 2 "arrived" of which ONE was `identify()` naming
   `dealer_table` — a pose, which §7 says it may never confirm. Frames +
   contact sheets committed.
1. **Census migration done** (f9b9c56, ad13c6e): every harness reports
   `failures_by_kind_leg_end` split by provenance via `_harness.census_kinds`
   / `report_kinds`; foreign and blank rows are named, not dropped.
2. **Orphan audit done** (f0de600): 13 dead routing-generation modules and the
   floor-map cluster, flagged in QA_AUDIT.md, nothing deleted.
3. **Static QA on Haiku done**: one by-construction check removed from my own
   test, `report_kinds` made loud on foreign rows (ad13c6e).
4. **Suite**: 142/143 → cause fixed → re-run in flight (above).

## First decision for you (not done unasked)
`graph_walk.locate()` falls through from `at_table()` to `identify()`, so the
GOAL can be "confirmed" by the localiser. Proposed: for `GOAL`, `locate()`
believes only `at_table()`; plus a test that pins it. One guard, no movement.

## Rules in force
No flagship sub-agents for routine work (Haiku); no drafting; never mutate the
checkout while `console_lock` is held (10.17/10.21); no mutation sweeps on the
Mac while the console is live (Snoopy_testing.md); save patch scripts before
running them (10.19).

## Tonight's results, committed
- Leg-1 flags cost 8/10 arrivals; reverted (aa773dc, p = 0.000714).
- OPEN-5: attempts=9 9/9 vs attempts=3 5/10 to bar_jukebox (d0b6143, p = 0.0325).
- OPEN-14: 1 real arrival of 3 valid; 7/10 censored; the `locate()` hole (38a17af).
- Reset diagnostic measured the wrong transport; fixed at the root (d3bf513).
- Console interlock (`console_lock.py`); keep_awake stands down during runs.
- QA_AUDIT.md: four guards no test can reach, by mutant (2251c49); orphans (f0de600).
- A test globbed a live run's sink and broke overnight (7b8f918).
