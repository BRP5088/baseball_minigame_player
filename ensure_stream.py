"""Make sure the game is streaming before doing anything that drives it.

The PS5 drops to standby on its own after a stretch of inactivity, and chiaki
falls back to its host list. Everything downstream then fails in a confusing
way — the reset reports "pause menu did not open after 5 OPTIONS presses",
which sounds like a button problem and is actually a disconnected console.

So: check first, and reconnect if needed, rather than letting each script
discover the disconnection separately.
"""

import os
import subprocess
import time

import compass
import pause_menu as pm

CONNECT_WAIT = 6.0
MAX_WAIT = 150.0


def _pid():
    """The chiaki pid, from the ONE resolver that checks what the process IS.

    This was `pgrep -f chiaki-ng-build` taking out[0] -- the same loose
    command-line match that sent an afternoon of presses into a /bin/zsh
    (see input_controller._resolve_chiaki_pid). "chiaki-ng-build" is more
    specific than "chiaki", which is why it survived that round; it is not a
    guard. REPRODUCED 2026-09-13 in about a minute:

        $ /bin/sh -c 'sleep 20; : chiaki-ng-build' &
        ensure_stream._pid()          -> 10919   actually chiaki? False
        input_controller.chiaki_pid() -> 83980

    New pids on this machine are LOWER than chiaki's, so the decoy sorted
    first and won. _key() below posts straight to whatever this returns, so
    the escape ladder's Return/Down/Escape would have gone to that shell --
    and the ladder would then report that it tried and nothing moved, which
    is 10.1's no-op-indistinguishable-from-success on the recovery path.

    Imported lazily: input_controller pulls in Quartz and pyautogui, and this
    module is imported by things that only want streaming().
    """
    import input_controller
    return input_controller.chiaki_pid()


