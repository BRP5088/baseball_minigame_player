"""patch65: read the reveal at its PEAK, not at its first frame; and make the deal
threshold a knob that can be swept hand by hand without a code edit.

MEASURED LIVE, 2026-09-08 22:39-22:49 (one match, the first with patch60+63+64 on;
overnight/smoke_cycle_wrapper.log, overnight/events/cycle_20260908_2239.jsonl):

  THE REVEAL. `episode_after` returned the open episode as soon as it had one frame
  above the threshold, and that frame was ALWAYS the first of the rise -- 8 of 8
  handovers logged "0.0s long". Two populations, no overlap in practice:

      what the loop READ   0.066 0.067 0.072 0.085 0.094 0.094 0.096 0.096   (n=8)
      what the peak WAS    0.077 0.104 0.111 0.116 0.129 0.134 0.135 0.136
                           0.138 0.153 0.158 0.166                           (n=12)

  and the peak arrives after t_first at 0.17 0.23 0.34 0.39 0.46 0.51 0.62 0.63
  0.63 0.66 2.60 4.27 4.37 s -- 10 of 13 inside 0.7 s, three long tails. So no
  constant delay is right: the rule is WAIT UNTIL THE PEAK STOPS RISING.
  `PEAK_SETTLE_SEC = 0.5` is 0.5 s of no new maximum, which is 3.9x the longest
  sub-sample gap inside an episode measured for CLOSE_GAP (0.41 s in-episode dip)
  and well under the 1.0 s close gap, so a settle can never outlive the episode.
  Cost: the median turn waits peak_offset + 0.5 = ~1.1 s instead of 0.2 s, and the
  worst 4.9 s -- against a 75 s poll before patch60. The two "intended card absent
  from reveal" misfires and the one "no OPPONENT card identified" this match were
  all reads of a first frame (0.072, 0.096, 0.085) whose episode peaked at 0.116,
  0.138 and 0.166.

  THE DEAL. patch63's HAND_DEAL_THRESHOLD = 25.0 came from an OFFLINE recording at a
  0.060 s sample gap. Live at the 0.15 s poll it does not hold: released 6.0 6.1 6.2
  7.9 7.9 8.1 10.4 10.8 16.5 s, TWO timeouts of eleven, median 7.9 s against the
  study's predicted 11.5 s -- and two releases sat exactly on the 6.0 s floor, i.e.
  an edge before the deal. A gate that both fires early and misses entirely is
  CLAUDE.md 10.4's shape: the threshold is inside one population, not between two.
  NO NEW VALUE IS INVENTED HERE. The constant becomes `hand_deal_threshold()`, read
  at CALL time from BASEBALL_DEAL_THRESHOLD (10.18), so it can be swept across hands
  -- the user's own suggestion, 2026-09-08 22:47: "treat each hand as a mini reset
  to try code fixes to get the timing right" -- and every [deal] line now prints the
  threshold in force and the largest delta seen, which is the measurement that will
  settle it.

Applies to: reveal_watch.py, orchestrator.py; creates tests/minigame/test_reveal_peak.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch65.py [ROOT]
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
RW = open(os.path.join(ROOT, "reveal_watch.py")).read()
O = open(os.path.join(ROOT, "orchestrator.py")).read()
T = os.path.join(ROOT, "tests", "minigame", "test_reveal_peak.py")
assert not os.path.exists(T), T

# ---- anchors, ALL asserted before any write (10.19) ------------------------------
A1 = "CLOSE_GAP = 1.0\n"
A2 = '''        deadline = time.time() + float(timeout)
        entered_available = self.available
        while True:
            ep = self._first_after(t_mark)
            if ep is not None:
                return ep
'''
A3 = '''        Returns an episode as soon as it exists with a peak frame -- it does
        NOT wait for the episode to close. Waiting would add the close gap
        plus whatever is left of a 4-10 s animation to every turn that asks
        mid-reveal, and the peak-so-far is already past the face-down state
        that the threshold rejects. `closed` on the result says which case
        the caller got, so the live log can settle later whether waiting
        would have been worth it.
'''
B1 = "HAND_DEAL_THRESHOLD = 25.0\n"
B2 = '''        if _mean_abs_delta(prev, cur) >= HAND_DEAL_THRESHOLD:
            seen = True
'''
B3 = '''            print(f"  [deal] replacement card seen; released {time.time() - start:.1f}s after the play")
            return True
'''
B4 = '''    print(f"  [deal] no replacement card seen in {max_wait:.0f}s — "
          "reading anyway (the retry path will catch a bad read).")
'''
B6 = "    th = HAND_DEAL_THRESHOLD if threshold is None else threshold\n"
B5 = '''    start = time.time()
    prev = _grab_settle_regions(("hand",))["hand"]
    seen = False
'''
for a in (A1, A2, A3):
    assert RW.count(a) == 1, ("reveal_watch anchor", RW.count(a), a[:60])
for b in (B1, B2, B3, B4, B5, B6):
    assert O.count(b) == 1, ("orchestrator anchor", O.count(b), b[:60])
assert RW.count("PEAK_SETTLE_SEC") == 0 and O.count("hand_deal_threshold") == 0
assert O.count("BASEBALL_DEAL_THRESHOLD") == 0

# ---- reveal_watch ----------------------------------------------------------------
RW2 = RW.replace(A1, A1 + '''
# HOW LONG THE PEAK MUST STOP RISING before an OPEN episode is handed over.
# Measured live 2026-09-08 over 13 episodes of one match: the peak arrives after
# t_first at 0.17..0.66 s on ten of them and 2.60/4.27/4.37 s on three, so no fixed
# delay is right. What IS stable is that the rise ends: 0.5 s of no new maximum is
# 1.2x the longest sub-threshold dip measured INSIDE an episode (0.41 s, the datum
# CLOSE_GAP sits on) and half the 1.0 s close gap, so a settle always resolves
# before the episode itself closes. Before this rule the loop read the FIRST frame
# above the threshold on 8 of 8 turns (0.066-0.096) while the peaks were
# 0.077-0.166, and the three reveal misreads of that match were all first frames.
PEAK_SETTLE_SEC = 0.5
''', 1)
RW2 = RW2.replace(A3, '''        Returns an episode once its peak has STOPPED RISING -- no new maximum
        for PEAK_SETTLE_SEC -- or once it has closed, whichever comes first.
        It does not wait out the whole 4-10 s animation.

        WHY NOT THE FIRST FRAME. That is what this did until 2026-09-08, and
        measured live it handed over the first frame above the threshold on 8
        of 8 turns (peaks 0.066-0.096) while those same episodes went on to
        peak at 0.077-0.166 a median 0.63 s later. The three reveal misreads
        of that match -- two "intended card absent", one "no OPPONENT card
        identified" -- were all such frames: the cards mid-flip. `closed` on
        the result still says which case the caller got.
''', 1)
RW2 = RW2.replace(A2, '''        deadline = time.time() + float(timeout)
        entered_available = self.available
        # The peak-settle state: the best score seen for the episode we are
        # holding, and when it last rose. Held here rather than on the episode
        # because _first_after hands back an independent COPY each poll.
        best = None
        rose_at = None
        while True:
            ep = self._first_after(t_mark)
            if ep is not None:
                now = time.time()
                if best is None or ep.peak > best:
                    best, rose_at = ep.peak, now
                # Closed, settled, or out of budget: this is the peak.
                if ep.closed or now - rose_at >= PEAK_SETTLE_SEC or now >= deadline:
                    return ep
''', 1)

# ---- orchestrator ----------------------------------------------------------------
O2 = O.replace(B1, '''HAND_DEAL_THRESHOLD = 25.0
# ...AND IT IS A KNOB, NOT A SETTLED VALUE. 25.0 was derived offline at a 0.060 s
# sample gap; live at the 0.15 s poll (2026-09-08, n=11 turns) the gate released at
# 6.0-16.5 s with a median of 7.9 s against the study's predicted 11.5 s, twice
# exactly on the 6.0 s floor, and timed out entirely twice. Firing early AND missing
# is CLAUDE.md 10.4's signature of a threshold inside one population. Rather than
# invent a second number from the same thin evidence, the value is read at CALL time
# (10.18) so it can be swept hand by hand -- BASEBALL_DEAL_THRESHOLD=NN -- and every
# [deal] line prints the threshold in force and the largest delta the poll saw, which
# is the measurement that will settle it.
DEAL_THRESHOLD_ENV = "BASEBALL_DEAL_THRESHOLD"
# How often the wait says it is still alive. 5 s is short enough that no silence
# is ever mistaken for a hang and long enough that a 35 s wait costs 7 lines.
DEAL_HEARTBEAT_SEC = 5.0


def hand_deal_threshold(env=None):
    raw = (os.environ if env is None else env).get(DEAL_THRESHOLD_ENV)
    if raw is None:
        return HAND_DEAL_THRESHOLD
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{DEAL_THRESHOLD_ENV}={raw!r} is not a number")
    if not 0.0 < v <= 255.0:
        raise ValueError(f"{DEAL_THRESHOLD_ENV}={raw!r} is outside (0, 255]")
    return v
''', 1)
O2 = O2.replace(B5, '''    start = time.time()
    prev = _grab_settle_regions(("hand",))["hand"]
    seen = False
    th = hand_deal_threshold()
    biggest = 0.0
    last_beat = start
''', 1)
# The pure replay function and the live gate must resolve the SAME value, or a
# sweep moves one and not the other -- this project's "two tables that must agree".
O2 = O2.replace(B6, "    th = hand_deal_threshold() if threshold is None else threshold\n", 1)
O2 = O2.replace(B2, '''        d = _mean_abs_delta(prev, cur)
        biggest = max(biggest, d)
        # THE HEARTBEAT. A 35 s silence and a hung process read exactly alike --
        # the user watching the stream on 2026-09-08 could not tell them apart,
        # and CLAUDE.md 10.1 lists "a slow step and a hung step with identical
        # output" as this project's signature failure. One line every
        # DEAL_HEARTBEAT_SEC says the loop is alive, how long it has waited, and
        # how close the biggest delta has come -- which is also the number that
        # sizes the threshold.
        _now = time.time()
        if _now - last_beat >= DEAL_HEARTBEAT_SEC:
            last_beat = _now
            print(f"  [deal] waiting {_now - start:.0f}s of {max_wait:.0f}s — "
                  f"biggest delta {biggest:.1f} of the {th:g} needed")
        if d >= th:
            seen = True
''', 1)
O2 = O2.replace(B3, '''            print(f"  [deal] replacement card seen; released {time.time() - start:.1f}s "
                  f"after the play (threshold {th:g}, biggest delta {biggest:.1f})")
            return True
''', 1)
O2 = O2.replace(B4, '''    print(f"  [deal] no replacement card seen in {max_wait:.0f}s — "
          f"reading anyway (the retry path will catch a bad read). "
          f"Threshold {th:g}, biggest delta {biggest:.1f}: a biggest well UNDER the "
          f"threshold means the gate is too high for this turn.")
''', 1)

TEST = r'''"""patch65: the reveal is read at its PEAK, and the deal threshold is a call-time knob.
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
check(o.hand_deal_threshold({}) == 25.0, "the deal threshold defaults to 25.0 with the env unset")
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

if fails:
    print(f"\n{len(fails)} FAILED"); sys.exit(1)
print("\nall green")
'''

for s in (RW2, O2): ast.parse(s)
ast.parse(TEST)
assert RW2.count("PEAK_SETTLE_SEC") >= 3 and RW2.count("if ep.closed or now - rose_at >= PEAK_SETTLE_SEC") == 1
assert O2.count("def hand_deal_threshold") == 1
# TWO call sites, deliberately: the live gate and the pure replay function.
assert O2.count("th = hand_deal_threshold()") == 2
assert O2.count("    th = hand_deal_threshold()\n") == 1          # wait_for_hand_deal
assert O2.count("th = hand_deal_threshold() if threshold is None") == 1  # hand_deal_seen
assert O2.count("if d >= th:") == 1
assert O2.count("HAND_DEAL_THRESHOLD") == 3, O2.count("HAND_DEAL_THRESHOLD")
assert O2.count("hand_deal_threshold() if threshold is None") == 1
open(os.path.join(ROOT, "reveal_watch.py"), "w").write(RW2)
open(os.path.join(ROOT, "orchestrator.py"), "w").write(O2)
open(T, "w").write(TEST)
print("patch65 applied to", ROOT)
