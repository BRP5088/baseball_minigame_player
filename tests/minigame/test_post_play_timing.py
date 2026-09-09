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
check(_o.HAND_DEAL_THRESHOLD == 25.0, "HAND_DEAL_THRESHOLD is the measured 25.0")
check(DEAD_WINDOW_MAX < _o.HAND_DEAL_THRESHOLD < DEAL_BURST_MIN,
      "the deal threshold sits BETWEEN the dead window (max 15.44) and the deal burst (min 31.83)")
check(_o.SETTLE_THRESHOLDS["hand"] == 8.0, "SETTLE_THRESHOLDS['hand'] stays 8.0 for the settle gate")
check(not _o.hand_deal_seen([10.0]), "a dead-window delta (10.0) is NOT a deal by default")
check(not _o.hand_deal_seen([20.0]), "a delta inside the gap but under 25 (20.0) is NOT a deal")
check(_o.hand_deal_seen([32.0]), "a deal-burst delta (32.0) IS a deal")
check(_o.POST_PLAY_MIN_WAIT == 6.0, "POST_PLAY_MIN_WAIT is 6.0")
check(2.16 < _o.POST_PLAY_MIN_WAIT < 8.43, "the floor sits between the fastest old release (2.16) and the earliest readable hand (8.43)")
check(_o.POST_PLAY_DEAL_MAX_WAIT >= 22.0, "the cap clears the worst measured deal (21.95 s)")

# ON by default, off only by the env, read at call time.
check(_o.post_play_wait_for_deal({}) is True, "deal wait is ON with the env unset")
check(_o.post_play_wait_for_deal({"BASEBALL_DEAL_WAIT": "0"}) is False, "BASEBALL_DEAL_WAIT=0 turns it off")
check(_o.post_play_wait_for_deal({"BASEBALL_DEAL_WAIT": "1"}) is True, "BASEBALL_DEAL_WAIT=1 keeps it on")
src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("if post_play_wait_for_deal():\n                    wait_for_hand_deal()" in src,
      "the turn loop asks post_play_wait_for_deal() at CALL time")
check("if POST_PLAY_WAIT_FOR_DEAL:\n" not in src, "the loop no longer reads the import-time constant")

# wait_for_hand_deal: the floor holds even when the edge comes early; the edge is
# still required; the stubs are really reached.
def run(deltas, max_wait=35.0):
    calls = {"grab": 0, "delta": 0}
    it = iter(deltas)
    real = (_o._grab_settle_regions, _o._mean_abs_delta, _o.time)
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
        _o._grab_settle_regions, _o._mean_abs_delta, _o.time = real

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
