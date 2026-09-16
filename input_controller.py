"""
Chiaki-ng Input Controller (macOS, keyboard-only mode)
========================================================
Sends synthetic keypresses into the Chiaki-ng window to drive the
Baseball minigame, based on Chiaki-ng's keyboard-to-DualSense mapping
(no physical controller connected, so Chiaki-ng falls back to
whatever's set in Settings -> Controller -> Keyboard).

KEYMAP below is intentionally blank. Fill it in once you send the
actual bindings from your Chiaki-ng settings screen. Everything else
here is ready to go.

Requires: pip install pyautogui --break-system-packages
"""

import os as _os_env   # for the BASEBALL_TEST_RUN guards below
import os
import subprocess
import sys
import time

import pyautogui

# Logical actions the minigame needs, inferred from the observed UI:
#   - move hover left / right across the hand
#   - select/deselect the hovered card
#   - confirm Play      -> triangle, confirmed via on-screen "PLAY" prompt
#   - confirm Discard    -> square, confirmed via on-screen "DISCARD" prompt
# The dpad-navigation and select actions are inferred (standard menu
# navigation), not yet directly confirmed against the UI.
KEYMAP = {
    "move_left": "left",     # D-Pad Left  -> confirmed from Chiaki-ng Keys settings
    "move_right": "right",   # D-Pad Right -> confirmed from Chiaki-ng Keys settings
    "move_up": "up",         # D-Pad Up    -> confirmed from Chiaki-ng Keys settings
    "move_down": "down",     # D-Pad Down  -> confirmed from Chiaki-ng Keys settings
    "select_card": "enter",  # Cross       -> key binding confirmed; "Cross lifts a card"
                              #                itself is a standard-UI assumption, not yet
                              #                confirmed against this specific game — test
                              #                this one first when you try it live
    "confirm_play": "c",     # Pyramid/Triangle -> confirmed via on-screen "PLAY" prompt
    "confirm_discard": "\\",  # Box/Square      -> confirmed via on-screen "DISCARD" prompt
    "start_match": "\\",      # Box/Square      -> confirmed via on-screen "Play ($50)" prompt
                              #                    (same key as confirm_discard, kept as a
                              #                     separate name since it means something
                              #                     different in context)
    "toggle_pause": "o",      # Options -> key binding confirmed; "Options opens/closes the
                              #             pause menu" is a standard-PS-game assumption, not
                              #             yet confirmed against this specific game
    "close_result": "backspace",  # Moon/Circle -> confirmed via on-screen "CLOSE" prompt

    # --- Analog sticks and the remaining buttons ---------------------------
    # Read directly off chiaki-ng's Keys settings screen (2026-08-26). These
    # are NOT stored in any plist — chiaki keeps its defaults in-app, which is
    # why they had to be transcribed by hand.
    #
    # The sticks are what the RESET sequence needs: walking back to the
    # minigame after a save reload is left-stick movement, not D-pad. Held,
    # not tapped — press(..., hold_seconds=N) is how you walk for N seconds.
    # Rebound to WASD in chiaki's Keys screen on 2026-08-26. The originals were
    # Ins/Del/[/] and `Ins` DOES NOT WORK ON macOS — there is no Insert key on a
    # Mac keyboard, so pyautogui cannot synthesise that keycode and the press
    # silently does nothing. Measured: walk_left/right/down each produced a
    # 12-19 pixel-delta, walk_up produced 1.4 (noise). The Help key, which
    # shares Insert's scancode on Mac, did not work either.
    "walk_up": "w",             # Left Stick Up
    "walk_down": "s",           # Left Stick Down
    "walk_left": "a",           # Left Stick Left
    "walk_right": "d",          # Left Stick Right
    "look_up": "pageup",        # Right Stick Up
    "look_down": "pagedown",    # Right Stick Down
    "look_left": "-",           # Right Stick Left
    "look_right": "=",          # Right Stick Right

    "l1": "2", "r1": "3", "l2": "1", "r2": "4", "l3": "5", "r3": "6",
    "ps_button": "esc",         # PS
    "share": "f",               # Share
    "touchpad": "t",            # Touchpad

    # Raw PS button names, so an arbitrary sequence (a reset walk, a menu
    # path) can be written in the language of the controller instead of this
    # game's vocabulary. Same keys as above — aliases, not new bindings.
    "cross": "enter",           # X
    "pyramid": "c",             # Triangle
    "moon": "backspace",        # Circle
    "box": "\\",                # Square
    "dpad_up": "up",
    "dpad_down": "down",
    "dpad_left": "left",
    "dpad_right": "right",
    "options": "o",
}

CHIAKI_WINDOW_PROCESS_NAME = "chiaki"  # matches macOS process name, confirmed via System Events

# Delay after every keypress, to let both the local UI animation (a card
# lifting, a selection highlight moving) and Chiaki-ng's network round-trip
# to the actual PS5 catch up before the next input fires.
#
# START FAST, BACK OFF ON EVIDENCE. This was 0.4 — explicitly "a starting
# guess, not a measured value", with the instruction "if it feels sluggish and
# nothing's being missed, lower it". Both halves of that test now pass: the
# 2026-08-26 evening match ran 13 decisions with ZERO misfires, and a turn
# spends ~16 presses, so 0.4 was costing ~10s of every turn on delay alone.
#
# Measured on the real press path (focus + hold + delay), 16 presses:
#     0.40 / TTL 1.5  ->  10.01s      0.30 / TTL 3.0  ->  6.61s
#     0.40 / TTL 3.0  ->   8.65s      0.25 / TTL 3.0  ->  5.82s
# 0.25 is 42% off the input path. Below it the focus overhead dominates and
# further cuts buy nothing.
#
# The safety net is report_misfire(): if this is too fast for the machine or
# the network, dropped keystrokes surface as misfires and the delay climbs
# back on its own — starting with an immediate jump to BACKOFF_SAFE_DELAY,
# the value that ran clean for weeks, rather than crawling up in 0.05 steps.
ACTION_DELAY = 0.25
# The fast default, kept so an abandoned backoff can restore it.
DEFAULT_ACTION_DELAY = 0.25


# How long a focus call is trusted to still hold. Measured 2026-08-25: the
# osascript round-trip costs ~154ms, and press() paid it on EVERY keystroke
# plus a 150ms settle wait — 304ms of every 754ms press spent re-focusing a
# window that was already focused. A worst-case turn (card 4 plus a tactics
# card, 11 presses) spent 3.3s of its 8.3s on redundant focus calls.
#
# Within one navigation sequence the presses are 0.4s apart and nothing can
# steal focus in between, so re-asserting it each time buys nothing. Across
# turns there IS a real gap, so the TTL is deliberately short: any pause
# longer than this re-focuses.
#
# THE RISK, stated plainly: if focus is lost inside the TTL window, keystrokes
# land on whatever app took it. That needs a person to click another window
# mid-sequence — at which point they are at the keyboard and can stop the run.
# Set FOCUS_TTL = 0 to restore the old always-focus behaviour.
# Raised 1.5 -> 3.0. At the new press cadence (~0.36s) a 1.5s TTL re-focused
# every 4th press; 3.0 halves that for no measurable risk, since every capture
# also refreshes the focus. Measured: 6/16 focus calls -> 2/16, worth 1.37s a
# turn on its own. Beyond 3.0 the curve is flat (4.0 measured identical), so
# this is the knee, not a guess.
FOCUS_TTL = 3.0
_last_focus_at = 0.0

# --- Adaptive backoff ------------------------------------------------------
# The reveal auditor catches a misplayed card AFTER the fact, so it cannot undo
# the turn — but a misfire means the machine is currently too slow for the
# current pacing, and the next turn is likely to misfire too. Backing off makes
# the run self-healing when background CPU load spikes mid-session, instead of
# needing someone to notice and restart with a bigger ACTION_DELAY.
#
# CAPPED AND SLOW ON PURPOSE. The auditor cannot distinguish a dropped
# keystroke from a misread reveal — both look like "our card wasn't there". So
# the signal is noisy in exactly the direction that would ratchet the delay up
# forever on a vision problem that more waiting cannot fix, turning a logging
# fault into an unusably slow run. Hence: a floor of two misfires before
# reacting at all, +50ms a step, and a hard ceiling.
MISFIRES_BEFORE_BACKOFF = 2
BACKOFF_STEP = 0.05
MAX_ACTION_DELAY = 0.8
# How many backoffs may each be followed by ANOTHER misfire before concluding
# that waiting is not the fix. The ceiling check below only reaches that
# conclusion at MAX_ACTION_DELAY, which is far too late: measured 2026-09-01,
# a session ratcheted 0.25 -> 0.65 across six backoffs, ran every input 2.6x
# slower for the rest of the day, and misfired at the same rate throughout.
#
# That is the experiment. If dropped keystrokes were the cause, 2.6x more
# settling time would have changed something. It did not, and the reveal reader
# was visibly at fault in the same logs — returning power 0 for a card the
# roster puts at 5, and powers of 4/5/7 for hands where we had just played 8/9.
BACKOFF_INEFFECTIVE_AFTER = 3
# Where the first backoff lands: the delay that ran for weeks without dropped
# input. Fast by default, proven-safe the moment there is evidence otherwise.
BACKOFF_SAFE_DELAY = 0.40
_backoff_applied = 0.0
_misfires_seen = 0
_backoffs_applied = 0
_backoff_abandoned = False


def report_misfire() -> bool:
    """Tell the input layer a play didn't land. Returns True if pacing changed.

    Called by the orchestrator's reveal auditor. Kept here rather than there so
    the timing policy lives with the timing constants.
    """
    global _misfires_seen, _backoff_applied, ACTION_DELAY
    global _backoffs_applied, _backoff_abandoned
    _misfires_seen += 1
    # INVALIDATE FIRST, on EVERY misfire, before any early return.
    #
    # This used to live at the bottom, on the backoff-APPLIED path only, so
    # four of the five returns skipped it — including `_backoff_abandoned`,
    # which latches True and then never invalidates again for the life of the
    # process. Demonstrated 2026-09-04: after abandonment the belief survived a
    # misfire, and the next selection navigated from a position the game was
    # not at and played the WRONG CARD in a $50 match.
    #
    # The reason it belongs here is in its own original comment: a misfire
    # means a keystroke may have been SWALLOWED, which is exactly the event
    # that puts the real cursor somewhere other than where we believe it is.
    # That is true of every misfire, whatever the backoff decides to do about
    # it. The backoff is a remedy; this is an admission of ignorance.
    invalidate_cursor()
    if _misfires_seen < MISFIRES_BEFORE_BACKOFF:
        return False
    if _backoff_abandoned:
        return False
    # EVERY backoff so far was followed by another misfire, so waiting is not
    # what is wrong. Give the speed back rather than paying for a remedy that
    # has been measured not to work — a slower run is a real cost, and this one
    # bought nothing all day.
    if _backoffs_applied >= BACKOFF_INEFFECTIVE_AFTER:
        _backoff_abandoned = True
        ACTION_DELAY = DEFAULT_ACTION_DELAY
        _backoff_applied = 0.0
        print(f"  [input] {_backoffs_applied} backoffs and still misfiring — "
              f"more waiting is NOT the fix, so ACTION_DELAY is back to "
              f"{ACTION_DELAY:.2f}s. Suspect the REVEAL READ, not dropped "
              f"input (see report_misfire).")
        return False
    if ACTION_DELAY >= MAX_ACTION_DELAY:
        print(f"  [input] {_misfires_seen} misfires but ACTION_DELAY is already "
              f"at its {MAX_ACTION_DELAY}s ceiling — more waiting is not the "
              "fix, so this is likely a reveal MISREAD, not dropped input.")
        return False
    # First backoff jumps straight to the known-good value rather than
    # inching up from the fast default. Starting fast is only safe if getting
    # back to safe is fast too: from 0.25 a 0.05 step needs three separate
    # misfires — three lost turns — just to reach the 0.4 that ran clean for
    # weeks. After that, step as before.
    _before = ACTION_DELAY
    if ACTION_DELAY < BACKOFF_SAFE_DELAY:
        ACTION_DELAY = BACKOFF_SAFE_DELAY
    else:
        ACTION_DELAY = min(ACTION_DELAY + BACKOFF_STEP, MAX_ACTION_DELAY)
    _backoff_applied += ACTION_DELAY - _before
    _backoffs_applied += 1
    # Also stop trusting cached focus: if input is being dropped, the cheapest
    # thing to stop economising on is the focus assertion itself.
    globals()["FOCUS_TTL"] = 0.0
    # (The cursor was already invalidated at the top, on every misfire — see
    # the comment there. It used to be done only here, which meant four of the
    # five return paths kept a stale belief.)
    print(f"  [input] misfire #{_misfires_seen} — ACTION_DELAY raised to "
          f"{ACTION_DELAY:.2f}s and focus caching disabled for the rest of "
          "the run.")
    return True


def input_pacing_summary() -> str:
    if not _misfires_seen:
        return f"  [input] pacing unchanged (ACTION_DELAY {ACTION_DELAY:.2f}s, FOCUS_TTL {FOCUS_TTL}s)"
    return (f"  [input] {_misfires_seen} misfire(s); ACTION_DELAY ended at "
            f"{ACTION_DELAY:.2f}s (+{_backoff_applied:.2f}s), FOCUS_TTL {FOCUS_TTL}s")


