"""The per-leg "curve" the recordings hold is the human's LEFT THUMB, not a
camera turn — and `LEG_TURN_TOLERANCE` filters a quantity worth ~2% of a leg.

WHAT THIS PINS, and why it is worth a test rather than a paragraph.

A recorded step carries two headings. `bearing` is the WORLD TRAVEL DIRECTION
(camera heading + left-stick angle); `cam` is the camera heading the human
actually held. `cam` is written by build_route and read by nothing.

The executor cannot strafe inside a leg — graph_walk.walk_link calls
`st.walk_leg(0.0, -abs(speed), ...)` with lx hard-coded to 0.0 — so it
reproduces the human's travel direction by turning the CAMERA to `bearing`.
That is correct for displacement and wrong for viewing heading, and it means
every "curve" in `bearing` is a camera turn the human never made.

Measured over all 64 inter-step transitions in BOTH recordings (route3, which
the map is built from, and the independent route2):

    |delta bearing| > 4.0 deg     23 of 64
    |delta cam|     > 4.0 deg      1 of 64      <- the entire "recorded curve"

Per-leg span, route3:  bearing 0.32 / 30.46 / 6.59 / 2.65 / 25.64
                       cam     0.66 /  9.47 / 0.13 / 0.30 /  0.28

So on four of five legs the human's camera did not move at all, to within a
degree, and tightening `slow_traverse.TURN_TOLERANCE` would make the executor
rotate the camera to chase thumb jitter.

AND IT IS NOT WORTH CHASING. Integrating each leg at the headings the executor
actually walks, tolerance 4.0 costs at most 2.63% of a leg's displacement, and
0.27% / 2.32% on the two legs that actually fail. The project's own leg-distance
pin accepts 15%. For scale, the shortfall that genuinely broke the jukebox leg
was 0.703 of 1.031 units — 68%.

THIS TEST EXISTS SO THE ANALYSIS IS NOT RE-DERIVED FROM SCRATCH. If someone
changes TURN_TOLERANCE, or re-records a leg, the bound below is what tells them
the OPEN-3 arithmetic has to be redone.
"""
import json
import math
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def wrap(d):
    return (d + 540.0) % 360.0 - 180.0


MAP = os.path.join(_ROOT, "world_map.json")
R3 = os.path.join(_ROOT, "route3_steps.json")
R2 = os.path.join(_ROOT, "route2_steps.json")
for p in (MAP, R3, R2):
    if not os.path.exists(p):
        print(f"FAIL missing {p} — this test cannot run, and a test that "
              f"cannot run must not report success")
        sys.exit(1)

m = json.load(open(MAP))
r3 = json.load(open(R3))
r2 = json.load(open(R2))

LEGS = [("office_corridor", "office_door"), ("office_door", "portrait_room"),
        ("portrait_room", "bar_pool_room"), ("bar_pool_room", "bar_jukebox"),
        ("bar_jukebox", "dealer_table")]

# --- the map's legs must BE route3 slices --------------------------------
# Everything below attributes route3's `cam` to the map's legs. If that
# correspondence breaks (a re-record, a reordering), the cam figures describe a
# different walk and the whole analysis is void — so it is checked, not assumed.
ranges, cursor = [], 0
for a, b in LEGS:
    st = m["links"][a][b]["steps"]
    sl = r3[cursor:cursor + len(st)]
    same = len(sl) == len(st) and all(
        abs(x["bearing"] - y["bearing"]) < 1e-9 and
        abs(x["dur"] - y["dur"]) < 1e-9 and
        abs(x["speed"] - y["speed"]) < 1e-9 for x, y in zip(st, sl))
    check(f"{a} -> {b} is route3[{cursor}:{cursor + len(st)}], so its `cam` "
          f"values are attributable", same)
    ranges.append((cursor, cursor + len(st)))
    cursor += len(st)
check("route3 is exactly the five legs, nothing left over", cursor == len(r3))

