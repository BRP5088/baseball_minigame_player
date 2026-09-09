"""patch60: WATCH the frame dump for the reveal, instead of polling for it.

THE DEFECT, MEASURED ON THE LIVE MATCH OF 2026-09-08.
`orchestrator.wait_for_reveal_cards()` polls `_center_card_edge_fraction()` at
4 Hz for REVEAL_MAX_WAIT = 75 s after our card is committed and fires at
REVEAL_EDGE_THRESHOLD = 0.065. It TIMED OUT ON 7 OF 7 TURNS, logging "peak edge
0.034-0.0535" every time. So `read_matchup_reveal()` never ran, the strategy
got no reveal information at all, every turn waited the full 75 s, and the
match took about six extra minutes.

THE REVEAL WAS THERE. A 20 Hz sampler on chiaki's frame dump
(`agent_progress/ocr-speed/reveal_sampler.py`, reading
`frame_dump.read_frame("/tmp/chiaki_frame.bin")` at the native 1920x1080 and
scoring it with THE SAME `orchestrator.center_card_edge_fraction`) saw
1848 of 12678 samples at or above 0.065 over 720 s -- 14 EPISODES, 1.67-23.2 s
long, peaking at 0.0765-0.1687, one about every 20-35 s
(`overnight/census/reveal_edge_20260908.jsonl`).

RE-SEGMENTED FOR THIS ROUND, BECAUSE THE FIGURE FIRST QUOTED HERE -- "957 of
4129 samples over 234 s, episodes 4-10 s peaking at 0.08-0.16" -- WAS A PREFIX
OF THAT FILE AND NOTHING SAID SO. Counting only rows with t <= 234.0 gives
exactly 4128 rows and 956 over threshold, which is where those numbers came
from; the prefix ends in the MIDDLE of the file's one anomalous episode (see
THE THIRD POPULATION below). Over all 720 s the eleven episodes that look like
reveals peak at 0.1036-0.1687 and run 4.00-12.82 s, and the longest
sub-threshold DIP inside any episode is 0.41 s while the shortest silence
BETWEEN two episodes is 3.23 s -- which is the measurement CLOSE_GAP = 1.0 s
sits in the middle of.

HOW MUCH OF THAT IS CONFIRMED BY EYE, since the shape of an episode is not
proof of what was on screen: the sampler saves at most 60 frames
(reveal_sampler.py's SAVE_MAX) and the last one is at t = 248.21, so 7 of the
14 episodes have pictures and 7 do not. "One episode per turn, all of them
reveals" is established for the first 248 s and is an inference after that --
which is exactly how the LOSER episode sat inside the headline figure
unnoticed. The four population claims used here (reveal, face-down, LOSER
band, dip and silence lengths) all come from the frames that DO exist.
The 0.0535 the poll kept
reporting as its peak is the FACE-DOWN pre-flip pair of card backs, which
measures 0.050-0.054 (`overnight/census/reveal_edge_frames_20260908/`,
t0110.46_e0.0541.jpg and t0081.68_e0.0516.jpg against the genuine reveals
t0113.54_e0.1198.jpg and t0127.44_e0.1275.jpg). Re-scored for this patch:

    native 1920      reveals 0.1200, 0.1278      face-down 0.0520, 0.0544
    resized to 2000  reveals 0.1155, 0.1261      face-down 0.0491, 0.0516

so the shipped 0.065 separates the two classes at BOTH widths, which is why
this patch changes no threshold and no region. The poll was simply NOT LOOKING
during the flip. Whether it starts late or the flip lands between polls was
never established -- and this design makes the question irrelevant.

THE THIRD POPULATION, AND WHAT THIS PATCH DOES *NOT* SOLVE. The statistic also
fires on the END-OF-ROUND "LOSER" screen -- a bright wreath and the dealer's
white face at the diamond centre. Measured on the 15 saved frames of episode 6
(t = 222.47-245.67, 23.20 s, the longest in the file): 0.0705-0.0764 at the
native 1920 and 0.0677-0.0737 resized to 2000, i.e. ABOVE the 0.065 threshold
on every one of them. orchestrator.py's own comment at the region change knew
this ("the other 3 are the end-of-match LOSER screen, which this function is
never called on") and knew the mitigation: SCOPING. The old poll ran only
inside one turn's post-play window; a watcher that reads all the time has no
such scope, so this is a real cost of the design and it is stated here rather
than discovered later.

NO PEAK CUTOFF CAN SEPARATE THEM, so none is invented (CLAUDE.md 10.4): the
same orchestrator comment measures genuine reveals down to 0.0729 at 2000px,
which is INSIDE the LOSER band. Two of those frames ship as fixtures and the
new test asserts they score ABOVE the threshold -- the check exists to fail
loudly if anyone later assumes this statistic rejects them.

WHAT IS BOUNDED, and why it is not blocking. `episode_after` returns the FIRST
episode that began at or after the play's mark, and in the ordinary turn the
genuine reveal is that episode: the round-result screen comes AFTER the reveal
and BEFORE the next play. The confound can only be returned on a turn whose
genuine reveal produced no episode at all -- and that turn produced nothing
before this patch either. The blast radius is `match_log.jsonl`: `reveal_cards`
feeds the matchup log and nothing else (see the call site's own comment), the
whole block sits inside a try/except that swallows, and no money, input or
navigation path reads it. The log line names the episode's peak AND duration
so a 23 s / 0.077 episode is identifiable in the morning, and acceptance
criterion 2 ("intended card absent": 0) is what would catch it.

THE MERGE HAZARD IS REFUTED, MEASURED. A confound episode still OPEN when the
next play is marked would pin `t_first` before the mark and hide the genuine
reveal behind it. That needs less than CLOSE_GAP = 1.0 s of sub-threshold
silence between the two, and over the whole 720 s trace the SHORTEST silence
between consecutive episodes is 3.23 s (the rest: 9.4-201 s) -- 3.2x the gap.
It is also physically excluded: the LOSER screen is dismissed by a CLOSE press
and a whole new round of dealing and card selection follows before any reveal.
Pinned by a segmentation test built on the measured timing.

THE FIX IS THE USER'S: "couldn't the frame dump from chiaki be used ... that
way more photos can be scanned", and "increase the Hz". A daemon thread reads
the dump at ~20 Hz and records every reveal EPISODE as it happens. The match
loop then asks for the episode that followed ITS OWN play and reads that
episode's PEAK frame. No polling race, no 75 s wait for something that already
happened, and the vision call sees the frame where the statistic was highest --
the fully drawn cards -- rather than whatever was on screen when a poll
happened to fire, which is what produced the mid-flip "intended card absent
from reveal" misfires.

WHAT IT ADDS AND WHAT IT LEAVES ALONE

  * NEW `reveal_watch.py`. `RevealWatcher(read_frame, score, threshold, ...)`
    with BOTH callables INJECTED: production passes `frame_dump.read_frame`
    and `orchestrator.center_card_edge_fraction`, tests pass fakes. It
    imports nothing from orchestrator (that would be circular) and it does no
    OCR and no vision call -- `tesserocr` links `cysignals`, whose
    sig_on/sig_off is process-global and MAIN-THREAD ONLY, and a worker-first
    call silently drops the whole process back to spawning subprocesses
    (CLAUDE.md 3). numpy and PIL on the thread are fine.
  * THE DUMP PATH IS NEVER CAPTURED. `frame_dump.read_frame` is passed with no
    arguments, so it resolves the path at CALL time -- argument, then
    CHIAKI_FRAME_DUMP, then DEFAULT_PATH -- and returns None under
    BASEBALL_TEST_RUN, which is what keeps the offline suite from ever being
    handed a frame by a chiaki that happens to be streaming. A path bound in
    a `def` line is CLAUDE.md 10.18's bug, silently.
  * `orchestrator.start_reveal_watcher()` / `stop_reveal_watcher()` are called
    from run()'s existing try/finally, alongside the screenshot logger and for
    the same reason: the loop exits through many paths and a daemon thread
    that outlives its run keeps reading forever.
  * `play_one_turn` stamps the play with `reveal_mark()` ONE LINE BEFORE
    `select_and_play(...)` -- before, so no part of the flip can land in the
    gap -- and carries it in `matchup_info["reveal_mark"]`. run() POPS that
    key before the dict can reach `pending_matchup`, so `match_log.jsonl` is
    byte-for-byte unaffected by this patch.
  * `reveal_frame_for(t_mark)` replaces the `wait_for_reveal_cards()` call at
    the one production site. `wait_for_reveal_cards()` ITSELF IS UNCHANGED and
    is still the fallback whenever the watcher is unavailable -- no patched
    chiaki, no dump, or a dump that stopped. That is the state of every
    offline test, so every existing run() test keeps exercising the old path.
  * `read_matchup_reveal(img=None)` gains an image-in path encoded by
    `screenshot_b64_from_image()`, which applies exactly the
    SCREENSHOT_MAX_WIDTH downscale `capture_screenshot_image()` applies and
    then the same `_encode_jpeg_b64` at quality 85. With no image it captures
    as it always did.
  * UNCHANGED, deliberately: REVEAL_EDGE_THRESHOLD, REVEAL_CENTER_REGION,
    REVEAL_MAX_WAIT, SETTLE_CALIBRATION_WIDTH, every other wait, all
    navigation, and the money path.

THE FAILURE MODES THIS IS BUILT AGAINST, each pinned by a check in the new
test file and each caught by a mutant:

  * an episode that never closes swallows the NEXT turn's reveal too;
  * `episode_after` handing back an episode that began BEFORE the mark reads
    the PREVIOUS turn's cards -- which resolves to a plausible pair and a
    silently wrong log row, the worst shape this project has;
  * keeping the FIRST above-threshold frame instead of the peak spends the
    vision call on a half-drawn faceoff, which is the mid-flip read that made
    the misfire auditor report our own card as absent (CLAUDE.md, the
    2026-09-01 seven turns);
  * losing the fallback turns a machine with no patched chiaki from "slow" to
    "cannot log a matchup at all";
  * an image-in path that captures fresh anyway is CLAUDE.md 10.1 exactly --
    the code did nothing and doing nothing looked like working;
  * a thread that never starts passes every episode check by doing nothing;
  * closing an episode on the FIRST below-threshold sample splits one reveal
    in two -- real episodes dip below the line for up to 0.41 s while the
    cards animate, which is what CLOSE_GAP is for and what nothing tested;
  * `episode_after` that ignores the dump DYING mid-wait idles out the whole
    budget against a watcher that can no longer answer, when the poll (which
    reads through `_fast_grab`, not the dump) could still see the reveal.

PRE-REGISTERED LIVE ACCEPTANCE, stated here so it cannot be moved afterwards.
Over the NEXT live match, with nothing else in the match changed:

  1. reveal episodes found on at least 4 of 5 turns  (tonight: 0 of 7);
  2. "intended card absent from reveal" misfire warnings: 0;
  3. median wait from the play to the episode under 20 s
     (tonight: 75 s on every turn, every one a timeout);
  4. the watcher thread's CPU under 15% of one core. Measured OFFLINE at
     3.8%: center_card_edge_fraction on a real 1920x1080 dump frame is 0.64 ms
     (p90 0.74, max 1.48), the peak-frame copy 0.14 ms and frame_dump.read_frame
     ~1.1 ms, so a 20 Hz tick is ~1.9 ms. That is a prediction, not the
     measurement -- criterion 4 is checked on the live process.

A run that logs "[reveal] no episode within Ns" on most turns FAILS 1 and the
patch is reverted, not tuned: that line and the old timeout line are the same
shape on purpose so the two are comparable turn for turn in one log.

MEMORY, stated because it is the one cost that is not free: each kept episode
holds ONE full frame, ~6 MB at 1920x1080 RGB, so REVEAL_WATCH_KEEP = 8 costs
about 50 MB steady state. Lower `keep` if that ever matters; the lookup only
ever wants the newest, and the rest are for the log and the post-mortem.

Applies to: orchestrator.py; creates reveal_watch.py,
tests/minigame/test_reveal_watch.py, and test_fixtures/reveal_episode/ (six
frames copied from overnight/census/reveal_edge_frames_20260908/: two genuine
reveals, two face-down, and two of the end-of-round LOSER screen).
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch60.py [ROOT]
"""
import ast
import os
import shutil
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
O = os.path.join(ROOT, "orchestrator.py")
M = os.path.join(ROOT, "reveal_watch.py")
T = os.path.join(ROOT, "tests", "minigame", "test_reveal_watch.py")
FIXDIR = os.path.join(ROOT, "test_fixtures", "reveal_episode")
SRCFRAMES = os.path.join(ROOT, "overnight", "census",
                         "reveal_edge_frames_20260908")

