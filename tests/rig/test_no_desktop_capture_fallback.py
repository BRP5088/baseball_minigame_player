"""PRIVACY: a missed game_capture.grab() must never fall back to a desktop
screenshot. OFFLINE.

WHY THIS EXISTS
----------------
Three sites in orchestrator.py used to do `game_capture.grab() or
pyautogui.screenshot()` (or the equivalent two-step form). pyautogui.screenshot()
(and, on the old _fast_grab() mss path, _MSS.grab(_MSS.monitors[1])) captures the
PRIMARY display -- on this two-monitor rig, that is the user's own laptop desktop,
not the game. It fired once live (overnight/run_live_20260922b.log:780) and no
desktop capture is on disk, but the mechanism was real: any transient failure to
locate the chiaki window silently photographed whatever the user was doing on
their own screen.

THE FIX: capture_screenshot_image() and _fast_grab() now return None on a missed
grab, and _screenshot_logger_loop() skips that tick and writes nothing. NEVER a
desktop screenshot.

THE PART THAT MATTERS MORE: every direct caller of those two functions had to be
re-checked, because before this change neither one could ever return None (the
fallback always produced SOME image). Several callers did `img.size`,
`.convert(...)`, or handed the frame straight to a reader with no guard, and would
have crashed the turn loop or a live match the first time a grab was missed. This
file pins the None-safety of a representative sample of those callers: the ones
directly reachable and cheaply testable without standing up a whole live match.
"""
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import shutil
import tempfile

import game_capture
import pyautogui
import orchestrator as o

FAILS = []


def check(label, cond, detail=""):
    if cond:
        print(f"  PASS {label}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL {label}" + (f"  ({detail})" if detail else ""))
        FAILS.append(label)


class _PyAutoGUIGuard:
    """Stubs pyautogui.screenshot() to RECORD any call and RAISE -- so a
    fallback that reaches it fails the test immediately and visibly, rather
    than silently returning a picture that happens to look plausible."""

    def __init__(self):
        self.calls = 0
        self._real = pyautogui.screenshot

    def _fake(self, *a, **k):
        self.calls += 1
        raise AssertionError(
            "pyautogui.screenshot() was called -- this is the PRIVACY bug "
            "(captures the primary display, not the game)")

    def __enter__(self):
        pyautogui.screenshot = self._fake
        return self

    def __exit__(self, *exc):
        pyautogui.screenshot = self._real


def _grab_always_none(*a, **k):
    return None


# game_capture.grab is imported LOCALLY inside every function under test
# (`import game_capture; game_capture.grab(...)`), so patching the attribute
# on the real module object -- not sys.modules substitution -- is what every
# call site actually sees, the same technique test_settle_calibration_width.py
# uses for compass.fast_capture.
_real_grab = game_capture.grab
game_capture.grab = _grab_always_none


# ============================================================================
# 1. THE THREE SITES THIS TICKET IS ABOUT
# ============================================================================

with _PyAutoGUIGuard() as guard:
    img = o.capture_screenshot_image()
    check("capture_screenshot_image() returns None on a missed grab",
          img is None, f"got {img!r}")
    check("capture_screenshot_image(): pyautogui.screenshot NOT called",
          guard.calls == 0, f"{guard.calls} call(s)")

with _PyAutoGUIGuard() as guard:
    img = o._fast_grab()
    check("_fast_grab() returns None on a missed grab",
          img is None, f"got {img!r}")
    check("_fast_grab(): pyautogui.screenshot NOT called",
          guard.calls == 0, f"{guard.calls} call(s)")

_scratch_dir = tempfile.mkdtemp(prefix="baseball_test_screenshot_log_")
try:
    o._screenshot_run_dir = _scratch_dir

    class _FakeStopEvent:
        """Runs the loop body exactly `n` times, then stops it -- a real
        threading.Event with is_set() pre-armed would need a second thread."""

        def __init__(self, n):
            self._left = n

        def is_set(self):
            self._left -= 1
            return self._left < 0

        def wait(self, timeout):
            pass

    with _PyAutoGUIGuard() as guard:
        o._screenshot_logger_loop(_FakeStopEvent(3))
        written = [f for f in os.listdir(_scratch_dir) if f.endswith(".jpg")]
        check("_screenshot_logger_loop() writes NOTHING on a missed grab",
              written == [], f"found {written}")
        check("_screenshot_logger_loop(): pyautogui.screenshot NOT called",
              guard.calls == 0, f"{guard.calls} call(s)")
finally:
    shutil.rmtree(_scratch_dir, ignore_errors=True)


# ============================================================================
# 2. CALLERS: must survive a None capture -- no crash, no fallback, no
#    decision made on a missing frame.
# ============================================================================

