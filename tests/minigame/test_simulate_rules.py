"""THE SIMULATOR'S RULES, PINNED — the ones that were wrong and were fixed by hand.

Every check here guards a mistake this model has ACTUALLY made. None of them had a test,
which is why each was found by the user reading numbers back rather than by the suite.

    the match shape          it looped over two innings, played FOUR halves and roughly
                             doubled every score (2026-09-12). You bat in inning one and
                             pitch in inning two; that is the whole match.
    the hand                 both hands were redrawn every ROUND, so card economy could not
                             exist -- nothing survived to a later turn. The real hand is
                             dealt once per half and topped up ONE card per play.
    a tie                    equal power is a COIN FLIP, and losing one is an OUT. The model
                             used to fold ties into "out" unconditionally.
    roles                    a pitcher could be dealt as a batter and its FIELDING read as
                             SPEED (see test_card_roles.py, which owns that one).

These are rules, not tunings. The UNMEASURED knobs (OUT_RUNNER_ADVANCE,
FIELDING_SUBTRACT_PER_POINT, TIE_RUNNERS_ADVANCE) are deliberately NOT pinned to a value
here -- pinning a guess makes it look settled. What is pinned is that they exist and are
reachable, so nobody deletes the seam that lets them be measured.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, random, collections
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import simulate as s
from decision_engine import PlayerCard, TacticsCard, TacticsType, Decision

_fails = []


def _play_best(hand_players, hand_tactics, state):
    """The simplest legal heuristic: strongest card, no tactics."""
    return Decision(player_card=max(hand_players, key=lambda c: c.power),
                    tactics_card=None, reasoning="test")


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


print("1. THE MATCH IS TWO HALVES — you bat once and pitch once")
calls = []
_real_half = s.simulate_batting_half


def _spy(batting, pitching, defender_target_score=None, **kw):
    calls.append(defender_target_score)
    return 3


s.simulate_batting_half = _spy
try:
    team = {"batting": lambda *a: None, "pitching": lambda *a: None}
    a, b = s.simulate_match(dict(team), dict(team))
finally:
    s.simulate_batting_half = _real_half
check(len(calls) == 2,
      f"exactly two halves are played ({len(calls)}) — four means the two-inning loop is "
      f"back, and it roughly doubles every score")
check(calls[0] is None and calls[1] == 3,
      f"the SECOND half knows the first's score and the first does not ({calls}) — that "
      f"ordering is what makes them innings one and two rather than two independent halves")
check((a, b) == (3, 3), f"and both scores come back ({(a, b)})")

print("2. FIVE ROUNDS PER HALF")
check(s.ROUNDS_PER_HALF == 5, f"ROUNDS_PER_HALF is 5 ({s.ROUNDS_PER_HALF})")
seen = {"n": 0}


def _count_batting(hand_players, hand_tactics, state):
    seen["n"] += 1
    return Decision(player_card=max(hand_players, key=lambda c: c.power), tactics_card=None, reasoning="test")


random.seed(3)
s.simulate_batting_half(_count_batting, lambda hp, ht, st: Decision(
    player_card=max(hp, key=lambda c: c.power), tactics_card=None, reasoning="test"))
check(seen["n"] == 5, f"the batting heuristic is asked exactly 5 times ({seen['n']})")

print("3. THE HAND PERSISTS and is topped up ONE card per play")
# refill_hand must ADD to the hand it is given, never replace it.
keep = [PlayerCard("Keep A", 9, 1, "batter"), PlayerCard("Keep B", 8, 2, "batter")]
players, tactics = list(keep), []
players.pop()                                       # a card was played
random.seed(5)
players, tactics = s.refill_hand(players, tactics, "batting")
check(keep[0] in players,
      "the cards NOT played are still in the hand — a reshuffle would lose them, and that "
      "is what made card economy impossible to model")
check(len(players) + len(tactics) == 5,
      f"and the hand is back to five ({len(players)} + {len(tactics)})")

print("4. A PLAYED CARD LEAVES THE HAND")
# If it does not, refill is a no-op and the hand silently grows.
sizes = []
_real_refill = s.refill_hand


def _watch_refill(players, tactics, phase, *a, **kw):
    sizes.append(len(players) + len(tactics))
    return _real_refill(players, tactics, phase, *a, **kw)


s.refill_hand = _watch_refill
try:
    random.seed(11)
    s.simulate_batting_half(
        _play_best,
        _play_best)
finally:
    s.refill_hand = _real_refill
# round 0 sees a full hand; every later round must see a hand with a GAP in it
check(len(sizes) >= 10, f"refill ran for both sides every round ({len(sizes)})")
check(any(n < 5 for n in sizes),
      f"at least one round began with a hand SHORT of five ({sorted(set(sizes))}) — all "
      f"fives means played cards never left and the refill is doing nothing")
check(max(sizes) <= 5,
      f"and the hand never grew past five ({max(sizes)}) — growth is the same bug seen "
      f"from the other end")

print("5. A TIE IS A COIN FLIP, AND LOSING ONE IS AN OUT")
check(s.resolve(5, 5) == "tie", "equal power is a tie, not an out")
check(s.resolve(4, 5) == "out" and s.resolve(6, 5) == "hit", "and the ordinary cases hold")
check(s.resolve(8, 5) == "home_run", "beating it by 3 is a home run")
check(s.resolve(7, 5) == "hit", "beating it by 2 is not")
# a tie that is LOST must score nothing; with TIE_WIN_PROB forced to 0 every tie is lost
_real_prob = s.TIE_WIN_PROB
s.TIE_WIN_PROB = 0.0
try:
    # SPEED 3, deliberately. At speed 1 a phantom runner cannot reach home inside five
    # rounds, so "no runs" passes even when a lost tie wrongly puts one on base -- that
    # mutant SURVIVED the first sweep of this file. At speed 3 the error scores.
    one = PlayerCard("Tie", 5, 3, "batter")
    pit = PlayerCard("Tie", 5, 0, "pitcher")
    random.seed(2)
    lost = s.simulate_batting_half(
        lambda hp, ht, st: Decision(player_card=one, tactics_card=None, reasoning="t"),
        lambda hp, ht, st: Decision(player_card=pit, tactics_card=None, reasoning="t"))
finally:
    s.TIE_WIN_PROB = _real_prob
check(lost == 0,
      f"every at-bat a tie, every flip lost -> no runs ({lost}). A lost tie that is not an "
      f"out puts a runner on, and at SPEED 3 that runner scores -- which is the only way "
      f"this check can see the mistake")
# and the control: the same set-up with every flip WON must score, or the zero above is
# just a half that cannot score at all
s.TIE_WIN_PROB = 1.0
try:
    random.seed(2)
    won = s.simulate_batting_half(
        lambda hp, ht, st: Decision(player_card=one, tactics_card=None, reasoning="t"),
        lambda hp, ht, st: Decision(player_card=pit, tactics_card=None, reasoning="t"))
finally:
    s.TIE_WIN_PROB = _real_prob
check(won > 0,
      f"...and winning every flip DOES score ({won}) — without this, a half that can never "
      f"score would satisfy the check above for the wrong reason")

print("6. the BATTING state knows the opponent's score when there is one")
# It was `opp_score=0` unconditionally, while defender_target_score held the real number
# two arguments away. Inert today -- no heuristic reads the score, and CLAUDE.md section 4
# explains why that is correct -- which is exactly why it survived: a field nothing reads
# is a lie nothing catches, until something reads it and is wrong on the second half of
# every match.
_bat, _pit = [], []


def _decider(store):
    # NAMED APART from the simulate_batting_half stub above. Both were `_spy`, which
    # is harmless in a straight-line script (the first is used before the second is
    # defined) but trips tests/harness/test_no_shadowed_module_defs.py -- and that
    # guard is kept strict on purpose, because the same collision in an IMPORTED
    # module silently broke the deal gate on 2026-09-20.
    def f(hp, ht, st):
        store.append((st.half, st.your_score, st.opp_score, st.target_score))
        return Decision(player_card=max(hp, key=lambda c: c.power),
                        tactics_card=None, reasoning="t")
    return f


random.seed(1)
s.simulate_batting_half(_decider(_bat), _decider(_pit), defender_target_score=7)
check(_bat and all(o == 7 for _h, _y, o, _t in _bat),
      f"the batter is told the defender has 7 ({[o for _h, _y, o, _t in _bat]})")
check(_pit and all(t == 7 for _h, _y, _o, t in _pit),
      f"and the pitcher still gets it as target_score ({[t for _h, _y, _o, t in _pit]})")
_bat2 = []
random.seed(1)
s.simulate_batting_half(_decider(_bat2), _decider([]), defender_target_score=None)
check(_bat2 and all(o == 0 for _h, _y, o, _t in _bat2),
      "and when the defender has NOT batted yet it is 0, not None — the first half of a "
      "match has no opponent score to know")

print("7. the UNMEASURED knobs are still reachable — do not pin their VALUES")
for name in ("OUT_RUNNER_ADVANCE", "FIELDING_SUBTRACT_PER_POINT", "TIE_RUNNERS_ADVANCE",
             "TIE_WIN_PROB", "MODEL_SPEED"):
    check(hasattr(s, name), f"{name} exists as a knob")
check(s.OUT_RUNNER_ADVANCE in ("none", "one", "speed"),
      f"OUT_RUNNER_ADVANCE is one of the three modelled answers ({s.OUT_RUNNER_ADVANCE!r}), "
      f"which is a shape check — the VALUE is unmeasured and is deliberately not pinned")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
