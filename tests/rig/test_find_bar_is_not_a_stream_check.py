"""find_bar answers "is there structure here", not "is the game streaming".

WHY THIS EXISTS (OPEN-18). ensure_stream.streaming() returns True as soon as
compass.find_bar() locates a horizontal light strip, on the strength of a
docstring line that read "It is None only in the state this function exists to
detect". That line was never measured and it is false.

The user watched it cost an hour on 2026-09-06: every failed reconnect attempt
announced "[stream] up via find_bar (compass strip located)" first, INCLUDING
while chiaki was not running at all and the PS5 was switched off. An unattended
run in that state presses buttons at a dead stream all night and reports
navigation failures.

THIS FILE DOES NOT FIX THAT. It pins the measurement, so the claim cannot drift
back to "find_bar is None only when disconnected" and so the next person's fix
has something to test against. Removing the branch is NOT obviously safe: it
exists because requiring read_bearing conflated "frames are arriving" with "a
compass LETTER is legible", and bright scenes ended two unattended runs in one
day. The proposed replacement, a flatness score, is UNEVALUABLE rather than
unproven -- the negative population is one frame that is not on disk, so
CLAUDE.md 10.4 cannot be satisfied from what exists.

THE FIXTURES ARE SYNTHESISED, deliberately. An earlier probe used chiaki's own
documentation screenshots, which live under the gitignored chiaki-ng-src/ and
would make this file hard-fail on a fresh clone for a reason unrelated to what
it checks. A dark window with one light horizontal toolbar is the shape of any
desktop application's chrome, it is eight lines to draw, and it trips find_bar
just as the real thing does.
"""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

from PIL import Image, ImageDraw

import compass

ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (f"  -- {detail}" if detail else ""))
    if not cond:
        ok = False


W, H = 1920, 1080


def app_chrome():
    """A dark window with one light horizontal toolbar. No game anywhere."""
    im = Image.new("RGB", (W, H), (24, 26, 30))
    ImageDraw.Draw(im).rectangle([0, 40, W, 88], fill=(210, 214, 220))
    return im


def settings_panel():
    """A light panel with dark rows -- a settings dialog, no game anywhere."""
    im = Image.new("RGB", (W, H), (245, 245, 247))
    d = ImageDraw.Draw(im)
    for y in range(120, 900, 60):
        d.rectangle([80, y, 1500, y + 28], fill=(60, 62, 68))
    return im


# --- the measurement this file exists to pin --------------------------------
for name, img in (("a dark window with one light toolbar", app_chrome()),
                  ("a light settings panel with dark rows", settings_panel())):
    got = compass.find_bar(img)
    check(f"find_bar FIRES on {name}, which contains no game at all",
          got is not None, f"find_bar -> {got}")

# --- the control: it is not simply always non-None --------------------------
# Without this the checks above are satisfied by a function that returns a
# constant, and the file would be pinning nothing.
for name, img in (("solid mid grey", Image.new("RGB", (W, H), (128, 128, 128))),
                  ("solid black", Image.new("RGB", (W, H), (0, 0, 0)))):
    got = compass.find_bar(img)
    check(f"and it is None on {name}, so it is not a constant",
          got is None, f"find_bar -> {got}")

# --- the positive control: it must still find the real thing ----------------
# If find_bar stopped working on real frames, every check above would still
# pass while the detector was broken in the opposite direction.
frames = sorted(glob.glob(os.path.join(_ROOT, "demos", "*", "f_*.jpg")))[:40]
check("there are real game frames to check against", len(frames) >= 10,
      f"{len(frames)} frames")
if frames:
    hits = [(f, compass.find_bar(Image.open(f))) for f in frames]
    found = [h for h in hits if h[1] is not None]
    check("find_bar still locates the strip on real game frames",
          len(found) == len(hits), f"{len(found)}/{len(hits)}")

    # A LEAD, RECORDED AS AN OBSERVATION AND NOT AS A RULE. On every synthetic
    # and UI image tried the strip spans the full frame width, while real game
    # frames return a strip bounded well inside it. Nobody has measured this on
    # the host list, which is the frame that actually matters, so it is not a
    # threshold and nothing branches on it. Printed so the next person sees it.
    def spans_full_width(box, width):
        return box is not None and box[1] <= 1 and box[2] >= width - 2

    synth_full = sum(1 for im in (app_chrome(), settings_panel())
                     if spans_full_width(compass.find_bar(im), W))
    game_full = sum(1 for f, b in found
                    if spans_full_width(b, Image.open(f).size[0]))
    print(f"     LEAD (not asserted): full-width strip on {synth_full}/2 "
          f"synthetic UI images and {game_full}/{len(found)} real game frames. "
          f"If that separation holds on a real host-list frame it is a "
          f"discriminator -- but that frame is not on disk, so this is one "
          f"measured population and CLAUDE.md 10.4 is unmet.")

# --- and the docstring must not re-assert the false claim -------------------
import ensure_stream
doc = ensure_stream.streaming.__doc__ or ""
check("streaming()'s docstring no longer claims find_bar is None only when "
      "disconnected",
      "is None only in the state this function exists to detect" not in doc)
check("and it names OPEN-18, so the reader is told the branch is known-weak",
      "OPEN-18" in doc)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
