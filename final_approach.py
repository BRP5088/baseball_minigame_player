"""Close the last step to the Baseball Cards table, by looking rather than guessing.

WHY NOT A FIXED NUDGE
---------------------
The replay ends near the table but a step short of interaction range, and how
short varies with where the replay happened to end. A hardcoded "strafe 0.4s,
step forward 0.4s" worked once and is luck the next time — the first attempt
at tuning it by hand overshot into a neighbouring NPC and had to be walked
back three times.

So: move a little, look for the prompt, stop the moment it appears.

DETECTING THE PROMPT
--------------------
"Baseball Cards / Play ($50)" renders as bright UI text mid-frame. Measured
over real frames from 2026-08-27:

    with the prompt      0.2534
    without it           0.0000, 0.0038, 0.0155, 0.0256

PROMPT_MIN sits at 0.10 — an order of magnitude above every negative and well
under the positive.

NOTHING HERE PRESSES THE PROMPT. Arriving is free; playing costs $50, and the
goal is to arrive.
"""

import time

import numpy as np

import analog_replay as ar

PROMPT_BOX = (0.38, 0.60, 0.68, 0.68)   # x0, y0, x1, y1 as frame fractions
PROMPT_LEVEL = 225                      # brightness that counts as UI text
PROMPT_MIN = 0.10                       # measured gap: 0.0256 vs 0.2534

STEP_SEC = 0.18
STEP_MAG = 0.42
MAX_STEPS = 14


def prompt_score(img):
    """Fraction of the prompt region that is bright UI text."""
    g = img.convert("L")
    w, h = g.size
    a = np.asarray(g.crop((int(w * PROMPT_BOX[0]), int(h * PROMPT_BOX[1]),
                           int(w * PROMPT_BOX[2]), int(h * PROMPT_BOX[3]))),
                   dtype=float)
    return float((a > PROMPT_LEVEL).mean())


def at_prompt(img):
    return prompt_score(img) >= PROMPT_MIN


def _move(lx, ly, secs):
    ar.send([f"left_x {ar.to_axis(lx)}", f"left_y {ar.to_axis(ly)}",
             "right_x 0", "right_y 0"])
    time.sleep(secs)
    ar.send(["left_x 0", "left_y 0"])
    time.sleep(0.30)


def approach(capture, log=print):
    """Search for the prompt with small moves. True if found.

    Tries forward first, then forward-left, then left — the directions the
    table sat in on the confirmed run — and checks after every single step
    rather than committing to a sequence.
    """
    img = capture()
    if at_prompt(img):
        log(f"  already at the prompt (score {prompt_score(img):.3f})")
        return True

    # (lx, ly, description) — ly negative is forward, lx negative is left
    moves = [(0.0, -STEP_MAG, "forward"),
             (-STEP_MAG * 0.7, -STEP_MAG * 0.7, "forward-left"),
             (-STEP_MAG, 0.0, "left")]

    for i in range(MAX_STEPS):
        lx, ly, what = moves[i % len(moves)]
        _move(lx, ly, STEP_SEC)
        img = capture()
        s = prompt_score(img)
        log(f"    step {i + 1}: {what:12} prompt score {s:.3f}")
        if s >= PROMPT_MIN:
            log(f"  AT THE TABLE — prompt visible (score {s:.3f})")
            return True
    log("  prompt not found within the step budget")
    return False
