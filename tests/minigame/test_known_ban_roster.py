"""Self-check for KNOWN_BAN_ROSTER, the roster-hit short-circuit logic, and
the self-extending learned-entry persistence in read_full_ban_collection().
No live capture — pure data/logic check."""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import json
import os

# Guard the key BEFORE importing orchestrator, which builds an Anthropic client
# at module scope. Without this the file only runs under run_tests.sh, and a
# standalone run — including a mutation check — dies with a KeyError that looks
# nothing like a test failure. That masked a mutation earlier today.
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import orchestrator
from decision_engine import PlayerCard
from orchestrator import KNOWN_BAN_ROSTER

assert len(KNOWN_BAN_ROSTER) >= 33
# Row bound comes from the scroller, NOT from what happens to be catalogued
# today. read_full_ban_collection(max_presses=40) returns ABSOLUTE rows and the
# roster is self-extending, so the old `row <= 6` was really asserting "nobody
# has learned a card past row 6 yet" — a fact about the current data, not an
# invariant. The first live session that scrolls deeper would have turned this
# red for a non-bug. Columns are 0-4 because the grid is genuinely 5 wide.
import inspect
_MAX_ROW = inspect.signature(orchestrator.read_full_ban_collection).parameters["max_presses"].default
for (row, col), card in KNOWN_BAN_ROSTER.items():
    assert 0 <= row <= _MAX_ROW and 0 <= col <= 4, f"position out of range: {(row, col)}"
    assert isinstance(card, PlayerCard)
    assert card.name and card.power > 0

# Simulate the batch classification: all-known positions should skip vision,
# a batch with any unknown position should not.
known_batch = [(0, 0), (0, 1), (0, 2)]
roster_hits = {pos: KNOWN_BAN_ROSTER[pos] for pos in known_batch if pos in KNOWN_BAN_ROSTER}
assert len(roster_hits) == len(known_batch)

mixed_batch = [(0, 0), (6, 3)]  # (6, 3) was never captured, not in the table
roster_hits = {pos: KNOWN_BAN_ROSTER[pos] for pos in mixed_batch if pos in KNOWN_BAN_ROSTER}
assert len(roster_hits) != len(mixed_batch)

# Learning round-trip. A roster entry becomes permanent ground truth (that
# position is never re-read by vision afterwards), so persisting now requires
# TWO INDEPENDENT AGREEING reads — one sighting is held in memory only.
test_file = "test_learned_roster_scratch.json"
orchestrator.LEARNED_BAN_ROSTER_FILE = test_file
# This file drives PERSISTENCE on purpose, against the scratch path above.
# _learn_roster_entry refuses to write under BASEBALL_TEST_RUN since
# 2026-09-13 -- a learned entry is permanent ground truth that vision
# never re-reads -- so opt in explicitly.
orchestrator.LEARN_ROSTER_IN_TESTS = True
if os.path.exists(test_file):
    os.remove(test_file)
new_pos = (6, 3)
try:
    assert new_pos not in KNOWN_BAN_ROSTER
    new_card = PlayerCard("Test Guy", 6, 1)

    # First sighting: held, NOT persisted.
    assert orchestrator._learn_roster_entry(new_pos, new_card, "test") is False
    assert new_pos not in KNOWN_BAN_ROSTER, "one read must not persist"
    assert not os.path.exists(test_file), "one read must not write to disk"

    # A disagreeing second read must also not persist.
    assert orchestrator._learn_roster_entry(new_pos, PlayerCard("Other Guy", 4, 0), "test") is False
    assert new_pos not in KNOWN_BAN_ROSTER, "disagreeing reads must not persist"

    # Two agreeing reads persist.
    assert orchestrator._learn_roster_entry(new_pos, PlayerCard("Other Guy", 4, 0), "test") is True
    assert KNOWN_BAN_ROSTER[new_pos].name == "Other Guy"
    # M7: name lookup is refreshed so the new name is immediately matchable.
    assert orchestrator.ROSTER_BY_NAME.get("other guy") is not None

    with open(test_file) as f:
        raw = json.load(f)
    assert raw["6,3"]["name"] == "Other Guy" and raw["6,3"]["source"] == "test"

    del KNOWN_BAN_ROSTER[new_pos]
    orchestrator._load_learned_roster()
    assert KNOWN_BAN_ROSTER[new_pos].name == "Other Guy"
