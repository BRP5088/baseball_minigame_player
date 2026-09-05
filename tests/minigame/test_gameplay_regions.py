"""Self-check for crop_gameplay_regions()/GAMEPLAY_REGIONS_FRAC against a
real screenshot — no live capture, no API call."""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import io
import os

from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import GAMEPLAY_REGIONS_FRAC, crop_gameplay_regions

SRC_DIR = "Photos to train on"
src_name = next(f for f in os.listdir(SRC_DIR) if "9.49" in f)
img = Image.open(os.path.join(SRC_DIR, src_name))

crops = crop_gameplay_regions(img)
labels = [label for label, _ in crops]
assert labels == list(GAMEPLAY_REGIONS_FRAC.keys())
for label, crop in crops:
    assert crop.width > 0 and crop.height > 0, f"{label} cropped to zero size"


def jpeg_size(im, q=85):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=q)
    return len(buf.getvalue())


full_bytes = jpeg_size(img)
crop_bytes = sum(jpeg_size(c) for _, c in crops)
assert crop_bytes < full_bytes * 0.5, (
    f"crops ({crop_bytes} bytes) should be well under half the full frame ({full_bytes} bytes)"
)

print(f"OK: 5 regions cropped correctly, combined JPEG size {crop_bytes/1024:.1f}KB "
      f"vs full-frame {full_bytes/1024:.1f}KB ({100*crop_bytes/full_bytes:.0f}%)")


# --- Input-prompt detector (audit-only signal) ----------------------------
# Locked against the frames the region was measured on, so a crop-geometry
# change can't silently turn the signal into noise. It drives no decision yet,
# but it IS logged into the diagnostic bundle, and a detector that quietly
# started reading card art would make that log actively misleading.
import glob

from PIL import Image

from orchestrator import (INPUT_PROMPT_REGION, INPUT_PROMPT_THRESHOLD,
                          input_prompt_visible)

# Recaptured 2026-09-01: the original 2026-08-24 frames were pruned with their
# run folder, which left this block raising SystemExit — the detector has had
# no coverage since. Chosen by LOOKING at them, not by asking the detector:
# each "visible" frame is a gameplay turn (scoreboard, hand of five, and the
# words "PLAY" beside the triangle glyph legible in the crop), and each
# "absent" frame reads "BANNED CARDS 0/3", which is the case the region comment
# warns about — there the PLAY prompt rides the cursor, so a fixed crop lands
# on card art and must NOT count as a prompt.
_PROMPT_VISIBLE = ["20260828_140623_689.jpg", "20260828_140652_622.jpg",
                   "20260828_140708_034.jpg"]
_PROMPT_ABSENT = ["20260828_140309_081.jpg", "20260828_140315_271.jpg"]

_prompt_fail = []
# COUNT what is actually checked, and fail loudly on a missing fixture.
# `if os.path.exists(_p) and ...` turned an absent frame into a pass, and the
# summary printed len(_PROMPT_VISIBLE) — the length of the INTENDED list, not
# the number examined. QA ran this file in a copy with no screenshot_log/ at
# all and it printed "3 visible detected, 2 ban screens correctly ignored"
# having opened none of the five files (2026-08-26).
_checked_visible = _checked_absent = 0
_missing = []

for _f in _PROMPT_VISIBLE:
    _p = os.path.join("test_fixtures", "prompt_detector", _f)
    if not os.path.exists(_p):
        _missing.append(_f)
        continue
    _checked_visible += 1
    if not input_prompt_visible(Image.open(_p)):
        _prompt_fail.append(f"{_f}: PLAY prompt is visible but not detected")
for _f in _PROMPT_ABSENT:
    _p = os.path.join("test_fixtures", "prompt_detector", _f)
    if not os.path.exists(_p):
        _missing.append(_f)
        continue
    _checked_absent += 1
    # Ban screens: the same "PLAY" text exists but rides the moving cursor, so
    # the FIXED gameplay box must not fire on them.
    if input_prompt_visible(Image.open(_p)):
        _prompt_fail.append(f"{_f}: fired on a ban screen — the fixed box is "
                            "only valid for gameplay turns")

if _missing:
    raise SystemExit(
        f"{len(_missing)} prompt-detector fixture(s) missing: {_missing}. This "
        "test must not silently skip — a skipped detector test reports success "
        "on zero frames, which is how it went unnoticed.")
if _prompt_fail:
    for _m in _prompt_fail:
        print(f"FAIL: {_m}")
    raise SystemExit(f"{len(_prompt_fail)} input-prompt detector failure(s)")
assert _checked_visible == len(_PROMPT_VISIBLE) and _checked_absent == len(_PROMPT_ABSENT)
print(f"OK: input-prompt detector — {_checked_visible} visible detected, "
      f"{_checked_absent} ban screens correctly ignored "
      f"(region={INPUT_PROMPT_REGION}, thr={INPUT_PROMPT_THRESHOLD})")


# --- Run-folder pruning must never reach the calibration corpus ----------
# The logger writes ~4.6 GB per run and nothing used to remove old run folders.
# Pruning them is right; pruning the loose *.jpg at the top of screenshot_log/
# would be a disaster — every settle, reveal and lock threshold in orchestrator
# was measured against those frames, and test_ocr_ban_card, test_ban_scan and
# this file reference specific ones by name. Deleting them would silently
# invalidate the calibration record AND turn several tests into no-ops.
import re as _re
import shutil as _shutil
import tempfile as _tf

import orchestrator as _o3

_sandbox = _tf.mkdtemp(prefix="screenshot-prune-test-")
_orig_dir = _o3.SCREENSHOT_LOG_DIR
try:
    _o3.SCREENSHOT_LOG_DIR = _sandbox
    # Loose frames standing in for the calibration corpus.
    _corpus = ["20260824_200458_664.jpg", "20260825_165900_331.jpg"]
    for _f in _corpus:
        open(os.path.join(_sandbox, _f), "w").close()
    # Plus more run folders than the keep limit.
    _made = []
    for _i in range(_o3.SCREENSHOT_KEEP_RUNS + 3):
        _d = os.path.join(_sandbox, f"run_2026080{_i + 1}_120000")
        os.makedirs(_d, exist_ok=True)
        open(os.path.join(_d, "frame.jpg"), "w").close()
        _made.append(os.path.basename(_d))

    _o3._prune_old_run_folders()

    _left_files = sorted(f for f in os.listdir(_sandbox) if f.endswith(".jpg"))
    assert _left_files == sorted(_corpus), (
        f"pruning removed calibration frames: expected {sorted(_corpus)}, "
        f"found {_left_files}. Those frames ARE the calibration record — every "
        "threshold in orchestrator was measured against them.")

    _left_runs = sorted(d for d in os.listdir(_sandbox) if d.startswith("run_"))
    assert len(_left_runs) == _o3.SCREENSHOT_KEEP_RUNS, (
        f"kept {len(_left_runs)} run folders, expected "
        f"{_o3.SCREENSHOT_KEEP_RUNS} — unbounded growth is ~4.6 GB per run")
    assert _left_runs == _made[-_o3.SCREENSHOT_KEEP_RUNS:], (
        f"kept the wrong run folders: {_left_runs}; the MOST RECENT should "
        "survive, since those are the ones a post-mortem needs")
finally:
    _o3.SCREENSHOT_LOG_DIR = _orig_dir
    _shutil.rmtree(_sandbox, ignore_errors=True)

print(f"OK: run-folder pruning keeps the {_o3.SCREENSHOT_KEEP_RUNS} most recent "
      "and cannot touch the loose calibration corpus")
