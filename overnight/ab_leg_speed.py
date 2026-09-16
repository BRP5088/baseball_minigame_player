"""A/B: do the office legs still ARRIVE when walked 3x faster?

The win condition is TIME, not arrival — so flat arrival with fewer seconds is
a WIN, not a null. Both are recorded.

The detector is unusually sensitive: `office_door -> portrait_room` has arrived
20/20, so any degradation shows immediately. The corridor leg has no reference
by design, but it does not need one — if speeding it up breaks anything,
portrait_room arrival falls off 20/20.

Capped at LEG_SPEED_MAX = 0.60, which is where measured repeatability collapses
(spread 15px through 0.45, 27 at 0.60, 124 at 0.75, 476 at 0.85).
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

# THERE IS NOTHING TO RESTORE ANY MORE, AND THAT IS THE POINT. The arm is
# installed inside the `--one-trial` CHILD, which then exits, so PROCESS DEATH
# is the restore. It cannot be forgotten and it cannot be written wrong.
#
# What that replaces is a `_SHIPPED` capture re-assigned in a `finally`, and the
# lesson which forced that capture stays here for anyone tempted to put a
# restore back. This script's restore used to hardcode what the default was ON
# THE DAY THE SCRIPT WAS WRITTEN, so it silently rotted into a WRONG value:
# ab_leg_speed restored {} after leg 1 shipped an override of 3.0, and ab_stall
# restored 2.5 after STALL_CHANGE became 6.0. A cleanup that reinstates a stale
# default is worse than no cleanup -- it looks like tidiness and installs an
# arm. The parent process no longer touches gw.LEG_SPEED_BY_LEG at all, so
# there is no value left for it to get wrong.

TARGET = "portrait_room"
TRIALS = 8
TIMEOUT = 240
FAST = {("office_corridor", "office_door"): 3.0,
        ("office_door", "portrait_room"): 3.0}
# THE ARM TRAVELS AS ITS NAME, NEVER AS ITS VALUE. These values are dicts keyed
# by TUPLES and no argv can carry one. The child imports this same module and
# looks the name up in this same list, so the two processes cannot disagree
# about what an arm is.
ARMS = [("fast_3x", FAST), ("normal", {})]
OUT = os.path.dirname(os.path.abspath(__file__))
res = {"target": TARGET, "runs": []}


# _quiet, NOT the bare lambda. Silencing the RESET is defensible — reset noise
# is not the measurement — but writing `log=lambda *a: None` here puts the exact
# literal that means "bug" everywhere else in this project one line above the
# measurement call, which is how it kept getting copied onto the measurement.
def _quiet(*a, **k):
    pass


def log(m): print(m, flush=True)
def save(): _harness.save_result(os.path.join(OUT, "ab_leg_speed.json"), res)


def one(overrides):
    import graph_walk as gw, reset_env, worldmap as wm
    # _harness.alive, not a local copy: this is the BEFORE half of the stream
    # check whose AFTER half run_trial performs, and the two halves have to be
    # the same instrument or a trial can pass one and fail the other for
    # reasons that are about the code rather than the console.
    if not _harness.alive(): raise RuntimeError("stream not updating")
    gw.LEG_SPEED_BY_LEG = dict(overrides)
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet); time.sleep(1.2)
    t0 = time.time()
    ok = gw.go_to_node_verified(m, TARGET, log=log, start_hint=gw.SPAWN)
    return bool(ok), round(time.time() - t0, 1)


def one_trial(name):
    """Run exactly ONE trial in this child process and return its result row."""
    arms = dict(ARMS)
    if name not in arms:
        raise SystemExit(f"unknown arm {name!r}; known: {sorted(arms)}")
    ok, secs = one(arms[name])
    return {"arm": name, "arrived": ok, "seconds": secs}


def main():
    try:
        # THE CEILING IS ENFORCED FROM OUTSIDE THE PROCESS, by run_trial killing
        # a child. This loop used to arm signal.alarm around `one()`, and Python
        # can only deliver a signal BETWEEN bytecode instructions -- so an alarm
        # cannot fire while the trial is blocked inside a C call, which every
        # screen capture is. Measured (CLAUDE.md 10.14): a 590s trial sailed
        # past a 260s alarm. The run produced nothing and the ceiling LOOKED
        # like it was working, which is 10.1 exactly -- the code did nothing and
        # doing nothing was indistinguishable from working.
        #
        # run_trial also makes a trial that cannot be measured INVALID (None)
        # rather than a failure, checks the stream AFTER the trial (10.6: a
        # console falling asleep degrades both arms at once and reads as a bad
        # change), and forwards the child's log live.
        for t, name in _harness.interleave([n for n, _ in ARMS], TRIALS):
            r, wall = _harness.run_trial(__file__, name, TIMEOUT, log=log)
            if r is None:
                ok, secs = None, None
                log(f"  [{name}] {t+1}: INVALID after {wall:.0f}s — timed out, "
                    f"crashed, or the stream went down. NOT a failure.")
            else:
                ok, secs = r["arrived"], r["seconds"]
            log(f"  [{name}] {t+1}/{TRIALS}: {ok} in {secs}s")
            res["runs"].append({"arm": name, "arrived": ok, "seconds": secs})
            save()
    finally:
        # THE PARENT CLEARS THE STICK BECAUSE A KILLED CHILD CANNOT. A trial
        # that blows its ceiling is SIGKILLed mid-leg, so any deflection it had
        # in flight is still held until something zeroes it. The ARM needs no
        # undoing -- it lived and died with the child.
        try:
            import analog_replay as ar; ar.send(["clear"])
        except Exception: pass
        save()
    import statistics
    print("\n--- RESULT ---")
    for name, _ in ARMS:
        v = [r for r in res["runs"] if r["arm"] == name and r["arrived"] is not None]
        if v:
            a = [r["arrived"] for r in v]; s = [r["seconds"] for r in v if r["seconds"]]
            print(f"  {name:8} arrived {sum(a)}/{len(a)}   median {statistics.median(s):.0f}s")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        print(json.dumps(one_trial(sys.argv[2])), flush=True)
    else:
        main()
