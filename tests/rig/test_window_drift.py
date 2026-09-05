"""The window-position guard must actually be able to FAIL.

WHAT THIS REPLACES
------------------
A previous guard measured how much of the capture was lit and called that "the
game fills the frame". The macOS desktop lights every column edge to edge, so
it returned 1.000 for every frame ever captured, including the windowed ones
the ban-grid constants were calibrated on. It passed its own tests because
those tests used images pasted on a BLACK canvas — a displacement that does not
happen in reality.

So the first thing asserted here is the thing that was missing: that a REAL
displacement, of the size that was measured to corrupt the ban grid, is
rejected. A guard that cannot fail is worse than no guard, because it is
mistaken for protection.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)

import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
import input_controller as ic

fails = []
REF = (100.0, 50.0, 1500.0, 900.0)


def at(rect):
    ic.game_window_rect = lambda: rect


real = ic.game_window_rect
try:
    # --- the corrupting displacement must be REJECTED ----------------------
    # 110 capture px on a 2000px capture of a 1728pt screen is ~95pt, and that
    # is the shift measured to flip a ban-grid cell.
    at((100.0 + 95.0, 50.0, 1500.0, 900.0))
    fits, drift, _, _ = ic.window_drift(reference=REF)
    if fits:
        fails.append(f"a 95pt displacement was ACCEPTED (drift {drift}) — that "
                     "is the shift measured to flip a ban-grid cell, i.e. ban "
                     "the wrong card with no error raised")

    # --- a small, measured-safe nudge must be tolerated --------------------
    at((100.0 + 12.0, 50.0 - 8.0, 1500.0, 900.0))
    fits, drift, _, _ = ic.window_drift(reference=REF)
    if not fits:
        fails.append(f"a 12pt nudge was rejected (drift {drift}) — the grid was "
                     "measured to read identically far past this, so this "
                     "refuses runs that would have worked")

    # --- resizing counts too, not just moving ------------------------------
    at((100.0, 50.0, 1500.0 - 200.0, 900.0))
    fits, _, _, _ = ic.window_drift(reference=REF)
    if fits:
        fails.append("a 200pt narrower window was accepted — every fractional "
                     "region scales with window size, so a resize corrupts "
                     "them exactly as a move does")

    # --- no window at all is NOT 'fine' ------------------------------------
    at(None)
    fits, drift, rect, _ = ic.window_drift(reference=REF)
    if fits:
        fails.append("a missing chiaki window was reported as ok — the regions "
                     "then point at whatever else is on screen")
    if rect is not None:
        fails.append("reported a rect when no window was found")

    # --- never calibrated is not the same as 'perfectly placed' ------------
    at(REF)
    fits, drift, rect, ref = ic.window_drift(reference=None)
    if drift == 0.0:
        fails.append("an uncalibrated machine reported drift 0.0, which reads "
                     "as 'measured and perfect' — it must be None so the "
                     "caller can tell the two apart")
finally:
    ic.game_window_rect = real

if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("  window guard rejects the 95pt shift that corrupts the ban grid, "
      "tolerates a 12pt nudge, catches resizes, fails closed with no window, "
      "and distinguishes 'never calibrated' from 'perfectly placed'")
