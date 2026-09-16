"""No irreversible press while a card the engine did not choose is (or may be) lifted.

Two QA round 4 findings, one fix.

  AN UNMEASURED LIFT READ AS 'DOWN'. selected_cards() skips a row whose y could not
  be measured, which scores an ABSTENTION as the value "this card is not selected".
  The stray check is computed from that same list, so a card that is really raised
  but unreadable is not in `extra`, is never put back down, and goes in with the
  commit. And SELECTING A CARD IS WHAT MAKES IT UNREADABLE -- local_hand's own
  comment: "A RAISED CARD'S DISC SHRINKS OUT OF DISC_MIN_R ... thr 130 r=13 --
  under DISC_MIN_R 18, rejected." So the unknown state is not rare here; it is the
  state the guard exists for. _look_settled cannot catch it either: its gate is
  `any(y is not None for y in ys)`, which passes on a read where only SOME measured.

  THE DISCARD PATH HAD NO STRAY CLEARING AT ALL. The play path computed
  `extra = lifted - want` and walked to every stray before confirm_play, refusing if
  it could not. select_and_discard went straight from _select_verified to
  confirm_discard. That is the same asymmetry behind the 2026-09-16 incident: the
  play path hardened, the discard path left with an unverified irreversible press.
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


N = ic.MAX_HAND_SIZE


def looker(ys, sel):
    return lambda: ([0.0] * N, list(ys), N, list(sel))


saved = {n: getattr(ic, n) for n in
         ("press", "invalidate_cursor", "_walk_cursor_to", "_deselect_verified")}
pressed = []
try:
    ic.press = lambda a, *r, **k: pressed.append(a)
    ic.invalidate_cursor = lambda *a, **k: None
    ic._walk_cursor_to = lambda s, look: (True, [])
    ic._deselect_verified = lambda s, look: (True, [])

    # 1. EVERY y MEASURED, only the wanted card lifted -> safe. This is the CONTROL,
    #    and it comes first: without it every refusal below could be a function that
    #    refuses unconditionally, which would be a worse bug than the one fixed.
    ok = ic._clear_strays({2}, looker([10, 10, 40, 10, 10], [2]))
    check(ok is True, f"CONTROL: all lifts measured, only slot 2 up -> commit ({ok})")

    # 2. One lift UNMEASURED -> refuse, even though `sel` looks clean.
    ok = ic._clear_strays({2}, looker([10, None, 40, 10, 10], [2]))
    check(ok is False,
          f"an UNMEASURED lift refuses the commit ({ok}) — `sel` said only slot 2 "
          "was up, and slot 1's lift was never read")

    # 3. A stray that CAN be put down -> cleared, then safe. The second read must
    #    show it down, so the looker flips after the first call.
    reads = [([0.0] * N, [10, 40, 40, 10, 10], N, [1, 2]),
             ([0.0] * N, [10, 10, 40, 10, 10], N, [2])]
    it = iter(reads)
    last = [reads[-1]]

    def flipping():
        try:
            return next(it)
        except StopIteration:
            return last[0]

    ok = ic._clear_strays({2}, flipping)
    check(ok is True, f"a clearable stray is put down and the commit proceeds ({ok})")

    # 4. A stray that will NOT go down -> refuse.
    ic._deselect_verified = lambda s, look: (False, [])
    ok = ic._clear_strays({2}, looker([10, 40, 40, 10, 10], [1, 2]))
    check(ok is False, f"a stray that will not clear refuses the commit ({ok})")
    ic._deselect_verified = lambda s, look: (True, [])

    # 5. The wanted card NOT lifted -> refuse a partial commit.
    ok = ic._clear_strays({2}, looker([10, 10, 10, 10, 10], []))
    check(ok is False, f"nothing lifted refuses a partial commit ({ok})")

    # --- and the DISCARD path must run it before its irreversible press ----------
    # A stray is up and cannot be cleared, so confirm_discard must never be sent.
    ic._deselect_verified = lambda s, look: (False, [])
    pressed.clear()
    more = {n: getattr(ic, n) for n in ("_select_verified",)}
    try:
        ic._select_verified = lambda t, look: (True, [1, 3])
        out = ic.select_and_discard(3, look=looker([10, 40, 10, 40, 10], [1, 3]))
    finally:
        for n, v in more.items():
            setattr(ic, n, v)

    check(out is False, f"select_and_discard REFUSES with an uncleatable stray ({out})")
    check("confirm_discard" not in pressed,
          f"...and never sent the irreversible press: {pressed}")
finally:
    for n, v in saved.items():
        setattr(ic, n, v)

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