# The six real frames, and the names they take in the fixture directory. Two
# genuine reveals (batter + boost against pitcher + focus at the diamond
# centre, fully drawn); two FACE-DOWN pre-flip frames -- the 0.050-0.054 state
# the live poll kept reporting as its peak; and two of the END-OF-ROUND LOSER
# screen, the third population, which scores 0.0705-0.0764 and so clears the
# threshold. The last two are fixtures for a check that this statistic CANNOT
# reject them, not for one that it can.
FRAMES = {
    "t0113.54_e0.1198.jpg": "reveal_t0113.54.jpg",
    "t0127.44_e0.1275.jpg": "reveal_t0127.44.jpg",
    "t0110.46_e0.0541.jpg": "facedown_t0110.46.jpg",
    "t0081.68_e0.0516.jpg": "facedown_t0081.68.jpg",
    "t0225.30_e0.0765.jpg": "loser_t0225.30.jpg",
    "t0231.38_e0.0764.jpg": "loser_t0231.38.jpg",
}

o = open(O).read()

MODULE = r'''"""Watch chiaki's frame dump for the faceoff REVEAL, in the background.

WHY THIS EXISTS
---------------
`orchestrator.wait_for_reveal_cards()` polls the screen at 4 Hz for up to 75
seconds after our card is committed and fires when
`center_card_edge_fraction()` reaches REVEAL_EDGE_THRESHOLD (0.065). In the
live match of 2026-09-08 it TIMED OUT ON 7 OF 7 TURNS, logging "peak edge
0.034-0.0535" every time -- so `read_matchup_reveal()` never ran, the strategy
got no reveal information at all, and every turn paid the full 75 seconds.

The reveal was there. A 20 Hz sampler on the frame dump, scoring frames with
THE SAME `center_card_edge_fraction`, saw 1848 of 12678 samples at or above
0.065 over 720 seconds -- 14 episodes, the eleven reveal-shaped ones 4.00-12.82
s long and peaking at 0.1036-0.1687, one about every 20-35 s
(`agent_progress/ocr-speed/reveal_sampler.py`,
`overnight/census/reveal_edge_20260908.jsonl`). The logged peak of 0.0535 is
the FACE-DOWN pre-flip state (two card backs at the diamond centre, measured
0.050-0.054). So the poll was simply not looking during the flip. Whether it
starts late or the flip lands between polls was never established, and this
module makes the question irrelevant: nothing has to be looking at the right
moment if something is looking all the time.

WHAT LOOKING ALL THE TIME COSTS. The statistic also fires on the END-OF-ROUND
LOSER screen: 15 saved frames of that screen measure 0.0705-0.0764 at 1920 and
0.0677-0.0737 at 2000, all above the threshold, and orchestrator's own region
comment records genuine reveals reaching down to 0.0729 -- so the two overlap
and NO cutoff on the score separates them. The old poll was safe only because
it ran inside one turn's post-play window; this module has no such scope. What
bounds it is the mark: `episode_after` returns the first episode that began at
or after the play, and the round-result screen comes after the reveal and
before the next play, so it can only ever be returned on a turn whose real
reveal produced no episode -- a turn that had nothing before this existed
either. Do not "fix" that with a peak threshold; measure a composition test
against both populations first.

THE SHAPE, which is the user's: "couldn't the frame dump from chiaki be used
... that way more photos can be scanned", and "increase the Hz". A daemon
thread reads the dump at ~20 Hz and records every reveal EPISODE as it
happens. The match loop then asks for the episode that followed ITS OWN play
and reads that episode's PEAK frame. No polling race, no 75 s wait for
something that already happened, and the vision call sees the frame where the
statistic was highest -- the fully drawn cards -- rather than whatever was on
screen at the instant a poll happened to fire, which is what produced the
mid-flip "intended card absent from reveal" misfires.

WHAT THIS MODULE MUST NOT DO
----------------------------
No OCR and no vision call, ever, on this thread. `tesserocr` links `cysignals`,
whose sig_on/sig_off is process-global and MAIN-THREAD ONLY: a worker-first
call silently drops the whole process back to spawning subprocesses
(CLAUDE.md 3). numpy and PIL are fine, and that is all `score` needs.

It also imports nothing from `orchestrator`. `read_frame` and `score` are
INJECTED callables -- production passes `frame_dump.read_frame` and
`orchestrator.center_card_edge_fraction`, tests pass fakes -- which keeps the
import graph acyclic and makes every rule here checkable with no game, no
console and no dump.

THE DUMP PATH IS NEVER CAPTURED HERE. `frame_dump.read_frame()` called with no
arguments resolves it at CALL time -- the argument, then CHIAKI_FRAME_DUMP,
then DEFAULT_PATH -- and returns None under BASEBALL_TEST_RUN so the offline
suite can never be handed a frame by a chiaki that happens to be streaming
(frame_dump.dump_path / _test_run). A module-level knob captured in a `def`
line is CLAUDE.md 10.18's bug, and it is silent.

MEMORY. Each kept episode holds ONE full frame: at the dump's native
1920x1080 RGB that is ~6 MB, so the default keep=8 costs ~50 MB steady state.
That is the price of being able to answer "what did the reveal look like"
after the fact; lower `keep` if it ever matters.
"""
import threading
import time
from collections import deque

# HOW OFTEN THE THREAD LOOKS. 0.05 s is the sampler's own rate, and the rate
# the patched chiaki writes the dump at (framedump's min_interval_ms), so
# asking faster only re-reads frames already seen.
PERIOD = 0.05

# HOW LONG THE SCORE MUST STAY BELOW THRESHOLD BEFORE AN EPISODE IS CLOSED.
# A THRESHOLD BETWEEN TWO MEASURED POPULATIONS (CLAUDE.md 10.4), both counted
# over the whole 720 s trace: the statistic dips below the line INSIDE an
# episode as the cards animate, and the longest such dip is 0.41 s (only two
# dips over one sample period in 14 episodes); the shortest SILENCE between
# two consecutive episodes is 3.23 s, the rest 9.4-201 s. 1.0 s is 2.4x the
# longest dip and 3.2x under the shortest silence, so it can neither split one
# reveal in two nor glue two screens into one episode.
CLOSE_GAP = 1.0

# HOW MANY CLOSED EPISODES ARE KEPT. A match is ~10 turns and a lookup only
# ever wants the newest, so this is for the log and the post-mortem.
KEEP = 8

# READS WITH NO FRAME BEFORE THE ABSENCE IS LOGGED. One second at 20 Hz.
# `available` is already False before the first frame arrives, so this decides
# only when the watcher SAYS SO -- once, by name, instead of on every read.
PROBE_READS = 20

# ... AND HOW LONG WITHOUT A FRAME COUNTS AS THE DUMP HAVING DIED mid-match.
# Longer than PROBE_READS' second because by then frames HAVE been arriving,
# so a gap is more likely a hiccup than an absence.
STALE_AFTER = 5.0


class Episode:
    """One continuous run of frames whose score cleared the threshold.

    `frame` is the frame with the HIGHEST score seen so far, which is the one
    worth spending a vision call on: at the peak the cards are fully drawn.
    `closed` says whether the run has ended -- an episode is handed out as
    soon as it has a peak frame, so a caller that arrives mid-reveal is not
    made to wait for the animation to finish.
    """

    __slots__ = ("t_first", "t_last", "t_peak", "peak", "frame", "closed",
                 "samples")

    def __init__(self, t, score, frame):
        self.t_first = t
        self.t_last = t
        self.t_peak = t
        self.peak = score
        self.frame = frame
        self.closed = False
        self.samples = 1

    def duration(self):
        return self.t_last - self.t_first

    def snapshot(self):
        """An immutable copy, so a caller never reads a field the thread is
        halfway through updating."""
        e = Episode.__new__(Episode)
        e.t_first, e.t_last, e.t_peak = self.t_first, self.t_last, self.t_peak
        e.peak, e.frame, e.closed = self.peak, self.frame, self.closed
        e.samples = self.samples
        return e

    def __repr__(self):
        return (f"<Episode t_first={self.t_first:.2f} t_peak={self.t_peak:.2f} "
                f"peak={self.peak:.4f} dur={self.duration():.2f}s "
                f"{'closed' if self.closed else 'open'}>")


def _copy(img):
    """A frame the thread can keep while the reader goes on reading.

    `frame_dump.read_frame` already returns a fresh image per call, so this is
    belt and braces against a future reader that reuses a buffer -- and it is
    written to survive a fake with no `copy`, because the tests inject one.
    """
    try:
        return img.copy()
    except Exception:
        return img


class RevealWatcher:
    """Reads frames at ~20 Hz and segments them into reveal episodes.

    `read_frame()` -> a frame or None (None is a skip, never an error);
    `score(frame)` -> float. Both are injected: this module knows nothing
    about chiaki, orchestrator or the dump's path.
    """

    def __init__(self, read_frame, score, threshold, period=PERIOD,
                 close_gap=CLOSE_GAP, keep=KEEP, probe_reads=PROBE_READS,
                 stale_after=STALE_AFTER, log=None):
        self._read_frame = read_frame
        self._score = score
        self._threshold = float(threshold)
        self._period = float(period)
        self._close_gap = float(close_gap)
        self._probe_reads = int(probe_reads)
        self._stale_after = float(stale_after)
        # Where the log lines go, resolved at CALL time by _say() rather
        # than bound to `print` here, so a caller can redirect them later.
        self._log = log
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._episodes = deque(maxlen=int(keep))
        self._open = None
        self._reads = 0
        self._frames = 0
        self._misses = 0
        self._errors = 0
        self._closed_count = 0
        self._last_frame_at = 0.0
        self._unavailable = None
        self._said_unavailable = False

    # ---------------------------------------------------------------- lifecycle

    def start(self):
        """Start the daemon thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        with self._lock:
            # `available` stays False until a frame actually arrives; from
            # then on STALE_AFTER decides. PROBE_READS only sets the reason
            # that gets logged.
            self._last_frame_at = time.time()
            self._unavailable = None
            self._said_unavailable = False
        self._thread = threading.Thread(target=self._loop, name="reveal-watch",
                                        daemon=True)
        self._thread.start()
        self._say(f"[reveal] watcher started at {1.0 / self._period:.0f} Hz, "
                  f"threshold {self._threshold}, close gap {self._close_gap}s")
        return self

    def stop(self, timeout=2.0):
        """Stop the thread and wait for it to actually be gone.

        `is_alive()` before `join()` because Thread.join() RAISES on a thread
        that was never started, and stop() is called from run()'s `finally` --
        where a raise would replace whatever really ended the match with a
        threading error and lose the stop_reason with it.
        """
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout)
        self._thread = None
        return self

    @property
    def running(self):
        t = self._thread
        return t is not None and t.is_alive()

    @property
    def available(self):
        """Can this watcher see the stream right now?

        False means the caller should fall back to its own polling wait, and
        there are exactly four ways to get there: the thread is not running;
        a read RAISED before any frame arrived; no frame has EVER arrived; or
        the last one is older than `stale_after`. Four conditions, each with
        one reason, because a fallback that engages for an unnameable reason
        is a fallback nobody can debug -- and `stats()["unavailable"]` carries
        the reason in words for the log.
        """
        if not self.running:
            return False
        with self._lock:
            if self._unavailable is not None:
                return False
            if self._frames == 0:
                # NOTHING HAS EVER COME OUT OF THE DUMP, so there is nothing to
                # be available for -- and answering True here would be a real
                # hazard, not just an inaccuracy: a caller told "available"
                # blocks in episode_after() for its whole budget, which is the
                # 75 s wait this exists to remove. Live it costs nothing,
                # because the writer runs at 20 Hz and the first read lands
                # within ~50 ms of start(), long before the first play.
                return False
            return (time.time() - self._last_frame_at) < self._stale_after

    def stats(self):
        with self._lock:
            return {"reads": self._reads, "frames": self._frames,
                    "misses": self._misses, "errors": self._errors,
                    "episodes": self._closed_count,
                    "unavailable": self._unavailable}

    # ------------------------------------------------------------------ lookup

    def mark(self):
        """The clock the caller stamps its play with.

        A method rather than a bare `time.time()` so the mark and the
        episodes it is compared against can only ever come from the same
        clock.
        """
        return time.time()

    def episodes(self):
        """The closed episodes, oldest first."""
        with self._lock:
            return [e.snapshot() for e in self._episodes]

    def episode_after(self, t_mark, timeout, poll=0.05):
        """The first episode that BEGAN at or after `t_mark`, or None.

        Blocks up to `timeout` seconds. `t_first >= t_mark` is the whole
        guard against reading the PREVIOUS turn's reveal: an episode already
        under way when the card was committed belongs to the turn before and
        is never returned, however recent it is.

        Returns an episode as soon as it exists with a peak frame -- it does
        NOT wait for the episode to close. Waiting would add the close gap
        plus whatever is left of a 4-10 s animation to every turn that asks
        mid-reveal, and the peak-so-far is already past the face-down state
        that the threshold rejects. `closed` on the result says which case
        the caller got, so the live log can settle later whether waiting
        would have been worth it.

        IT ALSO GIVES UP THE MOMENT THE DUMP DIES. `available` is checked on
        every poll, not only at entry: a stream that stops mid-wait (chiaki
        crashing, the VPN reconnecting, the console freezing -- all of which
        this project has logged) leaves the caller waiting out a budget that
        nothing can satisfy any more, which is the 75 s wait this module
        exists to remove, wearing a different hat. Bailing hands the turn
        back to the poll, which reads through the CAPTURE path rather than
        the dump and may still see the reveal. Only a watcher that WAS
        available at entry can go unavailable in this sense, so a caller that
        starts waiting before the first frame is not cut off by it.
        """
        deadline = time.time() + float(timeout)
        entered_available = self.available
        while True:
            ep = self._first_after(t_mark)
            if ep is not None:
                return ep
            if time.time() >= deadline:
                return None
            self._stop.wait(poll)
            if not self.running:
                # The thread is gone; nothing new can arrive. Answer with
                # whatever is already recorded rather than sleeping out the
                # rest of the budget against a dead watcher.
                return self._first_after(t_mark)
            if entered_available and not self.available:
                # THE DUMP WENT QUIET WHILE WE WAITED. Same reasoning as the
                # branch above, and the caller can tell the two apart by
                # asking `available` itself.
                return self._first_after(t_mark)

    def _first_after(self, t_mark):
        with self._lock:
            for e in self._episodes:
                if e.t_first >= t_mark and e.frame is not None:
                    return e.snapshot()
            o = self._open
            if o is not None and o.t_first >= t_mark and o.frame is not None:
                return o.snapshot()
        return None

    # ------------------------------------------------------------------- thread

    def _loop(self):
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(self._period)
        # A run that ends mid-episode still publishes it, so the last turn of
        # a match is not lost to the shutdown.
        self._close_open(time.time(), reason="watcher stopped")

    def _tick(self, now=None):
        """One sample. Never raises: a watcher that dies on a bad frame is a
        guard that stops guarding exactly when the stream gets interesting."""
        now = time.time() if now is None else now
        try:
            img = self._read_frame()
        except Exception as e:
            self._note_error(e)
            return
        if img is None:
            self._note_miss()
            return
        try:
            s = float(self._score(img))
        except Exception as e:
            self._note_error(e)
            return
        with self._lock:
            self._reads += 1
            self._frames += 1
            self._last_frame_at = now
            self._unavailable = None
            self._said_unavailable = False
        if s >= self._threshold:
            self._extend(now, s, img)
        else:
            self._maybe_close(now)

    def _extend(self, now, s, img):
        with self._lock:
            o = self._open
            if o is None:
                self._open = Episode(now, s, _copy(img))
                return
            o.t_last = now
            o.samples += 1
            if s > o.peak:
                o.peak = s
                o.t_peak = now
                o.frame = _copy(img)

    def _maybe_close(self, now):
        with self._lock:
            o = self._open
            if o is None or (now - o.t_last) < self._close_gap:
                return
        self._close_open(now, reason="gap")

    def _close_open(self, now, reason=""):
        with self._lock:
            o = self._open
            if o is None:
                return
            o.closed = True
            self._open = None
            self._episodes.append(o)
            self._closed_count += 1
            snap = o.snapshot()
        self._say(f"[reveal] episode closed ({reason}): t_first={snap.t_first:.2f} "
                  f"t_peak={snap.t_peak:.2f} peak={snap.peak:.4f} "
                  f"duration={snap.duration():.2f}s samples={snap.samples}")

    def _note_error(self, e):
        say = None
        with self._lock:
            self._reads += 1
            self._errors += 1
            if self._frames == 0 and self._unavailable is None:
                # THE FIRST READ RAISED. Say so at once and let the caller
                # fall back; do not make a whole turn wait to find out.
                self._unavailable = f"read raised: {e!r}"
                if not self._said_unavailable:
                    self._said_unavailable = True
                    say = self._unavailable
        if say:
            self._say(f"[reveal] watcher unavailable -- {say}")

    def _note_miss(self):
        say = None
        with self._lock:
            self._reads += 1
            self._misses += 1
            if (self._frames == 0 and self._unavailable is None
                    and self._misses >= self._probe_reads):
                self._unavailable = (f"no frame from the dump in "
                                     f"{self._misses} reads")
                if not self._said_unavailable:
                    self._said_unavailable = True
                    say = self._unavailable
        if say:
            self._say(f"[reveal] watcher unavailable -- {say}")

    def _say(self, msg):
        """One log line. Resolved at CALL time, and never fatal.

        A watcher that died because its logger raised would take the reveal
        with it, and the log line is the live instrument -- it is how the
        next match says whether any of this worked.
        """
        fn = self._log
        try:
            if fn is None:
                print(msg, flush=True)
            else:
                fn(msg)
        except Exception:
            pass
'''

