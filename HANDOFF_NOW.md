# HANDOFF — 2026-09-22, session 2 close-out (updated ~01:00)

## 1. STATE RIGHT NOW

- `main` HEAD **`49d18db`** was the build cycles 19–26 launched on. Neither
  **I-56** (`c0953b8`, READY) nor **I-62** (`worktree-I62`, unmerged) is on
  `main` as of this writing — both are queued to merge in the gap after
  cycle 19.
- **Cycles 19–26 are CHAINED AND RUNNING as this is written** (one Python loop
  calling `run_cycles.cycle(n)` for n=19..26, stops on `reset_failed` or an
  exception): `overnight/run_live_20260922e.log`, monitor id `b3p1mc61u`
  (expires 30 min after being armed — re-arm if you land after it lapses).
  **The log is the record** — read its tail for the live tally before trusting
  any number below.
- **Cycle 19 so far, on `49d18db`**: WIN #101, WIN #102, WIN #103 — 0 issue
  lines across all three (strict streak reached 3). Match 4 then had a play
  **REFUSED in the I-56 shape** (target slot 1 selected on attempt 2 after a
  dropped press; tactics neighbour slot 2 read unreadable
  `[201,114,None,166,211]` twice → refused; frames
  `diagnostics/deal_frames/refused_select_1790052649835023000` and
  `dropped_1790052651118893000`) — **strict streak reset 3→0**, unmerged
  I-56 would have covered exactly this. Record climbing from the pre-cycle-19
  100W 15L 11D.
- <<CLOSE: I-56 merge outcome + cycle 19 close + relaunch sha>>
- **I-56** round 3 fix is READY at `c0953b8` (M3d/`_mark_candidates` and
  MY-M3/`_new_blind`'s cannot-read-fan path both guarded, 13 files green;
  note: `_deselect_verified` always dirties the ledger on a real press —
  recorded in ISSUES.md, not a blocker — see §5). Merge agent is waiting for
  the cycle-19 gap (`gap19.txt` GAP_MADE) to merge --no-ff, run the battery
  (the probe-select budget test from a scratch copy, not the live checkout —
  see §5), a spot mutant, update ISSUES.md, then an un-niced full suite.
  Cycles 20–26 relaunch on the merged build once that's green.
- **I-62** (accept a disc at the lifted position in slot assignment): branch
  `worktree-I62` at `c1fcebc` + `ccdecb8`, **UNMERGED, no skeptic yet** — first
  item for the morning, see §5.
- Two read-only QA finders (over `204bb5b..49d18db`, silent-paths/guards +
  test quality) both reported back — findings folded into §5, nothing
  merge-blocking.
- **INCIDENT**: `tools/questions_sheet.py` (committed `d5f9ed0`) was found
  deleted from the main working tree mid-session (a bare ` D` in
  `git status`); restored with `git checkout -- tools/questions_sheet.py`
  (only that path touched, live data files untouched). Culprit **not
  established** — see §6.
- Console: mid the cycle 19–26 chain. Confirm the three tells (CLAUDE.md §1)
  before any manual press if you take over mid-chain.
- User, 00:5x: Snoopy OFF; *"finish the cycles left ... all current todos;
  anything new is added to future sessions todo list"* — no new dispatches
  after that point; overnight unattended chaining is the stated default. User,
  01:0x: sleep the console when not in live use — tonight the cycle chain IS
  live use, and when it ends the console auto-sleeps on its own (nothing
  reaches it); see `console_rest_mode_procedure.md` if it ever needs putting
  down by hand instead.
- Paid vision model OFF (`orchestrator.PAID_MODEL_ENABLED = False`). Never
  save the game — resets / `Load Last Save` only.

## 2. RESULT / STREAK

**Bar** (user, escalated twice tonight): first *"30 matches in a row without
any issues = rock solid"* (18:3x), then *"bar raised to 50 CONSECUTIVE PERFECT
MATCHES (no stalls, no issues; losses and draws are fine)"* (23:0x).

