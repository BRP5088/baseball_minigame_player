"""I-33: a press off a BLIND-CONFIRMED slot must be retried once, not refused outright.

Live 2026-09-21 (`overnight/run_live_20260921f.log`): `_verified_select_and_play_inner`
walks to card_index=4, `_select_verified(4, ...)` selects it (leaving it lifted), then
walks a FRESH `_walk_cursor_to(0, ...)` toward tactics_index=0. That second call's own
TOP-OF-FUNCTION read sees glow=[0.0, 0.4, 0.0, 0.0, 0.4] -- slot 4 still at its
structural ceiling (CLAUDE.md 10.35: "slot 4 never exceeds 11.0 at ANY offset, while
slots 0-3 read 26-28"), no occlusion, every slot's y readable -- presses once toward 0,
and "lost the cursor after 1 press(es)" refuses. The play was refused, unwound, and
retried a full cycle later -- 15-20s on a paid match for a press section 5 already
measures the console dropping 15.20% of the time, clustered.

V1 OF THIS FIX WAS REFUTED (agent_progress/issues/I-33-skeptic/progress.md,
repro_cross_call.py). It scoped `cur_confirmed_blind` to "set only by the I-02 probe
within THIS call", a local that resets to False at the top of every `_walk_cursor_to`
invocation -- so it could not survive the walk-to-4-call -> select -> walk-to-0-call
sequence the live log actually shows, which is a BRAND NEW call whose own
top-of-function read is what names cur=4, never a probe inside it. Two things
independently name `cur` there without a genuine strong glow read, and V2 covers both:

  (a) A MARGINAL glow crossing. Section 3.35's own numbers give slot 4 a ceiling of
      11.0 -- ABOVE CURSOR_GLOW_MIN (10.0) -- so cursor_slot() can occasionally name it
      directly, just unreliably. `CUR_TRUSTED_GLOW_MIN` (20.7, local_hand.cursor_slot's
      OWN measured floor for a genuine cursor) is the line: below it, a cleared gate is
      not yet trusted.
  (b) A card already SELECTED when the fan's own glow cannot name ANY cursor. Selection
      only happens under the cursor, and nothing else can move it without a press this
      call has not sent -- so if exactly one slot is lifted, it names the cursor even
      through a gate the glow itself never clears (`0.4 < CURSOR_GLOW_MIN`). This is the
      literal live-log mechanism: card 4 was already selected by the FIRST call's
      `_select_verified`, so the second call's own top-of-function read finds `sel = [4]`
      with nothing lit.

THE MECHANISM, UNCHANGED FROM V1: a slot whose presence was proven only by an
UNRELIABLE confirmation -- (a) or (b) above, or the I-02 probe's selection lift landing
on a slot other than the call's target -- reads EXACTLY like a dropped press when the
walk steps off it and nothing lights up. `_walk_cursor_to` tracks this per-`cur`
(`cur_confirmed_blind`), RE-EVALUATED on every genuine read so an earlier blind flag
cannot leak into a later, unrelated lost cursor (the mutant-B hole below), and when a
press off a blind `prev` reads nothing, it presses the SAME direction once more before
refusing -- bounded to one extra press per lost-cursor event, counted toward
`steps`/CURSOR_MAX_STEPS like any other press.

WHY abs(prev - target) == 1 IS EXCLUDED. That is precisely the case the EXISTING I-02
probe branch already claims (checked just above this fix in the code, and it always
returns or continues before reaching the new retry) -- a second blind press there could
run PAST `target` before the probe ever got a chance to look with a lift instead of a
glow. So the two mechanisms are disjoint by construction: I-02 handles "one step from
target", I-33 handles everything short of a "refuse" that I-02 does not claim first.

WHAT THIS FILE PINS:
  (1) prev confirmed via the I-02 probe (landing on a DIFFERENT slot, 4, than the
      call's own target), one press toward the real target reads NOTHING (dropped),
      one retry in the same direction reads slot 3 -- the walk continues and arrives,
      exactly one extra press was taken, and the log names the blind slot (4);
  (2) the SAME setup but the retry ALSO reads nothing (two drops, or a truly dead
      slot) -- refuses exactly as before, total presses for that event = 2, and
      NOTHING further is sent;
  (3) prev confirmed via the I-02 probe with the call's target only ONE STEP away --
      no extra press is taken; the (existing, unmodified) I-02 probe branch is what
      runs a second time, not the new retry;
  CONTROL (4): prev confirmed by a READABLE glow (not inference) -- a press that
      reads nothing still hits the OLD, unmodified refusal, with NO extra press;
  (5) THE REFUTED CROSS-CALL SHAPE, mechanism (a): a FRESH call's own TOP-OF-FUNCTION
      read names cur=4 from a marginal glow crossing (10.5), no I-02 probe involved
      anywhere in this call -- the retry still fires and the walk arrives;
  (6) THE REFUTED CROSS-CALL SHAPE, mechanism (b), and the literal live-log frame:
      slot 4 already SELECTED (`sel == [4]`) with glow=[0.0, 0.0, 0.0, 0.0, 0.4] at the
      top of a fresh call -- named from the lift, no probe, no nudge -- and the retry
      still fires and the walk arrives;
  (7) MUTANT-B GUARD: the probe confirms slot 4 (blind), then TWO genuine strong reads
      (slots 3, 2) intervene, then a LATER unrelated drop -- must refuse immediately,
      proving the blind flag was actually CLEARED by the intervening reads and not
      just left set from four steps back.

Uses a ScriptedLook stub rather than the position-tracking fakes in the sibling I-02/
I-32 files, because this fix keys on WHICH look() answers "nothing reads" and which
answers "here it is", at a fixed slot (4) that must never itself glow-confirm --
arithmetic cursor tracking would blur exactly the distinction under test. `_deselect_
verified` is mocked exactly as `tests/rig/test_blind_slot_probe_select.py` does, so
this file does not also have to model its own press/look sequence.
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

import io as _io                                                     # noqa: E402
import contextlib as _contextlib                                     # noqa: E402
import input_controller as ic                                        # noqa: E402

fails = []


def check(name, cond):
    if not cond:
        fails.append(name)


N = ic.MAX_HAND_SIZE
LOW = [0.2] * N          # nothing clears CURSOR_GLOW_MIN -- cursor_slot() reads None
YS_READABLE = [100] * N  # no occlusion anywhere in this bug's own hand


def lit(i, val=27.0):
    g = list(LOW)
    g[i] = val
    return g


class ScriptedLook:
    """Serves pre-scripted (glow, sel) frames from a queue, one per look() call --
    exact call-order control, rather than deriving glow from a tracked cursor
    position the way the sibling I-02/I-32 fakes do. `ys` is always fully readable.
    """

    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []

    def look(self):
        glow, sel = self.frames.pop(0)
        return list(glow), list(YS_READABLE), N, list(sel)

    def press(self, key):
        self.sent.append(key)


_real_press = ic.press
_real_deselect = ic._deselect_verified
try:
    # --- (1) prev inferred (probe landed on 4), one dropped press, one retry lands,
    #         the walk continues and arrives ------------------------------------
    deselect_calls = []

    def fake_deselect_ok(slot, look):
        deselect_calls.append(slot)
        return True, []

    frames = [
        (lit(1), []),        # initial look: cur=1, direct glow read
        (LOW, []),            # press toward 0: nothing reads (prev=1, one step
                               # from target 0 -- triggers the EXISTING I-02 probe)
        ([0.2] * N, [4]),      # probe's look: slot 4 lifted (a DIFFERENT slot than
                               # the target) -- "other"=4, cur becomes 4 by INFERENCE
        (LOW, []),             # press toward 0 from cur=4: DROPPED, nothing reads
        (lit(3), []),          # THE RETRY: same direction again, slot 3 reads
        (lit(2), []),          # ordinary walk continues: 3 -> 2
        (lit(1), []),          # 2 -> 1
        (lit(0), []),          # 1 -> 0 == target, walk arrives
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    ic._deselect_verified = fake_deselect_ok
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        try:
            ok, sel = ic._walk_cursor_to(0, s.look)
        finally:
            ic._deselect_verified = _real_deselect
    out = buf.getvalue()
    check("(1) the walk arrives", ok is True)
    check("(1) the probe fired exactly once (landed on the wrong slot)",
          s.sent.count("select_card") == 1)
    check("(1) deselect was called on the wrong slot (4)", deselect_calls == [4])
    check("(1) the retry fired exactly once",
          out.count("pressing once more before refusing") == 1)
    check("(1) the log names the blind slot (4)",
          "the press left blind slot 4" in out)
    check("(1) exactly one extra move_left beyond what a clean walk would send "
          "(6 total: 1 before the probe, 2 around the dropped press, 3 after)",
          s.sent.count("move_left") == 6)
    check("(1) no frames left unconsumed (every scripted look was actually read)",
          s.frames == [])

    # --- (2) same setup, but the retry ALSO reads nothing -- refuses, total
    #         presses for the event = 2, nothing further is sent ----------------
    deselect_calls = []
    frames = [
        (lit(1), []),
        (LOW, []),
        ([0.2] * N, [4]),
        (LOW, []),             # first press toward 0 from cur=4: dropped
        (LOW, []),             # the retry: ALSO nothing reads
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    ic._deselect_verified = fake_deselect_ok
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        try:
            ok, sel = ic._walk_cursor_to(0, s.look)
        finally:
            ic._deselect_verified = _real_deselect
    out = buf.getvalue()
    check("(2) refuses when the retry also reads nothing", ok is False)
    check("(2) the retry fired exactly once (not looped)",
          out.count("pressing once more before refusing") == 1)
    check("(2) 'lost the cursor after 2 press(es)' is the terminal line",
          "lost the cursor after 2 press(es)" in out)
    check("(2) exactly move_left x2 sent for THIS event, nothing further after it "
          "(plus the 1 move_left before the probe that established cur=4)",
          s.sent[-2:] == ["move_left", "move_left"]
          and s.sent.count("move_left") == 3)
    check("(2) no frames left unconsumed", s.frames == [])

    # --- (3) target is ONE STEP from the inferred slot -- the retry must NOT fire;
    #         the (unmodified) I-02 probe branch runs a second time instead --------
    frames = [
        (lit(2), []),          # initial: cur=2, direct read (target=3, one step away)
        (LOW, []),              # press toward 3: nothing reads -- I-02 fires (1st)
        ([0.2] * N, [4]),        # probe lands on 4 (the wrong slot, one step further)
        (LOW, []),               # press toward 3 from cur=4 (also one step away):
                                 # nothing reads -- I-02 must fire AGAIN, not the retry
        ([0.2] * N, [3]),         # probe's second look: slot 3 (the target) lifted
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    ic._deselect_verified = fake_deselect_ok
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        try:
            ok, sel = ic._walk_cursor_to(3, s.look)
        finally:
            ic._deselect_verified = _real_deselect
    out = buf.getvalue()
    check("(3) the walk arrives via the probe both times", ok is True)
    check("(3) the probe fired twice (once from 2, once from the inferred 4)",
          s.sent.count("select_card") == 2)
    check("(3) the I-33 retry never fired",
          "pressing once more before refusing" not in out)
    check("(3) presses sent are exactly the two moves and two probes an ordinary "
          "I-02 walk needs -- no I-33 retry press added on top",
          s.sent == ["move_right", "select_card", "move_left", "select_card"])
    check("(3) no frames left unconsumed", s.frames == [])

    # --- CONTROL (4): prev confirmed by a READABLE glow, not inference -- a lost
    #                  cursor still hits the OLD refusal, with NO extra press -----
    frames = [
        (lit(2), []),           # initial: cur=2, direct glow read (26-equivalent)
        (LOW, []),               # press toward 0: nothing reads, two steps from
                                 # target -- neither dead-reckon nor I-02 applies
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(0, s.look)
    out = buf.getvalue()
    check("CONTROL: refuses with no extra press", ok is False)
    check("CONTROL: the I-33 retry never fired", "pressing once more" not in out)
    check("CONTROL: the OLD unmodified refusal line fires",
          "lost the cursor after 1 press(es)" in out)
    check("CONTROL: exactly one press sent, nothing more",
          s.sent == ["move_left"])
    check("CONTROL: no frames left unconsumed", s.frames == [])

    # --- (5) THE CROSS-CALL HOLE A SKEPTIC FOUND (agent_progress/issues/
    #         I-33-skeptic/progress.md, repro_cross_call.py): a FRESH call's own
    #         TOP-OF-FUNCTION read names `cur` from a MARGINAL glow crossing --
    #         above CURSOR_GLOW_MIN (10.0) but below CUR_TRUSTED_GLOW_MIN (20.7),
    #         exactly the live log's own shape (glow 10.5 at slot 4, no I-02 probe
    #         involved in THIS call at all) -- and the shipped v1 fix, scoped to
    #         "confirmed via the I-02 probe", could not see it. No `sel` entry
    #         here on purpose, to isolate this from case (6)'s lift path. -------
    frames = [
        (lit(4, 10.5), []),   # top-of-function: a marginal glow crossing names 4
        (LOW, []),             # press toward 0 from cur=4: dropped, nothing reads
        (lit(3), []),          # THE RETRY: slot 3 reads
        (lit(2), []),
        (lit(1), []),
        (lit(0), []),
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(0, s.look)
    out = buf.getvalue()
    check("(5) the walk arrives", ok is True)
    check("(5) no I-02 probe was needed -- this is a top-of-function glow read, "
          "never select_card", "select_card" not in s.sent)
    check("(5) the retry fired exactly once", out.count("pressing once more") == 1)
    check("(5) the log names the blind slot (4)",
          "the press left blind slot 4" in out)
    check("(5) exactly 5 move_left presses (4 to cross the fan + 1 retry)",
          s.sent == ["move_left"] * 5)
    check("(5) no frames left unconsumed", s.frames == [])

    # --- (6) THE EXACT SHAPE THE COORDINATOR ASKED FOR: slot 4 already SELECTED
    #         (`sel == [4]`) at the top of a fresh call, glow[4] == 0.4 -- byte
    #         for byte the live log's own failing frame, glow=[0.0, 0.4, 0.0, 0.0,
    #         0.4] -- reached by NO glow crossing at all (0.4 never clears
    #         CURSOR_GLOW_MIN). `_verified_select_and_play_inner` leaves card 4
    #         selected via `_select_verified(4, ...)` before ever calling
    #         `_walk_cursor_to(0, ...)`, so this is the literal cross-call state,
    #         not a stand-in for it. -----------------------------------------
    frames = [
        ([0.0, 0.0, 0.0, 0.0, 0.4], [4]),  # top-of-function: cursor_slot() reads
                                           # None (0.4 < CURSOR_GLOW_MIN); the
                                           # lift fallback names cur=4 from `sel`
        (LOW, [4]),                        # first press toward 0: dropped
        (lit(3, val=27.0), [4]),           # THE RETRY: slot 3 reads
        (lit(2), [4]),
        (lit(1), [4]),
        (lit(0), [4]),
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(0, s.look)
    out = buf.getvalue()
    check("(6) the walk arrives", ok is True)
    check("(6) no I-02 probe or nudge was needed -- named from the lift alone",
          "select_card" not in s.sent and "nudging" not in out)
    check("(6) the lift-naming line fires, naming slot 4",
          "the fan is blind but slot 4 is already selected" in out)
    check("(6) the retry fired exactly once", out.count("pressing once more") == 1)
    check("(6) the log names the blind slot (4) in the retry line too",
          "the press left blind slot 4" in out)
    check("(6) exactly 5 move_left presses (4 to cross the fan + 1 retry)",
          s.sent == ["move_left"] * 5)
    check("(6) no frames left unconsumed", s.frames == [])

    # --- (7) MUTANT-B GUARD: the probe confirms slot 4 (blind), the walk then
    #         makes TWO genuine, strongly-confirmed reads (slots 3 and 2), and
    #         ONLY THEN does a press read nothing. That later loss must NOT get
    #         the retry -- the blind flag from the probe, four steps back, must
    #         have been CLEARED by the intervening genuine reads. A flag that
    #         only ever gets set and never re-evaluated would wrongly retry
    #         here, exactly the hole a skeptic found unguarded in the first
    #         version of this fix. --------------------------------------------
    frames = [
        ([0.0, 0.0, 0.0, 0.0, 0.4], [4]),  # top-of-function: lift-named, blind=True
        (lit(3), []),                       # genuine strong read -- clears blind
        (lit(2), []),                       # another genuine strong read
        (LOW, []),                          # a LATER, unrelated drop -- must
                                             # refuse immediately, no retry
    ]
    s = ScriptedLook(frames)
    ic.press = s.press
    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        ok, sel = ic._walk_cursor_to(0, s.look)
    out = buf.getvalue()
    check("(7) refuses -- the later drop is NOT covered by the stale blind flag",
          ok is False)
    check("(7) the I-33 retry never fired for this later drop",
          "pressing once more" not in out)
    check("(7) the OLD unmodified refusal line fires, after 3 presses",
          "lost the cursor after 3 press(es)" in out)
    check("(7) exactly 3 presses sent, nothing more",
          s.sent == ["move_left"] * 3)
    check("(7) no frames left unconsumed", s.frames == [])

    # --- no bare-bool checks slipped in (CLAUDE.md 5's nine check() signatures) --
    check("CURSOR_MAX_STEPS untouched by this file's fix", ic.CURSOR_MAX_STEPS == 8)
    check("CUR_TRUSTED_GLOW_MIN sits between the measured populations "
          "(11.0 slot-4 ceiling, 20.7 cursor_slot's own genuine floor)",
          ic.CUR_TRUSTED_GLOW_MIN == 20.7)
finally:
    ic.press = _real_press
    ic._deselect_verified = _real_deselect

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a press off a blind-confirmed slot is retried once before refusing, a "
      "second drop still refuses cleanly, a target one step away is left to the "
      "I-02 probe untouched, a press off a glow-confirmed slot still hits the old "
      "refusal with no extra press, both cross-call mechanisms (a marginal top-of-"
      "call glow crossing and a card already selected) retry and arrive, and an "
      "intervening genuine read clears a stale blind flag before a later drop")