# Focus-cache counters. The whole point of the TTL is that a navigation
# sequence pays ONE osascript round-trip instead of one per press — but whether
# that actually happens depends on live conditions, not on the code. If network
# lag or a slow frame stretches the gap between presses past FOCUS_TTL, every
# press re-focuses and the optimisation silently does nothing while still
# looking healthy: no error, no misfire, just the old latency back.
#
# These make that visible per turn, so the first few turns confirm the cache is
# working rather than merely failing to complain.
_focus_calls = 0
_focus_skips = 0
_focus_marker = (0, 0)


def focus_stats_since_mark():
    """(presses_focused, presses_cached) since the last mark, then re-mark."""
    global _focus_marker
    c, s = _focus_calls - _focus_marker[0], _focus_skips - _focus_marker[1]
    _focus_marker = (_focus_calls, _focus_skips)
    return c, s


# WHICH DELIVERY PATH CARRIED EACH PRESS. press() has three, tried in order,
# and the log never said which one ran:
#
#   FIFO inject        writes a stick/button field into chiaki's inject pipe
#   background Quartz  CGEventPostToPid — targeted, does not touch focus
#   focus+pyautogui    raises the chiaki window and types into the FRONTMOST
#                      window, per press()'s own comment "capable of typing
#                      into the user's work"
#
# The third is not a variant of the first two, it is a different risk. And it
# is reached in SILENCE whenever can_use_background_input() is False — the
# announced fallback below only covers _bg_hold_keys() returning False, not the
# guard skipping the whole branch. A run that had quietly moved onto the
# focus-stealing path was indistinguishable in the log from one delivering
# cleanly over the FIFO.
#
# COUNTERS, NOT PER-PRESS LINES: press() is the hottest button path in the
# system (every menu navigation, every card selection), so a line each would
# bury the log. One summary, printed where focus_cache_summary() is.
_press_via_inject = 0
_press_via_background = 0
_press_via_focus = 0


def press_path_counts():
    """(fifo_inject, background_quartz, focus_pyautogui) presses so far."""
    return (_press_via_inject, _press_via_background, _press_via_focus)


def press_path_summary() -> str:
    inj, bg, foc = _press_via_inject, _press_via_background, _press_via_focus
    total = inj + bg + foc
    if not total:
        return "  [input] no presses delivered by any path"
    line = (f"  [input] press delivery: {inj} FIFO inject, {bg} background "
            f"Quartz, {foc} focus+pyautogui (of {total})")
    if foc:
        line += (f" — those {foc} went to the FRONTMOST window, so they may "
                 "have been typed into the user's own work rather than the "
                 "game; a press counted here is NOT proof it reached chiaki")
    return line


def focus_cache_summary() -> str:
    total = _focus_calls + _focus_skips
    # Appended rather than printed separately so the one existing caller
    # (orchestrator, which prints this string) reports it without changing.
    if not total:
        # "no keypresses sent" is itself misleading when every press went over
        # the FIFO — that path never touches focus, so both counters stay 0.
        return "  [input] no keypresses sent\n" + press_path_summary()
    pct = 100.0 * _focus_skips / total
    return (f"  [input] {total} presses, {_focus_calls} focus calls, "
            f"{_focus_skips} cached ({pct:.0f}%) — saved ~"
            f"{_focus_skips * 0.304:.1f}s\n" + press_path_summary())


def focus_chiaki_window(force: bool = False) -> bool:
    """
    Bring the Chiaki-ng window to the foreground before sending input,
    so keystrokes land on the game and not on whatever else has focus.

    Returns True if it actually called out to osascript, False if it trusted
    a recent focus. The caller uses that to skip the settle wait too — there
    is nothing to wait for when no focus change was requested.
    """
    global _last_focus_at, _focus_calls, _focus_skips
    now = time.monotonic()
    if not force and FOCUS_TTL and (now - _last_focus_at) < FOCUS_TTL:
        _focus_skips += 1
        return False
    # NEVER RAISE THE WINDOW WHEN WE DO NOT NEED TO.
    # Background input delivers keystrokes straight to chiaki's process, so
    # focus is irrelevant — and taking it anyway yanks the user out of whatever
    # they are doing. That happened live on 2026-08-27: the user was working in
    # Slack and the window jumped. The guard lives HERE rather than at each
    # call site because the call sites are the problem: any of them, in code or
    # in a test, would otherwise steal focus the moment chiaki is running.
    # OVERNIGHT OVERRIDE. Normally focus is never taken — stealing the keyboard
    # from someone at their desk is the thing background input exists to avoid.
    # But chiaki does not deliver injected input reliably when it is not the
    # active window, which stalled an unattended run on 2026-08-28. When the
    # user is away and has said so, focusing is correct rather than rude.
    if os.environ.get("BASEBALL_ALLOW_FOCUS") == "1":
        pass
    elif can_use_background_input():
        _focus_skips += 1
        return False

    # NEVER raise a real window from the offline suite. Disabling background
    # input for tests (so they exercise the stubbed pyautogui path) also took
    # the guard above out of play, which handed the focus-stealing path back to
    # every test that presses a key — and with the game running, that yanked
    # the user out of their work twice. Tests that COUNT focus calls still see
    # them: the counter below increments either way.
    _focus_calls += 1
    if os.environ.get("BASEBALL_TEST_RUN"):
        _last_focus_at = time.monotonic()
        return True

    if sys.platform == "win32":
        _focus_window_windows()
    else:
        script = (
            f'tell application "System Events" to set frontmost of first process '
            f'whose name contains "{CHIAKI_WINDOW_PROCESS_NAME}" to true'
        )
        subprocess.run(["osascript", "-e", script], check=False)
    _last_focus_at = time.monotonic()
    return True


def _focus_window_windows() -> None:
    """Raise the chiaki window on Windows. Never raises.

    Deliberately silent on failure, matching the macOS path: this only ASKS for
    focus. has_focus() is what decides whether input may be sent, and it is
    checked separately. A raise here would abort a run over a transient
    SetForegroundWindow refusal, which Windows issues routinely.
    """
    try:
        import pygetwindow
        for win in pygetwindow.getWindowsWithTitle(CHIAKI_WINDOW_PROCESS_NAME):
            if win.isMinimized:
                win.restore()
            win.activate()
            return
    except Exception:
        pass


# Opt-in for the three tests that drive the focus+pyautogui fallback on purpose. OFF by
# default so the offline suite can never reach the real keyboard; see press().
FOCUS_PRESS_IN_TESTS = False


def focus_input_allowed(action=None):
    """May this process type into the FRONTMOST window?

    THE TEST-RUN LOCKOUT ONLY EVER COVERED THE TARGETED PATH, and 2026-09-13 showed what
    that costs. can_use_background_input() refuses under BASEBALL_TEST_RUN and its
    docstring claims that "means a test run can never move the character" -- it means a
    test run cannot use the BACKGROUND path, and each of the three callers below then
    falls straight through to pyautogui, which types into whatever is FRONTMOST. A
    mutation run of the offline suite reached that line and sent "c"
    (confirm_play/Triangle) repeatedly while a paid match sat parked on the console; the
    user saw the keystrokes before any log did.

    The same shape as section 5's `_inject_press` returning True because the WRITE
    succeeded: a guard one layer up from where the damage happens, answering a narrower
    question than the one it is credited with. This one is asked AT the damage.

    The tests that exercise this path on purpose set FOCUS_PRESS_IN_TESTS and restore it.
    A test that forgets sends nothing and FAILS, which is the safe direction to be wrong
    in -- silence here means the keyboard.
    """
    if os.environ.get("BASEBALL_TEST_RUN") and not FOCUS_PRESS_IN_TESTS:
        print(f"  [input] BASEBALL_TEST_RUN: refusing to send {action or 'keys'} via "
              "focus+pyautogui — that path types into the FRONTMOST window")
        return False
    return True


def press(action: str, hold_seconds: float = 0.05, post_delay: float = None):
    """Press a single logical action's mapped key, then pause post_delay
    seconds so the UI/stream has time to register it before the next
    input fires.

    post_delay defaults to None, NOT to ACTION_DELAY. A default argument is
    bound once when the function is defined, so `post_delay=ACTION_DELAY` would
    freeze the value at import and every later adjustment by report_misfire()
    would be silently ignored — the backoff would appear to work, print that it
    had raised the delay, and change nothing.
    """
    # THE EVENT LOG (patch64), first, so the row exists whether or not the press
    # goes out (the test-run lockout below still holds every input path off).
    try:
        import event_log
        event_log.log_event("press", action=action, hold=hold_seconds, post_delay=post_delay)
    except Exception:
        pass
    global _press_via_inject, _press_via_background, _press_via_focus
    if post_delay is None:
        post_delay = ACTION_DELAY
    key = KEYMAP.get(action)
    if key is None:
        raise NotImplementedError(
            f"No key mapped for action '{action}' yet — fill in KEYMAP first."
        )
    # INJECTED INPUT FIRST — it does not depend on chiaki holding OS keyboard
    # focus, which is the thing that breaks. Both paths below need that focus,
    # and on 2026-09-01 both were dead after a chiaki restart while FIFO writes
    # reached the console fine.
    if _inject_press(action, hold_seconds):
        _press_via_inject += 1
        time.sleep(post_delay)
        return

    # Targeted delivery FIRST. pyautogui sends to whatever app is frontmost, so
    # every line below this guard is capable of typing into the user's work.
    if can_use_background_input(action):
        if _bg_hold_keys([key], hold_seconds):
            _press_via_background += 1
            time.sleep(post_delay)
            return
        # SAY SO. _bg_hold_keys returns False on a dead pid, an unmapped
        # keycode, or a Quartz raise — all three silently — and execution then
        # falls through to the focus-stealing path below, which per the comment
        # above is capable of typing into whatever the person is working in.
        #
        # Unannounced, a run that had quietly stopped using targeted delivery
        # was indistinguishable from one that never needed to, on the exact
        # path that spends the money.
        print(f"  [input] background injection FAILED for {action!r} — falling "
              "back to focus+pyautogui, which sends to the FRONTMOST window")

    # Every line below this point types into the FRONTMOST window. See focus_input_allowed.
    if not focus_input_allowed(action):
        return

    # Counted BEFORE the keys go out, so a press that raises still shows in the
    # summary as having taken this path — the fact worth recording is where the
    # keystrokes were aimed, not whether they finished.
    _press_via_focus += 1
    if focus_chiaki_window():
        # Only wait for focus to land when focus was actually changed.
        time.sleep(0.15)
    pyautogui.keyDown(key)
    time.sleep(hold_seconds)
    pyautogui.keyUp(key)
    time.sleep(post_delay)
    # The post_delay counts as elapsed time for the TTL, so a sequence with a
    # large ACTION_DELAY still re-focuses at a sane cadence rather than
    # trusting a focus that is older than it looks.


MAX_HAND_SIZE = 5


# Where we believe the hand cursor is, or None when we do not know.
#
# The game does NOT reset the cursor between turns (confirmed live: it stays
# where the last selection left it), which is why every navigation used to
# begin by blindly pressing move_left four times. That homing cost 4 presses
# of EVERY selection — at the measured 0.36s per press, ~1.4s a turn spent
# re-discovering a position we had just chosen ourselves.
#
# So remember it instead, and home only when the belief is unavailable. The
# belief is dropped whenever anything could have desynced it: a suspected
# misfire (a keystroke may have been swallowed), or an explicit invalidation
# from the caller when the screen changed under us.
_cursor_col = None


def invalidate_cursor():
    """Forget where the cursor is; the next navigation will re-home.

    Call this whenever the hand may have been re-dealt or the screen changed
    outside our own keypresses.
    """
    global _cursor_col
    _cursor_col = None


def reset_hand_cursor(force: bool = False):
    """
    Drive the cursor to the leftmost hand position regardless of where it
    currently is.

    Skips the four blind presses when the position is already known — that is
    the whole saving. `force=True` re-homes unconditionally, which is what the
    tests use to assert the homing still works when it is needed.
    """
    global _cursor_col
    if not force and _cursor_col == 0:
        return
    for _ in range(MAX_HAND_SIZE - 1):
        press("move_left")
    _cursor_col = 0


def _move_cursor_to(target: int):
    """Navigate to `target`, from the remembered position when we have one.

    Falls back to homing first when the position is unknown, so the worst case
    is exactly the old behaviour and never worse.
    """
    global _cursor_col
    if _cursor_col is None:
        reset_hand_cursor(force=True)
    steps = target - _cursor_col
    move = "move_right" if steps > 0 else "move_left"
    for _ in range(abs(steps)):
        press(move)
    _cursor_col = target


# --- Injected input, bypassing chiaki's keyboard mapping --------------------
#
# WHY THIS EXISTS. Buttons and sticks reach the PS5 by different routes: sticks
# go through our own injector (a FIFO chiaki reads every 8ms), buttons went
# through chiaki's Qt keyboard handling, which needs its window to hold OS
# keyboard focus. On 2026-09-01 that path died after a chiaki restart while
# video and heartbeats stayed perfectly healthy — reset_env's own probe
# reported "NO input is reaching the game" at the same moment FIFO writes were
# producing 20+ screen deltas. One route dead, the other fine.
#
# The bits are MEASURED, not recalled. Sent one at a time on a round-result
# overlay whose only action was CLOSE (so a wrong bit had nothing to hit):
#
#     cross  bit 1 -> delta 20.51      square bit 4 -> delta 21.96
#     circle bit 2 -> delta 20.55      idle baseline 1.70
#
# Those three confirm the enum's ordering, and the rest follow it. Anything not
# listed here has NOT been fired, and falls back to the keyboard path.
# EVERY ALIAS HERE MUST NAME THE SAME PHYSICAL BUTTON AS ITS KEYMAP ENTRY.
# `confirm_play` was mapped to CROSS here while KEYMAP documents it as
# Pyramid/Triangle ("confirmed via on-screen PLAY prompt"). The keyboard path
# had it right; this table, added 2026-09-01, did not. Every card play then
# pressed the wrong button: nothing was played, the faceoff never flipped, and
# wait_for_reveal_cards burned its full 75s on each turn before giving up —
# a whole match of "reveal cards never appeared" with zero rows logged, while
# the hand sat visibly untouched at five cards. test_button_bits_match_keymap
# now pins the two tables together.
# Send BUTTONS over the FIFO? OFF: measured 2026-09-03, FIFO button presses do
# nothing on this console while the keyboard path works immediately. Left as a
# flag rather than deleted because the bits may simply be wrong — if anyone
# measures a correct table, flip this back and re-verify with the pause menu,
# which is a free and harmless target.
INJECT_BUTTONS = False