NEW_TEST = r'''"""The reveal WATCHER: episodes, the mark that separates turns, and the fallback.

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
'''

# ---------------------------------------------------------------- the edits

WATCH_BLOCK = '''

# --- THE REVEAL WATCHER: look all the time, instead of at the right moment --
#
# THE POLL ABOVE TIMED OUT ON 7 OF 7 TURNS of the live match on 2026-09-08,
# logging "peak edge 0.034-0.0535" every time. read_matchup_reveal() therefore
# never ran, the strategy got no reveal information at all, and every turn
# spent the full 75 seconds -- about six extra minutes on that match.
#
# The reveal was on screen. A 20 Hz sampler on chiaki's frame dump, scoring
# frames with THIS SAME center_card_edge_fraction, saw 1848 of 12678 samples
# at or above 0.065 over 720 seconds: 14 episodes, the eleven reveal-shaped
# ones 4.00-12.82 s long and peaking at 0.1036-0.1687, one about every 20-35 s
# (agent_progress/ocr-speed/reveal_sampler.py ->
# overnight/census/reveal_edge_20260908.jsonl, frames under
# overnight/census/reveal_edge_frames_20260908/). The 0.0535 the poll kept
# reporting as its peak is the FACE-DOWN pre-flip pair of card backs, which
# measures 0.050-0.054. So the poll was not looking during the flip.
#
# THE STATISTIC ALSO FIRES ON THE END-OF-ROUND LOSER SCREEN -- 0.0705-0.0764
# over 15 saved frames of it, against genuine reveals that reach down to
# 0.0729 in the census above this function, so the two OVERLAP and no cutoff
# separates them. The old poll was scoped to one turn's post-play window and
# this watcher is not, which is a real cost of looking all the time. It is
# bounded by the mark, not by a threshold: the round-result screen comes AFTER
# the reveal and BEFORE the next play, so the first episode after a play is
# the reveal unless that turn produced no episode at all -- a turn that had
# nothing before this patch either. reveal_cards feeds match_log.jsonl and
# nothing else.
#
# WHETHER IT STARTS LATE OR THE FLIP LANDS BETWEEN POLLS WAS NEVER
# ESTABLISHED, and this design makes the question irrelevant: a thread reading
# the dump at 20 Hz records every episode as it happens, and a turn asks
# afterwards for the episode that followed ITS OWN play. Nothing has to be
# looking at the right moment.
#
# THE THRESHOLD, THE REGION AND THE POLL ARE ALL UNCHANGED. The watcher scores
# frames with the same function against the same 0.065 -- re-measured on the
# four saved frames at both widths, reveals 0.1155-0.1278 and face-down
# 0.0491-0.0544 -- and wait_for_reveal_cards() is still what runs whenever the
# dump is not there.
REVEAL_WATCH_PERIOD = 0.05
REVEAL_WATCH_CLOSE_GAP = 1.0
REVEAL_WATCH_KEEP = 8
# The same budget the poll had, so a turn can never wait LONGER than before.
REVEAL_EPISODE_TIMEOUT = REVEAL_MAX_WAIT

_REVEAL_WATCHER = None


def start_reveal_watcher():
    """Start the background reveal watcher, or return None if it cannot run.

    Both imports are LAZY, so importing orchestrator costs nothing and a
    script that never plays a match never loads them.

    `frame_dump.read_frame` is passed as the reader WITH NO PATH: it resolves
    the dump at CALL time -- the argument, then CHIAKI_FRAME_DUMP, then
    DEFAULT_PATH -- and returns None under BASEBALL_TEST_RUN, which is what
    stops the offline suite from ever being handed a frame by a chiaki that
    happens to be streaming on this machine. A path captured here would be
    CLAUDE.md 10.18's bug, and it would be silent.
    """
    global _REVEAL_WATCHER
    if _REVEAL_WATCHER is not None:
        return _REVEAL_WATCHER
    if os.environ.get("BASEBALL_TEST_RUN"):
        # NO THREAD IN THE OFFLINE SUITE. frame_dump would hand it None on
        # every read anyway, but a daemon thread per run() test is noise the
        # suite does not need, and the flag is read HERE, at call time, never
        # captured at import (CLAUDE.md 5: tools/prompt_ocr_ab.py set it at
        # module level and silently disabled every stick send in a live
        # harness). It also keeps the fallback the state every existing run()
        # test exercises.
        return None
    try:
        import frame_dump
        import reveal_watch
        w = reveal_watch.RevealWatcher(
            frame_dump.read_frame, center_card_edge_fraction,
            REVEAL_EDGE_THRESHOLD, period=REVEAL_WATCH_PERIOD,
            close_gap=REVEAL_WATCH_CLOSE_GAP, keep=REVEAL_WATCH_KEEP)
        w.start()
    except Exception as e:
        # NEVER fatal. A match that cannot watch falls back to the poll it
        # always used; a match that cannot start is a $50 fee already paid.
        print(f"  [reveal] watcher could not start ({e}) -- falling back to "
              f"the {REVEAL_MAX_WAIT:.0f}s poll.")
        return None
    _REVEAL_WATCHER = w
    return w


def stop_reveal_watcher():
    """Stop the watcher and forget it. Safe when none is running."""
    global _REVEAL_WATCHER
    w, _REVEAL_WATCHER = _REVEAL_WATCHER, None
    if w is not None:
        try:
            w.stop()
        except Exception as e:
            print(f"  [reveal] watcher would not stop ({e}).")


def reveal_mark():
    """The clock a play is stamped with.

    Taken from the watcher when there is one, so the mark and the episodes it
    will be compared against can only ever come from the same clock.
    """
    w = _REVEAL_WATCHER
    return w.mark() if w is not None else time.time()


def reveal_frame_for(t_mark, timeout=None):
    """The frame to read this turn's reveal from, or None to capture fresh.

    Raises RuntimeError when no reveal was seen -- exactly the signal the
    polling wait gave, so the caller's `except` is unchanged.

    THE `available` CHECK IS THE WHOLE POINT OF THE FALLBACK. With no patched
    chiaki, no dump, or a dump that has stopped, this behaves as the code did
    before this patch -- and the offline suite is in precisely that state, so
    every existing run() test still exercises wait_for_reveal_cards().

    `timeout` is resolved at CALL time (CLAUDE.md 10.18): written
    `timeout=REVEAL_EPISODE_TIMEOUT`, the constant would be captured when this
    `def` ran and no later change to it could ever be seen.
    """
    w = _REVEAL_WATCHER
    if w is None or t_mark is None or not w.available:
        if not wait_for_reveal_cards():
            raise RuntimeError("reveal cards never appeared")
        return None
    budget = REVEAL_EPISODE_TIMEOUT if timeout is None else timeout
    t0 = time.time()
    ep = w.episode_after(t_mark, budget)
    waited = time.time() - t0
    if ep is None:
        left = budget - waited
        if not w.available and left > 1.0:
            # THE DUMP DIED WHILE WE WAITED, so episode_after gave up early
            # rather than idling out a budget nothing could satisfy. The poll
            # reads through _fast_grab -- the CAPTURE path, not the dump -- so
            # it may still see the reveal that the watcher can no longer see.
            #
            # IT GETS ONLY WHAT IS LEFT OF THE BUDGET. wait_for_reveal_cards
            # already takes max_wait, so nothing about that function changes,
            # and the turn can never wait longer in total than the
            # REVEAL_MAX_WAIT it waited before this patch existed. A fallback
            # that started a fresh 75 s clock would make the rare case slower
            # than the code it replaced, which is not a fallback, it is a
            # regression with a comment.
            print(f"  [reveal] the dump went quiet after {waited:.0f}s "
                  f"({w.stats()}) -- falling back to the poll for the "
                  f"{left:.0f}s left of the budget")
            if not wait_for_reveal_cards(max_wait=left):
                raise RuntimeError("reveal cards never appeared")
            return None
        # Deliberately the same SHAPE as the poll's timeout line above, so the
        # two are comparable turn for turn inside one log.
        print(f"  [reveal] no episode within {waited:.0f}s of the play vs "
              f"threshold {REVEAL_EDGE_THRESHOLD} -- {w.stats()}")
        raise RuntimeError("reveal cards never appeared")
    # THE DURATION IS IN THE LINE ON PURPOSE. The end-of-round LOSER screen
    # scores in the same band as a weak reveal and sits there for 20+ seconds,
    # where a reveal runs 4-13 s; peak and duration together are what make a
    # confounded row identifiable in the morning without a new threshold.
    print(f"  [reveal] episode t_first=+{ep.t_first - t_mark:.1f}s after the "
          f"play, peak {ep.peak:.4f}, {ep.duration():.1f}s long, waited "
          f"{waited:.1f}s" + ("" if ep.closed else " (still open)"))
    return ep.frame
'''

