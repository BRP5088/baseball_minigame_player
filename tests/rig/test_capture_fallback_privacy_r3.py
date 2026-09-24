"""PRIVACY, round 3: skeptic findings 1, 2, 4, 5 on 28983d2, and mutants K1,
K2, K3, K6 which round 2's skeptic found survived (correct but UNTESTED
code). Each fixture-based check here FAILS on 28983d2 (or on the matching
mutant from agent_progress/privacy-capture-fallback-r3/r2-skeptic/mutants.py)
and PASSES on the r3 fix.

The rule this whole file pins: a missed frame = no frame this poll, look
again. It must never cause a button press or a decision, and every retry
must stay bounded.
"""
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import time as _time_mod

from PIL import Image

import compass
import game_capture
import input_controller
import orchestrator as o
import pause_menu

FAILS = []


def check(label, cond, detail=""):
    if cond:
        print(f"  PASS {label}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL {label}" + (f"  ({detail})" if detail else ""))
        FAILS.append(label)


# ============================================================================
# VIRTUAL CLOCK -- installed/removed per-block so only the loops that need
# exact, instant timing pay for it. time.sleep advances a fake time.time;
# nothing actually waits. Same technique as agent_progress/
# privacy-capture-fallback-r3/r2-skeptic/none_probe.py.
# ============================================================================
_real_sleep = _time_mod.sleep
_real_time = _time_mod.time


def _install_virtual_clock(start=1_800_000_000.0):
    clock = [start]

    def _sleep(s):
        clock[0] += max(0.0, float(s))

    def _time():
        return clock[0]

    _time_mod.sleep = _sleep
    _time_mod.time = _time
    return clock


def _restore_clock():
    _time_mod.sleep = _real_sleep
    _time_mod.time = _real_time


# ============================================================================
# FINDING 1 / "_ban_scroll_to_top presses on None": a missing frame
# (capture_screenshot_image() is None) must press NOTHING and stay bounded.
# read_ban_scroll_level is left UNSTUBBED (the REAL function) so a regression
# that calls it with None -- the exact 28983d2 bug: img.size on None raises
# AttributeError, a bare except swallows it, lvl stays None, and the loop
# reads that as "mid-animation, keep pressing" -- shows up here as a press,
# not as a silently-passing stub.
# ============================================================================
_real_capture_img = o.capture_screenshot_image
_real_press = o.press
_real_settle = o.wait_for_screen_to_settle

_ban_presses = []
_ban_capture_calls = [0]

try:
    o.capture_screenshot_image = lambda: (_ban_capture_calls.__setitem__(0, _ban_capture_calls[0] + 1) or None)
    o.press = lambda action, *a, **k: _ban_presses.append(action)
    o.wait_for_screen_to_settle = lambda *a, **k: 0.0

    result = o._ban_scroll_to_top()

    check("finding 1: a SUSTAINED missing frame must press NOTHING -- "
          "28983d2 pressed move_up up to 20 times per call (40 per "
          "read_full_ban_collection scan) because AttributeError on "
          "img.size was swallowed and read as 'mid-animation'",
          len(_ban_presses) == 0, f"presses={_ban_presses!r}")
    check("finding 1: a sustained-blind _ban_scroll_to_top gives up and "
          "reports 'could not verify' (False, None) rather than exhausting "
          "the whole press budget into a screen it cannot see",
          result == (False, None), f"got {result!r}")
    check("finding 1: the blind retry budget is BOUNDED (capture attempted "
          "BAN_SCROLL_BLIND_TRIES times, not spun forever and not given "
          "only one try)",
          _ban_capture_calls[0] == o.BAN_SCROLL_BLIND_TRIES,
          f"capture called {_ban_capture_calls[0]} time(s), expected "
          f"{o.BAN_SCROLL_BLIND_TRIES}")
finally:
    o.capture_screenshot_image = _real_capture_img
    o.press = _real_press
    o.wait_for_screen_to_settle = _real_settle


# ---- control + single-transient-miss: must press exactly as many times as
# a healthy scan, whether or not one grab along the way came back empty.
class _ScrollWorld:
    """A ban grid at `level`, decremented by one on every move_up press --
    same shape as the live rig (six move_up presses took a level-3 grid to
    0, per _ban_scroll_to_top's own docstring)."""

    def __init__(self, level, miss_on=frozenset()):
        self.level = level
        self.miss_on = miss_on          # 1-based capture-call indices to miss
        self.calls = 0
        self.presses = []

    def capture(self):
        self.calls += 1
        if self.calls in self.miss_on:
            return None
        return object()                 # any non-None sentinel; level comes from scroll_level

    def scroll_level(self, img):
        return self.level, 500

    def press(self, action, *a, **k):
        self.presses.append(action)
        if action == "move_up":
            self.level = max(0, self.level - 1)

    def settle(self, *a, **k):
        return 0.0


