"""I-29: A REDEAL AT A CONFIRMED INDEX CAN COINCIDE WITH THE OLD CARD'S VALUE, AND
THE STALL COUNTERS HAD NO NOTION OF A CARD INSTANCE.

Found in QA round 4, offline (agent_progress/census-20260920 lineage), not seen live.
`_discard_hand_identity` compares a hand_index's VALUE tuple (kind, power, secondary,
type) -- I-27's whole point, so a slot that flickers to UNKNOWN for one poll is not
mistaken for a real redeal. But the roster has only ~18-24 distinct (power, secondary)
pairs (CLAUDE.md section 4: "DO CARD VALUES CHANGE PER GAME? NO."), so a REAL redeal at
a slot we just played or discarded can draw a card that happens to share the old card's
value. Compared by VALUE alone, that reads as "no change" -- the fresh card inherits
whatever refusal count or play-exclusion the old card had built up, even though it is a
different physical card.

THE FIX (orchestrator.py, `note_slot_dealt`, called at the two places a card is
actually spent -- right beside `forget_hand_slot`): a confirmed play or discard is a
KNOWN deal event at that index, independent of value. Drop the index from both stall
trackers' stored identity, clear it from the play-exclusion set, and reset both
trackers' running counts, so "this card is new" is true by construction.

Four scenarios, driven through the REAL `play_one_turn` with `select_and_play` /
`select_and_discard` stubbed -- the shape test_refused_play_falls_back.py section 7 and
test_discard_stall_breaks.py section 5 use, not a source-text substring check
(CLAUDE.md's "check() SIGNATURES" / "a check that cannot fail" entries):

  (a) a confirmed DISCARD un-excludes and forgets its own slot.
  (b) a confirmed PLAY forgets its own slot AND its tactics slot, and resets a
      PARTIAL (not yet stalled) refusal count.
  (c) CONTROL: a confirmed play at a DIFFERENT index leaves an unrelated
      excluded slot's exclusion, identity and count untouched.
  (d) added by the second QA-round-4 finder: a confirmed discard, then 50 polls
      where the replacement card at that index never reads (occluded) -- the
      slot must stay un-excluded and un-stalled THROUGH the absence, not just
      at the moment of the confirm.

Mutation sensitivity is deliberate: dropping the `note_slot_dealt` call at the play
site fails only (b); dropping it at the discard site fails only (a) and (d).
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

import orchestrator as o                                             # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def _reset_stall_state():
    o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
    o._PLAY_STALL["sig"], o._PLAY_STALL["n"], o._PLAY_STALL["excluded"] = None, 0, frozenset()


def _sig_of(hand):
    return o._discard_hand_identity(hand)


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


# =============================================================================
# (a) A CONFIRMED DISCARD forgets its own slot: un-excludes it, drops it from
#     both trackers' stored identity, and resets the count -- so the SAME
#     value redealt there is offered again rather than inheriting the old
#     card's exclusion.
# =============================================================================
_reset_stall_state()

WEAK_HAND = [{"kind": "player", "name": None, "power": p, "secondary": 1,
              "hand_index": i} for i, p in enumerate([6, 5, 4, 3, 2])]
# index 4 (power 2) is the weakest -- the discard branch's own deterministic
# target (min by (power, secondary)).
STATE_A = {"phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
           "discards_left": 2, "hand": WEAK_HAND}

# Simulate "index 4 excluded after PLAY_STALL_MAX refusals", the state the real
# exclude_play_slot() call leaves behind -- set up directly rather than driven,
# because index 4 is the WEAKEST card and can never be a play target through the
# real decision (a play always picks the strongest), so this is the only way to
# reach "excluded from play" for the card the discard branch is about to pick.
_full_sig = _sig_of(WEAK_HAND)
o._PLAY_STALL["sig"] = dict(_full_sig)
o._PLAY_STALL["excluded"] = frozenset({4})
o._PLAY_STALL["n"] = 0
o._DISCARD_STALL["sig"] = dict(_full_sig)
o._DISCARD_STALL["n"] = 0

_discard_calls_a = []


def _fake_select_and_discard_a(player_idx, look=None, discards_look=None):
    _discard_calls_a.append(player_idx)
    return True                        # CONFIRMED


_saved = {}
_patch(_saved, select_and_discard=_fake_select_and_discard_a,
       _grab_settle_regions=_fake_grab_settle_regions)
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        _result_a = o.play_one_turn(dict(STATE_A), 0)
finally:
    _unpatch(_saved)

check(_discard_calls_a == [4],
      f"the discard branch's own weakest-card pick must target hand_index 4: "
      f"{_discard_calls_a!r}")
check(_result_a == (False, None),
      f"a confirmed discard still returns (False, None) -- I-29 changes stall "
      f"bookkeeping, not the discard contract: {_result_a!r}")
check(4 not in o._PLAY_STALL["sig"],
      "a confirmed discard at 4 must drop 4 from _PLAY_STALL's stored identity")
check(4 not in o._PLAY_STALL["excluded"],
      "a confirmed discard at 4 must un-exclude 4 from the PLAY breaker -- the "
      "old card's exclusion must not survive the redeal it caused")
check(o._PLAY_STALL["n"] == 0,
      f"_PLAY_STALL['n'] must be 0 after the confirm, got {o._PLAY_STALL['n']}")
check(4 not in o._DISCARD_STALL["sig"],
      "a confirmed discard at 4 must drop 4 from _DISCARD_STALL's stored identity too")
check(o._DISCARD_STALL["n"] == 0,
      f"_DISCARD_STALL['n'] must be 0 after the confirm, got {o._DISCARD_STALL['n']}")
for _i in (0, 1, 2, 3):
    check(_i in o._PLAY_STALL["sig"] and _i in o._DISCARD_STALL["sig"],
          f"only the dealt slot (4) may be dropped -- hand_index {_i} vanished too")

# THE SAME VALUE REAPPEARS AT 4 (the roster is a small fixed set -- CLAUDE.md
# section 4). It must be offered again, not excluded, with a fresh count.
check(4 not in o.play_excluded_slots(WEAK_HAND),
      "the same value redealt at 4 must be offered again, not excluded")
check(o.play_stalled(WEAK_HAND) is False,
      "the same value redealt at 4 must start its refusal count at 0")


# =============================================================================
# (b) A CONFIRMED PLAY forgets its own slot AND its tactics slot, and resets a
#     PARTIAL (not-yet-stalled) refusal count -- the case (a) cannot exercise,
#     because a card that has already reached PLAY_STALL_MAX is EXCLUDED and a
#     real play can therefore never confirm at it.
# =============================================================================
_reset_stall_state()

STRONG_HAND_B = ([{"kind": "tactics", "name": "Swing Boost", "type": "swing_boost",
                   "bonus": 1, "hand_index": 0}] +
                  [{"kind": "player", "name": None, "power": p, "secondary": 1,
                    "hand_index": i} for i, p in zip((1, 2, 3, 4), (9, 5, 4, 3))])
# best_batting_play must pick hand_index 1 (power 9, the max) with the swing
# boost at hand_index 0 attached (it only ever adds power, so it always attaches
# -- decision_engine.best_batting_play's own docstring).
STATE_B = {"phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
           "discards_left": 0, "hand": STRONG_HAND_B}

_full_sig_b = _sig_of(STRONG_HAND_B)
o._PLAY_STALL["sig"] = dict(_full_sig_b)
o._PLAY_STALL["excluded"] = frozenset()
o._PLAY_STALL["n"] = 2                 # two refusals already on THIS unchanged
                                        # hand -- one more would stall it
o._DISCARD_STALL["sig"] = dict(_full_sig_b)
o._DISCARD_STALL["n"] = 0

_play_calls_b = []


def _fake_select_and_play_b(player_idx, tactics_idx, look=None):
    _play_calls_b.append((player_idx, tactics_idx))
    return True                        # CONFIRMED


_saved = {}
_patch(_saved, select_and_play=_fake_select_and_play_b,
       _grab_settle_regions=_fake_grab_settle_regions)
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        _result_b = o.play_one_turn(dict(STATE_B), 0)
finally:
    _unpatch(_saved)

check(_play_calls_b == [(1, 0)],
      f"best_batting_play must pick (player=1, tactics=0) on this hand: {_play_calls_b!r}")
check(_result_b[0] is True,
      f"a confirmed play must report played=True: {_result_b!r}")
check(1 not in o._PLAY_STALL["sig"] and 0 not in o._PLAY_STALL["sig"],
      "a confirmed play at (1, 0) must drop BOTH the player slot and the "
      f"tactics slot from _PLAY_STALL's stored identity: {o._PLAY_STALL['sig']!r}")
check(o._PLAY_STALL["n"] == 0,
      f"a confirmed play must reset _PLAY_STALL['n'] even though it never "
      f"reached PLAY_STALL_MAX, got {o._PLAY_STALL['n']}")
check(1 not in o._DISCARD_STALL["sig"] and 0 not in o._DISCARD_STALL["sig"],
      "a confirmed play must drop both spent slots from _DISCARD_STALL too, "
      f"got {o._DISCARD_STALL['sig']!r}")
for _i in (2, 3, 4):
    check(_i in o._PLAY_STALL["sig"] and _i in o._DISCARD_STALL["sig"],
          f"only the two spent slots may be dropped -- hand_index {_i} vanished too")

check(1 not in o.play_excluded_slots(STRONG_HAND_B),
      "the same value redealt at 1 must be offered again, not excluded")
check(o.play_stalled(STRONG_HAND_B) is False,
      "the same value redealt at 1 must not inherit the old n=2")


# =============================================================================
# (c) CONTROL: a confirmed play at a DIFFERENT index must not disturb an
#     unrelated slot's exclusion, identity or count.
# =============================================================================
_reset_stall_state()

STRONG_HAND_C = [{"kind": "player", "name": None, "power": p, "secondary": 1,
                   "hand_index": i} for i, p in enumerate([5, 9, 6, 8, 4])]
# hand_index 1 is the strongest (9) but EXCLUDED below, so best_batting_play
# must fall through to the next-best AVAILABLE card, hand_index 3 (power 8).
STATE_C = {"phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
           "discards_left": 0, "hand": STRONG_HAND_C}

_full_sig_c = _sig_of(STRONG_HAND_C)
o._PLAY_STALL["sig"] = dict(_full_sig_c)
o._PLAY_STALL["excluded"] = frozenset({1})
o._PLAY_STALL["n"] = 0
o._DISCARD_STALL["sig"] = dict(_full_sig_c)
o._DISCARD_STALL["n"] = 0

_play_calls_c = []


def _fake_select_and_play_c(player_idx, tactics_idx, look=None):
    _play_calls_c.append((player_idx, tactics_idx))
    return True


_saved = {}
_patch(_saved, select_and_play=_fake_select_and_play_c,
       _grab_settle_regions=_fake_grab_settle_regions)
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        _result_c = o.play_one_turn(dict(STATE_C), 0)
finally:
    _unpatch(_saved)

check(_play_calls_c == [(3, None)],
      f"excluding hand_index 1 must make hand_index 3 (next-best) the play "
      f"target: {_play_calls_c!r}")
check(_result_c[0] is True, f"expected a confirmed play: {_result_c!r}")
check(o._PLAY_STALL["excluded"] == frozenset({1}),
      f"a confirmed play at 3 must leave hand_index 1's exclusion in place, "
      f"got {o._PLAY_STALL['excluded']!r}")
check(1 in o._PLAY_STALL["sig"] and 1 in o._DISCARD_STALL["sig"],
      "a confirmed play at 3 must not touch hand_index 1's stored identity in "
      "either tracker")
check(3 not in o._PLAY_STALL["sig"] and 3 not in o._DISCARD_STALL["sig"],
      "the ACTUALLY confirmed slot (3) must still be dropped")
for _i in (0, 2, 4):
    check(_i in o._PLAY_STALL["sig"] and _i in o._DISCARD_STALL["sig"],
          f"an untouched slot ({_i}) must not vanish from either tracker")


# =============================================================================
# (d) QA round 4, second finder: a confirmed discard, then 50 polls where the
#     replacement card at that index NEVER READS (occluded, CLAUDE.md 10.28).
#     I-27's merge only ADDS keys present in the current poll's hand, so an
#     absent index can never itself contradict the stored value -- the slot
#     must stay forgotten and un-excluded for the WHOLE absence, not just at
#     the instant of the confirm.
# =============================================================================
_reset_stall_state()

WEAK_HAND_D = [{"kind": "player", "name": None, "power": p, "secondary": 1,
                "hand_index": i} for i, p in enumerate([6, 1, 5, 4, 3])]
# hand_index 1 (power 1) is the weakest -- the discard branch's target.
STATE_D = {"phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
           "discards_left": 2, "hand": WEAK_HAND_D}

_full_sig_d = _sig_of(WEAK_HAND_D)
o._PLAY_STALL["sig"] = dict(_full_sig_d)
o._PLAY_STALL["excluded"] = frozenset({1})     # pre-existing, like (a)
o._PLAY_STALL["n"] = 0
o._DISCARD_STALL["sig"] = dict(_full_sig_d)
o._DISCARD_STALL["n"] = 0

_discard_calls_d = []


def _fake_select_and_discard_d(player_idx, look=None, discards_look=None):
    _discard_calls_d.append(player_idx)
    return True


_saved = {}
_patch(_saved, select_and_discard=_fake_select_and_discard_d,
       _grab_settle_regions=_fake_grab_settle_regions)
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        _result_d = o.play_one_turn(dict(STATE_D), 0)
finally:
    _unpatch(_saved)

check(_discard_calls_d == [1], f"expected the discard to target 1: {_discard_calls_d!r}")
check(1 not in o._PLAY_STALL["sig"] and 1 not in o._PLAY_STALL["excluded"],
      "immediately after the confirm, 1 must be gone from _PLAY_STALL")

# NOW THE REPLACEMENT NEVER READS. Fifty polls, hand_index 1 absent from `hand`
# every single time -- local_hand_cards's own shape for an occluded slot
# (dropped.append(i); continue), never a value.
ABSENT_HAND = [c for c in WEAK_HAND_D if c["hand_index"] != 1]
for _ in range(50):
    o.play_excluded_slots(ABSENT_HAND)
    o.discard_stalled(ABSENT_HAND)

check(1 not in o._PLAY_STALL["sig"],
      "50 polls of hand_index 1 being merely ABSENT must not resurrect it in "
      "_PLAY_STALL's stored identity -- nothing there ever contradicted it, "
      "so nothing should have re-added it either")
check(1 not in o._PLAY_STALL["excluded"],
      "50 polls of absence must not re-exclude hand_index 1 -- nothing can "
      "target an index that is not even in the hand")
check(o._PLAY_STALL["n"] == 0,
      f"50 polls of absence must not move _PLAY_STALL['n'], got {o._PLAY_STALL['n']}")
check(1 not in o._DISCARD_STALL["sig"],
      "50 polls of absence must not resurrect hand_index 1 in _DISCARD_STALL either")
check(o._DISCARD_STALL["n"] == 0,
      f"50 polls of absence must not move _DISCARD_STALL['n'], got {o._DISCARD_STALL['n']}")

# THEN IT FINALLY READS AGAIN, at the SAME value it had before (the roster is a
# small fixed set) -- offered again, not excluded, count still 0.
check(1 not in o.play_excluded_slots(WEAK_HAND_D),
      "when hand_index 1 finally reads again it must be offered, not excluded")
check(o.play_stalled(WEAK_HAND_D) is False,
      "when hand_index 1 finally reads again its count must still be 0")


if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a confirmed play or discard forgets its own slot (and tactics slot) "
      "from both stall trackers, independent of value; unrelated slots and a "
      "long absence of the replacement are both left alone")
