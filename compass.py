"""Read the player's heading off the world HUD compass bar.

WHY
---
Turning by held-stick DURATION is open-loop: a frame-rate dip or a snagged
corner silently changes how far a fixed hold actually turns you, and the error
compounds over a multi-leg route. The compass gives an ABSOLUTE bearing from a
single frame, so a turn becomes "hold until the heading reaches X" — closed
loop, and self-correcting across the whole walk.

HOW IT WORKS
------------
The bar is a horizontal scale with N/E/S/W in circles, 90 degrees apart. Two
facts make it readable without any model:

  * the lettered circles extend ABOVE AND BELOW the bar's horizontal line,
    while the minor tick marks do not — so masking out the line's rows leaves
    mostly circles;
  * the letters sit at a fixed pixel pitch (measured 293px per 90 degrees at
    2000px capture width).

Candidate blobs are OCR'd with a NESW whitelist. Anything that is not a letter
returns empty and filters itself out, which is what happens to the point-of-
interest markers (a car, a mouse) that also ride above the bar. One confirmed
letter plus the known pitch is enough to compute the heading at view centre.

MEASURED on frame screenshot_log/reset_state_185959.jpg (2000x1292):
    N at x=908, E at x=1201  ->  pitch 293px / 90deg
    view centre x=1005       ->  heading ~30 degrees (NNE)
"""

import os

import numpy as np
import pytesseract
from PIL import Image

# --- Fast paths -------------------------------------------------------------
# A bearing read cost ~4.2s, which is the reason a 7-second walk took ten
# minutes and why turning looked, from the outside, like aimless glancing
# around: every iteration of the closed loop paid it before deciding anything.
#
# Two costs, both avoidable:
#   * the capture: orchestrator.capture_screenshot_image() re-focuses the
#     chiaki window (an ~154ms osascript round trip), sleeps 150ms, then takes
#     a full pyautogui screenshot. ~800ms. mss grabs the same pixels in ~30ms
#     and the focus call is redundant when we are only reading.
#   * the OCR: pytesseract was called once per candidate blob per threshold,
#     up to four thresholds. Dozens of subprocess round trips per frame.
#
# TEMPLATE MATCHING AND BAR CORRELATION WERE BOTH TRIED AND REMOVED. Templates
# ran 72x faster than tesseract and disagreed with it by up to 104 degrees on
# the same live frames. Correlating the bar's ticks cost ~1ms but they repeat
# every 10 degrees, so it aliased onto the wrong period and reported -80 for a
# press that moved +38. Both are fast and wrong, and a fast wrong heading
# steers a real character into a real wall. Batched in-process OCR in
# ocr_glyphs is the speedup that kept the right answers.
_MSS = None


class NoGameWindow(RuntimeError):
    """Raised when there is no game window to capture."""


_warned = set()


def _warn_once(key, msg):
    """Print `msg` the first time `key` is seen in this process, then never.

    read_bearing() runs inside every iteration of every turn's control loop —
    52 calls in one profiled trial — so a per-call warning would bury the log
    it is supposed to make readable. The conditions warned about here are
    PROCESS-WIDE (a missing import, a broken backend): they are true for the
    whole run or not at all, so once is the whole story.
    """
    if key in _warned:
        return
    _warned.add(key)
    print(msg)


def fast_capture():
    """Grab JUST THE GAME, without focusing or sleeping. ~30ms vs ~800ms.

    Returns the game's own pixels — 1920x1080 for a PS5 stream — with the
    desktop and chiaki's letterbox bars already removed, so every fraction
    taken from this frame is relative to the game and nothing else.

    WHY IT NO LONGER GRABS monitors[1]
    ----------------------------------
    That was the primary display, which held the game only because the game
    happened to be there. On 2026-08-27 the game moved to a second monitor and
    monitors[1] became a capture of the user's WORK. Hardcoding a display index
    silently captures whatever is at that index.

    WHY THE CROP IS COMPUTED, NOT DETECTED
    --------------------------------------
    Finding the letterbox by brightness fails: measured on a real frame, the
    detected width ran 1682px at one threshold and 1937px at another on the
    SAME image, because dark scene content is indistinguishable from a black
    bar. chiaki centres a 16:9 stream in its window, so the crop follows from
    the window rect the OS reports, and does not depend on what is on screen.
    """
    global _MSS
    import mss
    import input_controller as _ic
    if _MSS is None:
        _MSS = mss.mss()

    rect = _ic.game_window_rect()
    if rect is None:
        # NO GAME WINDOW IS AN ERROR, NOT A FALLBACK. This used to grab
        # monitors[1] — the exact behaviour the docstring above explains is
        # wrong — and on 2026-09-02, with chiaki not running at all, it returned
        # the CLAUDE DESKTOP WINDOW. Every detector then read that: streaming()
        # answered True, the "picture" was measured as updating, and a whole
        # setup pass was spent analysing a screenshot of this conversation.
        #
        # Returning the wrong pixels is far worse than returning none, because
        # nothing downstream can tell. Callers that legitimately cope with no
        # game (ensure_stream) catch this; the rest should fail loudly.
        raise NoGameWindow(
            "no chiaki game window found — is chiaki running and streaming? "
            "Refusing to capture the desktop instead, which is how a session "
            "got spent reading the Claude window.")

    wx, wy, ww, wh = rect
    raw = _MSS.grab({"left": int(wx), "top": int(wy),
                     "width": int(ww), "height": int(wh)})
    img = Image.frombytes("RGB", raw.size, bytes(raw.rgb))

    cw, ch = _game_content_size(ww, wh)
    if (cw, ch) != (int(ww), int(wh)):
        ox, oy = (int(ww) - cw) // 2, (int(wh) - ch) // 2
        img = img.crop((ox, oy, ox + cw, oy + ch))
    # Mark it. Everything downstream that hunts for "where is the game inside
    # this capture" can stop hunting: the frame IS the game. The mark rides on
    # the image rather than a module global, so a frame loaded from an old
    # desktop-capture fixture is never mistaken for one of these.
    img.info["game_only"] = True
    return img


