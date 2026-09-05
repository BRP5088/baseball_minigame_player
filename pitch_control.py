"""Aim the camera vertically. Self-calibrating, because pitch has no sensor.

Yaw is easy: the compass reads it absolutely, so `turn_to` closes the loop on a
number. Pitch has no such reading anywhere in the HUD, so the only feedback is
where the target APPEARS in frame — which is enough, provided the relationship
between stick input and screen movement is measured rather than assumed.

That relationship is measured HERE, at the moment of use, by watching what a
probe pulse actually does. It is not a constant worth storing: it depends on the
game's sensitivity setting, and a stored value that silently goes stale is worse
than one measured every time, because a wrong pitch is invisible to every other
check in this project.

THE SIGN, MEASURED PROPERLY
---------------------------
POSITIVE right_y looks DOWN. Measured by pointing the camera and watching mean
frame brightness, which is unambiguous because the ceiling is bright and the
floor is dark: right_y +0.7 took brightness from 83 to 44 (floor), and -0.7 took
it from 77 to 118 (ceiling).

An earlier version tried to discover this by watching where a TEMPLATE matched
before and after a pulse. That gave the opposite answer and drove the camera to
the ceiling, because the template had jumped to a different match rather than
tracking the same object — its score changed from 0.451 to 0.657 across the
pulse. A measurement whose reference can silently relocate is not a measurement.
Whole-frame brightness cannot relocate.

Because the camera looking DOWN moves the scene UP the frame, a target BELOW
centre (dy > 0) needs POSITIVE right_y.
"""

import time

import analog_replay as ar
import aim
import compass
import jukebox

PROBE_MAG = 0.55
# A gentler stick for fine work. The pulse cannot be made arbitrarily short —
# below MIN_PULSE_SEC the stick does not register — so the only way to move less
# is to push less hard. Measured: 0.55 for the minimum 0.08s moves about 0.056
# of frame height, which is EIGHT times the tolerance and three times a typical
# residual error, so fine corrections always overshot.
FINE_MAG = 0.34
FINE_BELOW = 0.05          # errors smaller than this use the gentle stick
PROBE_SEC = 0.12
SETTLE = 0.30
# Tightened from 0.030 once aiming actually worked. At 0.030 the reticle lands
# on the target but visibly off its centre — 0.024 of frame height is about 1.9
# degrees, which a person watching can see. The loop converges quickly enough
# that a tighter bar costs one extra pulse, not a stall.
TOL = 0.007            # fraction of frame height (~0.6 deg)
MAX_STEPS = 9
MIN_SCORE = 0.30
YAW_TOL = 0.007        # fraction of frame width (~1.0 deg)
# The turn controller's own tolerance while aiming. Its default of 3.5 degrees
# is coarser than the aiming tolerance itself, so it would refuse the very
# corrections being asked for.
FINE_TURN_TOL = 0.5
MIN_PULSE_SEC = 0.08   # shorter than this and the stick does not register

# Apply only part of the computed correction each step. The rate is learned from
# a single probe pulse and is therefore noisy; acting on it in full overshoots.
# Measured: a correction from dy -0.035 shot past to +0.080, a 2.3x overshoot,
# and the safety check aborted the loop with the target still off. Damping trades
# one extra pulse for convergence.
DAMPING = 0.55

# WHERE ON THE TARGET THE RETICLE SHOULD SIT.
#
# Driving the offsets to zero puts the reticle on the template's geometric
# centre, which is not necessarily where you would aim. The bias shifts the goal
# posts: it is measured in the same units as the offsets (fractions of frame),
# and it is a preference, not a correction, so it lives here rather than being
# folded into the geometry.
#
# Signs: the reticle is fixed at screen centre, so to place it FURTHER RIGHT on
# the target the target must sit further LEFT, i.e. a negative x bias. Likewise
# a negative y bias places the reticle lower on the target.
# TUNED BY EYE, because "is the reticle on her" is a judgement only a person
# watching can make.
#
# History, since it may need revisiting: close up, x -0.030 sat slightly left
# and -0.045 slightly right, and y -0.020 was called perfect while -0.040 was
# too low. From further back, that same pair read as too far right and too low —
# hence the smaller values here. If a single pair cannot satisfy both distances,
# the bias is not a fixed offset and should scale with apparent size, i.e. live
# per template set rather than globally.
AIM_BIAS_X = -0.026
AIM_BIAS_Y = -0.008
MAX_SEC = 0.45