# --- the curve is the STICK, not the camera ------------------------------
SEGS = [r3[s:e] for s, e in ranges] + [
    r2[0:11], r2[11:20], r2[20:23], r2[23:30], r2[30:34]]
db, dc = [], []
for seg in SEGS:
    for i in range(1, len(seg)):
        db.append(abs(wrap(seg[i]["bearing"] - seg[i - 1]["bearing"])))
        if "cam" in seg[i] and "cam" in seg[i - 1]:
            dc.append(abs(wrap(seg[i]["cam"] - seg[i - 1]["cam"])))

big_b = sum(1 for v in db if v > 4.0)
big_c = sum(1 for v in dc if v > 4.0)
print(f"  transitions: {len(db)} bearing, {len(dc)} cam; "
      f"above 4.0 deg -> bearing {big_b}, cam {big_c}")
# Literals, not `> TURN_TOLERANCE`: this is a fact about the RECORDINGS and must
# not move when a tuning constant does (CLAUDE.md 10.11).
check("both recordings cover the same 64 transitions",
      len(db) == 64 and len(dc) == 64)
check("the CAMERA barely moved: at most 2 of 64 transitions turn it > 4.0 deg",
      big_c <= 2)
check("the BEARING moves constantly: at least 15 of 64 transitions exceed 4.0",
      big_b >= 15)
check("so the recorded 'curve' is overwhelmingly left-stick, not camera "
      f"({big_b} bearing vs {big_c} cam)", big_b >= 10 * max(big_c, 1))

# --- and filtering it is worth ~2% of a leg ------------------------------
def integrate(steps, headings):
    x = y = 0.0
    for s, h in zip(steps, headings):
        d = s["speed"] * s["dur"]
        x += d * math.sin(math.radians(h))
        y += d * math.cos(math.radians(h))
    return x, y


def cost(steps, tol):
    """Fraction of the leg's length lost by discarding turns under `tol`."""
    truth = [s["bearing"] for s in steps]
    cur, walked = None, []
    for t in truth:
        if cur is None or abs(wrap(t - cur)) > tol:
            cur = t
        walked.append(cur)
    tx, ty = integrate(steps, truth)
    ex, ey = integrate(steps, walked)
    return math.hypot(ex - tx, ey - ty) / math.hypot(tx, ty)


import slow_traverse as st_mod

# Pinned at the LITERAL the arithmetic was done at. Reading the module constant
# here instead would make the bound rise with it and pass forever.
per_leg = [cost(r3[s:e], 4.0) for s, e in ranges]
worst = max(per_leg)
print("  displacement cost at tolerance 4.0, per leg: "
      + "  ".join(f"{a[:14]} {c * 100:.2f}%" for (a, _), c in zip(LEGS, per_leg)))
# A ratchet of sub-tolerance turns all in one direction is the adversarial case
# and reaches 3.90% on this route; the recordings reach 2.63%. 3.0% sits between
# the two, so this bound can actually fail — verified by mutating the portrait
# leg to [286.57, 290.47, 294.37, 298.27] (deltas 3.9, every one discarded).
check("discarding sub-4.0-degree turns costs under 3% of any leg — an order "
      "below the 15% the leg-distance pin already accepts", worst < 0.03)
# The two figures the OPEN-3 decision rests on, pinned as literals so any drift
# in the data or in the turn model shows up here rather than in a live A/B.
check("portrait_room -> bar_pool_room loses 0.2-0.4% (the leg the whole ticket "
      f"was written about) — measured {per_leg[2] * 100:.2f}%",
      0.002 < per_leg[2] < 0.004)
check(f"bar_pool_room -> bar_jukebox loses 2.1-2.6% — measured "
      f"{per_leg[3] * 100:.2f}%", 0.021 < per_leg[3] < 0.026)
check("TURN_TOLERANCE is still the 4.0 that bound was computed at — if this "
      "fails, redo the OPEN-3 arithmetic before trusting the bound above",
      st_mod.TURN_TOLERANCE == 4.0)

