# CLOSED — tickets that were answered, with their evidence

Not loaded automatically. `CLAUDE.md` §11 carries a short pointer for each of these
and says what transferred; this file is the full text, kept because the EVIDENCE is
what makes a closed question stay closed.

Read it when you are about to re-open one of these, or when a number here is quoted
at you and you want the run it came from.

## OPEN-23  the ban scan returned a partial collection

**OPEN-23 — CLOSED THE SAME DAY, AND THE DIAGNOSIS IN IT WAS WRONG. The scan was fine;
every PRESS was going to a /bin/zsh.** `pgrep -f chiaki` matched this session's own shell --
its command line contained the word because the commands being run mentioned chiaki paths --
it sorted first, and `chiaki_pid` took `out[0]`. The liveness guard passed because a shell is
alive. So the scan pressed, nothing moved, its desync guard correctly refused to catalogue
rows it could not verify, and it returned what it had. **Every part of that behaved as
designed.** Fixed in `input_controller._resolve_chiaki_pid` (match the executable NAME, then
filter the loose match by what each process IS) plus an identity re-check on the cached pid
and a re-resolve on the ban scan's desync branch; pinned by
`tests/rig/test_input_target_is_chiaki.py`, 4 mutants caught. With the right pid the same
scan returns 23 cards on the old geometry and 25 on the fitted one.

**The lesson worth keeping is the shape, not the ticket:** the entry below blamed the loop
that reported the symptom. The guard that "could not fire" was one level further out and was
asking the wrong question -- "is this pid alive" rather than "is this pid CHIAKI" -- which is
this project's signature failure wearing a new hat. The original text follows.

**OPEN-23 (original) — THE LIVE BAN SCAN RETURNS A PARTIAL COLLECTION WITHOUT FAILING, and
choose_bans then picks the best 3 of 8 instead of the best 3 of ~33 (2026-09-13).**

Found while A/B-ing the fitted ban geometry, by running the REAL
`read_full_ban_collection()` end to end. It printed SCROLL DESYNC on every batch --
*"press count says row 39, the scrollbar says 4"* -- and returned 8 cards anyway.

The desync guard did exactly what it was built for: trust the scrollbar, never the press
count, because a wrong row bans a card the player does not own. What is missing is the
other half. The loop absorbs the desync, keeps pressing, reads the same rows again, dedupes
them by absolute (row, col), and hands back whatever it has WITH NO ERROR. `choose_bans`
cannot tell a complete collection from a quarter of one.

**IT IS NOT THE FRONTMOST TRAP and it is not the fitted geometry.** Probed straight
afterwards with chiaki confirmed frontmost: from level 5 one `move_down` moved it to 4 and
three more moved nothing at all, cursor parked at (1, 2) throughout. Both geometry arms hit
it identically, which is why they agreed so comfortably -- a partial collection is easy to
agree about.

**WHAT TO DO WITH IT.** The cheap guard is a floor: a scan whose scrollbar never reaches
the bottom level has not seen the collection, and should say so rather than return. The
scrollbar already knows -- `read_ban_scroll_level` reports 0..7 and the bottom clamp is 7,
so "did this scan ever observe level 7" is free and is exactly the question. What is NOT
understood is why the scroll stops; that wants one session with the console and no match in
flight.

Until then a match played on this bans the best of what it happened to see.


---

## OPEN-1  the leg-end frame path

**OPEN-1 — the leg-end frame path is BUILT AND PINNED; there are still ZERO
admissible frames.** `follow()` publishes at the right moment: it sets
`_LAST_LEG_END[node]` immediately after `img = capture()` and BEFORE the
`recover_to_node` branch, and the local reassignment after a successful fan does
NOT overwrite the published frame. `follow_verified` clears the stale entry per
node and pops it for classification, and classification sits OUTSIDE `if shots:`
so a run that saves no jpegs still produces a census. With `shots=` a live run
writes `at_<node>_<epoch_ms>.jpg` at the moment the leg's last push finished and
the character settled — before `confirm()`, before the fan. **A frame written by
that path IS admissible.**

Pinned BEHAVIOURALLY by `tests/routing/test_failure_census_provenance.py`, which
drives `follow()` with a stubbed `walk_link`, asserts `recover_to_node` actually
ran, and then checks the published frame is the pre-fan one. The older
`test_failure_frame_is_the_leg.py` checked this with a SOURCE SUBSTRING and does
not catch a second assignment added after the fan — re-introducing exactly that
bug passes it and fails the new one.

