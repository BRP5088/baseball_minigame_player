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
7. Model: Haiku for census and log parsing; Sonnet for code; Opus only for the money
   path (`start_match`, `close_result`, debit, reset) and for strategy A/B design.
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
Still open: the offline replay of the three run-c deals (Verify step 2).

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

**Status.** Open. Unblocked: the refutation is on disk (above) and the other agent
confirms its nudge cannot walk ONTO slot 4, so the gap stands.

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

**Status.** Open.

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

**Status.** In flight (other agent shipped the reader); the fixtures are open.

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

**Status.** Open.

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

**Status.** Open.

### I-08  The paused branch escaped every bound                                    P0  loop

**Status.** SHIPPED by the other agent (DIRTY tree, `orchestrator.py` ~8025:
`polls_without_progress` now counts paused polls). Recorded so it is not re-reported.
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

**Status.** Open. Do after I-01.

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

**Status.** Open.

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

**Status.** Open.

---

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

### I-16  The discard threshold is a fixed 6 and deck-blind                          P2  engine

**Evidence.** `decision_engine.py:227 REDRAW_POWER_THRESHOLD = 6`, swept once. The roster
is 33 known cards (`KNOWN_BAN_ROSTER`), 30 after bans, and the cards seen this half are
known, so P(draw > current max) is computable per turn.

**Proposed fix.** Arm: redraw when P(improve) x (expected gain) beats the cost of the
discard, from the live deck composition. Control: the fixed 6.

**Verify / brief / status.** As for I-13. Open.

### I-17  The opponent model is our card pool, not the log                            P2  engine

**Evidence.** `simulate.py:634 _pitcher_power_distribution` is built from `CARD_POOL`.
RULES.md §2: the two players hold separate decks. `match_log.jsonl` carries their powers
by phase (when we bat, their pitcher: 4 x42, 5 x35, 6 x31, 7 x23, 8 x10, 9 x21, n=162);
powers were read by the same reader in every era, so they survive the outcome-label
problem in I-18.

**Proposed fix.** Build the distribution from the log; rerun `expected_runs_play` vs
`CURRENT` (the earlier negative result used the pool).

**Verify / brief / status.** As for I-13. Open; better after I-18 refreshes the rows.

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

**Status.** Open.

### I-19  There is no run census tool                                              P1  evidence

**Evidence.** Nothing summarises `overnight/run_one_match_*.log` into turns played,
refusals, deals timed out, reveals logged, stop reason. This review counted them by grep.

**Proposed fix.** `tools/run_census.py <log...>` printing one row per run with those
columns, plus a total. Every fix above reports before/after on that table.

**Verify.** Run it on the three 2026-09-20 logs; the counts must match this file's
(run b: 8 refused plays, 3 refused discards; run c: 3 plays, 3 deal timeouts with edge,
stop `unreadable_screens`).

**Agent brief.** Haiku.

**Status.** Open. Do first; it is the scorecard for everything else.

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

## Suggested order

1. I-19 (scorecard), I-01 (relay), I-03, I-09, I-10 — offline, Sonnet, an afternoon.
2. I-02, I-11, I-12 — input path, need one supervised live session.
3. I-04 fixtures on the first live win and draw; I-06, I-07.
4. I-05 — the unattended run, only after 1-3.
5. I-13 to I-17 — simulator A/Bs, can run on Snoopy in parallel with 1-4; I-18 first
   so the opponent model has rows.
