"""Read the frames chiaki decoded, out of shared memory.

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