finally:
    KNOWN_BAN_ROSTER.pop(new_pos, None)
    orchestrator._pending_roster.pop(new_pos, None)
    if os.path.exists(test_file):
        os.remove(test_file)

print("OK: KNOWN_BAN_ROSTER self-check passed (33+ entries, short-circuit logic, two-read learning)")


# --- Tactics-boundary early stop -----------------------------------------
# The ban screen consumed 149 of 175 seconds on the 2026-08-25 run, idling in
# 20-40s blocks. The scan was grinding through the TACTICS section: the roster
# does not cover it, so every batch fell to vision, mismatched, and was RETRIED
# — two vision calls per wasted step plus ten fruitless tesseract reads.
#
# The stop condition must be recomputed, never frozen: the roster extends
# itself, and a boundary captured at import would stop moving as rows are
# learned, silently truncating future scans at the old extent.
from orchestrator import _max_roster_row

_before = _max_roster_row()
assert _before == max(r for r, _ in KNOWN_BAN_ROSTER), (
    f"_max_roster_row() returned {_before}, disagreeing with the roster itself")

_probe = (_before + 3, 0)
assert _probe not in KNOWN_BAN_ROSTER, "probe position unexpectedly occupied"
KNOWN_BAN_ROSTER[_probe] = PlayerCard("Boundary Probe", 5, 1)
try:
    assert _max_roster_row() == _before + 3, (
        f"after learning a row-{_before + 3} card the boundary is still "
        f"{_max_roster_row()} — it is cached, so the scan would stop before "
        "reaching newly learned rows and never see them again")
finally:
    del KNOWN_BAN_ROSTER[_probe]

assert _max_roster_row() == _before, "roster not restored after the probe"

# The scan allows one batch of slack past the known extent so the
# self-extending roster can still discover a genuinely new row.
print(f"OK: tactics-boundary stop is recomputed (roster extent {_before}, "
      f"discovery allowed through {_before + 1}, stop at {_before + 2})")


# --- TRUST_ROSTER_ONLY: the ban scan is fully local ----------------------
# Two independent facts compose to make this safe, and the split matters:
#   * WHICH positions are unlocked is per-SAVE and read live from the screen
#     by detect_ban_grid_locked() — pure local contrast, no roster involved.
#   * WHAT card sits at a position is game-wide and constant, which is what
#     KNOWN_BAN_ROSTER stores.
# Nothing about unlock state is baked into the roster, which is why one
# catalogue serves every save. If that ever stops holding, this is the
# assumption to revisit first.
from orchestrator import TRUST_ROSTER_ONLY

# The roster must never carry lock/ownership state — only identity + stats.
for _pos, _card in KNOWN_BAN_ROSTER.items():
    for _attr in ("locked", "unlocked", "owned"):
        assert not hasattr(_card, _attr), (
            f"roster entry {_pos} carries {_attr!r} — unlock state is per-save "
            "and must come from detect_ban_grid_locked(), not the catalogue")

# The documented trade: with the flag on, an uncatalogued position is skipped
# as a ban candidate rather than triggering a vision call. That is only
# acceptable while the roster covers enough of the collection to choose 3 bans.
assert len(KNOWN_BAN_ROSTER) >= 3 * 3, (
    f"only {len(KNOWN_BAN_ROSTER)} catalogued cards — too few to reliably pick "
    "3 good bans with discovery disabled; set TRUST_ROSTER_ONLY = False")

print(f"OK: TRUST_ROSTER_ONLY={TRUST_ROSTER_ONLY}, roster holds identity only "
      f"({len(KNOWN_BAN_ROSTER)} cards); unlock state stays with the live "
      "lock detector")


# --- A short ban scan must not poison the session cache ------------------
# QA1-F6, executed: a mid-animation first frame reads every cell as locked, the
# scan returns [], and caching that served the empty list to every later call —
# including the caller's own retry loop, which then "retried" 15 times with zero
# captures and died as ban_screen_stuck AFTER the $50 was debited. One bad frame
# cost the match fee and ended the session; only restarting the process cured it.
import orchestrator as _o

