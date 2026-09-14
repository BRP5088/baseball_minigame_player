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

print("\n6. THE SENSOR GOES BLIND MIDWAY — the case with no coverage until now")
# The probe in run() checks the cursor BEFORE placement and never during, and one
# success committed to this path with no way back. A cursor that answers the probe
# and then goes blind placed ZERO bans and still pressed confirm_play -- Triangle,
# i.e. PLAY -- on a match already debited $50. The covered cases were "always
# blind" and "always reads"; "reads, then stops" had none.
_g = Grid()
_looks = {"n": 0}


def _blind_after_one():
    _looks["n"] += 1
    return _g.look() if _looks["n"] <= 1 else None


_fell_back = []
_real_press, _real_sleep = ic.press, ic.time.sleep
ic.press = _g.press
ic.time.sleep = lambda *_a: None
try:
    _placed = ic.select_bans_verified(
        GRID, WANT, look=_blind_after_one,
        confirm_ban=lambda pos: pos in _g.banned, log=lambda *a: None,
        on_blind=lambda: _fell_back.append(1))
finally:
    ic.press, ic.time.sleep = _real_press, _real_sleep
check(_fell_back == [1],
      "a cursor that answers once and then goes blind must fall back, not press PLAY "
      f"on an unbanned $50 match (fell back: {_fell_back})")
check("confirm_play" not in _g.presses,
      f"it pressed {[x for x in _g.presses if x == 'confirm_play']} — the navigator must "
      "not commit when it is handing over to the dead-reckoned path, which confirms itself")
check(not _g.banned, f"nothing should have been toggled ({sorted(_g.banned)})")

# ...and the control: when it DOES toggle, on_blind must NOT fire, or every run
# would dead-reckon over bans that are already correctly placed.
_g2 = Grid()
_fb2 = []
ic.press, ic.time.sleep = _g2.press, lambda *_a: None
try:
    _p2 = ic.select_bans_verified(GRID, WANT, look=_g2.look,
                                  confirm_ban=lambda pos: pos in _g2.banned,
                                  log=lambda *a: None, on_blind=lambda: _fb2.append(1))
finally:
    ic.press, ic.time.sleep = _real_press, _real_sleep
check(not _fb2 and _g2.banned == WANT,
      f"CONTROL: a working sensor must NOT fall back (fell back {_fb2}, "
      f"banned {sorted(_g2.banned)}) — dead-reckoning over correct bans un-toggles them")

print("\n7. A RAISING READER MUST NOT LEAVE THE SCREEN MID-CHANGE")
# Neither look() nor confirm_ban was wrapped, and neither is ban_cursor_absolute.
# A raise left the bans ON SCREEN with confirm_play never pressed, and in run() it
# unwound before bans_done_this_match and acted_screen were set -- so the next poll
# re-entered with the cached collection and TOGGLED THE BANS BACK OFF. That is the
# one path that defeats the C3 guard.
_g3 = Grid()
_n3 = {"i": 0}


def _raises_late():
    _n3["i"] += 1
    if _n3["i"] > 6:
        raise RuntimeError("the ban screen could not be read")
    return _g3.look()


ic.press, ic.time.sleep = _g3.press, lambda *_a: None
try:
    _p3 = ic.select_bans_verified(GRID, WANT, look=_raises_late,
                                  confirm_ban=lambda pos: pos in _g3.banned,
                                  log=lambda *a: None)
    _raised = None
except Exception as _e:
    _raised = _e
finally:
    ic.press, ic.time.sleep = _real_press, _real_sleep
check(_raised is None,
      f"the reader's exception escaped ({_raised!r}) — at the real call site that unwinds "
      "before either guard is armed, and the next poll un-toggles the bans")
check(_g3.presses[-2:] == ["confirm_play", "confirm_play"],
      f"it must still COMMIT what is placed ({_g3.presses[-2:]}) rather than leave the "
      "screen mid-change for the next poll to undo")

print("\n8. A FAR TARGET IS NOT LOST TO THE WAIT BUDGET")
# Moves and blind waits shared one budget of 14, so a far target with one late frame
# per scrolling press ran out before arriving: (6, 2) needs 2*6 + 2 + 1 = 15 and was
# silently skipped, reported as ban_nav_incomplete, and the match played 2 of 3.
_g4 = Grid()
_alt = {"n": 0}