def _run_scroll_world(world):
    o.capture_screenshot_image = world.capture
    o.read_ban_scroll_level = world.scroll_level
    o.press = world.press
    o.wait_for_screen_to_settle = world.settle
    return o._ban_scroll_to_top()


_real_scroll_level = o.read_ban_scroll_level
try:
    control = _ScrollWorld(level=3)
    control_result = _run_scroll_world(control)

    miss1 = _ScrollWorld(level=3, miss_on={1})
    miss1_result = _run_scroll_world(miss1)

    check("CONTROL: a healthy scan reaches the top and presses exactly the "
          "number of move_up presses the starting level needs",
          control_result == (True, 0) and len(control.presses) == 3,
          f"result={control_result!r} presses={control.presses!r}")
    check("finding 1: a SINGLE transient miss (capture returns None once, "
          "then real frames) costs ZERO extra presses versus the control -- "
          "it is a missed poll, not a reason to press",
          miss1_result == (True, 0) and len(miss1.presses) == len(control.presses),
          f"result={miss1_result!r} presses={miss1.presses!r} vs control "
          f"{control.presses!r}")
finally:
    o.capture_screenshot_image = _real_capture_img
    o.read_ban_scroll_level = _real_scroll_level
    o.press = _real_press
    o.wait_for_screen_to_settle = _real_settle


# ============================================================================
# K3: game_capture.grab() must return None on a capture failure, never the
# STALE previous frame -- a stale frame looks exactly like a fresh one to
# every settle/diff check downstream, and the whole point of returning None
# is "no frame this poll, look again", not "here is an old one".
# ============================================================================
_real_fast_capture = compass.fast_capture
_calls_k3 = {"i": 0}


def _fc_k3():
    _calls_k3["i"] += 1
    if _calls_k3["i"] == 1:
        return Image.new("RGB", (1920, 1080), (10, 20, 30))
    raise RuntimeError("mss died (K3 probe)")


try:
    compass.fast_capture = _fc_k3
    first = game_capture.grab()
    second = game_capture.grab()
    check("K3: game_capture.grab() must not return a STALE previous frame "
          "when a later capture raises",
          second is None, f"first={first!r} second={second!r}")
finally:
    compass.fast_capture = _real_fast_capture


# ============================================================================
# K1: _close_pause_menu_verified must never treat a BLIND confirmation read
# (_pause_menu_open() returns None, "cannot tell") as "closed". Only a fresh
# read that comes back False (confirmed not open) may cancel the ok
# press_verified already reported.
# ============================================================================
_real_press_verified = input_controller.press_verified
_real_pause_open = o._pause_menu_open

try:
    input_controller.press_verified = lambda action, observe, tries=None, settle=None, log=None: (True, 1)

    o._pause_menu_open = lambda: None   # blind confirmation
    ok_blind, presses_blind = o._close_pause_menu_verified(log=lambda *a: None)
    check("K1: a BLIND confirmation read must never be treated as 'closed' "
          "(28983d2's own docstring: 'never turn cannot tell into closed')",
          ok_blind is False, f"got ok={ok_blind!r} presses={presses_blind!r}")

    o._pause_menu_open = lambda: False  # confirmed NOT open
    ok_closed, presses_closed = o._close_pause_menu_verified(log=lambda *a: None)
    check("CONTROL: a confirmed-closed read (False, a real frame) reports ok",
          ok_closed is True, f"got ok={ok_closed!r} presses={presses_closed!r}")

    o._pause_menu_open = lambda: True   # confirmed STILL open
    ok_open, presses_open = o._close_pause_menu_verified(log=lambda *a: None)
    check("CONTROL: a confirmed-still-open read must not report ok",
          ok_open is False, f"got ok={ok_open!r} presses={presses_open!r}")
finally:
    input_controller.press_verified = _real_press_verified
    o._pause_menu_open = _real_pause_open


# ============================================================================
# "balance presses on a blind attempt" (finding 2): a blind period that
# outlasts one WHOLE attempt (the initial grab plus both of its read-retries)
# must not cost the NEXT attempt a press -- there is still zero evidence the
# first press needs repeating, and repeating it blind can close a menu that
# actually opened. Round 2's own finding-6 test only covered a single,
# immediately-recovered miss; this is the sustained case the r3 skeptic
# refuted round 2 on.
# ============================================================================
_real_fast_grab_bal = o._fast_grab
_real_settle_bal = o.wait_for_screen_to_settle
_real_press_bal = o.press
_real_is_pause = pause_menu.is_pause_screen
_real_read_money = pause_menu.read_money
_real_close_verified = o._close_pause_menu_verified

