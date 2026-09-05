"""Turn the camera by a measured number of degrees.

THE MODEL
---------
Measured 2026-08-27 on the second-monitor setup, driving chiaki through
CGEventPostToPid (no pyautogui, no focus changes). Degrees turned against hold
duration is linear across the useful range:

    0.02s ->  2.0    0.07s ->  9.5
    0.03s ->  3.9    0.10s -> 13.1
    0.05s ->  6.1    0.14s -> 19.6

    deg = 143.8 * seconds - 0.80        (residuals all under 0.5 deg)

WHY THIS IS NEW
---------------
The project previously believed the minimum turn was ~28 degrees, which is why
routes could not be steered accurately and error compounded along a walk. That
figure came from pyautogui, whose PAUSE and focus-settle delays inflated every
hold well past what was asked for. Delivered straight to the process, a 0.02s
hold turns 2 degrees. Fine steering was always possible; the input layer was
the limit.

DO NOT USE A ZERO-LENGTH HOLD. Measured median 30.5 degrees at 0.00s — more
than a 0.12s hold — because posting keydown and keyup in the same instant lets
the game see them out of order. The floor here is MIN_HOLD_SEC.

SETTLING IS MEASURED, NOT SLEPT
-------------------------------
The camera keeps moving after the key is released, and how long varies: over 20
identical holds, three still read 0.0 degrees a third of a second later and then
settled to 9.6. A fixed sleep therefore reports "the input was dropped" for what
is only latency, and a caller that corrects for that phantom miss turns twice.
"""

import time

DEG_PER_SEC = 143.8
DEG_INTERCEPT = -0.80
MIN_HOLD_SEC = 0.02          # below this the zero-hold anomaly appears
MAX_HOLD_SEC = 0.14          # beyond this the response stops being linear
MIN_TURN_DEG = DEG_PER_SEC * MIN_HOLD_SEC + DEG_INTERCEPT      # ~2.1
MAX_TURN_DEG = DEG_PER_SEC * MAX_HOLD_SEC + DEG_INTERCEPT      # ~19.3

# Chained max-length presses accumulate near-linearly, so a big turn does not
# need a compass read between every press. Measured over 2/3/5/8 presses at
# 0.14s: 18.2, 19.7, 20.3, 21.0 degrees per press — a slight upward drift with
# count, which is why the burst is deliberately UNDER-shot and finished by the
# fine phase rather than trusted to land on its own.
BURST_DEG_PER_PRESS = 20.0
BURST_GAP_SEC = 0.03
BURST_UNDERSHOOT = 0.85          # aim short; overshooting costs a whole extra pass

SETTLE_POLL_SEC = 0.12
SETTLE_STABLE_READS = 3      # consecutive equal reads before believing it
SETTLE_TIMEOUT_SEC = 1.6
# How long to wait for the camera to START moving before concluding a press did
# nothing. Measured: movement appeared within ~0.9s on every press that worked.
# Waiting the FULL settle timeout for movement that is never coming is what
# made turns take 24 seconds — turn_to settles twice per step, so every dead
# press cost the whole budget twice over.
MOVE_WAIT_SEC = 1.0
# Bounded by COUNT as well as by clock. A time-only bound is not a bound when
# the poll interval is small: with a fast poll and a compass that never answers,
# the loop spins. Found by a test that hung for ten minutes.
SETTLE_MAX_POLLS = 60
SETTLE_TOLERANCE_DEG = 0.6


def hold_for(degrees):
    """Hold duration that turns `degrees`, clamped to the calibrated range."""
    d = abs(degrees)
    secs = (d - DEG_INTERCEPT) / DEG_PER_SEC
    return max(MIN_HOLD_SEC, min(MAX_HOLD_SEC, secs))


