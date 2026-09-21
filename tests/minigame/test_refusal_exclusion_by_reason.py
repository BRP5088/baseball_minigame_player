"""I-39: THE PLAY-REFUSAL EXCLUSION MUST BE KEYED ON THE SLOT AND WHY IT WAS
REFUSED, NOT ONLY ON THE EXACT HAND.

ISSUES.md I-39, live 2026-09-21 (overnight/run_live_20260921l.log, main checkout,
read-only). Hand "0: fielding_boost +1  1: 8/0  2: 6/0  3: 9/0  4: 6/0", slot 3's
POSITION could not be read (input_controller._select_verified's own "position is
unreadable" refusal -- I-38), refused PLAY_STALL_MAX times, and was excluded. Slot
1 (the 8) was played. On the NEXT turn a new card was dealt into slot 1 (read
UNKNOWN) and "hand_index [3] refused 3x running on this hand — excluded" fired
again: the exclusion's ONLY key was the hand's (kind, power, secondary, type)
identity, which never even looked at slot 1 -- I-27's own merge rule says a slot
missing from both sides is not a disagreement -- so slot 3 stayed excluded by an
accident of ANOTHER slot's readability, not because of anything about slot 3
itself.

The user's steer (2026-09-21 08:02): key the exclusion on the slot and its
REASON. "unreadable" (this slot's own POSITION could not be measured -- see
orchestrator._slot_position_readable) is a property of the SLOT: it persists for
as long as the slot itself reads unreadable, survives a genuine redeal elsewhere
in the hand, and clears the instant that slot is measured again -- whatever else
changed. Every other refusal ("transient": a dropped press, the wrong card
raised, a garbled fan) is a property of the ATTEMPT, not the slot, and keeps the
ORIGINAL behaviour: it clears on a genuine hand-identity change, same as before
I-39.

Four scenarios:

  (a) an UNREADABLE exclusion survives a GENUINE hand-identity change elsewhere
      in the hand (CLAUDE.md's own "readable slot disagreeing" shape,
      test_stall_identity_survives_flicker.py's control case) for as long as
      the excluded slot itself stays unreadable.
  (b) the same UNREADABLE exclusion is dropped the moment a poll shows that
      slot's position measured again -- with NO hand-identity change at all,
      which is the one thing the OLD (identity-only) code could never do.
  (c) a TRANSIENT exclusion (the slot's position WAS measured; refused for some
      other reason) keeps the pre-I-39 behaviour exactly: it survives while the
      hand is unchanged and clears on a genuine redeal.
  (d) CONTROL: fewer than PLAY_STALL_MAX refusals never excludes anything,
      whatever the reason would have been.

Section 5 drives the real `play_one_turn` end to end, reproducing the live
shape from the evidence above: slot 3 unreadable, refused 3x, excluded, slot 1
(the 8) played; next poll slot 1 is UNKNOWN (I-27) and slot 3 is STILL
unreadable -- the 6 is played, not the 9, because the exclusion is doing its
job generally now rather than by the old accident; then slot 3 finally reads
and the 9 (the correct, best card) is offered.

Mutation sensitivity (verified by hand, see agent_progress/issues/I-39/progress.md):
reverting play_excluded_slots to the pre-I-39, identity-only body (no reason,
no readability recheck) fails (a) and (b); hard-coding every exclusion's reason
to TRANSIENT fails (a); hard-coding every exclusion's reason to UNREADABLE
fails (c).
"""
import contextlib
import io
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from _run_harness import check, failures                             # noqa: E402
import orchestrator as o                                             # noqa: E402


def _reset():
    o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
    o._PLAY_STALL["sig"], o._PLAY_STALL["n"], o._PLAY_STALL["excluded"] = None, 0, frozenset()
    o._PLAY_STALL["reasons"] = {}


def _fake_grab_settle_regions(names):
    from PIL import Image
    return {n: Image.new("RGB", (4, 4), (0, 0, 0)) for n in names}


def _patch(saved, **fns):
    for _name, _fn in fns.items():
        saved[_name] = getattr(o, _name)
        setattr(o, _name, _fn)


def _unpatch(saved):
    for _name, _fn in saved.items():
        setattr(o, _name, _fn)


