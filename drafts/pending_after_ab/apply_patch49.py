"""patch49: capture the DECODED FRAME chiaki already has, not the screen.

THE FAILURE. Every capture goes through compass.fast_capture() ->
input_controller.game_window_rect() -> mss on that rect. game_window_rect lists
ON-SCREEN windows only, so the moment the user switches macOS Spaces the chiaki
window is gone from the list, fast_capture raises NoGameWindow and whatever walk
was running dies. Six walks died that way between 10:30 and 11:05 on 2026-09-08.
A window-ID capture is NOT a way out: CGWindowListCreateImage returns nothing
for a window on an inactive Space, because macOS never composites it. The Mac
is therefore unusable for anything else while a batch runs.

THE FIX, and its other half is the C++ patch already in chiaki-patch/.
chiaki writes each decoded frame into a memory-mapped file (opt-in, on
CHIAKI_FRAME_DUMP, ~20Hz, packed NV12 or I420, a two-counter seqlock for
tearing -- the format is specified at the top of chiaki-patch/framedump.h and
static_asserted on the C++ side). This patch adds the reader and puts it FIRST
in fast_capture. No window, no Space, no compositor -- and cheaper than the
screen grab it replaces.

IT IS A FALLBACK, NOT A REPLACEMENT. read_frame() returns None whenever it
cannot hand back a frame it is sure of -- no file, wrong magic, no frame
written yet, a torn read that survived its retries, or a timestamp older than
max_age_s -- and fast_capture then runs today's window path completely
unchanged. A stale dump means the stream is not producing frames, which is
exactly what the callers already treat NoGameWindow as.

WHAT CHANGES DOWNSTREAM, and it is worth knowing before this ships: the dump is
always the stream's own geometry (1920x1080), while the screen path has
returned both 1867x1050 and 1920x1080 in different sessions (CLAUDE.md 3,
"Capture geometry changes under you"). Everything that crops by FRACTION is
unaffected; anything holding absolute pixels was already broken by that drift.

Applies to: frame_dump.py (new), compass.py, restart_chiaki.sh, tools/doctor.py,
tests/rig/test_frame_dump.py (new).

Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch49.py [ROOT]
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

FRAME_DUMP = os.path.join(ROOT, "frame_dump.py")
COMPASS = os.path.join(ROOT, "compass.py")
GAME_CAPTURE = os.path.join(ROOT, "game_capture.py")
RESTART = os.path.join(ROOT, "restart_chiaki.sh")
DOCTOR = os.path.join(ROOT, "tools", "doctor.py")
TEST = os.path.join(ROOT, "tests", "rig", "test_frame_dump.py")

# ---------------------------------------------------------------------------
# THE NEW MODULE
# ---------------------------------------------------------------------------
FRAME_DUMP_SRC = r'''"""Read the frames chiaki decoded, out of shared memory.

WHY THIS EXISTS
---------------
`compass.fast_capture()` grabs chiaki's WINDOW off the screen, which needs the
window to be composited on the CURRENT macOS Space. Switch Spaces and
`input_controller.game_window_rect()` -- which lists ON-SCREEN windows only --
returns None, fast_capture raises NoGameWindow, and any walk in progress dies.
Six died that way inside thirty-five minutes on 2026-09-08. Capturing by window
ID instead does not help: macOS does not composite a window on an inactive
Space, so CGWindowListCreateImage hands back nothing.

So the frame is taken from where it already exists: chiaki's own decoder. The
patched build (chiaki-patch/framedump.{h,cpp}) writes each decoded frame into a
memory-mapped file, and this module reads it. No window, no Space, no
compositor -- and a memcpy plus one colour conversion instead of a screen grab.