STREAM_ASPECT = 16 / 9               # the PS5 output chiaki letterboxes


def is_game_only_shape(img):
    """True if this frame looks like a bare game capture rather than a desktop.

    fast_capture() marks its frames in img.info, but that mark does NOT survive
    being written to disk and read back — PIL keeps no arbitrary info keys
    through a PNG round trip. Every saved frame therefore arrived looking like a
    desktop capture, got its view bounds hunted for instead of assumed, and read
    a crop 220px off the compass.

    The shape is a reliable stand-in here because the two kinds of frame are far
    apart and both are fixed: a game capture is exactly the stream's 16:9, while
    the old desktop fixtures are 2000x1292, an aspect of 1.548. Nothing in this
    project produces a 16:9 desktop capture. If one ever does, this is where it
    will go wrong.
    """
    w, h = img.size
    return abs(w / h - STREAM_ASPECT) < 0.01


def _game_content_size(ww, wh):
    """Size of the streamed image inside a window of (ww, wh)."""
    ww, wh = int(ww), int(wh)
    if ww / wh > STREAM_ASPECT:      # window wider than the stream -> pillarbox
        return int(round(wh * STREAM_ASPECT)), wh
    return ww, int(round(ww / STREAM_ASPECT))


_GEOM_CACHE = {}          # remembered bar/viewport geometry, keyed by frame size











# Capture-coordinate box of the compass bar. Calibrated against a real
# capture_screenshot_image() frame, NOT against a chiaki-window screenshot —
# those have different geometry and the box would land on the wrong pixels.
COMPASS_BOX_FRAC = (0.27, 0.135, 0.72, 0.175)

# Rows of that crop occupied by the bar's own horizontal line. Excluded when
# hunting for circles, since the line spans every column and would swamp them.
# Expressed as FRACTIONS of the crop height: absolute row numbers were correct
# for exactly one window size, and the window gets moved and resized.
_LINE_ROW_FRAC = (0.45, 0.59)
_GLYPH_HALF_FRAC = 0.013      # was a fixed 26px, which clipped the letter when
                              # the window grew and OCR then returned nothing

# Pixels per 90 degrees, at the 2000px capture width the rest of the project
# uses. Scaled by actual frame width so a resolution change does not silently
# skew every bearing.
PITCH_PX_PER_90 = 293.0
REFERENCE_WIDTH = 2000

# Where the game view's centre sits in the capture. The frame includes the
# macOS menu bar and the dock, so this is NOT the image centre.
#
# MEASURED, not estimated. The game draws an aiming reticle at the view
# centre, which is a direct observation of this constant: a 9-pixel blob at
# x=968 of a 2000px capture -> 0.4840. The previous value 0.5025 was an eyeball
# estimate and sat 37px off, which at 293px/90deg is a SYSTEMATIC 11 degree
# bias on every absolute bearing this module reports.
#
# Closed-loop turning was immune (the bias cancels — turn_to steers on the same
# reading it targets), which is exactly why this went unnoticed. What it did
# skew is absolute claims, e.g. the spawn reading 97-98 (since remeasured at
# 57-91, which varies per reset) against a reference
# frame the user described as facing E; corrected, that becomes ~86, which is
# the better match.
VIEW_CENTRE_FRAC = 0.4840

# A blob must be at least this fraction of the widest blob to count as a
# letter ring rather than a tick. Measured separation is 28px vs 6-14px, so
# 0.55 sits comfortably in the gap at any scale.
PITCH_MIN_FRAC = 0.105          # px per 90deg, as a fraction of frame width
PITCH_MAX_FRAC = 0.200
LETTER_MAX_WIDTH_FRAC = 0.035   # wider than this is scenery, not a letter

