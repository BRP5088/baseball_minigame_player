# HANDOFF_NOW — close of 2026-09-23

## 1. STATE RIGHT NOW

- main HEAD `c6446cf`. It holds I-62, I-63, I-64, I-65 and I-65b, merged today (2026-09-23).
- Console unreachable: chiaki shows "ready" but no stream opens. The user will fix it in person.
- Nothing is running. The paid model is OFF. Never save the game.

## 2. MORNING, IN ORDER

1. Wake the Mac displays, then re-run the full suite. Last night 3 files failed only because the displays were asleep (`_MSS.monitors[1]`): `test_decisions`, `test_orchestrator_diagnostics`, `test_should_redraw_incomplete`.
2. The user restores the console connection.
3. Run live cycles 27+ on `c6446cf`. Streak scoring uses the user's rule, below.
4. From the new `deal_timing` rows, read `first_complete_at` and the "stable_bound" release counts to replace the PROVISIONAL `READABLE_HAND_BOUND` = 8.0 and to check the match-start gate.
5. Run a fresh labelling round with the artifact on the new decision frames. Acceptance: 0 "animating".

## 3. RESULTS / STREAK

- Cycles 20-26: 27/28 clean by the old rule; record 126W 18L 14D.
- The user's rule, 2026-09-23: a screen retry counts against the streak only if the engine lost something it could not get back; 15/15 always counts.
- Under that rule, 50 costly decisions fell across 25 of 28 matches, so there is no valid streak yet on the new build.
- The label results: 76 labels, readable 33, animating 30, slightly 9, covered 4.
- Verdict meanings, as the user clarified: readable = a person can tell the card even with clipped banner letters; slightly = readable but part of the power disc is covered; covered = hidden by design.

## 4. WHAT MERGED TODAY

| Issue | Merge sha | ISSUES sha | Skeptic verdict | Key number |
| --- | --- | --- | --- | --- |
| I-62 | `427b528` | `3cf032b` | Opus: CONFIRMED WITH NOTES | 8,714 frames compared, 0 wrong new reads, 2/2 recoveries; p95 `read_hand` 42→84 ms |
| I-63 | `ffd35ba` | `6a24ebd` (Haiku) | Opus: CONFIRMED WITH NOTES | 12 re-look events/37 logs, 5 recovered at 1.6 s; fix `_STRAY_RELOOK_MAX_ATTEMPTS=2` (T=3.2 s) |
| I-64 | `22c4cb1` | `78d289e` (Haiku) | Opus: CONFIRMED WITH NOTES | 6/14 readable tactics recovered (user truth), 0/43 wrong on labelled slightly/covered/animating; `BANNER_SEARCH` x-step 4→2 |
| I-65 round 1 | not merged | — | Opus: REFUTED | gate still released on empty sig `()` in 29/30 animating sequences; new call sites added ~20 s wait each, ~80 s/cycle |
| I-65 round 2 | `d53d5e9` | `6593582` (Haiku) | Opus: CONFIRMED WITH NOTES | 32/280 (11.4%) settled-but-incomplete reads held to the bound; +4.6 s/match median (21.6 s max); `READABLE_HAND_BOUND=8.0` PROVISIONAL |
| I-65b | `f2effc4` | `c6446cf` (Haiku) | Sonnet: CONFIRMED | release condition logically identical to pre-fix; reason now reflects stable vs bound trigger; 2/2 mutants, 19/19 siblings |

## 5. LATER (do not start without the user; new items from tonight go here too)

