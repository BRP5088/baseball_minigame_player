"""Walk a recorded CHAIN of reference frames by LOOKING AFTER EVERY PUSH.

Dead reckoning replays a recorded (bearing, duration) and looks only at the
leg's end; it arrives 5/10 per route after 13 measured changes (GRAVEYARD.md).
This is the closed loop the user asked for instead: stop, look, decide, push.
Position comes from the screen, never from the stick.

WHY THIS IS NOT ONE OF THE TWO CLOSED FAMILIES IN GRAVEYARD.md
--------------------------------------------------------------
* "Steering while walking" died because a 30 deg heading lag became METRES of
  position error. Nothing here steers mid-push: the camera is turned, the stick
  is held for PUSH_SEC, and only then is a frame taken.
* "Chunking a leg into more turn-then-walk cycles" died because each chunk
  re-accelerates from a standstill and the leg walks SHORT. That failure is a
  failure of DEAD RECKONING: a timer said the leg was done. Here the PICTURE
  says when a waypoint is reached, so a push that covers less ground than the
  recording's simply does not advance `k` and is repeated. Walking short costs
  time, not position.

WHAT IT NEVER DOES. No reset, no Square/Triangle/OPTIONS, no pause menu, no
write to world_map.json. The only button it presses is Cross, which is the JUMP
button (CLAUDE.md §8(g): four presses spiked 10.1-12.5 against a 4.67 idle
baseline).

THE ARRIVAL AUTHORITY IS THE PROMPT, AND IT STOPS EVERYTHING AT ONCE.
`table_prompt.at_table()` is checked on the very first frame (before any push --
a recorded chain may already END at the prompt, so the character can be standing
in it when the walk starts) and on every iteration once the walk is within
TABLE_CHECK_TAIL waypoints of the end. The instant it is True the function
returns: no further turn, no further push, no strafe. The user watched the
character win the table and then walk away from it; nothing moves after the
prompt is on screen.

EVERYTHING THAT TOUCHES THE CONSOLE IS INJECTABLE, and every default is resolved
INSIDE walk() at call time. A module-level knob captured in a `def` line is
bound once at import, so a test or an A/B that redirects it changes nothing and
nothing says so -- CLAUDE.md §10.18, measured on `leg_reliability`'s `path=STORE`
and on `press(post_delay=ACTION_DELAY)` before that.
"""

import json
import math
import os
import time

import pose

# ---------------------------------------------------------------------------
# Constants. Each carries the measurement it comes from; none is invented.
# ---------------------------------------------------------------------------

# CLAUDE.md §6, the walking table: 0.45 magnitude moves 70.6px per 0.40s push
# with a spread of 15, and walking is linear to ~0.75. Repeatability collapses
# above 0.60, so 0.45 sits inside the measured-repeatable band.
PUSH_MAG = 0.45
PUSH_SEC = 0.40                 # the duration that table was measured at
# SETTLE PROBE (patch54), OFF unless BASEBALL_SETTLE_PROBE is set in the
# environment. After each push it captures and fits at these delays measured
# FROM THE STICK RELEASE, and writes the inlier counts into the journal row, so
# a real walk -- with the controller keeping the character on the route -- says
# whether SETTLE_SEC's 0.35 s is needed. It makes the walk slower, so it is a
# separate short run, never an arm of a measured batch.
SETTLE_PROBE_ENV = "BASEBALL_SETTLE_PROBE"
SETTLE_PROBE_DELAYS = (0.00, 0.05, 0.10, 0.15, 0.25, 0.35)

# Consecutive UNMEASURABLE fixes (locate() returned None) before an escape.
# Not measured -- there is no population of "how many blind frames in a row is
# normal" yet. Exposed as a knob and logged so the first live run measures it.
MISS_MAX = 3
# Consecutive fixes that did not advance k before an escape. Same status.
STALL_MAX = 4

# pose.align_lateral's CLOSED-LOOP gain (pose.py:152): 2400 px per
# unit-magnitude-second. The open-loop figure (126px per 0.30 x 0.35s, i.e.
# ~1200) is WRONG for control -- at it the alignment loop oscillated with
# growing amplitude (+175 -> -201 -> +211 -> -215). Imported, not copied.
LATERAL_GAIN = pose.PX_PER_STRAFE_SEC
LATERAL_MAG = pose.STRAFE_MAG            # 0.30, the magnitude that gain was fitted at
# A push under ~0.10s does not move the character at all (pose.ALIGN_MIN_SEC),
# so a correction shorter than this is a no-op that reads as a correction.
# align_lateral uses the minimum push rather than giving up: measured better
# (bailing stopped at 84-116px).
LATERAL_MIN_SEC = pose.ALIGN_MIN_SEC
LATERAL_CAP_SEC = 0.3           # never lunge; a narrow passage punishes overshoot
LATERAL_TOL_PX = pose.ALIGN_TOL_PX       # 35.0 = 1.8 deg at 18.6-20.8 px/deg

# PIXELS PER DEGREE OF YAW at the live 1920-wide capture. CLAUDE.md §8(j):
# 18.6-20.8 px/deg over 7 pure camera-turn pairs with the character stationary,
# corroborated by camera_fov.json (1920 / 102 deg = 18.8). This is the value the
# stop look-around's un-yaw already used as a bare literal; it is NAMED here so
# that un-yaw and the end turn below cannot drift into two different numbers.
PX_PER_DEG = 19.7

# AT THE END, TURN TOWARD THE DEALER INSTEAD OF STRAFING.
#
# chains/route_user_1853 ends with a turn-only stop at 196 (heading 89.5) and
# pushes at 197, 200, 203, 204 toward the dealer, who sits across a table. The
# prompt is offered on PROXIMITY and is screen-fixed (OPEN-22), and at_table()
# ends the walk the instant it is True.
#
# Four trials on 2026-09-07 22:00-23:20 verified the 196 stop and then read the
# dealer's scene 460-777 px to the LEFT of where the reference has it (dx -777,
# -490, -481, -512 at 112, 52, 48, 41 inliers: the t03_1788833772 and
# t01_1788837390 journals, iterations 49-59 and 50-57, and two earlier ones).
# Every one strafed LEFT at LATERAL_CAP_SEC without the offset shrinking, pushed
# along the recorded 89.5 into the bar counter, and ran the plan out by count.
# None found the prompt. The user, watching: "they made it to the mini game
# table but weren't close enough to get the prompt ... They turned directly into
# the bar and just kept getting stuck." A person facing that turns to FACE the
# dealer and walks up to her.
#
# A 0.3 s sidestep is ~324 px at the closed-loop gain and CANNOT close 777 px
# five times over; a 39 deg turn closes it once, and a turn moves the character
# NOTHING -- the same argument that puts turn-early ahead of every escape rung,
# and GRAVEYARD's own summary that the only two navigation changes which ever
# survived move nothing.
#
# THE THRESHOLD SITS BETWEEN TWO SMALL POPULATIONS (§10.4): the one arrival at
# that spot carried |dx| 286-342, and every one of the four failures 460 or
# more. n = 4 failures and 1 arrival, so 400 is a gap between two THIN
# populations, not a calibrated gate -- it is recorded in the journal row on
# every firing so the next run measures it.
END_TURN_PX = 400.0
# The largest offset seen is 777 px = 39.4 deg, so one iteration may never turn
# further than this: a wrong match with a huge dx must not spin the camera.
END_TURN_MAX_DEG = 45.0
# ... and at most this many end turns in a walk, for the same reason. After
# three, the ordinary lateral correction takes over.
END_TURN_MAX = 3

# ---------------------------------------------------------------------------
# THE VERTICAL OFFSET (patch57). Ships OFF, and in REPORT mode when turned on:
# --flag PITCH_CORRECT writes what it WOULD have done and presses nothing.
#
# Every fit carries dy and the loop has never read it. dy is measured against
# the WAYPOINT'S OWN FRAME, so dy -> 0 means "hold the pitch the recorded drive
# held here" -- not "level the camera", which would fight the drive's own pitch
# (the larger term: between-waypoint medians run +318 px to -134 px, while the
# per-walk drift is an 86 px p10-p90 spread at one waypoint; 1,674 credible
# fits over 40 journals).
#
# IT MOVES THE CAMERA AND NOTHING ELSE. GRAVEYARD's summary is that every
# navigation change which failed MOVED THE CHARACTER, and both survivors move
# nothing. In the shipped mode it does not move even the camera.
PITCH_CORRECT = False
# "report" writes the row and presses NOTHING. "act" presses -- but only if the
# two measurements below exist; see pitch_correction. The mode alone can never
# unlock a press.
PITCH_MODE = "report"
# ---------------------------------------------------------------------------
# THE TWO MEASUREMENTS THAT GATE ACTING. Both UNMEASURED, both None, and while
# either is None nothing is ever pressed. tools/pitch_probe.py measures both in
# one two-minute standing-still run and prints the two lines to paste here.
#
# PITCH_STEP_PX -- how many px of dy ONE PITCH_PRESS_SEC press produces.
# THE PROJECT'S OWN NUMBERS SAY IT IS BIG, and that is why this is a gate and
# not a guess. STAIRS_APPROACH.md ("PITCH IS UNCONTROLLED IN PRODUCTION",
# "Nobody currently knows how to command a specific pitch") records that three
# readings of how many 0.05 s presses span the whole vertical travel disagree:
# 8 (input_controller.py:993), 20 (input_controller.py:1009-1014) and 36
# (STAIRS_APPROACH.md, live). Over a vertical fov of 69.57 deg at 15.5 px/deg
# that is 30, 54 or 135 px PER PRESS -- every one of them at or above the 28 px
# floor below. A fixed step S only avoids overshoot while S <= dead-band, so a
# rule that fired one press outside a 28 px band would HUNT: press, cross the
# band, press back. pose.py:145-151 has already measured that failure on the
# lateral axis ("the loop OSCILLATED, growing each time: +175 -> -201 -> +211
# -> -215"). Hence pitch_dead_band() below, which makes the band the step.
PITCH_STEP_PX = None
# PITCH_DOWN_DY_SIGN -- the SIGN of the change in dy that one look_down press
# produces (-1 if look_down makes dy fall). NEVER MEASURED: chain.Fix spells
# out a `dx SIGN` paragraph and there is no dy one, in chain.py or in pose.py,
# and no site in this project has ever recorded a live dy against a pitch press
# -- unlike the LATERAL axis, whose strafe/forward/back dx,dy table pose.py
# measured. The optics ARGUMENT says -1 (a camera pitched up puts scene content
# lower in an image whose y grows downward, so dy > 0 wants look_down), and
# every row records that as `hypothesis` so the probe can be checked against it
# rather than assumed to agree. Backwards, the rule DOUBLES the error.
PITCH_DOWN_DY_SIGN = None
# ---------------------------------------------------------------------------
# PIXELS PER DEGREE OF PITCH. DERIVED, not measured, and deliberately NOT
# assumed equal to PX_PER_DEG above (the yaw figure; this file states it once
# and only once, which is why it is not repeated here): camera_fov.json gives
# 102 deg across 1920, so a rectilinear pinhole has f = 960/tan(51 deg) =
# 777.4 px and a vertical fov of 2*atan(540/777.4) = 69.57 deg, i.e.
# 1080/69.57 = 15.52 px/deg -- the same whole-frame construction that gives the
# horizontal 1920/102 = 18.82 which the measured 18.6-20.8 corroborates. Two
# other readings exist and are quoted rather than hidden: the CENTRE gradient
# f*pi/180 = 13.57 px/deg (equal on both axes, as a pinhole demands), and
# PX_PER_DEG scaled by the fov ratio = 16.25. THEY DIFFER BY UP TO 20%
# ((16.25-13.57)/13.57 = 0.197). Nothing that moves depends on this: the
# dead-band is in PIXELS and the press is in SECONDS, so this constant only
# colours the `deg` a journal row reports.
PITCH_PX_PER_DEG = 15.5
# A FLOOR under the dead-band, and it is a PLACEHOLDER, not a derivation. The
# real rule is pitch_dead_band(): the ACTUATOR sets the tolerance, which is
# what pose.py:155-165 actually says about its own 35 px ("TOLERANCE IS SET BY
# THE ACTUATOR, not by the measurement ... 35px is where the loop can actually
# finish"). An earlier draft mirrored the 35 px as "the same ANGLE, 1.8 deg" --
# but 1.8 deg is an incidental unit conversion in that file, not the reason the
# number was picked, so mirroring it imported a coincidence. This floor is of
# the same ORDER and binds only if the measured step comes in under it.
PITCH_TOL_MIN_PX = 28.0
# The smallest hold this project has ever seen move the camera: a COPY of
# input_controller.PITCH_STEP_SEC, which home_pitch and level_pitch both press
# with. Copied rather than imported because chain_walk imports input_controller
# only inside walk() (doorway_pitch.LOOK_UP_POST_DELAY is the same copy with
# the same warning): if that literal changes, this must follow it by hand.
PITCH_PRESS_SEC = 0.05
PITCH_POST_DELAY = 0.30          # level_pitch's own look_up post_delay
# NEVER LUNGE, mirroring LATERAL_CAP_SEC = 0.3: one iteration's correction is
# capped at this hold however large the offset, so one bad fit cannot swing the
# camera. With PITCH_SEC_PER_DEG None the cap is not the binding limit -- one
# PITCH_PRESS_SEC hold is -- and it becomes binding the moment a gain is set.
PITCH_CAP_SEC = 0.30
# SECONDS OF right_y PER DEGREE: **UNMEASURED**. There is no vertical analogue
# of turn_curve's table. None means BANG-BANG: one PITCH_PRESS_SEC hold in the
# direction that reduces |dy|. It is NOT a third gate -- with the step and the
# sign measured, the bang-bang rule is safe by the D >= S condition above --
# but a second pitch_probe run at several hold lengths gives it, and the same
# code then becomes proportional, capped and floored, with no further edit.
PITCH_SEC_PER_DEG = None
# The two STICK AXES this rule may press. Both are right_y deflections in
# input_controller.STICK_AXES; NEITHER is in BUTTON_BITS, so the module still
# presses exactly one BUTTON (Cross) and NeverTouchesTheForbidden checks both
# halves. Indexed by the sign convention below, so the tuple is load-bearing.
PITCH_ACTIONS = ("look_up", "look_down")

TIME_CAP = 400.0                # the spec's "timed out" boundary; the harness
                                # kills the child at 420s from OUTSIDE (§10.14)

# chain.locate()'s own default window. k may never advance past k + WINDOW in
# one step: a single fix is one picture, and letting it skip an arbitrary
# distance ahead would let one wrong match teleport the plan to the end of the
# chain -- exactly the "reached is a routing claim, not evidence of position"
# failure in CLAUDE.md §8(e).
WINDOW = 3
# ADVANCE at most this many waypoints per iteration, whatever the sensor says.
# One push is 0.18 u and the user's drive put waypoints ~0.2 u apart, so a push
# passes about ONE waypoint. Trial 1 (2026-09-07 19:05) advanced 3 per push on
# fits of 13-28 inliers, ran ~6 waypoints ahead of the character in 5 pushes,
# and then found nothing in a window the character had not reached. Lagging is
# safe (the window still holds the truth); running ahead was fatal.
ADVANCE_MAX = 1
# A fix under this many RANSAC inliers neither advances k nor steers. It is the
# 5th percentile of TRUE-position inliers on the route chain's own held-out
# frames (overnight/census/chain_user_1853_closed.json: near p05 29, median
# 146; far median 7) -- measured on this chain, not chosen. Trial 1's junk fixes
# (13 and 19 inliers, dx -66 and -131) strafed the character into the wall.
FIX_MIN_INLIERS = 29
# On a miss or a weak fix, look BACK this many waypoints before counting it,
# and let k REGRESS if the look-back fits. An over-advanced k was otherwise
# permanent: the window only ever looked forward.
LOOKBACK = 2

# THE PROMPT IS CHECKED ON EVERY ITERATION (None = no tail gate). It used to be
# asked only when the target was within 3 waypoints of the end; if the sensor's
# k lagged while the character already stood in the prompt, the loop would
# stall, escape and walk away from a won table -- the exact failure the user
# watched under dead reckoning. at_table() costs milliseconds and measured 0
# false positives on 693 frames at non-table nodes (CLAUDE.md §3), so the gate
# bought nothing. THEN IT DID: 2026-09-08 a detector change fired at k=58 (the
# office doorway facing the L&B storefront) and the walk "arrived" 47 s in.
# at_table() is the $50 gate. Every true closed-loop arrival on disk (64) had
# its target at 197-204 when the prompt appeared; the false one had 61. A tail
# of 30 waypoints (targets >= 175 on the 205-waypoint chain) sits 22 under the
# lowest true arrival, so a lagging estimate has that much room, and no false
# positive anywhere before the bar tables can end a walk.
TABLE_CHECK_TAIL = 30

