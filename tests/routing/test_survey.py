"""survey.consider must keep only RICH, UNRECOGNISED frames.

A quarter of route failures are the character standing somewhere detailed that
the map cannot name. Those places can only be mapped if something records them,
and nothing did. But a place seeded from a BAD frame poisons the localiser
permanently — a near-featureless door once matched the bar at 0.906, beating
every genuine arrival — so the filter matters more than the collection.
"""
import json
import os
import os as _os
import sys
import tempfile
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import survey

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class Img:
    def __init__(self):
        self.saved = []

    def save(self, p):
        self.saved.append(p)
        open(p, "wb").write(b"x")


def run(keypoints, room, score, margin=1.0):
    fake = types.ModuleType("places")
    fake.keypoints = lambda img, cache_key=None: (None, [0] * keypoints)
    fake.identify = lambda img: (room, score, margin)
    saved = sys.modules.get("places")
    sys.modules["places"] = fake
    d = tempfile.mkdtemp()
    old = survey.SURVEY_DIR
    survey.SURVEY_DIR = d
    img = Img()
    try:
        return survey.consider(img, {"leg": "a->b"}), img, d
    finally:
        survey.SURVEY_DIR = old
        if saved is not None:
            sys.modules["places"] = saved
        else:
            sys.modules.pop("places", None)


# The case this exists for: rich and unrecognised.
p, img, d = run(1346, None, 105)
check("a rich UNRECOGNISED frame is kept", p is not None)
check("and the image was actually written", img.saved)
check("and its metadata was recorded",
      os.path.exists(os.path.join(d, "candidates.jsonl")))

# Featureless: a wall, not a place. This is the 0.906 false-positive guard.
p, _, _ = run(10, None, 1)
check("a featureless frame is REJECTED", p is None)
p, _, _ = run(399, None, 1)
check("just below the keypoint bar is rejected", p is None)

# Already known: not a new place.
p, _, _ = run(1500, "portrait_room", 480, 4.3)
check("a frame the localiser already names is rejected", p is None)

# Ambiguous: high match count but no name. Exactly what must not be seeded.
p, _, _ = run(1500, None, 300)
check("an ambiguous near-match is rejected", p is None)

check("the keypoint bar matches brett_walk.mark's reasoning",
      survey.MIN_KEYPOINTS >= 200)



# WIRING: walk_link must actually call survey.consider when the flag is on, and
# a survey failure must never end a leg — this is bookkeeping, not navigation.
import graph_walk as gw

calls = {"n": 0}
real_consider = survey.consider
real_st = sys.modules.get("slow_traverse")
fake_st = types.ModuleType("slow_traverse")
fake_st.TURN_TOLERANCE = 4.0
fake_st.turn_to = lambda *a, **k: (10.0, [])
fake_st.walk_leg = lambda *a, **k: (0.4, 20.0, [])
sys.modules["slow_traverse"] = fake_st


class M2:
    def steps_for(self, a, b):
        return [{"bearing": 10.0, "dur": 0.4, "speed": 0.3}]


def boom(img, where, log=None):
    calls["n"] += 1
    raise RuntimeError("survey exploded")


old_flag = gw.SURVEY_WHILE_WALKING
try:
    gw.SURVEY_WHILE_WALKING = True
    survey.consider = boom
    raised = None
    try:
        gw.walk_link(M2(), "a", "b", capture=lambda: object(),
                     read_heading=lambda: 10.0, log=lambda *a: None)
    except RuntimeError as e:
        raised = e
    check("walk_link calls survey.consider when surveying", calls["n"] >= 1)
    check("a survey failure does NOT end the leg", raised is None)

    calls["n"] = 0
    gw.SURVEY_WHILE_WALKING = False
    try:
        gw.walk_link(M2(), "a", "b", capture=lambda: object(),
                     read_heading=lambda: 10.0, log=lambda *a: None)
    except Exception:
        pass
    check("with the flag off it never surveys", calls["n"] == 0)
finally:
    gw.SURVEY_WHILE_WALKING = old_flag
    survey.consider = real_consider
    if real_st is not None:
        sys.modules["slow_traverse"] = real_st
    else:
        sys.modules.pop("slow_traverse", None)

check("surveying ships OFF", gw.SURVEY_WHILE_WALKING is False)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
