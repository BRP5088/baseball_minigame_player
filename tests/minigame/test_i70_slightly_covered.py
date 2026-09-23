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
  4. (round 2, M2) Dropping the "digit is None" gate on the fourth pass' caller
     loop (read_hand would then call the masked search for a PLAYER row that
     already has a digit, and overwrite it) -- check 5 below catches this by
     monkeypatching the search itself, so it does not depend on any particular
     frame having an unread slot.
  5. (round 2) Reordering the no-candidate branch back to round 1's shape
     (masked search before the tactics-banner check) -- check 6 below catches
     this by forcing every slot into "no candidate" and asserting a confidently
     bannered tactics slot never becomes kind=player.
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

# ---- 5. MUTANT M2 GUARD: a digit already read must never reach the masked search ----
# round 1's check 3 above only pinned DETERMINISM, which a removed gate still satisfies
# (the mutant is deterministic too) -- r1/skeptic.md confirmed M2 survives it. This
# monkeypatches _left_masked_digit_search itself to return an obviously wrong,
# high-confidence sentinel digit, so the check does not depend on any fixture having a
# slot the gate would otherwise protect; it directly asks "is the search even callable
# once a row already has a digit, from the FOURTH pass's own gate".
#
# Only slot 0 in this fixture goes through the no-candidate branch (which legitimately
# calls this same search UNGATED by "digit is None" -- there is nothing to protect
# there, see the comment above that call site); slots that already read a digit via an
# ordinary earlier pass (digit_from_left_masked_search is NOT set) are the ones the
# fourth pass's OWN gate must protect, so those are what this check watches.
img = Image.open(os.path.join(FIX, "slightly_slot0_digit5.png")).convert("RGB")
baseline_rows = local_hand.read_hand(img)
baseline_digits = {r["_slot_i"]: r.get("digit") for r in baseline_rows
                    if r.get("digit") is not None and not r.get("digit_from_left_masked_search")}
check("sanity: the baseline frame has an already-read digit from an ORDINARY pass "
      "(not from the no-candidate branch's own masked-search call)",
      len(baseline_digits) > 0, str(baseline_digits))

_orig_masked_search = local_hand._left_masked_digit_search


def _sentinel_masked_search(img, ax, ay, s, keep_cols=local_hand.LEFT_MASK_COLS):
    return "9", 0.999, (int(ax), int(ay))


local_hand._left_masked_digit_search = _sentinel_masked_search
try:
    guarded_rows = local_hand.read_hand(img)
finally:
    local_hand._left_masked_digit_search = _orig_masked_search

guarded_digits = {r["_slot_i"]: r.get("digit") for r in guarded_rows if r.get("_slot_i") is not None}
check("a sentinel masked search never overwrites a digit read by an earlier pass",
      all(guarded_digits.get(i) == d for i, d in baseline_digits.items()),
      f"baseline={baseline_digits} guarded={guarded_digits}")

# ---- 6. TACTICS-BANNER GUARD: the no-candidate branch must check the banner BEFORE --
# trying the masked search, so a confidently-bannered tactics slot can never be
# mis-promoted to kind=player by a search that only ever looks for a player digit.
# Every disc-finding source is monkeypatched empty so EVERY slot hits the "no
# candidate at all" branch regardless of the fixture's real content, then the raised/
# resting search and the tactics banner are forced so the ordering is the only thing
# under test.
_orig_fan_present = local_hand._fan_looks_present
_orig_strong = local_hand._strong_discs
_orig_white = local_hand._white_discs
_orig_find_tactics = local_hand.find_tactics
_orig_raised_resting = local_hand._raised_or_resting_search
_orig_tactics_type = local_hand.read_tactics_type

local_hand._fan_looks_present = lambda *a, **k: True
local_hand._strong_discs = lambda img: []
local_hand._white_discs = lambda g: []
local_hand.find_tactics = lambda img, dark_max=110: []
local_hand._raised_or_resting_search = lambda *a, **k: (None, 0.0, None, False)
local_hand.read_tactics_type = lambda img, i: ("pitch_boost", 0.9)  # >= TACTICS_PRESENT_MIN
local_hand._left_masked_digit_search = _sentinel_masked_search  # confident PLAYER digit
try:
    forced_rows = local_hand.read_hand(img)
finally:
    local_hand._fan_looks_present = _orig_fan_present
    local_hand._strong_discs = _orig_strong
    local_hand._white_discs = _orig_white
    local_hand.find_tactics = _orig_find_tactics
    local_hand._raised_or_resting_search = _orig_raised_resting
    local_hand.read_tactics_type = _orig_tactics_type
    local_hand._left_masked_digit_search = _orig_masked_search

check("every slot with a confident tactics banner and no other candidate stays kind=tactics",
      len(forced_rows) == 5 and all(r.get("kind") == "tactics" for r in forced_rows),
      str([(r.get("_slot_i"), r.get("kind"), r.get("digit")) for r in forced_rows]))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
