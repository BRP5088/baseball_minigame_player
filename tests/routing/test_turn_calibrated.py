"""turn_calibrated against a camera that behaves like the real one.

The simulator reproduces the three behaviours measured live on 2026-08-27,
because each one previously caused a wrong conclusion:

  * SETTLING LATENCY. The camera keeps moving after release. Three of twenty
    identical holds still read 0.0 degrees a third of a second later, then
    settled to 9.6. Read too early and a working press looks dropped.
  * OVERSHOOT. About one press in ten keeps rotating past its release.
  * THE ZERO-HOLD ANOMALY. A 0.00s hold turns ~30 degrees, more than a 0.12s
    hold, because keydown and keyup posted together can be seen out of order.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
import turn_calibrated as tc

tc.SETTLE_POLL_SEC = 0.0          # no real waiting in an offline test
tc.SETTLE_TIMEOUT_SEC = 9e9   # the poll-count bound is what stops these loops

fails = []


class Camera:
    """Bearing that eases toward a commanded target over several reads."""

    def __init__(self, bearing=0.0, latency=3, overshoot=1.0):
        self.bearing = bearing
        self.pending = 0.0
        self.latency = latency
        self.overshoot = overshoot
        self.ticks = 0
        self.holds = []

    def read(self):
        if self.pending and self.ticks > 0:
            self.ticks -= 1
            if self.ticks == 0:
                self.bearing = (self.bearing + self.pending) % 360
                self.pending = 0.0
        return self.bearing

    # MEASURED CONSTANTS, hardcoded on purpose. Turning by tc.DEG_PER_SEC would
    # make the simulated camera obey whatever the module currently believes, so
    # a wrong calibration would steer a camera that was wrong in exactly the
    # same way and every test would still pass. These are the numbers measured
    # live on 2026-08-27; the module has to match THEM.
    REAL_DEG_PER_SEC = 143.8
    REAL_INTERCEPT = -0.80

    def press(self, action, hold):
        self.holds.append(hold)
        deg = self.REAL_DEG_PER_SEC * hold + self.REAL_INTERCEPT
        if action == "look_left":
            deg = -deg
        self.pending = deg * self.overshoot
        self.ticks = self.latency


# --- 1. lands on target ----------------------------------------------------
for target in (12.0, 47.0, 180.0, 300.0, 359.0):
    cam = Camera(bearing=0.0)
    final = tc.turn_to(target, cam.read, cam.press, tolerance=3.0, max_steps=40)
    if final is None:
        fails.append(f"abstained steering to {target}")
        continue
    err = abs((target - final + 540) % 360 - 180)
    if err > 3.0:
        fails.append(f"target {target}: landed {final:.1f}, off by {err:.1f} deg "
                     f"— outside the tolerance it was asked for")

# --- 2. never commands the zero-hold anomaly -------------------------------
cam = Camera(bearing=0.0)
tc.turn_to(1.0, cam.read, cam.press, tolerance=0.05, max_steps=10)
cam2 = Camera(bearing=0.0)
tc.turn_to(200.0, cam2.read, cam2.press, tolerance=0.5, max_steps=60)
# 0.02 as a LITERAL. Comparing against tc.MIN_HOLD_SEC asks "is any hold below
# the floor?" using the floor itself, so setting the floor to 0.0 satisfies it
# trivially — the check would pass precisely when the bug was introduced.
tiny = [h for h in (cam.holds + cam2.holds) if h < 0.02]
if tiny:
    fails.append(f"commanded holds below MIN_HOLD_SEC ({tiny[:3]}) — at 0.00s the "
                 f"camera swings ~30 deg, so this turns far further than asked")

# --- 3. settling is waited out, not slept through --------------------------
# changed_from is what separates "has not started moving" from "has finished".
# Without it both look like a run of identical readings.
cam = Camera(bearing=0.0, latency=5)
cam.press("look_right", tc.hold_for(10.0))
b = tc.settled_bearing(cam.read, changed_from=0.0)
if b is None or abs(b) < 1.0:
    fails.append(f"settled_bearing returned {b} while the camera was still "
                 "moving — a caller reads that as a dropped press and turns twice")

# and a press that genuinely does nothing must report the unmoved bearing,
# not None, so the caller can tell a dead press from a blind compass
still = Camera(bearing=17.0, latency=0)
b = tc.settled_bearing(still.read, changed_from=17.0)
if b != 17.0:
    fails.append(f"a camera that never moved reported {b} instead of 17.0 — "
                 "'that press did nothing' and 'the compass failed' are "
                 "different problems and must not look alike")

# --- 4. an overshooting camera is still corrected --------------------------
cam = Camera(bearing=0.0, overshoot=1.6)
final = tc.turn_to(40.0, cam.read, cam.press, tolerance=3.0, max_steps=40)
if final is None or abs((40.0 - final + 540) % 360 - 180) > 3.0:
    fails.append(f"a camera that overshoots every press ended at {final} instead "
                 "of 40 — the loop is trusting the model instead of re-reading")

# --- 5. abstains rather than guessing when the compass cannot read ----------
class Blind(Camera):
    def read(self):
        return None


blind = Blind()
if tc.turn_to(90.0, blind.read, blind.press, max_steps=5) is not None:
    fails.append("returned a bearing while the compass was abstaining")
if blind.holds:
    fails.append("pressed keys while unable to read the compass — turning blind "
                 "is how the camera ends up somewhere arbitrary")

# --- 6. a camera still drifting when the budget runs out ------------------
# recent[-1] is the best available answer there. Returning None instead would
# make an almost-settled camera indistinguishable from a blind compass, and the
# caller abandons a turn it had very nearly completed.
class Drifting(Camera):
    def read(self):
        self.bearing = (self.bearing + 5.0) % 360      # never settles
        return self.bearing


drift = Drifting(bearing=0.0)
b = tc.settled_bearing(drift.read, changed_from=0.0)
if b is None:
    fails.append("a camera that never stops drifting returned None — that is "
                 "the same answer as a compass that cannot read at all, and "
                 "the two need different handling")

# --- 7. hold_for is clamped at BOTH ends ----------------------------------
# turn_to happens to keep its requests inside the calibrated band, so an
# unclamped hold_for passes every test above. Exercised directly instead:
# outside that band the linear fit stops holding, and a 0.5s hold does not
# turn 5x what a 0.1s one does.
if tc.hold_for(1000.0) > 0.14:
    fails.append(f"hold_for(1000) returned {tc.hold_for(1000.0):.3f}s — beyond "
                 "0.14s the response is no longer linear, so the model would "
                 "be extrapolating into behaviour it never measured")
if tc.hold_for(0.001) < 0.02:
    fails.append(f"hold_for(0.001) returned {tc.hold_for(0.001):.3f}s — below "
                 "0.02s sits the zero-hold anomaly, where the camera swings "
                 "~30 deg instead of barely moving")

# --- 8. a drifting camera reports a READING, not its starting point --------
drift2 = Drifting(bearing=0.0)
b2 = tc.settled_bearing(drift2.read, changed_from=0.0)
if b2 == 0.0 or b2 is None:
    fails.append(f"a drifting camera reported {b2}, its pre-press bearing — "
                 "that says the press did nothing, when in fact the camera "
                 "moved a long way and simply never stopped")

# --- 9. a tolerance finer than one press must TERMINATE --------------------
# The smallest commandable turn is ~2.1 deg. Asked for better than that, the
# loop must stop at the closest reachable bearing rather than nudging back and
# forth forever, each nudge overshooting the target from the other side.
osc = Camera(bearing=0.0)
tc.turn_to(1.0, osc.read, osc.press, tolerance=0.2, max_steps=40)
if len(osc.holds) > 3:
    fails.append(f"asked for +-0.2 deg (finer than one press can deliver) the "
                 f"loop pressed {len(osc.holds)} times — it is oscillating "
                 "around a target it cannot hit")

# --- 10. a camera that EASES through intermediate angles -------------------
# The cameras above jump straight to their final bearing, so a single reading
# is never wrong and requiring several looks unnecessary. A real camera sweeps
# through every angle on the way, and one reading taken during that sweep is a
# real bearing that is simply not the final one. That is what the consecutive
# -agreement rule exists for.
class Easing:
    def __init__(self):
        self.bearing = 0.0
        self.remaining = 0.0
        self.holds = []

    def read(self):
        if abs(self.remaining) > 1e-9:
            step = self.remaining / 4.0          # sweeps in visible increments
            self.bearing = (self.bearing + step) % 360
            self.remaining -= step
            if abs(self.remaining) < 0.05:
                self.bearing = (self.bearing + self.remaining) % 360
                self.remaining = 0.0
        return self.bearing

    def press(self, action, hold):
        self.holds.append(hold)
        deg = 143.8 * hold - 0.80
        self.remaining = -deg if action == "look_left" else deg


ease = Easing()
ease.press("look_right", tc.hold_for(19.0))
settled = tc.settled_bearing(ease.read, changed_from=0.0)
expected = 143.8 * tc.hold_for(19.0) - 0.80
if settled is None or abs(settled - expected) > 1.0:
    fails.append(f"settled at {settled} while the camera was still sweeping "
                 f"toward {expected:.1f} — a single reading mid-rotation is a "
                 "real bearing, just not the finished one, so one read can "
                 "never be enough to call it settled")

# --- 11. screen-x to bearing uses the SCREEN scale, not the compass ---------
# Both are horizontal pixels, which is exactly why they get confused. The
# compass strip runs ~3.2 px/deg and the picture ~18.7, so reading a landmark
# off the compass scale overstates its angle 5.8x. That mistake put a doorway
# at 319 degrees when it was at 359 and walked the character into a wall.
if abs(tc.bearing_of_screen_x(960, 100.0) - 100.0) > 0.01:
    fails.append("something at the reticle must be at the bearing the reticle "
                 "reports, and was not")

right = tc.bearing_of_screen_x(960 + 187, 100.0)      # 187px = 10 deg
if abs(right - 110.0) > 0.5:
    fails.append(f"187px right of centre gave {right:.1f}, expected ~110 — that "
                 f"is the compass scale (3.2 px/deg) leaking in where the screen "
                 f"scale (18.7) belongs")

left = tc.bearing_of_screen_x(960 - 187, 100.0)
if abs(left - 90.0) > 0.5:
    fails.append(f"187px left of centre gave {left:.1f}, expected ~90")

if abs(tc.bearing_of_screen_x(0, 5.0) - (5.0 - 960 / 18.7)) % 360 > 0.5:
    fails.append("the frame edge did not wrap correctly below 0 degrees")

if not (0 <= tc.bearing_of_screen_x(0, 5.0) < 360):
    fails.append("returned a bearing outside 0-360")

if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("  turn_to lands within tolerance from any angle, never commands the "
      "0.00s hold, waits out settling instead of reading mid-rotation, corrects "
      "a persistently overshooting camera, and presses nothing when blind")
