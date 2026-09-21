"""F1 (QA round 1, ISSUES.md): reset_hand_memory() must also clear the discard/play
stall counters (_DISCARD_STALL, _PLAY_STALL), or a later hand that reproduces the same
(hand_index, kind, power, secondary, type) signature -- plausible, since the roster is
a small fixed set (CLAUDE.md section 4) -- inherits a stale refusal count and an
excluded slot from a PREVIOUS match or half.

`reset_hand_memory()` is called at every match start and at the half boundary ("a new
half deals a fresh hand" -- CLAUDE.md section 4), and it used to clear only
`_hand_memory`. The stall breakers key on the CARDS
(`_discard_hand_identity`/`_discard_stalled`'s signature), not on `_hand_memory`, so
clearing that dict never touched them.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o                                               # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


HAND = [
    {"kind": "player", "name": None, "power": 6, "secondary": 0, "hand_index": 0},
    {"kind": "player", "name": None, "power": 5, "secondary": 1, "hand_index": 1},
]

# ---- seed 2 refused discards and one excluded play slot on this exact signature -----
o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
o._PLAY_STALL["sig"], o._PLAY_STALL["n"], o._PLAY_STALL["excluded"] = None, 0, frozenset()
o.discard_stalled(HAND)          # establishes the signature, n stays 0
o.note_discard_refused()
o.note_discard_refused()
o.play_excluded_slots(HAND)      # establishes the signature
o.exclude_play_slot(1)

# ---- CONTROL: without the reset, the seeded state is exactly what was seeded --------
check("CONTROL: seeded discard refusal count is 2, before any reset",
      o._DISCARD_STALL["n"] == 2, f"n={o._DISCARD_STALL['n']!r}")
check("CONTROL: seeded exclusion is {1}, before any reset",
      o.play_excluded_slots(HAND) == frozenset({1}),
      f"excluded={o.play_excluded_slots(HAND)!r}")
check("CONTROL: this exact hand IS reported stalled after 2 refusals is False, but "
      "the count itself, not the flag, is what the reset must clear",
      o._DISCARD_STALL["n"] == 2 and o.discard_stalled(HAND) is False)

# ---- reset_hand_memory() must clear both stall breakers ------------------------------
o.reset_hand_memory()

check("reset_hand_memory() clears the discard stall counter entirely",
      o._DISCARD_STALL == {"sig": None, "n": 0}, f"{o._DISCARD_STALL!r}")
check("reset_hand_memory() clears the play stall counter and its exclusions",
      o._PLAY_STALL == {"sig": None, "n": 0, "excluded": frozenset(), "reasons": {}},
      f"{o._PLAY_STALL!r}")

# ---- the SAME signature, replayed after the reset, starts fresh ---------------------
check("the same signature starts at 0 refusals after reset_hand_memory()",
      o.discard_stalled(HAND) is False and o._DISCARD_STALL["n"] == 0,
      f"{o._DISCARD_STALL!r}")
check("the same signature has no excluded slot after reset_hand_memory()",
      o.play_excluded_slots(HAND) == frozenset(),
      f"excluded={o.play_excluded_slots(HAND)!r}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
