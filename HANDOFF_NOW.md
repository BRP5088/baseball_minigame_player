# HANDOFF_NOW — manager restart, 2026-09-24 ~01:30

## 1. STATE RIGHT NOW

- main HEAD: the commit carrying this file (parent `dd39842`). Merged this session: **I-70** (`e027daf`), and label set V truth (`dd39842`).
- **No agents running from this session.** chiaki is not running. The console has not been touched this session.
- The full suite has NOT been run on main since the I-70 merge. Run it before anything goes live.
- A separate session (task_d648486a / [819d23], "Investigate local_state.read_result false positives") may still be running. See §2a.
- **First actions, in order:** (1) dispatch the reshaped I-65c fixer from the brief in §2 (the user decided 09-24); (2) skeptic, then merge the peer's read_result regression test (§2a); (3) the PRIVACY capture-fallback fix (§6); (4) the test-speed ticket (§6); (5) run the full suite on main before anything goes live.
- Record is unchanged: **163W 20L 19D**. The paid model is OFF. Never save the game.

## 2. I-65c — STOPPED after 7 rounds; USER DECIDED 09-24: shrink to the core (see DECISION below)

**Refutations, one line each**
- r1: a has_fan/stillness race, and a weakened test.
- r2: the last play released at the 20 s cap instead of 8 s (+11.9 s/match), and the grab-count test mocked the real grab path away.
- r3: 2 wrong skips (a "reveal never appeared" play still counted), 1 missed skip (a phase fallback reset the count, costing 20 s), and a `_DEAL_INPUTS` leak into the next match's row.
- r4: an 8 s pitching cap brought back main's early release. 34/178 (19%) of real pitching deals still unread at 8 s.
- r5: both counters one low leaves the result screen waiting 20 s. An unpaid-restart path skipped every gate in the next match (SK1 survived).
- r6: `read_result` ran on every gate poll (90-140 ms), breaking `test_deal_frames_kept` and hanging `test_run_gates_on_liveness` (410 s against 147). Its false-positive census used hand crops, which a full-frame detector cannot read.
- r7: PARKED mid mutation sweep (not refuted). See below.

**What every brief assumed:** that the gate can safely tell "no deal is coming" on the last play, first from play counters and then from a result detector, and that this ~8 s/match saving is worth the extra machinery. Each round's fix for one failure mode opened another.

**The one question for the user:** keep chasing the last-play skip (~8.1 s/match saved), or shrink I-65c to its core? The core is to wait past 8 s on real deals (the motion-aware release, fixing the 19% of pitching deals read mid-animation) and keep main's fixed 8 s wait on the last play, with no counters and no detector.

**USER DECISION (2026-09-24): SHRINK I-65c TO THE CORE.**
- Wait past 8 s on real deals so cards are not read mid-animation. That means the motion-aware release, up to the 20 s cap.
- Keep main's fixed 8 s wait on the LAST play.
- The gate gets NO play counters and NO result detector.
- The last-play skip (~8 s/match) moves to the LATER list. Revisit it only after the read_result false-positive work (§2a) is finished AND merged.

**Brief for the new fixer (fresh agent, own worktree, based on main):**
- **Known traps, one per earlier round.** Each must be re-checked in the new round's tests:
  1. r1: has_fan/stillness race; a test weakened to pass.
  2. r2: the last play must release at 8 s, not the 20 s cap. Grab-count tests must go through the REAL grab path.
  3. r3: nothing skips or counts plays. The `_DEAL_INPUTS` stash must be popped on every exit path; the leak test from r3/r4 applies.
  4. r4: no 8 s cap on real deals, in either phase.
  5. r5: without counters, the both-low and unpaid-restart failures cannot happen. Add a test that proves the last play costs the same 8 s as main in every phase-misread case.
  6. r6: nothing expensive runs per poll. `test_deal_frames_kept.py` and `test_run_gates_on_liveness.py` must pass UNMODIFIED, within 15% of base runtime. Any evidence census must feed each reader the input it is built for (full frames stay full frames).
