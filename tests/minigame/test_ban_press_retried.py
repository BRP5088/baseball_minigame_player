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


class SlowSplashGrid:
    """A single target whose select_card LANDS immediately but whose banned_set()
    only reveals it once enough VIRTUAL time has passed -- the skeptic's harness
    shape for "the re-check is not on a settled frame". time.sleep() is stubbed to
    `tick`, which advances a fake clock; look() and press() cost no time. Reveal
    is set to outlive exactly ONE settle (the sleep already spent before the first
    `_after` read) but not two, so it tells apart "no extra sleep before the retry
    re-check" from "one more settle before it".
    """

    def __init__(self):
        self.r, self.c = 0, 0
        self.presses = []
        self.select_presses = 0
        self.true_banned = set()
        self._press_clock = {}
        self.clock = 0.0
        self.reveal_after = 1.5 * ic.BAN_NAV_SETTLE

    def tick(self, dur):
        self.clock += dur

    def press(self, action, **kw):
        self.presses.append(action)
        if action != "select_card":
            return
        self.select_presses += 1
        cell = (self.r, self.c)
        if cell in self.true_banned:
            self.true_banned.discard(cell)
            self._press_clock.pop(cell, None)
        else:
            self.true_banned.add(cell)
            self._press_clock[cell] = self.clock

    def look(self):
        return (self.r, self.c)

    def banned_set(self):
        return {c for c in self.true_banned
                if self.clock - self._press_clock[c] >= self.reveal_after}


class StaleRetryGrid:
    """T1=(0,0) lands cleanly. T2=(1,1)'s first press is dropped; its RETRY press
    lands not at (1,1) but at T1's cell -- a stale cursor, CLAUDE.md's own "a stale
    column frame bans the wrong card" shape -- which UN-BANS T1. T2's second retry
    then lands correctly. Exercises `_gone` firing on a RETRY (not just attempt 1)
    and the running baseline (`_before`) reflecting the PREVIOUS attempt, not the
    frame before the very first press.
    """

    def __init__(self):
        self.r, self.c = 0, 0
        self.presses = []
        self.banned = set()
        self._at = {}   # cell AIMED at -> count of select_card presses aimed there

    def press(self, action, **kw):
        self.presses.append(action)
        if action == "move_down":
            self.r = 1
        elif action == "move_up":
            self.r = 0
        elif action == "move_right":
            self.c = 1
        elif action == "move_left":
            self.c = 0
        elif action == "select_card":
            aimed = (self.r, self.c)
            n = self._at.get(aimed, 0)
            self._at[aimed] = n + 1
            if aimed == (1, 1):
                if n == 0:
                    return                            # T2's first press: dropped
                real_cell = (0, 0) if n == 1 else (1, 1)   # n==1: stale onto T1
            else:
                real_cell = aimed
            if real_cell in self.banned:
                self.banned.discard(real_cell)
            else:
                self.banned.add(real_cell)

    def look(self):
        return (self.r, self.c)

    def banned_set(self):
        return set(self.banned)


