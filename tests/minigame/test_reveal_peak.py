"""patch65: the reveal is read at its PEAK, and the deal threshold is a call-time knob.
Pins the LIVE measurements of 2026-09-08 as literals (10.11).
"""
import os, sys, time
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
fails = []
def check(c, m): (print("PASS", m) if c else (fails.append(m), print("FAIL", m)))

import reveal_watch as rw

# --- the constant, and the two measured populations it sits between ---------------
LONGEST_IN_EPISODE_DIP = 0.41      # measured, the datum CLOSE_GAP rests on
check(rw.PEAK_SETTLE_SEC == 0.5, "PEAK_SETTLE_SEC is 0.5")
check(LONGEST_IN_EPISODE_DIP < rw.PEAK_SETTLE_SEC < rw.CLOSE_GAP,
      "the settle sits between the longest in-episode dip (0.41s) and the close gap (1.0s)")

# --- the peak rule, on a scripted rise, with a synthetic clock ---------------------
class Clock:
    def __init__(self): self.t = 1000.0
    def time(self): return self.t
    def advance(self, dt): self.t += dt

def make(pairs, threshold=0.065):
    """A watcher driven by hand: read_frame pops (frame, score); score reads it.
    The thread is never started -- _tick is called directly."""
    it = iter(pairs)
    box = {"cur": None}
    def read_frame():
        box["cur"] = next(it, None)
        return box["cur"]
    return rw.RevealWatcher(read_frame=read_frame, score=lambda f: f[1], threshold=threshold)

# The live shape: a rise to a peak, then a decay, all above the threshold.
SCORES = [0.07, 0.09, 0.13, 0.166, 0.15, 0.14, 0.13]
clock = Clock()
w = make([(f"f{i}", s) for i, s in enumerate(SCORES)])
for _ in SCORES:
    w._tick(now=clock.time()); clock.advance(0.05)
open_ep = w._first_after(0.0)
check(open_ep is not None, "an episode is visible after the rise")
check(open_ep is not None and open_ep.peak == 0.166,
      f"the episode's peak is the MAXIMUM, not the first frame (peak={getattr(open_ep, 'peak', None)})")
check(open_ep is not None and open_ep.frame[0] == "f3",
      f"...and the kept frame is the peak's frame (got {getattr(open_ep, 'frame', [None])[0]})")

# episode_after must wait for the settle rather than hand over the first frame.
import types
real_time = rw.time
class FakeTime:
    def __init__(self, c): self.c = c
    def time(self): return self.c.time()
    def sleep(self, s): self.c.advance(s)
class Waiter:
    def __init__(self, c, w): self.c, self.w = c, w
    def wait(self, s):
        self.c.advance(s)
        self.w._tick(now=self.c.time())      # the thread's job, done by the waiter
        return False
    def is_set(self): return False
    def set(self): pass
try:
    c2 = Clock(); rw.time = FakeTime(c2)
    # One frame at 0.07, then a rise to 0.14 over the next ticks, then flat.
    w2 = make([("a", 0.07)] + [("b", 0.10), ("c", 0.14)] + [(f"d{i}", 0.12) for i in range(60)])
    w2._thread = types.SimpleNamespace(is_alive=lambda: True, start=lambda: None, join=lambda *a: None)
    w2._stop = Waiter(c2, w2)
    w2._tick(now=c2.time())                  # the first frame exists before we ask
    t0 = c2.time()
    ep = w2.episode_after(0.0, timeout=5.0)
    waited = c2.time() - t0
    check(ep is not None, "episode_after returns an episode")
    check(ep is not None and ep.peak == 0.14,
          f"...at the settled PEAK, not the first frame (got {getattr(ep, 'peak', None)}, first was 0.07)")
    check(waited >= rw.PEAK_SETTLE_SEC,
          f"...having waited out the settle ({waited:.2f}s >= {rw.PEAK_SETTLE_SEC}s)")
    check(waited < 5.0, f"...and it did NOT wait out the whole budget ({waited:.2f}s of 5.0s)")
finally:
    rw.time = real_time

# The live populations, as literals: what the first frame gave vs what the peak gave.
FIRST_FRAME_READS = [0.066, 0.067, 0.072, 0.085, 0.094, 0.094, 0.096, 0.096]
EPISODE_PEAKS = [0.077, 0.104, 0.111, 0.116, 0.129, 0.134, 0.135, 0.136, 0.138, 0.153, 0.158, 0.166]
check(max(FIRST_FRAME_READS) < 0.10 <= min(p for p in EPISODE_PEAKS if p > 0.10),
      "the live first-frame reads (max 0.096) sit below the bulk of the peaks")

# --- the deal knob ----------------------------------------------------------------
import orchestrator as o
check(o.hand_deal_threshold({}) == 15.0, "the deal threshold defaults to the measured 15.0 with the env unset")
check(o.hand_deal_threshold({"BASEBALL_DEAL_THRESHOLD": "12"}) == 12.0, "the env overrides it")
for bad in ("nope", "0", "-3", "999"):
    try:
        o.hand_deal_threshold({"BASEBALL_DEAL_THRESHOLD": bad})
        fails.append(f"a bad threshold {bad!r} was accepted"); print("FAIL", f"bad threshold {bad!r} accepted")
    except ValueError:
        print("PASS", f"a bad threshold {bad!r} is refused, not silently defaulted")
