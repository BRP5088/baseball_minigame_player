"""Per-leg table for the MERGE_STEPS_BY_LEG extension analysis (TASK 4).READ-ONLY on the project. Reads world_map.json, route3_steps.json,
route2_steps.json. Does NOT import graph_walk (places.py is under mutation in
this session and importing graph_walk would pull it in); instead the REAL
merge_steps() is lifted out of graph_walk.py by ast and exec'd, so this is the
shipped algorithm, not a mirror -- CLAUDE.md warns what mirrors cost.
"""
import ast
import json
import math
import os
import sysROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))def lift(module_path, names):
    """exec only the named top-level defs/assignments from a module's source."""
    src = open(module_path).read()
    tree = ast.parse(src)
    keep = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    keep.append(node)
    mod = ast.Module(body=keep, type_ignores=[])
    ns = {"math": math}
    exec(compile(mod, module_path, "exec"), ns)
    return nsgw = lift(os.path.join(ROOT, "graph_walk.py"),
          {"merge_steps", "MERGE_TOL_DEG", "MERGE_MAX_SEC", "_scaled",
           "LEG_SPEED_SCALE", "LEG_SPEED_MAX"})
merge_steps = gw["merge_steps"]
print(f"lifted merge_steps  MERGE_TOL_DEG={gw['MERGE_TOL_DEG']}  "
      f"MERGE_MAX_SEC={gw['MERGE_MAX_SEC']}  LEG_SPEED_MAX={gw['LEG_SPEED_MAX']}")m = json.load(open(os.path.join(ROOT, "world_map.json")))
r3 = json.load(open(os.path.join(ROOT, "route3_steps.json")))
r2 = json.load(open(os.path.join(ROOT, "route2_steps.json")))def circ_spread(vals):
    """max pairwise angular separation, degrees."""
    best = 0.0
    for a in vals:
        for b in vals:
            d = abs((a - b + 180.0) % 360.0 - 180.0)
            best = max(best, d)
    return bestdef circ_mean(vals, w=None):
    w = w or [1.0] * len(vals)
    x = sum(math.sin(math.radians(v)) * k for v, k in zip(vals, w))
    y = sum(math.cos(math.radians(v)) * k for v, k in zip(vals, w))
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0def dist(steps):
    return sum(s["dur"] * s["speed"] for s in steps)def r3_slice(lk):
    """Map a leg's steps back onto route3 by t0, so `cam` can be read."""
    t0s = [s.get("t0") for s in lk["steps"]]
    if all(t is not None for t in t0s):
        idx = [i for i, s in enumerate(r3) if abs(s["t0"] - t0s[0]) < 1e-6]
        if idx:
            i0 = idx[0]
            return list(range(i0, i0 + len(t0s)))
    return None# route2 equivalents, by inspection of bearings/cam (CLAUDE.md OPEN-17 uses
# route2 for the same legs). Marked ASSUMED in the writeup.
R2_SLICES = {
    ("office_corridor", "office_door"): None,        # route2 starts elsewhere
    ("office_door", "portrait_room"): list(range(0, 20)),
    ("portrait_room", "bar_pool_room"): [20, 21, 22],
    ("bar_pool_room", "bar_jukebox"): list(range(23, 30)),
    ("bar_jukebox", "dealer_table"): [30, 31, 32, 33],
}order = [("office_corridor", "office_door"), ("office_door", "portrait_room"),
         ("portrait_room", "bar_pool_room"), ("bar_pool_room", "bar_jukebox"),
         ("bar_jukebox", "dealer_table")]rows = []
for a, b in order:
    lk = m["links"][a][b]
    steps = lk["steps"]
    bearings = [s["bearing"] for s in steps]
    durs = [s["dur"] for s in steps]
    n = len(steps)
    merged = merge_steps([dict(s) for s in steps])
    sl = r3_slice(lk)
    if sl is None and (a, b) == ("bar_pool_room", "bar_jukebox"):
        sl = list(range(27, 32))   # per the distance pin test and CLAUDE.md
    cams = [r3[i]["cam"] for i in sl] if sl else []
    r3b = [r3[i]["bearing"] for i in sl] if sl else []
    r2sl = R2_SLICES[(a, b)]
    r2cams = [r2[i]["cam"] for i in r2sl] if r2sl else []
    r2b = [r2[i]["bearing"] for i in r2sl] if r2sl else []
    # per-step |delta| between consecutive bearings / cams (route3)
    def deltas(v):
        return [abs((v[i + 1] - v[i] + 180) % 360 - 180) for i in range(len(v) - 1)]
    row = {
        "leg": f"{a} -> {b}",
        "n_steps": n,
        "bearing_spread_deg": round(circ_spread(bearings), 2),
        "cam_spread_deg_route3": round(circ_spread(cams), 2) if cams else None,
        "cam_spread_deg_route2": round(circ_spread(r2cams), 2) if r2cams else None,
        "bearing_spread_deg_route2": round(circ_spread(r2b), 2) if r2b else None,
        "total_dur_s": round(sum(durs), 3),
        "last_step_dur_s": durs[-1],
        "last_step_speed": steps[-1]["speed"],
        "typical_step_dur_s": round(sorted(durs)[n // 2], 3),
        "speeds": f"{min(s['speed'] for s in steps):.3f}-{max(s['speed'] for s in steps):.3f}",
        "distance_units": round(dist(steps), 4),
        "merged_pushes_at_tol8_cap4": len(merged),
        "merged_durs": [round(x["dur"], 3) for x in merged],
        "merged_bearings": [round(x["bearing"], 2) for x in merged],
        "merged_speeds": [round(x["speed"], 3) for x in merged],
        "merged_distance_units": round(dist(merged), 4),
        "accelerations_removed": n - len(merged),
        "settles_removed_s": round(0.35 * (n - len(merged)), 2),
        "turns_removed": n - len(merged),
        "r3_slice": sl,
        "r3_cam_mean": round(circ_mean(cams), 2) if cams else None,
        "r3_bearing_wmean": round(circ_mean(bearings, durs), 2),
        "r3_deltas_bearing_gt4": sum(1 for d in deltas(r3b) if d > 4.0) if r3b else None,
        "r3_deltas_cam_gt4": sum(1 for d in deltas(cams) if d > 4.0) if cams else None,
        "r3_transitions": len(r3b) - 1 if r3b else None,
    }
    rows.append(row)print()
hdr = ["leg", "n_steps", "bearing_spread_deg", "cam_spread_deg_route3",
       "total_dur_s", "last_step_dur_s", "typical_step_dur_s", "distance_units",
       "merged_pushes_at_tol8_cap4", "accelerations_removed", "settles_removed_s"]
print(" | ".join(hdr))
for r in rows:
    print(" | ".join(str(r[h]) for h in hdr))
print()
for r in rows:
    print(json.dumps(r, indent=None))# Distance check: merging preserves speed*dur? NO -- merge takes MAX speed of the
# parts, so distance is NOT preserved when speeds differ across the merged steps.
print()
print("distance drift introduced by merge_steps (speed=max of parts):")
for r in rows:
    print(f"  {r['leg']:36s} recorded {r['distance_units']:.4f}  merged "
          f"{r['merged_distance_units']:.4f}  "
          f"ratio {r['merged_distance_units']/r['distance_units']:.3f}")json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "leg_table.json"), "w"), indent=1)
