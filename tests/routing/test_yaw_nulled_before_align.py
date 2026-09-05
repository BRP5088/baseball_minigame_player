"""align_at_node must null the YAW before measuring lateral offset.

THE BUG. `pose.offset`'s own docstring states the precondition — "Null the yaw
with the compass first and what remains is lateral translation" — and until
2026-09-05 NOTHING did it. align_at_node opened the reference frame and went
straight to align_lateral, so every degree of heading error was measured as
sideways displacement and STRAFED AWAY.

MEASURED at the live geometry (7 pure camera-turn pairs, character stationary):
**18.6-20.8 px per degree**, sign consistent, corroborated by camera_fov.json
(1920 / 102 deg = 18.8).

The units therefore collide:
    ALIGN_TOL_PX  35.0   is 1.8 DEGREES of heading
    SAME_POSE_PX  16.85  is 0.87 DEGREES
while the leg executor turns with a 4.0 degree tolerance. A character parked
exactly on the reference POSITION but 2 degrees off its heading reads ~40px and
gets strafed sideways to "correct" a displacement that does not exist.

The fix uses the project's own principle: turning does not move the character,
walking does. So turn to the reference's heading first, then measure.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw
import pose
import slow_traverse as st

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


REF = os.path.join(_ROOT, "places", "portrait_room", "route_0038.23.jpg")
if not os.path.exists(REF):
    print(f"FAIL missing reference frame {REF} — this test cannot run, and a "
          f"test that cannot run must not report success")
    sys.exit(1)


def run(reference_heading_readable=True, turn_works=True):
    """Drive align_at_node with the compass and aligner faked out."""
    turned, lines = [], []
    old_ref, old_align, old_turn = (gw._recorded_reference, pose.align_lateral,
                                    st.turn_to)
    old_cache = dict(gw._REF_HEADING)
    try:
        gw._recorded_reference = lambda n: REF
        pose.align_lateral = lambda *a, **k: 12.0
        if not reference_heading_readable:
            gw._REF_HEADING["portrait_room"] = None

        # RECORD THE TOLERANCE, not just the target. The first version of this
        # stub swallowed **kwargs, so align_at_node's failure to pass a
        # tolerance was invisible and the test passed while the feature turned
        # on 0 of 3 nodes.
        def fake_turn(want, read_heading=None, capture=None, log=None,
                      tolerance=None, **kw):
            turned.append((want, tolerance))
            return (want, []) if turn_works else (None, [])

        st.turn_to = fake_turn
        gw.align_at_node("portrait_room", capture=lambda: object(),
                         read_heading=lambda: 45.0, log=lines.append)
    finally:
        gw._recorded_reference, pose.align_lateral = old_ref, old_align
        st.turn_to = old_turn
        gw._REF_HEADING.clear()
        gw._REF_HEADING.update(old_cache)
    return turned, "\n".join(lines)


# --- the reference frame's own heading must be readable -------------------
gw._REF_HEADING.clear()
h = gw.reference_heading("portrait_room")
gw._REF_HEADING.clear()
check("the reference frame carries a readable heading", h is not None)
# Pinned as a literal: comparing it to itself would pass for any value.
check("and it is the measured 1.39 degrees", h is not None and abs(h - 1.39) < 0.05)

# --- the yaw must actually be nulled BEFORE measuring ---------------------
turned, log = run()
check("align_at_node turns before measuring", len(turned) == 1)
check("and it turns to the REFERENCE's heading, not the leg's bearing",
      turned and abs(turned[0][0] - 1.39) < 0.05)
check("and it says so", "yaw nulled" in log)

# THE DEFECT THE OLD TEST COULD NOT SEE. align_at_node omitted `tolerance`, so
# slow_traverse's WALKING default of 4.0 applied — and every offset this feature
# targets (2.56 / -0.50 / -1.47 deg) is inside 4.0, so it turned on 0 of 3
# nodes. 4.0 deg is also ~75px of residual against ALIGN_TOL_PX = 35.
check("it passes an EXPLICIT tolerance, not slow_traverse's walking default",
      turned and turned[0][1] is not None)
check("and that tolerance is tight enough to matter (<= 1 deg)",
      turned and turned[0][1] is not None and turned[0][1] <= 1.0)
check("the constant is the measured 0.5 deg", gw.YAW_NULL_TOLERANCE_DEG == 0.5)
check("px-per-degree is the measured 18.8", gw.PX_PER_DEG == 18.8)

# The log must call the residual a RESIDUAL. It used to print the error still
# PRESENT as "phantom dx removed", in runs where nothing was sent.
check("the log reports the residual as remaining, not as removed",
      "REMAINING" in log and "removed" not in log)

# --- the flag must be honoured -------------------------------------------
old = gw.NULL_YAW_BEFORE_ALIGN
try:
    gw.NULL_YAW_BEFORE_ALIGN = False
    turned_off, _ = run()
finally:
    gw.NULL_YAW_BEFORE_ALIGN = old
check("with the flag OFF it does not turn (so the A/B is real)",
      len(turned_off) == 0)

# --- failures must be LOUD, never silently skipped ------------------------
_t, log = run(reference_heading_readable=False)
check("an unreadable reference heading is reported, not skipped silently",
      "UNREADABLE" in log and "not nulled" in log.lower())

_t, log = run(turn_works=False)
check("a failed turn says the dx still carries yaw",
      "could not turn" in log and "carries yaw" in log)

# --- the px-per-degree figure this all rests on --------------------------
# Literal, from camera_fov.json: 1920 / 102 deg. If the FOV changes, the
# phantom-dx arithmetic in the log line changes with it.
import json
fov = json.load(open(os.path.join(_ROOT, "camera_fov.json")))["fov_degrees"]
check("the FOV still implies ~18.8 px/deg", abs(1920.0 / fov - 18.8) < 0.3)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
