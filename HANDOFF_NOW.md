# HANDOFF_NOW — manager session 2026-09-24 (01:06 → ~12:30)

## 1. STATE RIGHT NOW

- main HEAD: the commit carrying this file (parent `fa9e2ce`). **Full suite on `fa9e2ce`: 305/305 PASS, 791 s, JOBS=2** (`agent_progress/merge-privacy-r3/suite.log`).
- No agents running from this session. chiaki is not running. The console was not touched this session. No live runs since 09-23.
- Record unchanged: **163W 20L 19D**. The paid model is OFF. Never save the game.
- **GitHub:** `https://github.com/BRP5088/baseball_minigame_player`, main = `880da35` (pushed by the user 09-24; a rewritten copy, see §5). Local main is AHEAD: the press_verified test, the README, the PRIVACY fix and this handoff are not pushed yet. Next push: §5.
- **First actions for the next session, in order:** (1) the user runs the next GitHub push (§5); (2) the user decides the open questions in §7; (3) pick from §6 LATER. Live runs are allowed (the user said: after the merges + a clean suite, both now true); follow CLAUDE.md's rig rules.

## 2. MERGED THIS SESSION

| What | Merge sha | Skeptic | Key number |
| --- | --- | --- | --- |
| read_result end-screen regression test (peer session) | `bf9f697` | Sonnet: CONFIRMED | 7 end screens read True, 134 mid-match False; 6/6 own mutants killed |
| Test speed: real sleeps stubbed, 30 test temp-dir leaks plugged | `81df31d` | Sonnet: CONFIRMED WITH NOTES | suite 937 → 867 s mean (n=2/arm, JOBS=2, under load); `test_verified_selection` 56 → 4 s |
| `test_discard_watches_redeal.py` no longer leaves `diagnostics/deal_frames` (peer session) | `ae2627b` | Sonnet: works, 3/3 mutants | swap not in try/finally (LATER) |
| `test_verified_selection.py` pins `press_verified`'s retry | `359fc99` | Sonnet: CONFIRMED | no production defect: the old test never exercised `press_verified`; 5+3 mutants killed |
| README.md | `2ff220c` | manager review | 141 lines, every claim sourced |
| **PRIVACY: never capture the desktop; a missed frame never presses or decides** | `fa9e2ce` | Opus r3: CONFIRMED (r1, r2 REFUTED) | 0 desktop captures and 0 blind presses under every stub (main: up to 244 captures, 20-80 blind presses); normal frames unchanged |

