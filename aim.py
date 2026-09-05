"""Turn the camera so the reticle lands on something. Trigonometry, done right.

THE MISTAKE THIS FIXES
----------------------
The obvious formula is linear: an object a fraction f from the centre of the
screen is f * FOV degrees off axis. That is WRONG for a perspective camera, and
wrong in a way that matters here — it is accurate near the centre and
increasingly optimistic toward the edges, which is precisely where a landmark
sits when it needs the largest correction. Aiming at something near the frame
edge under-turned every time, and the reticle never quite landed.

A perspective projection puts a point at angle `a` from the axis at screen
offset proportional to tan(a). So the inverse is:

    offset = (x - 0.5)                     fraction of frame width from centre
    angle  = atan( 2 * offset * tan(FOV/2) )

At the centre the two agree. At the frame edge with a 102-degree FOV, linear
says 51 degrees and the correct answer is 51 too — but at the QUARTER point
linear says 25.5 and the truth is 31.4, a six-degree error, which is the
difference between the reticle landing on a character and beside her.

FOV is a calibration knob, not a constant of the universe: measure it with
`measure_fov` rather than trusting the default.
"""

import json
import math
import os

FOV_FILE = "camera_fov.json"
DEFAULT_FOV = 102.0


def load_fov(path=FOV_FILE, default=DEFAULT_FOV):
    if os.path.exists(path):
        try:
            return float(json.load(open(path))["fov_degrees"])
        except Exception:
            pass
    return default


def save_fov(fov, path=FOV_FILE, note=""):
    json.dump({"fov_degrees": round(float(fov), 2), "note": note},
              open(path, "w"), indent=1)


def angle_for_offset(offset, fov=None):
    """Degrees to turn so a thing at this screen offset ends up centred.

    `offset` is (x - 0.5) as a fraction of frame width: negative is left of
    centre, positive right. The result has the same sign convention as a
    compass turn, so add it to the current heading.
    """
    fov = load_fov() if fov is None else fov
    half = math.radians(fov / 2.0)
    return math.degrees(math.atan(2.0 * offset * math.tan(half)))


def offset_for_angle(angle, fov=None):
    """The inverse: where on screen a thing this many degrees off axis appears."""
    fov = load_fov() if fov is None else fov
    half = math.radians(fov / 2.0)
    return math.tan(math.radians(angle)) / (2.0 * math.tan(half))


def measure_fov(observations):
    """Estimate FOV from (heading, screen_x) pairs of one FIXED object.

    Each pair says: the object sits `heading - bearing` degrees off axis and
    appears at offset `x - 0.5`. Solving tan for the half-angle gives FOV. Uses
    the median, because a template's idea of an object's centre wobbles.
    """
    pts = [(h, x - 0.5) for h, x in observations]
    if len(pts) < 2:
        return None
    ests = []
    for (h1, o1), (h2, o2) in zip(pts, pts[1:]):
        dh = (h2 - h1 + 540) % 360 - 180
        do = o2 - o1
        if abs(dh) < 1.0 or abs(do) < 0.02:
            continue
        # local linearisation is fine for small steps: dOffset/dAngle at the
        # centre is 1 / (2 tan(FOV/2)) per radian
        per_deg = do / -dh
        if per_deg <= 0:
            continue
        half = math.atan(1.0 / (2.0 * per_deg * 180.0 / math.pi))
        ests.append(math.degrees(half) * 2.0)
    if not ests:
        return None
    ests.sort()
    return ests[len(ests) // 2]


ASPECT = 16.0 / 9.0


def vertical_fov(fov=None):
    """Vertical field of view implied by the horizontal one and the aspect."""
    fov = load_fov() if fov is None else fov
    half_h = math.radians(fov / 2.0)
    return math.degrees(2.0 * math.atan(math.tan(half_h) / ASPECT))


def pitch_for_offset(offset_y, fov=None):
    """Degrees to pitch so a thing this far below/above centre ends up centred.

    Same perspective relation as the horizontal case, but against the VERTICAL
    field of view. Positive means the target is below centre and the camera must
    look down.

    This axis was ignored entirely until it was pointed out: the matcher
    computed a vertical position and threw it away, so aiming was yaw-only. On a
    frame where the reticle genuinely sits on the dealer, she measures y=0.596 —
    about a tenth of the frame below centre, roughly 7 degrees. Centring only in
    x therefore leaves the reticle consistently above her.
    """
    half_v = math.radians(vertical_fov(fov) / 2.0)
    return math.degrees(math.atan(2.0 * offset_y * math.tan(half_v)))


def turn_by(degrees, send, sleep, max_sec=0.6):
    """Turn a RELATIVE amount. No compass involved.

    Aiming does not need an absolute bearing. It needs to rotate by a computed
    angle and then look again — and the thing that verifies the result is the
    template, not the compass. Removing the compass from this path matters
    because it fails exactly where aiming is hardest: pointed at a light source,
    the strip washes out and the bearing becomes unreadable, which used to
    abandon the turn silently and report "turned +0.0 deg".

    The turn curve was measured to a few degrees open-loop, which is well inside
    what one iteration of a closed loop needs.
    """
    import turn_curve as tc
    mag, secs = tc.plan_turn(abs(degrees), max_sec=max_sec)
    if mag == 0.0:
        return False
    signed = mag if degrees > 0 else -mag
    send([f"right_x {int(max(-32768, min(32767, round(signed * 32767))))}",
          "right_y 0", "left_x 0", "left_y 0"])
    sleep(secs)
    send(["right_x 0"])
    sleep(0.25)
    return True
