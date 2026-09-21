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
    print("(D) record_refused_select writes NOTHING under BASEBALL_TEST_RUN")
    # =====================================================================
    _os.environ["BASEBALL_TEST_RUN"] = "1"
    with tempfile.TemporaryDirectory() as _watch:
        # No out_dir and no env override -- the same _running_under_test() gate
        # record_reveal_kind / record_money_read_frame already use.
        _os.environ.pop(orch.REFUSED_SELECT_DIR_ENV, None)
        got = orch.record_refused_select(0, "player+tactics", 1)
        check("(D) returns None under the test flag", got is None)
        check("(D) writes nothing to the real corpus",
              not _os.path.isdir(orch.DEAL_FRAME_DIR)
              or not any(n.startswith("refused_select_")
                         for n in _os.listdir(orch.DEAL_FRAME_DIR)))

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
                "            tactics_index = None\n            continue\n",
                "            tactics_index = None\n            return False\n")
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

finally:
    pass

print()
if fails:
    print(f"{len(fails)} FAILED")
    _sys.exit(1)
print("all checks passed")
