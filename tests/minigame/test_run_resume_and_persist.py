"""run(): what survives a restart, and what it writes down.

One of three files split out of test_run_state_machine.py (see
tests/minigame/_run_harness.py for the harness and for why the split
happened). The concern is STATE THAT OUTLIVES A POLL — everything run()
persists, re-reads on a rerun, resets between matches, or records:

  * progress.json across a stop: resume counts, the win target, N5's logger
    stop event, and QA2-1 (a restart must not discard the win it already paid
    for, since "just rerun the script" is the DESIGNED recovery path)
  * the ban lifecycle: C3 (no re-toggle), B1 (a short or unreadable counter is
    reported, never assumed good), the crash-after-bans rerun,
    bans_done_this_match, once-per-match, re-arming on a genuinely new match,
    and the ban-set integrity guards
  * per-match state that must RESET: QA-L5, where last_phase persisting across
    matches reported a second match's first batter as batter 2
  * the record itself: the match log (misfire detection, a pending matchup
    surviving a brief failed read, runners on base not costing the row) and
    the diagnostics bundle (a stall dumps its trail, a clean stop stays
    silent)
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

# The deal gate is NOT under test here -- test_readable_hand_gate.py drives every one of
# its branches. It is stubbed because it spends REAL WALL CLOCK: it polls the screen until
# the hand reads clean, and a stubbed harness never produces a readable hand, so every turn
# would burn the full POST_PLAY_DEAL_MAX_WAIT and the file would hit the suite's 300 s
# ceiling -- the ceiling censoring the work it slowed down (CLAUDE.md 10.14).
orchestrator.wait_for_hand_deal = lambda *a, **k: True

import orchestrator as o
import input_controller
from decision_engine import PlayerCard

# --- C3: a ban screen that does not dismiss must not re-toggle ----------
# Ban selection is a TOGGLE: a second pass over the same cached collection
# un-bans exactly what it just banned, then re-bans it, forever.
h = Harness(["ban_screen"] * 4)
h.run(target_wins=99)
check(len(h.bans_submitted) == 1,
      f"C3: a ban screen seen 4x submitted bans {len(h.bans_submitted)}x, "
      "expected 1 — the toggle guard is not holding")
check(len(h.bans_submitted[0]) == 3 if h.bans_submitted else False,
      f"C3: expected 3 distinct ban positions, got {h.bans_submitted}")


# --- A BLIND CURSOR MUST NOT MEAN ZERO BANS ------------------------------
# select_bans_verified refuses to toggle a cell it cannot SEE, and that is the right
# refusal when the cursor reads and one target is unreachable: one missing ban beats
# banning a card the engine never chose. It is the wrong answer when the cursor never
# reads at all — it then places NOTHING, and a $50 match starts completely unbanned,
# strictly worse than the dead-reckoned path it replaced.
#
# Found BY this file, not by reasoning: flipping VERIFY_BAN_NAVIGATION on took the six
# ban assertions here from 3 bans to none, because an offline harness has no screen. The
# checks above already go red if the fallback is removed, but they go red saying "the
# toggle guard is not holding", which names the wrong thing. This says what it is.
check([o for o in orchestrator._OBSERVATIONS if o.get("event") == "ban_nav_sensor_blind"],
      "a ban screen whose cursor cannot be read recorded no 'ban_nav_sensor_blind' — "
      "either the fallback did not fire or it fired silently, and a run that bans "
      "nothing has to be visible in the record")

# ...and the probe must not simply ALWAYS fall back, or the verified navigation that
# took a live ban screen from 2 of 3 to 3 of 3 is dead code wearing a flag.
_nav = []
_saved_nav = input_controller.select_bans_verified
input_controller.select_bans_verified = (
    lambda grid, positions, **k: _nav.append(sorted(positions)) or sorted(positions))
try:
    _hseen = Harness(["ban_screen"] * 4, ban_cursor=(0, 0))
    _hseen.run(target_wins=99)
finally:
    input_controller.select_bans_verified = _saved_nav
check(len(_nav) == 1 and not _hseen.bans_submitted,
      f"a READABLE ban cursor took the dead-reckoned path anyway: verified "
      f"navigation ran {len(_nav)}x, dead reckoning {len(_hseen.bans_submitted)}x")
check(not [o for o in orchestrator._OBSERVATIONS
           if o.get("event") == "ban_nav_sensor_blind"],
      "a readable ban cursor was recorded as a blind sensor")


# --- the loop exits when the win target is reached ----------------------
h = Harness((["match_start_prompt"] + _PLAYED + [RESULT_WIN]) * 3)
final = h.run(target_wins=2)
check(final["wins"] == 2,
      f"target_wins=2 ended with {final['wins']} wins — the loop overran "
      "its target")

# --- progress survives a mid-run stop -----------------------------------
# The whole point of progress_file is that a stopped run resumes. A win logged
# before the stop must be on disk.
final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                + ["other"] * 30, wins=4,
                losses=4, draws=1, balance=200).run(target_wins=99)
check((final["wins"], final["losses"], final["draws"]) == (5, 4, 1),
      f"resume state: expected 5/4/1 wins/losses/draws, got {final}")

# --- N5: the screenshot logger is always stopped ------------------------
# It runs on a daemon thread and the loop exits through many paths; the stop
# event is set in a finally so it cannot outlive the run.
class _Ev:
    def __init__(self):
        self.set_called = False

    def set(self):
        self.set_called = True


ev = _Ev()
Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN], logger_stop=ev).run(
    target_wins=1, log_screenshots=True)
check(ev.set_called,
      "N5: the screenshot logger's stop event was never set — the logging "
      "thread outlives the run")



# --- QA2-1: a restart must not discard the win it already paid for -------
# Scoring only a PAID match (QA1-F2) stops a misread overlay fabricating a win.
# But the flag lived in memory, so a restart lost it — and every stall message
# in orchestrator.py ends with "just rerun the script", making restart the
# DESIGNED recovery path. Sequence: pay $50, stall, rerun, and the result
# overlay for the paid match is refused, dismissed, and gone.
_h1 = Harness(["match_start_prompt"] + ["other"] * 20, balance=500)
_mid = _h1.run(target_wins=99, max_spend=500)
check(_mid.get("match_in_progress") is True,
      f"after paying, the progress file says match_in_progress="
      f"{_mid.get('match_in_progress')!r} — a restart cannot know a match was "
      "paid for, so its result will be silently discarded")

# Now "rerun the script" against the result overlay that was still on screen.
# The overlay is repeated because the fresh process has plays_this_match = 0 —
# it cannot know how far the paid match got — so the early-result gate makes
# it re-read before scoring. That is the intended cost of the 2026-09-05 fix,
# and the recovery still has to WORK: the overlay is genuinely still up, so it
# survives the re-reads and the win is kept.
_h2 = Harness([RESULT_WIN] * (_CONFIRM + 1), wins=_mid["wins"],
              losses=_mid["losses"],
              draws=_mid["draws"], balance=_mid["balance"])
_h2.seed["match_in_progress"] = True          # what the previous run persisted
_after = _h2.run(target_wins=99)
check(_after["wins"] == _mid["wins"] + 1,
      f"QA2-1: a rerun scored {_after['wins']} wins vs {_mid['wins']} before — "
      "the genuine win from the already-paid match was thrown away on exactly "
      "the recovery path the tool tells you to take")

# And the inverse still holds: a result with NO paid match is still refused.
_none = Harness([RESULT_WIN] * 3, balance=500).run(target_wins=99)
check(_none["wins"] == 0,
      f"a result overlay with no paid match scored {_none['wins']} wins — the "
      "fabricated-win guard has been lost while fixing the restart case")

# --- B1: a SHORT ban set must be detected, not silently played ------------
# Measured on the cached frames: three of five real ban sequences finished at
# 2/3 and the match started two seconds later anyway. Three paid matches were
# played with a ban set the engine did not choose, and nothing noticed, because
# nothing read the counter. Two comments in the codebase asserted the opposite.
shutil.rmtree(_DIAGTMP, ignore_errors=True)
os.makedirs(_DIAGTMP, exist_ok=True)

_hb1 = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 20,
               balance=500, ban_counter=2)          # only 2 of 3 registered
_hb1.run(target_wins=99, max_spend=500)
_short = [o for o in orchestrator._OBSERVATIONS if o.get("event") == "ban_count_short"]
check(len(_short) == 1,
      f"a 2-of-3 ban set produced {len(_short)} 'ban_count_short' records — the "
      "run must NOTICE that the match is starting with a ban set the engine did "
      "not choose")
if _short:
    check(_short[0].get("placed") == 2 and _short[0].get("wanted") == 3,
          f"short-ban record has the wrong numbers: {_short[0]}")

# A FULL set must not be flagged, or the warning becomes noise and gets ignored.
_hb2 = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 20,
               balance=500, ban_counter=3)
_hb2.run(target_wins=99, max_spend=500)
check(not [o for o in orchestrator._OBSERVATIONS if o.get("event") == "ban_count_short"],
      "a complete 3/3 ban set was flagged as short")

# An UNREADABLE counter must be recorded as unverified, never assumed good.
_hb3 = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 20,
               balance=500, ban_counter=None)
_hb3.run(target_wins=99, max_spend=500)
check([o for o in orchestrator._OBSERVATIONS if o.get("event") == "ban_count_unreadable"],
      "an unreadable ban counter was treated as success — it must be recorded "
      "as NOT VERIFIED, since guessing here is how the 2/3 failures stayed "
      "invisible")

# ...and the run must CONTINUE in every case. Raising would send the caller's
# retry back into the ban branch to re-toggle the bans that DID land.
check(len(_hb1.bans_submitted) == 1,
      f"a short ban set caused {len(_hb1.bans_submitted)} submissions — the "
      "check must report, not retry")
shutil.rmtree(_DIAGTMP, ignore_errors=True)
os.makedirs(_DIAGTMP, exist_ok=True)

# --- AUDIT: a crash after bans must not UN-ban them on rerun -------------
# match_in_progress was persisted but bans_done_this_match was not. A crash
# between placing the bans and finishing the match therefore left "a paid match
# is running" True and "its bans are placed" False — so the rerun re-entered the
# ban branch and toggled the same three cards back OFF, stranding a match that
# had already been paid for with its bans undone.
_h = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 20, balance=500)
_mid = _h.run(target_wins=99, max_spend=500)
check(_mid.get("match_in_progress") is True and _mid.get("bans_done_this_match") is True,
      f"after paying and banning, the progress file says "
      f"match_in_progress={_mid.get('match_in_progress')!r} "
      f"bans_done_this_match={_mid.get('bans_done_this_match')!r} — a rerun "
      "cannot know the bans are already placed")

# The rerun sees the ban screen again and must NOT re-toggle.
_h2 = Harness(["ban_screen"] + ["other"] * 20, wins=_mid["wins"],
              losses=_mid["losses"], draws=_mid["draws"], balance=_mid["balance"])
_h2.seed["match_in_progress"] = True
_h2.seed["bans_done_this_match"] = True
_h2.run(target_wins=99, max_spend=500)
check(len(_h2.bans_submitted) == 0,
      f"AUDIT: a rerun re-submitted bans {len(_h2.bans_submitted)} time(s) for a "
      "match whose bans were already placed — that TOGGLES THEM BACK OFF")

# ...and it must ADVANCE the screen, not merely decline to re-ban. On
# 2026-09-01 a paid match sat on the ban screen for all 15 polls and stopped:
# one of three bans had landed, the counter read failed so nothing noticed, and
# nobody pressed the "PLAY" the screen was displaying the whole time. $50 for
# zero logged turns. Triangle commits the bans as they stand and starts the
# match; it is not the ban toggle, so the no-blind-retry rule does not cover it.
_h3 = Harness(["ban_screen"] * 10 + ["other"] * 10, balance=500)
_h3.seed["match_in_progress"] = True
_h3.seed["bans_done_this_match"] = True
_h3.run(target_wins=99, max_spend=500)
check(_h3.presses.count("pyramid") >= 1,
      f"a stuck ban screen got {_h3.presses.count('pyramid')} PLAY presses — "
      "it waited out the poll budget on a screen it could have advanced, which "
      "is a paid match thrown away")
check(len(_h3.bans_submitted) == 0,
      f"advancing the ban screen re-submitted bans {len(_h3.bans_submitted)} "
      "time(s) — PLAY must commit what is there, never re-toggle")
check(_h3.presses.count("pyramid") <= 5,
      f"sent {_h3.presses.count('pyramid')} PLAY presses over 10 ban screens — "
      "it is hammering a screen that may simply be slow")



# Bans are ONCE PER MATCH — on its own harness, because `h` above contains no
# ban screen at all. Asserting bans_submitted on that harness was vacuously
# true: the guard could be deleted entirely and the check still passed. (QA
# round 2 caught this; it is the same class as LESSONS.md §1.)
hb = Harness(["match_start_prompt"] + ["ban_screen", "turn"] * 60,
             play_results=[(False, None)] * 120, balance=500)
hb.run(target_wins=99, max_spend=500)
check(len(hb.bans_submitted) >= 1,
      "fixture error: this harness must actually reach the ban screen, or the "
      "assertion below proves nothing")
check(len(hb.bans_submitted) <= 2,
      f"QA1-F3: {len(hb.bans_submitted)} ban submissions for ONE paid match — "
      "re-entering the ban branch re-reads the cached collection and toggles "
      "the same three cards back off.")

# ...and a genuinely NEW paid match must be allowed to ban again, or the guard
# would leave every match after the first unbanned.
hb2 = Harness(["match_start_prompt", "ban_screen"] + _PLAYED
              + [RESULT_WIN, "match_start_prompt", "ban_screen"], balance=500)
hb2.run(target_wins=99, max_spend=500)
check(len(hb2.bans_submitted) == 2,
      f"two paid matches submitted bans {len(hb2.bans_submitted)} time(s), "
      "expected 2 — the once-per-match guard is not being re-armed on a new "
      "match, so every match after the first plays unbanned")

# QA-L5. turns_this_half only resets when `phase` CHANGES, and last_phase
# persists across matches — so a second match opening on the same phase the
# previous one ended on carried the old count in, and its first batter was
# reported as batter 2. It is passed into GameState on every turn.
class _CountingHarness(Harness):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.batters_seen = []

    def _play_one_turn(self, state_json, turns_this_half):
        self.batters_seen.append(turns_this_half)
        return super()._play_one_turn(state_json, turns_this_half)


# The result overlay is REPEATED rather than the match being played out to
# MIN_PLAYS_FOR_RESULT, so that the batter indices asserted below stay at
# [0, 1] / [0, ...] and the check keeps reading against literal positions.
hc = _CountingHarness(
    ["match_start_prompt", "turn", "turn"] + [RESULT_WIN] * (_CONFIRM + 1)
    + ["match_start_prompt", "turn", "turn"],
    play_results=[(True, None)] * 6, balance=500)
hc.run(target_wins=99, max_spend=500)
check(hc.batters_seen[:2] == [0, 1],
      f"first match saw batters {hc.batters_seen[:2]}, expected [0, 1]")
check(len(hc.batters_seen) >= 3 and hc.batters_seen[2] == 0,
      f"QA-L5: the second paid match started at batter "
      f"{hc.batters_seen[2] if len(hc.batters_seen) > 2 else 'n/a'} instead of "
      f"0 (full trace {hc.batters_seen}) — half-tracking is carrying across "
      "matches because last_phase never resets")


# A NEW HALF DEALS A FRESH HAND, so the memory of the old one is five wrong cards.
# reset_hand_memory() had exactly two call sites, both in the match_start_prompt
# branch; the phase-change branch called neither. Demonstrated: a batting-half slot
# remembered as secondary 3 -- a BATTER'S SPEED, which the role census says a pitcher
# is never -- stayed live for every pitching turn. Its safety net cannot catch this:
# memory is consulted only for slots the reader CANNOT see, so a readable card never
# audits it.
class _MemoryHarness(Harness):
    """Records what the hand memory held at the start of each turn."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.memory_at_turn = []

    def _play_one_turn(self, state_json, turns_this_half):
        self.memory_at_turn.append((state_json.get("phase"),
                                    dict(orchestrator._hand_memory)))
        # stand in for a card the reader could see and remembered
        orchestrator._hand_memory[3] = PlayerCard("Remembered", 9, 3)
        return super()._play_one_turn(state_json, turns_this_half)


