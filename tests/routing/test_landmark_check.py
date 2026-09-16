"""The landmark check must separate 'same place' from 'different place'.

Both halves matter. A check that says yes to everything gives false confidence
that a leg landed correctly; one that says no to everything makes a working
route look broken.

The frames here are real captures from the confirmed run on 2026-08-27.
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
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import glob
import itertools
import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
from PIL import Image

import landmark_check as lc

fails = []
# ANCHORED ON _ROOT, and a MISSING FIXTURE IS A FAILURE.
# This was `FIX = "route_frames"` (CWD-relative) guarded by `SystemExit(0)`,
# which is a PASS. So running this file from its own directory — what an
# editor's "run this file" button does — reported success having checked
# nothing at all. Eleven sibling files explicitly refuse to silently skip;
# this was the last one that did.
FIX = os.path.join(_ROOT, "route_frames")
if not os.path.isdir(FIX):
    print(f"FAIL: no {FIX}/ reference frames — this test cannot run, and a "
          f"test that cannot run must not report success")
    raise SystemExit(1)

groups = {}
for f in sorted(glob.glob(f"{FIX}/*.png")):
    groups.setdefault(os.path.basename(f).split("__")[0], []).append(f)

same, diff = [], []
for name, fs in groups.items():
    for a, b in itertools.combinations(fs, 2):
        same.append((name, lc.similarity(Image.open(a), Image.open(b))))
for (n1, f1), (n2, f2) in itertools.combinations(
        [(n, fs[0]) for n, fs in groups.items()], 2):
    diff.append((f"{n1}|{n2}", lc.similarity(Image.open(f1), Image.open(f2))))

for name, s in same:
    if s < lc.MATCH_THRESHOLD:
        fails.append(f"two frames of {name} scored {s:.2f}, below the "
                     f"{lc.MATCH_THRESHOLD} threshold — a correct leg would be "
                     "reported as having landed in the wrong place")
for name, s in diff:
    if s >= lc.MATCH_THRESHOLD:
        fails.append(f"{name} are different places but scored {s:.2f} — the "
                     "check would confirm a leg that ended somewhere else")

# NOT ASSERTED: that masking the HUD improves discrimination. It does not —
# measured, masking costs a little (gap +0.33 vs +0.39), because the quest log
# is semi-transparent and the compass tracks heading, so both carry some scene
# information. The mask exists because the quest log goes STALE as jobs
# complete, and no frame available here can demonstrate that. Asserting it
# anyway would be a test that passes for the wrong reason.

if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print(f"  {len(same)} same-place pairs all >= {lc.MATCH_THRESHOLD}, "
      f"{len(diff)} different-place pairs all below it")
