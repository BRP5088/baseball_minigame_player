"""Speed must follow PROVEN reliability, and fall away when it lapses."""
import json
import os
import os as _os
import sys
import tempfile

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import leg_reliability as lr

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


tmp = os.path.join(tempfile.mkdtemp(), "rel.json")

# Unknown ground is slow. This is the default and the safe one.
check("an unrecorded leg is NOT sped up",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# A perfect but SHORT record is not enough — n=3 has no power here.
for _ in range(3):
    lr.record("a", "b", True, tmp)
check("3 perfect attempts do not earn speed (n too small)",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# A long perfect record does.
for _ in range(17):
    lr.record("a", "b", True, tmp)
r, n = lr.rate("a", "b", tmp)
check(f"20/20 earns speed (rate {r:.2f}, n={n})",
      lr.scale_for("a", "b", tmp) == lr.FAST_SCALE)

# A merely-decent leg does not. 0.667 is the best non-perfect leg measured.
for _ in range(14):
    lr.record("c", "d", True, tmp)
for _ in range(7):
    lr.record("c", "d", False, tmp)
r, n = lr.rate("c", "d", tmp)
check(f"a 0.667 leg stays slow (rate {r:.2f}, n={n})",
      lr.scale_for("c", "d", tmp) == lr.NORMAL_SCALE)

# THE POINT: a proven leg that starts failing LOSES its speed on its own.
for _ in range(4):
    lr.record("a", "b", False, tmp)
r, n = lr.rate("a", "b", tmp)
check(f"a leg that starts failing slows itself back down (rate {r:.2f})",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# The bar must sit clear of the best non-perfect leg actually measured.
check("MIN_RATE is well above the best imperfect leg (0.667)",
      lr.MIN_RATE > 0.9)
check("MIN_ATTEMPTS reflects the power analysis (n=3 has power 0.00)",
      lr.MIN_ATTEMPTS >= 10)

# A corrupt record must not stop a run.
open(tmp, "w").write("{ not json")
check("a corrupt record degrades to slow rather than raising",
      lr.scale_for("a", "b", tmp) == lr.NORMAL_SCALE)

# WIRING into graph_walk: an explicit override must still win, and bookkeeping
# must never be able to stop a walk.
import graph_walk as gw

old_flag, old_by = gw.SPEED_FROM_RELIABILITY, dict(gw.LEG_SPEED_BY_LEG)
try:
    gw.SPEED_FROM_RELIABILITY = False
    check("with reliability off, an unproven leg is at the global scale",
          gw.leg_scale("x", "y") == gw.LEG_SPEED_SCALE)

    gw.LEG_SPEED_BY_LEG = {("x", "y"): 2.5}
    gw.SPEED_FROM_RELIABILITY = True
    check("an explicit override beats the earned scale",
          gw.leg_scale("x", "y") == 2.5)

    gw.LEG_SPEED_BY_LEG = {}
    check("an unproven leg earns nothing even with reliability on",
          gw.leg_scale("nope", "nowhere") == lr.NORMAL_SCALE)
finally:
    gw.SPEED_FROM_RELIABILITY, gw.LEG_SPEED_BY_LEG = old_flag, old_by

check("both reliability flags ship OFF",
      gw.SPEED_FROM_RELIABILITY is False and gw.RECORD_RELIABILITY is False)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