_BAT = {"screen": "turn", "phase": "batting", "your_score": 0, "opp_score": 0,
        "hand": [], "runners": [], "discards_left": 2}
_PIT = dict(_BAT, phase="pitching")
orchestrator._hand_memory.clear()
# THREE _PIT screens for TWO pitching turns, deliberately. run() now RE-READS the
# state after the half reset -- the hand it was about to play was built by
# read_state_for_turn BEFORE the reset, i.e. from the batting half's memory, so
# resetting and playing it anyway protected turns 2-5 and not the first. The
# re-read consumes one extra screen from this harness, which hands out one per
# read_state_for_turn call. See tests/minigame/test_half_boundary_rereads.py.
#
# That test and this one guard DIFFERENT things and both are needed: this one
# observes the MEMORY DICT at play time, which is why it passed for the whole life
# of the ordering bug -- the dict really was empty by then. The hand built from it
# one call earlier was not.
hm = _MemoryHarness(["match_start_prompt", _BAT, _BAT, _PIT, _PIT, _PIT],
                    play_results=[(True, None)] * 4, balance=500)
hm.run(target_wins=99, max_spend=500)
_phases = [p for p, _m in hm.memory_at_turn]
check(_phases[:4] == ["batting", "batting", "pitching", "pitching"],
      f"fixture error: the harness must cross a half boundary, saw {_phases}")