src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("th = hand_deal_threshold()" in src, "wait_for_hand_deal reads the knob at CALL time")
check("biggest delta" in src, "both [deal] lines print the threshold in force and the biggest delta")
check(o.DEAL_HEARTBEAT_SEC == 5.0 and "waiting {_now - start:.0f}s of" in src,
      "the wait prints a heartbeat, so waiting can never be mistaken for hung")
# and it must actually fire: drive a 12 s wait with no edge and count the beats
import io, contextlib
_c = Clock()
class _FT:
    def time(self): return _c.time()
    def sleep(self, s): _c.advance(s)
_rt = o.time
_grabs = {"n": 0}
try:
    o.time = _FT()
    o._grab_settle_regions = lambda names: (_grabs.__setitem__("n", _grabs["n"] + 1), {n: None for n in names})[1]
    o._mean_abs_delta = lambda a, b: 3.0          # alive, but nowhere near 25
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        o.wait_for_hand_deal(max_wait=12.0, poll_interval=0.15)
    beats = [l for l in buf.getvalue().splitlines() if "[deal] waiting" in l]
    check(len(beats) >= 2, f"a 12s wait with no edge printed {len(beats)} heartbeats")
    check(any("biggest delta 3.0" in l for l in beats), "the heartbeat reports the biggest delta seen so far")
finally:
    o.time = _rt
check(src.count("th = hand_deal_threshold()") == 2, "both the live gate and the replay function read the knob")
check(src.count("if d >= th:") == 1, "the poll compares against the call-time value, not the constant")
check("hand_deal_threshold() if threshold is None" in src,
      "hand_deal_seen resolves the SAME knob as the live gate (two tables that must agree)")
os.environ["BASEBALL_DEAL_THRESHOLD"] = "12"
try:
    check(o.hand_deal_seen([13.0]) is True and o.hand_deal_seen([11.0]) is False,
          "a swept threshold moves the pure replay function too")
finally:
    os.environ.pop("BASEBALL_DEAL_THRESHOLD", None)

# --- patch66: the gate measures distance from the BASELINE ------------------------
NO_DEAL = [4.1, 5.5, 6.8, 9.3, 9.3, 10.1, 11.5]        # measured, n=7
DEAL = [20.0, 21.6, 29.1, 29.4, 29.8, 31.9, 31.9, 32.0, 34.3, 34.6, 34.9, 35.9,
        36.2, 37.2, 37.5, 39.9, 40.1, 40.6, 41.2, 46.8, 48.8, 49.1, 50.1]   # n=23
check(o.HAND_DEAL_THRESHOLD == 15.0, "HAND_DEAL_THRESHOLD is the measured 15.0, now a distance from the baseline")
check(max(NO_DEAL) < o.HAND_DEAL_THRESHOLD < min(DEAL),
      f"it sits BETWEEN the two measured populations ({max(NO_DEAL)} .. {min(DEAL)})")
check(o.POST_PLAY_DEAL_MAX_WAIT == 20.0, "the cap is 20.0")
check(o.POST_PLAY_DEAL_MAX_WAIT > 15.0,
      "...which clears the slowest real deal measured (15.0s)")
check(o.hand_deal_threshold({}) == 15.0, "the knob now defaults to the baseline threshold")
check(o.HAND_DEAL_THRESHOLD == 15.0, "there is ONE deal constant and it is 15.0")
_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("_mean_abs_delta(baseline, cur)" in _src, "the poll compares against the BASELINE")
check("_mean_abs_delta(prev, cur)" not in _src, "...and no longer against the previous sample")
check(not any(l.strip() == "prev = cur" for l in _src.splitlines()),
      "the previous-sample carry is gone (matched as a whole line, not the substring that also hits `prev = current`)")

# It must SEE a gradual deal the rising edge misses: 40 steps of 0.8 each.
_rt = o.time
class _C:
    def __init__(s): s.t = 0.0
    def time(s): return s.t
    def sleep(s, d): s.t += d
try:
    _c = _C(); o.time = _c
    # Same note as test_post_play_timing: satisfy the stable-hand half so these checks
    # keep measuring the EDGE rule. test_readable_hand_gate.py owns the other half.
    o._hand_signature = lambda img: "settled"
    o.crop_gameplay_regions = lambda img: [("hand", object())]
    o._fast_grab = lambda: object()
    calls = {"n": 0}
    o._grab_settle_regions = lambda names: (calls.__setitem__("n", calls["n"] + 1), {n: None for n in names})[1]
    # distance from the baseline grows 0.8 per poll; no single STEP is ever above 0.8
    o._mean_abs_delta = lambda a, b: 0.8 * calls["n"]
    got = o.wait_for_hand_deal(max_wait=20.0, poll_interval=0.15)
    check(got is True, "a GRADUAL deal (0.8 per poll, never a big step) is now detected")
    check(_c.t < 20.0, f"...and detected before the cap ({_c.t:.1f}s)")
    _c2 = _C(); o.time = _c2; calls["n"] = 0
    o._mean_abs_delta = lambda a, b: 9.0        # a no-deal window: sits in the 4.1-11.5 band
    check(o.wait_for_hand_deal(max_wait=20.0, poll_interval=0.15) is False,
          "a no-deal window (statistic 9.0, inside the measured no-deal band) still times out")
