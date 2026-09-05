"""Replay a recorded walk: hold forward, steer with the camera, at the right SPEED.

WHAT THE RECORDING ACTUALLY SHOWS (demos/walk_20260827_214446)
--------------------------------------------------------------
The left stick points FORWARD almost the entire walk — direction 355-5 degrees
throughout. Steering is done with the RIGHT stick, turning the camera, while
forward is held. It is the ordinary third-person scheme, and it is much simpler
than the strafing arcs I had been modelling.

    left stick magnitude: min 0.16, median 0.54, max 0.77
    full-tilt samples:    0 out of 684

THE SPEED MISMATCH, which is the important part.
A keyboard press is magnitude 1.0 — there is no other option. So every replay
so far walked at roughly TWICE the recorded speed, on every leg, and no amount
of tuning the headings could fix that. Here the walk key is duty-cycled: held
for WALK_DUTY of each slice, released for the rest, which approximates a
part-pressed stick with a key that only has two states.

This is an approximation, not a reproduction. A pulsed key is not a stick held
at 0.55 — acceleration and animation differ — so treat WALK_DUTY as a knob to
calibrate against distance covered, not as a solved value.
"""

import json
import os
import time

SLICE_SEC = 0.5
WALK_DUTY = 0.55          # from the recording's median stick magnitude
HEADING_TOLERANCE = 6.0   # steer only when further off than this
TURN_DEG_PER_SEC = 124.0  # 143.8 measured on the spot, x0.86 while walking


def load_trace(demo_dir):
    """[(t, heading)] from the analysed frames, gaps filled from neighbours."""
    rows = json.load(open(os.path.join(demo_dir, "timeline.json")))
    dec = [(r["t"], r["heading"]) for r in rows if r.get("heading") is not None]
    out = []
    for r in rows:
        near = min(dec, key=lambda d: abs(d[0] - r["t"]))
        if abs(near[0] - r["t"]) < 1.5:
            out.append((r["t"], near[1]))
    return out


def walking_window(demo_dir, deadzone=0.15):
    """(start, end) of the stretch where the LEFT STICK was actually engaged.

    Taken from the input, not the picture. The picture cannot distinguish
    'walking' from 'the camera panned', and the reset at the head of the
    recording moves the picture a great deal while going nowhere.
    """
    import math
    inp = json.load(open(os.path.join(demo_dir, "input.json")))
    live = [s["t"] for s in inp
            if math.hypot(s["axes"].get("lx", 0), s["axes"].get("ly", 0)) > deadzone]
    return (live[0], live[-1]) if live else (None, None)


def replay(demo_dir, step, read, orient=None, log=print):
    """Follow the recorded heading trace WITHOUT EVER STOPPING.

    `step(walk_secs, turn_action, turn_secs)` must press the walk key and the
    turn key TOGETHER — that is the whole point, and getting it wrong is subtle
    because a sequential version produces the same log output.

    HOW THIS WENT WRONG BEFORE, twice:
    The first version called a blocking turn_to() and then walked. It visits the
    right headings and prints a plausible trace, but the character stops dead at
    every step, so the path is a series of pivots rather than a curve. The tell
    is wall time — 44.9s to replay 15.5s of walking, two thirds of it standing
    still doing compass reads.

    So: ONE compass read per slice, and the walk key is down for the whole
    slice regardless of whether steering is needed.
    """
    trace = load_trace(demo_dir)
    t0, t1 = walking_window(demo_dir)
    if not trace or t0 is None:
        log("  nothing to replay")
        return
    # ORIENT FIRST, WITHOUT WALKING.
    # The recording is already facing 269.6 when its walk begins — the camera
    # was turned during the 9s after the save reload, before the stick was
    # touched. A replay that starts at the spawn heading and walks immediately
    # spends its first second and a half travelling the wrong way while it
    # rotates, and never recovers. That is not part of the walk and must happen
    # before it.
    start_heading = min(trace, key=lambda x: abs(x[0] - t0))[1]
    if orient is not None:
        log(f"  orienting to {start_heading:.1f} before walking")
        orient(start_heading)

    log(f"  replaying {t0:.1f}s..{t1:.1f}s ({t1 - t0:.1f}s of walking)")
    t = t0
    while t < t1:
        target = min(trace, key=lambda x: abs(x[0] - t))[1]
        now = read()
        turn_action, turn_secs = None, 0.0
        if now is not None:
            err = (target - now + 540) % 360 - 180
            if abs(err) > HEADING_TOLERANCE:
                turn_action = "look_right" if err > 0 else "look_left"
                # hold the turn key for as long as this slice's rotation needs,
                # capped so it never exceeds the slice itself
                turn_secs = min(SLICE_SEC, abs(err) / TURN_DEG_PER_SEC)
        step(SLICE_SEC * WALK_DUTY, turn_action, turn_secs)
        t += SLICE_SEC
    log(f"  finished; heading {read()}")
