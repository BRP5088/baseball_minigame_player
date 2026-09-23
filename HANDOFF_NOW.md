# HANDOFF_NOW — manager restart, 2026-09-23

## 1. STATE RIGHT NOW

- main HEAD `3600252`. Today's merges (I-62, I-63, I-64, I-65+65b, I-67, I-66) are in §4.
- Nothing is running and chiaki is quit (user rule: disconnect the stream when idle).
- The console is reachable again — the user fixed it this morning (was broken at last night's handoff).
- Record **163W 20L 19D**.
- The paid model is OFF. Never save the game.

## 2. FIRST ACTIONS FOR THE NEXT MANAGER, in order

1. **Restart the PARKED Opus skeptic on I-65c round 3.** Branch `worktree-agent-abdb7e40496b486b1` @ `952dd0a` (fixer notes: `.claude/worktrees/agent-abdb7e40496b486b1/agent_progress/issues/I-65c/round3/progress.md`). Brief: verify `turns_this_half` trust via log replay of `run_live_20260923b/c/e`, check extra-innings behaviour, review the 8 updated test-file diffs, re-run the harness, confirm single-grab-per-poll, check the 5 new mutants + siblings.
2. **Restart the PARKED I-70 round-2 fixer**, from round-1 branch `worktree-agent-a7ba63b647f1ca9c2` @ `0911795`. Round-2 acceptance: runtime median/p95 <= main+10%, max <= 200 ms; recoveries >=19/20 certain-slightly, >=6/6 label-IV checks, >=90% of the 74 corpus resolutions; 0 wrong; mutant M2 (digit-is-None gate) caught; add a tactics-banner-guard test (currently 0 cases, unpinned).
3. Merge each one if it is confirmed. Run the full suite, which must be green, before anything goes live.
4. Before live: `./restart_chiaki.sh` (the patched build only — verify it's the patched pid, not `/Applications/chiaki-ng.app`), then `ensure_stream.ensure()`, then check a frame. Launch cycles with the scratchpad `chain.py` pattern: copy its logic, which stops after 2 route failures in a row. Watch with a Monitor that reads from the start of the log (`tail -n +1`, not `-n 0`) and uses `awk` with `fflush`, not `cut` — both buffered silently on live runs today.
5. After each chain: `pkill -9 -x chiaki`, because the user wants the stream disconnected when idle. Then build a labelling artifact from the new decision frames, using the scratchpad labeler template (adds the "Unknown" chip and per-field "Best guess" toggle — see §8).

## 3. RESULTS

Per-cycle table, cycles 27-37 (all today; builds noted where the HEAD changed):

| Cycle | Build | Outcome | Flagged events | Unread-decisions | Gate bound/stable |
| --- | --- | --- | --- | --- | --- |
| 27 | c6446cf | W W W W | m3: 4x play REFUSED (slot 0 blind); m4: discard NOT CONFIRMED | 8 | 26/22 |
| 28 | c6446cf | W W W W | none | 2 | 23/25 |
| 29 | c6446cf | W W W W | none | 3 | 29/19 |
| 30 | c6446cf | W D W W | m4: confirm_play FAILED 5/5, play REFUSED | — | — |
| 31 | 10a66d6 | L(refusal) L W W | m1 refusal (I-68-shape) | — | — |
| 32 | 10a66d6 | W W W W | none | — | — |
| 33 | 10a66d6 | D W W D | none | — | — |
| 34 | 3600252 | W W W W | none | 2 | 30/18 |
| 35 | 3600252 | W W W W | none | 2 | 30/21 |
| 36 | 3600252 | W W W W | none | — | — |
| 37 | 3600252 | W D W D | none | — | — |

Build `3600252` (I-66+I-67) went **14W 0L 2D over cycles 34-37 (16 matches), 0 monitor-flagged events.**

Label-set progression (unread-card decisions per cycle → readable-miss rate per cycle):

| Set | Cycles | Build | Decisions/cycle | Readable misses/cycle |
| --- | --- | --- | --- | --- |
| I | 20-26 | old (pre-session) | 10.9 (76/7) | 4.7 |
| II | 27-30 | +I-62..65 | 7.0 (28/4) | 2.0 |
| III-a | 31-33 | +I-67 | 5.7 (17/3) | 0 |
| III-b | 34-35 | +I-66 | 4.0 (8/2) | 1.0 (both tactics) |

Streak under the user's rule (a retry counts against the streak only if the engine lost something unrecoverable; 15/15 always counts): **19 consecutive monitor-clean matches** since c31m2 (c31m2-m4, c32 x4, c33 x4, c34 x4, c35 x4) — but UNKNOWN-slot ("costly") decisions still occur most cycles (c27 8, c28 2, c29 3, c34 2, c35 2), so the strict count toward the 163W/20L/19D goal-of-50-in-a-row is lower than 19. Remaining decision classes: "slightly covered" ~2/cycle (I-70's job), mid-animation ~2-3/cycle (I-65c's job).

## 4. MERGED TODAY

| Issue | Merge sha | Skeptic verdict | Key number |
| --- | --- | --- | --- |
| I-62 | `427b528` | Opus: CONFIRMED WITH NOTES | 8,714 frames compared, 0 wrong new reads, 2/2 recoveries; p95 `read_hand` 42→84 ms |
| I-63 | `ffd35ba` | Opus: CONFIRMED WITH NOTES | 12 re-look events/37 logs, 5 recovered at 1.6 s; `_STRAY_RELOOK_MAX_ATTEMPTS=2` (T=3.2 s) |
| I-64 | `22c4cb1` | Opus: CONFIRMED WITH NOTES | 6/14 readable tactics recovered, 0/43 wrong on labelled slightly/covered/animating; `BANNER_SEARCH` x-step 4→2 |
| I-65 (+65b) | `d53d5e9` (+`f2effc4`) | Opus: CONFIRMED WITH NOTES (r2); Sonnet: CONFIRMED (65b) | 32/280 (11.4%) settled-but-incomplete reads held to bound; +4.6 s/match median (21.6 max); `READABLE_HAND_BOUND=8.0` PROVISIONAL |
| I-67 | `ead1e1e` | Opus: CONFIRMED WITH NOTES | 5/8 held-out tactics misses recovered (4 new template donors), 0 new wrong over 7,217 frames, 55 new recoveries |
| I-66 | `de70a27` | Opus: CONFIRMED (round 2, verified on merged code) | 37/40 round-2 recoveries, 0 wrong on 76 labels + 8,514-frame census; user-readable 8/19 |

## 5. PARKED AND REFUTED WORK

- **I-68** — PARKED after 3 refuted rounds. Key insight: the hovered/raised TARGET card occludes its LEFT neighbour's disc — the blindness is caused by our own cursor, not the game. Round 3's safe-only fix still stalled the run at `MAX_STUCK` in a live case; main's existing rotate-after-3-refusals behaviour is already the safer choice, net gain across all 3 rounds was ~1 card grade in 1 case. Branches kept: `278cc01` (r3), `8666168` (r2), `f570a6c` (r1).
- **I-65c** — rounds 1 and 2 REFUTED (r1: has_fan/stillness race + a weakened test; r2: last-play-of-match releases at the 20 s cap instead of the old 8 s bound, +11.9 s/match, and the grab-count test mocked away the real grab path). Round 3 (branch `worktree-agent-abdb7e40496b486b1` @ `952dd0a`) is done and its skeptic is PARKED — restart per §2.1.
- **I-70** — round-1 reading is SOUND (0 wrong on 1,675 re-reads, 4 labelled sets, and 74 corpus resolutions), but blocked on runtime (p95 122→156 ms, over the 150 ms budget) and mutant M2 survives. Round-2 fixer is PARKED — restart per §2.2.
- **I-69** — null. Measured that no floor/margin threshold separates true from false slightly-covered digit reads (45 false abstentions up to score 0.911). Its resulting decision ("don't read slightly-covered digits, lean on I-68 not refusing on them") is now stale: I-68 is parked, and the user later ruled the non-read outcome unacceptable (§8) — I-70 is the live replacement.

## 6. LATER

**Must**

- **`ensure()`'s overlay-dismiss Escape raises chiaki's own Quit dialog** when it fires on the host list after a failed connect — confirmed live TWICE today (once fatally, once during a recovered attempt). One keystroke from killing the app mid-session. Should check a session exists before sending Escape.
- **Preflight: verify chiaki is the patched binary** (inject FIFO has a reader) before launching a chain. Tonight's run-a was fully wasted (7 cycles, 0 matches, `OSError Errno 6` on the FIFO) because the user had started stock `/Applications/chiaki-ng.app`.
- **The `| tail`/`| cut` exit-code and buffering hazard in briefs and Monitors.** Caused today's silent monitor (run-a) and is a repeat methodology note (§10.16c). Briefs should report capture exit status before piping; Monitors should use `tail -n +1` and `awk`-with-`fflush`, never `cut`.
- **"REFUSED 3x running on hand_index 3 — excluding it" excludes the TARGET when the blocker is a stray**, not the target itself — the next target then gets refused for the same slot (c27 census). Same family as I-68's parked exclusion bug; needs its own fix now that I-68 is parked.
- **The match-start gate may release at the 8 s bound without protection** (I-65 r2 skeptic: first reads ~16.7 s after the last pre-commit event, 7/10 still animating) — needs the live `first_complete_at` distribution I-65c/I-70 work is accumulating.
- **I-64/I-67's remaining tactics misses**: q18 (held out, same card as recovered q16), q53 (0.840), q29/q56/q62/q75 (template-bank mismatch, cause unknown).

**Nice**

- I-56's `_deselect_verified` note (always dirties the ledger on a real press) — not currently causing a wrong commit.
- I-60 (cursor eligibility keyed on the digit, not the disc) — PARKED, tool-facing only, branch `worktree-I60` @ `2122c8f`.
- I-61 (raised-card detector independent of the disc) — PARKED, spike only, branch `worktree-I61` @ `eeb593a`; re-confirmed by I-68 r3 that slots 0-3 rest/lifted populations overlap 2-8 px (only slot 4 separates).
- QA finder A: `I-57`'s `_topup_budget` check (`input_controller.py:1243-1250`) can't fire under current constants; `_close_pause_menu()`'s observer chain has no try/except around a raising grab.
- QA finder B: `test_probe_select_budget.py` mutates production files in place; make it run from a scratch copy.
- 8 false phase flips mid-pitching half (pre-existing, reconfirmed by I-65 r2 skeptic).
- Reader misses now cost 8 s each under the current bound — digit/banner work pays twice.
- `test_deal_gate_arms` scenario 2 lost its same-read-twice mutant coverage (readable_hand_gate itself still catches it).
- `test_hand_gate_completeness.py:187-199`'s wiring checks read source text — the only guard on the two new gate call sites.
- 3 tests reach real screen capture (`test_orchestrator_diagnostics`, `test_decisions`, `test_should_redraw_incomplete` via `_grab_settle_regions`) and fail when the Mac displays sleep overnight; stub `orch._fast_grab`/`_MSS`. Also: I-65c r2's own grab-count test mocked away the real grab path (invalid) — needs a real-grab test.
- `_best_banner` caching — called up to 3x/slot over 65 positions.
- `test_tactics_select_fallback`'s `_clear_pycache` races parallel jobs (JOBS=4); passes standalone.
- Confirm-play: base rate 155/1277 plays needed 2+ confirms (12%), 2 hard-failed (0.16%), clustered drops — no fix proposed yet.
- Record the blocker slot (not just the target) in `why.json` for refused frames, and have the questions-sheet tool box the blocker — a labeller question was mis-boxed on the target today.
- Cycle 4's "match never started" abandonment — never separately tracked.
- 15/36 never-staged reveal misses (I-49 only fixed the staged-then-dropped half).
- The transition-timeout drop site (`orchestrator.py` ~`:9091`).
- I-35's `new_inning`/`reveal_recap` branches have still never fired live.
- I-42's `FLICKER_WINDOW=10` is unmeasured; 9/53 good labels wrongly rejected.
- Full hand corpus re-check after I-46 (540-hand corpus, not just the 2,409 turn frames).
- Exclude LOCKED cards from the simulator pool and `choose_bans` (RULES.md, user 2026-09-21).
- I-55's `result_source='ocr'` reported on a frame where the template alone had already cleared 0.80.
- `test_fixtures/reveal_kind_truth/auto/` hit its 200-frame cap.
- `REVEAL_SETTLE_MAX_SEC` — class B/D reveal frames (29% of the orphan population) captured at 4.0-4.4 s, past the 2.5 s ceiling.
- `questions_sheet.py`'s slot box is asymmetric (margins 49-71 px right; `SLOT_TOL` doesn't clip a legitimately off-anchor card).
- `test_result_commit_evidence.py` flakes on Snoopy (timing) — Snoopy is off, low priority.
- 10 Windows-only footguns, enumerated in `Snoopy_testing.md` — not actionable on the Mac.

## 7. OPEN QUESTIONS

- **What actually blinds a disc after a select press, live?** I-63's skeptic found it's time-varying, NOT selection occlusion (7/7 refused slots read clean on rescue with the target still lifted, nothing pressed in between) — blind slot is a tactics card in >=5/7 refusals, which links to the banner weakness I-64/I-67 have been closing. Mechanism itself still not identified.
- **WHO DELETED `tools/questions_sheet.py` from the main working tree mid-session (prior session)?** Never established. Before dispatching anything that writes under `tools/`, check `agent_progress/*/progress.md` for an `rm`/`rmtree` on that path.
- Does a speed boost PERSIST on base? Two live runners read +1 over their card; still needs one live at-bat to confirm.
- Was draw #8 (session 1, cycle 6) or the evidence-less draw #9 (cycle 9) real? Unverifiable — no frame, no score. Stays unknown.
- **Is `READABLE_HAND_BOUND=8.0` still the right fallback value?** c27 census: bound releases complete right at the wall (median 8.0 s vs 4.85 s for stable releases), suggesting it's too tight for a confirm pass; I-65c's motion-aware release now avoids the fixed bound for post-play/end-of-half cases, but the match-start path (§6 must-list) and the general fallback still use it. Collect more `first_complete_at` data before resetting it.
- **Does `turns_this_half` correctly identify the last play in extra innings?** Open question for the I-65c round-3 skeptic restart (§2.1).

## 8. RULES IN FORCE (user's words where quoted)

- *"Any stalls, any issues count. Things need to be run perfectly like a nuclear power plant."* — the strict streak rule, §3.
- A screen retry counts against the streak only if the engine lost something it could not get back (user rule, 09-23); 15/15 always counts.
- *"Never halt for input"* — questions about unreadable/ambiguous cards get queued (`tools/questions_sheet.py`, I-59), never block a run.
- Push a notification only for: run-stopping events, wrong-card commits, or the 50th clean match.
- **Never save the game** — resets and `Load Last Save` only.
- **Play the engine's pick, fix the engine** — never hand-override a card choice; check the reader first when a read looks wrong.
- **Never `git stash` / `git checkout <sha> -- file` in the main checkout while it holds uncommitted live data** — bisect in a scratch copy or a detached worktree.
- Navigation/routing code is left alone — no changes to `graph_walk.py` or the closed-loop chain logic; per CLAUDE.md §9, any such change needs a live A/B and a read of `GRAVEYARD.md` first.
- **Snoopy: one job at a time, grunt-work/labelling only, text-only reads.** Snoopy is OFF (user turned it off 09-22, still off).
- **Any NEW task or question found from here goes on the LATER list — do not dispatch it.**
- **Sleep the console when not in live use** — let it auto-sleep, or follow `console_rest_mode_procedure.md` by hand. Never press `ps_button` just to find out whether it's already asleep.
- **Disconnect the stream when idle** (new today) — `pkill -9 -x chiaki` after each chain; the user reports the stream looks laggy after ~4 h connected.
- **Use labelling artifacts** — the user is willing to label more; the template now includes an "Unknown" chip and a per-field "Best guess" toggle on every number row (guessed values are truth for scoring, NOT template donors).
- **"Slightly covered stays unread" is NOT acceptable** (user's ruling, 09-23) — read them or optimise the photo timing; this is why I-70 exists and I-69's non-read fallback is stale.
- **Fielding is 0-3, never negative** (user correction, 09-23) — removed -2/-1 chips from the labeller.
- **Manager delegates routine work** (merges, tests, doc edits, log reading) to Sonnet agents; Opus skeptics for anything on the money path.
- **Merge via Haiku; on a conflict, abort and hand to Sonnet.**
- **Refuted work goes to a fresh fixer**, not a patch on the refuted branch.
- **Restart the manager after every 4th merged fix, or on the first compaction** (new rule, 09-23) — this restart is one.
- **Label artifact URLs**: I (c20-26) `https://claude.ai/artifact/9MsSvsvvJcwsLgyb7sqDXG` · II (c27-30) `https://claude.ai/artifact/LV1ZvDaBr1aYaNQM3KKaQP` · III (c31-35) `https://claude.ai/artifact/KSgyELyD6UQS6Uuc8y2v9T` · IV (I-70 checks) `https://claude.ai/artifact/7PnTHz5Lb2dWTCQDvRnBnU` — all db collection "answers".
- **CLAUDE.md is split into topic files**; cite sections (see the §-number map in CLAUDE.md).
