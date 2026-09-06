"""What does "the push moved me" actually look like? Measure both populations.

CLAUDE.md 10.4: a threshold must sit BETWEEN two measured populations, never
inside one. And section 10.4 already records that SCENE CHANGE fails this test
for exactly this question -- STALL_CHANGE cuts through a unimodal 3.1-7.9, so
frame delta cannot tell a blocked push from a walking one.

So this measures the null directly. At each heading it does the SAME capture
pair twice: once with no push at all, and once with a real push. Anything that
separates those two populations is a usable blocked/free signal. Anything that
does not, is not -- however reasonable it sounds.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import _harness
import analog_replay as ar
import compass
import places
import reset_env
import slow_traverse as st

N_DIR = int(sys.argv[1]) if len(sys.argv) > 1 else 6
PROBE_SEC, PROBE_SPEED = 0.45, 0.35


def cap():
    return compass.fast_capture()


def delta(a, b):
    a = np.asarray(a.convert("L"), float); b = np.asarray(b.convert("L"), float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean())


def inliers(a, b):
    import cv2
    (k1, d1), (k2, d2) = places.keypoints(a), places.keypoints(b)
    if d1 is None or d2 is None or len(d1) < 8 or len(d2) < 8:
        return -1
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    m = bf.match(d1, d2)
    if len(m) < 8:
        return -1
    p1 = np.float32([k1[x.queryIdx].pt for x in m]).reshape(-1, 1, 2)
    p2 = np.float32([k2[x.trainIdx].pt for x in m]).reshape(-1, 1, 2)
    _, mask = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC,
                                          ransacReprojThreshold=6.0)
    return -1 if mask is None else int(mask.sum())


def measure(do_push):
    a = cap()
    if do_push:
        ar.send([f"left_y {int(-PROBE_SPEED*32767)} {int(PROBE_SEC*1000)}"])
    time.sleep(PROBE_SEC + 0.55)
    ar.send(["clear"])
    b = cap()
    return delta(a, b), inliers(a, b)


def main():
    if os.environ.get("BASEBALL_TEST_RUN"):
        raise SystemExit("refusing to drive the console under BASEBALL_TEST_RUN")
    ar.open_stream()
    reset_env.reset_environment(log=lambda *a: None,
                               progress_file="progress_testing.json")
    time.sleep(1.2)
    base = compass.read_bearing(cap())
    print(f"spawn bearing {base}\n")
    print(f"{'heading':>8} {'NULL delta':>11} {'NULL inl':>9} | "
          f"{'PUSH delta':>11} {'PUSH inl':>9}")
    rows = []
    for k in range(N_DIR):
        want = (base + k * (360 / N_DIR)) % 360
        st.turn_to(want, lambda: compass.read_bearing(cap()), cap,
                   log=lambda *a: None, tolerance=6.0)
        nd, ni = measure(False)
        pd, pi = measure(True)
        # walk back, so every heading is probed from the SAME spot
        ar.send([f"left_y {int(PROBE_SPEED*32767)} {int(PROBE_SEC*1000)}"])
        time.sleep(PROBE_SEC + 0.55); ar.send(["clear"])
        rows.append({"heading": want, "null_delta": nd, "null_inl": ni,
                     "push_delta": pd, "push_inl": pi})
        print(f"{want:8.1f} {nd:11.2f} {ni:9} | {pd:11.2f} {pi:9}", flush=True)

    print("\n--- CAN EITHER SIGNAL SEPARATE THEM? ---")
    for name, a, b in (("frame delta", [r["null_delta"] for r in rows],
                        [r["push_delta"] for r in rows]),
                       ("ORB inliers", [r["null_inl"] for r in rows],
                        [r["push_inl"] for r in rows])):
        a = [x for x in a if x >= 0]; b = [x for x in b if x >= 0]
        if not a or not b:
            print(f"  {name:12} not enough valid samples"); continue
        gap = min(a) - max(b) if min(a) > max(b) else max(a) - min(b)
        sep = (min(a) > max(b)) or (min(b) > max(a))
        print(f"  {name:12} null [{min(a):.0f}..{max(a):.0f}]  "
              f"push [{min(b):.0f}..{max(b):.0f}]   "
              f"{'SEPARATED' if sep else 'OVERLAP — unusable as a gate'}")
    _harness.save_result(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "probe_calib.json"), rows)


main()