PRIVACY detail: removed `pyautogui.screenshot()` fallbacks in `game_capture.grab()` (the real source; every path goes through it, including the 1 Hz logger) and 3 orchestrator sites. Missed frames now retry within bounds: `_ban_scroll_to_top` (`BAN_SCROLL_BLIND_TRIES=3`), the ban scan (not cached after misses), `_pause_menu_open`/`_close_pause_menu_verified`, `read_balance_from_pause_menu` (only the opener press when blind), `_match_start_screen` (None = can't see), `wait_for_hand_deal` (an outage counts against the same `max_wait`). Tests: `tests/rig/test_no_desktop_capture_fallback.py`, `test_capture_fallback_privacy_r2.py`, `test_capture_fallback_privacy_r3.py`. Skeptic notes: `.claude/worktrees/agent-a6497625697a3c3f9/agent_progress/skeptic-privacy-r3/progress.md`.

## 3. PARKED / DECIDED

- **I-65c (reshaped core): PARKED by the user, 09-24.** r1 `ef51e3b` REFUTED (removed the 3.0 s floor and the completeness rule unasked; 3 tests weakened). The skeptic's numbers made the change not worth it: of main's unread-at-8 s deals, pitching 18/34 and batting 134/154 had NO fan on screen at 8 s, so a motion-aware release could at best take pitching from 19.1% to 10.1%. The user chose to investigate why cards come late instead (§4). Skeptic notes: `.claude/worktrees/agent-a134f527e9d4a8f3d/agent_progress/skeptic-I-65c-core/`.
- The I-65c last-play skip stays deferred (as 09-24 morning).
- I-68 (3 refuted rounds), I-60, I-61: parked, unchanged. I-69: stale.

## 4. WHY THE CARDS COME LATE (investigation, read-only; `agent_progress/late-deal-cards/` in the main checkout: `summary.md`, `deals.csv` 442 rows, `contact_sheet.png`)

- **The more bases the runners travel, the later the hand appears** (n=269, `predicted_bases` from the reveal margin, `orchestrator.py:3443`): 0 bases → 24% not complete by 8 s (median 6.30 s); 1-2 → 65%; 3-4 → 95%; 5+ (n=18) → 100%. The code's own comment already notes "1.1 s after one play, 10.8 s after a home run".
- Reader miss REFUTED for the main case: 6/6 no-fan-at-8 s frames opened by eye show an empty table.
- 44 of the batting cases are the inning change (no deal coming), which is expected.
- Batting has far more no-fan deals than pitching (51% vs 10%).
- **The user's hypothesis ("runners moved differently than the engine expected") is UNTESTABLE on disk:** only the pre-play prediction is logged, not the actual bases moved. A proxy (occupied-base diff, n=215) is unreliable: no runner identity.
- New lead, n=3 by eye, unverified: the rightmost fan slot sits at or over the edge of the fixed "hand" crop (`orchestrator.py:1770`, x ≤ 0.760).
- **Not yet reproduced by a skeptic.**

## 5. GITHUB PUBLISHING (the user's; each push waits for the user)

- The repo is published as a REWRITTEN COPY. The local repo keeps its own history, so every sha in this file and in ISSUES/OPEN is a LOCAL sha. GitHub's shas differ.
- The kit is in `agent_progress/github-publish/` (gitignored):
  - `publish_copy.sh <new dir>`: a fresh clone of main, then one `git filter-repo` pass.
  - `mailmap`: both old addresses → brp5088@gmail.com.
  - `replacements`: scrubs both addresses from file text.
  - `make_blanked.py`: blanks ONLY the macOS menu bar and Dock in the 47 full-desktop captures in history (9x 1400x904, 2x 1728x1117, 2x 1999x1292, 34x 2000x1292), measured per image, with a cache in `blanked/<orig blob id>`.
- It is deterministic (two runs gave identical shas), so each push fast-forwards.
- **Next push:**
  1. `agent_progress/github-publish/publish_copy.sh <new empty dir>`
  2. Check that `880da35` is an ancestor of the new HEAD.
  3. Re-run the blue-pixel scan over all images (the game is black and white, so blue near the top or right edge means desktop UI).
  4. The user runs, in the new dir: `git remote add origin git@github-personal:BRP5088/baseball_minigame_player.git` and `git push -u origin main`.
- The auto-mode classifier refuses a push from Claude ([Sensitive-Source Provenance]), so the user runs the push.
- Checked before the first push:
  - No secrets in the files or the history. `.env.example` holds the placeholder `sk-ant-...`. The chiaki `regist_key`/`morning` hits are source identifiers.
  - No private IPs in the text.
  - 2 chiaki host-list PNGs show the console's LAN IP and part of its name. The user was told this and did not ask for a blank.
- `gh` is not installed. git-filter-repo was installed with brew, with the user's approval.

## 6. LATER

**From this session: test speed** (profiler, read-only: `agent_progress/test-profile/{per_file.tsv,ranked_by_cpu.tsv,prof_test_*.txt}`. Total 856 s CPU. Longest-first scheduling is ALREADY live via `.test_durations`)
1. `reset_env.py:135/170` `give_up_dialog`/`load_save_dialog` call pytesseract directly (~474 ms/call). Moving them to the warm `ocr_glyphs` handle saves ~150-160 s of suite time: `test_run_gates_on_liveness` 83 s, `test_early_result_double_debit` 74 s, and more across the 18 files that reach it. PRODUCTION reset/money path, so it needs an Opus skeptic.
2. `test_graph_walk.py`: 138 s wall but 0.2 s CPU. It makes 265 real `time.sleep` calls in `graph_walk.walk_link`/`_slip_past`/`face_the_table`/`approach_goal`. `graph_walk.py` is OFF-LIMITS (§9 rule), so stub the sleep IN THE TEST only. Saves ~130 s, and this is the suite's longest file.
3. `local_state.py:568` `base_badge`/`read_base`: 66,675 `cv2.matchTemplate` calls in `test_runner_speed` (85.7 s). Production live reader.
4. `circle_finder.find_circles`/`reveal_cards.read_reveal` run repeatedly on the same frames: ~35-40 s over 3 files.
5. The earlier per-file "top 10" list (from the timing agent) was wrong. Use `per_file.tsv`.

**From this session: the rest**
- **Deal-wait bound by predicted bases** (§4): the candidate fix for late cards. It is on the live turn path, so it needs a live A/B (user rule 09-24).
- Log the actual bases moved (or runner identity) per play, so the user's mismatch hypothesis can be tested.
- Verify the hand-crop clipping lead (`orchestrator.py:1770`) and the has-fan gate flickering true on background texture.
- Blind presses outside the PRIVACY diff (pre-existing):
  - `run()` checks the ban cursor 3 times. After 3 missed frames it falls back to dead reckoning: `select_bans_and_start_full` presses move/select/confirm twice without looking. This was deliberate, since the $50 is already paid. **User decision.**
  - A ban scan that was blind while homing reads a fragment (7 cards, not cached), and `run()` still chooses bans from it.
- Test gaps:
  - Mutant X5 (a missed deal poll counted twice) is caught only by a setup count, because the outage check reads the function's self-reported `waited`.
  - `test_discard_watches_redeal.py` does its `DEAL_FRAME_DIR` swap without try/finally. The pattern to copy is `test_tactics_select_fallback.py` ~545.
  - `test_verified_selection.py`'s outer sleep restore is manual, not try/finally.
  - The `press_verified` single-attempt mutant is not caught by `test_give_up_dialog_recognized`/`test_early_result_double_debit`. `tests/rig/test_press_verified.py` does catch it.
- Sweep tooling:
  - Sweep scripts grep FAIL/TIMEOUT, but the runner logs a 300 s kill as HUNG. Add HUNG to every sweep grep.
  - Copying the gitignored `demos/` into a worktree makes the pre-commit hook pass for real, so `--no-verify` is no longer needed. Put this in every brief.
- Harness friction:
  - The `rtk` PreToolUse hook refused plain `git` in 3 sub-agent worktrees. One agent used git plumbing; one used `/usr/bin/git`. Investigate before the next fan-out.
  - The session scratchpad is SHARED by sub-agents, and a skeptic's `make_mutant.py` overwrote another's. Briefs must give a per-agent scratch path (§10.16b).
- 13 suite files fail in any fresh worktree, because gitignored data is missing (`chiaki-ng-src/`, `demos/`, `screenshot_log/`, `overnight/*.log`, a C++ binary). Consider skip-with-reason.

**Carried (still open)**
- Tests that rewrite production files in place: `test_tactics_select_fallback.py`, `test_refusal_unwinds.py` (a `_clear_pycache` race at :283), `test_probe_select_budget.py`.
- ~2 s/match on the live turn path: `orchestrator.py:4409` `local_game_state()` runs `read_result`/`read_ban_counter`/`at_table` before `local_hand_cards`. Try the hand first. Needs a live A/B (user rule 09-24).
- `compass.py:717` direct pytesseract fallback: 0 s in the suite, rare live. `landmarks.py:238,311` are dead scripts.
- The home-plate blank (`_blank_homeplate_strip`, `orchestrator.py:5334`) may clip slot-2 tactics reads (38 frames).
- Label-set builders must DEDUPE by hand+slot.
- I-70 geometry mutants survive (fine window off-by-one, one-radius fine pass, coarse step 5→6). Needs more positive fixtures.
- `ensure()`'s overlay-dismiss Escape can raise chiaki's Quit dialog on the host list (confirmed live twice 09-23).
- Preflight must verify chiaki is the PATCHED binary (the FIFO has a reader) before a chain.
- The `| tail`/`| cut` exit-code and buffering hazard in briefs and Monitors (§10.16c).
- "REFUSED 3x ... excluding it" excludes the TARGET when the blocker is a stray.
- The match-start gate may release at the 8 s bound without protection.
- I-64/I-67's remaining tactics misses (q18, q53, q29/q56/q62/q75).
- Nice: I-56 `_deselect_verified`; I-57 `_topup_budget`; `_close_pause_menu()` observer without try/except; 8 false phase flips mid-pitching; `test_deal_gate_arms` scenario 2 coverage; `test_hand_gate_completeness.py:187-199` source-text wiring checks; `_best_banner` caching; confirm-play 12% need 2+ confirms; record the blocker slot in `why.json`; cycle 4 "match never started"; 15/36 never-staged reveal misses; transition-timeout drop site (~`:9091`); I-35 branches never fired live; I-42 `FLICKER_WINDOW=10` unmeasured; full hand corpus re-check after I-46; exclude LOCKED cards from the simulator pool and `choose_bans`; I-55 `result_source='ocr'`; `reveal_kind_truth/auto/` hit its 200-frame cap; `REVEAL_SETTLE_MAX_SEC`; `questions_sheet.py` slot box asymmetric; `test_result_commit_evidence.py` flakes on Snoopy; 10 Windows-only footguns in `Snoopy_testing.md`.
- **Pure code smells** (dead code, duplicates, style): per the user (09-24), LIST them for the user to pick; no deletions without their yes. No finder pass has been run yet.

## 7. OPEN QUESTIONS (for the user)

- Should the deal wait scale with predicted bases (§4, §6)? It needs a live A/B.
- Should the ban-cursor dead-reckoned fallback (§6) be kept, or should the bot refuse to press when it is blind?
- Should the chiaki host-list PNGs (LAN IP, partial console name) be blanked in the published copy?
- Carried: what blinds a disc after a select press, live? Who deleted `tools/questions_sheet.py` mid-session (a prior session)? Does a speed boost persist on base? Were draws #8/#9 real? Is `READABLE_HAND_BOUND=8.0` right? Does `turns_this_half` find the last play in extra innings?

## 8. RULES IN FORCE (user's words where quoted)

- *"Any stalls, any issues count. Things need to be run perfectly like a nuclear power plant."* A retry counts against the streak only if the engine lost something it could not get back; 15/15 always counts.
- *"Never halt for input"*: questions about cards get queued (`tools/questions_sheet.py`), never block a run.
- Push a notification only for run-stopping events, wrong-card commits, or the 50th clean match.
- **Never save the game.** Play the engine's pick; fix the engine.
- Never `git stash` / `git checkout <sha> -- file` in the main checkout while it holds uncommitted live data.
- Navigation/routing code is left alone (`graph_walk.py`, the chain logic) without a live A/B and a read of `GRAVEYARD.md`.
- **Snoopy is OFF** (the user offers to turn it on if it would help).
- **New tasks and questions found mid-work go on the LATER list; do not dispatch them** (the user repeated this 09-24).
- **Pure code smells: list them for the user; fix only what has a measurable cost** (time, flakes, wrong behaviour) (user, 09-24).
- **Live-turn-path speed fixes need an interleaved live A/B (≥10 matches/arm) before merge** (user, 09-24).
- Sleep the console and disconnect the stream when idle.
- Manager delegates routine work. Opus skeptics on money paths. Merges on Haiku; conflicts go to Sonnet. Refuted work goes to a fresh fixer. STOP after the 3rd refutation of the same issue.
- Restart the manager after every 4th merge, 8th sub-agent report, or the first compaction. (This session ran past that at the user's choice, overnight.)
- **Parallel jobs:** 2 on weekdays 08-18, 8-10 at night, all 12 when the user frees the Mac; 1 while live. Never serial sweeps. Keep full sibling sweeps.
- `--no-verify` is allowed only when the sole hook failure is the missing gitignored `demos/`. Better: copy `demos/` into the worktree.
- Permanent deletion is not allowed for Claude: move files to the Trash.
- **Publishing: the user approves every push, and runs it** (§5). Before any push, check for secrets and desktop captures.
- Label artifact URLs: I `https://claude.ai/artifact/9MsSvsvvJcwsLgyb7sqDXG` · II `https://claude.ai/artifact/LV1ZvDaBr1aYaNQM3KKaQP` · III `https://claude.ai/artifact/KSgyELyD6UQS6Uuc8y2v9T` · IV `https://claude.ai/artifact/7PnTHz5Lb2dWTCQDvRnBnU` · V `https://claude.ai/artifact/KrjZ6LZzJ6sLzMQnEvoZJ4` (truth: `test_fixtures/user_truth/20260923_i70_setV/labels.json`).
