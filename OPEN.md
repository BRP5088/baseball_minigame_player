# Open work (§11)

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

---

## §11 OPEN

Nothing outside this section may claim to be open.

Closed, answered and dropped tickets are NOT kept here. Verified measurements
and fixes are folded into the section they belong to — OPEN-4 and OPEN-5 into
§8(c), OPEN-10 and OPEN-11 into §2, OPEN-12 and OPEN-18 into §3, OPEN-16 into
§5, OPEN-2 into §1 — dropped hypotheses go to `GRAVEYARD.md` (OPEN-3) so they
are not retried, and an answered ticket's FULL TEXT goes to `CLOSED.md` with a
pointer left here (OPEN-1, OPEN-8, OPEN-14, OPEN-19, OPEN-23). A ticket that
stays here is unmeasured, half-measured or blocked, and says which.

**THAT RULE WAS NOT BEING KEPT.** On 2026-09-17 this section was 1,056 lines,
24% of the file, and roughly 500 of them were tickets it says do not belong
here — several carrying their own superseded "(original)" text underneath the
answer. A closed ticket left at full length is not harmless: it costs context
every session, and a live finding appended underneath one reads as closed too.

Numbering: **OPEN-15 is the compass reader**, **OPEN-16 was the injector release
window** (closed, §5), **OPEN-17 is the arrival heading**. Older worktree copies
of this file used those numbers differently; this file is the authority.

**THE BAN GRID IS FITTED PER FRAME NOW, AND THE INPUT TARGET IS CHECKED (2026-09-13).**
Two flags shipped ON after a phased comparison; both are in §11's closed record rather than
here, but the three facts worth carrying are:

**`ban_grid` IS 16:9 ONLY, and that is enforced, not assumed.** Its card height is derived as
`CARD_ASPECT * column_width * (w / h)`, so the frame's ASPECT is an input to the row fit. On
an archived 2000x1292 frame (aspect 1.548) it fits rows at 0.382 / 0.710 where the true ones
are 0.195 / 0.478 -- different cards, not a small error. Flipping the flag took
`test_ocr_ban_card` from 2 abstentions to 18 in one run. `orchestrator._ban_frame_is_16x9`
now routes anything else to the shipped boxes. The live rig captures 2000x1125 and
1920x1080, both 16:9, so production was never exposed -- but §3 says a reader is checked at
BOTH geometries, and "it does not happen today" is how a rig change becomes a wrong answer
later.

**GIVING UP MID-MATCH LEAVES YOU AT THE TABLE, prompt up.** Measured: OPTIONS -> "Give up?"
-> cross, and one second later `screen match_start_prompt`, `at_table True`, no walking. That
is a free ride back to a ban screen and it skips the entire 76 s route whenever another one
is needed.

**THE DEALER PROMPT RENDERS WHATEVER THE WALLET HOLDS.** A Square press with too little money
does NOTHING and looks exactly like a press that did not land -- it cost a wrong diagnosis
and a wrong $50 in the record here. `Load Last Save` restores the wallet to $246; the tracked
balance must be set to match, because it is not read from the game.

**OPEN-23 — CLOSED 2026-09-13. The live ban scan returned 8 cards of ~33 and the
diagnosis in the ticket was wrong: the scan was fine, every PRESS was going to a
`/bin/zsh`** that `pgrep -f chiaki` had matched. Fixed in
`input_controller._resolve_chiaki_pid` (match the executable NAME, then filter by what
each process IS), pinned by `tests/rig/test_input_target_is_chiaki.py`, 4 mutants. The
shape worth keeping is in §10: the guard that "could not fire" was one level further out
and asking "is this pid ALIVE" rather than "is this pid CHIAKI". Full text: `CLOSED.md`.

**OPEN-1 — CLOSED 2026-09-07. The leg-end frame path is built, pinned and has
executed live**; hundreds of `at_<node>_<epoch_ms>.jpg` frames exist and the first
admissible failure census was taken from them (§8(f), and "THE FAILURE CENSUS EXISTS"
below). Acceptance test, unchanged: a real jukebox-leg failure frame must NOT read
bearing ~286 and must NOT identify as `bar_pool_room`. Full text, including why all
fifteen earlier candidate frames were inadmissible: `CLOSED.md`.

### Findings that were filed under OPEN-1 and are not that ticket

SEVEN separate results were appended under the ticket above over two days. None is about
frame provenance, which is what OPEN-1 was; they are about the world, the localiser and
two regressions. They stay here, under their own heading, until §7 and §8 absorb them --
filed under a CLOSED ticket they read as closed too, which is how a live finding goes
quiet:

    a working "did I move" signal, and it is a PAIRED ratio      §8's missing instrument
    every leg ends by walking into something                     16 of 17 blockages
    mapping the world in 3D, and rotation is worthless for it    3 points of 196,198
    the localiser's gate sits inside the overlap                 137 true vs 135 outdoors
    the failure census exists, and it is 80% OVERSHOT            the first admissible one
    leg 1's regression was OUR OWN CHANGE, not the console       Fisher p = 0.000714
    the start node regressed the same day                        why OPEN-14 did not run

**A WORKING "DID I MOVE" SIGNAL, AT LAST — AND IT IS A PAIRED RATIO (2026-09-06).**
Section 10.4 records that scene change CANNOT answer this: `STALL_CHANGE` cuts
through a unimodal 3.1-7.9, one population. Measured again directly, by taking
the SAME capture pair twice at each heading — once with no push at all, once
with a real one:

    signal          null range        push range        verdict
    frame delta     1 - 12            7 - 24            OVERLAP, unusable
    ORB inliers     353 - 1366        35 - 908          OVERLAP, unusable

Neither works as an absolute gate. But PAIRED at the same heading, dividing the
push's inlier count by that heading's own null:

    0.10  0.11  0.26  0.30  0.34   |   0.82
    <------------ moved ---------->     blocked

A gap of 0.49 between two measured populations. The pairing is what makes it
work and an absolute count cannot: one heading's NULL read 353 while another's
PUSH read 407, so the same number means "blocked" in one place and "moved" in
another. The ratio divides out local scene animation, which is also what makes
it robust to an NPC wandering through the shot.

n = 6 headings from one spot. The MECHANISM is sound and the gap is wide; the
rate is not established. `overnight/probe_calib.py` re-measures it anywhere in
about two minutes, and `overnight/collect_map.py` is the collector built on it.

**WHY THIS MATTERS MORE THAN IT LOOKS.** Every navigation failure this project
has is downstream of not knowing whether a push worked. The stall gate guesses,
the escape ladder fires blind, and a blocked leg is indistinguishable from a
walked one until the localiser disagrees two legs later. A probe that costs two
seconds and answers directly is the missing instrument.

