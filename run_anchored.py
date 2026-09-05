"""Reset, walk to the JUKEBOX, verify it, then run the short leg to the table.

WHY ANCHORED
------------
Twenty-five seconds of open-loop walking cannot be made reliable: heading is
servoed exactly against the compass, but distance is not measured at all, so
error accumulates with nothing to correct it and the identical route finishes in
different rooms.

The jukebox fixes the important half of that. It does not move — confirmed by
the person who plays this, and by measurement: it is the one landmark whose
match score rises to 0.70-0.85 in a specific place and sits near 0.51 elsewhere.
So the run can be split at it:

    reset -> walk the route to roughly the jukebox   (open loop, forgiving)
    centre on the jukebox until it is actually seen  (CLOSED LOOP, verified)
    run the last 4.07 seconds to the table           (open loop, but SHORT)

Only the final leg has to be accurate, and 4 seconds of drift is a different
proposition from 25. Anything that goes wrong before the anchor is corrected AT
the anchor rather than carried into the table approach.

Wanda and the compass markers were both tried as anchors and both failed —
she was thought to move (the player says she does not, and the truth is the
route simply stops where she stands), and the markers ride the camera. The
jukebox is the first landmark that measurement supports.
"""

import json
import os
import time

import analog_replay as ar
import compass
import jukebox
import table_prompt as tp
import walk_steps as ws

JB_DIR = "test_fixtures/jukebox"
JB_SEEN = 0.64             # measured: 0.70-0.85 at the jukebox, ~0.51 elsewhere
JB_CENTRED = 0.10          # fraction of frame width
ANCHOR_T = 53.27           # when the jukebox peaks in recording 3
FOV = 70.0


def walk_to_anchor(dur_scale=1.15, log=print):
    steps = [s for s in json.load(open("route3_steps.json")) if s["t0"] < ANCHOR_T]
    log(f"    {len(steps)} steps to the anchor")
    json.dump(steps, open("/tmp/_head.json", "w"))
    return ws.run(steps_path="/tmp/_head.json", dur_scale=dur_scale,
                  final_cam=None, log=lambda m: None)


def find_and_centre(tries=10, log=print):
    """Turn until the jukebox is seen, then centre it. True if verified."""
    best = -2.0
    for i in range(tries):
        img = compass.fast_capture()
        score, x, _ = jukebox.find(img, JB_DIR)
        best = max(best, score)
        if score >= JB_SEEN:
            if abs(x - 0.5) <= JB_CENTRED:
                log(f"      jukebox verified: score {score:.3f}, centred x={x:.2f}")
                return True
            ws.turn_to((compass.read_bearing(img) + (x - 0.5) * FOV) % 360,
                       log=lambda m: None)
            continue
        h = compass.read_bearing(img)
        if h is None:
            return False
        ws.turn_to((h + 40) % 360, log=lambda m: None)
    log(f"      jukebox not found (best {best:.3f} < {JB_SEEN})")
    return False


def run_tail(dur_scale=1.15, log=print):
    tail = json.load(open("route3_tail.json"))
    for i, s in enumerate(tail, 1):
        ws.turn_to(s["bearing"], log=lambda m: None)
        moved = ws.walk_forward(s["speed"], s["dur"] * dur_scale)
        if moved < ws.STUCK_CHANGE:
            ws.unstick(s["speed"], s["dur"] * dur_scale, log=lambda m: None)
            ws.turn_to(s["bearing"], log=lambda m: None)
        img = compass.fast_capture()
        here = tp.at_table(img)
        log(f"      tail {i}/{len(tail)} bearing {s['bearing']:6.1f} moved {moved:5.1f} "
            f"table {tp.score(img):+.3f}{'  *** AT THE TABLE ***' if here else ''}")
        if here:
            return True, img
    img = compass.fast_capture()
    return tp.at_table(img), img


def attempt(log=print):
    import inject_reset
    inject_reset.reset(log=lambda m: None)
    time.sleep(1.0)
    walk_to_anchor(log=log)
    anchored = find_and_centre(log=log)
    ok, img = run_tail(log=log)
    ar.clear()
    return ok, anchored


if __name__ == "__main__":
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    ok, anchored = attempt()
    print(f"\n  anchored on jukebox: {anchored}   reached table: {ok}")
