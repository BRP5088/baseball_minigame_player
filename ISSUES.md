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
match read nothing. DEFEAT pinned by the other session. **DRAW still unconfirmed by a frame**
for the card reader; the first live draw closes it. DRAW still unconfirmed by a frame; the
one "draw" scored on 2026-09-20 was I-30's phantom.

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

**Proposed fix.** A named "new_inning"/"reveal_recap" screen case so the pending row waits
through a recognised transition.

**Status.** Open.

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

**Status.** Open.

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

**Status.** Redone after REFUTED skeptic round 1; awaiting skeptic round 2.

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

**Status.** Redone after REFUTED skeptic round 1; awaiting skeptic round 2.

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