_first_pitch = next((m for p, m in hm.memory_at_turn if p == "pitching"), None)
check(_first_pitch == {},
      f"the first PITCHING turn inherited the batting half's hand memory "
      f"({_first_pitch}) — a new half deals a fresh five, so every remembered slot "
      "is a wrong card, and a remembered secondary of 3 is a batter's speed that no "
      "pitcher has")
# ...and the control: within a half the memory must SURVIVE, or the reader loses the
# occluded-card recovery the memory exists for.
_second_bat = [m for p, m in hm.memory_at_turn if p == "batting"][1:2]
check(_second_bat and _second_bat[0] != {},
      f"CONTROL: the memory was cleared WITHIN a half ({_second_bat}) — that throws "
      "away the occluded-card recovery it exists for")
orchestrator._hand_memory.clear()


# QA1-F8. Guard-suppressed stalls used to break without setting stop_reason, so
# they wrote no bundle and printed the same closing line as a healthy stop —
# from the terminal, indistinguishable from running out of money. Those are the
# states where the observation trail is MOST informative.
shutil.rmtree(_DIAGTMP, ignore_errors=True)
Harness(["match_start_prompt"] + [RESULT_WIN] * 40).run(target_wins=99)
check(glob.glob(os.path.join(_DIAGTMP, "*", "bundle.json")),
      "QA1-F8: a result overlay that never dismisses wrote no diagnostics "
      "bundle — a guard-suppressed stall must still leave a record")
