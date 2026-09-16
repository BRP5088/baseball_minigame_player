"""describe_hand(): always one row per slot, UNKNOWN where nothing read.

Plain asserts on purpose. CLAUDE.md records four different check() signatures in
this suite, and a reversed call to a name-first one prints "PASS True" and can
never fail -- an assert cannot be reversed into a no-op.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import orchestrator as o

P = lambda i, pw, sec: {"kind": "player", "name": None, "power": pw,
                        "secondary": sec, "hand_index": i}
T = lambda i, ty, b: {"kind": "tactics", "name": ty, "type": ty,
                      "bonus": b, "hand_index": i}

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


# 1. A COMPLETE HAND: five rows, no UNKNOWN.
full = [T(0, "power_swing", 1), P(1, 8, 2), P(2, 5, 2), P(3, 5, 3),
        T(4, "speed_boost", 1)]
s = o.describe_hand(full)
want("complete hand has 5 rows", s.count(":") == 5, s)
want("complete hand has no UNKNOWN", "UNKNOWN" not in s, s)

# 2. THE LIVE CASE, 2026-09-15: slots 1 and 4 unreadable, 3 cards returned.
gappy = [T(0, "power_swing", 1), P(2, 5, 2), P(3, 5, 3)]
s = o.describe_hand(gappy)
want("gappy hand still has 5 rows", s.count(":") == 5, s)
want("slot 1 reads UNKNOWN", "1: UNKNOWN" in s, s)
want("slot 4 reads UNKNOWN", "4: UNKNOWN" in s, s)

# 3. THE ANTI-SHIFT CHECK, and the one that makes this test worth having.
#    Rendering by POSITION would put the 5/2 (slot 2) at slot 1 and read as a
#    complete-looking hand that is wrong about every card after the gap.
want("the 5/2 stays at slot 2", "2: 5/2" in s, s)
want("the 5/3 stays at slot 3", "3: 5/3" in s, s)
want("nothing was shifted into slot 1", "1: 5/2" not in s, s)

# 4. AN EMPTY HAND IS FIVE UNKNOWNS, not an empty string -- "nothing read" and
#    "no hand on this screen" must not print identically.
s = o.describe_hand([])
want("empty hand is 5 UNKNOWNs", s.count("UNKNOWN") == 5, s)

# 5. NO hand_index -> refuses to place, rather than guessing.
s = o.describe_hand([{"kind": "player", "power": 8, "secondary": 2}])
want("a card with no hand_index is not given a slot",
     "UNPLACEABLE" in s and "0: " not in s, s)

# 6. want= is honoured, so the row count follows the fan's geometry and is not
#    a literal 5 baked in here.
s = o.describe_hand([P(0, 8, 2)], want=3)
want("want=3 gives 3 rows", s.count(":") == 3, s)

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
