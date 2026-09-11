"""THE CARD PLAYED MUST BE THE CARD CHOSEN, and the loop must prove it before committing.

select_and_play() sent eight BLIND presses -- home four left, walk N right, select,
confirm -- and never looked. Measured live on 2026-09-10, three plays:

    asked index 4 (a power 8)   a power-4 was played
    asked index 2 (a power 6)   the power-4 at index 1 was played
    asked index 2 (a power 6)   correct

Intermittent, not a fixed off-by-one, so no arithmetic correction can fix it. The
frame captured at the instant of the second miss shows the cursor sitting at index 0
while the code believed 2: ONE move_right was swallowed. The same swallowed press one
step later eats select_card instead, confirm_play fires into nothing, no reveal
arrives and the loop stalls ~35 s. One bug, two faces.

The fix is to look. The game answers both questions on screen, with two different
signals (the user, watching the stream): the cursor HOVERING a card makes it GLOW;
the card being SELECTED makes it LIFT.

The fixtures are real frames with adjudicated ground truth, not synthetic:
  cursor_on_1.png       the user, watching the live screen: "currently the 6 card is
                        glowing" -- the 6 is at index 1
  cursor_on_2.png       one move_right later. Not merely asserted: the select that
                        followed lifted index 2 by 44 px and the 9 that lives there
                        is the card the reveal shows on the mound
  selected_index_2.png  that select, mid-lift
"""
import os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image
import local_hand as lh
import input_controller as ic

FIX = os.path.join(_ROOT, "test_fixtures", "hand_cursor")
_fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        _fails.append(msg)


# =========================================================================
print("1. the sensor names the slot the USER said the cursor was on")
# =========================================================================
# GROUND TRUTH THE DETECTOR DID NOT PRODUCE. An earlier version of this file scored
# against frames the detector itself had labelled, and it passed while reading 4 of 9
# on a real sweep -- it was blind to TACTICS cards, so every tactics frame went into
# the "no cursor" pile and the census reported healthy headroom (CLAUDE.md 31).
# These nine come from a sweep where the user named the slot after every press; the
# truth is in each FILENAME, so nothing here can drift back to self-labelling.
SWEEP = [("sweep_f00_slot2.png", 2), ("sweep_f01_slot1.png", 1), ("sweep_f02_slot0.png", 0),
         ("sweep_f03_slot0.png", 0), ("sweep_f04_slot0.png", 0), ("sweep_f05_slot1.png", 1),
         ("sweep_f06_slot2.png", 2), ("sweep_f07_slot3.png", 3), ("sweep_f08_slot4.png", 4)]
_wins, _all_glows = [], []
for fname, truth in SWEEP:
    got, glow, _ = lh.cursor_glow(Image.open(os.path.join(FIX, fname)))
    check(got == truth, f"{fname}: read {got}, the user says {truth} — glow {glow}")
    _wins.append(glow[truth])
    _all_glows.append((glow, truth))

# SLOTS 0 AND 2 ARE THE TACTICS CARDS and they are the ones the old geometry could not
# see at all. Four of the nine cover them, deliberately: a version that reads only
# player cards scores 5/9 here and fails.
check(sum(1 for _, t in SWEEP if t in (0, 2)) >= 4,
      "the sweep covers the tactics slots, which is where the old reader scored 0/4")

idx1, glow1, rows1 = lh.cursor_glow(Image.open(os.path.join(FIX, "cursor_on_1.png")))
check(idx1 == 1, f"cursor_on_1: cursor_glow says {idx1}, the user says index 1 — glow {glow1}")
check(str(rows1[1].get("digit")) == "6", f"and index 1 holds the 6 (got {rows1[1].get('digit')})")

idx2, glow2, rows2 = lh.cursor_glow(Image.open(os.path.join(FIX, "cursor_on_2.png")))
check(idx2 == 2, f"cursor_on_2: cursor_glow says {idx2}, expected 2 — glow {glow2}")

# THE GATE IS A FLOOR UNDER THE POSITIVES, NOT A SEPARATION, and the comment in
# local_hand.py says so: there is essentially no negative population, because the
# cursor is on some slot on every turn frame we have. This pins that the floor is
# genuinely below every true reading, with margin -- pinned as a LITERAL so raising
# the constant cannot make its own guard pass (CLAUDE.md 10.11).
# THE GATE MUST SIT BETWEEN THE TWO MEASURED POPULATIONS (CLAUDE.md 10.4), and the
# first version of this check did NOT test that: it only asked whether the gate was
# below the true readings, which any small number satisfies. It passed at 3.0 while
# a tactics card's own artwork read a constant 6.1-6.5 and was named "the cursor"
# live. The ceiling of the FALSE readings is what decides the gate.
_false_ceiling = max(max(v for i, v in enumerate(glow) if i != truth)
                     for glow, truth in _all_glows)
check(_false_ceiling < lh.CURSOR_GLOW_MIN <= min(_wins),
      f"CURSOR_GLOW_MIN {lh.CURSOR_GLOW_MIN} sits BETWEEN the highest non-cursor "
      f"reading {_false_ceiling:.1f} and the lowest true reading {min(_wins):.1f}")
# PINNED AS A LITERAL BAND so raising the constant cannot make its own guard pass
# (CLAUDE.md 10.11). It was 6.0-9.0 when the gate was 7.5; that gate rejected 8 CORRECT
# slot-0 readings, which read 2.7-4.4 against every other slot's 12-18. The band moved
# because the evidence did, not to accommodate the constant.
check(12.0 <= lh.CURSOR_GLOW_MIN <= 18.0,
      f"the gate sits between two MEASURED populations — every other card tops out at 8.4 "
      f"and the faintest true cursor card reads 20.7, over 74 labelled frames — got "
      f"{lh.CURSOR_GLOW_MIN}")
