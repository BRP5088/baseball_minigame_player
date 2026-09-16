"""Turn-gain estimation and the stopping rule, proved in simulation. Offline.

WHY THIS EXISTS
---------------
The camera turn is closed-loop on an OCR'd compass, and the actuator's scale
changes with conditions (fullscreen turns ~2.4x faster than the fitted
constants), so the loop learns a multiplier at runtime. That learning is what
failed. Live trace, target 85, gain shown after each update:

    349 -> press -> moved 140 vs  96 predicted -> gain 1.27
    128 -> press -> moved  62 vs  43 predicted -> gain 1.59
     67 -> press -> moved  48 vs  22 predicted -> gain 2.75
    114 -> press -> moved 163 vs  37 predicted -> gain 6.00   (clamped at max)
    278 -> press -> moved  30 vs 167 predicted -> gain 3.05
    308 -> press -> bearing unreadable
    313 -> press -> moved   5 vs 137 predicted -> gain 1.29
    gave up after 8 iterations, best was 18 degrees off

`gain *= (1 + 0.6*(moved/predicted - 1))` believes every sample. Two of those
are physically impossible — 163 degrees off a ~0.00s hold is 12x the fitted
rate, 5 degrees off a 0.15s hold is less than one press's fixed cost — and
each rewrote the model. The compass is OCR: a STATIONARY camera has been read
as 342, 342, 157, 341, 251, so nonsense samples are routine, not exceptional.

These tests are not arithmetic against the constants (a threshold asserted
against the constant it came from passes for every value). They run a
SIMULATED camera — affine response, unknown scale k, 12% per-press noise, 8%
of reads wild or None — for a few hundred randomised turns per scale, and
compare OUTCOMES: final error against the camera's TRUE bearing, presses
spent, and how often a turn ends outside what that scale can physically
deliver. compass.turn_to's loop is ported faithfully below as the baseline.

    python3 test_turn_gain.py            # assert
    python3 test_turn_gain.py --bench    # assert and print the head-to-head
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
import random
import statistics
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import turn_gain as tg
from turn_gain import angular_error

fails = []
BENCH = "--bench" in sys.argv

# --- the simulated camera --------------------------------------------------
# True response is k*(13.5 + 207*hold) with a per-press multiplicative error,
# read back through a sensor that is sometimes nonsense. k is what the
# estimator has to discover; nothing under test is told it.
PRESS_NOISE = 0.12          # +-12% on every press
BAD_READ_P = 0.08           # 8% of reads are junk...
NONE_FRACTION = 0.4         # ...of which this share are None, the rest wild
OCR_SIGMA = 1.5             # degrees of jitter on a good read
K_VALUES = (1.0, 2.4, 0.5, 4.0)     # windowed, fullscreen, and two stresses
TRIALS = 400
MAX_ITERS = 8


class FakeCamera:
    """Affine camera + flaky bearing sensor. No screen, no game, no sleeps."""

    def __init__(self, k, rng, start):
        self.k = k
        self.rng = rng
        self.bearing = start % 360.0
        self.presses = 0
        self.reads = 0

    def press(self, action, hold_seconds=0.0, post_delay=0.0):
        self.presses += 1
        # The keypress floor is physical: 0.00s and 0.01s deliver the same
        # ~15.6 degrees. There is deliberately NO upper clamp — a 4s hold
        # really does spin the camera several times, and the baseline commands
        # holds like that once its gain has been driven down.
        hold = max(tg.MIN_HOLD_SEC, float(hold_seconds))
        step = (self.k * (tg.FIXED_DEG + tg.RATE_DEG_PER_SEC * hold)
                * self.rng.uniform(1 - PRESS_NOISE, 1 + PRESS_NOISE))
        if action == "look_left":
            step = -step
        self.bearing = (self.bearing + step) % 360.0

    def read(self):
        self.reads += 1
        r = self.rng.random()
        if r < BAD_READ_P * NONE_FRACTION:
            return None
        if r < BAD_READ_P:
            return self.rng.uniform(0.0, 360.0)      # wild misread
        return (self.bearing + self.rng.gauss(0.0, OCR_SIGMA)) % 360.0


# --- the baseline: compass.turn_to's control logic, ported faithfully ------
# Verbatim in every respect that touches steering: the gain update and its
# [0.2, 6.0] clamp, the `moved > 2 and predicted > 2` gate, abs() on the
# measured movement, `last` surviving an unreadable frame, the fixed
# MIN_TURN_STEP_DEG/2 stop, the affine hold, and returning the closest bearing
# SEEN on exhaustion. Only the focus check and the frame-difference dead-press
# detector are omitted: both can only abort a turn, neither steers it, and
# neither can be simulated without images.
BASE_MIN_TURN_STEP_DEG = 16.0


def baseline_turn(target_deg, cam, estimator=None, max_iters=MAX_ITERS):
    gain = 1.0
    best = None
    last = None
    for _ in range(max_iters):
        current = cam.read()
        if current is None:
            continue
        if last is not None:
            hold_prev, before_deg = last
            moved = abs(angular_error(before_deg, current))
            predicted = (tg.FIXED_DEG * gain
                         + tg.RATE_DEG_PER_SEC * gain * hold_prev)
            if moved > 2.0 and predicted > 2.0:
                gain *= (1.0 + 0.6 * (moved / predicted - 1.0))
                gain = min(6.0, max(0.2, gain))
            last = None
        err = angular_error(current, target_deg)
        if best is None or abs(err) < abs(best[1]):
            best = (current, err)
        if abs(err) <= BASE_MIN_TURN_STEP_DEG / 2:
            return current
        hold = max(0.0, (abs(err) - tg.FIXED_DEG * gain)
                   / (tg.RATE_DEG_PER_SEC * gain))
        last = (hold, current)
        cam.press("look_right" if err > 0 else "look_left", hold_seconds=hold)
    if best is not None:
        return best[0]
    return cam.read()


def new_turn(target_deg, cam, estimator=None, max_iters=MAX_ITERS, **policy):
    # sleep=lambda: None. run_turn settles 0.8s per iteration in the game, and
    # an earlier attempt at this work timed out because the loop under test
    # actually slept through the simulation.
    return tg.run_turn(target_deg, cam.press, cam.read, estimator=estimator,
                       max_iters=max_iters, sleep=lambda _s: None, **policy)


# --- running the comparison ------------------------------------------------
def achievable_tol(k):
    """Tolerance a turn at scale k can physically meet.

    Half a minimum step is the floor no controller can beat: at k=4 one press
    moves 62 degrees, so ~31 is the best any policy can guarantee, plus a few
    degrees for press noise. Scoring that against the 12-degree corridor
    tolerance would only measure k. Both algorithms are scored on the same
    number.
    """
    step = k * (tg.FIXED_DEG + tg.RATE_DEG_PER_SEC * tg.MIN_HOLD_SEC)
    return max(12.0, 0.6 * step + 4.0)


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.95 * len(xs)))] if xs else float("nan")


def run_suite(algo, k, trials=TRIALS, seed0=0, persistent=False,
              max_iters=MAX_ITERS, **kw):
    """Paired trials: both algorithms see the same seeds, starts and targets."""
    shared = tg.GainEstimator() if persistent else None
    tol = achievable_tol(k)
    true, presses, reads, lie = [], [], [], []
    fail = fail12 = nones = 0
    for t in range(trials):
        rng = random.Random(seed0 + t)
        start, target = rng.uniform(0, 360), rng.uniform(0, 360)
        cam = FakeCamera(k, rng, start)
        est = shared if persistent else tg.GainEstimator()
        got = algo(target, cam, est, max_iters=max_iters, **kw)
        # The metric is where the camera REALLY ended up, not what the
        # controller says. Those differ, and the difference is the point of
        # assertion 5.
        err = abs(angular_error(cam.bearing, target))
        true.append(err)
        presses.append(cam.presses)
        reads.append(cam.reads)
        if got is None:
            nones += 1
        else:
            lie.append(abs(angular_error(got, cam.bearing)))
        fail += err > tol
        fail12 += err > 12.0
    return {"mean": statistics.fmean(true), "p95": p95(true),
            "presses": statistics.fmean(presses),
            "reads": statistics.fmean(reads),
            "failrate": fail / trials, "fail12": fail12 / trials,
            "none": nones / trials,
            "lie": statistics.fmean(lie) if lie else float("nan")}


results = {k: {"baseline": run_suite(baseline_turn, k),
               "new": run_suite(new_turn, k)} for k in K_VALUES}

if BENCH:
    print(f"\n{TRIALS} randomised turns per scale, {MAX_ITERS} iterations max, "
          f"{PRESS_NOISE:.0%} press noise, {BAD_READ_P:.0%} bad reads")
    print(f"{'k':>5} {'algo':<9} {'mean':>6} {'p95':>7} {'fail':>6} "
          f"{'>12deg':>7} {'press':>6} {'reads':>6} {'stale':>6}")
    for k in K_VALUES:
        for name in ("baseline", "new"):
            s = results[k][name]
            print(f"{k:>5} {name:<9} {s['mean']:>6.1f} {s['p95']:>7.1f} "
                  f"{s['failrate']:>6.1%} {s['fail12']:>7.1%} "
                  f"{s['presses']:>6.2f} {s['reads']:>6.2f} {s['lie']:>6.1f}")
        print(f"{'':>5} {'':<9} tolerance {achievable_tol(k):.0f} deg "
              f"(half a minimum step at this scale, +4 for noise)")

# --- 1. the real trace: impossible samples must be thrown away -------------
# Holds recovered from the trace by inverting the printed prediction against
# the gain in force at the time (predicted = gain*(13.5 + 207*hold)).
TRACE = [  # (hold_s, degrees_moved, must_be_believed)
    (0.399, 140.0, True),    # 140 vs 96 predicted at gain 1.00 -> implies 1.46x
    (0.098,  62.0, True),    # 62 vs 43 at gain 1.27             -> 1.83x
    (0.000,  48.0, True),    # 48 vs 22 at gain 1.59             -> 3.08x
    (0.000, 163.0, False),   # 163 vs 37 at gain 2.75            -> 10.5x, absurd
    (0.069,  30.0, True),    # 30 vs 167 at gain 6.00            -> 1.08x
    (0.152,   5.0, False),   # 5 vs 137 at gain 3.05  -> 0.11x, under one press
]
est = tg.GainEstimator()
for hold, moved, believable in TRACE:
    if est.update(hold, moved) != believable:
        fails.append(
            f"trace sample (hold {hold:.3f}s, moved {moved:.0f}) was "
            f"{'believed' if believable else 'rejected'} the wrong way — a "
            f"press cannot move less than its fixed cost nor 12x the fitted "
            f"rate, and believing either is what drove the live gain to its "
            f"clamp and back")
# The run that produced this trace was fullscreen, i.e. genuinely ~2.4x. The
# live loop ended it at 1.29 having passed through 6.00.
if not 1.2 <= est.gain <= 3.5:
    fails.append(f"replaying the real trace left the gain at {est.gain:.2f}; "
                 f"that run was fullscreen (~2.4x), so this is not tracking it")
# A press that reads as having moved BACKWARDS is a bad read or a lost input,
# never evidence about the scale.
if tg.GainEstimator().update(0.2, -55.0):
    fails.append("a backwards press was folded into the gain")

# --- 2. estimator against estimator, on identical samples -----------------
# The loops differ in more than the estimator, so compare the estimators alone:
# same stream of (hold, measured movement) pairs into both update rules.
def sample_stream(k, rng, n=16):
    out = []
    for _ in range(n):
        hold = rng.choice([0.01, 0.03, 0.08, 0.15, 0.30, 0.50])
        move = (k * (tg.FIXED_DEG + tg.RATE_DEG_PER_SEC * hold)
                * rng.uniform(1 - PRESS_NOISE, 1 + PRESS_NOISE))
        if rng.random() < BAD_READ_P:
            measured = angular_error(0.0, rng.uniform(0, 360))   # wild OCR
        else:
            # A real reading is mod 360: a press that turns more than half a
            # circle reads as having gone the other way.
            measured = angular_error(0.0, move + rng.gauss(0.0, OCR_SIGMA))
        out.append((hold, measured))
    return out


def baseline_gain(stream):
    gain = 1.0
    for hold, measured in stream:
        moved = abs(measured)
        predicted = tg.FIXED_DEG * gain + tg.RATE_DEG_PER_SEC * gain * hold
        if moved > 2.0 and predicted > 2.0:
            gain *= (1.0 + 0.6 * (moved / predicted - 1.0))
            gain = min(6.0, max(0.2, gain))
    return gain


for k in (1.0, 2.4, 4.0, 0.5):
    mine, theirs = [], []
    for s in range(300):
        stream = sample_stream(k, random.Random(4000 + s))
        e = tg.GainEstimator()
        for hold, measured in stream:
            e.update(hold, measured)
        mine.append(abs(e.gain - k))
        theirs.append(abs(baseline_gain(stream) - k))
    mine_err, their_err = statistics.fmean(mine), statistics.fmean(theirs)
    if mine_err > 0.25 * k:
        fails.append(f"k={k}: after 16 presses the estimate is off by "
                     f"{mine_err:.2f} on average — it is not converging")
    if mine_err >= their_err:
        fails.append(f"k={k}: estimate off by {mine_err:.2f} against the "
                     f"current rule's {their_err:.2f} on the SAME samples")
    if BENCH:
        print(f"  estimator only, k={k}: |error| {mine_err:.2f} vs "
              f"{their_err:.2f} for the current rule (300 streams, 16 presses)")

# --- 3. a lone bad sample must not move the estimate much ------------------
est = tg.GainEstimator()
for _ in range(4):
    est.update(0.1, 2.4 * (tg.FIXED_DEG + tg.RATE_DEG_PER_SEC * 0.1))
clean = est.gain
est.update(0.1, 5.9 * (tg.FIXED_DEG + tg.RATE_DEG_PER_SEC * 0.1))
if abs(est.gain - clean) > 0.35:
    fails.append(f"one in-bounds outlier moved the gain {clean:.2f} -> "
                 f"{est.gain:.2f}; no single sample may swing the model")

# --- 4. head to head, per scale -------------------------------------------
for k in K_VALUES:
    b, n = results[k]["baseline"], results[k]["new"]
    # Where the fitted constants are wrong, the whole point, the improvement
    # has to be large — not a rounding win.
    if k in (2.4, 4.0):
        if n["mean"] > 0.6 * b["mean"]:
            fails.append(f"k={k}: mean final error {n['mean']:.1f} vs the "
                         f"current algorithm's {b['mean']:.1f} — the scale is "
                         f"not being learned")
        if n["p95"] > 0.5 * b["p95"]:
            fails.append(f"k={k}: p95 final error {n['p95']:.1f} vs "
                         f"{b['p95']:.1f} — the tail is still there")
    # Where they are right, it must not COST anything material to have learned
    # that. 1 degree of mean error and 1 point of failure rate is the slack.
    elif n["mean"] > b["mean"] + 1.0 or n["failrate"] > b["failrate"] + 0.01:
        fails.append(f"k={k}: {n['mean']:.1f} deg / {n['failrate']:.1%} "
                     f"failures against {b['mean']:.1f} / {b['failrate']:.1%} "
                     f"— adapting is costing more than it earns where the "
                     f"fitted constants were already right")
    if n["failrate"] > 0.05:
        fails.append(f"k={k}: {n['failrate']:.1%} of turns ended outside "
                     f"{achievable_tol(k):.0f} deg, which this scale can "
                     f"physically deliver")

# --- 5. the stopping rule has to scale with the learned gain ---------------
# At 2.4x one press moves 37 degrees, so every error between 8 and 37 is
# UNCORRECTABLE. A loop with a hardcoded 16-degree floor chases them anyway:
# press, overshoot, press back. That is the limit cycle seen live, and it
# shows up as presses spent, not as final error alone.
for k in (2.4, 4.0):
    if results[k]["new"]["presses"] > 0.6 * results[k]["baseline"]["presses"]:
        fails.append(
            f"k={k}: {results[k]['new']['presses']:.2f} presses per turn "
            f"against {results[k]['baseline']['presses']:.2f} — still chasing "
            f"errors smaller than one minimum step")
if results[4.0]["new"]["presses"] > 4.0:
    fails.append(f"at 4x (minimum step 62 deg) the loop still spends "
                 f"{results[4.0]['new']['presses']:.2f} presses per turn")

# --- 6. the returned bearing must be where the camera actually is ----------
# turn_to returns the CLOSEST bearing SEEN when it runs out of iterations, but
# it presses on its last iteration too, so that reading is stale: it names a
# heading the camera has already left, and the caller walks on it.
for k in K_VALUES:
    if results[k]["new"]["lie"] > 4.0:
        fails.append(f"k={k}: the bearing handed back is "
                     f"{results[k]['new']['lie']:.1f} deg from where the "
                     f"camera really is — the caller would act on a lie")
if results[4.0]["baseline"]["lie"] <= 4.0 * results[4.0]["new"]["lie"]:
    fails.append("the stale-best return was expected to misreport the heading "
                 "badly at 4x and did not — check the baseline port")
# ...and the case that matters is the GIVE-UP path, which 8 iterations rarely
# reach. Squeeze the budget to 3 so nearly every turn ends there: that is where
# reporting the best bearing seen, rather than reading once more, turns a
# 40-degree miss into a logged success.
for k in (1.0, 2.4, 4.0):
    tight = run_suite(new_turn, k, max_iters=3)
    tight_base = run_suite(baseline_turn, k, max_iters=3)
    if tight["lie"] > 8.0:
        fails.append(f"k={k}, budget 3: the bearing handed back on the "
                     f"give-up path is {tight['lie']:.1f} deg from the "
                     f"camera's real heading")
    if k > 1.0 and tight_base["lie"] < 20.0:
        fails.append(f"k={k}, budget 3: the ported baseline misreports by "
                     f"only {tight_base['lie']:.1f} deg — it should be badly "
                     f"stale here, so check the port")
    if BENCH:
        print(f"  k={k}, budget 3 (give-up path): returned bearing is "
              f"{tight['lie']:.1f} deg from the truth, against "
              f"{tight_base['lie']:.1f} for the current algorithm")

# --- 7. learning must persist across turns ---------------------------------
# The scale is a property of the window, not of a turn. compass.turn_to resets
# gain to 1.0 on every call, so it re-learns from scratch, from 2-3 samples,
# for every leg of every walk.
fresh = run_suite(new_turn, 2.4, trials=200, seed0=9000)
kept = run_suite(new_turn, 2.4, trials=200, seed0=9000, persistent=True)
if kept["mean"] >= fresh["mean"] or kept["presses"] >= fresh["presses"]:
    fails.append(f"keeping one estimator across a route did not help: "
                 f"{kept['mean']:.1f} deg / {kept['presses']:.2f} presses vs "
                 f"{fresh['mean']:.1f} / {fresh['presses']:.2f} fresh")
if BENCH:
    print(f"\nk=2.4, 200 turns: one estimator kept across the route "
          f"{kept['mean']:.1f} deg / {kept['presses']:.2f} presses; reset per "
          f"turn {fresh['mean']:.1f} deg / {fresh['presses']:.2f}")

# --- 8. confirming a stop has to earn its extra read -----------------------
# A wild OCR inside the stop band ends the turn pointing anywhere, so a read
# that no measured press vouches for must say it twice.
for k in (1.0, 0.5):
    off = run_suite(new_turn, k, confirm_stop=False)
    on = results[k]["new"]
    if on["mean"] >= off["mean"] or on["failrate"] > off["failrate"]:
        fails.append(f"k={k}: confirming the stop did not pay for itself — "
                     f"{on['mean']:.1f} deg / {on['failrate']:.1%} with, "
                     f"{off['mean']:.1f} / {off['failrate']:.1%} without")
    if BENCH:
        print(f"  k={k} confirm_stop off: mean {off['mean']:.1f} fail "
              f"{off['failrate']:.1%} stale {off['lie']:.1f} | on: mean "
              f"{on['mean']:.1f} fail {on['failrate']:.1%} stale {on['lie']:.1f}")

# --- 9. the scale can change MID-SESSION ----------------------------------
# It did: the trace at the top is a fullscreen run being steered by constants
# fitted windowed. An estimator kept across a route therefore has to
# RE-converge, not lock in on what it learned first. 30 turns, scale switched
# from 1.0x to 2.4x half way, one estimator throughout.
def switched_route(algo, est, seed0=7000, n=30, switch_at=15):
    errs = []
    for t in range(n):
        k = 1.0 if t < switch_at else 2.4
        rng = random.Random(seed0 + t)
        start, target = rng.uniform(0, 360), rng.uniform(0, 360)
        cam = FakeCamera(k, rng, start)
        algo(target, cam, est)
        errs.append(abs(angular_error(cam.bearing, target)))
    return errs


shared = tg.GainEstimator()
mine_route = switched_route(new_turn, shared)
base_route = switched_route(baseline_turn, None)
settled = statistics.fmean(mine_route[18:])
base_settled = statistics.fmean(base_route[18:])
if abs(shared.gain - 2.4) > 0.6:
    fails.append(f"after 15 turns at 2.4x the estimator still reads "
                 f"{shared.gain:.2f} — it locked in on the old scale")
if settled > 12.0:
    fails.append(f"turns 19-30 after the scale changed average "
                 f"{settled:.1f} deg — it never re-converged")
if settled >= 0.5 * base_settled:
    fails.append(f"after the scale changed, {settled:.1f} deg against the "
                 f"current algorithm's {base_settled:.1f} — no better at the "
                 f"exact situation the live trace came from")
if BENCH:
    print(f"\nscale switched 1.0x -> 2.4x at turn 16, one estimator: "
          f"before {statistics.fmean(mine_route[:15]):.1f} deg, turns 16-18 "
          f"{statistics.fmean(mine_route[15:18]):.1f}, turns 19-30 "
          f"{settled:.1f} (current algorithm {base_settled:.1f}), gain now "
          f"{shared.gain:.2f}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
_b = statistics.fmean([results[k]["baseline"]["mean"] for k in K_VALUES])
_n = statistics.fmean([results[k]["new"]["mean"] for k in K_VALUES])
print(f"  {TRIALS} simulated turns at each of k={list(K_VALUES)}: mean final "
      f"error {_n:.1f} deg vs {_b:.1f} for compass.turn_to's loop, and "
      f"{results[2.4]['new']['failrate']:.1%} vs "
      f"{results[2.4]['baseline']['failrate']:.1%} unconverged at 2.4x; the "
      f"live trace's impossible samples are rejected, the stop rule scales "
      f"with the learned gain, a mid-route switch to 2.4x is re-learned within "
      f"~2 turns, and the bearing returned is one measured after the last "
      f"press")
