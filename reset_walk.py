"""The walk from the save-point typewriter back to the baseball minigame.

ROUTE (dictated by the user, 2026-08-26):

    turn 180                       (face away from the typewriter)
    forward 3.5s
    turn right 90
    forward 5s                     down the steps, through the doorway
      -> CHECKPOINT: the "Little & Big" / L&B building should be visible
    forward 4s                     towards it
    turn left 90
    forward 3s
    turn right 90
    forward 3.5s
    turn right 90
      -> CHECKPOINT: a lady sitting at a table should be visible
    forward 3s
      -> CHECKPOINT: the normal "start game" text should be showing

WHY THE CHECKPOINTS MATTER MORE THAN THE TIMINGS
------------------------------------------------
The walk does not need to be reliable. It needs to be VERIFIABLE. Dead
reckoning over ~25 seconds of movement will drift — a slightly different
camera angle, a snagged corner, a frame-rate dip during the turn — and no
amount of tuning removes that. What makes it usable anyway is that a failed
walk costs nothing: nobody is hurt by the detective standing in the wrong
corridor. So the design is:

    attempt the route -> check a landmark -> if it is not there, STOP and
    hand back, rather than pressing on and eventually mashing "play match"
    at a wall.

An 80%-reliable walk with 100%-reliable checkpoints is a working system. A
100%-reliable walk with no checkpoints is one patch away from silently
breaking.

TURNS ARE CLOSED-LOOP, NOT TIMED
--------------------------------
The world HUD carries a COMPASS BAR across the top, and the screen centre is
the current heading — reference frames supplied 2026-08-26 read:

    typewriter spawn      centre ~ E
    cafe / lady at table  centre ~ E
    bar interior          centre ~ W
    Little & Big exterior centre ~ N
    stairs and doorway    centre ~ N

That is an ABSOLUTE bearing, readable from a single frame, which makes timed
turns unnecessary: hold the right stick until the compass reaches the target
and stop. No TURN_90_SEC to measure, and — more importantly — immune to the
thing that breaks dead reckoning, which is that a frame-rate dip or a snagged
corner silently changes how far a fixed hold actually turns you.

Walking still has to be timed (there is no odometer), so drift remains
possible in the straight legs. That is what the checkpoints are for.

WHAT IS STILL UNKNOWN
---------------------
* The compass box in CAPTURE coordinates. The supplied frames are the chiaki
  window; capture_screenshot_image() grabs the whole desktop. Needs one live
  capture to locate.
* How to read a bearing out of that strip. It is a tick scale with N/E/S/W
  glyphs, so it is a template-match or OCR problem, not arithmetic.
* Whether walking legs need tuning. The durations below are the user's own
  estimates ("about", "ish").
"""

# Target BEARINGS rather than turn durations — see the module docstring. The
# route is expressed as "face this way", which is self-correcting: if a leg
# drifts, the next turn still ends up pointing the right way.
#
# Bearings observed in the reference frames. The spawn faces E; the route ends
# facing the cafe table, also E.
SPAWN_BEARING = "E"

# Kept only so a timed fallback is possible if the compass proves unreadable.
# UNMEASURED — and if it is ever needed, measure it AGAINST the compass rather
# than by eye.
TURN_90_SEC = None

# Seconds of held left-stick-up per "walk N seconds" leg, straight from the
# route description. These are the user's own estimates ("about", "ish"), so
# treat them as starting values to be tuned against the checkpoints, not as
# measurements.
# RECOVERED FROM A HUMAN DEMONSTRATION, not dictated. The earlier route was a
# verbal description ("turn right 90, walk 3 seconds") totalling ~25s of
# walking across seven turns, and it never arrived — because it never went
# INDOORS. The baseball table is inside the Little & Big building: through the
# front door, past a bar with stools and a dartboard, past a curtained archway,
# into the dining room. The real walk is about 7 seconds.
#
# Legs are ABSOLUTE bearings, not relative turns. The spawn POSITION is
# reproducible (the spawn HEADING is not — measured 57 to 91 degrees across
# resets), and the heading is read rather than assumed
# and walking cannot disturb a heading (measured: 0.5 degrees across nine
# presses), so aiming at an absolute bearing makes every leg self-correcting —
# a leg that comes out crooked cannot poison the next one.
#
# Bearings below are as this compass reads them in FULLSCREEN, where the macOS
# dock is not in the capture. Windowed, every reading ran ~8.5 degrees high
# because the dock pushed the apparent view centre 28px right of the real one.
# NOT a constant the reset guarantees — measured 57, 87, 89, 90, 91 across
# clean resets. Kept only as a rough sanity bound for "are we plausibly at the
# typewriter", never as an anchor to correct a reading against.
SPAWN_FACING = 87.0
SPAWN_FACING_TOLERANCE = 45.0