- **I-56's `_deselect_verified` note** (from `c0953b8`'s round-3 skeptic notes): it always dirties the ledger on a real press, even a clean one — recorded in ISSUES.md, not currently causing a wrong commit; worth a look if a future I-56 refusal looks ledger-related.
- **I-60** (cursor eligibility keyed on the digit, not the disc) — PARKED, tool-facing only. Branch `worktree-I60` (`2122c8f`): fixes 3 offline tools' reads but never touches the live refusal path — `hand_cursor_look` hands the raw glow list straight to `cursor_slot`, which already ignores the digit mask. Also breaks one sub-check in `test_false_cursor_on_occluded_slot.py`. Not merged.
- **I-61** (raised-card detector independent of the power disc) — PARKED, spike only. Branch `worktree-I61` (`eeb593a`), `card_lift.py` unwired: the lift step itself is real (38-43px on all 14 disc-corroborated events) but per-slot rest-vs-lifted populations overlap by 2-8px on slots 0 and 3, so no threshold ships (CLAUDE.md §10.4). Revisit only if a future live probe shows the disc genuinely unreadable after settling.
- **QA finder A** (`agent_progress/qa5-silent/`), 2 low findings: (1) I-57's `_topup_budget` check at `input_controller.py:1243-1250` cannot fire under current constants — delete it or cover it with a mutant that varies the constants; (2) `_close_pause_menu()`'s observer chain inside `read_balance_from_pause_menu`'s `finally` has no try/except (`_pause_menu_open` → `_fast_grab` → `_MSS.grab` fallback can raise), so a raising grab would replace the `PaidModelDisabled` the `finally` exists to pass through — narrow trigger, diagnostic-only impact today.
- **QA finder B** (`agent_progress/qa5-tests/`): `test_probe_select_budget.py` mutates `input_controller.py`/`orchestrator.py` in place by design (it has to run off-checkout during a live cycle) — make it run from a scratch copy instead of the live checkout.
- **The I-21-vs-probe contradiction** (§3, §6) — what really blinds a disc after a select press, if not the lift itself.
- **Tactics slot not excluded after an I-48 fallback** — the loop re-attempts the same failed tactics slot on later turns, ~11s tax per turn (not a deadlock).
- **I-44's hard case is still OPEN** (QA6 Q2: a dropped press + a coincidentally-blind post-press read still commits a false inference) — needs per-row digit corroboration from orchestrator or a post-commit detector; can't be closed inside `input_controller`.
- **Cycle 4's "match never started" abandonment** (table-approach failure, found by the guard census, never separately tracked) — needs its own look.
- **15/36 never-staged reveal misses** (10 no-OPPONENT-card-identified, 5 local-misfire-flag) — I-49 only fixed the staged-then-dropped half.
- **The transition-timeout drop site** (`orchestrator.py` ~`:9091`) still discards — 0/42 orphans traced through it this session, but it's structurally the same gap I-49 fixed elsewhere.
- **I-35 live verification** — `new_inning`/`reveal_recap` branches have still never fired live; keep checking cycle logs.
- **I-42 labels**: `FLICKER_WINDOW=10` is from the ticket text, not measured; 9/53 good labels wrongly rejected. Measure only if the label corpus is needed at scale.
- **Full hand corpus re-check after I-46** (the 540-hand corpus, not just the 2,409 turn frames) — never done.
- **Exclude LOCKED cards from the simulator pool and `choose_bans`** (RULES.md, user 2026-09-21) — `ban_grid.is_locked` reads ownership per cell; needs threading into `simulate.player_pool` / `decision_engine.choose_bans`, then re-run the I-13 ban A/B on the 31-card pool.
- **`result_source` semantics** — I-55's evidence line reported `path='ocr'` on a frame where the template alone had already cleared 0.80; check the path-selection logic.
- **`test_fixtures/reveal_kind_truth/auto/` hit its 200-frame cap** this cycle ("NOT keeping this pitch_boost one") — rotate or raise the cap (evidence loss, not a stall).
- **`REVEAL_SETTLE_MAX_SEC` lengthening** — carried from session 1: class B/D reveal frames (29% of the orphan population) are captured at 4.0-4.4s, past the current 2.5s ceiling.
- **`game_capture` desktop-fallback removal** — cycle 16's rig death showed `grab()` "FALLING BACK to a full-screen grab ... reading the DESKTOP", a fallback CLAUDE.md forbids. The I-05a liveness gate caught it this time, but the fallback itself should return `None`, never the desktop.
- **`questions_sheet.py`'s slot box is asymmetric** — neither the box (margins 49-71px right) nor `SLOT_TOL` (cost 13-27.7 vs 34) clips a legitimately-off-anchor card (the "7" in the user-truth sheet); tighten or document the asymmetry.
- **`test_result_commit_evidence.py` flakes on Snoopy** (FAIL/PASS/FAIL, timing) — check whether it's timing-sensitive on the Mac too.
- **10 Windows-only footguns with one-line fixes** (file-handle locks, `mss` BitBlt failing headless over SSH, `open()` defaulting to cp1252, `/tmp` literals, path separators) — enumerated in `Snoopy_testing.md` (`9783aad`); not actionable on the Mac, keep for whoever maintains the Snoopy runner. Separately, 6 OCR-content diffs under Windows tesseract are real but Mac-irrelevant (same file).
- **Housekeeping — DONE, noting for the record**: `.claude/worktrees/` cleanup removed 46 of ~51 worktrees (69G→7.6G); 1 unmerged skipped (`claude/eloquent-spence-03fe41`), 2 locked by old agents, 3 live at the time. Re-run `git worktree list` if it's grown large again.
- **I-64's 8 still-missed tactics**: q16/q18/q23 clipped left; q53 at 0.840; q29/q56/q62/q75 template-bank mismatch. The right-only banner match reached 10/14 but defeats `test_i22`.
- **The 9 "slightly" cards**: disc/digit ticket.
- **19 readable player-card digit misses.**
- **The match-start gate may release at the bound without protection.**
- **8 false phase flips in the middle of a pitching half.**
- **Reader misses now cost 8 s each.**
- **`test_deal_gate_arms` scenario 2 lost its same-read-twice coverage.**
- **The source-text wiring checks in `test_hand_gate_completeness`.**
- **3 tests reach real screen capture; stub `orch._fast_grab`/`_MSS`.**
- **`_best_banner` caching for speed.**
- **`ensure()`'s overlay-dismiss Escape raises chiaki's Quit dialog on the host list when connect fails.**
- **q18/q23 are missing from `clipped_banners.json`.**
- **The `| tail` exit-code hazard in briefs.**

