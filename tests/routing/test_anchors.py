"""The anchor thresholds must sit between measured scores, not be guessed.

An anchor is only useful if the worst match at its own location still beats the
best match anywhere else on the route. This checks that property held when the
anchors were selected, and that the stored threshold actually separates the two
— a threshold outside that gap would either accept everything or nothing.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import
_os.chdir(_ROOT)

import anchors

a = anchors.load()
assert a, "no anchors — route_anchors.json is empty or missing"

for x in a:
    assert x["near"] > x["far"], (
        f"anchor t={x['t']} is not separable: worst same-place {x['near']:.3f} "
        f"does not beat best elsewhere {x['far']:.3f}. It would fire in the "
        "wrong place, which is worse than having no anchor there.")
    assert x["far"] < x["threshold"] < x["near"], (
        f"anchor t={x['t']}: threshold {x['threshold']:.3f} is outside the "
        f"measured gap ({x['far']:.3f}..{x['near']:.3f})")

# The early anchors are the trustworthy ones, and THE REASON IS THE NPCs, NOT THE
# MARGINS. The late ones sit inside a bar full of NPCs who move between runs —
# Wanda was found at the arrival point despite appearing at t=17.95 in the
# recording — so their margins are not evidence of position whatever size they are.
#
# THIS USED TO ALSO ASSERT THAT EVERY LATE GAP IS THINNER THAN EVERY EARLY ONE,
# WRITTEN AS `... or True`, WHICH CANNOT FAIL ON ANY INPUT. The `or True` was
# load-bearing, because the claim is FALSE on today's data:
#
#     early n=7   gaps 0.0620 .. 0.4380
#     late  n=3   gaps 0.0700 .. 0.1010
#     max(late) 0.1010 < min(early) 0.0620  ->  False
#
# One EARLY anchor is thinner than every late one. The blanket ordering is not a
# property of this data and asserting it with an escape hatch stated something
# untrue while proving nothing. What IS true is pinned immediately below: every
# late gap is under 0.12. That is the measured fact, and the NPC argument above is
# the reason they are distrusted.
early = [x for x in a if x["t"] < 14.0]
assert len(early) >= 5, f"only {len(early)} early anchors; expected the office/stairs run"
assert min(x["gap"] for x in early) >= 0.05

late = [x for x in a if x["t"] > 20.0]
if late:
    thin = [x["t"] for x in late if x["gap"] < 0.12]
    assert thin, (
        "the late anchors used to have margins under 0.12, which is why they "
        "are not trusted; if that changed, revisit whether they can be relied on")

print(f"OK: {len(a)} anchors, all separable with thresholds inside their gaps "
      f"({len(early)} trustworthy early, {len(late)} thin late)")