BUTTON_BITS = {
    "cross": 1 << 0, "select_card": 1 << 0,
    "confirm_play": 1 << 3,        # Pyramid/Triangle — the on-screen PLAY prompt
    "moon": 1 << 1, "close_result": 1 << 1,
    "box": 1 << 2, "confirm_discard": 1 << 2, "start_match": 1 << 2,
    "pyramid": 1 << 3,
    "dpad_left": 1 << 4, "move_left": 1 << 4,
    "dpad_right": 1 << 5, "move_right": 1 << 5,
    "dpad_up": 1 << 6, "move_up": 1 << 6,
    "dpad_down": 1 << 7, "move_down": 1 << 7,
    "l1": 1 << 8, "r1": 1 << 9, "l3": 1 << 10, "r3": 1 << 11,
    "options": 1 << 12, "toggle_pause": 1 << 12,
    "share": 1 << 13, "touchpad": 1 << 14, "ps_button": 1 << 15,
}

# The stick directions, as axis deflections rather than buttons. walk_steps
# already drives movement this way; these are the press()-shaped equivalents so
# the camera probe does not remain on the dead keyboard path.
STICK_AXES = {
    "look_left": ("right_x", -0.8), "look_right": ("right_x", 0.8),
    "look_up": ("right_y", -0.8), "look_down": ("right_y", 0.8),
    "walk_left": ("left_x", -0.8), "walk_right": ("left_x", 0.8),
    "walk_up": ("left_y", -0.8), "walk_down": ("left_y", 0.8),
}

USE_INJECTED_INPUT = os.environ.get("BASEBALL_INJECT_INPUT", "1") != "0"


def _inject_press(action, hold_seconds):
    """Send one action over the FIFO. True if it was sent, False if unmapped.

    ALWAYS RELEASES, even if interrupted — a held button on a live console is
    far worse than a missed press.
    """
    # HARD OFF DURING TESTS, for the same reason can_use_background_input() is:
    # the offline suite stubs pyautogui but nothing stubs a FIFO write, so this
    # path would reach the REAL console and drive the game for real. It sits
    # ABOVE that guard in press(), so it needs its own — without this, adding
    # injected input silently re-opened the hole that guard was written to
    # close, and every `./run_tests.sh` would move the character.
    if os.environ.get("BASEBALL_TEST_RUN"):
        return False
    if not USE_INJECTED_INPUT:
        return False
    import analog_replay as ar
    if action in BUTTON_BITS and not INJECT_BUTTONS:
        # BUTTONS DO NOT WORK OVER THE FIFO. Measured 2026-09-03 on the live
        # console: `buttons 4096` (options) produced NOTHING after 4s, while the
        # keyboard path opened the pause menu in 0.5s. The bit values were never
        # confirmed — chiaki-patch/README.md says as much, and 1<<5 for
        # dpad-right famously did not move the PS5 dashboard.
        #
        # Returning True here was the bug: ar.send() succeeds because WRITING to
        # the pipe succeeds, so press() believed the button had been pressed and
        # never fell through to the keyboard path that works. A success path and
        # a no-op path with identical output — the exact shape catalogued in
        # CLAUDE.md, and it silently disabled every button in the system:
        # resets, menu navigation, card selection, match play.
        #
        # Sticks are unaffected and stay on the FIFO: they are proven by every
        # walk the router makes.
        return False
    if action in BUTTON_BITS:
        held, release = f"buttons {BUTTON_BITS[action]}", "buttons 0"
    elif action in STICK_AXES:
        axis, value = STICK_AXES[action]
        held, release = f"{axis} {ar.to_axis(value)}", f"{axis} 0"
    else:
        return False

    # A MISSING FIFO MUST NOT END THE RUN. ar.send() opens the pipe on every
    # call, so if chiaki restarted without it, this raises FileNotFoundError
    # straight through press() and kills an unattended cycle — over an input
    # method that has a working fallback sitting right below it. Degrade to the
    # keyboard path instead, and SAY SO: an input path that quietly stops
    # working is the exact failure that cost a full afternoon on 2026-09-01.
    try:
        try:
            ar.send([held])
            time.sleep(max(hold_seconds, 0.05))
        finally:
            ar.send([release])
    except OSError as e:
        print(f"  [inject] FIFO unavailable ({e.__class__.__name__}) — "
              f"falling back to the keyboard path for {action!r}")
        return False
    return True


def select_and_play(card_index: int, tactics_index: int = None,
                    look=None):
    """
    Navigate from the leftmost hand position to the target player card,
    select it, optionally also select a tactics card, then confirm Play.
    Indices are 0-based positions in the 5-card hand.

    IT HOMES FIRST AND FORGETS AFTERWARDS, exactly as select_and_discard does, and
    for the same reason its comment gives: a play RE-DEALS the hand, so the cursor
    ends up wherever the game put it, not where we left it. Without this the belief
    survives into the next turn and every move is measured from a position the
    cursor no longer holds.

    MEASURED, run 20260908_235423, one match of 15 turns:

        play turns that homed first (2, 9, 11, 14)      logged correctly 4 of 4
        play turns that did not (3, 4, 5, 6, 7, 10)     logged correctly 0 of 6
        Fisher exact p = 0.0048

    A turn only homed when a discard or a misfire happened to invalidate first.
    Turn 3 is the worked example, agreed by four independent sources: the hand read
    before the play held 8/1 at index 2 and 5/2 at index 3, the engine chose the 8,
    the reveal frame shows the 5/2 card at home plate, and the hand read afterwards
    still holds the 8. The selection landed one slot right of the target every time.

    Cost: four presses on a turn that would not otherwise have homed, about 0.32 s
    each, so roughly 7.6 s a match against six turns of wrong cards.
    """
    if look is None:
        # THE BLIND PATH, unchanged. Kept because a caller that cannot capture the
        # screen has nothing better available -- not because it is safe.
        reset_hand_cursor(force=True)
        _move_cursor_to(card_index)
        press("select_card")

        if tactics_index is not None:
            _move_cursor_to(tactics_index)
            press("select_card")

        press("confirm_play")
        # The hand is re-dealt behind this press. Drop the belief rather than guess.
        invalidate_cursor()
        return True

    return _verified_select_and_play(card_index, tactics_index, look)


# How many corrective presses before giving up. The walk is at most 4 slots, so
# anything past this is presses not landing at all, not a longer journey.
CURSOR_MAX_STEPS = 8

# LOOK AFTER THE ANIMATION, NOT DURING IT. The user, watching the stream
# (2026-09-10): "it quickly selected slot 1, mid animation of moving up deselected
# it." A card takes a moment to slide, and a frame grabbed mid-slide puts the disc
# somewhere between its two positions -- so the glow box, which is anchored on the
# disc, reads pixels that belong to neither. The walk then believed it was already
# at the tactics slot, skipped its move, and pressed select_card onto the card it
# had JUST selected, toggling it back off.
#
# These two values are not invented: they are the ones the standalone spike used
# when the closed loop ran correctly end to end on the console, and dropping them
# is what I broke when I moved that logic in here.
MOVE_SETTLE_SEC = 0.40
SELECT_SETTLE_SEC = 0.60

SELECT_ATTEMPTS = 2            # 1 swallowed select in 5 measured; the selection confirms each

# BEFORE PRESSING AGAIN, WAIT LONGER THAN THE ANIMATION -- because a press can be LATE
# rather than lost, and the two look identical at 0.6 s. Measured 2026-09-10: the lift and
# the drop both settle at ~550 ms when a press is handled promptly, but one deselect was
# still unlanded at 1.2 s. A retry that fires on a press still in flight presses TWICE and
# toggles the card back off. That is bounded, not silent: the selection check then fails
# and the loop refuses, so the cost is a wasted turn, never a wrong card committed.
SELECT_RETRY_CONFIRM_SEC = 1.6

# A LOOK THAT LANDS MID-ANIMATION IS NOT A READING, AND read_hand SAYS SO ITSELF.
# Reproduced at the user's insistence rather than retried past: sampling through a select
# animation, 3 frames of 45 came back with SEVEN rows. While a card is in flight it sits
# BETWEEN slot anchors, the five-slot fan correctly declines to fit, and the older UNGATED
# disc search runs instead -- documented as returning "3 to 8" positions, with no slots.
# Re-looking is right here and is NOT the "retry a stable misread" mistake (CLAUDE.md 4):
# the two are told apart by whether the answer changes, and this one does.
LOOK_RETRIES = 3
LOOK_RETRY_SEC = 0.25


def _look_settled(look):
    """A usable fan read, or a row count of 0 meaning THERE ISN'T ONE.

    It must not hand back the unusable read: the caller's guard tests the row count, and
    an ungated read that happens to return five rows would sail past it. Found by a
    mutant-driven test that then watched the walk press move_right EIGHT times against a
    screen it could not read at all.
    """
    glow, ys, n, sel = [], [], 0, []
    for attempt in range(LOOK_RETRIES):
        glow, ys, n, sel = look()
        if n == MAX_HAND_SIZE and any(y is not None for y in ys):
            return glow, ys, n, sel
        if attempt + 1 < LOOK_RETRIES:
            time.sleep(LOOK_RETRY_SEC)
    # AND THE SELECTION IS EMPTIED WITH IT. Returning n=0 alongside the bad frame's `sel`
    # is what made a forgetful caller dangerous rather than merely wrong: _select_verified
    # read `target in before` off an UNGATED frame, took its "already selected, no press
    # needed" branch, and confirm_play then committed whatever was really up. Reproduced:
    # select_and_play(3) returned True having pressed only move_right twice and
    # confirm_play, committing slot 1. Emptying it makes the failure direction "not
    # selected" (which presses) rather than "already selected" (which commits).
    return glow, ys, 0, []


def _walk_cursor_to(target, look):
    """Press toward `target`, LOOKING after every single press.

    Returns (ok, selected_slots). Never presses twice on one reading: a press count is
    exactly the thing that was wrong, so every step is re-measured. Which cards are
    SELECTED comes from the fan's own anchors, so this works from any starting state --
    including one with cards already selected.
    """
    import local_hand
    glow, ys, n, sel = _look_settled(look)
    cur = local_hand.cursor_slot(glow, sel)
    if n != MAX_HAND_SIZE or cur is None:
        print(f"  [cursor] cannot see the cursor (rows={n}, glow={glow}) — refusing")
        return False, sel
    steps = 0
    while cur != target:
        if steps >= CURSOR_MAX_STEPS:
            print(f"  [cursor] still at {cur} after {steps} presses — refusing")
            return False, sel
        press("move_right" if cur < target else "move_left")
        steps += 1
        time.sleep(MOVE_SETTLE_SEC)
        glow, ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print(f"  [cursor] the fan stopped reading mid-walk (rows={n}) — refusing")
            return False, sel
        cur = local_hand.cursor_slot(glow, sel)
        if cur is None:
            print(f"  [cursor] lost the cursor after {steps} press(es) "
                  f"(glow={glow}) — refusing")
            return False, sel
    if steps:
        print(f"  [cursor] verified on {target} after {steps} press(es)")
    return True, sel


def _select_verified(target, look):
    """Make sure `target` is SELECTED, and prove it before anything is committed.

    ALREADY SELECTED IS A SUCCESS, NOT A PRESS. Pressing select_card on a card that is
    already up toggles it back off -- which is how two attempts at p1+2 deselected the
    card they had just selected. Selection is now read absolutely from the fan anchors,
    so this can tell the two apart and is safe to run from any board state.

    A SWALLOWED select_card IS EXPECTED, AND RETRYING IT IS ONLY SAFE BECAUSE WE LOOK.
    Measured 2026-09-10 over a five-slot sweep: 1 of 5 select presses did not show up.
    Pressing again blind would risk DESELECTING one that did land, so each attempt is
    confirmed first, and a press that is merely LATE is waited out rather than repeated.
    """
    import local_hand
    _g, _ys, n, before = _look_settled(look)
    # THE GUARD _look_settled's DOCSTRING ASSUMES. It says the unusable read "must not"
    # be handed back "because the caller's guard tests the row count" -- and four of its
    # five callers had no such guard. On an ungated frame `before` is whatever the bad
    # read produced, and if it happens to contain the target this returns success WITHOUT
    # PRESSING, leaving confirm_play to commit whatever is actually up.
    if n != MAX_HAND_SIZE:
        print(f"  [cursor] cannot read the fan to check the selection (rows={n}) — "
              "refusing rather than assuming the card is already up")
        return False, before
    if target in before:
        return True, before

    # WHAT COUNTS AS "THE WRONG CARD WENT UP" IS A CHANGE, NOT A STATE. The first version
    # refused whenever ANY other card was raised -- which defeats the whole point of
    # reading selection absolutely, because a card selected before this call ever ran is
    # not an error. It cost the first turn of a live match: slot 3 was already up from
    # earlier testing, so selecting slot 4 was refused as "lifted [3], expected 4".
    sel = before
    for attempt in range(1, SELECT_ATTEMPTS + 1):
        press("select_card")
        time.sleep(SELECT_SETTLE_SEC)
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print(f"  [cursor] cannot read the fan after select_card (rows={n}) — "
                  "refusing; a press whose result cannot be seen is not a selection")
            return False, sel
        if target in sel:
            if attempt > 1:
                print(f"  [cursor] select_card landed on attempt {attempt}")
            return True, sel
        new = [i for i in sel if i not in before]
        if new:
            # something that was NOT up before has gone up, and it is not the target.
            # Pressing again compounds it.
            print(f"  [cursor] select_card raised {new}, expected {target} — refusing")
            return False, sel
        if attempt < SELECT_ATTEMPTS:
            time.sleep(SELECT_RETRY_CONFIRM_SEC)
            _g, _ys, n, sel = _look_settled(look)
            if n != MAX_HAND_SIZE:
                print(f"  [cursor] cannot read the fan on the late re-check (rows={n})"
                      " — refusing")
                return False, sel
            if target in sel:
                print(f"  [cursor] select_card landed late ({SELECT_RETRY_CONFIRM_SEC}s)")
                return True, sel
            print(f"  [cursor] select_card did not land (attempt {attempt}) — retrying")
    print(f"  [cursor] select_card never landed after {SELECT_ATTEMPTS} attempts — refusing")
    return False, sel


