"""CRAWL MODE: one action at a time, with a HUMAN label for what happened.

WHY THIS EXISTS. Nothing on this rig can tell, per push, whether the character
hit something. `slow_traverse.walk_leg` measures how far the view moved and
returns it -- and the closed loop calls it as a bare statement and DISCARDS the
value, which is CLAUDE.md 10.1's catalogued shape verbatim ("walk_forward
returns how far the view moved; both step loops threw it away, so walking into
an NPC looked like walking"). Mining it back out of the logs shows it carries
signal but cannot be calibrated: a push travelling under 5 px happens on 1.6% of
pushes in walks that ARRIVE and 10.9% in walks that FAIL (n = 4,969 / 384), and
"the walk failed" is not "this push was the collision". The label is at the
wrong resolution.

The user, watching the stream, proposed the fix: take one action, and they say
whether it hit a wall or the bar. That is the per-push ground truth no amount of
log mining can produce.

WHAT IT RECORDS PER STEP, so the labels can decide which signal separates:
  change      the frame delta walk_leg already computes, in the same units
  null_change the SAME measurement with NO action -- the paired control
  ratio       change / null_change. CLAUDE.md's OPEN-1 measured this paired
              ratio as the ONLY signal that separated moved from blocked
              (moved 0.10-0.34, blocked 0.82, a gap of 0.49 at n = 6 headings)
              while the ABSOLUTE delta and the absolute inlier count both
              overlapped and were unusable. It has never been implemented.
  inliers/scale/k  the chain sensor's own answer, for context
  frame       the .jpg, so a disagreement can be adjudicated by eye

It writes one JSON line per step, with `label` left null. Label them afterwards
with --label, which is a separate step precisely so the numbers are recorded
BEFORE anyone knows the answer.

    .venv/bin/python -B tools/crawl.py --steps 12            # crawl and record
    .venv/bin/python -B tools/crawl.py --label 3,5,7=bar 9=wall
    .venv/bin/python -B tools/crawl.py --report             # do the signals separate?
    .venv/bin/python -B tools/crawl.py --selftest

It DRIVES THE CONSOLE, so it refuses while a trial harness is running.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join("overnight", "crawl.jsonl")
FRAMES = os.path.join("overnight", "crawl_frames")


def _pgrep(pattern):
    return subprocess.run(["pgrep", "-f", pattern],
                          capture_output=True, text=True).stdout.strip()


def harness_running(probe=_pgrep):
    """True if a trial harness is live. Injected so the selftest drives both."""
    return bool(probe("chain_trials.py"))


def ratio(change, null):
    """change / null, the paired signal -- None when the null is unusable.

    Paired because an ABSOLUTE delta cannot work: one heading's null read 353
    while another's push read 407, so the same number means blocked in one place
    and moved in another (CLAUDE.md OPEN-1). Dividing by this heading's own null
    removes the scene, which is also what makes it robust to an NPC wandering
    through the shot.
    """
    if null is None or null <= 0:
        return None
    return round(change / null, 3)


def summarise(rows):
    """-> (labelled, by-label stats, whether any signal separates)."""
    import statistics as st
    lab = [r for r in rows if r.get("label")]
    hit = [r for r in lab if r["label"] != "clean"]
    clean = [r for r in lab if r["label"] == "clean"]
    out = {}
    for name in ("change", "ratio"):
        h = sorted(r[name] for r in hit if r.get(name) is not None)
        c = sorted(r[name] for r in clean if r.get(name) is not None)
        if len(h) < 3 or len(c) < 3:
            out[name] = None
            continue
        gap = min(c) - max(h)          # clean should move MORE than a collision
        out[name] = {"hit_n": len(h), "clean_n": len(c),
                     "hit_median": st.median(h), "clean_median": st.median(c),
                     "hit_max": max(h), "clean_min": min(c),
                     "separates": gap > 0, "gap": round(gap, 3)}
    return lab, out


def report(path=OUT):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    lab, out = summarise(rows)
    print(f"{len(rows)} steps recorded, {len(lab)} labelled")
    if not lab:
        print("  nothing labelled yet -- run --label first")
        return
    from collections import Counter
    print("  labels:", dict(Counter(r["label"] for r in lab)))
    for name, s in out.items():
        if s is None:
            print(f"  {name}: too few labelled samples on one side to judge "
                  f"(need 3 of each)")
            continue
        verdict = ("SEPARATES" if s["separates"] else
                   "OVERLAPS -- no threshold on this quantity can work")
        print(f"  {name}: hit n={s['hit_n']} median {s['hit_median']:.2f} "
              f"max {s['hit_max']:.2f} | clean n={s['clean_n']} median "
              f"{s['clean_median']:.2f} min {s['clean_min']:.2f}  -> {verdict}"
              f" (gap {s['gap']})")
    print("\n  A threshold is only usable if it sits BETWEEN the two, with a "
          "gap.\n  Four bugs on this project came from cutting through ONE "
          "population (10.4).")


def label(spec, path=OUT):
    """--label '3,5=bar 9=wall 1,2,4=clean' -- step numbers to a label."""
    rows = [json.loads(l) for l in open(path) if l.strip()]
    by_step = {r["step"]: r for r in rows}
    n = 0
    for part in spec:
        steps, _, name = part.partition("=")
        if not name:
            raise SystemExit(f"expected steps=label, got {part!r}")
        for s in steps.split(","):
            r = by_step.get(int(s))
            if r is None:
                raise SystemExit(f"no step {s} recorded")
            r["label"] = name
            n += 1
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"labelled {n} step(s)")


def crawl(steps, mag, sec, chain_name):
    import numpy as np
    import analog_replay as ar
    import compass
    import chain as chain_mod
    import walk_steps as ws
    import slow_traverse as st

    os.makedirs(FRAMES, exist_ok=True)
    ch = chain_mod.Chain.load(os.path.join("chains", chain_name),
                              log=lambda *a: None)

    def grey():
        im = compass.fast_capture()
        return im, np.asarray(im.convert("L"), dtype=float)

    def delta(a, b):
        return float(np.abs(b - a).mean())

    prev_k = 1
    with open(OUT, "a") as fh:
        for i in range(1, steps + 1):
            # THE PAIRED NULL FIRST: the same measurement with nothing sent, so
            # this heading's own scene animation is divided out.
            _, a0 = grey()
            time.sleep(sec)
            _, a1 = grey()
            null = delta(a0, a1)

            im0, b0 = grey()
            ar.send([f"left_x 0", f"left_y {ar.to_axis(-abs(mag))}",
                     "right_x 0", "right_y 0"])
            time.sleep(sec)
            ar.send(["left_x 0", "left_y 0"])
            time.sleep(0.35)
            im1, b1 = grey()
            change = delta(b0, b1)

            fix = ch.locate(im1, prev_k, window=6)
            if fix is not None:
                prev_k = fix.k
            frame = os.path.join(FRAMES, f"step{i:03d}.jpg")
            im1.save(frame, quality=85)
            row = {"step": i, "change": round(change, 2),
                   "null_change": round(null, 2), "ratio": ratio(change, null),
                   "inliers": None if fix is None else fix.inliers,
                   "k": None if fix is None else fix.k,
                   "scale": None if fix is None else round(float(fix.scale), 2),
                   "heading": ws.read_heading(), "frame": frame, "label": None}
            fh.write(json.dumps(row) + "\n")
            fh.flush()          # written AS IT GOES: a killed crawl keeps its rows
            print(f"  step {i:3d}  change {change:6.1f}  null {null:5.1f}  "
                  f"ratio {row['ratio']}  inliers {row['inliers']}  "
                  f"k {row['k']}  scale {row['scale']}")
    print(f"\n{steps} steps -> {OUT}. Now say which hit something, e.g.\n"
          f"  .venv/bin/python -B tools/crawl.py --label '3,5=bar 9=wall' \n"
          f"and label the rest clean. Then --report.")


def selftest():
    assert harness_running(lambda p: "1") is True
    assert harness_running(lambda p: "") is False
    seen = []
    harness_running(lambda p: seen.append(p) or "")
    assert seen == ["chain_trials.py"], seen
    assert ratio(10.0, 20.0) == 0.5
    assert ratio(10.0, 0) is None and ratio(10.0, None) is None
    # separation: clean must move MORE than a collision, and the gap decides
    hit = [{"label": "bar", "change": 2.0, "ratio": 0.1} for _ in range(3)]
    clean = [{"label": "clean", "change": 20.0, "ratio": 0.9} for _ in range(3)]
    lab, out = summarise(hit + clean)
    assert len(lab) == 6
    assert out["change"]["separates"] is True, out["change"]
    assert out["ratio"]["separates"] is True
    # ... and overlapping populations must NOT be reported as separating
    mixed = ([{"label": "bar", "change": 25.0, "ratio": 0.5} for _ in range(3)]
             + clean)
    _, out2 = summarise(mixed)
    assert out2["change"]["separates"] is False, out2["change"]
    # too few on one side is "cannot judge", never "separates"
    _, out3 = summarise(hit + clean[:1])
    assert out3["change"] is None
    print("selftest OK: the guard both ways, the paired ratio, separation, "
          "overlap, and the too-few case")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--mag", type=float, default=0.45)
    ap.add_argument("--sec", type=float, default=0.40)
    ap.add_argument("--chain", default="route_user_1853")
    ap.add_argument("--label", nargs="+")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); raise SystemExit(0)
    if a.report:
        report(); raise SystemExit(0)
    if a.label:
        label(a.label); raise SystemExit(0)
    if harness_running():
        raise SystemExit("REFUSING: chain_trials.py is running. Crawl mode "
                         "DRIVES THE STICK and would fight the live trial.")
    crawl(a.steps, a.mag, a.sec, a.chain)