ENCODE_BLOCK = '''

def screenshot_b64_from_image(img) -> str:
    """Encode an image for the model EXACTLY as capture_screenshot_b64()
    encodes a fresh capture: the same SCREENSHOT_MAX_WIDTH downscale that
    capture_screenshot_image() applies, then the same JPEG at quality 85.

    It exists so read_matchup_reveal() can be handed the reveal watcher's peak
    frame -- taken from chiaki's dump at its native 1920x1080 -- without the
    model seeing a different KIND of image from the one every prompt in this
    file was calibrated against.
    """
    if img.width > SCREENSHOT_MAX_WIDTH:
        ratio = SCREENSHOT_MAX_WIDTH / img.width
        img = img.resize((SCREENSHOT_MAX_WIDTH, int(img.height * ratio)))
    return _encode_jpeg_b64(img)
'''

A_POLL_END = ('          f"({100.0 * peak / REVEAL_EDGE_THRESHOLD:.0f}% of the bar)")\n'
              '    return False\n')

A_ENCODE = ('def _encode_jpeg_b64(img) -> str:\n'
            '    buf = io.BytesIO()\n'
            '    img.convert("RGB").save(buf, format="JPEG", quality=85)\n'
            '    return base64.b64encode(buf.getvalue()).decode("utf-8")\n')

