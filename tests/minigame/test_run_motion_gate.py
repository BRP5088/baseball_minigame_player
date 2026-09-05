"""run(): the motion gate, and every other bound on "the loop must keep moving".

One of three files split out of test_run_state_machine.py (see
tests/minigame/_run_harness.py for the harness and for why the split
happened). One concern, two directions:

  * SKIP — the motion gate ("no action needed"). Doing nothing while the
    screen animates is a real action, so the gate must be able to skip, must
    never act, must be consulted BEFORE the expensive vision read, must cost
    exactly one check per poll on a still screen, and must fall through on
    MAX_CONTINUOUS_MOTION_WAIT. checks_per_read measures that bound PER
    fall-through, which is the only way it means anything.

  * STOP — the bounds that stop a loop which is no longer progressing: the
    frozen-stream guard (the only one that bounds "the screen never changes at
    all"), N25's stuck counter, N3's bounded discard prompt, QA1-F3's
    screen-independent progress bound, and QA2-4's RESETS of it — a bound that
    fires on a healthy run is strictly worse than the hang it prevents.

Exception absorption lives here too: a raise from read_game_state, from
play_one_turn or from the motion check itself must not end the session, which
is the same question of whether the loop keeps going.
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
# ...and this file's OWN directory, so `_run_harness` imports whether the file
# is run directly, from the project root, or re-executed in a subprocess by
# tests/harness/test_no_side_effects.py.
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))


import glob
import json
import os
import shutil

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
# Set before ANY project import: it is what holds every input path off.
os.environ["BASEBALL_TEST_RUN"] = "1"

# _run_harness FIRST among the project imports. It points
# BASEBALL_DIAGNOSTICS_DIR and BASEBALL_MATCH_LOG at a temp dir and only THEN
# imports orchestrator; importing orchestrator ahead of it would leave a stall
# bundle in the directory a live session watches, and match-log rows in the
# dataset this project exists to collect.
from _run_harness import (Harness, RESULT_WIN, _CONFIRM, _DIAGTMP, _PLAYED,
                          check, failures)
import orchestrator
import orchestrator as o

# --- N3: a discard prompt that does not dismiss is bounded ---------------
h = Harness(["discard_prompt"] * 4)
h.run(target_wins=99)
check(h.presses.count("confirm_play") == 1,
      f"N3: a stuck discard prompt sent confirm_play "
      f"{h.presses.count('confirm_play')}x, expected 1")

# --- N25: turn stuck_count resets only on a CONFIRMED play --------------
# The redraw path returns played=False without consuming a card. With an
# unconditional reset, a discard that never lands resets the counter forever
# and the loop spins without bound. This must terminate.
h = Harness(["turn"] * 200, play_results=[(False, None)] * 200)
h.run(target_wins=99)
check(h.idx <= orchestrator.MAX_STUCK_ATTEMPTS + 2,
      f"N25: {h.idx} turns consumed on a never-playing loop — the stuck "
      f"counter is being reset unconditionally (bound is "
      f"{orchestrator.MAX_STUCK_ATTEMPTS})")

# A loop that DOES play must not trip the stuck counter.
h = Harness(["turn"] * 40, play_results=[(True, None)] * 40)
h.run(target_wins=99)
check(h.idx >= 40,
      f"N25: only {h.idx} of 40 successful turns ran before the loop gave up — "
      "a confirmed play is not resetting the stuck counter")

# --- play_one_turn raising must not kill the run ------------------------
h = Harness(["turn"] * 5, play_results=[RuntimeError("bad vision read")] * 5)
h.run(target_wins=99)
check(h.idx >= 5,
      f"a raising play_one_turn stopped the loop after {h.idx} screens — it "
      "should be retried like any other bad read")

# --- read_game_state raising must not kill the run ----------------------
class _Boom(Harness):
    """Three unreadable screens, then a paid match and its result.

    The match_start_prompt is required now that a result only scores a match
    this process actually paid for (QA1-F2) — without it this would assert that
    exception absorption works by checking a win that could never be scored."""

    def _next_state(self):
        self.idx += 1
        if self.idx <= 3:
            raise RuntimeError("unreadable screen")
        if self.idx == 4:
            return {"screen": "match_start_prompt", "phase": "batting",
                    "your_score": 0, "opp_score": 0, "hand": [], "runners": [],
                    "discards_left": 2}
        return dict(RESULT_WIN)


final = _Boom([]).run(target_wins=1)
check(final["wins"] == 1,
      f"three unreadable screens then a win scored {final['wins']} — an "
      "exception from read_game_state is not being absorbed")


# --- OVERNIGHT_AUDIT #1: a frozen stream must not run forever ------------
# The worst finding of the audit, and the one that only shows up overnight.
# On a stalled Chiaki stream / sleeping PS5 the last frame is maximally STILL:
#   screen_is_moving()  -> False   (a frozen frame does not move)
#   read_game_state()   -> the same valid `turn` payload, forever
#   play_one_turn()     -> (True, ...) forever, because select_and_play() is
#                          just keystrokes, which return normally whether or
#                          not anything is listening
# Both liveness counters reset on that "play", so nothing bounded it. Measured
# at 500 phantom turns — roughly 1,500 API calls and 15,000 keystrokes into a
# dead stream over a night, ending with "input timing looks safe".
#
# Every OTHER guard bounds "the screen keeps changing without progressing".
# This is the only one that bounds "the screen never changes at all".
h = Harness(["match_start_prompt"] + ["turn"] * 2000,
            play_results=[(True, None)] * 2000, balance=500, frozen=True)
h.run(target_wins=99, max_spend=500)
# LITERAL, not orchestrator.MAX_IDENTICAL_FRAMES. Reading the constant means
# the bar moves with the mutation: raising it to 10**9 left this green because
# the assertion compared against 10**9 too. Fourth instance of this exact trap
# in this project (LESSONS.md §1, category (d)).
# The clock is virtual and each poll advances it ~0.2s, so 90s of frozen frames
# is ~450 polls. The bound is TIME, not poll count: at ~0.2s a 12-poll bound was
# only 2.4s, short enough that a genuinely paused game would abort a real run.
check(h.idx <= 600,
      f"AUDIT-1: {h.idx} polls against a byte-identical frozen frame. The loop "
      "plays phantom turns into a dead stream and every liveness counter is "
      "reset by the play itself.")
check(h.idx < 2000,
      "AUDIT-1: the frozen-stream bound never fired at all")

# A PAUSED game is static too, and stopping there would be a false alarm that
# throws away a paid match. Pixels cannot tell "paused" from "dead"; the screen
# CONTENT can, so the bound probes once before giving up. Here the probe returns
# a menu screen, so the run must continue.
class _FrozenButPaused(Harness):
    def _next_state(self):
        # Frozen frames, but the screen is a pause/menu overlay the whole time.
        self.idx += 1
        return {"screen": "other", "phase": "batting", "your_score": 0,
                "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}


# Clear FIRST — the frozen test above legitimately wrote a frozen_stream
# bundle, and asserting on a shared directory without clearing it made this
# check fail on the previous test's artefact. (Test isolation, not a code bug.)
shutil.rmtree(_DIAGTMP, ignore_errors=True)
os.makedirs(_DIAGTMP, exist_ok=True)

hp = _FrozenButPaused(["match_start_prompt"], balance=500, frozen=True)
hp.run(target_wins=99, max_spend=500)
_bundles = glob.glob(os.path.join(_DIAGTMP, "*", "bundle.json"))
_frozen_bundles = []
for _b in _bundles:
    with open(_b) as _f:
        if json.load(_f).get("reason") == "frozen_stream":
            _frozen_bundles.append(_b)
check(not _frozen_bundles,
      "a PAUSED game (static frames, but the screen reads as a menu) was "
      "declared a frozen stream — that false alarm abandons a match that has "
      "already been paid for")
# What it IS diagnosed as, measured: a paused game shows a menu overlay, which
# reads as "other", and the pre-existing unrecognized-screen path stops the run
# after 15 polls — well before the 90s frozen timer could fire. So a pause is
# already bounded and correctly labelled; the probe above is defence in depth
# for the case where a pause somehow survives that path.
check(any(json.load(open(_b)).get("reason") == "unrecognized_screen"
          for _b in _bundles) if _bundles else True,
      f"a paused game produced bundles {[json.load(open(b)).get('reason') for b in _bundles]}, "
      "expected it to be recognised as an unrecognized-screen stall")
shutil.rmtree(_DIAGTMP, ignore_errors=True)
os.makedirs(_DIAGTMP, exist_ok=True)

# A LIVE screen must not be mistaken for a frozen one, or every real match
# aborts at poll 13. (Unpatched, the guard reads the real desktop — which is
# byte-identical between polls — so this direction is the easy one to break.)
h = Harness(["match_start_prompt"] + ["turn"] * 200,
            play_results=[(True, None)] * 200, balance=500, frozen=False)
h.run(target_wins=99, max_spend=500)
check(h.idx >= 150,
      f"AUDIT-1 false positive: a LIVE screen stopped after {h.idx} polls — the "
      "frame-identity guard is firing on ordinary play")


# F3. Two screens that each clear the other's guard looped forever: measured
#     3000 screens and 1500 ban re-toggles with no stall and no diagnostics.
#     Before C5 this was bounded by money; C5 removed the debit and left
#     nothing in its place.
h = Harness(["match_start_prompt"] + ["ban_screen", "match_start_prompt"] * 400,
            balance=500)
h.run(target_wins=99, max_spend=500)
check(h.idx < 200,
      f"QA1-F3: {h.idx} screens consumed alternating match_start_prompt and "
      "ban_screen with no bound. Each screen clears the other's acted_screen "
      "guard, so nothing ever trips MAX_STUCK_ATTEMPTS.")
# The bound must also catch cycles NO per-screen guard sees. discard_prompt
# zeroes stuck_count every time it acts, and a turn whose play_one_turn returns
# played=False neither increments nor resets it (N25 resets only on a confirmed
# play). So the two together advance nothing and trip nothing — this pair is
# caught by the global bound alone.
#
# An earlier version of this test used match_start_prompt <-> ban_screen, which
# the once-per-match ban guard now catches independently: it passed with the
# bound removed entirely.
h = Harness(["match_start_prompt"] + ["discard_prompt", "turn"] * 400,
            play_results=[(False, None)] * 800, balance=500)
h.run(target_wins=99, max_spend=500)
# LITERAL bound, not orchestrator.MAX_POLLS_WITHOUT_PROGRESS. Referencing the
# constant meant the bar moved with the mutation: raising it to 10**9 left this
# green because the assertion compared against 10**9 too. A test must not read
# its threshold from the thing it is testing.
check(h.idx <= 200,
      f"QA1-F3: {h.idx} screens consumed alternating discard_prompt and a "
      "non-playing turn. Neither guard sees this pair — discard_prompt zeroes "
      "stuck_count and a played=False turn leaves it alone — so only the "
      "screen-independent progress bound can stop it.")

# QA2-4. The BOUND is tested; its RESETS were not. Deleting either reset
# survives every other assertion, yet each turns a healthy match into a forced
# abort at poll 121 — the bound firing on a run that is progressing fine is
# strictly worse than the hang it was added to prevent.
h = Harness(["match_start_prompt"] + ["turn"] * 300,
            play_results=[(True, None)] * 300, balance=500)
h.run(target_wins=99, max_spend=500)
check(h.idx >= 250,
      f"QA2-4: only {h.idx} of 300 successfully-PLAYED turns ran before the "
      "loop gave up — a confirmed play must reset polls_without_progress, or a "
      "long healthy match is aborted mid-play")

h = Harness((["match_start_prompt"] + ["turn"] * 100 + [RESULT_WIN]) * 3,
            play_results=[(True, None)] * 400, balance=500)
final = h.run(target_wins=99, max_spend=500)
check(final["wins"] == 3,
      f"QA2-4: three long paid matches scored {final['wins']} wins — a scored "
      "result must reset polls_without_progress, or the second match aborts")


# QA1-F9. The motion gate is the FIRST call every iteration and was the only
# unguarded one. _fast_grab() -> _MSS.grab() fails on display reconfiguration,
# revoked screen-recording permission, or a stale mss handle. Unguarded, one
# raise killed the run mid-match AND wrote no diagnostics (stop_reason stayed
# None), so the session ended with no record of why.
class _MotionRaises(Harness):
    def _screen_is_moving(self, *a, **k):
        self.motion_checks += 1
        raise OSError("mss: display disconnected")


h = _MotionRaises(["match_start_prompt"] + _PLAYED + [RESULT_WIN])
final = h.run(target_wins=1)
check(final["wins"] == 1,
      "QA1-F9: a raising motion check killed the run — it must fall through to "
      "the normal read, not end the session")


# --- MOTION GATE: "no action needed" ------------------------------------
# Doing nothing while the screen animates is a real action. The gate must be
# able to SKIP but must never be able to ACT, and must never stall.

# 1. Motion delays the read; it does not consume a screen or take an action.
h = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN],
            motion=[True, True, True])
final = h.run(target_wins=1)
check(final["wins"] == 1,
      f"motion gate: expected the win to still be scored once motion stopped, "
      f"got {final['wins']}")
check(h.presses.count("close_result") == 1,
      f"motion gate: {h.presses.count('close_result')} close presses, expected 1 "
      "— a skipped poll must not act")

# 2. The skip is BOUNDED. A permanently-animating screen must fall through and
#    be handled by the normal stuck path, not stall the run forever.
#    `motion` is never exhausted here, so the ONLY way out is the timeout —
#    if the bound does not work this test hangs rather than passing.
class _AlwaysMoving(Harness):
    def _screen_is_moving(self, *a, **k):
        self.motion_checks += 1
        self.clock.advance(0.2)
        return True


h = _AlwaysMoving(["match_start_prompt"] + _PLAYED + [RESULT_WIN])
final = h.run(target_wins=1)
check(final["wins"] == 1,
      "motion gate: a permanently-moving screen never reached the vision read — "
      f"MAX_CONTINUOUS_MOTION_WAIT ({orchestrator.MAX_CONTINUOUS_MOTION_WAIT}s) "
      "is not forcing a fall-through")
# LITERAL, not orchestrator.MAX_CONTINUOUS_MOTION_WAIT. Reading the constant
# means the bar moves with the mutation: setting it to 0.001 leaves this green
# because `_expected` shrinks too. FIFTH instance of LESSONS.md §1 category (d)
# in this project — and this file already warns about the trap for two OTHER
# constants a few lines away, then reproduced it here.
#
# 15.0s at ~0.2s per check is ~75 checks; require at least half of that.
# TWO-SIDED. The floor alone left MAX_CONTINUOUS_MOTION_WAIT = 100000.0
# (27 hours) surviving: a bound that never fires means a permanently animating
# screen NEVER reaches the vision read, which is the exact failure the
# fall-through exists to prevent. 15s at ~0.2s per check is ~75; 150 is double
# that and still catches an effectively-infinite bound. Literals on purpose —
# reading the constant under test would make this true for any value.
#
# PER FALL-THROUGH, not as a run total. What the constant bounds is ONE
# continuous run of motion: motion_wait_started is cleared after every
# fall-through, so a run that takes N vision reads legitimately spends N times
# the bound. The old assertions were run TOTALS and only matched the bound
# because this sequence happened to be two screens long — lengthening it by
# the plays a result now needs made the upper one fire on arithmetic rather
# than on behaviour. checks_per_read holds one entry per vision read, so min
# and max below are the eager and loose directions of the SAME bound.
check(h.checks_per_read and min(h.checks_per_read) >= 37,
      f"motion gate: fell through after only {min(h.checks_per_read or [0])} "
      f"checks (~{min(h.checks_per_read or [0]) * 0.2:.1f}s), expected to hold "
      "out for roughly 15s — a bound this eager aborts on ordinary animation")
check(h.checks_per_read and max(h.checks_per_read) <= 150,
      f"motion gate ran {max(h.checks_per_read or [0])} checks "
      f"(~{max(h.checks_per_read or [0]) * 0.2:.1f}s) before one vision read "
      "— a bound this loose never reads the screen at all on a permanently "
      "animating game")

# 3. A still screen must not be skipped at all — the gate costs nothing when
#    there is no motion.
#
# EXACT, not a floor. `h.idx >= 3` was the old bar and it was nearly vacuous:
# the gate consults screen_is_moving() once per iteration, so with no motion
# there is exactly ONE motion check per vision read, and any skipping at all
# shows up as motion_checks running ahead of reads. A floor of 3 out of 4
# screens tolerated that; out of the 12 this sequence now needs it would
# tolerate almost anything.
_still = (["match_start_prompt"] + _PLAYED + [RESULT_WIN]
          + ["match_start_prompt"] + _PLAYED + [RESULT_WIN])
h = Harness(_still, motion=[False] * 10)
h.run(target_wins=2)
check(h.idx >= len(_still),
      f"motion gate: only {h.idx} of {len(_still)} screens consumed with no "
      "motion — the gate is skipping still frames")
check(h.motion_checks == h.idx,
      f"motion gate: {h.motion_checks} motion checks for {h.idx} vision reads "
      "on a screen that never moves — with no motion the gate must cost one "
      "check per poll and skip nothing")

# 4. The gate is consulted BEFORE the vision call, which is the entire point:
#    a skipped poll must cost no API call.
h = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN],
            motion=[True, True, False])
h.run(target_wins=1)
check(h.motion_checks > h.idx,
      f"motion gate: {h.motion_checks} motion checks vs {h.idx} vision reads — "
      "the gate should run more often than the expensive read")


print("OK: run() motion gate and liveness bounds — N3 (bounded discard), N25 "
      "(stuck counter resets only on a confirmed play), exception absorption "
      "(read_game_state, play_one_turn, the motion check itself), "
      "OVERNIGHT_AUDIT #1 (frozen stream bounded, a paused game not mistaken "
      "for one, a live screen not mistaken for one), QA1-F3 (the "
      "screen-independent progress bound), QA2-4 (its resets), and the motion "
      "gate itself (skips, bounded per fall-through, no-op when still, "
      "consulted pre-API)")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} run() motion-gate/bound failure(s)")