check(lh.CURSOR_GLOW_MIN < 20.7,
      f"and it admits the faintest true reading on disk (20.7, sweep_f08 slot 4)")
# THE WINDOW ITSELF IS PINNED AS LITERALS, because the gate above is only reachable from
# this geometry: at the old (110,10,70,30) the two populations OVERLAP (8.7 vs 9.7) and no
# gate exists at all. Changing the window without re-measuring must fail here.
check((lh.GLOW_XL, lh.GLOW_XR, lh.GLOW_DY0, lh.GLOW_DY1) == (80, 0, 55, 35),
      f"the glow window is the measured one, not the backdrop-sampling original "
      f"(got {(lh.GLOW_XL, lh.GLOW_XR, lh.GLOW_DY0, lh.GLOW_DY1)})")
check(not hasattr(lh, "CURSOR_DOMINANCE"),
      "CURSOR_DOMINANCE is gone — a constant nothing reads is how a measured failure "
      "comes back (CLAUDE.md's booby-trapped duplicates)")

# THIS FIXTURE WAS MISLABELLED BY ME, AND THE CHECK ON IT PINNED THE WRONG BEHAVIOUR.
# It was called "no_cursor" and asserted to ABSTAIN -- because the detector abstained on
# it, which is the only reason I filed it as a negative. The user looked at it and said
# the cursor is plainly on slot 0. A census labelled by the detector under test is
# worthless (CLAUDE.md 31), and I did it while quoting that entry.
#
# It is the faintest true slot-0 reading on disk, so it is kept as exactly that.
faint_idx, faint_glow, faint_rows = lh.cursor_glow(
    Image.open(os.path.join(FIX, "cursor_on_slot0_faint.png")))
check(faint_glow.index(max(faint_glow)) == 0,
      f"the faintest slot-0 frame: argmax names slot 0 (glow {faint_glow})")
check(faint_idx == 0,
      f"and the gate lets it through rather than abstaining (got {faint_idx}) — it used "
      f"to be rejected at 3.0 against a gate of 7.5")

# =========================================================================
print("2. the LIFT names the selected card, and it is the stronger signal")
# =========================================================================
_, _, rows_sel = lh.cursor_glow(Image.open(os.path.join(FIX, "selected_index_2.png")))
y_before = [r.get("y") for r in rows2]
y_after = [r.get("y") for r in rows_sel]
risen = lh.lifted_cards(y_before, y_after)
check(risen == [2], f"exactly index 2 rose: {risen}  (before {y_before} after {y_after})")
check((y_before[2] - y_after[2]) >= 40,
      f"and it rose {y_before[2] - y_after[2]}px — far above the {lh.SELECT_LIFT_MIN_PX}px gate")

# A CARD THAT MOVES DOWN IS NOT SELECTED, and the direction has to be asserted
# separately: every check above passes with the sign thrown away (abs()), which is
# exactly the mutant that SURVIVED the first Snoopy sweep. A surviving mutant means
# the test is decorative, not that the mutant is harmless (CLAUDE.md 10.9).
check(lh.lifted_cards([100, 100, 100, 100, 100], [100, 100, 144, 100, 100]) == [],
      "a card that DROPS 44px is not reported as lifted")
check(lh.lifted_cards([100, 100, 100, 100, 100], [100, 100, 56, 100, 100]) == [2],
      "and the same 44px in the other direction still is")


# =========================================================================
print("3. the loop CORRECTS a swallowed press instead of playing the wrong card")
# =========================================================================
class FakeScreen:
    """A hand of 5 whose cursor moves when a press lands -- and sometimes does not."""

    REST = [200, 160, 150, 165, 220]

    def __init__(self, start=0, drop=()):
        self.cur, self.drop, self.n = start, set(drop), 0
        self.y = list(self.REST)
        self.sent = []

    def press(self, key):
        self.sent.append(key)
        if key in ("move_left", "move_right"):
            self.n += 1
            if self.n in self.drop:          # the swallowed keystroke
                return
            self.cur += 1 if key == "move_right" else -1
            self.cur = max(0, min(4, self.cur))
        elif key == "select_card":
            self.y[self.cur] -= 44           # a selected card RISES

    def selected(self):
        return [i for i, y in enumerate(self.y) if self.REST[i] - y >= 25]

    def look(self):
        # A SELECTED CARD WAS BELIEVED TO KEEP GLOWING -- "14.8 while lifted" -- and that
        # was the WINDOW, not the screen: it sat in the backdrop above each card and caught
        # the card's own white top rim, so the reading tracked how HIGH a card sat. On the
        # rim (local_hand GLOW_DY0/DY1) a selected-but-unhovered card reads at most 5.7
        # over 74 labelled frames. The fake screen models the measured numbers, so it stays
        # at least as hard as the real one.
        glow = [0.0] * 5
        for i in self.selected():
            glow[i] = 5.7          # a SELECTED card that is not hovered: measured max 5.7
        glow[self.cur] = 30.0      # the card holding the cursor: measured 20.7 - 36.1
        return glow, list(self.y), 5, self.selected()


def run(target, start=0, drop=(), tactics=None):
    fs = FakeScreen(start, drop)
    old = ic.press
    ic.press = fs.press
    try:
        ok = ic.select_and_play(target, tactics, look=fs.look)
    finally:
        ic.press = old
    return ok, fs


