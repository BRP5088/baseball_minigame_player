"""Just the last stretch: Wanda -> corner -> jukebox -> right -> table.

    python3 last_mile.py                 # walk it with the current numbers
    python3 last_mile.py 1.6 3.3 4.1     # override the three leg durations

NO recovery fan, NO escape wandering, no full route. The character is parked in
front of Wanda by hand; this walks the four moves the human described and says
where it ended up. Everything that made the executor wander is off, because
watching it wander is how we established it does not help.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Bearings from the recorded route, which agree with the human description:
#   around the corner  ~287 (WNW)      toward the jukebox  ~2 (N)
#   turn right          ~90 (E)        then approach the table
CORNER_BEARING = 287.0
JUKEBOX_BEARING = 2.0
TABLE_BEARING = 90.0
DEFAULTS = (2.0, 3.3, 4.1)          # corner, jukebox, table — seconds


def walk(bearing, seconds, speed=0.25, log=print):
    """Turn, then push in <=0.8s chunks so chiaki's watchdog cannot cut it."""
    import walk_steps as ws

    ws.turn_to(bearing % 360.0, log=lambda *a: None)
    time.sleep(0.3)
    left, moved = seconds, 0.0
    while left > 0.01:
        step = min(0.8, left)
        moved += ws.walk_forward(speed, step) or 0.0
        time.sleep(0.2)
        left -= step
    return moved


def main(durs=DEFAULTS, log=print):
    import compass
    import ensure_stream
    import places
    import table_prompt as tp

    if not ensure_stream.ensure_live(log=log):
        log("no live picture")
        return 2

    corner_s, juke_s, table_s = durs
    img = compass.fast_capture()
    log(f"start: {places.identify(img)}  bearing {compass.read_bearing(img)}")

    for name, bearing, secs in (("around the corner", CORNER_BEARING, corner_s),
                                ("toward the jukebox", JUKEBOX_BEARING, juke_s),
                                ("right, to the table", TABLE_BEARING, table_s)):
        moved = walk(bearing, secs, log=log)
        img = compass.fast_capture()
        room, n, ratio = places.identify(img)
        log(f"  {name:20} {bearing:5.0f} for {secs:.1f}s -> moved {moved:5.1f}, "
            f"here={room} ({n}), at_table={tp.at_table(img)}")
        if tp.at_table(img):
            log("  AT THE TABLE")
            return 0

    # One aim sweep at the end: turning costs nothing and cannot wedge anything.
    import graph_walk
    ok, _ = graph_walk.face_the_table(log=log)
    img = compass.fast_capture()
    log(f"after sweep: at_table={tp.at_table(img)}  ink={tp.ink(img):.4f}  "
        f"here={places.identify(img)}")
    return 0 if ok else 1


if __name__ == "__main__":
    d = [float(x) for x in sys.argv[1:4]] if len(sys.argv) >= 4 else list(DEFAULTS)
    sys.exit(main(tuple(d)))
