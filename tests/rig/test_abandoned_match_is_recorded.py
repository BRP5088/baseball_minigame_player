"""I-06: a match abandoned via reset_environment's "Give up?" path leaves a record.

WHY THIS EXISTS
---------------
ISSUES.md I-06: reset_environment answers "Give up?" YES whenever a stall or
route failure lands it mid-match (reset_env.py:270-281), then reloads the save
and clears match_in_progress -- CLAUDE.md's "A RESET IS THE MONEY RECONCILER"
explains why that is the right thing to do for MONEY. But nothing recorded
that a $50 match was thrown away: the census this project exists to build
(match_log.jsonl) simply never learned the match happened.

This pins that a give-up reset now appends ONE row to match_log.jsonl through
`orchestrator.log_matchup` -- the SAME helper the reveal path uses, so the
`_synthetic` stamp that keeps test rows out of the real dataset (CLAUDE.md
section 5, "FOUR MORE STATE BUGS") applies here automatically -- and bumps an
`abandoned` counter in the progress file, alongside wins/losses/draws. And the
control: a reset that never sees the "Give up?" dialog (nothing was abandoned)
writes neither.

Reuses the Game/screen-script pattern from test_reset_sequence.py, which
already proved the "match in progress" give-up flow completes successfully;
this file only adds the two assertions that fall out of I-06's fix, driven
against the REAL orchestrator.log_matchup with the match log and progress file
both redirected to a temp path -- never the real match_log.jsonl.
"""

import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import atexit
import os
import sys
import json
import shutil
import tempfile
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

# MATCH_LOG_FILE is bound at IMPORT time (orchestrator.py:468), so the
# redirect must land before `import orchestrator` or every row lands in the
# real project-root match_log.jsonl (CLAUDE.md 10.18 -- read at call time,
# never captured in a default -- is the same trap the module-level default
# already dodges; this is the caller-side half of it).
_LOGTMP = tempfile.mkdtemp(prefix="i06_matchlog_")
atexit.register(shutil.rmtree, _LOGTMP, ignore_errors=True)
_MATCH_LOG = os.path.join(_LOGTMP, "match_log.jsonl")
os.environ["BASEBALL_MATCH_LOG"] = _MATCH_LOG

from PIL import Image

import reset_env
import orchestrator            # REAL module: log_matchup is what's under test
import input_controller as ic
import pause_menu as pm
import compass

fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


# Same brightness table as test_reset_sequence.py, trimmed to the states this
# file drives: gameplay -> match -> giveup -> gameplay -> pause -> confirm ->
# loading -> world (scenario A), and pause -> confirm -> loading -> world
# (scenario B, no give-up).
LEVEL = {"gameplay": 60, "pause": 170, "confirm": 92, "loading": 121,
         "world": 80, "match": 45, "giveup": 150}


class Game:
    def __init__(self, state="gameplay"):
        self.state = state
        self.cursor = 1                 # start on "Load Last Save" (index 1)
        self.confirm_drop = 78.0
        self.load_secs = 6.0
        self.bearing = 97.4
        self.clock = 0.0
        self.events = []

    def level(self):
        base = LEVEL[self.state]
        if self.state == "confirm":
            base = LEVEL["pause"] - self.confirm_drop
        return int(round(base))

    def capture(self):
        v = max(0, min(255, self.level()))
        self.events.append(("cap", self.state))
        return Image.new("RGB", (64, 64), (v, v, v))

    # --- input_controller --------------------------------------------------
    def has_focus(self):
        return True

    def frontmost_app(self):
        return "Terminal"

    def chiaki_pid(self, refresh=False):
        return 4242

    def press(self, action, hold_seconds=0.05, post_delay=None):
        self.events.append(("press", action))
        if action == "toggle_pause":
            if self.state == "gameplay":
                self.state = "pause"
            elif self.state == "match":
                self.state = "giveup"
            elif self.state == "giveup":
                self.state = "match"
        elif action == "dpad_down":
            if self.state == "pause":
                self.cursor = min(self.cursor + 1, 3)
        elif action == "cross":
            if self.state == "giveup":
                self.state = "gameplay"          # YES: quits to the world
            elif self.state == "pause":
                self.state = "confirm"
            elif self.state == "confirm":
                self.state = "loading"
                self._world_at = self.clock + self.load_secs

    def press_background(self, action, hold_seconds=0.05, post_delay=None):
        self.events.append(("bg", action))
        return True

    # --- pause_menu ----------------------------------------------------
    def is_pause_screen(self, img):
        return self.state == "pause"

    def selected_item(self, img):
        MENU = ["Resume", "Load Last Save", "Load", "Quit to Main Menu"]
        return MENU[self.cursor] if self.state == "pause" else None

    # --- compass ---------------------------------------------------------
    def read_bearing(self, img):
        if self.state == "loading" and self.clock >= getattr(self, "_world_at", 1e18):
            self.state = "world"
        return self.bearing if self.state == "world" else None

    # --- clock -------------------------------------------------------------
    def sleep(self, seconds):
        self.clock += seconds


def _write_progress(path, **kw):
    rec = {"wins": 3, "losses": 1, "draws": 0, "balance": 246,
          "match_in_progress": False, "bans_done_this_match": False}
    rec.update(kw)
    with open(path, "w") as fh:
        json.dump(rec, fh)
    return rec


