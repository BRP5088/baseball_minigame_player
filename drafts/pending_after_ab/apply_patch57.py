"""patch57: THE VERTICAL OFFSET. Three pieces, separable.

THE USER'S ASK, watching the reticle drift on the stream: "can correction be
made so drift doesn't essentially exist since it's corrected for it ... if they
can add error correction to make heat seeking missiles, then it can be done
with this project."

WHAT THE LOOP DOES TODAY. Every fit computes dx AND dy. `grep -n '\\.dy'
chain_walk.py` returns nothing and `grep -c 'dx'` returns 92: the controller
steers on the horizontal offset and throws the vertical one away, after
writing it to the journal. That is CLAUDE.md 10.1's catalogued shape, "a
measurement taken and discarded" -- and the only reason the drift the user
watched is uncorrected.

THE TWO COMPONENTS OF dy, MEASURED (agent_progress/closed-loop/pitch/
dy_census.py over the last 40 journals, 1,674 credible fits at inliers >= 29):

    |dy|                    median 108 px   p75 234   p90 287   p99 339   max 403
    between WAYPOINTS       median +318 px (wp 30-39) ... -134 px (wp 140-149)
    between WALKS at one    p10-p90 spread, 59 waypoints: MEDIAN 86 px
      waypoint                                          min 1, max 228

The first is the RECORDED DRIVE'S OWN PITCH along the route -- signal, not
error. The second is the per-walk drift, and it is the correctable part.

SO LEVELLING THE CAMERA IS THE WRONG CORRECTION. `input_controller.level_pitch`
homes to the floor stop, i.e. to an ABSOLUTE pitch; driving to an absolute
would fight the recording's own varying pitch, which is the larger term. The
right target is THE RECORDING at that waypoint: dy is measured against the
waypoint's own frame, so dy -> 0 means "hold the pitch the drive held here".
Exactly what the lateral correction does with dx.

WHY THIS IS THE SAFE FAMILY. GRAVEYARD.md records thirteen navigation changes
that moved no number, and its own summary is that every change which FAILED
moved the character while the two survivors move nothing. THIS MOVES THE
CAMERA ONLY -- and in the version that ships it does not move even that.

=============================================================================
THE FIRST VERSION REPORTS. IT DOES NOT ACT. HERE IS WHY, PLAINLY.
=============================================================================

A first draft of this patch fired one fixed 0.05 s press whenever |dy| left a
28 px dead-band. Four reviewers' findings killed that, and the numbers that
killed it were ALREADY IN THE REPO -- no new data was needed.

CLAUDE.md: "Read STAIRS_APPROACH.md before touching leg 2 or anything about
pitch." The first draft never opened it. It says: "PITCH IS UNCONTROLLED IN
PRODUCTION", "Nobody currently knows how to command a specific pitch", and
"THREE NUMBERS ABOUT PITCH CONTRADICT EACH OTHER".

THE THREE NUMBERS, AND WHAT THEY DO TO A FIXED-STEP RULE. The project's own
readings of how many PITCH_STEP_SEC (0.05 s) presses span the WHOLE vertical
travel are 8 (input_controller.py:993, "Full range is about 8 presses", from
the homing sweep's own frame deltas), 20 (input_controller.py:1009-1014, the
ceiling from the floor stop) and 36 (STAIRS_APPROACH.md, measured live). They
disagree, and that disagreement is the point. Taking the vertical field of
view derived below (69.57 deg) as a LOWER bound on the travel, and the
PITCH_PX_PER_DEG derived below (15.5):

    presses for the full travel     deg per press      px of dy per press
             36                          1.93                  30
             20                          3.48                  54
              8                          8.70                 135

THE SMALLEST READING THE PROJECT HAS IS 30 px, AGAINST A 28 px DEAD-BAND. A
bang-bang rule with fixed step S and dead-band D cannot overshoot only while
S <= D. Here S >= D under every reading and 4.8x over it under one, so the
first draft's rule would have hunted: press, cross the band, press back,
forever. That is the SAME failure pose.py already measured on the lateral
axis at an over-large gain -- "the loop OSCILLATED, growing each time: dx went
+175 -> -201 -> +211 -> -215" (pose.py:145-151). A dead-band suppresses action
INSIDE itself; it does not bound a limit cycle.

AND THE SIGN WAS NEVER MEASURED EITHER. The first draft said the direction came
"FROM chain.Fix's OWN DOCSTRING and nothing else". It does not. chain.py:141-148
spells out a `dx SIGN` paragraph and there is no dy paragraph anywhere in
chain.py or pose.py; pose.offset's docstring (pose.py:91-105) states the
convention for dx alone. The dy > 0 -> look_down claim is an INFERENCE (median
(dst - src) is symmetric across the axes, plus an unstated optics argument that
a camera pitched up puts scene content lower in an image whose y grows
downward). Nothing in this project has ever recorded a live dy against a pitch
press -- `grep -rn "look_up\\|look_down"` finds no such site, in pointed
contrast to pose.py's measured strafe/forward/back dx,dy table for the LATERAL
axis. Backwards, the rule DOUBLES the error every iteration.

SO TWO QUANTITIES GATE ACTING AND NEITHER IS MEASURED: the per-press step in
px, and the sign. The ticket's own instruction covers exactly this case -- "If
a gain cannot be derived honestly, make the first version REPORT what it would
have done rather than act, and say so plainly -- an invented constant is the
same bug wearing a fix's clothes." That is what this does.

    PITCH_STEP_PX       = None      UNMEASURED
    PITCH_DOWN_DY_SIGN  = None      UNMEASURED

WITH EITHER OF THEM None THE RULE PRESSES NOTHING, whatever PITCH_MODE says.
Acting is gated on A MEASUREMENT EXISTING, not on a flag, so an invented
constant cannot be smuggled in: the constant that would have to be invented is
the one that unlocks acting, and its absence is loud in every journal row
(`"blocked": ["step_px_unmeasured", "down_sign_unmeasured"]`).

AND THE DEAD-BAND IS DERIVED FROM THE STEP, once the step exists:

    pitch_dead_band() = max(PITCH_TOL_MIN_PX, PITCH_STEP_PX)

which makes D >= S true BY CONSTRUCTION, so the limit cycle above cannot
happen at any measured step. This also corrects how the first draft justified
its dead-band. It claimed to mirror LATERAL_TOL_PX "as the SAME ANGLE" (1.8 deg
x 15.5 px/deg = 28 px). But pose.py:155-165 says why 35 px was really chosen:
"TOLERANCE IS SET BY THE ACTUATOR, not by the measurement ... below about 0.10s
a push does not move the character at all ... So 35px is where the loop can
actually finish." The 1.8 deg is an incidental unit conversion for comparison
against END_TURN's yaw arithmetic, not the reason. THE MIRROR IS THEREFORE THE
PRINCIPLE, NOT THE NUMBER: the dead-band is the actuator's own step, and
PITCH_TOL_MIN_PX = 28.0 is only a provisional FLOOR under it -- of the same
order as the lateral tolerance, binding only if the measured step comes in
below it, and stated here as a placeholder rather than a derivation.

-----------------------------------------------------------------------------
PIECE A -- level_pitch can now return False.

Its docstring at HEAD already records that it "Always returns True" and that
the older promise ("False means homing failed and pitch is NOT known") was one
"no code path could ever produce, so any caller branching on the result was
branching on a constant". THE PREMISE OF THE TICKET IS THEREFORE STALE: the
false promise was already withdrawn. What remains is that the return value
carries ZERO information, and the information exists -- home_pitch's own
verdict, which doorway_pitch.py treats as decisive.

The fix keeps every press exactly as it was (the recovery presses still run;
the count-up still runs) and returns whether the floor stop was CONFIRMED.
Two files quote the old state and are corrected with it: doorway_pitch.py's
module docstring and tests/rig/test_doorway_pitch.py's header. The one caller,
walk_route_v2.start_from_known_pitch, has no importers and line 138 ignores
the return, so this is behaviourally inert in the checkout.

-----------------------------------------------------------------------------
PIECE B -- PITCH_CORRECT, a flag that ships OFF, in REPORT mode.

MIRRORED FROM THE LATERAL CORRECTION, element by element, and each element
says where it came from:

  * dead-band -- the ACTUATOR sets it (pose.py:155-165's own stated reason),
    so pitch_dead_band() is max(PITCH_TOL_MIN_PX, PITCH_STEP_PX). Not the
    lateral 35 px, and not its incidental 1.8 deg.
  * per-iteration cap -- LATERAL_CAP_SEC = 0.3 ("never lunge"). PITCH_CAP_SEC
    is the same 0.3 s of hold. END_TURN_MAX_DEG's role (one bad fit may not
    swing the camera wildly) is served by that cap plus one correction per
    iteration.
  * floor -- LATERAL_MIN_SEC exists because "a push under ~0.10s does not move
    the character at all". PITCH_PRESS_SEC = 0.05 is the hold level_pitch and
    home_pitch already use (input_controller.PITCH_STEP_SEC).
  * credibility gate -- FIX_MIN_INLIERS, the chain's own true-position p05.
    A fit under it "neither advances nor steers", and that now includes the
    camera.
  * an ESCAPE gate -- and this one the first draft argued its way OUT of, on
    the grounds that "pitch is a camera-axis quantity that neither displaces".
    A reviewer pointed out that the jump rung's hop animation is not obviously
    pitch-neutral, and that an iteration can end-turn and pitch-correct off one
    pre-turn fix. Report mode makes the answer free: the row is still written
    with `"blocked": ["escaped"]`, so the census KEEPS the data and labelled,
    while acting stays conservative. Costing a deferred camera nudge to remove
    a confound from the instrument is the right way round.

px per DEGREE, vertically, is DERIVED and is the one number here that is:
camera_fov.json's 102 deg over 1920 px at 1080 tall, rectilinear pinhole --
f = 960/tan(51 deg) = 777.4, vfov = 2*atan(540/777.4) = 69.57 deg,
1080/69.57 = 15.52 px/deg. Ships as 15.5. TWO OTHER READINGS EXIST and are
quoted rather than hidden: the centre gradient f*pi/180 = 13.57 px/deg (a
pinhole has the same centre px/deg on both axes) and the measured horizontal
19.7 scaled by the fov ratio = 16.25. THEY DIFFER BY UP TO 20% -- (16.25 -
13.57)/13.57 = 19.7%, or 16.5% against the larger; the first draft said "at
most 15%", which is wrong under either base, and a reviewer caught it. It
changes nothing that moves while the rule reports: PITCH_PX_PER_DEG only
colours the `deg` a journal row carries, and the dead-band and the press are
both in PIXELS and SECONDS.

-----------------------------------------------------------------------------
PIECE C -- tools/pitch_probe.py, THE INSTRUMENT THAT CLOSES BOTH GAPS.

The report mode cannot measure the two blocked quantities, because measuring
them requires pressing. So the measurement is made where it is cheap and safe:
STANDING STILL, off the route, one press at a time.

    capture -> press look_down once at PITCH_STEP_SEC -> capture
    -> pose.offset(before, after) -> dy

That is px of dy per press AND its sign, in one reading, and it is the SAME
experiment that produced pose.py's own strafe/forward/back dx,dy table. It
repeats in both directions and reports medians and spread. Two minutes on the
console, character stationary, nothing walks.

IT IS NOT RUN BY THIS PATCH and was not run by its author (the console is the
user's). When it has been run, set PITCH_STEP_PX and PITCH_DOWN_DY_SIGN from
its output and the same code acts -- with the dead-band moving to the measured
step automatically, so the D >= S condition holds at whatever it turns out to
be. Setting PITCH_SEC_PER_DEG as well (a second run at several hold lengths)
makes it proportional, capped and floored, with no further edit.

Each row records `hypothesis`, the direction the optics ARGUMENT predicts, so
the probe's answer can be checked against it rather than assumed to match.

-----------------------------------------------------------------------------
HOW IT COMPOSES WITH EVERYTHING ELSE THAT TURNS THE CAMERA. The loop already
turns for the target's heading, for the end turn, for the stop yaw and for the
look-arounds. ALL FOUR ARE YAW, commanded as an absolute compass bearing
through turn_to; pitch is the orthogonal axis and none of them reads or writes
it. The compass strip is a screen-fixed HUD (MEMORY: "Compass markers ride the
camera"), so a pitch change does not move the bar a bearing is read from --
ASSUMED, not re-measured here, and the cheapest thing to check first if a
batch goes strange. What pitch DOES change is what fills the frame, which is
the point: CLAUDE.md records that every fit on the stairs carries a 200-300 px
vertical offset "the loop ignores", and this census puts +318 px at waypoints
30-39. Closing it should raise inliers there. It also changes what sits BEHIND
the screen-fixed prompt band, and §3 records at_table() missing a prompt over
a light table top with the camera pitched down -- that interaction is real and
its direction is unknown.

ONE KNOWN WEAKNESS OF dy ITSELF, recorded and not fixed: match_fit's
estimateAffinePartial2D models a similarity transform, and a pure camera PITCH
is really a perspective change, better described as keystoning than as a
uniform vertical translation. So dy is a small-angle proxy, and it is weakest
exactly where it is largest -- the 200-300 px stairs offsets. FIX_MIN_INLIERS
is the only backstop and it is the same one everything else here uses. Report
mode is how this gets checked before it can steer anything: the census can ask
whether the implied `deg` at the stairs ever exceeds a plausible camera pitch,
which would say the model has broken down there.

-----------------------------------------------------------------------------
COST. In report mode: nothing. No press, no sleep, one dict per iteration.
Once acting, the rule fires on most iterations (|dy| median 108 px) at
PITCH_PRESS_SEC + PITCH_POST_DELAY = 0.35 s each: roughly +17 s on an ~85 s
walk, inside TIME_CAP 400 s and the harness's 420 s ceiling -- and fewer than
that, because the dead-band will have risen to the measured step.

PRE-REGISTERED INSTRUMENT for the eventual A/B (state it before the run,
§10.2). Arrival is not the sensitive measure here. THE MEASURE IS THE
BETWEEN-WALK SPREAD OF dy AT THE SAME WAYPOINT: p10-p90 across walks, median
over waypoints, today 86 px on the off arm. On the on arm it must FALL. It is
computed by the same code on both arms from the journals every walk already
writes (agent_progress/closed-loop/pitch/dy_census.py), needs no extra
instrument, and one batch of 10 an arm measures it. Secondary, in the same
journals: inliers at waypoints 30-69, where the offset is +237..+318 px today.

AND THE FIRST READ OF THE FIRST ACTING BATCH IS AN OSCILLATION CHECK, not the
spread: count sign reversals of the fired action at consecutive iterations
targeting the same waypoint. A hunting signature means THE STEP IS OVERSIZED,
which is a statement about PITCH_STEP_PX, not about whether the correction
helps -- and with the dead-band derived from the step it should be impossible,
so it would mean the measured step is wrong.

    overnight/chain_trials.py --arms off,on --flag PITCH_CORRECT

Applies to: chain_walk.py, tests/routing/test_chain_walk.py,
input_controller.py, doorway_pitch.py, tests/rig/test_doorway_pitch.py, and
two NEW files, tests/rig/test_level_pitch_return.py and tools/pitch_probe.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch57.py [ROOT]
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
I = os.path.join(ROOT, "input_controller.py")
D = os.path.join(ROOT, "doorway_pitch.py")
TD = os.path.join(ROOT, "tests", "rig", "test_doorway_pitch.py")
NEW = os.path.join(ROOT, "tests", "rig", "test_level_pitch_return.py")
PROBE = os.path.join(ROOT, "tools", "pitch_probe.py")

c = open(C).read()
t = open(T).read()
i = open(I).read()
d = open(D).read()
td = open(TD).read()

# ---------------------------------------------------------------- chain_walk
CONSTANTS = '''END_TURN_MAX = 3

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

TIME_CAP = 400.0'''

PURE = '''def pitch_dead_band():
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


def _fix_row(fix):'''

LOOP = '''            if consistent is not None:
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

'''

ROW = '''        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,
               **({"pitch": pitch_row} if pitch_row else {}),
'''

NOTE = '''        else:
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
'''

edits_c = [
 ('END_TURN_MAX = 3\n\nTIME_CAP = 400.0', CONSTANTS),
 ('def _fix_row(fix):', PURE),
 ('        jump()                  press Cross once\n',
  '''        jump()                  press Cross once
        pitch(action, secs)     hold the RIGHT stick vertically for `secs`;
                                `action` is one of PITCH_ACTIONS
'''),
 ('now=time.time, sleep=time.sleep, back=None):',
  'now=time.time, sleep=time.sleep, back=None, pitch=None):'),
 ('''    if at_table is None:
        import table_prompt
        at_table = table_prompt.at_table
''',
  '''    if pitch is None:
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
'''),
 ('''            if consistent is not None:
                lateral["consistent"] = consistent_n

''', LOOP),
 ('''        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,
''', ROW),
 ('''        else:
            note = ""
''', NOTE),
]

# ---------------------------------------------------------- input_controller
edits_i = [
 ('''    Always returns True. Failing to home is NOT a failure here: the comment
    below records why — being already parked at the stop is indistinguishable
    from never reaching it, and both are recoverable by driving firmly to the
    floor and counting up. The docstring used to promise "False means homing
    failed and pitch is NOT known", which no code path could ever produce, so
    any caller branching on the result was branching on a constant.
    """''',
  '''    RETURNS WHETHER THE FLOOR STOP WAS CONFIRMED. False does not mean the
    presses were skipped -- every press below still happens, in the same order,
    and a False result is still a best effort at a level camera. It means
    home_pitch never saw the stop, so the count-up started from an UNKNOWN
    pitch and the caller must not assume a known one. doorway_pitch treats the
    same verdict as decisive and refuses to press at all, because its 22 is
    only meaningful from a confirmed stop; this function is the coarse variant
    that presses anyway and SAYS SO.

    Until patch57 it returned a literal True on every path while promising
    "False means homing failed and pitch is NOT known", so any caller branching
    on the result was branching on a constant. The promise came back rather
    than the constant, because the information exists -- home_pitch's own
    verdict -- and throwing it away is §10.1's measurement taken and discarded.
    """'''),
 ('''    if home_pitch(capture, "look_down", log=log) is None:
        # Already parked at the stop is indistinguishable from never reaching
        # it, and both are fine here: pressing down again is harmless, so drive
        # it firmly to the floor and count up from there.''',
  '''    homed = home_pitch(capture, "look_down", log=log) is not None
    if not homed:
        # Already parked at the stop is indistinguishable from never reaching
        # it, and both are recoverable here: pressing down again is harmless,
        # so drive it firmly to the floor and count up from there -- and report
        # the unconfirmed home, which is the one thing the caller cannot see.'''),
 ('''    time.sleep(0.5)
    return True
''',
  '''    time.sleep(0.5)
    return homed
'''),
]

# ------------------------------------------------------------- doorway_pitch
edits_d = [
 ('''level_pitch, for two reasons its own docstring supplies: it ALWAYS returns
True ("any caller branching on the result was branching on a constant"), and
when homing fails it presses down four more times and counts up anyway. That''',
  '''level_pitch, for a reason its own docstring supplies: when homing fails it
presses down four more times and counts up ANYWAY, reporting the unconfirmed
home (since patch57) rather than refusing to press. That'''),
]

edits_td = [
 ('''= 14 and level_pitch's "4 positions"), and level_pitch's own docstring records
that a caller branching on its result "was branching on a constant". So the
things worth pinning are the ones a plausible edit would silently break:''',
  '''= 14 and level_pitch's "4 positions"), and level_pitch presses on ANYWAY when
the home is not confirmed, merely reporting it (patch57). So the things worth
pinning are the ones a plausible edit would silently break:'''),
]

# ------------------------------------------------- tests/routing/test_chain_walk
NEW_TESTS = '''
class PitchCorrection(unittest.TestCase):
    """patch57: the VERTICAL offset -- REPORTED, not acted on, until two
    quantities have been measured.

    Every fit carries dy and the loop threw it away (`grep -n '.dy'
    chain_walk.py` returned nothing before this patch). The user, watching the
    reticle drift on the stream: "can correction be made so drift doesn't
    essentially exist since it's corrected for it".

    WHY IT ONLY REPORTS. A fixed-step bang-bang rule needs its step to be no
    larger than its dead-band or it hunts, and the project's own three readings
    of the pitch actuator (8, 20 and 36 presses for the whole vertical travel:
    input_controller.py:993, :1009-1014, STAIRS_APPROACH.md) put ONE press at
    30, 54 or 135 px against a 28 px floor -- at or above it under every
    reading. The sign was never measured either: chain.Fix documents `dx SIGN`
    and no dy one. So PITCH_STEP_PX and PITCH_DOWN_DY_SIGN ship None, and while
    either is None NOTHING IS PRESSED, whatever PITCH_MODE says. These tests
    pin that, and pin the acting mechanism by supplying a calibration OF THEIR
    OWN -- the STOP_REWIND_MAX precedent, "the mechanism stays; its tests run
    it for themselves".

    THE TARGET IS THE RECORDING, NOT LEVEL. dy is measured against the
    waypoint's own frame, so dy -> 0 holds the pitch the drive held there. The
    between-waypoint medians run +318 px to -134 px (the drive's own pitch,
    signal) and the between-walk spread at one waypoint is 86 px (the drift,
    the correctable part) -- 1,674 credible fits over 40 journals.
    """

    # A calibration a test supplies for itself: 30 px per press is the SMALLEST
    # of the project's three readings, and -1 is the optics hypothesis. Neither
    # is shipped; both are here so the acting path can be driven at all.
    STEP_PX, DOWN_SIGN = 30.0, -1

    def _rig(self, dy, inliers=120, n=4, table_at=3):
        return Rig(FakeChain(n, [Fix(k=1, scale=1.0, dy=dy, inliers=inliers)]),
                   table_at=table_at)

    def _set(self, **kw):
        for name, value in kw.items():
            prev = getattr(chain_walk, name)
            setattr(chain_walk, name, value)
            self.addCleanup(setattr, chain_walk, name, prev)

    def _report(self, dy, inliers=120):
        """The SHIPPED on-arm: the flag on, both calibrations still None."""
        self._set(PITCH_CORRECT=True)
        rig = self._rig(dy, inliers)
        return rig, rig.go()

    def _act(self, dy, inliers=120, **over):
        """The flag on AND calibrated, which is the only way to press."""
        cal = {"PITCH_CORRECT": True, "PITCH_MODE": "act",
               "PITCH_STEP_PX": self.STEP_PX,
               "PITCH_DOWN_DY_SIGN": self.DOWN_SIGN}
        cal.update(over)
        self._set(**cal)
        rig = self._rig(dy, inliers)
        return rig, rig.go()

    def _off(self, dy, inliers=120):
        rig = self._rig(dy, inliers)
        return rig, rig.go()

    @staticmethod
    def _pitches(rig):
        return [e for e in rig.events if e[0] == "pitch"]

    @staticmethod
    def _rows(res):
        return [r["pitch"] for r in res["fixes"] if "pitch" in r]

    def test_the_flag_ships_OFF_and_these_are_the_literals(self):
        # §10.11: a test that asserts against the constant it guards rises with
        # it and passes forever. Every one of these is pinned as a literal, and
        # each is justified where it is defined.
        self.assertIs(chain_walk.PITCH_CORRECT, False)
        self.assertEqual(chain_walk.PITCH_MODE, "report")
        self.assertIsNone(chain_walk.PITCH_STEP_PX,
                          "px per press is UNMEASURED; tools/pitch_probe.py "
                          "measures it, and until then nothing may press")
        self.assertIsNone(chain_walk.PITCH_DOWN_DY_SIGN,
                          "the sign is UNMEASURED -- chain.Fix documents dx "
                          "and no dy -- and backwards it DOUBLES the error")
        self.assertIsNone(chain_walk.PITCH_SEC_PER_DEG)
        self.assertEqual(chain_walk.PITCH_TOL_MIN_PX, 28.0)
        self.assertEqual(chain_walk.PITCH_PX_PER_DEG, 15.5)  # derived, not 19.7
        self.assertNotEqual(chain_walk.PITCH_PX_PER_DEG, chain_walk.PX_PER_DEG,
                            "the vertical figure is DERIVED from the fov, never "
                            "assumed equal to the measured yaw one")
        self.assertEqual(chain_walk.PITCH_PRESS_SEC, 0.05)
        self.assertEqual(chain_walk.PITCH_POST_DELAY, 0.30)
        self.assertEqual(chain_walk.PITCH_CAP_SEC, 0.30)
        self.assertEqual(chain_walk.PITCH_ACTIONS, ("look_up", "look_down"))

    # ---- the dead-band is the ACTUATOR's step, which is the anti-hunt rule --

    def test_the_dead_band_is_never_smaller_than_one_press(self):
        # THE STABILITY CONDITION, and the whole reason the first draft was
        # wrong: a fixed step S outside a dead-band D overshoots to the other
        # side unless S <= D. Making the band the step makes that impossible at
        # ANY measured step -- so this is a property, checked across the three
        # readings the project actually has (30 / 54 / 135 px per press) and
        # well past them.
        self.assertEqual(chain_walk.pitch_dead_band(),
                         chain_walk.PITCH_TOL_MIN_PX,
                         "uncalibrated, the floor is all there is")
        for step in (30.0, 54.0, 135.0, 1.0, 500.0):
            self._set(PITCH_STEP_PX=step)
            band = chain_walk.pitch_dead_band()
            self.assertGreaterEqual(band, step,
                                    f"a {step} px step needs a band >= it")
            self.assertGreaterEqual(band, chain_walk.PITCH_TOL_MIN_PX)
        # ... and the floor is a FLOOR, not the answer: a big step raises it.
        self._set(PITCH_STEP_PX=135.0)
        self.assertEqual(chain_walk.pitch_dead_band(), 135.0)

    def test_a_calibrated_step_widens_the_band_a_walk_uses(self):
        # Not just the pure function: the LOOP must ask for the band each time.
        # 100 px is outside the 28 px floor and inside a 135 px step.
        _, loose = self._report(+100.0)
        self.assertEqual(len(self._rows(loose)), 1)
        self._set(PITCH_STEP_PX=135.0)
        rig, tight = self._rig(+100.0, 120), None
        tight = rig.go()
        self.assertEqual(self._rows(tight), [],
                         "inside a 135 px band, 100 px is not an error")

    # ---- the flag OFF ----------------------------------------------------

    def test_OFF_the_vertical_offset_is_INVISIBLE(self):
        big, _ = self._off(+400.0)
        none, _ = self._off(0.0)
        self.assertEqual(self._pitches(big), [], "nothing may touch the pitch")
        self.assertEqual(big.events, none.events,
                         "with the flag off a 400 px vertical offset must "
                         "change NOTHING about the walk")

    def test_OFF_no_row_carries_a_pitch_key(self):
        _, res = self._off(+400.0)
        self.assertEqual(self._rows(res), [],
                         "a row padded with a correction that never happened is "
                         "§10.1's no-op that reads as a success")
        # ANTI-VACUITY: the same fixture ON does write one, so this is not
        # passing because the fixture could never produce a correction.
        _, on_res = self._report(+400.0)
        self.assertEqual(len(self._rows(on_res)), 1)

    # ---- the SHIPPED on-arm: it reports and presses nothing --------------

    def test_the_shipped_on_arm_REPORTS_AND_PRESSES_NOTHING(self):
        rig, res = self._report(+400.0)
        self.assertEqual(self._pitches(rig), [],
                         "with PITCH_STEP_PX and PITCH_DOWN_DY_SIGN unmeasured "
                         "the rule may not send a single press")
        row, = self._rows(res)
        self.assertIs(row["acted"], False)
        self.assertIsNone(row["action"], "it must not name a direction it "
                                         "cannot justify")
        self.assertIsNone(row["seconds"])
        self.assertEqual(set(row["blocked"]),
                         {"step_px_unmeasured", "down_sign_unmeasured",
                          "report_mode"})
        # ... and it reports what it MEASURED, which is the point of the mode.
        self.assertEqual(row["dy"], 400.0)
        self.assertAlmostEqual(row["deg"], round(400.0 / 15.5, 1), places=6)
        self.assertEqual(row["band"], 28.0)
        self.assertEqual(row["hypothesis"], "look_down",
                         "the optics ARGUMENT, labelled as one so the probe's "
                         "measured sign can be checked against it")

    def test_the_MODE_ALONE_CANNOT_UNLOCK_A_PRESS(self):
        # The safety argument of the whole first version. Setting the mode is
        # exactly the edit someone in a hurry makes; it must not be enough.
        self._set(PITCH_CORRECT=True, PITCH_MODE="act")
        rig = self._rig(+400.0)
        res = rig.go()
        self.assertEqual(self._pitches(rig), [])
        row, = self._rows(res)
        self.assertIs(row["acted"], False)
        self.assertEqual(set(row["blocked"]),
                         {"step_px_unmeasured", "down_sign_unmeasured"})
        # HALF a calibration is still no calibration.
        self._set(PITCH_STEP_PX=self.STEP_PX)
        rig2 = self._rig(+400.0)
        rig2.go()
        self.assertEqual(self._pitches(rig2), [],
                         "the step alone, without the sign, may not press")

    # ---- the flag ON and CALIBRATED --------------------------------------

    def test_the_MEASURED_sign_decides_the_direction_not_the_hypothesis(self):
        # PITCH_DOWN_DY_SIGN is the sign of the CHANGE look_down makes to dy,
        # so look_down reduces |dy| exactly when that change opposes dy. Driven
        # BOTH WAYS: if the code fell back to `hypothesis` (dy > 0 -> look_down)
        # the second half of this test fails, which is the only way to tell the
        # measured convention from the guessed one.
        rig, res = self._act(+400.0, PITCH_DOWN_DY_SIGN=-1)
        got = self._pitches(rig)
        self.assertEqual(len(got), 1, "exactly one correction per iteration")
        self.assertEqual(got[0][1], "look_down")
        self.assertEqual(got[0][2], chain_walk.PITCH_PRESS_SEC)
        row, = self._rows(res)
        self.assertIs(row["acted"], True)
        self.assertEqual(row["blocked"], ())
        self.assertEqual(row["action"], "look_down")
        self.assertEqual(row["step_px"], self.STEP_PX)
        self.assertIsNone(row["gain"], "the row says which control law ran")

    def test_the_OPPOSITE_measured_sign_inverts_the_direction(self):
        rig, res = self._act(+400.0, PITCH_DOWN_DY_SIGN=+1)
        got = self._pitches(rig)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][1], "look_up",
                         "with look_down measured to INCREASE dy, a positive "
                         "dy must be answered with look_up")
        row, = self._rows(res)
        self.assertEqual(row["action"], "look_up")
        self.assertEqual(row["hypothesis"], "look_down",
                         "and the hypothesis still says what the optics "
                         "argument predicted, so the two can be compared")

    def test_a_NEGATIVE_offset_is_answered_the_other_way(self):
        rig, res = self._act(-400.0, PITCH_DOWN_DY_SIGN=-1)
        self.assertEqual([e[1] for e in self._pitches(rig)], ["look_up"])
        self.assertEqual(self._rows(res)[0]["action"], "look_up")

    def test_inside_the_dead_band_nothing_is_sent_and_nothing_is_said(self):
        rig, res = self._act(+20.0)
        self.assertEqual(self._pitches(rig), [],
                         "|dy| under the dead-band must not be corrected")
        self.assertEqual(self._rows(res), [],
                         "and must not write a row either -- a row for an "
                         "offset nobody would act on is noise in the census")
        # ... and just OUTSIDE it, it fires: the dead-band is a boundary, not a
        # reason nothing ever happens. 31 px clears the 30 px calibrated band.
        rig2, _ = self._act(+31.0)
        self.assertEqual(len(self._pitches(rig2)), 1)

    def test_a_THIN_fit_never_steers_the_camera(self):
        # FIX_MIN_INLIERS is the chain's own true-position p05; a fit under it
        # "neither advances nor steers", and that now includes the camera. A
        # thin fit's offsets are junk (-847 px at 7 inliers).
        thin, thin_res = self._act(+400.0,
                                   inliers=chain_walk.FIX_MIN_INLIERS - 1)
        self.assertEqual(self._pitches(thin), [])
        self.assertEqual(self._rows(thin_res), [])
        credible, _ = self._act(+400.0, inliers=chain_walk.FIX_MIN_INLIERS)
        self.assertEqual(len(self._pitches(credible)), 1,
                         "the SAME fixture one inlier up must fire, or the test "
                         "above passes for the wrong reason")

    def test_an_unmeasurable_fix_is_never_corrected(self):
        self._set(PITCH_CORRECT=True, PITCH_MODE="act",
                  PITCH_STEP_PX=self.STEP_PX,
                  PITCH_DOWN_DY_SIGN=self.DOWN_SIGN)
        rig = Rig(FakeChain(4, [None]), table_at=3)
        rig.go()
        self.assertEqual(self._pitches(rig), [])

    def test_an_ESCAPE_blocks_the_PRESS_and_KEEPS_the_row(self):
        # Reached through a REAL plan, not by poking a flag: a credible fit
        # that never advances k stalls, and STALL_MAX stalls fire the ladder
        # and set `escaped`. The strafe skips such an iteration outright
        # because a sidestep displaces the character between the measurement
        # and the action; whether the jump rung's hop is pitch-neutral is
        # unknown, so the press waits and the ROW IS STILL WRITTEN -- which is
        # what keeps those iterations out of the census as a silent confound.
        self._set(PITCH_CORRECT=True, PITCH_MODE="act",
                  PITCH_STEP_PX=self.STEP_PX,
                  PITCH_DOWN_DY_SIGN=self.DOWN_SIGN)
        stuck = Fix(k=1, scale=0.5, dy=+400.0, inliers=120)
        rig = Rig(FakeChain(6, default=stuck), table_at=None)
        res = rig.go()
        rows = self._rows(res)
        self.assertGreater(rig.count("jump"), 0,
                           "the fixture must actually reach the escape ladder")
        blocked = [r for r in rows if "escaped" in r["blocked"]]
        self.assertGreaterEqual(len(blocked), 2,
                                "the escaping iteration and the one after it")
        for r in blocked:
            self.assertIs(r["acted"], False)
            self.assertIsNone(r["action"])
            self.assertEqual(r["dy"], 400.0, "the measurement is still there")
        # ANTI-VACUITY: most iterations of this same walk DO act, so the block
        # above is the escape and not a walk that never corrects at all.
        self.assertTrue(any(r["acted"] for r in rows))
        acted = [e for e in rig.events if e[0] == "pitch"]
        self.assertEqual(len(acted), sum(1 for r in rows if r["acted"]))

    def test_the_hold_is_CAPPED_and_FLOORED_once_a_gain_exists(self):
        # The cap is unreachable while PITCH_SEC_PER_DEG is None (one press is
        # the whole command), so it is driven here at a gain of its own -- the
        # STOP_REWIND_MAX precedent. Without this the cap is a guard that
        # cannot fire.
        self.assertEqual(chain_walk.PITCH_CAP_SEC, 0.30)     # the literals
        self.assertEqual(chain_walk.PITCH_PRESS_SEC, 0.05)
        gain = 0.01                                          # s per degree
        # BOTH BOUNDS MUST BIND AT ONE GAIN or one of the two assertions below
        # is about a quantity the law never produced: 5000 px is 322.6 deg is
        # 3.2 s uncapped, and 31 px is 2.0 deg is 0.020 s unfloored.
        uncapped = abs(5000.0 / chain_walk.PITCH_PX_PER_DEG) * gain
        unfloored = abs(31.0 / chain_walk.PITCH_PX_PER_DEG) * gain
        self.assertGreater(uncapped, 0.6,
                           "the fixture must exceed even a DOUBLED cap, or the "
                           "assertion below holds whatever the cap is")
        self.assertLess(unfloored, chain_walk.PITCH_PRESS_SEC / 2.0,
                        "and fall well under even a HALVED floor")
        big, _ = self._act(+5000.0, PITCH_SEC_PER_DEG=gain)
        self.assertEqual(self._pitches(big)[0][2], 0.30)
        small, _ = self._act(+31.0, PITCH_SEC_PER_DEG=gain)
        self.assertEqual(self._pitches(small)[0][2], chain_walk.PITCH_PRESS_SEC)
        # ... and BETWEEN them the law is proportional, so the two bounds are
        # bounds and not the whole function: 155 px is 10 deg is 0.10 s.
        mid, _ = self._act(+155.0, PITCH_SEC_PER_DEG=gain)
        self.assertAlmostEqual(self._pitches(mid)[0][2], 0.1, places=3)

    def test_the_character_is_never_moved_by_this_rule(self):
        # THE WHOLE SAFETY ARGUMENT (GRAVEYARD: every failed change moved the
        # character; both survivors move nothing). A dy of 400 with dx zero
        # must produce a pitch press and NOT a strafe, a push or a jump.
        rig, _ = self._act(+400.0)
        self.assertEqual(len(self._pitches(rig)), 1)
        self.assertEqual(rig.strafes(), [])
        self.assertEqual(rig.count("jump"), 0)
        off, _ = self._off(+400.0)
        self.assertEqual(rig.count("push"), off.count("push"),
                         "the rule must not add or remove a single push")

    # ---- the pure function, where every guard can be driven --------------

    def test_the_predicate_refuses_a_thin_fit_and_a_missing_dy(self):
        f = chain_walk.pitch_correction
        self.assertIsNone(f(400.0, chain_walk.FIX_MIN_INLIERS - 1))
        self.assertIsNone(f(None, 200))
        self.assertIsNone(f(400.0, None))
        self.assertIsNotNone(f(400.0, chain_walk.FIX_MIN_INLIERS))

    def test_the_predicate_refuses_the_dead_band_on_both_sides(self):
        f = chain_walk.pitch_correction
        self.assertIsNone(f(+28.0, 200), "the boundary itself is inside")
        self.assertIsNone(f(-28.0, 200))
        self.assertEqual(f(+29.0, 200)["hypothesis"], "look_down")
        self.assertEqual(f(-29.0, 200)["hypothesis"], "look_up")

    def test_the_predicate_blocks_on_an_escape_and_still_answers(self):
        self._set(PITCH_MODE="act", PITCH_STEP_PX=self.STEP_PX,
                  PITCH_DOWN_DY_SIGN=self.DOWN_SIGN)
        f = chain_walk.pitch_correction
        free = f(+400.0, 200, escaped=False)
        held = f(+400.0, 200, escaped=True)
        self.assertIs(free["acted"], True)
        self.assertEqual(free["action"], "look_down")
        self.assertIs(held["acted"], False)
        self.assertEqual(held["blocked"], ("escaped",))
        self.assertEqual(held["dy"], free["dy"],
                         "a blocked row still carries the measurement")

    def test_the_predicate_reports_the_degrees_it_would_command(self):
        # The journal's own instrument: dy in px AND the angle it implies, so a
        # census can be taken in either unit without re-deriving px/deg.
        got = chain_walk.pitch_correction(+310.0, 200)
        self.assertAlmostEqual(got["deg"], 20.0, places=1)
        self.assertEqual(got["dy"], 310.0)
'''

RIG_PITCH = '''    def strafe(self, lx, secs):
        self.t += secs
        self.events.append(("strafe", lx, secs))

    def pitch(self, action, secs):
        # patch57. Recorded like every other console call, so a test can assert
        # that NOTHING touches the pitch with the flag off -- or with it on and
        # the calibration still unmeasured, which is what ships.
        self.t += secs
        self.events.append(("pitch", action, secs))
'''

AST_TEST = '''    def test_the_only_button_pressed_is_cross(self):
        calls = [node for node in ast.walk(self.tree)
                 if isinstance(node, ast.Call)
                 and getattr(node.func, "attr", None) == "press" and node.args]
        pressed = [n.args[0].value for n in calls
                   if isinstance(n.args[0], ast.Constant)]
        self.assertEqual(pressed, ["cross"])
        # THE PITCH WRAPPER PRESSES A VARIABLE (patch57), so the constant scan
        # above cannot see it -- exactly how a guard quietly stops covering the
        # module it guards. Exactly one such call may exist, and the only values
        # its argument can take are PITCH_ACTIONS: both are STICK AXES on the
        # FIFO (right_y), neither is a button, so "one button, and it is Cross"
        # still holds. A second variable press fails here until it is justified.
        import input_controller as ic
        variable = [n for n in calls if not isinstance(n.args[0], ast.Constant)]
        self.assertEqual(len(variable), 1,
                         "one press call takes a variable: the pitch wrapper")
        self.assertEqual(chain_walk.PITCH_ACTIONS, ("look_up", "look_down"))
        for action in chain_walk.PITCH_ACTIONS:
            self.assertIn(action, ic.STICK_AXES,
                          "the pitch actions are stick deflections")
            self.assertNotIn(action, ic.BUTTON_BITS,
                             "and neither of them is a button")
'''

WRAPPER_TEST = '''    def test_the_pitch_correction_reaches_press_on_the_STICK_axis(self):
        # patch57, and this class exists for exactly this reason: a stub can
        # only pin the value chain_walk hands IT. Only input_controller.press
        # pins that the correction lands on right_y with the right sign.
        #
        # It is driven at a CALIBRATION OF ITS OWN, because what ships presses
        # nothing: PITCH_STEP_PX and PITCH_DOWN_DY_SIGN are None and the rule
        # refuses. 30 px is the smallest of the project's three readings of the
        # actuator; -1 is the optics hypothesis. Neither is shipped.
        import input_controller as ic
        for name, value in (("PITCH_CORRECT", True), ("PITCH_MODE", "act"),
                            ("PITCH_STEP_PX", 30.0),
                            ("PITCH_DOWN_DY_SIGN", -1)):
            prev = getattr(chain_walk, name)
            setattr(chain_walk, name, value)
            self.addCleanup(setattr, chain_walk, name, prev)
        self.table_at = 3
        self._walk(FakeChain(4, [Fix(k=1, scale=1.0, dy=+400.0)]))
        self.assertIn("look_down", self.presses,
                      "look_down measured to REDUCE dy means a positive dy is "
                      "answered with look_down")
        self.assertNotIn("look_up", self.presses)
        self.assertEqual(ic.STICK_AXES["look_down"][0], "right_y")
        self.assertGreater(ic.STICK_AXES["look_down"][1], 0.0)
        self.assertLess(ic.STICK_AXES["look_up"][1], 0.0,
                        "the two actions must be opposite deflections of the "
                        "same axis, or the sign above means nothing")

    def test_the_SHIPPED_pitch_flag_reaches_press_NOT_AT_ALL(self):
        # The same walk with only the flag on -- what a batch would actually
        # run -- must send nothing to input_controller.press at all.
        prev = chain_walk.PITCH_CORRECT
        chain_walk.PITCH_CORRECT = True
        self.addCleanup(setattr, chain_walk, "PITCH_CORRECT", prev)
        self.table_at = 3
        self._walk(FakeChain(4, [Fix(k=1, scale=1.0, dy=+400.0)]))
        self.assertEqual(self.presses, [],
                         "PITCH_STEP_PX and PITCH_DOWN_DY_SIGN are unmeasured, "
                         "so the shipped on-arm reports and presses nothing")

    def test_the_escape_presses_CROSS_and_sidesteps_on_the_same_axis(self):'''

edits_t = [
 ("class Lateral(unittest.TestCase):", NEW_TESTS + "\nclass Lateral(unittest.TestCase):"),
 ('''    def strafe(self, lx, secs):
        self.t += secs
        self.events.append(("strafe", lx, secs))
''', RIG_PITCH),
 ('''            jump=self.jump, at_table=self.at_table, now=self.now,
            sleep=self.sleep, back=self.back, **kw)''',
  '''            jump=self.jump, at_table=self.at_table, now=self.now,
            sleep=self.sleep, back=self.back, pitch=self.pitch, **kw)'''),
 ('        self.dy = dy               # chain.Fix carries it; recorded, never acted on',
  '        self.dy = dy               # the pitch correction reads it (patch57)'),
 ('''    def test_the_only_button_pressed_is_cross(self):
        pressed = [node.args[0].value for node in ast.walk(self.tree)
                   if isinstance(node, ast.Call)
                   and getattr(node.func, "attr", None) == "press"
                   and node.args and isinstance(node.args[0], ast.Constant)]
        self.assertEqual(pressed, ["cross"])
''', AST_TEST),
 ('    def test_the_escape_presses_CROSS_and_sidesteps_on_the_same_axis(self):',
  WRAPPER_TEST),
]

NEW_FILE = '''"""level_pitch reports whether the floor stop was CONFIRMED (patch57).

