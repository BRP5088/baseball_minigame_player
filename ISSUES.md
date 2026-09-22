# ISSUES — what stops the engine from winning every match and playing every turn

Written 2026-09-20 by the manager session. Every finding was taken against
**HEAD a3419d0 with a dirty tree** (another agent's uncommitted edits to
`orchestrator.py`, `input_controller.py`, `local_state.py`, plus three new tests and six
fixtures). Where a line number is in the DIRTY tree it says so; the rest are at HEAD.
Line numbers rot; the function name beside each one is the durable anchor.

## How to read this

- **A** blocks an unattended run. **B** costs turns or time. **C** costs wins.
  **D** is evidence the others need and do not have.
- **P0** = fix before the next unattended run. **P1** = next. **P2** = worth an A/B, ship
  only on a measured win.
- ESTABLISHED means someone read the line or ran the command named. ASSUMED is labelled.
  CLAUDE.md §10.32: do not assert what you have not checked.

## Rules every fix agent inherits

1. The paid vision model stays OFF. `PaidModelDisabled` is the choke point.
2. Look before every press, and again after it (§5: 15.20% of presses are ignored, clustered).
3. Do not edit a module a live run imports while the run is in flight (§10.21). Check
   `pgrep -fl "run_one_match|run_cycles|go_now"` first.
4. Every guard is mutation-tested: break it, watch the test fail, restore, verify the sha
   (§10.9, §10.10). Mutation sweeps while the console is live go to Snoopy.
5. Write `agent_progress/issues/I-NN/progress.md` AS YOU GO, split Established / Assumed
   (§10.16). Scripts that produced a number sit beside it. Nothing in /tmp.
6. A threshold sits between two measured populations or it is not a threshold (§10.4).
   A change to card choice ships only on an interleaved A/B with a control arm that
   reproduces the shipped number (the `tie_w` pattern, CLAUDE.md §4).
7. Model: Sonnet for code and census (Haiku cannot load this repo's CLAUDE.md; it
   died at launch on I-19); Opus only for the money path (`start_match`,
   `close_result`, debit, reset) and for strategy A/B design.
8. Before touching the cursor, deal gate or result reader, `git diff` — the other agent
   is in those files now.

Entry shape:

    Evidence · Root cause · Proposed fix · Verify (with control) · Agent brief · Status

---

## A. Blocks an unattended run

### I-01  `_hand_signature` is defined twice; the deal gate can never release      P0  loop

