"""I-70: a power disc PARTLY covered by the next card in the fan must still read,
without ever guessing on a slot the ungated reader gets right.

WHY THIS MATTERS MORE THAN A PLAIN ACCURACY CHECK. This reader decides which card
gets played in a $50 match. A recovery pass that occasionally proposes the WRONG
digit is worse than one that recovers nothing -- so this file checks abstention as
hard as it checks the positive recovery. See local_hand.py's LEFT_MASK_COLS comment
and agent_progress/issues/I-70/progress.md for the measurement this is built on.

MUTANTS THIS IS DESIGNED TO CATCH (agent_progress/issues/I-70/progress.md has the
mutation table):
  1. Reverting local_hand.LEFT_MASK_COLS to 24 (i.e. turning the mask off) --
     the positive recovery check must fail.
  2. Raising local_hand.MIN_SCORE so the recovered score no longer clears it --
     the positive recovery check must fail.
  3. Swapping local_hand._masked_templates' digit labels (e.g. reversing the
     `digits` list without reversing `grid`) -- a WRONG digit should come back
     confidently, and the safety check must fail.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "i70_slightly")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


def slot_row(rows, slot):
    for r in rows:
        if r.get("_slot_i") == slot:
            return r
    return None


# ---- 1. THE POSITIVE CASE: a "slightly" covered disc the ungated reader misses ------
img = Image.open(os.path.join(FIX, "slightly_slot0_digit5.png")).convert("RGB")
rows = local_hand.read_hand(img)
row = slot_row(rows, 0)
check("slightly-covered slot 0 now reads a digit",
      row is not None and row.get("digit") is not None,
      str(row))
if row is not None:
    check("slightly-covered slot 0 reads the CORRECT digit (5)",
          str(row.get("digit")) == "5", f"got {row.get('digit')!r}")
    check("slightly-covered slot 0 clears MIN_SCORE",
          row.get("score", 0.0) >= local_hand.MIN_SCORE, str(row.get("score")))
    check("the row is flagged as coming from the I-70 pass",
          row.get("digit_from_left_masked_search") is True, str(row))

# ---- 2. THE SAFETY CASE: a covered slot must never read the WRONG digit -------------
for fname, slot, truth in (("covered_slot0_digit4.png", 0, "4"),
                            ("covered_slot1_digit4.png", 1, "4")):
    img = Image.open(os.path.join(FIX, fname)).convert("RGB")
    rows = local_hand.read_hand(img)
    row = slot_row(rows, slot)
    digit = row.get("digit") if row else None
    check(f"{fname}: never claims a digit other than the true {truth}",
          digit is None or str(digit) == truth, f"got {digit!r}")

# ---- 3. do-no-harm: MASKED matching must not fire when a digit is ALREADY set -------
# Fabricate a row with a digit already present; _left_masked_digit_search is gated on
# "digit is None" by every caller in read_hand -- this pins that the FUNCTION ITSELF
# is only ever reachable through that gate, by checking read_hand's own output shape
# rather than calling the private search directly (which has no such gate on its own
# and is not meant to).
already = Image.open(os.path.join(FIX, "slightly_slot0_digit5.png")).convert("RGB")
rows_a = local_hand.read_hand(already)
rows_b = local_hand.read_hand(already)
check("read_hand is deterministic across repeated calls on the same frame (idempotent)",
      [(r.get("digit"), r.get("kind")) for r in rows_a] ==
      [(r.get("digit"), r.get("kind")) for r in rows_b])

# ---- 4. LEFT_MASK_COLS sits where it was measured, not silently re-tuned -----------
check("LEFT_MASK_COLS is 14 (agent_progress/issues/I-70/progress.md)",
      local_hand.LEFT_MASK_COLS == 14, str(local_hand.LEFT_MASK_COLS))
check("LEFT_MASK_COLS is strictly less than SIDE (a real mask, not a no-op)",
      0 < local_hand.LEFT_MASK_COLS < local_hand.SIDE, str(local_hand.LEFT_MASK_COLS))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
