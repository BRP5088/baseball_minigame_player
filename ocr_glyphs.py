"""Recognise compass glyphs (N/E/S/W) without paying a subprocess per glyph.

WHY THIS EXISTS
---------------
compass.read_bearing cost ~8.5 seconds a call, and a profile put 8502ms of an
8519ms read inside tesseract: 23 pytesseract calls at ~370ms each. None of that
is recognition work. pytesseract shells out to the `tesseract` binary, so every
call pays process spawn + a fresh load of eng.traineddata + a temp-file round
trip, and read_bearing makes one of those per candidate blob per threshold (up
to four thresholds each). That single cost is what turned a 7-second walk into
an 8-minute one, because the closed loop pays it before every decision.

The fix is not to ask tesseract for less. Three attempts at that have already
been tried and reverted on this project, all for the same reason:

  * template matching ran 72x faster and disagreed with tesseract by up to 104
    degrees on the same live frames;
  * bar correlation aliased on the periodic tick marks;
  * one whole-strip OCR call cost ~560ms instead of ~8500ms and returned
    duplicate contradictory letters (N@919, N@930, W@646, W@655, ...), which
    consensus could not separate — a STATIONARY camera read 342, 342, 157.

So this module changes only HOW tesseract is invoked, never what it is asked or
what is done with the answer. Same 6x LANCZOS upscale, same (110, 140, 170, 90)
threshold ladder, same --psm 10 with a NESW whitelist, same first-hit-wins rule.
The recognised character for any given glyph is bit-for-bit what the slow path
returned; only the process spawn goes away.

  MEASURED. Ground truth is what the SLOW path actually returned, recorded by
  running it over 8923 glyph crops cut by compass.read_bearing's own geometry
  out of 1048 saved frames (screenshot_log/reset_*, demo3/, demo2/). The crops
  were checked byte-for-byte, in order, against the images read_bearing really
  hands tesseract, so they are the same question.

      agreement with the slow path            8923 / 8923
      of which letters / abstentions          2852 / 6071
      letters read as a DIFFERENT letter         0
      abstentions turned into a letter           0
      letters turned into an abstention          0

      per glyph, the same 40 crops back to back, twice:
          original per-subprocess sweep      5380 / 5720 ms
          this module                         111 /  114 ms      ~49x
      (on a quiet machine the same pair measured ~1160 vs ~59 ms, ~20x. The
      spread is not noise: process spawn degrades far worse under load than
      an in-process call, so the busier the laptop the bigger the win.)

      per frame, 22 frames through the real compass.read_bearing, once with
      recognise replaced by the original sweep and once with this module:
          original per-subprocess sweep     10444 ms mean
          this module                        1028 ms mean
          bearings identical                   22 / 22, to 1e-9 degrees

HOW
---
Preferred backend is `tesserocr`, the Python bindings to the Tesseract C API:
no subprocess, and eng.traineddata is loaded once and reused for the life of
the process. Recognition is single threaded on purpose — see the note on
cysignals below the constants.

Two fallbacks exist so this module never becomes a new way to fail:
`tesseract` on the command line fed a FILE LIST (one spawn per threshold level
instead of one per glyph, ~4 spawns a frame), and finally plain pytesseract,
which is the original slow path and is always available because compass already
imports it. Backend choice never changes the answer — see test_ocr_glyphs.py,
which pins every backend against the recorded slow-path output.

USAGE
-----
    import ocr_glyphs
    letters = ocr_glyphs.recognise(glyph_crops)      # ["N", None, "E", ...]

`glyph_crops` are the RAW crops as compass.read_bearing cuts them, BEFORE the
6x upscale and thresholding — those are recognition steps and live in here.

There is a second, separate entry point for WHOLE LINES AND BLOCKS of text —
ban-grid card names, the scoreboard, runner banners, the ban counter:

    text = ocr_glyphs.image_to_text(prepared, psm=6)                # a block
    text = ocr_glyphs.image_to_text(prepared, psm=7, whitelist="0123456789/")

That one takes an ALREADY-preprocessed image, because each of its callers has
its own recipe tuned against real frames. See the WORD MODE section below.
"""

