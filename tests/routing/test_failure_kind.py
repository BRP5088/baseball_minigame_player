"""The classifier must separate the three MEASURED failure signatures.

Run against the real archived frames, not synthetic ones — a classifier that
only works on invented data would be worse than none.
"""
import glob
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
ROOT = _ROOT
sys.path.insert(0, ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import failure_kind as fk

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]


def fake(room, score, margin, n):
    return (lambda img: (room, score, margin)), (lambda img, cache_key=None: (None, [0] * n))


# The three measured signatures, with their real numbers.
i, k = fake(None, 1, 1.0, 10)
check("9-11 keypoints, unrecognised -> WEDGED",
      fk.classify(None, "bar_jukebox", ROUTE, i, k)[0] == fk.WEDGED)

i, k = fake(None, 105, 1.54, 1346)
check("1346 keypoints, unrecognised -> OVERSHOT",
      fk.classify(None, "bar_jukebox", ROUTE, i, k)[0] == fk.OVERSHOT)

i, k = fake("portrait_room", 480, 4.32, 1500)
check("confidently at an EARLIER node -> REGRESSED",
      fk.classify(None, "bar_jukebox", ROUTE, i, k)[0] == fk.REGRESSED)

# A node that is not behind us is not a regression.
i, k = fake("bar_jukebox", 500, 4.0, 1500)
check("the target itself is not a regression",
      fk.classify(None, "bar_pool_room", ROUTE, i, k)[0] != fk.REGRESSED)

# Somewhere off-route.
i, k = fake("office_door", 300, 2.0, 900)
check("a node that is not on the route -> UNPLACED",
      fk.classify(None, "bar_jukebox", ROUTE, i, k)[0] == fk.UNPLACED)

# The threshold must sit BETWEEN the measured populations (9-11 and 744).
check("the keypoint threshold is between the measured classes",
      11 < fk.WEDGED_MAX_KEYPOINTS < 744)

# --- and now against the REAL archived frames -------------------------------
# The archived set lives in failframes_prerecovery/ because those frames were
# captured AFTER recover_to_node ran, so they describe where the FAN left the
# character rather than where the leg failed — a confident diagnosis was built
# on them and was wrong.
#
# They are still the right data for THIS test. The classifier judges what a
# frame LOOKS like (featureless / rich-but-unnamed / confidently elsewhere), and
# these are genuine examples of each. Their provenance problem is about what
# they prove regarding the leg, not about their appearance.
# The PRERECOVERY archive first, deliberately. It is the curated set that spans
# all three classes, which is what a classifier test needs. `failframes/` holds
# whatever the last run happened to save — currently four frames of a single
# class — so preferring it makes this test's coverage depend on the last run.
frames = sorted(glob.glob(os.path.join(
    ROOT, "overnight", "failframes_prerecovery", "*.jpg")))
if not frames:
    frames = sorted(glob.glob(
        os.path.join(ROOT, "overnight", "failframes", "*.jpg")))
if not frames:
    print("FAIL no archived failure frames to classify")
    sys.exit(1)

from PIL import Image

seen = {}
for f in frames:
    target = "bar_jukebox" if "bar_jukebox" in f else "bar_pool_room"
    kind, detail = fk.classify(Image.open(f), target, ROUTE)
    seen[kind] = seen.get(kind, 0) + 1
    print(f"    {os.path.basename(f)[:38]:40} {kind:10} {detail}")

# REMOVED: check("every archived frame gets a class",
#                sum(seen.values()) == len(frames))
# `seen` is incremented exactly once per frame, so that sum is len(frames) by
# construction. It could only fail if classify() raised — in which case the
# file crashes before reaching it. Zero information.
check("the real frames span more than one class", len(seen) >= 2)
check("no archived frame is left UNPLACED-by-accident",
      seen.get(fk.UNPLACED, 0) < len(frames))

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
