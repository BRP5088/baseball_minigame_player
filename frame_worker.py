"""Frame-capture worker. Run as its OWN PROCESS by record_input.py.

WHY A SEPARATE PROCESS
----------------------
pyautogui pulls in pyscreeze, which pulls in cv2, which ships its own copy of
libSDL2 — and pygame ships another. Loading both into one process makes macOS
warn that a dozen SDL classes are implemented twice, "may cause spurious
casting failures and mysterious crashes", and a recording did die eight seconds
in. Two processes never share an address space, so the duplicate cannot arise.

Writes ready.txt once imports are done, so the parent can start its own clock at
the same moment instead of guessing at subprocess startup time.
"""
import os
import sys
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-frames")

out_dir, seconds = sys.argv[1], float(sys.argv[2])

from PIL import Image

import compass

os.makedirs(out_dir, exist_ok=True)
compass.fast_capture()                       # warm the capture path
open(os.path.join(out_dir, "ready.txt"), "w").write("ready")

t0 = time.time()
nxt = 0.0
while True:
    now = time.time() - t0
    if now >= seconds:
        break
    if now < nxt:
        time.sleep(0.004)
        continue
    nxt = now + 1 / 6.0
    img = compass.fast_capture()
    if img.width > 1400:
        r = 1400 / img.width
        img = img.resize((1400, int(img.height * r)), Image.BILINEAR)
    img.save(os.path.join(out_dir, f"f_{now:07.2f}.jpg"), quality=78)
print("frames done", flush=True)
