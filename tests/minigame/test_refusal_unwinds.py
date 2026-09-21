"""A refused play puts back down whatever IT raised -- and nothing else.

OBSERVED LIVE 2026-09-16. The engine chose 8/0 + a fielding boost. The player
card selected fine; the TACTICS select could not be verified -- local_hand's own
comment records why, find_tactics stops matching a card once it is selected, so
a tactics target goes unreadable AT THE MOMENT IT LIFTS. _select_verified then
pressed again, and select_card is a TOGGLE, so the second press put it back
down. The call refused honestly and committed nothing... and left the 8/0
LIFTED on a board the next caller would read as clean.

_verified_select_and_play's own comment already names the consequence: the retry
selects its own target and confirm_play commits BOTH. It was reproduced once
with [0, 2] going in together.

RECONCILED 2026-09-21 AFTER I-48 (db3bfcb). I-48 gave exactly this shape -- batter
succeeds, tactics select never verifies -- a DIFFERENT ending: the tactics target
alone is unwound and the batter is committed WITHOUT it
(`_verified_select_and_play_inner`'s `card_index is not None`-gated fallback, see
ISSUES.md I-48 and `test_tactics_select_fallback.py`), rather than refusing the
whole play. Scenarios 1-3 below all land on that fallback (a batter walk/select
that succeeds, paired with a tactics target that never verifies) and are rewritten
to pin the NEW contract: `ok is True`, exactly one `confirm_play`, only the batter
in `confirmed_sel`, nothing left lifted (the fan is gone), and
`tactics_dropped_last_play()` is True. The `Board` mock gained a `confirm_play`
that empties the fan (the same "fan-gone" sentinel `_fan_state()` reads as a
landed play, in `test_tactics_select_fallback.py`'s `PlayScreen`) -- without it
`confirm_play` never verifies against this mock and every I-48 fallback commit
reads as a refusal for the wrong reason.

What did NOT change: a failure on the BATTER's own target (its walk or its
select) still refuses the whole play and unwinds everything this call raised,
same as before I-48 -- scenarios 4 and 5 pin that, unchanged and newly added
respectively.

Plain asserts: four incompatible check() signatures live in this suite.
"""
import hashlib
import importlib
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import input_controller as ic

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


class Board:
    """A fake fan. `lifted` is the truth; presses toggle it. `confirm_play` empties
    the fan (n -> 0, sel -> []), the same "fan-gone" sentinel `_fan_state()` reads
    as a landed play -- see `test_tactics_select_fallback.py`'s `PlayScreen`, same
    shape. Without this a successful I-48 fallback commit never verifies against
    this mock and reads as a refusal for the wrong reason."""

    def __init__(self, lifted=(), select_works=True):
        self.lifted = set(lifted)
        self.select_works = select_works
        self.cursor = 0
        self.presses = []
        self.fan_gone = False
        self.confirmed_sel = None

    def look(self):
        if self.fan_gone:
            return [0.0] * ic.MAX_HAND_SIZE, [None] * ic.MAX_HAND_SIZE, 0, []
        ys = [100 if i in self.lifted else 160 for i in range(ic.MAX_HAND_SIZE)]
        glow = [30.0 if i == self.cursor else 0.0 for i in range(ic.MAX_HAND_SIZE)]
        return glow, ys, ic.MAX_HAND_SIZE, sorted(self.lifted)

    def press(self, action, **kw):
        self.presses.append(action)
        if self.fan_gone:
            return
        if action == "move_right":
            self.cursor = min(self.cursor + 1, ic.MAX_HAND_SIZE - 1)
        elif action == "move_left":
            self.cursor = max(self.cursor - 1, 0)
        elif action == "select_card":
            # THE TOGGLE. A select on a lifted card puts it DOWN -- which is the
            # mechanism that made the live failure look like "never landed".
            if self.select_works or self.cursor in self.lifted:
                self.lifted.symmetric_difference_update({self.cursor})
        elif action == "confirm_play":
            self.confirmed_sel = sorted(self.lifted)
            self.fan_gone = True