ok, fs = run(target=2, start=0, drop=())
check(ok is True and fs.cur == 2 and "confirm_play" in fs.sent,
      f"clean run: reached {fs.cur}, committed={'confirm_play' in fs.sent}")

ok, fs = run(target=2, start=0, drop=(1,))       # the first move_right is swallowed
check(ok is True and fs.cur == 2,
      f"one swallowed move_right: still landed on {fs.cur}, expected 2")
check(fs.sent.count("move_right") == 3,
      f"and it noticed and pressed again — {fs.sent.count('move_right')} move_right for a "
      f"2-slot walk (2 + 1 correction)")
check(fs.y.index(min(fs.y)) == 2, f"the card that lifted is index {fs.y.index(min(fs.y))}")

ok, fs = run(target=1, start=4, drop=(2,))       # walking LEFT, one swallowed
check(ok is True and fs.cur == 1, f"swallowed move_left: landed on {fs.cur}, expected 1")

# THE BUG AS IT ACTUALLY HAPPENED: cursor at 0, code believes it walked to 2.
# The blind path plays index 1. The verified path must not.
ok, fs = run(target=2, start=0, drop=(2,))
check(ok is True and fs.cur == 2,
      f"the live failure reproduced: landed on {fs.cur}, expected 2 (blind play gave 1)")


# =========================================================================
print("4. it REFUSES rather than committing something it could not verify")
# =========================================================================
def run_look(target, look):
    sent = []
    old = ic.press
    ic.press = lambda k: sent.append(k)
    try:
        ok = ic.select_and_play(target, None, look=look)
    finally:
        ic.press = old
    return ok, sent

ok, sent = run_look(2, lambda: ([0.0] * 5, [200, 160, 150, 165, 220], 5, []))
check(ok is False and "confirm_play" not in sent,
      f"nothing glowing -> refused={ok is False}, confirm_play not sent="
      f"{'confirm_play' not in sent}")

ok, sent = run_look(2, lambda: ([30.0, 0, 0, 0, 0], [200, 160, 150, 165, 220], 3, []))
check(ok is False and "confirm_play" not in sent,
      f"a 3-row hand (mid-deal) -> refused={ok is False}, no commit="
      f"{'confirm_play' not in sent}")

# A cursor that never moves however many times it is pressed: the press path is dead.
# It must give up, and it must NOT commit whatever it happens to be sitting on.
ok, sent = run_look(2, lambda: ([30.0, 0, 0, 0, 0], [200, 160, 150, 165, 220], 5, []))
check(ok is False and "confirm_play" not in sent,
      f"cursor never moves -> refused={ok is False}, no commit={'confirm_play' not in sent}")
check(sent.count("move_right") <= ic.CURSOR_MAX_STEPS,
      f"and it stopped after {sent.count('move_right')} presses, "
      f"cap {ic.CURSOR_MAX_STEPS}")

# THE SELECT ITSELF CAN BE SWALLOWED -- this is the STALL. Nothing lifts, so nothing
# may be confirmed; the old code fired confirm_play into an empty table and waited.
class DeadSelect(FakeScreen):
    def press(self, key):
        if key == "select_card":
            self.sent.append(key)            # swallowed: no lift
            return
        super().press(key)

fs = DeadSelect(0)
old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_play(2, None, look=fs.look)
finally:
    ic.press = old
check(ok is False and "confirm_play" not in fs.sent,
      f"select_card swallowed EVERY time (the 35s stall) -> refused={ok is False}, "
      f"no commit={'confirm_play' not in fs.sent}")
check(fs.sent.count("select_card") == ic.SELECT_ATTEMPTS,
      f"and it tried {fs.sent.count('select_card')} times, not once "
      f"(SELECT_ATTEMPTS={ic.SELECT_ATTEMPTS})")


# A SWALLOWED SELECT THAT LANDS ON THE RETRY. Measured live: 1 select press in 5 never
# reached the console, the frames before and after pixel-identical. Retrying is only safe
# because the lift confirms each attempt -- a blind second press would DESELECT a card
# that had in fact landed.
class FlakySelect(FakeScreen):
    def __init__(self, start=0, swallow_first=True):
        super().__init__(start)
        self.swallowed = not swallow_first

    def press(self, key):
        if key == "select_card" and not self.swallowed:
            self.swallowed = True
            self.sent.append(key)          # the console never sees it
            return
        super().press(key)


fs = FlakySelect(0)
old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_play(2, None, look=fs.look)
finally:
    ic.press = old
check(ok is True and "confirm_play" in fs.sent,
      f"first select swallowed, second lands -> committed={ok is True}")
check(fs.sent.count("select_card") == 2,
      f"exactly two select presses, not more ({fs.sent.count('select_card')})")
check(fs.y.index(min(fs.y)) == 2,
      f"and the card that ended up lifted is index {fs.y.index(min(fs.y))}")


# =========================================================================
print("5. a tactics card is verified the same way")
# =========================================================================
ok, fs = run(target=1, start=0, drop=(), tactics=3)
check(ok is True and fs.cur == 3, f"walked on to the tactics slot: {fs.cur}, expected 3")
check(sorted([i for i, y in enumerate(fs.y) if y < [200, 160, 150, 165, 220][i]]) == [1, 3],
      "both the player card and the tactics card are lifted")


# =========================================================================
print("6. look=None still walks the old blind path, byte for byte")
# =========================================================================
sent = []
old = ic.press
ic.press = lambda k: sent.append(k)
try:
    ic.invalidate_cursor()
    ic.select_and_play(3)
