"""Steer to the dealer's table by keeping it centred, until the prompt appears.

WHY THIS LANDMARK AND NOT THE OTHERS
------------------------------------
Measured over a full traversal, the table template scores 0.28-0.36 anywhere on
the route, 0.45 on approach, and 0.58-0.77 standing at it. That ~0.35 separation
is the widest of anything tried:

    compass markers   ride the camera; no position information at all
    Wanda             fixed, but her prompt only appears within arm's reach,
                      and she reads a newspaper at distance so her appearance
                      changes
    jukebox           real but thin — 0.70 at it against 0.51-0.62 elsewhere,
                      and a live anchor attempt measured 0.603, unusable
    dealer's table    0.70 against 0.33

It is also the goal itself, so steering at it needs no assumption about the
relationship between a waypoint and the destination.

The prompt is the stopping condition, not the steering signal: it only appears
within a small radius, so it says "arrived" but never "which way".
"""

import time

import analog_replay as ar
import compass
import numpy as np
import jukebox
import table_prompt as tp
import walk_steps as ws

DIR = "test_fixtures/dealer"
SETTLE = 0.35              # let the camera stop before measuring
LOOKS = 2                  # frames per measurement


def measure():
    """Best table-view score over a couple of settled frames.

    A single capture taken straight after a turn catches the camera still
    moving, and motion blur halves the score: a view measured at 0.594 read
    0.323 one frame later and the approach concluded it had lost the table.
    """
    time.sleep(SETTLE)
    best = (-2.0, 0.5)
    for _ in range(LOOKS):
        img = compass.fast_capture()
        s, x, _ = jukebox.find(img, DIR)
        if s > best[0]:
            best = (s, x)
    return best
IN_VIEW = 0.42             # table somewhere in frame (measured: 0.28-0.36
                           # anywhere on the route, 0.45+ once actually in view)
CENTRED = 0.08             # fraction of frame width
FOV = 102.0                 # measured; see go.FOV_DEGREES
SWEEP = 25.0


def look_around(log=print):
    """Sweep the whole way round and go back to the BEST view of the table.

    Two changes from the obvious version, both of which cost a run:

    * The sweep completes rather than stopping at the first view above
      threshold. Taking the first acceptable heading leaves the table off to one
      side when a better one was a step away.
    * Steps are fine enough not to jump over the peak. At 45 degrees a view
      measured at 0.470 was missed entirely on the next sweep, which then
      reported the table "not in view anywhere" at 0.434.
    """
    h0 = compass.read_bearing(compass.fast_capture())
    if h0 is None:
        return None
    best = (-2.0, None, None)
    n = int(round(360.0 / SWEEP))
    for i in range(n):
        target = (h0 + i * SWEEP) % 360
        ws.turn_to(target, log=lambda m: None)
        s, x = measure()
        if s > best[0]:
            best = (s, x, target)
    if best[0] < IN_VIEW:
        log(f"      table not in view anywhere (best {best[0]:.3f})")
        return None
    ws.turn_to(best[2], log=lambda m: None)
    log(f"      best view {best[0]:.3f} at bearing {best[2]:.0f}")
    return best[0], best[1]


def approach(max_steps=14, speed=0.30, log=print):
    if look_around(log=log) is None:
        return False
    for i in range(max_steps):
        if tp.at_table(compass.fast_capture()):
            log(f"      AT THE TABLE after {i} steps")
            return True
        s, x = measure()
        h = compass.read_bearing(compass.fast_capture())
        if s < IN_VIEW * 0.72:
            log(f"      lost the table at step {i} ({s:.3f}); looking again")
            if look_around(log=log) is None:
                return False
            continue
        if abs(x - 0.5) > CENTRED and h is not None:
            ws.turn_to((h + (x - 0.5) * FOV) % 360, log=lambda m: None)
        # Short steps. A 0.30s stride at 0.40 moved far enough in one go to
        # carry the table straight out of frame — the view went 0.552 to 0.328
        # in a single step and the approach concluded it was lost.
        moved = ws.walk_forward(speed, 0.18)
        if moved < ws.STUCK_CHANGE:
            ws.unstick(speed, 0.30, log=lambda m: None)
        log(f"      step {i + 1:2}: table-view {s:.3f} x={x:.2f} moved {moved:5.1f} "
            f"prompt {tp.score(compass.fast_capture()):+.3f}")
    return tp.at_table(compass.fast_capture())
