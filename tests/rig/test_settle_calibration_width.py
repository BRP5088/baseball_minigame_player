"""SETTLE_CALIBRATION_WIDTH matches the rig's native geometry. OFFLINE.

WHAT THIS GUARDS, AND WHY IT DID NOT EXIST UNTIL NOW. The constant was 2000 for
months and NOTHING pinned it -- a grep of tests/ for it returns only this file.
2000 was a fossil of the Aug-26 capture path, which grabbed the whole laptop
display: the only 2000px frames in the archive are 32 files at 2000x1292, aspect
1.548, which is the built-in display (1728x1117) upscaled, showing the macOS
menu bar and the Dock.

The cost was not theoretical. `_fast_grab` upscaled every frame 1920 -> 2000
before any reader saw it, so the hand crop arrived 1020px wide against
local_hand.ANCHOR_W of 979 -- and the first live match read ZERO cards.

THE EVIDENCE FOR 1920, measured over 3,000 consecutive pairs of
screenshot_log/run_20260828_140236 (the one 10Hz stream, all 1920x1080). The
comment above SETTLE_THRESHOLDS claims that at a shared 6.0, 17.4% of idle
`hand` pairs read as moving:

    claimed 17.4%      at 1920: 17.70%      at 2000: 12.27%

1920 reproduces it to 0.3pp. The upscale also cost verdicts: over 2,500 pairs,
25 flips, every one moving@1920 -> settled@2000 -- the gate calling a MOVING
screen SETTLED, which hands the hand reader a mid-animation frame.

WHY THE CONSTANT IS NOT SIMPLY DELETED. The normalisation is real work on the
FALLBACK path, which can return an mss logical grab (1728x1117) or a pyautogui
Retina grab (3456x2234). Mean-absolute-delta is scale-sensitive, so those must
be brought to a common width or the statistic is not comparable between
backends. What was wrong was the WIDTH, not the idea.

THIS TEST ASSERTS BEHAVIOUR, NOT THE CONSTANT (CLAUDE.md 10.11). It never says
"the width is 1920"; it says a frame at the RIG's geometry passes through
untouched, and a frame at another geometry is normalised. Setting the constant
back to 2000 fails the first; deleting the resize fails the second.

MUTANTS CAUGHT (2026-09-13, each restored after):
  * SETTLE_CALIBRATION_WIDTH = 2000 -> "a native rig frame is not resized" FAILS
  * the resize removed from game_capture.grab
        -> "a foreign geometry IS normalised" FAILS
  * the hand normalisation removed from crop_gameplay_regions
        -> "the hand crop lands on ANCHOR_W" FAILS at the foreign geometry
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image

import game_capture
import compass
import local_hand
import orchestrator as o

FAILS = []
RAN = {"grab": 0, "crop": 0}

# The geometry the PS5 actually streams, and what chiaki's decoded-frame dump
# hands back. Both capture functions were measured returning exactly this.
RIG_W, RIG_H = 1920, 1080
# The Aug-26 laptop display, i.e. the geometry the fallback path can still
# produce and the one the dead constant was derived from.
FOREIGN_W, FOREIGN_H = 1728, 1117


def check(label, cond, detail=""):
    if cond:
        print(f"  PASS {label}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL {label}" + (f"  ({detail})" if detail else ""))
        FAILS.append(label)


def _grab(w, h):
    """game_capture.grab() with the capture stubbed to a frame of this size."""
    real = compass.fast_capture
    try:
        compass.fast_capture = lambda: Image.new("RGB", (w, h), (40, 40, 40))
        RAN["grab"] += 1
        return game_capture.grab(width=o.SETTLE_CALIBRATION_WIDTH)
    finally:
        compass.fast_capture = real


# --- 1. a frame at the rig's own geometry must pass through UNTOUCHED --------
#
# This is the whole point. If the calibration width is anything other than what
# the rig captures, every frame is resampled before any reader sees it, and the
# raw-pixel readers downstream (local_hand's disc and blob size gates) are handed
# a crop they were not measured on.
native = _grab(RIG_W, RIG_H)
check("a native rig frame is NOT resized",
      native is not None and native.size == (RIG_W, RIG_H),
      f"{RIG_W}x{RIG_H} in -> {None if native is None else native.size} out")

# --- 2. CONTROL: a foreign geometry IS still normalised ----------------------
#
# Without this, check 1 would also pass if the resize were deleted outright,
# which would silently break the fallback path's comparability between backends.
foreign = _grab(FOREIGN_W, FOREIGN_H)
check("a foreign geometry IS normalised to the calibration width",
      foreign is not None and foreign.width == o.SETTLE_CALIBRATION_WIDTH,
      f"{FOREIGN_W}x{FOREIGN_H} in -> {None if foreign is None else foreign.size} out")

# --- 3. the hand crop lands on ANCHOR_W, from EITHER geometry ----------------
#
# local_hand's size gates are RAW PIXELS, so this is the crop width the reader
# was actually calibrated at. crop_gameplay_regions normalises only the hand,
# because every other region carries its own anchor.
for label, img in (("native", native), ("normalised foreign", foreign)):
    if img is None:
        check(f"the hand crop lands on ANCHOR_W ({label})", False, "no frame")
        continue
    RAN["crop"] += 1
    hand = dict(o.crop_gameplay_regions(img)).get("hand")
    check(f"the hand crop lands on ANCHOR_W ({label})",
          hand is not None and hand.width == int(local_hand.ANCHOR_W),
          f"{img.size} -> hand {None if hand is None else hand.width}px "
          f"vs ANCHOR_W {int(local_hand.ANCHOR_W)}")

# --- 4. ANTI-VACUITY --------------------------------------------------------
#
# Every check above routes through the two helpers. A counter that reads 0 for
# the wrong reason would let the whole file pass while exercising nothing, which
# is the shape this project keeps finding (CLAUDE.md 10.1).
check("the capture helper actually ran", RAN["grab"] >= 2, f"{RAN['grab']} grabs")
check("the crop helper actually ran", RAN["crop"] >= 2, f"{RAN['crop']} crops")
check("the two geometries under test are genuinely different",
      (RIG_W, RIG_H) != (FOREIGN_W, FOREIGN_H),
      "otherwise check 2 is check 1 again")

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
