# Offline queue — overnight 2026-09-13

Rules in force: paid vision model OFF. No console action taken. The PS5 left the game of its
own accord around 04:30 (see HANDOFF_NOW.md), so nothing is in flight at all.

## Done

- [x] **`ban_grid` had no tests.** Three named fixtures, truth hand-read off a ruler. The
      control ("must not answer on a frame with no grid") FAILED on first run and exposed a
      real hole — a flat frame got a confident fit. 7 mutants, 7 caught.
- [x] **Simulator rules pinned** — two halves, five rounds, hand persistence, a lost tie is
      an out. 6 mutants, 6 caught. One SURVIVED first time: at speed 1 a phantom runner
      cannot score in five rounds, so the check passed while the bug was live. Fixed with a
      speed-3 batter and a matching control.
- [x] **preflight's $50 guard could not fire the way preflight is run.** It read one
      progress file and defaulted to the wrong one, so bare `preflight.py` said READY while
      `progress_testing.json` held `match_in_progress`. Now checks every progress file via
      `orchestrator.open_match_files`. 4 mutants, 4 caught.
- [x] **A test that printed "overlay screens rejected" without ever looking at one** — its
      negative half looped over two `/tmp` paths nothing creates. Five committed frames now,
      mandatory, at three widths each. 2 mutants, 2 caught.
- [x] **The undefined-name scanner deferred to a test that did not exist** (`except
      SyntaxError: return []  # a syntax error is a different test`). Five broken TRACKED
      files were invisible. Test written; the exemption list can only shrink. 2 mutants.
- [x] **`opp_score` was hardcoded to 0** in the batting state with the real number two
      arguments away. Inert today, which is why it survived. 2 mutants, 2 caught.
- [x] **Docstring rot** in `best_batting_play` — it described power-only sorting and an
      "UNEVALUATED" speed alternative, both superseded.
- [x] **`verify_button_bits.py`** hardcoded the author's home directory, and it drives the
      console.
- [x] **CLAUDE.md**: card roles, the ban-grid geometry, locked-vs-owned, the tactics roster,
      the preflight finding, and three approaches that DO NOT work so they are not retried.
- [x] **Viewer**: ban-grid boxes, per-cell name + type + locked, self-reload on source
      change, `--once` for debugging, power/shield boxes, and `s` to dump a labelling sheet.
- [x] Verified affected-test selection is correct on all four cases that matter.

## Parked, with the reason

- **Reading POWER off ban cards.** The hand digit bank does not transfer: argmax correct on
  3 of 7, everything under 0.5 wrong. A ban-specific bank needs labels INDEPENDENT of the
  roster, or the audit is circular — i.e. a human. The viewer's `s` key now makes that one
  keypress.
- **Two git worktrees** hold pre-lockout `orchestrator.py` with 5 unguarded paid call sites
  reading the real key. Removal is destructive; needs a yes.
- **Brian Coker (8/1), Zachary Lee (6/2)** — the last 2 of 33 untyped.
- **Five broken draft files** (blank lines stripped, statements joined). Recorded and
  guarded; not repaired at a guess, because one is a pending patch.
- **`FIELDING_SUBTRACT_PER_POINT`** needs the console.
- **"Does a speed boost persist on base"** needs the console, and is now PRICED: +0.046
  runs/half, 4.2 sigma. Real, but it cannot flip the engine's preference (a speed boost
  totals 0.177 either way against a swing boost's 0.614). One at-bat settles it; do not
  plan around it.
