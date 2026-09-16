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

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
