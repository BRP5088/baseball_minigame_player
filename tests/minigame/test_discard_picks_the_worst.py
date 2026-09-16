"""The discard must throw the WORST card, not whichever weak card sits lowest.

The same tie-blindness fdd1737 removed from choose_bans, in the function
should_redraw's own docstring names as its partner ("discarding the WORST card in
orchestrator.py ... the two rules must move together").

    _weakest = min(players, key=lambda ip: ip[1].power)

`min` returns the FIRST minimum and `players` is built in hand-index order, so a
power tie was resolved by SLOT ORDER. With a 4/3 and a 4/1 in hand it threw
whichever sat lower -- burning one of the half's TWO discards on the better card
half the time. QA round 4 reached it on 2.8% of 285 real hand-labelled hands.

Nothing on disk distinguished the cases: the log line "discarding the weakest
(power 4)" is true of both candidates.

This drives the SHIPPED play_one_turn. A test that re-evaluates a COPY of the
min() expression passes no matter what the real one says.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def card(idx, power, secondary):
    return {"kind": "player", "name": None, "power": power,
            "secondary": secondary, "hand_index": idx}


def discarded_slot(hand):
    """Run the real play_one_turn and return the slot it threw."""
    thrown = []
    # STUB THE CAPTURES TOO. The PLAY branch reaches _grab_settle_regions and
    # capture_diamond_at_play, and with no game window game_capture.grab() falls
    # back to a FULL-SCREEN grab -- i.e. a test that photographs the user's
    # desktop. CLAUDE.md records that exact fallback logging the user's own work
    # for 247 frames. Caught here by reading the test's output instead of only
    # its PASS lines.
    saved = {n: getattr(o, n) for n in
             ("select_and_discard", "forget_hand_slot", "hand_cursor_look",
              "select_and_play", "record_observation", "_grab_settle_regions",
              "stash_hand_baseline", "capture_diamond_at_play")}
    try:
        o.select_and_discard = lambda idx, **k: thrown.append(idx) or True
        o.forget_hand_slot = lambda *a, **k: None
        o.hand_cursor_look = lambda *a, **k: None
        o.select_and_play = lambda *a, **k: True
        o.record_observation = lambda **k: None
        o._grab_settle_regions = lambda *a, **k: {"hand": None}
        o.stash_hand_baseline = lambda *a, **k: None
        o.capture_diamond_at_play = lambda *a, **k: None
        o.play_one_turn({"hand": hand, "phase": "batting", "your_score": 0,
                         "opp_score": 0, "discards_left": 2, "runners": [],
                         "batters_used": None}, 0)
    finally:
        for n, v in saved.items():
            setattr(o, n, v)
    return thrown[0] if thrown else None


# The 4/1 is the worse card in BOTH orders -- a batter's speed 1 advances one base
# where speed 3 advances three. Which SLOT it sits in must not change the answer.
a = discarded_slot([card(0, 4, 3), card(1, 4, 1)])
b = discarded_slot([card(0, 4, 1), card(1, 4, 3)])

check(a == 1, f"4/3 in slot 0, 4/1 in slot 1 -> throws slot {a} (want 1, the 4/1)")
check(b == 0, f"4/1 in slot 0, 4/3 in slot 1 -> throws slot {b} (want 0, the 4/1)")
check(a is not None and b is not None and a != b,
      "the thrown SLOT follows the card, not the position "
      f"(got {a} and {b}; power-only gives 0 both times)")

# Power still dominates the tie-break: a 4/3 goes before a 5/0.
c = discarded_slot([card(0, 5, 0), card(1, 4, 3)])
check(c == 1, f"power still outranks secondary: throws slot {c} (want 1, the 4)")

# CONTROL. Without this the checks above pass on a play_one_turn that never
# discards at all -- every one of them would read None == None.
d = discarded_slot([card(0, 9, 2), card(1, 8, 1)])
check(d is None,
      f"CONTROL: a STRONG hand discards nothing (got slot {d}), so the checks "
      "above are reading a discard that really happened")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
