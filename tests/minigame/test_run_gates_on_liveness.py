"""run(): the I-05a liveness gate, at the top of every poll, via the harness.

THE BUG. ensure_live() returning True is not proof the game will take input
(CLAUDE.md section 1): it is satisfied by a heartbeat, and the PS5 Control
Center can sit on top of a live one. Before this landed, run()'s only defence
against a dead capture was the "Couldn't read the screen" except branch --
bounded by MAX_STUCK_ATTEMPTS, but reached only once read_state_for_turn had
already thrown. Evidence 2026-09-20: a parked match, the PS5 auto-slept,
run_one_match.py burned real retries against chiaki's own host list
(1867x1050) before ensure_live() ever ran.

THE FIX, tested here. orchestrator._screen_shows_the_game() (see its
docstring) runs BEFORE any read: if the capture is not the PS5's 1920x1080, or
ensure_stream.looks_like_ui(img) is True and no game reader answers, the poll
counts toward stuck_count, ensure_stream.ensure_live() is tried at most ONCE
per stall, and nothing else is pressed from the gate itself.

REAL IMAGES, REAL READERS. This file does not stub compass.read_bearing,
pause_menu.is_pause_screen, table_prompt.at_table or reset_env.load_save_dialog
-- it feeds real (or trivially synthetic) frames through the harness's
`liveness_frame` and lets the REAL _screen_shows_the_game()/looks_like_ui()/
ensure_stream._game_visible() chain answer, which is what makes the third
scenario below an actual regression test for I-24 rather than an assertion
about a stub.

    1. test_fixtures/not_streaming/hostlist_standby.png (1867x1050) -- wrong
       size alone must fire the gate.
    2. a synthetic solid-colour 1920x1080 frame -- right size, but
       looks_like_ui() is True (one exact RGB value across the whole frame)
       and no game reader answers it. Must fire the gate the SAME way as (1).
    3. test_fixtures/load_last_save_dialog_live_20260920.png (1920x1080) --
       I-24's own known false positive: looks_like_ui() is ALSO True here
       (pinned in test_streaming_rejects_chiaki_ui.py), but
       reset_env.load_save_dialog(img) answers True, so this is the CONTROL:
       the gate must NOT fire, ensure_live() must never be called, and the
       loop must read states normally.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ["BASEBALL_TEST_RUN"] = "1"

from _run_harness import Harness, RESULT_WIN, _PLAYED, check, failures
import orchestrator as o

import contextlib
import io

from PIL import Image

import ensure_stream

HOSTLIST = os.path.join(_ROOT, "test_fixtures", "not_streaming",
                        "hostlist_standby.png")
DIALOG = os.path.join(_ROOT, "test_fixtures",
                      "load_last_save_dialog_live_20260920.png")

check(os.path.exists(HOSTLIST),
      f"missing fixture {HOSTLIST} -- scenario 1 cannot run without it")
check(os.path.exists(DIALOG),
      f"missing fixture {DIALOG} -- scenario 3 (the I-24 control) cannot "
      f"run without it")


def _with_recorded_ensure_live(fn):
    """Run `fn()` with ensure_stream.ensure_live replaced by a call counter.

    Returns (fn's return value, call count). The real ensure_live() already
    refuses under BASEBALL_TEST_RUN (ensure_stream._refuse_under_test), so
    leaving it live would be safe but silent -- this makes the call itself
    observable, which is the actual thing under test here.
    """
    calls = {"n": 0}
    real = ensure_stream.ensure_live

    def fake(*a, **k):
        calls["n"] += 1
        return False
    ensure_stream.ensure_live = fake
    try:
        result = fn()
    finally:
        ensure_stream.ensure_live = real
    return result, calls["n"]


# =========================================================================
# 1 & 2: THE GATE FIRES. host-list size, then a same-size UI frame with no
# reader answering -- "the same", per the ticket. Neither ever reaches a
# screen read, and ensure_live is tried exactly once for the whole stall
# (MAX_STUCK_ATTEMPTS polls), not once per poll.
# =========================================================================
SCENARIOS = []
if os.path.exists(HOSTLIST):
    SCENARIOS.append(("host-list frame (1867x1050)", Image.open(HOSTLIST)))
SCENARIOS.append(("same-size UI frame, no reader answers",
                  Image.new("RGB", (1920, 1080), (40, 40, 40))))

for label, frame in SCENARIOS:
    h = Harness([], liveness_frame=frame)
    buf = io.StringIO()

    def _go():
        with contextlib.redirect_stdout(buf):
            h.run(target_wins=99)
    _, ensure_live_calls = _with_recorded_ensure_live(_go)
    out = buf.getvalue()

    check(h.presses == [],
          f"{label}: the gate itself pressed {h.presses!r} -- it must never "
          f"press anything on its own")
    check(h.next_state_calls == 0,
          f"{label}: read_state_for_turn was reached {h.next_state_calls}x -- "
          f"a dead capture must never fall through to a real read")
    check(ensure_live_calls == 1,
          f"{label}: ensure_stream.ensure_live() was called {ensure_live_calls}x "
          f"across a whole stall, expected exactly 1 (bounded, not once a poll)")
    check(out.count("not looking at the game") == o.MAX_STUCK_ATTEMPTS,
          f"{label}: the gate logged 'not looking at the game' "
          f"{out.count('not looking at the game')} times, expected exactly "
          f"MAX_STUCK_ATTEMPTS ({o.MAX_STUCK_ATTEMPTS}) -- stuck_count must "
          f"climb on EVERY firing, and the loop must stop there")
    check("Stuck too long off the game screen" in out,
          f"{label}: no stop message printed -- MAX_STUCK_ATTEMPTS was not "
          f"honoured")


# =========================================================================
# 3: THE CONTROL (I-24). looks_like_ui is True here too (pinned in
# test_streaming_rejects_chiaki_ui.py), but reset_env.load_save_dialog
# answers True -- so the SAME false positive that fools looks_like_ui alone
# must NOT also fool this gate. The loop should never see the liveness gate
# fire and should read states normally.
# =========================================================================
if os.path.exists(DIALOG):
    dialog_img = Image.open(DIALOG)
    # Sanity-check the fixture's own two preconditions before trusting the
    # control -- otherwise a fixture that stopped reproducing either half
    # would make this pass for the wrong reason.
    check(ensure_stream.looks_like_ui(dialog_img) is True,
          "I-24 precondition: looks_like_ui must be True on the Load Last "
          "Save dialog fixture, or this is not testing the false positive "
          "it claims to")
    check(ensure_stream._game_visible(dialog_img) is True,
          "precondition: reset_env.load_save_dialog (inside _game_visible) "
          "must answer True on this fixture, or the control cannot pass "
          "for the right reason")

    h = Harness(_PLAYED + [RESULT_WIN], liveness_frame=dialog_img)
    buf = io.StringIO()

    def _go2():
        with contextlib.redirect_stdout(buf):
            h.run(target_wins=1)
    _, ensure_live_calls = _with_recorded_ensure_live(_go2)
    out = buf.getvalue()

    check(ensure_live_calls == 0,
          f"I-24 control: ensure_stream.ensure_live() was called "
          f"{ensure_live_calls}x -- the gate must not fire on the game's own "
          f"dialog")
    check("not looking at the game" not in out,
          "I-24 control: the gate logged 'not looking at the game' against "
          "a real game screen")
    check(h.next_state_calls > 0,
          f"I-24 control: read_state_for_turn was never reached "
          f"({h.next_state_calls}x) -- the gate blocked a normal turn loop")


print("OK: I-05a liveness gate -- fires on a wrong-size capture and on a "
      "same-size UI frame with no reader answering (bounded at "
      "MAX_STUCK_ATTEMPTS, ensure_live tried once per stall, nothing else "
      "pressed), and does NOT fire on the I-24 control (the game's own Load "
      "Last Save dialog, where looks_like_ui is also True)")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} liveness-gate failure(s)")
