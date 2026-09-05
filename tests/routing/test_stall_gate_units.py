"""The stall gate must compare GREY LEVELS against a grey-level threshold.

THE BUG, found 2026-09-05. `walk_link` did

    best = max(best, best2)      # best  = GREY LEVELS (slow_traverse._change,
                                 #         np.abs(a-b).mean() over 0-255)
                                 # best2 = PIXELS (pose.displacement, RANSAC
                                 #         median inlier displacement)
    if best < STALL_CHANGE:      # ...against a bar calibrated in GREY LEVELS

Two unrelated quantities carried in one variable and tested against one number.
This is the seventh threshold defect of this family on the project and the first
that is a UNITS mismatch rather than a badly-placed bar — the worst kind,
because no amount of retuning the number fixes a wrong quantity.

THE TWO POPULATIONS, both measured, both pinned below.

1. PIXELS — pose.py's own calibration, n=23 and n=10, captured through
   compass.fast_capture() so the JPEG artefacts match production:

       perfectly stationary, no input   median  3.58px   MAX  8.80px
       after a single 0.2s step         median 38.89px   MIN 32.25px

   So a STATIONARY frame pair can read 8.80px. Against a 6.0 bar that is
   "moved enough, not blocked", while pose.same_pose (tol 16.85px) calls the
   same pair THE SAME POSE. Two modules, one frame pair, opposite answers.

2. PIXELS — the escape ladder's own outcomes, harvested 2026-09-05 from the 85
   ladder episodes in overnight/{streak,streak2,failframes,newleg,
   phase1/step3}.log:

       FAILED  ladders  n=65   best2 = {0.0: 63,  4.3: 1,  5.9: 1}
       CLEARED ladders  n=20   best2 = 21.4 .. 917.5

   NOTE THE CENSORING: the CLEARED side is not independent evidence for a 20px
   bar, because `_slip_past` returns the instant a rung reaches
   SLIP_PROGRESS_PX. Fitting a threshold to it would be measuring the loop's
   own exit condition (CLAUDE.md 10.6, the vacuous statistic). The independent
   evidence for 20.0 is population 1: it sits inside 8.80 -> 32.25.

WHAT THE MISMATCH ACTUALLY COST: nothing yet, and that is the point. The failed
population tops out at 5.9px against the 6.0 bar — a margin of 0.1px — so at
STALL_CHANGE = 6.0 it never once changed an outcome on disk. It gave the right
answer because 6.0 grey-levels happens to land in the same empty band as 20.0
pixels. At STALL_CHANGE = 2.5 it would have falsely cleared 2 of 65.

THE FIX is not a new number. `_slip_past` already applies the correct pixel
threshold and reports its verdict as `how`; the caller takes that verdict
instead of laundering the ladder's magnitude through a grey-level bar.
"""
import os
import os as _os
import sys
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw
import worldmap

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# --------------------------------------------------------------------------
# THE MEASURED POPULATIONS. Literals, so nothing here can be made true by
# editing the constant under test (CLAUDE.md 10.11).
# --------------------------------------------------------------------------
# pose.py, 2026-09-02, n=23 stationary / n=10 one 0.2s step.
STATIONARY_PX_MEDIAN = 3.58
STATIONARY_PX_MAX = 8.80
ONE_REAL_STEP_PX_MIN = 32.25
# The escape ladder's own outcomes, n=85 episodes off the overnight logs.
LADDER_FAILED_PX = [0.0] * 63 + [4.3, 5.9]
LADDER_CLEARED_PX_MIN = 21.4
# slow_traverse._change over 20 runs of office_corridor -> office_door step 7/7.
# GREY LEVELS. Deliberately overlapping STALL_CHANGE — see test_stall_threshold.
MOVING_GREY = [3.1, 5.5, 5.7, 5.7, 5.8, 6.1, 6.3, 6.3, 6.5, 6.5, 6.6, 6.9, 6.9,
               7.0, 7.1, 7.2, 7.3, 7.3, 7.6, 7.9]


# --------------------------------------------------------------------------
# 1. THE UNITS ARE DECLARED, AND THE PIXEL BAR SITS IN THE PIXEL GAP.
# --------------------------------------------------------------------------
check("STALL_CHANGE declares its units, so the next reader cannot guess",
      getattr(gw, "STALL_CHANGE_UNITS", None) == "grey_levels")