**All fifteen candidate frames on disk are excluded, and none is a near miss.**
`overnight/failframes_prerecovery/` (8) are POST-FAN — six sit at bearing
98.1-105.8 against a leg commanded 2.1, the fan's signature, and 4 wedged /
2 overshot / 2 regressed by class. `overnight/failframes/` (4) are PRE-ATTEMPT:
all 1500 keypoints, all identifying `bar_pool_room` at 506-734 matches, bearings
284.8-288.3 — the inbound heading of the PREVIOUS leg, i.e. photographs of the
previous node's successful arrival. `overnight/jukebox_failframes/` (3) use
FIXED names, so each is the last write and its outcome is unknown. They remain
valid as classifier appearance data and invalid as evidence about a leg.

**And the OPEN-14 harness collects nothing.** `overnight/ab_jukebox_leg.py`
reaches its start node with `go_to_node_verified(..., shots=SHOTS)` but walks the
leg UNDER TEST with `gw.walk_link`, which publishes no leg-end frame — so that
A/B produced ZERO frames of the leg it was testing, and there is no
`at_bar_jukebox.jpg` anywhere. `ab_stall_on_restored.py` is the same shape. Fix
that before spending console time on the census.

**No live run has ever recorded a class census at all**: zero "failures by
signature" and zero "failure kind:" lines across every `overnight/*.log`, and no
`overnight/*.json` carries the key.

One silent spoiler is FIXED. When no leg into a node ever completed, the
classifier was handed `before` or a post-fan `capture()` — the two inadmissible
frames this ticket is about — and `failures_by_kind` counted them identically.
`graph_walk._LAST_FAILURE_SOURCES` and `LEG_END_SOURCE` now split the result into
`failures_by_kind_leg_end` and `failures_from_fallback_frame`, so no denominator
goes missing. Three spoilers remain and are not fixable in a few lines: the
published frame is the last attempt in which the leg actually RAN, not
necessarily the third; `walk_link`'s in-leg escape ladder can jump or strafe
before the frame is taken; and for the GOAL node the frame follows
`reach_table()`'s aim sweep, so its heading is post-sweep.

**BOTH HALVES OF THIS ARE NOW DONE (audit 2026-09-07; the paragraph stood
stale for a day).** The path HAS executed live: hundreds of
`at_<node>_<epoch_ms>.jpg` frames and dozens of `success/ok_*.jpg` exist under
`overnight/*failframes*/` from 2026-09-06 on, and "THE FAILURE CENSUS EXISTS"
below was taken from them. And every harness now surfaces the leg-end key:
`_harness.census_kinds` / `report_kinds` (f9b9c56, 2026-09-07) report
`failures_by_kind_leg_end` split by provenance and name what they cannot read. Acceptance test unchanged: a real
jukebox-leg failure frame must NOT read bearing ~286 and must NOT identify as
`bar_pool_room`.


---

## OPEN-14  the full-route streak to the table

**OPEN-14 — MEASURED 2026-09-07 (02:26-06:45): the full-route streak to the
table at attempts=9 arrived 1 of 3 valid trials; 7 of 10 were CENSORED by the
ceiling; and the one other "arrival" was `identify()` naming a pose it must not.**
`overnight/streak_table.py`, 10 trials, route `portrait_room -> bar_pool_room ->
bar_jukebox -> dealer_table`, `attempts=9`, `start_hint=SPAWN`, `shots=`, 1800s
external ceiling (`overnight/streak_table.json`, `.log`, `streak_table_arrivals.jpg`,
`streak_table_table_ends.jpg`):

    trial   outcome    depth   seconds   at_table recheck
      1     INVALID      -       1800    ceiling; dealer_table attempted 6x, 19 sweeps, ink max 0.0415, 7 resets
      2     ARRIVED     4/4      1201    True  — the prompt, twice, 0.8s apart
      3     INVALID      -       1800    ceiling; 6 table attempts, 26 sweeps, ink max 0.0253
      4     INVALID      -       1800    ceiling; 7 table attempts, 15 sweeps
      5     INVALID      -       1800    ceiling; 6 table attempts, 19 sweeps, ink max 0.0370
      6     "ARRIVED"   4/4       486    FALSE — verified by identify() at 194/1.53, one sweep at ink 0.0105
      7     INVALID      -       1800    ceiling; 5 table attempts, 15 sweeps
      8     missed      2/4      1049    wedged on the jukebox leg, all 9 attempts
      9     INVALID      -       1800    ceiling; 5 table attempts, 14 sweeps
     10     INVALID      -       1800    ceiling; 5 table attempts, 17 sweeps

