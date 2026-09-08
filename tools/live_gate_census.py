"""Gate populations on LIVE trial frames, not the drive's own frames.

NEAR = the journal's in-window best-fit inliers for every iteration of every
trial that ARRIVED (the loop's own answer on frames whose walk ended at the
prompt). FAR = the same frames matched against a window of waypoints 30 ahead
of the journal's k (recomputed here). The gates FIX_MIN / WEAK_MIN / STRONG
must sit between these, not inside the drive's census (the audit, 2026-09-07).
"""
import glob, json, os, re, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chain

ch = chain.Chain.load("chains/route_user_1853", log=lambda m: None)
n = len(ch.waypoints)
lines = {}
for log in glob.glob("overnight/chain_trials_batch*.log") + ["overnight/chain_trials.log"]:
    pass
journals = sorted(glob.glob("overnight/chain_journals/route_user_1853_t*.jsonl"), key=lambda p: int(re.search(r"_(\d{10})\.jsonl$", p).group(1)))
dirs = sorted(glob.glob("overnight/chain_frames/t*"), key=lambda p: int(os.path.basename(p)[1:]))
near_arr, near_fail, far = [], [], []
n_frames = 0
for j in journals:
    jt = int(re.search(r"_(\d{10})\.jsonl$", j).group(1))
    if jt < 1788824800:          # batch 4 onward (the controller with verified stops)
        continue
    d = next((p for p in dirs if jt <= int(os.path.basename(p)[1:]) // 1000 <= jt + 90), None)
    if d is None:
        continue
    rows = [json.loads(l) for l in open(j)]
    arrived = bool(rows) and rows[-1].get("action") == "arrived"
    for r in rows:
        f = r.get("fix")
        if not f or f.get("inliers") is None or not r.get("iteration"):
            continue
        (near_arr if arrived else near_fail).append(int(f["inliers"]))
        if r["iteration"] % 4:
            continue
        fs = glob.glob(os.path.join(d, f"it_{int(r['iteration']):03d}_k*.jpg"))
        if not fs:
            continue
        k = int(r["k"])
        hint = k + 30 if k + 33 < n else max(0, k - 33)
        fx = ch.locate(Image.open(fs[0]), hint, window=3)
        far.append(0 if fx is None else int(fx.inliers))
        n_frames += 1
def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None
def desc(v):
    return dict(n=len(v), p05=q(v, .05), p25=q(v, .25), median=q(v, .5), p75=q(v, .75), p95=q(v, .95), max=max(v) if v else None)
out = {"near_arrived": desc(near_arr), "near_failed": desc(near_fail), "far": desc(far), "far_frames": n_frames}
os.makedirs("overnight/census", exist_ok=True)
json.dump(out, open("overnight/census/live_gate_census.json", "w"), indent=1)
for k_, v in out.items():
    print(k_, v)
