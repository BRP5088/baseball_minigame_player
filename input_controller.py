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
# How many polls the discards counter gets to fall after confirm_discard. Mirrors
# MONEY_READ_TRIES' reasoning: every attempt is the same conservative reader, so more
# tries can only turn a refusal into an answer and invent no confidence.
DISCARD_CONFIRM_TRIES = 5
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
                    look=None, allow_blind: bool = False):
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
        # THE BLIND PATH IS NOW OPT-IN, AND THE OPT-IN IS THE POINT.
        #
        # This path dead-reckons the walk, presses select_card, presses confirm_play
        # and returns True with NOTHING READ. On a console measured to drop presses
        # (three move_rights 0.31 s apart moved the cursor TWO slots) that is exactly
        # the state CLAUDE.md records: selected slot 0, then DESELECTED slot 0
        # (select_card is a TOGGLE), committed nothing, and reported True. 10.1's
        # canonical shape -- a success path and a no-op path with identical output.
        #
        # Every production caller already passes look=. The defect was the SIGNATURE:
        # `look=None` made the unverified path the DEFAULT, so the one function that
        # can do the worst thing on this axis was the one whose easiest call was the
        # blind one. A new caller reached it by forgetting an argument.
        #
        # The body is unchanged and the tests that pin its press sequence still reach
        # it -- they now say so. TRUE HERE MEANS "the presses were sent", NOT "the
        # card was played"; only the verified path below can tell you that.
        if not allow_blind:
            raise ValueError(
                "select_and_play was called with no look= and no allow_blind=True. "
                "The blind path cannot tell a landed press from a dropped one, and "
                "returns True either way -- it once selected a card and then "
                "deselected it and reported success. Pass look=hand_cursor_look for "
                "the verified path, or allow_blind=True to state deliberately that "
                "nothing can read this screen.")
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

# How many slots _walk_cursor_to may write off as FALSE cursors in one walk (I-25).
# At most MAX_HAND_SIZE - 1 can be wrong while a real one still exists; past that,
# excluding a slot cannot invent a cursor that is not there and the walk refuses
# through the ordinary "nothing lit" path in cursor_slot.
FALSE_CURSOR_EXCLUDE_MAX = 4

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

SELECT_ATTEMPTS = 5            # 0.059% residual; covers the longest observed run of 4
# DERIVED FROM THE n=1000 PRESS CENSUS (2026-09-17, commit d07c0bb), NOT FROM THE n=5 THIS
# LINE USED TO CITE. That census measured, with every press confirmed against chiaki's own
# instrumented log before being scored: the game IGNORES 15.20% of presses it demonstrably
# receives, and they CLUSTER -- P(ignore | previous ignored) = 0.250 against 0.135 after a
# press that moved, longest consecutive run 4. So the residual is 0.152 * 0.25**(n-1), NOT
# the independent 0.2**n the old figure assumed:
#
#     attempts 2   3.80%    <- shipped until now, and it FIRED on a live $50 match
#     attempts 3   0.95%
#     attempts 4   0.238%
#     attempts 5   0.059%   <- and 5 covers the longest run actually observed
#
# A turn makes TWO selections (batter + tactics), so at 2 attempts roughly one turn in
# thirteen loses a play to a refusal -- which is most matches. Observed live 2026-09-17:
# selecting the tactics card refused after 2 attempts, unwound correctly, and the identical
# retry landed, which is what proves the reader CAN see that lift and the presses were
# ignored rather than unseen. That distinction is what makes retrying safe here: a press
# that LANDED but could not be SEEN would be un-toggled by the next press, and this loop
# guards that by re-reading between attempts and refusing the moment a card it did not
# expect goes up.
#
# The same census set PRESS_VERIFY_TRIES = 5 and BAN_NAV_MAX_STEPS = 22 the same night.
# This constant sits on the same axis and was missed; it is on the money path, where the
# cost of the miss is a refused play rather than a wrong one.
#
# Extra attempts are paid ONLY when a press is actually ignored, so the expected added
# cost is 0.152 * (SELECT_SETTLE_SEC + SELECT_RETRY_CONFIRM_SEC) per selection, not a
# fixed tax on every turn.

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


# (I-33) BELOW THIS, A CLEARED CURSOR_GLOW_MIN GATE IS NOT YET TRUSTED. Reused
# directly from local_hand.cursor_slot's OWN measured populations -- "the card
# with the cursor 20.7 .. 36.1; every other card 0.0 .. 8.4" -- rather than a new
# number: a read at or above 20.7 is inside that genuine-cursor band, and a read
# between CURSOR_GLOW_MIN (10.0) and this floor cleared the gate but is still
# inside CLAUDE.md 10.35's own measured ceiling for slot 4 ("never exceeds 11.0
# at ANY offset") -- exactly the gap a marginal, unreliable crossing sits in.
# Refuted skeptic repro `agent_progress/issues/I-33-skeptic/repro_cross_call.py`
# is this case verbatim: a FRESH call's own top-of-function read names cur=4 at
# glow 10.5, no I-02 probe involved, and the shipped fix (scoped to "confirmed
# via the I-02 probe") could not see it -- see `cur_confirmed_blind` below.
#
# NOT A FLOOR OF EVERY MEASURED TRUE READING (v2 skeptic, progress_v2.md Q B).
# local_hand.py ~1160-1236 documents a single live true-cursor reading of 12.4
# -- below this constant -- and CURSOR_GLOW_MIN (10.0) was deliberately set to
# "clear 8.4 AND admit 12.4", i.e. to treat 12.4 as genuine. This constant does
# not contradict that: a true reading landing in [10.0, 20.7) is merely
# TREATED AS UNRELIABLE here, not rejected -- the cost is at most one extra,
# bounded retry press (see `cur_confirmed_blind` below), and it can never
# produce a false arrival, since every arrival still requires a later genuine
# glow-confirmed read or the pre-existing I-02 probe.
CUR_TRUSTED_GLOW_MIN = 20.7

# How many blind nudges may be spent finding a cursor the glow reader cannot see.
# MAX_HAND_SIZE - 1 moves cross the whole fan; at section 5's measured 15.20%
# press-drop rate that is ~4.7 presses, and the slack absorbs a clustered run of
# drops. It is a bound on a RECOVERY, not a threshold on a measured quantity.
CURSOR_BLIND_NUDGES = 8

# How many times the PROBE-SELECT itself may be pressed before refusing. The probe
# is a single select_card press, and section 5's press-drop rate is 15.20%,
# CLUSTERED (P(ignore | previous ignored) = 0.250) -- so it can be dropped exactly
# like any other press. One retry (2 total) absorbs a lone drop without turning a
# genuinely dead slot into an unbounded press loop; it is not derived from
# SELECT_ATTEMPTS (5) because that number bounds a SELECTION the caller already
# knows is reachable, while this one bounds a PROBE whose whole purpose is to find
# out whether the target is reachable at all.
PROBE_SELECT_MAX = 2