_BEARING = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}

# Measured px-per-90deg, keyed by the window geometry it was measured under.
# Lets a one-letter frame borrow a scale measured moments earlier, without ever
# borrowing one from a different window position.
_SCALE_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "compass_scale.json")


def _load_scale_cache():
    """Scale measured in an EARLIER process, keyed by window geometry.

    A frame showing only one letter cannot establish the scale, so a fresh run
    abstains on every such frame — which live means abstaining at the spawn,
    where the camera looks at a bright floor and only one ring clears the
    blob filter. The scale is a property of the window, not of the run, so it
    is worth keeping between them. The key includes the frame size and view
    centre, so a moved or resized window simply misses and re-measures rather
    than inheriting a wrong scale.
    """
    try:
        import json
        import input_controller as _ic
        with open(_SCALE_CACHE_FILE) as fh:
            raw = json.load(fh)
        return {tuple(int(p) for p in k.split(",")): v
                for k, v in raw.get(_ic.machine_id(), {}).items()}
    except Exception:
        return {}


def _save_scale_cache():
    try:
        import json
        import input_controller as _ic
        try:
            with open(_SCALE_CACHE_FILE) as fh:
                raw = json.load(fh)
        except Exception:
            raw = {}
        # Merge, never overwrite: moving the project between computers must not
        # discard the geometry the other one measured.
        raw[_ic.machine_id()] = {",".join(str(p) for p in k): v
                                 for k, v in _SCALE_CACHE.items()}
        # Write-then-rename, because this file now lives on a NAS. A plain
        # open("w") truncates first, so a dropped mount mid-write leaves an
        # empty file and loses EVERY machine's geometry, not just this one's.
        # os.replace is atomic within a filesystem.
        import os as _os
        tmp = _SCALE_CACHE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(raw, fh, indent=1)
        _os.replace(tmp, _SCALE_CACHE_FILE)
    except Exception:
        pass


_SCALE_CACHE = _load_scale_cache()

# How far apart two letters' implied headings may be and still be believed to
# come from the same bar. Letters sit 90 degrees apart at a known pitch, so
# genuine disagreement is small (sub-degree); anything larger means one of them
# is not really a letter. 15 leaves generous room for blob-centre jitter while
# still rejecting the ~30 degree excursions seen live.
CONSENSUS_TOLERANCE_DEG = 15.0

# Tried in order until two letters separate. Low first, because a dim letter on
# a dark scene needs a low threshold; higher ones rescue the opposite case,
# where scenery bright enough to merge with a letter has to be cut away.
# Higher thresholds added for BRIGHT BACKGROUNDS. The strip is drawn over
# whatever the camera is looking at, and pointing at a light source washes it
# out: facing a chandelier, every existing threshold failed and the compass
# abstained on 8 frames out of 8, which silently stopped all yaw control.
# The letters stay near-white, so a stricter cut still isolates them when the
# background has risen to meet the old ones.
BLOB_THRESHOLDS = (120, 140, 170, 200, 225, 240)


def _candidate_blobs(gray_crop, threshold=120, min_width_frac=0.0110,
                     frame_width=REFERENCE_WIDTH):
    """Column ranges where something reaches above/below the bar's line."""
    rows = gray_crop.shape[0]
    mask = np.ones(rows, dtype=bool)
    mask[int(rows * _LINE_ROW_FRAC[0]):int(rows * _LINE_ROW_FRAC[1])] = False
    # WIDE ENOUGH TO BE A LETTER RING, not a tick. Measured on a clean bar at
    # 1728px capture width: the lettered circles are 28px across while the
    # minor ticks are 6-14px. The old floor of 6px let every tick through to
    # the recogniser, and a tick that happens to come back as a letter poisons
    # the consensus — that is what produced 315 and 269 readings on a
    # stationary camera whose two real letters (E and S) both said 150.6.
    # Letters are the WIDEST blobs on the bar; ticks are much narrower.
    # Measured on a clean bar at 1728px capture: lettered circles 28px, minor
    # ticks 6-14px. Feeding ticks to the recogniser is what produced 315 and
    # 269 readings on a stationary camera whose two real letters both said
    # 150.6 — one tick coming back as a letter poisons the consensus.
    #
    # Selected RELATIVE to the widest blob found, not as a fraction of frame
    # width: an absolute floor is calibrated to one capture size, and when the
    # view is scaled down the letter rings fall under it too, which is a
    # confidently-wrong bearing rather than a missing one.
    min_width = max(4, int(min_width_frac * frame_width))
    bright = (gray_crop[mask] > threshold).sum(axis=0)
    runs, start = [], None
    for i, v in enumerate(bright):
        if v >= 2 and start is None:
            start = i
        elif v < 2 and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(bright)))
    # A letter ring has a BOUNDED width — too narrow is a tick, too wide is
    # scenery. Measured at 1728px capture: rings 28-37px, ticks 6-14px. Both
    # bounds earned their place from a live failure:
    #   * without the lower bound, ticks reached the recogniser and a tick read
    #     as a letter poisoned the consensus (315 and 269 on a stationary
    #     camera whose real letters both said 150.6);
    #   * without the upper bound, a bright floor produced blobs of 137 and
    #     316px, and a filter defined RELATIVE to the widest blob then discarded
    #     the genuine 30px letter and abstained on every frame.
    lo = max(4, int(min_width_frac * frame_width))
    hi = max(lo + 1, int(LETTER_MAX_WIDTH_FRAC * frame_width))
    return [(a, b) for a, b in runs if lo <= b - a <= hi]


