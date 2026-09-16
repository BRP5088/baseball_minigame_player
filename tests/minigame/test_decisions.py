"""Tests for what the bot actually PLAYS. Offline: no game, no API, no input.

WHY THIS EXISTS
---------------
QA (2026-08-25) inverted five decisions — play the WORST batter, play the WORST
pitcher, never boost, always discard, ban the STRONGEST cards — and
`./run_tests.sh` output was **byte-identical** every time. The entire strategy
layer had zero coverage: `test_run_state_machine.py` stubs `play_one_turn` out,
its ban assertions check the COUNT of bans and never their identity, and
`decision_engine.py`'s own `__main__` asserts are never executed by anything.

That gap hid a real defect for the life of the project: `best_pitching_play`
sorted by `(secondary, power)` with secondary PRIMARY, so one fielding pip
outranked any amount of pitch focus — a 4/1 played over a 9/0. Measured over
20,000 simulated runner turns it gave up the stronger pitcher on 73.6% of them,
3.30 power on average. Head-to-head over 800 matches the corrected version wins
53.9% to 23.9%.

These assertions are about IDENTITY — which card — not counts.
"""

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

from decision_engine import (FIELDING_POWER_BUDGET, GameState, PlayerCard,
                             TacticsCard, TacticsType, best_batting_play,
                             best_pitching_play, choose_bans, should_redraw)

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def st(half="pitching", runners=(), **kw):
    return GameState(half=half, batters_used=kw.get("batters_used", 0),
                     your_score=kw.get("your_score", 0),
                     opp_score=kw.get("opp_score", 0),
                     target_score=kw.get("target_score"),
                     runners=list(runners),
                     redraws_left=kw.get("redraws_left", 2))


ACE = PlayerCard("Ace", 9, 0)
SCRUB = PlayerCard("Scrub", 4, 3)
MID = PlayerCard("Mid", 8, 1)
RUNNER = PlayerCard("Runner", 5, 1)

# --- BATTING: always the highest power ------------------------------------
d = best_batting_play([SCRUB, ACE, MID], [], st(half="batting"))
check(d.player_card is ACE,
      f"batting played {d.player_card.name} (power {d.player_card.power}) over "
      f"Ace (9) — the confirmed rule is that a hit needs power > the "
      "opponent's, so the strongest batter is always right")

# A swing boost must be attached; holding it back lost 79% of a 500-match
# tournament (simulate.py, 2026-08-23).
sw = TacticsCard("Swing", TacticsType.SWING_BOOST, 2)
d = best_batting_play([ACE], [sw], st(half="batting"))
check(d.tactics_card is sw,
      "an available swing boost was not attached — extra power is never wasted "
      "under the confirmed rule")

# A speed boost adds NO power (power_bonus, simulate.py:97) and must never be
# taken over a swing boost.
sp = TacticsCard("Speed", TacticsType.SPEED_BOOST, 3)
d = best_batting_play([ACE], [sp, sw], st(half="batting", runners=[RUNNER]))
check(d.tactics_card is sw,
      f"batting attached {d.tactics_card.name} over the swing boost — a speed "
      "boost adds zero power, so this trades a confirmed gain for a "
      "speculative one")

# --- PITCHING: the regression that cost the most --------------------------
# No runners: pure power.
d = best_pitching_play([SCRUB, ACE], [], st())
check(d.player_card is ACE,
      f"pitching with no runners played {d.player_card.name} over Ace (9)")

# Runners on: fielding may break a tie, but must NOT buy more than the budget.
d = best_pitching_play([SCRUB, ACE], [], st(runners=[RUNNER]))
check(d.player_card is ACE,
      f"THE REGRESSION: with a runner on, pitching played {d.player_card.name} "
      f"(power {d.player_card.power}, fielding {d.player_card.secondary}) "
      f"instead of Ace (9/0). Fielding outranking pitch focus concedes home "
      f"runs on exactly the turns that matter most.")

# Within the budget, fielding is allowed to win.
NEAR = PlayerCard("Near", 9 - FIELDING_POWER_BUDGET, 3)
d = best_pitching_play([NEAR, ACE], [], st(runners=[RUNNER]))
check(d.player_card is NEAR,
      f"a pitcher {FIELDING_POWER_BUDGET} power below the best with better "
      "fielding was not chosen — the hedge is meant to be affordable")

