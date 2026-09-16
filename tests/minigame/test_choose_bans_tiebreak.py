"""choose_bans must break a power tie on `secondary`, worst card first.

Sorting on power alone left ties to the SCAN ORDER. On the live collection
read 2026-09-16 that banned two 4/3 cards and kept a 4/1 and a 4/2 -- the
engine threw away the best of the weak cards and kept the worst.

`secondary` settles it with no role plumbing, because higher is better in
BOTH of its meanings: SPEED on a batter is bases run, FIELDING on a pitcher
subtracts runner movement. So ascending (power, secondary) is worst-first
either way.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from decision_engine import PlayerCard, choose_bans

fails = []


def check(ok, msg):
    # (ok, msg) order -- see CLAUDE.md on this suite's four check() signatures.
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


# The live collection, 2026-09-16, in the order the scan returned it -- so the
# tie-break has to fight scan order rather than agree with it.
LIVE = [
    PlayerCard("Brandon Ortiz", 5, 2),
    PlayerCard("Joshua Diaz", 4, 0),
    PlayerCard("Justin Young", 6, 0),
    PlayerCard("Johnny Sweets", 4, 3),
    PlayerCard("Charlie Pepper", 8, 0),
    PlayerCard("Rube Sharp", 8, 1),
    PlayerCard("William Brown", 4, 3),
    PlayerCard("Jeremiah Curd", 7, 0),
    PlayerCard("Marian Bunz-Twarog", 4, 1),
    PlayerCard("Jedediah Wetters", 4, 2),
    PlayerCard("Timmeh Rattycum", 4, 3),
    PlayerCard("Joe Jody Gain", 6, 0),
    PlayerCard("Papa Jody Gain", 5, 0),
    PlayerCard("Daniel Cruz", 4, 3),
    PlayerCard("Joel Blunt", 9, 0),
]

picked = [c.name for c in choose_bans(LIVE)]

# The three literal names the correct ordering produces. Pinned as literals,
# NOT recomputed from a sort -- a test that re-derives the answer with the
# expression under test passes no matter what that expression is (10.11).
check(picked == ["Joshua Diaz", "Marian Bunz-Twarog", "Jedediah Wetters"],
      f"live collection bans the three genuinely weakest: {picked}")

# The specific regression: a max-secondary card must not be banned while a
# lower-secondary card of the SAME power survives.
check("Johnny Sweets" not in picked and "William Brown" not in picked,
      "no 4/3 card is banned while a 4/1 and a 4/2 are still in the deck")

# Direction, stated as its own fact so a reversed comparator cannot pass by
# happening to match the list above.
two = [PlayerCard("low", 4, 0), PlayerCard("high", 4, 3)]
check([c.name for c in choose_bans(list(reversed(two)), count=1)] == ["low"],
      "on a straight tie the LOWER secondary is banned, whatever the input order")

# Power still dominates: a 4/3 goes before a 5/0, so the tie-break cannot
# have been promoted above the primary key.
mixed = [PlayerCard("five", 5, 0), PlayerCard("four", 4, 3)]
check([c.name for c in choose_bans(mixed, count=1)] == ["four"],
      "power still outranks secondary -- a 4/3 is banned before a 5/0")

check(len(choose_bans(LIVE, count=3)) == 3, "count is honoured")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
