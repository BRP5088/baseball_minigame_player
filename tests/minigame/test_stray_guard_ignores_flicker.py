"""I-26: `_clear_strays`'s "went unreadable DURING this operation" refusal fired
on a FLICKER, not a lift, and deadlocked a resumed match twice in one log.

Live 2026-09-20, `overnight/run_live_20260920h.log` (main checkout): slot 0's
power disc sat hidden under slot 1's card -- the same occluded-slot shape I-25
fixed for the cursor argmax -- and its disc finder locked onto a bogus blob
(a circle sized and positioned like a real digit disc, `y_from == "disc"`, but
`digit is None`). `_clear_strays` read that slot's `y` at the START of the
operation, THEN read it again after the walk/select and found it `None`, and
refused: "slot(s) [0] went unreadable DURING this operation ([None, 152, 139,
162, 162]) -- refusing." Both refusals in the log were followed by a retry that
LANDED, so the guard was wrong, not the card.

CONFIRMED OFFLINE against the real frames (`screenshot_log/run_20260920_220144/`
in the main checkout, matched to the log by epoch timestamp, read through
`orchestrator.crop_gameplay_regions` + `local_hand.read_hand`/`cursor_glow`):
over a 2.9s, 29-frame window spanning the refusal, slot 0's read FLICKERS
between three states with the card never moving --

    y_from="disc", digit=None, y~259-269, glow 30-70     <- most frames
    y_from="fallback", y=198 (gated to None by hand_cursor_look)
    kind="unknown", y_measured=False (gated to None)

The refusal landed on a frame from the second or third state, sandwiched
between two "disc" reads of the same untouched card -- a flicker, exactly
CLAUDE.md 10.26 ("a reader that looks stable on a still may not be. FILM IT.")
one layer over the digit reader it was first measured on.

TWO FIXES, BOTH IN `_clear_strays` (and the callers that hand it `blind_before`):

  (1) A slot whose START-of-operation glow already clears `local_hand.
      CURSOR_GLOW_MAX` is the SAME false reading I-25 already excludes from the
      cursor argmax (a disc that never matched a digit, its window landing on
      card art) -- this layer never sees `rows`, only the raw glow numbers
      `look()` returns, so `_untrustworthy_slots` reuses the ceiling instead of
      `y_from`/`digit` directly. A slot that was never trustworthy cannot be
      proven "lifted by us" later just because it went to None.
  (2) A slot that goes unreadable mid-operation and was NOT already
      untrustworthy gets ONE re-look after `SELECT_RETRY_CONFIRM_SEC` (the same
      settle this file already waits out a swallowed press with) before
      refusing, and refuses only if it is STILL unreadable AND nothing else
      says the fan is at rest (the row count is unchanged and nothing outside
      what the engine chose is lifted). A genuinely lifted stray -- a real,
      measured rise past `SELECTED_MIN_RISE` -- is untouched: it is not `None`
      at all, so neither fix's code path ever runs for it, and the existing
      clear-or-refuse logic still refuses when it cannot be put back down.

Uses the same check(cond, msg) shape as tests/minigame/test_verified_selection.py
and tests/minigame/test_select_stops_when_lift_unreadable.py (checked with
`grep -m1 -o "def check(.*)"` on both before writing this one).
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
import local_hand as lh                                               # noqa: E402

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


N = ic.MAX_HAND_SIZE
REST = [200, 160, 150, 165, 220]


class ScriptedLook:
    """Hands back one scripted (glow, ys, n, sel) tuple per call to `look()`,
    repeating the last one if it is called more times than scripted -- so a
    bug that adds an UNEXPECTED extra look does not crash the test, it fails
    the call-count assertion instead.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def look(self):
        i = min(self.calls, len(self.script) - 1)
        self.calls += 1
        glow, ys, n, sel = self.script[i]
        return list(glow), list(ys), n, list(sel)


def _flat_glow(hot=()):
    g = [0.0] * N
    for i in hot:
        g[i] = 30.0
    return g


_old_sleep = ic.time.sleep
_slept = []
ic.time.sleep = lambda d: _slept.append(d)

