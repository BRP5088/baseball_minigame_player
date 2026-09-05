"""Calibrate camera pitch against an absolute reference: the endstop.

THE IDEA (suggested by the user, 2026-08-28)
--------------------------------------------
    "Couldn't you measure pitch by hitting the max by looking up, then moving
     it down N degrees? Then you know exactly what angle it is."

Yes. Pitch has hard limits at the top and bottom of its travel, and driving
into one is detectable — the view stops changing. From that stop, every step is
a known increment, so counting steps gives an absolute angle. No scene content
required, which matters because everything scene-based has failed: brightness
proxies track the room rather than the camera, and structure matching cannot
separate a correct match from a wrong one in a building full of repeated
doorframes.

WHAT THIS MEASURES
------------------
How far the view moves, in thumbnail pixels, per pitch step. That converts the
vertical offset between two views into a number of steps, so a pitch error can
be corrected exactly rather than nudged at a guessed gain.

It only moves the CAMERA. The character does not walk, so a bad calibration
costs a re-run and nothing else.
"""

import time

import analog_replay as ar
import structure_match as sm

STEP_STICK = 0.85          # right_y magnitude while driving pitch
STEP_SEC = 0.10            # one "step" of pitch
SETTLE = 0.30
ENDSTOP_TRIES = 14         # presses to be sure the limit is reached
ENDSTOP_QUIET_PX = 2       # view moving less than this means we are at the stop
STEPS_TO_MEASURE = 10

# MEASURED 2026-08-28 on the second-monitor setup.
# Driving to the UP endstop settled after 9 presses (view stopped moving), then
# ten steps down gave consistent negative shifts: -12 -12 -6 -12 -9 -9 -12 -9
# -9 -12, i.e. 10.0 thumbnail px per step over 9 usable measurements.
#
# The spread is mostly QUANTISATION, not noise: structure_match searches
# vertical shift in steps of VERT_STEP=3, so every reading is a multiple of 3
# and a true 10px shift reads as 9 or 12. Treat this as 10 +- 1.5, which is
# fine for converting an error into a step count but not for finer work.
PX_PER_PITCH_STEP = 10.0


def _pitch(stick, secs=STEP_SEC):
    """Drive pitch. Negative stick looks up, positive looks down."""
    ar.send([f"right_y {ar.to_axis(stick)}",
             "right_x 0", "left_x 0", "left_y 0"])
    time.sleep(secs)
    ar.send(["right_y 0"])
    time.sleep(SETTLE)


def drive_to_endstop(capture, direction=-1.0, log=print):
    """Hold pitch against its limit until the view stops changing.

    Returns the number of presses that still produced movement — useful only
    as a sanity check that the camera was moving at all.
    """
    moved = 0
    prev = capture()
    for i in range(ENDSTOP_TRIES):
        _pitch(direction * STEP_STICK, STEP_SEC * 2)
        now = capture()
        _, dy, score = sm.offset(now, prev)
        prev = now
        if abs(dy) <= ENDSTOP_QUIET_PX:
            log(f"    endstop reached after {i + 1} presses (dy={dy})")
            return moved
        moved += 1
    log(f"    never settled after {ENDSTOP_TRIES} presses — camera may be blocked")
    return moved


def calibrate(capture, log=print):
    """Return pixels-of-view-movement per pitch step, measured from the stop."""
    log("  driving pitch to the UP endstop")
    drive_to_endstop(capture, direction=-1.0, log=log)

    log(f"  stepping down {STEPS_TO_MEASURE} times, measuring each")
    shifts = []
    prev = capture()
    for i in range(STEPS_TO_MEASURE):
        _pitch(+STEP_STICK)
        now = capture()
        _, dy, score = sm.offset(now, prev)
        prev = now
        shifts.append((i + 1, dy, score))
        log(f"    step {i + 1:2}: dy={dy:+3} score={score:.2f}")

    usable = [dy for _, dy, sc in shifts if sc > 0.3 and dy != 0]
    ar.clear()
    if not usable:
        log("  no usable measurements — every step scored too low to trust")
        return None
    per_step = sum(abs(d) for d in usable) / len(usable)
    log(f"\n  {len(usable)}/{len(shifts)} steps usable, "
        f"{per_step:.2f} thumbnail px per pitch step")
    return per_step
