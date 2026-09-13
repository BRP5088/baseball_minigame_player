"""THE BAN NAVIGATOR MUST LOOK, because a wrong cell bans a card the engine did not choose.

select_bans_and_start_full dead-reckons: N presses of move_down and then select_card, with
nothing ever checking where the cursor actually is. Its own comment records the cost --
"three of five real ban sequences finished at 2/3 and the match started anyway... with a
ban set the engine never chose" -- and a live run on 2026-09-13 reported 2 of 3 while the
scrollbar sat at level 1 after navigating toward a row-3 target.

These drive select_bans_verified against a SIMULATED grid whose cursor can be made to drop
presses, which is the thing that cannot be arranged on a real console on demand.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import input_controller as ic

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


class Grid:
    """A ban grid that moves when pressed, and can be told to drop presses."""

    def __init__(self, rows=8, cols=5, drop=(), frozen=False):
        self.r, self.c = 0, 0
        self.rows, self.cols = rows, cols
        self.drop = set(drop)          # press ORDINALS that vanish
        # FROZEN swallows MOVEMENT only, and leaves select_card working. Dropping every
        # press including the toggle hides a blind-toggle bug, because a blind toggle into
        # a dead input does nothing either -- a mutant proved that.
        self.frozen = frozen
        self.n = 0
        self.banned = set()
        self.presses = []

    def press(self, action, **kw):
        self.n += 1
        self.presses.append(action)
        if self.n in self.drop:
            return                      # swallowed, exactly as a mid-animation press is
        if self.frozen and action.startswith("move_"):
            return                      # the cursor will not move, but a toggle still lands
        if action == "move_down":
            self.r = min(self.rows - 1, self.r + 1)
        elif action == "move_up":
            self.r = max(0, self.r - 1)
        elif action == "move_right":
            self.c = min(self.cols - 1, self.c + 1)
        elif action == "move_left":
            self.c = max(0, self.c - 1)
        elif action == "select_card":
            # A TOGGLE, like the real one: a second press un-bans what the first banned.
            if (self.r, self.c) in self.banned:
                self.banned.discard((self.r, self.c))
            else:
                self.banned.add((self.r, self.c))

    def look(self):
        return (self.r, self.c)


GRID = [(r, c, object()) for r in range(8) for c in range(5)]
WANT = {(1, 3), (2, 1), (3, 3)}


def run(drop=(), sleep_patch=True, frozen=False):
    g = Grid(drop=drop, frozen=frozen)
    real_press, real_sleep = ic.press, ic.time.sleep
    ic.press = g.press
    if sleep_patch:
        ic.time.sleep = lambda *_a: None
    try:
        placed = ic.select_bans_verified(
            GRID, WANT, look=g.look,
            confirm_ban=lambda pos: pos in g.banned, log=lambda *a: None)
    finally:
        ic.press, ic.time.sleep = real_press, real_sleep
    return g, placed


print("1. A CLEAN RUN BANS EXACTLY THE THREE ASKED FOR")
g, placed = run()
check(g.banned == WANT, f"the three intended cells carry an X ({sorted(g.banned)})")
check(sorted(placed) == sorted(WANT), f"...and it reports them ({sorted(placed)})")
check(g.presses[-2:] == ["confirm_play", "confirm_play"],
      f"and it confirms twice at the end ({g.presses[-2:]})")

print("\n2. A DROPPED PRESS DOES NOT MOVE THE BAN TO ANOTHER CARD")
# Drop presses 2 and 5 -- mid-navigation, the mid-animation case
g, placed = run(drop=(2, 5))
check(g.banned == WANT,
      f"still exactly the three intended ({sorted(g.banned)}) — the loop looked again "
      f"and made up the lost step")
check(len(g.banned) == 3, f"and three, not two ({len(g.banned)})")

print("\n3. MANY DROPPED PRESSES: it reports rather than toggling blind")
g, placed = run(frozen=True)
check(not (g.banned - WANT),
      f"no card OUTSIDE the intended set is ever banned ({sorted(g.banned)}) — a missing "
      f"ban is recoverable, a wrong one bans a card the engine did not choose")
check(g.presses.count("select_card") == 0,
      f"with the cursor stuck at (0,0) it presses select_card ZERO times "
      f"({g.presses.count('select_card')}) — toggling there would ban whatever happens to "
      f"be under an unmoved cursor")
check(placed == [], f"and it claims nothing was placed ({placed})")

print("\n4. IT NEVER PRESSES select_card WITHOUT LOOKING FIRST")
g, placed = run()
first_sel = g.presses.index("select_card")
check(first_sel > 0, "at least one navigation press precedes the first select_card")
seen = set()
g2 = Grid()
calls = {"looks": 0}
_orig_look = g2.look


def counting_look():
    calls["looks"] += 1
    return _orig_look()


real_press, real_sleep = ic.press, ic.time.sleep
ic.press = g2.press
ic.time.sleep = lambda *_a: None
try:
    ic.select_bans_verified(GRID, WANT, look=counting_look,
                            confirm_ban=lambda p: p in g2.banned, log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = real_press, real_sleep
check(calls["looks"] >= len([p for p in g2.presses if p.startswith("move_")]),
      f"it looks at least once per navigation press ({calls['looks']} looks, "
      f"{len([p for p in g2.presses if p.startswith('move_')])} moves) — the dead-reckoned "
      f"path looks ZERO times")

print("\n5. A TOGGLE THAT DID NOT TAKE IS NOT PRESSED AGAIN")
# select_card is a TOGGLE: a second press un-bans what the first banned.
g = Grid()
real_press, real_sleep = ic.press, ic.time.sleep
ic.press = g.press
ic.time.sleep = lambda *_a: None
try:
    ic.select_bans_verified(GRID, {(1, 3)}, look=g.look,
                            confirm_ban=lambda pos: False,   # always claims it failed
                            log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = real_press, real_sleep
check(g.presses.count("select_card") == 1,
      f"select_card is pressed ONCE even when the confirm says it failed "
      f"({g.presses.count('select_card')}) — pressing again would un-ban it")

print("\n6. THE DEAD-RECKONED PATH BANS THE WRONG CARDS ON THE SAME GRID")
# This is the comparison that justifies the flag. Same grid, same dropped presses; the
# shipped path counts and the new one looks.
def run_old(drop=()):
    g = Grid(drop=drop)
    real_press, real_sleep = ic.press, ic.time.sleep
    ic.press = g.press
    ic.time.sleep = lambda *_a: None
    try:
        ic.select_bans_and_start_full(GRID, WANT)
    finally:
        ic.press, ic.time.sleep = real_press, real_sleep
    return g

g_old = run_old()
check(g_old.banned == WANT,
      f"with NOTHING dropped the old path is correct too ({sorted(g_old.banned)}) — the "
      f"difference is not the happy path")

g_old = run_old(drop=(2, 5))
g_new, _ = run(drop=(2, 5))
check(g_old.banned != WANT,
      f"but with two presses dropped it bans {sorted(g_old.banned)} instead of "
      f"{sorted(WANT)}")
wrong = sorted(g_old.banned - WANT)
check(bool(wrong),
      f"and {wrong} is a card the engine never chose — banned silently, in a match that "
      f"costs $50")
check(g_new.banned == WANT,
      f"the looking path, same grid and same dropped presses, is still correct "
      f"({sorted(g_new.banned)})")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