**Strict streak rule** (user, 18:4x, verbatim): *"Any stalls, any issues
count. Things need to be run perfectly like a nuclear power plant."* A clean
match = zero refusals of any kind, zero retries that cost a poll, zero ban
shortfalls, zero unverified results. Losses/draws don't break it; any
stall/issue does. **Streak resets whenever a fix merges** — it is scored
against frozen code only, never carried across a build change.

### Per-cycle table, cycles 9–18 (all `overnight/run_live_20260921{u..y,z},20260922{a..d}.log`)

| Cycle | `run_live_...` | main build | Matches | What broke the streak | Streak after |
|---|---|---|---|---|---|
| 9 | 21u | `ff2d69f` (+I-50/48b/53/51/54/48e) | WIN74 (discard-unconf, landed next poll), WIN75 (clean), DRAW9 (**no evidence line**, +2nd discard-unconf), WIN76 (clean) | discard-unconfirmed x2; evidence-less draw | 1 (m4) |
| 10 | 21v | `a99bc6e` (+I-52) | LOSS15, WIN77, WIN78, WIN79 — **ALL 4 CLEAN** | — | 5 (c9m4+c10) |
| 11 | 21w | `a99bc6e` | WIN80–83 — **ALL 4 CLEAN** | — | 9 |
| 12 | 21x | `a99bc6e` | WIN84 (clean); WIN85 (I-56-shape: tactics select unreadable behind lifted batter neighbour → boost dropped; +half-boundary refusal, recovered); WIN86 (I-52 resolver's first live firing was a **false** "genuine stray" → 3 I-43 refusals → worse card played, ~75s); WIN87 (clean) | boost dropped; false stray mark | broken at 10 (m2), ends 1 (m4) |
| 13 | 21y | `204bb5b` (+I-55) | WIN88 (**3rd I-56 occurrence**: boost dropped + false "lifted them" mark → REFUSED); WIN89/90/91 (clean, first live I-55 evidence lines: winner 0.985/0.983/0.981) | I-56 shape | reset 0→3 |
| 14 | 21z | `204bb5b` | **STALLED before any match** — pause-menu close press dropped, 15 unreadable polls, run stopped, no money spent → I-58 filed | pause-menu close drop | cycle-level stall (no match) |
| 15 | (same log continued) | `204bb5b` | **SAME STALL again** (2nd in a row, p≈3.8% under §5 clustering) | pause-menu close drop | cycle-level stall |
| 16 | 20260922b | `204bb5b` | WIN92/93 (clean, streak reached 5); WIN94/m3 (I-57-shape: walk stalled one hop short of an 8-press cap → boost dropped); m4 **ABORTED BY THE RIG** — chiaki died mid-match, rig not engine, $50 recovered by next reset, unscored | boost dropped; rig death | 0 |
| 17 | 20260922c | `204bb5b` | WIN95 (clean, 1); WIN96 (clean, 2); DRAW10 (clean, first draw **with** evidence: draw 0.981/winner 0.660/loser 0.490, OCR 'DRAW!', 3); WIN97 (I-48f refusal, recovered) | I-48f | reset 0 |
| 18 | 20260922d | `204bb5b` | WIN98 (clean,1); WIN99 (clean,2); DRAW11 (**I-56-family** discard refusal — neighbour blind beside the walk target,0); WIN100 (clean) | I-56 family | 1 (m4) |

**Record after each cycle** (all from `progress_testing.json` snapshots quoted
in facts2.md): c9 76W14L9D → c10 79W15L9D → c11 83W15L9D → c12 87W15L9D →
c13 91W15L9D → c16 94W15L10D → c17 97W15L10D → **c18 100W15L11D**.

**Every streak break across cycles 9–18 traces to one of two families**: the
I-56 shape (a tactics/wreath read fails beside a lifted neighbour or after a
walk crosses an occlusion — cycles 12, 13, 18) or a press-drop cluster hitting
a walk/press budget (I-57 shape — cycles 12, 16) or a rig/OS event (cycle 16
m4, chiaki died). Ban shortfalls and evidence-less results, the two other big
families from cycles 4–8, are **gone** — I-50 (bans) and I-55 (evidence) both
show zero recurrences once merged (cycles 9–18 ban tally: 4/4 cycles at 3/3
bans from cycle 9 on, per the guard census).

## 3. MEASUREMENTS THAT SETTLED QUESTIONS TONIGHT

| Question | Answer | n / source |
|---|---|---|
| Is "cards dancing around" real card drift? | **REFUTED.** Only motion in a settled plateau is the selection lift (42–43px, eased ~5 frames) plus deal/select transients. | 9,290 frames, 2 runs @10Hz, 56 settled plateaus, 295 within-plateau samples: x/y amplitude p50 1px, p95 3px, max 6px (vs SLOT_TOL 34). `agent_progress/issues/card-drift/` |
| Does a lifted card's disc go blind *because it's lifted*? | **NO**, live-verified. Disc stays crisp at rest, mid-lift (~400–500ms), and lifted (dy −41). | Archive: 14/14 lifts disc-readable on every frame (`agent_progress/issues/lift-transition/`). Live probe: **0/187 frames unreadable**, 10.3fps, 3 select/deselect events (`agent_progress/issues/lift-live-probe2/`). |
| What actually caused the probe's drops then? | **Press delivery**, not the reader: of 6 presses across 3 slots, **3 dropped** — slot 1 both presses no-ops, slot 4 first press dropped and the retry (meant as deselect) instead *selected* it (a toggle trap), slot 2 clean. | Same live probe, `agent_progress/issues/lift-live-probe2/`. |
| Is I-21 (select-time inference) safe to keep? | **YES — do not remove it.** 32 firings over 34 run logs: **28 committed and correct** (26 confirmed by the next hand read, 2 by reveal+WIN), 0 wrong, 4 refusals (3 pre-I-28 bug, 1 the I-48f case). Removing it would turn ~28 clean commits into refusals. | `agent_progress/issues/i21-census/` |
| So why do 32 real "went blind after a select press" events happen in production if lifting itself doesn't blind the disc? | **OPEN — unresolved contradiction, recorded not guessed at.** The I-21 census agent's own claim ("a lifted card's disc stays blind while lifted") is *unmeasured*, sourced from code comments; the live probe and the archive both refute it directly (disc reads fine lifted). Both facts can coexist: production reads *do* go blind after some select presses, but the lift itself is not the cause. Candidate mechanisms, neither measured: cursor glow interference on the just-selected card, or a ~0.6s settle-timing gap in the read. **This is the standing open question for next session — see §6.** | `agent_progress/issues/i21-census/` vs `agent_progress/issues/lift-live-probe2/` |
| What's actually in the `dropped_*` population (400 dirs)? | 299/412 slot reads are genuinely blind on disk: 160 nothing in the slot (occlusion), 69 player + 59 tactics "position found but no disc within SLOT_TOL", 11 banner-only, 50 deal-in-flight. → fed the I-62 fix (accept a disc at the lifted position, `RAISED_SEARCH_DY`, in slot assignment — see §1/§5/§6). | `agent_progress/issues/i21-census/` |
| Were the 5 full-suite failures under `BASEBALL_NICE=1` (niced, ~30min wall) real regressions? | **4 of 5 were niced timing artefacts** — `test_movement`, `test_reveal_watch`, `test_framedump_cpp` (1/39), `test_settled_reveal_frame` all passed clean when re-run un-niced, twice. **1 of 5 was a real regression**: `test_hand_memory_forgets`, from the I-57 merge (`c705e52`) pushing I-51b's prose between `forget_hand_slot` and `select_and_play` — fixed `49d18db` (§4). | Merge agent's un-niced re-run + diff against `204bb5b`, 00:4x |

## 4. WHAT MERGED THIS SESSION (all on `main`, one at a time, each skeptic-confirmed before merge)

| Ticket | Fix sha(s) | Merge sha | Status sha | Skeptic verdict |
|---|---|---|---|---|
| I-48b/I-48c (batter-alone fallback fires before batter verified) | `0fe4a16`, `2bad7ab` | `0748b80` | `c308e00` | Opus CONFIRMED — blind-probe-toggles-batter mechanism proven by elimination + reproduced |
| I-48e (shared re-check retries a flickering tactics read, 8 phantom presses) | `2649ff7` | `99000b4` | `ff2d69f` | Sonnet CONFIRMED |
| I-50 (dropped ban press never retried, 15/37 matches short) | `9af16f2`, `d92e81d`, `3f39ed8` (case H) | `59bb0b7` | `136fb0a` | Opus CONFIRMED WITH NOTES, both rounds closed |
| I-51 (blind-target probe gives up after 2 presses) | `7454be4`, `48892cf` | `af9a5bb` | `f5e3a24` | Opus CONFIRMED (round 2) |
| I-52 (confirm_discard verified once; late landings misread as strays) | `62fb7be`(refuted)→`5d10639`(refuted)→`ac40df0`→`7a42d46` | `5d7dc88` | `a99bc6e` | Opus CONFIRMED after 2 refutations + round-4 notes; M4/M5/M6 spot-checked at merge |
| I-53 (cursor lost after dead-reckoning across an occlusion) | `111837b` | `39f160a` | `3df988b` | Sonnet CONFIRMED |
| I-54 (truncated card name 'JOHNNY DRAW' passes result OCR) | `064bb3a` | `ca202d1` | `a97a1da` | Opus CONFIRMED WITH NOTES (N1/N3 closed at merge) |
| I-55 (result commits keep no evidence) | `3c477fa`, `9ce856e`, `f5c14be` | `c55d2cc` | `204bb5b` | Sonnet CONFIRMED WITH NOTES, 3 coverage gaps closed |
| I-57 (walk cap counts presses sent, not moves; refuses one hop short) | `fda9436`(refuted)→`41dc5f7`→`c865555` | `c705e52` | `430012b` | Sonnet CONFIRMED (round 2); **regression found post-merge, fixed `49d18db` (test_hand_memory_forgets)** |
| I-58 (pause-menu close after balance read is one blind toggle) | `f5e7572`, `0e6fa49` | `cb5d72e` | `b027a9f` | Opus CONFIRMED WITH NOTES, N1–N4 closed |
| I-58 follow-up (2 stale pause-menu test stubs vs the verified close) | `42cecdc` | `ef2da17` | — | test-only — both stubs patch `orchestrator.press`/`input_controller.press` and track the real toggle state; mutant caught |
| I-59 (questionable-card contact-sheet tool, new file) | `d5f9ed0` | (direct to main, no live import) | — | test-only, 15/15 green, 2 mutants caught |
| user truth (5 refused-select frames scored by the user) | `94343b7` | — | — | ground truth, not a fix |
| Snoopy tesseract install + fixtures | `9783aad` (`Snoopy_testing.md`) | — | — | 213/284→249/285; see §5 |
| I-44 N-2 (carried from session 1, baseline-readable gate) | `e55a02e`,`ce8d665` | `69e77a4` | `758f2ed` | Sonnet CONFIRMED WITH NOTES — narrow, hard case stays open (§6) |
| I-57 regression fix (`forget_hand_slot` adjacency) | — | `49d18db` (direct) | — | test-only — the I-57 merge (`c705e52`) had pushed I-51b's comment+snapshot line between `forget_hand_slot` and `select_and_play` (~orchestrator.py:8752-8764), outside `test_hand_memory_forgets`'s 6-line window; no behaviour change, block moved back, test green |

## 5. LATER (do not start without the user; new items from tonight go here too)

- **I-56's `_deselect_verified` note** (from `c0953b8`'s round-3 skeptic
  notes): it always dirties the ledger on a real press, even a clean one —
  recorded in ISSUES.md, not currently causing a wrong commit; worth a look
  if a future I-56 refusal looks ledger-related. (I-56 itself is READY at
  `c0953b8` and merging in the current gap — see §1, not a LATER item.)
