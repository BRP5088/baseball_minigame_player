# State at 2026-09-07 03:10 — read this first

## Running now (survives this session dying)
`overnight/streak_table.py`: 10-trial streak of the FULL route to `dealer_table`
at `attempts=9`, `start_hint=SPAWN`, `shots=`, 1800s external ceiling, goal
scored by `at_table()` after the aim sweep. Started 02:26. Log:
`overnight/streak_table.log` (per-trial lines `[ n]`), result:
`overnight/streak_table.json` (written after EVERY trial, so a kill loses at
most one), frames: `overnight/streak_table_failframes/`.

**Trial 1 was INVALID at the ceiling** — see CLAUDE.md OPEN-14: the table leg
never saw the prompt (ink 0.0000 across 19 headings, five times), and a
goal-leg retry is a full reset + route re-walk, so 1800s censors attempts=9
there. The user chose to let all ten run (n=1 is noise; trial 1 started at
load 15.5). If more trials come back INVALID the same way, that IS the result:
record it with the frames, do not re-run.

## The overnight plan, in order, AFTER the run completes
0. Score the run: arrived / valid / best streak / failures by class from
   `streak_table.json`; write the result under CLAUDE.md OPEN-14 with n and the
   frames; commit json + log + a contact sheet of the `at_dealer_table` frames.
1. **Census-key migration**: every overnight harness and script reports from
   `failures_by_kind_leg_end` (admissible frames) not `failures_by_kind` (mixed
   with fallback frames). grep first; direct edits; Haiku only if it fans out.
   `overnight/_harness.py` may be edited ONLY once the run is done — trial
   children import it fresh (CLAUDE.md 10.17).
2. **Orphan audit**: functions/files GRAVEYARD.md names as removed or dead,
   cross-referenced against the import graph by AST. Read-only; flag, do not
   delete.
3. **Static QA of the migration** on Haiku: stale keys, unasserted defaults,
   CLAUDE.md rules (10.11 constants, 18 default-arg binding, 10a restores).
4. `BASEBALL_NICE=1 ./run_tests.sh` LAST, certifying 1-3.

Rules in force: no flagship sub-agents for routine work (Haiku); no drafting;
never mutate the checkout while `console_lock` is held; never run mutation
sweeps on the Mac while the console is live (Snoopy_testing.md).

## Tonight's results, committed
- Leg-1 flags cost 8/10 arrivals; reverted (aa773dc, p = 0.000714).
- OPEN-5: attempts=9 9/9 vs attempts=3 5/10 to bar_jukebox (d0b6143, p = 0.0325).
- Reset diagnostic measured the wrong transport; fixed at the root (d3bf513).
- Console interlock (console_lock.py) — keep_awake stands down during runs.
- QA_AUDIT.md: four guards no test can reach, demonstrated by mutants (2251c49).
- CLAUDE.md reconciled: closed tickets flushed, rules 10.16b/18/19 (bf54429…6b80ed0).
