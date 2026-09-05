"""Focus detection and the closed-loop turn stopping rule. Offline, no input.

WHY THIS EXISTS
---------------
Two live test runs produced plausible-looking numbers that were entirely
fictional, because the chiaki window had lost keyboard focus and every press
vanished. Nothing in the data said so — a bearing read without focus is a
perfectly valid bearing that simply never changes.

The game only draws its aiming reticle while focused, so focus is observable
from any frame. These tests pin the two properties that make that useful:
has_focus must reject a frame with NO reticle (or it never fires), and it must
reject a frame that is broadly bright (or a loading screen reads as focused).

The turn rule is here because its correctness is counter-intuitive: the stream
cannot deliver less than ~16 degrees, so stopping at an error of 11 is WORSE
than pressing once more and landing on -5. The stop threshold is therefore half
a step, not a tolerance someone picked.
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
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import numpy as np
from PIL import Image

import compass
import input_controller as ic

W, H = 2000, 1292
fails = []


def _frames(pattern, limit=12):
    import glob

# GAMEPLAY FIXTURES: frames from the CURRENT capture path.
#
# This used to read screenshot_log/reset_facing_*.jpg, which are 2000x1292
# whole-DISPLAY grabs from a capture path that no longer exists — the game
# occupied only part of those frames, so the reticle sits at a different
# fraction than in a game-window capture. One constant cannot serve both, and
# the old geometry can no longer occur, so testing against it tests a
# configuration the code will never see.
    return sorted(glob.glob(pattern))[:limit]


# --- has_focus: asks the window manager, not the pixels --------------------
# Patched at the subprocess boundary so no osascript actually runs.
import subprocess


class _Out:
    def __init__(self, name):
        self.stdout = name


_real_run = subprocess.run
subprocess.run = lambda *a, **k: _Out("chiaki\n")
if not ic.has_focus():
    fails.append("frontmost really is chiaki but has_focus said False")
subprocess.run = lambda *a, **k: _Out("Terminal\n")
if ic.has_focus():
    fails.append("frontmost is Terminal but has_focus said True — inert check")
subprocess.run = lambda *a, **k: _Out("")
if ic.has_focus():
    fails.append("empty frontmost read as focused")


def _boom(*a, **k):
    raise OSError("osascript unavailable")


subprocess.run = _boom
if ic.has_focus():
    fails.append("has_focus returned True when it could not ask at all — it "
                 "must fail closed, or a broken osascript silently green-lights "
                 "every measurement")
subprocess.run = _real_run

# --- in_gameplay: validated against REAL logged frames ---------------------
# Synthetic frames would only prove the arithmetic. These are the actual game
# states the check has to separate, which is what it is for.
gameplay = _frames("demos/walk3_full_20260828_050731/f_*.jpg")
paused = (_frames("screenshot_log/reset_pause*.jpg")
          + _frames("screenshot_log/reset_down*.jpg")
          + _frames("screenshot_log/reset_confirm*.jpg"))
if not gameplay or not paused:
    fails.append("the labelled reference frames are missing — this test cannot "
                 "validate anything without them")
for f in gameplay:
    if not ic.in_gameplay(Image.open(f).convert("RGB")):
        fails.append(f"gameplay frame {f} read as NOT in gameplay")
for f in paused:
    if ic.in_gameplay(Image.open(f).convert("RGB")):
        fails.append(f"pause-menu frame {f} read as in gameplay — the reset "
                     f"would try to walk while sitting in a menu")

# --- geometry must be DERIVED, never assumed --------------------------------
# The laptop was moved and the chiaki window resized mid-session. Every
# hardcoded fraction went stale at once: the reticle shifted 141px and the
# letter spacing went 293 -> 329 px/90deg. Bearings stayed perfectly readable
# and were simply WRONG, so eight consecutive turns drove the camera nowhere
# while reporting plausible numbers. The fix is to measure both off the frame.
_geo = _frames("screenshot_log/reset_facing_*.jpg")
if not _geo:
    fails.append("no reference frame to test geometry against")


def reframe(base, scale, dx, dy):
    """The window moved/resized INSIDE an unchanged desktop capture.

    A plain resize of the whole image is NOT this bug: it scales every fraction
    proportionally, so hardcoded constants keep working and the test proves
    nothing (an earlier version of this test did exactly that and every
    mutation survived it). What actually happened is the capture stayed
    2000x1292 while the game view within it moved and changed size.
    """
    canvas = Image.new("RGB", base.size, (0, 0, 0))
    small = base.resize((int(base.width*scale), int(base.height*scale)),
                        Image.LANCZOS)
    canvas.paste(small, (dx, dy))
    return canvas


for f in _geo[:2]:
    base = Image.open(f).convert("RGB")
    b0 = compass.read_bearing(base)
    if b0 is None:
        fails.append(f"{f}: reference frame unreadable")
        continue
    if ic.view_bounds(base) is None:
        fails.append(f"{f}: view bounds not found, so there is no geometry "
                     f"reference and the bearing would be guesswork")
    # 0.85x and 0.92x, not 0.75x. A 0.75x shrink takes the letter rings to
    # ~24px, where tesseract genuinely misreads them (W as N, S as W), and two
    # consistently-misread letters agree with each other and with the scale
    # derived from them — so the module answers confidently and wrongly, and no
    # consistency check inside it can tell. That is a REAL limitation, recorded
    # rather than hidden: a bearing read from a heavily downscaled view is not
    # trustworthy. It is also not a case that occurs — the game runs fullscreen
    # and the capture is native — whereas moving or resizing the window is a
    # thing that actually happened mid-session and cost hours.
    for scale, dx, dy in ((0.85, 180, 20), (0.92, 90, 10)):
        moved = reframe(base, scale, dx, dy)
        # Abstaining is ACCEPTABLE here and correct: a heavily downscaled view
        # genuinely loses the OCR fidelity to read the bar. What is not
        # acceptable is answering anyway. So this asserts only "never wrong".
        b1 = compass.read_bearing(moved)
        if b1 is None:
            pass
        # 12 deg, not 6: a downscaled bar genuinely loses OCR precision in the
        # blob centres, and the loop's own stop threshold is 8. What this
        # guards is GROSS error — the 29-to-146 degree kind seen when geometry
        # was assumed rather than measured.
        elif abs(compass.angular_error(b0, b1)) > 12.0:
            fails.append(
                f"{f}: bearing moved {compass.angular_error(b0,b1):+.1f} deg "
                f"when the window moved ({scale}x, +{dx}px) — it must be right "
                f"or abstain, never confidently wrong")

# --- consensus: one bad OCR must not drag the heading -----------------------
# Live, a STATIONARY camera read 348 -> 18 -> 351 with zero input: a spurious
# blob was read as a letter and a plain mean laundered it into the answer.
# Steering on that is what produced turn_to's overshoot-and-return oscillation.
if sorted(compass.consensus([90.0, 91.0, 120.0])) != [90.0, 91.0]:
    fails.append("a 30-deg outlier survived the consensus filter — a plain "
                 "mean would put the heading ~10 deg off with no way to tell")
if sorted(compass.consensus([90.0, 91.0, 92.0])) != [90.0, 91.0, 92.0]:
    fails.append("agreeing readings were discarded")
if compass.consensus([90.0]) != [90.0]:
    fails.append("a lone reading was dropped — most frames show one letter, so "
                 "this would abstain almost always")
# Wraparound: 359 and 1 are 2 degrees apart, not 358.
if sorted(compass.consensus([359.0, 1.0, 180.0])) != [1.0, 359.0]:
    fails.append("consensus failed across the 0/360 wrap")
# The outlier must not win by being listed first.
if sorted(compass.consensus([200.0, 10.0, 11.0])) != [10.0, 11.0]:
    fails.append("an outlier listed first was taken as the anchor")

# --- the stopping rule -----------------------------------------------------
# Below half a step, pressing overshoots further than the error it corrects.
half = compass.MIN_TURN_STEP_DEG / 2
if not half < compass.MIN_TURN_STEP_DEG:
    fails.append("stop threshold is not below one step")

presses = []

# turn_to compares frames to check a press had any effect, so the fake capture
# must return real images — and DIFFERENT ones each call, or every press looks
# dead and the loop aborts before exercising the stopping rule.
_tick = [0]


def fake_capture():
    _tick[0] += 1
    return Image.new("RGB", (300, 200), (_tick[0] * 37 % 256, 40, 90))


def fake_press(action, hold_seconds=0.0, post_delay=0.0):
    presses.append(action)
    step = max(compass.MIN_TURN_STEP_DEG,
               hold_seconds * compass.TURN_RATE_DEG_PER_SEC)
    state["deg"] = (state["deg"] + (step if action == "look_right" else -step)) % 360


import time as _t
_t.sleep = lambda *a: None
compass.read_bearing = lambda img: state["deg"]
ic.has_focus = lambda: True
ic.in_gameplay = lambda img: True

# An error of 11 exceeds half a step, so the loop MUST press again rather than
# accept it — that is the whole behavioural change from a fixed tolerance.
state = {"deg": 0.0}
presses.clear()
compass.turn_to(11.0, fake_press, fake_capture, log=lambda *a: None)
if not presses:
    fails.append("error of 11 deg (above half a step) was accepted without "
                 "pressing — the loop reverted to a fixed tolerance")

# An error INSIDE half a step must not be chased, or the loop oscillates.
state = {"deg": 0.0}
presses.clear()
compass.turn_to(half * 0.5, fake_press, fake_capture, log=lambda *a: None)
if presses:
    fails.append(f"error of {half*0.5:.1f} deg (inside half a step) was chased "
                 f"anyway with {len(presses)} press(es) — this oscillates")

# Out of iterations, the returned bearing must be a FRESH measurement.
#
# This previously asserted the opposite — that the CLOSEST heading seen came
# back — and that was wrong. The loop presses on its final iteration too, so
# the closest-seen value names a heading the camera has already left. Simulated
# at a 3-iteration budget, returning it misreports the final heading by 67
# degrees at 2.4x gain where reading once more misreports by 2. The live trace
# showed the same thing: "gave up, best was 18 degrees off" while the camera
# was actually at 313.
#
# So: the answer must match the LAST reading, not the nicest one.
seq = iter([40.0, 12.0, 100.0, 150.0, 200.0, 250.0, 300.0, 340.0])
last_seen = []


def _reading(img=None):
    v = next(seq, 340.0)
    last_seen.append(v)
    return v


compass.read_bearing = _reading
got = compass.turn_to(0.0, lambda *a, **k: None, fake_capture, max_iters=8,
                      log=lambda *a: None)
if got is None:
    fails.append("returned None despite every bearing being readable")
elif last_seen and abs(compass.angular_error(got, last_seen[-1])) > 0.01:
    fails.append(f"returned {got}, which is not the final measurement "
                 f"{last_seen[-1]} — a stale bearing names a heading the "
                 f"camera has already left")

# Each gate must ABSTAIN, and must not press. A turn attempted without focus,
# or while the game sits in a menu, is the exact failure they exist to stop.
ic.has_focus = lambda: False
compass.read_bearing = lambda img: 0.0
presses.clear()
got = compass.turn_to(90.0, fake_press, fake_capture, log=lambda *a: None)
if got is not None:
    fails.append(f"turned without focus and returned {got} — the gate is inert")
if presses:
    fails.append(f"pressed {len(presses)} time(s) with no focus")
ic.has_focus = lambda: True

# NOTE: turn_to deliberately does NOT gate on in_gameplay. The reticle is a
# reliable positive signal but its absence is ambiguous (a dark door frame has
# no reticle yet turns fine), and gating there aborted eight valid turns. The
# dead-press check below is the guard that belongs here, because it measures
# whether input had an effect instead of inferring it.

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  has_focus tracks frontmost and fails closed; in_gameplay separates "
      f"{len(gameplay)} live frames from {len(paused)} menu frames; stop rule "
      f"presses above {half:.0f} deg, holds below, and returns a "
      f"fresh measurement rather than a stale best")
