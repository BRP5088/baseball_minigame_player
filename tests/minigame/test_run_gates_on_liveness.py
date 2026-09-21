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
      it requires LIVENESS_MISS_STREAK (3) CONSECUTIVE such polls first, since
      a single miss at a screen transition is expected and not evidence of
      anything (see that constant's comment). Section 3 tests this directly:
      a lone ambiguous frame followed by a real game frame must NOT fire the
      gate at all.

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
# 2: SAME-SIZE, looks_like_ui TRUE, NO READER ANSWERS -- but this is the
#    AMBIGUOUS case, so it needs LIVENESS_MISS_STREAK (3) consecutive misses,
#    not one. The same static frame every poll models "never changes":
#    the first (LIVENESS_MISS_STREAK - 1) polls fall through to a real read
#    (screen "other", harmless), and only from the 3rd miss does the gate
#    start firing -- from then on EVERY poll misses again, so the total
#    'not looking' count still lands on exactly MAX_STUCK_ATTEMPTS, same as
#    scenario 1, just spread over more total polls.
# =========================================================================
h2 = Harness([], liveness_frame=Image.new("RGB", (1920, 1080), (40, 40, 40)),
             ban_counter=None)
buf2 = io.StringIO()


def _go2():
    with contextlib.redirect_stdout(buf2):
        h2.run(target_wins=99)


_, ensure_live_calls2 = _with_recorded_ensure_live(_go2)
out2 = buf2.getvalue()

check(h2.presses == [],
      f"same-size UI frame: the gate pressed {h2.presses!r}")
check(h2.next_state_calls == o.LIVENESS_MISS_STREAK - 1,
      f"same-size UI frame: read_state_for_turn was reached "
      f"{h2.next_state_calls}x, expected exactly LIVENESS_MISS_STREAK - 1 "
      f"({o.LIVENESS_MISS_STREAK - 1}) -- the debounced misses before the "
      f"streak completes")
check(ensure_live_calls2 == 1,
      f"same-size UI frame: ensure_stream.ensure_live() was called "
      f"{ensure_live_calls2}x, expected exactly 1")
# stuck_count is SHARED across every guard in run(), including the
# unrecognized-screen branch the two debounced fall-through polls land on
# (screens=[] yields "other", which spends its own stuck_count budget too --
# see "Unrecognized screen (other), waiting..." in orchestrator.py). So the
# liveness gate's own share of the MAX_STUCK_ATTEMPTS budget is reduced by
# exactly the (LIVENESS_MISS_STREAK - 1) polls that were spent falling
# through before the streak completed -- the run still stops at the SAME
# total stuck_count, just split between two reasons.
_expected_liveness_msgs = o.MAX_STUCK_ATTEMPTS - (o.LIVENESS_MISS_STREAK - 1)
check(out2.count("not looking at the game") == _expected_liveness_msgs,
      f"same-size UI frame: the gate logged 'not looking at the game' "
      f"{out2.count('not looking at the game')} times, expected "
      f"MAX_STUCK_ATTEMPTS - (LIVENESS_MISS_STREAK - 1) "
      f"({_expected_liveness_msgs}) -- stuck_count is shared with the "
      f"unrecognized-screen branch the debounced polls fall through to")
check("Stuck too long off the game screen" in out2,
      "same-size UI frame: no stop message printed")


# =========================================================================
# 3: A SINGLE TRANSIENT MISS MUST NOT FIRE ANYTHING. One ambiguous frame,
#    then a REAL game frame (table_prompt_live.jpg, a genuine world capture)
#    for the rest of the match. This is the direct regression test for the
#    debounce: with LIVENESS_MISS_STREAK wrongly at 1, this scenario fires on
#    poll 1 and calls ensure_live once -- exactly the mutant named in the
#    ticket ("set N to 1, a single-poll transition case must fail").
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


print(f"OK: I-05a liveness gate -- fires at once on a wrong-size capture "
      f"({o.MAX_STUCK_ATTEMPTS} polls), needs {o.LIVENESS_MISS_STREAK} "
      f"consecutive misses on an ambiguous same-size frame, never fires on a "
      f"single transient miss, never fires on the I-24 control, and the "
      f"full reader set has zero false negatives over {_tripped_ui} "
      f"looks_like_ui-true fixtures out of {_checked_1920} scanned at "
      f"1920x1080 ({len(_all_images)} fixture images total)")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} liveness-gate failure(s)")