# SLIP_PROGRESS_PX is the pixel-domain bar, and it must sit between the two
# measured PIXEL populations — the rule STALL_CHANGE could never satisfy for
# this quantity because it is not measured in pixels at all.
check("SLIP_PROGRESS_PX sits between the measured pixel populations "
      f"({STATIONARY_PX_MAX} stationary max, {ONE_REAL_STEP_PX_MIN} smallest "
      f"real step)",
      STATIONARY_PX_MAX < gw.SLIP_PROGRESS_PX < ONE_REAL_STEP_PX_MIN)

# THE MISMATCH, stated as data rather than as prose: STALL_CHANGE does NOT sit
# in that gap. It is below the stationary noise ceiling, so if it were ever
# applied to pixels a motionless character would read as moving.
check("STALL_CHANGE is BELOW the stationary pixel ceiling — proof it cannot "
      "serve as a pixel threshold",
      gw.STALL_CHANGE < STATIONARY_PX_MAX)
# 6.0 sits between the stationary median (3.58) and the stationary max (8.80),
# which is exactly the ambiguity that made the mismatch invisible: most
# motionless frame pairs read UNDER it, so the wrong comparison mostly gave the
# right answer. What is assertable is that the population STRADDLES it.
check("the stationary pixel population straddles STALL_CHANGE — a motionless "
      "character reads both sides of it",
      STATIONARY_PX_MEDIAN < gw.STALL_CHANGE < STATIONARY_PX_MAX)


# --------------------------------------------------------------------------
# 2. THE COUNTERFACTUAL, from the harvested ladder outcomes.
# --------------------------------------------------------------------------
# A failed ladder whose best2 lands at or above STALL_CHANGE would have cleared
# the gate under `max(best, best2)`. At 6.0 that is nobody; at 2.5 it is two.
false_clears_at_6 = [x for x in LADDER_FAILED_PX if x >= 6.0]
false_clears_at_25 = [x for x in LADDER_FAILED_PX if x >= 2.5]
check("at 6.0 the old mismatch falsely cleared 0 of the 65 failed ladders — it "
      "was latent, not benign",
      len(false_clears_at_6) == 0)
check("at 2.5 it would have falsely cleared exactly 2 of 65, so the A/B's "
      "losing arm carried a confound the winning arm did not",
      len(false_clears_at_25) == 2)
check("the failed-ladder population comes within 0.1px of the 6.0 bar",
      abs(max(LADDER_FAILED_PX) - 5.9) < 1e-9)
# And the ladder's own verdict separates the two populations cleanly, which is
# why it is the right thing to trust.
check("the ladder's own verdict separates its outcomes with a real gap "
      f"({max(LADDER_FAILED_PX)} failed vs {LADDER_CLEARED_PX_MIN} cleared)",
      max(LADDER_FAILED_PX) < LADDER_CLEARED_PX_MIN)

# HOW CLOSE IT CAME. Episode maxima never landed in the [6.0, 20.0) band, but
# INDIVIDUAL RUNGS did, 13 times across 9 episodes:
#
#     [14.9, 27.4]   [3.0, 7.2, 8.7, 11.4, 38.9]   [16.6, 35.8]
#     [7.2, 14.7, 8.8, 33.7]   [9.0, 26.1]   [4.6, 17.9, 33.4]
#     [14.9, 55.0]   [9.4, 1.7, 1.7, 68.4]   [14.1, 31.1]
#
# Every one was rescued by a LATER rung passing 20px. Had any of those ladders
# exhausted its five rungs with 14.9 or 17.9 as its best, `max(best, best2)`
# would have declared the leg unblocked on a pixel count measured against a
# grey-level bar — and `pose.same_pose` (tol 16.85px) would have called the
# very same frame pair THE SAME POSE. The bug was one unlucky ladder from
# firing, which is why "0 occurrences on disk" is not a reason to leave it.
RUNGS_IN_BAND = [14.9, 7.2, 8.7, 11.4, 16.6, 7.2, 14.7, 8.8, 9.0, 17.9, 14.9,
                 9.4, 14.1]