# TRAVEL legs, not turn-then-walk legs.
#
# ("travel", bearing, seconds) means: go in that ABSOLUTE compass direction for
# that long, whatever way the camera happens to point. Movement is
# camera-relative and W/A/S/D cover eight directions, blended for anything in
# between, so the travel direction is continuous — while AIMING the camera is
# stuck at a ~28 degree quantum (measured fullscreen: the smallest commandable
# turn moves a median 28 degrees, spread 18-51).
#
# That distinction is what unblocks this route. Previously every leg had to
# turn first, so a leg could start up to 28 degrees off and walk that error the
# whole way — into a wall. Now the heading only has to be READ (accurate to
# ~2 degrees), never aimed, and the error in travel direction is the error in
# the reading rather than in the actuator.
#
# The single "face" leg at the end is the exception: the interaction prompt
# only shows when the camera looks at the table, and that is the one place
# coarse aiming is good enough.
ROUTE = [
    # RECOVERED FROM THE FULLSCREEN DEMONSTRATION, segmenting moving frames
    # from stationary ones. The previous route was 6.7s across 3 legs, taken
    # from the WINDOWED recording where the walker's deliberate pauses were
    # mistaken for the legs themselves — so it replayed a fraction of the
    # actual distance and never left the building. The real walk is 19.4s of
    # movement across 6 legs.
    ("travel", 272.2, 2.68, None),              # office hallway, west to the door
    ("travel", 2.5, 6.99, "lb_building"),       # through the door, north to the street
    ("travel", 357.9, 4.25, None),              # across the street, through the archway
    ("travel", 329.3, 0.94, None),              # inside L&B, past the bar
    ("travel", 313.3, 1.08, None),              # deeper into the bar room
    ("travel", 74.0, 3.45, "start_game_text"),  # east to the Baseball Cards table
]

# Landmarks the route passes. Each must be recognisable from a single frame.
# `start_game_text` is the one that already exists — the match-start prompt the
# orchestrator reads every session — so the final checkpoint is free.
CHECKPOINTS = {
    "lb_building": "the Little & Big (L&B) building is visible ahead",
    "lb_interior": "inside L&B — bar stools, dartboard, curtained archway",
    "start_game_text": "the 'Baseball Cards / Play ($50)' prompt is showing",
}


HEADING_REREAD_SEC = 3.5    # the heading only changes when WE change it
UNWEDGE_ATTEMPTS = 4        # back off and sidestep before declaring failure
UNWEDGE_BACK_SEC = 0.35
UNWEDGE_SIDE_SEC = 0.40
STUCK_MIN_CHUNK_SEC = 0.5   # shorter than this gives no reliable signal
# Frame delta is the movement signal. It is reliable for "did I move" —
# sustained travel reads 15-34, jammed reads 0.8-2.0 — but NOT for choosing a
# direction: walking toward a lit wall sconce scored 60 while covering almost
# no ground, and a navigator that picked the largest delta optimised itself
# into the lamp. Direction comes from the landmark; delta only says whether the
# step worked.
#
# OPTICAL FLOW WAS TRIED AS A REPLACEMENT AND REJECTED. It measures camera
# motion of any kind, and this is a third-person camera that orbits the
# character on a multi-metre arc, so TURNING scored higher flow (median 6.76)
# than real walking (2.00) on labelled demo frames. It cannot separate
# rotation from translation here.
STUCK_DELTA = 2.0           # forward motion changes the frame by ~3.9
STUCK_LIMIT = 2             # consecutive dead segments before giving up
AIM_TOLERANCE_DEG = 35.0        # good enough to SEE by; steering uses vectors
HEADING_JUMP_TOL_DEG = 30.0     # travel cannot turn you; a jump is a misread


