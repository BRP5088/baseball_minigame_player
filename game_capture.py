"""THE one place that decides what "a screenshot of the game" means.

WHY THIS MODULE EXISTS
----------------------
It did not, and the same bug appeared in three places independently:
`orchestrator._fast_grab`, `orchestrator.capture_screenshot_image` and
`orchestrator._screenshot_logger_loop` each grabbed the whole primary display.
On a two-monitor setup with the game on the external one, "the primary display"
is the laptop — so every fractional crop read the desktop, the vision model was
sent pictures of the code editor and replied "other" until the run stalled, and
the 1Hz diagnostic logger wrote 247 frames of the user's actual work to disk.

Fixing them one at a time is how the fourth one gets missed. Everything that
needs game pixels calls grab() here, so changing what a capture means is a
one-line change in one file.
"""


def grab(width=None):
    """The game's pixels as an RGB PIL Image, or None if unavailable.

    `width` resizes to a fixed width for callers whose thresholds were
    calibrated at a particular resolution — mean-absolute-delta comparisons are
    scale-sensitive, so feeding a different size silently shifts them.
    """
    img = None
    # WHY THE EXCEPTION'S IDENTITY MATTERS HERE, when it never used to.
    #
    # NoGameWindow means one specific thing: we know where the game window is
    # supposed to be and it is not visible -- which, since the frame dump
    # landed, is the NORMAL state whenever the user is on another macOS Space.
    # That is the whole point of the dump, and it turns this function's last
    # resort into a trap: pyautogui.screenshot() grabs the PRIMARY DISPLAY, so
    # in exactly that state it returns a picture of the user's own desktop and
    # hands it back as "the game's pixels". This module's own docstring is
    # about that incident -- the 1Hz logger wrote 247 frames of the user's
    # actual work to disk and the vision model answered "other" until the run
    # stalled -- and two callers reach here with no focus recovery first:
    # orchestrator._fast_grab (which read_balance_from_pause_menu uses to
    # verify the pause menu opened, on the $50 money path) and
    # _screenshot_logger_loop (which does not focus, by its own comment).
    #
    # So a missing window returns None, which is what this function's docstring
    # has always promised. Every OTHER failure returns None too (see the except
    # block below) -- there is no fallback left at all. This comment used to say
    # "every OTHER failure keeps the fallback", which stopped being true the
    # moment the pyautogui.screenshot() fallback below was removed; it just
    # never got corrected (r3, skeptic finding 5).
    try:
        import compass
        img = compass.fast_capture()
    except Exception:
        # ANY capture failure means "no frame this poll" -- never a desktop
        # screenshot. NoGameWindow used to be special-cased to return None
        # while every other exception fell through to pyautogui.screenshot(),
        # which grabs the PRIMARY DISPLAY (the user's own laptop desktop on
        # this two-monitor rig). That fallback fired live
        # (overnight/run_live_20260922b.log:780). There is no failure mode
        # for which the wrong display is an acceptable answer, so every
        # exception now returns None, full stop.
        return None
    if img is None:
        return None
    img = img.convert("RGB")
    if width and img.width != width:
        ratio = width / img.width
        img = img.resize((width, int(img.height * ratio)))
    return img
