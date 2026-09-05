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
    try:
        import compass
        img = compass.fast_capture()
    except Exception:
        img = None
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
