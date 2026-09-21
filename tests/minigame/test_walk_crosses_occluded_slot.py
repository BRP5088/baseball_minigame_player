"""I-32: a walk that CROSSES an occluded slot must not refuse on the first press.
I-53: nor may it refuse on the SECOND, when that press is the one right after
a dead-reckoned crossing -- see the bottom of this file for that half.

Live 2026-09-21 (`overnight/run_live_20260921d.log`): a hand read
`0: swing_boost +2, 1: UNKNOWN, 2: swing_boost +1, 3: speed_boost +1, 4: 5/3`.
Slot 1's power disc sat under slot 2's card (CLAUDE.md 10.28's fan occlusion), so
`read_hand` gave that row `y_measured: False` and `local_hand.cursor_glow` returns
0.0 BY CONSTRUCTION for any row whose y was never measured -- the cursor sitting
on slot 1 is invisible to `cursor_slot`, always, for the whole hand. Walking from
slot 0 toward slot 4 crosses slot 1, and `_walk_cursor_to` refused after exactly
ONE press ("lost the cursor after 1 press(es) (glow=[0.0, 0.0, 0.0, 0.0, 0.7])"),
three times running, excluding the play. `overnight/crawl/20260921_005556/
001_before.png` is the frame.

THIS IS NOT I-02's CASE. `tests/rig/test_blind_slot_probe_select.py` fixed the
cursor going blind ONE STEP FROM THE TARGET (slot 4, which is structurally
glow-blind at every position -- CLAUDE.md 10.35) by probing with select_card.
This file is the cursor passing THROUGH an occluded slot on its way to a target
that is itself perfectly readable: probing there would toggle a card that was
never meant to be touched. The fix instead reads the walk's own `ys` column --
which `_walk_cursor_to` already carries from `_look_settled`, the same
fallback-y gate `_probe_select_blind_target` checks at its own top -- and when
the slot the cursor MUST be on (`prev` plus one step toward `target`) is exactly
the one row the lift reader abstains on, "nothing lit" is the EXPECTED reading,
not evidence of a lost cursor. Dead-reckon across it for ONE step and let the
next press prove the walk is still alive.

WHAT THIS FILE PINS (I-32):
  (1) the walk crosses a single occluded slot and arrives, in exactly the
      number of presses a normal walk would take -- the occluded slot costs
      nothing extra, and the log names it;
  (3) never dead-reckon ONTO the target itself -- an occluded target must go
      through I-02's probe-select path (or its own refusal when the probe
      cannot see it either), never be guessed at;
  (5) a LEFTWARD walk (every case above is rightward) exercises the `prev - 1`
      branch of `expected`'s ternary directly -- a mutant hardcoding
      `expected = prev + 1` is invisible to (1) and (3);
  (6) two occlusions separated by a genuinely readable slot prove
      `dead_reckoned_last` actually RESETS on a clean read, not just that it
      caps one consecutive dead-reckon -- found by an independent skeptic
      review and folded in here rather than left as scratch scripts.

WHAT THIS FILE PINS (I-53, the bottom half): a lost read that follows
IMMEDIATELY after a dead-reckoned crossing is not refused on the spot any
more -- `_walk_cursor_to` presses again (a real press, never a second guess)
up to `PRESS_VERIFY_TRIES` times before giving up, because CLAUDE.md section 5
measures the console dropping 15.20% of presses and the position right after a
guess is exactly the one this walk cannot yet confirm either way.
  (A) the press meant to cross the occluded slot was itself dropped, so the
      real cursor is STILL sitting on the occluded slot -- one extra move
      finds a readable slot and the walk arrives, no refusal;
  (B) every extra move is also dropped -- refuses, same as an unrecoverable
      loss always has;
  (C) the extra retries run past a slot that momentarily failed to glow
      (target included) and land beyond the target -- the walk simply turns
      around, using the SAME per-step logic every other leg of the walk
      already uses, and arrives;
  (D) CONTROL -- with no occlusion anywhere, a lost cursor is refused with the
      exact press count it always had. This is what proves the new retry is
      scoped to a loss that follows a dead-reckon, not "forgive any lost
      cursor once".

The two old cases this replaces (a transient miss on the slot right after a
dead-reckoned crossing, and two occluded slots back to back) are now folded
into (A)/(D)'s family below: both RECOVER instead of refusing, because pressing
again and re-reading is not the "second guess" I-32 was written to forbid --
that prohibition is about ASSUMING a position with no read at all, which
dead-reckoning does and this retry never does.
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


def check(name, cond):
    if not cond:
        fails.append(name)


N = ic.MAX_HAND_SIZE


class Screen:
    """A 5-slot fan whose glow reader can fail two DIFFERENT ways, matched to
    the two different real causes CLAUDE.md documents:

      occluded        the slot's POSITION is unreadable (`ys[i] is None`) --
                       CLAUDE.md 10.28's fan occlusion, STABLE for the whole
                       hand, exactly like `ys` in production. `cursor_glow`
                       returns 0.0 for these BY CONSTRUCTION whether or not the
                       cursor is actually there.
      miss_after_press a specific PRESS CALL NUMBER whose immediately-following
                       look() reads no glow anywhere, even though the cursor's
                       real position is perfectly readable (`ys` unaffected).
                       This is section 5's 15.20% ignored-press rate and
                       CLAUDE.md 10.1's "a look that lands mid-animation is not
                       a reading" in one knob -- a ONE-OFF miss, not a
                       structural defect, and it clears itself the moment the
                       cursor is read again (by construction: `n_calls` only
                       ever matches once).
      drop_press       a specific PRESS CALL NUMBER that does not move the
                       cursor at all -- section 5's press ARRIVES-but-ignored
                       finding, modelled at the point where it actually
                       matters: the character's real position.

    Call numbers are 1-indexed in send order, so they can be read straight off
    `s.sent`.
    """

    def __init__(self, cur, occluded=frozenset(), miss_after_press=frozenset(),
                 drop_press=frozenset()):
        self.cur = cur
        self.occluded = set(occluded)
        self.miss_after_press = set(miss_after_press)
        self.drop_press = set(drop_press)
        self.sent = []
        self.n_calls = 0

    def _ys(self):
        return [None if i in self.occluded else 100 for i in range(N)]

    def look(self):
        glow = [0.2] * N
        if self.n_calls not in self.miss_after_press and self.cur not in self.occluded:
            glow[self.cur] = 27.0
        return glow, self._ys(), N, []

    def press(self, key):
        self.n_calls += 1
        self.sent.append(key)
        if self.n_calls in self.drop_press:
            return
        if key == "move_left":
            self.cur = max(0, self.cur - 1)
        elif key == "move_right":
            self.cur = min(N - 1, self.cur + 1)


import io as _io
import contextlib as _contextlib

_real_press = ic.press
try:
    # ---------------------------------------------------------------- I-32 --
    # --- (1) a single occluded slot mid-walk costs nothing: arrives, exactly
    #         4 presses (0->1->2->3->4), log names the occluded slot ----------
    s = Screen(cur=0, occluded={1})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(1) walk arrives crossing one occluded slot", ok is True)
    check("(1) exactly 4 presses (no probe, no retry)", s.sent == ["move_right"] * 4)
    check("(1) verified-on-target line printed",
          "verified on 4 after 4 press(es)" in out)
    check("(1) the occluded slot is named in the log",
          "slot 1 is occluded" in out)

    # --- (3) never dead-reckon ONTO the target -- an occluded target refuses
    #         through the existing probe path, never a guess -------------------
    s = Screen(cur=0, occluded={1})
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(1, s.look)
    check("(3) an occluded TARGET refuses", ok is False)
    check("(3) refused without a select_card guess",
          "select_card" not in s.sent)
    check("(3) exactly one move press, no dead-reckon onto the target",
          s.sent == ["move_right"])

    # --- (5) LEFTWARD walk across an occluded slot: every case above walks
    #         RIGHTWARD (0->4 or 0->1), so a mutant that hardcodes
    #         `expected = prev + 1` in place of the ternary
    #         `prev + 1 if prev < target else prev - 1` is invisible to them --
    #         walking cur=4 -> target=0 across occluded slot 3 exercises the
    #         `prev - 1` branch directly (independent skeptic review, I-32) ----
    s = Screen(cur=4, occluded={3})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(0, s.look)
    out = buf.getvalue()
    check("(5) leftward walk arrives crossing one occluded slot", ok is True)
    check("(5) exactly 4 presses, all move_left",
          s.sent == ["move_left"] * 4)
    check("(5) the occluded slot is named in the log",
          "slot 3 is occluded" in out)

    # --- (6) TWO occlusions separated by a genuinely readable slot: occluded
    #         {1, 3} with slot 2 readable in between, walking 0->4. Checks that
    #         `dead_reckoned_last` actually RESETS on the clean read at slot 2 --
    #         if the reset were dropped, the flag from the FIRST dead-reckon
    #         (slot 1) would still be set when slot 3 goes dark, and the SECOND
    #         dead-reckon would be wrongly blocked by a guess three steps stale
    #         (independent skeptic review, I-32) ------------------------------
    s = Screen(cur=0, occluded={1, 3})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(6) arrives across two occlusions separated by a readable slot",
          ok is True)
    check("(6) exactly 4 presses, all move_right",
          s.sent == ["move_right"] * 4)
    check("(6) BOTH occluded slots are named in the log",
          "slot 1 is occluded" in out and "slot 3 is occluded" in out)
    check("(6) dead-reckoned twice -- the flag reset after the clean read at 2",
          out.count("dead-reckoning") == 2)

    # ---------------------------------------------------------------- I-53 --
    # --- (A) the dead-reckon PRESS itself was dropped, so the real cursor is
    #         STILL on the occluded slot when the next look fails -- one more
    #         real press (not a second guess) finds slot 2 and the walk
    #         arrives ------------------------------------------------------
    s = Screen(cur=0, occluded={1}, drop_press={2})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(A) arrives after the extra retry finds the real cursor", ok is True)
    check("(A) exactly one extra move logged (1/5)",
          "pressing once more toward 4 rather than refusing (1/5)" in out
          and "(2/5)" not in out)
    check("(A) five presses sent total (one of them dropped)",
          s.sent == ["move_right"] * 5)
    check("(A) still names the occluded slot that started it",
          "slot 1 is occluded" in out)
    check("(A) arrives at the target", "verified on 4 after 5 press(es)" in out)

    # --- (B) every extra move is ALSO dropped -- refuses, same outcome as an
    #         unrecoverable loss always has, after PRESS_VERIFY_TRIES tries ---
    s = Screen(cur=0, occluded={1}, drop_press={2, 3, 4, 5, 6, 7})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(B) refuses once the whole retry budget is spent", ok is False)
    check("(B) all five extra tries were logged",
          all(f"({i}/{ic.PRESS_VERIFY_TRIES})" in out for i in range(1, 6)))
    check("(B) the final refusal line fires",
          "lost the cursor after 7 press(es)" in out)
    check("(B) seven presses sent (initial cross + 1 + 5 retries)",
          s.sent == ["move_right"] * 7)

    # --- (C) the retry runs past a target whose OWN read momentarily misses,
    #         lands past it, and the ordinary per-step logic (nothing special
    #         to (C)) walks it back -----------------------------------------
    s = Screen(cur=0, occluded={1}, miss_after_press={2, 3})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(3, s.look)
    out = buf.getvalue()
    check("(C) arrives after overshooting and turning back", ok is True)
    check("(C) five presses: cross, two misses, overshoot, walk back",
          s.sent == ["move_right"] * 4 + ["move_left"])
    check("(C) two extra retries logged before the overshoot resolved",
          "(1/5)" in out and "(2/5)" in out)
    check("(C) verified on the target after walking back",
          "verified on 3 after 5 press(es)" in out)

    # --- (D) CONTROL: no occlusion anywhere, so no dead-reckon ever ran --
    #         a lost cursor is refused with EXACTLY the press count it always
    #         had, proving the new retry never fires without a dead-reckon
    #         behind it -----------------------------------------------------
    s = Screen(cur=0, miss_after_press={2})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("CONTROL: no occlusion anywhere -- old refusal, unmodified", ok is False)
    check("CONTROL: refuses on the FIRST lost press (no dead-reckon fired)",
          s.sent == ["move_right", "move_right"])
    check("CONTROL: no dead-reckon line printed at all",
          "dead-reckoning" not in out)
    check("CONTROL: the I-53 retry never fires without a dead-reckon behind it",
          "pressing once more toward" not in out)
    check("CONTROL: the plain 'lost the cursor' line fires",
          "lost the cursor after 2 press(es)" in out)

    # --- no bare-bool checks slipped in (CLAUDE.md 5's nine check() signatures) --
    # I-51 made PROBE_SELECT_MAX an alias of PRESS_VERIFY_TRIES (was a literal 2);
    # this file's own fix never touches either, so the two must still agree.
    check("PROBE_SELECT_MAX untouched by this file's fix",
          ic.PROBE_SELECT_MAX == ic.PRESS_VERIFY_TRIES)
finally:
    ic.press = _real_press

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a walk crosses one occluded slot for free, never dead-reckons onto the "
      "target, and a read lost right after a dead-reckoned crossing now retries "
      "for real (up to PRESS_VERIFY_TRIES) instead of refusing on the spot -- "
      "while a loss with no dead-reckon behind it still refuses exactly as before")