_open_frame = Image.new("RGB", (1920, 1080), (200, 200, 200))

# --- sustained blind through attempt 1's whole read, then recovers ---------
_presses_a = []
_grab_calls_a = [0]


def _grab_stub_a():
    _grab_calls_a[0] += 1
    # Attempt 1's initial grab (#1) and both of its read-retries (#2, #3) all
    # miss -- a run that outlasts one entire attempt. Attempt 2 onward: real,
    # OPEN frames.
    if _grab_calls_a[0] <= 3:
        return None
    return _open_frame


try:
    o._fast_grab = _grab_stub_a
    o.wait_for_screen_to_settle = lambda *a, **k: 0.0
    o.press = lambda action, *a, **k: _presses_a.append(action)
    pause_menu.is_pause_screen = lambda img: img is _open_frame
    pause_menu.read_money = lambda img: 246
    o._close_pause_menu_verified = lambda log=None: (True, 0)

    balance_a = o.read_balance_from_pause_menu()

    check("balance presses on a blind attempt: a blind period spanning "
          "attempt 1's ENTIRE read (initial grab + both retries) must not "
          "cost attempt 2 a press -- 28983d2 pressed toggle_pause again on "
          "no evidence (skeptic r2 sweep: 7 presses vs 6 with good frames)",
          _presses_a.count("toggle_pause") == 1,
          f"toggle_pause pressed {_presses_a.count('toggle_pause')} "
          f"time(s): {_presses_a!r}")
    check("read_balance_from_pause_menu() still reads correctly once real "
          "evidence (an open frame) finally arrives",
          balance_a == 246, f"got {balance_a!r}")
finally:
    o._fast_grab = _real_fast_grab_bal
    o.wait_for_screen_to_settle = _real_settle_bal
    o.press = _real_press_bal
    pause_menu.is_pause_screen = _real_is_pause
    pause_menu.read_money = _real_read_money
    o._close_pause_menu_verified = _real_close_verified

# --- NEVER recovers: exactly one press total, then raises, zero more -------
_presses_b = []

try:
    o._fast_grab = lambda: None   # always blind
    o.wait_for_screen_to_settle = lambda *a, **k: 0.0
    o.press = lambda action, *a, **k: _presses_b.append(action)

    raised = False
    try:
        o.read_balance_from_pause_menu()
    except RuntimeError:
        raised = True

    check("balance presses on a blind attempt: a SUSTAINED blind period "
          "(never a single real frame) presses toggle_pause exactly ONCE "
          "total -- the one unavoidable opening press -- then raises rather "
          "than pressing again with no evidence, ever",
          raised and _presses_b.count("toggle_pause") == 1,
          f"raised={raised} presses={_presses_b!r}")
finally:
    o._fast_grab = _real_fast_grab_bal
    o.wait_for_screen_to_settle = _real_settle_bal
    o.press = _real_press_bal


# ============================================================================
# K2 + "the deal outage ends the wait early" + K6: wait_for_hand_deal's
# consecutive-capture-fail counter must (a) RESET on a successful read (K2),
# so fails spread across a run are never mistaken for one continuous outage,
# and (b) an outage must count against the SAME max_wait budget as
# everything else, so the wait never ends before max_wait purely because of
# a run of misses (finding 4) -- and only a run that is STILL failing when
# the budget runs out, of at least _DEAL_CAPTURE_FAIL_TRIES, is reported as
# "error" rather than "timeout" (K6: that threshold must be 3, not 1).
#
# Virtual clock: exact iteration counts, no real-time tolerance needed.
# ============================================================================
_stub_gray = Image.new("L", (200, 60), 128)
_real_grs = o._grab_settle_regions
_real_fast_grab_deal = o._fast_grab
_real_mean_abs_delta = o._mean_abs_delta


def _deal_rows():
    return [row for row in o._OBSERVATIONS if row.get("event") == "deal_timing"]


