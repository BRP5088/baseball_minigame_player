"""The >2-card reveal path: identify ours by power, strip runners from the rest.

Built from the five real "no OPPONENT card identified" drops of 2026-08-31.
Four of the five had 3+ revealed players, because exclude_runners() refuses to
strip below two and handed the whole list back, leaving the two-card power path
unreachable. See pick_opponent_card().
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

from orchestrator import exclude_runners, pick_opponent_card


def _P(name, power, secondary=0):
    return {"kind": "player", "name": name, "power": power, "secondary": secondary}


def _R(name):
    return {"name": name}


# --- the floor parameter keeps every existing caller unchanged --------------
_three = [_P("A", 4), _P("B", 5), _P("C", 6)]
assert exclude_runners(_three, [_R("B"), _R("C")]) == _three, (
    "default floor=2 must still refuse to strip 3 cards down to 1")
assert exclude_runners(_three, [_R("B"), _R("C")], floor=1) == [_three[0]], (
    "floor=1 must allow stripping to a single card")

# --- the live case: 3 revealed, 2 on base, ours identified by power ---------
# ours power 9; runners Johnny Drawers and Jacob McQueen; opponent is Coker.
_players = [_P("Jacob \"Cheesehead\" McQueen", 9), _P("Brian Coker", 8),
            _P("Johnny Drawers", 7)]
_runners = [_R("Johnny Drawers"), _R("Jacob \"Cheesehead\" McQueen")]
_opp = pick_opponent_card(_players, "pitcher", our_power=9, bonus=0,
                          runners=_runners)
assert _opp is not None and _opp["name"] == "Brian Coker", (
    f"3-card reveal with 2 runners should resolve to Brian Coker, got {_opp!r}")

# Without runners it must still abstain — that is the pre-fix behaviour and the
# guard against inventing an opponent from a list we cannot disambiguate.
assert pick_opponent_card(_players, "pitcher", our_power=9, bonus=0) is None, (
    "no runner information means the 3-card list stays undecidable")

# --- it must ABSTAIN rather than guess -------------------------------------
# Two cards share our power: ours is not uniquely identified.
_ambig = [_P("X", 9), _P("Y", 9), _P("Z", 7)]
assert pick_opponent_card(_ambig, "pitcher", our_power=9, bonus=0,
                          runners=[_R("Z")]) is None, (
    "two cards matching our power must abstain, not pick arbitrarily")

# Our card is absent entirely (a misfire): nothing matches, so no opponent.
assert pick_opponent_card(_players, "pitcher", our_power=3, bonus=0,
                          runners=_runners) is None, (
    "our power absent from the reveal must abstain")

# Runners strip more than one card away, leaving two: still ambiguous.
_four = [_P("A", 9), _P("B", 8), _P("C", 7), _P("D", 6)]
assert pick_opponent_card(_four, "pitcher", our_power=9, bonus=0,
                          runners=[_R("D")]) is None, (
    "two survivors after stripping is not a unique answer")

# --- the boost is honoured on this path too --------------------------------
_boost = [_P("Runner", 5), _P("Ours", 9), _P("Theirs", 6)]
_opp2 = pick_opponent_card(_boost, "batter", our_power=7, bonus=2,
                           runners=[_R("Runner")])
assert _opp2 is not None and _opp2["name"] == "Theirs", (
    f"power+bonus should identify our card, got {_opp2!r}")

# --- existing two-card behaviour is untouched ------------------------------
assert pick_opponent_card([_P("Batter", 7), _P("Rube Sharp", 8)],
                          "Batter", 7, 0)["name"] == "Rube Sharp"
assert pick_opponent_card([_P("Batter", 7), _P("Batter", 7)], "Batter", 7, 0) is None

print("test_reveal_three_cards: all assertions passed")
