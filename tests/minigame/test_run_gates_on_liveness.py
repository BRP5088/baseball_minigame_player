"""run(): the I-05a liveness gate, at the top of every poll, via the harness.

THE BUG. ensure_live() returning True is not proof the game will take input
(CLAUDE.md section 1): it is satisfied by a heartbeat, and the PS5 Control
Center can sit on top of a live one. Before this landed, run()'s only defence
against a dead capture was the "Couldn't read the screen" except branch --
bounded by MAX_STUCK_ATTEMPTS, but reached only once read_state_for_turn had
already thrown. Evidence 2026-09-20: a parked match, the PS5 auto-slept,
run_one_match.py burned real retries against chiaki's own host list
(1867x1050) before ensure_live() ever ran.

THE FIRST VERSION OF THIS FIX WAS ITSELF REFUTED (skeptic review of 2b426fa).
It used ensure_stream._game_visible's original four-reader set (world, pause
menu, dealer prompt, reset dialog) and fired whenever looks_like_ui was True
and none of those four answered. Measured against real 1920x1080 fixtures
where looks_like_ui is True, NONE of the four fires on a RESULT screen or a
REVEAL -- so the gate would have fired on an ordinary live match (a WINNER/
LOSER/DRAW banner, a mid-play reveal), ensure_live's overlay dismiss would
have toggled the PS5 overlay open and closed for nothing, and
MAX_STUCK_ATTEMPTS would have stopped the run in ~30s on a screen
local_state.read_result reads fine.

THE FIX, tested here, has three parts:

  (1) ensure_stream._game_visible (see its own docstring) now uses the FULL
      reader set -- the original four plus orchestrator.read_ban_counter,
      local_hand.read_hand on the hand crop, local_state.read_result /
      read_result_card, and orchestrator.center_card_edge_fraction (the
      reveal-arrival statistic). Measured zero false negatives over every
      1920x1080 fixture in the project that trips looks_like_ui -- section 2
      below reproduces that sweep directly, with the fixture list pinned.

  (2) orchestrator._screen_shows_the_game(img) only fires the gate AT ONCE for
      a wrong-size capture (chiaki's own window -- never a transient game
      frame). For a right-size, looks_like_ui-true, no-reader-answered frame
      it requires LIVENESS_MISS_SEC (6.0) SECONDS of UNINTERRUPTED wall-clock
      time since the first miss, not a poll count -- a second-skeptic review
      of an earlier poll-count version (LIVENESS_MISS_STREAK = 3) found that
      orchestrator.py's motion gate does a bare `continue` with NO sleep
      while a screen is animating, so three consecutive polls could complete
      in well under a second, exactly when misses are expected (see that
      constant's comment for the measured deal-animation miss-run
      distribution behind 6.0). Section 3 tests this directly: a lone
      ambiguous frame followed by a real game frame must NOT fire the gate at
      all, and section "M2" below tests that an INTERRUPTED run of misses
      (a hit in between) does not let elapsed time accumulate across the
      interruption.

  (3) run() now USES ensure_stream.ensure_live()'s return value. On False, the
      remaining polls of that stall skip the capture-and-reader-sweep
      entirely (liveness_recovery_failed) -- they just count toward
      stuck_count -- rather than re-running up to nine readers every 2s for an
      answer already known. Section 1 below asserts ensure_live is called
      exactly once across a whole stall, not once per poll.

REAL IMAGES, REAL READERS THROUGHOUT. This file does not stub
compass.read_bearing, pause_menu.is_pause_screen, table_prompt.at_table,
reset_env.load_save_dialog, local_hand.read_hand, local_state.read_result,
local_state.read_result_card, or orchestrator.center_card_edge_fraction -- it
feeds real (or trivially synthetic) frames through the harness's
`liveness_frame` and lets the REAL chain answer. The ONE harness stub that
would corrupt this if left alone is orchestrator.read_ban_counter, which
_run_harness.py's OWN patches dict stubs to a constant `self.ban_counter`
(default 3) for the ban-screen tests elsewhere in this suite -- with that
default, EVERY frame would read as "a ban screen is here" regardless of
pixels, defeating the whole point of testing real readers. Every scenario that
must NOT be recognised as the game therefore constructs its Harness with
`ban_counter=None`.
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
import glob
import io

from PIL import Image

import ensure_stream

# CLAUDE.md sec 10.11: a test must not assert the constant against ITSELF (that rises
# with the constant and passes forever). Every check below reads o.LIVENESS_MISS_SEC
# so an accidental edit sails through unnoticed -- pin the literal directly, once, so
# a change to the 9,729-frame-census calibration (CLAUDE.md sec 3/the QA6 finder notes)
# fails loudly instead of silently retuning every downstream assertion with it.
check(o.LIVENESS_MISS_SEC == 6.0,
      f"LIVENESS_MISS_SEC drifted from its calibrated 6.0s to {o.LIVENESS_MISS_SEC} -- "
      f"every debounce assertion in this file reads the constant, not this literal, so "
      f"a silent retune would otherwise pass unnoticed")

HOSTLIST = os.path.join(_ROOT, "test_fixtures", "not_streaming",
                        "hostlist_standby.png")
DIALOG = os.path.join(_ROOT, "test_fixtures",
                      "load_last_save_dialog_live_20260920.png")
WORLD_FRAME = os.path.join(_ROOT, "test_fixtures", "table_prompt_live.jpg")

check(os.path.exists(HOSTLIST),
      f"missing fixture {HOSTLIST} -- scenario 1 cannot run without it")
check(os.path.exists(DIALOG),
      f"missing fixture {DIALOG} -- scenario 4 (the I-24 control) cannot "
      f"run without it")
check(os.path.exists(WORLD_FRAME),
      f"missing fixture {WORLD_FRAME} -- scenario 3 needs a real GAME frame "
      f"to recover onto")


def _with_recorded_ensure_live(fn):
    """Run `fn()` with ensure_stream.ensure_live replaced by a call counter.

    Returns (fn's return value, call count). The real ensure_live() already
    refuses under BASEBALL_TEST_RUN (ensure_stream._refuse_under_test), so
    leaving it live would be safe but silent -- this makes the call itself
    observable, which is the actual thing under test here. It also returns
    False, exercising point (3): the caller must not keep polling readers
    after a failed recovery.
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
# 1: WRONG SIZE FIRES AT ONCE, every poll, no streak. Bounded by
#    MAX_STUCK_ATTEMPTS, ensure_live tried exactly once for the whole stall,
#    and once it has failed the remaining polls stop re-capturing/re-reading
#    (point 3) -- there is no way to observe that from outside except that the
#    run still terminates in exactly MAX_STUCK_ATTEMPTS "not looking" lines
#    despite the picture never changing.
# =========================================================================
h = Harness([], liveness_frame=Image.open(HOSTLIST), ban_counter=None)
buf = io.StringIO()


def _go1():
    with contextlib.redirect_stdout(buf):
        h.run(target_wins=99)


_, ensure_live_calls = _with_recorded_ensure_live(_go1)
out = buf.getvalue()

check(h.presses == [],
      f"host-list frame: the gate pressed {h.presses!r} -- it must never "
      f"press anything on its own")
check(h.next_state_calls == 0,
      f"host-list frame: read_state_for_turn was reached "
      f"{h.next_state_calls}x -- a wrong-size capture must never fall "
      f"through to a real read")
check(ensure_live_calls == 1,
      f"host-list frame: ensure_stream.ensure_live() was called "
      f"{ensure_live_calls}x across a whole stall, expected exactly 1")
check(out.count("not looking at the game") == o.MAX_STUCK_ATTEMPTS,
      f"host-list frame: the gate logged 'not looking at the game' "
      f"{out.count('not looking at the game')} times, expected exactly "
      f"MAX_STUCK_ATTEMPTS ({o.MAX_STUCK_ATTEMPTS})")
check("Stuck too long off the game screen" in out,
      "host-list frame: no stop message printed")


# =========================================================================
# 2: SAME-SIZE, looks_like_ui TRUE, NO READER ANSWERS -- the AMBIGUOUS case,
#    which needs LIVENESS_MISS_SEC (6.0) SECONDS of uninterrupted elapsed
#    time, not one poll. The same static frame every poll models "never
#    changes".
#
#    `motion=[True] * _M2_MOTION_POLLS` scripts every fall-through poll as
#    "still animating", which (a) advances the harness's virtual clock by
#    0.2s per poll -- a real motion check's own cost, per _screen_is_moving's
#    docstring -- and (b) `continue`s WITHOUT ever calling
#    read_state_for_turn. That second part matters: stuck_count is SHARED
#    across every guard in run(), including the separate "Unrecognized
#    screen (other)" branch (its own, TIGHTER budget, MAX_UNRECOGNIZED_
#    ATTEMPTS = 6) that a fall-through poll would otherwise land on with
#    screens=[] -- and 6 polls at 0.2s is only 1.2s, nowhere near enough to
#    cross a 6-second debounce. Scripting motion=True keeps every
#    fall-through poll OFF that unrelated budget, so this scenario measures
#    only the liveness debounce, not an accidental race between two
#    independent stuck-count consumers.
# =========================================================================
_M2_MOTION_POLLS = int(o.LIVENESS_MISS_SEC / 0.2) + 10  # generous margin
h2 = Harness([], liveness_frame=Image.new("RGB", (1920, 1080), (40, 40, 40)),
             ban_counter=None, motion=[True] * _M2_MOTION_POLLS)
buf2 = io.StringIO()


def _go2():
    with contextlib.redirect_stdout(buf2):
        h2.run(target_wins=99)


_, ensure_live_calls2 = _with_recorded_ensure_live(_go2)
out2 = buf2.getvalue()

check(h2.presses == [],
      f"same-size UI frame: the gate pressed {h2.presses!r}")
check(h2.next_state_calls == 0,
      f"same-size UI frame: read_state_for_turn was reached "
      f"{h2.next_state_calls}x -- every fall-through poll was scripted as "
      f"'still animating' so it should never be reached before the debounce "
      f"fires")
check(ensure_live_calls2 == 1,
      f"same-size UI frame: ensure_stream.ensure_live() was called "
      f"{ensure_live_calls2}x, expected exactly 1 -- tried once per stall")
check("not looking at the game" in out2,
      "same-size UI frame: the gate never fired at all over a persistent "
      "miss -- it must eventually fire")
# Pull the elapsed figure straight out of the gate's own log line
# ("N.Ns of misses running") rather than hard-coding a poll count: the
# TIME-based mechanism is what is under test, so the assertion should be on
# TIME, and it must be reported as having reached the real constant, not a
# fixed number that would silently go stale if LIVENESS_MISS_SEC is
# re-measured later.
import re as _re
_m = _re.search(r"\((\d+\.\d+)s of misses running\)", out2)
check(_m is not None,
      f"same-size UI frame: could not find an '(N.Ns of misses running)' "
      f"line in the output -- the gate's own log format changed:\n{out2!r}")
if _m is not None:
    _reported_elapsed = float(_m.group(1))
    check(_reported_elapsed >= o.LIVENESS_MISS_SEC,
          f"same-size UI frame: the gate fired after only "
          f"{_reported_elapsed}s of misses, expected at least "
          f"LIVENESS_MISS_SEC ({o.LIVENESS_MISS_SEC}s) -- it must not fire "
          f"early")
check("Stuck too long off the game screen" in out2,
      "same-size UI frame: no stop message printed")


# =========================================================================
# 3: A SINGLE TRANSIENT MISS MUST NOT FIRE ANYTHING. One ambiguous frame,
#    then a REAL game frame (table_prompt_live.jpg, a genuine world capture)
#    for the rest of the match. This is the direct regression test for the
#    debounce: with the debounce window wrongly near-zero (a poll-count
#    version at N=1, or a time version at ~0s), this scenario fires on poll
#    1 and calls ensure_live once -- exactly the mutant named in the ticket
#    ("a single-poll transition case must fail").
# =========================================================================
world_img = Image.open(WORLD_FRAME)
check(ensure_stream._game_visible(world_img) is True,
      "precondition: table_prompt_live.jpg must read as the game (at_table), "
      "or scenario 3 is not testing what it claims to")

h3 = Harness(_PLAYED + [RESULT_WIN],
             liveness_frame=[Image.new("RGB", (1920, 1080), (40, 40, 40)),
                            world_img],
             ban_counter=None)
buf3 = io.StringIO()


def _go3():
    with contextlib.redirect_stdout(buf3):
        h3.run(target_wins=1)


_, ensure_live_calls3 = _with_recorded_ensure_live(_go3)
out3 = buf3.getvalue()

check(ensure_live_calls3 == 0,
      f"single transient miss: ensure_stream.ensure_live() was called "
      f"{ensure_live_calls3}x -- one miss around a transition must never "
      f"trigger recovery")
check("not looking at the game" not in out3,
      "single transient miss: the gate logged 'not looking at the game' "
      "over a single blip")
check(h3.next_state_calls > 0,
      f"single transient miss: read_state_for_turn was never reached "
      f"({h3.next_state_calls}x) -- the debounce blocked a normal turn loop")


# =========================================================================
# 4: THE CONTROL (I-24). looks_like_ui is True here too (pinned in
#    test_streaming_rejects_chiaki_ui.py), but reset_env.load_save_dialog
#    answers True -- so the SAME false positive that fools looks_like_ui alone
#    must NOT also fool this gate. The loop should never see the liveness gate
#    fire and should read states normally.
# =========================================================================
dialog_img = Image.open(DIALOG)
check(ensure_stream.looks_like_ui(dialog_img) is True,
      "I-24 precondition: looks_like_ui must be True on the Load Last "
      "Save dialog fixture, or this is not testing the false positive "
      "it claims to")
check(ensure_stream._game_visible(dialog_img) is True,
      "precondition: reset_env.load_save_dialog (inside _game_visible) "
      "must answer True on this fixture, or the control cannot pass "
      "for the right reason")

h4 = Harness(_PLAYED + [RESULT_WIN], liveness_frame=dialog_img,
             ban_counter=None)
buf4 = io.StringIO()


def _go4():
    with contextlib.redirect_stdout(buf4):
        h4.run(target_wins=1)


_, ensure_live_calls4 = _with_recorded_ensure_live(_go4)
out4 = buf4.getvalue()

check(ensure_live_calls4 == 0,
      f"I-24 control: ensure_stream.ensure_live() was called "
      f"{ensure_live_calls4}x -- the gate must not fire on the game's own "
      f"dialog")
check("not looking at the game" not in out4,
      "I-24 control: the gate logged 'not looking at the game' against "
      "a real game screen")
check(h4.next_state_calls > 0,
      f"I-24 control: read_state_for_turn was never reached "
      f"({h4.next_state_calls}x) -- the gate blocked a normal turn loop")


# =========================================================================
# 5: THE FALSE-NEGATIVE SWEEP, reproduced directly (the fixture list is what
#    the skeptic asked to see pinned). Every 1920x1080 image under
#    test_fixtures/ that trips looks_like_ui must be caught by at least one
#    reader in ensure_stream._game_visible's full set -- ZERO exceptions.
#    Counted separately from the file-by-file breakdown so the assertion
#    fails loudly if the fixture population moves without anyone noticing.
# =========================================================================
_fixtures_dir = os.path.join(_ROOT, "test_fixtures")
_all_images = sorted(set(
    p for pattern in ("*.jpg", "*.jpeg", "*.png")
    for p in glob.glob(os.path.join(_fixtures_dir, "**", pattern), recursive=True)))
check(len(_all_images) > 500,
      f"only {len(_all_images)} fixture images found under {_fixtures_dir} -- "
      f"the sweep below cannot mean anything against a walk this small")

_checked_1920 = 0
_tripped_ui = 0
_false_negatives = []
for _p in _all_images:
    try:
        _img = Image.open(_p).convert("RGB")
    except Exception:
        continue
    if _img.size != (1920, 1080):
        continue
    _checked_1920 += 1
    try:
        if not ensure_stream.looks_like_ui(_img):
            continue
    except Exception:
        continue
    _tripped_ui += 1
    if not ensure_stream._game_visible(_img):
        _false_negatives.append(_p)

check(_checked_1920 > 500,
      f"only {_checked_1920} 1920x1080 fixtures scanned -- too few to trust "
      f"a zero-false-negative claim")
check(_tripped_ui >= 8,
      f"only {_tripped_ui} fixtures tripped looks_like_ui, expected at "
      f"least 8 (the population measured when this test was written -- see "
      f"agent_progress/issues/I-05a/progress.md for the full list)")
check(len(_false_negatives) == 0,
      f"{len(_false_negatives)} 1920x1080 fixture(s) trip looks_like_ui and "
      f"NONE of ensure_stream._game_visible's readers recognise them as the "
      f"game -- these would false-fire the liveness gate mid-match: "
      f"{_false_negatives}")


# =========================================================================
# M2 (HOLE 2, skeptic review of 3731b5e): AN INTERRUPTED run of misses must
#    NOT accumulate across the interruption. Three batches of misses
#    separated by two real "hit" frames -- if the hit branch's reset
#    (`liveness_miss_since = None`) is intact, each batch restarts from zero
#    and none of the three individually reaches LIVENESS_MISS_SEC, so the
#    gate never fires. If the reset is REMOVED (the mutant this guards
#    against), `liveness_miss_since` stays pinned to the very first miss and
#    elapsed keeps growing straight through the hits, crossing the threshold
#    partway through the second batch.
#
#    Same motion=True trick as scenario 2, for the same reason: keep every
#    non-firing poll (hit or miss) off the unrelated unrecognized-screen
#    budget so this measures only the reset behaviour.
# =========================================================================
_M2B_MISS_BATCH = int(o.LIVENESS_MISS_SEC / 0.2 / 2)  # well under one threshold alone
_m2b_miss = Image.new("RGB", (1920, 1080), (40, 40, 40))
_m2b_frames = ([_m2b_miss] * _M2B_MISS_BATCH + [world_img] +
              [_m2b_miss] * _M2B_MISS_BATCH + [world_img] +
              [_m2b_miss] * _M2B_MISS_BATCH + [world_img])
h5 = Harness([], liveness_frame=_m2b_frames, ban_counter=None,
             motion=[True] * (len(_m2b_frames) + 10))
buf5 = io.StringIO()


def _go5():
    with contextlib.redirect_stdout(buf5):
        h5.run(target_wins=99)


_, ensure_live_calls5 = _with_recorded_ensure_live(_go5)
out5 = buf5.getvalue()

check(ensure_live_calls5 == 0,
      f"M2 (miss/hit/miss/hit/miss): ensure_stream.ensure_live() was called "
      f"{ensure_live_calls5}x -- a hit between batches of misses must reset "
      f"the debounce, so no batch alone should ever reach the threshold")
check("not looking at the game" not in out5,
      "M2 (miss/hit/miss/hit/miss): the gate fired even though every batch "
      "of misses was interrupted by a real game frame before reaching "
      "LIVENESS_MISS_SEC on its own")


# =========================================================================
# M5 (HOLE 2, skeptic review of 3731b5e): ensure_live()'s RETURN VALUE must
#    gate whether the reader sweep continues for the rest of a stall. A
#    persistent ambiguous frame that never resolves, compared across two
#    arms that differ only in what the stubbed ensure_live() returns.
#
#    h.fast_grab_calls counts every _fast_grab() call the liveness check
#    itself makes (see _run_harness.py). On a False return
#    (liveness_recovery_failed), run()'s own top-of-loop short-circuit
#    (orchestrator.py, "already failed" branch) skips the capture entirely
#    for every remaining poll of the stall -- so fast_grab_calls should
#    plateau right after the first fire. On a True return, nothing skips the
#    capture, so it keeps growing roughly one per poll until
#    MAX_STUCK_ATTEMPTS ends the stall. The comparison is deliberately
#    RELATIVE (True arm clearly higher than False arm) rather than pinned to
#    an exact count, so it does not have to be hand-recomputed every time
#    LIVENESS_MISS_SEC or MAX_STUCK_ATTEMPTS changes.
# =========================================================================
def _with_ensure_live_returning(value, fn):
    calls = {"n": 0}
    real = ensure_stream.ensure_live

    def fake(*a, **k):
        calls["n"] += 1
        return value
    ensure_stream.ensure_live = fake
    try:
        result = fn()
    finally:
        ensure_stream.ensure_live = real
    return result, calls["n"]


_m5_persistent = Image.new("RGB", (1920, 1080), (40, 40, 40))
_M5_MOTION_POLLS = int(o.LIVENESS_MISS_SEC / 0.2) + 10

h_false = Harness([], liveness_frame=_m5_persistent, ban_counter=None,
                  motion=[True] * _M5_MOTION_POLLS)
buf_false = io.StringIO()


def _go_false():
    with contextlib.redirect_stdout(buf_false):
        h_false.run(target_wins=99)


_, ensure_live_calls_false = _with_ensure_live_returning(False, _go_false)

h_true = Harness([], liveness_frame=_m5_persistent, ban_counter=None,
                 motion=[True] * _M5_MOTION_POLLS)
buf_true = io.StringIO()


def _go_true():
    with contextlib.redirect_stdout(buf_true):
        h_true.run(target_wins=99)


_, ensure_live_calls_true = _with_ensure_live_returning(True, _go_true)

check(ensure_live_calls_false == 1,
      f"M5 (ensure_live=False arm): ensure_live() was called "
      f"{ensure_live_calls_false}x, expected exactly 1 -- tried once per "
      f"stall regardless of outcome")
check(ensure_live_calls_true == 1,
      f"M5 (ensure_live=True arm): ensure_live() was called "
      f"{ensure_live_calls_true}x, expected exactly 1 -- a True return must "
      f"not be re-tried on the next fire within the same stall either")
check(h_true.fast_grab_calls > h_false.fast_grab_calls + 5,
      f"M5: fast_grab_calls was {h_true.fast_grab_calls} on the True arm "
      f"against {h_false.fast_grab_calls} on the False arm -- a False "
      f"return must STOP the reader sweep for the rest of the stall (point "
      f"3 of the skeptic's refutation), so the True arm, which keeps "
      f"capturing every poll, should end up well ahead")


# =========================================================================
# COORDINATOR ADDITION (2026-09-21, overnight/run_live_20260921h.log): run()
#    was launched with the console ASLEEP. The first captures are chiaki's
#    own host list (1867x1050, wrong size), and main's run() never called
#    ensure_live -- every poll printed "UNRECOGNISED SCREEN" and after 15
#    polls it stopped with unreadable_screens, never once trying to wake the
#    console. The wrong-size branch is supposed to catch this on the FIRST
#    poll (no debounce for a wrong size, see scenario 1); this pins it as a
#    STARTUP case specifically -- ensure_live must run BEFORE any press, and
#    the wrong-size polls before recovery must not spend the unrecognized-
#    screen budget (they never reach read_state_for_turn at all).
# =========================================================================
_hostlist_img = Image.open(HOSTLIST)
check(_hostlist_img.size != (1920, 1080),
      f"precondition: {HOSTLIST} must NOT be 1920x1080, or this scenario "
      f"is not modelling a wrong-size capture")

# Two independent event streams, merged into one ordered log by APPEND
# ORDER (both append to the same list): ensure_live() calls, and
# read_state_for_turn() calls (wrapping the harness's OWN _next_state, since
# that is what patches["read_state_for_turn"] resolves to at call time --
# see _run_harness.py). This is what lets the assertions below say
# "ensure_live ran before any press AND before any state read", not just
# "ensure_live ran at some point" -- and it is also the precise instrument
# for "the wrong-size polls never reached read_state_for_turn": if they had,
# a "next_state" event would appear in the log BEFORE the sole "ensure_live"
# event, which never happens per orchestrator.py's own structure (the
# wrong-size branch always `continue`s before the read further down the
# loop) but is exactly the shape a regression in that structure would take.
_wake_order = []


def _ensure_live_records_order(*a, **k):
    _wake_order.append(("ensure_live", len(h_wake.presses)))
    return True


h_wake = Harness(_PLAYED + [RESULT_WIN],
                 liveness_frame=[_hostlist_img, _hostlist_img, _hostlist_img,
                                world_img],
                 ban_counter=None)
_real_next_state = h_wake._next_state


def _next_state_records_order():
    _wake_order.append(("next_state", None))
    return _real_next_state()


h_wake._next_state = _next_state_records_order

buf_wake = io.StringIO()
_real_ensure_live = ensure_stream.ensure_live
ensure_stream.ensure_live = _ensure_live_records_order
try:
    with contextlib.redirect_stdout(buf_wake):
        h_wake.run(target_wins=1)
finally:
    ensure_stream.ensure_live = _real_ensure_live
out_wake = buf_wake.getvalue()

check(len(_wake_order) >= 1 and _wake_order[0][0] == "ensure_live",
      f"console-asleep-at-launch: the first liveness/state event was "
      f"{_wake_order[0] if _wake_order else None!r}, expected the FIRST "
      f"event overall to be ensure_live -- the wrong-size branch fires at "
      f"once with no debounce, so recovery must happen before any state "
      f"read, not just before target_wins is reached")
_ensure_live_events = [e for e in _wake_order if e[0] == "ensure_live"]
check(len(_ensure_live_events) == 1,
      f"console-asleep-at-launch: ensure_live() was called "
      f"{len(_ensure_live_events)}x, expected exactly 1 -- tried once per "
      f"stall, and the two later wrong-size polls (recovery already "
      f"succeeded) must not re-trigger it")
if _ensure_live_events:
    check(_ensure_live_events[0][1] == 0,
          f"console-asleep-at-launch: ensure_live() was called after "
          f"{_ensure_live_events[0][1]} press(es) had already landed -- it "
          f"must run BEFORE any press, on the very first poll")
check("Stuck too long off the game screen" not in out_wake,
      "console-asleep-at-launch: the liveness gate's own stuck budget was "
      "exhausted -- recovery should have happened on poll 1")
check(h_wake.next_state_calls > 0,
      f"console-asleep-at-launch: read_state_for_turn was never reached "
      f"({h_wake.next_state_calls}x) after recovery -- the run never "
      f"resumed normal play once the console woke up")


print(f"OK: I-05a liveness gate -- fires at once on a wrong-size capture "
      f"({o.MAX_STUCK_ATTEMPTS} polls), needs {o.LIVENESS_MISS_SEC}s of "
      f"uninterrupted misses on an ambiguous same-size frame (never a raw "
      f"poll count), resets on any interrupting hit (M2), stops re-capturing "
      f"for the rest of a stall once ensure_live fails but not once it "
      f"succeeds (M5), recovers before any press when the console is asleep "
      f"at launch, never fires on a single transient miss, never fires on "
      f"the I-24 control, and the full reader set has zero false negatives "
      f"over {_tripped_ui} looks_like_ui-true fixtures out of "
      f"{_checked_1920} scanned at 1920x1080 ({len(_all_images)} fixture "
      f"images total)")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} liveness-gate failure(s)")
