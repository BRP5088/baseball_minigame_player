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

finally:
    pass

print()
if fails:
    print(f"{len(fails)} FAILED")
    _sys.exit(1)
print("all checks passed")