def _probe_select_blind_target(target, ys, before_sel, look):
    """The cursor went blind one step from `target` -- find out where it really is
    by pressing select_card and reading the SELECTION lift, never the glow window.

    THE GAP THIS CLOSES (I-02): CURSOR_GLOW_MIN is a hover-brightness gate, and
    slot 4 is structurally under it (CLAUDE.md 10.35: "slot 4 never exceeds 11.0
    at ANY offset, while slots 0-3 read 26-28"). A walk that presses toward slot 4
    and then loses the cursor there had no way to confirm arrival, so slot 4 could
    never be a play or discard TARGET. The lift geometry `selected_cards` reads is
    a different signal the glow window cannot corrupt: a SELECTED card rises ~44px
    (`SELECTED_MIN_RISE`), and hovering alone moves nothing (measured in
    agent_progress/cursor-lift-refutation/: hover-lift is dead at every slot,
    slot 4 reads -10.0 hovered or not; only selection lifts).

    Returns (ok, cur, sel):
      ok=True,  cur=target        target lifted -- the cursor was on it. `sel`
                                   still names target selected, so the caller's own
                                   _select_verified sees "already selected" on its
                                   next look and presses nothing further.
      ok=True,  cur=<other slot>  a DIFFERENT slot lifted -- that names where the
                                   cursor actually is. It has been UNTOGGLED back
                                   down (verified, not assumed) and the walk should
                                   continue toward `target` from there.
      ok=False, cur=None          refuse: `target`'s row is unreadable to the lift
                                   reader, nothing lifted after PROBE_SELECT_MAX
                                   tries, or the untoggle could not be verified.
    """
    # CAUTION 2 FROM THE REFUTATION: selected_cards SKIPS a row whose y is a
    # fallback (it abstains on exactly the cards whose disc is unreadable), so
    # "nothing lifted" from a slot the reader cannot see is not evidence of
    # anything. `ys` here is orchestrator.hand_cursor_look's already-gated column
    # (None on a fallback y, same rule _select_verified uses at :983), so this is
    # that same check without a second look.
    if not (0 <= target < len(ys)) or ys[target] is None:
        print(f"  [cursor] slot {target} is not seen by the lift reader — refusing "
              "the probe rather than trusting a 'nothing lifted' it cannot answer")
        return False, None, before_sel
    before = set(before_sel)
    sel = before_sel
    for attempt in range(1, PROBE_SELECT_MAX + 1):
        press("select_card")
        time.sleep(SELECT_SETTLE_SEC)
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print(f"  [cursor] cannot read the fan after the probe select (rows={n}) "
                  "— refusing")
            return False, None, sel
        new = [i for i in sel if i not in before]
        if target in new:
            print(f"  [cursor] probe-select: {target} lifted — the cursor was there")
            return True, target, sel
        if new:
            other = new[0]
            print(f"  [cursor] probe-select raised {other}, not {target} — the "
                  "cursor is there; putting it back down")
            ok2, sel2 = _deselect_verified(other, look)
            if not ok2:
                print(f"  [cursor] could not untoggle probe slot {other} — refusing "
                      "rather than continuing with a stray card lifted")
                return False, None, sel2
            return True, other, sel2
        if attempt < PROBE_SELECT_MAX:
            print(f"  [cursor] probe-select raised nothing (attempt {attempt}/"
                  f"{PROBE_SELECT_MAX}) — retrying once; a dropped press is routine "
                  "at this console's 15.20% ignore rate")
    print(f"  [cursor] probe-select raised nothing after {PROBE_SELECT_MAX} attempts "
          "— refusing")
    return False, None, sel


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
    _cur_from_lift = False
    # (I-33) A SELECTED card is where the cursor was the moment select_card was
    # pressed, and nothing else can move the cursor without a press this call has
    # not yet sent -- so if the fan's own glow cannot name ANY cursor but exactly
    # one card is already lifted, that card names it. This closes a cross-call
    # hole a skeptic found (agent_progress/issues/I-33-skeptic/progress.md,
    # repro_cross_call.py): `_verified_select_and_play_inner` calls
    # `_walk_cursor_to(4, ...)` then `_select_verified(4, ...)` (which leaves
    # card 4 selected), then a FRESH `_walk_cursor_to(0, ...)`. That second
    # call's own TOP-OF-FUNCTION read sees glow=[0.0, 0.4, 0.0, 0.0, 0.4] --
    # `cursor_slot()` answers None (0.4 never clears CURSOR_GLOW_MIN, CLAUDE.md
    # 10.35) -- and every belief the FIRST call built (`cur_confirmed_blind`,
    # whether via I-02's probe or this same rule) is a local that resets to
    # False at the top of every call, so it cannot carry over. Without this,
    # the nudge loop below would move a cursor whose position is already known
    # from the selection, and the retry further down could never fire for the
    # cross-call event it exists to cover.
    if cur is None and n == MAX_HAND_SIZE and len(sel) == 1:
        cur = sel[0]
        _cur_from_lift = True
        print(f"  [cursor] the fan is blind but slot {cur} is already selected "
              "— naming it the cursor from the selection, not the glow")
    # AN UNLOCATABLE CURSOR IS RECOVERABLE, BECAUSE MOVING COMMITS NOTHING.
    #
    # Refusing here is right when the FAN cannot be read -- there is nothing to
    # navigate. It is the wrong answer when the fan reads perfectly and only the
    # CURSOR cannot be found, because that has a known cause and a free remedy.
    #
    # Live 2026-09-20: the cursor sat on slot 4 reading 6.9-9.8 against
    # CURSOR_GLOW_MIN 10.0 while every other slot read 0.0-1.0. cursor_slot
    # answered None, this refused, and the engine could neither discard slot 4 nor
    # navigate AWAY from it to play slots 1 and 2 -- a total deadlock from one
    # unreadable position. CLAUDE.md 10.35 measured the cause and it is permanent:
    # "slot 4 never exceeds 11.0 at ANY offset, while slots 0-3 read 26-28 at the
    # shipped position."
    #
    # SO WALK OFF THE BLIND SLOT. move_left/move_right are NAVIGATION; select_card
    # is the only toggle, and nothing is committed until confirm_play. A nudge
    # therefore risks nothing that a refusal protects -- it cannot select, deselect,
    # play or discard -- while landing the cursor on any of slots 0-3 makes it
    # readable by a factor of three over the gate.
    #
    # LOOK AFTER EVERY PRESS, never count them (section 5: 15.20% of presses are
    # ignored, clustered). That also makes this safe whether or not the fan wraps at
    # the edge: if it wraps, a blind slot is passed through rather than settled on,
    # and the re-read catches the first readable position either way.
    #
    # THE BUDGET IS DERIVED. The fan is MAX_HAND_SIZE wide, so at most
    # MAX_HAND_SIZE - 1 moves reach the far edge; at the measured 15.20% drop rate
    # that needs about 4.7 presses, and the slack below covers a run of drops
    # without letting a genuinely dead reader press forever.
    _nudges = 0
    while n == MAX_HAND_SIZE and cur is None and _nudges < CURSOR_BLIND_NUDGES:
        _nudges += 1
        print(f"  [cursor] fan reads but the cursor is nowhere above the gate "
              f"(glow={glow}) — nudging off the blind slot ({_nudges}/"
              f"{CURSOR_BLIND_NUDGES}); moving commits nothing")
        press("move_left")
        time.sleep(MOVE_SETTLE_SEC)
        glow, ys, n, sel = _look_settled(look)
        cur = local_hand.cursor_slot(glow, sel)
    if _nudges and cur is not None:
        print(f"  [cursor] recovered on slot {cur} after {_nudges} nudge(s)")
    if n != MAX_HAND_SIZE or cur is None:
        print(f"  [cursor] cannot see the cursor (rows={n}, glow={glow}) — refusing")
        return False, sel
    steps = 0
    excluded = set()
    first_cur = cur
    # (I-33) True once `cur` is known only by an UNRELIABLE confirmation --
    # either inferred from a lift/I-02-probe rather than glow at all, or a glow
    # read that cleared CURSOR_GLOW_MIN (10.0) but sits below CUR_TRUSTED_
    # GLOW_MIN (20.7, local_hand.cursor_slot's own measured floor for a genuine
    # cursor) -- squarely inside CLAUDE.md 10.35's slot-4 ceiling (never exceeds
    # 11.0). `_cur_from_lift` covers the top-of-function case just above; a
    # normal `cursor_slot()` read (here or after the nudge loop) is trusted only
    # if it clears that floor by a healthy margin. NOT set after an I-32
    # dead-reckon; see that branch's own comment for why. See the retry this
    # feeds, below the I-02 probe branch.
    cur_confirmed_blind = _cur_from_lift or glow[cur] < CUR_TRUSTED_GLOW_MIN
    # DEAD-RECKONING ACROSS AN OCCLUDED SLOT (I-32). `cursor_glow` returns 0.0 BY
    # CONSTRUCTION for any row whose y was never measured (CLAUDE.md 10.28's fan
    # occlusion: one card's power disc sits under its neighbour, `y_measured: False`
    # forever for that hand). Walking from slot 0 to slot 4 across an occluded slot 1
    # made `cursor_slot` read None mid-walk -- indistinguishable from a dropped press
    # by glow alone -- and refused after one press, excluding the whole play. The
    # bound below is deliberately ONE consecutive step: two occluded slots in a row
    # (or an occluded slot right next to a genuinely dropped press) still refuse: see
    # the `dead_reckoned_last` check below, and I-32's task note.
    dead_reckoned_last = False
    while cur != target:
        if steps >= CURSOR_MAX_STEPS:
            # EIGHT LANDED PRESSES CANNOT LEAVE THE CURSOR IN PLACE (I-25). Section 5
            # measures the console dropping at most 15.20% of presses, clustered but
            # never eight in a row on this path -- CURSOR_MAX_STEPS crosses the whole
            # 5-slot fan twice over. A reading that read the SAME slot before the
            # first press and after every single one of the eight is not a stuck
            # cursor, it is a FALSE one: CLAUDE.md 10.35 measured a glow window that
            # lands ON a card's white art reads 60-88% regardless of the cursor, and
            # test_fixtures/hand_reads/i25_false_cursor_slot0_live_20260920.png is
            # exactly that -- slot 0 read 68.6 while presses toward slot 4 (22.8)
            # never once moved the argmax winner. Exclude the false slot and see
            # whether the real cursor is hiding under the gate elsewhere; bounded so
            # this cannot loop forever writing off slots that were never the problem.
            if cur == first_cur and cur not in excluded and len(excluded) < FALSE_CURSOR_EXCLUDE_MAX:
                excluded.add(cur)
                print(f"  [cursor] still at {cur} after {steps} presses with no change "
                      f"— treating slot {cur} as a false cursor and excluding it")
                glow, ys, n, sel = _look_settled(look)
                if n != MAX_HAND_SIZE:
                    print(f"  [cursor] cannot confirm the exclusion (rows={n}) — refusing")
                    return False, sel
                retried = local_hand.cursor_slot(glow, sel, exclude=excluded)
                if retried is None:
                    print(f"  [cursor] excluding slot {cur} finds nothing else lit "
                          f"(glow={glow}) — refusing")
                    return False, sel
                print(f"  [cursor] excluding slot {cur} finds the real cursor on "
                      f"{retried} — continuing the walk from there")
                cur = first_cur = retried
                # (I-33) a normal cursor_slot() read, so judged the same way as
                # any other: trusted only above CUR_TRUSTED_GLOW_MIN.
                cur_confirmed_blind = glow[cur] < CUR_TRUSTED_GLOW_MIN
                steps = 0
                continue
            print(f"  [cursor] still at {cur} after {steps} presses — refusing")
            return False, sel
        prev = cur
        prev_blind = cur_confirmed_blind
        press("move_right" if cur < target else "move_left")
        steps += 1
        time.sleep(MOVE_SETTLE_SEC)
        glow, ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print(f"  [cursor] the fan stopped reading mid-walk (rows={n}) — refusing")
            return False, sel
        cur = local_hand.cursor_slot(glow, sel, exclude=excluded)
        was_dead_reckoned, dead_reckoned_last = dead_reckoned_last, False
        if cur is not None:
            # (I-33, mutant-B fix) RE-EVALUATED on every genuine read, not just
            # reset to a flat False -- a read that clears CURSOR_GLOW_MIN but
            # stays under CUR_TRUSTED_GLOW_MIN is still not fully trusted, and a
            # strong read here must actually CLEAR an earlier blind flag so a
            # later, unrelated lost cursor does not inherit an old one's retry.
            cur_confirmed_blind = glow[cur] < CUR_TRUSTED_GLOW_MIN
        if cur is None:
            expected = prev + 1 if prev < target else prev - 1
            # CROSSING AN OCCLUDED SLOT MID-WALK (I-32), CHECKED BEFORE THE I-02
            # PROBE BELOW SO "never dead-reckon onto the target" IS A REAL GUARD,
            # NOT DEAD CODE. `expected == target` is exactly the `abs(prev - target)
            # == 1` condition the I-02 branch tests (both mean "the press just moved
            # one step toward target"), so checking that branch first would make
            # `expected != target` here unreachable -- a mutant deleting it would
            # change nothing. Ordered this way, an occluded TARGET falls straight
            # through to `_probe_select_blind_target`, which already refuses without
            # a press when `ys[target] is None` -- that is the only place a target
            # the lift reader can't see is allowed to be trusted, never a guess here.
            #
            # For every OTHER slot the walk merely crosses: `cursor_glow` returns 0.0
            # BY CONSTRUCTION for a row whose y was never measured (CLAUDE.md 10.28's
            # fan occlusion -- a card's power disc hidden under its neighbour,
            # `y_measured: False` for the rest of that hand), so "nothing lit" on
            # exactly the row `ys[expected] is None` names is the EXPECTED reading,
            # not a lost cursor. Dead-reckon across it for one step and let the next
            # press prove the walk is still live. `was_dead_reckoned` caps this at
            # ONE consecutive step -- a second dark slot right after a dead-reckoned
            # one still refuses below, whether or not IT is occluded too (two
            # occluded slots in a row is the mirror case and stays a refusal; no
            # code chains guesses to cover it).
            if (not was_dead_reckoned and expected != target
                    and 0 <= expected < len(ys) and ys[expected] is None):
                print(f"  [cursor] slot {expected} is occluded (y unmeasured) — its "
                      "glow cannot read; dead-reckoning one step across it")
                cur = expected
                dead_reckoned_last = True
                # NOT cur_confirmed_blind = True (I-33). I-32's own bound above is
                # STRICTER than I-33's retry -- "no code chains guesses to cover
                # it" means not even one retry press after a dead-reckon, which
                # `tests/minigame/test_walk_crosses_occluded_slot.py` cases (2) and
                # (2b) pin exactly (2 presses, refuse, nothing further). Flagging a
                # dead-reckoned `cur` as blind here would have the I-33 retry add a
                # press I-32 deliberately refuses to send.
                continue
            # THE PRESS JUST MOVED TOWARD `target` AND `prev` WAS ONE STEP AWAY, SO
            # THE CURSOR IS MOST LIKELY ON `target` NOW (I-02): the glow window is
            # structurally blind at some slots (e.g. slot 4, CLAUDE.md 10.35), so
            # arriving there reads exactly like a dropped press. PROBE with
            # select_card instead of refusing outright -- see
            # _probe_select_blind_target for the mechanism and its two cautions.
            if abs(prev - target) == 1:
                ok, new_cur, sel = _probe_select_blind_target(target, ys, sel, look)
                if not ok:
                    return False, sel
                cur = new_cur
                first_cur, steps = cur, 0
                cur_confirmed_blind = True
                continue
            # (I-33) `prev` was ITSELF only known by an UNRELIABLE confirmation --
            # the I-02 probe above landing on a DIFFERENT slot than the call's own
            # target, a marginal glow crossing, or the top-of-function lift
            # fallback (see `cur_confirmed_blind` / `_cur_from_lift`, set at the
            # top of this function) -- never a confidently-clear direct glow read.
            # So a press off it that reads nothing is exactly what a DROPPED press
            # looks like too: the cursor may never have left `prev`, and `prev`'s
            # own glow cannot confirm that either way (CLAUDE.md 10.35's
            # structurally-blind slot 4, ceiling 11.0 against CURSOR_GLOW_MIN
            # 10.0). Reproduced live 2026-09-21 (I-33, overnight/
            # run_live_20260921f.log): "lost the cursor" with
            # glow=[0.0, 0.4, 0.0, 0.0, 0.4] -- slot 4 still reading exactly its
            # blind ceiling -- but NOT via this call's own I-02 probe. Traced
            # precisely (an independent skeptic's repro,
            # agent_progress/issues/I-33-skeptic/progress.md): this is a BRAND
            # NEW `_walk_cursor_to(0, ...)` call, made after a SEPARATE
            # `_walk_cursor_to(4, ...)` confirmed slot 4 by a normal read (the log
            # shows "verified on 4 after 6 press(es)" -- steps nonzero, which only
            # a direct read leaves behind) and `_select_verified(4, ...)` left it
            # selected. That belief cannot cross the call boundary -- a local
            # resets to False at the top of every call -- so THIS call's own
            # top-of-function read is what names `cur=4`, from the lift fallback
            # (`sel == [4]`, glow 0.4 never clears the gate). One retry in the
            # same direction absorbs a single dropped press (section 5: 15.20% of
            # presses are ignored) without risking an overshoot -- the one place a
            # second press COULD run past `target` is abs(prev - target) == 1,
            # and that case already returned above via the I-02 probe branch,
            # never reaching here.
            #
            # DELIBERATELY NOT SET AFTER AN I-32 DEAD-RECKON (see that branch's own
            # comment above): I-32's bound is one guess and no chaining at all, and
            # a retry press here would be exactly the chain it refuses to add.
            if prev_blind:
                print(f"  [cursor] the press left blind slot {prev} and nothing "
                      "reads — a dropped press looks identical; pressing once more "
                      "before refusing")
                press("move_right" if prev < target else "move_left")
                steps += 1
                time.sleep(MOVE_SETTLE_SEC)
                glow, ys, n, sel = _look_settled(look)
                if n != MAX_HAND_SIZE:
                    print(f"  [cursor] the fan stopped reading mid-walk (rows={n}) "
                          "— refusing")
                    return False, sel
                cur = local_hand.cursor_slot(glow, sel, exclude=excluded)
                if cur is not None:
                    cur_confirmed_blind = glow[cur] < CUR_TRUSTED_GLOW_MIN
                    continue
            print(f"  [cursor] lost the cursor after {steps} press(es) "
                  f"(glow={glow}) — refusing")
            return False, sel
    if steps:
        print(f"  [cursor] verified on {target} after {steps} press(es)")
    return True, sel


