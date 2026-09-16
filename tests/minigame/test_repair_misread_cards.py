"""A tactics card read as a player card must be re-labelled, not rejected.

Live 2026-08-31: "Fielding Play" came back as kind=player/power=1 and burned
an API retry per poll. See repair_misread_cards().
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

from orchestrator import repair_misread_cards, validate_game_state

_TURN = {"screen": "turn", "phase": "batting", "runners": [],
         "your_score": 1, "opp_score": 0}


_PLAYER = {"kind": "player", "name": "Rube Sharp", "power": 8,
           "secondary": 1, "hand_index": 4}


def _turn(hand):
    """A real hand always holds a player card; validate_game_state requires one."""
    return dict(_TURN, hand=list(hand) + [dict(_PLAYER)])


# The live failure: repaired, then passes validation.
state = _turn([{"kind": "player", "name": "Fielding Play", "power": 1,
                "secondary": 0, "hand_index": 0}])
repair_misread_cards(state)
card = state["hand"][0]
assert card["kind"] == "tactics", card
assert card["type"] == "fielding_boost", card
assert card["bonus"] == 1, card
assert "power" not in card and "secondary" not in card, card
validate_game_state(state)          # must not raise

# All four tactics names, whatever the casing.
for name, kind in [("Power Swing", "swing_boost"), ("speed boost", "speed_boost"),
                   ("  Pitch Focus  ", "pitch_boost"), ("FIELDING PLAY", "fielding_boost")]:
    s = _turn([{"kind": "player", "name": name, "power": 2, "hand_index": 0}])
    repair_misread_cards(s)
    assert s["hand"][0]["type"] == kind, (name, s)

# A real player card is untouched — this is the case that must not regress.
s = _turn([{"kind": "player", "name": "Rube Sharp", "power": 8,
            "secondary": 1, "hand_index": 0}])
repair_misread_cards(s)
assert s["hand"][0] == {"kind": "player", "name": "Rube Sharp", "power": 8,
                        "secondary": 1, "hand_index": 0}, s

# A correctly-read tactics card is untouched.
s = _turn([{"kind": "tactics", "name": "Fielding Play", "type": "fielding_boost",
            "bonus": 3, "hand_index": 0}])
repair_misread_cards(s)
assert s["hand"][0]["bonus"] == 3, s

# Junk power must not become a junk bonus — validation would reject it.
for bad in (None, True, -2, "1"):
    s = _turn([{"kind": "player", "name": "Fielding Play", "power": bad, "hand_index": 0}])
    repair_misread_cards(s)
    assert s["hand"][0]["bonus"] == 0, (bad, s)
    validate_game_state(s)

# Missing name, no name key at all: left alone for the validator to reject.
s = _turn([{"kind": "player", "name": None, "power": 1, "hand_index": 0}])
repair_misread_cards(s)
assert s["hand"][0]["kind"] == "player", s

print("test_repair_misread_cards: all assertions passed")