class BlindRetryGrid(FakeGrid):
    """Like FakeGrid, but the look() called right after ANY select_card press
    returns None once (an unreadable frame -- ban_cursor_absolute's own None on a
    mid-animation frame) before reporting the cursor truthfully again. A blind
    retry look must not be read as "the cursor moved" and must not abandon the
    chain.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self._blind_pending = False

    def press(self, action, **kw):
        super().press(action, **kw)
        if action == "select_card":
            self._blind_pending = True

    def look(self):
        if self._blind_pending:
            self._blind_pending = False
            return None
        return super().look()


class TransientFlickerGrid:
    """Single target (0, 0). Its first select_card press is genuinely dropped (no
    state change at all). The pre-press retry re-check's OWN banned_set() read (the
    3rd call: initial _before, _after of the dropped press, then this one) reports a
    TRANSIENT flicker at an UNRELATED cell (1, 1) -- gone again on every other read --
    rather than the target. The re-check must ask specifically whether `want` carries
    the X, not merely whether the set grew: a merged-agent mutant that accepts ANY new
    X (`_recheck - _before` non-empty) reads that flicker as "the target landed late",
    never presses select_card again, and reports (0, 0) placed while it is still
    unbanned on screen. Correct code presses again, which really bans it.
    """

    def __init__(self):
        self.r, self.c = 0, 0
        self.select_presses = 0
        self.banned = set()
        self.banned_set_calls = 0

    def press(self, action, **kw):
        if action == "select_card":
            self.select_presses += 1
            if self.select_presses == 1:
                return  # genuinely dropped: no state change at all
            self.banned.add((0, 0))  # the real retry press lands

    def look(self):
        return (self.r, self.c)

    def banned_set(self):
        self.banned_set_calls += 1
        if self.banned_set_calls == 3:
            # the pre-press retry re-check's own read: a flicker at an UNRELATED
            # cell, gone again on every other read
            return {(1, 1)}
        return set(self.banned)


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
GRID2 = [(r, c, object()) for r in range(2) for c in range(2)]


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

print("\nB2. THE SPLASH OUTLIVES ONE SETTLE BUT NOT TWO -> the retry's re-check must "
      "itself wait a settle, not just spend the wall time of a look() + banned_set()")
g = SlowSplashGrid()
real_press, real_sleep = ic.press, ic.time.sleep
ic.press = g.press
ic.time.sleep = g.tick
try:
    placed = ic.select_bans_verified(
        GRID3, {(0, 0)}, look=g.look, banned_set=g.banned_set,
        confirm_ban=lambda pos: pos in g.true_banned, log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = real_press, real_sleep
check(f"placed once the second settle clears the splash ({placed})", placed == [(0, 0)])
check(f"still banned, not toggled back off ({sorted(g.true_banned)})",
      g.true_banned == {(0, 0)})
check(f"exactly ONE select_card press ({g.select_presses}) — without a settle before "
      "the retry's re-check, it would still be reading the stale (pre-press) frame and "
      "would press again, un-banning it", g.select_presses == 1)

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

print("\nF. A STALE RETRY PRESS LANDS ON AN EARLIER TARGET: un-ban caught, later target "
      "still lands, and the un-ban is reported exactly once")
g = StaleRetryGrid()
_wrong = []
real_press, real_sleep = ic.press, ic.time.sleep
ic.press = g.press
ic.time.sleep = lambda *_a: None
try:
    placed = ic.select_bans_verified(
        GRID2, {(0, 0), (1, 1)}, look=g.look, banned_set=g.banned_set,
        confirm_ban=lambda pos: pos in g.banned,
        on_wrong_ban=lambda want, gone: _wrong.append((want, sorted(gone))),
        log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = real_press, real_sleep
check(f"T2 placed, T1 dropped from `placed` ({placed})", placed == [(1, 1)])
check(f"the screen agrees: only T2 carries an X ({sorted(g.banned)})",
      g.banned == {(1, 1)})
check(f"on_wrong_ban fired exactly ONCE ({_wrong}) — a stale baseline (M3: no "
      "`_before = _after` between retries) reports the same un-ban a second time; "
      "an attempt-1-only `_gone` check (M4) never reports it at all",
      len(_wrong) == 1)
if _wrong:
    check(f"...naming what actually happened (want={_wrong[0][0]}, "
          f"gone={_wrong[0][1]})", _wrong[0] == ((1, 1), [(0, 0)]))

print("\nG. A BLIND RETRY LOOK IS NOT A MOVED CURSOR: try again rather than abandon")
g = BlindRetryGrid(drop_first=1)
_logged = []
real_press, real_sleep = ic.press, ic.time.sleep
ic.press = g.press
ic.time.sleep = lambda *_a: None
try:
    placed = ic.select_bans_verified(
        GRID3, {(0, 0)}, look=g.look, banned_set=g.banned_set,
        confirm_ban=lambda pos: pos in g.banned, log=_logged.append)
finally:
    ic.press, ic.time.sleep = real_press, real_sleep
check(f"placed despite a blind retry look ({placed})", placed == [(0, 0)])
check(f"exactly TWO select_card presses (one dropped, one landed after the blind "
      f"retry was retried rather than abandoned) ({g.select_presses})",
      g.select_presses == 2)
check("the chain was never abandoned as a cursor drift",
      not any("cursor left" in m for m in _logged))
check("the blind frame was named truthfully",
      any("could not be read" in m for m in _logged))

print("\nH. THE PRE-PRESS RETRY RE-CHECK MUST NAME THE TARGET, NOT JUST 'A NEW X "
     "APPEARED': a transient flicker on an UNRELATED cell must not be read as the "
     "target landing")
g = TransientFlickerGrid()
placed = run(g, {(0, 0)})
check(f"placed only if actually banned on screen ({placed} vs banned={sorted(g.banned)})",
      ((0, 0) in placed) == ((0, 0) in g.banned))
check(f"the target really is banned ({sorted(g.banned)})", g.banned == {(0, 0)})
check(f"TWO select_card presses (dropped, then a real retry press once the flicker "
      f"at (1, 1) was correctly NOT read as the target landing) ({g.select_presses})",
      g.select_presses == 2)

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