# THE PLAN. The recorder samples every 0.25 s and ~40% of an executor-recorded
# chain is STATIONARY: the camera turns between steps and the 0.35 s settle
# after each push. Servoing onto those frames would turn to each intermediate
# heading of a corner and PUSH along it -- a curve into the inside wall. So the
# chain is compiled into a plan: walking frames every STRIDE, and each
# stationary run collapsed to ONE turn-only target carrying the run's last
# heading (turn on the spot, no push, no locate). STRIDE 1 costs no extra
# iterations because the sensor's fix.k, not the target, drives the advance.
STRIDE = 1
# PUSH-SPACED TARGETS. A push target is emitted once the recorded stick has
# covered PLAN_STEP_UNITS since the last one (|ly| x dt, the same stick-seconds
# unit as PUSH_MAG x PUSH_SEC), so one push reaches about one target whatever
# speed the human drove at. The user's drive held ~0.29 stick at 0.25 s per
# frame = 0.07 u per frame, four frames a push: with one target per FRAME the
# estimate fell four waypoints behind per push (trial 1b, 2026-09-07) and the
# plan never reached the turn at the door. Frames without stick data fall back
# to every STRIDE frames.
PLAN_STEP_UNITS = PUSH_MAG * PUSH_SEC
RECORD_PERIOD_SEC = 0.25          # chain_record's default when a row has no t
# When the sensor is BLIND (no credible fix) the loop dead-reckons: it assumes
# the push it just made reached its target, up to this many pushes in a row,
# before it starts treating the silence as a blockage and escapes. A door
# panel or a dark wall is featureless (7-16 keypoints, CLAUDE.md §8(g)), and
# trial 1b showed the sensor goes blind exactly where the plan needs to turn.
BLIND_MAX = 6
# Inside the last END_TAIL_TARGETS plan targets a blind push is capped at
# END_BLIND_MAX: past the final stop, overshooting means the bar's back door
# (batch 5b trial 3, 2026-09-07 20:20), and the prompt check runs every
# iteration anyway.
END_TAIL_TARGETS = 6
END_BLIND_MAX = 2
# A credible fit at the waypoint BEHIND the target whose scale says the scene
# is this much larger than in that frame means the character is well past it:
# count it as reaching the target. Arriving trials advanced through the bar at
# scales 1.0-1.5; trial 3 stalled at 166 with 2.1 and 2.6 while at ~181.
PAST_SCALE = 1.6
# NEAR A WALL, NEAR A STOP: when the last credible fit had scale >= WALL_SCALE
# (the scene that much larger than in its frame: the wall a push away) and the
# next turn stop is within NEAR_STOP_TARGETS plan entries, a blind sensor gets
# ONE dead-reckoned push, not six, and then the stop. Batch 6 trials 4 and 7
# lost credibility at 100-104 with scales 2.9 and 2.6 and pushed four times
# into the portrait wall the user's drive stops at; arrivals turned there while
# still seeing the room. Scale alone does not separate them (arrivals saw
# 2.4-3.7 too); blindness right after it does.
WALL_SCALE = 2.5
NEAR_STOP_TARGETS = 3
# A BACKWARD step: the one move that creates clearance from a wall. Batch 6
# trials 4 and 7 stood nose-first against the portrait wall; looks, a wait,
# retries and sidesteps could not open the view; a step back would have.
BACK_SEC = 0.5
# A weak fix (under FIX_MIN_INLIERS) still corroborates the plan when it has at
# least this many inliers: right-but-thin fits in trials 1-3 read 17-36, junk
# read 6-13 (n ~ 15, provisional; re-measure from overnight/chain_journals/).
WEAK_MIN_INLIERS = 15
# Consecutive iterations with no credible fix AFTER the blind budget is spent
# before the walk declares itself LOST (three escape cycles). Off the route
# nothing can match; burning the rest of the cap only delays the next trial.
# One full ladder per blockage. The ladder fires a rung every MISS_MAX misses
# (or STALL_MAX stalls), so a budget of 9 reached the third rung on the very
# iteration it ended the walk: every trial lost tonight at Wanda (an NPC
# parked on the route at k=112, three in a row) or at the jukebox (k=171-173,
# three in a row) had tried ONE rung whose effect was observed, and which
# rung depended on how many escapes the trial had spent earlier. Budgets of
# MISS_MAX*4+1 and STALL_MAX*4+1 let all four rungs fire and be seen.
LOST_MAX = 13
# THE LOST RESCUE: ONE terminal rung, after the ladder and before the walk
# ends. Every lost trial of 2026-09-08 is one shape (census_after_129_notes.md
# and its readers): pinned against geometry or an NPC at k 100-140, the view
# unchanged for thirteen iterations, and the ladder unable to open it — a
# credible fix follows `escape:back` 0 of 27 times in the bar stretch, `right`
# 5 of 69, `left` 36 of 106. What a human does there is back STRAIGHT OUT a
# full step and look for the room they were facing. ONE per walk: a second
# loss ends the walk exactly as before, so an arriving trial pays nothing.
LOST_RESCUE_MAX = 1
# Two of the existing step-backs, not a new physical constant: one BACK_SEC
# has never freed a pin (0 of 27), and the readers describe backing out of a
# doorway, not off a wall.
LOST_RESCUE_BACK_SEC = 2 * BACK_SEC
# ... and the looks search from a little BEHIND the last CREDIBLE sighting,
# because when this fires the estimate is typically 20-60 waypoints ahead of
# the character (turn-early and blind advances carried it there), so a window
# around k is a window around somewhere the character has never been. The
# window reaches WIDE_AHEAD past its start, which is the same span the wide
# relocalisation searches.
# None = the WHOLE chain behind the last credible k (patch43b). b16 t19: a
# wrong 191-inlier wide relocalisation made last_cred_k 136 while the
# character stood at ~120; a six-waypoint lookback could never find it.
LOST_RESCUE_LOOKBACK = None
# NO PROGRESS: this many consecutive iterations without k advancing (stalls,
# misses, escapes, retries, all of it) ends the walk as STUCK, whatever the
# sensor sees. LOST covers a blind sensor; this covers a wanderer whose sensor
# still sees the room -- pushing at a door, circling a stop. Arrivals advance
# at least every few iterations; twelve without is ~20 s of nothing.
NO_PROGRESS_MAX = 17
# CONSISTENT THIN FITS STEER. A single weak fix never steers (its dx is junk:
# -847 px at 7 inliers). But CONSISTENT_N consecutive fits of at least
# WEAK_MIN_INLIERS whose dx all exceed the tolerance on the SAME side are
# evidence one junk fit cannot give: batch 5e trials 13-14 drifted right of the
# stairs with five fits in a row at 15-30 inliers reading -120, -159, -204,
# -219, -323 px and were refused all five times. Strafe once by their median.
CONSISTENT_N = 3
# The same rule for JUNK fits (6..14 inliers, under WEAK_MIN): four in a row on
# the same side. Measured over the 53 journals of batches 4-7: four such fits
# in a row never occur in an ARRIVING trial (0 of 24) and occur five times in
# the failing ones (the office-corridor drift cluster, four failures of ~30 s
# each: dx -47 -50 -103 -198 -241 -252 -367 -390 at 6-16 inliers, refused
# every time). Three in a row do occur in arrivals (2), so four it is.
JUNK_CONSISTENT_N = 4
JUNK_MIN_INLIERS = 6
# A turn stop is verified against its own frame after the turn; if nothing
# credible fits, the loop turns back, pushes once more along the walking
# heading and retries, this many times, before accepting the turn unverified.
TURN_RETRY_MAX = 3
# ... and when the verification is exhausted with nothing credible, the stop is
# NOT where the estimate is: k rewinds to the last credible waypoint and the
# loop re-approaches. A rewind moves the ESTIMATE, not necessarily the
# character, so without a bound one stop could be circled forever. After this
# many rewinds the stop is advanced unverified as it always was, and LOST,
# STUCK and the time cap still end the walk. It is spent PER STOP and NEVER
# REFUNDED (see `rewinds_at`): a counter that resets when the walk visits
# another stop is not a bound at all, and measured 22 rewinds against this 2.
# A LIVELOCK BOUND, not a measured
# quantity: two re-approaches is what a 400 s cap can afford beside the ~90 s
# an arriving trial takes, and the stop table (audit/stop_table.md) says a
# stop taken unverified arrives 1 in 14 at 129 and 0 in 6 at 166, so a third
# re-approach is worth less than the seconds it costs.
# SHIPPED AT ZERO (2026-09-08, batch 15). Measured at the bar-entrance stop
# 129: batches 12-14 took it UNVERIFIED and arrived 11/11; batch 15 REWOUND
# there 3 times and arrived 0/3, each lost at 109 on the re-approach -- the
# rewind walks the character back into the NPC it had just met, and every
# action on a re-approach is unevidenced so turn-early never re-arms (b15 t4,
# agent_progress/closed-loop/review/notes_cur_t04_1788853535.md). The
# mechanism stays; its tests run it at 2 for themselves.
STOP_REWIND_MAX = 0
# LOOK AROUND AT AN UNVERIFIED STOP before believing "occluded / past": yaw
# these many degrees each way, match the stop's frame at each, and if a
# credible fit appears take its lateral offset as a correction. Batch 5 trial
# 2 (2026-09-07 20:08) stood beside the bar doorway, displaced to the right of
# the user's path, with the counter just visible at the left edge; the stop's
# frame fitted nothing head-on, the loop turned and walked into the wall.
STOP_LOOK_DEG = (-25.0, 25.0)
# THE PAN FROM THE RUN (ships False; the A/B decides). At a stop, look along
# headings the drive's own stationary run recorded there and match each look
# against the frame recorded AT that heading. See stationary_runs().
STOP_PAN_FROM_RUN = False
STOP_PAN_LOOKS = 2              # how many run frames to look at (first, middle)
# AT A STOP THE LOOK-AROUND VERIFIED, CORRECT THE HEADING, NOT THE POSITION
# (ships False; the A/B decides).
#
# THE MEASUREMENT (agent_progress/closed-loop/review/after_look129_census.py
# and .out, over the 113 journals carrying a `turned-looked` stop at chain
# 129 -- the bar entrance, the stop the audit's own table names as the lever):
# the look fits at -25 deg on EVERY one of them, with the scene a further +dx
# to the RIGHT inside that yawed frame, so the residual heading error
# theta = -25 + dx / PX_PER_DEG has the SAME median on the trials that
# arrived and on the ones that failed -- close to -20 deg either way, so it is
# not a symptom of a bad trial. The loop answers it with a SIDESTEP, and the
# FIRST head-on fit after that strafe still reads dx median -300 px on
# arrivals (93 of 96 credible, -379..-17) and -269 on failures: the scene is
# still ~15 deg left of the walking heading. The sidestep changes NOTHING
# measurable, because the offset is a YAW and a sidestep cannot fix a yaw.
# What it DOES do is move the character -- six of 2026-09-08's failures put it
# into the doorway corner or into an NPC, the view then unchanged for twenty
# rows -- while the arrivals carry the offset all the way through waypoints
# 130-142, correcting LEFT on 393 of 419 fits without converging
# (agent_progress/closed-loop/waste/bar-counter.md).
#
# (The exact median residual is in that script's .out and is deliberately not
# repeated as a number here: px-per-degree is ONE literal in this file,
# PX_PER_DEG, and tests/routing/test_chain_walk.py counts the occurrences.)
#
# So turn by it. This is the END TURN's own rule (see END_TURN_PX) applied at
# a looked stop instead of only in the tail, referencing its formula and its
# cap rather than copying them, and it is what HANDOFF_NOW.md item (e) asked
# for. It MOVES NOTHING: GRAVEYARD's two survivors out of thirteen navigation
# changes are the aim sweep and turning, and every change that failed moved
# the character. `stop_yaw` carries it until the next turn-only stop.
#
# SHIPS ON (patch45, 2026-09-08 07:55). The A/B, 10 a side interleaved
# (overnight/chain_trials_ab_stop_yaw.*): arrival 9/10 against 9/10, and the
# INSTRUMENT -- the first credible fit's dx after a looked 129 stop -- read
# median -352 px on every off-arm trial (the strafe left the scene ~18 deg
# left) and median +72 px on every on-arm trial (five yaws of -12.6..-22.9
# deg): two populations, no overlap at 5 and 5. The OFF path is the control
# and its test sets the flag False for itself.
STOP_LOOK_YAW = True
# ... AND THE UN-YAW ONLY MEANS ANYTHING WHEN THE LOOK FOUND THE STOP ITSELF.
# `px = dx + ddeg * PX_PER_DEG` assumes the frame that matched IS the stop's
# frame. A fit two or three waypoints PAST the stop is a different pose of the
# recording, so the sum answers about somewhere the character is not.
#
# THE CENSUS IS A NAMED POPULATION, NOT A GLOB. overnight/chain_journals/ is
# written by the LIVE batch: globbing it returned 41 rows and then 42 two
# minutes later, so counts taken that way are stale before they are read
# (CLAUDE.md's "name the fixture files", one level up). The 120 journals of
# 2026-09-08 05:36-09:09, ending with the last trial of batch 22, are listed
# with a sha256 each in drafts/pending_after_ab/patch46_yaw_firings.json and
# recounted by patch46_yaw_census.py beside it. 39 firings, each scored on the
# first credible fit (>= FIX_MIN_INLIERS) in the five rows after it:
#
#   stop 129, look fit within +-1   22 firings   dx -232..+263, BOTH SIGNS
#                                                (14 pos, 8 neg), 20 ARRIVED
#   stop 129, look fit +2 / +3       6 firings   dx +141..+230, ALL POSITIVE
#                                                4 ARRIVED; the two losses
#                                                (b21 t13, t17) went blind into
#                                                geometry in the rows after
#   stop  39, look fit +3            8 firings   dx -9..+174, BOTH SIGNS
#   stops 39 / 166 / 196 at the stop 3 firings
#
# A leftover that keeps the yaw's own sign reversed on six firings out of six is
# an OVER-TURN of 29-57% of the yaw, not scatter -- and those rows sit at the
# extreme of the yaw range (-20.1..-25.1 deg against -9.4..-23.8 at the stop).
# Where the fit is at the stop the leftover is unbiased, which is the shape a
# correction that landed has.
#
# So gate the yaw on the STRUCTURAL condition its formula needs, and fall back
# to the sidestep -- the pre-STOP_LOOK_YAW path, unchanged -- when it does not
# hold. SHIPS OFF: an A/B decides it, the way patch45's did
# (`--arms off,on --flag STOP_YAW_NEAR_FIT_ONLY`). It is NOT a special case for
# one stop, and equally the signature is only AT one stop: the stairs stop 39
# asks half the yaw (-104..-210 px) and its leftovers are both signs, so the
# eight firings the flag sends to the strafe there ride a rule whose evidence is
# at 129. What that costs is what the measurement is for.
STOP_YAW_NEAR_FIT_ONLY = False
# How far the look's fit may sit from the stop's own index and still be "the
# stop seen": ONE waypoint, which at the recording's 0.25 s is a quarter second
# of the user's walk. It is the census's own boundary -- the unbiased population
# above is exactly 128/129/130 -- and not a tuned number.
STOP_YAW_FIT_TOL = 1
# NO STOP YAW AT THE PLAN'S LAST TURN-ONLY STOP (patch51). The yaw is cleared
# at the NEXT turn-only stop; the last stop has none, so a yaw taken there
# rides the whole final approach and the end turn then aims the tail ON TOP
# of it. Census of the 196 stop over 266 walks since batch 16
# (agent_progress/closed-loop/review/census_after_129_notes.md, 2026-09-08):
# head-on or strafed, 225 arrived / 1 ended without the prompt / 1 failed;
# looked and YAWED (6), 4 arrived / 2 ended at 204 without the prompt (b24
# t12 +29.2 deg, b26 t1 +10.6 deg). The last three pushes go straight at the
# dealer and the prompt zone is 0.05 u wide (OPEN-22): a rotated final
# approach walks past it. The strafe there is the measured 225/227 path.
STOP_YAW_SKIP_LAST_STOP = True
# A stop whose frame and both looks fit NOTHING is most likely an NPC in the
# face (batch 4 trial 8, Wanda). NPCs move: wait this long once and look
# again before spending retry pushes into whatever is there.
STOP_WAIT_SEC = 2.0
# A stop fit whose runner-up is within this fraction of it MAY be ambiguity
# rather than verification -- but the ratio ALONE never was evidence of it, and
# from 2026-09-08 it is only the first of three conditions.
#
# WHAT THE RATIO ACTUALLY MEASURES AT A STOP. A turn-only target is a
# STATIONARY RUN of the recording collapsed to one index: several frames of the
# same spot, 0.25 s apart. Their fits to one live frame are near-duplicates, so
# the runner-up sits at 0.92-0.96 of the winner BY CONSTRUCTION. Replaying 37
# saved stop frames through chain.locate (agent_progress/closed-loop/stop_tie/
# replay_stops.py) calls a tie at EVERY one of the six stops of the four
# fastest arrivals ever recorded -- each of which verified head-on at the time
# in 0.1-4.2 s. The rule-cost study puts two thirds of the +34 s per arrival
# that followed this constant on exactly that (rule_costs/notes.md).
#
# AND ALONE IT COULD NOT CATCH ITS OWN EXAMPLE EITHER. Batch 5e trial 6's stop
# 129 ("33 against 33 with dx -386") reads winner 132, runner-up 128, and the
# ARRIVING batch 5e trial 5 reads the same stop at 34/31 with the same runner-up
# and the same 185 px disagreement. Nothing built from (best, second, dx)
# separates those two frames -- so the rule cannot be "spot the failure"; it can
# only be "spot the AMBIGUITY and go and look".
STOP_TIE_FRAC = 0.9
# ... so a tie also needs the two candidates to be TWO PLACES: their indices not
# both inside the stop's own stationary-run span (below), AND their dx
# disagreeing by more than this.
#
# THE SPAN TEST IS ON BOTH INDICES, NOT JUST THE RUNNER-UP'S. Two indices inside
# one span are one spot 0.25 s apart, and neither being there is what makes the
# pair informative -- in EITHER direction. A first draft asked only about the
# runner-up and lost exactly the frame above, whose WINNER (132) is the one past
# the span and whose runner-up (128) is the stop's own frame: it verified the
# stop and strafed on the winner's -386 px, which is the bug.
#
# WHAT THIS GATE JUDGES, MEASURED. Over the 37 replayed stop fits, those with a
# close count and two places read |second_dx - dx| =
#     0 0 0 0 0 0 0.2 0.3 0.4 0.6 1 4 4 6 6 9 11 27 45 67 95   |   185.0 185.4
# TWO populations with a gap between them (10.4), not the one the runner-up-only
# draft had: the low group is every neighbour one to three frames off the stop,
# each in a trial that ARRIVED; the high pair is stop 129 in batch 5e trials 5
# and 6. 120 sits in the gap -- 1.26x the low maximum, 0.65x the high minimum.
STOP_TIE_DX_PX = 120.0
# ONE MORE STEP TOWARD THE DOOR BEFORE THE OFFICE-DOOR STOP TURNS (ships OFF;
# the A/B decides).
#
# THE USER, watching the live stream during batch 23 (2026-09-08 09:50,
# verbatim): "an observation, you should take 1 more step towards the door in
# the beginning of the route. saves you from rubbing against the banister."
#
# THE STOP'S OWN FIT SCALE SAYS THE SAME THING, and it is this rule's
# instrument (agent_progress/closed-loop/review/census_after_129_notes.md,
# 226 walks since batch 16):
#     39 verified head-on (195 walks)      scale median 1.03-1.04   10% failed
#     39 verified by the LOOK-AROUND (31)  scale median 0.87-0.88   29% failed
#     39 unverified (2)                    scale 0.78-0.79          both failed
# Scale under 1 is the scene SMALLER than the reference: the character SHORT
# of the door when it turns. The corridor is blind for the sensor on every
# walk -- the last credible fit is at chain 4-10 and the pushes to 13, 16 and
# 19 are dead-reckoned -- so nothing in the loop can notice, and the stairs
# losses of batches 17-23 all begin from that short position (the turn goes
# into the bannister alcove, or into the mouse NPC beside the newel post).
#
# HOW FAR ONE PUSH IS, READ OFF THE CHAIN ITSELF rather than chosen: the
# corridor's push targets are 10, 13, 16 and 19, one PLAN_STEP_UNITS apart,
# and the 39 stop's own stationary run spans waypoints 21..39 (the human
# standing still and turning). So one more PUSH_MAG x PUSH_SEC push carries
# the character about three recorded frames -- from waypoint 19's spot INTO
# the span the recording turned in, not past it.
#
# WHAT IT CANNOT DO, said plainly: the step is taken BEFORE the stop's turn,
# so it cannot be conditioned on the stop's fit -- that fit is only measured
# after the turn, and the 195 head-on walks that already stand at scale 1.03
# get the step too. Gating on the scale would need a number inside a
# population the loop cannot read until it is too late to act on it (10.4).
# That cost is exactly what the A/B weighs, and the `door-step` row carries
# the fit taken right after the push, so the on arm's own rows say whether it
# overshoots rather than leaving it to be argued about.
#
# It MOVES THE CHARACTER, which is the shape GRAVEYARD closed thirteen times
# out of thirteen (both survivors move nothing), so it ships OFF and an A/B
# decides: `--arms off,on --flag DOOR_STOP_EXTRA_PUSH`.
# SHIPS ON (patch50, 2026-09-08 11:50): the A/B, 10 a side -- on arm 10/10, the
# 39 stop verified HEAD-ON on every trial at 66 inliers, fit scale 1.04
# [1.01..1.11]; off arm 9/10, three look-arounds and one unverified loss, 38
# inliers, scale 0.96 [0.80..1.05] (overnight/chain_trials_ab_doorstep.*).
DOOR_STOP_EXTRA_PUSH = True
# THE STOP IT APPLIES TO, AND IT IS CHAIN-SPECIFIC: 39 is the office-door /
# top-of-the-stairs turn-only stop of chains/route_user_1853, the drive every
# batch walks. It is an index into THAT recording and not a property of the
# world -- another chain's door stop is another number, and a chain with no
# stop there leaves the rule dormant, because no plan entry ever equals it.
DOOR_STOP_INDEX = 39
# How many extra pushes. ONE, because one step is what the user asked for.
DOOR_STOP_EXTRA_PUSHES = 1
# ONE FEWER PUSH BEFORE THE BAR'S SHARP TURN (patch55), the mirror of the door
# step and from the same source: the user, watching the stream, said "they
# walked too close to the bar when they should have turned earlier". The fit
# scale agrees -- over 2,560 credible fits the 135-149 band medians 2.22, the
# worst on the route, against 1.00 at the spawn and 1.29 once the turn is
# taken. Those waypoints are exactly plan[33..35], the last pushes before the
# 296-degree turn at 166. Ships OFF; --flag BAR_STOP_EARLY_TURN measures it,
# and the pre-registered instrument is that band's median scale falling
# toward 1.0.
BAR_STOP_EARLY_TURN = False
BAR_STOP_INDEX = 166
# LOOK INSTEAD OF PUSHING BLIND AGAIN (patch56). The user, watching the stream:
# "the bar area seems to be an area the player struggles to detect and know when
# to turn towards the jukebox. This causes them to ram into the bar"; and "they
# also walk into the wall behind Wanda. they also walk into wanda."
#
# The turn itself is NOT the problem -- over 58 walks the stop at 166 was
# serviced on a credible fit in 57, median ZERO blind iterations before it. The
# loss is AFTER it. Read from its own rows rather than its summary line, the
# motivating failure (chain_trials.log:1085-1133) is: the 166 stop taken
# `turned-unverified` on 7 inliers, TWO blind advances (the cap was 2 because
# that unverified turn set it, not because the tail did), a weak fit, then
# eleven iterations of misses and escape rungs, then lost. The "6 blind
# advances" in its failure string is this file's own hardcoded {BLIND_MAX}
# below and is not a count of anything -- a separate, pre-existing bug.
#
# Two blind pushes were still two pushes further into whatever it could not
# see, and a frame of wall stays a frame of wall however many waypoints
# `_strong_ahead` re-matches it against. Turning the camera is the one cheap
# thing that changes the FRAME, and the loop already knows how -- at an
# unverified stop and inside the lost rescue.
#
# On the BLIND_LOOK_AFTER'th consecutive blind push the iteration looks instead
# of pushing: STOP_LOOK_DEG about the heading it was going to walk, the same
# `_strong_ahead` on each view, and the walk carries on from a strong one. It
# moves the character LESS than the push it replaces, which is the opposite of
# every change in GRAVEYARD.
#
# Ships OFF; `--flag BLIND_LOOK_AROUND` measures it. Pre-registered instrument:
# the number of consecutive `blind-advance` rows in the stretch past waypoint
# 166 (shorter on the on-arm); how many `blind_look` rows carry
# `relocalised-look` (zero refutes the mechanism outright); and WHERE each
# firing happened -- `from_k`, reported per firing, because a look spent far
# from 166 is not evidence about 166.
BLIND_LOOK_AROUND = False
# HOW MANY CONSECUTIVE BLIND PUSHES BEFORE THE FIRST LOOK. Borrowed, not
# invented: END_BLIND_MAX is the loop's own answer to "how many blind pushes
# before another is not worth the risk", from the one place it has already
# decided that -- past the last stop, and after an unverified turn, which is
# the state the motivating failure was in. It does NOT mean the budget runs out
# here: in the common case that stretch is capped at BLIND_MAX (6), so this
# looks on the second blind push with four still in hand. A look that finds
# nothing therefore costs the walk none of its dead-reckoning, which is why the
# trigger is small rather than "when the budget is nearly gone".
# (Near a wall and a stop `_blind_cap` allows only ONE blind push, so `blind`
# never reaches this and TURN-EARLY still owns that case, untouched.)
BLIND_LOOK_AFTER = END_BLIND_MAX
# ... and the BOUND: LOST_RESCUE_MAX's value, with LOST_MAX's own scope -- "One
# full ladder per blockage". PER BLIND STRETCH, not per walk: the count resets
# when `blind` returns to 0, which is exactly when a credible fit ended the
# stretch. Per WALK was the first draft and it has a hole -- a walk that went
# blind for two pushes ANYWHERE earlier would spend its only look there and
# reach the bar with none, silently behaving as the off arm while still being
# scored as an on-arm trial. The reset reads `blind`, which every branch that
# ends a stretch already zeroes, so it is one line and not the six-site mirror
# that argument assumed.
BLIND_LOOK_MAX = 1
# The journal's name for a look that found nothing, and for one that did. The
# second starts with "relocalised" ON PURPOSE: `PROGRESS_ACTIONS` is tested with
# str.startswith, so it resets the escape ladder and re-arms turn-early exactly
# as the forward search's `relocalised` does, while still being greppable apart
# from it. A no-op path and a working path must not have identical output
# (10.1), which is why the failing look records a row at all.
BLIND_LOOK_ACTION = "blind-look"
BLIND_LOOK_FOUND_ACTION = "relocalised-look"

