"""Read which entry of the in-game PAUSE menu is currently selected.

WHY
---
The reset sequence commits an irreversible-ish action (reloading the save)
with a blind `cross` press. Knowing the cursor STARTED on "Resume" is not the
same as knowing it is on "Load Last Save" when we press — the cursor does not
reset between visits to this menu any more than the hand cursor does, and a
dropped D-pad press would leave it one row off.

One row off is "Load" (a save picker — harmless but wrong). Two is "Quit to
Main Menu", which drops out of the game entirely and ends the session. Neither
destroys anything, but both silently break an unattended run, and the whole
point of automating the reset is that nobody is watching.

HOW
---
The selected entry renders in PURE WHITE; the others are a mid grey against
the light page. Mean brightness does NOT separate them (the page itself is
bright) — the fraction of near-white pixels does, by two orders of magnitude.

MEASURED on screenshot_log/reset_pause_190605.jpg (2000x1292):

    Resume (selected)     19.7% of pixels > 200      max 255
    Load Last Save         0.0%                      max 194
    Load                   0.0%                      max 198
    Quit to Main Menu      0.2%                      max 203

A threshold of 5% sits an order of magnitude clear of both classes.

WHY THE PAGE IS CHECKED TOO
---------------------------
Brightness inside the menu column is not enough, and the four bands alone are
not enough either. The 14 frames logged during the 2026-08-26 live reset
(screenshot_log/reset_load_*.jpg) are, apart from reset_load_00, the world
BACK -- standing at the typewriter, confirmed by input_controller.in_gameplay()
and by compass.read_bearing() returning a bearing on every one of them. The
typewriter's white roller sweeps through the menu column as the camera settles,
so "3 of the 4 bands brighter than 100" held on 11 of those 13 gameplay frames,
and on three of them selected_item() went on to answer 'Load Last Save' -- on a
screen with no menu at all. reset_environment() would have taken that as proof
the cursor was already parked and pressed `cross` into the live world.

The menu is printed on a PAGE: a book that covers most of the screen while
paused. Requiring the page is what separates a menu entry from a bright object
in the 3D scene that happens to land in the same box. Measured over every
reset_*.jpg in the log -- fraction of PAGE_BOX_FRAC brighter than PAGE_LEVEL:

    4 real pause frames        0.926 - 0.929
    24 real non-pause frames   0.005 - 0.238  (max is a post-load gameplay frame)

PAGE_MIN_FRAC sits at 0.60, roughly midway across that gap. The check is an
AND on top of the band test, so it can only ever reject frames the old rule
accepted -- it cannot invent a new way to say "yes".
"""

import numpy as np

# Capture-coordinate geometry of the menu column. Calibrated against a real
# capture_screenshot_image() frame — a chiaki-window screenshot has different
# geometry and these boxes would land on the wrong pixels.
MENU_X_FRAC = (0.24, 0.42)
MENU_BAND_HALF_HEIGHT = 0.014

# Entry order, top to bottom, with the y centre of each. The ORDER is what the
# reset navigation depends on: Load Last Save is exactly one Down from Resume.
# Two calibrations, because the capture changed shape on 2026-08-27.
#
# The project used to capture the whole DESKTOP with the game as a window in
# it; it now captures the game alone (16:9, letterbox removed). Menu rows sit
# at different fractions of those two frames, and the old fixtures the tests
# depend on are all the desktop kind — so both sets have to stay.
#
# Measured on a real 1920x1080 pause frame: rows at y 405, 470, 536, 601.
MENU_ITEMS_DESKTOP = [
    ("Resume", 0.4226),
    ("Load Last Save", 0.4729),
    ("Load", 0.5240),
    ("Quit to Main Menu", 0.5751),
]
MENU_ITEMS_GAME = [
    ("Resume", 0.3750),
    ("Load Last Save", 0.4352),
    ("Load", 0.4963),
    ("Quit to Main Menu", 0.5565),
]
MENU_ITEMS = MENU_ITEMS_DESKTOP          # order is what reset navigation uses

STREAM_ASPECT = 16 / 9