def _pulse(mag, secs):
    ar.send([f"right_y {ar.to_axis(mag)}", "right_x 0",
             "left_x 0", "left_y 0"])
    time.sleep(secs)
    ar.send(["right_y 0"])
    time.sleep(SETTLE)


def _look(template_dir, samples=3):
    """Median position over several frames.

    A single frame's match can relocate — a marginal score jumps between
    features, and a controller acting on it steers at the jump rather than the
    target. The median ignores a lone outlier; a wide spread means the match is
    not stable enough to act on at all, so the score is knocked down and the
    caller treats it as not seen.
    """
    obs = []
    for _ in range(samples):
        img = compass.fast_capture()
        sc, x, y, _, _ = jukebox.find_best_xy(img, template_dir)
        obs.append((sc, x, y))
        time.sleep(0.05)
    obs.sort(key=lambda o: o[1])
    score, x, _ = obs[len(obs) // 2]
    ys = sorted(o[2] for o in obs)
    y = ys[len(ys) // 2]
    if (obs[-1][1] - obs[0][1]) > 0.06 or (ys[-1] - ys[0]) > 0.06:
        score = min(score, MIN_SCORE - 0.01)
    return score, x, y


def _heading(tries=4):
    """The compass, retried. It abstains on the odd frame."""
    for _ in range(tries):
        h = compass.read_bearing(compass.fast_capture())
        if h is not None:
            return h
        time.sleep(0.08)
    return None


ACQUIRE_STEPS = 6
ACQUIRE_SEC = 0.14
ACQUIRE_MAG = 0.55
ACQUIRE_SCORE = 0.42


def acquire(template_dir, log=print):
    """Pitch DOWN until the landmark is properly in frame.

    Needed because of a genuine chicken-and-egg. The camera rests pitched
    slightly up, which puts a seated character at the very bottom of the frame
    with most of her below the edge — and a template of her head and torso
    cannot match something that is half off-screen. So the matcher does not find
    her, and without finding her there is nothing to tell the camera to look
    down.

    Looking down is the right prior regardless: the things worth interacting
    with in this game sit at table height, never above the horizon. So sweep
    downward a step at a time and stop as soon as she is confidently in view.
    """
    best = (-2.0, 0)
    for i in range(ACQUIRE_STEPS):
        score, x, y = _look(template_dir)
        if score >= ACQUIRE_SCORE and 0.15 < y < 0.85:
            log(f"      acquired at step {i}: score {score:.3f} y={y:.3f}")
            return True
        if score > best[0]:
            best = (score, i)
        _pulse(ACQUIRE_MAG, ACQUIRE_SEC)      # positive = down; see module docs
    log(f"      could not acquire (best {best[0]:.3f})")
    return False


def centre_pitch(template_dir, log=print):
    """Pitch until the landmark sits at the vertical centre. Returns final dy."""
    score, x, y = _look(template_dir)
    if score < MIN_SCORE:
        log(f"      pitch: landmark not visible ({score:.3f})")
        return None

    rate = None            # fraction of frame height per (magnitude x second)
    for i in range(MAX_STEPS):
        score, x, y = _look(template_dir)
        if score < MIN_SCORE:
            log("      pitch: lost the landmark")
            return None
        dy = y - 0.5 - AIM_BIAS_Y
        if abs(dy) <= TOL:
            log(f"      pitch: centred, dy {dy:+.3f} "
                f"({aim.pitch_for_offset(dy):+.1f} deg)")
            return dy

        # Positive right_y looks DOWN, which moves a target UP the frame. So a
        # target below centre (dy > 0) needs positive.
        strength = FINE_MAG if abs(dy) < FINE_BELOW else PROBE_MAG
        mag = strength if dy > 0 else -strength
        # SCALE THE PROBE to the error. A fixed first pulse is fine for a large
        # error and far too big for a small one: starting from dy -0.037 it
        # overshot to +0.076 before any damping could apply, and the loop
        # aborted with the target still off. The probe still has to be big
        # enough to produce a measurable movement, hence the floor.
        probe_sec = PROBE_SEC if abs(dy) > 0.06 else \
            max(MIN_PULSE_SEC, PROBE_SEC * abs(dy) / 0.06)
        secs = probe_sec if rate is None else \
            max(MIN_PULSE_SEC,
                min(MAX_SEC, DAMPING * abs(dy) / (abs(rate) * strength)))
        before = y
        _pulse(mag, secs)
        score, x, y = _look(template_dir)
        if score < MIN_SCORE:
            log("      pitch: lost the landmark after a pulse")
            return None
        moved = y - before
        if abs(moved) < 1e-3:
            log("      pitch: no movement (at the limit of travel?)")
            return y - 0.5
        # Learn the rate from what actually happened, and CHECK the direction
        # helped. If the error grew, the sign assumption is wrong for this
        # situation and continuing would drive the camera to an endstop, which
        # is exactly how a previous version ended up staring at the ceiling.
        if abs(y - 0.5 - AIM_BIAS_Y) > abs(dy) + 0.005:
            # UNDO IT. Stopping here used to leave the camera worse than before
            # the attempt — one run went from dy -0.017 to +0.100 and reported
            # that as the result. Reversing the pulse restores the better
            # position, which is the honest place to give up.
            log(f"      pitch: correction overshot "
                f"({dy:+.3f} -> {y - 0.5 - AIM_BIAS_Y:+.3f}); reverting")
            _pulse(-mag, secs)
            score, x, y = _look(template_dir)
            log(f"      pitch: reverted to dy {y - 0.5 - AIM_BIAS_Y:+.3f}")
            return y - 0.5 - AIM_BIAS_Y
        rate = moved / (mag * secs)
    return y - 0.5


SEARCH_STEP = 30.0
SEARCH_SCORE = 0.45


def search_for(template_dir, walk_steps, log=print):
    """Sweep until the landmark is found. Returns True if acquired.

    Needed for the realistic case: the camera does not start pointed at the
    thing. Sweeps yaw a step at a time and, at each bearing, tries pitching down
    as well — a seated character can be below the frame edge entirely, in which
    case no amount of turning will reveal her.

    Takes the BEST bearing over a full circle rather than the first one above
    threshold, so it does not settle for a weak match when a strong one is a
    step away.
    """
    h0 = _heading()
    if h0 is None:
        return False
    best = (-2.0, None)
    n = int(round(360.0 / SEARCH_STEP))
    for i in range(n):
        target = (h0 + i * SEARCH_STEP) % 360
        walk_steps.turn_to(target, log=lambda m: None)
        time.sleep(0.30)
        score, x, y = _look(template_dir)
        if score < SEARCH_SCORE:
            # she may be below the frame; look down and check again
            _pulse(ACQUIRE_MAG, ACQUIRE_SEC)
            score, x, y = _look(template_dir)
            _pulse(-ACQUIRE_MAG, ACQUIRE_SEC)
        if score > best[0]:
            best = (score, target)
    if best[1] is None or best[0] < SEARCH_SCORE:
        log(f"      search: not found (best {best[0]:.3f})")
        return False
    walk_steps.turn_to(best[1], log=lambda m: None)
    log(f"      search: found at bearing {best[1]:.0f} (score {best[0]:.3f})")
    return True


def centre_both(template_dir, walk_steps, log=print):
    """Yaw with the compass, pitch with the probe. Returns (dx, dy)."""
    score, _, _ = _look(template_dir)
    if score < ACQUIRE_SCORE:
        acquire(template_dir, log=log)
    for _ in range(5):
        img = compass.fast_capture()
        score, x, y, _, _ = jukebox.find_best_xy(img, template_dir)
        if score < MIN_SCORE:
            return None, None
        dx = x - 0.5 - AIM_BIAS_X
        if abs(dx) > YAW_TOL:
            # relative turn; the template verifies it, so no compass required
            aim.turn_by(aim.angle_for_offset(dx), ar.send, time.sleep)
            continue
        break
    dy = centre_pitch(template_dir, log=log)
    # MEDIAN OF SEVERAL, because a single frame's match can land on a different
    # template or scale and report a position the camera never had. One run had
    # the pitch loop finish at dy +0.001 and the very next capture read +0.051,
    # which is not a camera that moved — it is a measurement that jumped. The
    # median of three ignores a lone outlier.
    xs, ys = [], []
    for _ in range(3):
        score, x, y, _, _ = jukebox.find_best_xy(compass.fast_capture(), template_dir)
        if score >= MIN_SCORE:
            xs.append(x)
            ys.append(y)
        time.sleep(0.06)
    if not xs:
        return None, None
    xs.sort()
    ys.sort()
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    spread = max(ys) - min(ys)
    if spread > 0.04:
        log(f"      note: vertical reading unstable across frames "
            f"(spread {spread:.3f}); treat dy as approximate")
    return mx - 0.5 - AIM_BIAS_X, my - 0.5 - AIM_BIAS_Y
