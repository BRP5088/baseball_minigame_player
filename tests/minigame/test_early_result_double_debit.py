"""One misread "result" mid-match must not re-arm the $50 debit.

WHAT WAS WRONG
--------------
The early-result confirmation gate in run() carried an extra clause:

    if (plays_this_match < MIN_PLAYS_FOR_RESULT and _scores_all_zero
            and unconfirmed_result_reads < RESULT_CONFIRM_READS):

`_scores_all_zero` was written in because the one live observation that
motivated the gate (2026-08-31, "Draw logged" after a single card) happened to
show 0-0. But nothing in the gate's reasoning is about the SCORE — it is about
how far into the match we are. Mid-match the scoreboard is normally NOT 0-0, so
the clause switched the gate OFF for the whole window it was built to cover.
An AND that is false in the common case is not a narrower guard, it is an
absent one — the §10 rule-1 shape: the code did nothing, and doing nothing
looked exactly like working.

The cost, reproduced offline against the real run() loop:

    screens [match_start_prompt, turn, RESULT 7-3, match_start_prompt]
    saves   (0,0,0,450,True)
            (1,0,0,450,False)    <- fabricated win, match_in_progress cleared
            (1,0,0,400,True)     <- SECOND $50 for the same match
    start_match presses: 2

Three harms from one misread frame: $100 charged for one match, a win that
never happened written into the permanent record, and two `\\` keystrokes fired
into a live match — start_match shares its key with confirm_discard, which is
the exact 2026-08-25 harm.

match_in_progress is the ONLY thing guard C5 has to go on, so a fabricated
result hands the next transition-overlay misread a clean debit.

WHAT THIS FILE PINS
-------------------
That a non-zero "result" seen too early is CONFIRMED before it is believed, and
that confirming it costs nothing real: a genuine finish still scores exactly
once, two genuine matches still cost exactly $100, and a result that keeps
saying the same thing still scores rather than hanging the loop.

I-30 UPDATE, 2026-09-20 — THE ROUND-4/5 HOLE THIS FILE USED TO PIN IS CLOSED
-----------------------------------------------------------------------------
A player card OCR'd as "JOHNNY DRAWERS" (a batter's name) scored a phantom
DRAW at round 1, 0-0 -- plays_this_match was exactly MIN_PLAYS_FOR_RESULT (4),
which is the boundary this file's "positive control" scenarios deliberately
placed OUTSIDE the confirm-gate ("a finish at or past MIN_PLAYS_FOR_RESULT
must score on the first sighting, with no confirmation delay"). That is
exactly the hole: plays_this_match == MIN_PLAYS_FOR_RESULT was treated as far
enough into the match to trust a single frame, and it is not -- a match is 5
rounds A SIDE, so 4 plays is still the first half.

Fixed with no new numeric threshold beyond "two consecutive frames": AT
EXACTLY plays_this_match == MIN_PLAYS_FOR_RESULT, a "result" screen must be
read as the SAME (outcome, your_score, opp_score) on the very next poll too
before it scores -- see `last_result_read` in run(). It is cleared the moment
any non-"result" screen is seen, so the two reads must be genuinely
back-to-back, which is exactly what the live misread was not: the next poll
read a turn screen. A genuine finish's banner holds for several seconds
(CLAUDE.md: "sits fully opaque for a measured 4.0s at its shortest"), so this
costs one extra poll for a real finish and refuses a one-frame fluke.

WHAT IT STILL DOES NOT COVER
-----------------------------
The boundary check only fires AT plays_this_match == MIN_PLAYS_FOR_RESULT.
Past it (5, 6, ... plays -- still short of a real match's 10) a "result" still
scores on the first sighting with no confirmation, same as always. Closing
THAT needs positive evidence that no match is running before a debit
(_dealer_prompt_on_screen), which is instrumented in run() as audit output and
deliberately NOT wired in — see the comment at the debit.
"""

import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import json
import os
import tempfile
import time as _real_time