def scenario1():
    """THE LIVE CASE, under I-48: the player card goes up, the TACTICS select
    never verifies -- the tactics target alone is unwound and the batter is
    committed WITHOUT it, in one confirm_play press."""
    b = Board()

    def press_tactics_fails(action, **kw):
        # slot 0 is the tactics card here: every select on it is swallowed
        if action == "select_card" and b.cursor == 0:
            b.presses.append(action)
            return
        b.press(action, **kw)

    ic.press = press_tactics_fails
    ok = ic._verified_select_and_play(1, 0, b.look)
    return b, ok


def scenario2():
    """A CARD ALREADY UP WHEN A COMMIT RUNS IS A STRAY, NOT A SURVIVOR. Pre-I-48
    this exact setup (tactics select swallowed) was a full refusal, and a
    pre-existing selection is not this call's to touch on a refusal (see
    scenario 4). Under I-48 it is a COMMIT (batter alone) instead, and
    `_clear_strays` -- unrelated to I-48, unchanged, the same guard every commit
    has always run -- puts down anything not in `want` before pressing
    confirm_play. So the pre-existing stray at slot 3 gets cleared here, not
    preserved; only a genuine refusal (scenario 4) leaves an untouched stray up."""
    b2 = Board(lifted={3})
    ic.press = lambda a, **k: (b2.presses.append(a) if (a == "select_card" and b2.cursor == 0)
                                else b2.press(a, **k))
    ok = ic._verified_select_and_play(1, 0, b2.look)
    return b2, ok


def scenario3():
    """THE WALK REFUSAL now also lands on the I-48 fallback. The player card
    selects (cursor starts on it), then the cursor cannot reach the tactics
    slot at all (every move press is swallowed) -- so _walk_cursor_to gives up.
    The guard in the per-target loop does not care whether the WALK or the
    SELECT failed, only which target failed, so this is the same fallback as
    scenario 1: the batter, already raised, is committed instead of put back
    down."""
    b3 = Board()

    def press_moves_fail(action, **kw):
        if action in ("move_left", "move_right"):
            b3.presses.append(action)          # sent, but the cursor never moves
            return
        b3.press(action, **kw)

    ic.press = press_moves_fail
    b3.cursor = 1                               # already on the player card
    ok = ic._verified_select_and_play(1, 4, b3.look)
    return b3, ok


def scenario4():
    """A CARD THAT WENT UP WITHOUT BEING AIMED AT IS NOT UNWOUND, AND THE BATTER'S
    OWN FAILURE STILL REFUSES THE WHOLE PLAY. UNCHANGED BY I-48: this call has no
    tactics_index at all, so the fallback guard (which requires the failing
    target to BE tactics_index) never applies -- a card_index failure is the
    same full refusal it always was. _select_verified's own comment: "something
    that was NOT up before has gone up, and it is not the target. Pressing again
    compounds it." test_verified_selection pins exactly ONE select press on that
    path, and a first version of this unwind pressed on the stray and took it to
    three."""
    b4 = Board()

    def press_lifts_wrong(action, **kw):
        if action == "select_card":
            b4.presses.append(action)
            b4.lifted.symmetric_difference_update({(b4.cursor + 1) % ic.MAX_HAND_SIZE})
            return
        b4.press(action, **kw)

    ic.press = press_lifts_wrong
    ok = ic._verified_select_and_play(2, None, b4.look)
    return b4, ok


