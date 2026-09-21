"""I-52: confirm_discard is verified once, immediately, and a late-landing
discard leaves its slot in _MAYBE_LIFTED.

Evidence: `run_live_20260921t.log` ~386-420 (main checkout). A discard was
decided, its confirm_discard press was not confirmed on the poll right after
it, and the FUNCTION GAVE UP -- it pressed exactly once and then only polled
the counter (never retried the press itself). A SECOND, separate discard
Decision was logged at line 392 (`_walk_cursor_to`'s print is gated `if
steps:`, and the cursor needed none, so that attempt's own press landed
SILENTLY), and discards_left fell one poll later. Because the discarded
slot's replacement card read UNKNOWN at that moment, the slot stayed in
`_MAYBE_LIFTED` and THREE SEPARATE plays were refused by the I-43 guard
("slot(s) [0] may still be physically lifted...") before hand_index 1 was
excluded and a worse card committed. 19 of 26 archived `discard NOT
CONFIRMED` lines across `overnight/run_live_2026092*.log` eventually landed,
via a later attempt, before play committed; 7 never landed at all
(`agent_progress/issues/I-52/discard_table.txt` has the full table and a
second breakdown: 21 of 26 reached confirm_discard at all, 5 refused earlier,
at the cursor/select step).

A second, independent false-refusal shape was found the same day in a PLAY
commit (not a discard): a card legitimately lifted for the play occludes its
UNSELECTED neighbour's own disc/badge read, so the neighbour reads unreadable
and gets marked by the commit guard's `_new_blind` path even though it was
never touched -- `diagnostics/deal_frames/refused_select_1790029942849538000/`
(main checkout), hand [swing+1, speed+1, 4/3, 4/3, 8/1], slot 1 (unselected,
next to selected slot 0) refused for 8 straight polls, excluding the best card
in the hand (the 8).

**A first fix for the second shape -- an adjacency exemption in
`_reconcile_maybe_lifted` -- was REFUTED by an independent skeptic**
(`agent_progress/issues/I-52/skeptic.md`): it cleared the mark on the
STRONGEST evidence this system makes (readable at baseline, blind after our
own press -- I-21's own lift signature), with no measurement separating it
from a genuine stray, and it WIDENED `ISSUES.md` I-48d (OPEN). It is gone.
The replacement, `resolve_neighbour_occlusion`, presses nothing blind: it
lowers the KNOWN-lifted neighbour, looks again, and only clears the mark on
what it actually SEES -- see cases F2-F4 below.

**IT IS NOW WIRED IN.** A second pass found the first one incomplete in
CLAUDE.md 10.1's own shape: a fix that is not wired in is dead code, and the
live deadlock (`run 21t` match 3: "may still be physically lifted" x8, every
batter excluded) was exactly as reachable as before. `_clear_strays`'s own
`_unproven` branch (input_controller.py's I-43 refusal site) now calls
`resolve_neighbour_occlusion` before refusing -- see cases H/I below, which
drive the change end to end through the REAL `_verified_select_and_play_
inner`, not a stub of it.

Fix, confined to `_MAYBE_LIFTED`/`_reconcile_maybe_lifted`/
`resolve_neighbour_occlusion`/`_clear_strays` and `select_and_discard`
(see ISSUES.md I-52):

  1. confirm_discard is now verified with `press_verified`, the same helper
     I-11 uses for every other commit press: it retries the PRESS, not just
     the read, but ONLY while a fresh look still shows the slot lifted AND the
     counter unchanged. The moment the slot stops reading lifted with the
     counter still unchanged, it refuses to press again rather than risk a
     second confirm_discard with nothing selected.
  2. `_reconcile_maybe_lifted` is UNCHANGED from its original "seen down"
     rule. A landed discard clears its OWN slot directly the moment
     discards_left proves it (`_prove_maybe_lifted_clean`), regardless of
     what the replacement card currently reads as -- a signal
     `_reconcile_maybe_lifted` cannot see at all, since it only takes
     `(ys, sel)`.
  3. `resolve_neighbour_occlusion(m_slot, t_slot, look)`: a bounded,
     press-and-look disambiguation for the neighbour-occlusion shape, now
     called from `_clear_strays` at the I-43 refusal site (cases F2-F4 test
     it standalone; cases H/I test the wiring end to end).

`def check(name, cond)` name-first, matching this suite.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import time as _time

import input_controller as ic

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok   {name}")
    else:
        fails.append(name)
        print(f"FAIL {name}  {detail}")


CARD = 2
REST = [200] * ic.MAX_HAND_SIZE


class DiscardRig:
    """Drives select_and_discard's confirm_discard step in isolation.

    `_walk_cursor_to`, `_select_verified` and `_clear_strays` are stubbed to
    succeed trivially (they are a DIFFERENT branch's territory -- I-52 is
    scoped to what happens from confirm_discard onward) so every press and
    every look this fixture sees is the confirm_discard verification itself.

    `land_on_attempt`: which confirm_discard press (1-based) actually lands
    -- None means it never does. `counts`: the exact script of discards_left
    values `discards_look()` returns, call by call, in the same order
    select_and_discard consumes them (an `iter`, exhausted raises -- a bug
    reading one call too many is a real bug, not something to paper over with
    a default).
    """

    def __init__(self, land_on_attempt, counts, redeal_unknown=True):
        self.land_on_attempt = land_on_attempt
        # press_verified's own observe() retries a None answer up to 6 times
        # (never the case here -- discards_look never abstains) and, more to
        # the point, `_look_settled` inside the ambiguity check can cost this
        # fixture an extra call it did not script for. Repeat the LAST scripted
        # value indefinitely rather than raising StopIteration on it -- a real
        # counter does not stop answering either, it just stops CHANGING.
        import itertools
        self._counts = itertools.chain(counts, itertools.repeat(counts[-1]))
        self._counts_consumed = 0
        self.redeal_unknown = redeal_unknown
        self.attempts = 0
        self.lifted = True
        self.sent = []

    def press(self, key, **kw):
        self.sent.append(key)
        if key == "confirm_discard":
            self.attempts += 1
            if self.land_on_attempt is not None and self.attempts == self.land_on_attempt:
                self.lifted = False

    def look(self):
        sel = [CARD] if self.lifted else []
        ys = list(REST)
        if not self.lifted and self.redeal_unknown:
            ys[CARD] = None
        glow = [0.0] * ic.MAX_HAND_SIZE
        return glow, ys, ic.MAX_HAND_SIZE, sel

    def discards_look(self):
        self._counts_consumed += 1
        return next(self._counts)


M_SLOT, T_SLOT = 1, 0


class NeighbourRig:
    """Drives resolve_neighbour_occlusion(M_SLOT, T_SLOT, look) in isolation.

    Models the cursor as always sitting on T_SLOT -- the only slot this
    function ever presses select_card against -- matching
    _deselect_verified/_select_verified's own contract: they toggle whatever
    the cursor already holds, no walking. `m_readable_when_t_down` decides
    which real-episode shape this is: True is occlusion (F2), False is a
    genuine stray (F3). `reraise_lands=False` models the re-raise itself
    being swallowed (F4).
    """

    def __init__(self, m_readable_when_t_down, deselect_lands=True, reraise_lands=True):
        self.t_lifted = True
        self.m_blind = True
        self.m_readable_when_t_down = m_readable_when_t_down
        self.deselect_lands = deselect_lands
        self.reraise_lands = reraise_lands
        self.sent = []

    def press(self, key, **kw):
        self.sent.append(key)
        if key != "select_card":
            return
        if self.t_lifted:
            if self.deselect_lands:
                self.t_lifted = False
                if self.m_readable_when_t_down:
                    self.m_blind = False
        else:
            if self.reraise_lands:
                self.t_lifted = True

    def look(self):
        sel = [T_SLOT] if self.t_lifted else []
        ys = list(REST)
        if self.m_blind:
            ys[M_SLOT] = None
        glow = [0.0] * ic.MAX_HAND_SIZE
        return glow, ys, ic.MAX_HAND_SIZE, sel


class HandRig:
    """Drives the REAL `_verified_select_and_play_inner` end to end, replaying
    the match-3 shape `resolve_neighbour_occlusion`'s own docstring names:
    hand [swing+1, speed+1, 4/3, 4/3, 8/1], card_index=4 (the 8/1 batter),
    tactics_index=0 (swing+1), slot 1 (speed+1) unreadable.

    Slot 0 starts the call ALREADY lifted -- standing in for whatever earlier
    partial attempt left it that way and marked slot 1 -- so THIS operation's
    own baseline (`_ys0`, read before it presses anything) already shows slot
    1 blind. That is what routes the mark through `_clear_strays`'s
    `_untouched_blind`/`_unproven` path (what this case exists to exercise)
    rather than the separate `_new_blind` "re-look" branch, which is for a
    slot that goes blind DURING an operation and is a different guard.

    `t0_lift_frees_m1`: True models OCCLUSION -- slot 1 reads the instant
    slot 0 comes back down (the COMMIT case, H). False models a GENUINE
    STRAY -- slot 1 stays blind no matter what (the REFUSE mirror, I).
    """

    def __init__(self, t0_lift_frees_m1):
        self.cursor = 2
        self.lifted = {0}
        self.t0_lift_frees_m1 = t0_lift_frees_m1
        self.confirmed = 0
        self.sent = []

    def press(self, key, **kw):
        self.sent.append(key)
        if key == "move_left":
            self.cursor = max(0, self.cursor - 1)
        elif key == "move_right":
            self.cursor = min(ic.MAX_HAND_SIZE - 1, self.cursor + 1)
        elif key == "select_card":
            if self.cursor in self.lifted:
                self.lifted.discard(self.cursor)
            else:
                self.lifted.add(self.cursor)
        elif key == "confirm_play":
            self.confirmed += 1

    def look(self):
        if self.confirmed:
            # A LANDED confirm_play takes the card out of the fan -- a gone
            # fan is a sentinel, not a five-row read (_verified_select_and_
            # play_inner's own comment on _fan_state).
            return [], [], 0, []
        glow = [0.0] * ic.MAX_HAND_SIZE
        glow[self.cursor] = 30.0
        ys = [200 + i for i in range(ic.MAX_HAND_SIZE)]
        m1_blind = (0 in self.lifted) if self.t0_lift_frees_m1 else True
        if m1_blind:
            ys[1] = None
        return glow, ys, ic.MAX_HAND_SIZE, sorted(self.lifted)


def _run_end_to_end():
    """Case (H): COMMIT. Case (I): the REFUSE mirror. Real function, real
    resolve_neighbour_occlusion, real _clear_strays -- only `press`/`look`
    are stubbed, through a rig that models the fan, not the guards."""
    old_press = ic.press
    try:
        ic.clear_maybe_lifted()
        ic._mark_maybe_lifted({1})
        rig_h = HandRig(t0_lift_frees_m1=True)
        ic.press = rig_h.press
        ok_h = ic._verified_select_and_play_inner(4, 0, rig_h.look)
        maybe_lifted_after_h = set(ic._MAYBE_LIFTED)

        ic.clear_maybe_lifted()
        ic._mark_maybe_lifted({1})
        rig_i = HandRig(t0_lift_frees_m1=False)
        ic.press = rig_i.press
        ok_i = ic._verified_select_and_play_inner(4, 0, rig_i.look)
        maybe_lifted_after_i = set(ic._MAYBE_LIFTED)
    finally:
        ic.press = old_press
        ic.clear_maybe_lifted()
    return ok_h, ok_i, rig_h, rig_i, maybe_lifted_after_h, maybe_lifted_after_i


def run_discard(rig):
    old_walk, old_select, old_clear = ic._walk_cursor_to, ic._select_verified, ic._clear_strays
    old_press = ic.press
    ic._walk_cursor_to = lambda target, look: (True, [])
    ic._select_verified = lambda target, look: (True, [])
    ic._clear_strays = lambda *a, **kw: True
    ic.press = rig.press
    try:
        return ic.select_and_discard(CARD, look=rig.look, discards_look=rig.discards_look)
    finally:
        ic._walk_cursor_to, ic._select_verified, ic._clear_strays = old_walk, old_select, old_clear
        ic.press = old_press


_real_sleep = _time.sleep
try:
    _time.sleep = lambda *a, **k: None

    # =====================================================================
    print("(A) confirm_discard press dropped, retry lands")
    # =====================================================================
    ic.clear_maybe_lifted()
    # PRE-MARKED: a prior operation on this same slot could not prove it
    # clean (I-43), so the success path below must clear it, not merely leave
    # an already-empty set alone.
    ic._mark_maybe_lifted({CARD})
    rig = DiscardRig(land_on_attempt=2, counts=[2, 2, 1])
    ok = run_discard(rig)
    check("(A) a dropped press that a retry lands is reported ok", ok is True, str(ok))
    check("(A) exactly 2 confirm_discard presses were sent",
          rig.sent.count("confirm_discard") == 2, str(rig.sent))
    check("(A) confirm_play is never sent by a discard",
          "confirm_play" not in rig.sent, str(rig.sent))
    check("(A) the PRE-MARKED slot is cleared by the proven landing",
          CARD not in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))

    # =====================================================================
    print("(B) the press lands but discards_left reads ONE POLL LATE -- the "
          "exact run_live_20260921t.log:386-397 shape")
    # =====================================================================
    ic.clear_maybe_lifted()
    # attempt 1 lands (lifted -> False), but the FIRST post-press poll still
    # reads the stale count -- discards_look never gets a THIRD call, because
    # press_verified must stop rather than press again with nothing selected.
    rig = DiscardRig(land_on_attempt=1, counts=[2, 2])
    ok = run_discard(rig)
    check("(B) an ambiguous late-landing read is UNVERIFIED, not success",
          ok is False, str(ok))
    check("(B) exactly ONE confirm_discard press was sent -- no blind retry "
          "with nothing selected",
          rig.sent.count("confirm_discard") == 1, str(rig.sent))
    check("(B) confirm_play is never sent", "confirm_play" not in rig.sent, str(rig.sent))
    check("(B) the slot is marked, pending proof", CARD in ic._MAYBE_LIFTED,
          str(ic._MAYBE_LIFTED))
    # THE NEXT POLL. A later, settled read (the replacement card has now
    # resolved) reconciles the mark on the ORIGINAL "seen down" rule, with no
    # new machinery -- exactly what happens in production the poll after.
    settled_ys = list(REST)
    ic._reconcile_maybe_lifted(settled_ys, [])
    check("(B) the next play is not refused once the slot settles",
          CARD not in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))

    # =====================================================================
    print("(C) every retry is dropped -- the safe direction is unchanged")
    # =====================================================================
    ic.clear_maybe_lifted()
    rig = DiscardRig(land_on_attempt=None, counts=[2, 2, 2, 2, 2, 2])
    ok = run_discard(rig)
    check("(C) a discard that never lands is UNVERIFIED", ok is False, str(ok))
    check("(C) it retried up to PRESS_VERIFY_TRIES presses",
          rig.sent.count("confirm_discard") == ic.PRESS_VERIFY_TRIES,
          str(rig.sent))
    check("(C) confirm_play is never sent", "confirm_play" not in rig.sent, str(rig.sent))
    check("(C) the slot stays marked", CARD in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))
    # THE NEXT POLL, STILL STUCK: nothing settled and nothing is adjacent to
    # it -- the mark must survive exactly as it does live.
    ic._reconcile_maybe_lifted([200, 200, None, 200, 200], [])
    check("(C) the next play IS still refused -- an unresolved discard must "
          "not be waved through", CARD in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))

    # =====================================================================
    print("(D) discards_left proving a mark clears it directly, whatever the "
          "replacement currently reads as")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({CARD})
    check("(D) starts marked", CARD in ic._MAYBE_LIFTED)
    ic._prove_maybe_lifted_clean({CARD})
    check("(D) discards_left proof clears it directly, no position read needed",
          CARD not in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))
    # AND THE SUCCESS PATH ABOVE USES IT: a mutant that drops the
    # _prove_maybe_lifted_clean call from select_and_discard's own landed
    # branch would leave (A)'s slot marked despite a proven, measured drop --
    # already asserted above, restated here as the direct claim this case is
    # named for.
    ic.clear_maybe_lifted()
    # PRE-MARKED, so the clear below is a real assertion and not a trivial
    # "it was never marked to begin with" -- a mutant dropping
    # _prove_maybe_lifted_clean from the success path must fail HERE.
    ic._mark_maybe_lifted({CARD})
    rig = DiscardRig(land_on_attempt=1, counts=[2, 1])
    ok = run_discard(rig)
    check("(D) a landed discard commits AND clears its own PRE-MARKED slot",
          ok is True and CARD not in ic._MAYBE_LIFTED,
          f"ok={ok} marked={ic._MAYBE_LIFTED}")

    # =====================================================================
    print("(E) I-26/I-28 control: an untracked, chronically occluded slot is "
          "neither created nor blocked by any of this")
    # =====================================================================
    ic.clear_maybe_lifted()
    # A slot nothing ever marked, unreadable, with nothing selected next to
    # it -- reconciliation must not conjure a mark out of it.
    ic._reconcile_maybe_lifted([200, None, 200, 200, 200], [])
    check("(E) reconcile never MARKS a slot, only ever clears one",
          ic._MAYBE_LIFTED == set(), str(ic._MAYBE_LIFTED))

    # =====================================================================
    print("(F2) resolve_neighbour_occlusion: M reads once T is lowered -- "
          "occlusion proven, not guessed; T re-raised")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({M_SLOT})
    rig = NeighbourRig(m_readable_when_t_down=True)
    _old_press = ic.press
    ic.press = rig.press
    try:
        ok, detail = ic.resolve_neighbour_occlusion(M_SLOT, T_SLOT, rig.look)
    finally:
        ic.press = _old_press
    check("(F2) ok=True: the occlusion was proven by lowering T", ok is True, detail)
    check("(F2) M's mark is cleared", M_SLOT not in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))
    check("(F2) T ends back up (re-raised)", rig.t_lifted is True, str(rig.t_lifted))
    check("(F2) exactly 2 select_card presses -- one lower, one re-raise",
          rig.sent.count("select_card") == 2, str(rig.sent))

    # =====================================================================
    print("(F3) resolve_neighbour_occlusion: M is STILL blind with T down -- "
          "a genuine stray, refused, T left down, nothing re-raised")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({M_SLOT})
    rig = NeighbourRig(m_readable_when_t_down=False)
    _old_press = ic.press
    ic.press = rig.press
    try:
        ok, detail = ic.resolve_neighbour_occlusion(M_SLOT, T_SLOT, rig.look)
    finally:
        ic.press = _old_press
    check("(F3) ok=False: T's lift was not the explanation", ok is False, detail)
    check("(F3) M's mark SURVIVES -- a genuine stray, now with evidence",
          M_SLOT in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))
    check("(F3) T is left DOWN -- nothing here re-raises a genuine stray's "
          "neighbour", rig.t_lifted is False, str(rig.t_lifted))
    check("(F3) exactly 1 select_card press -- the lower only, no re-raise "
          "attempt (bounded: no loop chasing a stray)",
          rig.sent.count("select_card") == 1, str(rig.sent))

    # =====================================================================
    print("(F4) resolve_neighbour_occlusion: the re-raise of T itself fails "
          "-- refused, T left down, nothing committed")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({M_SLOT})
    rig = NeighbourRig(m_readable_when_t_down=True, reraise_lands=False)
    _old_press = ic.press
    ic.press = rig.press
    try:
        ok, detail = ic.resolve_neighbour_occlusion(M_SLOT, T_SLOT, rig.look)
    finally:
        ic.press = _old_press
    check("(F4) ok=False: T would not come back up", ok is False, detail)
    check("(F4) T is left DOWN -- nothing partially lifted for a caller to "
          "mistakenly commit", rig.t_lifted is False, str(rig.t_lifted))
    check("(F4) exactly 6 select_card presses -- 1 lower + SELECT_ATTEMPTS "
          "failed re-raises, no more",
          rig.sent.count("select_card") == 1 + ic.SELECT_ATTEMPTS, str(rig.sent))

    # =====================================================================
    print("(G) I-43 TRUE POSITIVE: an isolated stray, nothing selected beside "
          "it, must still be refused")
    # =====================================================================
    ic.clear_maybe_lifted()
    ic._mark_maybe_lifted({1})
    # slot 1 unreadable, nothing selected anywhere near it (or at all).
    ic._reconcile_maybe_lifted([180, None, 160, 165, 168], [])
    check("(G) a genuinely isolated stray SURVIVES reconciliation",
          1 in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))
    # AND survives even with a SELECTED slot elsewhere in the hand, as long as
    # it is not adjacent -- adjacency, not "anything is selected", is the gate.
    ic._reconcile_maybe_lifted([180, None, 160, 165, 168], [3])
    check("(G) ...and a non-adjacent selection does not rescue it either",
          1 in ic._MAYBE_LIFTED, str(ic._MAYBE_LIFTED))

    # =====================================================================
    print("(H)/(I) END TO END through the REAL _verified_select_and_play_inner "
          "-- resolve_neighbour_occlusion is now WIRED IN, not standalone")
    # =====================================================================
    ok_h, ok_i, rig_h, rig_i, marked_after_h, marked_after_i = _run_end_to_end()
    check("(H) the match-3 shape COMMITS: T lowered, slot 1 read, mark "
          "cleared, T re-raised, confirm once", ok_h is True, str(ok_h))
    check("(H) confirm_play pressed exactly once", rig_h.confirmed == 1,
          str(rig_h.sent))
    check("(H) slot 1's mark is cleared by the proven occlusion",
          1 not in marked_after_h, str(marked_after_h))
    check("(H) exactly 3 select_card presses -- raise 4, lower 0, re-raise 0 "
          "(tactics 0 was already up, so no press to raise it)",
          rig_h.sent.count("select_card") == 3, str(rig_h.sent))
    check("(H) both targets end up lifted", {0, 4} <= rig_h.lifted, str(rig_h.lifted))

    check("(I) the mirror -- slot 1 stays blind with T down -- REFUSES",
          ok_i is False, str(ok_i))
    check("(I) confirm_play is never sent", rig_i.confirmed == 0, str(rig_i.sent))
    check("(I) slot 1's mark SURVIVES -- a genuine stray, now with evidence",
          1 in marked_after_i, str(marked_after_i))
    check("(I) T (slot 0) is left DOWN by the failed disambiguation",
          0 not in rig_i.lifted, str(rig_i.lifted))
finally:
    _time.sleep = _real_sleep
    ic.clear_maybe_lifted()

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
