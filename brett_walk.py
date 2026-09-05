"""Boilerplate so a walk can be written as plain button presses.

    from brett_walk import walk

    with walk("wanda to the table") as w:
        w.turn(287)
        w.forward(2.0)
        w.mark("bar_pool_room")
        w.forward(3.3)
        w.right(0.4)
        w.look()

Everything else — connecting, checking the picture is live, recording, saving —
is handled here. The script you write is only the moves.

WHY IT RECORDS
--------------
The legs in world_map.json came from a human's walk that started from a
different pose than the bot reaches, and that mismatch is the single reason
routing still fails. A walk driven by hand is only useful if it is CAPTURED:
every command, frame, heading and place guess on one clock, so map_build.py can
turn it into legs offline. So this records automatically — there is nothing to
remember to switch on.

WHY IT REFUSES TO START BLIND
-----------------------------
With chiaki not running, capture used to hand back the desktop and every reading
was of the wrong window. `walk()` will not begin without a live, updating game
picture.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_SPEED = 0.25          # left-stick magnitude used by the recorded route
SETTLE = 0.25

# Let CHIAKI time the release instead of sleeping here and writing a zero.
# Patched into the injector 2026-09-03: a third field on a stick line is a
# hold in milliseconds, released on chiaki's own clock.
#
# It removes the Python sleep and the FIFO round trip from the release edge.
# That is worth having but it is NOT the main source of drift — the error is
# quantised to whole GAME FRAMES (3.795 deg each, measured over 6 runs), and
# nothing on this side can remove that. See CLAUDE.md.
#
# Kept as a flag so it can be A/B'd against the old path rather than assumed.
CHIAKI_TIMES_THE_HOLD = True
MAX_TIMED_HOLD = 4.5          # INJECT_TIMEOUT_MS is 5s; stay under it


class Walk:
    """Movement primitives that record themselves."""

    def __init__(self, name, speed=DEFAULT_SPEED, recorder=None, log=print):
        self.name = name
        self.speed = speed
        self.rec = recorder
        self.log = log
        self._moves = 0

    # --- the primitives you write ------------------------------------------

    def turn(self, bearing):
        """RIGHT STICK, closed loop. Moves the CAMERA to an absolute bearing.

        The player does not move. This is the same physical stick as camera(),
        but instead of holding it for a fixed time it reads the compass and
        keeps nudging until the heading is right — so it lands on 270 whether
        it started at 0 or at 269, and errors do not accumulate down a route.

        0 = N, 90 = E, 180 = S, 270 = W.

        WHY THIS MATTERS FOR WALKING: forward is CAMERA-RELATIVE. The left
        stick moves the player in whatever direction the camera faces, so
        aiming the camera is how you choose the direction of the next
        forward(). That is the whole reason a route is written turn-then-walk.
        """
        import walk_steps as ws

        want = float(bearing) % 360.0
        got = ws.turn_to(want, log=self.log)
        # Report the ERROR, not the raw heading. Turning to 2 and landing on
        # 359.7 is a 2.3 degree miss, but printed as "got 359.7" against a
        # target of 2 it reads as a 358 degree failure — which is exactly how
        # a correct turn got reported as "the compass didn't work".
        err = None if got is None else (got - want + 540) % 360 - 180
        self._note("turn", bearing=round(want, 1),
                   got=None if got is None else round(got, 1),
                   error=None if err is None else round(err, 1))
        if got is None:
            self.log(f"  turn  {want:6.1f}  FAILED — no compass reading")
        else:
            self.log(f"  turn  {want:6.1f}  -> {got:6.1f}  "
                     f"(off by {err:+.1f} deg{', ok' if abs(err) <= ws.TURN_TOLERANCE else ''})")
        return got

    def forward(self, seconds, speed=None):
        """Walk forward. Split into <=0.8s pushes so chiaki cannot cut it short."""
        return self._push(seconds, speed=speed, strafe=0.0, label="forward")

    def back(self, seconds, speed=None):
        return self._push(seconds, speed=speed, strafe=0.0, label="back",
                          sign=-1.0)

    def stick(self, seconds, y=0.0, x=0.0):
        """Raw left stick, if the four named moves are not enough.
        y: +forward -back.  x: +right -left."""
        return self._push(seconds, speed=abs(y) or None, strafe=x,
                          label="stick", sign=-1.0 if y < 0 else 1.0)

    def right(self, seconds, speed=None):
        """Strafe right without turning."""
        return self._push(seconds, speed=0.0, strafe=+(speed or self.speed),
                          label="right")

    def left(self, seconds, speed=None):
        return self._push(seconds, speed=0.0, strafe=-(speed or self.speed),
                          label="left")

    def camera(self, seconds, x=0.0, y=0.0):
        """RIGHT STICK. Moves the CAMERA. The player does not move.

            x: + right / - left        y: + down / - up
            magnitude 0..1             seconds = how long it is held

        Raw and open-loop: stick and duration, nothing else. It does NOT read
        the compass. Use it when you want "hold right stick for 0.4s".

        The COST of open loop is drift, and it is not small. Two identical
        `camera(1.0, x=1.0)` calls measured 2026-09-02 turned +208.6 and
        +201.0 degrees — 7.7 degrees apart on the same command, with no
        compass anywhere in the path. The variance is in the stick-to-console
        timing, so a sequence of raw turns accumulates error.

        `turn(bearing)` is the closed-loop alternative: same right stick, but
        it reads the compass and lands on an absolute heading, which is how
        that drift gets cancelled instead of accumulated.

        The x sign is measured: turn_to sends POSITIVE right_x to correct a
        positive bearing error, so positive turns clockwise.
        THE Y SIGN IS NOT MEASURED — nothing in this project has ever sent a
        nonzero right_y (turn_to pins it to 0), and some games invert pitch.
        Try a small one and look before trusting it.
        """
        import analog_replay as ar
        import walk_steps as ws

        # to_axis clamps to int16, so x=10 is silently x=1 — full stick, and
        # the least precise place to be. Say so rather than quietly obeying
        # something the caller did not mean.
        for axis, v in (("x", x), ("y", y)):
            if abs(v) > 1.0:
                self.log(f"  camera: {axis}={v:+.2f} is outside the stick's "
                         f"-1..1 range — clamped to "
                         f"{max(-1.0, min(1.0, v)):+.2f} (full stick)")
            if 0.9 < abs(v) <= 1.0:
                # MEASURED 2026-09-03, n=6 per arm, same pose and conditions:
                #   mag 1.0  spread 17.28 deg over a 209 deg turn  (8.3%)
                #   mag 0.9  spread  3.61 deg over a  72 deg turn  (5.0%)
                # 4.8x more absolute drift for 11% more stick. turn_curve's
                # own table says why: 74.8 deg/s at 0.90 against 197.7 at 1.00.
                self.log(f"  camera: {axis}={v:+.2f} is above the usable band. "
                         f"0.9 measured 4.8x LESS drift — turn for longer "
                         f"instead of harder.")
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))

        secs = float(seconds)
        if CHIAKI_TIMES_THE_HOLD and secs <= MAX_TIMED_HOLD:
            # ONE write. chiaki holds and releases it itself, so the duration
            # no longer depends on this process waking up on time.
            ms = int(round(secs * 1000))
            ar.send([f"right_x {ar.to_axis(x)} {ms}",
                     f"right_y {ar.to_axis(y)} {ms}",
                     "left_x 0", "left_y 0"])
            time.sleep(secs + ws.SETTLE)
        else:
            left = secs
            while left > 0.01:              # chiaki drops injected input at 5s
                step = min(0.8, left)
                ar.send([f"right_x {ar.to_axis(x)}", f"right_y {ar.to_axis(y)}",
                         "left_x 0", "left_y 0"])
                time.sleep(step)
                left -= step
            ar.send(["right_x 0", "right_y 0"])
            time.sleep(ws.SETTLE)
        self._note("camera", seconds=round(float(seconds), 2), x=x, y=y)
        self.log(f"  camera {float(seconds):5.2f}s  x={x:+.2f} y={y:+.2f}")

    def jump(self):
        """Cross is jump — measured, four presses spiked 10.1-12.5 vs a 4.67 idle."""
        return self.press("cross")

    def press(self, button, hold=0.08):
        """Any button by name: cross, moon, box, pyramid, dpad_up ..."""
        import input_controller as ic

        ic.press(button, hold_seconds=hold)
        self._note("press", button=button)
        self.log(f"  press {button}")
        time.sleep(SETTLE)

    def wait(self, seconds):
        """Stand still. Useful when an NPC is in the way."""
        self._note("wait", seconds=seconds)
        self.log(f"  wait  {seconds:.1f}s")
        time.sleep(seconds)

    # --- looking, and naming what you see ----------------------------------

    def look(self):
        """Report where we are. Moves nothing."""
        import compass
        import places
        import table_prompt as tp

        img = compass.fast_capture()
        room, n, ratio = places.identify(img)
        bearing = compass.read_bearing(img)
        at_table = bool(tp.at_table(img))
        self._note("look", room=room, matches=n, bearing=bearing,
                   at_table=at_table)
        self.log(f"  look  here={room} ({n} matches)  bearing="
                 f"{'--' if bearing is None else f'{bearing:.1f}'}  "
                 f"at_table={at_table}")
        return room

    def mark(self, place):
        """Say "this spot is <place>" — the label that makes a walk a map.

        Only YOU can do this: the localiser fails exactly where its references
        do not cover, and a frame labelled by someone who can see the screen is
        what fixes it. Refuses a frame with too little structure, because a
        near-blank reference matches every other blank frame — that is how an
        upstairs door once scored 0.906 against the bar.
        """
        import compass
        import places

        img = compass.fast_capture()
        _, desc = places.keypoints(img)
        n = 0 if desc is None else len(desc)
        if n < 200:
            self.log(f"  mark  REFUSED {place}: only {n} keypoints — too "
                     f"featureless to be anyone's fingerprint")
            self._note("mark_refused", place=place, keypoints=n)
            return None
        path = places.add(place, img)
        self._note("mark", place=place, keypoints=n, file=path)
        self.log(f"  mark  {place}  ({n} keypoints) -> {path}")
        return path

    # --- internals ---------------------------------------------------------

    def _push(self, seconds, speed, strafe, label, sign=1.0):
        """Hold the stick, in <=0.8s pushes.

        Chiaki drops injected input after INJECT_TIMEOUT_MS (5s), so one long
        write silently caps at ~4.5s.
        """
        import analog_replay as ar
        import walk_steps as ws

        mag = (self.speed if speed is None else speed) * sign
        moved, left = 0.0, float(seconds)
        while left > 0.01:
            step = min(0.8, left)
            before = ws._grey()
            ar.send([f"left_y {ar.to_axis(-mag)}",
                     f"left_x {ar.to_axis(strafe)}",
                     "right_x 0", "right_y 0"])
            time.sleep(step)
            ar.clear()
            time.sleep(ws.SETTLE)
            moved += ws._view_change(before, ws._grey()) or 0.0
            left -= step
        self._moves += 1
        self._note(label, seconds=round(float(seconds), 2), moved=round(moved, 1))
        self.log(f"  {label:7} {float(seconds):5.2f}s  -> view moved {moved:5.1f}")
        return moved

    def _note(self, action, **fields):
        if self.rec is not None:
            self.rec.note(action, **fields)


class _Session:
    def __init__(self, name, speed, hz, log):
        self.name, self.speed, self.hz, self.log = name, speed, hz, log
        self.rec = None
        self.walk = None

    def __enter__(self):
        import ensure_stream
        import world_log

        if not ensure_stream.ensure_live(log=self.log):
            raise RuntimeError(
                "no live game picture — chiaki is not up or the stream is "
                "frozen. Refusing to start: with no game window, capture used "
                "to return the desktop and every reading was of the wrong "
                "window.")
        self.rec = world_log.Recorder(self.name, hz=self.hz).start()
        self.walk = Walk(self.name, speed=self.speed, recorder=self.rec,
                         log=self.log)
        self.log(f"recording to {self.rec.dir}")
        self.walk.look()
        return self.walk

    def __exit__(self, *exc):
        import analog_replay as ar

        try:
            ar.clear()          # stops NEW input; whatever is in flight lands
        except Exception:
            pass
        if self.walk is not None:
            try:
                self.walk.look()
            except Exception:
                pass
        d = self.rec.stop() if self.rec else None
        self.log(f"\nsaved {d}")
        self.log(f"turn it into graph legs with:\n"
                 f"  .venv/bin/python map_build.py {d}")
        return False


def walk(name="walk", speed=DEFAULT_SPEED, hz=6.0, log=print):
    """Context manager: connects, records, hands you the primitives, saves."""
    return _Session(name, speed, hz, log)
