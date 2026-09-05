"""Turn a recorded mapping walk into graph edges — offline, no game needed.

    python3 map_build.py world_log/20260901_2011_bar        # inspect a session
    python3 map_build.py world_log/... --write               # write world_map.json

WHAT THIS IS FOR
----------------
Live game time is the scarce resource: a walk cannot be repeated identically,
and every pass costs real minutes at the console. So a mapping session records
once (see world_log.py) and everything else — deciding which stretches were a
recognised place, how long the transit between two places took, and which
stretches were somewhere not yet labelled — happens here, offline, as many
times as it takes.

HOW A LEG GETS ITS COST AND BEARING
-----------------------------------
A leg is replayed as "face this way, walk this long", so it needs both, and
both come from the frames BETWEEN two recognised places:

    cost    = when the destination was first recognised
              minus when the origin was last recognised
    bearing = the median heading over those transit frames

Median, not mean: headings are a circle, a walk usually holds one heading, and
a couple of frames captured mid-turn at each end would drag a mean off the
line actually walked.

WHAT IT REFUSES TO DO
---------------------
It does not invent an edge between two places just because they were both seen
in one session. A leg is only emitted when the walk went DIRECTLY from one to
the other, because worldmap.connect() means "this was walked" — an edge
inferred from proximity is the straight-line answer wearing a graph's clothes,
and a straight line between two mapped points goes through walls.

It also does not name places. Frames that match nothing are grouped and handed
back for a HUMAN to look at and label, because a place named by the same code
that will later be graded on finding it is not evidence of anything.
"""

import os
import sys

import numpy as np

import places
import world_log

# A frame counts as "standing in a known place" only well clear of the abstain
# threshold. Building an EDGE on a barely-confident frame bakes that doubt into
# the map permanently, so the bar is higher here than for a live lookup.
#
# THESE WERE ON THE WRONG SCALE UNTIL 2026-09-04 AND THE GATE COULD NOT FAIL.
# They were 0.62 / 0.08, written for the old identify_edges() correlation
# scores (0..1, MIN_SCORE 0.55). identify() has delegated to identify_orb()
# since 2026-09-01, so `score` is now a MATCH COUNT (a non-abstaining answer is
# >= places.MIN_MATCHES, i.e. 140) and `margin` is a RATIO (>= MIN_RATIO, 1.35).
# Against those, `score >= 0.62` and `margin >= 0.08` are ALWAYS TRUE:
# _confident() silently collapsed to `place is not None`, and every edge in the
# map was admitted with no confidence bar at all.
#
# Set clear of the live thresholds, as the paragraph above always intended.
SEG_MIN_SCORE = 200.0        # vs places.MIN_MATCHES 140
SEG_MIN_MARGIN = 1.60        # vs places.MIN_RATIO   1.35
# A place must be seen this many frames running to count as arrival, so one
# lucky frame in a corridor cannot become a graph node.
SEG_MIN_FRAMES = 3

# The left-stick magnitude a mapping walk is made at. Legs are replayed at the
# magnitude they were recorded at, so this only has to be CONSISTENT, not
# correct — there is no speed-to-distance calibration anywhere in this project
# and this does not pretend to be one.
WALK_SPEED = 0.25


def _confident(row):
    return (row.get("kind") == "frame"
            and row.get("place")
            and (row.get("score") or 0) >= SEG_MIN_SCORE
            and (row.get("margin") or 0) >= SEG_MIN_MARGIN)


def segments(rows, min_frames=SEG_MIN_FRAMES):
    """Contiguous stretches where one place was confidently recognised."""
    out, cur = [], None
    for r in rows:
        if r.get("kind") != "frame":
            continue
        name = r.get("place") if _confident(r) else None
        if cur and cur["place"] == name and name is not None:
            cur["t_end"] = r["t"]
            cur["n"] += 1
            cur["scores"].append(r.get("score") or 0.0)
        else:
            if cur and cur["n"] >= min_frames:
                out.append(cur)
            cur = ({"place": name, "t_start": r["t"], "t_end": r["t"], "n": 1,
                    "scores": [r.get("score") or 0.0]} if name else None)
    if cur and cur["n"] >= min_frames:
        out.append(cur)
    for s in out:
        s["mean_score"] = round(float(np.mean(s["scores"])), 4)
        del s["scores"]
    return out


def _median_heading(headings):
    """Median of a set of compass bearings, handled on the circle."""
    hs = [h for h in headings if h is not None]
    if not hs:
        return None
    # Unit vectors then atan2: a plain median calls 359 and 1 degrees far apart.
    x = float(np.median([np.sin(np.radians(h)) for h in hs]))
    y = float(np.median([np.cos(np.radians(h)) for h in hs]))
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return round((float(np.degrees(np.arctan2(x, y))) + 360.0) % 360.0, 1)


