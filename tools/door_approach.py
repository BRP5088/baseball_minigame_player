"""How many pushes should the route take before it turns to the front door?

THE QUESTION, from the user: compare 7 pushes against 6.5 and 6.

THE ROUTE'S OWN ANSWER IS SIX. `plan_indices` gives six push entries along
heading 271.3 (targets 4, 7, 10, 13, 16, 19), then the turn-only stop at
waypoint 39 which turns to 1.6 -- north, the front door.
`DOOR_STOP_EXTRA_PUSH` (patch50, shipped ON) adds one more, so the build walks
seven. That flag won its A/B 10/10 against 9/10, and the instrument was the fit
at the 39 stop: head-on 66 inliers at scale 1.04 on the on arm, against 38
inliers at 0.96 with a 0.80 tail on the off arm.

THE INSTRUMENT, the same one, because it decided the last question and is more
sensitive than arrival. `scale` is how big the scene looks against the recorded
waypoint. Below 1.0 the character is SHORT of the reference; near 1.0 it is
where the drive was.

METHOD. Each trial: reset to the deterministic spawn, turn to the route heading,
take N pushes, turn to the door heading, then fit the frame against the door
stop. The conditions are INTERLEAVED, never blocked, because route performance
has a large session-to-session component that would otherwise be confounded with
the condition (CLAUDE.md 10.5).

It reports the raw numbers per condition and invents no threshold.

    .venv/bin/python -B tools/door_approach.py --repeats 3
    .venv/bin/python -B tools/door_approach.py --selftest
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join("overnight", "door_approach.jsonl")
FRAMES = os.path.join("overnight", "door_approach_frames")
ROUTE_HEADING = 271.3        # plan[1..6], the corridor
DOOR_HEADING = 1.6           # plan[7], the turn-only stop at waypoint 39
DOOR_K = 39


def _pgrep(pattern):
    return subprocess.run(["pgrep", "-f", pattern],
                          capture_output=True, text=True).stdout.strip()


def harness_running(probe=_pgrep):
    return bool(probe("overnight/chain_trials.py"))


def plan_pushes(n):
    """N as (whole pushes, trailing fraction). 6.5 -> (6, 0.5), 7 -> (7, 0.0).

    A half push is half the SECONDS at the same magnitude. It is not half the
    distance: CLAUDE.md 6 measured that a push under ~0.10 s does not move the
    character at all, and that short pushes are mostly acceleration, so the
    relationship is not linear. Reported, not corrected for.
    """
    whole = int(n)
    frac = round(n - whole, 3)
    return whole, frac


def summarise(rows):
    out = {}
    for cond in sorted({r["pushes"] for r in rows}):
        v = [r for r in rows if r["pushes"] == cond]
        sc = [r["scale"] for r in v if r.get("scale") is not None]
        inl = [r["inliers"] for r in v if r.get("inliers") is not None]
        out[cond] = {
            "n": len(v), "fitted": len(sc),
            # rounded: statistics.median([0.8, 0.9]) is 0.8500000000000001,
            # which fails an exact comparison and reads badly in a table
            "scale_median": round(statistics.median(sc), 3) if sc else None,
            "scale_range": (min(sc), max(sc)) if sc else None,
            "inliers_median": round(statistics.median(inl), 1) if inl else None,
        }
    return out


def run(repeats, mag, sec, chain_name, conditions):
    import analog_replay as ar
    import compass
    import chain as chain_mod
    import reset_env
    import slow_traverse as st
    import walk_steps as ws

    ch = chain_mod.Chain.load(os.path.join("chains", chain_name),
                              log=lambda *a: None)
    rows = []
    order = [c for _ in range(repeats) for c in conditions]   # INTERLEAVED
    with open(OUT, "a") as fh:
        for i, n in enumerate(order, start=1):
            whole, frac = plan_pushes(n)
            print(f"\n[{i}/{len(order)}] {n} pushes")
            reset_env.reset_environment(log=lambda *a: None,
                                        progress_file="progress_testing.json")
            time.sleep(1.5)
            st.turn_to(ROUTE_HEADING, ws.read_heading, compass.fast_capture,
                       log=lambda *a: None)
            for p in range(whole):
                ar.send(["left_x 0", f"left_y {ar.to_axis(-abs(mag))}",
                         "right_x 0", "right_y 0"])
                time.sleep(sec)
                ar.send(["left_x 0", "left_y 0"])
                time.sleep(0.35)
            if frac > 0:
                ar.send(["left_x 0", f"left_y {ar.to_axis(-abs(mag))}",
                         "right_x 0", "right_y 0"])
                time.sleep(sec * frac)
                ar.send(["left_x 0", "left_y 0"])
                time.sleep(0.35)
            st.turn_to(DOOR_HEADING, ws.read_heading, compass.fast_capture,
                       log=lambda *a: None)
            time.sleep(0.4)
            img = compass.fast_capture()
            fix = ch.locate(img, DOOR_K, window=6) if img is not None else None
            # KEEP A FRAME (CLAUDE.md 10.15). A number at the door stop is not
            # adjudicable without the picture it came from, and the person
            # judging this is watching the stream, not the terminal.
            os.makedirs(FRAMES, exist_ok=True)
            shot = os.path.join(FRAMES, f"n{str(n).replace('.','_')}_t{i:02d}.jpg")
            if img is not None:
                img.save(shot, quality=85)
            row = {"trial": i, "pushes": n, "frame": shot,
                   "inliers": None if fix is None else fix.inliers,
                   "k": None if fix is None else fix.k,
                   "scale": None if fix is None else round(float(fix.scale), 3),
                   "dx": None if fix is None else round(float(fix.dx), 1),
                   "heading": ws.read_heading()}
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            print(f"    at the door stop: inliers {row['inliers']}  "
                  f"scale {row['scale']}  k {row['k']}  -> {shot}")
    print("\nSCALE AT THE DOOR STOP. Below 1.0 the character is SHORT of the "
          "reference.")
    for cond, s in summarise(rows).items():
        print(f"  {cond:4} pushes  n={s['n']}  fitted {s['fitted']}  "
              f"scale median {s['scale_median']}  range {s['scale_range']}  "
              f"inliers median {s['inliers_median']}")
    return rows


def selftest():
    assert harness_running(lambda p: "1") is True
    assert harness_running(lambda p: "") is False
    seen = []
    harness_running(lambda p: seen.append(p) or "")
    assert seen == ["overnight/chain_trials.py"], seen
    assert plan_pushes(7) == (7, 0.0)
    assert plan_pushes(6.5) == (6, 0.5)
    assert plan_pushes(6) == (6, 0.0)
    r = [{"pushes": 6, "scale": 0.8, "inliers": 30},
         {"pushes": 6, "scale": 0.9, "inliers": 40},
         {"pushes": 7, "scale": 1.0, "inliers": 60},
         {"pushes": 7, "scale": None, "inliers": None}]
    s = summarise(r)
    assert s[6]["scale_median"] == 0.85 and s[6]["n"] == 2
    assert s[7]["n"] == 2 and s[7]["fitted"] == 1, s[7]
    assert s[7]["scale_median"] == 1.0
    print("selftest OK: the guard both ways, the half push, and a condition "
          "where only some trials fitted")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--mag", type=float, default=0.45)
    ap.add_argument("--sec", type=float, default=0.40)
    ap.add_argument("--chain", default="route_user_1853")
    ap.add_argument("--conditions", default="6,6.5,7")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); raise SystemExit(0)
    if harness_running():
        raise SystemExit("REFUSING: chain_trials.py is running.")
    run(a.repeats, a.mag, a.sec, a.chain,
        [float(c) if "." in c else int(c) for c in a.conditions.split(",")])
