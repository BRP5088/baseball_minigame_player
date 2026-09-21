"""I-44 N-2 (QA6 Q2, RE-OPENED by the round-2 skeptic,
agent_progress/issues/I-43-44/skeptic.md, worktree agent-a44ed7de3382216c3):
round 2 fixed S-1 by marking `_InferredSel.inferred` on EVERY `_select_
verified` success path, which made `_clear_strays`'s `inferred_targets` gate
INERT in production (N-1) -- the inference is always its own corroboration.
QA6 Q2's original shape survives: "a dropped press plus a transient disc
misread" reads identically to a genuine lift, and nothing in `inferred_
targets` alone tells them apart.

Traced against the real, unmodified `_select_verified`/`_clear_strays` (not a
reimplementation) before writing anything: `selected_cards()` (local_hand.py)
requires `y is not None` and, for a non-tactics row, `y_from != "fallback"` --
i.e. a DISC-derived y. A target whose disc has gone blind is, by that same
requirement, exactly the row `selected_cards` abstains on. So candidate 1
(selection-lift geometry) is UNAVAILABLE for validating an inference at the
moment it needs validating -- the disc is blind by construction. That is
candidate 1 CLOSED, not merely difficult.

Candidate 2 (baseline comparison) is what `_clear_strays` already had --
`ys0[k] is not None`, now named `_baseline_readable` -- and tracing it end to
end shows it ALREADY refuses a target that was unreadable at this
OPERATION's own start (`ys0`), regardless of what `_select_verified`'s own
LATER look (taken after a walk, possibly after a sibling target's own
selection) believed. That is QA6 Q2's literal repro (`want={3}`, baseline
readable, `sel` permanently empty) reversed at the one axis that was never
tested: baseline UNREADABLE. This file pins that, previously untested and
therefore free for a mutant to remove unnoticed.

WHAT THIS DOES NOT CLOSE, and is not claimed to: a target genuinely readable
at `ys0`, genuinely selected, and then misread as blind by the same circle-
fit noise I-21 exists to tolerate (CLAUDE.md 10.26) is READ-IDENTICAL to QA6
Q2's false inference, and (control-c) below is the sibling file's own pinned
MUST-COMMIT for exactly that read shape -- it cannot be told apart with the
signals `_clear_strays` has. Closing it needs either a post-commit read (too
late to stop a wrong card; a detector, not a fix -- candidate 3) or per-row
digit corroboration threaded from `orchestrator.hand_cursor_look`, which is
out of this fix's scope (input_controller.py only).

Same harness shape as test_commit_refuses_unseen_strays.py: `check(name,
cond)`, `ic.time.sleep` patched to a no-op, `_select_verified` driven for
real via a small FakeScreen rather than stubbed, so a `.inferred`/`sel`
report is the genuine article.
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

fails = []


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


N = ic.MAX_HAND_SIZE
REST = [200, 160, 150, 165, 220]

_real_press = ic.press
_old_sleep = ic.time.sleep
ic.time.sleep = lambda d: None


class LiftScreen:
    """Copied from the sibling file's own harness (test_commit_refuses_
    unseen_strays.py / test_select_stops_when_lift_unreadable.py): a resting
    fan whose lift-readability after pressing TARGET is controlled directly.
    Drives `_select_verified` for real."""

    def __init__(self, target, unreadable_when_lifted=True):
        self.target = target
        self.y = list(REST)
        self.sent = []
        self.presses = 0
        self.unreadable_when_lifted = unreadable_when_lifted

    def is_lifted(self, i):
        return REST[i] - self.y[i] >= 25

    def selected(self):
        return [i for i, y in enumerate(self.y) if REST[i] - y >= 25]

    def press(self, key):
        self.sent.append(key)
        if key != "select_card":
            return
        self.presses += 1
        t = self.target
        if self.is_lifted(t):
            self.y[t] = REST[t]
        else:
            self.y[t] -= 44

    def look(self):
        glow = [0.0] * N
        ys = []
        blind = self.unreadable_when_lifted and self.is_lifted(self.target)
        for i in range(N):
            ys.append(None if (i == self.target and blind) else int(self.y[i]))
        sel = [i for i in self.selected() if not (i == self.target and blind)]
        return glow, ys, N, sel


def _flat_glow(hot=()):
    g = [0.0] * N
    for i in hot:
        g[i] = 30.0
    return g


try:
    # =====================================================================
    print("(A) target readable at baseline, press lands, disc goes blind -- "
          "inferred, committed. CONTROL: unchanged from the shipped S-1 fix.")
    # =====================================================================
    ic.clear_maybe_lifted()
    s_a = LiftScreen(target=2)
    ic.press = s_a.press
    try:
        _g0, ys0_a, _n0, _before0 = s_a.look()
        check("(A) baseline is readable before anything is pressed",
              ys0_a[2] is not None)
        ok_sel_a, sel_a = ic._select_verified(2, s_a.look)
    finally:
        ic.press = _real_press
    check("(A) _select_verified must land and report the target",
          ok_sel_a is True)
    check("(A) it must be the inference branch (disc blinded on lift, I-21)",
          getattr(sel_a, "inferred", frozenset()) == {2})

    ok_a = ic._clear_strays({2}, s_a.look, blind_before=set(), ys0=ys0_a,
                             inferred_targets=getattr(sel_a, "inferred", frozenset()))
    check("(A) readable-baseline inference still COMMITS", ok_a is True)

    # =====================================================================
    print("(B) target ALREADY blind at baseline, press DROPPED, nothing "
          "lifts -- must NOT be inferred, must REFUSE (the hole, closed).")
    # =====================================================================
    ic.clear_maybe_lifted()

    # (B1) driven through the REAL _select_verified: baseline blind means its
    # OWN pre-press guard refuses before ever sending a press.
    def _look_b1():
        return _flat_glow(), [REST[0], REST[1], None, REST[3], REST[4]], N, []

    sent_b1 = []
    ic.press = lambda key: sent_b1.append(key)
    try:
        ok_sel_b1, _sel_b1 = ic._select_verified(2, _look_b1)
    finally:
        ic.press = _real_press
    check("(B1) _select_verified refuses a baseline-blind target", ok_sel_b1 is False)
    check("(B1) and never presses select_card against it -- a TOGGLE pressed "
          "blind can put a landed card back down just as easily as select one",
          sent_b1 == [])

    # (B2) directly at _clear_strays: even a caller that (wrongly, or because
    # its own LATER look disagreed with this operation's `ys0`) reports the
    # slot as inferred must not be trusted -- ys0/`_baseline_readable` is the
    # backstop, not `inferred_targets` alone.
    ys0_b = [REST[0], REST[1], None, REST[3], REST[4]]     # ALREADY blind

    def _look_b2():
        # never lifts, ever -- sel permanently empty, slot 2 permanently None.
        return _flat_glow(), [REST[0], REST[1], None, REST[3], REST[4]], N, []

    ok_b2 = ic._clear_strays({2}, _look_b2, blind_before=set(), ys0=ys0_b,
                              inferred_targets={2})
    check("(B2) a want slot blind AT BASELINE TOO must refuse even when "
          "(wrongly) reported inferred", ok_b2 is False)

    # =====================================================================
    print("(C) target already blind at baseline (ys0), press LANDS and "
          "selected_cards shows the rise -- committed. Candidate 1 IS "
          "available here: the disc never went blind, so selected_cards "
          "answers directly, bypassing the ys0-gated inference entirely.")
    # =====================================================================
    ic.clear_maybe_lifted()
    # ys0 (this OPERATION's true start) shows slot 2 blind -- e.g. a sibling
    # target's own selection briefly occluded it, or it was mid-deal. By the
    # time _select_verified is actually called for slot 2, the occlusion has
    # cleared (its OWN fresh look sees it readable) -- exactly the disagreement
    # the "one unmarked exit" comment in _clear_strays already names.
    ys0_c = [REST[0], REST[1], None, REST[3], REST[4]]

    class RiseReadableScreen:
        """Unlike LiftScreen, the disc STAYS readable through the rise --
        the common case S-1's own docstring calls "the commonest case, an
        immediate attempt-1 landing" -- so selected_cards can answer for it
        directly, with no inference at all."""

        def __init__(self, target):
            self.target = target
            self.y = list(REST)

        def press(self, key):
            if key == "select_card":
                self.y[self.target] -= 44

        def look(self):
            sel = [i for i, y in enumerate(self.y) if REST[i] - y >= 25]
            return _flat_glow(sel), list(self.y), N, sel

    s_c = RiseReadableScreen(target=2)
    ic.press = s_c.press
    try:
        ok_sel_c, sel_c = ic._select_verified(2, s_c.look)
    finally:
        ic.press = _real_press
    check("(C) _select_verified lands", ok_sel_c is True)
    check("(C) it is a REAL read, not an inference (the disc stayed readable)",
          2 in sel_c)

    ok_c = ic._clear_strays({2}, s_c.look, blind_before=set(), ys0=ys0_c,
                             inferred_targets=getattr(sel_c, "inferred", frozenset()))
    check("(C) commits via selected_cards directly, despite ys0 blind at "
          "this operation's own start", ok_c is True)

    # =====================================================================
    print("(D) I-26/I-28 regression: an untouched, chronically-occluded "
          "NON-want slot is still exempted, not marked, not unwound. The "
          "_baseline_readable extraction only touches _want_inferred, which "
          "_untouched_blind's chronic-occlusion exemption never reads.")
    # =====================================================================
    ic.clear_maybe_lifted()
    want_d = {1}
    ys0_d = [None, REST[1], REST[2], REST[3], REST[4]]      # slot 0 chronic
    blind0_d = ic._untrustworthy_slots(_flat_glow(), ys0_d)
    check("(D) slot 0 is untrustworthy at baseline", 0 in blind0_d)

    walked_d = []
    _old_walk_d = ic._walk_cursor_to
    ic._walk_cursor_to = lambda target, look: (walked_d.append(target), (True, []))[1]
    try:
        def _look_d():
            return _flat_glow({1}), [None, None, REST[2], REST[3], REST[4]], N, []

        ok_d = ic._clear_strays(want_d, _look_d, blind_before=blind0_d, ys0=ys0_d,
                                 inferred_targets={1})
    finally:
        ic._walk_cursor_to = _old_walk_d
    check("(D) a target beside a chronically-occluded non-want slot still "
          "commits", ok_d is True)
    check("(D) the chronically-occluded slot is never walked to", 0 not in walked_d)
    check("(D) it was never marked maybe-lifted", 0 not in ic._MAYBE_LIFTED)

finally:
    ic.press = _real_press
    ic.time.sleep = _old_sleep

print()
if fails:
    print(f"FAILED {len(fails)}:")
    for f in fails:
        print(f"  - {f}")
    _sys.exit(1)
print("ALL PASS")
