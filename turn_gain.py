"""Robust gain estimation and stopping policy for the closed-loop camera turn.

WHY THIS EXISTS
---------------
The camera actuator is AFFINE in hold time (deg = 13.5 + 207*hold, measured
windowed: 0.01s -> 15.6, 0.03s -> 19.6, 0.05s -> 23.9) and its scale CHANGES
with conditions — switching the game to fullscreen made it turn ~2.4x faster
than the fitted constants. So the loop has to learn a multiplier at runtime.

compass.turn_to learns it with a per-sample multiplicative jump,
`gain *= (1 + 0.6*(moved/predicted - 1))`, clamped to [0.2, 6.0], with no
plausibility check on `moved`. One bad OCR therefore rewrites the model. Live
trace, target 85:

    349 -> press -> moved 140 vs  96 predicted -> gain 1.27
    128 -> press -> moved  62 vs  43 predicted -> gain 1.59
     67 -> press -> moved  48 vs  22 predicted -> gain 2.75
    114 -> press -> moved 163 vs  37 predicted -> gain 6.00   (clamped at max)
    278 -> press -> moved  30 vs 167 predicted -> gain 3.05
    308 -> press -> bearing unreadable
    313 -> press -> moved   5 vs 137 predicted -> gain 1.29
    gave up after 8 iterations, best was 18 degrees off

Two of those samples are physically impossible and both are decisive. "moved
163" against a hold of ~0.00s implies 163/13.5 = 12x the fitted rate — no
window change does that. "moved 5" against the 0.15s hold that prediction of
137 implies is 0.11x — a press cannot move LESS than its fixed cost. The bearings come from OCR of an
on-screen compass that has been seen reading 342, 342, 157, 341, 251 off a
STATIONARY camera, so a nonsense sample is expected, not exceptional.

What this module changes:

  * each press yields a DIRECT estimate of the multiplier, k = moved /
    (13.5 + 207*hold), instead of a ratio against the current estimate. There
    is no feedback loop, so one sample cannot compound into the next.
  * samples outside [0.35, 6.0] are DISCARDED, not clamped. Those are the
    absolute physical bounds of the actuator across every window mode seen
    (windowed 1.0, fullscreen 2.4), with wide margin. Both poison samples in
    the trace above fall outside them.
  * the reported gain is the MEDIAN of the last 7 accepted samples, with the
    fitted prior (1.0) mixed in as a pseudo-sample until 3 real ones exist. A
    median of a window ignores a lone survivor of the bounds check; the
    pseudo-sample keeps the first sample from being taken at face value and
    makes the median of 2 well defined.
  * the STOPPING RULE scales with the learned gain. The smallest turn the
    stream can deliver is one minimum press, 15.6*gain degrees; below half of
    that, pressing overshoots further than the error it corrects. compass uses
    a hardcoded 16 for that floor, which is right windowed and wrong in
    fullscreen, where the true floor is ~37 — so it chases 20-degree errors it
    physically cannot fix, which is the oscillation.
    It also stops at 8 degrees however fine the steps get: that is the
    threshold compass validated live, and the corridors are ~15 degrees wide,
    so more precision only spends iterations.
  * NO PRESS IS AIMED FURTHER THAN ITS OUTCOME CAN BE READ. A bearing is known
    only mod 360, so a correction planned at the wrong scale can turn a full
    circle and read back as having done nothing — the loop then repeats it
    forever. The aim is capped by the largest scale still consistent with the
    samples so far, which is strict while nothing is known and relaxes to ~130
    degrees once presses agree. In simulation this single rule is most of the
    difference at 2.4x and 4x.
  * a stop decided on a reading that no measured press vouches for must be
    seen TWICE. Otherwise one wild OCR inside the stop band ends the turn
    declaring success while pointing anywhere at all.
  * when it runs out of corrections it READS AGAIN rather than reporting the
    closest bearing it saw, which is stale by a press. See run_turn.

Nothing here imports compass, PIL or numpy: it is pure arithmetic, so it stays
importable (and testable) while compass is being edited, and the constants
below deliberately mirror compass's rather than depending on them.
"""

import statistics
import time
from collections import deque

