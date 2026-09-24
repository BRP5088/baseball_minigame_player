"""I-30: the "Give up?" dialog must be a RECOGNISED screen, not 15 failed polls.

WHAT HAPPENED, live, 2026-09-20 (overnight/run_live_20260920i.log, match 5, and the
crawl frame overnight/crawl/20260920_225626/001_before.png)
-----------------------------------------------------------------------------------
A player card OCR'd as "JOHNNY DRAWERS" scored a phantom draw at round 1, 0-0 (fixed
separately: local_state.read_result_card now matches a WHOLE WORD, and run()'s
early-result gate now requires the same result on two CONSECUTIVE frames at the
MIN_PLAYS_FOR_RESULT boundary -- see test_early_result_double_debit.py). Before
either of those landed, `close_result` was pressed FIVE TIMES at a live TURN screen
(see `_close_result_safely`), and the game answered with the "Give up?" dialog.
`read_state_for_turn()` has no branch for that dialog -- it is not a game screen the
local readers know -- so every poll raised, and the run burned all 15 "Couldn't read
the screen" retries and stopped with `unreadable_screens`, sitting one Cross away
from forfeiting a paid match until a human (the manager session) noticed the crawl
and pressed Circle by hand.

WHAT THIS FILE PINS
--------------------
When `read_state_for_turn()` raises WHILE a match is in progress, run() now checks
`reset_env.give_up_dialog()` on a fresh frame BEFORE counting the poll as one more
unreadable screen. If the dialog is up: press Circle ("moon" -- KEYMAP maps it to
backspace, the same physical button as close_result) exactly ONCE, look again to
confirm it cleared, and `continue` WITHOUT incrementing stuck_count. NEVER Cross --
Cross is YES, and answers "Give up?" by forfeiting the match.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import atexit
import os
import shutil
import tempfile
import time as _real_time

os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
_TMP = tempfile.mkdtemp(prefix="baseball-give-up-")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["BASEBALL_DIAGNOSTICS_DIR"] = _TMP
os.environ["BASEBALL_MATCH_LOG"] = os.path.join(_TMP, "match_log.jsonl")

import json                                                                  # noqa: E402

import orchestrator as o                                                     # noqa: E402
import reset_env                                                             # noqa: E402
from decision_engine import PlayerCard                                       # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


class _Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def sleep(self, n):
        self.now += n

    def time(self):
        return self.now

    def strftime(self, fmt, *a):
        return _real_time.strftime(fmt, *a)


GIVE_UP = object()   # sentinel: read_state_for_turn() raises on this poll


class Harness:
    """Drives the real orchestrator.run() against a scripted screen list.

    GIVE_UP entries make read_state_for_turn() raise, exactly like a screen the
    local readers cannot name. give_up_dialog() is scripted to answer True for the
    FIRST look at a GIVE_UP entry and False afterwards, so a single Circle press is
    enough to "clear" it -- matching the live shape (one press, one confirming look).
    """

    def __init__(self, screens, balance=500, match_in_progress=True):
        self.screens = list(screens)
        self.idx = 0
        self.presses = []
        self.give_up_looks = 0
        self.give_up_calls = []   # sequence number of each frame give_up_dialog() saw
        self._frame_seq = 0       # bumped on every captured frame -- proves freshness
        self._press_seq = None    # frame seq as of the moment Circle was pressed
        self.seed = {"wins": 0, "losses": 0, "draws": 0, "balance": balance,
                     "match_in_progress": match_in_progress}
        self.clock = _Clock()

    def _press(self, key, *a, **kw):
        self.presses.append(key)

    def _next_state(self):
        if self.idx < len(self.screens):
            s = self.screens[self.idx]
            self.idx += 1
        else:
            s = "other"
        if s is GIVE_UP:
            raise ValueError("LOCAL STATE GAP: UNRECOGNISED SCREEN -- the 'Give up?' "
                             "dialog is up, and no local reader names it")
        if isinstance(s, dict):
            return dict(s)
        return {"screen": s, "phase": "batting", "your_score": 0,
                "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}

    def _full_frame(self):
        # Every capture is tagged with a fresh, monotonically increasing sequence
        # number -- this is what lets _give_up_dialog answer from the FRAME it is
        # given rather than from a flag toggled elsewhere. A mutant that re-checks
        # a stale (already-seen) frame instead of taking a new capture hands back
        # an object whose tag does not advance, and that is exactly what the
        # freshness assertions below catch.
        from PIL import Image
        self._frame_seq += 1
        img = Image.new("RGB", (1920, 1080), (0, 0, 0))
        img._bb_seq = self._frame_seq
        return img

    def _give_up_dialog(self, img):
        # Answers from the frame's own sequence tag: True (dialog still up) for a
        # frame captured before the Circle press, False (dialog cleared) only for
        # a frame captured strictly AFTER it. A press with no fresh look afterward
        # -- i.e. the same frame object/tag reused -- reads as "still up", which is
        # what a re-read of the stale pre-press frame should mean.
        self.give_up_looks += 1
        seq = getattr(img, "_bb_seq", None)
        self.give_up_calls.append(seq)
        if self._press_seq is None:
            return True
        return seq is not None and seq <= self._press_seq

    def run(self, **kwargs):
        real_save = o.save_progress

        def fake_save(w, l, d, b, path=None, match_in_progress=False,
                      bans_done_this_match=False):
            real_save(w, l, d, b, path, match_in_progress=match_in_progress,
                      bans_done_this_match=bans_done_this_match)

        def _press_and_track(key, *a, **kw):
            self.presses.append(key)
            if key == "moon":
                self._press_seq = self._frame_seq

        patches = {
            "read_game_state": lambda *a, **k: self._next_state(),
            "read_state_for_turn": lambda *a, **k: self._next_state(),
            "screen_is_moving": lambda *a, **k: False,
            "_grab_settle_regions": lambda names: {n: self._full_frame() for n in names},
            "_safe_prompt_check": lambda *a, **k: None,
            "_fast_grab": lambda *a, **k: self._full_frame(),
            "_result_screen_up": lambda *a, **k: False,
            "_match_start_screen": lambda *a, **k: "prompt",
            "press": _press_and_track,
            "wait_for_screen_to_settle": lambda *a, **k: True,
            "wait_for_reveal_cards": lambda *a, **k: False,
            "read_matchup_reveal": lambda *a, **k: [],
            "play_one_turn": lambda *a, **k: (True, None),
            "read_full_ban_collection": lambda *a, **k: [
                (0, i, PlayerCard(f"Card {i}", 5 + i, 1)) for i in range(5)],
            "read_ban_counter": lambda *a, **k: 3,
            "_dealer_prompt_on_screen": lambda *a, **k: False,
            "capture_screenshot_image": lambda *a, **k: None,
            "select_bans_and_start_full": lambda *a, **k: None,
            "read_balance_from_pause_menu": lambda *a, **k: 500,
            "start_screenshot_logger": lambda *a, **k: None,
            "save_progress": fake_save,
            "time": self.clock,
        }
        saved = {name: getattr(o, name) for name in patches}
        for name, fn in patches.items():
            setattr(o, name, fn)

        import input_controller as _ic
        _ic_press = _ic.press
        _ic.press = _press_and_track

        # press_verified sleeps for real through input_controller's OWN `time`;
        # `patches["time"]` above only swaps ORCHESTRATOR's `time`.
        _ic_sleep = _ic.time.sleep
        _ic.time.sleep = lambda *a, **k: None

        saved_gud = reset_env.give_up_dialog
        reset_env.give_up_dialog = self._give_up_dialog

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
            _ic.press = _ic_press
            _ic.time.sleep = _ic_sleep
            reset_env.give_up_dialog = saved_gud
            os.unlink(path)


# --- the dialog is recognised, answered NO once, and the run continues -----------
h = Harness([GIVE_UP, "turn", "turn"], match_in_progress=True)
final = h.run(target_wins=99, max_spend=500)
check(h.presses.count("moon") == 1,
      f"the Give-up dialog must be answered with exactly ONE Circle ('moon') press; "
      f"got {h.presses.count('moon')} (presses: {h.presses})")
check("cross" not in h.presses,
      f"Cross must NEVER be pressed at the Give-up dialog -- it answers YES and "
      f"forfeits a paid match; presses: {h.presses}")
check(h.give_up_looks >= 2,
      f"the dialog must be looked at again after the press, to confirm it cleared "
      f"(before-press + after-press); only {h.give_up_looks} look(s) were made")
# Exactly two captures for one give-up event: the pre-press look and the
# post-press confirm. Anything else means the handling took more or fewer
# fresh looks than the recipe calls for.
check(len(h.give_up_calls) == 2,
      f"expected exactly 2 give_up_dialog() captures for one give-up event "
      f"(fresh look before the press, fresh look after); got {h.give_up_calls}")
# The mutant this pins: orchestrator.py re-reading the STALE pre-press frame
# (_gu_img) for the post-press confirm instead of taking a fresh _fast_grab().
# A reused frame's sequence tag does not advance, so the second call's tag
# would equal (never exceed) the first's -- catch that here, not by inferring
# it from run()'s behaviour, which presses "moon" and continues either way.
if len(h.give_up_calls) == 2:
    pre_seq, post_seq = h.give_up_calls
    check(post_seq is not None and pre_seq is not None and post_seq > pre_seq,
          f"the post-press confirm read a STALE frame -- its capture sequence "
          f"({post_seq!r}) did not advance past the pre-press look's ({pre_seq!r}). "
          f"orchestrator.py must take a fresh _fast_grab() for the post-press "
          f"give_up_dialog() check, not reuse the frame captured before Circle "
          f"was pressed")
check(final["match_in_progress"] is True,
      "answering the Give-up dialog's NO must not itself end the match — "
      f"match_in_progress={final['match_in_progress']!r}")

# --- it must not count toward the 15-poll unreadable-screen budget ---------------
# A run that hits the give-up dialog and then genuinely cannot read the screen
# afterward should still get its FULL MAX_STUCK_ATTEMPTS budget for that separate
# problem -- the dialog's own poll(s) must not have eaten into it.
h2 = Harness([GIVE_UP] + ["other"] * (o.MAX_STUCK_ATTEMPTS), match_in_progress=True)
final2 = h2.run(target_wins=99, max_spend=500)
check(h2.presses.count("moon") == 1,
      f"expected exactly one Circle press before the unreadable-screen budget took "
      f"over; got {h2.presses.count('moon')}")
# "other" is a RECOGNISED screen (not a read failure), so it does not touch
# stuck_count either -- this scenario is here to show the give-up handling does not
# ITSELF ever reach MAX_STUCK_ATTEMPTS, not to exercise that budget's own accounting.
check(final2["match_in_progress"] is True,
      f"match_in_progress was disturbed by the give-up recognition path: "
      f"{final2['match_in_progress']!r}")

# --- CONTROL: no match in progress -> the dialog check is skipped ----------------
# give_up_dialog() cannot fire with no match running (CLAUDE.md: the dialog only
# exists mid-match), so the check must not even look when match_in_progress is
# False -- otherwise a plain unreadable screen between matches would pay for an
# OCR call and a press for nothing.
h3 = Harness([GIVE_UP, "other"], match_in_progress=False, balance=500)
final3 = h3.run(target_wins=99, max_spend=500)
check(h3.give_up_looks == 0,
      f"with no match in progress, give_up_dialog() must not be consulted at all; "
      f"it was looked at {h3.give_up_looks} time(s)")
check("moon" not in h3.presses,
      f"with no match in progress, Circle must not be pressed; presses: {h3.presses}")


for f in failures:
    print(f"FAIL: {f}")
print(f"{len(failures)} give-up dialog recognition failure(s)"
      if failures else "give-up dialog recognition: all checks passed")
_sys.exit(1 if failures else 0)