finally:
    o.time = _rt

# --- patch67: the baseline is taken AT THE PLAY -----------------------------------
# Measured over 28 recorded plays: how far the hand had ALREADY moved from its
# at-the-play state by the moment the gate began. The eight that timed out are the
# subset; against a threshold of 15.0 every one of them clears when measured from the
# play, and none of them cleared when measured from the gate's start.
MOVED_BEFORE_GATE_ON_TIMEOUTS = [13.4, 19.7, 20.1, 21.9, 27.8, 29.6, 53.5, 60.0]
FROM_PLAY_ON_TIMEOUTS = [15.5, 23.0, 23.9, 26.8, 29.6, 30.5, 77.4, 82.0]
check(min(FROM_PLAY_ON_TIMEOUTS) >= o.HAND_DEAL_THRESHOLD,
      "measured from the PLAY, all 8 timed-out turns clear the 15.0 threshold")
check(sum(1 for x in MOVED_BEFORE_GATE_ON_TIMEOUTS if x >= o.HAND_DEAL_THRESHOLD) == 7,
      "7 of those 8 had already passed the threshold BEFORE the gate opened -- the deal was over")

import inspect
check("baseline=None" in inspect.signature(o.wait_for_hand_deal).__str__() or
      o.wait_for_hand_deal.__defaults__ is not None,
      "wait_for_hand_deal takes a baseline")
_src2 = open(os.path.join(_ROOT, "orchestrator.py")).read()


def _in_code(needle):
    """True only if `needle` appears OUTSIDE a comment or a docstring line.

    A bare substring cannot tell a call from prose that quotes one (CLAUDE.md
    10.10b). Both needles below occur TWICE in orchestrator.py: once inside a
    docstring describing the wiring and once as the real call. Deleting the real
    call left the check green, because the docstring still supplied the needle --
    the same shape as the preflight guard that was pinned by a substring its own
    comment also provided.
    """
    for line in _src2.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", '"', "'")):
            continue
        if needle in line.split("#", 1)[0]:
            return True
    return False


check(_in_code("wait_for_hand_deal(baseline=pop_hand_baseline())"),
      "the turn loop passes the play-time baseline (as CODE, not as prose)")
check(_in_code("stash_hand_baseline(_grab_settle_regions"),
      "...which it stashed beside the reveal mark (as CODE, not as prose)")
o.stash_hand_baseline("X")
check(o.pop_hand_baseline() == "X", "the stash round-trips")
check(o.pop_hand_baseline() is None, "...and a second pop yields None, so no turn inherits the last one's hand")
# SCOPED TO play_one_turn, NOT THE WHOLE FILE. These were `_src2.index(...)` over
# orchestrator.py, and .index() returns the FIRST match: when spend_and_play landed
# above play_one_turn carrying the same select_and_play(...) call, the ordering check
# started comparing a line in a DIFFERENT function and failed on correct code. That is
# CLAUDE.md 10.10b -- a substring search cannot tell two occurrences apart, so anchor
# it on the function this rule is actually about.
_pot = inspect.getsource(o.play_one_turn)
_i_base = _pot.index("stash_hand_baseline(_grab_settle_regions")
_i_play = _pot.index("select_and_play(player_idx, tactics_idx, look=")
check(_i_base < _i_play, "the baseline is captured BEFORE the commit press, not after")

# A GIVEN baseline must be used -- and no capture taken at entry.
_rt = o.time
class _C2:
    def __init__(s): s.t = 0.0
    def time(s): return s.t
    def sleep(s, d): s.t += d
try:
    o.time = _C2()
    grabs = {"n": 0}
    o._grab_settle_regions = lambda names: (grabs.__setitem__("n", grabs["n"] + 1), {n: "LIVE" for n in names})[1]
    seen = {}
    def _mad(a, b):
        seen.setdefault("base", a)
        return 99.0
    o._mean_abs_delta = _mad
    o.wait_for_hand_deal(max_wait=5.0, poll_interval=0.15, baseline="GIVEN")
    check(seen.get("base") == "GIVEN", f"the GIVEN baseline is what the poll compares against (got {seen.get('base')!r})")
    before = grabs["n"]
    o.time = _C2(); seen.clear(); grabs["n"] = 0
    o.wait_for_hand_deal(max_wait=5.0, poll_interval=0.15)
    check(seen.get("base") == "LIVE", "with no baseline given it still captures its own, as before")
finally:
    o.time = _rt

if fails:
    print(f"\n{len(fails)} FAILED"); sys.exit(1)
print("\nall green")
