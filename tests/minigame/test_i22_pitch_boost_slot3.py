"""I-22: a live PITCH FOCUS card sat unplayed in slot 3 for four consecutive turns
and never read locally.

WHAT HAPPENED, from overnight/run_live_20260920d.log's pitching half. After
"discarding the weakest (power 5)" at slot 3, the redeal into slot 3 read
`3: UNKNOWN` on four straight polls (hands [fb,6/0,5/1,UNKNOWN,6/0],
[fb,8/0,5/1,UNKNOWN,6/0], [fb,7/0,5/1,UNKNOWN,6/0], [fb,9/0,5/1,UNKNOWN,6/0])
before finally reading `pitch_boost +1` on the fifth. `describe_hand` prints
UNKNOWN only when local_hand_cards DROPPED the slot (it tried the hand memory
and the hail-mary bank first) -- so the engine played three full turns with
`hand_incomplete=True` and a pitch boost it could not see.

NOT AN OCCLUSION (10.28/10.34 do not apply). All four "dropped" hand.png stills
`local_hand_cards` writes show the card plainly: "PITCH FOCUS" legible, bonus
digit "1" in a clean white disc, nothing covering it. `read_bonus` already read
it correctly every time (bonus=1, score 0.92-0.94) -- only `read_tactics_type`'s
TYPE score fell short (0.755-0.764 against MIN_TYPE_SCORE 0.85), so
local_hand_cards dropped the whole card (`type is None`).

NOT A TIMING/SETTLE ARTEFACT either. The four polls span tens of seconds and the
type_score agrees to three decimal places across all of them (a STABLE misread,
CLAUDE.md: "same frame, same prompt, same wrong answer. Repair or clamp it
instead of looping"). And "watching the redeal" (play_one_turn's discard branch)
never armed for this card, correctly by its own rule: at discard time slot 3 was
the card BEING discarded, so it was in `_seen`, not `_blind` -- the gate answers
"was some OTHER slot already unreadable", not "will this slot's own replacement
be readable", and this defect lives entirely in the second question.

THE ACTUAL CAUSE, same shape as commit 83a4a73 (FIELDING PLAY at slot 3, "the
bank had never seen it there"): this card's disc lands at x=642 in the 979-wide
crop, well left of the ~661-664 cluster the bank's other pitch_boost examples
were cut from. Measured (agent_progress/issues/I-22/progress.md):
overnight/local_hand's slot-3 pitch_boost cards score 0.97 mean against the
shipped bank; this card's own raw crop correlates only 0.28 against one of them
directly. A genuine bank-coverage gap, not a threshold to move.

THE FIX: tools/build_hand_tactics_templates.py's DONORS list gained one entry,
cut from test_fixtures/hand_reads/i22_pitch_boost_slot3_turn1.png at slot 3's
FOUND position (not a fixed anchor -- CLAUDE.md 10.23). test_fixtures/hand_reads/
i22_pitch_boost_slot3_turn4.png, captured ~50s later, was deliberately NOT added
as a donor, so this file has one independently-captured frame the fix was never
trained on.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image

import local_hand as lh

_FIXDIR = os.path.join(_ROOT, "test_fixtures", "hand_reads")
_DONOR_FRAME = "i22_pitch_boost_slot3_turn1.png"   # used as a DONORS entry
_HELDOUT_FRAME = "i22_pitch_boost_slot3_turn4.png"  # never used as a donor

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


def _slot3(frame):
    img = Image.open(os.path.join(_FIXDIR, frame))
    rows = lh.read_hand(img)
    check(len(rows) == 5, f"{frame}: read_hand returned {len(rows)} rows, expected 5")
    return rows[3]


print("1. both frames read slot 3 as a fully identified pitch_boost card")
for frame in (_DONOR_FRAME, _HELDOUT_FRAME):
    r = _slot3(frame)
    check(r.get("kind") == "tactics", f"{frame}: kind={r.get('kind')!r}, expected tactics")
    check(r.get("type") == "pitch_boost",
          f"{frame}: type={r.get('type')!r} (score {r.get('type_score')}), "
          f"expected pitch_boost >= {lh.MIN_TYPE_SCORE}")
    check(r.get("type_score", 0) >= lh.MIN_TYPE_SCORE,
          f"{frame}: type_score {r.get('type_score')} under the gate {lh.MIN_TYPE_SCORE}")
    check(r.get("bonus") == 1, f"{frame}: bonus={r.get('bonus')!r}, expected 1")
    check(r.get("adds_power") is True,
          f"{frame}: adds_power={r.get('adds_power')!r}, expected True (pitch_boost adds power)")

print()
print("2. MUTATION: drop the I-22 donor and the fix disappears on BOTH frames")
# _type_templates() caches the loaded bank at module level (lh._type_cache), so the
# only way to prove the new row is load-bearing rather than vacuous (CLAUDE.md's
# check() lesson: a check that cannot fail is worse than none) is to strip it and
# watch both frames regress to the live failure this ticket started from.
_full_vecs, _full_types = lh._type_templates()
_stripped_vecs, _stripped_types = _full_vecs[:-1], _full_types[:-1]
check(len(_stripped_types) == len(_full_types) - 1,
      f"CONTROL: the mutation actually removes one template "
      f"({len(_stripped_types)} of {len(_full_types)} kept)")
check(_full_types[-1] == "pitch_boost",
      f"CONTROL: the last template is the I-22 donor, got {_full_types[-1]!r} -- "
      "the mutation above is stripping the wrong row")
lh._type_cache = (_stripped_vecs, _stripped_types)
try:
    for frame in (_DONOR_FRAME, _HELDOUT_FRAME):
        r = _slot3(frame)
        check(r.get("type") != "pitch_boost" or r.get("type_score", 1.0) < lh.MIN_TYPE_SCORE,
              f"{frame}: still reads pitch_boost at {r.get('type_score')} with the I-22 "
              "donor removed -- some OTHER template is doing the work, not the one added")
finally:
    lh._type_cache = (_full_vecs, _full_types)  # restore for any test that runs after this

print()
print("3. RESTORE CONFIRMED: the donor is back and both frames read right again")
for frame in (_DONOR_FRAME, _HELDOUT_FRAME):
    r = _slot3(frame)
    check(r.get("type") == "pitch_boost" and r.get("type_score", 0) >= lh.MIN_TYPE_SCORE,
          f"{frame}: recovers to pitch_boost after the bank is restored "
          f"(type={r.get('type')!r}, score={r.get('type_score')})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all checks passed")
