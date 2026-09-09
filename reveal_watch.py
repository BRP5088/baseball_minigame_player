"""Watch chiaki's frame dump for the faceoff REVEAL, in the background.

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

        Returns an episode once its peak has STOPPED RISING -- no new maximum
        for PEAK_SETTLE_SEC -- or once it has closed, whichever comes first.
        It does not wait out the whole 4-10 s animation.

        WHY NOT THE FIRST FRAME. That is what this did until 2026-09-08, and
        measured live it handed over the first frame above the threshold on 8
        of 8 turns (peaks 0.066-0.096) while those same episodes went on to
        peak at 0.077-0.166 a median 0.63 s later. The three reveal misreads
        of that match -- two "intended card absent", one "no OPPONENT card
        identified" -- were all such frames: the cards mid-flip. `closed` on
        the result still says which case the caller got.

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
            try:
                import event_log
                event_log.log_event("reveal_episode", t_first=o.t_first, t_peak=o.t_peak,
                                    t_last=o.t_last, peak=o.peak,
                                    peak_seq=(o.frame.info.get("dump_seq") if o.frame is not None else None))
            except Exception:
                pass
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
