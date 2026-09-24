"""The map must refuse to give a heading to somewhere on another floor.

That refusal is the whole point. Four separate route attempts walked toward a
street-level doorway while standing on an upper landing, and every one of them
jammed into railings or geometry. A bearing to a place you cannot reach from
this floor is worse than no answer, because it looks usable.
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

import math
import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
import worldmap

fails = []

# --- dead reckoning agrees with the compass convention ---------------------
m = worldmap.WorldMap()
m.walk(0, 1.0)
if abs(m.y - 1.0) > 1e-6 or abs(m.x) > 1e-6:
    fails.append(f"walking north moved to {m.here()}, expected +y only — north "
                 "must be +y or every recorded position is rotated")
m = worldmap.WorldMap()
m.walk(90, 1.0)
if abs(m.x - 1.0) > 1e-6 or abs(m.y) > 1e-6:
    fails.append(f"walking east moved to {m.here()}, expected +x only")

# --- a round trip returns to the start -------------------------------------
m = worldmap.WorldMap()
for b in (0, 90, 180, 270):
    m.walk(b, 2.0)
if abs(m.x) > 1e-6 or abs(m.y) > 1e-6:
    fails.append(f"a closed square ended at {m.here()} instead of the origin")

# --- THE POINT: no heading across floors -----------------------------------
m = worldmap.WorldMap()
m.mark("upstairs_desk")
m.change_level(-1)
m.walk(45, 3.0)
if m.bearing_to("upstairs_desk") is not None:
    fails.append("gave a bearing to a landmark on a DIFFERENT FLOOR — this is "
                 "the exact error that walked the character at a street-level "
                 "door from an upper landing, four times")

# same place, same floor: must answer
m.change_level(+1)
answer = m.bearing_to("upstairs_desk")
if answer is None:
    fails.append("refused a bearing to a landmark on the SAME floor — the "
                 "level check is rejecting everything, not just cross-floor")
else:
    bearing, dist = answer
    if abs(dist - math.hypot(3 * math.sin(math.radians(45)),
                             3 * math.cos(math.radians(45)))) > 1e-6:
        fails.append(f"distance came back {dist}, not the 3.0 walk-seconds travelled")
    if abs((bearing - 225 + 540) % 360 - 180) > 1e-6:
        fails.append(f"bearing back came out {bearing}, expected 225 (the "
                     "reverse of the 45 walked out)")

# --- a saved map reloads unchanged -----------------------------------------
import atexit
import shutil
import tempfile
_map_dir = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _map_dir, ignore_errors=True)
p = os.path.join(_map_dir, "m.json")
m.save(p)
back = worldmap.WorldMap.load(p)
if back.here() != m.here() or back.landmarks != m.landmarks or back.level != m.level:
    fails.append("a saved map did not reload identically — the trail is the "
                 "only record of where anything is")

if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("  north is +y, a closed square returns to origin, cross-floor bearings "
      "are refused while same-floor ones answer with the right angle and "
      "distance, and a saved map reloads unchanged")
