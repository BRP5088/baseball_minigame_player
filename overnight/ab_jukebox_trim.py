"""(c) Does TRIMMING the jukebox leg's end stop it wedging into the jukebox?

2026-09-07: the jukebox leg ended WEDGED in 69 of 106 executions -- the nine
darkest leg-end frames all show the character pressed into the jukebox cabinet
(dark surface, no compass strip). The recorded leg's last step is 0.14s at
0.319 = 0.045u. One arm trims 0.05u off the leg's end (LEG_TRIM_UNITS_BY_LEG);
the other walks it as recorded. Single-leg A/B from a VERIFIED bar_pool_room
through walk_leg_under_test (one attempt), scored on verified arrival at
bar_jukebox with the failure class from the leg-end frame. Interleaved, 10 an
arm, external ceiling.
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

START = "bar_pool_room"
TARGET = "bar_jukebox"
TRIALS = _harness.TRIALS         # 10
SETUP_ATTEMPTS = 3               # bar_pool_room arrives by attempt 2 in every trial today
TIMEOUT = 900
OUT = os.path.join(HERE, "ab_jukebox_trim.json")
SHOTS = os.path.join(HERE, "jukebox_trim_failframes")

ARMS = ("recorded", "trimmed")

# THE ARM'S VALUE, NAMED (the restore-shape check cannot read intent from a literal).
TRIM_ARM_UNITS = 0.05            # the last step is 0.045u; this removes it and a hair more
LEG = (START, TARGET)


def set_arm(gw, arm, log):
    """Runs in the CHILD, so nothing has to be put back."""
    if arm == "trimmed":
        gw.LEG_TRIM_UNITS_BY_LEG = {LEG: TRIM_ARM_UNITS}
    elif arm != "recorded":
        raise SystemExit(f"unknown arm {arm!r}")
    log(f"  arm={arm}  LEG_TRIM_UNITS_BY_LEG={gw.LEG_TRIM_UNITS_BY_LEG}")


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
    row = _harness.leg_trial_row(arm, r, secs, arrived=bool(r["verified_arrived"]))
    row.update({"reached_start": True, "setup_seconds": setup_s,
                "recheck_at_table": None,
                "measurable": gw._LAST_TRIAL_MEASURABLE})
    return row


def main():
    def log(m):
        print(m, flush=True)

    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")

    import graph_walk as gw
    res = {"question": "jukebox leg as recorded vs its end trimmed by 0.05u (LEG_TRIM_UNITS_BY_LEG)",
           "start": START, "target": TARGET, "trials": TRIALS,
           "setup_attempts": SETUP_ATTEMPTS, "timeout": TIMEOUT,
           "shipped_config": {
               "LEG_TRIM_UNITS_BY_LEG": {str(k): v for k, v in gw.LEG_TRIM_UNITS_BY_LEG.items()},
               "TRUST_RESET_SPAWN": gw.TRUST_RESET_SPAWN,
               "RECOVER_MISSED": gw.RECOVER_MISSED,
               "NULL_YAW_BEFORE_ALIGN": gw.NULL_YAW_BEFORE_ALIGN,
           },
           "runs": []}
    log(f"jukebox TRIM A/B: {TRIALS} trials per arm, interleaved, {START} -> {TARGET}")
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
    (a, na), (c, nc) = counts["recorded"], counts["trimmed"]
    if na and nc:
        p = fisher_two_sided(a, na - a, c, nc - c)
        res["fisher_p"] = p
        log(f"\n  recorded {a}/{na}  trimmed {c}/{nc}  Fisher exact p = {p:.4f}")
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