Until patch57 it returned a literal True on every path, so a caller branching
on the result was branching on a constant -- the docstring had already been
corrected to admit that, which left the information (home_pitch's own verdict)
measured and thrown away. This pins the branch that exists now:

  (a) a CONFIRMED home returns True;
  (b) an UNCONFIRMED home returns False -- the `return False` path this file
      exists to keep alive;
  (c) and False is NOT a refusal: every press still happens, in the same order
      and the same count, so the fix changed what is REPORTED and nothing that
      moves. level_pitch is the coarse variant that presses anyway;
      doorway_pitch is the one that refuses.

OFFLINE BY CONSTRUCTION: home_pitch, press and time.sleep are replaced on the
real module for the length of each run, so nothing can reach the console, and
the capture is a stub that is never looked at.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import input_controller as ic          # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (f"  -- {detail}" if detail else ""))
    if not cond:
        ok = False


def run(home_result):
    """One level_pitch() with home_pitch stubbed. Returns (result, presses)."""
    presses = []
    saved = (ic.home_pitch, ic.press)
    try:
        ic.home_pitch = lambda capture, action="look_up", log=None: home_result
        ic.press = lambda name, hold_seconds=0.05, post_delay=None: (
            presses.append((name, hold_seconds, post_delay)), True)[1]
        import time as _time
        slept = _time.sleep
        _time.sleep = lambda s: None
        try:
            return ic.level_pitch(lambda: None), presses
        finally:
            _time.sleep = slept
    finally:
        ic.home_pitch, ic.press = saved


got_true, presses_true = run(home_result=3)
got_false, presses_false = run(home_result=None)

check("(a) a CONFIRMED home returns True", got_true is True, repr(got_true))
check("(b) an UNCONFIRMED home returns False", got_false is False,
      repr(got_false))
check("(b) the two answers differ, so the return is not a constant",
      got_true is not got_false)

# (c) the behaviour is unchanged: the False run presses MORE, never less --
# four recovery look_downs then the same count-up.
ups_true = [p for p in presses_true if p[0] == "look_up"]
ups_false = [p for p in presses_false if p[0] == "look_up"]
downs_false = [p for p in presses_false if p[0] == "look_down"]
check("(c) a confirmed home counts up PITCH_STEPS_FROM_BOTTOM times",
      len(ups_true) == ic.PITCH_STEPS_FROM_BOTTOM,
      f"{len(ups_true)} vs {ic.PITCH_STEPS_FROM_BOTTOM}")
check("(c) a confirmed home presses look_down NOT AT ALL itself",
      [p for p in presses_true if p[0] == "look_down"] == [])
check("(c) an unconfirmed home still counts up the same number of times",
      len(ups_false) == len(ups_true), f"{len(ups_false)} vs {len(ups_true)}")
check("(c) ... after driving firmly to the floor 4 times",
      len(downs_false) == 4, f"{len(downs_false)}")
check("(c) every press uses PITCH_STEP_SEC",
      all(p[1] == ic.PITCH_STEP_SEC for p in presses_true + presses_false))

# ANTI-VACUITY: the stub was consulted at all, and the real one is what ran.
check("(d) the run actually pressed something (the stub was consulted)",
      len(presses_true) > 0 and len(presses_false) > 0)
check("(d) level_pitch is the real module's function",
      ic.level_pitch.__module__ == "input_controller")

print("\\nall green" if ok else "\\nFAILURES above")
sys.exit(0 if ok else 1)
'''

PROBE_FILE = '''"""How far does ONE pitch press move the picture, and which way? (patch57)

THE TWO NUMBERS chain_walk.PITCH_STEP_PX and chain_walk.PITCH_DOWN_DY_SIGN
need, and the only reason the pitch correction ships in REPORT mode. Both ship
None; while either is None the correction presses nothing.

WHY THEY CANNOT BE DERIVED. STAIRS_APPROACH.md: "PITCH IS UNCONTROLLED IN
PRODUCTION ... Nobody currently knows how to command a specific pitch", and
"THREE NUMBERS ABOUT PITCH CONTRADICT EACH OTHER". The project's three readings
of how many PITCH_STEP_SEC presses span the whole vertical travel are 8
(input_controller.py:993), 20 (input_controller.py:1009-1014) and 36
(STAIRS_APPROACH.md) -- 30, 54 or 135 px of dy per press at 15.5 px/deg. And no
site anywhere has ever recorded a live dy against a pitch press, in pointed
contrast to pose.py's measured strafe/forward/back dx,dy table for the LATERAL
axis. This is that table, for this axis.

THE EXPERIMENT, and it is pose.py's own:

    capture BEFORE -> press look_down once -> capture AFTER
    -> pose.offset(before, after) -> (dx, dy)

dy is px of vertical shift per press and its sign IS the sign, read straight
off. Repeated, both directions, character stationary -- NOTHING WALKS, the
left stick is never touched, and the only thing that moves is the camera.

RUN IT ANYWHERE THE VIEW HAS TEXTURE and the camera is NOT parked against a
stop: a stop clamps the press and reads as zero, which is indistinguishable
from a dead stream, so both are checked for before any number is believed
(§10.6: a run where everything degrades at once is the environment).

    .venv/bin/python -B tools/pitch_probe.py [--n 8]

Paste the two lines it prints into chain_walk.py. The dead-band moves to the
measured step on its own (pitch_dead_band), so the D >= S condition that stops
a bang-bang rule hunting holds at whatever the step turns out to be.
"""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The probe SENDS INPUT, so it may never run inside the offline suite.
if os.environ.get("BASEBALL_TEST_RUN"):
    sys.exit("pitch_probe sends stick input; BASEBALL_TEST_RUN is set. Refusing.")

import console_lock          # noqa: E402
import game_capture          # noqa: E402
import input_controller as ic  # noqa: E402
import pose                  # noqa: E402

# A press that moves the picture less than this is indistinguishable from a
# stop, a frozen stream, or the fit failing -- pose.py measured two stationary
# frames at exactly 0.0 px, so anything at all is movement, and this is a
# generous margin over the scene's own animation.
QUIET_PX = 3.0


def _shift(a, b):
    """(dx, dy) between two frames, or None when it cannot be measured."""
    got = pose.offset(a, b)
    return None if got is None else (float(got[0]), float(got[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8, help="presses per direction")
    args = ap.parse_args()

    with console_lock.held("pitch_probe"):
        grab = game_capture.grab

        # THE NULL CONTROL FIRST. Two captures with no press between them: if
        # this is not quiet, the scene is animating or the stream is stalled
        # and every number below would be that instead. A stalled stream reads
        # 0.0 and would look like a perfect control, so the frames must also
        # not be identical -- standing still measures 0.9-6.4 of frame delta,
        # and byte-identical frames are a dead picture (STAIRS_APPROACH.md).
        a = grab()
        time.sleep(0.4)
        b = grab()
        null = _shift(a, b)
        if null is None:
            sys.exit("the null control could not be measured: no texture here")
        if abs(null[1]) > QUIET_PX:
            sys.exit(f"the null control moved {null[1]:+.1f} px vertically; "
                     "something else is turning the camera")
        print(f"null control: dy {null[1]:+.2f} px, dx {null[0]:+.2f} px")

        rows = []
        for action in ("look_down", "look_up"):
            for trial in range(args.n):
                before = grab()
                ic.press(action, hold_seconds=ic.PITCH_STEP_SEC,
                         post_delay=0.30)
                after = grab()
                got = _shift(before, after)
                if got is None:
                    print(f"  {action} {trial}: UNMEASURABLE, skipped")
                    continue
                rows.append((action, got[1], got[0]))
                print(f"  {action} {trial}: dy {got[1]:+7.1f} px "
                      f"(dx {got[0]:+6.1f})")
            # Walk the camera back, so the second direction starts where the
            # first did and neither run drifts into a stop.
            other = "look_up" if action == "look_down" else "look_down"
            for _ in range(args.n):
                ic.press(other, hold_seconds=ic.PITCH_STEP_SEC, post_delay=0.20)

    downs = [dy for act, dy, _ in rows if act == "look_down"]
    ups = [dy for act, dy, _ in rows if act == "look_up"]
    if len(downs) < 3 or len(ups) < 3:
        sys.exit("too few measurable presses to conclude anything")

    quiet = [dy for dy in downs + ups if abs(dy) < QUIET_PX]
    if quiet:
        print(f"\\nWARNING: {len(quiet)} of {len(downs) + len(ups)} presses "
              "moved almost nothing -- the camera was probably against a stop "
              "for part of this run. Move to a mid pitch and re-run; a stop "
              "reads exactly like a dead stream.")

    md, mu = statistics.median(downs), statistics.median(ups)
    print(f"\\nlook_down: median dy {md:+.1f} px  "
          f"[{min(downs):+.1f} .. {max(downs):+.1f}]  n={len(downs)}")
    print(f"look_up:   median dy {mu:+.1f} px  "
          f"[{min(ups):+.1f} .. {max(ups):+.1f}]  n={len(ups)}")

    if (md > 0) == (mu > 0):
        sys.exit("\\nthe two directions moved the picture the SAME way. That is "
                 "not a pitch axis; do not set either constant from this run.")

    step = round((abs(md) + abs(mu)) / 2.0, 1)
    sign = 1 if md > 0 else -1
    print("\\nPaste into chain_walk.py:\\n")
    print(f"PITCH_STEP_PX = {step}")
    print(f"PITCH_DOWN_DY_SIGN = {sign}")
    print(f"\\n(the correction's `hypothesis` field predicts -1; this run "
          f"measured {sign}, so they "
          + ("AGREE" if sign == -1 else "DISAGREE -- the optics argument was "
             "backwards, and the shipped rule would have DOUBLED the error")
          + ".)")
    print(f"the dead-band becomes max(PITCH_TOL_MIN_PX, {step}) on its own.")


if __name__ == "__main__":
    main()
'''

# ------------------------------------ RULE 19: assert EVERY anchor, then write
for label, edits, src in (("chain_walk", edits_c, c), ("test_chain_walk", edits_t, t),
                          ("input_controller", edits_i, i), ("doorway_pitch", edits_d, d),
                          ("test_doorway_pitch", edits_td, td)):
    for a, b in edits:
        assert src.count(a) == 1, (label, a[:60], src.count(a))

assert "PITCH_CORRECT" not in c and "pitch" not in c, "chain_walk is untouched"
assert "PitchCorrection" not in t and "pitch=self.pitch" not in t
assert not os.path.exists(NEW), NEW
assert not os.path.exists(PROBE), PROBE
assert os.path.isdir(os.path.dirname(PROBE)), "tools/ must exist"
assert os.path.isdir(os.path.dirname(NEW)), "tests/rig/ must exist"
assert "return True\n" in i and "return homed" not in i
assert c.count("LATERAL_TOL_PX = pose.ALIGN_TOL_PX") == 1, "the mirror still exists"
assert c.count("FIX_MIN_INLIERS = 29") == 1
assert c.count("PX_PER_DEG = 19.7") == 1, "the yaw figure is untouched"
assert c.count("STALL_MAX = 4") == 1, "the escape test's fixture depends on it"

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)
for a, b in edits_i:
    i = i.replace(a, b)
for a, b in edits_d:
    d = d.replace(a, b)
for a, b in edits_td:
    td = td.replace(a, b)

# ------------------------------------------------- re-assert, parse, and write
ast.parse(c)
ast.parse(t)
ast.parse(i)
ast.parse(d)
ast.parse(NEW_FILE)
ast.parse(PROBE_FILE)
assert c.count("PITCH_CORRECT = False") == 1
assert c.count('PITCH_MODE = "report"') == 1
assert c.count("PITCH_STEP_PX = None") == 1
assert c.count("PITCH_DOWN_DY_SIGN = None") == 1
assert c.count("PITCH_SEC_PER_DEG = None") == 1
assert c.count("def pitch_dead_band():") == 1
assert c.count("def pitch_correction(dy, inliers, escaped=False):") == 1
assert c.count("pitch_row = pitch_correction(") == 1
assert c.count('pitch(pitch_row["action"], pitch_row["seconds"])') == 1
assert c.count('**({"pitch": pitch_row} if pitch_row else {}),') == 1
assert c.count("back=None, pitch=None):") == 1
assert c.count("PITCH_ACTIONS = (") == 1
assert c.count("PX_PER_DEG = 19.7") == 1
assert t.count("class PitchCorrection(unittest.TestCase):") == 1
assert t.count("pitch=self.pitch") == 1
assert t.count("def pitch(self, action, secs):") == 1
assert t.count("def test_the_pitch_correction_reaches_press_on_the_STICK_axis") == 1
assert t.count("def test_the_SHIPPED_pitch_flag_reaches_press_NOT_AT_ALL") == 1
assert t.count("def test_the_escape_presses_CROSS_and_sidesteps_on_the_same_axis") == 1
assert i.count("return homed") == 1 and i.count("homed = home_pitch(") == 1
assert i.count("branching on a constant") == 1, "the history stays recorded"

open(C, "w").write(c)
open(T, "w").write(t)
open(I, "w").write(i)
open(D, "w").write(d)
open(TD, "w").write(td)
open(NEW, "w").write(NEW_FILE)
open(PROBE, "w").write(PROBE_FILE)
print("patch57 applied to", ROOT)
