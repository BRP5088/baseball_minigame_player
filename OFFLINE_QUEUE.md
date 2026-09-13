# Offline queue — overnight 2026-09-13

Rules in force: paid vision model OFF. No console action. Nothing timing-sensitive is in
flight (the console is parked on a ban screen), so per CLAUDE.md section 2's mechanism test
offline CPU work and mutation testing are permitted.

## Done tonight

- [x] `ban_grid` had no tests. Three named fixtures, truth hand-read off a ruler. The
      control ("must not answer on a frame with no grid") FAILED first run and exposed a
      real hole. 7 mutants, 7 caught. `2b2bc1f` / `053d5c4` / this file's commit.
- [x] Simulator rules pinned: two halves, five rounds, hand persistence, a lost tie is an
      out. 6 mutants, 6 caught — one SURVIVED first time because a speed-1 phantom runner
      cannot score in five rounds; fixed with a speed-3 batter and a matching control.
- [x] Verified affected-test selection is correct on all four cases that matter
      (module -> 1 test, orchestrator -> 130, a FIXTURE -> all 183, a new test -> selected).

## Doing

- [ ] Preflight: everything green and ready to test on waking.
- [ ] Fix any test issues found on the way.
- [ ] Docstring rot: `decision_engine` + `test_power_speed_blend` describe a superseded
      power/speed model; `best_batting_play` describes the pre-99/1 rule.
- [ ] `GameState.opp_score` is hardcoded to 0 on the batting side.
- [ ] Live viewer upgrades.
- [ ] CLAUDE.md: roles, ban-grid geometry, locked-vs-owned, the tactics roster.

## Parked, with the reason (not forgotten, blocked)

- **Reading POWER off ban cards.** The hand digit bank does not transfer: argmax correct on
  only 3 of 7, and everything scoring under 0.5 is wrong. Lowering the gate manufactures
  wrong digits. A ban-specific bank needs labels INDEPENDENT of the roster (else it is
  circular for auditing the roster) — i.e. a human reading a sheet. Prepared for morning.
- **Two git worktrees** hold pre-lockout `orchestrator.py` with 5 unguarded paid call sites
  reading the real key. Removal is destructive; needs the user's yes.
- **Brian Coker (8/1), Zachary Lee (6/2)** — the last 2 of 33 untyped. Neither appears on
  any ban grid held. Needs a ban screen scrolled to where they live.
