"""Test ONLY the aiming: can the camera put the reticle on a landmark?

    python3 aim_test.py dealer_tight    # or jukebox, office_door, poster
    python3 aim_test.py dealer_tight --fov

Use dealer_tight, not dealer, for AIMING. The wide "dealer" crop contains the
table and the window, so centring it centres the scene rather than her.
    python3 aim_test.py dealer --fov    # also re-measure the field of view

Point the character at a landmark from any angle and run it. Testing this in
isolation takes seconds; testing it inside the full route takes ninety, and the
answer is buried under everything else that can go wrong on the way.

WHAT IT SEPARATES
-----------------
Three things can put the reticle in the wrong place and they need different
fixes, so the report keeps them apart:

  predicted vs turned   Did the camera actually turn as far as it was told?
                        That is the turn controller, not the aiming maths.
  turned vs needed      Was the prediction right? That is the FOV and the
                        trigonometry.
  residual offset       Where the landmark ended up. The number that matters.

A large "turned" error with a small prediction error means the stick, not the
sums. The reverse means the geometry.
"""

import sys
import time

import aim
import analog_replay as ar
import pitch_control
import compass
import jukebox
import walk_steps as ws

TRIES = 6
TOL = 0.007


def look(template_dir, settle=0.35):
    """Landmark position and heading, retrying the compass.

    The compass abstains on the odd frame — motion blur, or the strip crossing
    something bright. Treating that as "lost the landmark" abandoned an aim that
    was going perfectly well, and reported it as a loss at score 0.718, which is
    a strong match. The two failures are unrelated and need separating: a
    missing bearing is worth retrying, a missing landmark is not.
    """
    time.sleep(settle)
    # MEDIAN OF THREE. A marginal match relocates between frames, and acting on
    # a single reading steers at whatever it jumped to. Seen directly: a 13.6
    # degree turn was followed by the reported position moving 0.325 of frame
    # when the geometry says 0.098 — the camera did not do that, the match did.
    obs = []
    for _ in range(3):
        img = compass.fast_capture()
        sc, xx, _, _, _ = jukebox.find_best_xy(img, template_dir)
        obs.append((sc, xx))
        time.sleep(0.05)
    obs.sort(key=lambda o: o[1])
    score, x = obs[1]
    spread = obs[-1][1] - obs[0][1]
    if spread > 0.06:
        score = min(score, 0.29)      # unstable: treat as not seen
    img = compass.fast_capture()
    h = compass.read_bearing(img)
    for _ in range(8):
        if h is not None:
            break
        time.sleep(0.12)
        h = compass.read_bearing(compass.fast_capture())
    return score, x, h


def run(name, tries=TRIES, log=print):
    # a registered set name (covering several distances) or a directory
    d = name if name in jukebox.SETS else f"test_fixtures/{name}"
    score, x, h = look(d)
    if h is None:
        log("  (no compass here — aiming works without it)")
    log(f"  landmark '{name}': score {score:.3f}, at x={x:.3f}, "
        f"heading {'--' if h is None else f'{h:.1f}'}")
    if score < 0.35:
        log(f"  not confidently visible ({score:.3f}) — searching for it")
        if not pitch_control.search_for(d, ws, log=log):
            return None
        score, x, h = look(d)
        if h is None:
            return None
        log(f"  acquired: score {score:.3f}, at x={x:.3f}, heading {h:.1f}")

    obs = [(h, x)]
    for i in range(tries):
        score, x, h = look(d)
        if score < 0.30:
            log(f"  step {i + 1}: match unstable or lost (score {score:.3f}); "
                "not steering on it")
            break
        if h is None:
            log(f"  step {i + 1}: no compass reading; skipping this step")
            continue
        offset = x - 0.5 - pitch_control.AIM_BIAS_X
        if abs(offset) <= TOL:
            log(f"  step {i + 1}: CENTRED, offset {offset:+.3f} "
                f"({aim.angle_for_offset(offset):+.1f} deg)")
            break
        want = aim.angle_for_offset(offset)
        # RELATIVE turn: no compass needed, and the template verifies the result
        aim.turn_by(want, ar.send, time.sleep)
        score2, x2, h2 = look(d)
        obs.append((h2, x2))
        turned = None if (h2 is None or h is None) else (h2 - h + 540) % 360 - 180
        log(f"  step {i + 1}: offset {offset:+.3f} -> turned {want:+.1f} deg "
            f"(compass says {'--' if turned is None else f'{turned:+.1f}'}), "
            f"now x={x2:.3f} (offset {x2 - 0.5 - pitch_control.AIM_BIAS_X:+.3f})")
        x, h = x2, h2
    # BOTH AXES. Centring only in x leaves the reticle above or below the
    # target, which is what a person watching it sees as "still off" while the
    # numbers report CENTRED.
    dx, dy = pitch_control.centre_both(d, ws, log=log)
    if dx is not None:
        log(f"  final: dx {dx:+.3f} ({aim.angle_for_offset(dx):+.1f} deg), "
            f"dy {'--' if dy is None else f'{dy:+.3f}'}"
            + ("" if dy is None else f" ({aim.pitch_for_offset(dy):+.1f} deg)"))
    ar.clear()
    return obs


if __name__ == "__main__":
    import os
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    name = sys.argv[1] if len(sys.argv) > 1 else "dealer"
    # optional aim bias:  python3 aim_test.py dealer_tight --bias -0.03 -0.04
    if "--bias" in sys.argv:
        i = sys.argv.index("--bias")
        pitch_control.AIM_BIAS_X = float(sys.argv[i + 1])
        pitch_control.AIM_BIAS_Y = float(sys.argv[i + 2])
        print(f"  aim bias: x {pitch_control.AIM_BIAS_X:+.3f} "
              f"y {pitch_control.AIM_BIAS_Y:+.3f}")
    obs = run(name)
    if obs and "--fov" in sys.argv:
        est = aim.measure_fov(obs)
        if est:
            print(f"\n  FOV estimated from this run: {est:.1f} deg "
                  f"(currently using {aim.load_fov():.1f})")
