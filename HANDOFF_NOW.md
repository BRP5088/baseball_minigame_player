# HANDOFF — 2026-09-21, 02:00 EDT stop

## 1. READ THIS FIRST: console / money state

**NO MATCH IN PROGRESS.** `progress_testing.json`: 46W 12L 5D, balance 146,
`match_in_progress: false`, `bans_done_this_match: true` (verified: `cat
progress_testing.json`, this session).

**Nothing has reached the console since WIN #46 logged at 01:37** (last line of
`overnight/run_live_20260921f.log` before the spend-cap stop). Expect it
**ASLEEP**. Confirm with the three tells in CLAUDE.md §1 before any press —
`game_capture.grab()` size, `ensure_stream.looks_like_ui()`,
`ensure_stream.streaming()` — and if it reads asleep, **do nothing**.

**NEVER save the game.** Resets and `Load Last Save` only (memory:
never-save-the-game.md).

This is an OFFLINE stop-procedure write-up: no presses were sent, no screen
was captured, no run was started while producing this file.

## 2. What was merged tonight, and what the two live matches showed

Merges/fixes on `main` since `a3419d0` (this session, filtered from `git log`):

- `3b7c77f`/`3ef4447` — I-30 test follow-up (`_clear_strays` accepts I-28's `ys0`)
- `e6fbcce` — **Merge I-30**: whole-word result reads; `close_result` only after
  a fresh result read; two-frame confirm at the play floor; give-up dialog
  answered NO, never Cross
- `f8dfa34`/`49af1ca` — I-30 follow-ups (pin the fresh-check gate; phantom-draw
  fixture)
- `13a4f6a`/`dc47548` — QA round 4 (census wording, false-cursor exclusion bound)
- `1abeb4e` — ISSUES.md: I-29 added/merged
- `3149e8e`/`db96589` — **Merge I-28**: stray guard exempts the engine's own
  target when it was readable at baseline and went blind after the press
- `aed2468` — I-28 follow-up: narrow want-blind inference to I-21's own shape
- `ed7e4ab`/`1babf0c` — **Merge I-29**: forget a spent hand slot's stall
  identity on confirm, not on value change
- `7b27ca6`/`41dd459` — **QA round 5**: give-up test reads the frame, not its
  own press flag
- `39d0eb8`/`e23e0f6` — **Merge I-31**: tactics kinds (swing/speed=batting,
  pitch/fielding=pitching) vote on the phase; the match's own half is the
  fallback when `read_phase` abstains on a readable hand
- `4f5da6f` — redraw log names the incomplete-hand guard (was "strong enough"
  at best 5 < 6)
- `61b5d2a`/`a5e212a` — **Merge I-32**: `_walk_cursor_to` dead-reckons ONE step
  across a known-occluded slot (`ys[expected] is None`) instead of refusing
  the whole hand; bounded to one consecutive dead-reckoned step; never
  dead-reckons onto the target itself
- `ccdd46b` — I-32: fold skeptic's two coverage-gap tests (leftward walk, two
  occlusions in a row) into the shipped test file

**WIN #45 — the parked I-32 match, resumed on main.** `overnight/run_live_20260921e.log`
(verified by grep): the walk hit the same occluded slot 1 that had caused the
00:52-00:56 stall (`run_live_20260921d.log`, three "every reachable card on
this hand has been refused" stops) — this time logging `slot 1 is occluded (y
unmeasured) — its glow cannot read; dead-reckoning one step across it`, then
`verified on 4 after 4 press(es)`. Zero refusals. `WIN #45 logged. 954 to go.`
Run then hit `Spend cap reached ($0/$0 spent this session)` (a resume, no new
match bought) and stopped clean. This is I-32's first live exercise and it
worked as designed.

**WIN #46 — a fresh match, `run_live_20260921f.log` (max_spend=50).** Walk +
bans + full match on `main`. Two things worth carrying forward:

- I-02's probe-select answered YES live for the first time:
  `[cursor] probe-select: 4 lifted — the cursor was there`, and the play
  committed (`verified on 4 after 6 press(es)`). Slot 4 is confirmed reachable
  as a target through the probe path.
- One refusal, recovered on the next attempt. Pitching half: a card was played
  and verified (`ours 8, theirs 4` in the reveal), then one press toward slot
  0 for the pitch boost read `lost the cursor (glow=[0.0, 0.4, 0.0, 0.0, 0.4])`
  and the walker unwound and refused (`run_live_20260921f.log:112`). Slot 4 is
  structurally blind by glow (10.35 in CLAUDE.md), so a dropped press leaving
  it reads exactly like a lost cursor — this is NOT an I-32 defect, it's a
  gap I-32 doesn't cover (the blind slot here is the walk's *start*, not a
  slot it's crossing). Candidate rule for next session, not built: when a
  press leaves a structurally-blind slot (4) and the next look reads None,
  press once more before refusing, since a dropped press there is
  indistinguishable from a landed one.

