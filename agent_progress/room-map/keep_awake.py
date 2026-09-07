"""Nudge the camera often enough that the PS5 does not enter rest mode.

WHY THIS EXISTS AGAIN. A previous keep_awake module was deleted 2026-09-05, for
a good reason and a bad one. The good reason: a RUN drives the console, so it
cannot sleep during one, and the module had never actually launched. The bad
one: that argument only covers time INSIDE a run. On 2026-09-06 the console sat
idle between experiments and put "rest mode in 6 minutes" on screen -- exactly
the gap the deletion note named and dismissed.

TWO FAILURES OF THE OLD MODULE, BOTH AVOIDED HERE:

  ITS NUDGE DID NOTHING. NUDGE_MAG sat exactly ON turn_curve.DEAD_BELOW rather
  than above it, so the ~7 degree turn it advertised was 0.41 degrees. This one
  uses 16000 of 32767 (about 0.49) and MEASURES the frame delta across every
  nudge, so a nudge that moves nothing is reported instead of assumed.

  IT COULD CORRUPT A RUN. Every 240s it sent `clear`, which zeroes the stick --
  and slow_traverse holds the stick untimed and sleeps out the full duration, so
  a leg would silently walk short with no log to distinguish that from a routing
  failure. This refuses to start if anything under overnight/ is running, and
  re-checks before every nudge rather than trusting a hand-kept list of names,
  which is what rotted last time.

A CAMERA TURN, NOT A WALK. Section 8(g): turning is the one input measured never
to move the character, and it is symmetric here -- equal and opposite -- so it
cannot accumulate heading either.
"""
import os
import subprocess
import sys
import time

# console_lock lives at the PROJECT ROOT; this script does not. Without the
# path insert the import raises and keep_awake dies at startup -- which it
# did, silently, leaving the console unattended while the log said nothing
# until someone read it.
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
import console_lock as _cl

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import analog_replay as ar
import compass

PERIOD = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
HOLD_MS = 180
MAG = 16000            # ~0.49 of full, comfortably above DEAD_BELOW's 0.35
MIN_DELTA = 0.5        # below this the nudge did not reach the console


def a_run_is_active():
    """Is anything under overnight/ driving the console right now?

    Checked by looking at what is RUNNING, not at a list of script names. The
    deleted module matched on names and missed every A/B harness, because
    run_trial spawns trials as `<venv>/python <abspath> --one-trial <arm>`.
    """
    try:
        out = subprocess.run(["ps", "-Ao", "command"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return True          # cannot tell -> assume yes, and stay out of the way
    me = os.path.basename(__file__)
    return any("overnight/" in line and me not in line
               for line in out.splitlines())


def frame():
    return np.asarray(compass.fast_capture().convert("L"), dtype=float)


def main():
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit("refusing to drive the console under BASEBALL_TEST_RUN")
    print(f"keep-awake: nudging every {PERIOD:.0f}s", flush=True)
    ar.open_stream()
    while True:
        if a_run_is_active():
            print(f"  {time.strftime('%H:%M:%S')} a run is active — standing down",
                  flush=True)
        else:
            try:
                a = frame()
                # NEVER NUDGE WHILE A RUN IS DRIVING. `clear` below zeroes the
                # stick, and slow_traverse holds it untimed and sleeps out the
                # whole push -- so a nudge landing mid-leg ends it early, the
                # leg walks short, and no log tells that apart from a routing
                # failure. Checked every cycle rather than once at startup,
                # because a run usually STARTS after this does.
                busy = _cl.holder()
                if busy and busy.get("pid") != os.getpid():
                    print(f"  {time.strftime('%H:%M:%S')} standing down — "
                          f"{busy.get('name')!r} is driving", flush=True)
                    time.sleep(PERIOD)
                    continue
                ar.send([f"right_x {MAG} {HOLD_MS}"]); time.sleep(0.9)
                ar.send([f"right_x -{MAG} {HOLD_MS}"]); time.sleep(0.9)
                ar.send(["clear"])
                b = frame()
                h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
                d = float(np.abs(a[:h, :w] - b[:h, :w]).mean())
                flag = "" if d >= MIN_DELTA else "   <-- NUDGE REACHED NOTHING"
                print(f"  {time.strftime('%H:%M:%S')} nudged, delta {d:5.2f}{flag}",
                      flush=True)
            except Exception as e:
                print(f"  {time.strftime('%H:%M:%S')} nudge failed: "
                      f"{type(e).__name__}: {e}", flush=True)
        time.sleep(PERIOD)


main()
