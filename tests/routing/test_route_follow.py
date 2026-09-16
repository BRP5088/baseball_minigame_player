"""Check the heading maths the route follower steers on.

These are the two places a sign or wrap error would send the character into the
wrong room while every log line still looked reasonable: the shortest-angle
error, and interpolating the recorded heading curve across the 360/0 boundary.
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

import route_follow as rf

# shortest-angle error, including across the wrap
assert rf._err(90, 80) == 10
assert rf._err(80, 90) == -10
assert rf._err(10, 350) == 20, "crossing 360->0 must be +20, not -340"
assert rf._err(350, 10) == -20
# The route's first leg goes from the spawn (87) to the door (270). The
# recording turned CLOCKWISE through 105, 148, 232 to get there, but the
# shortest angle is 177 the other way, so the follower will sweep left where
# the player swept right. That is fine — a turn leg is performed standing
# still, so only the bearing it ENDS on affects where the character then walks.
# What must hold is that the shortest angle is what gets used, and that it is
# never mistaken for the 183 the player actually swept.
assert abs(rf._err(270, 87) + 177) < 1e-9, (
    f"expected -177 (shortest, counter-clockwise), got {rf._err(270, 87)}")
assert abs(rf._err(270, 87)) <= 180, "an error outside +-180 means a wrap bug"

# interpolation along a leg
pts = [(0.0, 0.0), (1.0, 90.0)]
assert rf._want_at(pts, -1) == 0.0, "before the leg starts, hold the first bearing"
assert rf._want_at(pts, 2.0) == 90.0, "after it ends, hold the last"
assert abs(rf._want_at(pts, 0.5) - 45.0) < 1e-6

# interpolation must take the SHORT way across the wrap
pts = [(0.0, 350.0), (1.0, 10.0)]
mid = rf._want_at(pts, 0.5)
assert abs(rf._err(mid, 0.0)) < 1e-6, (
    f"midpoint of 350->10 must be 0, got {mid} — going the long way round here "
    "would spin the camera a full turn mid-walk")

# a correction must actually be big enough to move the stick out of its deadzone
import turn_curve as tc
assert tc.mag_for(20 / rf.CORRECT_HORIZON) >= tc.DEAD_BELOW, (
    "a 20 degree error must produce a stick magnitude above the deadzone, "
    "otherwise the follower 'corrects' with a stick that does nothing")

print("OK: shortest-angle error, wrap-safe interpolation, correction above deadzone")