# THE ESCAPE GATE (patch59): the ladder's rung at the BAR-ENTRANCE STOP, and no
# rung at all when the push that led to it MOVED.
#
# The user, watching the stream: "the navigation is jumping around in the bar
# area. getting onto the bar and ramming into it and somehow ending up at the
# mini game table."
#
# THE CENSUS IS A SCRIPT, NOT PROSE:
# agent_progress/closed-loop/escape_gate/census.py regenerates every number
# here from the journals. The first draft of this patch carried a hand-copied
# table and three of its seven rows were wrong.
#
# Over the last 60 journals, 94 rungs fired; whether a CREDIBLE fit (>=
# FIX_MIN_INLIERS) followed within three rows, split at the boundary
# tools/collision_census.py already uses:
#
#     region          rung   n   credible   no fit
#     BAR-A 115-129   jump    7   0 (  0%)   7/7    <- ALL SEVEN AT k=129
#     BAR-A 115-129   back    7   0 (  0%)   7/7
#     BAR-A 115-129   left    7   7 (100%)   0/7    <- but see the confound
#     BAR-B 130-150   jump   15  13 ( 87%)   1/15   <- the BEST rung anywhere
#     elsewhere       jump   41  33 ( 80%)   3/41
#     elsewhere       back    7   4 ( 57%)   2/7
#     elsewhere       left    5   2 ( 40%)   3/5
#     elsewhere       right   3   1 ( 33%)   2/3
#
# THE CONFOUND, AND IT IS WHY THE COMMENT IS THIS LONG. The ladder is jump,
# back, left, right and IT STOPS WHEN IT WORKS, so the last rung tried always
# looks like the rung that worked. All seven k=129 blockages are the identical
# triple (jump., back., leftC) at exactly MISS_MAX iterations apart, with the
# next credible fit exactly 7 iterations after the first rung -- one
# deterministic trajectory observed seven times, not seven samples. Left is
# NEVER tried first anywhere in this dataset, so its 7 of 7 is an artefact of
# the ORDER (CLAUDE.md 10.2's STALL_CHANGE shape) and is a HYPOTHESIS here.
#
# What survives is position-matched only: JUMP ALWAYS WENT FIRST and at k=129
# it is 0 of 7 with the picture lost on 7 of 7 -- which is exactly the hop the
# user watched -- while everywhere else, first as well, it is 33 of 41. BACK
# always went second and is 0 of 7 here (LOST_RESCUE_MAX's comment below has
# carried "escape:back 0 of 27 times in the bar stretch" since patch43 without
# anything acting on it).
#
# NOT TOUCHED, and recorded so nobody reads its absence as a claim: at k=166
# every rung fails (jump 0/3, back 0/3, left 0/3, right 0/2, ten of eleven
# losing the picture). No rung order helps there.
#
# THIS REMOVES AND REDIRECTS MOVEMENT rather than adding any. GRAVEYARD's
# summary is that every failed navigation change MOVED the character and both
# survivors move nothing.
#
# Ships OFF; `--flag ESCAPE_GATE` measures it. Instruments: at k=129 the
# fraction of escapes followed by a credible fit (baseline 7 of 21) and the
# number followed by NO fit (14 of 21); the rungs per affected walk (baseline
# exactly 3 on 7 of 7); the iterations from the first rung to the next credible
# fit (baseline exactly 7 on 7 of 7 -- the instrument the confound demands);
# and the two-population check on the journalled push signal.
ESCAPE_GATE = False
# THE WINDOW IS ONE WAYPOINT, inclusive at both ends, IN THIS CHAIN
# (chains/route_user_1853): k = 129 is the bar-entrance stop. It is a range of
# one because that is the whole of the evidence -- every failing bar jump is
# there, and at k 130-139 jump is 13 of 15, the best rung in the dataset, so a
# wider window would ban it exactly where it works. The 115-150 span the first
# draft used came from a census bucket and hid that split.
#
# The test `k` is the ESTIMATE, which is what the census bucketed and which can
# be wrong; a rung chosen from a wrong estimate is the same risk the rest of
# the loop already runs, and every firing records its `k` so instrument (e) can
# throw out a firing that was not really here.
BAR_ESCAPE_FROM_K = 129
BAR_ESCAPE_TO_K = 129
# JUMP IS ABSENT, and that is the SUPPORTED half: it is the rung that always
# went first, 0 of 7 at this stop, and the one that loses the picture entirely,
# 7 times in 7 -- the hop the user watched climb the counter.
#
# LEFT FIRST IS A HYPOTHESIS, NOT A MEASUREMENT. Its 7 of 7 comes from the
# third rung of a ladder that stops when it works; nothing here has ever tried
# it first. RIGHT second: the same clearance on the other side. BACK last, and
# kept only because a two-rung ladder alternates sidesteps down the counter for
# ever while back is the one rung that changes the distance to whatever is in
# front -- NOT because it works (0 of 7 as the second rung, 0 of 27 in the
# older census). Which side "left" is relative to the counter is not
# established either.
BAR_ESCAPE_RUNGS = ("left", "right", "back")
# Today's `escapes % 4`, written out so the two orders sit side by side. With
# the gate off this is the order everywhere and the ladder is byte-identical.
DEFAULT_ESCAPE_RUNGS = ("jump", "back", "left", "right")
# THE MOVED/BLOCKED THRESHOLD, in RANSAC inliers between the frame before a
# push and the frame after it (tools/crawl.py:pair_inliers, imported not
# reimplemented). The twelve hand labels in overnight/crawl_labelled.jsonl:
#
#     BLOCKED (pressed on the desk, the push moved nothing)  148 153 154 164 166
#     MOVED   (travelled)                    10 11 23 28, and two with NO FIT
#
# 88 is the MIDPOINT of 28 | 148. Step 1 of that file is labelled `desk` at 28
# and belongs to the MOVED population: crawl.py's labels name what was HIT, and
# step 1 is the push that travelled INTO the desk -- its `change` is the
# largest of the twelve and its frame is a different viewpoint from step 2's.
# n = 5 and 7, UNDER 10.3's power floor (0.72 at n=6, 0.94 at n=10). This is a
# gap between two thin populations, not a calibrated gate; the raw count is
# journalled on every push, on BOTH arms, so the next batch calibrates it at
# scale.
#
# CLAUDE.md OPEN-1 measured the RAW count as unusable and only the PAIRED ratio
# (push / a null taken at the same spot) as usable. The raw count separates
# here because these nulls sit at pose._MAX_MATCHES (184-200 on the blocked
# rows); a null costs a second measurement window per push, which the loop
# cannot pay for. Rows 11-12 are the counter-case (nulls of 49 and 10), and
# they fail toward MOVED -- which suppresses an escape on a stuck character.
# ESCAPE_SUPPRESS_MAX below is the bound that exists for exactly that.
#
# IT IS ALSO THE KEYPOINT FLOOR, by arithmetic and not by choice: inliers <=
# matches <= min(keypoints), so a pair with fewer keypoints than this CANNOT
# read BLOCKED and its low count is an artefact rather than an answer (10.1's
# "a measurement that returns the same number everywhere"). Under the floor the
# verdict is None -- NO SIGNAL, today's behaviour -- and never "moved".
PUSH_BLOCKED_MIN_INLIERS = 88
PUSH_MOVED = "moved"
PUSH_BLOCKED = "blocked"
# THE LAST RESORT'S BOUND: this many consecutive suppressions per blockage,
# after which every trigger fires its rung until the walk moves on evidence.
#
# DERIVED FROM THE LOOP'S OWN CADENCES, not borrowed -- the first draft set it
# to MISS_MAX (3) and that could remove EVERY rung. Two families reach the
# ladder and both increment `lost` under one budget, LOST_MAX:
#
#     the MISS family (fix is None)   cadence MISS_MAX  = 3 -> lost 3, 6, 9, 12
#     the WEAK family (a thin fit)    cadence STALL_MAX = 4 -> lost 4, 8, 12
#
# LOST_MAX's own comment derives 13 as MISS_MAX*4+1, "let all four rungs fire
# and be seen" -- true of the miss family, false of the weak one, which gets
# only THREE triggers inside the budget. At a cap of 3 all three were
# suppressed and the walk reached LOST_MAX having attempted no physical
# recovery at all, with a failure line identical to today's. Reproduced on a
# scratch copy: cap 3 -> rungs [], cap 2 -> rungs [jump].
#
# So: the shortest trigger sequence any family gets is THREE, and a cap of TWO
# leaves at least one real rung in every family. A loop that can never escape
# is worse than one that escapes too often, and the failure this bounds is a
# real one: a scene whose own frames do not match each other (crawl rows 11-12)
# reads MOVED however stuck the character is.
ESCAPE_SUPPRESS_MAX = 2
# The action a suppressed trigger records. It deliberately does NOT start with
# "escape:", because tools/collision_census.py counts waste with
# `startswith("escape:")` and a rung not taken is the opposite of waste; and it
# is not in PROGRESS_ACTIONS, because it is not evidence the walk moved on. A
# no-op path and a working path must not have identical output (10.1), which is
# why a suppression writes a row at all.
ESCAPE_SKIPPED_ACTION = "escape-skipped"
# THE ACTION THE EXTRA PUSH RECORDS, and the reason it is a name and not a
# bare literal: it is the FIRST row this module has ever written that shares
# an iteration number with another row, and three readers select "one
# iteration's own fit" by asking whether a row HAS an iteration number --
# `_timeout_diagnosis` below, `tools/live_gate_census.py`, and
# `tools/trial_sheet.py`. That proxy was exact until this row existed. Each
# of those three now excludes this action by name, and each has a test.
DOOR_STEP_ACTION = "door-step"
# A retry (turn back, one more push) needs EVIDENCE of being short: the stop's
# frame fitting an EARLIER waypoint, however thinly. A frame that fits nothing
# is an occluded view or a stop already passed (batch 4 trial 8: Wanda the
# camera mouse in the loop's face at the bar-entrance stop; three retry pushes
# walked into her and past the spot). Then: turn and go on.
# WIDE RE-LOCALISATION once the blind budget is spent: search this many chain
# indices AHEAD of k for a STRONG fix before counting misses. Batch 2 trials 1
# and 2 (2026-09-07 19:4x): at the office exit the scene is a distant facade
# that looks the same from the doorway and from halfway across the street, the
# loop crossed in two pushes and stood at the portraits inside the building
# while the estimate still said "doorway"; nothing within [k-1, k+3] could
# ever match again. Sixty indices spans the street crossing and the
# portrait room beyond it (chain 64 -> 126).
WIDE_AHEAD = 60
# A wide-search fix is believed only when it is STRONG: at least this many
# inliers. 120 is the true-position p25 on this chain and sits above the
# wrong-place p95 of 117 (chain_user_1853_closed.json NEAR / FAR); a margin
# over the runner-up was tried first and was wrong -- in a window of adjacent
# frames the runner-up is the NEIGHBOUR (batch 3 trial 1: the portrait room
# scored 188 against a runner-up of 175, and the margin gate refused it).
# The wide search runs from the FIRST blind push and inside turn retries, not
# only after the budget: by then that trial was nose to nose with an NPC and
# then against a wall, with nothing left to match. Provisional; logged.
STRONG_MIN_INLIERS = 165
# LIVE census (overnight/census/live_gate_census.json, 2026-09-07 21:2x, 1,858
# in-window fits from batches 4-5 and 468 far matches on the same frames):
#   true fits, arriving trials   p05 13  p25 49  median 98  p95 179
#   wrong-place matches (30 away) p25 0   median 6  p75 15   p95 126  max 164
# No count separates these populations; the sequence window does the work.
# 165 sits above the wrong-place MAXIMUM because a wrong relocalisation moves
# the estimate by up to 60; FIX_MIN 29 and WEAK_MIN 15 stay, documented as
# unseparable rather than moved without a population to move them to.
# |stick| at or under this is "not walking": the tap records the COMMANDED value
# and a settle or a turn is exactly 0.0. Frames whose ly is None (no tap, or a
# chain older than this field) count as walking, so nothing is silently skipped.
STATIONARY_STICK = 0.05
# A target whose heading is within this of the LAST COMMANDED heading is not
# turned to again: the camera holds its yaw while walking (only the right stick
# yaws it, §5), so re-issuing a heading only pays turn_to's compass reads, and
# inside the bar the compass abstains on ~15% of frames (OPEN-15). Scheduling,
# not a population threshold; logged per iteration.
TURN_SKIP_DEG = 1.0

# THE END OF THE CHAIN, WHICH USED TO BE A 400-SECOND FORWARD WALK.
#
# `target_k` is clamped to the last waypoint, so once k reaches it the loop can
# only ever aim at the waypoint it is already standing on. A locate() that
# honestly answers "I am at or past the last waypoint" then satisfies
# `chain.reached` on EVERY iteration forever: k is frozen, so the stall counter
# never rose, the escape ladder was unreachable, and every row still said
# "advanced" — CLAUDE.md §10.1's "a success path and a no-op path with identical
# output". Measured by the skeptic on a 6-waypoint chain with the prompt absent:
# 120 iterations, 120 forward pushes, 0 escapes, 118 of 120 rows "advanced" with
# k frozen (agent_progress/closed-loop/verify-controller/endchain.py).
#
# What SHOULD happen there is not obvious, so it is derived rather than picked.
# The chain's last waypoint is where the RECORDING stopped, and chain_record
# only keeps a chain whose end saw the prompt. So "k == n-1 and no prompt" means
# either the sensor is early or the walk landed somewhere the prompt is not —
# both measured in OPEN-22, where the goal leg ended at the round table BESIDE
# the dealer's in two recorded walks of three.
#
# OPEN-22 also holds the ONLY number anyone has about how far the prompt is from
# where a goal leg stops: at the recorded endpoint the prompt was absent at all
# five headings, and 0.05 walk-units FORWARD it appeared at four of five. One
# push here is PUSH_MAG * PUSH_SEC = 0.180 walk-units, so a SINGLE terminal push
# already covers 3.6x that measured gap.
#
# Past that, more forward pushing is the failure the user reported on day one
# and a leg-end frame has since caught: a walk into the bar that ended on a CITY
# STREET (§8(k), test_fixtures/leg_failures/overshot_outdoors_*.jpg). So the
# terminal phase is BOUNDED, and running out of it is a named FAILURE — never a
# silent 400s of forward pushes logged as progress.
END_PUSH_UNITS = 0.05           # OPEN-22's measured prompt-zone offset

# A sidestep rung is a DETOUR around a body, not a nudge. At 0.3 s the frame
# after 'escape:left' showed a sliver of wall at the far edge and nothing
# else (batch 9 trial 2, pressed on the jukebox; trial 4, an NPC), and the
# very next push walked straight back into the obstacle because the lateral
# correction pulled toward the recorded line. So: 0.6 s, the RIGHT rung
# doubled when a LEFT was taken in the same blockage (the same clearance on
# the other side), and the correction that would undo the detour is held
# off for DETOUR_TARGETS plan targets. 0.6 is the smallest doubling of a
# measured-insufficient 0.3, not a measured body width.
ESCAPE_STRAFE_SEC = 0.6
DETOUR_TARGETS = 3
# Actions that mean the walk moved on; the next blockage restarts the ladder.
PROGRESS_ACTIONS = ("advanced", "relocalised", "regressed", "turned")
ESCAPE_STRAFE_MAG = 0.45
# ... and the two of them that carry NO evidence: both advance k at a stop that
# fitted nothing (or fitted thinly at a later waypoint), so neither is proof the
# character moved. They re-arm the escape ladder like any progress action; they
# do NOT re-arm the once-per-blockage turn-early, which would otherwise cascade
# from stop to stop while the character stands still against the same NPC.
UNEVIDENCED_ACTIONS = ("turned-unverified", "turned-past")

# Sign convention, verified in three places rather than assumed:
#   slow_traverse.walk_leg sends `left_x = ar.to_axis(lx)`
#   walk_steps.walk_forward sends `left_x = ar.to_axis(strafe)`   (same axis)
#   walk_steps.unstick names -0.6 "left" and +0.6 "right"
#   pose.align_lateral: `side = +1 if dx > 0` with the comment "dx > 0 means the
#     scene sits RIGHT of where it should, i.e. the camera is LEFT of the
#     reference -- so strafe RIGHT, which measured dx<0"
# So: POSITIVE lx = RIGHT, and dx > 0 -> strafe RIGHT.
RIGHT = +1.0
LEFT = -1.0


def escape_rungs(k, gate, from_k, to_k, bar_order, default_order):
    """The escape ladder's rung ORDER at estimate `k`.

    Pure, and every argument is a PARAMETER rather than a module-level default
    (10.18): a knob captured in a default cannot be redirected by a test or an
    A/B arm, which is how `leg_reliability.STORE` silently served one store to
    both arms.

    Three clauses, each of which a mutant can delete, each driven directly:

      gate         with the flag off this returns `default_order` for every k,
                   so the ladder is byte-identical to the one that has always
                   shipped. That is what makes the off arm today's build.
      k is not None  the estimate is never None in the loop today, but a rung
                   chosen from a missing estimate would be chosen from
                   `None <= 129`, which raises. Explicit beats a TypeError in
                   a live walk.
      from_k <= k <= to_k   inclusive at both ends. The shipped window is a
                   RANGE OF ONE (129..129), so both ends are the same waypoint
                   and an off-by-one at either is a firing in the wrong place.
    """
    if gate and k is not None and from_k <= k <= to_k:
        return bar_order
    return default_order


def push_verdict(inliers, kp_before, kp_after, thresh):
    """Did this push MOVE the character, or was it BLOCKED? None = no signal.

    `inliers` is tools/crawl.py's `pair_inliers` between the frame before the
    push and the frame after it -- None from it means UNMEASURABLE (too few
    surviving matches to fit), never "identical".

    THE KEYPOINT FLOOR COMES FIRST, and it is arithmetic rather than judgement:
    inliers <= matches <= min(keypoints), so a pair with fewer keypoints than
    the threshold cannot reach BLOCKED at all, and its low count would be a
    number that is low everywhere -- 10.1's measurement that reads as a verdict.
    Below the floor the answer is NO SIGNAL, which falls through to today's
    behaviour. It is never "moved": a suppressed escape on a stuck character is
    the expensive direction to be wrong in.

    ABOVE the floor, NO FIT IS THE MOVED POPULATION. Two of the six clean rows
    in overnight/crawl_labelled.jsonl have `push_inliers` None. What the floor
    cannot catch is a scene whose frames do not match each other at all (those
    same two rows have nulls of 49 and 10 on plenty of keypoints), and that
    case reads MOVED -- which is why the caller's suppression is bounded.
    """
    if min(kp_before, kp_after) < thresh:
        return None
    if inliers is None:
        return PUSH_MOVED
    return PUSH_BLOCKED if inliers >= thresh else PUSH_MOVED


def escape_is_suppressed(gate, verdict, suppressed, cap):
    """Should THIS escape trigger fire no rung at all?

    Pure, so each of the three clauses can be driven and mutated directly --
    patch55 learned that a guard reachable only through a scripted walk lets its
    mutant survive.

      gate                 the arm.
      verdict == MOVED     BLOCKED fires the rung, and so does NO SIGNAL. Only
                           a positive reading of "the character travelled"
                           earns a suppression.
      suppressed < cap     the bound, and it is load-bearing: at a cap of 3 the
                           WEAK family (cadence STALL_MAX = 4, three triggers
                           inside LOST_MAX = 13) had every one of its rungs
                           suppressed and reached the end of the walk having
                           attempted no physical recovery at all. See
                           ESCAPE_SUPPRESS_MAX.
    """
    return bool(gate) and verdict == PUSH_MOVED and suppressed < cap


