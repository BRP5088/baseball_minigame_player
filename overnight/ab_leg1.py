"""Did the leg-1 changes cost the route? Restored leg 1 against the shipped one.

WHY THIS EXPERIMENT AND NOT ANOTHER. `go_to_node_verified("bar_pool_room")`
measured 10/10 at a 52.9s median on 2026-09-05 at 23:12, and 0/3 at 274-446s on
2026-09-06 at 15:06. Fisher on 10/10 against 0/3 is p = 0.0035, so the collapse
is real rather than n=3 noise, and it invalidates every navigation measurement
taken between those two points.

The cause was recorded in CLAUDE.md as "the console was power-cycled", i.e. the
environment. That is an association, and section 10.2 is explicit that an
association does not count however good the story is -- STALL_CHANGE had
p = 0.00039 observationally and reversed under intervention. So this intervenes.

WHAT ACTUALLY CHANGED BETWEEN THE TWO RUNS, from git rather than memory:

    23:12  10/10 measured        leg 1 original: 7 pushes, 0.78-0.79s at 0.21
    23:33  commit 2fb1ae6        "OPEN-4 answered 10/10; LEG 1 TO MAX SPEED"
    00:20  commit 4e1804c        + MERGE_STEPS_BY_LEG, MERGED_TURN_TOLERANCE
    15:06  0/3 measured          all three live

THE COMMIT THAT RECORDED THE 10/10 ALSO TURNED ON THE FIRST FLAG. That is
section 10.7 -- change one thing, THEN measure -- violated inside the artifact
that reports the measurement, which is why it stayed invisible: the result and
the change that invalidates it share a commit message.

`backups/RESTORE_LEG1.md` describes `LEG_SPEED_BY_LEG` 3.0 in its own words as
"**Walks the leg SHORT**": a 0.26s push is mostly acceleration, so arithmetic
distance is preserved and physical distance is not. The merge was added to fix
exactly that. Whether it did is UNMEASURED against arrival -- the test that
passed it scored arrival AT office_door, which the localiser and aligner recover
from, so a leg that walks short still arrives and the damage only appears
downstream. The user said so before any metric did: "you aren't walking close
enough ... which causes everything else to go off the rails."

WHY THE TARGET IS bar_pool_room AND NOT office_door. Downstream is the whole
point. Leg 1 arrives 20/20 either way; the question is what it does to the two
legs after it.

METHOD, and every clause is a scar:
  - Scored EXACTLY as measure_primitive.py scored the 10/10, so that run remains
    a comparable historical baseline rather than a different quantity.
  - INTERLEAVED (10.5): route performance has a large session-to-session
    component, and blocking the arms would confound the arm with the hour.
  - n = 10 per arm (10.3): n=3 has power 0.00 for the effects looked for here.
  - The arm is set in the CHILD process, so process death IS the restore and a
    cleanup cannot reinstate a stale default (10.x, four harnesses had that bug).
  - The timeout is enforced from OUTSIDE the process (10.14): signal.alarm did
    not interrupt a 590s trial blocked inside a capture call.
  - A trial that cannot be measured is INVALID, never a failure (10.6).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import _harness

TARGET = "bar_pool_room"
TRIALS = _harness.TRIALS         # 10
ATTEMPTS = 3                     # as the 10/10 baseline ran it
TIMEOUT = 900                    # the failing run took 274-446s; do not censor
OUT = os.path.join(HERE, "ab_leg1.json")
SHOTS = os.path.join(HERE, "leg1_failframes")

ARMS = ("shipped", "original")

# THE 'original' ARM'S VALUES, NAMED RATHER THAN WRITTEN INLINE. As bare
# literals these are indistinguishable from a harness reinstating a stale
# default -- the exact defect that put an arm into four earlier harnesses and
# that tests/harness/test_harness_restores_shipped_value.py exists to catch. It
# caught these too, correctly: the check cannot read intent from a literal. They
# are an ARM, not a restore: this is how leg 1 executed when the 10/10 was
# measured, before 2026-09-05 23:33 and 2026-09-06 00:20 respectively.
ORIGINAL_LEG_SPEED = {}          # no per-leg speed override existed
ORIGINAL_MERGE_LEGS = set()      # no leg was merged


def set_arm(gw, arm, log):
    """Configure leg 1. Runs in the CHILD, so nothing has to be put back.

    'shipped' deliberately touches NOTHING -- it is whatever graph_walk actually
    ships, read back and logged rather than asserted, so this harness cannot
    drift from the shipped value the way four earlier ones did by restoring a
    literal written on the day they were themselves written.
    """
    leg = ("office_corridor", "office_door")
    if arm == "original":
        gw.LEG_SPEED_BY_LEG = dict(ORIGINAL_LEG_SPEED)
        gw.MERGE_STEPS_BY_LEG = set(ORIGINAL_MERGE_LEGS)
    elif arm != "shipped":
        raise SystemExit(f"unknown arm {arm!r}")
    log(f"  arm={arm}  LEG_SPEED_BY_LEG={gw.LEG_SPEED_BY_LEG.get(leg)}  "
        f"MERGE_STEPS_BY_LEG={leg in gw.MERGE_STEPS_BY_LEG}  "
        f"MERGED_TURN_TOLERANCE={getattr(gw, 'MERGED_TURN_TOLERANCE', None)}")


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
    ok = gw.go_to_node_verified(m, TARGET, log=log, attempts=ATTEMPTS,
                                shots=SHOTS, start_hint=gw.SPAWN)
    secs = round(time.time() - t0, 1)

    # Independent confirmation from a settled pose, as the baseline did. A
    # disagreement between the primitive and locate() is worth more than the
    # arrival rate itself.
    where, detail = gw.locate(m, log=log)
    return {"arm": arm, "arrived": bool(ok), "seconds": secs,
            "located": where, "detail": str(detail)[:140],
            "agrees": bool(ok) == (where == TARGET),
            **_harness.census_kinds(gw),
            "measurable": gw._LAST_TRIAL_MEASURABLE}


def main():
    def log(m):
        print(m, flush=True)

    _harness.assert_map_pristine(os.path.join(ROOT, "world_map.json"), log=log)
    if not _harness.alive():
        raise SystemExit("the stream is not up; not starting")

    import graph_walk as gw
    res = {"question": "Did the leg-1 speed+merge changes cost route arrival?",
           "target": TARGET, "attempts": ATTEMPTS, "trials": TRIALS,
           "baseline": {"when": "2026-09-05 23:12", "arrived": "10/10",
                        "median_s": 52.9, "leg1": "original"},
           "shipped_config": {
               "LEG_SPEED_BY_LEG": {str(k): v for k, v in gw.LEG_SPEED_BY_LEG.items()},
               "MERGE_STEPS_BY_LEG": [str(x) for x in gw.MERGE_STEPS_BY_LEG],
               "MERGED_TURN_TOLERANCE": getattr(gw, "MERGED_TURN_TOLERANCE", None),
               "TRUST_RESET_SPAWN": gw.TRUST_RESET_SPAWN,
               "RECOVER_MISSED": gw.RECOVER_MISSED,
               "NULL_YAW_BEFORE_ALIGN": gw.NULL_YAW_BEFORE_ALIGN,
           },
           "runs": []}
    log(f"leg-1 A/B: {TRIALS} trials per arm, interleaved, target {TARGET}")
    log(f"  shipped: {res['shipped_config']}")

    # interleave() yields (trial_index, arm) -- taking it as a bare arm string
    # silently gave every trial the same arm. Unpack it.
    for i, (_t, arm) in enumerate(_harness.interleave(ARMS, TRIALS), 1):
        r, secs = _harness.run_trial(__file__, arm, TIMEOUT, log=log)
        if r is None:
            log(f"[{i:2d}] {arm:9s} INVALID after {secs:.0f}s "
                f"(timeout, crash, or the stream went down) — not a failure")
            res["runs"].append({"arm": arm, "arrived": None,
                                "reason": "unmeasurable", "seconds": secs})
        else:
            log(f"[{i:2d}] {arm:9s} {'ARRIVED' if r['arrived'] else 'missed  '} "
                f"in {r['seconds']:.0f}s  located={r['located']}"
                f"{'  DISAGREED' if not r['agrees'] else ''}")
            res["runs"].append(r)
        _harness.save_result(OUT, res)

    log("")
    for arm in ARMS:
        rows = [r for r in res["runs"] if r["arm"] == arm]
        val = [r for r in rows if r.get("arrived") is not None]
        arr = [r for r in val if r["arrived"]]
        med = (sorted(r["seconds"] for r in arr)[len(arr) // 2] if arr else None)
        log(f"  {arm:9s} {len(arr)}/{len(val)} arrived"
            f"  ({len(rows) - len(val)} invalid)"
            f"  median {med if med is not None else '-'}s")
        _harness.report_kinds(val, out=log, indent="            ")
    log(f"\n  -> {OUT}")
    log("  Report BY CLASS, not just overall: arrival averages several different")
    log("  failures, so a change that kills one class moves the total by a third")
    log("  of it and looks flat at n=10.")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        import json
        print(json.dumps(one_trial(sys.argv[2])), flush=True)
    else:
        main()
