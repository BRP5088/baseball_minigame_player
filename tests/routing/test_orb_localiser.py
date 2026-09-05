"""Place recognition must survive a changed pose and NPCs that moved.

WHY THIS EXISTS
---------------
The previous localiser was a GLOBAL edge descriptor, and a global statistic
fails exactly where this game moves: standing a step to one side, or a mouse
wandering past, changes the whole vector. Measured 2026-09-01, held out on five
arrival frames verified by eye with one demo reference per room:

    edge descriptor   1/5 correct, 4 abstain
    ORB keypoints     5/5 correct, 0 wrong, 0 abstain

It also could not be tuned out of a catastrophic false positive: an UPSTAIRS
office door scored 0.906 against beside_dealer_table — higher than any genuine
live match, so no threshold could separate it. The same frame gets ONE keypoint.
"""
import glob
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

import places

fails = []


def check(c, m):
    if not c:
        fails.append(m)


# Every reference must identify as its own room. Trivial, but it is the
# property that breaks first when the mask or the thresholds are edited.
refs = [p for p in sorted(glob.glob(os.path.join(_ROOT, "places", "*", "*.jpg")))
        if os.path.basename(p) != "pano.jpg"]
check(len(refs) >= 4, f"only {len(refs)} reference frames on disk")
for p in refs:
    truth = os.path.basename(os.path.dirname(p))
    room, n, ratio = places.identify(p)
    check(room == truth,
          f"{truth}/{os.path.basename(p)} identified as {room!r} "
          f"({n} matches, ratio {ratio}) — a reference that cannot recognise "
          f"itself cannot recognise anything")

# Frames that are NOT any known room must ABSTAIN. Being confidently wrong is
# what sends a route walking at a doorway on another floor.
NEGATIVES = [
    ("demos/walk3_full_20260828_050731/f_0016.06.jpg",
     "an upstairs office door — the frame that scored 0.906 as the BAR"),
    ("test_fixtures/prompt_detector/20260828_140652_622.jpg", "a gameplay turn"),
    ("test_fixtures/ban_scan/20260828_140309_081.jpg", "a ban screen"),
]
checked_neg = 0
for rel, what in NEGATIVES:
    p = os.path.join(_ROOT, rel)
    if not os.path.exists(p):
        fails.append(f"missing negative fixture {rel} — this test must not "
                     f"silently skip; that is how the old false positive lived "
                     f"for weeks")
        continue
    checked_neg += 1
    room, n, ratio = places.identify(p)
    check(room is None,
          f"{what} was identified as {room!r} ({n} matches, ratio {ratio}). "
          f"It is not a labelled place and naming it is worse than not knowing")

# HELD-OUT ARRIVALS — the property that actually matters. Not "can a reference
# recognise itself" (true for almost any method) but "is a frame taken where the
# executor ACTUALLY stops, with the NPCs wherever they wandered to, still
# recognised". None of these is a reference.
#
# This is also what pins the HUD MASK. Measured 2026-09-01: masked scores 5/5
# here, UNMASKED scores 1/5 — the quest list and compass are pixel-identical in
# every frame, so unmasked they hand every pair of rooms a large pile of free
# matches and the wrong room wins. (The ratio gap actually looks BETTER
# unmasked, +0.57 vs +0.30, which is why a threshold check alone cannot catch
# this: the separation is fine, it is just separating the wrong thing.)
_fix = os.path.join(_ROOT, "test_fixtures", "localiser")
_labels = os.path.join(_fix, "labels.json")
if not os.path.exists(_labels):
    fails.append(f"missing {_labels} — this test must not silently skip; "
                 f"held-out frames are the only thing here that can fail")
else:
    _held = json.load(open(_labels))
    check(len(_held) >= 5, f"only {len(_held)} held-out frames")
    _ok = 0
    for entry in _held:
        p = os.path.join(_fix, entry["file"])
        room, n, ratio = places.identify(p)
        _ok += room == entry["room"]
        check(room == entry["room"],
              f"held-out {entry['file']} (really {entry['room']}) identified as "
              f"{room!r} with {n} matches, ratio {ratio}. These are the frames "
              f"the executor actually produces; the previous global descriptor "
              f"managed 1 of 5 on them")
    check(_ok == len(_held), f"{_ok}/{len(_held)} held-out arrivals recognised")

# The thresholds must sit BETWEEN the two measured populations, not inside one.
check(114 < places.MIN_MATCHES < 166,
      f"MIN_MATCHES {places.MIN_MATCHES} is outside the measured gap: "
      f"negatives reached 114 matches and the weakest true positive was 166")
check(1.22 < places.MIN_RATIO < 1.52,
      f"MIN_RATIO {places.MIN_RATIO} is outside the measured gap: negatives "
      f"reached 1.22 and the weakest true positive was 1.52")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  ORB localiser: {len(refs)} references each recognise themselves, "
      f"{checked_neg} non-places abstain (including the upstairs door that "
      f"scored 0.906 as the bar), thresholds sit in the measured gap")