def settled_bearing(read, changed_from=None, log=None):
    """Bearing once it stops changing, or None if it never reads.

    `changed_from` is the bearing BEFORE a press. Given it, readings still
    equal to it are treated as "the camera has not started moving yet" rather
    than as a settled answer.

    That distinction is the whole point. The camera does not begin rotating the
    instant the key is released: over 20 identical holds, three still read their
    ORIGINAL bearing a third of a second later and only reached 9.6 degrees
    after another poll. Stability alone cannot tell not-started-yet from
    finished — both look like a run of identical readings — and mistaking the
    first for the second reports a working press as a dropped one, after which
    a correcting caller turns twice.
    """
    t0 = time.time()
    recent = []
    polls = 0
    last_seen = None
    while time.time() - t0 < SETTLE_TIMEOUT_SEC and polls < SETTLE_MAX_POLLS:
        polls += 1
        b = read()
        if b is not None:
            last_seen = b
            moved = (changed_from is None or
                     abs((b - changed_from + 540) % 360 - 180) > SETTLE_TOLERANCE_DEG)
            if moved:
                recent.append(b)
                if len(recent) >= SETTLE_STABLE_READS:
                    window = recent[-SETTLE_STABLE_READS:]
                    spread = max((a - c + 540) % 360 - 180
                                 for a in window for c in window)
                    if abs(spread) <= SETTLE_TOLERANCE_DEG:
                        return window[-1]
            elif not recent and time.time() - t0 > MOVE_WAIT_SEC:
                # Nothing has moved and the grace period is spent, so this
                # press did nothing. Report the unmoved bearing NOW instead of
                # sitting out the rest of the budget.
                return b
        time.sleep(SETTLE_POLL_SEC)
    if recent:
        return recent[-1]
    if last_seen is not None:
        return last_seen
    # Never moved. Report the position it never left rather than None, so the
    # caller sees "that press did nothing" instead of "the compass failed".
    return changed_from if changed_from is not None else None


def turn_by(degrees, read, press, log=None):
    """Turn `degrees` (positive = right). Returns what was ACTUALLY turned.

    Reports the measured result rather than the requested one, because the
    two differ often enough to matter: about one press in ten keeps rotating
    past its release.
    """
    before = settled_bearing(read)
    if before is None:
        return None
    press("look_right" if degrees > 0 else "look_left", hold_for(degrees))
    after = settled_bearing(read, changed_from=before)
    if after is None:
        return None
    return (after - before + 540) % 360 - 180


def turn_to(target, read, press, tolerance=3.0, max_steps=6, log=None):
    """Steer onto `target` degrees. Returns the final bearing, or None.

    Closed loop: every step re-reads rather than trusting the model, so a
    press that overshoots is corrected on the next pass instead of being
    carried through the rest of the route.
    """
    for step in range(max_steps):
        current = settled_bearing(read)
        if current is None:
            return None
        error = (target - current + 540) % 360 - 180
        if abs(error) <= tolerance:
            return current
        want = max(-MAX_TURN_DEG, min(MAX_TURN_DEG, error))
        # COARSE PHASE. Turning 177 degrees one 19-degree press at a time cost
        # ten compass reads and 13.8 seconds. Bursting gets the bulk of the
        # rotation done in one pass, and the fine phase below cleans up.
        if abs(error) > MAX_TURN_DEG * 2:
            n = int(abs(error) * BURST_UNDERSHOOT / BURST_DEG_PER_PRESS)
            if n >= 1:
                if log:
                    log(f"    step {step + 1}: at {current:.1f}, error {error:+.1f}"
                        f" -> burst of {n} presses")
                action = "look_right" if error > 0 else "look_left"
                for _ in range(n):
                    press(action, MAX_HOLD_SEC)
                    time.sleep(BURST_GAP_SEC)
                settled_bearing(read, changed_from=current)
                continue

        if abs(want) < MIN_TURN_DEG:
            # Too small to command. Nudging by the floor and correcting back
            # would oscillate forever, so stop on the closest reachable answer.
            return current
        if log:
            log(f"    step {step + 1}: at {current:.1f}, want {target:.1f}, "
                f"error {error:+.1f}, commanding {want:+.1f}")
        press("look_right" if want > 0 else "look_left", hold_for(want))
        settled_bearing(read, changed_from=current)
    return settled_bearing(read)


# --- Screen position -> bearing --------------------------------------------
# Measured 2026-08-27 by turning a known amount and cross-correlating the scene:
# 10.9 degrees of turn shifted the image 204px, i.e. 18.7 px per degree, a
# horizontal FOV of about 103 degrees on the 1920px game frame.
#
# THIS IS NOT THE COMPASS SCALE. The HUD compass strip runs at ~3.2 px per
# degree, so it shows roughly 260 degrees of heading across a strip narrower
# than the picture. Reading a landmark's bearing off the COMPASS scale — which
# is the intuitive mistake, since both are horizontal pixels — overstates the
# angle by 5.8x. Doing exactly that put the L&B doorway at 319 degrees when it
# was really at 359, and walking that heading drove the character into a wall.
SCREEN_PX_PER_DEG = 18.7
FRAME_CENTRE_X = 960.0


def bearing_of_screen_x(x, current_bearing, frame_width=1920):
    """Bearing of something seen at horizontal pixel `x`.

    The reticle sits at the centre of the frame and shows `current_bearing`, so
    everything else is an offset from it at the SCREEN scale.
    """
    centre = frame_width / 2.0
    return (current_bearing + (x - centre) / SCREEN_PX_PER_DEG) % 360