THE FILE FORMAT is specified at the top of `chiaki-patch/framedump.h`, which is
the authority; the C++ side static_asserts every offset the struct below
unpacks. A 4096-byte header, then ONE frame slot holding the planes PACKED
(each plane's stride equals its width), which is exactly the layout cv2 wants.

TEARING: a two-counter seqlock. The writer stores `seq_before`, writes the
pixels, then stores `seq_after`. A reader latches `seq_after`, copies, then
reads `seq_before`; the copy is consistent only if the two agree. If the writer
started a new frame mid-copy, `seq_before` has run ahead and the mismatch is
caught. At ~20Hz writes against a ~2ms read a retry is already rare.

TIME: the header's `timestamp_ns` is CLOCK_REALTIME on the C++ side, i.e. UNIX
epoch nanoseconds -- the same quantity `time.time_ns()` returns here. That is
deliberate, and the alternative was worse: macOS has three monotonic clocks and
CPython has changed which one `time.monotonic()` rides, so a monotonic
comparison across two processes would be an assumption nobody could check from
either side. `mono_ns` is also in the header, for diagnostics only.

EVERY FAILURE IS None. No file, wrong magic, a version this reader does not
know, no frame written yet, a torn read that survived its retries, a size that
does not match the format, an unreadable payload -- all None, and the caller
falls back to the screen path. There is no half-answer: a frame that is not
provably the current one is worth less than nothing, because nothing downstream
can tell.
"""
import os
import struct
import time

# Must match restart_chiaki.sh's CHIAKI_FRAME_DUMP and nothing else. A runtime
# mmap in /tmp is fine -- CLAUDE.md's "nothing that matters goes in /tmp" is
# about source and findings, and this file is regenerated every launch.
DEFAULT_PATH = "/tmp/chiaki_frame.bin"

MAGIC = b"CHFD"
# 2 (2026-09-08): the header grew push_us and min_interval_ms and went from 128
# to 136 bytes. A reader built for version 1 would parse every field up to
# `dropped` correctly and then read push_us as `reserved` -- plausible numbers,
# no error, which is exactly the failure the version field exists to stop. So
# an unknown version is refused rather than parsed leniently.
VERSION = 2

# Our own small numbers, not AVPixelFormat values: those are an ffmpeg internal
# enumeration that has been renumbered between major versions.
FMT_NV12 = 1
FMT_I420 = 2

DATA_OFFSET = 4096

# <4sI  magic, version
# QQ    seq_before, seq_after
# IIII  width, height, pix_fmt, n_planes
# 4I    stride[4]
# 4I    plane_offset[4]
# QQQQQ frame_bytes, timestamp_ns, mono_ns, data_offset, data_capacity
# IIIIII dropped, color_space, color_range, push_us, min_interval_ms, reserved
#
# Every offset here is static_asserted on the C++ side (framedump.cpp), which
# is the only thing keeping two languages' idea of this layout in step.
HEADER = struct.Struct("<4sIQQIIII4I4IQQQQQIIIIII")
assert HEADER.size == 136, HEADER.size

# THE FLOOR ON HOW OLD A FRAME MAY BE. Not the whole gate: the writer records
# its OWN throttle in the header as min_interval_ms, and `age_limit()` below
# takes the larger of this and AGE_MARGIN intervals. This used to be a bare 0.5
# justified by a comment that hard-coded the C++'s 50ms -- a constant mirrored
# by hand across two languages, which is the RELEASE_MS bug CLAUDE.md 5 records
# (the mirror went stale, the check went vacuous, and nothing failed until it
# mattered). Above the limit the answer is None, which the callers must treat
# exactly as they treat NoGameWindow today: the stream is not producing frames.
MAX_AGE_S = 0.5

# How many of the writer's own dump intervals a frame may be behind before it
# is stale. Ten, so a couple of missed dumps are not a failure, and derived
# from the writer's number rather than a copy of it.
AGE_MARGIN = 10

# A torn read costs a retry, not an answer. Three is generous against a writer
# that touches the slot 20 times a second.
READ_RETRIES = 3

# Cached mappings, keyed by (path, inode, size). Re-mmapping per call is only
# tens of microseconds, but the stat that validates the cache is what notices a
# file that was deleted and recreated under us -- which is what a chiaki
# restart with a different build would do.
_MAPS = {}


def dump_path(path=None):
    """The dump to read: the argument, then the environment, then the default.

    None when no path was given AND this is an offline test run -- see
    `_test_run` below.
    """
    if path:
        return path
    if _test_run():
        return None
    return os.environ.get("CHIAKI_FRAME_DUMP") or DEFAULT_PATH


def _test_run():
    """True inside the offline suite.

    WHY THE SUITE MUST NOT SEE THE LIVE DUMP. tests/rig/test_no_game_window.py
    stubs game_window_rect to None and requires fast_capture to RAISE; with a
    real chiaki streaming on this machine the dump would hand it a real frame
    and the test would fail -- or, worse, pass or fail depending on whether the
    console happened to be awake. An offline check whose answer depends on the
    rig is not a check. Same reasoning, and the same flag, as the hard stick-
    injection lockout and the suppressed calibration-cache writes.

    A CALLER THAT NAMES A PATH IS ALWAYS OBEYED: this gate is about the DEFAULT
    and the environment, i.e. about stumbling onto the live rig's file, never
    about a file a test wrote itself.

    READ AT CALL TIME, NEVER CAPTURED AT IMPORT. tools/prompt_ocr_ab.py set
    this flag at module level for its own offline run, overnight/prompt_zone.py
    imported it after walking a leg, and from that import every stick send was
    dropped in silence -- three runs of "measurements" of a character that
    never moved (CLAUDE.md 5).
    """
    return bool(os.environ.get("BASEBALL_TEST_RUN"))


def age_limit(hdr):
    """How old this writer's frames may get, in seconds.

    Derived from the writer's own throttle where it reports one, so the two
    sides cannot drift apart; MAX_AGE_S is the floor, so a writer that dumped
    every millisecond could not shrink the gate to something a scheduling
    hiccup would trip.
    """
    ms = hdr.get("min_interval_ms") or 0
    return max(MAX_AGE_S, AGE_MARGIN * ms / 1000.0)


def _planes_are_packed(hdr):
    """Does the writer's DECLARED layout match the one cv2 can consume?

    THE POINT IS THAT THIS READS THE HEADER RATHER THAN ASSUMING. framedump.cpp
    records stride[] and plane_offset[] with a comment saying it does so "so a
    reader that derives them instead of reading them is not a second copy of
    this arithmetic that nothing keeps in step" -- and the first version of this
    module derived them anyway and never looked. That is correct exactly while
    the C++ passes align=1 to av_image_copy_to_buffer; change that one argument
    and the planes gain padding, the reshape below shears the picture by a few
    pixels per row, and NOTHING raises. cv2's NV12/I420 conversions cannot take
    strides at all, so the only safe answer to a non-packed dump is to refuse
    it and let the caller fall back to the screen.
    """
    w, h = hdr["width"], hdr["height"]
    s, off = hdr["stride"], hdr["plane_offset"]
    if hdr["pix_fmt"] == FMT_NV12:
        return (hdr["n_planes"] == 2
                and s[0] == w and s[1] == w
                and off[0] == 0 and off[1] == w * h)
    return (hdr["n_planes"] == 3
            and s[0] == w and s[1] == w // 2 and s[2] == w // 2
            and off[0] == 0 and off[1] == w * h
            and off[2] == w * h + (w // 2) * (h // 2))


def _mapping(path):
    """An mmap of `path`, or None. Remapped when the file underneath changes."""
    import mmap
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_ino, st.st_size)
    hit = _MAPS.get(path)
    if hit is not None:
        if hit[0] == key:
            return hit[1]
        try:
            hit[1].close()
        except Exception:
            pass
        _MAPS.pop(path, None)
    if st.st_size < DATA_OFFSET + HEADER.size:
        return None
    try:
        fh = open(path, "rb")
    except OSError:
        return None
    try:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        fh.close()
        return None
    finally:
        # The mapping keeps the file alive; the descriptor is not needed.
        try:
            fh.close()
        except Exception:
            pass
    _MAPS[path] = (key, mm)
    return mm


def _snapshot(buf):
    """One attempt at a CONSISTENT read of `buf`.

    Returns (header_fields, payload_bytes) or None. None means "try again" for
    a torn read and "give up" for anything structurally wrong -- the caller
    cannot tell the two apart and does not need to, because both end at the
    screen fallback if they persist.
    """
    try:
        (magic, version, seq_before, seq_after,
         width, height, pix_fmt, n_planes,
         s0, s1, s2, s3, p0, p1, p2, p3,
         frame_bytes, timestamp_ns, mono_ns,
         data_offset, data_capacity, dropped,
         color_space, color_range, push_us, min_interval_ms,
         _res) = HEADER.unpack_from(buf, 0)
    except struct.error:
        return None
    if magic != MAGIC or version != VERSION:
        return None
    # seq 0 is the header the writer publishes at startup: the file is ours and
    # well formed, and no frame has been written into it yet.
    if seq_after == 0:
        return None
    if pix_fmt not in (FMT_NV12, FMT_I420):
        return None
    if width <= 0 or height <= 0 or (width % 2) or (height % 2):
        return None
    if frame_bytes != width * height * 3 // 2:
        return None
    if data_offset != DATA_OFFSET or frame_bytes > data_capacity:
        return None
    if len(buf) < data_offset + frame_bytes:
        return None
    # THE WRITER'S OWN STRIDES, CHECKED RATHER THAN ASSUMED. See
    # _planes_are_packed: a dump whose planes are padded cannot be reshaped for
    # cv2, and reshaping it anyway shears the picture with no error at all.
    _hdr_layout = {"width": width, "height": height, "pix_fmt": pix_fmt,
                   "n_planes": n_planes, "stride": (s0, s1, s2, s3),
                   "plane_offset": (p0, p1, p2, p3)}
    if not _planes_are_packed(_hdr_layout):
        return None

    payload = buf[data_offset:data_offset + frame_bytes]

    # THE SEQ RE-READ IS THE WHOLE POINT and must happen AFTER the copy. Reading
    # it before would compare two numbers taken at the same instant and prove
    # nothing about the bytes in between.
    try:
        seq_before_again = HEADER.unpack_from(buf, 0)[2]
    except struct.error:
        return None
    if seq_before_again != seq_after:
        return None

    return ({"seq": seq_after, "width": width, "height": height,
             "pix_fmt": pix_fmt, "frame_bytes": frame_bytes,
             "timestamp_ns": timestamp_ns, "mono_ns": mono_ns,
             "dropped": dropped, "color_space": color_space,
             "color_range": color_range, "push_us": push_us,
             "min_interval_ms": min_interval_ms,
             "stride": (s0, s1, s2, s3),
             "plane_offset": (p0, p1, p2, p3),
             "n_planes": n_planes}, payload)


def _to_image(hdr, payload):
    """Packed NV12/I420 bytes -> an RGB PIL Image, or None.

    THE COLOUR MATRIX IS BT.601 LIMITED RANGE, because that is what cv2's
    COLOR_YUV2RGB_NV12/I420 do and there is no BT.709 variant of them. A PS5
    1080p stream is usually BT.709, so a dump frame and a screen grab of the
    same moment are not bit-identical. On this game's near-monochrome art the
    difference should be small -- SHOULD BE is not a measurement, so the header
    carries the decoder's own colorspace and color_range (read them with
    stats()) and swap_chiaki_framedump.sh compares a dump frame against a
    simultaneous screen grab on the rig. If that difference turns out to matter
    to any detector, the fix is a matrix here, not a threshold there.
    """
    import numpy as np
    import cv2
    from PIL import Image

    w, h = hdr["width"], hdr["height"]
    try:
        yuv = np.frombuffer(payload, dtype=np.uint8).reshape(h * 3 // 2, w)
    except ValueError:
        return None
    code = (cv2.COLOR_YUV2RGB_NV12 if hdr["pix_fmt"] == FMT_NV12
            else cv2.COLOR_YUV2RGB_I420)
    try:
        rgb = cv2.cvtColor(yuv, code)
    except Exception:
        return None
    return Image.fromarray(rgb)


def read_frame(path=None, max_age_s=None, now_ns=None):
    """The newest decoded frame as an RGB PIL Image, or None.

    None whenever the frame cannot be vouched for. `now_ns` is a seam for the
    tests; production passes nothing and the wall clock is used.

    `max_age_s` DEFAULTS TO None AND IS RESOLVED AT CALL TIME, deliberately.
    Written the obvious way -- `max_age_s=MAX_AGE_S` -- the module constant is
    captured when the `def` runs, so `frame_dump.MAX_AGE_S = 2.0` from a test or
    an A/B arm would change nothing and report nothing. That is CLAUDE.md
    10.18's bug exactly: leg_reliability declared `path=STORE` and every
    redirect silently kept writing the import-time file, while the harness
    reported a clean one. None here means "ask age_limit(), which reads the
    writer's own throttle out of the header".
    """
    p = dump_path(path)
    if p is None:
        return None
    buf = _mapping(p)
    if buf is None:
        return None

    snap = None
    for _ in range(READ_RETRIES + 1):
        snap = _snapshot(buf)
        if snap is not None:
            break
    if snap is None:
        return None
    hdr, payload = snap

    # STALENESS IS CHECKED ON THE VERIFIED SNAPSHOT, not on a header read
    # earlier: a torn header can carry a plausible timestamp, and bailing on it
    # would throw away a frame that was actually fine.
    now = time.time_ns() if now_ns is None else now_ns
    age_s = (now - hdr["timestamp_ns"]) / 1e9
    limit = age_limit(hdr) if max_age_s is None else max_age_s
    # A timestamp in the FUTURE is rejected too. It means the two processes do
    # not share a clock (a corrupt header, someone else's file at this path),
    # and "impossibly fresh" must never read as fresh.
    if age_s > limit or age_s < -1.0:
        return None

    return _to_image(hdr, payload)


def stats(path=None):
    """Header fields without decoding the pixels. Diagnostics only."""
    p = dump_path(path)
    if p is None:
        return None
    buf = _mapping(p)
    if buf is None:
        return None
    snap = _snapshot(buf)
    if snap is None:
        return None
    hdr = dict(snap[0])
    hdr["path"] = p
    hdr["age_s"] = (time.time_ns() - hdr["timestamp_ns"]) / 1e9
    # The gate this frame would actually be judged against, so the doctor prints
    # the number in force rather than the module's floor.
    hdr["age_limit_s"] = age_limit(hdr)
    return hdr
'''

# ---------------------------------------------------------------------------
# THE TEST
# ---------------------------------------------------------------------------
TEST_SRC = r'''"""frame_dump.read_frame, and fast_capture preferring it. OFFLINE.

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
'''

# ---------------------------------------------------------------------------
# EDITS TO EXISTING FILES
# ---------------------------------------------------------------------------
COMPASS_EDITS = [(
"""_MSS = None


class NoGameWindow(RuntimeError):
""",
"""_MSS = None

# --- THE FRAME DUMP, tried BEFORE the screen --------------------------------
#
# chiaki's patched build writes every decoded frame into a memory-mapped file
# (chiaki-patch/framedump.h). Reading that instead of grabbing the window is
# what lets a run survive the user switching macOS Spaces: game_window_rect()
# lists ON-SCREEN windows only, so a Space switch used to raise NoGameWindow
# and kill the walk -- six of them between 10:30 and 11:05 on 2026-09-08.
#
# The flag is read at CALL time, never captured in a default argument
# (CLAUDE.md 10.18), so a harness or a test can turn it off for one arm.
USE_FRAME_DUMP = True

# None means "wherever CHIAKI_FRAME_DUMP says", which is what production wants.
# A test names a file of its own here instead of pointing the environment at
# one: frame_dump.read_frame() deliberately refuses the DEFAULT path under
# BASEBALL_TEST_RUN, so that the offline suite can never be handed a frame by
# a chiaki that happens to be streaming on this machine.
FRAME_DUMP_PATH = None


def _frame_from_dump():
    \"\"\"The newest decoded frame from chiaki's mmap, or None.

    None means "fall back to the screen", and it covers every case: the patched
    build is not running, the environment variable is unset, no frame has
    arrived yet, the dump has gone stale because the stream stopped, or a read
    was torn. Nothing here ever raises -- a capture path that can fail in a new
    way is worse than one that is merely slower.
    \"\"\"
    try:
        import frame_dump
        return frame_dump.read_frame(FRAME_DUMP_PATH)
    except Exception:
        return None


class NoGameWindow(RuntimeError):
"""), (
"""    global _MSS
    import mss
    import input_controller as _ic
    if _MSS is None:
        _MSS = mss.mss()
""",
"""    # THE DUMP FIRST. It is the same 1920x1080 game frame the window path
    # produces after cropping the letterbox, so every fraction taken from it
    # means what it meant before, and nothing downstream changes. When it
    # returns None the window path below runs exactly as it always has.
    if USE_FRAME_DUMP:
        _img = _frame_from_dump()
        if _img is not None:
            _img.info["game_only"] = True
            _img.info["frame_dump"] = True
            return _img

    global _MSS
    import mss
    import input_controller as _ic
    if _MSS is None:
        _MSS = mss.mss()
""")]

GAME_CAPTURE_EDITS = [(
"""    img = None
    try:
        import compass
        img = compass.fast_capture()
    except Exception:
        img = None
    if img is None:
""",
"""    img = None
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
"""), ]

DOCTOR_EDITS = [(
"""    print("  --- current frame ---")
""",
"""    # WHICH PATH SERVED THE FRAME. The whole point of the dump is that a
    # capture no longer needs chiaki's window to be on the current Space, so
    # "is the dump alive" is now a rig fact on the same footing as "is the
    # FIFO there" -- and when it is NOT alive, every capture is back to
    # grabbing the screen and will die at the next Space switch. Silence here
    # would make the two states look identical, which is this project's
    # signature failure.
    try:
        import frame_dump
        st = frame_dump.stats()
    except Exception as e:
        st = None
        print(f"  frame dump         unreadable ({type(e).__name__}: {e})")
    if st is not None:
        # The gate the reader would actually apply, which is derived from the
        # writer's own throttle -- not the module's floor.
        fresh = st["age_s"] <= st.get("age_limit_s", frame_dump.MAX_AGE_S)
        print(f"  frame dump         {st['path']}  {st['width']}x{st['height']} "
              f"seq {st['seq']}  age {st['age_s'] * 1000:.0f}ms"
              f"  push {st['push_us']}us"
              f"{'' if fresh else '   <- STALE; captures fall back to the screen'}")
    else:
        print(f"  frame dump         absent   <- captures grab the SCREEN, which "
              f"fails when chiaki's window leaves the current Space "
              f"(is CHIAKI_FRAME_DUMP exported? does the log say 'frame dump'?)")
    print("  --- current frame ---")
"""), (
"""    w, h = img.size
    aspect = w / h
""",
"""    w, h = img.size
    aspect = w / h
    log(f"  served by {'the frame DUMP' if img.info.get('frame_dump') else 'the SCREEN'}")
""")]

RESTART_EDITS = [(
"""CHIAKI_INJECT_INPUT=/tmp/chiaki_input nohup "$DEST" > /tmp/chiaki_run.log 2>&1 &
""",
"""# CHIAKI_FRAME_DUMP turns on the decoded-frame mmap the Python capture reads
# first (frame_dump.py). Without it every capture goes back to grabbing the
# window off the screen, which dies the moment the user switches macOS Spaces.
# A runtime mmap in /tmp is fine: it is recreated on every launch, and
# CLAUDE.md's "nothing that matters goes in /tmp" is about source and findings.
CHIAKI_INJECT_INPUT=/tmp/chiaki_input CHIAKI_FRAME_DUMP=/tmp/chiaki_frame.bin \\
    nohup "$DEST" > /tmp/chiaki_run.log 2>&1 &
"""), (
"""grep -i inject /tmp/chiaki_run.log || true
""",
"""grep -i inject /tmp/chiaki_run.log || true
# Both halves of the patch announce themselves, and a MISSING line is the whole
# point: an unpatched or half-patched binary launches, prints nothing unusual
# and delivers nothing, which is how this project lost a day to the injector.
grep -i "frame dump" /tmp/chiaki_run.log \\
    || echo "WARNING: no 'frame dump' line -- this build has no frame dump, so "\\
"every capture will grab the screen and will fail when the window leaves the Space"
"""),]


def main():
    for p in (COMPASS, RESTART, DOCTOR, GAME_CAPTURE):
        if not os.path.isfile(p):
            raise SystemExit("not a project root (%s missing): %s" % (p, ROOT))

    compass_src = open(COMPASS).read()
    restart_src = open(RESTART).read()
    doctor_src = open(DOCTOR).read()
    capture_src = open(GAME_CAPTURE).read()

    if (os.path.exists(FRAME_DUMP) or "USE_FRAME_DUMP" in compass_src
            or "CHIAKI_FRAME_DUMP" in restart_src or "frame_dump" in doctor_src
            or "missing_window" in capture_src
            or os.path.exists(TEST)):
        raise SystemExit("ALREADY APPLIED")

    # EVERY ANCHOR, BEFORE ANY WRITE. A patch script that writes one file and
    # then fails an assert on the next leaves the tree half-changed, and on
    # 2026-09-07 that killed a trial child mid-batch (CLAUDE.md 10.19).
    for a, b in COMPASS_EDITS:
        assert compass_src.count(a) == 1, ("compass anchor", a[:60], compass_src.count(a))
    for a, b in RESTART_EDITS:
        assert restart_src.count(a) == 1, ("restart anchor", a[:60], restart_src.count(a))
    for a, b in DOCTOR_EDITS:
        assert doctor_src.count(a) == 1, ("doctor anchor", a[:60], doctor_src.count(a))
    for a, b in GAME_CAPTURE_EDITS:
        assert capture_src.count(a) == 1, ("game_capture anchor", a[:60],
                                           capture_src.count(a))

    for a, b in COMPASS_EDITS:
        compass_src = compass_src.replace(a, b)
    for a, b in RESTART_EDITS:
        restart_src = restart_src.replace(a, b)
    for a, b in DOCTOR_EDITS:
        doctor_src = doctor_src.replace(a, b)
    for a, b in GAME_CAPTURE_EDITS:
        capture_src = capture_src.replace(a, b)

    ast.parse(compass_src)
    ast.parse(doctor_src)
    ast.parse(capture_src)
    ast.parse(FRAME_DUMP_SRC)
    ast.parse(TEST_SRC)

    os.makedirs(os.path.dirname(TEST), exist_ok=True)
    open(FRAME_DUMP, "w").write(FRAME_DUMP_SRC)
    open(TEST, "w").write(TEST_SRC)
    open(COMPASS, "w").write(compass_src)
    open(RESTART, "w").write(restart_src)
    open(DOCTOR, "w").write(doctor_src)
    open(GAME_CAPTURE, "w").write(capture_src)

    print("patch49 applied to", ROOT)
    print("  new  frame_dump.py")
    print("  new  tests/rig/test_frame_dump.py")
    print("  edit compass.py            (USE_FRAME_DUMP + the dump-first branch)")
    print("  edit restart_chiaki.sh     (CHIAKI_FRAME_DUMP + the log grep)")
    print("  edit tools/doctor.py       (a 'frame dump' line and which path served)")
    print("  edit game_capture.py       (no whole-display grab when the window "
          "is off-Space)")
    print("")
    print("The C++ half is already in chiaki-patch/ and chiaki-ng-src/. Installing")
    print("the new binary is a SEPARATE step and must happen at a batch boundary:")
    print("  scratchpad/swap_chiaki_framedump.sh")


if __name__ == "__main__":
    main()
