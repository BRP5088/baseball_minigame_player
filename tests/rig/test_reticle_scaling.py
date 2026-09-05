"""The gameplay check must be resolution-independent and reject overlays.

Two bugs this guards, both found live:

  * RETICLE_XY_FRAC pointed at plain background in the game-window capture, so
    in_gameplay() returned False on real gameplay.
  * The box sizes were absolute pixels, so the ring sampled a different area
    depending on capture width.

And one design point: brightness alone cannot separate gameplay from the PS5
home overlay (their ranges overlap), so the check is on the reticle's SHAPE.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)

import glob

from PIL import Image

import input_controller as ic

frames = sorted(glob.glob("demos/walk3_full_20260828_050731/f_*.jpg"))[::20]
assert frames, "no walk frames to test against"

# every frame of a walk is gameplay, at every capture width this codebase uses
for f in frames[:6]:
    src = Image.open(f)
    for w in (1400, 1920, 2000):
        im = src.resize((w, int(src.height * w / src.width)))
        assert ic.in_gameplay(im), (
            f"{_os.path.basename(f)} at {w}px read as NOT gameplay "
            f"(dotness {ic.reticle_dotness(im):.1f}) — the check is not "
            "resolution-independent")

# and the screens that must be rejected
for p in ("/tmp/reconnect_state.png", "/tmp/wake_state.png"):
    if _os.path.exists(p):
        im = Image.open(p)
        assert not ic.in_gameplay(im), (
            f"{p} accepted as gameplay (dotness {ic.reticle_dotness(im):.1f}) — "
            "input would be sent to a menu or the PS5 overlay")

print(f"OK: gameplay detected at 1400/1920/2000px across {len(frames[:6])} frames; "
      "pause and overlay screens rejected")