**Evidence (DIRTY tree).** `orchestrator.py:4860 def _hand_signature(hand_img)` (the deal
gate's helper, at HEAD) and `orchestrator.py:7358 def _hand_signature(hand)` (the new
discard stall breaker's helper, uncommitted). `ast.parse` confirms both are module-level;
the second wins at import. The deal gate calls it with a PIL image at
`orchestrator.py:3700` and `:3746`; the list version iterates the image, raises, and the
`except` sets `readable = False`, so `good` never reaches `READABLE_POLLS`.
`deal_timing.jsonl` rows 37-39 (run c, 17:53-17:57): `edge_seen: true`, biggest 55.7 /
54.8 / 83.1 against threshold 15, all `outcome: timeout` at 20 s. Run c log lines 55-60,
71-74, 84-88 show the same three deals waiting the full 20 s.

**Root cause.** Name collision in a 9,000-line module; the new helper was written
without grepping for the old one.

**Proposed fix.** Rename the stall breaker's helper (`_hand_identity`) and its two
callers at `:7371` and in `discard_stalled`. Nothing else.

**Verify.** (1) A test that asserts `inspect.signature(orchestrator._hand_signature)` has
one parameter named `hand_img`. (2) Replay the three run-c deals offline: feed the frames
from `screenshot_log/run_20260920_175322/` for those windows through
`wait_for_hand_deal`'s stability rule and require `stable`. Control: the same frames with
the collision restored must time out.

**Agent brief.** Sonnet. May touch `orchestrator.py` (the new helper only) and one new
test under `tests/minigame/`. Done when the test passes and fails with the rename reverted.

**Status.** FIXED in the other agent's working tree, 2026-09-20 evening, uncommitted:
its helper is now `_discard_hand_identity` (orchestrator.py:7358), and
`tests/harness/test_no_shadowed_module_defs.py` AST-scans every module for a duplicate
top-level def with a positive control (456 modules, one pre-existing duplicate found and
renamed in `test_simulate_rules.py`). Verified here: `grep -c "^def _hand_signature"` is 1.
COMMITTED to main in de5a79b. **CLOSED 2026-09-20 (85c745b):** the replay
(`agent_progress/issues/I-01/replay_deal_gate.py`) releases all three run-c deals at frame 3
of their windows under the fixed helper, and none under the shadowing control.
`deal_timing.jsonl` rows 37-39 are ARTEFACTS of the bug (a delta five times the threshold
logged as a timeout); the data file is untouched and `tools/deal_timing.py` now excludes
that exact shape (`edge_seen` true, timeout, no `reason`) and says so: 40 -> 37 live rows.

### I-02  Slot 4 cannot be played or discarded                                     P0  input

**Evidence (DIRTY tree).** `input_controller.py:927-942 _walk_cursor_to`: the walk loop
re-reads `cursor_slot` after every press and returns `False` the moment it is `None`.
`local_hand.py:1237 CURSOR_GLOW_MIN = 10.0`; the glow at slot 4 reads 6.9-9.8 in every
frame of runs a, b, c while the cursor sits there (`glow=[0.1, 0.0, 0.5, 0.2, 8.6]` and
23 more like it). CLAUDE.md §10.35: "slot 4 never exceeds 11.0 at ANY offset, while
slots 0-3 read 26-28". Run c line 14: `lost the cursor after 2 press(es)` on the way to
DISCARD slot 4; run b lines 36-108: the PLAY of slot 2 refused eight times because the
cursor started blind on slot 4 (fixed by the other agent's nudge-off, which walks AWAY
from slot 4 and never onto it).

**Root cause.** The only cursor sensor is the glow window, and it is structurally blind
at the last slot. Nothing else names the cursor slot.

**Proposed fix (candidate).** When the walk arrives at the target's expected position
and the glow is blind, PROBE-SELECT: press `select_card` once and read
`local_hand.selected_cards` (lift geometry, `SELECTED_MIN_RISE` 25, an empty 34-point band
between rest and selected). A NEW lift names the slot the cursor is on. If it is the
target, the selection is done (`_select_verified` already accepts "already up"). If not,
press once more to untoggle and continue. The `before` set must be captured first;
`select_card` is a toggle.

**The refutation that does NOT block this**, `agent_progress/cursor-lift-refutation/`
(progress.md + `measure_lift_vs_glow.py`, re-runnable on a run dir): over 277 five-row
fans from `screenshot_log/run_20260920_175322`, HOVER produces no measurable rise (slot 3
p50 7.0 hovered and 7.0 not; slot 4 -10.0 either way; max-rise agrees with the glow reader
34 times, disagrees 98). So CLAUDE.md §10.28's "the card RISES when the cursor moves onto
it" is wrong for hover, and a hover-based lift reader is dead. The probe-select uses the
SELECTION lift (~44 px, `SELECTED_MIN_RISE` 25), which that measurement leaves intact.
Two cautions from the same write-up: (1) the probe must deselect AND verify the deselect
landed (§10.29; `close_result` is not a deselect); (2) `selected_cards` skips a player row
whose y came from a fallback rather than the disc, so it abstains on exactly the cards
whose disc is unreadable. Check it can SEE the slot before trusting a negative.

**Verify.** Offline: harness test with the glow reader stubbed blind at slot 4 and the
lift reader answering, asserting the discard of slot 4 lands and that a probe on the
WRONG slot is untoggled (control: without the untoggle the test must fail). Live: one
hand whose weakest card is in slot 4; the discard must be confirmed by the ban-style
counter read.

**Agent brief.** Sonnet, then Opus for the live check. May touch
`input_controller._walk_cursor_to`, `_select_verified`. Must not touch `local_hand`'s
glow constants. Done when both verifications pass.

**Status.** OFFLINE HALF MERGED 2026-09-20 (b886b35): `_walk_cursor_to` probes by
selection when the cursor goes blind one step from the target (`PROBE_SELECT_MAX` 2); a
wrong lift is untoggled through `_deselect_verified` and the untoggle is VERIFIED; a target
row the lift reader cannot see is refused without a press. Three mutants caught, one of
them only after the test was rewritten to spy on the untoggle primitive rather than the
fake screen (progress.md records why). **LIVE CHECK STILL OPEN**, recipe in
`agent_progress/issues/I-02/progress.md` ("The live check a supervised session should
run next"): a hand whose weakest card is in slot 4, watch for `probe-select: 4 lifted`,
confirm no further press and `discards_left` decrements.

### I-03  A refused PLAY ends the run instead of playing another card             P0  loop

**Evidence.** `orchestrator.py:7642-7645 play_one_turn`: a refused `select_and_play`
prints `play REFUSED` and returns `False, None`. `orchestrator.py:9188-9199 run()`: the
`else` branch is written for discards ("A discard leaves the screen looking identical")
but takes every `False`, increments `stuck_count`, and at `MAX_STUCK_ATTEMPTS` (15,
`orchestrator.py:293`) stops with `stop_reason = "redraw_never_played"`. Run b lines 36-108:
eight identical refusals of the same play, ~25 s each, until Ctrl-C. So it is a bounded
stall of about six minutes ending in a STOP, not a hang; the other agent confirms this
and withdraws its earlier "unbounded".

**Root cause.** Refused plays and refused discards share one counter and one exit, and
the exit is a STOP. The engine has a full ranking of the hand but only ever asks for its
first choice.

**Proposed fix.** Count refused plays against the hand signature the other agent's
`_DISCARD_STALL` already keys on; at the bound, re-run the decision with the refused slot
excluded and play the next-best reachable card. Name the stop reason correctly
(`play_refused`) if it still stops.

**Verify.** Harness test: stub `select_and_play` to refuse slot k forever; assert a
different slot is played by attempt 4 and that the log line names the fallback. Control:
with the fallback removed the run must stop with the old counter. Mutant: drop the
exclusion so the same slot is retried.

**Agent brief.** Sonnet. May touch `play_one_turn` and the `else` at `:9188`. Must not
touch the debit path. Done when the test and mutants pass.

**Status.** MERGED to main 2026-09-20 (b02b178): `PLAY_STALL_MAX` 3 keyed on the same hand
identity as the discard breaker; a slot refused 3x is excluded and the next-best card is
played; run() stops with `play_refused`, distinct from `redraw_never_played`. Two mutants
caught.

### I-04  The result CARD reader has one confirmed word                             P0  reader

**Evidence (DIRTY tree).** `local_state.py:798 read_result_card` OCRs a band for
`DEFEAT / WINNER / DRAW`. Its own comment: "only DEFEAT is confirmed by a frame. WINNER
and DRAW are taken from screen_classifier_experiment.py's comment". Run c lines 89-105:
the DEFEAT card was on screen for the whole 15-poll budget and the run stopped with
`unreadable_screens`, leaving the match unscored (the user scored it by hand; the record
went 10 to 11 losses). The arched template bank scored 0.55 max over 705 frames of that
match; it never appeared.

**Root cause.** §10.31 again: a classifier with a missing class. The card build of the
result screen was never in the fixture set.

**Proposed fix.** None to the code beyond what shipped. On the next live WIN and DRAW,
save the full frame to `test_fixtures/result_screens/` and pin both words in
`tests/minigame/test_result_card_is_read.py`. Until then a win cannot be scored by the loop.

**Verify.** The two fixtures read `win` and `draw`; the existing DEFEAT fixture still
reads `loss`; 500 non-result frames from `screenshot_log/` read `None` (one false positive
is a veto, as for `at_table`).

**Agent brief.** Haiku, after the frames exist. Done when the three fixtures are pinned.

**Status.** WIN pinned 2026-09-20 (c994139): the live win screen is the ARCHED WINNER banner,
answered by the template bank at 0.91-0.93; called directly the card reader also reads
'WINNER'. 42 of 42 result frames read win, 0 wrong; 300 non-result frames from the same
match read nothing. DEFEAT pinned by the other session. **DRAW is now pinned too (2026-09-21),
found by the Snoopy archive search that also produced I-38's fixtures.** The live frame is
`test_fixtures/result_screens/draw_live_20260910.png` (2026-09-10, sha256
`c7f6fce5e75197b3...`); like WINNER it is the ARCHED DRAW banner, not the notebook card --
`result_scores` reads winner 0.659 / loser 0.494 / draw 0.984, well clear of RESULT_MIN
(0.80) and of RESULT_MARGIN against the runner-up, and `read_result_card` independently
reads 'DRAW' off the same frame. Pinned in `test_result_card_is_read.py` section 5b,
mirroring how WINNER is pinned in section 5. All three words -- DEFEAT, WINNER, DRAW -- are
now confirmed by a live frame; nothing is left taken on the comment alone.

### I-21  `_select_verified` re-toggled a landed selection once its own disc went blind   P0  input

**Evidence.** overnight/run_live_20260920d.log ~168-190 and screenshot_log/run_20260920_194419
19:48:50-19:49:30: hand [fielding_boost, 9/0, 5/1, pitch_boost, 6/0], "Playing pitch focus 9"
(slot 1); `_select_verified` pressed select_card FIVE times, the user watched the 9 select
and deselect on the stream, then two polls refused on "position is unreadable", then I-03's
fallback played the 6 at slot 4 (revealed 6 vs 6, a coin flip).

**Root cause.** A lifted card's power disc loses its dark edge, so `selected_cards` abstains
on that row and a LANDED select reads exactly like an unlanded one; the pre-press guard ran
once, before the first press, and every retry toggled the card back down.

**Fix.** MERGED 2026-09-20 (3450a03): after any press, a target that has become unreadable
is re-looked once after `SELECT_RETRY_CONFIRM_SEC` and, if still unreadable, INFERRED
selected (nothing but our press could have blinded a row proven readable a moment before);
it is never pressed twice without a look showing it at rest and readable. A target
unreadable from the start still refuses without pressing.

**Verify.** `tests/minigame/test_select_stops_when_lift_unreadable.py`: landed-then-blind (1
press, success), dropped press (still retries), pre-unreadable (refuses, 0 presses),
genuinely dead (exhausts the budget). Two mutants reproduce the 5-press toggle. Live check:
the next match with a 9 selected must log one press, no toggle.

**Status.** Merged; live confirmation open.

### I-05  The unattended loop has never run end to end with the paid model off      P0  loop

**Evidence.** `run_one_match.py:50` passes `max_spend=0`: it finishes the match already
paid for and stops, by design. The loop that buys matches is `run_cycles.py`; its
per-cycle liveness check is `ensure_stream.ensure(log=log)` at `run_cycles.py:422`,
which `ensure_stream.py:378-417` satisfies on a heartbeat alone. `ensure_live()` — the
one that also runs `is_frozen()` and the blocking-UI ladder — has one caller,
`go_now.py:30`. CLAUDE.md §1: `ensure_live()` returning True is not proof the game will
take input; here it is not even called. No run since the model went off on 2026-09-12 has
gone walk → pay → ban → play → result → next match unattended (the three 2026-09-20 runs
all began mid-match).

**Root cause.** The cycle driver predates the reconnect lessons in §1 and was never
re-audited against them.

**Proposed fix.** In `cycle()`: `ensure_live()`, then a reader that answers only on the
screen expected next (`at_table` for the prompt, `read_ban_counter` for bans,
`local_hand.read_hand` for a turn) before the first press. Refuse and log otherwise.

**Verify.** Harness test asserting `cycle()` calls `ensure_live` and one screen reader
before any press (control: the test must fail against HEAD). Then a SUPERVISED 3-match
run, then an unattended 10-match run scored with I-19's census. The overlay case: put the
PS5 overlay up and confirm the cycle refuses rather than presses.

**Agent brief.** Opus (money path). May touch `run_cycles.py`. Must not change
`reset_env` or the debit code. Done when the 10-match run completes with zero stops.

**Status.** Open. Blocked on I-01 to I-04 landing first.

**I-05a:** third attempt on branch worktree-agent-a7613eff370917779 (7d1c70b,
plus one prose-only follow-up commit): round 2's three holes are fixed
(debounce is now a wall-clock window, LIVENESS_MISS_SEC, not a poll count;
M2 and M5 both killed; ensure_stream._game_visible fails open when every
reader crashes). Round-3 skeptic verdict: CONFIRMED WITH NOTES (not
merge-blocking). The deciding measurement: over 1004s of real 10Hz gameplay
across the three surviving screenshot_log/ runs (9729 frames,
agent_progress/issues/I-05a-skeptic-r3/census_gate.json), the REAL liveness
gate misses exactly ONE genuine game frame (a ban-selection splash, 0.102s)
-- LIVENESS_MISS_SEC=6.0 is a 59x margin over that. 9 of 9 mutants killed
(M1-M5, the HOLE-3 guard, plus two new shapes from the skeptic). 14/14
regression files EXIT:0. Two open notes, neither blocking: the AMBIGUOUS
branch's true-positive class (a real PS5 overlay over a live game) has n=0
on disk, so its false-positive rate is measured ~0 but its ability to catch
a real overlay is unmeasured (safe direction: it can only fail by not
firing); and _dismiss_overlay_if_blocking has no pre-filter or debounce of
its own, so on a false fire it could in principle leave the overlay open --
untestable offline, no such fixture exists.

**Status.** merged 44c0c99199ab725665b1d79f0f065a36de44ed7d; skeptic CONFIRMED WITH
NOTES (9,729-frame census, 1 miss of 0.102 s; notes folded).

### I-06  A stalled match is abandoned by the next cycle with no record             P1  money

**Evidence.** `reset_env.py:183 reset_environment`: `:270-276` answer the "Give up?" dialog
YES up to `GIVE_UP_ATTEMPTS` (3, `:60`) to reach the pause menu; `_clear_match_flags()`
then clears `match_in_progress`; `run_cycles._reset_progress()` re-reads the balance from
the pause menu. CLAUDE.md §11 records giving up as measured and safe. The $50 and the
match's outcome are never written anywhere.

**Root cause.** The recovery is correct for money and silent for the census; every stall
in A becomes an invisible match.

**Proposed fix.** When `reset_environment` takes the give-up path, append
`{"outcome": "abandoned", "reason": <stop_reason>}` to `match_log.jsonl` and bump an
`abandoned` counter in the progress file.

**Verify.** Harness test seeding `match_in_progress: true` plus the give-up fixture
(`tests/rig/test_give_up_dialog.py` has the detector); assert the row and counter.
Control: seed no match, assert nothing is written.

**Agent brief.** Sonnet. May touch `reset_env.py`, `run_cycles.py`, `orchestrator.save_progress`.
Done when the test passes and the row appears on the next real abandonment.

**Status.** MERGED to main 2026-09-20 (b60f839). Smaller than the brief: only `reset_env.py`
changed, because `_clear_match_flags` already owned the progress file; two mutants caught.

### I-07  The motion gate cap is below the game's measured animation ceiling        P1  loop

**Evidence.** `orchestrator.py:2688 MAX_CONTINUOUS_MOTION_WAIT = 15.0`. RULES.md §4: a
bases-loaded home run's bases clear at 16.65 s. After 15 s of motion the loop reads anyway.

**Root cause.** The constant was set before the baserunning timings were taken.

**Proposed fix.** Raise to the measured ceiling plus a poll (18 s). ASSUMED impact: one
unreadable poll or a mid-deal read on the longest plays; no log line on disk shows it
because no loaded home run has been played since the timings landed.

**Verify.** `tests/minigame/test_run_motion_gate.py` pins the constant; update the pin
with the RULES.md figure as the citation. Confirm on the next loaded home run's deal row.

**Agent brief.** Haiku. One constant, one test line.

**Status.** MERGED to main 2026-09-20 (028e78f): 18.0, literal pinned in
`test_run_motion_gate.py`, mutant caught.

### I-08  The paused branch escaped every bound                                    P0  loop

**Status.** SHIPPED by the other agent, committed in de5a79b (`polls_without_progress`
now counts paused polls). Recorded so it is not re-reported.
I-05's overlay check is the live verification it still needs.

---

## B. Costs turns or time

### I-09  The deal gate is armed with no deal to watch, and its timeout line lies    P1  loop

**Evidence.** `deal_timing.jsonl`: 40 rows, 26 `timeout`, 13 `stable`, 1 `error`. Rows
20-36 are timeouts with `edge_seen: false` and biggest 6.2-10.8: nothing moved, because
the preceding action was a REFUSED discard or play. The post-play wait at
`orchestrator.py:9216-9224` sits after the played / not-played `if-else`, so it runs on
both branches. The discard path is gated (`:7568-7575`, "not watching, because there is
no deal to watch") but the play path is not. The timeout message at `:3761-3764` prints
"a biggest well UNDER the threshold means the gate is too high" unconditionally, including
at biggest 83.1 (run c line 88).

**Root cause.** The gate's caller does not know whether a deal happened, and the message
was written for one of three cases.

**Proposed fix.** Arm the post-play gate only when `played` is True. Print three distinct
lines: no edge (nothing dealt), edge but never stable (I-01's shape), stable. Add
`reason` to the row.

**Verify.** Three harness cases produce three lines; rows carry `reason`. Control: a
refused play must write NO row (the discard path's own rule, `:7555-7561`).

**Agent brief.** Sonnet. May touch `wait_for_hand_deal` and its call at `:9216`.

**Status.** MERGED to main 2026-09-20 (028e78f): the post-play gate runs only when `played`;
timeout messages split by `seen`; rows carry `reason` in {capture_error, edge_released,
stable, no_edge, edge_no_stable}; three mutants caught.

### I-10  Hand incompleteness is flagged for one occluder only                       P1  engine

**Evidence.** `decision_engine.py:365 should_redraw` refuses to redraw only when
`state.hidden_by_homeplate_runner` is set. `orchestrator.py:4932 local_hand_cards` drops
any slot it cannot read and proceeds once `MIN_LOCAL_HAND_CARDS` (3, `:4799`) remain, setting
no flag. Run a lines 25, 40, 71, 88, 99, 114: `UNKNOWN` at slots 2, 0, 4, 1, 1, 1 on six
turns of one half. CLAUDE.md §10.34: the hidden slot was the best card and a discard was
spent on a hand that was never weak.

**Root cause.** The guard was built for the home-plate occluder (RULES.md §3) and the
fan-neighbour occluder (§10.28) takes the same path without the flag.

**Proposed fix.** Rename the flag `hand_incomplete`; set it in `local_hand_cards`'s
caller whenever a PLAYER slot was dropped, from either cause.

**Verify.** Unit test in `tests/minigame/test_decisions.py`: a 4-card hand with max 5,
flag False → redraw True; flag True → False. Mutant: remove the flag assignment.

**Agent brief.** Sonnet. May touch `decision_engine.should_redraw`, `GameState`, and the
flag's setter in `orchestrator.local_game_state`.

**Status.** MERGED to main 2026-09-20 (86437f4). Smaller than the brief: `local_hand_cards`
already returned the drop signal (`why`) and `local_game_state` discarded it; now
`state_json["hand_incomplete"]` reaches `GameState`. Three mutants caught. The two paid-path
call sites of `local_hand_cards` are not wired (paid model is off).

### I-11  Three presses on the match path are blind                                 P1  input

**Evidence.** `input_controller.py:1269 press("confirm_play")` (inside the verified
select-and-play), `orchestrator.py:8130, 8164, 8270 press("close_result")`,
`orchestrator.py:8377, 8449 press("start_match")`. Each is verified only by the next poll's
screen and shares `stuck_count` with unrecognised screens. `input_controller.py:2933
press_verified` exists, is tuned from the 1,000-press census (`PRESS_VERIFY_TRIES` 5), is
tested by `tests/rig/test_press_verified.py`, and has ZERO production callers
(`grep -rn "press_verified("` outside tests returns only the definition). RULES.md §1:
`confirm_play` was ignored twice in a row live on 2026-09-20.

**Root cause.** The primitive was built after the call sites and never wired in.

**Proposed fix.** Wrap each site in `press_verified` with a screen-specific `observe`:
confirm_play → the selected card has left the fan (`selected_cards` empty or the reveal
watcher's episode opened); close_result → `read_result` returns not-a-result;
start_match → `read_ban_counter` answers.

**Verify.** One harness test per site with the first press dropped, asserting a second
press and success. Control: with a never-landing press the site gives up after 5 and
returns False, not True.

**Agent brief.** Opus for `start_match` (money), Sonnet for the other two. Must not
change what `press` sends.

**Status.** Open.

### I-12  Misfire detection is inert with the paid model off                         P2  input

**Evidence.** `orchestrator.py:8927`: `reveal_cards = (...) if paid_model_allowed() else []`.
The misfire guard downstream reads `reveal_cards`, so with the shipped default it never
runs; every run summary says so ("NOT MEASURED — the misfire detector lives in the reveal
path, which is paid-only"). Run a's summary counted 1 suspected misfire in 10 plays
from the LOCAL path's `[MISFIRE?]` line (`:9160-9170`), which logs but does not back off.

**Root cause.** The backoff was wired to the paid read; the local read landed beside it.

**Proposed fix.** Call `input_controller.report_misfire()` from the local `[MISFIRE?]`
branch, which already has our intended and revealed powers.

**Verify.** Harness test: local reveal shows power 7, we played 8 → `report_misfire`
called once. Control: matching powers → not called.

**Agent brief.** Sonnet. Small.

**Status.** MERGED to main 2026-09-20 (6390fdc): the local `[MISFIRE?]` branch calls
`report_misfire()`; the summary says MEASURED (local reveal) once a local read ran. Mutant caught.

---

### I-22  A PITCH FOCUS at slot 3 read UNKNOWN for four turns: bank coverage, not occlusion   P1  reader

**Evidence.** overnight/run_live_20260920d.log, pitching half: after the discard at slot 3
the redeal read `3: UNKNOWN` four straight turns (hand_incomplete each time) and only then
`pitch_boost +1`. The four dropped-hand stills in diagnostics/deal_frames are the SAME card
(pairwise correlation 0.99+), plainly legible; `read_bonus` read 1 every time.

**Root cause.** `read_tactics_type`'s score sat at 0.755-0.764 against MIN_TYPE_SCORE 0.85,
stable to three decimals across tens of seconds: this card's disc lands at x=642, left of the
661-664 cluster the bank's slot-3 pitch_boost templates were cut from. The same gap as commit
83a4a73's FIELDING PLAY at slot 3. The "watching the redeal" gate never armed because the
discarded slot is readable at discard time by definition.

**Fix.** MERGED 2026-09-20 (16319b8): one donor in tools/build_hand_tactics_templates.py cut
at its found position, bank rebuilt (373 templates); a second independent frame reads 0.996+.

**Verify.** tests/minigame/test_i22_pitch_boost_slot3.py (stripping the donor regresses both
fixtures to the exact live scores); test_tactics_bank_is_rebuildable.py catches the same
mutation from the builder side. Three turns played with an invisible pitch boost cost
nothing this match (pitch boosts would have attached; I-14 says a boost changes outcomes).

**Status.** Merged.

### I-23  The reset's dialog detector missed a visible "Load Last Save" dialog three times   P0  loop

**Evidence.** overnight/run_live_20260920e.log lines 72-87: `selected: Load Last Save`, then
`no dialog yet (delta 2.4 / 2.8 / 2.1) — the commit press did not land, retrying (1..3/3)`,
then `ResetError: no confirmation dialog appeared (delta 2.1)`. The frame captured right
after (`test_fixtures/load_last_save_dialog_live_20260920.png`) shows the dialog fully up:
"Load Last Save — NO (circle) / YES (cross)". The same routine had succeeded four minutes
earlier on attempt 1.

**Root cause (ASSUMED, to trace).** `reset_env.reset_environment` detects the dialog by a
frame DELTA against a baseline; if the first Cross landed before the baseline was taken, the
dialog is already in the baseline and every later delta is idle-animation noise (2-3), so a
present dialog reads absent, and each "retry" presses Cross at a dialog whose YES is Cross.
Alternative: three consecutive dropped presses (P ~ 0.152 x 0.25 x 0.25 = 1%).

**MEASURED 2026-09-20, and it is neither:** chiaki's log shows every Cross tap accepted and
TRANSMITTED (`[btnedge] id=1 DOWN TRANSMITTED`); the game ignored four taps at 0.05 s in a
row and accepted ONE Cross held 0.6 s at once, the world reloading 3 s later. **This dialog
wants a HELD confirm.** The reset's confirm press must hold; the content-based detector
stays needed because the delta rule cannot tell "dialog up, press ignored" from "no dialog".

**Proposed fix.** Detect the dialog by CONTENT, not by delta: a small template/OCR reader
for the "Load Last Save" panel (dark flat panel, the two button glyphs), gated the way
`give_up_dialog` is, and used both before pressing (already up -> do not press again) and
after. Keep the delta as a secondary signal only.

**Verify.** Fixture above must read as the dialog; the pause menu without the dialog, a
world frame, the give-up dialog and a ban screen must not. Mutation: drop the content
check, the fixture reads absent.

**Status.** MERGED 2026-09-20 (4ce2d5e). The traced cause was NEITHER hypothesis: the
retry loop polled the PREVIOUS press's result at the top of each iteration and pressed
at the bottom, so the LAST press's result was never polled and the raise quoted the
delta from before it. Fix: `reset_env.load_save_dialog(img)` (phrase read in a band,
1 true positive and 0 false positives over 656 other 1920x1080 fixtures), checked before
the first press so an open dialog is never pressed again, every press polled in the same
iteration, delta kept as the fast signal; and `CONFIRM_HOLD_SEC = 0.6` on the confirm
presses (n=1 accepted vs 4 taps ignored, thin and said so). Three mutants caught. Live
confirmation: the next reset must reload in one held press. QA round 3 (46a8210): the YES
retry loop now re-reads the screen and re-presses only while the dialog is visibly up; a
landed press followed by a slow world load sends one Cross, not three.

### I-24  `ensure_stream.looks_like_ui` fires on the game's own dark dialog panel          P1  reader

**Evidence.** On the same frame `looks_like_ui(img)` returned True with `capture (1920, 1080)`.
The heuristic looks for flat fills and full-width exact runs (Qt draws them, H.264 does
not); this in-game panel is flat enough to pass.

**Consequence.** `streaming()` pairs `find_bar` with `looks_like_ui`, so a reader that asks
"is the stream up" while this dialog is open can be told no and fall through to the slow
heartbeat path; CLAUDE.md §1's three tells would misclassify this screen as chiaki's UI.

**Proposed fix.** Add the fixture to `test_fixtures/not_streaming/`'s NEGATIVE side (it IS
streaming) and re-derive the flatness/row-run gates against it; if the populations no
longer separate, `streaming()` needs a game-content signal (compass strip or notebook
edge) rather than a flatness one. Do not move the constants without the census.

**Status.** CENSUS DONE 2026-09-20 (bd06795, agent_progress/issues/I-24/): over 616
streaming frames the widest-row-run quantity saturates at 1.0 on genuine game dialogs and
ban-counter frames, tied with the host list's 1.0, and 11 of 67 in-game fixtures outside
the test's glob are rejected today. NO threshold on these two quantities separates the
populations; constants untouched; the false negative is pinned in
test_streaming_rejects_chiaki_ui.py so a fix flips it deliberately. Fix wanted: a
game-content signal (compass strip, or pause_menu's page/menu-text pair). Open.

### I-25  A false argmax on an occluded disc deadlocked a live match                P0  reader

**Evidence.** `test_fixtures/hand_reads/i25_false_cursor_slot0_live_20260920.png`, a live
mid-match frame: slot 0's power disc sat hidden under slot 1's card, `read_hand` returned
`digit: None, y_from: "disc"` for that row (a circle WAS found, sized and positioned like a
real digit disc, but nothing on it matched a digit template), and the glow window it
anchored read 68.6 -- on the card's own white art, ahead of the true cursor at slot 4's
22.8. `cursor_glow`/`cursor_slot` named slot 0; `_walk_cursor_to` pressed `move_right`
eight times toward the target, never saw the reading move off 0, and refused; the
play-stall fallback then excluded slots one at a time and every one refused the same way --
total deadlock on a paid match.

**Root cause.** `cursor_slot` takes an unqualified argmax over `cursor_glow`'s raw list, so
a disc-shaped blob that never resolved to a digit can outscore the genuine cursor whenever
its glow window lands on card art rather than backdrop (CLAUDE.md 10.35: any box placed ON
a card reads 60-88% bright whether or not the cursor is there). No ceiling separated a
false on-card reading from a true one, and `_walk_cursor_to` had no way to notice a target
that never moves and try something else.

**Fix.** MERGED 2026-09-20 (12e1d2f). `cursor_glow`/`cursor_slot` exclude a row whose
`y_from == "disc"` and `digit is None` (a disc found, no digit matched -- occurs zero times
elsewhere in the corpus, `probe_disc_none.py`, 20/22 fixtures checked) and cap the argmax at
`CURSOR_GLOW_MAX = 48.0`, the midpoint between the measured true-cursor ceiling (36.1 over
74 labelled frames, `cursor_slot`'s own docstring census) and the on-card false floor (60,
CLAUDE.md 10.35). `_walk_cursor_to` now excludes a slot whose reading never changes across
its full press budget and re-reads with `cursor_slot(exclude=...)`, bounded at 4 slots
(`FALSE_CURSOR_EXCLUDE_MAX`).

**Verify.** `tests/minigame/test_false_cursor_on_occluded_slot.py`: the live fixture reads
slot 4, not 0; the digit/y_from rule and the glow ceiling are isolated with controls; a
scripted walk reaches its target instead of refusing. Three mutants (drop the digit/y_from
rule, drop the ceiling, drop the walk-level exclusion), each caught by a distinct assertion,
restored clean. A skeptic's scan of 1,217 live hands the same night found zero genuine
cursor readings above the new ceiling and 68 false ones, all `digit None` with
`y_from "disc"` -- exactly the population the fix excludes. (The "142 mid-play" figure in
HANDOFF_NOW.md is a pixel distance from the unrelated, unshipped vertical-bound patch, not
a glow percentage -- do not conflate the two.)

**Status.** Merged; live confirmation open: resume the parked match. QA round 4 (dc47548):
FALSE_CURSOR_EXCLUDE_MAX now has a test; because 4 equals the fan's natural exhaustion, the
test also probes a lowered budget to prove the clause is load-bearing.

### I-26  `_clear_strays` refused on a flickered read, not a lift              P0  guard

**Evidence.** `overnight/run_live_20260920h.log`: four "went unreadable DURING this
operation" refusals (slot 0 once, slot 1 twice, slot 3 once), every one followed by a
successful retry a poll or two later. Offline replay of the frame window for the line-14
occurrence (`screenshot_log/run_20260920_220144/`, 29 frames at 10 Hz spanning ~2.9s, the
card never moving and not even that turn's play target) shows slot 0's disc read cycling
between a bogus-but-measured position and `None` several times with nothing pressed near
it: `y_from="disc", digit=None` on 21 of 29 frames (glow 29.9-70.3) against `y_from` fallback
or `kind="unknown"` on the rest, both of which `hand_cursor_look`'s own gating maps to
`None`.

**Root cause.** `_clear_strays` took one `look()` at the top of the operation and compared
it to the caller's baseline with no re-look of any kind, so a slot that happened to land on
a `None`-gated frame at that instant was scored as "went unreadable DURING this operation" —
indistinguishable, at that layer, from a card we had actually just lifted. The 29-frame
probe shows the card never moved; the refusal was decided on a coin flip between two
unstable disc-finder states of the exact same untouched card.

**Fix.** MERGED 2026-09-20 (67f3851): one re-look after `SELECT_RETRY_CONFIRM_SEC`, a
sustained blind is REFUSED, and only a slot untrustworthy at baseline is exempt.
`input_controller._untrustworthy_slots(glow, ys)` marks a baseline slot untrustworthy when
its `y` is already `None` or its glow exceeds `local_hand.CURSOR_GLOW_MAX` (I-25's own
false-on-card ceiling, reused since this layer has no `y_from`/`digit` to ask directly), so
a slot bad from the start never counts as newly-blind. Any OTHER newly-blind slot gets
exactly one extra `look()` after `SELECT_RETRY_CONFIRM_SEC`; if it reads back real and
unselected, the operation proceeds on the fresh read. The first version of this fix
(ecabe6f) instead let a still-`None` slot through whenever the rest of the fan looked
untouched ("at rest"); the skeptic REFUTED that in the dangerous direction — a stray card
OUR OWN PRESS lifts also reads `y=None` and is absent from `sel` (a `None` row is skipped by
`selected_cards`), so `_at_rest` could not tell a lifted-and-blind stray from an
undisturbed slot and would have committed the stray. That fallback is deleted outright: a
slot still unreadable after the one re-look is refused, full stop, unless it was already
proven untrustworthy at baseline.

**Verify.** `tests/minigame/test_stray_guard_ignores_flicker.py`, cases (a)-(e): (a) a
one-frame flicker that recovers on the re-look commits with exactly one extra look; (b) a
baseline-untrustworthy slot (bogus glow or `None` from the start) commits with no extra
look; (c) a genuinely lifted stray that cannot be cleared is still refused (control); (d) our
own press lifts a stray that reads `None` on both the check-look and the re-look — refused;
(e) the mirror of (a), a lift that reverts and reads back real and unselected on the re-look
— commits. Mutation-tested: reverting the re-look branch to the old immediate refusal fails
(a); dropping the glow-ceiling half of `_untrustworthy_slots` fails (b); forcing the deleted
`_at_rest` fallback back to `True` fails (d) (it survived the pre-amendment suite because no
earlier case reached that branch with a still-non-empty newly-blind set after the re-look).
Restored after each; `git diff input_controller.py | grep -i MUTANT` empty. All nine
requested regression files plus `test_no_real_input_under_test_run.py`,
`test_every_test_sets_the_flag.py` and `test_no_shadowed_module_defs.py` pass unmodified.

**Status.** Merged; live confirmation open.

### I-27  A slot flickering to UNKNOWN reset the stall counters and forgot an exclusion   P0  loop

**Evidence.** `overnight/run_live_20260920h.log` lines ~136-150 (main checkout path): hand_index
1 excluded at line 136 ("play REFUSED 3x running on hand_index 1 ... excluding it"), hand_index
3 going UNKNOWN at line 148 while hand_index 1 is still listed as present (`1: 9/0`), and line
150 offering "pitch focus 9" -- `agent_progress/census-20260920/progress.md` section 5 finding 1
identifies that as hand_index 1 coming back on offer, confirmed by reading the log directly.

**Root cause.** `_discard_hand_identity` (orchestrator.py:7358, pre-fix) returned
`tuple(sorted(...))` over every card PRESENT in `hand`. `local_hand_cards` drops a slot it
cannot read for one poll instead of emitting it with `power=None` (`dropped.append(i);
continue`), so the identity tuple is genuinely shorter on a one-poll flicker, and comparing two
such tuples with `!=` treats a missing element exactly like a changed one -- indistinguishable
from a genuine redeal. `discard_stalled` and `play_excluded_slots` both keyed their breakers on
it, so a flicker on any unrelated slot reset the count and forgot the exclusion.

**Fix.** MERGED 2026-09-20 (bce1f4d). `_discard_hand_identity` now returns a `dict` keyed by
`hand_index`, and `_hand_identity_changed(stored, current)` treats two identities as the same
hand unless some `hand_index` readable in BOTH disagrees -- a slot missing from either side is
not a disagreement. On a "same hand" verdict the current poll's readable cards are merged into
the stored identity (`{**stored, **current}`) so a recovered slot compares against the fullest
picture seen so far. Bounds (`DISCARD_STALL_MAX`, `PLAY_STALL_MAX` = 3) untouched.

**Verify.** `tests/minigame/test_stall_identity_survives_flicker.py`: an excluded slot survives
a same-hand flicker on an unrelated slot and the refusal count keeps accumulating across it;
CONTROL, a hand where one readable slot holds a genuinely different card still resets the count
and clears the exclusion, for both breakers. Mutation-tested: reverting `_hand_identity_changed`
to exact dict equality (the pre-fix shape) fails 4 of the new test's checks; restored clean,
`git diff orchestrator.py` shows only the intended change. `test_refused_play_falls_back.py`,
`test_discard_stall_breaks.py` and `test_stall_counters_reset_with_hand_memory.py` pass
unmodified against the fix.

**Status.** Merged.

### I-28  The stray guard refused the engine's own target for going blind on its own lift   P0  guard

**Evidence.** QA round 4 finder reproduced offline; live in
`overnight/run_live_20260920h.log:121-132`: "selected by inference" followed by "went
unreadable DURING this operation" three times running, then the 9 excluded.

**Root cause.** `_clear_strays` never exempted `want` from its newly-blind refusal, and
the commit gate could not see a blind selected target either — `selected_cards` skips a
blind row, so a `want` slot that goes unreadable the instant it lifts (I-21's own
mechanism) is never in `sel` and fails `want <= set(sel)` on the next line even if the
early refusal is fixed.

**Fix.** MERGED 2026-09-20 (aed2468): `want` is exempt from the newly-blind
refusal/re-look, and a blind `want` slot counts as lifted everywhere `sel` is consulted
— but only when it was READABLE at baseline and is blind now (I-21's own signature).
The first version (c286308) counted any blind `want` slot unconditionally and was
narrowed after a skeptic showed it would trust a target that was chronically
unreadable before the operation ever pressed anything, on nothing but being blind and
being `want`.

**Verify.** `tests/minigame/test_stray_guard_exempts_target.py`, cases (a)-(f): (a) the
literal repro, blind-on-lift target with `sel` containing it — commits, one look, no
extra press; (b) CONTROL, a non-want slot blind through the re-look — still refused;
(c) an inferred-selected target not in `sel`, beside a genuinely lifted non-want stray
that cannot be cleared — refused, proving the exemption doesn't mask a real stray; (d)
two simultaneous blind targets with nothing in `sel` at all — commits; (e) an
inferred target beside a non-want slot occluded since baseline — commits, and that
slot is never walked to or deselected (spied); (f) a target blind at baseline too, with
no proof it was ever selected — refused. Two mutants, "count all blind slots as
lifted" and "want blind at baseline counts", each killed by a different case ((e) and
(f) respectively). All 11 regression files pass unmodified.

**Status.** Merged; live confirmation open. Its regression list missed
test_verified_presses_on_match_path.py, whose _clear_strays stub lacked the new keyword;
fixed in 3ef4447.

### I-29  A redeal at a stalled slot that draws the same value inherited the old refusal count   P1  loop

**Evidence.** QA round 4 (not seen live): `_discard_hand_identity` compares a VALUE tuple
`(kind, power, secondary, type)` per `hand_index`, and the roster has only ~18-24 distinct
(power, secondary) pairs. A REAL redeal at a stalled or excluded index that happens to draw a
card sharing the value of the card it replaced reads as "no change" under
`_hand_identity_changed` (I-27's own merge-only-adds fix), and the fresh card silently
inherits the old card's refusal count or exclusion.

**Root cause.** Both stall breakers (`discard_stalled`, `play_excluded_slots`) key entirely
on VALUE identity with no notion of a confirmed deal EVENT at that index. Nothing in
`play_one_turn` ever told the identity tracker "this index was just spent," so a coincidental
value match after a real deal is indistinguishable from a truly unchanged card.

**Fix.** MERGED 2026-09-20 (1abeb4e). Added `note_slot_dealt(hand_index, tactics_index=None)`
(`orchestrator.py`) that pops the index (and, on a play, its tactics slot) out of both
`_PLAY_STALL` and `_DISCARD_STALL`'s stored identity/exclusion/count, called at the two points
in `play_one_turn` where a play or discard is CONFIRMED (not refused) — independent of what
value the next read happens to show. `# ponytail:`-marked simplification: clearing BOTH
trackers' counts unconditionally on every confirm, rather than only the tracker owning the
confirmed action, on the reasoning that within one unchanged hand each breaker's target is a
deterministic function of the pool, so a nonzero count can only belong to the slot actually
being retried — except when a play-refusal streak on slot X is in progress and the hand later
goes weak enough to fire the discard branch on a different slot Y, which forgives X's streak
one cycle early. Judged safe-directioned (worst case one extra refusal cycle, never a wrong
card played); not measured live.

**Verify.** `tests/minigame/test_stall_state_forgets_dealt_slot.py`: (a) a confirmed discard
clears that index's sig/exclusion from both trackers; (b) a confirmed play clears the played
slot AND its tactics slot from both trackers; (c) an unrelated slot's stall state is left
alone by either confirm; (d) 50 polls of the replacement index being merely ABSENT (never
re-read) do not resurrect the forgotten identity, count, or exclusion, and the slot reads
clean, unexcluded, uncounted when it finally reappears. Mutation-tested: dropping the
play-site call fails (b) and (c)'s play-dependent check; dropping the discard-site call fails
(a) and (d); both restored, `git diff orchestrator.py` shows only the three intended hunks.
`test_stall_identity_survives_flicker.py`, `test_refused_play_falls_back.py`,
`test_discard_stall_breaks.py`, `test_stall_counters_reset_with_hand_memory.py`,
`test_should_redraw_incomplete.py`, `test_run_motion_gate.py`,
`test_every_test_sets_the_flag.py` and `test_no_shadowed_module_defs.py` pass unmodified.

**Status.** Merged; not seen live.

### I-30  Phantom draw (substring OCR) scored, then close_result mashed a Give-up dialog open   P0  reader/loop/input

**Evidence.** Match 5 on 2026-09-20: a live turn frame's mound card "JOHNNY DRAWERS" read
as DRAW by the card reader's substring match, at exactly `MIN_PLAYS_FOR_RESULT` plays so no
confirmation ran; a phantom draw was scored, `match_in_progress` cleared, `close_result`
pressed on a live turn which opened "Give up?", 15 unreadable polls, stop; the manager
answered NO and corrected the record.

**Root cause.** Four: the OCR fallback's bare substring match; the `<` boundary at exactly
`plays_this_match == MIN_PLAYS_FOR_RESULT`, a known, deliberately-pinned residual;
`press_verified` accepting a stale False baseline as proof nothing needed pressing; and the
give-up dialog unknown to `run()`.

**Fix.** MERGED 2026-09-20 (e6fbcce): whole-word regex + negative fixture
`phantom_draw_20260920.png`; `_close_result_safely` presses only after a fresh result read;
two consecutive result frames required at the play floor; the give-up dialog answered with
one Circle and a look, never Cross.

**Verify.** `test_result_card_is_read.py`, `test_early_result_double_debit.py`'s rewritten
boundary block, `test_give_up_dialog_recognized.py`, `test_close_result_refuses_stale_read.py`;
four mutants caught, including the skeptic's fresh-read one; 1,340 fixtures swept with zero
give-up false positives.

**Status.** Merged; live confirmation open. QA round 5 (41dd459cad89a71bff9af2bb63881dd78be8bf5e): the give-up test's stub answered from its own press flag rather than the frame, so a stale post-press read went uncaught; it now keys on the frame's capture sequence and that mutant fails.

### I-31  A fresh match's first turn stalled forever on an unreadable phase banner   P0  reader/loop

**Evidence.** overnight/run_live_20260921c.log: a fresh match's first hand held three
tactics cards and two batters, one batter's disc hidden under the lifted neighbour, the
SPEED BOOST's type unread; read_phase had one banner vote and abstained, 15 polls of
"phase not read locally", and the run stopped with unreadable_screens. Frame:
test_fixtures/phase/i31_fresh_match_tactics_batting.png.

**Root cause.** read_phase voted only on BATTER/PITCHER banners, and local_game_state
raised on abstention even on a fresh match whose half is known.

**Fix.** MERGED 2026-09-21 (e23e0f6602267664261b71386d65d60bfba983ca): tactics kinds
vote (swing/speed = batting, pitch/fielding = pitching), and when the reader still
abstains on a readable hand the match's own half decides, logged.

**Verify.** 12 checks, 3 mutants.

**Status.** Merged; live confirmation: resume the parked match.

### I-32  A cursor crossing an occluded slot was refused as "lost", excluding the play   P0  input

**Evidence.** overnight/run_live_20260921d.log (00:52-00:56): a hand read
`0: swing_boost +2, 1: UNKNOWN, 2: swing_boost +1, 3: speed_boost +1, 4: 5/3`. Slot 1's
power disc sat under slot 2's card (CLAUDE.md 10.28's fan occlusion), so `read_hand` gave
that row `y_measured: False` for the rest of the hand. `input_controller._walk_cursor_to`
walked from slot 0 toward slot 4, crossing slot 1, and refused after exactly ONE press:
`lost the cursor after 1 press(es) (glow=[0.0, 0.0, 0.0, 0.0, 0.7]) — refusing`, three
times running on the same hand. The play was excluded and the run stopped with "every
reachable card on this hand has been refused". Frame:
`overnight/crawl/20260921_005556/001_before.png`.

**Root cause.** `local_hand.cursor_glow` returns 0.0 BY CONSTRUCTION for any row whose y
was never measured, so `cursor_slot` reads None whenever the cursor sits on an occluded
slot -- indistinguishable from a dropped press by glow alone. `_walk_cursor_to` only had
I-02's remedy for a blind slot ONE STEP FROM THE TARGET (probe by selection); a blind slot
the walk merely CROSSES had no remedy at all and refused immediately.

**Fix.** `input_controller._walk_cursor_to`, ~1015-1113: when a press reads no cursor,
compute `expected` (the slot one step toward `target` from where the cursor was). If
`expected` is not the target and the walk's own `ys` column -- the same fallback-y gate
I-02's probe already checks -- shows `ys[expected] is None`, "nothing lit" is the expected
reading of an occluded row, not a lost cursor: dead-reckon onto it and let the next press
prove the walk is still live. Bounded to ONE consecutive dead-reckoned step
(`dead_reckoned_last`); a second dark slot right after one still refuses, occluded or not
-- two occluded slots in a row is the mirror case and stays a refusal, no code chains
guesses to cover it. The occlusion check runs BEFORE I-02's probe-select branch (not
after) so "never dead-reckon onto the target" is a real, mutation-catchable guard rather
than an unreachable one: `expected == target` is exactly I-02's own `abs(prev - target)
== 1` condition, so checking I-02 first would make the guard dead code. An occluded
target still falls through to `_probe_select_blind_target`, which already refuses without
a press when `ys[target] is None`.

**Verify.** `tests/minigame/test_walk_crosses_occluded_slot.py`: (1) a single occluded
slot mid-walk costs nothing extra and the log names it; (2) a genuinely dropped press
right after the dead-reckoned step still refuses; (2b) the mirror case -- two occluded
slots in a row still refuse, only the first is dead-reckoned; (3) an occluded TARGET is
never dead-reckoned onto, only I-02's probe (or its own refusal); CONTROL (4) a hand with
no occlusion anywhere still hits the old, byte-identical refusal. Three mutants, each
caught by a different check: dropping the `ys[expected] is None` test is caught by
CONTROL; dropping the one-consecutive-step bound is caught by (2b) (not by (2), whose
second slot is readable and would refuse regardless of the bound); dropping the
`expected != target` guard is caught by (3), which dead-reckons straight onto the
occluded target and returns success instead of refusing. Siblings all still pass:
`tests/rig/test_blind_slot_probe_select.py` (I-02), `test_select_stops_when_lift_
unreadable.py`, `test_verified_presses_on_match_path.py`, `tests/rig/test_no_real_input_
under_test_run.py`, `tests/harness/test_no_shadowed_module_defs.py`.

**Status.** MERGED to main 2026-09-21 (a5e212a), skeptic CONFIRMED WITH NOTES
(coverage gaps folded into the test): an independent review confirmed the diff
matches this ticket, found no overstated claims, and reproduced the fixer's own
three mutants by hand, but found two of its OWN gaps -- the shipped test only
ever walks rightward, so a mutant hardcoding `expected = prev + 1` (dropping the
`prev - 1` branch) survived, and it never separates two occlusions by a clean
read, so a mutant dropping the `dead_reckoned_last` reset also survived. Both
are folded into `tests/minigame/test_walk_crosses_occluded_slot.py` as checks
(5) (a leftward walk, occluded slot 3, must arrive in 4 presses naming it) and
(6) (occluded {1, 3} with readable slot 2 in between, walk 0->4, must arrive in
4 presses naming BOTH). Each mutant reproduced on this checkout and shown to
fail exactly its own check and no other, sha256-verified restored byte for byte
between them.

### I-33  A press off a slot named without a genuine glow read is refused, not retried   P1  input

**Evidence.** `overnight/run_live_20260921f.log` (~01:40): hand
`0: pitch_boost +1  1: 5/1  2: fielding_boost +1  3: 5/0  4: 8/0`, no occlusion, every
slot's y readable. `_verified_select_and_play_inner` walks to `card_index=4`, prints
"verified on 4 after 6 press(es)" (a NORMAL glow-confirmed arrival -- `steps` is nonzero,
which only happens off a direct read; the I-02 probe resets `steps` to 0 on success), then
`_select_verified(4, ...)` selects it, leaving card 4 lifted. A FRESH
`_walk_cursor_to(0, look)` call then begins for the tactics slot: its own TOP-OF-FUNCTION
read sees `glow=[0.0, 0.4, 0.0, 0.0, 0.4]` -- slot 4 still on its structural ceiling
(CLAUDE.md 10.35: "slot 4 never exceeds 11.0 at ANY offset") -- presses once toward 0, and
"lost the cursor after 1 press(es)" refuses. `_unwind_selection` walks back to slot 4 and
deselects it, and the retry a full poll cycle later played the identical card correctly.
Cost: ~15-20s (an unwind-and-retry cycle) on a paid match, for a press section 5 already
measures the console dropping 15.20% of the time, clustered (`P(ignore | previous
ignored) = 0.250`).

**Root cause.** A slot named without a genuine, confidently-clear glow read -- either
because the read barely crossed `CURSOR_GLOW_MIN` (a slot-4-shaped marginal crossing) or
because it was inferred (a lift, or the I-02 probe) -- has a glow that cannot reliably
confirm "still here" either. So when the walk steps off it and the very next look reads
nothing, that is EXACTLY what a dropped press looks like: the cursor may never have left
that slot at all. `_walk_cursor_to` treated every such loss as "lost the cursor" and
refused outright, at the one place a free remedy (retrying the same direction once, since
nothing irreversible has been pressed) was available.

**FIRST FIX WAS REFUTED (2026-09-21) BY AN INDEPENDENT SKEPTIC**
(`agent_progress/issues/I-33-skeptic/progress.md`, `repro_cross_call.py`). It scoped the
new local, `cur_confirmed_blind`, to "True only when set by the I-02 probe within THIS
call" -- and that local resets to False at the top of EVERY `_walk_cursor_to` invocation.
The live event is a call boundary: `_walk_cursor_to(4, ...)` confirms slot 4 by a NORMAL
read (not the probe, per the "verified on 4 after 6 press(es)" evidence above), returns,
`_select_verified` leaves it lifted, and the SEPARATE `_walk_cursor_to(0, ...)` call that
follows has no memory of any of it -- its own top-of-function read is what names `cur=4`,
and nothing in the shipped v1 code marked that as unreliable. The skeptic's repro
(top-of-function read at glow 10.5, sel empty) reproduces the refusal on v1 byte for byte.

**FIX (v2).** `input_controller._walk_cursor_to`: `cur_confirmed_blind` is now
RE-EVALUATED wherever `cur` is set, from TWO independent sources of unreliability, not
just the I-02 probe:

  1. `CUR_TRUSTED_GLOW_MIN = 20.7` (local_hand.cursor_slot's own measured floor for a
     genuine cursor, "20.7 .. 36.1"). A `cursor_slot()` read that clears `CURSOR_GLOW_MIN`
     (10.0) but stays under this floor sits inside CLAUDE.md 10.35's own measured ceiling
     for slot 4 ("never exceeds 11.0") -- a marginal, unreliable crossing rather than a
     confident one. Applied at every normal read, TOP OF FUNCTION included (the nudge
     loop's own read and the initial read both feed the same check), not only inside the
     walk loop.
  2. A NEW top-of-function fallback: if the fan's own glow cannot name ANY cursor
     (`cursor_slot()` returns None) but exactly one card is already SELECTED, that card
     names the cursor -- selection only happens under the cursor, and nothing else can
     move it without a press this call has not yet sent. This is the literal live-log
     mechanism: `sel == [4]` with `glow[4] == 0.4` at the top of the second call.

Both sources set `cur_confirmed_blind = True`; a genuine read (clears
`CUR_TRUSTED_GLOW_MIN`) always RECOMPUTES it (not just resets to False), so an earlier
blind flag cannot leak into a later, unrelated lost cursor -- see the mutant-B fix below.
When a press off a blind `prev` reads nothing, and the walk is not one step from target
(claimed, unmodified, by the existing I-02 probe branch, which runs first and would
otherwise risk overshooting `target` on a second press), press the SAME direction once
more and look again before refusing. Bounded to exactly one extra press per lost-cursor
event (counts toward `steps`/`CURSOR_MAX_STEPS`); if the retry also reads nothing, fall
through to the original, unmodified refusal.

**Deliberately NOT set after an I-32 dead-reckon.** I-32's own bound is stricter than this
fix: "no code chains guesses to cover it" means not even a retry PRESS after a
dead-reckoned step, which `test_walk_crosses_occluded_slot.py` cases (2) and (2b) pin
exactly (2 presses, refuse, nothing further). An early draft of v1 flagged a
dead-reckoned `cur` as blind too, and that broke those two cases (a third press appeared
where they require none) -- caught by running the sibling suite, not by this ticket's own
tests. The dead-reckon branch leaves `cur_confirmed_blind` untouched by that step alone.

**Verify.** `tests/minigame/test_walk_retries_off_blind_slot.py`, 7 cases: (1) prev
confirmed via the I-02 probe (landing on slot 4, a DIFFERENT slot than the call's own
target), one dropped press, one retry that lands on slot 3 -- arrives, exactly one extra
press, log names slot 4; (2) the retry ALSO reads nothing -- refuses exactly as before, 2
presses for that event, nothing further sent; (3) the target is only one step from the
probed slot -- no extra press; the existing I-02 probe branch fires a second time instead,
untouched; CONTROL (4) prev confirmed by a READABLE glow (not inference) -- a lost cursor
still hits the old refusal, with no extra press; (5) THE REFUTED SHAPE, mechanism 1: a
FRESH call's own top-of-function read names cur=4 from a marginal glow crossing (10.5), no
I-02 probe anywhere in this call -- retries and arrives; (6) THE REFUTED SHAPE, mechanism
2, the literal live-log frame: slot 4 already selected (`sel == [4]`) with
`glow=[0.0, 0.0, 0.0, 0.0, 0.4]` at the top of a fresh call -- named from the lift, no
probe, no nudge -- retries and arrives; (7) MUTANT-B GUARD: the probe confirms slot 4
(blind), then TWO genuine strong reads intervene, then a LATER unrelated drop -- must
refuse immediately, proving the blind flag was actually cleared and not just left set.

Four mutants, each caught by a different check, sha256-verified restored byte for byte
between them: (a) dropping the `prev_blind` gate (retry unconditionally) is caught by
CONTROL, which then runs out of scripted frames retrying when it should have refused; (b)
allowing two extra presses instead of one is caught by (2), which runs out of frames on
the now-unexpected third attempt; (c) reordering the retry to run BEFORE the I-02
one-step check is caught by (3), which then hits the retry's own press instead of the
second I-02 probe and runs out of frames; (B, the skeptic's own finding) deleting the
recompute of `cur_confirmed_blind` on a genuine mid-walk read is caught by (7), which then
wrongly retries a later, unrelated drop and runs out of frames.

Reproduced on the ORIGINAL skeptic repro (`agent_progress/issues/I-33-skeptic/
repro_cross_call.py`, unmodified): on v2 it no longer reproduces the refusal -- the retry
fires and consumes the script's third (previously "left unconsumed") frame, then runs out
of frames because the walk now proceeds past where the 3-frame script stops (confirmed
separately with a fully-populated frame set: the walk arrives, `ok is True`, exactly one
retry press). Siblings all still pass, unmodified: `tests/rig/test_blind_slot_probe_
select.py` (I-02), `tests/minigame/test_walk_crosses_occluded_slot.py` (I-32),
`test_select_stops_when_lift_unreadable.py`, `test_verified_presses_on_match_path.py`,
`tests/rig/test_no_real_input_under_test_run.py`, `tests/harness/
test_no_shadowed_module_defs.py`, `tests/harness/test_no_undefined_names.py`.

**Status.** merged c335d42a673f2a7fc92f31642172887e183b2342; skeptic CONFIRMED WITH NOTES
(v1 refuted: the flag was call-local and the live case was a fresh call; v2 covers it via
the selected-card fallback); notes folded in.

### I-34  A second substring matcher scored a phantom draw from a card name (JOHNNY DRAWERS)   P0  reader

**Evidence.** overnight/run_live_20260921j.log ~262-268 (main checkout, read-only): a live
turn frame's OCR-read card banner "JOHNNY DRAWERS" reached the LAST-RESORT OCR path
(`orchestrator.local_game_state`, ~4325-4345 -> `result_ocr.read_banner`, wired in only
after templates, ban counter, dealer prompt and hand reader all decline). `match_word`
scored DRAW as a substring of DRAWERS, `run()` logged a draw for a match still in progress
(6 total), and the real result screen that followed was discarded as "already scored" (log
~line 374). Money unaffected; the record was wrong by one draw.

**Root cause.** I-30 (2026-09-20) fixed the SAME bug shape in `local_state.read_result_card`
(the TEMPLATE reader's own last-resort card path) with a whole-word regex. `result_ocr.py`'s
`match_word`/`_similar` is a completely SEPARATE matcher -- the orchestrator's own OCR
fallback -- and I-30 never touched it. Its rule was `seen == word or seen in word or word
in seen`, a bare containment test, so `"DRAW" in "DRAWERS"` matched.

**Fix.** `result_ocr._similar` requires the WHOLE OCR token to equal the vocab word, with
two OCR-noise tolerances: UP TO TWO dropped letters (`WINE` -> WINNER -- pre-existing
behaviour; see below, this was mis-stated as "one dropped letter" in the first version of
this fix) and one trailing letter standing in for a misread `!` (`DRAWI` -> DRAW). A token
LONGER than the word for any other reason -- `DRAWERS`, `WINNERS`, `LOSERS` -- no longer
matches, however much of the word it contains. `match_word` tries two kinds of candidate
per OCR text: the individual runs split on non-letter boundaries (`re.findall(r"[A-Za-z]+",
...)`, so "JOHNNY DRAWERS" is checked as JOHNNY and DRAWERS, never concatenated into one
string a containment test could hit) and the text's letters joined into ONE string with
every space/digit/punctuation dropped (see the recall-regression paragraph below). Neither
candidate can reopen the bug: a joined card name like `JOHNNYDRAWERS` is still LONGER than
every vocab word, so `_similar` refuses it exactly as it refuses the split tokens.

grep for `DRAW` across `result_ocr.py`, `local_state.py`, `orchestrator.py` and
`tools/read_banner_paddle.py` found exactly one other matcher: `local_state.
read_result_card`'s I-30 fix (`\b{k}\b`), already whole-word and untouched here. The
remaining hits in all four files are prose comments and docstrings, not matching code.

**REFUTED AS FIRST SHIPPED (6686603), FIXED ON THE SAME BRANCH.** The first version added a
second, independent call-site layer (`result_ocr._match_word_strict`, wired into
`read_banner`) that refused a match outright if the OCR band carried any other alphabetic
token longer than 2 letters, on the theory that a real banner shows the word alone. An Opus
skeptic (`agent_progress/issues/I-34-skeptic/progress.md`) cropped `result_ocr.BAND` from
every fixture in `test_fixtures/result_screens/` and VIEWED it: the crop always contains the
matchbox-ring lettering around the medallion (CAMEL BURN, SPARK-D, SAFETY MATCHES, SPIKE-D),
on every class including the phantom-draw frame itself -- so the veto refused every genuine
WINNER/LOSER/DRAW read. It also refuted the claimed failure direction: a None from OCR here
(not "unavailable", not "missing") reaches orchestrator.py:4241-4259's "the template answer
is not trusted alone" branch, which is static on an unchanging real result screen and so
repeats every poll until MAX_STUCK_ATTEMPTS (15) -- the run ends UNSCORED, the exact 35s-
stall failure this module exists to prevent, not the "one extra poll" the first write-up
claimed. **The veto is REMOVED**: `read_banner` calls `match_word` directly again;
`_match_word_strict`/`_extraneous_alpha_tokens` are deleted, along with the four test checks
that pinned them. Do not re-add a "no other token" rule without measuring the real `BAND`
crop first (CLAUDE.md 10.32 -- an unmeasured claim about the failure direction is exactly
what got this wrong).

The same skeptic found two more real findings, both fixed on this branch:

- **A recall regression from dropping the old joined-alpha candidate.** The pre-I-34 reader
  joined every alpha character of an OCR text into ONE string before matching (digits and
  spaces silently dropped), so it caught a word OCR splits across spaces (`"W I N N E R"`)
  or digit-corrupts (`"L0SER"`). Tokenising on word boundaries lost this. Restored as an
  ADDITIONAL candidate alongside the split tokens (`match_word` now tries both per text),
  verified NOT to reopen the bug: the joined form of a card name (`JOHNNYDRAWERS`) is still
  longer than every vocab word.
- **The docstring understated the dropped-letter tolerance.** `len(seen) >= len(word) - 2`
  allows TWO drops, not the one the first write-up claimed (`WINE`, `INNER`, `WIER` and 13
  more all match WINNER). Pre-existing behaviour, not introduced by this ticket; documented
  accurately rather than tightened, because tightening a reader on the money path is itself
  an unmeasured change and this tolerance has been live and correct since the module's first
  commit. The floor `len(seen) < 4` caps how much of it any given word can use: DRAW gets
  zero drops, LOSER one, only WINNER the full two -- now stated in `_similar`'s docstring
  with the reasoning. `_EXCLAIM_NOISE`'s dead `"1"` (tokens come from `[A-Za-z]+`, so a token
  can never end in a digit) is removed rather than made reachable; no design needed a digit
  tolerance.

**Verify.** `tests/minigame/test_result_ocr_whole_word.py`, rewritten: (1) the exact bug --
`match_word([("JOHNNY DRAWERS", 1.0)])` -> None, and the joined form `"JOHNNYDRAWERS"` ->
None too; (2) `DRAWERS`/`WINNERS`/`LOSERS`/`PITCHERBATTER` each refused as real, longer,
different (or non-vocabulary) words; (3) the vocabulary and both OCR-noise tolerances
(`WINER`, `WINE` for the 2-drop case, `DRAWI`, a real `DRAW!`) read correctly, and a THIRD
dropped letter (`WIE`) is refused; (4) card banners (`PITCHER`, `BATTER`) and junk
(`BANNEDCARDS`, `""`) still refused; (5) tokenised matching still finds a result word beside
other text (`"THE WINNER"` -> win); (6) the recall-regression cases -- `"W I N N E R"` ->
win, `"D R A W"` -> draw, `"DRA W"` -> draw, `"L0SER"` -> loss; (7) THE WIRING -- a new test
drives the real `read_banner` end to end through a stubbed `_worker`/`_readline` (no
`paddle_venv` needed) with `texts=["JOHNNY DRAWERS"]` -> None and `texts=["DRAW!"]` -> draw,
so a future edit that disconnects `read_banner` from `match_word` fails a test rather than
reaching the live rig unnoticed.

Five mutants, each caught by a disjoint set of checks and nothing else, restored byte-for-
byte (sha256) between them, `__pycache__` not implicated (`-B` throughout, no `.pyc` ever
written): (i) tokenise on whitespace only (`r"[A-Za-z]+"` -> `r"\S+"`) fails the `DRAW!`,
`L0SER` and wiring-`DRAW!` checks (3); (ii) the call-site veto no longer exists to mutate
(removed as refuted) -- N/A, superseded by the wiring mutant below; (iii) restore
containment in `_similar` fails the exact-bug, joined-form, `DRAWERS`/`WINNERS`/`LOSERS` and
wiring-`JOHNNY DRAWERS` checks (6); (iv) drop the `!`-as-letter tolerance fails exactly the
`DRAWI` check (1); (v) `read_banner` bypasses `match_word` (returns a hardcoded string
instead) fails exactly the wiring-`DRAW!` check (1) -- confirming the wiring test earns its
keep. Siblings run clean: `tests/minigame/test_close_result_refuses_stale_read.py`,
`tests/minigame/test_run_debit_and_scoring.py`, `tests/harness/test_no_shadowed_module_
defs.py`, `tests/harness/test_no_undefined_names.py` all pass. `tests/minigame/
test_result_reader.py` has one PRE-EXISTING, unrelated failure in this worktree --
`diagnostics/20260910_103221_5018/screen_at_stall.png` does not exist here -- reproduced
identically both before this ticket's changes and after the redo, so it is not this fix's
doing.

**Status.** Fixed on branch (whole-word matcher CONFIRMED by the skeptic; call-site veto
REMOVED per the same skeptic's refutation), redo complete, awaiting a second skeptic pass on
the redo.

### I-35  Two post-reveal screens are unrecognised, dropping the at-bat log row   P2  evidence

**Evidence.** `agent_progress/reveal-drops/progress.md` (ESTABLISHED): the "NEW INNING"
half-boundary banner and the settled reveal-recap tableau (cards on the diamond, no hand
fan) both fall through `local_game_state()` to UNRECOGNISED SCREEN; `MAX_PENDING_READ_
FAILURES=2` drops the pending match_log row on the 3rd poll; 5 rows dropped in
`run_live_20260921i.log`, more in 21j/21n.

**Root cause.** No named screen case for either.

**Impact.** Logging loss only (nothing downstream reads the pending row).

**FIXED, offline worktree, 2026-09-21.** Two new local readers, `local_state.
is_new_inning` (OCR on a fixed caption band, requiring "NEW" and "INNING" as whole
words) and `local_state.is_reveal_recap` (`center_card_edge_fraction` + "no 5-card
fan", composed with `read_result`/`table_prompt.at_table` as exclusions plus a
bright-page gate for the ban/pause notebook shape -- edge alone overlapped badly
with result/prompt/ban screens, CLAUDE.md 10.4; see the docstrings for the measured
populations). Wired into `local_game_state()` AFTER result/ban/prompt/turn, returning
named `"new_inning"`/`"reveal_recap"` states instead of the UNRECOGNISED SCREEN gap.

`run()`'s pending-matchup resolution now skips (rather than "unscorable"-drops) on
these two screens, so the row waits for the next real "turn"/"result" read instead of
being dropped on the very poll that correctly identified the gap. Bounded:
`TRANSITION_SCREEN_MAX_SEC` (30s, over 2x the longest measured dwell of 6.6-13.7s) --
a transition that never advances is still treated as stuck and the row is dropped, so
a frozen or misidentified screen cannot wait forever.

**Found while building this:** the gap also shows "PLAY BALL!", "ROUND N", "PLAY AS
THE BATTER/PITCHER" captions and a fleeting "HOME RUN!", none of which either detector
promises to cover (`is_reveal_recap` catches most of them as a side effect of its
geometric signal, not as a claim). Two `test_fixtures/screens/turn__0.jpg` /
`turn__1.jpg` fixtures are mislabelled -- viewed directly, they are the HOME RUN!
caption family, not turn screens (CLAUDE.md 10.15) -- left as-is since nothing here
owns that directory, noted in `agent_progress/issues/I-35/measure_screens.py`.

**Tests.** `tests/minigame/test_transition_screens_recognised.py`: both detectors
against pinned positives and the five required negatives (turn with fan, result, ban,
dealer prompt, pause book, each filtered by the reader that already owns its
category, not by folder name); `local_game_state()` end to end; a pending row
surviving 6 polls of each transition screen and being logged on the next turn; a
CONTROL proving 3 genuinely-unreadable polls (the pre-existing, unmodified
`MAX_PENDING_READ_FAILURES` path) still drop the row; the 30s bound firing. 9
mutants across three categories (each detector forced True, the bound dropped, the
recognised screens routed through the old unrecognised-screen path), each caught by
a different assertion, files restored byte-for-byte (sha256) between mutants.
`tests/minigame/_run_harness.py` gained one additive capability (a scripted screen
entry that is an `Exception` now makes `read_state_for_turn` raise it, mirroring
`play_results`' existing shape) -- no existing test passes an `Exception` there, so
this is backward compatible.

**Opus skeptic round, 2026-09-21 (`agent_progress/issues/I-35-skeptic/progress.md`,
worktree head 63edc52): CONFIRMED WITH NOTES.** 9,966 archived frames scanned (both
live logs in full, every fixture dir), 2,525 detector firings, **0 on a turn, result,
ban or dealer-prompt screen** -- no refutation. Measured durations: new_inning
1.4-1.7s (7 episodes), reveal_recap 3.7-12.6s (36 episodes), both well under the 30s
bound. Money path (start_match, the debit, C1/C2/C3/C5, close_result) confirmed
textually unchanged. Of 6 planted mutants, 3 survived and were fixed here, all
re-verified CAUGHT after the fix (sha256 restored both times: `local_state.py
cd042a6a...`, `orchestrator.py 8a78168a...`):

- **A (`is_reveal_recap`'s no-hand-fan term rejected 0 of 9,966 frames -- inert).**
  Kept rather than removed (the code's own contract: a fan present must mean "not a
  recap" regardless of the diamond), now pinned by a MANUFACTURED fixture
  (`test_fixtures/screens/reveal_recap_with_fan_synthetic.jpg`,
  `agent_progress/issues/I-35/build_fan_composite.py`: a real fan crop pasted onto a
  real recap frame's hand region, centre region untouched) that isolates the fan
  check as the only thing rejecting it. Docstring corrected to say so plainly rather
  than claim it as a fourth separating signal.
- **B (the pending-row skip's NARROWNESS was unpinned -- the CONTROL used a raised
  Exception, never a screen literally named "other" through the success path).**
  Added a harness case: `["turn"] + ["other"] * N` with no trailing "turn" (a first
  draft had one and it rescued the row under BOTH arms, proving nothing) --
  baseline resolves (logs) the row on the first "other" poll (its default payload
  carries real, not None, score fields); a mutant widening the skip to also exempt
  "other" leaves it unresolved. logged==1 pins the narrow scope.
- **E (whole-word vs substring in `is_new_inning` measure IDENTICAL on all 9,966
  frames).** Not a measured separation; corrected the docstring to say it is
  insurance against the I-30/I-34 substring-collision shape, kept for that reason
  alone. Left unpinned by a mutant deliberately -- the skeptic's own instruction
  scoped this one as a documentation fix, not a code-behind-a-test gap, and forcing
  a synthetic fixture to fabricate a difference the measurement says does not exist
  would misrepresent it as more than insurance.

Also fixed: the orchestrator.py comment on `transition_screen_since` claimed an
"uninterrupted" clock; an unreadable poll in between does NOT reset it (the raise
path's `continue` sits before the reset line), so it spans the whole gap, not just
recognised-screen runs -- corrected, kept (right direction: it still bounds the
total wait). Added a harness case pinning the skeptic's noted (non-refuting)
behavioural delta: "new_inning"/"reveal_recap" DO clear `acted_screen` (unlike
"other"), so a `result -> reveal_recap -> result` sequence was checked directly
rather than just argued -- scores exactly once, `match_in_progress` (QA1-F2)
independently blocks the double-score N2's `acted_screen != "other"` clause cannot
see here. (Measured while building it: the second result read still presses
close_result to dismiss the overlay even though it does not re-score -- 2 presses
across 2 sightings is correct, not a symptom; an earlier draft of this test wrongly
asserted exactly 1 press.)

**Status.** Merged 26255bcace2b87b48dff5e24d3f3c4660d35313f, skeptic CONFIRMED WITH
NOTES, follow-up 29469b1 closed mutants A and B; E is docstring-only. Awaiting live
verification (this ticket is offline-only; a live run is what would confirm the
measured 6.6-13.7s dwell and the 30s bound against a real match rather than a
scripted one).

### I-36  The half's second discard is refused three times, then the stall breaker plays   P1  input/loop

**Evidence.** `run_live_20260921j.log` ~592-618 ("confirm_discard did not register —
discards_left is still 1") and `run_live_20260921n.log` (the last "the discard was
REFUSED 3x on this exact hand" block: "select_card did not land (attempt 1..4)", "never
landed after 5 attempts", three polls). Both in the pitching half with 1 discard left; the
first discard of the same half worked. Frames: `screenshot_log/run_20260921_080311/`
(main checkout).

**Root cause.** ESTABLISHED, read-only, from `agent_progress/issues/I-36/progress.md`
(copied into this worktree's `agent_progress/issues/I-36/`). Target slot 3 (the 5/0
pitcher, weakest by `(power, secondary)`) genuinely lifts on the first `select_card`
press. For 2-5 seconds afterward, while it overlaps its neighbour in the fan, `read_hand`
misreads its row as `kind='tactics', digit=None, type=None, y_from='fallback'` -- a REAL
(wrong) y, not a None one. `orchestrator.hand_cursor_look`'s null rule (~line 7465, before
this fix) only treated a row as position-unknown when `y_measured is False` OR the row
was NOT typed 'tactics' and came from a fallback position -- `kind == 'tactics'` skipped
the null, so `_ys[3]` read a real number, `_select_verified` concluded the press "did not
land", and pressed `select_card` AGAIN: a TOGGLE, which put the just-lifted card back
down. Repeats ~15 times (3 polls x up to 5 attempts) over ~40s without the discard ever
committing. This is I-37's shape one layer over: I-37 fixed whether the FAN is admitted
at all; this is about how one ROW inside an admitted fan gets typed. Measured directly:
I-37 (already merged into this branch) does NOT fix it -- 167 of 378 frames in the
failing window (`08:14:49-08:15:27`, `screenshot_log/run_20260921_080311/`) still misread
slot 3 exactly this way with I-37's fix in place.

**Fix v1.** `orchestrator.hand_cursor_look` only: a row is now ALSO treated as
position-unknown when `kind == 'tactics'` AND `digit is None` AND `type is None`.
`type` is read from the card's own banner and populated whenever that banner is
legible, which is the normal case for a genuine tactics card -- so `type is None` is
the discriminator between a genuine tactics card and a garbled lifted row typed
'tactics' with no banner actually read. This lets the EXISTING I-21 "selected by
inference" rescue in `_select_verified` catch the case, with no new machinery.

**v1 WAS REFUTED, NARROWLY, BY AN INDEPENDENT SKEPTIC** (`agent_progress/issues/
I-36-skeptic/progress.md`, two repros run against the real code, not committed).
Before v1, `_ys[i]` could never go None for a `kind=='tactics'` row at all -- the
pre-I-36 rule explicitly excluded `kind == "tactics"` -- so I-21's inference branch in
`_select_verified` (~1323-1327) was STRUCTURALLY UNREACHABLE for a tactics target; only
a real, geometric `target in sel` could confirm one. v1's widened null rule removed
that exclusion for EVERY tactics row, garbled or genuine, which made the inference
newly reachable on a TACTICS TARGET too -- not just on a misclassified player lift,
which is the only case ISSUES.md's control paragraph had analysed. `_clear_strays`'s
`_want_inferred` (~1554-1556, ~1577-1580) uses the IDENTICAL heuristic independently, at
commit time. Both are exploitable: a genuine tactics target whose `select_card` press is
DROPPED and whose banner transiently misreads `type=None` on the SAME look that follows
is then named "selected by inference" although it never lifted -- `confirm_play`/
`confirm_discard` then commits the OTHER (genuinely selected) card only, silently (a
lost boost, not a wrong card, and nothing distinguishes it in the log). Measured against
real frames (`screenshot_log/run_20260921_080311/`, unstubbed reader): the genuinely-
ambient (not-lifted) version of this misread is RARE, ~0.4% of tactics-row instances (5
of ~1,145 measured), longest observed run on the same slot 4 frames -- under
`SELECT_RETRY_CONFIRM_SEC` (1.6s) -- but reachable through the shipped code exactly as
v1 wrote it, confirmed by a working repro, not merely argued.

**Fix v2 (this worktree).** The widened null rule in `hand_cursor_look` is UNCHANGED --
it still cannot tell "garbled by an overlap" from "this banner just missed a read" from
one frame alone, and does not try to. Instead the INFERENCE that CONSUMES the null is
gated on what the row was typed AT BASELINE, before any press touched it:
`_select_verified` now also captures the target's baseline `kind` (from the very first,
pre-press look) and refuses to trust the inference when that baseline kind was
'tactics' -- I-36's actual bug (a PLAYER card mid-lift, misread as tactics) always has a
baseline kind of 'player', so it is unaffected and still rescued; the skeptic's exploit
(a genuine, untouched tactics card) always has a baseline kind of 'tactics', so the
inference is now refused and the ordinary retry-and-look loop runs instead -- exactly
the pre-I-36 behaviour for that slot, restored. `_clear_strays`'s two `_want_inferred`
sites get the SAME gate via a new `kinds0` parameter, threaded from its two callers
(`_verified_select_and_play_inner`, `select_and_discard`) the same way `ys0` already is
-- both already take an identical baseline look for `ys0`'s own sake, so `kinds0` is the
same look's `.kinds`, not an extra capture.

**The plumbing, because it decided where the gate could live.** `hand_cursor_look`'s
4-element return (`glow, ys, n, sel`) is UNCHANGED in shape -- ~20 call sites in
`input_controller.py` alone unpack it positionally, and so does every test's own
`look()` stub, so widening it to 5 elements would be a breaking change everywhere
rather than a fix in one place. Instead `sel` is now `orchestrator._CursorSel`, a `list`
subclass that behaves as a plain list to every existing consumer (`in`, `sorted()`,
`set()`, `==`, all defer to `list`) and additionally carries `.kinds`, the per-slot kind
from the SAME look. `getattr(sel, "kinds", None)` is how a caller reads it; a `look()`
that returns a plain list (any test stub, any caller written before this) supplies no
kinds and the gate is then PERMISSIVE -- unchanged, pre-tightening behaviour -- which is
why I-21's own sibling test (a player-only scenario) needed no changes.

**"Never a wrong play" is WITHDRAWN as stated; replaced with what the gate actually
proves.** The v1 write-up's control paragraph claimed the residual risk "always resolves
in the safe direction ... never a wrong play" for ANY tactics row; the skeptic's repro is
the direct counterexample, on the TARGET path specifically. v2's gate closes exactly
that gap -- a TACTICS-baseline target can no longer reach a commit via inference alone,
only via a real geometric read or an exhausted, refused retry -- and this is verified
below (case 4), not merely argued. What is NOT re-proven, and is not claimed to be: that
a PLAYER-baseline target could never ALSO produce a coincidental false-positive
inference (i.e. read as tactics/typeless while genuinely never lifted). The mechanism
I-36 itself measured -- pixel overlap between adjacent cards, which only occurs once a
card is physically raised above its fan neighbours -- gives a REASON to expect a resting
player card cannot trigger the same misclassification, but that reason is read from the
code and the corpus census, not a fresh measurement of THIS specific sub-case, so it is
recorded here as ESTABLISHED-by-mechanism rather than ESTABLISHED-by-measurement
(CLAUDE.md 10.32).

**Verify.** `tests/minigame/test_lifted_discard_row_rescued.py`, three copied real
frames from the failing window (`test_fixtures/hand_reads/i36_lifted_discard_before.jpg`,
`_garbled.jpg`, `_after.jpg`, real `cp`, never symlinked) plus one synthetic pair and the
skeptic's own repro shape, four cases: (1) `_select_verified(3, ...)` driven with a
stubbed `orchestrator._grab_settle_regions` returning the real before/garbled/garbled
frame sequence (a PLAYER-baseline target) is rescued by inference -- exactly ONE
`select_card` press, `sel == [3]`; (2) CONTROL on the SAME garbled frame: slot 2
(fielding_boost, a genuine tactics card whose banner DID read) keeps its measured y,
while slot 3 is nulled; (3) a SYNTHETIC player-baseline before/after row pair (stubbed
`local_hand.cursor_glow`) reproduces the same tactics/None/None-after-press shape and is
also rescued with one press; (4) THE SKEPTIC'S REPRO -- a SYNTHETIC TACTICS-baseline
target, its first press scripted as dropped (y never leaves rest across two garbled
type=None looks) -- must NOT be named selected by inference, and the retry that actually
lands (a genuine lift, banner reads fine again) must succeed on its own geometric merits;
asserts exactly 2 presses and that every scripted frame was consumed (an early,
wrongly-inferred return would have left frames unconsumed). Three mutants, each caught
by a different check, sha256-verified restored byte for byte between them: (a) revert
the widened null rule to the pre-v1 rule -- caught by (1), which exhausts its scripted
look() frames retrying select_card a second time and crashes with an unconsumed-queue
IndexError (the same "runs out of scripted frames" shape I-33's own tests use); (b) drop
the `type is None` guard (null unconditionally on any tactics/fallback row) -- caught
exactly by check (2), the CONTROL: slot 2's genuine, correctly-read tactics row gets
wrongly nulled; (c, the skeptic's new mutant) revert the baseline-kind gate in
`_select_verified` (`if _bk != "tactics":` -> `if True:`) -- caught exactly by check (4):
the dropped press on the genuine tactics target is wrongly named selected on ONE press
instead of retried, and a scripted frame is left unconsumed. `digit is None` in the null
rule is DROPPED, not pinned: the skeptic's own mutant (drop only that half, keep `type is
None`) SURVIVED v1's full suite -- `digit` never varies for a tactics row by
construction, so the clause contributed no selectivity, and an untested clause that
looks load-bearing is worse than none (CLAUDE.md 10.9); `type is None` is the
semantically correct discriminator on its own. Siblings run clean, unmodified:
`tests/minigame/test_select_stops_when_lift_unreadable.py` (I-21),
`tests/minigame/test_verified_presses_on_match_path.py`,
`tests/minigame/test_stray_guard_exempts_target.py`,
`tests/minigame/test_stray_guard_ignores_flicker.py`,
`tests/minigame/test_false_cursor_on_occluded_slot.py`,
`tests/minigame/test_hand_read_two_lifted.py` (I-37),
`tests/minigame/test_walk_retries_off_blind_slot.py` (I-33),
`tests/harness/test_no_shadowed_module_defs.py`, `tests/harness/test_no_undefined_names.py`.

**Status.** merged 87c683c409ca54de79f4bb41c9636068be89f43c; skeptic v1 REFUTED narrowly
(tactics-target inference), v2 CONFIRMED WITH NOTES (kinds0 threading now pinned).

### I-37  A selected card's own disc can be absent from `strong`, blinding the fan gate   P0  reader

**Evidence.** overnight/run_live_20260921j.log:844-849 (07:50): hand `0: UNKNOWN
1: swing_boost +1 2: 5/3 3: 5/2 4: 4/3`, the engine selected slot 2 then slot 1
(attaching the boost), both verified, and the very next read stalled: "cannot read
the fan after select_card (rows=0) -- refusing". A second live occurrence at 08:00,
ONE card lifted (`0: Fielding Play +1 | 1: Pitcher 9/2 LIFTED | 2: Pitcher 7 |
3: Pitcher 9 | 4: Pitcher 6`), same shape: `read_hand` returned 3 rows, none with a
measured y. Frames: `test_fixtures/hand_reads/i37_two_lifted_20260921.png`,
`i37_one_lifted_20260921.png`.

**Root cause.** `read_hand`'s "is the fan there" gate (I-32's neighbour, the
2026-09-20 COUNT fix in `local_hand.py`) counted only `_strong_discs(img)` --
discs found as an isolated dark digit ringed by white, at `DARK_THRESHOLDS`
(110/90/130). A SELECTED card's own disc often needs a threshold ABOVE that range
to register at all (it brightens on lift; that is what `RAISED_DARK_MAX` exists
for elsewhere in this file), so it can be entirely absent from `strong` while
sitting, at the right position, in the WHITE-DISC or WREATH candidates
`_read_fan` itself already pools from (`_white_discs`, `find_tactics`). On the
two-lifted frame, `_strong_discs` found 4 candidates and only ONE cleared
`FIT_MAX`; `_white_discs` finds the selected player card's own disc at cost 15.7
(comfortably under `FIT_MAX` -- the cost formula `|dx| + |dy|/3` weighs a pure
vertical lift lightly, and a white-disc blob's x is cleaner than a noisy partial
digit-in-disc crop), invisible to the gate that decides whether to call
`_read_fan` at all.

**Fix.** `local_hand.py`: `read_hand`'s gate is now `_fan_looks_present(img,
strong, s)`, which pools `strong` + `_white_discs` + `find_tactics` (the SAME
candidates `_read_fan` itself reads from, deduped via the existing `_free`
bookkeeping), takes the BEST cost PER SLOT (0..4), and requires `FIT_MIN_DISCS`
slots at or under `FIT_MAX` -- same two constants, nothing invented.
`_read_fan`/`_read_ungated` are untouched.

**Verify.** `tests/minigame/test_hand_read_two_lifted.py`: both live fixtures read
5 rows, every row `y_measured`, `selected_cards` names exactly the lifted slot(s)
([1, 2] and [1]), the lifted cards' own kind/type/digit are correct, the untouched
resting cards read unchanged; a CONTROL fixture with no selection (`hand_cursor/
cursor_on_1.png`) reads byte-identical digits to before the fix; a negative-control
fixture (`overnight/local_hand/hand_1788963163511615000.png`, the same one I-32's
neighbour test uses) is still rejected as a non-fan. Three mutants, all caught:
(1) reverting to the old strong-only gate and (2) keeping the broadened
candidate pool but taking the FIRST candidate per slot instead of the best
(min-cost) one -- both caught end to end, row count collapses to 4/3 and the
file raises an IndexError (`strong`'s own bad candidate for the lifted slot is
seen before the good white-disc one, so "first wins" reproduces the same stall
the fix exists for); (3) replacing the per-slot dedup with a raw count over the
pooled candidates (an independent skeptic's finding, 2026-09-21: this survived
every local_hand test in the repo including this file's first version) --
caught by check (e), two synthetic same-slot candidates >25px apart (so
`_free`'s own dedup does not collapse them first) that a raw count wrongly
admits and the deduped gate correctly refuses. sha256-verified restored byte
for byte between all three mutants.

**Regression check.** `agent_progress/issues/I-37/probe6_corpus_regression.py`
(not part of the suite, too slow): over 2,396 archived hand crops
(`overnight/local_hand/*.png`) plus the two fixtures above and the two
`test_fixtures/selected_card/` fixtures I-32's neighbour test uses, the broadened
gate agrees with the old (strong-only) gate on every frame except 4 -- ZERO
frames flip from admitted to rejected, and the 4 newly-admitted are both I-37
fixtures plus 2 archived corpus frames whose paid-model "vision" label in
`agreement.jsonl` (never trusted for card VALUES, fine for card COUNT) confirms
are genuine five-card fans the old gate was dropping for no reason.

**CORRECTED 2026-09-21, caught by an independent skeptic.** The probe's first
version opened the two I-37 fixtures with `Image.open()` directly -- they are
FULL 1920x1080 frames, not hand crops -- so at ~2x calibration scale every
raw-pixel size gate rejected every disc on them and BOTH gates rejected BOTH
fixtures; the script's own tally then said "2 newly-admitted", not 4, and never
exercised the fixtures the fix targets at all (the fix itself, verified through
`orchestrator.crop_gameplay_regions` the way `test_hand_read_two_lifted.py`
and production both do, was never in question). Fixed by cropping the two
fixtures through `orchestrator.crop_gameplay_regions(img)["hand"]` before
either gate sees them, matching the test. Re-run, it prints exactly:

    total files: 2400   both admit: 462   both reject: 1934
    old-admits-new-rejects (BAD): 0   new-admits-old-rejects (newly fixed): 4

naming the four files above (`agent_progress/issues/I-37/probe6_corrected_output.txt`).

**Status.** merged 3bd69d56c183d7cc1dff2fc49f7f4853758d70e0; skeptic CONFIRMED WITH
NOTES (probe corrected, dedup pinned).

**Status.** Merged to main (3bd69d5). Independent skeptic round 2026-09-21
(`agent_progress/issues/I-37-skeptic/progress.md`): CONFIRMED WITH NOTES -- the
fix itself was never in question; two write-up/coverage gaps were found and
both fixed on this branch (the corpus-regression probe's fixture scale bug,
and the missing per-slot-dedup mutant), see above.

**FOLLOW-UP, found on main after merge: `local_state._fan_discs` was a SECOND,
STALE copy of the same "is the fan there" gate, and I-37 never touched it.**
Main's full suite showed one non-pre-existing failure,
`tests/minigame/test_hand_memory_persists.py` -- "the file carries a half
stamp derived from the hand itself: phase written by local_hand_cards was
None". Bisected against the pre-I-37 `local_hand.py` (ccdd46b): passes there,
fails with the I-37 gate. Untestable in this worktree before now because the
test globs `agent_progress/deal-frames/` (gitignored, absent here) -- copied
in read-only from the main checkout (`cp -r`, never symlinked) to reproduce.

**Mechanism.** `local_state._fan_discs` (feeding both `player_discs` and
`read_phase`'s tactics votes) carried its OWN inline reimplementation of the
gate -- the OLD median-residual check, never updated through the 2026-09-20
count fix or I-37's broadened pool. Its own docstring's claim ("exactly one
place decides which slot a disc belongs to") was already false of the GATE,
only true of the per-slot assignment below it. On a genuine hand with 2 of 5
slots occluded (`agent_progress/deal-frames/20260908_235423_patch65_66_67/
loss_0008448_slot4/f0008425.png`, now `test_fixtures/hand_reads/
i37_fan_discs_disagreed_with_read_hand.png`): `local_hand._strong_discs` finds
2 candidates at cost [19.3, 33.3]; `read_hand`'s fixed gate (I-37) admits it
(pools in the two players' own discs among others) and returns 5 rows, 2
correctly marked unreadable; `_fan_discs`'s stale median gate takes
`fit[1] = 33.3 > FIT_MAX (20)` and rejects the SAME frame outright, so
`read_phase` saw zero votes and abstained (`cards: 0`) on a hand with two
perfectly legible player banners reading "batting" at 0.905 and 0.898.

Not a case of the widened gate admitting a non-fan (`read_hand`'s call is
correct: two of the five cards genuinely are unreadable, the hand plays
without them per CLAUDE.md 10.28, and the two THAT read are plainly real
player cards) -- it is a second, drifted copy of the gate never brought in
step with the first.

**Fix.** `local_state.py`: `_fan_discs` now calls `local_hand._fan_looks_present`
instead of reimplementing the gate, so it cannot drift from `read_hand` again.
`orchestrator.local_hand_cards` and `local_state.read_phase` themselves are
untouched, per the diagnosis instruction -- the bug was one layer below both.

**Verify.** New check (d) in `tests/minigame/test_phase_from_tactics_and_match_
state.py`: on the fixture above, `read_hand` returns 5 rows, `_fan_discs`
agrees a fan is present, `read_phase` gets 3 real votes and derives `batting`.
One mutant (revert `_fan_discs` to the old inline median gate): all three new
checks fail (`_fan_discs` -> None, `cards: 0`, phase -> None), exit 1;
`local_state.py` restored byte-for-byte after (sha256
89c96fe58f5d43fee210fd23161c0ac7feb7137555ace17db4fcc7508a88a3a5, verified
equal before and after). Re-ran `test_hand_memory_persists.py` (now with the
copied `agent_progress/deal-frames/` present), `test_hand_read_two_lifted.py`,
`test_deal_gate_arms_on_confirmed_play.py`, `test_readable_hand_gate.py`,
`test_phase_from_tactics_and_match_state.py` -- all five exit 0. The copied
`agent_progress/deal-frames/` (gitignored, 1.4G) was deleted from the worktree
afterward; the one crop that mattered is the committed fixture above.

**Status.** Fixed on this branch, not yet merged.

### I-38  An occluded target card cannot be selected, so the engine plays second-best   P1  input

**Evidence.** `run_live_20260921l.log`: hand "fielding_boost +1 | 8/0 | 6/0 | 9/0 | 6/0",
the 9 at slot 3 read its digit but its position was unmeasured; "slot 3's position is
unreadable, so whether it is already selected cannot be told — refusing rather than
pressing a TOGGLE blind" x3; the 8 was played.

**Root cause.** Not established beyond the Evidence above — the refusal is deliberate
(a TOGGLE is not pressed blind on an unpositioned target), but no frames yet show whether
a select would actually land there.

**Proposed fix.** (candidate, needs frames) Verify a select on an unpositioned target by
its disc becoming READABLE after the press (a lifted card rises above its occluder; the
inverse of I-21's inference).

**Status.** Open. Three genuine occlusion fixtures now exist, found by a Snoopy archive
search 2026-09-21 (`test_fixtures/hand_reads/i38_occluded_target_1.png`, `_2.png`,
`_3.jpg`; see `test_fixtures/hand_reads/README.md` for the read-off-each-frame detail).
The same search sampled 60 candidates flagged by a local pre-filter and had a VLM
(Snoopy, Qwen3-VL-8B) and a human eye each judge them: only 2 of 7 non-animation
candidates inspected by eye were genuine physical occlusion. **The other 5 were RAISED
(selected) cards whose disc was plainly visible on screen but still read `digit: None`**
-- not occlusion at all, but the brightened-disc-defeats-`DARK_THRESHOLDS` gap CLAUDE.md
section 10.23 already names. That is a distinct defect in the disc reader itself and is
a candidate for its own issue rather than more of I-38's occlusion scope.

### I-39  The play-refusal exclusion is keyed on the exact hand and over-persists   P2  loop

**Evidence.** Same run: after the 8 was played and a new card dealt into slot 1,
"hand_index [3] refused 3x running on this hand — excluded" fired again and the 6 was
played over the 9.

**Root cause established.** `orchestrator.play_excluded_slots` keyed exclusion SOLELY on
`_discard_hand_identity` (the hand's (kind, power, secondary, type) value tuple), with no
notion of WHY a slot was refused. Slot 3's exclusion happened to survive the next poll
not because anything about slot 3 was re-checked, but because I-27's own merge rule says
a slot missing from both sides (slot 1, dropped to UNKNOWN mid-deal) is not a
disagreement — so the hand identity never registered as "changed" at all, and slot 3
stayed excluded by accident. Had a DIFFERENT, readable slot genuinely changed instead
(a real redeal), the identity check would have cleared slot 3's exclusion too, even
though slot 3's own position was still unreadable — the same bug in the other direction.

**Fix (orchestrator.py).** `_PLAY_STALL` gained a `"reasons"` dict, one of
`PLAY_REFUSAL_UNREADABLE` / `PLAY_REFUSAL_TRANSIENT` per excluded hand_index, set at the
one call site in `play_one_turn` via `_slot_position_readable(state_json.get("hand"),
player_idx)` — the same "position is unreadable" question
`input_controller._select_verified` already asks before pressing a TOGGLE blind (I-38).
`play_excluded_slots` now: on a genuine hand-identity change, drops only the TRANSIENT
exclusions (unchanged pre-I-39 behaviour) and keeps the UNREADABLE ones; and on EVERY
call, independent of identity change, re-checks each UNREADABLE exclusion against
`_slot_position_readable` on the CURRENT hand and un-excludes it the instant it reads.
`exclude_play_slot(idx, reason=PLAY_REFUSAL_TRANSIENT)` defaults to the old behaviour so
every pre-I-39 caller is unaffected. `note_slot_dealt` and `reset_stall_counters` also
forget the reason when they forget everything else about a slot.

**Verify.** `tests/minigame/test_refusal_exclusion_by_reason.py`: (a) an UNREADABLE
exclusion survives a genuine redeal elsewhere in the hand while the slot itself stays
unreadable; (b) it clears the instant that slot reads again, with NO identity change at
all (the one thing the old, identity-only code could never do); (c) a TRANSIENT exclusion
keeps the exact pre-I-39 behaviour (survives an unchanged hand, clears on a genuine
redeal); (d) fewer than PLAY_STALL_MAX refusals never excludes; (e)
`exclude_play_slot`'s default reason; (5) end to end through the real `play_one_turn`,
reproducing the live shape at three turns (excluded, still-excluded-next-poll, then
re-offered once readable); (6) the TRANSIENT mirror of (5), which exercises the real call
site's OWN reason inference rather than a reason the test computed itself. Three mutants,
each caught by a different assertion: reverting `play_excluded_slots` to the pre-I-39,
identity-only body fails (a)/(b)/(5-turn-3); hard-coding every reason to TRANSIENT at the
call site fails (5, the "excluded as unreadable" log line and turn 3); hard-coding every
reason to UNREADABLE fails (6, which is the one test that would not otherwise catch it).
Restored byte-for-byte (sha256) after each mutant. Siblings re-run green:
`test_refused_play_falls_back.py`, `test_stall_identity_survives_flicker.py`,
`test_stall_state_forgets_dealt_slot.py`, `test_lifted_discard_row_rescued.py`,
`test_run_debit_and_scoring.py`, `test_no_shadowed_module_defs.py`,
`test_no_undefined_names.py`. `test_stall_counters_reset_with_hand_memory.py` updated for
the new `"reasons": {}` key in `_PLAY_STALL`'s exact-dict-equality check.

**Skeptic review (CONFIRMED WITH NOTES, agent_progress/issues/I-39-skeptic/progress.md):
one defect found and fixed before merge.** The readability un-exclude path
(`play_excluded_slots`, the "reads again" loop) did NOT reset `_PLAY_STALL["n"]` --
`n` is a SINGLE SHARED counter for whatever the decision currently offers, and
`exclude_play_slot`'s own docstring promises "whatever is played next its own fresh
PLAY_STALL_MAX budget", a promise the identity-change branch and `exclude_play_slot`
itself both keep but this second way an exclusion clears did not. Reproduced: exclude
slot A (unreadable); refuse slot B twice on the same hand (n=2, A still excluded); A
becomes readable and is re-offered; ONE further refusal on A read n=3 and re-excluded
it after a single fresh refusal, not PLAY_STALL_MAX (3).

**Fix.** Reset the SHARED counter (`_PLAY_STALL["n"] = 0`) whenever the readability
path un-excludes at least one slot — not a per-slot counter. Only one target is ever
"current" (the decision recomputes its single best pick every poll), and every other
reset in this module already treats `n` as belonging to that one pick, not to a
specific hand_index; a per-slot counter would be more precise but is a second
bookkeeping structure for a shape this file already declined to build once
(`note_slot_dealt`'s own comment: clearing both breakers' counts on every spend "is
the smaller diff... forgiving a count early is the safe direction this file already
uses elsewhere"). Same tolerance applies here — if a different slot was mid-streak
when the un-exclude fires, its count is forgiven one cycle early in the rare case the
decision keeps offering it anyway; never the direction that excludes something short
of its own fresh PLAY_STALL_MAX.

**Verify (added).** `test_refusal_exclusion_by_reason.py` scenario (f) reproduces the
skeptic's exact sequence (slot A excluded unreadable; two refusals on slot B; A reads
again and is re-offered; one refusal on A must not re-exclude it; three must). Mutant:
drop the `_PLAY_STALL["n"] = 0` reset — caught (n reads 2 instead of 0 immediately
after un-exclusion, then 3 and 4 on what should be a fresh 1-refusal and 2-refusal
count). Restored byte-for-byte (sha256:
9f2d8d1c1b816608dd01ea5aba3e4eaf796d6cf0d0897627240777efccadc349) after the mutant.
All 7 named sibling tests re-run green at that same sha.

**Open note from the skeptic, not itself a defect.** The reason inference
(`play_one_turn`, `_slot_position_readable(state_json.get("hand"), player_idx)`) is
computed against the hand read taken at POLL START (`read_state_for_turn`), which is
captured BEFORE `select_and_play`'s own internal press/verify loop runs its fresh
`hand_cursor_look` reads (`input_controller.py` ~1244-1400). So the reason is an
indirect proxy from a slightly earlier snapshot, not the walker's own per-attempt
refusal cause. Directionally right — the two reads are seconds apart on an otherwise
unchanged hand, and slot readability is unlikely to flip in that window — but this is
a narrow gap the skeptic did not demonstrate misfiring live. Worth a live frame pair
if a future exclusion is ever classified wrong.

**Status.** merged bedd4ca; skeptic CONFIRMED WITH NOTES (counter reset on re-offer
added and pinned).

### I-40  A reload's local money read disagreed with the known wallet and was trusted   P1  money

**Evidence.** `overnight/run_live_20260921p.log:158-161` (main checkout): right after a Load
Last Save, which CLAUDE.md section 4 says restores the wallet to $246 every time (and cycles
1-3 that same run read 246), `pause_menu.read_money` answered **$286** ("[balance] read
LOCALLY from the pause menu: $286"). `run_cycles` trusted it as `max_spend`, played four
matches, and attempted a fifth with the game's real wallet at $46: "[verify] start_match:
FAILED after 5 attempts, state never left 'prompt'" / "Match never started — stopping". The
record was left at balance 36 with `match_in_progress` true — a phantom $50 debit (no
`save_progress` on that path), repaired by the next reset. Separately, at 10:50 the pause
book plainly showed **46** (`test_fixtures/pause_money_20260921.png`, copied from the main
checkout, never symlinked) and `read_money` returned **None** on it.

**Root cause, ESTABLISHED (`agent_progress/issues/I-40/progress.md`, step 1).** The $46
fixture is a DIFFERENT failure from the live $286 misread, not the same one reproduced:
`read_money` REFUSES on it (both OCR scales return the empty string at every PSM, both
the `tesserocr` and `pytesseract` backends agree — verified bypassing `ocr_glyphs`'s
handle cache entirely) rather than answering wrong. Diagnosed (not fixed): narrowing the
crop recovers "46", but a too-narrow crop starts reading the coin badge as a spurious
extra digit ("466") — the fixed-width `MONEY_BOX_FRAC`, calibrated for 3-4 digit
right-aligned numbers, leaves enough blank space beside a 2-digit value to defeat
tesseract's segmentation outright. No frame from the actual $286 misread exists anywhere
on disk, so that specific mechanism (a 246-to-286 read, not a refusal) could not be
reproduced or explained here — nothing had ever saved the frame a money read was made on.

**Fix, in two parts, NEITHER of which touches the reader:**

  1. `orchestrator.record_money_read_frame()` keeps the frame every local money read
     settles on (answer or refusal) at `diagnostics/money_reads/<epoch_ns>_<answer>.png`
     — copies `record_reveal_kind`'s shape exactly (never raises, skipped under
     `BASEBALL_TEST_RUN`, refuses past a 200-file cap rather than pruning). Called AFTER
     `MONEY_READ_TRIES`'s retry loop, with the loop's final answer — pinned below — so a
     retry that recovers a read does not file the frame under the earlier refusal.
  2. `run_cycles.RELOAD_WALLET = 246` (renamed from `RESET_BALANCE_FALLBACK`, same
     value): `_read_balance()` now treats a read that DISAGREES with the known reload
     constant, or that raised, identically — logs the disagreement loudly (names both
     numbers) and returns `RELOAD_WALLET`, never the raw reading. `_reset_progress()`'s
     `balance` — which is exactly what becomes `max_spend` — inherits this for free.

**Tests.** `tests/harness/test_reload_wallet_guard.py`, **21 checks** (re-counted from
`grep -c "^PASS"` on a clean run — the branch's original writeup said 18), all green.
Three mutants, all caught, files restored byte-for-byte (sha256-verified): the
disagreement branch, the frame keeper's test-flag guard, and — added on skeptic review —
moving the `record_money_read_frame` call to BEFORE the retry loop (case v: with the
keeper stubbed and `read_money` returning None then 246, the un-mutated code calls the
keeper once with 246; the mutant calls it once with None, and the check fails as
required). Six sibling tests (`test_budget_reserve_fits`, `test_run_debit_and_scoring`,
`test_stale_flag_never_presses_unpaid`, `test_no_shadowed_module_defs`,
`test_no_undefined_names`, `test_no_real_input_under_test_run`) plus
`test_pause_money_local`, `test_reveal_frame_kept` and `test_caches_not_written_in_tests`
all still exit 0.

**Residual, documented rather than fixed.** The guard closes the OVER-read cause only —
a read ABOVE the true $246 inflating `max_spend`. `run()`'s `max_spend` is a session
counter, set once at reset and never re-checked against a live wallet read again, and
the $50 debit is recorded in the progress file before `start_match` is confirmed to have
landed. So if the "$246 every reload" premise were ever violated in the LOW direction —
a genuine reload that left the wallet under $246 — this guard would force `max_spend` UP
to $246 and could reproduce a phantom debit of its own, the same shape as the bug it
fixes, just the other sign. Judged acceptable rather than also guarded: `reset_environment`
proves the reload happened (it reads the spawn bearing off the screen, CLAUDE.md section
8(d)), and the reload wallet has read exactly $246 on every reset measured for weeks —
so the LOW-direction premise violation this residual depends on has never once been
observed. Revisit if a reload is ever seen landing under $246.

**Status.** Merged `aedc9ba`; skeptic CONFIRMED WITH NOTES (keeper ordering now
pinned by a mutation-tested check; residual documented above; check count corrected to
21). The reader itself (`pause_menu.read_money`) is UNCHANGED.

### I-41  Four tools popped BASEBALL_TEST_RUN at import, silently disabling the offline input lockout   P1  rig

**Evidence.** `tools/crawl_sheet.py:15` (and `label_batch.py:23`, `play_match_verified.py:16`,
`turn_timer.py:21`) did `os.environ.pop("BASEBALL_TEST_RUN", None)` at import; the scanner only
matched assignments/setdefault.

**Proposed fix.** Merged `f7bd912808c3708b5e0d489d189a11164fb7dbaf` — refuse at the
press/grab behind `<NAME>_DRIVE_IN_TESTS`, scanner widened to `.pop`.

**Status.** Merged.

### I-42  `cursor_labels_from_lifts.py`'s labels were 28/81 wrong, from a cursor caught mid-travel   P2  evidence

**Evidence, from an independent census (`agent_progress/census/cursor_vlm/notes.md`,
main checkout, read-only, 2026-09-21).** 81 lift-derived labels from two real runs
(`screenshot_log/run_20260921_080311`, `run_20260921_075118`) were checked against
`local_hand.cursor_slot`'s own read: 53 agreed, 28 did not. Every one of the 28 has
the same signature (`scripts/investigate_mismatches.py`): the target slot's own glow
is under 5% in the labelled frame — nowhere near `CURSOR_GLOW_MIN` (10.0) or the
reader's documented true-cursor floor (20.7-36.1) — and the rise fires the very next
captured frame, ~100ms later. That is a cursor caught MID-TRAVEL between slots, not
one that was parked and then pressed select: the tool's core assumption ("the frame
before a rise is a frame whose cursor slot is known") is violated whenever the
pre-select cursor travel crosses the ~100ms gap between two captures. 9 of the 28 are
a second, separate artefact — one selection's rise flickering near
`SELECTED_MIN_RISE`, re-triggering "newly risen" several times for one event.

**Root cause.** `tools/cursor_labels_from_lifts.py`'s HOLD=3 persistence filter
catches a lift that never becomes a real selection; it has nothing to say about a
real selection reached by a cursor that was already moving, or about the same
selection's rise flickering across the detector's edge.

**Fix, two independent checks, neither consulting `cursor_slot` or `cursor_glow`**
(CLAUDE.md 10.22 — an independent label cannot mark its own homework; both are pure
geometry from `selected_cards`, same as the original signal):

  1. CAPTURE GAP: the frame immediately before the labelled frame must show the SAME
     selected-set as the labelled frame — evidence the fan was already quiet for
     >=2 frames before the rise, not mid a fast cursor jump.
  2. NO-FLICKER: the rising slot must not have been risen at all in the
     `FLICKER_WINDOW` (10) frames before the labelled frame — a re-rise right after a
     drop is the same selection flickering, not a new one.

`labels_for()` now returns `(kept, rejected)` with a reason per rejection
(`capture_gap`, `flicker`, or the original `transient`) instead of silently dropping
candidates, and `main()` prints both lists per run.

**Verify, re-run on the same two real corpora the census used** (frame paths matched
by basename against `agent_progress/census/cursor_vlm/joined.jsonl`'s 81 ground-truth
rows, main checkout, read-only):

    of 28 known-bad (A != C)    28 rejected (100%)    0 wrongly kept
    of 53 known-good (A == C)   44 correctly kept (83%)  9 wrongly rejected (17%)

Every one of the 28 bad labels is now caught — 16 by flicker alone, 11 by
capture_gap+flicker together, 1 by capture_gap alone. The cost is real and reported
rather than tuned away: 9 of 53 good labels (17%) are also rejected, all by the same
two checks, because a genuine parked-and-selected cursor can occasionally sit inside
a fan that had *other* recent activity or a near-window flicker on the same slot. No
threshold here was chosen to hit a number (CLAUDE.md 10.4) — `FLICKER_WINDOW=10` and
the 2-frame capture-gap requirement are the literal reading of the two checks' own
definitions, not a fit to this data.

**Tests.** `tests/harness/test_cursor_labels_capture_gap.py`, originally 4 synthetic
frame-sequence cases (8 checks): a clean selection (kept), a rise one frame after a
move (rejected, capture_gap), a flicker re-rise (rejected, flicker), and the original
HOLD filter still firing on its own (rejected, transient).

**Skeptic round 1: CONFIRMED WITH NOTES.** Independently re-derived the diff, the
verification table (exact match: 28/28 known-bad rejected, 44/53 known-good kept) and
the caller census (`labels_for` has exactly two callers, both already unpack the new
`(kept, rejected)` return). Ran its OWN four mutants against the original 4-case
suite and found two coverage gaps the fixer's two mutants (`gap_ok = True`,
`flickered = False`) never probed: a wrong-pair swap (`hist[-3] == hist[-2]` in place
of `hist[-2] == hist[-1]`) escaped by fixture coincidence (this test's case 2 happens
to have `hist[-3] != hist[-2]` exactly where `hist[-2] != hist[-1]`, so the mutant's
wrong condition gives the same answer as the right one on that one fixture), and a
flicker-window off-by-one (`hist[-(fw+1):-1]` shrunk to `hist[-fw:-1]`) escaped
structurally (case 3's flicker gap sits 4 frames inside a 10-frame window, far from
the boundary a one-frame shrink would clip). Both are coverage gaps in the TEST, not
correctness defects in the shipped code — confirmed by tracing the correct logic by
hand, independent of any test.

**Four cases added to close both gaps, none touching the shipped mechanism:**
case 5 (`hist[-3]==hist[-2]` while `hist[-2]!=hist[-1]`, so the correct pair
disagrees but the adjacent wrong pair agrees), case 6 (the analogous
`hist[-3]==hist[-1]` swap), case 7 (the rising slot last risen EXACTLY
`FLICKER_WINDOW` frames before the labelled frame — inside the window, REJECTED)
and case 8 (EXACTLY `FLICKER_WINDOW + 1` frames before — one frame outside, KEPT).
8 cases, 16 checks total, all green on unmodified code.

**All four of the skeptic's named mutants re-run, this time against the full
16-case suite, `__pycache__` deleted and sha256 verified identical
(`b727bb7ed7760555ec0204df2d9f821430ed19daa26d4ecf7e11a9c1f1fd7481`) before, between
and after every one:**

    force gap_ok = True                                  case 2, 5, 6 FAIL
    force flickered = False                              case 3, 7 FAIL
    hist[-2]==hist[-1] -> hist[-3]==hist[-2] (literal)    CRASHES (IndexError) at
                                                          case 2's own n=2 candidate,
                                                          before case 5 is even
                                                          reached -- the SAME literal
                                                          substitution the skeptic
                                                          used, unearthing that its
                                                          own len(hist)<2 guard is
                                                          now one index too short.
                                                          A crash is a harder failure
                                                          than a printed FAIL: no
                                                          "all green", nonzero exit.
    hist[-2]==hist[-1] -> hist[-3]==hist[-2] (guarded,
      len(hist)<3, so it cannot crash)                    case 5 FAILS, nothing else
    hist[-(fw+1):-1] -> hist[-fw:-1] (flicker off-by-one) case 7 FAILS, nothing else
    reasons discarded to None (unconditionally)           already caught by cases
                                                          2 and 3 (unchanged)

All four fail as required; the two that escaped before are now caught cleanly
(cases 5 and 7), and the wrong-pair mutant is caught in BOTH the literal form the
skeptic used (a crash) and a hypothetical better-guarded form (a clean FAIL),
so the guard isn't accidentally load-bearing for the catch.

**Status.** merged cf127a477a05c00ebbfc450207c360061e2a016c, skeptic CONFIRMED WITH
NOTES (two escaped mutants closed by 4 boundary cases). Re-verified post-merge on
main: `tests/harness/test_cursor_labels_capture_gap.py` prints 16/16 checks, and
`tools/cursor_labels_from_lifts.py screenshot_log/run_20260921_080311` reproduces
173 raw candidates -> 41 kept, `cursor_slot` scoring 41/41 correct (0 blind, 0
wrong) against the survivors. Both real runs re-scanned end to end offline, no
console, no live change.

### I-43  A stray left lifted by a refused attempt survives into the NEXT operation's baseline-blind exemption   P0  guard

**Evidence.** QA6 finder, read-only, main checkout HEAD a277f46
(`agent_progress/qa6/interactions/progress.md`, Q4), reproduced against the real
`input_controller._clear_strays` (the finder's own repro script did not survive
on disk; reconstructed from its precise write-up in
`tests/minigame/test_commit_refuses_unseen_strays.py` case (A)).

**Root cause.** `_verified_select_and_play_inner`/`select_and_discard` capture
`blind_before` from ONE `_look_settled` at the very top of the call, before any
press. When an EARLIER, unrelated attempt's `_unwind_selection` could not even
read the fan ("cannot read the fan to unwind — leaving the board as is") its
target may still be genuinely lifted. That slot then reads unreadable at the
NEXT operation's own baseline too — indistinguishable, from `blind_before`
alone, from a card that has been chronically occluded the whole hand and was
never touched by anyone. I-26/I-28's own accepted exemption ("slot(s) [..] were
ALREADY unreadable before this operation began — proceeding") then waves it
through: `selected_cards()` also skips a None-y row, so the stray is invisible
to `lifted = set(sel) | _want_inferred` too, and `_clear_strays` returns `True`
believing the board is clean when a card the engine never chose is still up.

**Fix.** A process-local `_MAYBE_LIFTED` set in `input_controller.py`, reset by
`orchestrator.reset_hand_memory()` (every match/half boundary — a stray cannot
survive a hand that no longer exists on screen). Every return-False site across
`_unwind_selection` and `_clear_strays` that leaves the board's clean state
UNPROVEN now records the implicated slot(s) via `_mark_maybe_lifted`, listed
here (the trace the fix is built from):

    _unwind_selection   fan unreadable at all            marks `ours`
                        a slot in `extra` could not be
                          walked-to/deselected            marks that slot and
                                                          every slot after it
                                                          in that loop (unproven)
                        any exception mid-unwind          marks `ours`
    _clear_strays       top: fan unreadable before
                          committing                      marks `want`
                        re-look: fan unreadable            marks `_new_blind`
                        still blind after the one
                          allowed re-look                  marks `_new_blind`
                        a stray in `extra` could not be
                          cleared                          marks that slot and
                                                          every slot after it
                                                          in the clearing loop
                        still bad after clearing           marks the implicated
                                                          blind/lifted slots
    select_and_discard   the pre-select walk/select fail
                          (no _unwind_selection safety
                          net on this path)                marks `card_index`
                        the post-clear walk-back fails     marks `card_index`
                        confirm_discard pressed but its
                          result is unverified (four
                          distinct branches)                marks `card_index`

`_clear_strays`'s baseline-blind exemption (`_untouched_blind`) now refuses,
naming the slot(s), whenever it intersects `_MAYBE_LIFTED` — a tracked slot
must be SEEN DOWN (a real y, not risen) before it can be waved through as a
chronic occlusion. `_reconcile_maybe_lifted(ys, sel)` clears a tracked slot the
moment a fresh read proves exactly that, at every `_look_settled` inside
`_clear_strays`. A genuinely chronic occlusion nobody ever failed to clear is
never in `_MAYBE_LIFTED` and is unaffected (control-a).

**Verify.** `tests/minigame/test_commit_refuses_unseen_strays.py`: case (A) is
the reconstructed QA6 Q4 repro (refuses, was `True` pre-fix); control (a) shows
a genuine chronic occlusion (I-28's own live case) is still exempted, never
walked to or deselected, never marked; control (d) is the full lifecycle —
attempt 1 refuses while the stray is still up, attempt 2 commits once a later
read proves it down, and `_MAYBE_LIFTED` is cleared for it. Mutant (i), drop the
`_MAYBE_LIFTED` intersection check, caught by case (A) and control-d's attempt
1. sha256-verified restored byte for byte.

**ROUND 1 REFUTED by an independent Opus skeptic**
(`agent_progress/issues/I-43-44/skeptic.md`, S-2, S-3). The fix as shipped
missed its own PRIMARY path and had a second silent-unmarking hole:

- **S-2.** `_unwind_selection`'s `extra` is computed from `sel` (risen rows
  only, via `selected_cards()`), so a slot that is BOTH lifted AND blind
  (I-21's own mechanism) can never appear in it. The function's SUCCESS path
  (`if not extra: return True`) then returned `True` having put nothing down
  and — because every marking site round 1 added was on a FAILURE exit — proved
  nothing and recorded nothing. The I-43 bug survived the I-43 fix.
  Reproduced by the skeptic against the real `_select_verified` ->
  `_unwind_selection` -> `_clear_strays` chain (an odd `SELECT_ATTEMPTS`=5
  leaves the card physically up when the I-36-skeptic tactics gate declines
  the inference and the retries run out).
- **S-3.** `_reconcile_maybe_lifted` at one of its three call sites ran on
  `_look_settled`'s FAILURE return (`(glow, ys, 0, [])`) — the LAST bad frame's
  `ys` (real-looking numbers) with `sel` deliberately EMPTIED. Both of the
  reconcile conditions (`ys[slot] is not None`, `slot not in sel`) are then
  satisfied by construction, so a read that saw NOTHING silently "proved" a
  tracked slot down.

**Fix v2 (this worktree).** `_unwind_selection` now takes an optional `ys0`
(both production callers already have it) and, before EITHER return path,
marks `{s for s in ours if _ys[s] is None and (readable at ys0 or ys0
unavailable)}` — the `ys0` gate is deliberately NARROWER than the skeptic's own
one-line suggestion ("mark every blind `ours` slot, unconditionally"): marking
a slot that was ALREADY blind at this operation's own start (never pressed,
e.g. a genuine chronic occlusion the engine merely chose) would reintroduce
the exact I-26/I-28 deadlock the exemption exists to prevent, because such a
slot's `ys` can never later read non-None and `_reconcile_maybe_lifted` could
then never clear it. `_reconcile_maybe_lifted`'s unguarded call site was moved
below its own `n != MAX_HAND_SIZE` guard, matching the other two.

**Verify (round 2).** New cases in the same test file: (S-2) drives the real
`_unwind_selection` with a lifted-and-blind `ours` slot, confirms it still
reports success AND now marks the slot, and chains into a following
`_clear_strays` call that correctly refuses; (S-2 control) the SAME slot blind
at `ys0` too (never touched) is NOT marked, proving the deadlock is avoided;
(S-3) forces the post-clear look to fail and confirms a pre-existing mark
SURVIVES rather than being wrongly cleared. Two new mutants (M1, M2, from the
skeptic's own round): M1 makes `_reconcile_maybe_lifted` UNCONDITIONALLY clear
everything (the opposite failure direction from mutant iii, which made it a
no-op) — caught by (S-2)/(d); M2 drops the new mark on `_unwind_selection`'s
fan-unreadable exit — caught by case (A)/(d). A third (M3, the skeptic's own):
drop the mark on `select_and_discard`'s "the counter never answered ...
UNVERIFIED" exit — SURVIVED round 1's suite (the fix was present, nothing
exercised that specific branch); caught now by a dedicated case driving
`select_and_discard` through it directly. All sha256-verified restored,
`__pycache__` cleared between mutants.

**The one exit the skeptic flagged as still unmarked** (`_clear_strays`'s
final `if not want <= lifted:`, reachable with a `want` slot genuinely lifted
whenever `_select_verified` proved it selected against ITS OWN, later
baseline look while this operation's earlier `ys0` read the same slot as
already blind — the two windows can disagree) is now marked too:
`_mark_maybe_lifted(set(want) - lifted)` at that exit, rather than argued
unreachable, since the argument for unreachability does not hold in that one
narrow window.

**Status.** merged 2f18a734dbd43828f4f6fbbafb8a20a947456e0e; skeptic round 1 REFUTED (29% healthy-turn refusals), round 2 CONFIRMED WITH NOTES, 7/7 mutants.

### I-44  `_clear_strays`'s commit-time inference asks for no real corroboration   P0  guard

**Evidence.** QA6 finder (`agent_progress/qa6/interactions/progress.md`, Q2),
reproduced against the real `_clear_strays` (script not on disk; reconstructed
in `tests/minigame/test_commit_refuses_unseen_strays.py` case (B)): `want={3}`,
baseline readable, a look() where the card never lifts, ever (`sel` permanently
empty, the slot's own y permanently `None`) — `_clear_strays` still returned
`True` and `confirm_play` would fire.

**Root cause.** `_want_inferred`'s commit-time re-application of I-21's
inference asks only three facts, all derivable from the CALLER's own
`ys0`/`kinds0`/`blind_before` book-keeping with no reference to a real,
geometric read: readable at baseline, blind now, not tactics-typed. Nothing
requires that `sel` (the fresh look `_clear_strays` itself just took) or
`_select_verified`'s own retry loop EVER actually saw the target selected. A
dropped press plus a transient disc misread produce the identical three facts
a genuine lift does, and I-36's own write-up already named this as an accepted,
unmeasured gap for a player-baseline target.

**Fix.** `_select_verified`'s existing inference branch (I-21) now reports
WHICH slot it inferred, via a new `_InferredSel(list)` subclass carrying
`.inferred` (behaves as a plain list to every existing consumer — `in`,
`sorted()`, `set()`, `==` all defer to `list`, the same trick `orchestrator.
_CursorSel.kinds` already uses for `kinds0`, chosen specifically so the
existing 2-tuple `ok, sel = _select_verified(...)` unpacking at both call
sites, and in every sibling test, needs no changes). Both callers
(`_verified_select_and_play_inner`, `select_and_discard`) accumulate
`getattr(sel, "inferred", frozenset())` across their select step(s) into an
`inferred_targets` set and thread it into `_clear_strays` the same way
`ys0`/`kinds0` already are. `_want_inferred`'s gate gains a fourth condition:
`inferred_targets is None or k in inferred_targets` — `None` (no caller
support) is PERMISSIVE, the unchanged pre-I-44 behaviour, matching the exact
convention `kinds0` already established for the identical reason (every test
and caller written before this needs no changes); a caller that supplies a
real set (even empty, meaning "the select step ran and reported nothing")
requires the SAME slot to have been actually inferred by `_select_verified` on
THIS operation. A target that ends up neither in `sel` nor in `inferred_targets`
is refused with a line naming it ("target not seen selected — refusing to
commit"), falling through to the existing "not all lifted" refusal. I-36's own
baseline-kind gate (`kinds0`) is untouched and still applies independently.

**Verify.** `tests/minigame/test_commit_refuses_unseen_strays.py`: case (B)
shows `inferred_targets=None` still commits (unchanged) while
`inferred_targets=set()` (empty, real) now refuses the identical never-lifts
scenario; control (b) a genuine geometric selection commits regardless;
control (c) drives `_select_verified` for real against a `LiftScreen` harness,
takes its actual `.inferred` report, threads it into `_clear_strays`, and
confirms the commit — proving the plumbing end to end, not just the gate in
isolation. Mutant (ii), `_corroborated` always returns `True`, caught by case
(B)'s fix check. sha256-verified restored byte for byte. Sibling
`test_lifted_discard_row_rescued.py` case (5) (I-36's own kinds0-threading
test, a tactics-baseline target whose commit-time look glitches) passes
unmodified and is now ALSO caught by this gate independently of I-36's own —
both must agree the target was never seen selected.

**ROUND 1 REFUTED by an independent Opus skeptic**
(`agent_progress/issues/I-43-44/skeptic.md`, S-1 — BLOCKING). `_InferredSel.
inferred` was set on EXACTLY ONE of `_select_verified`'s four success paths:
the I-21 inference branch. The other three — `target in before` ("already
selected", no press at all) and `target in sel` (the three real, geometric
"it landed" checks, including the COMMONEST case, an immediate attempt-1
landing that `_select_verified` prints nothing for) — are STRONGER evidence
than the inference, not weaker, yet reported no corroboration at all. So a
target verified by a real read and then gone blind by commit time — I-21's own
stated premise, "selecting a card is what blinds its own disc" — fell out of
`_want_inferred` and refused, and the retry re-refused on `_select_verified`'s
own "position is unreadable... refusing rather than pressing a TOGGLE blind"
guard: a HARD STALL, not one lost turn.

**Measured against the archived logs** (main checkout, `overnight/run_live_
*.log`, gitignored and absent from this worktree by design — read there,
per-operation pairing on `_clear_strays`'s own `_want_blind` print matched
against `_select_verified`'s own inference print in the same "Decision:"
block): of **34** want-blind commit events, only **24** carried an inference
print; the other **10 (29%)** would have refused under round 1's fix, every
one inspected and legitimate (5 of the 10 in one run,
`run_live_20260921n.log`; the model excerpt is `run_live_20260921q.log:
326-330`, which reads "verified on 3 after 1 press(es)" — a real, silent
read — then "WIN #62 logged"). **This reconstruction reproduces the
skeptic's own reported numbers (34/24/10, 5-in-one-run) exactly.**

**Fix v2 (this worktree).** ALL FOUR of `_select_verified`'s success returns
now carry `_InferredSel.inferred = frozenset({target})` — the class's own
semantics widened from "selected by I-21's inference specifically" to
"confirmed selected on THIS operation, by a real read OR by inference"
(`_clear_strays`'s gate and both callers' plumbing are unchanged; only what
`_select_verified` reports is wider). No new hole: `_clear_strays` only ever
runs `_want_inferred`'s check on a `want` slot AFTER `_select_verified`
returned `True` for it THIS operation, so every want-blind slot is now
corroborated by construction — `would_now_REFUSE` is **0 of 34** by this
structural argument, not merely by re-running the same 34 events (the
archived logs cannot be replayed byte-for-byte offline; the argument is
verified directly instead, below).

**Verify (round 2).** New cases (S-1a, S-1b) drive the REAL `_select_verified`
through the "already selected" and "immediate real-read landing" paths (the
two the skeptic named), confirm each returns an `_InferredSel` carrying the
target, then thread that into a `_clear_strays` call where the target is blind
at commit — both must and do COMMIT, reproducing the exact archived shape.
Mutant (S-1 bonus): drop the `.inferred` marking from JUST the `target in
before` path — caught by (S-1a). A new mutant M4 (the skeptic's own): drop
`_corroborated(k)` from the POST-CLEAR `_want_inferred` computation only (the
second occurrence, reached whenever a real stray also needs clearing) —
survived round 1's suite entirely; caught now by a dedicated case that forces
the post-clear branch to run with an uncorroborated want-blind target present.
All sha256-verified restored, `__pycache__` cleared between mutants.

**Status.** PARTIAL, merged 2f18a734dbd43828f4f6fbbafb8a20a947456e0e: the corroboration gate is inert in production (every success path marks, so inferred_targets == want always; N-1); the original QA6 Q2 hole (a dropped press + false inference supplies its own corroboration) is STILL OPEN and needs corroboration the inference cannot manufacture (selection-lift geometry or a post-commit read). Live watch: count 'may still be physically lifted' lines on the next matches; the archive bounds it at 14 exemption events vs 51 refusals.

**N-2 closed on branch e55a02e by (2), NARROWLY — read before building anything on
this entry.** Traced first, against the real, unmodified code, before writing anything
(CLAUDE.md 10.32): candidate 1 (selection-lift geometry, `local_hand.selected_
cards`) is UNAVAILABLE for validating this specific inference by construction —
`selected_cards` requires `y is not None` and, for a non-tactics row, `y_from !=
"fallback"` (a DISC-derived y), which is exactly what a target has already lost
the moment its disc goes blind. Candidate 2 (baseline comparison) turned out to
already be SHIPPED: `_want_inferred`'s `ys0[k] is not None` check (now extracted
and named `_baseline_readable`, mirroring `_baseline_not_tactics`) already
requires a `want` slot to have been readable at THIS OPERATION's true start
before an inference is trusted at all, independent of whatever `_select_verified`'s
own LATER look (taken after a walk, possibly after a sibling target's own
selection) believed. Reversing QA6 Q2's own repro at the one axis it never
tested — baseline UNREADABLE rather than baseline readable — reproduces a REFUSAL,
not a commit, on the CURRENT code, with no change needed to close it. It was simply
untested and therefore mutant-free.

**What this DOES close.** A target that starts an operation already blind
(chronically occluded, or one `_select_verified`'s own look disagreed with) can
never self-corroborate via inference; it either shows up in `sel` on its own (a
real, disc-readable rise — candidate 1 IS available for THIS sub-case, and
already commits via direct `sel` membership, no new code) or the commit refuses.
Cost, measured against the archived logs (`overnight/*.log` in the main
checkout, per-operation, grepping every "selected by inference (disc unreadable
after lift)" line and every "was never selected by inference on this operation"
refusal line): 28 inference events across 11 files, **0** would-be refusals from
`_baseline_readable` specifically (the refusal line itself never fires anywhere
in the archive) — this fix is free in the historical record, because `_select_
verified` structurally never presses against a target its OWN pre-press look
already shows blind, so the operation-level `ys0` and `_select_verified`'s local
check almost always agree; the one window where they can disagree (a sibling
target's own selection transiently occludes this one) is exactly what
`_baseline_readable` protects, and it has never fired historically either way.

**What this does NOT close, and the skeptic's own N-2 repro is the harder case
than the ticket's own hole description.** A target genuinely readable at `ys0`,
genuinely pressed, and then MISREAD as blind by the same circle-fit noise I-21
exists to tolerate (CLAUDE.md 10.26 — "the fitted circle alternated between
r=19 and r=20") is READ-IDENTICAL to a real lift that blinds its own disc
(I-21's own stated mechanism) — and `test_commit_refuses_unseen_strays.py`'s
own (control-c) pins the LATTER as a MUST-COMMIT, driven for real through the
same `_select_verified`. Nothing in `_clear_strays` — not `ys0`, not `kinds0`,
not `inferred_targets` — can tell these two apart, because they are the SAME
observation. Closing it needs either a post-commit read (candidate 3 — too
late to prevent a wrong card, a detector not a fix) or per-row DIGIT
corroboration threaded from `orchestrator.hand_cursor_look` (a `.digits`
attribute alongside `_CursorSel.kinds`), which is out of this fix's scope
(input_controller.py only) and is the next real lever if this is worth more
than a detector.

**Verify.** `tests/minigame/test_inference_needs_baseline_read.py`: (A) baseline
readable, driven for real through `_select_verified` (LiftScreen), commits —
CONTROL, unchanged. (B1) baseline blind, driven for real: `_select_verified`
refuses BEFORE pressing, 0 presses sent. (B2) `_clear_strays` directly, with a
(hypothetically wrong) `inferred_targets` naming the slot anyway: still
refuses — `_baseline_readable` is the actual backstop, not `inferred_targets`
alone. (C) `ys0` blind at operation start but the target's OWN later look is
readable, driven for real through a screen whose disc stays legible through
the rise (the common case, not I-21's blinding one): commits via direct `sel`
membership, bypassing the inference path entirely. (D) I-26/I-28 regression:
an untouched, chronically-occluded NON-want slot is still exempted, never
walked to, never marked — `_baseline_readable` only touches `_want_inferred`,
which the chronic-occlusion exemption never reads. Mutants (3, APFS-clone
scratch copy per CLAUDE.md 10.16a, sha256-verified restored,
`__pycache__/input_controller*` cleared between mutants): M1 `_baseline_
readable` → unconditional `True` (accept the inference on a blind baseline) —
CAUGHT, case (B2) fails, and `test_stray_guard_exempts_target.py` also breaks.
M2 drop `set(sel)` from `lifted = set(sel) | _want_inferred` (candidate 1's own
mechanism — existing code, not new; included because case C leans on it) —
CAUGHT, case (C) fails, and four siblings break with it (`test_commit_refuses_
unseen_strays.py`, `test_verified_selection.py`, both stray-guard tests). M3
mark every untouched-blind slot unconditionally (drop the `& _MAYBE_LIFTED`
narrowing) — CAUGHT, case (D) fails, and `test_commit_refuses_unseen_strays.py`
plus both stray-guard tests break with it. `test_no_undefined_names.py` and
`test_no_shadowed_module_defs.py` are unaffected by all three, confirming
nothing structural broke. Full suite run (worktree, `BASEBALL_TEST_RUN=1`,
`nice -n 10`): `test_verified_selection.py`, this file, `test_tactics_select_
fallback.py`, `test_i22_pitch_boost_slot3.py`, both harness tests and
`tests/rig/test_no_real_input_under_test_run.py` all EXIT 0.
`test_refusal_unwinds.py` EXITS 1 with 4 failures — reproduced identically
against `git show HEAD:input_controller.py` in an untouched scratch copy, so
this is PRE-EXISTING and unrelated to this diff; not investigated further here
(out of scope: it is not on this diff's file, and CLAUDE.md 10.9 says a
failing check gets the same suspicion as a passing one, not a free pass to fix
opportunistically on someone else's ticket).

**Status.** N-2 merged 69e77a4, skeptic CONFIRMED (narrow: the baseline gate
was already present, now named and tested; the hard case -- baseline-readable
target, dropped press, coincidentally blind post-press read -- still commits
and is OPEN: needs per-row digit corroboration from orchestrator or a
post-commit detector; 0/28 archived inference events affected).

## C. Costs wins

All four C items are simulator A/Bs first. Harness: `simulate.py` (`sweep`,
`run_tournament`, `blend_team`), 20,000 halves x 3 seeds an arm, and a control arm that
must reproduce the shipped number exactly before any other arm is read (CLAUDE.md §4's
`tie_w` sweep is the template; its first version was wrong and the control caught it).
Ship only on a significant win; the score-risk experiment shows how a plausible idea
measures zero.

### I-13  The ban choice has never been A/B'd                                       P2  engine

**Evidence.** User, 2026-09-20: a ban removes cards from OUR OWN draw pool.
`decision_engine.py:370-388 choose_bans` bans the weakest 3 by `(power, secondary)`.
`simulate.py` threads `player_pool` through `draw_hand`, `refill_hand`, `replace_weakest`
(:138-244) but no sweep compares ban rules; the redraw threshold was swept over 4,000
matches (`decision_engine.py:220-227`), the ban rule never.

**Proposed fix.** Arms: no bans (control), weakest-3 (shipped), weakest by ROLE (the
pitching half and batting half draw different pools, so a weak pitcher costs nothing in
the batting half), and "ban the three cards most often played when losing" from the log.

**Verify.** The no-ban arm reproduces the shipped baseline run/half; report each arm
with sigma. **Agent brief.** Opus (strategy). May touch `simulate.py` and add a test that
pins the winner.

**RESULT 2026-09-20 (agent_progress/issues/I-13/, 20,000 matches x 3 seeds an arm; the
no-ban control reproduces the shipped baseline match for match).** Win rate: no bans
39.56%, weakest-3 (shipped) 45.27% (+5.7 points, 20 sigma), weakest-3 batters 45.95%,
role split 45.36%. Against shipped, the batters arm is +2.35 sigma pooled and REVERSES in
one seed (-0.36); nothing clears 3 sigma. **CLOSED: the shipped rule stands.** Two facts
worth keeping: banning at all is worth +5.7 points and had never been measured; and the
three weakest cards of this 33-card collection are all pitchers, so the shipped rule is a
pitching-only rule by accident (bit-identical to "weakest-3 pitchers"). Banning batters
instead buys offence (1.79 -> 2.07 runs/match) at the same win rate. **Status.** Closed.

**2026-09-21 update.** The roster's last two untyped cards, Brian Coker (8/1) and Zachary
Lee (6/2), are now typed BATTER (user-confirmed from ban-grid frames, Snoopy job 2;
`simulate.UNTYPED` is empty). Both were already excluded from "the three weakest cards
are all pitchers" above, so this result is unaffected; recorded here because it is the
nearest roster-composition entry.

### I-14  Tactics timing is "always attach", measured only against "never attach"    P2  engine

**Evidence.** `decision_engine.py:120-201, 230-318`: the boost attaches to whichever card
is chosen, every turn. The 79% that justifies it compared always-attach against
never-attach in a model where speed did nothing (its own docstring says so). RULES.md §3:
max batter power is 11; a pitcher playing 9 cannot concede a home run, 8 can. So a pitch
boost on a 9 changes no outcome (10 loses to 11 exactly as 9 does) while on a 7 it flips
outs against 7s and 8s (opp batter powers in the log: 4 x56, 5 x41, 6 x27, 7 x13, 8 x24,
9 x24, n=185).

**Proposed fix.** Arm: attach only when the boost changes an outcome against the
modelled opponent distribution, else hold it for the next card. Control: weight 0
reproduces shipped.

**RESULT 2026-09-20 (agent_progress/issues/I-14/, 20,000 halves x 3 seeds an arm; w=0
reproduces the shipped per-half scores element-wise).** Every w from 0 to 0.20 changes
zero decisions; the first w that changes one (0.30) is worse in BOTH halves (batting
-0.019 runs/half, pitching +0.123 conceded, 16 sigma) and it only gets worse from there.
**CLOSED: always-attach stands**, the tie_w shape exactly. **AND THE PREMISE ABOVE WAS
WRONG:** a pitch boost on a 9 is NOT outcome-free. `simulate.resolve`: batter 9 vs
pitcher 9 is a TIE (a 50% hit) but vs 10 is an OUT; batter 10 vs 9 is a hit but vs 10 a
tie. P(change) for a 9 is 0.22, the lowest cell, not zero. The claim holds only against a
batter at 11. **Status.** Closed.

### I-15  Card sequencing is greedy; the round number is plumbed and never read       P2  engine

**Evidence.** `GameState.batters_used` (`decision_engine.py:60`) is set every turn and
read by no decision function (decision_engine.py read in full). The engine plays its best
batter first; a home run with the bases empty scores 1, with two on it scores 3.

**Proposed fix.** Arm: hold the best batter until a runner is on or round >= 4. Likely
small (INFLIGHT.md's runner-aware batting measured +0.015, 1.5 sigma); measure, do not
ship on plausibility (§10.2).

**Verify / brief / status.** As for I-13. Open.

**RESULT 2026-09-21 (agent_progress/issues/I-15-16-17/, 12,000 halves x 3 seeds an arm
vs `ALWAYS_BOOST`; the hold=False control reproduces the shipped baseline's per-match
score array exactly).** Baseline (`CURRENT` vs `ALWAYS_BOOST`): **1.9879 runs/half,
48.34% win, n=36,000.** Arm (hold the best batter back unless a runner is on or
`batters_used >= 4`): **1.7438 runs/half, 42.96% win — delta -0.2441, 24.85 sigma**, and
it changed the played card on 37.5% of 4,000 sampled (hand, state) pairs, so this is not
a vacuous knob. **Decisively worse, not a wash — CLOSED: do not ship.** INFLIGHT.md's
+0.015/1.5-sigma figure does not reproduce at this n; the sign is the opposite. Mechanism:
holding a card is not banking it — it sits out a round it could have hit, and 5 rounds per
half (RULES.md §1) means "runners on or round>=4" often never arrives while the bases stay
empty, so the policy trades a certain at-bat for a maybe-better one that frequently never
comes. See GRAVEYARD.md's Engine table. **Status.** closed (measured 2026-09-21,
merged 7d9d198).

### I-16  The discard threshold is a fixed 6 and deck-blind                          P2  engine

**Evidence.** `decision_engine.py:227 REDRAW_POWER_THRESHOLD = 6`, swept once. The roster
is 33 known cards (`KNOWN_BAN_ROSTER`), 30 after bans, and the cards seen this half are
known, so P(draw > current max) is computable per turn.

**Proposed fix.** Arm: redraw when P(improve) x (expected gain) beats the cost of the
discard, from the live deck composition. Control: the fixed 6.

**Verify / brief / status.** As for I-13. Open.

**RESULT 2026-09-21 (agent_progress/issues/I-15-16-17/, 12,000 halves x 3 seeds an arm
vs `ALWAYS_BOOST`; the fixed-6 control reproduces the shipped baseline exactly).** Swept
P(a fresh draw beats the current hand's max power), computed from the role-filtered
33-card pool minus the cards currently visible in hand (no bans modelled; I-13's own
arms are closed), over {0.3, 0.4, 0.5, 0.6}:

    threshold   runs/half   delta      sigma    decisions changed
    control(6)     1.9879       --        --     --
    0.3             1.9840   -0.0038    -0.39    98/2662
    0.4             1.9838   -0.0041    -0.41    91/2662
    0.5             1.9298   -0.0581    -5.92    470/2662
    0.6             1.8269   -0.1609   -16.53    605/2662

0.3/0.4 are statistically flat (<1 sigma, the tie_w "changes no decision" shape at the
low end); 0.5/0.6 are significantly WORSE. No swept threshold beats the fixed 6. **CLOSED:
do not ship any of the four.** Scope note: this arm conditions only on the currently
VISIBLE hand, not on every card seen earlier in the half (a fuller tracker would need a
mutable per-half accumulator threaded through `simulate_batting_half`), so it bounds a
weaker version of the proposed policy from above — re-open with that fuller tracker if
this is ever revisited. **Status.** closed (measured 2026-09-21, merged 7d9d198).

### I-17  The opponent model is our card pool, not the log                            P2  engine

**Evidence.** `simulate.py:634 _pitcher_power_distribution` is built from `CARD_POOL`.
RULES.md §2: the two players hold separate decks. `match_log.jsonl` carries their powers
by phase (when we bat, their pitcher: 4 x42, 5 x35, 6 x31, 7 x23, 8 x10, 9 x21, n=162);
powers were read by the same reader in every era, so they survive the outcome-label
problem in I-18.

**Proposed fix.** Build the distribution from the log; rerun `expected_runs_play` vs
`CURRENT` (the earlier negative result used the pool).

**Verify / brief / status.** As for I-13. Open; better after I-18 refreshes the rows.

**RESULT 2026-09-21 (agent_progress/issues/I-15-16-17/, 12,000 halves x 3 seeds,
`expected_runs_play`-style batting vs `CURRENT`; the pool-dist control reproduces the
shipped `expected_runs_play`'s per-match score array exactly).** Built the opponent
pitcher distribution from `match_log.jsonl` in the MAIN CHECKOUT (read-only): of **520**
total rows, **151** carry a local reveal read (`outcome_basis` or `margin` present, the
withdrawn score-went-up classifier's **369** rows excluded), and of those, **82** are
`phase == "batting"` (we bat, opponent pitching against us — the distribution wanted).
Effective power = `opp_power + opp_tactics_bonus` when `opp_tactics_kind` is a swing or
pitch boost, verified by hand against the log's own `margin` field on six bonus rows.

    pool-derived   (4:4.0%  5:24.2%  6:22.7%  7:14.6%  8:12.1%  9:12.1%  10:10.1%)
    log-derived    (4:14.6% 5:24.4%  6:20.7%  7:17.1%  8:14.6%  9:7.3%   10:1.2%)  n=82

Swapping the log distribution into `expected_runs_play`'s scorer gave a **bit-identical**
per-match score array to the pool-derived control (1.6641 runs/half, 36.90% win, both
arms, delta +0.0000, sigma +0.00) and **0 of 4,000** sampled (hand, state) pairs picked a
different (card, tactics). The swap IS reaching the scorer — spot-checked by hand on an
8/9/5-power hand, EV 0.510 (pool) vs 0.598 (log), same chosen card — it just never crosses
an argmax boundary for hands drawable from this 33-card pool, despite the two
distributions genuinely differing in shape (log puts more mass at power 4, less at 9-10).
`expected_runs_play` itself still loses decisively to `CURRENT` either way (36.90% win,
consistent with the documented 39.8%/35.5% negative result at a different n) — the
opponent-model swap does not rescue it, because the losing mechanism (a myopic per-at-bat
EV, see `simulate.expected_runs_play`'s own docstring) is unrelated to which pitcher
distribution is plugged in. **CLOSED as not actionable: the knob changes nothing inside
this consumer, so there is no ship decision to make from this experiment.** Re-open only
if the opponent distribution is ever wired into a DIFFERENT consumer (e.g. a direct
power-margin threshold) where a boundary crossing is more plausible, or if the log grows
well past n=82. **Status.** closed (measured 2026-09-21, merged 7d9d198).

---

## D. Evidence gaps

### I-18  The at-bat log cannot answer win-rate questions                            P1  evidence

**Evidence.** `match_log.jsonl`: 373 real rows; 369 have `outcome_basis` None (the
withdrawn "score went up" classifier, CLAUDE.md §4), 4 have `margin` (all 2026-09-20).
Opponent tactics bonuses include 11 (x2) and 3 (x24), paid-model misreads. Run c: the
opponent's tactics KIND read `None` on 6 of 7 reveals; 1 of 3 turns was "not logged" for
want of an opponent read. 56 matches played, 4 usable rows.

**Root cause.** The reveal reader logs a row only when the local opponent read succeeds,
and the kind reader (`reveal_cards.TACTICS_KIND_MIN` 0.75) abstains on 29% of right-kind
frames (OPEN-24) and has 5 live fixtures.

**Proposed fix.** (a) Stamp rows with `classifier: "reveal_margin"`; `analyze_match_log.py`
filters on it. (b) OPEN-24's decision, needs the user's yes because it touches the turn
loop: keep one reveal frame per tactics play beside its row. (c) Score the kind reader on
`test_fixtures/reveal_kind_truth/live/` (5 frames) and raise the read rate with a bank
cut at native size (§10.30).

**Verify.** (a) a test that a row without the stamp is excluded; (c) 5/5 live fixtures
read the right kind with the wrong-kind max still under the gate.

**Agent brief.** Haiku for (a), Sonnet for (c). (b) waits for the user.

**Status.** (a) and (c) MERGED 2026-09-20 (8c99313). (a): `analyze_match_log.py` and
`tactics_effect.py` exclude rows with no `outcome_basis` KEY (it is absent on legacy rows,
not null) from outcome statistics, say how many, and take `--include-legacy`; the
power-only margin analysis keeps them. Two pre-existing crashes in analyze_match_log fixed
on the way. (c): live fixtures read 2/5 -> 4/5 after two native-size templates cut from
the pitch and speed fixtures; the held-out 48-frame corpus's wrong-kind max is 0.741,
still under the 0.75 gate. NOT fixed: the fielding_boost fixture renders in ZONE_HOME and
its banner sits above the padded band the reader searches, a zone/pad geometry gap in
`reveal_cards.py`, open. (b) MERGED 2026-09-20 (f459378) with the user's yes:
`record_reveal_kind` keeps one frame per tactics play under
`test_fixtures/reveal_kind_truth/auto/`, links it from the row as `reveal_frame`, and
refuses past 200 files; `tests/minigame/test_reveal_frame_kept.py`, three mutants caught.
Reveal-log crash fixed (21dd7589bfc29149e8b59f9b9b861819be98e6dc): `_ours_seen` was bound
only when the local opponent read succeeded and read unconditionally in the no-opponent
branch, so an occluded reveal printed UnboundLocalError instead of "no OPPONENT card
identified"; one binding added, pinned by
`tests/minigame/test_reveal_log_never_unbound.py`. Separately, the census's confirm_play
verify failure on 2026-09-20 was the game ignoring FIVE consecutive presses (frames
static, then the next poll's press landed), the longest run observed; PRESS_VERIFY_TRIES
= 5 is now at the observed maximum and is a tuning question, not a bug.

### I-19  There is no run census tool                                              P1  evidence

**Evidence.** Nothing summarises `overnight/run_one_match_*.log` into turns played,
refusals, deals timed out, reveals logged, stop reason. This review counted them by grep.

**Proposed fix.** `tools/run_census.py <log...>` printing one row per run with those
columns, plus a total. Every fix above reports before/after on that table.

**Verify.** Run it on the three 2026-09-20 logs; the counts must match this file's
(run b: 8 refused plays, 3 refused discards; run c: 3 plays, 3 deal timeouts with edge,
stop `unreadable_screens`).

**Agent brief.** Haiku (overflowed on CLAUDE.md; ran on Sonnet).

**Status.** MERGED to main 2026-09-20 (f25f5f0): `tools/run_census.py`, pinned by
`tests/harness/test_run_census.py` on the three 2026-09-20 logs. Unclassified lines it
reports: `slot(s) [N] were ALREADY unreadable`, `Decision: Playing` with no reveal episode
(3 in run a), `MEMORY WAS WRONG`. I-19b (200318a68bbf22b5b9723d1b40496390b27a0312): the
deal-timeout column had gone dead when I-09 reworded the message (a 10.1 shape in the
scorecard itself); it now counts both wordings, and six refusal shapes (false_cursor,
stray_guard, pre_press_guard, inferred_select, excluded, confirm_verify_fail) have
columns. QA round 4 (dc47548): the stray_guard column had gone dead a second time when
I-26 reworded its message; it now counts both wordings and a stray_relook column shows
recovered flickers.

### I-20  Coverage gaps on the match loop                                          P1  evidence

**Evidence** (rig scout, spot-checked by grep over `tests/`): no test asserts
`stop_reason == "unreadable_screens"`; none drives reset → money accounting end to end;
none covers `run_cycles.cycle()`'s liveness check; none covers "confirm_play dropped, the
next turn re-targets the still-lifted card". `test_run_motion_gate.py` covers
`frozen_stream` and `no_progress` well.

**Proposed fix.** Each gap is the Verify line of I-03, I-06, I-05 and I-11 respectively;
no separate work.

**Status.** Folded into those issues.

---

## Status at the end of 2026-09-20

Merged: I-01, I-03, I-04 (win), I-06, I-07, I-08, I-09, I-10, I-11, I-12, I-18 (a, b, c),
I-19, I-21, I-22, and I-02's offline half. Closed by measurement: I-13, I-14. QA round 1 on
the merged diff: four confirmed findings, all fixed and skeptic-verified (7b5aba2); full
suite 258 files green. A slot flickering to UNKNOWN resetting the stall counters, flagged by
`agent_progress/census-20260920`, was reproduced against the live log and closed as I-27.

Still open, in order:

1. I-02 live check (a slot-4 discard through the probe-select) and I-21 live confirmation
   (a 9 selected in one press). Both cheap with crawl mode's `d4` override.
2. I-04 DRAW fixture on the first live draw.
3. I-05 the unattended cycle: `run_cycles` must call `ensure_live` and a screen reader
   before its first press, and `reset_environment` must reconcile the balance from the
   pause menu (QA round 2 traced the stale-$46 refusal).
4. I-15, I-16, I-17 simulator A/Bs (I-17 after the log has modern rows).
5. I-18's fielding-boost zone gap in `reveal_cards.py`.

### I-45  QA6 test hygiene                                                          P2  test

**Evidence.** Four fixes from the QA6 finder, merged 738a2e7: `load_log_distribution()`
no longer `open()`s a gitignored one-off artefact (crashed with `FileNotFoundError` on a
fresh clone) — it now derives the opponent-pitcher power distribution live from
`match_log.jsonl` (tracked) by ISSUES.md I-17's method, falling back to a pinned snapshot
(`tools/ab_data/opp_pitcher_dist_20260921.json`) when the tracked log has zero qualifying
rows; `test_hand_memory_persists.py` no longer globs the gitignored 1.4G
`agent_progress/deal-frames/` tree, using two named fixtures under
`test_fixtures/deal_frames/` instead; `test_hand_read_two_lifted.py`'s negative-control
fixture moved from the live-written `overnight/local_hand/` to `test_fixtures/hand_reads/`;
and `LIVENESS_MISS_SEC` (6.0) / `MONEY_READ_MAX_FILES` (200) are now pinned as literals in
their tests.

**Status.** Merged fd2c6ccb5db1f3d24529d6fe22234997e66b4fe7. All seven required tests pass
against a clean checkout of that sha (verified in an isolated `git worktree add --detach`
at HEAD, so the check runs on tracked content only); `test_no_shadowed_module_defs.py` and
`test_no_undefined_names.py` are also green. Both fails-loudly claims proved: renaming
`tools/ab_data/opp_pitcher_dist_20260921.json` makes `test_ab_controls_reproduce_baseline.py`
die with `FileNotFoundError` naming that exact path (exit 1); renaming
`test_fixtures/deal_frames/hand_memory_drive_01.png` makes `test_hand_memory_persists.py`
die with `FileNotFoundError` naming that exact path (exit 1). Both files restored, `git
status --porcelain` clean of any `T` (rename) entries afterward.
`test_run_gates_on_liveness.py`'s full census ran in 126s (under the 3-minute budget) and
passed. `tests/harness/test_claude_md_constants.py` and `test_reload_wallet_guard.py` pass.

**Open finding — CLOSED 2026-09-21.** Run against THIS checkout's actual on-disk
`match_log.jsonl` (520 rows, 151 uncommitted since the tracked 369) rather than a clean
checkout, `test_ab_controls_reproduce_baseline.py` FAILED: the extra rows on disk are
enough (82 qualifying) that `load_log_distribution()` no longer takes the
zero-qualifying-rows fallback branch and instead derives a live distribution, which does
not bit-for-bit match the pinned 20260921 snapshot. On inspection the mismatch was
entirely a cosmetic `source` string (the live-derived meta's probabilities and counts were
identical to the pin's) — so the check was asserting equality with a file that is
guaranteed to go stale the moment a match is logged, which is the same "asserting a
growing file equals a snapshot" shape CLAUDE.md §10.16c/2 warns about, pointed at the
test itself. Fixed: `test_ab_controls_reproduce_baseline.py` no longer asserts
`meta == _pinned`. It instead validates each artefact for what it actually needs to be —
the pinned snapshot's own `effective_power_probs` sum to 1.0 (this is what
`load_log_distribution()`'s fallback branch returns verbatim, so a corrupted pin is a live
defect), and the live-derived `log_dist` (whichever branch fired) has keys within the
plausible effective-power range 4-11 (base power 4-9 per CLAUDE.md sec 4, plus a
swing/pitch tactics bonus of at most +2). Loading the pinned file unconditionally, with no
try/except, keeps the fails-loudly behaviour if it goes missing. Mutation-tested:
corrupting the pin's probabilities to sum to 1.5 makes the test fail on that exact check;
restored and sha256-verified back to `d09cbcb...` (unchanged from HEAD, confirmed via
`git status --porcelain`). The i15/i16/i17 exact-equality control checks were never
affected by this — they compare simulate.py's own deterministic scorers against each
other and never touch `match_log.jsonl`.

### I-46  Raised card's disc located on the decorative icon, digit reads None (8%)     P2  reader

**Evidence.** `agent_progress/census/raised_disc/` (2,446 sampled frames across three
recorded runs): on a RAISED (selected) player card, `read_hand` locates a disc
(`y_from == "disc"`) but `read_digit` returns None on 23 of 287 (8.0%). Every one of the
23 digits is plainly legible by eye on the contact sheet
(`agent_progress/census/raised_disc/sheet.jpg`); `read_digit`'s own template score tops
out at 0.793 across all 23, cleanly under `MIN_SCORE` 0.80 (the real-digit population's
own minimum is 0.821), so the gate is correct and was not moved.

**Root cause, measured** (`agent_progress/issues/I-46/progress.md`): a small decorative
icon (a baseball-seam on a PITCHER card, a bat on a BATTER card) sits over the top-left
of the power disc. On a raised card the true digit's own ink either never clears any of
`DARK_THRESHOLDS`/`RAISED_DARK_MAX` (the brightened card washes it out) or MERGES with
the brightened ring into a blob too big for `circle_finder`'s `DIGIT_W`/`DIGIT_H` gates
(measured merged blobs 37x34 and 57x59, against a digit's 6-26 x 10-32) -- while the
icon, a separate sprite unaffected by the brightening, stays an isolated blob of exactly
digit size and wins every candidate pass, correctly reading nothing. This is NOT a
candidate-selection bug: `_white_discs`'s own digit-in-disc extraction, checked
independently, lands on the SAME icon in 20 of 22 cases it fires on at all (within
1-23px), and the existing `RAISED_DARK_MAX` circle-finder pass proposes zero candidates
in its own search window on all 23 frames. There is no discarded correct candidate for a
rank-ordering fix to prefer -- the true digit is simply never proposed by any
circle-finding pass.

**Fix** (`local_hand.py`, `RAISED_SEARCH_DY`/`DX`/`STEP`/`R` and the loop appended after
the existing `RAISED_DARK_MAX` pass in `_read_fan`): search POSITION directly near the
slot anchor, scored only by `read_digit`'s own `MIN_SCORE` gate (untouched) -- the same
shape `DIGIT_RADII` already uses to search SCALE. A raised card lifts fairly
consistently (measured over 22 of 23 census frames via an exhaustive grid search: dy
-49..-34 anchor px, dx -10..+14); the shipped window (dy -60..-25, dx +-20) is generous
around that, not fitted to it. It runs only where every pass above still leaves a
PLAYER slot's digit unread, so it can add a reading and never change one.

**Verify.** Regression corpus (`overnight/local_hand/*.png` + `test_fixtures/hand_reads/`,
2,409 frames), HEAD vs the fix: digits CHANGED 0, previously-read now None
(regression) 0, previously None now read 4 (all "9", scores 0.86-0.95, confirmed
correct by eye against the source frames). On the 23-frame census itself, through the
actual production `read_hand()`: 17 of 23 now read, every one matching the digit
legible on the contact sheet by eye. The remaining 6 sit outside the deliberately
narrow, safety-margined search window (near-duplicate frames of the same hand whose
frame-to-frame jitter pushed the digit out, or one frame where the icon nearly fully
covers the digit) and correctly still abstain rather than guess.
`tests/minigame/test_raised_disc_reads.py` pins 5 of the census frames (copied to
`test_fixtures/hand_reads/i46_raised_{1..5}.png`) plus a control fixture that already
read correctly before the fix and must read identically after it. Mutation-tested:
reverting `local_hand.py` to HEAD makes all 5 new-reading assertions fail (exit 1);
restored and sha256-verified. `tests/minigame/test_verified_selection.py`,
`test_hand_read_two_lifted.py`, `test_hand_memory_persists.py`,
`tests/harness/test_no_undefined_names.py`, and `test_claude_md_constants.py` all pass
unchanged.

**Status.** merged 15cfac4, narrow window kept. Independent skeptic review
(`agent_progress/issues/I-46/skeptic.md`) reproduced the regression check and the
17/23 census result exactly, confirmed scaling and the "cannot overwrite a read
digit" invariant by tracing, and found two small defects: D1, the search wrote `y`
but not `x`, so 3 of 34 real hits checked offline kept the EARLIER pass's `x` (the
icon's), up to 67px off; D2, a dead `x = r.get("x")` fetch. Both fixed here. A
WIDE-vs-NARROW window comparison was run (WIDE recovers 22/23 census frames instead
of 17/23, at 0 accuracy cost measured offline, but costs 274ms/one firing slot and
539ms/two against a 150ms poll, versus NARROW's 77ms/138ms) -- NARROW is kept for the
runtime margin; the full table is in skeptic.md. `local_hand.py` also now documents,
where `SELECTED_MIN_RISE` sits, that the search window (dy -60..-25) lies entirely
above it, so every slot this pass reads is reported SELECTED by construction (a fact
of the window's geometry, not an independent measurement) -- and records the measured
runtime (0/1/2 firing slots: ~36/77/138ms; 87.9% of frames fire zero times). The new
test's (a2) section pins D1 against x positions measured independently of this fix's
own output; mutation-tested (dropping the x write makes it fail, restored and
sha256-verified). `local_hand.py` and the new test are the only files touched besides
this entry.

### I-47  Two silent permissive defaults in offline tools (QA7)                     P2  evidence

**F1. `load_log_distribution()` in `tools/ab_engine_i15_16_17.py` fell back to the
pinned snapshot silently, and its own docstring described a narrower trigger than the
code.** The branch is `n_used == 0` (rows must be `phase=="batting"` AND carry a
non-null `opp_power`), not "zero qualifying rows" as the docstring and ISSUES.md I-45
both said — a log whose qualifying rows are all pitching, or all `opp_power: null`,
also falls back with zero output and a `meta` dict shaped identically to a
live-derived one. Reproduced with a synthetic 3-line `match_log.jsonl` (2 pitching
rows + 1 batting row with `opp_power: null` — 3 "qualifying" rows, 0 usable):
`n_used=0` triggers the pinned fallback even though `qualifying=2`, silently.
`test_ab_controls_reproduce_baseline.py`'s own check (`meta["n_used_for_distribution"]
> 0`) did not catch this, because the fallback also satisfied it (it returned the
pin's own `n_used_for_distribution: 82` verbatim, reporting the SNAPSHOT's n as if it
were live).

**Fix.** The fallback branch now prints one line to stderr naming the reason (rows
with a local reveal read but none phase==batting with a non-null opp_power) and the
pinned path; the returned `meta` carries a dedicated `meta["fallback"]` bool (`True`
on fallback, `False` when live-derived) and separates the two `n` quantities that were
being conflated — `meta["n_used_for_distribution"]` is now always THIS checkout's own
live count (honestly 0 on fallback), and `meta["n_used_for_distribution_pinned"]`
carries the pinned snapshot's own n under its own key.

**F2. `labels_for()` in `tools/cursor_labels_from_lifts.py`: the capture-gap and
flicker filters both passed silently with under 2 frames of history.** `gap_ok =
len(hist) < 2 or hist[-2] == hist[-1]` and `window = hist[-(flicker_window+1):-1] if
len(hist) > 1 else []` both defaulted to permissive (gap_ok=True, no flicker window to
check) whenever fewer than 2 valid frames had been seen since the last capture-gap
reset — i.e. the first candidate right after a `sel is None` reset kept its label with
reason `None`, indistinguishable from a genuinely 2-frame-verified one. That is
exactly the shape both filters exist to catch (I-42): a rise right after instability,
just with the instability being "too little history" rather than "a recent jump".

**Fix.** With fewer than 2 prior frames, the candidate is now REJECTED with reason
`"insufficient_history"` instead of passed. `capture_gap` and `flicker` are unchanged
for candidates with >=2 frames of history.

**F3 (found reviewing F1's own test coverage).** The pre-fix test file never actually
executed `load_log_distribution()`'s fallback branch's own code — its "pinned
probabilities sum to 1" check re-opened the JSON with a bare `json.load` and never
called `load_log_distribution()` at all, so a mutant corrupting the fallback branch
itself (e.g. leaving its returned keys as strings instead of `int`) would have
survived the whole file. Fixed by adding a case that monkeypatches
`ab_engine._MATCH_LOG_PATH` to the same synthetic all-pitching/null-power log used for
F1 and calls `load_log_distribution()` for real, asserting on the RETURNED
distribution: `meta["fallback"] is True`, `meta["n_used_for_distribution"] == 0`,
integer keys 4-11, probabilities summing to 1 within 1e-9.

**Verify.** `tests/minigame/test_ab_controls_reproduce_baseline.py` (F1, F3) and
`tests/harness/test_cursor_labels_capture_gap.py` (F2, cases 9-10) both green.
`tests/harness/test_no_undefined_names.py` and `tests/harness/test_claude_md_constants.py`
also green. Three mutants applied by hand, `__pycache__` deleted before and after each
(CLAUDE.md 10.10), each confirmed to fail the relevant test, then reverted and
`git status --porcelain`/`diff` confirmed byte-identical to HEAD before commit:

    `d["fallback"] = True` -> `d["fallback"] = False` in the fallback branch
        -> test_ab_controls_reproduce_baseline.py: 2 checks FAIL (the fallback-or-
           positive check, and F3's `meta["fallback"] is True` check)
    `[(int(k), v) for k, v in ...]` -> `[(k, v) for k, v in ...]` (string keys)
        in the fallback branch's return
        -> test_ab_controls_reproduce_baseline.py: TypeError on the existing
           "keys are plausible effective powers 4-11" check (4 <= p <= 11 on a str)
    restore the permissive default (`gap_ok = len(hist) < 2 or hist[-2] == hist[-1]`,
        `window = ... if len(hist) > 1 else []`) in `labels_for()`
        -> test_cursor_labels_capture_gap.py: case 9 FAILS (f00.jpg wrongly kept
           with reason None instead of rejected as insufficient_history); case 10
           still passes (a discriminating mutant, not a vacuous one)

Also re-ran `tools/cursor_labels_from_lifts.py` on `screenshot_log/run_20260921_080311`
(8036 frames, main checkout) end to end with the fix: `raw candidates 173 -> kept 41,
rejected 132 {'capture_gap+flicker': 38, 'flicker': 62, 'transient': 29, 'capture_gap':
3}` — identical to the pre-fix 173/41 split, with zero `insufficient_history`
rejections in this particular run (no candidate in it happened to sit inside 2 frames
of a reset), so the fix changes no label on this corpus while closing the gap the QA7
finder demonstrated synthetically.

**Status.** Merged 3d0526c. `tests/minigame/test_ab_controls_reproduce_baseline.py` and
`tests/harness/test_cursor_labels_capture_gap.py` re-run on main post-merge against this
checkout's own grown `match_log.jsonl`: both exit 0. `test_no_undefined_names.py`,
`test_no_shadowed_module_defs.py` and `test_claude_md_constants.py` also green; a
`find | xargs grep` for `labels_for`/`load_log_distribution` across `tools`, `tests` and
`overnight` (CLAUDE.md sec 2's `.gitignore`-blind-`grep` warning) turned up only the four
files already covered here. Two independent mutants spot-checked post-merge, each
`__pycache__`-cleared and sha256-restored: `len(hist) < 2` -> `< 3` in `labels_for` makes
case 10 (the 2-prior-frames control) FAIL as insufficient_history instead of KEPT;
dropping `d["fallback"] = True` from the fallback branch (stderr line left intact) makes
F3's `meta["fallback"] is True` check die with `KeyError: 'fallback'`. Both restored;
`git status --porcelain` shows no source diff.

### I-48  A failed TACTICS select burns every batter before the loop plays anything    P1  play

**Evidence.** Census over every `overnight/run_live_2026092*.log` in the main checkout
(23 files), counting `[cursor] select_card never landed after 5 attempts — refusing`:

    file                       events  path    target       slot(s) already    slot UNKNOWN/    resolution
                                                              selected           occluded
    run_live_20260920d.log       1     PLAY    batter (1)    none               none at the time  1 refusal, then I-21 blinded
                                                                                                    slot 1's own disc on the
                                                                                                    retries, 2 more refusals on
                                                                                                    "position unreadable", then
                                                                                                    excluded as UNREADABLE (3x);
                                                                                                    next turn played hand_index 4
    run_live_20260921e.log       1     DISCARD slot0         none               none               "discard NOT CONFIRMED";
                                                                                                    re-read next poll, the
                                                                                                    discard HAD landed; no
                                                                                                    exclusion, one turn's delay
    run_live_20260921n.log       3     DISCARD slot3 (x3)    none               none               each "discard NOT CONFIRMED";
                                                                                                    after the 3rd, the EXISTING
                                                                                                    discard-stall breaker played
                                                                                                    the hand instead of looping
    run_live_20260921r.log       6     PLAY    TACTICS       none               slot 2 UNKNOWN     2 batters excluded in turn
                                                              (slot 1, swing_                       (hand_index 4, then 3) before
                                                              boost) every                          hand_index 0 finally worked
                                                              time; batter                          (0->1 is one step, no
                                                              varies 3,4,4,3,3,3                     crossing); ~5 min lost,
                                                                                                    one hand played on a worse
                                                                                                    card than the engine chose

11 events total. 4 (20260921e, 20260921n) are on the DISCARD path (`select_and_discard`
/ `_DISCARD_STALL`), a different tracker with its own re-read-next-poll and
play-instead-of-looping breakers already built — out of scope here, unaffected by this
fix. Of the 7 PLAY-path events, 1 (20260920d) is a genuine BATTER failure with no
occlusion in sight, which escalates through I-21's own "selecting is what blinds the
disc" mechanism to a legitimate permanent exclusion — also out of scope, and correctly
handled by the existing code. The other 6 (20260921r, one match) are the shape this
ticket is about: the BATTER's own walk+select lands cleanly every single time
("`[cursor] verified on <batter> after N press(es)`" then a landed `select_card`), the
cursor then walks to the TACTICS slot (1, POWER SWING / swing_boost) and verifies
there too, and `select_card` never lands on slot 1 after 5 attempts — every time the
batter sits at slot 3 or 4, on the far side of slot 2 (UNKNOWN all hand, occluded by a
home-plate runner's card). The one instance where the tactics select landed easily
(1 retry) is the batter=0 case, where the walk to slot 1 is a single adjacent step and
never crosses slot 2 (`run_live_20260921r.log:746-751`).

**Root cause**, traced in the code (not guessed):

1. **The exclusion keys on the wrong target.** `orchestrator.py:8384-8401` calls
   `exclude_play_slot(player_idx, _reason)` on any refused `select_and_play(player_idx,
   tactics_idx, ...)` — always the BATTER's hand_index, because `select_and_play`
   returns a single bool for the whole call
   (`input_controller._verified_select_and_play_inner`, ~:1919-1994) and orchestrator
   has no way to see whether it was `card_index` (the batter) or `tactics_index` (the
   tactic) that actually failed to verify inside it. `_slot_position_readable` (used to
   pick `PLAY_REFUSAL_UNREADABLE` vs `PLAY_REFUSAL_TRANSIENT`) also only ever inspects
   `player_idx`'s own `y_measured`, never the tactic's. So on a tactics-select failure
   the code excludes a batter whose own selection worked perfectly, learns nothing
   about the actual problem (slot 1 / slot 2), and burns through every batter until one
   happens to be reachable without crossing the occluded slot.
2. **What the walk from slot 3/4 to slot 1 does when slot 2 is occluded.** The WALK
   itself is fine — `_walk_cursor_to` already dead-reckons across one occluded slot
   (I-32) and every failing turn logs `verified on 1 after N press(es)`, proving the
   walk lands. The failure is specifically in the SUBSEQUENT `_select_verified(1,
   look)` call: `select_card` is pressed and re-read up to `SELECT_ATTEMPTS` (5) times,
   and every attempt reports "did not land" (the plain "readable, not in `sel`, retry"
   branch, not the I-21 blind-disc rescue — `ys[1]` stays readable throughout every
   failing turn's log). The log evidence supports a correlation between the crossing
   and the subsequent select failing, not a proven mechanism for WHY the select itself
   (as opposed to the walk) is what fails — that would need a live screen to settle
   (which mode this task is confined off of). What IS established: it is never the
   batter's own select that fails in this match, only the tactic's, and only when the
   batter sits on the far side of the occlusion.

**Fix**, two parts, both in `input_controller._verified_select_and_play_inner`
and `orchestrator.py`:

1. **`input_controller.py`**: the per-target loop (`for target in (card_index,
   tactics_index): ...`) now tells the two targets apart. A BATTER failure is
   unchanged — same unwind, same `return False`. A TACTICS failure (only reachable
   once the batter has already succeeded, since it is always processed first) unwinds
   ONLY the tactics attempt (`_unwind_selection(before_all, look, {tactics_index},
   ys0=_ys0)`, never touching the batter's own already-verified selection), drops
   `tactics_index` to `None`, and falls through to the SAME commit path every
   successful play already uses (`want`/`_clear_strays`/`press_verified`) — so a
   boost that cannot be verified costs nothing but the boost (~+0.6 runs/half,
   CLAUDE.md §4) instead of the batter, the hand, and the exclusion budget.
2. **`orchestrator.py`**: `record_refused_select` (new, beside `record_money_read_
   frame`) keeps one frame + why.json per refused `select_and_play` call under
   `diagnostics/deal_frames/refused_select_<ns>/` — `target`, `kind` ("player" or
   "player+tactics", since orchestrator still cannot see which of the two failed
   inside a single bool), `already_selected` (from a fresh `hand_cursor_look()`, not
   a stale decision-time snapshot) and `attempt` (`play_stalled`'s own running
   count). Same shape as `record_local_hand`/`record_reveal_kind`/
   `record_money_read_frame`: never raises into the turn loop, writes nothing under
   `BASEBALL_TEST_RUN` unless a test hands it `out_dir`, REFUSES past 200 dirs
   rather than pruning (OPEN-24's lesson). None of the six I-48 refusals in
   `run_live_20260921r.log` had a kept frame before this — this is what would have
   let a human see slot 2's occlusion at the moment of failure instead of
   re-deriving it from the log.

**Verify.** `tests/minigame/test_tactics_select_fallback.py` (new): cases A (tactics
never lands -> batter alone committed, one confirm press, tactics attempt unwound,
log names the fallback), B (tactics lands -> both committed, control, unchanged), C
(batter itself never lands -> refused exactly as before, control), D
(`record_refused_select` writes nothing under `BASEBALL_TEST_RUN`), E
(`record_refused_select` writes the dir + all four why.json fields with an explicit
`out_dir`, same seam `record_reveal_kind` uses). Three mutants, each a REAL edit to
`input_controller.py`/`orchestrator.py` on disk with `__pycache__` cleared and the
module reloaded, sha256-verified restored afterward: dropping the batter-alone commit
(the fallback's `continue` -> `return False`) makes case A refuse; dropping the
`_unwind_selection` call in the fallback makes case A's unwind-spy record zero calls;
dropping `kind`/`already_selected`/`attempt` from `record_refused_select`'s
`json.dump` makes case E's field checks fail. All three caught; all three restored
(`git status --porcelain` clean; sha256 matches HEAD).

**2026-09-21 fix:** case D re-pointed at a temp root (`orch.DEAL_FRAME_DIR`
monkeypatched) instead of the real `diagnostics/deal_frames/` — CLAUDE.md §2, it was
reading the live directory and failing whenever a live cycle had left
`refused_select_*` entries there. orchestrator.py sha
`f8f98603fa7d499e0b2c90faa315bb706206e9fb3001af47a5bc30ae1a1b3acd` (unchanged).

Also green: `tests/minigame/test_verified_selection.py`,
`test_commit_refuses_unseen_strays.py`, `test_i22_pitch_boost_slot3.py`,
`test_hand_memory_persists.py`, `test_run_debit_and_scoring.py`,
`tests/harness/test_no_undefined_names.py`, `test_no_shadowed_module_defs.py`,
`tests/rig/test_no_real_input_under_test_run.py` (the emission census — the new
frame keeper does a screen GRAB, no press, and was not flagged as a new input site).

**Skeptic round (`agent_progress/issues/I-48/skeptic.md`): CONFIRMED WITH NOTES, three
edits.**

- **S-2 (defect, latent).** The fallback guard was `target == tactics_index and target
  != card_index`, true when `card_index` is `None` — a tactics-only call (the signature
  allows it; no production caller passes it today) whose select never lands took the
  fallback, `want` became `set()`, and `_clear_strays` passed vacuously — confirm_play
  sent on an EMPTY fan, reporting True. Fixed: `and card_index is not None` added to the
  guard. Case F pins it (`tests/minigame/test_tactics_select_fallback.py`).
- **S-3 (defect, real, unmeasured before this).** The batter-alone fallback committed a
  play with NO WAY for `play_one_turn` to learn the tactics card was dropped:
  `note_slot_dealt(player_idx, tactics_idx)` claimed a slot that was never spent, and
  `matchup_info["our_tactics_bonus"/"our_tactics_kind"]` still recorded
  `decision.tactics_card`'s own bonus/kind — what the ENGINE CHOSE, not what was
  actually played. `match_log.jsonl` would have recorded a boost that never went in, on
  exactly the field OPEN-24 calls this project's only non-circular tactics ground truth,
  and `record_reveal_kind` would have kept a labelled reveal frame for a reveal with no
  tactics card in it — poisoning the `TACTICS_KIND_MIN` corpus. Fixed: a module flag
  beside `_MAYBE_LIFTED` (`input_controller._LAST_PLAY_DROPPED_TACTICS`, cleared at the
  top of every `_verified_select_and_play_inner` call, set only in the fallback branch;
  read via `tactics_dropped_last_play()`). `orchestrator.play_one_turn` reads it right
  after `select_and_play(...)` returns True, before `note_slot_dealt`/`matchup_info`:
  drops `tactics_idx` from `note_slot_dealt`, zeroes `our_tactics_bonus`/sets
  `our_tactics_kind` to `None` (which also makes `record_reveal_kind`'s own `if not
  kind: return None` gate skip the frame — one field change closes both holes), and adds
  `"tactics_dropped": true` so a later census can tell "no tactics card was ever chosen"
  apart from "one was chosen and dropped". Case G pins it, driving the REAL
  `play_one_turn`/`hand_to_cards`/`best_batting_play` (not a scripted `matchup_info` —
  `tests/minigame/_run_harness.py`'s `Harness` stubs `play_one_turn` out entirely via
  `play_results=[...]`, so it cannot exercise a fix that lives inside that function).
- **S-4 (defect, in the guard's own proof).** Case D's two checks passed even with the
  `_running_under_test()` guard stripped, whenever `_grab_settle_regions` happened to
  raise (any headless box, or chiaki down) — `record_refused_select`'s own
  `except Exception: return None` supplied the same answer the guard would have, so the
  test proved nothing about the guard specifically. Fixed: case D now stubs
  `_grab_settle_regions`/`hand_cursor_look` to WORK, the same as case E, so the write is
  what the mutant actually has to survive.

Re-ran the skeptic's own M1-M4 against the fixed code (real file mutation,
`__pycache__` cleared, sha256-verified restore, scratchpad script, not shipped):
M1 (fallback fires for the batter too) CAUGHT, M2 (`_clear_strays`'s `want <= lifted`
dropped — pre-existing code, unchanged by this fix) CAUGHT by
`test_commit_refuses_unseen_strays.py` (confirmed directly against that file, EXIT=1,
3 checks fail), M3 (unwind the full target set instead of `{tactics_index}`) CAUGHT,
M4 (strip the `BASEBALL_TEST_RUN` guard, capture stubbed to succeed) CAUGHT. Plus the
three mutants above (case A/A/E). All seven caught; both files restored byte-for-byte.

**LATER (not fixed now, per the skeptic and the coordinator's call): the tactics slot
is NOT excluded after the fallback fires.** Only the batter is spared exclusion —
`note_play_refused()`/`exclude_play_slot` are never reached because `select_and_play`
returns True. Nothing marks tactics_idx as unreliable, so the NEXT turn re-offers the
same tactics attachment, and if the same occlusion-crossing problem recurs it burns
`SELECT_ATTEMPTS` (5) presses again — roughly 5 x (0.60 + 1.60)s ≈ 11s — before falling
back a second time. This converts I-48's deadlock into a per-turn TAX rather than
removing it; not a stall (the play still commits every time), just a repeated cost.
Fixing it would mean tracking a per-slot-per-reason exclusion for TACTICS attachments
separate from `_PLAY_STALL` (which is keyed on the player_idx the play command
targets, not the tactics_idx) — new state, not a one-line change, and deliberately
deferred.

**Status.** merged db3bfcb247a085d50411d5056a28fe00e91c8e5c, skeptic CONFIRMED WITH
NOTES round 1, S-2/S-3/S-4 fixed 2c6cca5, 7/7 mutants; LATER: tactics slot not
excluded after the fallback (~11 s per later turn).

test_refusal_unwinds.py reconciled 307408c: scenarios 3 re-pinned to the
batter-alone contract, 1 kept (plus 1 new scenario added so the
general-refusal unwind's own mutant has something real to catch).

QA8 (`agent_progress/qa8/silent_state`): `orchestrator.spend_and_play` never read
`input_controller.tactics_dropped_last_play()`, so `tools/match_crawl.py` printed
"COMMITTED" for a batter-alone fallback play the same way `play_one_turn` already
guards against (~8473); fixed by reading the flag in `spend_and_play` itself and
printing/returning the drop via the existing `(ok, why)` tuple, case H + mutant 4
in `tests/minigame/test_tactics_select_fallback.py`.

### I-49  A readable reveal's row is staged, then dropped by a later poll's failure (21 of 36 orphans)  P1  evidence

**Evidence.** `agent_progress/census/reveal_orphans_trace/` traced 42 fully-readable
reveal frames (36 class-A + 6 class-C) that produced no `match_log.jsonl` row, by
walking each frame's own run log for the drop signature. 21 of the 36 class-A frames
had already been STAGED (`pending_matchup = matchup_info` — powers, kinds, bonuses,
phase all known) and were then dropped by a LATER poll's own failure, not by the
staging turn itself:

    12   `pending_read_failures > MAX_PENDING_READ_FAILURES` -- "N consecutive
         unreadable screens" (orchestrator.py ~:8845)
     9   the follow-up read came back with no score -- "outcome unscorable:
         <field> missing from the follow-up read" (~:8907)

Both sites read `if pending_matchup is not None: print(...); pending_matchup = None`
— the row was discarded outright, with nothing but a print line marking that it ever
existed. CLAUDE.md §4 already says the outcome comes from the REVEAL's margin (a
wrong score is worse than no score); these two paths were the DATA equivalent —
a real at-bat's cards, thrown away because the SCORE could not be attributed, when
the cards alone are real evidence for the margin/secondary questions
`analyze_match_log.py` already answers powers-only.

**Fix.** Both sites now `log_matchup()` the row instead of discarding it, with the
outcome-dependent fields explicitly null (`outcome`, `runs_scored`, `margin`,
`outcome_basis`) so no consumer can mistake it for a scored verdict, plus
`row_status: "unscored"` and a `drop_reason` string naming which of the two killed
it (`"<N>_consecutive_unreadable_screens"` or
`"outcome_unscorable:<field>_missing"`). The successful scoring call (the ONE other
`log_matchup` call site in the file) is unchanged except for `row_status: "scored"`,
added so any consumer can filter by status without inferring it from which fields
are null. classify_outcome/reveal_margin/the margin rule are untouched — nothing
about how an outcome is DECIDED changed, only what happens when it cannot be.

**Out of scope, deliberately.** A third drop site (~:9091,
`TRANSITION_SCREEN_MAX_SEC` outlasting a stuck `new_inning`/`reveal_recap`) has the
identical `pending_matchup = None` shape and is not touched: 0 of the 42 traced
frames died there, it sits outside the ticket's named line ranges
(orchestrator.py ~8840-8915 / ~10150-10245), and `test_transition_screens_recognised.py`
section 5 already pins `len(logged) == 0` for it — left alone rather than guessed at.
Also out of scope: the give-up/abandon row producer in `reset_env.py`
(`tests/rig/test_abandoned_match_is_recorded.py`), a different code path with no
`row_status` field at all; not touched.

**Consumer decisions**, one per file that reads `match_log.jsonl` (found via
`find . -name '*.py' -not -path './.venv/*' -print0 | xargs -0 grep -l match_log`,
excluding `agent_progress/` and `drafts/`):

    analyze_match_log.py        NO CHANGE. has_outcome_basis(row) is
                                `bool(row.get("outcome_basis"))`, and an unscored
                                row's outcome_basis is None -- it already excludes
                                itself from `outcome_rows`/the outcome tally/the
                                baseline, the same bucket legacy pre-classify_outcome
                                rows already fall into. The margin/secondary analysis
                                (the `usable` list) is legacy-inclusive BY DESIGN
                                (reads *_power/*_tactics_bonus/*_tactics_kind, never
                                `outcome`) and effective_power() does not consult
                                row_status -- so an unscored row's REAL powers are
                                usable there with zero changes, which is the "MAY use
                                the power distribution" half of the ticket.
    tactics_effect.py           NO CHANGE. Same has_outcome_basis() gate, one line:
                                `rows = [r for r in rows if aml.has_outcome_basis(r)]`
                                before any win-rate arithmetic runs. Every statistic
                                in this file is scored on `outcome`, so it is the
                                right file to exclude unscored rows from entirely,
                                and it already does.
    tools/ab_engine_i15_16_17.py NO CHANGE. load_log_distribution()'s qualifying
                                (load_log_distribution)   test is `"outcome_basis" not in row and
                                "margin" not in row: continue` -- KEY PRESENCE, not
                                truthiness. An unscored row carries both keys (value
                                None), so it is NOT excluded; its real opp_power feeds
                                the opponent-pitcher-power distribution exactly as the
                                ticket allows ("the power is real"). Verified directly
                                against the real function (not re-implemented) with a
                                synthetic 3-row log: a scored row and an unscored row
                                both count toward `n_used_for_distribution` (2), a
                                genuinely legacy row with NEITHER key is excluded (see
                                test scenario E).
    reset_env.py (a DIFFERENT   NOT TOUCHED -- out of scope, see above. Its rows carry
    producer, not this ticket) no row_status at all; a future ticket could add one.

**Verify.** `tests/minigame/test_unscored_reveal_rows_kept.py` (new, this ticket):
scenario A (streak drop -> unscored + drop_reason, plus an A-control proving a
streak one poll SHORTER than the bound still resolves normally), B (outcome-
unscorable drop -> unscored + drop_reason), C (control: a normally scored row is
row_status="scored" with its outcome intact and no drop_reason), D (the two
has_outcome_basis()-gated consumers need no code change), E (the key-presence
consumer, driven through the real `load_log_distribution()` against a synthetic
log). Also green: `test_run_debit_and_scoring.py`,
`test_stale_flag_never_presses_unpaid.py`, `test_run_resume_and_persist.py`
(one assertion updated — see below), `test_ab_controls_reproduce_baseline.py`,
`test_reveal_frame_kept.py`, `test_transition_screens_recognised.py` (one assertion
updated — see below), `tests/harness/test_no_undefined_names.py`,
`test_no_shadowed_module_defs.py`, `test_claude_md_constants.py`.

**Two pre-existing tests pinned the OLD (discard) behaviour on the exact two paths
this ticket changes, and both needed their assertion updated, not their mechanism**:
`test_run_resume_and_persist.py`'s `_dropped = _rows_after(6)` control used to assert
`not _dropped` (zero rows after six failed reads); it now asserts exactly one row,
`row_status == "unscored"`, `outcome is None` — the actual concern that check
existed for (no OUTCOME attributed across a stale gap) still holds, because the
outcome fields are null, not guessed. `test_transition_screens_recognised.py`
section 4's control (the same streak, its own scripted `ValueError`) got the same
treatment. Neither test's SCENARIO changed; only what a correct implementation is
now asserted to produce.

**Mutants (3, `__pycache__` cleared before/after each, sha256-verified restore to
`994655cc2f0685b49beadfe56296d6c947bc09e6dd99daf0849fe0df01a8b0fb`):**

    revert the append on the streak path (`log_matchup(...)` -> `pass`)
        -> test_unscored_reveal_rows_kept.py: scenario A FAILS (0 rows, expected 1)
    mislabel the outcome-unscorable append's row_status as "scored"
        -> test_unscored_reveal_rows_kept.py: scenario B FAILS (row_status check)
    drop the `drop_reason` field from the streak append
        -> test_unscored_reveal_rows_kept.py: scenario A FAILS (drop_reason check)

**Status.** merged 0a62bbf69c73cb343c3723d1bd92f0c2e523ee0c, skeptic CONFIRMED WITH
NOTES (rows carry no match id beyond ts; the transition-timeout drop site ~9091
still discards, 0/42 traced).

### I-48b/I-48c  A target verified earlier in an operation can be silently toggled down by a LATER blind press, and nothing re-checked before commit    P1  play

**Evidence.** `overnight/run_live_20260921s.log` ~369-400 (main checkout), the first
live firing of I-48's batter-alone fallback. Hand `[swing_boost +2, UNKNOWN
(occluded slot 1), 5/3 (card_index=2), speed_boost +1, 5/2]`, decision batter=2 +
tactics=0:

    [cursor] slot 1 is occluded (y unmeasured) — its glow cannot read; dead-reckoning one step across it
    [cursor] probe-select raised nothing (attempt 1/2) — retrying once; ...
    [cursor] probe-select raised nothing after 2 attempts — refusing
    [cursor] tactics slot 0 could not be verified — dropping the boost and playing the batter alone (I-48)
    [cursor] slot(s) [1] were ALREADY unreadable before this operation began — proceeding. ...
    [cursor] the engine's cards [2] are not all lifted ([]) — refusing to commit a partial selection

The whole play refused, having never re-attempted the batter. The refusal frame is
`diagnostics/deal_frames/refused_select_1790025302210541000/` (main checkout). On
the VERY NEXT poll the identical decision succeeded, via a different recovery path
("fan reads but the cursor is nowhere above the gate ... nudging off the blind
slot", "recovered on slot 0 after 1 nudge(s)").

**Root cause, traced in `input_controller._verified_select_and_play_inner`
(pre-fix ~:2027-2066).** The per-target loop is `for target in (card_index,
tactics_index):` -- card_index is listed first, so by the time the
`target == tactics_index` I-48 branch's own guard condition can even be reached,
card_index's iteration MUST already have returned `ok=True` (if it had failed,
`target == tactics_index` is false for `target == card_index`, and the loop falls
straight to the generic `_unwind_selection(...); return False` without ever
attempting the tactics target). That is airtight from control flow alone. So in
this play: card_index=2 was walked to and selected (silently -- no log line, the
"already selected" and "steps==0" success paths in `_walk_cursor_to`/
`_select_verified` print nothing), THEN the walk to tactics_index=0 dead-reckoned
across occluded slot 1 (which sits geometrically between 0 and 2, so a walk in
EITHER direction between them crosses it), and the subsequent I-02 probe
(`_probe_select_blind_target`, 2 attempts) failed twice.

The probe presses `select_card` BLIND, hoping the cursor physically reached the
tactics target. Its own success check, `new = [i for i in sel if i not in
before]`, only asks "did anything NEW appear selected" -- it has no way to notice
a slot that DISAPPEARED. If the navigation presses toward the tactics target were
silently dropped (section 5's measured 15.20% ignore rate, clustered), the true
cursor can still be sitting on card_index's own slot when the probe presses
`select_card` -- toggling the BATTER's own, already-verified selection, with the
probe reporting "raised nothing" either way.

**The independent skeptic review (`agent_progress/issues/I-48b/skeptic.md`) PROVED
this by elimination, and reproduced it from press mechanics alone.** Section 1
walks the log: the four presses between "batter verified" and "not all lifted"
are two `move_left` (which cannot toggle anything) and the probe's two
`select_card` presses, so a probe press putting the batter down is a DEDUCTION
from the log, not a hypothesis — and `probe2.py` R1 reproduces the exact log
sequence, wording included, from a physically-honest fake screen with no sabotage
hook at all. The one thing genuinely NOT recoverable from the log alone is the
precise press-by-press parity (whether it was one toggle or an even number that
happened to net to one) — the fix does not depend on that parity either way.

**The skeptic's N1 found the fix was NARROWER than the root cause.** The real
invariant that broke is stated in this ticket's title: *a target verified earlier
in this operation can be silently toggled down by a later blind press, and
nothing re-checked before commit.* The first cut of this fix put the re-check
only inside the I-48 branch (reachable only when the TACTICS target fails), so it
repaired exactly the shape above and missed the SIBLING shape, present twice in
the archive, where the TACTICS target's own walk and select both SUCCEED and the
BATTER is what gets silently lost instead — the I-48 branch never fires, so a
branch-local re-check never runs:

    run_live_20260921j.log:620-624
      verified on 0 after 2 press(es)   <- batter
      verified on 1 after 1 press(es)   <- tactics
      select_card did not land (attempt 1) — retrying
      select_card landed on attempt 2
      the engine's cards [0, 1] are not all lifted ([1]) — refusing

    run_live_20260921o.log:1040-1050
      verified on 3 after 2 press(es) ... verified on 4 after 3 press(es)
      the engine's cards [3, 4] are not all lifted ([4]) — refusing

Driven through the real code (skeptic's `probe3.py` R7): the play refuses with
exactly that message and nothing recovers the batter. So the first cut of this
fix repaired 1 of the 3 archived instances of the underlying defect.

**Fix**, in `input_controller._verified_select_and_play_inner`. The re-verify
moved from inside the I-48 branch to ONE shared place, right before the commit
gate (`_clear_strays`) that every path converges on:

1. **The batter is still processed first as a REAL invariant, not an assumed
   position.** `_batter_verified` is set True only when `target == card_index`
   succeeds; the I-48 fallback's own guard still requires it. `card_index`
   happening to be listed first in the loop's source tuple was never a proof by
   itself -- a reordering mutant (5) still needs this gate to refuse rather than
   silently proceed on an unattempted batter.
2. **Before the commit gate, re-read the fan once.** Every target still in
   `want` succeeded its OWN walk+select earlier in the loop (the loop's only
   other exit is a full refusal that already returned False), so `want` IS the
   set of targets this operation has already verified. For every one of them NOT
   seen lifted in this fresh read, retry `_walk_cursor_to`+`_select_verified`
   once -- the SAME calls the loop already uses, so no new constant and no new
   press budget. This covers BOTH shapes: the I-48 branch's own case (batter lost
   while tactics was failing) and the sibling case (batter lost while tactics
   succeeded), because it no longer cares which target failed, only which one
   is missing now.
3. If a retry also fails, refuse the whole play exactly as the pre-I-48 code did:
   unwind the full original target set, invalidate the cursor, return False.
   Never commits an unproven selection.

This is a SHORTER diff than the first cut (one copy of the re-check instead of
one embedded in a branch), and it is not a new mechanism -- the skeptic's own
recommendation (N1) names the same move. I-43's `_MAYBE_LIFTED` contract is
unchanged -- the retry-failure path reuses the same `_unwind_selection(...)` call
(existing marking logic intact) that the generic refusal branch already used;
the argument passing is keyword-explicit (`ours=targets`) on BOTH occurrences now,
to keep them textually distinct from each other and from
`test_refusal_unwinds.py`'s own pre-existing mutation anchor on the loop's
generic-refusal unwind.

**Not fixed here, and named as a follow-up rather than guessed at:** whether the
walk should prefer a NUDGE (moving off the current slot without assuming a
direction) over dead-reckoning when the CURRENT slot is itself the occluded one,
rather than only using the nudge as a last resort at the top of a fresh
`_walk_cursor_to` call. The live log's own successful retry the next poll used
exactly that nudge path ("nudging off the blind slot ... recovered on slot 0
after 1 nudge(s)"), which is markedly cheaper and safer than dead-reckoning
across the same slot and falling into a 2-attempt blind probe. Changing WHEN the
nudge is preferred touches `_walk_cursor_to`'s core decision tree (interacts with
I-32's dead-reckon bound and I-33's blind-confirmation retry, both of which are
mutation-tested against specific press counts) -- a bigger change than one branch,
and it changes the $50 play path, so it is not made unilaterally here.

**Verify.** `tests/minigame/test_tactics_select_fallback.py`: `OccludedPlayScreen`
(models an occluded slot between two targets, a one-shot dropped navigation press,
and a count-based "sabotage" hook -- the Nth `select_card` press system-wide costs
an earlier target's lift instead of doing its normal thing -- deliberately
mechanism-agnostic, matching the skeptic's own finding that the exact press parity
is not recoverable, and general enough to model BOTH shapes by choosing which
press it lands on). Cases I/J: the original I-48 shape (recovered / double
failure). K: control, both land, nothing fires. L/M (new, the sibling shape): the
tactics target's own walk and select both succeed with no occlusion and no I-48
branch at all, its own `_select_verified` retry costs the batter, and the SHARED
re-check recovers it (L) or, with the retry also blocked, refuses cleanly (M).

Nine mutants total in the file now (4 pre-existing + 5 for this ticket),
`__pycache__` cleared and sha256-verified restored around each:

    mutant 5: reorder the loop to (tactics_index, card_index)
        -> case I no longer succeeds (the _batter_verified gate still refuses
           the fallback outright rather than silently proceeding)
    mutant 6 (skeptic M1b): the shared re-check reuses a stale, fabricated
        "everything is still lifted" belief instead of a fresh look
        -> case I no longer honestly recovers the batter
    mutant 7 (skeptic M2): a missing target's retry is unbounded instead of
        running once -> case J (a genuine double failure) sends far more
        select_card presses than the shipped single retry
    mutant 8 (skeptic M3): the double-failure unwind passes ours=set() instead
        of the real target set -> the unwind spy no longer sees {0, 2}
    mutant 9 (skeptic M4): the retry drops _walk_cursor_to and presses
        select_card wherever the cursor already is -> case I refuses instead
        of recovering (the skeptic's own M4 survived their narrower scenario --
        cursor already on the target -- and is caught here by the occluded one)

All nine caught; both `input_controller.py` and `orchestrator.py` restored
byte-for-byte (sha256-verified) after every mutant. Also green:
`test_refusal_unwinds.py`, `test_verified_selection.py`,
`test_commit_refuses_unseen_strays.py`, `test_inference_needs_baseline_read.py`,
`test_i22_pitch_boost_slot3.py`, `test_walk_crosses_occluded_slot.py`,
`tests/harness/test_no_undefined_names.py`, `test_no_shadowed_module_defs.py`,
`tests/rig/test_no_real_input_under_test_run.py`.

**Status.** merged 0748b80; Opus skeptic CONFIRMED WITH NOTES, mechanism PROVEN
(probe2.py R1); N1 applied 2bad7ab (shared re-verify covers the sibling shape
j.log:620 / o.log:1040); 9/9 mutants.

**REGRESSION TRIAGE, 2026-09-21 (offline, HEAD 3df988b).**
`tests/minigame/test_lifted_discard_row_rescued.py` FAILS at HEAD
(`IndexError: pop from empty list`, its case (5) queue exhausted at
`test_lifted_discard_row_rescued.py:346`) because the shared re-check
(`input_controller.py:2182-2194`) takes at least one MORE `_look_settled`
call before `_clear_strays` than case (5)'s 4-frame script budgeted for. Not
just a script-length problem: extending the queue (repeating the commit-glitch
frame) shows `ok5` still ends False, matching the test's own assertion, but
`_walk_cursor_to`'s blind-nudge loop now fires 8 real `move_left` presses
before giving up — falsifying case (5)'s own `check(_presses5 == [], ...)`
at `test_lifted_discard_row_rescued.py:364`, whose comment says a press there
"would itself be evidence the threading test is not isolating what it
claims to." The shared re-check at :2182-2194 retries via `_walk_cursor_to`
unconditionally (no `kinds0`/`_baseline_not_tactics` gate, unlike
`_clear_strays`'s own inference logic a few lines below it), so a genuine,
untouched tactics card whose banner merely glitches at commit time now costs
real navigation presses it never cost before I-48b, even though the shipped
mutant 9 (skeptic M4, above) already pins `_walk_cursor_to` being called here
as intended behaviour. Per this triage's own decision rule this is case (b)
(an extra press, not a script-length fix), so the test was left UNCHANGED
rather than loosening its zero-press assertion; reproduction script at
`agent_progress/issues/I-48b/probe_i48b_case5_extra_presses.py` (not
committed here — offline scratch only). Needs a human call: either give the
shared re-check the same `kinds0` gate `_clear_strays` uses before it presses,
or accept the extra presses and update case (5)'s invariant deliberately.

### I-48d  An invisible (chronically occluded) stray can still be committed through the I-26/I-28 exemption    P2  play

**Evidence.** Skeptic review of I-48b (`agent_progress/issues/I-48b/skeptic.md`
section 2, `probe2.py` R4), pre-existing and NOT introduced by I-48b/I-48c. The
I-02 probe (`_probe_select_blind_target`, unchanged by this ticket) presses
`select_card` blind while hunting for a target it lost the cursor near. If that
press lands on a THIRD slot that is chronically occluded (its `ys` was never
readable, so `selected_cards` abstains on it regardless of whether it is really
lifted), the probe's own toggle is invisible to every reader downstream:
`_clear_strays`'s I-26/I-28 exemption waves an already-blind, non-`want` slot
through with "were ALREADY unreadable before this operation began — proceeding"
(`input_controller.py` ~:1803), because that exemption exists precisely for the
common, harmless case of a chronic occlusion nobody ever touched, and it has no
way to tell that apart from one the probe just silently raised.
`probe2.py` R4 drives this through the real code and confirm_play commits
`[1, 2]` -- a card the engine never chose, alongside the one it did.

**Root cause.** `_clear_strays`'s exemption for a slot blind at baseline answers
"was this slot readable before we touched anything", not "is this slot's
SELECTION STATE unchanged" -- and a chronically occluded slot can never answer
the second question either way, by construction (its `y` is never readable, so
`selected_cards` can never confirm it either lifted or not). The I-48b/I-48c fix
in this file does not worsen this (the skeptic's R6: the shared re-check's own
retry can fire a second probe, marginally raising exposure, but the exemption is
what admits the stray either way, with or without the re-check) and does not
close it either -- it is a pre-existing hole in a DIFFERENT function
(`_clear_strays`), not the target-verification logic I-48b/I-48c touches.

**Not fixed here.** It changes ban/select verification on the $50 play path and
the skeptic's own review explicitly declines to hold the I-48b/I-48c merge on it
("filing it is the right answer; blocking this merge on it is not"). A real fix
needs a way to distinguish "chronically occluded, never touched" from
"chronically occluded, and the probe just raised it" -- for example, tracking
which chronically-occluded slots a probe pressed `select_card` on during THIS
operation (the same shape `_MAYBE_LIFTED` already uses for a different case) and
excluding those from the I-26/I-28 exemption specifically. That is new state on
the money path and wants a live screen to check before it ships, not a
same-day follow-on to this ticket.

**Status.** OPEN, no fix here.
### I-48e  The I-48b shared re-check retried a tactics card on a single flickering read (8 phantom presses; test_lifted_discard_row_rescued case 5)  P1  play

**Evidence.** The I-48b regression triage note above (commit 0b15578) and its
repro `agent_progress/issues/I-48b/probe_i48b_case5_extra_presses.py` (main
checkout, offline scratch, not committed here): `tests/minigame/
test_lifted_discard_row_rescued.py` case (5) fails at HEAD with `IndexError: pop
from empty list` -- `input_controller.py`'s shared re-check block
(pre-fix ~:2182-2194) takes at least one MORE `_look_settled` call before
`_clear_strays` than the case's 4-frame script budgeted for, and extending the
queue shows why: `_walk_cursor_to`'s blind-nudge loop fires 8 real `move_left`
presses hunting a cursor that was never lost, for a target (a TACTICS card)
that had been correctly selected the whole operation.

**Root cause, traced against the real code (call-counting `look()` stub, not
committed).** Case (5) calls `_verified_select_and_play_inner(2, None, look)`,
so `want = {2}` and `_kinds0[2] == "tactics"` (the baseline, pre-press snapshot
already threaded into `_clear_strays` as `kinds0`). The pre-fix call sequence:
before_all(1) + the target loop's own walk(1) + select(1) = 3 calls, all
reading the SAME already-lifted baseline (slot 2 needs zero presses -- "already
selected" is a success, not a press). Call 4 is the shared re-check's OWN
preliminary look (`_g1, _ys1, n1, sel1 = _look_settled(look)`), which reads a
COMMIT-TIME GLITCH on slot 2's banner (`type=None`, the exact I-36 tactics-row
misread shape `ISSUES.md` already documents) -- its `y` nulls, `selected_cards`
skips it, so `_missing = {2}`. The retry loop then enters `_walk_cursor_to(2,
look)`, a 5th look, and the test's own 4-item queue has nothing left.

The test's own comment names the INTENDED architecture: 4 looks total --
"baseline, the walk's own look, the select's own look, and `_clear_strays`'s
commit-time look". In the pre-I-48b code (no shared re-check at all), that 4th
look was `_clear_strays`'s OWN internal `_look_settled`, which ALREADY handles
exactly this case correctly via its existing `_baseline_not_tactics`/
`_want_inferred` gate (this file ~:1893-1894, unchanged by this ticket): it
refuses to trust "readable at baseline, blind now" as proof of a lift for a
tactics-baseline target, requiring a genuine risen `sel` read instead, and
refuses the whole play when it doesn't see one. The shared re-check's own
preliminary look was pure REDUNDANT overhead for an all-tactics `want` --
answering a question `_clear_strays` was about to answer anyway, one look
later, with a stricter gate -- and the SECOND question ("is this really
missing, or just a flicker") was never asked at all before spending real
presses on it.

**Fix**, in the shared re-check block only (`input_controller.py`, the same
`_verified_select_and_play_inner` function I-48b/I-48c added). `_baseline_is_
tactics(k)` mirrors `_clear_strays`'s own `_baseline_not_tactics`, reading the
SAME `_kinds0` snapshot already threaded into `_clear_strays` below it (no new
capture). Two gates, matching the docstring:

    (a) target's BASELINE kind is a PLAYER card (disc-anchored, does not
        flicker this way) -> trust the first look, exactly as I-48b/I-48c
        shipped. UNCHANGED.
    (b) target's BASELINE kind is 'tactics' -> only trust a MISSING read once
        a SECOND settled look, taken after the same `SELECT_RETRY_CONFIRM_SEC`
        sleep the I-26 flicker re-look already uses inside `_clear_strays`
        (~:1813-1822), ALSO shows it missing. A target that reappears in `sel`
        on the re-look is a flicker (I-26), not a toggle, and is dropped from
        `_missing` with no press sent.

**When `want` has NO player-kind target at baseline, the whole block is
skipped -- no look is taken here at all**, and execution falls straight to
`_clear_strays`, whose own single fresh look (existing, untouched) answers the
question with its own, already-stricter gate. This is what restores case (5)
to exactly 4 total `look()` calls: before_all + walk + select + `_clear_
strays`'s own look, with `_clear_strays` itself producing the correct refusal
(`"the engine's cards [2] are not all lifted"`) -- the same shape the pre-I-48b
code produced, because for an all-tactics `want` a look here first can only
ever be a wasted, redundant read of the exact same question `_clear_strays` is
about to ask with a STRICTER gate, never a safer one.

**Verify.** `test_lifted_discard_row_rescued.py`: all 5 cases pass, case (5)
now `ok5=False`, `_presses5==[]`, `len(_queue5)==0` -- UNCHANGED, not edited.
`test_tactics_select_fallback.py`: cases A-M unchanged and still pass (every
pre-existing screen returns a plain `sel` list with no `.kinds`, so `_kinds0`
is `None` and the new gate is permissive there, matching the file's own stated
convention -- the preliminary look still always fires for them). Two new
cases, driven through the real `_verified_select_and_play_inner` with a new
`TacticsKindPlayScreen` (carries `.kinds`, mirroring `orchestrator._CursorSel`,
plus two call-numbered fault-injection knobs found by tracing a real run
once, the same method case (5)'s own queue uses):

    (N) card_index=0 ('player'), tactics_index=1 ('tactics'), both land
        cleanly. The shared re-check's own preliminary look (traced as call
        #9) reads slot 1 unlifted via a pure READ glitch (`hide_on_call`,
        `self.lifted` untouched) -- the confirmatory re-look (call #10, no
        glitch) reads it lifted again. Zero extra presses; `sent` matches the
        control case (B)'s exactly; both commit.
    (O) same setup, but a REAL drop (`drop_on_call`, mutates `self.lifted` for
        real at call #9) -- still missing on the confirmatory look #10 -- the
        EXISTING retry loop fires (`_walk_cursor_to` + `_select_verified`,
        exactly one extra `select_card` press) and recovers it; both commit.

9/9 pre-existing mutants in the file still caught; the file's own mutation
harness still passes end to end. Also green: `test_refusal_unwinds.py`,
`test_verified_selection.py`, `test_commit_refuses_unseen_strays.py`,
`test_inference_needs_baseline_read.py`, `test_walk_crosses_occluded_slot.py`,
`tests/harness/test_no_undefined_names.py`,
`tests/harness/test_no_shadowed_module_defs.py`,
`tests/rig/test_no_real_input_under_test_run.py`.

**Mutants for THIS ticket (`agent_progress/issues/I-48e/mutate_i48e.py`, not
committed), both caught, `input_controller.py` restored byte-for-byte
(sha256-verified) after each:**

    1. remove the gate entirely (revert to the pre-fix unconditional look)
       -> case (5) fails again (the extra look/press regression returns) AND
          case (N)/(O) fail (their log-text assertions no longer hold)
    2. gate on a single look (keep the all-tactics skip and the split, drop
       the confirmatory sleep+re-look, trust the first look as final)
       -> case (5) unaffected (no player-kind target, block still skipped for
          it) but case (N) fails -- a pure flicker now costs real presses,
          which is the discriminating case this fix exists for

**Status.** merged 99000b4; Sonnet skeptic CONFIRMED WITH NOTES (sibling shape
still covered: the dropped slot is always the batter; all-tactics want loses
one retry-before-refuse, deliberate).
### I-50  A dropped select_card press on the ban grid is never retried; 15 of 37 matches start a ban short  P1  money

**Evidence.** Census (`agent_progress/census/ban_shortfall/progress.md`, main
checkout) over 37 matches: 15 started with fewer than 3 bans (2/3 x10, 1/3 x5). All
20 missed targets are the same log line, `[ban] select_card at (r, c) placed no X
anywhere — leaving it` (`input_controller.py`, `select_bans_verified`, was ~:2554).
Re-ran the census's own grep to confirm before touching anything:
`grep -nE "verified [0-9]+/3 bans placed|WARNING: only [0-9]+ of 3 bans registered|..."
overnight/run_live_2026092*.log` -> 22x 3/3, 10x 2/3, 5x 1/3 (37 total, 15
shortfall), and `grep -c "placed no X anywhere" overnight/run_live_2026092*.log` ->
20 -- matches 10*1 + 5*2 exactly. Zero misses came from navigation, a blind cursor,
or a stale-frame desync; only the press-after-arrival was ever wrong.

**Root cause.** The verified navigator confirms the cursor is ON the target
(`here == want`), presses `select_card` ONCE (a bare `press()`, not
`press_verified`), diffs `banned_set()` before/after, finds no change, and moves on
WITHOUT RETRYING. CLAUDE.md §5 measured the console ignoring 15.2% of presses,
clustered -- a silently dropped press, exactly what `PRESS_VERIFY_TRIES` (5) already
covers for `confirm_play`/`start_match` on the same screen via `press_verified`
(~:3812). This was the one press on the ban path with no retry at all.

**Fix.** `input_controller.select_bans_verified`, and ONLY that function (another
branch is editing `_verified_select_and_play_inner` in the same file). The single
press is now a loop of up to `PRESS_VERIFY_TRIES` (reused, no new constant),
confined to the `banned_set`-diff branch the census implicates (the `confirm_ban`-
only fallback, with no `banned_set`, is untouched -- zero misses came from it).
Before every RETRY: re-`look()` and refuse to press again if the cursor has left
`want` (a drifted cursor is never guessed at -- test case E); then re-`banned_set()`
and, if `want` is now in it, accept as placed WITHOUT a further press (the selection
splash can make a LANDED press's X invisible on the very next look, and
`select_card` is a TOGGLE, so a blind retry there would un-ban it -- test case B).
The `_gone` (un-banned) and WRONG-CARD checks, and the `toggled` press count, are
unchanged. Exhausting all tries still logs "leaving it" and the run still moves on
to the next target (test case C).

**Verify.** `tests/minigame/test_ban_press_retried.py` (new): A (first press
dropped, second lands -> 3/3 placed, 2 presses/cell), B (splash: X appears only on
re-look -> 1 press, never toggled off), C (all tries dropped -> "leaving it",
exactly `PRESS_VERIFY_TRIES` presses, run continues to the next target), D (control:
everything lands first time, unchanged), E (cursor drifts after the dropped press ->
retry refuses to press blind). Also green, unaffected: every
`tests/minigame/test_*ban*.py` (16 files), `tests/rig/test_ban_nav_verified.py`,
`test_scan_stops_are_honest.py`, `test_ban_fallback_is_honest.py`,
`test_toggle_and_raise_leave_nothing.py`, `test_run_resume_and_persist.py`,
`tests/harness/test_no_undefined_names.py`, `test_no_shadowed_module_defs.py`,
`tests/rig/test_no_real_input_under_test_run.py`.

**Mutants (3, `__pycache__` cleared each time, sha256-verified restore):** no retry
at all (`range(1, PRESS_VERIFY_TRIES + 1)` -> `range(1, 1 + 1)`) caught by case A;
the splash re-check removed (cursor check kept) caught by case B (press count 5 not
1, placed stays empty); the cursor re-check removed (splash check kept) caught by
case E (3 presses not 1, and a wrong cell -- `(0, 1)` -- ends up banned instead of
nothing).

**Status.** merged 59bb0b7; Opus skeptic CONFIRMED WITH NOTES, round 2 d92e81d
added the settle before the re-check, cases B2/F/G, 7/7 mutants; expected
shortfall ~0.07 matches per 37 vs 15 observed. Merge agent found a surviving
mutant (the pre-press re-check accepting ANY new X instead of `want in
_recheck`, so an unrelated flicker reads as the target landing); case H pins
it, 8/8 mutants.

### I-51  The blind-target probe gives up after 2 presses; two clustered drops refuse a play on a healthy cursor   P1  play

**Evidence.** `agent_progress/census/blind_cursor_m4/progress.md` (cycle7 match4,
`refused_select_1790026023456048000`). `_walk_cursor_to` presses toward a target one
step away, reads back a blind cursor, and hands off to `_probe_select_blind_target`
(input_controller.py, ~:910) when the target's row IS readable to the lift reader --
that probe presses `select_card` up to `PROBE_SELECT_MAX` (2) times, looking for the
target to rise. Here it pressed twice, nothing lifted, and the play was REFUSED. The
kept post-refusal frame shows the cursor sitting correctly on the target the whole
time: slot 3, glow 26.9 (comfortably inside `cursor_slot`'s own measured true band
20.7 .. 36.1, well clear of `CUR_TRUSTED_GLOW_MIN`), digit 9 legible off a
disc-anchored y, nothing selected. Not CLAUDE.md 10.28-style occlusion (the disc is
fully legible) and not slot-4's structural glow ceiling (slot 3 reads fine). The
simplest account consistent with the evidence: two GENUINELY DROPPED `select_card`
presses on a cursor that was exactly where the walk expected it. The very next poll
re-decided the same play and committed it after one dropped `confirm_play` retry --
an ordinary press-drop, not a stuck slot.

**Root cause.** CLAUDE.md section 5 measured the console ignoring 15.20% of presses,
CLUSTERED (P(ignore | previous ignored) = 0.250, longest observed run 4) -- the exact
reasoning that already raised `PRESS_VERIFY_TRIES` from 3 to 5 (independent-assumption
tail 0.95% -> clustered-tail 0.059%) after it fired on a live $50 match at 2. The
probe's own budget was never re-derived alongside it: `PROBE_SELECT_MAX = 2` (one
retry) leaves a ~3.8% chance of two clustered drops in a row, which is exactly what
this event looks like. The user's bar is zero stalls, and a second constant on the
same money path, bounding retries against the same measured drop rate, drifted from
the first one that was already fixed for this reason.

**Fix.** `PROBE_SELECT_MAX` now ALIASES `PRESS_VERIFY_TRIES` (defined right after it,
since Python needs that name to exist first) instead of a separately-derived 2 -- both
bound retrying `select_card` against the same measured, clustered press-drop rate, so
they cannot drift apart again. The probe's existing safety is untouched and now stated
as an explicit invariant in its docstring: every iteration LOOKS before it decides
whether to press again, so a press whose lift only becomes visible on the very next
look is caught there -- an extra press after a landed one is impossible by
construction, not merely unlikely. `input_controller._LAST_PROBE_ATTEMPTS` now records
one entry (glow, ys, selected) per attempt, reset at the top of every probe call, so a
refusal's own evidence shows which attempts saw nothing instead of only the frame
grabbed after the fact. `orchestrator.record_refused_select` grew an optional `extra`
dict argument (default `None`, so every existing caller -- including
`tests/minigame/test_tactics_select_fallback.py`'s own mutation anchor on that
function's `json.dump` call -- is byte-for-byte unchanged) that merges into why.json
AFTER the base write, never inside it, specifically so it does not disturb that
anchor.

**Verify.** `tests/minigame/test_probe_select_budget.py` (new): (A) four clustered
drops then a landed 5th press -> success, exactly `PRESS_VERIFY_TRIES` (5) presses;
(B) the first press lands -> success, exactly 1 press, no double-toggle; (C) all 5
dropped -> refusal, `_LAST_PROBE_ATTEMPTS` carries 5 records in order, and
`record_refused_select(..., extra={"probe_attempts": ...})` persists them into
why.json while `extra=None` (every existing call site) writes no such key at all; (D)
a rise at the wrong slot after two drops is untouched -- explicit untoggle, walk
continues. Three mutants, `__pycache__` cleared and sha256-verified restore around
each:

    PROBE_SELECT_MAX reverted to a literal 2
        -> case A: refuses at 2 presses, never reaches the 5th
    an unconditional press before the loop's own first look
        -> case B: 2 presses sent instead of 1
    _LAST_PROBE_ATTEMPTS.append(...) dropped
        -> case C: 0 records instead of 5

All three caught. Also re-ran unaffected: `tests/rig/test_blind_slot_probe_select.py`
(updated to assert `PROBE_SELECT_MAX == PRESS_VERIFY_TRIES` rather than the literal
2), `tests/minigame/test_walk_crosses_occluded_slot.py` (same literal updated),
`tests/minigame/test_verified_selection.py`, `tests/minigame/
test_tactics_select_fallback.py` (its own mutant 3 on `record_refused_select` still
finds its anchor and still passes -- confirms the `extra` merge does not disturb it),
`tests/minigame/test_commit_refuses_unseen_strays.py`,
`tests/harness/test_no_undefined_names.py`,
`tests/harness/test_no_shadowed_module_defs.py`,
`tests/rig/test_no_real_input_under_test_run.py` -- all green.

**INDEPENDENT SKEPTIC ROUND 1: REFUTED, two blockers, both fixed
(`agent_progress/issues/I-51/skeptic.md`, `probe_toggle_parity.py`,
`probe_end_to_end.py`).**

**B1 (the real bug).** `select_card` is a TOGGLE and does NOT move the cursor, so
when the TRUE cursor sits on an ALREADY-SELECTED slot (I-48b: the batter selected
first, then dropped navigation presses toward the tactics target left the true
cursor sitting on the batter still), the probe's `select_queue=[None|slot]`
fixer's-own fake could not represent it, and every probe press TOGGLES the
already-selected batter -- the original code only ever checked `sel - before`
(a rise), never `before - sel` (a disappearance). Raising the budget 2 -> 5
changed the TOGGLE PARITY of an unrelated press storm without the probe ever
noticing: P(the already-selected batter left DOWN), CLAUDE.md sec5's clustered
chain -- **0.229 at budget 2, 0.707 at budget 3, 0.621 at budget 5** --
non-monotonic in the budget, so it was never a knob to nudge. End to end through
the real `_verified_select_and_play_inner` (I-48b's own shape), budget 2
COMMITTED the batter alone (I-48's fallback) and budget 5 was a FULL STALL --
I-51 was built to remove stalls and, unfixed, it added one. Safety was intact
throughout (`_clear_strays`' `want <= lifted` gate caught it every time -- cost
was a stall, never a wrong commit).

Fix: mirror the rise branch with a disappearance branch, inserted before the
rise check. `gone = [i for i in before if i not in sel]`; if `gone`, the true
cursor is (or was) on `gone[0]`, put back UP via `_select_verified` (not
`_deselect_verified` -- restoring a selection the probe's own press just
knocked down, not removing a stray one) and return, with NO further
select_card press. Re-run against the skeptic's own two scripts: `probe_end_to_end.py`
now returns True with confirm_play sent exactly once at BOTH budget 2 and 5 (was a
stall at 5); `probe_toggle_parity.py`'s exhaustive sweep (every drop pattern,
budgets 2 and 5) reads "restored" on every row, P(left DOWN) = 0.0000 at both
budgets, and the wrong-slot CONTROL is unharmed. New test cases (E) all-land,
(F) an odd landed-press count (1, 3 dropped), (G) end to end through
`_verified_select_and_play_inner` at both budgets.

**B2 (half the ticket was dead).** The sole production call site
(`orchestrator.py` ~:8472, inside `play_one_turn`) passed no `extra`, so
`input_controller._LAST_PROBE_ATTEMPTS` never reached a live why.json --
CLAUDE.md 10.1, a fix that produces output that looks like evidence and does
not. Fixed: `extra={"probe_attempts": input_controller._LAST_PROBE_ATTEMPTS}`,
module-qualified (not `from ... import`) because the probe REBINDS that name
every call. New test case (H) drives the REAL `play_one_turn` with
`select_and_play` stubbed to refuse and confirms the real call site's why.json
carries the seeded sentinel.

**Non-blocking, fixed while here (Q3):** the `extra` merge used to
`open(path, "w")` (truncating) and then `json.dump` straight into it -- an
unserialisable `extra` would destroy the good base record the merge was
supposed to enrich. Now serialises to a string first (`json.dumps(..., default=str)`)
and only writes the file once that succeeds; `default=str` also means most
unserialisable values degrade to a string instead of raising at all.

**Mutants, round 2 (4 new, 7 total in `test_probe_select_budget.py`):**

    (M1, the skeptic's own, re-run) `if target in new:` -> `if new:`
        -> case D: a wrong-slot rise is misattributed to the target
    the whole B1 disappearance branch deleted
        -> case E: the already-selected batter ends up lost, not re-lifted
    press-and-return WITHOUT verifying, after detecting a disappearance
        -> case F: a corrective press that itself gets dropped is reported
           as success with the batter still down (an earlier attempt --
           an extra press placed just BEFORE the existing, still-verifying
           `_select_verified` call -- was an EQUIVALENT mutant: that helper
           already checks state before pressing, so a redundant press one
           line earlier does exactly what its own first internal attempt
           would have done; not counted)
    orchestrator.py's call site drops extra=
        -> case H: probe_attempts never reaches why.json

All four caught; the original three (budget reverted, press-before-look,
attempt-log dropped) still caught after the B1/B2 edits; both files restored
byte-for-byte (sha256-verified). Full regression re-run, all green:
`test_probe_select_budget.py`, `test_blind_slot_probe_select.py`,
`test_verified_selection.py`, `test_tactics_select_fallback.py`,
`test_commit_refuses_unseen_strays.py`, `test_no_undefined_names.py`,
`test_no_shadowed_module_defs.py`, `test_no_real_input_under_test_run.py`,
`test_walk_crosses_occluded_slot.py`.

**INDEPENDENT SKEPTIC ROUND 2: CONFIRMED WITH NOTES.** One ordering risk
flagged, N-2: the row-count guard (`if n != MAX_HAND_SIZE`) and the B1 `gone`
computation are two separate statements, and nothing pinned which one has to
run first. If `gone = [i for i in before if i not in sel]` ran BEFORE the
row-count guard, a GARBLED post-press frame -- `_look_settled`'s own bad-read
sentinel, n=0 and `sel` EMPTIED -- would be read as a disappearance: with an
already-selected slot in `before` (I-48b's own batter), `gone` would equal
that slot and `_select_verified` would fire on a frame nobody could read, not
a real toggle-down. Pinned as case I in `test_probe_select_budget.py`
(`GarbledScreen`, every look() unreadable, `before=[2]`): refuses,
`_select_verified` is never called. Mutant 8 swaps the two statements'
order and case I catches it (`_select_verified` fires on the unreadable
frame); both files restored byte-for-byte (sha256-verified) after. The
shipped order already had the guard first -- N-2 pins that it stays first,
it does not change production code.

**Status.** merged af9a5bb; Opus skeptic round 1 REFUTED (parity), round 2
CONFIRMED WITH NOTES; N-2 ordering pinned as case I.

### I-53  A cursor lost right after dead-reckoning across an occluded slot is refused instead of nudged    P1  input

**Evidence.** Census over every `overnight/run_live_2026092*.log` in the main checkout
(25 files), counting `[cursor] lost the cursor after N press(es)`:

    file                     events  dead-reckon adjacent?   resolution
    run_live_20260921d.log     3     no -- glow never clears  play REFUSED, retried
                                      CURSOR_GLOW_MIN anywhere next poll on the same
                                      (no "occluded"/            hand_index, refused
                                      "dead-reckoning" line       again, excluded after
                                      anywhere in the log)         3x running
    run_live_20260921f.log     1     no -- I-33's cross-call     _unwind_selection put
                                      blind cursor (a SEPARATE     the stray back down,
                                      earlier call left slot 4     re-verified on 4 with
                                      selected; THIS call's        1 press on the retry
                                      own top-of-function read
                                      never dead-reckoned)
    run_live_20260921t.log     1     YES -- "slot 1 is           I-48's fallback fired:
                                      occluded ... dead-           "tactics slot 3 could
                                      reckoning" printed twice     not be verified --
                                      immediately before it        dropping the boost and
                                                                    playing the batter
                                                                    alone" (a real swing_
                                                                    boost/speed_boost was
                                                                    silently never played)

Only ONE of the five (`run_live_20260921t.log`, the case this ticket was opened
against) is the I-32/I-53 shape at all -- the other four are different failure
modes (a totally-blind fan across the whole gate, and I-33's cross-call belief
loss) that this fix does not and should not touch, confirmed by re-running the
full suite unchanged after the fix (§ Verify).

**Root cause, traced in the code (not guessed).** `_walk_cursor_to`'s dead-reckon
branch (I-32) assigns `cur` the crossed slot's `expected` value with NO read at all
-- by design, since the slot's `ys[i] is None` means the glow reader cannot answer
either way. The NEXT press's own `cur_confirmed_blind` (I-33's "was this position
actually trusted" flag) is deliberately left UNCHANGED by the dead-reckon branch
(its own comment: "NOT cur_confirmed_blind = True"), so whether the following lost
read gets I-33's one-retry depends entirely on what `cur_confirmed_blind` happened
to be BEFORE the crossing, not on the fact that a guess was just made. In the
run_live_20260921t.log trace, that flag was carried over from a prior call's
top-of-function lift-fallback (`_cur_from_lift`), so ONE extra retry did fire and
still failed (three presses total) -- but nothing in the code special-cases "the
position we just moved away from was never itself confirmed", so a run where the
prior belief happened to be trusted (the common case) gets ZERO retries after a
dead-reckon and refuses on the very next lost read.

**Fix**, `input_controller._walk_cursor_to` only. A new branch, keyed on
`was_dead_reckoned` (already computed every iteration for I-32's own one-guess
cap; unused elsewhere), fires when a lost read immediately follows a dead-reckoned
crossing -- REGARDLESS of `cur_confirmed_blind`, since a guessed position was never
read at all and so was never "trusted" in I-33's sense either. It presses again (a
real move, never a second guess -- `select_card` is the only toggle) and re-looks,
up to `PRESS_VERIFY_TRIES` (5, reused, nothing invented) times, breaking as soon as
a real read names a slot. If that slot is not yet `target`, `continue` hands
control back to the ordinary outer `while cur != target:` loop, which already
presses toward `target` from wherever `cur` is -- including PAST it, in which case
the very next iteration's existing direction check (`move_right if cur < target
else move_left`) walks back with no special-cased code. Only if every extra press
also fails to read does the branch fall through to the original "lost the cursor
... refusing" line.

Placed BEFORE I-33's own `prev_blind` branch in the same `if cur is None:` chain,
so the two interact cleanly: when both conditions are true (as in the reproduction
above), I-53's branch runs first and its own bounded loop supersedes I-33's single
retry rather than stacking with it; I-33's branch is now only ever reached when
`was_dead_reckoned` is False, so it keeps its ORIGINAL behaviour unchanged for
every loss that did not follow a dead-reckon (test (D)/CONTROL pins this: exact
same press count as before the fix). I-32's own one-consecutive-dead-reckon cap
(`not was_dead_reckoned` in the dead-reckon condition) and the "never dead-reckon
onto the target" rule (I-02's probe-select path, case (3)) are both untouched --
I-53 cannot chain a SECOND guess, because it never guesses; it only chains real
presses-and-reads or runs out of budget.

One side effect, understood and accepted rather than incidental: two OCCLUDED
slots back to back (the file's old case (2b), "no code chains guesses to cover
it") now also RECOVERS instead of hard-refusing, because pressing past a second
occluded slot for real and reading the slot after it is not a guess -- it is
exactly what I-53 is for. The one-guess cap that motivated the old refusal is
about never ASSUMING a second position with no read; it says nothing about
retrying with real presses, which this never was and still isn't.

**Verify.** `tests/minigame/test_walk_crosses_occluded_slot.py`, rewritten to keep
the I-32 cases (1)/(3)/(5)/(6) and fold the two behaviour-changing ones into the
new I-53 family below them: (A) the dead-reckon press itself was dropped, so the
real cursor is still ON the occluded slot when the next look fails -- one extra
move finds a readable slot and the walk arrives; (B) every extra move is also
dropped -- refuses, same as an unrecoverable loss always has, after the full
`PRESS_VERIFY_TRIES` budget; (C) the retry runs past a slot whose own read
momentarily misses (including the target itself) and lands past it -- the ordinary
per-step direction logic (nothing special-cased for this) walks it back and
arrives; (D) CONTROL, no occlusion anywhere -- a lost cursor is refused with the
EXACT press count it always had, proving the retry never fires without a
dead-reckon behind it. Also green, unchanged: `test_verified_selection.py`,
`test_tactics_select_fallback.py` (whose own mutation harness mutates and restores
`input_controller.py` -- confirms the new branch coexists with I-48's fallback),
`test_commit_refuses_unseen_strays.py`, `tests/harness/test_no_undefined_names.py`,
`test_no_shadowed_module_defs.py`, `tests/rig/test_no_real_input_under_test_run.py`.

**Mutants (3, `__pycache__` cleared before/after each, sha256-verified restore to
`f4dbfd8de773ac8d21c06944399b84f55e8a958ca51065398c4975735b161431`):**

    drop the extra-move branch (`if was_dead_reckoned:` -> `if False:`)
        -> test_walk_crosses_occluded_slot.py: (A)/(B)/(C) all FAIL (11 checks)
    widen the retry bound (`PRESS_VERIFY_TRIES + 1` -> `PRESS_VERIFY_TRIES + 50`)
        -> test_walk_crosses_occluded_slot.py: (B) FAILS (press count, refusal line)
    skip the walk-back (`continue` -> `return True, sel` on a found-but-unconfirmed cur)
        -> test_walk_crosses_occluded_slot.py: (A)/(C) FAIL (press counts, wrong "arrived")

**Status.** merged 39f160a; Sonnet skeptic CONFIRMED (moves only, bounded at
PRESS_VERIFY_TRIES, I-33/nudge cannot double-fire, worst observed 7 presses).

### I-52  confirm_discard is verified once, immediately, and a late-landing discard leaves its slot in _MAYBE_LIFTED (three false I-43 refusals)   P1  input/loop

**Evidence.** `overnight/run_live_20260921t.log` ~386-420 (main checkout). Decision
"discarding the weakest (power 4)" at slot 0; `[discard] confirm_discard did not
register — discards_left is still 2. REFUSING to press confirm_play...`; `discard
NOT CONFIRMED — it may or may not have been thrown. Re-reading the hand next poll`.
A SECOND, separate discard Decision was logged at line 392, still reading the
stale count, whose own press landed SILENTLY (`_walk_cursor_to`'s print is gated
`if steps:`, and the cursor needed no move, so nothing logged it); discards_left
fell one poll later. Slot 0 then stayed in `_MAYBE_LIFTED` (its replacement's
position unreadable/animating), and THREE plays were refused by the I-43 guard
("slot(s) [0] may still be physically lifted...") before hand_index 1 was
excluded and a worse card (batter 3) committed. Cost ~75s and a worse card.
Frames: `diagnostics/deal_frames/dropped_1790029230537281000/`,
`refused_select_1790029233140573000/`, `_1790029235068215000/`,
`_1790029236869044000/`.

**REFUTED ONCE, REVISED.** An independent skeptic reviewed the first version of
this fix (`agent_progress/issues/I-52/skeptic.md`) and refuted two of its three
claims: the evidence table's own numbers disagreed with the prose quoting them
(19/7 vs a claimed 21/5), and no row's "landed late" classification is actually
attributable to the REFUSED press proving anything about timing -- every such row
has a second, separate discard attempt that landed silently in between. Separately,
a second false-I-43 fix (an adjacency exemption in `_reconcile_maybe_lifted`) was
refuted outright: it cleared the STRONGEST mark this system ever makes, on no
discriminating measurement, and widened a different open ticket (I-48d). Both are
corrected below; the skeptic's own "cheapest route to CONFIRMED" is followed for
the numbers and `press_verified`/`_prove_maybe_lifted_clean` is kept unchanged
(CONFIRMED outright, probes 1a-1d), and the adjacency rule is replaced with a
bounded, evidence-producing disambiguation rather than simply dropped.

**The 26-row table, corrected.** Full detail, method and the two independent
classifications in `agent_progress/issues/I-52/discard_table.txt`.

```
 #  file                            line before  after     status  play@  I-43@
 1  run_live_20260920i.log           95      1      0       LATE    100   -
 2  run_live_20260921b.log           42      1      0       LATE     50   -
 3  run_live_20260921e.log          134      2      1       LATE    139   -
 4  run_live_20260921j.log          450      2      2    DROPPED    455   -
 5  run_live_20260921j.log          608      1      1    DROPPED    619   -
 6  run_live_20260921j.log          612      1      1    DROPPED    619   -
 7  run_live_20260921j.log          616      1      1    DROPPED    619   -
 8  run_live_20260921j.log          802      2      0       LATE    810   -
 9  run_live_20260921n.log           84      1      0       LATE     89   -
10  run_live_20260921n.log          485      1      1    DROPPED    506   -
11  run_live_20260921n.log          493      1      1    DROPPED    506   -
12  run_live_20260921n.log          501      1      1    DROPPED    506   -
13  run_live_20260921o.log          721      2      0       LATE    733   -
14  run_live_20260921o.log          728      1      0       LATE    733   -
15  run_live_20260921p.log          237      1      0       LATE    242   -
16  run_live_20260921p.log          406      1      0       LATE    411   -
17  run_live_20260921p.log          540      2      0       LATE    548   -
18  run_live_20260921p.log          612      1      0       LATE    617   -
19  run_live_20260921q.log          565      2      0       LATE    577   -
20  run_live_20260921q.log          838      2      1       LATE    845   -
21  run_live_20260921r.log          294      2      1       LATE    299   -
22  run_live_20260921r.log          434      2      0       LATE    441   -
23  run_live_20260921s.log          236      2      1       LATE    241   -
24  run_live_20260921s.log          283      1      0       LATE    288   -
25  run_live_20260921s.log          499      1      0       LATE    504   -
26  run_live_20260921t.log          390      2      1       LATE    397   399
```

**19 LATE / 7 DROPPED / 26** (rows 4-7, 10-12 are the DROPPED ones). "LATE" means
this discard EVENTUALLY landed, via a later attempt, before play committed -- NOT
that the original refused press was merely slow to register; the skeptic traced
two rows by hand (t.log 390-396, o.log 721-732) and found a second, silent, SEPARATE
discard attempt in both. 1 of 19 LATE rows was followed by an `(I-43)` refusal
(#26); the other 18 never hit I-43 because the redealt slot happened to read cleanly
on the next commit attempt.

A second, orthogonal classification: did confirm_discard get PRESSED at all for
this occurrence? **21 of 26 rows pressed confirm_discard** (and the counter simply
did not move on THAT poll) -- exactly what `press_verified`'s retry now recovers
WITHIN one call. **5 of 26 rows never reached confirm_discard** -- the cursor/select
step refused first (#2, #3, #10, #11, #12) -- and `press_verified` on the
confirm_discard press cannot help these; of the 5, two (#2, #3) still resolved LATE
via a later attempt and three (#10-#12) are DROPPED.

**A second, independent false-refusal shape**, found while counting I-43 true
positives (see below): a card legitimately lifted for a PLAY commit (not a
discard) occludes its UNSELECTED neighbour's own disc/badge read, so the
neighbour reads unreadable and the commit guard's `_new_blind` path (in
`_verified_select_and_play_inner`, out of this ticket's scope) marks it as a
stray. `run_live_20260921t.log` ~906-996: hand [swing+1, speed+1, 4/3, 4/3, 8/1],
slot 0 (tactics) and slot 4 (the 8, the play target) legitimately selected, slot 1
(speed, untouched) reads unreadable purely from sitting beside slot 0 -- marked,
refused for 8 STRAIGHT POLLS, excluding hand_index 4 -- the best card in the hand
-- from every attempt (`diagnostics/deal_frames/refused_select_1790029942849538000/`,
`why.json`: `{"target": 4, "already_selected": [0, 4]}`).

**I-43 true-positive count, today's logs (`run_live_20260921[rst].log`, the three
files after the I-43 merge `2f18a734`, 2026-09-21 13:31:34 — verified by the epoch
in each file's own frame-directory names, 13:53/17:10/18:20).** All 11 `(I-43)`
refusals in these three files are in `t.log`: 3 at lines 399/406/413 (the discard
shape, row 26 above) and 8 at lines 922-996 (the neighbour-occlusion shape).
**0 of 11 are true positives.**

**Root cause, two parts.**

1. `select_and_discard`'s confirm_discard was pressed exactly ONCE and then only
   POLLED the counter for reads (`input_controller.py`, pre-fix) — unlike every
   other commit press (I-11's `press_verified`), a press the console dropped
   (CLAUDE.md section 5: ~1 in 6, and they cluster) could only ever be REPORTED,
   never retried within the same call. Recovery instead depended on the caller
   (`orchestrator.play_one_turn`) looping back on the NEXT poll and re-running the
   whole select-and-discard sequence from scratch — ~15-20s per cycle.
2. `_reconcile_maybe_lifted(ys, sel)` only ever cleared a tracked slot on a real,
   readable `y` that was not currently selected ("seen down"). A slot whose true
   state was proven a DIFFERENT way — discards_left measurably falling, or a
   neighbour's lift explaining its own unreadability — had no path to clearing, so
   it stayed marked until its OWN position happened to read cleanly, however many
   polls that took.

**Fix**, confined to `input_controller.py`'s `select_and_discard` and the
`_MAYBE_LIFTED`/`_reconcile_maybe_lifted` helpers (no other function touched):

1. `select_and_discard` verifies confirm_discard with `press_verified`, the SAME
   helper I-11 uses for `confirm_play`/`close_result`/`start_match` — no new
   constants, `tries`/`settle` are its own defaults (`PRESS_VERIFY_TRIES`,
   `PRESS_VERIFY_SETTLE`). Its `observe()` (`_discard_landed`) answers with the NEW
   count the moment discards_left measurably falls (decisive proof, however the
   replacement currently reads) and otherwise with the unchanged baseline —
   UNLESS a fresh read shows card_index is no longer lifted while the count is
   still unchanged, which is answered with None, press_verified's own signal to
   STOP rather than press again (the guard against a second confirm_discard with
   nothing selected -- RULES.md and the code were checked, and confirm_discard,
   like confirm_play, commits whatever is CURRENTLY selected; nothing in this
   codebase exercises a bare confirm_discard with nothing selected, so its effect
   is untested and the fix simply never sends one). The first `observe()` call
   answers `before` directly rather than re-deriving it, so a caller whose counter
   never answers on any later poll still gets its one owed press
   (`tests/minigame/test_commit_refuses_unseen_strays.py`'s M3). A raising
   `_look_settled` inside the verification is now caught and converted to the
   SAME safe UNVERIFIED outcome, matching `select_bans_verified`'s identical
   lesson about an exception leaving the screen mid-change.
2. `_reconcile_maybe_lifted` is back to EXACTLY its original "seen down" rule (see
   below) — CONFIRMED unchanged by the skeptic. A landed discard clears its OWN
   slot directly the moment discards_left proves it (`_prove_maybe_lifted_clean`),
   a THIRD, independent signal `_reconcile_maybe_lifted` cannot express at all
   (it only ever sees `(ys, sel)`).
3. `resolve_neighbour_occlusion(m_slot, t_slot, look)`, NEW: the replacement for
   the refuted adjacency rule. Bounded (one lower, one look, at most one
   re-raise, no loop) and presses nothing blind -- it only presses `select_card`
   on `t_slot`, a card whose CURRENT state is already known, through the same
   verified toggle (`_deselect_verified`/`_select_verified`) every other
   put-down/pick-up in this file uses:

       lower t_slot, then look
       m_slot now READS               -> t_slot's lift explains it, PROVEN not
                                         guessed. Clear the mark, re-raise
                                         t_slot, hand back to the ordinary
                                         commit path.
       m_slot STILL blind, t_slot down -> genuine stray. t_slot stays down,
                                         m_slot's mark SURVIVES, the existing
                                         refusal/unwind path handles it with
                                         a positive finding instead of a guess.
       the re-raise of t_slot fails    -> refuse. t_slot left down, nothing
                                         partially lifted.

   **NOW WIRED IN (third pass).** The first wiring pass left this function
   built and tested but uncalled — CLAUDE.md 10.1's own shape, "the code did
   nothing, and doing nothing looked exactly like working" — so the live
   deadlock it was built to fix (`run 21t` match 3: `may still be physically
   lifted` x8, every batter excluded) was exactly as reachable as before.
   `_clear_strays`'s own `_unproven` branch (`input_controller.py:1970`, the
   I-43 refusal site every commit — play and discard alike — passes through)
   now calls it: on `_m` in `_unproven` beside a `_t` in `sel`, call
   `resolve_neighbour_occlusion(_m, _t, look)`; on ANY attempt, re-observe
   the fan before re-checking `_unproven`/`want <= lifted` (a failed re-raise
   leaves `_t` down, and only a FRESH look, not the stale one this block
   started with, lets the downstream `want <= lifted` floor catch it — see
   the second mutant below). See cases H/I.

**What the adjacency rule got wrong, in the skeptic's own words.** It cleared the
mark at `run_live_20260921t.log:912` ("slot(s) [1] read unreadable... something we
pressed lifted them") -- the `_new_blind` branch, which fires ONLY when a slot was
READABLE at the operation's baseline and went blind AFTER our own press: I-21's own
stated lift signature, the STRONGEST evidence this system makes, not a coincidence.
The rule had no measurement separating "explained by a neighbour" from "we lifted
it" -- both explanations fit the one frame available
(`refused_select_1790029942849538000`, where slot 1's `y` comes from `fallback`,
so `selected_cards` has no rise to measure either way) -- and it widened
`ISSUES.md` I-48d (OPEN), whose own proposed remedy is `_MAYBE_LIFTED` tracking a
probed slot so it can be EXCLUDED from exactly this kind of exemption; the
adjacency rule did the opposite for every marked slot beside any current
selection.

**FOURTH PASS (skeptic round 2, `agent_progress/issues/I-52/skeptic.md`):
CONFIRMED WITH NOTES, three defects, all fixed on this branch.**

1. **N1 — `resolve_neighbour_occlusion` never walked the cursor to `t_slot`.**
   Every other toggle pair in this file walks first
   (`_walk_cursor_to`/`_select_verified`/`_deselect_verified` at
   2071/2073, 2218/2220, 2315/2317); this one pressed `select_card` on
   whatever the cursor already held. The play path selects the BATTER
   first, leaving the cursor on the TACTICS slot, so a marked slot
   adjacent to the batter hit the wrong card — measured live: 5 select
   presses landed on slot 4 while `t_slot` was 1, the tactics target went
   down, and the deadlock stayed intact. Fixed: `_walk_cursor_to(t_slot,
   look)` before the lower AND again before the re-raise; a walk failure
   returns "unresolved" with zero further presses.
2. **N2 — the occlusion-proven check tested `_ys[m_slot] is None` but never
   `m_slot not in sel`.** A genuinely LIFTED m_slot that happens to read
   once t_slot comes down was being cleared as "occlusion" and committed —
   a card the engine never chose. Fixed: `if _ys[m_slot] is None or
   m_slot in sel:` — occlusion is proven only when m_slot reads AT REST.
3. **N3 — the mark was cleared BEFORE the re-raise was attempted.** A
   failed re-raise still discarded a proof that was genuinely obtained,
   throwing the finding away on a press that never landed. Moved
   `_MAYBE_LIFTED.discard(m_slot)` to after a confirmed re-raise.

Also fixed: the skeptic's **M6** — a mutant deleting the resolver's
`t_slot not in sel` precondition (line 1627) survived every prior case,
because a later "still blind" refusal reaches the same verdict with or
without it whenever M_SLOT is genuinely blind. It bites only when T is
resting AND M is misread blind on ONE look and readable on the next (I-26's
own flicker) — a shape the earlier cases never built. New case (F6) does.

**Verify.** `tests/minigame/test_discard_confirm_verified.py`: (A) a dropped press
a retry lands — 2 presses, ok=True, the (pre-marked) slot cleared; (B) the press
lands but the count reads one poll late — exactly 1 press, no second
confirm_discard, ok=False (UNVERIFIED), and the mark clears on the NEXT poll's
ordinary "seen down" read with no new machinery; (C) every retry dropped — retries
up to `PRESS_VERIFY_TRIES`, ok=False, the mark SURVIVES a next-poll check that is
still unresolved; (D) `_prove_maybe_lifted_clean` clears a mark directly, and a
landed discard's own success path uses it on a PRE-MARKED slot; (E) I-26/I-28
control: reconciliation never MARKS an untracked slot, only ever clears one;
(F2) `resolve_neighbour_occlusion`, occlusion-by-lift: M reads once T is lowered —
ok=True, mark cleared, T re-raised, exactly 2 presses; (F3) real stray: M still
blind with T down — ok=False, mark SURVIVES, T left down, exactly 1 press (bounded,
no loop chasing a stray); (F4) the re-raise of T itself fails — ok=False, T left
down, exactly 6 presses (1 lower + `SELECT_ATTEMPTS` failed re-raises), **and
(fourth pass) M's mark SURVIVES the failed re-raise (N3)**; (G) I-43
true-positive control: an isolated marked slot survives, including with an
unrelated NON-adjacent selection elsewhere in the hand. (H)/(I) — end to end
through the REAL `_verified_select_and_play_inner`, not a stub of it,
replaying the exact match-3 shape `resolve_neighbour_occlusion`'s own
docstring names (hand [swing+1, speed+1, 4/3, 4/3, 8/1], card_index=4,
tactics_index=0, slot 1 unreadable from the operation's own baseline —
routing the mark through `_untouched_blind`/`_unproven`, the branch this pass
wires up, rather than the separate `_new_blind` re-look branch): (H) COMMIT —
slot 0 already lifted at baseline (occlusion tied to its own lift), the play
lowers it, sees slot 1 read, clears the mark, re-raises slot 0, and presses
confirm_play exactly once, 3 `select_card` presses total (raise 4, lower 0,
re-raise 0 — tactics 0 was already up, so no press to raise it); (I) the
REFUSE mirror — slot 1 stays blind no matter what (a genuine stray) — the play
REFUSES, confirm_play is never sent, slot 1's mark SURVIVES, and slot 0 is
left DOWN by the failed disambiguation. **New (fourth pass): (F1) — the cursor
starts on a THIRD slot (`CURSOR_START`, standing in for a tactics slot the
batter-first play path leaves it on), t_slot IS the batter — ok=True, the
cursor ends on t_slot not CURSOR_START, CURSOR_START is never toggled, exactly
3 `move_left` presses (one walk; the second, before the re-raise, is already
there) and 2 `select_card` presses. (F5) — M reads once T is down but M is
ITSELF lifted (`m_lifted=True`) — ok=False, "genuine stray", M's mark
SURVIVES, T left down, M stays lifted throughout (this function never
touches it), exactly 1 `select_card` press. (F6) — T is NOT lifted and M is
misread blind on the FIRST look only, readable after (`flicker_m_blind_once`)
— ok=False, ZERO presses of any kind, mark survives; a T-resting case with M
genuinely (not transiently) blind was tried first and could NOT distinguish
the M6 mutant, because the later "still blind" refusal reaches the same
verdict either way — only the flicker shape reaches the top guard's own
`t_slot not in sel` clause.** `def check(name, cond)`, name-first.

**Mutants (16 total, `__pycache__` cleared and sha256-verified restored
between each, `4227122eb701e35cdb165707058e69dbe668075c669a97a364b499b6d234666f`):**

    force press_verified tries=1 (drop the retry)
        -> case A FAILS: only 1 press, never lands, ok=False
    drop the fresh-count/fan re-check inside _discard_landed (retry blind)
        -> case B FAILS: 2 presses sent, not 1 -- the guarded double-press happens
    drop _prove_maybe_lifted_clean from the landed branch
        -> cases A and D FAIL: a pre-marked slot stays marked despite a proven drop
    resolve_neighbour_occlusion: skip the lower (never press to check)
        -> case F2 FAILS: reports "genuine stray" without ever looking, mark
           survives, 0 presses sent
    resolve_neighbour_occlusion: treat "still blind" as clear
        -> case F3 FAILS: ok=True, mark wrongly cleared, T wrongly re-raised
    resolve_neighbour_occlusion: commit without re-verifying T (skip the re-raise
    check)
        -> case F4 FAILS: ok=True with T still down, only 1 press sent
    the skeptic's M1: press again when the slot un-lifted but the count is stale
    (drop the same ambiguity check as above, verified independently)
        -> case B FAILS: 5 presses sent, not 1
    the skeptic's M3: prove-clean on a count that did NOT fall (`<` -> `<=`)
        -> case B FAILS: 5 presses sent, not 1 (the ambiguous read is wrongly
           treated as a fall, so the retry never triggers)
    (third pass, the wiring) `_clear_strays`: `if _t in sel:` -> `if False:`,
    i.e. the call to resolve_neighbour_occlusion is never reached
        -> case H FAILS 4 ways (ok=False not True, 0 confirm_play presses not
           1, the mark survives instead of clearing, 2 select_card presses
           not 3); case I also catches it (slot 0 is never touched at all, so
           "T left down" reads {0, 4} instead of {4})
    (third pass) resolve_neighbour_occlusion: skip the re-raise, fake ok=True
    without calling _select_verified(t_slot, look)
        -> case H FAILS 4 ways: ok=False (refused downstream by the `want <=
           lifted` floor — "the engine's cards [0, 4] are not all lifted
           ([4])"), 2 confirm_play... 0 presses not 1, 8 select_card presses
           not 3, {4} not {0, 4} lifted. Case F4 also catches it (a
           pre-existing case that exercises the same call).
    the skeptic's M4: drop the fresh re-observe entirely after the resolver
    in _clear_strays (fall through with whatever _unproven was BEFORE the call)
        -> case H FAILS 2 ways: ok=False (the stale _unproven, computed
           before the mark was cleared, still names slot 1 and refuses),
           9 presses sent including a spurious extra select_card
    the skeptic's M5: call it occlusion even when M is STILL blind (drop the
    `_ys[m_slot] is None` half of the guard, keep only `m_slot in sel`)
        -> case F3 FAILS 4 ways (ok=True, mark wrongly cleared, T wrongly
           re-raised, 2 presses not 1) AND case I FAILS 4 ways end to end:
           the play COMMITS a card that should have refused, confirm_play
           IS sent, the mark is wrongly cleared, T ends up lifted
    (fourth pass) N1: skip the FIRST _walk_cursor_to call (fake ok=True, sel
    unchanged, cursor never moves off CURSOR_START)
        -> case F1 FAILS 6 ways: ok=False ("t_slot would not go down"), the
           cursor never reaches T_SLOT, CURSOR_START itself gets toggled
           (5 select_card presses sent AT THE WRONG SLOT), the mark survives
    (fourth pass) N2: same mutation as M5 above (same line) -- see M5
    (fourth pass) N3: move `_MAYBE_LIFTED.discard(m_slot)` back to BEFORE
    the re-raise attempt (the pre-fourth-pass ordering)
        -> case F4 FAILS: the mark is gone even though the re-raise then
           fails and T stays down -- exactly the discarded-proof hazard N3 fixes
    the skeptic's M6: drop the resolver's `t_slot not in sel` precondition
    (line 1627), leaving only `n != MAX_HAND_SIZE or _ys[m_slot] is not None`
        -> case F6 FAILS 3 ways: ok=True (should refuse, T is resting), a
           `select_card` press lands on T (raising a card that was never
           meant to be touched), the mark is wrongly cleared -- reproduces
           the skeptic's own predicted mechanism exactly ("the re-look would
           find M readable, and `_select_verified` would then RAISE a card
           that was resting")

**Run.** `test_discard_confirm_verified.py`, `test_discard_is_proven.py`,
`test_verified_selection.py`, `test_commit_refuses_unseen_strays.py`,
`test_verified_presses_on_match_path.py`, `test_hand_memory_persists.py`,
`test_run_debit_and_scoring.py`, `test_i22_pitch_boost_slot3.py`,
`test_tactics_select_fallback.py`, `test_refusal_unwinds.py`,
`test_readable_hand_gate.py`, `test_run_resume_and_persist.py`,
`test_scoreboard_populations.py`,
`tests/harness/test_no_undefined_names.py`, `test_no_shadowed_module_defs.py`,
`test_claude_md_constants.py`,
`tests/rig/test_no_real_input_under_test_run.py` — all 16 exit 0 (the
skeptic's own round-2 regression list). **Also run
(third pass) `test_lifted_discard_row_rescued.py`: FAILS on this branch, but
identically on `main` (0b15578) — the traceback is inside
`_verified_select_and_play_inner`'s I-48b/I-48c re-verify loop calling
`_walk_cursor_to`, an `IndexError` from the test's own scripted
`_fake_cursor_glow5`/`_queue5` running out of frames, and `git diff main --
input_controller.py` touches no line between there and `_clear_strays`. A
separate, pre-existing issue (I-48e); this branch does not change its
outcome.** The skeptic independently verified this same finding on the
scratch copy, byte-identical traceback.

**Also this pass:** the dead `DISCARD_CONFIRM_TRIES` constant (superseded by
`PRESS_VERIFY_TRIES` once confirm_discard went through `press_verified`) and its
two now-stale prose references (`orchestrator.py`, `test_verified_selection.py`)
are removed; a raising `_look_settled` inside the confirm_discard verification is
now caught and converted to the safe UNVERIFIED outcome instead of propagating
with no `_mark_maybe_lifted`/`invalidate_cursor` (`select_bans_verified` carries
the identical lesson).

**Status.** merged 5d7dc88; Opus skeptic round 1 REFUTED (adjacency exemption
widened I-48d), round 2 CONFIRMED WITH NOTES, N1/N2/N3 fixed 7a42d46, 16/16
mutants; live: 2 discard-not-confirmed polls in cycle 9 are this fix's target.

### I-54  A truncated card name ('JOHNNY DRAW') passes the result-word OCR fallback: phantom draw #9 mid-match   P0  reader

**Evidence.** Main checkout, `overnight/run_live_20260921t.log` ~634-640 (read-only):

    [state] the templates missed this banner; OCR read it: 'JOHNNY DRAW'
    [reveal] outcome unscorable: your_score missing from the follow-up read; dropping the pending row for our_power 8.
    Draw logged (9 total).
    [verify] close_result: a fresh frame reads is_result=False, not True -- nothing to close, and this is not a result screen. Refusing to press rather than button-mash a live screen.

`close_result` refusing to press because a FRESH read says `is_result=False` is the
tell: the match was still live, no banner had ever appeared. `progress_testing.json`'s
draws count is over by one from this event; the match's real result, whatever it
turns out to be, will be logged separately when it actually finishes.

The opponent's card that turn is JOHNNY DRAWERS (confirmed from the frame: the
reveal frame in `test_fixtures/reveal_kind_truth/auto/` nearest the log's own
timestamp, `speed_boost_1790029528372177000.jpg`, shows a BATTER card "Johnny
Drawers" power 7 speed 1 on the diamond, matching the log's own "ours 7, theirs 4"
two lines earlier -- copied here to
`test_fixtures/result_screens/negative_johnny_drawers_20260921.jpg`). I-34
(2026-09-21, commit b8c033f) already fixed the CONTAINMENT form of this bug
("DRAW" as a substring of "DRAWERS") with a whole-OCR-token match. This is the
TRUNCATION form: OCR dropped DRAWERS' trailing letters instead of running them
together, reading "JOHNNY DRAW" -- and once split on the space, "DRAW" is not a
substring of anything, it IS the whole vocab word. `_similar` cannot refuse it; it
is correctly being asked about "DRAW" alone.

**Root cause.** `result_ocr.match_word` (the orchestrator's last-resort PaddleOCR
fallback, distinct from `local_state.read_result_card`'s own I-30 whole-word fix,
which this ticket does not touch) had no way to tell "the banner says DRAW" from
"a card name got truncated down to DRAW" -- both produce the identical single
token "DRAW" once split. Reproduced offline before this fix:
`result_ocr.match_word([("JOHNNY DRAW", 1.0)])` -> `('draw', 'JOHNNY DRAW')`.

**Fix.** A candidate token is now refused when the OCR TEXT IT CAME FROM also
contains another alphabetic run of 3+ letters -- a real banner's OCR text is the
word alone, plus trailing punctuation noise ("DRAW!", "DRAWI"), never a second
word, while a card name is two. Checked PER OCR TEXT ENTRY (one `(text, conf)`
tuple in `texts`), never pooled across the whole band crop.

That per-entry scoping is load-bearing and is the reason this is not a
rediscovery of the veto I-34's own skeptic reverted the same day ("refuse a match
if the band has any other long alphabetic token"), which pooled every OCR text in
the crop and always tripped on the matchbox-ring lettering (CAMEL BURN, SPARK-D,
SAFETY MATCHES, SPIKE-D...) that sits somewhere in `BAND` on every class,
including the phantom-draw frame itself. `tools/read_banner_paddle.py` returns
one `texts` entry per PaddleOCR-DETECTED TEXT REGION (`rec_texts`/`rec_scores`
zipped), not one entry for the whole crop -- the matchbox lettering and a card
name banner are always SEPARATE detected regions, so a guard scoped to a single
entry's own tokens never sees the matchbox text at all, and a card name's two
words landing in ONE entry is exactly what it catches.

No confidence floor from the template reader was added (the task considered one:
"accept only when the template reader's best score for that word is at least some
measured floor"). No such floor has been measured, and CLAUDE.md 10.32 is explicit
that inventing one on the money path is exactly the mistake this file's history
warns against -- the lone-token rule alone is what shipped.

**Measured (agent_progress/issues/I-54/progress.md), via real PaddleOCR, before AND
after this fix -- identical both times, so the fix costs nothing on a genuine
banner:**

    test_fixtures/reveal_kind_truth/auto/ (185 real reveal frames)   0 false positives, both arms
    heldout_winner_a.jpg 'WINNER' / heldout_loser_a.jpg 'LOSER' /
      heldout_draw_768.jpg 'DRAW!'                                    all three still read correctly
    the new negative fixture (real OCR: PITCH/FOCUS/PITCHER)          None, both arms
    phantom_draw_20260920.png (I-34's own fixture, real OCR:
      JOHNNY/DRAWERS/JOHNNYDRAWERS/PITCHER)                           None, both arms

A KNOWN, DECIDED LIMIT, PINNED RATHER THAN LEFT IMPLICIT: a run under 3 letters
("JO", "A") does not count as a second real word, so a card name truncated on
BOTH halves down to 2-letter fragments ("JO DRAW") is not caught by this fix.
Nothing observed -- this module's own docstring, the live incident -- has ever
shown OCR truncate a card's FIRST word that hard while leaving the second at a
clean vocab length, so this is recorded rather than chased with an arbitrary
lower floor (CLAUDE.md 10.4: a threshold sits between two MEASURED populations,
and no population of 1-2 letter OCR fragments has been measured here). Pinned:
`match_word([("JO DRAW", 1.0)])` still reads `draw`, deliberately.

**Verify.** `tests/minigame/test_result_ocr_whole_word.py`, extended: (A) the exact
bug, `match_word([("JOHNNY DRAW", 1.0)])` -> None; (B) the untruncated form stays
refused (I-34 control, re-asserted here); (C) `DRAW`/`DRAW!`/`DRAWI` still read as
draw; the mechanism generalises to `match_word([("THE WINNER", 1.0)])` -> None
(a second real word, even a filler, refuses) with the JO DRAW limit pinned
alongside it, and to a SEPARATE-entry control (`[("CAMEL BURN", ...), ("DRAW!",
...)]` -> draw) proving the guard is per-entry, not pooled; (D) the three live
result fixtures still read, through `read_banner`'s full wiring (worker stubbed to
the REAL texts measured above -- no `paddle_venv` needed to run this
deterministically, same pattern I-34's own wiring test uses); (E) the new negative
fixture -> no result, both via `match_word` directly on its real measured OCR text
and through `read_banner`'s full wiring on the real fixture file. Section 3's
former `"THE WINNER" -> win` assertion is now `"A WINNER" -> win` (a filler under
the 3-letter floor, which still demonstrates the tokeniser finding a word beside
other text); the old input is re-asserted elsewhere as the new, correct answer --
shown and adjusted, not silently dropped, per CLAUDE.md 10.32.

**Mutants (4, `__pycache__` never written -- `-B` throughout; sha256-verified
restore to `71e7b2f21aa735834ed502036e9dba83965a22b494009f97194fa3b0bae34966`
between each):**

    remove the `len(significant) > 1` guard entirely
        -> FAILS the exact-bug check AND the 'THE WINNER' check (2)
    `len(significant) > 1` -> `>= 1` (any significant token at all blocks)
        -> FAILS 19 checks: every plain-vocabulary read, 'A WINNER', the pinned
           'JO DRAW' case, three of the four recall-regression cases, the
           SEPARATE-entry control, the wiring checks, and all three live-fixture
           checks
    the length floor `>= 3` -> `>= 1` (single letters count as "significant")
        -> FAILS 6 checks: 'A WINNER', the pinned 'JO DRAW' case (its own "JO"
           now counts as significant, which is exactly the known limit the pin
           exists to name), and three of the four recall-regression cases --
           their split forms are runs of 1-3 letter fragments
    the length floor `>= 3` -> `>= 7` ('JOHNNY', 6 letters, no longer counts)
        -> FAILS the exact-bug check AND the 'THE WINNER' check (2), reopening
           the bug this ticket exists to close

The negative fixture's real OCR text (PITCH/FOCUS/PITCHER) does not itself match
any vocab word with or without the guard, so none of the four mutants above are
caught BY that check specifically -- noted plainly rather than left to look like
independent coverage it is not. It is a real-image control against the pooled-veto
regression shape (mutant 2's kind, generalised) and against any future change that
makes the OCR fallback newly loose on non-vocabulary text.

Siblings run clean: `tests/minigame/test_result_reader.py` (one PRE-EXISTING,
UNRELATED failure carried over from I-34 -- `diagnostics/20260910_103221_5018/
screen_at_stall.png` does not exist in this worktree; reproduced identically
before and after this ticket's changes), `test_result_card_is_read.py`,
`test_run_debit_and_scoring.py`, `test_transition_screens_recognised.py`,
`tests/harness/test_no_undefined_names.py`, `test_claude_md_constants.py`.

**Status.** merged ca202d1; Opus skeptic CONFIRMED WITH NOTES (627 frames, 0
disagreements on true results, 0 FP on 285 non-result frames); N1 pinned, N3 fixture
added; LATER: VOCAB lacks DEFEAT (a live run retried 15/15 and ended unscored) and
PaddleOCR fails on the mid-animation flat banner 10/231.

### I-55  Result commits leave no evidence: three draws today with no numbers and no frame   P1  evidence

**Evidence.** Main checkout, three result commits with nothing behind them, same day:

    overnight/run_live_20260921r.log ~555-556   "Draw logged (8 total)" right after a
        poll that printed the templates were distrusted -- draw #8 is unverifiable
        after the fact
    overnight/run_live_20260921t.log ~634-636   a PHANTOM draw from a truncated card
        name (I-54's own incident) -- the ONLY reason this one is explained is that
        a frame happened to survive in test_fixtures/reveal_kind_truth/auto/ from an
        unrelated keeper (record_reveal_kind) and someone went and found it by hand
    overnight/run_live_20260921u.log ~724-725   "Draw logged (9 total)" with no
        `[state]` line at all -- the next match's ban scan followed, so it was
        PROBABLY real, but nothing on disk says so either way

`HANDOFF_NOW.md`'s LATER list already named the gap: "log the evidence (template
scores + OCR words + scoreboard) on every result commit and keep the result frame --
the reveal/money keepers exist, the result screen has none."

**Root cause.** `local_game_state`'s "result" branch (orchestrator.py ~4388, ~4463)
computes the template scores dict, which reader answered (`why`, which names the
CARD path when the arched-banner templates missed) and the OCR outcome/detail --
and returns NONE of it. Its return dict for a "result" screen carries only
`result_outcome`/`result_won`/`your_score`/`opp_score` (the last two always None on
the local path, per that function's own comment on why it supplies no scores). So
by the time run() reaches the commit block and prints "WIN #N logged" / "Draw
logged" / "Loss logged", the numbers behind the word are already gone -- there was
never anywhere for them to survive the round trip, unlike the reveal path
(`record_reveal_kind`, OPEN-24) and the refused-select path (`record_refused_select`,
I-48), which both already keep a frame + why.json at their own decision point.

**Fix.** `record_result_frame(outcome, evidence, row=None, out_dir=None)`, beside
`record_reveal_kind` / `record_refused_select`, same contract as both: never raises
into the turn loop, writes nothing under `BASEBALL_TEST_RUN` unless a test hands it
`out_dir` (or sets `BASEBALL_RESULT_FRAME_DIR`), REFUSES past
`RESULT_FRAME_MAX_FILES` (200) rather than pruning. One call site, run()'s shared
commit block, right after the WIN/Draw/Loss print and before `match_in_progress`
is cleared.

`evidence` is exactly what run() still has at that point -- `your_score`,
`opp_score`, `result_outcome`, `result_won` off `state_json` -- threaded straight
through, no re-read. The template scores per word and the OCR fallback's answer are
genuinely gone (see Root cause), so the keeper re-derives them from a FRESH capture
taken there, before the screen is dismissed, by calling `local_state.read_result`
and `result_ocr.read_banner` again on it -- and says so explicitly, in both the
printed line and `why.json`'s `note` field, so a re-derivation taken a poll or two
after the real decision is never mistaken for the decision frame itself. Neither
reader's own code was touched, and nothing about how the outcome is DECIDED changed
-- this call sits after `outcome` is already settled.

Frame + why.json land at `diagnostics/result_frames/<outcome>_<ns>.png` /
`<outcome>_<ns>.why.json` (`diagnostics/` is gitignored, `.gitignore:75`). `row`,
when given (run() passes `state_json`), is stamped with the frame's relative path
the way `record_reveal_kind` stamps `matchup_info` -- there is no per-match result
row persisted anywhere today, so this is a forward-looking no-op until one exists.

**The evidence line**, printed once per commit -- captured verbatim from
`tests/minigame/test_result_commit_evidence.py` case (A), run against this
worktree's blank harness frame (real numbers, not an invented example; the
`paddle venv missing at ...` detail is genuine too -- `paddle_venv/` does not
exist in this worktree, CLAUDE.md section 2):

    [result] win decided from state_json (your_score=7, opp_score=3,
    result_outcome=None, result_won=True); re-derived template scores
    {'winner': 0.0, 'loser': 0.0, 'draw': 0.0} (no result word found (best
    0.000 < 0.8; card band read '')); re-derived OCR None (paddle venv missing
    at .../paddle_venv/bin/python); frame -> win_1790037824847166000.png

**Verify.** `tests/minigame/test_result_commit_evidence.py`, driven end to end
through `_run_harness.Harness` (the same harness `test_run_debit_and_scoring.py`
uses) plus two direct calls for the cases that would otherwise fight the harness's
own `_fast_grab` patch, its own `check(name, cond)` NAME-FIRST (deliberately not
`_run_harness`'s COND-FIRST `check`, to keep the two orders out of one file --
CLAUDE.md's nine-signatures trap): (A) a WIN commit prints the evidence line
(state_json's numbers plus the re-derived template scores and OCR) and writes
frame + why.json into a temp root (`BASEBALL_RESULT_FRAME_DIR`, never the live
dir); (B) a DRAW commit, with `local_state.read_result` monkeypatched to a
card-reader answer, names the CARD path in both the print and why.json; (C) under
`BASEBALL_TEST_RUN` with no seam, `_fast_grab` stubbed to SUCCEED, nothing is
written and capture is never even called -- proves the guard fires before
capture, not that capture happened to fail; (D) `PIL.Image.Image.convert`
monkeypatched to raise, driven through a real WIN commit -- the match still
scores (`wins == 1`) and nothing is left half-written; (E) the 200-file cap
refuses out loud and does not prune the oldest frame.

**Mutants (3, `__pycache__` cleared between each -- `-B` throughout; sha256-verified
restore to `8cc8afe21e79c3136eacc59212ea8d3a3190f0b22eb4d8143f1df1c736556896`
between each):**

    drop the print call (lines 7598-7604)
        -> FAILS 5: all four (A) evidence-line checks, and (B)'s CARD-path check
    `why = {...}` -> `why = {"outcome": outcome}` (the numbers dropped)
        -> FAILS 5: all four (A) why.json-content checks, and (B)'s why.json
           CARD-path check
    remove `if d is None and _running_under_test(): return None`
        -> FAILS 3: all three (C) checks -- returns a filename instead of None,
           writes into the watched temp root, and (moot at that point) the
           guard-before-capture ordering check

Run clean (`BASEBALL_TEST_RUN=1`, offline, single process): the new file, plus
`test_run_debit_and_scoring.py`, `test_stale_flag_never_presses_unpaid.py`,
`test_run_resume_and_persist.py`, `test_transition_screens_recognised.py`,
`test_reveal_frame_kept.py`, `test_unscored_reveal_rows_kept.py`,
`tests/harness/test_no_undefined_names.py`, `test_no_shadowed_module_defs.py`,
`tests/rig/test_no_real_input_under_test_run.py`.

**FOLLOW-UP, SAME DAY: THE FIRST FIX WAS RE-DERIVING, NOT RECORDING.** The evidence
line above IS the tell, read correctly: template scores of
`{'winner': 0.0, 'loser': 0.0, 'draw': 0.0}` on a screen that had just been scored a
WIN. A skeptic caught it from that own sample -- `record_result_frame`'s first
version called `_fast_grab()` fresh at the commit site, one or more polls AFTER
`local_game_state` had already decided the outcome, so the "evidence" it printed and
saved was a picture of whatever the result screen looked like a beat later (already
fading, already dismissed, or simply re-photographed), never the frame the decision
was actually made on. The fix was correctly scoped (no re-read unless the values are
gone) but wrong about WHERE the values were gone from: they were gone from
`state_json`, not from existence -- `local_game_state` had them the whole time and
simply never returned them.

**Root cause, precisely.** `local_game_state`'s "result" branch (orchestrator.py, both
return sites) already computes `res["scores"]` (the template bank's per-word dict),
`res["why"]` (which names the CARD path when the arched-banner templates missed) and
the OCR outcome/detail from `result_ocr.read_banner`, and held `full` -- the exact
frame it read them from -- in a local variable that went out of scope the moment the
function returned. None of that survived into `state_json`.

**Fix.** `local_game_state` now threads five new keys on every "result" return --
`result_scores`, `result_source` ("template"|"card"|"ocr", derived from `why` and
whether OCR overrode the templates -- no new reader call, just naming the path already
taken), `result_card_word` (regex-extracted from `why`'s own `CARD read 'X' -> ...`
text when the card path fired), `result_ocr_words` and `result_frame_ns` -- and stashes
the frame itself in a new module-level `_LAST_RESULT_FRAME = (PIL Image, ns)`, set
ONLY inside the "result" branch (never touched by a `"turn"`/`"ban_screen"`/etc read),
paired with the same timestamp so a consumer can refuse a mismatched pairing rather
than trust a global that might belong to an earlier poll -- same shape as
`input_controller._LAST_PROBE_ATTEMPTS` / `_LAST_PLAY_DROPPED_TACTICS`. Neither reader
was touched and the outcome decision is untouched; this only threads what was already
computed.

`record_result_frame` now prefers that exact pairing: when `evidence["result_frame_ns"]`
matches `_LAST_RESULT_FRAME`'s own timestamp, it saves THAT frame and prints the
threaded numbers verbatim -- no second call to either reader. It falls back to the old
re-derive-and-say-so behaviour only when the fields are genuinely absent (the paid
path, or a hand-built state dict), and the fallback is now unmistakably labelled
`path='re-derived'` in both the print and `why.json`, rather than looking like ordinary
evidence.

**The evidence line, now on the decision frame** (captured verbatim,
`tests/minigame/test_result_commit_evidence.py` case A, `local_state.read_result`
seeded with a known dict so the assertion is exact, not eyeballed):

    [result] win decided from state_json (your_score=None, opp_score=None,
    result_outcome='win', result_won=True); path='template'
    scores={'WINNER': 0.987, 'LOSER': 0.012, 'DRAW': 0.034} card_word=None
    ocr_words='paddle venv missing at /nope'; frame is the DECISION frame --
    local_game_state's own 'result' branch read this exact picture and produced
    these exact numbers; nothing here was re-derived; kept -> win_<ns>.png

The seeded `{'WINNER': 0.987, ...}` appears verbatim -- proof this is the threaded
value, not a fresh read of a 1920x1080 solid-colour test frame (which would score
near 0.000 on every word, exactly what the FIRST fix's sample showed).

**Verify, updated.** `test_result_commit_evidence.py` cases A and B now call
`orchestrator.local_game_state()` directly with `local_state.read_result` /
`result_ocr.read_banner` / `_fast_grab` seeded to known values (a helper,
`_seed_and_read`), so the threaded fields and the stashed frame are checked against
exactly what was seeded, not against whatever a live screen happens to show. New
**case F**: seeds `local_game_state` with one known frame (`_DECISION_FRAME`), then --
before calling `record_result_frame` -- swaps the live capture over to a SECOND, 
distinct known frame (`_FALLBACK_FRAME`, standing in for a screen that has "moved on"
by commit time) and asserts the kept PNG's pixel bytes are byte-identical to
`_DECISION_FRAME` and NOT `_FALLBACK_FRAME`. A trailing control keeps one full
Harness-driven WIN commit through `run()`, confirming the commit site still wires
`state_json` into the keeper rather than something ad hoc.

**Mutants, 5 total now (all `__pycache__`-cleared, sha256-verified restore to
`ec7dbf24d7972041df39fac3ae3a922c510f58c58b6c77d311970461d5de8acf` between each --
note the first fix's sha `8cc8afe2...` above is now stale, superseded by this
follow-up):**

    drop the print call                                   -> FAILS 6 (A x2, B x2)
    `why = {...}` -> `why = {"outcome": outcome}`          -> FAILS 2 (A's why.json checks)
    remove record_result_frame's OWN test-run gate
      (there are 4 near-identical gates in this file --
      record_reveal_kind's, record_money_read_frame's,
      record_refused_select's, and this one; a naive
      `lines.index()` on the first match hit
      record_reveal_kind's and produced a SILENT FALSE PASS,
      caught only by re-running: exit 0, zero failures, on
      a mutant that should have broken case C outright --
      CLAUDE.md 10.10, "count the occurrences first")       -> FAILS 3 (all of C)
    print the RE-DERIVED numbers instead of the threaded
      ones (swap evidence.get(...) for a fresh
      local_state.read_result(full) call even when the
      decision frame is available)                          -> FAILS 6 (A x4, B x2)
    keep a FRESH capture instead of the stashed decision
      frame (`full = stashed[0]` -> `full = _fast_grab()`,
      leaving the threaded scores/source/etc untouched)      -> FAILS 2 (both of F)

The fourth mutant's near-miss is worth keeping: the first attempt at it targeted the
wrong `if d is None and _running_under_test():` occurrence (this file has four) and
the test suite reported clean on code that no longer guarded anything. Re-running the
test after EVERY mutant, not just trusting the diff, is what caught it -- the same
discipline CLAUDE.md 10.9 already asks for.

Battery re-run clean against this follow-up (`BASEBALL_TEST_RUN=1`, offline, single
process, 11 files): the new test, `test_run_debit_and_scoring.py`,
`test_stale_flag_never_presses_unpaid.py`, `test_run_resume_and_persist.py`,
`test_transition_screens_recognised.py`, `test_reveal_frame_kept.py`,
`test_unscored_reveal_rows_kept.py`, `tests/harness/test_no_undefined_names.py`,
`test_no_shadowed_module_defs.py`, `tests/rig/test_no_real_input_under_test_run.py`,
`test_validate_game_state.py` -- all exit 0. `test_result_reader.py` exits 1 on ONE
PRE-EXISTING, UNRELATED failure already documented under I-54 ("the dealer prompt
classifies as match_start_prompt" -- `diagnostics/20260910_103221_5018/
screen_at_stall.png` does not exist in this worktree), reproduced identically before
and after every edit in this ticket; confirmed by reading the failure -- it dies
inside `local_game_state`'s own `except Exception as exc: return None, f"could not
capture ({exc})"` branch, before reaching any of the code this ticket touches. Also
grepped `state_json\[` / `.get("result_` across the whole tree: the only other
consumers are `validate_game_state` (paid-path only, never sees `local_game_state`'s
output -- checked its one call site) and `tools/match_crawl.py` (reads a different,
unrelated dict shape via plain `.get()`), neither affected by adding five new keys.

**SKEPTIC VERDICT: CONFIRMED WITH NOTES (`agent_progress/issues/I-55/skeptic.md`).**
Every claim in the follow-up checked out -- decision untouched, consumer safety,
`record_result_frame`'s never-raises/capped/gated contract, timing at the commit
site (12.4ms measured PNG save against a >=4.0s banner hold, no hazard) -- but
THREE independently-constructed mutants, each targeting the exact failure class
this whole ticket exists to prevent, survived the shipped 5-mutant campaign AND
the regression battery:

    loosen the ns equality check (`stashed is not None` alone, dropping
      `stashed[1] == wanted_ns`)                    NOT CAUGHT
    drop the threading at the SECOND return site
      (the OCR-only fallback when the templates
      never score `is_result` at all)               NOT CAUGHT
    make the fallback's provenance text claim
      "the DECISION frame" instead of "RE-DERIVED"   NOT CAUGHT

None of these are refutations of the code -- the skeptic verified all three
scenarios by hand against the UNMUTATED worktree and confirmed the code handles
each one correctly (a genuine stale stash correctly falls back and says so; the
second return site's diff already threads all five keys; the fallback's real
provenance text already says "RE-DERIVED"). The gap was entirely in test
COVERAGE: `_seed_and_read`'s stub always answers `is_result: True`, so every
existing case takes the FIRST return site with a single, internally-consistent
`local_game_state()` call -- nothing in the shipped suite ever (a) reads two
DIFFERENT results in sequence and commits on the stale one, (b) drives the
second return site at all, or (c) inspects the fallback path's own provenance
text rather than only checking the decision path avoids it.

**Three cases added, no orchestrator.py change:**

    (G) genuine ns MISMATCH. Reads result A (frame A, scores A), then reads a
        SECOND, different result B -- overwriting `_LAST_RESULT_FRAME` with B's
        frame and timestamp, the way the next poll in run()'s own loop would --
        then commits on A's now-stale state_json. Asserts the kept frame is a
        FRESH capture (a third, distinct known image, standing in for "the
        screen at commit time"), NOT B's stashed picture stamped with A's
        numbers, and that the print/why.json say `path='re-derived'` and "did
        not match the stashed frame".
    (H) the SECOND return site. `local_state.read_result` seeded to MISS
        (`is_result: False`) with partial scores; `result_ocr.read_banner`
        seeded to answer; ban/prompt/hand stubbed to fall through
        deterministically (`crop_gameplay_regions`, `read_ban_counter`,
        `homeplate_runner_present`, `local_hand_cards`, `table_prompt.at_table`)
        so the test does not depend on how the real readers happen to score a
        synthetic frame. Asserts `result_source`/`result_card_word`/
        `result_ocr_words`/`result_scores`/`result_frame_ns` all thread from
        THIS site, `_LAST_RESULT_FRAME` is stashed here too, and the evidence
        line names the ocr path.
    (I) the fallback's provenance text. Calls `record_result_frame` with NO
        threaded fields at all (`_LAST_RESULT_FRAME` is None) and asserts the
        print AND why.json's `frame_provenance` say "RE-DERIVED" and do NOT say
        "DECISION frame" -- the converse of what case A already checked (that
        the decision path's own print avoids "re-derived").

Verified independently by direct call to `local_game_state()` outside the test
file (`local_game_state()` with the same five stubs as case H) before trusting
the assertion -- reproduces state_json exactly as the test expects, `_LAST_
RESULT_FRAME` set, before any mutant was applied.

**Mutants (3, matching the skeptic's own three exactly; `__pycache__` cleared,
sha256-verified restore to `ec7dbf24d7972041df39fac3ae3a922c510f58c58b6c77d311970461d5de8acf`
between each):**

    loosen `stashed[1] == wanted_ns` to `stashed is not None` alone
        -> FAILS 4: all of (G) -- the kept frame becomes B's stashed picture
           and the print falsely claims the decision frame
    revert the SECOND return site's dict to the pre-I-55 four-key shape
        -> FAILS 8: all of (H) -- result_source/ocr_words/scores/frame_ns all
           come back None, and record_result_frame silently falls through to
           its own honestly-labelled fallback (which is not what (H) is
           testing: it is testing that the SITE threads, not that the
           fallback still works when it doesn't)
    replace the fallback's provenance string with the literal "the DECISION
    frame" text
        -> FAILS 5: all of (I), AND 2 of (G) -- (G) also takes the fallback
           branch (a genuine ns mismatch IS a fallback), so the same lie
           reaches it too; this is a feature of the mutant, not a leak between
           tests, since both cases legitimately exercise the same provenance
           code

Every mutant's FAIL list is scoped to exactly the case(s) whose branch it
touches; no mutant produced a failure outside G/H/I, and no pre-existing case
(A-F, the trailing control) was disturbed by writing them.

Regression battery re-run clean against this addition (`BASEBALL_TEST_RUN=1`,
offline, single process, 11 files): the new test, `test_run_debit_and_scoring.py`,
`test_stale_flag_never_presses_unpaid.py`, `test_run_resume_and_persist.py`,
`test_transition_screens_recognised.py`, `test_reveal_frame_kept.py`,
`test_unscored_reveal_rows_kept.py`, `tests/harness/test_no_undefined_names.py`,
`test_no_shadowed_module_defs.py`, `tests/rig/test_no_real_input_under_test_run.py`,
`test_validate_game_state.py` -- all exit 0. `test_result_reader.py` still exits 1
on the same pre-existing, unrelated fixture gap documented above and under I-54.

**Status.** fixed on branch (follow-up + skeptic gaps closed), awaiting re-review.
