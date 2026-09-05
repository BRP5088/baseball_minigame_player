"""A recorded walk must become the RIGHT graph edges, or none at all.

WHY THIS EXISTS
---------------
This is the step that converts scarce live game time into a permanent map, so
its mistakes are permanent too. Three specific ways it could be wrong:

  - inventing an edge between two places that were merely both seen
  - averaging a bearing across the circle's seam so a leg walks the wrong way
  - writing an empty map, which is WORSE than no map: WorldMap.load() then
    succeeds and route() returns None for everything, which reads as "no path
    exists" rather than "there is no map here"
"""
import json
import os
import os as _os
import shutil
import sys
import tempfile

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import map_build

fails = []


def check(c, m):
    if not c:
        fails.append(m)


# SCORES ARE ON THE ORB SCALE. identify() has delegated to identify_orb()
# since 2026-09-01, so `score` is a MATCH COUNT and `margin` is a RATIO. These
# defaults were 0.75 / 0.20 — old correlation values — which passed only
# because map_build's gate was itself on the wrong scale and could not reject
# anything. Both were fixed 2026-09-04; a row that should be confident must now
# look like one a real arrival produces (measured: 249-698 matches at 2.6-5.3x).
def frame(t, place, score=520.0, margin=4.30, heading=90.0, f=None):
    return {"kind": "frame", "t": t, "place": place, "score": score,
            "margin": margin, "heading": heading, "file": f or f"{int(t*10):05d}.jpg"}


# A walk: stand at A, transit east, stand at B, transit, stand at C.
rows = []
for i in range(4):
    rows.append(frame(0.0 + i * 0.5, "bar_exit_corner"))
for i in range(6):
    rows.append(frame(2.5 + i * 0.5, None, score=130.0, margin=1.10, heading=88 + i))
for i in range(4):
    rows.append(frame(6.0 + i * 0.5, "beside_dealer_table"))
for i in range(4):
    rows.append(frame(8.5 + i * 0.5, None, score=125.0, margin=1.05, heading=180.0))
for i in range(4):
    rows.append(frame(11.0 + i * 0.5, "dealer_table"))

segs = map_build.segments(rows)
check([s["place"] for s in segs] == ["bar_exit_corner", "beside_dealer_table", "dealer_table"],
      f"segments came back as {[s['place'] for s in segs]}")

lg = map_build.legs(rows, segs)
check([(l["a"], l["b"]) for l in lg] ==
      [("bar_exit_corner", "beside_dealer_table"),
       ("beside_dealer_table", "dealer_table")],
      f"legs came back as {[(l['a'], l['b']) for l in lg]}")
check(abs(lg[0]["seconds"] - 4.5) < 0.01,
      f"leg 1 cost {lg[0]['seconds']}s; it is the gap between LAST seeing the "
      f"origin (1.5s) and FIRST seeing the destination (6.0s) = 4.5s")
check(85 <= lg[0]["bearing"] <= 95,
      f"leg 1 bearing {lg[0]['bearing']}, expected ~90 from the transit frames")
check(lg[1]["bearing"] == 180.0, f"leg 2 bearing {lg[1]['bearing']}, expected 180")

# NO edge may appear between places the walk never went directly between.
check(not any(l["a"] == "bar_exit_corner" and l["b"] == "dealer_table" for l in lg),
      "invented a bar_exit_corner -> dealer_table edge. The walk never went "
      "directly between them; connect() means WALKED, and a straight line "
      "between two mapped points goes through walls")

# --- the circle seam -----------------------------------------------------
seam = ([frame(i * 0.5, "a") for i in range(4)]
        + [frame(2.5 + i * 0.5, None, score=125.0, margin=1.05, heading=h)
           for i, h in enumerate([358.0, 359.0, 1.0, 2.0])]
        + [frame(5.0 + i * 0.5, "b") for i in range(4)])
sl = map_build.legs(seam)
check(sl and (sl[0]["bearing"] > 355 or sl[0]["bearing"] < 5),
      f"bearing across the 0/360 seam came out {sl[0]['bearing'] if sl else None}; "
      "headings 358,359,1,2 average to ~180 if treated as plain numbers, which "
      "would walk the leg backwards")

# --- unlabelled stretches are surfaced for a human -----------------------
unk = map_build.unlabelled(rows)
check(len(unk) == 2, f"found {len(unk)} unlabelled stretches, expected 2")
check(all(u["representative"] for u in unk),
      "an unlabelled stretch came back with no representative frame; the whole "
      "point is that a person LOOKS at it and names it")

# --- an empty session must REFUSE to write -------------------------------
tmp = tempfile.mkdtemp(prefix="mapbuild-test-")
try:
    d = os.path.join(tmp, "empty")
    os.makedirs(d)
    with open(os.path.join(d, "index.jsonl"), "w") as fh:
        for i in range(6):
            fh.write(json.dumps(frame(i * 0.5, None, score=110.0, margin=1.02)) + "\n")
    store = os.path.join(tmp, "world_map.json")
    raised = False
    try:
        map_build.build(d, write=True, store=store)
    except SystemExit:
        raised = True
    check(raised, "a session with no legs wrote a map anyway")
    check(not os.path.exists(store),
          "an EMPTY world_map.json was created. WorldMap.load() would then "
          "succeed and route() would return None for every pair, which reads "
          "as 'no path exists' instead of 'there is no map'")

    # --- a real session writes, and the result is routable ---------------
    d2 = os.path.join(tmp, "good")
    os.makedirs(d2)
    with open(os.path.join(d2, "index.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    map_build.build(d2, write=True, store=store)
    import worldmap
    m = worldmap.WorldMap.load(store)
    path = m.route("bar_exit_corner", "dealer_table")
    check(path == ["bar_exit_corner", "beside_dealer_table", "dealer_table"],
          f"after writing, route() gave {path!r} — the whole point is that the "
          f"two recorded legs chain into a path the walk never took in one go")
    check(m.route_cost(path) is not None, "route_cost could not price the path")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  map_build: segments a walk, costs and aims each leg (seam-safe), "
      "invents no edges, surfaces unlabelled stretches, refuses to write an "
      "empty map, and the written map chains into a route")
