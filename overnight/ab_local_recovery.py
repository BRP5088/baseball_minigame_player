"""OPEN-7: does searching locally beat resetting to the spawn?

METRIC: verified arrival at bar_pool_room, SECONDS per trial, and failures BY
CLASS. The seconds are the point. A reset re-walks the whole route, so if local
search arrives as often but faster, that alone multiplies how much can be
measured per hour. The fan is currently the single largest item on the clock:
~79s each and ~33% of a streak trial, confirmed twice by independent routes.

WHAT CHANGED HERE (2026-09-06), and why the previous version could not be
trusted to run unattended:

* THE TIMEOUT DID NOT WORK. It armed `signal.alarm`, and CLAUDE.md 10.14
  records that a 590s trial sailed straight past a 260s alarm because the
  process was blocked inside a screen capture. An A/B whose whole thesis is
  "this arm is faster" cannot enforce its ceiling from inside the process it is
  timing -- and worse, a ceiling that only bites one arm censors exactly the
  arm it bites. Trials now run as subprocesses through `_harness.run_trial`,
  where the kill is a real SIGKILL from a parent.

* IT CARRIED ITS OWN COPY OF `alive()`. Three scripts had one and three did
  not; `_harness.alive` is the one that is maintained, and run_trial checks the
  stream AFTER every trial as well as before -- which is what tells a console
  that fell asleep mid-leg apart from an arm that failed.

* TRIALS WAS 8. The documented minimum is 10: power 0.94 at n=10 against 0.00
  at n=3, and 8 is not a number anyone chose, it is a number nobody revisited.

* ITS CLEANUP RESTORED THE WRONG VALUE. The `finally` set
  `gw.LOCAL_RECOVERY_FIRST = True`, while the shipped default is False. In
  process that only mattered on the way out; as a pattern it is how an arm gets
  left installed. The arm is now set inside the trial subprocess, so the parent
  never holds it at all and there is nothing to restore.

* IT REPORTED ONLY A TOTAL. Arrival averages several different failures
  together, so a change that eliminates one whole class moves the total by
  about a third of it -- invisible at n=10, and the leading explanation on this
  project for why so many well-motivated changes measured flat. It now reports
  by class, with the provenance split, through the shared reporter.
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

TARGET = "bar_pool_room"
TRIALS = _harness.TRIALS          # 10; n=3 has power 0.00 here
# Generous, and it must be: this A/B's "local" arm exists to spend longer, and
# CLAUDE.md 10.14 records an attempts A/B that lost 3 of 6 deep-arm trials to a
# ceiling that censored precisely the arm whose mechanism is "spend longer".
TIMEOUT = 900
ARMS = (("local", True), ("reset", False))
OUT = os.path.dirname(os.path.abspath(__file__))

res = {"question": "OPEN-7: is a local recovery fan better than resetting?",
       "target": TARGET, "trials": TRIALS, "runs": []}


# _quiet, NOT the bare lambda. Silencing the RESET is defensible -- reset noise
# is not the measurement -- but writing `log=lambda *a: None` here puts the
# exact literal that means "bug" everywhere else in this project one line above
# the measurement call, which is how it kept getting copied onto the
# measurement.
def _quiet(*a, **k):
    pass


def log(m):
    print(m, flush=True)


def save():
    _harness.save_result(os.path.join(OUT, "ab_local_recovery.json"), res)


def one_trial(local):
    """Reset, then reach TARGET with the given recovery strategy."""
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    gw.LOCAL_RECOVERY_FIRST = local
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet)
    time.sleep(1.2)

    # attempts=3, the production default: this experiment's SUBJECT is the
    # retrying/recovery behaviour, so it must run the primitive as production
    # runs it. (A leg comparison would use the default attempts=1.)
    # start_hint: the reset just landed on SPAWN, which locate() is designed
    # never to name -- without it every trial in BOTH arms pays ~24s for a
    # sweep and a second reset.
    r = _harness.walk_leg_under_test(gw, m, gw.SPAWN, TARGET,
                                     log=log, attempts=3)
    r["arm_local"] = local
    return r


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        arm = sys.argv[2]
        try:
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

    log(f"OPEN-7: {TRIALS} interleaved trials per arm, target {TARGET}")
    log("  local = try a recovery fan before resetting; reset = reset first\n")
    try:
        for t, (name, _local) in _harness.interleave(ARMS, trials=TRIALS):
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
            else:
                ok = bool(r["arrived"])
                log(f"  [{name}] {t+1}/{TRIALS}: arrived={ok} in {secs}s "
                    f"(located {r.get('located')})")
                res["runs"].append(
                    _harness.leg_trial_row(name, r, secs, ok))
            save()
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        save()

    print("\n--- RESULT ---")
    for name, _ in ARMS:
        v = [r for r in res["runs"]
             if r["arm"] == name and r["arrived"] is not None]
        inv = sum(1 for r in res["runs"]
                  if r["arm"] == name and r["arrived"] is None)
        _harness.report_leg_arm(name, v, inv)
        secs = [r["seconds"] for r in v if r.get("seconds")]
        if secs:
            # THE SECONDS ARE THE POINT of this experiment, so they are stated
            # with their spread, not as a bare median. The previously recorded
            # 155.4s vs 76.3s is the number this run is testing.
            print(f"            seconds: median {statistics.median(secs):.0f}, "
                  f"min {min(secs):.0f}, max {max(secs):.0f}  (n={len(secs)})")
