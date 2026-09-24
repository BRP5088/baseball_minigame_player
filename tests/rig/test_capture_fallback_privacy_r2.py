"""PRIVACY, round 2: skeptic findings 2, 4, 5, 6 on 2512b49. OFFLINE.

Round 1 (2512b49) removed the three orchestrator.py desktop-screenshot
fallbacks but left several callers deciding, caching, or pressing on a
missed frame instead of treating it as "no frame this poll, look again".
An Opus skeptic found five such sites (see agent_progress/
privacy-capture-fallback-r2/skeptic-progress.md); this file pins the four
that need new fixtures beyond what tests/rig/test_no_desktop_capture_fallback.py
already covers (findings 1, 3, 7 there; finding 3 also gets a press_verified
regression test there). Each check here FAILS on 2512b49 and PASSES on the r2
fix.
"""
import glob
import os
import sys
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PIL import Image

import orchestrator as o

FAILS = []


def check(label, cond, detail=""):
    if cond:
        print(f"  PASS {label}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL {label}" + (f"  ({detail})" if detail else ""))
        FAILS.append(label)


# ============================================================================
# FINDING 2: read_full_ban_collection must not CACHE a scan that ended on a
# run of missed frames -- a fragment cached is served to every later ban
# screen in the process (OPEN-23's shape), zero captures.
# ============================================================================
_BAN_FIXTURE_DIR = os.path.join(_ROOT, "test_fixtures", "ban_scan")
_BAN_FRAMES = sorted(glob.glob(os.path.join(_BAN_FIXTURE_DIR, "*.jpg")))
if not _BAN_FRAMES:
    raise SystemExit(
        f"no reference frames in {_BAN_FIXTURE_DIR} -- finding-2 coverage "
        "would be silently disabled; restore the fixtures")
_REAL_BAN_FRAME = Image.open(_BAN_FRAMES[0]).convert("RGB")

_REAL_LOCK_FN = o.detect_ban_grid_locked
_LOCK_CACHE = {}


class _BanScanRig:
    """Same faking technique as tests/minigame/test_ban_scan.py's Rig, not a
    modification of that file: every boundary read_full_ban_collection
    touches is patched. `miss_after` makes capture_screenshot_image() return
    a REAL frame for that many calls, then None forever -- simulating the
    game window going away mid-scan, the way a Space-switch or an occluding
    window does live.
    """

    def __init__(self, miss_after):
        self.miss_after = miss_after
        self.captures = 0
        self.presses = []
        self.downs = 0

    def _press(self, k, *a, **kw):
        self.presses.append(k)
        if k == "move_down":
            self.downs += 1
        elif k == "move_up":
            self.downs = max(0, self.downs - 1)

    def __enter__(self):
        self.saved = {}

        def cap(*a, **k):
            self.captures += 1
            if self.captures <= self.miss_after:
                return _REAL_BAN_FRAME
            return None   # simulated window loss -- never a desktop fallback

        def scroll_level(img):
            # Mirror the production formula (top_row = max(0, presses - 1)):
            # a HEALTHY scrollbar, so the scan measures the no-frame break
            # in isolation rather than tripping the (separate, pre-existing)
            # scroll-desync branch.
            return max(0, self.downs - 1), 500

        def lock(img):
            key = id(img)
            if key not in _LOCK_CACHE:
                _LOCK_CACHE[key] = _REAL_LOCK_FN(img)
            return _LOCK_CACHE[key]

        def vision(*a, **k):
            raise AssertionError("vision called on a trust_roster=True path")

        patches = {
            "read_ban_scroll_level": scroll_level,
            "detect_ban_grid_locked": lock,
            "capture_screenshot_image": cap,
            "read_ban_row_cards": vision,
            "ocr_ban_card_name": lambda c: None,
            "press": self._press,
            "wait_for_screen_to_settle": lambda *a, **k: True,
        }
        for n, f in patches.items():
            if hasattr(o, n):
                self.saved[n] = getattr(o, n)
                setattr(o, n, f)
        o._cached_ban_collection = None
        return self

    def __exit__(self, *a):
        for n, f in self.saved.items():
            setattr(o, n, f)
        o._cached_ban_collection = None
        return False


# Enough real batches to clear the >= 3 floor well before the misses start
# (test_ban_scan.py's own healthy control clears it by max_presses=6 on this
# same repeating-frame technique): first batch costs 2 captures
# (_settled_lock_grid confirms twice on an unchanging frame), each later
# batch costs 1. 5 real captures -> 4 batches -> presses_so_far reaches 6
# before the first miss.
with _BanScanRig(miss_after=5) as rig:
    partial = o.read_full_ban_collection(max_presses=40, use_cache=True,
                                         trust_roster=True)
    cached_after = o._cached_ban_collection

check("finding 2 fixture: the scan actually collected >= 3 cards before the "
      "misses began (otherwise this proves nothing about the no-frame break)",
      len(partial) >= 3, f"got {len(partial)} card(s)")
check("finding 2: a scan that ends on a run of missed frames "
      "(_consecutive_no_frame >= BAN_CURSOR_PROBE_TRIES) is NOT cached -- a "
      "fragment cached here is served to every later ban screen in the "
      "process with zero further captures",
      cached_after is None,
      f"{len(partial)}-card fragment was cached anyway")

# Control: the SAME scan with no misses at all (miss_after large) must still
# cache -- otherwise this rule reads exactly like a disabled cache (10.1).
with _BanScanRig(miss_after=10_000) as rig_healthy:
    healthy = o.read_full_ban_collection(max_presses=8, use_cache=True,
                                         trust_roster=True)
    cached_healthy = o._cached_ban_collection
check("CONTROL: a healthy scan (no missed frames) still caches",
      len(healthy) >= 3 and cached_healthy is not None,
      f"{len(healthy)} cards, cached={cached_healthy is not None}")


