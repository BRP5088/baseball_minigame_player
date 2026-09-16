"""Self-check for the misfire detector (our_card_in_reveal / revealed_powers).

This check has shipped BROKEN TWICE — once name-based, once power-based — and
both times for the same structural reason: it lived inline inside run(), where
no test could reach it. It is a module-level function now so this file can
exist at all. Offline; no capture, no vision, no API key needed.

Both live false positives it guards against were caught on 2026-08-26, in the
same run, by two DIFFERENT failure modes. Both are pinned below.
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
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

from orchestrator import our_card_in_reveal, revealed_powers


def C(name, power=0):
    """A revealed card shaped the way the reveal reader really returns one.

    power=0 means UNREAD, not "a card with zero power" — no card in this game
    has power 0. Conflating those two is the first bug this file guards.
    """
    return {"name": name, "power": power}


# 1. LIVE FALSE POSITIVE #1 — unread powers. Both revealed powers came back 0,
#    we had just played a 9, and the roster says Bunz-Konicky IS a 9.
live_unread = [C('Brandon "Binge"'), C("Josef Bunz-Konicky")]
assert 9 in revealed_powers(live_unread[1]), "roster recovery lost Bunz-Konicky"
assert our_card_in_reveal(9, 0, live_unread), (
    "the reveal that produced the first false misfire live still fires")

# 2. LIVE FALSE POSITIVE #2 — MISREAD powers, which is nastier: the reveal
#    returned a plausible-looking 5 for Brian Coker, who is an 8. A fix that
#    only handles unread (0) powers sails straight past this one, which is
#    exactly what the first version of this patch did.
live_misread = [C("Mickey Brown", 5), C("Brian Coker", 5)]
assert revealed_powers(live_misread[1]) == {5, 8}, (
    "both readings of a disputed power must survive; adjudicating between "
    "them is not this check's job")
assert our_card_in_reveal(8, 3, live_misread), (
    "the reveal that produced the second false misfire live still fires")

# 3. Abstain when NEITHER side resolves. "P.J. Gary" is genuinely unresolvable:
#    five "* Gain" cards make that surname ambiguous, so the N7 guard refuses
#    to guess. Delete the abstain and this returns False — a confident misfire
#    assembled out of no evidence, which is what happened live.
unreadable = [C("P.J. Gary"), C("Zzzz Qqqq")]
assert all(not revealed_powers(c) for c in unreadable), "fixture resolved after all"
assert our_card_in_reveal(9, 0, unreadable), (
    "no revealed power is knowable, yet the check still claims a mismatch")

# 4. Abstain when OUR power is unknown — the one case the old code got right,
#    kept here so a rewrite cannot quietly drop it.
assert our_card_in_reveal(None, 0, [C("Rube Sharp", 8)])

# 5. A REAL mismatch must still fire, or the whole detector is decoration and
#    every assertion above passes trivially. Rube Sharp is an 8 by BOTH
#    readings, so a played 9 is genuinely absent.
assert not our_card_in_reveal(9, 0, [C("Rube Sharp", 8)]), (
    "a genuine mismatch no longer fires — the detector has gone inert")

# 6. The tactics bonus counts: an 8 played with +1 reveals as a 9. The name
#    must be one the roster CANNOT resolve, so the only power in play is the
#    raw 9. With "Rube Sharp" here the assertion passed either way — his
#    roster power is 8, which is our_power itself, so the fixture satisfied
#    the test without the bonus ever being consulted. Mutation testing caught
#    that; the assertion was decorative.
assert our_card_in_reveal(8, 1, [C("Zzzz Qqqq", 9)])
# The non-matching power must be a LEGAL one. This read `3` until the power
# floor landed; 1-3 is the tactics bonus range, so a 3 is now (correctly) a
# misread that abstains, and the assertion started failing for the right
# reason. 5 is a real power that genuinely is not 8 or 9.
assert not our_card_in_reveal(8, 1, [C("Zzzz Qqqq", 5)])

print("OK: misfire detector abstains on either side's ignorance, tolerates a "
      "disputed power, still fires on a real mismatch")


# --- Gaps proven by adversarial mutation (QA, 2026-08-26) ----------------
# Everything above passed while four real defects went undetected. Each block
# here exists because a specific mutation SURVIVED the tests above.
from orchestrator import MIN_PLAYER_POWER, revealed_powers as _rp

# M-D: `known |= revealed_powers(c)` mutated to `known = ...` — i.e. only the
# LAST revealed card counts — survived every assertion above, because each
# fixture was single-card or had a last card that happened to satisfy it.
# Live, _players holds our card AND the opponent's in arbitrary order, so that
# mutant flags ~42% of healthy turns as misfires. The matching card must sit
# FIRST here, with a non-matching card last, or this proves nothing.
assert our_card_in_reveal(9, 0, [C("Josef Bunz-Konicky", 9), C("Rube Sharp", 8)]), (
    "our card is present but listed FIRST — only the last revealed card is "
    "being consulted")

# M-A / M-B: no assertion above depended on a GARBLED name resolving; every
# load-bearing fixture used an exactly-spelled roster name, so tightening the
# resolver to cutoff=0.95 or disabling the surname fallback changed nothing.
# OCR-garble recovery is the entire mechanism of this fix. Here the garbled
# name must resolve for the detector to correctly FIRE: "Pure Sharp" is Rube
# Sharp (8), we played a 4, so our card is genuinely absent.
assert _rp(C("Pure Sharp")) == {8}, "garbled name no longer recovers a power"
assert not our_card_in_reveal(4, 0, [C("Pure Sharp")]), (
    "a real mismatch is missed because the garbled name stopped resolving")

# ...but "Pure Sharp" alone still proved nothing: it resolves by EITHER path
# (whole-string at 0.800, and surname "sharp" is unique), so tightening the
# cutoff and disabling the fallback both left it green. Each path needs a
# fixture that only IT can satisfy.
#   whole-string only: last word '"binge"' matches no surname.
assert _rp(C('Brandon "Binge"')) == {5}, (
    "the whole-string match no longer recovers a garbled name")
#   surname only: whole-string scores 0.375, far below the confident cutoff.
assert _rp(C("Ortiz")) == {5}, (
    "the surname fallback no longer recovers a surname-only read")

# The aggregate clause is now reachable only with an empty reveal — the
# caller guards against that, but the contract is still "no cards, no claim".
assert our_card_in_reveal(9, 0, []), "an empty reveal is not evidence of a misfire"

# M-H: `our_power is None` mutated to `not our_power` was invisible, because
# nothing pinned behaviour for a power of 0-3. Those are misreads, not cards
# (the hand reader treats 1-3 as a tactics bonus digit), so no reveal can ever
# contain them and every such turn was a guaranteed false misfire.
assert MIN_PLAYER_POWER >= 4, "no player card should sit below the tactics range"
for _bad in range(0, MIN_PLAYER_POWER):
    assert our_card_in_reveal(_bad, 0, [C("Rube Sharp", 8)]), (
        f"our_power={_bad} is a misread, not a card, yet it produces a "
        "confident misfire")
assert not our_card_in_reveal(MIN_PLAYER_POWER, 0, [C("Rube Sharp", 8)]), (
    "the guard swallowed a legitimate power — it must abstain BELOW the "
    "minimum only, not at it")

# A1: a garbled name resolving to the WRONG card turned the roster lookup from
# a false-positive fix into a false-positive source. All three were confirmed
# live-shaped failures: our own card is the unreadable one, so the check was
# concluding from evidence about the OPPONENT's card alone.
for _ours, _reveal, _why in (
        (4, [C("Brown"), C("Mickey Brown", 5)], "2 Browns in the roster"),
        (5, [C("Jody Gain"), C("Justin Young", 6)], "4 '* Gain' cards"),
        (8, [C("Charlie"), C("Justin Young", 6)], "'Charlie' -> Zachary Lee")):
    assert our_card_in_reveal(_ours, 0, _reveal), (
        f"ambiguous read resolved to a specific wrong card ({_why}) and "
        "produced a confident misfire")

print("OK: pooling, garble recovery, implausible-power and wrong-resolution "
      "gaps all pinned")


# --- POWER_TACTIC_KINDS must not drift from the rule it mirrors ---------
# Only a swing/pitch boost changes the power a reveal shows. That rule lives
# in simulate.power_bonus(); orchestrator now needs it too, so it is encoded
# twice and can drift. It already did once in the other direction — every
# tactics card's bonus was added regardless of kind, which overstated the
# speed-boost fallback's value in early runs (fixed 2026-08-23).
import types

import simulate as _sim
from orchestrator import POWER_TACTIC_KINDS
from decision_engine import TacticsType

for _kind in TacticsType:
    _stub = types.SimpleNamespace(kind=_kind, bonus=3)
    _adds_power = _sim.power_bonus(_stub) > 0
    _listed = _kind.value in POWER_TACTIC_KINDS
    assert _adds_power == _listed, (
        f"{_kind.value}: simulate.power_bonus says adds_power={_adds_power} "
        f"but POWER_TACTIC_KINDS says {_listed} — the two encodings of the "
        "same rule have drifted")

assert POWER_TACTIC_KINDS, "no tactics kind adds power — the set is empty"

print(f"OK: POWER_TACTIC_KINDS ({sorted(POWER_TACTIC_KINDS)}) agrees with "
      "simulate.power_bonus across all tactics kinds")


# --- opponent selection must survive an occluded name --------------------
# The "PLAY BALL!" banner covers the opponent card's NAME band from ~0.5s to
# ~2s after reveal onset; 14 of 28 captures in the 2026-08-26 run landed in
# that window. Type banner and power stay legible, so vision returns a bare
# "Batter"/"Pitcher" as the name — which is why 15 of 44 logged rows carry
# that as the opponent. Name-only selection then returned None and the whole
# turn was discarded.
from orchestrator import pick_opponent_card

_P = lambda n, pw: {"kind": "player", "name": n, "power": pw}
_T = {"kind": "tactics", "name": "Power Swing", "bonus": 1}

# Names still win when they can actually separate the two cards.
assert pick_opponent_card([_P("Batter", 7), _P("Rube Sharp", 8)],
                          "Batter", 7, 0)["name"] == "Rube Sharp"

# BOTH names occluded: power must break the tie, in either order.
for _cards in ([_P("Batter", 7), _P("Batter", 8)],
               [_P("Batter", 8), _P("Batter", 7)]):
    _opp = pick_opponent_card(_cards, "Batter", 7, 0)
    assert _opp is not None and _opp["power"] == 8, (
        "both names occluded and power did not identify the opponent — this "
        "is the case that discarded the turn entirely")

# A tactics card must never be mistaken for the opponent's player card.
assert pick_opponent_card([_P("Batter", 7), _P("Batter", 8), _T],
                          "Batter", 7, 0)["power"] == 8

# Abstain rather than guess. A wrong opponent writes a WRONG row, which is
# worse for this dataset than a missing one.
assert pick_opponent_card([_P("Batter", 7), _P("Batter", 7)], "Batter", 7, 0) is None, (
    "two cards of our own power are indistinguishable — picking one fabricates "
    "an opponent")
assert pick_opponent_card([_P("Batter", 4), _P("Batter", 5)], "Batter", 9, 0) is None, (
    "neither revealed card is ours, so which one is 'the opponent' is unknown")
assert pick_opponent_card([_T], "Batter", 7, 0) is None, "no player cards, no opponent"

print("OK: opponent survives an occluded name via power, and abstains when "
      "power cannot separate the cards")


# --- base runners must be stripped from a reveal -------------------------
# This game draws runners as FACE-UP CARDS on the diamond, and the reveal read
# returns them alongside the two faceoff cards. Confirmed live 2026-08-26 at
# 0, 1 and 2 runners across all three bases; the rule held without exception:
#     revealed players == 2 faceoff cards + one per runner on base
# Uncorrected it caused ALL 15 "no OPPONENT card identified" drops of a 30-play
# run — half of every turn played, and worst exactly when the bot is winning.
from orchestrator import exclude_runners

_R = lambda n: {"name": n}

# The real 4-card reveal from that run, with its real runners.
# _P, not C: pick_opponent_card filters on kind == "player", and C omits it.
# Using C here made the strip look broken when it was the fixture that was.
_reveal4 = [_P("Donny Mekesz", 5), _P("William Lee Gains", 7),
            _P("Johnny Drawers", 7), _P("Rube Sharp", 8)]
_runners2 = [_R("Johnny Drawers"), _R("Donny Mekesy")]   # 'Mekesy' as vision read it
_kept = exclude_runners(_reveal4, _runners2)
assert [c["name"] for c in _kept] == ["William Lee Gains", "Rube Sharp"], (
    f"runners not stripped: {[c['name'] for c in _kept]}")

# ...and the whole pipeline, called the way PRODUCTION calls it, must yield an
# opponent. Asserting on `_kept` alone was the bug that hid a dead fix: the
# strip worked, this assertion passed, and production was still handing the
# UNSTRIPPED list to pick_opponent_card — so every runner-on-base turn dropped
# exactly as before. Compose the two calls here, as run() does.
def _production_pick(reveal, runners, ours, power, bonus=0):
    players = [c for c in reveal if c.get("kind") == "player"]
    return pick_opponent_card(exclude_runners(players, runners), ours,
                              our_power=power, bonus=bonus)


_opp = _production_pick(_reveal4, _runners2, "", 7)
assert _opp is not None and _opp["name"] == "Rube Sharp", (
    f"production path yields {_opp} — the runner strip is not reaching "
    "pick_opponent_card")

# Every runner count must survive, since the drop was guaranteed at 1, 2 and 3.
for _n in (1, 2, 3):
    _rs = [_R(n) for n in ["Johnny Drawers", "Donny Mekesy", "Rube Sharp"][:_n]]
    _reveal = [_P("William Lee Gains", 7), _P("Brian Coker", 8)] + [
        _P(r["name"], 6) for r in _rs]
    assert _production_pick(_reveal, _rs, "", 7) is not None, (
        f"with {_n} runner(s) on base the opponent is still undecidable")

# The real 3-card case: one runner on first.
_kept3 = exclude_runners(
    [_P("William Lee-Gains", 7), _P("Johnny Drawers", 7), _P("Donny Mekesz", 5)],
    [_R("Johnny Drawers")])
assert [c["name"] for c in _kept3] == ["William Lee-Gains", "Donny Mekesz"]

# No runners, nothing stripped.
assert exclude_runners(_reveal4, []) == _reveal4
assert exclude_runners(_reveal4, None) == _reveal4

# Must refuse to strip below a faceoff. If every card matched a runner name we
# would be left with nothing to decide on, which is worse than not filtering.
_all_runners = [_R("Donny Mekesz"), _R("William Lee Gains"),
                _R("Johnny Drawers"), _R("Rube Sharp")]
assert exclude_runners(_reveal4, _all_runners) == _reveal4, (
    "filter stripped the faceoff itself instead of backing off")

print("OK: base runners are stripped from reveals, and the filter refuses to "
      "strip below a two-card faceoff")


# --- the power floor inside revealed_powers had NO coverage --------------
# QA 2026-08-26: mutations reverting the floor entirely, and an off-by-one on
# it, both survived the whole suite. 1-3 is the tactics BONUS digit range, so a
# revealed power there is a misread and must read as UNKNOWN, exactly like 0.
assert _rp(C("Zzzz Qqqq", 3)) == set(), (
    "a revealed power of 3 is being treated as a real card — that is a tactics "
    "bonus digit, and trusting it produced 2 of the 5 misfires on 2026-08-26")
assert _rp(C("Zzzz Qqqq", MIN_PLAYER_POWER - 1)) == set(), "off-by-one below the floor"
assert _rp(C("Zzzz Qqqq", MIN_PLAYER_POWER)) == {MIN_PLAYER_POWER}, (
    "the floor is one too high — it is swallowing the weakest legal card")

# And the whole detector must abstain rather than fire on such a reveal.
assert our_card_in_reveal(8, 0, [C("Zzzz Qqqq", 3), C("Yyyy Wwww", 1)]), (
    "every revealed power is a misread, yet the detector still claims our "
    "card is absent")

print("OK: sub-floor revealed powers read as unknown, not as cards")


# --- case-safety must be asserted where it is CLAIMED (V18) --------------
# QA 2026-08-26: gutting norm_name (no lower-casing, no strip) survived both
# this file and test_run_state_machine.py, even though both print "case-safe".
# No fixture in either differed only by case. test_roster_matching.py does
# kill it, so the guarantee holds — but not where these files assert it.
#
# The live defect it prevents: the vision model returned the SAME card as
# "Pitcher" one turn and "PITCHER" the next, and an exact != logged our own
# card as the opponent's.
_MIXED = [_P("BATTER", 7), _P("Rube Sharp", 8)]
assert pick_opponent_card(_MIXED, "batter", our_power=7)["name"] == "Rube Sharp", (
    "our card 'batter' did not match the revealed 'BATTER' — a case-only "
    "difference is being treated as a different card, which logs our own card "
    "as the opponent's")

# Same for the runner strip: the base crop and the reveal disagree on case.
_kept_case = exclude_runners(
    [_P("RUBE SHARP", 8), _P("William Lee Gains", 7), _P("Brian Coker", 8)],
    [_R("Rube Sharp")])
assert [c["name"] for c in _kept_case] == ["William Lee Gains", "Brian Coker"], (
    f"case-only mismatch defeated the runner strip: "
    f"{[c['name'] for c in _kept_case]}")

print("OK: case-only differences are handled where this file claims they are")


# --- an INCOMPLETE reveal read is not evidence of a misfire --------------
# Established 2026-09-01 by replaying center_card_edge_fraction() over the 461
# logged frames of the live match and OPENING all 11 frames it fires on. In
# every one of them our own card is fully face-up at bottom-centre with its
# power badge, secondary badge, type banner and name band all legible — it is
# never hidden behind its own tactics card (those sit BESIDE it), and the
# "PLAY BALL!" banner band (y 508-568) never reaches it (its top edge is
# y >= 560, its power badge y >= 660). The reads are not failing on our card.
#
# What they DO fail on is completeness: 2 player cards came back on turns that
# had 3 on the diamond. exclude_runners() will not strip below two, so the
# runner stays in the list, its power counts as evidence against us, and the
# turn is discarded with a confident "your card is absent" — plus a
# report_misfire() that drove ACTION_DELAY 0.25s -> 0.75s across the run.
from orchestrator import reveal_is_complete


def _production_misfire(reveal, runners, power, bonus=0):
    """True when run() would flag this turn as a suspected misfire.

    Composed exactly as the call site does, for the same reason
    _production_pick above exists: asserting on the pieces is how a dead fix
    stayed hidden for a whole run. The RAW reveal goes to reveal_is_complete
    and the STRIPPED list to our_card_in_reveal — swap those and every
    runner-on turn reads as incomplete.
    """
    players = [c for c in reveal if c.get("kind") == "player"]
    players = exclude_runners(players, runners)
    return bool(players) and reveal_is_complete(reveal, runners) and \
        not our_card_in_reveal(power, bonus, players)


# The three live false misfires, verbatim from /tmp/day8.log with the runner
# each turn's own state read reported. All three are 2-of-3 (or 1-of-3) reads.
for _reveal, _runners, _power, _bonus, _why in (
        ([_P("Jake Baucepan Black", 5), _P("Joel Blunt", 9)],
         [_R("Jake Saucepan Black")], 8, 2,
         "the runner came back and one faceoff card did not"),
        ([_P("Mickey Brown", 5), _P('Brandon "Dinger" Ortiz', 5)],
         [_R('Justin "Cur" Behr')], 8, 1,
         "3 player cards on the diamond, 2 returned"),
        ([_P("Bartholomew Creasley", 5)], [_R("Rube Sharp")], 7, 0,
         "a single card back on a turn logged as 'runners on'")):
    assert not _production_misfire(_reveal, _runners, _power, _bonus), (
        f"incomplete read still produces a confident misfire ({_why})")

# ...and the detector must NOT have gone inert. Both of these are misfires
# CONFIRMED AGAINST THE FRAME: the reveal read was complete and correct, and
# our own card was in it with a power that is not the one we meant to play.
#   r_0141 (13:36:25): PITCHER "Papa Jody Gain" 5 top, BATTER
#   "Daniel 'The Rat-Ta-Train' Cruz" 4/3 bottom — we had played a 7 (+1).
#   r_0455 (13:41:57): PITCHER "Bartholomew Creasley" 5/1 top, BATTER
#   "Jake Saucepan Black" 5/3 bottom — we had played an 8. First turn of a
#   fresh match, so the bases were provably empty.
assert _production_misfire(
    [_P("M.J. Cain", 5), _P('Daniel "The Rat-Za Train" Cruz', 4)], [], 7, 1), (
    "frame-confirmed real misfire (r_0141) no longer fires")
assert _production_misfire(
    [_P("Bartholomew Creasley", 5), _P("Jake Saucepan Black", 5)], [], 8, 0), (
    "frame-confirmed real misfire (r_0455) no longer fires")

# A runner on base must not switch the detector off — only a SHORT read does.
# Three cards back with one runner on is a complete read, and a real mismatch
# in it still has to fire.
assert _production_misfire(
    [_P("Rube Sharp", 8), _P("Mickey Brown", 5), _P("Joel Blunt", 9)],
    [_R("Joel Blunt")], 4, 0), (
    "a complete 3-card read with a runner on base stopped firing — the gate "
    "is keying on 'any runner' instead of on the card count")

# The arithmetic itself, including the off-by-one either side.
assert reveal_is_complete([_P("a", 5), _P("b", 6)], [])
assert reveal_is_complete([_P("a", 5), _P("b", 6)], None), "None runners != 0 runners"
assert not reveal_is_complete([_P("a", 5)], [])
assert not reveal_is_complete([_P("a", 5), _P("b", 6)], [_R("x")])
assert reveal_is_complete([_P("a", 5), _P("b", 6), _P("c", 7)], [_R("x")])
assert not reveal_is_complete([_P("a", 5), _P("b", 6), _P("c", 7)], [_R("x"), _R("y")])
# TACTICS ENTRIES ARE NOT PLAYER CARDS. len(reveal_cards) would call a reveal
# of one player plus two tactics cards "complete" — and a reveal with tactics
# on both sides is exactly when the diamond is most crowded.
assert not reveal_is_complete([_P("a", 5), _T, dict(_T)], []), (
    "tactics cards are being counted toward the player-card total"
)

print("OK: a reveal read that came back short of 2 + one-per-runner player "
      "cards abstains instead of manufacturing a misfire")

# _production_misfire above RE-IMPLEMENTS the call site, so every assertion in
# this block stays green if run() never calls the gate at all. That is not a
# hypothetical: the runner strip shipped exactly that way — the unit assertions
# passed while production handed pick_opponent_card the unstripped list, and a
# whole run's turns dropped as before. run() is 4700 lines into a module that
# needs a live capture to enter, so pin the wiring at the source level.
import inspect as _inspect

import orchestrator as _orch

# getsource(run), NOT getsource(the module): the module text contains
# `def reveal_is_complete(reveal_cards, runners)`, which satisfies a naive
# substring search all by itself. This assertion was written that way first
# and it passed with the gate deleted from the call site — the precise thing
# this file exists to stop.
_run_src = _inspect.getsource(_orch.run)
assert "reveal_is_complete(reveal_cards," in _run_src, (
    "run() no longer gates the misfire check on reveal_is_complete — the fix "
    "is present but dead, which is how the runner strip failed silently")
assert "reveal_is_complete(_players" not in _run_src, (
    "the gate is counting the RUNNER-STRIPPED list; it must count the raw "
    "reveal or every runner-on turn reads as incomplete")

print("OK: the completeness gate is actually wired into run()")