A_SIG = 'def read_matchup_reveal() -> list:'

A_DOC = ('''    this logging exists to investigate (caught by the user, 2026-08-24,
    reviewing the fix that first excluded tactics cards entirely).
    """
    img_b64 = capture_screenshot_b64()
''')

B_DOC = ('''    this logging exists to investigate (caught by the user, 2026-08-24,
    reviewing the fix that first excluded tactics cards entirely).

    `img` IS THE FRAME TO READ, and None means "take a fresh screenshot" --
    which is what every caller did before the reveal watcher existed. The
    watcher hands over the PEAK frame of the reveal episode, the moment the
    centre-edge statistic was highest and so the moment the cards are fully
    drawn. That is strictly better than whatever happens to be on screen by
    the time this runs: the reveal stays up 4-10 s and this call arrives
    somewhere inside that window, or after it has closed. The frame is encoded
    by screenshot_b64_from_image(), byte for byte the way
    capture_screenshot_b64() encodes its own capture.
    """
    img_b64 = (capture_screenshot_b64() if img is None
               else screenshot_b64_from_image(img))
''')

A_PLAY = ('    select_and_play(player_idx, tactics_idx)\n'
          '\n'
          '    matchup_info = {\n'
          '        "phase": state_json["phase"],\n')

B_PLAY = ('''    # THE REVEAL CLOCK STARTS ONE LINE BEFORE THE COMMIT, not after
    # play_one_turn returns. Everything after this press belongs to THIS
    # turn's reveal; an episode already under way when it is taken belongs to
    # the turn before, and reveal_frame_for() refuses that on `t_first >=
    # t_mark` alone. Taken BEFORE the press rather than after, so no part of
    # the flip can land in the gap between the two.
    _reveal_mark = reveal_mark()
    select_and_play(player_idx, tactics_idx)

    matchup_info = {
        # POPPED by run() before this dict can reach pending_matchup, so
        # match_log.jsonl is unaffected by patch60. It is a clock reading, not
        # a measurement of the turn, and it has no business in the dataset.
        "reveal_mark": _reveal_mark,
        "phase": state_json["phase"],
''')