check("13 individual rungs did land in the false-clear band — the gap in the "
      "EPISODE maxima is luck, not structure",
      len(RUNGS_IN_BAND) == 13
      and all(6.0 <= r < gw.SLIP_PROGRESS_PX for r in RUNGS_IN_BAND))
# pose.SAME_POSE_PX is the other module's verdict on the same numbers. The two
# disagreeing on one frame pair is the clearest statement of the mismatch.
import pose as _pose
_both = [r for r in RUNGS_IN_BAND
         if r <= _pose.SAME_POSE_PX and r > gw.STALL_CHANGE]
check(f"and pose.same_pose would call {len(_both)} of them the SAME POSE while "
      f"the old gate called them progress — two modules, one frame pair, "
      f"opposite answers",
      len(_both) > 0)


# --------------------------------------------------------------------------
# 3. THE BEHAVIOUR. Drive walk_link with a wall and a controllable ladder.
# --------------------------------------------------------------------------
class Rig:
    """A leg that pushes and never moves the view (GREY delta below the bar)."""

    def __init__(self, grey, ladder_px, ladder_how):
        self.grey, self.ladder_px, self.ladder_how = grey, ladder_px, ladder_how
        self.walks = []

    def turn_to(self, target, read_heading, capture, log=print, **kw):
        return target, []

    def walk_leg(self, lx, ly, seconds, capture, read_heading, label="",
                 log=print, step_sec=None):
        self.walks.append(label)
        return seconds, self.grey, []


def run(grey, ladder_px, ladder_how, steps=3, wait_out=None):
    """Walk a leg; return (hazard kinds, number of pushes, blockers)."""
    m = worldmap.WorldMap()
    m.mark("s")
    m.mark("e")
    m.connect("s", "e", [{"bearing": 0.0, "dur": 0.5, "speed": 0.25}] * steps)
    rig = Rig(grey, ladder_px, ladder_how)

    saved = {k: sys.modules.get(k) for k in
             ("slow_traverse", "compass", "walk_steps", "pose",
              "input_controller")}
    sys.modules["slow_traverse"] = types.SimpleNamespace(
        turn_to=rig.turn_to, walk_leg=rig.walk_leg)
    sys.modules["compass"] = types.SimpleNamespace(
        read_bearing=lambda img: 90.0, fast_capture=lambda: object())
    sys.modules["walk_steps"] = types.SimpleNamespace(
        turn_to=lambda t, log=print, **kw: None, read_heading=lambda: 90.0,
        walk_forward=lambda *a, **k: None)
    sys.modules["pose"] = types.SimpleNamespace(displacement=lambda a, b: 0.0)
    sys.modules["input_controller"] = types.SimpleNamespace(
        press=lambda a, **kw: None)

    real_slip, real_sleep = gw._slip_past, gw.time.sleep
    real_wait = gw.WAIT_OUT_MOVERS
    ladder_calls = []

    def _fake_slip(*a, **k):
        ladder_calls.append(1)
        return (ladder_px, ladder_how)

    gw._slip_past = _fake_slip
    gw.time.sleep = lambda *a: None
    if wait_out is not None:
        gw.WAIT_OUT_MOVERS = wait_out
    try:
        leg = gw.walk_link(m, "s", "e", lambda: object(), lambda: 90.0,
                           log=lambda *a: None)
    finally:
        gw._slip_past, gw.time.sleep = real_slip, real_sleep
        gw.WAIT_OUT_MOVERS = real_wait
        for k, v in saved.items():
            if v is not None:
                sys.modules[k] = v
            else:
                sys.modules.pop(k, None)
    return ([h.kind for h in leg["hazards"]], len(rig.walks), leg["blockers"],
            len(ladder_calls))


# THE DEMONSTRATION FROM THE BUG REPORT. A wall (grey delta 2.0, well under the
# 6.0 bar), and an escape ladder that FAILED — `how` is None — but whose best
# rung measured somewhere in the pixel noise band. Under `max(best, best2)` the
# 6.50 and 8.80 cases silently un-blocked the leg.
for px in (1.00, STATIONARY_PX_MEDIAN, 6.50, STATIONARY_PX_MAX):
    kinds, pushes, blockers, _ = run(2.0, px, None)
    check(f"a FAILED ladder measuring {px:.2f}px still reports BLOCKED "
          f"(it is {'above' if px >= gw.STALL_CHANGE else 'below'} "
          f"STALL_CHANGE, which is irrelevant — wrong units)",
          "BLOCKED" in kinds)
    check(f"  ...and it stops pushing into the wall ({pushes} pushes)",
          pushes <= 2)

