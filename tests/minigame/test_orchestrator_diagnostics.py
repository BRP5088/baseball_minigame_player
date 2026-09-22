"""Six places on the money path where orchestrator.py did nothing and looked fine.

CLAUDE.md §10.1: "the code did nothing, and doing nothing looked exactly like
working". Each site below produced output — or an absence of output — that a
reader would confidently interpret as the healthy case:

  1. _fast_grab() falling back to a full-screen grab. Every fractional crop in
     the file then reads the DESKTOP, and the symptoms (never settles, prompt
     never found, stall screenshot of the editor) all point elsewhere. HOT
     (~7 Hz), so the warning must be once per process.
  2. repair_phase_from_hand() abstaining. A silent abstention is byte-identical
     to a check that ran and agreed, so "vision improved" and "the repair never
     fired" are the same log. This guard exists for 12 of ~255 decisions that
     played the wrong card type, at $50 a match.
  3. read_balance_from_pause_menu() retrying silently, and never verifying the
     CLOSE. A dropped close leaves the game paused; the symptom appears minutes
     later as "no input is reaching the game".
  4. should_redraw()'s false branch. The true branch logged its numbers; the
     false branch wrote nothing, so the value that decided whether to burn a
     discard in a paid match was never recorded. §10.4: you cannot plot a
     distribution you never wrote down.
  5. The stall bundle recording its own screenshot error onto a dict that was
     already written to disk — i.e. into nothing.
  6. `except Exception: pass` around report_misfire(), which mutates
     ACTION_DELAY, kills FOCUS_TTL and invalidates the cursor. The misfire
     COUNT still climbs, so the symptom stays and the cause vanishes.

Offline: no capture, no vision, no API key, no PS5 input.
"""

import os as _os
import sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
import sys

# HARD OFF before anything project-owned is imported: this is what holds every
# input path away from the live console.
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import ast
import contextlib
import io
import re
import tempfile

from PIL import Image

import orchestrator as orch

FAILS = []


def check(name, cond):
    if not cond:
        FAILS.append(name)


