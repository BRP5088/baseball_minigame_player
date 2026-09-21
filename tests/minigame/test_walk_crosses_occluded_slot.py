"""I-32: a walk that CROSSES an occluded slot must not refuse on the first press.

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

WHAT THIS FILE PINS:
  (1) the walk crosses a single occluded slot and arrives, in exactly the
      number of presses a normal walk would take -- the occluded slot costs
      nothing extra, and the log names it;
  (2) a SECOND slot going unreadable right after the dead-reckoned step (even
      though ITS row is perfectly readable -- a genuine drop, not occlusion)
      still refuses, and sends no further presses: dead-reckoning covers one
      step, not a chain;
  (2b) THE MIRROR CASE, stated in the task and worth pinning directly: two
      OCCLUDED slots in a row still refuse rather than chain a second guess --
      (2) alone cannot tell "the bound fired" from "the ys check alone would
      have refused anyway", because its second slot is not occluded;
  (3) never dead-reckon ONTO the target itself -- an occluded target must go
      through I-02's probe-select path (or its own refusal when the probe
      cannot see it either), never be guessed at;
  CONTROL: (4) with every row's y readable, a press that reads no cursor mid-walk
      still hits the old, unmodified refusal -- proving this fix is scoped to
      occluded rows and not "forgive any lost cursor once".
  (5) a LEFTWARD walk (every case above is rightward) exercises the `prev - 1`
      branch of `expected`'s ternary directly -- a mutant hardcoding
      `expected = prev + 1` is invisible to (1)-(4);
  (6) two occlusions separated by a genuinely readable slot prove
      `dead_reckoned_last` actually RESETS on a clean read, not just that it
      caps one consecutive dead-reckon -- both found by an independent skeptic
      review and folded in here rather than left as scratch scripts.
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
REST = [200, 160, 150, 165, 220]


class OccludedScreen:
    """A 5-slot fan where `occluded` slots are unreadable to BOTH readers at once --
    exactly how a fan occlusion (CLAUDE.md 10.28) reads in production: the disc is
    hidden, so `ys[i]` is a fallback (None) AND `cursor_glow` returns 0.0 for that
    row regardless of whether the cursor is actually sitting there. That is the
    one thing this screen must get right that `tests/rig/test_blind_slot_probe_
    select.py`'s `ProbeScreen` deliberately does NOT model: there, `blind` (glow)
    and `unreadable` (position) are independent, because slot 4's glow blindness
    has nothing to do with its position being readable. Here they are the SAME
    set, because occlusion blinds both at once -- and that is exactly the signal
    `ys[expected] is None` keys on.

    `also_blind` marks slots that are glow-blind WITHOUT being position-unreadable
    (a genuine dropped press, not occlusion) -- used to build the "a second slot
    goes dark for an unrelated reason" case without touching `ys`.
    """

    def __init__(self, cur_glow_slot, occluded=frozenset(), also_blind=frozenset()):
        self.cur_glow_slot = cur_glow_slot
        self.occluded = set(occluded)
        self.also_blind = set(also_blind)
        self.sent = []

    def _ys(self):
        return [None if i in self.occluded else 100 for i in range(N)]

    def look(self):
        glow = [0.2] * N
        c = self.cur_glow_slot
        if c is not None and c not in self.occluded and c not in self.also_blind:
            glow[c] = 27.0
        return glow, self._ys(), N, []

    def press(self, key):
        self.sent.append(key)
        if key == "move_left":
            self.cur_glow_slot = max(0, (self.cur_glow_slot or 0) - 1)
        elif key == "move_right":
            self.cur_glow_slot = min(N - 1, (self.cur_glow_slot or 0) + 1)


_real_press = ic.press
try:
    # --- (1) a single occluded slot mid-walk costs nothing: arrives, exactly
    #         4 presses (0->1->2->3->4), log names the occluded slot ----------
    s = OccludedScreen(cur_glow_slot=0, occluded={1})
    ic.press = s.press
    import io as _io
    import contextlib as _contextlib
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

    # --- (2) a SECOND slot unreadable right after the dead-reckoned step (its
    #         OWN row is readable -- a genuine drop, not occlusion) refuses,
    #         and sends no further presses ------------------------------------
    s = OccludedScreen(cur_glow_slot=0, occluded={1}, also_blind={2})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(2) refuses -- dead-reckoning does not chain across two dark slots",
          ok is False)
    check("(2) exactly 2 presses sent, none further",
          s.sent == ["move_right", "move_right"])
    check("(2) the old 'lost the cursor' line fires, not a second dead-reckon",
          "lost the cursor after 2 press(es)" in out
          and out.count("dead-reckoning") == 1)

    # --- (2b) THE MIRROR CASE: two consecutive OCCLUDED slots still refuse --
    #          exercises the ONE-consecutive-step bound directly (unlike (2),
    #          where the second slot's own ys is readable and would refuse on
    #          that alone) -- this is what actually distinguishes "the bound
    #          exists" from "the bound was silently dropped" -----------------
    s = OccludedScreen(cur_glow_slot=0, occluded={1, 2})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(2b) two occluded slots in a row still refuse -- no chaining",
          ok is False)
    check("(2b) exactly 2 presses, no third press guessing past the pair",
          s.sent == ["move_right", "move_right"])
    check("(2b) only the FIRST occluded slot was dead-reckoned",
          out.count("dead-reckoning") == 1 and "slot 1 is occluded" in out)

    # --- (3) never dead-reckon ONTO the target -- an occluded target refuses
    #         through the existing probe path, never a guess -------------------
    s = OccludedScreen(cur_glow_slot=0, occluded={1})
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(1, s.look)
    check("(3) an occluded TARGET refuses", ok is False)
    check("(3) refused without a select_card guess",
          "select_card" not in s.sent)
    check("(3) exactly one move press, no dead-reckon onto the target",
          s.sent == ["move_right"])

    # --- CONTROL (4): every row's y is readable; a mid-walk dropped press still
    #                  hits the OLD, unmodified refusal ------------------------
    s = OccludedScreen(cur_glow_slot=0, also_blind={2})   # occluded={} -- all ys readable
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
    check("CONTROL: the plain 'lost the cursor' line fires",
          "lost the cursor after 2 press(es)" in out)

    # --- (5) LEFTWARD walk across an occluded slot: every case above walks
    #         RIGHTWARD (0->4 or 0->1), so a mutant that hardcodes
    #         `expected = prev + 1` in place of the ternary
    #         `prev + 1 if prev < target else prev - 1` is invisible to them --
    #         walking cur=4 -> target=0 across occluded slot 3 exercises the
    #         `prev - 1` branch directly (independent skeptic review, I-32) ----
    s = OccludedScreen(cur_glow_slot=4, occluded={3})
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
    s = OccludedScreen(cur_glow_slot=0, occluded={1, 3})
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

    # --- no bare-bool checks slipped in (CLAUDE.md 5's nine check() signatures) --
    check("PROBE_SELECT_MAX untouched by this file's fix",
          ic.PROBE_SELECT_MAX == 2)
finally:
    ic.press = _real_press

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a walk crosses one occluded slot for free, refuses on a second dark "
      "slot right after, never dead-reckons onto the target, and a walk with "
      "no occlusion anywhere still hits the old refusal unmodified")
