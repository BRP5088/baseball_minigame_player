"""Walk the route as a WORLD-SPACE path: face a bearing, then walk forward.

WHY THIS SHAPE
--------------
Every previous attempt replayed the run as camera-plus-feet moving together,
because that is how it was recorded. But the two are separable, and separating
them removes the dominant error.

Where the character TRAVELS is the camera bearing combined with the stick's own
angle. Recovering that gives a path in world coordinates — 13 steps, 13.2
seconds of walking — that says nothing about where the camera was pointing.
Each step can then be performed as: turn to an absolute bearing (closed-loop on
the compass, accurate to a few degrees), then walk straight forward.

The point is that the character never walks while turning. Continuous following
had to steer and travel at once, so any heading lag became distance in the wrong
direction, and a lag of 30 degrees at the top of a staircase put the run in the
wrong room. Here a heading error is corrected BEFORE any distance is covered, so
it cannot turn into position error.

What remains open-loop is how far each step travels. That is why every step
measures how much the view changed and reports the ones that went nowhere —
a step that is blocked by a doorframe is the failure this cannot prevent, only
detect.
"""

import json
import os
import time

import numpy as np

import analog_replay as ar
import compass
import turn_curve as tc

TURN_TOLERANCE = 3.5
TURN_MAX_STEPS = 12
SETTLE = 0.25
STUCK_CHANGE = 2.5         # mean frame delta below this means nothing moved

# Turning in place covers no ground, but the recording DID cover ground while
# turning — the player never stopped. Replaying the route as turn-then-walk
# therefore travels systematically short: 25 steps of it ended where the
# recording was six seconds earlier, outside the L&B building rather than
# inside at the table. dur_scale buys that distance back. It is a calibration
# knob, not a constant of the world: it compensates for a specific difference
# between how the route was recorded and how it is replayed, and it needs
# re-measuring if either changes.
DEFAULT_DUR_SCALE = 1.35


def _err(a, b):
    return (a - b + 540) % 360 - 180


def read_heading(tries=4):
    for _ in range(tries):
        b = compass.read_bearing(compass.fast_capture())
        if b is not None:
            return b
        time.sleep(0.05)
    return None


def turn_to(target, log=print, tolerance=TURN_TOLERANCE, max_steps=None):
    """Turn to an absolute bearing.

    `tolerance` is a parameter because the right value depends on the job. For
    walking a route, 3.5 degrees is fine and stopping early saves time. For
    putting a reticle ON something it is far too coarse: a request to turn 2.1
    degrees was silently discarded as "already there", so fine aiming stalled
    with the target visibly off centre and the log reporting "turned +0.0 deg".

    That discard is now LOGGED rather than silent. Every other exit is too: a
    turn that never happened, one the stick could not plan, and one that ran to
    exhaustion all used to return a heading and say nothing, so the caller
    could not tell them apart from a turn that reached its target.
    """
    steps = max_steps or TURN_MAX_STEPS
    for i in range(steps):
        now = read_heading()
        if now is None:
            # A single unreadable frame used to abandon the turn SILENTLY, so
            # the caller saw "turned +0.0 deg" and no explanation. read_heading
            # already retries; if it still fails the bearing is genuinely
            # unavailable here, which is worth saying rather than hiding.
            log("      no compass reading; cannot turn to an absolute bearing")
            return None
        e = _err(target, now)
        if abs(e) <= tolerance:
            if i == 0:
                log(f"      turn to {target:.1f}: NO-OP, already inside "
                    f"{tolerance:.1f} deg (at {now:.1f}, err {e:+.1f}) — "
                    f"nothing was sent; a caller reporting 'turned +0.0 deg' "
                    f"is reporting a turn that never happened")
            return now
        mag, secs = tc.plan_turn(e)
        if mag == 0.0:
            log(f"      turn to {target:.1f}: err {e:+.1f} is below the 0.5 "
                f"deg plan_turn will act on, so NOTHING was sent — the stick's "
                f"floor, not a turn that was attempted and missed")
            return now
        ar.send([f"right_x {ar.to_axis(mag if e > 0 else -mag)}",
                 "right_y 0", "left_x 0", "left_y 0"])
        time.sleep(secs)
        ar.send(["right_x 0"])
        time.sleep(SETTLE)
    log(f"      turn to {target:.1f}: {steps} pushes and still outside "
        f"{tolerance:.1f} deg — this turn RAN and did NOT converge, so the "
        f"heading returned is where it gave up, not where it was aimed")
    return read_heading()


def _grey():
    return np.asarray(compass.fast_capture().convert("L"), dtype=float)


