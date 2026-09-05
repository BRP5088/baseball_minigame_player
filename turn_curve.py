"""Convert a desired turn rate into a stick magnitude, from measurement.

MEASURED 2026-08-28 (two trials per point, right stick, 0.30s holds):

    stick  0.20  0.30  0.40  0.50  0.60  0.70  0.80  0.90  1.00
    deg/s   0.4   1.6   7.5  16.2  22.5  37.3  58.2  74.8 197.7

WHY THIS MATTERS MORE THAN IT LOOKS
-----------------------------------
The response spans 46x across the stick and is nowhere near linear, and every
correction this project has sent assumed it was. Three consequences, all
observed:

  * Below ~0.35 the stick is effectively DEAD (0.4 deg/s at 0.20). Small
    corrections did nothing while appearing to be sent.
  * 0.55 gives ~16 deg/s, not the ~60 assumed from keyboard calibration —
    so every correction was about 4x too weak, which is every underturn.
  * Full deflection is a cliff: 74.8 deg/s at 0.90 becomes 197.7 at 1.00.
    A keyboard key is ALWAYS 1.0, so keyboard turning lived at the top of the
    curve and analog corrections lived at the bottom. That is why the two felt
    like different controls — they were, at opposite ends of one steep curve.

Interpolated rather than fitted: no simple curve matched all nine points, and a
fit that is wrong at the ends is worse than a table that is right at the ones
that were measured.
"""

# WHAT THESE NUMBERS ACTUALLY ARE — read this before using them.
#
# Each entry is the AVERAGE RATE OVER A 0.30s HOLD, so every one includes one
# acceleration transient and one deceleration transient. It is NOT the
# steady-state turn rate, and the two differ a lot at the top of the range:
# mid-hold sampling puts the steady rate at full stick near 220 deg/s against
# the 197.7 recorded here.
#
# That distinction cost a wrong conclusion on 2026-09-03 — "the table is 10%
# low, so anything doing rate x duration inherits the error". It is not. The
# table is right for what it measures, and an independent check at a DIFFERENT
# hold length (1.0s, n=6 per point, see VERIFIED_1S) lands within ~5% across
# the usable band:
#
#     mag 0.90   table 74.8   measured 72.01   +3.9%
#     mag 0.70   table 37.3   measured 35.49   +5.1%
#     mag 1.00   table 197.7  measured 209.45  -5.6%   (above USABLE_MAX)
#
# So: do not "correct" these constants from a steady-state measurement. If a
# caller ever needs a true steady rate, measure one and add it as its own
# table rather than editing this one.
MEASURED = [
    (0.20, 0.4), (0.30, 1.6), (0.40, 7.5), (0.50, 16.2), (0.60, 22.5),
    (0.70, 37.3), (0.80, 58.2), (0.90, 74.8), (1.00, 197.7),
]

DEAD_BELOW = 0.35        # below this the stick does not meaningfully turn
USABLE_MAX = 0.90        # above this the response triples; unusable for control

# Independent check, 2026-09-03: six identical 1.0s open-loop camera turns per
# magnitude, live. Kept separate from MEASURED because it is a different hold
# length, and averaging the two would destroy both.
#
# The reason USABLE_MAX exists, now measured rather than reasoned:
#
#     mag 1.00   spread 17.28 deg over a 209 deg turn   8.3% of the turn
#     mag 0.90   spread  3.61 deg over a  72 deg turn   5.0%
#     mag 0.70   spread  2.90 deg over a  35 deg turn   8.2%
#
# 0.90 is a genuine sweet spot — 4.8x less absolute drift than full stick, and
# better RELATIVE precision than either neighbour. Turning harder than this
# does not just overshoot, it is less repeatable.
VERIFIED_1S = [(0.70, 35.49), (0.90, 72.01), (1.00, 209.45)]


def rate_for(mag):
    """Degrees per second at this stick magnitude."""
    m = abs(mag)
    if m <= MEASURED[0][0]:
        return MEASURED[0][1]
    for (m0, r0), (m1, r1) in zip(MEASURED, MEASURED[1:]):
        if m <= m1:
            f = (m - m0) / (m1 - m0)
            return r0 + f * (r1 - r0)
    return MEASURED[-1][1]


def mag_for(deg_per_sec):
    """Stick magnitude that turns at this rate, clamped to the usable band.

    Capped at USABLE_MAX deliberately: the jump from 0.90 to 1.00 nearly
    triples the rate, so anything asking for more than ~75 deg/s should turn
    for LONGER rather than harder, or it will wildly overshoot.
    """
    want = abs(deg_per_sec)
    if want <= MEASURED[0][1]:
        return 0.0
    for (m0, r0), (m1, r1) in zip(MEASURED, MEASURED[1:]):
        if want <= r1:
            f = (want - r0) / (r1 - r0) if r1 > r0 else 0.0
            m = m0 + f * (m1 - m0)
            return min(USABLE_MAX, max(DEAD_BELOW, m))
    return USABLE_MAX


def plan_turn(degrees, max_sec=0.6):
    """(magnitude, seconds) to turn `degrees`. Sign carried by the caller.

    Prefers a moderate stick held longer over a hard stick held briefly: the
    curve is far flatter — and therefore far more predictable — below 0.9.
    """
    want = abs(degrees)
    if want < 0.5:
        return 0.0, 0.0
    for secs in (0.15, 0.25, 0.40, max_sec):
        rate = want / secs
        if rate <= 74.8:                     # inside the measured, usable band
            return mag_for(rate), secs
    return USABLE_MAX, want / 74.8
