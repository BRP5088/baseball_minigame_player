"""Smoke test for orchestrator.validate_game_state — run: python test_validate_game_state.py"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import


import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import validate_game_state

# Valid turn state passes.
validate_game_state({
    "screen": "turn",
    "phase": "batting",
    "runners": [],
    "your_score": 0,
    "opp_score": 0,
    "hand": [
        {"kind": "player", "name": "A", "power": 5, "secondary": 1, "hand_index": 0},
        {"kind": "tactics", "name": "Boost", "type": "swing_boost", "bonus": 2, "hand_index": 1},
    ],
})

# Empty hand / no collection (e.g. result screen) passes.
validate_game_state({"screen": "result", "result_won": True})

def _T(hand=None, **over):
    """A structurally COMPLETE turn payload, with one field optionally spoiled.

    A turn screen requires runners/your_score/opp_score (orchestrator.py:1957).
    Omitting them made every targeted case below raise for the missing field
    instead of for the guard it names — which is the same defect as the
    phantom power-1 fixture, and would have left all nine guards deletable.
    """
    state = {"screen": "turn", "phase": "batting",
             "hand": hand if hand is not None else [_P()],
             "runners": [], "your_score": 0, "opp_score": 0, "discards_left": 2}
    state.update(over)
    return state


def _P(**over):
    """A structurally valid player card, with one field optionally spoiled.

    Built this way so a bad_cases entry fails for the guard it TARGETS rather
    than for a missing field an earlier guard catches.
    """
    card = {"kind": "player", "name": "Rube Sharp", "power": 8,
            "secondary": 1, "hand_index": 0}
    card.update(over)
    return card


bad_cases = [
    # --- one case per guard that survived DELETION against all 16 files ----
    # QA 2026-08-26: nine separate guards in validate_game_state could each be
    # replaced with `if False:` and the whole suite stayed green. This block
    # exists so each guard is load-bearing. Every entry is built so that no
    # EARLIER guard can reject it first — that was the trap the phantom
    # power-1 fixture fell into (it lacked hand_index, so it was rejected
    # before the power check it claimed to exercise, and the power guard was
    # deletable anyway).
    #
    # `_P(**over)` = a structurally valid player card with one field spoiled.
    {"screen": "result"},                                    # empty result payload
    # A dict, NOT a long string: with runners="not a list" the length is 10,
    # so deleting the type guard merely let the >3 guard fire and the case
    # raised either way. len({...}) == 1 passes the count guard, so only the
    # type guard can reject this.
    _T(runners={"first": {"name": "a"}}),
    _T(runners=[{"name": "a"}, {"name": "b"}, {"name": "c"},
                {"name": "d"}, {"name": "e"}]),              # 5 on a 3-base diamond
    # discards_left=99 moved out of this raise-table: it is now clamped to 0
    # rather than rejected. Asserted below, under "discards_left must respect".
    _T(discards_left="two"),   # non-int is still a rejectable read
    _T(your_score="seven"),
    _T(opp_score=-1),
    # A VALID player card must sit alongside the bad tactics card. With the
    # tactics card alone, deleting the bonus guard just let the later
    # "no player card in hand" guard fire instead — the case raised either
    # way and the mutation survived.
    _T(hand=[_P(), {"kind": "tactics", "type": "swing_boost",
                    "bonus": None, "hand_index": 1}]),
    # NOTE: with CARD_POWER_MIN raised to 4 the `isinstance(power, bool)`
    # clause is now UNREACHABLE — True==1 and False==0 are both below the
    # floor, so the range check rejects a bool first. This case therefore
    # pins the OUTCOME (a bool is rejected) rather than which guard does it;
    # deleting the bool clause is a no-op for power, though it still matters
    # for `secondary`, whose range starts at 0 and does admit True.
    _T(hand=[_P(power=True)]),
    _T(hand=[_P(secondary=99)]),
    _T(hand=[_P(name=123)]),
    # Two-sided on the power floor: below and above must both raise. The
    # matching "power=CARD_POWER_MIN must NOT raise" lives in good_cases.
    _T(hand=[_P(power=3)]),
    _T(hand=[_P(power=16)]),
    {"screen": "nonsense"},
    {"screen": "turn", "phase": "batting", "hand": [{"kind": "player", "power": 5, "hand_index": 7}]},  # out of range
    {"screen": "turn", "phase": "batting", "hand": [
        {"kind": "player", "power": 5, "hand_index": 0},
        {"kind": "player", "power": 3, "hand_index": 0},  # duplicate
    ]},
    {"screen": "turn", "phase": "batting", "hand": [{"kind": "player", "hand_index": 0}]},  # missing power
    _T(hand=[_P(), {"kind": "tactics", "type": "not_a_real_type",
                    "bonus": 1, "hand_index": 1}]),
    _T(hand=[_P(), {"kind": "wat", "hand_index": 1}]),
    {"screen": "ban_screen", "collection": [{"name": "X", "row": "0", "col": 0}]},  # row not int
    # A turn with no usable phase must be rejected: play_one_turn() would
    # otherwise fall through to the PITCHING strategy on a batting turn.
    {"screen": "turn", "hand": []},                    # phase missing
    {"screen": "turn", "phase": None, "hand": []},     # phase explicitly null
    {"screen": "discard_prompt", "phase": "nonsense", "hand": []},
    # Turn-completeness: both of these USED TO PASS and then crash deeper in
    # play_one_turn() with the exact KeyError/IndexError this validator promises
    # to convert. A tactics-only hand is what a mid-deal frame looks like.
    {"screen": "turn", "phase": "batting",
     "hand": [{"kind": "player", "name": "A", "power": 5, "secondary": 1, "hand_index": 0}]},
    {"screen": "turn", "phase": "batting", "runners": [], "your_score": 0, "opp_score": 0,
     "hand": [{"kind": "tactics", "name": "Boost", "type": "swing_boost", "bonus": 2, "hand_index": 0}]},
]
for case in bad_cases:
    try:
        validate_game_state(case)
        raise AssertionError(f"expected ValueError for {case!r}")
    except ValueError:
        pass

print("validate_game_state: all cases passed")


# --- the power floor must track the roster, not a typed-in literal -------
# CARD_POWER_MIN was 1, which let TACTICS BONUS digits (1-3) through as player
# powers. Live 2026-08-26: a hand read as one `power=1` card passed validation
# and the engine burned a capped discard on it; the same misread class caused
# 2 of that run's 5 misfires. 4 is the roster minimum — pinned here because the
# roster is self-extending and a hardcoded floor would rot silently.
from orchestrator import CARD_POWER_MIN, CARD_POWER_MAX, KNOWN_BAN_ROSTER

_roster_min = min(c.power for c in KNOWN_BAN_ROSTER.values())
_roster_max = max(c.power for c in KNOWN_BAN_ROSTER.values())
assert CARD_POWER_MIN == _roster_min, (
    f"CARD_POWER_MIN={CARD_POWER_MIN} but the weakest catalogued card is "
    f"{_roster_min} — a floor below the real minimum lets tactics bonus "
    "digits through as player powers")
assert CARD_POWER_MAX == _roster_max, (
    f"CARD_POWER_MAX={CARD_POWER_MAX} but the strongest catalogued card is "
    f"{_roster_max}. A looser ceiling lets a HALLUCINATED card through: on "
    "2026-08-26 vision reported 'Spike-B (power 10)' while the frame showed a "
    "hand of 9/6/6/7/4 and no such card exists. The engine played it and the "
    "misfire detector then fired on a card that was never in the hand.")

# The exact hallucination, rejected.
try:
    validate_game_state(_T(hand=[_P(name="Spike-B", power=10)]))
    raise AssertionError("the power-10 hallucination still validates")
except ValueError:
    pass
assert CARD_POWER_MIN > 3, (
    "1-3 is the tactics bonus digit range; a player power there is a misread")

# The live payload that cost a discard must now be rejected outright.
_phantom = {"screen": "turn", "phase": "batting", "your_score": 0, "opp_score": 0,
            "discards_left": 2, "runners": [],
            # hand_index is REQUIRED. Without it this payload was rejected by an
            # earlier check and never reached the power test at all — so the
            # mutation `CARD_POWER_MIN <= power` -> `1 <= power` survived and this
            # assertion proved nothing (QA, 2026-08-26).
            "hand": [{"kind": "player", "name": "Batter", "power": 1,
                      "secondary": 0, "hand_index": 0}]}
try:
    validate_game_state(_phantom)
    raise AssertionError(
        "a hand whose only player card has power 1 still validates — that is "
        "the exact payload that burned a discard on 2026-08-26")
except ValueError:
    pass

print(f"OK: power floor {CARD_POWER_MIN} matches the roster minimum; the "
      "phantom power-1 hand is rejected")


# --- the floor must be two-sided, or the constant is decorative ----------
# A guard that only ever rejects proves nothing about where the boundary is:
# CARD_POWER_MIN could be 9 and every "must raise" case above would still
# pass. Pin the weakest LEGAL card as accepted.
_at_floor = _T(hand=[_P(power=CARD_POWER_MIN)])
validate_game_state(_at_floor)          # must not raise

_at_ceiling = _T(hand=[_P(power=CARD_POWER_MAX)])
validate_game_state(_at_ceiling)        # must not raise

# And a fully ordinary turn must survive every guard added above — otherwise
# a validator that rejects EVERYTHING would satisfy all the bad_cases.
validate_game_state(_T(hand=[_P(), _P(hand_index=1, power=5, name="Brian Coker")],
                       runners=[{"name": "Johnny Drawers", "power": 7, "secondary": 1}],
                       your_score=2, opp_score=1))

print("OK: power floor and ceiling are two-sided; an ordinary turn still validates")


# --- discards_left must respect what the screen actually shows -----------
# The DISCARDS indicator has exactly TWO dots (frames 20260826_173511_095 and
# _174500). Vision repeatedly claimed "3 discard(s) left", the loop issued a
# discard the game could not honour, the hand did not change, and it decided
# to discard again — 33 attempts across 4 matches where at most 8 were
# possible, with the counter observed INCREASING between turns.
from orchestrator import MAX_DISCARDS_PER_MATCH

assert MAX_DISCARDS_PER_MATCH == 2, (
    f"MAX_DISCARDS_PER_MATCH={MAX_DISCARDS_PER_MATCH}; the on-screen indicator "
    "has two dots, and a looser bound lets a hallucinated count drive a "
    "discard loop")
# An out-of-range count no longer RAISES — it is clamped to 0. The invariant
# that matters is unchanged and still asserted here: a hallucinated count must
# never authorise a discard. Raising also achieved that, but cost an API call
# per retry, and vision was measured returning the same bad count 11 polls
# running on 2026-08-31 — a retry cannot fix a stable misread.
for _bad in (MAX_DISCARDS_PER_MATCH + 1, 4, 99, -1):
    _s = _T(discards_left=_bad)
    validate_game_state(_s)                      # must not raise
    assert _s["discards_left"] == 0, (
        f"discards_left={_bad} clamped to {_s['discards_left']}, not 0 — a "
        "count that cannot be trusted must not authorise a discard, which is "
        "the exact hallucination behind the 2026-08-26 discard loop")

# A non-int is a different failure (a confused scoreboard read) and still raises.
for _junk in ("two", True, 1.5, []):
    try:
        validate_game_state(_T(discards_left=_junk))
        raise AssertionError(f"discards_left={_junk!r} should not validate")
    except ValueError:
        pass
# ...and the legal values must all survive.
for _n in range(0, MAX_DISCARDS_PER_MATCH + 1):
    validate_game_state(_T(discards_left=_n))

print(f"OK: discards_left bounded at {MAX_DISCARDS_PER_MATCH} (observed on "
      "screen), 0..2 accepted, out-of-range clamped to 0, non-int rejected")
