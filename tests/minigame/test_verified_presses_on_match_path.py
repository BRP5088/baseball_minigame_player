"""I-11: the three presses on the match path LOOK after themselves now.

WHY. Section 5 measured the console on a live ban screen, 1,000 presses, every
one confirmed against chiaki's own instrumented log before being scored: 15.20%
were DELIVERED AND IGNORED BY THE GAME, zero were lost on the way. No delay,
event source or faster retry prevents that -- the only remedy is to look and
press again. `input_controller.press_verified` is that loop and it shipped with
ZERO production callers, so `close_result`, `start_match` and `confirm_play`
were each verified only by the NEXT POLL, sharing `stuck_count` with
unrecognised screens. RULES.md section 1 records confirm_play being ignored
TWICE IN A ROW live on 2026-09-20.

WHAT EACH CHECK IS. Every site gets the same three:

    the press LANDS first time      the ordinary case; exactly one press
    the FIRST press is DROPPED      the game ignored it, so press again -- and
                                    this is the whole point of the change
    it NEVER lands                  the CONTROL: stop at PRESS_VERIFY_TRIES,
                                    report failure, and never claim success

AND THE MONEY CHECK IS THE ONE THAT MATTERS. `start_match` is the press that
spends $50. Verification adds KEYSTROKES, never debits -- the retry sends the
key only, which is what tests/minigame/test_run_debit_and_scoring.py already
pins -- so every start_match scenario below asserts the closing BALANCE, and a
debit-per-retry mutant moves it by $50 a press.

Nothing here touches the game, the network or the real progress files: the run
harness scripts every seam and `press` is a recorder (in BOTH modules, because
press_verified calls input_controller's `press`, not orchestrator's).
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.join(_ROOT, "tests", "minigame"))
# BEFORE any project import. _run_harness sets it too, but a file that relies
# on another file's side effect is one refactor from sending real keystrokes --
# tests/harness/test_every_test_sets_the_flag.py requires it here.
_os.environ["BASEBALL_TEST_RUN"] = "1"

from _run_harness import Harness, RESULT_WIN, _PLAYED              # noqa: E402
import input_controller as ic                                      # noqa: E402

fails = []


def check(cond, msg):
    # COND FIRST. CLAUDE.md counts NINE check() signatures across this suite,
    # roughly evenly split between name-first and cond-first, and a reversed
    # call lands the MESSAGE in the `ok` slot where a non-empty string is
    # truthy -- a check that cannot fail on any input, ever.
    print(f"{'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        fails.append(msg)


TRIES = ic.PRESS_VERIFY_TRIES


# =========================================================================
# (a) close_result -- observe: read_result says the banner is GONE
# =========================================================================
#
# One result screen, then screens run out and the harness yields "other"
# forever, so close_result is pressed in exactly ONE poll and the counts below
# are that poll's.

def close_result_trial(drops):
    h = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN],
                balance=500, drop_presses={"close_result": drops})
    h.dealer_prompt = True
    h.run(target_wins=99)
    return h.presses.count("close_result")


n = close_result_trial(0)
check(n == 1, f"close_result that lands is pressed ONCE ({n})")

n = close_result_trial(1)
check(n == 2,
      f"close_result IGNORED once is pressed again and then stops: expected 2, got {n}. "
      "Before I-11 a dropped close_result was never retried within the poll -- the "
      "result overlay simply stayed up and the C1 guard counted toward MAX_STUCK_ATTEMPTS")

n = close_result_trial(99)
check(n == TRIES,
      f"CONTROL: a close_result the game NEVER takes stops at PRESS_VERIFY_TRIES "
      f"({TRIES}), it does not press forever and it does not report success; got {n}")


# =========================================================================
# (b) start_match -- observe: the ban screen answers, or the dealer prompt is gone
# =========================================================================
#
# THE DEBIT GUARDS ARE UNTOUCHED AND THESE CHECKS ARE WHAT SAYS SO. The debit
# happens BEFORE the press, once, and `debited_this_process` is what lets the
# C2 block retry the keystroke on a later poll without paying again. So the
# balance is a function of the number of DEBITS and never of the number of
# PRESSES, at any drop rate.

def start_match_trial(drops, polls=1):
    h = Harness(["match_start_prompt"] * polls, balance=500,
                drop_presses={"start_match": drops})
    # The world HUD is up -- positive proof no match is running, which is what
    # makes the C2 keystroke-only retry on poll 2 reachable.
    h.dealer_prompt = True
    final = h.run(target_wins=99)
    return h.presses.count("start_match"), final["balance"]


n, bal = start_match_trial(0)
check(n == 1, f"start_match that lands is pressed ONCE ({n})")
check(bal == 450, f"...and debits exactly $50 (500 -> {bal})")

n, bal = start_match_trial(1)
check(n == 2,
      f"start_match IGNORED once is pressed again and then stops: expected 2, got {n}")
check(bal == 450,
      f"THE MONEY CHECK: a retried start_match debits $50 ONCE, not once per press. "
      f"Expected 500 -> 450, got {bal}")

n, bal = start_match_trial(99)
check(n == TRIES,
      f"CONTROL: a start_match the game NEVER takes stops at PRESS_VERIFY_TRIES "
      f"({TRIES}); got {n}. start_match is `\\\\`, the same key as confirm_discard, so "
      "an unbounded retry types into whatever the screen really is")
check(bal == 450,
      f"THE MONEY CONTROL: {TRIES} keystrokes for ONE match still debit exactly $50 "
      f"(500 -> {bal}). A debit moved inside the retry loop reads ${50 * TRIES} here")

# TWO polls on the same prompt: poll 1 takes the ordinary debit path, poll 2
# enters the C2 block and retries the KEYSTROKE ONLY. Both presses are verified
# and neither adds a debit.
n, bal = start_match_trial(1, polls=2)
check(n == 3,
      f"the debit poll retries a dropped press (2) and the C2 poll presses once more "
      f"(1): expected 3, got {n}")
check(bal == 450,
      f"...across BOTH polls the wallet moves exactly once (500 -> {bal})")


# =========================================================================
# (c) confirm_play -- observe: the chosen cards have LEFT the fan
# =========================================================================
#
# Driven directly against _verified_select_and_play_inner. The walk and the
# selection have their own tests (test_verified_selection.py); everything
# before the commit is stubbed here so a failure names the commit.

class Fan:
    """The hand as _look_settled sees it. Slot 0 lifts when selected, and the
    whole fan stops reading MAX_HAND_SIZE rows once the play is committed --
    which is what happens live, because the card leaves the hand."""

    def __init__(self, drops):
        self.drops, self.presses = drops, []
        self.selected = self.played = False

    def press(self, action, *a, **k):
        self.presses.append(action)
        if action != "confirm_play":
            return
        if self.drops > 0:
            self.drops -= 1          # delivered, and the game ignored it
        else:
            self.played = True

    def look_settled(self, look):
        if self.played:
            return ([], [10.0] * 4, 4, [])
        return ([], [10.0] * 5, 5, [0] if self.selected else [])

    def select_verified(self, target, look):
        self.selected = True
        return True, [target]


def confirm_play_trial(drops):
    f = Fan(drops)
    saved = {n: getattr(ic, n) for n in
             ("press", "_look_settled", "_walk_cursor_to", "_select_verified",
              "_clear_strays", "invalidate_cursor")}
    ic.press = f.press
    ic._look_settled = f.look_settled
    ic._walk_cursor_to = lambda target, look: (True, [])
    ic._select_verified = f.select_verified
    ic._clear_strays = lambda want, look, blind_before=None, **kw: True
    ic.invalidate_cursor = lambda *a, **k: None
    try:
        ok = ic._verified_select_and_play_inner(0, None, lambda: None)
    finally:
        for name, fn in saved.items():
            setattr(ic, name, fn)
    return ok, f.presses.count("confirm_play")


ok, n = confirm_play_trial(0)
check(ok is True and n == 1,
      f"confirm_play that lands is pressed ONCE and reports the play ({ok}, {n})")

ok, n = confirm_play_trial(1)
check(ok is True and n == 2,
      f"confirm_play IGNORED once is pressed again and the play still reports True: "
      f"expected (True, 2), got ({ok}, {n}). Live on 2026-09-20 it was ignored TWICE "
      "in a row and nothing noticed until the next poll")

ok, n = confirm_play_trial(99)
check(ok is False and n == TRIES,
      f"CONTROL: a confirm_play the game NEVER takes stops at PRESS_VERIFY_TRIES and "
      f"reports FALSE -- nothing was committed, so the caller must re-read rather than "
      f"score a play that never happened. Expected (False, {TRIES}), got ({ok}, {n})")


print()
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  I-11: close_result, start_match and confirm_play are each verified against "
      "the screen, a dropped press is re-sent, a press that never lands stops at the "
      "budget, and start_match debits exactly $50 however many keystrokes it takes")