shutil.rmtree(_DIAGTMP, ignore_errors=True)


# --- MISFIRE DETECTION ---------------------------------------------------
# The only signal that a keystroke was dropped during card selection. Card
# selection is N move_right presses then a confirm; a swallowed press stops the
# cursor a card short and plays a card we never chose. The game accepts it, the
# turn resolves, and nothing downstream notices — so this check, and the count
# it feeds, are the entire safety net for the input-timing change.

_INFO = {"phase": "batting", "our_card_name": "Johnny Drawers", "our_power": 7,
         "our_secondary": 1, "our_tactics_bonus": 0, "our_tactics_kind": None,
         "runners_before": 0, "score_before": 0}


def _Reveal(revealed):
    return Harness(["turn"] + ["other"] * 20, revealed=revealed,
                   opp_local=_local(revealed),
                   play_results=[(True, dict(_INFO))])


# our_power in _INFO is 7, so this is the card we played...
_OURS = {"kind": "player", "name": "Johnny Drawers", "power": 7, "secondary": 1}
_THEIRS = {"kind": "player", "name": "Rube Sharp", "power": 4, "secondary": 2}
# WHAT THE OPPONENT READ ACTUALLY RETURNS NOW, and without it these cases drive a
# branch production no longer takes. `revealed` feeds read_matchup_reveal -- the
# PAID model -- and run() wraps that in `if paid_model_allowed() else []`, False
# by default since 2026-09-12. So reveal_cards was [] here no matter what
# `revealed` said, and every one of these turns took the no-opponent branch.
# opponent_from_reveal() is the local rung that replaced it; this is its answer
# for the _THEIRS faceoff above (power 4, no tactics card).
_OPP_LOCAL = {"opp_power": 4, "opp_tactics_bonus": 0, "opp_tactics_kind": None}


