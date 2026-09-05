"""Capture DualSense button presses and stick positions, timestamped.

WHY
---
Every route so far was INFERRED from what the camera did — heading decoded per
frame, movement guessed from picture change. That is downstream of the thing
that actually matters. The controller carries the intent directly: which
stick, how far, for how long. Replaying real inputs beats reconstructing them.

    python3 record_input.py identify      # press buttons, see their names
    python3 record_input.py 90 walk       # record 90s of input + frames

MAPPING PLAUSIBLE, NOT CONFIRMED PRESS-BY-PRESS (2026-08-27).
Every control was pressed and each produced exactly one distinct label, in an
order consistent with the physical layout — but the person pressing did not
check each label against the button under their thumb. So the map is
self-consistent and almost certainly right, and it is NOT verified.

That distinction is cheap to ignore and expensive to be wrong about, so: this
recording is READ-ONLY and no controller input is ever replayed, which keeps a
mislabel confined to analysis. If controller input is ever played back, confirm
`square` first — it is the button that spends $50 at the Baseball Cards prompt.

STICK CONVENTIONS, measured in that same pass:
    ly = -1.0 fully FORWARD, +1.0 fully back
    lx = -1.0 fully left,    +1.0 fully right
    rx/ry likewise for the camera stick
    l2/r2 rest near -1.0 and go to +1.0 fully pressed

The sticks are ANALOG and were used as such: the walk showed lx/ly at
intermediate values, not slammed to the stops. Everything this project has sent
so far has been full-tilt keyboard presses, so partial-tilt movement is a real
difference between the recording and any replay of it.
"""

import json
import os
import sys
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-input")

POLL_HZ = 60
STICK_DEADZONE = 0.15

# SDL's usual DualSense layout — UNVERIFIED on this controller, see `identify`.
BUTTONS = {
    0: "cross", 1: "circle", 2: "square", 3: "triangle",
    4: "share", 5: "ps", 6: "options", 7: "l3", 8: "r3",
    9: "l1", 10: "r1", 11: "dpad_up", 12: "dpad_down",
    13: "dpad_left", 14: "dpad_right", 15: "touchpad", 16: "mic",
}
AXES = {0: "lx", 1: "ly", 2: "rx", 3: "ry", 4: "l2", 5: "r2"}


def _open():
    import pygame
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        raise RuntimeError("no controller found — is the DualSense connected?")
    j = pygame.joystick.Joystick(0)
    return pygame, j


def identify():
    """Print what is pressed, live, so the mapping can be checked by hand."""
    pygame, j = _open()
    print(f"  {j.get_name()}: {j.get_numbuttons()} buttons, {j.get_numaxes()} axes")
    print("  press buttons / move sticks. ctrl-c to stop.\n")
    last = None
    while True:
        pygame.event.pump()
        now = []
        for b in range(j.get_numbuttons()):
            if j.get_button(b):
                now.append(f"{b}:{BUTTONS.get(b, '?')}")
        for a in range(j.get_numaxes()):
            v = j.get_axis(a)
            if a in (4, 5):          # triggers rest at -1
                if v > -0.8:
                    now.append(f"{a}:{AXES.get(a,'?')}={v:+.2f}")
            elif abs(v) > STICK_DEADZONE:
                now.append(f"{a}:{AXES.get(a,'?')}={v:+.2f}")
        s = " ".join(now)
        if s != last:
            print(f"  {s or '(nothing)'}")
            last = s
        time.sleep(1.0 / POLL_HZ)


def record(seconds, out_dir, log=print):
    """Record controller input here, frames in a CHILD PROCESS, one clock.

    The child signals readiness after its imports so both clocks start
    together; subprocess startup is otherwise ~1s of unrecorded drift.
    """
    import subprocess
    pygame, j = _open()
    os.makedirs(out_dir, exist_ok=True)
    ready = os.path.join(out_dir, "ready.txt")
    if os.path.exists(ready):
        os.remove(ready)

    child = subprocess.Popen(
        [sys.executable, "frame_worker.py", out_dir, str(seconds)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(200):                       # up to 20s for imports
        if os.path.exists(ready):
            break
        time.sleep(0.1)
    else:
        child.kill()
        raise RuntimeError("frame worker never became ready")

    samples = []
    t0 = time.time()
    while True:
        now = time.time() - t0
        if now >= seconds:
            break
        pygame.event.pump()
        samples.append({
            "t": round(now, 3),
            "buttons": [BUTTONS.get(b, str(b)) for b in range(j.get_numbuttons())
                        if j.get_button(b)],
            "axes": {AXES.get(a, str(a)): round(j.get_axis(a), 3)
                     for a in range(j.get_numaxes())},
        })
        time.sleep(1.0 / POLL_HZ)

    child.wait(timeout=30)
    json.dump(samples, open(os.path.join(out_dir, "input.json"), "w"))
    frames = len([f for f in os.listdir(out_dir) if f.startswith("f_")])
    log(f"  {len(samples)} input samples, {frames} frames")
    return samples


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "identify":
        try:
            identify()
        except KeyboardInterrupt:
            print("\n  stopped")
    else:
        secs = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
        name = sys.argv[2] if len(sys.argv) > 2 else "input"
        out = os.path.join("demos", f"{name}_{time.strftime('%Y%m%d_%H%M%S')}")
        print(f"  recording {secs:.0f}s of INPUT + FRAMES -> {out}", flush=True)
        for i in (3, 2, 1):
            print(f"    {i}...", flush=True)
            time.sleep(1)
        print("  GO", flush=True)
        record(secs, out)
        print(f"  done -> {out}", flush=True)
