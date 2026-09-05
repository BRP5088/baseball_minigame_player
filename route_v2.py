"""The route from spawn to the bar, walked and confirmed on 2026-08-27.

Every leg was verified by looking at the frame at the end of it, not by a
detector agreeing with a script.

WHY THIS REPLACES route_verified.TO_BAR
---------------------------------------
The old route stored leg 3 as bearing 285. That is where the bar SIGNAGE is
visible from, not where the door is, and walking 285 does not enter the bar.
The error came from reading a landmark's bearing off the HUD compass scale
(~3.2 px/deg) instead of the screen scale (18.7 px/deg) — a 5.8x overstatement
that put the L&B doorway at 319 degrees when it was at 359, and drove the
character into a wall twice. See turn_calibrated.bearing_of_screen_x.

HOW TO WRITE A LEG — facing, AND the turn
-----------------------------------------
Every leg records BOTH the heading you end up facing and the turn that gets you
there from the previous leg. Writing only one of them is what broke the old
route: it stored "0.7s at 66", and 66 was read back as a compass heading when
it was a TURN from whatever the character happened to be facing. Applied as a
heading it points somewhere else entirely, and the walk ends at a coat rack.

A bare number is ambiguous between the two, and the ambiguity is invisible
until a run fails. So: `face` is absolute, `turn_from_prev` is the delta, and
they must agree. If they ever disagree, the note is wrong and neither should be
trusted.

Bearings are ABSOLUTE compass headings. Face the bearing, then walk forward;
walking never changes the heading (confirmed again here: it held at 269.4 and
then 0.3 for entire legs).
"""

# face            = absolute compass heading to end up on
# turn_from_prev  = degrees to turn from the PREVIOUS leg's facing (+ = right)
# The spawn heading varies, so leg 1's turn is computed at run time, not stored.
TO_BAR = [
    dict(face=270.0, turn_from_prev=None, kind="until_blocked", secs=5.0,
         ends="jammed against the office door — dark, panelled, nothing else"),
    dict(face=8.0, turn_from_prev=+98.0, kind="timed", secs=1.8,
         ends="outside on the steps; LITTLE & BIG facade and L&B sign fill the view"),
    dict(face=358.0, turn_from_prev=-10.0, kind="until_blocked", secs=5.0,
         ends="through the L&B doorway, interior with portraits and a rug"),
    dict(face=330.0, turn_from_prev=-28.0, kind="until_blocked", secs=4.0,
         ends="INSIDE THE BAR: menu board, counter and stools, barman, dartboard"),
]


def check_consistency():
    """Every turn_from_prev must agree with the two facings it sits between.

    Cheap, and it is the exact error that cost this route a rerun: a number
    that is a turn in one place and a heading in another looks fine until a
    walk ends somewhere unexpected.
    """
    bad = []
    for prev, leg in zip(TO_BAR, TO_BAR[1:]):
        if leg["turn_from_prev"] is None:
            continue
        implied = (prev["face"] + leg["turn_from_prev"]) % 360
        if abs((implied - leg["face"] + 540) % 360 - 180) > 0.5:
            bad.append(f"{prev['face']} + {leg['turn_from_prev']:+} = {implied}, "
                       f"but the leg says it faces {leg['face']}")
    return bad

# Landmarks that confirm position, for a human reading a frame:
#   leg 2 end  — "LITTLE & BIG" oval sign, "L & B" over the doorway
#   between 3 and 4, facing 285 — "FETA MUG 4c" and "BRIE SHOT 2c" on the wall,
#                                 and a sandwich board about grabbing a shot
#   leg 4 end  — the menu board, the bar counter, the barman

SPAWN_NOTE = "spawn heading varies 57-91 across resets; read it, never assume"

# Timings observed on the confirmed run. until_blocked legs stop early when the
# frame stops changing, so these are upper bounds, not targets.
OBSERVED = {"leg1_blocked_at": 2.4, "leg2": 1.8, "leg3_blocked_at": 5.0,
            "leg4_blocked_at": 4.0}


# --- Still unfound: the Baseball Cards table -------------------------------
# Reaching the BAR is now reliable. Finding the table inside it is not.
#
# The old note's "0.7s at 66 degrees" does NOT transfer: it was recorded from a
# different spot on the bar floor, and walking 66 from where leg 4 ends jams
# into a wall with a portrait and a coat rack. Bearings only mean something
# paired with a position, and the old route never recorded the position.
#
# What IS mapped inside, from where leg 4 ends:
#     330  the bar counter, stools, barman, menu board
#     169  back out through the entrance door (potted plant beside it)
#      90  a corridor of portraits and a rug, wall sconce, door on the right
#      66  a dead end — wall, portrait, coat rack
#
# So the table is not on any of those four headings from that spot. The next
# thing to try is walking INTO the room at 330 (past the counter) and scanning
# again from there, rather than scanning further from the doorway.


# --- WHY THE AUTOMATED RUN DOES NOT YET REPRODUCE THE MANUAL ONE -----------
#
# Walked by hand, leg by leg, this route reaches the bar. Run end to end by
# walk_route_v2 it lands inside the barman, and leg-4 scene scores come out at
# 0.19-0.36 against a reference of 0.84+ for the same place.
#
# The cause is NOT leg 4's duration. Tried 2.0/2.5/3.0s: 0.19, 0.36, 0.28. It
# is leg 3, which is declared "until_blocked 5.0s" and NEVER BLOCKS — its frame
# deltas stay at 18-42 for the whole five seconds on every run, so it always
# walks the full distance and ends somewhere slightly different each time.
#
# DETECTING "BLOCKED" IS THE OPEN PROBLEM, and three approaches have now failed:
#
#   1. absolute frame delta < 2.0        — scene-dependent; a bright street
#                                          moves more pixels than a dark room
#   2. delta < 18% of this leg's peak    — jammed against a door the deltas
#                                          PLATEAU at ~3.5 and never dip
#   3. similarity to the frame 1.5s ago  — unreliable on near-uniform dark
#                                          frames, where normalised correlation
#                                          is mostly noise (0.87-0.91 while
#                                          genuinely stuck against a door)
#
# The reason all three fail is ambient motion: this game has rain, idle
# animation and a bobbing camera, so the frame NEVER stops changing. Any
# "has the picture settled" test is measuring the wrong thing.
#
# What would actually work is a measure of TRANSLATION rather than change.
# Optical flow was rejected earlier in this project for steering (turning
# scored higher than walking, because the camera orbits), but the failure mode
# there was rotation — and heading is now known exactly from the compass and
# holds constant during a walk. Flow with the rotation component removed is the
# obvious next thing to try, and it has not been tried under those conditions.
