"""Build world_map.json from the RECORDED route — offline, no game needed.

    python3 build_world_map.py            # dry run: show what it would write
    python3 build_world_map.py --write    # write world_map.json and seed places/

WHY THIS CAN BE DONE OFFLINE
----------------------------
Two artefacts already on disk hold the whole route:

  route3_steps.json                       40 controller steps, each with a
                                          bearing, a duration and a speed
  demos/walk3_full_20260828_050731/       712 frames at 6fps over the same walk

So the graph does not need a live walking pass to exist. It needs the steps
grouped into legs, a frame picked at each leg boundary to serve as that node's
appearance, and the pair written out. Live time then goes on VERIFYING the
graph rather than on discovering it, which matters because a walk cannot be
repeated identically and every pass costs real minutes at the console.

WHAT A LEG IS
-------------
A stretch of consecutive steps whose bearing stays within BEARING_TOL. A curve
stays ONE leg and keeps all its sub-steps: averaging a 26-degree bend into a
single heading walks into a wall.

WHAT THIS DELIBERATELY DOES NOT DECIDE
--------------------------------------
Node NAMES are provisional and set here by hand from looking at the frames.
Nothing infers them. And the landmark coordinates it writes are dead-reckoned
with an uncalibrated speed, so they are for display only — routing and walking
read `links`, never the coordinates, so that error cannot steer anything.
"""

import json
import os
import re
import shutil
import sys

STEPS_FILE = "route3_steps.json"
DEMO_DIR = "demos/walk3_full_20260828_050731"
STORE = "world_map.json"
PLACES = "places"

# Consecutive steps within this many degrees are one leg. Chosen so the known
# curve (338 -> 4 degrees over 16 steps) stays intact while the five genuine
# direction changes (each > 60 degrees) still split.
BEARING_TOL = 25.0

# Provisional, from looking at the six boundary frames. Renaming later is a
# directory move and a key rename — cheap, so this does not block.
# MEASURED 2026-09-01, pairwise descriptor similarity between the six node
# frames: every pair is <= 0.474 EXCEPT office_corridor vs office_door at
# 0.726, which is above places.MIN_SCORE (0.55). They are the same dark
# corridor 5.24s apart and the localiser cannot tell them apart — that is a
# fact about the world, not a bug to tune away.
#
# They stay as separate GRAPH nodes because the 5.24s walk between them is real
# and the route needs it. What must not happen is trusting identify() to say
# which of the two we are standing in. office_corridor is the spawn, reached
# deterministically by reset_environment(), so nothing has to recognise it;
# arrival at office_door is confirmed by having walked the leg, not by
# appearance. CONFUSABLE records this so an executor can refuse to use
# identify() to choose between them.
CONFUSABLE = [("office_corridor", "office_door")]

# Nodes that get an APPEARANCE reference under places/. The two office nodes
# are deliberately excluded, and that is a measurement, not tidiness:
#
#   - their frames are dark and nearly structureless (masked edge energy 91,
#     against 286 for the dealer table), so 91% of each descriptor is the
#     vignette component EVERY frame shares;
#   - seeding office_door was tried and immediately produced a fresh false
#     positive — beside_dealer_table/sweep01_124 and sweep02_145 identified as
#     office_door at 0.790 and 0.801. The same sponge that made an upstairs
#     door match the bar at 0.906, just relocated;
#   - and they are not needed: office_corridor IS the reset spawn, reached
#     deterministically by reset_environment(), and office_door is confirmed by
#     having walked the leg to it, not by recognising it.
#
# A reference that cannot identify its own place but does attract other places
# is worse than no reference.
SEED_PLACES = [n for n in ("portrait_room", "bar_pool_room", "bar_jukebox",
                           "dealer_table")]

NODE_NAMES = ["office_corridor",   # coat rack, doorway ahead
              "office_door",       # facing a closed panelled door
              "portrait_room",     # framed portraits, NPC, patterned rug
              "bar_pool_room",     # pool table, two NPCs, bottles
              "bar_jukebox",       # NPC with a cue, machine at left
              "dealer_table"]      # the "Baseball Cards [] Play ($50)" prompt


