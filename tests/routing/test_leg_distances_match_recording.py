"""Every leg must cover the distance its own recording covered.

THE BUG THIS GUARDS, found 2026-09-05 and the largest single defect in the
project's history.

`bar_pool_room -> bar_jukebox` was re-recorded on 2026-09-04 as a single 0.80s
step at speed 0.30 = **0.240 walk-units**. The human recording the map was built
from covers that same span in **1.032 units over 3.32s** (route3_steps.json
steps 27-31, bearings 2.08 / 1.16 / 0.76 / 359.43 / 359.61 — due north, matching
the leg's 2.1). A SECOND independent recording (route2) gives 1.086, agreeing to
5%.

So the leg was **4.3x too short and could not reach its own destination**: from
the far edge of `bar_pool_room`'s recognition basin it landed 0.703 units short
of the near edge of `bar_jukebox`'s.

Why it stayed invisible: the search that produced it
(`overnight/phase1_step4_rerecord.py`) only offered `DURS = [0.8, 1.3]`, so the
correct ~3.3s was never a candidate — and the A/B that followed reported
"4/8 -> 4/8, identical" and was filed as an informative null. It cannot have
been measuring the leg.

The invariant: a leg's recorded distance should be within ~15% of what the
source recording covers between the same two node poses. Every other leg sits at
0.91-0.98; only this one was 0.22.
"""
import json
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


def dist(steps):
    return sum(s["dur"] * s["speed"] for s in steps)


MAP = os.path.join(_ROOT, "world_map.json")
SRC = os.path.join(_ROOT, "route3_steps.json")
for p in (MAP, SRC):
    if not os.path.exists(p):
        print(f"FAIL missing {p} — this test cannot run, and a test that "
              f"cannot run must not report success")
        sys.exit(1)

m = json.load(open(MAP))
src = json.load(open(SRC))

# --- the leg that was broken --------------------------------------------
leg = m["links"]["bar_pool_room"]["bar_jukebox"]["steps"]
d = dist(leg)
recorded = dist([{"dur": s["dur"], "speed": s["speed"]} for s in src[27:32]])

print(f"  jukebox leg: {d:.3f} units   source recording: {recorded:.3f} units")
check("the jukebox leg covers its recorded distance (within 15%)",
      abs(d - recorded) / recorded < 0.15)
# Pinned as a literal too: comparing the leg to itself would pass for any value.
check("and that is ~1.03 units, not the 0.24 the re-record left",
      0.85 < d < 1.20)
check("it is a multi-step leg — the recorded curve is preserved",
      len(leg) >= 4)

# --- no leg may be trivially short --------------------------------------
# A single-step leg under ~0.3 units is the signature of the bug: a search that
# only offered short durations collapsing a real walk into one brief push.
for a, dests in m["links"].items():
    for b, lk in dests.items():
        ld = dist(lk["steps"])
        check(f"{a} -> {b} is not implausibly short ({ld:.3f} units)",
              ld > 0.30)

# --- speeds stay inside the measured-repeatable band --------------------
# pose displacement spread holds at ~15px through 0.45 and collapses above 0.60
# (27px, then 124, then 476). A leg recorded above that is not reproducible.
for a, dests in m["links"].items():
    for b, lk in dests.items():
        fast = [s for s in lk["steps"] if s["speed"] > 0.60]
        check(f"{a} -> {b} has no step above the repeatable 0.60",
              not fast)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
