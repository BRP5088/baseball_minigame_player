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
    # has always promised. Every OTHER failure keeps the fallback, because a
    # broken compass import or a dead mss is the case it was written for and
    # nothing about it says the display is the wrong one.
    missing_window = False
    try:
        import compass
        img = compass.fast_capture()
    except Exception as exc:
        # By NAME, not by isinstance: compass itself may be what failed to
        # import, and then there is no class here to compare against.
        missing_window = type(exc).__name__ == "NoGameWindow"
        img = None
    if img is None and missing_window:
        return None
    if img is None:
        # Last resort. This is the WRONG display on a multi-monitor setup, so it
        # is a degraded fallback rather than an equivalent path — better than
        # crashing the loop, but anything relying on exact crops will be wrong.
        try:
            import pyautogui
            img = pyautogui.screenshot()
        except Exception:
            return None
    img = img.convert("RGB")
    if width and img.width != width:
        ratio = width / img.width
        img = img.resize((width, int(img.height * ratio)))
    return img
