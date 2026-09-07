"""Does walking the GOAL leg as recorded arrive more often than approach_goal()?

WHAT IS BEING COMPARED. On every leg but the last, follow() replays the recorded
steps through walk_link. On the last leg it does not: approach_goal() walks a
straight line at steps[-1]["bearing"] in 0.4s chunks for up to 1.6x the recorded
duration, checking for the prompt as it goes, and reach_table() then sweeps for
the prompt. That executor predates the 2026-09-05 jukebox-leg restoration --
when the table leg started 0.7 units early, an over-long straight approach was
the workaround -- and it has never been A/B'd against the recorded leg.

WHAT OPEN-14 MEASURED ABOUT IT (2026-09-07, overnight/streak_table.log and
overnight/census/table_leg_ends_20260907.json): 37 executions, and in 37 of 37
the approach exhausted its budget ("stepped 6.8s of a 6.5s budget without
finding the prompt"); the prompt was found by stepping 0 times and by the sweep
once. Of the 37 post-sweep frames, 17 were wedged (7-11 keypoints) and the
visual census read dark 12 / bar counter 8 / floor 5 / NPC 3 / wall 1. The
recorded leg is eight steps at bearings 72-98 with a net direction near 85; the
approach aims at 75.5, 10.6 deg off, and walks 1.6x as long.

THE ARM. GOAL_LEG_AS_RECORDED=True routes the goal leg through walk_link like
every leg that arrives; reach_table's sweep still follows in both arms. This is
NOT one of GRAVEYARD's closed shapes: it steers nothing mid-push, and it REMOVES
a chunked approach rather than adding chunks.

SCORING. The character is first brought to bar_jukebox by the retrying
primitive (attempts=9, start_hint=SPAWN -- OPEN-5 measured 9/9 there); a trial
that does not reach it is INVALID, not a failure of the leg. Then ONE execution
of bar_jukebox -> dealer_table through _harness.walk_leg_under_test, scored by
follow_verified's own confirm() -- at_table() on the post-sweep frame -- plus an
independent at_table() re-read from a settled pose. Frames: the pre-sweep leg
end (at_dealer_table_*), the post-sweep frame (at_dealer_table_postsweep_*),
and success/ok_dealer_table_* for arrivals, all under SHOTS.

METHOD, every clause a scar: interleaved (10.5); n = 10 per arm (10.3); the arm
is set in the CHILD so process death is the restore (10.18); timeout enforced
from OUTSIDE (10.14) and sized so the setup cannot be censored -- reaching
bar_jukebox at attempts=9 took up to 780s in OPEN-5; INVALID is never a failure
(10.6); report BY CLASS from leg-end frames, not just the total (§8(f)).
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import _harness

START = "bar_jukebox"
TARGET = "dealer_table"
TRIALS = _harness.TRIALS         # 10
SETUP_ATTEMPTS = 9               # OPEN-5: 9/9 to bar_jukebox at this depth
TIMEOUT = 1200                   # setup max 780s (OPEN-5) + leg + sweep; do not censor
OUT = os.path.join(HERE, "ab_goal_leg.json")
SHOTS = os.path.join(HERE, "goal_leg_failframes")

ARMS = ("shipped", "recorded")

# THE 'recorded' ARM'S VALUE, NAMED RATHER THAN WRITTEN INLINE. As a bare literal
# it is indistinguishable from a harness reinstating a stale default -- the
# defect tests/harness/test_harness_restores_shipped_value.py exists to catch,
# and it flagged this line as a literal, correctly. It is an ARM, not a restore.
RECORDED_ARM_FLAG = True


def set_arm(gw, arm, log):
    """'shipped' touches NOTHING; 'recorded' flips the one flag. Runs in the child."""
    if arm == "recorded":
        gw.GOAL_LEG_AS_RECORDED = RECORDED_ARM_FLAG
    elif arm != "shipped":
        raise SystemExit(f"unknown arm {arm!r}")
    log(f"  arm={arm}  GOAL_LEG_AS_RECORDED={gw.GOAL_LEG_AS_RECORDED}")


def fisher_two_sided(a, b, c, d):
    """Exact p for the 2x2 table [[a, b], [c, d]] (arrived/missed per arm)."""
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def pr(x):
        return (math.comb(r1, x) * math.comb(n - r1, c1 - x)) / math.comb(n, c1)
    p_obs = pr(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + 1e-9))


def one_trial(arm):
    import graph_walk as gw
    import table_prompt
    import worldmap as wm
    import reset_env

    def log(m):
        print(m, flush=True)

    set_arm(gw, arm, log)
    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()

    t0 = time.time()
    ok = gw.go_to_node_verified(m, START, log=log, attempts=SETUP_ATTEMPTS,
                                shots=SHOTS, start_hint=gw.SPAWN)
    setup_s = round(time.time() - t0, 1)
    if not ok:
        # The leg under test never ran. That is a fact about the setup, and the
        # parent scores it INVALID -- it must not enter either arm's denominator.
        return {"arm": arm, "reached_start": False, "setup_seconds": setup_s,
                "measurable": gw._LAST_TRIAL_MEASURABLE}

    t1 = time.time()
    r = _harness.walk_leg_under_test(gw, m, START, TARGET, shots=SHOTS, log=log)
    secs = round(time.time() - t1, 1)
    # Independent re-read from a settled pose, the check OPEN-14 trial 6 failed.
    time.sleep(0.8)
    recheck = bool(table_prompt.at_table(gw._default_capture()))
    row = _harness.leg_trial_row(arm, r, secs, arrived=bool(r["verified_arrived"]))
    row.update({"reached_start": True, "setup_seconds": setup_s,
                "recheck_at_table": recheck,
                "measurable": gw._LAST_TRIAL_MEASURABLE})
    return row


def main():
    def log(m):
        print(m, flush=True)

    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")

    import graph_walk as gw
    res = {"question": "goal leg as recorded (walk_link) vs approach_goal(), then reach_table in both",
           "start": START, "target": TARGET, "trials": TRIALS,
           "setup_attempts": SETUP_ATTEMPTS, "timeout": TIMEOUT,
           "shipped_config": {
               "GOAL_LEG_AS_RECORDED": gw.GOAL_LEG_AS_RECORDED,
               "APPROACH_STEP_SEC": gw.APPROACH_STEP_SEC,
               "APPROACH_OVERSHOOT": gw.APPROACH_OVERSHOOT,
               "TRUST_RESET_SPAWN": gw.TRUST_RESET_SPAWN,
               "RECOVER_MISSED": gw.RECOVER_MISSED,
               "NULL_YAW_BEFORE_ALIGN": gw.NULL_YAW_BEFORE_ALIGN,
           },
           "runs": []}
    log(f"goal-leg A/B: {TRIALS} trials per arm, interleaved, {START} -> {TARGET}")
    log(f"  shipped: {res['shipped_config']}")

    for i, (_t, arm) in enumerate(_harness.interleave(ARMS, TRIALS), 1):
        r, secs = _harness.run_trial(__file__, arm, TIMEOUT, log=log)
        if r is None:
            log(f"[{i:2d}] {arm:9s} INVALID after {secs:.0f}s "
                f"(timeout, crash, or the stream went down) -- not a failure")
            res["runs"].append({"arm": arm, "arrived": None,
                                "reason": "unmeasurable", "seconds": secs})
        elif not r.get("reached_start"):
            log(f"[{i:2d}] {arm:9s} INVALID: never reached {START} "
                f"(setup {r['setup_seconds']:.0f}s) -- the leg under test did not run")
            res["runs"].append({"arm": arm, "arrived": None,
                                "reason": f"setup did not reach {START}", **r})
        else:
            log(f"[{i:2d}] {arm:9s} {'ARRIVED' if r['arrived'] else 'missed  '} "
                f"leg {r['seconds']:.0f}s  setup {r['setup_seconds']:.0f}s  "
                f"located={r['located']}  recheck={r['recheck_at_table']}"
                f"{'  FAN' if r.get('fan_ran') else ''}"
                f"  kinds_leg_end={r.get('failure_kinds_leg_end')}")
            res["runs"].append(r)
        _harness.save_result(OUT, res)

    log("")
    counts = {}
    for arm in ARMS:
        rows = [r for r in res["runs"] if r["arm"] == arm]
        val = [r for r in rows if r.get("arrived") is not None]
        counts[arm] = (sum(1 for r in val if r["arrived"]), len(val))
        _harness.report_leg_arm(arm, val, len(rows) - len(val), out=log)
    (a, na), (c, nc) = counts["shipped"], counts["recorded"]
    if na and nc:
        p = fisher_two_sided(a, na - a, c, nc - c)
        res["fisher_p"] = p
        log(f"\n  shipped {a}/{na}  recorded {c}/{nc}  Fisher exact p = {p:.4f}")
        _harness.save_result(OUT, res)
    log(f"\n  -> {OUT}")
    log("  Report BY CLASS from leg-end frames; the pre-sweep frames are the")
    log("  admissible ones (at_dealer_table_*), the postsweep ones are what")
    log("  confirm() judged.")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        import json
        print(json.dumps(one_trial(sys.argv[2])), flush=True)
    else:
        main()