# ============================================================================
# FINDING 5: _match_start_screen must answer None (blind), never "other", on
# a missed frame. Live effect on 2512b49: with the guard inside
# read_ban_counter only, a missed grab read as "other" -- a REAL change from
# press_verified's "prompt" baseline -- and start_match's key doubles as
# confirm_discard, so press_verified sent up to PRESS_VERIFY_TRIES Squares
# into a match already debited $50.
# ============================================================================
_real_fast_grab_o = o._fast_grab
try:
    o._fast_grab = lambda: None
    screen = o._match_start_screen()
    check("_match_start_screen() returns None (not \"other\") on a missed "
          "frame -- \"can't see\", never a decision",
          screen is None, f"got {screen!r}")
finally:
    o._fast_grab = _real_fast_grab_o

# Control: a real-but-irrelevant frame (neither a ban screen nor the dealer
# prompt) must still read as "other" -- the None-check must not swallow the
# ordinary case.
_blank = Image.new("RGB", (1920, 1080), (30, 90, 30))
try:
    o._fast_grab = lambda: _blank
    screen_other = o._match_start_screen()
    check("CONTROL: _match_start_screen() still reads \"other\" on a real, "
          "irrelevant frame",
          screen_other == "other", f"got {screen_other!r}")
finally:
    o._fast_grab = _real_fast_grab_o


# ============================================================================
# FINDING 6: read_balance_from_pause_menu's open-verification loop must
# retry the READ (not the PRESS) on a missed frame. Pressing again on a
# missed frame can double-toggle a menu that the FIRST press actually opened
# -- the toggle landed, we just could not see it, and a second blind press
# closes it again.
# ============================================================================
import pause_menu

_stub_open_frame = Image.new("RGB", (1920, 1080), (200, 200, 200))
_real_is_pause_screen = pause_menu.is_pause_screen
_real_read_money = pause_menu.read_money
# `press` is bound into orchestrator's OWN namespace at import time
# (`from input_controller import ... press ...`), so read_balance_from_
# pause_menu's bare `press("toggle_pause")` call resolves via o.press, not
# input_controller.press -- patch the name this function actually looks up.
_real_o_press = o.press
_real_close_verified = o._close_pause_menu_verified
_real_settle = o.wait_for_screen_to_settle

_grab_calls = [0]


def _grab_stub():
    _grab_calls[0] += 1
    # Call 1: the toggle landed but the grab MISSED it (transient window
    # lookup failure). Every call after that: a real, open pause menu frame.
    if _grab_calls[0] == 1:
        return None
    return _stub_open_frame


_presses = []

try:
    o._fast_grab = _grab_stub
    o.wait_for_screen_to_settle = lambda *a, **k: 0.0
    o.press = lambda action, *a, **k: _presses.append(action)
    pause_menu.is_pause_screen = lambda img: img is _stub_open_frame
    pause_menu.read_money = lambda img: 246
    o._close_pause_menu_verified = lambda log=None: (True, 0)

    balance = o.read_balance_from_pause_menu()

    check("read_balance_from_pause_menu(): a single missed frame right "
          "after the toggle does NOT cost an extra toggle_pause press -- "
          "pressing again here can double-toggle a menu that actually "
          "opened (found in review, r2)",
          _presses.count("toggle_pause") == 1,
          f"toggle_pause pressed {_presses.count('toggle_pause')} time(s): "
          f"{_presses!r}")
    check("read_balance_from_pause_menu() still reads the balance correctly "
          "once the menu is confirmed open",
          balance == 246, f"got {balance!r}")
finally:
    o._fast_grab = _real_fast_grab_o
    o.wait_for_screen_to_settle = _real_settle
    o.press = _real_o_press
    pause_menu.is_pause_screen = _real_is_pause_screen
    pause_menu.read_money = _real_read_money
    o._close_pause_menu_verified = _real_close_verified


# ============================================================================
# FINDING 4: wait_for_hand_deal must retry a missed BASELINE grab within the
# same max_wait budget, not release almost immediately. On 2512b49 this
# baseline = None crashed _mean_abs_delta(None, cur) on the very first poll,
# and the broad `except Exception: return False` turned that crash into an
# early release at ~one poll_interval instead of the full wait.
# ============================================================================
_stub_hand_gray = Image.new("L", (200, 60), 128)
_grs_calls = [0]


def _grs_stub(region_names):
    _grs_calls[0] += 1
    if _grs_calls[0] == 1:
        raise RuntimeError("_grab_settle_regions: no frame available (game window not found)")
    return {n: _stub_hand_gray for n in region_names}


_real_grs = o._grab_settle_regions
_real_fast_grab_o2 = o._fast_grab
_MAX_WAIT = 0.6
try:
    o._grab_settle_regions = _grs_stub
    o._fast_grab = lambda: Image.new("RGB", (1920, 1080), (50, 50, 50))
    t0 = time.time()
    result = o.wait_for_hand_deal(max_wait=_MAX_WAIT, poll_interval=0.05, baseline=None)
    elapsed = time.time() - t0
finally:
    o._grab_settle_regions = _real_grs
    o._fast_grab = _real_fast_grab_o2

check("wait_for_hand_deal(): a missed BASELINE grab retries within the "
      "SAME max_wait budget rather than releasing almost immediately "
      "(found in review, r2: used to end the wait after ~0.16s instead of "
      "the full budget)",
      elapsed >= _MAX_WAIT * 0.7,
      f"elapsed={elapsed:.3f}s of max_wait={_MAX_WAIT}s")
check("wait_for_hand_deal() with a missed baseline and no real motion times "
      "out (False) rather than crashing",
      result is False, f"got {result!r}")


print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
