"""Where do the seconds of a ROUTED trial actually go?

WHAT THIS FILE USED TO MEASURE, AND WHY IT WAS THE WRONG THING (OPEN-8).

Three defects, all of which made its output look like a route profile when it
was not one:

1. IT WRAPPED FUNCTIONS A LEG NEVER CALLS. It timed `walk_steps.walk_forward`
   and `walk_steps.turn_to`. Legs go through `slow_traverse.walk_leg` and
   `slow_traverse.turn_to`. So leg walking -- the thing the profile existed to
   size -- appeared NOWHERE, which is why the old profile.json reads
   "walk_forward: 1 call". Its "turn_to: 6 calls" was
   `_look_around_for_a_node`'s five bearings plus the turn back, not leg turning.

2. IT PROFILED TWO LEGS, NOT THE ROUTE. `reset` plus
   `go_to_node_verified("portrait_room")` is office_corridor -> office_door ->
   portrait_room. CLAUDE.md section 8(a) reports the route
   portrait_room -> bar_pool_room -> bar_jukebox at 338s a trial, and the two
   numbers were being read as if they described the same thing. They do not,
   and 85.6s was quoted as a route trial for days.

3. THE ROWS NESTED AND WERE SUMMED ANYWAY. `turn_to` calls `read_bearing` calls
   `fast_capture`, so adding those rows counts the same microseconds three
   times, and the leftover was reported as "unaccounted" -- 65% of the run.
   That residual was the ticket's whole question, and it was an artefact.

WHAT IT MEASURES NOW. The route from section 8(a), through `follow_verified`,
which is what `consecutive_arrivals` uses to score the requirement. Every timer
records INCLUSIVE and EXCLUSIVE time: exclusive subtracts whatever was spent
inside other wrapped functions, so the exclusive column SUMS to real elapsed
time and the residual is a real residual. Read the exclusive column; the
inclusive one is there because "read_bearing costs 18s including its captures"
is also worth knowing.

The log is written to a file rather than thrown away. Passing
`log=lambda *a: None` is the first entry in CLAUDE.md's catalogue of defects,
and the previous version of this file did exactly that.

NOT SAFE TO RUN OFFLINE -- it drives the console. Do not run it while any other
console work or heavy sweep is in flight (CLAUDE.md 10.13).
"""
import collections
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

OUT = os.path.dirname(os.path.abspath(__file__))

# CLAUDE.md section 8(a): the route whose 338s/trial and 6/10 arrival every
# other number here is compared against. Profiling anything else produces a
# figure that will be quoted as if it were this one.
ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]

# name -> [calls, inclusive_sec, exclusive_sec]
STATS = collections.defaultdict(lambda: [0, 0.0, 0.0])
# One accumulator per active wrapped frame, holding time spent in its children.
_FRAMES = []


def wrap(mod, name, label):
    """Time `mod.name`, recording inclusive AND exclusive seconds.

    EXCLUSIVE IS THE COLUMN THAT ADDS UP. These functions nest -- turn_to calls
    read_bearing calls fast_capture -- so summing inclusive times counts the
    same microseconds once per level and leaves a residual that is an artefact
    of the arithmetic rather than a component of the run. That artefact was
    reported as "65% unaccounted" and became the open question this file exists
    to answer.
    """
    real = getattr(mod, name)
    if getattr(real, "_profiled", False):        # never double-wrap
        return real

    def timed(*a, **k):
        t0 = time.perf_counter()
        _FRAMES.append(0.0)
        try:
            return real(*a, **k)
        finally:
            elapsed = time.perf_counter() - t0
            children = _FRAMES.pop()
            s = STATS[label]
            s[0] += 1
            s[1] += elapsed
            s[2] += elapsed - children
            if _FRAMES:
                _FRAMES[-1] += elapsed

    timed._profiled = True
    setattr(mod, name, timed)
    return real


