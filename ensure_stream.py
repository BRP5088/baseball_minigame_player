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
    out = subprocess.run(["pgrep", "-f", "chiaki-ng-build"],
                         capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def _key(pid, code, after=1.2):
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

    find_bar() locates the compass STRIP rather than reading it, and separates
    the states cleanly:

        in-world, compass readable      find_bar (64, 619, 1535)   bearing 89.2
        in-world, compass unreadable    find_bar (64, 223, 1322)   bearing None
        PS5 overlay (game behind it)    find_bar (300, 47, 1429)   bearing 136.0
        chiaki host list, disconnected  find_bar None              bearing None

    It is None only in the state this function exists to detect.
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
    if compass.find_bar(img) is not None:
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