os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
# Stall paths below dump diagnostic bundles and the play path appends to the
# match log. Both go to a temp dir: a real stall alert buried under synthetic
# ones is worthless, and a synthetic row in match_log.jsonl looks genuine.
_TMP = tempfile.mkdtemp(prefix="baseball-early-result-")
os.environ["BASEBALL_DIAGNOSTICS_DIR"] = _TMP
os.environ["BASEBALL_MATCH_LOG"] = os.path.join(_TMP, "match_log.jsonl")

import orchestrator as o
from decision_engine import PlayerCard

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


class _Clock:
    """Virtual clock. orchestrator does `import time`, so swapping the module
    attribute lets these scenarios run without spending any."""

    def __init__(self):
        self.now = 1_000_000.0

    def sleep(self, n):
        self.now += n

    def time(self):
        return self.now

    def strftime(self, fmt, *a):
        return _real_time.strftime(fmt, *a)


class Harness:
    """Drives the real orchestrator.run() against a scripted screen list.

    Everything that would touch the game, the network or the real progress file
    is replaced, so nothing here can send a keypress or spend an API call.
    When the script runs out the harness yields "other" forever, which run()
    counts toward MAX_STUCK_ATTEMPTS and then breaks on — so every scenario
    terminates without relying on reaching a win target.
    """

    def __init__(self, screens, balance=500, match_in_progress=False):
        self.screens = list(screens)
        self.idx = 0
        self.presses = []
        self.saves = []
        self.seed = {"wins": 0, "losses": 0, "draws": 0, "balance": balance,
                     "match_in_progress": match_in_progress}
        self.frames = 0
        self.clock = _Clock()
        # I-11: close_result and start_match go through press_verified, which
        # LOOKS after every press. Per POLL, because press_verified runs inside
        # one iteration -- see _run_harness, which has the same pair.
        self.landed = set()

    def _press(self, key, *a, **kw):
        self.presses.append(key)
        self.landed.add(key)          # this file simulates no dropped presses

    def _next_state(self):
        self.landed.clear()
        if self.idx < len(self.screens):
            s = self.screens[self.idx]
            self.idx += 1
        else:
            s = "other"
        if isinstance(s, dict):
            return dict(s)
        return {"screen": s, "phase": "batting", "your_score": 0,
                "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}

    def _frame_bytes(self):
        # A DIFFERENT image each poll: unpatched this reads the real desktop,
        # which genuinely is byte-identical between polls, and every scenario
        # would trip the frozen-stream bound instead of the branch under test.
        from PIL import Image
        self.frames += 1
        return Image.new("L", (4, 4), self.frames % 251)

    def _full_frame(self):
        """A blank frame at real capture geometry, standing in for _fast_grab."""
        from PIL import Image
        return Image.new("RGB", (1920, 1080), (0, 0, 0))

    def run(self, **kwargs):
        real_save = o.save_progress

        def fake_save(w, l, d, b, path=None, match_in_progress=False,
                      bans_done_this_match=False):
            self.saves.append((w, l, d, b, match_in_progress))
            real_save(w, l, d, b, path, match_in_progress=match_in_progress,
                      bans_done_this_match=bans_done_this_match)

        patches = {
            # run()'s loop reads state through read_state_for_turn, which asks the paid
            # model ONCE per cycle and the local readers every turn after. Both seams are
            # scripted here: this file pins run()'s early-result GATE, not which reader
            # supplied the screen, and leaving read_state_for_turn live would have the
            # local readers grab the real desktop.
            "read_game_state": lambda *a, **k: self._next_state(),
            "read_state_for_turn": lambda *a, **k: self._next_state(),
            "screen_is_moving": lambda *a, **k: False,
            "_grab_settle_regions": lambda names: {n: self._frame_bytes() for n in names},
            "_safe_prompt_check": lambda *a, **k: None,
            # I-11's three seams. `_fast_grab` was NOT patched here and the two
            # observes call it, so this file would have taken a REAL screenshot
            # of the user's desktop on every poll -- the exact leak
            # _run_harness's own comment records finding and closing.
            "_fast_grab": lambda *a, **k: self._full_frame(),
            "_result_screen_up": lambda *a, **k: "close_result" not in self.landed,
            "_match_start_screen": lambda *a, **k: (
                "ban" if "start_match" in self.landed else "prompt"),
            "press": self._press,
            "wait_for_screen_to_settle": lambda *a, **k: True,
            "wait_for_reveal_cards": lambda *a, **k: False,
            "read_matchup_reveal": lambda *a, **k: [],
            "play_one_turn": lambda *a, **k: (True, None),
            "read_full_ban_collection": lambda *a, **k: [
                (0, i, PlayerCard(f"Card {i}", 5 + i, 1)) for i in range(5)],
            "read_ban_counter": lambda *a, **k: 3,
            # "Is the dealer's Play ($50) prompt on screen?" False is the
            # conservative default and matches every scenario here, all of
            # which script a live match. run() reads this only for the audit
            # line at the debit, which drives nothing.
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

        # AND input_controller's OWN `press`, which is what press_verified
        # calls (I-11). In production the two names are the same object; left
        # unstubbed the real one refuses under BASEBALL_TEST_RUN and records
        # nothing, so every press count here would silently read zero.
        import input_controller as _ic
        _ic_press = _ic.press
        _ic.press = self._press

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
            os.unlink(path)

    def debits(self, start_balance=500):
        return (start_balance - self.saves[-1][3]) // 50 if self.saves else 0

    def starts(self):
        return self.presses.count("start_match")


RESULT_WIN = {"screen": "result", "phase": "batting", "your_score": 7,
              "opp_score": 3, "result_won": True, "hand": [], "runners": [],
              "discards_left": 2}
RESULT_ZERO = dict(RESULT_WIN, your_score=0, opp_score=0, result_won=False)

# LITERALS, not the constants themselves (§10 rule 11). Every scenario below is
# built around these two numbers: with MIN_PLAYS_FOR_RESULT at 0 the gate can
# never fire and the reproduction would pass vacuously, and with
# RESULT_CONFIRM_READS at 0 "confirm, then accept" is just "accept". If either
# is deliberately re-measured, re-derive the scenarios rather than editing this
# line to match.
check(o.MIN_PLAYS_FOR_RESULT == 4,
      f"MIN_PLAYS_FOR_RESULT is {o.MIN_PLAYS_FOR_RESULT}, not the 4 these "
      "scenarios were written against — the gate's coverage changed")
check(o.RESULT_CONFIRM_READS == 3,
      f"RESULT_CONFIRM_READS is {o.RESULT_CONFIRM_READS}, not the 3 these "
      "scenarios were written against")

_N = o.MIN_PLAYS_FOR_RESULT          # cards a real match plays before it ends
_C = o.RESULT_CONFIRM_READS          # polls a real result survives


# --- THE REPRODUCTION: one misread result must not buy a second match ----
# Exactly the observed shape. The 7-3 is the point: mid-match the scoreboard is
# normally non-zero, which is what the deleted `_scores_all_zero` clause keyed
# on and why the gate was inert precisely when it was needed.
h = Harness(["match_start_prompt", "turn", RESULT_WIN, "match_start_prompt"])
final = h.run(target_wins=99, max_spend=500)
check(final["balance"] == 450,
      f"double-debit: one match, one misread 7-3 'result', and the balance "
      f"ended at ${final['balance']} — expected $450. A non-zero result read "
      "after 1 play cleared match_in_progress, so C5 waved the next "
      "transition-overlay misread through and paid for the same match twice.")
check(final["wins"] == 0 and final["losses"] == 0 and final["draws"] == 0,
      f"double-debit: a 7-3 'result' after 1 play was written into the record "
      f"as {final['wins']}W/{final['losses']}L/{final['draws']}D — a result "
      "that early is a transition overlay, not a finish")
check(final["match_in_progress"] is True,
      "double-debit: match_in_progress was cleared by an unconfirmed result — "
      "that flag is the ONLY thing C5 has to go on, so clearing it re-arms the "
      "debit")
check(h.starts() == 1,
      f"double-debit: start_match pressed {h.starts()}x for one match. That key "
      "is `\\`, the same one as confirm_discard, so the extra press lands in a "
      "live match (the 2026-08-25 harm)")

# The same run carried through to a genuine finish: the misread is absorbed,
# the match continues, and the real result scores ONCE for ONE $50.
h = Harness(["match_start_prompt", "turn", RESULT_WIN, "match_start_prompt"]
            + ["turn"] * _N + [RESULT_WIN])
final = h.run(target_wins=99, max_spend=500)
check(final["balance"] == 450 and final["wins"] == 1,
      f"one match played through a misread scored {final['wins']} win(s) for "
      f"${500 - final['balance']} — expected exactly 1 win for $50")


# --- the gate must not delay or suppress a GENUINE finish ---------------
# Positive control. Without this the file would pass with the gate wired to
# reject every result, which is a different and equally expensive bug.
#
# I-30: AT the boundary (exactly _N plays) a genuine finish now needs the SAME
# result read on two CONSECUTIVE frames -- one extra poll, not a rejection.
h = Harness(["match_start_prompt"] + ["turn"] * _N + [RESULT_WIN, RESULT_WIN])
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 1 and final["balance"] == 450,
      f"a result confirmed on two consecutive frames after {_N} plays (the "
      f"boundary) scored {final['wins']} win(s) — expected exactly 1, with no "
      "more delay than the one extra confirming frame")

# Past the boundary (_N + 1 plays) nothing changed: still scores on the first
# sighting, no confirmation delay.
h = Harness(["match_start_prompt"] + ["turn"] * (_N + 1) + [RESULT_WIN])
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 1 and final["balance"] == 450,
      f"a result after {_N + 1} plays (past the boundary) scored "
      f"{final['wins']} win(s) — a finish past MIN_PLAYS_FOR_RESULT must still "
      "score on the first sighting, with no confirmation delay")

