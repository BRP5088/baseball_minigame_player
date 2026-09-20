"""I-09: the post-play deal gate must arm only on a CONFIRMED play, and its
timeout line must say why -- no motion at all, or motion that never settled.

Two things were wrong before this test existed. (1) run()'s post-play
`wait_for_hand_deal()` call sat AFTER the `if played: ... else: ...` block
instead of inside the `if played:` branch, so it ran on every non-play too --
a refused play, or any discard -- watching a hand nothing was ever going to
change for the full 20s and appending a phantom "timeout" row to
deal_timing.jsonl. (2) `wait_for_hand_deal`'s own timeout message printed "a
biggest well UNDER the threshold means the gate is too high" unconditionally,
even when the biggest delta seen was 83.1 against a threshold of 15 -- which
is not a threshold problem, it is a reader that saw the deal start and never
called the hand stable (I-01's shape).

Both are ROOT-CAUSE fixes at the one place each question is answered:
run()'s own play/no-play branch for (1), and wait_for_hand_deal's own outcome
classification for (2). Nothing here touches deal_timing thresholds or floors
(CLAUDE.md 10.4) -- only which branch runs and what it prints/logs.
"""
import itertools
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The flag goes here too, before ANY project import, so the suite-wide scan
# (test_every_test_sets_the_flag) can see it set in THIS file.
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

# _run_harness sets BASEBALL_TEST_RUN / BASEBALL_DEAL_LOG / BASEBALL_MATCH_LOG
# and imports orchestrator, BEFORE this file touches either -- same reason
# _run_harness.py itself gives: those redirects must land before import.
from _run_harness import Harness, check, failures  # noqa: E402
import orchestrator as o  # noqa: E402


# ---------------------------------------------------------------------------
# (a) run(): the gate is armed only when the play was CONFIRMED.
# ---------------------------------------------------------------------------

def _run_one_turn_and_count_deal_waits(played):
    """Drive run() through exactly one 'turn' poll with play_one_turn stubbed
    to return `played`, and count how many times wait_for_hand_deal fires.

    matchup_info is always None here -- both branches of `played` produce
    that in practice (a discard never has one; this isolates the `played`
    gate from the separate reveal-logging machinery, which I-09 does not
    touch). Only ONE screen is scripted; the harness yields "other" once it
    is exhausted, and run() self-terminates on MAX_UNRECOGNIZED_ATTEMPTS --
    see _run_harness.py's own docstring on why every test here terminates
    without reaching a win.
    """
    h = Harness(["turn"], play_results=[(played, None)])
    calls = []
    saved = o.wait_for_hand_deal
    o.wait_for_hand_deal = lambda *a, **k: calls.append(1) or True
    try:
        h.run(target_wins=1)
    finally:
        o.wait_for_hand_deal = saved
    return len(calls)


_refused_calls = _run_one_turn_and_count_deal_waits(False)
check(_refused_calls == 0,
      f"I-09: played=False (refused play / discard) must NOT arm the post-play "
      f"deal gate -- there is no deal to watch -- but it was called "
      f"{_refused_calls} time(s)")

_played_calls = _run_one_turn_and_count_deal_waits(True)
check(_played_calls == 1,
      f"I-09 CONTROL: played=True must still arm the gate exactly once "
      f"(saw {_played_calls} call(s)) -- without this control the check above "
      "would pass against a version that never arms the gate at all")


# ---------------------------------------------------------------------------
# (b) wait_for_hand_deal(): three distinct outcomes, and `reason` on the row.
# ---------------------------------------------------------------------------
#
# Drives the real wait_for_hand_deal, not a copy of its logic. Every capture
# call it makes is stubbed to a controlled sequence; `_mean_abs_delta` and
# `_hand_signature` are stubbed directly (rather than feeding them real
# images) because they are the only two functions whose OUTPUT wait_for_
# hand_deal branches on -- everything upstream of them (_grab_settle_regions,
# crop_gameplay_regions, _fast_grab) is just plumbing that hands them images.

_DEAL_LOG = os.environ["BASEBALL_DEAL_LOG"]


def _last_deal_row():
    with open(_DEAL_LOG) as f:
        lines = [ln for ln in f if ln.strip()]
    return json.loads(lines[-1])


