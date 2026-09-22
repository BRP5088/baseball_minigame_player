"""I-51: the blind-target probe gives up after 2 presses; two clustered drops
refuse a play on a healthy cursor.

Evidence: `agent_progress/census/blind_cursor_m4/progress.md` (cycle7 match4,
refused_select_1790026023456048000). `_probe_select_blind_target`
(input_controller.py, ~:910) is gated on `PROBE_SELECT_MAX` -- was a literal 2, one
retry. The kept post-refusal frame shows the cursor sitting correctly on the target
(slot 3, glow 26.9 -- comfortably inside cursor_slot's own measured true band 20.7
.. 36.1) with nothing selected: two consecutively DROPPED select_card presses on a
fine cursor, not a reader defect. CLAUDE.md section 5 measured the console ignoring
15.20% of presses, CLUSTERED (P(ignore | previous ignored) = 0.250) -- exactly the
reasoning that already raised PRESS_VERIFY_TRIES from 3 to 5 (0.95% -> 0.059% tail).
Two tries leaves ~3.8%; the user's bar is zero stalls.

THE FIX. (1) PROBE_SELECT_MAX now ALIASES PRESS_VERIFY_TRIES (input_controller.py,
defined right after it) instead of its own separately-derived 2 -- both bound
retrying select_card against the SAME measured, clustered press-drop rate, so they
cannot drift apart. The probe's existing safety is untouched: it still stops the
INSTANT `selected_cards` shows the target risen, so an extra press after a landed
one is impossible by construction (every iteration looks BEFORE it decides whether
to press again -- see `_probe_select_blind_target`'s own docstring). (2)
`orchestrator.record_refused_select` grew an optional `extra` dict argument
(defaults to None, so every existing caller/test is unchanged) that gets merged
into why.json -- letting a refusal's own record show input_controller.
_LAST_PROBE_ATTEMPTS, the probe's per-attempt glow/ys/selected reads, not just the
single frame grabbed after the fact.

WHAT THIS FILE PINS, driving `_probe_select_blind_target` directly (not through
`_walk_cursor_to`, which `tests/rig/test_blind_slot_probe_select.py` already covers
end to end -- this file is scoped to the budget change and the attempt log):

  (A) four clustered drops then a landed 5th press -> success, EXACTLY
      PRESS_VERIFY_TRIES presses sent, not fewer or more;
  (B) the very first press lands -> success, EXACTLY ONE press sent -- no press is
      ever sent after a look has already shown the target risen;
  (C) all PRESS_VERIFY_TRIES presses are dropped -> refusal, and
      input_controller._LAST_PROBE_ATTEMPTS carries one record per attempt (glow,
      ys, selected), which `orchestrator.record_refused_select`'s new `extra`
      argument persists into why.json;
  (D) a rise at the WRONG slot after two dropped presses is untouched: the existing
      untoggle-and-continue behaviour still fires, at the SAME press it always did.

FakeScreen (A-D) models a "dropped" press as `None` in `select_queue` (no effect at
all, not a toggle) -- simple and sufficient for A-D, which never put the true
cursor on an already-selected slot.

INDEPENDENT SKEPTIC ROUND, REFUTED (agent_progress/issues/I-51/skeptic.md):
`select_card` is a TOGGLE and does NOT move the cursor, so when the TRUE cursor
sits on an ALREADY-SELECTED slot (I-48b: the batter selected first, then dropped
navigation presses toward the tactics target left the true cursor sitting on the
batter still), the `select_queue=[None|slot]` model above CANNOT represent what
happens -- every probe press toggles the batter, and the original code (A-D's
own code) only ever checked for a RISE, never a DISAPPEARANCE. Raising the budget
2 -> 5 changed the TOGGLE PARITY of an unrelated press storm without the probe
ever noticing: P(the already-selected batter left DOWN) measured **0.229 at
budget 2, 0.707 at budget 3, 0.621 at budget 5** -- non-monotonic in the budget,
so it was never a knob to nudge, and end to end
(`_verified_select_and_play_inner`) budget 5 turned a COMMITTED batter-alone play
(budget 2) into a FULL STALL, in a scenario I-48b traced live.

THE B1 FIX mirrors the rise branch with a disappearance branch: `gone = [i for i
in before if i not in sel]`; if `gone`, the true cursor is (or was) on `gone[0]`,
and it is put back UP via `_select_verified` (not `_deselect_verified` -- the goal
is to RESTORE a selection the probe's own press just knocked down, not remove a
stray one) before returning, with no further select_card press. `ToggleFakeScreen`
below models a REAL toggle at a fixed cursor slot, which the None/slot model
cannot -- this is why A-D and E-F use two different fakes, not one:

  (E) the true cursor sits on an ALREADY-SELECTED slot, all PRESS_VERIFY_TRIES
      presses land -> the slot is re-lifted, the probe returns True naming it,
      the batter is never left down;
  (F) same, but presses 1 and 3 are dropped (an ODD number of LANDED presses,
      which the pre-fix toggle-only view could not survive) -> the same outcome;
  (G) end to end through the REAL `_verified_select_and_play_inner` (I-48b's own
      shape): card_index=2 already selected and verified, the walk toward
      tactics_index=0 loses the cursor one step away and probes -- every press
      lands on the ALREADY-SELECTED batter (slot 2) -- and the play COMMITS with
      confirm_play sent exactly once, at BOTH budget 2 and budget 5 (was a full
      stall at 5 before the fix).

THE B2 FIX: `orchestrator.play_one_turn`'s own `record_refused_select` call
(orchestrator.py ~:8472, the ONE production call site) now passes
`extra={"probe_attempts": input_controller._LAST_PROBE_ATTEMPTS}`, module-qualified
because the probe REBINDS that name every call so a `from ... import` copy would
go stale:

  (H) driving the REAL `play_one_turn` with `select_and_play` stubbed to refuse,
      `_LAST_PROBE_ATTEMPTS` seeded to a known sentinel -- the why.json the real
      call site writes carries that sentinel under "probe_attempts".

ROUND-2 SKEPTIC N-2 (the ORDER of the row-count guard and the B1 `gone` check):
`_look_settled` has its own bad-read sentinel -- n=0, `sel` EMPTIED -- for a frame
none of its `LOOK_RETRIES` attempts could read. With an already-selected slot in
`before` (I-48b's batter), a `gone` computed against that emptied `sel` would name
it, exactly as a real disappearance would -- so the row-count guard MUST run first
and return before `gone` is ever computed.

  (I) a GarbledScreen whose every look() is unreadable -> refuses, and
      `_select_verified` is never called on the previously-selected slot. Mutant 8
      moves the `gone` computation above the row-count guard -- case I must then
      catch `_select_verified` firing on a frame nobody could read.
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

import hashlib                                                       # noqa: E402
import importlib                                                     # noqa: E402
import json                                                           # noqa: E402
import tempfile                                                       # noqa: E402

import input_controller as ic                                        # noqa: E402
import orchestrator as orch                                          # noqa: E402
from PIL import Image                                                 # noqa: E402

fails = []


def check(name, cond):
    if not cond:
        fails.append(name)


N = ic.MAX_HAND_SIZE
REST = [200, 160, 150, 165, 220]


class ProbeFakeScreen:
    """Drives `_probe_select_blind_target` directly. `select_queue[i]` is which
    slot the (i+1)-th select_card press actually lifts (or puts back down, if
    already up) -- `None` means that press is DROPPED, exactly like a swallowed
    console press: no effect, nothing observable changes. An exhausted queue also
    drops every further press. `ys` defaults to fully readable (no row is a
    fallback-y row), since that refusal path is `tests/rig/
    test_blind_slot_probe_select.py` case (d)'s job, not this file's."""

    def __init__(self, select_queue, ys=None):
        self.select_queue = list(select_queue)
        self.ys = ys if ys is not None else [100] * N
        self.y = list(REST)
        self.sent = []

    def selected(self):
        return [i for i, y in enumerate(self.y) if REST[i] - y >= 25]

    def look(self):
        return [0.2] * N, list(self.ys), N, self.selected()

    def press(self, key):
        self.sent.append(key)
        if key != "select_card" or not self.select_queue:
            return
        t = self.select_queue.pop(0)
        if t is None:
            return                      # dropped: nothing lifts
        if REST[t] - self.y[t] >= 25:
            self.y[t] = REST[t]         # already up -> DOWN
        else:
            self.y[t] -= 44             # a selected card RISES


class ToggleFakeScreen:
    """A REAL toggle at a FIXED cursor slot -- select_card never moves the
    cursor, so every landed press toggles `cursor`'s own selection state,
    exactly the I-48b mechanism (I-51 skeptic B1). `drops[i]` is whether the
    (i+1)-th select_card press is swallowed (no effect at all, nothing
    toggles). `ys` defaults to fully readable."""

    def __init__(self, cursor, selected, drops, ys=None):
        self.cursor = cursor
        self.sel = set(selected)
        self.drops = list(drops)
        self.ys = ys if ys is not None else [100] * N
        self.sent = []

    def look(self):
        return [0.2] * N, list(self.ys), N, sorted(self.sel)

    def press(self, key):
        self.sent.append(key)
        if key != "select_card":
            return
        i = len([k for k in self.sent if k == "select_card"]) - 1
        if i < len(self.drops) and self.drops[i]:
            return                      # dropped: nothing toggles
        self.sel ^= {self.cursor}       # TOGGLE


_real_press = ic.press
_real_deselect = ic._deselect_verified
try:
    # --- (A) four clustered drops, the 5th lands -----------------------------
    s = ProbeFakeScreen(select_queue=[None, None, None, None, 4])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("(A) succeeds once the 5th press finally lands", ok is True and cur == 4)
    check("(A) exactly PRESS_VERIFY_TRIES presses were sent, not fewer or more",
          s.sent.count("select_card") == ic.PRESS_VERIFY_TRIES == 5)
    check("(A) the target ends up selected", 4 in sel)

    # --- (B) the first press lands -- exactly one press, no double-toggle ----
    s = ProbeFakeScreen(select_queue=[4])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("(B) succeeds on the first press", ok is True and cur == 4)
    check("(B) EXACTLY ONE press was sent -- nothing fires after a landed look",
          s.sent.count("select_card") == 1)
    check("(B) the target ends up selected", 4 in sel)

    # --- (C) every attempt is dropped -- refuse, and the attempt log persists
    #         into why.json via record_refused_select's new `extra` -----------
    s = ProbeFakeScreen(select_queue=[])          # every press dead
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("(C) a probe that never lifts anything refuses", ok is False)
    check("(C) exactly PRESS_VERIFY_TRIES presses were sent before giving up",
          s.sent.count("select_card") == ic.PRESS_VERIFY_TRIES)
    check("(C) _LAST_PROBE_ATTEMPTS carries one record per attempt",
          len(ic._LAST_PROBE_ATTEMPTS) == ic.PRESS_VERIFY_TRIES)
    check("(C) each record names its own attempt number, in order",
          [a["attempt"] for a in ic._LAST_PROBE_ATTEMPTS]
          == list(range(1, ic.PRESS_VERIFY_TRIES + 1)))
    check("(C) each record carries glow/ys/selected",
          all({"glow", "ys", "selected"} <= set(a) for a in ic._LAST_PROBE_ATTEMPTS))

    # record_refused_select's `extra` merges that log into why.json.
    _real_grab = orch._grab_settle_regions
    _real_look = orch.hand_cursor_look
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = orch.record_refused_select(
                4, "player", 1, out_dir=tmp,
                extra={"probe_attempts": ic._LAST_PROBE_ATTEMPTS})
            why = json.load(open(_os.path.join(out_dir, "why.json")))
            check("(C) why.json still carries the four base fields",
                  why.get("target") == 4 and why.get("kind") == "player"
                  and why.get("attempt") == 1)
            check("(C) why.json carries PRESS_VERIFY_TRIES probe_attempts records",
                  len(why.get("probe_attempts", [])) == ic.PRESS_VERIFY_TRIES == 5)

            # extra=None (the default) must change nothing -- every existing
            # caller of record_refused_select stays unchanged.
            out_dir2 = orch.record_refused_select(4, "player", 1, out_dir=tmp)
            why2 = json.load(open(_os.path.join(out_dir2, "why.json")))
            check("(C) extra=None writes no probe_attempts key at all",
                  "probe_attempts" not in why2)
    finally:
        orch._grab_settle_regions = _real_grab
        orch.hand_cursor_look = _real_look

    # --- (D) a rise at the WRONG slot after two dropped presses: untouched ---
    s = ProbeFakeScreen(select_queue=[None, None, 2])
    ic.press = s.press
    deselect_calls = []

    def fake_deselect_ok(slot, look):
        deselect_calls.append(slot)
        if REST[slot] - s.y[slot] >= 25:
            s.y[slot] = REST[slot]
        return True, s.selected()

    ic._deselect_verified = fake_deselect_ok
    try:
        ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    finally:
        ic._deselect_verified = _real_deselect
    check("(D) a wrong-slot rise still succeeds, naming the true slot",
          ok is True and cur == 2)
    check("(D) it took exactly 3 presses to surface (2 drops + the landed 3rd)",
          s.sent.count("select_card") == 3)
    check("(D) the wrong slot was explicitly untoggled",
          deselect_calls == [2])
    check("(D) it ends up put back down", 2 not in sel)

    # --- (E) B1: the true cursor sits on an ALREADY-SELECTED slot, every -----
    #         press lands -> re-lifted, no batter lost --------------------
    s = ToggleFakeScreen(cursor=2, selected=[2], drops=[False] * ic.PRESS_VERIFY_TRIES)
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(0, s.ys, sorted(s.sel), s.look)
    check("(E) succeeds, naming the true (already-selected) cursor slot",
          ok is True and cur == 2)
    check("(E) the batter is never left down", 2 in sel)

    # --- (F) same, but presses 1 and 3 are DROPPED (an ODD landed count) ----
    s = ToggleFakeScreen(cursor=2, selected=[2],
                          drops=[True, False, True, False, False])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(0, s.ys, sorted(s.sel), s.look)
    check("(F) succeeds despite an odd landed-press count",
          ok is True and cur == 2)
    check("(F) the batter is never left down", 2 in sel)

    # --- (G) end to end, I-48b's own shape: through the REAL
    #         _verified_select_and_play_inner, both budgets commit ----------
    class PlayScreen:
        """slot 0 (tactics) is structurally glow-blind (I-02); select_card
        ALWAYS lands on `true_cursor` (2, the batter) -- I-48b's premise --
        and it is a real toggle."""

        def __init__(self):
            self.glow_slot, self.true_cursor = 2, 2
            self.y, self.sent, self.committed = list(REST), [], False

        def selected(self):
            return [i for i, y in enumerate(self.y) if REST[i] - y >= 25]

        def look(self):
            glow = [0.2] * N
            if self.glow_slot is not None and self.glow_slot != 0:
                glow[self.glow_slot] = 27.0
            return glow, [100] * N, (0 if self.committed else N), self.selected()

        def press(self, key):
            self.sent.append(key)
            if key == "move_left":
                self.glow_slot = max(0, (self.glow_slot or 0) - 1)
            elif key == "move_right":
                self.glow_slot = min(N - 1, (self.glow_slot or 0) + 1)
            elif key == "select_card":
                t = self.true_cursor
                self.y[t] = REST[t] if REST[t] - self.y[t] >= 25 else REST[t] - 44
            elif key == "confirm_play":
                self.committed = True

    for _budget in (2, 5):
        scr = PlayScreen()
        ic.press = scr.press
        old_max = ic.PROBE_SELECT_MAX
        ic.PROBE_SELECT_MAX = _budget
        try:
            res = ic._verified_select_and_play_inner(2, 0, scr.look)
        finally:
            ic.PROBE_SELECT_MAX = old_max
        check(f"(G budget={_budget}) the play COMMITS, not stalls",
              res is True)
        check(f"(G budget={_budget}) confirm_play sent exactly once",
              scr.sent.count("confirm_play") == 1)
        check(f"(G budget={_budget}) the batter ends up selected at commit",
              2 in scr.selected())
finally:
    ic.press = _real_press
    ic._deselect_verified = _real_deselect
    ic.PROBE_SELECT_MAX = ic.PRESS_VERIFY_TRIES

# --- (H) B2: the REAL orchestrator.play_one_turn call site passes `extra` ---
_hand = [
    {"kind": "player", "hand_index": 0, "name": "Test Batter", "power": 7,
     "secondary": 1},
    {"kind": "tactics", "hand_index": 1, "name": "Power Swing",
     "type": "swing_boost", "bonus": 2},
]
_state_json = {"phase": "batting", "your_score": 0, "opp_score": 0,
               "discards_left": 0, "runners": [], "hand": _hand}
_real_sap = orch.select_and_play
_real_grab_h = orch._grab_settle_regions
_real_look_h = orch.hand_cursor_look
_real_attempts = ic._LAST_PROBE_ATTEMPTS
_env_key = orch.REFUSED_SELECT_DIR_ENV
_had_env, _old_env = _env_key in _os.environ, _os.environ.get(_env_key)

_STALE_ATTEMPTS = [
    {"attempt": 99, "glow": [9.9] * N, "ys": [100] * N, "selected": []}]
_FRESH_ATTEMPTS = [
    {"attempt": 1, "glow": [0.2] * N, "ys": [100] * N, "selected": []}]


def _refuse_with_probe(*a, **k):
    # I-51b: `_LAST_PROBE_ATTEMPTS` is only ever REBOUND (never mutated) inside
    # _probe_select_blind_target -- mimic that rebind so the freshness check
    # orchestrator.py's call site now does (identity moved since the play
    # started) sees a probe that genuinely ran THIS call.
    ic._LAST_PROBE_ATTEMPTS = list(_FRESH_ATTEMPTS)
    return False


def _refuse_without_probe(*a, **k):
    # No rebind at all -- models a refusal whose WALK failed before any probe
    # ran (or I-57's top-up ran instead of a probe): _LAST_PROBE_ATTEMPTS is
    # whatever the LAST probe (from a different play) left behind.
    return False


orch.select_and_play = _refuse_with_probe          # every play is refused
orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [])
ic._LAST_PROBE_ATTEMPTS = list(_STALE_ATTEMPTS)    # a record from a PRIOR play
try:
    with tempfile.TemporaryDirectory() as tmp:
        _os.environ[_env_key] = tmp
        played, info = orch.play_one_turn(_state_json, 0)
        check("(H) play_one_turn reports the refusal (played False)", played is False)
        dirs = [d for d in _os.listdir(tmp) if d.startswith("refused_select_")]
        check("(H) exactly one refused_select_* dir was written", len(dirs) == 1)
        why = json.load(open(_os.path.join(tmp, dirs[0], "why.json"))) if dirs else {}
        check("(H) why.json carries the FRESH probe_attempts this call rebound, "
              "not the stale one seeded before it",
              why.get("probe_attempts") == _FRESH_ATTEMPTS)

        # --- (J) I-51b: a SECOND play, on the SAME process, that refuses
        #         WITHOUT a probe ever running this call -- its why.json must
        #         carry no probe_attempts (or an empty list), never the FRESH
        #         list the FIRST play just left behind
        # (agent_progress/census evidence: a 62-second-old record attached to
        # an unrelated refusal) -------------------------------------------
        orch.select_and_play = _refuse_without_probe
        played2, info2 = orch.play_one_turn(_state_json, 0)
        check("(J) play_one_turn reports the second refusal too",
              played2 is False)
        dirs2 = sorted(d for d in _os.listdir(tmp)
                        if d.startswith("refused_select_"))
        check("(J) two refusals were recorded", len(dirs2) == 2)
        why2 = (json.load(open(_os.path.join(tmp, dirs2[1], "why.json")))
                if len(dirs2) == 2 else {})
        check("(J) the second refusal (no probe this call) carries no "
              "probe_attempts -- a stale list must never be attached",
              not why2.get("probe_attempts"))
finally:
    orch.select_and_play = _real_sap
    orch._grab_settle_regions = _real_grab_h
    orch.hand_cursor_look = _real_look_h
    ic._LAST_PROBE_ATTEMPTS = _real_attempts
    if _had_env:
        _os.environ[_env_key] = _old_env
    else:
        _os.environ.pop(_env_key, None)

# --- (I) N-2 (round-2 skeptic): a GARBLED post-press frame -- _look_settled's
#         own bad-read sentinel, n=0 and `sel` EMPTIED -- must never be read as
#         a disappearance. The row-count guard (`if n != MAX_HAND_SIZE`) has to
#         fire BEFORE the `gone = [i for i in before if i not in sel]` line even
#         looks at `sel`: with `before=[2]` (an already-selected slot, I-48b's
#         own batter) and `sel` emptied by the sentinel, `gone` would equal
#         `[2]` and the mutant order would re-select a slot on the strength of
#         a frame nobody could read -- not a real disappearance. -------------
class GarbledScreen:
    """Every look() this probe takes is unreadable: n=0, sel=[] on every call,
    so `_look_settled` exhausts LOOK_RETRIES and hands back its own sentinel
    rather than a real frame."""

    def __init__(self):
        self.sent = []

    def look(self):
        return [0.2] * N, [100] * N, 0, []

    def press(self, key):
        self.sent.append(key)


s = GarbledScreen()
ic.press = s.press
select_verified_calls = []
_real_select_verified = ic._select_verified
ic._select_verified = lambda slot, look: (
    select_verified_calls.append(slot) or (True, [slot]))
try:
    ok, cur, sel = ic._probe_select_blind_target(0, [100] * N, [2], s.look)
finally:
    ic.press = _real_press
    ic._select_verified = _real_select_verified
check("(I) a garbled post-press frame refuses rather than guessing", ok is False)
check("(I) _select_verified is never called on the previously-selected slot "
      "-- the row-count guard beats the gone computation to it",
      select_verified_calls == [])
check("(I) exactly one press -- the row-count guard returns on the very "
      "first unreadable look, no further attempts",
      s.sent.count("select_card") == 1)

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the probe absorbs a run of up to PRESS_VERIFY_TRIES clustered drops, "
      "stops the instant a press lands, logs one record per attempt into "
      "_LAST_PROBE_ATTEMPTS, record_refused_select's extra persists that log into "
      "why.json without disturbing any existing caller, and a wrong-slot rise is "
      "still untoggled exactly as before")


# =============================================================================
print()
print("MUTATION TESTING")
# =============================================================================
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
with open(IC_PATH, "rb") as f:
    _IC_ORIG_BYTES = f.read()


def _reload_ic():
    global ic
    _clear_pycache("input_controller")
    ic = importlib.reload(ic)


def _restore_ic():
    with open(IC_PATH, "wb") as f:
        f.write(_IC_ORIG_BYTES)
    _reload_ic()
    check("input_controller.py restored byte-for-byte", _sha(IC_PATH) == _ic_sha0)


_orch_sha0 = _sha(ORCH_PATH)
with open(ORCH_PATH, "rb") as f:
    _ORCH_ORIG_BYTES = f.read()


def _reload_orch():
    global orch
    _clear_pycache("orchestrator")
    orch = importlib.reload(orch)


def _restore_orch():
    with open(ORCH_PATH, "wb") as f:
        f.write(_ORCH_ORIG_BYTES)
    _reload_orch()
    check("orchestrator.py restored byte-for-byte", _sha(ORCH_PATH) == _orch_sha0)


_real_press = ic.press
_real_deselect = ic._deselect_verified

# --- mutant 1: the budget reverts to a literal 2 --------------------------
print("mutant 1: PROBE_SELECT_MAX back to a literal 2 -- case A must fail")
try:
    _mutate(IC_PATH, "PROBE_SELECT_MAX = PRESS_VERIFY_TRIES",
            "PROBE_SELECT_MAX = 2")
    _reload_ic()
    s = ProbeFakeScreen(select_queue=[None, None, None, None, 4])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("mutant 1 caught: a 5th-press landing is never reached at budget 2",
          ok is False and s.sent.count("select_card") == 2)
finally:
    ic.press = _real_press
    _restore_ic()

# --- mutant 2: an extra press fires before the first look ------------------
print("mutant 2: an unconditional press before the loop's own look -- case B "
      "must show 2 presses instead of 1")
try:
    _mutate(
        IC_PATH,
        "    before = set(before_sel)\n"
        "    sel = before_sel\n"
        "    for attempt in range(1, PROBE_SELECT_MAX + 1):\n",
        "    before = set(before_sel)\n"
        "    sel = before_sel\n"
        "    press(\"select_card\")  # MUTANT (I-51 test): pressed before any look\n"
        "    time.sleep(SELECT_SETTLE_SEC)\n"
        "    for attempt in range(1, PROBE_SELECT_MAX + 1):\n")
    _reload_ic()
    s = ProbeFakeScreen(select_queue=[4])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("mutant 2 caught: a press before ever looking costs an extra one",
          s.sent.count("select_card") == 2)
finally:
    ic.press = _real_press
    _restore_ic()

# --- mutant 3: the attempt log is never appended to -------------------------
print("mutant 3: _LAST_PROBE_ATTEMPTS.append(...) is dropped -- case C's "
      "record count must fail")
try:
    _mutate(
        IC_PATH,
        '        _LAST_PROBE_ATTEMPTS.append({"attempt": attempt, "glow": list(_g),\n'
        '                                      "ys": list(_ys), "selected": list(sel)})\n',
        '')
    _reload_ic()
    s = ProbeFakeScreen(select_queue=[])          # every press dead -> refuses
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("mutant 3 caught: no attempt records were kept",
          ok is False and len(ic._LAST_PROBE_ATTEMPTS) == 0)
finally:
    ic.press = _real_press
    _restore_ic()

# --- mutant 4 (skeptic's M1, re-run): `if target in new:` -> `if new:` ------
# A rise at the WRONG slot would then be misattributed to the TARGET -- case D
# must catch it (cur must stay 2, the true slot, never 4).
print("mutant 4 (skeptic M1): `if target in new:` -> `if new:` -- case D must "
      "misattribute the wrong-slot rise to the target")
try:
    _mutate(IC_PATH, "        if target in new:\n", "        if new:\n")
    _reload_ic()
    s = ProbeFakeScreen(select_queue=[None, None, 2])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
    check("mutant 4 caught: the wrong slot (2) was reported as the target (4)",
          ok is True and cur == 4)
finally:
    ic.press = _real_press
    _restore_ic()

# --- mutant 5 (B1): the whole disappearance ("gone") branch is dropped -----
print("mutant 5: the B1 disappearance branch is deleted -- case E must fail "
      "(the already-selected batter is lost, not re-lifted)")
try:
    _mutate(
        IC_PATH,
        '        # B1: a DISAPPEARANCE names the true cursor exactly as a rise does --\n'
        '        # this press toggled an already-selected slot back down, so put it back\n'
        '        # up and stop; never press select_card again on the strength of a guess.\n'
        '        gone = [i for i in before if i not in sel]\n'
        '        if gone:\n'
        '            back = gone[0]\n'
        '            print(f"  [cursor] probe-select made {back} disappear (it was already "\n'
        '                  "selected before this probe) — the true cursor is there; "\n'
        '                  "re-selecting it rather than pressing blind again")\n'
        '            ok2, sel2 = _select_verified(back, look)\n'
        '            if not ok2:\n'
        '                print(f"  [cursor] could not re-select probe slot {back} — refusing "\n'
        '                      "rather than leaving it lost")\n'
        '                return False, None, sel2\n'
        '            return True, back, sel2\n',
        '')
    _reload_ic()
    s = ToggleFakeScreen(cursor=2, selected=[2], drops=[False] * ic.PRESS_VERIFY_TRIES)
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(0, s.ys, sorted(s.sel), s.look)
    check("mutant 5 caught: the already-selected batter (2) ends up lost",
          2 not in sel)
finally:
    ic.press = _real_press
    _restore_ic()

# --- mutant 6: presses AFTER detecting a disappearance, WITHOUT verifying --
# A plain extra press right before the existing `_select_verified` call turns
# out EQUIVALENT for most drop patterns -- `_select_verified` itself checks
# state before pressing, so an unconditional press one line earlier does
# exactly what its own first internal attempt would have done anyway (same
# press() call, same position in the drop sequence, same outcome). The
# discriminating mutant is the one the skeptic's wording actually guards
# against: pressing WITHOUT VERIFYING the result at all, so a corrective press
# that itself gets swallowed (F's own odd drop pattern makes this happen) is
# reported as success with the batter still down.
print("mutant 6: press-and-return-unverified after detecting a disappearance "
      "-- case F must show the batter left down when that corrective press "
      "is itself dropped")
try:
    _mutate(
        IC_PATH,
        '            ok2, sel2 = _select_verified(back, look)\n'
        '            if not ok2:\n'
        '                print(f"  [cursor] could not re-select probe slot {back} — refusing "\n'
        '                      "rather than leaving it lost")\n'
        '                return False, None, sel2\n'
        '            return True, back, sel2\n',
        '            press("select_card")  # MUTANT (I-51 test): no verify\n'
        '            return True, back, sel\n')
    _reload_ic()
    s = ToggleFakeScreen(cursor=2, selected=[2],
                          drops=[True, False, True, False, False])
    ic.press = s.press
    ok, cur, sel = ic._probe_select_blind_target(0, s.ys, sorted(s.sel), s.look)
    check("mutant 6 caught: an unverified corrective press that got dropped "
          "still reports the batter selected", 2 not in sel)
finally:
    ic.press = _real_press
    _restore_ic()

# --- mutant 7 (B2): the production call site drops `extra=` ----------------
print("mutant 7 (B2): orchestrator.play_one_turn's record_refused_select call "
      "drops extra= -- case H must find no probe_attempts in why.json")
try:
    _mutate(
        ORCH_PATH,
        '        _probe_ran_this_call = (\n'
        '            id(input_controller._LAST_PROBE_ATTEMPTS) != _probe_attempts_before)\n'
        '        record_refused_select(\n'
        '            player_idx, "player+tactics" if tactics_idx is not None else "player",\n'
        '            _PLAY_STALL["n"],\n'
        '            extra={"probe_attempts": (\n'
        '                input_controller._LAST_PROBE_ATTEMPTS if _probe_ran_this_call\n'
        '                else [])})',
        '        record_refused_select(\n'
        '            player_idx, "player+tactics" if tactics_idx is not None else "player",\n'
        '            _PLAY_STALL["n"])')
    _reload_orch()
    _real_sap_m7 = orch.select_and_play
    _real_grab_m7 = orch._grab_settle_regions
    _real_look_m7 = orch.hand_cursor_look
    # a probe genuinely runs this call (the FRESH-rebind stub from case H) --
    # if `extra=` were still wired up, probe_attempts WOULD be present, so
    # this mutant is caught by its absence, not by the freshness check.
    orch.select_and_play = _refuse_with_probe
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [])
    ic._LAST_PROBE_ATTEMPTS = list(_STALE_ATTEMPTS)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _os.environ[orch.REFUSED_SELECT_DIR_ENV] = tmp
            orch.play_one_turn(_state_json, 0)
            dirs = [d for d in _os.listdir(tmp) if d.startswith("refused_select_")]
            why = (json.load(open(_os.path.join(tmp, dirs[0], "why.json")))
                   if dirs else {})
            check("mutant 7 caught: probe_attempts never reached why.json",
                  "probe_attempts" not in why)
    finally:
        orch.select_and_play = _real_sap_m7
        orch._grab_settle_regions = _real_grab_m7
        orch.hand_cursor_look = _real_look_m7
        _os.environ.pop(orch.REFUSED_SELECT_DIR_ENV, None)
finally:
    _restore_orch()

# --- mutant 9 (I-57 B2 / I-51b): the freshness check is bypassed --
# `_probe_ran_this_call` always True, so a SECOND play that never probed still
# gets the FIRST play's list attached -- case J must fail --------------------
print("mutant 9 (I-51b): the freshness check is bypassed -- a stale "
      "probe_attempts list is attached even when no probe ran this call -- "
      "case J must fail")
try:
    _mutate(
        ORCH_PATH,
        '        _probe_ran_this_call = (\n'
        '            id(input_controller._LAST_PROBE_ATTEMPTS) != _probe_attempts_before)\n',
        '        _probe_ran_this_call = True  # MUTANT (I-51b test): never False\n')
    _reload_orch()
    _real_sap_m9 = orch.select_and_play
    _real_grab_m9 = orch._grab_settle_regions
    _real_look_m9 = orch.hand_cursor_look
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [])
    ic._LAST_PROBE_ATTEMPTS = list(_STALE_ATTEMPTS)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _os.environ[orch.REFUSED_SELECT_DIR_ENV] = tmp
            orch.select_and_play = _refuse_with_probe
            orch.play_one_turn(_state_json, 0)             # play 1: DID probe
            orch.select_and_play = _refuse_without_probe
            orch.play_one_turn(_state_json, 0)             # play 2: did NOT
            dirs = sorted(d for d in _os.listdir(tmp)
                          if d.startswith("refused_select_"))
            why2 = (json.load(open(_os.path.join(tmp, dirs[1], "why.json")))
                    if len(dirs) == 2 else {})
            check("mutant 9 caught: the second (no-probe) refusal wrongly "
                  "carries the first play's stale probe_attempts",
                  bool(why2.get("probe_attempts")))
    finally:
        orch.select_and_play = _real_sap_m9
        orch._grab_settle_regions = _real_grab_m9
        orch.hand_cursor_look = _real_look_m9
        _os.environ.pop(orch.REFUSED_SELECT_DIR_ENV, None)
finally:
    _restore_orch()

# --- mutant 8 (N-2, round-2 skeptic): the `gone` computation moved ABOVE the
# row-count guard -- case I must fail (a garbled, unreadable frame gets read as
# a disappearance and _select_verified fires on it) ------------------------
print("mutant 8 (N-2): the gone computation moved above the row-count guard "
      "-- case I must call _select_verified on an unreadable frame")
try:
    _mutate(
        IC_PATH,
        '        if n != MAX_HAND_SIZE:\n'
        '            print(f"  [cursor] cannot read the fan after the probe select (rows={n}) "\n'
        '                  "— refusing")\n'
        '            return False, None, sel\n'
        '        # B1: a DISAPPEARANCE names the true cursor exactly as a rise does --\n'
        '        # this press toggled an already-selected slot back down, so put it back\n'
        '        # up and stop; never press select_card again on the strength of a guess.\n'
        '        gone = [i for i in before if i not in sel]\n'
        '        if gone:\n'
        '            back = gone[0]\n'
        '            print(f"  [cursor] probe-select made {back} disappear (it was already "\n'
        '                  "selected before this probe) — the true cursor is there; "\n'
        '                  "re-selecting it rather than pressing blind again")\n'
        '            ok2, sel2 = _select_verified(back, look)\n'
        '            if not ok2:\n'
        '                print(f"  [cursor] could not re-select probe slot {back} — refusing "\n'
        '                      "rather than leaving it lost")\n'
        '                return False, None, sel2\n'
        '            return True, back, sel2\n',
        '        # MUTANT (I-51 N-2): gone computed before the row-count guard checks it\n'
        '        gone = [i for i in before if i not in sel]\n'
        '        if gone:\n'
        '            back = gone[0]\n'
        '            print(f"  [cursor] probe-select made {back} disappear (it was already "\n'
        '                  "selected before this probe) — the true cursor is there; "\n'
        '                  "re-selecting it rather than pressing blind again")\n'
        '            ok2, sel2 = _select_verified(back, look)\n'
        '            if not ok2:\n'
        '                print(f"  [cursor] could not re-select probe slot {back} — refusing "\n'
        '                      "rather than leaving it lost")\n'
        '                return False, None, sel2\n'
        '            return True, back, sel2\n'
        '        if n != MAX_HAND_SIZE:\n'
        '            print(f"  [cursor] cannot read the fan after the probe select (rows={n}) "\n'
        '                  "— refusing")\n'
        '            return False, None, sel\n')
    _reload_ic()
    s = GarbledScreen()
    ic.press = s.press
    m8_calls = []
    ic._select_verified = lambda slot, look: (
        m8_calls.append(slot) or (True, [slot]))
    try:
        ok, cur, sel = ic._probe_select_blind_target(0, [100] * N, [2], s.look)
    finally:
        ic.press = _real_press
        ic._select_verified = _real_select_verified
    check("mutant 8 caught: _select_verified fires on an unreadable frame",
          m8_calls == [2])
finally:
    ic.press = _real_press
    ic._select_verified = _real_select_verified
    _restore_ic()

# --- sanity: the fix is intact after all mutants ----------------------------
s = ProbeFakeScreen(select_queue=[None, None, None, None, 4])
ic.press = s.press
try:
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
finally:
    ic.press = _real_press
check("post-restore sanity: case A passes again",
      ok is True and cur == 4 and s.sent.count("select_card") == ic.PRESS_VERIFY_TRIES
      and len(ic._LAST_PROBE_ATTEMPTS) == ic.PRESS_VERIFY_TRIES)

s = ToggleFakeScreen(cursor=2, selected=[2], drops=[False] * ic.PRESS_VERIFY_TRIES)
ic.press = s.press
try:
    ok, cur, sel = ic._probe_select_blind_target(0, s.ys, sorted(s.sel), s.look)
finally:
    ic.press = _real_press
check("post-restore sanity: case E passes again", ok is True and cur == 2 and 2 in sel)

with tempfile.TemporaryDirectory() as tmp:
    orch._grab_settle_regions = lambda regions: {"hand": Image.new("L", (10, 10))}
    orch.hand_cursor_look = lambda: ([0.0] * N, list(REST), N, [])
    orch.select_and_play = _refuse_with_probe
    ic._LAST_PROBE_ATTEMPTS = list(_STALE_ATTEMPTS)
    try:
        _os.environ[orch.REFUSED_SELECT_DIR_ENV] = tmp
        orch.play_one_turn(_state_json, 0)
    finally:
        orch._grab_settle_regions = _real_grab_h
        orch.hand_cursor_look = _real_look_h
        orch.select_and_play = _real_sap
        _os.environ.pop(orch.REFUSED_SELECT_DIR_ENV, None)
    dirs = [d for d in _os.listdir(tmp) if d.startswith("refused_select_")]
    why = json.load(open(_os.path.join(tmp, dirs[0], "why.json"))) if dirs else {}
    check("post-restore sanity: case H's probe_attempts is back",
          why.get("probe_attempts") == _FRESH_ATTEMPTS)

s = GarbledScreen()
ic.press = s.press
m8_calls_post = []
ic._select_verified = lambda slot, look: (
    m8_calls_post.append(slot) or (True, [slot]))
try:
    ok, cur, sel = ic._probe_select_blind_target(0, [100] * N, [2], s.look)
finally:
    ic.press = _real_press
    ic._select_verified = _real_select_verified
check("post-restore sanity: case I passes again",
      ok is False and m8_calls_post == [])

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  all nine mutants caught, input_controller.py and orchestrator.py "
      "restored byte-for-byte")