def _unwind_selection(before, look, ours):
    """Put back down anything raised since `before`. Best effort; never raises.

    A REFUSAL THAT LEAVES A CARD UP IS NOT A CLEAN REFUSAL. The commit path already
    clears strays with _deselect_verified, but the two EARLY refusals -- the walk and
    the select -- returned False with whatever they had already raised still lifted.
    Observed live 2026-09-16: the engine chose 8/0 + fielding boost, the tactics select
    could not be verified, the call refused honestly, and the 8/0 was left selected on a
    board the next caller would read as clean.

    That is CLAUDE.md 10.29 with the production refusal path as the poisoner rather than
    a human probe -- and the function's own comment already names the consequence: the
    retry selects its own target and confirm_play commits BOTH.

    ONLY WHAT THIS CALL RAISED, AND ONLY WHAT IT AIMED AT. `ours` is the set of slots
    this call deliberately targeted. Two exclusions, and both are load-bearing:

      * a card lifted BEFORE we ran belongs to whoever put it there, and clearing it
        would be the same overreach in the other direction;
      * a card that went up WITHOUT being aimed at is the "wrong card lifted" case, and
        _select_verified's own comment is explicit that "pressing again compounds it".
        test_verified_selection pins exactly one select press on that path -- a first
        version of this unwind pressed on the stray and took it to three.
    """
    try:
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print("  [cursor] cannot read the fan to unwind — leaving the board as is; "
                  "the next caller must re-read rather than assume it is clean")
            return False
        extra = sorted((set(sel) - set(before)) & set(ours))
        if not extra:
            return True
        for slot in extra:
            print(f"  [cursor] unwinding slot {slot}, raised by this refused attempt")
            ok, _s = _walk_cursor_to(slot, look)
            if ok:
                ok, _s = _deselect_verified(slot, look)
            if not ok:
                print(f"  [cursor] could NOT put slot {slot} back down — say so loudly "
                      "rather than let the next caller find it and commit it")
                return False
        return True
    except Exception as exc:
        print(f"  [cursor] unwind failed ({type(exc).__name__}: {exc})")
        return False


def _verified_select_and_play(card_index, tactics_index, look):
    """Read, step, verify, select, verify the selection, and only then commit.

    Returns True only when confirm_play was actually sent. False means NOTHING was
    committed and the caller should re-read and retry -- it must never be treated as a
    play, and it must never fall through to the blind path, which would make a refusal
    and a success indistinguishable (CLAUDE.md 10.1).

    A FALSE ALSO LEAVES THE BOARD AS IT FOUND IT, as far as it can. See
    _unwind_selection: an early refusal used to keep whatever it had already lifted.
    """
    # THE BOARD AS WE FOUND IT. Anything already up belongs to a previous caller and
    # is not ours to clear; the commit path below handles a stray that is still there.
    _g0, _ys0, n0, before_all = _look_settled(look)
    before_all = set(before_all) if n0 == MAX_HAND_SIZE else set()
    targets = {t for t in (card_index, tactics_index) if t is not None}

    for target in (card_index, tactics_index):
        if target is None:
            continue
        ok, _sel = _walk_cursor_to(target, look)
        if not ok:
            _unwind_selection(before_all, look, targets)
            invalidate_cursor()
            return False
        ok, _sel = _select_verified(target, look)
        if not ok:
            _unwind_selection(before_all, look, targets)
            invalidate_cursor()
            return False

    # COMMIT ONLY WHAT THE ENGINE CHOSE.
    #
    # _verified_select_and_play returns False WITHOUT undoing the selection it already
    # made, and nothing anywhere deselects -- `grep` for a deselect routine finds none.
    # So a refusal on the TACTICS walk leaves the player card lifted, run() re-reads and
    # calls play_one_turn again, the retry selects its own target, and confirm_play
    # commits BOTH. Reproduced: the engine chose slot 0, slot 2 was still up from the
    # previous attempt, and [0, 2] went in together.
    #
    # It is also reachable without a refusal: local_hand's own comment records that
    # find_tactics stops matching a card once it is selected, so a target can go
    # unreadable AT THE MOMENT IT LIFTS -- _select_verified then presses a second time,
    # and 1 in 5 of those presses is swallowed (the code's own measured figure), leaving
    # the card up.
    #
    # This is CLAUDE.md 10.29 with the production refusal path as the poisoner instead of
    # a human probe: "an investigation that leaves state behind poisons the next
    # experiment, and the result still looks like a finding".
    want = {t for t in (card_index, tactics_index) if t is not None}
    _g, _ys, n, sel = _look_settled(look)
    if n != MAX_HAND_SIZE:
        print("  [cursor] cannot read the fan before committing — refusing. A "
              "confirm_play whose lifted set was never seen is a blind commit.")
        invalidate_cursor()
        return False
    lifted = set(sel)
    extra = lifted - want
    if extra:
        # TRY TO PUT THEM DOWN, with the same walk-and-verify used to raise them.
        # select_card is a TOGGLE, so this is the documented way to clear one -- but it
        # is only safe because every step is confirmed against the screen.
        for slot in sorted(extra):
            print(f"  [cursor] slot {slot} is lifted and the engine did not choose it "
                  f"(it chose {sorted(want)}) — putting it back down before committing")
            ok, _s = _walk_cursor_to(slot, look)
            if ok:
                ok, _s = _deselect_verified(slot, look)
            if not ok:
                print(f"  [cursor] could not clear slot {slot} — REFUSING to commit. "
                      "Playing a card the engine did not choose is worse than playing "
                      "nothing; the caller will re-read and retry.")
                invalidate_cursor()
                return False
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE or set(sel) - want:
            print(f"  [cursor] after clearing, the lifted set is still {sel} against "
                  f"{sorted(want)} — refusing to commit")
            invalidate_cursor()
            return False
    if not want <= set(sel):
        print(f"  [cursor] the engine's cards {sorted(want)} are not all lifted "
              f"({sel}) — refusing to commit a partial play")
        invalidate_cursor()
        return False

    press("confirm_play")
    invalidate_cursor()
    return True


def _deselect_verified(target, look):
    """Press select_card to put a lifted card DOWN, confirmed against the screen.

    The mirror of _select_verified, and it exists for the same reason: select_card is a
    TOGGLE, so pressing blind on a card that is already down RAISES it. Every attempt is
    confirmed, and a press that is merely LATE is waited out rather than repeated.
    """
    _g, _ys, n, sel = _look_settled(look)
    if n != MAX_HAND_SIZE:
        return False, sel
    if target not in sel:
        return True, sel                      # already down; nothing to do
    for attempt in range(1, SELECT_ATTEMPTS + 1):
        press("select_card")
        time.sleep(SELECT_SETTLE_SEC)
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            return False, sel
        if target not in sel:
            return True, sel
        if attempt < SELECT_ATTEMPTS:
            time.sleep(SELECT_RETRY_CONFIRM_SEC)
            _g, _ys, n, sel = _look_settled(look)
            if n == MAX_HAND_SIZE and target not in sel:
                return True, sel
    print(f"  [cursor] slot {target} would not go back down after {SELECT_ATTEMPTS} "
          "attempts")
    return False, sel


def select_and_discard(card_index: int, look=None):
    """
    Navigate to a card and discard it for a replacement.

    Confirmed live (2026-08-23): discarding isn't a single action — after
    confirm_discard, the game deals a replacement card and auto-lifts it
    with its own "PLAY" prompt, which still needs confirm_play to
    actually commit it as this turn's play. Skipping that second press
    leaves the game stuck waiting on a discard-and-forget script.

    HOMES FIRST, always. Everywhere else the remembered cursor position is a
    reasonable optimisation, but a discard is irreversible and lands on the
    wrong card if the belief has drifted by even one slot — which is exactly
    what a dropped keypress does, and it is invisible to a press count. Observed
    live 2026-08-28: the engine chose to discard a power-4 player and a tactics
    card was thrown instead. The ban scanner learned this same lesson and
    resolved it by trusting a measurement over the press count; homing is the
    cheap version of that for a five-slot hand.
    """
    if look is None:
        reset_hand_cursor(force=True)
        _move_cursor_to(card_index)
        press("select_card")
        press("confirm_discard")
        # The replacement card is dealt into this slot and auto-lifted, so the
        # cursor is wherever the game put it — not necessarily where we left it.
        # Drop the belief rather than guess; the next navigation re-homes.
        invalidate_cursor()
        press("confirm_play")
        return True

    # VERIFIED. This function's own docstring records a discard landing on the
    # wrong card live (2026-08-28: the engine chose a power-4 player and a tactics
    # card was thrown), and homing was the cheap mitigation available then. Reading
    # the screen is the real one: the same walk-and-verify the play path uses, and
    # the lift must name THIS card before anything irreversible is pressed.
    ok, _sel = _walk_cursor_to(card_index, look)
    if not ok:
        invalidate_cursor()
        return False
    ok, _sel = _select_verified(card_index, look)
    if not ok:
        invalidate_cursor()
        return False
    press("confirm_discard")
    # Past this point the game deals the replacement and auto-lifts it with its own
    # PLAY prompt; confirm_play commits THAT card as this turn's play. There is
    # nothing left to verify -- the choice was made at confirm_discard.
    invalidate_cursor()
    press("confirm_play")
    return True


# NAVIGATE BY LOOKING, NOT BY COUNTING.
#
# select_bans_and_start_full below dead-reckons: it presses move_down (row - current_row)
# times and then presses select_card, and NOTHING EVER LOOKS. Its own docstring states the
# two assumptions -- that N presses land on absolute row N, and that banning does not shift
# the cursor -- and neither is checked at runtime. One press dropped and every later target
# is a DIFFERENT CARD, banned silently.
#
# It is not hypothetical. The code's own comment records "three of five real ban sequences
# finished at 2/3 and the match started anyway, two seconds later, with a ban set the
# engine never chose", and a live run on 2026-09-13 reported 2 of 3 at confirm while the
# scrollbar sat at level 1 after navigating toward a row-3 target -- it never got there.
# ACTION_DELAY is 0.25 s and a press that causes a SCROLL needs about twice that to settle,
# which is the likely trigger; the missing verification is why the trigger matters.
#
# This is the shape that took route walking from 5/10 to 40/40 (CLAUDE.md section 8): take
# the position from the SCREEN, never from the count of what was sent.
#
# `look()` is supplied by the caller and returns (absolute_row, col) or None -- input_
# controller must not import ban_grid, and the caller already owns both the fitted rows and
# the scroll level. `confirm_ban()` returns True once the X is actually on the card.
# ON since 2026-09-13, measured against the dead-reckoned path twice.
#
#   simulated grid, two presses dropped   old bans (2,0) and (3,2) -- two cards the engine
#                                         never chose, and only two of three
#                                         new bans (1,3) (2,1) (3,3), exactly as asked
#   live, same collection, same 3 cards   old: counter 2 of 3, scrollbar three rows short
#                                         new: counter 3 of 3, each X confirmed at the
#                                              press, in 16 s
#
# With nothing dropped both are correct, so this is not the happy path -- it is the failure
# path, which is the one that bans a card nobody chose in a match that costs $50.
VERIFY_BAN_NAVIGATION = True
BAN_NAV_MAX_STEPS = 14             # per target; a grid is 5 wide and ~8 deep
BAN_NAV_SETTLE = 0.55              # a scrolling press needs about twice ACTION_DELAY


BAN_NAV_MAX_BLIND = 10             # consecutive unreadable frames per target


