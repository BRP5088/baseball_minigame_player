"""The reveal WATCHER: episodes, the mark that separates turns, and the fallback.

WHY THIS EXISTS
---------------
`wait_for_reveal_cards()` polls at 4 Hz for 75 s and timed out on 7 OF 7 TURNS
of the live match on 2026-09-08, logging "peak edge 0.034-0.0535" every time --
so `read_matchup_reveal()` never ran and every turn burned the full budget. A
20 Hz sampler on chiaki's frame dump, scoring frames with THE SAME
`orchestrator.center_card_edge_fraction`, saw 957 of 4129 samples at or above
the 0.065 threshold over 234 s: episodes 4-10 s long peaking at 0.08-0.16, one
per turn. The logged 0.0535 is the FACE-DOWN pre-flip state. The poll was not
looking during the flip.

`reveal_watch.RevealWatcher` looks all the time, on a background thread, and
records every episode. What that buys is only real if four things hold, and
each has its own section below:

  1. a run of above-threshold frames becomes ONE episode whose kept frame is
     the PEAK -- not the first frame over the line, which is mid-flip and is
     what produced the "intended card absent from reveal" misfires;
  2. `episode_after(t_mark)` never hands back the PREVIOUS turn's reveal --
     without that the whole scheme reads the wrong turn's cards, silently;
  3. it answers an OPEN episode rather than making a turn wait out a 4-10 s
     animation plus the close gap;
  4. when the dump is not there, `orchestrator` falls back to the poll it
     replaced -- asserted on CALLS, because both paths return the same thing
     and only the calls can tell them apart;
  5. a DIP below the line inside one reveal does not split it in two, and the
     3.23 s silence that really separates two screens does (section 1b, 1c);
  6. the dump DYING mid-wait ends the wait at once and hands what is left of
     the budget to the poll, instead of idling out a budget nothing can
     satisfy any more (section 7).

Section 5 pins tonight's measurement against SIX real frames -- two genuine
reveals, two face-down, and two of the end-of-round LOSER screen, which the
statistic also accepts and which no cutoff separates from a weak reveal --
and section 6 is the anti-vacuity check: a threading test that never started
a thread passes everything above by doing nothing at all.

Sections 1b and 1c drive `_tick(now=...)` on a SYNTHETIC clock rather than
starting a thread. A 38-second timeline would otherwise take 38 seconds and
be at the mercy of suite load (CLAUDE.md 10.13a); the threaded path is
exercised by sections 1, 3, 6 and 7.

Offline: no capture, no vision call, no dump, no console. The scripted
watchers inject their own reader and scorer; the fixture section reads saved
frames only.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)

import base64
import io
import os
import threading
import time
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import reveal_watch
import orchestrator as o

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def wait_until(pred, seconds=5.0, poll=0.005):
    """Wait for a condition instead of for a duration.

    Every assertion in this file is about CONTENT -- how many episodes, which
    frame -- and none is about how fast the thread got there. Sleeping a fixed
    amount would make the suite's own load (CLAUDE.md 10.13a) into a failure;
    waiting on the predicate cannot.
    """
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(poll)
    return pred()


class Frame:
    """A stand-in for a decoded frame: carries its own score and its identity.

    `copy()` returns an object that is EQUAL by tag but not identical, so a
    check that the watcher kept the right frame cannot pass by accident on an
    `is` comparison against the live object the loop is still holding.
    """

    def __init__(self, tag, score):
        self.tag = tag
        self.score = score

    def copy(self):
        return Frame(self.tag, self.score)

    def __repr__(self):
        return f"<Frame {self.tag} {self.score}>"


class Reader:
    """Hands out a scripted sequence of frames, one per call, then repeats the
    last one forever. Records the THREAD it was called on -- section 6."""

    def __init__(self, frames, tail=None):
        self.frames = list(frames)
        self.tail = tail if tail is not None else (
            self.frames[-1] if self.frames else None)
        self.i = 0
        self.calls = 0
        self.threads = set()
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            self.calls += 1
            self.threads.add(threading.current_thread().name)
            if self.i < len(self.frames):
                f = self.frames[self.i]
                self.i += 1
                return f
        return self.tail

    @property
    def exhausted(self):
        with self.lock:
            return self.i >= len(self.frames)


def score_of(frame):
    return frame.score


# THE SEQUENCE, shaped like a real turn: quiet table, the FACE-DOWN pair (the
# 0.050-0.054 state that produced the live "peak edge 0.0535" line and that the
# threshold must reject), the flip rising to its peak, the decay, and quiet
# again. `PEAK_TAG` is the one frame worth a vision call.
BASE, FACEDOWN = 0.034, 0.052
RISE = [0.070, 0.095, 0.128, 0.101, 0.081]
PEAK_TAG = "rise2"
THRESHOLD = 0.065


def scripted_frames():
    fs = [Frame(f"base{i}", BASE) for i in range(3)]
    fs += [Frame(f"down{i}", FACEDOWN) for i in range(4)]
    fs += [Frame(f"rise{i}", s) for i, s in enumerate(RISE)]
    fs += [Frame(f"quiet{i}", BASE) for i in range(3)]
    return fs


def watcher(frames, **kw):
    r = Reader(frames, tail=Frame("tail", BASE))
    # period small so the sequence is consumed quickly; close_gap generous so
    # a scheduling stall inside the above-threshold run cannot SPLIT the
    # episode and turn a load spike into a failed assertion. The measured
    # worst sleep overrun during a suite run is 9.7ms (CLAUDE.md 10.13a) --
    # 0.4s is a 40x margin.
    w = reveal_watch.RevealWatcher(r, score_of, THRESHOLD, period=0.01,
                                   close_gap=0.4, log=lambda m: None, **kw)
    return w, r


# --- 1. Segmentation: one episode, and its frame is the PEAK ---------------
w, r = watcher(scripted_frames())
w.start()
try:
    got = wait_until(lambda: len(w.episodes()) >= 1, seconds=8.0)
    eps = w.episodes()
    check(got and len(eps) == 1,
          f"a baseline / face-down / rise / peak / decay / baseline sequence "
          f"must segment into exactly ONE episode, got {len(eps)}: {eps}")
    if len(eps) == 1:
        e = eps[0]
        check(e.frame is not None and e.frame.tag == PEAK_TAG,
              f"the kept frame is {getattr(e.frame, 'tag', None)!r}, not the "
              f"PEAK frame {PEAK_TAG!r} (score {max(RISE)}). Keeping the first "
              "frame over the line means spending the vision call on a "
              "half-drawn faceoff -- exactly the mid-flip read that made the "
              "misfire auditor report our own card as absent.")
        check(abs(e.peak - max(RISE)) < 1e-9,
              f"episode peak {e.peak} is not the sequence maximum {max(RISE)}")
        check(e.t_first < e.t_peak,
              f"t_first {e.t_first} must precede t_peak {e.t_peak}: the "
              "episode is opened by the first frame over the line and the "
              "peak arrives later")
        check(e.closed,
          "the episode never closed after the score fell back below "
          "threshold for longer than close_gap -- an episode that never "
          "closes is one that swallows the NEXT turn's reveal too")
        check(e.samples == len(RISE),
              f"episode covered {e.samples} frames, expected the {len(RISE)} "
              "above-threshold ones")
        # The face-down state must not be inside the episode at all: it is
        # BELOW the threshold, and admitting it is how the reveal wait fired
        # on two card backs.
        check(e.peak > FACEDOWN and THRESHOLD > FACEDOWN,
              f"the face-down score {FACEDOWN} is not below the threshold "
              f"{THRESHOLD}; the sequence does not exercise what it claims")
finally:
    w.stop()


# A SYNTHETIC-CLOCK DRIVER. `_tick` takes `now` as an argument, so a timeline
# of any length costs microseconds and its segmentation is deterministic: no
# thread, no sleeps, nothing for suite load to perturb.
def timeline(spans, step=0.05):
    # [(t0, t1, score, tag), ...] -> [(t, Frame), ...] at the sampler's own
    # 20 Hz, so a span's length is read straight off the measured trace.
    out = []
    for t0, t1, s, tag in spans:
        i = 0
        while t0 + i * step < t1 - 1e-9:
            out.append((round(t0 + i * step, 4), Frame(f"{tag}{i}", s)))
            i += 1
    return out


def hand_drive(spans, step=0.05, close_gap=1.0, stop_before=None):
    samples = timeline(spans, step)
    r = Reader([f for _t, f in samples], tail=None)
    w = reveal_watch.RevealWatcher(r, score_of, THRESHOLD, close_gap=close_gap,
                                  log=lambda m: None)
    rest = []
    for t, _f in samples:
        if stop_before is not None and t >= stop_before:
            rest.append(t)
            continue
        w._tick(now=t)
    return w, rest


# --- 1b. A DIP INSIDE ONE REVEAL MUST NOT SPLIT IT -------------------------
# CLOSE_GAP exists for this and nothing tested it: the sequences above rise
# through the threshold and come back down without ever dipping inside the
# episode, so closing on the FIRST below-threshold sample passed the whole
# file. Measured over the 14 episodes of the 720 s trace: the statistic dips
# below the line INSIDE an episode as the cards animate, the longest such dip
# is 0.41 s, and the shortest silence BETWEEN two episodes is 3.23 s. 0.40 s
# here is that longest measured dip; section 1c uses the 3.23 s.
DIP_PEAK = 0.150
DIP_SPANS = [
    (0.0, 1.0, BASE, "pre"),
    (1.0, 3.0, 0.090, "up"),
    (3.0, 3.40, 0.040, "dip"),      # 0.40 s, under CLOSE_GAP
    (3.40, 5.0, DIP_PEAK, "late"),  # the TRUE peak is on the far side of it
    (5.0, 9.0, BASE, "post"),
]
wd, _rest = hand_drive(DIP_SPANS)
eps = wd.episodes()
check(len(eps) == 1,
      f"a 0.40 s dip -- the longest measured inside a real episode -- SPLIT "
      f"one reveal in two: {len(eps)} episodes, {eps}. Two half-episodes mean "
      f"the turn reads whichever half it asks for and the peak frame is the "
      f"peak of a fragment, not of the reveal.")
if len(eps) == 1:
    e = eps[0]
    check(abs(e.peak - DIP_PEAK) < 1e-9,
          f"episode peak {e.peak} is not the timeline maximum {DIP_PEAK}, "
          "which lies AFTER the dip")
    check(getattr(e.frame, "tag", None) == "late0",
          f"the kept frame is {getattr(e.frame, 'tag', None)!r}, not the "
          "post-dip peak frame 'late0'")
    check(abs(e.t_first - 1.0) < 1e-6,
          f"t_first {e.t_first} is not the first above-threshold sample (1.0) "
          "-- the episode was re-opened after the dip")
    check(e.closed, "the episode never closed after the 4 s of quiet at the end")


# --- 1c. THE THIRD POPULATION: the end-of-round LOSER screen ---------------
# The same statistic fires on the end-of-round LOSER screen (0.0705-0.0764
# over the 15 saved frames of it; genuine reveals reach down to 0.0729 in
# orchestrator's own census, so the two OVERLAP and no cutoff separates them
# -- CLAUDE.md 10.4). The old poll was safe because it only ever ran inside
# one turn's post-play window; this watcher reads all the time, so what bounds
# the confound is the MARK, and that is what these three checks are.
#
# The timeline is the measured one: the LOSER episode of the trace
# (t = 222.47-245.67, 23.20 s, peak 0.0769), the 3.23 s silence that followed
# it -- the SHORTEST between any two episodes in 720 s -- and then a genuine
# reveal.
CONFOUND = 0.075
CONF_SPANS = [
    (0.0, 1.0, BASE, "quiet"),
    (1.0, 24.2, CONFOUND, "loser"),      # 23.2 s, the measured duration
    (24.2, 27.43, BASE, "silence"),      # 3.23 s, the measured shortest gap
    (27.43, 33.43, 0.1485, "reveal"),    # a genuine reveal, measured peak
    (33.43, 38.43, BASE, "after"),
]
MARK = 10.0            # a card committed while the LOSER screen is still up
wc, rest_t = hand_drive(CONF_SPANS, stop_before=12.0)
mid = wc.episode_after(MARK, timeout=0.0)
check(mid is None,
      f"the still-OPEN LOSER episode was handed back for a mark taken inside "
      f"it ({mid!r}); an episode already under way when the card was "
      "committed belongs to whatever was on screen BEFORE the play")
# ... now the rest of the timeline, through the silence and the real reveal.
for t, _f in timeline(CONF_SPANS):
    if t >= 12.0:
        wc._tick(now=t)
eps = wc.episodes()
check(len(eps) == 2,
      f"the measured 3.23 s silence did not separate the LOSER screen from "
      f"the reveal that followed it: {len(eps)} episode(s), {eps}. Merged, "
      "the reveal inherits the LOSER screen's t_first and no mark can ever "
      "reach it.")
after = wc.episode_after(MARK, timeout=0.0)
check(after is not None and abs(after.t_first - 27.43) < 1e-6,
      f"the episode returned for a mark inside the LOSER screen is {after!r}, "
      "not the genuine reveal that began at 27.43")
if after is not None:
    check(str(getattr(after.frame, "tag", "")).startswith("reveal"),
          f"the frame handed over is {getattr(after.frame, 'tag', None)!r}, "
          "not one of the reveal's own")
early = wc.episode_after(0.5, timeout=0.0)
check(early is not None and abs(early.t_first - 1.0) < 1e-6,
      f"a mark placed BEFORE the LOSER screen got {early!r} instead of that "
      "episode -- the statistic does not reject that screen and this file "
      "must not pretend it does; what bounds the confound is the mark")


# --- 2. The mark: never the previous turn's reveal -------------------------
# Two episodes in one sequence, with a mark taken between them. This is the
# one that matters most in the live loop: without it, every turn would read
# the reveal of the turn before, which resolves to a plausible pair of cards
# and a silently wrong match_log row.
two = ([Frame("a_base", BASE)] * 2 + [Frame("a_hi", 0.10)] * 3
       + [Frame("gap", BASE)] * 90 + [Frame("b_hi", 0.12)] * 3
       + [Frame("b_quiet", BASE)] * 90)
w, r = watcher(two)
w.start()
try:
    ok = wait_until(lambda: len(w.episodes()) >= 1, seconds=8.0)
    first = w.episodes()[0] if w.episodes() else None
    check(ok and first is not None, "the first episode never closed")
    if first is not None:
        # A mark taken AFTER the first episode began must never see it, even
        # while it is the newest thing on record.
        t_mark = first.t_last + 1e-6
        stale = w.episode_after(first.t_first - 1.0, timeout=0.0)
        check(stale is not None and stale.t_first == first.t_first,
              "an episode that began after an EARLIER mark was not returned")
        got2 = w.episode_after(t_mark, timeout=8.0)
        check(got2 is not None,
              "the second episode was never returned for a mark placed "
              "between the two")
        if got2 is not None:
            check(got2.t_first > first.t_last,
                  f"episode_after returned the PREVIOUS turn's episode "
                  f"(t_first {got2.t_first} <= previous t_last {first.t_last})")
            check(getattr(got2.frame, "tag", None) == "b_hi",
                  f"returned frame {getattr(got2.frame, 'tag', None)!r}, not "
                  "the second episode's own peak frame 'b_hi'")
    # ... and a mark placed after EVERYTHING must time out rather than hand
    # back the newest episode it can find.
    t0 = time.time()
    none = w.episode_after(time.time() + 60.0, timeout=0.2)
    check(none is None,
          "episode_after returned an episode that began BEFORE the mark; "
          "the t_first >= t_mark guard is the only thing separating turns")
    check(time.time() - t0 >= 0.2,
          "episode_after returned before its timeout with no episode -- it "
          "must block for the budget it was given, or a turn would give up "
          "on a reveal that had not happened yet")
finally:
    w.stop()


# --- 3. An OPEN episode is answered at once -------------------------------
# The above-threshold frames never stop, so nothing here can ever close. A
# watcher that waited for closure would hang for the whole timeout, and in the
# live loop would add close_gap plus the rest of a 4-10 s animation to a turn
# that arrived mid-reveal.
never_ends = ([Frame("q", BASE)] * 2 + [Frame("hot", 0.11)] * 500)
w, r = watcher(never_ends)
mark = w.mark()
w.start()
try:
    ep = w.episode_after(mark, timeout=8.0)
    check(ep is not None,
          "an episode that is still OPEN was never returned: episode_after "
          "waited for a close that a continuing reveal never gives it")
    if ep is not None:
        check(ep.closed is False,
              "the episode reported itself closed while its frames were "
              "still above threshold")
        check(ep.frame is not None and ep.frame.tag == "hot",
              f"open episode handed back {getattr(ep.frame, 'tag', None)!r} "
              "instead of a frame from the episode")
    check(w.episodes() == [],
          f"an open episode must not already be in the closed list; "
          f"found {w.episodes()}")
finally:
    w.stop()


# --- 4. Unavailable -> orchestrator falls back to wait_for_reveal_cards ----
# Both paths end in a reveal read, so only the CALLS distinguish them.
class Calls:
    def __init__(self, ret=True):
        self.n = 0
        self.ret = ret

    def __call__(self, *a, **k):
        self.n += 1
        return self.ret


def with_watcher(watcher_obj, waiter, t_mark, timeout=8.0):
    saved = (o._REVEAL_WATCHER, o.wait_for_reveal_cards)
    o._REVEAL_WATCHER = watcher_obj
    o.wait_for_reveal_cards = waiter
    try:
        return o.reveal_frame_for(t_mark, timeout=timeout), None
    except Exception as e:
        return None, e
    finally:
        o._REVEAL_WATCHER, o.wait_for_reveal_cards = saved


# (a) no watcher at all -- the state every offline test and every run before
#     this patch is in.
waiter = Calls(True)
img, err = with_watcher(None, waiter, time.time())
check(err is None and img is None,
      f"with no watcher, reveal_frame_for must fall back and return None "
      f"(read fresh); got img={img!r} err={err!r}")
check(waiter.n == 1,
      f"the polling wait was called {waiter.n} times, expected exactly 1 -- "
      "with no watcher there is nothing else that can see the reveal")

# (b) a watcher that is present but cannot see the dump.
def no_dump():
    raise OSError("no dump")


dead = reveal_watch.RevealWatcher(no_dump, score_of, THRESHOLD, period=0.005,
                                  log=lambda m: None)
dead.start()
wait_until(lambda: not dead.available, seconds=5.0)
check(not dead.available,
      "a watcher whose every read RAISES still reports itself available; "
      "the caller would wait out the whole budget instead of falling back")
waiter = Calls(True)
img, err = with_watcher(dead, waiter, time.time())
check(err is None and img is None and waiter.n == 1,
      f"an unavailable watcher must fall back to wait_for_reveal_cards; "
      f"calls={waiter.n} img={img!r} err={err!r}")
# ... and the fallback keeps the old contract: a timeout still raises.
waiter = Calls(False)
img, err = with_watcher(dead, waiter, time.time())
check(isinstance(err, RuntimeError) and waiter.n == 1,
      f"a fallback poll that times out must raise the same RuntimeError the "
      f"loop already catches; got {err!r} after {waiter.n} call(s)")
dead.stop()

# (c) an AVAILABLE watcher must NOT call the poll, and must hand its peak
#     frame back for the vision call.
live_frames = [Frame("q", BASE)] * 2 + [Frame("hot", 0.11)] * 500
w, r = watcher(live_frames)
mark = w.mark()
w.start()
try:
    wait_until(lambda: w.available and r.calls > 3, seconds=5.0)
    waiter = Calls(True)
    img, err = with_watcher(w, waiter, mark)
    check(err is None, f"reveal_frame_for raised with a live watcher: {err!r}")
    check(waiter.n == 0,
          f"the polling wait ran {waiter.n} times while the watcher was "
          "available -- the 75s poll is exactly what this replaces")
    check(getattr(img, "tag", None) == "hot",
          f"reveal_frame_for returned {img!r}, not the episode's peak frame")
finally:
    w.stop()

# (d) an available watcher that sees NOTHING after the mark still gives up
#     the way the poll did, so the caller's `except` is unchanged.
w2, r2 = watcher([Frame("q", BASE)] * 500)
w2.start()
try:
    wait_until(lambda: w2.available and r2.calls > 3, seconds=5.0)
    waiter = Calls(True)
    saved = (o._REVEAL_WATCHER, o.wait_for_reveal_cards)
    o._REVEAL_WATCHER, o.wait_for_reveal_cards = w2, waiter
    try:
        err = None
        try:
            o.reveal_frame_for(w2.mark(), timeout=0.3)
        except Exception as e:
            err = e
    finally:
        o._REVEAL_WATCHER, o.wait_for_reveal_cards = saved
    check(isinstance(err, RuntimeError),
          f"a watcher that saw no episode must raise RuntimeError like the "
          f"poll's timeout did; got {err!r}")
    check(waiter.n == 0,
          "an available watcher must not ALSO run the 75s poll")
finally:
    w2.stop()


# --- 4b. The frame actually reaches the vision call -----------------------
# The whole point of the peak frame is that the model reads THAT image. A
# read_matchup_reveal that captures fresh anyway would pass every check above
# while changing nothing at all.
class Vision:
    def __init__(self):
        self.calls = 0
        self.b64 = None

    def create(self, **kw):
        self.calls += 1
        for block in kw["messages"][0]["content"]:
            if block.get("type") == "image":
                self.b64 = block["source"]["data"]
        return types.SimpleNamespace(content=[types.SimpleNamespace(
            type="text", text='{"cards": []}')])


PROBE = Image.new("RGB", (640, 360), (17, 200, 33))
v = Vision()
saved = (o.client, o.capture_screenshot_b64)
o.client = types.SimpleNamespace(messages=v)
o.capture_screenshot_b64 = lambda *a, **k: "SENTINEL-FRESH-CAPTURE"
try:
    o.read_matchup_reveal(img=PROBE)
finally:
    o.client, o.capture_screenshot_b64 = saved
check(v.calls == 1, f"read_matchup_reveal made {v.calls} vision calls")
check(v.b64 not in (None, "SENTINEL-FRESH-CAPTURE"),
      "read_matchup_reveal(img=...) captured a FRESH screenshot instead of "
      "encoding the frame it was handed -- the watcher's peak frame would "
      "never reach the model and nothing about the reveal would change")
if v.b64 and v.b64 != "SENTINEL-FRESH-CAPTURE":
    back = Image.open(io.BytesIO(base64.b64decode(v.b64))).convert("RGB")
    check(back.size == PROBE.size,
          f"the encoded image is {back.size}, not the {PROBE.size} it was given")
    px = back.getpixel((320, 180))
    check(abs(px[0] - 17) < 12 and abs(px[1] - 200) < 12 and abs(px[2] - 33) < 12,
          f"the encoded image is not the frame that was passed in (centre "
          f"pixel {px}, expected ~(17, 200, 33))")

# ... and with no image it still takes its own screenshot, unchanged.
v2 = Vision()
saved = (o.client, o.capture_screenshot_b64)
o.client = types.SimpleNamespace(messages=v2)
o.capture_screenshot_b64 = lambda *a, **k: "SENTINEL-FRESH-CAPTURE"
try:
    o.read_matchup_reveal()
finally:
    o.client, o.capture_screenshot_b64 = saved
check(v2.b64 == "SENTINEL-FRESH-CAPTURE",
      "read_matchup_reveal() with no image must capture as it always did; "
      f"got {str(v2.b64)[:40]!r}")


# --- 5. The real statistic on the real frames -----------------------------
# Tonight's measurement, pinned. These four came out of the 20 Hz sampler run
# that proved the reveal is on the dump (overnight/census/
# reveal_edge_20260908.jsonl); the two REVEALS show a batter+boost against a
# pitcher+focus at the diamond centre, fully drawn, and the two FACE_DOWN are
# the pre-flip pair of card backs whose 0.050-0.054 is what the live poll kept
# reporting as its peak.
#
# BOTH WIDTHS MATTER. The statistic is a gradient-pixel count normalised by
# area, so it rises as the capture shrinks: the watcher scores the dump at its
# native 1920, and orchestrator's own poll path resizes to
# SETTLE_CALIBRATION_WIDTH = 2000. If the threshold only separated at one of
# them, the watcher and the poll would disagree about the same screen.
FIXTURES = os.path.join(_ROOT, "test_fixtures", "reveal_episode")
REVEALS = {
    "reveal_t0113.54.jpg": "batter + boost vs pitcher + focus, fully drawn",
    "reveal_t0127.44.jpg": "the next turn's faceoff, fully drawn",
}
FACE_DOWN_FIXTURES = {
    "facedown_t0110.46.jpg": "two card backs at centre, pre-flip",
    "facedown_t0081.68.jpg": "two card backs at centre, pre-flip",
}
# THE THIRD POPULATION, and the only fixtures here whose expected verdict is
# that the detector ACCEPTS them. The end-of-round LOSER screen puts a bright
# wreath and the dealer's white face at the diamond centre and measures
# 0.0705-0.0764 at 1920 (0.0677-0.0737 at 2000) over the 15 saved frames of
# it, while orchestrator's own census records genuine reveals down to 0.0729
# at 2000 -- one overlapping population, so no cutoff on this score can
# separate them and none is invented here (CLAUDE.md 10.4).
LOSER_FIXTURES = {
    "loser_t0225.30.jpg": "end-of-round LOSER screen",
    "loser_t0231.38.jpg": "the same screen six seconds later",
}
WIDTHS = (1920, 2000)


def fixture_score(path, width):
    img = Image.open(path)
    if img.size[0] != width:
        img = img.resize((width, round(img.size[1] * width / img.size[0])),
                         Image.LANCZOS)
    return o.center_card_edge_fraction(img)


seen = 0
for name, what in REVEALS.items():
    p = os.path.join(FIXTURES, name)
    if not os.path.exists(p):
        failures.append(f"missing fixture {name} -- this test must not "
                        "silently skip; a detector check that runs on zero "
                        "frames reports success on nothing")
        continue
    for width in WIDTHS:
        s = fixture_score(p, width)
        seen += 1
        check(s >= o.REVEAL_EDGE_THRESHOLD,
              f"{name} ({what}) at {width}px scores {s:.4f} < threshold "
              f"{o.REVEAL_EDGE_THRESHOLD}: the watcher would never open an "
              "episode on a genuine reveal, and the turn would fall back to "
              "the 75s poll that already misses it")
for name, what in FACE_DOWN_FIXTURES.items():
    p = os.path.join(FIXTURES, name)
    if not os.path.exists(p):
        failures.append(f"missing fixture {name} -- this test must not silently skip")
        continue
    for width in WIDTHS:
        s = fixture_score(p, width)
        seen += 1
        check(s < o.REVEAL_EDGE_THRESHOLD,
              f"{name} ({what}) at {width}px scores {s:.4f} >= threshold "
              f"{o.REVEAL_EDGE_THRESHOLD}: the watcher would open an episode "
              "on the FACE-DOWN pair and hand the model a screen where our "
              "card has not flipped -- the 2026-09-01 misfire, from the other "
              "direction")
for name, what in LOSER_FIXTURES.items():
    p = os.path.join(FIXTURES, name)
    if not os.path.exists(p):
        failures.append(f"missing fixture {name} -- this test must not silently skip")
        continue
    for width in WIDTHS:
        s = fixture_score(p, width)
        seen += 1
        check(o.REVEAL_EDGE_THRESHOLD <= s <= 0.090,
              f"{name} ({what}) at {width}px scores {s:.4f}, outside the "
              f"measured LOSER band (0.0677-0.0764 across 15 frames of that "
              f"screen, threshold {o.REVEAL_EDGE_THRESHOLD}). This fixture is "
              "the CONFOUND: the watcher DOES open an episode on this screen "
              "and what keeps it out of a turn is the mark, not the score. If "
              "it now scores BELOW the threshold that is good news, and not "
              "silently: update the confound paragraphs in reveal_watch.py "
              "and in the patch before touching this check.")
check(seen == len(WIDTHS) * (len(REVEALS) + len(FACE_DOWN_FIXTURES)
                             + len(LOSER_FIXTURES)),
      f"scored {seen} fixture readings, expected "
      f"{len(WIDTHS) * (len(REVEALS) + len(FACE_DOWN_FIXTURES) + len(LOSER_FIXTURES))}"
      " -- a missing fixture must FAIL this file, never shrink it")


# --- 6. Anti-vacuity: the thread really ran, and stop() really stops it ----
# Sections 1-3 would pass unchanged if the reader were called on the MAIN
# thread by some synchronous shortcut, and section 4's fallback would pass if
# no thread ever started at all. Both are named here.
w, r = watcher(scripted_frames())
before = threading.active_count()
w.start()
wait_until(lambda: r.calls > 5, seconds=5.0)
check(r.calls > 5,
      f"the injected read_frame was called {r.calls} times after start(); the "
      "watcher never read a frame, so every episode check above ran on "
      "nothing")
check(r.threads and r.threads != {threading.current_thread().name},
      f"read_frame only ever ran on {r.threads} -- it must run on the "
      "watcher's own thread, or the match loop is still blocked while it "
      "polls, which is the defect")
check(w.running, "the watcher reports itself not running while it is reading")
check(threading.active_count() > before,
      "start() added no thread")
w.stop()
check(not w.running, "running is still True after stop()")
check(wait_until(lambda: threading.active_count() <= before, seconds=5.0),
      "stop() left the watcher thread alive -- a daemon thread that outlives "
      "the match keeps reading the dump for the rest of the process")
calls_at_stop = r.calls
time.sleep(0.15)
check(r.calls == calls_at_stop,
      f"read_frame was called {r.calls - calls_at_stop} more times after "
      "stop() returned")

# The available/unavailable flag is the fallback's whole trigger, so a
# never-started watcher must never claim to be available.
fresh = reveal_watch.RevealWatcher(lambda: None, score_of, THRESHOLD,
                                   log=lambda m: None)
check(not fresh.available,
      "a watcher that was never start()ed reports itself available")


# --- 7. The dump dying MID-WAIT ends the wait and pays the poll the rest ---
# `reveal_frame_for` checks `available` once, before it starts waiting. If the
# stream dies after that -- chiaki crashing, the VPN reconnecting, the console
# freezing, all of which this project has logged -- a watcher that only ever
# asks "is the thread alive" keeps polling for the whole 75 s budget against
# something that can no longer answer. That is the wait this patch exists to
# remove, wearing a different hat.
class Faucet:
    # Hands out one frame until it is turned OFF, then None forever, which is
    # exactly what frame_dump.read_frame does when the dump stops.
    def __init__(self, frame):
        self.frame = frame
        self.on = True
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.frame if self.on else None


class Waiter:
    # wait_for_reveal_cards stand-in that records HOW LONG it was given.
    def __init__(self, ret=True):
        self.n = 0
        self.ret = ret
        self.max_wait = None

    def __call__(self, *a, **k):
        self.n += 1
        self.max_wait = k.get("max_wait", a[0] if a else None)
        return self.ret


STALE = 1.0
fau = Faucet(Frame("quiet", BASE))
w7 = reveal_watch.RevealWatcher(fau, score_of, THRESHOLD, period=0.005,
                                stale_after=STALE, log=lambda m: None)
w7.start()
try:
    check(wait_until(lambda: w7.available and fau.calls > 3, seconds=5.0),
          "the faucet watcher never became available, so section 7 would be "
          "measuring the wrong state")
    fau.on = False
    t0 = time.time()
    ep7 = w7.episode_after(w7.mark(), timeout=8.0)
    dt = time.time() - t0
    check(ep7 is None, f"a dead dump produced an episode: {ep7!r}")
    check(dt < 4.0,
          f"episode_after waited {dt:.1f}s of an 8s budget against a dump that "
          f"stopped {STALE}s in: it burns the whole 75s budget live and the "
          "poll never gets the chance it was kept for")
    check(dt >= STALE * 0.5,
          f"episode_after gave up after {dt:.2f}s, before the watcher could "
          f"have gone stale ({STALE}s) -- the check above would pass on a "
          "watcher that never waits at all")
    check(not w7.available,
          "the watcher reports itself available with no frame for longer than "
          "stale_after, so nothing downstream can tell the dump died")
finally:
    w7.stop()

fau2 = Faucet(Frame("quiet", BASE))
w8 = reveal_watch.RevealWatcher(fau2, score_of, THRESHOLD, period=0.005,
                                stale_after=STALE, log=lambda m: None)
w8.start()
try:
    check(wait_until(lambda: w8.available and fau2.calls > 3, seconds=5.0),
          "the second faucet watcher never became available")
    fau2.on = False
    waiter = Waiter(True)
    t0 = time.time()
    img8, err8 = with_watcher(w8, waiter, w8.mark(), timeout=8.0)
    el = time.time() - t0
    check(err8 is None and img8 is None,
          f"after the dump died the fallback must read fresh and not raise; "
          f"img={img8!r} err={err8!r}")
    check(waiter.n == 1,
          f"the poll ran {waiter.n} times after the dump died, expected 1 -- "
          "it reads through the capture path, not the dump, so it can still "
          "see a reveal the watcher cannot")
    check(waiter.max_wait is not None,
          "the fallback poll was given no max_wait, so it starts a fresh 75s "
          "clock on top of the time already spent and this turn ends up "
          "SLOWER than it was before patch60")
    if waiter.max_wait is not None:
        check(el + waiter.max_wait <= 8.0 + 0.3,
              f"waited {el:.2f}s and then gave the poll {waiter.max_wait:.2f}s "
              "-- together more than the budget the turn was given")
        check(waiter.max_wait > 1.0,
              f"the poll was given {waiter.max_wait:.2f}s; a fallback with no "
              "time left in it is not a fallback")
    check(el < 4.0,
          f"reveal_frame_for spent {el:.1f}s of an 8s budget against a dead "
          "dump before falling back")
finally:
    w8.stop()


if failures:
    for f in failures:
        print("FAIL:", f)
    raise SystemExit(1)

print(f"OK: reveal watcher segments episodes on the peak frame (through a "
      f"0.40s dip, not through a 3.23s silence), refuses the previous "
      f"screen's episode open or closed, answers an open one, falls back to "
      f"the {o.REVEAL_MAX_WAIT:.0f}s poll when the dump is absent and to what "
      f"is LEFT of the budget when it dies mid-wait, and scores "
      f"{len(REVEALS)} real reveals, {len(FACE_DOWN_FIXTURES)} face-down and "
      f"{len(LOSER_FIXTURES)} end-of-round frames at "
      f"{'/'.join(str(x) for x in WIDTHS)}px "
      f"(threshold {o.REVEAL_EDGE_THRESHOLD})")
