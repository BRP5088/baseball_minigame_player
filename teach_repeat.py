"""Follow the recording by asking WHERE AM I IN IT, then doing what was done.

THE PROBLEM THIS SOLVES
-----------------------
Every route replay so far has been open loop in DISTANCE. Heading is servoed
exactly against the compass, so bearings land within a couple of degrees, but
nothing measures how far the character has actually travelled. Error accumulates
with no correction, and the same route ends at Wanda one run and elsewhere the
next.

The recording already contains the answer. If the live view can be matched
against the recorded frames, the best match says how far along the route the
character actually is — not how far it was supposed to be. Progress becomes
something measured rather than assumed.

WHY THE TIME WINDOW MATTERS
---------------------------
Matching against the WHOLE recording does not work: scanning it earlier showed
only 10 of 32 sampled moments are globally distinguishable, because the building
is full of repeated doorframes and similar corridors. A confident match on the
wrong one is worse than no match.

Restricting the search to frames near where the character is believed to be
removes almost all of that ambiguity. The route is not a maze — it does not
double back through the same view — so within a few seconds of the current
estimate the frames are genuinely different from one another. The estimate then
advances only as fast as the matching says it has, which is exactly the missing
feedback: if the character has not travelled, the best match does not move, and
it keeps walking.
"""

import glob
import json
import os
import time

import numpy as np
from PIL import Image

import analog_replay as ar
import compass
import visual_replay as vr
import walk_steps as ws

DEMO = "demos/walk3_full_20260828_050731"
HEADINGS = "route3_headings.json"
# Below this the match is not trustworthy. Measured: while genuinely on the
# route the best match scores 0.70-0.79; when the character has diverged it
# falls to 0.32-0.42. Advancing on a low score is how a run reported reaching
# the end of the recording while standing in a completely different room.
CONFIDENT = 0.55
DEAD_RECKON_LIMIT = 16     # ~5s of route walked without confirmation
BACK_WINDOW = 1.5          # seconds of the recording to look back over
FWD_WINDOW = 3.5           # and forward
STEP_SEC_SLOW = 0.30
STEP_SEC = 0.35
MIN_SPEED = 0.15


def load(demo=DEMO, headings=HEADINGS, t0=9.0, t1=62.5):
    frames = []
    for f in sorted(glob.glob(os.path.join(demo, "f_*.jpg"))):
        t = float(os.path.basename(f)[2:-4])
        if t0 <= t <= t1:
            frames.append((t, vr._strip(Image.open(f))))
    heads = {round(h["t"], 2): h["heading"] for h in json.load(open(headings))}
    samples = json.load(open(os.path.join(demo, "input.json")))
    return frames, heads, samples


def _match(live, frames, lo, hi):
    """(time, score) of the recorded frame the live view best resembles.

    The shift search is deliberately narrow. The camera is turned to the
    recorded heading before every step, so the live and recorded views start
    roughly aligned and a wide search only costs time — it was taking most of a
    second per step, which exhausted the run budget before the route was half
    walked.
    """
    a = vr._strip(live)
    best = (None, -2.0)
    for t, b in frames:
        if not (lo <= t <= hi):
            continue
        s = -2.0
        for dy in (-6, 0, 6):
            rb = np.roll(b, dy, axis=0)
            for dx in range(-24, 25, 4):
                v = float((a * np.roll(rb, dx, axis=1)).sum())
                if v > s:
                    s = v
        if s > best[1]:
            best = (t, s)
    return best


def _push(lx, ly, secs):
    ar.send([f"left_x {ar.to_axis(lx)}", f"left_y {ar.to_axis(ly)}",
             "right_x 0", "right_y 0"])
    time.sleep(secs)
    ar.send(["left_x 0", "left_y 0"])
    time.sleep(0.22)


def _heading_at(heads, t):
    keys = [k for k in heads if abs(k - t) < 0.6]
    return heads[min(keys, key=lambda k: abs(k - t))] if keys else None


def _next_moving(samples, t):
    """The next time in the recording where the player is actually walking."""
    import math
    for s in samples:
        if s["t"] <= t:
            continue
        a = s["axes"]
        if math.hypot(a.get("lx", 0.0), a.get("ly", 0.0)) >= MIN_SPEED:
            return s["t"]
    return None


def _travel_at(samples, t):
    import math
    near = min(samples, key=lambda s: abs(s["t"] - t))
    a = near["axes"]
    lx, ly = a.get("lx", 0.0), a.get("ly", 0.0)
    speed = math.hypot(lx, ly)
    if speed < MIN_SPEED:
        return None, 0.0
    h = _heading_at({}, 0)  # placeholder, world bearing computed by caller
    return math.degrees(math.atan2(lx, -ly)), speed


