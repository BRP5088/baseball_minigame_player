"""The tactics TYPE reader must never name the wrong type. Abstaining is free; guessing is not.

WHY THIS IS THE STRICTEST READER HERE. CLAUDE.md section 4: only SWING_BOOST and PITCH_BOOST
add power, while speed and fielding boosts carry a nonzero bonus that adds NONE. So the type
is not a label, it is the field the play decision turns on -- a speed boost read as a swing
boost plays the wrong card in a $50 match, and nothing downstream would report an error.

MEASURED, leave-one-HAND-out over 83 located tactics cards in 30 distinct hands (a hand
sampled twice is nearly the same picture, so scoring across the pair measures JPEG rather
than recognition -- the neighbour of CLAUDE.md 10.22):

    at MIN_TYPE_SCORE   69 correct, 0 WRONG, 14 abstained
    top score           RIGHT p05 0.773     WRONG MAX 0.761      no overlap
    the MARGIN over the runner-up does NOT separate (right p05 0.112, wrong max 0.203)
    and is deliberately not used (CLAUDE.md 10.4)
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np                                                      # noqa: E402
from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "hand_digits")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


expected = json.load(open(os.path.join(FIX, "expected.json")))

# ---- 1. ON REAL HANDS: the type either matches the paid model, or is None. A WRONG type
# is the only unacceptable outcome, so it is checked separately from coverage.
seen_tactics = 0
for fname, meta in sorted(expected.items()):
    rows = local_hand.read_hand(Image.open(os.path.join(FIX, fname)).convert("RGB"))
    if len(rows) != len(meta["paid"]):
        continue
    for r, c in zip(rows, meta["paid"]):
        if c["kind"] != "tactics" or not c.get("type"):
            continue
        seen_tactics += 1
        got = r.get("type")
        check(f"{fname}: tactics type is {c['type']} or not read",
              got in (None, c["type"]), f"got {got!r} at {r.get('type_score')}")
check("the fixtures actually contain tactics cards", seen_tactics >= 3,
      f"{seen_tactics} checked")

# ---- 1b. AND IT MUST ACTUALLY READ SOME. Without this the file passes when the reader
# reads NOTHING: a mutant that moved BANNER_BOX off the banner made every card abstain and
# the whole file stayed green, because check 1 accepts "or not read". That is this
# project's signature failure -- the code did nothing and doing nothing looked exactly like
# working (CLAUDE.md 10.1). Three of the five fixtures carry a card the bank has seen, so
# three successful reads is the floor; a lower count means the geometry has moved.
reads = 0
for fname, meta in sorted(expected.items()):
    rows = local_hand.read_hand(Image.open(os.path.join(FIX, fname)).convert("RGB"))
    if len(rows) != len(meta["paid"]):
        continue
    reads += sum(1 for r, c in zip(rows, meta["paid"])
                 if c["kind"] == "tactics" and r.get("type") == c.get("type"))
check("the reader NAMES at least three fixture cards, not merely abstains everywhere",
      reads >= 3, f"{reads} named")

# ---- 2. A PLAYER CARD'S SLOT MUST NOT PRODUCE A TYPE. The banner box is placed by slot,
# so pointing it at a player card is the natural way to get a confident wrong answer.
players = 0
for fname, meta in sorted(expected.items()):
    img = Image.open(os.path.join(FIX, fname)).convert("RGB")
    rows = local_hand.read_hand(img)
    if len(rows) != len(meta["paid"]):
        continue
    for i, c in enumerate(meta["paid"]):
        if c["kind"] != "player":
            continue
        players += 1
        t, s = local_hand.read_tactics_type(img, i)
        check(f"{fname} slot {i} is a player card and names no tactics type",
              t is None, f"got {t!r} at {s:.3f}")
check("player slots were actually exercised", players >= 8, f"{players} slots")

# ---- 3. NOISE MUST ABSTAIN. A reader that answers anything answers wrongly on a bad frame.
rng = np.random.RandomState(11)
noise = Image.fromarray(rng.randint(0, 255, (307, 979), dtype=np.uint8)).convert("RGB")
for slot in range(5):
    t, s = local_hand.read_tactics_type(noise, slot)
    check(f"noise abstains at slot {slot}", t is None, f"got {t!r} at {s:.3f}")

# ---- 4. THE GATE IS PINNED AS A LITERAL and bracketed by the two measured populations.
# Comparing against local_hand.MIN_TYPE_SCORE would rise with it and pass forever
# (CLAUDE.md 10.11).
# RE-MEASURED after the banner box was narrowed from 180px to 120px and the crop
# recentred on the FOUND card rather than the slot anchor. The 180px box reached past
# the card into the NEIGHBOUR's banner, so the correlation was matching two cards at
# once; a contact sheet of the "unsure" cards showed their banner text plainly legible.
# Cross-session (templates from the early half of the corpus, tested on the late half,
# 173 cards):
#
#     RIGHT (n=172)   p01 0.714   p05 0.830   p50 0.969
#     WRONG (n=1)     the single wrong answer in the whole test set scores 0.766
#
# Still an OVERLAP, not a gap, so still a SAFETY TRADE -- an abstention costs one paid
# call, a wrong type plays a speed boost as if it added power in a $50 match:
#
#     gate 0.80   coverage 97.7%   0 wrong   margin +0.034
#     gate 0.85   coverage 93.6%   0 wrong   margin +0.084   <- shipped
#     gate 0.88   coverage 87.3%   0 wrong   margin +0.114
#
# 0.85 keeps the ~8% margin the previous gate was chosen for, at more than twice the
# coverage: the old 0.88 against the wide box read 40.5% of cards.
check("MIN_TYPE_SCORE is 0.85", local_hand.MIN_TYPE_SCORE == 0.85,
      str(local_hand.MIN_TYPE_SCORE))
check("and it clears the worst measured WRONG answer (0.766) with margin",
      local_hand.MIN_TYPE_SCORE >= 0.766 * 1.05, str(local_hand.MIN_TYPE_SCORE))

# AND THE BOX IS PINNED TOO, because the gate is only meaningful against the crop it
# was measured on. A wider box quietly re-admits the neighbour's banner and the gate
# above then rejects cards it was chosen to accept.
check("BANNER_BOX is the narrow one the gate was measured against",
      local_hand.BANNER_BOX == (-62, 18, 58, 70), str(local_hand.BANNER_BOX))
check("and it does not reach past the card into the neighbour",
      local_hand.BANNER_BOX[2] - local_hand.BANNER_BOX[0] == 120,
      f"{local_hand.BANNER_BOX[2] - local_hand.BANNER_BOX[0]}px wide")

# ---- 5. THE BANK holds only the four types the game has, and no type has a single example
# (one template cannot be checked against anything).
bank = local_hand._type_templates()
check("the tactics template bank loads", bank is not None)
if bank:
    vecs, types = bank
    from collections import Counter
    c = Counter(types)
    check("only the four real tactics types",
          set(c) == {"swing_boost", "speed_boost", "fielding_boost", "pitch_boost"},
          str(sorted(c)))
    check("every type has more than one template", min(c.values()) > 1, str(dict(c)))
    check("templates are unit vectors",
          bool(np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-4)))

# ---- 6. read_hand EXPOSES it, or the caller cannot use any of the above.
rows = local_hand.read_hand(Image.open(os.path.join(FIX, "hand030.png")).convert("RGB"))
tac = [r for r in rows if r["kind"] == "tactics"]
check("read_hand carries a type field on every tactics row",
      bool(tac) and all("type" in r for r in tac), str(tac))
check("and never carries one on a player row",
      all("type" not in r for r in rows if r["kind"] == "player"))

# ---- 8. THE QUESTION THE DECISION ACTUALLY ASKS: does this card add power?
# CLAUDE.md section 4 -- only swing and pitch boosts do; speed and fielding carry a nonzero
# bonus that adds NONE, and decision_engine branches on exactly that. The binary is easier
# than the 4-way name and therefore answered more often, which is the whole point.
#
# MEASURED ACROSS SESSIONS (train on one run, test on another hours later, 198/61 cards),
# because a leave-one-hand-out on this corpus LEAKS: two hands from the same match holding
# the same cards in a different order land in different groups while being nearly the same
# picture (CLAUDE.md 10.22, written the same day).
#     gate 0.70   binary 42 right  9 WRONG   84% read      4-way 41 right 10 WRONG
#     gate 0.77   binary 38 right  0 WRONG   62% read      4-way 37 right  1 WRONG
#     gate 0.85   binary 22 right  0 WRONG   36% read
check("MIN_ADDS_POWER_SCORE is 0.77", local_hand.MIN_ADDS_POWER_SCORE == 0.77,
      str(local_hand.MIN_ADDS_POWER_SCORE))
check("only swing and pitch boosts count as adding power",
      set(local_hand.ADDS_POWER) == {"swing_boost", "pitch_boost"},
      str(sorted(local_hand.ADDS_POWER)))

both = disagree = binary_only = 0
for fname, meta in sorted(expected.items()):
    img = Image.open(os.path.join(FIX, fname)).convert("RGB")
    for i, c in enumerate(meta["paid"]):
        if c["kind"] != "tactics":
            continue
        name, _ = local_hand.read_tactics_type(img, i)
        ap, _ = local_hand.reads_adds_power(img, i)
        if name is not None and ap is not None:
            both += 1
            disagree += (name in local_hand.ADDS_POWER) != ap
        elif name is None and ap is not None:
            binary_only += 1
        if ap is not None and c.get("type"):
            truth = c["type"] in local_hand.ADDS_POWER
            check(f"{fname} slot {i}: adds_power {ap} matches the paid type {c['type']}",
                  ap == truth, f"got {ap}, truth {truth}")
check("the binary never contradicts the 4-way name", disagree == 0, f"{disagree} of {both}")
# THE OLD VERSION OF THIS CHECK ASKED FOR A FIXTURE CARD WHERE THE 4-WAY ABSTAINS AND
# THE BINARY ANSWERS, AND THAT CHECK CANNOT HONESTLY PASS ANY MORE. The shipped template
# bank is cut from the same corpus these fixtures come from, so the bank has effectively
# memorised them and answers the 4-way on all of them -- searching all 360 corpus cards
# finds ZERO in the band. A check that needs a fixture the bank has not seen is
# structurally vacuous here (CLAUDE.md 10.12), so it is replaced by the property that
# actually makes the binary more available, pinned as literals in the right ORDER.
#
# It still bites: raise MIN_ADDS_POWER_SCORE to or above MIN_TYPE_SCORE and the binary
# becomes strictly no more available than the name, which is the bug this guards.
# Measured cross-session, where the bank has NOT seen the test half: the binary reads
# 97.7% of cards with 0 wrong against the 4-way's 93.6%.
check("the binary's gate is LOWER than the 4-way's, so it can answer where the name cannot",
      local_hand.MIN_ADDS_POWER_SCORE < local_hand.MIN_TYPE_SCORE,
      f"{local_hand.MIN_ADDS_POWER_SCORE} < {local_hand.MIN_TYPE_SCORE}")
check("the binary never answered where the name did not, on these fixtures",
      binary_only == 0, f"{binary_only} such card(s) -- see the note above")

# ---- 7. THE RECENTRING ITSELF, which is the whole fix and which nothing else here
# guards. Cropping at the SLOT anchor instead of the FOUND card is what held this
# reader at 40.5%: the cursor lifts a card and its banner rides with it, so the fixed
# box lands on the wrong pixels. 41 corpus cards are read by the found position and
# abstained on by the anchor; four are pinned here, chosen for how far off the anchor
# they sit -- one is 63px out in x, two are 43px out in y.
#
# THIS BLOCK EXISTS BECAUSE THE FILE WITHOUT IT DID NOT BITE. Removing the recentring
# left every other check in this file green, which is the decorative-test failure
# CLAUDE.md 10.9 is about. Each card below carries the score the ANCHOR path gives it,
# so the margin is visible rather than asserted in the abstract.
def anchor_only_score(img, slot):
    """Best banner correlation from the SLOT_TACTICS anchor alone -- what the reader
    did before it recentred on the found card."""
    vecs, _ = local_hand._type_templates()
    sc = img.width / local_hand.ANCHOR_W
    ax, ay = local_hand.SLOT_TACTICS[slot][0] * sc, local_hand.SLOT_TACTICS[slot][1] * sc
    best = 0.0
    for ox, oy in local_hand.BANNER_SEARCH:
        v = local_hand._banner_at(img, ax, ay, ox, oy)
        if v is not None:
            best = max(best, float((vecs @ v).max()))
    return best


LIFT = os.path.join(_ROOT, "test_fixtures", "tactics_lifted")
lift = json.load(open(os.path.join(LIFT, "expected.json")))["cards"]
check("lifted-card fixtures present", len(lift) >= 3, f"{len(lift)} cards")
for c in lift:
    img = Image.open(os.path.join(LIFT, c["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    got = rows[c["slot"]].get("type") if c["slot"] < len(rows) else None
    dx, dy = c["offset_from_anchor"]
    check(f"{c['file']}: reads {c['type']} on a card {dx:+.0f},{dy:+.0f} off its anchor",
          got == c["type"], f"got {got!r}; the anchor path scores {c['anchor_score']}")
    # AND THE SLOT ANCHOR REALLY IS THE THING THAT FAILS -- if it could read the card
    # too, the fixture proves nothing. Scored at the anchor DIRECTLY rather than through
    # read_tactics_type(), because that function now falls back to trying both anchors
    # when no card was located, which would mask exactly what this is measuring.
    check(f"{c['file']}: the slot's own tactics anchor cannot read it",
          anchor_only_score(img, c["slot"]) < local_hand.MIN_TYPE_SCORE,
          f"anchor scores {anchor_only_score(img, c['slot']):.3f}")

for slot in range(5):
    ap, sc = local_hand.reads_adds_power(noise, slot)
    check(f"noise abstains on adds_power at slot {slot}", ap is None, f"{ap!r} @{sc:.3f}")

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
