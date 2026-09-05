"""Replay a recorded walk by FOLLOWING ITS HEADING TRACE, not a summary of it.

WHY NOT SEGMENTS
----------------
Summarising the recording into legs, or even into arcs, throws away the shape.
The first segment of the 2026-08-27 recording ran 6.86s from 87 to 271 degrees;
replayed as one uniform arc that is a smooth semicircle, and it drove straight
into the office furniture. The human walked mostly straight, then turned — same
endpoints, completely different path.

So instead of describing the walk, follow it: every STEP_SEC, look up what the
heading was at that point in the recording, steer toward it, and keep walking.
The recording is the plan at full resolution.

Position is not observable, so this is still open-loop in POSITION — but it is
closed-loop in HEADING at every step, which is the part that drifts.
"""

import json
import os
import time

STEP_SEC = 0.5
WALK_KEY = "walk_up"


def load_trace(demo_dir):
    """[(t, heading)] with gaps filled from the nearest decoded frame."""
    rows = json.load(open(os.path.join(demo_dir, "timeline.json")))
    decoded = [(r["t"], r["heading"]) for r in rows if r["heading"] is not None]
    if not decoded:
        return []
    out = []
    for r in rows:
        t = r["t"]
        near = min(decoded, key=lambda d: abs(d[0] - t))
        out.append((t, near[1] if abs(near[0] - t) < 1.5 else None))
    return [(t, h) for t, h in out if h is not None]


def moving_window(demo_dir, moving_delta=6.0):
    """(start, end) of the stretch where the walk actually happens.

    Trims the reset/loading at the front and the standing-at-the-table tail,
    both of which are motionless and would otherwise be replayed as walking.
    """
    rows = json.load(open(os.path.join(demo_dir, "timeline.json")))
    mov = [r["t"] for r in rows if r["motion"] and r["motion"] >= moving_delta]
    return (mov[0], mov[-1]) if mov else (None, None)


def replay(demo_dir, turn_to, press_walk, read, log=print):
    """Walk the recording. turn_to(target) must close the loop on the compass."""
    trace = load_trace(demo_dir)
    t_start, t_end = moving_window(demo_dir)
    if not trace or t_start is None:
        log("  nothing to replay")
        return
    log(f"  replaying {t_start:.1f}s..{t_end:.1f}s at {STEP_SEC}s resolution")

    t = t_start
    while t < t_end:
        target = min(trace, key=lambda x: abs(x[0] - t))[1]
        turn_to(target)
        press_walk(STEP_SEC)
        t += STEP_SEC
    log(f"  replay finished; final heading {read()}")
