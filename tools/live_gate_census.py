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


def is_iteration_fit_row(r):
    """Is this row ONE ITERATION'S OWN in-window fit -- the unit of this census?

    A row carrying a fit and an iteration number WAS that, exactly, until
    2026-09-08. `chain_walk.DOOR_STOP_EXTRA_PUSH` breaks the equivalence: a
    `door-step` row is an extra push taken INSIDE an iteration, fitted at a
    position the walk has not yet verified as the stop, and it shares its
    iteration number with the stop's own row. Counted here it would weight the
    iterations that have one twice over and mix a mid-iteration fit into the
    very populations FIX_MIN / WEAK_MIN / STRONG are calibrated against -- a
    gate landing inside a population it was not measured on (CLAUDE.md 10.4),
    arriving by the back door of an unrelated patch.

    Named rather than inlined so the suite can run it: this file does its work
    at module level and cannot be imported, so
    tests/routing/test_chain_walk.py compiles this definition out of the file
    and drives it with the rows a real walk records.
    """
    f = r.get("fix")
    return bool(f and f.get("inliers") is not None and r.get("iteration")
                and r.get("action") != "door-step")


def frame_for(shots, iteration):
    """The iteration's OWN frame -- SORTED, because an iteration saves several.

    A rescue saves its three look frames beside the iteration's own, and a
    door step saves `_door1`. This census matches ONE frame per sampled
    iteration against a window 30 ahead, and an unsorted glob handed it
    whichever the filesystem listed first -- so the FAR population could be
    measured on a frame taken at a different spot in the same iteration. The
    base name sorts before any suffix ("." < "_"). Same fix, same reason, as
    `turn_review.frame_for`.
    """
    fs = sorted(glob.glob(os.path.join(shots, f"it_{int(iteration):03d}_k*.jpg")))
    return fs[0] if fs else None


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
        if not is_iteration_fit_row(r):
            continue
        (near_arr if arrived else near_fail).append(int(r["fix"]["inliers"]))
        if r["iteration"] % 4:
            continue
        fp = frame_for(d, r["iteration"])
        if fp is None:
            continue
        k = int(r["k"])
        hint = k + 30 if k + 33 < n else max(0, k - 33)
        fx = ch.locate(Image.open(fp), hint, window=3)
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