- **Replay `refused_select_1790052649835023000` offline through the merged
  I-56 code** (cycle 19 match 4's I-56-shape refusal, see §1) — it must
  commit slot 1 and never press slot 2. First item for the morning, same
  batch as the I-62 skeptic below.
- **I-62 skeptic + merge** — first item for the morning. Branch `worktree-I62`
  (`c1fcebc` + `ccdecb8`), UNMERGED, no skeptic yet. Needs an Opus skeptic on
  the gated raised search's FALSE column: an **unconditional** raised search
  gave 28/650 wrong reads (4.3%), which is why the shipped fix is gated
  (only fires when no candidate lands in `SLOT_TOL` at all) rather than
  blanket — the skeptic should re-check the FALSE column on the gated path
  specifically over the full 650-slot census. Also surfaced but **out of
  scope**: the **BANNER_SEARCH type-window finding** — 52/59 blind tactics
  rows are blocked on the TYPE banner read, not the digit, and need their own
  search-window ticket.
- **I-60** (cursor eligibility keyed on the digit, not the disc) — **PARKED,
  tool-facing only.** Branch `worktree-I60` (`2122c8f`): fixes 3 offline
  tools' reads but never touches the live refusal path — `hand_cursor_look`
  hands the raw glow list straight to `cursor_slot`, which already ignores
  the digit mask, so the live Q17 refusal traced to something else entirely
  (the I-56 family, not I-60 — see §3). Also breaks one sub-check in
  `test_false_cursor_on_occluded_slot.py`. Not merged.
- **I-61** (raised-card detector independent of the power disc) — **PARKED,
  spike only.** Branch `worktree-I61` (`eeb593a`), `card_lift.py` unwired: the
  lift step itself is real (38–43px on all 14 disc-corroborated events) but
  per-slot rest-vs-lifted populations overlap by 2–8px on slots 0 and 3, so no
  threshold ships (CLAUDE.md §10.4). Revisit only if a future live probe shows
  the disc genuinely unreadable after settling — the lift-transition census
  says today's live lever is a re-look, not a new detector.
- **QA finder A** (`agent_progress/qa5-silent/`), 2 low findings: (1) I-57's
  `_topup_budget` check at `input_controller.py:1243-1250` cannot fire under
  current constants (entry is always at `steps==8`, 5 top-ups fit under the
  13-press budget) — delete it or cover it with a mutant that varies the
  constants; (2) `_close_pause_menu()`'s observer chain inside
  `read_balance_from_pause_menu`'s `finally` has no try/except
  (`_pause_menu_open` → `_fast_grab` → `_MSS.grab` fallback can raise), so a
  raising grab would replace the `PaidModelDisabled` the `finally` exists to
  pass through, and the "STILL OPEN" warning would not print — narrow
  trigger, diagnostic-only impact today.
- **QA finder B** (`agent_progress/qa5-tests/`): `test_probe_select_budget.py`
  mutates `input_controller.py`/`orchestrator.py` **in place** by design (it
  has to run off-checkout during a live cycle) — make it run from a scratch
  copy instead of the live checkout.
- **The I-21-vs-probe contradiction** (§3, §6) — what really blinds a disc
  after a select press, if not the lift itself.
- **Tactics slot not excluded after an I-48 fallback** — the loop re-attempts
  the same failed tactics slot on later turns, ~11s tax per turn (not a
  deadlock).
- **I-44's hard case is still OPEN** (QA6 Q2: a dropped press + a
  coincidentally-blind post-press read still commits a false inference) —
  needs per-row digit corroboration from orchestrator or a post-commit
  detector; can't be closed inside `input_controller`.