# --- I-30: THE EXACT INCIDENT, REPRODUCED AND CLOSED ---------------------
# A single misread "result" at EXACTLY plays_this_match == MIN_PLAYS_FOR_RESULT
# (the boundary the old code trusted outright) must not score and must not
# re-arm the debit -- the live incident's next poll went straight to a turn
# screen, never a second "result".
h = Harness(["match_start_prompt"] + ["turn"] * _N + [RESULT_WIN, "turn"])
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 0 and final["losses"] == 0 and final["draws"] == 0,
      f"a single misread 'result' at exactly {_N} plays (the boundary) scored "
      f"{final['wins']}W/{final['losses']}L/{final['draws']}D — a one-frame "
      "read at the boundary must not score without a second consecutive read")
check(final["match_in_progress"] is True,
      "a single misread 'result' at the boundary cleared match_in_progress — "
      "that flag is the only thing C5 has to go on")

# ...and the streak must be genuinely CONSECUTIVE: the same misread seen twice
# with ANYTHING else in between must not confirm it either. The gap screen is
# match_start_prompt, not "turn" -- a "turn" screen calls play_one_turn and
# would advance plays_this_match PAST the boundary itself (a confound: that
# would pass the check below for the wrong reason, because past the boundary
# nothing requires confirmation at all).
h = Harness(["match_start_prompt"] + ["turn"] * _N
            + [RESULT_WIN, "match_start_prompt", RESULT_WIN])
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 0 and final["draws"] == 0,
      f"two 'result' sightings at the boundary with a non-result screen "
      f"between them scored {final['wins']}W/{final['draws']}D — a gap must "
      "reset the confirmation, or 'consecutive' means nothing")