# --- and the OTHER half of the mechanism, which the bound above omits ------
# `cost()` seeds the leg at truth[0] exactly, so it prices only the commanded
# turns the tolerance DISCARDS. turn_to does not work that way: it compares the
# target against the MEASURED heading, so a leg also STARTS up to `tolerance`
# off and is walked at that offset until some step exceeds the band. That is
# the second half of OPEN-3's own stated mechanism ("neither executes a
# commanded change under 4 deg nor corrects drift under it") and graph_walk.py's
# own comment says it outright: the leg is walked "at whatever heading the
# character arrived with, anywhere in a +-4 degree band". The one real trace is
# exactly that — commanded 286.57, character at 289.1, entry turn a NO-OP.
#
# Pricing BOTH halves is what makes the drop verdict safe rather than lucky.
def cost_entry(steps, tol):
    """Worst case over the entry offset the tolerance permits, not just the
    discarded turns. Deterministic sweep, so this is a bound and not a sample."""
    truth = [s["bearing"] for s in steps]
    tx, ty = integrate(steps, truth)
    L = math.hypot(tx, ty)
    worst = 0.0
    for i in range(-100, 101):
        off = tol * i / 100.0
        cur, walked = truth[0] + off, []
        for t in truth:
            if abs(wrap(t - cur)) > tol:
                cur = t
            walked.append(cur)
        ex, ey = integrate(steps, walked)
        worst = max(worst, math.hypot(ex - tx, ey - ty) / L)
    return worst, L


full = [cost_entry(r3[s:e], 4.0) for s, e in ranges]
print("  FULL cost at tolerance 4.0 (entry offset included), per leg: "
      + "  ".join(f"{a[:14]} {c * 100:.2f}%" for (a, _), (c, _) in zip(LEGS, full)))
# Tight literals, so any drift in the data or the turn model breaks them.
check("including the entry offset the worst leg costs 6.5-7.0%, NOT the 2.63% "
      f"the discarded-turn bound alone reports — measured "
      f"{max(c for c, _ in full) * 100:.2f}%",
      0.065 < max(c for c, _ in full) < 0.070)
# The quantity a 4.0 -> 1.0 A/B could actually move, summed over the whole route,
# in walk-units — directly comparable to the 0.703-unit shortfall that genuinely
# broke the jukebox leg. THIS is the number that says 20 trials cannot see it.
tight = [cost_entry(r3[s:e], 1.0) for s, e in ranges]
saved = sum(c * L for c, L in full) - sum(c * L for c, L in tight)
print(f"  worst-case route endpoint error: {sum(c * L for c, L in full):.3f} units "
      f"at 4.0 vs {sum(c * L for c, L in tight):.3f} at 1.0 -> {saved:.3f} saved")
check(f"even priced worst-case end to end, tightening 4.0 -> 1.0 is worth "
      f"0.24-0.28 walk-units over the WHOLE route against the 0.703-unit "
      f"shortfall that actually broke a leg — measured {saved:.3f}",
      0.24 < saved < 0.28)

# --- the floor nobody may tune below -------------------------------------
# turn_curve.plan_turn returns (0.0, 0.0) below 0.5 deg, so slow_traverse.turn_to
# can never satisfy `abs(err) <= tolerance` under that: it breaks out and files
# an UNDERTURNED hazard on EVERY step. Verified offline against a perfect
# simulated console — tolerance 0.40 filed 297 of 2800, tolerance 0.0 filed all
# of them. A LEG_TURN_TOLERANCE below 0.5 is not a tuning value, it is broken.
import turn_curve as tc
check("plan_turn refuses anything under 0.5 deg, so tolerances below that "
      "cannot converge", tc.plan_turn(0.49)[0] == 0.0
      and tc.plan_turn(0.51)[0] > 0.0)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("all green")
