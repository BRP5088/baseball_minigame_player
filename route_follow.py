"""Walk the recorded route by FOLLOWING ITS HEADING TRAJECTORY.

WHY THIS IS DIFFERENT FROM EVERY EARLIER REPLAY
-----------------------------------------------
Replaying the recorded sticks open-loop drifts: a small yaw error early becomes
a wrong room later, and nothing in the loop ever notices. Correcting to a single
final heading does not help either, because the error that matters accumulates
DURING the walk, not at the end of it.

The recording, though, contains an absolute heading for almost every frame — the
compass is readable on 299 of 533 frames. So the run is not just a list of stick
values, it is a heading-versus-time curve. This follows that curve: at ~14Hz it
reads the live compass, compares it with where the recording was pointing at the
same moment in the leg, and steers the difference away while the left stick
pushes at the recorded magnitude.

Yaw therefore cannot accumulate error — it is servoed against an absolute
reference the whole way. What is NOT closed-loop is distance: how far the
character travels still comes from replaying the recorded stick magnitude for
the recorded duration. That is the remaining source of divergence, and it is
why walk legs are checked for hazards afterwards rather than trusted.

HEADINGS ARE ABSOLUTE COMPASS BEARINGS, not turn amounts. The route starts at
the office spawn facing the typewriter at 87 degrees, and the first move is a
+183 degree turn CLOCKWISE to 270 to face the door — writing that down as "turn
183" rather than "face 270" is how an earlier attempt ended up facing the wrong
way and confidently walking into the wrong room.
"""

import json
import math
import os
import time

import analog_replay as ar
import compass
import turn_curve as tc
import visual_replay as vr

CORRECT_DEADBAND = 8.0     # degrees of heading error tolerated before steering
CORRECT_HORIZON = 0.80     # seconds to null a heading error over
MAX_CORRECTION = 0.55      # never let a correction dominate the player's input
TURN_TOLERANCE = 4.0
TURN_MAX_STEPS = 14


def _err(target, now):
    return (target - now + 540) % 360 - 180


def read_heading(tries=3):
    for _ in range(tries):
        b = compass.read_bearing(compass.fast_capture())
        if b is not None:
            return b
    return None


def turn_to(target, log=print, tolerance=TURN_TOLERANCE):
    """Turn to an ABSOLUTE bearing, closed-loop on the compass."""
    for _ in range(TURN_MAX_STEPS):
        now = read_heading()
        if now is None:
            break
        e = _err(target, now)
        if abs(e) <= tolerance:
            return now
        mag, secs = tc.plan_turn(e)
        if mag == 0.0:
            break
        ar.send([f"right_x {ar.to_axis(mag if e > 0 else -mag)}",
                 "right_y 0", "left_x 0", "left_y 0"])
        time.sleep(secs)
        ar.send(["right_x 0"])
        time.sleep(0.30)
    now = read_heading()
    if now is not None:
        log(f"      turn ended at {now:.1f} (wanted {target:.1f}, "
            f"off {_err(target, now):+.1f})")
    return now


def _profile(headings, t0, t1):
    """The recorded heading curve for one leg, as (relative_time, bearing)."""
    pts = [(h["t"] - t0, h["heading"]) for h in headings if t0 <= h["t"] <= t1]
    return pts or None


def _want_at(pts, rel):
    """Recorded bearing at this point in the leg, interpolated."""
    if rel <= pts[0][0]:
        return pts[0][1]
    for (a, ha), (b, hb) in zip(pts, pts[1:]):
        if rel <= b:
            f = 0.0 if b == a else (rel - a) / (b - a)
            return (ha + _err(hb, ha) * f) % 360
    return pts[-1][1]


def _sample_at(samples, rel):
    """The player's own stick values at this point in the leg."""
    if rel <= samples[0]["dt"]:
        return samples[0]
    for a, b in zip(samples, samples[1:]):
        if rel <= b["dt"]:
            return a
    return samples[-1]


