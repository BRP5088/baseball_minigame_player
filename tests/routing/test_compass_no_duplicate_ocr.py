"""read_bearing must not re-ask tesseract a question it has already answered.

WHAT THIS GUARDS
----------------
compass.read_bearing cuts glyph crops, hands them to ocr_glyphs.recognise, and
— if no letter came back — used to run the ORIGINAL per-blob pytesseract sweep
over the same crops. Two different things reach that line:

  (a) ocr_glyphs RAN and abstained. The sweep is then the same question asked
      through a ~50x slower invocation. ocr_glyphs changes only HOW tesseract
      is invoked (same 6x upscale, same 110/140/170/90 ladder, same --psm 10
      NESW whitelist, same first-hit-wins) and is pinned against the slow
      path's recorded output over 8923 crops from 1048 frames: 8923/8923
      agreement, 0 abstentions turned into a letter. So the sweep is measured
      to return nothing here.

  (b) ocr_glyphs could not run at all (missing, or a backend raised). Then
      `letters` is a row of Nones that nothing computed, and the sweep is the
      only reader left. It must still run.

WHAT (a) COSTS. Counted 2026-09-05 over 26 archived 1920x1080 frames with
ocr_glyphs forced to abstain: a median of **12 pytesseract calls** per frame
(range 8-16) — len(crops) x 4 threshold levels, and an abstaining glyph never
breaks out early. At the 370ms per call compass.py's own header records, that
is ~4.4s per unreadable frame, and walk_steps.read_heading retries up to four
times. read_bearing abstains on ~6% of world frames and more inside the bar,
which is most of the route.

WHY IT IS TESTED BY COUNTING CALLS. Both the old and the new code return None
on an unreadable frame — that is the point, and it is why this went unnoticed.
The only observable difference is how many subprocesses were spawned to get
there, so that is what is asserted.

Offline. No game, no screen, no tesseract subprocess: pytesseract is replaced
by a counter.
"""

import os as _os
import sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
_os.environ["BASEBALL_TEST_RUN"] = "1"

import glob                       # noqa: E402
import tempfile                   # noqa: E402

from PIL import Image             # noqa: E402

import compass                    # noqa: E402
import ocr_glyphs                 # noqa: E402

fails = []


def check(msg, ok):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


# A world frame at the live capture geometry. places/ holds the localiser's own
# reference frames, which are exactly what fast_capture() returns.
FRAMES = [p for p in sorted(glob.glob(_os.path.join(_ROOT, "places", "*", "*.jpg")))
          if Image.open(p).size == (1920, 1080)][:6]
if not FRAMES:
    FRAMES = [p for p in sorted(glob.glob(
        _os.path.join(_ROOT, "test_fixtures", "**", "*.jpg"), recursive=True))
        if Image.open(p).size == (1920, 1080)][:6]

if not FRAMES:
    print("FAIL no 1920x1080 world frame to test with")
    raise SystemExit(1)


class _Counter:
    """Stands in for pytesseract and never reads anything."""

    def __init__(self):
        self.calls = 0

    def image_to_string(self, img, config=None):
        self.calls += 1
        return ""


def _read(path, recognise, tess):
    img = Image.open(path).convert("RGB")
    img.info["game_only"] = True
    real_pt, real_rec = compass.pytesseract, ocr_glyphs.recognise
    real_cache_file = compass._SCALE_CACHE_FILE
    cache = dict(compass._SCALE_CACHE)
    try:
        # Never touch the real cache file: this test is about OCR, and a stray
        # write would make it a second test of the thing it is not measuring.
        compass._SCALE_CACHE_FILE = _os.path.join(tempfile.mkdtemp(), "s.json")
        compass.pytesseract = tess
        ocr_glyphs.recognise = recognise
        return compass.read_bearing(img)
    finally:
        compass.pytesseract, ocr_glyphs.recognise = real_pt, real_rec
        compass._SCALE_CACHE_FILE = real_cache_file
        compass._SCALE_CACHE.clear()
        compass._SCALE_CACHE.update(cache)


def _abstains(images, whitelist="NESW"):
    return [None] * len(list(images))


def _raises(images, whitelist="NESW"):
    raise RuntimeError("no OCR backend, as if tesserocr were missing")


# --- 1. the fast reader ran and abstained: no subprocess may be spawned ----
tess = _Counter()
answers = [_read(p, _abstains, tess) for p in FRAMES]
check("an abstention from the fast reader spawns NO pytesseract call",
      tess.calls == 0)
check("and read_bearing still abstains (the answer is unchanged)",
      all(a is None for a in answers))

# --- 2. the CONTROL: when the fast reader cannot run, the sweep still does -
# Without this the test would pass on a build that simply deleted the fallback,
# which would leave a machine without tesserocr unable to read a bearing at all.
tess2 = _Counter()
[_read(p, _raises, tess2) for p in FRAMES]
check("CONTROL: when ocr_glyphs cannot run, the sweep DOES run",
      tess2.calls > 0)
check("CONTROL: and it is the full ladder, not one probe "
      f"({tess2.calls} calls over {len(FRAMES)} frames)",
      tess2.calls >= 4 * len(FRAMES))

# --- 3. the size of what is being avoided ----------------------------------
# Not a threshold, a record: this is the cost case 1 removes, measured on these
# very frames rather than quoted from elsewhere.
per_frame = tess2.calls / len(FRAMES)
print(f"     (the avoided sweep is {per_frame:.1f} pytesseract calls per "
      f"unreadable frame; at compass.py's recorded 370ms each that is "
      f"{per_frame * 0.370:.1f}s, and walk_steps.read_heading retries 4x)")
check("the avoided cost is real, not marginal (>= 8 calls a frame)",
      per_frame >= 8)

# --- 4. a READABLE frame is untouched by any of this -----------------------
# The change must not alter a single bearing. Run the real reader on the same
# frames and require an answer, so a build where ocr_glyphs silently stopped
# working could not pass the checks above by reading nothing anywhere.
real_answers = []
_real_file = compass._SCALE_CACHE_FILE
_kept = dict(compass._SCALE_CACHE)
try:
    # Redirect the cache file even here: read_bearing writes it when it meets a
    # geometry the file has not seen, and a test that leaves a file behind is a
    # side effect tests/harness/test_no_side_effects.py exists to catch.
    compass._SCALE_CACHE_FILE = _os.path.join(tempfile.mkdtemp(), "s.json")
    for p in FRAMES:
        img = Image.open(p).convert("RGB")
        img.info["game_only"] = True
        real_answers.append(compass.read_bearing(img))
finally:
    compass._SCALE_CACHE_FILE = _real_file
    compass._SCALE_CACHE.clear()
    compass._SCALE_CACHE.update(_kept)
check("ANTI-VACUITY: the real reader still reads these frames "
      f"({sum(a is not None for a in real_answers)}/{len(FRAMES)})",
      sum(a is not None for a in real_answers) >= max(1, len(FRAMES) - 1))

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    raise SystemExit(1)
print("all green")
