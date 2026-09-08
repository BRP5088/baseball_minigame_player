"""frame_dump.read_frame, and fast_capture preferring it. OFFLINE.

WHAT THIS GUARDS. read_frame is the thing that lets a walk survive the user
switching macOS Spaces, and every one of its failure modes has to end at None
rather than at a plausible-looking frame -- because a stale or torn frame is
indistinguishable downstream from a live one, and the whole project's notes are
about exactly that shape.

The dump files here are SYNTHETIC and written by this test, byte for byte in
the layout chiaki-patch/framedump.h specifies. That is the point: it pins the
FORMAT CONTRACT between the two languages, which is the seam neither side can
check alone.

MUTANTS CAUGHT (2026-09-08, each restored after):
  * staleness check deleted            -> "a stale dump reads as None" FAILS
  * the seq_before re-read deleted     -> "a torn dump reads as None" FAILS
  * the fallback to the window path
    deleted from fast_capture          -> "no dump falls back ..." FAILS
"""
import os
import struct
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np
import cv2

import frame_dump
import compass

ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (("  -- " + detail) if detail else ""))
    if not cond:
        ok = False


SCRATCH = os.environ.get("TMPDIR") or "/tmp"
PATH = os.path.join(SCRATCH, "framedump_test_%d.bin" % os.getpid())

W, H = 320, 180                     # even, and 4:2:0 clean
FILE_BYTES = frame_dump.DATA_OFFSET + 4 * 1024 * 1024


def encode_420(rgb):
    """RGB -> (Y, Cb, Cr) planes, BT.601 LIMITED RANGE, written out here.

    NOT cv2.COLOR_RGB2YUV_I420: that encoder is FULL range while cv2's
    matching DECODER is limited range, so a cv2-to-cv2 round trip is off by up
    to 228 levels and would have to be waved through with a huge tolerance --
    a tolerance that then accepts a genuinely wrong reader. Writing the forward
    transform out means the test is an INDEPENDENT implementation of the
    convention the reader assumes, so a reader using the wrong matrix fails
    here instead of passing on slack.
    """
    R = rgb[:, :, 0].astype(np.float64)
    G = rgb[:, :, 1].astype(np.float64)
    B = rgb[:, :, 2].astype(np.float64)
    h, w = rgb.shape[:2]
    Y = 16.0 + (65.481 * R + 128.553 * G + 24.966 * B) / 255.0
    Cb = 128.0 + (-37.797 * R - 74.203 * G + 112.0 * B) / 255.0
    Cr = 128.0 + (112.0 * R - 93.786 * G - 18.214 * B) / 255.0
    box = lambda P: np.clip(np.round(
        P.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))), 0, 255).astype(np.uint8)
    return np.clip(np.round(Y), 0, 255).astype(np.uint8), box(Cb), box(Cr)


