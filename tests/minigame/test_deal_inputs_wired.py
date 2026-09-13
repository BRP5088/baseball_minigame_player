"""THE DIAMOND AT THE PLAY REACHES THE DEAL GATE, and a stale one can never leak forward.

The delay model needs two numbers per turn: what was on the field when the ball was hit,
and how long the deal then took. They are produced several hundred lines apart, so the
diamond is stashed at the play and popped at the gate -- the same shape stash_hand_baseline
already uses, and for the same reason (a module stash the consumer POPS, so a turn can
never inherit the last one).

RAW INPUTS, NOT A PREDICTION, and that is deliberate. bases_to_travel needs the MARGIN,
and the margin is not known at the play: the opponent's card is revealed afterwards.
Guessing it would invent the very number this exists to measure, so the gate logs the
BOUNDS (an out at one end, a home run at the other) and the exact value is joined offline
from the row match_log.jsonl already writes.

WHY IT IS ALL WRAPPED: this is a diagnostic sitting on the $50 path. A log line that can
kill a turn is worse than no log line -- the matchup logger beside it carries the same
belt-and-braces for the same reason, after one crashed a real loop in QA on 2026-08-23.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, ast, inspect
os.environ["BASEBALL_TEST_RUN"] = "1"
import orchestrator as o

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def mk(**kw):
    return {n: {"occupied": n in kw, "speed": kw.get(n)} for n in ("third", "second", "first")}


print("1. the stash carries the diamond, and POPPING clears it")
o.stash_deal_inputs(mk(third=1, first=2), 2, 1)
first = o.deal_inputs_summary(o.pop_deal_inputs())
check(first and "third" in first and "first" in first, f"both runners are described: {first}")
check("batter_speed 2" in first and "fielding 1" in first, "with the batter's speed and the fielding")
check(o.deal_inputs_summary(o.pop_deal_inputs()) is None,
      "a SECOND pop gives nothing — a turn cannot inherit the last turn's diamond, which is "
      "the whole reason this is a stash and not a module variable someone reads")

print("2. it reports BOUNDS, because the margin is not knowable at the play")
o.stash_deal_inputs(mk(third=1, second=1, first=1), 1, 0)
s = o.deal_inputs_summary(o.pop_deal_inputs())
# 3, not 1: a LOSING at-bat still advances the runners (CLAUDE.md section 4), so all three
# move a base even though the batter is out. Only the BATTER's four bases are outcome-
# dependent. I asserted 1 here first and the code was right.
check("bases 3..10" in s,
      f"bases loaded at speed 1: an out still moves all three runners (3), a home run "
      f"moves everyone (10) — {s}")
o.stash_deal_inputs(mk(), 1, 0)
s2 = o.deal_inputs_summary(o.pop_deal_inputs())
check("bases 0..4" in s2, f"an empty diamond: 0 on an out, 4 on a solo home run — {s2}")

print("3. nothing it is handed can raise — it sits on the $50 path")
for bad in (None, {}, {"bases": "nonsense"}, {"bases": {"third": None}},
            {"bases": mk(third=1), "batter_speed": "x"}):
    try:
        o.deal_inputs_summary(bad)
        check(True, f"survives {str(bad)[:38]}")
    except Exception as e:
        check(False, f"raised on {str(bad)[:38]}: {type(e).__name__}")

print("4. THE CAPTURE ACTUALLY RUNS — the check this file did not have")
# THIS FILE WAS GREEN AGAINST A CALL SITE THAT COULD NOT EXECUTE. The capture referenced an
# unimported local_state, raised NameError into its own except on every single turn, and
# stashed nothing — while these checks passed, because they only AST-verified that
# stash_deal_inputs was WRITTEN at the call site. Found by the QA round this wiring was
# built for. So the capture is now a function, and this drives it.
import types
from PIL import Image
from decision_engine import PlayerCard, TacticsCard, TacticsType, Decision

_grabs = {"n": 0}


def _fake_grab(regions):
    _grabs["n"] += 1
    return {r: Image.new("RGB", (220, 227), (30, 30, 30)) for r in regions}


_real_grab = o._grab_settle_regions
o._grab_settle_regions = _fake_grab
try:
    o.pop_deal_inputs()                      # start clean
    _d = Decision(PlayerCard("b", 7, 2), None, "t")
    _ok = o.capture_diamond_at_play(_d, {"phase": "batting"})
    check(_ok is True,
          "capture_diamond_at_play RUNS and reports success — if it raises anything at all "
          "it returns False, which is what a NameError looked like for a whole afternoon")
    check(_grabs["n"] == 1, f"and it really grabbed the base regions ({_grabs['n']}x)")
    _s = o.deal_inputs_summary(o.pop_deal_inputs())
    check(_s is not None and "batter_speed 2" in _s,
          f"the stash is POPULATED, with the batter's speed from the decision — {_s}")

    # WHILE PITCHING the card in hand is our PITCHER: its secondary is FIELDING, not speed.
    o.pop_deal_inputs()
    _dp = Decision(PlayerCard("p", 9, 2),
                   TacticsCard("Fielding Play", TacticsType.FIELDING_BOOST, 1), "t")
    o.capture_diamond_at_play(_dp, {"phase": "pitching"})
    _sp = o.deal_inputs_summary(o.pop_deal_inputs())
    check("fielding 3" in _sp,
          f"pitching: fielding is the pitcher's secondary PLUS a Fielding Play (2+1=3) — {_sp}")
    check("batter_speed None" in _sp,
          f"and the BATTER's speed is None, because the batter is theirs and unknown — one "
          f"number must not play two roles — {_sp}")

    # a failing grab must not propagate
    o._grab_settle_regions = lambda regions: (_ for _ in ()).throw(RuntimeError("boom"))
    _lines = []
    check(o.capture_diamond_at_play(_d, {"phase": "batting"}, log=_lines.append) is False,
          "a failing grab returns False instead of killing the turn")
    check(any("could not record" in x for x in _lines),
          f"and it SAYS so rather than failing silently — {_lines}")
finally:
    o._grab_settle_regions = _real_grab
    o.pop_deal_inputs()

print("5. the gate really POPS it, and the play really STASHES it")
_gate = inspect.getsource(o.wait_for_hand_deal)
check("pop_deal_inputs" in _gate,
      "wait_for_hand_deal pops the stash — if it only READ it, a turn whose gate never ran "
      "would hand its diamond to the next turn")
_tree = ast.parse(open(_os.path.join(_ROOT, "orchestrator.py")).read())
_play = next(n for n in ast.walk(_tree)
             if isinstance(n, ast.FunctionDef) and n.name == "play_one_turn")
_calls = [c.func.id for c in ast.walk(_play)
          if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
check("capture_diamond_at_play" in _calls,
      "play_one_turn captures the diamond (it calls the extracted function, which section 4 "
      "above actually EXERCISES — the AST check alone is what let a dead call site pass)")
check("stash_hand_baseline" in _calls, "beside the hand baseline it mirrors (control)")
# THE WRAPPING MOVED WITH THE CODE. It is now the whole of capture_diamond_at_play, which
# section 4 proves by making the grab raise and asserting the turn survives — a stronger
# check than "there is a try statement near this line", which is what this used to be.
_cap = next(n for n in ast.walk(_tree)
            if isinstance(n, ast.FunctionDef) and n.name == "capture_diamond_at_play")
check(any(isinstance(n, ast.Try) for n in ast.walk(_cap)),
      "and the capture body is wrapped — a diagnostic must never cost a turn")
check(any(isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
          and n.value.value is False for n in ast.walk(_cap)),
      "with a False return on failure, so a caller can tell 'recorded nothing' from "
      "'recorded an empty diamond'")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
