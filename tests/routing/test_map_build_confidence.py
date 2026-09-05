"""map_build's confidence gate must sit on the ORB scale, not the old one.

THE BUG THIS GUARDS. SEG_MIN_SCORE/SEG_MIN_MARGIN were 0.62 / 0.08, written for
the identify_edges() correlation scores (0..1). identify() has delegated to
identify_orb() since 2026-09-01, so `score` is a MATCH COUNT (>= 140 when it
does not abstain) and `margin` is a RATIO (>= 1.35). Against those the gate was
ALWAYS TRUE — _confident() collapsed to `place is not None`, and every edge in
world_map.json was admitted with no confidence bar at all, in a function whose
own comment claims "the bar is higher here than for a live lookup".

Same shape as the rest of this project's threshold bugs: a gate that cannot
fail looks exactly like a gate that passes.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import map_build as mb
import places

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def row(score, margin, place="bar_jukebox", kind="frame"):
    return {"kind": kind, "place": place, "score": score, "margin": margin}


# THE LITERALS ARE PINNED, not read from the module. Asserting
# `SEG_MIN_SCORE > places.MIN_MATCHES` would rise with the constant under test
# and pass forever — the exact mistake documented for MAX_HAND_SIZE.
check("SEG_MIN_SCORE is on the match-count scale",
      mb.SEG_MIN_SCORE == 200.0)
check("SEG_MIN_MARGIN is on the ratio scale",
      mb.SEG_MIN_MARGIN == 1.60)

# The gate must sit ABOVE the live abstain thresholds — an edge is permanent,
# a live lookup is not.
check("the bar really is higher than a live lookup's",
      mb.SEG_MIN_SCORE > places.MIN_MATCHES
      and mb.SEG_MIN_MARGIN > places.MIN_RATIO)

# The two directions that matter.
check("a strong arrival is admitted", mb._confident(row(520, 4.30)))
check("a barely-confident ORB frame is REJECTED", not mb._confident(row(150, 1.40)))
check("a frame just under the score bar is REJECTED", not mb._confident(row(199, 4.30)))
check("a frame just under the margin bar is REJECTED", not mb._confident(row(520, 1.59)))

# The regression itself: old-scale values must not sail through.
check("an old-scale correlation row is REJECTED",
      not mb._confident(row(0.7, 0.1)))

# And the gate must still reject the things it always did.
check("a non-frame row is rejected", not mb._confident(row(520, 4.30, kind="cmd")))
check("a row with no place is rejected", not mb._confident(row(520, 4.30, place=None)))

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
