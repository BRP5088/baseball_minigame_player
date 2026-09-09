"""`kind` is decided by POSITION, and a slot the fan cannot reach must not invent one.

THIS IS THE ONE FIELD WHERE THE PAID MODEL WAS RIGHT AND THE LOCAL READER WAS WRONG, which
is why it gets its own file. The fan places a card by anchor -- the tactics disc sits
60-83px left of the player disc in the same slot -- and when NO candidate reached a slot the
old code emitted `kind: "tactics"` anyway, with no digit, as though that were a reading.

Measured over 360 recorded hands: that branch emits 17 rows, and the paid model calls TEN
of them PLAYER and seven tactics. So the default was wrong more often than a coin, and it
accounted for 10 of the 13 kind disagreements on the whole corpus. Opening the frames
settled it against the local reader every time -- they are plainly player cards, with a
BATTER or PITCHER banner, a power disc and a shield.

It is CLAUDE.md 10.1's signature shape: a no-op path whose output is indistinguishable from
a real answer. Nothing failed, because a player card mislabelled tactics is simply never
played as a batter -- the cost was a missing card, not a visibly wrong one.

The banner decides now, and when there is no banner the answer is "unknown" -- ask the paid
model. The labels below are the PAID model's kind, deliberately: on this field it is the
better reader and pretending otherwise would be scoring against the thing under test.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "hand_kind")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


data = json.load(open(os.path.join(FIX, "expected.json")))
hands = data["hands"]
check("fixtures present", len(hands) >= 4, f"{len(hands)} hands")

# ---- 1. THE GATE SITS ABOVE THE PLAYER MAXIMUM, pinned as literals -------------------
# Pooling every real player card that has landed on a tactics anchor against the
# cross-session tactics scores:
#     really PLAYER   MAX 0.560
#     really TACTICS  MIN 0.595   p01 0.720
# 0.56 was tried first and sits EXACTLY ON the player maximum -- a threshold inside a
# population, which is CLAUDE.md 10.4. Comparing against the constant itself would rise
# with it and pass forever (10.11), so both edges are written out here.
check("TACTICS_PRESENT_MIN is 0.58", local_hand.TACTICS_PRESENT_MIN == 0.58,
      str(local_hand.TACTICS_PRESENT_MIN))
check("and it sits STRICTLY ABOVE the highest-scoring real player card (0.560)",
      local_hand.TACTICS_PRESENT_MIN > 0.560, str(local_hand.TACTICS_PRESENT_MIN))
check("and BELOW the lowest-scoring real tactics card across sessions (0.595)",
      local_hand.TACTICS_PRESENT_MIN < 0.595, str(local_hand.TACTICS_PRESENT_MIN))
# It must also stay below the gate that names the TYPE: presence is the easier question.
check("presence is a lower bar than identity",
      local_hand.TACTICS_PRESENT_MIN < local_hand.MIN_TYPE_SCORE,
      f"{local_hand.TACTICS_PRESENT_MIN} < {local_hand.MIN_TYPE_SCORE}")

# ---- 2. AN UNREACHED SLOT SAYS UNKNOWN, NOT TACTICS ----------------------------------
seen = 0
for h in hands:
    img = Image.open(os.path.join(FIX, h["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    for slot_s, paid_kind in h["paid_kinds"].items():
        i = int(slot_s)
        got = rows[i]["kind"] if i < len(rows) else None
        score = h["banner_score_at_those_slots"][slot_s]
        seen += 1
        # The point of the fix: it must NOT claim tactics. It is allowed to say unknown
        # (honest) or player (right); it is never allowed to say tactics.
        check(f"{h['file']} slot {i}: does not claim tactics (paid says {paid_kind}, "
              f"banner scores {score})",
              got != "tactics", f"got {got!r}")
check("every pinned slot was checked", seen >= 4, f"{seen} slots")

# ---- 3. AND AN UNKNOWN ROW CARRIES NO FABRICATED FIELDS ------------------------------
# hand_to_cards() indexes c["type"] and c["bonus"] with [] on any non-player card, so an
# "unknown" row that still carried a `type` would be read as a tactics card downstream --
# the guess coming back in through a different door.
for h in hands:
    img = Image.open(os.path.join(FIX, h["file"])).convert("RGB")
    for r in local_hand.read_hand(img):
        if r["kind"] != "unknown":
            continue
        check(f"{h['file']}: an unknown row carries no invented type/bonus/secondary",
              not any(k in r for k in ("type", "bonus", "secondary", "adds_power")),
              str(sorted(r)))

# ---- 4. THE CONTROL: a hand it CAN read is still read ---------------------------------
# Without this the file passes by making the reader answer "unknown" to everything.
ok_fix = os.path.join(_ROOT, "test_fixtures", "shields")
ok = json.load(open(os.path.join(ok_fix, "expected.json")))["hands"]
graded = 0
for h in ok[:4]:
    img = Image.open(os.path.join(ok_fix, h["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    for c in h["cards"]:
        if c["slot"] < len(rows):
            graded += 1
            check(f"control {h['file']} slot {c['slot']} still reads as a player card",
                  rows[c["slot"]]["kind"] == "player", f"got {rows[c['slot']]['kind']!r}")
check("the control actually graded something", graded >= 8, f"{graded} cards")

# ---- 5. THE OTHER HALF OF THE CONTROL, and the file did not have it ------------------
# Section 4 only guards PLAYER cards, so a mutant that turned EVERY tactics card into
# "unknown" passed the whole file -- the reader would have stopped reading tactics
# entirely and nothing here would have said so. A control must cover both directions of
# the rule it guards.
LIFT = os.path.join(_ROOT, "test_fixtures", "tactics_lifted")
lift = json.load(open(os.path.join(LIFT, "expected.json")))["cards"]
check("tactics control fixtures present", len(lift) >= 3, f"{len(lift)} cards")
tg = 0
for c in lift:
    img = Image.open(os.path.join(LIFT, c["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    i = c["slot"]
    got = rows[i]["kind"] if i < len(rows) else None
    tg += 1
    check(f"control {c['file']} slot {i}: a real {c['type']} still reads as tactics",
          got == "tactics", f"got {got!r}")
    if got == "tactics":
        check(f"control {c['file']} slot {i}: and still names its type",
              rows[i].get("type") == c["type"], f"got {rows[i].get('type')!r}")
check("the tactics control actually graded something", tg >= 3, f"{tg} cards")

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
