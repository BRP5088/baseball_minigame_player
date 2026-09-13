"""HOW MANY BASES HAVE TO ANIMATE AFTER A PLAY -- the input the post-play wait never had.

The user, 2026-09-12, on the deal delay: "I didn't say it's broken. It's just not working
correctly. make it work." What they asked for is a wait sized by what actually has to move:
the number of runners and how far each one goes.

Measured live, the same gate released 1.1 s after one play and 10.8 s after a home run, so
the spread is real and an order of magnitude. This computes the PREDICTOR'S INPUT. It
deliberately does NOT convert bases into seconds, and that refusal is the finding:

  * the archived release times are FLOOR-CENSORED. wait_for_hand_deal cannot release before
    POST_PLAY_MIN_WAIT, and 77% of recorded releases land within one poll of it. The
    natural experiment settles it -- at floor 6.0 releases pile at 6.0-6.2, at floor 3.0
    they pile at 3.6-3.7. An animation does not shorten by 2.5 s because a constant moved.
  * no [deal] line on disk carries runner state beside it, so there is nothing to join
    against even where the times ARE uncensored (76 turns between 7 and 18.5 s).

So wait_for_hand_deal now logs the predicted bases next to the measured wait, and the
coefficient comes from a few matches of that pair. An invented seconds-per-base would be
the same bug wearing a fix's clothes (CLAUDE.md's honest-refusal rule).

This is computable at all only because a runner's live SPEED now reads off their base
badge (local_state.read_runners()["speeds"]).
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, inspect
os.environ["BASEBALL_TEST_RUN"] = "1"
import orchestrator as o

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def bases(**kw):
    """kw: third=/second=/first= a speed, or omitted for an empty base."""
    return {n: {"occupied": n in kw, "speed": kw.get(n)} for n in ("third", "second", "first")}


print("1. an empty diamond is just the batter")
check(o.bases_to_travel(bases(), 1, -2) == 1, "a batter with speed 1 moves 1 base")
check(o.bases_to_travel(bases(), 3, 1) == 3, "a batter with speed 3 moves 3")

print("2. runners move by their OWN speed, and cannot run past home")
check(o.bases_to_travel(bases(third=1), 1, 1) == 2, "one on third (1 base) plus the batter (1)")
check(o.bases_to_travel(bases(third=3), 0, 0) == 1,
      "a speed-3 runner on THIRD still travels only 1 — home is the end of the line")
check(o.bases_to_travel(bases(first=3), 0, 0) == 3, "a speed-3 runner on first travels 3")
check(o.bases_to_travel(bases(third=1, second=1, first=1), 1, 1) == 4,
      "bases loaded at speed 1, plus the batter")

print("3. a HOME RUN empties the diamond — the maximum the game can animate")
check(o.bases_to_travel(bases(), 1, o.AUTO_HOME_RUN_MARGIN) == 4,
      "a solo home run is the batter's four bases")
check(o.bases_to_travel(bases(third=1, second=1, first=1), 1, o.AUTO_HOME_RUN_MARGIN) == 10,
      "bases loaded: 1 + 2 + 3 from the runners and 4 from the batter")
check(o.bases_to_travel(bases(third=1), 1, 9) == 5, "and any bigger margin is the same rule")
# the batter's own speed is IRRELEVANT on a home run — they run all four regardless
check(o.bases_to_travel(bases(), 1, 3) == o.bases_to_travel(bases(), 3, 3),
      "on a home run the batter's speed does not change the distance")

print("4. a hole in the read gives None, never a number")
check(o.bases_to_travel({"third": {"occupied": None}, "second": {"occupied": False},
                         "first": {"occupied": False}}, 1, 1) is None,
      "a base that could not be read -> None")
check(o.bases_to_travel({"third": {"occupied": True, "speed": None},
                         "second": {"occupied": False, "speed": None},
                         "first": {"occupied": False, "speed": None}}, 1, 1) is None,
      "a runner whose SPEED did not read -> None, because a count with a hole is wrong, "
      "not partial")
check(o.bases_to_travel(None, 1, 1) is None, "no bases at all -> None")
# ...but a missing speed on a HOME RUN is fine: nobody's speed matters, everyone scores
check(o.bases_to_travel({"third": {"occupied": True, "speed": None},
                         "second": {"occupied": False}, "first": {"occupied": False}},
                        1, o.AUTO_HOME_RUN_MARGIN) == 5,
      "except on a home run, where no speed is needed to know everyone scores")

print("5. the gate accepts it and logs it, and it is OPTIONAL")
_sig = inspect.signature(o.wait_for_hand_deal).parameters
check("predicted_bases" in _sig, "wait_for_hand_deal takes predicted_bases")
check(_sig["predicted_bases"].default is None,
      "defaulting to None, so a caller that does not know stays on the fixed budget")
_src = inspect.getsource(o.wait_for_hand_deal)
check("predicted" in _src and "print" in _src,
      "and it is recorded beside the measured wait, which is what makes the "
      "seconds-per-base coefficient fittable later")
# THE REFUSAL IS PART OF THE CONTRACT: no seconds-per-base constant may appear until it is
# measured. If one is added, this check should be the thing that makes someone justify it.
check(not any(n for n in dir(o) if "PER_BASE" in n.upper()),
      "and NO seconds-per-base constant has been invented — the archived deal times are "
      "floor-censored and cannot fit one")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