def read_heading_near(cap, expected, log=None, tries=6, tol=HEADING_JUMP_TOL_DEG):
    """A bearing consistent with `expected`, or None.

    Rejects the one failure the compass cannot catch on its own: a UNIFORM
    LABELLING SHIFT. If every letter on the bar is read one position round
    (N as E, E as S...), the implied bearings all agree with each other AND
    with the scale derived from them, so consensus, spacing and plausibility
    checks all pass on an answer exactly 90 degrees wrong. Live, a spawn that
    every other reset read as 87-91 came back as 177, and the route then walked
    perpendicular to itself.

    What catches it is knowledge from outside the frame:
      * the spawn heading varies (57-91 measured) but stays within a wide
        band, so a reading far outside it is suspect even though a reading
        inside it cannot be trusted precisely;
      * walking cannot change a heading (measured 0.5 degrees over nine
        presses), so during a travel leg the heading must not move.
    Either way there is an expected value, and a reading 90/180/270 off it is
    not a heading that changed — it is a misread.
    """
    import compass

    seen = []
    for _ in range(tries):
        b = compass.read_bearing_stable(cap)
        if b is None:
            continue
        if abs(compass.angular_error(expected, b)) <= tol:
            return b
        seen.append(round(b))
    if log and seen:
        log(f"      rejected {seen} — none within {tol:.0f} of "
            f"{compass.describe(expected)} (labelling shift)")
    return None


def _check_landmark(name, img):
    """True/False if a detector exists and is confident, else None.

    WHY THIS IS NOT OPTIONAL
    ------------------------
    walk_route used to print "CHECKPOINT start_game_text: the prompt is
    showing" and carry on — with no detector behind it. It printed exactly that
    while standing in front of a blank wall. A checkpoint that cannot fail is
    not a checkpoint; it is a comment that makes a failed run look identical to
    a successful one, and it made every test run uninterpretable.

    Returning None (unverified) is honest and stays loud in the log. Returning
    False stops the walk, because the whole design of this route is that a
    failed walk should cost nothing and hand back rather than press on.
    """
    try:
        import landmarks
    except ImportError:
        return None
    fn = {
        "start_game_text": getattr(landmarks, "at_baseball_table", None),
        "lb_building": getattr(landmarks, "sees_lb_building", None),
        "lb_interior": getattr(landmarks, "in_lb_interior", None),
    }.get(name)
    if fn is None:
        return None
    try:
        return fn(img)
    except Exception:
        return None


# How long the camera needs to stop coasting after a turn, and how far off
# target a leg may start before it is worth re-aiming. Walking on a heading
# that is tens of degrees out is the difference between a doorway and a wall.
SETTLE_BEFORE_WALK_SEC = 1.2
SEGMENT_SEC = 1.1           # walk this long before checking the heading again
REAIM_TOLERANCE_DEG = 15.0


class WalkError(RuntimeError):
    """Raised when the walk cannot continue safely."""


