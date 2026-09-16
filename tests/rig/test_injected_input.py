"""press() must reach the console without needing chiaki's keyboard focus.

Buttons and sticks travel different routes. Sticks go through our injector (a
FIFO chiaki reads); buttons went through chiaki's Qt keyboard mapping, which
requires its window to hold OS keyboard focus. On 2026-09-01 that path died
after a chiaki restart while video and heartbeats stayed healthy —
reset_env's probe reported "NO input is reaching the game" at the same moment
FIFO writes produced 20+ screen deltas.

Bits were measured on a round-result overlay whose only action was CLOSE:
cross 20.51, circle 20.55, square 21.96, against an idle baseline of 1.70.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import tempfile
import types

# THE FIFO GOES TO A SCRATCH FILE, ALWAYS, AND BEFORE ANYTHING IS IMPORTED.
# The lockout check below deliberately CALLS the injection path. If that
# lockout is ever removed, the call reaches analog_replay.send() for real —
# measured 2026-09-03, it wrote "buttons 1" / "buttons 0", which on this
# machine is a live Cross press on the console. The test that guards the
# console must not be the thing that drives it while reporting the failure.
# analog_replay reads this at ITS import time, which happens inside
# _inject_press, so setting it here is early enough.
# PID-SUFFIXED — see test_analog_replay.py. Two copies of this file run
# concurrently whenever test_no_side_effects.py re-runs the suite.
_SINK = os.path.join(tempfile.gettempdir(),
                     f"baseball_test_fifo_sink_{os.getpid()}.txt")
os.environ["CHIAKI_INJECT_INPUT"] = _SINK

# START FROM A CLEAN SINK. This path is shared and PERSISTS between runs, so
# anything an earlier run left here would be read below as a leak from THIS one
# and fail the test on correct code — measured 2026-09-03, a stale
# "right_x 26214" from a mutation experiment failed the unmutated tree twice.
# A leak detector that reports yesterday's leak is worse than none: it trains
# the reader to ignore it.
try:
    os.remove(_SINK)
except FileNotFoundError:
    pass

_os.environ.setdefault("BASEBALL_TEST_RUN", "1")   # the suite exports it; this file
# manipulates the flag itself below, so it must start from the same state standalone.
import input_controller as ic

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# --- THE SAFETY PROPERTY FIRST -------------------------------------------
# This path sits ABOVE can_use_background_input() in press(), so it needs its
# own test lockout. Without it every ./run_tests.sh would drive the real game.
os.environ["BASEBALL_TEST_RUN"] = "1"

# PROBE A STICK, NOT A BUTTON. Buttons are refused a few lines further down by
# INJECT_BUTTONS = False, so `_inject_press("cross") is False` passes whether
# or not the test lockout exists — measured 2026-09-03, deleting the lockout
# left this whole file GREEN while it was probing cross. A stick is the only
# action that still reaches the FIFO, so it is the only one that can tell the
# lockout from the button gate.
#
# What the stick probe would send with the lockout gone, measured the same day:
#   _inject_press('cross')      -> False   FIFO got ''
#   _inject_press('look_right') -> True    FIFO got 'right_x 26214\nright_x 0\n'
# i.e. a real right-stick camera swing on a live console, from `./run_tests.sh`.
check(ic._inject_press("look_right", 0.05) is False,
      "injected STICK input fired while BASEBALL_TEST_RUN was set — the "
      "offline suite would swing the camera on a live console")
_leaked = open(_SINK).read() if os.path.exists(_SINK) else ""
check(_leaked == "",
      f"the injection path WROTE to the FIFO under BASEBALL_TEST_RUN "
      f"({_leaked!r}) — returning False is not enough, nothing may leave "
      "this process")

# The button path too, so the lockout is pinned for both kinds even if
# INJECT_BUTTONS is ever turned back on.
check(ic._inject_press("cross", 0.05) is False,
      "injected input fired while BASEBALL_TEST_RUN was set — the offline "
      "suite would send real button presses to a live console")
_leaked = open(_SINK).read() if os.path.exists(_SINK) else ""
check(_leaked == "",
      f"the injection path WROTE to the FIFO under BASEBALL_TEST_RUN "
      f"({_leaked!r}) — returning False is not enough, nothing may leave "
      "this process")

# THE SECOND LOCKOUT, in can_use_background_input(). press() tries injection
# first and this next, so both have to be shut. Nothing asserted this one until
# 2026-09-03: removing it let test_input_timing and test_movement post real
# CGEventPostToPid keystrokes into the running chiaki, and seven input tests
# passed while it happened.
#
# The three conditions BELOW the lockout are forced to their permissive values,
# so this cannot pass merely because chiaki is not running on this machine —
# that would make it vacuous on exactly the desks where it is cheapest to run.
_real_pid, _real_bg, _real_plat = ic.chiaki_pid, ic.BACKGROUND_INPUT, sys.platform
ic.chiaki_pid = lambda refresh=False: 424242
ic.BACKGROUND_INPUT = True
sys.platform = "darwin"
try:
    check(ic.can_use_background_input() is False,
          "can_use_background_input() said YES under BASEBALL_TEST_RUN — the "
          "offline suite would post real keystrokes into the live chiaki "
          "process, which is what happened on 2026-09-01")
    check(ic.can_use_background_input("select_card") is False,
          "can_use_background_input('select_card') said YES under "
          "BASEBALL_TEST_RUN — a mapped action must be refused too, not just "
          "the bare call")
finally:
    ic.chiaki_pid, ic.BACKGROUND_INPUT = _real_pid, _real_bg
    sys.platform = _real_plat

del os.environ["BASEBALL_TEST_RUN"]

# --- it sends what it claims, and always releases -------------------------
sent = []
_real_ar = sys.modules.get("analog_replay")
fake = types.ModuleType("analog_replay")
fake.send = lambda lines: sent.extend(lines)
fake.to_axis = lambda v: int(v * 32767)
sys.modules["analog_replay"] = fake

# --- BUTTONS DO NOT TRAVEL OVER THE FIFO ---------------------------------
# Measured 2026-09-03 on the live console: `buttons 4096` (OPTIONS) produced
# NOTHING after 4s, while the keyboard path opened the pause menu in 0.5s. So
# INJECT_BUTTONS ships False, and the load-bearing property is that a button
# DECLINES and writes nothing.
#
# Returning True was the bug it was turned off for: ar.send() succeeds whenever
# the WRITE succeeds, so press() believed the button had been pressed and never
# fell through to the keyboard path that works — a success path and a no-op
# path with identical output, the exact shape catalogued in CLAUDE.md. It
# silently disabled every button in the system: resets, menu navigation, card
# selection, match play.
check(ic.INJECT_BUTTONS is False,
      "INJECT_BUTTONS is on. Buttons over the FIFO were measured DEAD on the "
      "live console (`buttons 4096` did nothing in 4s) while the keyboard path "
      "worked in 0.5s — turning it back on needs a measurement, not an argument")

sent.clear()
check(ic._inject_press("cross", 0.01) is False,
      "a button reported SUCCESS from the FIFO path while INJECT_BUTTONS is "
      "off — press() then believes it was pressed and never falls through to "
      "the keyboard path that actually works")
check(sent == [],
      f"a button wrote {sent!r} to the FIFO while INJECT_BUTTONS is off")

# ...and now the button wiring UNDER the flag, so it is not dead-testable.
# With the flag off, every assertion below passes against a bare `return
# False`, so the measured bits and the release would rot untested until the day
# someone gets buttons working and flips the flag back on. That is the same
# hole `if MERGE_STEPS:` had in graph_walk (mutation-tested 2026-09-03).
_was_buttons = ic.INJECT_BUTTONS
try:
    ic.INJECT_BUTTONS = True
    sent.clear()
    check(ic._inject_press("cross", 0.01) is True,
          "with INJECT_BUTTONS on, cross should be injectable")
    check(sent == ["buttons 1", "buttons 0"],
          f"cross sent {sent!r}; expected press then RELEASE — a button left "
          "held on a live console is worse than a missed press")

    sent.clear()
    ic._inject_press("toggle_pause", 0.01)
    check(sent == ["buttons 4096", "buttons 0"],
          f"toggle_pause sent {sent!r}; OPTIONS is bit 12")
finally:
    ic.INJECT_BUTTONS = _was_buttons
check(ic.INJECT_BUTTONS is False,
      "the button-wiring check above left INJECT_BUTTONS switched on for every "
      "test after it")

# A stick action must move an AXIS, not press a button.
sent.clear()
ic._inject_press("look_right", 0.01)
check(len(sent) == 2 and sent[0].startswith("right_x ") and sent[1] == "right_x 0",
      f"look_right sent {sent!r}; stick directions are axis deflections, and "
      "sending them as buttons would press something unrelated")

# An unmapped action must decline so press() falls back rather than guessing.
sent.clear()
check(ic._inject_press("l2", 0.01) is False,
      "an unmapped action must return False so press() can fall back")
check(sent == [], f"an unmapped action still wrote {sent!r} to the FIFO")

# --- releases even when the hold raises ----------------------------------
sent.clear()
_sleep = ic.time.sleep


def _boom(_):
    raise KeyboardInterrupt


# The release lives below the button gate, so it is only reachable with the
# flag on. Held under the flag rather than skipped: a button left down on a
# live console is the worst outcome this file has.
_was_buttons = ic.INJECT_BUTTONS
ic.time.sleep = _boom
try:
    ic.INJECT_BUTTONS = True
    ic._inject_press("cross", 0.01)
except KeyboardInterrupt:
    pass
finally:
    ic.time.sleep = _sleep
    ic.INJECT_BUTTONS = _was_buttons
check("buttons 0" in sent,
      f"an interrupted press left the button HELD (sent {sent!r}) — this runs "
      "against a live console")

if _real_ar is not None:
    sys.modules["analog_replay"] = _real_ar
else:
    del sys.modules["analog_replay"]

# ---------------------------------------------------------------------------
# analog_replay.send() must refuse ON ITS OWN under BASEBALL_TEST_RUN.
#
# The guard used to live only in input_controller._inject_press, but 15+ call
# sites reach analog_replay directly (walk_steps, brett_walk, route_follow,
# go_to_landmark, and every overnight harness's `finally:` block), so none of
# them were covered. The suite was safe only because no test happened to call
# ar.send() — which is not a guard, it is luck.
#
# BOTH DIRECTIONS are asserted. Checking only "nothing was written" would pass
# if send() were broken, or if the sink path were simply wrong — an empty file
# proves nothing on its own. The flag is deleted at line 121 above, so the
# unguarded write is available here as a positive control.
import analog_replay as _ar

_sink = os.path.join(tempfile.gettempdir(),
                     f"baseball_test_direct_send_{os.getpid()}.txt")
_old_fifo = getattr(_ar, "FIFO", None)


def _send_and_peek():
    """Point analog_replay at a plain file, send, and report what landed."""
    if os.path.exists(_sink):
        os.remove(_sink)
    _ar.FIFO = _sink
    _ar.close_stream()
    _ar.send(["left_x 32767", "left_y -32768"])
    _ar.close_stream()
    if not os.path.exists(_sink):
        return ""
    with open(_sink) as fh:
        return fh.read()


try:
    # POSITIVE CONTROL: with the flag CLEAR the write must actually happen.
    os.environ.pop("BASEBALL_TEST_RUN", None)
    check("left_x 32767" in _send_and_peek(),
          "analog_replay.send() must write when BASEBALL_TEST_RUN is CLEAR — "
          "without this the guard test below would pass on a broken send()")

    # THE GUARD: with the flag SET, nothing at all.
    os.environ["BASEBALL_TEST_RUN"] = "1"
    check(_send_and_peek() == "",
          "analog_replay.send() must write NOTHING under BASEBALL_TEST_RUN")

    if os.path.exists(_sink):
        os.remove(_sink)
    _ar.FIFO = _sink
    _ar.clear()
    _ar.close_stream()
    check(not os.path.exists(_sink) or os.path.getsize(_sink) == 0,
          "analog_replay.clear() must write nothing either")
finally:
    os.environ.pop("BASEBALL_TEST_RUN", None)
    if _old_fifo is not None:
        _ar.FIFO = _old_fifo
    _ar.close_stream()
    if os.path.exists(_sink):
        os.remove(_sink)


if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  injected input: BOTH test lockouts hold and nothing leaves the "
      "process, sends measured bits, treats sticks as axes, declines unmapped "
      "actions, and always releases")
