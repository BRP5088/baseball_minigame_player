"""Walk the confirmed route, checking each leg against what it should look like.

Two independent confirmations per leg, because either alone has failed before:

  * the COMPASS says which way we are facing — but a correct heading walked
    from the wrong position ends somewhere else entirely, which is how the old
    route's leg 3 passed its own checks while missing the bar;
  * the SCENE says where we ended up — but only coarsely, so it cannot steer.

Together they catch what each misses. A leg that faces right and looks right is
almost certainly right.
"""

import os
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-route")

import numpy as np

import compass
import input_controller as ic
import landmark_check as lc
import route_v2
import turn_calibrated as tc

# BLOCKED IS RELATIVE, NOT ABSOLUTE.
#
# A fixed threshold on mean frame change does not survive a change of scene:
# walking down a bright street moves far more pixels than walking through a
# dark interior, so one number cannot mean "stopped" in both. A run with
# STUCK_DELTA=2.0 walked leg 1 for its full 5 seconds without ever registering
# the door it was pressed against, and every later leg started from the wrong
# place and ended jammed into an NPC.
#
# So compare against how much THIS leg was moving when it was clearly moving:
# blocked is when the frame change falls to a small fraction of the largest
# change seen so far on this leg.
# ...and comparing CONSECUTIVE frames does not work either. Jammed against a
# wall the character keeps animating, so consecutive frames keep differing: a
# real leg-1 walk plateaued at a delta of ~3.5 forever and never dipped below
# an 18%-of-peak limit of 2.89. "Stuck but animating" and "moving slowly" look
# identical over half a second.
#
# Over a LONGER baseline they separate completely. Progress accumulates and
# animation does not, so the frame from ~1.5s ago is nearly identical when
# stuck and clearly different when still moving.
LOOKBACK_CHUNKS = 3        # x CHUNK_SEC = 1.5s of travel to compare against
LOOKBACK_SIMILARITY = 0.97 # above this, 1.5s of walking changed nothing

CHUNK_SEC = 0.5
REFERENCE_DIR = "route_frames"


def _read():
    return compass.read_bearing(compass.fast_capture())


def _press(action, hold):
    ic._bg_hold_keys([ic.KEYMAP[action]], hold)


def _grey(img):
    return np.asarray(img.convert("L"), dtype=float)


def start_from_known_pitch(log=None):
    """Home the camera pitch before walking anything.

    PITCH IS STATE, and nothing else in the route accounts for it. A camera
    tilted up sees walls and ceilings, which made a 360 sweep of a landing look
    like a sweep of pipework and sent the navigation off after the wrong
    features entirely. Heading is measured every leg; pitch never was, so it
    drifts across a session and quietly changes what every frame shows.

    level_pitch() homes to the floor endstop — a hard limit that can actually be
    detected — and steps up a fixed amount, so it is repeatable in a way that
    "tilt up a bit" is not.
    """
    ok = ic.level_pitch(compass.fast_capture)
    if log:
        log(f"  pitch homed: {ok}")
    return ok


def walk_leg(leg, log=print):
    """Face the leg's heading, walk it, return (facing, seconds, frame)."""
    facing = tc.turn_to(leg["face"], _read, _press, tolerance=2.5, max_steps=12)
    if facing is None:
        raise RuntimeError("compass will not read — refusing to walk blind")

    history = [compass.fast_capture()]
    prev = _grey(history[0])
    spent = 0.0
    while spent < leg["secs"] - 1e-3:
        step = min(CHUNK_SEC, leg["secs"] - spent)
        ic._bg_hold_keys([ic.KEYMAP["walk_up"]], step)
        spent += step
        time.sleep(0.4)
        shot = compass.fast_capture()
        cur = _grey(shot)
        delta = float(np.abs(cur - prev).mean())
        prev = cur
        history.append(shot)
        if log:
            log(f"        {spent:4.1f}s delta {delta:6.2f}")
        if leg["kind"] != "until_blocked":
            continue
        # Only meaningful once we have seen this leg actually moving; the very
        # first chunk has nothing to compare against.
        if len(history) > LOOKBACK_CHUNKS:
            back = history[-1 - LOOKBACK_CHUNKS]
            travelled = lc.similarity(shot, back)
            if log:
                log(f"           vs {LOOKBACK_CHUNKS * CHUNK_SEC:.1f}s ago: "
                    f"{travelled:.3f}")
            if travelled >= LOOKBACK_SIMILARITY:
                break
    return facing, spent, compass.fast_capture()


def reference_for(index):
    """The stored frame for leg `index`, or None if none was captured."""
    from PIL import Image
    stem = {1: "leg1_officedoor", 2: "leg2_storefront", 4: "leg4_barentry"}.get(index)
    if not stem:
        return None
    for suffix in ("__a.png", "__b.png"):
        path = os.path.join(REFERENCE_DIR, stem + suffix)
        if os.path.exists(path):
            return Image.open(path)
    return None


def run(log=print):
    """Walk every leg. Returns a list of per-leg results."""
    results = []
    start_from_known_pitch(log)
    for i, leg in enumerate(route_v2.TO_BAR, 1):
        facing, spent, frame = walk_leg(leg, log)
        ref = reference_for(i)
        if ref is None:
            verdict, score = None, None
        else:
            verdict, score = lc.matches(frame, ref)
        results.append(dict(leg=i, facing=facing, seconds=spent,
                            looks_right=verdict, score=score))
        shown = "no reference" if score is None else \
            f"scene {score:.2f} {'OK' if verdict else 'MISMATCH'}"
        log(f"  leg {i}: faced {facing:6.1f} (wanted {leg['face']:.1f}), "
            f"walked {spent:.1f}s — {shown}")
        log(f"          expected: {leg['ends']}")
    return results


if __name__ == "__main__":
    import reset_env
    spawn = reset_env.reset_environment(log=lambda m: None)
    print(f"  reset: spawn {spawn:.1f}\n")
    run()