# --- the fitted actuator ---------------------------------------------------
# deg = FIXED_DEG + RATE_DEG_PER_SEC * hold, at gain 1 (windowed). Mirrors
# compass.TURN_FIXED_DEG / TURN_RATE_DEG_PER_SEC.
FIXED_DEG = 13.5
RATE_DEG_PER_SEC = 207.0
# A keypress is a discrete event with a minimum duration: asking for 0.00s and
# asking for 0.01s produce the same ~15.6 degrees. Every prediction is made at
# the hold that will ACTUALLY be delivered, not the one requested.
MIN_HOLD_SEC = 0.01
# Absolute ceiling on one press: 189 degrees at gain 1, more than any error can
# be. The aim cap below is what actually keeps presses readable; this is the
# backstop for a gain estimate that has gone to the floor.
MAX_HOLD_SEC = 0.85
# No press may aim so far that its OUTCOME could be unreadable. A bearing is
# only known mod 360, so a press that turns more than half a circle reads as
# having gone the other way and one that turns a full circle reads as having
# done nothing at all — the worst possible failure, because the loop then
# repeats it forever. Every aim is therefore capped at this many degrees
# DIVIDED by the largest scale still consistent with what has been measured
# (see plausible_max_gain), which is a hard cap while nothing is known and
# relaxes to ~130 degrees once samples agree. 170 rather than 180 because a
# turn of exactly half a circle has no readable direction.
NO_WRAP_DEG = 170.0
# How far above the largest accepted sample the true scale might still be:
# press noise is 8-15%, so this is that plus slack.
GAIN_HEADROOM = 1.3

# --- what a sample is allowed to say ---------------------------------------
# Bounds on the multiplier itself, NOT on the current estimate: a plausibility
# check that depends on the thing it is protecting can be walked anywhere one
# step at a time. Measured modes are 1.0 (windowed) and 2.4 (fullscreen); these
# bracket that by ~3x on each side, which is enough slack for an unseen window
# size and still rejects the trace's 12x and 0.04x samples.
GAIN_MIN = 0.35
GAIN_MAX = 6.0
PRIOR_GAIN = 1.0            # the fitted constants, believed until measured otherwise
WINDOW = 7                  # samples kept; median tolerates 3 bad ones
PRIOR_WEIGHT_UNTIL = 3      # real samples needed before the prior drops out

# Never chase below this regardless of how fine the steps get. 8 degrees
# is the threshold compass validated live over 10 targets (mean |err| 3.6, max
# 7.8, 0 abstentions) and the corridors this has to walk are ~15 degrees wide,
# so precision beyond it buys nothing and costs iterations — each one is a
# 0.8s settle plus a read, and every extra read is another chance for the OCR
# to hand back nonsense at the worst moment.
GOOD_ENOUGH_DEG = 8.0
# Two consecutive reads must agree within this to end a turn. Sized to sit
# above OCR jitter (~1-2 deg) and far below a wild misread (uniform in 360).
CONFIRM_AGREE_DEG = 12.0
# Reads spent measuring where the camera ended up after the last press, when
# the loop runs out of corrections. Two, because a single unreadable frame is
# routine and a wrong heading reported as fact is not.
VERIFY_READS = 2


def angular_error(current, target):
    """Signed shortest rotation from current to target, in (-180, 180]."""
    return (target - current + 180.0) % 360.0 - 180.0


