"""Does EXTENDING the recorded goal leg by 0.10u reach the prompt zone?

OPEN-22 (2026-09-07) measured the prompt zone's near edge 0.05u AHEAD of where
the recorded leg stops when it lands at the dealer's table: no prompt at five
headings at the endpoint, the prompt at four of five headings 0.05u forward,
that point not wedged. The prompt is screen-fixed and offered on proximity, so
heading is not the constraint; distance is. This walks the recorded leg
(GOAL_LEG_AS_RECORDED) in BOTH arms and adds a 0.10u push along the leg's net
bearing in one of them -- one constant, one change.

Scoring as ab_goal_leg.py: setup to bar_jukebox at attempts=9 (a miss is
INVALID), ONE execution of the leg through walk_leg_under_test, at_table()
after the sweep (now correlation OR OCR, the ink gate gone) plus an at_table()
re-read; pre-sweep leg-end frames under SHOTS. Interleaved, 10 an arm, 1500s
ceiling (today's setups reached 1065s), Fisher exact.
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
TIMEOUT = 1500                   # today's setups reached 1065s; do not censor
OUT = os.path.join(HERE, "ab_goal_extend.json")
SHOTS = os.path.join(HERE, "goal_extend_failframes")

ARMS = ("recorded", "extended")

# THE ARMS' VALUES, NAMED RATHER THAN WRITTEN INLINE (the restore-shape check
# cannot read intent from a literal). Both arms walk the recorded leg; only the
# extension differs. These are ARMS, not restores.
RECORDED_ARM_FLAG = True
EXTENDED_ARM_UNITS = 0.10        # the measured edge is +0.05; the push is twice that


def set_arm(gw, arm, log):
    """Runs in the CHILD, so nothing has to be put back."""
    gw.GOAL_LEG_AS_RECORDED = RECORDED_ARM_FLAG
    if arm == "extended":
        gw.GOAL_LEG_EXTRA_UNITS = EXTENDED_ARM_UNITS
    elif arm != "recorded":
        raise SystemExit(f"unknown arm {arm!r}")
    log(f"  arm={arm}  GOAL_LEG_AS_RECORDED={gw.GOAL_LEG_AS_RECORDED}  GOAL_LEG_EXTRA_UNITS={gw.GOAL_LEG_EXTRA_UNITS}")


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
    res = {"question": "recorded goal leg vs recorded + 0.10u along its net bearing, then reach_table in both",
           "start": START, "target": TARGET, "trials": TRIALS,
           "setup_attempts": SETUP_ATTEMPTS, "timeout": TIMEOUT,
           "shipped_config": {
               "GOAL_LEG_AS_RECORDED": gw.GOAL_LEG_AS_RECORDED,
               "GOAL_LEG_EXTRA_UNITS": gw.GOAL_LEG_EXTRA_UNITS,
               "APPROACH_STEP_SEC": gw.APPROACH_STEP_SEC,
               "APPROACH_OVERSHOOT": gw.APPROACH_OVERSHOOT,
               "TRUST_RESET_SPAWN": gw.TRUST_RESET_SPAWN,
               "RECOVER_MISSED": gw.RECOVER_MISSED,
               "NULL_YAW_BEFORE_ALIGN": gw.NULL_YAW_BEFORE_ALIGN,
           },
           "runs": []}
    log(f"goal-leg EXTENSION A/B: {TRIALS} trials per arm, interleaved, {START} -> {TARGET}")
    log(f"  shipped: {res['shipped_config']}")

    # --resume: the user paused the run (2026-09-07, the stream looked sluggish
    # under offline CPU work). interleave() is deterministic, so continuing from
    # the number of trials already banked keeps the same interleaved design.
    skip = 0
    if "--resume" in sys.argv and os.path.exists(OUT):
        import json as _json
        prev = _json.load(open(OUT))
        res["runs"] = prev.get("runs", [])
        skip = len(res["runs"])
        log(f"  RESUMING after {skip} banked trials")
    for i, (_t, arm) in enumerate(_harness.interleave(ARMS, TRIALS), 1):
        if i <= skip:
            continue
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
    (a, na), (c, nc) = counts["recorded"], counts["extended"]
    if na and nc:
        p = fisher_two_sided(a, na - a, c, nc - c)
        res["fisher_p"] = p
        log(f"\n  recorded {a}/{na}  extended {c}/{nc}  Fisher exact p = {p:.4f}")
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
