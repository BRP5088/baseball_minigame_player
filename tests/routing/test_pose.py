"""Pose sameness must resolve a single 0.2s step, and must refuse to guess.

WHY THIS EXISTS
---------------
The wall anchor's whole claim is "this puts the character in the same place
every time". That claim needs a measurement, and the measurement needs to be
calibrated against the real capture path — calibrating on a cleaner
representation than production is how read_ban_counter (2000px vs 1920px) and
the reveal thresholds (resized vs native) both broke.

Calibrated 2026-09-02 at the jukebox through compass.fast_capture():

    stationary, no input   n=23  median  3.58px  MAX  8.80px
    after one 0.2s step    n=10  median 38.89px  MIN 32.25px
"""
import json
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import pose

FIX = os.path.join(_ROOT, "test_fixtures", "pose")
fails = []


def check(c, m):
    if not c:
        fails.append(m)


if not os.path.exists(os.path.join(FIX, "manifest.json")):
    raise SystemExit(f"missing {FIX}/manifest.json — this test must not "
                     f"silently skip; the threshold it guards is the only "
                     f"evidence the anchor works")

man = json.load(open(os.path.join(FIX, "manifest.json")))
stat = [os.path.join(FIX, f) for f in man["stationary"]]
moved = [os.path.join(FIX, f) for f in man["moved"]]
check(len(stat) >= 2 and len(moved) >= 1, "not enough calibration frames")

# A frame against itself is exactly zero. If this drifts, the metric is broken
# in a way no threshold can rescue.
check(pose.displacement(stat[0], stat[0]) == 0.0,
      f"a frame against itself measured {pose.displacement(stat[0], stat[0])}px")

# Frames with NO input between them are the same pose.
for a, b in zip(stat, stat[1:]):
    d = pose.displacement(a, b)
    check(d is not None and d <= pose.SAME_POSE_PX,
          f"two stationary frames measured {d}px, over the "
          f"{pose.SAME_POSE_PX}px threshold — the anchor would report drift "
          f"that did not happen and never settle")
    check(pose.same_pose(a, b), "same_pose() rejected two stationary frames")

# Frames after real movement are NOT the same pose.
for m in moved:
    d = pose.displacement(stat[0], m)
    check(d is not None and d > pose.SAME_POSE_PX,
          f"a frame taken after deliberate steps measured {d}px, under the "
          f"{pose.SAME_POSE_PX}px threshold — the anchor would call a moved "
          f"character anchored, which is the whole failure it exists to prevent")
    check(not pose.same_pose(stat[0], m), "same_pose() accepted a moved frame")

# The threshold must sit BETWEEN the two measured populations.
# Alignment tolerance must be reachable by the stick: below ~0.10s a push does
# not move the character, and at the measured gain that floor is ~20-30px.
check(pose.ALIGN_TOL_PX >= 20.0,
      f"ALIGN_TOL_PX {pose.ALIGN_TOL_PX} is finer than the stick can deliver "
      f"(a push under {pose.ALIGN_MIN_SEC}s does not move), so the loop would "
      f"never report success")
check(pose.ALIGN_DAMPING < 1.0,
      f"ALIGN_DAMPING {pose.ALIGN_DAMPING} is undamped; at full gain the "
      f"correction oscillated with growing amplitude (+175 -> -201 -> +211)")

check(8.80 < pose.SAME_POSE_PX < 32.25,
      f"SAME_POSE_PX {pose.SAME_POSE_PX} is outside the measured gap: "
      f"stationary noise reached 8.80px and the smallest real step was 32.25px")

# Unmeasurable must NOT read as identical.
check(pose.same_pose("/nonexistent_a.jpg", "/nonexistent_b.jpg") is False,
      "an unmeasurable pair was reported as the same pose; being unable to "
      "tell is not evidence of sameness")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  pose: identical frames measure 0px, {len(stat)} stationary frames "
      f"agree, {len(moved)} moved frames are rejected, threshold sits in the "
      f"measured 8.80-32.25px gap, unmeasurable never reads as identical")