# A ladder that genuinely CLEARED must NOT be reported blocked — otherwise this
# fix would just break the escape. `how` non-None is the ladder's own verdict,
# reached only when a rung passed SLIP_PROGRESS_PX.
kinds, pushes, blockers, _ = run(2.0, 27.4, "jump")
check("a ladder that CLEARED does not report BLOCKED — the escape still works",
      "BLOCKED" not in kinds)
check("  ...and the leg runs to the end", pushes == 3)
check("  ...and the blocker is recorded with its units named in the key",
      blockers and blockers[0]["cleared_by"] == "jump"
      and blockers[0]["displaced_px"] == 27.4)

# WITH THE LADDER TURNED OFF the gate must still fire. `escaped` starts False
# and only the ladder may set it; initialising it True would leave a wall
# undetected for every run with WAIT_OUT_MOVERS off — a flag that exists to be
# flipped in an A/B, so the branch is reachable in production, and "the code did
# nothing and doing nothing looked exactly like working" is the house failure.
kinds, pushes, blockers, ladder_calls = run(2.0, 999.0, "jump", wait_out=False)
check("with WAIT_OUT_MOVERS off a wall is still reported BLOCKED",
      "BLOCKED" in kinds)
check("  ...and the escape ladder was never consulted", ladder_calls == 0)
check("  ...and no blocker was invented for an encounter that never happened",
      blockers == [])

# THE POSITIVE CONTROL FOR THE TEST ITSELF: a leg that is plainly moving (grey
# delta above the bar) must never be called blocked, or the checks above would
# pass for a walk_link that reports BLOCKED unconditionally.
kinds, pushes, _, _ = run(40.0, 0.0, None)
check("POSITIVE CONTROL: a leg with a healthy GREY delta is never BLOCKED",
      "BLOCKED" not in kinds and pushes == 3)

# AND THE GREY QUANTITY MUST STILL DRIVE THE GATE. Every value in the measured
# moving population that sits under STALL_CHANGE still fires the gate, exactly
# as test_stall_threshold pins — this change must not have quietly moved that.
under = [v for v in MOVING_GREY if v < gw.STALL_CHANGE]
check("the grey-level gate is untouched: the same 5 of 20 moving pushes still "
      "fire it, as the A/B settled",
      len(under) == 5)


# --------------------------------------------------------------------------
# 4. THE MIXING ITSELF IS GONE FROM THE SOURCE.
# --------------------------------------------------------------------------
# A behavioural test cannot catch a reintroduction that happens to be latent on
# these fixtures, and the whole finding is that the bug WAS latent for months.
# So pin the shape of the code too.
_src = open(_os.path.join(_ROOT, "graph_walk.py"), encoding="utf-8").read()
_walk_link = _src[_src.index("def walk_link("):_src.index("def face_the_table(")]
_code = "\n".join(ln for ln in _walk_link.splitlines()
                  if not ln.lstrip().startswith("#"))
check("walk_link no longer max()es the ladder's PIXEL figure into the "
      "grey-level `best`",
      "max(best, best2)" not in _code)
# Pin the ASSIGNMENT, not just the phrase. `how is not None` also appears in
# the log line below it, so the looser check passed for a walk_link that had
# gone back to `escaped = best2 >= STALL_CHANGE`.
check("walk_link consumes the ladder's own verdict (`how`) instead",
      "escaped = how is not None" in _code)
# ...and the diagnostic must not depend on `escaped` and `how` agreeing. The
# obvious phrasing, `'CLEARED by ' + how if escaped else ...`, raises TypeError
# the moment they diverge — on the live console, inside the log line added to
# explain the failure.
check("the escape-ladder log line cannot raise when `how` is None",
      "'CLEARED by ' + how if escaped" not in _code)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