import collections
import os
import shutil
import subprocess
import tempfile
import threading

from PIL import Image

# --- The recognition recipe, copied from compass.read_bearing --------------
# Do not tune these to go faster. Every one of them was paid for by a live
# failure, and this module's whole claim is that it changes none of them.
#
# UPSCALE: the crop is ~52x42; tesseract reads it far more reliably at 6x.
# LADDER: FOUR thresholds. The bar sits over whatever the world happens to
#   show, so glyph contrast swings with the background — trimming this to three
#   dropped an S that only read at 90, and that frame then had one letter, no
#   scale, and no bearing at all. First level that yields a whitelisted
#   character wins, so the ORDER is part of the answer, not just the cost.
UPSCALE = 6
THRESHOLD_LADDER = (110, 140, 170, 90)
PSM_SINGLE_CHAR = 10

# SINGLE THREADED, DELIBERATELY. A pool of 8 PyTessBaseAPI handles, one per
# thread, was built and measured here: 59ms/glyph fell to 16ms, a real 3.7x,
# and it agreed with the slow path on every glyph. It was removed anyway.
#
# tesserocr links cysignals, and cysignals wraps GetUTF8Text in sig_on/sig_off
# around a PROCESS-GLOBAL state machine meant for the main thread. Driven from
# workers it interleaves, and real runs printed
#     RuntimeWarning: sig_off() without sig_on() at tesserocr.cpp:32359
# with a C backtrace through thread_run. That warning is not cosmetic: the
# state it complains about is what cysignals uses to decide where to longjmp
# when a signal arrives, and this module runs inside a process that drives a
# PS5 and gets Ctrl-C'd. Trading correct signal handling for 120ms a frame is
# not a trade this project makes — a 20x speedup that is sound beats a 70x one
# that is not.
#
# To get the parallelism back, build tesserocr with cysignals absent at build
# time (its pyx compiles a no-op branch then) and re-measure. Do not simply
# silence the warning.
#
# WORD MODE (added for OPEN-12) shares all of the above. It asks tesseract a
# different QUESTION — a line or a block of text rather than one character —
# but by the same route, in process, off the same handle cache. It deliberately
# does NOT bring its own preprocessing: every word-mode caller in this project
# already has preprocessing that was tuned against real frames and paid for by
# live failures, and re-tuning it here would change the answers, which is the
# one thing this module promises never to do.
PSM_TEXT_BLOCK = 6      # tesseract's "assume a single uniform block of text"
PSM_SINGLE_LINE = 7     # tesseract's "assume a single text line"

# How many (psm, whitelist) handles one thread keeps open. Three is what this
# codebase actually uses (glyphs at 10/NESW, names at 6/none, the ban counter
# at 7/digits); the fourth is slack so that adding one caller does not silently
# start thrashing Init.
_MAX_APIS = 4

_UNSET = object()
_lock = threading.Lock()
_backend = None
_tessdata = _UNSET
_local = threading.local()


# --- Backend selection ------------------------------------------------------

def _import_tesserocr():
    """Import tesserocr, which MUST happen on the main thread.

    tesserocr links cysignals, and cysignals installs a SIGINT handler at
    import time. `signal.signal` refuses to run anywhere but the main thread,
    so importing tesserocr from a worker raises ValueError. Backend selection
    therefore does this import eagerly, on whatever thread first calls
    recognise() — a main-thread caller (every caller today) makes the workers
    safe, and a worker-thread caller degrades to the CLI backend instead of
    exploding halfway through a frame.

    The handler it installs still raises KeyboardInterrupt, so Ctrl-C during a
    long run behaves as before; verified, not assumed.
    """
    import tesserocr
    return tesserocr