def select_bans_verified(grid, banned_positions, look, confirm_ban=None,
                         before_confirm=None, log=print, on_blind=None,
                         banned_set=None, on_wrong_ban=None):
    """Place the bans, checking the cursor on the screen before every select_card.

    Returns the list of positions it actually banned. A target it cannot reach is REPORTED
    and skipped rather than toggled blind: a select_card on the wrong cell bans a card the
    engine did not choose, which is strictly worse than one missing ban.
    """
    targets = sorted(
        ((row, col) for row, col, _c in grid if (row, col) in banned_positions))
    if len(targets) != len(banned_positions):
        raise ValueError(f"ban positions not all in grid: asked {sorted(banned_positions)}, "
                         f"matched {targets}")
    placed = []
    toggled = 0                    # select_card presses, whether or not they confirmed
    for want in targets:
        # SEPARATE BUDGETS. Both moves and blind waits used to spend the same 14, so a
        # far target with one late frame per scrolling press ran out before arriving:
        # (6, 2) needs 2*6 + 2 + 1 = 15 and was silently skipped, reported as
        # ban_nav_incomplete, and the match played with 2 of 3 bans. A blind frame is
        # not a failed step toward the target; it is no step at all.
        moves = blind = 0
        reached = False
        # AN EXCEPTION HERE USED TO LEAVE THE SCREEN MID-CHANGE. Neither look() nor
        # confirm_ban was wrapped, and neither is ban_cursor_absolute / ban_x_on. A raise
        # on the 14th look left the bans ON SCREEN with confirm_play never pressed, and
        # in run() it unwound before bans_done_this_match and acted_screen were set -- so
        # the next poll re-entered with the cached collection and TOGGLED THE BANS BACK
        # OFF. That is the one path that defeats the C3 guard, and the verified navigator
        # made it likelier by adding a screen read per press.
        try:
            while moves < BAN_NAV_MAX_STEPS and blind < BAN_NAV_MAX_BLIND:
                here = look()
                if here is None:
                    blind += 1
                    time.sleep(BAN_NAV_SETTLE)
                    continue
                if here == want:
                    # WHAT WAS BANNED BEFORE THIS PRESS. `confirm_ban` can only say
                    # whether an X is on the cell we AIMED at, so an X that landed
                    # somewhere else reads as a missing ban and the counter still
                    # says 3/3. The difference of the full set names the actual card.
                    _before = banned_set() if banned_set is not None else None
                    press("select_card")
                    toggled += 1
                    reached = True
                    time.sleep(BAN_NAV_SETTLE)
                    _after = banned_set() if banned_set is not None else None
                    if _before is not None and _after is not None:
                        _new = _after - _before
                        if _new == {want}:
                            placed.append(want)
                        elif _new:
                            # A CARD THE ENGINE DID NOT CHOOSE IS NOW BANNED. Not
                            # re-pressed: select_card is a TOGGLE and the cursor is
                            # demonstrably not where we believed, so a second press
                            # would land somewhere else again. Report, record, and
                            # do NOT count it as placed.
                            log(f"  [ban] WRONG CARD: pressing at {want} put an X on "
                                f"{sorted(_new)} — the cursor was not where the last "
                                f"look said. NOT re-pressing; a toggle from an unknown "
                                f"cell bans another one.")
                            if on_wrong_ban is not None:
                                on_wrong_ban(want, _new)
                        else:
                            log(f"  [ban] select_card at {want} placed no X anywhere "
                                "— leaving it")
                        break
                    if confirm_ban is None or confirm_ban(want):
                        placed.append(want)
                    else:
                        # THE TOGGLE DID NOT TAKE. Pressing again is not safe --
                        # select_card is a TOGGLE, so a second press on a card that DID
                        # ban un-bans it. Report.
                        log(f"  [ban] select_card at {want} did not place an X — leaving it")
                    break
                # one step toward the target, then look again
                if here[0] < want[0]:
                    press("move_down")
                elif here[0] > want[0]:
                    press("move_up")
                elif here[1] < want[1]:
                    press("move_right")
                else:
                    press("move_left")
                moves += 1
                time.sleep(BAN_NAV_SETTLE)
        except Exception as e:
            log(f"  [ban] reading the ban screen raised while placing {want} "
                f"({type(e).__name__}: {e}) — committing what IS placed rather than "
                "leaving the screen mid-change for the next poll to un-toggle")
        if not reached:
            log(f"  [ban] could not reach {want} in {moves} moves / {blind} blind frames "
                f"— NOT toggling blind")

    # THE PROBE CHECKED THE SENSOR BEFORE, NEVER DURING, and one success committed to
    # this path with no way back. A cursor that answers the probe and then goes blind
    # placed ZERO bans here and still pressed confirm_play -- which is Triangle, i.e.
    # PLAY -- starting a match that had already been debited $50, completely unbanned.
    # That is the exact failure the probe was added to close, moved one look() later.
    #
    # Only when NOTHING was toggled. A target that was pressed but could not be
    # confirmed may well BE banned (the selection splash makes ban_x_on read False on a
    # card that is banned), and dead-reckoning over that would toggle it back off.
    if toggled == 0 and on_blind is not None:
        log("  [ban] the cursor answered the probe and then went blind: NOTHING was "
            "toggled. Falling back to the dead-reckoned path rather than pressing PLAY "
            "on a match that is paid for and unbanned.")
        on_blind()
        return sorted(banned_positions)
    if before_confirm is not None:
        try:
            before_confirm()
        except Exception as e:
            log(f"  [ban] pre-confirm verification raised ({e}) — continuing.")
    # back to the top before confirming, by LOOKING rather than counting.
    # WRAPPED for the same reason as the placement loop: a reader that raises HERE
    # skipped the confirm entirely, and an unconfirmed ban screen is un-toggled by the
    # next poll. Triangle commits from anywhere, so an unwind that stops early costs
    # nothing; not confirming costs the whole ban set.
    try:
        for _ in range(BAN_NAV_MAX_STEPS):
            here = look()
            if here is None or here[0] <= 0:
                break
            press("move_up")
            time.sleep(BAN_NAV_SETTLE)
    except Exception as e:
        log(f"  [ban] reading the ban screen raised while returning to the top "
            f"({type(e).__name__}: {e}) — confirming from here; Triangle commits "
            "from anywhere")
    press("confirm_play")
    press("confirm_play")
    return placed


def select_bans_and_start_full(grid: list, banned_positions: set,
                               before_confirm=None):
    """
    Scroll-aware version of select_bans_and_start for a collection that
    extends below the initially-visible rows. grid: list of
    (absolute_row, col, PlayerCard) — absolute_row is the card's row
    position in the full (unscrolled) collection, as gathered by a
    caller that scrolled through and read it via vision.

    Confirmed live (2026-08-23): after the first move_down (which just
    moves the cursor within the still-fully-visible page), every further
    move_down scrolls the viewport by exactly 1 row while keeping the
    cursor at the same visual row. Net effect: pressing move_down N
    times from a fresh (0, 0) state always lands the cursor at absolute
    row N, regardless of any scrolling along the way — no separate
    scroll-then-navigate step needed, just move_down straight to the
    target row.

    Assumes the caller starts at (0, 0) and that banning a card doesn't
    itself shift the cursor's row. Processes bans in row order (always
    moving down, never back up) to avoid needing to reverse-navigate.
    """
    # N1 FIX: select by (row, col) POSITION, never by name. Name matching
    # toggled every grid entry sharing a name — and a mis-resolved OCR read can
    # legitimately put the same name at two positions, so one intended ban
    # became two physical toggles (verified: 4 toggles for 3 bans). Position is
    # unambiguous by construction.
    targets = sorted(
        ((row, col, card) for row, col, card in grid if (row, col) in banned_positions),
        key=lambda t: t[0],
    )
    if len(targets) != len(banned_positions):
        raise ValueError(
            f"ban positions not all present in grid: asked for "
            f"{sorted(banned_positions)}, matched {sorted((r, c) for r, c, _ in targets)}"
        )

    current_row, current_col = 0, 0
    for row, col, card in targets:
        for _ in range(row - current_row):
            press("move_down")
        col_diff = col - current_col
        move = "move_right" if col_diff > 0 else "move_left"
        for _ in range(abs(col_diff)):
            press(move)
        press("select_card")
        current_row, current_col = row, col

    # Verification hook. The counter can ONLY be read here: it is legible on
    # the literal last frame of the ban screen, and the caller's old
    # post-confirm read always landed after the screen was gone, so it had
    # never once succeeded live ("bans NOT verified this match", every match).
    # Frame audit of 2026-08-26 measured 4.20s / 5.69s / 5.85s of ban screen
    # remaining at this point against a 0.26s read — an 8x margin. Do NOT move
    # this below the move_up loop: the cursor only reaches the top with
    # 0.53-1.11s left.
    if before_confirm is not None:
        try:
            before_confirm()
        except Exception as e:
            # Verification must never cost a ban. The presses below are the
            # actual work; a failed read is a reporting problem.
            print(f"  [ban] pre-confirm verification raised ({e}) — continuing.")

    for _ in range(current_row):  # back to the top before confirming
        press("move_up")

    # M11: TWO confirm_play presses, deliberately. The first commits the ban
    # selection; the second dismisses the confirmation prompt the game shows
    # afterwards. Empirically required — this path ran successfully through
    # every ban screen of the 2026-08-24 live session. NOT verified against the
    # game's UI frame-by-frame, so if ban selection ever starts failing, an
    # extra/missing press here is a prime suspect. Do not "clean up" to a
    # single press without live-testing it.
    press("confirm_play")
    press("confirm_play")


# --- Is the game actually receiving our input? -----------------------------
# The most expensive failure in this project is a measurement taken while the
# chiaki window did NOT have keyboard focus: every press vanishes, the screen
# never changes, and the numbers that come back look like real data. Two full
# test runs were thrown away to this.
#
# A REJECTED APPROACH, recorded so nobody tries it again: the game draws a
# white aiming reticle at the view centre, and it looked like a focus lamp.
# It is not. The reticle is rendered by the PS5, so macOS focus cannot affect
# it — measured with a real focus loss (frontmost genuinely "Terminal"), the
# reticle was still there, 14 bright pixels against 5 while focused. It is also
# unstable as a target: the typewriter sways behind it, swinging the local
# background between white and black, which defeats any fixed threshold.
#
# Ask the window manager instead. It is authoritative, costs ~317ms, and does
# not care what the game is drawing.
FOCUS_QUERY_TRIES = 3
FOCUS_QUERY_RETRY_SEC = 0.25

_FRONTMOST_SCRIPT = ('tell application "System Events" to get name of first '
                     'application process whose frontmost is true')


def _frontmost_app_darwin() -> str:
    try:
        out = subprocess.run(["osascript", "-e", _FRONTMOST_SCRIPT],
                             capture_output=True, text=True, timeout=5.0)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _frontmost_app_windows() -> str:
    """Active window TITLE on Windows — not a process name.

    has_focus() does a substring match, so a title works for the same purpose,
    but the two are not interchangeable: a title is whatever the app chose to
    draw in its title bar and can change while the app runs. If chiaki-ng on
    Windows titles its window something without "chiaki" in it, this returns a
    string that never matches and has_focus() fails CLOSED — no presses, rather
    than presses into the wrong window. That is the safe direction, but it will
    look like "the automation does nothing", so check here first if it does.
    """
    try:
        import pygetwindow
        win = pygetwindow.getActiveWindow()
        return (win.title or "") if win is not None else ""
    except Exception:
        return ""


def frontmost_app() -> str:
    """Name of the frontmost application, or "" if it cannot be read."""
    if sys.platform == "darwin":
        return _frontmost_app_darwin()
    if sys.platform == "win32":
        return _frontmost_app_windows()
    return ""


def has_focus() -> bool:
    """True if a press may be ATTEMPTED. NOT evidence that one was acted on.

    With background input available this is unconditionally True, because
    CGEventPostToPid reaches the process whether or not it is frontmost —
    verified live while the user worked in another app. Gating on frontmost
    there would refuse every press for a reason that no longer applies.

    SO IT REDUCES TO "a chiaki process exists", and callers have read more into
    it than that. CGEventPostToPid reports nothing back, and a modal Qt dialog
    inside chiaki will swallow the key it delivers — so a True here is
    compatible with no input reaching the game at all. It is deliberately left
    this way: no delivery function consults it, so tightening it would refuse
    presses that do land. DO NOT use it to diagnose a failed press; measure the
    transport instead (reset_env._probe_transports).
    """
    if can_use_background_input():
        return True
    return _has_focus_frontmost()


def _has_focus_frontmost() -> bool:
    """True if chiaki is frontmost, i.e. keystrokes will actually reach it.

    Callers should treat False as "do not measure, do not press" rather than
    retrying: this process cannot take focus back from the user, so spinning on
    it burns time against a problem only they can fix.
    """
    # RETRIED. The osascript query is flaky under load and returns "" or a
    # stale answer occasionally; a single transient miss killed a live walk
    # with the self-contradicting message "chiaki is not frontmost ('chiaki'
    # is)" — the abort path re-queried and got the right answer. Focus does not
    # flicker in reality, so disagreement between consecutive reads means the
    # QUERY is unreliable, not the focus. Only a consistent negative counts.
    import time as _t
    for attempt in range(FOCUS_QUERY_TRIES):
        if CHIAKI_WINDOW_PROCESS_NAME.lower() in frontmost_app().lower():
            return True
        if attempt < FOCUS_QUERY_TRIES - 1:
            _t.sleep(FOCUS_QUERY_RETRY_SEC)
    return False


