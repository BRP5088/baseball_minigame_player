"""THE AT-BAT IS DECIDED BY THE REVEAL'S MARGIN, NOT BY THE SCOREBOARD MOVING.

The old rule was `if new_score > score_before: outcome = "home_run"`. It is wrong because
SPEED decides how many bases a runner takes (user's sources, 2026-09-12): a fast batter
scores on an ordinary hit, a runner on third scores on a single, and CLAUDE.md section 4
records that a LOSING at-bat can still advance runners. All three raise the score.

Measured over the 345 scorable rows of match_log.jsonl at the time of the fix: 20 were
labelled home_run at a margin that cannot produce one, 10 of them at a LOSING margin.

HONEST SCOPE. These checks pin the RULE, not the field data. The recorded labels cannot
validate the new classifier because they are the thing it replaces -- re-scoring them
reconstructs `runs` from the old label, which is circular.

AND THE OLD LABELS ARE DEMONSTRABLY THE WRONG HALF. 26 rows carry a margin of 3 or more
and were labelled "out", which under an absolute rule is impossible. All 26 have a KNOWN
tactics kind on both sides, so the margin is not a guess. The user confirmed the rule is
absolute from the scoreboard on 2026-09-12 -- their own home run raised it -- so what
those rows record is the OLD evidence failing: "out" meant only that `new_score` did not
appear to exceed `score_before`, and the score read is exactly what the margin replaces.
They are a measure of how bad the old labelling was, not an open question about the rule.

Live rows now carry runs_scored, margin and outcome_basis, so a row says which evidence
decided it and the two can finally be compared on real data.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"
import orchestrator as o

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


print("1. only swing/pitch boosts add power")
check(o.effective_power(5, 2, "swing_boost") == 7, "swing boost adds")
check(o.effective_power(5, 2, "pitch_boost") == 7, "pitch boost adds")
check(o.effective_power(5, 2, "speed_boost") == 5, "speed boost does NOT add power")
check(o.effective_power(5, 2, "fielding_boost") == 5, "fielding boost does NOT add power")
check(o.effective_power(None, 2, "swing_boost") is None, "an unread card stays unread")

print("2. the margin is taken from the BATTER's side in both phases")
bat = {"phase": "batting", "our_power": 9, "opp_power": 4,
       "our_tactics_bonus": 0, "opp_tactics_bonus": 0}
pit = {"phase": "pitching", "our_power": 9, "opp_power": 4,
       "our_tactics_bonus": 0, "opp_tactics_bonus": 0}
check(o.reveal_margin(bat) == 5, f"batting: ours - theirs (got {o.reveal_margin(bat)})")
check(o.reveal_margin(pit) == -5,
      f"pitching: the at-bat is THEIRS, so the sign flips (got {o.reveal_margin(pit)})")
check(o.reveal_margin({**bat, "opp_power": None}) is None,
      "an unreadable opponent card gives None, never a guessed margin")

print("3. the game's own rule decides, and runs are recorded separately")
check(o.classify_outcome(3, 4, 3, 0) == ("home_run", "margin"),
      "margin +3 is an automatic home run (CLAUDE.md section 4)")
check(o.classify_outcome(9, 1, 0, 0)[0] == "home_run", "and so is any bigger margin")
check(o.classify_outcome(2, 0, 0, 1) == ("hit", "margin"), "margin +2 is a hit, not a home run")
# THE DEFECT, AS A CHECK: a losing at-bat that drove a runner home.
check(o.classify_outcome(-4, 1, 1, 0) == ("out", "margin"),
      "a LOSING margin is an OUT even though a run scored — the exact 10 rows the old "
      "rule wrote home_run for")
check(o.classify_outcome(1, 3, 3, 0) == ("hit", "margin"),
      "and a +1 margin that cleared the bases is still a HIT, not a home run")

print("4. a tie is the one case the screen has to answer")
check(o.classify_outcome(0, 1, 0, 1) == ("tie_win", "tie"), "a tie that produced something")
check(o.classify_outcome(0, 0, 0, 0) == ("out", "tie"), "a tie that produced nothing")

print("5. no margin means no verdict — it must NOT invent a home run")
check(o.classify_outcome(None, 2, 0, 0) == ("scored", "delta"),
      "runs with no reveal are recorded as 'scored', which claims only what is known")
check(o.classify_outcome(None, 0, 0, 0) == ("out", "delta"), "and nothing is an out")
check("home_run" not in [o.classify_outcome(None, r, 0, 3)[0] for r in (0, 1, 5)],
      "no fallback path can ever produce home_run — that is the whole bug")

print("6. the basis is recorded, so a row says WHICH evidence decided it")
check({o.classify_outcome(m, 1, 0, 0)[1] for m in (5, 1, -1)} == {"margin"}, "margin rows")
check(o.classify_outcome(0, 1, 0, 0)[1] == "tie", "tie rows")
check(o.classify_outcome(None, 1, 0, 0)[1] == "delta", "fallback rows")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
