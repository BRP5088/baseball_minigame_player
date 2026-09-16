"""A/B: does STALL_CHANGE=2.5 beat 6.0 on arrival?

MEASURED: at 6.0 the gate fired on 5 of 20 office-leg step-7 pushes whose view
change was 3.1-7.9 — one unimodal population, so all five were FALSE POSITIVES.
Each ran the escape ladder, injecting unaccounted forward push. Runs with a
clean office leg reached bar_pool_room 14/15; runs where the gate fired reached
it 0/5 (Fisher p = 0.00039).

If that association is causal, 2.5 should raise arrival here. If it does not,
the association was confounded and the threshold change is cosmetic.

OLD DOCSTRING FOLLOWS (structure reused):

A/B: did swapping the align references to the BOT's poses hurt arrivals?

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

# THERE IS NOTHING TO RESTORE, AND THAT IS THE POINT.
#
# This file used to capture gw.STALL_CHANGE at import and put it back in a
# `finally`. The capture existed because the version before THAT hardcoded what
# the default was ON THE DAY THE SCRIPT WAS WRITTEN, so it silently rotted into
# a WRONG value: ab_leg_speed restored {} after leg 1 shipped an override of
# 3.0, and ab_stall restored 2.5 after STALL_CHANGE became 6.0. A cleanup that
# reinstates a stale default is worse than no cleanup -- it looks like tidiness
# and installs an arm.
#
# The arm is now set inside the `--one-trial` CHILD, which then exits. Process
# death is the restore: the parent never holds the flag at all, so the restore
# cannot be forgotten and cannot be written wrong. That is a second reason to
# prefer the subprocess pattern, beyond the timeout below being real.

TARGET = "bar_pool_room"
TRIALS = 10
TRIAL_TIMEOUT = 200
ARMS = [("fixed_2.5", 2.5), ("old_6.0", 6.0)]
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
    _harness.save_result(os.path.join(OUT, "ab_stall.json"), res)


def one(arm):
    """Reset, walk to TARGET, report whether the localiser VERIFIES it.

    Runs in the `--one-trial` child, so `gw.STALL_CHANGE = arm` needs no undo.
    """
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    # _harness.alive, not a local copy. This file carried its own byte-identical
    # stream_alive with the same 0.35 gate; one definition is one place to be
    # wrong. The AFTER-the-trial check is not here at all -- run_trial does it
    # once, for every harness, which is the whole reason that module exists.
    if not _harness.alive():
        raise RuntimeError("stream not updating — refusing to record")
    gw.STALL_CHANGE = arm
    m = wm.WorldMap.load()
    reset_env.reset_environment(log=_quiet)
    time.sleep(1.2)
    gw.follow(m, gw.SPAWN, TARGET, log=log)
    got, detail = gw.locate(m, log=log)
    log(f"    here: {got!r} ({detail})")
    return got == TARGET


def _one_trial(name):
    """Run ONE trial and print its result as JSON. Invoked as a subprocess.

    THE ARM ARRIVES AS ITS NAME AND IS LOOKED UP HERE. Across these harnesses an
    arm's value is a float, a dict, a None or a string, and a dict cannot travel
    through argv. The child imports this same module, so the name is the one
    encoding that works for all of them -- and a typo is a loud KeyError on the
    JSON line rather than a silently different arm.
    """
    try:
        print(json.dumps({"arrived": one(dict(ARMS)[name])}))
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
    finally:
        # Whatever is already in flight still lands, so release the stick before
        # this process dies. Nothing after the result may print a JSON line:
        # run_trial takes the LAST line starting with `{`, so a second one would
        # become the answer. (`ar.send` DOES print a warning under
        # BASEBALL_TEST_RUN — harmless, it does not start with `{`.)
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass


def main():
    log(f"arrival at {TARGET}, {TRIALS} interleaved trials per arm, "
        f"{TRIAL_TIMEOUT}s ceiling enforced out-of-process\n")
    for t in range(TRIALS):
        for name, _arm in ARMS:
            # THE CEILING IS ENFORCED FROM OUTSIDE THE PROCESS.
            #
            # This used to be an in-process SIGALRM armed to TRIAL_TIMEOUT,
            # which cannot work here: Python only delivers a signal BETWEEN
            # bytecode instructions, and a trial spends its time blocked inside
            # a screen capture. Measured (CLAUDE.md 10.14), a 590s trial sailed
            # straight past a 260s ceiling -- the run produced nothing and the
            # ceiling LOOKED like it was working, which is 10.1: the code did
            # nothing and doing nothing was indistinguishable from doing its
            # job. run_trial spawns the trial and kills it from out here, so the
            # kill is real.
            #
            # (The old call is described rather than quoted ON PURPOSE.
            # test_overnight_harness.py's ratchet greps these files for that
            # call as a bare substring, so quoting it in prose would report this
            # file as still armed -- CLAUDE.md 10b, prose that quotes code
            # creates new matches. This comment was written that way first and
            # the ratchet caught it.)
            r, secs = _harness.run_trial(__file__, name, TRIAL_TIMEOUT, log=log)
            # A trial that could not be MEASURED is INVALID, never a miss:
            # `ok is None` is the same "dropped" the alarm branch recorded.
            if r is None:
                log(f"  [{name}] trial {t+1}: no result after {secs}s "
                    f"(exceeded {TRIAL_TIMEOUT}s, crashed, or the stream died) "
                    f"— dropped")
                ok = None
            elif "error" in r:
                log(f"  [{name}] trial {t+1}: {r['error']}")
                ok = None
            else:
                ok = r["arrived"]
            log(f"  [{name}] trial {t+1}/{TRIALS}: "
                f"{'ARRIVED' if ok else ('dropped' if ok is None else 'missed')}")
            res["runs"].append({"arm": name, "trial": t + 1, "arrived": ok})
            save()


if __name__ == "__main__":
    # Child mode: one trial, one JSON line, then exit. The parent enforces the
    # timeout from out here because signal.alarm does not interrupt a trial
    # blocked inside a capture — see the note in main().
    if len(sys.argv) > 2 and sys.argv[1] == "--one-trial":
        _one_trial(sys.argv[2])
        sys.exit(0)

    try:
        main()
    finally:
        # The parent never touches gw.STALL_CHANGE now, so there is no flag to
        # put back — only the stick, in case a killed child left one deflected.
        try:
            import analog_replay as ar
            ar.send(["clear"])
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