# --- Is the GAME in a state where input does what we expect? ---------------
# The user flagged that the little white centre dot vanishes when input stops
# working, and they were right about the symptom even though the cause is not
# macOS focus (the reticle is drawn by the PS5 and survives a real focus loss —
# verified with frontmost genuinely "Terminal"). What it actually tracks is
# whether the game is in interactive gameplay at all.
#
# MEASURED over logged frames, as centre-vs-surround contrast:
#
#     gameplay (reticle drawn)   207 .. 214
#     pause menu (no reticle)      0 ..   1
#     loading                     22 .. 203   (some already show the world)
#
# Two orders of magnitude apart, so the threshold is not delicate. Contrast
# rather than an absolute level because the background behind the dot swings
# from white to black as the typewriter sways — a fixed level read the same
# scene as both focused and unfocused depending on where the roller was.
# RE-MEASURED 2026-08-28 for the game-window capture. The old (0.4840, 0.5248)
# was calibrated against a differently-framed capture and points at plain
# background here — contrast read 2 where gameplay should read ~200, so
# in_gameplay() returned False on live gameplay frames. Found by taking the
# per-pixel MINIMUM across five gameplay frames: the reticle is the one bright
# point that survives every scene, and it sits dead centre.
RETICLE_XY_FRAC = (0.4995, 0.5000)

# FRACTIONS of frame width, not pixels. As absolutes these silently changed
# meaning with the capture size — the ring is meant to sample the immediate
# surroundings of the dot, and at 3360px wide a 22px ring is a quarter the
# intended area. Values match the original 5px/22px at 1920 wide.
RETICLE_INNER_FRAC = 0.0026
RETICLE_OUTER_FRAC = 0.0115
RETICLE_MIN_CONTRAST = 35.0     # kept for diagnostics; see RETICLE_MIN_DOTNESS

# BRIGHTNESS ALONE DOES NOT SEPARATE. Measured over 102 frames of a full walk
# (bright rooms and dark stairwells) against the screens that must be rejected:
#
#     gameplay      contrast min 39, p5 105, median 195
#     PS5 overlay   contrast 67
#     host list     contrast 45
#
# The ranges overlap, so any threshold either misses gameplay in dark areas or
# accepts the overlay. What distinguishes them is SHAPE: the reticle is a few
# bright pixels with darker pixels all around, while the overlay's brightness
# comes from UI edges and panels. Requiring the bright region to be CONFINED
# separates them completely — gameplay bottoms at 31, and all three non-gameplay
# screens score exactly 0.
RETICLE_MIN_DOTNESS = 15.0


def reticle_contrast(img) -> float:
    """Brightness of the centre dot above its immediate surroundings."""
    import numpy as np
    w, h = img.size
    cx, cy = int(w * RETICLE_XY_FRAC[0]), int(h * RETICLE_XY_FRAC[1])
    a = np.asarray(img.convert("L"), dtype=float)
    i = max(2, int(w * RETICLE_INNER_FRAC))
    o = max(i + 3, int(w * RETICLE_OUTER_FRAC))
    core = a[cy - i:cy + i, cx - i:cx + i]
    ring = a[cy - o:cy + o, cx - o:cx + o]
    if core.size == 0 or ring.size == 0:
        return 0.0
    return float(core.max() - np.median(ring))


def reticle_dotness(img) -> float:
    """How much the centre looks like a small bright DOT rather than any bright thing.

    Brightness lift, discounted by how much of the surrounding area shares that
    brightness. A dot lifts sharply and is confined; an edge or panel lifts and
    spreads.
    """
    import numpy as np
    w, h = img.size
    a = np.asarray(img.convert("L"), dtype=float)
    cx = int(w * RETICLE_XY_FRAC[0])
    cy = int(h * RETICLE_XY_FRAC[1])
    r = max(4, int(w * RETICLE_OUTER_FRAC))
    patch = a[cy - r:cy + r, cx - r:cx + r]
    if patch.size == 0:
        return 0.0
    core = patch[r - 2:r + 2, r - 2:r + 2]
    if core.size == 0:
        return 0.0
    lift = float(core.max() - np.median(patch))
    spread = float((patch >= core.max() - 20).mean())
    return lift * (1.0 - spread)


def in_gameplay(img) -> bool:
    """True if the aiming reticle is drawn, i.e. the world is interactive.

    Distinct from has_focus(): that asks whether keystrokes reach the app, this
    asks whether the game will act on them. A paused or loading game has focus
    and ignores movement input entirely — and so does a game sitting behind the
    PS5 home overlay, which is what a brightness-only test used to accept.
    """
    return reticle_dotness(img) >= RETICLE_MIN_DOTNESS


# --- Camera pitch: homed against its endstop, not measured ------------------
# Pitch has no HUD readout — the compass bar is screen-fixed and reads the same
# bearing at every pitch — so there is nothing to close a loop on. Worse, one
# press moves the view more than 140px, so it is coarser than yaw.
#
# But the axis is CLAMPED at both ends (a limit on how far up and down you can
# look), and a hard stop is an absolute reference. So pitch is handled the way
# a stepper is homed: drive to the endstop, then count steps back. No readout
# needed, and it re-derives absolute pitch from any unknown starting position.
#
# MEASURED from the top of the stairs, 0.05s presses, mean frame delta:
#     up:    37.7  30.2  11.7   3.0  4.5 | 1.2  0.8  1.3  0.9  1.4
#     down:   4.7   2.9  22.8  44.7 34.1  25.7 15.6  3.7 | 0.8  0.9
# Moving deltas run 3-45; parked against the stop they sit under 1.5. A 10x gap,
# so the stop threshold is not delicate. Full range is about 8 presses.
PITCH_STEP_SEC = 0.05
PITCH_STOP_DELTA = 1.5        # absolute floor for a very still scene
PITCH_NOISE_MULT = 1.6        # a press must beat the scene's own animation
PITCH_STOP_FRAC = 0.20        # ...but mainly: quiet means well under the
                              # biggest movement this sweep actually produced
PITCH_STOP_CONFIRM = 2        # consecutive quiet frames before believing it
PITCH_MAX_PRESSES = 14        # range is ~8; more than this means something is wrong
# RE-MEASURED 2026-08-27 after the capture changed to game-only pixels.
# From the bottom stop, stepping up at PITCH_STEP_SEC each:
#      6  desk edge, still looking at the floor
#     10  typewriter visible, still tilted down
#     14  LEVEL — typewriter, its Save prompt, the room behind it
#     17  ceiling light fixtures
#     20  ceiling
# The old value of 2 was calibrated when the capture was the whole desktop with
# the game as a window inside it. Left unchanged it homed the camera at the
# floor, which is why a 360 sweep of a landing came back as eight tiles of
# floorboards and the navigation had nothing to steer by.
PITCH_STEPS_FROM_BOTTOM = 14   # measured: +2 from the floor stop is level


def _pitch_band(img):
    import numpy as np
    a = np.asarray(img.convert("L"), dtype=float)
    h, w = a.shape
    return a[int(h * 0.20):int(h * 0.90), int(w * 0.42):int(w * 0.78)]


def home_pitch(capture, action="look_up", log=None):
    """Drive pitch to its hard limit. Returns presses used, or None if it never
    settled — which means the camera is not responding and the caller must not
    assume a known pitch."""
    import time

    import numpy as np
    # MEASURE the noise floor before pressing anything. The scene animates on
    # its own — NPCs idle, signs flicker — and how much it animates depends on
    # where you are standing, so no constant can express "not moving". Two
    # frames with no input give the answer directly, and "parked against the
    # endstop" is then just "indistinguishable from doing nothing".
    prev = _pitch_band(capture())
    time.sleep(0.55)
    cur0 = _pitch_band(capture())
    noise = float(np.abs(cur0 - prev).mean())
    prev = cur0
    if log:
        log(f"      noise floor {noise:.2f} (no input)")
    quiet = 0
    biggest = 0.0
    for i in range(1, PITCH_MAX_PRESSES + 1):
        press(action, hold_seconds=PITCH_STEP_SEC, post_delay=0.30)
        time.sleep(0.55)
        cur = _pitch_band(capture())
        delta = float(np.abs(cur - prev).mean())
        prev = cur
        biggest = max(biggest, delta)
        # RELATIVE to the largest movement seen, not an absolute level. A fixed
        # threshold of 1.5 was measured in a window; fullscreen has livelier
        # scenery and the frame never sits quieter than ~5 even when the camera
        # is hard against the stop, so homing ran to its iteration limit and
        # reported failure while parked at the endstop the whole time.
        stop_at = max(PITCH_STOP_DELTA, noise * PITCH_NOISE_MULT,
                      PITCH_STOP_FRAC * biggest)
        if log:
            log(f"      {action} #{i} delta {delta:.2f} (stop under {stop_at:.2f})")
        quiet = quiet + 1 if delta < stop_at else 0
        if quiet >= PITCH_STOP_CONFIRM:
            return i
    return None


def level_pitch(capture, steps=None, log=None):
    """Put the camera at a known, level pitch regardless of where it started.

    Homes DOWNWARD, not up. Both are hard stops, but only the down stop is
    reliably detectable: homing up gave a flat 6-10 delta for all 14 presses
    and never settled (the ceiling keeps producing moderate frame change),
    while homing down reads 108, 33, 33, 4, 3 — unmistakable.

    MEASURED from the bottom stop, in fullscreen:
        +0  floor planks
        +1  floor, edge of furniture
        +2  LEVEL — room, clock, doorway visible
        +3  ceiling light fixtures
    Four positions in the entire range, so this is coarse but repeatable, and
    repeatable is what the walk needs.

    RETURNS WHETHER THE FLOOR STOP WAS CONFIRMED. False does not mean the
    presses were skipped -- every press below still happens, in the same order,
    and a False result is still a best effort at a level camera. It means
    home_pitch never saw the stop, so the count-up started from an UNKNOWN
    pitch and the caller must not assume a known one. doorway_pitch treats the
    same verdict as decisive and refuses to press at all, because its 22 is
    only meaningful from a confirmed stop; this function is the coarse variant
    that presses anyway and SAYS SO.

    Until patch57 it returned a literal True on every path while promising
    "False means homing failed and pitch is NOT known", so any caller branching
    on the result was branching on a constant. The promise came back rather
    than the constant, because the information exists -- home_pitch's own
    verdict -- and throwing it away is §10.1's measurement taken and discarded.
    """
    import time
    if steps is None:
        steps = PITCH_STEPS_FROM_BOTTOM
    homed = home_pitch(capture, "look_down", log=log) is not None
    if not homed:
        # Already parked at the stop is indistinguishable from never reaching
        # it, and both are recoverable here: pressing down again is harmless,
        # so drive it firmly to the floor and count up from there -- and report
        # the unconfirmed home, which is the one thing the caller cannot see.
        for _ in range(4):
            press("look_down", hold_seconds=PITCH_STEP_SEC, post_delay=0.25)
        time.sleep(0.5)
    for _ in range(steps):
        press("look_up", hold_seconds=PITCH_STEP_SEC, post_delay=0.30)
    time.sleep(0.5)
    return homed


# The hardware half of the id. ioreg is a subprocess with a 5s timeout, and a
# machine's hardware UUID cannot change while the process runs, so it is
# memoised for the life of the process. The SCREEN half is not — see below.
_MACHINE_HOST = None

_MACHINE_ID = None

# The last id machine_id() built for itself. An id that differs from this was
# assigned by hand (tests fake a second computer that way), and an explicit
# override is a deliberate act, not staleness — so it is returned verbatim and
# never overwritten by re-derivation.
_MACHINE_ID_DERIVED = None


def _machine_host():
    """Per-machine identifier, memoised: hardware UUID, or a MAC fallback.

    HOSTNAME IS NOT AN IDENTIFIER HERE. Both of this project's machines are
    named the same, so hostname|arch|screen is identical on both and each would
    have read the other's geometry out of the shared cache — the precise bug
    machine_id() exists to prevent, reintroduced by trusting a name.
    """
    global _MACHINE_HOST
    if _MACHINE_HOST is None:
        try:
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5).stdout
            _MACHINE_HOST = out.split('"IOPlatformUUID" = "')[1].split('"')[0]
        except Exception:
            # Not macOS (the ROG Ally), or ioreg unavailable. uuid.getnode() is
            # stdlib and returns the MAC address — per-machine where hostname
            # is not, since both of these computers share a name.
            import uuid as _uuid
            _MACHINE_HOST = f"node:{_uuid.getnode():012x}"
    return _MACHINE_HOST


def _screen_geometry():
    """'WxH' of the primary display, or 'unknown'.

    READ FRESH ON EVERY CALL, deliberately. This is the one part of the id that
    can change while the process is running — plugging in an external display,
    unplugging one, or changing which display is primary all move
    mss.monitors[1]. Memoising it is what made the id go stale; see machine_id.

    Measured cost: 1.3ms median (the first call pays ~105ms of mss import).
    machine_id() is called a handful of times per process — twice at import for
    the two geometry caches, once per window_drift(), and once per cache SAVE,
    which for view_bounds only happens when a wider extent is discovered — so
    there is nothing here worth caching and no throttle to get wrong.
    """
    try:
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[1]
            return f"{mon['width']}x{mon['height']}"
    except Exception:
        return "unknown"