finally:
    ic.press = old
check(sent == ["move_left"] * 4 + ["move_right"] * 3 + ["select_card", "confirm_play"],
      f"blind path unchanged: {sent}")


# =========================================================================
print("7. a DISCARD is verified the same way -- it is the irreversible one")
# =========================================================================
# This function's docstring records a discard landing on the wrong card live, and
# it is worse than a wrong play: confirm_discard throws the card AND the game then
# auto-lifts the replacement, which confirm_play commits as this turn's play. Two
# commitments behind one unverified press.
fs = FakeScreen(0)
old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_discard(2, look=fs.look)
finally:
    ic.press = old
check(ok is True and fs.cur == 2 and "confirm_discard" in fs.sent,
      f"verified discard reached {fs.cur} and threw it")

fs = FakeScreen(0, drop=(1,))
old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_discard(2, look=fs.look)
finally:
    ic.press = old
check(ok is True and fs.cur == 2,
      f"a swallowed press mid-discard: still threw index {fs.cur}, expected 2")

sent = []
old = ic.press
ic.press = lambda k: sent.append(k)
try:
    ok = ic.select_and_discard(2, look=lambda: ([0.0] * 5, [200, 160, 150, 165, 220], 5, []))
finally:
    ic.press = old
check(ok is False and "confirm_discard" not in sent and "confirm_play" not in sent,
      f"cannot see the cursor -> refused, nothing thrown and nothing played: {sent}")

sent = []
old = ic.press
ic.press = lambda k: sent.append(k)
try:
    ic.invalidate_cursor()
    ic.select_and_discard(3)
finally:
    ic.press = old
check(sent == ["move_left"] * 4 + ["move_right"] * 3
      + ["select_card", "confirm_discard", "confirm_play"],
      f"blind discard unchanged: {sent}")


# =========================================================================
print("8. it LOOKS AFTER the animation, not during it")
# =========================================================================
# THE REGRESSION THIS PINS. The standalone spike slept after every press and ran
# correctly on the console; moving that logic into input_controller dropped both
# sleeps, and the very first live run mis-read a frame captured mid-slide. The user
# named it from the stream: "it quickly selected slot 1, mid animation of moving up
# deselected it." A card in motion puts its disc between two positions, so the glow
# box -- anchored on that disc -- reads pixels belonging to neither.
import time as _time

_events = []
_real_sleep = ic.time.sleep


class TimedScreen(FakeScreen):
    def press(self, key):
        _events.append(("press", key))
        super().press(key)


fs = TimedScreen(0)
_old_press, _old_sleep = ic.press, ic.time.sleep
ic.press = fs.press
ic.time.sleep = lambda d: _events.append(("sleep", d))
try:
    ic.select_and_play(2, 3, look=fs.look)
finally:
    ic.press, ic.time.sleep = _old_press, _old_sleep

# every move and every select must be followed by a settle before the next look
_bad = []
for i, (kind, val) in enumerate(_events):
    if kind != "press":
        continue
    want = (ic.MOVE_SETTLE_SEC if val in ("move_left", "move_right")
            else ic.SELECT_SETTLE_SEC if val == "select_card" else None)
    if want is None:
        continue
    nxt = _events[i + 1] if i + 1 < len(_events) else None
    if not (nxt and nxt[0] == "sleep" and nxt[1] >= want):
        _bad.append((val, nxt))
check(not _bad, f"every move/select is followed by its settle before the next look "
                f"(offenders: {_bad})")
check(ic.MOVE_SETTLE_SEC >= 0.3 and ic.SELECT_SETTLE_SEC >= 0.5,
      f"the settles are the spike's measured values, not token ones "
      f"({ic.MOVE_SETTLE_SEC}, {ic.SELECT_SETTLE_SEC})")


# =========================================================================
print("9. a position that was never measured is not reported as one")
# =========================================================================
# THE COINCIDENCE THAT HID A BUG FOR AN HOUR. find_tactics stops matching a tactics
# card once it is SELECTED, so the row falls through to a branch that fills y from
# SLOT_PLAYER[i] -- and for slot 0 that constant equals the card's own resting
# position. A completely lost card therefore read as a perfectly stable one, the
# lift check compared a constant with itself, and it could never fire (10.1).
_un = lh.read_hand(Image.open(os.path.join(FIX, "tactics_unselected_slot0.png")))
_sel = lh.read_hand(Image.open(os.path.join(FIX, "tactics_selected_slot0.png")))
check(_un[0].get("y_measured") is True,
      f"unselected tactics card: position IS measured (y={_un[0].get('y')})")
check(_sel[0].get("y_measured") is True,
      f"SELECTED tactics card is found too, by the second pass (y={_sel[0].get('y')})")

# AND IT MOVED. The whole point: before the second pass this row fell back to a slot
# constant of 203 -- the card's own resting position -- so a card that had risen 44px
# reported not moving at all. A tactics card lifts exactly like a player card.
_lift = _un[0].get("y") - _sel[0].get("y")
check(38 <= _lift <= 50,
      f"the selected tactics card rose {_lift}px, in the same 44px band as a player card")
check(lh.lifted_cards([r.get("y") for r in _un], [r.get("y") for r in _sel]) == [0],
      "and lifted_cards names slot 0 — the check that could never fire on tactics before")

# THE FIRST PASS MUST STILL BE THE ONE THAT ANSWERS on an unselected card: the second
# pass may only ADD a reading, never change one, or it would silently re-decide every
# frame this reader has ever handled.
check(lh.find_tactics(Image.open(os.path.join(FIX, "tactics_unselected_slot0.png"))),
      "the unselected card is still found by the ORIGINAL threshold, untouched")
