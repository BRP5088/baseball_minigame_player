"""ocr_glyphs must return EXACTLY what the slow per-subprocess path returned.

WHY THIS EXISTS
---------------
Reading the compass cost ~8.5s and a profile put 8502ms of an 8519ms read
inside tesseract — 23 pytesseract calls at ~370ms each, one subprocess per
candidate blob per threshold. ocr_glyphs removes the subprocess. It must not
remove anything else.

That distinction is the whole point, because THREE faster compass reads have
already been built and reverted on this project, each of them plausible:

  * template matching, 72x faster, disagreed with tesseract by up to 104
    degrees on the same live frames;
  * bar cross-correlation aliased on the periodic tick marks;
  * a single whole-strip OCR call cost 560ms instead of 8500ms and returned
    duplicate contradictory letters, so a STATIONARY camera read 342, 342,
    157, 341, 251, 251, 299.

A wrong bearing is not a wrong number. It turns the player to face somewhere
else and the walk ends somewhere arbitrary, and it does it while reporting
perfectly sensible-looking degrees. So this suite does not measure accuracy
against what a human thinks the letters are — it pins ocr_glyphs against what
the slow path ACTUALLY RETURNED, character for character, including every
place the slow path read nothing.

test_fixtures/compass_glyphs/ holds 200-odd glyph crops cut by
compass.read_bearing's own geometry out of screenshot_log/reset_*.jpg and the
demo3/demo2 recordings, and truth.json is the recorded output of the slow path
(pytesseract, 6x LANCZOS, thresholds 110/140/170/90, --psm 10, whitelist NESW)
over exactly those crops. frames/frame.jpg is one whole screenshot, kept for
the end-to-end leg. They live under test_fixtures/ and NOT in screenshot_log/,
which is a live log directory that gets pruned.

The crops are frozen files, so this suite keeps working while compass.py's
geometry is edited: what it pins is the OCR, not where the glyphs are cut.

The checks below are ordered by what they would have caught:

  AGREEMENT   the letters, against the recorded slow path.
  ALIGNMENT   batching must not shuffle answers onto the wrong blobs. The
              batch backend splits one tesseract output into pages by form
              feed, and a page-count that is off by one would silently slide
              every letter onto its neighbour — a wrong heading that looks
              entirely valid. Permuting the input must permute the output.
  LADDER      all four thresholds must still matter. Trimming the ladder to
              three once dropped an S that only read at 90, leaving a frame
              with one letter, no scale and no bearing at all. The fixture is
              chosen so removing ANY level, or reversing their order, changes
              an answer — which is also what makes mutating the module fail
              this test instead of surviving it.
  MECHANISM   the speedup itself: recognising N glyphs must not spawn N
              processes. Everything above would still pass at 8.5s a frame.
  SPLITTING   the batch backend's form-feed page split, driven directly with
              synthetic tesseract output, including the malformed case its
              length guard exists for.
  FRAME       one real frame read twice by the REAL compass.read_bearing —
              once with recognise replaced by a transcription of the ORIGINAL
              per-blob pytesseract sweep, once with the real one — must give
              the same DEGREES, not merely the same letters. Guarded against
              going vacuous if read_bearing stops calling recognise.
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


import json
import os
import random
import subprocess
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

from PIL import Image

import ocr_glyphs

HERE = _ROOT
FIX = os.path.join(HERE, "test_fixtures", "compass_glyphs")

fails = []

truth = json.load(open(os.path.join(FIX, "truth.json")))
names = sorted(truth)
imgs = [Image.open(os.path.join(FIX, n)).convert("L") for n in names]
letters = [n for n in names if truth[n]]
blanks = [n for n in names if not truth[n]]

# --- the fixture itself, before anything is asked of the module ------------
# A suite that silently lost its corpus passes by testing nothing. These are
# the properties every check below leans on.
if len(names) < 100:
    fails.append(f"fixture has only {len(names)} glyphs; it is meant to hold "
                 f"200-odd and cover four letters plus the non-letter blobs")
missing = set("NESW") - {truth[n] for n in letters}
if missing:
    fails.append(f"fixture never exercises {sorted(missing)} — the slow path "
                 f"read no such letter in it, so agreement on them is untested")
if len(blanks) < 40:
    fails.append(f"fixture has only {len(blanks)} glyphs the slow path read as "
                 f"nothing; abstention is the majority case and the one a "
                 f"careless speedup breaks")
if len({n.split('__')[0] for n in names}) < 3:
    fails.append("fixture frames come from fewer than three recordings; "
                 "one capture session is not evidence of anything")

backend = ocr_glyphs.backend()

# --- AGREEMENT -------------------------------------------------------------
got = ocr_glyphs.recognise(imgs)
if len(got) != len(imgs):
    fails.append(f"recognise returned {len(got)} answers for {len(imgs)} "
                 f"images — the caller pairs these with blob positions")
else:
    bad = [(n, truth[n], g) for n, g in zip(names, got) if truth[n] != g]
    if bad:
        fails.append(f"{len(bad)}/{len(names)} glyphs disagree with the slow "
                     f"path (backend={backend}); first few: " +
                     "; ".join(f"{n}: slow={t!r} fast={f!r}"
                               for n, t, f in bad[:6]))

# --- ALIGNMENT -------------------------------------------------------------
if ocr_glyphs.recognise([]) != []:
    fails.append("recognise([]) must be [], not an error or a padded list")

order = list(range(len(imgs)))
random.Random(11).shuffle(order)
shuffled = ocr_glyphs.recognise([imgs[i] for i in order])
slid = [(names[i], got[i], shuffled[k]) for k, i in enumerate(order)
        if got[i] != shuffled[k]]
if slid:
    fails.append(f"{len(slid)} answers changed when the SAME glyphs were "
                 f"passed in a different order — batching is misaligning "
                 f"results with inputs; first: {slid[:3]}")

# One at a time must equal the same glyph inside a batch. This is the check
# that separates "the batch is self-consistent" from "the batch is right".
solo_idx = list(range(0, len(imgs), max(1, len(imgs) // 12)))[:12]
for i in solo_idx:
    solo = ocr_glyphs.recognise([imgs[i]])
    if solo != [got[i]]:
        fails.append(f"{names[i]} reads {solo[0]!r} alone but {got[i]!r} in a "
                     f"batch — the answer depends on its neighbours")

# --- LADDER ----------------------------------------------------------------
# Each threshold must change an answer on this fixture, or the fixture is not
# evidence that the ladder is needed and a trimmed ladder would pass.
full = tuple(ocr_glyphs.THRESHOLD_LADDER)
if len(full) != 4:
    fails.append(f"THRESHOLD_LADDER is {full}; compass reads at four levels "
                 f"and the order of them decides which letter wins")
# Only the glyphs the slow path read as LETTERS, and that loses nothing:
# removing a level, or reordering the levels, cannot conjure a letter out of a
# glyph that read as nothing at every level. So a glyph whose full-ladder
# answer is None has the same answer under every variation, and testing it
# would only cost time. Restricting here keeps the five extra passes cheap
# without weakening the claim.
sub = [imgs[names.index(n)] for n in letters]
sub_full = ocr_glyphs.recognise(sub)
if sub_full != [truth[n] for n in letters]:
    fails.append("the letter subset does not even reproduce itself; the "
                 "ladder checks below would be measuring noise")
try:
    for drop in range(len(full)):
        ocr_glyphs.THRESHOLD_LADDER = full[:drop] + full[drop + 1:]
        without = ocr_glyphs.recognise(sub)
        if without == sub_full:
            fails.append(
                f"dropping threshold {full[drop]} changed no answer on "
                f"{len(sub)} glyphs — the fixture cannot tell whether that "
                f"level is load-bearing, so a trimmed ladder would pass")
    ocr_glyphs.THRESHOLD_LADDER = tuple(reversed(full))
    if ocr_glyphs.recognise(sub) == sub_full:
        fails.append("reversing the threshold order changed no answer; "
                     "first-hit-wins is then untested and the fixture holds "
                     "no glyph the levels disagree about")
finally:
    ocr_glyphs.THRESHOLD_LADDER = full

# --- MECHANISM -------------------------------------------------------------
# The reason the old path cost 8.5s was one process per glyph per threshold.
# Count the spawns instead of the seconds: a wall-clock threshold on a loaded
# laptop is a coin flip, but "did it spawn 160 processes" is not.
# Popen ONLY. subprocess.run is implemented ON TOP of Popen, so patching both
# counts every real spawn twice — which is exactly what happened here: the
# batch backend's honest 4 spawns were reported as 8 and failed this check.
spawns = []
_popen = subprocess.Popen
subprocess.Popen = lambda *a, **k: (spawns.append(a[0] if a else k.get("args")),
                                    _popen(*a, **k))[1]
try:
    ocr_glyphs.recognise(imgs[:40])
finally:
    subprocess.Popen = _popen

if backend == "pytesseract":
    fails.append("no fast OCR backend is available, so ocr_glyphs fell back to "
                 "the original one-subprocess-per-call path and buys nothing. "
                 "Install tesserocr (pip install tesserocr) or put tesseract "
                 "on PATH — a silent fall back to 8.5s a read is exactly the "
                 "failure this module exists to remove")
elif len(spawns) > len(full):
    fails.append(f"recognising 40 glyphs spawned {len(spawns)} processes; the "
                 f"whole point is at most one spawn per threshold level "
                 f"({len(full)}), and zero on the tesserocr backend")

# --- BATCH PAGE SPLITTING --------------------------------------------------
# The batch backend turns ONE tesseract stdout back into per-glyph answers by
# splitting on form feeds. Everything else in this file exercises that only
# through the happy path, where a bug in the splitting and a correct splitting
# look identical. So drive it directly with synthetic tesseract output: this is
# the check that covers the length guard, and the reason it exists.
#
# Fed a file list, tesseract writes a form feed BETWEEN pages and none after
# the last, so N images produce N chunks and most of them are EMPTY here
# (most blobs are not letters).
class _FakeProc:
    def __init__(self, out):
        self.stdout, self.stderr, self.returncode = out, "", 0


_sub_run = ocr_glyphs.subprocess.run
try:
    three = ["a.png", "b.png", "c.png"]
    cases = [
        ("N\n\x0c\x0cW\n", three, ["N", "", "W"],
         "a letter, a blank and a letter must stay on their own glyphs"),
        ("\x0c\x0c", three, ["", "", ""],
         "three glyphs that all read as nothing must give three blanks, not "
         "zero pages — stripping trailing blanks was the first bug here"),
        ("", ["a.png"], [""],
         "one glyph that reads as nothing must give one blank"),
        ("N\n\x0c\x0cW\n\x0c", three, ["N", "", "W"],
         "a build that DOES append a trailing form feed must still align"),
    ]
    for out, paths, want, why in cases:
        ocr_glyphs.subprocess.run = lambda *a, _o=out, **k: _FakeProc(_o)
        try:
            gotp = ocr_glyphs._run_batch(paths, "NESW")
        except Exception as exc:
            gotp = f"{type(exc).__name__}: {exc}"
        if gotp != want:
            fails.append(f"batch page split of {out!r} gave {gotp!r}, "
                         f"expected {want!r} — {why}")

    # A page count that does not match the input MUST refuse, not realign.
    ocr_glyphs.subprocess.run = lambda *a, **k: _FakeProc("N\n\x0cW\n")
    try:
        ocr_glyphs._run_batch(three, "NESW")
        fails.append("_run_batch accepted 2 pages for 3 images; a short read "
                     "would silently slide every letter onto the wrong blob")
    except RuntimeError:
        pass
finally:
    ocr_glyphs.subprocess.run = _sub_run

# --- BACKENDS AGREE --------------------------------------------------------
# The fallbacks are not decoration: whichever one a machine lands on must give
# the same letters. tesserocr links its OWN libtesseract (5.5.1 here) while
# the CLI is whatever is on PATH (5.5.3) — two different builds, and this is
# the check that they have not drifted apart.
import shutil as _shutil

others = []
if backend != "tesserocr":
    try:
        ocr_glyphs._import_tesserocr()
        if ocr_glyphs._find_tessdata():
            others.append("tesserocr")
    except Exception:
        pass
if backend != "batch" and _shutil.which("tesseract"):
    others.append("batch")
_cstride = max(1, len(imgs) // 60)
cross = imgs[::_cstride]
cross_names = names[::_cstride]
cross_ref = got[::_cstride]
for other in others:
    saved = ocr_glyphs._backend
    try:
        ocr_glyphs._backend = other
        alt = ocr_glyphs.recognise(cross)
    except Exception as exc:                      # a backend that cannot run
        alt = None                                # is reported, not hidden
        fails.append(f"backend {other!r} raised {type(exc).__name__}: {exc}")
    finally:
        ocr_glyphs._backend = saved
    if alt is not None:
        diff = [(n, a, b) for n, a, b in zip(cross_names, cross_ref, alt)
                if a != b]
        if diff:
            fails.append(f"backend {other!r} disagrees with {backend!r} on "
                         f"{len(diff)}/{len(cross)} glyphs: {diff[:4]}")

# --- FRAME -----------------------------------------------------------------
# Letters are the module's contract, but degrees are what steers the player.
# compass.read_bearing now calls ocr_glyphs.recognise directly, so the honest
# comparison is: run the REAL read_bearing over a real frame twice, once with
# recognise replaced by a transcription of the ORIGINAL per-blob pytesseract
# sweep and once with the real one, and require the same bearing.
#
# _reference_slow below is deliberately a literal copy of the loop compass used
# to contain, written out here rather than imported from ocr_glyphs. Importing
# it would compare the module against itself, which is how this check was
# vacuous on its first draft: it patched compass.pytesseract, which the
# integrated read_bearing no longer calls except as a fallback, so both sides
# ran ocr_glyphs and agreed 16/16 while proving nothing.
#
# ONE frame, because the reference side pays ~28 real tesseract spawns (~9s).
# Breadth is the glyph-level check above; this leg exists to prove the wiring.
FRAME = os.path.join(FIX, "frames", "frame.jpg")


def _reference_slow(images, whitelist="NESW"):
    """The pre-ocr_glyphs loop, verbatim: one subprocess per blob per level."""
    import pytesseract
    out = []
    for im in images:
        g = im.convert("L")
        g = g.resize((g.width * 6, g.height * 6), Image.LANCZOS)
        got = None
        for level in (110, 140, 170, 90):
            txt = pytesseract.image_to_string(
                g.point(lambda p, L=level: 0 if p < L else 255),
                config="--psm 10 -c tessedit_char_whitelist=NESW").strip()
            if txt in ("N", "E", "S", "W"):
                got = txt
                break
        out.append(got)
    return out


if backend != "tesserocr":
    pass                    # the reference side is unconditional, but the
                            # comparison is only meaningful for the backend
                            # this machine would actually run
elif not os.path.exists(FRAME):
    fails.append(f"{FRAME} is missing; the frame-level check ran on nothing")
else:
    import compass

    frame = Image.open(FRAME)
    seen = []
    _real_recognise = ocr_glyphs.recognise
    _cache = dict(compass._SCALE_CACHE)
    try:
        def _spy(images, whitelist="NESW"):
            seen.append(len(images))
            return _reference_slow(images, whitelist)

        # Cleared before BOTH reads: a one-letter frame reuses a pitch measured
        # on an earlier frame, so a cache left over from the first read would
        # make the second one a different computation.
        ocr_glyphs.recognise = _spy
        compass._SCALE_CACHE.clear()
        slow_deg = compass.read_bearing(frame)
        ocr_glyphs.recognise = _real_recognise
        compass._SCALE_CACHE.clear()
        fast_deg = compass.read_bearing(frame)
    finally:
        ocr_glyphs.recognise = _real_recognise
        compass._SCALE_CACHE.clear()
        compass._SCALE_CACHE.update(_cache)

    # Anti-vacuity: if read_bearing stopped routing through recognise, the two
    # sides above are the same code and agreeing means nothing.
    if not seen:
        fails.append("compass.read_bearing never called ocr_glyphs.recognise, "
                     "so this frame-level check compared read_bearing with "
                     "itself and proves nothing")
    elif slow_deg is None and fast_deg is None:
        fails.append("read_bearing abstains on frames/frame.jpg either way, so "
                     "this check compares two abstentions — pick a frame that "
                     "reads")
    elif slow_deg is None or fast_deg is None:
        fails.append(f"the original per-subprocess sweep read "
                     f"{slow_deg!r} deg and ocr_glyphs read {fast_deg!r}")
    elif abs(compass.angular_error(fast_deg, slow_deg)) > 1e-9:
        fails.append(f"same frame, same compass: the original per-subprocess "
                     f"sweep gives {slow_deg:.6f} deg, ocr_glyphs gives "
                     f"{fast_deg:.6f} deg")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)

print(f"backend={backend}: {len(names)} glyph crops from "
      f"{len({n.split('__')[0] for n in names})} recordings "
      f"({len(letters)} letters, {len(blanks)} abstentions) match the recorded "
      f"slow path exactly; answers survive reordering and solo calls; each of "
      f"the {len(full)} thresholds and their order change an answer; 40 glyphs "
      f"cost {len(spawns)} subprocesses, not {40 * len(full)}; "
      f"{len(others) + 1} backend(s) agree; the batch page split survives "
      f"blank, trailing-form-feed and short output; " +
      (f"and one real frame through the real compass.read_bearing "
       f"({seen and seen[0] or 0} glyphs) gives the same degrees as the "
       f"original per-subprocess sweep"
       if backend == "tesserocr" else
       "frame-level leg SKIPPED (it needs the tesserocr backend)"))