**Honest tally: 1 arrived of 3 valid, best streak 1.** The harness printed 2/3
and streak 2; both count trial 6, which does not count.

**TRIAL 6 IS A HOLE IN THE VERIFIED PATH, AND IT IS THE FIRST ITEM FOR THE
MORNING.** `locate()` (graph_walk.py:260-292) tries `at_table()` and, when that
is False, falls through to `places.identify()` and returns whatever room it
names. `places/dealer_table/` holds three references, so `identify()` CAN name
the table — from a distance where no prompt exists, because the references are
the table VIEW. `go_to_node_verified` then logged `verified at dealer_table
(dealer_table 194.000/1.530)` and counted it, while the independent `at_table()`
re-read 0.8s later said False and the trial's only sweep peaked at ink 0.0105
(`INK_MIN` 0.024). §7's rule — the table is a POSE, confirmed by `at_table()`,
never `identify()` — is enforced in `confirm()` (node == GOAL) and NOT in
`locate()`. The two "verified" frames make it plain: trial 2 stands close with
the dealer group ahead; trial 6 is the same scene from further back. FIXED
2026-09-07 morning: `locate()` returns None when `identify()` names `GOAL` and
the prompt is absent, with the refused evidence in its detail string. Pinned by
`tests/routing/test_locate_goal_is_a_pose.py` (three mutants caught: guard
deleted, guard compares to a node that never occurs, guard over-blocks every
room). The trial-6 capture itself was never saved — the `ok_dealer_table` frame
is the pre-sweep leg end and identifies as `bar_jukebox` 295/2.11 — so the
test stubs the detectors with trial 6's numbers verbatim.

**THE CEILING CENSORED 7 OF 10 BY CONSTRUCTION.** Every censored trial reached
`bar_jukebox` and then spent the rest of its 1800s on the table leg, 5-7
attempts each — and after each miss `locate()` could not name the position, so
an `attempts=9` retry on the goal leg is a FULL RESET AND ROUTE RE-WALK (6-7
resets per trial). The 780s maximum that sized the ceiling came from OPEN-5,
where retries are local. §10.14, self-inflicted. A streak to the table is not
measurable at this ceiling; it needs either local retries on the goal leg or a
ceiling of `attempts x route-time`.

**WHAT THE 37 TABLE-LEG END FRAMES SAY.** *(Caveat 2026-09-07: for the GOAL node
those frames were taken AFTER approach_goal's stepping and reach_table's sweep,
so they describe where the recovery left the camera — six read 253-258, the far
end of the 19-heading circle — not where the leg ended. From da5b7ec the leg-end
frame is published BEFORE the sweep; see OPEN-21.)* The leg ends in the dark, against an
NPC, against the bar-top, or looking at the floor — including in both trials
that then "arrived": the arrival happens only after `reach_table` turns the
camera. The sweeps DO see the prompt at times (ink max 0.042, 0.037, 0.030,
0.025 across trials, above `INK_MIN` 0.024) without satisfying `at_table()`'s
score gate, so the character is near the prompt's edge, not far from it. That
is OPEN-17's arrival-heading gap with frames instead of an ordering.

**What did NOT fail:** `portrait_room` and `bar_pool_room` arrived by attempt 2
in all ten trials; `bar_jukebox` arrived in 9 of 10 (2-7 attempts; trial 8
exhausted nine). The restored jukebox leg is not the problem it was.

The original ticket text, for the harness lessons, follows.

**OPEN-14 (original) — The restored jukebox leg as a full-route streak
(started 2026-09-07 02:26).** The leg was 4.3x too short and could not reach its
destination; it is back to its recorded 1.031 units over 3.30s. The short-vs-
restored A/B this ticket originally asked for is superseded: the short leg is
gone, the arithmetic says it could not arrive from anywhere in its origin's
basin, and console time spent measuring a leg that cannot arrive answers
nothing. What measures the restored leg is the run on the console now:

    overnight/streak_table.py  ->  overnight/streak_table.json, streak_table.log
    10 trials, route portrait_room -> bar_pool_room -> bar_jukebox -> dealer_table
    attempts=9, start_hint=SPAWN, shots= (leg-end frames), 1800s external ceiling
    goal scored by at_table() after follow()'s aim sweep (confirm(), node == GOAL)
    reported as the LONGEST CONSECUTIVE streak; invalid trials neither extend nor break it

Its per-node results give the restored leg's arrival rate at attempts=9 on the
way to the answer that matters: how many in a row reach the TABLE. Trial 1
started at load 8.0 / 15.5 / 13.7 (cancelled agents draining); §10.13a covers
~8-11, so treat trial 1 as suspect if it is an outlier. Read the result before
touching any leg — this is the first streak with the table leg and the prompt
as the final check.