# A five-card hand shaped like the live evidence: a tactics card at 0, and four
# player cards at 1-4. `y_measured` is the exact field input_controller's own
# "position is unreadable" refusal checks (via hand_cursor_look's `_ys`) --
# see orchestrator._slot_position_readable's own docstring.
def _hand(power3=9, y3=False, power1=8, present1=True, power2=6, power4=5):
    cards = [
        {"kind": "tactics", "name": "fielding_boost", "type": "fielding_boost",
         "bonus": 1, "hand_index": 0, "y_measured": True},
        {"kind": "player", "name": None, "power": power2, "secondary": 0,
         "hand_index": 2, "y_measured": True},
        {"kind": "player", "name": None, "power": power3, "secondary": 0,
         "hand_index": 3, "y_measured": y3},
        {"kind": "player", "name": None, "power": power4, "secondary": 0,
         "hand_index": 4, "y_measured": True},
    ]
    if present1:
        cards.insert(1, {"kind": "player", "name": None, "power": power1,
                          "secondary": 0, "hand_index": 1, "y_measured": True})
    return cards


H_BASE = _hand()                       # slot 3 unreadable, everything else stock


# =============================================================================
# (a) UNREADABLE exclusion survives a GENUINE hand-identity change elsewhere
#     in the hand, for as long as the excluded slot itself stays unreadable.
# =============================================================================
_reset()
o.play_excluded_slots(H_BASE)
for _ in range(o.PLAY_STALL_MAX):
    o.note_play_refused()
check(o.play_stalled(H_BASE) is True,
      "setup: slot 3 must be stalled after PLAY_STALL_MAX refusals")
_reason_a = (o.PLAY_REFUSAL_UNREADABLE
             if not o._slot_position_readable(H_BASE, 3) else o.PLAY_REFUSAL_TRANSIENT)
check(_reason_a == o.PLAY_REFUSAL_UNREADABLE,
      "setup: slot 3's own position is unmeasured on H_BASE, so the inferred "
      f"reason must be 'unreadable', got {_reason_a!r}")
o.exclude_play_slot(3, _reason_a)
check(o.play_excluded_slots(H_BASE) == frozenset({3}),
      "setup: slot 3 must be excluded before the genuine-redeal check")

# A READABLE slot (2) now disagrees -- CLAUDE.md/test_stall_identity_survives_
# flicker.py's own definition of a genuine redeal, nothing to do with slot 3.
H_REDEAL = _hand(power2=7)             # slot 2: 6 -> 7, slot 3 still unreadable
check(o.play_excluded_slots(H_REDEAL) == frozenset({3}),
      "a slot excluded as UNREADABLE must survive a genuine redeal elsewhere "
      "in the hand -- it is a property of the slot's own readability, not of "
      "what else got dealt")
check(o.play_stalled(H_REDEAL) is False,
      "the fresh target's own count must start at 0 after the redeal, even "
      "though slot 3's exclusion itself survived it")


# =============================================================================
# (b) the SAME exclusion is dropped the instant a poll shows the slot measured
#     again -- with NO hand-identity change at all. The old, identity-only code
#     could never do this: slot 3's (kind, power, secondary, type) VALUE never
#     changes when it starts reading, only its readability does, so an
#     identity-only comparison sees no reason to reconsider it.
# =============================================================================
H_READS = _hand(y3=True)               # nothing but slot 3's readability changes
check(o.play_excluded_slots(H_READS) == frozenset(),
      "slot 3 must be un-excluded the instant it reads, with the hand "
      "otherwise identical to what excluded it")
check(o.play_stalled(H_READS) is False,
      "a freshly un-excluded slot must not carry over a stale refusal count")
check(3 not in o._PLAY_STALL["reasons"],
      "an un-excluded slot's reason must be forgotten too, not just its "
      f"membership: {o._PLAY_STALL['reasons']!r}")


# =============================================================================
# (c) a TRANSIENT exclusion (the slot's position WAS measured) keeps the
#     pre-I-39 behaviour: survives while the hand is unchanged, clears on a
#     genuine redeal.
# =============================================================================
_reset()
H_C = _hand(y3=True)                   # every slot readable -- refusal is NOT positional
o.play_excluded_slots(H_C)
for _ in range(o.PLAY_STALL_MAX):
    o.note_play_refused()
check(o.play_stalled(H_C) is True, "setup: slot 3 must be stalled on H_C")
_reason_c = (o.PLAY_REFUSAL_UNREADABLE
             if not o._slot_position_readable(H_C, 3) else o.PLAY_REFUSAL_TRANSIENT)