class _InferredSel(list):
    """A `sel` returned by `_select_verified` when it has CONCLUDED `target` is
    selected on THIS call -- whether by a real, geometric read (`target in
    before`/`target in sel`, the common case) or by I-21's inference (a disc
    that was readable and is now blind after our own press). Behaves as a
    plain list to every existing consumer (`in`, `sorted()`, `set()`, `==` all
    defer to `list`, same as orchestrator._CursorSel's `.kinds`) and
    additionally carries `.inferred`, the slot(s) confirmed on THIS call.
    `getattr(sel, "inferred", frozenset())` is how a caller reads it; a plain
    list (any test stub predating this) supplies none (I-44).

    S-1 (I-44 skeptic, round 1 REFUTED): a real read is STRONGER evidence than
    the inference, not weaker, and the first version of this file marked
    ONLY the inference branch -- so a target proven selected by a real read,
    then gone blind at commit (I-21's own stated premise, "selecting a card
    is what blinds its own disc"), refused, and the retry refused again: a
    hard stall on the commonest shape, measured at 10 of 34 archived
    want-blind commits (29%), every one a legitimate play. Every success path
    in `_select_verified` now carries this marker for exactly that reason.
    """
    inferred = frozenset()


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
    # THE BASELINE KIND, if this `look()` supplies one (I-36 skeptic). A tuple
    # `.kinds` attribute on `before` (orchestrator's `_CursorSel`) names what
    # `read_hand` called EVERY row on the very first, pre-press look -- the
    # one question a garbled POST-press read cannot answer for itself. A
    # `look()` that returns a plain list (any test stub, any future caller)
    # has no `.kinds`, and `_kinds0` is then None -- see the inference branch
    # below for what that means.
    _kinds0 = getattr(before, "kinds", None)
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
        # I-44 SKEPTIC (S-1): a REAL geometric read is STRONGER evidence than
        # I-21's inference, not weaker -- yet only the inference branch used
        # to report corroboration, so a target proven selected THIS way still
        # refused at commit once its disc went blind (I-21's own premise).
        # Reproduced: 10 of 34 archived want-blind commits (29%) would have
        # refused, every one a legitimate play that had already committed and
        # won. Every success path below carries the SAME `.inferred` marker.
        _sel = _InferredSel(before)
        _sel.inferred = frozenset({target})
        return True, _sel
    # AND IF THE TARGET'S POSITION IS UNKNOWN, REFUSE -- DO NOT PRESS.
    #
    # select_card is a TOGGLE. Pressing it at a card whose state cannot be read is
    # as likely to put a selected card DOWN as to put an unselected one up, and the
    # reader cannot see which happened, so the retry loop keeps going. Live
    # 2026-09-20: a selected card brightened until its power disc had no dark edge,
    # `before` came back empty, and five presses toggled the card the engine had
    # already selected. Refusing hands the decision back to the caller, which
    # re-reads a fresh frame -- and a refusal is recoverable where a toggle is not.
    if 0 <= target < len(_ys) and _ys[target] is None:
        print(f"  [cursor] slot {target}'s position is unreadable, so whether it is "
              "already selected cannot be told — refusing rather than pressing a "
              "TOGGLE blind")
        return False, before

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
            # S-1: a real, geometric read -- mark it the same as the
            # inference branch below (see the `target in before` comment).
            _sel = _InferredSel(sel)
            _sel.inferred = frozenset({target})
            return True, _sel
        new = [i for i in sel if i not in before]
        if new:
            # something that was NOT up before has gone up, and it is not the target.
            # Pressing again compounds it.
            print(f"  [cursor] select_card raised {new}, expected {target} — refusing")
            return False, sel
        # THE TARGET'S OWN DISC CAN GO BLIND THE MOMENT IT LIFTS (I-21). Selecting a
        # card brightens it until its power disc loses the dark edge read_hand needs
        # for a position, so a card that DID select reads exactly like one that did
        # not: selected_cards abstains on a row it cannot place, so `target` is
        # missing from `sel` either way. Live 2026-09-20: the first press landed, the
        # retry read the lifted 9 as absent and pressed select_card again -- a
        # TOGGLE -- five times, visibly selecting and deselecting the card the user
        # was watching on the stream. NEVER PRESS select_card AGAIN while the target
        # is in this state; the pre-loop guard above already proved its disc was
        # readable before this attempt's press (every later attempt only reaches a
        # press having just confirmed the same, below), so a press is the only thing
        # that could have made it unreadable now, and a second press is as likely to
        # put a landed card back DOWN as to select one that truly did not land.
        if 0 <= target < len(_ys) and _ys[target] is None:
            time.sleep(SELECT_RETRY_CONFIRM_SEC)
            _g, _ys, n, sel = _look_settled(look)
            if n != MAX_HAND_SIZE:
                print(f"  [cursor] cannot read the fan on the blind-lift re-check "
                      f"(rows={n}) — refusing")
                return False, sel
            if target in sel:
                print(f"  [cursor] select_card landed late, disc visible again "
                      f"({SELECT_RETRY_CONFIRM_SEC}s)")
                # S-1: real read.
                _sel = _InferredSel(sel)
                _sel.inferred = frozenset({target})
                return True, _sel
            if 0 <= target < len(_ys) and _ys[target] is None:
                # I-36 SKEPTIC: THE INFERENCE MUST NOT FIRE ON A BASELINE
                # TACTICS ROW. The garbled row this rescue exists for (I-36
                # itself) and a genuine tactics card whose own banner just
                # missed a read are INDISTINGUISHABLE from `_ys` alone --
                # both are `kind=='tactics'` with no type, on a fallback y.
                # The one thing that tells them apart is what the row was
                # typed BEFORE any press touched it: I-36's target was a
                # PLAYER card that only turned 'tactics' by misreading the
                # overlap; a card that was ALREADY 'tactics' at baseline is
                # never the case this rescue was built for, and trusting the
                # inference there let a dropped press on a genuine tactics
                # target -- unmoved, its own banner glitching twice by
                # coincidence -- be reported "selected" although it never
                # lifted (reproduced by the skeptic against the real code,
                # ~0.4% ambient rate, max observed run 4 frames). `None`
                # means this `look()` supplied no baseline kind at all (any
                # test stub, any future caller) and is PERMISSIVE -- the
                # pre-tightening behaviour, unchanged -- because every
                # sibling test that exercises this branch (I-21's own) is a
                # PLAYER scenario with no kind to gate on.
                _bk = (_kinds0[target]
                       if _kinds0 is not None and target < len(_kinds0) else None)
                if _bk != "tactics":
                    print(f"  [cursor] {target}'s disc is unreadable after the press "
                          "and was readable before it — selected by inference (disc "
                          "unreadable after lift)")
                    # I-44: mark THIS target as inferred-selected so _clear_strays'
                    # own commit-time inference (which asks the identical three
                    # facts again from a fresh look) can require that WE actually
                    # concluded this, rather than re-deriving it from ys0/kinds0
                    # alone with no requirement `sel` ever named the target. See
                    # _InferredSel and _clear_strays' `inferred_targets` param.
                    _sel = _InferredSel(sorted(set(before) | {target}))
                    _sel.inferred = frozenset({target})
                    return True, _sel
                # STILL UNREADABLE, gated out — this is NOT the "readable
                # again" case below (the target's position is not back; only
                # the INFERENCE is refused). Retry the press: on a genuinely
                # dropped press against a resting tactics card, the next
                # attempt lands it for real and `target in sel` (a real,
                # geometric read) catches it above, no inference needed.
                print(f"  [cursor] {target} is unreadable after the press, but its "
                      "BASELINE row was already typed 'tactics' — a genuine tactics "
                      "card can misread its own banner without ever having moved, so "
                      "this is not trusted as an inferred selection (I-36 skeptic); "
                      "retrying instead")
                continue
            # Readable again but not lifted: this attempt's press was genuinely
            # dropped, not a landed one gone blind. The look just taken proves the
            # target is back at rest and readable, so the next attempt's press
            # satisfies the same invariant this branch exists to protect.
            print(f"  [cursor] select_card did not land (attempt {attempt}) — retrying")
            continue
        if attempt < SELECT_ATTEMPTS:
            time.sleep(SELECT_RETRY_CONFIRM_SEC)
            _g, _ys, n, sel = _look_settled(look)
            if n != MAX_HAND_SIZE:
                print(f"  [cursor] cannot read the fan on the late re-check (rows={n})"
                      " — refusing")
                return False, sel
            if target in sel:
                print(f"  [cursor] select_card landed late ({SELECT_RETRY_CONFIRM_SEC}s)")
                # S-1: real read.
                _sel = _InferredSel(sel)
                _sel.inferred = frozenset({target})
                return True, _sel
            print(f"  [cursor] select_card did not land (attempt {attempt}) — retrying")
    print(f"  [cursor] select_card never landed after {SELECT_ATTEMPTS} attempts — refusing")
    return False, sel


# I-43: slots that MAY still be physically lifted because some earlier
# operation pressed select_card and then could not prove the board clean
# before giving up (an unreadable fan mid-unwind, a walk/deselect that never
# confirmed, a confirm press whose result was never verified). Process-local,
# module state -- reset at a hand-memory boundary (orchestrator.reset_hand_
# memory(), called at every match/half start, calls clear_maybe_lifted()) and
# otherwise persists ACROSS calls, because the stray it exists to catch is
# exactly one that survives from one _verified_select_and_play/select_and_
# discard call into the next (CLAUDE.md 10.28/10.29: an investigation -- here,
# a refused attempt -- that leaves state behind poisons the next one).
_MAYBE_LIFTED = set()


def clear_maybe_lifted():
    """Reset at a hand-memory boundary. See _MAYBE_LIFTED."""
    _MAYBE_LIFTED.clear()


def _mark_maybe_lifted(slots):
    """Record slot(s) a refused/incomplete attempt could not prove clean."""
    _MAYBE_LIFTED.update(s for s in slots if s is not None)


def _reconcile_maybe_lifted(ys, sel):
    """Clear a tracked slot the moment a read PROVES it down: a real (readable)
    y and not among the risen/selected rows. Until that proof arrives the slot
    stays protected, however many operations pass."""
    for slot in list(_MAYBE_LIFTED):
        if slot < len(ys) and ys[slot] is not None and slot not in sel:
            _MAYBE_LIFTED.discard(slot)


# I-48 SKEPTIC S-3: whether the LAST _verified_select_and_play_inner call committed a
# play with its tactics attachment DROPPED (the batter-alone fallback fired). Same
# shape as _MAYBE_LIFTED: module-local, because select_and_play returns one bool and
# this is the one extra bit orchestrator needs to keep match_log.jsonl honest about
# what actually went into the hand. Set False at the top of every
# _verified_select_and_play_inner call (so a call that never reaches the fallback, or
# refuses before it, reports False -- not a stale True from a PREVIOUS call), set True
# only inside the fallback branch. play_one_turn reads it via tactics_dropped_last_play()
# immediately after select_and_play returns True, before anything else touches state.
_LAST_PLAY_DROPPED_TACTICS = False


