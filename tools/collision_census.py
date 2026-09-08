"""Where a closed-loop walk WASTES its time: escapes, stalls, misses and
wall-scale fits, bucketed by chain region, over the journals of a batch.

    .venv/bin/python -B tools/collision_census.py [<journal glob>] [--since EPOCH]

The user's observation (2026-09-07): "you walk into Wanda, the wall near Wanda
and the bar a lot." This counts it instead of arguing about it: for every
journal, the iterations whose action is an escape rung, 'stalled', 'weak' or
'miss', or whose fit scale is at or above chain_walk.WALL_SCALE (pressed close
to something), grouped by the plan region the estimate was in, with the
seconds those iterations cost. Regions follow the chain's turn stops.
"""
import glob, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import chain_walk  # noqa: E402

REGIONS = [(0, 3, "office"), (4, 39, "corridor+stairs"), (40, 88, "door->street"),
           (89, 114, "portrait room (Wanda at 109-114)"), (115, 129, "turn->bar entrance"),
           (130, 166, "bar counter->tables"), (167, 196, "tables->last turn"), (197, 204, "table approach")]
WASTE = ("stalled", "weak", "miss", "turn-retry", "turn-back", "turn-wait", "lost")


def region(k):
    for lo, hi, name in REGIONS:
        if lo <= k <= hi:
            return name
    return "?"


def main(pattern, since=0):
    files = [p for p in sorted(glob.glob(pattern), key=os.path.getmtime) if os.path.getmtime(p) >= since]
    per_region = defaultdict(lambda: {"trials": 0, "waste_it": 0, "waste_s": 0.0, "escapes": 0, "wall": 0, "lost_here": 0})
    totals = {"trials": 0, "arrived": 0, "seconds": 0.0, "waste_s": 0.0}
    for p in files:
        rows = [json.loads(l) for l in open(p) if l.strip()]
        if not rows:
            continue
        totals["trials"] += 1
        arrived = rows[-1].get("action") == "arrived" or rows[-1].get("arrived")
        totals["arrived"] += bool(arrived)
        totals["seconds"] += rows[-1].get("elapsed", 0)
        seen = set()
        for r in rows:
            reg = region(r["k"]); seen.add(reg)
            a = r.get("action") or ""
            f = r.get("fix") or {}
            waste = a in WASTE or a.startswith("escape:")
            if waste:
                per_region[reg]["waste_it"] += 1
                per_region[reg]["waste_s"] += r.get("seconds", 0) or 0
                totals["waste_s"] += r.get("seconds", 0) or 0
            if a.startswith("escape:"):
                per_region[reg]["escapes"] += 1
            if (f.get("scale") or 0) >= chain_walk.WALL_SCALE:
                per_region[reg]["wall"] += 1
            if a in ("lost",) or (r is rows[-1] and not arrived):
                per_region[reg]["lost_here"] += 1
        for reg in seen:
            per_region[reg]["trials"] += 1
    print(f"{totals['trials']} journals, {totals['arrived']} arrived, {totals['seconds']:.0f} s walked, "
          f"{totals['waste_s']:.0f} s ({100*totals['waste_s']/max(1,totals['seconds']):.0f}%) in escapes/stalls/misses")
    print(f"{'region':38s} {'trials':>6s} {'waste it':>8s} {'waste s':>8s} {'s/trial':>7s} {'escapes':>7s} {'wall':>5s} {'ended':>5s}")
    for lo, hi, name in REGIONS:
        d = per_region[name]
        if not d["trials"]:
            continue
        print(f"{name:38s} {d['trials']:6d} {d['waste_it']:8d} {d['waste_s']:8.0f} {d['waste_s']/d['trials']:7.1f} {d['escapes']:7d} {d['wall']:5d} {d['lost_here']:5d}")
    return per_region


if __name__ == "__main__":
    since = float(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else 0
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and not (i > 1 and sys.argv[i - 1] == "--since")]
    main(args[0] if args else os.path.join(ROOT, "overnight", "chain_journals", "route_user_1853_t*.jsonl"), since)