def _on_machine_id_changed(old, new):
    """The display changed under a running process. Say so, and drop what is
    now mislabelled.

    RE-DERIVING ALONE WOULD BE A WORSE BUG THAN THE STALE ID. _VIEW_CACHE is
    loaded ONCE at import under the id current at that moment, and
    _save_view_cache() writes the WHOLE in-memory dict under machine_id() as it
    stands at save time. So a bare re-derive takes display A's measured bounds
    and files them under display B's key — turning a wrong read that lasts one
    process into a wrong calibration that lives on disk and is believed by
    every future run on display B. Reloading the cache for the new id is what
    makes re-derivation safe, and it is not optional.

    IT WARNS RATHER THAN RAISING, because raising here would be silent. Of the
    six places that call machine_id(), FIVE wrap it in `except Exception` and
    swallow it: _load_view_cache, _save_view_cache, _load_window_reference, and
    compass's _load_scale_cache / _save_scale_cache. Only
    save_window_reference() would propagate. A raise would therefore be
    indistinguishable from doing nothing in almost every caller — the exact
    shape in CLAUDE.md's diagnosis catalogue — while also killing an unattended
    run for a condition it could have reported.

    WHAT THIS DOES NOT REACH: compass._SCALE_CACHE is the same pattern in a
    module that imports this one, so it cannot be invalidated from here. Its
    inner key carries the frame geometry, which gives it incidental protection
    a display change usually trips, but that is luck rather than a guarantee.
    The warning says to restart because that is the only thing that clears
    every in-memory cache in the process.
    """
    global _VIEW_CACHE
    sys.stderr.write(
        f"WARNING: the display changed under this process. machine_id went\n"
        f"         {old!r}\n      -> {new!r}\n"
        f"         Geometry measured from here on is filed under the NEW id.\n"
        f"         view_bounds was reloaded for it; compass's scale cache was\n"
        f"         NOT (it lives in another module) — restart to be sure.\n")
    _VIEW_CACHE = _load_view_cache(new)


def machine_id():
    """Stable identifier for the computer this is running on.

    The geometry caches hold px-per-90-degrees, the view centre, and the game
    window's screen rect. All are properties of THIS machine's display and
    window placement. Carrying them to another computer would silently apply
    one machine's geometry to another's frames, which is the exact failure that
    produced confident, wrong headings for hours — a bearing that reads fine
    and is 8 degrees out because the dock sat where the game used to be.

    So the caches are keyed by machine and the file travels safely: a new
    computer simply misses on lookup and measures its own values, while the
    original machine's entries stay valid if the project moves back.

    Screen size is folded in because one laptop can drive different external
    displays, and the geometry differs per display, not just per machine.

    THE SCREEN HALF IS RE-READ ON EVERY CALL. It used to be memoised with the
    rest of the id, which meant a display change MID-PROCESS left the id
    pointing at the previous display: geometry newly measured on display B was
    filed under display A's key, and the next run on B read A's calibration
    back — precisely the bug this function exists to prevent, arrived at from
    inside one process instead of across two machines.

    The sharpest case was window_reference.json, whose value is a bare screen
    rect with no secondary geometry key to catch the mismatch: a stale id makes
    window_drift() compare display B's window against display A's reference and
    call a window that never moved misplaced, and makes save_window_reference()
    overwrite display A's reference with display B's rect.

    A change is never silent — see _on_machine_id_changed for why it warns
    instead of raising, and for the cache it must drop to stay safe.
    """
    global _MACHINE_ID, _MACHINE_ID_DERIVED
    if _MACHINE_ID is not None and _MACHINE_ID != _MACHINE_ID_DERIVED:
        return _MACHINE_ID          # set by hand; honour it verbatim
    import platform
    fresh = f"{_machine_host()}|{platform.machine()}|{_screen_geometry()}"
    if fresh == _MACHINE_ID:
        return _MACHINE_ID
    was, _MACHINE_ID, _MACHINE_ID_DERIVED = _MACHINE_ID, fresh, fresh
    if was is not None:
        _on_machine_id_changed(was, fresh)
    return _MACHINE_ID


_VIEW_CACHE = {}
_VIEW_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "view_bounds.json")


def _load_view_cache(me=None):
    """Bounds this machine measured earlier, for the id given (default: now).

    _on_machine_id_changed passes the NEW id explicitly rather than letting
    this call machine_id() again: it is invoked from inside machine_id(), and
    re-entering it there would probe the display a second time for an answer
    already in hand.
    """
    try:
        import json
        with open(_VIEW_CACHE_FILE) as fh:
            raw = json.load(fh)
            if me is None:
                me = machine_id()
            return {tuple(int(p) for p in k.split(",")): tuple(v)
                    for k, v in raw.get(me, {}).items()}
    except Exception:
        return {}


def _save_view_cache(force=False):
    # OFFLINE TESTS MUST NOT WRITE A PRODUCTION CALIBRATION FILE.
    #
    # This is read back by live runs, so a test that writes it changes what the
    # next real run believes about the screen. It already happened twice: an
    # offline analysis pass added a live geometry's key to a worktree's copy,
    # and on 2026-09-06 the ordinary offline suite added "1400,787,117,0" from
    # a DEMO ARCHIVE frame -- a geometry no live capture ever produces -- to the
    # file the rig uses. Nothing failed, because nothing ever does when a cache
    # is silently wrong; that is the whole hazard.
    #
    # The IN-MEMORY cache is untouched, so behaviour inside a test run is
    # exactly what it would be live. Only the persistence is suppressed.
    # `force` is for the two tests that exist to exercise PERSISTENCE itself.
    # They must redirect the file path to a temp directory first; forcing a
    # write at the real path is the exact pollution this guard prevents, so the
    # opt-in is a visible argument at the call site rather than an env twiddle.
    if not force and _os_env.environ.get("BASEBALL_TEST_RUN"):
        return
    try:
        import json
        try:
            with open(_VIEW_CACHE_FILE) as fh:
                raw = json.load(fh)
        except Exception:
            raw = {}
        # Merge, never overwrite: another machine's entries must survive.
        raw[machine_id()] = {",".join(str(p) for p in k): list(v)
                             for k, v in _VIEW_CACHE.items()}
        # Write-then-rename, because this file now lives on a NAS. A plain
        # open("w") truncates first, so a dropped mount mid-write leaves an
        # empty file and loses EVERY machine's geometry, not just this one's.
        # os.replace is atomic within a filesystem.
        import os as _os
        tmp = _VIEW_CACHE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(raw, fh, indent=1)
        _os.replace(tmp, _VIEW_CACHE_FILE)
    except Exception:
        pass


_VIEW_CACHE = _load_view_cache()


def view_bounds(img, threshold=18):
    """(x_left, x_right, y_top, y_bottom) of the game view inside the capture.

    The game is letterboxed, so the lit region is the window's content area.
    This is a property of the WINDOW, not the scene, which is what a geometry
    reference has to be — measured across 17 logged frames of wildly different
    content it gave the same centre every time.

    Takes the LARGEST CONTIGUOUS run of lit columns, not first-to-last: the
    macOS dock is a separate lit strip down the right edge, and including it
    put the centre 27px too far right — a systematic +8.5 degree bias on every
    bearing. Running the game fullscreen removes the dock from the capture
    entirely and is the better fix.
    """
    import numpy as np
    a = np.asarray(img.convert("L"), dtype=float)
    h, w = a.shape
    top = int(h * 0.06)                       # skip the macOS menu bar
    body = a[top:]
    lit = body.max(axis=0) > threshold
    rows = np.where(body.max(axis=1) > threshold)[0]
    if not lit.any() or rows.size == 0:
        return None
    best_len = best_start = run = 0
    start = 0
    for x, v in enumerate(lit):
        if v:
            if run == 0:
                start = x
            run += 1
            if run > best_len:
                best_len, best_start = run, start
        else:
            run = 0
    if best_len == 0:
        return None
    found = (best_start, best_start + best_len - 1,
             int(rows[0]) + top, int(rows[-1]) + top)
    # KEEP THE WIDEST EXTENT EVER SEEN for this frame size. The lit region
    # shrinks in a dark scene — measured (0, 1249) in an unlit hallway against
    # (0, 1727) in daylight — which moves the computed view centre from 864 to
    # 624 and puts every bearing derived from it tens of degrees out. The
    # window does not move when the room goes dark, so the widest observation
    # is the true one and a narrower reading is just the scene.
    key = img.size
    prev = _VIEW_CACHE.get(key)
    if prev is None or (found[1] - found[0]) > (prev[1] - prev[0]):
        _VIEW_CACHE[key] = found
        _save_view_cache()
        return found
    return prev


# --- Travel in any direction WITHOUT turning --------------------------------
# The smallest turn the stream delivers is ~28 degrees (measured fullscreen:
# holds of 0.00/0.01/0.05s move a median 28/46/60), so the camera cannot be
# aimed finely. But movement is CAMERA-RELATIVE and the heading can be READ
# finely (+/-2 degrees) even when it cannot be aimed finely — so where the
# character goes need not be limited by where the camera can be pointed.
#
# W/A/S/D give eight directions relative to the camera at 45 degree steps.
# Alternating between two ADJACENT directions in a duty cycle gives everything
# in between: 70% forward and 30% forward-right travels about 13 degrees off
# forward. That makes travel direction continuous while aiming stays coarse.
_DIRECTION_KEYS = {
    0: ("walk_up",),
    45: ("walk_up", "walk_right"),
    90: ("walk_right",),
    135: ("walk_down", "walk_right"),
    180: ("walk_down",),
    225: ("walk_down", "walk_left"),
    270: ("walk_left",),
    315: ("walk_up", "walk_left"),
}
BLEND_SLICE_SEC = 0.18      # one duty-cycle slice; shorter is smoother, slower


def angular_difference(a, b):
    """Signed shortest rotation from a to b, in (-180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


def hold_combo(actions, seconds):
    """Hold several mapped keys down together for `seconds`."""
    keys = [KEYMAP[a] for a in actions if KEYMAP.get(a)]
    if not keys:
        return
    # WAIT for focus to land before pressing, exactly as press() does. Without
    # it the keydown fires while focus is still moving and part of the hold is
    # lost: measured, a 1.0s hold here travelled a THIRD as far as the same
    # hold through press() (frame delta 7.9 against 24.9), which looked from
    # the outside like the character being blocked after half a step.
    if can_use_background_input() and _bg_hold_keys(keys, seconds):
        return

    if not focus_input_allowed("+".join(keys)):
        return
    if focus_chiaki_window():
        time.sleep(0.15)
    prev_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0.0
    try:
        for k in keys:
            pyautogui.keyDown(k)
        time.sleep(seconds)
        for k in reversed(keys):
            pyautogui.keyUp(k)
    finally:
        pyautogui.PAUSE = prev_pause


def walk_at(rel_deg, seconds, slice_sec=BLEND_SLICE_SEC):
    """Travel `seconds` at `rel_deg` clockwise from the camera's forward.

    Blends the two adjacent 45-degree directions so any angle is reachable.
    Returns the time actually spent moving.
    """
    # BOTH branches below reach the keyboard -- the pure one through press()/hold_combo(),
    # the blended one through pyautogui directly, which had no lockout of any kind. Guard
    # once here so a refusal reports 0.0 travelled either way; the pure branch returns
    # `seconds` unconditionally and would otherwise claim a walk it did not take (10.1).
    if not focus_input_allowed(f"walk {rel_deg:.0f} deg"):
        return 0.0
    rel = rel_deg % 360.0
    # A pure direction needs no blending. Route it through the single-key path
    # in one hold rather than slicing it into duty-cycle chunks: each slice
    # pays a key up/down and the game appears to ramp movement speed, so the
    # sliced version covered noticeably less ground for the same seconds.
    snapped = round(rel / 45.0) * 45 % 360
    if abs(angular_difference(rel, snapped)) < 4.0:
        keys = _DIRECTION_KEYS[snapped]
        if len(keys) == 1:
            press(keys[0], hold_seconds=seconds, post_delay=0.0)
        else:
            hold_combo(keys, seconds)
        return seconds
    lo = int(rel // 45) * 45
    hi = (lo + 45) % 360
    frac_hi = (rel - lo) / 45.0            # 0 -> all lo, 1 -> all hi
    a, b = _DIRECTION_KEYS[lo], _DIRECTION_KEYS[hi]
    # FOCUS ONCE, then drive the slices directly. Calling focus_chiaki_window()
    # per slice costs a ~150ms osascript round trip each time, and a blended
    # second was measured at 12.4s of wall clock for 1.0s of walking — the
    # blending itself is cheap, the window-manager chatter was not.
    if focus_chiaki_window():
        time.sleep(0.15)
    ka = [KEYMAP[x] for x in a if KEYMAP.get(x)]
    kb = [KEYMAP[x] for x in b if KEYMAP.get(x)]
    # SUPPRESS pyautogui's inter-call pause for the duration of the blend.
    # It inserts 0.1s after EVERY keyDown and keyUp, and a blended second
    # issues ~8 key calls per 0.18s slice — measured, a 1.0s blended walk took
    # 11.3s of wall clock, nearly all of it this pause. The pause exists to
    # stop scripts outrunning a UI; here the sleeps between key events already
    # pace us, so it is pure cost.
    _prev_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0.0
    spent = 0.0
    while spent < seconds - 1e-3:
        step = min(slice_sec, seconds - spent)
        t_hi = step * frac_hi
        t_lo = step - t_hi
        for keys, dur in ((ka, t_lo), (kb, t_hi)):
            if dur <= 0.012 or not keys:
                continue
            if not (can_use_background_input() and _bg_hold_keys(keys, dur)):
                for k in keys:
                    pyautogui.keyDown(k)
                time.sleep(dur)
                for k in reversed(keys):
                    pyautogui.keyUp(k)
        spent += step
    pyautogui.PAUSE = _prev_pause
    return spent


# WHY THE OLD GUARD HERE WAS DELETED
# ----------------------------------
# It measured how much of the capture was LIT and called that "does the game
# fill the frame". On a real capture the macOS desktop -- menu bar, wallpaper,
# dock -- lights every column edge to edge, so it returned a perfect 1.000 for
# frames that plainly showed a windowed game surrounded by desktop. Verified
# against the very fixtures the ban-grid constants were calibrated on: all
# 1.000, all windowed. It could not fail, so it guarded nothing.
#
# It looked correct only because it was tested against synthetic frames pasted
# onto a BLACK canvas. Real displacement does not come with black bars.
#
# The regions in orchestrator are fractions of the WHOLE DESKTOP CAPTURE, so
# what actually has to hold is that the chiaki window sits where it sat during
# calibration. That is a question about window placement, and the OS answers it
# directly instead of it being guessed from brightness.


def game_window_rect():
    """(x, y, w, h) of the chiaki window in SCREEN POINTS, or None."""
    if sys.platform == "darwin":
        try:
            import Quartz
            wl = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly
                | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID)
            # LARGEST, not first. chiaki-ng owns two windows: the game itself
            # and a 2560x44 title strip above it. Taking the first match got
            # the title strip live on 2026-08-27, which would have compared a
            # 44px-tall bar against a 1080px reference and reported enormous
            # drift forever.
            best = None
            for w in wl or []:
                owner = (w.get("kCGWindowOwnerName") or "").lower()
                if CHIAKI_WINDOW_PROCESS_NAME in owner:
                    b = w.get("kCGWindowBounds") or {}
                    try:
                        rect = (float(b["X"]), float(b["Y"]),
                                float(b["Width"]), float(b["Height"]))
                    except (KeyError, TypeError):
                        continue
                    if best is None or rect[2] * rect[3] > best[2] * best[3]:
                        best = rect
            return best
        except Exception:
            return None
    if sys.platform == "win32":
        try:
            import pygetwindow
            for win in pygetwindow.getWindowsWithTitle(
                    CHIAKI_WINDOW_PROCESS_NAME):
                return (float(win.left), float(win.top),
                        float(win.width), float(win.height))
            return None
        except Exception:
            return None
    return None


# Measured on this Mac against a real ban-grid frame: displacing the game by
# 58px left every cell still read correctly, 110px silently FLIPPED one. Those
# are capture pixels on a 2000px-wide capture of a 1728pt screen, so 110px is
# ~95pt. 40pt sits well inside the safe half of that gap.
WINDOW_DRIFT_MAX_PT = 40.0

_WINDOW_REF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "window_reference.json")


def _load_window_reference():
    try:
        import json
        with open(_WINDOW_REF_FILE) as fh:
            return tuple(json.load(fh)[machine_id()])
    except Exception:
        return None


def window_drift(reference=None):
    """(ok, drift_pt, rect, reference) against the calibrated window position.

    ok is True when the window has not moved enough to matter, and ALSO when
    there is no reference yet -- an uncalibrated machine is not a misplaced
    one. drift is None in that case rather than 0.0, so a caller cannot mistake
    "never measured" for "measured, perfect".

    ok is False when the window cannot be found at all: every region is then
    pointed at whatever else happens to be on screen.
    """
    rect = game_window_rect()
    if reference is None:
        reference = _load_window_reference()
    if rect is None:
        return False, None, None, reference
    if reference is None:
        return True, None, rect, None
    drift = max(abs(a - b) for a, b in zip(rect, reference))
    return drift <= WINDOW_DRIFT_MAX_PT, drift, rect, reference


def save_window_reference(rect=None):
    """Record the current window position as this machine's reference."""
    import json
    rect = rect or game_window_rect()
    if rect is None:
        return None
    try:
        with open(_WINDOW_REF_FILE) as fh:
            raw = json.load(fh)
    except Exception:
        raw = {}
    raw[machine_id()] = list(rect)
    tmp = _WINDOW_REF_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(raw, fh, indent=1)
    os.replace(tmp, _WINDOW_REF_FILE)
    return rect