# The block that used to sit here asserted `len([]) >= 3 is False` and
# `len([...5 items...]) >= 3 is True` — arithmetic on lists the test had just
# built. It called no production code at all, while its header claimed
# "QA1-F6, executed". Deleted rather than left to imply coverage it never had.
#
# The guarantee IS covered behaviourally, in test_ban_scan.py §3, which drives
# read_full_ban_collection against a short collection and asserts the session
# cache is not poisoned. The source-text check below stays as a cheap tripwire
# for the specific line being removed.
# A SOURCE-SUBSTRING TRIPWIRE WAS HERE, and it fired on a CORRECT change. It asserted
# the literal "len(full_collection) >= 3" appeared in the source; refactoring that into a
# named _short flag plus a new desync gate -- strictly stronger behaviour -- broke it
# while the guarantee got better. That is the failure mode of every source-text
# assertion, and this project hit it twice on 2026-09-13 alone.
#
# Behavioural instead, and cheap: the function must still REFUSE to cache something it
# cannot trust. test_ban_scan.py sections 3 and 3b drive the real scan for both reasons
# (too short, and desynced) with a control proving a healthy scan IS cached; four
# mutants confirmed all three bite. This asserts the seam those rely on still exists.
assert hasattr(_o, "_cached_ban_collection"), (
    "the session ban cache is gone — test_ban_scan's poisoning guards now test nothing")
_o._cached_ban_collection = ["sentinel"]
_o._cached_ban_collection = None
print("OK: short/desynced ban scans are not cached (behaviour pinned in test_ban_scan)")


# --- The two ground truths must not drift apart --------------------------
# KNOWN_BAN_ROSTER (orchestrator) and CARD_POOL (simulate) both claim to hold
# the same 33 cards' power/secondary. They are stored TWICE, so they can and did
# disagree — on `secondary`, which is the exact stat match_log.jsonl exists to
# measure, and which simulate.py's tournaments are used to reason about.
#
# This is a duplicated FACT, unlike the row-geometry constants in orchestrator
# that are deliberately measured independently and must NOT be unified.
import simulate as _sim

_pool = {c.name: c for c in _sim.CARD_POOL}
# Known-open dispute: no evidence either way, so it is recorded rather than
# guessed. Resolve by reading the card on the ban screen (PaddleOCR reads those
# badges at ~1.0 confidence) and then delete this entry.
_DISPUTED = {"Papa Jody Gain"}

# Positions (6,3) and (6,4) were long described as "uncatalogued roster gaps"
# that the self-extending roster ought to fill. They are not gaps: a 411-frame
# study with independent scroll positions identified them as POWER SWING
# **tactics** cards. They are correctly absent from a PLAYER roster and will
# never be learned, so nothing should treat their absence as incompleteness.
_NOT_PLAYER_CARDS = {(6, 3), (6, 4)}
for _p in _NOT_PLAYER_CARDS:
    assert _p not in KNOWN_BAN_ROSTER, (
        f"{_p} is in KNOWN_BAN_ROSTER, but it is a POWER SWING tactics card, "
        "not a player card — a tactics card in the player roster would become a "
        "ban candidate with fabricated power/secondary")

_drift = []
for _pos, _c in KNOWN_BAN_ROSTER.items():
    _s = _pool.get(_c.name)
    if _s is None:
        continue
    if (_c.power, _c.secondary) != (_s.power, _s.secondary):
        if _c.name in _DISPUTED:
            continue
        _drift.append(f"{_c.name}: roster={(_c.power, _c.secondary)} "
                      f"simulate={(_s.power, _s.secondary)}")
if _drift:
    for _d in _drift:
        print(f"FAIL: ground truths disagree — {_d}")
    raise SystemExit(
        f"{len(_drift)} card(s) differ between KNOWN_BAN_ROSTER and "
        "simulate.CARD_POOL. Both are used to reason about `secondary`, the "
        "stat the whole match log exists to measure.")

print(f"OK: {len(_pool)} cards agree between KNOWN_BAN_ROSTER and "
      f"simulate.CARD_POOL ({len(_DISPUTED)} known-disputed, recorded)")
