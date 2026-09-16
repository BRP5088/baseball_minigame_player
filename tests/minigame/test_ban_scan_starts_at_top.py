"""The ban scan must start at scroll level 0, or refuse to cache what it read.

OPEN-23's mechanism, found live 2026-09-16. `top_row` is derived from the
PRESS COUNT as `presses_so_far - 1`, which is a row number only if the grid
began at row 0. After an earlier scan, a cursor walk or a ban placement it does
not: three consecutive live scans on a grid parked at level 3+ returned 10, 6
and 14 cards of 25, every one from rows 3-6.

The scrollbar cross-check already in the scan cannot save this. It relabels a
row it can SEE; it cannot conjure a row the viewport never visited. So the scan
returned a fragment and choose_bans picked the best three of it, with nothing
downstream able to tell a fragment from the whole collection.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


class Rig:
    """Stubs every screen/​input call _ban_scroll_to_top makes."""

    def __init__(self, levels):
        self.levels = list(levels)   # what the scrollbar reads, in order
        self.presses = []

    def install(self):
        self.saved = {n: getattr(o, n) for n in
                      ("read_ban_scroll_level", "capture_screenshot_image",
                       "press", "wait_for_screen_to_settle")}
        o.capture_screenshot_image = lambda *a, **k: "FRAME"
        o.press = lambda a, *rest, **k: self.presses.append(a)
        o.wait_for_screen_to_settle = lambda *a, **k: None
        o.read_ban_scroll_level = self._level
        return self

    def _level(self, _img):
        return (self.levels.pop(0) if self.levels else 0), 123

    def restore(self):
        for n, v in self.saved.items():
            setattr(o, n, v)


# 1. Already at the top: no presses at all. A scroll-to-top that always presses
#    would walk the cursor for nothing on every scan.
r = Rig([0]).install()
try:
    got = o._ban_scroll_to_top()
finally:
    r.restore()
check(got == (True, 0) and r.presses == [],
      f"already at level 0 -> {got}, presses {r.presses} (must be none)")

# 2. Parked at level 3, arrives at 0. The live case, exactly.
r = Rig([3, 2, 1, 0]).install()
try:
    got = o._ban_scroll_to_top()
finally:
    r.restore()
check(got == (True, 0) and r.presses == ["move_up"] * 3,
      f"level 3 -> {got} after {len(r.presses)} move_up presses")

# 3. A None reading is MID-ANIMATION, not "not at the top". The live probe read
#    None at thumb 650/566/484/483/400 and only 350 mapped to level 0 -- so a
#    loop that gives up on None gives up on nearly every real scroll.
r = Rig([None, None, None, 0]).install()
try:
    got = o._ban_scroll_to_top()
finally:
    r.restore()
check(got == (True, 0) and len(r.presses) == 3,
      f"None readings keep pressing -> {got} after {len(r.presses)} presses")

# 4. Never arrives: it must SAY so rather than claim the top. This is the whole
#    point -- a false "we're at the top" is how the fragment got scanned.
r = Rig([5] * 40).install()
try:
    got = o._ban_scroll_to_top(max_presses=4)
finally:
    r.restore()
check(got == (False, 5), f"stuck at level 5 -> {got} (must report False)")
check(len(r.presses) == 4, f"honours max_presses: {len(r.presses)} presses, want 4")

# 5. THE MONEY CHECK, behavioural, WITH ITS CONTROL. A scan that could not reach
#    the top must not populate the cache -- a cached fragment is served to every
#    later ban screen in the process with zero captures.
#
#    THE FIRST VERSION OF THIS CHECK COULD NOT FAIL, and the mutant said so. It
#    passed `use_cache=False`, so the cache was never written on ANY path, and it
#    returned 0 cards, which trips the independent `len < 3` floor as well. Two
#    reasons to pass, neither of them the one under test. The control below is
#    what makes the check mean anything: the SAME scan, differing only in whether
#    the top was reached, must cache in one arm and not the other.
def scan(reached_top):
    """Run the real scan with only the top-of-grid answer varying."""
    o._cached_ban_collection = None
    names = {(r, c): _Card(f"c{r}{c}", 5, 1) for r in (0, 1) for c in range(5)}
    saved = {n: getattr(o, n) for n in
             ("_ban_scroll_to_top", "capture_screenshot_image", "press",
              "wait_for_screen_to_settle", "detect_ban_grid_locked",
              "_settled_lock_grid", "read_ban_scroll_level", "record_observation",
              "KNOWN_BAN_ROSTER")}
    try:
        o._ban_scroll_to_top = lambda *a, **k: (reached_top, 0 if reached_top else 3)
        o.capture_screenshot_image = lambda *a, **k: "FRAME"
        o.press = lambda *a, **k: None
        o.wait_for_screen_to_settle = lambda *a, **k: None
        o.detect_ban_grid_locked = lambda *a, **k: [[False] * 5, [False] * 5]
        o._settled_lock_grid = lambda *a, **k: ("FRAME", [[False] * 5, [False] * 5])
        o.read_ban_scroll_level = lambda *a, **k: (0, 123)
        o.record_observation = lambda **k: None
        o.KNOWN_BAN_ROSTER = names
        cards = o.read_full_ban_collection(max_presses=0, use_cache=True,
                                           trust_roster=True)
    finally:
        for n, v in saved.items():
            setattr(o, n, v)
    return cards, o._cached_ban_collection


from decision_engine import PlayerCard as _Card

ok_cards, ok_cache = scan(reached_top=True)
bad_cards, bad_cache = scan(reached_top=False)
o._cached_ban_collection = None

# Both arms must return the SAME cards, and enough of them to clear the `len < 3`
# floor -- otherwise the floor, not the top-of-grid answer, is doing the work.
check(len(ok_cards) >= 3 and len(bad_cards) == len(ok_cards),
      f"both arms return the same {len(ok_cards)} cards, clear of the <3 floor "
      f"(fragment arm returned {len(bad_cards)})")

# THE CONTROL: reaching the top must actually cache. If this fails, the check
# below proves nothing -- it would pass on a scan that never caches at all.
check(ok_cache is not None,
      f"CONTROL: a scan that DID reach the top caches its result "
      f"({len(ok_cache) if ok_cache else 0} cards)")

check(bad_cache is None,
      f"a scan that never reached the top is NOT cached "
      f"(cache holds {bad_cache!r})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
