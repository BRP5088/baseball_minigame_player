"""The drive feedback may not name a room the localiser would not name.

WHAT THE USER SAW. Driving through a side room of the office -- a place with no
reference frame at all -- the feedback read "(best dealer_table ...)". They
reported it immediately, and they were right.

THE CAUSE was not the localiser. record_drive took an ARGMAX over the four
rooms and printed the winner's name whatever its score. An argmax always returns
something, and on this game's art an unrelated rich frame scores 100-135 against
ANY room: that is the spurious-match floor measured the same day, when a genuine
arrival scored 137 and a frame taken outdoors on a street scored 135, against a
gate of 140.

So the display named a room from a score the shipped gates reject. The fix is to
report what places.verdict concluded -- it applies MIN_MATCHES and MIN_RATIO and
returns None when it abstains -- rather than a private argmax.

WORTH RECORDING: a QA finder checked this area and passed it, having verified
that the KNOWN verdict never claims coverage identify_orb denies. That was true.
The bug was in the NAME printed beside the verdict, on every line regardless of
it. The person who could see the screen found what the analysis did not.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np
from PIL import Image

import places

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


import importlib.util
spec = importlib.util.spec_from_file_location(
    "rd", os.path.join(_ROOT, "overnight", "record_drive.py"))
rd = importlib.util.module_from_spec(spec)
sys.argv = ["record_drive.py", "office", "1"]
try:
    spec.loader.exec_module(rd)
except SystemExit:
    pass

refs = places.load_keypoints(os.path.join(_ROOT, "places"))
check("the reference set loads by absolute path", bool(refs))

# A frame from a place with NO reference. The outdoor street frame is exactly
# that: the character walked out of the building, and nothing in places/ is
# anywhere near it.
STREET = os.path.join(_ROOT, "test_fixtures", "leg_failures",
                      "overshot_outdoors_1788718155150.jpg")
check("the outdoor fixture exists", os.path.exists(STREET))
if os.path.exists(STREET):
    img = Image.open(STREET)
    _, d = places.keypoints(img)
    scores = {r: max(places.match_count(d, x) for x in rs)
              for r, rs in refs.items()}
    named, best, ratio = places.verdict(scores)
    argmax = max(scores, key=scores.get)
    check(f"the localiser ABSTAINS on it (best {best}, ratio {ratio})",
          named is None)
    check(f"but an argmax still returns a room ({argmax} at {scores[argmax]}) "
          f"-- which is what used to be printed", argmax is not None)

    room, score, verdict = rd._novelty(img, refs, [])
    check(f"_novelty reports NO room for it (got {room!r})", room is None)
    check(f"and does not call it KNOWN or thin (got {verdict!r})",
          verdict in ("NEW", "repeat", "FEATURELESS"))

# A real reference frame must still be named, or the fix has gone too far the
# other way and the feedback can never say KNOWN.
REF = os.path.join(_ROOT, "places", "portrait_room", "live_00.jpg")
# THE FIXTURE MUST EXIST, exactly as the STREET half already requires. This
# block is the file's only anti-vacuity control -- its own comment says "A real
# reference frame must still be named, or the fix has gone too far the other way
# and the feedback can never say KNOWN". Behind a bare os.path.exists it would
# disappear SILENTLY if the fixture went missing, and the file would still pass
# while proving only that the negative half works.
check("the reference fixture exists", os.path.exists(REF))
if os.path.exists(REF):
    room, score, verdict = rd._novelty(Image.open(REF), refs, [])
    check(f"a genuine reference frame IS named ({room} {score} {verdict})",
          room == "portrait_room" and verdict == "KNOWN")

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
