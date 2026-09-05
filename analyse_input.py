"""Pair recorded controller input with what the game did, and segment it.

    python3 analyse_input.py demos/walk_<stamp>

INPUT (60Hz) says what was COMMANDED: stick direction and how far pushed.
FRAMES (6fps) say what RESULTED: heading from the compass, movement from the
picture changing.

Having both is the point. Every route before this was reconstructed from
results alone, and the reconstruction was wrong in a specific way: an
eleven-second stretch of constant heading was read as "stand still facing 88"
when the left stick was pushed forward the whole time. The stick says outright
which it was.

STICK CONVENTION (measured on this controller):
    ly = -1.0 fully forward, +1.0 back;  lx = -1.0 left, +1.0 right
"""

import json
import math
import os
import sys

DEADZONE = 0.15
MOVING_DELTA = 6.0


def load(demo_dir):
    inputs = json.load(open(os.path.join(demo_dir, "input.json")))
    tl_path = os.path.join(demo_dir, "timeline.json")
    frames = json.load(open(tl_path)) if os.path.exists(tl_path) else None
    return inputs, frames


def stick(sample):
    """(magnitude, direction_deg) of the left stick. 0 deg = forward."""
    lx, ly = sample["axes"].get("lx", 0.0), sample["axes"].get("ly", 0.0)
    mag = math.hypot(lx, ly)
    if mag < DEADZONE:
        return 0.0, None
    # forward is -ly, right is +lx; 0 deg = forward, 90 = right
    return mag, (math.degrees(math.atan2(lx, -ly)) + 360) % 360


def segment(inputs, min_sec=0.3):
    """Group input samples into stretches with a consistent left-stick command."""
    segs, cur = [], None
    for s in inputs:
        mag, direction = stick(s)
        walking = mag > 0
        key = None if not walking else round(direction / 15.0)
        if cur and cur["walking"] == walking and cur["key"] == key:
            cur["t1"] = s["t"]
            cur["mags"].append(mag)
            if direction is not None:
                cur["dirs"].append(direction)
            cur["buttons"] |= set(s["buttons"])
        else:
            if cur:
                segs.append(cur)
            cur = {"t0": s["t"], "t1": s["t"], "walking": walking, "key": key,
                   "mags": [mag], "dirs": [direction] if direction is not None else [],
                   "buttons": set(s["buttons"])}
    if cur:
        segs.append(cur)
    return [s for s in segs if s["t1"] - s["t0"] >= min_sec]


def heading_at(frames, t):
    if not frames:
        return None
    dec = [(f["t"], f["heading"]) for f in frames if f.get("heading") is not None]
    if not dec:
        return None
    near = min(dec, key=lambda d: abs(d[0] - t))
    return near[1] if abs(near[0] - t) < 1.0 else None


def report(demo_dir):
    inputs, frames = load(demo_dir)
    segs = segment(inputs)
    print(f"  {len(inputs)} input samples, "
          f"{len(frames) if frames else 0} analysed frames")
    print(f"  {len(segs)} segments >= 0.3s\n")
    print(f"  {'from':>6} {'to':>6} {'secs':>5} {'stick':>18} "
          f"{'head@start':>10} {'head@end':>9}  buttons")
    for s in segs:
        dur = s["t1"] - s["t0"]
        if s["walking"]:
            mag = sum(s["mags"]) / len(s["mags"])
            d = sum(s["dirs"]) / len(s["dirs"])
            desc = f"{mag:.2f} @ {d:5.1f} deg"
        else:
            desc = "(no stick)"
        h0, h1 = heading_at(frames, s["t0"]), heading_at(frames, s["t1"])
        b = ",".join(sorted(s["buttons"])) if s["buttons"] else ""
        print(f"  {s['t0']:6.2f} {s['t1']:6.2f} {dur:5.2f} {desc:>18} "
              f"{('--' if h0 is None else f'{h0:10.1f}')} "
              f"{('--' if h1 is None else f'{h1:9.1f}')}  {b}")
    return segs


if __name__ == "__main__":
    report(sys.argv[1])