def reference_rgb(w=W, h=H):
    """Three smooth gradients plus one soft blob.

    SMOOTH ON PURPOSE. 4:2:0 throws away three quarters of the chroma, so a
    hard saturated edge comes back over a hundred levels out and the tolerance
    would have to swallow it. Gradients cost 3 levels, which leaves a tolerance
    tight enough to catch a swapped plane or a wrong stride -- and the blob
    makes the picture asymmetric, so the flipped-image control below is a real
    control and not a coincidence.
    """
    xs = np.linspace(0, 255, w)
    ys = np.linspace(0, 255, h)
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :, 0] = xs[None, :].astype(np.uint8)
    img[:, :, 1] = ys[:, None].astype(np.uint8)
    img[:, :, 2] = ((xs[None, :] + ys[:, None]) / 2).astype(np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = (120 * np.exp(-(((xx - w * 0.7) / (w / 10.0)) ** 2
                           + ((yy - h * 0.3) / (h / 9.0)) ** 2))).astype(np.int32)
    return np.clip(img.astype(np.int32) + blob[:, :, None], 0, 255).astype(np.uint8)


def write_dump(path, rgb, fmt=frame_dump.FMT_NV12, age_s=0.0,
               seq=7, seq_before=None, magic=frame_dump.MAGIC,
               version=frame_dump.VERSION, strides=None, offs=None,
               min_interval_ms=50, push_us=123):
    """Write a dump file byte for byte as the C++ writer would.

    `strides` and `offs` override the packed layout, which is how the check
    below can present a dump whose planes are PADDED -- the thing that happens
    for real if av_image_copy_to_buffer's align argument ever stops being 1.
    """
    h, w = rgb.shape[:2]
    y, cb, cr = encode_420(rgb)
    if fmt == frame_dump.FMT_NV12:
        uv = np.empty((h // 2, w), np.uint8)
        uv[:, 0::2] = cb
        uv[:, 1::2] = cr
        payload = y.tobytes() + uv.tobytes()
        n_planes = 2
        strides = strides or (w, w, 0, 0)
        offs = offs or (0, w * h, 0, 0)
    else:
        payload = y.tobytes() + cb.tobytes() + cr.tobytes()
        n_planes = 3
        strides = strides or (w, w // 2, w // 2, 0)
        offs = offs or (0, w * h, w * h + (w // 2) * (h // 2), 0)
    assert len(payload) == w * h * 3 // 2, len(payload)

    ts = time.time_ns() - int(age_s * 1e9)
    hdr = frame_dump.HEADER.pack(
        magic, version,
        seq if seq_before is None else seq_before, seq,
        w, h, fmt, n_planes,
        strides[0], strides[1], strides[2], strides[3],
        offs[0], offs[1], offs[2], offs[3],
        len(payload), ts, 1234567890, frame_dump.DATA_OFFSET,
        4 * 1024 * 1024, 0, 1, 1, push_us, min_interval_ms, 0)
    with open(path, "wb") as fh:
        fh.write(hdr)
        fh.write(b"\x00" * (frame_dump.DATA_OFFSET - len(hdr)))
        fh.write(payload)
        fh.write(b"\x00" * (FILE_BYTES - frame_dump.DATA_OFFSET - len(payload)))
    frame_dump._MAPS.clear()        # a new file every time, never a cached one


def maxdiff(img, rgb):
    return int(np.max(np.abs(np.asarray(img, np.int16) - rgb.astype(np.int16))))


REF = reference_rgb()

# ---------------------------------------------------------------------------
# (a) round trip
# ---------------------------------------------------------------------------
# The tolerance is 4:2:0 CHROMA SUBSAMPLING plus rounding: the smooth reference
# costs 3 levels through the round trip (measured), so 8 is snug. A swapped
# plane, a wrong stride or the wrong colour matrix is off by TENS to HUNDREDS,
# and the control immediately below proves this still discriminates.
TOL = 8
for name, fmt in (("NV12", frame_dump.FMT_NV12), ("I420", frame_dump.FMT_I420)):
    write_dump(PATH, REF, fmt=fmt)
    img = frame_dump.read_frame(PATH)
    check("a fresh %s dump round-trips to the right picture" % name,
          img is not None and img.size == (W, H) and maxdiff(img, REF) <= TOL,
          "size %s, max channel error %s" % (
              img.size if img else None, maxdiff(img, REF) if img else "n/a"))

# THE CONTROL for that tolerance: a DIFFERENT picture must fail it, or the
# check above would pass on anything (CLAUDE.md 10.12).
other = REF[::-1, ::-1].copy()
check("...and the tolerance rejects a different picture",
      maxdiff(frame_dump.read_frame(PATH), other) > TOL,
      "max channel error %d against the flipped reference"
      % maxdiff(frame_dump.read_frame(PATH), other))

# ---------------------------------------------------------------------------
# (b) staleness
# ---------------------------------------------------------------------------
write_dump(PATH, REF, age_s=5.0)
check("a stale dump reads as None -- the stream is not producing frames",
      frame_dump.read_frame(PATH) is None)

write_dump(PATH, REF, age_s=0.0)
check("...and the same dump, fresh, reads fine (the control)",
      frame_dump.read_frame(PATH) is not None)

write_dump(PATH, REF, age_s=frame_dump.MAX_AGE_S + 0.2)
check("the age gate is MAX_AGE_S and not something looser",
      frame_dump.read_frame(PATH) is None,
      "MAX_AGE_S = %.2fs" % frame_dump.MAX_AGE_S)

write_dump(PATH, REF, age_s=-30.0)
check("a timestamp from the FUTURE is refused, not treated as fresh",
      frame_dump.read_frame(PATH) is None)

# ---------------------------------------------------------------------------
# (c) tearing
# ---------------------------------------------------------------------------
write_dump(PATH, REF, seq=9, seq_before=10)
check("a torn dump (seq_before != seq_after) reads as None",
      frame_dump.read_frame(PATH) is None)

# A read that is torn ONCE must RETRY and return the consistent copy. The real
# _snapshot does the work in both attempts: attempt 1 sees the torn file on
# disk and rejects it with its own logic, then this wrapper repairs the file
# and attempt 2 succeeds. Nothing here fakes the verdict.
write_dump(PATH, REF, seq=9, seq_before=10)
_real = frame_dump._snapshot
_calls = []


def _flaky(buf):
    r = _real(buf)
    _calls.append(r)
    if len(_calls) == 1:
        with open(PATH, "r+b") as fh:            # repair: seq_before := 9
            fh.seek(8)
            fh.write(struct.pack("<Q", 9))
            fh.flush()
            os.fsync(fh.fileno())
    return r


frame_dump._snapshot = _flaky
try:
    img = frame_dump.read_frame(PATH)
finally:
    frame_dump._snapshot = _real
check("a read torn ONCE is retried and the consistent copy returned",
      img is not None and len(_calls) == 2 and _calls[0] is None
      and _calls[1] is not None,
      "%d attempt(s), first %s" % (len(_calls),
                                   "rejected" if _calls and _calls[0] is None else "accepted"))

# ---------------------------------------------------------------------------
# structural refusals
# ---------------------------------------------------------------------------
write_dump(PATH, REF, magic=b"XXXX")
check("a file with the wrong magic reads as None", frame_dump.read_frame(PATH) is None)
write_dump(PATH, REF, version=frame_dump.VERSION + 1)
check("a file with an unknown version reads as None", frame_dump.read_frame(PATH) is None)
write_dump(PATH, REF, seq=0)
check("a dump with no frame written yet (seq 0) reads as None",
      frame_dump.read_frame(PATH) is None)
frame_dump._MAPS.clear()
check("a path that does not exist reads as None",
      frame_dump.read_frame(PATH + ".nope") is None)

# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------
BIG = reference_rgb(1920, 1080)
write_dump(PATH, BIG)
frame_dump.read_frame(PATH)                       # warm numpy/cv2
t0 = time.perf_counter()
N = 10
for _ in range(N):
    frame_dump.read_frame(PATH)
per_ms = (time.perf_counter() - t0) / N * 1000.0
check("a 1920x1080 read costs well under the 111ms screen grab it replaces",
      per_ms < 40.0, "%.1f ms/read" % per_ms)

# ---------------------------------------------------------------------------
# the offline suite must never be served by the LIVE rig's dump
# ---------------------------------------------------------------------------
# tests/rig/test_no_game_window.py stubs game_window_rect to None and requires
# fast_capture to RAISE. With a chiaki streaming on this machine the default
# dump would hand it a real frame, and that test would pass or fail according
# to whether the console was awake. So read_frame() refuses the DEFAULT and the
# ENVIRONMENT path under BASEBALL_TEST_RUN, while always obeying a path a
# caller names.
write_dump(PATH, REF)
os.environ["CHIAKI_FRAME_DUMP"] = PATH
check("BASEBALL_TEST_RUN is set for this test", bool(os.environ.get("BASEBALL_TEST_RUN")))
check("read_frame() with NO path refuses the environment's dump under "
      "BASEBALL_TEST_RUN", frame_dump.read_frame() is None)
check("...while a path the caller NAMES is still read (or the gate would "
      "disable this whole test file)", frame_dump.read_frame(PATH) is not None)

# ---------------------------------------------------------------------------
# (e) the reader BELIEVES THE WRITER'S DECLARED LAYOUT, and refuses a padded one
# ---------------------------------------------------------------------------
# framedump.cpp records stride[] and plane_offset[] so that a reader does not
# have to guess -- and the first version of this module guessed anyway, deriving
# (h*3//2, w) from the format alone and never reading either field. That is
# right exactly while the C++ passes align=1 to av_image_copy_to_buffer. Change
# that one argument and every plane gains padding, the reshape shears the
# picture a few pixels per row, and nothing raises. cv2's NV12/I420 conversions
# cannot take a stride at all, so a padded dump has to be REFUSED.
write_dump(PATH, REF, strides=(W + 16, W + 16, 0, 0))
check("a dump whose declared stride is PADDED is refused, not sheared",
      frame_dump.read_frame(PATH) is None,
      "stride %d against width %d" % (W + 16, W))

write_dump(PATH, REF, offs=(0, W * H + 64, 0, 0))
check("a dump whose declared plane OFFSET is not the packed one is refused",
      frame_dump.read_frame(PATH) is None)

write_dump(PATH, REF)
check("...and the packed layout the C++ actually writes still reads (the control)",
      frame_dump.read_frame(PATH) is not None)

# The I420 side of the same rule: three planes, chroma stride w/2.
write_dump(PATH, REF, fmt=frame_dump.FMT_I420, strides=(W, W, W, 0))
check("an I420 dump claiming full-width chroma strides is refused",
      frame_dump.read_frame(PATH) is None)
write_dump(PATH, REF, fmt=frame_dump.FMT_I420)
check("...and a correct I420 dump still reads (the control)",
      frame_dump.read_frame(PATH) is not None)

# ---------------------------------------------------------------------------
# (f) the staleness gate comes from the WRITER, not from a copy of its constant
# ---------------------------------------------------------------------------
# MAX_AGE_S used to be justified by a comment that hard-coded the C++'s 50ms
# throttle. A constant mirrored by hand across two languages is CLAUDE.md 5's
# RELEASE_MS bug: the mirror goes stale and the check goes vacuous with nothing
# failing. The writer now records min_interval_ms and the reader multiplies it.
write_dump(PATH, REF, age_s=1.0, min_interval_ms=50)
check("at a 50ms throttle a 1.0s-old frame is stale (floor MAX_AGE_S = %.2f)"
      % frame_dump.MAX_AGE_S,
      frame_dump.read_frame(PATH) is None)

write_dump(PATH, REF, age_s=1.0, min_interval_ms=200)
check("...and at a 200ms throttle the SAME age is fresh -- the gate follows "
      "the writer", frame_dump.read_frame(PATH) is not None,
      "AGE_MARGIN %d x 200ms = %.1fs" % (frame_dump.AGE_MARGIN,
                                         frame_dump.AGE_MARGIN * 0.2))

write_dump(PATH, REF, age_s=3.0, min_interval_ms=200)
check("...and past even that, still stale (so the derivation is a gate, not a "
      "waiver)", frame_dump.read_frame(PATH) is None)

# ---------------------------------------------------------------------------
# (g) MAX_AGE_S is read at CALL time, not captured in a default argument
# ---------------------------------------------------------------------------
# `def read_frame(path=None, max_age_s=MAX_AGE_S)` binds the module constant
# when the def runs, so `frame_dump.MAX_AGE_S = 3.0` -- the obvious way for a
# test or an A/B arm to widen the gate -- would change NOTHING and say so
# nowhere. That is exactly CLAUDE.md 10.18: leg_reliability declared
# `path=STORE`, every redirect silently kept writing the import-time file, and
# the harness reported a clean redirect. Grep for `=MAX_AGE_S)` before trusting
# any knob on this module.
write_dump(PATH, REF, age_s=1.5, min_interval_ms=50)
check("a 1.5s-old frame is stale at the shipped floor",
      frame_dump.read_frame(PATH) is None)
_floor = frame_dump.MAX_AGE_S
frame_dump.MAX_AGE_S = 3.0
try:
    _widened = frame_dump.read_frame(PATH)
finally:
    frame_dump.MAX_AGE_S = _floor
check("rebinding frame_dump.MAX_AGE_S actually takes effect (no bound default)",
      _widened is not None,
      "MAX_AGE_S 3.0 must admit a 1.5s frame; if this fails, max_age_s is "
      "captured at import")
check("...and restoring it puts the gate back (the control)",
      frame_dump.read_frame(PATH) is None)

# An explicit argument still wins over both, which is what the seam is for.
check("an explicit max_age_s overrides the derived gate",
      frame_dump.read_frame(PATH, max_age_s=5.0) is not None)

# ---------------------------------------------------------------------------
# (h) the OLD header layout is refused rather than parsed leniently
# ---------------------------------------------------------------------------
# Version 1 was 128 bytes. A reader that shrugged at the version would parse
# every field up to `dropped` correctly and then read push_us as `reserved` --
# plausible numbers and no error, which is the whole failure the version field
# exists to stop.
write_dump(PATH, REF, version=1)
check("a version-1 (128-byte) dump is refused by this version-2 reader",
      frame_dump.read_frame(PATH) is None,
      "this reader is version %d" % frame_dump.VERSION)

# ---------------------------------------------------------------------------
# (i) stats() surfaces the cost and the throttle, which the doctor prints
# ---------------------------------------------------------------------------
write_dump(PATH, REF, push_us=4321, min_interval_ms=50)
_st = frame_dump.stats(PATH)
check("stats() reports the writer's measured push cost and its throttle",
      _st is not None and _st["push_us"] == 4321
      and _st["min_interval_ms"] == 50 and _st["age_limit_s"] == 0.5,
      "%s" % ({k: _st[k] for k in ("push_us", "min_interval_ms", "age_limit_s")}
              if _st else None))

# ---------------------------------------------------------------------------
# (d) fast_capture prefers the dump, and falls back without it
# ---------------------------------------------------------------------------
compass.FRAME_DUMP_PATH = PATH      # what production leaves None; see above
compass._MSS = object()             # the window path must not build an mss
_rect_calls = []


class _StubIC:
    @staticmethod
    def game_window_rect():
        _rect_calls.append(1)
        return None


sys.modules["input_controller"] = _StubIC

img = compass.fast_capture()
check("fast_capture serves the DUMP when it is fresh",
      img is not None and img.size == (W, H) and maxdiff(img, REF) <= TOL)
check("...without ever asking for the window rect",
      not _rect_calls, "%d call(s)" % len(_rect_calls))
check("...and marks it game_only like the screen path does",
      bool(img.info.get("game_only")))
# tools/doctor.py prints WHICH PATH served the frame off this mark. Without it
# the doctor would print "the SCREEN" on a healthy dump -- a status line that is
# always the same word, which is worse than no line.
check("...and marks it as having come from the DUMP, which the doctor prints",
      bool(img.info.get("frame_dump")))

os.remove(PATH)
frame_dump._MAPS.clear()
raised = None
try:
    compass.fast_capture()
except Exception as exc:
    raised = exc
check("no dump falls back to the window path (which then refuses, as today)",
      type(raised).__name__ == "NoGameWindow", repr(raised))
check("...and the fallback really went through game_window_rect",
      len(_rect_calls) == 1, "%d call(s)" % len(_rect_calls))

# The flag is the off switch, and it must actually switch off.
write_dump(PATH, REF)
compass.USE_FRAME_DUMP = False
raised = None
try:
    compass.fast_capture()
except Exception as exc:
    raised = exc
compass.USE_FRAME_DUMP = True
check("USE_FRAME_DUMP=False skips the dump entirely",
      type(raised).__name__ == "NoGameWindow", repr(raised))

compass.FRAME_DUMP_PATH = None
try:
    os.remove(PATH)
except OSError:
    pass

# ---------------------------------------------------------------------------
# (j) game_capture.grab() must NOT hand back the user's desktop
# ---------------------------------------------------------------------------
# grab()'s last resort is pyautogui.screenshot(), which grabs the PRIMARY
# DISPLAY. That was a degraded fallback while "the window is missing" meant
# something had gone wrong; this patch makes it the NORMAL state, because its
# entire purpose is that the user can work on another macOS Space while a batch
# runs. In that state the fallback is guaranteed to return a picture of the
# user's own desktop and label it "the game's pixels" -- the incident
# game_capture.py's own docstring is about (247 frames of the user's actual work
# written to disk). Two callers reach it with no focus recovery first:
# orchestrator._fast_grab, which read_balance_from_pause_menu uses on the $50
# money path, and _screenshot_logger_loop.
import game_capture

_shots = []


class _StubPyAutoGui:
    @staticmethod
    def screenshot():
        _shots.append(1)
        from PIL import Image
        return Image.new("RGB", (2560, 1600), (7, 7, 7))   # a laptop display


sys.modules["pyautogui"] = _StubPyAutoGui
_real_fast_capture = compass.fast_capture


def _no_window():
    raise compass.NoGameWindow("the window is on another Space")


compass.fast_capture = _no_window
try:
    got = game_capture.grab()
finally:
    compass.fast_capture = _real_fast_capture
check("grab() returns None when the game window is off-Space", got is None,
      repr(got))
check("...without ever grabbing the whole display",
      not _shots, "%d screenshot(s) of the primary display" % len(_shots))

# THE CONTROL, and it is what keeps this from being a blanket deletion: the
# fallback still exists for the failure it was written for -- a broken compass
# import, a dead mss -- where nothing says the display is the wrong one.
def _other_failure():
    raise RuntimeError("mss is broken")


compass.fast_capture = _other_failure
try:
    got = game_capture.grab()
finally:
    compass.fast_capture = _real_fast_capture
check("...but any OTHER failure still falls back, as it always did",
      got is not None and len(_shots) == 1,
      "%r, %d screenshot(s)" % (type(got).__name__, len(_shots)))

print("\nall green" if ok else "\nFAILED")
sys.exit(0 if ok else 1)
