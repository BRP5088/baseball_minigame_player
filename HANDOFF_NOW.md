# HANDOFF — 2026-09-21, end of session 2

## 1. STATE RIGHT NOW

- `main` HEAD **`214650e`**.
- Record (`progress_testing.json`): **71W 14L 8D**, balance **46**,
  `match_in_progress: false`, `bans_done_this_match: true`. The `true` flag is
  **harmless** — nothing is mid-match, it's left from the last match and the
  next reset clears it (preflight only keys on `match_in_progress`).
- Console: left at the **dealer table**, **$46 in-game** (matches the tracked
  balance). **Not put to sleep** — it auto-sleeps on its own when nothing
  reaches it (CLAUDE.md §1); confirm with the three tells before any press.
  `ensure_live()` started chiaki and woke the PS5 this session (86 s).
- **Snoopy is ON and idle.** Port is rediscovered per job (changes with model
  load — re-check via `/props`, don't reuse a cached port). **The VLM is
  useless for scene-state questions, text only**: `reveal_timing` scored it
  "no reveal" on 70% of KNOWN-GOOD controls (21.6% agreement) — never wire it
  into anything that decides what's on screen, only OCR-shaped text reads.
- **Paid vision model is OFF** (`orchestrator.PAID_MODEL_ENABLED = False`, as always).
- **No agent is running.** Nothing in flight.

## 2. TODAY'S RESULT

**16-match stall census, cycles 4–7, on `main` with every fix from today
merged as it landed:**

    cycles 4-6 (pre-I-48, runs 21p/21q/21r)   10 W, 1 L, 1 unverified D
    cycle 7    (post-I-48, run 21s)            4 W, 0 L, 0 D  -- WIN #68-71, 4/4
    -----------------------------------------------------------------------
    TOTAL      14 W, 1 L, 1 unverified D over 16 matches

    refusals: 9 total (6 in one hand, pre-I-48; 2 in cycle 7, one per match,
              each cleared on the NEXT poll)
    hand-assisted stalls: 0        runs ended by a human: 0

**Before/after I-48, the number that mattered — refusal cost per stall:**

    before (cycle 6, pre-I-48)   6 refusals in ONE hand, ~5 minutes to clear,
                                 the loop stumbling onto a batter whose walk
                                 happened to avoid the occluded slot
    after  (cycle 7, post-I-48)  2 refusals total, ~25 s each, cleared on the
                                 very next poll (fallback drops the tactics
                                 attachment and plays the batter alone)

**Cycle 7 detail (run 21s, main `b96f0f1` — before I-44 N-2/case-D/spend_and_play
landed on top of it):** 4/4 wins, 2 refusals (both recovered on the next poll,
~25 s each — match 2 the I-48 fallback fired with the batter not yet lifted;
match 4 a blind cursor on a fully readable hand, probe-select x2), 1 fallback
event (first ever live), 0 never-landed-after-5, 8 reveal misses, 0 unscored
rows (I-49 never triggered — no staged row was dropped this cycle), 0
physically-lifted lines (I-43 clean), 1 ban shortfall (1 of 3 bans registered,
match 2), 51 unreadable-screen retries. Two `refused_select_*` frames kept.

## 3. WHAT MERGED THIS SESSION

- **I-48** A failed TACTICS select was burning every batter in turn before the
  loop stumbled onto a workable one. Fix: on a tactics-only failure, drop the
  attachment and commit the batter alone instead of unwinding everything.
  Merged `db3bfcb` (skeptic: **Opus, CONFIRMED WITH NOTES** — census over 506
  decision blocks found 0 boost loss from the fallback itself, but flagged
  S-2 a guard true when `card_index` is `None`, S-3 a REAL bug — the fallback
  still logged the boost that never went in, S-4 case D passing when capture
  raises). Round 2 `2c6cca5` fixed S-2/S-3/S-4 (S-3 via
  `tactics_dropped_last_play()` flag zeroing the fields and setting
  `tactics_dropped: true`), **7/7 mutants caught**. Test-file reconciliation
  `307408c`/`b96f0f1` (the old full-refuse test pinned the wrong contract on 3
  scenarios). `c7ed3f4` fixed case D reading the LIVE `diagnostics/deal_frames`
  dir instead of a temp root (QA8-adjacent). `214650e` fixed the last gap:
  `spend_and_play` (the `tools/match_crawl.py` entry point) never read the
  drop flag and printed "COMMITTED" on a batter-alone fallback (QA8 finding,
  see below).
- **I-49** A readable reveal's row was staged, then discarded outright by a
  later poll's failure (21 of 36 traced orphans). Fix: append the staged row
  with `row_status: "unscored"` instead of dropping it. Merged `0a62bbf`
  (skeptic: **Sonnet, CONFIRMED WITH NOTES** — no stale `pending_matchup`
  across a match boundary, fabricated-outcome mutant caught by three tests,
  consumers verified live: rates use scored rows only, distribution uses all).
- **I-44 N-2** `_clear_strays`'s corroboration gate now has a named,
  test-covered branch (`_baseline_readable`) for the case QA6 Q2 flagged.
  Merged `69e77a4` (baseline mutant caught). **Narrow, and says so**: the
  hard case (a dropped press plus a coincidentally-blind post-press read that
  still commits a false inference) reproduces unmodified on 0/28 archived
  events and is **still open** — it can't be closed inside
  `input_controller`, it needs corroboration the inference itself can't
  manufacture. Stays a LATER item.
- **QA8** (round over `f9f9ede..758f2ed`): silent-paths/state finder — 1
  CONFIRMED low finding (`spend_and_play`, fixed in `214650e`), everything
  else checked and found correct (tactics-dropped flag resets cleanly, no
  reveal-frame dangling, no keeper race, N-2 is a pure refactor). Test-quality
  finder — clean, 7 files, 8/8 mutants caught, no live-dir globs, no bare
  bools. Round came back dry after the one fix → stopped.

## 4. HOW TO RUN THE NEXT CYCLE

Before launching: `ensure_stream.ensure_live()`, then **read the frame by
eye** and confirm the GAME is actually on screen (an `ensure_live` success
does not by itself mean the game is up — CLAUDE.md §3). Then:

```
BASEBALL_API_BUDGET=300 nohup .venv/bin/python -B -u -c "import run_cycles; print(run_cycles.cycle(8))" > overnight/run_live_20260921t.log 2>&1 &
```

(next log letter after `s` is `t`; if the date has rolled past midnight before
you launch, start over at `overnight/run_live_20260922a.log`.)

Monitor for milestones with:

```
grep -E "logged|WIN #|LOSS #|Draw logged|REFUSED|playing the batter alone|DROPPED|may still be physically lifted|Traceback|stop_reason" overnight/run_live_20260921t.log
```

(the two new terms are I-48's fallback lines — watch them alongside the old
ones.)

Between cycles, or at handoff: `.venv/bin/python -B tools/questions_sheet.py --since <last handoff's ns or ISO time>` (I-59) writes a contact sheet + `questions.md`/`questions.json` of every refused-select/dropped-slot frame since then to `diagnostics/questions/<stamp>/` for the user to answer whenever they get to it.

## 5. LATER (do not start without the user)

Carried from before, plus what today's cycle 7 and QA8 round surfaced.
~~Struck~~ items closed this session, with what closed them:

- ~~I-48 candidate (match-3 stall on cycle 6)~~ **DONE** — fixed and merged,
  see §3. Live-confirmed in cycle 7 (2 refusals, ~25 s each, vs the old 6/hand).
- ~~Reveal watcher: wait for the 2+2 cards to separate before keeping the
  frame~~ **REFUTED** by the `reveal_timing` census (facts file): class-A
  (readable) captures land at 2.6–2.8 s, well inside the window — the misses
  are **late** captures (class B/D at 4.0–4.4 s, past `REVEAL_SETTLE_MAX_SEC`
  2.5 s) and dropped rows, not early ones. Don't build a "wait for
  separation" gate; see the `REVEAL_SETTLE_MAX_SEC` item below instead.
- **I-48b (new):** the fallback fires *before* the batter is confirmed
  lifted, so `_clear_strays` refuses on top of it ("engine's cards [2] are
  not all lifted"). The premise "batter already succeeded" isn't enforced by
  ordering. Fix direction: order the batter select first, or when the
  tactics target fails and the batter isn't yet lifted, go on to lift/confirm
  it instead of refusing outright. Frame:
  `diagnostics/deal_frames/refused_select_1790025302210541000`.
- **Cycle 7 match 4: blind cursor on a fully readable hand** — target slot 3
  went straight to probe-select (the I-02 blind-target path) with no
  apparent reason (hand was `[fielding+1, 5/1, 5/1, 9/2, 6/0]`, all rows
  read). Open question: glow gate, or cursor parked on the just-played slot?
  Frame kept: `diagnostics/deal_frames/refused_select_1790026023456048000`.
- **I-48 tactics slot not excluded after a fallback** — after the boost is
  dropped, the loop keeps re-attempting the same tactics slot on later turns,
  costing ~11 s/turn (a tax, not a deadlock, but worth excluding once dropped
  for the rest of the hand).
- **I-44's hard case is still OPEN** (see §3) — needs per-row digit
  corroboration from orchestrator, or a post-commit detector; can't be closed
  inside `input_controller`.
- **`REVEAL_SETTLE_MAX_SEC` lengthening** — class B/D reveal frames (29% of
  the orphan population) are captured at 4.0–4.4 s, past the current 2.5 s
  ceiling. Raising it should recover them; score against the next cycles'
  orphan rate.
- **15/36 never-staged reveal misses** — the remaining reader question after
  I-49: 10 "no OPPONENT card identified" (`:10238`), 5 local misfire flag
  (`:10214`). Unlike the 21/36 staged-then-dropped (now fixed by I-49), these
  never got far enough to stage a row at all.
- **Ban shortfall** — cycle 7 match 2 registered only 1 of 3 bans (`ban_nav`).
  Not investigated; watch for a repeat.
- **The transition-timeout drop site (`orchestrator.py` ~`:9091`) still
  discards** — 0/42 orphans traced through it this session, but it's an
  unfixed drop path structurally identical to what I-49 just fixed elsewhere.
- I-46 wide window: decide narrow (17/23) vs wide (22/23) from the skeptic's
  false-read table; widen only at zero false reads.
- I-35 live verification: `new_inning` / `reveal_recap` branches have still
  never fired live; confirm on the next matches' logs.
- I-42 labels: `FLICKER_WINDOW=10` is from the ticket text, not measured;
  9/53 good labels wrongly rejected. Measure if the label corpus is ever
  needed at scale.
- Full hand corpus re-check after I-46 merges (the 540-hand corpus, not just
  the 2,409 turn frames).
- Raised-card disc: 6/23 census frames still unread (5 jitter, 1 obscured) —
  covered by the wide-window decision above.
- The narrow I-46 window makes every slot it reads SELECTED by construction
  (dy above `SELECTED_MIN_RISE` 25); fine today (32/34 were `y_from`
  fallback), worth a line if `selected_cards` ever misfires.
- Log the evidence (template scores + OCR words + scoreboard) on every
  result commit and keep the result frame — the reveal/money keepers exist,
  the result screen has none. This is what would settle draw #8.
- Exclude LOCKED cards from the simulator pool and from `choose_bans`
  (RULES.md, user 2026-09-21). Ownership is readable per cell from the ban
  scan the run already does (`ban_grid.is_locked`, 3.5x contrast gap);
  persist it beside the roster and thread it into `simulate`'s `player_pool`
  and `decision_engine.choose_bans`. Then re-run the I-13 ban A/B on the
  31-card pool.
- **Worktree cleanup** — `.claude/worktrees/` is ~67 GB across 54 worktrees;
  every branch there is merged into `main` as of this session. User's call
  to run `git worktree remove` / `git branch -d` on the merged ones — check
  `git status` in each first, don't touch anything with uncommitted work.

### Snoopy jobs (one at a time; VLM text reading and grunt work only)
- Label the kept reveal frames (test_fixtures/reveal_kind_truth/auto/): opponent card name + power per frame -> ground truth for the reveal-miss rate and for reveal_cards.TACTICS_KIND_MIN (OPEN-24).
- ~~Second-opinion the 34 I-46 raised-card digits~~ DROPPED after job 1: the VLM misreads small digits the local reader gets right.
- Mutation sweeps for I-48 once built, if the console is live (Snoopy_testing.md) — I-48 is now built and merged; this can run.
- I-30 coverage gap (from an earlier skeptic, resurfaced 2026-09-21): deleting the fresh-read check in `orchestrator._close_result_safely` passes all 12 named tests. Verify whether a later commit closed it; if not, add a test that scripts `_result_screen_up` to go False right before the press and assert no press.
Not Snoopy: reveal-miss baseline count, FLICKER_WINDOW sweep, raised-disc jitter -- local scripts, seconds.

### Snoopy job 1 DONE (reveal frames, agent_progress/census/reveal_vlm/)
- 153 kept reveal frames; only 82 have a match_log row. VLM vs match_log (n=82): our_power 83%, opp_power 91%, tactics kind 77% — worse than the local reader on digits, confirming the VLM-for-digits idea is dead.
- WHAT THE MISSES ARE (13 tiles by eye): 3/13 kept "peak" frame is the next turn's hand fan; 10/13 a 4-card cluster still bunched at the mound, home plate empty. Superseded by the fuller `reveal_orphans_trace` census this session (see §3 I-49 and the LATER items above) — the mechanism is now traced to staged-then-dropped rows and late captures, not just capture timing.

### Snoopy job 2 DONE (roster typing, agent_progress/census/roster_type_vlm/)
- Brian Coker (8/1) and Zachary Lee (6/2) are BOTH BATTERS, both LOCKED (not owned) in this save. Applied `5afe7e0` after user confirmation; `test_card_roles` re-derived `dc6ac98`.

## 6. OPEN QUESTIONS

- Does a speed boost PERSIST on base? Two live runners read +1 over their
  card (CLAUDE.md §4); worth one at-bat with a boosted batter then a later
  hit. Low stakes (+0.046 runs/half).
- Does the raised-card position search ever read a NEIGHBOUR's disc live?
  Skeptic measures offline; the live check is one hand with the target in
  slot 4 and a 9 in slot 3.
- Is the 8% raised-disc miss the dominant cause of I-21 inference commits?
  Count, over the next 10 matches, plays where the target read blind at
  commit before vs after I-46.
- Why do 5 of 23 raised digits land outside the narrow window (jitter): is
  the disc position on a raised card a function of the lift height
  (selection lift ~44 px) or of the fan phase? Measure dy vs SELECTED lift
  per frame from the census json.
- Do new_inning / reveal_recap ever appear on the live path, and how long do
  they hold? No live sighting yet through cycle 7; the next matches' logs
  answer it.
- Are the 9/53 good lift-labels rejected by I-42 a flicker-window size
  effect? Sweep `FLICKER_WINDOW` 4..20 on `joined.jsonl` and report
  kept/rejected by class.
- **Was draw #8 (cycle 6, match 2) real?** Still unanswered — no result-commit
  evidence logging exists yet (see the LATER item), and nothing since has
  produced a comparable frame to check offline.
- **Why 11–15 reveal misses per cycle ("no OPPONENT card identified")?**
  **PARTLY ANSWERED** this session by the `reveal_orphans_trace` census: of
  36 traced class-A (readable) orphans, 21/36 were staged and then dropped by
  a later poll's failure (now fixed — I-49 appends them as `unscored` instead
  of discarding), and 15/36 were never staged at all (10 no-opponent-card,
  5 local-misfire-flag — still open, see LATER). Separately, `reveal_timing`
  found 29% of the orphan population is captured LATE, past
  `REVEAL_SETTLE_MAX_SEC` — also a LATER item. So the miss count itself isn't
  one cause; it's three, and two of the three now have a fix in flight or
  merged.
- ~~Locked cards in the pool?~~ ANSWERED (RULES.md, user 2026-09-21): locked
  cards are never dealt and can't be selected as a ban, so the draw pool is
  31, not 33; wiring that into simulate/choose_bans is the §5 LATER item.

## 7. RULES IN FORCE

- **User rule, 2026-09-21 ~13:30: any NEW task or question found from here
  goes on the LATER list — do not dispatch it to an agent.**
- Manager delegates routine work (merges, tests, doc edits, log reading) to
  Sonnet agents; the main model decides and dispatches.
- Snoopy: one job at a time, grunt-work/labelling only, never wired into the
  live ladder. **The VLM reads text only — never scene state** (facts file,
  `reveal_timing`: 70% wrong on known-good controls when asked "is there a
  reveal here").
- **Never save the game** — resets and `Load Last Save` only.
- **Play the engine's pick, fix the engine** — never hand-override a card
  choice; when a read looks wrong, check the reader first.
- **Ask before pushing, opening a PR, or posting anywhere shared** — draft,
  show, wait for a yes.

## 8. LIVE WATCH ITEMS for the next cycle

- **"playing the batter alone" count, and whether the batter was lifted when
  it fired.** I-48's fallback line. Cycle 7 saw it once, with the batter NOT
  yet lifted (I-48b, above) — watch whether that's the common case or a
  fluke.
- **Unscored rows appearing in `match_log.jsonl`.** I-49's new `row_status:
  "unscored"` path — never fired in cycle 7 (0 rows). Watch for the first
  live instance and check the drop reason it records.
- **The I-43 "may still be physically lifted" count — still 0** through
  cycle 7 (archive bound: 14 exemption events vs 51 refusals). More than a
  handful on the next cycle means the single-frame `ys0` gate is admitting
  transient blinds.
