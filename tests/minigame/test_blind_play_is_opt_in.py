"""select_and_play's unverified path must not be reachable by forgetting an argument.

The blind path dead-reckons the walk, presses select_card, presses confirm_play and
returns True with NOTHING READ. On a console measured to drop presses (three
move_rights 0.31 s apart moved the cursor TWO slots) that is the state CLAUDE.md
records: selected slot 0, then DESELECTED slot 0 (select_card is a TOGGLE),
committed nothing, and reported True. 10.1's canonical shape.

Every production caller already passes look=. The defect was the SIGNATURE:
`look=None` made the unverified path the DEFAULT, so the one function that can do
the worst thing on this axis had the blind call as its easiest call.

This does not remove the path -- tests pin its press sequence, and a caller that
genuinely cannot capture the screen has nothing better. It makes reaching it a
STATEMENT rather than an omission.
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


sent = []
saved = {n: getattr(ic, n) for n in
         ("press", "reset_hand_cursor", "_move_cursor_to", "invalidate_cursor",
          "_verified_select_and_play")}
try:
    ic.press = lambda a, *r, **k: sent.append(a)
    ic.reset_hand_cursor = lambda *a, **k: None
    ic._move_cursor_to = lambda *a, **k: None
    ic.invalidate_cursor = lambda *a, **k: None
    ic._verified_select_and_play = lambda c, t, look: "VERIFIED"

    # 1. No look, no opt-in -> REFUSE. And refuse BEFORE pressing anything: a guard
    #    that raises after committing a card has not guarded anything.
    raised = None
    try:
        ic.select_and_play(2)
    except ValueError as e:
        raised = e
    check(raised is not None, "no look= and no allow_blind= RAISES")
    check(sent == [], f"...and sends NO presses before raising: {sent}")

    # 2. The opt-in reaches the same body it always did.
    sent.clear()
    out = ic.select_and_play(2, allow_blind=True)
    check(out is True, f"allow_blind=True still returns True: {out!r}")
    check("select_card" in sent and "confirm_play" in sent,
          f"...and still sends the blind sequence: {sent}")

    # 3. CONTROL. look= must take the VERIFIED path, untouched. Without this the
    #    checks above pass on a function that refuses everything.
    sent.clear()
    out = ic.select_and_play(2, look=lambda *a, **k: None)
    check(out == "VERIFIED",
          f"CONTROL: look= still routes to the verified path, got {out!r}")
    check(sent == [],
          f"CONTROL: the verified path sends nothing through the blind body: {sent}")
finally:
    for n, v in saved.items():
        setattr(ic, n, v)

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
