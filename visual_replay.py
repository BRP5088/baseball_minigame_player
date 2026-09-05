"""Replay recorded input, steering the CAMERA to match the recorded view.

THE INSIGHT THIS IMPLEMENTS
---------------------------
The person recording deliberately put the reticle on landmarks — doorways,
the table — so the walk would be followable. That only helps if the replay
puts the reticle in the same places, and correcting heading alone does not:
heading is yaw, and pitch drifts freely, so the view ends up aimed somewhere
the recording never looked.

The recording's own frames say exactly where the camera pointed at every
moment. So instead of correcting one angle against a compass, compare the live
frame with the recorded frame at the same timestamp and steer both axes until
they line up.

HOW THE ERROR IS MEASURED
-------------------------
Cross-correlate a downscaled, HUD-free strip of the two frames. The horizontal
shift that best aligns them is yaw error; the vertical shift is pitch error.
This works where the compass cannot: it sees pitch, and it degrades gracefully
in the dark instead of abstaining.

Correction is deliberately gentle. The recorded sticks still drive the walk —
this only removes accumulated error, and a hard correction would fight the
player's own camera movement rather than following it.
"""

import json
import os
import threading
import time

import numpy as np
from PIL import Image

import analog_replay as ar

HUD_LEFT = 0.26          # quest log occupies the left of frame
HUD_TOP = 0.11           # compass strip
THUMB = (160, 90)

MAX_SHIFT = 40           # search +-this many thumbnail px
YAW_GAIN = 0.020         # stick units per px of horizontal error
PITCH_GAIN = 0.016
MAX_CORRECTION = 0.30
DEADBAND_PX = 3          # ignore shifts this small; they are noise


def _strip(img):
    """HUD-free, contrast-normalised thumbnail for correlation."""
    g = img.convert("L")
    w, h = g.size
    g = g.crop((int(w * HUD_LEFT), int(h * HUD_TOP), w, h))
    a = np.asarray(g.resize(THUMB, Image.BILINEAR), dtype=float)
    a -= a.mean()
    n = np.linalg.norm(a)
    return a / n if n > 1e-6 else a


def offset(live, want):
    """(dx, dy) in thumbnail px that best aligns `live` onto `want`.

    Positive dx means the live view sits LEFT of the recorded one and must
    rotate right to match.
    """
    a, b = _strip(live), _strip(want)
    best, bx, by = -2.0, 0, 0
    for dy in range(-12, 13, 3):
        rb = np.roll(b, dy, axis=0)
        for dx in range(-MAX_SHIFT, MAX_SHIFT + 1, 2):
            v = float((a * np.roll(rb, dx, axis=1)).sum())
            if v > best:
                best, bx, by = v, dx, dy
    return bx, by, best


class FrameWatcher:
    """Holds the newest capture so the input loop never blocks on one."""

    def __init__(self, capture):
        self.capture = capture
        self.img = None
        self._stop = threading.Event()

    def start(self):
        def loop():
            while not self._stop.is_set():
                try:
                    self.img = self.capture()
                except Exception:
                    pass
                # Yield. Without this the capture loop is CPU-bound and holds
                # the GIL hard enough to slow whatever it is feeding, which is
                # how a control loop ends up running slower than the
                # corrections it is computing assume.
                time.sleep(0.005)
        threading.Thread(target=loop, daemon=True).start()
        return self

    def stop(self):
        self._stop.set()


def load_frames(demo_dir):
    """[(t, path)] of the recording's frames, by timestamp."""
    out = []
    for f in sorted(os.listdir(demo_dir)):
        if f.startswith("f_") and f.endswith(".jpg"):
            out.append((float(f[2:-4]), os.path.join(demo_dir, f)))
    return out


def replay(demo_dir, capture, t0=5.6, t1=25.9, correct_every=0.25, log=print):
    samples = json.load(open(os.path.join(demo_dir, "input.json")))
    frames = load_frames(demo_dir)
    win = [s for s in samples if t0 <= s["t"] <= t1]
    if not win or not frames:
        log("  nothing to replay")
        return

    watcher = FrameWatcher(capture).start()
    time.sleep(0.5)
    log(f"  replaying {len(win)} samples, matching the view every "
        f"{correct_every}s against {len(frames)} recorded frames")

    corr_x = corr_y = 0.0
    last_correct = -99.0
    corrections = 0
    start_t = win[0]["t"]
    started = time.time()
    try:
        for s in win:
            now = s["t"]
            if now - last_correct >= correct_every and watcher.img is not None:
                ft, fp = min(frames, key=lambda f: abs(f[0] - now))
                if abs(ft - now) < 0.4:
                    dx, dy, _ = offset(watcher.img, Image.open(fp))
                    corr_x = 0.0 if abs(dx) <= DEADBAND_PX else \
                        max(-MAX_CORRECTION, min(MAX_CORRECTION, dx * YAW_GAIN))
                    corr_y = 0.0 if abs(dy) <= DEADBAND_PX else \
                        max(-MAX_CORRECTION, min(MAX_CORRECTION, dy * PITCH_GAIN))
                    if corr_x or corr_y:
                        corrections += 1
                last_correct = now

            a = s["axes"]
            rx = max(-1.0, min(1.0, a.get("rx", 0.0) + corr_x))
            ry = max(-1.0, min(1.0, a.get("ry", 0.0) + corr_y))
            ar.send([f"left_x {ar.to_axis(a.get('lx', 0))}",
                     f"left_y {ar.to_axis(a.get('ly', 0))}",
                     f"right_x {ar.to_axis(rx)}",
                     f"right_y {ar.to_axis(ry)}"])
            behind = (now - start_t) - (time.time() - started)
            if behind > 0:
                time.sleep(behind)
    finally:
        ar.clear()
        watcher.stop()
    log(f"  done in {time.time() - started:.1f}s, corrected {corrections} times")