**TRIAL 1 (03:00): INVALID at the 1800s ceiling, and the ceiling was censoring by
construction.** It verified `portrait_room`, `bar_pool_room` and `bar_jukebox`,
then failed the TABLE leg five times: every `reach_table` sweep reported *swept
19 headings around 76; best ink 0.0000 at None, prompt never appeared* — not a
weak prompt, no prompt. After each miss the localiser could not name the
position (87 matches, ratio 1.16), so `attempts=9` on the goal leg means a FULL
RESET AND RE-WALK OF THE ROUTE per attempt (7 resets inside one trial); six of
those is 30 minutes. OPEN-5's 780s maximum was measured where retries are
local, and I set the ceiling on it — §10.14, self-inflicted.

The five `at_dealer_table` leg-end frames (`overnight/streak_table_trial1_table_ends.jpg`)
show where the table leg actually ends from the restored jukebox pose: pressed
into an NPC's coat; dark geometry; a bar-top with a bottle filling the view; and
twice **looking DOWN at a tiled floor** — a yaw sweep with the camera on the
floor cannot see the prompt at any heading (STAIRS_APPROACH.md: pitch is
uncontrolled in production). So the restored jukebox leg ARRIVES, verified, and
the table leg recorded from the human's jukebox pose then walks somewhere the
prompt is not. n = 1 trial, 5 table attempts. That is the chain OPEN-17 names
(arrival heading at the table -11.31 deg; `approach_goal` aims 10.6 deg off the
leg's own direction), now with frames instead of an ordering.

**Harness lessons that must not be re-copied** (fixed in `overnight/_harness.py`,
2026-09-06): `ab_jukebox_leg.py` walked the leg under test with `gw.walk_link`,
which publishes no leg-end frame, so it collected NO evidence about the leg it
existed to test (OPEN-1), and it reset twice a trial for want of `start_hint`.
`_harness.walk_leg_under_test()` runs ONE attempt through `follow_verified`
(retries would hide exactly the difference a leg A/B looks for), returns the
census SPLIT BY PROVENANCE, and counts recovery-fan rescues separately from
arrivals — a rescued trial travelled ~7x the leg's distance and is not evidence
the leg arrives. Pinned by `tests/harness/test_leg_under_test_collects_evidence.py`,
which asserts on CALLS through a stub rather than on source text.


---

## OPEN-8  where the other ~45s goes -- the three cuts

**FIRST, THE PROFILE IN §8(h) IS NOT A ROUTED TRIAL, and its rows do not sum.**
`overnight/profile_trial.py` profiles `reset` + `go_to_node_verified(
"portrait_room")` — two legs, not the three-node route — and it wraps
`walk_steps.walk_forward` / `turn_to`, which a LEG NEVER CALLS: legs go through
`slow_traverse.walk_leg` / `turn_to`. So leg walking appears NOWHERE in it, which
is why it shows `walk_forward: 1 call`, and its `turn_to: 6 calls` is
`_look_around_for_a_node`'s five bearings plus the turn back, not leg turning.
The wrapped rows also nest, leaving 65% of the 85.6s unattributed — which is
precisely what this ticket was asking about. **Do not quote §8(h) as a route
trial**, and fix `profile_trial.py` (wrap `slow_traverse.walk_leg`/`turn_to`,
`pose.align_lateral` and `table_prompt.at_table`, and profile the ROUTE) before
anyone reads it again.

The accounting that DOES add up, validated against `profile.json`'s own call
counts — modelling the run from the code predicts `identify` 8, `walk_forward` 1
and `ws.turn_to` 6, and the file records 8 / 1 / 6:

    reset x2 + sleep(1.2) x2          20.3s  23.7%
    leg turning, 23 steps             21.5s  25.2%  (only ~3.5s is stick push)
    stick time walking                16.2s  18.9%
    relocalise sweep, SILENT          13.9s  16.2%
    SETTLE_SEC x 23 steps              8.1s   9.4%
    captures inside walk_leg           1.7s   2.0%
    align + confirm + locate + live    4.0s   4.7%

**CUT 1 — 26 of 26 archived trials threw away the reset they had just paid
for.** Every one opens with "not at portrait_room and cannot say where this is —
reloading to a known start" IMMEDIATELY after the harness's own reset. `SPAWN =
office_corridor` is in `UNSEEDED` BY DESIGN (§7: seeding it from a dark frame
created false positives), so `locate()` can never name it; `go_to_node_verified`
called that lost, ran a 13.9s sweep with nothing to find, and reset a SECOND time
to reach the spot it was already standing on. Fixed by
`graph_walk.TRUST_RESET_SPAWN` plus a `start_hint` threaded through
`follow_verified` / `consecutive_arrivals`, spent on the first attempt only.
**~24s a trial.** Pinned by `tests/routing/test_trusted_spawn_start_hint.py`,
which asserts on CALLS not outcomes — both paths end at the same node, so only
the sweep and reset counts can tell them apart — and which now also pins that a
hint must NOT override a `locate()` that named a routable node. It did not, at
first: the hint was consumed inside the `start is None` branch, so it survived any
attempt that DID locate, and a mutant that let the caller's claim beat the
screen's evidence passed the whole file.

**CUT 2 — `read_bearing` re-asked tesseract a question it had already
answered.** The pytesseract fallback fired whenever `ocr_glyphs` returned
nothing, including when it RAN and abstained — an identical question through a
~50x slower invocation, at a median 12 subprocess calls per unreadable frame,
times four `read_heading` retries. It now runs only when `ocr_glyphs` could not
RUN. Pinned by `tests/routing/test_compass_no_duplicate_ocr.py`, which carries
the control (when the fast reader genuinely cannot run, the full ladder still
sweeps) and an anti-vacuity check that the real reader still reads every frame.
Residual risk: `ocr_glyphs` caches a per-thread `PyTessBaseAPI`, so a handle that
goes bad WITHOUT raising now returns `None`s with nothing behind it.

**CUT 3 — the scale cache is written once per geometry, not on most reads.**
Worth ~0.4s of an 85.6s trial, under 1%: the first measurement put the
read-modify-write at ~120ms, and re-measurement on a quiet machine gave a median
of **9.0ms (n=60)**, with the multi-second outliers traced to whole-process
stalls under load rather than to the I/O. A tidy-up, not a saving. It also
silently freezes the disk value at whatever the first process to see that
geometry wrote.

**REFUSED, with the measurement.** The escape ladder must NOT be truncated: 82
invocations across four logs, 19 cleared, and **14 of those 19 cleared on a rung
AFTER the first**. And `SETTLE_SEC` (13.4s of a streak trial, 4%) must NOT be
shortened, because `walk_leg` would then capture mid-motion and inflate `best`,
which is the input to `STALL_CHANGE` — a blocked step would read as walked. Four
percent is not worth breaking a gate.

**(a) IS DONE, 2026-09-06.** Every harness that resets and then navigates now
passes `start_hint=gw.SPAWN` — seven call sites. Pinned by
`tests/harness/test_overnight_start_hint.py`, an AST scan that fires only where
a reset and a navigation call share a scope, so a call with no reset is never
forced to claim one. It carries a floor so it cannot pass by scanning nothing.
`profile_trial.py` was rewritten at the same time (see below), so the
"85.6s -> ~61s" figure still describes a build nobody has made — but it now
describes the wrong quantity as well, and should not be quoted at all.


---

## OPEN-19  did the old clear corrupt the walking table

**OPEN-19 — Did the OLD `clear` corrupt §6's walking table?** Raised 2026-09-05
and deliberately left open rather than inherited.

OPEN-16 does NOT implicate that table: `overnight/walk_curve.json` is dated
2026-09-04 13:00, the release window was added 2026-09-05. But `walk_curve.py`
had the same clear-then-push-75ms-later loop then, and BEFORE the release window
`clear` never transmitted a release at all — that is the defect the window was
ADDED to fix, measured at the time as "0.4s after `clear`, the PS5 still believed
left_y = -9830" (`chiaki-patch/injectinput.cpp`). So the question is whether the
walk-back push at `walk_curve.py:49` stayed deflected into the next sample's own
`before` capture and its `walk_forward`. That is unestablished, and it is not the
same mechanism as OPEN-16.

It would inflate exactly the high-magnitude rows, and those are the strange ones:

    mag    median   spread   n
    0.60     71.2       27   3
    0.75    106.0      124   3
    0.85    352.9      476   2      <- 3.3x the row below it
    1.00    113.4       73   3      <- and then DOWN again

A response that rises 3.3x and then falls is not a shape a monotonic
stick-to-distance relation has. **`LEG_SPEED_MAX = 0.60` derives from these
numbers** (§6), so this is load-bearing, not curiosity.

**Do NOT re-measure with `walk_curve.py` until OPEN-16's fix is on the rig** — its
loop is the one live site inside the release window, so the script would corrupt
the very table it is being run to check. It is the fix's own test case. (The fix
IS on the rig as of 2026-09-05, so this no longer blocks.)

**DOWNGRADED 2026-09-05 — LOW VALUE, and the user was right to ask.**
`LEG_SPEED_MAX` (defined `graph_walk.py:1379`) has exactly ONE production
consumer, `_scaled` at `graph_walk.py:1530`, which is leg-speed scaling — and §8(h) already measured that lever: *"a 32% cut in
walking bought 5% and a worse mean."* So this table feeds one thing and that thing
is known not to pay. `walk_curve.py` also drives `left_y` ONLY (`walk_forward`
with the default `strafe=0`), so it cannot speak to the question that actually
motivated it — see OPEN-20. Answer it if it is ever cheap; do not spend rig time
on it.

An attempt on 2026-09-05 was VOID and is not in the record: run straight from a
reset, it measured the character pressed against the typewriter desk (the spawn
FACES that desk, so forward is blocked). 18 of 21 samples read displacement 0.0,
which is what a wedge looks like and also what a dead stream looks like — the
script has no way to tell those apart and reported a table of zeros as though it
were data. **If it is ever re-run, position in the office corridor first and
assert a non-zero control sample before trusting any row.**


---

## The closed loop, batch by batch (2026-09-08)

Twenty-three builds between the first working controller and the 40/40 goal run.
Each row is a rule that was tried; four measured FLAT and were reverted.

**THE CLOSED LOOP'S MEASURED STATE, 2026-09-08 02:15 (the newest line in this file; the batches below
are archived as `overnight/chain_trials_batch{10,11,12}.*`, one reader per failure in
`agent_progress/closed-loop/review/`):**

    build (commit)       trials  arrived   walk median   best streak   what changed
    e49cd3e  00:13         12     11 + 1 false   ~105 s      11        retry gate after a wall-scale fit; a dark-frame
                                                                        detector retry that fired on the street (reverted)
    f8af4d3  00:38         25     21           105.3 s       9        the end-turn rule (turn toward the dealer past the last stop)
    2220c83  01:31         25     24            86.4 s      21        a stop tie needs a different place; the look-around
                                                                        exits on a strong look; the prompt check only in the
                                                                        tail; at_table() believes 0.20 with one OCR word

    2220c83  02:16 (again)  25     23            84 s        15        repeatability: the 24/25 repeats
    a8ff495  02:59         25     22            82 s        10        a thin fit at a stop is nothing; a retry needs credible
                                                                        short-evidence; an unverified stop REWINDS and re-approaches
    a8ff495  03:40 (again)  12      9            81 s         3        stopped at the boundary: the REWIND IS A REGRESSION at the
                                                                        bar-entrance stop 129 -- taken unverified (b12-14) 11/11
                                                                        arrived; rewound (b15) 0/3, each lost at 109 re-walking
                                                                        into the NPC it had just met
    078a912  04:02         25     22            82.5 s      11        STOP_REWIND_MAX 0 (rules A/B stay); at_table() reads the
                                                                        "$50" fee token last: 0 of 7,885 route frames, 58 of 81
                                                                        prompt frames, the three b13-t5 "FAILED at the prompt"
                                                                        frames all read it -- AND IT DECIDED 2 OF THE 22 ARRIVALS
                                                                        (t9 score 0.173, t14 0.245, zero words, fee read; 17 by the
                                                                        mask, 3 by two words). The three failures, each read: all
                                                                        PINNED in the portrait room / bar entrance (a framed
                                                                        portrait, the bar-entrance corner after the 129 look's
                                                                        strafe, the photographer NPC then a wrong 191-inlier wide
                                                                        relocalisation), the ladder moving nothing
    078a912  04:51 (again)  25     22            88.9 s      13        repeatability: 22/25 REPEATS. Its three, each read: t8 the
                                                                        bar-entrance corner after the 129 look's strafe (b16 t12
                                                                        again); t9 a 29-inlier look at the top of the stairs turned
                                                                        the character into the doorway post, a jump put it in an
                                                                        unrecorded side room; t12 an aproned patron in the tables
                                                                        aisle, the ladder freed it and STUCK fired on the row the
                                                                        fit read 176 at scale 0.973 (reached() needs 1.0)
    078a912  05:35 (again)  25     20            78.7 s       7        the third run of this build: five failures, a NEW cluster --
                                                                        three losses on the STAIRS (t8 the door stop turned short
                                                                        into a side room, t14/t22 thin fits that never advance at
                                                                        39-46; four stairs losses in 40 trials after ~100 without)
                                                                        and two more identical 129-look failures (t10, t20). The
                                                                        fastest walk on record, t3 at 62.7 s: nothing went wrong.
    32e4400  06:15         25     23            80.2 s      10        patch43+43b, a LOST RESCUE: at lost >= LOST_MAX, once per
                                                                        walk, back out 1.0 s and look 0/-25/+25 over the WHOLE chain
                                                                        behind the last credible k at the strong gate (165); fires
                                                                        only where the walk was already lost, so every firing is a
                                                                        measurement and arrivals cost nothing. patch44 (STOP_LOOK_YAW:
                                                                        a looked stop turns instead of strafing; census: after the
                                                                        129 strafe the next fit still reads -300 px on 93 of 96
                                                                        arrivals) is in build for an A/B. RESULT: 23/25, the night's
                                                                        best count (= b13); the rescue fired twice, found nothing
                                                                        twice (t11 in an unmapped storage room through a WRONG DOOR
                                                                        in the office corridor; t17 against an NPC now standing at
                                                                        the top of the stairs), cost nothing. The office losses of
                                                                        b17-b19 are wanderers: an NPC at the stairs, doors that open
                                                                        when a blind push hits them.
    a411fe4  07:07   A/B 20  off 9/10    78.3 s                        patch44 STOP_LOOK_YAW, `--arms off,on --flag STOP_LOOK_YAW`:
             (10/arm)        on  9/10    79.4 s                        at a stop verified by the look-around, TURN by px/PX_PER_DEG
                                                                        (the end turn's formula, capped at END_TURN_MAX_DEG) and
                                                                        carry the offset to the next stop, instead of the capped
                                                                        0.3 s strafe. Arrival a tie (Fisher 1.0; each loss a
                                                                        wanderer). THE INSTRUMENT DECIDED IT: the first credible
                                                                        fit's dx after a looked 129 stop, off arm median -352
                                                                        [-383..-264] on 5 of 5, on arm +72 [-96..+150] on 5 of 5
                                                                        (yaws -12.6..-22.9 deg) -- no overlap. SHIPPED ON (patch45).
    da361ef  07:43         25     21            81.4 s      11        patch45: STOP_LOOK_YAW = True, plain 25 -- the first full
                                                                        batch with the rescue AND the yaw. 18 yaw firings; THE
                                                                        RESCUE'S FIRST WIN (t18: lost at 129, backed out, saw the
                                                                        portrait room at 180 inliers, re-approached, arrived). Four
                                                                        losses: the stairs NPC (t1), the blind stretch past 129
                                                                        (t20), and TWO post-yaw over-corrections (t13, t17): when
                                                                        the look's fit lands 2-3 waypoints AHEAD of the stop the
                                                                        un-yaw formula over-turns (fits at 128-130: 12/13 arrived,
                                                                        residual |~90| px; at 131-132: 2/4, residual +150..+230).
                                                                        Yaw at the stairs stop: 3 of 4 arrived. The morning's first
                                                                        candidate: yaw only on a fit at the stop's own index +-1
    da361ef  08:28 (again)  25     22            79.2 s      13        repeatability of the rescue + yaw build: 22/25. 16 yaw
                                                                        firings; the rescue fired 5 times and WON TWICE (t15, t18:
                                                                        the estimate at 166, the +25 look found the portrait room
                                                                        at 118/121 on 171/188 inliers, both re-walked and arrived,
                                                                        t18 at 176.5 s against the 180 s walk cap). Losses: past
                                                                        129 (t6), the office stretch twice (t20, t23, lost at 88
                                                                        after the corridor). Rescue tally over three batches: 14
                                                                        firings, 3 believed, 3 arrived
    da361ef  09:12 (third)  25     23            79.8 s      21        the same build again: STREAK 21, TYING THE RECORD (b12).
                                                                        Losses: t3 the office stretch; t25 the fourth fit-ahead
                                                                        yaw over-correction (a look matched waypoint 132, yaw
                                                                        -25.8, the next fits +126/+275, blind, lost) -- 3 of 7 such
                                                                        firings lost, the patch46 gate's case
    da361ef  09:57 (4th)    12      9            92.0 s       4        a short batch so the next boundary met patch46. Losses: the
                                                                        stairs NPC (t5); 129 taken unverified then fits with dx
                                                                        +640 the strafes could not close (t9); a +29 deg yaw at the
                                                                        196 stop then the end without the prompt (t12)
    ef717b1  10:19   A/B     off 7/10    89 s                          patch46 STOP_YAW_NEAR_FIT_ONLY, `--arms off,on --flag
             (2 launches)    on  7/9     91 s                          STOP_YAW_NEAR_FIT_ONLY`: the yaw only when the look fits the
                                                                        stop's index +-1, else the old strafe (fits 2-3 ahead
                                                                        over-turned and lost 3 of 7). INCONCLUSIVE: the gate fired
                                                                        twice in nine on-arm trials (1 arrived, 1 lost to the stairs
                                                                        NPC); the off arm yawed on a far fit twice (both arrived).
                                                                        Ships OFF. 20 trial numbers were burnt by the game window
                                                                        going off screen (the user's Space switches) -> patch48: the
                                                                        harness waits up to 120 s and re-runs the number twice
    0226268  11:06   A/B     off 9/10                                  patch47 DOOR_STOP_EXTRA_PUSH, `--arms off,on --flag
             (10/arm)        on 10/10                                  DOOR_STOP_EXTRA_PUSH`: one more push toward the office door
                                                                        before the stairs turn -- THE USER'S OBSERVATION FROM THE
                                                                        STREAM. The instrument decided it: the 39 stop verified
                                                                        HEAD-ON on 10 of 10 on-arm trials (66 inliers, fit scale
                                                                        1.04 [1.01..1.11]) against looked 3 / aligned 6 / unverified
                                                                        1 (the loss) on the off arm (38 inliers, scale 0.96 with a
                                                                        0.80 tail). SHIPPED ON (patch50). Also landed: patch48, the
                                                                        harness waits for a missing game window and re-runs the
                                                                        trial number instead of burning it
    a780ed6  11:46   12 + 8   12/12 + 7/8   83.7 s / 86.1 s   12      the door step ON, plain 25 in two parts: part 1 stopped at 12
                                                                        by the user's VPN reconnecting (chiaki: "Takion failed to send
                                                                        data packet"; trials 13-14 INVALID on the dead stream, not
                                                                        counted), part 2 stopped at 8 by the user's restart. 19 of 20
                                                                        valid; the one loss t1 of part 2: a +10.6 deg STOP YAW at the
                                                                        LAST stop (196, the look fit TWO ahead at 198), then the final
                                                                        approach never found the prompt (patch51's case, below)
    2d0f4e0  12:25          -     not run yet                          patch51 STOP_YAW_SKIP_LAST_STOP = True: no stop yaw at the plan's
                                                                        LAST turn-only stop -- nothing clears it after that, so it rides
                                                                        the whole final approach under the end turn. Census of the 196
                                                                        stop over 266 walks: head-on or strafed 225 arrived / 1 ended
                                                                        without the prompt / 1 failed; looked and YAWED (6) 4 arrived /
                                                                        2 ended at 204 without the prompt. The strafe runs there instead
                                                                        (marker yaw_skipped.reason = "last stop"); 4 mutants caught.
                                                                        Landed at the restart boundary; THE NEXT PLAIN 25 MEASURES IT
    2d0f4e0  12:55   17 + 1i  17/17         76 s        17      patch51 measured as far as it can be: the last stop verified
                                                                        HEAD-ON on every trial, so the rule never fired (it touches
                                                                        ~1 walk in 40); the batch shows it broke nothing. Stopped at
                                                                        18 for the user's settle measurement; trial 17 INVALID
                                                                        (Mission Control took the window) and re-run by patch48
    d36ba83  15:25   A/B      off 8/10                                  patch55 BAR_STOP_EARLY_TURN, one fewer push before the 296-deg
             (10/arm)         on  8/10                                  jukebox turn -- the user's "they walked too close to the bar".
                                                                        Tie, and the PRE-REGISTERED instrument (fit scale at 135-149,
                                                                        must fall toward 1.0) went 2.67 -> 2.71, UP. Ships OFF. The
                                                                        fourteenth navigation change measured flat -> GRAVEYARD
    2c8fea7  18:14   40       40/40         76 s        40      THE GOAL. --attempts 2 (patch52, the reload the user chose:
                                                                        "reload and report both numbers every run"). Every trial
                                                                        passed the independent at_table re-check; FIRST-WALK 39/40
                                                                        (97.5%); one reload (t13, lost at the jukebox turn with the
                                                                        blind-then-lost signature, recovered). By the strict no-reload
                                                                        reading the run from t14 is 27, which also clears 25. Sheet:
                                                                        overnight/goal_batch_arrivals.jpg. Blind-look (patch56) and
                                                                        pitch correction (patch57) landed on this build but OFF
