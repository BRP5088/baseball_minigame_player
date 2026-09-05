"""Replay a recording's raw controller input at its original rate — a macro.

WHY TRY THIS AT ALL
-------------------
Every route replay so far has RECONSTRUCTED the walk: decode a heading per
frame, turn to an absolute bearing, walk forward, repeat. That is robust to
starting in the wrong place but it is not what the player did — they walked and
turned at once, continuously, and stopping to turn loses the ground covered
during every turn.

A macro does the opposite: send exactly the recorded stick values at exactly the
recorded times. If the game is deterministic from a fixed save, this should
reproduce the run outright. The third recording makes this a fair test for the
first time, because it starts at the reset spawn — earlier recordings did not,
so replaying them from a reset was meaningless.

TIMING IS ABSOLUTE, NOT INCREMENTAL. Sleeping for the gap between samples
accumulates every scheduling overshoot, so the replay drifts slowly later. Each
sample is instead scheduled against a single start time.

The FIFO is held open for the whole replay. Reopening it per sample caused
BrokenPipeError at 50Hz and, before that, a replay that visibly under-travelled.
"""

import json
import os
import time

import analog_replay as ar

BOX = 1 << 2               # never sent: it spends $50 at the table


def replay(demo_dir, t0=0.0, t1=None, rate_scale=1.0, log=print):
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    win = [s for s in samples if s["t"] >= t0 and (t1 is None or s["t"] <= t1)]
    if not win:
        raise RuntimeError("no samples in that window")
    log(f"  replaying {len(win)} samples over "
        f"{(win[-1]['t'] - win[0]['t']) * rate_scale:.1f}s")

    began = time.time()
    start_t = win[0]["t"]
    sent = late = 0
    for s in win:
        a = s["axes"]
        ar.send([f"left_x {ar.to_axis(a.get('lx', 0.0))}",
                 f"left_y {ar.to_axis(a.get('ly', 0.0))}",
                 f"right_x {ar.to_axis(a.get('rx', 0.0))}",
                 f"right_y {ar.to_axis(a.get('ry', 0.0))}"])
        sent += 1
        target = began + (s["t"] - start_t) * rate_scale
        gap = target - time.time()
        if gap > 0:
            time.sleep(gap)
        else:
            late += 1
    ar.clear()
    elapsed = time.time() - began
    log(f"  sent {sent} samples in {elapsed:.1f}s, {late} arrived late "
        f"({100 * late / sent:.0f}%)")
    return elapsed
