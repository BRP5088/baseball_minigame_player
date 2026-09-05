"""Step-and-look navigation helper. One command, one contact sheet, maximum info.

WHY
---
Scripted route-replay found nothing in hours; stepping and looking found two
real bugs in twenty minutes. But each look costs a round trip, so the tool
should return as much as possible per call: several steps or several headings
in ONE image, each labelled with its bearing and the frame delta that says
whether the character actually moved.

Frame delta is the movement signal: ~1 means blocked or standing, and a real
walking second reads well above that. Treat a low delta as a QUESTION though —
it was a broken mover, not a wall, the first time it appeared.

    python3 probe.py look [n]              n headings around a full circle
    python3 probe.py walk <bearing> <secs> [steps]
    python3 probe.py reset
    python3 probe.py where                 one frame + bearing, no input
"""
import os
import sys
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-probe")

import numpy as np
from PIL import Image, ImageDraw

import compass
import input_controller as ic

OUT = os.environ.get("PROBE_OUT", ".")
cap = compass.fast_capture
grey = lambda im: np.asarray(im.convert("L"), dtype=float)


def _tile(img, label):
    im = img.crop((60, 60, 1680, 1090)).resize((430, 274))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 180, 20], fill=(0, 0, 0))
    d.text((4, 4), label, fill=(255, 255, 255))
    return im


def _sheet(tiles, name, cols=3):
    if not tiles:
        return
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (430 * min(cols, len(tiles)), 274 * rows))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 430, (i // cols) * 274))
    path = os.path.join(OUT, name)
    sheet.save(path, quality=85)
    print(f"  saved {path}", flush=True)


def look(n=6):
    ic.focus_chiaki_window(force=True); time.sleep(0.4)
    tiles = []
    for k in range(n):
        target = (360.0 / n) * k
        got = compass.turn_to(target, ic.press, cap, log=lambda *a: None)
        time.sleep(0.4)
        tiles.append(_tile(cap(), f"{compass.describe(got)}"))
        print(f"  looked {compass.describe(got)}", flush=True)
    _sheet(tiles, "probe_look.jpg")


def walk(bearing, secs, steps=4):
    ic.focus_chiaki_window(force=True); time.sleep(0.4)
    compass.turn_to(bearing, ic.press, cap, log=lambda *a: None)
    time.sleep(0.4)
    h = compass.read_bearing_stable(cap)
    if h is None:
        print("  bearing unreadable — refusing to walk blind", flush=True)
        return
    print(f"  facing {compass.describe(h)} (wanted {bearing:.0f})", flush=True)
    tiles = []
    tot = 0.0
    for k in range(steps):
        before = grey(cap())
        ic.walk_at(compass.angular_error(h, bearing), secs)
        tot += secs
        time.sleep(0.3)
        img = cap()
        d = float(np.abs(grey(img) - before).mean())
        tiles.append(_tile(img, f"{tot:.1f}s  d={d:.0f}"))
        print(f"    +{tot:.1f}s  delta {d:5.1f}"
              f"{'   (blocked?)' if d < 2.0 else ''}", flush=True)
    _sheet(tiles, "probe_walk.jpg")


def until_blocked(bearing, max_secs=6.0, step=0.7):
    """Walk a bearing until the character jams. Returns seconds actually walked.

    Being pressed against geometry is a REPEATABLE POSITION; a stopwatch is
    not. Replaying a leg by its measured duration left the character short of
    the office door and the whole route diverged from there, while walking
    until it jammed reproduced the position twice running.
    """
    ic.focus_chiaki_window(force=True); time.sleep(0.4)
    compass.turn_to(bearing, ic.press, cap, log=lambda *a: None); time.sleep(0.4)
    h = compass.read_bearing_stable(cap)
    if h is None:
        print("  no heading", flush=True)
        return 0.0
    rel = compass.angular_error(h, bearing)
    done, blocked = 0.0, 0
    while done < max_secs - 0.01:
        before = grey(cap()); ic.walk_at(rel, step); time.sleep(0.3); done += step
        d = float(np.abs(grey(cap()) - before).mean())
        print(f"    +{done:.1f}s delta {d:5.1f}", flush=True)
        blocked = blocked + 1 if d < 3.0 else 0
        if blocked >= 2:
            break
    img = cap()
    img.save(os.path.join(OUT, "probe_blocked.jpg"), quality=88)
    print(f"  stopped after {done:.1f}s facing "
          f"{compass.describe(compass.read_bearing(img))}", flush=True)
    return done


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "where"
    if cmd == "look":
        look(int(sys.argv[2]) if len(sys.argv) > 2 else 6)
    elif cmd == "walk":
        walk(float(sys.argv[2]), float(sys.argv[3]),
             int(sys.argv[4]) if len(sys.argv) > 4 else 4)
    elif cmd == "until":
        until_blocked(float(sys.argv[2]),
                      float(sys.argv[3]) if len(sys.argv) > 3 else 6.0)
    elif cmd == "reset":
        import reset_env
        ic.focus_chiaki_window(force=True); time.sleep(0.4)
        print(f"  spawn {compass.describe(reset_env.reset_environment(log=lambda *a: None))}",
              flush=True)
        cap().save(os.path.join(OUT, "probe_spawn.jpg"), quality=88)
    else:
        img = cap()
        img.save(os.path.join(OUT, "probe_where.jpg"), quality=88)
        print(f"  bearing {compass.describe(compass.read_bearing(img))}", flush=True)
