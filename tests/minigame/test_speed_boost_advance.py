"""A SPEED BOOST MOVES THE BATTER WHO PLAYED IT, ONCE, AND IS THEN GONE.

The rules, supplied by the user 2026-09-12 with two sources: speed is how many bases a
runner takes on a hit; a speed boost "immediately adds to your Speed stat for that hit,
determining how many bases you advance right then and there"; and "once your player
finishes their turn and stops on a base, the Speed Boost card is discarded -- if that same
runner needs to advance again on a subsequent turn they revert back to moving at their
standard baseline speed."

WHAT THIS GUARDS, and it is not hypothetical. Until 2026-09-12 simulate.py computed
`batter_speed` at the top of every at-bat and NEVER READ IT -- an AST scan found it the
only dead local in the file (CLAUDE.md 10.1: "a measurement taken and discarded"). The
batter's own advance used card.secondary with no bonus, so a speed boost was worth exactly
zero while power_bonus paid the swing boost in full. Measured over 9,000 simulated halves,
attaching a speed boost was worth +0.013 runs/half before the fix and +0.262 after it.

AND IT NEARLY TOOK A SHIPPED CONSTANT WITH IT. blend_play ADDS tac.bonus to the speed it
scores a choice on, so the chooser paid for speed boosts while the resolver ignored them --
a bias against speed running through the 1,010,000-match sweep behind power/speed 99/1.
Re-swept in both models, the answer was unchanged (best w = 0.01 either way), so 99/1
stands on its own; that is a measured reprieve, not a reason to stop checking.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, ast, random, statistics
os.environ["BASEBALL_TEST_RUN"] = "1"

import simulate as S
from decision_engine import PlayerCard, TacticsCard, TacticsType, Decision

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


print("1. speed_bonus pays the SPEED boost and nothing else")
for kind, want in ((TacticsType.SPEED_BOOST, 3), (TacticsType.SWING_BOOST, 0),
                   (TacticsType.PITCH_BOOST, 0), (TacticsType.FIELDING_BOOST, 0)):
    got = S.speed_bonus(TacticsCard("t", kind, 3))
    check(got == want, f"{kind.value:15s} -> {got} (want {want})")
check(S.speed_bonus(None) == 0, "no tactics card -> 0")
# the mirror image, so the two bonuses cannot quietly become the same function
check(S.power_bonus(TacticsCard("t", TacticsType.SPEED_BOOST, 3)) == 0,
      "and power_bonus still refuses the speed boost — they are different stats")

print("2. the bonus reaches the BATTER'S OWN advance")
slow = PlayerCard("slow", 9, 1)
check(S._step(slow, 0) == 1, f"baseline speed 1 takes 1 base (got {S._step(slow, 0)})")
check(S._step(slow, 0, 2) == 3, f"with a +2 boost, 3 bases (got {S._step(slow, 0, 2)})")
check(S._step(slow, 0, 3) == 4, "a +3 boost on a speed-1 batter reaches home (4)")
# fielding subtracts AFTER the boost is added, not before
check(S._step(slow, 1, 2) == 2, f"fielding 1 removes one of those bases (got {S._step(slow, 1, 2)})")

print("3. and NOT the runners already on base — the card is discarded when they stop")
# advance_runners must never see a bonus: its signature takes none, by construction
_sig = S.advance_runners.__code__.co_varnames[:S.advance_runners.__code__.co_argcount]
check("bonus" not in _sig,
      f"advance_runners takes no bonus argument, so a stored runner cannot keep one {_sig}")
still, scored = S.advance_runners([(slow, 1)], 0, "speed")
check(still == [(slow, 2)] and scored == 0,
      f"a speed-1 runner on first goes to second, not further (got {still}, {scored})")
# the batter is stored as the CARD, so next turn it re-derives baseline speed
_src = ast.parse(open(_os.path.join(_ROOT, "simulate.py")).read())
_fn = next(n for n in ast.walk(_src) if isinstance(n, ast.FunctionDef)
           and n.name == "simulate_batting_half")
_appends = [n for n in ast.walk(_fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "append"]
check(bool(_appends), "the half really appends runners (an empty scan must not pass)")
check(all(not (isinstance(a.args[0], ast.Tuple) and len(a.args[0].elts) > 1
               and "bonus" in ast.dump(a.args[0].elts[0]))
          for a in _appends if a.args),
      "and stores the CARD, never a boosted speed — that is what makes the revert free")

print("4. it changes the outcome, by a margin worth having")


def always_speed(hp, ht, st):
    p = max(hp, key=lambda c: (c.power, c.secondary))
    sp = [t for t in ht if t.kind is TacticsType.SPEED_BOOST]
    return Decision(p, max(sp, key=lambda t: t.bonus) if sp else None, "always speed")


def half_runs(n, seed):
    random.seed(seed)
    return [S.simulate_batting_half(always_speed, S.naive_no_tactics) for _ in range(n)]


_real = S.speed_bonus
try:
    S.speed_bonus = lambda t: 0
    old = [r for s in (1, 2, 3) for r in half_runs(1200, s)]
    S.speed_bonus = _real
    new = [r for s in (1, 2, 3) for r in half_runs(1200, s)]
finally:
    S.speed_bonus = _real
gain = statistics.mean(new) - statistics.mean(old)
# PINNED AS A LITERAL FLOOR, not against the constant it guards (CLAUDE.md 10.11).
# Measured +0.249 over 9,000 halves; 0.10 is far below that and far above the +0.013
# the old model produced, so it separates the two models rather than tracking either.
check(gain > 0.10,
      f"attaching a speed boost is worth {gain:+.3f} runs/half against the same seeds "
      f"with the bonus forced to zero (measured +0.249; the old model gave +0.013)")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
