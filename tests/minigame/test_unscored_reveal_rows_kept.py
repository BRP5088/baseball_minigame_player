"""I-49: a staged row that a LATER poll fails to resolve must not vanish.

`agent_progress/census/reveal_orphans_trace/final_reasons.json` traced 36 fully
readable reveal frames that produced NO match_log.jsonl row. 21 of them had
already been STAGED (`pending_matchup = matchup_info`, powers/kinds/bonuses/phase
all known) and were then DROPPED by a later poll's own failure:

    12   "N consecutive unreadable screens" (MAX_PENDING_READ_FAILURES, ~:8845)
     9   "outcome unscorable: <field> missing from the follow-up read" (~:8907)

Both sites used to `pending_matchup = None` and print nothing else. They now
append the row with the outcome fields null, `row_status: "unscored"`, and a
`drop_reason` naming which of the two killed it. A normally scored row is
unchanged except for one new field, `row_status: "scored"`.

NOT COVERED HERE, DELIBERATELY: the third drop site (~:9091,
`TRANSITION_SCREEN_MAX_SEC` outlasting a stuck "new_inning"/"reveal_recap"), and
the give-up/abandon producer in reset_env.py. Neither appeared among the 42
traced frames (0 of them), and the ticket's own line-range scope
(orchestrator.py ~8840-8915, ~10150-10245) does not reach either -- see
`agent_progress/issues/I-49/progress.md`.

CONSUMER CHECK, not just the producer: `outcome_basis` is what
`analyze_match_log.has_outcome_basis()` and `tactics_effect.py` gate win-rate
statistics on, and it is `None` on every unscored row here -- so they exclude
themselves from any OUTCOME statistic with NO changes needed to either script.
`tools/ab_engine_i15_16_17.load_log_distribution()` gates on `"outcome_basis"
not in row and "margin" not in row` -- a KEY-PRESENCE test, not a truthiness
one -- and an unscored row carries both keys (value None), so it is NOT
excluded there: its `opp_power` is real and the opponent-power distribution is
allowed to use it, exactly as the ticket asked.
"""
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import json
import os
import sys
import tempfile

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ["BASEBALL_TEST_RUN"] = "1"

from _run_harness import Harness
import orchestrator as o
import analyze_match_log as aml
sys.path.insert(0, _os.path.join(_ROOT, "tools"))
import ab_engine_i15_16_17 as ab_engine

fails = []


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


# our_tactics_kind set (not None) so a "kind" is something to preserve; bonus 0
# so reveal_margin does not need it to compute a definite margin either way.
_INFO = {"phase": "batting", "our_card_name": "Johnny Drawers", "our_power": 7,
         "our_secondary": 1, "our_tactics_bonus": 0, "our_tactics_kind": "swing_boost",
         "runners_before": 0, "score_before": 0}
_OURS = {"kind": "player", "name": "Johnny Drawers", "power": 7, "secondary": 1}
_THEIRS = {"kind": "player", "name": "Rube Sharp", "power": 4, "secondary": 2}
_OPP_LOCAL = {"opp_power": 4, "opp_tactics_bonus": 0, "opp_tactics_kind": None,
              "_ours_power_seen": 7}


def _rows_for(screens):
    rows = []
    real = o.log_matchup
    o.log_matchup = lambda record: rows.append(record)
    try:
        Harness(screens, revealed=[_OURS, _THEIRS], opp_local=dict(_OPP_LOCAL),
                play_results=[(True, dict(_INFO))]).run(target_wins=99)
    finally:
        o.log_matchup = real
    return rows


# =============================================================================
# A. dropped_unreadable_streak: turn (stages the row) -> MAX_PENDING_READ_FAILURES+1
#    consecutive unreadable polls -> the row is appended, not lost.
# =============================================================================
_N = o.MAX_PENDING_READ_FAILURES + 1
rows = _rows_for(["turn"] + [RuntimeError("unreadable")] * _N + ["other"] * 3)
check("A: exactly one row reaches match_log despite the unreadable streak",
      len(rows) == 1)
if rows:
    r = rows[0]
    check("A: row_status is unscored", r.get("row_status") == "unscored")
    check("A: drop_reason names the streak",
          r.get("drop_reason") == f"{_N}_consecutive_unreadable_screens")
    check("A: outcome is null, not fabricated", r.get("outcome") is None)
    check("A: runs_scored/margin/outcome_basis are all null",
          r.get("runs_scored") is None and r.get("margin") is None
          and r.get("outcome_basis") is None)
    check("A: the at-bat's OWN card data survived (power, kind, phase)",
          r.get("our_power") == 7 and r.get("our_tactics_kind") == "swing_boost"
          and r.get("phase") == "batting")
    check("A: the opponent's LOCAL read survived (staged before the drop)",
          r.get("opp_power") == 4)

# --- MUTANT-CATCHING CONTROL: fewer than the streak bound must NOT drop -----
# (pins that A's row-count assertion is actually testing the streak length,
# not "any failed read at all logs something")
rows_short = _rows_for(["turn"] + [RuntimeError("unreadable")] * (_N - 1)
                        + [{"screen": "other", "phase": "batting", "your_score": 1,
                            "opp_score": 0, "hand": [], "runners": [],
                            "discards_left": 2}])
check("A-control: a streak ONE SHORT of the bound resolves normally instead "
      "(scored, not appended-as-unscored)",
      len(rows_short) == 1 and rows_short[0].get("row_status") == "scored")


