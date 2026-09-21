"""run()'s reveal-logging block must never crash with UnboundLocalError.

overnight/run_live_20260920g.log:187: "[reveal] turn NOT logged --
UnboundLocalError: cannot access local variable '_ours_seen' where it is not
associated with a value".

`_ours_seen` (orchestrator.py, inside run()'s post-play reveal block) was only
ever assigned inside `if _opp_local is not None:` -- i.e. only when the LOCAL
opponent read (`opponent_from_reveal`) found something. It is read
unconditionally further down, in the "opponent_card is None" branch that
decides whether to log on the local read or print "no OPPONENT card
identified". So a turn whose local opponent read comes back None (the game
occluded the card, a fresh deal was mid-animation, whatever) skipped straight
past the assignment and blew up on the read -- caught by the block's own
broad `except Exception`, which printed the exception's name and TYPE and
swallowed the turn instead of reaching the "no OPPONENT card identified"
message that already exists for exactly this case.

See ISSUES.md I- (none filed; found directly from the log) and
agent_progress/census-20260920/progress.md finding 3.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.pop("BASEBALL_ALLOW_PAID", None)  # paid model OFF, the case under test

import contextlib
import io

from _run_harness import Harness, check, failures
import orchestrator as o

# Same reason _run_harness's sibling files stub this: it polls a real screen
# otherwise and would burn the full POST_PLAY_DEAL_MAX_WAIT every play.
o.wait_for_hand_deal = lambda *a, **k: True

check(o.paid_model_allowed() is False,
      "this file is about the paid-off case; paid_model_allowed() must be False")

_INFO = {"phase": "batting", "our_card_name": "Johnny Drawers", "our_power": 8,
         "our_secondary": 1, "our_tactics_bonus": 0, "our_tactics_kind": None,
         "runners_before": 0, "score_before": 0}


def _run_and_capture(h):
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf):
        h.run(target_wins=99)
    return _buf.getvalue()


# --- 1. a play whose LOCAL opponent read comes back None must not crash --
# opp_local defaults to None (the harness's opponent_from_reveal() stub
# returns it unchanged) -- the exact shape a live occluded/mid-animation
# reveal produces. revealed must be non-None (an empty list is enough) so
# wait_for_reveal_cards() reports a reveal happened and the block actually
# reaches opponent_from_reveal() instead of aborting earlier on "reveal
# cards never appeared" -- paid_model_allowed() is False regardless, so
# read_matchup_reveal() (what `revealed` would feed) is never even called.
h = Harness(["turn"] + ["other"] * 20, revealed=[],
            play_results=[(True, dict(_INFO))])
out = _run_and_capture(h)

check("UnboundLocalError" not in out,
      f"the reveal block raised UnboundLocalError on a None local opponent "
      f"read instead of falling through to the existing message: {out!r}")
check("no OPPONENT card identified" in out,
      f"the turn was not accounted for by the existing "
      f"'no OPPONENT card identified' message: {out!r}")
check("turn NOT logged —" not in out,
      f"the reveal block's catch-all exception handler fired at all (some "
      f"exception was swallowed), expected a clean fall-through: {out!r}")


# --- 2. CONTROL: a genuine local read must still log normally ------------
# Sanity check that the fix didn't turn the local-read path into a no-op:
# with opp_local populated, _ours_seen must still be threaded through to the
# "logging on the LOCAL read" message.
_ours = {"kind": "player", "name": "Johnny Drawers", "power": 8, "secondary": 1}
_theirs = {"kind": "player", "name": "Rube Sharp", "power": 4, "secondary": 2}
_opp_local = {"opp_power": 4, "opp_tactics_bonus": 0, "opp_tactics_kind": None,
              "_ours_power_seen": 8}
h2 = Harness(["turn"] + ["other"] * 20, revealed=[_ours, _theirs],
             opp_local=_opp_local, play_results=[(True, dict(_INFO))])
out2 = _run_and_capture(h2)
check("UnboundLocalError" not in out2,
      f"CONTROL: a populated local read must not crash either: {out2!r}")
check("logging on the LOCAL read" in out2,
      f"CONTROL: a genuine local opponent read stopped reaching the "
      f"existing logging message -- the fix broke the working path: {out2!r}")


print("OK: run()'s reveal block never raises UnboundLocalError on a None "
      "local opponent read, and the genuine local-read path still logs")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} reveal-log-unbound failure(s)")