def _local(revealed):
    """What opponent_from_reveal() returns for a given faceoff.

    `_ours_power_seen` is OUR side of the reveal, which read_reveal() returns and
    the caller uses to tell a clean turn from a MISFIRE: the row carries the power
    we INTENDED, so if the screen shows a different one the row would pair an
    intended card with someone else's outcome. Index 0 of `revealed` is our side
    in every case below, which is why a _WRONG faceoff models the misfire for free.
    """
    return dict(_OPP_LOCAL, _ours_power_seen=(revealed[0] or {}).get("power"))
# ...and this is a DIFFERENT power, i.e. a card we did not play.
_WRONG = {"kind": "player", "name": "Zachary Lee", "power": 6, "secondary": 2}

# 1. A normal reveal (our card present) is NOT flagged.
h = _Reveal([_OURS, _THEIRS])
h.run(target_wins=99)
check(orchestrator._OBSERVATIONS is not None, "observation buffer missing")
_ev = [o for o in orchestrator._OBSERVATIONS if o.get("event") == "suspected_misfire"]
check(not _ev, f"a clean reveal was flagged as a misfire: {_ev}")

# 2. Our card ABSENT from the reveal IS flagged — this is the dropped
#    keystroke. Note the revealed pair here is what a misfire actually looks
#    like: a card we did not choose, plus the opponent's.
h = _Reveal([_WRONG, _THEIRS])
h.run(target_wins=99)
_ev = [o for o in orchestrator._OBSERVATIONS if o.get("event") == "suspected_misfire"]
check(len(_ev) == 1,
      f"a reveal missing our intended card produced {len(_ev)} misfire records, "
      "expected 1 — dropped keystrokes are undetectable")
if _ev:
    check(_ev[0].get("intended_power") == 7,
          f"misfire record does not carry the played POWER: {_ev[0]} — power is "
          "what the hand provides; names are not on hand cards at all")

