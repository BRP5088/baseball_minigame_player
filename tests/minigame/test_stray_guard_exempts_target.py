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
      is `None`, and `selected_cards` skips a `None` row by construction. So even
      after (1) stops the early refusal, the ORIGINAL final gate
      (`want <= set(sel)`) would still refuse the instant `sel` is consulted,
      because a blind target is never IN `sel`.

A SKEPTIC CAUGHT THE FIRST SHIP OF (2) TRUSTING `want` UNCONDITIONALLY. The first
version simply OR'd `(set(want) & _blind_now)` into `lifted`, which counts a
`want` slot as lifted purely because it is (a) blind now and (b) something the
engine asked for -- with nothing ever proving it was actually toggled ON. A `want`
slot that was ALREADY occluded before this operation touched anything (CLAUDE.md
10.28: a card whose disc sits permanently under its neighbour, never revealed by
any input) would sail through as "selected" on that mutant's strength alone,
committing a card that was never lifted at all. Fixed by narrowing the inference
to I-21's own signature: a `want` slot counts as lifted BY INFERENCE only when it
was READABLE at the operation's baseline (`ys0[k] is not None`, the snapshot both
callers already capture before pressing anything) and is blind NOW -- a proven
lift, not a chronic occlusion. `_clear_strays` gained an `ys0=None` parameter for
this and both callers (`_verified_select_and_play_inner`, `select_and_discard`)
now pass their own `_ys0`. A `want` slot blind at baseline AND blind now must
still appear in `sel` on its own, or the commit refuses (case (f)).

