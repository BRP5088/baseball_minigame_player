"""I-28: `_clear_strays` treated the ENGINE'S OWN TARGET going blind the moment it
selects as "went unreadable DURING this operation" and refused -- the same refusal
I-26 built for a genuine stray, now firing on a landed select instead.

Root cause (I-21's own mechanism, re-read against I-26's fix): selecting a card is
what makes its power disc unreadable, so a correctly-selected target's `y` reads
`None` on the very next look, exactly like a stray mid-lift. I-26 added a re-look
and a refusal for any slot that stays blind after it -- and never exempted `want`,
so the target itself, having JUST been proven selected by `_select_verified`'s own
inference (`_verified_select_and_play_inner` calls `_select_verified` before
`_clear_strays` ever runs), was scored as a stray and refused three times running
before I-03's exclusion dropped the card. Live: `overnight/run_live_20260920h.log:
121-132`. Reproduced offline with a scripted `look()` that always answers the
target blind (case (a) below).

Two fixes, both in `_clear_strays`:

  (1) `want` is exempt from the "newly blind" computation, so the engine's own
      target(s) never enter the I-26 re-look/refuse branch at all -- landing IS
      going blind, not a stray appearing.
  (2) THE COMMIT GATE ITSELF HAD TO AGREE. `selected_cards()` (the `sel` a fresh
      `look()` returns) abstains on exactly the row this guard exempts -- its `y`
      is `None`, and `selected_cards` skips a `None` row by construction (same
      shape I-26's own docstring already describes for a stray). So even after (1)
      stops the early refusal, the ORIGINAL final gate (`want <= set(sel)`) would
      still refuse the instant `sel` is consulted, because a blind target is never
      IN `sel`. `_clear_strays` now ORs `(set(want) & _blind_now)` into `lifted`
      wherever it reads `sel`, so the stray computation and the commit gate both
      agree with the exemption in (1) instead of re-discovering the same refusal
      one line later.

Case (c) is the one that proves (1) did not turn into "ignore every blind slot":
an inferred-selected target sits blind NEXT TO a genuinely lifted stray with a
REAL (non-None) risen y, and the stray must still be caught and, if it cannot be
cleared, still refuse the commit.

Uses the same check(cond, msg) shape as test_stray_guard_ignores_flicker.py and
test_select_stops_when_lift_unreadable.py (checked with
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
    repeating the last one if it is called more times than scripted -- so a bug
    that adds an UNEXPECTED extra look does not crash the test, it fails the
    call-count assertion instead.
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
    print("(a) THE REPRODUCTION: the engine's own target goes blind the moment "
          "it selects, and stays blind on every look -- commits, no re-look")
    # =====================================================================
    _slept.clear()
    want = {1}
    # The target's disc goes unreadable the instant it lifts (I-21) and never
    # recovers -- this is what a LANDED select looks like from here, not a
    # dropped press. selected_cards() names it selected anyway (a real deploy
    # would abstain on the same None row, which case (c)/(d) below exercise --
    # this script pins the minimal repro as described in the ticket).
    look1 = (_flat_glow({1}), [100, None, 120, 130, 140], N, [1])
    scr = ScriptedLook([look1])
    ok = ic._clear_strays(want, scr.look, blind_before=set())
    check(ok is True, f"the engine's own blind target must not be refused as a "
          f"stray; got {ok!r}")
    check(scr.calls == 1, f"want is exempt from the newly-blind re-look entirely "
          f"-- expected exactly 1 look() call, got {scr.calls}")
    check(len(_slept) == 0, f"no re-look means no sleep; got {_slept!r}")

    # =====================================================================
    print("(b) CONTROL: a NON-want slot that stays blind through the re-look "
          "is still refused -- the exemption is narrow, not blanket")
    # =====================================================================
    _slept.clear()
    want = {2}
    # slot 2 (the target) is genuinely selected and readable throughout; slot 0
    # is a stray that goes blind and never recovers, exactly I-26's own case (d).
    look1 = (_flat_glow({2}), [None, REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    look2 = (_flat_glow({2}), [None, REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    scr = ScriptedLook([look1, look2])
    ok = ic._clear_strays(want, scr.look, blind_before=set())
    check(ok is False, f"a NON-want slot that stays blind after the re-look must "
          f"still refuse; got {ok!r}")
    check(scr.calls == 2, f"exactly one extra look past the first -- got "
          f"{scr.calls} look() calls")
    check(len(_slept) == 1 and abs(_slept[0] - ic.SELECT_RETRY_CONFIRM_SEC) < 1e-9,
          f"the one sleep must be SELECT_RETRY_CONFIRM_SEC ({ic.SELECT_RETRY_CONFIRM_SEC}); "
          f"got {_slept!r}")

    # =====================================================================
    print("(c) an inferred-selected target next to a genuinely lifted NON-want "
          "stray (a real risen y) -- the stray is still caught, not masked")
    # =====================================================================
    want = {1}
    # slot 1 (the target) is blind, inferred selected -- realistic production
    # shape: selected_cards() abstains on it too (it is not in `sel`), so this
    # exercises the commit-gate OR-fix, not just the early-refusal exemption.
    # slot 3 is a REAL stray: a measured rise past SELECTED_MIN_RISE, readable,
    # and named in `sel` -- it must be caught and, when it cannot be cleared,
    # the whole commit must still refuse.
    rise = int(lh.SELECTED_MIN_RISE) + 20
    ys = [REST[0], None, REST[2], REST[3] - rise, REST[4]]
    check(REST[3] - ys[3] >= lh.SELECTED_MIN_RISE,
          "sanity: the scripted rise clears SELECTED_MIN_RISE")

    def _look_c():
        return _flat_glow({3}), list(ys), N, [3]

    _old_walk = ic._walk_cursor_to
    ic._walk_cursor_to = lambda target, look: (False, [])
    try:
        ok = ic._clear_strays(want, _look_c, blind_before=set())
    finally:
        ic._walk_cursor_to = _old_walk
    check(ok is False, f"a real stray beside an inferred-selected target must "
          f"still be caught and refuse when it cannot be cleared -- the "
          f"exemption must not mask it; got {ok!r}")

    # =====================================================================
    print("(d) BOTH targets (card + tactics) inferred-selected and blind -- "
          "commits")
    # =====================================================================
    _slept.clear()
    want = {1, 3}
    # Neither target's disc reads (both freshly lifted); neither is in `sel`
    # either, the realistic production shape -- the commit gate must accept
    # both from the OR-fix alone, with no stray left over.
    ys = [REST[0], None, REST[2], None, REST[4]]

    def _look_d():
        return _flat_glow({1, 3}), list(ys), N, []

    ok = ic._clear_strays(want, _look_d, blind_before=set())
    check(ok is True, f"both inferred-selected targets, both blind, neither in "
          f"`sel` -- must still commit; got {ok!r}")
    check(len(_slept) == 0, f"neither target is a newly-blind stray, so no "
          f"re-look and no sleep; got {_slept!r}")
finally:
    ic.time.sleep = _old_sleep

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the engine's own blind target(s) commit without a re-look or refusal, "
      "a non-want stray that stays blind is still refused, and a real stray "
      "beside an inferred-selected target is still caught")