def find_bar(img, threshold=140):
    """(y, x_left, x_right) of the compass bar, or None.

    THINNESS is the signature, not brightness. Two earlier attempts failed on
    real frames: "one long unbroken run" found nothing (tick marks and letter
    circles break the bar up — its longest run is 267px while it spans ~900),
    and "most bright pixels over a wide span" picked lit scenery instead, y=576
    and y=530 against a true bar at y=200, which fed the OCR a crop with no
    letters in it and abstained on 10 of 17 frames.

    What separates the bar from a lit wall is that a wall is bright over many
    consecutive rows while the bar is bright in a couple and dark immediately
    above and below. So score each row against its own neighbourhood rather
    than against the frame.
    """
    w, h = img.size
    a = np.asarray(img.convert("L"), dtype=float)
    # Skip the very top of the frame. This existed to dodge the macOS MENU BAR,
    # back when the capture was the whole desktop and the game was a window in
    # it. fast_capture() now returns game pixels only, and on a 1080px-tall
    # game frame the old 6% skipped 64px while the compass sits at y=64 — the
    # guard was eating the thing it was meant to help find, and read_bearing
    # abstained on every frame. 3% clears any chrome without reaching the bar,
    # and returns byte-identical results on the old desktop-capture fixtures.
    top = int(h * 0.03)
    counts = (a > threshold).sum(axis=1).astype(float)
    gap = max(6, int(h * 0.010))
    best = None
    for y in range(top + gap, int(h * 0.45)):
        here = counts[y]
        if here < w * 0.10:
            continue
        around = (counts[y - gap] + counts[y + gap]) / 2.0
        score = here - around           # thin line: high here, low just off it
        if score < w * 0.05:
            continue
        bright = np.where(a[y] > threshold)[0]
        if bright.size == 0 or (bright[-1] - bright[0]) < w * 0.30:
            continue
        if best is None or score > best[0]:
            best = (score, y, int(bright[0]), int(bright[-1]))
    if best is None:
        return None
    return best[1], best[2], best[3]


def _ic_view_bounds(img):
    import input_controller as _ic
    return _ic.view_bounds(img)


_view_bounds = _ic_view_bounds