def walk_route(log=print, route=None, legs=None, save_dir=None):
    """Execute the route. Returns the final bearing.

    Turns are ABSOLUTE-corrected: the route stores a relative delta, but each
    turn re-reads the compass and aims at (current + delta), so a leg that came
    out crooked does not poison the next one. Walking cannot disturb a heading
    (measured: 0.5 degrees across nine presses), so the only thing a bad leg
    costs is position, which is what the checkpoints are for.

    Raises WalkError rather than pressing on blindly. A walk that has drifted is
    harmless; a walk that drifts and then keeps mashing buttons is not.
    """
    import time

    import compass
    import input_controller as ic
    import orchestrator as o

    route = ROUTE if route is None else route
    if legs is not None:
        route = route[:legs]

    def cap():
        # compass.fast_capture, not orchestrator.capture_screenshot_image:
        # MEASURED 111ms against 3058ms. The slow one re-focuses the chiaki
        # window over an osascript round trip and sleeps 150ms before grabbing,
        # which is right when we are about to PRESS something and pointless
        # when we are only looking. Paying it on every iteration of a closed
        # loop is what made turning look like aimless glancing around.
        return compass.fast_capture()

    def guard(step):
        if not ic.has_focus():
            raise WalkError(f"step {step}: chiaki is not frontmost "
                            f"({ic.frontmost_app()!r} is) — input is going "
                            f"somewhere else")
        # NOT gated on the reticle. Its presence proves gameplay, but its
        # ABSENCE proves nothing: looking at a dark door frame produces no
        # reticle while the compass reads fine and the camera turns normally.
        # Gating here aborted a valid walk at step 2. turn_to's dead-press
        # check is the real guard — it measures whether input had an effect
        # rather than inferring it from a HUD element.
        return cap()

    bearing = None
    since_read = HEADING_REREAD_SEC      # force a read before the first move
    for i, step in enumerate(route, 1):
        kind, amount, secs, check = step
        frame = guard(i)

        if kind == "until_blocked":
            # Walk until the character JAMS. Being pressed against geometry is
            # a repeatable position; a stopwatch is not. Replaying the office
            # leg by its measured duration left the character short of the
            # door and the whole route diverged from there, while jamming
            # against it reproduced twice running.
            here = compass.read_bearing_stable(cap, log=log)
            if here is None and bearing is not None:
                here = bearing
            if here is None:
                raise WalkError(f"step {i}: no heading to walk on")
            if abs(compass.angular_error(here, amount)) > AIM_TOLERANCE_DEG:
                aimed = compass.turn_to(amount, ic.press, cap, log=log)
                if aimed is not None:
                    here = read_heading_near(cap, aimed, log=log) or aimed
            bearing = here
            rel = compass.angular_error(here, amount)
            done, jammed = 0.0, 0
            # `here` is guaranteed non-None above; the rel is computed ONCE and
            # reused. Recomputing it per segment from a fresh read crashes the
            # moment a read abstains — which happens routinely when an NPC
            # stands close enough to cover the compass bar. Walking cannot
            # change a heading, so one computation is also the correct one.
            import numpy as _np
            while done < secs - 0.01:
                before = _np.asarray(cap().convert("L"), dtype=float)
                ic.walk_at(rel, 0.7)
                time.sleep(0.3)
                done += 0.7
                d = float(_np.abs(_np.asarray(cap().convert("L"), dtype=float)
                                  - before).mean())
                jammed = jammed + 1 if d < STUCK_DELTA else 0
                if jammed >= 2:
                    break
            log(f"  {i:2}. until_blocked {amount:.0f} -> jammed after {done:.1f}s")

        elif kind == "travel":
            here = compass.read_bearing_stable(cap, log=log)
            if here is None and bearing is not None:
                log(f"      compass unreadable — carrying {compass.describe(bearing)}")
                here = bearing
            if here is None:
                raise WalkError(f"step {i}: no heading, and none carried over — "
                                f"refusing to move blind")
            bearing = here
            # AIM COARSELY FIRST, then travel by vector.
            #
            # These solve different problems and both are needed. Travelling by
            # vector makes the PATH precise without accurate aiming. But the
            # landmark detectors read what the CAMERA sees, and with the camera
            # left pointing at the spawn heading the whole route, none of them
            # can confirm anything — the first vector-only run travelled with
            # the camera facing 87 for every leg and saw nothing.
            #
            # Aiming is only ~28 degrees accurate, which is useless for steering
            # but perfectly good for LOOKING: a building 28 degrees off centre
            # is still plainly in frame. So point roughly along the leg, then
            # let the vector correct whatever the aim got wrong.
            if abs(compass.angular_error(bearing, amount)) > AIM_TOLERANCE_DEG:
                log(f"      aiming roughly at {amount:.0f} so landmarks are "
                    f"in view")
                aimed = compass.turn_to(amount, ic.press, cap, log=log)
                if aimed is not None:
                    checked = read_heading_near(cap, aimed, log=log)
                    bearing = checked or aimed
                    since_read = 0.0
            # Walk in SEGMENTS, re-reading the heading between them. Reading is
            # cheap (~350ms) and the heading is what the travel vector is
            # computed from, so a fresh read each segment keeps the course true
            # even though nothing is ever aimed.
            remaining = secs
            seg = 0
            stuck = 0
            unwedge = 0
            # NOT reset per leg. Nothing between legs turns the camera, so
            # the heading carried out of the last leg is still valid. Only two
            # things invalidate it — a coarse aim, and an unwedge sidestep —
            # and both reset the timer explicitly where they happen.
            while remaining > 0.01:
                chunk = min(SEGMENT_SEC, remaining)
                # RE-READ ON A TIMER, not every segment. Walking cannot change
                # a heading (measured 0.5 degrees across nine presses), so a
                # read per segment re-measures a constant: 36 segments cost
                # ~13s of the successful run for a value that had not moved.
                # A periodic read still catches the one thing that can change
                # it — an unwedge sidestep, or a coarse aim — without paying
                # for the 90% of segments where nothing happened.
                if since_read >= HEADING_REREAD_SEC:
                    fresh = read_heading_near(cap, bearing, log=log)
                    if fresh is not None:
                        bearing = fresh
                    since_read = 0.0
                rel = compass.angular_error(bearing, amount)
                log(f"  {i:2}.{seg + 1} travel {amount:.0f} for {chunk:.1f}s "
                    f"(facing {compass.describe(bearing)}, moving {rel:+.0f} "
                    f"relative)")
                import numpy as _np
                judge = chunk >= STUCK_MIN_CHUNK_SEC
                before = (_np.asarray(cap().convert("L"), dtype=float)
                          if judge else None)
                ic.walk_at(rel, chunk)
                if judge:
                    time.sleep(0.25)
                    moved_px = float(_np.abs(
                        _np.asarray(cap().convert("L"), dtype=float)
                        - before).mean())
                else:
                    moved_px = None
                # STUCK DETECTION. Walking into a wall looks exactly like
                # walking down a corridor to an open-loop route: the keys are
                # pressed, the time passes, and nothing happens. Live, the
                # character wedged in the hallway on leg 1 and the remaining 17
                # seconds of route were walked into that wall, with the frame
                # unchanged the whole way. Measured: moving forward changes the
                # frame by ~3.9, standing still by ~1 (JPEG noise and NPC idle).
                # SCALE the threshold with how long we actually walked. Frame
                # change is roughly proportional to distance covered, so a
                # fixed floor calibrated on 1.1s segments declares every short
                # one blocked: the spliced curve uses 0.14-0.3s segments, which
                # move the frame ~0.7 even when travelling perfectly, and the
                # detector fired on almost all of them. Segments too short to
                # produce a reliable signal are not judged at all.
                expected = STUCK_DELTA * (chunk / SEGMENT_SEC)
                if moved_px is None:
                    pass
                elif moved_px < expected:
                    stuck += 1
                    log(f"      no movement (delta {moved_px:.2f} < "
                        f"{expected:.2f} expected for {chunk:.2f}s) — "
                        f"blocked {stuck}x")
                    if stuck >= STUCK_LIMIT:
                        # UNWEDGE, don't give up. Being blocked is the normal
                        # way a replayed path fails: the doorways here are
                        # narrow and a couple of degrees of drift catches a
                        # frame. Backing off and sidestepping is exactly what a
                        # person does, and strafing is free here because it
                        # moves without disturbing the heading (measured 0.0
                        # degrees). Alternating the sidestep direction means a
                        # wrong guess is corrected on the next attempt rather
                        # than driving further into the corner.
                        if unwedge < UNWEDGE_ATTEMPTS:
                            unwedge += 1
                            side = 90.0 if unwedge % 2 else 270.0
                            log(f"      wedged — backing off and sidestepping "
                                f"{'right' if side == 90.0 else 'left'} "
                                f"(attempt {unwedge})")
                            ic.walk_at(180.0, UNWEDGE_BACK_SEC)
                            time.sleep(0.25)
                            ic.walk_at(side, UNWEDGE_SIDE_SEC)
                            time.sleep(0.25)
                            stuck = 0
                            since_read = HEADING_REREAD_SEC   # sidestep may
                            continue          # have changed nothing, but read
                        raise WalkError(
                            f"step {i}: blocked against geometry and "
                            f"{UNWEDGE_ATTEMPTS} unwedge attempts failed. "
                            f"Walking on would replay the rest into a wall.")
                else:
                    stuck = 0
                remaining -= chunk
                seg += 1

        elif kind in ("turn", "face"):
            current = compass.read_bearing_stable(cap, log=log)
            if current is None and bearing is not None:
                current = bearing
            if current is None:
                raise WalkError(f"step {i}: compass unreadable and no prior "
                                f"heading — refusing to turn blind")
            target = (amount if kind == "face"
                      else (current + amount)) % 360.0
            log(f"  {i:2}. {kind} {amount:.0f} from {compass.describe(current)}")
            got = compass.turn_to(target, ic.press, cap, log=log)
            if got is not None:
                bearing = got

        if check:
            import time
            time.sleep(0.6)
            shot = cap()
            if save_dir:
                path = f"{save_dir}/walk_{i:02d}_{check}.jpg"
                shot.save(path, quality=88)
            verdict = _check_landmark(check, shot)
            if verdict is True:
                log(f"      CHECKPOINT {check}: CONFIRMED — {CHECKPOINTS[check]}")
            elif verdict is False:
                raise WalkError(
                    f"step {i}: checkpoint {check!r} NOT reached — expected "
                    f"{CHECKPOINTS[check]}. Stopping rather than walking on "
                    f"blind; the frame is saved for inspection.")
            else:
                log(f"      checkpoint {check}: UNVERIFIED (no detector) — "
                    f"expected {CHECKPOINTS[check]}")
    return bearing