try:
    # =====================================================================
    print("(a) a flickered read (unreadable for one look) settles back at "
          "rest -- commit proceeds, exactly one extra look")
    # =====================================================================
    _slept.clear()
    want = {2}
    # look 1: slot 0 unreadable (not in blind_before -- newly blind); slot 2
    # (the engine's own target) genuinely selected.
    look1 = (_flat_glow({2}), [None, REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    # look 2 (the re-look): slot 0 back to its ordinary rest position, not
    # selected -- the flicker cleared on its own.
    look2 = (_flat_glow({2}), [REST[0], REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    scr = ScriptedLook([look1, look2])
    ok = ic._clear_strays(want, scr.look, blind_before=set())
    check(ok is True, f"a flicker that clears on the re-look must not block the "
          f"commit; got {ok!r}")
    check(scr.calls == 2, f"exactly one extra look past the first -- got "
          f"{scr.calls} look() calls")
    check(len(_slept) == 1 and abs(_slept[0] - ic.SELECT_RETRY_CONFIRM_SEC) < 1e-9,
          f"the one sleep must be SELECT_RETRY_CONFIRM_SEC ({ic.SELECT_RETRY_CONFIRM_SEC}); "
          f"got {_slept!r}")

    # =====================================================================
    print("(b) a bogus disc at the START of the operation (I-25's own false "
          "reading) reads None later -- commit proceeds, no extra look")
    # =====================================================================
    _slept.clear()
    want = {2}
    # The baseline read this project's caller would take BEFORE the walk: slot 0
    # is a disc that was found but never matched a digit -- real y, but glow
    # well above CURSOR_GLOW_MAX (68.6, the exact figure measured on the I-25
    # fixture) -- so it is untrustworthy from the first look, before anything
    # was pressed.
    glow0 = _flat_glow({2})
    glow0[0] = 68.6
    ys0 = [259, REST[1], REST[2], REST[3], REST[4]]
    blind0 = ic._untrustworthy_slots(glow0, ys0)
    check(0 in blind0, f"a baseline glow of 68.6 (> CURSOR_GLOW_MAX "
          f"{lh.CURSOR_GLOW_MAX}) must be flagged untrustworthy from the start; "
          f"got {blind0!r}")
    # The only look _clear_strays itself takes: slot 0 has gone properly
    # unreadable (None), which is expected of an untrustworthy position, and
    # nothing else changed.
    look1 = (_flat_glow({2}), [None, REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    scr = ScriptedLook([look1])
    ok = ic._clear_strays(want, scr.look, blind_before=blind0)
    check(ok is True, f"a slot untrustworthy from the start must not block the "
          f"commit when it later reads None; got {ok!r}")
    check(scr.calls == 1, f"no re-look needed -- the slot was already excluded "
          f"by blind_before; got {scr.calls} look() calls")
    check(len(_slept) == 0, f"and nothing was slept for it; got {_slept!r}")

    # =====================================================================
    print("(c) CONTROL: a genuinely LIFTED stray (a real, measured rise) is "
          "still refused when it cannot be cleared")
    # =====================================================================
    want = {2}
    # slot 0 is really up: its y sits SELECTED_MIN_RISE below rest, and
    # selected_cards would name it -- this is not a None anywhere, so neither
    # of the two new code paths (blind_before / the re-look) is even reached.
    rise = int(lh.SELECTED_MIN_RISE) + 20
    lifted_ys = [REST[0] - rise, REST[1], REST[2] - 44, REST[3], REST[4]]
    check(REST[0] - lifted_ys[0] >= lh.SELECTED_MIN_RISE,
          "sanity: the scripted rise clears SELECTED_MIN_RISE")

    def _always_look():
        return _flat_glow({0, 2}), list(lifted_ys), N, [0, 2]

    _old_walk = ic._walk_cursor_to
    ic._walk_cursor_to = lambda target, look: (False, [])
    try:
        ok = ic._clear_strays(want, _always_look, blind_before=set())
    finally:
        ic._walk_cursor_to = _old_walk
    check(ok is False, f"a real stray that cannot be walked-to-and-cleared must "
          f"still refuse; got {ok!r}")
finally:
    ic.time.sleep = _old_sleep

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a flickered read settles and commits with one extra look, a slot "
      "untrustworthy from the start commits with none, and a genuinely lifted "
      "stray that cannot be cleared is still refused")