def _match_log_lines():
    if not os.path.exists(_MATCH_LOG):
        return []
    with open(_MATCH_LOG) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _run(state, reason=None, progress_seed=None):
    game = Game(state=state)
    ic.has_focus, ic.frontmost_app, ic.press = (
        game.has_focus, game.frontmost_app, game.press)
    ic.press_background, ic.chiaki_pid = game.press_background, game.chiaki_pid
    pm.is_pause_screen, pm.selected_item = game.is_pause_screen, game.selected_item
    compass.read_bearing, compass.fast_capture = game.read_bearing, game.capture
    compass.describe = lambda d: f"{d:.0f} deg"
    game.gave_up_seen = 0

    def _give_up(img):
        seen = game.state == "giveup"
        game.gave_up_seen += int(seen)
        return seen

    reset_env.give_up_dialog = _give_up
    reset_env.time = types.SimpleNamespace(sleep=game.sleep, time=lambda: game.clock)

    fd, progress_file = tempfile.mkstemp(prefix="i06_progress_", suffix=".json")
    os.close(fd)
    _write_progress(progress_file, **(progress_seed or {}))

    err = None
    try:
        bearing = reset_env.reset_environment(log=lambda *a, **k: None,
                                              progress_file=progress_file,
                                              reason=reason)
    except reset_env.ResetError as e:
        bearing, err = None, e
    with open(progress_file) as fh:
        after = json.load(fh)
    os.unlink(progress_file)
    return game, bearing, err, after


# =========================================================================
# A. THE GIVE-UP PATH: one abandoned row, one counter bump.
# =========================================================================
before_rows = _match_log_lines()
game, bearing, err, after = _run("match", reason="test-stall",
                                 progress_seed={"match_in_progress": True})

check(err is None, f"the give-up scenario raised {err!r}")
check(bearing == 97.4, f"give-up scenario returned {bearing!r}, expected 97.4")
check("cross" in [a for k, a in game.events if k == "press"],
      "the Give up? dialog was never answered — the scenario proved nothing")

rows = _match_log_lines()
check(len(rows) == len(before_rows) + 1,
      f"expected exactly 1 new match_log row after a give-up reset, got "
      f"{len(rows) - len(before_rows)}: {rows[len(before_rows):]}")
if len(rows) == len(before_rows) + 1:
    row = rows[-1]
    check(row.get("outcome") == "abandoned",
          f"abandoned row has outcome={row.get('outcome')!r}, expected 'abandoned'")
    check(row.get("reason") == "test-stall",
          f"abandoned row has reason={row.get('reason')!r}, expected the caller's "
          f"'test-stall'")
    check(row.get("_classifier") == "abandon",
          f"abandoned row has _classifier={row.get('_classifier')!r}, expected "
          f"'abandon'")
    check("ts" in row, "abandoned row carries no 'ts' -- log_matchup stamps every row")
    check(row.get("_synthetic") is True,
          f"abandoned row written under BASEBALL_TEST_RUN must carry "
          f"_synthetic=True (the same guard the reveal path relies on), got "
          f"{row.get('_synthetic')!r}")

check(after.get("abandoned") == 1,
      f"progress file 'abandoned' counter is {after.get('abandoned')!r}, "
      f"expected 1")
check(after.get("match_in_progress") is False,
      "match_in_progress was not cleared by the give-up reset")

# A second give-up reset on the same progress file must bump the counter
# again, not reset it -- it accumulates across the run like wins/losses/draws.
game2, bearing2, err2, after2 = _run("match", reason="test-stall-2",
                                     progress_seed={"match_in_progress": True,
                                                    "abandoned": 1})
check(err2 is None, f"second give-up scenario raised {err2!r}")
check(after2.get("abandoned") == 2,
      f"a second abandonment must bump the counter to 2, got "
      f"{after2.get('abandoned')!r}")

# =========================================================================
# B. THE CONTROL: no "Give up?" dialog seen -> no row, counter unchanged.
# =========================================================================
before_rows = _match_log_lines()
game, bearing, err, after = _run("pause", reason="should-be-ignored",
                                 progress_seed={"match_in_progress": True})

check(err is None, f"the control scenario raised {err!r}")
check(bearing == 97.4, f"control scenario returned {bearing!r}, expected 97.4")
check(game.gave_up_seen == 0,
      "sanity: the control scenario answered a Give up? dialog that was never "
      "supposed to appear — it is not testing the control it claims to")

rows = _match_log_lines()
check(len(rows) == len(before_rows),
      f"a plain reset with no match to abandon wrote "
      f"{len(rows) - len(before_rows)} match_log row(s); expected 0: "
      f"{rows[len(before_rows):]}")
check("abandoned" not in after or after.get("abandoned") == 0,
      f"the control's progress file shows abandoned={after.get('abandoned')!r} "
      f"after no give-up dialog was ever answered")
check(after.get("match_in_progress") is False,
      "the pre-existing match_in_progress flag was not cleared by the "
      "ordinary (non-give-up) reset path")


if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  I-06: a give-up reset appends one _synthetic-stamped 'abandoned' row "
      f"to match_log.jsonl and bumps the progress file's abandoned counter "
      f"(cumulative across resets); a reset with nothing to give up on writes "
      f"neither. Redirected log: {_MATCH_LOG}")
