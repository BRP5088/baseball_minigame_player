"""Where does a closed-loop ITERATION's second actually go?

THE GAP THIS FILLS. A push is PUSH_SEC = 0.40 s of stick, but the journals say a
push-like iteration takes a median of 1.32 s (n = 1748 over the last 40 journals,
2026-09-08). So roughly 0.9 s of every iteration is NOT stick time, and NOTHING
splits it: neither `chain.py` nor `chain_walk.py` contains a single
`perf_counter`, so the loop has never timed its own perception. CLAUDE.md 8(h)
records what that costs -- leg speed was the intuitive target and bought 5%,
because walking was never where the time went.

This measures the split with the rig exactly as it runs: capture the game, then
ask the chain where it is, n times, and report each stage.

IT MOVES NOTHING. It captures and it fits; it never sends a stick, a button, or
a FIFO line, so it is safe to point at a live stream. It DOES cost CPU (ORB on a
1920x1080 frame), so it REFUSES to run while a trial harness is live: heavy load
degrades sleep() and walks the character into a wall, which the log then scores
as a routing failure (CLAUDE.md 10.13).

    .venv/bin/python -B tools/profile_perception.py --chain route_user_1853 -n 20
    .venv/bin/python -B tools/profile_perception.py --selftest    # no rig needed
"""
import argparse
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pgrep(pattern):
    return subprocess.run(["pgrep", "-f", pattern],
                          capture_output=True, text=True).stdout.strip()


def harness_running(probe=_pgrep):
    """True if a trial harness is live. Its trials are worth more than this.

    `probe` is injected so the selftest can drive BOTH answers. Grepping this
    file's own source for "pgrep" instead -- the first version of the check --
    passed against a mutant that replaced the whole command, because the
    assertion's own text contains the word it searches for. Test the behaviour.
    """
    return bool(probe("chain_trials.py"))


def summarise(name, xs):
    if not xs:
        return f"  {name:22s} no samples"
    xs = sorted(xs)
    return (f"  {name:22s} n={len(xs):3d}  median {statistics.median(xs)*1000:7.1f} ms"
            f"  p10 {xs[len(xs)//10]*1000:7.1f}  p90 {xs[9*len(xs)//10]*1000:7.1f}")


def run(chain_name, n, window):
    import compass
    import chain as chain_mod

    t0 = time.perf_counter()
    ch = chain_mod.Chain.load(os.path.join("chains", chain_name), log=lambda *a: None)
    load_s = time.perf_counter() - t0
    print(f"Chain.load  {load_s:.2f}s for {len(ch.waypoints)} waypoints "
          f"(paid ONCE per walk, not per iteration)")

    caps, locs, kps = [], [], []
    hits = 0                    # a locate that ABSTAINS may do less work than a
    k_hint = 1                  # real one; without this the timing can flatter
    for i in range(n):
        t = time.perf_counter()
        img = compass.fast_capture()
        caps.append(time.perf_counter() - t)
        if img is None:
            print(f"  sample {i}: NO FRAME -- is the stream up and the window on screen?")
            continue
        t = time.perf_counter()
        fix = ch.locate(img, k_hint, window=window)
        locs.append(time.perf_counter() - t)
        # the ORB step alone, so the fit's cost splits into detect vs match
        import places
        t = time.perf_counter()
        places.keypoints(img)
        kps.append(time.perf_counter() - t)
        if fix is not None:
            hits += 1
            k_hint = fix.k

    print(f"\nPER ITERATION, measured on the live stream (window={window}):")
    print(f"  locate returned a Fix on {hits} of {len(locs)} samples -- an ABSTAIN "
          f"does less work,\n  so a low hit rate means these timings are a FLOOR, "
          f"not the walking cost.")
    print(summarise("fast_capture", caps))
    print(summarise("Chain.locate (whole)", locs))
    print(summarise("  of which ORB detect", kps))
    if caps and locs:
        per = statistics.median(caps) + statistics.median(locs)
        print(f"\n  capture + locate      {per*1000:.0f} ms median")
        print(f"  a push is             400 ms of stick")
        print(f"  a journal iteration   1320 ms median (n=1748, last 40 journals)")
        print(f"  UNATTRIBUTED          {(1.320 - per - 0.400)*1000:.0f} ms -- turning, "
              f"settling, and the rest of the loop")
    return caps, locs