class GainEstimator:
    """Learns the actuator's scale multiplier from what presses actually did.

    Keep ONE of these across a whole route, not one per turn. The multiplier is
    a property of the window/stream, not of a turn: compass.turn_to resets it
    to 1.0 on every call, so it re-learns from scratch — badly, on 2-3 samples
    — for every leg of every walk.
    """

    def __init__(self, prior_gain=PRIOR_GAIN, window=WINDOW):
        self._prior = float(prior_gain)
        self._samples = deque(maxlen=window)
        self.accepted = 0
        self.rejected = 0

    # -- model ------------------------------------------------------------
    def model_deg(self, hold_seconds, gain=1.0):
        """Degrees a press of `hold_seconds` should turn, at `gain`."""
        hold = min(MAX_HOLD_SEC, max(MIN_HOLD_SEC, float(hold_seconds)))
        return gain * (FIXED_DEG + RATE_DEG_PER_SEC * hold)

    @property
    def gain(self):
        """Current best estimate of the multiplier."""
        if not self._samples:
            return self._prior
        pool = list(self._samples)
        if len(pool) < PRIOR_WEIGHT_UNTIL:
            pool.append(self._prior)
        return statistics.median(pool)

    @property
    def plausible_max_gain(self):
        """Largest scale still consistent with the evidence.

        With nothing measured that is the whole plausible range; each accepted
        sample shrinks it, which is what lets the aim cap relax. Using the
        current estimate alone here would be circular — a badly LOW estimate
        would licence a badly long press.
        """
        if not self._samples:
            return GAIN_MAX
        return min(GAIN_MAX, max(max(self._samples), self.gain) * GAIN_HEADROOM)

    @property
    def min_step_deg(self):
        """Smallest turn the stream can deliver: one minimum press."""
        return self.model_deg(MIN_HOLD_SEC, self.gain)

    @property
    def stop_threshold_deg(self):
        """Below this, stop: either it cannot be improved or it need not be.

        Half a step exactly, with no safety margin on top. A press at exactly
        half a step is break-even and above it is a strict improvement, so
        padding the threshold to save an iteration was measurably worse at
        every scale simulated (10-25% of padding cost 0.2-1.5 degrees of mean
        final error and bought ~0.1 of a press).
        """
        return max(GOOD_ENOUGH_DEG, 0.5 * self.min_step_deg)

    # -- learning ---------------------------------------------------------
    def update(self, hold_seconds, degrees_moved):
        """Fold in one press. Returns True if the sample was believed.

        `degrees_moved` is SIGNED in the commanded direction: positive means
        the camera moved the way it was asked to. A press that reads as having
        moved backwards is a bad read (or a lost input), never evidence about
        the gain, and the negative implied multiplier is rejected below.
        """
        base = self.model_deg(hold_seconds, 1.0)
        implied = float(degrees_moved) / base
        if not (GAIN_MIN <= implied <= GAIN_MAX):
            self.rejected += 1
            return False
        self._samples.append(implied)
        self.accepted += 1
        return True

    # -- control ----------------------------------------------------------
    def predict_hold(self, error_degrees):
        """Hold time to close `error_degrees`, clamped to what is commandable.

        Degrees are AFFINE in hold, so this inverts deg = g*(FIXED + RATE*h).
        When the error is smaller than the fixed cost the answer is the minimum
        press, which OVERSHOOTS — should_press decides whether that is still
        worth doing.

        UNTIL ONE PRESS HAS BEEN MEASURED the aim is capped much harder, so
        that the press stays interpretable even if the true scale is GAIN_MAX.
        Planning a big correction at an unmeasured scale does not merely miss,
        it destroys the measurement: at 2.4x a 150-degree correction planned at
        1.0x turns 360 and the compass reads back UNCHANGED, so the loop learns
        nothing, and does the same thing again. Measured in simulation, that
        one effect is most of the difference at 2.4x and 4x. This costs at most
        an extra press, and only on the FIRST turn of a route if the caller
        keeps the estimator (which it should).
        """
        cap = NO_WRAP_DEG * self.gain / self.plausible_max_gain
        need = min(abs(float(error_degrees)), cap) / self.gain
        hold = (need - FIXED_DEG) / RATE_DEG_PER_SEC
        return min(MAX_HOLD_SEC, max(MIN_HOLD_SEC, hold))

    def should_press(self, error_degrees):
        """True when a press leaves us closer than staying put.

        The smallest press moves min_step_deg, landing at |min_step - err|.
        That beats |err| only while err > min_step/2. This is the whole reason
        the loop terminates: with a hardcoded floor, a gain of 2.4 makes the
        real floor 37 degrees and every error between 8 and 37 becomes
        uncorrectable — press, overshoot, press back, forever.
        """
        return abs(float(error_degrees)) > self.stop_threshold_deg

    def plan(self, error_degrees):
        """(action, hold_seconds) for one correction, or None to stop."""
        if not self.should_press(error_degrees):
            return None
        action = "look_right" if error_degrees > 0 else "look_left"
        return action, self.predict_hold(error_degrees)

    def __repr__(self):
        return (f"GainEstimator(gain={self.gain:.2f}, n={len(self._samples)}, "
                f"accepted={self.accepted}, rejected={self.rejected})")


def _noop(*a, **k):
    pass