def tactics_dropped_last_play() -> bool:
    """True when the most recent _verified_select_and_play_inner call committed the
    batter alone after its tactics attachment could not be verified (I-48). Read this
    right after select_and_play(...) returns True -- the NEXT call resets the flag at
    its own top, so it answers only for the play that was just committed."""
    return _LAST_PLAY_DROPPED_TACTICS


def _unwind_selection(before, look, ours, ys0=None):
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

    S-2 (I-44 skeptic): `extra` IS COMPUTED FROM `sel`, WHICH IS RISEN ROWS ONLY. A
    slot that is lifted AND BLIND (I-21's own mechanism: selecting a card is what
    blinds its own disc) can never appear in `sel`, so it is invisible to `extra`
    -- this function then returns `True` having put NOTHING down and having proved
    NOTHING about it. That is the I-43 bug surviving the I-43 fix: the very next
    operation's own baseline read finds the same slot blind, and with nothing
    recorded here, `_clear_strays`'s I-26/I-28 exemption waves it through as a
    chronic occlusion. `ys0`, when the caller has it (both production callers do,
    it is the same operation-start snapshot threaded into `_clear_strays`), narrows
    the mark to I-21's own signature -- readable at the OPERATION's start, blind
    now -- so a target that was never even pressed (refused before any press, e.g.
    a genuinely chronic occlusion) is not marked and cannot deadlock a later commit
    that must wave it through. `ys0=None` (no caller support, e.g. the exception
    wrapper's recovery call, which has no baseline to offer) is PERMISSIVE, the
    same convention every other `ys0`/`kinds0`/`inferred_targets` gate in this file
    uses.
    """
    try:
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print("  [cursor] cannot read the fan to unwind — leaving the board as is; "
                  "the next caller must re-read rather than assume it is clean")
            # I-43: the fan cannot be read at all, so nothing in `ours` is
            # provably down. Whatever this attempt may have lifted survives
            # into the next caller unless proven clean.
            _mark_maybe_lifted(ours)
            return False
        _reconcile_maybe_lifted(_ys, sel)
        # S-2: mark every `ours` slot that is blind right now and was READABLE
        # at the operation's own start (or `ys0` is unavailable, permissive) --
        # this is checked BEFORE `extra`'s early return, because that return is
        # exactly the path S-2 found unguarded.
        _mark_maybe_lifted({s for s in ours
                             if s < len(_ys) and _ys[s] is None
                             and (ys0 is None or (s < len(ys0) and ys0[s] is not None))})
        extra = sorted((set(sel) - set(before)) & set(ours))
        if not extra:
            return True
        for i, slot in enumerate(extra):
            print(f"  [cursor] unwinding slot {slot}, raised by this refused attempt")
            ok, _s = _walk_cursor_to(slot, look)
            if ok:
                ok, _s = _deselect_verified(slot, look)
            if not ok:
                print(f"  [cursor] could NOT put slot {slot} back down — say so loudly "
                      "rather than let the next caller find it and commit it")
                # I-43: `slot` itself is unresolved, and every later slot in
                # `extra` this loop had not yet reached is equally unproven --
                # only the ones BEFORE it in this loop were confirmed down.
                _mark_maybe_lifted(extra[i:])
                return False
        return True
    except Exception as exc:
        print(f"  [cursor] unwind failed ({type(exc).__name__}: {exc})")
        # I-43: an exception mid-unwind leaves the board's state unknown.
        _mark_maybe_lifted(ours)
        return False


def _untrustworthy_slots(glow, ys):
    """Slots with no trustworthy start-of-operation position (I-26).

    An unmeasured y is the obvious case. The other is I-25's own shape one layer
    up: a disc that was found but never matched a digit only clears
    `local_hand.CURSOR_GLOW_MAX` by landing its glow window on a card's own white
    art (CLAUDE.md 10.35), which is exactly the reading `local_hand.cursor_glow`
    already refuses to let win its argmax. This layer never sees `rows`, only the
    raw glow numbers `look()` returns, so the ceiling is the only way to ask the
    same question here -- there is no `y_from`/`digit` to check directly.

    A slot this untrustworthy from the start cannot be proven "lifted by us"
    later just because its y went from a bogus number to None.
    """
    import local_hand
    blind = {i for i, y in enumerate(ys) if y is None}
    blind |= {i for i, g in enumerate(glow) if i < len(ys) and g > local_hand.CURSOR_GLOW_MAX}
    return blind


def _clear_strays(want, look, blind_before=frozenset(), ys0=None, kinds0=None,
                   inferred_targets=None):
    """Put down every lifted card the engine did not choose. True if safe to commit.

    Factored out of _verified_select_and_play so the DISCARD path can run it too.
    It had only ever guarded the play path, and that asymmetry is the one that
    produced the 2026-09-16 incident: the play path was hardened and the discard
    path kept an unverified irreversible press in the middle of it.

    AN UNMEASURED LIFT IS NOT A CARD THAT IS DOWN. selected_cards() skips a row
    whose y could not be measured (`if y is None or r.get("y_measured") is False`),
    which scores an ABSTENTION as the value "this card is not selected". The stray
    check is computed from that same list, so a card that is really raised but
    unreadable is not in `extra`, is never put back down, and goes in with the play.
    The mechanism is local_hand's own, at its comment on the raised-pass rescue: "A
    RAISED CARD'S DISC SHRINKS OUT OF DISC_MIN_R ... thr 130 r=13 -- under
    DISC_MIN_R 18, rejected." SELECTING A CARD IS WHAT MAKES IT UNREADABLE, so the
    unknown state is not rare here -- it is the state the guard exists for.

    So the gate below requires every y to be MEASURED, not merely that the fan was
    counted. The walk can still tolerate one unreadable card; the COMMIT cannot.

    A SLOT IN `want` IS NEVER A STRAY CANDIDATE (I-28). I-21 already established why
    a target's own disc goes blind: selecting IS what makes it unreadable, so a
    correctly-landed target reads exactly like a stray mid-lift. Scoring that as
    "went unreadable DURING this operation" refused a landed select three times
    running and excluded the card (overnight/run_live_20260920h.log:121-132,
    reproduced offline: want={1}, blind_before=set(), a look() that always answers
    slot 1 blind). The exemption is narrow -- only slots the engine itself chose are
    exempt; any OTHER slot that goes blind mid-operation still gets the I-26 re-look
    and, failing that, the refusal.

    A SKEPTIC CAUGHT THE FIRST VERSION TRUSTING `want` UNCONDITIONALLY. `lifted`
    below used to OR in every blind `want` slot with no further question, which
    means a target that was ALREADY occluded at baseline -- never actually
    selected, just permanently unreadable (CLAUDE.md 10.28) -- would be counted
    as lifted on the strength of being blind and being `want`, with nothing ever
    having proven it was toggled on. `ys0`, the baseline `_ys` the callers already
    capture before pressing anything, narrows the inference to I-21's own shape:
    a `want` slot counts as lifted by INFERENCE only when it was READABLE at
    baseline (`ys0[k] is not None`) and is blind NOW -- that is a proven lift, not
    a chronic occlusion. A `want` slot blind at baseline AND blind now must still
    show up in `sel` on its own merits, or the commit refuses.

    `kinds0` GATES THE SAME INFERENCE ON BASELINE KIND (I-36 skeptic). The
    identical heuristic above -- readable at baseline, blind now -- is ALSO
    what `_select_verified` uses, and it is reachable here independently: a
    fresh look taken at commit time, well after `_select_verified` already
    returned, can ALSO find a target's tactics row transiently blind. `kinds0`
    is the caller's OWN baseline kinds (the same look that produced `ys0`),
    and inference is trusted only when the baseline row was NOT 'tactics' --
    `None` (no kinds supplied) is permissive, matching every caller that
    predates this gate.

    `inferred_targets` GATES THE SAME want-blind INFERENCE ON REAL CORROBORATION
    (I-44). Everything above -- readable at baseline, blind now, not tactics --
    can be satisfied with NOTHING but a caller's own `ys0`/`kinds0` book-keeping;
    it does not require `sel` (a real, geometric read) or `_select_verified`'s
    own retry loop to have EVER actually seen `target` selected. Reproduced
    (QA6 Q2): a target that never lifts, ever, still commits, because those
    three facts describe a card that simply sat at rest the whole time just as
    well as one genuinely mid-lift -- the live shape is a dropped press plus a
    transient disc misread producing the identical three facts. `inferred_
    targets` is threaded from `_select_verified`'s OWN report of which
    target(s) IT concluded selected by inference on THIS operation (via
    `_InferredSel.inferred`, the SAME look-based retry loop, never a
    re-derivation) -- when a caller supplies it (even an empty set), a `want`
    slot blind at commit time is trusted ONLY if it is ALSO in `inferred_
    targets`; `None` (no caller support) is PERMISSIVE, the pre-I-44 ys0/
    kinds0-only behaviour, unchanged -- the same convention `kinds0` already
    uses, so every caller written before this needs no changes.

    N-2 (I-44 skeptic round 2, QA6 Q2 RE-OPENED): `inferred_targets` closed
    NOTHING on its own, because round 2 correctly widened `_InferredSel.
    inferred` to every success path (S-1's fix), which means `_select_
    verified`'s OWN inference is ALWAYS a member of whatever it reports --
    `inferred_targets` and the inference are the SAME conclusion asked twice.
    QA6 Q2's mechanism (a dropped press plus a transient disc misread) still
    reproduces the identical three facts a real lift does, and threading the
    inference in as its own corroboration cannot catch that.

    WHAT DOES CLOSE, NARROWLY: candidate 1 (selection-lift geometry, `local_
    hand.selected_cards`) is UNAVAILABLE for validating THIS inference by
    construction -- it needs exactly the disc `y` a blind target has already
    lost. Candidate 2 (this function's own `ys0`/`_baseline_readable`,
    extracted below) already requires a `want` slot to have been READABLE at
    THIS OPERATION's true start before the inference is trusted at all -- a
    target that starts the operation already blind (occluded, or a target
    `_select_verified`'s own LATER look disagreed with, see the "one unmarked
    exit" comment near `want <= lifted`) can never satisfy it, and must
    either show up in `sel` on its own (a real read; still committed, no
    inference needed) or the commit refuses. That is QA6 Q2's ORIGINAL
    repro -- `want={3}`, baseline readable+player-kind, `sel` permanently
    empty -- reversed: baseline UNREADABLE, `sel` permanently empty, refused.
    It does NOT close the harder, read-identical case control tests already
    pin as a MUST-COMMIT (a target readable at `ys0`, genuinely selected, then
    misread as blind by the same disc-fit noise I-21 exists to tolerate) --
    that is indistinguishable from a legitimate inference with the signals
    this function has, and closing it needs either a post-commit read (too
    late to prevent a wrong card, a detector not a fix) or per-row digit
    corroboration this function is never handed.

    `_MAYBE_LIFTED` GATES THE BASELINE-BLIND STRAY EXEMPTION (I-43).
    Symmetrically, a STRAY slot already blind at baseline is exempted below
    (I-26/I-28) on the strength of `blind_before` alone -- but `blind_before`
    cannot tell "a chronically occluded, never-selected card" apart from "a
    stray left lifted by an EARLIER refused attempt whose own unwind could not
    prove the board clean" (CLAUDE.md 10.28/10.29). `_MAYBE_LIFTED` (module
    state, see `_mark_maybe_lifted`) is that earlier attempt's own record, and
    a slot in it is never waved through this exemption -- it must be SEEN DOWN
    first.
    """
    _g, _ys, n, sel = _look_settled(look)
    if n != MAX_HAND_SIZE:
        print("  [cursor] cannot read the fan before committing — refusing. A "
              "commit whose lifted set was never seen is a blind commit.")
        # I-43: nothing in `want` can be proven clean off an unreadable frame.
        _mark_maybe_lifted(want)
        invalidate_cursor()
        return False
    _reconcile_maybe_lifted(_ys, sel)
    # AN UNMEASURABLE LIFT IS DANGEROUS ONLY IF WE COULD HAVE CAUSED IT.
    #
    # This refused whenever ANY y was None, and that deadlocked a live match on
    # 2026-09-17: slot 1's disc sat under its neighbour for the whole hand, so its
    # lift was unmeasurable FOREVER. The hand then read weak (the occluded card is
    # dropped, 10.28), should_redraw fired, the discard reached this guard, and it
    # refused -- leaving the state identical, so the next poll decided the same thing
    # and refused again. Neither a play nor a discard could ever commit: both call
    # this. Unattended that burns all 15 stuck attempts and ends the match with $50
    # spent and three rounds unplayed.
    #
    # The guard is still RIGHT about the hazard it was built for, and that hazard has
    # a direction: SELECTING a card is what makes it unreadable (the disc shrinks out
    # of DISC_MIN_R), so the dangerous case is a slot that WAS measurable and has
    # gone blind since -- something we did. A slot already blind in `blind_before`,
    # read before this operation pressed anything, cannot have been raised by us.
    #
    # This is the same line the stray check already draws: `extra` is computed
    # against `before`, so cards already up when we arrived are deliberately not
    # treated as ours. Extending that to "already unreadable" is consistent, not new
    # licence -- and it is NARROW, because a slot that goes blind mid-operation still
    # refuses exactly as before.
    _blind_now = {i for i, y in enumerate(_ys) if y is None}
    # I-28: `want` IS EXEMPT FROM "NEWLY BLIND". The engine's own target(s) are
    # EXPECTED to go blind the moment they lift (I-21's own mechanism: selecting a
    # card is what makes its disc unreadable), so a landed select must never be
    # scored as "went unreadable DURING this operation" -- that refused a correctly
    # selected card three times running and excluded it. Only a slot OUTSIDE
    # `want` can be newly blind in the dangerous sense this guard exists for.
    _new_blind = _blind_now - set(blind_before) - set(want)
    if _new_blind:
        # A SINGLE LOOK CAN CATCH A FLICKER, NOT A LIFT (I-26). The occluded-disc
        # reader can drop a slot from a real (if untrustworthy) position to
        # unreadable and back within a few frames of an UNCHANGED card
        # (CLAUDE.md 10.26: "a reader that looks stable on a still may not be").
        # Give it one more look, after the same settle this file already waits
        # out a swallowed press with, before treating that as something WE
        # raised.
        print(f"  [cursor] slot(s) {sorted(_new_blind)} read unreadable ({_ys}) — "
              "re-looking once before refusing")
        time.sleep(SELECT_RETRY_CONFIRM_SEC)
        _g, _ys, n, sel = _look_settled(look)
        if n != MAX_HAND_SIZE:
            print("  [cursor] cannot read the fan on the re-look — refusing. A "
                  "commit whose lifted set was never seen is a blind commit.")
            # I-43: `_new_blind` was already under suspicion; an unreadable
            # re-look proves nothing clean either way.
            _mark_maybe_lifted(_new_blind)
            invalidate_cursor()
            return False
        _reconcile_maybe_lifted(_ys, sel)
        _blind_now = {i for i, y in enumerate(_ys) if y is None}
        _new_blind = _blind_now - set(blind_before) - set(want)
        # NO "AT REST" FALLBACK (I-26, skeptic-refuted). A slot WE genuinely
        # lift and then cannot read looks IDENTICAL to a flicker at this point:
        # a raised card's disc shrinks out of DISC_MIN_R, so its y goes None
        # too, and selected_cards SKIPS a None row -- so `set(sel) - want`
        # is empty for a lifted-and-blind stray exactly as it is for a
        # never-touched one. Scripted: baseline readable, our own press lifts
        # it, None on the check-look AND the re-look -- the old fallback let
        # `ok=True` through with the card still up. One re-look is the whole
        # allowance; still unreadable after it is refused, full stop. The
        # only slots this never refuses are ones proven untrustworthy at
        # BASELINE (`blind_before`, case b above) or the engine's OWN targets
        # (`want`, I-28) -- never a STRAY that turned blind during this
        # operation.
        if _new_blind:
            print(f"  [cursor] slot(s) {sorted(_new_blind)} still unreadable after "
                  f"the re-look ({_ys}) — refusing. They were measurable when this "
                  "operation started, so something we pressed lifted them, and a "
                  "raised card would go in with the commit.")
            # I-43: still unreadable after the one allowed re-look.
            _mark_maybe_lifted(_new_blind)
            invalidate_cursor()
            return False
    _untouched_blind = _blind_now - set(want)
    if _untouched_blind:
        # I-43: a slot this operation cannot have raised (it was ALREADY blind
        # before anything was pressed) is not automatically safe to wave
        # through -- if an EARLIER refused attempt could not prove it clean,
        # `blind_before` alone (which only asks "was it blind before THIS
        # call") cannot tell that apart from a genuinely chronic occlusion.
        # See _MAYBE_LIFTED and this function's own docstring.
        _unproven = _untouched_blind & _MAYBE_LIFTED
        if _unproven:
            print(f"  [cursor] slot(s) {sorted(_unproven)} may still be physically "
                  "lifted by an earlier attempt that could not prove the board "
                  "clean (I-43) — refusing to commit rather than waving them "
                  "through as a chronic occlusion")
            invalidate_cursor()
            return False
        print(f"  [cursor] slot(s) {sorted(_untouched_blind)} were ALREADY unreadable "
              "before this operation began — proceeding. We cannot have raised them, "
              "and refusing forever is how a hand with one occluded card deadlocks.")
    _want_blind = set(want) & _blind_now
    if _want_blind:
        print(f"  [cursor] slot(s) {sorted(_want_blind)} are the engine's own "
              "target(s) and are unreadable — I-21's inference: selecting a card is "
              "what makes its own disc unreadable, so this is expected, not a stray.")
    # I-28: A `want` SLOT BLIND NOW *AND* READABLE AT BASELINE COUNTS AS LIFTED.
    # `sel` comes from selected_cards(), which abstains on exactly the row this
    # guard just exempted (its own y is None), so `sel` alone cannot see an
    # inferred-selected target -- the final commit gate below would refuse it
    # right after this guard just proved it safe. But the inference is only
    # earned by I-21's own signature -- READABLE then BLIND -- never by a slot
    # that was already unreadable before this operation touched anything (a
    # skeptic caught the first version trusting `want` unconditionally, which
    # would have let a chronically-occluded, never-selected target through).
    # I-36 SKEPTIC: the same "baseline was 'tactics'" gate _select_verified
    # uses, applied here too -- see this function's own docstring. `kinds0`
    # absent (None) is permissive, matching every caller written before this.
    def _baseline_not_tactics(k):
        return kinds0 is None or k >= len(kinds0) or kinds0[k] != "tactics"

    # I-44: `None` (no caller support) is PERMISSIVE -- unchanged pre-I-44
    # behaviour. A caller that supplies a real set (even empty) requires REAL
    # corroboration: `_select_verified` itself must have reported inferring
    # this exact slot on THIS operation.
    def _corroborated(k):
        return inferred_targets is None or k in inferred_targets

    # N-2 (I-44 skeptic round 2, QA6 Q2 re-opened): a DROPPED press on a target
    # whose disc was ALREADY blind before this operation ever pressed anything
    # produces the identical read as a genuine lift -- readable-before/blind-
    # after is what `_select_verified` infers from, and "before" there is ITS
    # OWN look, taken after the walk, which can disagree with THIS operation's
    # own earlier `ys0` (see the "the one unmarked exit" comment below `want <=
    # lifted`). Named here, not inlined, because it is the one fact a false
    # inference cannot manufacture: a slot that was NEVER readable at this
    # operation's true start cannot have gone "readable, then blind" during
    # it, whatever `_select_verified`'s own later look believed. It is exactly
    # `_baseline_not_tactics`'s shape, checked against `ys0` instead of
    # `kinds0`.
    #
    # WHAT THIS DOES NOT CLOSE, so it is not claimed here: a target that WAS
    # genuinely readable at `ys0` and is then misread as blind by a transient
    # circle-fit wobble (CLAUDE.md 10.26 -- "the fitted circle alternated
    # between r=19 and r=20") is READ-IDENTICAL to a real lift that blinds its
    # own disc (I-21's own stated mechanism), and nothing here -- or anywhere
    # in this function -- tells them apart; that is candidate-1-unavailable
    # by construction, because `selected_cards` needs exactly the disc `y`
    # this scenario has already lost (see its own docstring: "skip a row
    # whose y could not be measured").
    def _baseline_readable(k):
        return ys0 is not None and k < len(ys0) and ys0[k] is not None

    _want_inferred = {k for k in want
                       if k in _blind_now
                       and _baseline_readable(k)
                       and _baseline_not_tactics(k)
                       and _corroborated(k)}
    lifted = set(sel) | _want_inferred
    extra = lifted - want
    if extra:
        # TRY TO PUT THEM DOWN, with the same walk-and-verify used to raise them.
        # select_card is a TOGGLE, so this is the documented way to clear one -- but it
        # is only safe because every step is confirmed against the screen.
        _extra_sorted = sorted(extra)
        for _i, slot in enumerate(_extra_sorted):
            print(f"  [cursor] slot {slot} is lifted and the engine did not choose it "
                  f"(it chose {sorted(want)}) — putting it back down before committing")
            ok, _s = _walk_cursor_to(slot, look)
            if ok:
                ok, _s = _deselect_verified(slot, look)
            if not ok:
                print(f"  [cursor] could not clear slot {slot} — REFUSING to commit. "
                      "Committing a card the engine did not choose is worse than "
                      "committing nothing; the caller will re-read and retry.")
                # I-43: `slot` and everything after it in this loop were never
                # confirmed down.
                _mark_maybe_lifted(_extra_sorted[_i:])
                invalidate_cursor()
                return False
        # S-3 (I-44 skeptic): DO NOT reconcile against this read before its own
        # `n != MAX_HAND_SIZE` guard, below. `_look_settled`'s failure return
        # is `(glow, ys, 0, [])` -- it hands back the LAST bad frame's `ys`
        # (which can be full of real-looking numbers) while deliberately
        # EMPTYING `sel`. A tracked slot then satisfies both of
        # `_reconcile_maybe_lifted`'s conditions (`ys[slot] is not None` and
        # `slot not in sel`) purely because the read saw nothing -- the
        # safety measure `_look_settled` exists for becomes the false proof.
        # Reconciling happens only once this read is confirmed usable.
        _g, _ys, n, sel = _look_settled(look)
        _blind_now = {i for i, y in enumerate(_ys) if y is None}
        _want_inferred = {k for k in want
                           if k in _blind_now
                           and _baseline_readable(k)
                           and _baseline_not_tactics(k)
                           and _corroborated(k)}
        lifted = set(sel) | _want_inferred
        if n != MAX_HAND_SIZE or (_blind_now - set(want)) or lifted - want:
            print(f"  [cursor] after clearing, the lifted set is still {sel} against "
                  f"{sorted(want)} — refusing to commit")
            _mark_maybe_lifted((_blind_now - set(want)) | (lifted - want))
            invalidate_cursor()
            return False
        _reconcile_maybe_lifted(_ys, sel)
    if not want <= lifted:
        # I-44: name a target that fell out purely because it lacked real
        # corroboration, separately from the generic "not all lifted" line --
        # `_want_inferred`'s gate is what left it out of `lifted`.
        if inferred_targets is not None:
            _uncorroborated = (set(want) & _blind_now) - _want_inferred
            for k in sorted(_uncorroborated):
                print(f"  [cursor] slot {k} was never selected by inference on "
                      "this operation (I-44) — target not seen selected — "
                      "refusing to commit")
        # I-43 (skeptic, the one unmarked exit): a `want` slot that fails this
        # check may still be genuinely, physically lifted -- e.g. `_select_
        # verified` reported it selected against ITS OWN baseline look (taken
        # after the walk), while this operation's earlier, top-of-function
        # `ys0` read that same slot as already blind (a narrower window than
        # `_select_verified`'s own, so the two can disagree) and `_want_
        # inferred` then refuses to trust it. Whether it is up is genuinely
        # unproven either way -- mark it rather than assume either answer.
        _mark_maybe_lifted(set(want) - lifted)
        print(f"  [cursor] the engine's cards {sorted(want)} are not all lifted "
              f"({sel}) — refusing to commit a partial selection")
        invalidate_cursor()
        return False
    return True


def _verified_select_and_play(card_index, tactics_index, look):
    """Commit only what the engine chose, and leave nothing lifted on the way out.

    A WRAPPER, BECAUSE A RAISE USED TO LEAVE A CARD UP. Neither look() nor
    _look_settled was wrapped, and the look seam in production is
    orchestrator.hand_cursor_look -> _grab_settle_regions, a LIVE CAPTURE that can
    raise. A raise after press("select_card") propagated straight out:
    _unwind_selection never ran (it is only reached on an explicit `not ok`),
    invalidate_cursor() never ran, and the card stayed lifted.

    The stray it leaves is then the next caller's problem, and CLAUDE.md 10.29 is
    what that costs -- "an investigation that leaves state behind poisons the next
    experiment, and the result still looks like a finding". select_bans_verified was
    wrapped for exactly this shape ("AN EXCEPTION HERE USED TO LEAVE THE SCREEN
    MID-CHANGE"); the play path was not.

    The unwind is best-effort and never masks the original error: if the screen
    cannot be read to unwind, the raise still propagates.
    """
    # NO PRE-READ. Computing `before` here called _look_settled -- in production
    # orchestrator.hand_cursor_look -> _grab_settle_regions, a SETTLE-GATED LIVE
    # CAPTURE that retries LOOK_RETRIES times on an unreadable frame -- and the body
    # then calls _look_settled again as its first act. An unreadable hand burnt the
    # retry budget TWICE, and the extra read landed on every play, not just the
    # raising ones.
    #
    # An empty `before` is the right value anyway: _unwind_selection restricts itself
    # to `(set(sel) - before) & ours`, so before=set() puts down exactly the slots
    # THIS call targeted -- which on a raised, half-finished play is precisely what
    # should come back down, and nothing that belonged to a previous caller.
    _before = set()
    _targets = {t for t in (card_index, tactics_index) if t is not None}
    try:
        return _verified_select_and_play_inner(card_index, tactics_index, look)
    except Exception:
        try:
            _unwind_selection(_before, look, _targets)
        except Exception:
            pass
        invalidate_cursor()
        raise


def _verified_select_and_play_inner(card_index, tactics_index, look):
    """Read, step, verify, select, verify the selection, and only then commit.

    Returns True only when confirm_play was actually sent AND the fan was seen to
    change (I-11). False means NOTHING was committed and the caller should re-read and
    retry -- it must never be treated as a play, and it must never fall through to the
    blind path, which would make a refusal and a success indistinguishable
    (CLAUDE.md 10.1). False now also covers "we pressed up to PRESS_VERIFY_TRIES times
    and the chosen cards are STILL sitting lifted in a full fan", which is the game
    declining the press rather than us refusing to send it -- the same answer either
    way, because in both cases no card left the hand.

    A FALSE ALSO LEAVES THE BOARD AS IT FOUND IT, as far as it can. See
    _unwind_selection: an early refusal used to keep whatever it had already lifted.
    """
    global _LAST_PLAY_DROPPED_TACTICS
    _LAST_PLAY_DROPPED_TACTICS = False
    # THE BOARD AS WE FOUND IT. Anything already up belongs to a previous caller and
    # is not ours to clear; the commit path below handles a stray that is still there.
    _g0, _ys0, n0, before_all = _look_settled(look)
    # CAPTURED BEFORE `before_all` IS REBUILT AS A PLAIN SET, which loses the
    # `.kinds` attribute a real look() carries (I-36 skeptic) -- this is the
    # SAME baseline read `_ys0` comes from, so it is the correct kinds to
    # thread into `_clear_strays` below.
    _kinds0 = getattr(before_all, "kinds", None)
    before_all = set(before_all) if n0 == MAX_HAND_SIZE else set()
    targets = {t for t in (card_index, tactics_index) if t is not None}
    # I-44: which target(s) _select_verified itself concluded selected by
    # INFERENCE on THIS operation -- threaded into _clear_strays below so its
    # own commit-time inference requires the SAME proof rather than
    # re-deriving it from ys0/kinds0 alone.
    _inferred_targets = set()

    for target in (card_index, tactics_index):
        if target is None:
            continue
        ok, _sel = _walk_cursor_to(target, look)
        if ok:
            ok, _sel = _select_verified(target, look)
        if ok:
            _inferred_targets |= getattr(_sel, "inferred", frozenset())
            continue
        if target == tactics_index and target != card_index and card_index is not None:
            # I-48: THE TACTIC FAILED TO VERIFY, NOT THE BATTER -- card_index's own
            # walk+select already succeeded above, or this loop would never have
            # reached the tactics target at all. ISSUES.md I-48's census shows the
            # tactics select failing repeatedly whenever the cursor walk to it is
            # forced to cross an occluded slot (a home-plate runner's card, e.g.),
            # never the batter's own selection. `orchestrator.exclude_play_slot`
            # can only exclude the BATTER's hand_index on a refusal here (this
            # function returns one bool for the whole call, so the caller cannot
            # see which target failed) -- so refusing the whole play burns every
            # batter in turn for a boost worth ~+0.6 runs/half (CLAUDE.md §4)
            # against a stalled half. Unwind the tactic attempt ALONE and commit
            # the batter without it instead.
            #
            # `card_index is not None` (I-48 skeptic S-2): without it this guard is
            # also true on a TACTICS-ONLY call (card_index=None, which the signature
            # allows and no production caller passes today, orchestrator.py:8400 is
            # always an int) -- the premise in the paragraph above ("card_index's own
            # walk+select already succeeded") is exactly what is false there, and
            # `want` would become `set()`, committing confirm_play on an EMPTY fan
            # and reporting True. Reproduced offline (skeptic's probe_none.py): a
            # tactics-only call whose select never lands returned True having pressed
            # confirm_play with nothing lifted -- 10.1's "a success path and a no-op
            # path with identical output". A card_index=None call must still refuse.
            print(f"  [cursor] tactics slot {tactics_index} could not be verified "
                  "— dropping the boost and playing the batter alone (I-48)")
            _unwind_selection(before_all, look, {tactics_index}, ys0=_ys0)
            invalidate_cursor()
            tactics_index = None
            _LAST_PLAY_DROPPED_TACTICS = True
            continue
        _unwind_selection(before_all, look, targets, ys0=_ys0)
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
    # THE BASELINE IS THE PRE-PRESS READ AT THE TOP OF THIS FUNCTION, so a slot that
    # was never readable (or never trustworthy -- I-26) is told apart from one this
    # call lifted.
    _blind0 = _untrustworthy_slots(_g0, _ys0)
    if not _clear_strays(want, look, blind_before=_blind0, ys0=_ys0, kinds0=_kinds0,
                          inferred_targets=_inferred_targets):
        return False

    # LOOK AFTER THE COMMIT TOO (I-11). Every other press in this function is
    # confirmed against the screen and this one was not -- it was verified only
    # by the next poll, which shares its stuck_count with unrecognised screens.
    # RULES.md §1 records confirm_play ignored TWICE IN A ROW live on
    # 2026-09-20, and §5 measures the game declining 15.20% of presses.
    #
    # THE OBSERVE IS THE FAN, from the look() seam already in hand. The reveal
    # watcher would be the other candidate and is NOT available here:
    # hand_cursor_look's docstring records that input_controller must never
    # import back into orchestrator, which is where the reveal episode lives.
    #
    # A GONE FAN IS A SENTINEL, NOT None, and that direction is deliberate.
    # A landed confirm_play takes the card out of the fan, so _look_settled
    # stops returning MAX_HAND_SIZE rows -- mapping that to None would make
    # press_verified call every SUCCESSFUL play "blind after press" and answer
    # False, and this function's False means "nothing was committed", so the
    # caller would re-read and play a SECOND card. The sentinel makes the
    # failure direction "report success and let run()'s own re-read catch it",
    # which is exactly what this line did before any verification existed.
    #
    # The baseline is safe because _clear_strays has just proved a settled
    # MAX_HAND_SIZE fan with exactly `want` lifted, and _look_settled retries
    # LOOK_RETRIES times, so a single bad frame cannot make the baseline the
    # sentinel and turn a landed press into a retry.
    def _fan_state():
        _g, _ys, n, sel = _look_settled(look)
        return tuple(sorted(sel)) if n == MAX_HAND_SIZE else ("fan-gone",)

    ok, _sent = press_verified("confirm_play", _fan_state, log=print)
    invalidate_cursor()
    return ok


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


def select_and_discard(card_index: int, look=None, discards_look=None):
    """
    Navigate to a card and discard it for a replacement.

    A DISCARD DOES NOT USE THE TURN. It swaps one card for a new one and the
    player still plays normally afterwards. Confirmed by the user 2026-09-16,
    and the arithmetic of that same match says the same thing: the batting half
    took 2 DISCARDS AND 5 PLAYS, and a half is only 5 rounds -- so five plays
    are impossible if a discard costs one.

    THIS FUNCTION THEREFORE NO LONGER PRESSES confirm_play, AND THAT PRESS WAS
    THE BUG. It was here on a claim dated 2026-08-23 that "the game deals a
    replacement card and auto-lifts it with its own PLAY prompt, which still
    needs confirm_play to actually commit it as this turn's play". That claim is
    withdrawn. Triangle after a discard commits nothing useful and, when the
    Square press is DROPPED -- which this console does -- it commits the card
    that is still lifted: on 2026-09-16 it pitched the worst card in the hand
    (a 5/0) at the opponent, who hit it. The ROUND pips went 4 -> 5 while
    discards_left sat at 2, which is the whole story in two numbers.

    CLAUDE.md's N27 ("a redraw does not mean no turn was consumed") rested on
    the same withdrawn claim and is corrected with it.

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
        # The replacement card is dealt into this slot, so the cursor is wherever
        # the game put it — not necessarily where we left it. Drop the belief
        # rather than guess; the next navigation re-homes.
        #
        # NO confirm_play. See the docstring: a discard does not use the turn, and
        # Triangle here plays whatever is still lifted whenever Square is dropped.
        invalidate_cursor()
        return True

    # VERIFIED. This function's own docstring records a discard landing on the
    # wrong card live (2026-08-28: the engine chose a power-4 player and a tactics
    # card was thrown), and homing was the cheap mitigation available then. Reading
    # the screen is the real one: the same walk-and-verify the play path uses, and
    # the lift must name THIS card before anything irreversible is pressed.
    #
    # READ THE FAN BEFORE TOUCHING IT. The play path already had this (`_ys0`) and the
    # discard path did not, so it had no way to tell a slot it had just lifted from one
    # that was unreadable all along -- see _clear_strays. One look, ~40 ms.
    _g0, _ys0, _n0, _before0 = _look_settled(look)
    _blind0 = _untrustworthy_slots(_g0, _ys0) if _n0 == MAX_HAND_SIZE else frozenset()
    _ys0_for_strays = _ys0 if _n0 == MAX_HAND_SIZE else None
    # SAME BASELINE, SAME KINDS (I-36 skeptic) -- see _verified_select_and_play_inner.
    _kinds0_for_strays = getattr(_before0, "kinds", None)
    ok, _sel = _walk_cursor_to(card_index, look)
    if not ok:
        # I-43: the walk itself can probe-select `card_index` (I-02) and then
        # refuse without knowing whether that press landed.
        _mark_maybe_lifted({card_index})
        invalidate_cursor()
        return False
    ok, _sel = _select_verified(card_index, look)
    if not ok:
        # I-43: an exhausted or dropped select_card leaves the card's true
        # state unproven.
        _mark_maybe_lifted({card_index})
        invalidate_cursor()
        return False
    # I-44: which target(s) _select_verified concluded selected by inference
    # on THIS operation -- see _verified_select_and_play_inner's own comment.
    _inferred_targets = getattr(_sel, "inferred", frozenset())
    # AND CLEAR THE STRAYS, exactly as the play path does. This was the asymmetry:
    # _verified_select_and_play computed `extra = lifted - want` and walked to every
    # stray before confirm_play, refusing if it could not; the discard path went
    # straight from _select_verified to an IRREVERSIBLE press without ever reading
    # which OTHER cards were up.
    #
    # A stray at this point is the NORMAL case, not an exotic one: _unwind_selection
    # deliberately leaves a wrongly-raised card up ("pressing again compounds it"),
    # and the clear-at-commit is the play path's answer to that. The discard path
    # simply did not have one.
    if not _clear_strays({card_index}, look, blind_before=_blind0, ys0=_ys0_for_strays,
                          kinds0=_kinds0_for_strays, inferred_targets=_inferred_targets):
        return False
    # AND PUT THE CURSOR BACK ON THE CARD. _clear_strays walks to each stray to
    # deselect it and does not walk back, so adding it here parked the cursor on the
    # LAST CLEARED STRAY immediately before confirm_discard -- and a stray at this
    # point is the NORMAL case by that block's own argument. Every earlier version of
    # this function pressed confirm_discard with the cursor on card_index; the blind
    # path still does (_move_cursor_to(card_index) two lines before its press).
    #
    # Whether Square acts on the SELECTED card or the card under the cursor cannot be
    # determined offline and the console is asleep, so this restores the invariant
    # rather than relying on the answer. It costs nothing on the common path: the walk
    # is a no-op when the cursor is already there.
    ok, _sel = _walk_cursor_to(card_index, look)
    if not ok:
        print(f"  [discard] could not put the cursor back on slot {card_index} after "
              "clearing strays — REFUSING rather than pressing confirm_discard from "
              "wherever the clearing left it.")
        # I-43: _clear_strays just proved card_index genuinely lifted; this
        # walk's own probe-select could disturb that before it is read again.
        _mark_maybe_lifted({card_index})
        invalidate_cursor()
        return False
    # THE DISCARD MUST BE PROVEN BEFORE confirm_play, AND IT WAS NOT.
    #
    # This block used to read: press confirm_discard, then "there is nothing left to
    # verify -- the choice was made at confirm_discard", then press confirm_play.
    # That is false on this console, which drops presses. If confirm_discard is
    # swallowed the card is still merely SELECTED, and confirm_play then PLAYS IT.
    #
    # Reproduced live 2026-09-16, and the evidence was a counter nothing was reading:
    # discards_left was 2 before and 2 after, while the ROUND pips went 4 -> 5 and the
    # diamond changed. The worst card in the hand (a 5/0) was pitched at the opponent
    # because a Square press went missing. The PLAY path was hardened against exactly
    # this shape; the discard path kept an unverified irreversible press in the middle.
    #
    # `discards_look` is the seam: a callable returning discards_left, or None. It is
    # injected rather than imported so input_controller never has to import
    # orchestrator back, and so the offline suite can drive it.
    before = None
    if discards_look is not None:
        try:
            before = discards_look()
        except Exception:
            before = None
    press("confirm_discard")
    if discards_look is not None and before is not None:
        # MORE TRIES CAN ONLY TURN A REFUSAL INTO AN ANSWER -- the same reasoning
        # MONEY_READ_TRIES carries: every attempt is the same conservative reader, so
        # retrying invents no confidence, it only waits out a counter that is still
        # animating.
        dropped = False
        answered = False          # did ANY poll come back with a number at all?
        for _ in range(DISCARD_CONFIRM_TRIES):
            time.sleep(ACTION_DELAY)
            try:
                now = discards_look()
            except Exception:
                now = None
            if now is not None:
                answered = True
            if now is not None and now < before:
                dropped = True
                break
        if not dropped and answered:
            # WE KNOW THE DISCARD DID NOT REGISTER, because the counter ANSWERED and
            # did not move. Pressing confirm_play here is the bug: it plays the card.
            # Refusing leaves the card lifted and nothing committed, which the caller
            # can re-read and recover from.
            print(f"  [discard] confirm_discard did not register — discards_left is "
                  f"still {before}. REFUSING to press confirm_play, because that would "
                  f"PLAY slot {card_index} instead of discarding it.")
            # I-43: the card is confirmed still selected -- the next caller
            # must see it down before waving it through as a chronic occlusion.
            _mark_maybe_lifted({card_index})
            invalidate_cursor()
            return False
        if not dropped:
            # NOT THE SAME THING, AND IT USED TO BE. `dropped` was only ever set on
            # `now is not None and now < before`, so FIVE ABSTENTIONS were
            # indistinguishable from five readings that said the counter had not
            # moved. A discard that really landed then exited reporting "did not
            # register" about a press that was no longer there -- and the caller says
            # "nothing thrown", after which an operator or a retry spends the SECOND
            # of only two discards in the half.
            print(f"  [discard] the counter never answered after the press "
                  f"({DISCARD_CONFIRM_TRIES} tries) — the discard is UNVERIFIED, not "
                  f"refused. Slot {card_index} may or may not have been thrown; the "
                  "caller must re-read rather than retry blind.")
            # I-43: confirm_discard was pressed and its result is genuinely
            # unknown -- the card may still be selected.
            _mark_maybe_lifted({card_index})
            invalidate_cursor()
            return False
    elif discards_look is not None:
        # THE COUNTER COULD NOT BE READ BEFORE THE PRESS. This used to print exactly
        # this and then RETURN TRUE, so one abstention on the pre-read disabled the
        # whole proof and the verdict still read like a checked discard (10.1).
        print("  [discard] discards_left could not be read before the press, so the "
              "discard is UNVERIFIED — the card may or may not have been thrown. "
              "Returning False so the caller re-reads rather than assumes.")
        # I-43: same reasoning -- confirm_discard was pressed, unverified.
        _mark_maybe_lifted({card_index})
        invalidate_cursor()
        return False
    else:
        # NO SEAM AT ALL. A caller that passes no discards_look cannot be given a
        # verified answer, and saying True here is what let the production redraw
        # path believe a proof that never ran.
        # I-43: same reasoning -- confirm_discard was pressed, unverified.
        _mark_maybe_lifted({card_index})
        print("  [discard] no discards_look seam was passed, so nothing verified this "
              "discard — returning False rather than a True nobody checked.")
        invalidate_cursor()
        return False
    # NO confirm_play. A discard does not use the turn, and Triangle here is what
    # played the card on 2026-09-16 when the Square press was swallowed.
    invalidate_cursor()
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
# DERIVED FROM THE MEASURED IGNORE RATE, NOT FROM THE GRID'S SIZE. It was 14 --
# "12 moves of travel plus 2 slack" -- which is right only if every press lands.
# It does not: measured 2026-09-17 over 1000 presses on a live ban screen, each one
# confirmed against chiaki's own instrumented log before being scored, the console
# receives about one press in six and the GAME declines to act on it. Nothing we send
# is lost (undelivered: 0 of 1000).
#
#     ignored 152 / 1000 = 15.20%
#     P(ignore | previous IGNORED) = 0.250      <- they CLUSTER
#     P(ignore | previous moved)   = 0.135
#     longest consecutive-ignore run: 4
#
# `moves` counts EVERY press, landed or not, so this is a budget of presses and not of
# travel. Markov simulation over 200,000 trials, P(reaching a 12-move target):
#
#     budget 14  64.36%   <- what shipped: a far ban silently missing 1 time in 3
#     budget 18  97.55%
#     budget 20  99.52%
#     budget 22  99.92%   <- chosen
#
# It cannot simply be raised to infinity: the budget is also the bail-out for a cursor
# that is genuinely stuck, on a match that has been paid for. 22 buys 99.9% of reachable
# targets while still giving up in about 22 seconds on one that is not.
BAN_NAV_MAX_STEPS = 22
# UNMEASURED, AND SAID SO HERE RATHER THAN LEFT TO READ LIKE EVIDENCE.
#
# CLAUDE.md already names this and BAN_CURSOR_PROBE_TRIES as invented; a QA sweep
# confirmed both and added LOCK_CONFIRM_TRIES. None of the three sits between two
# measured populations, which is the standard every other gate on this path is held
# to (10.4):
#
#   BAN_NAV_SETTLE 0.55        justified as "about twice ACTION_DELAY" -- DERIVED
#                              FROM ANOTHER CONSTANT, not from a measured settle
#   BAN_CURSOR_PROBE_TRIES 3   justified in prose, with no measurement of how long a
#                              routine blind period lasts -- and denominated in
#                              BAN_NAV_SETTLE, so it inherits that constant's error
#   LOCK_CONFIRM_TRIES 4       no comment and no measurement at all, and unlike the
#                              conservative-reader budgets (MONEY_READ_TRIES,
#                              BAN_COUNTER_READ_TRIES) exhausting it ANSWERS rather
#                              than refuses -- the opposite kind of budget
#
# THE VALUES ARE NOT BEING CHANGED. There is no measurement to move them toward, and
# inventing one is the same bug wearing a fix's clothes. What would settle all three
# is one offline pass: log a timestamp and ban_cursor_absolute()'s answer on every
# poll through a real ban navigation, then read off how long a routine blind period
# actually is. Until then they are working guesses, and they are labelled as such.
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
                # A GOOD LOOK RESETS THE BLIND BUDGET, because the constant's own
                # comment says "consecutive unreadable frames per target" and the
                # code counted CUMULATIVE ones -- `blind` was initialised once per
                # target and never reset. ban_cursor_absolute returns None BY DESIGN
                # whenever the scrollbar is mid-travel, which is exactly what a
                # scrolling press produces, so blind frames arrive interleaved with
                # good ones rather than in a run and the budget of 10 was spent
                # across the whole approach. That is the same failure the separate
                # move/blind budgets were introduced to fix: a far target silently
                # skipped, reported as ban_nav_incomplete, and the match played with
                # 2 of 3 bans.
                blind = 0
                if here == want:
                    # WHAT WAS BANNED BEFORE THIS PRESS. `confirm_ban` can only say
                    # whether an X is on the cell we AIMED at, so an X that landed
                    # somewhere else reads as a missing ban and the counter still
                    # says 3/3. The difference of the full set names the actual card.
                    _before = banned_set() if banned_set is not None else None
                    reached = True
                    # A DROPPED select_card LOOKS IDENTICAL TO A DECLINED ONE (CLAUDE.md
                    # §5: 15.2% of presses are silently ignored, clustered) and this was
                    # the one press on the whole ban path with no retry at all. Retry up
                    # to PRESS_VERIFY_TRIES -- but never blind: select_card is a TOGGLE,
                    # so a retry that fires after a press that DID land, just late (the
                    # selection splash), would un-ban the very cell it meant to confirm.
                    # Before each retry: re-look to confirm the cursor is still on
                    # `want`, and re-check the full set for a splash that caught up.
                    _settled = False
                    for _attempt in range(1, PRESS_VERIFY_TRIES + 1):
                        if _attempt > 1:
                            # A SETTLED FRAME, NOT THE ONE THE PREVIOUS PRESS LEFT
                            # BEHIND. Without this sleep the only settle a retry's
                            # re-check had was the one already spent before _after
                            # below plus the wall time of one look() + one
                            # banned_set() -- reader time, not a settle. A splash
                            # that outlives that would then have this re-check miss
                            # the X and press again, un-banning it.
                            time.sleep(BAN_NAV_SETTLE)
                            _here_retry = look()
                            if _here_retry is None:
                                # A BLIND FRAME IS NOT A MOVED CURSOR. Reported as
                                # "cursor left" before, which named the wrong cause
                                # and abandoned the chain on one unreadable frame.
                                # Try again rather than pressing blind or giving up.
                                log(f"  [ban] the ban screen could not be read before "
                                    f"retry {_attempt}/{PRESS_VERIFY_TRIES} — trying "
                                    "again rather than pressing blind")
                                continue
                            if _here_retry != want:
                                log(f"  [ban] cursor left {want} before retry "
                                    f"{_attempt}/{PRESS_VERIFY_TRIES} — not pressing "
                                    "again")
                                break
                            _recheck = banned_set() if banned_set is not None else None
                            if _recheck is not None and want in _recheck:
                                log(f"  [ban] {want} now carries an X on re-look — the "
                                    "earlier press landed late (selection splash); not "
                                    "pressing again")
                                _after = _recheck
                                placed.append(want)
                                _settled = True
                                break
                        press("select_card")
                        toggled += 1
                        time.sleep(BAN_NAV_SETTLE)
                        _after = banned_set() if banned_set is not None else None
                        if _before is None or _after is None:
                            if confirm_ban is None or confirm_ban(want):
                                placed.append(want)
                            else:
                                # THE TOGGLE DID NOT TAKE. Pressing again is not safe --
                                # select_card is a TOGGLE, so a second press on a card
                                # that DID ban un-bans it. Report. (No banned_set() here
                                # to distinguish a splash from a genuine drop, so this
                                # path does not retry -- census: zero misses came from
                                # it.)
                                log(f"  [ban] select_card at {want} did not place an X "
                                    "— leaving it")
                            _settled = True
                            break
                        _new = _after - _before
                        # AND THE OTHER DIRECTION. select_card is a TOGGLE, so a press
                        # that lands on a cell ALREADY banned by an earlier target
                        # REMOVES that X. `_after - _before` is then empty, this fell
                        # to the else branch and logged "placed no X anywhere --
                        # leaving it", on_wrong_ban never fired, and the run finished
                        # with fewer bans than it believed and no observation saying so.
                        # A disappearance is a wrong-cell press exactly as much as an
                        # appearance; only the direction differed.
                        _gone = _before - _after
                        if _gone:
                            log(f"  [ban] UN-BANNED: pressing at {want} REMOVED the X "
                                f"from {sorted(_gone)} — select_card is a toggle and "
                                f"the cursor was not where the last look said. NOT "
                                f"re-pressing.")
                            if on_wrong_ban is not None:
                                on_wrong_ban(want, _gone)
                            # ...and it is no longer placed, whatever an earlier target
                            # recorded. `placed` must describe the SCREEN.
                            for _p in _gone:
                                if _p in placed:
                                    placed.remove(_p)
                        if _new == {want}:
                            placed.append(want)
                            _settled = True
                            break
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
                            _settled = True
                            break
                        # NOTHING CHANGED. Advance the baseline to THIS look before the
                        # next retry, so its own diff is scored against here, not
                        # against the frame before the very first press.
                        _before = _after
                    if not _settled:
                        log(f"  [ban] select_card at {want} placed no X anywhere after "
                            f"{PRESS_VERIFY_TRIES} tries — leaving it")
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
        # HOME THE CURSOR FIRST, BY SATURATION. select_bans_and_start_full's own
        # docstring says "Assumes the caller starts at (0, 0)" and it does not home.
        # By the time we get here the navigator may have spent up to BAN_NAV_MAX_STEPS
        # moves PER TARGET without ever toggling -- `toggled == 0` is a fact about
        # SELECT presses and says nothing about MOVE presses -- so the cursor can sit
        # rows and columns away from where the dead-reckoned path believes it is, and
        # every one of its counted presses then lands on the wrong card. That is
        # CLAUDE.md's named "worst outcome available": three cards banned, all wrong,
        # read_ban_counter says 3/3.
        #
        # Saturation is the only homing available with a blind cursor: move_up at row 0
        # and move_left at column 0 are no-ops, so over-pressing costs presses, never
        # position. It is the same trick reset_hand_cursor(force=True) uses on the hand.
        for _ in range(BAN_NAV_MAX_STEPS):
            press("move_up")
            time.sleep(BAN_NAV_SETTLE)
        for _ in range(BAN_NAV_MAX_STEPS):     # 14 > any grid width; over-pressing
            press("move_left")                 # a boundary is a no-op, by design
            time.sleep(BAN_NAV_SETTLE)
        on_blind()
        # RETURN WHAT WE VERIFIED, WHICH IS NOTHING -- NOT WHAT WE INTENDED.
        #
        # This used to `return sorted(banned_positions)`, i.e. the INTENT. run() checks
        # `sorted(_placed) != sorted(banned_positions)` to decide whether to record
        # ban_nav_incomplete, so returning the intent made that check False by
        # construction: a run that placed three WRONG cards printed a clean 3/3 and
        # recorded nothing. A success path and a failure path with identical output
        # (10.1), inside the guard added to prevent exactly this.
        #
        # `placed` is [] here by definition (toggled == 0). That is the honest answer:
        # this function verified nothing. The dead-reckoned path may well have placed
        # all three, and the ban_nav_blind_midway observation its caller records is
        # what says so -- but it is unverified, and unverified must not read as placed.
        return placed
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
    path.

    IT DOES NOT MEAN A TEST RUN CANNOT MOVE THE CHARACTER, AND THIS DOCSTRING
    SAID IT DID. Refusing here only closes the BACKGROUND path; all three callers
    then fall straight through to pyautogui, which types into whatever window is
    FRONTMOST. That is how "c" (confirm_play) appeared in the user's own window
    on 2026-09-13 with a paid match parked on the console. The question is
    answered AT the damage by focus_input_allowed(), which press(), hold_combo()
    and walk_at() all call; read that one for the actual guarantee.
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


# THE GAME IGNORES ABOUT ONE PRESS IN SIX, AND NOTHING WE SEND IS LOST.
# Measured 2026-09-17 on a live ban screen, every press confirmed against chiaki's own
# instrumented log before being scored (n=60):
#
#     moved                50
#     IGNORED by the game  10   (16.7%)
#     never reached chiaki  0
#
# Four hypotheses died to get that number, each killed by a measurement rather than an
# argument: stale frames fooling the cursor reader (40/40 double-reads agreed), chiaki's
# isAutoRepeat discarding (zero discards in ~150 presses), its edge-collapse dedup (keys
# == edges exactly), and a null CGEventSource costing deliveries (100% on all three
# sources, interleaved). The press ARRIVES and the game declines to act on it.
#
# So no delay, no event-source change and no faster retry can prevent this -- the only
# thing that works is to LOOK, and press again if it did not take. Waiting longer does
# not help either: the gap since the previous move is the same for ignored presses as for
# accepted ones.
# AND THE FIRST VERSION OF THIS NUMBER WAS WRONG BECAUSE IT ASSUMED INDEPENDENCE.
# It was 3, justified as 0.167**3 = 0.47%. That arithmetic treats each press as its own
# coin flip, and the n=1000 run above refutes it: after an ignored press the next one is
# ignored 25.0% of the time against 13.5% after a good one. Ignores come in runs, and the
# longest observed was 4. A retry budget is exactly where that matters, because every
# retry is conditioned on the press before it having failed.
#
#     tries=3   0.950%   <- the independence assumption claimed 0.47%
#     tries=4   0.237%
#     tries=5   0.059%   <- chosen; also covers the longest run actually observed
#
# n=60 could not have shown this -- 10 ignores cannot separate 0.25 from 0.135. It took
# 152. That is the argument for the bigger sample, and it was not precision.
PRESS_VERIFY_TRIES = 5
PRESS_VERIFY_SETTLE = 0.45      # time for the UI to show the change before re-reading


def press_verified(action, observe, tries=None, settle=None, log=None):
    """Press `action` until `observe()` proves it landed. Returns (ok, presses_sent).

    `observe` returns any comparable value that CHANGES when this press takes effect --
    the ban cursor's cell, a counter, a selected slot. It returns None when it cannot
    tell, and that distinction is the whole safety of this function.

    IT NEVER PRESSES WHILE BLIND, AND THAT IS THE POINT. Many of these actions are
    TOGGLES: select_card bans a card and pressing it again UN-bans it. So a retry issued
    because we could not see is strictly worse than no retry at all -- it can undo the
    thing that actually worked. When `observe()` returns None this re-READS, and if it
    is still None it gives up with ok=False rather than pressing into the dark. A caller
    that gets ok=False knows nothing was committed on the last attempt.

    It also refuses to start blind: with no baseline there is nothing to compare against,
    and "it changed" would be unanswerable.
    """
    tries = PRESS_VERIFY_TRIES if tries is None else tries
    settle = PRESS_VERIFY_SETTLE if settle is None else settle
    sent = 0

    def _look(attempts=6):
        for _ in range(attempts):
            v = observe()
            if v is not None:
                return v
            time.sleep(0.15)
        return None

    before = _look()
    if before is None:
        if log:
            log(f"    [verify] {action}: cannot see the starting state — NOT pressing")
        return False, 0

    for attempt in range(1, tries + 1):
        press(action)
        sent += 1
        time.sleep(settle)
        after = _look()
        if after is None:
            # Blind AFTER a press. The press may or may not have taken, so pressing
            # again could double-toggle. Stop and say so.
            if log:
                log(f"    [verify] {action}: blind after press {attempt} — "
                    f"stopping rather than risking a double-toggle")
            return False, sent
        if after != before:
            if log and attempt > 1:
                log(f"    [verify] {action}: took on attempt {attempt}/{tries}")
            return True, sent
        if log:
            log(f"    [verify] {action}: no change after attempt {attempt}/{tries} "
                f"(state still {before!r}) — the game ignored it, retrying")
    if log:
        log(f"    [verify] {action}: FAILED after {tries} attempts, state never left {before!r}")
    return False, sent


def _release_keycodes(Quartz, pid, codes):
    """Post key-UP for every keycode that got a key-DOWN, from a finally.

    Returns True when every key was released, so the callers keep their
    ORIGINAL contract: any failure across DOWN / sleep / UP still answers
    False, and press()'s announced fallback still fires. The release is the
    only thing this adds.

    A DOWN with no UP is a key HELD DOWN at chiaki, and therefore at the
    console -- the keyboard twin of the dropped release packet section 5 calls
    "the lurking catastrophe" on the stick path. Both callers used to post
    DOWN, sleep, then post UP inside one try/except with no finally, so:

        raise on the UP post        key held, and the function returns False
        raise on a later DOWN       the earlier keys held, returns False
        KeyboardInterrupt in sleep  key held, and `except Exception` cannot
                                    catch a BaseException, so it propagates
                                    without even reaching the return

    All six cases reproduced offline with a stubbed Quartz by
    agent_progress/qa3-bghold/probe_stuck_key.py. The exposure is not exotic:
    press() routes EVERY button press through _bg_hold_keys, and
    reset_env._probe_transports holds look_right for 0.3 s at a time.

    It never raises -- there is nothing else to try, and raising from a finally
    would replace the original exception with this one. It is LOUD instead,
    because a release that silently failed is section 10.1's exact shape on the
    one path that reaches the console.
    """
    released = True
    for c in reversed(codes):
        try:
            Quartz.CGEventPostToPid(
                pid, Quartz.CGEventCreateKeyboardEvent(None, c, False))
        except Exception as exc:
            released = False
            print(f"  [input] COULD NOT RELEASE keycode {c} at pid {pid}: "
                  f"{exc!r} -- that key may STILL BE HELD DOWN at the console.")
    return released


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
    posted, ok = [], True
    try:
        Quartz.CGEventPostToPid(
            pid, Quartz.CGEventCreateKeyboardEvent(None, code, True))
        posted.append(code)
        time.sleep(hold_seconds)
    except Exception:
        ok = False
    finally:
        released = _release_keycodes(Quartz, pid, posted)
    if not (ok and released):
        return False
    time.sleep(ACTION_DELAY if post_delay is None else post_delay)
    return True

def _bg_hold_keys(keys, seconds):
    """Hold raw key names down together for `seconds`, targeted at chiaki.

    Returns True if it handled them. It is the single low-level route for the
    TARGETED Quartz path, and it does now ask targeted_input_allowed() before
    posting anything.

    IT IS NOT THE ONE PLACE THAT DECIDES "game or the user's work", AND THIS
    DOCSTRING CLAIMED IT WAS. There are FIVE emission paths (CLAUDE.md §5) and a
    public call reaches this one only when the background route is available:

        keyboard        press / hold_combo / walk_at   -> pyautogui
        targeted        press_background / _bg_hold_keys -> CGEventPostToPid  <- here
        sticks          analog_replay.send             -> the FIFO
        recovery keys   ensure_stream._key             -> CGEventPostToPid
        raw masks       inject_reset.tap / clear       -> the FIFO

    Each needed its own lockout and four of the five were found by looking rather
    than by a failure. A docstring that claims a chokepoint it does not own is
    worse than none: it is where the next reader stops looking.
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
    posted, ok = [], True
    try:
        for c in codes:
            Quartz.CGEventPostToPid(
                pid, Quartz.CGEventCreateKeyboardEvent(None, c, True))
            posted.append(c)
        time.sleep(seconds)
    except Exception:
        ok = False
    finally:
        released = _release_keycodes(Quartz, pid, posted)
    return ok and released