check(not lh.find_tactics(Image.open(os.path.join(FIX, "tactics_selected_slot0.png"))),
      "and the selected one is still invisible to it — so the second pass is what "
      "found it, not a loosened first pass")
check(lh.SELECTED_DARK_MAX > 119,
      f"SELECTED_DARK_MAX {lh.SELECTED_DARK_MAX} clears the selected wreath's p05 of 119")

# A ROW THAT STILL HAS NO MEASURED POSITION MUST NOT ANCHOR THE GLOW BOX. The second
# pass rescues selected tactics cards, so no fixture on disk produces this row any
# more -- and a mutant deleting the guard therefore SURVIVED the whole file. A guard
# that nothing exercises is not a guard, so the case is constructed rather than waited
# for: a slot nothing reached still falls back to a constant, and sampling there reads
# the pixels where the card used to be.
_rows = lh.read_hand(Image.open(os.path.join(FIX, "cursor_on_1.png")))
_faked = [dict(r) for r in _rows]
_faked[1]["y_measured"] = False          # the glowing card, now with an unmeasured y
_i_ok, _g_ok, _ = lh.cursor_glow(Image.open(os.path.join(FIX, "cursor_on_1.png")), _rows)
_i_no, _g_no, _ = lh.cursor_glow(Image.open(os.path.join(FIX, "cursor_on_1.png")), _faked)
check(_g_ok[1] > lh.CURSOR_GLOW_MIN and _g_no[1] == 0.0,
      f"the same card scores {_g_ok[1]} when its position is measured and "
      f"{_g_no[1]} when it is not")
check(_i_no != 1,
      f"and it is no longer named as the cursor (got {_i_no})")


# =========================================================================
print("10. one lit card is the cursor; two lit means one is merely SELECTED")
# =========================================================================
# A SELECTED CARD KEEPS GLOWING -- slot 1 read 14.8 while selected and raised, live.
# So "brightest card" stops meaning "the cursor is here" the moment anything is
# selected, which is precisely the state a SECOND selection has to start from. The
# user's rule, from watching the screen: look at every card, and when two are lit the
# one that has NOT risen is the one holding the cursor.
G = lh.CURSOR_GLOW_MIN
# THE RULE IS NOW ONE LINE: the brightest card, if it clears the gate. The two rules that
# used to live here (subtract the SELECTED cards; require a 2.0x dominance) were artefacts
# of a window that read the backdrop -- see cursor_slot's docstring. These checks pin the
# behaviour that replaced them, with LITERAL readings taken from the measured populations
# (true 20.7-36.1, everything else 0.0-8.4) rather than from the constant (CLAUDE.md 10.11).
check(lh.cursor_slot([0, 25, 0, 0, 0], []) == 1, "one lit card, nothing selected -> cursor there")
check(lh.cursor_slot([0, 25, 0, 0, 0], [1]) == 1,
      "one lit card which is ALSO selected -> still the cursor")
check(lh.cursor_slot([0, 0, 27, 0, 0], [2]) == 2,
      "THE LIVE FALSE RESULT, 2026-09-11: the cursor sits on the ONE selected card. The old "
      "rule subtracted it and named slot 1 off a 4.5 backdrop reading; argmax names slot 2")
check(lh.cursor_slot([0, 5.7, 30, 0, 0], [1]) == 2,
      "a SELECTED but un-hovered card reads at most 5.7 and cannot outvote the real cursor")
check(lh.cursor_slot([0, 0, 0, 0, 0], []) is None, "nothing lit -> abstain")
check(lh.cursor_slot([8.4, 0, 0, 0, 0], []) is None,
      "the LOUDEST false reading measured anywhere (8.4, cursor_on_1 slot 0) is refused")
check(lh.cursor_slot([20.7, 0, 0, 0, 0], []) == 0,
      "and the FAINTEST true reading measured anywhere (20.7, sweep_f08 slot 4) is admitted")
check(lh.cursor_slot([0, 30, 28, 0, 0], []) == 1,
      "two genuinely lit cards cannot happen on one screen, but if they did the brighter "
      "wins rather than the reader abstaining -- the old dominance rule refused this and "
      "stalled a live match at glow [5.2, 6.8, 0.0, 0.2, 8.1]")
check(lh.cursor_slot([], []) is None, "an empty read is not a slot")
# A HAND WITH MORE ROWS THAN THE FAN HAS SLOTS MUST NOT CRASH THE READER. read_hand's
# ungated path appends one row per strong disc plus one per unmatched tactics blob, with no
# cap, while SLOT_PLAYER/SLOT_TACTICS hold five -- so a six-row read indexed SLOT_PLAYER[5].
# Found by the QA sweep on 2026-09-11, hours after the comprehension that caused it shipped.
# It degrades to a retry rather than a wrong card (orchestrator catches and re-polls), but a
# reader that raises cannot abstain, and abstaining is the whole contract here.
_wide = [{"x": 100 + 90 * i, "y": 200, "kind": "player", "y_measured": True} for i in range(7)]
_probe = Image.new("L", (1020, 307), 40)
try:
    _iw, _gw, _ = lh.cursor_glow(_probe, _wide)
    check(len(_gw) == 7 and _iw is None,
          f"seven rows read without raising, and nothing is named the cursor on a blank "
          f"probe (got index {_iw}, {len(_gw)} readings)")
    # CHECK THE BOX, NOT THE READING. A row past the fan that BORROWS slot 0's anchor still
    # reads 0.0 on a blank probe, so a reading-only check cannot tell the two apart -- that
    # mutant survived when this was written, which is exactly what makes a check decorative.
    # A row with no slot must get NO WINDOW at all.
    _bw = []
    lh.cursor_glow(_probe, _wide, _boxes=_bw)
    check(all(b is None for b in _bw[len(lh.SLOT_PLAYER):]),
          f"and every row PAST the fan's five slots gets NO window rather than borrowing "
          f"another slot's anchor (got {_bw[len(lh.SLOT_PLAYER):]})")
    check(sum(b is not None for b in _bw) == len(lh.SLOT_PLAYER),
          f"exactly five windows are sampled, one per real slot (got "
          f"{sum(b is not None for b in _bw)})")