def menu_items(img):
    """The row calibration matching this frame's shape."""
    w, h = img.size
    if abs(w / h - STREAM_ASPECT) < 0.01:
        return MENU_ITEMS_GAME
    return MENU_ITEMS_DESKTOP

# MEASURED 2026-09-03 on a live pause menu with "Load Last Save" highlighted.
# Peak brightness per row:
#
#     Resume             202      Load               201
#     Load Last Save     255      Quit to Main Menu  210   <- all UNSELECTED
#
# The selected entry is drawn in PURE WHITE; every other entry peaks at
# 201-210. WHITE_LEVEL was 200 — BELOW the unselected text's own brightness —
# so grey letters counted, and the score became a measure of how much TEXT a
# row has rather than whether it is highlighted. A long unselected entry then
# outscored a short selected one:
#
#     level >200:  Resume 0.0003  LoadLast 0.0771  Load 0.0006  Quit 0.1075
#     level >225:  Resume 0.0000  LoadLast 0.0586  Load 0.0000  Quit 0.0000
#
# At 200 it returned "Quit to Main Menu" for a frame where "Load Last Save" was
# selected — a CONFIDENT WRONG answer on the one reading that decides whether to
# press cross. An unattended run would have quit the game to the main menu.
#
# 225 sits between two measured populations (210 and 255) instead of under one
# of them. Same mistake, third time on this project: a threshold has to clear
# the noise floor of the thing it is discriminating against.
WHITE_LEVEL = 225

# At WHITE_LEVEL 225 the selected row scores ~0.059 and every unselected row
# scores exactly 0.0000, so anything in between separates them. 0.02 keeps a
# ~3x margin under the selected class and is far above the unselected class.
#
# The old 0.10 existed because a GAMEPLAY frame put white quest text in the top
# band at 0.059 — but selected_item() now gates on is_pause_screen() first, so
# that frame never reaches this test.
SELECTED_MIN_FRAC = 0.02

# Footprint of the open book, as a fraction of the frame: (left, top, right,
# bottom). Deliberately inside the page's edges so the drop shadow and the
# tab icons along its top do not count against it.
PAGE_BOX_FRAC = (0.16, 0.30, 0.84, 0.84)
PAGE_LEVEL = 120
PAGE_MIN_FRAC = 0.80


def _band(img, y_centre):
    w, h = img.size
    return np.asarray(
        img.convert("L").crop((int(w * MENU_X_FRAC[0]),
                               int(h * (y_centre - MENU_BAND_HALF_HEIGHT)),
                               int(w * MENU_X_FRAC[1]),
                               int(h * (y_centre + MENU_BAND_HALF_HEIGHT)))),
        dtype=float)


def white_fractions(img):
    """Fraction of near-white pixels per menu entry, in menu order."""
    return [float((_band(img, y) > WHITE_LEVEL).mean())
            for _, y in menu_items(img)]


def page_fraction(img):
    """Fraction of the pause book's footprint that is paper-bright."""
    w, h = img.size
    box = np.asarray(
        img.convert("L").crop((int(w * PAGE_BOX_FRAC[0]),
                               int(h * PAGE_BOX_FRAC[1]),
                               int(w * PAGE_BOX_FRAC[2]),
                               int(h * PAGE_BOX_FRAC[3]))),
        dtype=float)
    return float((box > PAGE_LEVEL).mean())


# The pause book is bright AND has DARK MENU TEXT on it. Brightness alone is
# not enough: measured 2026-09-03 on a gameplay frame where the character faced
# a blown-out white wall,
#
#     gameplay bright wall   page 0.927   dark text 0.0000
#     real pause menu        page 0.944   dark text 0.0465
#
# page_fraction cannot separate those (0.927 vs 0.944), so is_pause_screen
# returned TRUE on open world. That is not cosmetic: reset_environment waits for
# this, then tries to read the selection, gets nothing, and aborts with
# "cannot tell which menu entry is selected". It is the root cause of the five
# consecutive ResetErrors that invalidated half of the 2026-09-03 streak run.
#
# Requiring dark text separates them completely — 0.0000 against 0.0465.
# The "PAUSE" TITLE band, not the menu entries. Two reasons:
#   1. It separates better — wall 0.0055 vs book 0.1054, about 19x.
#   2. The entries get REPAINTED by tests that synthesise selection states, so
#      measuring ink there made those frames stop reading as pause screens and
#      broke three assertions that were testing something else entirely.
# The title is always present on a real pause book and nothing repaints it.
MENU_TEXT_BAND = (0.14, 0.30)
MENU_TEXT_LEVEL = 120           # darker than this is ink, not paper
MENU_TEXT_MIN_FRAC = 0.03       # between the measured classes (0.0055 / 0.1054)


