"""The escape ladder must not run against a flat surface — it never clears one.

MEASURED, from the archived wedge frames: a character pressed into the bar
counter yields 9, 10, 10, 11 keypoints, while every frame in open space yields
744-1500. The classes never overlap.

Every archived occurrence of the ladder against geometry shows
wait -> jump -> jump -> slip right -> slip left, each displacing 0.0px, then
"nothing cleared it". ~10 seconds to confirm what the keypoint count says at
once.

THIS IS THE DISCRIMINATOR THE OLD WALL-VS-NPC TEST LACKED. That test judged "a
wall does not move" on SCENE CHANGE, and standing still already produces changes
of 0.91-6.41, so its 2.0 threshold sat under the noise floor. Keypoint count
does not care whether anything moved — only whether there is structure in view.
"""
import os
import os as _os
import sys
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def run(n_keypoints, skip=True):
    """Returns (result, how many escape moves were attempted)."""
    moves = {"n": 0}
    fake_places = types.ModuleType("places")
    fake_places.keypoints = lambda img, cache_key=None: (None, [0] * n_keypoints)
    saved = sys.modules.get("places")
    sys.modules["places"] = fake_places

    real = (gw.ws if hasattr(gw, "ws") else None, gw.SKIP_LADDER_ON_GEOMETRY)
    gw.SKIP_LADDER_ON_GEOMETRY = skip
    fake_ws = types.ModuleType("walk_steps")
    fake_ws.turn_to = lambda *a, **k: 0.0
    def walk(*a, **k):
        moves["n"] += 1
        return 0.0
    fake_ws.walk_forward = walk
    saved_ws = sys.modules.get("walk_steps")
    sys.modules["walk_steps"] = fake_ws

    fake_pose = types.ModuleType("pose")
    fake_pose.displacement = lambda a, b: 0.0
    saved_pose = sys.modules.get("pose")
    sys.modules["pose"] = fake_pose

    real_sleep = gw.time.sleep
    gw.time.sleep = lambda *a: None
    try:
        out = gw._slip_past(2.1, 0.3, 0.4, lambda: object(),
                            lambda: 0.0, log=lambda *a: None)
    except Exception as e:
        out = ("raised", e)
    finally:
        gw.SKIP_LADDER_ON_GEOMETRY = real[1]
        gw.time.sleep = real_sleep
        for k, v in (("places", saved), ("walk_steps", saved_ws), ("pose", saved_pose)):
            if v is not None:
                sys.modules[k] = v
            else:
                sys.modules.pop(k, None)
    return out, moves["n"]


# A featureless frame: the ladder must not run at all.
out, moves = run(10)
check("a featureless frame skips the ladder entirely", moves == 0)
check("and it reports no progress and no clearing method",
      out == (0.0, None))

# A rich frame (an NPC blocking a visible passage): the ladder still runs.
out, moves = run(900)
check("a rich frame STILL runs the ladder — an NPC is not geometry", moves > 0)

# Flag off: old behaviour, ladder always runs.
out, moves = run(10, skip=False)
check("with the flag off the ladder runs even on geometry", moves > 0)

# The threshold must sit between the two measured populations.
check("the threshold is between the measured classes (11 and 744)",
      11 < gw.GEOMETRY_MAX_KEYPOINTS < 744)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