Case (c) is the one that proves (1) did not turn into "ignore every blind slot":
an inferred-selected target sits blind NEXT TO a genuinely lifted stray with a
REAL (non-None) risen y, and the stray must still be caught and, if it cannot be
cleared, still refuse the commit. Case (e) proves the SAME thing on the baseline
side: an inferred-selected target sits blind NEXT TO a NON-want slot that was
ALREADY occluded at baseline (never lifted, never going to be) -- the commit must
still succeed, and that occluded slot must never be walked to or deselected,
because it was never counted as a stray in the first place.

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
    print("(a) THE REPRODUCTION: the engine's own target was readable at "
          "baseline, goes blind the moment it selects, and stays blind on "
          "every look -- commits, no re-look")
    # =====================================================================
    _slept.clear()
    want = {1}
    # Baseline: slot 1 was readable BEFORE this operation pressed anything --
    # this is what makes the later blindness a PROVEN lift, not a guess.
    ys0 = [REST[0], REST[1], REST[2], REST[3], REST[4]]
    look1 = (_flat_glow({1}), [100, None, 120, 130, 140], N, [1])
    scr = ScriptedLook([look1])
    ok = ic._clear_strays(want, scr.look, blind_before=set(), ys0=ys0)
    check(ok is True, f"the engine's own blind target must not be refused as a "
          f"stray; got {ok!r}")
    check(scr.calls == 1, f"want is exempt from the newly-blind re-look entirely "
          f"-- expected exactly 1 look() call, got {scr.calls}")
    check(len(_slept) == 0, f"no re-look means no sleep; got {_slept!r}")

    # =====================================================================
    print("(b) CONTROL: a NON-want slot that stays blind through the whole "
          "bounded re-look window is still refused -- the exemption is "
          "narrow, not blanket")
    # =====================================================================
    # I-63: the bound is now ic._STRAY_RELOOK_MAX_ATTEMPTS looks past the
    # first (agent_progress/issues/I-63/measure.py), not a single re-look --
    # ScriptedLook repeats its last entry past the end of the script, so a
    # 2-entry script still exercises "stays blind for every attempt".
    _slept.clear()
    want = {2}
    # slot 2 (the target) is genuinely selected and readable throughout; slot 0
    # is a stray that goes blind and never recovers, exactly I-26's own case (d).
    look1 = (_flat_glow({2}), [None, REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    look2 = (_flat_glow({2}), [None, REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])
    scr = ScriptedLook([look1, look2])
    ok = ic._clear_strays(want, scr.look, blind_before=set())
    check(ok is False, f"a NON-want slot that stays blind through the whole "
          f"re-look window must still refuse; got {ok!r}")
    _expected_calls = 1 + ic._STRAY_RELOOK_MAX_ATTEMPTS
    check(scr.calls == _expected_calls, f"the first look plus every bounded "
          f"re-look, none of them recovering -- expected {_expected_calls}, "
          f"got {scr.calls} look() calls")
    check(len(_slept) == ic._STRAY_RELOOK_MAX_ATTEMPTS
          and all(abs(s - ic.SELECT_RETRY_CONFIRM_SEC) < 1e-9 for s in _slept),
          f"every sleep must be SELECT_RETRY_CONFIRM_SEC ({ic.SELECT_RETRY_CONFIRM_SEC}), "
          f"{ic._STRAY_RELOOK_MAX_ATTEMPTS} of them; got {_slept!r}")

    # =====================================================================
    print("(c) an inferred-selected target next to a genuinely lifted NON-want "
          "stray (a real risen y) -- the stray is still caught, not masked")
    # =====================================================================
    want = {1}
    ys0 = [REST[0], REST[1], REST[2], REST[3], REST[4]]
    # slot 1 (the target) is blind, inferred selected -- realistic production
    # shape: selected_cards() abstains on it too (it is not in `sel`), so this
    # exercises the commit-gate inference, not just the early-refusal exemption.
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
        ok = ic._clear_strays(want, _look_c, blind_before=set(), ys0=ys0)
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
    # Baseline: BOTH targets were readable before this operation pressed
    # anything -- the proof the inference in (2) requires.
    ys0 = [REST[0], REST[1], REST[2], REST[3], REST[4]]
    # Neither target's disc reads now (both freshly lifted); neither is in
    # `sel` either, the realistic production shape -- the commit gate must
    # accept both from the baseline-proven inference alone, no stray left over.
    ys = [REST[0], None, REST[2], None, REST[4]]

    def _look_d():
        return _flat_glow({1, 3}), list(ys), N, []

    ok = ic._clear_strays(want, _look_d, blind_before=set(), ys0=ys0)
    check(ok is True, f"both inferred-selected targets, both blind, neither in "
          f"`sel` -- must still commit; got {ok!r}")
    check(len(_slept) == 0, f"neither target is a newly-blind stray, so no "
          f"re-look and no sleep; got {_slept!r}")

    # =====================================================================
    print("(e) an inferred-selected target beside a NON-want slot that was "
          "ALREADY occluded at baseline (never lifted) -- commits, and the "
          "occluded slot is never walked to or deselected")
    # =====================================================================
    _slept.clear()
    want = {1}
    # slot 0 is occluded from the very start (CLAUDE.md 10.28 shape) -- its
    # baseline glow is a bogus on-card reading, exactly I-26's own case (b),
    # and it never becomes readable. slot 1 (the target) is readable at
    # baseline and goes blind the moment it selects (I-21).
    glow0 = _flat_glow({1})
    glow0[0] = 68.6                          # > CURSOR_GLOW_MAX -- untrustworthy
    ys0 = [259, REST[1], REST[2], REST[3], REST[4]]
    blind0 = ic._untrustworthy_slots(glow0, ys0)
    check(0 in blind0, f"slot 0's baseline glow (68.6) must be flagged "
          f"untrustworthy from the start; got {blind0!r}")
    check(1 not in blind0, f"slot 1 must be TRUSTWORTHY at baseline -- it is "
          f"the target the inference in (2) depends on being readable there; "
          f"got {blind0!r}")

    walked = []
    deselected = []
    _old_walk2 = ic._walk_cursor_to
    _old_deselect = ic._deselect_verified
    ic._walk_cursor_to = lambda target, look: (walked.append(target), (True, []))[1]
    ic._deselect_verified = lambda target, look: (deselected.append(target), (True, []))[1]

    def _look_e():
        # slot 0 stays occluded (None) throughout; slot 1 is blind (selected).
        return _flat_glow({1}), [None, None, REST[2], REST[3], REST[4]], N, []

    try:
        ok = ic._clear_strays(want, _look_e, blind_before=blind0, ys0=ys0)
    finally:
        ic._walk_cursor_to = _old_walk2
        ic._deselect_verified = _old_deselect
    check(ok is True, f"an inferred target beside a chronically-occluded "
          f"non-want slot must still commit; got {ok!r}")
    check(0 not in walked, f"the occluded slot must NEVER be walked to -- it "
          f"was never counted as lifted, so it is not a stray to clear; "
          f"walked={walked!r}")
    check(0 not in deselected, f"the occluded slot must NEVER be deselected; "
          f"deselected={deselected!r}")
    check(len(_slept) == 0, f"slot 0 is exempt via blind_before and slot 1 via "
          f"want -- neither triggers a re-look; got {_slept!r}")

    # =====================================================================
    print("(f) the engine's own target was ALREADY blind at baseline (never "
          "proven selected) and stays blind, never in `sel` -- refused")
    # =====================================================================
    want = {1}
    # slot 1 is occluded from the START -- the same shape as slot 0 in (e),
    # but this time it IS `want`. Nothing ever proved it was toggled on: it
    # could be a chronic occlusion the engine happened to pick, not a landed
    # select. The commit must not take that on faith.
    glow0 = _flat_glow()
    ys0 = [REST[0], None, REST[2], REST[3], REST[4]]
    blind0 = ic._untrustworthy_slots(glow0, ys0)
    check(1 in blind0, f"slot 1 must be flagged untrustworthy at baseline (its "
          f"own y is None); got {blind0!r}")

    def _look_f():
        return _flat_glow(), [REST[0], None, REST[2], REST[3], REST[4]], N, []

    ok = ic._clear_strays(want, _look_f, blind_before=blind0, ys0=ys0)
    check(ok is False, f"a target blind at baseline AND blind now, never seen "
          f"in `sel`, must refuse -- nothing ever proved it was selected; "
          f"got {ok!r}")
finally:
    ic.time.sleep = _old_sleep

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the engine's own blind target(s) commit only when proven readable at "
      "baseline, a non-want stray that stays blind is still refused, a real "
      "stray beside an inferred-selected target is still caught, a "
      "chronically-occluded non-want slot is never walked to or deselected, "
      "and a target blind at baseline with no proof of selection is refused")