def read_bearing(img):
    """Heading in degrees (0=N, 90=E), or None if no letter could be read.

    Returns None rather than guessing — a wrong bearing would turn the player
    to face the wrong way and the walk would end somewhere arbitrary, which is
    worse than not turning at all.
    """
    w, h = img.size
    # NO HARDCODED FALLBACK. Geometry must be derived from this frame or we
    # abstain. Falling back to constants calibrated for one window position is
    # exactly what produced the worst failure of this project: after the laptop
    # moved, bearings stayed readable and plausible and were wrong by tens of
    # degrees, and eight consecutive turns drove the camera nowhere while
    # reporting sensible numbers. A missing answer is recoverable; a confident
    # wrong one is not.
    bar = find_bar(img)
    if bar is None:
        return None
    bar_y, bx0, bx1 = bar
    # Anchor on the LOCATED bar row, but keep the crop proportions that were
    # already proven to read: the bar's own bright extent is far too wide (it
    # follows whatever the scene lights up) and using it yielded 0 letters on
    # frames where the narrower window-relative box yielded one. Sized from the
    # game view, so it still tracks the window instead of assuming a position.
    if img.info.get("game_only") or is_game_only_shape(img):
        # The capture is already cropped to the game, so the view spans the
        # whole frame. Measuring it instead returns the lit part of the SCENE:
        # on a dark frame that read 0-1483 of 1920, which put the letter crop
        # 220px left of the compass and abstained on every single frame.
        vb0 = (0, w - 1, 0, h - 1)
    else:
        vb0 = _ic_view_bounds(img)
    if vb0 is None:
        return None
    vmid = (vb0[0] + vb0[1]) / 2.0
    vw = vb0[1] - vb0[0]
    band = max(14, int(h * 0.020))
    glyph_band = max(12, int(h * 0.017))
    x0, x1 = int(vmid - vw * 0.235), int(vmid + vw * 0.235)
    y0, y1 = bar_y - band, bar_y + band
    glyph_top, glyph_bot = bar_y - glyph_band, bar_y + glyph_band
    crop = img.convert("L").crop((x0, y0, x1, y1))
    arr = np.asarray(crop, dtype=float)

    # Geometry is DERIVED from the frame, not assumed. The hardcoded fractions
    # below are only a fallback: they are calibrated to one chiaki window
    # position, and moving the laptop invalidated all of them at once — the
    # reticle moved 142px and the letter spacing went 293 -> 329 px/90deg,
    # after which every bearing was wrong but still looked valid.
    pitch = PITCH_PX_PER_90 * (w / REFERENCE_WIDTH)
    centre_x = w * VIEW_CENTRE_FRAC
    vb = vb0
    centre_x = vmid

    readings = []
    half = max(12, int(w * _GLYPH_HALF_FRAC))

    # Collect every candidate glyph, then recognise them in ONE batch.
    #
    # This was the project's worst bottleneck by a wide margin. pytesseract
    # spawns a tesseract SUBPROCESS per call, and the old loop called it once
    # per blob per threshold: profiled at 8502ms of an 8519ms read, 23 spawns
    # at ~370ms each, while find_bar, view_bounds and blob-finding together
    # cost 26ms. ocr_glyphs drives the Tesseract C API in-process and keeps the
    # handle open — measured 60ms per glyph warm. That is the difference
    # between a route step taking eight minutes and taking seconds.
    #
    # Earlier attempts to go faster by recognising DIFFERENTLY were all
    # reverted for being wrong (template matching disagreed by up to 104
    # degrees; bar correlation aliased on the 10-degree ticks; one whole-strip
    # call returned duplicate contradictory letters). This one is the same
    # recogniser, merely not paying process spawn 23 times.
    # SWEEP THE THRESHOLD. A single fixed one loses letters whenever the scene
    # behind the bar is bright: measured on a frame with a lit window behind the
    # W, threshold 120 merged the letter into the window glow, the blob then
    # exceeded the max letter width and was discarded, and the read abstained
    # with only one letter found. At 140 and above both letters separate
    # cleanly. Take the first threshold that yields at least two candidates —
    # two is what fixes the scale, and one is never enough.
    blobs = []
    for _thr in BLOB_THRESHOLDS:
        blobs = _candidate_blobs(arr, threshold=_thr, frame_width=w)
        if len(blobs) >= 2:
            break

    crops, centres = [], []
    for a, b in blobs:
        cx = x0 + (a + b) / 2
        crops.append(img.convert("L").crop(
            (int(cx - half), glyph_top, int(cx + half), glyph_bot)))
        centres.append(cx)

    if crops:
        try:
            import ocr_glyphs
            letters = ocr_glyphs.recognise(crops)
        except Exception as e:
            # THE ANSWERS STAY RIGHT AND THE RUN GETS 8x SLOWER PER READ, which
            # is the worst combination to leave unannounced: the pytesseract
            # sweep below has the longest record of being correct, so nothing
            # downstream looks broken and there is no failure to trace back.
            # Measured 2026-09-04: 31ms per bearing read through ocr_glyphs
            # (in-process Tesseract C API) against 261ms through the sweep,
            # which spawns a tesseract subprocess per glyph per threshold.
            # read_bearing was 21% of a whole trial before that fix.
            #
            # Without this line a reader profiling a slow run would conclude
            # the console, the network or the walk had degraded. It is the OCR
            # backend, and it says so exactly once per process.
            _warn_once(
                "ocr_glyphs",
                f"  [compass] the fast in-process glyph reader is unavailable "
                f"({type(e).__name__}: {e}) — EVERY bearing read for the rest "
                f"of this process falls back to the pytesseract sweep. "
                f"Measured 31ms -> 261ms per read. Bearings stay CORRECT, so "
                f"nothing will look broken; the run is simply ~8x slower per "
                f"read and this is the only place that says why.")
            letters = [None] * len(crops)
        for cx, letter in zip(centres, letters):
            if letter in _BEARING:
                readings.append((cx, letter))

    if not readings and crops:
        # Fall back to the original per-blob sweep. Slow, but it has the
        # longest record of being correct, and abstaining on a frame the old
        # code could read would be a regression.
        for cx, glyph in zip(centres, crops):
            g6 = glyph.resize((glyph.width * 6, glyph.height * 6), Image.LANCZOS)
            for level in (110, 140, 170, 90):
                txt = pytesseract.image_to_string(
                    g6.point(lambda p, L=level: 0 if p < L else 255),
                    config="--psm 10 -c tessedit_char_whitelist=NESW").strip()
                if txt in _BEARING:
                    readings.append((cx, txt))
                    break
            if len(readings) >= 4:
                break

    if not readings:
        return None

    # Each confirmed letter independently implies a heading, and they must all
    # agree — they are the same bar read at different points. A plain mean does
    # NOT guard against a bad OCR, it launders it: observed live, a stationary
    # camera read 348 -> 18 -> 351 across three samples with zero input, a 30
    # degree excursion caused by one spurious blob being read as a letter and
    # dragged into the average. Steering on that produces exactly the
    # overshoot-and-return oscillation seen in turn_to.
    #
    # So take the largest group that agrees instead, and average only that.
    # Two letters 90 degrees apart pin the scale exactly, so measure it rather
    # than trusting REFERENCE_WIDTH scaling.
    # The LAST hardcoded fallback, and the one that survived every other fix:
    # with only one letter visible there is nothing to measure the scale
    # against, and PITCH_PX_PER_90 is calibrated to one window size. On a moved
    # window the true scale was 221 px/90deg while the constant said 293, which
    # alone put the heading 29 degrees out — with the bar and reticle both
    # located perfectly. So two letters are REQUIRED; one letter means abstain.
    spans = []
    for i in range(len(readings)):
        for j in range(i + 1, len(readings)):
            (cxa, la), (cxb, lb) = readings[i], readings[j]
            dd = angular_error(_BEARING[la], _BEARING[lb])
            if abs(dd) >= 45.0:
                spans.append(abs(cxb - cxa) / (abs(dd) / 90.0))
    # Two letters pin the scale exactly. One letter cannot, and the hardcoded
    # constant is calibrated to a single window size — using it on a moved
    # window put the heading 29 degrees out with bar and reticle both located
    # perfectly. But REQUIRING two letters costs too much: it took the logged
    # frames from 17/17 readable down to 7/17.
    #
    # So: measure the scale whenever two letters are visible and remember it,
    # tagged with the geometry it was measured under. A one-letter frame may
    # reuse it only while the window has not moved — checked against the
    # reticle position and bar span, both of which shift when it does.
    # Keyed on the RETICLE position and frame size, not the bar's extent: the
    # bar's bright span depends on what the scene happens to light up, so
    # keying on it made every frame look like a different window and the cache
    # never hit (10 of 17 frames abstained). The reticle is the view centre —
    # it moves only when the window actually moves.
    geom = (w, h, round(centre_x / 6.0), round(vb[2] / 6.0))
    if spans:
        candidate = float(np.median(spans))
        # A derived scale must be PLAUSIBLE, not merely self-consistent.
        # Measured, the bar runs ~0.15 of the frame width per 90 degrees
        # (295px at 2000, 262px at 1728). When two letters are misread the
        # scale is computed from the same wrong pair and then agrees with
        # itself: 'W' and 'E' 256px apart implies 180 degrees at 128px/90,
        # i.e. 0.064 of the width, and that bogus scale passed every
        # consistency check while putting the heading 31 degrees out.
        if PITCH_MIN_FRAC * w <= candidate <= PITCH_MAX_FRAC * w:
            pitch = candidate
        elif geom in _SCALE_CACHE:
            pitch = _SCALE_CACHE[geom]
        else:
            return None
        if _SCALE_CACHE.get(geom) != pitch:
            _SCALE_CACHE[geom] = pitch
            _save_scale_cache()
    elif geom in _SCALE_CACHE:
        pitch = _SCALE_CACHE[geom]
    else:
        return None

    readings = spacing_consistent(readings, pitch)
    if not readings:
        return None
    degs = [_BEARING[letter] + (centre_x - cx) / pitch * 90.0
            for cx, letter in readings]

    return _mean_circular(consensus(degs))