# ...and an EARLY result that keeps saying the same thing is evidence, so it
# must eventually score. Otherwise a genuinely short match hangs the loop with
# match_in_progress stuck True and no debit ever possible again.
h = Harness(["match_start_prompt"] + [RESULT_WIN] * (_C + 1))
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 1,
      f"an early result confirmed {_C + 1}x scored {final['wins']} win(s), "
      "expected 1 — the gate must yield to evidence, not reject early results "
      "outright, or a short match deadlocks the run")

# Two genuine matches still cost exactly $100 and score exactly twice: the
# guard must not over-suppress into a deadlock after the first match. Past the
# boundary (_N + 1 plays) so this is not entangled with I-30's two-consecutive-
# frame check above -- that one already has its own positive control.
h = Harness((["match_start_prompt"] + ["turn"] * (_N + 1) + [RESULT_WIN]) * 2)
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 2 and final["balance"] == 400,
      f"two genuine matches scored {final['wins']} win(s) for "
      f"${500 - final['balance']} — expected 2 wins for $100")


# --- the confirmation budget is PER MATCH, not per session --------------
# unconfirmed_result_reads is reset in two places (on scoring, and on the next
# debit) and either alone is enough, so neither mutates detectably on its own.
# Removing BOTH does: the counter would arrive at the next match already spent,
# and the FIRST misread of match 2 would be believed with no re-read at all.
# Match 1 here deliberately ends through the confirmation path so the counter
# is at its budget when match 2 starts.
h = Harness(["match_start_prompt"] + [RESULT_WIN] * (_C + 1)
            + ["match_start_prompt", "turn", RESULT_WIN, "match_start_prompt"])
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 1 and final["balance"] == 400,
      f"the confirmation budget leaked across matches: scored {final['wins']} "
      f"win(s) and ${500 - final['balance']} spent, expected 1 win and $100 "
      "(two legitimate debits). Match 2's first misread was believed without a "
      "single re-read because match 1 had already spent the budget.")