# =============================================================================
# B. outcome_unscorable: turn (stages the row) -> a "turn" follow-up whose score
#    field is missing -> the row is appended, not lost.
# =============================================================================
_UNSCORABLE_TURN = {"screen": "turn", "phase": "batting", "your_score": None,
                     "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}
rows = _rows_for(["turn", _UNSCORABLE_TURN] + ["other"] * 3)
check("B: exactly one row reaches match_log despite the missing score field",
      len(rows) == 1)
if rows:
    r = rows[0]
    check("B: row_status is unscored", r.get("row_status") == "unscored")
    check("B: drop_reason names the missing field",
          r.get("drop_reason") == "outcome_unscorable:your_score_missing")
    check("B: outcome/runs_scored/margin/outcome_basis are all null",
          r.get("outcome") is None and r.get("runs_scored") is None
          and r.get("margin") is None and r.get("outcome_basis") is None)
    check("B: the at-bat's OWN card data survived",
          r.get("our_power") == 7 and r.get("our_tactics_kind") == "swing_boost")
    check("B: the opponent's LOCAL read survived",
          r.get("opp_power") == 4)


# =============================================================================
# C. CONTROL: a normally scored row is unchanged (outcome intact), plus the one
#    new field. Reproduces test_reveal_frame_kept.py's plain shape: "turn" then
#    "other" resolves on the very first follow-up poll (your_score/opp_score
#    default to 0 in the harness's minimal payload).
# =============================================================================
rows = _rows_for(["turn"] + ["other"] * 3)
check("C: exactly one row logged for a normally scored at-bat", len(rows) == 1)
if rows:
    r = rows[0]
    check("C: row_status is scored", r.get("row_status") == "scored")
    check("C: outcome is a real verdict, not null",
          r.get("outcome") is not None)
    check("C: margin/outcome_basis are populated (7 vs 4 -> a definite margin)",
          r.get("margin") is not None and r.get("outcome_basis") is not None)
    check("C: no drop_reason on a scored row", "drop_reason" not in r)
    check("C: the shape is otherwise untouched (powers, kind, phase all present)",
          r.get("our_power") == 7 and r.get("opp_power") == 4
          and r.get("our_tactics_kind") == "swing_boost"
          and r.get("phase") == "batting")


# =============================================================================
# D. CONSUMER CHECK 1: analyze_match_log / tactics_effect exclude unscored rows
#    from OUTCOME statistics via has_outcome_basis() -- no code change needed
#    there, because outcome_basis is None on every unscored row.
# =============================================================================
_unscored_row = {"phase": "batting", "our_power": 7, "opp_power": 4,
                  "outcome": None, "outcome_basis": None, "row_status": "unscored"}
_scored_row = {"phase": "batting", "our_power": 7, "opp_power": 4,
                "outcome": "home_run", "outcome_basis": "margin", "row_status": "scored"}
check("D: has_outcome_basis() is False for an unscored row -- excluded from "
      "outcome/win-rate statistics automatically",
      aml.has_outcome_basis(_unscored_row) is False)
check("D: has_outcome_basis() is True for a scored row -- included as before",
      aml.has_outcome_basis(_scored_row) is True)
# The margin/secondary half of analyze_match_log.py is legacy-inclusive by its
# own design (reads powers, never `outcome`) and effective_power() does not
# consult row_status at all -- so an unscored row's REAL powers are usable
# there without any change, which is the "MAY use them" half of the ticket.
check("D: effective_power() reads an unscored row's power the same as a "
      "scored one (the powers-only analysis stays usable)",
      aml.effective_power(_unscored_row, "our") == 7
      and aml.effective_power(_unscored_row, "our")
      == aml.effective_power(_scored_row, "our"))


# =============================================================================
# E. CONSUMER CHECK 2: the opponent-power distribution MAY use an unscored row,
#    because load_log_distribution() gates on KEY PRESENCE ("outcome_basis" or
#    "margin" in the row), not on either being truthy -- an unscored row
#    carries both keys (null), so it is NOT excluded. Driven through the real
#    function against a synthetic log, same pattern as
#    test_ab_controls_reproduce_baseline.py's own F3 case.
# =============================================================================
_synthetic_log = "\n".join([
    json.dumps({"phase": "batting", "outcome_basis": "margin", "margin": 3,
                "row_status": "scored", "opp_power": 5, "opp_tactics_bonus": 0,
                "opp_tactics_kind": None}),
    json.dumps({"phase": "batting", "outcome_basis": None, "margin": None,
                "row_status": "unscored", "drop_reason": "outcome_unscorable:your_score_missing",
                "opp_power": 6, "opp_tactics_bonus": 0, "opp_tactics_kind": None}),
    # A genuinely LEGACY row (pre-I-18a shape: neither key at all) must still
    # be excluded -- this is the control that proves the check above is not
    # vacuously true for every row.
    json.dumps({"phase": "batting", "opp_power": 9}),
]) + "\n"
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as _tf:
    _tf.write(_synthetic_log)
    _synthetic_path = _tf.name
_real_log_path = ab_engine._MATCH_LOG_PATH
try:
    ab_engine._MATCH_LOG_PATH = _synthetic_path
    dist, meta = ab_engine.load_log_distribution()
finally:
    ab_engine._MATCH_LOG_PATH = _real_log_path
    os.remove(_synthetic_path)

check("E: both the scored row (5) and the unscored row (6) feed the "
      "opponent-power distribution -- the legacy row (9, neither key) does not",
      meta["n_used_for_distribution"] == 2
      and dict(dist).keys() == {5, 6})
check("E: the legacy row without outcome_basis/margin was excluded from the "
      "'qualifying' count too (3 rows total, 2 qualify)",
      meta["rows_with_outcome_basis_or_margin"] == 2)


print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
