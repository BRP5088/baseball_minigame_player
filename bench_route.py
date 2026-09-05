"""Run reset+walk repeatedly and report reliability and where the time goes.

Optimising before measuring is how this project lost most of a night: the
compass was assumed to be the bottleneck for hours on the strength of a guess,
and when finally profiled it turned out 8502ms of an 8519ms read was one call
nobody had timed. So: measure first, per phase, over several runs.

NEVER presses Play. The prompt costs $50 a match; arriving at it is free.
"""
import os
import sys
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-bench")

import compass
import input_controller as ic
import landmarks
import reset_env
import reset_walk

D = sys.argv[1]
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
cap = compass.fast_capture

rows = []
for run in range(1, RUNS + 1):
    t0 = time.time()
    phase = {}
    try:
        reset_env.reset_environment(log=lambda *a: None)
    except reset_env.ResetError as exc:
        rows.append((run, "reset-failed", time.time() - t0, {}))
        print(f"  run {run}: RESET FAILED — {exc}", flush=True)
        continue
    phase["reset"] = time.time() - t0

    t1 = time.time()
    walked = "ok"
    try:
        reset_walk.walk_route(log=lambda *a: None, save_dir=None,
                              route=reset_walk.spliced_route())
    except reset_walk.WalkError as exc:
        walked = f"stopped: {str(exc)[:60]}"
    phase["walk"] = time.time() - t1

    t2 = time.time()
    found = landmarks.at_baseball_table(cap()) is True
    if not found:
        found = reset_walk.find_table(cap, log=lambda *a: None)
    phase["search"] = time.time() - t2

    total = time.time() - t0
    rows.append((run, "TABLE" if found else "missed", total, phase))
    cap().save(os.path.join(D, f"bench_run{run}.jpg"), quality=85)
    print(f"  run {run}: {'TABLE' if found else 'missed':7} {total:5.0f}s  "
          f"reset {phase['reset']:.0f} walk {phase['walk']:.0f} "
          f"search {phase['search']:.0f}   [{walked}]", flush=True)

ok = sum(1 for r in rows if r[1] == "TABLE")
print(f"\n  {ok}/{len(rows)} reached the table", flush=True)
if rows:
    good = [r for r in rows if r[1] == "TABLE"]
    if good:
        print(f"  successful runs: {min(r[2] for r in good):.0f}-"
              f"{max(r[2] for r in good):.0f}s "
              f"(mean {sum(r[2] for r in good)/len(good):.0f}s)", flush=True)
    for key in ("reset", "walk", "search"):
        vals = [r[3][key] for r in rows if key in r[3]]
        if vals:
            print(f"    {key:7} mean {sum(vals)/len(vals):5.1f}s", flush=True)
