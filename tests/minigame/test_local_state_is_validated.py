"""The LOCAL path must not act on a reading the paid path would have rejected.

validate_game_state exists to turn a hallucinated card into "a clear, retryable error
instead of a stack trace pointing at the wrong function". It has exactly ONE call site:
read_game_state -- the PAID reader. With PAID_MODEL_ENABLED False (the shipped default
and the user's standing instruction) every turn takes local_game_state and the validator
runs for nobody.

That was harmless while the runner could not play at all: until 2026-09-13
read_state_for_turn made the orientation read paid, so run() died after 15 stuck
attempts every match. Fixing that turned a dead branch into a LIVE unvalidated one, so
the two readings the validator would have caught now reach the engine.

    a power of 1      digit_templates.npz holds 1 x200 and 2 x200 -- the TACTICS BONUS
                      digits -- and read_digit argmaxes the whole bank while `kind` is
                      decided separately, so a player row can carry one. Found in the
                      archive: hand_samples/hand_20260824_201140_317.jpg slot 0 reads '1'.
    a missing score   local_game_state sets your_score/opp_score only inside a try, with
                      no setdefault, and play_one_turn indexes them unconditionally.

Both are fixed where the path actually runs, not where the validator sits.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import orchestrator as o
import local_hand

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


def hand(*powers):
    return [{"kind": "player", "digit": str(p), "secondary": "1", "_art": None}
            for p in powers]


def read(rows):
    _saved = local_hand.read_hand
    try:
        local_hand.read_hand = lambda *a, **k: rows
        o._hand_memory.clear()
        return o.local_hand_cards("FRAME")
    finally:
        local_hand.read_hand = _saved
        o._hand_memory.clear()


# --- a power outside 4-9 is a MISREAD, and must not reach the engine ---------
# THE HARM, reproduced by the sweep that found it: a true hand [9,5,4,4,5] read as
# [1,5,4,4,5] puts max power at 5, under REDRAW_POWER_THRESHOLD, so should_redraw
# fires and the engine discards min(power) -- THE REAL 9. One of only two discards
# in the match, spent to throw the best card in it.
cards, why = read(hand(1, 9, 5, 4, 4))
_powers = [] if cards is None else sorted(c["power"] for c in cards)
check(cards is not None and 1 not in _powers,
      f"a power of 1 reached the hand: {_powers}")
check(9 in _powers,
      f"the rest of the hand must survive a single misread (10.28), got {_powers}")
check(cards is not None and len(cards) == 4,
      f"expected 4 usable cards, got {cards if cards is None else len(cards)}")

for bad in (0, 1, 2, 3, 10, 11, 99):
    c2, _w2 = read(hand(bad, 9, 5, 4, 4))
    _p2 = [] if c2 is None else [x["power"] for x in c2]
    check(bad not in _p2, f"power {bad} reached the hand: {_p2}")

# CONTROL: every LEGAL power must still come through, or this rule would quietly
# empty the hand and read exactly like a working guard (10.1).
for good in range(o.CARD_POWER_MIN, o.CARD_POWER_MAX + 1):
    c3, _w3 = read(hand(good, 9, 5, 4, 4))
    _p3 = [] if c3 is None else [x["power"] for x in c3]
    check(good in _p3 and len(_p3) == 5,
          f"CONTROL: legal power {good} was dropped — got {_p3}")

# ...and the range is pinned to the roster, not to a literal typed here twice
# (10.11: a test that asserts against the constant it guards passes forever).
check((o.CARD_POWER_MIN, o.CARD_POWER_MAX) == (4, 9),
      f"the power range moved to {o.CARD_POWER_MIN}-{o.CARD_POWER_MAX}; section 4 says "
      "4-9 over all 33 catalogued cards, and 1-2 are the tactics bonus digits")

# --- the score KEYS must always exist ---------------------------------------
# A None score is harmless: decision_engine reads none of your_score, opp_score,
# target_score or batters_used, and section 4 says the score must not change which card
# to play. It is the MISSING KEY that ends the match -- play_one_turn indexes it, run()
# counts 15 stuck attempts and stops with stop_reason="turn_action_failed", $50 spent.
#
# BEHAVIOURAL. A first version of this check exec'd the setdefault lines out of the
# source, which is a source-text assertion wearing a disguise -- the exact thing that
# broke twice in this session on correct code. Drive the real function instead, with
# ocr_scoreboard raising the way a missing scoreboard crop makes it raise.
import local_state


def local_state_with_broken_scoreboard():
    saved = (o._fast_grab, o.crop_gameplay_regions, o.ocr_scoreboard,
             local_hand.read_hand, local_state.read_phase,
             local_state.read_result, local_state.read_runners)
    try:
        o._fast_grab = lambda: "FRAME"
        # the three base crops too: local_game_state treats an unread diamond as a
        # GAP, not a default, so without them the state never reaches the score keys
        o.crop_gameplay_regions = lambda img: [
            ("hand", "H"), ("scoreboard", "S"),
            ("first_base", "B1"), ("second_base", "B2"), ("third_base", "B3")]
        o.ocr_scoreboard = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("no scoreboard on this frame"))
        local_hand.read_hand = lambda *a, **k: hand(9, 5, 4, 4, 5)
        local_state.read_phase = lambda *a, **k: ("batting", {})
        local_state.read_result = lambda *a, **k: {"is_result": False, "outcome": None}
        local_state.read_runners = lambda *a, **k: {"count": 0, "bases": {},
                                                    "occupied": {}, "speeds": {}}
        o._hand_memory.clear()
        return o.local_game_state()
    finally:
        (o._fast_grab, o.crop_gameplay_regions, o.ocr_scoreboard,
         local_hand.read_hand, local_state.read_phase,
         local_state.read_result, local_state.read_runners) = saved
        o._hand_memory.clear()


_st, _gap = local_state_with_broken_scoreboard()
check(_st is not None, f"the state came back as a GAP ({_gap}) — cannot test the keys")
if _st is not None:
    check("your_score" in _st and "opp_score" in _st,
          f"an ocr_scoreboard that RAISES leaves the score keys absent: "
          f"{sorted(_st)} — play_one_turn indexes them and the match dies after 15 polls")
    check(_st.get("your_score") is None and _st.get("opp_score") is None,
          f"an unreadable scoreboard must default to None, not a number: "
          f"your={_st.get('your_score')!r} opp={_st.get('opp_score')!r}")
    # ...and the caller must survive it, which is the thing that actually matters.
    try:
        _ = _st["your_score"], _st["opp_score"]
        _indexable = True
    except KeyError:
        _indexable = False
    check(_indexable, "play_one_turn's unconditional index would still raise")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)
