"""Replay the recorded input list directly. No reconstruction.

WHY THIS EXISTS
---------------
Earlier replays decoded headings from the frames, derived turn rates, fitted an
arc-efficiency constant, and steered toward a reconstructed trace. All of that
infers what the player MEANT. The input log already records what they DID.

The only genuine gap is analog vs binary: the recording holds the stick at 0.54
and a keyboard key is down or up. That is handled by duty-cycling — a key held
for 54% of each slice — and nothing else needs inferring.

MAPPING (game is camera-relative, so left stick direction is relative to facing)
    left stick   -> walk_up / walk_down / walk_left / walk_right, by direction
    right stick x-> look_left / look_right, held proportional to |rx|
    buttons      -> pressed as recorded, EXCEPT the ones below

NEVER REPLAYED, whatever the recording contains:
    square  — spends $50 at the Baseball Cards prompt
    options — opens the pause menu, which would derail the run
The recording of 2026-08-27 contains 16 `cross` presses, all from reloading the
save before the walk; those fall outside the walking window and are not replayed
either.
"""

import json
import math
import os
import time

SLICE_SEC = 0.1           # replay granularity
DEADZONE = 0.15
NEVER_PRESS = {"square", "options", "ps", "touchpad", "share", "mic"}


def load(demo_dir):
    return json.load(open(os.path.join(demo_dir, "input.json")))


def walking_window(samples, deadzone=DEADZONE):
    live = [s["t"] for s in samples
            if math.hypot(s["axes"].get("lx", 0), s["axes"].get("ly", 0)) > deadzone]
    return (live[0], live[-1]) if live else (None, None)


def slice_state(samples, t, dt):
    """Average stick state over [t, t+dt) — what to command for this slice."""
    win = [s for s in samples if t <= s["t"] < t + dt]
    if not win:
        return None
    n = len(win)
    return {
        "lx": sum(s["axes"].get("lx", 0) for s in win) / n,
        "ly": sum(s["axes"].get("ly", 0) for s in win) / n,
        "rx": sum(s["axes"].get("rx", 0) for s in win) / n,
        "buttons": {b for s in win for b in s["buttons"]} - NEVER_PRESS,
    }


def walk_keys(lx, ly):
    """Which movement keys correspond to this stick position."""
    mag = math.hypot(lx, ly)
    if mag < DEADZONE:
        return [], 0.0
    # 0 deg = forward (-ly), 90 = right (+lx)
    ang = (math.degrees(math.atan2(lx, -ly)) + 360) % 360
    keys = []
    if ang < 67.5 or ang >= 292.5:
        keys.append("walk_up")
    if 112.5 <= ang < 247.5:
        keys.append("walk_down")
    if 22.5 <= ang < 157.5:
        keys.append("walk_right")
    if 202.5 <= ang < 337.5:
        keys.append("walk_left")
    return keys, min(1.0, mag)


def replay(demo_dir, hold, log=print):
    """hold(keys, seconds) presses those keys together for that long."""
    samples = load(demo_dir)
    t0, t1 = walking_window(samples)
    if t0 is None:
        log("  no stick movement to replay")
        return
    log(f"  replaying input {t0:.1f}s..{t1:.1f}s ({t1 - t0:.1f}s)")
    t = t0
    while t < t1:
        st = slice_state(samples, t, SLICE_SEC)
        if st:
            keys, mag = walk_keys(st["lx"], st["ly"])
            turn = None
            if abs(st["rx"]) > DEADZONE:
                turn = "look_right" if st["rx"] > 0 else "look_left"
            # duty-cycle each channel by how far its stick was pushed
            walk_secs = SLICE_SEC * mag
            turn_secs = SLICE_SEC * min(1.0, abs(st["rx"]))
            both = min(walk_secs, turn_secs) if (keys and turn) else 0.0
            if both > 0.005:
                hold(keys + [turn], both)
                if walk_secs > both:
                    hold(keys, walk_secs - both)
                elif turn_secs > both:
                    hold([turn], turn_secs - both)
            elif keys:
                hold(keys, walk_secs)
            elif turn:
                hold([turn], turn_secs)

            # PAD THE SLICE. Duty-cycling holds the key for only part of the
            # slice; without waiting out the rest, the whole replay runs fast
            # AND under-walks. Measured: 10.1s of wall clock for 15.5s of
            # recording, i.e. a third of the walk simply never happened.
            spent = max(walk_secs, turn_secs)
            if spent < SLICE_SEC:
                time.sleep(SLICE_SEC - spent)
        t += SLICE_SEC
    log("  done")