def _view_change(before, after):
    """Mean absolute difference, tolerant of the capture CHANGING SIZE.

    chiaki's window is resized while it reconnects, and a capture taken across
    that moment comes back a different shape — measured 2026-09-02, a run died
    on "operands could not be broadcast together with shapes (1084,1927)
    (1080,1920)" in the middle of a leg. Comparing the overlapping region keeps
    the number meaningful instead of killing the walk.
    """
    h = min(before.shape[0], after.shape[0])
    w = min(before.shape[1], after.shape[1])
    return float(np.abs(before[:h, :w] - after[:h, :w]).mean())


def walk_forward(speed, seconds, strafe=0.0):
    """Walk ahead (optionally crabbing sideways). Returns the view change."""
    before = _grey()
    ar.send([f"left_y {ar.to_axis(-abs(speed))}",
             f"left_x {ar.to_axis(strafe)}", "right_x 0", "right_y 0"])
    time.sleep(seconds)
    ar.send(["left_x 0", "left_y 0"])
    time.sleep(SETTLE)
    return _view_change(before, _grey())


def unstick(speed, seconds, log=print):
    """Try to get moving again after a step made no progress.

    Every failed run so far reports a STUCK step, and a DIFFERENT one each time
    — the first half of the route is repeatable and the second half crosses a
    crowded bar where the character catches on furniture and on NPCs that are
    not where they were last time. Continuing as though a blocked step had
    succeeded is what turns one collision into a run that ends somewhere else
    entirely.

    Crabbing sideways while still pushing forward slides along whatever is in
    the way, which is what a person does without thinking about it. Both
    directions are tried because which one is open depends on what was hit.
    """
    tried = []
    for strafe, name in ((-0.6, "left"), (0.6, "right"), (-0.9, "hard left")):
        moved = walk_forward(speed, max(seconds, 0.35), strafe=strafe)
        tried.append((name, moved))
        if moved >= STUCK_CHANGE:
            log(f"        unstuck by crabbing {name} (moved {moved:.1f})")
            return moved
    # Three measurements were taken and all three were thrown away with the
    # bare `return 0.0`, so a failed escape logged NOTHING — indistinguishable
    # from an escape that was never attempted, and it hides how close each crab
    # came to the threshold.
    log("        crabbing did NOT free it: "
        + ", ".join(f"{n} {m:.1f}" for n, m in tried)
        + f" (all under {STUCK_CHANGE}) — the character DID crab {len(tried)} "
          f"times, so the caller's STUCK is a failed escape, not an absent one")
    return 0.0


def run(steps_path="route_steps.json", final_cam=82.4, log=print,
        speed_scale=1.0, dur_scale=1.0, capture_dir=None):
    steps = json.load(open(steps_path))
    hazards = []
    for i, s in enumerate(steps, 1):
        got = turn_to(s["bearing"], log=log)
        off = None if got is None else _err(s["bearing"], got)
        moved = walk_forward(s["speed"] * speed_scale, s["dur"] * dur_scale)
        note = ""
        if moved < STUCK_CHANGE:
            recovered = unstick(s["speed"] * speed_scale, s["dur"] * dur_scale,
                                log=log)
            if recovered >= STUCK_CHANGE:
                note = "  (was stuck, crabbed free)"
                hazards.append((i, "STUCK-RECOVERED", recovered))
                # re-aim: crabbing moves the character off the step's line
                back = turn_to(s["bearing"], log=log)
                # The step line below prints `got`, which was read BEFORE the
                # crab, so it is stale by the time it is printed. Without this
                # the re-aim's result is discarded and a re-aim that failed
                # reads exactly like one that worked.
                log(f"        re-aimed after crabbing: wanted "
                    f"{s['bearing']:.1f}, got "
                    f"{'--' if back is None else f'{back:.1f}'} — the step "
                    f"line's 'got' below predates the crab")
                moved = recovered
            else:
                note = "  STUCK — could not free it"
                hazards.append((i, "STUCK", moved))
        if off is not None and abs(off) > TURN_TOLERANCE * 2:
            note += f"  UNDERTURNED by {off:+.1f}"
            hazards.append((i, "UNDERTURNED", off))
        log(f"    step {i:2}/{len(steps)} bearing {s['bearing']:6.1f} "
            f"(got {'--' if got is None else f'{got:6.1f}'}) "
            f"{s['dur']:.2f}s moved {moved:5.1f}{note}")
        if capture_dir:
            compass.fast_capture().save(
                os.path.join(capture_dir, f"step{i:02d}.jpg"), quality=85)
    if final_cam is not None:
        turn_to(final_cam, log=log)
    ar.clear()
    return hazards


if __name__ == "__main__":
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    run()
