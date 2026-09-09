"""Harvest every live yaw-null line and the align dx that followed it.READS LOGS ONLY. Run:
    .venv/bin/python -B drafts/yaw/harvest_yaw_null.pyAnswers, from the archived overnight logs (no console):
  1. how often align_at_node's yaw null converged, and to what residual;
  2. how often each of its three fall-through branches fired (want None /
     got_h None / exception) -- these are the branches that measure dx with
     yaw NOT nulled and then strafe on it;
  3. the FIRST dx align_lateral saw at each node AFTER the null, i.e. the
     lateral offset that is NOT yaw.
The residual is NOT censored at the tolerance: slow_traverse.turn_to returns
the last read heading even when it did not converge, and align_at_node logs
`err` from that same value, so a non-converged null shows up here as a
residual > 0.5.
"""
import glob
import os
import re
import statistics as statsROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS = sorted(glob.glob(os.path.join(ROOT, "overnight", "**", "*.log"), recursive=True))NULL = re.compile(r"align at (\w+): yaw nulled to ([0-9.]+) \(reference ([0-9.]+)\) — ([0-9.]+) deg REMAINING")
UNREAD = re.compile(r"align at (\w+): reference heading UNREADABLE")
NOTURN = re.compile(r"align at (\w+): could not turn to the reference heading")
FAILED = re.compile(r"align at (\w+): yaw null FAILED")
STEP1 = re.compile(r"align: step 1/\d+ dx=([+-][0-9.]+) \(prev --\)")
WITHIN0 = re.compile(r"align: within \d+px \(dx=([+-][0-9.]+)\) after 0 step\(s\)")
OUTCOME = re.compile(r"align: (within \d+px|dx barely changed|diverging|\d+ steps used, still|offset unmeasurable|dx=[+-][0-9.]+ is finer)")residuals, by_node, first_dx, outcomes = [], {}, {}, {}
fall = {"unreadable": 0, "could_not_turn": 0, "failed": 0}
files_hit = set()
for path in LOGS:
    node = None
    for line in open(path, errors="replace"):
        m = NULL.search(line)
        if m:
            node, got, ref, res = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
            residuals.append(res)
            by_node.setdefault(node, []).append(res)
            files_hit.add(os.path.relpath(path, ROOT))
            continue
        for key, rx in (("unreadable", UNREAD), ("could_not_turn", NOTURN), ("failed", FAILED)):
            if rx.search(line):
                fall[key] += 1
                files_hit.add(os.path.relpath(path, ROOT))
        if node is None:
            continue
        m = STEP1.search(line) or WITHIN0.search(line)
        if m:
            first_dx.setdefault(node, []).append(float(m.group(1)))
        m = OUTCOME.search(line)
        if m:
            kind = m.group(1)
            kind = re.sub(r"\d+ steps used, still", "N steps used, still out", kind)
            kind = re.sub(r"dx=[+-][0-9.]+ is finer", "finer than one push", kind)
            kind = re.sub(r"within \d+px", "within tol", kind)
            outcomes.setdefault(node, {}).setdefault(kind, 0)
            outcomes[node][kind] += 1
            node = Noneprint(f"logs scanned: {len(LOGS)}; logs with yaw-null lines: {len(files_hit)}")
for f in sorted(files_hit):
    print("   ", f)
print(f"\nyaw-null lines: n={len(residuals)}")
if residuals:
    print(f"  residual deg: max {max(residuals):.1f}  median {stats.median(residuals):.1f}  "
          f"mean {stats.mean(residuals):.2f}")
    print(f"  residual > 0.5 deg (i.e. the null did NOT converge): "
          f"{sum(1 for r in residuals if r > 0.5)}")
    print(f"  residual x 18.8 px/deg: max {max(residuals)*18.8:.1f}px  vs ALIGN_TOL_PX 35")
print(f"fall-through branches (dx measured with yaw NOT nulled): {fall}")
print("\nper node:")
for node in sorted(by_node):
    r = by_node[node]
    print(f"  {node:15s} n={len(r):3d}  residual max {max(r):.1f} median {stats.median(r):.1f}")
    fd = first_dx.get(node, [])
    if fd:
        pos = sum(1 for d in fd if d > 0)
        print(f"  {'':15s} first dx after null: n={len(fd)} median {stats.median(fd):+.1f} "
              f"min {min(fd):+.1f} max {max(fd):+.1f}  positive {pos}/{len(fd)}")
        print(f"  {'':15s} |first dx| > 35 (needed a strafe): {sum(1 for d in fd if abs(d) > 35)}/{len(fd)}")
    print(f"  {'':15s} outcomes: {outcomes.get(node, {})}")
