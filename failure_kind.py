"""Classify WHY a route step failed, from the frame it failed on.

WHY THIS EXISTS. Seven consecutive well-motivated navigation changes measured
flat. The likely reason is not that all seven did nothing — it is that route
arrival averages THREE different failures, so a change that eliminates one
class moves the overall rate by a third of that class, which at n=8-10 is
invisible.

The three classes are separable with signals already being captured. Measured
over the eight archived frames in overnight/failframes/:

    kp     identify              bearing   class
    -------------------------------------------------------------------
    9-11   None (0-1 matches)    98-105    WEDGED    against the bar counter
    744    None (57/1.24)        105.7     OVERSHOT  detailed but unplaced
    1346   None (105/1.54)       101.8     OVERSHOT  out in an unmapped hallway
    1500   portrait_room 480     5.8       REGRESSED back at an earlier node
    1500   portrait_room 498     30.7      REGRESSED

Report arrival BY CLASS, never just overall, or the next seven changes will
also look flat.

There is a FIFTH class, UNMEASURABLE, and it is not a failure at all: a frozen
picture produces a frame that looks exactly like one of the four and is
evidence for none of them. See its definition below.
"""

WEDGED = "wedged"          # pressed into geometry; nothing to match
OVERSHOT = "overshot"      # rich frame, but nowhere the map knows
REGRESSED = "regressed"    # confidently at a node EARLIER in the route
UNPLACED = "unplaced"      # recognised, but not on this route at all

# NOT A FAILURE. The picture was not updating, so the frame is a photograph of
# a dead stream and says nothing whatever about where the character is.
#
# WHY IT HAS TO BE ITS OWN CLASS. Reproduced end to end 2026-09-05 with a
# capture returning identical pixels: follow_verified reported arrived=False
# having issued ZERO stick pushes, and the failure came back OVERSHOT — "rich
# frame, off the mapped route" — because a frozen frame of a real room is
# exactly a rich frame the localiser cannot place. Every one of the four real
# classes is a statement about POSITION, and a frozen capture supports none of
# them. Emitting the most plausible one is a confident wrong answer, and it
# lands in `failures_by_kind`, which is the number the queued A/Bs are scored
# on.
UNMEASURABLE = "unmeasurable"

# The classes that are actually claims about where the character is. Callers
# separating "this trial failed" from "this trial could not be measured" should
# test against this rather than re-listing the names and drifting out of step.
REAL_FAILURES = (WEDGED, OVERSHOT, REGRESSED, UNPLACED)

# Between the two measured populations: wedged frames hold 9-11 keypoints, the
# next lowest non-wedged frame holds 744. Anywhere in that gap works; 50 keeps
# a wide margin on both sides rather than hugging either.
WEDGED_MAX_KEYPOINTS = 50


def classify(img, target, route, identify=None, keypoints=None, live=None):
    """(kind, detail) for a frame on which `target` could not be verified.

    `route` is the ordered node list, so "earlier than target" is decidable.
    identify/keypoints are injectable so this is testable without the console.

    `live` is the caller's verdict on whether the STREAM was updating when this
    frame was taken — a bool, or a callable returning one. It is a parameter and
    not something measured here because liveness needs TWO captures separated in
    time, and by the time a frame reaches this function there is only one.

    THREE STATES, deliberately:

        live=False   the picture was proven dead -> UNMEASURABLE, always
        live=True    the picture was proven live -> classify normally
        live=None    NOBODY CHECKED -> classify normally, exactly as before

    None is not the same as True and must never be spelled `bool(live)`: an
    unchecked frame is the historic behaviour and the archived corpus is
    classified that way, but it is not evidence the stream was alive.
    """
    if live is not None:
        alive = live() if callable(live) else bool(live)
        if not alive:
            return UNMEASURABLE, ("the picture was not updating — this frame "
                                  "shows a frozen stream, not a position")

    if identify is None or keypoints is None:
        import places
        identify = identify or places.identify
        keypoints = keypoints or places.keypoints

    _, desc = keypoints(img)
    n = 0 if desc is None else len(desc)
    room, score, margin = identify(img)

    if room is not None:
        # Recognised somewhere. Is it BEHIND us on the route?
        if room in route and target in route:
            if route.index(room) < route.index(target):
                return REGRESSED, f"at {room} ({score:.0f}/{margin:.2f}), " \
                                  f"earlier than {target}"
            return UNPLACED, f"at {room}, not earlier than {target}"
        return UNPLACED, f"at {room}, which is not on this route"

    # Not recognised. Featureless means jammed against something; detailed
    # means genuinely somewhere the map does not know.
    if n <= WEDGED_MAX_KEYPOINTS:
        return WEDGED, f"{n} keypoints — pressed against geometry"
    return OVERSHOT, f"{n} keypoints but unplaced — off the mapped route"


def tally(kinds):
    """Count classes, for reporting a run by signature rather than in total."""
    out = {}
    for k in kinds:
        out[k] = out.get(k, 0) + 1
    return out
