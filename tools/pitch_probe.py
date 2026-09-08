"""How far does ONE pitch press move the picture, and which way? (patch57)

THE TWO NUMBERS chain_walk.PITCH_STEP_PX and chain_walk.PITCH_DOWN_DY_SIGN
need, and the only reason the pitch correction ships in REPORT mode. Both ship
None; while either is None the correction presses nothing.

WHY THEY CANNOT BE DERIVED. STAIRS_APPROACH.md: "PITCH IS UNCONTROLLED IN
PRODUCTION ... Nobody currently knows how to command a specific pitch", and
"THREE NUMBERS ABOUT PITCH CONTRADICT EACH OTHER". The project's three readings
of how many PITCH_STEP_SEC presses span the whole vertical travel are 8
(input_controller.py:993), 20 (input_controller.py:1009-1014) and 36
(STAIRS_APPROACH.md) -- 30, 54 or 135 px of dy per press at 15.5 px/deg. And no
site anywhere has ever recorded a live dy against a pitch press, in pointed
contrast to pose.py's measured strafe/forward/back dx,dy table for the LATERAL
axis. This is that table, for this axis.

THE EXPERIMENT, and it is pose.py's own:

    capture BEFORE -> press look_down once -> capture AFTER
    -> pose.offset(before, after) -> (dx, dy)

dy is px of vertical shift per press and its sign IS the sign, read straight
off. Repeated, both directions, character stationary -- NOTHING WALKS, the
left stick is never touched, and the only thing that moves is the camera.

RUN IT ANYWHERE THE VIEW HAS TEXTURE and the camera is NOT parked against a
stop: a stop clamps the press and reads as zero, which is indistinguishable
from a dead stream, so both are checked for before any number is believed
(§10.6: a run where everything degrades at once is the environment).

    .venv/bin/python -B tools/pitch_probe.py [--n 8]

Paste the two lines it prints into chain_walk.py. The dead-band moves to the
measured step on its own (pitch_dead_band), so the D >= S condition that stops
a bang-bang rule hunting holds at whatever the step turns out to be.
"""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The probe SENDS INPUT, so it may never run inside the offline suite.
if os.environ.get("BASEBALL_TEST_RUN"):
    sys.exit("pitch_probe sends stick input; BASEBALL_TEST_RUN is set. Refusing.")

import console_lock          # noqa: E402
import game_capture          # noqa: E402
import input_controller as ic  # noqa: E402
import pose                  # noqa: E402

# A press that moves the picture less than this is indistinguishable from a
# stop, a frozen stream, or the fit failing -- pose.py measured two stationary
# frames at exactly 0.0 px, so anything at all is movement, and this is a
# generous margin over the scene's own animation.
QUIET_PX = 3.0


def _shift(a, b):
    """(dx, dy) between two frames, or None when it cannot be measured."""
    got = pose.offset(a, b)
    return None if got is None else (float(got[0]), float(got[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8, help="presses per direction")
    args = ap.parse_args()

    with console_lock.held("pitch_probe"):
        grab = game_capture.grab

        # THE NULL CONTROL FIRST. Two captures with no press between them: if
        # this is not quiet, the scene is animating or the stream is stalled
        # and every number below would be that instead. A stalled stream reads
        # 0.0 and would look like a perfect control, so the frames must also
        # not be identical -- standing still measures 0.9-6.4 of frame delta,
        # and byte-identical frames are a dead picture (STAIRS_APPROACH.md).
        a = grab()
        time.sleep(0.4)
        b = grab()
        null = _shift(a, b)
        if null is None:
            sys.exit("the null control could not be measured: no texture here")
        if abs(null[1]) > QUIET_PX:
            sys.exit(f"the null control moved {null[1]:+.1f} px vertically; "
                     "something else is turning the camera")
        print(f"null control: dy {null[1]:+.2f} px, dx {null[0]:+.2f} px")

        rows = []
        for action in ("look_down", "look_up"):
            for trial in range(args.n):
                before = grab()
                ic.press(action, hold_seconds=ic.PITCH_STEP_SEC,
                         post_delay=0.30)
                after = grab()
                got = _shift(before, after)
                if got is None:
                    print(f"  {action} {trial}: UNMEASURABLE, skipped")
                    continue
                rows.append((action, got[1], got[0]))
                print(f"  {action} {trial}: dy {got[1]:+7.1f} px "
                      f"(dx {got[0]:+6.1f})")
            # Walk the camera back, so the second direction starts where the
            # first did and neither run drifts into a stop.
            other = "look_up" if action == "look_down" else "look_down"
            for _ in range(args.n):
                ic.press(other, hold_seconds=ic.PITCH_STEP_SEC, post_delay=0.20)

    downs = [dy for act, dy, _ in rows if act == "look_down"]
    ups = [dy for act, dy, _ in rows if act == "look_up"]
    if len(downs) < 3 or len(ups) < 3:
        sys.exit("too few measurable presses to conclude anything")

    quiet = [dy for dy in downs + ups if abs(dy) < QUIET_PX]
    if quiet:
        print(f"\nWARNING: {len(quiet)} of {len(downs) + len(ups)} presses "
              "moved almost nothing -- the camera was probably against a stop "
              "for part of this run. Move to a mid pitch and re-run; a stop "
              "reads exactly like a dead stream.")

    md, mu = statistics.median(downs), statistics.median(ups)
    print(f"\nlook_down: median dy {md:+.1f} px  "
          f"[{min(downs):+.1f} .. {max(downs):+.1f}]  n={len(downs)}")
    print(f"look_up:   median dy {mu:+.1f} px  "
          f"[{min(ups):+.1f} .. {max(ups):+.1f}]  n={len(ups)}")

    if (md > 0) == (mu > 0):
        sys.exit("\nthe two directions moved the picture the SAME way. That is "
                 "not a pitch axis; do not set either constant from this run.")

    step = round((abs(md) + abs(mu)) / 2.0, 1)
    sign = 1 if md > 0 else -1
    print("\nPaste into chain_walk.py:\n")
    print(f"PITCH_STEP_PX = {step}")
    print(f"PITCH_DOWN_DY_SIGN = {sign}")
    print(f"\n(the correction's `hypothesis` field predicts -1; this run "
          f"measured {sign}, so they "
          + ("AGREE" if sign == -1 else "DISAGREE -- the optics argument was "
             "backwards, and the shipped rule would have DOUBLED the error")
          + ".)")
    print(f"the dead-band becomes max(PITCH_TOL_MIN_PX, {step}) on its own.")


if __name__ == "__main__":
    main()
