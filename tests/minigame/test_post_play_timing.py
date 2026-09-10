"""patch63: the post-play deal wait -- threshold between two measured populations,
a hard floor, ON by default and read at call time. Pins LITERALS (10.11).
"""
import os, sys, time as _t
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
import orchestrator as _o

fails = []
def check(cond, msg):
    (print("PASS", msg) if cond else (fails.append(msg), print("FAIL", msg)))

# The two populations, measured 2026-09-08 (n=9 each). Literals, not the constant.
DEAD_WINDOW_MAX = 15.44
DEAL_BURST_MIN = 31.83
check(_o.HAND_DEAL_THRESHOLD == 15.0,
      "HAND_DEAL_THRESHOLD is 15.0 -- patch66 remeasured it live as a distance from the "
      "baseline, where no-deal windows reach 11.5 and real deals start at 20.0")
# RETIRED by patch66. Those two populations were of the RISING-EDGE statistic
# (sample vs previous sample), which the gate no longer uses; live it missed 11 of
# 30 windows. The populations that pin the shipped gate are in test_reveal_peak.py.
check(_o.SETTLE_THRESHOLDS["hand"] == 8.0,
      "the SETTLE gate keeps its own 8.0 -- correct once the deal has landed")
check(_o.SETTLE_THRESHOLDS["hand"] == 8.0, "SETTLE_THRESHOLDS['hand'] stays 8.0 for the settle gate")
check(not _o.hand_deal_seen([10.0]), "a dead-window delta (10.0) is NOT a deal by default")
# 20.0 IS a deal now: patch66 remeasured the gate as a distance from the baseline,
# where the no-deal band tops out at 11.5 and real deals start at 20.0.
check(_o.hand_deal_seen([20.0]), "20.0 clears the live threshold of 15.0")
check(not _o.hand_deal_seen([11.5]), "11.5, the highest no-deal window measured, does not")
check(_o.hand_deal_seen([32.0]), "a deal-burst delta (32.0) IS a deal")
check(_o.POST_PLAY_MIN_WAIT == 6.0, "POST_PLAY_MIN_WAIT is 6.0")
check(2.16 < _o.POST_PLAY_MIN_WAIT < 8.43, "the floor sits between the fastest old release (2.16) and the earliest readable hand (8.43)")
# The 21.95 s worst case came from replaying 9 turns offline against the rising-edge
# statistic. Live, over 30 gate windows, every real deal crossed the shipped
# threshold by 15.0 s, so a 20 s cap carries a third of margin and saves 15 s on
# each of the 7 turns in 30 that have no deal coming at all.
check(_o.POST_PLAY_DEAL_MAX_WAIT >= 15.0 * 1.25,
      "the cap clears the slowest deal measured LIVE (15.0 s) with 25% margin")

# ON by default, off only by the env, read at call time.
check(_o.post_play_wait_for_deal({}) is True, "deal wait is ON with the env unset")
check(_o.post_play_wait_for_deal({"BASEBALL_DEAL_WAIT": "0"}) is False, "BASEBALL_DEAL_WAIT=0 turns it off")
check(_o.post_play_wait_for_deal({"BASEBALL_DEAL_WAIT": "1"}) is True, "BASEBALL_DEAL_WAIT=1 keeps it on")
src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("if post_play_wait_for_deal():\n                    wait_for_hand_deal(baseline=pop_hand_baseline())" in src,
      "the turn loop asks post_play_wait_for_deal() at CALL time")
check("if POST_PLAY_WAIT_FOR_DEAL:\n" not in src, "the loop no longer reads the import-time constant")

# wait_for_hand_deal: the floor holds even when the edge comes early; the edge is
# still required; the stubs are really reached.
def run(deltas, max_wait=35.0):
    calls = {"grab": 0, "delta": 0}
    it = iter(deltas)
    # the gate now ALSO requires the hand SIGNATURE to repeat -- the deal has FINISHED,
    # not merely begun. That half is owned by test_readable_hand_gate.py, which drives
    # every branch of it. A constant signature satisfies it here so these checks still
    # measure the EDGE timing they were written for.
    real = (_o._grab_settle_regions, _o._mean_abs_delta, _o.time,
            _o._hand_signature, _o.crop_gameplay_regions, _o._fast_grab)
    _o._hand_signature = lambda img: "settled"
    _o.crop_gameplay_regions = lambda img: [("hand", object())]
    _o._fast_grab = lambda: object()
    clock = [1000.0]
    _o._grab_settle_regions = lambda names: (calls.__setitem__("grab", calls["grab"] + 1), {n: None for n in names})[1]
    def delta(a, b):
        calls["delta"] += 1
        return next(it, 0.0)
    _o._mean_abs_delta = delta
    _o.time = type("C", (), {"sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s)),
                             "time": staticmethod(lambda: clock[0]),
                             "strftime": staticmethod(_t.strftime)})()
    try:
        res = _o.wait_for_hand_deal(max_wait=max_wait, poll_interval=0.15)
        return res, clock[0] - 1000.0, calls
    finally:
        (_o._grab_settle_regions, _o._mean_abs_delta, _o.time,
         _o._hand_signature, _o.crop_gameplay_regions, _o._fast_grab) = real

res, elapsed, calls = run([0.0, 32.0] + [0.0] * 400)   # the edge at 0.30 s
check(res is True, "an early deal edge is still recognised")
check(elapsed >= 6.0, f"...but not released before the 6.0 s floor (released at {elapsed:.2f}s)")
check(elapsed < 7.0, f"...and released promptly once past the floor ({elapsed:.2f}s)")
check(calls["delta"] >= 2 and calls["grab"] >= 3, "the stubs were really polled")

res, elapsed, calls = run([0.0, 32.0] + [0.0] * 400)
res2, elapsed2, _ = run([14.0] * 400)                  # dead-window level only, never a deal
check(res2 is False, "dead-window deltas (14.0) never release the gate")
check(elapsed2 >= 35.0 - 0.2, f"...it falls through at the cap ({elapsed2:.1f}s)")

res3, elapsed3, _ = run([0.0] * 60 + [40.0] + [0.0] * 400)   # the edge at ~9.2 s
check(res3 is True and 9.0 <= elapsed3 <= 9.6, f"an edge past the floor releases at the edge ({elapsed3:.2f}s)")

if fails:
    print(f"\n{len(fails)} FAILED"); sys.exit(1)
print("\nall green")