def pair_signal(before, after, thresh=None):
    """One ORB match on the two frames around a push -> the journal's row.

    -> {"inliers": int|None, "kp_before": int, "kp_after": int,
        "verdict": "moved"|"blocked"|None}

    `pair_inliers` is IMPORTED from tools/crawl.py, which is where it was
    validated against the user's own labels, and NOT reimplemented here.
    CLAUDE.md records what a reimplementation of a project function costs: the
    localiser mirror that used a raw `len(bf.match(...))` instead of
    `places.match_count`'s Hamming filter scored the reference set 3 of 9 where
    the original scores 9 of 9, and a whole finding was written on it.

    The features come from `places.keypoints`, whose `_as_gray` masks the
    compass, the quest list and the coin -- pixel-identical HUD that would hand
    any two frames free matches and bias the answer toward BLOCKED.

    `thresh=None` resolves the constant at CALL time, so an A/B or a test can
    move `PUSH_BLOCKED_MIN_INLIERS` and be obeyed (10.18).
    """
    import places
    import tools.crawl as crawl
    t = PUSH_BLOCKED_MIN_INLIERS if thresh is None else thresh
    ka, da = places.keypoints(before)
    kb, db = places.keypoints(after)
    n_a = 0 if ka is None else len(ka)
    n_b = 0 if kb is None else len(kb)
    inliers = crawl.pair_inliers(ka, da, kb, db)
    return {"inliers": inliers, "kp_before": n_a, "kp_after": n_b,
            "verdict": push_verdict(inliers, n_a, n_b, t)}


def _strong_ahead(chain, img, k, n):
    """A STRONG fix ahead of k within WIDE_AHEAD, or None."""
    if k >= n - 1:
        return None
    wide = chain.locate(img, k + 1, window=WIDE_AHEAD)
    inl = 0 if wide is None else (getattr(wide, "inliers", 0) or 0)
    if wide is not None and inl >= STRONG_MIN_INLIERS and int(wide.k) > k:
        return wide
    return None


def _blind_cap(pi, plan, unverified_turn, last_cred_scale):
    """How many blind pushes are allowed from here."""
    if pi >= len(plan) - END_TAIL_TARGETS or unverified_turn:
        return END_BLIND_MAX
    if last_cred_scale >= WALL_SCALE:
        ahead = plan[pi:pi + NEAR_STOP_TARGETS]
        if any(not push for _, push, _ in ahead):
            return 1
    return BLIND_MAX


def _turn_early_at(pi, plan, index, latched):
    """Should the pointer step over plan[pi] to take a stop one push early?

    Pure, so every guard can be driven directly. Inside `walk` two of them --
    "the entry skipped must be a PUSH" and the once-per-walk latch -- are
    unreachable through anything `plan_indices` emits: it never puts two
    turn-only stops next to each other, and after a fired skip the next entry
    IS the stop. Mutants deleting them therefore survived a walk-level test,
    which is precisely the "guard that cannot fire" shape this project keeps
    finding. Held to their stated meaning here instead.
    """
    return (not latched
            and 0 <= pi
            and pi + 1 < len(plan)
            and plan[pi][1]              # the entry skipped must be a PUSH
            and not plan[pi + 1][1]      # ... and the next must be a stop
            and plan[pi + 1][0] == index)


def _blind_look_due(blind, looks, after, cap, pushing, at_end):
    """Should this iteration LOOK AROUND instead of pushing blind again?

    Pure, so every guard can be driven directly. patch55 learned this the
    expensive way: two of its guards were unreachable through anything the plan
    builder emits, so mutants deleting them survived a walk-level test. Two of
    the four here are the same shape -- `after >= 1` and `at_end` are hard or
    impossible to reach through a scripted walk -- and they are held to their
    stated meaning here instead.

    `after` and `cap` are PARAMETERS, never module-level defaults: a knob
    captured in a default cannot be redirected by a test or an A/B arm (10.18).

      after >= 1   a zero trigger would look before the walk has gone blind at
                   all, on a healthy walk, every iteration. `blind >= 0` is
                   true of every walk, so this one is NOT redundant.
      pushing      at a TURN-ONLY stop the stop's own look-around already runs,
                   and two look-arounds in one iteration would fight.
      not at_end   past the plan there is nothing ahead to find, the prompt
                   check runs every iteration anyway, and turning the camera
                   beside the dealer's table is where the walk can least afford
                   to spend an iteration.
      looks < cap  the budget for THIS blind stretch.

    `blind >= after + looks`, NOT `blind >= after`: A LOOK THAT FINDS NOTHING
    TOUCHES NEITHER `blind` NOR `k`, so the plain form is satisfied again on the
    very next iteration and the rule fires in a tight loop -- the same
    manoeuvre, the same k, the same heading, with no push and therefore no new
    information between attempts. Measured in a scratch copy at after=1, cap=4:
    the plain form gives four consecutive looks whose recorded `blind` reads
    [1, 1, 1, 1]; this form gives [1, 2, 3, 4], each separated by a blind push.
    It is dormant at the shipped cap of 1 -- which is exactly why it is written
    here rather than trusted to the cap: a bound that only holds at one value of
    its own constant is not a bound.

    A FIFTH CLAUSE WAS WRITTEN AND DELETED: `cap >= 1`, to make a zero cap
    disable the rule. `looks < cap` already refuses at cap 0 for every
    non-negative `looks`, so it could not change an answer -- its mutant
    survived the whole suite, which is how it was found. A guard that cannot
    fire is the shape this project keeps finding, so it is gone and the test
    that pins the BEHAVIOUR (cap 0 disables) stays.
    """
    return (after >= 1
            and bool(pushing)
            and not at_end
            and looks < cap
            and blind >= after + looks)


def _near_stop(pi, plan):
    """The plan index of a TURN-ONLY stop within NEAR_STOP_TARGETS of `pi`, or None.

    The same window `_blind_cap` uses to cut the blind budget to one push near a
    stop, read the other way round: not "is a stop close" but "which entry is
    it", so the loop can take that stop instead of an escape rung.
    """
    for j in range(pi, min(len(plan), pi + NEAR_STOP_TARGETS)):
        if not plan[j][1]:
            return j
    return None


def settle_probe_on(env=None):
    """Is the settle probe armed? Read at CALL time, never at import (10.18).

    A module-level knob captured in a default cannot be redirected by a test or
    a harness, and this project has the scar: `tools/prompt_ocr_ab` set
    BASEBALL_TEST_RUN at import and every stick send for the rest of that live
    run was silently dropped.
    """
    e = os.environ if env is None else env
    return bool(e.get(SETTLE_PROBE_ENV))


def _last_stop_index(plan):
    """The plan index of the LAST turn-only stop, or None if the plan has none.

    THE END TURN FIRES ONLY PAST THIS ENTRY. Past the last stop the plan is a
    straight approach and the only thing that matters is being close enough for
    the prompt, so aiming the remaining pushes at the scene is free. Before it,
    a large dx is the lateral displacement the strafe exists for, and turning
    would aim every subsequent push off the recorded line -- the "steering while
    walking" family GRAVEYARD closed. A plan with no turn-only stop at all
    returns None, and then only `at_end` opens the rule.
    """
    last = None
    for j, (_, push_target, _) in enumerate(plan):
        if not push_target:
            last = j
    return last


def _turn_report(reported):
    """What `turn_to` SAID about a turn, or None if it said nothing at all.

    `slow_traverse.turn_to` returns `(heading_now, hazards)`: no hazards when
    the camera arrived, one UNDERTURNED when the turn ran without converging or
    when the compass could not be read (`heading_now` None, and then NOTHING
    was sent). Every call site in walk() throws that away, which costs little
    for a heading the next iteration re-commands -- turn_to is ABSOLUTE and
    closed-loop, so an underturn is simply re-attempted.

    THE END TURN IS THE ONE SITE THAT MAKES IT PERSISTENT: its yaw rides every
    remaining heading and spends one of END_TURN_MAX slots, so a turn that did
    not happen would be counted as one that did. IT IS STILL NOT A GATE. §3:
    the compass abstains reliably INSIDE THE BAR, which is exactly where this
    rule fires, and turn_to reports UNDERTURNED whenever it cannot read one --
    refusing the turn on that report would switch the rule off precisely where
    it exists to work, which is §10.1's shape. This module's rule for an
    unmeasured gate is a knob defaulted off with the QUANTITY LOGGED; this is
    the quantity, and the next live run is what could earn the gate.

    A caller whose turn_to returns something else (the test rig's stub returns
    None) reports None, and the journal row is left exactly as it was.
    """
    if not isinstance(reported, tuple) or len(reported) != 2:
        return None
    now, hazards = reported
    return {"reached": None if now is None else round(float(now), 1),
            "hazards": [getattr(h, "kind", None) or str(h)
                        for h in (hazards or ())]}


def pitch_dead_band():
    """The |dy| below which nothing is corrected, in pixels.

    THE ACTUATOR SETS IT. A bang-bang rule that fires a fixed step S whenever
    the error leaves a dead-band D can only fail to overshoot while S <= D:
    from |dy| = D + e one press lands at D + e - S, which stays on the same
    side of zero exactly when S <= D. Making the band the step therefore makes
    the limit cycle impossible BY CONSTRUCTION, at whatever the step turns out
    to be -- and it is the same reasoning pose.py:155-165 gives for its own
    35 px ("TOLERANCE IS SET BY THE ACTUATOR, not by the measurement").

    PITCH_STEP_PX is None until tools/pitch_probe.py has run, and then the
    floor is all there is. That floor is a placeholder of the lateral
    tolerance's order, not a derivation; see PITCH_TOL_MIN_PX.
    """
    if PITCH_STEP_PX is None:
        return PITCH_TOL_MIN_PX
    return max(PITCH_TOL_MIN_PX, abs(float(PITCH_STEP_PX)))


def pitch_correction(dy, inliers, escaped=False):
    """The pitch nudge one fit calls for, or None. PURE, so every guard here
    can be driven directly rather than through a walk that may never reach it.

    Returns None when there is nothing to say at all, or a row:

        dy          the offset, px
        deg         dy / PITCH_PX_PER_DEG -- a REPORT, nothing acts on it
        band        the dead-band this row cleared
        acted       whether a press was issued for it
        blocked     why not, if not -- a tuple, possibly several reasons
        hypothesis  the direction the OPTICS ARGUMENT predicts, always
        action      the direction MEASURED to reduce |dy|, or None when the
                    sign is unmeasured. Never the hypothesis.
        seconds     the hold, or None
        step_px, gain   the calibration in force, so a journal row says which
                    control law produced it

    THE RULES, each mirroring the lateral correction (see the constants):

      1. a fit under FIX_MIN_INLIERS neither advances k nor steers -- and that
         now includes the camera. A thin fit's offsets are junk (-847 px at 7
         inliers), and this rule is why trial 1's 13-inlier fits are refused.
      2. inside pitch_dead_band(), nothing at all -- not even a row. The band
         is the actuator's own step once that is known.
      3. ACTING NEEDS BOTH MEASUREMENTS. PITCH_STEP_PX and PITCH_DOWN_DY_SIGN
         ship None and while either is None this returns a row that says so and
         presses nothing, WHATEVER PITCH_MODE is. That is the whole safety
         argument of the first version: the constant an invented gain would be
         invented for is the one that unlocks acting, so it cannot be smuggled
         in quietly -- its absence is in every row.
      4. an ESCAPE this iteration or last blocks the press but NOT the row.
         The strafe skips outright because a jump or sidestep displaces the
         character between the measurement and the action; whether the jump
         rung's hop is pitch-neutral is unknown, so this is conservative about
         pressing and generous about recording.
      5. the hold is capped at PITCH_CAP_SEC and floored at PITCH_PRESS_SEC.
         With no gain measured the floor IS the command.

    Every constant is read HERE, at call time, never captured in a default
    argument (§10.18: `path=STORE` changed nothing and nothing said so).
    """
    if dy is None or inliers is None or inliers < FIX_MIN_INLIERS:
        return None
    dy = float(dy)
    band = pitch_dead_band()
    if abs(dy) <= band:
        return None
    blocked = []
    if PITCH_STEP_PX is None:
        blocked.append("step_px_unmeasured")
    if PITCH_DOWN_DY_SIGN is None:
        blocked.append("down_sign_unmeasured")
    if PITCH_MODE != "act":
        blocked.append("report_mode")
    if escaped:
        blocked.append("escaped")
    row = {"dy": dy, "deg": round(dy / PITCH_PX_PER_DEG, 1),
           "band": round(band, 1), "acted": not blocked,
           "blocked": tuple(blocked),
           # THE OPTICS ARGUMENT'S ANSWER, LABELLED AS ONE. dy > 0 means the
           # scene moved DOWN the image since the waypoint, which is what a
           # camera pitched UP does -- so look_down. That is an inference from
           # pose.offset's median(dst - src) plus y-grows-downward, NOT a
           # quoted convention: chain.Fix documents the dx sign and no other.
           # It is here so pitch_probe's measured sign can be CHECKED against
           # it; `action` below never falls back to it.
           "hypothesis": PITCH_ACTIONS[1] if dy > 0 else PITCH_ACTIONS[0],
           "action": None, "seconds": None,
           "step_px": PITCH_STEP_PX, "gain": PITCH_SEC_PER_DEG}
    if blocked:
        return row
    # PITCH_DOWN_DY_SIGN is the sign of the CHANGE look_down makes to dy, so
    # look_down reduces |dy| exactly when that change opposes dy.
    row["action"] = (PITCH_ACTIONS[1] if PITCH_DOWN_DY_SIGN * dy < 0
                     else PITCH_ACTIONS[0])
    gain = PITCH_SEC_PER_DEG
    if gain is None:
        secs = PITCH_PRESS_SEC
    else:
        secs = min(PITCH_CAP_SEC,
                   max(PITCH_PRESS_SEC, abs(dy / PITCH_PX_PER_DEG) * gain))
    row["seconds"] = round(secs, 3)
    return row


def _fix_row(fix):
    """The Fix's fields as plain JSON, by attribute access only.

    chain.py is the SENSOR agent's file and is NOT imported here: chain_walk
    only ever calls `chain.locate(...)` / `chain.reached(...)` on the object it
    is handed. getattr with a default means a Fix that grows or loses a field
    does not crash a live run at minute nine.
    """
    if fix is None:
        return None
    return {name: getattr(fix, name, None) for name in
            ("k", "k_float", "inliers", "dx", "dy", "scale", "second",
             "second_k", "second_dx", "detail")}


def _save(shots, iteration, k, img, log, suffix=""):
    if not shots:
        return
    try:
        os.makedirs(shots, exist_ok=True)
        img.save(os.path.join(shots, f"it_{iteration:03d}_k{k}{suffix}.jpg"), quality=88)
    except Exception as e:                    # never let bookkeeping end a walk
        log(f"    could not save frame {iteration}: {type(e).__name__}: {e}")


def _journal(path, row, log):
    """Append one iteration's row as JSON, open-append-write-flush-close.

    WHY THIS EXISTS. The harness runs each trial as a subprocess and KILLS it at
    the external ceiling (`_harness.run_trial`, CLAUDE.md §10.14 — signal.alarm
    did not interrupt a trial blocked inside a capture). A killed child prints
    no JSON, so its `fixes` — the per-iteration record that is the whole point
    of a closed loop — died with it, on exactly the trials that need explaining.
    Written as it goes, the evidence survives the kill: §10.16, "a file written
    on completion is lost in precisely the case it exists for". Same
    append-and-flush shape as chain_record's meta.jsonl, and for the same
    reason: a crash at minute four keeps four minutes.
    """
    if not path:
        return
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
    except Exception as e:                    # never let bookkeeping end a walk
        log(f"    could not journal iteration {row.get('iteration')}: "
            f"{type(e).__name__}: {e}")


def min_iterations(n, window=None, tail=None):
    """The FEWEST iterations in which this chain could possibly arrive.

    Arrival needs an iteration whose `target_k >= n - TABLE_CHECK_TAIL`, and
    `target_k = k + 1` is computed from the k the PREVIOUS iterations left
    behind. So k must first reach `n - tail - 1`, which takes
    `ceil((n - tail - 1) / window)` iterations because k rises by at most
    `window` per iteration (deliberately — one picture may not move the plan an
    arbitrary distance), and the arrival then happens on the iteration AFTER
    that. Hence the `+ 1`.

    THAT `+ 1` WAS MISSING and the count was low by exactly one for every chain
    (skeptic's `../verify-controller/minit.py` drove walk() with the most
    generous locate possible and counted: n=1000 claimed 332, needed 333; n=10
    claimed 2, needed 3). A chain recorded at chain_record's 0.25s period over
    the 244s route is ~1000 waypoints and needs >= 333 iterations, and an
    iteration is one turn, one push, three captures and a locate.

    Nothing here refuses a long chain on its own (see `iteration_sec_floor`) —
    but a run that spends ten trials reporting TIMED_OUT must be able to say
    whether the chain was arithmetically unwalkable or the navigation failed,
    and those two need different responses. Reported on every walk.
    """
    window = ADVANCE_MAX if window is None else window
    tail = TABLE_CHECK_TAIL if tail is None else tail
    if tail is None:
        # The prompt is believed on any iteration, so the floor is just the
        # iterations k needs to reach the last waypoint at ADVANCE_MAX per step.
        return max(1, math.ceil(max(0, n - 1) / max(1, window)))
    return 1 + math.ceil(max(0, n - tail - 1) / max(1, window))


def plan_indices(wps, stride=None):
    """Compile the chain into targets: (chain index, push?, heading).

    Walking frames every `stride`; each STATIONARY run (a turn, a settle)
    collapses to ONE turn-only target carrying the run's last heading, so a
    corner is turned on the spot instead of pushed around. A heading falls
    back to the recorder's commanded `cam`, then to the last known heading, so
    an abstaining compass cannot silently skip a corner (it abstains on 6-15%
    of frames live). Index 0, the trusted spawn, is never a target; the final
    waypoint always is.
    """
    stride = STRIDE if stride is None else max(1, int(stride))
    plan, run, last_heading, walked = [], [], None, 0
    dist = 0.0                    # stick-seconds since the last push target
    prev_t = None
    n = len(wps)
    for i, w in enumerate(wps):
        t_now = getattr(w, "t", None)
        dt = (t_now - prev_t) if (t_now is not None and prev_t is not None
                                  and 0.0 < t_now - prev_t < 5.0) else RECORD_PERIOD_SEC
        prev_t = t_now if t_now is not None else prev_t
        heading = getattr(w, "heading", None)
        if heading is None:
            heading = getattr(w, "cam", None)
        if heading is None:
            heading = last_heading
        else:
            last_heading = heading
        lx = getattr(w, "lx", None) or 0.0
        ly = getattr(w, "ly", None)
        # The recorder writes 0.0 with `stick:unknown` in the note when it had
        # NO stick to read (a user drive with no controller on the Mac). That
        # is unknown, not stationary: treating it as stationary would collapse
        # a whole drive into one turn-only target.
        unknown = "stick:unknown" in (getattr(w, "note", "") or "")
        stationary = (not unknown and ly is not None
                      and abs(ly) <= STATIONARY_STICK
                      and abs(lx) <= STATIONARY_STICK)
        if i == 0:
            continue
        if stationary:
            run.append((i, heading))
            continue
        if run:
            plan.append((run[-1][0], False, run[-1][1]))
            run, walked, dist = [], 0, 0.0
        if unknown or ly is None:
            emit = walked % stride == 0
        else:
            dist += abs(ly) * dt
            emit = walked == 0 or dist >= PLAN_STEP_UNITS
        if emit:
            plan.append((i, True, heading))
            dist = 0.0
        walked += 1
    if run:
        plan.append((run[-1][0], False, run[-1][1]))
    if n > 1 and (not plan or plan[-1][0] != n - 1):
        plan.append((n - 1, True, last_heading))
    return plan


def stationary_runs(wps):
    """{last index of each stationary run: [(index, heading), ...] for the run}.

    The frames the drive recorded while turning on the spot at a stop, each
    with its own heading: a small panorama at every stop. Same stationarity
    rule as plan_indices; frames whose heading is None are skipped.
    """
    runs, run = {}, []
    for i, w in enumerate(wps):
        if i == 0:
            continue
        lx = getattr(w, "lx", None) or 0.0
        ly = getattr(w, "ly", None)
        unknown = "stick:unknown" in (getattr(w, "note", "") or "")
        stationary = (not unknown and ly is not None
                      and abs(ly) <= STATIONARY_STICK and abs(lx) <= STATIONARY_STICK)
        if stationary:
            h = getattr(w, "heading", None)
            if h is None:
                h = getattr(w, "cam", None)
            run.append((i, h))
            continue
        if run:
            runs[run[-1][0]] = [(i2, h2) for i2, h2 in run if h2 is not None]
            run = []
    if run:
        runs[run[-1][0]] = [(i2, h2) for i2, h2 in run if h2 is not None]
    return runs


def stop_spans(wps):
    """{last index of each stationary run: the FIRST index of that run}.

    The SAME SPOT as an index range, which is what the stop-tie rule needs.
    `stationary_runs` cannot answer it: it DROPS frames whose heading is None
    -- the compass abstains on 6-15% of frames inside the bar (OPEN-15) -- so
    its lists have holes (the user's drive records the run ending at 88 as
    65..80, 82, 84..88), and a hole is not a different place. A span cannot be
    broken by one. Same stationarity rule as `plan_indices`, so the keys are
    exactly the plan's turn-only targets.
    """
    spans, run = {}, []
    for i, w in enumerate(wps):
        if i == 0:
            continue
        lx = getattr(w, "lx", None) or 0.0
        ly = getattr(w, "ly", None)
        unknown = "stick:unknown" in (getattr(w, "note", "") or "")
        stationary = (not unknown and ly is not None
                      and abs(ly) <= STATIONARY_STICK and abs(lx) <= STATIONARY_STICK)
        if stationary:
            run.append(i)
            continue
        if run:
            spans[run[-1]] = run[0]
            run = []
    if run:
        spans[run[-1]] = run[0]
    return spans


