"""Reset, walk the route as world-space steps, then close on the table.

STAGES
------
1. RESET to the office spawn. Reproducible to about a twentieth of a degree
   (86.86, 86.86, 86.91 over three consecutive resets), which is what makes any
   two attempts comparable at all.

2. WALK the route as short straight steps in WORLD SPACE — face a bearing, walk
   forward, never both at once. See walk_steps for why that shape.

3. CLOSE the remaining distance, checking after every small move whether the
   BASEBALL CARDS prompt is on screen.

SUCCESS IS table_prompt.at_table, NOT "a prompt is visible". Standing in front
of Wanda Fuller puts "Wanda Fuller [] Talk" in the same screen region and scores
0.375 on the old brightness detector, against a 0.10 threshold. Six consecutive
"successes" of that kind would have meant nothing.

BOX/SQUARE IS NEVER PRESSED. It starts a match and spends $50 of in-game money.
Arriving at the prompt is the goal; pressing it is not.
"""

import os
import time

import analog_replay as ar
import compass
import inject_reset
import table_prompt as tp
import walk_steps

CLOSE_STEPS = 10
CLOSE_MAG = 0.45
CLOSE_SEC = 0.18


def close_in(log=print):
    """Small moves around the arrival point, checking for the table prompt."""
    img = compass.fast_capture()
    best = tp.score(img)
    if tp.at_table(img):
        log(f"    already at the table (score {best:.3f})")
        return True, best
    moves = [(0.0, -CLOSE_MAG, "forward"),
             (-CLOSE_MAG * 0.7, -CLOSE_MAG * 0.7, "forward-left"),
             (CLOSE_MAG * 0.7, -CLOSE_MAG * 0.7, "forward-right"),
             (-CLOSE_MAG, 0.0, "left")]
    for i in range(CLOSE_STEPS):
        lx, ly, what = moves[i % len(moves)]
        ar.send([f"left_x {ar.to_axis(lx)}", f"left_y {ar.to_axis(ly)}",
                 "right_x 0", "right_y 0"])
        time.sleep(CLOSE_SEC)
        ar.send(["left_x 0", "left_y 0"])
        time.sleep(0.25)
        shot = compass.fast_capture()
        s = tp.score(shot)
        best = max(best, s)
        here = tp.at_table(shot)
        log(f"    close {i + 1:2}: {what:13} table score {s:+.3f}"
            f"{'  <- AT THE TABLE' if here else ''}")
        if here:
            return True, s
    return False, best


def attempt(dur_scale=walk_steps.DEFAULT_DUR_SCALE, log=print, capture_dir=None):
    inject_reset.reset(log=lambda m: log("    " + m.strip()))
    time.sleep(1.0)
    hazards = walk_steps.run(dur_scale=dur_scale, capture_dir=capture_dir,
                             log=lambda m: None)
    img = compass.fast_capture()
    log(f"    route done: heading {compass.read_bearing(img)}, "
        f"table score {tp.score(img):+.3f}, hazards {hazards or 'none'}")
    ok, best = close_in(log=log)
    ar.clear()
    return ok, best, hazards


def main(n=1, dur_scale=walk_steps.DEFAULT_DUR_SCALE, log=print):
    wins = streak = best_streak = 0
    for i in range(1, n + 1):
        log(f"\n  === attempt {i}/{n} ===")
        try:
            ok, score, hz = attempt(dur_scale=dur_scale, log=log)
        except Exception as exc:
            log(f"    FAILED: {exc}")
            ok, score, hz = False, 0.0, None
        wins += ok
        streak = streak + 1 if ok else 0
        best_streak = max(best_streak, streak)
        log(f"  attempt {i}: {'REACHED' if ok else 'missed'} "
            f"(best score {score:+.3f}) — streak {streak}")
    log(f"\n  {wins}/{n} reached the table; longest streak {best_streak}")
    return wins, best_streak


if __name__ == "__main__":
    import sys
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