# 3. THE LIVE FALSE POSITIVE. Hand cards carry no name — the vision model
#    returns the type banner ("Batter") — so a NAME comparison can never match
#    and flags every turn. Measured live 2026-08-26: 2 of 2 turns, zero rows
#    logged, and the adaptive backoff then slowed the run on its own false
#    alarms. The check matches on POWER, which the hand does provide.
h = _Reveal([dict(_OURS, name="Batter"), _THEIRS])
h.run(target_wins=99)
_ev = [o for o in orchestrator._OBSERVATIONS if o.get("event") == "suspected_misfire"]
check(not _ev,
      "a reveal whose names differ from the hand's type banner was flagged as a "
      "misfire — hand cards have NO name, so name matching flags 100% of turns "
      "and suppresses all logging")

# A suspected misfire must not be LOGGED. QA_VACUOUS: deleting the `raise` at
# the end of the misfire check survives the suite, and the consequence is
# specific — the row still gets written, and because the filter picks "first
# player card that isn't ours", the opponent field holds OUR OWN misplayed card.
# A corrupted row is worse than a missing one: it is indistinguishable from real
# data in the dataset the project exists to build.
shutil.rmtree(_DIAGTMP, ignore_errors=True)
os.makedirs(_DIAGTMP, exist_ok=True)
_mlog = os.environ["BASEBALL_MATCH_LOG"]
if os.path.exists(_mlog):
    os.remove(_mlog)

_Reveal([_WRONG, _THEIRS]).run(target_wins=99)
_rows = []
if os.path.exists(_mlog):
    with open(_mlog) as _f:
        _rows = [json.loads(_l) for _l in _f if _l.strip()]
check(not _rows,
      f"a suspected misfire wrote {len(_rows)} row(s) to the match log: "
      f"{[r.get('opp_card_name') for r in _rows]}. On a misfire the 'opponent' "
      "field holds OUR OWN misplayed card, so the row is corrupt and "
      "indistinguishable from real data.")

# ...while a clean turn still logs normally, or the guard has eaten the dataset.
if os.path.exists(_mlog):
    os.remove(_mlog)
_Reveal([_OURS, _THEIRS]).run(target_wins=99)
_clean = []
if os.path.exists(_mlog):
    with open(_mlog) as _f:
        _clean = [json.loads(_l) for _l in _f if _l.strip()]
# PINNED ON THE POWER, NOT THE NAME. The name came from the PAID reveal's
# `opponent_card.get("name")`, and that reader has been off since 2026-09-12;
# opponent_from_reveal() reads the opponent's DISC, so a local row legitimately
# carries opp_power with opp_card_name None. Section 3 is explicit that a card
# cannot be matched by name anyway -- "Hand cards do not display a name ...
# match on POWER" -- so asserting the name here was pinning the one field the
# shipped path cannot produce. The power is what every analysis actually uses.
check(len(_clean) >= 1 and _clean[0].get("opp_power") == 4,
      f"a CLEAN turn logged {len(_clean)} row(s) "
      f"({[r.get('opp_power') for r in _clean]}) — the misfire guard is "
      "suppressing good data too")

# --- SELF-DIAGNOSING EXIT ------------------------------------------------
# A stall must say everything it knew, and a clean stop must NOT litter.
_DIAG = _DIAGTMP
shutil.rmtree(_DIAG, ignore_errors=True)

# 1. A stall writes a bundle naming the reason, with the observation trail.
Harness(["turn"] + ["other"] * 40).run(target_wins=99)
bundles = sorted(glob.glob(os.path.join(_DIAG, "*", "bundle.json")))
check(len(bundles) == 1, f"stall wrote {len(bundles)} diagnostic bundles, expected 1")
if bundles:
    with open(bundles[0]) as f:
        b = json.load(f)
    check(b.get("reason") == "unrecognized_screen",
          f"bundle reason was {b.get('reason')!r}, expected 'unrecognized_screen'")
    check(len(b.get("observations", [])) > 5,
          f"bundle captured {len(b.get('observations', []))} observations — too few "
          "to diagnose anything")
    check(b["observations"][0].get("screen") == "turn",
          "the observation trail does not start where the run did — the buffer "
          "is not recording what the loop actually saw")
    for k in ("wins", "balance", "stuck_count", "acted_screen", "motion_skips"):
        check(k in b, f"bundle is missing {k!r} — needed to diagnose a stall")

