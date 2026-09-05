"""Replay recorded input as CONTINUOUS holds, scaled by stick magnitude.

THE REASONING
-------------
chiaki-ng's keyboard mapping sends FIXED stick values — a key is full
deflection or nothing, with no analog channel. The recording walked at a median
magnitude of 0.54. So a key covers the same ground in 54% of the time.

Rather than approximate 0.54 by pulsing a key on and off inside each slice —
which re-accelerates from a standstill on every pulse and measurably
under-travelled — hold the key CONTINUOUSLY for a shorter time.

Consecutive samples with a similar stick state are merged into one run, and
that run is issued as a single hold of `duration * magnitude`. One press,
shorter, instead of many short presses.

NEVER REPLAYED, whatever the recording holds: square (spends $50 at the
Baseball Cards prompt) and options (opens the pause menu).
"""

import json
import math
import os

DEADZONE = 0.15
NEVER_PRESS = {"square", "options", "ps", "touchpad", "share", "mic"}
DIR_BUCKET = 25.0         # degrees; how different a direction must be to split
MAG_BUCKET = 0.25         # magnitude change that splits a run
MIN_RUN = 0.08            # ignore runs shorter than this


def _dir_mag(s):
    lx, ly = s["axes"].get("lx", 0.0), s["axes"].get("ly", 0.0)
    mag = math.hypot(lx, ly)
    if mag < DEADZONE:
        return None, 0.0
    return (math.degrees(math.atan2(lx, -ly)) + 360) % 360, mag


def walk_keys(direction):
    """Movement keys for a stick direction (0 = forward, 90 = right)."""
    keys = []
    if direction < 67.5 or direction >= 292.5:
        keys.append("walk_up")
    if 112.5 <= direction < 247.5:
        keys.append("walk_down")
    if 22.5 <= direction < 157.5:
        keys.append("walk_right")
    if 202.5 <= direction < 337.5:
        keys.append("walk_left")
    return keys


def runs(demo_dir):
    """Merge samples into runs of consistent stick state."""
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    live = [s for s in samples if _dir_mag(s)[0] is not None or abs(s["axes"].get("rx", 0)) > DEADZONE]
    if not live:
        return []
    out, cur = [], None
    for s in samples:
        d, m = _dir_mag(s)
        rx = s["axes"].get("rx", 0.0)
        key = (None if d is None else round(d / DIR_BUCKET),
               round(m / MAG_BUCKET),
               0 if abs(rx) < DEADZONE else (1 if rx > 0 else -1),
               round(abs(rx) / MAG_BUCKET))
        if cur and cur["key"] == key:
            cur["t1"] = s["t"]
        else:
            if cur:
                out.append(cur)
            cur = {"t0": s["t"], "t1": s["t"], "key": key,
                   "dir": d, "mag": m, "rx": rx}
    if cur:
        out.append(cur)
    return [r for r in out if r["t1"] - r["t0"] >= MIN_RUN
            and (r["dir"] is not None or abs(r["rx"]) > DEADZONE)]


def replay(demo_dir, hold, log=print):
    """hold(actions, seconds) presses those actions together, continuously."""
    rr = runs(demo_dir)
    if not rr:
        log("  nothing to replay")
        return
    total = sum(r["t1"] - r["t0"] for r in rr)
    log(f"  {len(rr)} runs, {total:.1f}s of recorded stick time")
    for r in rr:
        dur = r["t1"] - r["t0"]
        actions = walk_keys(r["dir"]) if r["dir"] is not None else []
        walk_secs = dur * min(1.0, r["mag"])          # <- the scaling
        turn = None
        if abs(r["rx"]) > DEADZONE:
            turn = "look_right" if r["rx"] > 0 else "look_left"
        turn_secs = dur * min(1.0, abs(r["rx"]))
        both = min(walk_secs, turn_secs) if (actions and turn) else 0.0
        if both > 0.01:
            hold(actions + [turn], both)
            if walk_secs > both:
                hold(actions, walk_secs - both)
            elif turn_secs > both:
                hold([turn], turn_secs - both)
        elif actions:
            hold(actions, walk_secs)
        elif turn:
            hold([turn], turn_secs)
    log("  done")