- **Cycle 4's "match never started" abandonment** (table-approach failure,
  found by the guard census, never separately tracked) — needs its own look.
- **15/36 never-staged reveal misses** (10 no-OPPONENT-card-identified, 5
  local-misfire-flag) — I-49 only fixed the staged-then-dropped half.
- **The transition-timeout drop site** (`orchestrator.py` ~`:9091`) still
  discards — 0/42 orphans traced through it this session, but it's
  structurally the same gap I-49 fixed elsewhere.
- **I-35 live verification** — `new_inning`/`reveal_recap` branches have
  still never fired live; keep checking cycle logs.
- **I-42 labels**: `FLICKER_WINDOW=10` is from the ticket text, not measured;
  9/53 good labels wrongly rejected. Measure only if the label corpus is
  needed at scale.
- **Full hand corpus re-check after I-46** (the 540-hand corpus, not just the
  2,409 turn frames) — never done.
- **Exclude LOCKED cards from the simulator pool and `choose_bans`** (RULES.md,
  user 2026-09-21) — `ban_grid.is_locked` reads ownership per cell; needs
  threading into `simulate.player_pool` / `decision_engine.choose_bans`, then
  re-run the I-13 ban A/B on the 31-card pool.
- **`result_source` semantics** — I-55's evidence line reported `path='ocr'`
  on a frame where the template alone had already cleared 0.80; check the
  path-selection logic.