# 2. A CLEAN stop writes nothing. Reaching the win target, running out of money
#    and hitting the spend cap are all normal outcomes, not faults.
shutil.rmtree(_DIAG, ignore_errors=True)
Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]).run(target_wins=1)
Harness(["match_start_prompt"], balance=12).run(target_wins=99)
# A result between the two prompts, so C5's in-progress flag is cleared and the
# SPEND CAP is what stops the run — a clean exit. (Without the result, C5
# correctly refuses the second debit and the run simply continues, which is not
# the clean-stop case being tested here.)
Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN, "match_start_prompt"]).run(
    target_wins=99, max_spend=50)
check(not glob.glob(os.path.join(_DIAG, "*")),
      "a clean stop wrote a diagnostic bundle — stalls and normal exits are "
      "being conflated")
shutil.rmtree(_DIAG, ignore_errors=True)


# --- a pending matchup survives a BRIEF failed read ----------------------
# The read-failure handler nulled pending_matchup on the very first failure.
# Measured over the 2026-08-26 run: 22 of 29 plays were followed by a failed
# read — 19 by exactly ONE poll, 3 by two, none by more. That is the loop
# re-reading while the next hand deals, well inside the same turn, so the
# outcome is still attributable. The line cost ~76% of that run's rows.
#
# Both directions are asserted. A bound that is merely large would pass the
# first check and fail the second: the mislabel hazard the original comment
# describes is real, it just needs a gap long enough for the opponent to act.
class _FlakyAfterPlay(Harness):
    """turn (play; matchup pending) -> N failed reads -> a scoreable state."""

    fail_polls = 1

    def _next_state(self):
        self.idx += 1
        if self.idx == 1:
            return {"screen": "turn", "phase": "batting", "your_score": 0,
                    "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}
        if self.idx <= 1 + self.fail_polls:
            raise RuntimeError("unreadable screen")
        return {"screen": "other", "phase": "batting", "your_score": 1,
                "opp_score": 0, "hand": [], "runners": [], "discards_left": 2}


def _rows_after(fail_polls):
    rows = []
    real = orchestrator.log_matchup
    orchestrator.log_matchup = lambda row: rows.append(row)
    try:
        h = _FlakyAfterPlay(["turn"], revealed=[_OURS, _THEIRS],
                            opp_local=_local([_OURS, _THEIRS]),
                            play_results=[(True, dict(_INFO))])
        h.fail_polls = fail_polls
        h.run(target_wins=99)
    finally:
        orchestrator.log_matchup = real
    return rows


# LITERAL counts, never orchestrator.MAX_PENDING_READ_FAILURES. Written first
# as `_rows_after(MAX_PENDING_READ_FAILURES)` / `+ 1`, which is the
# self-referential-threshold trap this file already warns about twice: it
# asserts "N survives and N+1 drops" for whatever N happens to be, so it
# passed with the bound at 0 AND at 9 — both of which are the bug. The
# numbers below are the measured behaviour, independent of the constant.
#
#   1 = the dominant real case (19 of 22 post-play failures were exactly one
#       poll, the next hand dealing, unmistakably the same turn)
#   6 = ~12s of dead screen, comfortably long enough for the opponent to act,
#       which is the mislabel hazard the original drop existed to prevent
_survived = _rows_after(1)
check(len(_survived) == 1,
      f"a play followed by ONE failed read logged {len(_survived)} rows, "
      "expected 1 — the pending matchup is dropped on a transient failure, "
      "which is what cost ~76% of the 2026-08-26 run's rows")

_dropped = _rows_after(6)
check(not _dropped,
      "a play followed by SIX failed reads still logged a row — the outcome "
      "is being attributed across a gap long enough for the opponent to act, "
      "so the row may be silently mislabeled rather than merely missing")


# --- runners on base must not cost the row (WIRING, not just the helper) ---
# exclude_runners() worked, its unit test passed, and production still dropped
# every runner-on-base turn — because run() handed pick_opponent_card the
# UNSTRIPPED list. The unit test could not see it: it called the helper with
# the stripped list, a call production never made. This drives run() itself.
# NOT "Rube Sharp" — that is _THEIRS, and a runner sharing the opponent's
# name makes exclude_runners strip both and correctly back off, so the
# fixture would fail for a reason unrelated to the wiring under test.
_RUNNER = {"name": "Joel Blunt", "power": 9, "secondary": 1}
_TURN_WITH_RUNNER = {"screen": "turn", "phase": "batting", "your_score": 0,
                     "opp_score": 0, "hand": [], "discards_left": 2,
                     "runners": [_RUNNER]}


def _rows_with_runner_on_base():
    rows = []
    real = orchestrator.log_matchup
    orchestrator.log_matchup = lambda row: rows.append(row)
    try:
        # The reveal carries the faceoff PLUS the runner, which is what the
        # game actually renders: 2 faceoff cards + one per runner on base.
        h = Harness([_TURN_WITH_RUNNER, dict(_TURN_WITH_RUNNER, screen="other",
                                             your_score=1)] + ["other"] * 8,
                    revealed=[dict(_OURS), dict(_THEIRS),
                              {"kind": "player", "name": "Joel Blunt",
                               "power": 9, "secondary": 1}],
                    opp_local=_local([_OURS, _THEIRS]),
                    play_results=[(True, dict(_INFO, runners_before=1))])
        h.run(target_wins=99)
    finally:
        orchestrator.log_matchup = real
    return rows


_with_runner = _rows_with_runner_on_base()
check(len(_with_runner) == 1,
      f"a turn played with a runner on base logged {len(_with_runner)} rows, "
      "expected 1 — the runner is still being counted as a revealed card, so "
      "the opponent cannot be identified and the whole turn is discarded")
if _with_runner:
    check(_with_runner[0].get("opp_card_name") != "Joel Blunt",
          "the BASE RUNNER was logged as the opponent's card — worse than "
          "dropping the row, this silently corrupts the dataset")


# --- the ban-set integrity guards must actually guard (V8) ---------------
# Three separate checks — len(bans) != 3, the N15 duplicate-object guard, and
# the N1 position-mapping guard — could each be replaced with `if False:` and
# the ENTIRE suite stayed green. The only ban assertion was a COUNT, fed by a
# harness whose collection is 5 distinct cards at 5 distinct positions, so the
# happy path could never trip any of them.
#
# What they exist for: KNOWN_BAN_ROSTER shares PlayerCard OBJECTS, so a
# mis-resolved read genuinely puts the same object at two grid positions.
# choose_bans can then return [X, X, B] — three entries, two real cards — and
# the run would ban a card the engine never chose.
# The shared card must be WEAK, or choose_bans (which bans the weakest) never
# selects it and the duplicate path is not exercised at all — the first
# version of this fixture made it a power 8 and the run happily banned the
# other three cards.
_shared = PlayerCard("Shared Card", 4, 0)
_dupe_grid = [(0, 0, _shared), (0, 1, _shared),
              (0, 2, PlayerCard("Other", 7, 1)),
              (0, 3, PlayerCard("Third", 8, 1)),
              (0, 4, PlayerCard("Fourth", 9, 1))]
h = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 8,
            ban_collection=_dupe_grid)
