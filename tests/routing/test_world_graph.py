"""The recorded graph must exist, route, and be WALKABLE — not just loadable.

WHY THIS EXISTS
---------------
Before 2026-09-01 world_map.json had never been written, WorldMap.route() had
zero production callers, and the whole route/worldmap test set was green over
NO graph at all — a suite that passes on missing data is how this project has
repeatedly shipped code that did nothing.

So this test refuses to skip. If the graph is absent it FAILS.
"""
import json
import math
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import worldmap

STORE = os.path.join(_ROOT, "world_map.json")
GOAL = "dealer_table"

fails = []


def check(c, m):
    if not c:
        fails.append(m)


if not os.path.exists(STORE):
    raise SystemExit(
        f"{STORE} does not exist. This is a FAILURE, not a skip: routing over "
        "a missing graph is the state the project sat in for weeks while its "
        "tests stayed green. Run: python3 build_world_map.py --write")

m = worldmap.WorldMap.load(STORE)

check(len(m.landmarks) >= 6, f"only {len(m.landmarks)} landmarks in the graph")
check(GOAL in m.landmarks, f"{GOAL!r} is not a node; it is the destination")

# Every node must be able to REACH the table, or it is a hole the router can
# never plan through — and the whole point is starting from anywhere.
for node in m.landmarks:
    if node == GOAL:
        continue
    path = m.route(node, GOAL)
    check(path is not None,
          f"no route {node} -> {GOAL} (route_reason: {m.route_reason(node, GOAL)}). "
          f"A node that cannot reach the table is unreachable-by-design")
    if not path:
        continue
    # ...and every leg on it must be executable, not merely priced.
    for a, b in zip(path, path[1:]):
        try:
            steps = m.steps_for(a, b)
        except Exception as e:
            fails.append(f"leg {a} -> {b} on the {node} route is not walkable: {e}")
            continue
        check(all(s.get("dur", 0) > 0 for s in steps),
              f"leg {a} -> {b} has a step with no duration")
        check(all("bearing" in s for s in steps),
              f"leg {a} -> {b} has a step with no bearing — a leg without a "
              f"heading cannot be walked, only priced")
    cost = m.route_cost(path)
    check(cost is not None and math.isfinite(cost) and cost > 0,
          f"route {node} -> {GOAL} priced at {cost!r}")

# The full route from the spawn must chain all the way through.
full = m.route("office_corridor", GOAL)
check(full and full[0] == "office_corridor" and full[-1] == GOAL and len(full) >= 5,
      f"spawn-to-table route came back as {full!r}")

# route_reason must distinguish the four causes route() collapses into None.
check(m.route_reason("nowhere_at_all", GOAL) == "unknown_start",
      f"unknown start reported as {m.route_reason('nowhere_at_all', GOAL)!r}")
check(m.route_reason(GOAL, "nowhere_at_all") == "unknown_goal",
      f"unknown goal reported as {m.route_reason(GOAL, 'nowhere_at_all')!r}")
check(m.route_reason(GOAL, GOAL) == "same",
      f"same-node reported as {m.route_reason(GOAL, GOAL)!r}")
check(m.route_reason("office_corridor", GOAL) == "ok",
      f"a real route reported as {m.route_reason('office_corridor', GOAL)!r}")

# Legs are ONE-WAY unless something walked the return. The recorded walk only
# went one direction, so the reverse must NOT have been fabricated.
check(m.route(GOAL, "office_corridor") is None,
      "the graph routes BACKWARDS from the table to the spawn, but nothing "
      "ever walked that direction. connect() used to fabricate the reverse "
      "leg from a single trip, which is how an unwalked drop becomes a "
      "planned climb")

# The measured localiser ambiguity must be carried in the file, not lost.
raw = json.load(open(STORE))
check(raw.get("confusable"),
      "world_map.json records no confusable pairs. office_corridor and "
      "office_door measured 0.726 similar (MIN_SCORE is 0.55) — an executor "
      "that does not know this will use appearance to choose between them")

# =========================================================================
# Degenerate maps, built here rather than hoped for. The real map above is
# well-formed, so it cannot catch a guard being removed.
# =========================================================================
import tempfile

with tempfile.TemporaryDirectory() as td:
    # 1. A file with NO links must not load as a valid empty map. That state
    #    made route() answer None for every pair, which reads as "no path
    #    exists" instead of "there is no map here".
    bad = os.path.join(td, "nolinks.json")
    json.dump({"level": 0, "x": 0.0, "y": 0.0,
               "landmarks": {"a": [0, 0, 0]}, "trail": []}, open(bad, "w"))
    err = None
    try:
        worldmap.WorldMap.load(bad)
    except KeyError as e:
        err = str(e)
    check(err is not None,
          "load() accepted a map with no 'links' key. An empty graph must not "
          "be able to masquerade as a full one whose destinations are all "
          "unreachable")
    # Bare d["links"] raises KeyError too, so RAISING is not what is being
    # pinned here — the EXPLANATION is. An unattended run is diagnosed from
    # this string, and "'links'" alone sends the reader to the wrong place.
    check(err and "no edges" in err,
          f"load() raised {err!r} for a map with no links. That is the bare "
          f"dict KeyError, not the guard: it must say the map has no edges and "
          f"that routing over it would report every destination unreachable")

    # 2. A leg with a cost but no steps is PRICED, not walkable. Returning []
    #    would let an executor 'complete' it while standing still.
    m2 = worldmap.WorldMap()
    m2.mark("a")
    m2.walk(0.0, 3.0)
    m2.mark("b")
    m2.connect("a", "b", 3.0)            # a bare cost: no steps
    raised = False
    try:
        m2.steps_for("a", "b")
    except ValueError:
        raised = True
    check(raised,
          "steps_for() returned quietly for a leg with no steps. An executor "
          "would then walk nothing and report the route completed — the exact "
          "'did nothing, looked like working' shape this codebase catalogues")

    # 3. One trip is evidence about ONE direction.
    m3 = worldmap.WorldMap()
    m3.mark("top")
    m3.walk(180.0, 2.0)
    m3.mark("bottom")
    m3.connect("top", "bottom", [{"bearing": 180.0, "dur": 2.0, "speed": 0.25}])
    check(m3.route("top", "bottom") == ["top", "bottom"], "forward leg lost")
    check(m3.route("bottom", "top") is None,
          "connect() fabricated the reverse leg from a single trip. Nothing "
          "walked back up, and planning an unwalked climb over a drop is how "
          "four attempts jammed into geometry")

    # 4. Costs that break Dijkstra must be refused at the door.
    for bad_cost in (0, -5.0, float("nan"), float("inf")):
        raised = False
        try:
            m3.connect("top", "bottom", bad_cost)
        except ValueError:
            raised = True
        check(raised,
              f"connect() accepted cost {bad_cost!r}. A negative cost makes "
              f"route()'s path reconstruction spin forever; NaN compares false "
              f"against everything and silently hides the leg")

    # 5. An unmarked endpoint is a silent orphan island.
    raised = False
    try:
        m3.connect("top", "never_marked", 2.0)
    except ValueError:
        raised = True
    check(raised, "connect() accepted an unmarked endpoint")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  world graph: {len(m.landmarks)} nodes, every one routes to {GOAL} "
      f"over legs that carry real steps; reverse travel is refused; "
      f"route_reason separates all four None causes")
