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
import local_hand as _local_hand                                     # noqa: E402

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


class ScriptedScreen:
    """Cursor reads driven by an explicit SCRIPT of `local_hand.cursor_slot`
    return values, one entry consumed per press -- for I-57 skeptic cases
    `Screen`'s press-tracked movement model cannot represent: a read that goes
    BLIND for a reason other than the target's own occlusion (a routine
    dropped/garbled press, same shape as `miss_after_press` elsewhere in this
    file, but at an arbitrary point inside the top-up rather than tied to a
    press call number), or a cursor whose READ appears to move backward
    without any `move_left` ever being sent (a transient misread, not a real
    move -- CLAUDE.md 10.35's "any box placed ON a card reads bright whether
    or not the cursor is there" is exactly this shape one level up).

    `ys` is always fully readable and `look()` always returns a valid
    MAX_HAND_SIZE-row frame; only what `cursor_slot` reports on top of that
    frame is scripted. Used with `local_hand.cursor_slot` monkeypatched (see
    the callers below), never against the real reader.
    """

    def __init__(self, script):
        self._it = iter(script)
        self.sent = []

    def look(self):
        return [5.0] * N, [100] * N, N, []

    def press(self, key):
        self.sent.append(key)

    def next_cur(self, glow, sel, exclude=None):
        return next(self._it)


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

    # ---------------------------------------------------------------- I-57 --
    # agent_progress/census/stuck_after_half/progress.md:
    # overnight/run_live_20260921x.log:465 -- "still at 3 after 8 presses --
    # refusing", target 4, the kept frame reading CLEANLY (fan fully dealt, glow
    # 21.2 on slot 3, unambiguous) -- the reads were confident and the presses
    # were dropped in a cluster, not lost. The next poll reached 4 in ONE press.
    # `CURSOR_MAX_STEPS` counts presses SENT, not moves REFLECTED, so a walk that
    # is confirmed moving (or already one hop from target) gets up to
    # PRESS_VERIFY_TRIES more look-gated presses before refusing -- a walk that
    # never moved at all (the OTHER 11 archived "still at N after 8" lines, a
    # chronic-occlusion shape) must still refuse exactly as before, with zero
    # top-up.

    # --- (W) 8 presses, 6 dropped in a cluster at the end -- the cursor is
    #         CONFIRMED moving (1 -> 3, first_cur=1) when the cap is hit, so the
    #         walk gets a real look-gated press toward the target rather than
    #         refusing one hop short; total presses <= CURSOR_MAX_STEPS +
    #         PRESS_VERIFY_TRIES --------------------------------------------
    s = Screen(cur=1, drop_press={3, 4, 5, 6, 7, 8})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(W) arrives after the top-up reaches the target", ok is True)
    check("(W) the top-up is logged, naming the move since the walk began",
          "moved since the walk began (1 -> 3)" in out)
    check("(W) no more than CURSOR_MAX_STEPS + PRESS_VERIFY_TRIES presses sent",
          len(s.sent) <= ic.CURSOR_MAX_STEPS + ic.PRESS_VERIFY_TRIES)
    check("(W) every press sent was toward the target",
          all(k == "move_right" for k in s.sent))

    # --- (X) CONTROL -- the cursor never moved in 8 presses (every one dropped
    #         from the first): the chronic-occlusion shape must still refuse
    #         with ZERO top-up, exactly as it did before this fix. The
    #         false-cursor-exclude branch above ALSO fires on `cur == first_cur`
    #         and takes priority, so it would mask this file's own guard on the
    #         very first round -- FALSE_CURSOR_EXCLUDE_MAX is dropped to 0 here
    #         (same monkeypatch shape as test_false_cursor_on_occluded_slot.py's
    #         part (d)) so the cap-hit falls straight through to THIS branch
    #         with `cur == first_cur` still true, which is the only way to
    #         exercise the guard this test exists to pin -----------------------
    _real_exclude_max = ic.FALSE_CURSOR_EXCLUDE_MAX
    try:
        ic.FALSE_CURSOR_EXCLUDE_MAX = 0
        s = Screen(cur=0, drop_press={1, 2, 3, 4, 5, 6, 7, 8})
        ic.press = s.press
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf):
            ok, sel = ic._walk_cursor_to(4, s.look)
        out = buf.getvalue()
        check("(X) a cursor that never moved at all is refused", ok is False)
        check("(X) the top-up never fires when the cursor never moved",
              "allowing up to" not in out)
        check("(X) no presses beyond the original budget were sent",
              len(s.sent) == ic.CURSOR_MAX_STEPS)
    finally:
        ic.FALSE_CURSOR_EXCLUDE_MAX = _real_exclude_max

    # --- (Y) the cursor moves during the first 8 (1 -> 3, granting the top-up),
    #         but every one of the top-up's own presses is ALSO dropped -- it
    #         must still refuse, having spent EXACTLY the extended budget -----
    s = Screen(cur=1, drop_press={3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13})
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(Y) refuses once the top-up budget is also spent", ok is False)
    check("(Y) exactly CURSOR_MAX_STEPS + PRESS_VERIFY_TRIES presses sent",
          len(s.sent) == ic.CURSOR_MAX_STEPS + ic.PRESS_VERIFY_TRIES)
    check("(Y) the top-up was granted exactly once",
          out.count("allowing up to") == 1)

    # --- (Z) CONTROL -- a normal walk with no drops and no occlusion never
    #         reaches the cap at all, so the top-up never fires and the press
    #         count is exactly what it always was ---------------------------
    s = Screen(cur=0)
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(4, s.look)
    out = buf.getvalue()
    check("(Z) CONTROL: a normal walk still arrives", ok is True)
    check("(Z) CONTROL: exactly 4 presses, no top-up logic touched",
          s.sent == ["move_right"] * 4)
    check("(Z) CONTROL: the top-up never fires on an unremarkable walk",
          "allowing up to" not in out)

    # ---------------------------------------------------------- I-57 skeptic --
    # agent_progress/issues/I-57/skeptic.md, REFUTED fda9436: finding 1
    # (fatal, a None read during the top-up crashed with TypeError), finding 2
    # (the true worst-case bound was 18 presses, not the claimed 13, because
    # I-53's own retry spends its budget BEFORE the top-up is even granted),
    # note 3 (an oscillating cursor that lands back on first_cur at cap time
    # got no top-up even though it clearly did move). These three cases pin
    # the redo. `local_hand.cursor_slot` is monkeypatched to a SCRIPT via
    # ScriptedScreen -- the only way to put a blind read or an apparent
    # backward move at an exact point in the top-up without also faking a
    # real movement model for it.
    _real_cursor_slot = _local_hand.cursor_slot

    # --- (V) finding 1: a None read on top-up press 2 must not crash. Base
    #         walk climbs 0 -> 3 over 8 presses (steps: 1,2,3,3,3,3,3,3), then
    #         the top-up's own first extra press ALSO goes blind (this is the
    #         exact point the unfixed code crashed at, one iteration earlier
    #         than the skeptic's own repro even needed), and the THIRD press
    #         (the recovery) reaches the target -- no exception, bounded,
    #         arrives ------------------------------------------------------
    try:
        _script = iter([0,                          # first_cur
                         1, 2, 3, 3, 3, 3, 3, 3,     # 8 base presses
                         None, None,                 # 2 blind top-up reads
                         4])                         # 3rd top-up press: target
        _local_hand.cursor_slot = lambda glow, sel, exclude=None: next(_script)
        s = ScriptedScreen([])
        ic.press = s.press
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf):
            ok, sel = ic._walk_cursor_to(4, s.look)
        out = buf.getvalue()
        check("(V) no exception, and the walk ARRIVES once the blind reads clear",
              ok is True)
        check("(V) exactly 11 presses (8 base + 3 top-up)", len(s.sent) == 11)
        check("(V) no more than CURSOR_MAX_STEPS + PRESS_VERIFY_TRIES presses",
              len(s.sent) <= ic.CURSOR_MAX_STEPS + ic.PRESS_VERIFY_TRIES)
        check("(V) still logs the top-up grant", "allowing up to" in out)
    finally:
        _local_hand.cursor_slot = _real_cursor_slot

    # --- (U) finding 2: I-53's own retry spends its budget BEFORE the top-up
    #         is granted -- 6 ordinary presses, then an occluded-slot dead-
    #         reckon, then I-53's retry running its full 5 tries (steps hits
    #         13 there, before the top-up branch is ever reached). The ENFORCED
    #         bound must be 13, not 18: the top-up's own budget check (BEFORE
    #         every top-up press) must see the budget already spent and send
    #         ZERO top-up presses, refusing at exactly 13 -------------------
    try:
        _script = iter([0,                               # first_cur
                         0, 0, 0, 0, 0, 0,                # 6 ordinary presses
                         None,                             # press 7: occluded
                                                            # slot 1 -> dead-
                                                            # reckon (cur is SET
                                                            # by the branch
                                                            # itself, not read)
                         None,                             # press 8: the very
                                                            # next read, also
                                                            # blind -- this is
                                                            # what triggers
                                                            # was_dead_reckoned's
                                                            # OWN retry loop
                         None, None, None, None,           # I-53 retry 1-4: miss
                         2,                                 # I-53 retry 5: off-
                                                            # target, resolves --
                                                            # steps=13 here
                         ])                                 # top-up: 0 presses
        _local_hand.cursor_slot = lambda glow, sel, exclude=None: next(_script)

        def _u_look():
            ys = [100] * N
            ys[1] = None  # slot 1 permanently occluded -- dead-reckon eligible
            return [5.0] * N, ys, N, []

        s = ScriptedScreen([])
        ic.press = s.press
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf):
            ok, sel = ic._walk_cursor_to(4, _u_look)
        out = buf.getvalue()
        check("(U) refuses once the STACKED budget (I-53 + top-up) is spent",
              ok is False)
        check("(U) exactly CURSOR_MAX_STEPS + PRESS_VERIFY_TRIES presses -- "
              "18 (the skeptic's unfixed number) must NOT appear",
              len(s.sent) == ic.CURSOR_MAX_STEPS + ic.PRESS_VERIFY_TRIES == 13)
        check("(U) the top-up was granted but sent zero presses of its own",
              "allowing up to" in out and "already spent by earlier retries" in out)
    finally:
        _local_hand.cursor_slot = _real_cursor_slot

    # --- (M) note 3: the cursor moves away on press 1, then OSCILLATES back
    #         to first_cur and stays there for the rest of the base walk. At
    #         cap time cur == first_cur, but it clearly DID move -- the
    #         false-cursor-exclude branch must NOT treat this as a chronic
    #         false reading, and the top-up must fire instead -------------
    try:
        _script = iter([0,                          # first_cur
                         1, 0, 0, 0, 0, 0, 0, 0,     # 8 base presses: away then
                                                      # back, stays at first_cur
                         1, 2, 3, 4])                # top-up reaches the target
        _local_hand.cursor_slot = lambda glow, sel, exclude=None: next(_script)
        s = ScriptedScreen([])
        ic.press = s.press
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf):
            ok, sel = ic._walk_cursor_to(4, s.look)
        out = buf.getvalue()
        check("(M) moved-and-back is treated as MOVED -- arrives via top-up",
              ok is True)
        check("(M) the top-up fired rather than the false-cursor exclusion",
              "allowing up to" in out and "false cursor" not in out)
        check("(M) names the oscillation explicitly",
              "moved since the walk began and returned to its start" in out)
        check("(M) exactly 12 presses (8 base + 4 top-up)", len(s.sent) == 12)
    finally:
        _local_hand.cursor_slot = _real_cursor_slot

    # --- (G) I-57 skeptic ROUND 2: `_ever_moved` must NOT latch on a dead-
    #         reckon's own GUESS. Occluded slot 1 triggers exactly one guess
    #         (cur := 1, no read behind it at all); the very next REAL read
    #         confirms the cursor is still on first_cur, and every remaining
    #         real read for the rest of the base budget agrees -- the walk
    #         never actually moved. At cap time `_ever_moved` must be False,
    #         so the I-25 false-cursor-exclude branch fires (not the I-57
    #         top-up), and once that exclusion also finds nothing lit, the
    #         walk refuses -- agent_progress/issues/I-57/
    #         repro_ever_moved_from_guess.py -----------------------------
    try:
        _script = iter([0,                    # first_cur (call 0)
                         None,                 # call 1: occluded slot 1 ->
                                                # dead-reckon guesses cur=1,
                                                # ZERO reads confirm it
                         0, 0, 0, 0, 0, 0, 0,  # calls 2-8: seven REAL reads,
                                                # every one names first_cur --
                                                # the guess was never right
                         None])                # call 9: I-25's own exclusion
                                                # confirmation -- nothing else
                                                # lit either
        _local_hand.cursor_slot = lambda glow, sel, exclude=None: next(_script)

        def _g_look():
            ys = [100] * N
            ys[1] = None  # slot 1 permanently occluded -- the ONE guess
            return [5.0] * N, ys, N, []

        s = ScriptedScreen([])
        ic.press = s.press
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf):
            ok, sel = ic._walk_cursor_to(4, _g_look)
        out = buf.getvalue()
        check("(G) a guess-only walk that never actually moved refuses",
              ok is False)
        check("(G) the I-25 false-cursor-exclude branch fired, naming slot 0",
              "treating slot 0 as a false cursor" in out)
        check("(G) the I-57 top-up never fired -- the guess did not latch "
              "_ever_moved",
              "allowing up to" not in out)
        check("(G) exactly 8 presses -- no top-up extension", len(s.sent) == 8)
    finally:
        _local_hand.cursor_slot = _real_cursor_slot

    # --- (H) CONTROL for (G) -- the identical away-then-back shape, but the
    #         move is a CONFIRMED read (no occlusion anywhere), never a
    #         guess. This time `_ever_moved` MUST latch, so the I-57 top-up
    #         fires instead of the I-25 exclusion -- proving (G)'s refusal
    #         comes from the guess never counting toward a move, not from
    #         the false-cursor-exclude branch being unreachable for some
    #         unrelated reason ------------------------------------------
    try:
        _script = iter([0,                    # first_cur (call 0)
                         1,                    # call 1: a REAL read -- the
                                                # cursor genuinely moved to 1
                         0, 0, 0, 0, 0, 0, 0,  # calls 2-8: seven real reads,
                                                # back at first_cur
                         1, 2, 3, 4])          # top-up reaches the target
        _local_hand.cursor_slot = lambda glow, sel, exclude=None: next(_script)
        s = ScriptedScreen([])
        ic.press = s.press
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf):
            ok, sel = ic._walk_cursor_to(4, s.look)
        out = buf.getvalue()
        check("(H) CONTROL: a confirmed away-then-back move arrives via the "
              "top-up", ok is True)
        check("(H) CONTROL: _ever_moved latched -- the top-up fired, not "
              "the I-25 exclusion",
              "allowing up to" in out and "false cursor" not in out)
        check("(H) CONTROL: exactly 12 presses (8 base + 4 top-up)",
              len(s.sent) == 12)
    finally:
        _local_hand.cursor_slot = _real_cursor_slot
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