def menu_text_fraction(img):
    """How much of the book's TITLE band is dark ink. Paper alone scores ~0."""
    w, h = img.size
    box = np.asarray(
        img.convert("L").crop((int(w * MENU_X_FRAC[0]),
                               int(h * MENU_TEXT_BAND[0]),
                               int(w * MENU_X_FRAC[1]),
                               int(h * MENU_TEXT_BAND[1]))), dtype=float)
    return float((box < MENU_TEXT_LEVEL).mean())


def is_pause_screen(img):
    """True if this looks like the PAUSE menu at all.

    THREE conditions, because two were not enough. A bright wall in normal
    gameplay passed both the band test and a 0.60 page threshold — measured
    page fraction 0.658 against 0.926-0.927 for real pause screens — and the
    reset then believed it was in a menu, refused to press blindly (correctly),
    and aborted. The character was standing in front of a lit wall the whole
    time.

    So the page must be nearly SATURATED: 0.80 sits squarely in the gap
    between the wall's 0.658 and a real menu's 0.926.

    A tempting extra rule — "a real menu lights exactly one row, the wall lit
    all four" — is deliberately NOT used. It would make this function reject a
    menu with two rows apparently selected, and that ambiguous case is
    precisely what selected_item() must still see so it can abstain. Folding
    the ambiguity check in here would turn "I cannot tell which row" into "this
    is not a menu", which is a different and much less safe answer.
    """
    means = [float(_band(img, y).mean()) for _, y in menu_items(img)]
    if sum(m > 100 for m in means) < 3:
        return False
    return (page_fraction(img) >= PAGE_MIN_FRAC
            and menu_text_fraction(img) >= MENU_TEXT_MIN_FRAC)


# How far ahead the winner must be before selected_item will name it. The
# failing case scored 0.1075 against a runner-up of 0.0771 — a ratio of 1.39 —
# so 2.0 rejects it while leaving a genuine highlight (which is far brighter
# than every other row) comfortably clear.
SELECTED_MARGIN = 2.0


def selected_item(img):
    """Name of the highlighted entry, or None if it cannot be determined.

    Returns None when zero or several entries look selected. Abstaining is the
    point: the caller uses this to decide whether to commit a `cross`, and a
    confident wrong answer there is what sends an unattended run to the main
    menu.
    """
    if not is_pause_screen(img):
        return None
    fracs = white_fractions(img)
    hits = [i for i, f in enumerate(fracs) if f >= SELECTED_MIN_FRAC]
    if len(hits) != 1:
        return None

    # AN ABSOLUTE THRESHOLD ON A *FRACTION* CANNOT SEPARATE THESE ROWS.
    # Measured 2026-09-03 on a menu where "Load Last Save" was visibly
    # highlighted (larger, pure white):
    #
    #     Resume             0.0003
    #     Load Last Save     0.0771   <- actually selected, BELOW the 0.1 bar
    #     Load               0.0006
    #     Quit to Main Menu  0.1075   <- returned, ABOVE the bar
    #
    # The score rises with how much TEXT a row has, so a long unselected entry
    # outscores a short selected one. Exactly one row cleared the bar, so this
    # returned "Quit to Main Menu" CONFIDENTLY — and the caller commits a cross
    # on that. An unattended run would have quit to the main menu.
    #
    # Until the signal is replaced with one that measures the highlight rather
    # than the letter count (the selected entry is rendered LARGER and pure
    # white, so peak brightness or glyph height would work), refuse to answer
    # unless the winner is UNAMBIGUOUS. Abstaining costs a failed reset that
    # says so; a confident wrong answer costs the session.
    best = hits[0]
    rest = [f for i, f in enumerate(fracs) if i != best]
    if rest and max(rest) > 0.0 and fracs[best] < SELECTED_MARGIN * max(rest):
        return None
    return menu_items(img)[best][0]


