"""Follow the recorded run as ONE continuous heading curve. No legs.

WHY SEGMENTATION WAS THE BUG
----------------------------
Earlier versions cut the recording into alternating "turn" and "walk" legs and
gave each turn leg an absolute bearing to face before the next walk. That looks
reasonable and matches how the player described the route ("aim, then move"),
but the recorded run does not actually stop between the two: the player walks
and turns at the same time, continuously.

Cutting a continuous sweep into legs means sampling a heading in the MIDDLE of
that sweep and then treating it as somewhere to stop and face. That is exactly
what went wrong: leg 3's target came out as 306 degrees while the player was
really at ~340 by the time they started walking, so the run began the next leg
33 degrees behind and never recovered. The frames confirm it — at the top of the
stairs the recording has the doorway centred and the replay has it off to the
right, by about the same 33 degrees the compass reported.

WHAT THIS DOES
--------------
One loop over the whole window. At each instant it takes the recorded left
stick (that is the travel) and servos the camera onto the recorded heading at
that same instant (that is the aim). Because the heading target is an absolute
compass bearing sampled continuously, yaw error cannot accumulate, and there is
never a moment where a stale mid-sweep bearing becomes a target.

The recorded RIGHT STICK is deliberately not replayed, but the recorded TURN
RATE is. Those are different things, and the difference is the whole trick.
Replaying stick samples was tried and made every score worse: this loop runs
slower than the 50Hz recording, so each camera sample gets held longer than the
player held it and integrates into far more rotation than they made. Degrees per
second, taken as the slope of the recorded heading curve, is a physical quantity
that does not care what rate the loop runs at — feeding it forward makes the
camera sweep at the speed the player swept, and leaves the error term with
nothing to do but trim.

Without that feed-forward the servo is purely reactive and therefore always
lagging. It cost the run at the top of the stairs: around t=11 to 12.5 the
recorded heading swings about 60 degrees quickly while the character is walking
DOWN A STAIRCASE, the servo fell 40 degrees behind, and the character descended
at the wrong angle. Everything after that tracked heading beautifully while
being in the wrong room, which is the signature of a positional error rather
than an aiming one.

HEADINGS HERE ARE ABSOLUTE BEARINGS. The route starts at the office spawn
facing the typewriter at 87 degrees and the first thing it does is sweep to 270
to face the door, then descends a staircase around t=11.7 before crossing to
the bar.
"""

import json
import os
import time

import analog_replay as ar
import compass
import turn_curve as tc
import visual_replay as vr

DEADBAND = 3.0             # degrees of heading error worth steering for
AIM_GATE = 12.0            # above this error the clock STOPS and the feet stop
GATE_LIMIT = 3.0           # seconds; never hold longer than this in one place
HORIZON = 0.25             # seconds to null an error over
MAX_STICK = 1.00           # the servo may use the full range; it is closed-loop
TICK = 0.02                # the recording's own rate


def _err(target, now):
    return (target - now + 540) % 360 - 180


def _want_at(pts, t):
    """Recorded bearing at time t, interpolated the short way round."""
    if t <= pts[0][0]:
        return pts[0][1]
    for (a, ha), (b, hb) in zip(pts, pts[1:]):
        if t <= b:
            f = 0.0 if b == a else (t - a) / (b - a)
            return (ha + _err(hb, ha) * f) % 360
    return pts[-1][1]


def _rate_at(pts, t, dt=0.15):
    """Slope of the recorded heading curve, in degrees per second."""
    return _err(_want_at(pts, t + dt), _want_at(pts, t - dt)) / (2 * dt)


def _pitch_over(samples, ta, tb, hint=0):
    """Stick value that reproduces the recording's PITCH change over [ta, tb].

    Pitch is the one axis with no feedback: the compass reports yaw only, so a
    wrong pitch is invisible to every check in this file and simply makes the
    camera point at the floor. Leaving right_y at zero, which earlier versions
    did, guarantees the mismatch — the player pitched the camera during the run
    and the replay never did.

    Replaying the recorded samples directly is wrong for the same reason it was
    wrong for yaw: this loop is slower than the recording, so each sample would
    be held too long. Instead integrate what the recording actually did over the
    interval and divide by how long this tick will last, which conserves the
    total movement rather than the instantaneous stick value.
    """
    if tb <= ta:
        return 0.0
    total = 0.0
    for i in range(max(0, hint - 4), min(len(samples) - 1, hint + 64)):
        a, b = samples[i], samples[i + 1]
        lo, hi = max(ta, a["t"]), min(tb, b["t"])
        if hi > lo:
            total += a["axes"].get("ry", 0.0) * (hi - lo)
    return total / (tb - ta)


