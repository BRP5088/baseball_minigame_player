"""OPEN-14 — does the RESTORED jukebox leg actually arrive?

THE FINDING. `bar_pool_room -> bar_jukebox` was re-recorded 2026-09-04 as ONE
0.80s step at speed 0.30 = 0.240 walk-units. The human recording the map was
built from covers that span in 1.032 units over 3.32s, and a second independent
recording agrees to 5%. Every other leg matches its recording at 0.91-0.98; this
one was 0.22. From the far edge of bar_pool_room's recognition basin the short
leg lands 0.703 units SHORT of bar_jukebox's basin — it cannot arrive.

THE USER SAW THIS FIRST, from the stream: "when you make the turn, you actually
walk right out of the bar." It went unexplained for days.

WHY THIS IS MEASURED PER-LEG, NOT PER-ROUTE. A full route is ~300s a trial; one
leg is ~90s. The question is about this leg, and CLAUDE.md is explicit that
measuring full-route depth to learn about one leg wastes the clock.

ARMS ARE INTERLEAVED because route performance has a large session-to-session
component that dwarfs the effect being measured. Blocking the arms would
confound the arm with the hour.
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import _harness

TRIALS = 10
TIMEOUT = 480
MAP = os.path.join(ROOT, "world_map.json")
BACKUP = os.path.join(HERE, "_ab_map_backup.json")
OUT = os.path.join(HERE, "ab_stall_lenient.json")
SHOTS = os.path.join(HERE, "jukebox_failframes")

START, TARGET = "bar_pool_room", "bar_jukebox"

# The two arms, as the leg's steps.
RESTORED = [
    {"bearing": 2.08, "dur": 0.797, "speed": 0.268},
    {"bearing": 1.16, "dur": 0.787, "speed": 0.327},
    {"bearing": 0.76, "dur": 0.797, "speed": 0.326},
    {"bearing": 359.43, "dur": 0.785, "speed": 0.327},
    {"bearing": 359.61, "dur": 0.138, "speed": 0.319},
]
SHORT = [{"bearing": 2.1, "dur": 0.8, "speed": 0.3}]

# OPEN-15: the leg is FIXED at RESTORED; the arms are STALL_CHANGE values.
#
# WHY THIS IS NOT A REPEAT of the 2026-09-03 STALL_CHANGE A/B. That one ran on
# the SHORT leg — one 0.80s push, where the gate barely gets a chance to fire
# (0 stall events in 10 trials, measured). It concluded "keep 6.0" from a leg
# that could not trigger the thing being tested.
#
# On the restored 5-step leg the gate fires on 6 of 10 trials, and those 6
# arrived 0/6 while the 4 clean trials arrived 4/4 (Fisher p = 0.0048). That is
# an ASSOCIATION, and the last association about this very constant measured
# p = 0.00039 and then LOST its intervention. So this run intervenes.
#
# 20.0 does not disable the gate — a genuine block produces near-zero view
# change and still trips it. It moves the bar clear of the measured MOVING
# population (3.1-7.9 grey_levels), which 6.0 sits inside.
# ARMS CORRECTED 2026-09-05. The first version used 20.0 as the "lenient" arm.
# The test is `best < STALL_CHANGE` -> stalled, so a HIGHER bar fires MORE, not
# less: at 20.0 the whole moving population (3.1-7.9 grey_levels) counts as
# stalled, and that arm abandoned 8 of 10 legs. It measured the opposite of
# what its own docstring claimed.
#
# 2.5 is the lenient direction. It is also the value the 2026-09-03 A/B chose
# and rejected (6/10 vs 8/10, p = 0.63) — but that ran on the SHORT leg, which
# produced 0 stall events in 10 trials. It rejected a threshold nothing could
# trigger. On the restored 5-step leg the gate fires on most trials, so this is
# a genuine first test rather than a repeat.
ARMS = [("stall_2p5", 2.5), ("stall_6", 6.0)]

res = {"trials": TRIALS, "runs": []}


def log(m):
    print(m, flush=True)


def save():
    # Atomic. A Ctrl-C during a truncate-first write loses the whole run, and a
    # route trial costs ~90s — 20 of them is 30 minutes that cannot be
    # re-run and compared, because performance varies session to session.
    _harness.save_result(OUT, res)


def set_leg(steps):
    m = json.load(open(MAP))
    m["links"][START][TARGET] = {
        "cost": round(sum(s["dur"] for s in steps), 2),
        "steps": steps,
        "recorded": "A/B arm, set by ab_jukebox_leg.py",
    }
    # Already atomic (temp + fsync + replace); routed through the shared helper
    # so there is one implementation to audit rather than two.
    _harness.save_result(MAP, m, indent=1)


def one_trial(stall_change):
    """Reset, reach START verified, walk the leg, report whether we arrived.

    THE TREATMENT IS SCOPED TO THE LEG UNDER TEST. A first version set
    graph_walk.STALL_CHANGE globally, which also raised it for the APPROACH
    legs — with blockage detection effectively off, the character ground into
    furniture on the way to bar_pool_room and two stall_20 trials died before
    the leg was ever walked (248s, then a 300s timeout). An experiment whose
    treatment contaminates its own setup cannot answer the question.
    """
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()

    # Reaching the START must be VERIFIED, or the leg is walked from nowhere in
    # particular and the trial says nothing about the leg.
    if not gw.go_to_node_verified(m, START, log=log, attempts=3, shots=SHOTS,
                                  start_hint=gw.SPAWN):
        return {"reached_start": False}

    # CAPTURE WHETHER THE LEG WAS ABANDONED, not just whether it arrived.
    # The restored leg is 5 steps where the short one was 1, so the stall gate
    # gets five chances to fire instead of one — and its threshold (6.0
    # grey_levels) sits INSIDE the measured moving population (3.1-7.9). A bare
    # arrived/not tells us nothing about which of those two things happened.
    _saved = gw.STALL_CHANGE
    gw.STALL_CHANGE = stall_change
    try:
        return _harness.walk_leg_under_test(gw, m, START, TARGET,
                                           shots=SHOTS, log=log)
    finally:
        gw.STALL_CHANGE = _saved


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        arm = sys.argv[2]
        try:
            set_leg(RESTORED)                      # the leg is not the variable
            print(json.dumps(one_trial(dict(ARMS)[arm])))
        except Exception as e:
            print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        finally:
            try:
                import analog_replay as ar
                ar.send(["clear"])
            except Exception:
                pass
        sys.exit(0)

    # Before the backup, not after: a backup of a contaminated map is
    # indistinguishable from a backup of a clean one.
    _harness.assert_map_pristine(MAP, log=log)
    shutil.copy(MAP, BACKUP)
    log(f"OPEN-15: {TRIALS} interleaved trials per arm on {START} -> {TARGET}")
    log(f"  leg FIXED at the restored "
        f"{sum(s['dur']*s['speed'] for s in RESTORED):.3f} units / "
        f"{sum(s['dur'] for s in RESTORED):.2f}s")
    log(f"  arms: STALL_CHANGE {[v for _n, v in ARMS]}  "
        f"(moving population measures 3.1-7.9 grey_levels)\n")
    try:
        for t, (name, _steps) in _harness.interleave(ARMS, trials=TRIALS):
            if not _harness.alive():
                log(f"  [{name}] {t+1}: stream DEAD before the trial — invalid")
                res["runs"].append({"arm": name, "arrived": None,
                                    "reason": "stream dead before"})
                save()
                continue
            r, secs = _harness.run_trial(__file__, name, TIMEOUT, log=log)
            if r is None or "error" in (r or {}):
                why = (r or {}).get("error", "timeout/crash")
                log(f"  [{name}] {t+1}/{TRIALS}: INVALID ({why}) after {secs}s")
                res["runs"].append({"arm": name, "arrived": None,
                                    "reason": why, "seconds": secs})
            elif not r.get("reached_start"):
                log(f"  [{name}] {t+1}/{TRIALS}: INVALID — never reached "
                    f"{START}, so the leg was never tested ({secs}s)")
                res["runs"].append({"arm": name, "arrived": None,
                                    "reason": "start not reached",
                                    "seconds": secs})
            else:
                ok = bool(r["arrived"])
                log(f"  [{name}] {t+1}/{TRIALS}: arrived={ok} "
                    f"(located {r.get('located')}, "
                    f"{r.get('steps_walked')} step(s) walked, "
                    f"{'ABANDONED' if r.get('abandoned') else 'ran to the end'}, "
                    f"{r.get('stall_events')} stall event(s)) in {secs}s")
                res["runs"].append(
                    _harness.leg_trial_row(name, r, secs, ok))
            save()
    finally:
        shutil.copy(BACKUP, MAP)
        log("\n  map restored from backup")
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        save()

    print("\n--- RESULT ---")
    for name, _ in ARMS:
        v = [r for r in res["runs"] if r["arm"] == name and r["arrived"] is not None]
        inv = sum(1 for r in res["runs"] if r["arm"] == name and r["arrived"] is None)
        _harness.report_leg_arm(name, v, inv)