# Just outside the budget, it is not.
FAR = PlayerCard("Far", 9 - FIELDING_POWER_BUDGET - 1, 5)
d = best_pitching_play([FAR, ACE], [], st(runners=[RUNNER]))
check(d.player_card is ACE,
      f"pitching paid more than FIELDING_POWER_BUDGET ({FIELDING_POWER_BUDGET}) "
      f"power for fielding — it played {d.player_card.name} "
      f"({d.player_card.power}) over Ace (9). The budget is not bounding it.")

# A fielding boost adds no power; a pitch boost does. Pitch boost wins.
pb = TacticsCard("Pitch", TacticsType.PITCH_BOOST, 2)
fb = TacticsCard("Field", TacticsType.FIELDING_BOOST, 3)
d = best_pitching_play([ACE], [fb, pb], st(runners=[RUNNER]))
check(d.tactics_card is pb,
      f"with runners on, pitching attached {d.tactics_card.name} over the pitch "
      "boost — a fielding boost adds ZERO power (power_bonus, simulate.py:97), "
      "so this discards confirmed power for an unconfirmed effect")

# With no pitch boost held, a fielding boost is better than nothing.
d = best_pitching_play([ACE], [fb], st(runners=[RUNNER]))
check(d.tactics_card is fb,
      "a fielding boost was left unplayed when no pitch boost was held")

# --- BANS: identity, not count -------------------------------------------
# choose_bans works on OUR OWN collection, so it removes our weakest cards.
pool = [PlayerCard(f"P{p}", p, 1) for p in (9, 8, 7, 3, 2, 1)]
bans = choose_bans(pool, count=3)
check(len(bans) == 3, f"choose_bans returned {len(bans)} cards, expected 3")
banned = {c.power for c in bans}
check(banned == {1, 2, 3},
      f"choose_bans removed powers {sorted(banned)} — expected the three "
      "weakest {1, 2, 3}. Banning the STRONGEST cards passed every previous "
      "test in this project.")

# --- REDRAW --------------------------------------------------------------
d0 = should_redraw([PlayerCard("W", 1, 0)], st(half="batting", redraws_left=0))
check(d0 is False,
      "should_redraw returned True with zero redraws left — the game would "
      "reject it and the turn would be wasted")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} decision failure(s)")

print(f"OK: decisions — batting takes max power and always boosts; pitching "
      f"takes max power with fielding bounded at {FIELDING_POWER_BUDGET}; "
      f"pitch boost beats fielding boost; bans remove the weakest")


# --- redraw threshold and discard choice are COUPLED ---------------------
# Threshold raised 4 -> 6 (58.5% head-to-head over 4000 matches) after
# simulate.py's discard model was corrected: the real mechanic keeps your
# at-bat and replaces ONE card, not the whole hand. The old 4 was correctly
# tuned for a mechanic this game does not have.
from decision_engine import REDRAW_POWER_THRESHOLD, should_redraw, GameState, PlayerCard

_st = lambda left=2: GameState(half="batting", batters_used=0, your_score=0,
                               opp_score=0, redraws_left=left)

assert REDRAW_POWER_THRESHOLD == 6, (
    f"threshold is {REDRAW_POWER_THRESHOLD}; 6 was the measured optimum "
    "(5->56.4%, 6->58.5%, 7->56.5%, 8->54.0%)")

# Fires at and below the threshold, not above it.
assert should_redraw([PlayerCard("a", REDRAW_POWER_THRESHOLD, 1)], _st())
assert not should_redraw([PlayerCard("a", REDRAW_POWER_THRESHOLD + 1, 1)], _st())

# The live hand that prompted this: 6,6,5,5,6 — user expected a redraw and the
# shipped rule refused, because its best was 6 > 4.
_live = [PlayerCard("a", 6, 0), PlayerCard("b", 6, 0), PlayerCard("c", 5, 1),
         PlayerCard("d", 5, 0), PlayerCard("e", 6, 0)]
assert should_redraw(_live, _st()), (
    "the 6,6,5,5,6 hand observed live still refuses to redraw")

# No discards left means no redraw, whatever the hand.
assert not should_redraw([PlayerCard("a", 4, 0)], _st(left=0))

# The coupling: above a threshold of 4 it MATTERS which card is discarded,
# because the pool minimum (4) no longer beats every qualifying hand outright.
from orchestrator import KNOWN_BAN_ROSTER
_pool_min = min(c.power for c in KNOWN_BAN_ROSTER.values())
assert REDRAW_POWER_THRESHOLD > _pool_min, (
    "threshold is at or below the pool minimum, so any draw beats the whole "
    "hand and the discard-choice fix is inert — fine, but then say so")

