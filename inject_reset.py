"""Reset the game using CONTROLLER INJECTION rather than the keyboard.

The locally-built chiaki does not carry the keyboard mappings the installed app
had, so keypresses reach nothing. Injection drives the real controller fields
and works regardless.

Buttons are chiaki's own bitmask (lib/include/chiaki/controller.h). BOX (4) is
NEVER sent: it spends $50 at the Baseball Cards prompt.
"""
import os
import time

CROSS, DPAD_DOWN, OPTIONS = 1, 1 << 7, 1 << 12
BOX = 1 << 2                       # never send this
# The DEFAULT only. Read through _fifo() at CALL time, never captured here:
# CHIAKI_INJECT_INPUT is the one lever every test in the suite uses to point the
# pipe somewhere harmless (test_injected_input, test_buttons_use_keyboard,
# test_chain_record all set it), and this module ignored it -- so a test that
# isolated the FIFO correctly still had THIS writer aimed at the live one.
FIFO = "/tmp/chiaki_input"


def _fifo():
    return os.environ.get("CHIAKI_INJECT_INPUT") or FIFO


def _locked_out(what):
    """HARD OFF under BASEBALL_TEST_RUN. This is the fourth path to the console.

    input_controller guards the keyboard, analog_replay guards the sticks,
    ensure_stream guards the recovery keys -- and this module wrote raw button
    masks to the pipe with no check of any kind. reset() is OPTIONS x5 ->
    DPAD_DOWN x4 -> CROSS x6; on a match parked mid-play OPTIONS opens "Give up?"
    and CROSS answers YES (CLAUDE.md section 4), so an offline run of anything
    importing this could forfeit a paid match.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        print(f"  [inject] BASEBALL_TEST_RUN is set — refusing to {what}. "
              "If this is a live run, nothing will move until you unset it.")
        return True
    return False


def tap(mask, hold=0.12, after=0.5):
    assert not (mask & BOX), "refusing to send BOX — that spends $50"
    if _locked_out(f"tap buttons {mask}"):
        return
    with open(_fifo(), "w", buffering=1) as f:
        f.write(f"buttons {mask}\n"); f.flush(); time.sleep(hold)
        f.write("buttons 0\n"); f.flush()
    time.sleep(after)


def clear():
    if _locked_out("clear the sticks"):
        return
    with open(_fifo(), "w", buffering=1) as f:
        f.write("clear\n"); f.flush()


def reset(log=print):
    """Options -> Load Last Save -> confirm. Returns the spawn bearing.

    Focuses chiaki first when BASEBALL_ALLOW_FOCUS=1. Injected BUTTONS are not
    acted on reliably while chiaki is in the background — sticks still work,
    which makes the failure look like a dead OPTIONS button rather than a focus
    problem. That cost an unattended run on 2026-08-28.
    """
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    if os.environ.get("BASEBALL_ALLOW_FOCUS") == "1":
        import focus_game
        focus_game.focus(log=lambda m: None)
    import compass
    import pause_menu as pm

    # RETRY rather than abort. A single OPTIONS press does not always register
    # — the game swallows it during a transition, or the press lands while the
    # character is still settling — and an unattended run that gives up on the
    # first miss stops the whole night's work over a dropped button.
    for attempt in range(5):
        tap(OPTIONS, after=1.8)
        img = compass.fast_capture()
        if pm.is_pause_screen(img):
            log(f"  pause open, selected {pm.selected_item(img)!r}")
            break
        log(f"  OPTIONS press {attempt + 1} did not open the pause menu; retrying")
        time.sleep(1.0)
    else:
        clear()
        raise RuntimeError("pause menu did not open after 5 OPTIONS presses")

    for _ in range(4):
        sel = pm.selected_item(compass.fast_capture())
        if sel == "Load Last Save":
            break
        tap(DPAD_DOWN, after=0.6)
    else:
        clear()
        raise RuntimeError("never landed on Load Last Save")
    log("  selected Load Last Save")

    # CROSS both opens the confirm dialog and answers YES on it, but how many
    # presses that takes is not fixed — a press lands or does not depending on
    # where the dialog is in its fade-in. A hardcoded two presses left the
    # dialog sitting open and the reset reported "world never came back".
    #
    # So press, then WATCH: the world returning is the only success signal, and
    # a still-black screen just means press again.
    for attempt in range(6):
        tap(CROSS, after=1.1)
        b = _settled_bearing(compass, log)
        if b is not None:
            clear()
            log(f"  world back after {attempt + 1} press(es), spawn {b:.1f}")
            return b
        log(f"  no world yet after press {attempt + 1}; pressing again")
    clear()
    raise RuntimeError("world never came back after 6 confirm presses")


# The office spawn, measured repeatedly: the character faces the typewriter.
SPAWN_BEARING = 86.9
SPAWN_TOLERANCE = 6.0


def _settled_bearing(compass, log, tries=20):
    """Wait for the world to come back AND the camera to stop moving.

    Returning on the first compass reading that is not None is not enough. The
    world fades in while the camera is still settling, so that first reading can
    be wildly wrong — one reset reported a spawn of 241 degrees when the actual
    spawn is 87, and the run that followed started from a false premise and was
    doomed before its first step. Two readings that agree mean the camera has
    actually come to rest.
    """
    prev = None
    for _ in range(tries):
        b = compass.read_bearing(compass.fast_capture())
        if b is not None and prev is not None:
            if abs((b - prev + 540) % 360 - 180) < 1.5:
                off = abs((b - SPAWN_BEARING + 540) % 360 - 180)
                if off > SPAWN_TOLERANCE:
                    log(f"  spawn reads {b:.1f}, expected ~{SPAWN_BEARING} "
                        f"(off {off:.1f}) — not the office; treating as a bad load")
                    return None
                return b
        prev = b
        time.sleep(0.35)
    return None


if __name__ == "__main__":
    reset()