def _run_deal_gate(deltas, sig_fn, max_wait, poll_interval=0.05,
                    post_play_min_wait=None):
    """Call the real wait_for_hand_deal with every capture stubbed.

    `deltas`: an iterable of _mean_abs_delta results, one per poll (last one
    repeats once exhausted). `sig_fn`: the stand-in for _hand_signature.
    `post_play_min_wait`, when given, monkeypatches POST_PLAY_MIN_WAIT for
    just this call (CLAUDE.md 10.18 -- it is read at call time, so this is
    the sanctioned way to shrink the floor for a fast test) so the STABLE
    scenario does not need to burn the real 3.0s floor in wall-clock time.
    """
    saved = {n: getattr(o, n) for n in
             ("_grab_settle_regions", "_mean_abs_delta", "crop_gameplay_regions",
              "_fast_grab", "_hand_signature", "record_observation")}
    saved_floor = o.POST_PLAY_MIN_WAIT
    delta_it = iter(deltas)
    _last_delta = [0.0]

    def _next_delta():
        try:
            _last_delta[0] = next(delta_it)
        except StopIteration:
            pass
        return _last_delta[0]

    try:
        o._grab_settle_regions = lambda names: {n: "IMG" for n in names}
        o._mean_abs_delta = lambda a, b: _next_delta()
        o.crop_gameplay_regions = lambda frame: [("hand", "IMG")]
        o._fast_grab = lambda *a, **k: "FRAME"
        o._hand_signature = sig_fn
        o.record_observation = lambda **k: None
        if post_play_min_wait is not None:
            o.POST_PLAY_MIN_WAIT = post_play_min_wait
        return o.wait_for_hand_deal(max_wait=max_wait, poll_interval=poll_interval,
                                     baseline="BASE")
    finally:
        for n, v in saved.items():
            setattr(o, n, v)
        o.POST_PLAY_MIN_WAIT = saved_floor


# 1. NOTHING DEALT: the delta never crosses the threshold. seen stays False.
_const_sig = lambda img: "SIG"  # noqa: E731
result1 = _run_deal_gate(deltas=[5.0], sig_fn=_const_sig, max_wait=0.4)
row1 = _last_deal_row()
check(result1 is False,
      f"no-edge scenario: wait_for_hand_deal should time out (got {result1!r})")
check(row1["outcome"] == "timeout" and row1["edge_seen"] is False,
      f"no-edge scenario: expected a timeout row with edge_seen False, got "
      f"outcome={row1.get('outcome')!r} edge_seen={row1.get('edge_seen')!r}")
check(row1.get("reason") == "no_edge",
      f"I-09: no-edge timeout row must carry reason='no_edge' (got "
      f"{row1.get('reason')!r}) so deal_timing.jsonl can be split by cause")

# 2. EDGE SEEN, NEVER STABLE: the delta crosses the threshold at once (biggest
#    stays well over it), but _hand_signature returns something DIFFERENT
#    every call -- a reader that never agrees with itself twice in a row,
#    I-01's shape -- so the gate can never release.
_counter = itertools.count()
_unstable_sig = lambda img: f"SIG-{next(_counter)}"  # noqa: E731
result2 = _run_deal_gate(deltas=[30.0], sig_fn=_unstable_sig, max_wait=0.4)
row2 = _last_deal_row()
check(result2 is False,
      f"edge-no-stable scenario: wait_for_hand_deal should time out (got {result2!r})")
check(row2["outcome"] == "timeout" and row2["edge_seen"] is True,
      f"edge-no-stable scenario: expected a timeout row with edge_seen True, got "
      f"outcome={row2.get('outcome')!r} edge_seen={row2.get('edge_seen')!r}")
check(row2.get("reason") == "edge_no_stable",
      f"I-09: edge-but-unstable timeout row must carry reason='edge_no_stable' "
      f"(got {row2.get('reason')!r}) -- this is I-01's shape (a reader problem), "
      "not the 'gate is too high' message the old code printed unconditionally")

# 3. STABLE: the delta crosses the threshold at once, and the signature settles
#    to one constant value -- a hand that reads the same thing twice running.
#    Floor shrunk to keep this fast (see _run_deal_gate's docstring).
result3 = _run_deal_gate(deltas=[30.0], sig_fn=_const_sig, max_wait=1.0,
                          post_play_min_wait=0.05)
row3 = _last_deal_row()
check(result3 is True,
      f"stable scenario: wait_for_hand_deal should release (got {result3!r})")
check(row3["outcome"] == "stable",
      f"stable scenario: expected outcome='stable', got {row3.get('outcome')!r}")
check(row3.get("reason") == "stable",
      f"I-09: the stable row must carry reason='stable' (got {row3.get('reason')!r})")

# CONTROL for the whole reason mechanism: the three rows above must actually be
# THREE DIFFERENT reasons, not one value _record_row happens to default to
# regardless of what happened. Without this, a `reason=None` default passed
# through unchanged would make every check above pass on coincidence.
_reasons = {row1.get("reason"), row2.get("reason"), row3.get("reason")}
check(len(_reasons) == 3,
      f"I-09 CONTROL: the three scenarios must produce three DISTINCT reasons, "
      f"got {_reasons!r} -- otherwise the field is not actually splitting by cause")


print()
if failures:
    print(f"{len(failures)} FAILED")
    for f in failures:
        print(f"  FAIL  {f}")
    sys.exit(1)
print("all good")
