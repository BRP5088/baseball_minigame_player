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

    # =====================================================================
    # ROUND 2 -- an independent Opus skeptic REFUTED the round-1 fix
    # (agent_progress/issues/I-43-44/skeptic.md). Three findings, S-1
    # (BLOCKING) through S-3, plus two of the skeptic's own four mutants
    # (M3, M4) survived round-1's suite unnoticed. All five are covered
    # below, each against the REAL, unmodified functions.
    # =====================================================================
    print("(S-1) SKEPTIC (BLOCKING): a target verified by a REAL geometric "
          "read (not I-21's inference), then blind at commit -- must COMMIT, "
          "not refuse. Round-1 marked ONLY the inference branch; reproduced "
          "against overnight/run_live_*.log in the main checkout: 10 of 34 "
          "archived want-blind commits (29%) would have refused, every one "
          "a legitimate play already committed and won (e.g. "
          "run_live_20260921q.log:326-330 -> WIN #62).")
    # =====================================================================
    ic.clear_maybe_lifted()

    # (a) "already selected" -- target in `before`, _select_verified's very
    # first check, no press sent at all.
    def _look_s1a():
        return (_flat_glow({2}),
                [REST[0], REST[1], REST[2] - 44, REST[3], REST[4]], N, [2])

    ok_s1a, sel_s1a = ic._select_verified(2, _look_s1a)
    check("(S-1a) an already-selected real read must succeed", ok_s1a is True)
    check("(S-1a) must carry real corroboration for slot 2",
          getattr(sel_s1a, "inferred", frozenset()) == {2})

    def _look_s1a_commit():
        # blind at commit time -- the disc lost its dark edge, I-21's own
        # stated premise ("selecting a card is what blinds its own disc").
        return _flat_glow({2}), [REST[0], REST[1], None, REST[3], REST[4]], N, []

    ok_s1a_commit = ic._clear_strays(
        {2}, _look_s1a_commit, blind_before=set(),
        ys0=[REST[0], REST[1], REST[2], REST[3], REST[4]],
        inferred_targets=getattr(sel_s1a, "inferred", frozenset()))
    check("(S-1a) must COMMIT -- pre-round-2 this refused", ok_s1a_commit is True)

    # (b) an ordinary select_card press that LANDS IMMEDIATELY (attempt 1) --
    # the commonest case, and the one _select_verified prints NOTHING for
    # (the archived logs' own "verified on N after K press(es)" line is the
    # WALK's print, not the select's -- see the QA6 skeptic's own log read).
    _sent_s1b = []
    ic.press = lambda key: _sent_s1b.append(key)
    try:
        def _look_s1b():
            if not _sent_s1b:
                return (_flat_glow(),
                        [REST[0], REST[1], REST[2], REST[3], REST[4]], N, [])
            return (_flat_glow({1}),
                    [REST[0], REST[1] - 44, REST[2], REST[3], REST[4]], N, [1])

        ok_s1b, sel_s1b = ic._select_verified(1, _look_s1b)
    finally:
        ic.press = _real_press
    check("(S-1b) an immediate real-read landing must succeed", ok_s1b is True)
    check("(S-1b) must carry real corroboration for slot 1",
          getattr(sel_s1b, "inferred", frozenset()) == {1})

    def _look_s1b_commit():
        return _flat_glow({1}), [REST[0], None, REST[2], REST[3], REST[4]], N, []

    ok_s1b_commit = ic._clear_strays(
        {1}, _look_s1b_commit, blind_before=set(),
        ys0=[REST[0], REST[1], REST[2], REST[3], REST[4]],
        inferred_targets=getattr(sel_s1b, "inferred", frozenset()))
    check("(S-1b) must COMMIT -- the commonest real-read shape, previously "
          "unmarked and the source of all 10 archived would-refuse events",
          ok_s1b_commit is True)

    # =====================================================================
    print("(S-2) SKEPTIC: _unwind_selection's own SUCCESS path ('if not "
          "extra: return True') must mark a slot that is lifted AND BLIND "
          "-- `extra` is computed from `sel` (risen rows only) and can "
          "never see it, so this function used to return True having put "
          "NOTHING down and proved NOTHING")
    # =====================================================================
    ic.clear_maybe_lifted()

    def _look_s2():
        # slot 3 is blind (None) and NOT in sel -- lifted-and-blind, the
        # exact row `extra` cannot see.
        return _flat_glow(), [REST[0], REST[1], REST[2], None, REST[4]], N, []

    ys0_s2 = [REST[0], REST[1], REST[2], REST[3], REST[4]]
    unwind_ok_s2 = ic._unwind_selection(set(), _look_s2, {3}, ys0=ys0_s2)
    check("(S-2) _unwind_selection still reports SUCCESS (extra was empty, "
          "correctly -- there was nothing it could walk to and put down)",
          unwind_ok_s2 is True)
    check("(S-2) but the lifted-and-blind slot must now be tracked",
          3 in ic._MAYBE_LIFTED)

    ok_s2_next = ic._clear_strays(
        {1}, lambda: (_flat_glow({1}),
                       [REST[0], None, REST[2], None, REST[4]], N, [1]),
        blind_before={3}, ys0=[REST[0], REST[1], REST[2], None, REST[4]])
    check("(S-2) the NEXT operation must refuse with the stray still up "
          "(chains into I-43, case (A)'s own shape)", ok_s2_next is False)

    print("(S-2 control) a CHRONICALLY occluded ours-slot (blind at THIS "
          "operation's own baseline too, never touched) must NOT be marked "
          "-- avoids reintroducing the I-26/I-28 deadlock on a card nobody "
          "ever lifted")
    ic.clear_maybe_lifted()
    ys0_s2c = [REST[0], REST[1], REST[2], None, REST[4]]  # already blind at ys0
    unwind_ok_s2c = ic._unwind_selection(set(), _look_s2, {3}, ys0=ys0_s2c)
    check("(S-2 control) unwind still reports success", unwind_ok_s2c is True)
    check("(S-2 control) a slot blind at ITS OWN operation baseline too "
          "must NOT be marked -- nothing proves WE lifted a chronic "
          "occlusion", 3 not in ic._MAYBE_LIFTED)

    # =====================================================================
    print("(S-3) SKEPTIC: _reconcile_maybe_lifted must not run on a read "
          "that saw nothing. _look_settled's failure return hands back the "
          "LAST bad frame's ys (real-looking numbers) with sel forced "
          "EMPTY -- both of _reconcile_maybe_lifted's conditions are then "
          "satisfied by construction, and the safety measure becomes the "
          "false proof")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({2})
    want_s3 = {1}
    _s3_calls = {"n": 0}

    def _look_s3():
        _s3_calls["n"] += 1
        if _s3_calls["n"] == 1:
            # top-level look: slot 1 (want) genuinely selected; slot 2 a
            # real stray, risen -- must be walked-to and cleared.
            return (_flat_glow({1, 2}),
                    [REST[0], REST[1] - 44, REST[2] - 44, REST[3], REST[4]],
                    N, [1, 2])
        # every call after that (the post-clear re-check) reports an
        # UNREADABLE fan; _look_settled retries LOOK_RETRIES times and gives
        # up, handing back THIS ys (a real-looking number for slot 2) with
        # sel forced empty by its own failure path.
        return (_flat_glow(),
                [REST[0], REST[1] - 44, REST[2], REST[3], REST[4]], 3, [])

    _old_walk_s3 = ic._walk_cursor_to
    _old_deselect_s3 = ic._deselect_verified
    ic._walk_cursor_to = lambda target, look: (True, [])
    ic._deselect_verified = lambda target, look: (True, [])
    try:
        ok_s3 = ic._clear_strays(
            want_s3, _look_s3, blind_before=set(),
            ys0=[REST[0], REST[1], REST[2], REST[3], REST[4]])
    finally:
        ic._walk_cursor_to = _old_walk_s3
        ic._deselect_verified = _old_deselect_s3
    check("(S-3) refuses when the post-clear read cannot be settled",
          ok_s3 is False)
    check("(S-3) slot 2's mark must SURVIVE a read that saw nothing",
          2 in ic._MAYBE_LIFTED)

    # =====================================================================
    print("(M3) select_and_discard's confirm_discard-unverified exit (the "
          "counter never answers after the press) must mark card_index -- "
          "the skeptic's own M3 dropped this and nothing in round-1's "
          "suite noticed")
    # =====================================================================
    ic.clear_maybe_lifted()
    _sent_m3 = []
    ic.press = lambda key: _sent_m3.append(key)
    _old_walk_m3 = ic._walk_cursor_to
    _old_select_m3 = ic._select_verified
    _old_clear_m3 = ic._clear_strays
    ic._walk_cursor_to = lambda target, look: (True, [])
    _m3_sel = ic._InferredSel([2])
    _m3_sel.inferred = frozenset({2})
    ic._select_verified = lambda target, look: (True, _m3_sel)
    ic._clear_strays = lambda *a, **kw: True
    _discards_calls_m3 = {"n": 0}

    def _discards_look_m3():
        _discards_calls_m3["n"] += 1
        if _discards_calls_m3["n"] == 1:
            return 2                # the pre-press read: 2 discards left
        return None                 # every confirm-loop poll abstains

    try:
        ok_m3 = ic.select_and_discard(
            2, look=lambda: (_flat_glow(), list(REST), N, []),
            discards_look=_discards_look_m3)
    finally:
        ic.press = _real_press
        ic._walk_cursor_to = _old_walk_m3
        ic._select_verified = _old_select_m3
        ic._clear_strays = _old_clear_m3
    check("(M3) select_and_discard refuses (the counter never answered)",
          ok_m3 is False)
    check("(M3) confirm_discard was pressed", "confirm_discard" in _sent_m3)
    check("(M3) card_index must be marked maybe-lifted", 2 in ic._MAYBE_LIFTED)

    # =====================================================================
    print("(M4) SKEPTIC: the POST-CLEAR `_want_inferred` computation must "
          "apply the SAME corroboration gate as the pre-clear one -- "
          "dropping it from JUST the post-clear computation (the "
          "skeptic's own M4) lets an uncorroborated want-blind target "
          "commit whenever a real stray also needed clearing")
    # =====================================================================
    ic.clear_maybe_lifted()
    want_m4 = {1}
    ys0_m4 = [REST[0], REST[1], REST[2], REST[3], REST[4]]
    _m4_calls = {"n": 0}

    def _look_m4():
        _m4_calls["n"] += 1
        if _m4_calls["n"] == 1:
            # slot 1 (want) is blind, readable at baseline, not tactics --
            # but inferred_targets is explicitly empty below: nothing has
            # ever proven THIS operation selected it. Slot 2 is a genuine,
            # real stray that must be cleared, forcing the post-clear
            # computation to run at all.
            return (_flat_glow({2}),
                    [REST[0], None, REST[2] - 44, REST[3], REST[4]], N, [2])
        # post-clear: slot 2 is now down (deselected); slot 1 unchanged.
        return _flat_glow(), [REST[0], None, REST[2], REST[3], REST[4]], N, []

    _old_walk_m4 = ic._walk_cursor_to
    _old_deselect_m4 = ic._deselect_verified
    ic._walk_cursor_to = lambda target, look: (True, [])
    ic._deselect_verified = lambda target, look: (True, [])
    try:
        ok_m4 = ic._clear_strays(want_m4, _look_m4, blind_before=set(),
                                  ys0=ys0_m4, inferred_targets=set())
    finally:
        ic._walk_cursor_to = _old_walk_m4
        ic._deselect_verified = _old_deselect_m4
    check("(M4) an uncorroborated want-blind target must REFUSE even after "
          "a real stray was cleared", ok_m4 is False)
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
      "genuine geometric selection and a genuine real inference both still commit. "
      "ROUND 2 (skeptic REFUTED round 1): a target verified by a REAL read, then "
      "blind at commit, now commits instead of stalling (S-1, the blocking find); "
      "_unwind_selection's own success path marks a lifted-and-blind slot without "
      "deadlocking a genuine chronic occlusion (S-2); a post-clear read that saw "
      "nothing cannot clear a tracked mark (S-3); and both of the skeptic's "
      "surviving mutants (M3, M4) are now caught.")