if __name__ == "__main__":
    import compass, places, graph_walk as gw, worldmap as wm
    import slow_traverse as st
    import reset_env, analog_replay as ar

    # THE FUNCTIONS A LEG ACTUALLY CALLS come first. slow_traverse is the leg
    # executor; walk_steps is not on the leg path at all.
    wrap(st, "walk_leg", "leg: walk_leg (stick + settle)")
    wrap(st, "turn_to", "leg: turn_to (incl compass reads)")
    wrap(compass, "read_bearing", "read_bearing")
    wrap(compass, "fast_capture", "capture")
    wrap(places, "identify", "identify")
    wrap(places, "keypoints", "keypoints")
    wrap(reset_env, "reset_environment", "reset")

    # Optional: present on most builds, and each is a documented suspect for
    # the residual. Wrapped defensively so a rename cannot stop the profile
    # running -- but reported loudly, because a silently missing row would look
    # exactly like a component that costs nothing.
    missing = []
    for modname, fname, label in (
            ("pose", "align_lateral", "pose: align_lateral"),
            ("table_prompt", "at_table", "table_prompt: at_table"),
            ("graph_walk", "recover_to_node", "recovery fan"),
            ("graph_walk", "_look_around_for_a_node", "relocalise sweep"),
    ):
        try:
            wrap(__import__(modname), fname, label)
        except (ImportError, AttributeError) as e:
            missing.append(f"{modname}.{fname} ({type(e).__name__})")
    if missing:
        print("  NOT PROFILED (could not wrap): " + ", ".join(missing))
        print("  Those components will be invisible in the table below and "
              "will show up inside 'unattributed'. Fix before reading it.")

    logpath = os.path.join(OUT, "profile_trial.log")
    logfh = open(logpath, "w")

    def log(msg):
        logfh.write(f"{msg}\n")
        logfh.flush()

    m = wm.WorldMap.load()
    t0 = time.perf_counter()
    try:
        reset_env.reset_environment(log=log)
        time.sleep(1.2)
        # start_hint: the reset just landed on SPAWN, which locate() is designed
        # never to name. Without it every trial pays ~24s for a sweep and a
        # second reset (26 of 26 archived trials did).
        ok, reached = gw.follow_verified(m, ROUTE, log=log, attempts=3,
                                         start_hint=gw.SPAWN)
    finally:
        try:
            ar.send(["clear"])
        except Exception:
            pass
        logfh.close()
    total = time.perf_counter() - t0

    rows = sorted(STATS.items(), key=lambda kv: -kv[1][2])
    accounted = sum(v[2] for v in STATS.values())
    out = {"route": ROUTE,
           "total_sec": round(total, 1),
           "arrived": bool(ok),
           "nodes_verified": len(reached),
           "unattributed_sec": round(total - accounted, 1),
           "not_profiled": missing,
           "log": logpath,
           "components": {k: {"calls": v[0],
                              "inclusive_sec": round(v[1], 2),
                              "exclusive_sec": round(v[2], 2)}
                          for k, v in rows}}
    _harness.save_result(os.path.join(OUT, "profile.json"), out)

    print(f"\n--- ROUTE PROFILE: {' -> '.join(ROUTE)} ---")
    print(f"    {total:.1f}s total, arrived={ok}, "
          f"{len(reached)}/{len(ROUTE)} nodes verified\n")
    print(f"  {'component':32} {'calls':>5} {'excl':>8} {'incl':>8}   % of run")
    for k, (n, inc, exc) in rows:
        print(f"  {k:32} {n:5} {exc:7.1f}s {inc:7.1f}s   {100*exc/total:5.1f}%")
    resid = total - accounted
    print(f"  {'unattributed':32} {'':5} {resid:7.1f}s {'':8}   "
          f"{100*resid/total:5.1f}%")
    print("\n  Read the EXCLUSIVE column: these functions nest, so the "
          "inclusive\n  column deliberately double-counts and must not be "
          "summed.")