# BEHAVIOURAL, not a source grep. Asserting `"min(players, key=" in source`
# proved only that a string appears — inverting the comparator to pick the
# STRONGEST card kept that substring and survived the suite (QA, 2026-08-26).
# Drive the real play_one_turn and observe which index it discards.
import orchestrator as _o

_discarded = []
_saved = (_o.select_and_discard, _o.select_and_play, _o.press)
_o.select_and_discard = lambda idx, *a, **k: _discarded.append(idx)
_o.select_and_play = lambda *a, **k: None
_o.press = lambda *a, **k: None
try:
    # Weakest is a 4 at index 2; the engine's best is the 6 at index 0. The
    # whole hand is <= REDRAW_POWER_THRESHOLD, so the redraw branch fires.
    _hand = [{"kind": "player", "name": "a", "power": 6, "secondary": 0, "hand_index": 0},
             {"kind": "player", "name": "b", "power": 5, "secondary": 0, "hand_index": 1},
             {"kind": "player", "name": "c", "power": 4, "secondary": 0, "hand_index": 2}]
    _state = {"screen": "turn", "phase": "batting", "your_score": 0,
              "opp_score": 0, "discards_left": 2, "runners": [], "hand": _hand}
    _played, _ = _o.play_one_turn(_state, 0)
    assert _played is False, "the redraw branch did not fire on an all-weak hand"
    assert _discarded == [2], (
        f"discarded hand_index {_discarded}, expected [2] — the WEAKEST card. "
        "Discarding the best throws away the floor that makes the higher "
        "redraw threshold profitable.")

    # --- P3: the card actually PLAYED must be the one the engine chose ------
    # QA 2026-08-26: `player_idx = next(i for i, p in players ...)` mutated to
    # `player_idx = 0` survived all 16 test files. That makes decision_engine
    # INERT in the live loop — the bot plays hand slot 0 every turn — while
    # test_decisions.py stays green, because it tests the engine directly and
    # never the function that acts on its answer. The strongest card must NOT
    # be at index 0 here or the mutation is indistinguishable.
    _played_idx = []
    _o.select_and_play = lambda idx, *a, **k: _played_idx.append(idx)
    _strong = [{"kind": "player", "name": "weak", "power": 5, "secondary": 0, "hand_index": 0},
               {"kind": "player", "name": "mid", "power": 7, "secondary": 0, "hand_index": 1},
               {"kind": "player", "name": "best", "power": 9, "secondary": 0, "hand_index": 2}]
    _st2 = {"screen": "turn", "phase": "batting", "your_score": 0, "opp_score": 0,
            "discards_left": 2, "runners": [], "hand": _strong}
    _ok, _ = _o.play_one_turn(_st2, 0)
    assert _ok is True, "a strong hand should be played, not discarded"
    assert _played_idx == [2], (
        f"played hand_index {_played_idx}, expected [2] — the engine chose the "
        "power-9 card and the loop played something else. If this reads [0] the "
        "decision engine is inert and every heuristic in it is decoration.")

    # --- P4: target_score is only known while PITCHING ----------------------
    _seen_state = []
    _real_bat = _o.best_batting_play
    _o.best_batting_play = lambda p, t, st: (_seen_state.append(st), _real_bat(p, t, st))[1]
    try:
        _o.play_one_turn(_st2, 0)
        assert _seen_state and _seen_state[-1].target_score is None, (
            "target_score is set while BATTING — it is the defender's known "
            "final score and is only available when pitching")
    finally:
        _o.best_batting_play = _real_bat

    # --- P2: a missing discards_left must mean ZERO, never a default -------
    # `if discards_left is None: discards_left = 0` mutated to `= 2` survived.
    # That invents discards the game has not granted, and the redraw branch
    # then burns a keypress on a discard the game may refuse.
    _discarded.clear()
    _st3 = {"screen": "turn", "phase": "batting", "your_score": 0, "opp_score": 0,
            "discards_left": None, "runners": [],
            "hand": [dict(c) for c in _hand]}
    _o.play_one_turn(_st3, 0)
    assert _discarded == [], (
        "discarded with discards_left=None — an unknown count must be treated "
        "as zero, not as a full allowance")

finally:
    _o.select_and_discard, _o.select_and_play, _o.press = _saved

print(f"OK: redraw threshold {REDRAW_POWER_THRESHOLD} (measured), discard "
      "targets the weakest card, and the two are pinned together")
