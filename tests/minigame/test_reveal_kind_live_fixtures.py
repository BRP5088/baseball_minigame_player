"""I-18(c): score reveal_cards.TACTICS_KIND_MIN against the 5 live fixtures.

WHAT THE FIVE ARE. `test_fixtures/reveal_kind_truth/live/<kind>_<ns>.jpg` -- the
top-level singles `record_reveal_kind` writes, one per fixture, named by the kind
the ENGINE chose (ground truth, not circular -- CLAUDE.md 10.22). They are the
first frames from a THIRD match (2026-09-17) the shipped bank had never seen; the
bank's 10 original templates were all cut from TWO archived matches (`reveal6`
and `reveal`, OPEN-24).

MEASURED BEFORE ANY FIX (agent_progress/issues/I-18/progress.md,
score_live5.py): 2 of 5 read right (both swing_boost, which happened to already
clear the gate). pitch_boost read the right kind but 0.026 under the gate.
speed_boost read the right kind but a wrong kind (fielding_boost) scored higher
in the SAME zone, both under the gate. fielding_boost read a wrong kind as best,
also under the gate. Zero wrong-kind scores crossed 0.75 -- the failure was all
abstention (CLAUDE.md OPEN-24's "abstains on 29%", worse here at 60%), never a
confident wrong answer.

THE FIX (tools/build_tactics_templates.py): two native-size templates cut from
the pitch_boost and speed_boost fixtures themselves, text band only, same shape
as the existing bank (CLAUDE.md 10.30: native size, one template per example,
never stretched, never averaged). Both fixtures now self-match at 1.000 and are
NO LONGER HELD OUT -- this file pins that they read right, not that the reader
generalises to a fourth match.

fielding_boost is NOT fixed, and that is recorded rather than hidden: its own
crop showed the true banner sits mostly ABOVE the padded ZONE_HOME band this
reader searches (agent_progress/issues/I-18/progress.md has the crops), so no
template placed inside the search area can ever match it. That is a zone/pad
geometry question in reveal_cards.py, not a bank-coverage gap, and is out of
scope here. This test PINS the abstention so a future fix is visible as a
change, not silently absorbed.

TWO GENUINELY HELD-OUT CHECKS, BOTH REQUIRED TO CLEAR THE GATE:
  the swing_boost fixtures (never supplied templates, unaffected by this fix)
  the archived 48-frame corpus (tools/banner_kind_census.py) -- the pitch_boost
    template's first cut (badge + wreath included) scored 0.7606 against a
    held-out swing_boost frame, OVER the gate; trimmed to text-only it is
    0.6712, and the archived census's wrong-kind MAX moved 0.710 -> 0.741,
    still under 0.75. `test_wrong_kind_max_stays_under_gate` pins both.

TACTICS_KIND_MIN IS NOT MOVED. Nothing here changes it.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import reveal_cards as rc
import tools.banner_kind_census as bkc

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


LIVE = os.path.join(_ROOT, "test_fixtures", "reveal_kind_truth", "live")

# (filename, truth kind, zone the truth kind actually renders in -- found by
# direct visual inspection of the frame, not assumed from the kind's name;
# CLAUDE.md 10.15: open the frame before theorising).
FIXTURES = [
    ("fielding_boost_1789941315522731000.jpg", "fielding_boost", rc.ZONE_HOME),
    ("pitch_boost_1789941284009861000.jpg",    "pitch_boost",    rc.ZONE_MOUND),
    ("speed_boost_1789940135610162000.jpg",    "speed_boost",    rc.ZONE_HOME),
    ("swing_boost_1789939952893318000.jpg",    "swing_boost",    rc.ZONE_HOME),
    ("swing_boost_1789940025431959000.jpg",    "swing_boost",    rc.ZONE_HOME),
]

# Fixtures that supplied a template to the bank -- self-matching at ~1.000 is
# expected and is NOT evidence the reader generalises (CLAUDE.md 10.30).
NO_LONGER_HELD_OUT = {"pitch_boost_1789941284009861000.jpg",
                      "speed_boost_1789940135610162000.jpg"}


def _read(fname, zone):
    im = Image.open(os.path.join(LIVE, fname))
    scores = rc.tactics_kind_scores(im, zone)
    best = max(scores, key=scores.get)
    return best, scores


print("1. right-kind read rate on the 5 live fixtures (4/5, up from 2/5)")
right = 0
for fname, truth, zone in FIXTURES:
    best, scores = _read(fname, zone)
    reads_right = best == truth and scores[best] >= rc.TACTICS_KIND_MIN
    right += reads_right
    check(reads_right == (fname != "fielding_boost_1789941315522731000.jpg"),
          f"{fname}: best={best} score={scores[best]:.3f} truth={truth} "
          f"truth_score={scores[truth]:.3f} reads_right={reads_right}")
check(right == 4, f"4 of 5 read right (got {right})")

print("\n2. the two fixtures that supplied templates self-match at 1.000")
for fname, truth, zone in FIXTURES:
    if fname not in NO_LONGER_HELD_OUT:
        continue
    best, scores = _read(fname, zone)
    check(best == truth and scores[best] >= 0.999,
          f"{fname}: {best} {scores[best]:.4f} (its own template, so ~1.000)")

print("\n3. fielding_boost is UNFIXED and PINNED, not silently accepted forever")
best, scores = _read("fielding_boost_1789941315522731000.jpg", rc.ZONE_HOME)
check(scores["fielding_boost"] < rc.TACTICS_KIND_MIN,
      f"fielding_boost still abstains ({scores['fielding_boost']:.3f} < "
      f"{rc.TACTICS_KIND_MIN}) -- its banner sits above the padded ZONE_HOME "
      "band this reader searches, a zone/pad question, not a bank-coverage one")

print("\n4. the two GENUINELY held-out live fixtures still read right, and no "
      "wrong kind crosses the gate on them")
for fname, truth, zone in FIXTURES:
    if fname in NO_LONGER_HELD_OUT or truth != "swing_boost":
        continue
    best, scores = _read(fname, zone)
    check(best == truth and scores[best] >= rc.TACTICS_KIND_MIN,
          f"{fname}: still reads {best} correctly ({scores[best]:.3f})")
    wrong_max = max(v for k, v in scores.items() if k != truth)
    check(wrong_max < rc.TACTICS_KIND_MIN,
          f"{fname}: wrong-kind max {wrong_max:.4f} stays under the gate "
          f"{rc.TACTICS_KIND_MIN}")

print("\n5. the ARCHIVED 48-frame held-out corpus still clears the gate too")
# The required OTHER check: growing the bank from live fixtures must not push
# a wrong kind over TACTICS_KIND_MIN on the corpus OPEN-24 was fitted against.
_right, _wrong, _skipped, _ = bkc.score_held_out()
check(_skipped == 0, f"CONTROL: no archived frame was skipped ({_skipped})")
check(len(_right) == 86 and len(_wrong) == 258,
      f"CONTROL: the archived corpus is still the same 86 right-kind / 258 "
      f"wrong-kind readings (got {len(_right)}/{len(_wrong)})")
_wrong_max = max(_wrong)
check(_wrong_max < rc.TACTICS_KIND_MIN,
      f"archived wrong-kind max {_wrong_max:.4f} stays under the gate "
      f"{rc.TACTICS_KIND_MIN} (was 0.710 before this bank grew, now {_wrong_max:.4f})")

print("\n6. MUTATION: drop the live-sourced templates and the fix disappears")
# _tactics_bank() caches the loaded bank at module level (rc._TBANK), so the
# only way to prove these two templates are load-bearing rather than vacuous
# (CLAUDE.md's check() lesson: a check that cannot fail is worse than none) is
# to filter them out and watch pitch_boost/speed_boost regress to the
# pre-fix abstention measured in agent_progress/issues/I-18/progress.md.
_full_bank = rc._tactics_bank()
# reveal_tactics_templates.npz stores keys as f"{kind}__{i}" in build order, and
# build_tactics_templates.py's CUTS list appends the two live-sourced templates
# LAST (index 10, 11) after the 10 archived-only ones (index 0-9) -- so the
# first 10 entries in build order are exactly the pre-fix bank.
_stripped = _full_bank[:10]
check(len(_stripped) < len(_full_bank),
      f"CONTROL: the mutation actually removes templates "
      f"({len(_stripped)} of {len(_full_bank)} kept)")
rc._TBANK = _stripped
try:
    best, scores = _read("pitch_boost_1789941284009861000.jpg", rc.ZONE_MOUND)
    check(not (best == "pitch_boost" and scores["pitch_boost"] >= rc.TACTICS_KIND_MIN),
          f"with the live templates removed, pitch_boost regresses to abstain "
          f"(got best={best} score={scores.get('pitch_boost'):.3f}) -- proving "
          f"the added template, not the gate or the zone, is what fixed it")
finally:
    rc._TBANK = _full_bank  # restore for any test that runs after this one

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
