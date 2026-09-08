"""How long does the character take to come to rest after a push?

WHY THIS EXISTS. A closed-loop iteration is a median 1.44 s, of which 700 ms is
two hard-coded 0.35 s sleeps: `slow_traverse.SETTLE_SEC` after the push (:95)
and a bare `0.35` literal inside `turn_to`'s loop (:191), paid per turn STEP.
The stick moves for 400 ms and the whole of perception costs 59 ms. So the
settle is the largest single item in the loop and it has never been measured.

WHAT THE SETTLE IS FOR, and what it is NOT for any more. It exists so the next
frame is taken when the character has stopped. In the DEAD-RECKONING system it
also protected `walk_leg`'s own travel measurement (`change`/`best`), which fed
`STALL_CHANGE` -- CLAUDE.md refuses to shorten it for exactly that reason. THE
CLOSED LOOP DOES NOT HAVE THAT CONSUMER: `chain_walk`'s `push()` calls
`walk_leg` as a bare statement and binds its return value to nothing (grep for
`= push(` -- there are no matches). So the only surviving question is the
optical one: how soon after the stick releases is a frame good enough to fit?

WHAT IT MEASURES. Push once, then capture and fit repeatedly at increasing
delays, recording the fit's inlier count at each. Repeat from several spots so
the answer is not one pose's accident. The output is inliers against delay; if
it plateaus early, the settle above the plateau is dead time, twice an
iteration. A threshold set from that curve sits BETWEEN two measured
populations instead of being invented (CLAUDE.md 10.4).

IT MOVES THE CHARACTER, so it refuses to run while a trial harness is live and
it must never run during a batch. Run it at a boundary, from a spot where the
chain can actually fit -- otherwise every fit abstains and the curve is flat for
a reason that has nothing to do with settling.

    .venv/bin/python -B tools/settle_response.py --chain route_user_1853 --pushes 6
    .venv/bin/python -B tools/settle_response.py --selftest
"""
import argparse
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DELAYS = (0.00, 0.05, 0.10, 0.15, 0.20, 0.30, 0.45, 0.60)


def _pgrep(pattern):
    return subprocess.run(["pgrep", "-f", pattern],
                          capture_output=True, text=True).stdout.strip()


def harness_running(probe=_pgrep):
    """True if a trial harness is live. Injected so the selftest drives both."""
    return bool(probe("chain_trials.py"))


def curve(samples):
    """{delay: [inliers, ...]} -> a printable table plus the knee.

    The knee is the FIRST delay whose median is within 5% of the best median.
    Reported, never applied: this tool measures, it does not tune.
    """
    rows = []
    for d in sorted(samples):
        v = [x for x in samples[d] if x is not None]
        rows.append((d, len(v), statistics.median(v) if v else 0.0,
                     sum(1 for x in samples[d] if x is None)))
    best = max((m for _, _, m, _ in rows), default=0.0)
    knee = next((d for d, _, m, _ in rows if best and m >= 0.95 * best), None)
    return rows, best, knee


def run(chain_name, pushes, mag, sec, reset=True):
    import analog_replay as ar
    import compass
    import chain as chain_mod

    if reset:
        # START FROM THE SPAWN, ALWAYS. After a batch the character stands
        # wherever the last trial ended -- often AT the dealer's table, where
        # pushing forward walks into furniture and every fit degrades for a
        # reason that has nothing to do with settling. The spawn is
        # deterministic (bearing 87 E on every reset), so the measurement is
        # repeatable across sessions instead of being one pose's accident.
        import reset_env
        reset_env.reset_environment(log=print,
                                    progress_file="progress_testing.json")
        time.sleep(1.2)          # the world has to finish appearing

    ch = chain_mod.Chain.load(os.path.join("chains", chain_name),
                              log=lambda *a: None)
    img = compass.fast_capture()
    fix = ch.locate(img, 1, window=200) if img is not None else None
    if fix is None:
        raise SystemExit(
            "cannot fit the CURRENT frame anywhere on the chain, so every "
            "reading below would abstain for a reason that is not settling. "
            "Stand the character on the route first (a reset spawn works).")
    k = fix.k
    print(f"starting at chain waypoint {k} ({fix.inliers} inliers)")

    samples = {d: [] for d in DELAYS}
    for i in range(pushes):
        # THE PUSH IS SENT HERE, NOT THROUGH walk_leg, for one reason: walk_leg
        # sleeps SETTLE_SEC before it returns, so sampling from its return would
        # start 350 ms after the stick released and miss the entire window this
        # tool exists to measure. t0 is the instant the stick is zeroed.
        ar.send([f"left_x 0", f"left_y {ar.to_axis(-abs(mag))}",
                 "right_x 0", "right_y 0"])
        time.sleep(sec)
        ar.send(["left_x 0", "left_y 0"])
        t0 = time.perf_counter()
        for d in DELAYS:
            while time.perf_counter() - t0 < d:
                time.sleep(0.005)
            im = compass.fast_capture()
            f = ch.locate(im, k, window=3) if im is not None else None
            samples[d].append(None if f is None else f.inliers)
        last = [f for f in samples[DELAYS[-1]] if f is not None]
        if last:
            nf = ch.locate(compass.fast_capture(), k, window=3)
            if nf is not None:
                k = nf.k
        print(f"  push {i+1}/{pushes} done, now near waypoint {k}")

    rows, best, knee = curve(samples)
    import slow_traverse as st
    print(f"\nINLIERS vs DELAY MEASURED FROM THE STICK RELEASE "
          f"(the shipped settle is SETTLE_SEC={st.SETTLE_SEC}s, so every row "
          f"below that is time the loop currently spends waiting):")
    print(f"  {'delay':>7s} {'n':>4s} {'median inliers':>15s} {'abstains':>9s}")
    for d, n, m, ab in rows:
        print(f"  {d:6.2f}s {n:4d} {m:15.1f} {ab:9d}")
    print(f"\n  best median {best:.1f}; first delay within 5% of it: {knee}")
    print("  REPORTED, NOT APPLIED. Shortening a settle is a live change and "
          "belongs in an A/B scored on ARRIVAL, not on inliers alone.")
    return rows


def selftest():
    assert harness_running(lambda p: "123") is True
    assert harness_running(lambda p: "") is False
    seen = []
    harness_running(lambda p: seen.append(p) or "")
    assert seen == ["chain_trials.py"], seen
    rows, best, knee = curve({0.0: [10, 12], 0.1: [90, 100], 0.2: [96, 104]})
    assert [r[0] for r in rows] == [0.0, 0.1, 0.2]
    assert best == 100.0, best
    assert knee == 0.1, f"the knee is the FIRST delay within 5% of best: {knee}"
    r2, b2, k2 = curve({0.0: [None, None]})
    assert b2 == 0.0 and k2 is None and r2[0][3] == 2, r2
    print("selftest OK: the harness guard both ways, the knee, and the "
          "all-abstain case")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default="route_user_1853")
    ap.add_argument("--pushes", type=int, default=6)
    ap.add_argument("--mag", type=float, default=0.45)
    ap.add_argument("--sec", type=float, default=0.40)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-reset", dest="reset", action="store_false",
                    help="measure from wherever the character stands (the "
                         "result is then one pose's accident, not the spawn's)")
    a = ap.parse_args()
    if a.selftest:
        selftest(); raise SystemExit(0)
    if harness_running():
        raise SystemExit("REFUSING: chain_trials.py is running. This tool "
                         "PUSHES THE STICK; running it now would drive the "
                         "character during a live trial.")
    run(a.chain, a.pushes, a.mag, a.sec, reset=a.reset)