**EVERY LEG ENDS BY WALKING INTO SOMETHING, AND THE LOGS HAVE SAID SO ALL
ALONG (2026-09-06).** Tallied over every archived `overnight/*.log`, no console
time spent:

    blocked on the LAST step of its leg        14
    blocked on the second-to-last step          2
    blocked anywhere else                       1

    portrait_room -> bar_pool_room   step 4/4   x8
    bar_pool_room -> bar_jukebox     step 5/5   x5
    bar_pool_room -> bar_jukebox     step 4/5   x2
    office_corridor -> office_door   step 7/7   x1

Sixteen of seventeen blockages are at or immediately before a leg's end. That is
not diffuse bad luck, it is one repeatable event happening in five different
places.

**WHY, AND IT IS VISIBLE IN THE MAP ITSELF.** Every leg's FINAL step is short —
0.14s, 0.23s, 0.36s, 0.40s, 0.42s — against 0.78-0.80s for the steps before it.
That is a HUMAN DECELERATING: they walked up to a door, a table or a wall,
made one small adjustment, and stopped. The executor does not decelerate. It
replays that tail as a fresh fixed-magnitude push from whatever speed it is
already carrying, and §7(j) records that a push under ~0.10s does not move the
character at all while short pushes are mostly acceleration. So the least
faithful part of every leg is its last step, and that is exactly where the
blockages are.

It corroborates two other things measured the same day. `office_door`'s arrival
frame is a DOOR PANEL filling the view at 7-16 keypoints, on BOTH the merged and
the original leg 1 — the recorded destination is already pressed against
geometry. And 8 of 10 admissible failure frames at `bar_pool_room` classify
OVERSHOT.

**WHAT THIS DOES NOT LICENSE.** Shortening the final step MOVES the character,
and GRAVEYARD's own summary is that every change which moved the character
failed while both survivors moved nothing. The finding is a diagnosis, not a
prescription, and it is cheap to test precisely because the blockage is
localised: one leg, one step, and the log already reports the event by name.

**MAPPING THE WORLD IN 3D IS POSSIBLE, AND ROTATION IS WORTHLESS FOR IT
(2026-09-06).** The single most expensive thing to relearn here.

A drive was recorded by hand through the office: 1064 frames, 95% with a
compass heading, the controller logged on every frame, the stream alive on every
pair, and all eight approach angles filled. By every check available on this
machine it was a perfect collection. Its reconstruction kept **3 points out of
196,198 tracks.**

    what the driver did          share of frames
    turning                            61%
    walking                            17%
    standing still                     32%
    camera translation over 3 frames   MEDIAN ZERO

**Triangulation needs the camera to MOVE.** Turning on the spot moves the lens
not at all, so the rays stay parallel and every distance fits equally well. 85%
of that drive fell short of the baseline the reconstruction needed. The filter
rejecting 196,195 tracks was CORRECT; the data carried no depth.

**THE TWO GOALS NEED DIFFERENT DRIVING, and conflating them cost a room.** The
instruction given was "fill the eight-sector angle bar", which optimises for the
LOCALISER — a reference matched from the wrong approach angle does not match at
all. Geometry needs the opposite: straight lines, turning only at the ends, like
mowing a lawn. That drive remains excellent reference data (789 frames of
genuinely new ground) and useless as structure.

**WHAT MAKES THE RECONSTRUCTION TRACTABLE AT ALL**, since generic
structure-from-motion breaks on this game's low-texture cartoon art: the poses
do not have to be solved for. Yaw comes from the game's own compass, absolute,
on 95-99% of frames, so rotational drift cannot accumulate. Pitch comes out of
the pose decomposition and was measured sound — 0.27 deg/frame integrating to
+1.0 deg over 82 pairs, against a roll control drifting -17.1 deg over the same
span. Distance comes from the recorded stick; the vision-only alternative was
scored against the four archived recordings carrying both and correlates 0.55-58
on walks and **0.14 on turns**.

**FOUR FILTERS ARE NOT OPTIONAL AND THEIR ABSENCE LOOKS LIKE A MAP.** A first
pass triangulated adjacent frames with no cheirality test, no reprojection test
and two views per point, and produced 644,872 points that rendered as radial
starbursts centred on the camera path — an audit found 19.6% of them lying
between or behind the two cameras. Require: a point in FRONT of every camera,
reprojection within a few pixels, three or more views, and positions genuinely
apart.

**THE RIG:** the Mac drives the console and Snoopy reconstructs, over SSH with
key auth. Snoopy is 2x SLOWER at this work than the Mac (ORB is CPU-only; the
3080 contributes nothing), so it is not a speed-up — its value is being a
DIFFERENT machine, because heavy local load degrades sleep from ~5ms to 242ms
and corrupts every walked leg. `tools/ask_snoopy.py` ships a drive, reconstructs
it there and answers one question in ~2 minutes: is this ground producing
geometry. It names the CAUSE, because "positions too close" (not translating),
"too few views" (too fast) and "behind a camera" (the trajectory is wrong, not
the driving) need different responses.

**THE LOCALISER'S GATE SITS INSIDE THE OVERLAP, MEASURED (2026-09-06).**
`portrait_room` abstains about half the time on frames where the character IS
there, and §8(b)'s per-leg rates inherit that. The cause is not the leg.

    a GENUINE arrival scored          137 matches
    a frame taken OUTDOORS ON A       135 matches
      STREET, off the mapped route

`MIN_MATCHES` is 140. Those two populations are not separated by it, in either
direction. Raw ORB match count cannot do this job on this game's art: unrelated
rich frames score 100-155 against any room, because a black-and-white cartoon of
wood, walls and floors produces promiscuous descriptor matches. **It is NOT the
HUD** — `places._as_gray` already crops the compass, coin and quest list (top
10%, bottom 10%, left 28%), and masking them again changes nothing.

So `portrait_room` is not being CONFUSED with `bar_pool_room`. `bar_pool_room`
simply sits at a constant 100-135 on every rich frame, and the ratio gate is
dividing a real signal by that floor.

**A CLAIM MADE HERE EARLIER THE SAME DAY WAS WRONG, AND IS WITHDRAWN.** This
section said "the reference set is too thin to pass its own test: leave-one-out
names its own room 3 of 9 times". **It names it 9 of 9, with zero wrong and zero
abstentions**, at best 248-698 and ratios 1.91-5.29 — which reproduces §7's
"249-698" exactly. The reference set passes its own test.

The 3-of-9 came from a REIMPLEMENTATION that was never checked against the
original. `places.match_count` filters matches by Hamming distance
(`places.py:409`); the mirror in `agent_progress/localiser-inliers/validate.py`
used a raw `len(bf.match(...))`. Unfiltered, spurious matches inflate the
SECOND-best room, which collapses the ratio and produces six false abstentions.
The same file's own docstring warns about exactly this trap, having already been
caught by it once that morning over the HUD crop. Anything scored through that
mirror's RAW-COUNT column is suspect; its RANSAC-inlier column and everything
computed through `places.identify` / `places.room_scores` are not.