def _mean_circular(vals):
    """Mean of angles on the circle, so 359 and 1 average to 0, not 180."""
    r = np.radians(vals)
    return float(np.degrees(np.arctan2(np.sin(r).mean(),
                                       np.cos(r).mean())) % 360.0)


def spacing_consistent(readings, pitch, tol_frac=0.28):
    """Largest subset of (cx, letter) whose SPACING matches their identities.

    The letters sit in a fixed cyclic order N->E->S->W at a known pitch, so two
    of them 295px apart must be 90 degrees apart. That constraint catches the
    failure a bearing vote cannot: misreads are not independent, they REPEAT.
    Measured with the camera stationary, reads returned 135 and 315 twice each
    — exactly 180 degrees apart, the signature of N read as S (or E as W). Two
    such reads corroborate each other and a majority vote confirms the wrong
    answer with confidence.

    Spacing breaks the tie because a swapped letter implies a gap the pixels do
    not show: S and W at 295px is consistent, N and W at 295px is impossible
    (that pair needs 885px).
    """
    if len(readings) < 2 or not pitch:
        return list(readings)
    best = []
    for i in range(len(readings)):
        group = [readings[i]]
        for j in range(len(readings)):
            if i == j:
                continue
            cxa, la = readings[i]
            cxb, lb = readings[j]
            want = abs(angular_error(_BEARING[la], _BEARING[lb])) / 90.0 * pitch
            got = abs(cxb - cxa)
            # same letter twice: any gap is a repeat of one ring, skip the pair
            if la == lb:
                continue
            if abs(got - want) <= tol_frac * max(pitch, 1.0):
                group.append(readings[j])
        if len(group) > len(best):
            best = group
    if len(best) >= 2:
        return best
    # Two or more letters that agree with NONE of each other are a
    # contradiction, not weak evidence. Returning them anyway is how a moved
    # window produced 334 where the truth was 302: 'W' and 'E' 256px apart
    # implies 180 degrees, which needs ~512px, so one of them is misread and
    # there is no way to tell which. Abstain instead.
    return [] if len(readings) >= 2 else list(readings)