def run_turn(target_deg, press, read_bearing, estimator=None, max_iters=8,
             settle_sec=0.8, sleep=time.sleep, log=_noop, confirm_stop=True):
    """Turn to `target_deg`. Returns the final measured bearing, or None.

    `press(action, hold_seconds=..., post_delay=...)` and `read_bearing()`
    (zero-arg, returns float|None) are injected, so this module needs no
    screen, no PIL and no game. The caller keeps its own focus and
    dead-stream gates around them — those abort a turn, they do not steer it.

    Pass the SAME `estimator` to every turn on a route. The scale belongs to
    the window, not to the turn: measured over 200 turns at 2.4x, keeping one
    estimator finished at 6.4 degrees in 1.4 presses against 10.7 degrees in
    2.5 presses when it was reset per turn.

    RETURNS A FRESH MEASUREMENT, never the closest bearing seen.
    compass.turn_to returns `best` on exhaustion, but it presses on its last
    iteration too, so `best` is at least one press stale — it names a heading
    the camera has already left. In the trace above it "gave up, best was 18
    degrees off"; simulated at a 3-iteration budget, that habit misreports the
    final heading by 67 degrees at 2.4x, where reading once more misreports by
    2. Returns None only if the compass cannot be read at all, which keeps
    compass's contract: an unknown heading means do not walk.

    Wiring it into compass.turn_to, which keeps its own focus and dead-press
    gates, is one call:

        turn_gain.run_turn(target_deg, press,
                           lambda: read_bearing(capture()),
                           estimator=_GAIN, log=log)
    """
    est = estimator if estimator is not None else GainEstimator()
    best = None
    pending = None          # (hold, bearing_before, sign) of an unmeasured press
    stop_vote = None        # bearing of a read that already wanted to stop
    current = None
    for i in range(max_iters):
        corroborated = False    # did a press we predicted vouch for this read?
        sleep(settle_sec)
        current = read_bearing()
        if current is None:
            # Deliberately does NOT drop `pending`: no press happened, so the
            # next successful read still measures the same press, just after
            # more settling. The bounds check is what protects the model.
            log(f"    turn: bearing unreadable (attempt {i + 1})")
            continue
        if pending is not None:
            hold_prev, before, sign = pending
            moved = angular_error(before, current) * sign
            ok = est.update(hold_prev, moved)
            log(f"    turn: press({hold_prev:.2f}s) moved {moved:+.0f} vs "
                f"{est.model_deg(hold_prev, est.gain):.0f} predicted -> "
                f"{'gain %.2f' % est.gain if ok else 'REJECTED (implausible)'}")
            # A rejected sample is dropped from the MODEL but still steered
            # on: re-reading instead (keeping the press pending and looking
            # again) was tried and measured, and came out a wash — it costs an
            # iteration exactly when iterations are scarce.
            corroborated = ok
            pending = None

        err = angular_error(current, target_deg)
        if best is None or abs(err) < abs(best[1]):
            best = (current, err)

        if not est.should_press(err):
            # A wild OCR inside the stop band ends the turn pointing anywhere,
            # so a read that nothing vouches for has to say it twice. A read
            # that a measured press already agreed with is corroborated
            # already; making it repeat itself costs an iteration for nothing,
            # which measurably HURT the low-gain cases in simulation.
            if (not confirm_stop or corroborated
                    or (stop_vote is not None
                        and abs(angular_error(stop_vote, current)) <= CONFIRM_AGREE_DEG)):
                log(f"    turn: {current:.0f} (target {target_deg:.0f}, "
                    f"err {err:+.0f}) OK, gain {est.gain:.2f}")
                return current
            stop_vote = current
            continue
        stop_vote = None

        action, hold = est.plan(err)
        log(f"    turn: {current:.0f} -> target {target_deg:.0f} "
            f"(err {err:+.0f}), {action} {hold:.2f}s at gain {est.gain:.2f}")
        pending = (hold, current, 1.0 if err > 0 else -1.0)
        press(action, hold_seconds=hold, post_delay=0.3)

    # Out of corrections. The camera is wherever the last press left it and
    # NOBODY HAS MEASURED THAT. compass.turn_to reports the closest bearing it
    # saw instead, which is at least one press stale: that is how a turn that
    # ended ~100 degrees out got logged as "best was 18 degrees off". Spend one
    # more read rather than hand back a number that was true a press ago.
    for _ in range(VERIFY_READS):
        sleep(settle_sec)
        current = read_bearing()
        if current is not None:
            log(f"    turn: out of iterations at {current:.0f} (err "
                f"{angular_error(current, target_deg):+.0f}); closest seen "
                f"was {best[0]:.0f} (err {best[1]:+.0f})" if best else
                f"    turn: out of iterations at {current:.0f}")
            return current
    log("    turn: out of iterations AND the compass will not read — the "
        "heading is unknown, do not walk on it")
    return None