Run stopped clean at `Spend cap reached ($50/$50 spent this session)` after
`WIN #46 logged. 953 to go.` Suite after both matches: **all green, 271 files,
314s** (`overnight/suite_20260921_0140.log`, verified: `tail -3`). `main` HEAD
is `ccdd46b`.

**NOT independently verified this session:** the outgoing notes state the
auto-mode classifier declined a third paid-match start at ~01:38 as a
real-money-transaction guard, after two starts had been allowed. I could not
find any trace of this in `run_live_20260921f.log` or any other file on disk
— that log's only stop is the ordinary `$50/$50` spend-cap message, which is
consistent with exactly one match being bought in that run. If this refers to
a decision made in the tool-permission layer above the game loop rather than
anything the game loop itself logs, there's nothing in this repo that would
show it either way. Treat it as reported by the outgoing session, not
confirmed here.

## 3. In flight / NOT merged: I-05a

Second attempt, worktree `.claude/worktrees/agent-a7613eff370917779`, branch
`worktree-agent-a7613eff370917779`, commits `2b426fa` ("verify the PS5 overlay
dismiss, and gate run() on liveness") + `3731b5e` ("widen the liveness reader
set, debounce ambiguous misses"). Both commits confirmed to exist and to sit
on that worktree's HEAD.

The first I-05a attempt was refuted (reader set omitted `read_result`/
`read_ban_counter`/`read_hand` — would have toggled the overlay mid-match).
This redo uses the full reader set plus a 3-consecutive-miss debounce before
`ensure_live()` fires.

**Skeptic verdict: CONFIRMED WITH NOTES, NOT MERGED.** Full notes at
`.claude/worktrees/agent-a7613eff370917779/agent_progress/issues/I-05a-skeptic/progress.md`
(read in full this session). The closed half: the first attempt's hazard
(false "not the game" on genuine frames) does not reproduce — a 659-fixture
sweep at 1920x1080 found 0 false negatives, `_game_visible` alone (with
`looks_like_ui` contributing nothing) answers on 96.5% of fixtures, and the
one real PS5 game-card overlay on disk (`agent_progress/still_overlay.png`) is
correctly rejected. The dismiss press itself (`ensure_stream.py:492` ->
`_dismiss_overlay_if_blocking`, at most two `ps_button` presses, a fresh
capture + `_game_visible` check after each) is verified.

**Three holes, from the skeptic's notes, verbatim in substance:**

1. `LIVENESS_MISS_STREAK = 3` is invented and its own comment's arithmetic is
   wrong: `orchestrator.py` ~8404, a moving screen `continue`s with **no
   sleep** (`settle_pause` 0.12s), so three consecutive misses can span under
   a second *during an animation* — exactly when misses are expected. Fix:
   measure the streak in TIME (misses on polls ≥N s apart), or measure the
   real population of consecutive-miss lengths on archived deal/reveal frames
   first (CLAUDE.md §10.4).
2. Two mutants survived out of five: **M2** — the streak never resets on a
   hit (turns a 3-consecutive-miss debounce into a 3-lifetime-miss trigger,
   unpinned). **M5** — `ensure_live()`'s False return is ignored (the
   existing test only asserts the call count, not that a failed recovery is
   noticed). Both need tests before merge.
3. `_game_visible` cannot tell "no reader answered" from "every reader
   crashed" — all nine readers sit in bare `try/except: pass`. If a broken
   numpy/cv2/tesseract makes every one raise, `_game_visible` returns False on
   every frame, indistinguishable from a real overlay: two blind `ps_button`
   presses at a live match, run stopped. Fix: count readers that actually
   executed; return True (don't fire) when that count is zero.

## 4. Open items for next session, in order

1. **I-05a**: fix the three holes above (time-based or measured streak;
   pin M2 and M5; zero-readers-executed fallback), get a fresh skeptic pass,
   merge.
2. **Candidate rule from WIN #46's one refusal**: at a structurally-blind slot
   (4), a press-then-None reads the same whether the press landed or was
   dropped — retry once before refusing. Not built; needs its own harness
   test (bounded, cheap per the notes above).
3. **I-04**: DRAW fixture still needs a live draw to capture.
4. **P2 simulator A/Bs**: I-15, I-16, I-17 — none started.

Also note: the auto-mode classifier apparently declined a third paid-match
start tonight (see §2's caveat) — worth asking the user about directly rather
than assuming a mechanism, since it isn't visible in any log here.

## 5. How to resume

1. The three tells (CLAUDE.md §1) — confirm the console's actual state before
   any press. If asleep, that's fine; leave it.
2. To play: `.venv/bin/python` (or an interactive session) calling
   `orchestrator.run(target_wins=999, progress_file='progress_testing.json',
   max_spend=50, compare_local_reads=True, log_screenshots=True)`, logging to
   a NEW `overnight/run_live_<date><letter>.log` (do not reuse `f`).
3. Suite: `PATH="$PWD/.venv/bin:$PATH" ./run_tests.sh` (or `.venv/bin/python -B
   tools/doctor.py` first if it's been more than a few hours since the last
   console check).
4. Read-only look without moving anything:
   `.venv/bin/python -B tools/match_crawl.py --session new --action look`.