A_TRY = '    try:\n        if log_screenshots:\n'

B_TRY = ('''    try:
        # THE REVEAL WATCHER runs for the length of the match loop and is
        # stopped in the finally below, for the same reason as the screenshot
        # logger: the loop exits through many paths, and a daemon thread that
        # outlives its run keeps reading the dump for the rest of the process.
        # Never fatal -- start_reveal_watcher() returns None when it cannot
        # run, and every turn then falls back to wait_for_reveal_cards().
        start_reveal_watcher()
        if log_screenshots:
''')

A_FIN = ('    finally:\n'
         '        if screenshot_stop is not None:\n'
         '            screenshot_stop.set()\n')

B_FIN = ('    finally:\n'
         '        stop_reveal_watcher()\n'
         '        if screenshot_stop is not None:\n'
         '            screenshot_stop.set()\n')

A_CALL = ('                            if not wait_for_reveal_cards():\n'
          '                                raise RuntimeError("reveal cards never appeared")\n'
          '                            reveal_cards = read_matchup_reveal()\n')

B_CALL = ('''                            # THE WATCHER'S EPISODE, NOT A POLL. The
                            # mark is POPPED, not read: it is a clock reading
                            # and must not travel on into match_log.jsonl
                            # through pending_matchup below.
                            # reveal_frame_for() raises the same RuntimeError
                            # the poll's timeout raised, and falls back to
                            # that poll whenever the watcher is unavailable --
                            # which is the state of every offline test and of
                            # any run without the patched chiaki.
                            _reveal_mark = matchup_info.pop("reveal_mark", None)
                            reveal_img = reveal_frame_for(_reveal_mark)
                            reveal_cards = read_matchup_reveal(img=reveal_img)
''')

