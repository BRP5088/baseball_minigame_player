"""Shared scaffolding for the run() state-machine tests.

WHY THIS EXISTS
---------------
run() was the largest untested function in the project and the only one that
can permanently corrupt progress.json or debit a real $50 match fee. Every
guard in it (C1, C2, C3, N2, N3, N5, N25) was added in response to a QA finding
about a real double-action, and none of them had a regression test — the
existing suite tests readers, geometry and thresholds, never the state machine
that acts on them.

The whole loop is driven here by a SCRIPTED SCREEN SEQUENCE with every external
call faked, so these tests need no game, no API key, no screenshots and no PS5.
Nothing here can send a keypress: `press` is replaced by a recorder before run()
is ever called, and the test asserts on what it recorded.

The shape of every test is the same: feed a screen sequence that reproduces the
exact failure the guard was written for (typically "the screen did not dismiss,
so the loop sees it twice"), then assert the irreversible action happened
EXACTLY ONCE.

WHY IT IS A SEPARATE FILE
-------------------------
It used to be the head of one 1368-line test_run_state_machine.py holding 59
harnesses and 87 checks. run_tests.sh parallelises across FILES, so that one
file was a serial floor for the whole suite: ~213s idle, and past the 900s
ceiling on a loaded machine, while run_tests.sh's own per-test alarm is 300s.
A test that is killed before it finishes proves nothing.

The checks now live in three files grouped by concern — test_run_debit_and_
scoring.py, test_run_motion_gate.py and test_run_resume_and_persist.py — and
every one of them imports this module. ONE copy, deliberately: three
copy-pasted harnesses would drift, and a fixture that drifts is how a detector
test ends up passing on the wrong frames.

IT MUST NOT BE NAMED test_*.py. run_tests.sh finds tests with
`find tests -name 'test_*.py'` and would execute this file as a test; it
contains no checks, so it would report PASS forever while guarding nothing.
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


import glob
import json
import os
import shutil
import tempfile
import time as _real_time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
# Every stall path is exercised below, and each writes a diagnostic bundle.
# Send them to a temp dir: the real one is watched during a live session, and
# burying one genuine stall under twenty synthetic ones defeats the point of
# having the alert at all.
_DIAGTMP = tempfile.mkdtemp(prefix="baseball-diag-test-")
os.environ["BASEBALL_DIAGNOSTICS_DIR"] = _DIAGTMP
# Same reason: the misfire/reveal tests drive real plays, which append to the
# match log. Without this they contaminate the dataset the project exists to
# collect, with rows that look genuine.
# run_tests.sh exports this, but these files are also run directly (and by
# tests/harness/test_no_side_effects.py). It is what holds every input path
# OFF, so it is set here rather than left to the caller — and it must land
# BEFORE orchestrator is imported, like the two redirects above.
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ["BASEBALL_MATCH_LOG"] = os.path.join(_DIAGTMP, "match_log.jsonl")
# Same reason, same failure: an unredirected sink appends test rows to a real dataset
# in the project root, where test_no_side_effects would catch it only after the fact.
os.environ["BASEBALL_DEAL_LOG"] = os.path.join(_DIAGTMP, "deal_timing.jsonl")
import orchestrator
import orchestrator as o
from decision_engine import PlayerCard

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


class _Clock:
    """Virtual clock. orchestrator does `import time`, so swapping the module
    attribute lets a test advance time without spending any.

    It has to be VIRTUAL, not just sleep-free. MAX_CONTINUOUS_MOTION_WAIT is 20
    real seconds, and a busy `continue` loop runs ~3M iterations/sec — so with a
    real clock the bound is unreachable in any sane test, and an earlier version
    of the timeout test "passed" only because the scripted motion list ran out
    first. That asserted nothing. Here every motion check advances the clock by
    what one really costs (~0.2s), so the bound is reached in ~100 iterations."""

    def __init__(self):
        self.now = 1_000_000.0

    def sleep(self, n):
        self.now += n

    def time(self):
        return self.now

    def advance(self, n):
        self.now += n

    # Delegated: the clock stands in for the whole `time` module, and
    # orchestrator uses strftime for observation and diagnostic timestamps.
    # Only sleep/time need to be virtual.
    def strftime(self, fmt, *a):
        return _real_time.strftime(fmt, *a)

    # Delegated for the same reason: a kept frame's FILENAME carries a wall-clock
    # stamp (record_reveal_kind writes `<kind>_<ns>.jpg`), which is an identity, not
    # a duration. Missing, it raised AttributeError inside that function's own
    # never-raises `except` and wrote nothing -- indistinguishable from "this turn
    # played no tactics card", which is what the test was asserting about (10.1).
    def time_ns(self):
        return _real_time.time_ns()


class Harness:
    """Runs orchestrator.run() against a scripted list of screens.

    Anything that would touch the game, the network, or the real progress file
    is replaced. `screens` is consumed one entry per loop iteration; when it is
    exhausted the harness yields "other" forever, which run() counts toward
    MAX_STUCK_ATTEMPTS and then breaks on — so every test terminates without
    relying on the loop reaching its win target.
    """

    def __init__(self, screens, play_results=None, balance=500,
                 wins=0, losses=0, draws=0, logger_stop=None, motion=None,
                 revealed=None, opp_local=None, frozen=False, ban_counter=3,
                 ban_collection=None, ban_cursor=None):
        self.screens = list(screens)
        self.idx = 0
        # Each entry is play_one_turn()'s (played, matchup_info) return.
        self.play_results = list(play_results or [])
        self.play_idx = 0
        self.presses = []
        self.bans_submitted = []
        self.seed = {"wins": wins, "losses": losses, "draws": draws,
                     "balance": balance}
        self.saves = []
        # What start_screenshot_logger() returns. None for every test except
        # the N5 one, which needs to observe the stop event.
        self.logger_stop = logger_stop
        # Motion gate ("no action needed"). A list of bools consumed one per
        # loop iteration; when exhausted the screen is treated as still. Left
        # empty by default so existing tests see a still screen — otherwise
        # they would consult the REAL display and depend on whatever is on it.
        self.motion = list(motion or [])
        self.motion_idx = 0
        self.motion_checks = 0
        # Motion checks spent immediately BEFORE each vision read, i.e. the
        # length of each continuous run of motion. MAX_CONTINUOUS_MOTION_WAIT
        # bounds ONE such run — motion_wait_started is cleared after every
        # fall-through — so a run TOTAL is not a measurement of the bound, it
        # is the bound times however many screens the script happens to have.
        self.checks_per_read = []
        self._checks_at_last_read = 0
        self.clock = _Clock()
        # What read_matchup_reveal() returns. None = reveal never fires, which
        # is the default for tests that don't care about the matchup path.
        self.revealed = revealed
        # What opponent_from_reveal() returns: {opp_power, opp_tactics_bonus,
        # opp_tactics_kind} or None. See the stub table below for why it exists.
        self.opp_local = opp_local
        # Frozen stream: every captured frame byte-identical, which is what a
        # stalled Chiaki stream / sleeping PS5 looks like to the loop.
        self.frozen = frozen
        self.frames_grabbed = 0
        # What read_ban_counter() reports after bans are submitted. Defaults to
        # a full set; the B1 test sets it short.
        self.ban_counter = ban_counter
        self.dealer_prompt = False
        # What read_full_ban_collection() returns. Default is 5 DISTINCT cards
        # at 5 distinct positions — a grid so clean that none of the three
        # ban-set integrity guards can ever fire, which is why all three were
        # deletable with the suite green (QA, 2026-08-26).
        self.ban_collection = ban_collection
        # What ban_cursor_absolute() reports -- the SENSOR the verified ban
        # navigator steers by. None means "the cursor cannot be read", which is
        # the truth in an offline harness: there is no screen. run() probes it
        # and falls back to the dead-reckoned submitter, which is the seam these
        # files have always patched. Left unstubbed, the real reader grabs the
        # user's DESKTOP 14 times per target and then places no bans at all.
        self.ban_cursor = ban_cursor

    def _next_state(self):
        self.checks_per_read.append(self.motion_checks - self._checks_at_last_read)
        self._checks_at_last_read = self.motion_checks
        if self.idx < len(self.screens):
            s = self.screens[self.idx]
            self.idx += 1
        else:
            s = "other"
        if isinstance(s, dict):
            return dict(s)
        # Minimal well-formed payload; branches that need more get a dict.
        return {"screen": s, "phase": "batting", "your_score": 0,
                "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}

    def _frame_bytes(self):
        """Stand-in for a captured crop, feeding the frame-identity guard.

        Returns a DIFFERENT image each poll by default so ordinary tests look
        like a live screen. This MUST be patched: unpatched, the guard reads the
        real desktop, which genuinely IS byte-identical between polls, and every
        long test trips the frozen-stream bound at poll 13."""
        from PIL import Image as _Im
        self.frames_grabbed += 1
        return _Im.new("L", (4, 4), 7 if self.frozen else self.frames_grabbed % 251)

    def _full_frame(self):
        """A blank frame at real capture geometry, for local_game_state's _fast_grab.

        Blank on purpose: every local reader should answer "nothing here" on it, which
        is the honest scripted state. The harness scripts SCREENS through
        read_game_state; it must never be the case that what the readers see depends
        on the machine the suite runs on.
        """
        from PIL import Image as _Im
        return _Im.new("RGB", (1920, 1080), (0, 0, 0))

    def _screen_is_moving(self, *a, **k):
        self.motion_checks += 1
        # A real motion check costs two grabs plus the settle pause.
        self.clock.advance(0.2)
        if self.motion_idx < len(self.motion):
            m = self.motion[self.motion_idx]
            self.motion_idx += 1
            return m
        return False

    def _submit_bans(self, grid, positions, before_confirm=None):
        """Stand-in for the real ban submitter.

        It MUST invoke before_confirm: that hook is where the counter is read
        now, while the ban screen is still up. A stub that ignored it would
        leave the whole verification path untested while the B1 test kept
        passing — the counter would simply never be read at all.
        """
        self.bans_submitted.append(sorted(positions))
        if before_confirm is not None:
            before_confirm()

    def _play_one_turn(self, state_json, turns_this_half):
        if self.play_idx < len(self.play_results):
            r = self.play_results[self.play_idx]
            self.play_idx += 1
        else:
            r = (True, None)
        if isinstance(r, Exception):
            raise r
        return r

    def run(self, **kwargs):
        o = orchestrator
        saved = {}
        card = PlayerCard("Test Card", 5, 2)

        def fake_save(w, l, d, b, path=None, match_in_progress=False,
                      bans_done_this_match=False):
            self.saves.append((w, l, d, b, match_in_progress))
            _real_save(w, l, d, b, path, match_in_progress=match_in_progress,
                       bans_done_this_match=bans_done_this_match)

        _real_save = o.save_progress
        patches = {
            # run()'s loop reads state through read_state_for_turn -- the paid model once
            # per cycle, the local readers every turn after. Both seams are scripted, so
            # these files keep pinning run()'s own logic rather than which reader answered;
            # leaving read_state_for_turn live would have the local readers grab the real
            # desktop.
            "read_game_state": lambda *a, **k: self._next_state(),
            "read_state_for_turn": lambda *a, **k: self._next_state(),
            "screen_is_moving": self._screen_is_moving,
            "_grab_settle_regions": lambda names: {n: self._frame_bytes() for n in names},
            # OVERNIGHT_AUDIT: unpatched, this took a REAL screenshot of the
            # desktop on every poll — 1,423 of them, 94.9% of this file's
            # runtime. It is an audit-only signal that drives nothing, so the
            # harness has no reason to exercise the real capture path, and a
            # test suite should not be photographing the user's screen.
            "_safe_prompt_check": lambda *a, **k: None,
            # AND local_game_state's OWN capture, for the same reason and with a
            # sharper cost. `_fast_grab()` was NOT stubbed, so every frozen-stream
            # probe in this harness photographed the REAL chiaki window.
            #
            # That was inert for as long as the readers failed on whatever was up:
            # at HEAD, read_result's template bank scores a live screen below
            # RESULT_MIN and answers "not a result", so the leak changed nothing and
            # nobody noticed it.
            #
            # It stopped being inert on 2026-09-20. A result-CARD reader landed, the
            # console happened to be sitting on a finished match's "DEFEAT!" screen,
            # and this harness read it 13 times: local_game_state returned a real
            # result, run() took the result path instead of the turn path,
            # _screen_is_moving was never called, the VIRTUAL CLOCK (which only
            # advances inside it) stopped, and the frozen-stream bound could not fire.
            # test_run_motion_gate then failed with "2001 polls" -- an offline test
            # whose verdict depended on what was on the user's television.
            #
            # A blank frame at the real capture geometry, not the 4x4 the region stub
            # uses: read_result needs RESULT_MIN_FRAME_W (384) before it will score at
            # all, so a tiny frame would take the "too small" branch and exercise a
            # path production never takes.
            "_fast_grab": lambda *a, **k: self._full_frame(),
            "press": lambda k, *a, **kw: self.presses.append(k),
            "wait_for_screen_to_settle": lambda *a, **k: True,
            "wait_for_reveal_cards": lambda *a, **k: self.revealed is not None,
            "read_matchup_reveal": lambda *a, **k: list(self.revealed or []),
            # THE PAID STUB ABOVE IS NEVER CALLED, and that is not a harness bug.
            # run() wraps it in `if paid_model_allowed() else []`, and the paid
            # model has been OFF since 2026-09-12 -- so every test here has been
            # driving a branch production no longer takes. The opponent now comes
            # from opponent_from_reveal(), read LOCALLY off the reveal frame.
            #
            # Defaults to None, which is what the real function returns on the
            # harness's blank frame, so this stub changes NOTHING for a test that
            # does not set `opp_local`. A test that wants a loggable turn sets it.
            "opponent_from_reveal": lambda *a, **k: self.opp_local,
            "play_one_turn": self._play_one_turn,
            "read_full_ban_collection": lambda *a, **k: (
                list(self.ban_collection) if self.ban_collection is not None
                else [(0, i, PlayerCard(f"Card {i}", 5 + i, 1)) for i in range(5)]),
            "read_ban_counter": lambda *a, **k: self.ban_counter,
            # "Is the dealer's Play ($50) prompt on screen?" — proof no match
            # is running. False by default, the conservative setting: every
            # existing scenario scripts a live match and so stays on the
            # no-retry path QA1-F1 protects.
            "_dealer_prompt_on_screen": lambda *a, **k: self.dealer_prompt,
            "capture_screenshot_image": lambda *a, **k: None,
            "select_bans_and_start_full": self._submit_bans,
            "ban_cursor_absolute": lambda *a, **k: self.ban_cursor,
            "read_balance_from_pause_menu": lambda *a, **k: 500,
            "start_screenshot_logger": lambda *a, **k: self.logger_stop,
            "save_progress": fake_save,
            "time": self.clock,
        }
        for name, fn in patches.items():
            saved[name] = getattr(o, name)
            setattr(o, name, fn)

        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w") as f:
            json.dump(self.seed, f)
        try:
            o.run(progress_file=path, **kwargs)
            with open(path) as f:
                return json.load(f)
        finally:
            for name, fn in saved.items():
                setattr(o, name, fn)
            os.unlink(path)


RESULT_WIN = {"screen": "result", "phase": "batting", "your_score": 7,
              "opp_score": 3, "result_won": True, "hand": [], "runners": [],
              "discards_left": 2}
RESULT_LOSS = dict(RESULT_WIN, your_score=2, opp_score=9, result_won=False)
RESULT_DRAW = dict(RESULT_WIN, your_score=4, opp_score=4, result_won=False)

# A "result" screen is only BELIEVED once the match has plausibly finished,
# and there are exactly two ways to get there. Both are exercised below:
#
#   * MIN_PLAYS_FOR_RESULT cards have been played this match  -> scores at once
#   * the same result screen survives RESULT_CONFIRM_READS re-reads -> scores
#
# Until 2026-09-05 the confirm gate also required the scoreboard to read 0-0,
# so any non-zero result scored on its FIRST poll and most sequences in this
# file could end `..., RESULT_WIN]`. That clause was removed because it made
# the guard inert exactly when it was needed (mid-match the score is normally
# not 0-0). Consequence for these tests, and it is a REAL consequence of the
# fix rather than a testing artefact: a scripted match must now either play
# its way past the threshold or hold the overlay up long enough to confirm.
#
# Which of the two a test uses is deliberate. A test about the confirm gate
# itself repeats the overlay; a test about some OTHER guard plays a match, so
# that it stays independent of RESULT_CONFIRM_READS.
_PLAYED = ["turn"] * o.MIN_PLAYS_FOR_RESULT
_CONFIRM = o.RESULT_CONFIRM_READS