**WHAT STILL STANDS, because it went through the project's own path:** a genuine
arrival at `portrait_room` scored 137 while a frame taken OUTDOORS ON A STREET
scored 135, against a `MIN_MATCHES` of 140. The gate sits inside the overlap.
That is the finding; "the references cannot recognise themselves" is not.

**RANSAC-VERIFIED INLIERS ARE A CANDIDATE, NOT A CONCLUSION.** Fitting one rigid
transform to the matches and counting inliers, because a spurious match is a
descriptor coincidence and does not agree with the others:

    metric              leave-one-out      160 unmapped bar frames NAMED
    raw match count        3/9 correct                16
    RANSAC inliers         9/9 correct, 0 wrong       55-96 (gate 60 down to 10)

It fixes the true-positive side completely and appears to make the false-positive
side much worse. **But that second column is not scoreable**: those 160 frames
are an EXPLORE run through the bar area, and §7 says that area is two-thirds
unmapped — which means up to a third of them may genuinely be at a mapped node,
so "named" is not the same as "wrong". Before anything ships, that corpus needs
labels. Do not quote the 55-96 as a false-positive rate.

Script: `agent_progress/localiser-inliers/validate.py`, self-contained. **It got
this wrong first, in a way worth remembering**: without replicating
`_as_gray`'s crop it scored the unmapped corpus at a median of 777 against a 140
gate and rated it above the references themselves — it was measuring the HUD
matching itself, 160 times. A reimplementation of a project function means
nothing until it is checked against the original.

**THE FAILURE CENSUS EXISTS (2026-09-06). It is 80% OVERSHOT, and it is the
first one ever taken from admissible frames.** OPEN-1 asked for this and OPEN-6
forbade quoting any class distribution until a run produced it. A run has.

Twenty-eight `at_<node>_<epoch_ms>.jpg` leg-end frames were written live for the
first time; ten of them are the failing node `bar_pool_room`, classified with the
stream confirmed live:

    OVERSHOT   8/10   95% Wilson [0.49, 0.94]
    WEDGED     2/10   95% Wilson [0.06, 0.51]

The interval EXCLUDES a half-and-half split, so "most of these failures are
overshoot" is supported at n=10. The exact fraction is not. The withdrawn figure
it replaces was 2 of 8 POST-FAN frames at [0.07, 0.59] — inadmissible and
uninformative. **OPEN-6's ban on quoting a class distribution is lifted for this
node only**, and only for the direction of the effect.

Every frame reads bearing 284.8-289.9, i.e. facing the way the leg walked, and
none identifies as any known place (best scores 1-154 against MIN_MATCHES 140).
Keypoints split cleanly: the two WEDGED frames hold 10, the OVERSHOT ones 420-1500.
`test_fixtures/leg_failures/` keeps one of each.

**AND ONE OF THEM IS OUTDOORS.** `overshot_outdoors_1788718155150.jpg` shows the
character on a CITY STREET — a truck, a lamppost, shop signs — after a leg that
should have ended in the bar's pool room. That is the shape of §8(k), *"when you
make the turn, you actually walk right out of the bar"*, which this file has
recorded since day one as never captured. It is now captured. Whether it is the
same event the user saw is NOT established; what is established is that a leg
into the bar can end outdoors and off the mapped route.

**SOLVED 2026-09-06, AND IT WAS OUR OWN CHANGE, NOT THE CONSOLE.** The
regression below was attributed to the power cycle. That was an association and
it was wrong. Measured interleaved, 10 trials an arm, verified arrivals at
`bar_pool_room` (`overnight/ab_leg1.py`, `overnight/ab_leg1.json`):

    leg 1 AS RECORDED           10/10 arrived   median  51.6s   [50..55]
    leg 1 at speed 3.0, MERGED   2/10 arrived   median 323.7s   [206..371]
    Fisher exact p = 0.000714, zero invalid trials

The restored arm reproduces the lost baseline exactly — 51.6s against the 52.9s
measured before the flags landed — and its ten times span five seconds.

**THE TIMELINE IS THE LESSON.** The 10/10 was measured at 23:12 on 2026-09-05.
The commit that RECORDED it, at 23:33, is titled "OPEN-4 answered 10/10; leg 1
to max speed" — it enabled the first flag. `MERGE_STEPS_BY_LEG` followed at
00:20. So the result and the change that invalidates it share a commit message,
which is section 10.7 violated inside the artifact that reports the
measurement. It stayed invisible for a day and cost an afternoon of runs.

`tests/routing/test_leg_speed_scale.py` then pinned the override and justified
it in a comment as shipping "on a measured 10/10 arrival" — crediting the flag
with a result measured before it was switched on, written where it reads as
evidence. Both flags are reverted (`backups/restore_leg1.py`) and the test now
pins their absence against the A/B above.

**GRAVEYARD HAD ALREADY MEASURED BOTH HALVES AS FAILURES.** Step merging is a
graveyard row whose stated mechanism is "a merged push covers more ground than
the stop-start sequence it replaces, so legs that used to stop short now run
into furniture" — and the failing log says *BLOCKED on step 4, the view is
featureless, this is geometry*. Leg speed at 3x is another row, mean WORSE. Both
rows' "State today" columns had gone stale and said the flags were off. **A
stale graveyard is worse than none: it is how a measured failure comes back.**

**THE START NODE REGRESSED THE SAME DAY, AND THAT IS WHY OPEN-14 DID NOT RUN.**
This morning `go_to_node_verified("bar_pool_room")` measured 10/10 at a 52.9s
median (OPEN-4). This afternoon, after the console was power-cycled, it reached
that node 0 of 3 times at 274-446s. Both arms degraded together, which §10.6 says
means the environment — the first suspicion was local load from concurrent
offline work, and that was WRONG: a restart on a quiet machine failed identically.

The signature is a RATIO failure at `portrait_room`, not a missing-features one:

    confirmed   267, 295 matches   ratio 2.04, 2.38
    abstained   155, 150, 109, 85  ratio 1.21, 1.21, 1.20, 1.16

`MIN_RATIO` is 1.35. When it works it clears comfortably; when it fails the best
reference barely beats the runner-up, which is ambiguity BETWEEN references
rather than a dark frame. Alongside it the leg into the bar reports "BLOCKED on
step 4" and the escape ladder fired five times, consistent with NPC traffic the
user had already noticed near that path.

**The start node is fixed (see above), so OPEN-14 is unblocked.** Measuring a leg
you reach 0 of 3 times spends an hour per arm to record INVALID; at the restored
leg 1 the start node is reached 10/10 at a 51.6s median.