# --- the original 0-0 guard must survive --------------------------------
# Deleting the whole gate would make the reproduction above pass too, so pin
# the 2026-08-31 case as well: 0-0 after no plays is re-read, not believed.
h = Harness(["match_start_prompt"] + [RESULT_ZERO] * _C)
final = h.run(target_wins=99, max_spend=500)
check(final["draws"] == 0,
      f"the original 0-0 guard is gone: a 0-0 result seen {_C}x with no plays "
      f"logged {final['draws']} draw(s)")
h = Harness(["match_start_prompt"] + [RESULT_ZERO] * (_C + 1))
final = h.run(target_wins=99, max_spend=500)
check(final["draws"] == 1,
      f"a 0-0 result confirmed {_C + 1}x logged {final['draws']} draw(s), "
      "expected 1")


# --- I-30 CLOSED, 2026-09-20: the boundary (round 4-5) no longer double-debits
# This used to be "RESIDUAL, PINNED ON PURPOSE" -- a transition overlay
# misread as a result exactly at MIN_PLAYS_FOR_RESULT plays fabricated a
# result and bought a second match ($400, 2 start_match presses). This is the
# live shape: a lone misread, then straight to the next dealer prompt with no
# confirming second frame. The two-consecutive-frame boundary check refuses to
# score it, match_in_progress survives, and C2's "match is running, don't
# press" branch takes over instead of re-debiting.
h = Harness(["match_start_prompt"] + ["turn"] * _N
            + [RESULT_WIN, "match_start_prompt"])
final = h.run(target_wins=99, max_spend=500)
check(final["balance"] == 450 and h.starts() == 1,
      f"a 'result' misread after {_N} plays (the boundary) followed by a "
      f"match_start_prompt ended at ${final['balance']} with {h.starts()} "
      "start_match press(es) — expected $450 and 1 press: the misread must be "
      "refused, not scored, and must not re-arm the debit")
check(final["match_in_progress"] is True and final["wins"] == 0
      and final["losses"] == 0 and final["draws"] == 0,
      f"the boundary misread was scored or match_in_progress was cleared: "
      f"match_in_progress={final['match_in_progress']!r}, "
      f"{final['wins']}W/{final['losses']}L/{final['draws']}D")


for f in failures:
    print(f"FAIL: {f}")
print(f"{len(failures)} early-result double-debit failure(s)"
      if failures else "early-result double-debit: all checks passed")
_sys.exit(1 if failures else 0)