- **`test_fixtures/reveal_kind_truth/auto/` hit its 200-frame cap** this
  cycle ("NOT keeping this pitch_boost one") — rotate or raise the cap
  (evidence loss, not a stall).
- **`REVEAL_SETTLE_MAX_SEC` lengthening** — carried from session 1: class
  B/D reveal frames (29% of the orphan population) are captured at 4.0–4.4s,
  past the current 2.5s ceiling.
- **`game_capture` desktop-fallback removal** — cycle 16's rig death showed
  `grab()` "FALLING BACK to a full-screen grab ... reading the DESKTOP", a
  fallback CLAUDE.md forbids. The I-05a liveness gate caught it this time
  (15/15 "wrong size"), but the fallback itself should return `None`, never
  the desktop.
- **`questions_sheet.py`'s slot box is asymmetric** — neither the box
  (margins 49–71px right) nor `SLOT_TOL` (cost 13–27.7 vs 34) clips a
  legitimately-off-anchor card (the "7" in the user-truth sheet); tighten or
  document the asymmetry.
- **`test_result_commit_evidence.py` flakes on Snoopy** (FAIL/PASS/FAIL,
  timing) — check whether it's timing-sensitive on the Mac too.
- **10 Windows-only footguns with one-line fixes** (file-handle locks, `mss`
  BitBlt failing headless over SSH, `open()` defaulting to cp1252, `/tmp`
  literals, path separators) — enumerated in `Snoopy_testing.md` (`9783aad`);
  not actionable on the Mac, keep for whoever maintains the Snoopy runner.
  Separately, 6 OCR-content diffs under Windows tesseract are real but Mac-
  irrelevant (same file).
