"""I-10: an occluded card is not only a home-plate runner's doing.

`should_redraw` used to refuse a redraw for exactly ONE occluder --
`hidden_by_homeplate_runner`. `local_hand_cards` drops ANY player slot it cannot
read (a fan-neighbour's card riding over the power disc, CLAUDE.md 10.28/10.34, a
misread power, ...) once MIN_LOCAL_HAND_CARDS still remain, and until this fix that
drop set no flag at all: `hand_players` was silently the cards that SURVIVED, and
max() over them is not the hand's true maximum. CLAUDE.md 10.34: the hidden slot was
the best card, 8 against a threshold of 6, and a discard was spent on a hand that was
never weak.

The fix is a SECOND, GENERAL flag -- `GameState.hand_incomplete` -- set wherever
`local_hand_cards` reports a dropped slot, alongside (not instead of) the existing
`hidden_by_homeplate_runner`.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import orchestrator                                                     # noqa: E402
from decision_engine import GameState, PlayerCard, should_redraw        # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---- 1. should_redraw, straight from the ticket's own example -----------------------
# A 4-card hand with a true max of 5 (say the fifth card, dropped, was an 8 -- unknown
# here, which is the whole point): visible cards alone are all <= REDRAW_POWER_THRESHOLD
# (6), so a complete-hand reading would redraw.
weak_visible = [PlayerCard(None, 5, 1), PlayerCard(None, 4, 3), PlayerCard(None, 4, 1),
                PlayerCard(None, 4, 2)]

complete = GameState(half="batting", batters_used=0, your_score=0, opp_score=0,
                     redraws_left=2)
incomplete = GameState(half="batting", batters_used=0, your_score=0, opp_score=0,
                       redraws_left=2, hand_incomplete=True)

check("hand_incomplete False -> redraw True (a 4-card weak hand still redraws)",
      should_redraw(weak_visible, complete) is True)
check("hand_incomplete True -> redraw False (the true max is unknown)",
      should_redraw(weak_visible, incomplete) is False)

# ---- 2. the home-plate flag still refuses, independently ----------------------------
homeplate = GameState(half="batting", batters_used=0, your_score=0, opp_score=0,
                      redraws_left=2, hidden_by_homeplate_runner=True)
check("hidden_by_homeplate_runner still refuses on its own",
      should_redraw(weak_visible, homeplate) is False)

# ---- 3. a strong hand never redraws, whichever flag is set --------------------------
strong = [PlayerCard(None, 9, 2)]
check("a strong hand is unaffected by hand_incomplete",
      should_redraw(strong, incomplete) is False)

# ---- 4. the default is False, so every existing caller is untouched -----------------
check("hand_incomplete defaults to False",
      GameState(half="batting", batters_used=0, your_score=0,
               opp_score=0).hand_incomplete is False)

# ---- 5. local_hand_cards' `why` is non-None whenever a player slot is DROPPED -------
# The hand-memory carry-forward counts as READ: a slot recovered from memory must NOT
# set `why`. Mirrors test_hand_memory_forgets.py's FULL fixture.
import local_hand                                                       # noqa: E402

FULL = [
    {"kind": "tactics", "x": 0, "y": 0, "digit": None, "type": "swing_boost", "bonus": 1},
    {"kind": "player", "x": 1, "y": 0, "digit": "5", "secondary": 0},
    {"kind": "player", "x": 2, "y": 0, "digit": "6", "secondary": 1},
    {"kind": "player", "x": 3, "y": 0, "digit": "7", "secondary": 0},
    {"kind": "player", "x": 4, "y": 0, "digit": "4", "secondary": 2},
]
blank = Image.new("RGB", (979, 307), (20, 20, 20))
_real_read_hand = local_hand.read_hand
try:
    orchestrator.reset_hand_memory()

    # slot 2 unreadable and NEVER seen before -- a true 4-of-5 hand.
    def four_of_five(img):
        rows = [dict(c) for c in FULL]
        rows[2]["digit"] = None
        return rows

    local_hand.read_hand = four_of_five
    cards, why = orchestrator.local_hand_cards(blank)
    check("a genuinely unreadable slot drops the hand to 4 of 5",
          cards is not None and len(cards) == 4, f"cards={cards!r}")
    check("...and `why` says so", bool(why), f"why={why!r}")

    # bank slot 2 via a clean read, then hide it again -- now memory carries it, and
    # that must NOT count as incomplete.
    local_hand.read_hand = lambda img: [dict(c) for c in FULL]
    orchestrator.local_hand_cards(blank)
    local_hand.read_hand = four_of_five
    cards, why = orchestrator.local_hand_cards(blank)
    check("a slot carried forward from memory is READ, not dropped",
          cards is not None and len(cards) == 5 and why is None, f"why={why!r}")
finally:
    local_hand.read_hand = _real_read_hand
    orchestrator.reset_hand_memory()

# ---- 6. local_game_state THREADS `why` into state["hand_incomplete"] ----------------
# Drives the full ladder with everything BEFORE the hand stubbed out of the way, exactly
# as test_local_retry_not_paid.py drives _retry_local_hand.
import local_state                                                      # noqa: E402
import table_prompt                                                     # noqa: E402

saved = (orchestrator._fast_grab, orchestrator.crop_gameplay_regions,
         orchestrator.local_hand_cards, orchestrator.read_ban_counter,
         local_state.read_result, local_state.read_phase, local_state.read_runners,
         table_prompt.at_table)
try:
    dummy = object()
    orchestrator._fast_grab = lambda: dummy
    orchestrator.crop_gameplay_regions = lambda full: [
        ("hand", dummy), ("third_base", dummy), ("second_base", dummy),
        ("first_base", dummy)]
    orchestrator.read_ban_counter = lambda full: None
    local_state.read_result = lambda full: {"is_result": False}
    local_state.read_phase = lambda img: ("batting", {})
    local_state.read_runners = lambda *a: {"count": 0}
    table_prompt.at_table = lambda full: False

    four_cards = [{"kind": "player", "name": None, "power": 5, "secondary": 0,
                  "hand_index": i} for i in range(4)]
    orchestrator.local_hand_cards = (
        lambda hand_img, phase=None, homeplate_runner=False:
        (four_cards, "played without slots [2] (unreadable)"))
    st, gap = orchestrator.local_game_state()
    check("local_game_state reaches a turn state with the stub ladder",
          st is not None and st.get("screen") == "turn", f"gap={gap!r} st={st!r}")
    if st is not None:
        check("...and hand_incomplete is threaded through from `why`",
              st.get("hand_incomplete") is True, f"st={st!r}")

    # control: nothing dropped -> hand_incomplete is False
    orchestrator.local_hand_cards = (
        lambda hand_img, phase=None, homeplate_runner=False: (four_cards, None))
    st2, gap2 = orchestrator.local_game_state()
    check("CONTROL: no drop -> hand_incomplete is False",
          st2 is not None and st2.get("hand_incomplete") is False,
          f"gap={gap2!r} st={st2!r}")
finally:
    (orchestrator._fast_grab, orchestrator.crop_gameplay_regions,
     orchestrator.local_hand_cards, orchestrator.read_ban_counter,
     local_state.read_result, local_state.read_phase, local_state.read_runners,
     table_prompt.at_table) = saved

# ---- 7. play_one_turn: state_json["hand_incomplete"] reaches the GameState it builds -
# Mirrors test_decisions.py's P4 capture of `state` via a stubbed best_batting_play.
seen_state = []
_real_batting = orchestrator.best_batting_play
_real_select_play = orchestrator.select_and_play
_real_press = orchestrator.press
orchestrator.best_batting_play = (
    lambda p, t, state: (seen_state.append(state), _real_batting(p, t, state))[1])
orchestrator.select_and_play = lambda *a, **k: None
orchestrator.press = lambda *a, **k: None
try:
    hand = [{"kind": "player", "name": "a", "power": 9, "secondary": 0, "hand_index": 0},
            {"kind": "player", "name": "b", "power": 5, "secondary": 0, "hand_index": 1},
            {"kind": "player", "name": "c", "power": 4, "secondary": 0, "hand_index": 2},
            {"kind": "player", "name": "d", "power": 3, "secondary": 0, "hand_index": 3}]
    state_json = {"screen": "turn", "phase": "batting", "your_score": 0, "opp_score": 0,
                 "discards_left": 2, "runners": [], "hand": hand,
                 "hand_incomplete": True}
    orchestrator.play_one_turn(state_json, 0)
    check("play_one_turn's GameState carries hand_incomplete=True through from state_json",
          bool(seen_state) and seen_state[-1].hand_incomplete is True,
          f"seen_state={seen_state!r}")

    seen_state.clear()
    state_json2 = dict(state_json, hand_incomplete=False)
    orchestrator.play_one_turn(state_json2, 0)
    check("CONTROL: hand_incomplete=False in state_json reaches GameState as False",
          bool(seen_state) and seen_state[-1].hand_incomplete is False,
          f"seen_state={seen_state!r}")
finally:
    orchestrator.best_batting_play = _real_batting
    orchestrator.select_and_play = _real_select_play
    orchestrator.press = _real_press

# ---- 8. QA1-F2: apply_local_readers threads `why` into state["hand_incomplete"] -----
# The finder's own reproduction: a stubbed local_hand_cards reporting a dropped slot,
# driven through apply_local_readers directly (the PAID-orientation path's own hand
# site, separate from local_game_state's -- section 6 above already covers that one).
# Before the fix, state["hand"] was set here and "hand_incomplete" never was, so
# should_redraw on this path saw a SHORT hand and read its survivors' max as the truth.
saved8 = orchestrator.local_hand_cards
try:
    three_cards = [{"kind": "player", "name": None, "power": 5, "secondary": 0,
                    "hand_index": i} for i in (0, 2, 4)]
    orchestrator.local_hand_cards = (
        lambda *a, **k: (three_cards, "played without slots [1, 3] (unreadable)"))
    state = {"screen": "turn"}
    orchestrator.apply_local_readers(state, crops={"hand": object()})
    check("apply_local_readers sets hand_incomplete when `why` is non-None",
          state.get("hand_incomplete") is True, f"state={state!r}")

    # control: nothing dropped -> hand_incomplete is False, not merely absent
    orchestrator.local_hand_cards = lambda *a, **k: (three_cards, None)
    state2 = {"screen": "turn"}
    orchestrator.apply_local_readers(state2, crops={"hand": object()})
    check("CONTROL: apply_local_readers sets hand_incomplete False when nothing dropped",
          state2.get("hand_incomplete") is False, f"state={state2!r}")
finally:
    orchestrator.local_hand_cards = saved8

# ---- 9. QA1-F2: _retry_local_hand threads `why` into state["hand_incomplete"] -------
# The other site the finder named: the local re-grab that runs after the paid
# orientation read fails to build a hand. Same defect, same fix.
saved9 = (orchestrator._fast_grab, orchestrator.crop_gameplay_regions,
          orchestrator.local_hand_cards, orchestrator.homeplate_runner_present,
          orchestrator.time)


class _InstantSleep:
    def sleep(self, *a, **k):
        pass


try:
    dummy = object()
    orchestrator._fast_grab = lambda: dummy
    orchestrator.crop_gameplay_regions = lambda full: [("hand", dummy)]
    orchestrator.homeplate_runner_present = lambda crops: False
    orchestrator.time = _InstantSleep()
    three_cards = [{"kind": "player", "name": None, "power": 5, "secondary": 0,
                    "hand_index": i} for i in (0, 2, 4)]
    orchestrator.local_hand_cards = (
        lambda *a, **k: (three_cards, "played without slots [1, 3] (unreadable)"))
    state = {"_hand_unread": "some earlier reason"}
    orchestrator._retry_local_hand(state)
    check("_retry_local_hand sets hand_incomplete when the regrab's `why` is non-None",
          state.get("hand_incomplete") is True, f"state={state!r}")

    orchestrator.local_hand_cards = lambda *a, **k: (three_cards, None)
    state2 = {"_hand_unread": "some earlier reason"}
    orchestrator._retry_local_hand(state2)
    check("CONTROL: _retry_local_hand sets hand_incomplete False when nothing dropped",
          state2.get("hand_incomplete") is False, f"state={state2!r}")
finally:
    (orchestrator._fast_grab, orchestrator.crop_gameplay_regions,
     orchestrator.local_hand_cards, orchestrator.homeplate_runner_present,
     orchestrator.time) = saved9

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
