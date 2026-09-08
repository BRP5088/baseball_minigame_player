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
# bought nothing. An integer here restores the old gate for an experiment.
TABLE_CHECK_TAIL = None

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
# A stop whose frame and both looks fit NOTHING is most likely an NPC in the
# face (batch 4 trial 8, Wanda). NPCs move: wait this long once and look
# again before spending retry pushes into whatever is there.
STOP_WAIT_SEC = 2.0
# A stop fit whose runner-up is within this fraction of it is AMBIGUOUS, not
# verification: batch 5e trial 6 'verified' the bar-entrance stop on 33 inliers
# against a runner-up of 33 with dx -386, and was short of the doorway.
STOP_TIE_FRAC = 0.9
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
            ("k", "k_float", "inliers", "dx", "dy", "scale", "second", "detail")}


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
    per = sorted(r["seconds"] for r in res["fixes"] if r.get("iteration"))
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
         now=time.time, sleep=time.sleep, back=None):
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
        back(mag, secs)         ONE continuous BACKWARD push
        strafe(lx, secs)        ONE continuous sidestep, lx > 0 = RIGHT
        jump()                  press Cross once
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
        def push(mag, secs, _st=st):
            # step_sec == seconds is ONE continuous push. Chunking it would
            # re-accelerate from a standstill and cover less ground -- the
            # GRAVEYARD row that ended two rooms adrift.
            return _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                                label="chain push", log=log, step_sec=secs)
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
    turn_retries = 0            # retries spent on the current turn stop
    since_advance = 0           # iterations since k last rose
    dx_run = []                 # dx of the last fits (>= WEAK_MIN_INLIERS), for the consistency rule
    junk_run = []               # dx of the last JUNK fits (>= JUNK_MIN_INLIERS), four agreeing steer once
    last_cred_scale = 1.0       # scale of the last CREDIBLE fit
    escaped_prev = False        # the previous iteration escaped: no lateral undo this one
    waited_here = False         # the current stop has had its one wait
    backed_here = False         # ... and its one step back
    k_prev_iter = 0
    unverified_turn = False     # the last stop was accepted unverified
    turned_early = False        # this blockage has already taken its early turn
    early_stop = False          # the current stop was reached by turn-early: no retry pushes
    walk_heading = None         # the last heading a push was made along
    last_cmd = None             # the last heading actually commanded
    plan_last_heading = next((h for _, _, h in reversed(plan) if h is not None),
                             None)
    last_stop_j = _last_stop_index(plan)   # the end turn fires only past this
    end_yaw = 0.0               # degrees added to every remaining tail heading
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

    def escape():
        """One escape. Jump first, then sidesteps alternating LEFT, RIGHT, ...

        Jump first because it moves nothing sideways, which is what a passage
        with stools on one side and a wall on the other requires; measured
        escape outcomes against real blockers were None, None, jump, None, None,
        None, wait, jump (§8(g)).
        """
        nonlocal escapes
        which = escapes % 4          # the ladder CYCLES: jump, back, left, right, jump, ...
        escapes += 1
        if which == 0:
            # Jump comes round again: the one arrival that beat the patron
            # wedge (batch 5c trial 2) had a jump; batch 5e trial 7, whose jump
            # had fired earlier in the street, got only sidesteps there.
            jump()
            return "escape:jump"
        if which == 1:
            back(PUSH_MAG, BACK_SEC)
            return "escape:back"
        nonlocal detour_side, detour_until
        side = LEFT if which == 2 else RIGHT
        secs = ESCAPE_STRAFE_SEC * (2 if (side > 0 and detour_side is not None and detour_side < 0) else 1)
        strafe(side * ESCAPE_STRAFE_MAG, secs)
        detour_side, detour_until = side, k + DETOUR_TARGETS
        return "escape:left" if side < 0 else "escape:right"

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
        while pi < len(plan) and plan[pi][0] <= k:
            pi += 1
        # THE END OF THE CHAIN IS A BOUNDED PHASE. Past the last target there
        # is nothing left to servo onto: every further push is dead reckoning
        # with no reference, which is the thing this module exists to replace.
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
        if end_yaw and heading is not None:
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
            heading = (heading + end_yaw) % 360.0

        turned = False
        if heading is not None and (
                last_cmd is None
                or abs((heading - last_cmd + 540.0) % 360.0 - 180.0) > TURN_SKIP_DEG):
            turn_to(heading)
            last_cmd = heading
            turned = True
        if do_push:
            push(PUSH_MAG, PUSH_SEC)
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
            tied = fix_t is not None and sec_t >= STOP_TIE_FRAC * max(1, inl_t)
            verified = fix_t is not None and inl_t >= FIX_MIN_INLIERS and not tied
            if not verified:
                # Maybe we are already PAST this stop (batch 3 trial 1 stood
                # in the portrait room while the plan still said "doorway").
                wide = _strong_ahead(chain, img, target_k, n)
                if wide is not None:
                    k = min(int(wide.k), n - 1)
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
            kt = None if fix_t is None else int(getattr(fix_t, "k", target_k))
            dxt = 0.0 if fix_t is None else (getattr(fix_t, "dx", 0.0) or 0.0)
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
            if (not verified and (fix_t is None or tied) and looked is None
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
            if (not verified and (fix_t is None or tied) and looked is None
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
            if (not verified and turn_retries < TURN_RETRY_MAX
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
            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            waited_here = False
            backed_here = False
            early_stop = False
            unverified_turn = not verified
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
                f"  ({inl_t} inliers at the stop)")
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
                    action = escape()
                    escaped = True
                    misses = 0
                else:
                    action = "miss"
            else:
                lost += 1
                misses = 0
                stalls += 1
                if stalls >= STALL_MAX:
                    action = escape()
                    escaped = True
                    stalls = 0
                else:
                    action = "weak"
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
                    action = escape()
                    escaped = True
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

        # `at_end` is what tells a terminal stall from a mid-chain one in
        # the journal: at the last waypoint k == target and no push can
        # advance it, so the two need different readings.
        escaped_prev = escaped
        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,
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
        log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action:14s}"
            f"  fix={_fix_row(fix)}" + note)
