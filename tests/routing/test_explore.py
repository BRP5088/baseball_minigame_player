"""The explorer must move SLOWLY, sweep every stop, and never touch the map.

"for the areas that are unknown, I don't care about speed at all. I would
rather you move slow but with intention." (user, 2026-09-04)

Explore slow, exploit fast. The speed work (0.60 repeatability cliff,
LEG_SPEED_SCALE) belongs to the KNOWN route; here the opposite applies, because
a sample is only worth recording if it sits where the recorder thinks it does.
"""
import json
import os
import os as _os
import sys
import tempfile
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import explore

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class Img:
    def save(self, p):
        open(p, "wb").write(b"x")


def fakes(identify=(None, 50, 1.0), kp=900, heading=90.0):
    turns, walks = [], []
    fc = types.ModuleType("compass")
    fc.fast_capture = lambda: Img()
    fc.read_bearing = lambda img: heading
    fp = types.ModuleType("places")
    fp.keypoints = lambda img, cache_key=None: (None, [0] * kp)
    fp.identify = lambda img: identify
    fw = types.ModuleType("walk_steps")
    fw.read_heading = lambda: heading
    fw.turn_to = lambda t, log=None, **k: turns.append(round(t, 1))
    fw.walk_forward = lambda sp, sec, **k: walks.append((sp, sec)) or 10.0
    for n, m in (("compass", fc), ("places", fp), ("walk_steps", fw)):
        sys.modules[n] = m
    return turns, walks


turns, walks = fakes()
real_sleep = explore.time.sleep
explore.time.sleep = lambda *a: None
try:
    d = tempfile.mkdtemp()
    e = explore.Explorer("t", log=lambda *a: None, root=d)
    rows = e.sweep()

    check("a sweep records every bearing", len(rows) == explore.SWEEP_BEARINGS)
    check("a sweep TURNS but never walks", turns and not walks)
    check("it returns the camera to where it started",
          turns and turns[-1] == 90.0)
    check("every frame is written to disk",
          all(os.path.exists(r["file"]) for r in rows))
    check("each row records what the localiser thought",
          all("identify" in r and "keypoints" in r for r in rows))

    # Steps must be short and inside the measured-repeatable band.
    e.step(10.0)
    check("a step is short", walks and walks[0][1] <= 0.5)
    check("a step stays in the repeatable speed band (<=0.45)",
          walks and walks[0][0] <= 0.45)

    s = e.summary()
    check("the summary counts unmapped rich views",
          s["unmapped_rich_views"] == explore.SWEEP_BEARINGS)

    # A featureless sweep must NOT be counted as a place worth mapping.
    fakes(kp=10)
    e2 = explore.Explorer("t2", log=lambda *a: None, root=d)
    e2.sweep()
    check("featureless views are not counted as unmapped places",
          e2.summary()["unmapped_rich_views"] == 0)
finally:
    explore.time.sleep = real_sleep

# It must never write to the map or the places directory.
src = open(os.path.join(_ROOT,
                        "explore.py")).read()
check("explore.py never writes world_map.json", "world_map" not in src)
check("explore.py never calls places.add", "places.add" not in src)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
