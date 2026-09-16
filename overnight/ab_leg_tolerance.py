"""A/B: does tightening the leg turn tolerance make the route land?

THE HYPOTHESIS, written before the run:
  slow_traverse's 4.0 deg tolerance is WIDER than the curvature of most legs, so
  turn_to returns without turning and the leg is walked straight at whatever
  heading the character arrived with. Measured on portrait_room ->
  bar_pool_room: four commanded bearings spanning 6.6 deg, all four no-ops, the
  character sitting at 289.1 the whole way.

  IF THE HYPOTHESIS IS RIGHT: tightening the tolerance walks the recorded curve
  and verified depth improves.
  IF IT IS WRONG: depth is unchanged or worse, and the recorded curve was never
  what mattered.

MEASURED ON VERIFIED POSITIONS, never on follow()'s "reached" — that is a
ROUTING CLAIM, and measuring with it is how "the four legs before it land every
time" became a published wrong finding.

ARMS ARE INTERLEAVED, not blocked. The console drifts over a session (NPCs
move, the stream degrades); running all of arm A then all of arm B would
confound the arm with the hour.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

# THE SHIPPED VALUE, CAPTURED -- never a literal. This restore used to hardcode
# what the default was ON THE DAY THE SCRIPT WAS WRITTEN, so it silently rotted
# into a WRONG value: ab_leg_speed restored {} after leg 1 shipped an override
# of 3.0, and ab_stall restored 2.5 after STALL_CHANGE became 6.0. A cleanup
# that reinstates a stale default is worse than no cleanup -- it looks like
# tidiness and installs an arm.
import graph_walk as _gw_shipped   # noqa: E402
_SHIPPED = {"LEG_TURN_TOLERANCE": _gw_shipped.LEG_TURN_TOLERANCE}

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]
TRIALS = 10                     # per arm, interleaved => 20 route walks.
                                # 10 is the MINIMUM that can resolve a 1.0-depth
                                # effect (power 0.94). n=3 has power 0.00 and is
                                # what every reversed A/B on this project used.
TRIAL_TIMEOUT = 240             # seconds; a wedged trial is dropped, not waited
                                # on -- and since the migration below it really
                                # is dropped: the ceiling is a kill from the
                                # parent, not a signal this process can miss.
ARMS = [("baseline_4.0", None), ("tight_1.0", 1.0)]
OUT = os.path.dirname(os.path.abspath(__file__))

res = {"route": ROUTE, "trials_per_arm": TRIALS, "runs": [],
       "started": time.strftime("%H:%M:%S")}


# _quiet, NOT the bare lambda. Silencing the RESET is defensible — reset noise
# is not the measurement — but writing `log=lambda *a: None` here puts the exact
# literal that means "bug" everywhere else in this project one line above the
# measurement call, which is how it kept getting copied onto the measurement.
def _quiet(*a, **k):
    pass


def log(m):
    print(m, flush=True)


def save():
    _harness.save_result(os.path.join(OUT, "ab_leg_tolerance.json"), res)


def fingerprint():
    import hashlib
    h = hashlib.sha256()
    for f in ("graph_walk.py", "slow_traverse.py", "walk_steps.py"):
        h.update(open(f, "rb").read())
    return h.hexdigest()[:16]


def stream_alive(gap=1.0):
    """Is the picture actually updating? 0.00 means the console is asleep.

    Added 2026-09-03: a whole confirmation run was taken while the PS5 was
    switching itself off. Every trial recorded depth 1 — "the first node
    verified, then nothing" — which is what a FROZEN picture looks like, not a
    routing failure. The harness recorded CANNOT SEE as DID NOT ARRIVE and the
    result read as a clean refutation.
    """
    import compass
    import numpy as np
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) > 0.35


def one_run(arm, tol):
    """Walk the route from a reset spawn. Returns how many nodes were VERIFIED.

    RUNS IN THE `--one-trial` CHILD. Setting gw.LEG_TURN_TOLERANCE here means
    process death IS the restore: it cannot be forgotten, and it cannot
    reinstate a stale literal the way four earlier harnesses did.

    Hard-capped: on 2026-09-03 a trial wedged in a retry loop for 25 minutes
    with the console perfectly healthy, and the run lost its last two trials to
    it. A dropped trial costs one data point; a wedged one costs the night. The
    cap is now the PARENT's, enforced by killing this process -- see the note in
    main(); the signal.alarm this file used to arm could not have delivered it.

    A raise here is the loud path and is meant to be: the child dies, prints no
    JSON, and run_trial scores the trial INVALID. That is never a failed trial.
    """
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    if not stream_alive():
        raise RuntimeError("stream is not updating — console asleep; "
                           "refusing to record a depth")
    gw.LEG_TURN_TOLERANCE = tol
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet)
    time.sleep(1.5)

    depth, where = 0, gw.SPAWN
    for node in ROUTE:
        gw.follow(m, where, node, log=log)
        got, detail = gw.locate(m, log=log)
        if got == node:
            depth += 1
            where = node
            log(f"    verified {node}")
        else:
            log(f"    lost at {node} (here: {got!r} {detail})")
            break
    return depth


def main():
    fp = fingerprint()
    res["code_fingerprint"] = fp
    log(f"code fingerprint {fp}\narms: {[a for a, _ in ARMS]}, "
        f"{TRIALS} interleaved trials each\n")
    for t in range(TRIALS):
        for arm, _tol in ARMS:
            log(f"  [{arm}] trial {t + 1}/{TRIALS}")
            # THE CEILING IS ENFORCED FROM OUTSIDE THE PROCESS. This used to arm
            # signal.alarm, and Python can only deliver a signal BETWEEN
            # bytecode instructions — so an alarm cannot interrupt a trial
            # blocked inside a C call, which every screen capture is. Measured
            # 2026-09-03 (CLAUDE.md 10.14): a 590s trial sailed straight past a
            # 260s alarm, the run produced nothing, and the ceiling LOOKED like
            # it was working. That is 10.1's whole family — the code did nothing
            # and doing nothing was indistinguishable from working. run_trial
            # re-invokes this file as `--one-trial <arm>` and kills the child
            # from HERE, so the kill is real.
            #
            # THE ARM TRAVELS AS ITS NAME, NOT ITS VALUE. The child imports this
            # same module and looks the value up in ARMS. `None` and `1.0` would
            # both survive argv, but the sibling harnesses arm a dict and a
            # string, so passing the name is the one thing that is uniform
            # across all of them — and a uniform contract is what stops the next
            # copy-paste reintroducing this.
            r, secs = _harness.run_trial(__file__, arm, TRIAL_TIMEOUT, log=log)
            # NULL THE DEPTH BEFORE RECORDING IT, NOT AFTER — which is now
            # STRUCTURAL rather than a rule to remember. This used to append the
            # row first and then set `d = None`, so the row kept the
            # contaminated depth while the log said "discarding this depth". The
            # analysis below reads res["runs"], not `d`, so every trial the
            # console slept through was scored as a real result — in the one arm
            # that had been running longest. CLAUDE.md 10.6 exists because a
            # sleeping console once made BOTH arms degrade together; that was
            # the same failure with the evidence deleted.
            #
            # run_trial makes it unwritable. It performs the post-trial stream
            # check itself (once, in the one function every harness routes
            # through) and returns None for a dead stream exactly as it does for
            # a timeout or a crash — INVALID, never a failure. So the depth is
            # already None before any row exists, and this harness's own
            # post-trial stream_alive() call is gone as redundant. The PRE-trial
            # check still runs, inside one_run, in the child.
            d = None if r is None else r.get("depth")
            res["runs"].append({"arm": arm, "trial": t + 1, "depth": d})
            log(f"    depth {d} of {len(ROUTE)} in {secs}s")
            save()
    if fingerprint() != fp:
        res["INVALID"] = "source changed mid-run; discard"
        log("*** SOURCE CHANGED MID-RUN — measurement INVALID ***")
    save()


def one_trial(name):
    """ONE trial, run in the child. Prints one JSON object and exits.

    The arm arrives as its NAME and the value is looked up HERE, in the child's
    own copy of ARMS. A missing name raises KeyError naming it, which the parent
    forwards from stderr and scores INVALID.
    """
    return {"arm": name, "depth": one_run(name, dict(ARMS)[name])}


if __name__ == "__main__":
    # THE CHILD BRANCH MUST NOT REACH save(). It shares this module with the
    # parent, so a stray save() here would write a child's empty `res` over the
    # parent's accumulating results file mid-run.
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        print(json.dumps(one_trial(sys.argv[2])), flush=True)
        sys.exit(0)
    try:
        main()
    finally:
        # STILL WORTH DOING THOUGH THE TRIALS ARE CHILDREN NOW: a child killed
        # on the ceiling runs no `finally` of its own, so it can leave the stick
        # deflected until chiaki's own INJECT_TIMEOUT_MS releases it.
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        # The arm is installed in the CHILD, which exits, so this is now a
        # belt-and-braces rather than the restore. It is kept because it is
        # taken from the CAPTURE above and so cannot be wrong — a restore that
        # names a literal is how ab_leg_speed and ab_stall each reinstated a
        # stale default and silently installed an arm.
        try:
            import graph_walk as gw
            gw.LEG_TURN_TOLERANCE = _SHIPPED["LEG_TURN_TOLERANCE"]
        except Exception:
            pass
        save()
    print("\n--- A/B RESULT (verified depth of %d) ---" % len(ROUTE))
    for arm, _ in ARMS:
        ds = [r["depth"] for r in res["runs"]
              if r["arm"] == arm and r["depth"] is not None]
        if ds:
            print(f"  {arm:14} {ds}  mean {sum(ds) / len(ds):.2f}")
        else:
            print(f"  {arm:14} no completed runs")
    print("\n  n is small. Treat this as a DIRECTION, not a coefficient.")
