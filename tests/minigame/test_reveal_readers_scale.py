"""Both reveal readers must answer the same at every capture geometry.

CLAUDE.md section 3 names this family: "a new window written in raw pixels works
perfectly on the machine it was tuned on and silently lands on the wrong thing
everywhere else". Both banks were fixed uint8 arrays handed to matchTemplate at
NATIVE size while their search bands are FRACTIONS of the frame, so a 4% change in
width put the word and the template at different scales.

AND 2000px IS THE RIG'S OWN GEOMETRY, not a hypothetical: orchestrator._fast_grab
asks game_capture.grab for SETTLE_CALIBRATION_WIDTH = 2000. Measured before the fix:

    reveal_banner (gate 0.80)      1920     2000     1867     1600
      HOME RUN!                    1.000    0.517    0.679    0.328   <- all MISSED
      PLAY BALL!                   1.000    0.638    0.723    0.197   <- all MISSED

    reveal_cards tactics (0.75)    1920     2000     1867     1600
      reveal_cards                 1.000    0.787    0.882    0.518   <- 1600 MISSED,
      reveal_fielding              0.997    0.829    0.863    0.523      2000 marginal

The negatives did NOT move, which is what makes scaling a fix rather than a
loosening -- the check below pins that too.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import reveal_banner as rb
import reveal_cards as rc

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


FR = os.path.join(_ROOT, "test_fixtures/reveal_banner")
WIDTHS = (1920, 2000, 1867, 1600)


def at(name, w):
    im = Image.open(os.path.join(FR, f"{name}.jpg")).convert("RGB")
    if im.width == w:
        return im
    return im.resize((w, int(round(im.height * w / im.width))), Image.LANCZOS)


def tactics_best(im):
    v = []
    for z in (rc.ZONE_HOME, rc.ZONE_MOUND):
        sc = rc.tactics_kind_scores(im, z)
        v.append(max(sc.values()) if sc else 0.0)
    return max(v)


# --- 1. the BANNER reader answers the same at every width -------------------
for name, want in (("home_run", "home_run"), ("play_ball", "play_ball")):
    got = {w: rb.read_banner(at(name, w))[0] for w in WIDTHS}
    check(set(got.values()) == {want},
          f"{name} reads {want} at every width: {got}")

# ...and the NEGATIVES stay negative. Scaling that inflated the negatives would be
# a loosening dressed as a fix -- this is the half that says which it is.
for name in ("reveal_cards", "reveal_fielding"):
    got = {w: rb.read_banner(at(name, w))[0] for w in WIDTHS}
    check(set(got.values()) == {None},
          f"{name} has no banner and reads None at every width: {got}")

# --- 2. the TACTICS reader clears its gate at every width -------------------
for name in ("reveal_cards", "reveal_fielding"):
    got = {w: round(tactics_best(at(name, w)), 3) for w in WIDTHS}
    check(all(v >= rc.TACTICS_KIND_MIN for v in got.values()),
          f"{name} clears TACTICS_KIND_MIN {rc.TACTICS_KIND_MIN} at every width: {got}")

neg = {w: round(tactics_best(at("reveal_pitching", w)), 3) for w in WIDTHS}
check(all(v < rc.TACTICS_KIND_MIN for v in neg.values()),
      f"the tactics negative stays under the gate at every width: {neg}")

# --- 3. THE CONTROL, and it is the whole test -------------------------------
# Forcing REF_W to the frame's own width makes s == 1, which reproduces the
# UNSCALED code exactly. If the readers scored the same either way, everything
# above would be passing for a reason that has nothing to do with scaling.
_saved = (rb.REF_W, rc.REF_W)
try:
    im = at("home_run", 1600)
    rb.REF_W = 1600
    unscaled = max(rb.scores(im).values())
    rb.REF_W = 1920
    scaled = max(rb.scores(im).values())
finally:
    rb.REF_W, rc.REF_W = _saved

check(unscaled < rb.BANNER_MIN <= scaled,
      f"CONTROL: at 1600px the UNSCALED reader misses HOME RUN! ({unscaled:.3f} "
      f"< {rb.BANNER_MIN}) and the scaled one reads it ({scaled:.3f}) — so the "
      "checks above are measuring the scaling and not something else")

# --- 4. the frame floor is DERIVED from the bank, not written ---------------
floor = rb._min_frame_w()
widest = max(t.shape[1] for _l, t in rb._bank())
check(floor >= widest / (rb.BAND[2] - rb.BAND[0]),
      f"MIN_FRAME_W {floor} is at least widest-template/band-fraction "
      f"({widest}/{rb.BAND[2] - rb.BAND[0]:.2f} = "
      f"{widest / (rb.BAND[2] - rb.BAND[0]):.0f})")
check(floor == 1230,
      f"and it comes out at 1230 for today's bank, not the written 1200 that let "
      f"a 1200-1229px frame drop the play_ball class silently (got {floor})")



# =========================================================================
# HELD-OUT POSITIVES. A template matches its OWN SOURCE at 1.000 (CLAUDE.md 30),
# so every check above that uses home_run.jpg / play_ball.jpg / reveal_cards.jpg is
# scoring a bank against the frames it was cut from and proves only that the cut
# worked. tools/banner_census.py and tools/banner_kind_census.py both held their
# sources out; the TESTS did not, and the tests are what runs on every commit.
#
# Identified by score: a frame that supplied a template reads exactly 1.000.
#   r_001099, r_001738  play_ball SOURCES
#   r_004785            home_run SOURCE
#   r_002387            held out, reads play_ball at 0.974   <- heldout_play_ball
#   r_005783            held out, tactics at 0.996           <- heldout_tactics
# =========================================================================
ho = at("heldout_play_ball", 1920)
_lab, _d = rb.read_banner(ho)
_best = max(rb.scores(ho).values())
check(_lab == "play_ball" and _best < 0.9995,
      f"a HELD-OUT frame reads play_ball at {_best:.3f} — under 1.000, so this is "
      "the bank generalising and not matching its own source")

hk = at("heldout_tactics", 1920)
check(rc.read_tactics_kind(hk, rc.ZONE_HOME)[0] == "swing_boost"
      and rc.read_tactics_kind(hk, rc.ZONE_MOUND)[0] == "pitch_boost",
      "a HELD-OUT frame names both tactics kinds correctly")

# ...and they must survive the rescaling too, which is the point of this file.
for w in WIDTHS:
    check(rb.read_banner(at("heldout_play_ball", w))[0] == "play_ball",
          f"the held-out play_ball still reads at {w}px")

# WHAT IS STILL MISSING, STATED RATHER THAN PAPERED OVER: there is NO held-out
# HOME RUN! frame anywhere on disk. The archive holds exactly one home_run reveal
# (r_004785) and it supplied the template, so that class is scored against its own
# source only and this file cannot fix that. The next live home run should have a
# reveal frame harvested into test_fixtures/reveal_banner/ as heldout_home_run.jpg,
# after which this block gets the matching check.
_hr_sources = [n for n in ("home_run",) if abs(max(rb.scores(at(n, 1920)).values()) - 1.0) < 5e-4]
check(_hr_sources == ["home_run"],
      "home_run.jpg is still a template SOURCE (scores 1.000) — recorded here so "
      "nobody reads the home-run checks above as held-out evidence")



# =========================================================================
# THE MISSING CLASS IN THE TACTICS CENSUS (10.31), MEASURED RATHER THAN ASSUMED.
#
# tools/banner_kind_census.py scores four kinds and has NO class for a card
# MID-ANIMATION -- the reveal's opening frames, before the cards settle. A census
# cannot discover a class its own labeller does not have, and the unnameable class
# sits exactly where the highest-scoring "negatives" are. That is how the DRAW!
# screen was found, and it is the shape that inflated a gate's apparent headroom.
#
# So the question is whether the missing class threatens TACTICS_KIND_MIN. It does
# not, on the frames that exist: the two openers of the one reveal recording on
# disk score 0.46 and 0.49 against a gate of 0.75 -- not marginal, roughly halfway
# to the floor. Pinned here so a later change to the gate has to reckon with them.
#
# HONEST LIMIT: n = 2, from ONE recording. This says the gate is not obviously
# endangered; it is nowhere near a census. The at_table precedent is the warning --
# 500 frames said zero false positives and the 701st fired.
for _name in ("midanim_opener", "midanim_early"):
    _im = at(_name, 1920)
    _best = max([max(rc.tactics_kind_scores(_im, _z).values() or [0])
                 for _z in (rc.ZONE_HOME, rc.ZONE_MOUND)] or [0])
    check(_best < rc.TACTICS_KIND_MIN,
          f"the mid-animation frame {_name} scores {_best:.3f}, under "
          f"TACTICS_KIND_MIN {rc.TACTICS_KIND_MIN} — the class the census cannot "
          "name does not clear the gate")
    check(rb.read_banner(_im)[0] is None,
          f"...and {_name} reads no banner either")


print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