h.run(target_wins=99)
check(not h.bans_submitted,
      f"bans were submitted from a grid holding the SAME card object at two "
      f"positions: {h.bans_submitted}. That bans 2 real cards plus a wrong "
      "one, silently.")

# A collection too small to choose 3 bans from must also refuse.
h = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 8,
            ban_collection=[(0, 0, PlayerCard("Only", 9, 1)),
                            (0, 1, PlayerCard("Two", 8, 1))])
h.run(target_wins=99)
check(not h.bans_submitted,
      f"bans were submitted from a 2-card collection: {h.bans_submitted}")

# NOTE on the other two guards. `len(bans) != 3` and `len(banned_positions)
# != 3` both SURVIVE deletion even with these fixtures, and that is genuine
# REDUNDANCY rather than a gap: banned_positions is built by identity-matching
# each ban to exactly one grid slot, so a collection too small to yield 3 bans
# trips both checks, and a ban absent from the grid cannot arise from
# choose_bans (which selects out of that same grid). Only the N15 duplicate
# guard is independently reachable, which is why only it has a killing test.
# Left in place as belt-and-braces; do not delete them on the strength of a
# surviving mutation alone.

# ...and the ordinary grid must still submit exactly 3, or the guards above
# would pass by refusing everything.
h = Harness(["match_start_prompt", "ban_screen"] + ["other"] * 8)
h.run(target_wins=99)
check(h.bans_submitted and len(h.bans_submitted[0]) == 3,
      f"a clean 5-card grid no longer submits 3 bans: {h.bans_submitted}")



print("OK: run() resume and persistence — target exit, resume state, N5 "
      "(logger stopped), QA2-1 (a rerun keeps the win it paid for), C3 (no "
      "ban re-toggle), B1 (short/unreadable ban counter reported), "
      "bans_done_this_match across a crash, once-per-match bans and their "
      "re-arm, QA-L5 (half-tracking resets between matches), misfire "
      "detection and the match log (clean pass, dropped keystroke caught, "
      "case-safe, pending matchup, runners on base), the ban-set integrity "
      "guards, and diagnostics (a stall dumps its trail, a clean stop stays "
      "silent)")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} run() resume/persistence failure(s)")