def legs(rows, segs=None):
    """[(a, b, seconds, bearing, n_transit)] for DIRECT walks between places.

    Consecutive segments only. If the walk passed through somewhere unlabelled
    on the way, that stretch is still a direct walk between the two recognised
    ends — which is exactly what makes it a usable edge.
    """
    segs = segments(rows) if segs is None else segs
    frames = [r for r in rows if r.get("kind") == "frame"]
    out = []
    for a, b in zip(segs, segs[1:]):
        if a["place"] == b["place"]:
            continue
        transit = [f for f in frames if a["t_end"] < f["t"] < b["t_start"]]
        seconds = round(b["t_start"] - a["t_end"], 2)
        if seconds <= 0:
            continue
        out.append({"a": a["place"], "b": b["place"], "seconds": seconds,
                    "bearing": _median_heading([f.get("heading") for f in transit]),
                    "n_transit": len(transit)})
    return out


def unlabelled(rows, min_frames=SEG_MIN_FRAMES):
    """Stretches the localiser could not name — candidates for a new label.

    Returned with a representative frame so a human can LOOK at it. Today 6 of
    14 route failures ended somewhere unlabelled; each of those is a missing
    node, and a missing node is a hole the router can never plan through.
    """
    out, cur = [], None
    for r in rows:
        if r.get("kind") != "frame":
            continue
        if not _confident(r):
            if cur is None:
                cur = {"t_start": r["t"], "t_end": r["t"], "n": 1, "files": []}
            cur["t_end"] = r["t"]
            cur["n"] += 1
            if r.get("file"):
                cur["files"].append(r["file"])
        else:
            if cur and cur["n"] >= min_frames:
                out.append(cur)
            cur = None
    if cur and cur["n"] >= min_frames:
        out.append(cur)
    for c in out:
        c["representative"] = c["files"][len(c["files"]) // 2] if c["files"] else None
    return out


def build(session_dir, write=False, store="world_map.json"):
    """Summarise a session; optionally fold its legs into world_map.json."""
    import worldmap

    rows = world_log.load(session_dir)
    segs = segments(rows)
    lg = legs(rows, segs)
    unk = unlabelled(rows)

    print(f"session {session_dir}")
    print(f"  {sum(1 for r in rows if r.get('kind') == 'frame')} frames, "
          f"{sum(1 for r in rows if r.get('kind') == 'note')} notes")
    print(f"  recognised stretches: {len(segs)}")
    for s in segs:
        print(f"    {s['place']:24} {s['t_start']:7.1f}-{s['t_end']:7.1f}s  "
              f"n={s['n']:3}  score {s['mean_score']}")
    print(f"  direct legs: {len(lg)}")
    for l in lg:
        print(f"    {l['a']:22} -> {l['b']:22} {l['seconds']:6.2f}s  "
              f"bearing {l['bearing']}  ({l['n_transit']} transit frames)")
    print(f"  unlabelled stretches: {len(unk)}")
    for c in unk:
        print(f"    {c['t_start']:7.1f}-{c['t_end']:7.1f}s  n={c['n']:3}  "
              f"look at: {os.path.join(session_dir, c['representative'] or '?')}")

    if not write:
        print("\n  (dry run — pass --write to fold these legs into world_map.json)")
        return {"segments": segs, "legs": lg, "unlabelled": unk}

    if not lg:
        # Writing an empty graph is worse than writing none: WorldMap.load()
        # would then succeed and route() would return None for everything,
        # which reads as "no path exists" rather than "there is no map".
        raise SystemExit("refusing to write: this session yielded NO legs, and "
                         "an empty map is indistinguishable from a full one "
                         "that cannot find a route")
    m = worldmap.WorldMap.load(store) if os.path.exists(store) else worldmap.WorldMap()
    for l in lg:
        # Endpoints must be marked before they can be connected — an unmarked
        # name is an orphan island route() would hand back and bearing_to()
        # would then refuse. Positions are placeholders: routing and walking
        # read links, never coordinates.
        for n in (l["a"], l["b"]):
            if n not in m.landmarks:
                m.mark(n)
        if l["bearing"] is None:
            print(f"    skipping {l['a']} -> {l['b']}: no heading was readable "
                  f"across its {l['n_transit']} transit frames, and a leg "
                  f"without a bearing can be priced but never walked")
            continue
        # One step carrying the measured heading and duration. WALK_SPEED is
        # the stick magnitude the walk was made at and is NOT calibrated
        # against distance; it is recorded so the replay uses the same
        # magnitude as the recording, which is the only thing that has to match.
        m.connect(l["a"], l["b"],
                  [{"bearing": l["bearing"], "dur": l["seconds"],
                    "speed": WALK_SPEED}],
                  one_way=True, note=f"world_log {os.path.basename(session_dir)}")
    m.save(store)
    print(f"\n  wrote {store}: {len(m.landmarks)} node(s), "
          f"{sum(len(v) for v in m.links.values())} directed edge(s)")
    return {"segments": segs, "legs": lg, "unlabelled": unk}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        ss = world_log.sessions()
        if not ss:
            raise SystemExit("no sessions under world_log/ — record one first")
        args = [ss[-1]]
    build(args[0], write="--write" in sys.argv)
