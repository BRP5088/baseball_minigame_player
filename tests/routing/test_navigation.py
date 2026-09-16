"""Walkable-graph routing, and appearance-based "which room am I in".

Together these are the two halves dead reckoning was missing: worldmap could
say where it THOUGHT it was but not whether that was true, and its bearings
were straight lines that "may go through a building" (its own docstring).
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import
os.chdir(_ROOT)

import glob

import places
import worldmap

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# =========================================================================
# 1. Dijkstra prefers the cheaper WALKABLE path, not the shorter straight line
# =========================================================================
m = worldmap.WorldMap()
for n in ("office", "landing", "bar", "table", "annex"):
    m.mark(n)
# one_way=False here on purpose: these stand for corridors walked both ways.
# The DEFAULT is one-way, because a single trip is evidence about one
# direction — fabricating the return is how an unwalked drop becomes a planned
# climb.
m.connect("office", "landing", 5, one_way=False)
m.connect("landing", "bar", 5, one_way=False)
m.connect("bar", "table", 3, one_way=False)
m.connect("office", "bar", 20, one_way=False)   # exists, but the long way round

path = m.route("office", "table")
check(path == ["office", "landing", "bar", "table"],
      f"route picked {path}; the 5+5+3 way is cheaper than 20+3 and Dijkstra "
      "must find it")
check(m.route_cost(path) == 13.0,
      f"route_cost said {m.route_cost(path)}, expected 13.0")

# An unconnected place must be REFUSED, not answered with a bearing. This is
# the failure the map exists to prevent: four attempts walked at a doorway
# they could not reach.
check(m.route("office", "annex") is None,
      "an unconnected landmark must return None, not a path")
check(m.route("office", "nowhere") is None,
      "an unknown name must return None")
check(m.route("office", "office") == ["office"],
      "a route to where you already are is the trivial path")

# route_cost must reject a path whose legs were never walked.
check(m.route_cost(["office", "table"]) is None,
      "route_cost accepted a leg that was never connected — that is the "
      "straight-line answer wearing a graph's clothes")

# --- one-way legs (a drop you cannot climb back up) ----------------------
m2 = worldmap.WorldMap()
# Endpoints must be marked before they can be connected: an unmarked name is an
# orphan island that route() would hand back and bearing_to() would then refuse.
m2.mark("ledge")
m2.walk(0.0, 2.0)
m2.mark("floor")
m2.connect("ledge", "floor", 2, one_way=True)
check(m2.route("ledge", "floor") == ["ledge", "floor"], "one-way leg forward")
check(m2.route("floor", "ledge") is None,
      "a one-way leg must not be traversable in reverse")

# --- links must survive save/load, or the map forgets what is walkable ---
import tempfile
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "m.json")
    m.save(p)
    back = worldmap.WorldMap.load(p)
    check(back.route("office", "table") == path,
          "links were lost across save/load — the graph would rebuild itself "
          "from scratch every session")

# =========================================================================
# 2. Place identification: right room, or NO room. Never a confident wrong one.
# =========================================================================
db = places.load_places()
if len(db) >= 2:
    # Leave-one-out: a frame must be recognised WITHOUT itself in the database,
    # or the test only proves a frame matches itself.
    paths = {r: [x for x in sorted(glob.glob(os.path.join("places", r, "*.jpg")))
                 if os.path.basename(x) != "pano.jpg"] for r in db}
    wrong_room = []
    scored = 0
    for room, ps in paths.items():
        if len(ps) < 2:
            continue
        for held in ps:
            # A REAL LEAVE-ONE-OUT. This used to build `sub` and pass it as
            # places.identify(held, sub) — but identify() ignored that argument
            # entirely and answered from the full database, so every frame
            # matched ITSELF and the loop measured nothing. `root=` is the
            # parameter identify() actually honours, so hold the frame out by
            # building a reference tree without it.
            with tempfile.TemporaryDirectory() as _sub_root:
                for r, xs in paths.items():
                    kept = [x for x in xs if x != held]
                    if not kept:
                        continue
                    _d = os.path.join(_sub_root, r)
                    os.makedirs(_d, exist_ok=True)
                    for x in kept:
                        os.symlink(os.path.abspath(x),
                                   os.path.join(_d, os.path.basename(x)))
                got, score, margin = places.identify(held, root=_sub_root)
            scored += 1
            if got is not None and got != room:
                wrong_room.append((held, room, got, score))
    check(scored > 0, "no room has two frames, so leave-one-out proved nothing")
    check(not wrong_room,
          f"identified the WRONG room for {wrong_room} — abstaining is fine, "
          "confidently answering the wrong room is what sends a route into a wall")

    # The masking is load-bearing: the HUD is identical everywhere, so leaving
    # it in makes every frame resemble every other.
    v = places.descriptor(next(p for ps in paths.values() for p in ps))
    check(abs(float((v ** 2).sum()) - 1.0) < 1e-6,
          "descriptors must be unit length for dot products to be comparable")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  navigation: Dijkstra prefers the cheaper walkable path, refuses "
      "unconnected and unknown goals, honours one-way legs, survives "
      "save/load; place identification never names the wrong room")
