"""The table detector must tell BASEBALL CARDS from any other prompt.

This test exists because the previous detector could not. It measured brightness
in a fixed box, so "Wanda Fuller [] Talk" scored 0.375 against a 0.10 threshold
and a run that stopped at the wrong NPC was recorded as having reached the
table. Any detector that cannot fail this test cannot be used to count
successful runs.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import glob

from PIL import Image

import table_prompt as tp

_os.chdir(_ROOT)

POSITIVES = sorted(glob.glob("test_fixtures/table_prompt/ref*.jpg"))
NEGATIVES = sorted(glob.glob("test_fixtures/table_prompt_negative/*.jpg"))
NEGATIVE = "test_fixtures/table_prompt_negative/wanda.jpg"

if not POSITIVES:
    raise SystemExit(
        "no reference crops in test_fixtures/table_prompt/ — without them the "
        "detector cannot distinguish the baseball prompt and no run can be "
        "called a success")
if not _os.path.exists(NEGATIVE):
    raise SystemExit(
        f"missing {NEGATIVE}: the Wanda frame is the whole point of this test. "
        "It is the prompt that fooled the previous detector; without it this "
        "file only proves the detector recognises itself.")

# LEAVE ONE OUT, but testing the right property. Scoring a reference against a
# set containing itself returns exactly 1.0 and proves nothing — the first
# version of this test "passed" at a perfect 1.000 for that reason.
#
# What it must NOT demand is that every reference clears the full threshold
# without itself. The references deliberately span three traversals so that each
# covers a viewpoint the others do not, so excluding one leaves its angle
# unrepresented and its score legitimately drops. Requiring otherwise would
# force the reference set back towards a single viewpoint, which is the failure
# this diversity exists to prevent.
#
# The honest requirement is that a reference, judged without itself, is still
# more table-like than anything that is NOT the table.
_neg_ceiling = max(tp.score(Image.open(f)) for f in NEGATIVES)
for i, f in enumerate(POSITIVES):
    s = tp.score(Image.open(f), exclude=i)
    assert s > _neg_ceiling, (
        f"{f}: scored {s:.3f} without itself, below the best non-table score "
        f"({_neg_ceiling:.3f}) — it is an outlier, not a reference")

# Frames from the recording that are NOT references at all.
# Held-out frames from BOTH recordings. Using one traversal taught the
# detector a single viewing angle, and it then rejected genuine table frames
# from the other recording — including one where the prompt is plainly legible.
# FIXTURES, NOT demos/. demos/ is GITIGNORED, so this held-out set did not exist
# on a fresh clone and the assertion below could not run for anyone else. These ARE
# the frames the two filters above used to select -- the time windows and the [::40]
# stride are already applied, so re-applying them would leave almost nothing.
_held_out = sorted(glob.glob("test_fixtures/table_prompt_heldout/f_*.jpg"))
assert len(_held_out) >= 4, "not enough held-out frames to check against"
_ho = [tp.score(Image.open(f)) for f in _held_out]
assert min(_ho) >= tp.MATCH_MIN, (
    f"held-out baseball-prompt frames scored as low as {min(_ho):.3f}; the "
    "detector only recognises the exact frames it was built from")

# The frame that broke the old detector must NOT pass.
wanda = tp.score(Image.open(NEGATIVE))
assert wanda < tp.MATCH_MIN, (
    f"'Wanda Fuller Talk' scored {wanda:.3f}, at or above the {tp.MATCH_MIN} "
    "threshold — this detector is no better than the brightness one it replaced")

# And there must be real separation, not a threshold squeezed between two
# numbers that happen to fall either side of it.
# Generalisation is measured on HELD-OUT frames, which is what the threshold
# is actually calibrated against.
worst_positive = min(_ho)
# INK is the presence signal and is what separates this prompt from Wanda's:
# hers is simply shorter text. Measured 0.032-0.037 at the table, at most 0.017
# anywhere else.
_ink_pos = min(tp.ink(Image.open(f)) for f in POSITIVES + _held_out)
_ink_neg = max(tp.ink(Image.open(f)) for f in NEGATIVES)
assert _ink_pos > _ink_neg, (
    f"ink does not separate: table {_ink_pos:.4f} vs non-table {_ink_neg:.4f}")
assert _ink_pos >= tp.INK_MIN > _ink_neg, (
    f"INK_MIN {tp.INK_MIN} is outside the measured gap "
    f"({_ink_neg:.4f}..{_ink_pos:.4f})")

# at_table is the criterion runs are judged by, so test THAT, not just score.
for f in POSITIVES + _held_out:
    assert tp.at_table(Image.open(f)), f"{f}: real table frame rejected"
for f in NEGATIVES:
    assert not tp.at_table(Image.open(f)), (
        f"{f}: accepted as the table. Both negatives are frames that actually "
        "fooled a previous version — Wanda's prompt, and dark scenery with no "
        "prompt at all scoring 0.555 by correlating noise.")

print(f"OK: ink separates {_ink_neg:.4f} -> {_ink_pos:.4f}; at_table accepts "
      f"{len(POSITIVES) + len(_held_out)} real frames and rejects "
      f"{len(NEGATIVES)} known false positives")