def _stick_at(samples, t, hint=0):
    """Recorded sticks at time t. `hint` makes this O(1) for a forward scan.

    A linear scan from the start cost 4550 comparisons per tick, which — with a
    capture thread competing for the GIL — was enough to slow the loop past the
    point where its own corrections became unstable.
    """
    i = max(0, min(hint, len(samples) - 1))
    while i + 1 < len(samples) and samples[i + 1]["t"] <= t:
        i += 1
    while i > 0 and samples[i]["t"] > t:
        i -= 1
    return samples[i]["axes"], i


def follow(demo_dir, headings_path, t0=5.6, t1=25.2, capture_dir=None,
           log=print):
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    heads = json.load(open(headings_path))
    pts = [(h["t"], h["heading"]) for h in heads if t0 - 1 <= h["t"] <= t1 + 1]
    if not pts:
        raise RuntimeError("no recorded headings in this window")

    watcher = vr.FrameWatcher(compass.fast_capture).start()
    time.sleep(0.4)
    began = time.time()
    ticks = corrected = blind = gated = 0
    worst = 0.0
    shots = []
    t = t0
    last = time.time()
    held_for = 0.0
    idx = 0
    try:
        deadline = began + (t1 - t0) * 3 + 20
        while t < t1:
            if time.time() > deadline:
                log("  ABORTING: wall-clock budget exhausted; the run was "
                    "making no progress through the recording")
                break
            now = time.time()
            elapsed = now - last
            last = now
            ticks += 1
            a, idx = _stick_at(samples, t, idx)
            rx = 0.0
            img = watcher.img
            live = compass.read_bearing(img) if img is not None else None
            hold = False
            if live is None:
                # NO COMPASS MEANS DO NOT WALK. The reading fails in the dark
                # stairwell and under motion blur, and those were exactly the
                # stretches where position was being lost: with no bearing there
                # is no correction, so every blind step goes wherever the last
                # heading error was pointing and nothing ever notices. Holding
                # costs a moment; walking blind costs the run. Bounded by
                # GATE_LIMIT below so a permanently dark view cannot hang it.
                blind += 1
                if held_for < GATE_LIMIT:
                    hold = True
            else:
                e = _err(_want_at(pts, t), live)
                worst = max(worst, abs(e))
                # feed-forward the recorded sweep rate, then trim the error
                rate = _rate_at(pts, t)
                if abs(e) > DEADBAND:
                    # Size the correction for the tick that will ACTUALLY
                    # elapse. Nulling the error over a fixed 0.25s horizon
                    # assumes the loop runs faster than it does; when a tick
                    # takes longer than the horizon the correction overshoots,
                    # the next one overshoots back, and with a gate in the way
                    # the clock never advances again. That deadlocked a run at
                    # the very first turn.
                    rate += e / max(HORIZON, elapsed * 1.5)
                    corrected += 1
                if abs(rate) > 1e-6:
                    mag = min(MAX_STICK, tc.mag_for(abs(rate)))
                    rx = mag if rate > 0 else -mag
                # WALKING WHILE MIS-AIMED is what actually loses the route. The
                # heading always catches up a moment later, but the steps taken
                # in the meantime went somewhere else, and no amount of correct
                # aiming afterwards puts the character back. So when the aim is
                # badly off, stop the feet AND stop the clock: hold this instant
                # of the recording until the camera has caught up with it. The
                # player described doing exactly this — "I didn't move until the
                # reticle was on the door."
                if abs(e) > AIM_GATE and held_for < GATE_LIMIT:
                    hold = True
                    gated += 1
            lx = 0.0 if hold else a.get("lx", 0)
            ly = 0.0 if hold else a.get("ly", 0)
            # Pitch advances only when the clock does, so a hold does not
            # accumulate pitch the recording never had.
            ry = 0.0 if hold else max(-1.0, min(1.0,
                _pitch_over(samples, t, t + elapsed, idx)))
            ar.send([f"left_x {ar.to_axis(lx)}", f"left_y {ar.to_axis(ly)}",
                     f"right_x {ar.to_axis(rx)}", f"right_y {ar.to_axis(ry)}"])
            if hold:
                # A hold that never ends is a hang, not a correction. Give the
                # camera a bounded chance to catch up, then walk on regardless
                # — a slightly mis-aimed run still produces a diagnosable
                # result, whereas a frozen one produces nothing at all.
                held_for += elapsed
            else:
                held_for = 0.0
                t += elapsed
            if capture_dir and img is not None and (not shots or t - shots[-1] >= 1.0):
                img.save(os.path.join(capture_dir, f"t{t:06.2f}.jpg"), quality=85)
                shots.append(t)
            time.sleep(TICK)
    finally:
        ar.clear()
        watcher.stop()
    log(f"  {ticks} ticks over {time.time()-began:.1f}s wall "
        f"({t - t0:.1f}s of recording), steered {corrected}, held for aim "
        f"{gated}, compass lost {blind}, worst error {worst:.1f}")
    return worst


if __name__ == "__main__":
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    follow("demos/walk_20260827_214446", "/tmp/recorded_headings.json")