def consensus(degs):
    """The largest subset of implied headings that agree with each other.

    Every letter on the bar implies the same heading, so a value that disagrees
    with the others is not a letter. Returns the whole input when nothing
    agrees (a single reading has nothing to corroborate it, and abstaining
    whenever only one letter is visible would reject most frames — the bar
    often shows just one).
    """
    best = []
    for anchor in degs:
        agree = [d for d in degs
                 if abs(angular_error(anchor, d)) <= CONSENSUS_TOLERANCE_DEG]
        if len(agree) > len(best):
            best = agree
    return best if best else list(degs)






def describe(deg):
    """Human-readable compass point, for logging."""
    if deg is None:
        return "unknown"
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return f"{deg:.0f} ({points[int((deg + 11.25) % 360 / 22.5)]})"


# --- Closed-loop turning ---------------------------------------------------
# MEASURED live 2026-08-26: the camera sweeps ~245 deg/s, so 90 degrees is
# roughly 0.36s of held stick. That is fast enough that control is coarse — a
# 0.05s hold is already ~12 degrees — which sets the practical tolerance.
#
# The compass CANNOT be read while the camera is moving: two 0.2s holds in a
# row both returned None, and only a read after an ~0.8s settle succeeded. So
# every iteration must hold, wait, then read. Reading during the turn and
# steering on it would chase noise.
# Fitted to the measurements above: one press costs TURN_FIXED_DEG no matter
# how briefly the key is held, and TURN_RATE_DEG_PER_SEC on top of that.
TURN_FIXED_DEG = 13.5
TURN_RATE_DEG_PER_SEC = 207.0
TURN_SETTLE_SEC = 0.8
# MEASURED: the smallest turn the stream will deliver is ~15-17 degrees, even
# at a 0.01s hold — a keypress becomes a discrete event with a minimum
# duration, so there is a hard floor on how fine a correction can be. A
# tolerance below half that step cannot be met: the loop overshoots, corrects,
# and overshoots back. 10.0 produced 2 failures in 12 turns at 11.6 and 12.2
# degrees, both just outside. 12.0 sits above half a step and inside the ~15
# degree width of the corridors this has to navigate.
# VALIDATED live over 10 targets including wraparound, after correcting
# VIEW_CENTRE_FRAC and switching to the half-step stopping rule below:
#     mean |err| 3.6 deg, max 7.8, 0 abstentions
# against 4.7 / 11.6 / 2-of-12-out-of-tolerance beforehand. An offline model of
# the 16 deg floor predicted mean 3.34 / max 7.96 — the sim and the game agree,
# so the model can be trusted for future tuning without spending live runs.
# A press that changes NOTHING on screen means the input never arrived. Seen
# live when the video stream froze (laptop moved, connection dropped): chiaki
# was still frontmost and the reticle was still drawn, so both gates passed,
# and every turn burned its full 8 iterations — 45 seconds each — reporting a
# bearing frozen at 351.3 that looked like a real reading.
# MEASURED: a real 0.4s turn moves the frame by 15-45 mean levels; the frozen
# stream moved 0.914 after the same press, and 0.003 with no input at all.
PRESS_EFFECT_MIN = 3.0
PRESS_DEAD_LIMIT = 2           # consecutive no-effect presses before giving up

TURN_TOLERANCE_DEG = 12.0      # reporting/threshold for callers only
MIN_TURN_STEP_DEG = 16.0       # measured floor: 15-17 deg, even at a 0.01s hold
# MUST stay at the hold that produces the measured 16 deg floor. At 0.05 the
# smallest press the loop could issue was ~24 deg while the stop threshold was
# 8, so any error between 8 and 24 was uncorrectable: the loop overshot, came
# back, and overshot again. Observed live as a limit cycle bouncing 256-280
# around a target of 266 for all 8 iterations.
MIN_HOLD_SEC = 0.01

