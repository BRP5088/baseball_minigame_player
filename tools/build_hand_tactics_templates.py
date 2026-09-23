"""Rebuild the HAND-scale tactics banner bank, tactics_templates.npz.

WHY THIS FILE EXISTS. The bank is a committed binary on the money path -- the
tactics TYPE decides which card is played, and CLAUDE.md section 4 records that
only SWING and PITCH boosts add power, so a fielding boost read as a swing boost
plays the wrong card in a $50 match with nothing downstream reporting an error.
Until 2026-09-20 it had NO builder in the live tree: tools/build_tactics_templates.py
builds the REVEAL-scale bank (reveal_tactics_templates.npz), a different geometry,
and the hand bank came from a draft patch that had already landed. So the bank
could not be regenerated from source and had to be trusted as-is.

WHAT IT CANNOT DO, STATED PLAINLY. The original 360 templates' source frames are
not recorded anywhere, so they cannot be re-cut. This builder PRESERVES them
byte-for-byte as the base and appends donors cut from NAMED, COMMITTED frames.
Re-running is idempotent: the base is always the first BASE_N rows.

THE DEFECT THE DONORS FIX. Measured over 540 archived hand crops, the rejection
rate against MIN_TYPE_SCORE splits by SLOT x TYPE, not by either alone:

    slot |  fielding |    pitch |    speed |    swing
      0  |  0.0(137) |  0.0( 25)|  0.0( 89)|  0.0( 59)
      3  |100.0( 12) |  0.0( 11)|  0.0( 38)|  0.0( 11)   <- 12 of 12

Fielding at slot 3 failed EVERY time; fielding at slot 0 failed none of 137. The
cause is the bank's own composition: 137 of 163 fielding examples are slot 0, so
it encodes the slot-0 framing, and a slot-3 card tops out at 0.75 against it AT
ANY OFFSET (swept -40..+40; the peak is at 0, inside the shipped +-12 search).

TWO OTHER EXPLANATIONS WERE MEASURED AND REJECTED, so they are not retried:

  * BANNER_BOX too narrow for "FIELDING PLAY", the longest label. The clipping is
    real and visible -- slot-0 cards lose the trailing Y, slot-3 cards lose the
    leading F -- but widening it changes within-class agreement by +0.006 for
    fielding and makes the other three types WORSE. Not the cause.
  * A search range too small. The score peaks at ox=0 and falls away on both
    sides, so no offset recovers it.

VALIDATION, leave-one-HAND-out, because the 12 donor frames are only 3 DISTINCT
hands (8 of them share one five-card signature, pairwise banner correlation mean
0.958, max 0.9997 -- a hand sampled repeatedly is one example, not twelve):

    GAINED 12   LOST 0   CLASS FLIPS 0     per hand [8, 1, 3] of 3

Each hand is recovered by templates cut from the OTHER two, so this generalises
rather than matching itself. n=3 distinct hands is THIN and is stated rather than
hidden: it shows the direction, not a rate.

CLAUDE.md section 10.30: native size, ONE TEMPLATE PER EXAMPLE, never stretched
and never averaged. The score is the max over the bank, so adding an example can
only raise a score -- which is why LOST and CLASS FLIPS must both be 0 and are
checked here.

I-22 (2026-09-20) ADDS A SECOND DONOR, one PITCH FOCUS card at slot 3, for the
same reason: a bank-coverage gap the corpus census above never sampled (it only
tallied REJECTION RATE against MIN_TYPE_SCORE, not the LEFT-shifted disc position
that caused this one). n=1 distinct card, stated rather than hidden -- see
test_fixtures/hand_reads/README.md for the frames and the trace.

    .venv/bin/python -B tools/build_hand_tactics_templates.py [--check]

--check verifies the shipped bank matches what this script would build, and
writes nothing.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import local_hand as lh                                              # noqa: E402

OUT = lh.TACTICS_TEMPLATES

# The templates this script cannot re-cut, preserved byte-for-byte. Their source
# frames are not recorded anywhere; see the module docstring.
BASE_N = 360

# (frame, slot, kind) -- every donor NAMED, never globbed, so the build is
# deterministic and a pruned directory fails loudly instead of silently shrinking
# the bank. All twelve are fielding_boost at slot 3, the cell that failed 12/12.
DONORS = [
    ("overnight/local_hand/hand_1788937348354812000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788937441840867000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788937546610305000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788937656332256000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788937763958031000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788937871920432000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788937965944936000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788938060672634000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788938083999495000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788938103188984000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788938208525368000.png", 3, "fielding_boost"),
    ("overnight/local_hand/hand_1788938305027886000.png", 3, "fielding_boost"),
    # I-67, same shape again: the user hand-labelled 8 plainly visible TACTICS
    # cards (test_fixtures/user_truth/20260923_c20-26/labels.json) that still
    # missed MIN_TYPE_SCORE after I-64's BANNER_SEARCH step fix. A fresh SLOT x
    # TYPE census over 510 diagnostics/deal_frames/*/hand.png (measured by
    # agent_progress/issues/I-67/measure.py's slot_census(), same shape as the
    # 2026-09-20 census above) found the gaps were never closed for these
    # cells:
    #
    #     slot 1 speed_boost      n=24   95.8% rejected
    #     slot 1 fielding_boost   n= 9   88.9% rejected
    #     slot 3 fielding_boost   n=14   64.3% rejected   (the 12 donors above
    #                                                       never covered x~644)
    #     slot 4 swing_boost      n= 8   50.0% rejected
    #
    # Three donors, one per worst-hit cell reachable from the labelled set (slot
    # 0 speed_boost/fielding_boost/swing_boost are already <6% rejected -- NOT a
    # gap, so q62's individual miss there is left unfixed rather than papered
    # over with an unjustified donor):
    ("test_fixtures/hand_reads/i67_fielding_boost_slot3_q16.png", 3, "fielding_boost"),
    ("test_fixtures/hand_reads/i67_swing_boost_slot4_q29.png", 4, "swing_boost"),
    ("test_fixtures/hand_reads/i67_speed_boost_slot1_q56.png", 1, "speed_boost"),
    # A fourth cell, added after the three above were built and MEASURED: slot 2
    # speed_boost, 45.0% rejected (n=20) in the same census. This donor's own
    # source frame is ALSO left-edge clipped by the neighbour ("SPEED BOOST" ->
    # "PEED BOOST") -- the same shape as the slot-3 fielding_boost donor above,
    # whose fix generalised cleanly to a DIFFERENT clipped frame at that slot
    # (q18: 0.784 -> 0.989) rather than merely matching itself. No second
    # clipped slot-2 speed_boost frame is available to hold out the same way;
    # this one is n=1, stated rather than hidden (CLAUDE.md 10.4 / I-22 style).
    ("test_fixtures/hand_reads/i67_speed_boost_slot2_q23_clipped.png", 2, "speed_boost"),
    # Held out (NOT donors), to check the fix generalises rather than matching
    # itself: q18 (fielding_boost, SAME slot 3, a different frame -- like I-22's
    # turn1/turn4 pair; recovers 0.784 -> 0.989). NOT recovered by any donor
    # above, measured and left as-is rather than forced: q53 (swing_boost, same
    # slot 4 as the donor, a different frame -- best match against the new donor
    # itself is only 0.715, lower than its existing best of 0.840; these two
    # cards are not visually similar enough for one donor to bridge, and a
    # second untested donor was not added rather than ship an unvalidated
    # double-donor cell), q75 and q62 (speed_boost, slots 4 and 0 -- q62's cell,
    # slot 0 speed_boost, is NOT a census gap at all, 5.6% rejected n=18, so its
    # individual miss is a one-off left unfixed rather than papered over). See
    # agent_progress/issues/I-67/progress.md for the full recovery table.
    #
    # I-22 MOVED HERE (was appended before the block above): a live PITCH FOCUS
    # card sat unplayed in slot 3 for four consecutive turns and read
    # type_score 0.755-0.764 every time -- MIN_TYPE_SCORE is 0.85. Its disc
    # lands at x=642 in the 979-wide crop, well left of the ~661-664 cluster
    # the bank's other pitch_boost examples were cut from (overnight/
    # local_hand's slot-3 pitch_boost cards score 0.97 mean against the bank;
    # this card's own crop correlates only 0.28 against one of those). Not
    # occlusion -- the card is plainly legible and read_bonus already read it
    # correctly (bonus=1, 0.92-0.94) on every poll -- and not a timing
    # artefact -- the four polls span tens of seconds and agree to three
    # decimal places. test_fixtures/hand_reads/README.md has the full trace;
    # the second of the two frames it names is kept OUT of this list as an
    # independent check.
    #
    # KEPT LAST, DELIBERATELY: tests/minigame/test_i22_pitch_boost_slot3.py's
    # own mutation check strips `_type_templates()[-1]` and asserts that is
    # the I-22 donor -- moved here (instead of appending the I-67 block after
    # it) so that test needs no edit. A future ticket appending more donors
    # should insert BEFORE this entry, or update that test's slice.
    ("test_fixtures/hand_reads/i22_pitch_boost_slot3_turn1.png", 3, "pitch_boost"),
]


def donor_vector(frame, slot):
    """The banner vector for `slot` in `frame`, cut exactly as the reader cuts it.

    It goes through read_hand rather than a hardcoded box so the donor is cut at
    the card's FOUND position -- CLAUDE.md 10.23: a reader that crops at a fixed
    anchor reads the wrong pixels the moment the thing moves, and the fan's edge
    cards shift between frames.
    """
    path = os.path.join(ROOT, frame)
    if not os.path.exists(path):
        raise SystemExit(f"donor frame missing: {frame}\n"
                         "The bank cannot be rebuilt without it. It is a tracked "
                         "file; restore it rather than dropping the donor.")
    img = Image.open(path)
    rows = lh.read_hand(img)
    if slot >= len(rows):
        raise SystemExit(f"{frame}: only {len(rows)} rows, wanted slot {slot}")
    r = rows[slot]
    cx, cy = r.get("x"), r.get("y")
    if cx is None or cy is None:
        raise SystemExit(f"{frame} slot {slot}: no located position to cut from")
    v = lh._banner_at(img, cx, cy, 0, 0)
    if v is None:
        raise SystemExit(f"{frame} slot {slot}: banner box fell off the crop")
    return v.astype(np.float32)


def build():
    z = np.load(OUT, allow_pickle=True)
    V, T = z["vectors"], np.array([str(x) for x in z["types"]])
    if len(V) < BASE_N:
        raise SystemExit(f"{OUT} has {len(V)} templates, fewer than the "
                         f"{BASE_N}-template base this script preserves.")
    base_V, base_T = V[:BASE_N], T[:BASE_N]
    add_V = np.array([donor_vector(f, s) for f, s, _ in DONORS], dtype=np.float32)
    add_T = np.array([k for _, _, k in DONORS])
    return (np.vstack([base_V, add_V]).astype(np.float32),
            np.concatenate([base_T, add_T]))


def main():
    new_V, new_T = build()
    if "--check" in sys.argv:
        z = np.load(OUT, allow_pickle=True)
        cur_V, cur_T = z["vectors"], np.array([str(x) for x in z["types"]])
        same = (cur_V.shape == new_V.shape
                and np.allclose(cur_V, new_V, atol=1e-6)
                and list(cur_T) == list(new_T))
        print(f"  shipped bank matches this builder: {same}  "
              f"({len(cur_V)} templates)")
        sys.exit(0 if same else 1)
    np.savez_compressed(OUT, vectors=new_V, types=new_T)
    import collections
    print(f"  wrote {OUT}")
    print(f"    {BASE_N} preserved + {len(DONORS)} donors = {len(new_V)} templates")
    print(f"    by type: {dict(collections.Counter(new_T))}")


if __name__ == "__main__":
    main()