## 6. OPEN QUESTIONS

- **What actually blinds a disc after a select press, live, given the lift itself does not?** I-21 (select-time inference) fired 32x over 34 run logs — 28 committed and correct, 0 wrong, 4 refused — so the mechanism is real and mostly safe, but the live probe read the disc on 0/187 unreadable frames, including lifted at dy -41, and the archive read 14/14 lifts clean. Candidates, neither measured: cursor-glow interference on the just-selected card, or a ~0.6s settle-timing gap.
- **WHO DELETED `tools/questions_sheet.py` from the main working tree mid-session?** Not established. Committed clean at `d5f9ed0`, then found as a bare ` D` in `git status` with no other file touched. Restored with `git checkout -- tools/questions_sheet.py`. Before dispatching anything else that writes under `tools/`, check every `agent_progress/*/progress.md` written this session for an `rm` or `rmtree` on that path.
- Does a speed boost PERSIST on base? Two live runners read +1 over their card (CLAUDE.md §4); low stakes (+0.046 runs/half). Still needs one live at-bat.
- Was draw #8 (session 1, cycle 6) or the evidence-less draw #9 (cycle 9, before I-55 merged) real? Both unverifiable — no frame, no score. Going forward every draw carries evidence (I-55); these two stay unknown.
- **Leave cycles chaining unattended overnight, or stop the console too?** Never answered by the user before a prior deadline; current behaviour (stated default, not contradicted): unattended chaining continues.
- **Why can the console not be streamed (IRL)?** chiaki's host list says "State: ready" but the stream never opens; the user is fixing it in person.
- **What is the true deal-completion time?** `READABLE_HAND_BOUND=8.0` is PROVISIONAL, borrowed from the old gate's max; §2 item 4 is how morning replaces it with measured `first_complete_at` data.

## 7. RULES IN FORCE (user's words where quoted)

- *"Any stalls, any issues count. Things need to be run perfectly like a nuclear power plant."* — the strict streak rule, §3.
- *"Never halt for input"* — questions about unreadable/ambiguous cards get queued (`tools/questions_sheet.py`, I-59), never block a run.
- Push a notification only for: run-stopping events, wrong-card commits, or the 50th clean match.
- **Never save the game** — resets and `Load Last Save` only.
- **Play the engine's pick, fix the engine** — never hand-override a card choice; check the reader first when a read looks wrong.
- **Never `git stash` / `git checkout <sha> -- file` in the main checkout while it holds uncommitted live data** — bisect in a scratch copy or a detached worktree.
- Navigation/routing code is left alone — no changes to `graph_walk.py` or the closed-loop chain logic; per CLAUDE.md §9, any such change needs a live A/B and a read of `GRAVEYARD.md` first.
- **Snoopy: one job at a time, grunt-work/labelling only, text-only reads** (never wired into the live ladder). Snoopy is OFF (user turned it off 2026-09-22).
- **Any NEW task or question found from here goes on the LATER list — do not dispatch it.**
- **Sleep the console when not in live use** — let it auto-sleep on its own (CLAUDE.md §1) or, if it needs putting down by hand, follow `console_rest_mode_procedure.md` step by step. Never press `ps_button` just to find out whether it's already asleep.
- Manager delegates routine work (merges, tests, doc edits, log reading) to Sonnet agents; the main model decides and dispatches. Opus skeptics for anything on the money path.
- **The labelling artifact is the preferred way to get ground truth. The user is willing to label more.** URL https://claude.ai/artifact/9MsSvsvvJcwsLgyb7sqDXG, db collection "answers".
- **Manager skill updates**: Haiku merges, abort on conflict → escalate to Sonnet; a fresh fixer on REFUTED; brief-size rules to keep context small; Snoopy only if a 5 s SSH probe answers.
- **CLAUDE.md is split into topic files**; cite sections (see the §-number map in CLAUDE.md).
