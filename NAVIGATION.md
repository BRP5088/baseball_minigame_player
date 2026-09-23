# The map, the localiser and navigation (§7, §8)

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

---

## §7 The map and the localiser

`world_map.json`: **6 nodes, 5 one-way legs**, built by `build_world_map.py`
from `route3_steps.json` plus a 712-frame recorded walk.

    office_corridor -> office_door -> portrait_room -> bar_pool_room
                    -> bar_jukebox -> dealer_table          23.00s total

- **A leg carries STEPS, not just a duration.** `connect()` stores
  `{"cost", "steps": [{"bearing","dur","speed"}]}`. A bare duration is not
  executable. Curves keep every sub-step; averaging a 26-degree bend into one
  heading walks into a wall.
- **Legs are ONE-WAY by default.** One trip is evidence about one direction.
  Fabricating the reverse plans an unwalked climb back up a drop.
- `WorldMap.load()` treats **links as mandatory, trail as optional** — it had
  this backwards, so a map with NO EDGES loaded as valid and then reported every
  destination unreachable.
- `route_reason()` separates the four causes `route()` collapses into one None.
- chiaki releases injected input after 5s, so an unchunked leg caps at ~4.5s.

### The localiser

`places.identify()` is ORB-based: `MIN_MATCHES = 140`, `MIN_RATIO = 1.35`
(`places.py:284-285`). When the character genuinely stands at a node it names it
with a **2.6-5.3x margin** (leave-one-out: 249-698 matches). Held-out check
after the node-set rebuild: 18 correct / 6 abstain / 0 wrong, every abstention
±1s from a node.

**Do not lower these thresholds.** The failures are POSITION failures, not
recognition failures.

- **`dealer_table` is a POSE, not a place.** Its identify() margin is the prompt
  TEXT. Confirm arrival with `table_prompt.at_table()`, never `identify()`.
  Enforced in `confirm()` AND, since 2026-09-07, in `locate()` — it was not, and
  OPEN-14 trial 6 was scored an arrival on `identify()` naming the table at
  194/1.53 with no prompt (`tests/routing/test_locate_goal_is_a_pose.py`).
- `office_corridor` and `office_door` measure 0.726 alike — the same corridor 5s
  apart. They stay separate nodes because the walk between them is real, and
  `world_map.json` records the pair under `confusable`.
- **Do not seed a place from a dark frame.** Seeding `office_door` instantly
  created false positives. `build_world_map.SEED_PLACES` excludes both office
  nodes deliberately; they are reached by walking, not recognition.
- `identify_edges` (the old correlation path) was **deleted 2026-09-17** with
  zero callers, taking `MIN_SCORE`, `MIN_MARGIN` and `HEADING_WINDOW_DEG` with
  it. It carried the 0.906 dark-frame trap and the reason is worth keeping:
  `descriptor()` divides by the vector norm, so a near-featureless frame becomes
  mostly the shared vignette and an upstairs office door scored 0.906 against
  `beside_dealer_table` — higher than any genuine match. **No score threshold
  fixes that**, which is why the ORB path replaced it. ORB is immune by
  construction: crossCheck matching cannot return more pairs than the smaller
  descriptor set, so a 10-keypoint frame scores 1. `descriptor()`, `load_places()`
  and `frame_heading()` are NOT dead and were not touched — they call each other
  and `load_places` has a test caller, which a plan of mine listed as deletable.
  The heading-filter measurement that died with `identify_edges` is preserved in
  `places.identify()`'s docstring.

### Admitting a new place

`map_propose.py --admit` gates on non-disruption, discrimination, and
recoverability. A deliberate mapping run (160 frames, 17 stops, 15 clusters)
was **rejected 15 of 15**, all on recoverability — no candidate could name any
frame of the failure population it claimed to fix.

Two traps found there, both worth keeping:

- **A self-match trap:** left in the pool, failure frames cluster as singletons
  and "rescue" themselves, reporting the problem solved. Hold them out.
- **The break/rescue test alone is degenerate.** The same frame scores ZERO
  breaks filed under every existing room, while filed under `dealer_table` it
  would newly name three bar-counter frames `dealer_table` — three confident
  wrong answers, scored "safe".

`identify_orb` scores a room by its BEST SINGLE reference (`places.py:288`), so
pooling many frames into one node does not raise its score.

**The bar area is two-thirds UNMAPPED, measured not inferred.** Of 160 frames
from that run, 100 were RICH AND UNNAMED: median 1500 keypoints (the ORB cap —
maximum possible detail) with a median best match of **128 against MIN_MATCHES
140**. Every one is JUST under the bar. So walking a metre off a known node goes
blind at once, and that is a mapping gap, not a detector failure.

---

## §8 Navigation: current measured state

**This is the only section that reports status.**

### THE CLOSED LOOP REPLACED DEAD RECKONING ON 2026-09-07, AT THE USER'S REQUEST

**The user had asked for this design earlier and an earlier session built dead
reckoning instead; that cost days. When the user proposes an architecture,
build a spike of it before continuing the current plan.**

Dead reckoning (§8(a) below: replay recorded bearing/duration, look only at a
leg's end) sat at 5/10 per route through thirteen measured changes. The closed
loop LOOKS AFTER EVERY PUSH and takes position from the screen, never from the
stick. Built in one evening: `chain.py` (the sensor), `chain_record.py` (the
recorder), `chain_walk.py` (the controller), `overnight/chain_trials.py` (the
harness), `tools/chain_validate.py`, `tools/turn_review.py`; spec and build
notes in `agent_progress/closed-loop/`. Three Opus builders, three skeptics,
every module refuted at least once and fixed; 74 controller tests, every fix
mutation-tested.

**The chain is the user's own drive** (`chains/route_user_1853`, 205 frames at
0.25 s, stick logged through pygame, compass on 94% of frames, stopped by
`at_table()` at the prompt). A chain is compiled into a PLAN: push targets one
push apart by the recorded stick's distance, and each stationary run collapsed
to ONE turn-only stop. The sensor (`Chain.locate`) matches a frame against a
window of waypoints around the last known index, ORB + Hamming + RANSAC,
`dx` and scale from the fit. Offline on the drive's own held-out frames, closed
hint: 82% within one waypoint, 96% within two, 4% abstain.

**Measured, batch 4 (2026-09-07 19:47, the first with all six fixes below but
the last): 8/10 ARRIVED at 90-121 s reset-to-prompt.** Dead reckoning's
arrivals took 240-340 s. Batches 1-3 were stopped early because each failure
was one spot with one fix (`overnight/chain_trials_batch{1..4}.*`). The 25 is
running as this is written.