@contextlib.contextmanager
def captured():
    """Collect everything printed inside the block."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def _lines(buf):
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


# ===========================================================================
# 1. _fast_grab()'s desktop fallback must announce itself — ONCE per process
# ===========================================================================
import game_capture

_saved = (game_capture.grab, orch._MSS, orch.pyautogui.screenshot,
          set(orch._WARNED_ONCE))
try:
    game_capture.grab = lambda *a, **k: None          # window lookup fails
    orch._MSS = None                                  # force the pyautogui arm
    orch.pyautogui.screenshot = lambda *a, **k: Image.new("RGB", (8, 8))
    orch._WARNED_ONCE.clear()

    with captured() as buf:
        for _ in range(3):
            orch._fast_grab()
    out = buf.getvalue()

    check("_fast_grab's desktop fallback is SILENT — every fractional crop in "
          "the file is now reading the wrong pixels and nothing says so",
          out.strip() != "")

    # The message has to name the consequence, not just the failure. "grab
    # failed" sends a reader to game_capture; the actual problem is that every
    # crop downstream is measuring the desktop.
    low = out.lower()
    check("the fallback warning does not say that the crops now read the "
          "DESKTOP — a reader would debug the settle gate instead",
          "desktop" in low)
    check("the fallback warning does not mention falling back",
          "fall" in low or "fallback" in low)

    # HOT PATH: ~7 Hz in the settle loop. One line is a diagnosis; ten thousand
    # bury the log the diagnosis is supposed to appear in.
    warned = [ln for ln in _lines(buf) if "game_capture.grab()" in ln]
    check(f"the hot-path fallback warning printed {len(warned)} times for 3 "
          f"calls — it must be once per process or it floods the settle loop",
          len(warned) == 1)
finally:
    game_capture.grab, orch._MSS, orch.pyautogui.screenshot = _saved[:3]
    orch._WARNED_ONCE.clear()
    orch._WARNED_ONCE.update(_saved[3])

# The helper itself: first call prints and reports it, later calls do neither.
_saved_warned = set(orch._WARNED_ONCE)
try:
    orch._WARNED_ONCE.clear()
    with captured() as buf:
        first = orch._warn_once("unit-test message alpha")
        second = orch._warn_once("unit-test message alpha")
        other = orch._warn_once("unit-test message beta")
    check("_warn_once did not print on first sight of a message", first is True)
    check("_warn_once repeated a message it had already printed",
          second is False)
    check("_warn_once suppressed a DIFFERENT message — it must be keyed on the "
          "message, not a single global 'already warned' flag", other is True)
    check("_warn_once printed the wrong number of lines",
          len(_lines(buf)) == 2)
finally:
    orch._WARNED_ONCE.clear()
    orch._WARNED_ONCE.update(_saved_warned)


# ===========================================================================
# 2. repair_phase_from_hand() must say WHY it did nothing
# ===========================================================================
def _p(name, i=0, power=7):
    return {"kind": "player", "name": name, "power": power, "secondary": 0,
            "hand_index": i}


def _state(phase, hand):
    return {"screen": "turn", "phase": phase, "hand": hand,
            "runners": [], "your_score": 0, "opp_score": 0}


# (a) a real player name carries no phase evidence -> abstain, loudly
s = _state("batting", [_p("Rube Sharp", 0), _p("Pitcher", 1)])
with captured() as buf:
    orch.repair_phase_from_hand(s)
check("repair_phase_from_hand abstained SILENTLY on a real player name — "
      "indistinguishable from a check that ran and agreed",
      _lines(buf) != [])
check("the real-name abstention does not name the card that caused it",
      "Rube Sharp" in buf.getvalue())
check("BEHAVIOUR CHANGED: the real-name case must still leave phase alone",
      s["phase"] == "batting")

# (b) a mixed hand proves nothing -> abstain, loudly
s = _state("batting", [_p("Pitcher", 0), _p("Batter", 1)])
with captured() as buf:
    orch.repair_phase_from_hand(s)
check("repair_phase_from_hand abstained SILENTLY on a mixed hand",
      _lines(buf) != [])
check("BEHAVIOUR CHANGED: a mixed hand must not flip the phase",
      s["phase"] == "batting")

# (c) an empty hand is not evidence either
s = _state("batting", [])
with captured() as buf:
    orch.repair_phase_from_hand(s)
check("repair_phase_from_hand abstained SILENTLY on an empty hand",
      _lines(buf) != [])
check("BEHAVIOUR CHANGED: an empty hand must not flip the phase",
      s["phase"] == "batting")

# (d) THE CASE THAT MOTIVATES ALL OF THIS: the check running and AGREEING must
#     look different in the log from the check never having had evidence.
s = _state("batting", [_p("Batter", 0), _p("Batter", 1)])
with captured() as buf:
    orch.repair_phase_from_hand(s)
agree_out = buf.getvalue()
check("the agreement case is SILENT — so 'vision improved' and 'the repair "
      "stopped firing' produce the same log, which is the whole finding",
      _lines(buf) != [])
check("BEHAVIOUR CHANGED: an agreeing hand must leave phase alone",
      s["phase"] == "batting")

# (e) the repair itself must still fire and still say so
s = _state("batting", [_p("Pitcher", 0), _p("Pitcher", 1)])
with captured() as buf:
    orch.repair_phase_from_hand(s)
check("BEHAVIOUR CHANGED: an all-pitcher hand must still flip a batting phase",
      s["phase"] == "pitching")
check("the repair fired without logging", _lines(buf) != [])

# The four outcomes must be DISTINGUISHABLE, not merely non-empty. Four
# identical lines would satisfy every check above and inform nobody.
_outs = set()
for _phase, _hand in (("batting", [_p("Rube Sharp", 0)]),
                      ("batting", [_p("Pitcher", 0), _p("Batter", 1)]),
                      ("batting", [_p("Batter", 0)]),
                      ("batting", [_p("Pitcher", 0)])):
    _s = _state(_phase, _hand)
    with captured() as buf:
        orch.repair_phase_from_hand(_s)
    _outs.add(buf.getvalue().strip())
check(f"the phase-repair outcomes are not distinguishable in the log — got "
      f"{len(_outs)} distinct messages for 4 different outcomes",
      len(_outs) == 4)


# ===========================================================================
# 3. read_balance_from_pause_menu(): log which attempt landed, verify the close
# ===========================================================================
class _Blk:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Blk(text)]


class _Msgs:
    def create(self, **kw):
        return _Resp('{"counters": [246, 3, 5], "money": 246}')


class _Client:
    messages = _Msgs()


import pause_menu as _pm
import input_controller as _ic

_b = (orch.press, _ic.press, orch.wait_for_screen_to_settle, orch._fast_grab,
      orch.capture_screenshot_b64, orch.client, _pm.is_pause_screen)


def _run_balance(open_on_attempt, closes):
    """Drive the reader with a scripted pause menu. Returns (money, output).

    I-58 (2026-09-21): the close is now VERIFIED -- `_close_pause_menu_verified`
    calls input_controller.press_verified, which presses through
    input_controller.press, not orchestrator's own `press` name, and it reads
    the menu state through a fresh `is_pause_screen` call before AND after
    each press (baseline, then one read per attempt). A stub keyed on a raw
    call-count threshold cannot tell those calls apart from the OPEN loop's
    own calls or from `read_money`'s internal guard call, so it must track
    the actual toggle instead: every real toggle_pause press flips it. The
    OPEN sequence lands on attempt `open_on_attempt`; the CLOSE -- a separate
    toggle sequence -- lands on its first press when `closes` is True, and
    never lands when `closes` is False, exactly as a real dropped toggle
    would look to a fresh, settled read.
    """
    state = {"toggle_presses": 0, "open": False}

    def _do_press(action, *a, **kw):
        if action != "toggle_pause":
            return
        state["toggle_presses"] += 1
        n = state["toggle_presses"]
        if n <= open_on_attempt:
            state["open"] = (n == open_on_attempt)
        elif closes:
            state["open"] = False
        # else: a close press that never lands -- state unchanged

    def _is_pause(img):
        return state["open"]

    orch.press = _do_press
    _ic.press = _do_press
    orch.wait_for_screen_to_settle = lambda *a, **k: None
    orch._fast_grab = lambda *a, **k: Image.new("RGB", (8, 8))
    orch.capture_screenshot_b64 = lambda *a, **k: ""
    orch.client = _Client()
    _pm.is_pause_screen = _is_pause
    with captured() as buf:
        money = orch.read_balance_from_pause_menu()
    return money, buf.getvalue()


try:
    # (a) opened first time, closed cleanly
    money, out = _run_balance(open_on_attempt=1, closes=True)
    check(f"BEHAVIOUR CHANGED: the clean path must still return the money "
          f"(got {money!r})", money == 246)
    # Matched on the ATTEMPT NUMBER, not on any digit being present anywhere:
    # "$246" and "3 counters" would satisfy a loose substring check with the
    # attempt logging deleted (§10.12).
    _confirmed = [ln for ln in out.splitlines()
                  if re.search(r"confirmed .*attempt\s+1\b", ln)]
    check("nothing logged which attempt opened the pause menu — a toggle that "
          "is degrading toward never landing stays invisible until it fails",
          len(_confirmed) == 1)
    check("a clean close must not warn that the menu is still open",
          "still open" not in out.lower())

    # (b) the toggle missed twice. Money is still read, but the retries must
    #     be on the record: this is a TOGGLE, and a miss may mean it CLOSED a
    #     menu rather than being slow.
    money, out = _run_balance(open_on_attempt=3, closes=True)
    check("BEHAVIOUR CHANGED: two missed toggles must still end in a read",
          money == 246)
    _attempts = sorted({int(m) for m in re.findall(r"attempt\s+(\d)", out)})
    check(f"the silent retry loop is still silent — a read that took three "
          f"toggles must not log identically to one that took one "
          f"(attempt numbers seen: {_attempts})",
          _attempts == [1, 2, 3])
    check("the retry line does not say that a missed toggle may have CLOSED a "
          "menu rather than been slow — that is the reading that put the "
          "health coin in the wallet",
          "toggle" in out.lower())

    # (c) THE UNVERIFIED CLOSE. If it drops, the game stays paused and every
    #     later press lands in a menu; the symptom surfaces much later as
    #     "no input is reaching the game".
    money, out = _run_balance(open_on_attempt=1, closes=False)
    check("BEHAVIOUR CHANGED: a failed close must not stop the balance being "
          "returned — it is a warning, not an error", money == 246)
    low = out.lower()
    check("the closing toggle_pause is NOT verified — a dropped close leaves "
          "the game paused and nothing notices",
          "still open" in low or "did not land" in low)
    check("the stuck-menu warning does not say what the symptom will look "
          "like, so it will be misdiagnosed as dead input",
          "menu" in low and ("input" in low or "world" in low))
finally:
    (orch.press, _ic.press, orch.wait_for_screen_to_settle, orch._fast_grab,
     orch.capture_screenshot_b64, orch.client, _pm.is_pause_screen) = _b


# ===========================================================================
# 4. The redraw decision must log the VALUE on BOTH branches
# ===========================================================================
def _turn_state(powers, discards_left):
    return {
        "phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
        "discards_left": discards_left,
        "hand": [{"kind": "player", "name": f"P{i}", "power": p,
                  "secondary": 0, "hand_index": i}
                 for i, p in enumerate(powers)],
    }


_bt = (orch.select_and_play, orch.select_and_discard)
try:
    orch.select_and_play = lambda *a, **k: None
    orch.select_and_discard = lambda *a, **k: None

    # (a) FALSE branch, strong hand. This is the case that wrote nothing.
    #
    # SCOPED TO THE [redraw] LINE, not the whole output. play_one_turn also
    # prints "Decision: Playing P0 (power 9)", so a naive `"9" in out` passes
    # with the redraw logging deleted entirely — a vacuous check of exactly the
    # kind CLAUDE.md §10.12 warns about. Verified: it does.
    def _redraw_line(text):
        for ln in text.splitlines():
            if "[redraw]" in ln:
                return ln
        return ""

    with captured() as buf:
        played, _ = orch.play_one_turn(_turn_state([9, 5, 4], 2), 0)
    out = buf.getvalue()
    line = _redraw_line(out)
    check("BEHAVIOUR CHANGED: a strong hand must still be played, not discarded",
          played is True)
    check("the redraw decision's FALSE branch is silent — 'no discard' covers "
          "both 'the hand was strong' and 'no discards left'", line != "")
    # §10.4: the compared VALUE, or there is no distribution to plot later.
    check("the [redraw] line does not carry the max power it compared (9) — "
          "you cannot plot a distribution you never recorded",
          "9" in line)
    check("the [redraw] line does not carry the threshold it compared against "
          f"({orch.REDRAW_POWER_THRESHOLD}) — a bare value is uninterpretable",
          str(orch.REDRAW_POWER_THRESHOLD) in line)

    # (b) FALSE branch for the OTHER reason: no discards left. A weak hand that
    #     is played anyway must not look like a strong hand.
    with captured() as buf:
        played, _ = orch.play_one_turn(_turn_state([4, 4, 4], 0), 0)
    line_nodiscard = _redraw_line(buf.getvalue())
    check("BEHAVIOUR CHANGED: with no discards left the hand must be played",
          played is True)
    check("a weak hand played because there were NO DISCARDS LEFT logs the "
          "same line as a strong hand played on merit",
          line_nodiscard != "" and line_nodiscard != line)
    check("the [redraw] line does not carry the max power (4) on the "
          "no-discards path either", "4" in line_nodiscard)

    # (c) TRUE branch still behaves and still logs.
    with captured() as buf:
        played, _ = orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
    check("BEHAVIOUR CHANGED: a weak hand with discards left must still "
          "discard", played is False)
    check("the discard branch stopped logging", _lines(buf) != [])
finally:
    orch.select_and_play, orch.select_and_discard = _bt


# ===========================================================================
# 5. The stall bundle must PRINT its screenshot error, not stash it on a dict
#    that was already written to disk
# ===========================================================================
_g = orch._fast_grab
_dd = os.environ.get("BASEBALL_DIAGNOSTICS_DIR")
try:
    def _boom(*a, **k):
        raise OSError("no game window to capture")

    orch._fast_grab = _boom
    with tempfile.TemporaryDirectory() as td:
        os.environ["BASEBALL_DIAGNOSTICS_DIR"] = td
        with captured() as buf:
            d = orch.dump_diagnostics("unit-test stall")
        out = buf.getvalue()
    check("BEHAVIOUR CHANGED: a failed screenshot must not stop the bundle "
          "being written", bool(d))
    check("the stall bundle's screenshot error is still written onto `bundle` "
          "AFTER bundle.json was saved, so nobody ever reads it",
          "no game window to capture" in out)
    check("the missing-screenshot message does not name the file, so its "
          "absence reads as 'nobody saved one'",
          "screen_at_stall" in out)
finally:
    orch._fast_grab = _g
    if _dd is None:
        os.environ.pop("BASEBALL_DIAGNOSTICS_DIR", None)
    else:
        os.environ["BASEBALL_DIAGNOSTICS_DIR"] = _dd

_src = open(_os.path.join(_ROOT, "orchestrator.py"), encoding="utf-8").read()
check('the dead `bundle["screenshot_error"]` write is back — it assigns into a '
      'dict that has already been serialised',
      'bundle["screenshot_error"]' not in _src)


# ===========================================================================
# 6. report_misfire() and the input summaries must not be swallowed
# ===========================================================================
# These sit deep inside run()'s loop, which no offline test can reach, so this
# is checked structurally: find the `try` that wraps each call and assert its
# handler does something a reader can see. Asserted against the CALL, not
# against a line of text, so renaming a comment cannot make it pass.
_tree = ast.parse(_src)


def _calls_in(node):
    """Attribute calls under `node`, NOT descending into a nested try.

    Without the cutoff every ENCLOSING try also matches, and run()'s outer
    try/finally would be judged instead of the two-line handler this is about.
    """
    found = set()
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            found.add(cur.func.attr)
        for child in ast.iter_child_nodes(cur):
            if isinstance(child, ast.Try):
                continue                        # that try owns its own calls
            stack.append(child)
    return found


def _handler_reports(try_node):
    """Does every handler of this try print something, and bind the exception?"""
    if not try_node.handlers:
        return False
    for h in try_node.handlers:
        if h.name is None:                      # `except Exception:` — the
            return False                        # exception is discarded
        printed = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == "print" for n in ast.walk(h))
        if not printed:
            return False
        # The bound exception must actually reach the message.
        used = any(isinstance(n, ast.Name) and n.id == h.name
                   for n in ast.walk(h))
        if not used:
            return False
    return True


_found = {"report_misfire": False, "focus_cache_summary": False}
for _node in ast.walk(_tree):
    if not isinstance(_node, ast.Try):
        continue
    _body_calls = set()
    for _stmt in _node.body:
        if isinstance(_stmt, ast.Try):
            continue                    # belongs to that try, not this one
        _body_calls |= _calls_in(_stmt)
    for _target in _found:
        if _target in _body_calls:
            _found[_target] = True
            check(f"the try/except around {_target}() swallows its exception — "
                  f"the misfire COUNT still climbs, so the symptom is visible "
                  f"and the cause is not",
                  _handler_reports(_node))

for _target, _seen in _found.items():
    check(f"no try/except wrapping {_target}() was found in orchestrator.py — "
          f"this test is asserting against code that has moved", _seen)


if FAILS:
    for f in FAILS:
        print("  FAIL:", f)
    sys.exit(1)
print("  orchestrator diagnostics: the desktop fallback warns once per "
      "process; phase repair says why it abstained and when it agreed; the "
      "balance read logs which toggle landed and verifies the close; the "
      "redraw decision logs its value on both branches; the stall bundle "
      "prints its own screenshot error; report_misfire and the input "
      "summaries no longer swallow theirs")
sys.exit(0)