edits = [
    (A_POLL_END, A_POLL_END + WATCH_BLOCK),
    (A_ENCODE, A_ENCODE + ENCODE_BLOCK),
    (A_SIG, 'def read_matchup_reveal(img=None) -> list:'),
    (A_DOC, B_DOC),
    (A_PLAY, B_PLAY),
    (A_TRY, B_TRY),
    (A_FIN, B_FIN),
    (A_CALL, B_CALL),
]

# ------------------------------------------- assert EVERYTHING, then write
#
# ONE assert block for all files, then all the writes. CLAUDE.md 10.19: a
# two-file patch that asserted-and-wrote the first file and then failed an
# anchor on the second left a live harness reading a half-patched tree
# mid-batch.
for a, b in edits:
    assert o.count(a) == 1, ("orchestrator anchor", a[:70], o.count(a))

assert not os.path.exists(M), f"{M} already exists"
assert not os.path.exists(T), f"{T} already exists"
assert os.path.isdir(os.path.dirname(T)), "tests/minigame/ must exist"
assert os.path.isdir(os.path.dirname(FIXDIR)), "test_fixtures/ must exist"
assert not os.path.isdir(FIXDIR), f"{FIXDIR} already exists"
assert os.path.isdir(SRCFRAMES), f"{SRCFRAMES} must exist (the sampler's frames)"
assert len(FRAMES) == 6 and len(set(FRAMES.values())) == 6, FRAMES
for src in FRAMES:
    p = os.path.join(SRCFRAMES, src)
    assert os.path.isfile(p), f"missing sampler frame {p}"
    # A 1920x1080 JPEG of a live frame; anything tiny is the wrong file.
    assert os.path.getsize(p) > 20000, (p, os.path.getsize(p))
assert os.path.isfile(os.path.join(ROOT, "frame_dump.py"))

# The state this patch assumes about orchestrator, before it touches it.
assert "reveal_watch" not in o
assert "_REVEAL_WATCHER" not in o
assert "reveal_frame_for" not in o
assert "screenshot_b64_from_image" not in o
assert o.count("REVEAL_EDGE_THRESHOLD = 0.065") == 1
assert o.count("REVEAL_CENTER_REGION = (0.42, 0.28, 0.58, 0.58)") == 1
assert o.count("REVEAL_MAX_WAIT = 75.0") == 1
assert o.count("SETTLE_CALIBRATION_WIDTH = 2000") == 1
assert o.count("SCREENSHOT_MAX_WIDTH = 2000") == 1
assert o.count("def wait_for_reveal_cards(") == 1
# The CALL SITE, at its own indent -- a bare "wait_for_reveal_cards()" also
# matches three comments and "read_matchup_reveal()" matches four, so a count
# on either would be a check on prose.
assert o.count("                            if not wait_for_reveal_cards():\n") == 1
assert o.count("                            reveal_cards = read_matchup_reveal()\n") == 1
assert o.count("pending_matchup = matchup_info") == 1
assert o.count("log_matchup({**pending_matchup") == 1
assert o.count("def play_one_turn(") == 1
assert o.count("def capture_screenshot_b64(") == 1

