"""I-21: a card that DID select must not be pressed again just because its own
disc went blind from the lift.

Live 2026-09-20, mid-match: hand [fielding_boost, 9/0, 5/1, pitch_boost, 6/0],
decision "Playing pitch focus 9" (slot 1). `_select_verified` pressed select_card
FIVE times -- "did not land (attempt 1..4) -- retrying" then "never landed after
5 attempts -- refusing" -- and the user, watching the stream, saw the 9 SELECT
and DESELECT repeatedly.

ROOT CAUSE. The first press landed. Selecting a card brightens it until its
power disc loses the dark edge `read_hand` needs for a position, so
`local_hand.selected_cards` abstains on that row (CLAUDE.md 10.35 is the glow-
window analogue; this is the SAME shape one layer over, on the LIFT reader
instead of the hover reader). `orchestrator.hand_cursor_look`'s own `_ys` column
already reports None for exactly this case (its 2026-09-20 comment: "a selected
card brightened until its power disc had no dark edge... None makes it refuse
instead") -- but that fix only ever ran ONCE, on the pre-loop guard, before any
press. Every retry inside `_select_verified`'s loop re-read `_ys` and never
asked it the same question, so a press that landed and then went blind looked
identical to one that never landed at all, and the loop pressed AGAIN -- a
TOGGLE, putting the just-selected card back down.

THE FIX, in `_select_verified`: after a press, if the target's row is now
unreadable to the lift reader, do NOT press again. Wait `SELECT_RETRY_CONFIRM_SEC`
and re-look once. If it comes back readable-but-not-selected, the press was a
genuine drop (nothing to infer) and the normal retry resumes -- one look always
sits between two select_card presses, so the invariant "never press twice
without a look showing the target still at rest and readable" holds. If it is
STILL unreadable, the only thing that could have caused that is our own press
(the guard above already proved the row was readable before this attempt), so
it is treated as landed: `selected by inference (disc unreadable after lift)`.
A target unreadable from the very start (nothing pressed by us yet) keeps the
existing refusal -- there is nothing to infer from, because nothing here made
it that way.

Uses the same `check(cond, msg)` shape as `tests/minigame/test_verified_selection.py`
and `tests/rig/test_blind_slot_probe_select.py` (checked with
`grep -m1 -o "def check(.*)"` on both before writing this one).
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import input_controller as ic                                        # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


N = ic.MAX_HAND_SIZE
REST = [200, 160, 150, 165, 220]


class LiftScreen:
    """A resting fan of N cards whose lift-readability after selecting the
    TARGET is controlled directly -- decoupled from whether it is lifted, the
    same way ProbeScreen (I-02) decouples glow from selection. Only
    `select_card` does anything; this exercises `_select_verified` directly,
    which never presses move_left/move_right.

    `unreadable_when_lifted`: once the target rises past the SELECTED_MIN_RISE
    gate, its `ys` entry reads None -- exactly what `orchestrator.hand_cursor_
    look`'s `_ys` column reports for a card whose power disc has lost its dark
    edge, and exactly what `local_hand.selected_cards` abstains on.
    `drop_presses`: 1-based press indices that are swallowed outright (the
    console's own 15.20% ignore rate, modelled the same way
    `test_verified_selection.py`'s FlakySelect does) -- nothing about the
    target changes on a dropped press.
    """

    def __init__(self, target, unreadable_when_lifted=True, drop_presses=frozenset()):
        self.target = target
        self.y = list(REST)
        self.sent = []
        self.presses = 0
        self.unreadable_when_lifted = unreadable_when_lifted
        self.drop = set(drop_presses)

    def is_lifted(self, i):
        return REST[i] - self.y[i] >= 25

    def selected(self):
        return [i for i, y in enumerate(self.y) if REST[i] - y >= 25]

    def press(self, key):
        self.sent.append(key)
        if key != "select_card":
            return
        self.presses += 1
        if self.presses in self.drop:
            return                      # the console never saw it
        t = self.target
        if self.is_lifted(t):
            self.y[t] = REST[t]         # a TOGGLE, like the real one -> DOWN
        else:
            self.y[t] -= 44             # -> UP

    def look(self):
        glow = [0.0] * N
        ys = []
        blind = self.unreadable_when_lifted and self.is_lifted(self.target)
        for i in range(N):
            ys.append(None if (i == self.target and blind) else int(self.y[i]))
        sel = [i for i in self.selected() if not (i == self.target and blind)]
        return glow, ys, N, sel


_real_press = ic.press
try:
    # ------------------------------------------------------------------
    # (1) the press LANDS and the disc goes blind from the lift: exactly ONE
    #     select_card press, success, target counted as selected by inference.
    # ------------------------------------------------------------------
    s = LiftScreen(target=1)
    ic.press = s.press
    ok, sel = ic._select_verified(1, s.look)
    check(ok is True, f"a landed-but-now-blind selection must succeed; got {ok!r}")
    check(1 in sel, f"the target must be counted as selected; sel={sel!r}")
    check(s.sent.count("select_card") == 1,
          f"exactly one select_card press -- pressing again would TOGGLE the "
          f"card the engine just selected back off; got "
          f"{s.sent.count('select_card')} in {s.sent!r}")
    check(s.is_lifted(1),
          "and the card is genuinely still lifted on the fake console, not "
          "toggled back down by a second press")

    # ------------------------------------------------------------------
    # CONTROL (a): a genuinely dropped press (nothing changes, the disc stays
    #     readable) must still retry exactly as it did before this fix.
    # ------------------------------------------------------------------
    s = LiftScreen(target=2, unreadable_when_lifted=False, drop_presses={1})
    ic.press = s.press
    ok, sel = ic._select_verified(2, s.look)
    check(ok is True,
          f"a press dropped once and landing on retry must still succeed; got {ok!r}")
    check(2 in sel, f"the target must be selected; sel={sel!r}")
    check(s.sent.count("select_card") == 2,
          f"one dropped press plus one that lands: exactly 2, not the whole "
          f"budget and not just 1; got {s.sent.count('select_card')} in {s.sent!r}")

    # ------------------------------------------------------------------
    # CONTROL (b): the target was ALREADY unreadable before ANY press (a stray
    #     from earlier) -- the existing refusal, and NOTHING is pressed.
    # ------------------------------------------------------------------
    s = LiftScreen(target=3)
    s.y[3] -= 44                                   # arrives already lifted+blind
    ic.press = s.press
    ok, sel = ic._select_verified(3, s.look)
    check(ok is False,
          f"a target unreadable before this call ever pressed anything must "
          f"still refuse; got {ok!r}")
    check("select_card" not in s.sent,
          f"and it must refuse WITHOUT pressing -- there is nothing here that "
          f"OUR press could have caused, so there is nothing to infer from; "
          f"pressed {s.sent!r}")

    # ------------------------------------------------------------------
    # the genuinely-dead case still exhausts SELECT_ATTEMPTS and refuses --
    # this fix must not turn a truly unreachable target into a false success.
    # ------------------------------------------------------------------
    s = LiftScreen(target=4, unreadable_when_lifted=False,
                   drop_presses={1, 2, 3, 4, 5})    # every press swallowed
    ic.press = s.press
    ok, sel = ic._select_verified(4, s.look)
    check(ok is False, f"a target that never lands must still refuse; got {ok!r}")
    check(s.sent.count("select_card") == ic.SELECT_ATTEMPTS,
          f"and it must exhaust the full budget ({ic.SELECT_ATTEMPTS}), not stop "
          f"early because of this fix; got {s.sent.count('select_card')}")
finally:
    ic.press = _real_press

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a selection that lands and then goes blind from its own lift is NOT "
      "pressed again (inferred selected on one press), a genuinely dropped "
      "press still retries and lands, an already-unreadable target still "
      "refuses without pressing, and a genuinely dead target still exhausts "
      "the full retry budget")