def walk_leg(lx, ly, seconds, pts, log=print, label="", samples=None,
             watcher=None):
    """Replay the player's own sticks, correcting only for accumulated drift.

    FEED-FORWARD PLUS FEEDBACK, and the split matters. The player's recorded
    right stick is the feed-forward term: on legs where they walked and turned
    at once, that turn IS the route, and an earlier version of this function
    discarded it and steered purely on heading error instead. The servo then
    spent the whole leg fighting a turn the recording was deliberately making —
    leg 4 corrected on 13 of 13 ticks, ended 33 degrees off, and was the first
    leg to diverge from the recording.

    The compass correction is now only a trim on top, with a wider deadband and
    a gentler horizon, so it removes drift without overriding intent.

    The capture runs in a BACKGROUND thread. Reading the compass inline capped
    the loop at 14Hz, which meant replaying a 50Hz recording at a third of its
    rate — every stick value held three times too long. The loop now runs at the
    recording's own rate and simply uses the newest frame available.
    """
    began = time.time()
    corrected = blind = ticks = 0
    worst = 0.0
    while True:
        rel = time.time() - began
        if rel >= seconds:
            break
        ticks += 1
        if samples:
            s = _sample_at(samples, rel)
            cur_lx, cur_ly, rx, ry = s["lx"], s["ly"], s["rx"], s["ry"]
        else:
            cur_lx, cur_ly, rx, ry = lx, ly, 0.0, 0.0

        if pts:
            img = watcher.img if watcher is not None else compass.fast_capture()
            live = compass.read_bearing(img) if img is not None else None
            if live is None:
                blind += 1
            else:
                e = _err(_want_at(pts, rel), live)
                worst = max(worst, abs(e))
                if abs(e) > CORRECT_DEADBAND:
                    mag = min(MAX_CORRECTION, tc.mag_for(abs(e) / CORRECT_HORIZON))
                    rx = max(-1.0, min(1.0, rx + (mag if e > 0 else -mag)))
                    corrected += 1
        ar.send([f"left_x {ar.to_axis(cur_lx)}", f"left_y {ar.to_axis(cur_ly)}",
                 f"right_x {ar.to_axis(rx)}", f"right_y {ar.to_axis(ry)}"])
        time.sleep(0.02)          # the recording's own ~50Hz rate
    ar.send(["left_x 0", "left_y 0", "right_x 0", "right_y 0"])
    log(f"      {label}: {ticks} ticks, trimmed {corrected}, "
        f"compass lost {blind}, worst heading error {worst:.1f}")
    return worst


def run(legs_path="/tmp/legs.json", headings_path="/tmp/recorded_headings.json",
        log=print):
    legs = json.load(open(legs_path))
    headings = json.load(open(headings_path))
    start = read_heading()
    log(f"  starting at {start:.1f}" if start is not None else "  no compass")
    watcher = vr.FrameWatcher(compass.fast_capture).start()
    time.sleep(0.4)

    for i, leg in enumerate(legs, 1):
        if leg["kind"] == "turn":
            if leg["h1"] is None:
                continue
            log(f"    [{i}] TURN to {leg['h1']:.1f}")
            turn_to(leg["h1"], log=log)
        else:
            pts = _profile(headings, leg["t0"], leg["t1"]) if "t0" in leg else None
            log(f"    [{i}] WALK {leg['dur']:.2f}s stick=({leg['lx']:.2f},"
                f"{leg['ly']:.2f})")
            walk_leg(leg["lx"], leg["ly"], leg["dur"], pts, log=log,
                     label=f"leg{i}", samples=leg.get("samples"), watcher=watcher)
    watcher.stop()
    ar.clear()
    end = read_heading()
    log(f"  finished at {end:.1f}" if end is not None else "  finished, no compass")
    return end


if __name__ == "__main__":
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    run()
