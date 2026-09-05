"""Find which bit is which, for button injection over the FIFO.

    python3 verify_button_bits.py          identify the D-pad bits

WHY THIS EXISTS
---------------
Buttons and sticks reach the PS5 by DIFFERENT paths. Sticks go through our own
injector (a FIFO chiaki reads); buttons go through chiaki's Qt keyboard
mapping. On 2026-09-01 the keyboard path appeared dead while sticks, video and
heartbeats were all healthy — two different mechanisms, one of which we control
and one of which we do not.

The injector already accepts `buttons <mask>` and writes it straight into
`state->buttons`, so the whole keyboard path can be bypassed. What is missing
is knowing WHICH BIT IS WHICH: the chiaki header defining the enum is not in
the source tree we still have, and an earlier guess of 1<<5 for D-pad-right
produced no visible movement — while the session may not even have been
connected, so it proved nothing either way.

Guessing is not acceptable here. A wrong bit does not fail quietly: it presses
some OTHER button on a live console.

WHY THE PAUSE MENU, AND WHY ONLY THE D-PAD
------------------------------------------
The test needs a surface where a press is (a) visible, so there is an oracle,
and (b) harmless. The pause menu moves a highlight when the D-pad is pressed —
visible — and D-pad presses commit to nothing — harmless.

Face buttons are NOT tested. The pause menu contains "Quit to Main Menu", and a
mis-identified bit landing on it would end the session. Once the D-pad bits are
confirmed the enum's ORDER is confirmed with them, and the face buttons follow
from the same enum without ever having to fire one blind.
"""

import sys
import time

sys.path.insert(0, "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball")

import numpy as np

import analog_replay as ar
import compass
import game_capture
import input_controller as ic
import pause_menu as pm

# The layout chiaki-ng is expected to use. Treated as a HYPOTHESIS to test,
# not as fact — that is the entire point of this script.
CANDIDATES = {
    "dpad_left":  1 << 4,
    "dpad_right": 1 << 5,
    "dpad_up":    1 << 6,
    "dpad_down":  1 << 7,
}

# A highlight moving is a small change on a mostly-static menu. Measured
# baseline idle drift on the pause menu is well under 1.0; the walk detector
# next door uses 2.5 for "something moved", and that is a reasonable floor here.
MOVED = 2.5
HOLD = 0.12
SETTLE = 1.2


def _grey():
    return np.asarray(game_capture.grab().convert("L"), dtype=float)


def _press_bits(mask):
    """One press over the FIFO. Always releases, even if interrupted."""
    try:
        ar.send([f"buttons {mask}"])
        time.sleep(HOLD)
    finally:
        ar.send(["buttons 0"])
    time.sleep(SETTLE)


def main():
    img = compass.fast_capture()
    if not pm.is_pause_screen(img):
        print("Opening the pause menu (via the known-good keyboard path) so "
              "there is a visible, harmless surface to test on.")
        for _ in range(3):
            ic.press("toggle_pause")
            time.sleep(2.0)
            if pm.is_pause_screen(compass.fast_capture()):
                break
        else:
            print("Could not open the pause menu — aborting rather than "
                  "pressing buttons into an unknown screen.")
            return 1

    print(f"On the pause menu. Selected: {pm.selected_item(compass.fast_capture())!r}")
    print("Idle baseline first, so a moving highlight can be told from noise.")
    base = _grey()
    time.sleep(SETTLE)
    idle = float(np.abs(_grey() - base).mean())
    print(f"  idle delta over {SETTLE}s: {idle:.2f}")

    results = {}
    for name, mask in CANDIDATES.items():
        before = _grey()
        _press_bits(mask)
        moved = float(np.abs(_grey() - before).mean())
        sel = pm.selected_item(compass.fast_capture())
        results[name] = moved
        verdict = "MOVED" if moved >= MOVED else "no change"
        print(f"  {name:11} bit {mask:3d} -> delta {moved:6.2f}  {verdict}"
              f"   selected now {sel!r}")

    print()
    hits = [n for n, v in results.items() if v >= MOVED]
    if hits:
        print(f"FIFO button injection WORKS — {len(hits)}/{len(CANDIDATES)} "
              f"candidate bits moved the menu: {', '.join(hits)}")
        print("The enum order is confirmed with them, so the face buttons "
              "follow without firing one blind.")
    else:
        print("No candidate bit moved anything. Either the layout differs, or "
              "buttons are not reaching the console by this path at all. Do "
              "NOT switch the input path on this result.")

    ar.clear()
    print("Injection cleared; the real controller has the pad back.")
    print("Leaving the pause menu open — close it yourself, or the next reset "
          "will handle it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
