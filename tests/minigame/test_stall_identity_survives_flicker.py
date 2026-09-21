"""I-27: A SLOT FLICKERING TO UNKNOWN MUST NOT RESET THE STALL COUNTERS OR FORGET
AN EXCLUDED SLOT.

Reproduced live 2026-09-20 (agent_progress/census-20260920/progress.md section 5,
finding 1; the raw log is overnight/run_live_20260920h.log lines ~136-150).
`_discard_hand_identity` used to return a flat sorted tuple of every card in
`hand`, compared with `!=`. `local_hand_cards` DROPS a slot it cannot read for
one poll (`dropped.append(i); continue` -- the slot never enters `hand` at
all, it does not become `{"power": None, ...}`), so that slot going UNKNOWN
for a single poll changed the tuple, which reset _DISCARD_STALL/_PLAY_STALL
exactly like a genuine redeal:

    h:136  play REFUSED 3x running on hand_index 1 -- excluding it
    h:141  a DIFFERENT slot (3) is targeted next, and itself goes unreadable
           mid-operation
    h:148  [hand] ... 3: UNKNOWN            <- slot 3 dropped from `hand`
    h:150  Decision: Playing None (pitch focus 9)   <- hand_index 1, the slot
           excluded 14 lines earlier, is back on offer

The fix (orchestrator.py `_discard_hand_identity` / `_hand_identity_changed`):
the identity is now a dict keyed by hand_index, and two identities are the
"same hand" whenever no hand_index readable in BOTH disagrees -- a slot
missing from either side is not a disagreement. `discard_stalled` and
`play_excluded_slots` merge the current poll's cards into the stored identity
on every "same" verdict, so a slot that comes back after a flicker is compared
against what was last known about it, not silently forgotten.
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

from _run_harness import check, failures                             # noqa: E402
import orchestrator as o                                             # noqa: E402


def _reset():
    o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
    o._PLAY_STALL["sig"], o._PLAY_STALL["n"], o._PLAY_STALL["excluded"] = None, 0, frozenset()


# A five-card hand shaped like the h.log reproduction: two tactics cards and
# three player cards, hand_index 1 the one that ends up excluded.
H = [
    {"kind": "tactics", "name": "fielding_boost", "type": "fielding_boost",
     "bonus": 1, "hand_index": 0},
    {"kind": "player", "name": None, "power": 9, "secondary": 0, "hand_index": 1},
    {"kind": "player", "name": None, "power": 5, "secondary": 1, "hand_index": 2},
    {"kind": "player", "name": None, "power": 6, "secondary": 0, "hand_index": 3},
    {"kind": "player", "name": None, "power": 6, "secondary": 0, "hand_index": 4},
]
# The same hand with hand_index 3 DROPPED -- exactly what local_hand_cards
# hands back when a slot's disc goes unreadable for one poll: the entry is
# absent from the list, not present with a None power.
H_FLICKER = [c for c in H if c["hand_index"] != 3]

# --- (a) exclusion survives a flicker on an UNRELATED slot; the count keeps
#         accumulating across the flicker and the breaker fires at exactly 3 -----
_reset()
o.play_excluded_slots(H)                    # establishes the signature
for _ in range(o.PLAY_STALL_MAX):
    o.note_play_refused()
check(o.play_stalled(H) is True,
      "setup: hand_index 1 must be stalled after PLAY_STALL_MAX refusals on H")
o.exclude_play_slot(1)                      # hand_index 1 excluded; n resets for the next target
check(o.play_excluded_slots(H) == frozenset({1}),
      "setup: hand_index 1 must be excluded before the flicker begins")

# The engine now offers hand_index 3 instead. It gets refused twice...
o.note_play_refused()
o.note_play_refused()
check(o.play_stalled(H) is False,
      "hand_index 3's count must be 2, not yet stalled, before the flicker")

# ...and on the NEXT poll hand_index 3 itself has gone UNKNOWN -- this is the
# exact shape of h:148 in the reproduction. Polling with the flickered hand
# must not reset anything: the excluded slot must survive, and the count for
# the current target must be preserved rather than thrown away.
check(o.play_excluded_slots(H_FLICKER) == frozenset({1}),
      "a slot flickering to UNKNOWN must not forget hand_index 1's exclusion")
check(o.play_stalled(H_FLICKER) is False,
      "the flicker must not have reset the in-flight refusal count back to 0 "
      "(it would silently give hand_index 3 an unearned fresh budget)")

# The third refusal lands WHILE the hand is still flickered (h:141-148 refused
# the card mid-operation, before the next poll's hand read landed) --
# exercising note_play_refused() against the flickered identity too.
o.note_play_refused()

# The slot recovers on the next poll (H, complete again) -- the count must
# read as 3 (stalled), NOT as reset-then-1, and hand_index 1 must still be
# excluded: nothing about the flicker may have let it back onto the table.
check(o.play_stalled(H) is True,
      f"the count must be 3 across the flicker (2 before + 1 during) and the "
      f"breaker must fire on the recovered hand, not silently reset: "
      f"n={o._PLAY_STALL['n']!r}")
check(o.play_excluded_slots(H) == frozenset({1}),
      "hand_index 1 must STILL be excluded once the flickered slot recovers -- "
      "this is the exact defect: h:150 replayed hand_index 1 after exactly "
      "this sequence")

# --- same shape for the discard breaker (DISCARD_STALL has no exclusion set,
#     but its count must be equally immune to an unrelated slot flickering) ----
_reset()
o.discard_stalled(H)                        # establishes the signature
o.note_discard_refused()
o.note_discard_refused()
check(o.discard_stalled(H) is False,
      "setup: 2 discard refusals on H must not yet be stalled")
check(o.discard_stalled(H_FLICKER) is False,
      "polling with a flickered hand must not itself change the stalled verdict")
o.note_discard_refused()
check(o.discard_stalled(H) is True,
      f"the discard breaker's count must also survive the flicker and reach "
      f"DISCARD_STALL_MAX: n={o._DISCARD_STALL['n']!r}")

# --- (b) CONTROL: a hand where one READABLE slot holds a genuinely DIFFERENT
#         card is NOT a flicker -- it must reset the count and clear the
#         exclusion, exactly like the pre-existing "new hand" controls -------------
_reset()
o.play_excluded_slots(H)
for _ in range(o.PLAY_STALL_MAX):
    o.note_play_refused()
o.exclude_play_slot(1)
check(o.play_excluded_slots(H) == frozenset({1}),
      "setup: hand_index 1 excluded before the genuine-change control")

CHANGED = [dict(c) for c in H]
CHANGED[2] = dict(CHANGED[2], power=9)      # hand_index 2, READABLE on both sides, different card
check(o.play_excluded_slots(CHANGED) == frozenset(),
      "a hand where a READABLE slot disagrees is a genuine redeal -- the "
      "exclusion set must be cleared, not carried forward like a flicker")
check(o.play_stalled(CHANGED) is False,
      "a genuine redeal must reset the refusal count to 0")

_reset()
o.discard_stalled(H)
o.note_discard_refused()
o.note_discard_refused()
CHANGED2 = [dict(c) for c in H]
CHANGED2[4] = dict(CHANGED2[4], power=4)    # hand_index 4, READABLE on both sides, different card
check(o.discard_stalled(CHANGED2) is False,
      "CONTROL: a genuine redeal must reset the discard breaker's count too")
check(o._DISCARD_STALL["n"] == 0,
      f"CONTROL: the count itself must be 0 after a genuine redeal, not just "
      f"the flag: n={o._DISCARD_STALL['n']!r}")

if failures:
    for f in failures:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a slot flickering to UNKNOWN preserves the stall count and any "
      "exclusion; a genuinely different readable card still resets both")