def _find_tessdata():
    """A directory containing eng.traineddata, or None.

    tesserocr ships its own libtesseract whose compiled-in datapath is often
    './', which finds no languages at all. The homebrew tesseract's tessdata is
    the one the slow path has been reading all along, so prefer it and keep
    both backends on the same model files.
    """
    global _tessdata
    if _tessdata is not _UNSET:
        return _tessdata
    tesserocr = _import_tesserocr()
    cands = []
    if os.environ.get("TESSDATA_PREFIX"):
        cands.append(os.environ["TESSDATA_PREFIX"])
    exe = shutil.which("tesseract")
    if exe:
        cands.append(os.path.join(os.path.dirname(exe), "..", "share", "tessdata"))
    cands += ["/opt/homebrew/share/tessdata", "/usr/local/share/tessdata",
              "/usr/share/tessdata", "/usr/share/tesseract-ocr/5/tessdata",
              "/usr/share/tesseract-ocr/4.00/tessdata", None]
    _tessdata = None
    for c in cands:
        try:
            path, langs = (tesserocr.get_languages(c) if c
                           else tesserocr.get_languages())
        except Exception:
            continue
        if "eng" in langs:
            _tessdata = path
            break
    return _tessdata


def backend():
    """Name of the backend in use: 'tesserocr', 'batch', or 'pytesseract'."""
    global _backend
    if _backend is None:
        with _lock:
            if _backend is None:
                _backend = _pick_backend()
    return _backend


def _pick_backend():
    forced = os.environ.get("OCR_GLYPHS_BACKEND")
    if forced:
        if forced == "tesserocr":
            _import_tesserocr()      # loud if it cannot work; it was asked for
        return forced
    try:
        _import_tesserocr()
        if _find_tessdata():
            return "tesserocr"
    except Exception:
        pass
    if shutil.which("tesseract"):
        return "batch"
    return "pytesseract"


# --- Shared preprocessing ---------------------------------------------------

def _prepared(images):
    """Upscale once per glyph; thresholding is per level and stays lazy."""
    out = []
    for im in images:
        g = im.convert("L") if im.mode != "L" else im
        out.append(g.resize((g.width * UPSCALE, g.height * UPSCALE),
                            Image.LANCZOS))
    return out


def _binar(glyph, level):
    return glyph.point(lambda p, L=level: 0 if p < L else 255)


def _accept(txt, whitelist):
    """compass's own test: exactly one character, and it is in the whitelist.

    A plain `txt in whitelist` would accept "" and "NE" as well, because that
    is substring containment on a str. compass tests membership of a dict
    keyed N/E/S/W, which accepts neither. Getting this wrong would invent
    letters out of empty reads.
    """
    return len(txt) == 1 and txt in whitelist


# --- Backend: tesserocr (no subprocess at all) ------------------------------

def _api(psm, whitelist):
    """A PyTessBaseAPI owned by, and reused by, the calling thread.

    KEYED ON (psm, whitelist), NOT ON WHITELIST ALONE. It used to be the
    latter, back when this module only ever asked for PSM 10. Word mode reads
    a name banner at PSM 6 and the ban counter at PSM 7, and both of those use
    the whitelist differently from the glyph path — so with the old key a
    SINGLE_CHAR handle would have been handed straight back to a caller asking
    for a whole line of text, and returned one character of a player's name.
    That is the exact shape this project keeps finding: a wrong answer that
    looks like a working one.

    Handles are CACHED, not swapped. Re-Init costs ~134ms against ~23ms warm,
    and the ban screen alternates PSM 6 (card names) with PSM 7 (the counter),
    so a single-slot cache would pay that on every alternation. The cache is
    bounded because the key space is caller-supplied: exceeding _MAX_APIS ends
    the least recently used handle rather than growing without limit.
    """
    from tesserocr import PyTessBaseAPI
    apis = getattr(_local, "apis", None)
    if apis is None:
        apis = _local.apis = collections.OrderedDict()
    key = (psm, whitelist)
    if key in apis:
        apis.move_to_end(key)
        return apis[key]
    api = PyTessBaseAPI(path=_find_tessdata(), psm=psm)
    # Setting an EMPTY whitelist is how tesseract expresses "no whitelist", and
    # it is what a fresh handle already has; writing it anyway keeps one code
    # path and makes a recycled handle impossible to confuse with a fresh one.
    api.SetVariable("tessedit_char_whitelist", whitelist or "")
    apis[key] = api
    while len(apis) > _MAX_APIS:
        _, evicted = apis.popitem(last=False)
        evicted.End()
    return api


