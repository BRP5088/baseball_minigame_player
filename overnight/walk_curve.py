"""MEASURE how far the character actually moves per second, by stick magnitude.

Everything about speeding legs up rests on one unverified assumption: that
velocity is proportional to stick magnitude, so scaling speed x duration
preserves distance. Nobody has ever measured it.

What IS known argues for caution: the RIGHT stick is badly non-linear — 74.8
deg/s at 0.90 against 197.7 at 1.00 (turn_curve.MEASURED) — and the human's
recorded walk only ever used 0.18-0.45, so every magnitude above that is
extrapolation. LEG_SPEED_MAX was set to 0.85 by borrowing the TURNING cap,
which is a different stick and not evidence.

Measured here in the office corridor: walls on both sides, no furniture, no
NPCs, and the leg that has never failed. Displacement is measured with
pose.displacement() (RANSAC on keypoints), which reports what the CAMERA did
rather than how much the picture changed.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# APPEND, not insert: _harness lives beside this file, so overnight/ goes at
# the END of sys.path where it can only ever add names, never shadow a
# project or stdlib module.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _harness   # noqa: E402  (needs the path line above)

MAGS = [0.25, 0.35, 0.45, 0.60, 0.75, 0.85, 1.00]
PUSH_SEC = 0.40
REPEATS = 3
OUT = os.path.dirname(os.path.abspath(__file__))


def main():
    import compass, pose, walk_steps as ws
    import analog_replay as ar

    res = {"push_sec": PUSH_SEC, "samples": []}
    for mag in MAGS:
        for r in range(REPEATS):
            before = compass.fast_capture()
            ws.walk_forward(mag, PUSH_SEC)
            time.sleep(0.45)
            after = compass.fast_capture()
            d = pose.displacement(before, after)
            res["samples"].append({"mag": mag, "rep": r,
                                   "px": None if d is None else round(d, 1)})
            print(f"  mag {mag:.2f} rep {r+1}: {d}", flush=True)
            _harness.save_result(os.path.join(OUT, "walk_curve.json"), res)
            # walk back so the next sample starts from a similar place
            ar.send([f"left_y {ar.to_axis(mag)} {int(PUSH_SEC*1000)}",
                     "left_x 0 %d" % int(PUSH_SEC*1000)])
            time.sleep(PUSH_SEC + 0.5)
            ar.send(["clear"])
    return res


if __name__ == "__main__":
    try:
        r = main()
    finally:
        try:
            import analog_replay as ar; ar.send(["clear"])
        except Exception:
            pass
    print("\n--- WALK RESPONSE (px per %.2fs push) ---" % PUSH_SEC)
    import statistics, collections
    by = collections.defaultdict(list)
    for s in r["samples"]:
        if s["px"] is not None:
            by[s["mag"]].append(s["px"])
    base = None
    for m in sorted(by):
        med = statistics.median(by[m])
        if base is None:
            base = (m, med)
        lin = base[1] * m / base[0]
        print(f"  {m:.2f}  median {med:7.1f}px   linear would be {lin:7.1f}px"
              f"   ratio {med/lin if lin else 0:.2f}")