def relocalise(frames, t_est, floor, log=print):
    """Sweep the camera to re-acquire the route. Returns (t, score).

    A low match usually means the camera is pointing somewhere the recording
    never looked, not that the character is lost — so look around before
    concluding anything. Only if every direction scores badly is the run
    genuinely off the route.
    """
    h0 = compass.read_bearing(compass.fast_capture())
    best = (None, -2.0, None)
    for d in (0, -35, 35, -70, 70):
        if h0 is not None:
            ws.turn_to((h0 + d) % 360, log=lambda m: None)
        t, s = _match(compass.fast_capture(), frames,
                      max(t_est - BACK_WINDOW, floor), t_est + FWD_WINDOW)
        if s > best[1]:
            best = (t, s, (h0 + d) % 360 if h0 is not None else None)
        if s >= CONFIDENT:
            break
    if best[2] is not None:
        ws.turn_to(best[2], log=lambda m: None)
    log(f"      relocalised: best {best[1]:.3f}"
        + (f" at t~{best[0]:.2f}" if best[0] is not None else ""))
    return best[0], best[1]


def run(t_start=9.0, t_end=62.0, budget=600.0, log=print):
    frames, heads, samples = load()
    t_est = t_start
    floor = t_start
    began = time.time()
    stalls = 0
    lost = 0
    while t_est < t_end and time.time() - began < budget:
        live = compass.fast_capture()
        # The lower bound never drops below `floor`. Without it the estimate
        # can be pulled BACK into a pause that was just skipped, which then
        # skips forward again, matches back, and loops forever — that stalled a
        # run at t~25 doing nothing but skipping the same pause.
        t_match, score = _match(live, frames,
                                max(t_est - BACK_WINDOW, floor),
                                t_est + FWD_WINDOW)
        if t_match is None:
            log("      no frames in window")
            break
        if score < CONFIDENT:
            t_match, score = relocalise(frames, t_est, floor, log=log)
            if t_match is None or score < CONFIDENT:
                # DEAD-RECKON, briefly. Parts of this route are genuinely
                # unmatchable: scanning the recording for visually distinctive
                # moments found NONE between t=14.7 and 20.8, because the
                # corridor and stairwell are dark and repetitive. Refusing to
                # move without a confident match simply stops the run there.
                #
                # So keep walking the recorded actions, but COUNT how long it
                # has been since the route was last confirmed. A few seconds of
                # blind progress through a known-ambiguous stretch is fine; the
                # danger is only in doing it indefinitely, which is how a run
                # ended in the wrong room believing it had arrived.
                lost += 1
                if lost > DEAD_RECKON_LIMIT:
                    log(f"      lost for {lost} steps ({score:.3f}); stopping "
                        "rather than walking on blind")
                    break
                log(f"      unmatched ({score:.3f}); dead-reckoning "
                    f"{lost}/{DEAD_RECKON_LIMIT}")
                t_match = t_est + STEP_SEC
                score = 0.0
            else:
                lost = 0
        advanced = t_match - t_est
        t_est = t_match
        stalls = stalls + 1 if advanced < 0.05 else 0
        floor = max(floor, t_est - BACK_WINDOW)

        stick_angle, speed = _travel_at(samples, t_est)
        cam = _heading_at(heads, t_est)
        if cam is None or stick_angle is None:
            # A PAUSE in the recording. The player stood still here, so there is
            # nothing to reproduce and no reason to spend a capture-and-match
            # cycle on every 0.3s of it. Jump straight to where they started
            # moving again — crawling through a 6.5 second pause a third of a
            # second at a time burned most of the run's budget before it had
            # left the first corridor.
            nxt = _next_moving(samples, t_est)
            if nxt is None:
                break
            log(f"      pause at t~{t_est:.2f}; skipping to {nxt:.2f}")
            t_est = nxt
            floor = nxt          # never fall back into a pause already skipped
            continue
        world = (cam + stick_angle) % 360
        ws.turn_to(world, log=lambda m: None)
        moved = ws.walk_forward(speed, STEP_SEC)
        if moved < ws.STUCK_CHANGE:
            ws.unstick(speed, STEP_SEC, log=lambda m: None)
        log(f"      t~{t_est:5.2f} (match {score:.3f}, advanced {advanced:+.2f}s) "
            f"bearing {world:6.1f} moved {moved:5.1f}")
        if stalls and stalls % 3 == 0:
            # Repeated stalls mean something physical is in the way — a
            # doorframe, furniture, or an NPC standing on the route. Crabbing
            # sideways for a fraction of a second is not enough to clear a body;
            # this backs off properly and tries a wide berth on alternating
            # sides before giving up on the spot.
            side = 1.0 if (stalls // 3) % 2 else -1.0
            log(f"      blocked at t~{t_est:.2f}; wide escape to the "
                f"{'right' if side > 0 else 'left'}")
            _push(0.0, 0.55, 0.55)                 # back off
            _push(side * 0.85, 0.0, 1.0)           # clear sideways
            _push(0.0, -0.45, 0.5)                 # advance past the obstacle
        if stalls >= 12:
            log("      not making progress through the recording; stopping")
            break
    ar.clear()
    return t_est
