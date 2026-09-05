"""Walk toward a STATIC landmark by keeping it centred in view.

This is the first closed-loop POSITION control in the project. Everything
before it servoed heading — which the compass gives exactly — while distance
ran open loop, so runs drifted and the same route ended in different rooms.

A fixed object fixes that, because where it appears on screen says which way to
go. The two used here are the jukebox and the dealer's table, both confirmed
static by the person who plays this. That distinction is the whole point:
Wanda Fuller looked like a checkpoint and walks around, and the compass-strip
markers looked world-fixed and ride the camera.

SWEEP, THEN CENTRE, THEN WALK. The sweep is what makes this robust to arriving
from the wrong angle — the landmark does not have to be in front to begin with,
only somewhere in the room.
"""

import time

import analog_replay as ar
import compass
import jukebox
import turn_curve as tc

SWEEP_STEP = 40.0
SWEEP_COUNT = 9
CENTRE_TOLERANCE = 0.06     # fraction of frame width
FOV_DEGREES = 70.0          # roughly, for converting screen offset to a turn


def _turn_by(deg):
    if abs(deg) < 1.0:
        return
    mag, secs = tc.plan_turn(deg)
    if mag == 0.0:
        return
    ar.send([f"right_x {ar.to_axis(mag if deg > 0 else -mag)}",
             "right_y 0", "left_x 0", "left_y 0"])
    time.sleep(secs)
    ar.send(["right_x 0"])
    time.sleep(0.28)


def sweep_for(template_dir, threshold, log=print):
    """Rotate until the landmark is seen. Returns (score, x, heading) or None."""
    best = None
    for i in range(SWEEP_COUNT):
        img = compass.fast_capture()
        score, x, scale = jukebox.find(img, template_dir)
        h = compass.read_bearing(img)
        if best is None or score > best[0]:
            best = (score, x, h, scale)
        log(f"      sweep {i}: heading {'--' if h is None else f'{h:6.1f}'} "
            f"score {score:.3f} x={x:.2f}")
        if score >= threshold:
            return best
        _turn_by(SWEEP_STEP)
    return best


def approach(template_dir, threshold, steps=8, speed=0.55, log=print):
    """Centre the landmark and walk at it, re-centring every step."""
    found = sweep_for(template_dir, threshold, log=log)
    if not found or found[0] < threshold:
        log(f"      landmark not found (best {found[0]:.3f} < {threshold})")
        return False
    for i in range(steps):
        img = compass.fast_capture()
        score, x, scale = jukebox.find(img, template_dir)
        if score < threshold * 0.75:
            log(f"      lost the landmark at step {i} (score {score:.3f})")
            return False
        off = (x - 0.5) * FOV_DEGREES
        if abs(x - 0.5) > CENTRE_TOLERANCE:
            _turn_by(off)
        ar.send([f"left_y {ar.to_axis(-speed)}", "left_x 0",
                 "right_x 0", "right_y 0"])
        time.sleep(0.35)
        ar.send(["left_x 0", "left_y 0"])
        time.sleep(0.25)
        log(f"      step {i + 1}: score {score:.3f} x={x:.2f} scale {scale}")
    return True