**Six controller lessons, each from a trial's frames and each pinned by a test
and mutants (`git log -- chain_walk.py`):**

1. Advance the estimate to the TARGET it pushed toward, never past it. Trial 1
   ran three waypoints ahead per push on 13-28-inlier fits and strafed into
   the wall on junk offsets.
2. Push targets spaced by the recorded stick's distance, not per frame; the
   user's slow stick put four frames in one push and the estimate fell behind.
3. A blind sensor (featureless door panel, dark wall) dead-reckons the target
   for `BLIND_MAX` pushes before misses count; a fix under `FIX_MIN_INLIERS`
   (29, the chain's own true-position p05) neither advances nor steers; a
   thin fit (`WEAK_MIN_INLIERS` 15) advances but does not restore the budget.
4. **Verify every turn stop against its own frame** (the user's call from the
   stream: "the player didn't move far enough towards the door"). A frame
   that fits an EARLIER waypoint means short: turn back, push once more,
   retry (`TURN_RETRY_MAX` 3). A frame that fits NOTHING is occluded (an NPC
   in the face) or already passed: turn and go on, no retry pushes.
5. A wide forward search (`WIDE_AHEAD` 60, believed at `STRONG_MIN_INLIERS`
   120 as first written -- **it ships at 165**, raised by the audit round below
   to clear the wrong-place MAXIMUM rather than the p95 of 117) from the FIRST blind push and at
   unverified stops. At the office exit the shop facade across the street
   looks the same from the doorway and from halfway across; the loop crossed
   in two pushes and stood at the portraits while the estimate said
   "doorway". A margin over the runner-up was tried first and was wrong: in a
   window of adjacent frames the runner-up is the neighbour.
6. `LOST_MAX` (9 as first written, **13 as it ships**): that many iterations
   with nothing credible after the budget ends
   the walk at once (80 s) instead of burning the 400 s cap (trial 3 pushed
   into a wall 312 times).

**Review rule (the user's):** look at the TURNS first. `tools/turn_review.py
<shots dir> <journal>` tiles the live frame at every stop beside the chain's
frame there; a wrong scene after a turn means the character stopped short.
Pair a journal with its shots by time.

**Known hazards at 97%:** an NPC standing in the exit door (trial 1 stalled
six pushes there before a jump cleared it); the user's camera pitch on the
stairs (every fit there carries a 200-300 px vertical offset the loop ignores).

**THE AUDIT ROUND (2026-09-07 21:00, commit 3df1727).** After eight rapid
patches the controller was audited by two independent skeptics while the
console ran; every confirmed finding was a guard that could not fire or a
rule that fired on the wrong measurement, the project's signature shape:
the plan pointer never rewound after a regression (the target then sat past
the window forever); a thin fit advanced the estimate to the target without
naming it; a stop verified only when its fit was BADLY misaligned; the
look-around's frames overwrote the frame the verdict was made on; and the
gates 29/120 sat inside the overlap of the census they cited, which had been
built on a 41-waypoint chain while the live run loads 205. All fixed and
mutation-tested. **The live-frame census** (`tools/live_gate_census.py` ->
`overnight/census/live_gate_census.json`, 1,858 in-window fits, 468 far
matches): true fits from arriving trials median 98 inliers, p25 49; wrong-
place matches p95 126, MAX 164. No count separates them; the sequence window
does the work, and only the wide-search gate was moved (to 165, above the
wrong-place maximum). **The stop table** (`agent_progress/closed-loop/audit/
stop_table.md`, 43 journals): the bar-entrance stop at chain 129 verifies 58%
of the time and a trial that takes it unverified arrives 1 in 14; stop 166
unverified arrives 0 in 6. That stop is the lever. **Arrival review** (13
arrivals, frame by frame): 12 minor detours, 1 wandered-and-lucky, 0 off the
route; every detour was a wedge at a real obstacle (the exit-door threshold,
the bartender's counter with two NPCs and two steins). **Failure review** (10
failures): turn-taken-short 5, NPC in view 2, blind into an obstacle, estimate
ran ahead, lateral displacement 1 each. Measured rates by version: batch 4
8/10, batch 5e 6/14 (three rules shipped in between, one of them a
regression corrected in 5e); the audit round runs as this is written.


**THE CLOSED LOOP REACHED THE GOAL: 40 TRIALS, 40 ARRIVALS, median 76 s (2026-09-08
18:14, build 2c8fea7).** Every trial passed the independent `at_table` re-check;
FIRST-WALK 39/40 (97.5%), with one reload (t13, lost at the jukebox turn, recovered).
By the strict no-reload reading the run from t14 is 27, which also clears the 25
requirement. Sheet: `overnight/goal_batch_arrivals.jpg`. `--attempts 2` is the reload
the user chose: *"reload and report both numbers every run"*. Blind-look (patch56) and
pitch correction (patch57) are in that build but OFF.

**The twenty-three intermediate batches are in `CLOSED.md`**, one row per build, with
what changed and what it cost. Read them before proposing a navigation rule -- every
row is a rule that was tried, and four of them were measured FLAT and reverted. The
rules that survived are the six controller lessons above plus the A/B'd patches
(STOP_LOOK_YAW on, DOOR_STOP_EXTRA_PUSH on, STOP_YAW_NEAR_FIT_ONLY off,
BAR_STOP_EARLY_TURN off -> GRAVEYARD).

Twenty true arrivals in a row across the first two, twenty-one inside the third. The failures that remain
are one shape: blind pushes into geometry after a verified stop, then the next stop accepted UNVERIFIED
with the estimate jumped ahead (unverified stops arrive 1 in 14 and 0 in 6 in the audit's table); the
rewind-on-unverified rule (`drafts/pending_after_ab/apply_patch41.py`) is in verification. Every rule
above came from a reader's frames and is pinned by tests and caught mutants; `HANDOFF_NOW.md` carries the
queue and the censuses behind each constant.

### (a) Where the route stands

**RE-MEASURED 2026-09-07, AFTER the leg-1 revert. Arrival did NOT move.**

    outcomes [F,T,T,F,T,F,F,T,F,T]   arrived 5/10   BEST STREAK 2
    243.7s per trial (was 338s), 0 invalid
    failures by class, ALL FIVE from admissible leg-end frames:
        wedged 4, overshot 1, fallback-frame 0

So the leg-1 flags were a REGRESSION I introduced and reverting them restored
the prior state -- it did not improve on it. The start node is 10/10 again and a
trial is 28% cheaper, but the route is where it was. Necessary repair, not
progress toward 25.

**This is the first route census taken entirely from admissible frames**
(`failures_by_kind_leg_end` 5, `failures_from_fallback_frame` 0), which OPEN-1
asked for. At n=5 it says nothing firm about the mix; note only that it is
WEDGED-heavy, where the earlier single-node census at `bar_pool_room` was
8/10 OVERSHOT.

At 5/10 per route, P(25 consecutive) is ~3e-8. Retry depth (OPEN-5) is the only
lever with the leverage to close that.

The pre-revert figures below are kept because the profile in (h) refers to them.



Route `portrait_room -> bar_pool_room -> bar_jukebox` from a reset spawn, using
`follow_verified` (which never walks a leg from an unconfirmed pose):

    outcomes [T,T,T,F,F,T,T,F,T,F]    arrived 6/10    BEST STREAK 3
    338s per trial

The requirement is **25 consecutive**. That needs ~97-99% per route.

### (b) Per-leg arrival (n=76 leg executions, measured over that 10-trial run, before several later fixes)

    office_door -> portrait_room      20/20   1.000
    portrait_room -> bar_pool_room    14/21   0.667
    bar_pool_room -> bar_jukebox       6/15   0.400
    Fisher, leg 1 vs leg 3: p = 7.1e-05

Not diffuse — two bad legs, and the jukebox leg is the worst. **Tag any reuse of
this table with its n and date**; it predates the button fix.

### (c) Retrying is the only lever that reaches the target

**MEASURED 2026-09-07 (OPEN-5): `attempts=9` arrived 9/9, `attempts=3` 5/10,
Fisher p = 0.0325, and the deep arm's median is LOWER (308s vs 381s).** Goal
node `bar_jukebox` — one leg BEFORE the dealer table, whose arrival is a
different check (`at_table()`). Both records below.

**`go_to_node_verified` arrives 10/10 (OPEN-4, 2026-09-06).**
`overnight/measure_primitive.py`, n=10, target `bar_pool_room`, attempts=3:
10 valid, 0 invalid, 10 arrived, **median 52.9s**, and `locate()` agreed with the
primitive on every trial (`overnight/primitive_open4.json`). Config as shipped:
`TRUST_RESET_SPAWN`, `RECOVER_MISSED`, `NULL_YAW_BEFORE_ALIGN` all True,
`REFERENCE_POSE` "bot". The ~55% figure is a SINGLE WALK; the retrying primitive
is what everything downstream should use. It is one leg from a reset, in one
session — it does not license quoting 100% for a route.

**`attempts=9` arrives 9/9 against `attempts=3` at 5/10 (OPEN-5, 2026-09-07).**
Interleaved, 10 trials an arm, TIMEOUT 900 so the deep arm could not be censored,
`start_hint=SPAWN`, scored on `follow_verified` confirming the goal
(`overnight/ab_attempts.py`, `overnight/ab_attempts.json`):

    attempts_9   9/9 valid arrived    median 308s   [83..780]    1 invalid
    attempts_3   5/10 arrived         median 381s   [77..403]    0 invalid
    Fisher exact p = 0.0325

"Arrived" here is the localiser naming `bar_jukebox` — one leg BEFORE the table —
at 218-1108 matches / ratio 1.74-11.66, with a photograph written at that moment:
14 of them, 9 + 5 exactly (`overnight/open5_arrivals.jpg`), and 5
`fail_bar_jukebox` frames for the 5 misses. **It is NOT the table and NOT the
prompt.** All five `attempts_3` misses died on the jukebox leg at depth 2/3. The
deep arm's median is LOWER because arriving is cheaper than exhausting three
attempts and reloading. The one invalid trial was a reset that could not open
the pause menu at 30.7s, diagnosed live by the transport probe as game state
(both transports alive) and recorded INVALID, never a failure. Nothing reached
the 900s ceiling. **Shipping attempts=9 changes a default and is the user's
call; the constant is untouched.** The streak at attempts=9 with the table leg
and `at_table()` as the final check is in flight — OPEN-14.

    follow() once, single attempt         ~55% per node
    go_to_node_verified (3 attempts)      10/10, median 52.9s  (OPEN-4, n=10)

Retrying costs TIME, not probability. At the measured per-attempt 0.40 for the
jukebox leg: attempts=3 gives a node rate of 0.784; attempts=7, 0.972;
attempts=9, 0.990. An earlier claim that "0.55^3 = 17%, so 25 consecutive is
arithmetically unreachable" was WRONG — that arithmetic applies to a
single-attempt walk, not to the retrying primitive.

### (d) The spawn is deterministic

Bearing 86.9/87/87 (E) on every reset. Drift accumulates after that.

### (e) `follow()`'s "reached" is a ROUTING CLAIM, not evidence of position

Since abstentions became advisory it carries on past nodes it could not confirm,
so it can report reaching `bar_jukebox` while the character stands in a
stairwell — which happened, and sent a scouting pass to photograph the wrong
room. Anything that must actually BE somewhere must use
`go_to_node_verified()`, which believes only `locate()`.

Treating abstention as ADVISORY was itself measured good: mean progress went
from node 1.7 to 4.0 of 5, and over every run **10 mid-route confirmations
failed and ALL TEN were abstentions** — `identify()` never once named a wrong
room.

### (f) Failure signatures

`failure_kind.classify(img, target, route)` returns WEDGED / OVERSHOT /
REGRESSED / UNPLACED. `WEDGED_MAX_KEYPOINTS = 50` sits between two measured
populations: a frame pressed against geometry holds 9-11 keypoints, the next
lowest non-wedged frame holds 744, and a genuine arrival 339-1500.

**AND IT DOES NOT RUN ON THE PRODUCTION PATH. Verified 2026-09-17, and this
section read as though it did.** `failure_kind.classify` has exactly ONE call
site, `graph_walk.py:2260`, which is inside `follow_verified` (2106-2296).
Production routing does not go through `follow_verified`: `go_now.py:46` calls
`graph_walk.go_to_table`, and go_to_table calls plain `follow()` at :328 and
:348. So a production trial produces NO class census at all, and every "report
arrival by class" instruction below describes the A/B harnesses
(`overnight/_harness.py`, `ab_attempts.py`, `profile_trial.py`) and nothing else.

`leg_reliability.record()` is in the same position — only inside
`follow_verified`, and additionally behind `RECORD_RELIABILITY = False`.

**THE OPEN QUESTION IS WHETHER PRODUCTION SHOULD USE follow_verified, AND IT IS
NOT A DOCUMENTATION FIX.** It is a NAVIGATION CHANGE: §9 records thirteen
well-motivated navigation changes that moved no number, and GRAVEYARD.md is
required reading before another. It needs an interleaved live A/B, 10 trials an
arm (§10.3), which needs the console and the user. Flipping it unattended would
be exactly the shape this file spends §9 warning about. Until then this section
describes a harness-only instrument, and says so.

**Report arrival BY CLASS, never just overall** -- in the harnesses, where the
census exists. Arrival averages several different failures, so a change that
eliminates an entire class moves the overall rate by roughly a third of it —
invisible at n=10. That is a leading explanation for why so many well-motivated
changes measured flat.

**But the class distribution itself is currently unsupported** — see OPEN-1. The
eight frames it was derived from describe the recovery fan, not the leg.

### (g) The escape ladder skips GEOMETRY

Keypoint count discriminates where scene-change could not: pressed into
furniture reads 9-11, open space 744-1500, and `GEOMETRY_MAX_KEYPOINTS = 50`
sits in the gap. The ladder has NEVER cleared a geometry wedge — every archived
occurrence reads `wait -> jump -> jump -> slip right -> slip left`, each
displacing 0.0px. `SKIP_LADDER_ON_GEOMETRY` is on; it is conservative by
construction, so an NPC blocking a visible passage still gets the full ladder.

**Cross (X) IS the jump button** — four presses spiked 10.1-12.5 against a 4.67
idle baseline. An earlier test concluded there was no jump and was WRONG: it ran
with the character against a wall, where a jump changes almost nothing.

**The wall-vs-NPC test was removed, not fixed.** "A wall does not move" needs a
threshold, and standing perfectly still already produces scene changes of
0.91-6.41 (median 4.09), so the 2.0 threshold sat under the noise floor. Against
real blockers the escape outcomes were `None, None, jump, None, None, None,
wait, jump` — jumping works sometimes and is worth trying FIRST, because it
moves nothing sideways in a passage with stools on one side and a wall on the
other.

### (h) Where a trial's time actually goes

**The 85.6s profile this section used to quote is withdrawn** (OPEN-8). It
profiled `reset` plus two legs rather than the route, it wrapped
`walk_steps.walk_forward` / `turn_to`, which a LEG NEVER CALLS (legs go through
`slow_traverse`), and it summed NESTED timers, so its "65% unaccounted" was an
artefact of the arithmetic. `overnight/profile_trial.py` now profiles the route
through `follow_verified` and records INCLUSIVE and EXCLUSIVE seconds; **read
the exclusive column** (`tests/harness/test_profile_exclusive_time.py`).

The accounting that DOES add up — modelled from the code and validated against
the old profile's own call counts (8 / 1 / 6 predicted, 8 / 1 / 6 recorded):

    reset x2 + sleep(1.2) x2          20.3s  23.7%   cut: start_hint, ~24s a trial
    leg turning, 23 steps             21.5s  25.2%   only ~3.5s of it is stick push
    stick time walking                16.2s  18.9%
    relocalise sweep, SILENT          13.9s  16.2%   cut: start_hint
    SETTLE_SEC x 23 steps              8.1s   9.4%   do NOT shorten (OPEN-8)
    captures inside walk_leg           1.7s   2.0%
    align + confirm + locate + live    4.0s   4.7%

About 26% of a 338s streak trial (~89s) is still unexplained with every modelled
component at its floor; the recovery fan (~79s each, ~33% of the clock when it
fires) is OPEN-7's. The largest single cut measured: `read_bearing` fell from
**261ms to 31ms (8.4x)** once `tesserocr` replaced shelling out to the binary,
~12s off a trial, correctness verified on 208 glyph crops that match EXACTLY.
`ocr_glyphs._api()` keeps a per-thread `PyTessBaseAPI` (134ms first call, 23ms
steady), so there is no spin-up left to remove and a daemon would add moving
parts for nothing.

**The lesson: profile before optimising.** Leg speed was the intuitive target
and was nearly worthless — walking is only ~20s of a trial, so a 32% cut in
walking bought 5% and a worse mean.

### (i) Why the jukebox leg cannot be fixed with a better constant

The starting pose inside `bar_pool_room` varies run to run, so no single
(bearing, duration) is right from every start. A direct search found 337.1 deg
for 0.80s reaching `bar_jukebox` where the recorded leg walked into furniture —
but putting it in the map and running it live still did not arrive, because that
run reached `bar_pool_room` off-pose and `align_lateral` reported "blocked
sideways, cannot correct from here".

**Caveat added 2026-09-04: the magnitude of that variance is not established.**
The "~150px" figure traces to ONE stalled alignment loop (`pose.py:233`), is
censored (the loop returns before logging when |dx| <= 35), and predates the
button fix. A later attempt to refute it using pairwise spread between failure
frames was invalid — it compared a SPREAD to a BIAS, and the frames were
captured immediately after the aligner drove the character onto that very
reference, making tight clustering circular. **Both the claim and its
refutation are unsupported.** See OPEN-1.

### (j) Pose alignment

`places.identify()` answers "which ROOM", but rooms are large and a
dead-reckoned leg assumes a POINT. `pose.align_lateral()` closes that on the one
axis that can be measured. `pose.offset()` fits a partial affine with RANSAC and
keeps the DIRECTION:

    strafe right  dx = -126.0   forward  dx =  +5.5  dy =  -8.6
    strafe left   dx = +132.7   back     dx = -14.3  dy = -24.5

Forward/back barely register — monocular depth is weak — so only the lateral
axis is corrected. **Measured: 214px -> 25px, 182px -> 27px, 360px -> 7px.**

**Its divergence guard never fired until 2026-09-04.** It read
`abs(dx) > last * 1.5`, but `last` was assigned `abs(dx)` twenty-five lines
above, so the test was `abs(dx) > abs(dx) * 1.5` — always False. It exists to
stop the oscillation in the first bullet below, and it was not stopping it.
Because that branch owned the only "diverging" log line, its absence from every
log read as "it never diverged". A bound that cannot be reached, inside a branch
that writes nothing: two catalogue items in one place. Every step now logs its
dx and the previous one, which is what would have exposed it.

Three tuning facts that cost measurements:

- The OPEN-LOOP gain (126px per 0.30 x 0.35s) is WRONG for control, because that
  push accelerated from standstill. Closed-loop is ~2400 px per
  unit-magnitude-second; at the open-loop figure the loop OSCILLATED with
  growing amplitude (+175 -> -201 -> +211 -> -215).
- A push under ~0.10s does not move the character at all, so the loop stalls
  issuing 0.03s corrections. Below ~36px is as close as the stick gets.
- Bailing out when the damped push falls under that floor is WORSE (it stopped
  at 84-116px). Use the minimum push and let the divergence check catch
  overshoot.

**Where it does NOT work:** at `bar_pool_room` the character is against the
wall/stools and strafing does nothing — four corrections left dx at -136, -179,
-156, -158. That is now detected and reported rather than retried.

**`pose.displacement()` is a MIXED statistic, not a pose distance.** It fits an
affine and then discards it, returning the median inlier pixel distance — so
yaw, depth and translation all enter undifferentiated. Measured scale response:
1.10 -> 33px, 1.20 -> 65px, 1.43 -> 104px. Do not read it as translation.

### (k) A note the user made that is still unexplained

*"When you make the turn, you actually walk right out of the bar."* Observed
directly on the stream, first day. **It has now been captured**:
`test_fixtures/leg_failures/overshot_outdoors_1788718155150.jpg` shows the
character on a CITY STREET — a truck, a lamppost, shop signs — at the end of a
leg that should have ended in the bar's pool room, written by the admissible
leg-end path (OPEN-1) during the 2026-09-06 census. What is established is that
a leg into the bar can end outdoors and off the mapped route. Whether it is the
same event the user saw, and the mechanism, are NOT established: the 90-degree
compass flip that would explain it cannot be produced offline at 1920x1080 (the
compass correction below §10), and OPEN-3's closure removed the other candidate.
Still unexplained; no longer uncaptured.

---

## at_table() WAS FIRING WITH NO PROMPT ON SCREEN (fixed 2026-09-05)

`table_prompt.MATCH_MIN` was **0.15**, which sits BELOW the highest measured
negative. Measured over all 3262 archived demo frames:

    score < 0.15    1817 frames   the bulk of the route
    0.15 - 0.25       52 frames   INCLUDES A CONFIRMED FALSE POSITIVE
    0.25 - 0.40      366 frames   genuine prompts start here
    0.40 - 0.60       28 frames   trough
    0.60 +           924 frames   clear prompts

The negative anchor was eyeballed and then confirmed by the user:
`demos/walk2_pauses_20260828_044514/f_0049.22.jpg` scores 0.1757 with the QUEST
LOG open — its text supplies both the ink and the stroke correlation — and the
player is not close enough for the game to offer the prompt at all. The positive
anchor, `demos/spawn_to_table_20260827_212516/f_0054.32.jpg` at 0.3503, shows
"Baseball Cards [] Play ($50)" plainly. **MATCH_MIN = 0.25** sits between them.

**WHY THIS MATTERS BEYOND ONE DETECTOR.** `at_table()` is the authority for
"arrived at the dealer table" — §7 says `dealer_table` is a POSE and must never
be confirmed by `identify()` — AND it gates the Square press that spends $50. So
a false positive both records an arrival that did not happen and can commit
money at nothing.

**Treat any arrival figure measured THROUGH at_table() before 2026-09-05 as
possibly inflated.** The route streak numbers in §8 are not affected (they score
`portrait_room -> bar_pool_room -> bar_jukebox`, none of which uses at_table),
but anything quoting arrival at `dealer_table` is.

Note `INK_MIN` cannot save this: the false-positive frame scores ink 0.027,
comfortably above the 0.024 gate. The score is doing the discrimination.
Pinned by `tests/routing/test_at_table_threshold.py` against both real frames.

**AND THE INK GATE IS GONE FROM THE VERDICT (2026-09-07).** It had never rejected
a negative the correlation did not already reject — every negative on disk tops
out at 0.176 against `MATCH_MIN` 0.25, Wanda's prompt (its stated purpose)
scores 0.10 — and it rejected 21 route frames with the prompt plainly on screen
(all 21 adjudicated by eye), the recorded arm's own arrival in the goal-leg A/B
(score 0.311, ink 0.006) and all five readings at the prompt zone's edge
(0.31-0.47, ink 0.011). `at_table()` is now correlation OR OCR after the
contrast guard; `ink()` stays as the aim sweep's ordering signal.
`tests/routing/test_at_table_ocr_path.py` carries a fixture only the correlation
can accept and Wanda pinned rejected; three mutants caught.

## at_table() ALSO MISSES THE PROMPT IN A DARK CAPTURE, AND A BRIGHTNESS-NORMALISED RETRY FIRED ON A STREET (2026-09-08)

The closed loop stood at the prompt for three iterations (frame mean 75/255,
`test_fixtures/table_prompt_cases/prompt_dark_ab4_t10_it062.jpg`) reading
False; a 1.2x gain read True. A retry on a copy scaled toward mean 90 (cap
1.5x) measured 21/21 arrival frames against 18/21 raw and 0 false positives on
500 route frames, shipped, and on its twelfth live trial "arrived" at k=58 —
the office doorway facing the L&B storefront, mean 54, normalised score 0.258
against MATCH_MIN 0.25. Re-measured on 36 prompt frames and 701 route frames:
the normalised scores of the prompts the raw mask misses are 0.25-0.30 and the
normalised negatives reach 0.258 — one population (§10.4). Reverted the same
minute. **The lesson is the census size: a 500-frame sample said 0; the frame
that fired was the 701st.** `at_table()` is the $50 gate; a change to it is
measured on EVERY route frame on disk, and a false positive anywhere is a
veto. The dark miss stays open.

## at_table() CANNOT SEE THE PROMPT OVER THE LIGHT TABLE TOP, and a local-contrast mask does not fix it (2026-09-07)

Goal-leg A/B trial 1 stood AT the dealer's table, camera pitched down onto the
table top after walking into it, with "Baseball Cards [] Play ($50)" plainly on
screen inside `TEXT_BOX` — and `at_table()` scored it **-0.001, ink 0.0001**
(`test_fixtures/table_prompt_cases/prompt_on_bright_table_goalleg_t1.jpg`). The
stroke mask keeps a pixel only if it is > `STROKE_BRIGHT` (175) AND its 11x11
neighbourhood averages < `STROKE_LOCAL` (140): white text over a light surface
is invisible to it by construction. That rule exists to remove the dealer's
white face, and it works; this is its cost.

**A local-contrast rule (pixel minus neighbourhood mean above a delta) is NOT
the fix — measured over 3,937 frames, `tools/prompt_mask_ab.py` ->
`overnight/census/prompt_mask_ab.json`:**

    variant   bright-table   old positives   NEG_NODES     route frames
              score          still True      false pos     newly True
    shipped     -0.002        1288/1288        0/671          0
    delta20      0.190        1203/1288       15/671         31
    delta30      0.119        1147/1288        0/671         32
    delta40      0.092        1117/1288        0/671         31
    delta60      0.044        1280/1288        0/671         23

The bright-table frame never clears `MATCH_MIN` 0.25 under any delta, while
every delta loses old positives and admits new ones: a wider mask takes wood
grain and card edges as strokes and the letter correlation drowns. No constant
is invented from this. **OCR of the band IS supported by the numbers, as a SECOND path after the
mask** (`tools/prompt_ocr_ab.py` -> `overnight/census/prompt_ocr_ab.json`, 4,002
frames; PSM 6 at 3x, both polarities, fuzzy match on baseball/cards/play,
two words required):

    false positives on 693 frames at non-table nodes      0
    the quest-log false-positive anchor                   0 words
    recall alone on the 1289 frames the mask accepts    341   (scale-sensitive)
    route frames the mask REJECTS that OCR reads         26   all dealer_circle,
                                                              prompt over the
                                                              dealer's white body
    table-leg end frames (43) with a hidden prompt        1   the bright-table one

Recall alone is poor, so it never replaces the mask: `at_table()` stays mask
first, OCR only when the mask says no. Two fixtures carry the two bright
backgrounds (`test_fixtures/table_prompt_cases/`). The patch and its test wait
in `drafts/pending_after_ab/` until no live run imports `table_prompt`.

Why this matters beyond one frame: `at_table()` is the arrival authority AND
the $50 gate, and OPEN-14's "ink up to 0.042 without the score gate" sweeps
were reading exactly this. Every arrival rate measured through it — including
the goal-leg A/B running today — is deflated by an unknown amount on the
pitched-down-at-the-table pose.

## Three more guards that could not fire (all fixed 2026-09-05)

- **`report_misfire` invalidated the cursor on 1 of 5 paths.** The call sat at
  the bottom, on the backoff-APPLIED branch, so four early returns skipped it —
  including `_backoff_abandoned`, which LATCHES and then never invalidates again
  for the life of the process. Demonstrated selecting card 0 when asked for card
  1. Its own comment says the invalidation is about the MISFIRE ("a keystroke may
  have been swallowed"), not the backoff, which is why it belongs at the top.
  The existing test passed throughout because it looped exactly
  `MISFIRES_BEFORE_BACKOFF` times — the one path that did invalidate.

- **`run_cycles` could never start a cycle.** `BUDGET_RESERVE = 120` against
  `api_budget.DEFAULT_BUDGET = 60`, so with `BASEBALL_API_BUDGET` unset the loop
  took its "stopping before cycle 1" branch every time: a plausible budget
  message and ZERO matches, forever. Now a loud error. Deliberately NOT fixed by
  raising DEFAULT_BUDGET — that constant caps REAL money.

- **`keep_awake` is DELETED (2026-09-05).** It existed to stop the PS5 sleeping,
  and its `NUDGE_MAG` sat exactly ON `turn_curve.DEAD_BELOW` rather than above
  it, so the nudge it advertised as ~7 degrees was 0.41 — a guard against a
  failure that has already cost a measurement, itself unable to fire. That was
  fixed; the module was deleted anyway, for a better reason.

  A run DRIVES the console, so it cannot sleep during one. The only gap
  keep_awake covered was idle time between runs — and nothing ever launched it
  (grep found it only in its own file and its two tests, and no log anywhere
  contains its output, so it had never run). Meanwhile its `BUSY_PATTERNS`
  stand-down list named 7 script names and matched NO A/B harness: `run_trial`
  spawns trials as `<venv>/python <abspath> --one-trial <arm>`. Every 240s it
  would have sent `clear`, which `injectinput.cpp` zeroes `left_x`/`left_y` on,
  while `slow_traverse` holds the stick untimed and sleeps out the full
  duration — **the leg walks short, and no log distinguishes that from a routing
  failure.** A module that could not help, in a way that could silently corrupt
  the run it was protecting.

  The lesson that survives it: a guard whose trigger is a hand-kept list of
  NAMES rots silently, because nothing fails when a new name is missing.

## A RESET IS THE MONEY RECONCILER, AND IT IS THE ONLY ONE (verified live 2026-09-13)

The user's point, and it closes a question the QA sweep left open. There is no
debit-undo anywhere in `orchestrator.py` -- `grep -nE "balance \+=|refund"` returns
one prose comment -- so a $50 debited for a press the wallet was too poor to accept
is never given back, and the tracked figure drifts below the game's forever.

**It does not need one.** `Load Last Save` restores the wallet to **$246**, and
`reset_env.reset_environment(progress_file=...)` clears `match_in_progress` on a
CONFIRMED reset. So one action repairs BOTH halves of the drift, and the repair is
free. What it does NOT do is set the tracked balance -- that is still by hand, because
the wallet is not read from the game.

    reset_env.reset_environment(progress_file="progress_testing.json")   # wallet -> 246,
                                                                         # flag cleared
    orchestrator.save_progress(w, l, d, 246, "progress_testing.json", ...)  # record -> 246

**Walked end to end on the live rig, and every step is worth recording:**

- The PS5 had auto-slept. `streaming()` returned **False** on chiaki's own host list
  (`State: standby`) -- OPEN-18's fix doing exactly its job on the one screen that used
  to make it answer True in 0.0s on a sleeping console. `ensure_live()` woke it in 8 s.
- **The pause menu was found OPEN**, left that way by an earlier `read_balance_from_
  pause_menu` whose paid call raised before reaching the close. That is the live form
  of the bug fixed hours earlier by moving the close into a `finally`; the evidence
  arrived after the fix, not before.
- `pause_menu.read_money` read **196**, then **246** after the reload -- its first ever
  use on the production path, correct both times, no paid call. The frame scored
  `page_fraction` **0.9401**, inside the PAUSE band 0.9263..0.9446 and well clear of the
  ban book's 0.8587 maximum: the census that found the ban-screen false positive is
  confirmed from the other side.
- **The local reader needs RETRIES right after a reload.** The settle gate reported the
  regions still moving at 6.0 s, `read_money` correctly refused (its two OCR scales
  disagreed), and a single-shot read then fell through to the paid call and raised. The
  reader was right; asking once was wrong. `MONEY_READ_TRIES = 5`, the same lesson
  `_verify_bans` already carries for the ban counter. More tries can only turn a
  refusal into an answer -- every attempt is the same conservative reader -- so this
  invents no confidence.
- The reset landed at spawn bearing **87 (E)**, reproducing section 8(d) exactly.

## A STALE match_in_progress SPENDS AN UNTRACKED $50

Reproduced 2026-09-04. When the flag is stale and a real dealer prompt is on
screen, orchestrator's recovery path presses `start_match` believing the $50 was
already paid: the money leaves the in-game wallet, `balance` is never debited,
`save_progress` is never called, and **`max_spend` cannot stop it** —
`run_one_match.py`'s promise that "no new money is ever spent, whatever the
tracked balance says" does not hold in that state.

**AND PREFLIGHT'S GUARD AGAINST IT COULD NOT FIRE THE WAY PREFLIGHT IS RUN (2026-09-13).**
The check read `sys.argv[1]` and defaulted to `progress.json`. This project keeps TWO
progress files ON PURPOSE (see section 2), so the guard only fired if you named the right
one. Demonstrated on one tree at one moment:

    python3 preflight.py                          ->  READY
    python3 preflight.py progress_testing.json    ->  FAIL, match in progress

`orchestrator.open_match_files(here)` now reports EVERY `progress*.json` claiming an open
match, because which file a later run will pass is not knowable in advance. Corrupt JSON is
SKIPPED rather than counted as a claim -- unreadable is not "a match is open", and treating
it as one blocks a run for the wrong reason.

**And the stale state was the NORMAL one.** 25 call sites reload the save; only
`run_cycles` repaired the record. Every navigation run left the flag armed.

Fixed at the source: `reset_env.reset_environment(progress_file=...)` clears
`match_in_progress`/`bans_done_this_match` on a CONFIRMED successful reset. That
is the one moment clearing is safe, and it satisfies CLAUDE.md's own "check the
screen first" rule — the reset IS the screen check. Money fields are never
touched. `preflight` also escalated from `warn` to `bad`, so a run cannot start
in the dangerous state.

## THE JUKEBOX LEG WAS 4.3x TOO SHORT TO REACH ITS DESTINATION (found 2026-09-05)

The largest single defect found on this project, and it invalidates several
things recorded here as settled.

`bar_pool_room -> bar_jukebox` was re-recorded 2026-09-04 as ONE 0.80s step at
speed 0.30 = **0.240 walk-units**. The human recording this map was built from
covers that span in **1.032 units over 3.32s** — `route3_steps.json` steps 27-31,
bearings 2.08 / 1.16 / 0.76 / 359.43 / 359.61, i.e. due north, matching the
leg's own 2.1. A SECOND independent recording (route2) gives **1.086**, agreeing
to 5%.

Distance recorded against distance needed, per leg:

    office_corridor -> office_door     0.98
    office_door     -> portrait_room   0.96
    portrait_room   -> bar_pool_room   0.95
    bar_pool_room   -> bar_jukebox     0.22   <<<
    bar_jukebox     -> dealer_table    0.91

From the FAR EDGE of `bar_pool_room`'s recognition basin the short leg lands
**0.703 units short** of the near edge of `bar_jukebox`'s basin. It could not
reach its destination from anywhere in its origin's basin. The original 3.30s
leg landed dead centre.

**Why it was never caught.** The search that produced it
(`overnight/phase1_step4_rerecord.py`) only offered `DURS = [0.8, 1.3]`, so the
correct ~3.3s was never a candidate. It then reported 2/2 arrivals — from a
basin its own landing point misses, which means those arrivals came from the
recovery fan, not the leg.

**RESTORED 2026-09-05** to the recorded five steps. Pinned by
`tests/routing/test_leg_distances_match_recording.py`. **It pins the JUKEBOX
leg specifically**, against its recorded 1.031 units within 15%, plus a floor
that no leg is implausibly short. It does NOT yet check the other four legs
against their recordings — doing that needs each leg's step-index span in
`route3_steps.json` established first, and until it is, this test would not
catch the same defect on a different leg.

### What this invalidates

- **GRAVEYARD's "the re-recorded leg changed NOTHING" row.** It reads 4/8 -> 4/8
  as "leg parameters do not matter". The arithmetic says the new leg CANNOT have
  produced those arrivals, so the A/B was not measuring the leg. Corrected there.
- **Any conclusion about this leg drawn between 2026-09-04 and 2026-09-05**,
  including the per-leg arrival rate of 6/15 and the failure-class census.
- It is a strong candidate for what has been costing the route. Whether it moves
  arrival is UNMEASURED — see OPEN-14.

## THE STEP FIELD `cam` IS WRITTEN BY build_route AND READ BY NOTHING

`bearing` in every recorded step is a WORLD TRAVEL DIRECTION = camera heading +
left-stick angle. `cam` is the camera heading the human actually held. Two
consequences, both live:

**`approach_goal` aims 10.6 degrees off the leg's own direction.** It takes
`steps[-1]["bearing"]` and discards the other seven. On the final leg the human
never turned — `cam` is 86.73-87.01 across all eight steps — and steered entirely
by strafing, so `bearing` swings 71.99 -> 97.63 -> 75.46. The last step's 75.46
is 10.61 off the leg's net direction and 11.31 off the heading the prompt was
recorded at. CLAUDE.md's own "ink 0.0214 at the leg's heading and 0.0395 twenty
degrees away" is at least partly this: we aim 11 degrees off the recorded
viewing heading, and `face_the_table`'s sweep pays to recover it every time.

**IT ALSO UNDERCUTS OPEN-3's PREMISE.** On `portrait_room -> bar_pool_room`,
`cam` is 281.09-281.22 — constant to 0.13 degrees — while `bearing` spans 6.59.
So the "recorded curve" that motivates `LEG_TURN_TOLERANCE` is, on that leg,
entirely LEFT-STICK WOBBLE. The human's camera did not move at all. Tightening
the turn tolerance would make the executor chase a curve that was never a curve.
**Re-derive OPEN-3's premise from `cam` before spending console time on it.**

## The map's COORDINATES and TRAIL still describe the old leg

`worldmap.connect()` writes `links` only; nothing re-integrates `landmarks` or
`trail`. Integrating the steps reproduces the stored coordinates exactly for the
first three nodes and then diverges by 0.79 at `bar_jukebox` and `dealer_table`.
`trail` still holds the original 40 steps.

Navigational impact today is NIL — `bearing_to()` is called only from tests. The
cost is that the coordinates are the only human-readable geometry in the file,
and they contradicted the steps by 4.3x, which is exactly how the short leg
stayed invisible. `world_map_backup_20260904.json` is byte-identical to the
post-change file, so the pre-re-record leg survived only in `route3_steps.json`.


## SAVING A FRAME CAN MAKE THE COMPASS READ 90 DEGREES WRONG (2026-09-05)

`read_bearing`'s docstring promises it "returns None rather than guessing — a
wrong bearing would turn the player to face the wrong way and the walk would end
somewhere arbitrary, which is worse than not turning at all." **It does guess.**

Measured on 120 archived demo frames, 80 of which read on the original. Each was
re-encoded as JPEG and re-read — nothing else changed:

    quality 75   ABSTAINED 5 (6.2%)   WRONG BY >5 deg 2 (2.5%)   errors [90.0, 15.2]
    quality 88   ABSTAINED 1 (1.2%)   WRONG BY >5 deg 3 (3.8%)   errors [90.0, 90.0, 74.9]

Same scene, same code, two encodings, two different CONFIDENT answers. At least
one of each pair is wrong.

**THE ERRORS ARE EXACTLY 90.0, WHICH NAMES THE MECHANISM.** N/E/S/W are 90 apart,
so this is CARDINAL LETTER CONFUSION — one glyph misidentified as another — not
gradual degradation of a good read. That is the single failure two agreeing
letters cannot make, which is why this is direct evidence for the
`REQUIRE_TWO_LETTERS` work in OPEN-15 rather than an argument against its
coverage cost.

**QUALITY 88 PRODUCED MORE WRONG ANSWERS THAN 75.** Non-monotonic, so this is a
chaotic threshold flip and not something a higher quality setting buys safety
from. 88 is what `places.py:185` and `play_now.py:39` save at; 82-88 is the range
used across the project.

### What this costs, in order of how sure it is

- **CERTAIN: §10.15's KEEP A FRAME is unsafe FOR THE COMPASS.** A kept frame can
  answer 90 degrees differently from the live capture it came from, so no compass
  threshold may be tuned or validated on a saved JPEG. The rule stands for
  everything else — a kept frame is what settled the wedge diagnosis the same day
  — but not for this detector.
- **CERTAIN: any bearing pinned in a test from a `.jpg` fixture pins what the
  COMPRESSED frame says.** It is still a valid regression guard on the code; it is
  not evidence about live behaviour.
- **NOT ESTABLISHED, AND THE REASON TO CARE: the live path is also lossy.** The
  stream is H.264 with varying quantization, and chiaki logs
  `StreamConnection reporting corrupt frame(s)` during normal play. Nobody has
  shown this fires live. But the old assumption — that the live path is immune
  because no JPEG is involved — is not available any more, and a wrong bearing
  live is the failure the docstring says is worse than not turning at all.
- **A HYPOTHESIS, EXPLICITLY NOT ESTABLISHED.** §8(k) is the user's unexplained
  observation, *"when you make the turn, you actually walk right out of the
  bar"* — seen on the stream the first day, never captured. A 90-degree bearing
  error is exactly the mechanism that produces it, and nothing else in this file
  explains it. **If `REQUIRE_TWO_LETTERS` lands and §8(k) stops happening, that is
  the strongest signal available.** Do not treat the coincidence as evidence
  before then.

Reproduce: re-encode any frame `read_bearing` reads, at quality 75 and 88, and
compare. No rig, no console, ~2 minutes.

### CORRECTION 2026-09-06 — re-measured twice, and the entry above is wrong in
### four ways. Read them before quoting any number from it.

Two agents reproduced this independently, the second adversarially. The effect
is REAL and the mechanism named above is RIGHT. Everything quantitative is not.

**1. IT WAS MEASURED ON A READER THAT NO LONGER SHIPS.** The numbers above come
from the pre-OPEN-15 `compass.py` (41,144 bytes). On the same worst-case run the
SHIPPED reader gives **5 of 270 at q75 and 0 of 262 at q88** wrong by >5 deg.
The guards landed; this is largely a description of the old reader.

**2. IT UNDER-REPORTS ITS OWN FINDING BY ABOUT 10x.** "2.5%" and "3.8%" come from
a 120-frame subset. Over the whole run that produced them, the OLD reader's rate
is **25.1% and 22.7%**. The entry was too kind to itself.

**3. IT IS A SINGLE-RUN EFFECT, NOT A RESOLUTION EFFECT.** All eight demo runs
are 1400x787, so "demo archive" and "0.73x linear resolution" were perfectly
confounded, and the RUN wins: `demos/walk3_full_20260828_050731`, same geometry,
710 frames, **zero** errors >5 deg at either quality, max 0.89 deg. Every flip
anyone has found is in `demos/walk_20260827_214446`. So "zero at 1920x1080" does
not license "the live geometry is safe" — it says those particular scenes are.

**4. PNG IS LOSSLESS AND CHANGES NOTHING.** 3,154 reads, max delta **0.0000**.
Only JPEG re-encoding perturbs anything. A compass fixture must therefore be a
PNG, and `test_fixtures/compass/bar_doorway_abstains_1920.png` already is — the
bearings derived from it are unaffected by any of this.

**THE ATTRIBUTION IS RIGHT, WITH ONE REFINEMENT.** It is the LETTER-
CORROBORATION family that stops the cardinal flips — `REQUIRE_TWO_LETTERS` **or**
`POOL_THRESHOLDS`, either alone is enough. `USE_TICK_LATTICE` stops a DIFFERENT
failure whose signature is ~32-37 deg: with the lattice on and both letter guards
off, >5 deg goes 5/270 to 34/178 at q75 with a correct cached pitch. A first pass
that credited the lattice was confounded by leaving `POOL_THRESHOLDS` on.

**THE §8(k) HYPOTHESIS LOSES ITS OFFLINE SUPPORT.** No 90-degree error is
producible at 1920x1080 on any frame that actually contains a compass bar, on
either reader. And the bullet above beginning "If `REQUIRE_TWO_LETTERS` lands" is
stale: it ships True. §8(k) is back to having no candidate explanation.

**THE LIVE PATH, CHECKED PROPERLY.** `graph_walk.reference_heading()` (~:1748) is
the ONE production caller that reads a bearing from a SAVED file rather than a
live capture — `places/<node>/route_*.jpg` — and `align_at_node` turns the camera
to that heading before measuring dx, so a wrong read there moves the character.
On the four files that exist, both readers agree to within **0.066 deg** across
original / PNG / q88 / q75. The best available proxy for the live question — 206
`world_log` pairs of a live in-memory read against the q82 JPEG saved from the
same object, all at 1920x1080 — gives max **0.591 deg** and zero disagreements
>5 deg. **No live hazard is demonstrated.** What remains unknown offline is
whether the ORIGINAL capture that produced those JPEGs read the same as the file.

**THE REPRODUCE RECIPE ABOVE NO LONGER WORKS** at HEAD on any corpus except
`demos/walk_20260827_214446`.

---
