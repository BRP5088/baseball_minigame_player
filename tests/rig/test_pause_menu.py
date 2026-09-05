"""pause_menu.py against REAL logged frames. Offline, no capture, no input.

WHY THIS EXISTS
---------------
pause_menu.py exists for exactly one reason, stated in its own docstring: the
reset sequence presses `cross` on this menu, and one row below "Load Last Save"
is "Load" (a save picker), two is "Quit to Main Menu" (ends the session). So a
CONFIDENT WRONG answer here is worse than no answer at all, and the module's
contract is that it abstains — returns None — whenever it cannot be sure.

Writing this test found that it did not abstain. `is_pause_screen()` asked for
"3 of the 4 menu bands brighter than 100", and the 14 logged frames from the
2026-08-26 live reset (screenshot_log/reset_load_*.jpg) are NOT loading screens
as their name suggests — only reset_load_00 is. Frames 01-13 are the world
BACK, standing at the typewriter, which is confirmed independently two ways:
input_controller.in_gameplay() says True for all 13 and compass.read_bearing()
returns a real bearing (~86 deg) on each, and a compass only renders in
gameplay. On that screen the typewriter's big white roller sweeps across the
menu column as the camera settles, so:

    reset_load_02..11, 13    is_pause_screen()  -> True   (no menu on screen)
    reset_load_05, 06, 08    selected_item()    -> 'Load Last Save'

That last line is the whole failure. reset_environment() opens with
`for _ in range(3): if pm.is_pause_screen(cap()): break` — so on such a frame
it breaks out WITHOUT ever pressing the pause key, then step 2 reads back
"Load Last Save", agrees the cursor is where it wants it, and commits `cross`
into the live world. Every verification gate in the reset passes on a screen
that has no menu at all. That is the same shape of bug the module's own
docstring records ("a 0.05 threshold reported 'Resume is selected' on a screen
with no menu"), one layer up: no per-band threshold can tell a menu entry from
an unrelated bright object in the same box, so the PAGE the menu is printed on
has to be required too. See the note on PAGE_MIN_FRAC in pause_menu.py.

WHAT IS PINNED HERE
-------------------
  * the four real pause frames read back the entry a human sees highlighted;
  * every other real reset-context frame (gameplay, loading, the confirmation
    dialog) is rejected by is_pause_screen AND abstained on by selected_item;
  * zero-selected and two-selected menus abstain -- and abstain for the RIGHT
    reason, i.e. is_pause_screen still says True on those fixtures, so the
    None is the hit-count rule firing and not the page gate masking it;
  * the selected/unselected white fractions the module measured (0.20 vs the
    0.059 that gameplay quest text scored) still land on opposite sides of the
    threshold, so SELECTED_MIN_FRAC cannot drift into either class;
  * MENU_ITEMS order -- "Load Last Save" is exactly one Down from "Resume" is
    what the reset's navigation arithmetic rests on.

Fixtures for the degenerate menus are REAL pause frames with the four menu
bands repainted, not synthetic images: the page, the book, the right-hand quest
list and everything else that is_pause_screen looks at stays real.
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


import glob
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

from PIL import Image

import pause_menu as pm

LOG = "screenshot_log"
fails = []

# Ground truth, read off each frame by eye. Every other reset_*.jpg in the log
# is a negative -- taken as the complement below rather than listed, so a frame
# nobody labelled cannot quietly escape the negative set.
PAUSE_TRUTH = {
    "reset_pause_190605.jpg": "Resume",
    "reset_pausetry_192715.jpg": "Resume",
    "reset_down_191027.jpg": "Load Last Save",
    "reset_pre_191157.jpg": "Load Last Save",
}

all_reset = sorted(os.path.basename(p) for p in glob.glob(f"{LOG}/reset_*.jpg"))
missing = [n for n in PAUSE_TRUTH if n not in all_reset]
if missing:
    fails.append(f"labelled pause frames are gone from {LOG}/: {missing} — this "
                 f"test cannot validate anything without them")
negatives = [n for n in all_reset if n not in PAUSE_TRUTH]
if len(negatives) < 15:
    fails.append(f"only {len(negatives)} negative frames found (expected ~24) — "
                 f"the reference corpus has shrunk and the false-positive case "
                 f"this test exists for may no longer be covered")


def load(name):
    return Image.open(f"{LOG}/{name}").convert("RGB")


# --- 1. real pause frames: the right entry, every time ---------------------
for name, want in sorted(PAUSE_TRUTH.items()):
    if name not in all_reset:
        continue
    img = load(name)
    if not pm.is_pause_screen(img):
        fails.append(f"{name} IS the pause menu but is_pause_screen said False "
                     f"— the reset would give up and never reload the save")
    got = pm.selected_item(img)
    if got != want:
        fails.append(f"{name}: selected_item said {got!r}, a human reads {want!r}"
                     + (" — pressing cross here lands on the wrong row"
                        if got is not None else ""))

# --- 2. every other real frame: rejected, and abstained on -----------------
# This is the case that was broken. A wrong answer here is the dangerous one,
# so it is checked separately from is_pause_screen: even if the gate regressed,
# selected_item must not hand back a name.
wrong_names = []
for name in negatives:
    img = load(name)
    if pm.is_pause_screen(img):
        fails.append(f"{name} is NOT the pause menu but is_pause_screen said "
                     f"True — reset_environment would skip pressing pause "
                     f"entirely and start navigating a menu that is not there")
    got = pm.selected_item(img)
    if got is not None:
        wrong_names.append((name, got))
        fails.append(f"{name} has no menu on it, but selected_item confidently "
                     f"said {got!r}. reset_environment believes that and "
                     f"presses cross into the live world")

# --- 3. degenerate menus abstain (and for the right reason) ----------------
# Built by repainting only the four menu bands of a real pause frame, so the
# page, the book and the rest of the screen stay exactly as captured.
BAND_H = None


def _band_box(img, idx):
    w, h = img.size
    _, y = pm.MENU_ITEMS[idx]
    return (int(w * pm.MENU_X_FRAC[0]),
            int(h * (y - pm.MENU_BAND_HALF_HEIGHT)),
            int(w * pm.MENU_X_FRAC[1]),
            int(h * (y + pm.MENU_BAND_HALF_HEIGHT)))


PAPER = (175, 175, 175)   # measured median of the pause page, well under
WHITE = (255, 255, 255)   # WHITE_LEVEL; pure white is well over it
DARK = (30, 30, 30)       # what the confirmation dialog's overlay measures


def occlude(name, indices):
    """Real pause frame with some menu rows covered by a dark box.

    The book stays open and the page stays bright — only the rows go. This is
    what an in-game dialog over the menu column looks like, and the reason the
    band test is still an AND with the page test: the page being there does not
    mean the entries can be read.
    """
    img = load(name)
    for i in indices:
        x0, y0, x1, y1 = _band_box(img, i)
        img.paste(Image.new("RGB", (x1 - x0, y1 - y0), DARK), (x0, y0))
    return img


def repaint(name, coverage):
    """Real pause frame with all four bands blanked to paper, then `coverage`
    (a list of four fractions) of each band's rows painted pure white.

    Returns (image, achieved fractions) — achieved, not requested, because the
    band is only ~36px tall and the rounding matters at these thresholds.
    """
    img = load(name)
    achieved = []
    for i, frac in enumerate(coverage):
        x0, y0, x1, y1 = _band_box(img, i)
        img.paste(Image.new("RGB", (x1 - x0, y1 - y0), PAPER), (x0, y0))
        rows = int(round((y1 - y0) * frac))
        if rows:
            img.paste(Image.new("RGB", (x1 - x0, rows), WHITE), (x0, y0))
        achieved.append(rows / float(y1 - y0))
    return img, achieved


BASE = "reset_pause_190605.jpg"
if BASE in all_reset:
    # zero entries selected
    zero, _ = repaint(BASE, [0.0, 0.0, 0.0, 0.0])
    if not pm.is_pause_screen(zero):
        fails.append("the zero-selected fixture stopped reading as a pause "
                     "screen — its None below would prove nothing about the "
                     "hit-count rule, only that the page gate fired")
    if pm.selected_item(zero) is not None:
        fails.append(f"a pause menu with NO entry highlighted returned "
                     f"{pm.selected_item(zero)!r} instead of abstaining")

    # two entries selected — a cursor caught mid-move, or a bright artefact
    two, two_fr = repaint(BASE, [0.30, 0.0, 0.30, 0.0])
    if not pm.is_pause_screen(two):
        fails.append("the two-selected fixture stopped reading as a pause "
                     "screen — see above, the None would prove nothing")
    if pm.selected_item(two) is not None:
        fails.append(f"two entries at {two_fr[0]:.2f}/{two_fr[2]:.2f} white both "
                     f"looked selected, but selected_item picked "
                     f"{pm.selected_item(two)!r} instead of abstaining — it is "
                     f"guessing between rows")

    # --- 4. the threshold still separates the two MEASURED classes ---------
    # RECALIBRATED 2026-09-03 when WHITE_LEVEL moved 200 -> 225.
    #
    # The old numbers (0.059 unselected, 0.20 selected) were measured at level
    # 200, where the grey unselected text — which peaks at 201-210 — was still
    # being counted. Raising the level above that peak moved BOTH classes:
    #
    #     at level 200:  selected 0.0771   unselected up to 0.1075
    #     at level 225:  selected 0.0586   unselected 0.0000
    #
    # So 0.06 is no longer "the level unrelated text reaches" — it is now
    # essentially the SELECTED level, and asserting it must be rejected would
    # assert the opposite of the truth. The probes below come from the same
    # re-measurement on test_fixtures/pause_menu/load_last_save_selected.png.
    # If WHITE_LEVEL moves again, re-measure these rather than nudging them.
    dim, dim_fr = repaint(BASE, [0.005, 0.0, 0.0, 0.0])
    if pm.selected_item(dim) is not None:
        fails.append(f"a band only {dim_fr[0]:.3f} white — the level unrelated "
                     f"quest text reaches — read as "
                     f"{pm.selected_item(dim)!r}; the threshold has dropped "
                     f"into the unselected class")
    lit, lit_fr = repaint(BASE, [0.0586, 0.0, 0.0, 0.0])
    if pm.selected_item(lit) != "Resume":
        fails.append(f"a band {lit_fr[0]:.3f} white — the level a genuinely "
                     f"selected entry measures — read as "
                     f"{pm.selected_item(lit)!r}, not 'Resume'; the threshold "
                     f"has risen above the selected class and the reset can no "
                     f"longer confirm any row")

    # white_fractions must stay in menu order, or every index above is a lie
    order_probe, _ = repaint(BASE, [0.0, 0.30, 0.0, 0.0])
    fr = pm.white_fractions(order_probe)
    if len(fr) != len(pm.MENU_ITEMS) or fr.index(max(fr)) != 1:
        fails.append(f"painted row 1 (Load Last Save) but white_fractions "
                     f"peaked at index {fr.index(max(fr))}: {fr} — the "
                     f"per-entry readings are not in menu order")

# --- 4b. a readable page is not a readable menu ---------------------------
# Built on the frame where "Load Last Save" IS highlighted, with two of the
# four rows covered. If is_pause_screen relaxes to "some band is bright", this
# fixture sails through and selected_item hands back the target row off a menu
# two thirds of which is not visible — the reset would then press cross on it.
OCCL = "reset_down_191027.jpg"
if OCCL in all_reset:
    covered = occlude(OCCL, [0, 2])
    if pm.page_fraction(covered) < pm.PAGE_MIN_FRAC:
        fails.append(f"the occluded fixture lost the page too "
                     f"({pm.page_fraction(covered):.3f}) — anything it proves "
                     f"below would be the page gate firing, not the band test")
    if pm.is_pause_screen(covered):
        fails.append("half the menu column is covered by a dialog box, but "
                     "is_pause_screen said True — 'the book is open' is not "
                     "the same as 'the entries can be read'")
    if pm.selected_item(covered) is not None:
        fails.append(f"with two of four rows covered, selected_item still "
                     f"answered {pm.selected_item(covered)!r} — it cannot see "
                     f"the rows it is implicitly ruling out")

# --- 5. the menu ORDER the reset's navigation depends on -------------------
names = [n for n, _ in pm.MENU_ITEMS]
if names[:2] != ["Resume", "Load Last Save"]:
    fails.append(f"MENU_ITEMS starts {names[:2]} — reset_env navigates by "
                 f"pressing Down from Resume and expects Load Last Save next")
if "Quit to Main Menu" not in names:
    fails.append("'Quit to Main Menu' is no longer in MENU_ITEMS — it is the "
                 "row that ends the session, and dropping it from the model "
                 "does not stop the cursor from reaching it")
ys = [y for _, y in pm.MENU_ITEMS]
if ys != sorted(ys):
    fails.append(f"MENU_ITEMS y-centres are not top-to-bottom: {ys}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  selected_item names the highlighted row on {len(PAUSE_TRUTH)} real "
      f"pause frames and abstains on all {len(negatives)} real non-pause "
      f"frames (13 post-load gameplay frames included, 3 of which used to "
      f"answer 'Load Last Save'); abstains on 0- and 2-selected menus while "
      f"still reading as a pause screen; threshold separates 0.06 from 0.20 "
      f"white; Load Last Save is one Down from Resume")