# --- _settled_lock_grid(): used to crash on detect_ban_grid_locked(None) ---
img, grid = o._settled_lock_grid(tries=2)
check("_settled_lock_grid() survives a persistently missed grab",
      img is None and grid is None, f"got img={img!r} grid={grid!r}")

# --- capture_screenshot_b64() / capture_state_images_b64(): used to crash on
#     img.convert(...) / img.width -----------------------------------------
b64 = o.capture_screenshot_b64()
check("capture_screenshot_b64() returns None rather than crashing",
      b64 is None, f"got {b64!r}")

state_imgs = o.capture_state_images_b64()
check("capture_state_images_b64() returns [] rather than crashing",
      state_imgs == [], f"got {state_imgs!r}")

# --- _center_card_edge_fraction(): used to crash on img.size --------------
frac = o._center_card_edge_fraction()
check("_center_card_edge_fraction() degrades to 0.0 (reads as 'no cards seen')",
      frac == 0.0, f"got {frac!r}")

# --- _pause_menu_open(): documented to NEVER return None; used to crash on
#     is_pause_screen(None) -- stub the settle wait so the test does not
#     block for real seconds on a poll that can never succeed here ----------
_real_settle = o.wait_for_screen_to_settle
o.wait_for_screen_to_settle = lambda *a, **k: 0.0
try:
    open_ = o._pause_menu_open()
    check("_pause_menu_open() survives a missed grab and stays a bool",
          open_ is False, f"got {open_!r}")
finally:
    o.wait_for_screen_to_settle = _real_settle

# --- ban_cursor_absolute() / ban_x_on() / ban_x_cells(): used to crash on
#     ban_grid.find_card_rows(None) ----------------------------------------
check("ban_cursor_absolute() refuses (None) rather than crashing",
      o.ban_cursor_absolute() is None)
check("ban_x_on() refuses (False) rather than crashing",
      o.ban_x_on((0, 0)) is False)
check("ban_x_cells() refuses (None) rather than crashing",
      o.ban_x_cells() is None)

# --- _grab_settle_regions(): the shared helper behind wait_for_screen_to_settle
#     and screen_is_moving. It raises a clear, named RuntimeError -- never the
#     cryptic AttributeError a bare img.size would have produced -- and every
#     caller below is what actually catches it. ------------------------------
try:
    o._grab_settle_regions(("hand",))
    check("_grab_settle_regions() raises (not silently wrong) on a missed grab",
          False, "did not raise")
except RuntimeError as e:
    check("_grab_settle_regions() raises a clear RuntimeError on a missed grab",
          "no frame available" in str(e), f"got: {e}")
except Exception as e:
    check("_grab_settle_regions() raises RuntimeError specifically (not "
          f"{type(e).__name__})", False, str(e))

# --- wait_for_screen_to_settle(): must return (not hang, not crash) even
#     though every poll inside it fails to capture -------------------------
waited = o.wait_for_screen_to_settle(max_wait=0.3, poll_interval=0.05)
check("wait_for_screen_to_settle() returns normally on all-missed polls "
      "(never crashes, matches its own documented timeout behaviour)",
      isinstance(waited, float), f"got {waited!r}")

# --- screen_is_moving(): "doing nothing is a legitimate action" -- on a
#     missed grab it must report True (assume motion / do not act on a frame
#     it never saw), never crash and never a confident False ---------------
moving = o.screen_is_moving(settle_pause=0.01)
check("screen_is_moving() reports True (assume motion) rather than crashing "
      "or guessing False on a missed grab",
      moving is True, f"got {moving!r}")

# --- stash_hand_baseline(None): the $50-path call site now catches the
#     capture failure and stashes None, which wait_for_hand_deal already
#     documents as a supported value -----------------------------------
o.stash_hand_baseline(None)
check("stash_hand_baseline(None) does not raise and is poppable",
      o.pop_hand_baseline() is None)


# ============================================================================
# 3. ANTI-VACUITY -- restore the real grab and confirm the SAME functions
#    behave normally (this file did not just break every reader).
# ============================================================================
game_capture.grab = _real_grab

from PIL import Image as _PILImage
_stub_frame = _PILImage.new("RGB", (1920, 1080), (60, 60, 60))
game_capture.grab = lambda *a, **k: _stub_frame

with _PyAutoGUIGuard() as guard:
    img = o.capture_screenshot_image()
    check("control: capture_screenshot_image() returns a real frame when "
          "the grab succeeds", img is not None and img.size[0] > 0)
    check("control: pyautogui.screenshot still not called on a healthy grab",
          guard.calls == 0)

game_capture.grab = _real_grab


print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
