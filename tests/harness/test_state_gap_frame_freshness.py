"""Skeptic finding on `_save_state_gap` (gap-frames-r2, round 2): the round-1
test (test_state_gap_frames.py) drives `_save_state_gap` directly, injecting
`_LAST_GAP_FRAME` by hand -- so it never caught that `local_game_state()`
itself (orchestrator.py, just above `_save_state_gap`) left `_LAST_GAP_FRAME`
UNCLEARED across calls. Two of its `(None, gap)` returns -- "local_state
unavailable (...)" and "could not capture (...)" -- fire BEFORE a frame is
ever grabbed for THIS call. Left uncleared, a later gap of that shape would
save the PREVIOUS call's frame under the CURRENT gap's name: a stale frame
mislabelled as evidence for a different failure.

This test drives the real `local_game_state()`, not a copy of its logic:
`_fast_grab` is stubbed to return a known image and the result/ban readers
are stubbed to decline, so the call runs the real function through to a real
gap with a real frame in hand -- then a second call is made whose grab fails,
and it must save NOTHING from the first call.
"""
import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import local_state
import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def _image_hash(img):
    return hashlib.sha256(img.convert("RGB").tobytes()).hexdigest()


def _latest_gap_dir():
    dirs = sorted(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    return dirs[-1] if dirs else None


# Same isolation as test_state_gap_frames.py: redirect STATE_GAP_DIR to a temp
# root for the whole file and restore everything in a finally.
_real_dir = o.STATE_GAP_DIR
o.STATE_GAP_DIR = tempfile.mkdtemp(prefix="state_gap_fresh_test_")
_saved_flag = o.STATE_GAP_FRAMES_IN_TESTS
_saved_cap = o.STATE_GAP_MAX_DIRS
_saved_grab = o._fast_grab
_saved_crop = o.crop_gameplay_regions
_saved_ban = o.read_ban_counter
_saved_read_result = local_state.read_result
_saved_local_state_module = sys.modules.get("local_state")

KNOWN_IMAGE = Image.new("RGB", (17, 13), (5, 99, 200))

try:
    o.STATE_GAP_FRAMES_IN_TESTS = True

    # ------------------------------------------------------------------
    # 1) A REAL call, through local_game_state(), that captures a known
    #    frame and then declines every reader down to "no hand crop".
    # ------------------------------------------------------------------
    o._fast_grab = lambda: KNOWN_IMAGE
    o.crop_gameplay_regions = lambda full: []  # no "hand" key -> "no hand crop"
    o.read_ban_counter = lambda img: None      # decline
    local_state.read_result = lambda full: {"is_result": False}  # decline

    st, gap = o.local_game_state()
    check(st is None and gap == "no hand crop",
          f"first call reaches the expected gap (got st={st!r} gap={gap!r})")
    check(o._LAST_GAP_FRAME is KNOWN_IMAGE,
          "local_game_state stashed the frame it actually grabbed")

    before = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    out1 = o._save_state_gap(gap, turns_this_half=2)
    new1 = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*"))) - before
    check(len(new1) == 1 and out1 in new1, "the first gap writes exactly one dir")
    if out1:
        frame_path = os.path.join(out1, "frame.png")
        check(os.path.exists(frame_path), "...with a frame.png")
        if os.path.exists(frame_path):
            saved = Image.open(frame_path)
            check(_image_hash(saved) == _image_hash(KNOWN_IMAGE),
                  "...and frame.png IS the frame local_game_state actually grabbed")
        why_path = os.path.join(out1, "why.json")
        with open(why_path) as fh:
            why1 = json.load(fh)
        check(why1.get("frame") == "frame.png",
              "...and why.json names it")

    # ------------------------------------------------------------------
    # 2) THE REGRESSION: a following call whose grab fails must NOT save
    #    the previous call's frame under its own (different) gap.
    # ------------------------------------------------------------------
    def _boom():
        raise RuntimeError("stream down")
    o._fast_grab = _boom

    st2, gap2 = o.local_game_state()
    check(st2 is None and gap2 == "could not capture (stream down)",
          f"second call hits the pre-stash gap (got st={st2!r} gap={gap2!r})")
    check(o._LAST_GAP_FRAME is None,
          "...and local_game_state cleared _LAST_GAP_FRAME before failing, "
          "not carrying the previous frame forward")

    before2 = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    out2 = o._save_state_gap(gap2, turns_this_half=2)
    new2 = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*"))) - before2
    check(len(new2) == 1 and out2 in new2, "the second gap writes its own dir")
    if out2:
        check(not os.path.exists(os.path.join(out2, "frame.png")),
              "...with NO frame.png -- the stale frame from call 1 was not reused")
        why_path2 = os.path.join(out2, "why.json")
        check(os.path.exists(why_path2), "...but a why.json still exists")
        if os.path.exists(why_path2):
            with open(why_path2) as fh:
                why2 = json.load(fh)
            check("frame" in why2 and why2["frame"] is None,
                  '...naming the gap with "frame": null, not silence')
            check(why2.get("gap") == "could not capture (stream down)",
                  "...and the gap text")

    # ------------------------------------------------------------------
    # 3) THE OTHER pre-stash path: "local_state unavailable". Force the
    #    `import local_state` inside local_game_state to fail by poisoning
    #    sys.modules (the standard way to make an import raise ImportError),
    #    and confirm it also produces a why-only record, never a stale frame.
    # ------------------------------------------------------------------
    o._fast_grab = lambda: KNOWN_IMAGE  # would succeed if reached -- it must not be
    sys.modules["local_state"] = None
    try:
        st3, gap3 = o.local_game_state()
    finally:
        sys.modules["local_state"] = _saved_local_state_module
    check(st3 is None and gap3.startswith("local_state unavailable"),
          f"third call hits the import-failure gap (got st={st3!r} gap={gap3!r})")
    check(o._LAST_GAP_FRAME is None,
          "...with _LAST_GAP_FRAME cleared, not the frame from call 1")

    before3 = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    out3 = o._save_state_gap(gap3, turns_this_half=2)
    new3 = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*"))) - before3
    check(len(new3) == 1 and out3 in new3, "the third gap writes its own dir")
    if out3:
        check(not os.path.exists(os.path.join(out3, "frame.png")),
              "...with NO frame.png here either")
        why_path3 = os.path.join(out3, "why.json")
        if os.path.exists(why_path3):
            with open(why_path3) as fh:
                why3 = json.load(fh)
            check("frame" in why3 and why3["frame"] is None,
                  '...naming the gap with "frame": null too')
finally:
    o.STATE_GAP_FRAMES_IN_TESTS = _saved_flag
    o.STATE_GAP_MAX_DIRS = _saved_cap
    o._fast_grab = _saved_grab
    o.crop_gameplay_regions = _saved_crop
    o.read_ban_counter = _saved_ban
    local_state.read_result = _saved_read_result
    sys.modules["local_state"] = _saved_local_state_module
    o._LAST_GAP_FRAME = None
    shutil.rmtree(o.STATE_GAP_DIR, ignore_errors=True)
    o.STATE_GAP_DIR = _real_dir

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("ALL PASSED")
