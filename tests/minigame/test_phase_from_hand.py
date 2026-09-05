"""A phase that contradicts an unambiguous hand must be corrected.

play_one_turn() branches on `phase` alone, and the engines sort the hand purely
by power — best_batting_play() never checks that its pick is a BATTER. So a
misread phase does not just apply the wrong strategy, it can play a card that is
wrong for the turn.

2026-09-01 logs, 12 of ~255 decisions contradicted themselves:
    9 x  Playing Pitcher (power N)        <- batting engine, pitcher card
    3 x  Playing Batter (pitch focus N)   <- pitching engine, batter card
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

from orchestrator import repair_phase_from_hand

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def _p(name, i=0):
    return {"kind": "player", "name": name, "power": 7, "secondary": 0,
            "hand_index": i}


def _state(phase, hand):
    return {"screen": "turn", "phase": phase, "hand": hand,
            "runners": [], "your_score": 0, "opp_score": 0}


# --- the live contradiction: batting engine on a hand of pitchers -----------
s = _state("batting", [_p("Pitcher", 0), _p("Pitcher", 1), _p("Pitcher", 2)])
repair_phase_from_hand(s)
check(s["phase"] == "pitching",
      f"phase stayed {s['phase']!r} with an all-pitcher hand — this is the "
      "'Playing Pitcher (power 9)' case, which played a pitcher while batting")

s = _state("pitching", [_p("Batter", 0), _p("Batter", 1)])
repair_phase_from_hand(s)
check(s["phase"] == "batting",
      f"phase stayed {s['phase']!r} with an all-batter hand")

# --- agreement is left alone ----------------------------------------------
for phase, banner in (("batting", "Batter"), ("pitching", "Pitcher")):
    s = _state(phase, [_p(banner, 0), _p(banner, 1)])
    repair_phase_from_hand(s)
    check(s["phase"] == phase,
          f"changed an already-correct {phase} phase to {s['phase']!r}")

# --- IT MUST ABSTAIN when the hand is not evidence -------------------------
# A real player name says nothing about whose turn it is.
s = _state("batting", [_p("Rube Sharp", 0), _p("Pitcher", 1)])
repair_phase_from_hand(s)
check(s["phase"] == "batting",
      "a hand containing a REAL name was treated as evidence; only the generic "
      "type banners carry phase information")

# A hand of ALL real names must abstain too. Without the per-card guard these
# collapse to a single "unknown" value, which passes a naive unanimity check and
# would set phase to None — caught by mutation testing, not by inspection.
s = _state("batting", [_p("Rube Sharp", 0), _p("Johnny Drawers", 1)])
repair_phase_from_hand(s)
check(s["phase"] == "batting",
      f"an all-real-names hand set the phase to {s['phase']!r}; real names "
      "carry no phase information and must leave it alone")

# A mixed hand of banners proves nothing either.
s = _state("batting", [_p("Pitcher", 0), _p("Batter", 1)])
repair_phase_from_hand(s)
check(s["phase"] == "batting", "a mixed hand must not flip the phase")

# An empty hand, or one with only tactics, is not evidence.
s = _state("batting", [])
repair_phase_from_hand(s)
check(s["phase"] == "batting", "an empty hand must not flip the phase")
s = _state("batting", [{"kind": "tactics", "name": "Power Swing",
                        "type": "swing_boost", "bonus": 2, "hand_index": 0}])
repair_phase_from_hand(s)
check(s["phase"] == "batting", "a tactics-only hand must not flip the phase")

# A phase that is already unusable is left for validate_game_state to reject.
s = _state(None, [_p("Pitcher", 0)])
repair_phase_from_hand(s)
check(s["phase"] is None, "a null phase must be left for the validator")

# Casing and whitespace must not defeat it — vision returns both.
s = _state("batting", [_p("  PITCHER  ", 0)])
repair_phase_from_hand(s)
check(s["phase"] == "pitching", "banner matching must ignore case and padding")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  phase repair: an unanimous hand overrides a contradicting phase; real "
      "names, mixed hands, empty hands and tactics-only hands all abstain")