def ocr_prepared(image, whitelist="NESW", psm=PSM_SINGLE_CHAR):
    """OCR ONE already-upscaled-and-thresholded image, in process.

    This is the exact substitute for a single pytesseract.image_to_string call
    and exists so a caller (or a test) can swap the OCR out at that call site
    without also taking over the preprocessing. recognise() is the interface
    to prefer; this is the seam.

    Note it STRIPS. That is right for a single glyph and wrong for a block of
    text, where the line structure is the answer — see image_to_text.
    """
    api = _api(psm, whitelist)
    api.SetImage(image)
    return api.GetUTF8Text().strip()


def _ladder_tesserocr(glyph, whitelist):
    for level in THRESHOLD_LADDER:
        txt = ocr_prepared(_binar(glyph, level), whitelist)
        if _accept(txt, whitelist):
            return txt
    return None


def _recognise_tesserocr(images, whitelist):
    return [_ladder_tesserocr(g, whitelist) for g in _prepared(images)]


# --- Backend: one CLI spawn per threshold level, not per glyph --------------

def _run_batch(paths, whitelist):
    """OCR many images in ONE tesseract process, via its file-list input.

    Pages come back concatenated and separated by form feeds, so the split is
    positional: page i is image i. Anything else would silently shift letters
    onto the wrong blobs, which is the single worst thing this module could do.
    """
    with tempfile.TemporaryDirectory() as td:
        listing = os.path.join(td, "list.txt")
        with open(listing, "w") as fh:
            fh.write("\n".join(paths) + "\n")
        proc = subprocess.run(
            ["tesseract", listing, "stdout", "--psm", str(PSM_SINGLE_CHAR),
             "-c", "tessedit_char_whitelist=" + whitelist],
            capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract exited {proc.returncode}: "
                           f"{proc.stderr.strip()[-400:]}")
    # Fed a file list, tesseract puts a form feed BETWEEN pages and none after
    # the last, so N images give exactly N chunks — including empty ones, which
    # are the common case here (most blobs are not letters). Stripping trailing
    # blanks, the obvious thing to write, turned a batch where nothing read
    # into ZERO pages and then into a length mismatch. Only a genuinely extra
    # trailing chunk is dropped, in case another tesseract build appends one.
    pages = proc.stdout.split("\x0c")
    if len(pages) == len(paths) + 1 and pages[-1] == "":
        pages.pop()
    if len(pages) != len(paths):
        raise RuntimeError(
            f"tesseract returned {len(pages)} pages for {len(paths)} images; "
            f"refusing to guess the alignment")
    return [p.strip() for p in pages]


def _recognise_batch(images, whitelist):
    glyphs = _prepared(images)
    out = [None] * len(glyphs)
    pending = list(range(len(glyphs)))
    with tempfile.TemporaryDirectory() as td:
        for level in THRESHOLD_LADDER:
            if not pending:
                break
            paths = []
            for i in pending:
                p = os.path.join(td, f"g{i:04d}_{level}.png")
                _binar(glyphs[i], level).save(p)
                paths.append(p)
            texts = _run_batch(paths, whitelist)
            still = []
            for i, txt in zip(pending, texts):
                if _accept(txt, whitelist):
                    out[i] = txt
                else:
                    still.append(i)
            pending = still
    return out


# --- Backend: the original slow path, kept as the last resort ---------------

def _recognise_pytesseract(images, whitelist):
    import pytesseract
    out = []
    for glyph in _prepared(images):
        got = None
        for level in THRESHOLD_LADDER:
            txt = pytesseract.image_to_string(
                _binar(glyph, level),
                config=f"--psm {PSM_SINGLE_CHAR} "
                       f"-c tessedit_char_whitelist={whitelist}").strip()
            if _accept(txt, whitelist):
                got = txt
                break
        out.append(got)
    return out


