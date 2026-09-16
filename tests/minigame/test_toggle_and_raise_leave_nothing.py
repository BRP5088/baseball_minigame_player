"""Two ways the selection code used to leave the screen wrong and say nothing.

  AN UN-BAN WAS INVISIBLE. select_bans_verified compares banned_set() before and
  after every select_card -- the FULL absolute hit set, which is right -- but only
  inspected `_after - _before`. select_card is a TOGGLE, so a stale-cursor press
  landing on a cell ALREADY banned by an earlier target REMOVES that X. The
  difference is then empty, the code logged "placed no X anywhere -- leaving it",
  on_wrong_ban never fired, and the run finished with fewer bans than it believed.
  Only the DIRECTION differed from the case it does catch.

  A RAISE LEFT A CARD LIFTED. Neither look() nor _look_settled was wrapped, and the
  production look seam is orchestrator.hand_cursor_look -> _grab_settle_regions, a
  LIVE CAPTURE that can raise. A raise after press("select_card") propagated out
  before _unwind_selection or invalidate_cursor could run, so the card stayed up --
  and a lifted stray is what CLAUDE.md 10.29 charges for. select_bans_verified was
  wrapped for this exact shape; the play path was not.
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


class Card:
    def __init__(self, n): self.name = n


GRID = [(r, c, Card(f"c{r}{c}")) for r in range(6) for c in range(5)]

# ---- 1. an UN-BAN is reported and un-counted ------------------------------
# Two targets. The cursor reads as arriving at both, but the SECOND press removes
# the X the first one placed instead of adding its own.
state = {"banned": set(), "presses": 0}
wrong = []


def look2():
    return (0, 0) if state["presses"] == 0 else (1, 1)


def press2(a, *r, **k):
    if a != "select_card":
        return
    state["presses"] += 1
    if state["presses"] == 1:
        state["banned"].add((0, 0))          # the first target lands
    else:
        state["banned"].discard((0, 0))      # the second press UN-bans it


saved = {n: getattr(ic, n) for n in ("press", "time")}


class _T:
    @staticmethod
    def sleep(_): pass


try:
    ic.press = press2
    ic.time = _T
    placed = ic.select_bans_verified(
        GRID, {(0, 0), (1, 1)},
        look=look2,
        banned_set=lambda: set(state["banned"]),
        on_wrong_ban=lambda want, got: wrong.append((want, sorted(got))),
        log=lambda *a, **k: None)
finally:
    for n, v in saved.items():
        setattr(ic, n, v)

check(wrong and wrong[-1][1] == [(0, 0)],
      f"an UN-BAN fires on_wrong_ban naming the cell it removed: {wrong}")
check((0, 0) not in placed,
      f"...and the un-banned cell is dropped from `placed`, which must describe the "
      f"SCREEN: {sorted(placed)}")

# ---- 2. a raise mid-play unwinds and invalidates --------------------------
calls = {"unwind": 0, "invalidate": 0}
saved = {n: getattr(ic, n) for n in
         ("_look_settled", "_unwind_selection", "invalidate_cursor",
          "_verified_select_and_play_inner")}
try:
    ic._look_settled = lambda look: ([0.0] * 5, [10] * 5, ic.MAX_HAND_SIZE, [])
    ic._unwind_selection = lambda *a, **k: calls.__setitem__("unwind", calls["unwind"] + 1)
    ic.invalidate_cursor = lambda *a, **k: calls.__setitem__(
        "invalidate", calls["invalidate"] + 1)

    def boom(*a, **k):
        raise RuntimeError("the capture died mid-play")
    ic._verified_select_and_play_inner = boom

    raised = None
    try:
        ic.select_and_play(2, None, look=lambda: None)
    except RuntimeError as e:
        raised = e
finally:
    for n, v in saved.items():
        setattr(ic, n, v)

check(raised is not None,
      "the original exception still propagates — the unwind must not swallow it")
check(calls["unwind"] == 1,
      f"a raise mid-play runs _unwind_selection ({calls['unwind']}x)")
check(calls["invalidate"] >= 1,
      f"...and invalidates the cursor belief ({calls['invalidate']}x)")

# ---- 3. CONTROL: a clean play does NOT unwind -----------------------------
# Without this, checks above pass on a wrapper that unwinds unconditionally, which
# would put a legitimately-selected card back down before every commit.
calls2 = {"unwind": 0}
saved = {n: getattr(ic, n) for n in
         ("_look_settled", "_unwind_selection", "invalidate_cursor",
          "_verified_select_and_play_inner")}
try:
    ic._look_settled = lambda look: ([0.0] * 5, [10] * 5, ic.MAX_HAND_SIZE, [])
    ic._unwind_selection = lambda *a, **k: calls2.__setitem__("unwind", calls2["unwind"] + 1)
    ic.invalidate_cursor = lambda *a, **k: None
    ic._verified_select_and_play_inner = lambda c, t, look: True
    out = ic.select_and_play(2, None, look=lambda: None)
finally:
    for n, v in saved.items():
        setattr(ic, n, v)

check(out is True and calls2["unwind"] == 0,
      f"CONTROL: a clean play returns True and unwinds NOTHING "
      f"(returned {out!r}, unwound {calls2['unwind']}x)")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