def _ang(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def legs_from_steps(steps, tol=BEARING_TOL):
    out, cur = [], [steps[0]]
    for s in steps[1:]:
        if _ang(s["bearing"], cur[-1]["bearing"]) <= tol:
            cur.append(s)
        else:
            out.append(cur)
            cur = [s]
    out.append(cur)
    return out


def demo_frames(d=DEMO_DIR):
    fs = []
    for p in sorted(os.listdir(d)):
        m = re.match(r"f_(\d+\.\d+)\.jpg$", p)
        if m:
            fs.append((float(m.group(1)), os.path.join(d, p)))
    return sorted(fs)


def frame_at(frames, t):
    return min(frames, key=lambda f: abs(f[0] - t))


def build(write=False):
    import worldmap

    steps = json.load(open(STEPS_FILE))
    legs = legs_from_steps(steps)
    frames = demo_frames()
    bounds = [legs[0][0]["t0"]] + [l[-1]["t0"] + l[-1]["dur"] for l in legs]
    if len(bounds) != len(NODE_NAMES):
        raise SystemExit(
            f"{len(legs)} legs give {len(bounds)} nodes but {len(NODE_NAMES)} "
            f"names are defined — the segmentation changed, so the names must "
            f"be re-checked against the frames before anything is written")

    m = worldmap.WorldMap()
    m.mark(NODE_NAMES[0])
    for name, leg in zip(NODE_NAMES[1:], legs):
        # Dead-reckon a position for display only. Speed is uncalibrated, so
        # these coordinates are NOT trustworthy for navigation and nothing
        # reads them for it.
        for s in leg:
            m.walk(s["bearing"], s["dur"] * s["speed"])
        m.mark(name)

    print(f"{len(steps)} steps -> {len(legs)} legs, {len(bounds)} nodes\n")
    for i, (a, b, leg) in enumerate(zip(NODE_NAMES, NODE_NAMES[1:], legs)):
        t0, t1 = leg[0]["t0"], leg[-1]["t0"] + leg[-1]["dur"]
        note = f"{STEPS_FILE} t {t0:.2f}-{t1:.2f}"
        m.connect(a, b, leg, one_way=True, note=note)
        bs = [s["bearing"] for s in leg]
        print(f"  leg {i}: {a:16} -> {b:16} {t1-t0:5.2f}s  "
              f"{len(leg):2} steps  bearing {min(bs):.0f}-{max(bs):.0f}")

    print("\n  node appearance frames:")
    seeds = []
    for name, t in zip(NODE_NAMES, bounds):
        ft, path = frame_at(frames, t)
        seeds.append((name, ft, path))
        print(f"    {name:16} t={t:6.2f}  {os.path.basename(path)}")

    path = m.route(NODE_NAMES[0], NODE_NAMES[-1])
    print(f"\n  route {NODE_NAMES[0]} -> {NODE_NAMES[-1]}: {path}")
    print(f"  cost: {m.route_cost(path):.2f}s")
    for a, b in zip(path, path[1:]):
        m.steps_for(a, b)          # raises if any leg is unwalkable
    print("  every leg on that route has walkable steps")

    if not write:
        print("\n  (dry run — pass --write to write world_map.json and seed places/)")
        return m

    written = 0
    for name, ft, src in seeds:
        if name not in SEED_PLACES:
            print(f"    (not seeding {name}: see SEED_PLACES)")
            continue
        d = os.path.join(PLACES, name)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, f"route_{ft:07.2f}.jpg")
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
        written += 1
    m.confusable = [list(c) for c in CONFUSABLE]
    m.save(STORE)
    print(f"\n  wrote {STORE}: {len(m.landmarks)} node(s), "
          f"{sum(len(v) for v in m.links.values())} directed leg(s)")
    # COUNT WHAT WAS WRITTEN, not what was considered. Reporting len(seeds)
    # here said "seeded 6" while writing 4.
    print(f"  seeded {written} of {len(seeds)} node frame(s) under {PLACES}/ "
          f"({len(seeds) - written} excluded by SEED_PLACES)")
    return m


if __name__ == "__main__":
    build(write="--write" in sys.argv)
