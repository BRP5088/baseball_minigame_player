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

FakeScreen models a "dropped" press as `None` in `select_queue` (no effect at all,
not a toggle) rather than reusing `test_blind_slot_probe_select.py`'s toggle-based
`ProbeScreen` -- simpler here because this file drives the probe directly rather
than through moves, and the toggle model would make a "double press" mutant look
identical to a single clean one on some inputs (two toggles cancel), which is
exactly the ambiguity a press-count assertion needs to avoid.
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
finally:
    ic.press = _real_press
    ic._deselect_verified = _real_deselect

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

# --- sanity: the fix is intact after all three mutants ----------------------
s = ProbeFakeScreen(select_queue=[None, None, None, None, 4])
ic.press = s.press
try:
    ok, cur, sel = ic._probe_select_blind_target(4, s.ys, [], s.look)
finally:
    ic.press = _real_press
check("post-restore sanity: case A passes again",
      ok is True and cur == 4 and s.sent.count("select_card") == ic.PRESS_VERIFY_TRIES
      and len(ic._LAST_PROBE_ATTEMPTS) == ic.PRESS_VERIFY_TRIES)

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  all three mutants caught, input_controller.py restored byte-for-byte")
