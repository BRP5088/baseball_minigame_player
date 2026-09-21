"""I-43 / I-44: two confirmed gaps on the play-commit path, both found by QA6's
finder reading `_clear_strays` against I-26/I-28/I-36's own accepted trade-offs
(`agent_progress/qa6/interactions/progress.md`, Q2 and Q4 -- read-only against the
real merged code, in the MAIN checkout). The finder's own `repro_q4_stray_
survives.py` / `repro_q2_false_inference_commits.py` scripts did not survive on
disk (only `progress.md` did); this file reconstructs both reproductions from the
finder's own precise write-up, driven against the real, unmodified
`input_controller` functions -- not a reimplementation.

I-43 (Q4). `_verified_select_and_play_inner`/`select_and_discard` capture their
baseline blind set ONCE, at the top, before any press. A stray card left LIFTED
by a PRIOR refused attempt whose `_unwind_selection` could not prove the board
clean ("cannot read the fan to unwind -- leaving the board as is") is genuinely
still up on the NEXT operation, and its slot reads unreadable at THAT operation's
own baseline too -- indistinguishable, from `blind_before` alone, from a card that
has been chronically occluded the whole hand and was never touched by anyone
(I-26/I-28's own accepted exemption, "refusing forever is how a hand with one
occluded card deadlocks"). `_MAYBE_LIFTED` (module state in `input_controller`,
reset by `orchestrator.reset_hand_memory()` at every hand-memory boundary) is the
missing memory: a slot an earlier operation could not prove clean is recorded
there, and `_clear_strays`'s baseline-blind exemption now refuses a slot in it
until a later read proves it POSITIONED (a real y) and NOT risen.

I-44 (Q2). `_clear_strays`'s own `_want_inferred` re-derives I-21's inference at
COMMIT time from nothing but `ys0`/`kinds0`/`blind_before` -- with no requirement
that `sel` (a real, geometric read) or `_select_verified`'s own retry loop ever
actually saw the target selected. A target that never lifts, ever, still commits
if it merely happens to read "readable at baseline, blind now, not tactics" --
which a dropped press plus a transient disc misread produce exactly as well as a
genuine lift does. The fix threads `inferred_targets` (which slot(s)
`_select_verified` itself concluded selected BY INFERENCE on this operation, via
a new `_InferredSel.inferred` attribute) into `_clear_strays`; a `want` slot blind
at commit time is now trusted only if it is in `sel` OR in `inferred_targets`.

Uses the same `check(name, cond)` shape requested for this file; verified it is
not reversed by (mutant iii below and) watching every case in this file both PASS
against HEAD and FAIL against a planted mutant before trusting it.
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


def _flat_glow(hot=()):
    g = [0.0] * N
    for i in hot:
        g[i] = 30.0
    return g


class LiftScreen:
    """Copied from test_select_stops_when_lift_unreadable.py's own harness: a
    resting fan whose lift-readability after selecting TARGET is controlled
    directly. Drives `_select_verified` for real, so its `_InferredSel` report
    is the genuine article, not a stand-in for it."""

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


def _dead_look():
    """A fan that never reads -- the shape _unwind_selection's own top branch
    ("cannot read the fan to unwind") and _clear_strays's top branch both
    exist for."""
    return [0.0] * N, [None] * N, 0, []


_real_press = ic.press
_old_sleep = ic.time.sleep
ic.time.sleep = lambda d: None

try:
    # =====================================================================
    print("(A) I-43 REPRODUCTION (QA6 Q4): a stray left lifted by a prior "
          "refused attempt whose _unwind_selection could not prove the board "
          "clean now survives a LATER operation's baseline-blind exemption "
          "-- must now REFUSE, not proceed")
    # =====================================================================
    ic.clear_maybe_lifted()
    check("_MAYBE_LIFTED starts empty", len(ic._MAYBE_LIFTED) == 0)

    # An earlier, unrelated attempt aimed at slot 3, got refused somewhere
    # upstream, and its own unwind could not even read the fan to try putting
    # slot 3 back down -- the literal "cannot read the fan to unwind" branch.
    unwind_ok = ic._unwind_selection(set(), _dead_look, {3})
    check("a fan-unreadable unwind must refuse", unwind_ok is False)
    check("and it must record slot 3 as maybe-lifted (I-43)",
          3 in ic._MAYBE_LIFTED)

    # THE NEXT OPERATION. Different target (slot 1), fresh baseline -- and at
    # THIS operation's own baseline, slot 3 STILL reads unreadable (it is
    # genuinely still lifted from before), so blind_before names it exactly
    # like a chronic occlusion would.
    ys0_a = [REST[0], REST[1], REST[2], None, REST[4]]
    blind0_a = ic._untrustworthy_slots(_flat_glow(), ys0_a)
    check("slot 3 reads blind at this operation's own baseline too",
          3 in blind0_a)

    def _look_a():
        # slot 1 (the target) is genuinely selected and in sel; slot 3 is
        # STILL blind, exactly as it was left -- never cleared, never
        # walked to by anyone since the failed unwind.
        return _flat_glow({1}), [REST[0], None, REST[2], None, REST[4]], N, [1]

    ok_a = ic._clear_strays({1}, _look_a, blind_before=blind0_a, ys0=ys0_a)
    check("the operation must REFUSE rather than commit with the old stray "
          "still up (pre-fix this returned True)", ok_a is False)

    # =====================================================================
    print("(B) I-44 REPRODUCTION (QA6 Q2): a target that never lifts, ever, "
          "must not commit purely on ys0/blind_before/kinds0 with no real "
          "corroboration ever offered")
    # =====================================================================
    ic.clear_maybe_lifted()
    want_b = {3}
    ys0_b = [REST[0], REST[1], REST[2], REST[3], REST[4]]  # readable at baseline

    def _look_b():
        # The card never lifts, ever: sel is permanently empty and slot 3's
        # own y reads None on every look this operation ever takes -- the
        # exact three facts (readable at baseline, blind now, not tactics)
        # the pre-I-44 inference asked for and nothing more.
        return _flat_glow(), [REST[0], REST[1], REST[2], None, REST[4]], N, []

    ok_b_permissive = ic._clear_strays(want_b, _look_b, blind_before=set(),
                                        ys0=ys0_b, inferred_targets=None)
    check("PRE-I-44 (inferred_targets=None) behaviour is UNCHANGED -- still "
          "commits on ys0/kinds0 alone, for every caller written before this",
          ok_b_permissive is True)

    ok_b_fixed = ic._clear_strays(want_b, _look_b, blind_before=set(),
                                   ys0=ys0_b, inferred_targets=set())
    check("I-44 FIX: with a caller reporting real inference (even an empty "
          "set), a target never seen selected must REFUSE", ok_b_fixed is False)

    # =====================================================================
    print("(control-a) a genuinely chronically-occluded NON-target slot "
          "(I-28's own live case) still passes the exemption -- I-43 must "
          "not touch a slot _MAYBE_LIFTED never named")
    # =====================================================================
    ic.clear_maybe_lifted()
    want_ca = {1}
    glow0 = _flat_glow({1})
    glow0[0] = 68.6                          # bogus on-card reading, untrustworthy
    ys0_ca = [259, REST[1], REST[2], REST[3], REST[4]]
    blind0_ca = ic._untrustworthy_slots(glow0, ys0_ca)
    check("slot 0 flagged untrustworthy at baseline", 0 in blind0_ca)

    walked_ca = []
    deselected_ca = []
    _old_walk_ca = ic._walk_cursor_to
    _old_deselect_ca = ic._deselect_verified
    ic._walk_cursor_to = lambda target, look: (walked_ca.append(target), (True, []))[1]
    ic._deselect_verified = lambda target, look: (
        deselected_ca.append(target), (True, []))[1]

    def _look_ca():
        return _flat_glow({1}), [None, None, REST[2], REST[3], REST[4]], N, []

    try:
        ok_ca = ic._clear_strays(want_ca, _look_ca, blind_before=blind0_ca,
                                  ys0=ys0_ca, inferred_targets={1})
    finally:
        ic._walk_cursor_to = _old_walk_ca
        ic._deselect_verified = _old_deselect_ca
    check("a target inferred-selected beside a chronically-occluded "
          "non-want slot still commits", ok_ca is True)
    check("the chronically-occluded slot is never walked to",
          0 not in walked_ca)
    check("the chronically-occluded slot is never deselected",
          0 not in deselected_ca)
    check("it was never marked maybe-lifted -- no one ever failed to prove "
          "it clean", 0 not in ic._MAYBE_LIFTED)

    # =====================================================================
    print("(control-b) a target selected and SEEN in `sel` commits, exactly "
          "as before -- no inference, no _MAYBE_LIFTED involvement at all")
    # =====================================================================
    ic.clear_maybe_lifted()
    want_cb = {2}

    def _look_cb():
        return _flat_glow({2}), [REST[0], REST[1], REST[2] - 44, REST[3], REST[4]], N, [2]

    ok_cb = ic._clear_strays(want_cb, _look_cb, blind_before=set())
    check("a genuinely, geometrically selected target commits", ok_cb is True)

    # =====================================================================
    print("(control-c) a target selected-by-inference IN _select_verified "
          "(driven for real) commits when threaded into _clear_strays")
    # =====================================================================
    ic.clear_maybe_lifted()
    s = LiftScreen(target=2)
    ic.press = s.press
    try:
        _g0, ys0_cc, _n0, _sel0 = s.look()
        ok_sel, sel_cc = ic._select_verified(2, s.look)
    finally:
        ic.press = _real_press
    check("_select_verified must land and report the target", ok_sel is True)
    inferred_cc = getattr(sel_cc, "inferred", frozenset())
    check("the real select step must have inferred slot 2 (its disc blinded "
          "on lift, exactly I-21's mechanism)", inferred_cc == {2})

    ok_cc = ic._clear_strays({2}, s.look, blind_before=set(), ys0=ys0_cc,
                              inferred_targets=inferred_cc)
    check("threading the REAL _select_verified inference into _clear_strays "
          "must commit", ok_cc is True)

    # =====================================================================
    print("(control-d) after a failed unwind, the NEXT attempt refuses "
          "until the slot reads down, then a LATER attempt commits")
    # =====================================================================
    ic.clear_maybe_lifted()
    unwind_ok_d = ic._unwind_selection(set(), _dead_look, {3})
    check("(d) the unwind must fail, exactly as in (A)", unwind_ok_d is False)
    check("(d) slot 3 recorded maybe-lifted", 3 in ic._MAYBE_LIFTED)

    ys0_d1 = [REST[0], REST[1], REST[2], None, REST[4]]
    blind0_d1 = ic._untrustworthy_slots(_flat_glow(), ys0_d1)

    def _look_d1():
        return _flat_glow({1}), [REST[0], None, REST[2], None, REST[4]], N, [1]

    ok_d1 = ic._clear_strays({1}, _look_d1, blind_before=blind0_d1, ys0=ys0_d1)
    check("(d) attempt 1 (slot 3 still blind) must refuse", ok_d1 is False)
    check("(d) slot 3 is still tracked after the refusal", 3 in ic._MAYBE_LIFTED)

    # LATER: slot 3 is now genuinely down -- a real y, and not risen (not in
    # sel). This is the read that proves it clean.
    def _look_d2():
        return (_flat_glow({1}),
                [REST[0], REST[1] - 44, REST[2], REST[3], REST[4]], N, [1])

    ok_d2 = ic._clear_strays({1}, _look_d2, blind_before=set())
    check("(d) attempt 2, slot 3 proven down, must commit", ok_d2 is True)
    check("(d) slot 3 must be cleared from _MAYBE_LIFTED once proven down",
          3 not in ic._MAYBE_LIFTED)
finally:
    ic.press = _real_press
    ic.time.sleep = _old_sleep
    ic.clear_maybe_lifted()

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  I-43: a stray left lifted by a prior refused attempt is refused until "
      "seen down, and a genuinely chronic occlusion nobody ever touched is still "
      "exempted. I-44: a commit-time inference now requires the select step's own "
      "real report, not a re-derivation from baseline snapshots alone, while a "
      "genuine geometric selection and a genuine real inference both still commit.")
