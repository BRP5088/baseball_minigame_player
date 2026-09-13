"""Camera-relative movement: correctness and cost. Offline, no key ever sent.

WHY THIS EXISTS
---------------
Two bugs in this one function wasted hours of live path-finding, and both were
invisible from the outside because the character simply appeared to be "stuck".

1. NOT WAITING FOR FOCUS. press() waits 0.15s after changing window focus
   before pressing a key; hold_combo did not, so the keydown landed while
   focus was still moving and part of every hold was swallowed. Measured live,
   a 1.0s hold travelled a THIRD as far as the same hold through press()
   (frame delta 7.9 against 24.9). Every route duration tuned against the
   broken mover was compensating for it.

2. pyautogui.PAUSE. It inserts 0.1s after EVERY keyDown and keyUp, and a
   blended direction issues ~8 key calls per 0.18s slice: a 1.0s blended walk
   took 11.3s of wall clock, nearly all of it library pause. A route that
   commands 20s of walking would take four minutes.

Both are timing faults, so the test asserts on TIME and on the key events
issued, with pyautogui stubbed out — nothing reaches the game.
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
import time
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import pyautogui

# Captured BEFORE any movement runs. Taking this baseline later is worthless:
# the cost section below already calls a diagonal walk, which goes through
# hold_combo, so a mover that fails to restore PAUSE has corrupted the value
# by then and the comparison passes against its own damage. That ordering bug
# let a real mutation survive.
ORIGINAL_PAUSE = pyautogui.PAUSE

SENT = []


def _fake_key(kind):
    def go(k):
        SENT.append((kind, k))
        # SIMULATE pyautogui's inter-call pause. The real keyDown/keyUp sleep
        # PAUSE after every call, and stubbing them plainly deletes that cost —
        # which made an earlier version of this test unable to detect the very
        # bug it exists for (removing the PAUSE suppression survived cleanly).
        if pyautogui.PAUSE:
            time.sleep(pyautogui.PAUSE)
    return go


pyautogui.keyDown = _fake_key("down")
pyautogui.keyUp = _fake_key("up")

import input_controller as ic

ic.focus_chiaki_window = lambda force=False: False      # no osascript, no wait
# This file drives the focus+pyautogui path ON PURPOSE, against the stubs above.
# press()/hold_combo()/walk_at() refuse it under BASEBALL_TEST_RUN since 2026-09-13 --
# it typed "c" into the frontmost window during a mutation run -- so opt in explicitly.
ic.FOCUS_PRESS_IN_TESTS = True

fails = []


def timed(rel, secs):
    SENT.clear()
    t0 = time.time()
    ic.walk_at(rel, secs)
    return time.time() - t0, list(SENT)


# --- cost: wall time must track commanded time -----------------------------
for rel, label in ((0.0, "cardinal"), (45.0, "diagonal"), (20.0, "blended")):
    dt, sent = timed(rel, 1.0)
    if dt > 1.0 * 1.6 + 0.3:
        fails.append(f"{label} walk of 1.0s took {dt:.2f}s — pyautogui.PAUSE is "
                     f"back, or the slices re-focus the window; a 20s route "
                     f"would take minutes")
    if not sent:
        fails.append(f"{label} walk issued no key events at all")

# --- global state must be restored -----------------------------------------
# pyautogui.PAUSE is process-global and every other caller depends on it. A
# mover that zeroes it and forgets to put it back silently removes the pacing
# from every keystroke this project sends, including menu navigation where a
# dropped press picks the wrong save slot.
timed(20.0, 0.3)
if pyautogui.PAUSE != ORIGINAL_PAUSE:
    fails.append(f"pyautogui.PAUSE left at {pyautogui.PAUSE} after a blended "
                 f"walk (was {ORIGINAL_PAUSE}) — global pacing state leaked")
pyautogui.PAUSE = ORIGINAL_PAUSE
ic.hold_combo(("walk_up",), 0.1)
if pyautogui.PAUSE != ORIGINAL_PAUSE:
    fails.append(f"pyautogui.PAUSE left at {pyautogui.PAUSE} after hold_combo "
                 f"(was {ORIGINAL_PAUSE})")

# --- the cardinal fast path must actually be taken -------------------------
# A pure direction needs ONE hold, not a duty cycle. Blending it works but
# issues an order of magnitude more key events, and every one of those is a
# chance for the stream to drop an input.
_, sent_card = timed(0.0, 1.0)
if len(sent_card) > 4:
    fails.append(f"a pure-forward walk issued {len(sent_card)} key events — "
                 f"the cardinal fast path is not being taken")

# --- correctness: the right keys for the right direction -------------------
def keys_for(rel):
    _, sent = timed(rel, 0.3)
    return {k for _, k in sent}


forward = ic.KEYMAP["walk_up"]
right = ic.KEYMAP["walk_right"]
left = ic.KEYMAP["walk_left"]
back = ic.KEYMAP["walk_down"]

if keys_for(0.0) != {forward}:
    fails.append(f"0 deg should be pure forward, got {keys_for(0.0)}")
if keys_for(90.0) != {right}:
    fails.append(f"90 deg should be pure strafe-right, got {keys_for(90.0)}")
if keys_for(270.0) != {left}:
    fails.append(f"270 deg should be pure strafe-left, got {keys_for(270.0)}")
if keys_for(180.0) != {back}:
    fails.append(f"180 deg should be pure backward, got {keys_for(180.0)}")
if keys_for(45.0) != {forward, right}:
    fails.append(f"45 deg should blend forward+right, got {keys_for(45.0)}")

# A blend must use BOTH bracketing directions — that is the whole point, since
# aiming the camera is stuck at a ~28 degree quantum while travel must be
# continuous.
mixed = keys_for(20.0)
if forward not in mixed or right not in mixed:
    fails.append(f"20 deg should mix forward and forward-right, got {mixed}")

# --- every key pressed must be released ------------------------------------
for rel in (0.0, 20.0, 45.0, 200.0):
    _, sent = timed(rel, 0.5)
    held = {}
    for kind, k in sent:
        held[k] = held.get(k, 0) + (1 if kind == "down" else -1)
    stuck = [k for k, n in held.items() if n != 0]
    if stuck:
        fails.append(f"{rel} deg left keys held down: {stuck} — a stuck "
                     f"movement key walks the character until something else "
                     f"presses it")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  walk_at: cardinal/diagonal/blended all track commanded time, pick the "
      "correct keys, blend both bracketing directions, and release everything")
