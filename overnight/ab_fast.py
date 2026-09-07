"""FAST single-leg A/B: return loop instead of reset, a TIMED OUT outcome, 3 setup attempts.

WHY (user, 2026-09-07 evening): "each A/B taking 2-4 hours is so much time".
Tonight's trials spent 21-70s on the leg under test and 60-1110s on the setup
(reset, reload, walk the whole route). So the setup is what gets cut:

  RETURN LOOP   after the leg, walk its reverse back to the start node and let
                the next trial's go_to_node_verified find the character there
                with locate() -- no reset, no route. It falls back to the full
                reset-and-route on its own when the localiser cannot name the
                node, so the loop can only make a trial cheaper, never wrong.
                Both arms share the setup, so the comparison stays fair; the
                absolute rate is "from a return-loop pose", and the streak
                still walks the real route.
  TIMED OUT     an arrival slower than LEG_TIME_CAP is scored timed_out and is
                NOT an arrival: the user does not count slow luck, and neither
                does a 25-streak.
  3 ATTEMPTS    for the setup; a miss is INVALID as before.

One file, several experiments (EXPERIMENTS below): the arm is set in the CHILD
so process death is the restore (10.18); the timeout is enforced from outside
(10.14); INVALID is never a failure (10.6); classes come from leg-end frames.

    nohup .venv/bin/python -B overnight/ab_fast.py --experiment trim > overnight/ab_fast_trim.log 2>&1 &
      -> overnight/ab_fast_<experiment>.json after every trial; frames under overnight/ab_fast_<experiment>_frames/
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

TRIALS = _harness.TRIALS          # 10 per arm
SETUP_ATTEMPTS = 3
LEG_TIME_CAP = 60                 # seconds; the recorded goal leg arrives in 21-34s
TRIAL_TIME_CAP = 400              # seconds, setup + leg: over this a trial is a FAILURE (user, 2026-09-07:
                                  # "letting a run go 400s+ clearly should be marked as a failure")
TIMEOUT = TRIAL_TIME_CAP + 20     # the external kill, just above the cap; a killed trial is timed_out

# ARM VALUES, NAMED (the restore-shape check cannot read intent from a literal).
RECORDED_ARM_FLAG = True
EXTENDED_ARM_UNITS = 0.10
TRIM_ARM_UNITS = 0.05


def _arm_recorded(gw):
    gw.GOAL_LEG_AS_RECORDED = RECORDED_ARM_FLAG


def _arm_extended(gw):
    gw.GOAL_LEG_AS_RECORDED = RECORDED_ARM_FLAG
    gw.GOAL_LEG_EXTRA_UNITS = EXTENDED_ARM_UNITS


def _arm_trimmed(gw):
    gw.LEG_TRIM_UNITS_BY_LEG = {("bar_pool_room", "bar_jukebox"): TRIM_ARM_UNITS}


def _arm_asis(gw):
    pass


EXPERIMENTS = {
    "extend": {"start": "bar_jukebox", "target": "dealer_table",
               "question": "recorded goal leg vs recorded + 0.10u (fast harness)",
               "arms": {"recorded": _arm_recorded, "extended": _arm_extended}},
    "trim": {"start": "bar_pool_room", "target": "bar_jukebox",
             "question": "jukebox leg as recorded vs its end trimmed by 0.05u (fast harness)",
             "arms": {"recorded": _arm_asis, "trimmed": _arm_trimmed}},
}


def reverse_steps(steps):
    """The leg walked backwards: reversed order, each bearing turned 180."""
    return [{"bearing": round((s["bearing"] + 180.0) % 360.0, 2), "dur": s["dur"],
             "speed": s.get("speed", 0.2)} for s in reversed(steps)]


def classify(arrived, leg_seconds, total_seconds=0.0, cap=LEG_TIME_CAP, trial_cap=TRIAL_TIME_CAP):
    """arrived / timed_out / missed.

    A trial over `trial_cap` (setup + leg) is timed_out whatever the leg did;
    an arrival slower than `cap` is timed_out; a miss is a miss. timed_out is
    a FAILURE, counted against the arm, never an invalid."""
    if total_seconds > trial_cap:
        return "timed_out"
    if not arrived:
        return "missed"
    return "arrived" if leg_seconds <= cap else "timed_out"


def fisher_two_sided(a, b, c, d):
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def pr(x):
        return (math.comb(r1, x) * math.comb(n - r1, c1 - x)) / math.comb(n, c1)
    p_obs = pr(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + 1e-9))


def one_trial(experiment, arm):
    import graph_walk as gw
    import worldmap as wm
    exp = EXPERIMENTS[experiment]
    start, target = exp["start"], exp["target"]
    shots = os.path.join(HERE, f"ab_fast_{experiment}_frames")

    def log(m):
        print(m, flush=True)
    exp["arms"][arm](gw)
    log(f"  arm={arm}  GOAL_LEG_AS_RECORDED={gw.GOAL_LEG_AS_RECORDED}  GOAL_LEG_EXTRA_UNITS={gw.GOAL_LEG_EXTRA_UNITS}"
        f"  LEG_TRIM_UNITS_BY_LEG={getattr(gw, 'LEG_TRIM_UNITS_BY_LEG', None)}")
    m = wm.WorldMap.load()
    # SETUP: locate() first -- the previous trial's return walk usually leaves
    # the character here -- and reset+route only if it cannot name the node.
    t0 = time.time()
    where0, _ = gw.locate(m, log=log)
    ok = gw.go_to_node_verified(m, start, log=log, attempts=SETUP_ATTEMPTS, shots=shots)
    setup_s = round(time.time() - t0, 1)
    if not ok:
        return {"arm": arm, "reached_start": False, "setup_seconds": setup_s,
                "setup_mode": "returned" if where0 == start else "reset",
                "measurable": gw._LAST_TRIAL_MEASURABLE}
    t1 = time.time()
    r = _harness.walk_leg_under_test(gw, m, start, target, shots=shots, log=log)
    secs = round(time.time() - t1, 1)
    outcome = classify(bool(r["verified_arrived"]), secs, setup_s + secs)
    row = _harness.leg_trial_row(arm, r, secs, arrived=(outcome == "arrived"))
    row.update({"outcome": outcome, "reached_start": True, "setup_seconds": setup_s,
                "setup_mode": "returned" if where0 == start else "reset",
                "measurable": gw._LAST_TRIAL_MEASURABLE})
    # RETURN LOOP: walk the leg backwards (in-memory link only; the map on disk
    # is never touched -- assert_map_pristine in main() would catch it).
    t2 = time.time()
    try:
        m.connect(target, start, reverse_steps(m.steps_for(start, target)), one_way=True,
                  note="return loop, in memory only")
        gw.walk_link(m, target, start, log=log)
        back, detail = gw.locate(m, log=log)
        row["returned_to"] = back
        log(f"  return walk: locate() -> {back} ({detail}) in {time.time() - t2:.0f}s")
    except Exception as e:                   # the next trial simply resets
        row["returned_to"] = f"error: {type(e).__name__}"
        log(f"  return walk failed ({type(e).__name__}: {e}); the next trial will reset")
    return row


def main(experiment):
    def log(m):
        print(m, flush=True)
    exp = EXPERIMENTS[experiment]
    out = os.path.join(HERE, f"ab_fast_{experiment}.json")
    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")
    arms = tuple(exp["arms"])
    res = {"question": exp["question"], "experiment": experiment, "start": exp["start"], "target": exp["target"],
           "trials": TRIALS, "setup_attempts": SETUP_ATTEMPTS, "timeout": TIMEOUT, "leg_time_cap": LEG_TIME_CAP, "trial_time_cap": TRIAL_TIME_CAP,
           "arms": list(arms), "runs": []}
    log(f"FAST A/B '{experiment}': {TRIALS} trials per arm, interleaved, {exp['start']} -> {exp['target']}, cap {LEG_TIME_CAP}s")
    for i, (_t, arm) in enumerate(_harness.interleave(arms, TRIALS), 1):
        r, secs = _harness.run_trial(__file__, f"{experiment}:{arm}", TIMEOUT, log=log)
        if r is None and secs >= TIMEOUT - 5 and _harness.alive():
            # killed at the ceiling with the stream alive: a FAILURE of the arm
            log(f"[{i:2d}] {arm:9s} TIMED_OUT at the {TIMEOUT}s ceiling -- counted as a failure")
            res["runs"].append({"arm": arm, "arrived": False, "outcome": "timed_out", "reason": "ceiling", "seconds": secs})
        elif r is None:
            log(f"[{i:2d}] {arm:9s} INVALID after {secs:.0f}s (crash, or the stream went down)")
            res["runs"].append({"arm": arm, "arrived": None, "outcome": "invalid", "reason": "unmeasurable", "seconds": secs})
        elif not r.get("reached_start"):
            # the setup is shared by both arms; a setup miss says nothing about the arm
            log(f"[{i:2d}] {arm:9s} INVALID: never reached {exp['start']} (setup {r['setup_seconds']:.0f}s, {r['setup_mode']})")
            res["runs"].append({"arm": arm, "arrived": None, "outcome": "invalid", "reason": f"setup did not reach {exp['start']}", **r})
        else:
            log(f"[{i:2d}] {arm:9s} {r['outcome'].upper():9s} leg {r['seconds']:.0f}s  setup {r['setup_seconds']:.0f}s ({r['setup_mode']})  "
                f"returned_to={r.get('returned_to')}  kinds_leg_end={r.get('failure_kinds_leg_end')}")
            res["runs"].append(r)
        _harness.save_result(out, res)
    log("")
    counts = {}
    for arm in arms:
        rows = [r for r in res["runs"] if r["arm"] == arm]
        val = [r for r in rows if r.get("outcome") != "invalid"]
        c = {k: sum(1 for r in val if r["outcome"] == k) for k in ("arrived", "timed_out", "missed")}
        counts[arm] = (c["arrived"], len(val))
        log(f"  {arm:9s} arrived {c['arrived']}  timed_out {c['timed_out']}  missed {c['missed']}  invalid {len(rows) - len(val)}"
            f"  setups returned {sum(1 for r in rows if r.get('setup_mode') == 'returned')}/{len(rows)}")
        _harness.report_kinds(val, out=log, indent="            ")
    (a, na), (c, nc) = counts[arms[0]], counts[arms[1]]
    if na and nc:
        p = fisher_two_sided(a, na - a, c, nc - c)
        res["fisher_p"] = p
        log(f"\n  {arms[0]} {a}/{na}  {arms[1]} {c}/{nc}  Fisher exact p = {p:.4f}  (arrived within {LEG_TIME_CAP}s leg / {TRIAL_TIME_CAP}s trial)")
        _harness.save_result(out, res)
    log(f"\n  -> {out}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        import json
        experiment, arm = sys.argv[2].split(":", 1)
        print(json.dumps(one_trial(experiment, arm)), flush=True)
    else:
        name = sys.argv[sys.argv.index("--experiment") + 1] if "--experiment" in sys.argv else "trim"
        main(name)
