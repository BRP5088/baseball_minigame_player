"""OPEN-25: start_match must never be pressed for a match this process did not pay for.

`match_in_progress` is loaded from DISK, so the flag being set does not mean
THIS RUN debited -- it can be a previous run's. run()'s C2 recovery block
retries the start_match keystroke without re-debiting, which is right for a
DROPPED PRESS (this process paid, the game did not take the key) and wrong when
this process never paid at all. The branch could not tell the difference.

THE SEQUENCE, all three polls on the same unchanging dealer prompt:

  poll 1  acted_screen is None, so C2 is skipped. C5 sees the stale flag,
          refuses to debit, and ARMS acted_screen = "match_start_prompt".
  poll 2  acted_screen is cleared only when the SCREEN CHANGES, and it did not,
          so C2 is entered. The stale branch proves the flag stale (the world
          HUD is up, and it is never drawn over a match), clears it, persists,
          and promises "the NEXT poll takes the ordinary debit path".
  poll 3  acted_screen is STILL armed, so C2 is entered AGAIN, both
          match_in_progress tests are now False, and control reaches the bare
          press("start_match") -- no debit, no max_spend check, no save.

Measured before the fix: TEN presses, $0 debited, max_spend never consulted.

THE OBVIOUS FIX IS THE WRONG ONE AND WAS MEASURED WRONG. Clearing acted_screen
beside the stale flag -- which the branch's own comment implies -- releases C2's
double-debit guard: 500 -> 200, SIX debits. The latch here cannot loop, because
the debit is what sets it.

Nothing here touches the game, the network or the real progress files: the
harness scripts every seam and `press` is a recorder.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.join(_ROOT, "tests", "minigame"))

from _run_harness import Harness                                  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


POLLS = 12


def trial(stale, max_spend=None):
    """12 polls on an unchanging, GENUINE dealer prompt."""
    h = Harness(["match_start_prompt"] * POLLS, balance=500)
    h.seed["match_in_progress"] = stale
    # The world HUD is on screen. run() treats that as positive proof no match
    # is running, because it is never drawn over one -- it is what makes the
    # stale branch reachable at all.
    h.dealer_prompt = True
    final = h.run(target_wins=99, max_spend=max_spend)
    presses = [p for p in h.presses if p == "start_match"]
    return len(presses), 500 - final["balance"], final


# --- THE BUG: a previous run's flag must not buy a free press ---------------
presses, debited, final = trial(stale=True)
check(debited == 50,
      f"stale flag: {presses} start_match press(es) debited ${debited}. Each press "
      "takes $50 out of the in-game wallet; anything but one $50 debit means the "
      "record and the wallet have drifted apart, permanently (there is no refund "
      "path anywhere in orchestrator.py).")
check(presses == 0 or debited > 0,
      f"stale flag: {presses} press(es) with ${debited} debited — start_match was "
      "pressed for a match this process never paid for")

# --- max_spend is the cap that OPEN-25 bypassed entirely -------------------
# The unguarded press sits INSIDE the C2 block, which run() reaches before the
# max_spend test, so the cap could not see it. This is the check that would
# have caught the original defect on its own.
presses, debited, final = trial(stale=True, max_spend=0)
check(presses == 0 and debited == 0,
      f"stale flag with max_spend=0: {presses} press(es), ${debited} debited — the "
      "spend cap must be able to stop this path. run_one_match.py's promise that "
      "'no new money is ever spent' rests on it.")

# --- CONTROL: the ordinary debit path is untouched -------------------------
# Without this, every check above is satisfied by a run() that debits nothing
# and presses nothing, which is this project's signature defect.
presses, debited, final = trial(stale=False)
check(debited == 50,
      f"CONTROL no flag: expected exactly one $50 debit, got ${debited} — if this "
      "fails the checks above prove nothing")
check(presses >= 1,
      f"CONTROL no flag: expected at least one start_match press, got {presses}")

# --- CONTROL: this process's OWN flag must survive -------------------------
# The stale branch used to fire on the flag THIS RUN had just set, because it
# only asked whether the flag was set and not who set it. That left
# match_in_progress False on disk during a live paid match — exactly the state
# C5 needs to refuse a second debit.
check(final["match_in_progress"] is True,
      "CONTROL: run() debited and set match_in_progress, then cleared its OWN flag "
      "as 'stale' while the paid match was still live. That is the state C5 relies "
      f"on to refuse a second $50; got {final['match_in_progress']!r}")

# --- the dropped-press retry it must NOT break -----------------------------
# A press the game ignored is retried with the keystroke only -- 15.20% of
# presses are ignored (CLAUDE.md section 5), so this path is routine.
presses, debited, final = trial(stale=False)
check(presses > 1 and debited == 50,
      f"the dropped-press retry must still send the keystroke again WITHOUT paying "
      f"again: got {presses} press(es) for ${debited}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  OPEN-25: start_match is never pressed for a match this process did not "
      "pay for, max_spend can stop it, and the dropped-press retry still works")