# ---------------------------------------------------------------- THE MONEY, READ LOCALLY
# THE ONLY BALANCE READER ON THIS PROJECT WAS A PAID CALL, and the paid model is off -- so
# the tracked balance had no way to be checked against the game at all. It is the money
# guard; a guard nothing can verify is the shape this project keeps finding.
#
# WHERE THE NUMBER IS. Three counters stack along the RIGHT edge of the pause book and the
# TOPMOST is money (CLAUDE.md section 3, which also records that the big coin in the world
# HUD is HEALTH and has been misread as money three times). Measured on the pause fixture,
# the digits of "246" span x 0.9036-0.9336, y 0.2181-0.2381, with the other two counters at
# y 0.293 and y 0.370 -- so the stack is real and the top one is the one wanted.
#
# The box extends LEFT of the measured digits because the text is RIGHT-ALIGNED: 246 and 96
# and 1246 all end at the same x and start at different ones.
# MEASURED ON BOTH CAPTURE GEOMETRIES, because the first version was measured on one and
# missed on the other -- clipping the last digit at x 0.947 and the tops of the digits at
# y 0.205. Both frames are 16:9 and the counter still sits in a slightly different place:
#
#     1867x1050 (fixture)   digits x 0.9036-0.9336   y 0.2181-0.2381
#     2000x1125 (live)      digits x 0.9185-0.9475   y 0.1929-0.2130
#
# CLAUDE.md section 3 says exactly this: one session produced two capture sizes and anything
# reading a fixed region must be checked against BOTH. The box below is the union with
# margin, and it extends LEFT because the text is RIGHT-ALIGNED -- 96, 246 and 1246 all end
# at the same x and begin at different ones.
MONEY_BOX_FRAC = (0.852, 0.176, 0.962, 0.252)
from PIL import Image  # for the money crop's resample filter
MONEY_MIN, MONEY_MAX = 0, 9999


def read_money(img, ocr=None):
    """The money total off an OPEN pause menu, locally. None when it cannot be read.

    REFUSES UNLESS THE PAUSE MENU IS CONFIRMED FIRST, and that is not defensive padding:
    toggle_pause is a TOGGLE that does not always land, and when it did not the capture was
    the WORLD -- where the only number on screen is the HEALTH coin. That misread reported
    the bankroll collapsing from $246 to $100 (CLAUDE.md section 3).
    """
    if not is_pause_screen(img):
        return None
    # PSM 6 AND TWO SCALES, AND THEY MUST AGREE. Swept over both capture geometries:
    #
    #     psm 7   reads the fixture (246) and NOT the live frame
    #     psm 6   reads BOTH, at either scale
    #     psm 8 / 13   return "1966" for 196 -- a spurious digit, on the money field
    #
    # The first version used psm 7 and a single read, and on the live frame it returned
    # 106 for 196: a confidently WRONG balance, which on the money guard is worse than no
    # answer at all. Two scales that agree is the same rule local_hand_cards uses, and it
    # costs one extra OCR on a screen that is open for seconds.
    import ocr_glyphs
    _ocr = ocr or (lambda im, psm=6: ocr_glyphs.image_to_text(
        im, psm=psm, whitelist="0123456789"))
    w, h = img.size
    x0, y0, x1, y1 = MONEY_BOX_FRAC
    base = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    seen = []
    for up in (4, 6):
        c = base.resize((base.width * up, base.height * up), Image.LANCZOS)
        txt = _ocr(c) or ""
        digits = "".join(ch for ch in txt if ch.isdigit())
        seen.append(int(digits) if digits else None)
    if seen[0] is not None and seen[0] == seen[1] and MONEY_MIN <= seen[0] <= MONEY_MAX:
        return seen[0]
    return None