def plan_min_iterations(plan, window=None):
    """Fewest iterations for a plan: one per turn-only target, and the push
    targets at ADVANCE_MAX per iteration."""
    window = ADVANCE_MAX if window is None else window
    turns = sum(1 for _, push, _ in plan if not push)
    pushes = len(plan) - turns
    return max(1, turns + math.ceil(pushes / max(1, window)))


def end_iteration_budget(push_mag=None, push_sec=None, units=None):
    """How many iterations the loop may spend ON the last waypoint.

    DERIVED, not chosen: `units` is OPEN-22's measured prompt-zone offset
    (0.05 walk-units forward of where the recorded goal leg stops) and one push
    covers `push_mag * push_sec` walk-units, so this is the number of pushes
    that covers the gap, floored at one. At the shipped 0.45 x 0.40 = 0.180
    units a push, that is ONE — a single push already covers 3.6x the measured
    gap, and everything beyond it is walking past the table.

    Exposed as a knob on `walk()` because 0.05 is ONE measurement at ONE spot
    (three walks, one of which reached the zone) and a live run may need to
    move it. It is logged on every walk so the first live run measures it.
    """
    mag = PUSH_MAG if push_mag is None else push_mag
    sec = PUSH_SEC if push_sec is None else push_sec
    units = END_PUSH_UNITS if units is None else units
    per_push = abs(mag) * abs(sec)
    if per_push <= 0:
        return 1
    return max(1, math.ceil(units / per_push))


