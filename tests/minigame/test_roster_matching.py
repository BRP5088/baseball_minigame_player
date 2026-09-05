"""Regression test for match_roster_name() — the function behind the round-2
Critical (QA_FINDINGS_R2.md N1).

WHY THIS EXISTS
---------------
`ocr_ban_card_name()` can only ever return a card already in KNOWN_BAN_ROSTER.
So for a grid position that isn't catalogued yet, a lenient fuzzy match forces
the real card's name onto the nearest KNOWN name. That wrong card then:
  1. fills roster_hits, suppressing the vision read that would have corrected it
  2. lands in the grid twice, so one intended ban toggled TWO physical cards

That is the only path in the project that sends wrong physical input into a
$50-per-match loop. It was measured at 15 false resolutions out of 17 plausible
unknown names before the fix.

The property under test is asymmetric and deliberately so:
  - STRICT mode (used for ban-grid cards): must REFUSE anything it isn't sure
    of. A false match bans the wrong card; an abstention just costs one vision
    call. Refusing too much is cheap, refusing too little is not.
  - LOOSE mode (used for base-runner names): may resolve garbled OCR, because
    those positions are only ever read for logging/among an already-known set.

No API calls, no images — pure function.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import KNOWN_BAN_ROSTER, match_roster_name

STRICT = dict(cutoff=0.85, allow_surname_fallback=False)

# Names that are NOT in the roster. Strict mode must refuse every one — each
# was verified to falsely resolve before the fix.
NOT_IN_ROSTER = [
    ("Frank Coker", "Brian Coker"),
    ("Nate Kelly", 'Noah "The Rat Baron" Kelly'),
    ("Bobby Sharp", "Rube Sharp"),
    ("Jose Diaz", "Joshua Diaz"),
    ("Otis Black", "Jake Saucepan Black"),
    ("Thomas Brown", "Thomas Thomas"),
    ("Mickey Lee", "Mickey Brown"),
    ("Randy Curd", "Jeremiah Curd"),
]

# Real garbled OCR output captured from live frames. Loose mode should still
# resolve these — this is what makes base-runner reading work at all.
GARBLED_REAL = [
    ("JOHNNY ORAWERS", "Johnny Drawers"),
    ("RUBE SHARP", "Rube Sharp"),
    ("NUGC SHARP", "Rube Sharp"),
    ("DONNY MEKESZ", "Donny Mekesz"),
    ("BRIAN COKER", "Brian Coker"),
]

failures = []

# --- 1. Strict mode must never invent a match for an unknown card ---
for name, would_have_matched in NOT_IN_ROSTER:
    got = match_roster_name(name, **STRICT)
    if got is not None:
        failures.append(
            f"STRICT resolved unknown {name!r} -> {got.name!r} "
            f"(pre-fix it matched {would_have_matched!r}); this bans a wrong card")

# --- 2. Strict mode must still accept an exact/near-exact real name ---
for card in list(KNOWN_BAN_ROSTER.values())[:8]:
    got = match_roster_name(card.name, **STRICT)
    if got is None or got.name != card.name:
        failures.append(f"STRICT failed to resolve exact name {card.name!r} -> {got}")

# --- 3. Loose mode still recovers real garbled reads ---
for garbled, expected in GARBLED_REAL:
    got = match_roster_name(garbled)
    if got is None or got.name != expected:
        failures.append(
            f"LOOSE failed on real OCR output {garbled!r}: expected "
            f"{expected!r}, got {got.name if got else None!r}")

# --- 4. Ambiguous surnames: STRICT must refuse (QA R2 N7) ---
# The roster has four "* Jody Gain" cards, two "* Brown", two "* Blunt". A
# garbled first word must not let the DANGEROUS path pick one of them.
#
# Scope note, established by this test: the N7 surname guard only governs the
# surname FALLBACK. The whole-string path at the loose cutoff (0.5) can still
# resolve e.g. 'XXXXX Blunt' -> 'Joel Blunt' by raw character overlap. That is
# accepted, and bounded:
#   - LOOSE mode is used only for base-runner names, where the decision engine
#     reads the runner COUNT (len(state.runners)), never the identity — and
#     ocr_runner_card() is not wired into the live loop at all today.
#   - STRICT mode is what guards ban selection, and it must refuse. That is the
#     assertion below.
# If loose mode is ever used somewhere identity matters, this needs revisiting.
surnames = {}
for c in KNOWN_BAN_ROSTER.values():
    surnames.setdefault(c.name.split()[-1], []).append(c.name)
ambiguous = {s: n for s, n in surnames.items() if len(n) > 1}
assert ambiguous, "expected at least one colliding surname in the roster"
for surname, names in ambiguous.items():
    for probe in (surname, f"XXXXX {surname}"):
        got = match_roster_name(probe, **STRICT)
        if got is not None:
            failures.append(
                f"STRICT resolved ambiguous {probe!r} (surname shared by "
                f"{len(names)} cards: {names}) -> {got.name!r}; must refuse")

# --- 5. Degenerate input must never resolve ---
for junk in ["", "   ", "|", "??", "\\ /", "a"]:
    got = match_roster_name(junk, **STRICT)
    if got is not None:
        failures.append(f"junk input {junk!r} resolved to {got.name!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} roster-matching failures")

print(f"OK: strict mode refused all {len(NOT_IN_ROSTER)} unknown names, "
      f"loose mode recovered all {len(GARBLED_REAL)} real garbled reads, "
      f"{len(ambiguous)} ambiguous surname(s) refused under strict mode")


# --- The two readers use DIFFERENT cutoffs, deliberately ------------------
# Both resolve an OCR'd name against the roster, but the cost of a wrong answer
# differs by orders of magnitude, so the thresholds differ and neither should
# be "unified" with the other:
#
#   ocr_ban_card_name  0.85 — a wrong match BANS THE WRONG PHYSICAL CARD in a
#                             paid match. Refusing costs one vision call.
#   ocr_runner_card    0.70 — audit-only (sole caller: log_local_read_comparison;
#                             GameState.runners comes from the vision read).
#                             Runner-name crops are far more garbled: the real
#                             read for "Rube Sharp" is "NUGC SHARP", which no
#                             cutoff above 0.72 accepts.
#
# Measured 2026-08-25, 5 real garbled reads vs 15 uncatalogued names:
#     0.50 : 5/5 genuine kept, 12/15 unknowns force-matched
#     0.70 : 5/5 genuine kept,  4/15 unknowns force-matched   <- knee
#     0.85 : 3/5 genuine kept,  1/15 unknowns force-matched
import inspect

import orchestrator as _o

_ban_src = inspect.getsource(_o.ocr_ban_card_name)
_run_src = inspect.getsource(_o.ocr_runner_card)

assert "cutoff=0.85" in _ban_src, (
    "ocr_ban_card_name is no longer resolving at cutoff=0.85 — a loosened ban "
    "matcher force-matches uncatalogued cards and bans the wrong one")
assert "allow_surname_fallback=False" in _ban_src, (
    "ocr_ban_card_name lost allow_surname_fallback=False — surname-only "
    "matching maps distinct players onto each other")
assert "cutoff=0.70" in _run_src or "cutoff=0.7" in _run_src, (
    "ocr_runner_card is no longer at the measured 0.70 knee — the loose default "
    "force-matched 12 of 15 uncatalogued names onto real cards, and 0.85 "
    "rejects genuine garbled reads like 'NUGC SHARP'")
assert "allow_surname_fallback=False" in _run_src, (
    "ocr_runner_card lost allow_surname_fallback=False")

# The genuine garbled read must survive its cutoff, and a plausible unknown
# must not: this is the property, not the constant.
assert match_roster_name("NUGC SHARP", cutoff=0.70,
                         allow_surname_fallback=False) is not None, \
    "the real garbled read for Rube Sharp no longer resolves at 0.70"
assert match_roster_name("Frank Coker", cutoff=0.85,
                         allow_surname_fallback=False) is None, \
    "'Frank Coker' (not in the roster) force-matches at the ban cutoff"

print("OK: ban matcher strict (0.85), runner matcher at the measured knee "
      "(0.70) — different by design, both reject surname-only fallback")


# --- Type banners must never resolve to a card ---------------------------
# The game labels a card by TYPE wherever its identity is hidden (cards in
# hand, the face-down card in a reveal). "Batter" scored 0.615 against the
# surname "Wetters" and force-matched Jedediah Wetters on 12 occurrences of
# the 2026-08-26 run, inventing a specific card AND a specific power for a
# card that was never actually identified. Downstream that power fed the
# misfire detector, so a fabricated identity became a fabricated comparison.
from orchestrator import CARD_TYPE_BANNERS, KNOWN_BAN_ROSTER

for _banner in ("Batter", "BATTER", "batter", "Pitcher", "Fielder"):
    assert match_roster_name(_banner) is None, (
        f"{_banner!r} resolves to "
        f"{getattr(match_roster_name(_banner), 'name', None)!r} — a type "
        "banner is not a name, and resolving one fabricates a card")

# The guard must not shadow a real card: if the game ever ships a player
# actually named one of these, the blocklist silently deletes them.
_shadowed = [c.name for c in KNOWN_BAN_ROSTER.values()
             if c.name.lower() in CARD_TYPE_BANNERS]
assert not _shadowed, f"banner list shadows real roster cards: {_shadowed}"

# The guard must be narrow. These are the real garbled renderings seen live,
# and every one of them has to survive — a blunter fix (raising the cutoff,
# or disabling the surname fallback) killed the three marked *, which the
# match log proves are genuine.
for _raw, _want in (('Brandon "Binge"', 'Brandon "Binger" Ortiz'),
                    ("Pure Sharp", "Rube Sharp"),
                    ("Russ Sharp", "Rube Sharp"),
                    ("P. J. Gain", "Papa Jody Gain"),      # *
                    ("M.J. Gain", "Mama Jody Gain"),       # *
                    ("Ortiz", 'Brandon "Binger" Ortiz')):  # *
    _hit = match_roster_name(_raw)
    assert _hit is not None and _hit.name == _want, (
        f"{_raw!r} -> {getattr(_hit, 'name', None)!r}, expected {_want!r}")

# cutoff must govern the surname fallback too. It was hardcoded at 0.6, so a
# caller asking for precision got surname guesses anyway and had no defence.
# The probe surname must be a NEAR match, not an exact one: "Zzzz Wetters"
# proves nothing here, because "wetters" matches the roster surname exactly
# (ratio 1.0) and so passes at ANY cutoff — it stayed green whether or not
# cutoff reached the fallback. "Wetter" scores ~0.92, which straddles it.
assert match_roster_name("Zzzz Wetter", cutoff=0.99) is None, (
    "cutoff still does not reach the surname fallback")
assert match_roster_name("Zzzz Wetter") is not None, (
    "fixture is not straddling the threshold — it fails at BOTH cutoffs, so "
    "the assertion above would pass even with the fallback hardcoded")

print("OK: type banners rejected, live garbled names still resolve, "
      "cutoff now governs the surname fallback")