**OPEN-14 — MEASURED 2026-09-07, and the honest tally is 1 ARRIVED OF 3 VALID,
best streak 1.** The harness printed 2/3 and streak 2; both counted trial 6, which was
`identify()` naming `dealer_table` from a distance with no prompt -- §7 says the table is
a POSE and that rule was enforced in `confirm()` but not in `locate()`. Fixed the same
morning, pinned by `tests/routing/test_locate_goal_is_a_pose.py`, 3 mutants.

**THE CEILING CENSORED 7 OF 10 BY CONSTRUCTION** and that is the transferable part: a
goal-leg retry is a FULL RESET AND ROUTE RE-WALK, so an `attempts=9` ceiling must be
`attempts x route-time`, not the 780s maximum from OPEN-5 where retries are local. 10.14,
self-inflicted. Full text, the per-trial table and what the 37 table-leg end frames show:
`CLOSED.md`.

**OPEN-13 — Does nulling the yaw before aligning improve ARRIVAL?**
`graph_walk.NULL_YAW_BEFORE_ALIGN` ships **True**, because the old behaviour
violated a precondition `pose.offset`'s own docstring states ("null the yaw with
the compass first"). That makes it a bug fix, not a tuning choice — but its
effect on arrival rate is **unmeasured**, and nine well-motivated navigation
changes on this project have failed their A/Bs.

Measured basis: 18.6-20.8 px per degree of yaw at the live geometry (7 pure
camera-turn pairs, character stationary), corroborated by
`camera_fov.json` (1920 / 102 deg = 18.8). So `ALIGN_TOL_PX = 35` is 1.8 degrees
and `SAME_POSE_PX = 16.85` is 0.87 degrees, while the leg executor turns with a
4.0 degree tolerance — a character exactly on the reference POSITION but 2
degrees off its heading read ~40px and was strafed sideways for it.

The A/B: `NULL_YAW_BEFORE_ALIGN` True vs False, 10 trials per arm, interleaved,
scored on VERIFIED arrivals, on a quiet machine. Report by failure class, not
just the total.

**Its own guard was DEAD until 2026-09-05, and the failure looked like a broken
feature.** `tests/routing/test_yaw_nulled_before_align.py` simulated an
unreadable reference by poking `gw._REF_HEADING["portrait_room"] = None`, but
`reference_heading()` keys that cache on `(REFERENCE_POSE, node)` — deliberately,
so an in-process A/B cannot serve one arm's heading to the other. The bare-node
poke therefore missed the key entirely, the heading recomputed to 1.39, and the
UNREADABLE branch the check exists to guard was UNREACHABLE. The stub was left
behind when the key gained `REFERENCE_POSE`. Fixed in the main checkout, and
mutation-tested by replacing that `log(...)` with `pass` (file size 100550 ->
100374, so no stale bytecode) — the check then fails, and only that one.