def _run_deal(fail_indices, max_wait, poll_interval):
    calls = {"i": 0}

    def _grs(region_names):
        calls["i"] += 1
        if calls["i"] in fail_indices:
            raise RuntimeError(f"simulated miss #{calls['i']}")
        return {n: _stub_gray for n in region_names}

    o._grab_settle_regions = _grs
    o._fast_grab = lambda: None
    o._mean_abs_delta = lambda a, b: 0.0   # never "seen" -- isolates the
                                            # capture-fail classification from
                                            # the motion-release path
    o._OBSERVATIONS.clear()
    clock = _install_virtual_clock()
    try:
        out = o.wait_for_hand_deal(max_wait=max_wait, poll_interval=poll_interval,
                                    baseline=_stub_gray)
    finally:
        _restore_clock()
    rows = _deal_rows()
    return out, rows, calls["i"]


try:
    # K2: fails at calls 1, 2, and 10 -- three fails total, but NEVER three
    # in a row (a success always intervenes), and the run ends on a long
    # stretch of successes. A counter that does not reset stays >= 3 from
    # call 10 onward and wrongly reports "error".
    out_k2, rows_k2, n_k2 = _run_deal(fail_indices={1, 2, 10}, max_wait=5.0,
                                      poll_interval=0.15)
    check("K2 setup: enough polls ran to exercise the pattern (fails at "
          "1, 2, 10, all later calls succeed)",
          n_k2 > 10, f"only {n_k2} call(s)")
    check("K2: the consecutive-capture-fail counter RESETS on a successful "
          "read -- 3 fails spread across the run (never 3 in a row) must "
          "NOT be reported as the capture being gone",
          rows_k2 and rows_k2[-1].get("outcome") != "error",
          f"rows={rows_k2!r}")

    # "the deal outage ends the wait early": an 8-poll outage early in the
    # run (same shape as the r2 skeptic's measurement), followed by
    # recovery and no real motion. The wait must run its FULL max_wait
    # budget, not stop at ~8 poll_intervals.
    MAX_WAIT_OUTAGE = 3.0
    POLL_OUTAGE = 0.15
    out_outage, rows_outage, n_outage = _run_deal(
        fail_indices=set(range(1, 9)), max_wait=MAX_WAIT_OUTAGE,
        poll_interval=POLL_OUTAGE)
    check("the deal outage ends the wait early: an 8-poll outage that later "
          "recovers must not end the wait early -- 28983d2 released at "
          "~8*poll_interval (~1.2s here) against a 3.0s budget",
          rows_outage and rows_outage[-1].get("waited", 0) >= MAX_WAIT_OUTAGE - POLL_OUTAGE,
          f"rows={rows_outage!r}")
    check("...and an outage that RECOVERS is not reported as 'error' -- "
          "the capture came back, so this is a normal timeout/no-motion row",
          rows_outage and rows_outage[-1].get("outcome") != "error",
          f"rows={rows_outage!r}")

    # K6: the classification threshold must be 3, not 1. Poll_interval=0.1,
    # max_wait=0.55 -> exactly 6 iterations with the virtual clock (elapsed
    # checked before each sleep: 0,0.1,..,0.5 all < 0.55; after the 6th
    # sleep elapsed=0.6 >= 0.55, loop stops). Fail only the LAST TWO calls
    # (5, 6) -- a trailing run of 2, below the real threshold of 3.
    out_k6, rows_k6, n_k6 = _run_deal(fail_indices={5, 6}, max_wait=0.55,
                                      poll_interval=0.1)
    check("K6 setup: exactly 6 iterations ran (virtual clock, deterministic)",
          n_k6 == 6, f"got {n_k6} call(s)")
    check("K6: a trailing run of 2 consecutive fails (below "
          "_DEAL_CAPTURE_FAIL_TRIES=3) must NOT be classified as 'error' -- "
          "only >=3 in a row, still failing when the budget runs out, means "
          "the capture is genuinely gone",
          rows_k6 and rows_k6[-1].get("outcome") != "error",
          f"rows={rows_k6!r}")

    # CONTROL for K6's threshold: a trailing run of >=3 (indices 4,5,6 of 6)
    # is still correctly reported as "error" -- the fix does not just widen
    # the window into never detecting a genuine outage.
    out_k6b, rows_k6b, n_k6b = _run_deal(fail_indices={4, 5, 6}, max_wait=0.55,
                                         poll_interval=0.1)
    check("CONTROL: a trailing run of >= 3 consecutive fails through the "
          "end of the budget IS still reported as 'error'",
          rows_k6b and rows_k6b[-1].get("outcome") == "error",
          f"rows={rows_k6b!r}")
finally:
    o._grab_settle_regions = _real_grs
    o._fast_grab = _real_fast_grab_deal
    o._mean_abs_delta = _real_mean_abs_delta
    o._OBSERVATIONS.clear()


print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
