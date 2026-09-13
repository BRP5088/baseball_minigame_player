"""A CARD IS A BATTER OR A PITCHER, AND `secondary` MEANS A DIFFERENT STAT IN EACH.

The user, 2026-09-13: "it might be useful to also read the players type, so you don't mark
a pitcher with speed since that doesn't make sense." Until then PlayerCard had no role and
simulate dealt all 33 cards in both directions, so a pitcher could be dealt as a batter and
_step read its FIELDING as SPEED. Every speed and fielding number the model produced before
that was computed on a scrambled pool.

THE RANGES ARE DISJOINT WHERE IT MATTERS, measured over 131 HAND-LABELLED cards split by
whether the hand they came from was a batting or a pitching hand (human labels, so not a
reader marking its own homework):

    batters   speed     1 x14   2 x14   3 x38    n=66   NEVER 0
    pitchers  fielding  0 x39   1 x23   2 x3     n=65   NEVER 3

That is what makes secondary 0 -> pitcher and 3 -> batter a sound inference, and it is why
the pools below are checked against those bounds rather than against a count.

THE ROLES CAME FROM FOUR INDEPENDENT SIGNALS AND NONE DISAGREED: the ban-grid banner read
by OCR, the range rule above, the user reading cards off a ban grid, and "a card seen on a
BASE is a batter" (runners belong to the batting side). 31 of 33; the two left are UNTYPED.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, random, collections
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import simulate as s
from decision_engine import PlayerCard

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


print("1. the roster carries roles, and the two ranges are disjoint as measured")
roles = collections.Counter(getattr(c, "role", "") or "untyped" for c in s.CARD_POOL)
check(len(s.CARD_POOL) == 33, f"33 cards ({len(s.CARD_POOL)})")
check(roles["batter"] >= 15 and roles["pitcher"] >= 16,
      f"typed both ways: {dict(roles)}")
bats = [c for c in s.CARD_POOL if getattr(c, "role", "") == "batter"]
pits = [c for c in s.CARD_POOL if getattr(c, "role", "") == "pitcher"]
# LITERALS from the hand-label census, not from the pool that is being checked.
check(all(1 <= c.secondary <= 3 for c in bats),
      "every batter's SPEED is 1-3 (66 hand-labelled batter cards were never 0)")
check(all(0 <= c.secondary <= 2 for c in pits),
      "every pitcher's FIELDING is 0-2 (65 hand-labelled pitcher cards were never 3)")
check(min(c.secondary for c in bats) != 0, "...so no batter has speed 0")
check(max(c.secondary for c in pits) != 3, "...and no pitcher has fielding 3")

print("2. UNTYPED is named and small, so the residual is countable")
check(s.UNTYPED == ("Brian Coker", "Zachary Lee"),
      f"exactly the two cards never seen on a ban grid: {s.UNTYPED}")
check(len(s.UNTYPED) == 2,
      "if this grows, roles were lost; if it shrinks, two cards were typed — either way "
      "re-derive, do not edit the literal")

print("3. no hand is ever dealt a card of the wrong role")
random.seed(7)
wrong = collections.Counter()
dealt = refilled = 0
for _ in range(3000):
    for phase, want in (("batting", "batter"), ("pitching", "pitcher")):
        players, tactics = s.draw_hand(phase)
        # PLAY A CARD FIRST, or refill_hand's filter is never exercised: draw_hand already
        # returns a full five, so the top-up loop does not run and a mutant that deletes
        # the filter SURVIVES. It did, on the first sweep of this file.
        if players:
            players.pop()
        refilled += 1
        players, tactics = s.refill_hand(players, tactics, phase)
        players = s.replace_weakest(players, s.CARD_POOL, phase)
        for c in players:
            dealt += 1
            r = getattr(c, "role", "")
            if r and r != want:
                wrong[(phase, c.name, r)] += 1
check(dealt > 10000, f"the loop actually dealt cards ({dealt}) — an empty sweep passes")
check(refilled > 5000, f"...and refill_hand was given a SHORT hand {refilled} times, so its filter actually ran")
check(not wrong, f"zero wrong-role cards across draw/refill/discard ({sum(wrong.values())} "
                 f"bad: {dict(list(wrong.items())[:3])})")

print("4. THE CONTROL: filtering must not empty a pool it cannot type")
blind = [PlayerCard("A", 5, 1), PlayerCard("B", 6, 2)]          # no roles at all
check(len(s.for_phase(blind, "batting")) == 2 and len(s.for_phase(blind, "pitching")) == 2,
      "an all-untyped pool survives both phases — a filter that empties the pool would "
      "make sections 1-3 pass while the simulator drew nothing")
only_bat = [c for c in s.CARD_POOL if getattr(c, "role", "") == "batter"]
check(len(s.for_phase(only_bat, "pitching")) == len(only_bat),
      "and a pool with NO card of the wanted role falls back rather than returning empty")

print("5. the role reaches the pools the halves actually draw from")
b = s.for_phase(s.CARD_POOL, "batting")
p = s.for_phase(s.CARD_POOL, "pitching")
check(all(getattr(c, "role", "") in ("batter", "") for c in b), "batting pool is batters")
check(all(getattr(c, "role", "") in ("pitcher", "") for c in p), "pitching pool is pitchers")
check(len(b) < len(s.CARD_POOL) and len(p) < len(s.CARD_POOL),
      f"and both are SMALLER than the whole roster ({len(b)}, {len(p)} of "
      f"{len(s.CARD_POOL)}) — equal sizes would mean the filter did nothing")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