# --- Background input: drive the game WITHOUT taking the keyboard ----------
#
# pyautogui posts events to the SYSTEM, so they land wherever focus happens to
# be. That is why press() has always dragged chiaki to the front first, and it
# makes the machine unusable for anything else while a run is going.
#
# CGEventPostToPid delivers an event to one process instead. chiaki-ng is Qt,
# so it reads through the normal Cocoa event path and accepts them. VERIFIED
# live on 2026-08-27: four camera turns landed in the game (frame deltas 10-23)
# while Google Chrome stayed frontmost and the user kept working in it.
#
# Focus is IRRELEVANT on this path, so it deliberately does not call
# focus_chiaki_window() or gate on has_focus(). Those exist because the old
# path needed them; requiring them here would reintroduce exactly the problem
# this removes.

BACKGROUND_INPUT = True          # set False to fall back to the focus-stealing path

# macOS virtual keycodes (kVK_*). Layout-independent: these are physical key
# positions, not characters, so they do not shift with keyboard layout.
_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "c": 8, "w": 13, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "=": 24, "-": 27, "o": 31, "enter": 36, "\\": 42,
    "backspace": 51, "esc": 53,
    "pageup": 116, "pagedown": 121,
    "left": 123, "right": 124, "down": 125, "up": 126,
}

_chiaki_pid = None


_IDENTITY_TTL_SEC = 5.0
_identity_checked = {"pid": None, "at": 0.0, "ok": False}


def _still_chiaki(pid):
    """Is this pid STILL the chiaki app? Cached for a few seconds.

    THE LIVENESS GUARD ASKS THE WRONG QUESTION, and 2026-09-13 showed what that costs: it
    asks "is this pid alive", and the pid it was holding was a live /bin/zsh. Alive is not
    the property that matters; BEING CHIAKI is. `ps -o comm=` answers it for about 5 ms,
    which is too much per keypress and nothing at all once every few seconds -- and a
    process cannot quietly turn into a different program between two ticks of that clock,
    because a pid only changes identity by dying first, which the liveness check catches.
    """
    now = time.time()
    if (_identity_checked["pid"] == pid
            and now - _identity_checked["at"] < _IDENTITY_TTL_SEC):
        return _identity_checked["ok"]
    try:
        comm = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                              capture_output=True, text=True, timeout=5).stdout.strip()
        ok = os.path.basename(comm) == CHIAKI_WINDOW_PROCESS_NAME
    except Exception:
        ok = True          # a failed LOOKUP is not evidence of a wrong process
    _identity_checked.update({"pid": pid, "at": now, "ok": ok})
    return ok


def _resolve_chiaki_pid():
    """The PID of the chiaki APP, never of something that merely mentions it.

    `pgrep -f chiaki` matches the whole COMMAND LINE, and on 2026-09-13 it matched this
    session's own shell -- a `/bin/zsh -c ...` whose argv contained the word because the
    commands being run mentioned chiaki paths. It sorted FIRST, so chiaki_pid returned the
    shell, every CGEventPostToPid went to a terminal, and the liveness guard directly above
    could not help: the shell is alive. Presses reported success for an afternoon and the
    console never saw one. The ban scan read 8 cards of a 33-card collection and reported
    no error.
    THE SAME SHAPE THE GUARD ABOVE WAS WRITTEN FOR, one step further out: that one asks
    "is this pid alive", and the question it could not ask was "is this pid CHIAKI".

    So: match the executable NAME exactly first. Fall back to the command-line match only
    when that finds nothing, and filter it by what each process actually IS.
    """
    exact = subprocess.run(["pgrep", "-x", CHIAKI_WINDOW_PROCESS_NAME],
                           capture_output=True, text=True, timeout=5).stdout.split()
    if exact:
        return int(exact[0])
    loose = subprocess.run(["pgrep", "-f", CHIAKI_WINDOW_PROCESS_NAME],
                           capture_output=True, text=True, timeout=5).stdout.split()
    for pid in loose:
        comm = subprocess.run(["ps", "-p", pid, "-o", "comm="],
                              capture_output=True, text=True, timeout=5).stdout.strip()
        if os.path.basename(comm) == CHIAKI_WINDOW_PROCESS_NAME:
            return int(pid)
    if loose:
        print(f"  [input] pgrep -f matched {loose} but none of them IS chiaki -- "
              f"treating chiaki as NOT RUNNING rather than pressing into one of them")
    return None


def chiaki_pid(refresh=False):
    """PID of the running chiaki process, or None."""
    global _chiaki_pid
    if _chiaki_pid is not None and not refresh:
        # VERIFY THE CACHED PID IS STILL ALIVE. It used to be trusted forever,
        # and nothing anywhere calls chiaki_pid(refresh=True) — so after a
        # chiaki restart (restart_chiaki.sh kill -9s it) every
        # CGEventPostToPid went to a dead process, delivered nothing, raised
        # nothing, and _bg_hold_keys still returned True. Every press would
        # report success while no input reached the game at all.
        #
        # That is the same failure that already cost a night as "the stock
        # build was running", one layer further down and harder to see.
        # os.kill(pid, 0) sends no signal; it just asks whether the process is
        # there, and costs nothing next to the pgrep it guards.
        try:
            os.kill(_chiaki_pid, 0)
            if _still_chiaki(_chiaki_pid):
                return _chiaki_pid
            print(f"  [input] pid {_chiaki_pid} is alive but is NOT chiaki any more — "
                  "re-resolving (presses would have gone to another process)")
            _chiaki_pid = None
        except ProcessLookupError:
            print(f"  [input] chiaki pid {_chiaki_pid} is gone — re-resolving "
                  "(input would otherwise vanish silently)")
            _chiaki_pid = None
        except PermissionError:
            return _chiaki_pid      # alive, merely not ours to signal
    try:
        _chiaki_pid = _resolve_chiaki_pid()
    except Exception as e:
        # SAY SO, exactly as the ProcessLookupError branch above does — its
        # comment is "input would otherwise vanish silently", and this sibling
        # had the same consequence with none of the noise. A pgrep TIMEOUT is
        # not evidence that chiaki has gone: returning None makes
        # can_use_background_input() False, which drops every press for the
        # rest of the run onto focus_chiaki_window() + pyautogui — the path
        # that steals the keyboard and types into whatever is frontmost.
        # Rare enough that a plain line costs nothing.
        print(f"  [input] could not resolve the chiaki pid "
              f"({type(e).__name__}: {e}) — treating chiaki as NOT RUNNING. "
              "That is a failed lookup, not a dead process; background input "
              "is now off and presses will steal focus.")
        _chiaki_pid = None
    return _chiaki_pid


def can_use_background_input(action=None):
    """True if this action can be sent without stealing focus.

    HARD OFF DURING TESTS. The offline suite stubs pyautogui so it can count
    key events without touching anything, but it does not stub pgrep — so this
    function found the REAL running game and the "offline" tests started
    driving it for real. Refusing here keeps the suite exercising the stubbed
    path, and means a test run can never move the character.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        return False
    if not BACKGROUND_INPUT or sys.platform != "darwin":
        return False
    if action is not None and KEYMAP.get(action) not in _KEYCODES:
        return False
    return chiaki_pid() is not None


def targeted_input_allowed(what):
    """May this process post key events straight to chiaki's pid?

    THE GATE WAS ONLY EVER AT THE CALL SITES. can_use_background_input() returns
    False under BASEBALL_TEST_RUN, and press() honours it -- but press_background()
    and _bg_hold_keys() never ask, so anything calling THEM directly posted to the
    live console during the offline suite. Reproduced 2026-09-13 with a PS5
    connected and a match on screen:

        BASEBALL_TEST_RUN = 1
        can_use_background_input() = False
        press_background('look_right') -> True   posted to pid 83980, twice
        _bg_hold_keys(['w'], 0.01)     -> True   posted to pid 83980, twice
        press('look_right')            -> refused, 0 posts        [control]

    _bg_hold_keys's own docstring calls itself "the single low-level route every
    public input function funnels through, so there is exactly one place where
    'did this go to the game or to the user's work' is decided" -- it named the
    responsibility and did not discharge it. Direct callers include
    reset_env._probe_transports and _diagnose_no_pause, which turn the camera.

    Same family as the keyboard hole fixed hours earlier: a guard one layer up
    from the damage, answering a narrower question than its name implies.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        print(f"  [input] BASEBALL_TEST_RUN: refusing to post {what} straight to "
              "chiaki's process. If this is a live run, nothing will reach the "
              "console until you unset it.")
        return False
    return True


def press_background(action, hold_seconds=0.05, post_delay=None):
    """Send one action straight to chiaki's process. Returns True if sent.

    Returns False rather than raising when it cannot: the caller then falls
    back to the focus-stealing path instead of silently doing nothing, which
    would look exactly like a dropped input.
    """
    if not targeted_input_allowed(f"{action!r}"):
        return False
    import Quartz
    code = _KEYCODES.get(KEYMAP.get(action))
    pid = chiaki_pid()
    if code is None or pid is None:
        return False
    try:
        for down in (True, False):
            Quartz.CGEventPostToPid(
                pid, Quartz.CGEventCreateKeyboardEvent(None, code, down))
            if down:
                time.sleep(hold_seconds)
    except Exception:
        return False
    time.sleep(ACTION_DELAY if post_delay is None else post_delay)
    return True

def _bg_hold_keys(keys, seconds):
    """Hold raw key names down together for `seconds`, targeted at chiaki.

    Returns True if it handled them. This is the single low-level route every
    public input function funnels through, so there is exactly one place where
    "did this go to the game or to the user's work" is decided.
    """
    if not targeted_input_allowed("+".join(keys)):
        return False
    import Quartz
    pid = chiaki_pid()
    if pid is None:
        return False
    codes = [_KEYCODES.get(k) for k in keys]
    if any(c is None for c in codes):
        return False
    try:
        for c in codes:
            Quartz.CGEventPostToPid(
                pid, Quartz.CGEventCreateKeyboardEvent(None, c, True))
        time.sleep(seconds)
        for c in reversed(codes):
            Quartz.CGEventPostToPid(
                pid, Quartz.CGEventCreateKeyboardEvent(None, c, False))
    except Exception:
        return False
    return True