**OPEN-6 — `SURVEY_WHILE_WALKING`, `SPEED_FROM_RELIABILITY` and
`RECORD_RELIABILITY` have never been tested live; the first's premise is now
MEASURED.** `SURVEY_WHILE_WALKING` was built on "the OVERSHOT class, a quarter of
failures", a figure from 8 post-fan frames that were inadmissible as evidence
about a leg. The admissible measurement replaced it (2026-09-06, "THE FAILURE
CENSUS EXISTS" above): at `bar_pool_room`, from leg-end frames with the stream
confirmed live, **OVERSHOT 8/10, Wilson [0.49, 0.94]; WEDGED 2/10, [0.06, 0.51]**.
The interval excludes a half-and-half split, so "most failures at that node are
overshoot" is supported at n=10; the exact fraction is not, and the first
admissible ROUTE census (2026-09-07, §8(a), n=5) is WEDGED-heavy — wedged 4,
overshot 1. So the premise survives for `bar_pool_room` and is unsettled for the
route. `SURVEY_WHILE_WALKING` stays `False` until an A/B, not because its
premise is gone.

`SPEED_FROM_RELIABILITY` and `RECORD_RELIABILITY` are correct at `False`,
demonstrated: 12 recorded arrivals make `leg_reliability.scale_for` return 3.0,
and ONE subsequent failure returns it to 1.0 (11/12 = 0.917, under `MIN_RATE`
0.95) — pinned with literals in `tests/routing/test_leg_reliability.py`. With
both on, `follow_verified` writes the outcome it is measuring and `leg_scale()`
reads it back, so trial N's walking speed is a function of trials 1..N-1, and an
interleaved A/B's two arms share one store unless each arm sets
`leg_reliability.STORE` inside its trial CHILD — the redirect works now (§10.18).
`leg_reliability.json` does not exist on disk; neither flag has ever run live.

Audited for the same write-then-read shape and reported, not changed:
`compass._SCALE_CACHE` (`compass_scale.json`) and `input_controller._VIEW_CACHE`
(`view_bounds.json`) are written mid-run and read back, and the view cache is a
"widest lit extent ever seen" ratchet that moves the view centre and hence every
bearing. They calibrate the DISPLAY, not the outcome — no arm can move them
differentially and they converge, so interleaving absorbs them. Their writes are
suppressed under `BASEBALL_TEST_RUN` (`tests/harness/test_caches_not_written_in_tests.py`).

**WHAT A CLASS CENSUS COSTS.** `follow_verified` stops at the FIRST unproven node,
so a trial yields AT MOST ONE classified failure; at 5/10 route arrival that is
0.5 failures a trial. ±20pp on one class needs 16-21 failures (~40 route trials,
~3h); ±10pp needs 69-93 (~230 trials, ~22h); a single-leg harness at ~90 s/trial
reaches ±20pp in about an hour. Take the ±20pp run when a decision hangs on a
class; nothing does today.

**OPEN-7 — Should `RECOVER_MISSED` be turned off?** The fan succeeded 0/15 in
the streak run and 2/31 combined, while costing ~34% of the clock. Judge it on
seconds and failures-by-class, not arrival. **The cost is now confirmed twice
over, independently** (2026-09-05): `ab_local_recovery`'s local arm has a median
trial of 155.4s against the reset arm's 76.3s, and the only difference is one
`LOCAL_RECOVERY_FIRST` fan, so a fan is ~79s; a static model of the fan from the
constants gives 70.0s. At the 14 misses per 10 streak trials in the archived
logs that is ~111s a trial, **33%** — reproducing the ~34% already recorded here
by a different route. It is the single largest item on the clock.

**OPEN-8 — Where does the other ~45s of a trial go? MOSTLY ANSWERED 2026-09-05;
three cuts made, ~26% of a streak trial still unexplained.**

**THREE CUTS WERE MADE AND ONE WAS REFUSED; the write-ups are in `CLOSED.md`.**
Cut 1, `TRUST_RESET_SPAWN` + `start_hint`: 26 of 26 archived trials threw away the reset
they had just paid for, ~24s a trial. Cut 2, `read_bearing` no longer re-asks tesseract a
question `ocr_glyphs` already answered. Cut 3, the scale cache is written once per
geometry -- a tidy-up, under 1%. REFUSED with the measurement: the escape ladder must not
be truncated (14 of 19 clears came on a rung AFTER the first) and `SETTLE_SEC` must not be
shortened (`walk_leg` would capture mid-motion and a blocked step would read as walked).

**REMAINS.** (b) About 26% of a
338.4s streak trial (~89s) is still unexplained with every modelled component at
its floor — one push per turn, no compass retries, no ladder repeats. Cut 2 was
the strongest candidate; re-run one streak trial and see whether the residual
closes. (c) All three cuts are UNMEASURED against arrival. Two cannot plausibly
move it, but the spawn hint has one real mechanism: the route now starts ~24s
earlier after the load, so the NPCs have wandered 24s less.
`TRUST_RESET_SPAWN = False` is the control arm, and the A/B is cheap precisely
because the True arm is faster. (d) The recovery fan, ~79s each and ~33% of the
clock, is OPEN-7's and is not decided here.

**OPEN-24 — THE TACTICS-KIND CENSUS CANNOT BE WIDENED FROM WHAT IS ON DISK, and
the reason is a retention policy rather than a missing measurement (2026-09-17).**

`reveal_cards.TACTICS_KIND_MIN` (0.75) is measured on 48 frames from TWO matches.
Re-measured from the protected copy in `test_fixtures/reveal_kind_truth/`: 86
held-out right-kind readings against 258 wrong-kind, and at the shipped gate **0 of
258 wrong-kind clear it while 25 of 86 right-kind fall under it** -- never wrong,
abstains on 29%, which is the right direction for a reader whose output is logged
and analysed later.

**148 ROWS OF GENUINE GROUND TRUTH EXIST AND HAVE NO FRAMES.** `our_tactics_kind`
in `match_log.jsonl` is `decision.tactics_card.kind` -- what the engine CHOSE, so
it is ground truth in the same sense the two reveal sets are, and not circular
(§10.22). The opponent's field is READ and carries the bonus-of-3 values §4 says
cannot exist, so only our side counts. 147 carry a timestamp across 2026-08-26 to
2026-09-10 and would take the census from 2 matches to ~150 turns.

    ground-truth rows with our_tactics_kind     148   (swing 82, pitch 52,
                                                       fielding 8, speed 6)
    of those, with an archived frame              0
    archived runs                                 3, all 2026-08-28, zero
                                                     tactics plays between them

`SCREENSHOT_KEEP_RUNS = 3`, so the row is append-only and the picture is pruned.
The overlap is exactly zero.

**WHAT WOULD ANSWER IT, and it is a decision rather than a measurement:** keep ONE
reveal frame per tactics play, beside the row that names it. ~148 jpegs across two
weeks of play, `record_local_hand`'s existing never-raises-into-the-turn-loop
pattern -- and it touches the turn loop, which is the money path, so it is not
made unilaterally. Until then the gate stands on two matches, and the two RARE
classes are the ones the existing sets happen to cover best (fielding 25 frames,
speed 23) while the log's rarest are fielding 8 and speed 6.

**SHIPPED 2026-09-20 with the user's yes (ISSUES.md I-18(b), commit 6808a39):**
`orchestrator.record_reveal_kind` keeps one full reveal frame per tactics play under
`test_fixtures/reveal_kind_truth/auto/<kind>_<ns>.jpg`, stamps the row with
`reveal_frame`, never raises into the turn loop, writes nothing under
`BASEBALL_TEST_RUN`, and refuses past 200 files rather than pruning. Pinned by
`tests/minigame/test_reveal_frame_kept.py`. The census can now grow one frame per play.

**OPEN-25 — A STALE `match_in_progress` STILL REACHES `start_match` WITH NO
DEBIT, AND IT IS REPRODUCED. PREFLIGHT IS THE ONLY THING STOPPING IT (2026-09-17).**

The branch at `orchestrator.py` ~8176-8223 exists to stop exactly this: it proves
the flag is stale (the dealer's prompt is on screen, and the world HUD is never
drawn over a match), clears it, persists, and says it is *"letting the NEXT poll
take the ordinary debit path"*. **That next poll cannot reach the debit path.**
`acted_screen` is cleared only when the SCREEN CHANGES -- and never by `"other"`
(`orchestrator.py:7985`) -- so after the `continue` the prompt is still up, the C2
guard at the top of the branch is still armed, and the poll falls through to the
recovery press instead: `start_match` with no debit, no `max_spend` check and no
`save_progress`.

REPRODUCED with the run harness, same screens and the same real dealer prompt,
differing ONLY in the seeded flag:

    match_in_progress False (control)   11 start_match presses   balance 500 -> 450
    match_in_progress True  (stale)     10 start_match presses   balance 500 -> 500

**WHAT SAVES IT TODAY IS `preflight.py`, and nothing else.** It reports every
`progress*.json` claiming an open match and escalated from `warn` to `bad`, so a
run cannot START in the dangerous state -- verified against the live file this
morning. The harmful case therefore needs a FRESH process carrying a previous
run's flag with preflight bypassed. Within one process the flag being set implies
this process debited, and retrying the KEYSTROKE without re-debiting is correct
and deliberate (`tests/minigame/test_run_debit_and_scoring.py` pins it: *"the
retry must send the KEYSTROKE only"*).

**THE OBVIOUS FIX IS WRONG AND WAS MEASURED WRONG.** Clearing `acted_screen`
alongside the flag -- which is what the comment's own promise implies -- releases
the C2 double-debit guard, and the same harness then gives:

    flag False (control)   balance 500 -> 200      SIX debits
    flag True  (stale)     balance 500 -> 250

i.e. it converts an under-charge into the over-charge C2 exists to prevent, and
that test's own warning ("12 polls would have taken $600 of a $500 wallet") is
the failure it reproduces. Reverted, sha-verified, not shipped.

**FIXED 2026-09-20 with the process-local latch, and the hole was one line
further on than this ticket said.** The stale branch is not where the money
leaks -- it clears the flag correctly. The leak is the BARE `press("start_match")`
at the bottom of the same C2 block: `acted_screen` is cleared only when the
SCREEN CHANGES, so the poll after the clear re-enters C2 with both
`match_in_progress` tests now False and falls straight through to that press.
It retries the keystroke on the assumption that THIS PROCESS already paid, and
nothing checked it.

    seeded flag   presses   debited   12 polls at a genuine dealer prompt
    none            11        $50     control
    a previous      10        $ 0     <- OPEN-25, and max_spend never consulted
    run's

`debited_this_process` is False at startup and set by the debit itself, so it
CANNOT loop the way clearing `acted_screen` beside the stale flag did (that
measured SIX debits, 500 -> 200). The press now hands back to the ordinary debit
path instead, which checks the balance, honours `max_spend` and records the
spend. Both arms now debit exactly $50.

**AND IT FIXED A SECOND BUG THE TICKET NEVER NAMED.** The stale branch asked
only whether the flag was SET, never who set it -- so on the control arm it
fired on the flag run() had just written itself and cleared it mid-match. That
leaves `match_in_progress` False on disk during a live paid match, which is
precisely the state C5 needs to refuse a second $50. The control arm's flag now
survives, and that is a pinned check.

`tests/minigame/test_stale_flag_never_presses_unpaid.py`, five mutants, each
caught by a different assertion -- including one that produces $150 of debits,
so the test guards the OVER-charge direction as well as the under-charge.

**OPEN-9 — Can a recovery REPLACE the reset rather than precede it?** Local
recovery failed because its cost was ADDITIVE — when the fan failed, the reset
still happened. The variant that skips the reset on success has not been tried.

**OPEN-15 — `read_bearing`'s confidently-wrong reads had ONE cause and it is
fixed; the coverage cost is real, and the change is UNMEASURED against
arrival.** (2026-09-05. This is the first time the reader's accuracy has been
measured at all.)

Ground truth was built for 2571 of 3628 archived world frames from three sources
that had to agree: letters at a pitch measured from the compass's own TICK
LATTICE; tick PHASE, which pins heading modulo 10 deg with no letter involved;
and RIGHT-STICK STATIONARITY from `demos/*/input.json`, since only the right
stick turns the camera (§5), so across a run where `|rx|` never left the deadzone
the heading CANNOT have changed. 1057 frames were EXCLUDED, not guessed. The
truth validates against an instrument that knows nothing about OCR: of 726
letter-truth frames inside a stationary run, exactly **1** deviated from its
run's consensus by 3 deg or more.

**THE TICKS ARE THE PART THAT CANNOT BE MISREAD.** They sit at ODD MULTIPLES OF
5 DEGREES, so a letter sits HALF a spacing off the lattice and nine spacings span
the 90 deg between letters (1.5 + 6 + 1.5 — the ticks either side of a letter
hide under its circle). On `explore/20260904_152521_bar_area/00001.jpg` the fit
gives d = 32.3941 at rms 0.200px, so 9d = **291.55** against the 291.5 the
letters measure, from marks no recogniser has to identify. A letter's OWN strokes
arrive as tight clusters and wreck the fit unless peaks closer than half a
spacing are dropped. **This is NOT the bar correlation that was tried and
reverted** — that aliased because it asked the 10-degree ticks for the whole
answer. Here the ticks supply only the sub-10-degree phase, the LETTERS choose
the decade, and a frame with no letter still abstains.

**THE CAUSE: believing a lone letter.** Every confidently-wrong read came from a
frame where exactly ONE letter was recognised.

    1 letter    268 reads   116 confidently wrong   43.3%
    2 letters  1330 reads     0
    3 letters   546 reads     0

Two of the three worst anchors are not letters at all: a scenery blob at x=572,
in a frame whose real letters stand at 499.5 / 711.7 / 924.0, reads as 'S' and
the frame reports 233.0 where the truth is 84.8. **The ticks cannot catch this** —
a letter swapped for the one opposite is 180 deg, a whole number of spacings, so
the phase agrees with the wrong answer too. Fixed by `REQUIRE_TWO_LETTERS` plus
`POOL_THRESHOLDS` (sweep until two LETTERS, not two BLOBS, over a ladder reaching
down to 110, which `BLOB_THRESHOLDS` never reaches): over the truth frames,
confidently wrong **116 -> 2** and abstain **16.6% -> 5.0%**. Both axes moved the
right way at once, which is the thing to re-check if it regresses. Of the 149
frames the new reader refuses where the old one answered, 70 have truth and **the
old reader was WRONG on 62 of them**.

Corroborated independently: over 343 frames of `demos/walk_20260827_214446`
inside right-stick-quiet segments, reads that contradict their own segment's
median go from **96** (of 166 in-segment reads) to **2** (of 230) — more coverage
AND fewer wrong answers — and the two survivors are the two frames already known
to be wrong.

**IT IS NOT PERFECT.** 2 of 2442 reads are still wrong by 150 deg, both from two
SPURIOUS blobs a plausible pitch apart that corroborate each other, which is the
one thing a two-letter rule cannot see.

**WHAT IT COSTS — and do NOT quote the labelled-subset figure.** Over ALL 160
frames of `explore/20260904_152521_bar_area`, at the LIVE 1920x1080 geometry,
abstention goes **5.6% -> 15.6%**: about 13 probably-good reads lost per 160
against about 4 bad reads correctly refused. The "0.0% at 1920x1080" figure came
from the truth subset, and the truth criterion (two or more letters over the full
ladder) SELECTS precisely the frames the new rule can read — so it excludes the
refusals by construction. Net safety is still positive; the honest sentence is
"abstention triples at the live geometry, and that is the price".

Also carry: the headline 5.41% wrong is a STRESS TEST, not today's live rate. All
116 failures are at the demo archive's 1400x787, 0.73x the live linear
resolution. The mechanism is resolution-independent so it CAN fire live, but the
rate has not been observed live. Cost is 1.13-1.32x per read, under a second a
trial.

**REMAINS.** (a) UNMEASURED against route ARRIVAL — this is a sensor change, and
this project's record is 13 well-motivated changes that moved no number. (b) Two
holes the test does not guard: the "stop on two LETTERS not two BLOBS" rule
survives mutation (on the current fixtures the entire gain comes from the ladder
reaching 110, not from the stop rule the comments credit), and
`TICK_SNAP_MAX_DEG` is asserted nowhere. (c) The scale cache is now rewritten on
~39 of 40 reads against 14 before, because `9*d` is a continuous lstsq output —
on a file whose own comment says it lives on a NAS. That collides directly with
OPEN-8's cut 3, which makes the write once-per-geometry; merged together, the
frozen value becomes the tick-derived one.

**OPEN-17 — Does the executor's ARRIVAL HEADING cost the two bad nodes?
PARKED — do not build it before OPEN-14 reports.** The executor ends every leg
facing `steps[-1]["bearing"]`, while the references were shot at `cam[-1]`. The
gap, per leg:

    office_door    +0.99   |  portrait_room  +1.82   (arrival 1.000)
    bar_pool_room  +6.37   (route2 +4.08)            (arrival 0.667)
    bar_jukebox    -3.05   (route2 +1.80)
    dealer_table  -11.31   (route2 -2.66)

At the measured 18.6-20.8 px/deg that is 118-132px at `bar_pool_room` and
210-235px at the table, against `ALIGN_TOL_PX = 35` — and the ordering matches
which nodes arrive worst. It is also the right SHAPE for this project: the
intervention is ONE TURN and no translation, and GRAVEYARD's own summary is that
every failed change MOVED the character while both survivors move nothing.
**But the evidence is n = 2 legs and an ordering**, which is an association of
exactly the shape that killed `STALL_CHANGE` after a Fisher p = 0.00039 (§10.2).
`approach_goal` compounds it by aiming at `steps[-1]["bearing"]` and discarding
the other seven, 10.6 deg off the leg's own net direction.

**OPEN-19 — DOWNGRADED TO LOW VALUE, and the user was right to ask.** The question
was whether the pre-release-window `clear` inflated §6's high-magnitude walking rows (0.85
reads 3.3x the row below it, then 1.00 falls again -- not a shape a monotonic response
has). It is not worth rig time: `LEG_SPEED_MAX` has exactly ONE consumer, leg-speed
scaling, and §8(h) already measured that lever at "a 32% cut in walking bought 5% and a
worse mean". `walk_curve.py` also drives `left_y` only, so it cannot speak to OPEN-20's
diagonal question either. If it is ever re-run: position in the office corridor first --
the spawn FACES the typewriter desk, and an attempt from there measured 18 of 21 samples
at displacement 0.0, which is what a wedge looks like AND what a dead stream looks like.
Full text: `CLOSED.md`.

**OPEN-20 — THE EXECUTOR NEVER WALKS DIAGONALLY, AND THE HUMAN ALWAYS DID.**
Raised 2026-09-05 by the user, who says this was the original point of the
walking-response work: *"get claude to walk diagonally instead of walking straight
then turning right and walking forward."* Nothing was ever built.

**The executor cannot steer with the left stick, by construction:**

    graph_walk.py:687   st.walk_leg(0.0, -abs(speed), dur, ...)
                                    ^^^ lx is a hardcoded literal zero

So every step of every leg is: turn the CAMERA to the step's bearing, then push
the left stick straight ahead. `slow_traverse.walk_leg` takes `lx` and
`walk_steps.walk_forward` takes `strafe` — the machinery is already there and is
used ONLY by the escape manoeuvres (`unstick`, the slip ladder, `goaround`), never
by a leg.

**The evidence that the human did the opposite is already in this file.** On
`portrait_room -> bar_pool_room` the recorded `cam` is constant to **0.13 deg**
across the whole leg while `bearing` spans **6.59 deg**. The human did not turn
the camera at all; they held it still and steered entirely with the left stick.
The same section notes the final leg's `cam` is 86.73-87.01 across all eight steps
while `bearing` swings 71.99 -> 97.63 -> 75.46. `bearing` = camera heading +
left-stick angle, and the executor throws the second term away.

**Why this is not a rediscovery.** GRAVEYARD's only strafe row is *"blind crabbing
to get around an obstacle"* — an unguided escape push when already stuck, not
replay of a recorded vector. And this is the OPPOSITE shape to both closed
families: "steering while walking" is a mid-push feedback loop converting heading
error into position error, while this is open-loop with the camera FIXED; and
"chunking a leg into more cycles" adds accelerations, while collapsing a
turn-then-walk pair into one diagonal push REMOVES a turn and an acceleration per
step. Both survivors in the graveyard move nothing; this moves less than what it
replaces.

**IT IS A REGRESSION, NOT A NEW FEATURE.** `route_follow.py:184` already replays
`leg["lx"]`/`leg["ly"]`. An earlier generation of this code steered with the left
stick and `graph_walk` dropped the term. That is a much easier thing to argue for
than a new capability, and it means the shape has been run here before.

**LEAD WITH TIME, NOT ACCURACY — the accuracy argument does not survive its own
data.** Per-leg lateral loss from the discarded term is
`office_door->portrait_room` **-0.260** units, `portrait_room->bar_pool_room`
+0.099, `bar_pool_room->bar_jukebox` -0.038, `dealer_table` -0.010,
`office_door` +0.020. **The leg with the LARGEST loss is the one that arrives
20/20.** So loss does not predict arrival, and this is NOT a clean explanation of
the two bad legs — an earlier draft of this entry let it read as though it might
be. What survives on accuracy is narrower: `portrait_room->bar_pool_room` has the
highest median angle of any leg at 5.9 deg, a consistent BIAS rather than
cancelling wobble.

The time argument is the strong one. Replaying the vector means one camera turn
per LEG instead of one per STEP — **5 turns instead of 40** — against `turn_to`'s
11.4s of an 85.6s trial (§8(h)).

**What it would take.** `route3_steps.json` already stores `cam` per step, so the
inputs exist. Hold the camera at `cam`, drive `left_x`/`left_y` as the recorded
vector, and the per-step turn disappears. Then A/B against turn-then-walk: 10
trials per arm, interleaved, verified arrivals, reported by failure class (§10.3,
§10.5).

**Note the left stick's DIAGONAL response is unmeasured.** §6's table is
`left_y`-only, so it does not cover this — see OPEN-19, which is why that one is
downgraded rather than closed.

**OPEN-21 — THE GOAL LEG IS NOT THE RECORDED LEG; the A/B against replaying
it is RUNNING (started 2026-09-07 09:35).** On every leg but the last,
`follow()` replays the recorded steps through `walk_link`. On the last it does
not: `approach_goal()` walks a straight line at `steps[-1]["bearing"]` (75.5,
10.6 deg off the leg's net direction of ~85) in 0.4s chunks with 0.3s sleeps —
the re-accelerating chunk shape GRAVEYARD records as walking a leg SHORT — for
up to 1.6x the recorded 4.07s, checking for the prompt as it goes; then
`reach_table()` sweeps. It predates the jukebox-leg restoration, when the table
leg started 0.7 units early and an over-long straight approach was the
workaround, and it has never been A/B'd against the recorded leg.

What OPEN-14 measured about it, from `overnight/streak_table.log` and
`overnight/census/table_leg_ends_20260907.json`: 37 executions, and in **37 of
37** the approach exhausted its budget ("stepped 6.8s of a 6.5s budget without
finding the prompt"); the prompt was found by stepping **0** times and by the
sweep **once** (trial 2). Of the 37 post-sweep frames, **17 were wedged** (7-11
keypoints); the visual census (two Haiku readers a frame, tiebreak on
disagreement) read dark 12 / bar counter 8 / floor 5 / NPC 3 / wall 1 / dealer
visible without prompt 4 / prompt 1 / unresolved 5. Pitch-down is a real
minority mode; the majority is pressed into the bar or into darkness.

**The arm:** `graph_walk.GOAL_LEG_AS_RECORDED` (ships **False**) routes the goal
leg through `walk_link` like every leg that arrives; the sweep still follows in
BOTH arms. Not a GRAVEYARD shape: it steers nothing mid-push and REMOVES a
chunked approach rather than adding chunks. **The harness:**
`overnight/ab_goal_leg.py` — shipped vs recorded, 10 trials an arm interleaved,
setup to `bar_jukebox` at attempts=9 (a setup miss is INVALID), ONE execution
of the leg through `_harness.walk_leg_under_test`, scored by `confirm()` =
`at_table()` on the post-sweep frame plus an `at_table()` re-read, 1200s
external ceiling, Fisher exact. Result: `overnight/ab_goal_leg.json`, log
`overnight/ab_goal_leg.log`, frames `overnight/goal_leg_failframes/`
(`at_dealer_table_*` = PRE-sweep leg end, admissible; `_postsweep_*` = what
`confirm()` judged; `success/ok_*` = the leg end on arrivals).

Two evidence changes landed with the flag (da5b7ec), each behind a test that
drives `follow()`/`follow_verified` with stubs and four mutants caught: the
GOAL's leg-end frame is now captured and published BEFORE `reach_table`, and
`follow_verified`'s success frame became the published leg end instead of
`before`. **The second was half wrong, and the suite caught it the same
morning** (142/143, `test_success_control_frames.py`): `before` — the start
pose, which is why both OPEN-14 `ok_dealer_table` frames identified
`bar_jukebox` — was DELIBERATE, the control for the start-pose-variance
question in §8(i), and its own test says so. Replacing it threw one control
away to gain another. The fix keeps both on both outcomes
(`success/start_<node>` + `success/ok_<node>` on arrival, `start_<node>` +
`fail_<node>` on failure); it is written and waits in
`drafts/pending_after_ab/` until no live run imports `graph_walk` (10.21).

**RESULT (2026-09-07, 20 trials, paused once at 14 and resumed in the same
order): NO ARRIVAL DIFFERENCE, A THREEFOLD COST DIFFERENCE.** Scored two ways
(`overnight/ab_goal_leg.json`, `tools/goal_leg_sheet.py`):

    as the harness scored it (at_table after the sweep)   shipped 1/8   recorded 1/9   Fisher p = 1.00
    prompt ON SCREEN at the leg's end (pre-sweep frame,
      mask + OCR; the leg-level criterion)                 shipped 2/9   recorded 1/9
    leg time, median [range]                               189s [68..277]   65s [26..74]
    setup to bar_jukebox, median [range] (same code)       306s [59..974]   157s [58..1019]
    invalid                                                2 (setup miss, ceiling)   1 (setup miss)

Both arms miss about nine in ten. The executor is not the lever; where the
leg ends relative to the prompt zone is, and nobody has measured that zone —
`overnight/prompt_zone.py` does (agreed 2026-09-07). The recorded leg costs a
third of the approach per attempt, which matters for retry depth; that is a
reason to flip the flag for COST, not for arrival, and it is the user's call.
What the 18 pre-sweep frames show: the prompt on screen and missed by the
mask (trials 1, 6 — the OCR path fixes those), stopped short at an NPC (2),
walked into the neighbouring table (3), and a spread of near-table endings
without a prompt (the rest). The ceiling censored the shipped arm twice. If the recorded arm wins, the next run is the full-route streak with
the flag on — and OPEN-14's ceiling lesson applies: a goal-leg retry is a full
reset and route re-walk, so the ceiling must be attempts x route-time or the
goal leg needs local retries.

**OPEN-22 — THE PROMPT ZONE, MEASURED (2026-09-07): its near edge sits five
hundredths of a walk-unit AHEAD of where the recorded goal leg stops, the
prompt is screen-fixed and offered on proximity alone, and the leg's endpoint
scatters by a table width.** `overnight/prompt_zone.py` — a star around the
recorded leg's endpoint (the endpoint first, then 0.05u left/right, 0.10/0.20u
back, 0.05u forward, stick-relative, wedge-checked), five headings a point,
mask + OCR verdicts, three walks (`overnight/prompt_zone.json`,
`prompt_zone_points.jsonl`, frames `overnight/prompt_zone_frames/pz_w*`):

    walk 1   45 readings   no prompt   endpoint at the NEIGHBOURING table, dealer ~70 deg left
    walk 2   50 readings   no prompt   the neighbouring table again, the waitress in the passage
    walk 3   50 readings   endpoint: none at 5 headings; +0.05u forward: PROMPT at 4 of 5
             headings spanning 80 deg (mask 0.31-0.47 with ink 0.011; OCR 3 of 5)

The +0.05 frame shows the character facing a pillar and a grey wall with the
prompt centred on screen: the label is a HUD element and the game offers it on
distance to the dealer, not on facing. So heading was never the constraint of
the last leg — `reach_table`'s 19-heading sweeps were searching the wrong axis
— and the recorded leg, when it lands at the dealer's table, stops just short
of the zone. When it does not (walks 1-2, A/B trial 3) it lands at the round
table beside hers, from the pose it was given at the jukebox.

**Three launches before this one measured nothing, from two instruments of
mine:** `len(places.keypoints(img))` is 2 (a (keypoints, descriptors) pair), so
every point read "wedged"; and `tools/prompt_ocr_ab` set `BASEBALL_TEST_RUN`
at import, switching stick injection off inside the live harness after the
leg (§5, §10.1). Both fixed and pinned; the fourth launch is the first valid.

**Today's setup census** (`overnight/census/setup_leg_ends_20260907.json`, 315
leg-end frames from the route walks): the JUKEBOX leg ended WEDGED in 69 of
106 executions (median 10 keypoints) against 3 of 77 on the pool-room leg —
that is why reaching `bar_jukebox` took 2-8 attempts and up to 1065s today
where OPEN-5 had 9/9. Unmeasured whether it is session variance or the
restored leg's own endpoint; the frames are on disk.

