"""follow_verified must never walk a leg from an unverified pose, and the
streak metric must be a STREAK, not a rate.

Why the streak: the requirement is 25 CONSECUTIVE arrivals. A 90% success rate
with an independent failure every tenth run never produces 25 in a row, and a
mean would hide that entirely.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


ROUTE = ["a", "b", "c"]
visited = []


def fake_verified(results):
    """go_to_node_verified stub driven by a list of outcomes."""
    seq = list(results)

    def f(m, node, capture=None, read_heading=None, log=None, attempts=3,
          shots=None):
        visited.append(node)
        return seq.pop(0) if seq else False
    return f


real = gw.go_to_node_verified
try:
    # All three verify -> arrived, and every node was attempted in order.
    visited.clear()
    gw.go_to_node_verified = fake_verified([True, True, True])
    ok, reached = gw.follow_verified(None, ROUTE, capture=lambda: None,
                                     log=lambda *a: None)
    check("arrives when every node verifies", ok and reached == ROUTE)
    check("and visits them in order", visited == ROUTE)

    # Second node fails -> must STOP, not walk the third leg.
    visited.clear()
    gw.go_to_node_verified = fake_verified([True, False, True])
    ok, reached = gw.follow_verified(None, ROUTE, capture=lambda: None,
                                     log=lambda *a: None)
    check("stops at the first unverified node", not ok and reached == ["a"])
    check("NEVER walks the leg after a failure — the whole point",
          visited == ["a", "b"] and "c" not in visited)
finally:
    gw.go_to_node_verified = real

# --- the streak metric ---------------------------------------------------
real_follow = gw.follow_verified
try:
    def scripted(seq):
        s = list(seq)
        def f(m, route, capture=None, read_heading=None, log=None, attempts=3,
              shots=None):
            v = s.pop(0)
            return v, route if v else []
        return f

    # 9 successes, one failure, then 3 more: best streak is 9, NOT 12/13.
    gw.follow_verified = scripted([True] * 9 + [False] + [True] * 3)
    r = gw.consecutive_arrivals(None, ROUTE, 13, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("best_streak is the longest RUN, not the total", r["best_streak"] == 9)
    check("arrived counts every success", r["arrived"] == 12)

    # A trailing streak still counts.
    gw.follow_verified = scripted([False, True, True, True])
    r = gw.consecutive_arrivals(None, ROUTE, 4, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("a streak at the end is counted", r["best_streak"] == 3)

    # All failures -> zero, and no crash.
    gw.follow_verified = scripted([False] * 4)
    r = gw.consecutive_arrivals(None, ROUTE, 4, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("all failures give a zero streak", r["best_streak"] == 0)
finally:
    gw.follow_verified = real_follow

# A FAILED RESET IS AN INVALID TRIAL, NOT A ROUTE FAILURE. Recording it as a
# failure would break a streak the route never broke — the same "cannot see vs
# did not arrive" error that contaminated the leg-tolerance A/B.
import types

real_follow2 = gw.follow_verified
fake_reset = types.ModuleType("reset_env")
calls = {"n": 0}


def flaky_reset(log=None):
    calls["n"] += 1
    if calls["n"] == 3:                 # third trial's reset fails
        raise RuntimeError("never landed on 'Load Last Save'")


fake_reset.reset_environment = flaky_reset
saved = sys.modules.get("reset_env")
sys.modules["reset_env"] = fake_reset
real_sleep = gw.time.sleep
gw.time.sleep = lambda *a: None
try:
    def always_ok(m, route, capture=None, read_heading=None, log=None,
                  attempts=3, shots=None):
        return True, route
    gw.follow_verified = always_ok
    r = gw.consecutive_arrivals(None, ROUTE, 5, capture=lambda: None,
                                log=lambda *a: None, reset_between=True)
    check("a failed reset is recorded as INVALID, not as a failure",
          None in r["outcomes"] and False not in r["outcomes"])
    check("and it does not count as a valid trial", r["valid"] == 4)
    check("the streak survives an invalid trial rather than resetting to 0",
          r["best_streak"] == 4)
finally:
    gw.follow_verified = real_follow2
    gw.time.sleep = real_sleep
    if saved is not None:
        sys.modules["reset_env"] = saved
    else:
        sys.modules.pop("reset_env", None)

# A failure must leave a PICTURE behind. Cause B stayed undiagnosed purely
# because no run ever kept one.
import tempfile, glob as _glob
real3 = gw.go_to_node_verified
try:
    gw.go_to_node_verified = lambda m, node, capture=None, read_heading=None, \
        log=None, attempts=3, shots=None: node != "b"
    # COUNT THE TWO KINDS SEPARATELY. An arrival now also saves a control
    # frame (into shots/success/), so a bare "how many files" count conflates
    # the failure evidence with the control group and reads as a regression
    # when both are working.
    d = tempfile.mkdtemp()
    class Img:
        def save(self, path):
            open(path, "wb").write(b"x")

    def fails():
        return [f for f in _glob.glob(d + "/*.jpg") if "fail_" in os.path.basename(f)]

    def controls():
        return _glob.glob(d + "/success/*.jpg")

    ok, reached = gw.follow_verified(None, ROUTE, capture=lambda: Img(),
                                     log=lambda *a: None, shots=d)
    check("a failure saves a frame", not ok and len(fails()) == 1)
    check("and it names the node that failed",
          any("_b_" in os.path.basename(f) for f in fails()))

    gw.go_to_node_verified = lambda m, node, capture=None, read_heading=None, \
        log=None, attempts=3, shots=None: True
    before_fails = len(fails())
    gw.follow_verified(None, ROUTE, capture=lambda: Img(),
                       log=lambda *a: None, shots=d)
    check("a clean run saves no FAILURE frame", len(fails()) == before_fails)
    check("but a clean run does save controls", len(controls()) > 0)
finally:
    gw.go_to_node_verified = real3

# A run must report failures BY SIGNATURE, not just in total. Reporting only the
# overall rate averages three different failures together, which is very likely
# why seven consecutive changes all measured flat: each addressed at most one
# class while being scored against the sum.
real4 = gw.follow_verified
try:
    def one_wedged(m, route, capture=None, read_heading=None, log=None,
                   attempts=3, shots=None):
        gw._LAST_FAILURE_KINDS[:] = ["wedged"]
        return False, []
    gw.follow_verified = one_wedged
    r = gw.consecutive_arrivals(None, ROUTE, 3, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("a run reports failures by signature",
          r.get("failures_by_kind") == {"wedged": 3})

    def clean(m, route, capture=None, read_heading=None, log=None,
              attempts=3, shots=None):
        gw._LAST_FAILURE_KINDS[:] = []
        return True, route
    gw.follow_verified = clean
    r = gw.consecutive_arrivals(None, ROUTE, 3, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("a clean run reports no failure signatures",
          r.get("failures_by_kind") == {})
finally:
    gw.follow_verified = real4

# THE SAVED FRAME MUST PREDATE RECOVERY. go_to_node_verified runs a fan on a
# miss that travels ~7x the leg it rescues, so a frame captured afterwards shows
# where the FAN went. Six archived frames sat at bearing 98-106 against a leg
# commanding 2.1 — a ~100 degree offset that is the fan's signature — and a
# confident diagnosis was built on them and was wrong.
real5 = gw.go_to_node_verified
try:
    frames = []

    class Marked:
        def __init__(self, tag):
            self.tag = tag

        def save(self, path):
            frames.append(self.tag)
            open(path, "wb").write(b"x")

    state = {"phase": "before"}

    def capture():
        return Marked(state["phase"])

    def verified(m, node, capture=None, read_heading=None, log=None,
                 attempts=3, shots=None):
        state["phase"] = "after_recovery"     # the fan has now moved us
        return False

    gw.go_to_node_verified = verified
    import tempfile as _tf
    gw.follow_verified(None, ROUTE, capture=capture, log=lambda *a: None,
                       shots=_tf.mkdtemp())
    check("the saved frame is the PRE-recovery one", frames == ["before"])
    check("it is not the post-recovery view", "after_recovery" not in frames)
finally:
    gw.go_to_node_verified = real5

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