# --- WORD MODE: whole lines and blocks, same in-process handle -------------
#
# WHY THIS EXISTS (OPEN-12). orchestrator.py read the ban-grid card names, the
# scoreboard, the runner banners and the ban counter through pytesseract, which
# spawns a `tesseract` process per call and hands it the image through a TEMP
# FILE. On this machine that temp file is scanned by Sophos as it is written
# and again as it is unlinked: six pytesseract-heavy tests intermittently blew
# the suite's 300s ceiling, and a faulthandler dump caught them stopped inside
# pytesseract.cleanup, unlinking that file. So the migration is not merely
# ~114ms a call — it removes the temp file, and with it the whole stall.
#
# It changes HOW tesseract is invoked and nothing else: same PSM, same
# whitelist, same image, same bytes back. The agreement evidence is in
# tests/minigame/test_ocr_word_mode.py, which pins every word-mode call site's
# real crops against what pytesseract returns for them.


def tesseract_config(psm, whitelist=None):
    """The `config=` string pytesseract needs for this (psm, whitelist).

    One definition, so the fast path and the fallback cannot drift apart. A
    fallback that quietly asks a DIFFERENT question is worse than no fallback:
    it keeps answering, and the answers change.
    """
    cfg = f"--psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return cfg


def _text_tesserocr(image, psm, whitelist):
    api = _api(psm, whitelist)
    api.SetImage(image)
    return api.GetUTF8Text()


def _text_pytesseract(image, psm, whitelist):
    import pytesseract
    return pytesseract.image_to_string(
        image, config=tesseract_config(psm, whitelist))


# "batch" exists for the GLYPH path, where one spawn can carry forty images.
# Word mode gets one image per call, so batching has nothing to batch and the
# CLI backend collapses onto plain pytesseract. Mapping it explicitly beats
# leaving a KeyError for a backend selection that is otherwise perfectly valid.
_WORD_BACKENDS = {
    "tesserocr": _text_tesserocr,
    "batch": _text_pytesseract,
    "pytesseract": _text_pytesseract,
}


def image_to_text(image, psm=PSM_TEXT_BLOCK, whitelist=None):
    """Read a line or block of text out of an ALREADY-PREPROCESSED image.

    The drop-in for `pytesseract.image_to_string(image, config=...)`, returning
    the same string for the same image — trailing newlines included, because
    callers split it into lines and a missing terminator changes the split.
    Nothing is stripped here for that reason; strip at the call site, as the
    pytesseract callers already do.

    `image` is whatever the caller has already upscaled, inverted and
    thresholded. This function adds no preprocessing of its own on purpose:
    each caller's recipe was tuned against real frames, and changing it would
    change what the game does with the answer.
    """
    return _WORD_BACKENDS[backend()](image, psm, whitelist)


_BACKENDS = {
    "tesserocr": _recognise_tesserocr,
    "batch": _recognise_batch,
    "pytesseract": _recognise_pytesseract,
}


# --- Public API -------------------------------------------------------------

def recognise(images, whitelist="NESW"):
    """Recognise one character per glyph image; None where nothing read.

    `images` are small PIL grayscale crops, one glyph each, exactly as
    compass.read_bearing cuts them (raw — the upscale and thresholding happen
    in here). Returns a list the same length as `images`, aligned by position.

    Returning None is a first-class answer, not an error: a blob that is a
    point-of-interest icon rather than a letter must read as nothing, or the
    heading is computed from a marker and the walk ends somewhere arbitrary.
    """
    images = list(images)
    if not images:
        return []
    name = backend()
    try:
        fn = _BACKENDS[name]
    except KeyError:
        raise ValueError(f"unknown OCR backend {name!r}; "
                         f"expected one of {sorted(_BACKENDS)}")
    return fn(images, whitelist)
