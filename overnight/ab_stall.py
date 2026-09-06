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
import signal
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
_SHIPPED = {"STALL_CHANGE": _gw_shipped.STALL_CHANGE}

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


class _T(Exception):
    pass


def _alarm(s, f):
    raise _T()


def stream_alive(gap=1.0):
    import compass
    import numpy as np
    a = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    time.sleep(gap)
    b = np.asarray(compass.fast_capture().convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean()) > 0.35


def one(arm):
    """Reset, walk to TARGET, report whether the localiser VERIFIES it."""
    import graph_walk as gw
    import reset_env
    import worldmap as wm

    if not stream_alive():
        raise RuntimeError("stream not updating — refusing to record")
    gw.STALL_CHANGE = arm
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
        for name, arm in ARMS:
            signal.signal(signal.SIGALRM, _alarm)
            signal.alarm(TRIAL_TIMEOUT)
            try:
                ok = one(arm)
            except _T:
                log(f"  [{name}] trial {t+1}: exceeded {TRIAL_TIMEOUT}s — dropped")
                ok = None
            except Exception as e:
                log(f"  [{name}] trial {t+1}: {type(e).__name__}: {e}")
                ok = None
            finally:
                signal.alarm(0)
            if ok is not None and not stream_alive():
                log("    stream died during the trial — discarding")
                ok = None
            log(f"  [{name}] trial {t+1}/{TRIALS}: "
                f"{'ARRIVED' if ok else ('dropped' if ok is None else 'missed')}")
            res["runs"].append({"arm": name, "trial": t + 1, "arrived": ok})
            save()


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
            import graph_walk as gw
            gw.STALL_CHANGE = _SHIPPED["STALL_CHANGE"]
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
