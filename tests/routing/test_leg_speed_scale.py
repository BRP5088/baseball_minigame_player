"""Walking a leg faster must preserve DISTANCE and respect the speed cap.

Why it exists: 70% of the route's walking time is in the two office legs, and
the biggest single chunk (11.04s) is the leg measured 20/20 reliable. The legs
that actually fail total 2.77s. At 338s per trial, time is the binding
constraint on learning, so the reliable legs are where to buy it back.

The scaling assumes velocity is roughly proportional to stick magnitude. That
is UNVERIFIED — turning is badly non-linear over its range — which is why the
flag ships at 1.0.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


STEPS = [{"bearing": 10.0, "dur": 1.0, "speed": 0.20},
         {"bearing": 12.0, "dur": 0.8, "speed": 0.40},
         {"bearing": 11.0, "dur": 0.5, "speed": 0.43}]


def dist(steps):
    return sum(s["dur"] * s.get("speed", 0.25) for s in steps)


old = gw.LEG_SPEED_SCALE
try:
    gw.LEG_SPEED_SCALE = 1.0
    check("scale 1.0 returns the steps untouched", gw._scaled(STEPS) is STEPS)

    gw.LEG_SPEED_SCALE = 1.5
    s = gw._scaled(STEPS)
    check("scaling shortens the leg",
          sum(x["dur"] for x in s) < sum(x["dur"] for x in STEPS))
    check("DISTANCE is preserved (speed x duration)",
          abs(dist(s) - dist(STEPS)) < 1e-9)
    check("bearings are untouched",
          [x["bearing"] for x in s] == [x["bearing"] for x in STEPS])

    # The cap must bind, or a fast leg walks into turn_curve's non-linear range.
    gw.LEG_SPEED_SCALE = 5.0
    s = gw._scaled(STEPS)
    check("no step exceeds LEG_SPEED_MAX",
          max(x["speed"] for x in s) <= gw.LEG_SPEED_MAX + 1e-9)
    check("a capped step still preserves its own distance",
          all(abs(a["dur"] * a["speed"] - b["dur"] * b["speed"]) < 1e-9
              for a, b in zip(s, STEPS)))
    # The cap is set by REPEATABILITY, not by the median. Measured spread per
    # 0.40s push: ~15px through 0.45, 27 at 0.60, 124 at 0.75, 476 at 0.85.
    # Variance is what makes a dead-reckoned leg miss.
    check("the cap stays in the repeatable range (spread collapses above 0.60)",
          gw.LEG_SPEED_MAX <= 0.60)

    # Never SLOW a leg down by accident.
    gw.LEG_SPEED_SCALE = 0.5
    s = gw._scaled(STEPS)
    check("a scale below 1 does not slow the leg down",
          sum(x["dur"] for x in s) <= sum(x["dur"] for x in STEPS))
finally:
    gw.LEG_SPEED_SCALE = old

check("it ships at 1.0 — unverified assumption, must be A/B'd",
      gw.LEG_SPEED_SCALE == 1.0)

# WIRING: _scaled must actually be APPLIED by the leg executor. Testing the
# helper alone leaves the flag able to be silently disconnected — a mutation
# that removed the call from walk_link passed every check above.
import types

seen = {"scaled": 0}
real_scaled, real_st = gw._scaled, sys.modules.get("slow_traverse")
fake_st = types.ModuleType("slow_traverse")
fake_st.TURN_TOLERANCE = 4.0
fake_st.turn_to = lambda *a, **k: (10.0, [])
sys.modules["slow_traverse"] = fake_st


class M:
    def steps_for(self, a, b):
        return list(STEPS)


def counting(steps, scale=None):
    seen["scaled"] += 1
    return real_scaled(steps, scale)


try:
    gw._scaled = counting
    try:
        gw.walk_link(M(), "a", "b", capture=lambda: None,
                     read_heading=lambda: 10.0, log=lambda *a: None)
    except Exception:
        pass                      # it will fail later on fake frames; fine
    check("walk_link actually applies the scaling", seen["scaled"] >= 1)
finally:
    gw._scaled = real_scaled
    if real_st is not None:
        sys.modules["slow_traverse"] = real_st
    else:
        sys.modules.pop("slow_traverse", None)

# PER-LEG scaling: speed belongs only on legs that have earned it. The office
# legs are corridors — walls constrain the path, no furniture, no NPCs — and
# together they are 16.17s of the route's 23.00s while never being the failure.
# The bar legs, which ARE the failures, must stay untouched.
old_by_leg = dict(gw.LEG_SPEED_BY_LEG)
old_scale = gw.LEG_SPEED_SCALE
try:
    gw.LEG_SPEED_SCALE = 1.0
    gw.LEG_SPEED_BY_LEG = {("office_door", "portrait_room"): 1.5}

    check("a leg with an override uses it",
          gw.leg_scale("office_door", "portrait_room") == 1.5)
    check("a leg WITHOUT an override is left at the global scale",
          gw.leg_scale("bar_pool_room", "bar_jukebox") == 1.0)

    sped = gw._scaled(STEPS, gw.leg_scale("office_door", "portrait_room"))
    same = gw._scaled(STEPS, gw.leg_scale("bar_pool_room", "bar_jukebox"))
    check("the overridden leg is actually shortened",
          sum(x["dur"] for x in sped) < sum(x["dur"] for x in STEPS))
    check("the fragile leg is untouched", same is STEPS)
    check("and the overridden leg still preserves distance",
          abs(dist(sped) - dist(STEPS)) < 1e-9)
finally:
    gw.LEG_SPEED_BY_LEG = old_by_leg
    gw.LEG_SPEED_SCALE = old_scale

# NO LEG HAS A SPEED OVERRIDE, AND ONE DID, AND IT COST 8 OF 10 ARRIVALS.
#
# This check used to pin {("office_corridor","office_door"): 3.0} and justified
# it in a comment as shipping "on a measured 10/10 arrival (OPEN-4 harness,
# 2026-09-06)". That attribution was wrong, and wrong in the way section 10.7
# exists to prevent: the 10/10 was measured 2026-09-05 at 23:12, and the
# override was enabled at 23:33 -- in the very commit that RECORDED the 10/10.
# The flag was credited with a result measured without it, and the credit was
# then written into a test, where it read as evidence.
#
# Measured properly, interleaved, 10 trials an arm, scored on verified arrival
# at bar_pool_room (overnight/ab_leg1.py, overnight/ab_leg1.json):
#
#     leg 1 as recorded          10/10 arrived   median  51.6s
#     leg 1 at speed 3.0, merged  2/10 arrived   median 323.7s
#     Fisher exact p = 0.000714
#
# The "original" arm reproduces the lost baseline exactly (51.6s against 52.9s).
# GRAVEYARD had already measured both halves as failures and its rows had gone
# stale, which is how they came back.
#
# SO: a future override must arrive with an INTERVENTIONAL A/B, not a plausible
# mechanism and not a measurement taken before it was switched on. Adding one
# means editing this check, which is the point -- it forces whoever adds it to
# read the paragraph above first.
check("no leg ships a speed override", gw.LEG_SPEED_BY_LEG == {})
check("no leg ships step merging", gw.MERGE_STEPS_BY_LEG == set())
check("global step merging stays off", gw.MERGE_STEPS is False)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