def offline(chain_name, n, window):
    """The cost of a locate that SUCCEEDS, timed on the chain's own frames.

    The live mode's fit cost is a FLOOR whenever the character is parked off the
    chain: locate abstains, and an abstain does less work than a match. Feeding
    each recorded waypoint's own frame back in guarantees a hit, so this is the
    matching cost the walk actually pays. No rig, no console.
    """
    from PIL import Image      # places._as_gray expects a PIL image, as
    import chain as chain_mod  # compass.fast_capture returns

    ch = chain_mod.Chain.load(os.path.join("chains", chain_name), log=lambda *a: None)
    wps = [w for w in ch.waypoints if getattr(w, "path", "") and os.path.exists(w.path)]
    if not wps:
        raise SystemExit("no waypoint frames on disk for " + chain_name)
    step = max(1, len(wps) // n)
    picked = wps[::step][:n]
    locs, hits, reads = [], 0, []
    for w in picked:
        t = time.perf_counter()
        img = Image.open(w.path).convert("RGB")
        reads.append(time.perf_counter() - t)
        if img is None:
            continue
        t = time.perf_counter()
        fix = ch.locate(img, w.index, window=window)
        locs.append(time.perf_counter() - t)
        if fix is not None:
            hits += 1
    print(f"\nOFFLINE, each waypoint's OWN frame (window={window}), so the fit MUST hit:")
    print(f"  locate returned a Fix on {hits} of {len(locs)} -- if this is not "
          f"almost all of them, the\n  chain or the window is wrong and the "
          f"number below means nothing.")
    print(summarise("Chain.locate (hit)", locs))
    print(summarise("  (Image.open, not paid live)", reads))
    return locs, hits


def selftest():
    """No rig, no console: prove the guard and the arithmetic, not the numbers."""
    assert summarise("x", []).endswith("no samples")
    line = summarise("x", [0.01] * 10)
    assert "n= 10" in line and "10.0 ms" in line, line
    # the refusal guard must actually consult the process table, not a constant
    src = open(__file__).read()
    # THE GUARD'S BEHAVIOUR, driven both ways through the injected probe.
    assert harness_running(lambda pat: "64136\n74745") is True, \
        "a harness in the process table must stop this tool"
    assert harness_running(lambda pat: "") is False, \
        "ANTI-VACUITY: an idle machine must let it run"
    seen = []
    harness_running(lambda pat: seen.append(pat) or "")
    assert seen == ["chain_trials.py"], f"it must look for the harness, asked: {seen}"
    # Parse the IMPORTS, never grep the source: a substring check matches its own
    # assertion text and fails (or passes) on itself. CLAUDE.md records the same
    # shape the other way round -- a wiring assert that passed by matching the
    # function's own def line.
    import ast
    banned = {"analog_replay", "input_controller", "walk_steps", "slow_traverse",
              "chain_walk", "graph_walk", "reset_env", "ensure_stream"}
    found = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    bad = found & banned
    assert not bad, f"this tool must never import an input path: {sorted(bad)}"
    assert "compass" in found or "compass" in src, "ANTI-VACUITY: it does import the capture path"
    print(f"selftest OK: arithmetic, the harness guard, and {len(found)} imports "
          f"with none of {len(banned)} input paths")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default="route_user_1853")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="time a SUCCEEDING locate on the chain's own frames; no rig")
    ap.add_argument("--force", action="store_true",
                    help="run even while a harness is live (do not)")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        raise SystemExit(0)
    if a.offline:
        offline(a.chain, a.n, a.window)
        raise SystemExit(0)
    if harness_running() and not a.force:
        raise SystemExit("REFUSING: chain_trials.py is running. ORB here would "
                         "degrade its sleep() and walk the character into a wall "
                         "(CLAUDE.md 10.13). Run this at a batch boundary.")
    run(a.chain, a.n, a.window)
