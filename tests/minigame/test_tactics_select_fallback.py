"""I-48: a failed TACTICS select must not burn the BATTER through the play-refusal
exclusion.

Live 2026-09-21 (`overnight/run_live_20260921r.log:600-780`): a hand held a POWER
SWING at slot 1 next to an occluded slot 2 (a home-plate runner's card covering its
disc). Turn after turn the batter's own walk+select landed cleanly, the cursor
walked to slot 1 and verified there too, and then `select_card` never landed on
slot 1 after 5 attempts -- so `_verified_select_and_play_inner` refused the WHOLE
play, `orchestrator.exclude_play_slot(player_idx, ...)` excluded the BATTER's
hand_index (the only thing a single bool return lets it see), and the loop burned
batter after batter (hand_index 4, then 3) before one happened to sit at slot 0,
where the walk to slot 1 is a single adjacent step and does not need to cross the
occluded slot. Five minutes and two hands lost for a boost worth ~+0.6 runs/half
(CLAUDE.md §4).

THE FIX, in two parts. (1) `_verified_select_and_play_inner`'s per-target loop
(input_controller.py) now tells the TACTICS target apart from the BATTER target: a
tactics failure unwinds only the tactics attempt and commits the batter alone,
instead of refusing the whole play. A batter failure is untouched -- same refusal,
same unwind, same return False as before. (2) `orchestrator.record_refused_select`
keeps one frame + why.json per refused select_and_play() call
(diagnostics/deal_frames/refused_select_<ns>/), the same never-raises/BASEBALL_TEST_
RUN-gated/REFUSES-past-the-cap shape as record_local_hand and record_money_read_frame,
so a human does not have to re-derive what failed from the log alone next time.

I-48b/I-48c (I-48b added 2026-09-21 `overnight/run_live_20260921s.log` ~369-400,
moved to its shared form the same day on the skeptic's N1): the I-48 fallback above
used to commit to "batter alone" on the STALE belief that card_index was still
lifted, re-checked ONLY inside its own branch. The skeptic's review
(agent_progress/issues/I-48b/skeptic.md) PROVED the mechanism (a later blind press
this operation sends -- most often the I-02 probe crossing an occluded slot, section
5's 15.20% ignore rate -- can toggle an EARLIER, already-verified target back down,
because the probe's own "did anything NEW appear" check cannot see one disappear)
and found a SIBLING instance the branch-local re-check could never reach: the
TACTICS target's own walk and select can both succeed while the BATTER is what gets
silently lost (`run_live_20260921j.log:620-624`, `20260921o.log:1040-1050`), which
never enters the I-48 branch at all. The re-check now lives in ONE shared place,
right before the commit both shapes converge on: for every target this operation
already verified and is not seen lifted now, retry its walk+select once; a second
failure refuses and unwinds everything. Cases I-M (`OccludedPlayScreen`, below)
drive this directly -- I/J the original I-48 shape (recovered / double failure), K
the control, L/M the sibling shape (recovered / double failure).

Cases A-C drive `input_controller._verified_select_and_play_inner` directly against a
FakeScreen (the `PlayScreen` class below, in the same style as
`test_commit_refuses_unseen_strays.py`'s `LiftScreen` / `test_walk_crosses_occluded_
slot.py`'s `OccludedScreen`) -- real code, fake screen, no console. Cases D-E drive
`orchestrator.record_refused_select` directly with a temp diagnostics root. Mutants
apply a REAL, targeted edit to the source file on disk, clear its `__pycache__`, and
reload the module -- the CLAUDE.md 10.9/10.10 shape, not a monkeypatched stand-in --
then restore the original bytes and verify the sha256 matches before moving on.
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

import contextlib                                                    # noqa: E402
import hashlib                                                       # noqa: E402
import importlib                                                     # noqa: E402
import io                                                             # noqa: E402
import json                                                           # noqa: E402
import tempfile                                                       # noqa: E402

import input_controller as ic                                        # noqa: E402
import orchestrator as orch                                          # noqa: E402
from PIL import Image                                                 # noqa: E402

fails = []


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


N = ic.MAX_HAND_SIZE
REST = [200, 160, 150, 165, 220]

ic.time.sleep = lambda d: None


class PlayScreen:
    """A 5-slot fan driving `_verified_select_and_play_inner` end to end.

    `cur` is the cursor's slot (glow-based, matching `OccludedScreen`'s 27.0/0.0
    convention -- clear of `CURSOR_GLOW_MIN`/`CURSOR_GLOW_MAX` in local_hand.py).
    `lifted` is the set of currently selected slots. `never_lands` names slots whose
    select_card press is ALWAYS swallowed -- the console's measured 15.20% drop rate
    (CLAUDE.md §5) landing on one slot every single time, which is what the live log
    actually shows for the tactics slot next to the occluded one. Every other slot
    behaves like a real select_card TOGGLE. `confirm_play` empties the fan (n->0),
    the same "fan-gone" sentinel `_fan_state()` reads as a landed play.
    """

    def __init__(self, cur=0, never_lands=frozenset()):
        self.cur = cur
        self.lifted = set()
        self.never_lands = set(never_lands)
        self.sent = []
        self.confirmed_sel = None
        self.fan_gone = False

    def press(self, key):
        self.sent.append(key)
        if self.fan_gone:
            return
        if key == "move_left":
            self.cur = max(0, self.cur - 1)
        elif key == "move_right":
            self.cur = min(N - 1, self.cur + 1)
        elif key == "select_card":
            if self.cur in self.never_lands:
                return
            if self.cur in self.lifted:
                self.lifted.discard(self.cur)
            else:
                self.lifted.add(self.cur)
        elif key == "confirm_play":
            self.confirmed_sel = sorted(self.lifted)
            self.fan_gone = True

    def look(self):
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, []
        glow = [0.0] * N
        glow[self.cur] = 27.0
        return glow, list(REST), N, sorted(self.lifted)


class OccludedPlayScreen(PlayScreen):
    """I-48b/I-48c: the live shape -- an OCCLUDED slot can sit between
    card_index and tactics_index (CLAUDE.md 10.28's fan occlusion, `ys[slot]`
    unmeasured), so the walk between them dead-reckons across it (I-32) and can
    fall into the I-02 probe one step short of the target.

    `drop_moves_from={slot: n}` silently drops the next `n` `move_left`/
    `move_right` presses whose cursor is AT `slot` when pressed -- the console's
    own measured press-drop rate (CLAUDE.md section 5), applied at the one place
    that reproduces the live log's exact message sequence: the cursor never
    physically reaches the target, so the walk falls into
    `_probe_select_blind_target` one step short.

    `sabotage_on_probe` (a slot) + `sabotage_on_nth_select` (a 1-indexed count):
    the Nth `select_card` press SYSTEM-WIDE, whatever it was meant to do, costs
    `sabotage_on_probe`'s lift instead, once -- modelling "a blind press this
    operation sent toggled an EARLIER, already-verified target back down",
    which is the mechanism `input_controller._verified_select_and_play_inner`'s
    I-48b re-check exists to repair. It is deliberately mechanism-agnostic:
    the skeptic review (agent_progress/issues/I-48b/skeptic.md, probe2.py R1)
    reproduced the I-48 shape from press mechanics alone (no hook needed) and
    also found the SIBLING shape -- the tactics target's own `_select_verified`
    retry costing the BATTER, with no occlusion and no probe at all
    (run_live_20260921j.log:620-624) -- so this hook is written to model
    EITHER shape by picking which press it lands on, rather than re-deriving
    one specific untraceable press sequence. `sabotage_permanent`, when True,
    also blocks the sabotaged slot from ever landing again (`never_lands`) --
    models a re-check retry that ALSO fails.

    Occluded slots are never themselves toggleable (matching `selected_cards`
    abstaining on any row whose y is unmeasured, CLAUDE.md 10.28), so
    `confirmed_sel` only ever reflects genuinely playable slots.
    """

    def __init__(self, cur=0, occluded=frozenset(), never_lands=frozenset(),
                 drop_moves_from=None, sabotage_on_probe=None,
                 sabotage_on_nth_select=None, sabotage_permanent=False):
        super().__init__(cur=cur, never_lands=never_lands)
        self.occluded = set(occluded)
        self.drop_budget = dict(drop_moves_from or {})
        self.sabotage_on_probe = sabotage_on_probe
        self.sabotage_on_nth_select = sabotage_on_nth_select
        self.sabotage_permanent = sabotage_permanent
        self._select_count = 0

    def press(self, key):
        self.sent.append(key)
        if self.fan_gone:
            return
        if key in ("move_left", "move_right"):
            if self.drop_budget.get(self.cur, 0) > 0:
                self.drop_budget[self.cur] -= 1
                return  # the console silently declined this one
            if key == "move_left":
                self.cur = max(0, self.cur - 1)
            else:
                self.cur = min(N - 1, self.cur + 1)
        elif key == "select_card":
            self._select_count += 1
            if (self.sabotage_on_probe is not None
                    and self._select_count == self.sabotage_on_nth_select):
                self.lifted.discard(self.sabotage_on_probe)
                if self.sabotage_permanent:
                    self.never_lands.add(self.sabotage_on_probe)
                self.sabotage_on_probe = None
                return  # this press cost an earlier target instead
            if self.cur in self.occluded:
                return  # occluded slots are never toggleable themselves
            if self.cur in self.never_lands:
                return
            if self.cur in self.lifted:
                self.lifted.discard(self.cur)
            else:
                self.lifted.add(self.cur)
        elif key == "confirm_play":
            self.confirmed_sel = sorted(self.lifted)
            self.fan_gone = True

    def look(self):
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, []
        glow = [0.0] * N
        if self.cur not in self.occluded:
            glow[self.cur] = 27.0
        ys = [None if i in self.occluded else REST[i] for i in range(N)]
        sel = sorted(s for s in self.lifted if s not in self.occluded)
        return glow, ys, N, sel


class TacticsKindPlayScreen(PlayScreen):
    """I-48e: carries a per-slot BASELINE `kind` on `.kinds`, the same
    `orchestrator._CursorSel` shape `hand_cursor_look` returns (see its own
    docstring) -- this is what `_kinds0 = getattr(before_all, "kinds", None)`
    reads, and every OTHER screen in this file returns a plain list, so
    `_kinds0` is `None` for cases A-M and the new gate is permissive there
    (unchanged). Two independent fault-injection knobs, each keyed by the
    1-indexed number of the `look()` call across the WHOLE operation (found by
    tracing a real run once, same method as `test_lifted_discard_row_rescued.
    py` case (5)'s own queue):

      `hide_on_call={call_n: {slots}}`  a pure READ glitch -- these slots are
                                         omitted from `sel` on call `call_n`
                                         ONLY; `self.lifted` (the real state)
                                         is untouched, so the NEXT look reads
                                         correctly again. Models the I-26
                                         tactics-row flicker case (N).
      `drop_on_call={call_n: {slots}}`  a REAL drop -- these slots are removed
                                         from `self.lifted` itself, right
                                         before call `call_n` builds its
                                         answer, so every look from then on
                                         reads them missing until a genuine
                                         select_card re-lifts them. Models a
                                         real silent toggle-off, case (O).
    """

    def __init__(self, cur=0, kinds=None, hide_on_call=None, drop_on_call=None,
                 **kw):
        super().__init__(cur=cur, **kw)
        self.kinds = list(kinds) if kinds is not None else ["player"] * N
        self.hide_on_call = {k: set(v) for k, v in (hide_on_call or {}).items()}
        self.drop_on_call = {k: set(v) for k, v in (drop_on_call or {}).items()}
        self._look_n = 0

    def look(self):
        self._look_n += 1
        for slot in self.drop_on_call.get(self._look_n, ()):
            self.lifted.discard(slot)
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, orch._CursorSel([], list(self.kinds))
        glow = [0.0] * N
        glow[self.cur] = 27.0
        hide = self.hide_on_call.get(self._look_n, set())
        sel = sorted(s for s in self.lifted if s not in hide)
        return glow, list(REST), N, orch._CursorSel(sel, list(self.kinds))


class NeighbourOcclusionPlayScreen(PlayScreen):
    """I-56: `m_slot`'s own position reads UNREADABLE for exactly as long as
    `t_slot` is lifted AND `m_slot` itself is not -- the live mechanic
    `resolve_neighbour_occlusion` (I-52) and `resolve_target_behind_lifted_
    neighbour` (I-56) both exist for: a raised card visually covers an
    ADJACENT, RESTING card's disc/wreath. Once BOTH slots are lifted the
    occlusion clears -- I-52's own case H already establishes this (the
    resolver re-raises its `t_slot` and the subsequent commit still reads
    the disambiguated `m_slot` fine). Distinct from `OccludedPlayScreen`'s
    `occluded` set, which is a STATIC, position-baked unreadable slot.

    `m_slot_chronic=True` instead makes `m_slot` unreadable NO MATTER WHAT
    `t_slot` does -- models a wreath-read failure unrelated to any lift
    (case Q: the manoeuvre correctly gives up and restores `t_slot`).
    `t_slot_never_reraises=True` blocks `select_card` on `t_slot` FOREVER
    once it has been lowered once by this class (case R: the manoeuvre's own
    re-raise fails).

    `t_slot` STARTS ALREADY LIFTED (I-56 part 3): with the fix that lets
    `_select_verified` trust the OPERATION's own baseline, a batter selected
    FRESH during this same operation is readable at `_ys0` before anything
    is pressed, and that baseline alone resolves `m_slot` directly -- this
    class's whole lower/look/re-raise manoeuvre would never even run. To
    keep exercising it as the FALLBACK it now is (baseline-trust applies
    only when the operation's OWN start was ALSO blind), `t_slot` is
    residually lifted from construction, matching `HandRig`'s own pattern in
    test_discard_confirm_verified.py.
    """

    def __init__(self, cur=0, m_slot=None, t_slot=None, m_slot_chronic=False,
                 t_slot_never_reraises=False, **kw):
        super().__init__(cur=cur, **kw)
        self.m_slot = m_slot
        self.t_slot = t_slot
        if t_slot is not None:
            self.lifted.add(t_slot)
        self.m_slot_chronic = m_slot_chronic
        self.t_slot_never_reraises = t_slot_never_reraises
        self._t_slot_lowered_once = False
        self.select_log = []          # cursor position at every select_card

    def press(self, key):
        self.sent.append(key)
        if self.fan_gone:
            return
        if key == "move_left":
            self.cur = max(0, self.cur - 1)
        elif key == "move_right":
            self.cur = min(N - 1, self.cur + 1)
        elif key == "select_card":
            self.select_log.append(self.cur)
            if (self.t_slot_never_reraises and self.cur == self.t_slot
                    and self._t_slot_lowered_once
                    and self.t_slot not in self.lifted):
                return                 # the re-raise is dropped, forever
            if self.cur in self.lifted:
                self.lifted.discard(self.cur)
                if self.cur == self.t_slot:
                    self._t_slot_lowered_once = True
            else:
                self.lifted.add(self.cur)
        elif key == "confirm_play":
            self.confirmed_sel = sorted(self.lifted)
            self.fan_gone = True

    def look(self):
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, []
        glow = [0.0] * N
        glow[self.cur] = 27.0
        ys = list(REST)
        occluded_now = set()
        if self.m_slot is not None:
            occluded = self.m_slot_chronic or (
                self.t_slot in self.lifted and self.m_slot not in self.lifted)
            if occluded:
                ys[self.m_slot] = None
                occluded_now.add(self.m_slot)
        sel = sorted(s for s in self.lifted if s not in occluded_now)
        return glow, ys, N, sel


class InferredSelectPlayScreen(PlayScreen):
    """I-48f (skeptic, live 2026-09-22): models I-21 literally, end to end
    through `_verified_select_and_play_inner`, rather than driving
    `_select_verified` directly (P2/Q2/R2's `BaselineSelectScreen`, which
    carries a name-only baseline). Whatever slot this operation lifts reads
    its OWN disc UNREADABLE (`ys[slot] is None`) and is ABSENT from `sel` for
    as long as it stays up -- I-21's own mechanism ("selecting a card is what
    blinds its own disc"), applied uniformly rather than to one hand-picked
    slot, so EVERY successful selection through this fixture is necessarily
    an INFERENCE, exactly like the live log the skeptic quoted
    (`slot 3's disc is unreadable after the press and was readable before it
    -- selected by inference`). The bug this reproduces is downstream of the
    inference, not in it: the shared I-48b/e re-check's own fresh look never
    sees an inferred target in `sel` either -- that is the SAME abstention,
    not a new one -- and reading that as 'no longer lifted' sends the
    manoeuvre back to re-select a card that never came down."""

    def look(self):
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, []
        glow = [0.0] * N
        glow[self.cur] = 27.0
        ys = [None if i in self.lifted else REST[i] for i in range(N)]
        sel = []          # a lifted slot NEVER reads in sel -- I-21, always
        return glow, ys, N, sel


class NewBlindNonWantPlayScreen(PlayScreen):
    """I-56 SKEPTIC ROUND 2, MY-M1: slot 2 is never `want`, never pressed and
    never walked near -- it reads fine on THIS operation's own baseline look
    (call 1) and then goes unreadable from the very next look onward, modelling
    an unrelated animation glitch rather than anything this operation raised.
    That is the exact `_new_blind` shape `_clear_strays`' ledger-gated mark
    exists for (I-56 R1): the mark must fire only when THIS operation's own
    ledger shows an unaccounted press that could explain it, never merely
    because a PRIOR, unrelated operation left the ledger dirty and nothing
    reset it."""

    def __init__(self, cur=0, blind_from_call=2, **kw):
        super().__init__(cur=cur, **kw)
        self.blind_from_call = blind_from_call
        self._look_n = 0

    def look(self):
        self._look_n += 1
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, []
        glow = [0.0] * N
        glow[self.cur] = 27.0
        ys = list(REST)
        if self._look_n >= self.blind_from_call:
            ys[2] = None
        sel = sorted(self.lifted)
        return glow, ys, N, sel


class Q17FrameScreen(PlayScreen):
    """I-56 SKEPTIC ROUND 2, MY-M3: the exact live Q17 frame
    (`test_fixtures/user_truth/20260922_0215/Q17_1790041074877095000_hand.png`,
    `run_live_20260921x.log` 651-672). `_ys = [201, None, 139, 157, 217]`,
    `glow = [28.2, 1.1, 0.4, 0.5, 0.6]`, `sel = []` -- slot 1 is a genuine
    fielding_boost whose TYPE banner missed the read (type_score 0.805,
    I-36's own misread shape), CHRONIC and UNTOUCHED: it is not `want`, this
    operation never presses near it, and nothing has ever marked it. Slot 0
    (the pitcher) is the user's own ground truth and is readable and
    unselected."""

    def __init__(self, **kw):
        super().__init__(cur=0, **kw)

    def look(self):
        if self.fan_gone:
            return [0.0] * N, [None] * N, 0, []
        glow = [28.2, 1.1, 0.4, 0.5, 0.6]
        ys = [201, None, 139, 157, 217]
        sel = sorted(self.lifted)
        kinds = ["player", "tactics", "player", "player", "player"]
        return glow, ys, N, orch._CursorSel(sel, kinds)


def _play(card_index, tactics_index):
    """Run one play through the REAL function, capturing stdout and every
    `_unwind_selection` call (target set only) without altering its behaviour."""
    calls = []
    real_unwind = ic._unwind_selection

    def _spy(before, look, ours, ys0=None):
        calls.append(set(ours))
        return real_unwind(before, look, ours, ys0=ys0)

    real_press = ic.press
    ic._unwind_selection = _spy
    ic.press = s.press
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            ok = ic._verified_select_and_play_inner(card_index, tactics_index, s.look)
    finally:
        ic._unwind_selection = real_unwind
        ic.press = real_press
    return ok, buf.getvalue(), calls


try:
    # =====================================================================
    print("(A) tactics never lands -> the batter alone is committed")
    # =====================================================================
    s = PlayScreen(cur=0, never_lands={1})
    ok, out, unwind_calls = _play(0, 1)
    check("(A) play succeeds", ok is True)
    check("(A) only the batter (slot 0) was committed", s.confirmed_sel == [0])
    check("(A) exactly one confirm_play press",
          s.sent.count("confirm_play") == 1)
    check("(A) the tactics select actually failed 5 times first",
          "select_card never landed after 5 attempts" in out)
    check("(A) the log names the fallback",
          "dropping the boost and playing the batter alone" in out)
    check("(A) the tactics attempt was unwound (not the batter's)",
          unwind_calls == [{1}])

    # =====================================================================
    print("(B) tactics lands -> both are committed (control, unchanged)")
    # =====================================================================
    s = PlayScreen(cur=0)
    ok, out, unwind_calls = _play(0, 1)
    check("(B) play succeeds", ok is True)
    check("(B) both slots committed", s.confirmed_sel == [0, 1])
    check("(B) exactly one confirm_play press",
          s.sent.count("confirm_play") == 1)
    check("(B) no fallback fired", "dropping the boost" not in out)
    check("(B) no unwind was needed at all", unwind_calls == [])

    # =====================================================================
    print("(C) the BATTER itself never lands -> refused as before (control)")
    # =====================================================================
    s = PlayScreen(cur=0, never_lands={0})
    ok, out, unwind_calls = _play(0, None)
    check("(C) play refuses", ok is False)
    check("(C) nothing was ever committed", s.confirmed_sel is None)
    check("(C) confirm_play was never sent", "confirm_play" not in s.sent)
    check("(C) the batter's own select failed 5 times",
          "select_card never landed after 5 attempts" in out)
    check("(C) the I-48 fallback did NOT fire for a batter failure",
          "dropping the boost" not in out)
    check("(C) the ORIGINAL refusal path unwound the batter's own targets",
          unwind_calls == [{0}])

    # =====================================================================
    print("(F) tactics-only call (card_index=None), select never lands -> "
          "REFUSES with no confirm press (I-48 skeptic S-2)")
    # =====================================================================
    # The pre-fix guard was `target == tactics_index and target != card_index`, which
    # is TRUE when card_index is None -- the paragraph it sits under assumes
    # "card_index's own walk+select already succeeded above", which is exactly false
    # for a tactics-only call (no production caller passes card_index=None today, but
    # the signature allows it). Reproduced by the skeptic: `want` became `set()` and
    # confirm_play was sent on an EMPTY fan, returning True. `card_index is not None`
    # closes it.
    s = PlayScreen(cur=1, never_lands={1})
    ok, out, unwind_calls = _play(None, 1)
    check("(F) a tactics-only call still refuses when its select never lands",
          ok is False)
    check("(F) nothing was ever committed", s.confirmed_sel is None)
    check("(F) confirm_play was never sent on the empty fan", "confirm_play" not in s.sent)
    check("(F) the I-48 fallback did NOT fire (card_index is None)",
          "dropping the boost" not in out)

    # =====================================================================
    print("(D) record_refused_select writes NOTHING under BASEBALL_TEST_RUN")
    # =====================================================================
    # I-48 SKEPTIC S-4: the capture is stubbed to WORK here, the same as case E --
    # otherwise this case's two checks pass whenever the capture merely FAILS (which
    # record_refused_select's own `except Exception: return None` already covers on
    # its own, guard or no guard), and the mutant that strips the _running_under_test()
    # guard survives on any machine where the stub -- or a real screen -- succeeds.
    # The stub proves the guard itself is what refuses the write, not a coincidental
    # capture failure.
    #
    # CLAUDE.md Sec2 "a test must never glob a directory a live run writes to": the
    # real DEAL_FRAME_DIR is exactly that -- diagnostics/deal_frames/ picks up
    # refused_select_* dirs from live cycles, and asserting against it made this case
    # fail whenever one was sitting there, unrelated to the guard under test. The
    # guard returns None BEFORE `d = d or DEAL_FRAME_DIR` is ever reached, so
    # DEAL_FRAME_DIR is monkeypatched to a fresh temp root here purely so the *mutant*
    # below (guard stripped) has somewhere harmless to write instead of the real
    # corpus -- and so this case can assert on that temp root instead of reading the
    # live directory at all.
    _real_grab_d = orch._grab_settle_regions
    _real_look_d = orch.hand_cursor_look
    _real_deal_dir_d = orch.DEAL_FRAME_DIR
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [2])
    _os.environ["BASEBALL_TEST_RUN"] = "1"
    try:
        with tempfile.TemporaryDirectory() as _watch:
            orch.DEAL_FRAME_DIR = _watch
            # No out_dir and no env override -- the same _running_under_test() gate
            # record_reveal_kind / record_money_read_frame already use.
            _os.environ.pop(orch.REFUSED_SELECT_DIR_ENV, None)
            got = orch.record_refused_select(0, "player+tactics", 1)
            check("(D) returns None under the test flag", got is None)
            check("(D) writes nothing to the temp root",
                  not _os.path.isdir(_watch)
                  or not any(n.startswith("refused_select_")
                             for n in _os.listdir(_watch)))
    finally:
        orch._grab_settle_regions = _real_grab_d
        orch.hand_cursor_look = _real_look_d
        orch.DEAL_FRAME_DIR = _real_deal_dir_d

    # =====================================================================
    print("(E) record_refused_select writes the dir + why.json when not "
          "under the flag (out_dir bypasses it, same as record_reveal_kind)")
    # =====================================================================
    _real_grab = orch._grab_settle_regions
    _real_look = orch.hand_cursor_look
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [2])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = orch.record_refused_select(3, "player", 2, out_dir=tmp)
            check("(E) a directory was written", out_dir is not None
                  and _os.path.isdir(out_dir))
            check("(E) it lives under the requested root, named refused_select_*",
                  out_dir is not None
                  and _os.path.dirname(out_dir) == tmp
                  and _os.path.basename(out_dir).startswith("refused_select_"))
            check("(E) hand.png was saved",
                  out_dir is not None
                  and _os.path.isfile(_os.path.join(out_dir, "hand.png")))
            why_path = _os.path.join(out_dir, "why.json") if out_dir else None
            why = json.load(open(why_path)) if why_path and _os.path.isfile(why_path) else {}
            check("(E) why.json exists", bool(why))
            check("(E) target is recorded", why.get("target") == 3)
            check("(E) kind is recorded", why.get("kind") == "player")
            check("(E) already_selected is recorded from the fresh look",
                  why.get("already_selected") == [2])
            check("(E) attempt is recorded", why.get("attempt") == 2)
    finally:
        orch._grab_settle_regions = _real_grab
        orch.hand_cursor_look = _real_look

    # =====================================================================
    print("(G) play_one_turn's own matchup_info is honest when the fallback "
          "dropped the tactic (I-48 skeptic S-3)")
    # =====================================================================
    # Drives the REAL play_one_turn/hand_to_cards/best_batting_play, not a scripted
    # matchup_info: `_run_harness.Harness` (used by test_reveal_frame_kept.py etc.)
    # stubs play_one_turn itself out via play_results=[...], so it cannot exercise
    # this fix at all -- it lives INSIDE play_one_turn, before that dict is built.
    # Only select_and_play, the screen grabs and tactics_dropped_last_play() are
    # stubbed here; hand_to_cards, best_batting_play, should_redraw and the
    # matchup_info construction all run for real.
    _hand = [
        {"kind": "player", "hand_index": 0, "name": "Test Batter", "power": 7,
         "secondary": 1},
        {"kind": "tactics", "hand_index": 1, "name": "Power Swing",
         "type": "swing_boost", "bonus": 2},
    ]
    _state_json = {"phase": "batting", "your_score": 0, "opp_score": 0,
                   "discards_left": 0, "runners": [], "hand": _hand}

    _real_select_and_play = orch.select_and_play
    _real_grab_g = orch._grab_settle_regions
    _real_tdl = ic.tactics_dropped_last_play
    orch.select_and_play = lambda *a, **k: True
    orch._grab_settle_regions = lambda regions: {r: Image.new("L", (10, 10))
                                                  for r in regions}
    try:
        # (G-control) the fallback did NOT fire -- the engine's own tactics
        # choice is logged unchanged, and tactics_dropped is False.
        ic.tactics_dropped_last_play = lambda: False
        played, info = orch.play_one_turn(_state_json, 0)
        check("(G-control) played", played is True)
        check("(G-control) a tactics card was actually chosen by the engine",
              info.get("our_tactics_kind") == "swing_boost"
              and info.get("our_tactics_bonus") == 2)
        check("(G-control) tactics_dropped is False", info.get("tactics_dropped") is False)

        # (G) the fallback DID fire -- the engine still CHOSE a tactics card
        # (decision.tactics_card is the same swing_boost), but it never went in,
        # so the logged row must show no kind/bonus and carry tactics_dropped.
        ic.tactics_dropped_last_play = lambda: True
        played, info = orch.play_one_turn(_state_json, 0)
        check("(G) played (the batter alone still committed)", played is True)
        check("(G) our_tactics_kind is None, not the engine's chosen swing_boost",
              info.get("our_tactics_kind") is None)
        check("(G) our_tactics_bonus is 0, not the engine's chosen 2",
              info.get("our_tactics_bonus") == 0)
        check("(G) tactics_dropped is True", info.get("tactics_dropped") is True)
    finally:
        orch.select_and_play = _real_select_and_play
        orch._grab_settle_regions = _real_grab_g
        ic.tactics_dropped_last_play = _real_tdl

    # =====================================================================
    print("(H) orchestrator.spend_and_play reads tactics_dropped_last_play() too "
          "(QA8, agent_progress/qa8/silent_state) -- a hand-driven crawl calling "
          "spend_and_play directly (tools/match_crawl.py) must not report a play "
          "whose tactics attachment was dropped as a clean COMMIT")
    # =====================================================================
    _real_select_and_play_ic = ic.select_and_play
    _real_tdl_h = ic.tactics_dropped_last_play
    ic.select_and_play = lambda *a, **k: True
    try:
        # (H-control) the fallback did NOT fire -- why stays None, same as before
        # this fix, and both slots are forgotten from hand memory either way.
        orch._hand_memory.clear()
        orch._hand_memory[0] = {"power": "7", "secondary": 1, "art": None}
        orch._hand_memory[1] = {"power": None, "secondary": 2, "art": None}
        ic.tactics_dropped_last_play = lambda: False
        ok, why = orch.spend_and_play(0, 1)
        check("(H-control) ok is True", ok is True)
        check("(H-control) why carries no drop message", why is None)
        check("(H-control) both slots are still forgotten",
              0 not in orch._hand_memory and 1 not in orch._hand_memory)

        # (H) the fallback DID fire -- select_and_play still returns True (the
        # batter alone committed), but spend_and_play must now say so instead of
        # reporting a silent COMMIT: `why` names the dropped slot and I-48, and
        # the line prints for a crawl script that only reads stdout.
        orch._hand_memory[0] = {"power": "7", "secondary": 1, "art": None}
        orch._hand_memory[1] = {"power": None, "secondary": 2, "art": None}
        ic.tactics_dropped_last_play = lambda: True
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok, why = orch.spend_and_play(0, 1)
        check("(H) ok is still True (the batter alone committed)", ok is True)
        check("(H) why names the dropped tactics slot and I-48",
              why is not None and "tactics slot 1" in why and "DROPPED" in why
              and "I-48" in why)
        check("(H) the drop is printed, not just returned",
              "DROPPED" in buf.getvalue() and "tactics slot 1" in buf.getvalue())
        check("(H) both slots are still forgotten",
              0 not in orch._hand_memory and 1 not in orch._hand_memory)
    finally:
        ic.select_and_play = _real_select_and_play_ic
        ic.tactics_dropped_last_play = _real_tdl_h
        orch._hand_memory.clear()

    # =====================================================================
    print("(I) THE LIVE SHAPE (I-48b): batter verified, tactics walk crosses an "
          "occluded slot and the probe fails, silently costing the batter's own "
          "selection -> the SHARED re-check before commit retries the batter "
          "rather than trusting the stale belief, and commits the batter alone")
    # =====================================================================
    # overnight/run_live_20260921s.log ~369-400: hand [swing_boost +2, UNKNOWN
    # (occluded slot 1), 5/3 (card_index=2), speed_boost +1, 5/2], decision
    # batter=2 + tactics=0. The walk from 2 to 0 dead-reckons across occluded
    # slot 1, one navigation press toward the target is dropped so the cursor
    # never physically arrives, and the probe fires. Post-I-51 (B1) this is
    # caught EARLY as a disappearance ("probe-select made 2 disappear ...
    # re-selecting it") rather than looping to "raised nothing after N
    # attempts" -- but the corrective re-select itself cannot land either
    # (the fake's cursor never physically reaches slot 2), so the probe still
    # genuinely fails ("could not re-select probe slot 2 -- refusing rather
    # than leaving it lost"), and (per the live log) card_index ends up
    # unselected by the time the old code checked. The exact press-by-press
    # parity that cost it is not recoverable from the log text alone -- see
    # agent_progress/issues/I-48b/skeptic.md section 1, which PROVED it by
    # elimination and reproduced it from press mechanics alone (probe2.py R1,
    # no sabotage hook needed) -- `sabotage_on_nth_select` here models the NET
    # effect the log and the skeptic's own reproduction both establish.
    s = OccludedPlayScreen(cur=2, occluded={1}, drop_moves_from={1: 1},
                            sabotage_on_probe=2, sabotage_on_nth_select=2)
    ok, out, unwind_calls = _play(2, 0)
    check("(I) play succeeds by recovering the batter, not refusing", ok is True)
    check("(I) the batter alone was committed (tactics dropped)",
          s.confirmed_sel == [2])
    check("(I) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(I) the occluded slot was dead-reckoned first",
          "slot 1 is occluded" in out)
    check("(I) the tactics probe genuinely failed",
          "could not re-select probe slot 2" in out)
    check("(I) the fallback fired",
          "dropping the boost and playing the batter alone" in out)
    check("(I) the batter was found NOT lifted and re-selected, never assumed",
          "was verified earlier this operation and is no longer lifted" in out
          and "re-selecting before committing (I-48b)" in out)

    # =====================================================================
    print("(J) tactics fails AND the batter's retry ALSO fails -> refused, "
          "nothing committed, no confirm_play (I-48b)")
    # =====================================================================
    s = OccludedPlayScreen(cur=2, occluded={1}, drop_moves_from={1: 1},
                            sabotage_on_probe=2, sabotage_on_nth_select=2,
                            sabotage_permanent=True)
    ok, out, unwind_calls = _play(2, 0)
    check("(J) play refuses", ok is False)
    check("(J) nothing was ever committed", s.confirmed_sel is None)
    check("(J) confirm_play was never sent", "confirm_play" not in s.sent)
    check("(J) the batter re-select was attempted and failed",
          "was verified earlier this operation and is no longer lifted" in out
          and "could not be re-verified" in out)
    check("(J) the refusal names I-48b, not a silent drop",
          "refusing rather than committing an unproven selection (I-48b)" in out)

    # =====================================================================
    print("(K) CONTROL: both land despite crossing the same occluded slot -> "
          "both committed, no fallback and no re-check fires at all")
    # =====================================================================
    s = OccludedPlayScreen(cur=2, occluded={1})   # no drops, no sabotage
    ok, out, unwind_calls = _play(2, 0)
    check("(K) play succeeds", ok is True)
    check("(K) both slots committed", s.confirmed_sel == [0, 2])
    check("(K) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(K) the occluded slot was still dead-reckoned",
          "slot 1 is occluded" in out)
    check("(K) neither fallback nor the re-check fired",
          "dropping the boost" not in out and "I-48b" not in out)
    check("(K) no unwind was needed at all", unwind_calls == [])

    # =====================================================================
    print("(L) THE SIBLING SHAPE (I-48c, skeptic N1): the TACTICS target's "
          "OWN walk and select both succeed -- no occlusion, no I-48 branch, "
          "no I-02 probe -- but its own select_verified retry silently costs "
          "the BATTER. The I-48-branch-local re-check could never see this; "
          "the SHARED re-check before commit does, and both are committed.")
    # =====================================================================
    # overnight/run_live_20260921j.log:620-624 (also 20260921o.log:1040-1050):
    #     verified on 0 after 2 press(es)   <- batter
    #     verified on 1 after 1 press(es)   <- tactics
    #     select_card did not land (attempt 1) — retrying
    #     select_card landed on attempt 2
    #     the engine's cards [0, 1] are not all lifted ([1]) — refusing
    # Both walks land cleanly; the tactics target's OWN select_card needs two
    # attempts, and somewhere in there the batter's own selection is gone.
    # card_index=0, tactics_index=1, no occlusion needed at all -- the second
    # select_card press system-wide is what tactics's own retry sends.
    s = OccludedPlayScreen(cur=0, sabotage_on_probe=0, sabotage_on_nth_select=2)
    ok, out, unwind_calls = _play(0, 1)
    check("(L) play succeeds, both committed", ok is True)
    check("(L) both slots committed", s.confirmed_sel == [0, 1])
    check("(L) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(L) the tactics target needed no I-48 fallback at all",
          "dropping the boost" not in out)
    check("(L) the batter was found missing and re-selected by the SHARED "
          "re-check", "was verified earlier this operation and is no longer "
          "lifted" in out and "re-selecting before committing (I-48b)" in out)

    # =====================================================================
    print("(M) THE SIBLING SHAPE, DOUBLE FAILURE: tactics lands, the batter is "
          "lost, and the re-check's own retry ALSO fails -> refused, nothing "
          "committed")
    # =====================================================================
    s = OccludedPlayScreen(cur=0, sabotage_on_probe=0, sabotage_on_nth_select=2,
                            sabotage_permanent=True)
    ok, out, unwind_calls = _play(0, 1)
    check("(M) play refuses", ok is False)
    check("(M) nothing was ever committed", s.confirmed_sel is None)
    check("(M) confirm_play was never sent", "confirm_play" not in s.sent)
    check("(M) the batter re-select was attempted and failed",
          "was verified earlier this operation and is no longer lifted" in out
          and "could not be re-verified" in out)

    # =====================================================================
    print("(N) I-48e: a TACTICS-baseline target reads unlifted ONCE at the "
          "shared re-check, then lifted again on the re-look -- a flicker, "
          "not a toggle -- so no navigation presses are sent and both commit")
    # =====================================================================
    # card_index=0 (kind 'player'), tactics_index=1 (kind 'tactics'). Both
    # land cleanly through the per-target loop with no occlusion and no
    # sabotage. The shared re-check's OWN preliminary look is call 9 (traced
    # once against the real code, same method as case (5)'s own queue) --
    # `hide_on_call` omits slot 1 from `sel` on THAT call only, so `self.
    # lifted` never actually changes and the very next look (the I-48e
    # confirmatory re-look) reads it correctly again.
    s = TacticsKindPlayScreen(cur=0, kinds=["player", "tactics", "player",
                                             "player", "player"],
                               hide_on_call={9: {1}})
    ok, out, unwind_calls = _play(0, 1)
    check("(N) play succeeds, both committed", ok is True)
    check("(N) both slots committed", s.confirmed_sel == [0, 1])
    check("(N) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(N) no navigation press was sent for the flicker -- the real fix "
          "is not entered at all",
          s.sent == ["select_card", "move_right", "select_card", "confirm_play"])
    check("(N) the re-look fired and named the flicker, not a real drop",
          "read unlifted on a tactics-baseline row" in out
          and "is lifted again on the re-look" in out
          and "tactics-row flicker (I-26), not a real drop" in out)
    check("(N) the I-48b re-select line never fired -- nothing was ever "
          "treated as genuinely missing", "re-selecting before committing "
          "(I-48b)" not in out)
    check("(N) no unwind was needed at all", unwind_calls == [])

    # =====================================================================
    print("(O) I-48e: a TACTICS-baseline target reads unlifted on BOTH the "
          "shared re-check's own look and the confirmatory re-look -- a real "
          "drop, not a flicker -- so the existing retry (one walk+select) "
          "runs and recovers it, exactly as I-48b already does for a player "
          "target")
    # =====================================================================
    # Same setup as (N), but `drop_on_call` removes slot 1 from `self.lifted`
    # for real at call 9 (the preliminary look), so it is genuinely gone by
    # the confirmatory look (call 10) too -- the I-48e gate then adds it to
    # `_missing` for the existing retry loop, which walks to it and presses
    # select_card once more, landing for real.
    s = TacticsKindPlayScreen(cur=0, kinds=["player", "tactics", "player",
                                             "player", "player"],
                               drop_on_call={9: {1}})
    ok, out, unwind_calls = _play(0, 1)
    check("(O) play succeeds by recovering the tactics target", ok is True)
    check("(O) both slots committed", s.confirmed_sel == [0, 1])
    check("(O) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(O) the retry sent exactly one extra select_card press",
          s.sent == ["select_card", "move_right", "select_card", "select_card",
                     "confirm_play"])
    check("(O) the re-look fired and confirmed a real drop, not a flicker",
          "read unlifted on a tactics-baseline row" in out
          and "is lifted again on the re-look" not in out)
    check("(O) the existing I-48b re-select ran and recovered it",
          "was verified earlier this operation and is no longer lifted" in out
          and "re-selecting before committing (I-48b)" in out)
    check("(O) no unwind was needed -- the retry succeeded", unwind_calls == [])

    # =====================================================================
    print("(P) I-56 THE LIVE SHAPE: the batter's own lift occludes the "
          "adjacent tactics target's wreath -- lower the batter, select the "
          "tactics card, re-raise the batter; both commit")
    # =====================================================================
    # overnight/run_live_20260921x.log ~419-430 (cycle 12 match 2): hand
    # [4/3, 4/3, 4/3, speed_boost +1, 8/1], decision batter=4 + tactics=3.
    # "probe-select: 4 lifted -- the cursor was there", "verified on 3 after
    # 1 press(es)", then slot 3's own _select_verified refuses outright
    # ("slot 3's position is unreadable ... refusing rather than pressing a
    # TOGGLE blind") -> the I-48 fallback used to fire here, dropping the
    # boost. card_index=4, tactics_index=3, adjacent.
    s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4)
    ok, out, unwind_calls = _play(4, 3)
    check("(P) play succeeds, both committed", ok is True)
    check("(P) both slots committed", s.confirmed_sel == [3, 4])
    check("(P) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(P) the I-48 fallback did NOT fire -- the boost was recovered",
          "dropping the boost" not in out)
    check("(P) the manoeuvre's own presses, IN ORDER: lower 4, select 3, "
          "re-raise 4 -- card_index=4 was already selected at baseline, so "
          "the per-target loop's own first attempt costs no press at all",
          s.select_log == [4, 3, 4])
    check("(P) every press in the manoeuvre was look-gated (each landed and "
          "was independently verified, not a single blind burst)",
          "slot 3 selected behind slot 4's lift" in out)
    check("(P) no unwind was needed at all", unwind_calls == [])

    # =====================================================================
    print("(Q) I-56: the tactics target is STILL blind once the batter "
          "comes down -- not this occlusion -- the batter is restored and "
          "the ordinary I-48 fallback fires exactly as before this ticket")
    # =====================================================================
    s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4,
                                      m_slot_chronic=True)
    ok, out, unwind_calls = _play(4, 3)
    check("(Q) play succeeds by falling back to the batter alone", ok is True)
    check("(Q) only the batter (slot 4) was committed", s.confirmed_sel == [4])
    check("(Q) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(Q) slot 4 was restored by the manoeuvre before the fallback ran",
          "restoring 4 (I-56)" in out)
    check("(Q) the I-48 fallback fired", "dropping the boost" in out)
    check("(Q) the tactics attempt was unwound, and it was a no-op -- "
          "nothing was ever raised at slot 3",
          unwind_calls == [{3}])
    check("(Q) the manoeuvre pressed EXACTLY lower-4/re-raise-4 and never "
          "touched slot 3 -- a still-blind read must never reach a "
          "select_card attempt on the target itself",
          s.sent == ["move_right", "move_right", "move_right", "move_right",
                     "move_left", "move_right", "select_card", "select_card",
                     "confirm_play"])

    # =====================================================================
    print("(R) I-56: the occlusion IS resolved and the tactics card selects "
          "cleanly, but the re-raise of the batter is dropped every time -- "
          "REFUSE THE WHOLE PLAY, nothing left half-committed")
    # =====================================================================
    s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4,
                                      t_slot_never_reraises=True)
    ok, out, unwind_calls = _play(4, 3)
    check("(R) play refuses", ok is False)
    check("(R) nothing was ever committed", s.confirmed_sel is None)
    check("(R) confirm_play was never sent", "confirm_play" not in s.sent)
    check("(R) nothing is left lifted", s.lifted == set())
    check("(R) the manoeuvre unwound the tactics select it had just made",
          "refusing and unwinding, nothing half-committed (I-56)" in out)

    # =====================================================================
    print("(S) CONTROL: the tactics target reads fine on its own -- the "
          "I-56 manoeuvre is never even tried, zero extra presses")
    # =====================================================================
    s = PlayScreen(cur=0)
    ok, out, unwind_calls = _play(4, 3)
    check("(S) play succeeds", ok is True)
    check("(S) both slots committed", s.confirmed_sel == [3, 4])
    check("(S) exactly one confirm_play press", s.sent.count("confirm_play") == 1)
    check("(S) no fallback and no I-56 manoeuvre fired",
          "dropping the boost" not in out and "I-56" not in out)
    check("(S) the walk-and-select path is unchanged: walk to 4, select, "
          "walk to 3, select, confirm -- one select_card each",
          s.sent == ["move_right", "move_right", "move_right", "move_right",
                     "select_card", "move_left", "select_card", "confirm_play"])
    check("(S) no unwind was needed at all", unwind_calls == [])

    # =====================================================================
    print("(P2/Q2/R2) I-56 PART 3: the operation's own BASELINE settles "
          "'already selected?' when a fresh, blind read cannot -- drives "
          "_select_verified directly, decoupled from any particular look()-"
          "call sequence, the same way test_discard_confirm_verified.py's "
          "NeighbourRig drives resolve_neighbour_occlusion directly")
    # =====================================================================

    class BaselineSelectScreen:
        """`overnight/run_live_20260921y.log` ~216-225: a tactics wreath
        fails to read AT REST with no lifted neighbour anywhere in sight
        ("slot 3's wreath is partly under slot 4's card edge, the normal fan
        overlap"). `chronic_blind=False` clears the moment the target is
        actually lifted (selecting moves the card clear of the overlap);
        `chronic_blind=True` never clears (the row never reads, whatever is
        pressed -- the worst case, where the existing retry loop's own rules
        decide the outcome exactly as they already do for any blind target).
        """

        def __init__(self, target, chronic_blind=False):
            self.target = target
            self.chronic_blind = chronic_blind
            self.lifted = set()
            self.sent = []

        def press(self, key, **kw):
            self.sent.append(key)
            if key == "select_card":
                if self.target in self.lifted:
                    self.lifted.discard(self.target)
                else:
                    self.lifted.add(self.target)

        def look(self):
            ys = list(REST)
            blind = self.chronic_blind or self.target not in self.lifted
            if blind:
                ys[self.target] = None
            glow = [0.0] * N
            sel = sorted(s for s in self.lifted if not (s == self.target and blind))
            return glow, ys, N, sel

    def _select_direct(target, screen, ys0, sel0):
        real_press = ic.press
        ic.press = screen.press
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ok, sel = ic._select_verified(target, screen.look, ys0=ys0, sel0=sel0)
        finally:
            ic.press = real_press
        return ok, sel, buf.getvalue()

    ic._reset_press_ledger()
    print("(P2) THE LIVE SHAPE: baseline readable and unselected, a CLEAN "
          "ledger -- one press, the row recovers once lifted (a real rise, "
          "or the same already-tested I-21/I-36 inference either way -- "
          "this ticket only widens WHEN a press is allowed, not what "
          "counts as proof)")
    s = BaselineSelectScreen(target=3, chronic_blind=False)
    ok, sel, out = _select_direct(3, s, ys0=list(REST), sel0=set())
    check("(P2) the target is verified selected", ok is True)
    check("(P2) exactly one select_card press", s.sent == ["select_card"])
    check("(P2) the baseline-trust line fired, not the ordinary refusal",
          "read it DOWN and readable" in out and "I-56" in out)

    ic._reset_press_ledger()
    print("(Q2) the BASELINE read of slot 3 was ALSO blind -- refuse "
          "exactly as before, no blind toggle")
    s = BaselineSelectScreen(target=3, chronic_blind=True)
    ys0_blind = list(REST)
    ys0_blind[3] = None
    ok, sel, out = _select_direct(3, s, ys0=ys0_blind, sel0=set())
    check("(Q2) refuses", ok is False)
    check("(Q2) NO press was ever sent -- the baseline could not vouch for "
          "it either", s.sent == [])
    check("(Q2) the ORIGINAL refusal fired, not the I-56 baseline bypass",
          "refusing rather than pressing a TOGGLE blind" in out
          and "I-56" not in out)

    ic._reset_press_ledger()
    print("(R2) slot 3 WAS already selected at baseline -- not pressed "
          "again, treated as already up")
    s = BaselineSelectScreen(target=3, chronic_blind=True)
    ok, sel, out = _select_direct(3, s, ys0=list(REST), sel0={3})
    check("(R2) treated as already selected", ok is True)
    check("(R2) NO press was sent -- it is already up", s.sent == [])
    check("(R2) the baseline-already-selected line fired",
          "already selected -- treating as already up, no press" in out)

    # =====================================================================
    print("(W1)/(W2)/(W3) I-56 SKEPTIC R1: an UNACCOUNTED press this "
          "operation sent is the ONLY thing that may justify marking a "
          "non-target slot's own mere blindness -- reproducing the "
          "skeptic's OP1/OP2 wrong-commit shape and its mirror (no "
          "unaccounted press -> refused, but not marked, the false-"
          "positive shape 14 live firings were)")
    # =====================================================================
    def _look_stray(blind_slot=2, extra_sel=(0,)):
        def _look():
            ys = list(REST)
            ys[blind_slot] = None
            return [0.0] * N, ys, N, sorted(extra_sel)
        return _look

    print("(W1) OP1: engine chose [0]; an UNACCOUNTED select press this "
          "operation sent could explain slot 2 going invisibly blind -- "
          "refuses THIS attempt and, unlike a clean ledger, MARKS it")
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    ic._note_unaccounted_press()
    ok_w1 = ic._clear_strays({0}, _look_stray(), blind_before=set())
    check("(W1) OP1 refuses (slot 2 unexpectedly blind)", ok_w1 is False)
    check("(W1) OP1 marks slot 2 -- an unaccounted press could explain it",
          2 in ic._MAYBE_LIFTED)

    print("(W2) OP2: a LATER, separate operation re-plays the SAME target "
          "-- the mark from OP1 persists (cross-operation, by design) and "
          "REFUSES rather than committing the stray alongside it (parent "
          "commit a99bc6e's own behaviour, restored)")
    ic._reset_press_ledger()
    ok_w2 = ic._clear_strays({0}, _look_stray(), blind_before={2})
    check("(W2) OP2 refuses -- nothing the engine chose is committed "
          "alongside an unproven stray", ok_w2 is False)
    ic.clear_maybe_lifted()

    print("(W3) the mirror: a CLEAN ledger (no unaccounted press this "
          "operation) still refuses THIS attempt, but does NOT mark -- "
          "occlusion and a chronic wreath misread (I-36) are not proof of "
          "a lift, and marking on them alone was the false-positive shape "
          "(14 firings, 0 true positives)")
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    ok_w3 = ic._clear_strays({0}, _look_stray(), blind_before=set())
    check("(W3) refuses this attempt (still cautious)", ok_w3 is False)
    check("(W3) but does NOT mark -- nothing this operation pressed could "
          "explain it", 2 not in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    # =====================================================================
    print("(X1) I-56 SKEPTIC R2: the I-02 probe's OWN select_card already "
          "touched the target -- 'untouched since the baseline' is FALSE, "
          "so the baseline-trust branch must not fire at all, even though "
          "the probe's own press was fully ACCOUNTED")
    # =====================================================================
    ic._reset_press_ledger()
    ic._note_accounted_press(4)   # the probe's own confirmed "4 lifted"
    s_x1 = BaselineSelectScreen(target=4, chronic_blind=True)
    ok_x1, _sel_x1, out_x1 = _select_direct(4, s_x1, ys0=list(REST), sel0=set())
    check("(X1) refuses", ok_x1 is False)
    check("(X1) NO press was sent -- the ledger shows slot 4 was already "
          "touched, confirmed or not", s_x1.sent == [])
    check("(X1) the ORIGINAL refusal fired, not the I-56 baseline bypass",
          "refusing rather than pressing a TOGGLE blind" in out_x1
          and "baseline-trust" not in out_x1)

    # =====================================================================
    print("(Y1) I-56 SKEPTIC R3: the diagonal fixture -- readable baseline, "
          "a row that does NOT recover after the one press, for kinds "
          "None/player/tactics -- exactly ONE press each time, never the "
          "5 the shared retry loop would have sent, and the I-36 gate "
          "still decides infer-vs-refuse exactly as it already does there")
    # =====================================================================
    class _KindBlindScreen:
        def __init__(self, target, kinds):
            self.target = target
            self.kinds = kinds
            self.sent = []

        def press(self, key, **kw):
            self.sent.append(key)   # never actually lifts -- chronic blind

        def look(self):
            ys = list(REST)
            ys[self.target] = None
            sel = orch._CursorSel([], list(self.kinds)) if self.kinds is not None else []
            return [0.0] * N, ys, N, sel

    for _label, _kinds in (("None", None), ("player", ["player"] * N),
                            ("tactics", ["tactics"] * N)):
        ic._reset_press_ledger()
        s_y = _KindBlindScreen(target=3, kinds=_kinds)
        ok_y, _sel_y, out_y = _select_direct(3, s_y, ys0=list(REST), sel0=set())
        check(f"(Y1-{_label}) exactly one select_card press, never a retry "
              "storm", s_y.sent == ["select_card"])
        if _label == "tactics":
            check(f"(Y1-{_label}) refuses -- the I-36 gate blocks the "
                  "inference on a tactics baseline", ok_y is False)
        else:
            check(f"(Y1-{_label}) infers selected -- I-21's own signature "
                  "on a non-tactics baseline, not retried", ok_y is True)

    # =====================================================================
    print("(Z1) I-48f (skeptic, live 2026-09-22): BOTH targets are selected "
          "by INFERENCE (I-21 -- their own disc goes unreadable the instant "
          "they lift, so they never appear in `sel` again). The shared "
          "I-48b/e re-check's fresh look cannot see them either -- that is "
          "the SAME abstention the inference already accounted for, not a "
          "new one -- so it must NOT re-walk and re-select them: no extra "
          "presses, no unwind, a clean commit with exactly the two original "
          "select_card presses")
    # =====================================================================
    s = InferredSelectPlayScreen(cur=0)
    ok_z1, out_z1, calls_z1 = _play(0, 1)
    check("(Z1) play succeeds", ok_z1 is True)
    check("(Z1) both slots committed", s.confirmed_sel == [0, 1])
    check("(Z1) no unwind was triggered by the shared re-check",
          calls_z1 == [])
    check("(Z1) the exact press sequence: select 0 (no move needed), walk "
          "to 1, select 1, confirm -- no re-check walk, no re-toggle",
          s.sent == ["select_card", "move_right", "select_card", "confirm_play"])
    check("(Z1) the re-check named both as inference-consistent rather than "
          "missing", "no longer lifted" not in out_z1)

    # =====================================================================
    print("(AA1) I-56 SKEPTIC ROUND 2, MY-M1: the LIVE ENTRY POINT must reset "
          "the ledger itself -- poison it exactly as a prior, unrelated "
          "operation would leave it (skeptic's probe_acd.py shape), send NO "
          "reset here, and drive the REAL _verified_select_and_play_inner "
          "through _play(). This operation's own press (batter, slot 0) is "
          "fully accounted, so a fresh ledger enters _clear_strays clean; "
          "slot 2 -- never `want`, never pressed, never walked near -- goes "
          "unreadable for reasons this operation cannot explain, and a clean "
          "ledger must NOT mark it. If the ledger enters dirty because "
          "production's own reset never ran, slot 2 gets marked anyway.")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._note_unaccounted_press()
    for _slot in range(N):
        ic._note_accounted_press(_slot)
    s = NewBlindNonWantPlayScreen(cur=0, blind_from_call=2)
    ok_aa1, out_aa1, calls_aa1 = _play(0, None)
    check("(AA1) slot 2 is NOT marked -- this operation's own ledger, reset "
          "by the entry point itself, shows nothing it pressed could explain "
          "slot 2's blindness", 2 not in ic._MAYBE_LIFTED)
    check("(AA1) the refusal fired for the right, unrelated reason (slot 2 "
          "unreadable), not because of anything carried over from before",
          ok_aa1 is False)
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()

    # =====================================================================
    print("(BB1) I-56 SKEPTIC ROUND 2, MY-M3: the live Q17 frame "
          "(run_live_20260921x.log 651-672, user ground truth slot 0) -- "
          "slot 1's wreath is chronic, untouched, never marked, and NOT "
          "`want`. Must COMMIT slot 0 with exactly one select and one "
          "confirm, and ZERO presses anywhere near slot 1.")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    s = Q17FrameScreen()
    ok_bb1, out_bb1, calls_bb1 = _play(0, None)
    check("(BB1) commits the user's own ground truth (slot 0)",
          ok_bb1 is True and s.confirmed_sel == [0])
    check("(BB1) exactly one select_card and one confirm_play, zero presses "
          "touching slot 1 -- cur never leaves 0",
          s.sent == ["select_card", "confirm_play"])

    # =====================================================================
    print()
    print("MUTATION TESTING")
    # =====================================================================
    IC_PATH = _os.path.join(_ROOT, "input_controller.py")
    ORCH_PATH = _os.path.join(_ROOT, "orchestrator.py")

    def _sha(path):
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _clear_pycache(modname):
        d = _os.path.join(_ROOT, "__pycache__")
        if _os.path.isdir(d):
            for fn in _os.listdir(d):
                if fn.startswith(modname + "."):
                    _os.remove(_os.path.join(d, fn))

    def _mutate(path, anchor, replacement):
        with open(path) as f:
            src = f.read()
        n = src.count(anchor)
        if n != 1:
            raise AssertionError(
                f"mutation anchor found {n} times in {path}, expected exactly 1: "
                f"{anchor!r}")
        with open(path, "w") as f:
            f.write(src.replace(anchor, replacement, 1))

    _ic_sha0 = _sha(IC_PATH)
    _orch_sha0 = _sha(ORCH_PATH)

    def _reload_ic():
        global ic
        _clear_pycache("input_controller")
        ic = importlib.reload(ic)
        ic.time.sleep = lambda d: None

    def _reload_orch():
        global orch
        _clear_pycache("orchestrator")
        orch = importlib.reload(orch)

    with open(IC_PATH, "rb") as f:
        _IC_ORIG_BYTES = f.read()
    with open(ORCH_PATH, "rb") as f:
        _ORCH_ORIG_BYTES = f.read()

    def _restore_ic():
        with open(IC_PATH, "wb") as f:
            f.write(_IC_ORIG_BYTES)
        _reload_ic()
        check("input_controller.py restored byte-for-byte",
              _sha(IC_PATH) == _ic_sha0)

    def _restore_orch():
        with open(ORCH_PATH, "wb") as f:
            f.write(_ORCH_ORIG_BYTES)
        _reload_orch()
        check("orchestrator.py restored byte-for-byte",
              _sha(ORCH_PATH) == _orch_sha0)

    # --- mutant 1: drop the batter-alone commit ------------------------------
    print("mutant 1: the fallback's own `continue` becomes `return False` "
          "(the pre-fix behaviour) -- case A must now REFUSE")
    try:
        _mutate(IC_PATH,
                "            tactics_index = None\n"
                "            _LAST_PLAY_DROPPED_TACTICS = True\n"
                "            continue\n",
                "            tactics_index = None\n"
                "            _LAST_PLAY_DROPPED_TACTICS = True\n"
                "            return False\n")
        _reload_ic()
        s = PlayScreen(cur=0, never_lands={1})
        ok, out, unwind_calls = _play(0, 1)
        check("mutant 1 caught: case A no longer succeeds", ok is False)
    finally:
        _restore_ic()

    # --- mutant 2: drop the unwind ------------------------------------------
    print("mutant 2: the fallback no longer unwinds the tactics attempt at all "
          "-- the spy must record zero calls")
    try:
        _mutate(IC_PATH,
                "            _unwind_selection(before_all, look, {tactics_index}, ys0=_ys0)\n",
                "            pass  # I-48 mutant: unwind dropped\n")
        _reload_ic()
        s = PlayScreen(cur=0, never_lands={1})
        ok, out, unwind_calls = _play(0, 1)
        check("mutant 2 caught: no unwind call was made for the tactics slot",
              unwind_calls == [])
    finally:
        _restore_ic()

    # --- sanity: the fix is still intact after both input_controller mutants -
    s = PlayScreen(cur=0, never_lands={1})
    ok, out, unwind_calls = _play(0, 1)
    check("post-restore sanity: case A passes again", ok is True
          and s.confirmed_sel == [0] and unwind_calls == [{1}])

    # --- mutant 3: drop the why.json fields ----------------------------------
    print("mutant 3: record_refused_select only writes 'target' -- case E's "
          "field checks must fail")
    try:
        _mutate(
            ORCH_PATH,
            '        with open(os.path.join(out, "why.json"), "w") as fh:\n'
            '            json.dump({"target": target, "kind": kind,\n'
            '                       "already_selected": list(sel), "attempt": attempt},\n'
            '                      fh, indent=1)\n',
            '        with open(os.path.join(out, "why.json"), "w") as fh:\n'
            '            json.dump({"target": target}, fh, indent=1)\n')
        _reload_orch()
        orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
        orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [2])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = orch.record_refused_select(3, "player", 2, out_dir=tmp)
            why = json.load(open(_os.path.join(out_dir, "why.json")))
            check("mutant 3 caught: kind/already_selected/attempt are gone",
                  "kind" not in why or "already_selected" not in why
                  or "attempt" not in why)
    finally:
        _restore_orch()

    # --- sanity: record_refused_select still writes every field afterwards --
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [2])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = orch.record_refused_select(3, "player", 2, out_dir=tmp)
            why = json.load(open(_os.path.join(out_dir, "why.json")))
            check("post-restore sanity: all four fields are back",
                  why.get("target") == 3 and why.get("kind") == "player"
                  and why.get("already_selected") == [2] and why.get("attempt") == 2)
    finally:
        orch._grab_settle_regions = _real_grab
        orch.hand_cursor_look = _real_look

    # --- mutant 4: drop the flag read in spend_and_play (QA8) ---------------
    print("mutant 4: spend_and_play no longer reads tactics_dropped_last_play() "
          "-- case H must go back to a silent COMMIT")
    try:
        _mutate(
            ORCH_PATH,
            '    if _ic.tactics_dropped_last_play():\n'
            '        why = f"tactics slot {tactics_idx} was DROPPED -- batter played alone (I-48)"\n'
            '        print(f"  [spend_and_play] {why}")\n'
            '        return True, why\n'
            '    return True, None\n',
            '    return True, None\n')
        _reload_orch()
        _real_sp_ic = ic.select_and_play
        _real_tdl_m4 = ic.tactics_dropped_last_play
        ic.select_and_play = lambda *a, **k: True
        ic.tactics_dropped_last_play = lambda: True
        orch._hand_memory.clear()
        orch._hand_memory[0] = {"power": "7", "secondary": 1, "art": None}
        orch._hand_memory[1] = {"power": None, "secondary": 2, "art": None}
        try:
            ok, why = orch.spend_and_play(0, 1)
            check("mutant 4 caught: why no longer names the drop",
                  ok is True and why is None)
        finally:
            ic.select_and_play = _real_sp_ic
            ic.tactics_dropped_last_play = _real_tdl_m4
            orch._hand_memory.clear()
    finally:
        _restore_orch()

    # --- sanity: spend_and_play reports the drop again after the restore ----
    _real_sp_ic = ic.select_and_play
    _real_tdl_m4 = ic.tactics_dropped_last_play
    ic.select_and_play = lambda *a, **k: True
    ic.tactics_dropped_last_play = lambda: True
    orch._hand_memory.clear()
    orch._hand_memory[0] = {"power": "7", "secondary": 1, "art": None}
    orch._hand_memory[1] = {"power": None, "secondary": 2, "art": None}
    try:
        ok, why = orch.spend_and_play(0, 1)
        check("post-restore sanity: case H passes again",
              ok is True and why is not None and "tactics slot 1" in why)
    finally:
        ic.select_and_play = _real_sp_ic
        ic.tactics_dropped_last_play = _real_tdl_m4
        orch._hand_memory.clear()

    def _case_i_screen():
        return OccludedPlayScreen(cur=2, occluded={1}, drop_moves_from={1: 1},
                                   sabotage_on_probe=2, sabotage_on_nth_select=2)

    def _case_j_screen():
        return OccludedPlayScreen(cur=2, occluded={1}, drop_moves_from={1: 1},
                                   sabotage_on_probe=2, sabotage_on_nth_select=2,
                                   sabotage_permanent=True)

    # --- mutant 5 (I-48b): revert the ordering -------------------------------
    print("mutant 5: the per-target loop processes tactics BEFORE the batter "
          "-- case I must fail (the batter is never even attempted before the "
          "fallback's own guard, which still requires _batter_verified, "
          "refuses outright)")
    try:
        _mutate(IC_PATH,
                "    for target in (card_index, tactics_index):\n",
                "    for target in (tactics_index, card_index):\n")
        _reload_ic()
        s = _case_i_screen()
        ok, out, unwind_calls = _play(2, 0)
        check("mutant 5 caught: case I no longer succeeds as designed",
              not (ok is True and s.confirmed_sel == [2]))
    finally:
        _restore_ic()

    # --- mutant 6 (I-48c, skeptic M1b): the shared re-check reuses a STALE ---
    # belief instead of a fresh read
    print("mutant 6: the shared re-check before commit reuses a stale, "
          "fabricated 'everything is still lifted' belief instead of taking a "
          "fresh look -- case I must commit an unproven selection or refuse "
          "outright, never honestly recover the batter")
    try:
        _mutate(
            IC_PATH,
            "    _g1, _ys1, n1, sel1 = _look_settled(look)\n",
            "    _g1, _ys1, n1, sel1 = _g0, _ys0, MAX_HAND_SIZE, list(want)"
            "  # I-48c mutant: stale belief, no fresh read\n")
        _reload_ic()
        s = _case_i_screen()
        ok, out, unwind_calls = _play(2, 0)
        # The mutant believes `want` (={2}) is already lifted without looking,
        # so `_missing` is always empty and the retry never runs at all --
        # _clear_strays is the only thing left standing between it and a
        # confirm_play with nothing actually lifted, and it refuses. Either
        # way this is NOT the fixed code's honest recovery.
        check("mutant 6 caught: case I no longer honestly recovers the batter",
              "was verified earlier this operation and is no longer lifted"
              not in out or not (ok is True and s.confirmed_sel == [2]))
    finally:
        _restore_ic()

    # --- mutant 7 (I-48c, skeptic M2): the retry is UNBOUNDED, not "once" ---
    print("mutant 7: a missing target's retry loops instead of running once "
          "-- case J (a genuine double failure) must send far more presses "
          "than the shipped single retry, instead of refusing promptly")
    try:
        _mutate(
            IC_PATH,
            "        _rok, _rsel = _walk_cursor_to(_t, look)\n"
            "        if _rok:\n"
            "            _rok, _rsel = _select_verified(_t, look)\n"
            "        if _rok:\n"
            "            _inferred_targets |= getattr(_rsel, \"inferred\", frozenset())\n"
            "        else:\n",
            "        _rok, _rsel = _walk_cursor_to(_t, look)\n"
            "        if _rok:\n"
            "            _rok, _rsel = _select_verified(_t, look)\n"
            "        _i48c_mutant_tries = 0\n"
            "        while not _rok and _i48c_mutant_tries < 50:  # I-48c mutant: unbounded\n"
            "            _i48c_mutant_tries += 1\n"
            "            _rok, _rsel = _walk_cursor_to(_t, look)\n"
            "            if _rok:\n"
            "                _rok, _rsel = _select_verified(_t, look)\n"
            "        if _rok:\n"
            "            _inferred_targets |= getattr(_rsel, \"inferred\", frozenset())\n"
            "        else:\n")
        _reload_ic()
        s = _case_j_screen()
        ok, out, unwind_calls = _play(2, 0)
        check("mutant 7 caught: far more select_card presses than a single "
              "bounded retry sends",
              s.sent.count("select_card") > 20)
    finally:
        _restore_ic()

    # --- mutant 8 (I-48c, skeptic M3): the double-failure unwind passes -----
    # ours=set() instead of the full original target set
    print("mutant 8: the shared re-check's own double-failure unwind passes "
          "ours=set() -- the spy must see it, not the real {0, 2}")
    try:
        _mutate(
            IC_PATH,
            "            print(f\"  [cursor] slot {_t} could not be re-verified "
            "— refusing \"\n"
            "                  \"rather than committing an unproven selection "
            "(I-48b)\")\n"
            "            _unwind_selection(before_all, look, ours=targets, ys0=_ys0)\n",
            "            print(f\"  [cursor] slot {_t} could not be re-verified "
            "— refusing \"\n"
            "                  \"rather than committing an unproven selection "
            "(I-48b)\")\n"
            "            _unwind_selection(before_all, look, ours=set(), ys0=_ys0)"
            "  # I-48c mutant\n")
        _reload_ic()
        s = _case_j_screen()
        ok, out, unwind_calls = _play(2, 0)
        check("mutant 8 caught: the double-failure unwind no longer names the "
              "real target set",
              not any(c == {0, 2} for c in unwind_calls))
    finally:
        _restore_ic()

    # --- mutant 9 (I-48c, skeptic M4): the retry never walks, presses where -
    # the cursor already happens to be
    print("mutant 9: the retry drops _walk_cursor_to and presses select_card "
          "blind wherever the cursor already is -- case I must fail (the "
          "cursor is sitting on the occluded slot, not the batter's)")
    try:
        _mutate(
            IC_PATH,
            "        _rok, _rsel = _walk_cursor_to(_t, look)\n"
            "        if _rok:\n"
            "            _rok, _rsel = _select_verified(_t, look)\n",
            "        _rok, _rsel = _select_verified(_t, look)"
            "  # I-48c mutant: no walk first\n")
        _reload_ic()
        s = _case_i_screen()
        ok, out, unwind_calls = _play(2, 0)
        check("mutant 9 caught: case I refuses instead of recovering",
              not (ok is True and s.confirmed_sel == [2]))
    finally:
        _restore_ic()

    # --- sanity: the I-48b/I-48c fix is still intact after all five new mutants
    s = _case_i_screen()
    ok, out, unwind_calls = _play(2, 0)
    check("post-restore sanity: case I passes again",
          ok is True and s.confirmed_sel == [2]
          and "was verified earlier this operation and is no longer lifted"
          in out)
    s = _case_j_screen()
    ok, out, unwind_calls = _play(2, 0)
    check("post-restore sanity: case J passes again",
          ok is False and s.confirmed_sel is None
          and s.sent.count("select_card") < 20)

    # --- mutant 10 (I-56 P/Q/R): skip the lower ------------------------------
    print("mutant 10: resolve_target_behind_lifted_neighbour never actually "
          "presses t_slot down -- case P must no longer recover the boost")
    try:
        _mutate(
            IC_PATH,
            "    ok, _sel = _deselect_verified(t_slot, look)\n"
            "    if not ok:\n"
            "        return \"unresolved\", None\n"
            "\n"
            "    def _restore_t_slot():\n",
            "    ok, _sel = True, []  # I-56 mutant: skip the lower press\n"
            "\n"
            "    def _restore_t_slot():\n")
        _reload_ic()
        s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4)
        ok, out, unwind_calls = _play(4, 3)
        check("mutant 10 caught: case P no longer recovers the boost",
              not (ok is True and s.confirmed_sel == [3, 4]))
    finally:
        _restore_ic()

    # --- mutant 11 (I-56 P/Q/R): select while still blind --------------------
    print("mutant 11: the manoeuvre presses select_card on the target even "
          "when its position is still unreadable -- case Q must send an "
          "extra, unverified press")
    try:
        _mutate(
            IC_PATH,
            "    if n != MAX_HAND_SIZE or _ys[m_slot] is None or m_slot in sel:\n"
            "        print(f\"  [cursor] slot {m_slot} still blind (or itself lifted) with \"\n",
            "    if False:  # I-56 mutant: never treat m_slot as still blind\n"
            "        print(f\"  [cursor] slot {m_slot} still blind (or itself lifted) with \"\n")
        _reload_ic()
        s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4,
                                          m_slot_chronic=True)
        ok, out, unwind_calls = _play(4, 3)
        check("mutant 11 caught: case Q's press sequence no longer matches "
              "the bounded, look-gated manoeuvre",
              s.sent != ["move_right", "move_right", "move_right", "move_right",
                         "select_card", "move_left", "move_right", "select_card",
                         "select_card", "confirm_play"])
    finally:
        _restore_ic()

    # --- mutant 12 (I-56 P/Q/R): skip the re-raise verify ---------------------
    print("mutant 12: the manoeuvre reports 'resolved' without checking "
          "whether t_slot's re-raise actually landed -- case R must no "
          "longer refuse and unwind cleanly")
    try:
        _mutate(
            IC_PATH,
            "    if not _restore_t_slot():\n"
            "        print(f\"  [cursor] slot {m_slot} selected but slot {t_slot} would not \"\n"
            "              \"re-raise -- refusing and unwinding, nothing half-committed (I-56)\")\n"
            "        _walk_cursor_to(m_slot, look)\n"
            "        _deselect_verified(m_slot, look)\n"
            "        return \"refused\", None\n",
            "    _restore_t_slot()  # I-56 mutant: never checks the outcome\n")
        _reload_ic()
        s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4,
                                          t_slot_never_reraises=True)
        ok, out, unwind_calls = _play(4, 3)
        check("mutant 12 caught: case R no longer refuses and unwinds via the "
              "manoeuvre's own detected failure",
              "refusing and unwinding, nothing half-committed (I-56)" not in out)
    finally:
        _restore_ic()

    # --- sanity: the I-56 fix is still intact after mutants 10-12 -----------
    s = NeighbourOcclusionPlayScreen(cur=0, m_slot=3, t_slot=4)
    ok, out, unwind_calls = _play(4, 3)
    check("post-restore sanity: case P passes again",
          ok is True and s.confirmed_sel == [3, 4])

    def _stray_probe(chronic_blind, m_independently_lifted=False):
        """Minimal rig for resolve_neighbour_occlusion, driving `ic.press`/
        a `look` callable directly -- the coordinator's I-56 part 2 (mark on
        blind / ignore the rise / drop the target mark), mutants 13-15.
        Mirrors test_discard_confirm_verified.py's own NeighbourRig, kept
        local here rather than imported so this file's mutation harness
        stays self-contained."""
        state = {"lifted": {0, 1} if m_independently_lifted else {0}, "cur": 0}

        def _press(key, **kw):
            if key == "move_left":
                state["cur"] = max(0, state["cur"] - 1)
            elif key == "move_right":
                state["cur"] = min(N - 1, state["cur"] + 1)
            elif key == "select_card":
                slot = state["cur"]
                if slot in state["lifted"]:
                    state["lifted"].discard(slot)
                else:
                    state["lifted"].add(slot)

        def _look():
            # Occlusion of slot 1 is governed PURELY by slot 0's own lifted
            # state (matching NeighbourRig's own model in
            # test_discard_confirm_verified.py: `if T_SLOT in self.lifted or
            # not self.m_readable_when_t_down: ys[M_SLOT] = None`) -- NOT by
            # whether slot 1 is itself lifted. `sel` is `sorted(lifted)`,
            # unfiltered, the same convention NeighbourRig uses.
            occluded = chronic_blind or (0 in state["lifted"])
            ys = [200] * N
            if occluded:
                ys[1] = None
            glow = [0.0] * N
            glow[state["cur"]] = 30.0
            sel = sorted(state["lifted"])
            return glow, ys, N, sel

        return _press, _look

    # --- mutant 13 (coordinator I-56 part 2, case T): mark on blind ---------
    print("mutant 13: resolve_neighbour_occlusion no longer clears the mark "
          "on a merely-blind (unproven) verdict -- case T's mark must not "
          "survive, and this mutant makes it survive again")
    try:
        _mutate(IC_PATH, "        _MAYBE_LIFTED.discard(m_slot)\n",
                "        pass  # I-56 mutant: mark on blind (never cleared)\n")
        _reload_ic()
        ic.clear_maybe_lifted()
        ic._mark_maybe_lifted({1})
        press, look = _stray_probe(chronic_blind=True)
        real_press = ic.press
        ic.press = press
        try:
            ic.resolve_neighbour_occlusion(1, 0, look)
        finally:
            ic.press = real_press
        check("mutant 13 caught: the mark survives when I-56 says it must not",
              1 in ic._MAYBE_LIFTED)
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()

    # --- mutant 14 (coordinator I-56 part 2, case U): ignore the rise -------
    print("mutant 14: resolve_neighbour_occlusion no longer distinguishes a "
          "POSITIVELY RISEN stray from mere blindness -- a genuine, "
          "independently lifted stray must still refuse with its mark intact")
    try:
        _mutate(IC_PATH, "    if m_slot in sel:\n",
                "    if False:  # I-56 mutant: ignore the rise\n")
        _reload_ic()
        ic.clear_maybe_lifted()
        ic._mark_maybe_lifted({1})
        press, look = _stray_probe(chronic_blind=False, m_independently_lifted=True)
        real_press = ic.press
        ic.press = press
        try:
            ok_u, detail_u = ic.resolve_neighbour_occlusion(1, 0, look)
        finally:
            ic.press = real_press
        check("mutant 14 caught: a genuine, independently lifted stray is no "
              "longer refused with its mark kept",
              not (ok_u is False and 1 in ic._MAYBE_LIFTED))
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()

    # --- mutant 15 (coordinator I-56 part 2, case V): drop the target mark --
    print("mutant 15: _clear_strays no longer marks a PRESSED TARGET whose "
          "own verify stayed blind -- I-43's legitimate case must survive "
          "the I-56 fix untouched")
    try:
        _mutate(IC_PATH, "        _mark_maybe_lifted(set(want) - lifted)\n",
                "        pass  # I-56 mutant: target mark dropped\n")
        _reload_ic()
        ic.clear_maybe_lifted()

        def _look_v_mut():
            return [0.0] * N, [None] + [200] * (N - 1), N, []

        ic._clear_strays({0}, _look_v_mut, blind_before=set())
        check("mutant 15 caught: the pressed target's own blind verify is no "
              "longer marked (I-43's legitimate case)",
              0 not in ic._MAYBE_LIFTED)
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()

    # --- sanity: T/U/V all still hold after mutants 13-15 --------------------
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({1})
    press, look = _stray_probe(chronic_blind=True)
    real_press = ic.press
    ic.press = press
    try:
        ok_t, _ = ic.resolve_neighbour_occlusion(1, 0, look)
    finally:
        ic.press = real_press
    check("post-restore sanity: case T passes again",
          ok_t is False and 1 not in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    # --- mutant 16 (I-56 redo, R2/R3): press even when the OPERATION's own
    # baseline was also blind -- case Q2 must send a press it has no right to
    print("mutant 16: _select_verified's baseline-trust guard is forced True "
          "unconditionally -- case Q2 (baseline ALSO blind) must send a "
          "press it has no right to")
    try:
        _mutate(
            IC_PATH,
            "        if (ys0 is not None and target < len(ys0) and ys0[target] is not None\n"
            "                and _baseline_untouched(target)):\n",
            "        if True:  # I-56 mutant: baseline blindness ignored\n")
        _reload_ic()
        _ic_reset_ledger_16 = getattr(ic, "_reset_press_ledger", None)
        if _ic_reset_ledger_16:
            _ic_reset_ledger_16()
        _ys0_q2 = list(REST)
        _ys0_q2[3] = None
        _s16 = BaselineSelectScreen(target=3, chronic_blind=True)
        real_press = ic.press
        ic.press = _s16.press
        try:
            ok16, _sel16 = ic._select_verified(3, _s16.look, ys0=_ys0_q2, sel0=set())
        finally:
            ic.press = real_press
        check("mutant 16 caught: case Q2 sent a press it has no right to",
              _s16.sent != [])
    finally:
        _restore_ic()

    # --- mutant 17 (I-56 redo, R2 -- "the ledger ignored"): drop the
    # _baseline_untouched clause so a slot this operation already touched
    # (accounted or not) still earns the baseline-trust press
    print("mutant 17: _select_verified's baseline-trust guard drops the "
          "_baseline_untouched(target) check -- the probe-raised-then-blind "
          "shape (X1) must press when the ledger says it must not")
    try:
        _mutate(
            IC_PATH,
            "        if (ys0 is not None and target < len(ys0) and ys0[target] is not None\n"
            "                and _baseline_untouched(target)):\n",
            "        if (ys0 is not None and target < len(ys0) and ys0[target] is not None):"
            "  # I-56 mutant: ledger ignored\n")
        _reload_ic()
        ic._reset_press_ledger()
        ic._note_accounted_press(4)   # the I-02 probe's own confirmed touch
        _s17 = BaselineSelectScreen(target=4, chronic_blind=True)
        real_press = ic.press
        ic.press = _s17.press
        try:
            ok17, _sel17 = ic._select_verified(4, _s17.look, ys0=list(REST), sel0=set())
        finally:
            ic.press = real_press
        check("mutant 17 caught: a press landed on a slot the ledger says "
              "was already touched this operation", _s17.sent != [])
    finally:
        _restore_ic()

    # --- mutant 18 (I-56 part 3, case R2): press a second time when already up
    print("mutant 18: the already-selected-at-baseline branch falls through "
          "to a press instead of returning -- case R2 must toggle an "
          "already-up card back DOWN")
    try:
        _mutate(
            IC_PATH,
            "            _sel = _InferredSel(before)\n"
            "            _sel.inferred = frozenset({target})\n"
            "            return True, _sel\n"
            "        if (ys0 is not None and target < len(ys0) and ys0[target] is not None\n"
            "                and _baseline_untouched(target)):\n",
            "            _sel = _InferredSel(before)\n"
            "            _sel.inferred = frozenset({target})\n"
            "            # I-56 mutant: no return -- falls through to a press\n"
            "        if (ys0 is not None and target < len(ys0) and ys0[target] is not None\n"
            "                and _baseline_untouched(target)):\n")
        _reload_ic()
        ic._reset_press_ledger()
        _s18 = BaselineSelectScreen(target=3, chronic_blind=True)
        real_press = ic.press
        ic.press = _s18.press
        try:
            ok18, _sel18 = ic._select_verified(3, _s18.look, ys0=list(REST), sel0={3})
        finally:
            ic.press = real_press
        check("mutant 18 caught: case R2 sent a press on an already-selected "
              "card", _s18.sent != [])
    finally:
        _restore_ic()

    # --- mutant 19 (I-56 redo, R1): delete the narrowed _clear_strays mark
    # -- OP1/OP2 (the skeptic's stray shape) must go from refuse to WRONGLY
    # COMMIT once the mark cannot land
    print("mutant 19: _clear_strays' ledger-gated mark is deleted -- the "
          "skeptic's OP1/OP2 stray shape must go from a refusal to a wrong "
          "COMMIT of a card the engine never chose")
    try:
        _mutate(
            IC_PATH,
            "                  f\"would go in with the commit if we proceeded{_explain}.\")\n"
            "            if _UNACCOUNTED_SELECT_PRESS:\n"
            "                _mark_maybe_lifted(_new_blind)\n"
            "            invalidate_cursor()\n"
            "            return False\n"
            "    _untouched_blind = _blind_now - set(want)\n",
            "                  f\"would go in with the commit if we proceeded{_explain}.\")\n"
            "            pass  # I-56 mutant: the narrowed mark is deleted\n"
            "            invalidate_cursor()\n"
            "            return False\n"
            "    _untouched_blind = _blind_now - set(want)\n")
        _reload_ic()

        def _look_op_mut(blind_slot=2, extra_sel=(0,)):
            def _look():
                ys = list(REST)
                ys[blind_slot] = None
                return [0.0] * N, ys, N, sorted(extra_sel)
            return _look

        ic.clear_maybe_lifted()
        ic._reset_press_ledger()
        ic._note_unaccounted_press()
        ic._clear_strays({0}, _look_op_mut(), blind_before=set())
        ic._reset_press_ledger()
        ok19 = ic._clear_strays({0}, _look_op_mut(), blind_before={2})
        check("mutant 19 caught: OP2 commits a card the engine never chose "
              "once the mark cannot land", ok19 is True)
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()
        ic.clear_maybe_lifted()

    # --- mutant 20 (I-48f, skeptic live 2026-09-22): a blind row is read as
    # "not lifted" again -- case (Z1) must go back to sending the re-check's
    # extra walk+select on an already-inference-selected target
    print("mutant 20: the shared re-check's `_missing` computation goes back "
          "to `want - set(sel1)`, with no inference exemption -- case (Z1) "
          "must send extra presses re-selecting targets that were never "
          "actually missing")
    try:
        _mutate(
            IC_PATH,
            "        if n1 == MAX_HAND_SIZE:\n"
            "            # I-48f (skeptic): a target this operation selected by INFERENCE\n"
            "            # (I-21 -- selecting a card blinds its OWN disc the instant it\n"
            "            # lifts) can NEVER show up in `sel1`; that is the inference's\n"
            "            # whole premise, not a defect in this look. So \"not in sel1\" is\n"
            "            # not evidence a target came back down -- it is the expected,\n"
            "            # permanent shape of a lifted-and-blind card. Only a target\n"
            "            # whose disc is READABLE now and still absent from sel1 has\n"
            "            # genuinely toggled back down; a target still blind is\n"
            "            # consistent with staying exactly where the inference put it,\n"
            "            # and re-selecting it is a blind TOGGLE that would put it back\n"
            "            # down. `_inferred_targets` is the same real report\n"
            "            # `_select_verified` already returns (I-44), not a re-derivation.\n"
            "            _missing = {t for t in want\n"
            "                        if t not in sel1\n"
            "                        and not (t in _inferred_targets\n"
            "                                 and (t >= len(_ys1) or _ys1[t] is None))}\n"
            "        else:\n"
            "            _missing = set()\n",
            "        if n1 == MAX_HAND_SIZE:\n"
            "            _missing = want - set(sel1)  # I-56 mutant: inference exemption dropped\n"
            "        else:\n"
            "            _missing = set()\n")
        _reload_ic()
        s = InferredSelectPlayScreen(cur=0)
        ok20, out20, calls20 = _play(0, 1)
        check("mutant 20 caught: the re-check sends extra presses (or "
              "refuses outright) once the inference exemption is gone",
              s.sent != ["select_card", "move_right", "select_card", "confirm_play"]
              or ok20 is not True)
    finally:
        _restore_ic()

    # --- sanity: (Z1) still holds after mutant 20 ----------------------------
    s = InferredSelectPlayScreen(cur=0)
    ok_z1b, _out_z1b, _calls_z1b = _play(0, 1)
    check("post-restore sanity: case (Z1) passes again",
          ok_z1b is True and s.confirmed_sel == [0, 1])

    # --- mutant 21 (I-56 skeptic round 2, MY-M1): the LIVE ENTRY POINT's own
    # ledger reset is deleted -- (AA1) must go from "clean and unmarked" to
    # "a prior operation's leftover state marks a slot this operation never
    # touched"
    print("mutant 21: _verified_select_and_play_inner's own "
          "_reset_press_ledger() call is deleted -- (AA1) must let a "
          "poisoned, left-over ledger from a prior operation mark a slot "
          "this operation never pressed near")
    try:
        _mutate(
            IC_PATH,
            "    # I-56 skeptic R1/R4: a fresh per-operation press ledger -- nothing this\n"
            "    # operation has pressed yet, so no slot's baseline can already be stale.\n"
            "    _reset_press_ledger()\n",
            "    # I-56 mutant (MY-M1): the reset never runs\n")
        _reload_ic()
        ic.clear_maybe_lifted()
        ic._note_unaccounted_press()
        for _slot in range(N):
            ic._note_accounted_press(_slot)
        s = NewBlindNonWantPlayScreen(cur=0, blind_from_call=2)
        ok21, out21, calls21 = _play(0, None)
        check("mutant 21 caught: slot 2 is marked once the entry point's own "
              "reset stops running", 2 in ic._MAYBE_LIFTED)
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()

    # --- sanity: (AA1) still holds after mutant 21 ----------------------------
    ic.clear_maybe_lifted()
    ic._note_unaccounted_press()
    for _slot in range(N):
        ic._note_accounted_press(_slot)
    s = NewBlindNonWantPlayScreen(cur=0, blind_from_call=2)
    ok_aa1b, _out_aa1b, _calls_aa1b = _play(0, None)
    check("post-restore sanity: case (AA1) passes again",
          2 not in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()

    # --- mutant 22 (I-56 skeptic round 2, MY-M3): resolve_neighbour_
    # occlusion's "still blind" branch is restored to the OLD, pre-I-56
    # behaviour -- mere blindness is unconditionally treated as a genuine,
    # positively-evidenced stray again (marked, t_slot left down), the exact
    # rule whose docstring names 14 firings and 0 true positives on
    # `run_live_20260921x.log` ~655-680. The live Q17 frame
    # (`run_live_20260921x.log` 651-672, user ground truth slot 0) reaches
    # this SAME branch -- slot 1 is adjacent to slot 0 once slot 0 is
    # selected, and slot 1's wreath never reads -- so it must go from a
    # clean commit to a refusal. TWO edits: `_clear_strays`' own
    # `_untouched_blind & _MAYBE_LIFTED` intersection is ALSO what decides
    # whether the disambiguation is even TRIED on a mark this operation
    # never carried in -- without also dropping it, resolve_neighbour_
    # occlusion is never called at all for a fresh, unmarked chronic slot,
    # and mutating it alone measures nothing (verified: `ok` stays True).
    print("mutant 22: BOTH `_clear_strays`' ledger-gated intersection AND "
          "resolve_neighbour_occlusion's 'still blind' branch are restored "
          "to unconditional marking -- the live Q17 frame must go from a "
          "clean commit to a refusal")
    try:
        _mutate(
            IC_PATH,
            "    _untouched_blind = _blind_now - set(want)\n"
            "    if _untouched_blind:\n"
            "        # I-43: a slot this operation cannot have raised (it was ALREADY blind\n"
            "        # before anything was pressed) is not automatically safe to wave\n"
            "        # through -- if an EARLIER refused attempt could not prove it clean,\n"
            "        # `blind_before` alone (which only asks \"was it blind before THIS\n"
            "        # call\") cannot tell that apart from a genuinely chronic occlusion.\n"
            "        # See _MAYBE_LIFTED and this function's own docstring.\n"
            "        _unproven = _untouched_blind & _MAYBE_LIFTED\n",
            "    _untouched_blind = _blind_now - set(want)\n"
            "    if _untouched_blind:\n"
            "        # I-56 mutant: unconditional (MY-M3, part 1 of 2)\n"
            "        _unproven = _untouched_blind\n")
        _mutate(
            IC_PATH,
            "    if _ys[m_slot] is None:\n"
            "        # STILL BLIND IS *NOT* THE SAME EVIDENCE (I-56). The branch above\n"
            "        # requires a POSITIVE rise; this one used to treat mere blindness as\n"
            "        # proof of the same thing, and blindness carries no such proof --\n"
            "        # occlusion by a DIFFERENT card, or a chronic wreath misread on a\n"
            "        # resting tactics card (I-36), read identically to a real lift. Live:\n"
            "        # `run_live_20260921x.log` ~655-680 -- a resting FIELDING PLAY card\n"
            "        # next to a selected pitcher card would not read no matter what, was\n"
            "        # scored \"genuine stray, marked\" by the old rule, refused 3 straight\n"
            "        # commits (I-43 firings that day: 14, true positives: 0), and\n"
            "        # excluded the engine's own chosen card. Restore t_slot -- the\n"
            "        # caller may still need it committed -- and report UNRESOLVED, not a\n"
            "        # stray. And CLEAR any existing mark on m_slot: the one thing that\n"
            "        # could have put it there is this exact blind-means-lifted\n"
            "        # assumption, which this branch has just shown false.\n"
            "        ok, _sel = _walk_cursor_to(t_slot, look)\n"
            "        if ok:\n"
            "            ok, _sel = _select_verified(t_slot, look)\n"
            "        _MAYBE_LIFTED.discard(m_slot)\n"
            "        if not ok:\n"
            "            return False, (f\"slot {m_slot} still blind with slot {t_slot} down -- \"\n"
            "                            f\"not proof of a lift, AND {t_slot} would not \"\n"
            "                            \"re-raise -- refusing\")\n"
            "        return False, (f\"slot {m_slot} still blind with slot {t_slot} down -- \"\n"
            "                        \"not proof of a lift (I-56); restored, unresolved\")\n",
            "    if _ys[m_slot] is None:\n"
            "        # I-56 mutant (MY-M3): mere blindness is treated as a genuine,\n"
            "        # positively-evidenced stray again -- marked, t_slot left down.\n"
            "        _mark_maybe_lifted({m_slot})\n"
            "        return False, (f\"slot {m_slot} still blind with slot \"\n"
            "                        f\"{t_slot} down -- genuine stray, marked (I-56 mutant)\")\n")
        _reload_ic()
        ic.clear_maybe_lifted()
        ic._reset_press_ledger()
        s = Q17FrameScreen()
        ok22, out22, calls22 = _play(0, None)
        check("mutant 22 caught: the live Q17 frame no longer commits once "
              "mere blindness is unconditionally treated as a stray again",
              ok22 is not True)
    finally:
        _restore_ic()

    # --- sanity: Q17 still commits after mutant 22 ----------------------------
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    s = Q17FrameScreen()
    ok_bb1b, _out_bb1b, _calls_bb1b = _play(0, None)
    check("post-restore sanity: the Q17 case commits again",
          ok_bb1b is True and s.confirmed_sel == [0])

    # =====================================================================
    print("(DD1)/(DD2) I-56 SKEPTIC ROUND 3: `_new_blind` has THREE marking "
          "sites, not two. (BB1)/mutant 22 above only exercises the "
          "RE-LOOK path (the re-look SUCCEEDS at reading the fan and the "
          "slot is still blind) -- this is the sibling CANNOT-READ-FAN "
          "path, where the re-look itself fails to read the fan at all "
          "('cannot read the fan on the re-look'). Same ledger gate, "
          "different branch, never exercised until now.")
    # =====================================================================
    def _look_deadfan(new_blind_slot=2, want_slot=0):
        # Call 1 (this function's own top-of-function look): the fan reads
        # fine, but `new_blind_slot` is unexpectedly blind -- a slot outside
        # `want`/`blind_before`. Every call after that (the re-look's own
        # LOOK_RETRIES attempts inside _look_settled) finds the fan
        # completely unreadable, which is the branch under test.
        state = {"cur": want_slot, "calls": 0}

        def _look():
            state["calls"] += 1
            if state["calls"] == 1:
                ys = list(REST)
                ys[new_blind_slot] = None
                glow = [0.0] * N
                glow[state["cur"]] = 30.0
                return glow, ys, N, []
            return [0.0] * N, [None] * N, 0, []

        return _look

    print("(DD1) an UNACCOUNTED press this operation sent marks the slot "
          "when the re-look cannot read the fan at all")
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    ic._note_unaccounted_press()
    ok_dd1 = ic._clear_strays({0}, _look_deadfan(), blind_before=set())
    check("(DD1) refuses (the re-look never recovered a readable fan)",
          ok_dd1 is False)
    check("(DD1) marks slot 2 -- an unaccounted press could explain it",
          2 in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    print("(DD2) the mirror: a CLEAN ledger still refuses but does NOT "
          "mark -- the fan going unreadable on its own, with nothing this "
          "operation pressed unaccounted for, is not proof of a lift")
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    ok_dd2 = ic._clear_strays({0}, _look_deadfan(), blind_before=set())
    check("(DD2) refuses this attempt (still cautious)", ok_dd2 is False)
    check("(DD2) but does NOT mark -- nothing this operation pressed (that "
          "went unaccounted) could explain it", 2 not in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    # --- mutant 23 (I-56 skeptic round 3, M3d): the cannot-read-fan branch's
    # own mark loses its ledger gate -- (DD2) must go from unmarked to marked
    print("mutant 23: the CANNOT-READ-FAN branch's own "
          "`if _UNACCOUNTED_SELECT_PRESS: _mark_maybe_lifted(_new_blind)` "
          "loses its gate -- (DD2), a clean-ledger refusal, must start "
          "marking a slot nothing this operation pressed can explain")
    try:
        _mutate(
            IC_PATH,
            "            # _note_unaccounted_press's callers).\n"
            "            if _UNACCOUNTED_SELECT_PRESS:\n"
            "                _mark_maybe_lifted(_new_blind)\n",
            "            # _note_unaccounted_press's callers).\n"
            "            _mark_maybe_lifted(_new_blind)"
            "  # I-56 mutant: cannot-read-fan mark unconditional\n")
        _reload_ic()
        ic.clear_maybe_lifted()
        ic._reset_press_ledger()
        ok23 = ic._clear_strays({0}, _look_deadfan(), blind_before=set())
        check("mutant 23 caught: (DD2)'s clean ledger no longer stops the "
              "cannot-read-fan branch from marking",
              2 in ic._MAYBE_LIFTED)
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()

    # --- sanity: (DD1)/(DD2) still hold after mutant 23 ----------------------
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    ok_dd2b = ic._clear_strays({0}, _look_deadfan(), blind_before=set())
    check("post-restore sanity: (DD2) passes again",
          ok_dd2b is False and 2 not in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    # =====================================================================
    print("(EE1)/(EE2) I-56 SKEPTIC ROUND 3, MY-M3: a THIRD marking site, "
          "distinct from both `_new_blind` branches above -- "
          "`_clear_strays`' own after-clearing refusal ('after clearing, "
          "the lifted set is still ... refusing to commit'), reached "
          "through the `extra` walk-and-put-down loop rather than "
          "`_new_blind`. A genuine stray (not the engine's target) is "
          "lifted before this operation starts; `_walk_cursor_to` reaches "
          "it, but by the time `_deselect_verified` takes its own look the "
          "stray's disc has already gone unreadable ON ITS OWN (a chronic "
          "wreath misread, I-36, arriving the instant we turn to look at "
          "it) -- so `target not in sel` is already true and "
          "`_deselect_verified` returns True WITHOUT EVER PRESSING "
          "select_card. That is what makes this site's ledger state "
          "genuinely free to set: unlike a real deselect (which "
          "`_deselect_verified`'s own docstring says ALWAYS marks the "
          "ledger unaccounted, even on success), nothing here presses "
          "select_card at all -- confirmed by mutant-free replay, zero "
          "select presses sent either way.")
    # =====================================================================
    def _stray_vanish_rig(stray=2, want_slot=0):
        # Call 1 (this function's own top-of-function look): the stray is
        # genuinely lifted, so `extra` is non-empty and the clearing loop
        # runs. Every call after that -- inside `_walk_cursor_to`'s own
        # navigation looks and `_deselect_verified`'s check -- finds the
        # stray's disc unreadable and absent from `sel`, so `_deselect_
        # verified` never actually presses select_card at all (its own
        # `target not in sel` short-circuit fires first); the post-clear
        # re-look (also a later call) sees the same thing. `press` still
        # has to move the cursor -- `_walk_cursor_to` needs to land on the
        # stray -- so this is a real press/look pair, not a no-op stub.
        state = {"cur": want_slot, "calls": 0, "sent": []}

        def _press(key, **kw):
            state["sent"].append(key)
            if key == "move_left":
                state["cur"] = max(0, state["cur"] - 1)
            elif key == "move_right":
                state["cur"] = min(N - 1, state["cur"] + 1)

        def _look():
            state["calls"] += 1
            ys = list(REST)
            glow = [0.0] * N
            glow[state["cur"]] = 30.0
            if state["calls"] == 1:
                return glow, ys, N, [stray]
            ys[stray] = None
            return glow, ys, N, []

        return _press, _look, state

    print("(EE1) an UNACCOUNTED press this operation sent (from elsewhere "
          "in the operation, not from clearing this stray -- nothing here "
          "ever presses select_card) marks the slot when the post-clear "
          "read still shows it blind")
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    ic._note_unaccounted_press()
    _press_ee1, _look_ee1, _state_ee1 = _stray_vanish_rig()
    real_press = ic.press
    ic.press = _press_ee1
    try:
        ok_ee1 = ic._clear_strays({0}, _look_ee1, blind_before=set())
    finally:
        ic.press = real_press
    check("(EE1) refuses (the stray is neither selected nor readable after "
          "the clearing walk)", ok_ee1 is False)
    check("(EE1) marks slot 2 -- an unaccounted press could explain it",
          2 in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    print("(EE2) the mirror: a CLEAN ledger still refuses but does NOT "
          "mark -- the stray was never actually pressed (it read down on "
          "its own before `_deselect_verified` ever reached it), so "
          "nothing this operation did explains its blindness")
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    _press_ee2, _look_ee2, _state_ee2 = _stray_vanish_rig()
    ic.press = _press_ee2
    try:
        ok_ee2 = ic._clear_strays({0}, _look_ee2, blind_before=set())
    finally:
        ic.press = real_press
    check("(EE2) refuses this attempt (still cautious)", ok_ee2 is False)
    check("(EE2) but does NOT mark -- nothing this operation pressed (that "
          "went unaccounted) could explain it", 2 not in ic._MAYBE_LIFTED)
    check("(EE2) confirms the mechanism: select_card was never pressed at "
          "all -- the stray read down on its own, never toggled",
          "select_card" not in _state_ee2["sent"])
    ic.clear_maybe_lifted()

    # --- mutant 24 (I-56 skeptic round 3, MY-M3): the after-clearing
    # refusal's own mark loses its ledger gate -- (EE2) must go from
    # unmarked to marked
    print("mutant 24: `_clear_strays`' own after-clearing "
          "`_mark_candidates` computation loses its "
          "`if _UNACCOUNTED_SELECT_PRESS:` gate on `_blind_now - want` -- "
          "(EE2), a clean-ledger refusal, must start marking a slot "
          "nothing this operation pressed can explain")
    try:
        _mutate(
            IC_PATH,
            "            _mark_candidates = lifted - want\n"
            "            if _UNACCOUNTED_SELECT_PRESS:\n"
            "                _mark_candidates = _mark_candidates | (_blind_now - set(want))\n"
            "            _mark_maybe_lifted(_mark_candidates)\n",
            "            _mark_candidates = (lifted - want) | (_blind_now - set(want))"
            "  # I-56 mutant: after-clearing mark unconditional\n"
            "            _mark_maybe_lifted(_mark_candidates)\n")
        _reload_ic()
        ic.clear_maybe_lifted()
        ic._reset_press_ledger()
        _press_m24, _look_m24, _state_m24 = _stray_vanish_rig()
        real_press = ic.press
        ic.press = _press_m24
        try:
            ok24 = ic._clear_strays({0}, _look_m24, blind_before=set())
        finally:
            ic.press = real_press
        check("mutant 24 caught: (EE2)'s clean ledger no longer stops the "
              "after-clearing branch from marking",
              2 in ic._MAYBE_LIFTED)
        ic.clear_maybe_lifted()
    finally:
        _restore_ic()

    # --- sanity: (EE1)/(EE2) still hold after mutant 24 -----------------------
    ic.clear_maybe_lifted()
    ic._reset_press_ledger()
    _press_ee2b, _look_ee2b, _state_ee2b = _stray_vanish_rig()
    ic.press = _press_ee2b
    try:
        ok_ee2b = ic._clear_strays({0}, _look_ee2b, blind_before=set())
    finally:
        ic.press = real_press
    check("post-restore sanity: (EE2) passes again",
          ok_ee2b is False and 2 not in ic._MAYBE_LIFTED)
    ic.clear_maybe_lifted()

    # --- sanity: P2/Q2/R2 all still hold after mutants 16-18 ----------------
    ic._reset_press_ledger()
    _s_p2 = BaselineSelectScreen(target=3, chronic_blind=False)
    real_press = ic.press
    ic.press = _s_p2.press
    try:
        ok_p2, _ = ic._select_verified(3, _s_p2.look, ys0=list(REST), sel0=set())
    finally:
        ic.press = real_press
    check("post-restore sanity: case P2 passes again",
          ok_p2 is True and _s_p2.sent == ["select_card"])

finally:
    pass

print()
if fails:
    print(f"{len(fails)} FAILED")
    _sys.exit(1)
print("all checks passed")