# The module and the test must parse before anything is written, and the
# module must be free of the two things it is forbidden to contain.
ast.parse(MODULE)
ast.parse(NEW_TEST)

# WHAT THE WATCHER MODULE IS ALLOWED TO IMPORT, checked on the AST rather than
# on substrings, because the docstring names frame_dump and tesserocr on
# purpose -- to say why neither is imported. Nothing on that thread may do OCR
# or spend a vision call: tesserocr links cysignals, whose sig_on/sig_off is
# process-global and MAIN-THREAD ONLY, and a worker-first call silently drops
# the whole process back to spawning subprocesses (CLAUDE.md 3). And importing
# orchestrator from here would be circular.
_mods = set()
for _n in ast.walk(ast.parse(MODULE)):
    if isinstance(_n, ast.Import):
        _mods.update(a.name.split(".")[0] for a in _n.names)
    elif isinstance(_n, ast.ImportFrom) and _n.module:
        _mods.add(_n.module.split(".")[0])
assert _mods == {"threading", "time", "collections"}, sorted(_mods)
assert MODULE.count("if s > o.peak:") == 1, "the peak rule moved"
assert MODULE.count("t_first >= t_mark") >= 2, "the mark guard moved"
# THE DUMP DYING MID-WAIT ends the wait (the fix round, finding 1). One read
# of `available` at entry, one test of it per poll.
assert MODULE.count("entered_available = self.available") == 1
assert MODULE.count("if entered_available and not self.available:") == 1
# ... and the grace period that keeps one dipping reveal as ONE episode.
assert MODULE.count("(now - o.t_last) < self._close_gap") == 1

for a, b in edits:
    o = o.replace(a, b)

ast.parse(o)

# ... and what the result must say, checked before it reaches disk.
assert o.count("def start_reveal_watcher():") == 1
# The guard, with its own first comment line, because orchestrator already
# had one BASEBALL_TEST_RUN gate at module scope and a bare count would
# read 2 and mean nothing.
assert o.count('    if os.environ.get("BASEBALL_TEST_RUN"):\n        # NO THREAD IN THE OFFLINE SUITE.') == 1
assert o.count("def stop_reveal_watcher():") == 1
assert o.count("def reveal_mark():") == 1
assert o.count("def reveal_frame_for(t_mark, timeout=None):") == 1
assert o.count("def screenshot_b64_from_image(img) -> str:") == 1
assert o.count("def read_matchup_reveal(img=None) -> list:") == 1
assert o.count("        start_reveal_watcher()\n") == 1
assert o.count("        stop_reveal_watcher()\n") == 1
assert o.count("    _reveal_mark = reveal_mark()\n") == 1
assert o.count('        "reveal_mark": _reveal_mark,\n') == 1
assert o.count('matchup_info.pop("reveal_mark", None)') == 1
assert o.count("reveal_img = reveal_frame_for(_reveal_mark)") == 1
assert o.count("reveal_cards = read_matchup_reveal(img=reveal_img)") == 1
# THE MID-WAIT FALLBACK gets only what is LEFT of the budget, so no turn can
# wait longer in total than the REVEAL_MAX_WAIT it waited before this patch.
# wait_for_reveal_cards itself is untouched -- max_wait is its own parameter.
assert o.count("if not wait_for_reveal_cards(max_wait=left):") == 1
assert o.count("        left = budget - waited\n") == 1
assert o.count("if not w.available and left > 1.0:") == 1
assert o.count("def wait_for_reveal_cards(max_wait: float = REVEAL_MAX_WAIT") == 1
# THE FALLBACK SURVIVES: wait_for_reveal_cards is untouched and is still
# called, from inside reveal_frame_for and nowhere else.
assert o.count("def wait_for_reveal_cards(") == 1
assert o.count("        if not wait_for_reveal_cards():\n") == 1
assert o.count("                            if not wait_for_reveal_cards():\n") == 0
assert o.count("                            reveal_cards = read_matchup_reveal()\n") == 0
# THREE, not two: the poll's own timeout, reveal_frame_for's "no episode",
# and the mid-wait fallback's timeout. The caller's `except` is unchanged
# because all three raise the same thing.
assert o.count('raise RuntimeError("reveal cards never appeared")') == 3
# THE MARK IS POPPED BEFORE THE DICT CAN BE LOGGED. Ordering, not presence:
# the key exists only between play_one_turn writing it and run() consuming it,
# and the pop sits ABOVE `pending_matchup = matchup_info` in the same
# straight-line block, which is the only route into log_matchup(). (Source
# order is the guarantee here BECAUSE both lines are in one linear block; the
# log_matchup call itself sits earlier in the file, on the previous turn's
# path, so its index says nothing and is deliberately not in this chain.)
assert (o.index('"reveal_mark": _reveal_mark,')
        < o.index('matchup_info.pop("reveal_mark", None)')
        < o.index("pending_matchup = matchup_info"))
assert o.count("log_matchup(") == 3, o.count("log_matchup(")  # def, the call, one comment
assert o.count("log_matchup({**pending_matchup") == 1
# ... and the mark is taken BEFORE the commit press, not after it.
assert (o.index("    _reveal_mark = reveal_mark()")
        < o.index("    select_and_play(player_idx, tactics_idx)"))
# THE START IS INSIDE THE TRY WHOSE FINALLY STOPS IT, so no exit path can
# leave the thread reading for the rest of the process.
assert (o.index("        start_reveal_watcher()")
        < o.index("        stop_reveal_watcher()"))
# NOTHING THIS PATCH IS NOT ABOUT MOVED.
assert o.count("REVEAL_EDGE_THRESHOLD = 0.065") == 1
assert o.count("REVEAL_CENTER_REGION = (0.42, 0.28, 0.58, 0.58)") == 1
assert o.count("REVEAL_MAX_WAIT = 75.0") == 1
assert o.count("SETTLE_CALIBRATION_WIDTH = 2000") == 1
assert o.count("_REVEAL_GRADIENT_CUTOFF = 28.0") == 1

os.makedirs(FIXDIR, exist_ok=True)
for src, dst in FRAMES.items():
    shutil.copy2(os.path.join(SRCFRAMES, src), os.path.join(FIXDIR, dst))
open(M, "w").write(MODULE)
open(T, "w").write(NEW_TEST)
open(O, "w").write(o)
print("patch60 applied to", ROOT)
print("  new module:", M)
print("  new test:  ", T)
print("  fixtures:  ", FIXDIR, "(%d frames: 2 reveal, 2 face-down, 2 LOSER)"
      % len(FRAMES))
print("  orchestrator: watcher started/stopped in run(), the mark taken before")
print("  the commit press and popped before the log, reveal_frame_for at the")
print("  one call site with wait_for_reveal_cards kept as the fallback")