check(_reason_c == o.PLAY_REFUSAL_TRANSIENT,
      f"setup: slot 3 IS measured on H_C, so the reason must be 'transient', "
      f"got {_reason_c!r}")
o.exclude_play_slot(3, _reason_c)
check(o.play_excluded_slots(H_C) == frozenset({3}),
      "setup: slot 3 excluded (transient) before the persistence/clear checks")

# Unchanged hand: must still be excluded (matches the original I-03 behaviour).
check(o.play_excluded_slots(H_C) == frozenset({3}),
      "a TRANSIENT exclusion must survive polling the SAME hand again")

# A genuine redeal (a readable slot disagreeing) must clear it.
H_C_REDEAL = _hand(y3=True, power2=7)
check(o.play_excluded_slots(H_C_REDEAL) == frozenset(),
      "a TRANSIENT exclusion must clear on a genuine hand redeal, unlike an "
      "UNREADABLE one -- this is the pre-I-39 behaviour and must be unchanged")


# =============================================================================
# (d) CONTROL: fewer than PLAY_STALL_MAX refusals never excludes anything.
# =============================================================================
_reset()
o.play_excluded_slots(H_BASE)
for _i in range(o.PLAY_STALL_MAX - 1):
    o.note_play_refused()
    check(o.play_stalled(H_BASE) is False,
          f"stalled after only {_i + 1} refusal(s), before PLAY_STALL_MAX "
          f"({o.PLAY_STALL_MAX})")
check(o.play_excluded_slots(H_BASE) == frozenset(),
      "nothing may be excluded before PLAY_STALL_MAX refusals, whatever the "
      "reason would eventually be")


# =============================================================================
# (e) exclude_play_slot's `reason` parameter defaults to TRANSIENT, so every
#     pre-I-39 caller (a bare `exclude_play_slot(idx)`) keeps its old meaning.
# =============================================================================
_reset()
o.play_excluded_slots(H_BASE)
for _ in range(o.PLAY_STALL_MAX):
    o.note_play_refused()
o.exclude_play_slot(3)                 # no reason given -- must be TRANSIENT
check(o._PLAY_STALL["reasons"].get(3) == o.PLAY_REFUSAL_TRANSIENT,
      f"exclude_play_slot with no reason must default to TRANSIENT (the "
      f"pre-I-39 behaviour), got {o._PLAY_STALL['reasons'].get(3)!r}")
check(o.play_excluded_slots(_hand(power2=7)) == frozenset(),
      "a default (TRANSIENT) exclusion must still clear on a genuine redeal")


# =============================================================================
# 5. END TO END, through the REAL play_one_turn, reproducing the live shape:
#    slot 3 unreadable -> refused 3x -> excluded -> slot 1 (8) played; next
#    poll slot 1 is UNKNOWN (I-27) and slot 3 is STILL unreadable -> the 6
#    (slot 2) is played, not the 9; then slot 3 finally reads -> the 9 is
#    offered.
# =============================================================================
_reset()

STATE_5 = {"phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
           "discards_left": 0}

_play_calls_5 = []
_calls_to_3 = [0]


def _fake_select_and_play_5(player_idx, tactics_idx, look=None):
    _play_calls_5.append(player_idx)
    if player_idx == 3:
        # The FIRST PLAY_STALL_MAX attempts at slot 3 refuse -- its position
        # is unreadable, exactly like the live evidence. Once it has been
        # excluded and offered again (only possible once it reads), a press
        # at it succeeds like any other card.
        _calls_to_3[0] += 1
        return _calls_to_3[0] > o.PLAY_STALL_MAX
    return True


_saved = {}
_patch(_saved, select_and_play=_fake_select_and_play_5,
       _grab_settle_regions=_fake_grab_settle_regions)
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        # Turn 1: refuse slot 3 three times, then slot 1 (the 8) plays.
        _turn1_results = []
        for _attempt in range(6):
            _turn1_results.append(o.play_one_turn(dict(STATE_5, hand=H_BASE), 0))
            if _turn1_results[-1][0]:
                break
        # Turn 2: slot 1 is gone (I-27: a flickered/redealt UNKNOWN card is
        # DROPPED from `hand`, never present with a null value), slot 3 is
        # STILL unreadable.
        H_TURN2 = _hand(present1=False, y3=False)
        _turn2_result = o.play_one_turn(dict(STATE_5, hand=H_TURN2), 0)
        # Turn 3: slot 3 finally reads. Nothing else about the hand changed.
        H_TURN3 = _hand(present1=False, y3=True)
        _turn3_result = o.play_one_turn(dict(STATE_5, hand=H_TURN3), 0)