- **Acceptance number:** the share of REAL deals read mid-animation. It is 19% on main (34/178 pitching deals still unread at 8 s). Measure it on the same live logs, `overnight/run_live_20260923{b,c,e}.log`, with the r4/r5 skeptics' census method (`census.py` in the r4 skeptic's notes). Report n per phase. Also report the cost per match vs main (median and max) and the last-play wait (must equal main's ~8 s).
- **Useful parts from earlier rounds:** r3's motion-aware release and single-grab-per-poll (CONFIRMED by the r3 skeptic), from `952dd0a`, minus its last-play skip.
- **Process:** parallel mutants per the rules in §8; full sibling sweeps; then an Opus skeptic. **Stop rule:** a third refutation of this reshaped issue goes back to the user.

**Round-7 state (parked, uncommitted; superseded by the decision above, kept for reference):** worktree `.claude/worktrees/agent-a3d05bc3677e260bf`, based on r6 `a9c0d0c`. Notes are in `agent_progress/issues/I-65c/r7/progress.md`, with `census_full.py`, `mutants_r7.py` and `mutants_r7_summary.txt` alongside. Its design gates the detector to run after `RESULT_DETECTOR_T=3.0` s with no fan. **Its `orchestrator.py` was killed MID-MUTANT:** sha256 is `55a577db…`, but r7's clean file is `965eb133…`. Recover it by reversing the one un-restored mutant (the next after R1 in `mutants_r7.py` order), then verify the sha before using anything from it. Earlier branches: r6 `a9c0d0c`, r5 `i65c-r5`/`922ae44`, r4 `adcf70f`, r3 `952dd0a`.

### 2a. read_result "false positives": FALSE ALARM (session [819d23] / task_d648486a)
- r7's full-frame census flagged `local_state.read_result()` True at 0.97-0.98 on 5 "reveal" frames and at 0.806 on `negative_win_screen_no_banner_20260921`.
- The peer session opened all 6. They are TRUE end-of-match result screens (medallion, WINNER/LOSER, CLOSE, all 5 round dots) sitting in reveal fixture folders. I checked `reveal_occlusion/reveal10_edge075` myself: LOSER, CLOSE, 0-3.
- Main census: **0 of 344 mid-match frames classified as a result.** No code change is needed. r7 was told to relabel the 6 as positives.
- The peer is building a regression test (6 True, 305 reveal frames False, <10 s, one mutant) and will report a branch/sha. Skeptic and merge it from the manager.

## 3. RESULTS (live, from 09-23; no live runs since)

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


## 4. MERGED (09-23 and 09-24)

| Issue | Merge sha | Skeptic verdict | Key number |
| --- | --- | --- | --- |
| I-62 | `427b528` | Opus: CONFIRMED WITH NOTES | 8,714 frames compared, 0 wrong new reads, 2/2 recoveries; p95 `read_hand` 42→84 ms |
| I-63 | `ffd35ba` | Opus: CONFIRMED WITH NOTES | 12 re-look events/37 logs, 5 recovered at 1.6 s; `_STRAY_RELOOK_MAX_ATTEMPTS=2` (T=3.2 s) |
| I-64 | `22c4cb1` | Opus: CONFIRMED WITH NOTES | 6/14 readable tactics recovered, 0/43 wrong on labelled slightly/covered/animating; `BANNER_SEARCH` x-step 4→2 |
| I-65 (+65b) | `d53d5e9` (+`f2effc4`) | Opus: CONFIRMED WITH NOTES (r2); Sonnet: CONFIRMED (65b) | 32/280 (11.4%) settled-but-incomplete reads held to bound; +4.6 s/match median (21.6 max); `READABLE_HAND_BOUND=8.0` PROVISIONAL |
| I-67 | `ead1e1e` | Opus: CONFIRMED WITH NOTES | 5/8 held-out tactics misses recovered (4 new template donors), 0 new wrong over 7,217 frames, 55 new recoveries |
| I-66 | `de70a27` | Opus: CONFIRMED (round 2, verified on merged code) | 37/40 round-2 recoveries, 0 wrong on 76 labels + 8,514-frame census; user-readable 8/19 |
| I-70 | `e027daf` (+ISSUES `995359e`) | Opus: CONFIRMED WITH NOTES (r2) | 0 wrong / 0 FP over 583 frames at both scales; 19/20 + 6/6 certain labels; cross-frame 0/8,605 pairs differ; user label set V: 22/22 distinct cards match (`dd39842`) |

## 5. PARKED AND REFUTED WORK

- **I-65c**: reshaped by the user's decision, see §2. The old last-play-skip branches are reference only.
- **I-68**: PARKED after 3 refuted rounds, unchanged. Branches `278cc01` (r3), `8666168` (r2), `f570a6c` (r1).
- **I-69**: null, and stale. I-70 replaced it and is merged.
- I-60 (`worktree-I60` @ `2122c8f`) and I-61 (`worktree-I61` @ `eeb593a`): parked, unchanged.

## 6. LATER

- **The I-65c last-play skip (~8.1 s/match).** Deferred by the user 09-24. Revisit only after the read_result false-positive investigation (§2a) is finished and merged. Designs and refutations: §2, r3-r7.

- **Before any first push:** rewrite the history off the work email `[work email removed]` (1,376 commits across all branches, 09-05..09-21) to `brp5088@gmail.com`. Do it in a copy with `git filter-repo`, since every cited sha changes, and only with the user's go-ahead (user, 09-24). The repo has no remote. Local `user.email` has been `brp5088@gmail.com` since 09-24.

**Must: new this session (all CONFIRMED by reading or measuring; each goes through fixer→skeptic)**

- **PRIVACY: the capture fallback grabs the laptop desktop.** `orchestrator.py` `_fast_grab` (~2396-2436), `capture_screenshot_image` (~1542) and `_screenshot_logger_loop` (~1656: `game_capture.grab() or pyautogui.screenshot()`) fall back to the primary display when `grab()` returns None. It fired once, at `overnight/run_live_20260922b.log:780`. Checked: all 9,729 `screenshot_log` frames are 1920x1080; the only 7 laptop-sized images in the project are game frames from Aug 27. No desktop capture is on disk. Fix: fail and return None, never fall back. **Do this first.**
- **Test-speed ticket.** Sweeps ran ~10 min/mutant because one long-pole file bounds each mutant.
  - (1) Move `reset_env.give_up_dialog`/`load_save_dialog` (`reset_env.py:135-189`) from direct `pytesseract` to the warm `ocr_glyphs` handle. Measured: 682 → 33 ms/call on a non-dialog frame. That call spawns a subprocess, then globs the temp dir, 55-59 s per slow test. Live cost is small: it is gated behind `looks_like_ui()`, ~0.35% of frames.
  - (2) Stub `ic.time.sleep` in the 5 slow tests. `press_verified` sleeps 0.45 s x22 = 10 s.
  - (3) Temp-dir leaks: `_run_harness.py:64`, `test_early_result_double_debit.py:91`, `test_give_up_dialog_recognized.py:41`, `test_reset_sequence.py:354`, `test_leg_reliability.py:53,73,134`, `test_crawl_one_step.py:103-211`, plus ~15 SUSPECTED of the same shape. 15,890 leaked dirs (45 GB) were moved to `~/.Trash/baseball-test-temp-20260924` on 09-24; the user empties the Trash.
  - (4) Sweep scripts run SEVERAL MUTANTS AT ONCE, each in its own copied tree.
  - Estimates: long pole 150 → ~85 s; sweep ~50 → ~10-15 min. Re-time after the change.
- **Tests that rewrite production files in place:** `test_tactics_select_fallback.py` and `test_refusal_unwinds.py` (plus the known `test_probe_select_budget.py`). `test_refusal_unwinds.py:283` has a `_clear_pycache` race.
- **~2 s/match on the live turn path:** `orchestrator.py:4409` `local_game_state()` runs `read_result` (100 ms), `read_ban_counter` (19 ms) and `at_table` (79 ms) BEFORE `local_hand_cards` (68 ms; 17 ms fail-fast) on every settled turn poll. Try the hand first. SUSPECTED: up to 4 grabs per poll (`:9216`, `:2803`/`:2556`, `~:4425`).
- `compass.py:717`: a direct `pytesseract` fallback in `read_bearing` (walk path; rare, ~5 s when it fires). `landmarks.py:238,311` are pytesseract in dead scripts.
- **The home-plate blank may cost slot-2 tactics reads.** `_blank_homeplate_strip` (`orchestrator.py:5334`, `HOMEPLATE_STRIP=(0.439,0.490)`) zeroes x 429-478 when a runner is stranded on home. 38 frames were found (7 bursts over 4 days), all with slot 2 unread, and the strip clips ~15 px of slot 2's tactics badge. The docstring only measured player digits (n=76). This is the "black line" the user saw in label set V q29.
- Label-set builders must DEDUPE by hand+slot. Set V v1 showed 12 near-identical frames of one held hand. I-70's "27 new reads" were ~15 distinct cards.
- I-70 geometry mutants survive: fine window off-by-one, one-radius fine pass, coarse step 5→6. It needs more positive fixtures. Branch worst-frame latency spikes of 241-245 ms under load, against a main max ≤167; record the frame id in timing.

**Carried from 09-23**

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
- **Sub-agent sweeps run in PARALLEL.** Use 2 jobs on weekdays 08-18 while the user works, 8-10 at night, all 12 when the user says they're off the Mac, and 1 while the console is live. Run several mutants at once in copied trees. Keep FULL per-mutant sibling sweeps; never fail-fast. `test_probe_select_budget.py` and `test_tactics_select_fallback.py` run alone. (memory: test-parallelism-schedule, full-mutant-sweeps-over-speed)
- **The first slow sweep gets profiled before the next dispatch** (memory: profile-slow-sweeps-immediately). About 9 h were lost on 09-23 to serial sweeps.
- **Worktree commits may use `--no-verify` ONLY when the sole hook failure is the missing gitignored `demos/`,** with the reason in the message (user, 09-23). The merge agent then runs the guards and the full suite in main.
- **Manager restart after every 8th sub-agent report, and STOP after the 3rd refutation of the same issue** (skill update, 09-24). This restart is both.
- Permanent deletion is not allowed for Claude. Move files to the Trash and let the user empty it.
- Label set V (I-70 new reads): `https://claude.ai/artifact/KrjZ6LZzJ6sLzMQnEvoZJ4`. Truth is in `test_fixtures/user_truth/20260923_i70_setV/labels.json`.