except IndexError as _e:
    check(False, f"cursor_glow raised IndexError on a {len(_wide)}-row hand: {_e}")
check(lh.cursor_slot([0, G - 0.1, 0, 0, 0], []) is None,
      f"a reading under CURSOR_GLOW_MIN ({G}) is not lit at all")


# =========================================================================
print("11. the reader works at OTHER capture sizes, not just the tuned one")
# =========================================================================
# THE MISTAKE THIS CATCHES, and the user says it keeps happening: every window here was
# first written in RAW PIXELS, tuned at one capture geometry. CLAUDE.md section 3 records
# one session producing both 1867x1050 and 1920x1080 -- a raw-pixel window works perfectly
# on the machine it was tuned on and silently samples the wrong thing everywhere else,
# with no error to notice. Resizing a fixture is the only thing that actually bites.
# HONEST SCOPE. This pins the GLOW WINDOW's scaling, which is what was fixed. It does
# NOT claim the hand reader is scale-free, because it is not: at 0.73x read_hand returns
# a single row (the discs fall under find_circles' size gates) and at 1.25x find_tactics
# misses the wreath, whose blob is checked against 28-48 x 30-50 RAW pixels. Those are
# the same disease one layer down and they predate this work -- see the OPEN note in
# CLAUDE.md section 3. So: wherever the reader still produces a full fan at another
# scale, the cursor must still be named correctly, and the count of cases actually
# exercised is asserted so this cannot pass by silently skipping everything.
_tested = 0
for _fname, _truth in (("sweep_f02_slot0.png", 0), ("sweep_f06_slot2.png", 2),
                       ("sweep_f08_slot4.png", 4)):
    _im = Image.open(os.path.join(FIX, _fname))
    for _factor in (0.9, 1.1, 1.25):
        _re = _im.resize((int(_im.width * _factor), int(_im.height * _factor)),
                         Image.LANCZOS)
        _rows = lh.read_hand(_re)
        if len(_rows) != 5 or any(r.get("y_measured") is False for r in _rows):
            continue                      # the reader below could not fit the fan here
        _tested += 1
        _got, _glow, _ = lh.cursor_glow(_re, _rows)
        check(_got == _truth,
              f"{_fname} at {_factor}x: read {_got}, expected {_truth} — glow {_glow}")
check(_tested >= 4,
      f"the scale check actually ran on {_tested} resized frames, not zero — a version "
      f"that skipped them all would otherwise pass silently")

# and the lift gate is an offset, so it has to scale with the capture too
# (e) THE BOX ITSELF MUST SCALE, and only the GEOMETRY shows it. A mutant forcing
# sc = 1.0 survived every outcome check above: an unscaled box is wrong but still lands
# on the halo at 1.25x, so the answer does not change until it is wrong enough to miss
# entirely. The window is what scaled, so the window is what gets asserted.
_im1 = Image.open(os.path.join(FIX, "sweep_f08_slot4.png"))
_im2 = _im1.resize((int(_im1.width * 1.25), int(_im1.height * 1.25)), Image.LANCZOS)
_b1, _b2 = [], []
lh.cursor_glow(_im1, _boxes=_b1)
lh.cursor_glow(_im2, _boxes=_b2)
# pair BY SLOT: the reader drops a row at 1.25x (its own scale fragility, see the OPEN
# note in CLAUDE.md section 3), so compare only the slots both reads placed a box on.
_pairs = [(p1, p2) for p1, p2 in zip(_b1, _b2) if p1 and p2]
check(len(_pairs) >= 3,
      f"at least three slots got a window in both reads ({len(_pairs)})")
if len(_pairs) >= 3:
    _wr = sum(b[2] - b[0] for _, b in _pairs) / sum(a[2] - a[0] for a, _ in _pairs)
    _hr = sum(b[3] - b[1] for _, b in _pairs) / sum(a[3] - a[1] for a, _ in _pairs)
    check(1.15 <= _wr <= 1.35,
          f"the sampled windows grew {_wr:.2f}x on a 1.25x capture — a box ignoring "
          f"the scale stays at 1.00x")
    check(1.15 <= _hr <= 1.35, f"and so did their heights ({_hr:.2f}x)")

# THE SELECTION GATE IS AN OFFSET TOO, so it scales or it is wrong on another capture.
# A mutant dropping the `* scale` survived every check above, because every fixture on
# disk is at ONE capture size where 25 and 25*1.04 are indistinguishable. Synthetic rows
# put the two apart: at 2x a real rise is twice as big, so the gate must be too.
def _rest_rows(scale):
    """Five player rows sitting exactly on their own anchors -- nothing selected."""
    return [{"kind": "player", "x": 0, "y": lh.SLOT_PLAYER[i][1] * scale,
             "y_measured": True} for i in range(5)]