def _key(pid, code, after=1.2):
    """Post one key to chiaki's process. HARD OFF under BASEBALL_TEST_RUN.

    It needs its own lockout rather than inheriting one: this is a third path
    to the console, beside input_controller's keyboard path and
    analog_replay's stick path, and it resolves its own pid and posts its own
    Quartz events. The offline suite has driven the live console through
    exactly this kind of gap before (analog_replay's docstring records it),
    and today's keyboard hole was the same shape one module over.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        print(f"  [stream] BASEBALL_TEST_RUN is set — refusing to post key "
              f"{code} to pid {pid}. If this is a live run, the recovery "
              f"ladder is a no-op until you unset it.")
        return
    if pid is None:
        print("  [stream] no chiaki pid — not posting a key to nothing")
        return
    import Quartz
    for down in (True, False):
        Quartz.CGEventPostToPid(
            pid, Quartz.CGEventCreateKeyboardEvent(None, code, down))
        if down:
            time.sleep(0.06)
    time.sleep(after)


# chiaki's own stdout, as redirected by restart_chiaki.sh. A runtime log, so
# /tmp is the right place for it — unlike source or findings.
CHIAKI_LOG = os.environ.get("CHIAKI_LOG", "/tmp/chiaki_run.log")
# Long enough to span a whole gap BETWEEN bursts. Measured 2026-09-01: 16
# heartbeats over 25s, arriving in clusters roughly 20s apart. At 4.0 this
# returned False on a demonstrably live stream simply by landing in a gap —
# the same false-negative the frame check keeps producing, reintroduced by a
# window sized from the burst rate instead of the gap.
#
# Only ever paid on the path that was about to declare the stream dead.
HEARTBEAT_WAIT_SEC = 25.0


_hb_offset = None


def _heartbeat_since_last_check(path=CHIAKI_LOG):
    """Has a heartbeat been logged since the LAST time this was asked?

    Non-blocking and effectively free: it remembers how far into the log it has
    read and only looks at what is new. Called every few seconds by a polling
    caller, that covers the gaps between heartbeat bursts without ever waiting.

    Returns None when there is nothing to compare against yet (first call, or
    the log is unreadable), which the caller must treat as "no answer" rather
    than as "no".
    """
    global _hb_offset
    try:
        size = os.path.getsize(path)
    except OSError:
        _hb_offset = None
        return None
    if _hb_offset is None or size < _hb_offset:
        _hb_offset = size            # first look, or the log was rotated
        return None
    if size == _hb_offset:
        return False
    try:
        with open(path, "rb") as fh:
            fh.seek(_hb_offset)
            new = fh.read()
    except OSError:
        return None
    _hb_offset = size
    return b"Heartbeat" in new


def _heartbeat_seen(within=HEARTBEAT_WAIT_SEC, path=CHIAKI_LOG):
    """Did chiaki log a control heartbeat in the next `within` seconds?

    Reads only what is APPENDED after the call starts, so an old heartbeat from
    a session that has since died cannot answer for a live one.

    Returns False on a missing or unreadable log, which is correct here: the
    caller treats False as "no proof either way" and falls through to looking
    at the screen.
    """
    try:
        start = os.path.getsize(path)
    except OSError:
        return False
    deadline = time.time() + within
    while time.time() < deadline:
        time.sleep(0.4)
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                if b"Heartbeat" in fh.read():
                    return True
        except OSError:
            return False
    return False


# WHICH of streaming()'s four routes last answered True, or None.
#
# The routes are NOT equivalent and the difference is operationally large:
# "up via heartbeat" means the CONSOLE is answering and says nothing about
# whether the picture is visible — the PS5 home overlay covers the game while
# heartbeats continue, which is the exact state _dismiss_overlay_if_blocking
# exists for. "up via read_bearing" means the compass is on screen. Collapsing
# both into a bare True lets a reader conclude "the game is visible" from
# evidence that only says "the console is alive".
#
# Recorded here rather than printed, because streaming() is polled every few
# seconds; ensure() prints it ONCE.
_last_route = None


def last_route():
    """How the most recent streaming() call reached its answer, or None."""
    return _last_route


# --- IS THIS CHIAKI'S OWN WINDOW RATHER THAN A VIDEO STREAM? ----------------
#
# find_bar answers "is there a horizontal light band here", which is true of the
# game's compass strip AND of any application toolbar. It is the reason
# streaming() reported UP while the PS5 was in standby (OPEN-18). These two
# numbers are what separates the chiaki window's own chrome from decoded video.
#
# WHY THESE FEATURES. Qt draws flat fills: large areas of ONE exact RGB value,
# and bands that run the full width of the window. H.264 never does — even a
# dark room is dithered by quantisation, so a decoded frame has no long exact
# runs. Neither feature is about the compass, which is why they still hold on
# ban screens and gameplay, where no compass exists.
#
# MEASURED 2026-09-06 over 848 real streaming frames (demos, screenshot_log,
# explore, overnight, places; 65 of them pause screens) against the live standby
# host list plus 70 non-game images that find_bar fires on:
#
#                      streaming: p50    p99     MAX  |  the standby host list
#     flatness              0.0357  0.1131  0.2949  |  0.6678   (2.7x the gate)
#     widest exact row run  0.1208  0.3917  0.6208  |  1.0000   (2.0x the gate)
#
# So the thresholds sit BETWEEN two measured populations (CLAUDE.md 10.4), and
# the frame that actually cost an hour is clear of both by 2x or better.
UI_FLAT_FRAC = 0.25      # one exact RGB value over more than a quarter of the frame
UI_ROW_RUN_FRAC = 0.50   # one exact RGB value across more than half of some row


def looks_like_ui(img):
    """True if this frame looks like flat-shaded chrome rather than video.

    A FALSE ANSWER HERE COSTS SECONDS, NOT A RUN, and that is the whole reason
    this is safe to add. Rejecting the find_bar branch does not return False --
    it falls through to `_heartbeat_seen()`, which is the CONSOLE's own word and
    strictly better evidence than pixels. So on the 0.35% of real streaming
    frames that trip these gates (fades, and match screens with a large flat
    band) the answer is still True, a few seconds later. Whereas the standby
    host list has no session, therefore no heartbeat, and correctly comes back
    False.
    """
    try:
        import numpy as _np
        a = _np.asarray(img.convert("RGB"))
        h, w, _ = a.shape
        if h == 0 or w == 0:
            return False
        flat = a.reshape(-1, 3)
        packed = ((flat[:, 0].astype(_np.int32) << 16)
                  | (flat[:, 1].astype(_np.int32) << 8) | flat[:, 2])
        if float(_np.bincount(packed).max()) / packed.size > UI_FLAT_FRAC:
            return True
        # Sample ~120 rows rather than all of them: a full-width fill spans
        # hundreds of rows, so sampling cannot miss one, and it keeps this at a
        # few milliseconds on the path every poll takes.
        for y in range(0, h, max(1, h // 120)):
            row = a[y]
            p = ((row[:, 0].astype(_np.int32) << 16)
                 | (row[:, 1].astype(_np.int32) << 8) | row[:, 2])
            change = _np.flatnonzero(_np.diff(p)) + 1
            starts = _np.concatenate(([0], change))
            ends = _np.concatenate((change, [w]))
            if int((ends - starts).max()) / float(w) > UI_ROW_RUN_FRAC:
                return True
        return False
    except Exception:
        # NEVER let this turn into a reason to call a live stream dead. On any
        # failure, say "not UI" and leave the original behaviour in place.
        return False


# Opt-in for the tests that drive this module's ORCHESTRATION on purpose, against
# stubbed internals (test_ensure_live_clears_ui, test_frozen_stream,
# test_rig_diagnostics). OFF by default so no test can reach the real rig; a test
# that forgets gets a refusal and FAILS, which is the safe direction to be wrong in.
RIG_DRIVER_IN_TESTS = False


def _refuse_under_test(what):
    """The whole module is a RIG DRIVER. No test may run it.

    Demonstrated 2026-09-13: tests/minigame/test_budget_reserve_fits.py imports
    run_cycles, which reaches ensure() -> streaming() -> _heartbeat_seen(), which
    polls the live chiaki log for up to HEARTBEAT_WAIT_SEC. The file HUNG at the
    suite's 300 s ceiling. The ceiling is the only thing that stopped it, and the
    next rung is worse: ensure_live() shells out to ./restart_chiaki.sh, which is
    `pgrep -x chiaki` then `kill -9`. An offline test run could kill the user's
    live stream -- with a paid match on screen -- and nothing would have said why.

    _key() alone was not enough, and gating it made this MORE likely rather than
    less: with the keys suppressed the clear ladder posts nothing, is_frozen()
    stays true, and the loop falls straight through to the restart. Guarding the
    leaf without guarding the entry point pushed the failure downhill.
    """
    if os.environ.get("BASEBALL_TEST_RUN") and not RIG_DRIVER_IN_TESTS:
        print(f"  [stream] BASEBALL_TEST_RUN is set — refusing to {what}. "
              "This module drives the rig; a test must stub it, not run it.")
        return True
    return False


def streaming(img=None):
    """Is a game stream actually on screen?

    ASKS WHETHER FRAMES ARE ARRIVING, not whether they can be interpreted.
    This used to require read_bearing() to return a heading, which conflates
    two different questions: read_bearing needs to identify a compass LETTER,
    and that fails on bright scenes — measured 2026-09-01 at ~6% of world
    frames, including reliably inside the bar this route ends in.

    The cost was not subtle. A run aborted with "stream did not come up within
    150s" while the game was running perfectly and visible on screen, because
    the one frame it sampled happened to be one the letter reader could not
    parse. Twice in one day, each time ending an unattended run.

    find_bar() locates the compass STRIP rather than reading it:

        in-world, compass readable      find_bar (64, 619, 1535)   bearing 89.2
        in-world, compass unreadable    find_bar (64, 223, 1322)   bearing None
        PS5 overlay (game behind it)    find_bar (300, 47, 1429)   bearing 136.0
        chiaki host list, disconnected  find_bar None              bearing None

    THE LINE THAT USED TO FOLLOW THAT TABLE -- "It is None only in the state
    this function exists to detect" -- IS FALSE, and it is why nobody looked.
    find_bar fires on almost any structured image, the game's compass strip
    being only one of them. Measured 2026-09-06 on an independent corpus:
    9 of 13 of chiaki's OWN Qt documentation screenshots, 5 of 6 arbitrary
    photographs, and a SYNTHETIC dark window with one light horizontal toolbar
    (see tests/rig/test_find_bar_is_not_a_stream_check.py, which pins this).
    Only a flat image -- solid colour, or pure noise -- returns None.

    The user watched this cost an hour: every failed reconnect announced
    "[stream] up via find_bar (compass strip located)" first, INCLUDING while
    chiaki was not running at all and the PS5 was switched off. That is OPEN-18.

    WHY THE BRANCH IS STILL HERE. Removing it is not obviously safe. It was
    added because requiring read_bearing conflated "frames are arriving" with
    "a compass LETTER is legible", and bright scenes ended two unattended runs
    in one day on 2026-09-01. The replacement discriminator that was proposed --
    a flatness score -- is UNEVALUABLE, not merely unproven: the negative
    population is a single frame that is not on disk, so CLAUDE.md 10.4's "a
    threshold must sit between two MEASURED populations" cannot be satisfied
    from what exists. Changing the verdict on that basis would trade a known
    false positive for an unmeasured false negative, and a false negative here
    ENDS an unattended run.

    So the branch stays and the claim is corrected. One lead worth recording,
    not yet a rule: on every synthetic and UI image tried, the located strip
    spans the FULL frame width (0..W-1), while real game frames return a strip
    bounded well inside it (460..937 of 1400). Nobody has measured that on the
    host list, which is the frame that matters.
    """
    # THE CONSOLE'S OWN WORD COMES FIRST, and costs nothing. Frames have proved
    # unreliable for this question over and over: read_bearing fails on bright
    # scenes, find_bar drifts when the room lights up, and the PS5 overlay
    # changes the picture entirely — three separate ways for a healthy stream
    # to look dead. A heartbeat is the console replying, and cannot be defeated
    # by what happens to be on screen.
    #
    # Non-blocking: it only reads what the log has gained since the last call,
    # which covers the ~20s gaps between bursts for any polling caller without
    # ever waiting.
    global _last_route
    if _heartbeat_since_last_check():
        _last_route = "heartbeat (console replied; says NOTHING about the picture)"
        return True

    # Frames next — still instant, and they answer during the first call before
    # there is any heartbeat history to compare against.
    try:
        img = img or compass.fast_capture()
    except getattr(compass, "NoGameWindow", ()):
        # No window at all — chiaki is not up. That is exactly the state this
        # function exists to detect, so answer it rather than propagating.
        _last_route = "no game window"
        return False
    # Split from one `or` chain only to record WHICH check answered. The order
    # and the short-circuiting are unchanged, so this decides exactly what the
    # chain decided.
    if compass.find_bar(img) is not None and not looks_like_ui(img):
        _last_route = "find_bar (compass strip located; may be under an overlay)"
        return True
    if compass.read_bearing(img) is not None:
        _last_route = "read_bearing (compass readable; the world is visible)"
        return True
    if pm.is_pause_screen(img):
        _last_route = "pause_screen (the pause book is up, so no match is running)"
        return True

    # ONLY NOW ASK THE CONSOLE. Saying "the stream is down" ends an unattended
    # run, and the picture is the least trustworthy way to conclude it — a
    # bright room defeated read_bearing twice on 2026-09-01 and killed two runs
    # while the game was visibly running. chiaki logs "Ctrl received Heartbeat,
    # sending reply" whenever the control channel is alive: that is the console
    # itself answering, with no pixels involved.
    #
    # Heartbeats are BURSTY — measured 16 over 25s in clusters ~20s apart — so
    # this waits a few seconds for one rather than sampling an instant. It only
    # costs that wait on the path that was about to give up anyway.
    if _heartbeat_seen():
        _last_route = ("heartbeat after wait (NO usable frame — the picture "
                       "was never confirmed)")
        print("  [stream] no usable frame, but the console is still "
              "heartbeating — treating the stream as up")
        return True
    _last_route = "nothing answered"
    return False


def ensure(log=print):
    """Return True once the stream is up, reconnecting if it is not."""
    if _refuse_under_test("probe the stream"):
        return False
    if streaming():
        # ONCE, at the entry — not on the poll below, which runs every few
        # seconds. Without this the log says only "the stream is up", and a
        # reader takes that as "the game is on screen". A heartbeat route does
        # not mean that: the PS5 overlay hides the compass and the pause book
        # while the console keeps replying, and every downstream check then
        # fails for reasons that have nothing to do with the code being blamed.
        log(f"  [stream] up via {last_route()}")
        return True
    pid = _pid()
    if pid is None:
        log("  chiaki is not running — run ./restart_chiaki.sh")
        return False
    log("  stream is down; waking the console and reconnecting")
    _key(pid, 36, after=2.0)      # dismiss any dialog
    _key(pid, 125, after=0.8)     # select the host row
    _key(pid, 36, after=8.0)      # connect / wake from standby
    waited = 8.0
    dismissed = False
    while waited < MAX_WAIT:
        if streaming():
            log(f"  stream up after {waited:.0f}s")
            return True
        # Waking the console often leaves the PS5 HOME OVERLAY on top of the
        # game. The stream is running fine underneath, but the overlay hides the
        # compass strip and the pause book, so every "is it streaming" check
        # says no. Escape is mapped to the PS button in chiaki, which closes it.
        if not dismissed and waited >= 20.0:
            log("  dismissing the PS5 overlay")
            _key(pid, 53, after=3.0)
            dismissed = True
            continue
        time.sleep(CONNECT_WAIT)
        waited += CONNECT_WAIT
    log(f"  stream did not come up within {MAX_WAIT:.0f}s")
    return False


# How long two captures may be pixel-identical before the stream counts as
# FROZEN. Measured 2026-09-02: idle in-world noise is 14-20, a static menu ~3,
# and a genuinely frozen stream is exactly 0.00.
FROZEN_DELTA = 0.35


def is_frozen(gap=1.2):
    """True if the picture has stopped updating entirely.

    Distinct from "not streaming": chiaki keeps heartbeating and reports a live
    session while its decoder has stalled, so streaming() says yes and every
    frame is identical. Measured twice on 2026-09-02, with chiaki logging
    "pending_overflow_evict ... overflow queue full" both times.

    This matters because a frozen picture SATISFIES most checks in this project:
    nothing moves, so nothing looks blocked; nothing changes, so a reset probe
    measures delta 0.0 and reports "NO input is reaching the game" — which sent
    two investigations at the input path while input was fine.
    """
    if _refuse_under_test("compare live frames"):
        return False
    import numpy as np
    import compass

    try:
        a = np.asarray(compass.fast_capture().convert("L"), dtype=float)
        time.sleep(gap)
        b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    except Exception as e:
        # Includes NoGameWindow: with no window there is nothing to call frozen,
        # and streaming() already reports that state.
        #
        # BUT SAY SO. False here does not mean "the picture is updating", it
        # means "nothing was seen" — and ensure_live() cannot tell the two
        # apart, because it reads
        #     if ensure(log=log) and not is_frozen(): return True
        # and streaming() can satisfy ensure() from a HEARTBEAT ALONE, without
        # ever capturing. So a broken capture plus a live console returned
        # "live, updating picture" with nothing whatsoever in the log.
        #
        # That is CANNOT SEE recorded as FINE, which is the failure that cost a
        # whole A/B when the harness scored a dead stream as "did not arrive".
        print(f"  [stream] is_frozen() could not capture "
              f"({type(e).__name__}: {e}) — answering NOT FROZEN. That is the "
              "absence of evidence, NOT evidence the picture is updating; "
              "ensure_live() will read it as a healthy stream.")
        return False
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) <= FROZEN_DELTA


def ensure_live(log=print, restarts=2):
    """Return True with a picture that is actually UPDATING, restarting if not.

    ensure() alone is not enough for an unattended run: it is satisfied by a
    heartbeat, and a heartbeat continues through a decoder stall. A five-run
    measurement was lost on 2026-09-02 because every reset in it probed a still
    picture and concluded the input was dead.
    """
    if _refuse_under_test("probe or RESTART the stream"):
        return False
    import subprocess

    for attempt in range(restarts + 1):
        if ensure(log=log) and not is_frozen():
            _dismiss_overlay_if_blocking(log=log)
            return True

        # A FROZEN PICTURE IS USUALLY SOMETHING SITTING ON TOP OF THE STREAM,
        # not a dead stream — and restarting cannot fix any of them:
        #
        #   - chiaki's own modal dialog ("Vulkan renderer is unavailable",
        #     shown on EVERY launch here), which a restart brings straight back
        #   - a macOS crash-report window over the chiaki window
        #   - the PS5 home overlay or the in-game pause book
        #   - chiaki sitting on its host list, never connected
        #
        # This loop used to go straight to a restart, so on 2026-09-03 it
        # printed "the picture is not updating" twice and gave up while the
        # console was awake, the session was heartbeating, and the only problem
        # was a dialog. _dismiss_overlay_if_blocking was already written for
        # this but was only reached on the SUCCESS path, i.e. when it was not
        # needed. Clearing costs about five seconds; a restart costs twenty and
        # re-creates the dialog.
        if _clear_blocking_ui(log=log):
            if ensure(log=log) and not is_frozen():
                log("  cleared something on top of the stream; picture is live")
                return True

        if attempt == restarts:
            break
        log(f"  the picture is not updating — restarting chiaki "
            f"({attempt + 1}/{restarts})")
        try:
            subprocess.run(["./restart_chiaki.sh"], capture_output=True,
                           timeout=120)
        except Exception as e:
            log(f"  restart failed: {type(e).__name__}: {e}")
            return False
        time.sleep(20.0)
    log("  could not get a live, updating picture")
    return False


def _front_chiaki():
    """Bring chiaki forward.

    _key() posts straight to the pid, which is enough for the game but NOT for
    a modal Qt dialog — those were only dismissed once the process was actually
    frontmost. Failing here is not fatal; the key press is still attempted.
    """
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to tell process "chiaki" '
         'to set frontmost to true'],
        capture_output=True, timeout=10)


def _dismiss_mac_crash_dialog(log=print):
    """Close a macOS "Problem Report" window if one is covering chiaki.

    Dismissed BY NAME rather than by coordinates: the chiaki window measured
    2540x1030 while the capture came back 1867x1050, so capture fractions do
    not map onto screen positions.
    """
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to tell process "Problem Reporter" '
             'to click button "OK" of window 1'],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            log("  dismissed a macOS crash dialog covering chiaki")
            return True
    except Exception:
        pass
    return False


def _clear_blocking_ui(log=print):
    """Clear anything sitting on top of the stream. True if worth re-checking.

    Order matters: the crash dialog is above chiaki, chiaki's own dialog is
    above its window, and only then can Return reach the host list.
    """
    pid = _pid()
    if pid is None:
        return False
    _dismiss_mac_crash_dialog(log=log)
    try:
        _front_chiaki()
    except Exception:
        pass
    # Return: dismisses chiaki's modal dialog, and on the host list it is also
    # what CONNECTS — which nothing on this path did before, so a chiaki left
    # on its host list could never come up no matter how often it restarted.
    # Escape: the PS button, which closes the PS5 overlay.
    log("  clearing dialogs / overlays before restarting")
    _key(pid, 36, after=2.5)
    _key(pid, 53, after=2.5)
    _key(pid, 36, after=6.0)
    return True


def _dismiss_overlay_if_blocking(log=print):
    """Close the PS5 home overlay if it is sitting on top of the game.

    ensure() only dismisses it on the path where streaming() said NO. Waking the
    console leaves the overlay up while the CONSOLE heartbeats, so streaming()
    returns True from the heartbeat, ensure() returns early, and the overlay
    stays — hiding the compass and the pause book from everything downstream.
    Observed repeatedly on 2026-09-02.

    Escape is mapped to the PS button in chiaki, which closes it.
    """
    import compass
    import pause_menu as pm

    try:
        img = compass.fast_capture()
        if compass.read_bearing(img) is not None or pm.is_pause_screen(img):
            return False          # the game is visible; nothing to dismiss
        pid = _pid()
        if pid is None:
            return False
        log("  compass unreadable and no pause menu — dismissing the PS5 overlay")
        _key(pid, 53, after=3.0)
        return True
    except Exception:
        return False