- **Housekeeping — DONE this session, noting for the record**: `.claude/worktrees/`
  cleanup removed 46 of ~51 worktrees (69G→7.6G); 1 unmerged skipped
  (`claude/eloquent-spence-03fe41`), 2 locked by old agents, 3 live at the
  time. Re-run `git worktree list` if it's grown large again.
- **QA round over `204bb5b..49d18db`** (2 finders, silent-paths/guards + test
  quality) is running as of this handoff — read its output when it lands and
  fold findings in here, don't act without reading.

## 6. OPEN QUESTIONS

- **What actually blinds a disc after a select press, live, given the lift
  itself does not?** (§3) The dominant open question tonight. I-21
  (select-time inference) fired 32x over 34 run logs — 28 committed and
  correct, 0 wrong, 4 refused — so the mechanism is real and mostly safe, but
  the live probe read the disc on **0/187 unreadable frames**, including
  lifted at dy −41, and the archive read 14/14 lifts clean. The census
  agent's own claim that "a lifted card's disc stays blind while lifted" is
  **unmeasured** (sourced from code comments) and directly contradicted by
  both the probe and the archive. Candidates, neither measured: cursor-glow
  interference on the just-selected card, or a ~0.6s settle-timing gap. Next
  step: instrument the actual production select path (not an offline probe)
  the way `lift-live-probe2` instrumented a manual one.
- **WHO DELETED `tools/questions_sheet.py` from the main working tree
  mid-session?** Not established. It was committed clean at `d5f9ed0`, then
  found as a bare ` D` in `git status` with no other file touched — ruling
  out `test_questions_sheet`'s own cleanup (only removes its tempdir) and
  making the merge agent's `git archive 204bb5b | tar -x` unlikely (that
  would have shown many `M` lines, and it didn't). Restored with
  `git checkout -- tools/questions_sheet.py`. Before dispatching anything else
  that writes under `tools/`, check every `agent_progress/*/progress.md`
  written this session for an `rm` or `rmtree` on that path.
- Does a speed boost PERSIST on base? Two live runners read +1 over their
  card (CLAUDE.md §4); low stakes (+0.046 runs/half). Still needs one live
  at-bat.