**(b) IS CLOSED AS DESIGNED (measured on Snoopy, 2026-09-07 evening):** the
neighbouring table cannot be a localiser-confirmed node. Ten references at the
landing pose (five headings x two walks) fail leave-one-out at ratios 1.00-1.22
against `MIN_RATIO` 1.35, with `bar_jukebox` the runner-up every time and one
frame naming it outright; non-disruption (333 frames) and discrimination from
the dealer's table both pass (`overnight/census/side_table_refs.json`,
`tools/side_table_refs.py`). It is the office corridor/door shape: a table
apart looks the same to ORB. What survives of (b) is the PATH from that landing
to the prompt, measurable without naming (`overnight/side_table_leg.py`), and a
correction that fires on "no prompt after the extension". **Also refuted the
same evening** (`tools/landing_signature.py`, 38 landing frames on Snoopy): the
idea that `identify()` after the goal leg tells the two landings apart — most
landings of BOTH kinds read None at 60-136 matches; only one walk's side-table
frames named `bar_jukebox`. There is no cheap landing classifier.

**Candidates, each an A/B, none built:** (a) extend the recorded goal leg by
~0.10u — the edge is at +0.05, walk 3's +0.05 point was not wedged; (b) give
the neighbouring table a place name from these frames and record the short leg
from it to the dealer, so the router finishes from wherever the leg lands;
(c) the jukebox leg's wedge. (a) is one constant and moves the character 0.1u;
(b) is the project's own machinery; (c) is the setup killer. The order is the
user's call.