def _timeout_diagnosis(res, n, min_iters, time_cap):
    """Why did the cap run out: the chain's LENGTH, or the walking?

    A timeout with no diagnosis is CLAUDE.md §10.1's "two paths with identical
    output": ten trials of a chain too long to finish look exactly like ten
    navigation failures, and the fix for each is the opposite of the other.
    """
    # ONE ITERATION'S OWN ROW, NOT EVERY ROW CARRYING ITS NUMBER. A
    # DOOR_STEP_ACTION row is an extra push taken INSIDE an iteration: it
    # shares the iteration's number with the row that resolves the stop, and
    # its `seconds` is the PARTIAL elapsed time up to the push, not a whole
    # iteration. Counted here it reported more iterations than the walk ran
    # (`res["iterations"]` is the loop's own counter and is right) and pulled
    # the median down -- inside the string that decides ARITHMETIC against
    # NAVIGATION, which is the whole reason this function exists.
    per = sorted(r["seconds"] for r in res["fixes"]
                 if r.get("iteration") and r.get("action") != DOOR_STEP_ACTION)
    if not per:
        return (f"no iteration completed inside the {time_cap:.0f}s cap — "
                f"suspect the console, not the chain")
    med = per[len(per) // 2]
    need = med * min_iters
    advanced = sum(1 for r in res["fixes"] if r.get("action") == "advanced")
    if need > time_cap:
        return (f"ARITHMETIC: {n} waypoints need >= {min_iters} iterations and "
                f"the median iteration took {med:.2f}s, i.e. >= {need:.0f}s "
                f"against a {time_cap:.0f}s cap — this chain could not be "
                f"walked in the cap however well it navigated. Record a "
                f"sparser chain or raise the cap; do not read this as a "
                f"navigation failure.")
    return (f"NAVIGATION: {len(per)} iterations at a median {med:.2f}s "
            f"({advanced} advanced) — the cap allowed the >= {min_iters} "
            f"iterations this chain needs, so the time went into not "
            f"advancing. k stopped at {res['k_final']} of {n - 1}.")


def walk(chain, capture, read_heading, log=print, time_cap=None, shots=None,
         journal=None, iteration_sec_floor=None, end_iterations=None,
         turn_to=None, push=None, strafe=None, jump=None, at_table=None,
         now=time.time, sleep=time.sleep, back=None, pitch=None):
    """Servo along `chain` until the dealer prompt is on screen.

    Returns {arrived, seconds, pushes, k_final, iterations, waypoints,
    min_iterations, iteration_budget_sec, end_iterations, fixes, failure}.

    `journal` is a path each iteration's row is appended to as it happens, so a
    child killed at the harness ceiling still leaves its evidence on disk.

    `iteration_sec_floor` is the OPTIONAL up-front feasibility check: given a
    floor on what one iteration costs, a chain needing more than the cap is
    refused before a single push instead of burning the whole cap to say so.
    It defaults to None — NEVER refuse — because no such floor has been
    measured on this rig yet, and SPEC's rule is that an unmeasured gate is a
    knob defaulted to off with the quantity logged, never an invented constant.

    `end_iterations` is how many iterations may be spent standing ON the last
    waypoint before the walk gives up. It defaults to `end_iteration_budget()`,
    which is DERIVED from OPEN-22's measured prompt-zone offset rather than
    chosen. `time_cap` defaults to TIME_CAP. Both are resolved here rather than
    in the signature: a module-level knob captured in a `def` line is bound
    once at import, so redirecting it changes nothing and nothing says so
    (§10.18).

    `turn_to`, `push`, `strafe`, `jump` and `at_table` default to the real
    console functions, resolved HERE rather than in the signature (§10.18).
    Their contracts, so a stub and the real thing cannot drift apart:

        turn_to(heading)        turn the camera to an absolute bearing
        push(mag, secs)         ONE continuous forward push, mag > 0 = forward
                                -> this push's MOVED/BLOCKED signal, or None
                                   when there is none (patch59). A stub that
                                   returns None is a stub with no signal, which
                                   is exactly today's behaviour.
        back(mag, secs)         ONE continuous BACKWARD push
        strafe(lx, secs)        ONE continuous sidestep, lx > 0 = RIGHT
        jump()                  press Cross once
        pitch(action, secs)     hold the RIGHT stick vertically for `secs`;
                                `action` is one of PITCH_ACTIONS
        at_table(img) -> bool   is the BASEBALL CARDS prompt on screen
    """
    if time_cap is None:
        time_cap = TIME_CAP
    end_budget = (end_iteration_budget() if end_iterations is None
                  else max(1, int(end_iterations)))
    if turn_to is None:
        import slow_traverse as st
        def turn_to(heading, _st=st):
            return _st.turn_to(heading, read_heading, capture, log=log)
    if push is None:
        import slow_traverse as st
        def push(mag, secs, on_release=None, _st=st):
            # step_sec == seconds is ONE continuous push. Chunking it would
            # re-accelerate from a standstill and cover less ground -- the
            # GRAVEYARD row that ended two rooms adrift.
            # `on_release` is forwarded ONLY when there is one: it is the
            # settle probe's hook, it is off unless the environment arms it,
            # and passing on_release=None to a stub written before patch54 is
            # a TypeError.
            #
            # `on_pair` is forwarded ALWAYS, and that is a deliberate change to
            # the shipped call (patch59). The signal is journalled on every
            # push whether or not ESCAPE_GATE is on -- that is the whole point
            # of part 3, since a measurement taken only on the arm that uses it
            # cannot be compared -- so there is nothing to make it conditional
            # ON. The one stub in the tree that had to grow the parameter is in
            # tests/routing/test_chain_walk.py's DefaultConsoleWrappers.
            #
            # WHAT IT COSTS, STATED HONESTLY: one ORB match per push (~28 ms)
            # on two frames walk_leg has already captured. No extra capture, no
            # extra push, no console call -- which is why the off arm's event
            # list is unchanged. But this closure is shared, and the forward
            # push call `push(PUSH_MAG, ...)` is made from FOUR places in this
            # file: the two tracked forward pushes whose signal reaches the
            # journal, plus DOOR_STOP_EXTRA_PUSH (once per walk at one stop)
            # and the turn-retry (up to TURN_RETRY_MAX per stop). Those two
            # discard the return, so the match still runs and its answer is
            # thrown away -- up to four extra matches a walk, ~112 ms. That is
            # a cost paid, not a cost avoided, and it is written here rather
            # than left to be discovered.
            sig = {}

            def _pair(before, after, _sig=sig):
                # A MEASUREMENT MUST NEVER KILL A LIVE WALK. The failure is
                # recorded in the row rather than swallowed, so it cannot look
                # like "there was no signal here" -- a silent no-op and a
                # working path with identical output is 10.1's first entry.
                try:
                    _sig.update(pair_signal(before, after) or {})
                except Exception as exc:
                    _sig.update({"error": repr(exc)})
                    log(f"        push signal FAILED, the walk carries on: "
                        f"{exc!r}")

            extra = {} if on_release is None else {"on_release": on_release}
            _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                         label="chain push", log=log, step_sec=secs,
                         on_pair=_pair, **extra)
            # walk_leg's own (spent, best, hazards) was already discarded by
            # every caller of this wrapper; the signal replaces it as the
            # return value rather than being smuggled out through a closure.
            return sig or None
    if back is None:
        import slow_traverse as st
        def back(mag, secs, _st=st):
            # ly POSITIVE is backward on walk_leg's axis (forward is -abs(mag)).
            return _st.walk_leg(0.0, abs(mag), secs, capture, read_heading,
                                label="chain back", log=log, step_sec=secs)
    if strafe is None:
        import slow_traverse as st
        def strafe(lx, secs, _st=st):
            return _st.walk_leg(lx, 0.0, secs, capture, read_heading,
                                label="chain strafe", log=log, step_sec=secs)
    if jump is None:
        import input_controller as ic
        def jump(_ic=ic):
            # Cross IS the jump button (§8(g)). It is also the ONLY button this
            # module is allowed to press.
            return _ic.press("cross")
    if pitch is None:
        import input_controller as ic
        def pitch(action, secs, _ic=ic):
            # A STICK AXIS, NOT A BUTTON. input_controller.STICK_AXES maps
            # look_up/look_down to right_y -/+0.8 and press() sends that over
            # the FIFO as a timed hold, which is the path every stick on this
            # project uses (§5: buttons go to the keyboard, sticks to the
            # FIFO). post_delay copies level_pitch's own look_up press.
            return _ic.press(action, hold_seconds=secs,
                             post_delay=PITCH_POST_DELAY)
    if at_table is None:
        import table_prompt
        at_table = table_prompt.at_table

    t0 = now()
    res = {"arrived": False, "seconds": 0.0, "pushes": 0, "k_final": 0,
           "iterations": 0, "fixes": [], "failure": None}
    wps = chain.waypoints
    n = len(wps)
    if n < 2:
        res["failure"] = f"chain has {n} waypoint(s); nothing to walk"
        log(f"  chain_walk: {res['failure']}")
        return res

    # THE ARITHMETIC, BEFORE ANYTHING MOVES, because a TIMED_OUT with no
    # arithmetic beside it cannot be told from a navigation failure.
    plan = plan_indices(wps)
    runs = stationary_runs(wps) if STOP_PAN_FROM_RUN else {}
    # Built unconditionally: every stop of every walk asks the tie rule below
    # which indices are the SAME SPOT as this stop, and `runs` is gated by the
    # shipped-False pan flag.
    spans = stop_spans(wps)
    n_turn = sum(1 for _, push, _ in plan if not push)
    n_push = len(plan) - n_turn
    min_iters = plan_min_iterations(plan)     # the loop iterates per TARGET (audit)
    res["waypoints"] = n
    res["plan_targets"] = len(plan)
    res["plan_pushes"] = n_push
    res["plan_turns"] = n_turn
    res["min_iterations"] = min_iters
    res["iteration_budget_sec"] = round(time_cap / min_iters, 3)
    res["end_iteration_budget"] = end_budget
    log(f"  chain_walk: {n} waypoints -> plan of {len(plan)} targets "
        f"({n_push} push, {n_turn} turn-only); the prompt is checked on every "
        f"iteration; k rises by at most {ADVANCE_MAX} per iteration, so >= "
        f"{min_iters} iteration(s). The {time_cap:.0f}s cap allows "
        f"{res['iteration_budget_sec']:.2f}s each. At the last waypoint the "
        f"walk may spend {end_budget} more iteration(s) — "
        f"{end_budget * PUSH_MAG * PUSH_SEC:.3f} walk-units of forward push "
        f"against OPEN-22's measured {END_PUSH_UNITS} — and then gives up "
        f"rather than walking on past the table.")

    k = 0                       # the last waypoint we believe we are AT.
                                # 0 is the reset spawn, which is trusted the way
                                # graph_walk.TRUST_RESET_SPAWN trusts it: the
                                # spawn is deterministic (bearing 86.9/87/87).
    misses = 0
    stalls = 0
    escapes = 0
    action = None               # the previous iteration's action (rung reset below)
    detour_side = None          # the side of the last sidestep rung, held while k < detour_until
    detour_until = -1
    iteration = 0
    end_iters = 0               # iterations spent standing ON the last waypoint
    pi = 0                      # the plan pointer: first target past k
    blind = 0                   # consecutive pushes made with no credible fix
    lost = 0                    # iterations with nothing credible, budget spent
    rescues = 0                 # LOST RESCUES spent this walk (LOST_RESCUE_MAX)
    turn_retries = 0            # retries spent on the current turn stop
    since_advance = 0           # iterations since k last rose
    dx_run = []                 # dx of the last fits (>= WEAK_MIN_INLIERS), for the consistency rule
    junk_run = []               # dx of the last JUNK fits (>= JUNK_MIN_INLIERS), four agreeing steer once
    last_cred_scale = 1.0       # scale of the last CREDIBLE fit
    last_cred_k = 0             # ... and the waypoint it NAMED. Waypoint 0 is
                                # the reset spawn, trusted the way k is trusted
                                # above, so it is the floor a rewind falls to.
    rewinds_at = {}             # stop -> rewinds already spent AT THAT STOP.
                                # A dict rather than a (which stop, how many)
                                # pair, because a pair is REFUNDABLE: a rewind
                                # can land BEFORE an earlier stop, that stop
                                # then fails too, and coming back the counter
                                # has been reset by the other stop. Measured
                                # on a two-stop chain: 22 rewinds and the whole
                                # 400 s cap spent oscillating, with
                                # STOP_REWIND_MAX = 2 in force the whole time.
                                # Keyed by stop, the pool is finite -- two per
                                # stop for the life of the walk.
    escaped_prev = False        # the previous iteration escaped: no lateral undo this one
    waited_here = False         # the current stop has had its one wait
    backed_here = False         # ... and its one step back
    k_prev_iter = 0
    unverified_turn = False     # the last stop was accepted unverified
    turned_early = False        # this blockage has already taken its early turn
    early_stop = False          # the current stop was reached by turn-early: no retry pushes
    walk_heading = None         # the last heading a push was made along
    last_cmd = None             # the last heading actually commanded
    blind_looks = 0             # BLIND_LOOK_AROUND firings in the CURRENT
                                # blind stretch (the budget; reset with `blind`)
    blind_looks_total = 0       # ... and over the whole walk, for the report
    escape_suppressed = 0       # ESCAPE_GATE suppressions in THIS blockage;
                                # reset wherever the ladder itself re-arms
    bar_turned_early = False    # the once-per-walk latch for
                                # BAR_STOP_EARLY_TURN
    door_stepped = False        # this SERVICING of DOOR_STOP_INDEX has had
                                # its extra push (DOOR_STOP_EXTRA_PUSH)
    plan_last_heading = next((h for _, _, h in reversed(plan) if h is not None),
                             None)
    last_stop_j = _last_stop_index(plan)   # the end turn fires only past this
    end_yaw = 0.0               # degrees added to every remaining tail heading
    stop_yaw = 0.0              # ... and the degrees a LOOKED STOP's yaw adds
                                # to every push until the next turn-only stop
                                # (STOP_LOOK_YAW). Zero unless that flag is on.
    end_turns = 0               # end turns spent this walk (END_TURN_MAX)

    def finish(failure=None):
        res["seconds"] = round(now() - t0, 2)
        res["k_final"] = k
        res["iterations"] = iteration
        res["end_iterations"] = end_iters
        res["failure"] = failure
        if failure == "timed out":
            res["timeout_diagnosis"] = _timeout_diagnosis(
                res, n, min_iters, time_cap)
            log(f"  chain_walk: {res['timeout_diagnosis']}")
        return res

    def record(row):
        """One row, in the result AND on disk. Never one without the other."""
        res["fixes"].append(row)
        _journal(journal, row, log)

    if iteration_sec_floor is not None:
        need = min_iters * float(iteration_sec_floor)
        if need > time_cap:
            log(f"  chain_walk: REFUSING before the first push — {n} waypoints "
                f"need >= {min_iters} iterations at >= {iteration_sec_floor}s "
                f"each = {need:.0f}s, against a {time_cap:.0f}s cap.")
            return finish(
                f"chain too long for the cap: {n} waypoints need >= "
                f"{min_iters} iterations at >= {iteration_sec_floor}s each "
                f"= {need:.0f}s > {time_cap:.0f}s")

    def escape(order=None):
        """One escape, taking the rung ORDER it should cycle through.

        Jump first in the DEFAULT order because it moves nothing sideways,
        which is what a passage with stools on one side and a wall on the other
        requires; measured escape outcomes against real blockers were None,
        None, jump, None, None, None, wait, jump (§8(g)). At the bar-entrance
        stop the order has no jump at all -- see BAR_ESCAPE_RUNGS: there it is
        the rung that always went first and never worked, 0 of 7, losing the
        picture 7 of 7.

        `order` defaults to DEFAULT_ESCAPE_RUNGS, so a caller that has not been
        told about regions gets exactly the ladder that has always shipped.
        """
        nonlocal escapes
        rungs = DEFAULT_ESCAPE_RUNGS if not order else tuple(order)
        # THE LADDER CYCLES its order, as `escapes % 4` did over
        # jump/back/left/right. The modulus is the order's own length, so a
        # three-rung order cycles three.
        rung = rungs[escapes % len(rungs)]
        escapes += 1
        if rung == "jump":
            # Jump comes round again: the one arrival that beat the patron
            # wedge (batch 5c trial 2) had a jump; batch 5e trial 7, whose jump
            # had fired earlier in the street, got only sidesteps there.
            jump()
            return "escape:jump"
        if rung == "back":
            back(PUSH_MAG, BACK_SEC)
            return "escape:back"
        nonlocal detour_side, detour_until
        side = LEFT if rung == "left" else RIGHT
        secs = ESCAPE_STRAFE_SEC * (2 if (side > 0 and detour_side is not None and detour_side < 0) else 1)
        strafe(side * ESCAPE_STRAFE_MAG, secs)
        detour_side, detour_until = side, k + DETOUR_TARGETS
        return "escape:left" if side < 0 else "escape:right"

    def escape_now(sig):
        """ONE escape TRIGGER: a rung and its order, or a suppression.

        -> (action, escaped, row). All three escape triggers go through here so
        the decision exists in ONE place; with ESCAPE_GATE off it resolves to
        `escape()` over the default order, which is the call the three sites
        made before this patch.

        `escaped` is what the iteration sets on itself, and a suppression does
        NOT set it: nothing displaced the character between the fit and now, so
        the lateral correction computed from that fit is still valid, and so is
        patch57's pitch press, which blocks on `escaped or escaped_prev`. That
        is the same reasoning those guards are built on, applied in the
        direction that gives the correction back.

        A suppression touches NOTHING ELSE -- not `lost`, not `misses`, not
        `stalls`, not `k`. The iteration count of a blockage is identical
        either way, so this cannot push a walk into LOST_MAX or NO_PROGRESS_MAX
        that would not have got there anyway. What it CAN do, unbounded, is
        reach LOST_MAX having fired no rung at all; ESCAPE_SUPPRESS_MAX is
        derived from the two trigger cadences so that it cannot.
        """
        nonlocal escape_suppressed
        verdict = (sig or {}).get("verdict")
        order = escape_rungs(k, ESCAPE_GATE, BAR_ESCAPE_FROM_K,
                             BAR_ESCAPE_TO_K, BAR_ESCAPE_RUNGS,
                             DEFAULT_ESCAPE_RUNGS)
        if escape_is_suppressed(ESCAPE_GATE, verdict, escape_suppressed,
                                ESCAPE_SUPPRESS_MAX):
            escape_suppressed += 1
            return (ESCAPE_SKIPPED_ACTION, False,
                    {"rung": None, "verdict": verdict, "k": k,
                     "order": list(order), "suppressed": escape_suppressed,
                     "cap": ESCAPE_SUPPRESS_MAX})
        rung = escape(order)
        return (rung, True,
                {"rung": rung, "verdict": verdict, "k": k,
                 "order": list(order), "suppressed": escape_suppressed,
                 "cap": ESCAPE_SUPPRESS_MAX})

    # THE FIRST FRAME, BEFORE ANYTHING MOVES. A chain recorded to the table ends
    # at the prompt, so a walk started from there is already finished; pushing
    # once "to get going" would walk the character out of the prompt zone, which
    # the user has watched happen.
    img = capture()
    _save(shots, iteration, k, img, log)
    if at_table(img):
        res["arrived"] = True
        record({"iteration": 0, "k": 0, "target": None,
                "fix": None, "action": "arrived",
                "lateral": None, "at_end": False, "seconds": 0.0,
                "elapsed": round(now() - t0, 2)})
        log("  chain_walk: the prompt is ALREADY on screen — stopping before "
            "the first push")
        return finish()

    while True:
        elapsed = now() - t0
        if elapsed >= time_cap:
            log(f"  chain_walk: {elapsed:.1f}s >= cap {time_cap:.0f}s at k={k} "
                f"of {n - 1} — TIMED OUT")
            return finish("timed out")

        # NO PROGRESS: k has not risen for NO_PROGRESS_MAX iterations.
        if k > k_prev_iter:
            since_advance = 0
        elif iteration > 0:
            since_advance += 1
        k_prev_iter = k
        if since_advance >= NO_PROGRESS_MAX:
            log(f"  chain_walk: STUCK — k={k} of {n - 1} has not advanced in "
                f"{since_advance} iterations")
            return finish(f"stuck at k={k} of {n - 1}: no advance in "
                          f"{since_advance} iterations")
        # THE PLAN POINTER: the next target is the first plan entry past k.
        #
        # A TURN-ONLY STOP THE POINTER PASSES WITHOUT TAKING IT DROPS THE YAW,
        # exactly as a stop the loop actually takes does. The clear below lives
        # on the UNPACK of `plan[pi]`, and a SKIPPED entry is never unpacked: k
        # jumps on a wide relocalisation -- the stop branch's "relocalised past
        # the stop", the blind path's forward search, the lost rescue -- and
        # the pointer then walks over whatever lies between. Reproduced
        # (agent_progress/closed-loop/stop_yaw): a yaw taken at chain 2 rode
        # every push from chain 25 on, twenty waypoints past the stop that
        # should have ended it, which is the "steering while walking" family
        # GRAVEYARD closed. The ordinary advance cannot do this -- ADVANCE_MAX
        # is 1 and `new_k` is capped at `target_k` -- and `_near_stop` returns
        # the FIRST turn-only entry in its window, so turn-early skips only
        # pushes; the wide jumps are the whole population.
        #
        # `pi` here is STILL the entry the previous iteration serviced, since
        # nothing moves it after the unpack. So `pi > pi_serviced` is precisely
        # "this entry was jumped over", and the stop the loop just took --
        # whose own look-around is what set the yaw -- is left alone.
        pi_serviced = pi
        while pi < len(plan) and plan[pi][0] <= k:
            if pi > pi_serviced and not plan[pi][1]:
                stop_yaw = 0.0
            pi += 1
        # THE END OF THE CHAIN IS A BOUNDED PHASE. Past the last target there
        # is nothing left to servo onto: every further push is dead reckoning
        # with no reference, which is the thing this module exists to replace.
        # TURN EARLY AT THE BAR (BAR_STOP_EARLY_TURN). Step over the push
        # immediately before the named stop, once per walk. It can only ever
        # skip a PUSH entry, and only when the very next entry is that stop,
        # so no stop is ever passed and the yaw-clearing rule above is
        # untouched.
        if (BAR_STOP_EARLY_TURN
                and _turn_early_at(pi, plan, BAR_STOP_INDEX,
                                   bar_turned_early)):
            bar_turned_early = True
            log(f"    turning EARLY at the bar: skipping the push to "
                f"{plan[pi][0]} so the stop at {BAR_STOP_INDEX} is taken one "
                f"push sooner (BAR_STOP_EARLY_TURN)")
            res["bar_turned_early"] = int(plan[pi][0])
            pi += 1
        at_end = pi >= len(plan)
        if at_end:
            end_iters += 1
            if end_iters > end_budget:
                log(f"  chain_walk: at the LAST waypoint ({k} of {n - 1}) and "
                    f"the prompt is not on screen after {end_budget} terminal "
                    f"iteration(s) — giving up rather than walking on past the "
                    f"table")
                return finish(
                    f"reached the last waypoint ({k} of {n - 1}) without the "
                    f"prompt; spent the {end_budget}-iteration end budget "
                    f"(~{end_budget * PUSH_MAG * PUSH_SEC:.3f} walk-units "
                    f"against OPEN-22's measured {END_PUSH_UNITS} to the "
                    f"prompt zone). Either the sensor is early or the walk "
                    f"landed where the prompt is not — OPEN-22 measured both.")

        iteration += 1
        it_t0 = now()
        # EVERY BLOCKAGE STARTS ITS LADDER AT THE FIRST RUNG. The rung counter
        # used to persist for the whole walk, so a late wedge got only the
        # sidesteps while jump and back -- which had already worked twice in
        # the same trial (batch 7 trial 1) -- were never retried there.
        if action is not None and action.startswith(PROGRESS_ACTIONS):
            escapes = 0
            # ... and the gate's suppression budget, on the same event and for
            # the same reason: the budget is PER BLOCKAGE, and a progress
            # action is this loop's own definition of a blockage ending.
            escape_suppressed = 0
            if action not in UNEVIDENCED_ACTIONS:
                # A turn-early is spent until the walk moves ON EVIDENCE. An
                # unverified turn is not that evidence -- it advances k at a
                # stop that fitted nothing -- so re-arming on it would let one
                # blockage turn early at stop after stop without moving.
                turned_early = False
        if at_end:
            # Nothing left in the plan: push toward the last waypoint along
            # the plan's final heading, inside the end budget above.
            target_k, do_push, heading = n - 1, True, plan_last_heading
        else:
            target_k, do_push, heading = plan[pi]
        if not do_push:
            # A TURN-ONLY STOP TURNS TO THE PLAN'S OWN HEADING. A stop is
            # verified against the recording's frame at the recording's
            # heading, and STOP_LOOK_YAW's offset was a correction measured at
            # a DIFFERENT stop, from a position the walk has since left.
            # Cleared HERE, before the turn below, so the stop is approached
            # square and its own look-around measures the residual afresh.
            stop_yaw = 0.0
        if (end_yaw or stop_yaw) and heading is not None:
            # THE END TURN RIDES ON EVERY REMAINING HEADING, including the end
            # budget's pushes along the plan's final heading. Each target of
            # the tail carries its own recorded heading and the loop turns to
            # it before pushing, so without this the very next push would undo
            # the turn toward the dealer and the loop would walk into the bar
            # again. It accumulates across end turns. The ONE thing that clears
            # it is a look-back REGRESSION, which is the loop saying the
            # position that measured the dx was not where it thought (see the
            # `regressed` branch); short of that the walk either arrives or
            # ends, and there is nothing after the final approach to restore
            # the recorded line for.
            # ... and STOP_LOOK_YAW's `stop_yaw` rides the same way and for
            # the same reason: a yaw taken at a stop has to survive until the
            # next turn-only stop, or the very next turn to a recorded heading
            # would undo the correction that earned it. It is cleared at that
            # stop, on a look-back regression, and on a lost rescue.
            heading = (heading + end_yaw + stop_yaw) % 360.0

        # ONE MORE STEP TOWARD THE DOOR (DOOR_STOP_EXTRA_PUSH), BEFORE THE
        # TURN AND NOT AFTER. The point is to reach the stop and turn THERE:
        # the user watched the loop turn short and rub along the banister, and
        # the stop's verifying fit scale of 0.87 on the looked stops measures
        # the same thing. A push taken AFTER the turn would run along the
        # STOP'S heading -- into the stairs -- which is the opposite change.
        #
        # ONCE PER SERVICING. A turn-back, a turn-wait and a turn-retry all
        # come round the loop to this same plan entry, and that is the same
        # stop, not a second step; `door_stepped` is cleared only by an
        # iteration that services something else, so a re-approach after a
        # rescue or a look-back regression -- which walks other targets to get
        # back here -- takes the step again, deliberately. A stop the plan
        # SKIPS (a wide relocalisation carrying k past it) is never unpacked
        # as `plan[pi]` at all, so this cannot fire on one.
        #
        # Nothing else changes for the WALK: the push is the ordinary
        # PUSH_MAG/PUSH_SEC one along the heading the walk arrived on, its
        # frame is captured and recorded as evidence, and the stop is then
        # turned to and verified exactly as before. The row is evidence only --
        # it moves no counter, spends no blind budget and gates nothing.
        #
        # IT DOES CHANGE ONE THING FOR THE READERS, and that is why
        # DOOR_STEP_ACTION exists: this row shares its iteration number with
        # the row that resolves the stop, and it is recorded FIRST. Every
        # reader that selected an iteration's own fit by "does this row carry
        # an iteration number" now excludes this action by name.
        servicing_door_stop = not do_push and target_k == DOOR_STOP_INDEX
        if not servicing_door_stop:
            door_stepped = False
        elif (DOOR_STOP_EXTRA_PUSH and not door_stepped
                and walk_heading is not None):
            door_stepped = True
            for step_i in range(1, max(1, int(DOOR_STOP_EXTRA_PUSHES)) + 1):
                if (last_cmd is None
                        or abs((walk_heading - last_cmd + 540.0) % 360.0 - 180.0)
                        > TURN_SKIP_DEG):
                    turn_to(walk_heading)
                    last_cmd = walk_heading
                push(PUSH_MAG, PUSH_SEC)
                res["pushes"] += 1
                img_d = capture()
                _save(shots, iteration, k, img_d, log, suffix=f"_door{step_i}")
                fix_d = chain.locate(img_d, target_k)
                inl_d = 0 if fix_d is None else (getattr(fix_d, "inliers", 0) or 0)
                sc_d = None if fix_d is None else getattr(fix_d, "scale", None)
                sc_d = None if sc_d is None else round(float(sc_d), 2)
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_d), "action": DOOR_STEP_ACTION,
                        "lateral": None,
                        "door_step": {"n": step_i,
                                      "heading": round(walk_heading, 1)},
                        "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"door-step {step_i}/{DOOR_STOP_EXTRA_PUSHES}: one more "
                    f"push along {walk_heading:.1f} before the stop turns "
                    f"(the frame after it fits {inl_d} inliers, scale {sc_d})")

        # LOOK AROUND INSTEAD OF PUSHING BLIND AGAIN (BLIND_LOOK_AROUND).
        #
        # It sits HERE, before the turn and the push, because that is the only
        # place a push can be replaced: `blind` is not known until after the
        # push and the capture, so a rule that reads it inside the sensor branch
        # can only ever ADD a look to an iteration that already pushed. This one
        # reads the PREVIOUS iterations' `blind` and ends in `continue`, so the
        # iteration turns twice, captures twice, turns back, and travels NOWHERE.
        #
        # WHAT CHANGES IN THE EVENT LIST, stated because getting this wrong is
        # how a test passes for nobody: where the off-arm has (turn, push,
        # capture), the on-arm has (turn -25, capture, turn +25, capture, turn
        # back). No push. The character does not move; only the camera does.
        #
        # The belief is `_strong_ahead`, unchanged -- the SAME forward search the
        # blind path already runs, on a DIFFERENT view. That is the whole idea:
        # re-matching a frame of wall against sixty more waypoints cannot find
        # the route, and turning the camera is the cheapest thing that changes
        # the frame. It returns only fits at or above STRONG_MIN_INLIERS, which
        # the live gate census puts above the wrong-place MAXIMUM, so the first
        # direction that fits is believed and the second is not paid for.
        #
        # Neither `blind` nor `lost` is spent by a look, so the blind budget,
        # the escape ladder and the LOST RESCUE below are all reachable exactly
        # as before if it finds nothing. `blind_looks` is the bound.
        #
        # THE LOOKED FRAMES GET NO at_table() CHECK, and that is deliberate:
        # neither look-around this copies checks its own frames either, and
        # adding it HERE ALONE would hand the on-arm an arrival path the off-arm
        # does not have, in the A/B whose primary outcome is arrival. One patch,
        # all three sites, on a day nothing depends on the difference.
        if BLIND_LOOK_AROUND and blind == 0 and blind_looks:
            # THE BUDGET IS PER BLIND STRETCH, NOT PER WALK. `blind == 0` is
            # the loop's own definition of "the sensor has seen something
            # credible since": every branch that ends a blind stretch --
            # `relocalised`, `regressed`, `advanced`, and this rule's own found
            # path -- sets it. Without this line the first two-push blind run
            # anywhere in the walk spends the only look, and the stretch this
            # rule was built for gets none while the trial still counts as an
            # on-arm trial. One line, because they all zero `blind` already.
            blind_looks = 0
        if (BLIND_LOOK_AROUND and heading is not None
                and _blind_look_due(blind, blind_looks, BLIND_LOOK_AFTER,
                                    BLIND_LOOK_MAX, do_push, at_end)):
            blind_looks += 1
            blind_looks_total += 1
            res["blind_looks"] = blind_looks_total
            base = heading
            best = None                  # (degrees, inliers, fix)
            looks = 0
            for ddeg in STOP_LOOK_DEG:
                turn_to((base + ddeg) % 360.0)
                img2 = capture()
                looks += 1
                _save(shots, iteration, k, img2, log,
                      suffix=f"_blindlook{int(ddeg):+d}")
                f2 = _strong_ahead(chain, img2, k, n)
                if f2 is not None:
                    best = (ddeg, getattr(f2, "inliers", 0) or 0, f2)
                    break            # already believed; see STRONG_MIN_INLIERS
            # Back to the heading this iteration was going to walk, so the next
            # iteration's turn is the no-op TURN_SKIP_DEG makes it and the push
            # resumes on exactly the line it would have.
            turn_to(base)
            last_cmd = base
            look_row = {"looks": looks, "blind": blind, "from_k": k,
                        "to_k": None, "in_stretch": blind_looks,
                        # WHAT THIS LOOK CLEARED, read BEFORE clearing it. The
                        # argument says these three are always already zero at
                        # a firing (a look fires the first time `blind` reaches
                        # its trigger, which took that many `blind-advance`s,
                        # each of which zeroes misses and stalls, from a
                        # `blind == 0` that every producer pairs with
                        # `lost == 0`). The one corner it does not cover is a
                        # `_blind_cap` that shrinks mid-stretch while the look
                        # is blocked by `do_push`. An argument is not a
                        # measurement, so the row carries the values: a
                        # non-zero `cleared` in any live journal says the
                        # corner is real and those assignments do work.
                        "cleared": {"lost": lost, "misses": misses,
                                    "stalls": stalls},
                        "deg": None if best is None else best[0],
                        "inliers": None if best is None else best[1]}
            if best is not None:
                _, _, f2 = best
                k = min(int(f2.k), n - 1)
                last_cred_k = k
                look_row["to_k"] = k
                # Exactly the forward search's `relocalised` reset, field for
                # field, because it is the same evidence at the same gate --
                # and, like it, this does NOT clear end_yaw or stop_yaw: the
                # character has not moved, so no correction measured at a
                # position is refuted. The pointer re-derives from k at the top
                # of the next iteration, and the stops it steps over drop their
                # yaw there, as they do for every wide jump.
                blind = 0
                lost = 0
                misses = 0
                stalls = 0
                action = BLIND_LOOK_FOUND_ACTION
            else:
                action = BLIND_LOOK_ACTION
            record({"iteration": iteration, "k": k, "target": target_k,
                    "fix": _fix_row(None if best is None else best[2]),
                    "action": action, "lateral": None,
                    "blind_look": look_row, "at_end": at_end,
                    "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            if best is not None:
                log(f"    it {iteration:3d}  k={look_row['from_k']:3d} -> "
                    f"{target_k:3d}  {action}: {look_row['blind']} blind "
                    f"push(es) in, looked {looks} time(s) about {base:.1f} "
                    f"instead of pushing; {look_row['inliers']} inliers at "
                    f"{look_row['deg']:+.0f} deg put k at {k}")
            else:
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"{action}: {blind} blind push(es) in, looked {looks} "
                    f"time(s) about {base:.1f} instead of pushing; nothing at "
                    f"{STRONG_MIN_INLIERS}+ inliers")
            continue

        turned = False
        if heading is not None and (
                last_cmd is None
                or abs((heading - last_cmd + 540.0) % 360.0 - 180.0) > TURN_SKIP_DEG):
            turn_to(heading)
            last_cmd = heading
            turned = True
        settle_rows = None       # this iteration's probe samples, if armed
        push_sig = None          # ... and this iteration's MOVED/BLOCKED
                                 # measurement, from the frames walk_leg holds
                                 # around the push. None on an iteration that
                                 # did not push, which is why a turn-only stop
                                 # and a blind look can never be gated.
        if do_push:
            probe = None
            if settle_probe_on():
                probe = []

                def _sample(_k=k, _probe=probe):
                    t0 = time.monotonic()
                    for d in SETTLE_PROBE_DELAYS:
                        while time.monotonic() - t0 < d:
                            time.sleep(0.005)
                        im = capture()
                        f = chain.locate(im, _k, window=WINDOW) if im is not None else None
                        _probe.append({"delay": d,
                                       "inliers": None if f is None else f.inliers,
                                       "k": None if f is None else f.k})

                push_sig = push(PUSH_MAG, PUSH_SEC, on_release=_sample)
            else:
                push_sig = push(PUSH_MAG, PUSH_SEC)
            settle_rows = probe          # attached to this iteration's row
            res["pushes"] += 1
            if heading is not None:
                walk_heading = heading

        img = capture()
        _save(shots, iteration, k, img, log)

        # STOP AT ONCE, ON EVERY ITERATION, BEFORE THE SENSOR IS EVEN ASKED.
        # This sits before every branch that could move anything.
        if (TABLE_CHECK_TAIL is None or target_k >= n - TABLE_CHECK_TAIL) \
                and at_table(img):
            res["arrived"] = True
            record({"iteration": iteration, "k": k,
                    "target": target_k, "fix": None,
                    "action": "arrived", "lateral": None,
                    "at_end": at_end,
                    "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            log(f"  chain_walk: ARRIVED at iteration {iteration}, k={k} "
                f"(target {target_k} of {n - 1}), {res['pushes']} push(es)")
            return finish()

        if not do_push:
            # A turn-only target: a stationary run in the recording (a corner,
            # a settle). VERIFIED against the stop's own frame: if nothing
            # credible fits after the turn, the plan reached this stop on thin
            # or blind pushes while the character is still short of it (trial
            # 3 turned north into the office instead of onto the stairs), so
            # turn back, push once more along the walking heading, and retry.
            fix_t = chain.locate(img, target_k)
            inl_t = 0 if fix_t is None else (getattr(fix_t, "inliers", 0) or 0)
            sec_t = 0 if fix_t is None else (getattr(fix_t, "second", 0) or 0)
            # Hoisted: `tied` reads the winner's index and offset now, and
            # `real` and the aligned block below read the same two locals.
            kt = None if fix_t is None else int(getattr(fix_t, "k", target_k))
            dxt = 0.0 if fix_t is None else (getattr(fix_t, "dx", 0.0) or 0.0)
            # A TIE NEEDS SEPARATION (see STOP_TIE_FRAC). Three conditions, all
            # required: a close count, the winner and the runner-up NOT BOTH
            # inside this stop's own stationary-run span, and a dx that
            # disagrees. `second_k` is None on a Fix built before it existed
            # (or by a caller that cannot say) -- that is NOT separation, so
            # no tie.
            #
            # BOTH indices, not just the runner-up's. Batch 5e trial 6 -- the
            # frame STOP_TIE_FRAC exists for -- has the WINNER past the span
            # (132 of 116..129) and the near-tied runner-up AT the stop (128).
            # A runner-up-only test called that "not a tie", verified the stop
            # and strafed 0.54 s LEFT on the winner's -386 px: it trusted the
            # candidate past the stop, which is the bug. Two indices inside one
            # span are one spot 0.25 s apart; anything else is two places.
            sec_k = None if fix_t is None else getattr(fix_t, "second_k", None)
            sec_dx = 0.0 if fix_t is None else (getattr(fix_t, "second_dx", 0.0) or 0.0)
            run_lo = spans.get(target_k, target_k)
            sec_here = sec_k is not None and run_lo <= sec_k <= target_k
            win_here = kt is not None and run_lo <= kt <= target_k
            separated = sec_k is not None and not (sec_here and win_here)
            apart = abs(sec_dx - dxt) > STOP_TIE_DX_PX
            tied = (fix_t is not None
                    and sec_t >= STOP_TIE_FRAC * max(1, inl_t)
                    and separated and apart)
            verified = fix_t is not None and inl_t >= FIX_MIN_INLIERS and not tied
            if not verified:
                # Maybe we are already PAST this stop (batch 3 trial 1 stood
                # in the portrait room while the plan still said "doorway").
                wide = _strong_ahead(chain, img, target_k, n)
                if wide is not None:
                    k = min(int(wide.k), n - 1)
                    last_cred_k = k
                    blind = 0
                    lost = 0
                    misses = 0
                    stalls = 0
                    turn_retries = 0
                    early_stop = False
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(wide), "action": "relocalised",
                            "lateral": None, "at_end": False,
                            "seconds": round(now() - it_t0, 2),
                            "elapsed": round(now() - t0, 2)})
                    log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  relocalised "
                        f"past the stop: {wide.inliers} inliers at {wide.k}")
                    continue
            # "PAST" needs a real fit (>= WEAK_MIN_INLIERS) at a LATER
            # waypoint. A junk fit at any index is no evidence: batch 5b
            # trials 2, 5 and 6 read 6-12-inlier fits at k >= stop as "past",
            # skipped the retry that fixes a short stop, and were lost.
            real = fix_t is not None and inl_t >= WEAK_MIN_INLIERS and not tied
            # A REAL fit at the stop's OWN index with a large offset is the
            # stop seen from beside the user's path (batch 5c trial 3: the bar
            # doorway 297 px to the left, the loop right of it): strafe toward
            # the scene, once, and count the stop as seen. Sign per
            # pose.offset: dx < 0 = scene left = camera right = strafe LEFT.
            aligned = None
            if real and abs(kt - target_k) <= WINDOW:
                # A real fit within the stop's window IS the stop seen (audit:
                # the old guard verified only when the offset was LARGE and
                # sent a well-aligned thin fit into three retry pushes).
                verified = True
                if abs(dxt) > LATERAL_TOL_PX:
                    secs = min(LATERAL_CAP_SEC * 2, abs(dxt) / (LATERAL_GAIN * LATERAL_MAG))
                    secs = max(secs, LATERAL_MIN_SEC)
                    side = RIGHT if dxt > 0 else LEFT
                    strafe(side * LATERAL_MAG, secs)
                    aligned = {"side": "right" if side > 0 else "left",
                               "seconds": round(secs, 3), "dx": round(dxt)}
            past_ev = not verified and real and kt is not None and kt > target_k
            looked = None
            pan = runs.get(target_k) if STOP_PAN_FROM_RUN else None
            if not verified and not past_ev and heading is not None and pan and len(pan) >= 2:
                # THE PAN FROM THE RUN: look along headings the drive recorded
                # at this stop and match each against ITS OWN frame. The fit's
                # dx is then relative to that heading and needs no un-yawing.
                picks = [pan[0], pan[len(pan) // 2]][:STOP_PAN_LOOKS]
                best = None
                for idx2, h2 in picks:
                    turn_to(h2 % 360.0)
                    img2 = capture()
                    _save(shots, iteration, k, img2, log, suffix=f"_pan{idx2}")
                    f2 = chain.locate(img2, idx2, window=1)
                    i2 = 0 if f2 is None else (getattr(f2, "inliers", 0) or 0)
                    if f2 is not None and i2 >= FIX_MIN_INLIERS and (best is None or i2 > best[1]):
                        best = (h2, i2, f2)
                    if best is not None and best[1] >= STRONG_MIN_INLIERS:
                        break            # same rule as the look-around below
                turn_to(heading)
                last_cmd = heading
                if best is not None:
                    h2, i2, f2 = best
                    looked = {"pan_heading": round(h2, 1), "inliers": i2}
                    verified = True
                    fix_t, inl_t = f2, i2
                    dx2 = getattr(f2, "dx", 0.0) or 0.0
                    if abs(dx2) > LATERAL_TOL_PX:
                        secs = min(LATERAL_CAP_SEC, abs(dx2) / (LATERAL_GAIN * LATERAL_MAG))
                        if secs >= LATERAL_MIN_SEC:
                            side = RIGHT if dx2 > 0 else LEFT
                            strafe(side * LATERAL_MAG, secs)
                            looked["strafe"] = {"side": "right" if side > 0 else "left",
                                                "seconds": round(secs, 3), "px": round(dx2)}
            elif not verified and not past_ev and heading is not None:
                # LOOK AROUND before believing the stop is occluded or passed:
                # a lateral displacement puts the stop's scene off to one side.
                best = None
                for ddeg in STOP_LOOK_DEG:
                    turn_to((heading + ddeg) % 360.0)
                    img2 = capture()
                    _save(shots, iteration, k, img2, log,
                          suffix=f"_look{int(ddeg):+d}")
                    f2 = chain.locate(img2, target_k)
                    i2 = 0 if f2 is None else (getattr(f2, "inliers", 0) or 0)
                    if f2 is not None and i2 >= FIX_MIN_INLIERS and (best is None or i2 > best[1]):
                        best = (ddeg, i2, f2)
                    if best is not None and best[1] >= STRONG_MIN_INLIERS:
                        # STOP LOOKING. STRONG_MIN_INLIERS (165) is above the
                        # wrong-place MAXIMUM of the live gate census (164,
                        # overnight/census/live_gate_census.json), so the other
                        # direction cannot change this verdict -- it can only
                        # cost a turn, a capture and a locate. The loop used to
                        # sample every direction whatever the first one said,
                        # and `turned-looked` is +20.9 s a trial
                        # (rule_costs/notes.md).
                        break
                turn_to(heading)
                last_cmd = heading
                if best is not None:
                    ddeg, i2, f2 = best
                    looked = {"deg": ddeg, "inliers": i2}
                    verified = True
                    fix_t, inl_t = f2, i2
                    # The scene sat to one side: strafe toward it once. At
                    # 18.6-20.8 px/deg (§8(j)) a 25 deg look is ~500 px, and
                    # the fit's own dx (in the looked frame) refines it; sign
                    # per pose.offset: dx > 0 -> RIGHT. Capped.
                    # Yawing LEFT by d moves the scene RIGHT in the image by
                    # PX_PER_DEG; un-yaw it: the scene's offset from the walking
                    # heading is dx + ddeg * PX_PER_DEG (ddeg < 0 = left). This
                    # is the relation the END TURN inverts; ONE literal, named.
                    dx2 = getattr(f2, "dx", 0.0) or 0.0
                    px = dx2 + ddeg * PX_PER_DEG
                    # ... and that formula assumes the frame that matched IS
                    # the stop's own (see STOP_YAW_NEAR_FIT_ONLY): a fit two or
                    # three waypoints on is a different pose, and the census
                    # says it then over-turns by 29-57% of itself, one way.
                    # `f2.k` is the look's own index; the default keeps a Fix
                    # without one inside the gate rather than outside it.
                    fit_off = int(getattr(f2, "k", target_k)) - target_k
                    near_fit = (not STOP_YAW_NEAR_FIT_ONLY
                                or abs(fit_off) <= STOP_YAW_FIT_TOL)
                    # ... and never at the plan's LAST stop: nothing clears
                    # the yaw after it, so it would ride the whole final
                    # approach under the end turn (STOP_YAW_SKIP_LAST_STOP).
                    last_stop = (STOP_YAW_SKIP_LAST_STOP
                                 and last_stop_j is not None
                                 and pi == last_stop_j)
                    if (STOP_LOOK_YAW and near_fit and not last_stop
                            and abs(px) > LATERAL_TOL_PX):
                        # THE OFFSET AT A LOOKED STOP IS A YAW, NOT A POSITION
                        # (see STOP_LOOK_YAW): turn by it instead of stepping
                        # sideways, and let it ride every push until the next
                        # turn-only stop. The END TURN's own formula and cap,
                        # referenced rather than copied so the two cannot drift
                        # into two different numbers, and its sign convention:
                        # a NEGATIVE px -- the scene sits LEFT of the walking
                        # heading -- turns LEFT, i.e. DECREASING heading, which
                        # is pose.offset's convention. NO strafe: the strafe is
                        # the thing this replaces, and the census says it moved
                        # the character without moving the offset.
                        ddeg_fix = round(max(-END_TURN_MAX_DEG,
                                             min(END_TURN_MAX_DEG,
                                                 float(px) / PX_PER_DEG)), 1)
                        stop_yaw = ddeg_fix
                        new_heading = (heading + stop_yaw) % 360.0
                        turn_to(new_heading)
                        last_cmd = new_heading
                        looked["yaw"] = {"deg": ddeg_fix, "px": round(px)}
                    else:
                        # THE NEAR-FIT GATE REFUSED THIS ONE. Name it in the
                        # journal: a stop the gate sent to the sidestep and a
                        # stop the flag was simply off for take the same path,
                        # and 10.1 is that a no-op and a working path must not
                        # have identical output. Recorded only where a yaw
                        # would otherwise have fired -- inside LATERAL_TOL_PX
                        # there is nothing to skip, and a marker there would
                        # claim the gate refused a correction never on offer.
                        if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:
                            looked["yaw_skipped"] = {
                                "fit_k": int(getattr(f2, "k", target_k)),
                                "off": fit_off}
                            if last_stop:
                                looked["yaw_skipped"]["reason"] = "last stop"
                        # ONE ordinary correction, not a double one: batch 7 trial
                        # 1's look fit (77 inliers, yawed 25 deg) drove a 0.6 s
                        # strafe RIGHT that three credible head-on fits then undid
                        # LEFT. A yawed fit sees the scene half out of frame; it
                        # earns a normal step, and the next head-on fit decides.
                        secs = min(LATERAL_CAP_SEC, abs(px) / (LATERAL_GAIN * LATERAL_MAG))
                        if secs >= LATERAL_MIN_SEC:
                            side = RIGHT if px > 0 else LEFT
                            strafe(side * LATERAL_MAG, secs)
                            looked["strafe"] = {"side": "right" if side > 0 else "left",
                                                "seconds": round(secs, 3), "px": round(px)}
            if not verified and past_ev:
                k = target_k
                misses = 0
                stalls = 0
                turn_retries = 0
                early_stop = False
                unverified_turn = True          # accepted on thin evidence
                why = "past"
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_t), "action": f"turned-{why}",
                        "lateral": None, "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turned-{why} "
                    f"to {heading}: the stop's frame fits "
                    f"{'nothing' if fix_t is None else f'waypoint {int(fix_t.k)} at {inl_t} inliers'}"
                    f", no evidence of being short")
                continue
            # RULE A: A THIN FIT AT A STOP IS NOTHING. These two gates ask
            # "did anything fit at all", and a fit under WEAK_MIN_INLIERS is
            # not an answer: b11 trial 13 read 13 inliers with a runner-up of
            # 11 at the k=196 stop with an NPC filling the frame -- neither
            # None nor tied (11 < 0.9 * 13) -- so the step back and the wait
            # were both skipped and three retry pushes went through a side
            # doorway into an unmapped corridor. WEAK_MIN_INLIERS is reused
            # rather than a new constant invented: it is already the line
            # between right-but-thin (17-36) and junk (6-13).
            nothing_t = fix_t is None or tied or inl_t < WEAK_MIN_INLIERS
            if (not verified and nothing_t and looked is None
                    and turn_retries == 0 and not backed_here):
                backed_here = True
                back(PUSH_MAG, BACK_SEC)
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": None, "action": "turn-back", "lateral": None,
                        "at_end": False, "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turn-back: nothing fits "
                    f"head-on or either side; one step back for clearance")
                continue
            if (not verified and nothing_t and looked is None
                    and turn_retries == 0 and not waited_here):
                waited_here = True
                sleep(STOP_WAIT_SEC)
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": None, "action": "turn-wait", "lateral": None,
                        "at_end": False, "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turn-wait: nothing fits "
                    f"head-on or either side; waited {STOP_WAIT_SEC:.0f}s for whatever is there to move")
                continue
            # A stop reached by turn-early gets NO retry pushes: the retries are
            # for evidence of being short, and an early turn was taken BECAUSE
            # nothing fits (an NPC in the face). Pushing along the old heading
            # there walked into her three more times (third A/B, trial 3).
            # ... and none when the last credible fit had WALL scale: pressed
            # close to something, three pushes along the old heading found
            # nothing at stops 88 and 129 in every slow arrival tonight, and
            # the ladder ran anyway (fast_runs/notes.md). The retries that
            # helped carried scale 1.1-1.2.
            # RULE B: and it needs EVIDENCE OF BEING SHORT, which is the
            # stop's frame fitting an EARLIER waypoint CREDIBLY. A thin fit is
            # not that evidence and neither is silence; both mean "I cannot
            # see", and a push forward on "I cannot see" is how trial 13 left
            # the room. locate() bounds its answer to [stop-1, stop+3], so
            # `kt < target_k` is the whole of the short case.
            short_ev = (fix_t is not None and inl_t >= FIX_MIN_INLIERS
                        and kt is not None and kt < target_k)
            if (not verified and short_ev and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None and not early_stop
                    and last_cred_scale < WALL_SCALE):
                turn_retries += 1
                turn_to(walk_heading)
                last_cmd = walk_heading
                push(PUSH_MAG, PUSH_SEC)
                res["pushes"] += 1
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_t), "action": "turn-retry",
                        "lateral": None, "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turn-retry "
                    f"{turn_retries}/{TURN_RETRY_MAX}: the stop's frame did not "
                    f"fit ({inl_t} inliers); one more push along {walk_heading:.1f}")
                continue
            if not verified:
                # RULE C: AN UNVERIFIED STOP REWINDS. Nothing credible fitted
                # here, so "I am at the stop" is not a reading -- it is the
                # plan talking. Stamping k = target_k there put trial 13's
                # estimate at the dealer's table while the character stood in
                # a service corridor, and the stop table (audit/stop_table.md)
                # says a stop taken unverified arrives 1 in 14 at 129 and 0 in
                # 6 at 166. Go BACK to the last credible waypoint, rewind the
                # plan pointer so it re-derives from there -- the same thing
                # the look-back regression does, and for the same reason --
                # and let the ordinary machinery re-approach: the wide search
                # from the first blind push, the ladder on stalls, the
                # back-off and the looks here.
                #
                # min(), so a rewind never moves the estimate FORWARD: a
                # look-back regression may already have put k behind the last
                # credible fit, and that regression is the better evidence.
                #
                # `rewound_k < k` is the no-op guard, and it is also the
                # honest statement of WHEN THIS RULE APPLIES: only when there
                # is ground between the last credible sighting and where k
                # stands. When the last credible fit IS where k already stands
                # there is nothing to re-approach -- the pointer would
                # re-derive to this same stop and the loop would repeat this
                # iteration, spending a rewind and a stop cycle to change
                # nothing (CLAUDE.md 10.1's no-op path that logs like an
                # action) -- so the stop is advanced unverified exactly as
                # before. b11 trial 12 is that case and is NOT fixed here: its
                # wide relocalisation to 144 (195 inliers) is itself the last
                # credible sighting, and the alternative would be falling back
                # past it onto a 42-inlier fit. Trial 13 is the case that IS
                # fixed: blind and thin pushes carried its estimate to the
                # stop, so there is real ground to re-walk.
                #
                # `blind = 0` and `unverified_turn = False` because the
                # estimate is back on the last thing the SENSOR SAW, which is
                # the opposite of the unverified stamp that flag means -- and
                # `_blind_cap` reads it with no regard to distance, so setting
                # it here would hold the WHOLE re-approach to END_BLIND_MAX
                # (2). A five-target run to a stop that never fits then
                # crosses on 4 blind advances the first time, gets 2 on the
                # re-approach, bridges once with the near-stop turn-early
                # (one-shot per blockage, and every action a re-approach makes
                # is unevidenced so it never re-arms), and the second
                # re-approach goes miss/escape/LOST at a k BEHIND the stop --
                # a walk-ending failure on ground it had just crossed. The
                # bound on a rewind is STOP_REWIND_MAX, LOST, STUCK and the
                # cap. `lost` is NOT reset: a walk that cannot see must still
                # end.
                rewound_k = min(last_cred_k, k)
                if rewinds_at.get(target_k, 0) < STOP_REWIND_MAX and rewound_k < k:
                    rewinds_at[target_k] = rewinds_at.get(target_k, 0) + 1
                    k = rewound_k
                    pi = 0
                    blind = 0
                    misses = 0
                    stalls = 0
                    turn_retries = 0
                    waited_here = False
                    backed_here = False
                    early_stop = False
                    unverified_turn = False
                    action = "turned-unverified"
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(fix_t), "action": action,
                            "lateral": None, "rewound_to": k, "at_end": False,
                            "seconds": round(now() - it_t0, 2),
                            "elapsed": round(now() - t0, 2)})
                    log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                        f"{action}: nothing credible fitted the stop — REWOUND "
                        f"to {k} (rewind {rewinds_at[target_k]}"
                        f"/{STOP_REWIND_MAX} at this stop) "
                        f"rather than claiming the stop")
                    continue
            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            waited_here = False
            backed_here = False
            early_stop = False
            unverified_turn = not verified
            if verified and inl_t >= FIX_MIN_INLIERS:
                # A VERIFIED STOP IS A CREDIBLE SIGHTING, and nothing recorded
                # it as one: `last_cred_k` was written only by the push path's
                # credible-fix branch and the two wide relocalisations. So a
                # walk that verified stop A on a look-around and then failed
                # at stop B rewound to a push fix from BEFORE A, re-walking
                # ground that was never in doubt and crossing back through
                # whatever is between them. FIX_MIN_INLIERS, not `verified`
                # alone: the head-on `real` path verifies from
                # WEAK_MIN_INLIERS (15) up, thin enough to advance on and too
                # thin to be the floor a later rewind falls to. The pan path
                # matched an index inside this stop's own stationary run,
                # where the character does not move, so target_k is the right
                # credit for all three.
                last_cred_k = target_k
            action = "turned" if verified else "turned-unverified"
            if looked is not None:
                action = "turned-looked"
            if aligned is not None:
                action = "turned-aligned"
            record({"iteration": iteration, "k": k, "target": target_k,
                    "fix": _fix_row(fix_t), "action": action,
                    "lateral": looked if looked is not None else aligned,
                    "at_end": False, "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action}"
                f"{'' if turned else ' (skipped, same heading)'} to {heading}"
                f"  ({inl_t} inliers at the stop)"
                # A STOP YAW has no side and no seconds; naming it in the log
                # is how a reader tells it from the sidestep it replaced.
                + (f"  STOP YAW {looked['yaw']['deg']:+.1f} deg on "
                   f"{looked['yaw']['px']} px, no strafe"
                   if looked is not None and "yaw" in looked else "")
                # ... and a yaw the near-fit gate refused names the offset that
                # refused it, beside the sidestep that ran in its place.
                + (("  STOP YAW skipped ("
                    + (looked["yaw_skipped"]["reason"]
                       if "reason" in looked["yaw_skipped"] else
                       f"fit {looked['yaw_skipped']['off']:+d} from the stop")
                    + "), strafe "
                    + (f"{looked['strafe']['side']} for "
                       f"{looked['strafe']['seconds']:.2f}s on "
                       f"{looked['strafe']['px']} px"
                       if "strafe" in looked else "under the minimum, none"))
                   if looked is not None and "yaw_skipped" in looked else ""))
            continue

        fix = chain.locate(img, k)
        inl = None if fix is None else (getattr(fix, "inliers", 0) or 0)
        weak = fix is not None and inl < FIX_MIN_INLIERS
        regressed = False
        if (fix is None or weak) and k > 0:
            # LOOK BACK before believing a miss, as far back as the blind
            # advances could have run ahead, and forward past the target.
            back_hint = plan[max(0, pi - blind - 1)][0] if pi > 0 else 0
            back_hint = max(0, min(back_hint, k - LOOKBACK))
            lbfix = chain.locate(img, back_hint,
                                window=max(WINDOW, (k - back_hint) + WINDOW))
            binl = None if lbfix is None else (getattr(lbfix, "inliers", 0) or 0)
            if lbfix is not None and binl >= FIX_MIN_INLIERS and (fix is None or binl > inl):
                fix, inl, weak = lbfix, binl, False
                if int(lbfix.k) < k:
                    k = max(0, int(lbfix.k))
                    regressed = True
                    # The plan pointer is otherwise monotone: without this,
                    # the target stays > WINDOW ahead of k after a regression
                    # and reached() is impossible (audit: 4 of 6 regressions).
                    pi = 0

        escaped = False
        escape_row = None        # this iteration's escape decision, journalled
        if regressed:
            misses = 0
            stalls = 0
            blind = 0
            lost = 0
            # A REGRESSION REFUTES THE END TURN'S OWN MEASUREMENT, so the yaw
            # it took goes with it. The look-back has just said the character
            # is BEHIND where the loop thought, which is the position the dx
            # that earned the turn was measured from; the regression branch
            # also rewinds the plan pointer to 0, and without this the offset
            # would ride the recorded mid-chain headings from there (a
            # demonstrated 0.0 commanded as 329.5, five waypoints from the
            # start) -- the "steering while walking" family GRAVEYARD closed.
            # The BUDGET is deliberately NOT restored: a walk that regresses
            # and re-approaches gets the turns it has left, never a fresh
            # three per regression.
            end_yaw = 0.0
            # ... and STOP_LOOK_YAW's yaw with it, for the reason above word
            # for word: it was measured at a stop the look-back has just said
            # the character is behind, and this branch rewinds the plan
            # pointer to 0, so the offset would otherwise ride the recorded
            # mid-chain headings from there.
            stop_yaw = 0.0
            action = "regressed"
        elif weak and inl >= WEAK_MIN_INLIERS and int(fix.k) > k:
            # WEAK BUT CONSISTENT: a thin fit that names the target (or its
            # neighbours) is corroboration, not blindness. Trial 1c spent the
            # whole blind budget on 18-23-inlier fits of the corridor that
            # were RIGHT, and had none left for the featureless door where it
            # was needed. Advance to the target, keep the blind budget, and
            # still do not steer on a weak dx (junk at 12 inliers: -180 px).
            misses = 0
            stalls = 0
            lost = 0
            # The blind budget is neither spent nor restored by a thin fit.
            # Advance no further than the thin fit itself names (audit: 84 of
            # 230 thin advances carried a fit BEHIND the target).
            k = min(int(fix.k), target_k, n - 1)
            action = "advanced-weak"
        elif fix is None or weak:
            # THE SENSOR IS BLIND (nothing fit, or nothing credible). Dead-
            # reckon: the push most likely reached its target, so believe that
            # for up to BLIND_MAX pushes -- a featureless door panel is exactly
            # where the plan has to keep moving -- and only then treat the
            # silence as a blockage.
            near_stop_j = None if at_end else _near_stop(pi, plan)
            wide = None
            if blind >= 1 and not at_end:
                # From the first blind push on, look far AHEAD for a strong
                # fix before dead-reckoning again (see WIDE_AHEAD above).
                wide = _strong_ahead(chain, img, k, n)
            if wide is not None:
                k = min(int(wide.k), n - 1)
                last_cred_k = k
                fix = wide
                weak = False
                blind = 0
                lost = 0
                misses = 0
                stalls = 0
                action = "relocalised"
            elif blind < _blind_cap(pi, plan, unverified_turn, last_cred_scale) and not at_end:
                blind += 1
                k = target_k
                misses = 0
                stalls = 0
                action = "blind-advance"
            elif near_stop_j is not None and not turned_early:
                # TURN EARLY, RATHER THAN PUSH INTO WHATEVER IS THERE. The blind
                # budget is spent and a TURN-ONLY stop is within
                # NEAR_STOP_TARGETS plan entries: take the stop NOW instead of
                # the first escape rung. 2026-09-07 22:00-22:10, three trials in
                # a row and both arms of an A/B: an NPC stood ON the turn point
                # in the portrait room (the drive walked north to waypoint 114,
                # stopped, and panned 1.3 -> 303.3 deg, which compiles to pushes
                # at ...112, 114 then one turn-only stop at 129). The estimate
                # stalled at 112 with her filling the frame, the near-a-stop
                # blind budget is ONE, and the walk spent itself on misses and
                # rungs pushing north into her without ever reaching the turn.
                # The user, watching: "you walked too close to her and should
                # have turned left." A turn moves the character NOTHING, so it
                # costs less than any rung and comes before all of them.
                #
                # Only the POINTER moves -- k is not touched, because the rule
                # is about what to do next, not a claim about where we are. The
                # stop's own verification (turned / -aligned / -looked /
                # turn-back / -wait / -retry / -unverified / -past) is unchanged
                # and decides whether the plan really is there. ONE per
                # blockage: see UNEVIDENCED_ACTIONS.
                pi = near_stop_j
                turned_early = True
                early_stop = True
                misses = 0
                stalls = 0
                action = "turn-early"
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix), "action": action,
                        "lateral": None, "at_end": at_end,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turn-early: "
                    f"blind with the budget spent and a turn stop at "
                    f"{plan[pi][0]} within {NEAR_STOP_TARGETS} targets — turning "
                    f"to {plan[pi][2]} now instead of pushing into whatever is "
                    f"in front")
                continue
            elif fix is None:
                lost += 1
                misses += 1
                if misses >= MISS_MAX:
                    action, escaped, escape_row = escape_now(push_sig)
                    misses = 0
                else:
                    action = "miss"
            else:
                lost += 1
                misses = 0
                stalls += 1
                if stalls >= STALL_MAX:
                    action, escaped, escape_row = escape_now(push_sig)
                    stalls = 0
                else:
                    action = "weak"
            if (lost >= LOST_MAX and rescues < LOST_RESCUE_MAX
                    and now() - t0 + LOST_RESCUE_BACK_SEC < time_cap):
                # THE LOST RESCUE (see LOST_RESCUE_MAX). Back out, look around
                # the LAST CREDIBLE SIGHTING, and go on if something strong
                # fits. It fires once per walk and only here, so it cannot
                # touch a trial that is not already over.
                #
                # AND ONLY IF THE CAP CAN PAY FOR IT. This is the one rung that
                # costs more than an iteration — a step back plus up to three
                # turn-and-look pairs plus the turn back — and a rescue that
                # finishes after the cap is worthless anyway, because the next
                # top-of-loop check returns "timed out" before the walk can use
                # it. Unguarded it ran the walk 3.20 s past a 25.4 s cap and
                # still reported "lost" (probe_time_cap.py), so an external
                # ceiling sized off `time_cap` had that much less slack here
                # than on every other iteration (§10.14). The step back is the
                # one part whose duration is known in advance; the looks are
                # bounded below, inside the loop.
                rescues += 1
                h0 = last_cmd if last_cmd is not None else heading
                from_k = k
                back(PUSH_MAG, LOST_RESCUE_BACK_SEC)
                # NOT `k`: when a walk is lost the estimate is ahead of the
                # character, so the window that could contain the view is the
                # one around the last thing the SENSOR actually saw.
                start = (0 if LOST_RESCUE_LOOKBACK is None
                         else max(last_cred_k - LOST_RESCUE_LOOKBACK, 0))
                span = max(last_cred_k + WIDE_AHEAD - start, WIDE_AHEAD)
                looks_plan = [(0.0, "_rescue_look0")]
                for _d in STOP_LOOK_DEG:
                    looks_plan.append((_d, "_rescue_lookL" if _d < 0
                                       else "_rescue_lookR"))
                looks = 0
                best = None                  # (degrees, inliers, fix)
                for ddeg, sfx in looks_plan:
                    if now() - t0 >= time_cap:
                        # The cap owns the walk. The step back is already paid
                        # for and the first look always fits behind it (the
                        # gate above reserved exactly that much), so this can
                        # only ever drop the second and third.
                        break
                    if ddeg != 0.0:
                        if h0 is None:
                            continue         # nothing to yaw about
                        turn_to((h0 + ddeg) % 360.0)
                    img2 = capture()
                    looks += 1
                    _save(shots, iteration, k, img2, log, suffix=sfx)
                    f2 = chain.locate(img2, start, window=span)
                    i2 = 0 if f2 is None else (getattr(f2, "inliers", 0) or 0)
                    if f2 is not None and (best is None or i2 > best[1]):
                        best = (ddeg, i2, f2)
                    if best is not None and best[1] >= STRONG_MIN_INLIERS:
                        # Stop at the first BELIEVED look, exactly as the stop
                        # look-around does: STRONG_MIN_INLIERS is above the
                        # wrong-place maximum, so another direction can only
                        # cost a turn, a capture and a locate.
                        break
                rescue = {"looks": looks, "from_k": from_k, "to_k": None,
                          "deg": None if best is None else best[0],
                          "inliers": None if best is None else best[1]}
                if best is not None and best[1] >= STRONG_MIN_INLIERS:
                    ddeg, i2, f2 = best
                    k = min(int(f2.k), n - 1)
                    last_cred_k = k
                    rescue["to_k"] = k
                    # The same re-aim the rewind and the look-back regression
                    # make when they move k: the plan pointer re-derives as
                    # the first entry past k.
                    pi = 0
                    while pi < len(plan) and plan[pi][0] <= k:
                        pi += 1
                    h2 = plan[pi][2] if pi < len(plan) else plan_last_heading
                    if h2 is not None:
                        turn_to(h2)
                        last_cmd = h2
                    lost = 0
                    misses = 0
                    stalls = 0
                    blind = 0
                    escapes = 0
                    # patch59, beside `escapes` and for the same reason: the
                    # suppression budget is per BLOCKAGE, the rescue has just
                    # ended one, and "rescued" carries no PROGRESS_ACTIONS
                    # prefix so the top-of-loop re-arm never catches it.
                    escape_suppressed = 0
                    unverified_turn = False
                    early_stop = False
                    # THE RESCUE MOVED THE CHARACTER AND THE ESTIMATE, so two
                    # more pieces of state measured before it are refuted with
                    # it. Both were left standing in the first draft and both
                    # were reproduced offline.
                    #
                    # end_yaw is the degrees an END TURN added to every
                    # remaining tail heading, measured from a position this
                    # rung has just contradicted and backed away from. Left
                    # standing it rides the re-aimed heading too: a walk that
                    # turned -30.5 at the tail and was correctly re-aimed to
                    # 95.0 commanded 64.5 on the very next push
                    # (probe_end_yaw.py). The `regressed` branch zeroes it for
                    # the same reason and in the same words; like that branch,
                    # this one does NOT restore the BUDGET (`end_turns`).
                    end_yaw = 0.0
                    # turned_early is the one-shot "turn toward the stop
                    # instead of pushing into whatever is there". It is
                    # re-armed by progress the sensor SAW — and this is that,
                    # believed at the same STRONG_MIN_INLIERS as
                    # `relocalised`, which re-arms it through PROGRESS_ACTIONS.
                    # Left set, a walk rescued back BEFORE the stop it had
                    # already turned early at could not take that cheap turn
                    # again, fell into the rungs, and died lost one stop later
                    # with no second rescue (probe_turned_early.py).
                    turned_early = False
                    # ... and STOP_LOOK_YAW's yaw, for the same reason as the
                    # end turn's above: the rescue has backed the character
                    # out and re-aimed it from a believed look, so a heading
                    # correction measured at a stop it has left is refuted.
                    stop_yaw = 0.0
                    action = "rescued"
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(f2), "action": action,
                            "lateral": None, "rescue": rescue,
                            "at_end": at_end,
                            "seconds": round(now() - it_t0, 2),
                            "elapsed": round(now() - t0, 2)})
                    log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                        f"rescued: backed {LOST_RESCUE_BACK_SEC:.1f}s and "
                        f"looked {looks} time(s) from {start}; {i2} inliers "
                        f"at {ddeg:+.0f} deg put k at {k} (was {from_k})")
                    continue
                # Nothing strong: leave the camera where the walk had it and
                # end exactly as before — the "lost" row and its wording are
                # what every harness and reader parses.
                if h0 is not None:
                    turn_to(h0)
                    last_cmd = h0
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix), "action": "rescue-failed",
                        "lateral": None, "rescue": rescue, "at_end": at_end,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"rescue-failed: backed {LOST_RESCUE_BACK_SEC:.1f}s and "
                    f"looked {looks} time(s) from {start}; best "
                    f"{rescue['inliers']} inliers, under {STRONG_MIN_INLIERS}")
            if lost >= LOST_MAX:
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix), "action": "lost", "lateral": None,
                        "at_end": at_end, "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"  chain_walk: LOST — {lost} iterations with nothing "
                    f"credible after the blind budget at k={k} of {n - 1}")
                return finish(f"lost at k={k} of {n - 1}: {lost} iterations "
                              f"with no credible fix after {BLIND_MAX} blind "
                              f"advances")
        else:
            misses = 0
            blind = 0
            lost = 0
            unverified_turn = False
            last_cred_scale = float(getattr(fix, "scale", 1.0) or 1.0)
            # The waypoint a CREDIBLE fit named is the rewind target. It is the
            # fit's own index, not k: k may be held back by `reached`, and what
            # a rewind wants is the last place the sensor could actually see.
            last_cred_k = min(int(fix.k), n - 1)
            # Never past the target this push was aimed at (one push, one
            # target: a wrong match must not run the plan ahead of the
            # character) and never past the last waypoint (locate() may
            # honestly answer "past the end of the chain").
            new_k = min(int(fix.k), max(target_k, k + ADVANCE_MAX), n - 1)
            # AN ADVANCE IS k ACTUALLY MOVING, not `reached` returning True.
            # At the last waypoint `target_k` IS k, so an honest "I am at or
            # past it" satisfies `reached` on every iteration forever: the
            # stall counter never rose, the escape ladder was unreachable, and
            # 118 of 120 measured rows said "advanced" with k frozen. A success
            # path and a no-op path with identical output (§10.1). Mid-chain
            # this changes nothing — `reached(fix, k+1)` forces `fix.k >= k+1`,
            # so `new_k > k` always holds there.
            past = (int(fix.k) == k and (getattr(fix, "scale", 1.0) or 1.0) >= PAST_SCALE)
            if past and new_k <= k:
                new_k = min(target_k, n - 1)
            if (chain.reached(fix, target_k) or past) and new_k > k:
                k = new_k
                stalls = 0
                action = "advanced-past" if past and not chain.reached(fix, target_k) else "advanced"
            else:
                stalls += 1
                if stalls >= STALL_MAX:
                    action, escaped, escape_row = escape_now(push_sig)
                    stalls = 0
                else:
                    action = "stalled"

        # AT MOST ONE LATERAL PUSH PER ITERATION, and none in an iteration that
        # already escaped: a 0.3s sidestep at 0.45 is ~324px at the closed-loop
        # gain, so a correction computed from the PRE-escape dx would be stale
        # and would fight the escape it just paid for.
        lateral = None
        dx = None if (fix is None or weak) else getattr(fix, "dx", None)
        # The consistency rule: track dx of every fit of at least WEAK_MIN
        # inliers; when the last CONSISTENT_N all exceed the tolerance on the
        # same side, steer by their median as if it were one credible dx.
        inl_now = 0 if fix is None else (getattr(fix, "inliers", 0) or 0)
        if fix is not None and inl_now >= WEAK_MIN_INLIERS and getattr(fix, "dx", None) is not None:
            dx_run.append(float(fix.dx))
            dx_run = dx_run[-CONSISTENT_N:]
        else:
            dx_run = []
        if fix is not None and inl_now >= JUNK_MIN_INLIERS and getattr(fix, "dx", None) is not None:
            junk_run.append(float(fix.dx))
            junk_run = junk_run[-JUNK_CONSISTENT_N:]
        else:
            junk_run = []
        consistent = None
        consistent_n = 0
        if dx is None and not escaped and len(dx_run) >= CONSISTENT_N \
                and all(abs(v) > LATERAL_TOL_PX for v in dx_run) \
                and len({v > 0 for v in dx_run}) == 1:
            consistent = sorted(dx_run)[len(dx_run) // 2]
            consistent_n = CONSISTENT_N
            dx = consistent
            dx_run = []
            junk_run = []
        elif dx is None and not escaped and len(junk_run) >= JUNK_CONSISTENT_N \
                and all(abs(v) > LATERAL_TOL_PX for v in junk_run) \
                and len({v > 0 for v in junk_run}) == 1:
            consistent = sorted(junk_run)[len(junk_run) // 2]
            consistent_n = JUNK_CONSISTENT_N
            dx = consistent
            junk_run = []
            dx_run = []
        if detour_side is not None and k >= detour_until:
            detour_side = None
        if dx is not None and detour_side is not None and (dx > 0) != (detour_side > 0) \
                and abs(dx) > LATERAL_TOL_PX:
            # The correction would undo the detour: hold it until the plan
            # has moved DETOUR_TARGETS past the blockage.
            lateral = {"held": "detour", "dx": float(dx), "side": "held", "seconds": 0.0}
            dx = None
        # TURN TOWARD THE SCENE INSTEAD OF STRAFING, ON THE FINAL APPROACH.
        #
        # It sits HERE, immediately above the strafe and below everything that
        # can contest a dx, because it REPLACES that strafe and must answer to
        # the same three gates -- a skeptic demonstrated all three bypasses on
        # 2026-09-08, and each was worse than the sidestep it replaced: a bad
        # sidestep costs one iteration, a bad end turn rides every remaining
        # heading and spends one of END_TURN_MAX slots.
        #
        #   - `not escaped and not escaped_prev`: an escape's jump or sidestep
        #     has moved the character since this dx was measured. The old
        #     placement fired `escape:jump` and a 30.5 deg turn off the same
        #     pre-escape frame in one iteration. Deferred, not lost: the first
        #     clean iteration still turns.
        #   - BELOW the detour hold, which sets dx to None: three rungs had
        #     just sidestepped LEFT around a blockage and the next fit's +600
        #     turned the camera back into it, permanently.
        #   - the position and budget tests below.
        #
        # dx here is what the strafe would have acted on: a credible fit's dx,
        # the CONSISTENT_N thin-fit median, or the JUNK run's. It cannot fire on
        # a turn-only target: those `continue` long before this point.
        # See END_TURN_PX for the four trials.
        if (dx is not None and abs(dx) > END_TURN_PX and heading is not None
                and not escaped and not escaped_prev
                and end_turns < END_TURN_MAX
                and not regressed
                and (at_end or (last_stop_j is not None and pi > last_stop_j))):
            # D = dx / PX_PER_DEG, from the stop look-around's own un-yaw: a
            # frame measured at heading h + D reads dx_at_h - D * PX_PER_DEG,
            # so this is the yaw that puts the scene back in the middle. A
            # NEGATIVE dx (the scene sits LEFT of where the reference has it)
            # turns LEFT, i.e. DECREASING heading -- pose.offset's convention.
            ddeg = round(max(-END_TURN_MAX_DEG,
                             min(END_TURN_MAX_DEG, float(dx) / PX_PER_DEG)), 1)
            end_yaw += ddeg
            end_turns += 1
            new_heading = (heading + ddeg) % 360.0
            said = _turn_report(turn_to(new_heading))
            last_cmd = new_heading
            lateral = {"end_turn": ddeg, "dx": float(dx),
                       "heading": new_heading, "n": end_turns}
            if said is not None:
                # WHAT THE TURN REPORTED, RECORDED AND GATING NOTHING; see
                # _turn_report for why a hazard must not refuse the turn.
                lateral["turn"] = said
            dx = None           # a turn, not a sidestep: nothing strafes here
        if dx is not None and not escaped and not escaped_prev and abs(dx) > LATERAL_TOL_PX:
            secs = min(LATERAL_CAP_SEC, abs(dx) / (LATERAL_GAIN * LATERAL_MAG))
            if secs < LATERAL_MIN_SEC:
                secs = LATERAL_MIN_SEC     # a shorter push does not move at all
            side = RIGHT if dx > 0 else LEFT
            strafe(side * LATERAL_MAG, secs)
            lateral = {"dx": float(dx),
                       "side": "right" if side > 0 else "left",
                       "seconds": round(secs, 3)}
            if consistent is not None:
                lateral["consistent"] = consistent_n

        # THE VERTICAL OFFSET (PITCH_CORRECT, ships OFF; REPORT mode when on).
        #
        # The mirror of the strafe above, on the axis the loop has always
        # thrown away: the same credibility gate, a dead-band set by the same
        # kind of reasoning, a cap of the same seconds, recorded in the same
        # row. It moves the CAMERA and nothing else -- no push, no strafe, no
        # plan pointer -- which is the only family of navigation change that
        # has ever survived here (GRAVEYARD.md); and until PITCH_STEP_PX and
        # PITCH_DOWN_DY_SIGN have been measured it moves nothing at all and
        # says so in every row.
        #
        # `escaped or escaped_prev` blocks the PRESS and not the row: the
        # strafe skips outright because a sidestep displaces the character
        # between measurement and action, and whether the jump rung's hop is
        # pitch-neutral is unknown. Recording the blocked rows is what keeps
        # them out of the census as a confound instead of losing them.
        pitch_row = None
        if PITCH_CORRECT:
            pitch_row = pitch_correction(
                None if fix is None else getattr(fix, "dy", None),
                0 if fix is None else (getattr(fix, "inliers", 0) or 0),
                escaped=bool(escaped or escaped_prev))
            if pitch_row is not None and pitch_row["acted"]:
                pitch(pitch_row["action"], pitch_row["seconds"])

        # `at_end` is what tells a terminal stall from a mid-chain one in
        # the journal: at the last waypoint k == target and no push can
        # advance it, so the two need different readings.
        escaped_prev = escaped
        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,
               **({"pitch": pitch_row} if pitch_row else {}),
               **({"settle": settle_rows} if settle_rows else {}),
               # patch59, ON EITHER ARM. `push_signal` is the measurement --
               # the inlier count, both frames' keypoint totals and the
               # verdict -- and `escape` is the decision, with the k and the
               # rung order it was made from so a firing outside the bar
               # stretch is not read as evidence about the bar.
               **({"push_signal": push_sig} if push_sig else {}),
               **({"escape": escape_row} if escape_row else {}),
               "seconds": round(now() - it_t0, 2),
               "elapsed": round(now() - t0, 2)}
        record(row)
        # An end turn has no `side` and no `seconds`; the old one-line format
        # would have raised KeyError on it, and padding the dict with a
        # "strafe left 0.00s" that never happened is §10.1's no-op that reads
        # as a success. It gets its own words instead.
        if lateral and "end_turn" in lateral:
            note = (f"  END TURN {lateral['end_turn']:+.1f} deg to heading "
                    f"{lateral['heading']:.1f} on dx {lateral['dx']:.0f} px "
                    f"({end_turns}/{END_TURN_MAX}) — no strafe"
                    + (f", turn_to said {lateral['turn']}"
                       if "turn" in lateral else ""))
        elif lateral:
            note = f"  strafe {lateral['side']} {lateral['seconds']:.2f}s"
        else:
            note = ""
        if pitch_row:
            # Its own words, never padded into the strafe's format: a row that
            # says "strafe ... 0.00s" for a correction on a different axis is
            # §10.1's no-op that reads as a success. And a REPORT says it
            # reported -- "would" and the reasons, never a press that was not
            # sent, because a log line that reads like an action taken is that
            # same bug with better prose.
            if pitch_row["acted"]:
                note += (f"  PITCH {pitch_row['action']}"
                         f" {pitch_row['seconds']:.2f}s"
                         f" on dy {pitch_row['dy']:+.0f} px"
                         f" ({pitch_row['deg']:+.1f} deg)")
            else:
                note += (f"  pitch WOULD correct dy {pitch_row['dy']:+.0f} px"
                         f" ({pitch_row['deg']:+.1f} deg); SENT NOTHING: "
                         + ",".join(pitch_row["blocked"]))
        log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action:14s}"
            f"  fix={_fix_row(fix)}" + note)