finally:
    _unpatch(_saved)
_log5 = _buf.getvalue()

check(_play_calls_5[:3] == [3, 3, 3],
      f"turn 1 must retry slot 3 (the best card) exactly PLAY_STALL_MAX times "
      f"before falling back: {_play_calls_5!r}")
check(_play_calls_5[3] == 1,
      f"turn 1 must fall back to slot 1 (power 8, the next best) once slot 3 "
      f"is excluded: {_play_calls_5!r}")
check(_turn1_results[-1] == (True, None) or _turn1_results[-1][0] is True,
      f"turn 1 must end in a confirmed play: {_turn1_results[-1]!r}")
check("excluded as unreadable" in _log5,
      "the log must name slot 3's exclusion as unreadable:\n" + _log5)

check(_turn2_result[0] is True,
      f"turn 2 must confirm a play (the best AVAILABLE card): {_turn2_result!r}")
check(_play_calls_5[4] == 2,
      f"turn 2 must play slot 2 (power 6) -- slot 3 (the 9) must STILL be "
      f"excluded (still unreadable) and slot 1 is gone: {_play_calls_5!r}")
check(3 not in _play_calls_5[3:5],
      f"slot 3 must never be re-targeted (turn 1's fallback play or turn 2's "
      f"play) while it is still unreadable, whatever else changed in the "
      f"hand: {_play_calls_5!r}")

check(_turn3_result[0] is True,
      f"turn 3 must confirm a play: {_turn3_result!r}")
check(_play_calls_5[5] == 3,
      f"turn 3 must offer slot 3 (the 9, the best card) again now that it "
      f"reads -- this is I-39's whole point: {_play_calls_5!r}")
check("reads again" in _log5,
      "the log must name slot 3 being re-offered once it reads:\n" + _log5)


# =============================================================================
# 6. END TO END, THE TRANSIENT MIRROR: slot 3 is READABLE the whole time
#    (y_measured True) but select_and_play refuses it anyway (a dropped
#    press, not a positional refusal). This drives the REAL play_one_turn
#    call site's own reason inference -- section (c) above computes its
#    reason directly and hands it to exclude_play_slot, which cannot catch a
#    mutant in the call site's classification; this can.
# =============================================================================
_reset()

H_T = _hand(y3=True)                   # slot 3 present AND readable

_play_calls_6 = []


def _fake_select_and_play_6(player_idx, tactics_idx, look=None):
    _play_calls_6.append(player_idx)
    return player_idx != 3             # slot 3 always refused -- NOT positional


_saved = {}
_patch(_saved, select_and_play=_fake_select_and_play_6,
       _grab_settle_regions=_fake_grab_settle_regions)
_buf6 = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf6):
        for _ in range(o.PLAY_STALL_MAX):
            o.play_one_turn(dict(STATE_5, hand=H_T), 0)
finally:
    _unpatch(_saved)
_log6 = _buf6.getvalue()

check(_play_calls_6 == [3, 3, 3],
      f"all three refusals must target slot 3 (the best, readable card): "
      f"{_play_calls_6!r}")
check(o._PLAY_STALL["reasons"].get(3) == o.PLAY_REFUSAL_TRANSIENT,
      "the REAL play_one_turn call site must classify a refusal on a "
      f"READABLE slot as transient, got {o._PLAY_STALL['reasons'].get(3)!r}")
check("excluded as transient" in _log6,
      "the log must name slot 3's exclusion as transient:\n" + _log6)

# A genuine redeal elsewhere in the hand must clear it -- the pre-I-39
# behaviour, and the one a TRANSIENT reason must still get.
H_T_REDEAL = _hand(y3=True, power2=7)
check(o.play_excluded_slots(H_T_REDEAL) == frozenset(),
      "a TRANSIENT exclusion reached through the real call site must still "
      "clear on a genuine redeal")


if failures:
    for f in failures:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a play exclusion keyed on the slot's own refusal reason: an "
      "UNREADABLE one survives a genuine redeal and clears the instant the "
      "slot reads again; a TRANSIENT one keeps the pre-I-39 behaviour "
      "unchanged; and play_one_turn end to end reproduces the live I-39 shape "
      "correctly at every turn")