def scenario5():
    """NEW, TO KEEP THE GENERAL (batter-failure) UNWIND HONEST. Scenario 4 proves
    the general refusal path does NOT touch a stray outside `ours` -- it says
    nothing about whether it puts back down a stray that IS one of `ours`, because
    that stray (slot 3) never belonged to `targets={2}`. Here the wrong card the
    mock raises during the batter's own select (cursor+1) is deliberately the
    OTHER target (tactics_index), so it IS in `ours`, and the general refusal at
    the bottom of the per-target loop (`_unwind_selection(before_all, look,
    targets, ys0=_ys0)`) has something real to put back down. The wrong lift
    fires only once, so the unwind's own deselect (a genuine toggle) can land."""
    b5 = Board()
    state = {"wrong_done": False}

    def press_one_wrong_lift(action, **kw):
        if action == "select_card" and not state["wrong_done"]:
            state["wrong_done"] = True
            b5.presses.append(action)
            b5.lifted.symmetric_difference_update({(b5.cursor + 1) % ic.MAX_HAND_SIZE})
            return
        b5.press(action, **kw)

    ic.press = press_one_wrong_lift
    # card_index=1 fails (wrong card raised); tactics_index=2 is exactly the slot
    # the mock's first bad select_card lifts (cursor is 1 when it presses, so it
    # raises (1+1)%5 == 2) -- a real lift inside `ours`, not outside it.
    ok = ic._verified_select_and_play(1, 2, b5.look)
    return b5, ok


real_press, real_sleep = ic.press, None
import time as _t
_real_sleep = _t.sleep
try:
    _t.sleep = lambda *a, **k: None

    # 1. THE LIVE CASE, post-I-48: fallback commits the batter alone.
    b, ok = scenario1()
    want("the batter is committed alone (I-48 fallback), not refused", ok is True, str(ok))
    want("only the batter (slot 1) was confirmed", b.confirmed_sel == [1],
         f"confirmed_sel={b.confirmed_sel}")
    want("exactly one confirm_play press", b.presses.count("confirm_play") == 1,
         f"{b.presses.count('confirm_play')} confirm_play presses")
    _sel = b.look()[3]
    want("and nothing is left lifted (the fan is gone)", _sel == [],
         f"look() -> sel={_sel}")
    want("tactics_dropped_last_play() reports True", ic.tactics_dropped_last_play() is True)

    # 2. A PRE-EXISTING STRAY IS CLEARED ON A COMMIT, NOT PRESERVED -- this input
    #    no longer refuses (see scenario2's own docstring for why).
    b2, ok = scenario2()
    want("the batter is committed alone here too", ok is True, str(ok))
    want("the pre-existing stray (slot 3) was cleared before committing, not kept",
         b2.confirmed_sel == [1], f"confirmed_sel={b2.confirmed_sel}")
    want("exactly one confirm_play press", b2.presses.count("confirm_play") == 1,
         f"{b2.presses.count('confirm_play')} confirm_play presses")
    want("tactics_dropped_last_play() reports True", ic.tactics_dropped_last_play() is True)

    # 3. THE WALK REFUSAL, which used to be the OTHER early return and now also
    #    lands on the I-48 fallback -- a mutant that stopped unwinding the
    #    tactics attempt there survives scenarios 1-2 alone if it only breaks on
    #    a SELECT failure, not a WALK failure.
    b3, ok = scenario3()
    want("a walk that cannot reach the tactics target also falls back to I-48",
         ok is True, str(ok))
    want("the batter, already raised, is committed rather than put back down",
         b3.confirmed_sel == [1], f"confirmed_sel={b3.confirmed_sel}")
    want("tactics_dropped_last_play() reports True", ic.tactics_dropped_last_play() is True)

    # 4. A CARD THAT WENT UP WITHOUT BEING AIMED AT IS NOT UNWOUND, and a BATTER
    #    failure still refuses the whole play -- unchanged by I-48 (see docstring).
    b4, ok = scenario4()
    want("a wrong-card lift is refused", ok is False, str(ok))
    want("and the unwind does NOT press on a stray outside `ours`",
         b4.presses.count("select_card") == 1,
         f"{b4.presses.count('select_card')} select presses -- pressing again compounds it")

    # 5. THE OTHER HALF OF 4: a stray that IS one of `ours` (here, the wrong card
    #    the mock raises happens to be tactics_index) IS put back down by the
    #    same general refusal, proving that path still does its job post-I-48.
    b5, ok = scenario5()
    want("a batter failure that also lifts the OTHER target still refuses",
         ok is False, str(ok))
    want("and that stray, being one of `ours`, is put back down",
         not b5.lifted, f"slot(s) {sorted(b5.lifted)} left up after the refusal")

