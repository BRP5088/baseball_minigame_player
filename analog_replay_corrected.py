"""Replay recorded stick input, but correct heading drift as it goes.

WHY CORRECTION IS NEEDED AT ALL
-------------------------------
Pure replay is open-loop: it reproduces the inputs and assumes the world
responds identically. It very nearly does — with analog values at native rate
the timing matches to 20.3s against 20.3s recorded — but "very nearly" is not
enough over a long walk. Measured on the 2026-08-27 recording, the walk from
12.5s to 19.5s holds the stick forward for seven seconds while the heading
drifts a few degrees. A few degrees over seven seconds of travel is enough
lateral offset to clip a doorframe, and the character snags on the door leaving
the first building.

WHAT THIS ADDS
--------------
The recording says what the heading SHOULD be at every moment. So: replay the
sticks unchanged, watch the compass, and when the live heading falls behind the
recorded one, add a small right_x offset to steer back. The character's own
inputs still drive the walk; this only removes accumulated error.

THE COMPASS IS READ ON ANOTHER THREAD. A read takes ~60ms, and the input stream
runs at 50Hz (20ms per sample) — reading inline would stall a third of the
samples and wreck the timing that took all evening to get right.
"""

import json
import math
import os
import threading
import time

import analog_replay as ar

# FINAL APPROACH, measured 2026-08-27 23:58.
# The replay ends at the table but a step short of interaction range. From
# there this reaches the prompt:
#     left_x -0.5 for 0.4s   (strafe left)
#     left_y -0.45 for 0.4s  (step forward)
# Applied as ONE smooth move, not a sequence of hops with pauses between —
# three separate nudges overshot, and instant full-value application reads as a
# lurch rather than a walk.
FINAL_STRAFE = (-0.5, 0.4)
FINAL_FORWARD = (-0.45, 0.4)

CORRECT_ABOVE_DEG = 3.0     # ignore drift smaller than this
MAX_CORRECTION = 0.35       # cap the nudge; this steers, it does not turn
DEG_TO_STICK = 0.02         # stick units per degree of error


class HeadingWatcher:
    """Continuously reads the compass on its own thread."""

    def __init__(self):
        self.heading = None
        self._stop = threading.Event()
        self._t = None

    def start(self):
        import compass

        def loop():
            while not self._stop.is_set():
                try:
                    b = compass.read_bearing(compass.fast_capture())
                    if b is not None:
                        self.heading = b
                except Exception:
                    pass
        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()
        return self

    def stop(self):
        self._stop.set()


def recorded_heading(rows, t):
    """What the heading was at time t in the recording, or None."""
    dec = [(r["t"], r["heading"]) for r in rows if r.get("heading") is not None]
    if not dec:
        return None
    near = min(dec, key=lambda d: abs(d[0] - t))
    return near[1] if abs(near[0] - t) < 1.0 else None


def replay(demo_dir, t0=5.6, t1=25.9, log=print):
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    rows = json.load(open(os.path.join(demo_dir, "timeline.json")))
    win = [s for s in samples if t0 <= s["t"] <= t1]
    if not win:
        log("  nothing to replay")
        return

    watcher = HeadingWatcher().start()
    time.sleep(0.4)                      # let it get a first reading
    log(f"  replaying {len(win)} samples with heading correction "
        f"(live heading {watcher.heading})")

    corrections = 0
    start_t = win[0]["t"]
    started = time.time()
    try:
        for s in win:
            a = s["axes"]
            rx = a.get("rx", 0.0)
            want = recorded_heading(rows, s["t"])
            live = watcher.heading
            if want is not None and live is not None:
                err = (want - live + 540) % 360 - 180
                if abs(err) > CORRECT_ABOVE_DEG:
                    nudge = max(-MAX_CORRECTION,
                                min(MAX_CORRECTION, err * DEG_TO_STICK))
                    rx = max(-1.0, min(1.0, rx + nudge))
                    corrections += 1
            ar.send([f"left_x {ar.to_axis(a.get('lx', 0))}",
                     f"left_y {ar.to_axis(a.get('ly', 0))}",
                     f"right_x {ar.to_axis(rx)}",
                     f"right_y {ar.to_axis(a.get('ry', 0))}"])
            behind = (s["t"] - start_t) - (time.time() - started)
            if behind > 0:
                time.sleep(behind)
    finally:
        ar.clear()
        watcher.stop()
    log(f"  done in {time.time() - started:.1f}s, corrected on "
        f"{corrections}/{len(win)} samples")
