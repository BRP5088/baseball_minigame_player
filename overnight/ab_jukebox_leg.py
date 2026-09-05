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
TIMEOUT = 300
MAP = os.path.join(ROOT, "world_map.json")
BACKUP = os.path.join(HERE, "_ab_map_backup.json")
OUT = os.path.join(HERE, "ab_jukebox_leg.json")
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
ARMS = [("restored", RESTORED), ("short", SHORT)]

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


def one_trial():
    """Reset, reach START verified, walk the leg, report whether we arrived."""
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    reset_env.reset_environment(log=log, progress_file=None)
    time.sleep(1.2)
    m = wm.WorldMap.load()

    # Reaching the START must be VERIFIED, or the leg is walked from nowhere in
    # particular and the trial says nothing about the leg.
    if not gw.go_to_node_verified(m, START, log=log, attempts=3, shots=SHOTS):
        return {"reached_start": False}

    # CAPTURE WHETHER THE LEG WAS ABANDONED, not just whether it arrived.
    # The restored leg is 5 steps where the short one was 1, so the stall gate
    # gets five chances to fire instead of one — and its threshold (6.0
    # grey_levels) sits INSIDE the measured moving population (3.1-7.9). A bare
    # arrived/not tells us nothing about which of those two things happened.
    lines = []
    def tee(m):
        lines.append(str(m))
        log(m)
    gw.walk_link(m, START, TARGET, log=tee)
    where, detail = gw.locate(m, log=log)
    joined = "\n".join(lines)
    abandoned = "abandoning the rest of this leg" in joined
    stalls = joined.count("stall score")
    steps_walked = joined.count("-> walked")
    return {"reached_start": True, "arrived": where == TARGET,
            "located": where, "detail": str(detail)[:120],
            "abandoned": abandoned, "stall_events": stalls,
            "steps_walked": steps_walked}


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        arm = sys.argv[2]
        try:
            set_leg(dict(ARMS)[arm])
            print(json.dumps(one_trial()))
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
    log(f"OPEN-14: {TRIALS} interleaved trials per arm on {START} -> {TARGET}")
    log(f"  restored = {sum(s['dur']*s['speed'] for s in RESTORED):.3f} units "
        f"/ {sum(s['dur'] for s in RESTORED):.2f}s")
    log(f"  short    = {sum(s['dur']*s['speed'] for s in SHORT):.3f} units "
        f"/ {sum(s['dur'] for s in SHORT):.2f}s\n")
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
                res["runs"].append({"arm": name, "arrived": ok,
                                    "located": r.get("located"),
                                    "abandoned": r.get("abandoned"),
                                    "stall_events": r.get("stall_events"),
                                    "steps_walked": r.get("steps_walked"),
                                    "seconds": secs})
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
        if v:
            a = sum(1 for r in v if r["arrived"])
            ab = sum(1 for r in v if r.get("abandoned"))
            st = sum(r.get("stall_events") or 0 for r in v)
            sw = sum(r.get("steps_walked") or 0 for r in v)
            print(f"  {name:9} arrived {a}/{len(v)} valid   ({inv} invalid)")
            print(f"            abandoned by the stall gate: {ab}/{len(v)}   "
                  f"stall events {st}   steps walked {sw}")
        else:
            print(f"  {name:9} NO VALID TRIALS ({inv} invalid)")
