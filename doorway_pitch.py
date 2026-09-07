"""Aim the camera PITCH at the bar doorway from where leg 1 lands.

WHERE THE NUMBER COMES FROM. STAIRS_APPROACH.md, "The pose that works",
measured live on 2026-09-06 with the user watching the stream:

    pitch      home DOWN to the floor stop, then 22 presses UP

From that pose (plus a bearing of ~3.7-4.5, commanded with tolerance 0.5 --
NOT this module's business, see below) five pushes of speed 0.35 for 0.80s
descend the stairs and reach the doorway.

WHY IT IS COUNTED FROM THE FLOOR. Pitch has no HUD readout, so it is homed
like a stepper: drive to an endstop, count back. Only the DOWN stop is
detectable -- home_pitch reads 24.18 against a 1.29 noise floor going down,
while going up "gave a flat 6-10 delta for all 14 presses and never settled"
(input_controller.level_pitch docstring). The 22 was verified two independent
ways that agree: 14 presses down from the ceiling and 22 up from the floor
land on the same aim, and 14 + 22 = 36, the full ceiling-to-floor range
measured the same day.

THREE PITCH NUMBERS IN THIS PROJECT CONTRADICT EACH OTHER, and this module
changes NONE of them (STAIRS_APPROACH.md, "THREE NUMBERS ABOUT PITCH
CONTRADICT EACH OTHER"):

    level_pitch docstring    4 positions across the whole range
    PITCH_STEPS_FROM_BOTTOM  14 presses from the floor stop to level
    measured 2026-09-06      36 presses ceiling-to-floor, 22 floor-to-doorway

At least two are wrong. This module deliberately does NOT route through
level_pitch, for two reasons its own docstring supplies: it ALWAYS returns
True ("any caller branching on the result was branching on a constant"), and
when homing fails it presses down four more times and counts up anyway. That
is fine for a coarse "roughly level" that tolerates a press either way; it is
not fine here, where the count was measured from a CONFIRMED floor stop.

WHY A FAILED HOME IS A REFUSAL, NOT A BEST EFFORT. home_pitch returns None
only after PITCH_MAX_PRESSES presses without two consecutive quiet frames --
its docstring: "the camera is not responding and the caller must not assume a
known pitch". Twenty-two presses from an UNKNOWN pitch is a different,
unmeasured pose, and a wrong pitch depresses identify() scores on every frame
of every following leg while looking like "the localiser is marginal here"
(STAIRS_APPROACH.md, "PITCH IS UNCONTROLLED IN PRODUCTION"). Refusing loudly
is cheaper than a confident wrong pose.

BEARING IS NOT TOUCHED HERE. The doorway bearing (~3.7-4.5) must be commanded
with turn tolerance 0.5, not the 4.0 default -- with 4.0, "asking for 1.0 deg
from 2.7 sent NOTHING" -- and that is aimed by the caller through the turning
machinery, not by this module. Pitch and yaw are separate axes with separate
instruments; this file owns exactly one of them.
"""

# The measured count. Source: STAIRS_APPROACH.md (2026-09-06), "home DOWN to
# the floor stop, then 22 presses UP". A MEASUREMENT is a record, not a
# tunable (CLAUDE.md section 6): change it only with a new live measurement,
# and note that it will then disagree with PITCH_STEPS_FROM_BOTTOM = 14 and
# level_pitch's "4 positions" in some new way -- those two already disagree
# with it and with each other, and none of the three is altered by this file.
#
# THIS DOES NOT COLLIDE WITH input_controller.PITCH_MAX_PRESSES (14). That
# constant bounds home_pitch's HOMING loop -- how many look_down presses it
# will try before deciding the camera is not responding -- and is not a limit
# on a fixed count issued AFTER homing. The 22 below is that fixed count; it
# runs only once home_pitch has returned a number.
DOORWAY_PRESSES_FROM_FLOOR = 22

# COPIED from the look_up press inside input_controller.level_pitch (a literal
# there, 0.30, so it cannot be imported). home_pitch uses the same 0.30. If
# that literal ever changes, this copy must follow it by hand.
LOOK_UP_POST_DELAY = 0.30


def aim_doorway_pitch(capture, log=print):
    """Home the pitch to the floor stop, then press look_up exactly
    DOORWAY_PRESSES_FROM_FLOOR times. Returns True when both halves ran.

    Returns False -- and presses NOTHING -- when home_pitch could not confirm
    the floor stop, because the 22 is only meaningful from that stop (see the
    module docstring). The caller must not assume a known pitch after False.

    `capture` is the frame source home_pitch measures its endstop against.
    Bearing is not read or changed here.
    """
    # Lazy on purpose: input_controller imports pyautogui at module top, which
    # is what makes importing it cost something (and what the offline test
    # fakes out entirely). Read PITCH_STEP_SEC through the module at call
    # time rather than copying it, so a re-measured press length is picked
    # up here without a second constant to hand-sync.
    import input_controller as ic

    used = ic.home_pitch(capture, "look_down", log=log)
    if used is None:
        # Say WHY, on the path that does nothing (CLAUDE.md 10.1: a no-op
        # that writes nothing is indistinguishable from success).
        if log:
            log("      doorway pitch: REFUSING -- home_pitch did not settle at "
                "the floor stop (None after its homing limit), so the pitch "
                f"is unknown and {DOORWAY_PRESSES_FROM_FLOOR} presses up from "
                "an unknown pitch is an unmeasured pose. Nothing pressed.")
        return False
    for _ in range(DOORWAY_PRESSES_FROM_FLOOR):
        ic.press("look_up", hold_seconds=ic.PITCH_STEP_SEC,
                 post_delay=LOOK_UP_POST_DELAY)
    if log:
        log(f"      doorway pitch: homed to the floor stop in {used} "
            f"press(es), then +{DOORWAY_PRESSES_FROM_FLOOR} up")
    return True