def describe():
    """Print the route as it would be executed. No input, no capture."""
    total = 0.0
    print(f"\n  {'step':<6} {'action':<40} {'checkpoint'}")
    for i, (kind, amount, secs, check) in enumerate(ROUTE, 1):
        if kind == "travel":
            act = f"travel bearing {amount:.0f} for {secs:.1f}s"
            total += secs
        elif kind == "face":
            act = f"face {amount:.0f} (only aim of the route)"
        else:
            act = f"turn {amount:+.0f}"
        print(f"  {i:<6} {act:<40} {CHECKPOINTS.get(check, '')}")
    print(f"\n  {total:.1f}s of travel, "
          f"{sum(1 for r in ROUTE if r[3])} checkpoints")
    print("  travel is camera-relative, so navigating needs no accurate "
          "turning\n")


if __name__ == "__main__":
    describe()


def find_table(cap, log=print, sweeps=8, step_sec=0.6, walk_steps=3):
    """Look around (and edge forward) until the baseball table is confirmed.

    WHY A SEARCH RATHER THAN AN ARRIVAL
    -----------------------------------
    The route cannot place the character exactly: the smallest commandable turn
    is ~28 degrees and leg durations are open-loop, so "arrive on the spot
    facing the right way" is not a thing this control has the resolution to do.
    But at_baseball_table is the most reliable signal in the project — 37/37
    true positives, 0 false positives across 108 negatives — so arriving
    NEARBY and then looking is a far better use of it than demanding precision
    the actuator cannot deliver.

    Sweeps the camera a full turn, checking each facing; if nothing, steps
    forward a little and sweeps again. Returns True the moment it is confirmed.
    """
    import time

    import compass
    import input_controller as ic
    import landmarks

    for advance in range(walk_steps + 1):
        for k in range(sweeps):
            if landmarks.at_baseball_table(cap()) is True:
                log(f"      TABLE CONFIRMED (advance {advance}, sweep {k})")
                return True
            ic.press("look_right", hold_seconds=0.0, post_delay=0.3)
            time.sleep(0.55)
        if advance < walk_steps:
            log(f"      not in sight from here — stepping forward")
            ic.press("walk_up", hold_seconds=step_sec, post_delay=0.35)
            time.sleep(0.5)
    return False




