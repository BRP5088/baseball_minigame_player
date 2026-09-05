"""run(): the money in and the result out — C1, C2, C5 and the result gate.

One of three files split out of test_run_state_machine.py (see
tests/minigame/_run_harness.py for the harness and for why the split
happened). Everything here is about the two irreversible things run() does:

  * DEBIT a $50 match       (C2, the balance floor, max_spend, C5, QA1-F1,
                             and the dropped-press retry at the real dealer
                             prompt)
  * SCORE a finished match  (C1, N2, the early-result confirm gate, draws vs
                             losses, QA1-F2)

The two are one concern because the guards are wired together: a result
CLEARS the in-progress flag that C5 uses to refuse a second debit, so a
fabricated win and a double payment are the same bug seen from either end.
Drift here is real money and a permanently wrong trophy count.
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
from _run_harness import (Harness, RESULT_DRAW, RESULT_LOSS, RESULT_WIN,
                          _CONFIRM, _PLAYED, check, failures)
import orchestrator
import orchestrator as o

# --- C1: a result screen that does not dismiss must score ONCE -----------
# The original defect: the branch persists win/loss counts, and a result
# overlay that stayed up was re-scored on every poll, inflating the trophy
# count in progress.json permanently.
final = Harness(["match_start_prompt"] + _PLAYED
                + [RESULT_WIN] * 3).run(target_wins=99)
check(final["wins"] == 1,
      f"C1: a result screen seen 3x scored {final['wins']} wins, expected 1 — "
      "the acted_screen guard is not suppressing the re-score")

# The same screen after an INTERVENING screen is a genuinely new match result
# and must score again — otherwise the guard would silently drop real wins.
final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                + ["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                ).run(target_wins=99)
check(final["wins"] == 2,
      f"C1: two results separated by a turn scored {final['wins']}, expected 2 — "
      "the guard is over-suppressing and would lose real wins")


# --- an early 0-0 "result" is a MISREAD, not a finish ---------------------
# Live 2026-08-31: one card played, then "Draw logged". The match had barely
# started; the $50 already paid for it was lost and a draw that never happened
# went into the record. The C5 guard above cannot see this — it only asks
# whether THIS process paid for a match, and it had.
RESULT_ZERO = dict(RESULT_WIN, your_score=0, opp_score=0, result_won=False)

final = Harness(["match_start_prompt"] + [RESULT_ZERO] * o.RESULT_CONFIRM_READS
                ).run(target_wins=99)
check(final["draws"] == 0,
      f"early-0-0: scored {final['draws']} draw(s) from a 0-0 result seen "
      f"{o.RESULT_CONFIRM_READS}x with no plays — it must be re-read, not "
      "believed, or a transition overlay ends a paid match")

# ...but a 0-0 that KEEPS saying 0-0 past the confirmation budget is real and
# must still score, or a genuine 0-0 finish would hang the loop forever.
final = Harness(["match_start_prompt"] + [RESULT_ZERO] * (o.RESULT_CONFIRM_READS + 1)
                ).run(target_wins=99)
check(final["draws"] == 1,
      f"early-0-0: a 0-0 result confirmed {o.RESULT_CONFIRM_READS + 1}x scored "
      f"{final['draws']} draws, expected 1 — the guard must yield to evidence, "
      "not reject 0-0 outright")

# --- THE SAME HOLDS FOR A NON-ZERO RESULT (the removed 0-0 clause) -------
# This check asserted the OPPOSITE until 2026-09-05: "the guard keys on 0-0,
# so a real finish scores immediately". It could, because the condition read
# `... and _scores_all_zero and ...`.
#
# That clause switched the guard OFF across the whole window it was built to
# cover, because mid-match the scoreboard is normally not 0-0. One non-zero
# "result" misread then cleared match_in_progress — the only thing C5 has to
# go on — and the next overlay misread as match_start_prompt debited a SECOND
# $50. Reproduced: $100 for one match plus a fabricated win. Nothing in the
# guard's reasoning was ever about the SCORE; it is about how far into the
# match we are. The 2026-08-31 observation that motivated it merely happened
# to show 0-0.
#
# So a 7-3 result after zero plays must be RE-READ, not believed...
final = Harness(["match_start_prompt"] + [RESULT_WIN] * _CONFIRM
                ).run(target_wins=99)
check(final["wins"] == 0,
      f"early result: a {RESULT_WIN['your_score']}-{RESULT_WIN['opp_score']} "
      f"result seen {_CONFIRM}x with no plays scored {final['wins']} win(s) — "
      "the confirm gate is keying on the SCORE again, which switches it off "
      "for every ordinary mid-match misread and re-opens the double-debit")

# ...and believed once it outlives the confirmation budget, exactly like 0-0.
final = Harness(["match_start_prompt"] + [RESULT_WIN] * (_CONFIRM + 1)
                ).run(target_wins=99)
check(final["wins"] == 1,
      f"early result: a {RESULT_WIN['your_score']}-{RESULT_WIN['opp_score']} "
      f"result confirmed {_CONFIRM + 1}x scored {final['wins']} — the guard "
      "must yield to evidence, not reject a real finish outright")

# ...while a match that has actually been PLAYED skips the wait entirely. The
# gate keys on plays_this_match, so past MIN_PLAYS_FOR_RESULT the very first
# result poll scores — otherwise every genuine finish would pay the delay.
final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                ).run(target_wins=99)
check(final["wins"] == 1,
      f"a result after {len(_PLAYED)} plays scored {final['wins']}, expected 1 "
      "— the gate must key on plays_this_match, not hold up every finish")

# --- N2: "other" must NOT re-arm the guard -------------------------------
# "other" is the catch-all for anything unrecognised, INCLUDING a transient
# misread of the very screen just acted on. Letting it clear acted_screen
# reopens exactly the defect C1 closed.
final = Harness(["match_start_prompt"] + _PLAYED
                + [RESULT_WIN, "other", RESULT_WIN]).run(target_wins=99)
check(final["wins"] == 1,
      f"N2: result/other/result scored {final['wins']} wins, expected 1 — an "
      "'other' misread is re-arming the guard and double-counting the match")

# --- Draws and losses are scored distinctly ------------------------------
# result_won is a bool and cannot tell a draw from a loss; the branch prefers
# the score comparison for exactly that reason.
final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_DRAW]).run(target_wins=99)
check(final["draws"] == 1 and final["wins"] == 0 and final["losses"] == 0,
      f"a tied score scored {final} — expected exactly 1 draw")
final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_LOSS]).run(target_wins=99)
check(final["losses"] == 1 and final["wins"] == 0,
      f"a losing score scored {final} — expected exactly 1 loss")

# --- C2: a match-start prompt that does not dismiss must debit ONCE ------
# This is the money guard. Drift here defeats max_spend, which exists to honour
# a limit lower than the real in-game balance.
final = Harness(["match_start_prompt"] * 4, balance=500).run(target_wins=99)
check(final["balance"] == 450,
      f"C2: a match-start prompt seen 4x left balance {final['balance']}, "
      "expected 450 — the loop is re-debiting $50 per poll")

# --- C2: the balance floor stops the run before debiting -----------------
final = Harness(["match_start_prompt"], balance=12).run(target_wins=99)
check(final["balance"] == 12,
      f"balance floor: started with $12 against a $50 entry and ended with "
      f"${final['balance']} — the loop debited a match it could not afford")

# --- C2: max_spend caps the session independently of balance -------------
# Two starts separated by an intervening screen, so the acted_screen guard
# does not suppress the second — only the cap should.
final = Harness(["match_start_prompt", "turn", "match_start_prompt"],
                balance=500).run(target_wins=99, max_spend=50)
check(final["balance"] == 450,
      f"max_spend: cap was $50 but balance fell to {final['balance']} "
      "(expected 450 — exactly one match)")

# --- C5: NEVER PAY TWICE FOR ONE MATCH ----------------------------------
# Found in live data 2026-08-25, not by reasoning about the code. Paid $50,
# applied 3/3 bans, the match began, and the "ROUND 1" transition overlay was
# classified as match_start_prompt. By then acted_screen was "ban_screen", so
# the C2 guard had already cleared — the loop was one step from debiting a
# second $50 for a match already paid for and already running. Only a
# max_spend=50 cap stopped it, by luck.
#
# This is the exact observed sequence.
final = Harness(["match_start_prompt", "ban_screen", "match_start_prompt"],
                balance=500).run(target_wins=99, max_spend=500)
check(final["balance"] == 450,
      f"C5: paid $50, banned, then a transition overlay read as another "
      f"match_start_prompt — balance fell to {final['balance']}, expected 450. "
      "The loop is paying twice for one match; acted_screen cannot catch this "
      "because the ban screen falls between the two prompts.")

# A genuinely NEW match — after a result is scored — must still be paid for,
# or the guard would deadlock the run after the first match.
final = Harness([RESULT_WIN, "match_start_prompt"] + _PLAYED
                + [RESULT_WIN, "match_start_prompt"],
                balance=500).run(target_wins=99, max_spend=500)
check(final["balance"] == 400,
      f"C5 over-suppression: two matches across two scored results should cost "
      f"$100, balance ended at {final['balance']} (expected 400) — a result "
      "must clear the in-progress flag or no second match is ever paid for")


# --- QA1 REGRESSIONS: the three ways C5 was still wrong ------------------
# All three were found by adversarial QA on 2026-08-25 AFTER C5 shipped, by
# executing scripted screen sequences rather than by reading the code. C5 fixed
# the double-debit and introduced two new defects doing it.

# F1. C5 refused the debit, then C2's recovery path pressed start_match anyway
#     — 15 real keystrokes into a live match, max_spend bypassed because
#     nothing increments `spent`.
h = Harness(["match_start_prompt", "turn"] + ["match_start_prompt"] * 25,
            balance=500)
h.run(target_wins=99, max_spend=500)
_presses = h.presses.count("start_match")
check(_presses <= 2,
      f"QA1-F1: {_presses} start_match presses sent while a paid match was "
      "running. C5 blocks the accounting but must also block the keystroke — "
      "each press is real in-game spend that max_spend never sees.")

# F2. The result->next-debit half of the cycle was unguarded: one misread
#     between two polls of the same result overlay scored the match twice.
#     'match_start_prompt' as the intervening screen also debited $50 — the
#     exact confusion observed live at 17:01:46.
for _mid in ("discard_prompt", "turn", "ban_screen", "other"):
    final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN, _mid, RESULT_WIN],
                    balance=500).run(target_wins=99, max_spend=500)
    check(final["wins"] == 1,
          f"QA1-F2: result -> {_mid} -> result scored {final['wins']} wins for "
          "ONE match. A result must only score a match this process paid for.")
# match_start_prompt is deliberately NOT in that list: it is a genuine second
# payment, so two results after two prompts really are two matches. The
# assertion there is that the money and the wins agree.
final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                + ["match_start_prompt"] + _PLAYED + [RESULT_WIN],
                balance=500).run(target_wins=99, max_spend=500)
check((final["wins"], final["balance"]) == (2, 400),
      f"two paid matches should be 2 wins and -$100, got {final['wins']} wins "
      f"and balance {final['balance']}")


# =========================================================================
# 9. A dropped start_match press at the REAL dealer prompt must be retried.
# =========================================================================
# QA1-F1 above stops start_match being hammered into a LIVE match, where a
# match_start_prompt read is a misread of a ROUND overlay. But it keyed on
# match_in_progress ALONE, so a genuinely dropped press left the run standing at
# the dealer table watching "Baseball Cards [] Play ($50)" for all 15 polls and
# then stopping — observed 2026-09-01, with a diagnostics frame showing the
# quest list, compass and health coin: unmistakably the world.
#
# The dealer's prompt TEXT separates the two cases. Note it must be the prompt,
# not the world HUD: measured 2026-09-01, compass.find_bar() returns non-None on
# EVERY frame including ban and gameplay screens, and read_bearing() returned
# 177.4 on a gameplay turn — a HUD-based guard would have fired start_match into
# a live match, which is exactly the QA1-F1 harm.
h = Harness(["match_start_prompt"] * 12, balance=500)
h.dealer_prompt = True
h.run(target_wins=99, max_spend=500)
_p = h.presses.count("start_match")
check(_p >= 2,
      f"only {_p} start_match press(es) at the REAL dealer prompt — the "
      f"\"Play ($50)\" text is never drawn over a match, so no match can be "
      f"running and a dropped press must be retried rather than stalling out "
      f"the poll budget")
# saves rows are (wins, losses, draws, balance, match_in_progress).
_bal = h.saves[-1][3] if h.saves else None
check(_bal is None or _bal >= 450,
      f"balance fell to {_bal!r} from 500 — the retry must send the KEYSTROKE "
      f"only. Re-debiting on each retry is the C5 double-charge all over again, "
      f"and 12 polls would have taken $600 of a $500 wallet.")

print("OK: run() debit and scoring — C1 (no double-score), N2 (a misread does "
      "not re-arm the guard), the early-result confirm gate (score-independent: "
      "a 7-3 result is re-read too, and MIN_PLAYS_FOR_RESULT is the only "
      "shortcut), draws vs losses, C2 (no double-debit, balance floor, spend "
      "cap), C5 (never pay twice for one match), QA1-F1/F2, and the dropped "
      "start_match press at the real dealer prompt")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} run() debit/scoring failure(s)")