def _late_every_other():
    _alt["n"] += 1
    return None if _alt["n"] % 2 == 0 else _g4.look()


_far = {(6, 2)}
ic.press, ic.time.sleep = _g4.press, lambda *_a: None
try:
    _p4 = ic.select_bans_verified(GRID, _far, look=_late_every_other,
                                  confirm_ban=lambda pos: pos in _g4.banned,
                                  log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = _real_press, _real_sleep
check(sorted(_p4) == sorted(_far) and _g4.banned == _far,
      f"a far target with a late frame on every other look was not reached: placed "
      f"{sorted(_p4)}, banned {sorted(_g4.banned)} — moves and waits must not share a budget")

print("\n9. A WRONG BAN IS CAUGHT AT THE PRESS THAT MADE IT")
# ban_x_on asks "is there an X where I THINK I am" and throws away the rest of what
# banned_cells found. When a STALE frame puts the cursor elsewhere, the X lands on a
# different card, ban_x_on looks at the intended cell, sees nothing, and reports the
# target as MISSING -- so a wrong ban is logged as a missing ban and read_ban_counter
# still says 3/3. Exhaustive search over 10,927 late-frame combinations: 126 wrong-ban
# outcomes, 75 of them ending with three bans, one wrong, and a 3/3 counter.
_g5 = Grid()
_stale = {"n": 0}


def _stale_column_look():
    """Reports the cursor ONE COLUMN AHEAD of where it really is.

    That is what a late frame after a HORIZONTAL press looks like: the press has been
    sent and the halo has not moved yet, so the reader confidently returns the cell the
    cursor is about to leave -- and the navigator, comparing against its target, decides
    it has ARRIVED one press early. A VERTICAL press mid-travel is safe by contrast: the
    scrollbar is unreadable, so the whole read is refused. That asymmetry is the hole.

    The stale read has to fire BEFORE the cursor arrives, or the press lands on the
    right card anyway and the fixture proves nothing -- a first version reported the
    correct cell for four looks and banned the target correctly.
    """
    _stale["n"] += 1
    return (_g5.r, min(_g5.cols - 1, _g5.c + 1))


_wrong = []
_real_press, _real_sleep = ic.press, ic.time.sleep
ic.press, ic.time.sleep = _g5.press, lambda *_a: None
try:
    _p5 = ic.select_bans_verified(
        GRID, {(0, 2)}, look=_stale_column_look,
        banned_set=lambda: set(_g5.banned),
        on_wrong_ban=lambda want, got: _wrong.append((want, sorted(got))),
        log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = _real_press, _real_sleep

check(bool(_wrong),
      f"a stale COLUMN read banned {sorted(_g5.banned)} while aiming at (0, 2) and "
      "nothing noticed — that is a card the engine never chose, in a $50 match, with "
      "the counter still reading 3/3")
check((0, 2) not in _p5,
      f"the wrong ban was REPORTED AS PLACED ({_p5}) — choose_bans would believe the "
      "engine's pick landed")
if _wrong:
    _want, _got = _wrong[0]
    check(_want == (0, 2) and _got and _got[0] != (0, 2),
          f"the report must name the card actually banned, got want={_want} got={_got}")

# CONTROL: a healthy sensor must NOT report a wrong ban, or every run would.
_g6 = Grid()
_wrong6 = []
ic.press, ic.time.sleep = _g6.press, lambda *_a: None
try:
    _p6 = ic.select_bans_verified(GRID, WANT, look=_g6.look,
                                  banned_set=lambda: set(_g6.banned),
                                  on_wrong_ban=lambda w, g: _wrong6.append((w, g)),
                                  log=lambda *a: None)
finally:
    ic.press, ic.time.sleep = _real_press, _real_sleep
check(not _wrong6 and _g6.banned == WANT and sorted(_p6) == sorted(WANT),
      f"CONTROL: a healthy run reported wrong bans {_wrong6}, banned "
      f"{sorted(_g6.banned)}, placed {sorted(_p6)} — the check is firing on correct runs")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
