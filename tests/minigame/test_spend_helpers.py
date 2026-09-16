"""spend_and_play/-discard forget the slot AND take the verified path.

A hand-driven crawl runs ONE PROCESS PER ACTION, so it gets both footguns that
play_one_turn already handles, and it got both live on 2026-09-16:

  * a script that called select_and_play directly left the card it had just
    played in the on-disk hand memory -- "slot 1: MEMORY WAS WRONG (7/0
    remembered, 8/0 read)". The read-audit caught it; a safety net firing every
    turn is a design that is wrong, not one that is safe.
  * a script that omitted `look` took the BLIND branch, which returns True
    unconditionally. It selected slot 0, DESELECTED slot 0 (select_card is a
    toggle), committed nothing, and reported success.

Plain asserts: four incompatible check() signatures live in this suite.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import orchestrator as o
import input_controller as ic

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


calls = []


def fake_play(card_index, tactics_index=None, look=None):
    calls.append({"fn": "play", "card": card_index, "tactics": tactics_index,
                  "look": look})
    return True


def fake_discard(card_index, look=None):
    calls.append({"fn": "discard", "card": card_index, "look": look})
    return True


real_play, real_discard = ic.select_and_play, ic.select_and_discard
try:
    ic.select_and_play, ic.select_and_discard = fake_play, fake_discard

    o._hand_memory.clear()
    o._hand_memory[1] = {"power": "7", "secondary": 0, "art": None}
    o._hand_memory[4] = {"power": "8", "secondary": 1, "art": None}
    o._hand_memory[2] = {"power": "6", "secondary": 0, "art": None}

    ok, why = o.spend_and_play(1, 4)
    want("the play is reported ok", ok is True, str(why))
    want("the spent player slot is forgotten", 1 not in o._hand_memory,
         str(o._hand_memory))
    want("the spent tactics slot is forgotten", 4 not in o._hand_memory,
         str(o._hand_memory))
    want("an untouched slot survives", 2 in o._hand_memory, str(o._hand_memory))

    # THE `look` ARGUMENT IS THE WHOLE POINT. Without it select_and_play blindly
    # dead-reckons and returns True whatever happened.
    want("the play went through the VERIFIED path",
         calls[-1]["look"] is not None, str(calls[-1]))
    want("and it is orchestrator's own screen reader",
         calls[-1]["look"] is o.hand_cursor_look, str(calls[-1]))

    o._hand_memory[3] = {"power": "5", "secondary": 1, "art": None}
    ok, why = o.spend_and_discard(3)
    want("the discard is reported ok", ok is True, str(why))
    want("the discarded slot is forgotten", 3 not in o._hand_memory,
         str(o._hand_memory))
    want("the discard went through the VERIFIED path",
         calls[-1]["look"] is o.hand_cursor_look, str(calls[-1]))

    # A REFUSAL MUST NOT READ AS A PLAY. select_and_play returns False when the
    # cursor could not be confirmed, and that means NOTHING was committed.
    ic.select_and_play = lambda *a, **k: False
    ok, why = o.spend_and_play(0)
    want("a refused play returns False", ok is False, str(ok))
    want("and it says nothing was committed", "NOTHING" in (why or ""), str(why))
finally:
    ic.select_and_play, ic.select_and_discard = real_play, real_discard
    o._hand_memory.clear()

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