# THE RIGHT STICK IS THE ONLY THING THAT TURNS. Measured 2026-08-26, 0.3s holds:
#
#     look_right   +72.2  +119.9  +72.8      right stick: turns
#     look_left    -72.3   -73.0  -68.9      right stick: turns
#     walk_right    -0.5    +0.1   +0.2      A/D:  does NOT turn
#     walk_left     -0.2    -0.1   -0.1
#     walk_up       -0.4    -0.1   +0.5      W:    does NOT turn
#
# So this compass reads the CAMERA, and WASD moves the character underneath it
# without rotating it — 0.5 degrees of noise across nine presses. Two
# consequences, and the second is the one that matters:
#
#   * there is no finer turning mechanism to fall back on. The ~17 degree floor
#     above is the hardware floor, not an artifact of which control we picked.
#   * a heading SURVIVES A WALK LEG UNCHANGED. Turn error therefore cannot
#     accumulate down a multi-leg route: each leg re-aims from an absolute
#     bearing, so a bad turn costs that leg and nothing after it.


def angular_error(current, target):
    """Signed shortest rotation from current to target, in (-180, 180]."""
    return (target - current + 180.0) % 360.0 - 180.0


AGREE_TOLERANCE_DEG = 12.0     # two reads this close are the same heading
STABLE_MIN_AGREE = 2           # how many must agree before we believe them
STABLE_MAX_READS = 5


def read_bearing_stable(capture, log=None):
    """A bearing corroborated by a second read, or None.

    A SINGLE read is not trustworthy. Measured with the camera completely
    stationary (frame-to-frame change ~1.0, i.e. nothing moving) the bearing
    still jumped 150 -> 315 -> 150 -> 269 across consecutive reads: excursions
    of 165 and 119 degrees that were pure misreads. Steering a control loop on
    one of those sends the walk into a wall, and no amount of gain tuning
    helps, because the error is in the sensor rather than the actuator.

    The same FRAME re-read gives the same answer every time, so this is not
    randomness inside tesseract — tiny frame differences flip which glyphs are
    recognised. Independent samples therefore disagree, which is exactly the
    condition a vote fixes.

    Affordable only because a read now costs ~350ms instead of ~8500ms; at the
    old price this would have been 45 seconds.
    """
    seen = []
    for _ in range(STABLE_MAX_READS):
        b = read_bearing(capture())
        if b is None:
            continue
        for other in seen:
            if abs(angular_error(other, b)) <= AGREE_TOLERANCE_DEG:
                return _mean_circular([other, b])
        seen.append(b)
    if log and seen:
        log(f"    bearing never corroborated across {len(seen)} reads: "
            f"{[round(x) for x in seen]}")
    return None


class _TurnAborted(RuntimeError):
    """Raised inside the injected press to stop a turn from outside the loop."""


_GAIN = None          # one estimator for the whole session: the scale belongs
                      # to the window, not to any single turn


def turn_to(target_deg, press, capture, max_iters=8, log=print):
    """Rotate until the compass reads `target_deg`. Returns the final bearing.

    Closed loop on the HUD compass rather than open-loop timing. Open-loop was
    measured and rejected: replaying identical presses from an identical save
    landed 25 degrees apart, which would compound over a four-turn route.

    The control law lives in turn_gain.run_turn — robust gain estimation and
    the stopping rule — while this function keeps the two guards that belong to
    the screen rather than to the controller:

      * FOCUS. Without it every press vanishes and the bearing simply never
        changes, which reads as a camera that will not turn.
      * DEAD INPUT. A press that changes nothing on screen means the stream is
        frozen; seen live, this burned all 8 iterations per turn at 45s each
        while reporting a bearing frozen at 351.3 that looked like real data.

    Returns None if the bearing never became readable, focus was lost, or the
    stream stopped responding — the caller must treat that as "do not walk",
    since walking on an unknown heading ends somewhere arbitrary.
    """
    import time

    import turn_gain

    import input_controller as _ic

    global _GAIN
    if _GAIN is None:
        _GAIN = turn_gain.GainEstimator()

    dead = [0]

    def guarded_press(action, hold_seconds=0.0, post_delay=0.3):
        if not _ic.has_focus():
            log(f"    turn: chiaki is NOT FRONTMOST ({_ic.frontmost_app()!r} "
                f"is) — refusing to press")
            raise _TurnAborted()
        before = np.asarray(capture().convert("L"), dtype=float)
        press(action, hold_seconds=hold_seconds, post_delay=post_delay)
        time.sleep(0.4)
        moved = float(np.abs(np.asarray(capture().convert("L"), dtype=float)
                             - before).mean())
        dead[0] = dead[0] + 1 if moved < PRESS_EFFECT_MIN else 0
        if dead[0] >= PRESS_DEAD_LIMIT:
            log(f"    turn: {dead[0]} presses changed nothing on screen (last "
                f"delta {moved:.2f}) — the stream is frozen or input is not "
                f"reaching the game. Reconnect chiaki.")
            raise _TurnAborted()

    try:
        return turn_gain.run_turn(target_deg, guarded_press,
                                  lambda: read_bearing_stable(capture),
                                  estimator=_GAIN, max_iters=max_iters,
                                  settle_sec=TURN_SETTLE_SEC, log=log)
    except _TurnAborted:
        return None
