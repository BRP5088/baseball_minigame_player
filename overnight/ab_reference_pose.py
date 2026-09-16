"""A/B: did swapping the align references to the BOT's poses hurt arrivals?

THE HYPOTHESIS, written before the run.

places/<node>/route_*.jpg was overwritten with the bot's own arrival frames on
2026-09-03, while world_map.json still holds the HUMAN's legs. Measured
separation: 71-212px. So align_at_node now pulls the character onto pose A and
walks a leg recorded from pose B.

  IF THE SWAP HURT:   "human" references beat "bot" on arrival rate, because
                      correcting toward the leg's own origin — even partially,
                      even when it stalls — starts the leg closer to right.
  IF THE SWAP HELPED: "bot" wins, because the bot can actually reach that pose
                      and alignment converges instead of grinding.
  IF NEITHER:         no difference, and the 3/3-this-morning vs 4/20-tonight
                      swing is environmental, which is its own finding.

METRIC: arrival at bar_pool_room, verified by the localiser. ONE NODE, not a
whole route — 20% of attempts could not reach it tonight, so it is the
bottleneck, and a single leg per trial makes trials ~3x cheaper than full-route
depth. A binary outcome is fine HERE (unlike whole-route depth, where a
simulated per-leg metric was measurably worse) because it is the quantity that
is actually failing.
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
_SHIPPED = {"REFERENCE_POSE": _gw_shipped.REFERENCE_POSE}

TARGET = "bar_pool_room"
TRIALS = 10
TRIAL_TIMEOUT = 200
ARMS = [("bot", "bot"), ("human", "human")]
OUT = os.path.dirname(os.path.abspath(__file__))
res = {"target": TARGET, "trials_per_arm": TRIALS, "runs": []}


# _quiet, NOT the bare lambda. Silencing the RESET is defensible — reset noise
# is not the measurement — but writing `log=lambda *a: None` here puts the exact
# literal that means "bug" everywhere else in this project one line above the
# measurement call, which is how it kept getting copied onto the measurement.
def _quiet(*a, **k):
    pass


def log(m):
    print(m, flush=True)


def save():
    _harness.save_result(os.path.join(OUT, "ab_reference_pose.json"), res)


def one(arm):
    """Reset, walk to TARGET, report whether the localiser VERIFIES it."""
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    # _harness.alive, not a local copy. This file carried its own byte-identical
    # stream_alive with the same 0.35 gate; one definition is one place to be
    # wrong. The AFTER-the-trial check is not here at all -- run_trial does it
    # once, for every harness, which is the whole reason that module exists.
    if not _harness.alive():
        raise RuntimeError("stream not updating — refusing to record")
    gw.REFERENCE_POSE = arm
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet)
    time.sleep(1.2)
    gw.follow(m, gw.SPAWN, TARGET, log=log)
    got, detail = gw.locate(m, log=log)
    log(f"    here: {got!r} ({detail})")
    return got == TARGET


def main():
    log(f"arrival at {TARGET}, {TRIALS} interleaved trials per arm\n")
    for t in range(TRIALS):
        for name, _value in ARMS:
            # THE TIMEOUT IS ENFORCED FROM OUTSIDE THE PROCESS.
            #
            # This loop used to arm signal.alarm(TRIAL_TIMEOUT). Python can only
            # deliver a signal BETWEEN bytecode instructions, so an alarm cannot
            # fire while the process is blocked inside a C call -- which every
            # screen capture is. Measured (CLAUDE.md 10.14): a 590s trial sailed
            # straight past a 260s alarm, the run produced nothing, and the
            # ceiling LOOKED like it was working. That is 10.1's whole family --
            # the code did nothing and doing nothing was indistinguishable from
            # working. _harness.run_trial re-invokes this script as a SUBPROCESS
            # and kills it from the parent, which a blocked child cannot ignore.
            #
            # THE ARM TRAVELS AS ITS NAME, NOT ITS VALUE. argv carries strings;
            # the child imports this same module and looks the value up in ARMS.
            # Uniform across all four migrated harnesses, one of which arms a
            # dict that could never have gone through argv at all.
            #
            # THE POST-TRIAL STREAM CHECK IS GONE FROM HERE, not moved:
            # run_trial does it once, inside, for every harness (10.6 -- a
            # console that falls asleep mid-trial must record INVALID, never a
            # failure). A crash inside the trial is louder than before too: the
            # child's traceback is forwarded on stderr instead of being
            # flattened into one `type: message` line.
            r, secs = _harness.run_trial(__file__, name, TRIAL_TIMEOUT, log=log)
            if r is None:
                log(f"  [{name}] trial {t+1}: INVALID after {secs:.0f}s "
                    f"(timeout, crash, or the stream went down) — dropped")
                ok = None
            else:
                ok = r["arrived"]
            log(f"  [{name}] trial {t+1}/{TRIALS}: "
                f"{'ARRIVED' if ok else ('dropped' if ok is None else 'missed')}")
            res["runs"].append({"arm": name, "trial": t + 1, "arrived": ok})
            save()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        # THE CHILD: resolve the arm by NAME, run exactly one trial, print one
        # JSON object as the LAST stdout line, exit. Everything the trial logs
        # goes to stdout above it and run_trial forwards it live.
        #
        # THE EXIT IS THE RESTORE. gw.REFERENCE_POSE is set in THIS process and
        # dies with it, so no cleanup can reinstate a stale default -- the bug
        # that put an arm into four earlier harnesses.
        by_name = dict(ARMS)
        if sys.argv[2] not in by_name:
            raise SystemExit(f"unknown arm {sys.argv[2]!r}; "
                             f"known: {sorted(by_name)}")
        print(json.dumps({"arm": sys.argv[2],
                          "arrived": bool(one(by_name[sys.argv[2]]))}),
              flush=True)
        sys.exit(0)
    try:
        main()
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
            import graph_walk as gw
            gw.REFERENCE_POSE = _SHIPPED["REFERENCE_POSE"]
        except Exception:
            pass
        save()
    print("\n--- ARRIVAL RATE ---")
    for name, _ in ARMS:
        v = [r["arrived"] for r in res["runs"]
             if r["arm"] == name and r["arrived"] is not None]
        if v:
            print(f"  {name:6} {sum(v)}/{len(v)} = {100*sum(v)/len(v):.0f}%")
        else:
            print(f"  {name:6} no valid trials")
