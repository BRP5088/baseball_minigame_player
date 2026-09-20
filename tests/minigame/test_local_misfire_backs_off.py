"""I-12: the LOCAL misfire branch must back off, and the summary must say so.

`orchestrator.run()`'s reveal block has two "our card is absent" branches: a
PAID one (`our_card_in_reveal`) that already calls `input_controller.
report_misfire()`, and a LOCAL one (the `[MISFIRE?]` line, reached when the
opponent's name cannot be matched but their power reads) that only logged the
observation and counted `misfires` — with the paid model off (the shipped
default, section 3 of CLAUDE.md) the local branch is the ONLY misfire detector
that ever runs, and it was never backing anything off.

The end-of-run "[input] N cards played, M suspected misfire(s)" line also
called that a false "NOT MEASURED" whenever misfires happened to be 0, even
though the local reveal path had run and found nothing wrong. See ISSUES.md
I-12.
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
import input_controller

# Same reason _run_harness's sibling files stub this: it polls a real screen
# otherwise and would burn the full POST_PLAY_DEAL_MAX_WAIT every play.
o.wait_for_hand_deal = lambda *a, **k: True

check(o.paid_model_allowed() is False,
      "this file is about the paid-off case; paid_model_allowed() must be False")

_INFO = {"phase": "batting", "our_card_name": "Johnny Drawers", "our_power": 8,
         "our_secondary": 1, "our_tactics_bonus": 0, "our_tactics_kind": None,
         "runners_before": 0, "score_before": 0}


def _turn(our_power_seen, opp_power=4):
    """One play whose LOCAL reveal read `our_power_seen` for our own side.

    `revealed` feeds read_matchup_reveal (the paid path, dead with the model
    off) purely so a faceoff-shaped list exists; opp_local is what
    opponent_from_reveal() actually returns, matching production's call.
    """
    ours = {"kind": "player", "name": "Johnny Drawers", "power": our_power_seen,
            "secondary": 1}
    theirs = {"kind": "player", "name": "Rube Sharp", "power": opp_power,
              "secondary": 2}
    opp_local = {"opp_power": opp_power, "opp_tactics_bonus": 0,
                 "opp_tactics_kind": None, "_ours_power_seen": our_power_seen}
    return Harness(["turn"] + ["other"] * 20, revealed=[ours, theirs],
                   opp_local=opp_local, play_results=[(True, dict(_INFO))])


def _run_and_capture(h):
    calls = []
    _real = input_controller.report_misfire
    input_controller.report_misfire = lambda: calls.append(1)
    _buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf):
            h.run(target_wins=99)
    finally:
        input_controller.report_misfire = _real
    return calls, _buf.getvalue()


# --- 1. a local mismatch calls report_misfire() exactly once -------------
# The reveal shows OUR side reading power 7; play_results says we played 8.
calls, out = _run_and_capture(_turn(our_power_seen=7))
check(len(calls) == 1,
      f"a local misfire (revealed 7, played 8) called report_misfire() "
      f"{len(calls)} time(s), expected 1")
check("MEASURED" in out,
      f"summary did not say MEASURED after a local misfire ran: {out!r}")

# --- 2. CONTROL: matching powers must NOT call report_misfire() ----------
calls, out = _run_and_capture(_turn(our_power_seen=8))
check(len(calls) == 0,
      f"CONTROL: a clean reveal (revealed 8, played 8) called "
      f"report_misfire() {len(calls)} time(s), expected 0 — if this fails "
      "the check above proves nothing")
check("MEASURED" in out,
      f"summary did not say MEASURED after a clean local reveal ran (a run "
      f"with zero misfires but a live local detector is still measured, "
      f"not NOT MEASURED): {out!r}")

# --- 3. CONTROL: zero plays -> no [input] verdict at all -----------------
# `if plays:` guards the whole summary block, so a run that never plays a
# card prints no [input] line and cannot claim MEASURED by accident.
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    Harness(["other"] * 40).run(target_wins=99)
out = _buf.getvalue()
check("[input]" not in out,
      f"a run with zero plays printed an [input] verdict: {out!r}")


print("OK: the local [MISFIRE?] branch backs off input timing, and the "
      "summary reports MEASURED (local reveal) once that branch has run")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} local-misfire-backoff failure(s)")
