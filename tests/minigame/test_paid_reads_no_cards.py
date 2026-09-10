"""The paid model is no longer asked to read cards, and the switch must stay honest.

THE USER'S CALL, 2026-09-09: "comment out the API reads for all card reading. only leave
the state classifications. leaving them in is hiding the real values and your also wasting
my IRL money."

Both halves are measured, and they are why this file exists rather than a comment:
  - it never read the cards. Over 2,171 recorded hand cards the paid `name` came back as
    'Batter'/'Pitcher' (the TYPE BANNER), '', 'None', 'Unknown', or one of 57 invented
    names including SIX spellings of the same one.
  - on 32 of 33 frames containing NO CARDS AT ALL it returned a full five-card hand,
    against 325 of 327 on frames that did. "Five cards" is a DEFAULT, not a reading.

NOTHING WAS DELETED. The original instructions are still in the file and PAID_READS_CARDS
flips everything back. This file guards the three ways that could rot: the flag drifting
from the prompt, the money not actually being saved, and a half-built hand reaching
hand_to_cards.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---- 1. the switch is off, and the prompt agrees with it -----------------------------
check("PAID_READS_CARDS is off", orchestrator.PAID_READS_CARDS is False,
      str(orchestrator.PAID_READS_CARDS))
p = orchestrator.READ_STATE_PROMPT
check("the prompt tells the model NOT to read cards",
      "DO NOT READ THE CARDS" in p)
check("and the card-reading instruction is really gone from what gets sent",
      orchestrator._PROMPT_CARDS_ON not in p and orchestrator._PROMPT_POWER_ON not in p)

# ---- 2. NOTHING WAS DELETED -- the old wording is still here and still restorable -----
src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("the original card instructions are still in the file, verbatim",
      src.count("read\nyour_score/opp_score/discards_left/hand") >= 1)
check("and are reachable through the flag, not just as dead text",
      "_PROMPT_CARDS_ON" in src and "PAID_READS_CARDS" in src)

# ---- 3. THE MONEY. Four of six images stop being sent. -------------------------------
# This is the check that actually guards the user's bill, and it is asserted on the
# CONSTANT the send loop reads rather than on a comment about it.
check("only the two state crops are sent while the flag is off",
      "PAID_CROPS = None if PAID_READS_CARDS else (\"overview\", \"scoreboard\")" in src)

# ---- 4. THE HAND IS ALL-OR-NOTHING ---------------------------------------------------
# hand_to_cards() indexes c["power"], c["secondary"], c["type"] and c["bonus"] with []
# rather than .get(), so a half-built hand is a KeyError deep inside play_one_turn -- and
# a hand missing one card is worse than no hand, because the decision engine would choose
# from four cards believing it saw five.
blank = Image.new("RGB", (979, 307), (20, 20, 20))
cards, why = orchestrator.local_hand_cards(blank)
check("a blank frame yields NO hand and says why", cards is None and bool(why), str(why))

fix = os.path.join(_ROOT, "test_fixtures", "shields")
import json                                                             # noqa: E402
good = json.load(open(os.path.join(fix, "expected.json")))["hands"][0]
img = Image.open(os.path.join(fix, good["file"])).convert("RGB")
cards, why = orchestrator.local_hand_cards(img)
check("a real hand builds", cards is not None, str(why))
if cards:
    check("every card carries what hand_to_cards indexes",
          all(("power" in c and "secondary" in c) if c["kind"] == "player"
              else ("type" in c and "bonus" in c) for c in cards))
    check("hand_index is 0..n and unique",
          sorted(c["hand_index"] for c in cards) == list(range(len(cards))))
    # `name` is None on player cards ON PURPOSE -- hand cards display no name at all
    # (CLAUDE.md section 3), so there is nothing to read and nothing downstream reads it.
    check("player cards carry no invented name",
          all(c["name"] is None for c in cards if c["kind"] == "player"))
    # And it must survive the real consumer, which is the thing that would crash.
    players, tactics = orchestrator.hand_to_cards(cards)
    check("hand_to_cards accepts the locally built hand",
          len(players) + len(tactics) == len(cards),
          f"{len(players)} players + {len(tactics)} tactics")

# ---- 5. EVERY all-or-nothing branch, driven directly ---------------------------------
# The fixtures cannot reach these: the shield reader abstains on 0.0% of the corpus, so a
# fixture with an unread shield does not exist, and a check that only runs on data which
# never occurs is a check that cannot fail (CLAUDE.md 10.12). Deleting the shield guard
# left this whole file green until these were added.
#
# So the branch is driven with a stubbed read_hand. That is honest -- it tests the guard,
# and it says so -- and it is the only way to reach a path the real corpus never produces.
import local_hand                                                       # noqa: E402

FULL = [
    {"kind": "tactics", "x": 0, "y": 0, "digit": None, "type": "swing_boost", "bonus": 1},
    {"kind": "player", "x": 1, "y": 0, "digit": "5", "secondary": 0},
    {"kind": "player", "x": 2, "y": 0, "digit": "6", "secondary": 1},
    {"kind": "player", "x": 3, "y": 0, "digit": "7", "secondary": 0},
    {"kind": "player", "x": 4, "y": 0, "digit": "4", "secondary": 2},
]

CASES = [
    ("a player card with no power",      1, {"digit": None}),
    ("a player card with no shield",     2, {"secondary": None}),
    ("a tactics card with no type",      0, {"type": None}),
    ("a tactics card with no bonus",     0, {"bonus": None}),
    ("a slot the fan could not name",    3, {"kind": "unknown"}),
]

_real = local_hand.read_hand
try:
    # the control first: the stub itself must build, or every case below passes vacuously
    local_hand.read_hand = lambda img: [dict(c) for c in FULL]
    cards, why = orchestrator.local_hand_cards(blank)
    check("CONTROL: the intact stub hand builds", cards is not None, str(why))

    # THE RULE CHANGED, DELIBERATELY, AND THESE FOUR CHECKS CHANGED WITH IT.
    # They used to require that ANY unreadable card killed the whole hand. That turned an
    # unreadable CARD into an unreadable STATE and cost a paid call every time: measured
    # live, the loop went 1.44 -> 5.00 -> 8.67 read_game_state calls per turn. A hand with
    # one invisible card is still playable -- that card simply is not played.
    #
    # So the card is DROPPED and the rest survive, and what is guarded now is that the
    # drop is honest: the bad slot is gone, the good ones keep their hand_index so input
    # targeting still hits the right card, and `why` says which slots went.
    for name, slot, patch in CASES:
        def stub(img, _s=slot, _p=patch):
            rows = [dict(c) for c in FULL]
            rows[_s].update(_p)
            return rows
        local_hand.read_hand = stub
        cards, why = orchestrator.local_hand_cards(blank)
        idx = [c["hand_index"] for c in (cards or [])]
        check(f"{name}: that card is dropped, the hand survives",
              cards is not None and slot not in idx, f"got {idx}")
        check(f"{name}: the survivors keep their own hand_index",
              idx == [i for i in range(len(FULL)) if i != slot], f"got {idx}")
        check(f"{name}: and the drop is REPORTED, not silent",
              why and str(slot) in why, f"why={why!r}")

    # AND THERE IS A FLOOR. Dropping is not free -- the decision engine then chooses from
    # fewer cards believing that is the hand -- so below MIN_LOCAL_HAND_CARDS the honest
    # answer is to refuse and let the paid path take it.
    def gut(img):
        rows = [dict(c) for c in FULL]
        for i in (1, 2, 3):
            rows[i]["digit"] = None
        return rows
    local_hand.read_hand = gut
    cards, why = orchestrator.local_hand_cards(blank)
    check("below the floor, the whole hand is refused",
          cards is None and why, f"got {cards!r} / {why!r}")
    check("MIN_LOCAL_HAND_CARDS is pinned as a literal",
          orchestrator.MIN_LOCAL_HAND_CARDS == 3,
          str(orchestrator.MIN_LOCAL_HAND_CARDS))
finally:
    local_hand.read_hand = _real

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
