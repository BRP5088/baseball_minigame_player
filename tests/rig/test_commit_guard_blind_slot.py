"""A PERMANENTLY OCCLUDED CARD MUST NOT DEADLOCK THE COMMIT -- and a card we
just lifted must still stop it.

DEADLOCKED A LIVE MATCH, 2026-09-17. Slot 1's power disc sat under its
neighbour's card for the whole hand, so its lift was unmeasurable forever.
_clear_strays refused whenever ANY y was None, and BOTH commit paths call it
(_verified_select_and_play and select_and_discard). So:

    slot 1 occluded -> dropped from the hand (10.28)
                    -> hand reads weak       -> should_redraw fires
                    -> discard reaches this guard -> refused
                    -> state unchanged       -> next poll decides the same
                    -> forever

Unattended that is 15 stuck attempts and a dead match with $50 spent.

THE FIX IS DIRECTIONAL, AND THE DIRECTION IS THE WHOLE TEST. Selecting a card
is what makes it unreadable (its disc shrinks out of DISC_MIN_R), so the
dangerous case is a slot that WAS measurable and has gone blind SINCE -- that is
something we pressed. A slot already blind before the operation began cannot
have been raised by us. Remove either half and one of the checks below fails.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import input_controller as ic

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def look_for(ys, sel=()):
    """A fan read the guard will accept as usable: full row count, some y measured.

    `sel` MUST include the chosen cards. _clear_strays also refuses a PARTIAL
    selection ("the engine's cards [2] are not all lifted"), so a stub that lifts
    nothing refuses for that reason instead and every check below would pass or
    fail for the wrong one -- which is how a test comes to measure nothing.
    """
    return lambda: ([0] * len(ys), list(ys), len(ys), list(sel))


MEASURED = [196, 160, 102, 150, 216]
OCCLUDED = [196, None, 102, 150, 216]      # slot 1 exactly as the live frame read

# 1. THE DEADLOCK. Slot 1 unreadable from the start -> the commit must proceed.
ok1 = ic._clear_strays({2}, look_for(OCCLUDED, sel=[2]), blind_before={1})
check(ok1 is True,
      f"a slot unreadable BEFORE the operation does not block the commit (got {ok1}) "
      "-- this is the live deadlock")

# 2. THE SAFETY PROPERTY, UNCHANGED. The same read, but the slot was measurable when
# we started, so something we pressed lifted it. Must still refuse.
ok2 = ic._clear_strays({2}, look_for(OCCLUDED, sel=[2]), blind_before=frozenset())
check(ok2 is False,
      f"a slot that goes unreadable DURING the operation still refuses (got {ok2}) "
      "-- a raised card would go in with the commit")

# 3. CONTROL. Without this, checks 1-2 pass against a guard that ignores y entirely.
ok3 = ic._clear_strays({2}, look_for(MEASURED, sel=[2]), blind_before=frozenset())
check(ok3 is True, f"a fully measurable fan commits normally (got {ok3})")

# 4. AND THE BASELINE IS NOT A BLANKET PASS. A slot blind from the start is excused;
# a DIFFERENT slot going blind in the same read is not.
two_blind = [196, None, None, 150, 216]
ok4 = ic._clear_strays({3}, look_for(two_blind, sel=[3]), blind_before={1})
check(ok4 is False,
      f"slot 1 excused but slot 2 newly blind still refuses (got {ok4}) -- the "
      "baseline excuses only the slots it names")

# 5. A STRAY STILL HAS TO COME DOWN. With slot 1 excused, a card that is genuinely
# LIFTED and not chosen must not sail through. It cannot be walked down with a stub
# look, so the guard must refuse rather than commit.
ok5 = ic._clear_strays({2}, look_for(OCCLUDED, sel=[2, 4]), blind_before={1})
check(ok5 is False,
      f"an unchosen LIFTED card still blocks the commit (got {ok5}) -- excusing an "
      "unreadable slot must not excuse a readable raised one")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
