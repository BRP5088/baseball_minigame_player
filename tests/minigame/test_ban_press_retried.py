"""I-50: THE select_card PRESS INSIDE select_bans_verified IS NOW RETRIED.

Census (`agent_progress/census/ban_shortfall/progress.md`, main checkout): over 37
matches, 15 started with fewer than 3 bans (2/3 x10, 1/3 x5) -- 20 missed targets, and
ALL TWENTY were the same line: "[ban] select_card at (r, c) placed no X anywhere —
leaving it" (input_controller.py, `select_bans_verified`). The verified navigator
confirms the cursor is on the target, presses `select_card` ONCE (a bare `press()`,
not `press_verified`), diffs `banned_set()` before/after, finds no change, and moves on
WITHOUT RETRYING. That is a silently dropped press: CLAUDE.md §5 measured the console
ignoring 15.2% of presses, clustered, which is exactly what `PRESS_VERIFY_TRIES` (5,
reused here -- no new constant) exists for on every OTHER press on this path
(confirm_play, start_match). Zero of the 20 misses came from navigation, a blind
cursor, or a stale-frame desync -- only the press-after-arrival was ever the problem.

`select_card` is a TOGGLE, and the ban screen shows a brief selection splash that can
make a landed press's X invisible on the VERY NEXT look. A naive retry would then press
again and UN-BAN the cell it just banned. So a retry must, before firing again: (a)
re-look and confirm the cursor is still on the target (a drifted cursor must not be
guessed at), and (b) re-check the full banned set for a splash that caught up (a cell
that IS now banned must not be pressed again).

These drive `select_bans_verified` against small fake grids, reusing
`tests/rig/test_ban_nav_verified.py`'s `look()`/`press()`/`banned_set()` stubbing
pattern rather than touching the real rig.
"""
import os as _os
import sys as _sys

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


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


class FakeGrid:
    """A small ban grid: normal move navigation, and a select_card press that can be
    scripted per case to drop N times before landing, show its X only after a delay
    (the selection splash), never land at all, or drift the cursor after landing.
    """

    def __init__(self, rows=4, cols=4, drop_first=0, splash_delay=0,
                 never_lands=False, drift_after=None):
        self.r, self.c = 0, 0
        self.rows, self.cols = rows, cols
        self.presses = []
        self.select_presses = 0
        self.banned = set()
        self._committed = set()
        self.drop_first = drop_first       # presses at a FRESH cell to swallow
        self.splash_delay = splash_delay   # banned_set() reads a landed press still owes
        self.never_lands = never_lands     # select_card is permanently a no-op
        self.drift_after = drift_after     # cursor moves off-target after N select presses
        self._tried = {}                   # cell -> presses already swallowed there
        self._pending = 0

    def press(self, action, **kw):
        self.presses.append(action)
        if action == "move_down":
            self.r = min(self.rows - 1, self.r + 1)
        elif action == "move_up":
            self.r = max(0, self.r - 1)
        elif action == "move_right":
            self.c = min(self.cols - 1, self.c + 1)
        elif action == "move_left":
            self.c = max(0, self.c - 1)
        elif action == "select_card":
            self.select_presses += 1
            if self.never_lands:
                if self.drift_after is not None and self.select_presses == self.drift_after:
                    self.c = min(self.cols - 1, self.c + 1)
                return
            cell = (self.r, self.c)
            n = self._tried.get(cell, 0)
            if n < self.drop_first:
                self._tried[cell] = n + 1
            else:
                if cell in self.banned:
                    self.banned.discard(cell)
                else:
                    self.banned.add(cell)
                self._pending = self.splash_delay
            if self.drift_after is not None and self.select_presses == self.drift_after:
                self.c = min(self.cols - 1, self.c + 1)

    def look(self):
        return (self.r, self.c)

    def banned_set(self):
        if self._pending > 0:
            self._pending -= 1
            return set(self._committed)
        self._committed = set(self.banned)
        return set(self._committed)


def run(grid, want):
    real_press, real_sleep = ic.press, ic.time.sleep
    ic.press = grid.press
    ic.time.sleep = lambda *_a: None
    try:
        placed = ic.select_bans_verified(
            GRID3, want, look=grid.look, banned_set=grid.banned_set,
            confirm_ban=lambda pos: pos in grid.banned, log=lambda *a: None)
    finally:
        ic.press, ic.time.sleep = real_press, real_sleep
    return placed


GRID3 = [(r, c, object()) for r in range(4) for c in range(4)]


print("A. FIRST PRESS DROPPED, SECOND LANDS -> 3/3 placed, 2 presses at each cell")
g = FakeGrid(drop_first=1)
want = {(0, 0), (1, 1), (2, 2)}
placed = run(g, want)
check(f"all three placed ({sorted(placed)})", sorted(placed) == sorted(want))
check(f"all three carry an X ({sorted(g.banned)})", g.banned == want)
check(f"exactly 2 select_card presses per cell (dropped once, PRESS_VERIFY_TRIES={ic.PRESS_VERIFY_TRIES})",
      g.select_presses == 2 * len(want))

print("\nB. THE SPLASH: X appears only on the RE-LOOK -> exactly 1 press, never toggled off")
g = FakeGrid(splash_delay=1)
want = {(1, 2)}
placed = run(g, want)
check(f"placed despite the delayed read ({placed})", placed == [(1, 2)])
check(f"still banned, not toggled back off ({sorted(g.banned)})", g.banned == want)
check(f"exactly ONE select_card press ({g.select_presses}) — a naive retry would have "
      "pressed a second time and un-banned it", g.select_presses == 1)

print("\nC. ALL TRIES DROPPED -> 'leaving it', PRESS_VERIFY_TRIES presses, run continues")
g = FakeGrid(never_lands=True)
want = {(0, 0), (3, 3)}
placed = run(g, want)
check(f"neither target ever placed ({placed})", placed == [])
check(f"nothing banned ({sorted(g.banned)})", not g.banned)
check(f"both targets exhausted exactly PRESS_VERIFY_TRIES presses each "
      f"({g.select_presses} == {2 * ic.PRESS_VERIFY_TRIES}) — the run did not stop "
      "after the first target's tries ran out",
      g.select_presses == 2 * ic.PRESS_VERIFY_TRIES)

print("\nD. CONTROL: everything lands first time -> one press per cell, unchanged")
g = FakeGrid()
want = {(0, 0), (1, 1), (2, 2)}
placed = run(g, want)
check(f"all three placed ({sorted(placed)})", sorted(placed) == sorted(want))
check(f"exactly one select_card press per cell (3 total, {g.select_presses})",
      g.select_presses == 3)

print("\nE. THE CURSOR DRIFTS BETWEEN THE DROPPED PRESS AND THE RETRY: refuse to press again")
g = FakeGrid(drop_first=1, drift_after=1)
want = {(0, 0)}
placed = run(g, want)
check(f"not placed ({placed})", placed == [])
check(f"nothing ever banned ({sorted(g.banned)})", not g.banned)
check(f"exactly ONE select_card press ({g.select_presses}) — the retry's here==want "
      "check must stop a second, blind press once the cursor has moved off target",
      g.select_presses == 1)

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
