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
# The gate is pinned as a LITERAL. It is no longer "between two populations": with 117
# templates over 196 cards the right answers reach down to 0.342 and the worst WRONG reaches
# 0.815, so they OVERLAP and no gap exists. It is a SAFETY TRADE, and the trade is
# asymmetric -- an abstention costs one paid call, a wrong type plays a speed boost as if it
# added power in a $50 match. 0.88 clears the worst observed wrong by 8%.
check("MIN_TYPE_SCORE is 0.88", local_hand.MIN_TYPE_SCORE == 0.88,
      str(local_hand.MIN_TYPE_SCORE))
check("and it clears the worst measured WRONG answer (0.815) with margin",
      local_hand.MIN_TYPE_SCORE >= 0.815 * 1.05, str(local_hand.MIN_TYPE_SCORE))

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

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
