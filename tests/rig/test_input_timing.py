"""Tests for the input path's focus caching — offline, NO key ever reaches the machine.

WHY THIS EXISTS
---------------
Input execution turned out to be the largest single latency component in the
loop — 2.3s to 8.3s per turn, more than the vision call and the settle gate
combined, and it had never been measured. 304ms of every 754ms press went on
re-focusing an already-focused window (a ~154ms osascript round-trip plus a
150ms settle wait).

The fix caches focus for FOCUS_TTL seconds. That is a real safety trade: if
focus is lost inside the window, keystrokes land on another app. So the cache's
behaviour is pinned here rather than left to inspection.

Triple-guarded: pyautogui's key functions and subprocess.run are both replaced
with recorders BEFORE input_controller is imported, so nothing can reach the
keyboard or spawn osascript even if a test is wrong.
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
import types

# No PERSONAL_ANTHROPIC_API_KEY guard needed here, deliberately: this file
# never imports orchestrator (only input_controller, which has no client), so
# it already runs standalone. Checked, not assumed.

# --- guard 1: a fake pyautogui, installed before the import ----------------
_fake = types.ModuleType("pyautogui")
_fake.keyDown = lambda *a, **k: _KEYS.append(("down", a, k))
_fake.keyUp = lambda *a, **k: _KEYS.append(("up", a, k))
_fake.screenshot = lambda *a, **k: None
_KEYS = []
sys.modules["pyautogui"] = _fake

import input_controller as ic

# --- guard 1b: this file MEASURES the focus+pyautogui path, against the fake above.
# press() refuses that path under BASEBALL_TEST_RUN since 2026-09-13 -- it typed "c"
# (confirm_play) into the frontmost window during a mutation run -- so opt in explicitly.
# Not restored: this module installs a fake pyautogui at import and never uninstalls it
# either, so the process is already committed to being a test process.
ic.FOCUS_PRESS_IN_TESTS = True

# --- guard 2: no subprocess may actually run ------------------------------
_OSASCRIPT = []
ic.subprocess = types.SimpleNamespace(
    run=lambda *a, **k: _OSASCRIPT.append(a[0] if a else None))


# WHAT IS COUNTED, AND WHY IT IS NOT SUBPROCESS CALLS ANY MORE
# ------------------------------------------------------------
# These tests are about focus ECONOMY: how often focus is requested versus
# reused from cache. Counting osascript invocations was a proxy for that, and
# the proxy broke twice — once on Windows, where the focus path does not use
# subprocess at all, and once when raising a real window had to be disabled
# during tests, because doing it for real pulled the user out of their work
# mid-suite with the game running.
#
# ic._focus_calls increments on every genuine focus request regardless of how
# (or whether) it is delivered, so it measures the property directly instead of
# through something that keeps turning out not to track it.
class _FocusCounter:
    def clear(self):
        ic._focus_calls = 0

    def __len__(self):
        return ic._focus_calls

    def append(self, _cmd):
        # The stubbed subprocess still funnels here. It is deliberately a
        # no-op: the count now comes from ic._focus_calls, and double-counting
        # would make a single focus request look like two.
        pass


_OSASCRIPT = _FocusCounter()

# --- guard 3: no real sleeping, and a clock the test controls -------------
_NOW = [1000.0]
ic.time = types.SimpleNamespace(
    sleep=lambda n: _NOW.__setitem__(0, _NOW[0] + n),
    monotonic=lambda: _NOW[0],
)

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def reset():
    _OSASCRIPT.clear()
    _KEYS.clear()
    ic._last_focus_at = 0.0


# The tests need a mapped key; use whatever the real keymap already has.
ACTION = next(iter(k for k, v in ic.KEYMAP.items() if v))

# --- 1. The first press always focuses ------------------------------------
reset()
ic.press(ACTION)
check(len(_OSASCRIPT) == 1,
      f"first press made {len(_OSASCRIPT)} focus calls, expected 1 — the "
      "very first input must not trust a stale focus")
check(len(_KEYS) == 2, f"expected one keyDown+keyUp, got {_KEYS}")

# --- 2. Presses inside the TTL reuse the focus ----------------------------
# This is the whole optimisation: a navigation sequence is one focus call.
reset()
for _ in range(6):
    ic.press(ACTION, post_delay=0.0)
check(len(_OSASCRIPT) == 1,
      f"6 rapid presses made {len(_OSASCRIPT)} focus calls, expected 1 — "
      "the focus cache is not holding within a sequence")
check(len(_KEYS) == 12,
      f"6 presses should still send 6 key pairs, got {len(_KEYS) // 2}")

# --- 3. A gap longer than the TTL re-focuses ------------------------------
# The cache must not silently trust focus across a turn boundary.
reset()
ic.press(ACTION, post_delay=0.0)
_NOW[0] += ic.FOCUS_TTL + 0.1
ic.press(ACTION, post_delay=0.0)
check(len(_OSASCRIPT) == 2,
      f"a press after a {ic.FOCUS_TTL}s gap made {len(_OSASCRIPT)} osascript "
      "calls, expected 2 — focus is being trusted past its TTL")

# --- 4. post_delay counts toward the TTL ----------------------------------
# A long ACTION_DELAY must not let the cache outlive its own window.
reset()
ic.press(ACTION, post_delay=ic.FOCUS_TTL + 0.1)
ic.press(ACTION, post_delay=0.0)
check(len(_OSASCRIPT) == 2,
      f"post_delay longer than the TTL still reused focus ({len(_OSASCRIPT)} "
      "calls, expected 2) — the delay is not counting toward the TTL")

# --- 5. force=True always re-focuses --------------------------------------
reset()
ic.focus_chiaki_window()
ic.focus_chiaki_window(force=True)
check(len(_OSASCRIPT) == 2,
      f"force=True did not bypass the cache ({len(_OSASCRIPT)} calls, expected 2)")

# --- 6. FOCUS_TTL = 0 restores the old always-focus behaviour -------------
# The documented escape hatch has to actually work.
reset()
_orig = ic.FOCUS_TTL
try:
    ic.FOCUS_TTL = 0
    for _ in range(4):
        ic.press(ACTION, post_delay=0.0)
    check(len(_OSASCRIPT) == 4,
          f"with FOCUS_TTL=0 expected 4 focus calls, got {len(_OSASCRIPT)} — "
          "the documented rollback switch does not work")
finally:
    ic.FOCUS_TTL = _orig

# --- 7. The saving is real ------------------------------------------------
# Guards the point of the change: a worst-case 11-press turn must not pay 11
# osascript round-trips.
reset()
for _ in range(11):
    ic.press(ACTION, post_delay=0.4)
check(len(_OSASCRIPT) <= 4,
      f"an 11-press turn made {len(_OSASCRIPT)} focus calls — at ~154ms "
      "each this is most of the latency the cache exists to remove")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} input-timing failure(s)")

print(f"OK: focus cache — first press focuses, sequences reuse (1 call/6 "
      f"presses), TTL={ic.FOCUS_TTL}s expiry re-focuses, post_delay counts "
      f"toward it, force= and FOCUS_TTL=0 both work, 11-press turn costs "
      f"<=4 focus calls (was 11)")


# --- Adaptive backoff -----------------------------------------------------
# A misfire means the machine is too slow for the current pacing right now, so
# the run slows itself instead of needing someone to notice and restart.
# Capped and floored deliberately: the reveal auditor cannot tell a dropped
# keystroke from a misread reveal, and a noisy signal must not ratchet the
# delay up forever on a vision fault that more waiting cannot fix.

def reset_pacing(delay=0.4, ttl=1.5):
    ic.ACTION_DELAY = delay
    ic.FOCUS_TTL = ttl
    ic._misfires_seen = 0
    ic._backoff_applied = 0.0
    # The give-up state is part of pacing and must reset with it. Without
    # these two, the first block to exhaust BACKOFF_INEFFECTIVE_AFTER latches
    # the backoff off, and every later block quietly measures a mechanism that
    # is no longer running.
    ic._backoffs_applied = 0
    ic._backoff_abandoned = False
    reset()


# 1. A single misfire does NOT change pacing — one bad reveal is not evidence.
reset_pacing()
changed = ic.report_misfire()
check(not changed and ic.ACTION_DELAY == 0.4,
      f"one misfire already changed pacing (delay={ic.ACTION_DELAY}) — the "
      f"floor of {ic.MISFIRES_BEFORE_BACKOFF} is not being respected")

# 2. Reaching the floor backs off and stops trusting cached focus.
reset_pacing()
for _ in range(ic.MISFIRES_BEFORE_BACKOFF):
    ic.report_misfire()
check(abs(ic.ACTION_DELAY - (0.4 + ic.BACKOFF_STEP)) < 1e-9,
      f"expected ACTION_DELAY {0.4 + ic.BACKOFF_STEP}, got {ic.ACTION_DELAY}")
check(ic.FOCUS_TTL == 0.0,
      "focus caching was not disabled after a backoff — if input is being "
      "dropped, the focus assertion is the first thing to stop economising on")

# 3. THE DEFAULT-ARGUMENT TRAP. `post_delay=ACTION_DELAY` in the signature
#    binds once at import, so every later adjustment would be ignored while
#    still printing that it had been applied. Assert the raised value is what
#    a press actually waits.
# Measure the delta between two presses at DIFFERENT pacing, so the fixed
# overheads (focus settle, key hold) cancel out. An earlier version of this
# test compared elapsed against ACTION_DELAY directly and passed with the trap
# still in place: 0.15 settle + 0.05 hold + 0.40 frozen = 0.60s, which clears a
# 0.45s bar for the wrong reason. Backing off to the CEILING makes the two
# cases far enough apart that only the real delay can explain the difference.
reset_pacing()
_before = _NOW[0]
ic.press(ACTION)
_baseline = _NOW[0] - _before

reset_pacing()
# Back off as far as the mechanism will actually go, rather than looping until
# MAX_ACTION_DELAY. It no longer climbs to the ceiling: after
# BACKOFF_INEFFECTIVE_AFTER raises that each got another misfire, it concludes
# waiting is not the remedy and hands the delay back (see report_misfire).
# The old `while ACTION_DELAY < MAX_ACTION_DELAY` spun forever against that,
# which is what hung this file and, through it, the whole suite.
# Bounded, and stops the moment the delay is actually ABOVE the 0.4 baseline:
# the first backoff jumps to BACKOFF_SAFE_DELAY, which IS 0.4, so it takes one
# more to produce a measurable difference — and one more after that would trip
# the give-up and hand the delay back.
for _ in range(ic.MISFIRES_BEFORE_BACKOFF + ic.BACKOFF_INEFFECTIVE_AFTER):
    if ic.ACTION_DELAY > 0.4 or ic._backoff_abandoned:
        break
    ic.report_misfire()
_raised_to = ic.ACTION_DELAY
check(_raised_to > 0.4,
      f"backing off left the delay at {_raised_to}, no higher than the 0.4 "
      "baseline — there is nothing for the timing check below to detect")
_expected_extra = _raised_to - 0.4
_before = _NOW[0]
ic.press(ACTION)
_raised = _NOW[0] - _before
check(abs((_raised - _baseline) - _expected_extra) < 1e-6,
      f"a press took {_raised:.3f}s after backing off to "
      f"{ic.ACTION_DELAY:.2f}s vs {_baseline:.3f}s at 0.40s — a difference of "
      f"{_raised - _baseline:.3f}s, expected {_expected_extra:.3f}s. The raised "
      "delay is NOT reaching press(): `post_delay=ACTION_DELAY` in the "
      "signature binds once at import, so the backoff prints success and "
      "changes nothing.")

# 4. The ceiling holds. Without it a persistent reveal misread would ratchet
#    the delay up until the run was unusable.
reset_pacing()
for _ in range(200):
    ic.report_misfire()
check(ic.ACTION_DELAY <= ic.MAX_ACTION_DELAY,
      f"ACTION_DELAY reached {ic.ACTION_DELAY}, above the "
      f"{ic.MAX_ACTION_DELAY}s ceiling — a misread reveal can now slow the run "
      "without bound")

# 5. The summary reports honestly in both states.
reset_pacing()
check("unchanged" in ic.input_pacing_summary(),
      f"clean run summary should say pacing was unchanged: {ic.input_pacing_summary()}")
for _ in range(ic.MISFIRES_BEFORE_BACKOFF):
    ic.report_misfire()
check("misfire" in ic.input_pacing_summary(),
      f"post-backoff summary should report the misfires: {ic.input_pacing_summary()}")

reset_pacing()

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} input-timing failure(s)")
print(f"OK: adaptive backoff — floor of {ic.MISFIRES_BEFORE_BACKOFF} respected, "
      f"+{ic.BACKOFF_STEP}s step reaches press() (not frozen in the signature), "
      f"focus caching disabled on backoff, {ic.MAX_ACTION_DELAY}s ceiling holds")


# --- Focus-cache visibility ------------------------------------------------
# Answers "is the TTL actually holding under live conditions?" during the run,
# not after it. Absence of a misfire warning is NOT confirmation — it reads
# identically whether the auditor is working or silently not running.

reset_pacing()
ic._focus_calls = 0
ic._focus_skips = 0
ic._focus_marker = (0, 0)

# A tight 7-press sequence: one focus call, six cached.
for _ in range(7):
    ic.press(ACTION, post_delay=0.0)
_c, _s = ic.focus_stats_since_mark()
check((_c, _s) == (1, 6),
      f"a 7-press sequence reported {_c} focus calls / {_s} cached, expected "
      "1/6 — the per-turn counters do not reflect what the cache did")

# The mark resets, so the next turn reports only its own presses.
for _ in range(3):
    ic.press(ACTION, post_delay=0.0)
_c2, _s2 = ic.focus_stats_since_mark()
check((_c2, _s2) == (0, 3),
      f"second sequence reported {_c2}/{_s2}, expected 0/3 — the marker is not "
      "resetting, so per-turn numbers would accumulate and mislead")

# THE FAILURE THIS EXISTS TO SURFACE: live latency stretching every gap past
# the TTL. The cache then does nothing, silently, with no error and no misfire.
reset_pacing()
ic._focus_calls = 0
ic._focus_skips = 0
ic._focus_marker = (0, 0)
for _ in range(5):
    ic.press(ACTION, post_delay=ic.FOCUS_TTL + 0.1)
_c3, _s3 = ic.focus_stats_since_mark()
check((_c3, _s3) == (5, 0),
      f"with every gap beyond the TTL the counters said {_c3}/{_s3}, expected "
      "5/0 — a cache that has silently stopped engaging would look healthy")
check("0%" in ic.focus_cache_summary() or "cached (0" in ic.focus_cache_summary(),
      f"summary should show 0% cached in this state: {ic.focus_cache_summary()}")

reset_pacing()
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} input-timing failure(s)")
print("OK: focus-cache visibility — per-turn counters track the cache, the "
      "mark resets each turn, and a cache that stops engaging under live "
      "latency reports 0% rather than looking healthy")


# --- INPUT EXECUTION: the exact key sequence, not just the timing ---------
# QA_VACUOUS found the worst gap in the suite: `input_controller`'s execution
# layer had ZERO behavioural coverage. Every test that reaches it replaces it
# with a recorder, so these all survived the entire 15-file suite:
#   * banning column `4-c` instead of `c`  <- BANS THE WRONG PHYSICAL CARD
#   * removing row navigation entirely
#   * dropping the second confirm (M11)
#   * inverting the play-card navigation
# The only ban assertion anywhere was `len(bans_submitted[0]) == 3` — a COUNT,
# which this file's own header already warns is not enough.
#
# These assert the KEY SEQUENCE. Still no key can reach the machine: pyautogui
# and subprocess were replaced with recorders at the top of this file, long
# before input_controller was imported.
from decision_engine import PlayerCard as _PC


def keys_for(fn, *a, **k):
    """Run an input routine and return the ordered list of logical actions."""
    reset()
    fn(*a, **k)
    return list(ic.press_log) if hasattr(ic, "press_log") else None


# press() is the single choke point; record the ACTION names through it.
_ACTIONS = []
_real_press = ic.press


def _recording_press(action, *a, **kw):
    _ACTIONS.append(action)
    return _real_press(action, *a, **kw)


ic.press = _recording_press


def seq(fn, *a, **k):
    _ACTIONS.clear()
    reset_pacing()
    fn(*a, **k)
    return list(_ACTIONS)


# --- select_and_play: navigate right N, select, confirm ------------------
# The cursor is HOMED first, never assumed. reset_hand_cursor() drives
# MAX_HAND_SIZE-1 lefts because the game does not reset the cursor between
# turns within a half — it stays wherever the last selection left it. Asserting
# "no left presses" would therefore be asserting a bug.
# invalidate_cursor() first: these assertions are about the COLD path, where
# the cursor's position is unknown and must be re-established. Warm, the
# position is remembered and the homing is correctly skipped — asserted
# separately below, and exhaustively in test_cursor_tracking.py.
ic.invalidate_cursor()
s0 = seq(ic.select_and_play, 0, allow_blind=True)
# LITERAL 4, not MAX_HAND_SIZE - 1. Reading the constant under test makes the
# assertion true for ANY value: MAX_HAND_SIZE = 3 survived the whole suite
# while homing two presses short of the left edge, so every index landed on
# the wrong card (QA, 2026-08-26). The hand is 5 cards — the validator already
# encodes that as `0 <= hand_index < 5` — so the home is 4 presses.
check(ic.MAX_HAND_SIZE == 5,
      f"MAX_HAND_SIZE is {ic.MAX_HAND_SIZE}; the hand is 5 cards, as "
      "validate_game_state's hand_index bound independently asserts")
check(s0.count("move_left") == 4,
      f"select_and_play(0) sent {s0.count('move_left')} move_left, expected 4 "
      "— without a full home the cursor's real position is unknown and every "
      "index lands on the wrong card")
check(s0.count("move_right") == 0,
      f"playing card 0 moved right {s0.count('move_right')} times after homing: {s0}")
check("select_card" in s0 and "confirm_play" in s0,
      f"select_and_play(0) sent {s0} — it must select AND confirm")

ic.invalidate_cursor()
s3 = seq(ic.select_and_play, 3, allow_blind=True)
check(s3.count("move_right") == 3,
      f"playing card 3 sent {s3.count('move_right')} move_right (expected 3): "
      f"{s3}. Off by one here plays a DIFFERENT CARD than the engine chose.")
# Homing must come BEFORE the rights, or the count is measured from nowhere.
check(s3.index("move_right") > s3.index("move_left"),
      f"the cursor moved right before homing: {s3}")
check(s3.index("select_card") > max(i for i, a in enumerate(s3) if a == "move_right"),
      f"select_card fired before the cursor finished moving: {s3}")

# A PLAY NEVER RUNS WARM, since 2026-09-09. These two checks used to require the
# opposite -- that a second play skipped the four homing presses because the position
# was known -- and that saving was the defect. A play RE-DEALS the hand, so the
# cursor ends up wherever the game put it, and the next selection was navigating from
# a position it no longer held. Measured over one match: play turns that happened to
# home first logged the right card 4 of 4; those that did not, 0 of 6, Fisher exact
# p = 0.0048. The saving still exists where nothing re-deals: two navigations inside
# one turn, pinned in tests/rig/test_cursor_tracking.py.
_warm = seq(ic.select_and_play, 3, allow_blind=True)          # the cursor is believed to be at 3
check(_warm.count("move_left") == ic.MAX_HAND_SIZE - 1,
      f"a second play must home again, not trust the belief: {_warm}")
_warm2 = seq(ic.select_and_play, 1, allow_blind=True)
check(_warm2.count("move_left") == ic.MAX_HAND_SIZE - 1 and _warm2.count("move_right") == 1,
      f"a play to index 1 must home ({ic.MAX_HAND_SIZE - 1} left) then step right once: {_warm2}")
check(ic._cursor_col is None,
      f"a play must forget the cursor afterwards, got {ic._cursor_col!r}")
ic.invalidate_cursor()

# --- select_and_discard: must NOT confirm a play -------------------------
sd = seq(ic.select_and_discard, 2)
check(sd.count("move_right") == 2,
      f"discarding card 2 sent {sd.count('move_right')} move_right: {sd}")
# The header above says "must NOT confirm a play", but this assertion used to
# be `"confirm_discard" in sd or "confirm_play" in sd` — satisfied by the OR
# even when confirm_discard was replaced outright by confirm_play, i.e. when
# the card was PLAYED instead of discarded. The comment claimed something
# strictly stronger than the check, and the weaker half was the true one
# (QA, 2026-08-26). Pin the discard itself, and its position.
check(sd.count("confirm_discard") == 1,
      f"select_and_discard sent {sd.count('confirm_discard')} confirm_discard, "
      f"expected exactly 1 — the card is being PLAYED, not discarded: {sd}")
# AND THE HEADER IS NOW LITERALLY TRUE. It has said "must NOT confirm a play"
# since it was written, and a 2026-08-26 QA pass noted the assertion under it was
# weaker -- but the press itself stayed for another three weeks. On 2026-09-16 it
# played the worst card in a pitching hand at the opponent when the Square press
# was dropped: ROUND pips 4 -> 5 with discards_left stuck at 2. A discard does not
# use the turn, so Triangle has no business here at all.
check("confirm_play" not in sd,
      f"select_and_discard must NEVER send confirm_play -- it plays whatever is "
      f"lifted whenever confirm_discard is swallowed: {sd}")

# --- select_bans_and_start_full: THE one that bans a physical card -------
# Grid is (absolute_row, col, card). Column navigation must move RIGHT by `col`
# from column 0 — not by `4 - col`, which is the mutation that survived
# everything and bans a different card in the same row.
_grid = [(0, 0, _PC("A", 9, 1)), (0, 3, _PC("B", 8, 1)), (1, 1, _PC("C", 7, 1))]
sb = seq(ic.select_bans_and_start_full, _grid, {(0, 0), (0, 3), (1, 1)})

_first_sel = sb.index("select_card")
_before_first = sb[:_first_sel]
check(_before_first.count("move_right") == 0 and _before_first.count("move_down") == 0,
      f"the first ban is at (0,0) but the cursor moved before selecting it: "
      f"{_before_first} — the caller guarantees a (0,0) start")

# Between the first and second selection: col 0 -> col 3 is THREE rights.
_second = sb[_first_sel + 1:]
_upto = _second[:_second.index("select_card")]
check(_upto.count("move_right") == 3 and _upto.count("move_left") == 0,
      f"moving from column 0 to column 3 sent {_upto.count('move_right')} right "
      f"and {_upto.count('move_left')} left: {_upto}. Banning column `4-c` "
      "instead of `c` bans a DIFFERENT PHYSICAL CARD and survived the entire "
      "previous suite.")

check(sb.count("select_card") == 3,
      f"3 ban positions produced {sb.count('select_card')} selections: {sb}")
# EXACT counts, not a floor. `>= 1` is one-sided: it catches too few and not
# too many, and too many is the same class of bug — mutating the loop to
# `range(3 * (row - current_row))` survived, sending the ban three rows down
# onto a card the player may not own. The fixture grid is
# [(0,0), (0,3), (1,1)], so exactly one move_down and one move_up (the unwind
# must return to the top before confirming).
check(sb.count("move_down") == 1,
      f"ban navigation sent {sb.count('move_down')} move_down, expected "
      f"exactly 1 for a grid whose deepest ban is row 1: {sb}")
check(sb.count("move_up") == 1,
      f"the cursor unwind sent {sb.count('move_up')} move_up, expected 1 to "
      f"match the single move_down: {sb}")

ic.press = _real_press
reset_pacing()

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} input-execution failure(s)")

print("OK: input execution — play/discard/ban key SEQUENCES asserted "
      "(column direction, row navigation, select-then-confirm ordering)")


# --- the before_confirm hook must fire, in the REAL function (V2) --------
# QA 2026-08-26: mutating `if before_confirm is not None:` to `if False:`
# survived the whole suite. test_run_state_machine.py replaces
# select_bans_and_start_full with its own stub, so it proves the STUB calls
# the hook; nothing proved the real function does. And this file called the
# real function but passed no before_confirm, so the branch never ran.
#
# The hook is the only moment the ban counter is legible — read it after the
# confirm presses and the screen is already gone, which is why the check had
# never once succeeded live. Its ORDERING is the whole point, so pin that.
# The recorder is uninstalled at line ~404 for the pacing tests, so re-install
# it here — without this, `seq` returns an empty action list and the ordering
# assertions below silently have nothing to check.
ic.press = _recording_press
# Record the hook AS AN ACTION rather than counting presses. Counting len()
# at hook time was off by one and produced a confident, wrong failure; a
# sentinel in the same list the presses go into cannot drift.
_grid2 = [(0, 0, _PC("A", 9, 1)), (1, 2, _PC("B", 8, 1))]
_sb2 = seq(ic.select_bans_and_start_full, _grid2, {(0, 0), (1, 2)},
           before_confirm=lambda: _ACTIONS.append("<hook>"))
ic.press = _real_press

check(_sb2.count("<hook>") == 1,
      f"before_confirm fired {_sb2.count('<hook>')} times, expected exactly 1 "
      "— with it dead the ban counter is never read on any real match and "
      f"verification reverts to the blindness it was written to fix: {_sb2}")

if "<hook>" in _sb2:
    _h = _sb2.index("<hook>")
    _last_select = max(i for i, a in enumerate(_sb2) if a == "select_card")
    _ups = [i for i, a in enumerate(_sb2) if a == "move_up"]
    _confirms = [i for i, a in enumerate(_sb2) if a == "confirm_play"]
    check(_h > _last_select,
          f"before_confirm fired BEFORE the last selection ({_last_select}), so "
          f"it would read an incomplete ban set: {_sb2}")
    check(not _confirms or _h < min(_confirms),
          f"before_confirm fired after the first confirm_play — the ban screen "
          f"is already dismissed by then: {_sb2}")
    check(not _ups or _h < min(_ups),
          f"before_confirm fired after the move_up unwind (hook at {_h}, first "
          f"move_up at {min(_ups) if _ups else None}). Measured live, the cursor "
          "only reaches the top with 0.53-1.11s of ban screen left, against "
          f"4.2s at the correct point: {_sb2}")

print("OK: before_confirm fires once, in the real function, between the last "
      "selection and the cursor unwind")


# --- start fast, fall back to KNOWN-SAFE on evidence ---------------------
# ACTION_DELAY now starts at 0.25 (measured 42% off the input path) instead of
# the old 0.4 "starting guess". That is only safe if recovery is fast: from
# 0.25 a bare +0.05 step needs THREE separate misfires — three lost turns — to
# get back to the 0.4 that ran clean for weeks. So the first backoff jumps
# straight there, and only then steps.
import importlib as _il
_il.reload(ic)
ic.FOCUS_PRESS_IN_TESTS = True   # reload() reset it to the False default
check(ic.ACTION_DELAY < ic.BACKOFF_SAFE_DELAY,
      f"ACTION_DELAY starts at {ic.ACTION_DELAY}, not below the known-safe "
      f"{ic.BACKOFF_SAFE_DELAY} — the fast default is gone and the jump below "
      "is untested")
for _ in range(ic.MISFIRES_BEFORE_BACKOFF):
    ic.report_misfire()
check(abs(ic.ACTION_DELAY - ic.BACKOFF_SAFE_DELAY) < 1e-9,
      f"first backoff landed at {ic.ACTION_DELAY:.2f}, expected an immediate "
      f"jump to {ic.BACKOFF_SAFE_DELAY} — inching up from a fast default costs "
      "a lost turn per step")
ic.report_misfire()
check(abs(ic.ACTION_DELAY - (ic.BACKOFF_SAFE_DELAY + ic.BACKOFF_STEP)) < 1e-9,
      f"after the jump it should step by {ic.BACKOFF_STEP}, got {ic.ACTION_DELAY:.2f}")
# The ceiling still holds from the new starting point.
for _ in range(40):
    ic.report_misfire()
check(ic.ACTION_DELAY <= ic.MAX_ACTION_DELAY,
      f"backoff blew past its {ic.MAX_ACTION_DELAY}s ceiling: {ic.ACTION_DELAY}")
_il.reload(ic)
ic.FOCUS_PRESS_IN_TESTS = True   # reload() reset it to the False default

print(f"OK: input starts fast ({ic.ACTION_DELAY}s), first backoff jumps to the "
      f"known-safe {ic.BACKOFF_SAFE_DELAY}s, then steps, ceiling holds")


# --- tactics attachment navigation (V10 IC7) -----------------------------
# No test ever called select_and_play with a tactics_index, so inverting
# `move = "move_right" if steps > 0 else "move_left"` survived — and attaching
# the swing boost is a decision the engine makes on EVERY batting turn.
# The recorder is uninstalled above for the pacing tests; re-install it or
# `seq` returns an empty list and every assertion below silently passes.
ic.press = _recording_press
ic.invalidate_cursor()
_tac = seq(ic.select_and_play, 1, 3, allow_blind=True)          # card 1, tactics 3: two rights
_sel = [i for i, a in enumerate(_tac) if a == "select_card"]
check(len(_sel) == 2, f"expected two select_card (card then tactics): {_tac}")
if len(_sel) == 2:
    _between = _tac[_sel[0] + 1:_sel[1]]
    check(_between.count("move_right") == 2 and _between.count("move_left") == 0,
          f"navigating from card 1 to tactics 3 sent {_between} — it must be "
          "two move_right; inverted, it walks the wrong way and attaches the "
          "wrong card")
ic.invalidate_cursor()
_tac2 = seq(ic.select_and_play, 3, 1, allow_blind=True)         # backwards: two lefts
_sel2 = [i for i, a in enumerate(_tac2) if a == "select_card"]
if len(_sel2) == 2:
    _b2 = _tac2[_sel2[0] + 1:_sel2[1]]
    check(_b2.count("move_left") == 2 and _b2.count("move_right") == 0,
          f"navigating from card 3 back to tactics 1 sent {_b2}")
ic.invalidate_cursor()
ic.press = _real_press

# FINAL failure summary. This file raises at four points (136, 230, 281, 407),
# so ANY check appended after the last one runs but can never report — its
# failures land in `failures` after the summary that would have printed them.
# That is how the before_confirm ordering assertions above passed against a
# hook physically moved below the cursor unwind (QA-caught, 2026-08-26). Third
# instance of this trap in one day; keep this block last in the file.
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} input-timing failure(s)")
