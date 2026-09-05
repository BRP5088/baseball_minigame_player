"""Record a human-driven walk so the route can be recovered from it.

WHY
---
Dictated routes ("turn right 90, walk 3 seconds") are estimates, and tuning
them by trial and error costs a live run per attempt. A demonstration carries
the real numbers. Because the compass gives an ABSOLUTE heading from a single
frame, and walking never disturbs that heading (measured: 0.5 degrees across
nine presses), a recorded demo segments afterwards into exactly the form the
route needs: face bearing X, walk N seconds.

WHY NOT orchestrator.capture_screenshot_image()
-----------------------------------------------
It calls focus_chiaki_window(), sleeps 0.15s, then takes a FULL pyautogui
screenshot — about 0.8s per frame. Asking for 3fps got 1.2fps, and the
constant full-desktop grabbing made the game stutter for the person playing,
which is the one thing a recording must not do. mss grabs the same pixels
roughly an order of magnitude faster, and skipping the focus call matters
here: the human already has focus and we must not fight them for it.

Frames are OCR'd LATER, never during. A bearing read takes ~4s, so decoding
live would sample the walk once per four seconds and miss every turn.
"""
import os
import sys
import time


def record(out_dir, seconds=150.0, target_fps=6.0, max_width=1400):
    """Capture frames to out_dir. Returns (frames, actual_fps).

    Downscales and encodes INLINE rather than buffering raw frames: 50s at 6fps
    of full-resolution RGB is ~2.3GB of RAM, which is a worse problem than the
    one being solved. Grab is ~30ms and downscale+encode ~30ms, so 6fps leaves
    plenty of headroom and the game keeps the machine to itself.
    """
    from PIL import Image
    import compass

    # compass.fast_capture(), NOT mss.monitors[1]. The primary display is not
    # where the game is — it moved to a second monitor on 2026-08-27, and
    # grabbing monitors[1] would faithfully record the user's WORK instead of
    # the game. fast_capture also crops the letterbox away, so every recorded
    # frame is game pixels only and read_bearing can decode it directly. A demo
    # recorded of the wrong screen is worse than none: it looks like data.
    os.makedirs(out_dir, exist_ok=True)
    interval = 1.0 / target_fps
    n = 0
    if True:
        t0 = time.time()
        nxt = 0.0
        while True:
            now = time.time() - t0
            if now >= seconds:
                break
            if now < nxt:
                time.sleep(min(0.004, max(0.0, nxt - now)))
                continue
            nxt = now + interval
            img = compass.fast_capture()
            if img.width > max_width:
                r = max_width / img.width
                img = img.resize((max_width, int(img.height * r)), Image.BILINEAR)
            img.save(os.path.join(out_dir, f"f_{now:07.2f}.jpg"), quality=78)
            n += 1
    return n, n / seconds


if __name__ == "__main__":
    out = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
    fps = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
    print(f"  recording {secs:.0f}s at {fps:.0f}fps -> {out}", flush=True)
    n, actual = record(out, secs, fps)
    print(f"  captured {n} frames ({actual:.1f}/s actual)", flush=True)