- Was draw #8 (session 1, cycle 6) or the evidence-less draw #9 (cycle 9, this
  session, before I-55 merged) real? Both unverifiable — no frame, no score.
  Going forward every draw carries evidence (I-55); these two stay unknown.
- **Leave cycles chaining unattended overnight, or stop the console too?**
  Asked by the assistant at 00:30, never answered by the user before the
  deadline. Current behaviour (stated default, not contradicted): unattended
  chaining continues. If you're reading this cold and the chain is still
  running or has stopped, that's why.

## 7. RULES IN FORCE (user's words where quoted)

- *"Any stalls, any issues count. Things need to be run perfectly like a
  nuclear power plant."* (18:4x) — the strict streak rule, §2.
- *"Never halt for input"* (02:1x) — questions about unreadable/ambiguous
  cards get queued (`tools/questions_sheet.py`, I-59), never block a run.
- Push a notification only for: run-stopping events, wrong-card commits, or
  the 50th clean match (user's approved scope, 02:0x–02:1x).
- **Never save the game** — resets and `Load Last Save` only.
- **Play the engine's pick, fix the engine** — never hand-override a card
  choice; check the reader first when a read looks wrong.
- **Never `git stash` / `git checkout <sha> -- file` in the main checkout
  while it holds uncommitted live data** — bisect in a scratch copy or a
  detached worktree (rule earned the hard way tonight: a bisect one-liner
  stashed live `match_log.jsonl`/`deal_timing.jsonl`/the cycle journal for a
  few minutes before being caught and recovered).
- Navigation/routing code is left alone this session — no changes to
  `graph_walk.py` or the closed-loop chain logic; per CLAUDE.md §9, any such
  change needs a live A/B and a read of `GRAVEYARD.md` first.
- **Snoopy: one job at a time, grunt-work/labelling only, text-only reads**
  (never wired into the live ladder — the VLM scored 70% wrong on known-good
  scene-state controls). Snoopy is OFF as of 00:5x tonight.
- **User rule (2026-09-21 ~13:30, still in force): any NEW task or question
  found from here goes on the LATER list — do not dispatch it.** Reaffirmed
  00:5x: *"finish the cycles left ... all current todos; anything new is
  added to future sessions todo list."* **No new dispatches after this
  handoff's close** — finish only what was already in flight (the I-56 merge,
  the I-62 skeptic+merge, the cycle relaunch); anything newly found goes on
  §5 LATER, full stop.
- **Sleep the console when not in live use** (user, 01:0x) — let it auto-sleep
  on its own (CLAUDE.md §1: nothing reaching it puts it to standby) or, if it
  needs putting down by hand, follow `console_rest_mode_procedure.md` step by
  step. Never press `ps_button` just to find out whether it's already asleep.
- Manager delegates routine work (merges, tests, doc edits, log reading) to
  Sonnet agents; the main model decides and dispatches. Opus skeptics for
  anything on the money path.

## 8. LIVE WATCH ITEMS for whoever picks this up

- **The cycle 19–26 chain's own tally** — `overnight/run_live_20260922e.log`
  is the ground truth; this document's record (100W15L11D) predates it.
- **I-56-family firings** (tactics/wreath read fails beside a lifted
  neighbour, or a false "genuine stray" mark) — the single most common
  streak-breaker across cycles 12/13/18. Watch for it recurring on the
  un-merged-I-56 build; it will, since I-56 hasn't landed yet.
- **I-57-shape walk stalls** ("still at N after 8/13 presses") — fixed at
  `49d18db`, but this is its first live cycle since the regression fix; watch
  for a clean recovery on a press-drop cluster near the cap.
- **Ban shortfalls** — should stay at 0 (4/4 cycles clean since I-50); a
  recurrence is a regression, not expected noise.
- **Evidence-less result commits** — should stay at 0 (I-55 merged, evidence
  line present on every WIN/LOSS/DRAW since cycle 13); a bare
  "X logged" with no `[state]`/OCR line is a regression.
- **Pause-menu stalls** (I-58) — watch specifically at the first balance read
  of a fresh cycle; that's where both prior occurrences fired.
