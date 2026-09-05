"""PHASE 1 STEP 3 — does align_lateral converge now the reference is reachable?

THE EXPERIMENT, stated before it runs so the result cannot be reinterpreted
afterwards:

  BEFORE (2026-09-02, human-walk reference): four corrections at bar_pool_room
  left dx at -136, -179, -156, -158. It did not move at all — the character was
  against the wall/stools, correcting toward a pose it could not stand in.

  PREDICTION IF THE GHOST-REFERENCE THEORY IS RIGHT: dx converges under
  ALIGN_TOL_PX (35px), like portrait_room did (131 -> 88 -> 46 -> 3).

  PREDICTION IF IT IS WRONG: dx stalls again around 100-180px, and the
  reference was never the problem — the character is simply blocked from
  strafing there.

EITHER OUTCOME ENDS THE EXPERIMENT. Step 4 runs only on convergence, and
nothing here tries a third idea to force a win.

Runs the SAME measurement three times, because n=1 cannot tell a fix from a
lucky pose, and every reversal on this project came from trusting a small n.
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

NODE = "bar_pool_room"
TRIALS = 3
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase1")
os.makedirs(OUT, exist_ok=True)

result = {"node": NODE, "trials": [], "started": time.strftime("%H:%M:%S")}


def log(m):
    print(m, flush=True)
    result.setdefault("log", []).append(str(m))


def save():
    _harness.save_result(os.path.join(OUT, "step3_result.json"), result)


def fingerprint():
    """Hash the modules a live run depends on.

    Phase 2 subagents MUTATE source files and restore them. A live console run
    that imported a half-mutated module would produce a measurement that looks
    real and is not. Cheaper to detect than to be fooled by.
    """
    import hashlib
    h = hashlib.sha256()
    for f in ("graph_walk.py", "slow_traverse.py", "pose.py", "walk_steps.py",
              "turn_curve.py", "places.py"):
        h.update(open(f, "rb").read())
    return h.hexdigest()[:16]


def main():
    import compass
    import graph_walk as gw
    import pose
    import walk_steps as ws
    import worldmap as wm
    from PIL import Image

    before = fingerprint()
    result["code_fingerprint"] = before
    log(f"code fingerprint: {before}")

    m = wm.WorldMap.load()
    refs = [f for f in os.listdir(f"places/{NODE}") if f.startswith("route_")]
    ref = Image.open(f"places/{NODE}/{refs[0]}")
    log(f"reference: places/{NODE}/{refs[0]}")

    for t in range(TRIALS):
        log(f"\n=== trial {t + 1}/{TRIALS} ===")
        trial = {"reached": False, "start_dx": None, "final_dx": None}
        result["trials"].append(trial)
        if not gw.go_to_node_verified(m, NODE, log=log):
            log("  could not verify the node — trial abandoned, NOT counted "
                "as a stall (a measurement from the wrong room proves nothing)")
            save()
            continue
        trial["reached"] = True

        o = pose.offset(ref, compass.fast_capture())
        trial["start_dx"] = None if o is None else round(o[0], 1)
        log(f"  starting dx: {trial['start_dx']}")

        final = pose.align_lateral(ref, compass.fast_capture,
                                   ws.walk_forward, log=log)
        trial["final_dx"] = None if final is None else round(final, 1)
        log(f"  final dx: {trial['final_dx']}")
        save()

    after = fingerprint()
    result["code_fingerprint_after"] = after
    if after != before:
        result["INVALID"] = ("source changed mid-run (Phase 2 mutation race) — "
                             "discard this measurement")
        log(f"\n  *** SOURCE CHANGED MID-RUN ({before} -> {after}). "
            f"This measurement is INVALID. ***")
    save()
    return result


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        try:
            import analog_replay as ar
            ar.send(["clear"])
        except Exception:
            pass
        save()
    print("\n--- STEP 3 RESULT ---")
    import pose
    got = [t["final_dx"] for t in result["trials"] if t.get("final_dx") is not None]
    for i, t in enumerate(result["trials"], 1):
        print(f"  trial {i}: reached={t['reached']} start={t['start_dx']} "
              f"final={t['final_dx']}")
    if not got:
        print("  NO MEASUREMENTS — inconclusive, do NOT proceed to step 4")
    elif all(g <= pose.ALIGN_TOL_PX for g in got):
        print(f"  CONVERGED (all <= {pose.ALIGN_TOL_PX}px) -> step 4 is justified")
    else:
        print(f"  STILL STALLING (worst {max(got)}px) -> the reference was NOT "
              f"the problem. STOP; do not re-record.")