_rows = _rest_rows(2.0)
check(lh.selected_cards(_rows, 2.0) == [],
      f"rows resting on their anchors report nothing selected "
      f"(got {lh.selected_cards(_rows, 2.0)})")
# slot 1 raised 30px on a 2x capture: UNDER the scaled gate (50), OVER the unscaled (25)
_rows[1]["y"] -= 30
check(lh.selected_cards(_rows, 2.0) == [],
      f"a 30px rise on a 2x capture is NOT a selection — the gate scales to 50 "
      f"(got {lh.selected_cards(_rows, 2.0)})")
_rows[1]["y"] -= 30                              # now 60px up
check(lh.selected_cards(_rows, 2.0) == [1],
      f"and a 60px rise on that same capture IS one "
      f"(got {lh.selected_cards(_rows, 2.0)})")
_rows1 = _rest_rows(1.0)
_rows1[1]["y"] -= 30
check(lh.selected_cards(_rows1, 1.0) == [1],
      "while the same 30px rise at reference scale IS a selection — which is what "
      "makes the scaled and unscaled gates distinguishable at all")

check(lh.lifted_cards([100, 100], [100, 92], scale=1.0) == [1],
      "an 8px rise counts at reference scale")
check(lh.lifted_cards([100, 100], [100, 92], scale=2.0) == [],
      "the same 8px does NOT count on a 2x capture, where a real lift is twice as big")


# =========================================================================
print("12. the cases the mutants found untested")
# =========================================================================
# EVERY CHECK BELOW EXISTS BECAUSE A MUTANT SURVIVED. A surviving mutant means the test
# is decorative, not that the guard is safe (CLAUDE.md 10.9) -- these are the five the
# sweep of 2026-09-10 walked straight through.

# (a) THE MIDPOINT BOUND. Every other fixture has NOTHING selected, so no raised card
# ever bleeds into a neighbour's box and removing the bound cost nothing. This frame is
# the live state the user adjudicated: slot 1 selected and raised, cursor on slot 1,
# and the unbounded box reads 23.5 on slot 2 off slot 1's raised card.
_im = Image.open(os.path.join(FIX, "slot1_selected_cursor_on_1.png"))
_rows = lh.read_hand(_im)
_got, _glow, _ = lh.cursor_glow(_im, _rows)
check(_got == 1, f"a raised neighbour does not steal the cursor: read {_got}, glow {_glow}")
check(_glow[2] == 0.0,
      f"and slot 2 reads 0.0, not the 23.5 an unbounded box picks off slot 1 "
      f"(got {_glow[2]})")

# (b) AN UNGATED READ -- five rows, but no measured positions. read_hand falls back to
# the ungated disc search mid-animation and it can return any count; five is not proof
# of a fan read, and acting on it would anchor every box on nothing.
_sent = []
_old = ic.press
ic.press = lambda k: _sent.append(k)
try:
    _ok = ic.select_and_play(2, None, look=lambda: ([30.0, 0, 0, 0, 0], [None] * 5, 5, []))
finally:
    ic.press = _old
check(_ok is False and not _sent,
      f"a 5-row read with NO measured positions is refused, nothing pressed ({_sent})")


# (c) A SELECT THAT LIFTS THE WRONG CARD must be refused, never retried -- pressing again
# compounds it.
class WrongCard(FakeScreen):
    def press(self, key):
        if key == "select_card":
            self.sent.append(key)
            self.y[(self.cur + 1) % 5] -= 44        # the WRONG card rises
            return
        super().press(key)


fs = WrongCard(0)
_old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_play(2, None, look=fs.look)
finally:
    ic.press = _old
check(ok is False and "confirm_play" not in fs.sent,
      f"wrong card lifted -> refused, nothing committed")
check(fs.sent.count("select_card") == 1,
      f"and it did NOT press again ({fs.sent.count('select_card')} select presses)")


# (d) A LATE PRESS IS NOT A LOST ONE. Measured live: a press landed later than 1.2s.
# Retrying one still in flight presses twice and toggles the card back off. Virtual time
# is accumulated from the sleeps so SELECT_RETRY_CONFIRM_SEC actually decides the outcome.
class LatePress(FakeScreen):
    LATENCY = 1.2

    def __init__(self, start=0):
        super().__init__(start)
        self.clock = 0.0
        self.pending = None

    def sleep(self, d):
        self.clock += d
        if self.pending is not None and self.clock >= self.pending[1]:
            slot = self.pending[0]
            self.y[slot] -= 44                       # it lands, late
            self.pending = None

    def press(self, key):
        if key == "select_card":
            self.sent.append(key)
            if self.pending is None:
                self.pending = (self.cur, self.clock + self.LATENCY)
            return
        super().press(key)


fs = LatePress(0)
_old_press, _old_sleep = ic.press, ic.time.sleep
ic.press = fs.press
ic.time.sleep = fs.sleep
try:
    ok = ic.select_and_play(2, None, look=fs.look)
finally:
    ic.press, ic.time.sleep = _old_press, _old_sleep
check(ok is True and "confirm_play" in fs.sent,
      f"a press landing {LatePress.LATENCY}s late is recognised, not retried "
      f"(committed={'confirm_play' in fs.sent})")
check(fs.sent.count("select_card") == 1,
      f"and exactly ONE select press was sent ({fs.sent.count('select_card')}) — "
      f"a second would have toggled it back off")
check(ic.SELECT_RETRY_CONFIRM_SEC > LatePress.LATENCY - ic.SELECT_SETTLE_SEC,
      f"SELECT_RETRY_CONFIRM_SEC {ic.SELECT_RETRY_CONFIRM_SEC} covers the measured "
      f"late-press window")


