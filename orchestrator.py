"""
Orchestrator - runs the full turn loop for the Baseball minigame.

Flow per turn:
  1. Screenshot the screen.
  2. Ask Claude (vision, via the Anthropic API) to read the current game
     state as structured JSON.
  3. Feed that into the decision engine to pick a play.
  4. Drive the input controller to execute it.
  5. Detect match end via the scoreboard's "S" column, log the result,
     and wait for the next match to start.

SCOPE NOTE — what this does and doesn't automate:
This automates in-match play: reading your hand, choosing cards,
executing the selection. It does NOT walk your character to the bar
NPC or pay the $50 to start each match — that needs general world
navigation (movement, NPC interaction, dialogue), which is a much
bigger and more fragile problem than reading a card game. After each
result, the loop waits for you to start the next match yourself (a
few seconds), then auto-detects the fresh hand and resumes. If you
want the walk-and-pay step automated too, that's worth tackling
separately once this core loop is proven reliable over real games.

Requires: pip install pyautogui anthropic tesserocr pytesseract numpy Pillow
(tesserocr is what the local reads actually use; without it every one of them
falls back to spawning a tesseract process — see _ocr_text)
Requires: PERSONAL_ANTHROPIC_API_KEY set in your environment.
Optional (audit-only local OCR): a Python 3.11 venv at ./paddle_venv with
  paddlepaddle + paddleocr — see hand_digit_reader.py.
"""

import base64
import difflib
import io
import collections
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import event_log

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import pyautogui
import ocr_glyphs
# Kept, and still imported at the top: _ocr_text falls back to it when the
# in-process reader cannot start, and that fallback must not be the first thing
# that discovers pytesseract is missing.
import pytesseract
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from decision_engine import (
    PlayerCard, TacticsCard, TacticsType, GameState,
    best_batting_play, best_pitching_play, choose_bans, should_redraw,
    # Imported only so the redraw decision can LOG the number it was compared
    # against. A logged "best power 7" is uninterpretable without the bar it
    # was measured against, and a bar quoted from memory drifts.
    REDRAW_POWER_THRESHOLD,
)
import input_controller
from input_controller import (
    select_and_play, select_and_discard, select_bans_and_start_full, press,
    focus_chiaki_window,
)

# `import anthropic` costs 1.84s (measured: 2.09s for `python -c "import
# anthropic"` against a 0.06s bare interpreter) — 84% of this module's 2.19s
# import time. Nothing that merely IMPORTS orchestrator needs it: not the 16
# offline test files, not preflight, not analyze_match_log. They pay it 16
# times per suite run, and preflight runs the whole suite before every live
# session.
#
# The env lookup stays EAGER and unchanged: a missing PERSONAL_ANTHROPIC_API_KEY
# must still raise at import, before preflight prints its clean message.
import env_loader as _env_loader
_env_loader.load()          # .env if present; the shell still wins

_API_KEY = os.environ["PERSONAL_ANTHROPIC_API_KEY"]


# --- Local OCR: in process, no subprocess, no temp file (OPEN-12) ----------
#
# Every local read on this file used to be pytesseract, which spawns a
# `tesseract` process per call and passes the image through a TEMP FILE. Two
# separate costs, and the second is the one that hurt:
#
#   * ~193ms a call against ~79ms through the Tesseract C API in process;
#   * the temp file itself. This is a work machine running Sophos, which scans
#     that file as it is written and again as it is unlinked. Six
#     pytesseract-heavy tests intermittently blew the suite's 300s ceiling and
#     a faulthandler dump caught them stopped inside pytesseract.cleanup,
#     unlinking exactly that file. ocr_glyphs writes no temp file at all, so
#     the migration removes the whole class of stall rather than 114ms of it.
#
# What it does NOT do is change the question. Same PSM, same whitelist, same
# already-preprocessed image; ocr_glyphs.tesseract_config builds the same
# config string the fallback passes, from one definition, so the two cannot
# drift into asking different things.
def _ocr_text(image, psm, whitelist=None):
    """The one word-mode OCR path, wrapped for the EVENT LOG (patch64): the caller
    names the read kind and the text is what the agent judges. See _ocr_text_raw."""
    _ocr_result = _ocr_text_raw(image, psm, whitelist)
    event_log.log_event("ocr", caller=event_log.caller_name(2), psm=psm, whitelist=whitelist,
                        size=(list(image.size) if hasattr(image, "size") else None),
                        text=(_ocr_result or "")[:200])
    return _ocr_result


def _ocr_text_raw(image, psm, whitelist=None):
    """Local OCR of an already-preprocessed crop. Returns tesseract's raw text.

    Raw, INCLUDING trailing newlines: ocr_scoreboard splits this into lines and
    a changed terminator changes the split. Callers that want it tidy strip it
    themselves, exactly as they did when this was a pytesseract call.

    Falls back to pytesseract if the in-process reader is unavailable, and says
    so ONCE. The warning has to spell out the combination, because it is the
    one that otherwise goes untraced: the answers stay RIGHT and the run gets
    slower and starts stalling in the AV. Nothing downstream looks broken, so a
    reader profiling it would blame the console, the network or the walk.
    """
    try:
        name = ocr_glyphs.backend()
        if name == "tesserocr":
            return ocr_glyphs.image_to_text(image, psm=psm, whitelist=whitelist)
        why = (f"ocr_glyphs selected the {name!r} backend, which still spawns "
               f"a tesseract process per call")
    except Exception as e:                       # import, tessdata, API init
        why = f"{type(e).__name__}: {e}"
    _warn_once(
        f"WARNING: the in-process OCR reader is unavailable ({why}) — every "
        f"local read for the rest of this process (ban-grid card names, the "
        f"scoreboard, runner banners, the ban counter) falls back to "
        f"pytesseract. THE ANSWERS STAY CORRECT, so nothing downstream will "
        f"look broken; the run simply gets slower (measured ~79ms -> ~193ms a "
        f"call) and regains the temp-file-per-call stall that Sophos turns "
        f"into multi-second pauses inside pytesseract.cleanup. This is the "
        f"only place that says why. (Warned once per process.)")
    return pytesseract.image_to_string(
        image, config=ocr_glyphs.tesseract_config(psm, whitelist))


class PaidModelDisabled(RuntimeError):
    """Raised when something tries to spend a paid vision call while the model is OFF."""


# OFF by the user's instruction, 2026-09-12. See _BudgetedMessages.create for why the
# lockout lives at the choke point rather than at the four call sites.
PAID_MODEL_ENABLED = False


def paid_model_allowed():
    """Read at CALL time, never captured in a default (CLAUDE.md 10.18).

    The env var is the one-process escape hatch; the module flag is the durable one.
    Anything that resolved this at import would let a stale value outlive the switch.
    """
    return PAID_MODEL_ENABLED or os.environ.get("BASEBALL_ALLOW_PAID") == "1"


class _LazyAnthropic:
    """Builds the real Anthropic client on first use, not at import.

    Deliberately a module-level OBJECT rather than a function, so existing
    `client.messages.create(...)` call sites are untouched, and tests that
    swap in a fake with `orchestrator.client = <stub>` keep working — they
    rebind the module attribute and this object is never consulted again.
    """

    _real = None

    def __getattr__(self, name):
        # THE OUTER HALF OF THE LOCKOUT, AND THE HALF THAT IS NOT OPTIONAL.
        # _BudgetedClient wraps `.messages` and NOTHING ELSE: `.beta`, `.with_raw_response`
        # and whatever namespace the SDK adds next version fall straight through to the
        # real client, so the create() gate below was one attribute name wide. Gating here
        # means the real Anthropic object is never CONSTRUCTED while the model is off --
        # PERSONAL_ANTHROPIC_API_KEY never leaves the environment variable it lives in.
        #
        # Both gates stay. This one is the catch-all; the one in create() is what covers a
        # hand-built _BudgetedMessages and is what the budget ordering is pinned against.
        if not paid_model_allowed():
            raise PaidModelDisabled(
                f"the paid vision model is OFF by the user's instruction (2026-09-12), so "
                f"no real client is built -- refusing `client.{name}`. Set "
                f"orchestrator.PAID_MODEL_ENABLED = True or BASEBALL_ALLOW_PAID=1 to "
                f"re-enable, and only if the user has said so.")
        if _LazyAnthropic._real is None:
            from anthropic import Anthropic
            _LazyAnthropic._real = Anthropic(api_key=_API_KEY)
        return getattr(_LazyAnthropic._real, name)


class _BudgetedClient:
    """The real client, with every paid call counted against a hard cap.

    Wrapping here rather than at each call site means a new `messages.create`
    added later is covered automatically — there are four today and the fifth
    would otherwise be free to slip past the budget.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        if name == "messages":
            return _BudgetedMessages(self._inner.messages)
        return getattr(self._inner, name)


class _BudgetedMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *args, **kwargs):
        # THE PAID MODEL IS OFF, BY THE USER'S INSTRUCTION (2026-09-12):
        # "stop using the paid model. you are no longer allowed to use it unless I say
        # so. comment out the paid model calls."
        #
        # The block sits HERE and not at the four call sites for the same reason the
        # budget does: a fifth `messages.create` added later is covered automatically,
        # where four commented-out call sites would leave the next one free to spend.
        # It RAISES rather than returning None, because a paid read that silently
        # answers nothing is this project's signature failure -- a no-op indistinguishable
        # from success (CLAUDE.md 10.1) -- and every caller of these four sites branches
        # on the answer. Failing loudly is what makes the lockout visible.
        #
        # Turning it back on is deliberate and reversible: set PAID_MODEL_ENABLED = True
        # here, or export BASEBALL_ALLOW_PAID=1 for one process. Nothing else re-enables
        # it, and nothing enables it by accident.
        if not paid_model_allowed():
            raise PaidModelDisabled(
                "the paid vision model is OFF by the user's instruction (2026-09-12). "
                "Every field the loop needs has a local reader: local_hand for the hand, "
                "local_state for phase/runners/result, ocr_scoreboard for the score. "
                "Set orchestrator.PAID_MODEL_ENABLED = True or BASEBALL_ALLOW_PAID=1 to "
                "re-enable, and only if the user has said so.")
        import api_budget
        api_budget.note_call()
        resp = self._inner.create(*args, **kwargs)
        # THE EVENT LOG (patch64): the one place every paid read passes through. The
        # caller names the read kind; the raw answer is what the agent judges.
        try:
            n_img = sum(1 for m in kwargs.get("messages", []) if isinstance(m, dict)
                        for c in (m.get("content") if isinstance(m.get("content"), list) else [])
                        if isinstance(c, dict) and c.get("type") == "image")
            text = "".join(getattr(b, "text", "") for b in getattr(resp, "content", []) or [])
            event_log.log_event("vision", caller=event_log.caller_name(2), images=n_img,
                                answer=text[:4000], calls_used=api_budget.used())
        except Exception:
            pass
        return resp

    def __getattr__(self, name):
        return getattr(self._inner, name)


client = _BudgetedClient(_LazyAnthropic())


def _api_used():
    try:
        import api_budget
        return api_budget.used()
    except Exception:
        return "?"

# Sonnet is the default for accuracy reading card stats off a screenshot.
# If cost or speed becomes a concern over many matches, Haiku is worth
# trying — swap the model string and see if read accuracy holds up.
MODEL = "claude-sonnet-5"

# If the screen goes unrecognized (or unreadable) for this many polls in a
# row, stop the loop rather than spin silently burning API calls. At the
# ~2s poll interval used below, this is roughly a minute of being stuck.
# TWO different situations, two different limits — conflating them broke a
# guarantee the state machine is supposed to give.
#
# An UNRECOGNISED SCREEN costs a paid API call per retry and learns nothing: a
# stall on 2026-08-28 spent fifteen calls staring at the wrong display. Fail
# fast there; the diagnostics bundle is what makes it fixable, not the attempts.
#
# A RAISING play_one_turn is different. It is usually a transient bad read, the
# retry is free, and abandoning the match loses real money. Lowering the shared
# limit to 4 broke that: a run with five consecutive bad reads gave up instead
# of recovering.
MAX_STUCK_ATTEMPTS = 15
# Six, not four, and not fifteen. Four exits fastest but leaves a five-entry
# observation trail, and the state-machine test rightly demands more than that —
# a bundle nobody can diagnose from is not "logging as much as possible before
# exiting", it is just exiting. Six gives a seven-entry trail while still
# spending a third of what the old fifteen did.
MAX_UNRECOGNIZED_ATTEMPTS = 6

# How many consecutive failed screen reads a pending matchup survives before
# it is dropped as unscoreable. Measured, not chosen: over the 2026-08-26 run
# 22 plays were followed by a failed read — 19 by exactly one poll, 3 by two,
# none by more. Those are the loop re-reading while the next hand deals, well
# inside the same turn. The old behaviour was an implicit 0 (drop on the very
# first failure), which cost ~76% of that run's rows. Raising this further
# starts risking the real hazard: a gap long enough for the opponent to act,
# which would silently mislabel the outcome rather than omit it.
MAX_PENDING_READ_FAILURES = 2
# Screen-independent bound; see polls_without_progress in run(). Generous, since
# a legitimate match has long stretches (ban scan, animations) with no debit,
# result or play — it only has to be tighter than "forever".
MAX_POLLS_WITHOUT_PROGRESS = 120
# How long the hand region may stay BYTE-IDENTICAL before the run is declared
# frozen. Time-based, not poll-count-based, and deliberately generous.
#
# Measured over all 1,937 logged frames from two real sessions: the longest run
# of byte-identical consecutive hand crops is ZERO — even menus and idle turn
# screens differ frame to frame. So this cannot fire on live play.
#
# But those frames are ~1s apart while the loop polls ~5x faster, and a count of
# 12 polls would have been only ~2.4s — short enough that a genuinely paused
# game (someone hits Options) could trip it and abort a real run. A frozen
# stream is a slow-burn cost, not an emergency: the harm is an overnight of
# wasted calls, so waiting 90s to be certain costs nothing and removes the
# false-positive risk entirely.
FROZEN_STREAM_SECONDS = 90.0

# Session progress persists here so killing and restarting the script
# doesn't lose the win/loss count — every match result gets written
# immediately, and it's read back in on startup. Per-save-file, not
# global: each player's own win/loss/balance history is tied to their
# own progress file, so playing on someone else's save (e.g. Taylor's,
# 2026-08-23) never mixes into your own trophy progress or vice versa.
PROGRESS_FILE = "progress.json"


def load_progress(progress_file: str = PROGRESS_FILE):
    if os.path.exists(progress_file):
        try:
            with open(progress_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # Starting from zero would silently discard the win/loss record and
            # re-read the balance from the pause menu. Refuse instead — this is
            # recoverable by hand, and _atomic_write_json() should prevent it.
            raise RuntimeError(
                f"{progress_file} is unreadable ({e}). Refusing to start and "
                "silently reset your progress — inspect or delete it first.")
        return (data.get("wins", 0), data.get("losses", 0), data.get("draws", 0),
                data.get("balance"), bool(data.get("match_in_progress", False)),
                bool(data.get("bans_done_this_match", False)))
    return 0, 0, 0, None, False, False


def _atomic_write_json(path: str, data):
    """Write JSON via a temp file + rename, so an interrupted write can never
    leave a truncated file behind. N8/N13: both progress.json and the learned
    roster are read back at startup, and a half-written one either loses the
    win/loss record or breaks module import."""
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # The real guarantee (a reader never sees a partial file) already holds
        # without this — os.replace is atomic and simply never runs. But a crash
        # mid-write otherwise ORPHANS the .tmp, and a stale one sitting next to
        # progress.json invites someone to wonder which is real.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def open_match_files(here=None):
    """[(filename, bans_done)] for every progress*.json claiming a match is in progress.

    THE FLAG IS THE $50 DOUBLE-DEBIT GUARD, and it was only ever checked on ONE file.
    preflight read sys.argv[1] and defaulted to progress.json, so `python3 preflight.py`
    with no argument reported READY while progress_testing.json held the flag -- and this
    project keeps two progress files deliberately (CLAUDE.md: recent training uses
    progress_testing.json), so the default is wrong for exactly the workflow that needs the
    guard. Which file a later run will pass is not knowable in advance, so ALL of them are
    checked and the caller decides what to do about it.
    """
    import glob
    here = here or os.path.dirname(os.path.abspath(__file__))
    out = []
    for path in sorted(glob.glob(os.path.join(here, "progress*.json"))):
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue                 # unreadable is the caller's problem, not a claim
        if data.get("match_in_progress"):
            out.append((os.path.basename(path), bool(data.get("bans_done_this_match"))))
    return out


def save_progress(wins: int, losses: int, draws: int, balance: int,
                  progress_file: str = PROGRESS_FILE,
                  match_in_progress: bool = False,
                  bans_done_this_match: bool = False):
    """Persist the record. `match_in_progress` is part of it, deliberately.

    QA2-1: a result is only scored for a match this process paid for, which
    stops a misread transition overlay fabricating a win. But the flag lived
    only in memory, so a RESTART lost it — and every stall message in this file
    ends with "just rerun the script", making restart the designed recovery
    path. The sequence was: pay $50, crash/stall, rerun, and the result overlay
    for the match you paid for is refused, dismissed, and gone. A real win,
    silently discarded, on the exact path the tool tells you to take.

    Persisting it makes "did I pay for the match that is currently on screen"
    survive the restart, which is the only thing that can answer it correctly.
    """
    _atomic_write_json(progress_file,
                       {"wins": wins, "losses": losses, "draws": draws,
                        "balance": balance, "match_in_progress": match_in_progress,
                        "bans_done_this_match": bans_done_this_match})


# ponytail: TEMPORARY diagnostic logging, not a permanent feature — rip
# this whole thing out once it's answered its one question.
#
# Real-game play-by-play log — one JSON line per resolved turn, capturing
# both our own card and (via the reveal-animation read) the opponent's
# actual card, so a later analysis can control for what the opponent
# drew instead of only ever seeing our stats next to a confounded
# outcome. Added 2026-08-23 specifically to investigate whether the
# fielding/speed secondary stat has a real effect — that's never been
# confirmed live, and a local simulation has no way to answer it since
# it would just be simulating our own guess. Discard turns aren't logged
# (see play_one_turn) since we don't know the replacement card's stats.
#
# Cost: one extra vision API call + ~0.5-3s per played turn, permanently,
# for as long as this stays wired in — a real, ongoing tax against the
# speed work from earlier this session. It buys nothing once the
# question is answered.
#
# ANALYSED 2026-08-27 at 72 turns: still unanswered, keep logging. Batting
# alone showed a 44-point gap (p=0.015) that REVERSED on the held-out pitching
# half, because `secondary` is speed on a batter and fielding on a pitcher, so
# the comparison flips meaning between phases. Stratified by power, no secondary
# effect survives. Full working in MATCH_LOG_ANALYSIS.md. Do not strip this yet,
# and do not weight secondary in card selection on the strength of it.
#
# REMOVAL PLAN: once match_log.jsonl has ~150-200 logged turns split
# roughly evenly across pitching/batting (enough for the secondary-stat
# question to show a real signal above the noise floor established in
# simulate.py's identical-strategy control test), analyze it, then strip
# out: READ_MATCHUP_PROMPT, read_matchup_reveal(), log_matchup(),
# MATCH_LOG_FILE, the matchup_info return value from play_one_turn()
# (revert to returning just `played`), and the pending_matchup capture
# block + its consumption block in run(). Don't leave this "temporarily"
# wired in past that point — it has no ongoing purpose once answered.
# BASEBALL_MATCH_LOG lets the test suite redirect this. Tests drive real plays
# through the reveal path, and without the override they append synthetic rows
# to the live dataset — 30 of 69 rows on 2026-08-25, indistinguishable from
# genuine ones except by a field that happened to be new that day. Same class
# of bug as the diagnostics directory, found the same way: by the data looking
# wrong, not by anything failing.
MATCH_LOG_FILE = os.environ.get("BASEBALL_MATCH_LOG") or "match_log.jsonl"


# Defence in depth. Redirecting the log (BASEBALL_MATCH_LOG) stops test rows
# reaching the real file, but only for tests that remember to set it — and 30
# synthetic rows got in exactly because one didn't. Stamping every row written
# under a redirect means that even if such a row DOES end up in the real file,
# it is trivially identifiable and removable:
#
#     grep -v '"_synthetic": true' match_log.jsonl > clean.jsonl
#
# The two mechanisms fail independently, which is the point: the redirect
# prevents contamination, the stamp makes it recoverable when prevention fails.
# Analysis code should filter on `_synthetic` rather than trusting the file.
#
# KEYED ON "AM I A TEST", NOT ON "IS THE LOG REDIRECTED". The first version of
# this stamped only when BASEBALL_MATCH_LOG was set — i.e. exactly when the
# rows were already going somewhere harmless. In the case that actually
# matters, a test that FORGETS to redirect, no stamp was applied and the rows
# landed in the real file invisible. Proven immediately: a mutation removing
# the redirect wrote two unstamped fixture rows into match_log.jsonl.
#
# Detected two ways so neither has to be remembered: run_tests.sh exports
# BASEBALL_TEST_RUN, and any directly-invoked test_*.py is recognised by its
# own filename.
def _running_under_test() -> bool:
    # QA1-F7: BASEBALL_MATCH_LOG is deliberately NOT a test signal. It only
    # says "the log lives somewhere else", which a REAL run has every reason to
    # do (a per-save log, say). Treating it as test context stamped genuine rows
    # `_synthetic`, and the documented `grep -v '"_synthetic": true'` cleanup
    # would then delete real match data — the exact loss the stamp exists to
    # prevent, inverted.
    if os.environ.get("BASEBALL_TEST_RUN"):
        return True
    entry = os.path.basename(sys.argv[0] or "")
    return entry.startswith("test_") and entry.endswith(".py")


# READ AT CALL TIME. This was `_SYNTHETIC_LOG = _running_under_test()`, bound at
# import -- two functions below a docstring that teaches the opposite rule for exactly
# this file ("Call time, not import time (10.18) ... a footgun that reads as working and
# silently does not"). Set BASEBALL_TEST_RUN after `import orchestrator` and the stamp
# was False while _running_under_test() was True, so a test row landed UNSTAMPED in the
# real match_log.jsonl -- which the documented `grep -v '"_synthetic": true'` cleanup
# would never have removed. That happened during the QA sweep that found it.
def _synthetic_log():
    return _running_under_test()


# THE DEAL-TIMING DATASET, and it is a SEPARATE FILE on purpose.
#
# The rows go through record_observation as well, but that is a deque(maxlen=40) which
# run() clears per run and which only reaches disk when dump_diagnostics fires on a STALL.
# On a healthy run -- the only kind that produces a clean timing row -- every row was
# written and then thrown away. That is 10.1's "a measurement taken and discarded", and it
# shipped here once already.
#
# Not folded into match_log.jsonl: that file is the dataset this project exists to
# collect, its own comment above records 30 synthetic rows contaminating it, and a second
# schema sharing the stream makes both harder to read. One row per deal, its own file.
DEAL_LOG_FILE = "deal_timing.jsonl"


def _deal_log_path():
    """Where a deal-timing row goes, or None for 'do not write'. Resolved at CALL time.

    TWO LESSONS, BOTH ALREADY PAID FOR HERE.

    Call time, not import time (10.18): a module-level `os.environ.get(...) or DEFAULT` is
    bound when the module loads, so a test can only redirect it by setting the variable
    BEFORE importing orchestrator -- a footgun that reads as working and silently does not.

    And a test that forgets the redirect writes NOTHING, rather than writing stamped rows
    into the real dataset. log_matchup takes the other approach and stamps instead, because
    it predates this and its tests genuinely drive real plays; the comment above it records
    30 synthetic rows reaching match_log.jsonl anyway. This sink is new, so it gets the
    stronger rule: prevention, with the stamp still there for a redirect that IS set.
    Demonstrated the hour it was written -- test_reveal_peak.py drives the deal gate and
    does not redirect, and deal_timing.jsonl appeared in the project root.
    """
    explicit = os.environ.get("BASEBALL_DEAL_LOG")
    if explicit:
        return explicit
    return None if _synthetic_log() else DEAL_LOG_FILE


def log_deal_timing(record: dict):
    """Append one deal-timing row. Never raises into the turn loop.

    A disk error here must not end a paid match: the row is diagnostic, the match is $50.
    Stamped `_synthetic` under test by the same rule as log_matchup, so a test that forgets
    to redirect BASEBALL_DEAL_LOG leaves rows that are trivially removable rather than
    invisible -- that failure has happened on the match log and is why the stamp exists.
    """
    # THE WHOLE BODY, not just the write. The first version left the timestamp outside the
    # try while this docstring promised "never raises" -- a guard that does not reach the
    # thing it claims to cover, written into the fix for exactly that shape.
    try:
        path = _deal_log_path()
        if path is None:
            return                     # under test with no redirect: write nothing
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}
        if _synthetic_log():
            record = dict(record, _synthetic=True, _source="test-suite")
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"  [deal] could not append the timing row ({type(e).__name__}: {e}) — "
              "the turn continues; the row is lost")


def log_matchup(record: dict):
    # Every row is stamped. Without this the log is one undifferentiated
    # stream: after the 2026-08-26 run there was no way to tell which rows it
    # had written, so "29 plays produced how many rows?" could only be bounded
    # by diffing a count taken before and after. `ts` first, so a row's origin
    # is visible without parsing the whole line.
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}
    if _synthetic_log():
        record = dict(record, _synthetic=True,
                      _source="test-suite", _written=time.strftime("%Y-%m-%dT%H:%M:%S"))
    with open(MATCH_LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

READ_STATE_PROMPT = """
You are reading a screenshot of a turn-based baseball card minigame,
provided as multiple images in this order:

1. "overview" — the whole screen, at low resolution. Use this alone to
   determine "screen" and "phase", and to read anything on a
   "ban_screen", "match_start_prompt", "result", or "other" screen.
2. "scoreboard" — a sharp close-up of the top-left score/round/discards
   box. ONLY present/meaningful when screen would be "turn",
   "discard_prompt", or "result" — ignore it otherwise (e.g. on a
   ban_screen or match_start_prompt it just shows whatever background
   happens to be in that fixed screen position, not a real scoreboard).
3. "hand" — a sharp close-up of the 5-card hand row at the bottom.
   Same caveat: only meaningful when screen is "turn" or
   "discard_prompt".
4. "third_base", 5. "first_base", 6. "second_base" — sharp close-ups of
   each base position on the diamond. Each shows EITHER a bare round
   coin medallion (that base is empty — no runner) OR a face-up player
   card resting at that same spot (that base has a runner). Only
   meaningful when screen is "turn" or "discard_prompt" or "result".

When screen is "turn", "discard_prompt", or "result": read
your_score/opp_score/discards_left/hand from the "scoreboard"/"hand"
crops (they're sharper than the overview), and read "runners" by
checking the three base crops for which ones show a real card instead
of a bare coin. For every other screen type, rely on the "overview"
image alone and leave scoreboard/hand/base-crop content out of it.

Respond with ONLY a JSON object, no other text, in this exact shape:

{
  "screen": "turn" | "discard_prompt" | "result" | "ban_screen" | "match_start_prompt" | "other",
  "phase": "batting" | "pitching" | null,
  "your_score": int | null,
  "opp_score": int | null,
  "batters_used": int | null,
  "discards_left": int | null,
  "runners": [{"name": str, "power": int, "secondary": int}],
  "hand": [
    {"kind": "player", "name": str, "power": int, "secondary": int, "hand_index": int},
    {"kind": "tactics", "name": str, "type": "swing_boost"|"speed_boost"|"pitch_boost"|"fielding_boost", "bonus": int, "hand_index": int}
  ],
  "result_won": bool | null,
  "collection": [{"kind": "player"|"tactics", "name": str, "power": int, "secondary": int, "row": int, "col": int}]
}

Rules for filling this in:
- "screen": "turn" for a normal card-selection turn, "discard_prompt" if
  Play/Discard options are shown for an already-lifted card, "result" if
  this is a WINNER/game-over screen, "ban_screen" if this is the
  "BANNED CARDS x/3" pre-match screen showing a grid of your collection,
  "match_start_prompt" if this is the seated table screen showing
  "Baseball Cards - Play ($50)", "other" for anything else (menus,
  overworld, dialogue, loading, etc).
- hand_index is the 0-based left-to-right position of that card in the
  5-card hand at the bottom of the screen.
- "discards_left" is the count of remaining usable discards, read off the
  "DISCARDS" dot counter in the top-left scoreboard box (below "ROUND").
  Count only the dots that still look available/unused (matching the
  filled/bright style of the ROUND dots still to come); a dot that looks
  dimmed, hollow, or crossed out has already been spent and should not
  be counted. Use null if this counter isn't visible on screen.
- "power" is swing power (batter) or pitch focus (pitcher). "secondary"
  is speed (batter) or fielding (pitcher) — use 0 if no shield icon is
  shown on the card.
- "runners" — check the "third_base", "first_base", and "second_base"
  crops. Each shows either a bare round coin (base empty — not a
  runner) or a face-up player card with a readable name/power sitting
  at that same spot (a real runner who reached base on a previous turn
  and is still waiting to score). Include one entry per base crop that
  shows a real card. A card with no readable name/power isn't a valid
  runner entry — treat that base as empty instead of guessing. This is
  separate from the always-face-down pitcher-indicator card that sits
  dead center of the diamond (never a runner, don't include it) and
  from the hand row at the bottom.
- Only fill "result_won" when screen == "result": true if the scoreboard's
  "S" column shows your total higher than the opponent's, false otherwise.
- Only fill "collection" when screen == "ban_screen": every card visible
  in the grid, with its 0-based row and column position. Tag each one
  "kind": "player" if it has a "BATTER" or "PITCHER" label at the top,
  or "kind": "tactics" if it doesn't (Speed Boost, Power Swing, Pitch
  Focus, Fielding Play, or anything else without that label) — these
  can appear scrolled into the same grid. Include both kinds; the
  caller filters by kind, so getting this tag right matters more than
  omitting tactics cards yourself. SKIP any card rendered faded/grayed
  out with no power number shown at all — that means it's locked/not
  yet owned, not a real card that can be banned. Only include cards
  where "power" is an actual visible number, never null, in this field.
  SKIP any card whose name label isn't clearly legible too (mid-scroll
  transition frames sometimes show art before the name renders) — do
  NOT invent a placeholder like "Unknown" for it, just leave that card
  out of the list entirely rather than guessing at its name. This
  applies to every field in "collection": if any of name/power/secondary
  isn't clearly legible on a given card, leave that whole card out
  rather than filling in a best guess (a made-up 0, "Unknown", or
  similar) — an incomplete list is fine, a fabricated entry isn't.
  IMPORTANT — a solid black rectangle inside the grid is a card slot
  that's been intentionally redacted (locked/unowned), NOT empty space:
  it still occupies its own row and column exactly like a visible card
  does. When numbering columns for the cards you CAN read, count every
  black rectangle you pass over as one column, the same as you would a
  normal card — do not skip over it or renumber the visible cards as if
  the black rectangle weren't there.
- Use null (or an empty list, for "runners"/"hand"/"collection") for any
  field that doesn't apply to the current screen.
"""

# ---------------------------------------------------------------------------------------
# PAID_READS_CARDS -- THE PAID MODEL IS NO LONGER ASKED TO READ CARDS.
#
# The user's call, 2026-09-09: "comment out the API reads for all card reading. only leave
# the state classifications. leaving them in is hiding the real values and your also
# wasting my IRL money."
#
# Both halves of that are measured. It never read the cards: over 2,171 recorded hand
# cards its `name` came back as 'Batter'/'Pitcher' (the TYPE BANNER, not a name),
# '', 'None', 'Unknown', or one of 57 invented names -- including six spellings of the
# same one. And on 32 of 33 frames that contained NO CARDS AT ALL it returned a full
# five-card hand, against 325 of 327 on frames that did: "five cards" is a DEFAULT, the
# same shape as `discards_left` answering 2 on 286 of 360 turns.
#
# NOTHING IS DELETED. The original instructions sit above this line, word for word. Set
# this flag True and the old behaviour returns exactly as it was.
PAID_READS_CARDS = False

# The card-reading half of the prompt, swapped out rather than removed.
_PROMPT_CARDS_ON = """When screen is "turn", "discard_prompt", or "result": read
your_score/opp_score/discards_left/hand from the "scoreboard"/"hand"
crops (they're sharper than the overview), and read "runners" by
checking the three base crops for which ones show a real card instead
of a bare coin. For every other screen type, rely on the "overview"
image alone and leave scoreboard/hand/base-crop content out of it."""

_PROMPT_CARDS_OFF = """When screen is "turn", "discard_prompt", or "result": read
your_score/opp_score from the "scoreboard" crop (it's sharper than the
overview). For every other screen type, rely on the "overview" image
alone.

DO NOT READ THE CARDS. Return "hand": [] and "runners": [] ALWAYS, on
every screen, whatever you can see. Those fields are read locally from
the same frame and your answer for them is discarded. Do not describe,
count or guess at any card in the hand or on a base."""

_PROMPT_POWER_ON = """- "power" is swing power (batter) or pitch focus (pitcher). "secondary"
  is speed (batter) or fielding (pitcher) — use 0 if no shield icon is
  shown on the card."""

_PROMPT_POWER_OFF = """- "power"/"secondary" are read locally, not here — see "hand" above."""

if not PAID_READS_CARDS:
    assert READ_STATE_PROMPT.count(_PROMPT_CARDS_ON) == 1, "prompt drifted from the flag"
    assert READ_STATE_PROMPT.count(_PROMPT_POWER_ON) == 1, "prompt drifted from the flag"
    READ_STATE_PROMPT = (READ_STATE_PROMPT
                         .replace(_PROMPT_CARDS_ON, _PROMPT_CARDS_OFF)
                         .replace(_PROMPT_POWER_ON, _PROMPT_POWER_OFF))

READ_BALANCE_PROMPT = """
You are looking at a screenshot of the game's pause menu (a book/journal
graphic with "PAUSE" at the top). Along the right edge of the screen are
three stacked currency counters, each a number next to an icon, one
directly above the other. The player's money total is ALWAYS the
TOPMOST (highest on screen) of these three counters, and its icon is a
round coin/medallion with an embossed face on it.

Do NOT use the second or third counters below it — the second has a
round badge/emblem icon (a different currency), and the third has a
rectangular photo/ticket-shaped icon (a different currency, not round).
Do NOT use the heart-icon or cheese-icon counters in the bottom-left
corner of the screen either — those are unrelated resources.

CRITICAL: the large round coin in the BOTTOM-LEFT with a smiling embossed
face and a ribbon/banner under it is the player's HEALTH, not money. It
looks like a coin and it is not one. If the three stacked counters along
the RIGHT EDGE are not visible, this is not the pause menu — answer null
rather than reading that bottom-left coin.

Report all three right-edge counters so it is clear you found the stack
and not some other number.

Respond with ONLY a JSON object, no other text:

{"counters": [top_int, middle_int, bottom_int], "money": top_int}

If you cannot see three stacked counters along the right edge, respond
with {"counters": null, "money": null} instead of guessing.
"""


READ_BAN_ROW_CARDS_PROMPT = """
You are looking at a screenshot of a baseball card minigame's ban
screen: a 5-column grid of cards. Some grid cells are solid black —
these are locked/redacted card slots, not real cards.

List ONLY the legible BATTER/PITCHER cards, in strict reading order:
left to right within a row, top row before the row below it. Skip every
solid black cell entirely (don't count it, don't guess at it). Skip any
card whose name or power isn't clearly legible for any other reason
too — leave it out rather than guessing. Skip tactics cards (Speed
Boost, Power Swing, Pitch Focus, Fielding Play, or anything without a
BATTER/PITCHER label at the top).

Do NOT report row/column position — just the ordered list of what you
can actually read; the exact position of each card is figured out
separately, deterministically, without vision. Respond with ONLY a JSON
object:

{"cards": [{"name": str, "power": int, "secondary": int}, ...]}

"power" is swing power (batter) or pitch focus (pitcher); "secondary" is
speed (batter) or fielding (pitcher), 0 if no shield icon shown. If
nothing on screen is legible, respond {"cards": []}.
"""

# WHAT THIS PROMPT MUST NOT DO IS ASSERT ITS OWN PREMISE.
#
# It used to open "You are looking at a screenshot showing the face-up cards
# revealed mid-resolution of a turn". On a frame where the faceoff had not
# flipped yet that sentence is false, and a model told the reveal is on screen
# will find one: it reported the face-up cards that WERE there, which are the
# base runners standing on the base medallions and the fan of cards in our own
# hand. Those come back as confident, accurate reads of the wrong cards — on
# the 2026-09-01 run all 14 names so returned resolved to real roster entries,
# and the OCR power equalled the roster power in every case that was legible.
# Nothing downstream can defend against that: the auditor correctly concludes
# our card is missing and calls a misfire that never happened.
#
# So the premise is now a question the model is allowed to answer "no" to, and
# the two distractors are named explicitly. The output contract is unchanged;
# only the framing and the exclusions are new.
READ_MATCHUP_PROMPT = """
This is a screenshot of a baseball card minigame, taken at a moment when
the turn's two cards MAY OR MAY NOT have been revealed yet. Your job is to
report the faceoff — one card ours, one the opponent's — but ONLY if it is
actually face-up on screen right now.

WHERE THE FACEOFF IS: the two cards face each other VERTICALLY down the
middle of the diamond, one in the upper half, one in the lower half. EACH
side can show up to two cards stacked together: a BATTER or PITCHER player
card, and (only if that player attached one) a separate tactics card like
"Speed Boost", "Power Swing", "Pitch Focus", or "Fielding Play" layered
behind/next to it — report BOTH, don't skip the tactics card, since which
side boosted its power changes the actual outcome.

DO NOT REPORT THESE, they are not the faceoff:
  * Cards lying ON A BASE — the round medallions to the left and right of
    the middle, and the one above it. Those are BASE RUNNERS. They are
    face-up, they have names and power badges, and one of them can sit
    directly alongside the faceoff's tactics card. They are still runners.
  * The fan of cards along the BOTTOM EDGE of the screen. That is our hand.
  * Face-down cards — a dark card back with crossed bats. If the middle of
    the diamond holds face-down cards, the reveal has NOT happened yet.

If the faceoff is face-down, or the middle is empty, respond {"cards": []}.
Answering "nothing is revealed yet" is a CORRECT and useful answer; guessing
from whatever else is face-up on the table is not. Respond with ONLY a JSON
object:

{"cards": [
  {"kind": "player", "name": str, "power": int, "secondary": int},
  {"kind": "tactics", "name": str, "bonus": int, "paired_with": str}
]}

For a "player" entry: "power" is swing power (batter) or pitch focus
(pitcher); "secondary" is speed (batter) or fielding (pitcher), 0 if no
shield icon shown.

For a "tactics" entry: "bonus" is the number shown on that tactics
card. "paired_with" is the exact "name" of whichever player card it's
visually stacked/layered with — this is how the caller tells which
side a tactics card belongs to, so get this pairing right rather than
guessing which player it modifies.

Include only cards actually visible face-up right now — if just one
side's reveal is visible (the other hasn't happened yet, or already
resolved past it), include just that side's card(s); if none, respond
{"cards": []} instead of guessing.
"""


def extract_json(text: str) -> dict:
    """
    Pull the JSON object out of a model response. A plain prefix/suffix
    strip (the old `.removeprefix("```json")...` approach) breaks the
    moment the model adds any conversational filler before the code
    fence — flagged in review, 2026-08-23. Regex-searching for the
    outermost {...} is tolerant of that regardless of what surrounds it.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise json.JSONDecodeError("no JSON object found in response", text, 0)
    return json.loads(match.group(0))


SCREENSHOT_MEDIA_TYPE = "image/jpeg"
SCREENSHOT_MAX_WIDTH = 2000  # downscale target


# A FRACTION of image width, not pixels. 60px was ~3% of the 2000-wide capture
# it was tuned on, but the tile silently coarsens or fines as the capture size
# changes — at 1400 wide the same 60px is 4.3%, masking in noticeably bigger
# blocks. The ban-grid boxes just below were converted from pixels to fractions
# for this same reason after a review flagged it; this one was missed.
MASK_TILE_FRAC = 0.030
# TWO CONSUMERS, TWO MEASUREMENTS — do not merge these again.
#
# `MASK_CONTRAST_THRESHOLD` is used by mask_low_contrast_regions(), which takes
# PIL TILE MEANS over any frame. `BAN_LOCKED_CONTRAST_THRESHOLD` is used by
# detect_ban_grid_locked(), which takes a WHOLE-CELL mean of _local_contrast()
# on a ban frame. They measure different quantities on different inputs and
# only ever coincidentally shared a number.
#
# They were briefly unified at 124.0 while recalibrating the lock detector, and
# it silently regressed the masker: base crops on gameplay frames went from
# ~65-80% blacked out to ~95%. Exactly the failure mode this file already warns
# about for BAN_GRID_ROW_Y_FRAC vs BAN_CARD_ROW_TOP_FRAC — two independently
# measured constants that must not be "simplified" into one.
MASK_CONTRAST_THRESHOLD = 100.0

# Whole-cell contrast below this reads as a LOCKED (faded) ban-grid card.
#
# 124.0 is correct, but the reasoning first written here was not, and the
# correction matters more than the value. A wider study (411 ban frames, 3,610
# cells, each given an independent scroll position by reading the scrollbar
# thumb) found:
#
#   * The value is right, and worth MORE than first measured: 18 settled cells
#     false-unlock at 100.0 (not 6). Zero false readings in either direction at
#     124.0.
#   * There is NO "empty gap [106.5, 142.5]". 142 cells (3.5%) sit inside it.
#     It looks empty only if you restrict to player-card cells on settled
#     frames — which is what the first sample did. The distribution has a
#     sparse VALLEY, not a void, and a threshold placed by "midpoint of the
#     empty gap" was right by luck as much as by method.
#   * The dominant lifter is the BANNING PHASE banner (+50 on one measured
#     cell), not the ban cursor (+26). The banner sets the lower bound.
#   * What lives in the "gap" is mostly (6,3), a POWER SWING **tactics** card,
#     at 120.8-141.3 across 63 frames.
#
# Anything moving this constant should re-derive it from the full 411-frame set,
# not from settled player cells alone.
BAN_LOCKED_CONTRAST_THRESHOLD = 124.0
# Re-measured 2026-08-26 over ALL 95 cached ban frames (950 cells). The
# distribution is cleanly bimodal and the old 100.0 sat BELOW the real gap:
#     locked cluster   ... 106.5
#     <-- empty, 35.9 wide -->
#     unlocked cluster 142.5 ...
# 6 cells fell between 100.0 and 142.5 — every one a LOCKED card whose contrast
# was lifted by the ban cursor's highlight sitting on it (+20-26 measured on one
# physical card, Zachary Lee at (2,0), as the cursor moved on and off). Those
# read as UNLOCKED, making a card the player does not own a ban candidate.
#
# That matters more now than it used to: with TRUST_ROSTER_ONLY the lock
# detector is the ONLY live vision component left on the ban path, so a
# false-unlocked cell is not caught by anything downstream.
#
# 124.0 is the gap midpoint, so cursor-lifted locked cards (max 106.5) and
# genuine unlocked cards (min 142.5) both sit ~18 clear of it.  # normal cards measured ~170-187, faded ones ~52-56 — wide margin
MASK_KERNEL = 41  # roughly card-art scale at SCREENSHOT_MAX_WIDTH


def mask_low_contrast_regions(img):
    """
    Black out any region of the image with low local contrast, before it
    ever reaches the vision model.

    Root-cause fix for a real, costly failure class (2026-08-23, live on
    a less-complete collection): locked/not-yet-owned ban-screen cards
    render faded, with no legible name or stats. Rather than reliably
    reporting that as unreadable, the model sometimes "filled in" a
    guess instead — a blank name, the literal word "Unknown", or a fake
    power=0 — each of which needed its own reactive patch downstream in
    read_full_ban_collection(). Masking the ambiguous pixels out locally,
    in code, removes the whole failure class at the source instead of
    pattern-matching whatever specific guess the model happens to make
    next. Those downstream filters stay on as cheap defense-in-depth,
    but this is the actual fix.

    Local contrast = local max brightness minus local min brightness
    within a MASK_KERNEL-sized neighborhood (PIL Max/MinFilter), then
    averaged over MASK_TILE_FRAC-sized tiles. Verified live against a real ban
    screen: legible cards measured ~170-187, faded/locked cards ~52-56 —
    MASK_CONTRAST_THRESHOLD=100 sits with a wide margin between both.
    """
    gray = img.convert("L")
    # _local_contrast() is the SEPARABLE form of exactly this Max/Min pair —
    # same border handling, same answer. PIL's naive filters cost 13.73s per
    # 2000x1292 frame at MASK_KERNEL=41; the separable version costs 47ms.
    # Verified byte-identical — both the contrast array AND the final masked
    # image — on 17 real frames (7 ban-screen fixtures, 5 scan frames, 5
    # sampled gameplay frames). 290x.
    #
    # detect_ban_grid_locked() already made this switch; this call site was
    # simply missed. It is dead while TRUST_ROSTER_ONLY is on, which is why
    # nobody noticed — but it is a 13.7s landmine in the vision fallback, and
    # it was 40% of the offline test suite's runtime.
    contrast_arr = _local_contrast(np.asarray(gray), MASK_KERNEL).astype(np.uint8)

    result = img.convert("RGB").copy()
    draw = ImageDraw.Draw(result)
    w, h = img.size
    # NOT named `tile` — that name is already taken by the pixel array below,
    # and shadowing it made the box arithmetic operate on an ndarray.
    tile_px = max(8, int(w * MASK_TILE_FRAC))
    for y in range(0, h, tile_px):
        for x in range(0, w, tile_px):
            box = (x, y, min(x + tile_px, w), min(y + tile_px, h))
            tile = contrast_arr[box[1]:box[3], box[0]:box[2]]
            if tile.size and tile.mean() < MASK_CONTRAST_THRESHOLD:
                draw.rectangle(box, fill=(0, 0, 0))
    return result


# Ban-screen grid, calibrated live 2026-08-23 against the actual
# SCREENSHOT_MAX_WIDTH=2000 downscaled capture (see PENDING_LIVE_VALIDATION.md
# for the sampled contrast values that validated these boxes: every one
# of 10 cells across 2 rows landed either 51-64 [locked] or 160-180
# [normal], a huge margin either side of MASK_CONTRAST_THRESHOLD). Only
# 2 rows — a 3rd, partial row is visible but its card boundaries are cut
# off, too unreliable to measure confidently.
#
# Expressed as FRACTIONS of image width (not absolute pixels) — flagged
# in Gemini review, 2026-08-23: hardcoded pixel boxes silently misalign
# if the Chiaki-ng window is resized or display scaling changes. Row
# boundaries are also fractions of WIDTH rather than height on purpose:
# every screenshot this whole session has shown horizontal letterboxing
# (black bars top/bottom), so content position scales with width even
# when the letterbox thickness (and therefore height) varies. Verified
# these fractions reproduce the original pixel calibration exactly at
# 2000px width (290/2000=0.145, 270/2000=0.135, etc.) before adopting.
# Margin around the derived ban-grid bbox before it is sent to vision. Small
# but non-zero: a card's glow/selection highlight extends slightly past its box.
BAN_CROP_MARGIN = 0.015

BAN_GRID_COL_X_FRAC = [(0.145 + i * 0.135, 0.145 + i * 0.135 + 0.130) for i in range(5)]
BAN_GRID_ROW_Y_FRAC = [(0.195, 0.385), (0.395, 0.585)]


def _local_contrast(gray_arr, k):
    """max-minus-min over a k x k window. Separable, so O(n*k) not O(n*k^2).

    PIL's MaxFilter/MinFilter are the naive implementation, and at
    MASK_KERNEL=41 on a ban frame the pair cost **6.27 s** — measured, and run
    once per scroll iteration, so roughly 36 s of blind non-polling CPU per ban
    screen. A max over a square window is separable (max along rows, then along
    columns), which is the same answer for a fraction of the work: **22 ms**,
    291x faster, verified byte-for-byte equal on the sampled cells across 6 real
    ban frames.

    Border handling is deliberately the same as PIL's (0 for max, 255 for min)
    so the arrays match at the edges too — though the caller crops with a margin
    wider than the kernel radius, so no sampled cell ever sees the border.
    """
    pad = k // 2
    hi = np.pad(gray_arr, pad, mode="constant", constant_values=0)
    lo = np.pad(gray_arr, pad, mode="constant", constant_values=255)
    mx = sliding_window_view(hi, k, axis=1).max(-1)
    mx = sliding_window_view(mx, k, axis=0).max(-1)
    mn = sliding_window_view(lo, k, axis=1).min(-1)
    mn = sliding_window_view(mn, k, axis=0).min(-1)
    return mx.astype(np.int16) - mn.astype(np.int16)


LOCK_CONFIRM_TRIES = 4

# Attempts to read the BANNED CARDS counter before giving up. Bounded by the
# ban screen's remaining life: measured 4.20s / 5.69s / 5.85s across the three
# ban episodes of 2026-08-26 at the point the check runs, against ~0.26s per
# read. Five leaves a wide margin. A single read failed 1 of 3 matches on a
# counter that was legible the whole time.
BAN_COUNTER_READ_TRIES = 5

# Run the local-vs-vision read comparison on every Nth turn.
#
# This was 4, and the reason was cost: the hand half took 25.57s (measured)
# against 0.33s for the base crops, because the old reader reloaded the
# PaddleOCR models on every call. So one turn in four paid twenty-five seconds
# for a diagnostic that drives no decision -- and turn TIME is the thing this
# project is currently trying to cut.
#
# patch69 replaced that reader with local_hand, at 4.5 ms. The cost that
# justified sampling is gone, and every turn is now a labelled example of the
# tactics art the local reader still cannot read (vision supplies the label),
# so sampling would throw away three quarters of the corpus for nothing.
LOCAL_CHECK_EVERY = 1


def _settled_lock_grid(tries: int = LOCK_CONFIRM_TRIES):
    """Capture until two CONSECUTIVE lock reads agree; return (img, grid).

    A locked cell is detected by low contrast, so a cell that is merely DIM
    reads as locked — and the ban screen fades in. Measured over the
    2026-08-26 run: one ban screen's first two frames reported 6/10 and 4/10
    cells locked where the settled truth was 3/10, marking four cards the
    player OWNS as locked. Those cards are then absent from the candidate set
    and can never be banned, silently and with no error.

    Same prove-it-twice discipline as _learn_roster_entry(): one reading of a
    transient is a guess. Falls through after `tries` and returns the latest
    read rather than blocking — a still-animating grid is caught downstream by
    the scrollbar cross-check, and a ban screen that never settles must not
    wedge the run.
    """
    img = capture_screenshot_image()
    grid = detect_ban_grid_locked(img)
    for _ in range(tries):
        img2 = capture_screenshot_image()
        grid2 = detect_ban_grid_locked(img2)
        if grid2 == grid:
            return img2, grid2
        img, grid = img2, grid2
    print("  [ban] lock grid still changing after "
          f"{tries} reads — using the latest.")
    record_observation(event="lock_grid_unsettled", tries=tries)
    return img, grid


def detect_ban_grid_locked(img) -> list:
    """
    Returns a 2D list [row][col] of bool (2 rows x 5 cols) — True if
    that grid cell is a locked/faded card, False if it's legible.
    Computed entirely in code against the calibrated fractional boxes
    above, NOT inferred by the vision model.

    Root-cause fix for a real bug (2026-08-23): asking the model to
    track grid position around masked-out cards is unreliable — it
    silently shifted the remaining visible cards left to fill the gap
    instead of preserving their true columns, live-verified twice (once
    on the original approach, again after a prompt-only attempt to fix
    it). This function means the model never has to reason about
    position at all: we already know exactly which grid cells are
    populated before we even ask it to read anything, and just zip its
    ordered "what I can read" list onto our own known positions.
    """

    if USE_FITTED_BAN_GRID:
        import ban_grid as _bg
        rows = _fitted_ban_rows(img)
        if rows and len(rows) >= 2:
            # ban_grid's is_locked was re-censused over 20,360 cells on the fitted box;
            # this detector reads WIDTH fractions and its own note forbids unifying the
            # two. They disagree on 3 of 600 cells and the fitted one is right on all
            # three -- see the flag's comment.
            out = [[bool(_bg.is_locked(img, _bg.card_box(img, rows, r, c)))
                    for c in range(5)] for r in range(2)]
            return out
    w, h = img.size
    col_x = [(int(w * x0), int(w * x1)) for x0, x1 in BAN_GRID_COL_X_FRAC]
    row_y = [(int(w * y0), int(w * y1)) for y0, y1 in BAN_GRID_ROW_Y_FRAC]

    # Run the Max/Min filters over the GRID REGION ONLY, not the whole frame.
    # Two MaxFilter(41) passes over 2000x1292 cost ~13.8s per call, and this is
    # called once per scan iteration — roughly half the ban screen's measured
    # 149s. Only cells inside the grid are ever sampled, so the rest is wasted.
    #
    # EXACT, not approximate. A MaxFilter's output at a pixel depends only on
    # its MASK_KERNEL-radius neighbourhood, so cropping with a margin wider than
    # that radius leaves every sampled pixel bit-identical. Verified on 12 real
    # ban frames: 12/12 grids identical, 2.2x faster.
    #
    # Downscaling instead was tried and REJECTED: 1000px matched on one frame
    # but 0/12 across the set, and 1400px 8/12. MASK_KERNEL is calibrated to
    # this resolution (see its "card-art scale at SCREENSHOT_MAX_WIDTH" note);
    # scaling the image without recalibrating the threshold changes which cards
    # read as locked, i.e. which cards get banned.
    margin = MASK_KERNEL // 2 + 2
    gx0 = max(0, min(x for x, _ in col_x) - margin)
    gx1 = min(w, max(x for _, x in col_x) + margin)
    gy0 = max(0, min(y for y, _ in row_y) - margin)
    gy1 = min(h, max(y for _, y in row_y) + margin)

    gray = img.convert("L").crop((gx0, gy0, gx1, gy1))
    contrast_arr = _local_contrast(np.asarray(gray), MASK_KERNEL)

    grid = []
    for y0, y1 in row_y:
        row = []
        for x0, x1 in col_x:
            cell = contrast_arr[y0 - gy0:y1 - gy0, x0 - gx0:x1 - gx0]
            mean_contrast = cell.mean() if cell.size else 0
            row.append(mean_contrast < BAN_LOCKED_CONTRAST_THRESHOLD)
        grid.append(row)
    return grid


# BAN_GRID_ROW_Y_FRAC's boxes are deliberately short — sized just for
# detect_ban_grid_locked()'s contrast sampling, not the whole card. The
# full card (needed to reach the name banner) extends further down from
# each row's same top edge. Measured live 2026-08-24 against a real
# scrollable-grid capture (not the different "BANNED CARDS" summary
# screen, which has different proportions).
BAN_GRID_CARD_HEIGHT_FRAC = 0.40
BAN_CARD_NAME_STRIP_FRAC = (0.70, 1.0)

# N6 FIX: card-crop row tops, as fractions of HEIGHT, derived from the real
# measured row pitch (~366 px at 1292 px tall = 0.283).
#
# These are deliberately SEPARATE from BAN_GRID_ROW_Y_FRAC. That constant is
# consumed by detect_ban_grid_locked() as fractions of WIDTH, and reusing it
# here meant one constant carried two incompatible meanings — which gave an
# effective row pitch of 259 px against a true 366 px, so row 1's name banner
# drifted ~107 px down and sat flush against the bottom of its strip. Row 1
# had ZERO downward tolerance: a 10 px frame shift (0.8% of height) took it
# from 6/6 to 0/6, and inside the failure band it returned WRONG names rather
# than None — which is exactly what feeds the N1 mis-ban path.
BAN_CARD_ROW_TOP_FRAC = [0.195, 0.195 + 0.283]  # widened 2026-08-24: tightly-tuned
# (0.82, 0.96) worked on one frame but missed the name banner entirely on
# another real capture — small frame-to-frame vertical drift pushed it
# out of the narrow window. ocr_ban_card_name()'s per-line "pick the
# longest" selection already discards extra junk lines this wider crop
# picks up, so widening costs nothing and buys real margin.


# THE FITTED BAN GRID, BEHIND A FLAG AND OFF BY DEFAULT.
#
# Everything below this point identifies a card by WHERE IT SITS --
# KNOWN_BAN_ROSTER[(row, col)] with TRUST_ROSTER_ONLY on -- so a geometry that disagrees
# about which cell is which bans a DIFFERENT PHYSICAL CARD with no error raised. That is
# the $50 failure this file already records from a 110px window nudge, which is why this
# arrives as a flag and a measurement rather than a replacement.
#
# WHAT THE MEASUREMENT SAYS (agent_progress/ban-wiring/phase0_equivalence.py, 60 frames,
# 600 cells): the two geometries name DIFFERENT cards on ZERO cells. They agree on 141
# names and on 323 locked cells; the new path resolves one name the old one missed, and
# the old path calls three plainly OWNED cards LOCKED -- Johnny Drawers twice and Mama
# Jody Gain -- which quietly kept them out of choose_bans' candidate list.
#
# The rows are FITTED per frame rather than fixed, which is the whole point: CLAUDE.md
# records that BAN_CARD_ROW_TOP_FRAC is wrong because the rows MOVE with scroll, and that
# the shipped constant only ever worked by being loose enough to contain the card wherever
# it drifted.
# ON since 2026-09-13, and every phase of the comparison is above. The short version:
#   phase 0   600 cells, 60 frames   0 named differently; the SHIPPED locked-detector
#                                    calls three plainly owned cards locked and the fitted
#                                    one is right on all three
#   phase 2   offline A/B            273 identical, 4 gained, 0 regressions
#   phase 3   live, read only        46 identical, 6 gained, counter untouched
#   phase 4a  the REAL scan, live    23 cards old, 25 new, THE SAME THREE BANS -- and the
#                                    two extra are the pair phase 0 caught, found again by
#                                    a completely different route
# Nothing was ever named differently, at any stage, on any cell.
USE_FITTED_BAN_GRID = True

_FIT_MEMO = {"key": None, "rows": None}


# EVERY NUMBER IN ban_grid WAS MEASURED AT 16:9, AND ONLY AT 16:9. Its card height is
# derived as CARD_ASPECT * column_width * (w / h), so the frame's ASPECT is an input to the
# row fit -- and on a 2000x1292 frame (aspect 1.548) it fits rows at 0.382 / 0.710 where the
# true ones are at 0.195 / 0.478. It is not a little off; it is on different cards.
#
# The archived fixtures at that geometry caught this the moment the flag was flipped:
# test_ocr_ban_card went from 2 abstentions to 18. The live rig captures 2000x1125 and
# 1920x1080, both 16:9, so nothing in production was exposed -- but CLAUDE.md section 3 is
# explicit that a reader must be checked at BOTH geometries, and "it happens not to occur
# today" is how a rig change becomes a silent wrong answer later.
#
# So the fitted path applies where it was MEASURED and the shipped boxes handle the rest.
BAN_FIT_ASPECT = 16.0 / 9.0
BAN_FIT_ASPECT_TOL = 0.02        # 1.760-1.796; 1.548 is nowhere near it


def _ban_frame_is_16x9(img):
    w, h = img.size
    return abs(w / float(h) - BAN_FIT_ASPECT) <= BAN_FIT_ASPECT_TOL


def _fitted_ban_rows(img):
    """ban_grid's fitted rows for this frame, or None when it cannot fit one.

    Memoised on the image OBJECT, because the scan asks for the locked grid and then a crop
    per cell off the same capture, and fitting costs ~8 ms. One entry: a second frame
    evicts the first, so a stale fit cannot be served for a picture it did not come from.
    """
    try:
        import ban_grid as _bg
    except Exception:
        return None
    if not _ban_frame_is_16x9(img):
        return None                  # measured at 16:9 only -- see BAN_FIT_ASPECT
    key = (id(img), img.size)
    if _FIT_MEMO["key"] == key:
        return _FIT_MEMO["rows"]
    try:
        rows = _bg.find_card_rows(img)
    except Exception:
        rows = None
    _FIT_MEMO.update({"key": key, "rows": rows})
    return rows


def get_ban_grid_card_crop(img, rel_row: int, col: int):
    """Full single-card crop (through the name banner) for grid position
    (rel_row, col) within img — rel_row is 0/1 within the two visible
    rows, same convention as detect_ban_grid_locked()'s return grid."""
    if USE_FITTED_BAN_GRID:
        import ban_grid as _bg
        rows = _fitted_ban_rows(img)
        # FALL BACK RATHER THAN GUESS. A frame mid-scroll fits one row or none, and the
        # caller's whole contract is two rows indexed 0 and 1; answering with the old box
        # is a worse crop, answering with the wrong ROW is a wrong card.
        if rows and rel_row < len(rows):
            box = _bg.card_box(img, rows, rel_row, col)
            if box is not None:
                return img.crop(box)
    w, h = img.size
    x0, x1 = BAN_GRID_COL_X_FRAC[col]
    y0 = BAN_CARD_ROW_TOP_FRAC[rel_row]
    y1 = y0 + BAN_GRID_CARD_HEIGHT_FRAC
    # Uses BAN_CARD_ROW_TOP_FRAC (height fractions, true ~366 px row pitch) —
    # deliberately NOT BAN_GRID_ROW_Y_FRAC, which detect_ban_grid_locked()
    # reads as WIDTH fractions. The two are measured independently and must
    # stay that way; see the N6 note on BAN_CARD_ROW_TOP_FRAC. Do not "unify"
    # them: a height-aligned box straddles the lock-detection contrast
    # threshold (measured 85-139, vs a clean 50-80 locked / 150-179 unlocked
    # under the width reading), and a width-aligned card crop fails OCR
    # outright. Changing either requires re-running test_ocr_ban_card.py AND
    # re-verifying lock detection against known frames.
    return img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


def ocr_ban_card_name(card_img):
    """
    Local OCR (no vision call) of a full ban-grid card's name banner,
    resolved against the known roster via the same fuzzy match already
    proven for runner names. Returns the roster's PlayerCard (trusted
    power/secondary) or None if the OCR'd text doesn't confidently
    resolve to any known card — never guesses.

    Deliberately doesn't attempt the power/secondary badges directly:
    live testing 2026-08-24 found the power circle's digit font
    genuinely unreadable by tesseract regardless of crop precision or
    polarity (tested exhaustively, both light-on-dark and dark-on-light,
    7 thresholds x 5 psm modes, zero correct reads) — a font-recognition
    limitation, not a framing problem. The name banner uses a normal
    printed font and reads reliably; resolving via the roster sidesteps
    the unreadable badge entirely for any card already catalogued.
    """
    w, h = card_img.size
    y0, y1 = BAN_CARD_NAME_STRIP_FRAC
    strip = card_img.crop((0, int(h * y0), w, int(h * y1))).convert("L")
    strip = strip.resize((strip.width * 4, strip.height * 4))
    strip = ImageOps.invert(strip).point(lambda p: 255 if p > 190 else 0)
    text = _ocr_text(strip, ocr_glyphs.PSM_TEXT_BLOCK).strip()
    candidates = [" ".join(re.findall(r"[A-Za-z]{2,}", line)) for line in text.splitlines()]
    cleaned = max(candidates, key=len, default="")

    # N1: resolve STRICTLY. This function can only ever return a card already in
    # the roster, so a genuinely new card (row 6 cols 3-4 were never catalogued)
    # would otherwise be force-matched onto the nearest known name — measured:
    # 15 of 17 plausible unknown names resolved to a WRONG roster card
    # ('Frank Coker' -> 'Brian Coker'). That wrong card then fills roster_hits,
    # suppressing the vision read that would have corrected it, and can put a
    # duplicate into the grid. Refusing here simply falls through to vision,
    # which is the correct behaviour for an uncatalogued position.
    # min_margin: found missing 2026-09-03. match_roster_name()'s whole-string
    # pass documents that it force-matches a short or garbled read onto one of
    # a near-identical family ("Brown" -> Mickey Brown of two, "Jody Gain" ->
    # Joe Jody Gain of four) and says callers that cannot afford a coin flip
    # must pass min_margin. THIS caller is the one that cannot afford it — its
    # answer bans a physical card — and it was the only one not passing it.
    # Measured on the original code: 'MAPA JODY GAIN' resolved to Papa Jody
    # Gain and 'XAMA JODY GAIN' to Mama Jody Gain, both at margin 0.000, so a
    # single misread letter in the first word decided which of four real cards
    # got banned. The value is the same 0.10 the second pass uses, and the same
    # one ROSTER_CONFIDENT_MARGIN was measured at.
    hit = match_roster_name(cleaned, cutoff=0.85, allow_surname_fallback=False,
                            min_margin=BAN_OCR_KEY_MARGIN)
    if hit is not None:
        return hit

    # SECOND pass, reached only after the first has refused, so it is strictly
    # additive: every card that resolved before still resolves the same way and
    # only abstentions can change. It compares on ocr_match_key() instead of
    # the raw text, which stops this font's measured separator damage (fused
    # words, dropped hyphens and nickname quotes — 50 of the 64 aligned reads)
    # from counting as character error, and it adds the runner-up margin the
    # whole-string path never had.
    #
    # Measured over 110 real ban-grid cells: 59 -> 63 resolved, 0 wrong either
    # way, abstention 46.4% -> 42.7%. All four recoveries are cards the frame
    # genuinely shows ('JOSHUADIAZ ss', 'SOSHUADIAZ ss', 'JOEJOOYGAIN',
    # 'oanige THE RAT TA TRAN CRUZ'). The remaining abstentions are 39 cells
    # with no legible banner at all (locked cards, and the one the PLAY prompt
    # covers) plus 8 reads too fragmentary to identify — 'OHNNY' fits three
    # different Johnnys, 'BLAZE' two.
    #
    # Ordering note: on that corpus the second pass turned out to DOMINATE the
    # first — 59 cells resolved by both with zero disagreements, 4 by the key
    # alone, 0 by the direct matcher alone. So the order is not what makes this
    # correct; it is what makes the change strictly additive, which is a much
    # smaller claim than "the new matcher is equivalent to the old one on every
    # input". The direct pass also compares the RAW text, spaces and
    # punctuation included, which is genuinely different evidence. Keep both.
    hit = match_roster_name_ocr(cleaned)
    if hit is not None:
        return hit

    # THIRD pass: a vision model on the LAN, reached ONLY after both local
    # passes have refused. Strictly additive for the same reason the second
    # pass is -- every cell that resolved above still resolves identically, and
    # only abstentions can change.
    #
    # What it replaces is not tesseract, it is the PAID vision call this
    # function's abstention currently falls through to. Measured over these
    # same 110 cells: 63 -> 95 resolved, 0 wrong either way. See vlm_ocr.py for
    # the numbers, the crop trap, and why every failure path abstains.
    return _vlm_ban_card(card_img)


def _vlm_ban_card(card_img):
    """Resolve one ban-grid card through the LAN vision model, or None.

    THE ROSTER LOOKUP LIVES HERE, not in vlm_ocr, so there is exactly one place
    that turns text into a card to ban. A name that maps to two DIFFERENT cards
    abstains: the roster holds families of near-identical names (four Jody
    Gains, two Mickey Browns) and picking between them on a name alone is the
    coin flip BAN_OCR_KEY_MARGIN exists to refuse.
    """
    try:
        import vlm_ocr
        by_name = {}
        for card in KNOWN_BAN_ROSTER.values():
            by_name.setdefault(card.name, set()).add(
                (card.name, card.power, card.secondary))
        text = vlm_ocr.read_card_text(card_img)
        name = vlm_ocr.resolve_against(text, list(by_name))
        if name is None or len(by_name.get(name, ())) != 1:
            return None
        for card in KNOWN_BAN_ROSTER.values():
            if card.name == name:
                return card
        return None
    except Exception:
        # Never let this path raise into a match. It is an optional extra rung
        # on a ladder that worked without it.
        return None


def _read_ban_rows_separately(masked_img, expected_positions):
    """Re-read the grid ONE ROW AT A TIME; returns cards or None.

    Only called after a combined read disagrees with the lock detector. Costs
    more tokens than the combined read (measured: 167+168 vs 268), which is
    exactly why it is not the default — but it isolates the failure, so a row
    that reads cleanly is kept even when the other does not.

    Returns None if the per-row totals still do not add up, leaving the
    caller's existing skip-the-batch path to handle it.
    """
    want_by_row = collections.Counter(r for r, _ in expected_positions)
    out = []
    for rel_row in sorted(want_by_row):
        try:
            raw = read_ban_row_cards(masked_img, only_row=rel_row)
        except Exception as e:
            print(f"  [ban] per-row read failed on row {rel_row}: {e}")
            return None
        good = [
            c for c in raw
            if c.get("name") and norm_name(c["name"]) not in PLACEHOLDER_CARD_NAMES
            and c["name"] not in KNOWN_TACTICS_NAMES
            and isinstance(c.get("power"), int) and c["power"] > 0
            and isinstance(c.get("secondary"), int)
        ]
        if len(good) != want_by_row[rel_row]:
            print(f"  [ban] row {rel_row}: expected {want_by_row[rel_row]}, "
                  f"got {len(good)} — this row is not usable")
            return None
        out.extend(good)
    print(f"  [ban] per-row retry recovered all {len(out)} cards")
    return out


def read_ban_row_cards(masked_img, only_row: int = None) -> list:
    """
    Ask the model for an ordered (reading-order) list of the legible
    cards visible in `masked_img` (a mask_low_contrast_regions()-ed
    frame) — no position reported, see READ_BAN_ROW_CARDS_PROMPT. Paired
    with detect_ban_grid_locked(), run by the caller against the SAME
    underlying capture, to assign real positions in code. Takes the
    image directly (rather than capturing its own) so both functions
    share one screenshot instead of risking two different moments.
    """
    # Send only the card grid, not the whole screen. Measured 2026-08-25 on a
    # real ban frame: full masked frame ~386 image tokens, grid-only ~211 — a
    # 45% cut, on the one call the ban screen makes repeatedly.
    #
    # The box is DERIVED from the same geometry constants the crops and lock
    # detection use, never hand-typed. A hand-picked x1=0.78 clipped column 4
    # (which ends at 0.815) and would have silently hidden a fifth of every row
    # from the model — the kind of error that reads as "the model missed a
    # card" rather than as a cropping bug.
    x0 = min(a for a, _ in BAN_GRID_COL_X_FRAC) - BAN_CROP_MARGIN
    x1 = max(b for _, b in BAN_GRID_COL_X_FRAC) + BAN_CROP_MARGIN
    if only_row is None:
        y0 = min(BAN_CARD_ROW_TOP_FRAC) - BAN_CROP_MARGIN
        y1 = max(BAN_CARD_ROW_TOP_FRAC) + BAN_GRID_CARD_HEIGHT_FRAC + BAN_CROP_MARGIN
    else:
        # Single row — used only by the per-row retry path.
        y0 = BAN_CARD_ROW_TOP_FRAC[only_row] - BAN_CROP_MARGIN
        y1 = BAN_CARD_ROW_TOP_FRAC[only_row] + BAN_GRID_CARD_HEIGHT_FRAC + BAN_CROP_MARGIN
    w, h = masked_img.size
    grid_only = masked_img.crop((max(0, int(w * x0)), max(0, int(h * y0)),
                                 min(w, int(w * x1)), min(h, int(h * y1))))
    buf = io.BytesIO()
    grid_only.convert("RGB").save(buf, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        thinking={"type": "disabled"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": SCREENSHOT_MEDIA_TYPE, "data": img_b64}},
                {"type": "text", "text": READ_BAN_ROW_CARDS_PROMPT},
            ],
        }],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return extract_json(text).get("cards", [])


def capture_screenshot_image():
    """
    Bring Chiaki-ng to the front and grab+downscale the current screen as
    a raw PIL Image (no masking, no encoding) — the shared first step
    behind capture_screenshot_b64() and read_full_ban_collection(), which
    both need the same captured frame (one to encode for the API, one to
    run detect_ban_grid_locked() against locally) without paying for two
    separate screenshots of what could be two different moments.

    Without the explicit focus call, a screenshot taken while some other
    window (e.g. the Claude app, if you're actively chatting mid-run)
    happens to be in front captures the WRONG window entirely — read as
    an "other"/unrecognized screen, wasting a full API call plus a retry
    backoff for nothing. Confirmed live 2026-08-23 as a real contributor
    to the loop feeling like it "waits for a long time before doing
    anything." The 0.15s settle delay matches the same focus-race fix
    already applied to press() in input_controller.py.
    """
    # Capture the GAME WINDOW, not the whole desktop. pyautogui.screenshot()
    # returns the main display, which is the laptop screen here — so with the
    # game on an external monitor this was sending pictures of the editor to the
    # vision model, which duly reported "other" and stalled the run.
    import game_capture
    img = game_capture.grab()
    event_log.log_event("capture", where="capture_screenshot_image",
                        dump=img is not None, img_seq=(img.info.get("dump_seq") if img is not None else None))
    if img is None:
        focus_chiaki_window()
        time.sleep(0.15)
        img = pyautogui.screenshot().convert("RGB")
    if img.width > SCREENSHOT_MAX_WIDTH:
        ratio = SCREENSHOT_MAX_WIDTH / img.width
        img = img.resize((SCREENSHOT_MAX_WIDTH, int(img.height * ratio)))
    return img


# ponytail: TEMPORARY diagnostic logging, not a permanent feature — same
# category as MATCH_LOG_FILE above, rip out once it's answered its
# questions. Two live, currently-unresolved things this session couldn't
# settle from static test photos alone: (1) whether the hand-card fan
# layout's edge-slot position/scale jitter (found comparing two manual,
# never-settled screenshots — see LOCAL_VISION_EXPERIMENTS.md) is a
# real problem in the pipeline's own settled captures, and (2) general
# ground truth for tuning crop regions / OCR / matching against real,
# consistently-captured frames instead of found and manual photos.
#
# Runs on a genuine ~1s wall-clock cadence in its own daemon thread,
# specifically NOT reusing capture_screenshot_image()'s focus_chiaki_window()
# call — forcing window focus every single second would yank focus away
# from whatever the user is doing (e.g. reading this chat) the moment
# they alt-tab away mid-run, which is a worse cost than an occasional
# logged frame of the wrong window. This is pure side-channel logging: it
# never feeds into any read/decision, so a wrong-window frame here just
# means that one frame isn't useful, not that anything breaks. Frames are
# downscaled the same way capture_screenshot_image() does, so what's
# logged matches what the real pipeline would have seen.
#
# REMOVAL PLAN: once the jitter question is answered and crop/OCR/match
# tuning has enough real reference frames, delete SCREENSHOT_LOG_DIR,
# start_screenshot_logger(), _screenshot_logger_loop(), the `threading`
# import if nothing else needs it, and the log_screenshots parameter
# (and its start_screenshot_logger() call) in run().
# Overridable because the project can live on a NAS, and this writes at
# SCREENSHOT_LOG_INTERVAL (10Hz) inside a timing-sensitive loop — point it
# at a local disk there: BASEBALL_LOG_DIR=/tmp/bb_log python3 run_testing.py
SCREENSHOT_LOG_DIR = os.environ.get("BASEBALL_LOG_DIR", "screenshot_log")
# Each run writes into its own SCREENSHOT_LOG_DIR/<start-time>/ subfolder.
# Flat-into-one-directory meant every session's frames piled into the same
# 1811-file heap with only the filename timestamp to separate them, so "which
# frames came from the run that stalled" was a manual sort every time.
#
# Existing loose *.jpg at the top level are LEFT WHERE THEY ARE on purpose:
# test_ocr_ban_card.py and test_gameplay_regions.py reference specific frames
# by path, and the settle/reveal thresholds were all measured against that
# corpus. Moving it would invalidate the calibration record and break tests for
# a tidiness gain. New runs are foldered; the old flat corpus stays flat.
#
# Set by start_screenshot_logger() at run start.
_screenshot_run_dir = SCREENSHOT_LOG_DIR
# I9: at 10Hz this writes ~2 MB/s (~8 GB/hour) — an overnight run would fill
# the volume, and the logger swallows exceptions so ENOSPC would be invisible.
# Cap the directory and prune oldest-first.
SCREENSHOT_LOG_MAX_FILES = 20000
# How many past run_* folders to keep. At 0.1s a run writes ~4.6 GB, and nothing
# used to remove them. Never applies to the loose *.jpg calibration corpus.
SCREENSHOT_KEEP_RUNS = 3        # ~30 min at 10Hz
SCREENSHOT_LOG_PRUNE_EVERY = 200        # check every N frames, not every frame
SCREENSHOT_LOG_INTERVAL = 0.1  # seconds (10Hz) — bumped up three times
# tonight (1s -> 2s -> 0.5s -> 0.2s -> 0.1s interval): the slower cadences
# missed several short-lived screens entirely (draw/defeat result
# overlays, a "ROUND N" transition), never caught in the log, only
# inferred after the fact. Faster capture trades more disk usage for a
# much better chance of actually landing on those moments. At
# ~200KB/frame this is ~2MB/s (~120MB/min) — watch disk usage closely,
# this is getting fast enough to matter over anything but a short session.


def _prune_screenshot_log():
    """Keep THIS RUN's screenshot folder under its file cap, oldest-first.

    Scoped to the current run's folder, never the whole corpus — pruning across
    runs could delete the reference frames the thresholds were calibrated on.
    """
    try:
        files = sorted(f for f in os.listdir(_screenshot_run_dir) if f.endswith(".jpg"))
        excess = len(files) - SCREENSHOT_LOG_MAX_FILES
        for f in files[:max(0, excess)]:
            try:
                os.remove(os.path.join(_screenshot_run_dir, f))
            except OSError:
                pass
    except OSError:
        pass


def _screenshot_logger_loop(stop_event: threading.Event):
    os.makedirs(_screenshot_run_dir, exist_ok=True)
    frames = 0
    failures = 0
    while not stop_event.is_set():
        start = time.time()
        try:
            # THE GAME WINDOW, not the desktop. This loop deliberately does not
            # focus the window (focusing every second would yank the user out of
            # whatever they are doing), which meant pyautogui.screenshot() was
            # capturing the primary display — the laptop screen. On a two-monitor
            # setup with the game on the external, that is a 1Hz recording of the
            # user's own work, saved to disk, and useless as diagnostics besides.
            # record_demo.py already carries this same warning.
            import game_capture
            img = game_capture.grab() or pyautogui.screenshot()
            if img.width > SCREENSHOT_MAX_WIDTH:
                ratio = SCREENSHOT_MAX_WIDTH / img.width
                img = img.resize((SCREENSHOT_MAX_WIDTH, int(img.height * ratio)))
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(start)) + f"_{int(start * 1000) % 1000:03d}"
            img.convert("RGB").save(os.path.join(_screenshot_run_dir, f"{ts}.jpg"), format="JPEG", quality=80)
            frames += 1
            failures = 0
            if frames % SCREENSHOT_LOG_PRUNE_EVERY == 0:
                _prune_screenshot_log()
        except Exception as e:
            # Best-effort logging must never take down the real loop — but a
            # persistent failure (e.g. ENOSPC) must not be silent either.
            # N4: throttle on a FAILURE counter. The previous version keyed on
            # `frames`, which only advances on success, so a persistent failure
            # was either permanently silent or spammed at full rate.
            failures += 1
            if failures == 1 or failures % 100 == 0:
                print(f"[screenshot-logger] write failed x{failures} ({e})")
        elapsed = time.time() - start
        stop_event.wait(max(0.0, SCREENSHOT_LOG_INTERVAL - elapsed))


def _prune_old_run_folders(keep: int = SCREENSHOT_KEEP_RUNS):
    """Delete all but the `keep` most recent run_* folders.

    At 0.1s the logger writes ~4.6 GB per run and nothing ever removed old run
    folders, so disk use grew without bound across sessions.

    ONLY touches directories matching `run_YYYYmmdd_HHMMSS`. The loose *.jpg at
    the top of SCREENSHOT_LOG_DIR are the CALIBRATION CORPUS — every settle,
    reveal and lock threshold in this file was measured against them, and
    test_ocr_ban_card / test_gameplay_regions / test_ban_scan reference specific
    frames by name. Deleting those would silently invalidate the calibration
    record and turn several tests into no-ops, so this cannot reach them.
    """
    try:
        runs = sorted(d for d in os.listdir(SCREENSHOT_LOG_DIR)
                      if re.fullmatch(r"run_\d{8}_\d{6}", d)
                      and os.path.isdir(os.path.join(SCREENSHOT_LOG_DIR, d)))
        for stale in runs[:max(0, len(runs) - keep)]:
            path = os.path.join(SCREENSHOT_LOG_DIR, stale)
            n = len([f for f in os.listdir(path) if f.endswith(".jpg")])
            shutil.rmtree(path, ignore_errors=True)
            print(f"  [screenshots] pruned old run folder {stale}/ ({n} frames)")
    except Exception as e:                                   # pragma: no cover
        print(f"  [screenshots] could not prune old run folders: {e}")


def start_screenshot_logger() -> threading.Event:
    """Starts the background screenshot logger (SCREENSHOT_LOG_INTERVAL); returns the Event
    that stops it (set it, or just let the daemon thread die with the
    process — either is fine for a diagnostic session)."""
    global _screenshot_run_dir
    # One folder per run, named by start time, so "which frames came from the
    # run that stalled" stops being a manual sort through a shared heap.
    _screenshot_run_dir = os.path.join(SCREENSHOT_LOG_DIR,
                                       time.strftime("run_%Y%m%d_%H%M%S"))
    os.makedirs(_screenshot_run_dir, exist_ok=True)
    _prune_old_run_folders()
    stop_event = threading.Event()
    thread = threading.Thread(target=_screenshot_logger_loop, args=(stop_event,), daemon=True)
    thread.start()
    print(f"Screenshot logger running — saving to {_screenshot_run_dir}/ "
          f"every {SCREENSHOT_LOG_INTERVAL}s.")
    return stop_event


def capture_screenshot_b64(mask_low_contrast: bool = False) -> str:
    """
    capture_screenshot_image(), optionally masked, encoded as base64 JPEG.

    A full-resolution PNG of a busy screen (e.g. the ban grid, dense card
    art) can exceed the API's 10MB image limit — hit live on 2026-08-23.
    Downscaling + JPEG keeps this comfortably under that regardless of
    screen content, and text/numbers stay plenty legible at this width.

    mask_low_contrast=True runs mask_low_contrast_regions() before
    encoding — opt-in, not the default, since it's calibrated for the
    ban screen specifically and hasn't been checked against every other
    screen type (a legitimately low-contrast but still-relevant region
    elsewhere could get blacked out unintentionally).
    """
    img = capture_screenshot_image()
    if mask_low_contrast:
        img = mask_low_contrast_regions(img)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# Fractional (x0, y0, x1, y1) crops of the in-match "turn" screen,
# calibrated live 2026-08-24 against real screenshots at multiple
# resolutions/aspect ratios (both the pipeline's own ~1999x1292 capture
# and manually-taken ~3360x2120 screenshots) — see PENDING_LIVE_VALIDATION.md
# item #10-12 for what's still unconfirmed. Coordinates are fractions of
# (width, height), same reasoning as BAN_GRID_COL_X_FRAC: this game
# letterboxes horizontally, so content position scales with width even
# when letterbox thickness (and therefore height) varies.
#
# first_base/second_base/third_base are centered on the diamond's coin
# markers, not on wherever a card happened to be sitting in one photo —
# a real bug caught live: the original third_base box was centered on
# the ALWAYS-face-down pitcher-indicator card next to it instead of the
# actual base coin, silently misreading an empty base as a phantom
# runner. When a base is empty, only the bare coin is visible in its
# box; when occupied, the runner's card sits at that same position.
GAMEPLAY_REGIONS_FRAC = {
    "scoreboard": (0.018, 0.175, 0.205, 0.405),
    # y0 lowered from 0.770 to 0.716 (~70px more headroom at 1292px tall)
    # on 2026-08-24. Hovering ENLARGES the selected card in place and
    # pushes its power badge above the old crop's top edge — found in all
    # four independent labelling passes (78 of 151 usable frames had a
    # raised card; 52 had a badge clipped). Measured effect on local OCR
    # against ground truth: hands parsed exactly right 6/13 -> 9/13,
    # false negatives 13 -> 3. See LOCAL_VISION_EXPERIMENTS.md §21.
    "hand": (0.250, 0.716, 0.760, 1.000),
    # MEASURED 2026-09-09 from recorded frames, not from the crops: a base CARD sits at
    # y 0.299..0.494 while these boxes started at 0.320, so the card's top -- its banner
    # and its power disc -- fell OUTSIDE and 0.038 of the box was bare table below. The
    # user spotted it by eye on both bases before it was measured. second_base is not
    # touched: it has a different vertical placement and reads correctly.
    "third_base": (0.3225, 0.290, 0.4375, 0.500),
    "first_base": (0.550, 0.290, 0.665, 0.500),
    "second_base": (0.430, 0.080, 0.580, 0.320),
}

# The coarse full-frame overview only needs to be legible enough to tell
# screens apart (turn vs. ban_screen vs. match_start_prompt vs. ...) and
# to read the WINNER/LOSER banner text — none of which needs the fine
# detail SCREENSHOT_MAX_WIDTH keeps for the targeted crops above. Kept
# separate and smaller specifically to cut vision-token cost.
OVERVIEW_MAX_WIDTH = 900


def crop_gameplay_regions(img) -> list:
    """Returns [(label, PIL.Image), ...] for every region in
    GAMEPLAY_REGIONS_FRAC, cropped from img at img's own resolution."""
    w, h = img.size
    return [
        (label, img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1))))
        for label, (x0, y0, x1, y1) in GAMEPLAY_REGIONS_FRAC.items()
    ]


def ocr_scoreboard(scoreboard_img) -> dict:
    """
    Local OCR (tesseract, no vision API call) of the scoreboard crop's
    two score rows. Returns {"your": [round1, round2, total],
    "opponent": [round1, round2, total]} — either value is None if that
    row couldn't be parsed (e.g. "ROUND"/"DISCARDS" dot rows, which this
    deliberately ignores since dot-counting isn't an OCR problem).
    Verified 2026-08-24 against 3 real screenshots (different save
    states), exact match on all 6 numbers every time.

    First step of moving off the vision API for the highest-value,
    easiest-to-verify field (clean printed digits) — not yet wired into
    read_game_state()/GameState. Proven locally first, integrate once
    it's been checked against more real screens, per the same
    prove-it-before-you-trust-it approach as detect_ban_grid_locked().

    Tesseract reads this font's "0" as the letter "O" about half the
    time — cheaper to treat O/o/Q as 0 when parsing than to fight the
    OCR engine for a cleaner read.
    """
    text = _ocr_text(scoreboard_img, ocr_glyphs.PSM_TEXT_BLOCK)
    result = {"your": None, "opponent": None}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.upper().startswith(("ROUND", "DISCARDS")):
            continue
        nums = [t for t in line.split() if re.fullmatch(r"[0-9OoQ]", t)]
        if len(nums) < 3:
            continue
        nums = [int(n.upper().replace("O", "0").replace("Q", "0")) for n in nums[-3:]]
        if line.upper().startswith("OPPONENT"):
            result["opponent"] = nums
        elif result["your"] is None:
            result["your"] = nums
    return result


def _encode_jpeg_b64(img) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


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


def capture_state_images_b64(mask_low_contrast: bool = False) -> list:
    """
    One screenshot, split into a cheap low-res overview (for screen-type
    classification, which needs to see the whole layout but not fine
    detail) plus sharp crops of just the fields that need precise
    reading when screen == "turn"/"discard_prompt"/"result". Replacing
    a single ~2000px-wide full-frame image with this combination cuts
    roughly 55-60% of the image tokens read_game_state() pays per call
    (measured 2026-08-24: ~3444 tokens full-frame vs. ~1400 combined),
    without losing the ability to recognize non-turn screens (ban_screen,
    match_start_prompt, etc.), which the crops alone can't do since
    they're calibrated only for the turn screen's layout.

    Returns [(label, b64_jpeg_str), ...] — "overview" first, then one
    entry per GAMEPLAY_REGIONS_FRAC key.
    """
    img = capture_screenshot_image()
    if mask_low_contrast:
        img = mask_low_contrast_regions(img)

    overview = img
    if overview.width > OVERVIEW_MAX_WIDTH:
        ratio = OVERVIEW_MAX_WIDTH / overview.width
        overview = overview.resize((OVERVIEW_MAX_WIDTH, int(overview.height * ratio)))

    global _last_gameplay_crops
    crops = crop_gameplay_regions(img)
    _last_gameplay_crops = dict(crops)  # stashed for log_local_read_comparison()'s ponytail:
                                        # diagnostic use — same frame, no second screenshot

    images = [("overview", _encode_jpeg_b64(overview))]
    images += [(label, _encode_jpeg_b64(crop)) for label, crop in crops]
    return images


_last_gameplay_crops = {}


# ponytail: TEMPORARY diagnostic, not wired into any decision — logs what
# the local OCR/hand-matcher tools would have said, next to what vision
# actually said, so the two can be eyeballed against each other over a
# real live session before either is trusted to replace vision for real.
# Never raises into the real loop (best-effort try/except at the call
# site in run()). REMOVAL PLAN: once local-vs-vision agreement has been
# checked over enough real turns, either wire the local read in for real
# (replacing the relevant vision call) or delete this function, its
# _last_gameplay_crops plumbing above, and the compare_local_reads
# parameter/call in run().
def _describe_vision_card(v):
    if v and v.get("kind") == "player":
        return f"power={v.get('power')} sec={v.get('secondary')}"
    if v:
        return f"tactics {v.get('name')!r} bonus={v.get('bonus')}"
    return "None"


# Where each sampled turn's hand crop and both readings are kept. Vision's
# answer is the LABEL, so this directory accumulates labelled tactics art --
# the one thing the local reader still cannot read (see the note below).
# Appended to, never rewritten: a truncating write loses a whole session's
# corpus if the run is interrupted.
LOCAL_HAND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "overnight", "local_hand")


# The five gameplay regions, all of which the paid call has just answered for. Saving only
# the hand meant three of the four remaining local readers had no corpus at all.
RECORDED_CROPS = ("hand", "scoreboard", "third_base", "first_base", "second_base")


def record_local_hand(crops, rows, state_json):
    """Keep one labelled example of EVERY gameplay region. Never raises into the turn loop.

    `crops` is the gameplay crop dict and `state_json` the paid model's whole answer, which
    is the LABEL for all of it -- names and phase for the banner reader, runners for the
    base reader, discards_left for the dot counter, secondary for the shield.
    """
    try:
        os.makedirs(LOCAL_HAND_DIR, exist_ok=True)
        stamp = time.time_ns()
        saved = {}
        for region in RECORDED_CROPS:
            img = (crops or {}).get(region)
            if img is None:
                continue
            fname = f"{region}_{stamp}.png"
            img.save(os.path.join(LOCAL_HAND_DIR, fname))
            saved[region] = fname
        cards = state_json.get("hand") or []
        with open(os.path.join(LOCAL_HAND_DIR, "agreement.jsonl"), "a") as f:
            f.write(json.dumps({
                # "crop", "local" and "vision" keep their exact original shape: every
                # analysis script written against the hands already on disk still reads.
                "t": stamp, "crop": saved.get("hand"), "crops": saved,
                "local": [{"x": r["x"], "kind": r["kind"], "digit": r["digit"],
                           "score": r["score"], "type": r.get("type"),
                           "type_score": r.get("type_score")} for r in rows],
                "vision": [{"i": c.get("hand_index"), "kind": c.get("kind"),
                            "name": c.get("name"),
                            "power": c.get("power"), "secondary": c.get("secondary"),
                            "bonus": c.get("bonus"), "type": c.get("type")}
                           for c in cards],
                "state": {"screen": state_json.get("screen"),
                          "phase": state_json.get("phase"),
                          "your_score": state_json.get("your_score"),
                          "opp_score": state_json.get("opp_score"),
                          "discards_left": state_json.get("discards_left"),
                          "batters_used": state_json.get("batters_used"),
                          "runners": state_json.get("runners")},
            }) + "\n")
    except Exception:
        pass


def log_local_read_comparison(state_json: dict):
    if state_json.get("screen") not in ("turn", "discard_prompt"):
        return
    crops = _last_gameplay_crops
    if not crops:
        return

    if "scoreboard" in crops:
        local_score = ocr_scoreboard(crops["scoreboard"])
        print(f"  [local-check] scoreboard OCR: {local_score}  "
              f"vs vision: your={state_json.get('your_score')} opp={state_json.get('opp_score')}")

    for base in ("third_base", "first_base", "second_base"):
        if base in crops:
            card = ocr_runner_card(crops[base])
            label = f"{card.name} (pwr={card.power} sec={card.secondary})" if card else "empty"
            print(f"  [local-check] {base}: {label}")
    print(f"  [local-check] vision runners: {state_json.get('runners')}")

    if "hand" in crops:
        # THE LOCAL HAND READER, run beside vision on every sampled turn.
        #
        # It replaces a PaddleOCR subprocess that reloaded its models on every
        # call. Measured on the same 15 corpus hands: 4.5 ms against seconds,
        # 45 of 55 card positions read, and ZERO disagreements with the paid
        # model. It ABSTAINS rather than guessing, so a position it cannot read
        # comes back None and is reported as NOT READ -- never as a value.
        #
        # WHY IT RUNS BESIDE VISION AND NOT INSTEAD OF IT. A tactics card's
        # decision needs its TYPE, not its number: CLAUDE.md section 4 records
        # that only swing and pitch boosts add power, while speed and fielding
        # boosts carry a nonzero bonus that adds NONE. The type is card art
        # this reader does not read, and 14 of the 15 measured hands hold at
        # least one tactics card -- so dropping the vision call today would
        # lose the type on almost every hand and change which card gets played.
        #
        # So every sampled turn records the crop and BOTH readings. Vision's
        # answer is the label, which makes each turn a labelled example of the
        # tactics art the type reader still needs. That is the cheapest
        # possible way to build the corpus: it rides on turns already paid for.
        import local_hand
        vision_hand = {c.get("hand_index"): c for c in (state_json.get("hand") or [])}
        try:
            rows = local_hand.read_hand(crops["hand"])
        except Exception as e:
            print(f"  [local-check] hand: local reader failed ({e})")
            rows = []
        record_local_hand(crops, rows, state_json)

        # ALIGNMENT IS BY POSITION, so it is only valid when the counts match.
        # A missed or invented card shifts every later column by one and would
        # print four spurious disagreements for one real error, which is
        # exactly the noise that made the previous reader's audit unreadable.
        if len(rows) != len(vision_hand):
            print(f"  [local-check] hand: local found {len(rows)} positions, vision "
                  f"{len(vision_hand)} — counts differ, no per-slot comparison")
        else:
            lines = []
            for i, r in enumerate(rows):
                v = vision_hand.get(i)
                if r["kind"] == "tactics" or r["digit"] is None:
                    continue                      # abstained: nothing to disagree with
                if not v or v.get("kind") != "player":
                    lines.append(f"  [local-check] hand[{i}]: local read {r['digit']} "
                                 f"@{r['score']} but vision says "
                                 f"{_describe_vision_card(v)}  <<< DISAGREE")
                elif str(v.get("power")) != str(r["digit"]):
                    lines.append(f"  [local-check] hand[{i}]: local power={r['digit']} "
                                 f"@{r['score']}  vs vision power={v.get('power')}"
                                 f"  <<< DISAGREE")
            read = sum(1 for r in rows if r["digit"] is not None)
            if lines:
                for line in lines:
                    print(line)
            else:
                print(f"  [local-check] hand: {read}/{len(rows)} read locally, "
                      f"all agree with vision")


# Fractional (x0, y0, x1, y1) crop of the full screenshot used for
# animation-stability polling — the scoreboard + card-matchup area only.
# Deliberately excludes the edges of the screen, where this game has
# ambient background animation (flickering lights, sparkle particles)
# even on an otherwise-settled turn, which would otherwise stop a naive
# full-frame diff from ever reading as "stable".
ANIMATION_ROI_FRACTION = (0.0, 0.15, 0.75, 0.65)
DIFF_THRESHOLD = 6.0  # average per-pixel grayscale delta below this counts as "unchanged"

# --- Region-aware settling -------------------------------------------------
#
# ROOT-CAUSE FIX (2026-08-25). ANIMATION_ROI_FRACTION spans y 0.15-0.65. The
# hand — the region every turn decision is actually read from — spans
# y 0.716-1.0. They do not overlap AT ALL, so the settle detector never
# observed the hand: it could declare "settled" while cards were still flying
# into it. Measured on real 10Hz capture, the hand region peaks at 56.2 mean
# per-pixel delta during a deal while the old ROI peaks at only 14.7 — so the
# old ROI is comfortably "stable" (< 6.0) at a moment the hand plainly is not.
#
# That is the mechanism behind the empty-hand and "power 0" reads seen live,
# each of which pushed should_redraw() into a defensive discard — i.e. it
# degraded actual play, not just logging.
#
# Named sets so each caller waits on what IT is about to read, rather than one
# global compromise region.
# Measured over 122 real animation events (SETTLE_TIMING_ANALYSIS.md).
#
# COUNTERINTUITIVE, AND THE DATA IS STRONG: a turn read gates on `hand` ALONE.
# My first version waited on every region a turn read consumes (hand +
# scoreboard + three bases) on the reasoning that you should wait for anything
# you are about to read. Measured, that is worse:
#
#   gate                          continuation   latency p50   p90
#   hand alone (< 8.0)                  1.6%        2.01 s    6.01 s
#   hand AND legacy_roi                 3.3%        ~2.2 s   17.97 s
#   legacy_roi alone (the old code)    12.3%        2.24 s   14.07 s
#
# Waiting on more regions means waiting longer, which pushes the "settled"
# declaration into the window where the NEXT animation has already begun — so
# the combined gate is both slower AND less safe. CIs for 12.3% vs 1.6% do not
# overlap at n=122.
#
# `scoreboard` is deliberately absent: its peak motion during real animation
# (p50 6.59) barely exceeds its own idle noise (p90 6.81), so it cannot
# discriminate and only adds latency.
# Named per SCREEN TYPE, so every call site declares what it is waiting on and
# settle_stats_summary() reports truncation separately for each.
#
# Why this matters: SETTLE_TIMING_ANALYSIS measured, over 122 real animation
# events, that gating on `hand` ALONE beats the combined gate on both axes —
# continuation 1.6% vs 3.3%, p90 latency 6.01s vs 17.97s. `default` IS the
# combined gate, and it was on 14 of 15 call sites while the measured-best set
# was on exactly one. A p90 of 17.97s against max_wait=8.0 means those calls
# frequently truncate and read un-settled.
#
# The non-turn sets deliberately still alias to the combined gate TODAY. That
# is not an endorsement — it keeps behaviour identical while making the stats
# per-screen-type, so the next live session says which of these should move to
# `hand`-alone (or to their own region) instead of guessing from a ~1 Hz proxy
# log that cannot resolve the production poll rate. Change them from
# settle_stats_summary() output, not from this comment.
SETTLE_REGION_SETS = {
    # Measured best for reading the hand. Do not add regions: waiting longer
    # runs into the NEXT animation.
    "turn": ("hand",),

    # Aliases pending measurement — identical regions, distinct labels.
    "result": ("legacy_roi", "hand"),
    "ban": ("legacy_roi", "hand"),
    "menu": ("legacy_roi", "hand"),
    "match_start": ("legacy_roi", "hand"),

    # Backwards-compatible default for callers that have not opted in.
    "default": ("legacy_roi", "hand"),
}

# Per-region thresholds, each set between that region's idle p95 and p99.
# A single shared DIFF_THRESHOLD was wrong: at 6.0, 17.4% of genuinely idle
# `hand` pairs and 20.2% of idle `scoreboard` pairs read as "moving", while
# only 1.4% of idle `legacy_roi` pairs do. 6.0 is well calibrated for
# legacy_roi specifically — it was only wrong as a shared constant.
SETTLE_THRESHOLDS = {
    "legacy_roi": 6.0,
    "hand": 8.0,
    "scoreboard": 8.0,
    "center": 6.5,
    "third_base": 6.5,
    "first_base": 6.5,
    "second_base": 6.5,
}

# Regions not already in GAMEPLAY_REGIONS_FRAC.
_EXTRA_SETTLE_REGIONS = {
    "legacy_roi": ANIMATION_ROI_FRACTION,
}


def _settle_region_box(name):
    if name in _EXTRA_SETTLE_REGIONS:
        return _EXTRA_SETTLE_REGIONS[name]
    return GAMEPLAY_REGIONS_FRAC[name]


# --- Fast capture backend ---------------------------------------------------
#
# pyautogui.screenshot() costs ~376 ms on this machine (measured: 3456x2234
# source, 376 ms capture + 78 ms resize + 16 ms encode = ~470 ms). That caps
# EVERYTHING at ~2.1 Hz and had two consequences that were not obvious:
#
#  1. The screenshot logger never achieved its configured rate. Settings of
#     0.2s (5 Hz) and 0.1s (10 Hz) both produced the same ~0.5 s floor — the
#     minimum inter-frame gap anywhere in 1,811 logged frames is 0.466 s.
#  2. More importantly, wait_for_screen_to_settle(poll_interval=0.3) actually
#     cycles at ~0.77 s (0.3 s sleep + 0.47 s capture), so "2 stable polls"
#     was ~1.5 s of real time rather than the intended ~0.6 s. Every settle
#     latency figure was inflated by this and the gate could not react finely.
#
# mss grabs the same full screen in ~32 ms (12x faster). Used for the settle
# poll loop only — the vision-read path still goes through
# capture_screenshot_image(), which needs the focus handling and downscale.
# Width the settle thresholds were measured at (the logged frames). Any
# capture backend must be normalised to this before its deltas are compared
# against SETTLE_THRESHOLDS.
SETTLE_CALIBRATION_WIDTH = 2000

try:
    import mss as _mss
    _MSS = _mss.mss()
except Exception:                                   # pragma: no cover
    _MSS = None

# Every crop in this file is FRACTIONAL, so it only lands on the right pixels
# if monitors[1] is the display the game is on. mss caches the monitor list for
# the process lifetime and monitors[1] is just "the first one" — on this
# machine that is the built-in (1728x1117, aspect 1.55), but an attached
# ultrawide sits at monitors[2] (3440x1440, aspect 2.39). If the main display
# ever changes, every region silently reads the wrong pixels and nothing
# raises. Aspect is the cheap tell; warn rather than crash, since a genuinely
# different-but-valid display should not stop a run.
_CALIBRATED_ASPECT = 1728 / 1117
if _MSS is not None:                                # pragma: no cover
    try:
        _m = _MSS.monitors[1]
        _a = _m["width"] / _m["height"]
        if abs(_a - _CALIBRATED_ASPECT) > 0.15:
            print(f"WARNING: capture display is {_m['width']}x{_m['height']} "
                  f"(aspect {_a:.2f}), calibrated for {_CALIBRATED_ASPECT:.2f}. "
                  "Fractional crops will target the wrong pixels — check which "
                  "display the game is on.")
    except Exception:
        pass


# Some of what needs announcing sits in the settle poll loop, which runs at
# roughly 7 Hz. A print per call would bury the log it exists to inform — so
# these fire ONCE PER PROCESS, keyed on the message itself. One line saying
# "everything after this is reading the wrong pixels" is a diagnosis; ten
# thousand of them are a wall nobody reads.
_WARNED_ONCE = set()


def _warn_once(msg: str) -> bool:
    """Print `msg` the first time this process sees it, then never again.

    Returns True if it printed. For warnings on HOT paths only — anything
    per-turn or rarer should just print every time, because the second
    occurrence of a per-turn problem is itself information.
    """
    if msg in _WARNED_ONCE:
        return False
    _WARNED_ONCE.add(msg)
    print(msg)
    return True


def _fast_grab():
    """The GAME's pixels, as a PIL Image.

    Was: whatever mss calls monitors[1]. That is "the first display", which on
    this machine is the built-in laptop screen — so with the game on an external
    monitor every fractional crop in this file was reading the laptop desktop.
    The stall diagnostic caught it red-handed: the captured "game screen" was a
    screenshot of the editor.

    compass.fast_capture() locates the game window from OS geometry and returns
    its content, which is the thing every region here is meant to be a fraction
    of. Falls back to the old behaviour if that is unavailable, so a broken
    window lookup degrades rather than crashing the loop.
    """
    import game_capture
    img = game_capture.grab(width=SETTLE_CALIBRATION_WIDTH)
    event_log.log_event("capture", where="_fast_grab", dump=img is not None,
                        img_seq=(img.info.get("dump_seq") if img is not None else None))
    if img is not None:
        return img
    # THE FALLBACK IS THE BUG THIS DOCSTRING DESCRIBES, REINTRODUCED. It is
    # correct as a degradation — a broken window lookup should not kill the run
    # — but it must never be SILENT, because from here on every fractional crop
    # in this file is measuring a different picture than the one it was
    # calibrated against, and each of them fails in a way that points somewhere
    # else entirely.
    _warn_once(
        "WARNING: game_capture.grab() returned nothing — FALLING BACK to a "
        "full-screen grab, so every fractional crop in orchestrator.py is now "
        "reading the DESKTOP, not the game window: the settle thresholds, the "
        "frozen-frame digest, _dealer_prompt_on_screen and screen_at_stall.png "
        "are all measuring the wrong pixels. Downstream this looks like a "
        "screen that never settles, a dealer prompt that is never there, and a "
        "stall screenshot of the editor — none of which are what is wrong. "
        "The game window could not be located. (Warned once per process.)")
    if _MSS is None:
        return pyautogui.screenshot()
    mon = _MSS.monitors[1]
    raw = _MSS.grab(mon)
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    # NORMALISE THE SCALE. mss returns logical points (1728x1117 here) while
    # pyautogui returns physical Retina pixels (3456x2234), and the logged
    # frames the SETTLE_THRESHOLDS were calibrated against were 2000px wide.
    # Mean-absolute-delta is scale-sensitive — downscaling averages noise
    # differently — so feeding a different resolution silently shifts every
    # threshold. Resize to the calibration width so the numbers stay valid.
    if img.width != SETTLE_CALIBRATION_WIDTH:
        ratio = SETTLE_CALIBRATION_WIDTH / img.width
        img = img.resize((SETTLE_CALIBRATION_WIDTH, int(img.height * ratio)))
    return img


def _grab_settle_regions(region_names):
    """One screenshot -> {name: grayscale crop} for every named region.

    Deliberately ONE capture per poll: grabbing each region separately would
    sample different moments and could report a region as stable using two
    frames taken either side of the very animation being waited on.
    """
    img = _fast_grab()
    w, h = img.size
    out = {}
    for name in region_names:
        x0, y0, x1, y1 = _settle_region_box(name)
        out[name] = img.crop((int(w * x0), int(h * y0),
                              int(w * x1), int(h * y1))).convert("L")
    return out


def _mean_abs_delta(a, b):
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    return sum(i * c for i, c in enumerate(hist)) / (a.width * a.height)


def _grab_animation_roi():
    """Legacy single-ROI grab, kept for anything still calling it directly."""
    return _grab_settle_regions(("legacy_roi",))["legacy_roi"]


def wait_for_screen_to_settle(max_wait: float = 8.0, poll_interval: float = 0.15,
                              stable_polls_required: int = 2,
                              regions: str = "default") -> float:
    """
    Poll until EVERY region in the named set has stopped changing, so the
    frame a caller is about to read is settled in the parts it actually reads.
    Returns seconds waited.

    `regions` picks a set from SETTLE_REGION_SETS ("turn", "reveal",
    "default"). Waiting on all of them together matters: a card can be still
    settling into the hand while the diamond is already quiet, and reading
    then is exactly the failure this exists to prevent.

    stable_polls_required stays at 2. Raising it to 3 was tried and measured:
    it buys ZERO reduction in bad reads on the recommended gate (1.6% either
    way) while costing ~1.1s of median latency. Do not raise it.

    poll_interval is 0.15s, which is now actually achievable. It used to be
    0.3s nominal but each poll ALSO paid ~470ms to capture, so the real cycle
    was ~0.77s and "2 stable polls" meant ~1.5s rather than the intended
    ~0.6s. With the mss backend a poll costs ~47ms, so the cycle is ~0.2s and
    the gate both reacts faster and resolves motion it previously stepped
    straight over.

    max_wait is a safety cap. On timeout this returns normally rather than
    raising: the caller still gets a frame, the read may fail, and the
    existing retry path handles it. That is deliberate — blocking forever on
    a genuinely animated screen would be worse.
    """
    names = SETTLE_REGION_SETS.get(regions, SETTLE_REGION_SETS["default"])
    start = time.time()
    prev = _grab_settle_regions(names)
    stable_count = 0

    while time.time() - start < max_wait:
        time.sleep(poll_interval)
        current = _grab_settle_regions(names)
        # Each region judged against ITS OWN threshold — idle noise differs by
        # ~3x between regions, so one shared value either blocks on idle hand
        # noise or ignores real legacy_roi motion.
        settled = all(_mean_abs_delta(prev[n], current[n])
                      < SETTLE_THRESHOLDS.get(n, DIFF_THRESHOLD) for n in names)
        prev = current

        if settled:
            stable_count += 1
            if stable_count >= stable_polls_required:
                return _record_settle(regions, time.time() - start, False)
        else:
            stable_count = 0

    print(f"  [settle] {regions!r} regions still moving after {max_wait}s — "
          "reading anyway (retry path will catch a bad read).")
    return _record_settle(regions, time.time() - start, True)


# INSTRUMENTATION ONLY — records how long settling actually took, changes no
# behaviour. Every latency and truncation number the thresholds were chosen
# from came from a frame log captured at ~1-1.9 Hz, whose finest resolution is
# 0.53s. Production polls at 0.15s, so that log CANNOT resolve what it was used
# to estimate: measuring across a ~1s gap captures more motion per diff and
# makes "2 stable polls" mean ~2s of quiet instead of ~0.3s, both of which
# inflate apparent settle time. The percentiles are therefore upper bounds of
# unknown tightness. This collects the real distribution at the real poll rate
# so max_wait can be set from measurement instead of from a conservative proxy.
_SETTLE_STATS = {}


def _record_settle(regions, elapsed, truncated):
    s = _SETTLE_STATS.setdefault(regions, {"n": 0, "truncated": 0, "times": []})
    s["n"] += 1
    s["truncated"] += int(truncated)
    s["times"].append(elapsed)
    return elapsed


# --- Self-diagnosing exit --------------------------------------------------
# When the loop gives up it should say everything it knew, not just "stuck".
# Every stall so far has been diagnosed by hand from screenshots plus guesswork
# about what the code was seeing; this makes the run answer that itself.
#
# Rolling buffer rather than a full log: the interesting window is the last
# handful of polls before the stall, and an unbounded list on a long session is
# a memory leak for data nobody reads.
_OBSERVATIONS = collections.deque(maxlen=40)


def record_observation(**kw):
    kw["t"] = time.strftime("%H:%M:%S")
    _OBSERVATIONS.append(kw)


def dump_diagnostics(reason: str, extra: dict = None) -> str:
    """Write everything the loop knew to diagnostics/<timestamp>/ and return it.

    Deliberately best-effort and exception-swallowing: this runs on the way out
    of a session that has ALREADY failed, so a fault here must not replace the
    original problem with a stack trace about diagnostics.
    """
    try:
        # BASEBALL_DIAGNOSTICS_DIR lets the test suite write somewhere
        # disposable. Tests exercise every stall path, so without this they
        # dump real bundles into the live diagnostics directory — which is
        # watched during a session, and 20 synthetic stalls would bury a
        # genuine one.
        root = os.environ.get("BASEBALL_DIAGNOSTICS_DIR") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "diagnostics")
        d = os.path.join(root, time.strftime("%Y%m%d_%H%M%S_") + str(time.time() % 1)[2:6])
        os.makedirs(d, exist_ok=True)
        bundle = {
            "reason": reason,
            "when": time.strftime("%Y-%m-%d %H:%M:%S"),
            "observations": list(_OBSERVATIONS),
            "settle_stats": {k: {"n": v["n"], "truncated": v["truncated"],
                                 "p50": sorted(v["times"])[len(v["times"]) // 2],
                                 "max": max(v["times"])}
                             for k, v in _SETTLE_STATS.items() if v["times"]},
        }
        # What the run COST, recorded with the failure. A stall that spent
        # forty paid API calls and one that spent four look identical in the
        # log otherwise, and the difference is the whole reason to fail fast.
        try:
            import api_budget
            bundle["api_calls_used"] = api_budget.used()
            bundle["api_budget"] = api_budget.budget()
            bundle["api_cost_approx"] = round(
                api_budget.used() * api_budget.APPROX_COST_PER_CALL, 3)
        except Exception:
            pass
        bundle.update(extra or {})
        _atomic_write_json(os.path.join(d, "bundle.json"), bundle)
        # The screen as it actually looked when we gave up — the single most
        # useful artefact, and the one that is gone forever if not saved now.
        try:
            _fast_grab().save(os.path.join(d, "screen_at_stall.png"))
        except Exception as e:
            # PRINTED, not stashed on `bundle`. The bundle was already written
            # to disk two lines above, so assigning a key to it here reached
            # nobody — the error was recorded into an object that is then
            # thrown away. A missing screen_at_stall.png with no explanation
            # reads as "nobody thought to save one", which is the opposite of
            # what happened.
            print(f"  [diagnostics] NO screen_at_stall.png — the capture "
                  f"itself failed: {e!r}. This bundle is missing the artefact "
                  f"that usually settles the argument; the absence is a "
                  f"capture failure, not an oversight.")
        print(f"\n  [diagnostics] wrote {d}")
        print(f"  [diagnostics] reason: {reason}")
        print(f"  [diagnostics] {len(_OBSERVATIONS)} recent observations captured.")
        try:
            import api_budget
            print(f"  [diagnostics] API: {api_budget.used()} calls "
                  f"(~${api_budget.used() * api_budget.APPROX_COST_PER_CALL:.2f}) "
                  f"of {api_budget.budget()} allowed")
        except Exception:
            pass
        # Several frames either side of the stall, not just the final one: the
        # cause is usually visible BEFORE the screen everyone stares at.
        try:
            import game_capture
            for _i in range(3):
                _im = game_capture.grab()
                if _im is not None:
                    _im.save(os.path.join(d, f"after_stall_{_i}.png"))
                time.sleep(0.6)
        except Exception:
            pass
        return d
    except Exception as e:                              # pragma: no cover
        print(f"  [diagnostics] could not write bundle: {e}")
        return ""


# --- Input-prompt detection (AUDIT ONLY, drives nothing yet) ---------------
# The game shows "PLAY" bottom-left and "DISCARD" bottom-right, each with a
# button glyph, when it is accepting input. That is a SEMANTIC readiness signal
# — the game itself saying "I want a decision now" — which is strictly better
# information than the statistical "pixels stopped changing" the settle gate
# uses, IF it holds up.
#
# Measured on the 2026-08-24 log, bright-pixel fraction (>200) in the PLAY box:
#     prompt visible : ~0.051  (n=67 gameplay frames)
#     prompt absent  : ~0.000  (n=90)
# Cleanly bimodal, so the DETECTOR is reliable. 0.02 sits in the gap.
#
# WHAT IS NOT ESTABLISHED, and why this drives nothing yet: whether "prompt
# visible" actually implies "safe to read". The frame log samples at ~1Hz, and
# at that spacing 93% of prompt-visible and 61% of prompt-absent frames both
# read as moving against a threshold calibrated for 0.15s gaps — the data
# cannot resolve the question it is being asked. So this is logged alongside
# the motion gate for one live session and compared at the real poll rate
# before it is trusted with anything.
#
# NOTE the fixed box is valid for GAMEPLAY TURNS ONLY. On the ban screen the
# same "PLAY" prompt is attached to the moving cursor, so a fixed crop there
# reads card art instead — verified by eye, do not reuse this for ban screens.
INPUT_PROMPT_REGION = (0.10, 0.815, 0.25, 0.875)
INPUT_PROMPT_BRIGHT = 200
INPUT_PROMPT_THRESHOLD = 0.02


def input_prompt_visible(img=None) -> bool:
    """True if the gameplay PLAY prompt is on screen. Local, ~50ms."""
    img = img if img is not None else _fast_grab()
    w, h = img.size
    x0, y0, x1, y1 = INPUT_PROMPT_REGION
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1))).convert("L")
    return float((np.asarray(crop, dtype=float) > INPUT_PROMPT_BRIGHT).mean()) \
        >= INPUT_PROMPT_THRESHOLD


def _safe_prompt_check():
    """input_prompt_visible() that can never break the loop it instruments."""
    try:
        return input_prompt_visible()
    except Exception:
        return None


def screen_is_moving(regions: str = "default", settle_pause: float = 0.12) -> bool:
    """True if the screen is animating right now. ~0.2s, no API call.

    This is the "no action needed" check. The loop used to spend a vision call
    on EVERY poll including ones that landed mid-animation, which wasted the
    call twice over: the read itself was unreliable (cards still sliding into
    the hand), and an unrecognised result burned a MAX_STUCK_ATTEMPTS slot for
    what was really just an animation in progress.

    Doing nothing is a legitimate action. Because this is local and cheap, the
    loop can check far more often than it could when every check cost an API
    round-trip — which is also what makes it likely to CATCH the informative
    frame rather than step over it.

    Note this is the frame-differencing signal, deliberately NOT the local
    reader self-validation from LOCAL_VS_API.md §4c. That one answers "is this a
    settled turn?" and cannot tell a mid-animation frame from a result or ban
    screen that genuinely needs acting on — using it here would skip real work.
    Motion is the right question for "should I wait?".
    """
    names = SETTLE_REGION_SETS.get(regions, SETTLE_REGION_SETS["default"])
    prev = _grab_settle_regions(names)
    time.sleep(settle_pause)
    current = _grab_settle_regions(names)
    return any(_mean_abs_delta(prev[n], current[n])
               >= SETTLE_THRESHOLDS.get(n, DIFF_THRESHOLD) for n in names)


# How long the loop may keep saying "no action needed" before it forces a read
# anyway. Without a bound, any permanently-animated screen (an attract loop, a
# looping victory flourish, a blinking prompt) would stall the run silently —
# the failure mode this whole gate exists to avoid, arriving by another route.
#
# The bound costs NOTHING in the normal case: a real animation stops, the gate
# notices within ~0.2s, and this value is never reached. It is paid only on a
# screen that never stops moving, and it is paid once per action there. So it
# wants to sit just above the longest genuine animation and no higher.
# Measured settle latency was p90 6.0s / max 10.0s — on a frame log whose ~1Hz
# capture OVERSTATES duration (see settle_stats_summary), so the true max is
# below that. 15s clears it with headroom while capping the worst case at 15s
# rather than 20s. Falling through is safe, not dangerous: the read still goes
# through validate_game_state() and the normal retry path.
# Tune from settle_stats_summary() after a real session.
MAX_CONTINUOUS_MOTION_WAIT = 15.0


def settle_stats_summary() -> str:
    if not _SETTLE_STATS:
        return "  [settle] no settle calls recorded."
    out = ["  [settle] observed latency at the real 0.15s poll rate:"]
    for name, s in sorted(_SETTLE_STATS.items()):
        t = sorted(s["times"])
        pct = lambda p: t[min(int(len(t) * p), len(t) - 1)]
        out.append(
            f"    {name:8s} n={s['n']:4d}  p50={pct(0.50):5.2f}s  "
            f"p90={pct(0.90):5.2f}s  max={t[-1]:5.2f}s  "
            f"truncated={s['truncated']}/{s['n']} "
            f"({100.0 * s['truncated'] / s['n']:.0f}%)")
    return "\n".join(out)


# --- Reveal detection ------------------------------------------------------
#
# The matchup reveal needs a DIFFERENT trigger from settling, and getting this
# wrong is easy. Traced against real 10Hz capture of one play:
#
#   t+0.0s  cards fly out of the hand      (hand motion spikes to 56)
#   t+0.5s  cards land at centre           <-- READABLE FROM HERE
#   ...     resolution animation plays: the ball flies, runners advance or are
#           held. The centre keeps moving for ~9s, oscillating 3->50 with
#           repeated dips below any sane "stable" threshold.
#   t+6.0s  cards clear                    <-- NO LONGER READABLE
#   t+9.0s  centre finally settles         <-- TOO LATE, cards are gone
#
# So "wait for the centre to settle" reads AFTER the cards have disappeared,
# and a short max_wait just times out mid-animation. Both are wrong.
#
# Instead detect PRESENCE: cards are high-contrast structured objects on a
# plain wooden diamond, so the fraction of strong-gradient pixels roughly
# triples when they are there. Measured over the sequence above:
#     cards present : 0.0775 - 0.1476
#     no cards      : 0.0220 - 0.0624
#
# THE THRESHOLD IS SCALE-SENSITIVE AND MUST SUIT BOTH CAPTURE PATHS. Those
# numbers come from logged frames, which are native 3456 DOWNSCALED to 2000.
# `_fast_grab()` on the mss path captures 1728 logical points and UPSCALES to
# 2000 — interpolation invents no high-frequency detail, so every gradient
# count lands lower. Re-measured over 500 real frames (55 present, 415 absent):
#     native path : absent max 0.0615 | present min 0.0779
#     mss path    : absent max 0.0591 | present min 0.0692
# The original 0.070 sits ABOVE the mss present-min — on that path the weakest
# real reveal never fires, and the failure is silent (see wait_for_reveal_cards).
# Because _fast_grab still falls back to pyautogui, the threshold has to sit in
# the INTERSECTION of both gaps, [0.0615, 0.0692]; 0.065 is its midpoint and
# maximises the worst-case margin (0.0035) across the two.
# Deliberately a numpy gradient rather than cv2.Canny (which separates a little
# better) to avoid adding an OpenCV dependency to the main loop.
#
# RIGHT EDGE 0.62 -> 0.58, 2026-09-01. THE REGION WAS THE BUG, NOT THE THRESHOLD.
#
# GAMEPLAY_REGIONS_FRAC["first_base"] starts at x=0.550, so the old 0.62 reached
# 0.07 of screen width INTO first base. This game draws base runners as face-up
# cards on the base medallions, so whenever a runner was on first, its card's
# edges were counted as "cards at centre" — and a runner sits there for the
# whole turn, including the entire card-selection phase before anything is
# revealed. wait_for_reveal_cards() therefore returned True on its first poll
# with nothing revealed, and read_matchup_reveal() spent its vision call on the
# pre-flip screen. That is the whole of the "intended card absent from reveal"
# misfire: the reader could not see our face-down card, so it reported the
# face-up cards it COULD see — the runners. Measured on the 2026-09-01 run, the
# reveal that flagged our played 8 as a misfire returned ('Johnny Drawers', 7),
# and the selection frame for that exact turn has Johnny Drawers, power 7,
# secondary 1, sitting on first base.
#
# Measured over 877 frames captured at 0.5 Hz during that run, labelling the
# face-down pre-flip state by template-matching the card back (NCC >= 0.55,
# 227 frames, spot-checked by eye at 40/40 correct):
#
#                                   x1=0.62 (old)   x1=0.58 (new)
#   face-down frames over threshold      21/227           0/227
#   max edge fraction, face-down         0.0842          0.0622
#   genuine reveals detected                112             126
#
# It REMOVES false triggers and FINDS MORE real reveals at the same time,
# because trimming the empty wooden strip on the right raises the fraction on
# frames that do have a card (the weakest confirmed reveal goes 0.0654 ->
# 0.0737). 14 of the 17 newly-firing frames are genuine reveals the old region
# missed; the other 3 are the end-of-match LOSER screen, which this function is
# never called on.
#
# THE THRESHOLD IS DELIBERATELY UNCHANGED at 0.065 — preflight.py and
# test_settle_regions.py both pin it to the value that ran live, and it was
# never the wrong number. At the live 2000px capture width the classes now
# separate with real margin either side of it: face-down 0.0482-0.0566,
# genuine reveals 0.0729-0.1545. Note that this statistic is scale-sensitive
# (every count rises as the capture shrinks), so re-measure at 2000px, which
# is what both capture paths deliver; at 1400px the separation is gone.
REVEAL_CENTER_REGION = (0.42, 0.28, 0.58, 0.58)
REVEAL_EDGE_THRESHOLD = 0.065
# How long to wait for the faceoff to flip. Set from the measured turn period,
# not from a guess. See wait_for_reveal_cards() for the full measurement.
#
# 20s missed 82% of turn periods and lost 84% of turns. 45s took that to 23%.
# Re-measured at 1Hz over 1001 frames (17 minutes of live play), which is finer
# than the 2s sampling 45 came from:
#
#     turn period   p50 32s   p75 59s   p90 83s   max 95s
#     cap 45s covers 64%   cap 75s covers 84%   cap 90s covers 96%
#
# THE REASONING ABOVE IS THE WRONG QUANTITY, and it cost 54% of a measured run.
#
# Turn PERIOD does not decide this wait. What decides it is how long AFTER THE PLAY the
# reveal appears -- and that is a different, much tighter distribution. Pooled over every
# log on disk, 4 logs, 72 real reveals:
#
#     t_first after the play   min 0.90   p50 3.80   p95 5.80   p99 7.90   MAX 7.90
#     1s bins                  0-1:1  1-2:2  2-3:7  3-4:32  4-5:18  5-6:9  7-8:3
#
# The other half of the sentence above is false too. "Only a turn with no reveal coming
# pays the extra" treats that as an edge case; it is 67 of 139 plays on disk. On the
# 2026-09-09 cycle those 22 turns cost 1,650 s -- 54% OF THE WHOLE RUN, against 457 s (15%)
# for every paid vision call put together.
#
# So the two populations are: a reveal that is coming, which has always arrived inside
# 7.9 s, and one that is not, which never arrives at any budget. 15.0 is 1.9x the observed
# maximum and loses none of the 72. It saves 60 s on every turn with no reveal.
REVEAL_MAX_WAIT = 15.0
_REVEAL_GRADIENT_CUTOFF = 28.0


def center_card_edge_fraction(img) -> float:
    """The presence statistic, over any PIL image.

    Split out from the polling loop for the same reason as hand_deal_seen():
    so it can be replayed against saved frames. The region that ships here
    was chosen by replaying exactly this function over 877 logged frames —
    an invariant test_reveal_trigger.py now pins to real fixtures.
    """
    w, h = img.size
    x0, y0, x1, y1 = REVEAL_CENTER_REGION
    crop = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1))).convert("L")
    a = np.asarray(crop, dtype=float)
    gy, gx = np.gradient(a)
    return float((np.hypot(gx, gy) > _REVEAL_GRADIENT_CUTOFF).mean())


def _center_card_edge_fraction() -> float:
    return center_card_edge_fraction(_fast_grab())


def wait_for_reveal_cards(max_wait: float = REVEAL_MAX_WAIT, poll_interval: float = 0.25) -> bool:
    """
    Block until the revealed cards are actually visible at the diamond centre.
    Returns True if they appeared, False on timeout.

    Rising-edge trigger, NOT a settle: see REVEAL_CENTER_REGION above for why
    settling is the wrong signal here. Returning False is not an error — the
    caller's matchup logging is diagnostic and simply skips that turn.

    MAX_WAIT WAS 6 SECONDS, AND THAT LOGGED NOTHING. A full live match on
    2026-08-28 played 51 cards and recorded ZERO turns — "reveal cards never
    appeared" on every single one, leaving match_log.jsonl exactly where it
    started at 72 rows.
    
    The threshold was never the problem. Measured over 2445 frames of that
    match, the centre-edge fraction sits at 0.0435 with no cards and peaks at
    0.1456 with them, so the 0.065 trigger separates them cleanly and fires on
    45 frames. The reveal simply happens LATER than six seconds after the play —
    the post-play notes twenty lines below record the game taking ~17s to finish
    dealing. The window closed before the cards arrived.

    AND 20 SECONDS WAS STILL TOO SHORT. The 2026-09-01 run played 215 cards and
    lost 180 of them to this timeout — 84% of every turn, an hour of pure
    waiting, and the reason match_log.jsonl grew by 2 rows across a whole run.

    Measured over 877 frames sampled at 2s through that run:

        reveal visible in            129/877 frames (14.7%)
        distinct reveal events       40
        each stays up for            8-12 seconds
        turn period (reveal->reveal) p50 33s, p75 52s
        turn periods exceeding 20s   82%

    82% of turn periods longer than the window against an 84% failure rate is
    the whole explanation. The cards are on screen for ten seconds at a time —
    a 0.25s poll cannot miss them — they simply arrive after the window shut.

    RAISING THE CAP IS ALMOST FREE, which is why it is the fix: this returns
    the moment the reveal is seen, so a turn that works is not slowed at all.
    Only a turn with no reveal coming pays the longer wait, and those were
    already paying 20s to fail.
    """
    # ON TIMEOUT, SAY WHAT WAS ACTUALLY SEEN. Three separate theories about
    # this failure were argued from captured frames and all three were wrong —
    # the region was fine, reveals do occur, and the commit press is last so the
    # wait is not late. Each was reasoning ABOUT the detector instead of asking
    # it. The peak it observed distinguishes the remaining possibilities at a
    # glance: far below threshold means it genuinely saw no cards, just below
    # means the threshold or scale is wrong, and at/above means it saw them and
    # something else lost the turn.
    start = time.time()
    peak = 0.0
    polls = 0
    while time.time() - start < max_wait:
        seen = _center_card_edge_fraction()
        polls += 1
        peak = max(peak, seen)
        if seen >= REVEAL_EDGE_THRESHOLD:
            return True
        time.sleep(poll_interval)
    print(f"  [reveal] no cards after {max_wait:.0f}s over {polls} polls — "
          f"peak edge {peak:.4f} vs threshold {REVEAL_EDGE_THRESHOLD} "
          f"({100.0 * peak / REVEAL_EDGE_THRESHOLD:.0f}% of the bar)")
    return False


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


# --- Post-play readiness ---------------------------------------------------
#
# THE LOOP READS ~15 SECONDS TOO EARLY AFTER EVERY PLAY. Measured over all 88
# plays in the two logged runs of 2026-08-26:
#
#   current gate first says "still" (2 polls) : p50  2.8 s after the play
#   LAST hand motion (replacement card dealt) : p50 16.9 s after the play
#   LAST motion of any watched region         : p50 17.6 s after the play
#
# 88 of 88 plays. The mechanism is that "settled" and "ready" are different
# questions and only one of them is being asked. Right after a play the hand is
# quiet because NOTHING HAS HAPPENED YET — the played card has left, the
# resolution animation is at the centre of the screen, and the replacement card
# will not arrive for another ~15 s. wait_for_screen_to_settle(regions="turn")
# watches the hand alone (correctly — see SETTLE_REGION_SETS) and so returns
# almost immediately on a hand that is quiet for the wrong reason.
#
# Nor does the motion gate at the top of the loop catch it: over the same
# frames, 46.8% of consecutive frame-pairs inside the 9 s resolution animation
# have BOTH watched regions under threshold, i.e. screen_is_moving() would
# answer False. Every one of the 89 plays had at least one such frame. (Those
# pairs are 0.57 s apart, the logger's real cadence; the live gate samples
# 0.12 s apart and therefore sees LESS motion per diff, so the true rate is
# higher than 46.8%, not lower.)
#
# The cost is one wasted vision call plus the 2 s retry sleep, per play. That
# matches the failure the run loop already documents from the other side: "22
# plays were followed by a failed read — 19 by exactly one poll".
#
# So wait for the EVENT, not for quiet: the replacement card landing in the
# hand is a large, unambiguous, purely local signal (peak delta ~56 against an
# 8.0 threshold), and once it has landed the ordinary settle gate means what it
# says. Falling through on timeout is deliberate and matches
# wait_for_screen_to_settle: the caller still gets a frame and the existing
# retry path handles a bad one.
# 35, was 25: the worst deal measured 2026-09-08 landed 21.95 s after the play (n=9);
# 25 left 3 s of margin. The cap costs time only on a turn that already failed.
# 20.0, was 35.0: over 30 real gate windows recorded at 60 fps on 2026-09-08 EVERY
# deal crossed the threshold below by 15.0 s (p50 5.5, p90 10.6), so 20 s carries a third
# of margin. The old 35 was sized for the rising-edge gate, which missed 11 of 30 windows
# and paid the whole cap for each. A cap costs time only on a turn with no deal.
POST_PLAY_DEAL_MAX_WAIT = 20.0
# THE DEAL EDGE, between two measured populations (2026-09-08, 20 Hz on the frame
# dump, n=9 turns; agent_progress/ocr-timing/TIMING_REPORT.md):
#   dead window (max d_hand between the play burst and the deal burst)  7.25 .. 15.44
#   the deal burst (its peak d_hand)                                    31.83 .. 41.15
# SETTLE_THRESHOLDS["hand"] = 8.0 sits BELOW the dead window -- inside the noise this
# gate must ignore (10.4) -- which is why the deal wait alone closed only half the
# gap. 25.0 sits in the gap; 16..30 all release at p50 ~10 s. CAVEAT: measured at a
# 0.060 s sample gap; the live poll is 0.15 s, so both populations rise in
# production. Re-check against the first live session's [deal] lines.
# 15.0, WAS 25.0 AND A DIFFERENT QUANTITY. The gate now measures how far the hand has
# moved from where it was when the gate STARTED, not how much it moved since the previous
# sample. Measured non-circularly over 30 real gate windows (agent_progress/hand-timing/):
#     no deal (n=7)    4.1  5.5  6.8  9.3  9.3 10.1 11.5
#     deal   (n=23)   20.0 21.6 29.1 ... 49.1 50.1
# 15.0 sits in that gap, 1.30x above the highest no-deal and 0.75x the lowest deal. The
# rising-edge statistic it replaces cannot see a card that slides in over two seconds,
# because that motion is divided among the thirteen polls that carry it -- four of the
# eleven live timeouts were exactly that, with total movement 19.3-33.4 and no step over
# 16.1. Read through hand_deal_threshold(), so a sweep moves it without a code edit.
HAND_DEAL_THRESHOLD = 15.0
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

# The gate releases on a HAND THAT READS, twice in a row, rather than on a delta edge --
# see the rule inside wait_for_hand_deal for why quiet cannot do this job. Set False to
# get the old edge-plus-floor behaviour back exactly.
USE_READABLE_HAND_GATE = True
# TWO, because one frame can be caught mid-animation and still parse; and only two,
# because each costs a poll interval and the reader is the expensive half of the poll.
READABLE_POLLS = 2


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
BASE_NUMBER = {"third": 3, "second": 2, "first": 1}


def bases_to_travel(bases, batter_speed=None, margin=None, fielding=0):
    """How many BASE-MOVEMENTS this play sets off -- one runner moving one base is one.
    None when it cannot be known. NOT a duration: see "zero bases is not zero time" below.

    This is the input a post-play wait wants and has never had: a routine out with nobody
    on animates almost nothing, while a home run with the bases loaded sends four runners
    all the way round. Measured live, the same gate released 1.1 s after one play and
    10.8 s after a home run, so the spread is real and large.

    `bases` is local_state.read_runners()["bases"] -- occupancy AND the runner's live speed
    off their shield badge, which is what makes this computable at all. `margin` is the
    reveal's margin (orchestrator.reveal_margin); at AUTO_HOME_RUN_MARGIN or above every
    runner scores from wherever they stand, which is the maximum animation the game has.

    Returns None rather than a guess when a base abstained, a speed did not read, or the
    MARGIN is unknown: a number built on a hole is worse than no number, and the caller's
    fallback is the fixed budget it already uses. The margin is required because it decides
    whether the batter runs at all -- an out is an out.

    `fielding` is the PITCHER's fielding for this at-bat -- their card's secondary plus a
    Fielding Play if one was attached. It is knowable while WE pitch, and only from the
    reveal while we bat. It does not apply on a home run: everyone scores regardless.

    WHAT ELSE ANIMATES, from the user's sources (2026-09-12) -- not counted here because
    none of it is a base-movement, and worth writing down because it means the fixed term
    is not one constant but a sum of conditional ones:

        the pitcher's score flash      every at-bat
        a COIN FLIP                    only on a TIE (equal power)
        Field Play effects             only when a defence card is used
        the base tracker resetting     on an out, tokens are removed rather than advanced
        the played card being discarded on an out

    So two turns with the same base count can animate for different lengths, and the model
    that eventually fits this will want those as terms rather than noise.

    ZERO BASES IS NOT ZERO TIME, and the number must never be read that way. An OUT moves
    nobody, but it still animates -- the pitch, the swing, the out -- and CLAUDE.md section
    4 already records that outs have a median reveal of 4.2 s and a MAXIMUM of 14.9 s
    (n=160). So this is the SLOPE's input only. Any wait built on it needs an intercept:

        wait  ~  FIXED_AT_BAT  +  PER_BASE * bases_to_travel(...)

    and a caller that multiplied a 0 straight into a wait of nothing would read a hand that
    has not been dealt. The user made the point directly on 2026-09-12: "an out still has an
    animation." Neither term is measured yet -- see wait_for_hand_deal on why the archived
    times cannot fit them.

    IT IS AN UPPER BOUND, NOT A PREDICTION, in two places that are honest to name. A LOSING
    at-bat can still advance runners (CLAUDE.md section 4) by an amount nobody has measured,
    so this counts them at their full speed; and a TIE is a coin flip, so the batter's 1
    base is counted whether or not they win it. Both err LONG, which is the safe direction
    for a wait: predicting too much animation costs a little time, predicting too little
    reads a half-dealt hand.
    """
    if not bases:
        return None
    total = 0
    for name, b in bases.items():
        if b.get("occupied") is None:
            return None
        if not b["occupied"]:
            continue
        start = BASE_NUMBER.get(name)
        if start is None:
            return None
        if margin is not None and margin >= AUTO_HOME_RUN_MARGIN:
            total += 4 - start          # everyone scores from where they stand
            continue
        sp = b.get("speed")
        if sp is None:
            return None
        # FIELDING SUBTRACTS RUNNER MOVEMENT -- that is what the black pitcher buffs do, and
        # it is why they only matter with runners on (CLAUDE.md section 4). The user, on
        # what happens during an out, 2026-09-12: "The players debuff could be applied too.
        # Which would prevent some runners from moving." A runner held still animates less,
        # so a count that ignored it over-predicted every turn against a fielding pitcher.
        # Same shape as simulate._step, including that FIELDING_SUBTRACT_PER_POINT is 1 and
        # UNMEASURED; subtract first, then cap, because a held runner cannot pass home either.
        total += max(0, min(sp - max(0, fielding), 4 - start))
    # THE BATTER ONLY RUNS IF THEY REACHED BASE. The first version of this added the
    # batter's speed on every at-bat, so a routine OUT with nobody on predicted 1 base of
    # animation instead of 0 -- the user spotted it by reading the numbers back
    # (2026-09-12). An out is an out: the batter does not take a base.
    #
    #     margin >= AUTO_HOME_RUN_MARGIN   all four, whatever their speed
    #     margin >  0                      a hit: their own speed
    #     margin == 0                      a TIE is a coin flip and winning one is CAPPED
    #                                      AT FIRST regardless of speed, so at most 1 --
    #                                      and which way the flip went is not knowable
    #                                      here, so this is the upper bound, not a claim
    #     margin <  0                      an out: the batter runs nowhere
    if margin is None:
        return None
    if margin >= AUTO_HOME_RUN_MARGIN:
        total += 4
    elif margin > 0 and batter_speed is not None:
        total += max(0, batter_speed)
    elif margin == 0:
        total += 1
    return total


# No post-play read before this, edge or no edge: between the fastest release the
# old gate produced (2.16 s, n=85 live) and the earliest a hand was readable by eye
# (8.43 s, n=9).
# MEASURED LIVE, 2026-09-10, and it was costing 5.6 s a turn for nothing. The floor predates
# the stable-hand rule: back then the gate released on the deal's rising EDGE, so a floor was
# the only thing stopping it firing on dead-window noise. The archived logs could not say
# whether it still earned its place, because the settle rule only RUNS once the floor has
# passed -- every release on disk sits at 6.30 s, exactly floor plus the two polls the rule
# needs. patch912e3d0's probe watches the same signal from the FIRST poll and only prints:
#
#     hand first settled at   median 1.1 s   (min 0.7, max 2.3, n=15 turns)
#     the 6.0 floor then held it   median 5.6 s   (4.5 .. 8.7)
#     total dead time              90 s over 15 turns
#
# 3.0 sits above every settle time observed (max 2.3) and still refuses a sub-second edge,
# which is what the floor was for. It is NOT zero: nothing has measured what the gate does
# with no floor at all, and the probe cannot answer that because it only ever watched a run
# that had one.
POST_PLAY_MIN_WAIT = 3.0
# ON BY DEFAULT since 2026-09-08. The diagnosis (88/88 plays read ~15 s early) was
# never in doubt; the replay that closed only half the gap did so because the
# threshold sat inside the noise -- see HAND_DEAL_THRESHOLD. Measured directly on
# the frame dump the deal lands 11.5 / 19.0 / 23.0 s (p50/p90/max, n=9) after the
# play and the old gate released at 0.38 s. Read at CALL time (10.18);
# BASEBALL_DEAL_WAIT=0 turns it off for one session.
def post_play_wait_for_deal(env=None):
    raw = (os.environ if env is None else env).get("BASEBALL_DEAL_WAIT")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "off", "no", "")


POST_PLAY_WAIT_FOR_DEAL = post_play_wait_for_deal()


def hand_deal_seen(deltas, threshold=None):
    """Pure decision function over a stream of hand-region deltas: True once a
    deal-sized motion has been observed. Split out from the polling loop so it
    can be replayed against logged frames — see the replay validation."""
    th = hand_deal_threshold() if threshold is None else threshold
    return any(d >= th for d in deltas)


# THE HAND AT THE PLAY, handed from play_one_turn to the deal gate in run(). POPPED,
# never merely read: a turn that does not set one must not inherit the previous turn's
# hand, which would have the gate compare against a stale picture and return at once.
# That is graph_walk's _LAST_LEG_END pattern, here for the same reason -- and the two
# sites are in DIFFERENT functions, which is why a plain local would have been a
# NameError (the patch asserts the setter and the popper are not the same function).
_HAND_BASELINE = None


# THE DEAL'S INPUTS, CAPTURED AT THE PLAY AND POPPED AT THE GATE. Same stash/pop shape as
# the hand baseline beside it, and for the same reason: the numbers are only true at the
# moment of the press, and the consumer is a different function several hundred lines away.
#
# RAW INPUTS, NOT A PREDICTION. bases_to_travel needs the MARGIN, and the margin is not
# known at the play -- the opponent's card is revealed afterwards. Guessing it here would
# invent the very number this instrumentation exists to measure, so what is stashed is the
# pre-play diamond and the batter's speed, and the margin is joined offline from the row
# match_log.jsonl already writes. That keeps every term honest and still records the pair
# the delay model needs: what was on the field, and how long the deal then took.
_DEAL_INPUTS = None


def capture_diamond_at_play(decision, state_json, log=print):
    """Stash the diamond as it stands at the play. Returns True if it recorded something.

    Wrapped whole: this is a diagnostic on the $50 path, and a log line that can kill a
    turn is worse than no log line. On any failure it records nothing and the deal gate
    behaves exactly as before.

    FIELDING IS THE PITCHER'S, so it is ours only while WE pitch. While batting the
    opponent's pitcher holds it and we cannot see it until the reveal, so 0 is passed --
    which makes the stashed bound an over-estimate of runner movement, the safe direction.
    """
    try:
        # imported here, not at module scope, the way this file's other two local_state
        # sites do it -- orchestrator must still import when local_state cannot.
        import local_state as _ls
        c = _grab_settle_regions(("third_base", "second_base", "first_base"))
        rr = _ls.read_runners(c["third_base"], c["second_base"], c["first_base"])
        pitching = state_json.get("phase") == "pitching"
        fielding = 0
        if pitching:
            fielding = getattr(decision.player_card, "secondary", 0) or 0
            tac = decision.tactics_card
            if tac is not None and getattr(getattr(tac, "kind", None), "value", "") == "fielding_boost":
                fielding += tac.bonus or 0
        # THE BATTER'S SPEED IS ONLY A BATTER'S. While pitching, decision.player_card is our
        # PITCHER and its secondary is FIELDING, not speed -- passing it as batter_speed put
        # one number in two roles (QA, 2026-09-13). The batter is then the opponent's and we
        # do not know them, so it is None and bases_to_travel abstains on the batter's leg.
        batter_speed = None if pitching else (getattr(decision.player_card, "secondary", None))
        stash_deal_inputs(rr.get("bases"), batter_speed, fielding)
        return True
    except Exception as exc:
        log(f"  [deal] could not record the diamond at the play "
            f"({type(exc).__name__}: {exc}) — the gate is unaffected")
        return False


_DEAL_SEQ = 0


def stash_deal_inputs(bases, batter_speed, fielding=0):
    """Record the diamond at the moment of the play, with a SEQUENCE NUMBER.

    The seq exists because the pop only happens WHEN THE GATE RUNS, and the gate
    does not always run: play_one_turn raising does `continue`, and a refused play
    pops the hand baseline but not this. The next turn's gate then consumes a
    diamond describing an at-bat that never happened, and the row is mislabelled
    with no way to tell. test_deal_inputs_wired names that hazard and believes
    popping at the gate closes it; it does not.

    Rather than reorder the turn loop -- control flow on the $50 path that cannot
    be tested live tonight -- the seq makes the problem VISIBLE: two rows carrying
    the same play_seq is a reused diamond, and the analysis drops them. Instrument
    first, decide later, invent nothing.
    """
    global _DEAL_INPUTS, _DEAL_SEQ
    _DEAL_SEQ += 1
    _DEAL_INPUTS = {"bases": bases, "batter_speed": batter_speed,
                    "fielding": fielding, "seq": _DEAL_SEQ}


def pop_deal_inputs():
    global _DEAL_INPUTS
    d, _DEAL_INPUTS = _DEAL_INPUTS, None
    return d


def deal_inputs_summary(d):
    """One line describing what was on the field, or None. Never raises: this is a log
    line on the $50 path, and a diagnostic that can kill a turn is worse than no
    diagnostic (the matchup logger beside it is wrapped for the same reason)."""
    try:
        if not d or not d.get("bases"):
            return None
        on = [(n, b.get("speed")) for n, b in d["bases"].items() if b.get("occupied")]
        # the margin is unknown here, so report the BOUNDS the outcome will fall between
        lo = bases_to_travel(d["bases"], d.get("batter_speed"), -1, d.get("fielding", 0))
        hi = bases_to_travel(d["bases"], d.get("batter_speed"),
                             AUTO_HOME_RUN_MARGIN, d.get("fielding", 0))
        return (f"runners {on or 'none'} batter_speed {d.get('batter_speed')} "
                f"fielding {d.get('fielding', 0)} bases {lo}..{hi}")
    except Exception:
        return None


def deal_inputs_bounds(d):
    """(lo, hi) base-movements this play can produce, or (None, None).

    THE X-AXIS THE DATASET WAS MISSING. wait_for_hand_deal takes a
    `predicted_bases` argument and NOTHING IN PRODUCTION EVER PASSED IT -- the one
    call site is `wait_for_hand_deal(baseline=pop_hand_baseline())` -- so every row
    would have carried predicted_bases=None and tools/deal_timing.py would have
    refused with "0 usable rows" however many matches were played. The pipeline was
    wired, exercised, green, and collected nothing (10.1, one level up).

    A single number does not exist at the play: bases_to_travel needs the MARGIN and
    the margin is only known at the reveal. So the bounds are what the moment
    actually supports, and they are recorded as numbers instead of being formatted
    into a log line and thrown away.
    """
    try:
        if not d or not d.get("bases"):
            return None, None
        lo = bases_to_travel(d["bases"], d.get("batter_speed"), -1, d.get("fielding", 0))
        hi = bases_to_travel(d["bases"], d.get("batter_speed"),
                             AUTO_HOME_RUN_MARGIN, d.get("fielding", 0))
        return lo, hi
    except Exception:
        return None, None


def stash_hand_baseline(img):
    global _HAND_BASELINE
    _HAND_BASELINE = img


def pop_hand_baseline():
    global _HAND_BASELINE
    img, _HAND_BASELINE = _HAND_BASELINE, None
    return img


def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,
                       poll_interval: float = 0.15, baseline=None,
                       predicted_bases=None) -> bool:
    """Block until the replacement card has visibly landed in the hand.

    Returns True if the deal was seen, False on timeout. Rising-edge trigger on
    the hand region, then hand off to the normal settle gate. Local only: one
    _grab_settle_regions(("hand",)) per poll, ~40 ms.
    """
    start = time.time()
    # PREDICTED BASES, RECORDED BESIDE THE MEASURED WAIT, on its own line so it cannot be
    # confused with the gate's own numbers. The coefficient that would turn bases_to_travel
    # into SECONDS cannot be fitted from anything on disk: the archived release times are
    # floor-censored (77% land within one poll of POST_PLAY_MIN_WAIT, and the whole
    # distribution MOVES when that constant changes -- floor 6.0 piles at 6.1, floor 3.0 at
    # 3.6), and no [deal] line on disk carries runner state to join against. So this logs
    # the PAIR and invents nothing; a few matches of it is what makes the model fittable.
    # An invented seconds-per-base would be the same bug wearing a fix's clothes.
    if predicted_bases is not None:
        print(f"  [deal] predicted {predicted_bases} base(s) to animate")
    _dinputs = pop_deal_inputs()
    _di = deal_inputs_summary(_dinputs)
    _bases_lo, _bases_hi = deal_inputs_bounds(_dinputs)
    if _di:
        print(f"  [deal] at the play: {_di}")
    # THE BASELINE: the hand as it was when this gate started. Every later frame is
    # compared against THIS, not against its predecessor, so a gradual deal accumulates
    # instead of being divided among the polls that carried it.
    # THE BASELINE IS THE HAND AT THE PLAY when the caller has it (patch67). Captured
    # here instead, it photographs a hand the game has usually already refilled: over 28
    # recorded plays the hand had moved a median 53.5 from its at-the-play state by the
    # time this function began, and all eight of the timeouts were changes that finished
    # during the reveal read. None is a supported value -- every existing caller keeps
    # the old behaviour.
    if baseline is None:
        baseline = _grab_settle_regions(("hand",))["hand"]
    seen = False
    good = 0
    last_sig = None
    # THE FLOOR PROBE. POST_PLAY_MIN_WAIT is 6.0 and the release rule below only RUNS once
    # the floor has passed, so every logged release sits at 6.30 or later -- exactly floor
    # plus the two polls the rule needs. The logs therefore CANNOT say whether the floor is
    # holding anything back: 24 of 54 archived releases are at that earliest permitted
    # instant, and nothing on disk records when the hand first settled. This watches the
    # same signal from the FIRST poll and only PRINTS, so the floor still decides the
    # release and the run is unchanged. One run answers whether the floor is redundant.
    probe_good = 0
    probe_sig = None
    probe_at = None
    th = hand_deal_threshold()
    biggest = 0.0
    last_beat = start

    def _record_row(outcome):
        """One machine-readable row per deal. THIS IS THE WHOLE EXPERIMENT.

        The prediction from bases_to_travel has only ever been PRINTED, and the user was
        right to call that out: nothing changes a delay, and no run has ever produced the
        line, so the dataset is EMPTY rather than thin. The coefficient that would turn
        base-movements into seconds still cannot be invented -- but it becomes fittable
        the moment the pair is on disk beside a wait that is not censored by the floor.

        `settled_at` is the FLOOR-FREE number and is the one to regress on. `waited` is
        what the gate actually spent, and it cannot fall below POST_PLAY_MIN_WAIT by
        construction -- 24 of 54 archived releases sit at the earliest permitted instant,
        which is why the archive could never answer this (10.4's censoring, one level up).
        Both are recorded so the difference between them is visible per turn.
        """
        row = dict(
            outcome=outcome,
            predicted_bases=predicted_bases,
            waited=round(time.time() - start, 2),
            settled_at=None if probe_at is None else round(probe_at, 2),
            floor=POST_PLAY_MIN_WAIT,
            threshold=th,
            biggest=round(biggest, 1),
            edge_seen=seen,
            bases_lo=_bases_lo,
            bases_hi=_bases_hi,
            play_seq=(_dinputs or {}).get("seq"),
            at_the_play=_di or None)
        # BOTH sinks, deliberately. The deque is what a stall bundle carries; the file is
        # what survives a HEALTHY run, and a healthy run is the only kind that produces a
        # clean timing row. Either alone loses exactly the case the other covers.
        # BOTH CALLS, one guard. record_observation stamps kw["t"] with time.strftime and
        # runs FIRST, so a guard on the sink alone protects nothing -- which is what the
        # first version shipped. The row is diagnostic; the turn is $50.
        try:
            record_observation(event="deal_timing", **row)
            log_deal_timing(row)
        except Exception as e:
            print(f"  [deal] timing row not recorded ({type(e).__name__}: {e}) — "
                  "the turn continues")
    while time.time() - start < max_wait:
        time.sleep(poll_interval)
        # A CAPTURE THAT RAISES MUST NOT END THE SESSION. These two were the only
        # unwrapped calls in the loop, and there is no try at the call site
        # (:7418) -- so a grab raising on poll 3 escaped wait_for_hand_deal,
        # reached run()'s outer finally, and stopped the run. The timing row was
        # lost with it, which is the one record that would have said why.
        # Demonstrated offline by raising from the third grab: 0 rows, run over.
        try:
            cur = _grab_settle_regions(("hand",))["hand"]
            d = _mean_abs_delta(baseline, cur)
        except Exception as e:
            print(f"  [deal] the deal gate could not read the hand "
                  f"({type(e).__name__}: {e}) — reading anyway; the retry path "
                  "will catch a bad read")
            _record_row("error")
            return False
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

        if USE_READABLE_HAND_GATE and probe_at is None:
            try:
                psig = _hand_signature(dict(crop_gameplay_regions(_fast_grab())).get("hand"))
                probe_good = probe_good + 1 if (psig is not None and psig == probe_sig) else 0
                probe_sig = psig
                if probe_good >= READABLE_POLLS:
                    probe_at = time.time() - start
            except Exception:
                probe_good, probe_sig = 0, None

        # The floor: an edge before POST_PLAY_MIN_WAIT is dead-window noise by the
        # measurement above, so keep polling; return on the first poll at or past
        # the floor once an edge has been seen.
        # THE RELEASE RULE: A COMPLETE HAND, TWICE RUNNING -- NOT A QUIET FRAME.
        #
        # This used to release on the EDGE plus a hand-picked 6 s floor: motion having
        # BEGUN, not motion having ENDED. That is how a mid-deal screenshot gets taken,
        # and it is why a quarter of all turns spend a paid API call to wait -- measured
        # over 514 turns, the first read of a turn lands a median 11.96 s after the play
        # while the read that finally WORKS on a retried turn lands at 17.59 s. Nothing
        # differs between them except that the deal finished in between.
        #
        # A "wait for the deltas to go quiet" rule was measured and REFUSED: over the
        # recorded plays a SETTLED HAND reads a frame-to-frame delta of ~4.6 while an
        # EMPTY TABLE reads ~2.5, so quiet cannot tell "the cards have landed" from
        # "there are no cards" -- the two populations are the wrong way round and no
        # threshold on that quantity separates them (CLAUDE.md 10.4).
        #
        # So ask the question we actually care about. local_hand_cards() returns a hand
        # only when every card is fully read, and it is ~21 ms, which is 14% of a poll.
        # Requiring it TWICE means a frame caught mid-animation cannot release the gate.
        # No new threshold is invented anywhere in this rule.
        if seen and time.time() - start >= POST_PLAY_MIN_WAIT:
            if not USE_READABLE_HAND_GATE:
                print(f"  [deal] replacement card seen; released "
                      f"{time.time() - start:.1f}s after the play "
                      f"(threshold {th:g}, biggest delta {biggest:.1f})")
                _record_row("edge")
                return True
            try:
                hand_img = dict(crop_gameplay_regions(_fast_grab())).get("hand")
                # STABLE, NOT COMPLETE. Requiring a COMPLETE hand made this gate wait out
                # its whole budget whenever one card was unreadable: measured over a
                # 46-play run, 14 timeouts and 280 SECONDS lost. Since the hand memory
                # landed, an incomplete hand is perfectly usable -- the missing card is
                # carried forward or dropped -- so completeness is the wrong question.
                # What the gate is actually for is "has the deal FINISHED", and the
                # answer to that is that the hand stops changing.
                sig = _hand_signature(hand_img)
                readable = sig is not None and sig == last_sig
                last_sig = sig
            except Exception:
                readable, last_sig = False, None   # never raise into the turn loop
            good = good + 1 if readable else 0
            if good >= READABLE_POLLS:
                _held = ("" if probe_at is None
                         else f", hand first settled at {probe_at:.1f}s "
                              f"(floor held it {max(0.0, time.time() - start - probe_at):.1f}s)")
                print(f"  [deal] hand STABLE {READABLE_POLLS}x; released "
                      f"{time.time() - start:.1f}s after the play "
                      f"(threshold {th:g}, biggest delta {biggest:.1f}{_held})")
                _record_row("stable")
                return True
    print(f"  [deal] no replacement card seen in {max_wait:.0f}s — "
          f"reading anyway (the retry path will catch a bad read). "
          f"Threshold {th:g}, biggest delta {biggest:.1f}: a biggest well UNDER the "
          f"threshold means the gate is too high for this turn.")
    _record_row("timeout")
    return False


VALID_SCREENS = {"turn", "discard_prompt", "result", "ban_screen", "match_start_prompt", "other"}


# Possible on-card values. Powers 4-9 and shield 0-3 are what the roster and
# hand_digit_reader both observe; the range check exists to reject hallucinated
# values (0, -5, 999, True) before they reach a decision, not to be precise.
#
# MIN was 1, which was too loose to be useful: 1-3 is the TACTICS BONUS digit
# range, and both readers pick those up as a player power. Live 2026-08-26, a
# hand read as a single `power=1` card sailed through this check, and the
# engine spent one of the match's 2-3 discards on a hand the user could see
# was strong. The same misread class produced 2 of that run's 5 misfires.
#
# 4 is the roster minimum over all 33 catalogued cards — asserted against the
# roster in test_validate_game_state.py rather than trusted as a literal,
# since the roster is self-extending. Rejecting the state makes the loop
# RE-READ, which is the correct response to a misread and is now cheap: a
# pending matchup survives a brief read failure (MAX_PENDING_READ_FAILURES).
# MAX was 15, which is not a real bound — the strongest card in the game is a
# 9. On 2026-08-26 vision reported `Playing Spike-B (power 10)`; frame
# 20260826_173511_095.jpg shows the hand at that moment held PITCHER cards of
# 9/6/6/7/4 and no card named "Spike-B" exists anywhere in the roster. The
# model invented both the name and the power, the engine played on it, and the
# misfire detector then fired on a card that was never in the hand.
#
# 9 is the roster maximum, asserted against the roster in
# test_validate_game_state.py so it tracks a self-extending catalogue rather
# than a typed-in literal. A power above it is a hallucination, and rejecting
# the state makes the loop re-read — which is cheap now that a pending matchup
# survives a brief read failure.
CARD_POWER_MIN, CARD_POWER_MAX = 4, 9
# OBSERVED, not assumed: the on-screen DISCARDS indicator has exactly TWO
# dots, white when available and dark when spent (frames 20260826_173511_095
# and _174500 of run_20260826_172200 show both states). The comment here used
# to say "game allows 2-3" and the bound was 5.
#
# That looseness had a cost. Vision repeatedly reported "3 discard(s) left" —
# impossible — and the loop acted on it: it issued a discard the game could
# not honour, the hand did not change, so it decided to discard again. 33
# discards were attempted across 4 matches on 2026-08-26 where at most 8 were
# possible, and the counter was seen going UP (1 -> 2 -> 3) between turns.
# Rejecting the state instead forces a re-read, which breaks the loop.
MAX_DISCARDS_PER_MATCH = 2

# A match is 5 rounds, so a "result" screen this early is a transition overlay
# misread, not a finish. Measured 2026-08-31: one card played, "Draw logged",
# $50 gone and a fabricated draw in the record. Set below the shortest
# plausible real match rather than at it — the check only has to separate "the
# match just started" from "the match ended".
MIN_PLAYS_FOR_RESULT = 4
# How many separate polls must agree before an early 0-0 result is believed.
# A transition overlay does not survive a re-read; a real 0-0 finish does.
RESULT_CONFIRM_READS = 3
CARD_SECONDARY_MAX = 9


# The generic type banners vision returns when a card shows no name. A hand
# card has no name printed on it (see the note in the reveal matcher), so these
# ARE the normal reading, not a failure.
_PHASE_FOR_BANNER = {"batter": "batting", "pitcher": "pitching"}


def repair_phase_from_hand(state: dict) -> None:
    """Correct a phase that contradicts an unambiguous hand.

    play_one_turn() branches on `phase` alone, and the engines behind it sort
    the hand purely by power — `best_batting_play()` never checks that what it
    picked is a BATTER. So a misread phase does not merely apply the wrong
    strategy, it can play a card that is wrong for the turn.

    Measured across 2026-09-01's logs, 12 of ~255 decisions (5%) contradicted
    themselves this way:

        9 x  Decision: Playing Pitcher (power N)        <- batting engine, pitcher card
        3 x  Decision: Playing Batter (pitch focus N)   <- pitching engine, batter card

    THE HAND IS THE MORE DIRECT EVIDENCE. `phase` is a single inferred field;
    the hand is five cards whose type banners are printed on them. When every
    named player card in hand agrees and `phase` disagrees, the hand wins.

    Deliberately conservative — it abstains unless the hand is unanimous AND
    every player card carries a generic banner. A real player name ("Rube
    Sharp") says nothing about whose turn it is, and a mixed hand is not
    evidence of anything. Both leave `phase` untouched.
    """
    phase = state.get("phase")
    if phase not in ("batting", "pitching"):
        return                      # validate_game_state rejects this separately
    banners = set()
    for card in state.get("hand") or []:
        if card.get("kind") != "player":
            continue
        want = _PHASE_FOR_BANNER.get(str(card.get("name") or "").strip().lower())
        if want is None:
            # ABSTENTION, ANNOUNCED. This used to write nothing, and a silent
            # abstention is indistinguishable from a check that agreed — so a
            # run where the repair never got a chance to fire looked exactly
            # like one where phase was right all along. That matters here
            # because this guard exists for 12 of ~255 decisions that played
            # the wrong card type at $50 a match.
            print(f"  [repair] phase NOT CHECKED against the hand: card "
                  f"{str(card.get('name') or '')!r} is a real player name or "
                  f"was unreadable, so the hand carries no phase evidence. "
                  f"{phase!r} stands UNVERIFIED — not confirmed.")
            return                  # a real name, or unreadable: no signal here
        banners.add(want)
    if len(banners) != 1:
        print(f"  [repair] phase NOT CHECKED against the hand: banners are "
              f"{sorted(banners) if banners else 'empty (no player cards)'} — "
              f"a mixed or empty hand proves nothing. {phase!r} stands "
              f"UNVERIFIED — not confirmed.")
        return                      # empty or mixed hand proves nothing
    hand_says = banners.pop()
    if hand_says != phase:
        print(f"  [repair] phase read as {phase!r} but every player card in "
              f"hand is a {'batter' if hand_says == 'batting' else 'pitcher'} "
              f"— trusting the hand, playing the {hand_says} turn")
        state["phase"] = hand_says
    else:
        # The agreement case, logged for the same reason: this is the check
        # RUNNING AND PASSING, which is a different fact from the check never
        # having had evidence to run on. Only these two lines together let a
        # log answer "did vision improve, or did the repair stop firing?".
        print(f"  [repair] phase {phase!r} CONFIRMED by an unanimous "
              f"{'batter' if hand_says == 'batting' else 'pitcher'} hand.")


def repair_misread_cards(state: dict) -> None:
    """Re-label a tactics card that vision returned as a player card.

    Measured live 2026-08-31: "Fielding Play" came back as
    {"kind": "player", "power": 1} every poll of one hand. validate_game_state
    then rejected it (power 1 is outside the 4-9 player range) and the caller
    retried the WHOLE read — a fresh API call each time, up to 15, for a card
    whose name already says what it is.

    The name is the authority: only the four TACTICS_NAME_TO_KIND names can
    appear here, and no player shares one. `power` carries the number printed
    on the card, which for a tactics card is its bonus.
    """
    for card in state.get("hand") or []:
        if card.get("kind") != "player":
            continue
        kind = TACTICS_NAME_TO_KIND.get(str(card.get("name") or "").strip().lower())
        if kind is None:
            continue
        bonus = card.pop("power", 0)
        card.update(kind="tactics", type=kind,
                    bonus=bonus if isinstance(bonus, int) and not isinstance(bonus, bool)
                    and bonus >= 0 else 0)
        card.pop("secondary", None)
        print(f"  [repair] {card.get('name')!r} read as a player card — "
              f"re-labelled tactics/{kind} (bonus {card['bonus']})")


def validate_game_state(state: dict) -> None:
    """
    Raise ValueError on a vision read that would otherwise crash deeper in
    the pipeline (hand_to_cards, play_one_turn) with a confusing
    IndexError/KeyError/TypeError. Callers already retry on any exception
    from read_game_state(), so this just turns a silent hallucination into
    a clear, retryable error instead of a stack trace pointing at the
    wrong function.
    """
    if state.get("screen") not in VALID_SCREENS:
        raise ValueError(f"unrecognized screen value: {state.get('screen')!r}")

    # A result screen must carry something to score. `{"screen": "result"}` with
    # nothing else passed, and run() does `"win" if state.get("result_won") else
    # "loss"` — so an empty payload was recorded as a LOSS in progress.json.
    if state.get("screen") == "result":
        has_scores = (isinstance(state.get("your_score"), int)
                      and isinstance(state.get("opp_score"), int))
        if not has_scores and state.get("result_won") is None:
            raise ValueError(
                "result screen carries neither scores nor result_won — there is "
                "nothing to score it from, and defaulting would record a loss")

    # I7: READ_STATE_PROMPT permits "phase": null, but play_one_turn() branches
    # `if phase == "batting" ... else: best_pitching_play(...)` — so a null or
    # missing phase silently plays the PITCHING strategy on a batting turn,
    # with no warning, on a real match. run() also indexes state_json["phase"]
    # outside its try/except, where a missing key crashes the loop outright.
    # Turn both into a retryable ValueError.
    if state.get("screen") in ("turn", "discard_prompt"):
        if state.get("phase") not in ("batting", "pitching"):
            raise ValueError(f"turn screen with unusable phase: {state.get('phase')!r}")

    hand = state.get("hand") or []
    seen_indices = set()
    for card in hand:
        idx = card.get("hand_index")
        if not isinstance(idx, int) or not (0 <= idx < 5):
            raise ValueError(f"hand card has invalid hand_index: {card!r}")
        if idx in seen_indices:
            raise ValueError(f"duplicate hand_index {idx} in hand: {hand!r}")
        seen_indices.add(idx)

        kind = card.get("kind")
        if kind == "player":
            power = card.get("power")
            # `isinstance(True, int)` is True in Python, so a bare isinstance
            # check accepts `"power": true` and plays the card with power=1.
            if not isinstance(power, int) or isinstance(power, bool):
                raise ValueError(f"player card missing/invalid power: {card!r}")
            # RANGE, not just type. Measured fallout of having no range check:
            #   power 0   -> should_redraw() fires and BURNS A DISCARD. This is
            #               exactly the "power 0 best card" defensive discard
            #               that SETTLE_REGION_SETS' comment blames on an
            #               unsettled frame — the validator never stopped it.
            #   power -5  -> played.
            #   power 999 -> played.
            # The ban path already filters `c["power"] > 0` and
            # hand_digit_reader defines MIN_POWER/MAX_POWER; this brings the
            # per-turn path in line with both.
            if not (CARD_POWER_MIN <= power <= CARD_POWER_MAX):
                raise ValueError(
                    f"player card power {power} outside the possible range "
                    f"{CARD_POWER_MIN}-{CARD_POWER_MAX}: {card!r}")
            secondary = card.get("secondary")
            if secondary is not None and (not isinstance(secondary, int)
                                          or isinstance(secondary, bool)
                                          or not (0 <= secondary <= CARD_SECONDARY_MAX)):
                raise ValueError(f"player card has invalid secondary: {card!r}")
            if card.get("name") is not None and not isinstance(card.get("name"), str):
                raise ValueError(f"player card name is not a string: {card!r}")
        elif kind == "tactics":
            if card.get("type") not in {t.value for t in TacticsType}:
                raise ValueError(f"tactics card has invalid type: {card!r}")
            # A null/str bonus reached best_batting_play and was PLAYED,
            # printing "attaching swing boost (+None)" and logging null — and
            # with two boosts of the same kind it crashed instead, so the
            # behaviour depended on hand composition.
            bonus = card.get("bonus")
            if not isinstance(bonus, int) or isinstance(bonus, bool) or bonus < 0:
                raise ValueError(f"tactics card has invalid bonus: {card!r}")
        else:
            raise ValueError(f"hand card has invalid kind: {card!r}")

    for c in state.get("collection") or []:
        if not isinstance(c.get("row"), int) or not isinstance(c.get("col"), int):
            raise ValueError(f"collection card missing row/col: {c!r}")

    # Turn-completeness LAST, deliberately. These are the fields play_one_turn()
    # indexes unconditionally, and a state missing them used to pass here and
    # die deeper with `KeyError: 'runners'` or `IndexError: list index out of
    # range` — precisely the confusing-crash class this function exists to
    # convert into a retryable ValueError.
    #
    # Ordered after the per-card checks so a malformed CARD still reports as a
    # malformed card. Checking completeness first would have made every existing
    # bad-hand case raise "missing runners" instead, quietly turning those
    # assertions into tests of this block rather than of the card validation.
    if state.get("screen") == "turn":
        for key in ("runners", "your_score", "opp_score"):
            if key not in state:
                raise ValueError(f"turn screen missing required field {key!r}")
            # PRESENT is not the same as USABLE. `"your_score": null` and
            # `"opp_score": "seven"` both passed a presence-only check and were
            # logged straight into match_log.jsonl, and the score feeds
            # GameState.target_score.
            val = state[key]
            if key.endswith("_score") and (not isinstance(val, int)
                                           or isinstance(val, bool) or val < 0):
                raise ValueError(f"turn screen has unusable {key}: {val!r}")
        if not isinstance(state["runners"], list):
            raise ValueError(f"runners is not a list: {state['runners']!r}")
        # Three bases. Five runners was accepted and flipped best_pitching_play
        # into its runners-on branch on a fabricated board.
        if len(state["runners"]) > 3:
            raise ValueError(
                f"{len(state['runners'])} runners on a 3-base diamond: "
                f"{state['runners']!r}")
        # The game allows 2-3 discards a match; 99 was accepted and DISCARDED.
        dl = state.get("discards_left")
        if dl is not None:
            # A non-int is a different failure from a miscount — that one is a
            # confused read of the whole scoreboard, so keep rejecting it.
            if not isinstance(dl, int) or isinstance(dl, bool):
                raise ValueError(f"discards_left is not an int: {dl!r}")
            if not (0 <= dl <= MAX_DISCARDS_PER_MATCH):
                # CLAMP, do not reject. Measured live 2026-08-31: vision read
                # 4 off the SAME frame 11 polls running, and the retry loop
                # paid for an API call every time. Retrying cannot fix a stable
                # misread — same frame, same prompt, same wrong answer — and 15
                # of them aborts a match that cost $50.
                #
                # Clamped to ZERO, not to the cap. An unreadable count must
                # never authorise a discard: a hallucinated count is exactly
                # what drove the 2026-08-26 loop — 33 discard attempts across 4
                # matches where at most 8 were possible, the counter observed
                # INCREASING between turns (see test_validate_game_state.py).
                # Rejecting the read and clamping to 0 both prevent that; only
                # clamping also avoids paying for the retry.
                #
                # Safe because discards_left feeds nothing but should_redraw().
                # The cost is one turn played instead of redrawn; the cost of
                # raising is the whole turn plus an API call per retry.
                print(f"  [repair] discards_left {dl} outside "
                      f"0-{MAX_DISCARDS_PER_MATCH} — treating as 0 (no discard)")
                state["discards_left"] = 0
        # A hand with no PLAYER card is not exotic — it is what a mid-deal or
        # partially-legible frame produces, i.e. the same failure the settle
        # gate exists to prevent, arriving by a different route.
        if not any(c.get("kind") == "player" for c in hand):
            raise ValueError(
                f"turn screen with no player card in hand (likely a mid-deal or "
                f"partial read): {hand!r}")


# ---------------------------------------------------------------------------------------
# ONE PAID STATE READ PER CYCLE. THE REST IS LOCAL.
#
# The user's call, after watching a run spend 41 paid state reads on 36 turns: "there
# should only be the one to determine if we are in the middle of the game... if we get
# stuck, we know the next spot that needs local OCR."
#
# THE LOCAL PATH WAS ALREADY COMPUTING ALL OF IT, every turn, as [local-check] -- the
# scoreboard, the three bases, the hand -- and agreeing with the paid answer. It simply
# was not the authority. Measured on the run that prompted this (36 plays):
#
#     hand      21 turns at 4/5 read, 7 at 5/5, ALL agreeing with vision
#     scoreboard OCR agreed with vision on every turn it was compared
#     bases     agreed on every turn
#     paid state reads 41, of which 40 told us what the local readers already knew
#
# AND GETTING STUCK IS THE POINT. When the local path cannot answer, that is a MEASUREMENT
# of the next reader to build -- paying to paper over it hides exactly the gap worth
# finding. So a local failure raises with the reason named, rather than buying an answer.
#
# NOTHING IS DELETED. Set PAID_STATE_ONCE = False and every turn asks the paid model again,
# exactly as before.
PAID_STATE_ONCE = True
_paid_state_done = False


def begin_cycle_state():
    """A new cycle: the next state read is the ORIENTATION read, and it is paid."""
    global _paid_state_done
    _paid_state_done = False
    # Warm the OCR banner reader now. Its cost is the MODEL LOAD (3.1 s) and not the read
    # (0.92 s), so paying it here means the one frame per match that needs it is never the
    # frame that also pays the load. Failure is fine and silent -- the reader is a last
    # resort and everything upstream of it still works.
    try:
        import result_ocr
        result_ocr.start()
    except Exception:
        pass


def local_game_state():
    """The state, read entirely locally. (state, None) or (None, what is missing).

    `screen` is "result" or "turn". The RESULT screen is read first, because a match that
    has ended has no hand to read and the hand reader would report the missing hand as the
    gap -- naming the wrong reader. Anything else comes back as a NAMED GAP.
    """
    try:
        import local_state
    except Exception as exc:
        return None, f"local_state unavailable ({exc})"
    try:
        full = _fast_grab()
        crops = dict(crop_gameplay_regions(full))
    except Exception as exc:
        return None, f"could not capture ({exc})"

    # THE RESULT SCREEN FIRST. It is the one screen with no hand on it, so asking the hand
    # reader first would blame the hand for a match that is simply over.
    try:
        res = local_state.read_result(full)
    except Exception as exc:
        return None, f"result reader failed ({exc})"
    if res.get("is_result"):
        # THE TEMPLATES DETECT; OCR NAMES. Held out by run over an OCR-labelled corpus the
        # templates had no hand in selecting, the word bank scores WIN at min 0.969 and 0/33
        # errors -- and DRAW at min 0.652 with 5 of 10 read as WINNER. A draw called a win
        # writes a win that never happened into the permanent record and into the money
        # arithmetic, which is the same class of error as the draw-logged-as-loss fixed
        # earlier today. Detection is what templates are reliable at, so that is all they do.
        #
        # OCR is shape-blind and reads the renderings that defeat every template, including
        # the arched DRAW that stalled a live run at 0.671. It costs 0.92 s and runs ONCE per
        # match, on the one screen that ends it.
        ocr_outcome = None
        try:
            import result_ocr
            ocr_outcome, ocr_detail = result_ocr.read_banner(full)
        except Exception as exc:
            ocr_detail = f"reader unavailable ({exc})"
        if ocr_outcome is not None:
            if res.get("outcome") and res["outcome"] != ocr_outcome:
                print(f"  [state] result: templates said {res['outcome']!r}, OCR read "
                      f"{ocr_detail!r} -> {ocr_outcome!r}. OCR wins.")
            res = dict(res, outcome=ocr_outcome, why=f"OCR {ocr_detail!r}")
        elif res.get("outcome") is not None:
            # OCR could not read it. The templates have an answer, but on DRAW they are wrong
            # half the time, so it is only taken when OCR is UNAVAILABLE -- not when OCR ran
            # and found no word, which is evidence the screen is not what we think.
            if "unavailable" in str(ocr_detail) or "missing" in str(ocr_detail):
                print(f"  [state] result: OCR unavailable ({ocr_detail}); falling back to the "
                      f"template answer {res['outcome']!r}, which is unreliable on draws")
            else:
                return None, (f"result screen, but OCR could not name it ({ocr_detail}) and "
                              f"the template answer {res['outcome']!r} is not trusted alone "
                              f"-- it misreads 5 of 10 held-out draws as WINNER")
        if res.get("outcome") is None:
            return None, f"result screen, but the outcome is unread: {res['why']} / {ocr_detail}"
        # NO SCORES ARE SUPPLIED HERE, DELIBERATELY. run() prefers a score comparison over
        # result_won because result_won cannot express a draw -- but ocr_scoreboard misreads
        # the RESULT screen (12 of 76 draw frames readable at all, and one of those 12 wrong;
        # see local_state.read_result). `result_outcome` carries the answer instead, and
        # run() prefers it over both.
        won = {"win": True, "loss": False, "draw": None}[res["outcome"]]
        return {"screen": "result", "result_outcome": res["outcome"], "result_won": won,
                "hand": [], "batters_used": None, "collection": [], "runners": None,
                "discards_left": None, "phase": None,
                "your_score": None, "opp_score": None}, None
    if res.get("is_result") is None:
        return None, f"result reader could not run: {res.get('why')}"

    # THE BAN SCREEN. It has no hand on it, so without this the hand reader is asked a
    # question about a screen it cannot see and answers "0 rows, expected 5" -- naming the
    # WRONG reader for the gap, which is how a stalled run sends the next session to fix
    # something that was never broken. This is what stopped the 2026-09-10 01:11 run.
    #
    # read_ban_counter already ships and already NEVER guesses: it OCRs the "N/3" counter and
    # returns None when it cannot read. The ban branch in run() consumes nothing from the
    # state but the screen name, so that is all this returns.
    try:
        banned = read_ban_counter(full)
    except Exception:
        banned = None
    if banned is not None:
        return {"screen": "ban_screen", "hand": [], "batters_used": None,
                "collection": [], "runners": None, "discards_left": None,
                "phase": None, "result_won": None}, None

    # THE DEALER PROMPT. A finished match returns to the world at the table, and until this
    # landed that screen was UNRECOGNISED: the 2026-09-10 10:24 run won its match, dismissed
    # the result, came back here and then burned all 15 stuck attempts against a screen
    # nothing could name. 28 of that run's 29 gaps were this.
    #
    # The test is at_table(), which is ALREADY the authority for the Square press that spends
    # the $50 -- _dealer_prompt_on_screen() is a one-line wrapper around it, and its docstring
    # records why the obvious alternatives are wrong (compass.find_bar returns non-None on
    # EVERY frame including gameplay, and read_bearing answered 177.4 on a gameplay turn, so
    # either would have fired start_match into a live match). Passing the frame already in
    # hand rather than re-grabbing keeps this verdict on the same pixels as the two above.
    try:
        import table_prompt as _tp
        at_dealer = bool(_tp.at_table(full))
    except Exception:
        at_dealer = False
    if at_dealer:
        return {"screen": "match_start_prompt", "hand": [], "batters_used": None,
                "collection": [], "runners": None, "discards_left": None,
                "phase": None, "result_won": None}, None

    hand_img = crops.get("hand")
    if hand_img is None:
        return None, "no hand crop"
    cards, why = local_hand_cards(hand_img)
    if cards is None:
        # NAME THE SCREEN, NOT THE HAND. Every screen that is not a result, a ban grid or a
        # turn arrives here, and reporting it as a hand failure is the same shape as
        # CLAUDE.md 10.1: a message that looks like a diagnosis and points at the wrong
        # component. The hand reader's own reason is kept, because when this IS a turn it is
        # the right answer.
        best_word = max((res.get("scores") or {}).values(), default=-1.0)
        # LAST RESORT: ASK OCR. The template reader matches a SHAPE, so every new rendering
        # of a word is a fresh failure -- over one night it missed DRAW entirely, then the
        # large flat WINNER/LOSER, then the ARCHED draw at 0.671 while the word sat crisp on
        # a motionless screen. Each miss stalled a live run for 35 s or ended it, and each
        # hid itself, because the templates were harvested BY template matching and the
        # census could only contain renderings that already matched (CLAUDE.md 31).
        #
        # OCR does not care about shape. It runs ONLY here -- after result, ban, prompt and
        # hand have all declined -- so it never touches a normal turn, and it costs 0.92 s
        # against a stall that costs 35 s. A None answer is NOT READ, never "no result".
        try:
            import result_ocr
            outcome, detail = result_ocr.read_banner(full)
        except Exception as exc:
            outcome, detail = None, f"reader unavailable ({exc})"
        if outcome is not None:
            print(f"  [state] the templates missed this banner; OCR read it: {detail!r}")
            won = {"win": True, "loss": False, "draw": None}[outcome]
            return {"screen": "result", "result_outcome": outcome, "result_won": won,
                    "hand": [], "batters_used": None, "collection": [], "runners": None,
                    "discards_left": None, "phase": None,
                    "your_score": None, "opp_score": None}, None
        return None, (f"UNRECOGNISED SCREEN -- not a result (best word {best_word:.3f} "
                      f"against {local_state.RESULT_MIN}; OCR: {detail}), not a ban grid "
                      f"(no N/3 counter), and the hand reader says: {why}")

    st = {"screen": "turn", "hand": cards, "batters_used": None, "result_won": None,
          "collection": []}

    sb = crops.get("scoreboard")
    if sb is not None:
        try:
            got = local_state.read_discards_left(sb)
            if got is not None:
                st["discards_left"] = got
        except Exception:
            pass
        try:
            sc = ocr_scoreboard(sb)
            st["your_score"] = (sc.get("your") or [None, None, None])[-1]
            st["opp_score"] = (sc.get("opponent") or [None, None, None])[-1]
        except Exception:
            pass
    st.setdefault("discards_left", None)

    try:
        ph, _ = local_state.read_phase(hand_img)
        st["phase"] = ph
    except Exception:
        st["phase"] = None

    bases = ("third_base", "second_base", "first_base")
    if all(crops.get(b) is not None for b in bases):
        try:
            out = local_state.read_runners(*[crops[b] for b in bases])
            if out and out.get("count") is not None:
                st["runners"] = [{"name": None, "power": None, "secondary": None}
                                 for _ in range(out["count"])]
        except Exception:
            pass
    st.setdefault("runners", None)

    # THE FIELDS THAT DECIDE A PLAY. Without a phase the engine silently runs the pitching
    # strategy on a batting turn (see validate_game_state), so an unread phase is a GAP,
    # not a default.
    if st.get("phase") is None:
        return None, "phase not read locally"
    if st.get("runners") is None:
        return None, "runners not read locally"
    return st, None


def read_game_state(mask_low_contrast: bool = False) -> dict:
    """Ask Claude to read the current screenshot into structured state.
    mask_low_contrast is passed straight through to capture_state_images_b64().

    Sends the overview + labeled region crops from capture_state_images_b64()
    rather than one full-frame image — each image is preceded by a text
    label so the model knows which crop is which. See READ_STATE_PROMPT
    and capture_state_images_b64() for why (cuts image tokens ~55-60%
    without losing the ability to recognize non-turn screens)."""
    # Per-image inline reminders for the three base crops — added
    # 2026-08-24 after live testing found vision repeatedly reporting an
    # empty "runners" list while local OCR confidently found a real,
    # roster-matching runner (confirmed 3x in one session: Papa Jody
    # Gain, Zachary Lee, Claude Ewer, all with correct stats). The
    # runners instruction previously lived only as one passive bullet in
    # a long rules list at the very end of the prompt, disconnected from
    # the three actual images it applies to — this puts the question
    # directly next to each image's pixels instead of relying on the
    # model recalling a distant instruction by the time it gets there.
    BASE_CROP_HINT = "{label} — look carefully: is this a bare round coin (empty, no runner) or a face-up player card with a readable name/power (a real runner)? Don't default to empty without checking."
    # PAID_READS_CARDS -- the card crops are no longer SENT. They are still computed,
    # because the local readers and record_local_hand need them; only the encode-and-ship
    # is skipped. That is four of six images per call, and it is the money.
    # The card crops are still COMPUTED -- the local readers and record_local_hand need
    # them -- but while PAID_READS_CARDS is False they are not encoded and shipped. That
    # is four of six images per call, and it is the money.
    PAID_CROPS = None if PAID_READS_CARDS else ("overview", "scoreboard")
    content = []
    for label, img_b64 in capture_state_images_b64(mask_low_contrast=mask_low_contrast):
        if PAID_CROPS is not None and label not in PAID_CROPS:
            continue
        label_text = BASE_CROP_HINT.format(label=label) if label in ("third_base", "first_base", "second_base") else label
        content.append({"type": "text", "text": f"[{label_text}]"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": SCREENSHOT_MEDIA_TYPE, "data": img_b64}})
    content.append({"type": "text", "text": READ_STATE_PROMPT})

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,  # thinking is disabled below, so no need for the extra
                          # headroom that used to absorb 1500+ tokens of internal
                          # thinking before the JSON answer — verified live 2026-08-23
        thinking={"type": "disabled"},  # removes the variable thinking-token latency/cost
                                        # (and the truncation bug it caused) with no accuracy loss
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    state = extract_json(text)
    # ORDER MATTERS NOW. The paid answer no longer carries a hand, so the local build has
    # to happen BEFORE anything that reads state["hand"] -- repair_phase_from_hand did,
    # and silently saw an empty list.
    apply_local_readers(state)
    _retry_local_hand(state)
    repair_misread_cards(state)
    repair_phase_from_hand(state)
    validate_game_state(state)
    return state


# A LOCAL FAILURE MUST NOT COST A PAID CALL.
#
# Measured on the first live run of the readable-hand gate: 26 of 31 paid calls were
# read_game_state, and the loop went from 1.44 reads per turn to 5.00. The mechanism was
# mine: the all-or-nothing local hand build refused 16 hands, each refusal raised out of
# validate_game_state, and the caller's retry is a WHOLE FRESH PAID CALL. So the retry
# loop was pointed at the wrong thing -- a re-grab costs ~21 ms of local reading, a paid
# retry costs a call and several seconds.
LOCAL_HAND_REGRABS = 4
LOCAL_HAND_REGRAB_SLEEP = 0.25
REFUSED_HAND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "overnight", "refused_hands")


def _save_refused_hand(img, why):
    """Keep a frame the local reader refused. Never raises into the turn loop."""
    if img is None:
        return
    try:
        os.makedirs(REFUSED_HAND_DIR, exist_ok=True)
        stamp = time.time_ns()
        img.save(os.path.join(REFUSED_HAND_DIR, f"hand_{stamp}.png"))
        with open(os.path.join(REFUSED_HAND_DIR, "why.jsonl"), "a") as fh:
            fh.write(json.dumps({"t": stamp, "why": why}) + "\n")
    except Exception:
        pass


def _retry_local_hand(state):
    """Re-grab and re-read LOCALLY when the hand did not build. Never raises.

    The paid call has already happened by the time this runs, so this does not save that
    one -- it saves the NEXT one, by not letting validate_game_state raise and send the
    caller round for a fresh paid read.
    """
    if not state.get("_hand_unread") or PAID_READS_CARDS:
        return
    for i in range(LOCAL_HAND_REGRABS):
        try:
            time.sleep(LOCAL_HAND_REGRAB_SLEEP)
            hand_img = dict(crop_gameplay_regions(_fast_grab())).get("hand")
            if hand_img is None:
                continue
            cards, why = local_hand_cards(hand_img)
        except Exception:
            continue
        if cards is not None:
            state["hand"] = cards
            state.pop("_hand_unread", None)
            print(f"  [local] hand read on local re-grab {i + 1} "
                  f"-- no paid retry needed")
            return
    print(f"  [local] hand still unread after {LOCAL_HAND_REGRABS} local re-grabs "
          f"({state.get('_hand_unread')}) -- the paid path takes it from here")


# How few cards may remain before the hand is not a hand. Four of five survive a turn only
# 45% of the time -- measured, after the user pointed out the assumption was wrong: the
# real spread is 2 to 5 with a mean of 2.77, because a turn can play a card, play a card
# WITH a tactics card attached, or discard.
# REMEMBER THE HAND, SLOT BY SLOT (the user's design).
#
# The whole hand is still read every turn -- it costs 21 ms and it works -- but what was
# read is KEPT. When a slot cannot be read, the value already known for that slot is used
# instead of dropping the card.
#
# WHY THAT IS SAFE, AND IT IS THE USER'S POINT: a card only changes when it is PLAYED or
# DISCARDED, and we are the ones who play it. So the slots that changed are known exactly,
# not inferred -- forget_hand_slot() is called at the two places that spend a card, and a
# forgotten slot is never carried forward.
#
# AND EVERY READABLE CARD AUDITS THE MEMORY FOR FREE. Measured over the 445-hand corpus:
# 910 checks where a slot was both remembered and readable, and the memory disagreed with
# the reader ZERO times. Memory is only consulted for slots the reader cannot see, so a
# drifted model is caught on the next turn that can see that slot.
#
# Coverage on that same corpus is 4 of 14 unreadable cards (29%), and the limit is the
# CORPUS, not the design: it holds about one frame per turn, taken at whatever moment the
# old timing happened to fire, so a card whose right-hand neighbour was dealt in the same
# turn was never seen clean. Captures taken with the readable-hand gate should do better;
# that is unmeasured and is not claimed here.
# Same gate as the hail mary, and measured the same way: the four true art matches scored
# 0.948-0.989 and nothing else in 445 hands reached 0.90.
HAND_MEMORY_MIN_ART = 0.90
_hand_memory = {}


def forget_hand_slot(*slots):
    """A slot we SPENT. Its card is gone, so nothing about it may be carried forward."""
    for s in slots:
        if s is not None:
            _hand_memory.pop(int(s), None)


def reset_hand_memory():
    """A new match, or any point where the hand is not the hand we remember."""
    _hand_memory.clear()


MIN_LOCAL_HAND_CARDS = 3
# The hail mary's gate. Art correlation, measured: the four true recoveries scored
# 0.948-0.989 and nothing else in 445 hands reached 0.90.
HAIL_MARY_MIN_ART = 0.90
HAIL_MARY_KEEP = 24
_hail_mary_seen = []


def _card_art(img, r):
    """A card's ART as a unit vector -- deliberately NOT including the disc, because the
    disc is the thing that is missing when this is needed."""
    try:
        import numpy as _np
        s = img.width / local_hand_module().ANCHOR_W
        x, y = r.get("x"), r.get("y")
        if y is None:
            return None
        b = (max(0, int(x - 56 * s)), max(0, int(y + 18 * s)),
             min(img.width, int(x + 10 * s)), min(img.height, int(y + 92 * s)))
        if b[2] - b[0] < 12 or b[3] - b[1] < 12:
            return None
        from PIL import Image as _I
        a = _np.asarray(_I.fromarray(_np.asarray(img.convert("L"))[b[1]:b[3], b[0]:b[2]])
                        .resize((32, 32), _I.LANCZOS), dtype=_np.float32).ravel()
        a -= a.mean()
        n = float(_np.linalg.norm(a))
        return None if n < 1e-6 else a / n
    except Exception:
        return None


def local_hand_module():
    import local_hand
    return local_hand


def _remember_card(vec, digit, sec):
    if vec is None:
        return
    _hail_mary_seen.append((vec, int(digit), int(sec)))
    del _hail_mary_seen[:-HAIL_MARY_KEEP]


def _hail_mary_card(row):
    """(power, secondary) for a card whose disc did not read, from a RECENT hand where the
    same card did. None when nothing matches. Never guesses: the gate is measured."""
    vec = row.get("_art")
    if vec is None or not _hail_mary_seen:
        return None
    try:
        import numpy as _np
        best, bv = None, -1.0
        for v, d, s in _hail_mary_seen:
            sc = float(_np.dot(vec, v))
            if sc > bv:
                best, bv = (d, s), sc
        return best if bv >= HAIL_MARY_MIN_ART else None
    except Exception:
        return None


def _hand_signature(hand_img):
    """What the reader currently sees, as a comparable tuple, or None.

    Two identical signatures a poll apart mean the hand has stopped moving. It counts
    UNREADABLE slots too -- a slot that reads nothing twice running is just as settled as
    one that reads a 7, and the hand memory covers it downstream.
    """
    if hand_img is None:
        return None
    try:
        import local_hand
        rows = local_hand.read_hand(hand_img)
    except Exception:
        return None
    return tuple((r.get("kind"), r.get("digit"), r.get("secondary"), r.get("type"))
                 for r in rows)


def local_hand_cards(hand_img):
    """(cards, None) in the paid schema's shape, or (None, why) when the hand is not
    fully readable.

    ALL OR NOTHING, deliberately. hand_to_cards() indexes c["power"], c["secondary"],
    c["type"] and c["bonus"] with [] rather than .get(), so a half-built hand is a
    KeyError deep in play_one_turn; and a hand missing one card is not a hand -- the
    decision engine would choose from four cards believing it saw five.

    `name` is None on player cards ON PURPOSE. Hand cards do not display a name
    (CLAUDE.md section 3), so there is nothing to read and nothing downstream reads it --
    matching a played card against a reveal is done on POWER.
    """
    try:
        import local_hand
    except Exception as exc:
        return None, f"local_hand unavailable ({exc})"
    try:
        rows = local_hand.read_hand(hand_img)
    except Exception as exc:
        return None, f"read_hand raised ({exc})"
    # The fan is five slots BY CONSTRUCTION, so its own geometry is the authority --
    # MAX_HAND_SIZE lives in input_controller and is not imported here (a NameError the
    # undefined-name test has already caught once in this file).
    want = len(local_hand.SLOT_PLAYER)
    if len(rows) != want:
        return None, f"{len(rows)} rows, expected {want}"
    # Each row carries its own ART, so the hail mary has something to match on and so a
    # card that DID read can be remembered for the next hand that cannot read it.
    for r in rows:
        r["_art"] = _card_art(hand_img, r)
    cards = []
    dropped = []
    for i, r in enumerate(rows):
        kind = r.get("kind")
        if kind == "player":
            digit, sec = r.get("digit"), r.get("secondary")
            if digit is None:
                # THE HAIL MARY (the user's idea, and their framing). Before giving up on
                # a card, look for the SAME CARD in a recent hand, where its disc may have
                # been readable. Measured over 445 recorded hands: it recovers 4 of 25
                # refused cards (16%), and all four were adjudicated correct by eye.
                #
                # WHAT IT ACTUALLY RESCUES, which is narrower than it sounds: in all four
                # the disc WAS on screen and simply scored under the gate. A genuinely
                # OCCLUDED card -- the disc hidden under its neighbour -- is only
                # recovered if that card was in an earlier hand unoccluded.
                got = _hail_mary_card(r)
                if got is not None:
                    digit, sec = got
                    print(f"  [local] slot {i}: power unread, recovered as {digit} "
                          f"from a recent hand (hail mary)")
            if digit is None or sec is None:
                # THE MEMORY. A slot we did not spend still holds the card it held last
                # turn, so what was read then is what is there now. Only slots we have
                # not spent are in here -- forget_hand_slot() removes the ones we play.
                remembered = _hand_memory.get(i)
                # SLOT IDENTITY IS THE RULE, and it is what the console says.
                # VERIFIED LIVE, twice, with a clean starting state asserted first: play
                # slot 2, and slot 2 is the ONLY slot that changes -- and the replacement
                # is readable the moment it lands. (A third round was excluded: the user
                # pointed out it was the last hand of the inning, so the whole hand was
                # replaced.) So the slots that changed are the ones WE SPENT, and we know
                # exactly which those are.
                #
                # An art check was tried first and is NOT used, because it is too strict
                # in exactly the case that matters: the overlap that hides a card's disc
                # also covers part of its art, so identity cannot be confirmed precisely
                # when it is needed. Gated on art the memory fired 0 times in 445 hands.
                #
                # THE SAFETY IS forget_hand_slot(), NOT A SIMILARITY SCORE, and
                # tests/minigame/test_hand_memory_forgets.py fails if any site that spends
                # a card stops calling it.
                if remembered is not None:
                    digit, sec = remembered["power"], remembered["secondary"]
                    print(f"  [local] slot {i}: unreadable, carried forward as "
                          f"{digit}/{sec} (slot not spent since it was last read)")
            if digit is None or sec is None:
                # A CARD THAT CANNOT BE READ IS NOT A HAND THAT CANNOT BE READ.
                # Rejecting the whole hand turned an unreadable CARD into an unreadable
                # STATE, and every one of those cost a paid call: measured live, the loop
                # went 1.44 -> 5.00 -> 8.67 read_game_state calls per turn. A hand with
                # one invisible card is still playable -- that card simply is not played.
                # hand_index is preserved on the others, so input targeting still hits the
                # right card.
                dropped.append(i)
                continue
            # EVERY READABLE CARD AUDITS THE MEMORY, free of charge. A disagreement means
            # the hand moved in a way we did not cause, so the memory is wrong and the
            # reader is right -- say so loudly and take the reader's answer.
            was = _hand_memory.get(i)
            if was is not None and r.get("digit") is not None and (
                    str(was["power"]) != str(r.get("digit"))):
                print(f"  [local] slot {i}: MEMORY WAS WRONG "
                      f"({was['power']}/{was['secondary']} remembered, "
                      f"{r.get('digit')}/{r.get('secondary')} read) -- taking the read")
            if r.get("digit") is not None:
                # `art` is kept for diagnostics only -- the carry-forward decision is
                # forget_hand_slot(), not similarity.
                _hand_memory[i] = {"power": r.get("digit"), "secondary": r.get("secondary"),
                                   "art": r.get("_art")}
            cards.append({"kind": "player", "name": None, "power": int(digit),
                          "secondary": int(sec), "hand_index": i})
            # and the art bag, for the hail mary when a slot has no memory at all
            _remember_card(r.get("_art"), digit, sec)
        elif kind == "tactics":
            if r.get("type") is None or r.get("bonus") is None:
                # Same rule. An unread tactics card is one card not played, not a dead
                # hand -- the screen-gate work reached the same conclusion independently:
                # "a tactics card whose adds_power did not read is simply not played".
                dropped.append(i)
                continue
            cards.append({"kind": "tactics", "name": r["type"], "type": r["type"],
                          "bonus": int(r["bonus"]), "hand_index": i})
        else:
            dropped.append(i)
            continue
    # THE FLOOR. Dropping is not free: the decision engine then chooses from fewer cards
    # believing that is the hand. One missing card is a worse choice; three missing is not
    # a hand at all, and asking the paid model is the honest answer.
    if len(cards) < MIN_LOCAL_HAND_CARDS:
        return None, (f"only {len(cards)} of {len(rows)} cards read "
                      f"(slots {dropped} unreadable)")
    if dropped:
        return cards, f"played without slots {dropped} (unreadable)"
    return cards, None


def on_turn_screen(hand_img):
    """Is this frame a TURN screen -- i.e. are the three base crops actually the DIAMOND?

    THE DIAMOND READER CANNOT ANSWER THIS FOR ITSELF, AND ON A BAN SCREEN IT LIES.
    The base crops land on BAN-GRID CARDS there, and a grid card is a power disc with no
    diamond coin -- which is exactly read_base's `occupied` rule -- so it reports a runner
    and then reads a REAL shield badge off the wrong card. Measured over the frames
    read_ban_counter labels as ban screens (labelled by a DIFFERENT detector from the one
    under test, so this is not 10.31):

        368 ban frames   base crops called OCCUPIED   144 of 1104
                         ...a CONFIDENT speed came back   60   worst score 0.782

    NO THRESHOLD FIXES IT, so do not raise SHIELD_MIN (0.69) for this. The worst false
    read is 0.782 and the true-runner population's p05 is 0.857 -- a 0.075 band with a
    real 5% tail already under it, so moving the gate buys this at the price of real
    runners. It is not a badge problem; it is a WRONG CROP problem (CLAUDE.md 10.23), and
    the fix is context, not a constant.

    THE HAND READER IS THE GATE. Over those 368 ban frames it returned a hand ZERO times,
    against 116 of the 255 non-ban frames beside them. `read_phase` measures identically
    (0 of 368 ban, 112 of 255 non-ban) and either would work -- an earlier draft of this
    docstring claimed read_phase leaked on ban screens and that was WRONG, an artefact of
    scoring an unlabelled population. The hand reader is chosen because it is the SAME
    reader local_game_state's ladder uses to reach screen="turn", so a tool and the live
    path cannot disagree about what a turn screen is.

    That ladder is also why the live path was never exposed: it only reaches screen="turn"
    through this reader. The exposure was the three diagnostic tools, which called
    read_base/read_runners with no gate at all and would print runners onto a sheet of a
    ban screen -- corrupting a measurement rather than a play.
    """
    if hand_img is None:
        return False
    try:
        return local_hand_cards(hand_img)[0] is not None
    except Exception:
        return False


def read_state_for_turn():
    """The state the turn loop reads. PAID once per cycle, LOCAL every turn after.

    A local failure RAISES with the gap named. The caller already retries and counts
    stuck attempts, so the run surfaces the missing reader instead of buying past it.
    """
    global _paid_state_done
    # ...AND `paid_model_allowed()`, or the turn loop cannot run at all.
    #
    # This branch made the ORIENTATION read PAID, unconditionally. With the paid model
    # off -- the shipped default and the user's standing instruction -- read_game_state
    # raises PaidModelDisabled, and `_paid_state_done = True` is set AFTER the call so it
    # is never reached: EVERY turn raises, run() counts 15 stuck attempts and stops with
    # `unreadable_screens`. The loop this project exists to run could not play a single
    # match. No test caught it because every run harness stubs read_state_for_turn.
    #
    # Nothing is lost by skipping it. Section 3 lists a local reader for every field the
    # orientation read supplies, and the line below already falls through to exactly
    # those; the paid read was a convenience for the first turn of a cycle, not a
    # dependency. When the model IS allowed the old behaviour is unchanged.
    if (not PAID_STATE_ONCE or not _paid_state_done) and paid_model_allowed():
        st = read_game_state()
        _paid_state_done = True
        print(f"  [state] orientation read (PAID): screen={st.get('screen')!r} "
              f"-- every turn after this one is local")
        return st
    st, gap = local_game_state()
    if st is not None:
        return st
    raise ValueError(f"LOCAL STATE GAP: {gap} -- this is the next reader to build; "
                     f"no paid call was made")


def apply_local_readers(state: dict, crops: dict = None) -> None:
    """Correct the paid model's answer with the local readers, in place. Never raises.

    TWO DIFFERENT CLAIMS, and the code keeps them apart:

      OVERRIDE  discards_left. Measured against the USER'S OWN EYES on eight boards
                spanning every disagreement shape: local 8 of 8, paid 0 of 8. The paid
                model answers 2 on 286 of 360 turns, which is a default rather than a
                reading, and once returned an impossible 3. The user found the mechanism --
                the fat middle of the S in DISCARDS reads as a third dot -- and the local
                reader samples two fixed anchors and never sees the letters.
                This feeds should_redraw(), so it decides DISCARD against PLAY.

      FILL ONLY  runners and phase. Local agrees with the paid model 97.2% and 96.1% of
                the time over 360 turns, and agreement is NOT evidence about who is right
                on the rest. So they only supply a field the paid model left empty, and a
                disagreement is reported and then LEFT ALONE.

    Every correction prints. A silent one is indistinguishable from none at all, and these
    run on a $50 path.
    """
    if crops is None:
        crops = _last_gameplay_crops
    if not crops or state.get("screen") not in ("turn", "discard_prompt"):
        return
    try:
        import local_state
    except Exception:
        return

    # ---- THE HAND, BUILT LOCALLY. The paid model is no longer asked for it. ----------
    # It never read the cards anyway: over 2,171 recorded hand cards its `name` was
    # 'Batter'/'Pitcher' (the type banner), '', 'None', 'Unknown' or one of 57 invented
    # names including six spellings of the same thing -- and on 32 of 33 frames that
    # contained NO CARDS AT ALL it returned a full five-card hand. That is a default, not
    # a reading, and it was hiding the local reader's true numbers behind it.
    if crops.get("hand") is not None and not PAID_READS_CARDS:
        cards, why = local_hand_cards(crops["hand"])
        if cards is not None:
            state["hand"] = cards
        else:
            # NOT READ is a real answer and it must look different from an empty hand.
            state["hand"] = []
            state["_hand_unread"] = why
            # AND THE REFUSED FRAME IS KEPT. It was not, and that was a blind spot of
            # exactly the shape CLAUDE.md 10.1 names: record_local_hand only fires after
            # the PAID read succeeds, so every frame the local reader refused was
            # captured, rejected and discarded. A live run refused 16 hands and every one
            # of the 6 frames it did save read COMPLETE -- the failures were unseeable.
            _save_refused_hand(crops.get("hand"), why)
            print(f"  [local] hand NOT READ: {why}")

    if crops.get("scoreboard") is not None:
        try:
            got = local_state.read_discards_left(crops["scoreboard"])
        except Exception:
            got = None
        if got is not None and got != state.get("discards_left"):
            print(f"  [local] discards_left {state.get('discards_left')} -> {got} "
                  f"(the dot counter; the paid model was 0 of 8 against the user's eyes "
                  f"on this field)")
            state["discards_left"] = got

    if crops.get("hand") is not None and not state.get("phase"):
        try:
            ph, _ = local_state.read_phase(crops["hand"])
        except Exception:
            ph = None
        if ph:
            print(f"  [local] phase was empty -> {ph} (the card banners, unanimous)")
            state["phase"] = ph

    bases = ("third_base", "second_base", "first_base")
    if state.get("runners") is None and all(crops.get(b) is not None for b in bases):
        try:
            out = local_state.read_runners(*[crops[b] for b in bases])
        except Exception:
            out = None
        if out and out.get("count") is not None:
            # The count is all decision_engine consumes (it branches on runners being
            # non-empty). A NAME cannot be supplied by a disc reader, so the entries are
            # explicitly nameless rather than invented.
            state["runners"] = [{"name": None, "power": None, "secondary": None}
                                for _ in range(out["count"])]
            print(f"  [local] runners was empty -> {out['count']} on base "
                  f"(bases read locally; names not available and not invented)")


def read_matchup_reveal(img=None) -> list:
    """
    Read whichever face-up reveal cards (yours vs the opponent's) are
    currently visible mid-turn-resolution — each side up to 2 entries
    (a player card, plus a tactics card if one was attached). Returns a
    list of dicts, either {"kind": "player", "name", "power",
    "secondary"} or {"kind": "tactics", "name", "bonus", "paired_with"}
    (0-4 entries total). The caller matches kind=="player" and
    name != our own to find the opponent's card, then finds any
    kind=="tactics" entry paired_with that name for their tactics bonus.

    Used for match_log.jsonl: capturing the opponent's actual card (and
    whether they boosted its power) lets later analysis control for it,
    instead of only ever seeing our own card's stats next to a final
    outcome that's confounded by whatever the opponent actually played —
    a boosted opponent power would otherwise look like an unexplained
    outcome and risk being misattributed to the fielding/speed effect
    this logging exists to investigate (caught by the user, 2026-08-24,
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
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        thinking={"type": "disabled"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": SCREENSHOT_MEDIA_TYPE, "data": img_b64}},
                {"type": "text", "text": READ_MATCHUP_PROMPT},
            ],
        }],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return extract_json(text).get("cards", [])


# Static catalogue of (absolute_row, col) -> PlayerCard, compiled from
# this session's clean 33-card scan of a fully-unlocked collection
# (2026-08-23). The ban-screen grid layout is fixed game-wide — every
# player sees the same card in the same position, only the lock state
# differs per save. Confirmed by cross-checking against Taylere's
# partial collection: the same names landed in the same (row, col) she
# had unlocked. read_full_ban_collection() checks this FIRST for every
# unlocked position and only falls back to a vision call
# (read_ban_row_cards()) for positions missing from this table (row 6,
# cols 3-4, never captured in any scan this session — cut off by
# either a transient mismatch or the tactics-section boundary before a
# clean read landed on them). Row 5's "Noah 'The Rat Baron' Kelly"
# (col 2) and row 6 col 2 "Thomas Thomas" only appeared in one of two
# scans this session and are included as best-effort; if a future
# vision fallback ever disagrees with an entry here, trust the vision
# read over this table for that run.
KNOWN_BAN_ROSTER = {
    (0, 0): PlayerCard("Johnny Drawers", 7, 1),
    (0, 1): PlayerCard("Mama Jody Gain", 5, 1),
    (0, 2): PlayerCard('Harold "Fisto" Blunt', 9, 3),  # corrected 2026-08-24: live capture showed secondary=3, table had 1
    (0, 3): PlayerCard("Jenny Jody Gain", 6, 0),
    (0, 4): PlayerCard("Donny Mekesz", 5, 3),
    (1, 0): PlayerCard("Claude Ewer", 7, 0),
    (1, 1): PlayerCard("William Lee-Gains", 4, 0),
    (1, 2): PlayerCard('Brandon "Binger" Ortiz', 5, 2),
    (1, 3): PlayerCard("Joshua Diaz", 4, 0),
    (1, 4): PlayerCard("Justin Young", 6, 0),
    (2, 0): PlayerCard("Zachary Lee", 6, 2),
    (2, 1): PlayerCard('Johnny "Blaze" Sweets', 4, 3),
    (2, 2): PlayerCard("Johnny C-Train Goudenberg", 7, 0),
    (2, 3): PlayerCard("Charlie Pepper", 8, 0),
    (2, 4): PlayerCard("Josef Bunz-Konicky", 9, 2),
    (3, 0): PlayerCard("Rube Sharp", 8, 1),
    (3, 1): PlayerCard('Austin "Cur" Bunz', 8, 1),
    (3, 2): PlayerCard('Jacob "Cheesehead" McQueen', 9, 1),
    (3, 3): PlayerCard("William Brown", 4, 3),
    (3, 4): PlayerCard("Jeremiah Curd", 7, 0),
    (4, 0): PlayerCard("Marian Bunz-Twarog", 4, 1),
    (4, 1): PlayerCard("Jedediah Wetters", 4, 2),
    (4, 2): PlayerCard("Brian Coker", 8, 1),
    (4, 3): PlayerCard("Timmeh Rattycum", 4, 3),
    (4, 4): PlayerCard("Joe Jody Gain", 6, 0),
    (5, 0): PlayerCard("Papa Jody Gain", 5, 0),
    (5, 1): PlayerCard('Daniel "The Rat-Ta-Train" Cruz', 4, 3),
    (5, 2): PlayerCard('Noah "The Rat Baron" Kelly', 6, 2),
    (5, 3): PlayerCard("Joel Blunt", 9, 0),
    (5, 4): PlayerCard("Bartholomew Creasley", 5, 1),
    (6, 0): PlayerCard("Jake Saucepan Black", 5, 3),
    (6, 1): PlayerCard("Mickey Brown", 5, 0),
    (6, 2): PlayerCard("Thomas Thomas", 5, 3),
}

# Self-extending: any position the vision fallback reads that isn't in the
# hardcoded table above gets appended here and persisted to disk, so later
# runs (any save) never need vision for that position again. The roster is
# game-wide fixed data, not per-save, so unlike _cached_ban_collection this
# is safe — and useful — to keep across runs.
# Opt-in for the one test that drives persistence on purpose (test_known_ban_roster),
# which points LEARNED_BAN_ROSTER_FILE at its own scratch path first. OFF by default so
# an offline run can never write PERMANENT ground truth into the real file; a test that
# forgets writes nothing and FAILS, which is the safe direction to be wrong in.
LEARN_ROSTER_IN_TESTS = False

# ANCHORED ON THIS FILE, like compass_scale.json and view_bounds.json, not on cwd.
# A bare relative name means a run launched from anywhere else loads no learned
# entries at import and writes a fresh file there -- the learned roster silently
# stops applying, with nothing to see.
LEARNED_BAN_ROSTER_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "known_ban_roster_learned.json")


def _load_learned_roster():
    # N8: this runs at MODULE SCOPE, so a truncated/corrupt file would make
    # `import orchestrator` fail for every script including the test suite.
    # A malformed cache should degrade to "no learned entries", not brick the
    # project. Paired with the atomic write below, which is what prevents
    # truncation in the first place.
    if not os.path.exists(LEARNED_BAN_ROSTER_FILE):
        return
    try:
        with open(LEARNED_BAN_ROSTER_FILE) as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: ignoring unreadable {LEARNED_BAN_ROSTER_FILE} ({e}) — "
              "continuing with the built-in roster only.")
        return
    # Valid JSON of the WRONG SHAPE (a list, a dict of strings, a missing key)
    # would raise here — outside the try above, at module scope, breaking
    # `import orchestrator` for every script including the tests. Validate each
    # entry and skip anything malformed rather than letting one bad row brick
    # the project.
    if not isinstance(raw, dict):
        print(f"WARNING: {LEARNED_BAN_ROSTER_FILE} is not an object — ignoring it.")
        return
    for key, v in raw.items():
        try:
            row, col = map(int, key.split(","))
            # N26: `name` must be validated as a STRING, not just present.
            # PlayerCard accepts any object, and the breakage surfaces later at
            # ROSTER_BY_NAME's `norm_name(c.name)` — at module scope, so a null or
            # numeric name bricks `import orchestrator` for every script
            # including the tests. Exactly the failure class this guard exists
            # to prevent (verified: name=null and name=123 both broke import).
            if not isinstance(v.get("name"), str) or not v["name"].strip():
                raise ValueError(f"name must be a non-empty string, got {v.get('name')!r}")
            card = PlayerCard(v["name"], int(v["power"]), int(v["secondary"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            print(f"WARNING: skipping malformed learned-roster entry {key!r}.")
            continue
        KNOWN_BAN_ROSTER[(row, col)] = card


# I3: a learned entry becomes permanent ground truth — once written, that
# position short-circuits and vision NEVER re-reads it, on any save, ever.
# The only gate on the vision path was a count match, and on the OCR path a
# loose fuzzy match (cutoff 0.5), either of which can resolve to the wrong
# card and carry the wrong power/secondary. Require two INDEPENDENT agreeing
# reads before persisting. Pending (seen-once) entries live in memory only.
_pending_roster = {}


def _learn_roster_entry(pos, card, source="unknown"):
    prev = _pending_roster.get(pos)
    if prev is None or (prev[0].name, prev[0].power, prev[0].secondary) != (card.name, card.power, card.secondary):
        # First sighting, or it disagrees with the last one — hold, don't persist.
        _pending_roster[pos] = (card, source)
        if prev is not None:
            print(f"  Roster read at {pos} disagreed with the previous one "
                  f"({prev[0].name!r} vs {card.name!r}) — not learning either.")
        return False

    KNOWN_BAN_ROSTER[pos] = card
    ROSTER_BY_NAME[norm_name(card.name)] = card   # M7: keep name lookup in sync

    # THE WRITE IS SUPPRESSED UNDER TEST, like every other per-machine cache. This was
    # the one write-then-read file without the guard: compass._save_scale_cache and
    # input_controller._save_view_cache both have it, this did not. And the cost here is
    # worse than theirs -- a learned entry is PERMANENT ground truth ("once written,
    # that position short-circuits and vision NEVER re-reads it, on any save, ever"), so
    # an offline run driving the ban scan with two agreeing reads poisons the roster for
    # good. The in-memory learning above still happens, so tests exercise the same path
    # with the same values; only the persistence stops.
    if os.environ.get("BASEBALL_TEST_RUN") and not LEARN_ROSTER_IN_TESTS:
        return True
    raw = {}
    if os.path.exists(LEARNED_BAN_ROSTER_FILE):
        # Tolerate a corrupt cache here too. _load_learned_roster() already
        # warns-and-continues at import, but this bare read would then hard-fail
        # every ban scan — the file would warn once and break the run forever.
        try:
            with open(LEARNED_BAN_ROSTER_FILE) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            raw = {}
    raw[f"{pos[0]},{pos[1]}"] = {"name": card.name, "power": card.power,
                                 "secondary": card.secondary, "source": source}
    _atomic_write_json(LEARNED_BAN_ROSTER_FILE, raw)
    return True


def norm_name(s) -> str:
    """Canonical form of a card name, FOR COMPARISON ONLY.

    The vision model is not stable about capitalisation — it returned
    "Pitcher" one turn and "PITCHER" the next, and an exact `!=` then logged
    our own card as the opponent's (match_log row 18). Every name comparison
    in this file goes through here so that class of bug is fixed once rather
    than at each call site.

    Deliberately NOT applied to stored names. Uppercasing the roster itself
    would fix the same bug, but it burns the display form ('Harold "Fisto"
    Blunt' in every log and print), makes new match_log rows incomparable with
    the mixed-case history already on disk, and still needs a normaliser
    wherever vision text arrives — so it loses data without removing the
    helper. Store what the game shows; compare canonically.
    """
    return (s or "").strip().casefold()


# Name -> PlayerCard, built from KNOWN_BAN_ROSTER for OCR fuzzy-matching
# (see ocr_runner_card() below). Dict keys dedupe automatically; rebuilt
# whenever a new roster entry is learned so newly-seen names are
# immediately matchable without a script restart.
ROSTER_BY_NAME = {norm_name(c.name): c for c in KNOWN_BAN_ROSTER.values()}

# Load persisted entries AFTER ROSTER_BY_NAME exists, then refresh it so
# learned names are immediately fuzzy-matchable (M7).
_load_learned_roster()
ROSTER_BY_NAME.update({norm_name(c.name): c for c in KNOWN_BAN_ROSTER.values()})


# The game labels a card by its TYPE wherever its identity is not being
# shown — cards in hand, and the face-down card in a reveal. Those banner
# words are not names and must never resolve to a roster entry.
#
# "batter" scores 0.615 against the surname "wetters", above the surname
# fallback's threshold, so it force-matched Jedediah Wetters on 12 occurrences
# of the 2026-08-26 run — fabricating a specific card, with a specific power,
# for a card whose identity was never read at all. Callers could not defend
# themselves: the fallback's cutoff was hardcoded, so even cutoff=0.999
# returned Jedediah Wetters. Fixed here rather than at the call sites because
# every caller routes through this function, and two of the three already
# carry scar tissue from the same over-permissive matching.
CARD_TYPE_BANNERS = {"batter", "pitcher", "fielder", "runner", "catcher"}


def match_roster_name(raw_text: str, cutoff: float = 0.5,
                      allow_surname_fallback: bool = True,
                      min_margin: float = 0.0):
    """
    Fuzzy-match a (possibly OCR-garbled) name against the known roster.
    Tries the whole string first; if that fails, falls back to matching
    just the last word (surname) — OCR noise on this game's ribbon-
    banner card names tends to hit the first word harder (the banner's
    pointed/notched left edge overlaps it), so "NUGC SHARP" still
    resolves to "Rube Sharp" via the surname fallback even though the
    whole-string match misses it. Returns the matching PlayerCard (with
    trusted power/secondary from the roster, not from OCR) or None.
    """
    text = norm_name(raw_text)
    if not text:
        return None
    if text in CARD_TYPE_BANNERS:
        return None
    whole = difflib.get_close_matches(text, list(ROSTER_BY_NAME.keys()), n=2, cutoff=cutoff)
    if whole:
        # The surname fallback below refuses ambiguous matches (N7), but this
        # whole-string pass never did — and it runs FIRST, so it silently
        # pre-empted that guard. Measured: "Brown" -> Mickey Brown (2 Browns in
        # the roster), "Jody Gain" -> Joe Jody Gain (4), "Charlie" -> Zachary
        # Lee. A short or garbled read scores just high enough against one
        # full name to win outright, and the caller receives a confident,
        # specific, wrong card. Callers that cannot afford that pass
        # min_margin and get a refusal instead of a coin-flip.
        if min_margin and len(whole) > 1:
            _top = [difflib.SequenceMatcher(None, text, w).ratio() for w in whole[:2]]
            if _top[0] - _top[1] < min_margin:
                return None
        return ROSTER_BY_NAME[whole[0]]
    if not allow_surname_fallback:
        return None

    # N7: build surname -> [names]. A dict keyed by surname silently collapsed
    # collisions (4 "* Gain" cards -> one, 2 "* Brown" -> one), so a garbled
    # first word could resolve to a same-surname card that isn't the right one.
    # If a surname is ambiguous we cannot tell them apart from the surname
    # alone, so refuse rather than guess.
    last_word = text.split()[-1]
    by_surname = {}
    for name in ROSTER_BY_NAME:
        by_surname.setdefault(name.split()[-1], []).append(name)
    # max(): a caller asking for high precision must be able to get it. This
    # threshold was a bare 0.6, so `cutoff` governed only the whole-string
    # pass and a caller passing 0.999 still received surname guesses.
    match = difflib.get_close_matches(last_word, list(by_surname.keys()), n=1,
                                      cutoff=max(0.6, cutoff))
    if match:
        names = by_surname[match[0]]
        if len(names) == 1:
            return ROSTER_BY_NAME[names[0]]
    return None


# --- The confusions tesseract ACTUALLY makes on the ban-card name banner ---
#
# MEASURED 2026-09-03, not assumed: 64 genuine reads aligned against their true
# roster names across 11 real ban-grid frames (test_fixtures/20260824_2005*,
# test_fixtures/ban_scan/, test_fixtures/ban_counter/, and one screenshot_log
# frame). Tally, most frequent first:
#
#   word space dropped, words fused    35 of 88   JUSTINYOUNG, RUBESHARP,
#                                                 MAMAJODYGAIN, JOSHUADIAZ
#   '-' dropped                         8 of 8    BUNZ KONICKY, C TRAIN
#   '"' round a nickname dropped        7 of 7    BRANDON BINGER ORTIZ
#   leading letters dropped            10         OHNNY, NNY MEKESZ, SHUA DIAZ
#   interior letter dropped             5         JOHNNY C TRAIN (the lone C)
#   d -> o                              3         ORAWERS, JOEJOOYGAIN
#   j -> s                              3         SOSHUADIAZ, SOSEF
#   letter hallucinated                 5         's' x4 (the ribbon's tail
#                                                 reads as "ss"), 'g' x1
#   trailing letter dropped             0
#
# The textbook OCR confusions were observed ZERO times on this font and are
# deliberately NOT in the table: no rn->m, no l->1, no O->0, no S->5. Adding
# them would only widen the matcher against errors this pipeline does not make.
#
# 50 of those 76 individual errors are SEPARATOR damage, not letters, which is
# why the letters-only projection below carries most of the work: measured on
# the corpus, the projection alone recovers 3 previously-abstained cards and
# the substitution table recovers 1 more ('SOSHUADIAZ ss'). Reported as such —
# the confusion table is worth one card, not four.
OCR_CONFUSION_CLASSES = (("d", "o"), ("j", "s"))
_OCR_CANON = {ch: cls[0] for cls in OCR_CONFUSION_CLASSES for ch in cls}


def ocr_match_key(name) -> str:
    """Compare-only projection of a name for ban-banner OCR.

    Letters only (so a fused "JUSTINYOUNG", a dropped hyphen and a dropped
    nickname quote all collapse onto the true name), lowercased, with the two
    MEASURED confusable pairs folded onto one representative each.

    Comparison only, exactly like norm_name(): nothing is ever stored in this
    form. It is lossy on purpose.
    """
    return "".join(_OCR_CANON.get(ch, ch)
                   for ch in re.sub(r"[^a-z]", "", (name or "").lower()))


# Both gates are MEASURED against the corpus above, and both are needed.
#
#   cutoff  the lowest ACCEPTED true read scores 0.889 ('SHUA DIAZ' ->
#           'Joshua Diaz'); the highest-scoring string that MUST be refused is
#           the ambiguous partial 'Jody Gain' at 0.842, with 'Frank Coker'
#           (a plausible name that is not in the roster) at 0.800. 0.85 sits
#           in that gap and is the same strictness the direct matcher already
#           uses — this pass must never be the loose one.
#   margin  the runner-up gate match_roster_name()'s whole-string path never
#           had. The four "* Jody Gain" cards and the two "* Brown" cards are
#           1.000/0.833 apart from each other, so a partial read lands on a
#           coin-flip without it. Every accepted true read on the corpus beats
#           its runner-up by >= 0.167; every refused negative by <= 0.042.
BAN_OCR_KEY_CUTOFF = 0.85
BAN_OCR_KEY_MARGIN = 0.10
# Under 4 letters there is nothing to identify a card by: the corpus's junk
# reads ('me', 'be', 'jy', 'we', 'nog') are all shorter than this, and the
# shortest roster key is 9 ('joelblunt').
BAN_OCR_MIN_KEY_LEN = 4


def match_roster_name_ocr(raw_text, cutoff: float = BAN_OCR_KEY_CUTOFF,
                          margin: float = BAN_OCR_KEY_MARGIN):
    """Confusion-aware roster match for a ban-card name banner, or None.

    Same contract as match_roster_name() in strict mode — returns a roster
    PlayerCard (trusted power/secondary) or refuses — but compares on
    ocr_match_key() so the separator damage above stops counting as character
    error, and REQUIRES a margin over the runner-up so a partial read of one
    of the roster's four near-identical "* Jody Gain" cards abstains instead
    of guessing.

    Never widens: it is only ever reached after the direct matcher has already
    refused, so it can add resolutions but cannot change one.

    No CARD_TYPE_BANNERS check here, deliberately. One was written and then
    REMOVED on 2026-09-03 because mutation testing could not tell it from
    nothing: the five banners score 0.471-0.533 against their nearest roster
    key, far under the 0.85 cutoff, so deleting the guard changed no outcome
    on any probe. A guard indistinguishable from its own absence is the
    project's most expensive bug shape, so the property is asserted where it
    is actually enforced instead — tests/test_ban_ocr_confusion.py pins those
    scores, and fires if a future roster entry ever lifts one toward the
    cutoff. match_roster_name(), which runs first, keeps its own check.
    """
    key = ocr_match_key(raw_text)
    if len(key) < BAN_OCR_MIN_KEY_LEN:
        return None
    scored = sorted(
        ((difflib.SequenceMatcher(None, key, ocr_match_key(n)).ratio(), n)
         for n in ROSTER_BY_NAME), reverse=True)
    if not scored or scored[0][0] < cutoff:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
        return None
    return ROSTER_BY_NAME[scored[0][1]]


# Settings for a roster lookup whose answer will be ACTED ON rather than
# merely displayed. Measured against the live garbled reads: these keep
# 'Brandon "Binge"' (0.811, margin 0.349) and 'Pure Sharp' (0.800, 0.419)
# while refusing 'Brown' (2 Browns), 'Jody Gain' (4 Gains), 'Charlie' and
# 'Johnny \'Train\' Schweitert' (margin 0.025). The initial-form reads
# 'P. J. Gain'/'M.J. Gain' also fall below this bar — they resolve correctly
# at the loose default, but not distinguishably, so here they abstain.
ROSTER_CONFIDENT_CUTOFF = 0.75
ROSTER_CONFIDENT_MARGIN = 0.10

# No player card in the game has a power below this. The hand digit reader
# treats 1-3 as a TACTICS bonus, so a vision misread of our own card's power
# into that range would otherwise match nothing in any reveal and produce a
# guaranteed false misfire on every such turn. Derived, not typed: the roster
# is self-extending and a hardcoded 4 would rot silently.
MIN_PLAYER_POWER = min(c.power for c in KNOWN_BAN_ROSTER.values())

# ---------------------------------------------------------------------------
# WHAT HAPPENED IN THE AT-BAT, FROM THE REVEAL RATHER THAN FROM THE SCOREBOARD
# ---------------------------------------------------------------------------
# The old rule was one line -- `if new_score > score_before: outcome = "home_run"` -- and
# it is wrong for a reason the user supplied on 2026-09-12 with sources: SPEED decides how
# many bases a runner takes, so a fast batter scores on an ordinary hit, a runner on third
# scores on a single, and CLAUDE.md section 4 already records that a LOSING at-bat can
# still advance runners. Every one of those raised the score and was logged "home_run".
#
# Measured over the 345 scorable rows in match_log.jsonl: 20 are labelled home_run at a
# margin that cannot produce one, and 10 of those at a LOSING margin -- our pitcher beat
# the batter by up to 4 and it still wrote home_run. Those rows feed the tactics analysis.
#
# The margin is known AT THE REVEAL, which is the moment the user pointed at: both cards
# are face up, so the result follows from the game's own rule rather than from watching
# the scoreboard afterwards. Runs are recorded SEPARATELY, because "how the at-bat went"
# and "how many runs it produced" are different questions and the old label conflated them.
POWER_TACTICS_KINDS = ("swing_boost", "pitch_boost")   # only these add power (section 4)
AUTO_HOME_RUN_MARGIN = 3     # "beating it by 3+ is an automatic home run" -- CLAUDE.md 4


def effective_power(power, bonus, kind):
    """Power after a tactics card, counting ONLY the kinds that add power."""
    if power is None:
        return None
    return power + ((bonus or 0) if kind in POWER_TACTICS_KINDS else 0)


def reveal_margin(row):
    """OUR margin over theirs at the reveal, or None if either card is unknown.

    Sign is from the BATTER'S side in both phases: while pitching, the at-bat belongs to
    the opponent, so their power leads. An unreadable card gives None rather than a guess
    -- a fabricated margin would mislabel the row it was invented to describe.
    """
    ours = effective_power(row.get("our_power"), row.get("our_tactics_bonus"),
                           row.get("our_tactics_kind"))
    theirs = effective_power(row.get("opp_power"), row.get("opp_tactics_bonus"),
                             row.get("opp_tactics_kind"))
    if ours is None or theirs is None:
        return None
    return ours - theirs if row.get("phase") == "batting" else theirs - ours


def classify_outcome(margin, runs, runners_before, runners_after):
    """(outcome, basis) for one at-bat. `basis` says WHICH evidence decided it.

    With a margin the game's own rule decides, and runs are just runs. Without one there
    is no honest verdict available, so the fallback says "scored" for a turn that produced
    runs and refuses to name it a home run -- the whole defect being fixed.
    """
    rose = (runs or 0) > 0 or (runners_after is not None and runners_before is not None
                               and runners_after > runners_before)
    if margin is None:
        return ("scored" if rose else "out"), "delta"
    if margin >= AUTO_HOME_RUN_MARGIN:
        return "home_run", "margin"
    if margin > 0:
        return "hit", "margin"
    if margin == 0:
        # A tie is a coin flip capped at first base, so the screen is the only witness.
        return ("tie_win" if rose else "out"), "tie"
    # A loss is an out -- and an out can still drive runners in, which is exactly the
    # case the old rule recorded as a home run.
    return "out", "margin"



def exclude_runners(cards, runners, floor=2):
    """Drop revealed cards that are actually BASE RUNNERS, not the faceoff.

    This game draws runners as face-up cards on the diamond, and the reveal
    read scoops them up alongside the two cards actually in play. Confirmed
    live on 2026-08-26 at 0, 1 and 2 runners, across first, second and third:

        runners [Johnny Drawers, Donny Mekesy]
        reveal  ['Donny Mekesz', 'William Lee Gains', 'Johnny Drawers', 'Rube Sharp']

    The rule held without exception — revealed players == 2 faceoff cards plus
    one per runner — and the runner names come back matching the base crops.
    Uncorrected this was the single largest source of lost rows: every one of
    the 15 "no OPPONENT card identified" drops in a 30-play run, i.e. half of
    all turns played, and it bites hardest exactly when the bot is doing well
    enough to have runners on.

    Refuses to strip below `floor` cards. A faceoff always has two, so if name
    collisions would leave fewer, the filter is doing more harm than good and
    the caller is better off deciding on the raw list.

    floor=1 is for the one caller that has ALREADY identified our own card by
    power and is stripping runners out of the remainder — there, one card left
    is the answer, not a sign of over-stripping. Everyone else wants the
    default: measured 2026-08-31, four of five "no OPPONENT card identified"
    drops were this filter refusing to strip 2 runners out of 3 revealed cards
    and handing back all three, which then failed the two-card power path.
    """
    if not runners or not cards:
        return cards

    def identity(name):
        # The two readers spell the same card differently — the runner crop
        # gave "Donny Mekesy" for the reveal's "Donny Mekesz". Resolve both to
        # a roster identity so one letter of OCR noise does not defeat the
        # filter; fall back to the raw normalised name for cards the roster
        # does not cover (there are known gaps, e.g. Cur Van).
        hit = match_roster_name(name or "", cutoff=ROSTER_CONFIDENT_CUTOFF,
                                min_margin=ROSTER_CONFIDENT_MARGIN)
        return norm_name(hit.name) if hit else norm_name(name)

    on_base = {identity(r.get("name")) for r in runners if r.get("name")}
    on_base.discard("")
    if not on_base:
        return cards
    kept = [c for c in cards if identity(c.get("name")) not in on_base]
    return kept if len(kept) >= floor else cards


def pick_opponent_card(reveal_cards, ours_name, our_power=None, bonus=0, runners=None):
    """The opponent's player card from a reveal, or None if undecidable.

    Selecting by name alone dropped the ENTIRE turn whenever the name was
    unreadable, and it often is: the reveal's "PLAY BALL!" banner sits across
    the opponent card's name band from ~0.5s to ~2s after onset, and 14 of the
    28 reveal captures in the 2026-08-26 run landed inside that window. The
    banner leaves the type banner and the power perfectly legible while
    covering the name — which is why 15 of 44 logged rows carry a bare
    "Pitcher"/"Batter" as the opponent, the vision model falling back to the
    type banner it CAN still see.

    So when names cannot separate the two cards, separate them by POWER: with
    two player cards revealed and only one matching what we played, the other
    is theirs regardless of what its name reads. Abstains when both or neither
    match — a wrong opponent writes a WRONG row, which is worse for this
    dataset than no row at all.
    """
    players = [c for c in reveal_cards if c.get("kind") == "player"]
    if not players:
        return None

    ours = norm_name(ours_name)
    if ours:
        others = [c for c in players if norm_name(c.get("name")) != ours]
        if len(others) == 1:
            return others[0]

    if our_power is not None and len(players) == 2:
        acceptable = {our_power, our_power + (bonus or 0)}
        mine = [c for c in players if revealed_powers(c) & acceptable]
        if len(mine) == 1:
            return next(c for c in players if c is not mine[0])

    # THREE OR MORE CARDS: identify ours by power, then strip runners from what
    # is left. Reached only when both paths above abstained, so this can turn a
    # dropped turn into a logged one but can never change an answer they gave.
    #
    # Why it is needed: exclude_runners() at the call site refuses to strip
    # below two, so 3 revealed cards with 2 runners on base come back untouched
    # and the two-card path never runs. That was 4 of the 5 "no OPPONENT card
    # identified" drops on 2026-08-31.
    #
    # Still abstains unless the answer is UNIQUE at both steps — exactly one
    # card carrying our power, and exactly one survivor after the runners are
    # removed. A wrong opponent writes a wrong row, which is worse than no row.
    if our_power is not None and runners and len(players) > 2:
        acceptable = {our_power, our_power + (bonus or 0)}
        mine = [c for c in players if revealed_powers(c) & acceptable]
        if len(mine) == 1:
            rest = [c for c in players if c is not mine[0]]
            rest = exclude_runners(rest, runners, floor=1)
            if len(rest) == 1:
                return rest[0]
    return None


def revealed_powers(card) -> set:
    """Every power a revealed card could plausibly have.

    BOTH available readings are kept, because both are demonstrably wrong in
    opposite directions and adjudicating between them is not this check's job:

      * the reveal's OCR read Brian Coker as power 5; the roster says 8;
      * it read Josef Bunz-Konicky as power 0 — no card in this game has
        power 0, so that is a failed read — while the roster says 9.

    The caller only ever asks "could the card we played be in here?", so a
    union is the right shape: it keeps the detector from crying misfire
    merely because its two sources disagree. An empty set means nothing is
    known about this card, which the caller must treat as ignorance rather
    than as evidence of a mismatch.
    """
    out = set()
    p = card.get("power")
    # A power below MIN_PLAYER_POWER is a MISREAD, not a card — 1-3 is the
    # tactics BONUS digit range, and the reveal reader picks those up as power.
    # Live 2026-08-26: revealed [('Pitcher', 3), ('Jedediah Wetters', 4)] and
    # [('Pitcher', 7), ('Batter', 1)] each produced a confident false misfire,
    # because a bogus value counts as "known" and suppresses the per-card
    # abstention below. Treat it exactly like the unread 0 it resembles.
    if p and p >= MIN_PLAYER_POWER:
        out.add(p)
    # Confident settings, not the permissive default. At cutoff=0.5 a garbled
    # read resolves to the WRONG card (11 of 132 systematic garbles did), and
    # when our own power is also unread that wrong power becomes the only
    # evidence — turning this roster lookup from a false-positive FIX into a
    # false-positive SOURCE. Abstaining costs nothing here; guessing costs a
    # suppressed row and an input backoff.
    hit = match_roster_name(card.get("name") or "",
                            cutoff=ROSTER_CONFIDENT_CUTOFF,
                            min_margin=ROSTER_CONFIDENT_MARGIN)
    if hit:
        out.add(hit.power)
    return out


def reveal_is_complete(reveal_cards, runners) -> bool:
    """Did the reveal read return EVERY player card that was on the diamond?

    The count is not a guess. exclude_runners() measured it live on 2026-08-26
    and the rule held without exception:

        face-up player cards == 2 faceoff cards + one per runner on base

    Re-confirmed 2026-09-01 by replaying center_card_edge_fraction() over the
    461 logged frames of the live match and opening all 11 frames it triggers
    on: 2 player cards in the 8 reveals with the bases empty, 3 in the 3 with a
    runner on. 11 of 11, no exceptions.

    So a read that comes back SHORT of that has dropped a card, and the caller
    cannot know it was not ours. our_card_in_reveal() would otherwise treat the
    survivors' powers as positive evidence of a mismatch and call a misfire out
    of an incomplete list — which is how three of the eight misfires on the
    2026-09-01 run were manufactured, e.g.

        vision runners: [{'name': 'Jake Saucepan Black', 'power': 5, ...}]
        revealed [('Jake Baucepan Black', 5), ('Joel Blunt', 9)]

    Two cards back where three were on screen: the runner and one faceoff card.
    exclude_runners() then refuses to strip the runner (it will not go below
    two, see its docstring), so the runner's power counts AGAINST us and the
    turn is discarded with a confident "your card is absent".

    This does NOT gate pick_opponent_card — that one already abstains on its
    own when it cannot separate the cards, and it is the misfire warning, not
    the opponent read, that costs a real run: a false misfire also fires
    input_controller.report_misfire(), which drove ACTION_DELAY 0.25s -> 0.75s
    on this run before the backoff gave up and reset itself.

    Fails OPEN when the runner count is unknown or wrong: state_json's runner
    read is itself flaky, and an undercount just leaves today's behaviour.
    """
    seen = sum(1 for c in reveal_cards if c.get("kind") == "player")
    return seen >= 2 + len(runners or [])


def our_card_in_reveal(our_power, bonus, players) -> bool:
    """Could one of the revealed cards be the card we just played?

    Returns True when the answer is yes OR undecidable. The caller turns a
    False into a suspected misfire that suppresses the turn's log row and
    slows the input layer down, so nothing short of positive evidence of a
    MISMATCH may return False.

    Both earlier versions failed live by being one-sided:
      * name-based (2026-08-25) compared a hand card's name — which does not
        exist, hand cards carry no name — against the reveal: 2 of 2 turns
        flagged, zero rows logged;
      * power-based (2026-08-26) abstained when OUR power was unknown but not
        when the REVEALED powers were, so a reveal reading
        [('Brandon "Binge"', 0), ('Josef Bunz-Konicky', 0)] produced a
        confident misfire against our played 9 — when Bunz-Konicky IS a 9.
    Each time the adaptive backoff then slowed the whole run in response to
    the detector's own false alarms. Hence: abstain on either side's
    ignorance, and accept either reading of a revealed power.
    """
    if our_power is None or our_power < MIN_PLAYER_POWER:
        # `is None` alone was still one-sided: a power of 1-3 is not a card,
        # it is a misread (most likely a tactics bonus digit picked up as
        # power). No revealed card can ever carry it, so every such turn was
        # a guaranteed false misfire — the v2 asymmetry mirrored onto our
        # own side of the comparison.
        return True
    acceptable = {our_power, our_power + (bonus or 0)}
    per_card = [revealed_powers(c) for c in players]
    # An unreadable card could BE the one we played, so its presence makes the
    # question undecidable — pooling every power into one set hid that. It let
    # a reveal of [our card: unreadable, opponent: Mickey Brown 5] conclude
    # "our 4 is absent" on the strength of evidence about the OPPONENT's card
    # alone. Judge ignorance per card, not in aggregate.
    if any(not s for s in per_card):
        return True
    known = set().union(*per_card) if per_card else set()
    return not known or bool(known & acceptable)


# Fraction of a base-crop's own height where the name ribbon banner
# sits, measured live 2026-08-24 against real occupied-base crops
# (below the character art, above the smaller team-name subtitle).
CARD_NAME_STRIP_FRAC = (0.72, 0.90)


def ocr_runner_card(base_crop_img):
    """
    Read a base-position crop (from GAMEPLAY_REGIONS_FRAC) locally: OCR
    just the name-banner strip, fuzzy-match it against the known
    roster, and return the roster's PlayerCard (trusted power/secondary)
    — or None if the base is empty (bare coin, no card) or the name
    didn't match anything confidently.

    No vision API call. The banner is light text on a dark ribbon with
    notched/pointed ends, which tesseract reads poorly at native
    contrast — inverting + thresholding + upscaling first (tuned
    2026-08-24 against real screenshots) gets a legible-enough read for
    match_roster_name()'s fuzzy match to close the gap on what's left.
    """
    w, h = base_crop_img.size
    y0, y1 = CARD_NAME_STRIP_FRAC
    strip = base_crop_img.crop((0, int(h * y0), w, int(h * y1))).convert("L")
    strip = strip.resize((strip.width * 4, strip.height * 4))
    strip = ImageOps.invert(strip).point(lambda p: 255 if p > 190 else 0)
    text = _ocr_text(strip, ocr_glyphs.PSM_TEXT_BLOCK).strip()

    # The ribbon banner's pointed/notched tail ends often OCR as a
    # second (sometimes first) line of junk — stray punctuation-like
    # glyphs — around the actual name, and which line has the real
    # text shifts slightly by card since the crop's fixed
    # CARD_NAME_STRIP_FRAC doesn't line up identically for every card's
    # exact vertical position. Rather than assume a fixed line, extract
    # letters-only words from EVERY line and keep whichever line has
    # the most of them — junk lines are consistently short (1-3 letter
    # noise), the real name line has multiple longer words.
    candidates = [" ".join(re.findall(r"[A-Za-z]{2,}", line)) for line in text.splitlines()]
    cleaned = max(candidates, key=len, default="")
    # V6: tightened from the loose defaults, but NOT to the ban path's 0.85.
    #
    # It used `match_roster_name(cleaned)` — the same over-permissive setting
    # (N1) that was fixed on the ban screen. Measured against 15 plausible names
    # absent from the roster, the loose setting force-matched 12 of them to a
    # real but WRONG card ('Frank Coker' -> 'Brian Coker', 'Nancy Drew' ->
    # 'Johnny Drawers'), silently attaching that card's power/secondary.
    #
    # The ban path's 0.85 is too strict HERE, because runner-name crops are far
    # more garbled than ban-grid ones: the real read for Rube Sharp is
    # 'NUGC SHARP', which no cutoff above 0.72 accepts. Measured sweep, 5 real
    # garbled reads vs 15 uncatalogued names:
    #     cutoff 0.50 : 5/5 genuine kept, 12/15 unknowns force-matched
    #     cutoff 0.70 : 5/5 genuine kept,  4/15 unknowns force-matched  <- knee
    #     cutoff 0.85 : 3/5 genuine kept,  1/15 unknowns force-matched
    #
    # 0.70 keeps every genuine read while cutting force-matches by two thirds.
    # The looser bar than the ban path is deliberate and the cost asymmetry
    # justifies it: a wrong BAN sends wrong physical input into a paid match,
    # whereas this reader is audit-only (its sole caller is
    # log_local_read_comparison; GameState.runners comes from the vision read at
    # play_one_turn). A wrong match here poisons an audit row, which is worth
    # avoiding but is not worth losing every real read for.
    return match_roster_name(cleaned, cutoff=0.70, allow_surname_fallback=False)


# Defensive safety net in case the prompt's BATTER/PITCHER-only rule
# still lets a tactics card through — filter out any known tactics card
# name before it reaches choose_bans().
KNOWN_TACTICS_NAMES = {"Speed Boost", "Power Swing", "Pitch Focus", "Fielding Play"}

# The four tactics cards map onto TacticsType. The vision prompt returns a
# tactics card's NAME but not its type, so the kind has to be recovered here —
# and it matters, because only SWING_BOOST/PITCH_BOOST add power
# (power_bonus(), simulate.py), so a bonus without a kind cannot be turned into
# effective power at all.
# The only tactics kinds that change the power a reveal will show. Kept as a
# named set beside the mapping so it cannot drift from simulate.power_bonus(),
# which is the authority on the rule.
POWER_TACTIC_KINDS = {TacticsType.SWING_BOOST.value, TacticsType.PITCH_BOOST.value}

TACTICS_NAME_TO_KIND = {
    "power swing": TacticsType.SWING_BOOST.value,
    "speed boost": TacticsType.SPEED_BOOST.value,
    "pitch focus": TacticsType.PITCH_BOOST.value,
    "fielding play": TacticsType.FIELDING_BOOST.value,
}


# The "BANNED CARDS n/3" header. Validated over all 411 cached ban frames:
# 94% read rate (386/411), zero misreads.
# The "n/3" of "BANNED CARDS n/3", as fractions of the frame. TWO boxes,
# tried in order, because the capture geometry CHANGED:
#
#   window capture  1920x1080  the game window — what capture sends today
#   full display    2000x1292  the whole screen, game letterboxed inside it
#
# The same fractions cannot hit the text in both. Only the full-display box
# existed, so on 2026-09-01 this returned None for every live frame — "could
# not read the BANNED CARDS counter — bans NOT verified" — while its test
# stayed green, because every fixture it owned was an old full-display capture.
# That blindness is what let a match start with 1 of 3 bans placed and nothing
# notice. Keep both: the historical fixtures are still the only frames showing
# counts 1, 2 and 3.
BAN_COUNTER_BOXES = ((0.605, 0.145, 0.685, 0.205),    # window capture
                     (0.595, 0.220, 0.690, 0.295))    # full display (legacy)
BAN_COUNTER_BOX_FRAC = BAN_COUNTER_BOXES[1]           # legacy name, still read


def _dealer_prompt_on_screen() -> bool:
    """True only if the REAL "Baseball Cards [] Play ($50)" prompt is visible.

    This is the evidence that a start_match press belongs: the dealer prompt is
    drawn in the world, never over a match, so seeing it proves no match is
    running and the match_start_prompt classification was not a misread of a
    ROUND transition overlay.

    IT MUST NOT BE A HUD TEST. The obvious version — "is the world HUD up?" —
    was written first using compass.find_bar()/read_bearing() and is WRONG:
    measured 2026-09-01, find_bar returns non-None on EVERY frame including ban
    and gameplay screens, and read_bearing returned 177.4 on a gameplay turn.
    Either would have reported "in the world" mid-match and fired start_match
    into it, which is real untracked in-game spend (QA1-F1).

    at_table() demands contrast AND prompt ink AND stroke-shape correlation
    together. Measured on the same frames: False on three gameplay turns and on
    a ban screen (whose ink alone reaches 0.0286), True on both dealer-table
    frames. Any failure answers False, the conservative direction — it only
    ever withholds a retry.
    """
    try:
        import table_prompt as _tp
        return bool(_tp.at_table(_fast_grab()))
    except Exception:
        return False


def read_ban_counter(img):
    """How many cards the ban screen says are banned, or None if unreadable.

    NEVER guesses. An unreadable counter returns None, which callers must treat
    as "not verified" — never as "the number I expected".

    This exists because nothing read the counter, and that blindness hid a live
    failure: OCRing every cached ban frame shows three of five real ban
    sequences finishing at **2/3**, with the match starting anyway two seconds
    later (scoreboard up, ROUND 1, 0-0). Three paid matches were played with a
    ban set the engine did not choose, and two comments in this codebase
    asserted the opposite — that the game "refuses to start" under three bans,
    and that the M11 path "ran successfully through every ban screen" of that
    session. Both were wrong, and unfalsifiable without this read.
    """
    w, h = img.size
    for x0, y0, x1, y1 in BAN_COUNTER_BOXES:
        c = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1))).convert("L")
        c = c.resize((c.width * 4, c.height * 4), Image.LANCZOS)
        for thr in (110, 130, 150):
            b = c.point(lambda p, t=thr: 0 if p < t else 255)
            text = _ocr_text(b, ocr_glyphs.PSM_SINGLE_LINE,
                             whitelist="0123456789/").strip()
            m = re.search(r"([0-3])\s*/\s*3", text)
            if m:
                return int(m.group(1))
    return None


def _tactics_kind_from_name(name):
    """TacticsType value for a tactics card name, or None if unrecognised.

    Abstains rather than guessing: an unknown name means the row is excluded
    from the effective-power analysis, which is correct — inventing a kind would
    silently fabricate the power figure the whole match log exists to measure.
    """
    return TACTICS_NAME_TO_KIND.get(norm_name(name)) if name else None

# Defensive backstop for a mid-scroll-transition card whose name label
# hadn't rendered yet — the model sometimes invents a placeholder like
# "Unknown" instead of following the prompt's "skip it" instruction.
# Caught live on a less-complete collection, 2026-08-23 (a blank-string
# name was already handled by the `c.get("name")` truthiness check;
# this catches the non-empty-but-fake-name variant of the same failure).
PLACEHOLDER_CARD_NAMES = {"unknown", "n/a", "none", "?"}

# Session-scoped cache: reused across ban screens within one script run,
# so only the FIRST match pays the full ~15-call scan cost. Deliberately
# in-memory only, never written to disk — this collection belongs to
# whichever save file is currently playing (it grows as you unlock cards
# through missions), so persisting it risks serving stale or wrong-player
# data on a future run or a different person's save. Clears itself the
# moment the script restarts.
_cached_ban_collection = None


# --- Independent confirmation of where the ban viewport actually is -------
# `top_row = presses_so_far - 1` is otherwise the ONLY thing that knows the
# scroll position: it counts keystrokes SENT, not scrolling that happened. One
# dropped move_down and every subsequent row is mislabelled — replayed against
# real frames, the scan then catalogues a LOCKED card the player does not own
# and choose_bans selects it. That is the cardinal failure of this screen and
# nothing cross-checked it.
#
# The scrollbar thumb answers the question directly. Validated over every
# cached ban frame: 361/361 settled frames correct, 0 wrong, and all 50 moving
# frames correctly refused (a thumb between levels means the grid is still
# animating). ~1.7 ms on a decoded image.
# y0 was 0.294, where the box's top row grazes the darkness threshold and the
# reader refuses a frame it can actually read. Measured over the 172 ban-screen
# frames of the 2026-08-26 run: 51 refusals (29.7%) at 0.294 against 30 (17.4%)
# from 0.298 onward — 21 frames, 12% of the screen's life, refused for nothing.
# Every one of those refusals makes the scan skip a batch and re-read.
#
# The move is strictly safe, not a re-tune: across those frames it changed ZERO
# reads (0 frames where both boxes returned a level and the levels differed)
# and lost no values. The remaining 30 refusals are genuine mid-animation
# frames, which is what the refusal is for. Stable anywhere in 0.298-0.310, so
# 0.300 sits mid-plateau rather than on an edge.
# RE-MEASURED 2026-08-28 for the game-window capture (1920x1080).
#
# The previous box sampled x 0.830-0.850, which lands 50px LEFT of the scrollbar
# in this capture and found nothing but page background — every read returned
# "scrollbar unreadable", the scan skipped every batch, and the ban screen never
# completed. The track is a thin dark line at x~0.858; the THUMB is wider, so
# sampling just right of the track isolates the thumb from the track.
BAN_SCROLLBAR_BOX_FRAC = (0.8585, 0.260, 0.8650, 0.970)
BAN_SCROLLBAR_DARK = 110

# Thumb-top as a FRACTION of frame height, not absolute pixels. The old list was
# in pixels of a differently-cropped capture, so every level was wrong here while
# looking perfectly reasonable.
#
# Measured over 479 frames of a real ban screen. The structure matches the
# original exactly — a larger first step, even middle steps, and a short final
# clamp (steps 0.088, 0.078, 0.077, 0.075, 0.075, 0.074, 0.046 against the old
# 96, 84, 83, 83, 82, 83, 50 px). Same UI, different crop. Level 7 is the bottom
# clamp; do not "regularise" this list.
BAN_SCROLL_LEVEL_FRAC = [0.3241, 0.4120, 0.4898, 0.5667, 0.6417,
                         0.7167, 0.7907, 0.8375]
BAN_SCROLL_TOLERANCE_FRAC = 0.006


def read_ban_scroll_level(img):
    """(level, thumb_top) for the ban grid's viewport.

    Returns level=None when the thumb sits between levels, which means the grid
    is mid-animation — that is a refusal, not a failure, and the caller should
    treat it as "don't know" rather than re-deriving from the press count.
    """
    w, h = img.size
    x0, y0, x1, y1 = BAN_SCROLLBAR_BOX_FRAC
    band = np.asarray(img.convert("L").crop(
        (int(w * x0), int(h * y0), int(w * x1), int(h * y1))), dtype=np.float32)
    dark = np.nonzero(band.mean(axis=1) < BAN_SCROLLBAR_DARK)[0]
    if not len(dark):
        return None, None
    top = int(h * y0) + int(dark[0])
    frac = top / float(h)
    for lvl, want in enumerate(BAN_SCROLL_LEVEL_FRAC):
        if abs(frac - want) <= BAN_SCROLL_TOLERANCE_FRAC:
            return lvl, top
    return None, top


def _max_roster_row() -> int:
    """Highest absolute row the roster knows about. Recomputed, not cached:
    the roster is self-extending, so a value frozen at import would stop the
    tactics-boundary check from moving as new rows are learned."""
    return max((r for r, _ in KNOWN_BAN_ROSTER), default=0)


# TRUST THE ROSTER. When True the ban scan is 100% local: positions resolve
# from KNOWN_BAN_ROSTER by (row, col) and nothing else runs — no name OCR, no
# vision call, no mismatch/retry.
#
# WHAT THIS GIVES UP, stated plainly: the ability to DISCOVER a card the roster
# has never seen. That machinery exists so a game update adding cards would be
# picked up automatically. The owner is renting the game and does not need that
# (2026-08-25), and the roster already covers 100% of visible unlocked
# positions measured across 23 real ban frames.
#
# The two catalogue gaps, (6,3) and (6,4), are simply skipped as ban
# candidates. choose_bans() picks the best 3 from what it sees, so missing two
# of ~33 cards cannot produce a wrong ban — only, at worst, a slightly
# less-optimal one.
#
# Set False to restore vision-backed discovery.
TRUST_ROSTER_ONLY = True


# How many times to ask for the ban cursor before deciding the sensor is BLIND rather
# than momentarily unsure. One None is routine -- mid-scroll and mid-animation both return
# it by design -- so a single probe would fall back constantly; a run of them at
# BAN_NAV_SETTLE apart is the screen not answering at all.
BAN_CURSOR_PROBE_TRIES = 3


def ban_cursor_absolute(img=None):
    """(absolute_row, col) of the ban-screen cursor, read from the SCREEN. None if unsure.

    This is the `look` that input_controller.select_bans_verified navigates by. Absolute row
    is the scrollbar's level plus the cursor's SCREEN row -- the same arithmetic
    read_full_ban_collection already uses to turn a visible cell into a roster position.

    EVERY PART OF IT REFUSES RATHER THAN GUESSES. No fit, no cursor, or a scrollbar
    mid-travel all return None, and the navigator waits and looks again. A cursor position
    that is wrong is worse than one that is late: it bans a card the engine did not choose.
    """
    import ban_grid as _bg
    img = img if img is not None else _fast_grab()
    rows = _bg.find_card_rows(img)
    if not rows:
        return None
    cell, _detail = _bg.cursor_cell(img, rows)
    if cell is None:
        return None
    lvl, _thumb = read_ban_scroll_level(img)
    if lvl is None:
        return None                      # mid-animation: the rows on screen are not level N
    return (lvl + cell[0], cell[1])


def ban_x_on(pos):
    """Is the ban X actually on the card at this ABSOLUTE position?

    The counter says HOW MANY are banned in the whole collection; this says WHETHER THIS
    CARD is one of them, which is the question a caller that just pressed select_card has.
    Nothing could answer it before ban_grid.banned_cells existed, which is why the shipped
    path verifies with a count and cannot tell three right bans from two right and one wrong.
    """
    import ban_grid as _bg
    img = _fast_grab()
    rows = _bg.find_card_rows(img)
    if not rows:
        return False
    lvl, _thumb = read_ban_scroll_level(img)
    if lvl is None:
        return False
    hits, _scores = _bg.banned_cells(img, rows)
    return (pos[0] - lvl, pos[1]) in hits


def read_full_ban_collection(max_presses: int = 40, use_cache: bool = True,
                             trust_roster: bool = None):
    """
    Scroll through the ban screen's full collection, reading it via
    vision, so choose_bans() can see the whole thing instead of just the
    first ~15 cards. Returns a list of (absolute_row, col, PlayerCard)
    for select_bans_and_start_full(). Leaves the cursor back at (0, 0)
    when done.

    Positions are determined entirely in code (detect_ban_grid_locked()
    against the calibrated BAN_GRID_COL_X/ROW_Y boxes), not by asking the
    vision model to report row/col — root-cause fix for a real bug
    (2026-08-23): the model silently shifted visible cards left to fill
    gaps left by masked-out locked cards instead of preserving their
    true columns, confirmed live twice (once on the original approach,
    again after a prompt-only fix attempt). The model's only job now is
    read_ban_row_cards(): return the legible cards it sees in reading
    order, which gets zipped onto the code-derived list of unlocked
    positions. If the count it returns doesn't match the expected
    unlocked-cell count, the whole batch is discarded rather than risk
    assigning any card to the wrong grid position — a wrong position
    (navigating to and toggling the wrong physical card) is worse than a
    temporarily incomplete collection.

    Confirmed live (2026-08-23): the first move_down just moves the
    cursor within the still-fully-visible page (no scroll); every
    move_down after that scrolls the viewport by exactly 1 row. So after
    N total presses, the row at the top of the screen is max(0, N - 1).
    Reading every 2 presses keeps each read mostly-fresh (1 row of
    overlap, deduped by absolute (row, col) now that position is known
    for certain) without a read on every single row.

    Stops once both visible rows are fully locked (assumed to mean the
    bottom of the owned-card section). max_presses is a hard safety
    bound in case that assumption is wrong, or the scroll wanders into
    the tactics-card section beyond (which reads as a mismatch every
    time, since read_ban_row_cards() is told to skip tactics cards but
    detect_ban_grid_locked() doesn't know the difference — safe, just
    wasteful, bounded by max_presses).
    """
    global _cached_ban_collection
    # Did this scan ever disagree with the scrollbar? A scan that did may have seen a
    # fraction of the collection, and caching a fraction is worse than re-scanning.
    _saw_desync = False
    if trust_roster is None:
        trust_roster = TRUST_ROSTER_ONLY
    if use_cache and _cached_ban_collection is not None:
        return _cached_ban_collection

    seen_positions = set()
    full_collection = []
    presses_so_far = 0
    consecutive_mismatches = 0

    try:
        while presses_so_far <= max_presses:
            if presses_so_far == 0:
                # The ban screen fades in, and a dim cell reads as LOCKED.
                # Only the first batch is exposed to it — every later one
                # follows a keypress and is covered by the scrollbar check.
                img, locked_grid = _settled_lock_grid()
            else:
                img = capture_screenshot_image()
                locked_grid = detect_ban_grid_locked(img)
            top_row = max(0, presses_so_far - 1)
            expected_positions = [
                (r, c) for r in range(len(locked_grid)) for c in range(len(locked_grid[r]))
                if not locked_grid[r][c]
            ]

            # B2: cross-check the viewport against the SCROLLBAR before
            # trusting top_row. top_row counts keystrokes SENT, not scrolling
            # that happened — one dropped move_down mislabels every row from
            # there on, and the scan then catalogues a locked card the player
            # does not own, which choose_bans will happily select.
            #
            # A refusal (level=None, thumb mid-travel) means the grid is still
            # animating: skip this batch rather than reading it, since the rows
            # on screen are not the rows top_row claims.
            try:
                _lvl, _thumb = read_ban_scroll_level(img)
            except Exception:
                _lvl, _thumb = None, None
            if _lvl is None:
                print(f"  [ban] scrollbar unreadable or mid-scroll "
                      f"(thumb={_thumb}) — skipping this batch rather than "
                      "trusting the press count.")
                if presses_so_far >= max_presses:
                    break
                for _ in range(2):
                    press("move_down")
                presses_so_far += 2
                wait_for_screen_to_settle(max_wait=6.0, regions="ban")
                continue
            if _lvl != top_row:
                _saw_desync = True
                print(f"  [ban] SCROLL DESYNC: press count says row {top_row}, "
                      f"the scrollbar says {_lvl}. Trusting the scrollbar — the "
                      "press count cannot see a dropped keystroke, and a wrong "
                      "row bans a card the player does not own.")
                # A DESYNC IS THE CHEAPEST "THE PRESSES ARE NOT LANDING" DETECTOR THIS
                # PROJECT HAS, and until 2026-09-13 it only ever narrated. That day every
                # press in a scan went to a /bin/zsh whose command line happened to contain
                # "chiaki" -- pgrep -f matched it, it sorted first, and it was alive, so
                # every guard passed. The scan pressed its way to "row 39" while the
                # scrollbar sat at 4 and returned 8 cards of a 33-card collection.
                #
                # So the desync now RE-RESOLVES the target before pressing again. It is one
                # pgrep, it happens only when something is already wrong, and if the pid was
                # right it changes nothing.
                try:
                    _was = input_controller.chiaki_pid()
                    _now = input_controller.chiaki_pid(refresh=True)
                    if _now != _was:
                        print(f"  [ban] and the input target was WRONG: {_was} -> {_now}. "
                              "The presses were going somewhere else.")
                        record_observation(event="ban_input_target_corrected",
                                           old_pid=_was, new_pid=_now)
                except Exception as _exc:
                    print(f"  [ban] could not re-resolve the input target ({_exc})")
                record_observation(event="ban_scroll_desync",
                                   press_count_row=top_row, scrollbar_row=_lvl)
                top_row = _lvl

            new_count = 0
            if expected_positions:
                absolute_positions = [(top_row + r, c) for r, c in expected_positions]
                roster_hits = {pos: KNOWN_BAN_ROSTER[pos] for pos in absolute_positions if pos in KNOWN_BAN_ROSTER}

                # For any position not yet in the roster by (row, col), try
                # local name-OCR + roster-by-name resolution before ever
                # touching vision. Verified live 2026-08-24: the name
                # banner OCRs reliably (unlike the power/secondary badge
                # digits, which tesseract and EasyOCR both proved unreliable
                # on regardless of crop precision) and match_roster_name()
                # already handles the noisy/garbled text this produces.
                # Whatever resolves here also gets learned by position, so
                # future scans of this exact cell skip straight to the
                # roster_hits short-circuit below with no OCR at all.
                for (rel_row, col), pos in zip(expected_positions, absolute_positions):
                    if trust_roster:
                        # Position lookup is the whole answer here; a position
                        # the roster doesn't know is simply not a ban candidate.
                        continue
                    if pos not in roster_hits:
                        card_crop = get_ban_grid_card_crop(img, rel_row, col)
                        local_card = ocr_ban_card_name(card_crop)
                        if local_card:
                            roster_hits[pos] = local_card
                            if pos not in KNOWN_BAN_ROSTER:
                                if _learn_roster_entry(pos, local_card, source="local_ocr"):
                                    print(f"Learned ban-roster entry at {pos} via local OCR "
                                          f"(2nd agreeing read): {local_card.name}")

            # EARLY TACTICS-BOUNDARY STOP — detected locally, before any vision
            # call. Measured on the 2026-08-25 run: the ban screen took 149 of
            # the run's 175 seconds, sitting idle in 20-40s blocks. That was the
            # scan grinding through the TACTICS section, which the roster does
            # not cover, so every batch fell through to vision, mismatched
            # (read_ban_row_cards correctly filters tactics out), and was
            # RETRIED — two vision calls per wasted step, plus ten fruitless
            # tesseract reads.
            #
            # The tell is free and already computed: tactics cards have no
            # player-name banner, so ocr_ban_card_name returns None for every
            # position (verified against real tactics frames — all ten
            # positions OCR to empty). Combined with being past the roster's
            # known extent, that is conclusive enough to stop here rather than
            # spend four vision calls discovering it.
            #
            # One batch of slack past the roster is deliberately allowed so the
            # self-extending roster can still discover a genuinely new row; it
            # is only the SECOND unrecognised batch that stops the scan.
            if (expected_positions and not roster_hits
                    and top_row > _max_roster_row() + 1):
                print(f"No player names readable at rows {top_row}+ and past the "
                      f"known roster — tactics section, stopping the scan "
                      f"(saved ~2 vision calls).")
                break

            if trust_roster and expected_positions:
                # Take whatever the roster covers and move on. No vision, no
                # retry, no mismatch bookkeeping — the cases those existed for
                # (an uncatalogued card, a garbled read) both resolve to "not a
                # ban candidate" here, which is a safe answer rather than an
                # error.
                missing = [p for p in absolute_positions if p not in roster_hits]
                if missing:
                    print(f"  [ban] {len(missing)} position(s) not in the roster "
                          f"{missing[:4]}{'...' if len(missing) > 4 else ''} — "
                          "skipping as ban candidates (trust_roster).")
                if not roster_hits:
                    print(f"No roster coverage at rows {top_row}+ — end of the "
                          "catalogued collection, stopping the scan.")
                    break
                for pos in absolute_positions:
                    if pos in roster_hits and pos not in seen_positions:
                        seen_positions.add(pos)
                        full_collection.append((pos[0], pos[1], roster_hits[pos]))
                        new_count += 1
                consecutive_mismatches = 0

            elif expected_positions and len(roster_hits) == len(expected_positions):
                # Every unlocked position in view is already catalogued in
                # KNOWN_BAN_ROSTER — skip the vision call entirely. The card
                # roster is fixed game-wide (only lock state differs between
                # players' saves, confirmed by cross-checking Taylere's
                # partial collection against this catalogue), so once a
                # position's card is known once, it's known for every save.
                consecutive_mismatches = 0
                for pos in absolute_positions:
                    if pos not in seen_positions:
                        seen_positions.add(pos)
                        full_collection.append((pos[0], pos[1], roster_hits[pos]))
                        new_count += 1
            elif expected_positions:
                # Two attempts against the SAME captured frame (nothing on
                # screen has changed, so no need to recapture) before giving
                # up on this batch — most mismatches turn out to be a
                # transient bad read rather than a real, persistent
                # disagreement, so a retry meaningfully cuts how often a
                # genuine player-card row gets silently dropped.
                masked_img = mask_low_contrast_regions(img)
                cards = None
                for attempt in range(2):
                    raw_cards = read_ban_row_cards(masked_img)
                    attempt_cards = [
                        c for c in raw_cards
                        if c.get("name") and norm_name(c["name"]) not in PLACEHOLDER_CARD_NAMES
                        and c["name"] not in KNOWN_TACTICS_NAMES
                        and isinstance(c.get("power"), int) and c["power"] > 0
                        # I8: the prompt permits nulls, and line below indexes
                        # c["secondary"] directly — an omitted key would
                        # KeyError mid-scan and abort the whole collection read.
                        and isinstance(c.get("secondary"), int)
                    ]
                    if len(attempt_cards) == len(expected_positions):
                        cards = attempt_cards
                        break
                    elif attempt == 0:
                        print(f"Ban-screen read mismatch (attempt 1/2): expected {len(expected_positions)} "
                              f"legible cards, got {len(attempt_cards)} — retrying per-row before giving up.")
                        # SPLIT THE RETRY BY ROW instead of repeating the same
                        # whole-grid call. Measured 2026-08-25: per-row crops
                        # cost ~25% MORE tokens than one combined crop (167+168
                        # vs 268 — JPEG overhead per image), so per-row is the
                        # wrong default. But a combined read that mismatches
                        # drops BOTH rows, and at the tactics boundary row 0 is
                        # usually real player cards while row 1 is not. That is
                        # how a 33-card roster produced "Read 19 cards": whole
                        # batches discarded for one bad row.
                        #
                        # So: cheap combined read first, and only when it
                        # disagrees does the extra per-row cost buy something —
                        # salvaging the good row instead of losing it.
                        per_row = _read_ban_rows_separately(masked_img, expected_positions)
                        if per_row is not None:
                            cards = per_row
                            break

                if cards is not None:
                    consecutive_mismatches = 0
                    for (rel_row, col), c in zip(expected_positions, cards):
                        pos = (top_row + rel_row, col)
                        card = PlayerCard(c["name"], c["power"], c["secondary"])
                        if pos not in KNOWN_BAN_ROSTER:
                            if _learn_roster_entry(pos, card, source="vision"):
                                print(f"Learned ban-roster entry at {pos} "
                                      f"(2nd agreeing read): {card.name}")
                        if pos not in seen_positions:
                            seen_positions.add(pos)
                            full_collection.append((pos[0], col, card))
                            new_count += 1
                else:
                    consecutive_mismatches += 1
                    print(f"Ban-screen read mismatch persisted after retry — skipping this batch "
                          f"({consecutive_mismatches}/2 before giving up on this section).")

            if new_count == 0 and not expected_positions and presses_so_far > 0:
                break  # both visible rows fully locked — reached the bottom
            if consecutive_mismatches >= 2:
                # Two batches in a row where the contrast-based lock detector
                # and the model's own filtering disagree on count — almost
                # certainly means we've scrolled past the owned player cards
                # into the tactics-card section (which reads as high-contrast
                # "unlocked" to detect_ban_grid_locked() but gets correctly
                # filtered out by read_ban_row_cards()'s prompt). Stop here
                # instead of grinding all the way to max_presses.
                print("Two consecutive ban-screen mismatches — likely past the "
                      "owned cards into the tactics section. Stopping the scan.")
                break
            if presses_so_far >= max_presses:
                break
            for _ in range(2):
                press("move_down")
            presses_so_far += 2
            wait_for_screen_to_settle(max_wait=6.0)
    finally:
        # Always unwind back to (0, 0), even on a failed read mid-scroll —
        # leaving the cursor scrolled would corrupt any retry's assumption
        # that it starts at the top.
        for _ in range(presses_so_far):
            press("move_up")

    # QA1-F6: never cache a result that cannot be right. A mid-animation first
    # frame reads every cell as locked, the scan exits immediately with [], and
    # caching that serves the empty list to every later call in the process —
    # including the caller's own retry loop, which then "retries" 15 times with
    # zero captures and dies as ban_screen_stuck AFTER the $50 was debited. A
    # single bad frame cost the match fee and ended the session.
    #
    # Three bans are needed, so anything under three cards is not a usable
    # collection regardless of why it came back short.
    # ...AND NEVER CACHE A SCAN THAT KNOWS IT WENT WRONG. The >= 3 floor was sized
    # against a mid-animation frame that returns []; OPEN-23's real failure returned
    # EIGHT cards of ~33, which clears it comfortably. The scan's own desync branch
    # had already printed "press count says row 39, the scrollbar says 4" -- it knew --
    # and the result was cached anyway and served to every later ban screen in the
    # process, with zero captures. That turns a one-match problem into a whole-process
    # one: every match after the first bans the best 3 of a stale eighth of the
    # collection, silently. run() never clears it either.
    _short = len(full_collection) < 3
    _suspect = bool(_saw_desync)
    if use_cache and not _short and not _suspect:
        _cached_ban_collection = full_collection
    elif _suspect:
        print(f"Ban scan hit a scroll desync — NOT caching its {len(full_collection)} "
              "card(s). It may be a fraction of the collection, and a cached fraction "
              "would ban the best of an eighth for the rest of the process.")
    elif _short:
        print(f"Ban scan returned only {len(full_collection)} card(s) — not "
              "caching it; the next attempt will re-capture rather than be "
              "served a bad read.")
    return full_collection


# How many times to ask the LOCAL money reader before giving up on it. It requires
# two OCR scales to agree, which a mid-animation frame will not satisfy -- and the
# menu is still animating for seconds after a Load Last Save. Not a confidence
# threshold: every attempt is the same conservative reader, so more tries can only
# turn a refusal into an answer, never a wrong answer into a confident one.
MONEY_READ_TRIES = 5


def read_balance_from_pause_menu() -> int:
    """
    Open the pause menu, read the money total off it via vision, then
    close the menu again.

    Assumption not yet confirmed — watch this closely on the first run:
    Options opens the pause menu with money visible, and pressing Options
    again is what closes it back out (rather than a different button,
    like Circle, being needed to back out of a submenu).
    """
    # VERIFY THE MENU IS ACTUALLY OPEN BEFORE SPENDING A VISION CALL ON IT.
    # toggle_pause is a TOGGLE, and it does not always land first time. When it
    # did not, this captured the WORLD instead — where the only number on screen
    # is the health coin in the bottom-left. Vision duly returned 100, the run
    # recorded it as the wallet, and reported the bankroll as collapsing from
    # $246 to $100. The health coin is a round coin with an embossed face, which
    # is also how the prompt describes MONEY, so nothing downstream could catch
    # it. The user has had to correct this reading three times.
    import pause_menu as _pm
    for _attempt in range(1, 4):
        press("toggle_pause")
        wait_for_screen_to_settle(max_wait=8.0)   # let the menu animate in
        if _pm.is_pause_screen(_fast_grab()):
            # WHICH ATTEMPT LANDED IS THE SIGNAL. A silent retry loop reports
            # a clean read whether the toggle worked first time or third, so
            # a toggle that is degrading toward never landing is invisible
            # right up until the run dies on the RuntimeError below.
            print(f"  [balance] pause menu confirmed open on attempt "
                  f"{_attempt} of 3")
            break
        print(f"  [balance] attempt {_attempt} of 3: toggle_pause did NOT "
              f"leave a pause menu on screen — retrying. Do not read this as "
              f"a slow menu; toggle_pause is a TOGGLE and may have closed one, "
              f"and reading money off a WORLD frame is how the health coin got "
              f"reported as the wallet ($246 -> $100).")
    else:
        raise RuntimeError(
            "the pause menu would not open, so there is nowhere to read the "
            "money from — refusing to read a number off the world, where the "
            "only counter is the HEALTH coin and any answer would be wrong")

    def _close_pause_menu():
        """Shut the menu, and SAY SO if it did not shut.

        In a helper because it now has to run on EVERY exit, including the raising
        one. It used to sit only after the paid call, so any exception from that
        call -- PaidModelDisabled being the certain one now -- skipped it and left
        the game PAUSED. run_cycles hits this once per cycle and swallows the
        exception, so every cycle walked 76 s to the table and then parked the
        console in a paused menu. The symptom looks like dead input; it is neither.
        """
        press("toggle_pause")
        wait_for_screen_to_settle(max_wait=6.0)  # let the menu animate closed

    # LOCAL FIRST. pause_menu.read_money is measured on BOTH capture geometries,
    # refuses unless is_pause_screen agrees, and requires two OCR scales to agree
    # before answering -- and it had ZERO production callers. Both sites that wanted
    # a balance called THIS function, which is a paid call; with the paid model off it
    # raises, run_cycles swallows the exception and returns its hardcoded
    # RESET_BALANCE_FALLBACK of 246 every cycle. So the only thing able to reconcile
    # the tracked balance against the game was a constant, while reloads keep putting
    # $246 back in the wallet and the tracked figure only ever marches down.
    # A measurement built, tested, and never wired (10.1).
    _local_money = None
    try:
        _frame = _fast_grab()
        # THE BAN SCREEN IS A NOTEBOOK PAGE TOO, and is_pause_screen cannot tell the
        # two books apart. Censused 2026-09-13 over 10,239 frames:
        #
        #     PAUSE book   n=  14   0.9263 .. 0.9446
        #     BAN book     n=1140   0.7101 .. 0.8587      <- 1,122 clear PAGE_MIN_FRAC 0.80
        #     everything else       0.0000 .. 0.9272 (a bright wall)
        #
        # MENU_TEXT_MIN_FRAC cannot rescue it -- ban 0.1224-0.4148 against pause
        # 0.0733-0.4309 is complete overlap, and no threshold on that quantity separates
        # two notebooks (10.4). Over 1,131 ban frames read_money returns a CONFIDENT
        # WRONG balance on 5 ($7 four times, $1 once) with both OCR scales agreeing --
        # which is the "$246 -> $100" failure its own docstring exists to prevent,
        # reached THROUGH the guard. It was harmless while read_money had no callers;
        # wiring it in an hour ago is what made it live.
        #
        # The ban counter is the instrument that already separates them, measured rather
        # than invented: 0 false positives off ban screens over 3,000 random frames, and
        # a confident answer on 313 of 317 ban frames. No new constant.
        _banned = read_ban_counter(_frame)
        if _banned is not None:
            print(f"  [balance] this is a BAN screen (counter reads {_banned}), not the "
                  "pause book — refusing to read money off it. Both are notebook pages "
                  "and is_pause_screen cannot tell them apart.")
            _close_pause_menu()
            raise RuntimeError(
                "refusing to read the wallet off a ban screen — the page-brightness "
                "guard admits it, and a confident wrong balance is worse than none")
        # RETRY, for the same reason _verify_bans retries the ban counter: "one
        # unlucky frame (mid-animation) returned None and the whole check failed".
        # Measured live 2026-09-13 right after a Load Last Save -- the settle gate
        # reported the regions still moving at 6.0 s, read_money correctly refused
        # (its two OCR scales disagreed), and the single-shot path then fell through
        # to the paid call and raised. The reader was right; asking once was wrong.
        for _try in range(MONEY_READ_TRIES):
            _local_money = _pm.read_money(_frame)
            if _local_money is not None:
                break
            if _try + 1 < MONEY_READ_TRIES:
                time.sleep(0.6)
                _frame = _fast_grab()
    except RuntimeError:
        raise
    except Exception as _e:
        print(f"  [balance] the local reader raised ({_e!r}) — falling through")
    if _local_money is not None:
        print(f"  [balance] read LOCALLY from the pause menu: ${_local_money} "
              "(no paid call)")
        _close_pause_menu()
        return _local_money

    # THE CLOSE MUST RUN EVEN WHEN THIS RAISES, which with the paid model off it
    # certainly does. Without the finally, PaidModelDisabled skipped the close and
    # left the game paused for the rest of the run.
    try:
        img_b64 = capture_screenshot_b64()
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,   # thinking disabled below
            thinking={"type": "disabled"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": SCREENSHOT_MEDIA_TYPE,
                                                 "data": img_b64}},
                    {"type": "text", "text": READ_BALANCE_PROMPT},
                ],
            }],
        )
        text = "".join(block.text for block in response.content
                       if block.type == "text").strip()
        result = extract_json(text)
    finally:
        _close_pause_menu()
    # THE CLOSE IS A TOGGLE TOO, and nothing checked it. The open is verified
    # three times over; the close was fire-and-forget. If it drops, the game
    # stays PAUSED and every press after this lands in a menu instead of the
    # world — which surfaces minutes later as "no input is reaching the game",
    # a diagnosis that has already been raised twice at a healthy stream with
    # working input. This only warns: re-pressing a toggle that DID land would
    # reopen the menu, which is the trap that costs more than it fixes.
    try:
        if _pm.is_pause_screen(_fast_grab()):
            print("  WARNING: [balance] the closing toggle_pause did NOT land "
                  "— THE PAUSE MENU IS STILL OPEN. The balance above is good, "
                  "but everything after this is pressing buttons into a menu. "
                  "Expect the symptom to look like dead input or a frozen "
                  "stream; it is neither.")
    except Exception as _e:
        print(f"  [balance] could not verify the pause menu closed ({_e!r}) — "
              f"so 'the menu is closed' is an ASSUMPTION from here on, not an "
              f"observation.")

    # The stack is the proof it read the right thing. A lone number could have
    # come from anywhere on screen — which is exactly how the health coin got
    # reported as the wallet.
    counters = result.get("counters")
    money = result.get("money")
    if isinstance(counters, list) and len(counters) == 3 and counters[0] is not None:
        money = counters[0]
    elif money is not None:
        raise RuntimeError(
            f"vision returned money={money!r} without the three right-edge "
            f"counters (got {counters!r}) — it did not find the currency stack, "
            f"so the number came from somewhere else on screen. The health coin "
            f"reads 100 and has been mistaken for the wallet before.")
    if money is None:
        raise RuntimeError(
            "Couldn't find a money total on the pause menu screen — "
            "check that Options actually opens a menu showing it, and "
            "adjust toggle_pause or READ_BALANCE_PROMPT if not."
        )
    return money


def hand_to_cards(hand: list):
    """Split the raw hand JSON into indexed (player, tactics) card lists,
    keeping each card's hand_index for input targeting."""
    players, tactics = [], []
    for c in hand:
        if c["kind"] == "player":
            players.append((c["hand_index"], PlayerCard(c["name"], c["power"], c["secondary"])))
        else:
            tactics.append((c["hand_index"], TacticsCard(c["name"], TacticsType(c["type"]), c["bonus"])))
    return players, tactics


def hand_cursor_look():
    """(cursor_index or None, y per card, row count) from ONE fresh frame.

    The seam select_and_play() presses against. It is injected rather than
    imported so the offline suite can drive the loop with a fake screen -- and
    so input_controller, which orchestrator imports, never has to import back.
    """
    import local_hand
    hand = _grab_settle_regions(("hand",))["hand"]
    _idx, glow, rows = local_hand.cursor_glow(hand)
    selected = local_hand.selected_cards(rows, hand.width / local_hand.ANCHOR_W)
    # THE WHOLE PROFILE, not one answer. A SELECTED card keeps glowing, so once anything
    # is selected the brightest card is no longer necessarily the cursor -- the caller
    # needs every reading plus which cards are lifted to tell them apart.
    # None where the position was never measured, so the lift check ABSTAINS rather
    # than comparing a slot constant against itself and reporting "nothing moved".
    return (glow,
            [None if r.get("y_measured") is False else r.get("y") for r in rows],
            len(rows), selected)


def play_one_turn(state_json: dict, batters_used: int):
    """
    Execute one turn. `batters_used` is the caller-tracked count of
    batters/pitchers already played this half (0-4), passed in rather
    than trusted from state_json["batters_used"] — the on-screen
    indicator for that is unreliable to read via vision (it comes back
    null almost every time), which silently broke the "last batter of
    the half, be aggressive" heuristic since `None == 4` is always False.

    Returns (played, matchup_info):
      - played: True if a normal play was made, False if the redraw
        (discard) branch was taken instead.

        N27: `played=False` means "took the discard branch" — it does NOT
        mean "no turn was consumed". An earlier version of this docstring
        claimed a redraw "doesn't use up a turn"; that contradicts
        input_controller.select_and_discard(), which ends in
        confirm_play() and whose own comment records that being confirmed
        live. So `turns_this_half` undercounts on redraw turns. That is
        inert today because no decision function reads batters_used, but
        it would be a live bug if that heuristic is ever re-enabled —
        see HEURISTICS.md §5.
      - matchup_info: dict describing what we played, for match_log.jsonl
        (None on a discard — we don't know the replacement card's stats
        without an extra vision read, so those turns aren't logged).
    """
    players, tactics = hand_to_cards(state_json["hand"])
    runners = [PlayerCard(r["name"], r["power"], r["secondary"]) for r in state_json["runners"]]

    # Default to 0 (not 2) when the discard counter can't be read, so a
    # misread never causes more discards than the game actually allows.
    discards_left = state_json.get("discards_left")
    if discards_left is None:
        # The out-of-range clamp two functions away announces itself; this one
        # did not, and it has the same consequence: should_redraw() can never
        # fire, so a weak hand is played instead of improved, for $50, and the
        # log shows only that no discard happened — indistinguishable from a
        # hand that did not need one.
        print("  [repair] discards_left unreadable — treating as 0, so no "
              "discard is possible this turn.")
        discards_left = 0

    state = GameState(
        half=state_json["phase"],
        batters_used=batters_used,
        your_score=state_json["your_score"],
        opp_score=state_json["opp_score"],
        target_score=state_json["your_score"] if state_json["phase"] == "pitching" else None,
        runners=runners,
        redraws_left=discards_left,
    )

    player_only = [p for _, p in players]
    tactics_only = [t for _, t in tactics]

    if state_json["phase"] == "batting":
        decision = best_batting_play(player_only, tactics_only, state)
    else:
        decision = best_pitching_play(player_only, tactics_only, state)

    if should_redraw(player_only, state):
        # Discard the WEAKEST card, not the one we would have played.
        #
        # This used to discard `decision.player_card` — the engine's own BEST
        # card. That was harmless while the threshold was 4: the rule only
        # fired when every card was <= 4, and the weakest card in the pool is
        # a 4, so the replacement always became the new best regardless of
        # which card was thrown. Measured over 200k qualifying hands: a 100%
        # tie at threshold 4.
        #
        # At the new threshold of 6 it is no longer harmless — discarding the
        # worst CHANGES the outcome in 17.0% of qualifying hands (5.9% of all
        # hands dealt) and is worse in none. The two rules pick a different
        # card 53.9% of the time, but usually to no effect — the fresh draw
        # becomes the best either way — so 54% counts disagreements, not wins.
        # Measured over 200k hands. Keeping
        # the old best as a floor makes the new best max(old_best, draw)
        # instead of max(second_best, draw).
        _weakest = min(players, key=lambda ip: ip[1].power)
        player_idx = _weakest[0]
        print(f"Decision: best card is weak (power {decision.player_card.power}) and "
              f"{state.redraws_left} discard(s) left — discarding the weakest "
              f"(power {_weakest[1].power}) instead of playing")
        # The card is SPENT. Forget it, so nothing carries its value forward into the
        # replacement -- the only way the hand memory can be wrong is if we let it.
        # CLOSED LOOP, exactly like the play site below -- and this one was missed. For
        # the whole life of the verified loop this call passed no `look=` and dropped its
        # return value, so the DISCARD ran the blind counted-press path that the play path
        # was rebuilt to replace. A discard is the IRREVERSIBLE one: select_and_discard's
        # own docstring records it landing on the wrong card live (2026-08-28, the engine
        # chose a power-4 player and a tactics card was thrown), and confirm_discard is
        # followed by the game auto-lifting the replacement, which confirm_play commits as
        # this turn's play -- so an unverified discard spends the turn on a card nobody
        # chose. Found by the QA sweep 2026-09-11, months after the play path was fixed.
        #
        # `is False` and not falsiness, for the play site's reason: a stub, or a caller
        # that simply forgets to return, must never read as "nothing was committed".
        #
        # KEEP forget_hand_slot IMMEDIATELY BEFORE THE SPEND -- test_hand_memory_forgets
        # requires a forget within six lines above it, so prose goes here, never between.
        forget_hand_slot(player_idx)
        if select_and_discard(player_idx, look=hand_cursor_look) is False:
            print("  discard REFUSED — the card could not be verified; nothing thrown")
        return False, None
    else:
        # THE FALSE BRANCH, LOGGED. The true branch has always announced
        # itself and its numbers; this one wrote nothing, so "no discard this
        # turn" covered two different decisions — the hand was strong enough,
        # or there were no discards left to spend — and the VALUE that decided
        # it was never recorded at all. CLAUDE.md §10.4: a threshold has to sit
        # between two MEASURED populations, and this one's populations do not
        # exist on disk because nothing ever wrote the max power down. Every
        # such turn happens inside a $50 match, so the samples are expensive.
        _best = max((p.power for p in player_only), default=None)
        _why = ("NO DISCARDS LEFT — this hand was not kept on merit"
                if state.redraws_left <= 0 else "hand is strong enough")
        print(f"  [redraw] keeping the hand: best power {_best} vs threshold "
              f"{REDRAW_POWER_THRESHOLD}, {state.redraws_left} discard(s) "
              f"left — {_why}")

    print(f"Decision: {decision.reasoning}")

    player_idx = next(i for i, p in players if p is decision.player_card)
    tactics_idx = None
    if decision.tactics_card:
        tactics_idx = next(i for i, t in tactics if t is decision.tactics_card)

    # THE REVEAL CLOCK STARTS ONE LINE BEFORE THE COMMIT, not after
    # play_one_turn returns. Everything after this press belongs to THIS
    # turn's reveal; an episode already under way when it is taken belongs to
    # the turn before, and reveal_frame_for() refuses that on `t_first >=
    # t_mark` alone. Taken BEFORE the press rather than after, so no part of
    # the flip can land in the gap between the two.
    _reveal_mark = reveal_mark()
    # THE HAND AS IT IS AT THE PLAY, for the deal gate that run() reaches further down.
    # Taken here, beside the reveal mark and before the press, because the replacement
    # card can land while the reveal is being read and a baseline captured after that is
    # already post-deal. It crosses functions the way graph_walk carries a leg-end frame:
    # a module stash that the consumer POPS, so a turn can never inherit the last one.
    stash_hand_baseline(_grab_settle_regions(("hand",))["hand"])
    # THE DIAMOND AS IT IS AT THE PLAY -- who is on, and how fast. Extracted so it can
    # actually be EXERCISED: the first version was inline, referenced an unimported
    # local_state, raised NameError into its own except on every turn, and was covered by a
    # test that only AST-checked the call was WRITTEN. A diagnostic nothing can run is
    # worse than none, because it looks like data collection (2026-09-13, found by QA).
    capture_diamond_at_play(decision, state_json)
    # CLOSED LOOP, not a press count. `hand_cursor_look` reads the cursor off the screen
    # after every single press; select_and_play refuses rather than commit a card it
    # could not verify. A refusal is NOT a play -- the turn returns played=False and
    # run() re-reads and tries again.
    #
    # THE GUARD IS `is False`, NOT FALSINESS. select_and_play returned None on success
    # for its whole life, so treating any falsy value as a refusal turns every stub --
    # and any caller that simply forgets to return -- into a phantom "nothing was
    # committed". It broke three test files the moment it landed, which was the cheap
    # version of the same mistake happening live.
    #
    # KEEP forget_hand_slot IMMEDIATELY BEFORE THE SPEND: test_hand_memory_forgets
    # asserts they stay within a few lines of each other, so prose goes above them,
    # never between them.
    #
    # Both slots are SPENT (the tactics one too, when one was attached).
    forget_hand_slot(player_idx, tactics_idx)
    if select_and_play(player_idx, tactics_idx, look=hand_cursor_look) is False:
        print("  play REFUSED — the selection could not be verified; nothing committed")
        pop_hand_baseline()
        return False, None

    matchup_info = {
        # POPPED by run() before this dict can reach pending_matchup, so
        # match_log.jsonl is unaffected by patch60. It is a clock reading, not
        # a measurement of the turn, and it has no business in the dataset.
        "reveal_mark": _reveal_mark,
        "phase": state_json["phase"],
        "our_card_name": decision.player_card.name,
        "our_power": decision.player_card.power,
        "our_secondary": decision.player_card.secondary,
        "our_tactics_bonus": decision.tactics_card.bonus if decision.tactics_card else 0,
        # The TYPE, not just the bonus. power_bonus() (simulate.py:97) only
        # counts SWING_BOOST/PITCH_BOOST toward power — a speed or fielding
        # tactic has a nonzero bonus that adds NO power. Logging the bonus
        # alone left effective power uncomputable on 20 of 39 logged rows,
        # which is most of the signal this log exists to measure.
        "our_tactics_kind": decision.tactics_card.kind.value if decision.tactics_card else None,
        "runners_before": len(runners),
        "score_before": state_json["your_score"] if state_json["phase"] == "batting" else state_json["opp_score"],
    }
    return True, matchup_info


def run(target_wins: int, starting_balance: int = None, progress_file: str = PROGRESS_FILE,
        max_spend: int = None, log_screenshots: bool = False, compare_local_reads: bool = False):
    """
    Play matches until target_wins wins are logged (across all runs), or
    money runs out.

    compare_local_reads=True prints local OCR/hand-matcher results next
    to vision's on every turn (see log_local_read_comparison()) — never
    affects any real decision, diagnostic only, off by default. Pulls
    in the PaddleOCR reader (hand_digit_reader.py), which runs in its own venv.

    log_screenshots=True starts the background screenshot logger (10Hz)
    (see its own comment block above run()) — diagnostic only, off by
    default, doesn't affect play.

    On the very first run (no progress_file yet), the starting balance is
    read automatically from the pause menu unless starting_balance is
    explicitly passed in, in which case that value is used instead and
    the pause-menu read is skipped. After that first run, the persisted
    balance is always authoritative. If you top up your in-game funds
    manually outside the script, edit the "balance" value in
    progress_file to match, since the script has no way to see that on
    its own.

    progress_file lets different save files (yours vs. someone else's,
    e.g. Taylere's, 2026-08-23) track wins/losses/balance independently
    instead of mixing into the same trophy progress — pass a different
    path per person/save.

    max_spend caps how much this run will spend on matches this session
    (e.g. Taylere's real balance is $496, but she only wants $250 of it
    used) — independent of the real in-game balance, which keeps getting
    tracked accurately either way.
    """
    begin_cycle_state()   # this run's FIRST state read is the paid orientation one
    if compare_local_reads:
        # C4: verify the PaddleOCR venv ONCE, loudly, at startup. Otherwise a
        # stale/missing interpreter surfaces as a swallowed per-turn exception
        # that reads like an OCR failure rather than a setup problem.
        from hand_digit_reader import check_paddle_venv
        check_paddle_venv()

    screenshot_stop = None

    (wins, losses, draws, balance, match_in_progress,
     bans_done_this_match) = load_progress(progress_file)
    if balance is None:
        if starting_balance is not None:
            balance = starting_balance
        else:
            print("No saved balance yet — opening the pause menu to read your current money...")
            balance = read_balance_from_pause_menu()
            print(f"Read ${balance} from the pause menu.")
        save_progress(wins, losses, draws, balance, progress_file,
                      match_in_progress=match_in_progress,
                      bans_done_this_match=bans_done_this_match)

    spent = 0
    stuck_count = 0
    turns_this_half = 0
    last_phase = None
    pending_matchup = None  # set right after a logged play; consumed once the outcome is visible
    pending_read_failures = 0  # consecutive failed reads while a matchup waits
    _local_check_turn = 0      # drives LOCAL_CHECK_EVERY sampling
    # Which screen we last took an irreversible action on (scored a result,
    # debited a match fee, toggled bans). Cleared as soon as a DIFFERENT screen
    # is observed, i.e. the action visibly took effect. Guards C1/C2/C3 — see
    # those branches. Without it, one screen that fails to dismiss gets acted
    # on once per poll forever.
    acted_screen = None
    # "No action needed" bookkeeping: when the current run of motion began (None
    # when the screen is still), and how many polls it has absorbed.
    motion_wait_started = None
    motion_skips = 0
    # Turns where the card we played was not the card we chose. This is the
    # ONLY signal that input is being dropped — everything else about a
    # misfire looks like a normal turn.
    misfires = 0
    plays = 0
    # Plays since the CURRENT match was paid for. `plays` counts the whole
    # session, so it cannot tell a result screen at the start of match 4
    # from one at the end of match 3. See MIN_PLAYS_FOR_RESULT.
    plays_this_match = 0
    unconfirmed_result_reads = 0
    # C5: True from the moment a match fee is debited until a result is scored.
    # Guards the one double-debit path acted_screen cannot see — see the C5
    # block in the match_start_prompt branch.
    # match_in_progress comes from load_progress() above — see QA2-1 there.
    if match_in_progress:
        print("NOTE: a paid match was in progress when this save was last "
              "written. Its result screen will still be scored.")
    # QA1-F3: a bound that no single screen can reset.
    #
    # stuck_count counts CONSECUTIVE repeats of one screen, and every branch
    # zeroes it on success. Two screens that each clear the other's guard
    # therefore spin forever: measured 3000 screens and 1500 ban re-toggles for
    # match_start_prompt <-> ban_screen, with no stall and no diagnostics. That
    # pair is a likely confusion, not exotic — the ban screen carries the same
    # on-screen "PLAY" prompt as the match-start prompt.
    #
    # Before C5 the alternation was bounded by money (each prompt debited until
    # the cap stopped it). Removing the debit removed the bound, turning a money
    # bug into a silent hang. So count polls since anything actually ADVANCED
    # the session — a debit, a scored result, or a played card — and stop on
    # that regardless of which screens are cycling.
    polls_without_progress = 0
    # OVERNIGHT_AUDIT #1: the guard nothing else provides — SCREEN CONTENT
    # UNCHANGED. Every other bound catches "the screen keeps changing in a way
    # that isn't progress"; none catches "the screen never changes at all".
    #
    # On a frozen stream (Chiaki stalled, PS5 asleep) the frame is maximally
    # STILL, so screen_is_moving() says False, read_game_state() returns the
    # same valid turn payload forever, and play_one_turn() returns played=True
    # forever — because select_and_play() is just keystrokes, which return
    # normally whether or not anything is listening. Both liveness counters
    # reset on that "play", so the loop is unbounded. Measured: 500 phantom
    # turns, ~1,500 API calls and ~15,000 keystrokes over a night, ending with
    # the summary "input timing looks safe".
    last_frame_digest = None
    last_frame_change_at = None
    # QA1-F3: bans happen ONCE per match. The C3 guard only blocks CONSECUTIVE
    # ban screens, so a ban_screen <-> anything alternation re-submits every
    # time — measured 400 submissions, each toggling 3 cards on and off. Tie it
    # to the match lifecycle instead of to screen adjacency.
    # bans_done_this_match comes from load_progress() above, alongside
    # match_in_progress. Persisting one without the other was its own bug: a
    # crash AFTER the bans were placed left match_in_progress True but
    # bans_done_this_match False, so the rerun re-entered the ban branch and
    # TOGGLED THE SAME THREE CARDS BACK OFF — stranding a match already paid
    # for, with its bans undone.
    # None means "stopped cleanly" (target reached, out of money, spend cap).
    # Any string is a stall worth dumping a diagnostic bundle for.
    stop_reason = None
    # Fresh buffers per run. Both are module-level so the helpers can stay
    # simple, which means a second run() in the same process would otherwise
    # dump the PREVIOUS run's trail and latency stats alongside its own.
    _OBSERVATIONS.clear()
    _SETTLE_STATS.clear()
    print(f"Resuming with {wins} wins / {losses} losses / {draws} draws logged, ${balance} on hand. "
          f"Target: {target_wins} wins total.")

    # N5: the screenshot logger runs on a daemon thread and the loop can
    # exit through many paths (break, exception, target reached). Stop it in
    # a finally so it cannot outlive the run — the previous version only
    # set the event on the two normal exits.
    try:
        # THE REVEAL WATCHER runs for the length of the match loop and is
        # stopped in the finally below, for the same reason as the screenshot
        # logger: the loop exits through many paths, and a daemon thread that
        # outlives its run keeps reading the dump for the rest of the process.
        # Never fatal -- start_reveal_watcher() returns None when it cannot
        # run, and every turn then falls back to wait_for_reveal_cards().
        start_reveal_watcher()
        if log_screenshots:
            # Started INSIDE the try so the finally always reaches it. I9: the
            # handle is kept (it used to be discarded, leaving no way to stop
            # the logger mid-run).
            screenshot_stop = start_screenshot_logger()

        while wins < target_wins:
            # NO ACTION NEEDED: if something is animating, the right move is to
            # do nothing and look again. Costs ~0.2s locally instead of a vision
            # call on a frame that was never going to read cleanly.
            #
            # Safety shape matters here: this gate can only ever cause the loop
            # to SKIP, never to act. A false "moving" costs one 0.2s poll; a
            # false "still" just falls through to the same read + validate path
            # as before, so it is no worse than the previous behaviour.
            # QA1-F9: guarded like every other per-iteration call. _fast_grab()
            # calls _MSS.grab(), whose real failure modes on this machine are
            # display reconfiguration, revoked screen-recording permission, and
            # an mss handle invalidated over a long session. Unguarded, one
            # raise killed the run mid-match with stop_reason None, so no
            # diagnostics bundle was written either. A motion check that cannot
            # answer should fall through to the normal read, not end the session.
            try:
                _moving = screen_is_moving()
            except Exception as e:
                print(f"  [motion] check failed ({e}) — reading anyway.")
                _moving = False
            if _moving:
                now = time.time()
                if motion_wait_started is None:
                    motion_wait_started = now
                waited = now - motion_wait_started
                if waited < MAX_CONTINUOUS_MOTION_WAIT:
                    motion_skips += 1
                    continue
                # Bounded: something is animating permanently. Read anyway and
                # let the normal stuck path handle it, rather than stalling.
                print(f"  [motion] still animating after {waited:.0f}s — reading anyway.")
                motion_wait_started = None
            else:
                motion_wait_started = None

            try:
                state_json = read_state_for_turn()
            except Exception as e:
                stuck_count += 1
                record_observation(screen="<read failed>", error=str(e)[:200],
                                   stuck=stuck_count, motion_skips=motion_skips)
                print(f"Couldn't read the screen ({e}), retrying... ({stuck_count}/{MAX_STUCK_ATTEMPTS})")
                # A pending matchup can't be reliably scored against whatever
                # state shows up after a retry — it may span more than one
                # turn by then. Drop it rather than silently mislabeling a
                # row in match_log.jsonl (caught in QA, 2026-08-23).
                #
                # That reasoning is right but the bound was zero, and zero was
                # far too tight. Measured over the 2026-08-26 run: 22 plays
                # were followed by a failed read, 19 of them by exactly ONE
                # failed poll and none by more than two — the loop re-reading
                # while the next hand deals, the same turn throughout. This
                # single line discarded 22 of 29 plays, roughly 76% of the
                # run's intended rows, to prevent a mislabel that needs a gap
                # long enough for the opponent to act. So: survive a brief
                # stumble, still drop on a real one.
                pending_read_failures += 1
                if pending_read_failures > MAX_PENDING_READ_FAILURES:
                    if pending_matchup is not None:
                        # Say which row died. This was the only drop path in the
                        # whole turn loop with no voice at all: a reconstruction
                        # of one full run found 22 plays reaching pending_matchup
                        # and 20 rows written, and the 2 that vanished left not
                        # one character of output to find them by.
                        print(f"  [reveal] {pending_read_failures} consecutive "
                              f"unreadable screens — dropping the pending row "
                              f"for our_power "
                              f"{pending_matchup.get('our_power')}.")
                    pending_matchup = None
                if stuck_count >= MAX_STUCK_ATTEMPTS:
                    print("Stuck too long on unreadable screens — stopping. Check the game manually.")
                    stop_reason = "unreadable_screens"
                    break
                time.sleep(2)
                continue

            pending_read_failures = 0   # the read succeeded; the streak ends

            # SAMPLED, not every turn. Measured 2026-08-26: the hand half of
            # this comparison costs 25.57s per turn (vs 0.33s for all three
            # base crops) because hand_digit_reader spawns a fresh Python and
            # reloads the PaddleOCR models on every call. That was roughly a
            # third of an 80s turn, spent entirely on a diagnostic that drives
            # no decision. Sampling keeps the audit signal — the point is to
            # catch systematic drift between the local and vision readers, and
            # that shows up just as well in every Nth turn — at 1/N the cost.
            # The real fix is a persistent worker; this is the cheap version.
            if compare_local_reads:
                _local_check_turn += 1
            # (n-1) % N, not n % N: the latter is never 1 when N == 1, so
            # setting LOCAL_CHECK_EVERY = 1 to get EVERY turn silently
            # disabled the comparison entirely (QA, 2026-08-26).
            if compare_local_reads and (_local_check_turn - 1) % LOCAL_CHECK_EVERY == 0:
                try:
                    log_local_read_comparison(state_json)
                except Exception as e:
                    print(f"  [local-check] comparison failed ({e}) — skipping, real loop unaffected.")

            if pending_matchup is not None:
                # Matchup logging is diagnostic-only (see the removal-plan
                # comment on MATCH_LOG_FILE) — a failure here (e.g. a disk
                # error on log_matchup's write) must never crash the real
                # automated loop over real match money (caught in QA, 2026-08-23).
                try:
                    score_field = "your_score" if pending_matchup["phase"] == "batting" else "opp_score"
                    new_score = state_json.get(score_field)
                    new_runners = state_json.get("runners") or []
                    if new_score is not None:
                        runs = new_score - pending_matchup["score_before"]
                        margin = reveal_margin(pending_matchup)
                        outcome, basis = classify_outcome(
                            margin, runs, pending_matchup["runners_before"],
                            len(new_runners))
                        log_matchup({**pending_matchup, "outcome": outcome,
                                     "runs_scored": runs, "margin": margin,
                                     "outcome_basis": basis})
                    else:
                        # No `else` here until 2026-09-01. A follow-up read that
                        # comes back without a score cannot have its outcome
                        # derived, so the row was dropped and the pending state
                        # cleared in silence — the turn simply never appeared.
                        print(f"  [reveal] outcome unscorable: {score_field} "
                              f"missing from the follow-up read; dropping the "
                              f"pending row for our_power "
                              f"{pending_matchup.get('our_power')}.")
                except Exception as e:
                    print(f"Matchup logging failed ({e}) — skipping this row, continuing the real loop.")
                pending_matchup = None

            # Frame-identity check. Cheap: one already-captured region, hashed.
            try:
                _crop = _grab_settle_regions(("hand",))["hand"]
                _digest = hashlib.blake2b(_crop.tobytes(), digest_size=16).digest()
                _now = time.time()
                if _digest != last_frame_digest:
                    last_frame_digest = _digest
                    last_frame_change_at = _now
                elif last_frame_change_at is None:
                    last_frame_change_at = _now
                _frozen_for = _now - (last_frame_change_at or _now)
            except Exception:
                last_frame_change_at = None
                _frozen_for = 0.0
            if _frozen_for >= FROZEN_STREAM_SECONDS:
                # A static screen has TWO very different causes, and stopping is
                # only right for one of them:
                #   * the stream is dead (Chiaki stalled, PS5 asleep) — every
                #     "turn" the loop plays is a phantom, and it must stop;
                #   * the game is legitimately PAUSED — the stream is alive,
                #     someone hit Options, and stopping the run would be a
                #     false alarm that throws away a paid match.
                #
                # Pixels cannot tell those apart: both are byte-identical. The
                # screen's CONTENT can. This costs one vision call, at most once
                # per FROZEN_STREAM_SECONDS, which is affordable precisely
                # because it is the moment we are about to abandon the run.
                _paused = False
                try:
                    _probe = read_game_state()
                    _scr = _probe.get("screen")
                    # A pause/menu overlay is exactly what "other" catches, and
                    # a still frame on it is expected rather than alarming.
                    _paused = _scr == "other"
                    print(f"  [frozen] {_frozen_for:.0f}s of identical frames; "
                          f"probe says screen={_scr!r}.")
                except Exception as e:
                    print(f"  [frozen] {_frozen_for:.0f}s of identical frames "
                          f"and the probe itself failed ({e}) — treating as a "
                          "dead stream.")
                if _paused:
                    # Alive, just not playing. Reset the clock and keep waiting;
                    # the no-progress bound still backstops a genuine stall.
                    last_frame_change_at = time.time()
                    print("  [frozen] looks like a paused/menu screen, not a "
                          "dead stream — waiting rather than stopping.")
                    wait_for_screen_to_settle(max_wait=8.0)
                    continue
                print(f"The screen has been byte-identical for "
                      f"{_frozen_for:.0f}s and does not look paused — the "
                      "stream is frozen (Chiaki stalled, PS5 asleep, or the "
                      "window is gone). Stopping rather than playing phantom "
                      "turns into it.")
                stop_reason = "frozen_stream"
                break

            polls_without_progress += 1
            if polls_without_progress > MAX_POLLS_WITHOUT_PROGRESS:
                print(f"No progress in {polls_without_progress} polls (no debit, "
                      f"no scored result, no card played) — stopping. The loop "
                      "is cycling between screens without advancing.")
                stop_reason = "no_progress"
                break

            screen = state_json.get("screen")

            # A different RECOGNIZED screen means the previous action visibly
            # landed — clear the guard.
            #
            # N2: "other" is the catch-all for anything unrecognized, including a
            # single misread or transition frame. Treating it as a real transition
            # let `result -> other -> result` double-score and
            # `match_start_prompt -> other -> prompt` double-debit $50 — exactly
            # the defect C1/C2 were meant to close. A misread must not re-arm the
            # guard, so "other" leaves it untouched.
            # Feed the rolling buffer the loop dumps on a stall. Cheap, and it
            # is the difference between "stuck on an unrecognized screen" and
            # knowing WHICH screens, in what order, with what hand and score.
            record_observation(
                # Audit signal: does the game's own "I want input" prompt agree
                # with what the vision model called this screen? One session of
                # this decides whether it can replace the motion gate.
                prompt=_safe_prompt_check(),
                screen=screen, phase=state_json.get("phase"),
                your_score=state_json.get("your_score"),
                opp_score=state_json.get("opp_score"),
                hand_size=len(state_json.get("hand") or []),
                runners=len(state_json.get("runners") or []),
                discards_left=state_json.get("discards_left"),
                acted_screen=acted_screen, stuck=stuck_count,
                motion_skips=motion_skips)

            if screen != acted_screen and screen != "other":
                acted_screen = None

            if screen == "result":
                # C1 GUARD: this branch persists win/loss/draw counts, so acting on
                # the same result screen twice permanently corrupts progress.json —
                # potentially past target_wins, ending the run on a fabricated
                # record. A dropped close_result press, or a result overlay that
                # outlives wait_for_screen_to_settle(), makes the very next poll
                # read "result" again. Require an intervening non-result screen
                # before scoring anything. Deliberately does NOT reset stuck_count
                # while suppressed, so a genuinely stuck overlay still trips
                # MAX_STUCK_ATTEMPTS instead of spinning forever.
                if acted_screen == "result":
                    stuck_count += 1
                    print(f"Result screen still up after close_result — not re-scoring "
                          f"(waiting for it to dismiss, {stuck_count}/{MAX_STUCK_ATTEMPTS}).")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Result screen never dismissed — stopping. Check the game manually.")
                        stop_reason = "result_never_dismissed"
                        break
                    press("close_result")
                    wait_for_screen_to_settle(max_wait=8.0)
                    continue
                # N12: everything below indexes a model-produced dict and writes
                # persisted state, with no guard. One malformed result payload
                # would propagate out of run() and end the session, unlike every
                # other read failure.
                #
                # N24: note this DROPS an unscoreable result rather than
                # retrying it — `acted_screen = "result"` is set first, so the
                # next poll's guard suppresses a second attempt. That is the
                # safe direction (double-counting a win is worse than missing
                # one) and double-counting is structurally impossible here
                # because save_progress() is the last statement in the try.
                # QA1-F2: only score a match this process actually PAID FOR.
                # match_in_progress covered debit->result; the result->next-debit
                # half was still on bare acted_screen, which cannot see a repeat
                # with another screen between. Measured: result -> <any misread>
                # -> result scored the SAME match twice, and when the misread was
                # match_start_prompt it also debited $50 — the exact screen
                # confusion observed live at 17:01:46 on 2026-08-25.
                #
                # Scoring only a paid match closes it in one place instead of
                # enumerating misread screens. A result overlay seen when no
                # match is running is, by definition, one already scored.
                if not match_in_progress:
                    stuck_count += 1
                    print(f"Result screen with no paid match in progress — "
                          f"already scored, not counting it again "
                          f"({stuck_count}/{MAX_STUCK_ATTEMPTS}).")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Result screen never cleared — stopping.")
                        stop_reason = "result_never_cleared"
                        break
                    press("close_result")
                    wait_for_screen_to_settle(max_wait=8.0)
                    continue

                # A 0-0 "result" a play or two into a match is a MISREAD, and an
                # expensive one: measured live 2026-08-31, one card played and
                # then "Draw logged", which ended a match that had barely
                # started, burned the $50 already paid for it, and wrote a draw
                # into the record that never happened.
                #
                # The C5 guard above cannot catch this — it only asks whether
                # THIS process paid for a match, and it had. What separates the
                # two is how far in we are: a match is 5 rounds, so a result
                # after fewer than MIN_PLAYS_FOR_RESULT plays is not a finish.
                #
                # Not rejected outright, because a genuine 0-0 result must still
                # be scorable eventually — a screen that keeps saying the same
                # thing across separate polls is evidence, a single frame during
                # a transition overlay is not. So: confirm, then accept.
                # THE `and _scores_all_zero` CLAUSE WAS REMOVED 2026-09-05.
                #
                # It made this guard INERT exactly when it was needed. Mid-match
                # the scoreboard is normally not 0-0, so the clause switched the
                # early-result confirm off for the whole window it was built to
                # cover. One non-zero "result" misread then cleared
                # match_in_progress — the only thing C5 has to go on — and the
                # next overlay misread as match_start_prompt debited a SECOND
                # $50. Reproduced: $100 for one match, a fabricated win in the
                # record, and two `\` keystrokes into a live match, since
                # start_match shares its key with confirm_discard.
                #
                # The 2026-08-31 observation that motivated the clause happened
                # to show 0-0, so 0-0 got written into the condition. Nothing in
                # the reasoning above is about the SCORE — it is about how far
                # into the match we are. An AND that is false in the common case
                # is not a narrower guard, it is an absent one.
                #
                # COST: a genuine finish reached in fewer than
                # MIN_PLAYS_FOR_RESULT plays now waits RESULT_CONFIRM_READS
                # extra polls before scoring. Bounded and accepted.
                if (plays_this_match < MIN_PLAYS_FOR_RESULT
                        and unconfirmed_result_reads < RESULT_CONFIRM_READS):
                    unconfirmed_result_reads += 1
                    print(f"  {state_json.get('your_score')}-"
                          f"{state_json.get('opp_score')} result after only "
                          f"{plays_this_match} play(s) — too early to be a real "
                          f"finish, re-reading "
                          f"({unconfirmed_result_reads}/{RESULT_CONFIRM_READS}).")
                    wait_for_screen_to_settle(max_wait=5.0)
                    continue

                try:
                    acted_screen = "result"
                    stuck_count = 0
                    unconfirmed_result_reads = 0
                    your_score = state_json.get("your_score")
                    opp_score = state_json.get("opp_score")
                    # Prefer the actual score comparison over result_won, since
                    # result_won is only true/false and can't distinguish a draw
                    # (scores tied) from a real loss — both read as false there.
                    # PREFERENCE ORDER, and it is not the obvious one. `result_outcome` is
                    # the LOCAL word reader (WINNER / LOSER / DRAW!), which scores 0 class
                    # errors over 342 held-out result frames from runs that supplied no
                    # template. It goes FIRST because the scoreboard -- which this block used
                    # to prefer -- is measurably unreliable on a result screen: readable on
                    # 12 of 76 draw frames, and wrong on one of those 12. Scores stay ahead
                    # of result_won for the PAID path, which supplies them and never sets
                    # result_outcome, so that path is untouched.
                    local_outcome = state_json.get("result_outcome")
                    if local_outcome in ("win", "loss", "draw"):
                        outcome = local_outcome
                    elif your_score is not None and opp_score is not None:
                        if your_score > opp_score:
                            outcome = "win"
                        elif your_score == opp_score:
                            outcome = "draw"
                        else:
                            outcome = "loss"
                    else:
                        outcome = "win" if state_json.get("result_won") else "loss"

                    if outcome == "win":
                        wins += 1
                        print(f"WIN #{wins} logged. {max(target_wins - wins, 0)} to go.")
                    elif outcome == "draw":
                        draws += 1
                        print(f"Draw logged ({draws} total).")
                    else:
                        losses += 1
                        print(f"Loss logged ({losses} total).")
                    match_in_progress = False   # C5: the paid match is over
                    polls_without_progress = 0  # a scored result is progress
                    save_progress(wins, losses, draws, balance, progress_file,
                      match_in_progress=match_in_progress,
                      bans_done_this_match=bans_done_this_match)
                except Exception as e:
                    stuck_count += 1
                    print(f"Couldn't score the result screen ({e}), retrying... "
                          f"({stuck_count}/{MAX_STUCK_ATTEMPTS})")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Could not score results repeatedly — stopping.")
                        stop_reason = "result_scoring_failed"
                        break
                # Dismiss regardless of whether scoring succeeded — leaving the
                # overlay up would strand the loop on a screen it has already
                # decided not to re-score.
                press("close_result")
                wait_for_screen_to_settle(max_wait=8.0)
                continue

            elif screen == "match_start_prompt":
                # C2 GUARD: same defect as C1 but it debits $50 from the tracked
                # balance and the max_spend cap. Drift here defeats the spend cap,
                # which exists specifically to honour a lower limit than the real
                # in-game balance. Require an intervening screen before debiting.
                if acted_screen == "match_start_prompt":
                    stuck_count += 1
                    print(f"Match-start prompt still up after start_match — not re-debiting "
                          f"({stuck_count}/{MAX_STUCK_ATTEMPTS}).")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Match never started — stopping. Check the game manually.")
                        stop_reason = "match_never_started"
                        break
                    # QA1-F1: this recovery press is for a prompt that GENUINELY
                    # failed to start a match. If a paid match is already
                    # running, the prompt is a misread (a ROUND/transition
                    # overlay), and pressing start_match 14 more times sends
                    # real keystrokes into a live match — the key is `\`, the
                    # same one as confirm_discard. C5 refused the debit and then
                    # this pressed anyway: tracked balance -$50, up to $750 of
                    # untracked in-game spend, max_spend bypassed entirely.
                    if match_in_progress and not _dealer_prompt_on_screen():
                        print("  [C5] ...and a paid match is running, so NOT "
                              "pressing start_match either — just waiting.")
                        wait_for_screen_to_settle(max_wait=8.0, regions="match_start")
                        continue
                    if match_in_progress:
                        # ...UNLESS THE DEALER PROMPT IS ON SCREEN. The guard above
                        # exists because a match_start_prompt read DURING a live
                        # match is a misread of a ROUND transition overlay, and
                        # pressing there fires `\` into the match. But the world
                        # HUD — compass strip, quest list — is never drawn over a
                        # match, so reading it is positive proof no match is
                        # running and this really is the dealer prompt.
                        #
                        # 2026-09-01: one dropped start_match press left the run
                        # standing at the table watching "Baseball Cards [] Play
                        # ($50)" for all 15 polls, refusing to press again, then
                        # stopping. NO RE-DEBIT happens here; only the keystroke
                        # is retried, so the accounting is untouched either way.
                        print("  [C5] ...but the dealer's \"Play ($50)\" prompt is "
                              "on screen, so no match is actually running — "
                              "retrying the press without re-debiting.")
                    reset_hand_memory()  # a new match is a new hand; nothing carries over
                    press("start_match")
                    wait_for_screen_to_settle(max_wait=8.0, regions="match_start")
                    continue
                # C5: DO NOT PAY TWICE FOR ONE MATCH.
                # The acted_screen guard above only blocks a match_start_prompt
                # seen back-to-back. It does nothing when another screen falls
                # between two of them — and one always does: the ban screen.
                #
                # Observed live 2026-08-25 on the throwaway save. Paid $50 at
                # 16:58, scanned and applied 3/3 bans by 17:01:40, the match
                # began, and the "ROUND 1" transition overlay at 17:01:46 was
                # classified as match_start_prompt. acted_screen was
                # "ban_screen" by then, so the guard had already cleared and
                # this branch was about to debit a SECOND $50 for a match
                # already paid for and already running. Only a max_spend=50 cap
                # stopped it, by luck rather than design.
                #
                # A paid match stays paid until a result is scored, so track
                # that directly instead of inferring it from screen order.
                if match_in_progress:
                    print("  [C5] match_start_prompt while a paid match is "
                          "already running (likely a ROUND/transition overlay "
                          "misread) — NOT debiting again.")
                    acted_screen = "match_start_prompt"
                    # QA1-F3: deliberately NOT resetting stuck_count. This
                    # branch takes no action, so it is not progress. Resetting
                    # here let match_start_prompt <-> ban_screen alternate
                    # forever (measured: 3000 screens, 1500 ban re-toggles, no
                    # stall, no diagnostics) because each screen cleared the
                    # other's guard. A money bug became a silent hang.
                    stuck_count += 1
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Repeated match-start prompts during a paid match "
                              "— stopping. Check the game manually.")
                        stop_reason = "match_start_prompt_during_match"
                        break
                    wait_for_screen_to_settle(max_wait=8.0, regions="match_start")
                    continue

                acted_screen = "match_start_prompt"
                stuck_count = 0
                if balance < 50:
                    print(f"Only ${balance} left — can't afford the next $50 match. Stopping.")
                    break
                if max_spend is not None and spent + 50 > max_spend:
                    print(f"Spend cap reached (${spent}/${max_spend} spent this session) — stopping.")
                    break
                balance -= 50
                spent += 50
                match_in_progress = True
                plays_this_match = 0
                unconfirmed_result_reads = 0
                bans_done_this_match = False   # new match, bans are due again
                # QA-L5: reset the half-tracking too. turns_this_half only
                # resets when `phase` CHANGES, and last_phase persists across
                # matches — so a new match opening on the same phase as the
                # previous one ended carried the old count in, and match 2's
                # first batter was reported as batter 2. Inert while no
                # decision function reads batters_used, but it is passed into
                # GameState on every turn and HEURISTICS.md §5 contemplates
                # re-enabling that heuristic.
                turns_this_half = 0
                last_phase = None
                polls_without_progress = 0  # a debit is progress
                save_progress(wins, losses, draws, balance, progress_file,
                      match_in_progress=match_in_progress,
                      bans_done_this_match=bans_done_this_match)
                print(f"Starting next match. ${balance} left"
                      + (f", ${spent}/${max_spend} of session cap spent." if max_spend is not None else "."))
                reset_hand_memory()  # a new match is a new hand; nothing carries over
                press("start_match")
                wait_for_screen_to_settle(max_wait=8.0, regions="match_start")
                continue

            elif screen == "ban_screen":
                # QA1-F3: bans are once per match. Re-entering this branch after
                # they are placed re-reads the cached collection and TOGGLES the
                # same three cards off again.
                if bans_done_this_match:
                    stuck_count += 1
                    print(f"Ban screen again after bans were already placed this "
                          f"match — not re-toggling ({stuck_count}/{MAX_STUCK_ATTEMPTS}).")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Ban screen never cleared — stopping.")
                        stop_reason = "ban_screen_stuck"
                        break
                    # ADVANCE IT RATHER THAN WAIT IT OUT. The ban screen shows
                    # "PLAY" against the TRIANGLE glyph, and triangle is not a
                    # toggle — it commits whatever is banned and starts the
                    # match. The no-recovery-press rule directly above is about
                    # re-pressing the BAN button, which would un-ban what was
                    # just banned; it does not apply here.
                    #
                    # 2026-09-01: a match was paid for, one of three bans
                    # landed, the counter read failed so nothing noticed, and
                    # this loop then polled 15 times for a screen that had been
                    # waiting for PLAY the whole time — $50 spent for zero
                    # logged turns. Pressing triangle by hand at that exact
                    # screen started the match immediately.
                    #
                    # Every third poll, so a single dropped press is retried
                    # without hammering a screen that is merely slow.
                    if stuck_count % 3 == 1:
                        print("  [ban] pressing PLAY (triangle) to advance a "
                              "ban screen whose bans are already placed")
                        press("pyramid")
                    wait_for_screen_to_settle(max_wait=8.0, regions="ban")
                    continue
                # C3 GUARD: ban selection is a TOGGLE. If the game stays on the ban
                # screen (dropped confirm, wrong ban count), a second pass re-reads
                # the same cached collection and UN-bans exactly what it just
                # banned, then re-bans it, forever. Count repeats and bail out.
                if acted_screen == "ban_screen":
                    stuck_count += 1
                    print(f"Still on the ban screen after selecting bans — not re-toggling "
                          f"({stuck_count}/{MAX_STUCK_ATTEMPTS}).")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Ban screen never advanced — stopping. Check the game manually.")
                        stop_reason = "ban_screen_never_advanced"
                        break
                    # N11: deliberately NO recovery press here, unlike the result /
                    # match-start guards. Ban selection is a TOGGLE, so a blind
                    # retry would un-ban what was just banned. A ban screen that is
                    # one confirm_play short is therefore a hard stop rather than a
                    # retry — the safe direction, but it does mean any drift in the
                    # double-confirm (see M11 in input_controller) ends the run
                    # instead of self-healing.
                    time.sleep(2)
                    continue
                try:
                    grid = read_full_ban_collection()
                    collection = [card for _, _, card in grid]
                    bans = choose_bans(collection, count=3)
                    # C3 sub-issue: choose_bans() returns sorted(...)[:3] with no
                    # minimum check. Fewer than 3 bans leaves the game on "BANNED
                    # CARDS n/3" and it refuses to start — landing in the loop above.
                    if len(bans) != 3:
                        raise ValueError(f"need exactly 3 bans, got {len(bans)} from "
                                         f"{len(collection)} collection cards")

                    # N1: map the chosen cards back to GRID POSITIONS, matching by
                    # object identity. Name matching is unsafe — a mis-resolved OCR
                    # read can put the same name (indeed the same PlayerCard object)
                    # at two positions, and the old name-based path then toggled
                    # both, banning 4 physical cards for 3 intended bans.
                    banned_positions = set()
                    remaining = list(bans)
                    for row, col, card in grid:
                        for i, b in enumerate(remaining):
                            if card is b:
                                banned_positions.add((row, col))
                                remaining.pop(i)
                                break
                    # N15: distinct POSITIONS is not sufficient on its own. When
                    # a mis-resolved read puts the SAME PlayerCard object at two
                    # grid positions, choose_bans can return [X, X, B] — which
                    # maps to 3 distinct positions and passes a position count
                    # check, while actually banning 2 real cards plus 1 wrong
                    # one. ROSTER_BY_NAME shares objects with KNOWN_BAN_ROSTER,
                    # so duplicate objects are the normal consequence of a
                    # wrong resolution, not an exotic case. Check identity too.
                    if len({id(b) for b in bans}) != 3:
                        raise ValueError(
                            f"bans are not 3 distinct card objects "
                            f"({[b.name for b in bans]}) — a duplicate from a "
                            f"mis-resolved read would ban the wrong physical card")
                    if len(banned_positions) != 3:
                        raise ValueError(
                            f"could not map 3 bans to 3 distinct grid positions "
                            f"(got {sorted(banned_positions)})")
                    print(f"Read {len(grid)} cards. Banning: "
                          f"{sorted(c.name for c in bans)} at {sorted(banned_positions)}")
                    # Read the counter DURING the ban screen, not after. The
                    # old post-confirm read fired once the screen had already
                    # been dismissed, so it reported "not verified" on every
                    # match ever played and could never have done otherwise.
                    _ban_count = {}

                    def _verify_bans():
                        # RETRY. The first version read exactly once and match 1
                        # of the 2026-08-26 afternoon run reported "not
                        # verified" — while the logged frames of that very ban
                        # screen show the counter progressing 0->1->2->3 and
                        # legible throughout. One unlucky frame (mid-animation)
                        # returned None and the whole check failed.
                        #
                        # There is 4.2s of ban screen left at this point
                        # (measured across all three episodes) and a read costs
                        # 0.26s, so several attempts fit comfortably. Stop at
                        # the first readable value; None only if every attempt
                        # fails.
                        for _ in range(BAN_COUNTER_READ_TRIES):
                            placed = read_ban_counter(capture_screenshot_image())
                            if placed is not None:
                                _ban_count["placed"] = placed
                                return
                        _ban_count["placed"] = None

                    # CLOSED-LOOP NEEDS A LIVE SENSOR, AND A DEAD ONE IS NOT A FAILED
                    # NAVIGATION. select_bans_verified refuses to toggle a cell it cannot
                    # see, which is right when the cursor READS and the target is merely
                    # unreachable -- one missing ban beats banning a card nobody chose.
                    # It is the wrong answer when the cursor never reads at ALL: it then
                    # places ZERO bans and a $50 match starts completely unbanned, which is
                    # strictly worse than the dead-reckoned path it replaced. Caught by
                    # tests/minigame/test_run_resume_and_persist.py, where no screen exists
                    # and six ban assertions went from 3 bans to none.
                    #
                    # So ask the sensor BEFORE trusting it. A few tries, because a single
                    # None is routine (mid-scroll, mid-animation) and says nothing.
                    _cursor = None
                    if input_controller.VERIFY_BAN_NAVIGATION:
                        for _try in range(BAN_CURSOR_PROBE_TRIES):
                            _cursor = ban_cursor_absolute()
                            if _cursor is not None:
                                break
                            time.sleep(input_controller.BAN_NAV_SETTLE)

                    if input_controller.VERIFY_BAN_NAVIGATION and _cursor is not None:
                        # NAVIGATE BY LOOKING. The dead-reckoned path presses N times and
                        # toggles, and on one dropped press it bans a card the engine never
                        # chose -- measured head to head on a simulated grid, and seen live
                        # at 2 of 3 with the scrollbar three rows short of its target.
                        # on_blind IS THE WAY BACK. The probe above checks the sensor
                        # BEFORE placement and never during, and one success committed to
                        # this path with no escape: a cursor that answered the probe and
                        # then went blind placed ZERO bans and still pressed confirm_play
                        # -- Triangle, i.e. PLAY -- on a match already debited $50. The
                        # probe moved that failure one look() later; it did not close it.
                        _placed = input_controller.select_bans_verified(
                            grid, banned_positions, look=ban_cursor_absolute,
                            confirm_ban=ban_x_on, before_confirm=_verify_bans,
                            on_blind=lambda: (
                                record_observation(event="ban_nav_blind_midway"),
                                select_bans_and_start_full(
                                    grid, banned_positions,
                                    before_confirm=_verify_bans)))
                        if sorted(_placed) != sorted(banned_positions):
                            missed = sorted(set(banned_positions) - set(_placed))
                            print(f"  [ban] VERIFIED NAVIGATION placed {sorted(_placed)}; "
                                  f"could not place {missed}. Nothing was toggled blind.")
                            record_observation(event="ban_nav_incomplete",
                                               placed=sorted(_placed), missed=missed)
                    else:
                        if input_controller.VERIFY_BAN_NAVIGATION:
                            print(f"  [ban] the ban cursor could not be read in "
                                  f"{BAN_CURSOR_PROBE_TRIES} tries — falling back to the "
                                  "DEAD-RECKONED path. Its bans are unverified, and that "
                                  "is still better than starting a paid match with none.")
                            record_observation(event="ban_nav_sensor_blind",
                                               tries=BAN_CURSOR_PROBE_TRIES)
                        select_bans_and_start_full(grid, banned_positions,
                                                   before_confirm=_verify_bans)

                    # VERIFY, don't assume. Measured on the cached frames:
                    # three of five real ban sequences finished at 2/3 and the
                    # match started anyway, two seconds later, with a ban set
                    # the engine never chose. Nothing read the counter, so three
                    # paid matches were played wrong and it was invisible.
                    #
                    # Deliberately does NOT raise: the caller's except-and-retry
                    # would re-enter the ban branch and re-toggle what IS placed.
                    # Report it, record it, and let the run continue — a match
                    # with 2 of 3 bans is degraded, not lost.
                    try:
                        placed = _ban_count.get("placed")
                        if placed is None:
                            print("  [ban] could not read the BANNED CARDS "
                                  "counter — bans NOT verified this match.")
                            record_observation(event="ban_count_unreadable")
                        elif placed < len(banned_positions):
                            print(f"  [ban] WARNING: only {placed} of "
                                  f"{len(banned_positions)} bans registered. The "
                                  "match will start with a ban set the engine "
                                  "did not choose.")
                            record_observation(event="ban_count_short",
                                               placed=placed,
                                               wanted=len(banned_positions))
                        else:
                            print(f"  [ban] verified {placed}/"
                                  f"{len(banned_positions)} bans placed.")
                    except Exception as e:
                        print(f"  [ban] counter check failed ({e}) — continuing.")

                    bans_done_this_match = True
                    # Persist IMMEDIATELY. This flag only mattered across a
                    # restart, and save_progress otherwise fires only on a debit
                    # or a scored result — so a crash in the window between
                    # placing the bans and finishing the match would lose it,
                    # which is exactly the case it exists for.
                    save_progress(wins, losses, draws, balance, progress_file,
                                  match_in_progress=match_in_progress,
                                  bans_done_this_match=bans_done_this_match)
                except Exception as e:
                    stuck_count += 1
                    print(f"Couldn't complete the ban screen ({e}), retrying... ({stuck_count}/{MAX_STUCK_ATTEMPTS})")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Stuck too long on the ban screen — stopping. Check the game manually.")
                        stop_reason = "ban_screen_stuck"
                        break
                    time.sleep(2)
                    continue
                acted_screen = "ban_screen"
                stuck_count = 0
                wait_for_screen_to_settle(max_wait=8.0, regions="ban")
                continue

            elif screen == "discard_prompt":
                # N3: same defect class as C1-C3 — this branch sends keypresses and
                # unconditionally reset stuck_count, so a prompt that never
                # dismissed produced an unbounded keypress loop. Count repeats.
                if acted_screen == "discard_prompt":
                    stuck_count += 1
                    print(f"Discard prompt still up after acting — "
                          f"({stuck_count}/{MAX_STUCK_ATTEMPTS}).")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Discard prompt never cleared — stopping. Check the game manually.")
                        stop_reason = "discard_prompt_stuck"
                        break
                    time.sleep(1)
                    continue
                acted_screen = "discard_prompt"
                stuck_count = 0
                # The should_redraw() decision is now made inside play_one_turn(),
                # before a card is even lifted, via select_and_discard(). This
                # branch catches the game's own Play/Discard prompt if the poll
                # lands on it directly (never observed live yet) — defaults to
                # Play since we don't have a confirmed reason to do otherwise here.
                press("confirm_play")
                wait_for_screen_to_settle(max_wait=8.0, regions="menu")
                continue

            elif screen == "turn":
                # N14/N25: a recurring "turn" screen is the normal steady state
                # (every new turn looks identical), so the acted_screen guard
                # deliberately does not apply here. But the stuck_count reset
                # below is NOT unconditional — an earlier version of this
                # comment claimed play_one_turn() "consumes a real card each
                # time", which is FALSE: the redraw path discards and returns
                # played=False. With an unconditional reset, a discard that
                # never lands resets the counter forever and the loop spins
                # without bound. Reset only on a confirmed play; legitimate
                # discards are capped by the game at 2-3 per match, well under
                # MAX_STUCK_ATTEMPTS, so letting the counter climb across them
                # is safe and still catches a genuinely stuck screen.
                if state_json["phase"] != last_phase:
                    turns_this_half = 0
                    # A NEW HALF DEALS A FRESH HAND OF FIVE, so the memory of the old
                    # one is not memory, it is five wrong cards. reset_hand_memory had
                    # exactly two call sites, both in the match_start_prompt branch, so
                    # a batting-half entry stayed live for every pitching turn.
                    # Demonstrated: a batting slot remembered as secondary 3 -- a
                    # BATTER'S SPEED, which the role census says a pitcher is never --
                    # was served for all three pitching turns. The memory's own comment
                    # names the case it does not handle ("the user pointed out it was
                    # the last hand of the inning, so the whole hand was replaced").
                    #
                    # And its safety net cannot catch this: memory is consulted only for
                    # slots the reader CANNOT see, so a readable card never audits it.
                    if last_phase is not None:
                        print(f"  [hand] phase {last_phase} -> {state_json['phase']}: "
                              "a new half deals a fresh hand — forgetting the old one")
                        reset_hand_memory()
                    last_phase = state_json["phase"]
                try:
                    played, matchup_info = play_one_turn(state_json, turns_this_half)
                except Exception as e:
                    # A bad vision read (e.g. an empty hand from a misclassified
                    # or transient screen) shouldn't kill the whole run — treat
                    # it the same as an unreadable screen and just retry.
                    stuck_count += 1
                    print(f"Couldn't act on this turn ({e}), retrying... ({stuck_count}/{MAX_STUCK_ATTEMPTS})")
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Stuck too long acting on turns — stopping. Check the game manually.")
                        stop_reason = "turn_action_failed"
                        break
                    time.sleep(2)
                    continue
                if played:
                    turns_this_half += 1
                    plays += 1
                    plays_this_match += 1
                    polls_without_progress = 0  # a played card is progress
                    # Positive per-turn signal. Absence of a misfire warning is
                    # NOT confirmation — it reads the same whether the auditor
                    # is working or silently not running. This says outright
                    # whether the focus cache engaged on the turn just played,
                    # which is the only way to see the TTL holding (or not)
                    # under live network conditions before the run ends.
                    try:
                        _fc, _fs = input_controller.focus_stats_since_mark()
                        if _fc + _fs:
                            print(f"  [input] turn used {_fc + _fs} presses: "
                                  f"{_fc} focus call(s), {_fs} cached"
                                  + ("  <-- cache not engaging, TTL may be too "
                                     "short for live latency" if _fs == 0 and
                                     _fc > 2 else ""))
                    except Exception:
                        pass
                    if matchup_info is not None:
                        # Capture the opponent's revealed card for match_log.jsonl.
                        # Best-effort: matchup logging must never break the real
                        # turn loop, so any failure here is swallowed and this
                        # turn just doesn't get logged.
                        try:
                            # Was a blind time.sleep(0.5), never validated
                            # against a real card-clash frame (see
                            # PENDING_LIVE_VALIDATION.md item 2). Now waits for
                            # the cards to actually APPEAR at centre. Do not
                            # "improve" this to wait for the centre to settle —
                            # the centre keeps animating for ~9s after the
                            # reveal and only goes quiet once the cards have
                            # already cleared.
                            # THE WATCHER'S EPISODE, NOT A POLL. The
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
                            # Known accepted limitation (QA, 2026-08-23): if our
                            # card and the opponent's happen to share a name
                            # (plausible from a shared card pool), both get
                            # filtered out here and this turn just isn't logged.
                            # Fails safe — reduces sample size, never mislabels
                            # a row — so not worth a fix for throwaway diagnostic data.
                            #
                            # Filtered to kind=="player" (2026-08-24 fix): a
                            # revealed tactics card (e.g. "Fielding Play") also
                            # has a name != our_card_name, so without this filter
                            # it could get picked here and logged as if it were
                            # the opponent's actual player card — wrong entity
                            # entirely, not just incomplete data.
                            # Case- and whitespace-insensitive (norm_name): the
                            # vision model returns the SAME card as "Pitcher" one
                            # turn and "PITCHER" the next, and an exact != let our
                            # own card through as the opponent's (match_log row 18).
                            _ours = norm_name(matchup_info["our_card_name"])

                            # MISFIRE CHECK — the only thing that can catch a
                            # dropped keystroke. Card selection is N move_right
                            # presses then a confirm; if ONE press is swallowed
                            # (stream hiccup, focus not landed, input too fast)
                            # the cursor stops a card short and we play a card we
                            # never chose. Nothing downstream notices: the game
                            # accepts it, the turn resolves, the loop continues.
                            #
                            # The reveal is the one place the truth is visible, and
                            # it was already being fetched and thrown away. If the
                            # card we INTENDED is not among the revealed players,
                            # either input misfired or the read is wrong — both
                            # worth knowing, neither currently detectable.
                            #
                            # It also stops a corrupt log row: the filter below
                            # picks "first player card that isn't ours", so on a
                            # misfire that is OUR OWN misplayed card, recorded as
                            # the opponent's.
                            _players = [c for c in reveal_cards if c.get("kind") == "player"]
                            # Strip base runners before anything reasons about
                            # this list — they are face-up cards on the diamond
                            # that the reveal read cannot tell from the faceoff.
                            # state_json is the pre-play state, so its runners
                            # are exactly the ones on screen during the reveal.
                            _players = exclude_runners(_players,
                                                       state_json.get("runners"))
                            # MATCH ON POWER, NOT NAME.
                            #
                            # Hand cards do not display a name — the vision model
                            # returns the type banner ("Batter") because that is
                            # the only text on the card. The reveal DOES show
                            # names. Comparing the two could therefore never
                            # match, and the first live run proved it: 2 of 2
                            # turns flagged as misfires, zero rows logged, and
                            # the adaptive backoff then slowed the run in
                            # response to its own false alarms.
                            #
                            # Power is what the hand actually gives, and gives
                            # reliably: local PaddleOCR and vision agreed on
                            # power/secondary for every card read live.
                            #
                            # Weaker than a name match — two cards can share a
                            # power — but it still catches the failure that
                            # matters, a cursor landing on a different card than
                            # the engine chose, and it abstains rather than
                            # fabricating when power is unknown.
                            _ours_power = matchup_info.get("our_power")
                            # Only a swing/pitch boost changes the power the
                            # reveal will show. A speed or fielding boost's
                            # effect is not a confirmed rule (see
                            # simulate.power_bonus, fixed 2026-08-23), so
                            # adding its bonus here widened `acceptable` to
                            # two values for nothing — masking real misfires
                            # roughly 15% more often, in a check whose entire
                            # job is to notice a card that isn't ours.
                            _bonus = (matchup_info.get("our_tactics_bonus") or 0
                                      if matchup_info.get("our_tactics_kind")
                                      in POWER_TACTIC_KINDS else 0)
                            # ONLY AUDIT A COMPLETE READ. reveal_cards is the
                            # RAW list on purpose — _players has already had
                            # the runners stripped out of it, so counting that
                            # would fail every runner-on turn. See
                            # reveal_is_complete() for the measured invariant
                            # and the three live false misfires it kills.
                            if (_players
                                    and reveal_is_complete(reveal_cards,
                                                           state_json.get("runners"))
                                    and not our_card_in_reveal(
                                        _ours_power, _bonus, _players)):
                                _seen = [(c.get("name"), c.get("power"),
                                          sorted(revealed_powers(c)))
                                         for c in _players]
                                print(f"  [MISFIRE?] no revealed card has our played "
                                      f"power {_ours_power} (or {_ours_power + _bonus} "
                                      f"with the boost) — revealed {_seen}. Either a "
                                      f"keystroke was dropped during card selection "
                                      f"or the reveal misread. Not logging this turn.")
                                record_observation(event="suspected_misfire",
                                                   intended_power=_ours_power,
                                                   revealed=_seen)
                                matchup_info["misfire_suspected"] = True
                                misfires += 1
                                # Let the input layer slow itself down. Capped
                                # and floored there — see report_misfire().
                                try:
                                    input_controller.report_misfire()
                                except Exception as _e:
                                    # The misfire COUNT climbs either way, so
                                    # the symptom stays visible while the cause
                                    # disappears: if this raised, ACTION_DELAY
                                    # was NOT raised, FOCUS_TTL was NOT killed
                                    # and the cursor was NOT invalidated. The
                                    # run then looks like input timing that
                                    # refuses to self-correct, and the pacing
                                    # summary at the end will show an
                                    # ACTION_DELAY that never moved.
                                    print(f"  WARNING: report_misfire() raised "
                                          f"{_e!r} — the input layer did NOT "
                                          f"slow itself down. Misfires will "
                                          f"keep being counted with nothing "
                                          f"adjusting in response; this is not "
                                          f"a timing problem that resisted the "
                                          f"fix, it is the fix not running.")
                                raise RuntimeError("intended card absent from reveal")

                            # _players, NOT reveal_cards. This passed the raw
                            # list until QA caught it on 2026-08-26, which made
                            # the runner strip above completely inert: both of
                            # pick_opponent_card's paths need a clean two-card
                            # faceoff, so with the runners still in, ANY runner
                            # on base guaranteed None and dropped the turn —
                            # exactly the 15 drops the strip was written to fix.
                            opponent_card = pick_opponent_card(
                                _players, _ours,
                                our_power=_ours_power, bonus=_bonus,
                                # _players may still hold runners: the strip
                                # above refuses to go below two cards. Passing
                                # them lets the >2 path finish the job.
                                runners=state_json.get("runners"))
                            if opponent_card is not None:
                                matchup_info["opp_card_name"] = opponent_card.get("name")
                                # Do not log a power the floor says cannot
                                # exist. match_log.jsonl already contains an
                                # `opp_power: 3` row — a tactics bonus digit
                                # read as power. Prefer the roster's value,
                                # and log None rather than a fiction, so the
                                # analyser excludes the row instead of
                                # silently averaging a wrong number into it.
                                _raw_opp = opponent_card.get("power")
                                _opp_known = revealed_powers(opponent_card)
                                matchup_info["opp_power"] = (
                                    _raw_opp if (_raw_opp or 0) >= MIN_PLAYER_POWER
                                    else (min(_opp_known) if _opp_known else None))
                                matchup_info["opp_secondary"] = opponent_card.get("secondary")
                                # The opponent's tactics card (if any) is whichever
                                # kind=="tactics" entry is paired with their player
                                # card — not simply "any tactics entry", since ours
                                # can also appear in the same reveal. Matters for
                                # the fielding/speed analysis: an opponent's boosted
                                # power (see power_bonus() in simulate.py) would
                                # otherwise look like an unexplained outcome and
                                # get misattributed to the secondary-stat effect
                                # actually being investigated.
                                opp_tactics = next(
                                    (c for c in reveal_cards
                                     if c.get("kind") == "tactics"
                                     and norm_name(c.get("paired_with")) == norm_name(opponent_card.get("name"))),
                                    None,
                                )
                                matchup_info["opp_tactics_bonus"] = opp_tactics.get("bonus", 0) if opp_tactics else 0
                                # See our_tactics_kind: bonus without type can't
                                # be turned into effective power.
                                # Derive the kind from the NAME, not from a
                                # "type" field — READ_MATCHUP_PROMPT's tactics
                                # schema is {kind, name, bonus, paired_with} and
                                # has never contained `type`. The old
                                # `.get("type")` therefore returned None
                                # unconditionally: measured None on 39/39 rows,
                                # including the 8 with a non-zero bonus. Those
                                # rows were then dropped by analyze_match_log.py
                                # as "kind missing" — the exact data this field
                                # was added to capture.
                                matchup_info["opp_tactics_kind"] = (
                                    _tactics_kind_from_name(opp_tactics.get("name"))
                                    if opp_tactics else None)
                                pending_matchup = matchup_info
                            else:
                                # No else here until 2026-08-26, and that was
                                # the single largest hole in the dataset: the
                                # opponent is matched BY NAME, the reveal's
                                # least reliable field, and a miss dropped the
                                # entire turn without printing one character.
                                # 27 decisions -> ~3 rows in that run.
                                _seen_names = [c.get("name") for c in reveal_cards
                                               if c.get("kind") == "player"]
                                print(f"  [reveal] no OPPONENT card identified "
                                      f"(ours={_ours!r}, revealed players="
                                      f"{_seen_names}) — turn not logged.")
                                record_observation(event="reveal_no_opponent",
                                                   ours=_ours,
                                                   revealed=_seen_names)
                        except Exception as _e:
                            # Was `pass`. A bare pass here meant a malformed
                            # reveal, a bad key, or an OCR crash all looked
                            # identical to a turn that simply had nothing to
                            # log — no message, no row, no way to count them.
                            print(f"  [reveal] turn NOT logged — "
                                  f"{type(_e).__name__}: {_e}")
                    stuck_count = 0     # N25: only a confirmed PLAY is progress
                else:
                    # A discard leaves the screen looking identical. Legitimate
                    # discards are capped by the game (2-3 per match), so
                    # letting the counter climb here still tolerates every real
                    # redraw while bounding a discard that never lands.
                    stuck_count += 1
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Discarding repeatedly with no play landing — "
                              "stopping. Check the game manually.")
                        stop_reason = "redraw_never_played"
                        break
                # Wait only as long as the actual animation takes (a quick out
                # settles in ~2s, a home run can run longer) instead of always
                # sleeping the old fixed worst-case delay.
                #
                # regions="turn" is the important part: the next loop iteration
                # reads the hand, scoreboard and bases, so settle must be
                # judged on THOSE. The old single ROI excluded the hand
                # entirely and let the loop read cards mid-deal.
                # WAIT FOR THE DEAL, NOT FOR QUIET. See wait_for_hand_deal():
                # the hand is quiet for ~15s after a play simply because the
                # replacement card has not arrived yet, so settling on it here
                # released a median of 14.7s early on 88/88 real plays, buying
                # a wasted vision call plus a 2s retry each time — and it is
                # the source of the empty-hand / power-0 reads that pushed
                # should_redraw() into discarding a hand that was actually fine.
                if post_play_wait_for_deal():
                    wait_for_hand_deal(baseline=pop_hand_baseline())
                wait_for_screen_to_settle(max_wait=8.0, regions="turn")
                time.sleep(0.4)  # small buffer past "settled" before the next read

            else:
                # Menus, dialogue, loading, or anything unrecognized.
                stuck_count += 1
                print(f"Unrecognized screen ({screen}), waiting... "
                      f"({stuck_count}/{MAX_UNRECOGNIZED_ATTEMPTS}) "
                      f"[api {_api_used()} calls spent]")
                # The tighter limit applies HERE ONLY. Every retry on an
                # unrecognised screen is a paid API call that learns nothing,
                # unlike a retry after a transient bad read.
                if stuck_count >= MAX_UNRECOGNIZED_ATTEMPTS:
                    print("Stuck too long on an unrecognized screen — stopping. "
                          "Check the game manually.")
                    stop_reason = "unrecognized_screen"
                    break
                time.sleep(2)

    finally:
        stop_reveal_watcher()
        if screenshot_stop is not None:
            screenshot_stop.set()
        if stop_reason is not None:
            dump_diagnostics(stop_reason, {
                "wins": wins, "losses": losses, "draws": draws,
                "balance": balance, "spent": spent,
                "stuck_count": stuck_count, "acted_screen": acted_screen,
                "motion_skips": motion_skips, "target_wins": target_wins,
                "plays": plays, "misfires": misfires,
            })
        # Print the real settle distribution. This is the number that decides
        # whether max_wait=8.0 is right; everything before tonight was
        # estimated from a log too coarse to resolve the production poll rate.
        print(settle_stats_summary())
        if plays:
            _pct = 100.0 * misfires / plays
            _verdict = ("input timing looks safe" if misfires == 0 else
                        "RAISE ACTION_DELAY or set FOCUS_TTL=0 in input_controller.py")
            print(f"  [input] {plays} cards played, {misfires} suspected misfire(s) "
                  f"({_pct:.1f}%) — {_verdict}")
            try:
                print(input_controller.focus_cache_summary())
                print(input_controller.input_pacing_summary())
            except Exception as _e:
                # These two lines are the only evidence in the whole run of
                # whether report_misfire() ever adjusted anything. Swallowed,
                # the misfire percentage above stands alone and reads as a
                # verdict on input timing when it may be a verdict on a
                # self-correction that never happened.
                print(f"  [input] focus/pacing summary UNAVAILABLE ({_e!r}) — "
                      f"the misfire rate above is reported WITHOUT the "
                      f"ACTION_DELAY and focus-cache figures, so it cannot "
                      f"tell you whether the input layer adapted or not.")

    if wins >= target_wins:
        print(f"Done — reached {wins} wins ({losses} losses, {draws} draws).")
    else:
        print(f"Stopped early at {wins}/{target_wins} wins ({losses} losses, {draws} draws). "
              f"Progress is saved — just rerun the script to pick back up.")


if __name__ == "__main__":
    # Adjust to however many wins you actually still need.
    # Balance is read automatically from the pause menu on the first run.
    # Pass starting_balance=<amount> instead if you'd rather skip that and
    # set it manually.
    run(target_wins=17)
