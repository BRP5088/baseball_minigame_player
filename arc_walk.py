"""Walk and turn at the same time, tracing an arc instead of a dog-leg.

WHY
---
A recorded human walk turns WHILE moving: in demo3 the heading slides
88 -> 108 -> 139 -> 150 -> 203 -> 232 -> 263 with the picture changing
throughout — one continuous arc taking about six seconds.

Replaying that as stop / turn / walk / stop / turn / walk visits the same
headings but traces a different SHAPE. It cuts every corner, and in a corridor
that means walking into the inside wall. Every attempt to reproduce this route
by sequential legs failed on the first turn for that reason.

The controls allow both at once — left stick to move, right stick to look — so
the arc can be reproduced directly.
"""

import time

import input_controller as ic

SLICE_SEC = 0.10          # granularity of the blend

# Turning while walking is LESS effective than turning on the spot. Measured
# 2026-08-27 with 1.0s arcs (short enough that the measured delta cannot wrap
# past 180 and flip sign — two earlier readings did exactly that and came back
# negative):
#
#     hold fraction   achieved / predicted
#         0.15               0.88
#         0.30               0.83
#         0.50               0.83
#         0.70               0.89
#         0.90               1.22   <- excluded
#
# 0.90 is excluded deliberately: at that hold the walk key gets under a tenth
# of each slice, so it stops being an arc and becomes a turn with a limp. The
# usable band is capped below it.
ARC_EFFICIENCY = 0.86
MAX_HOLD_FRACTION = 0.80


def arc(heading_from, heading_to, seconds, deg_per_sec, log=None):
    """Walk forward for `seconds` while turning from one heading to the other.

    deg_per_sec comes from turn_calibrated's measured response, so the turn
    keys are held for the fraction of each slice that produces the required
    rotation, rather than guessed at.
    """
    delta = (heading_to - heading_from + 540) % 360 - 180
    if seconds <= 0:
        return
    rate = delta / seconds                      # degrees per second required
    turn_key = ic.KEYMAP["look_right" if rate > 0 else "look_left"]
    walk_key = ic.KEYMAP["walk_up"]

    slices = max(1, int(round(seconds / SLICE_SEC)))
    per = seconds / slices
    # Fraction of each slice the turn key must be held to achieve `rate`.
    if deg_per_sec:
        hold = abs(rate) * per / (deg_per_sec * ARC_EFFICIENCY)
    else:
        hold = 0.0
    hold = min(hold, per * MAX_HOLD_FRACTION)
    if log:
        log(f"    arc {heading_from:.0f} -> {heading_to:.0f} over {seconds:.1f}s "
            f"({rate:+.0f} deg/s, turn held {hold / per:.0%} of each slice)")

    for _ in range(slices):
        if hold > 0.004:
            ic._bg_hold_keys([walk_key, turn_key], hold)
            rest = per - hold
            if rest > 0.004:
                ic._bg_hold_keys([walk_key], rest)
        else:
            ic._bg_hold_keys([walk_key], per)