finally:
    ic.press = real_press
    _t.sleep = _real_sleep

print(f"\n{len(fails)} failure(s) before mutation testing")

# =============================================================================
# MUTATION TESTING (CLAUDE.md 10.9/10.10): a REAL edit to input_controller.py on
# disk, __pycache__ cleared, module reloaded, restored byte-for-byte and
# sha256-verified afterward.
# =============================================================================
IC_PATH = os.path.join(_ROOT, "input_controller.py")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _clear_pycache(modname):
    d = os.path.join(_ROOT, "__pycache__")
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith(modname + "."):
                os.remove(os.path.join(d, fn))


def _mutate(path, anchor, replacement):
    with open(path) as f:
        src = f.read()
    n = src.count(anchor)
    if n != 1:
        raise AssertionError(
            f"mutation anchor found {n} times in {path}, expected exactly 1: {anchor!r}")
    with open(path, "w") as f:
        f.write(src.replace(anchor, replacement, 1))


def _reload_ic():
    global ic
    _clear_pycache("input_controller")
    ic = importlib.reload(ic)
    ic.time.sleep = lambda d: None


_ic_sha0 = _sha(IC_PATH)
with open(IC_PATH, "rb") as f:
    _IC_ORIG_BYTES = f.read()


def _restore_ic():
    with open(IC_PATH, "wb") as f:
        f.write(_IC_ORIG_BYTES)
    _reload_ic()
    want("input_controller.py restored byte-for-byte", _sha(IC_PATH) == _ic_sha0)


_t.sleep = lambda *a, **k: None

# --- mutant 1: re-introduce the pre-I-48 behaviour (fallback refuses) ---------
print("\nmutant 1: the fallback's own `continue` becomes `return False` "
      "(pre-I-48 behaviour) -- the rewritten scenarios must now REFUSE")
try:
    _mutate(IC_PATH,
            "            tactics_index = None\n"
            "            _LAST_PLAY_DROPPED_TACTICS = True\n"
            "            continue\n",
            "            tactics_index = None\n"
            "            _LAST_PLAY_DROPPED_TACTICS = True\n"
            "            return False\n")
    _reload_ic()
    b, ok = scenario1()
    want("mutant 1 caught by scenario 1: no longer committed", ok is False, str(ok))
    b3, ok = scenario3()
    want("mutant 1 caught by scenario 3: no longer committed", ok is False, str(ok))
finally:
    _restore_ic()

# --- mutant 2: drop the unwind on the BATTER-failure (general refusal) path --
print("\nmutant 2: the general refusal's `_unwind_selection(before_all, look, "
      "targets, ...)` is dropped -- the kept scenario (5) must leave its stray "
      "lifted")
try:
    _mutate(IC_PATH,
            "        _unwind_selection(before_all, look, targets, ys0=_ys0)\n",
            "        pass  # I-48 mutant: general unwind dropped\n")
    _reload_ic()
    b5, ok = scenario5()
    want("mutant 2 caught by scenario 5: the stray is left lifted", bool(b5.lifted),
         f"lifted={sorted(b5.lifted)} -- should be nonempty once the unwind is gone")
finally:
    _restore_ic()

# --- sanity: the fix is still intact after both mutants ----------------------
b, ok = scenario1()
want("post-restore sanity: scenario 1 passes again",
     ok is True and b.confirmed_sel == [1])
b5, ok = scenario5()
want("post-restore sanity: scenario 5 passes again",
     ok is False and not b5.lifted)

ic.press = real_press
_t.sleep = _real_sleep

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