# =========================================================================
print("13. it starts from ANY board state, including cards already selected")
# =========================================================================
# THE USER'S ASK: "could you make it work with existing selected cards? saves you time in
# the future and makes it more robust." It used to need a clean board, because "is this
# card lifted" was a before/after comparison and a baseline taken while something was
# already up quietly made the LIFTED position the resting one. Selection is now read
# absolutely, against each slot's own fan anchor (at rest -6.4..9.1, selected 43.1/51.7).

# (a) the target is ALREADY selected -- that is success, and pressing would toggle it OFF
fs = FakeScreen(2)
fs.y[2] -= 44                                  # slot 2 arrives already selected
_old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_play(2, None, look=fs.look)
finally:
    ic.press = _old
check(ok is True and "confirm_play" in fs.sent,
      f"an already-selected target commits without re-pressing ({fs.sent})")
check(fs.sent.count("select_card") == 0,
      f"and select_card was NOT pressed ({fs.sent.count('select_card')}) — a press "
      f"would have deselected it")

# (b) a DIFFERENT card is already selected: the loop must still reach and select its own
fs = FakeScreen(0)
fs.y[4] -= 44                                  # an unrelated card is up
_old = ic.press
ic.press = fs.press
try:
    ok = ic.select_and_play(2, None, look=fs.look)
finally:
    ic.press = _old
check(ok is True and 2 in fs.selected(),
      f"with slot 4 already selected it still selected slot 2 ({fs.selected()})")
check(4 in fs.selected(), "and it left the pre-selected card alone")

# (c) and the absolute reader itself, against the fan anchors
_im = Image.open(os.path.join(FIX, "slot1_selected_cursor_on_1.png"))
_rows = lh.read_hand(_im)
check(lh.selected_cards(_rows, _im.width / lh.ANCHOR_W) == [1],
      f"selected_cards names slot 1 from the anchors alone, with no baseline "
      f"({lh.selected_cards(_rows, _im.width / lh.ANCHOR_W)})")
_im2 = Image.open(os.path.join(FIX, "sweep_f04_slot0.png"))
_rows2 = lh.read_hand(_im2)
check(lh.selected_cards(_rows2, _im2.width / lh.ANCHOR_W) == [],
      "and reports nothing selected on a resting hand")


# =========================================================================
print("14. the cursor's own halo must not counterfeit a power disc")
# =========================================================================
# FOUND BY A BLIND LABELLED BATCH, and it is the first time any reader claimed a card was
# SELECTED when nothing was -- the direction that actually costs a card. With the cursor
# on slot 0, its halo forms a bright round blob that find_circles accepts as a disc (r=22).
# That candidate is rank 3 and outranks the tactics wreath at rank 1, so a SPEED BOOST was
# read as a PLAYER card at y=168 instead of a tactics card at y=205 -- wrong kind, wrong
# anchor table, and 168 then looked like a 35px rise. The banner scored 0.968 on that slot
# in that frame; nothing asked it, because the code only ever demoted tactics -> player.
_bad = Image.open(os.path.join(FIX, "halo_counterfeits_disc_slot0.png"))
_rows = lh.read_hand(_bad)
_sc = _bad.width / lh.ANCHOR_W
check(_rows[0].get("kind") == "tactics",
      f"slot 0 is read as the tactics card it is, not a player card "
      f"(got {_rows[0].get('kind')!r})")
check(_rows[0].get("y") > 190,
      f"and its position comes from the WREATH, not the counterfeit disc at y=168 "
      f"(got {_rows[0].get('y')}) — fixing the kind alone would leave it reading as raised")
check(lh.selected_cards(_rows, _sc) == [3],
      f"so nothing false is reported selected: {lh.selected_cards(_rows, _sc)} "
      f"(the user labelled this frame as slot 3 only)")

# THE CONTROL: the same hand with the cursor elsewhere must be untouched. Without this,
# a promotion that fired on every slot would pass the checks above.
_ok = Image.open(os.path.join(FIX, "same_hand_cursor_elsewhere.png"))
_rows_ok = lh.read_hand(_ok)
check(lh.selected_cards(_rows_ok, _ok.width / lh.ANCHOR_W) == [2],
      f"the same hand with the cursor elsewhere still reads slot 2 selected "
      f"({lh.selected_cards(_rows_ok, _ok.width / lh.ANCHOR_W)})")
check([r.get("kind") for r in _rows_ok] == ["tactics", "player", "player", "player", "player"],
      "and its kinds are unchanged")

# THE BAR IS ABOVE EVERY PLAYER SLOT MEASURED, and stricter than mere presence, because
# this overrides a disc that WAS found. Pinned as literals so raising either constant
# cannot make its own guard pass (CLAUDE.md 10.11).
check(lh.TACTICS_PROMOTE_MIN > 0.695,
      f"TACTICS_PROMOTE_MIN {lh.TACTICS_PROMOTE_MIN} clears the 0.695 maximum seen on a "
      f"player slot over 260 hands")
check(lh.TACTICS_PROMOTE_MIN > lh.TACTICS_PRESENT_MIN,
      f"and is stricter than TACTICS_PRESENT_MIN {lh.TACTICS_PRESENT_MIN}, which only "
      f"asks whether a banner is there at all")


print()
if _fails:
    print(f"FAILED {len(_fails)}")
    for f in _fails:
        print("   -", f)
    sys.exit(1)
print("all checks passed")
