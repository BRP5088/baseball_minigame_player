"""patch39: the prompt check is consulted only in the chain's tail.

Tenth launch trial 12 (2026-09-08 00:36): at_table() returned True at k=58
-- the office doorway facing the L&B storefront -- and the walk ended
"arrived" 47 s in. The check had no position gate (TABLE_CHECK_TAIL None,
because under dead reckoning a 3-waypoint tail once made the loop walk away
from a won table when k lagged). Census over every closed-loop arrival on
disk (65): the estimate's target at the moment of arrival was 197-204 on all
64 true ones and 61 on the false one. TABLE_CHECK_TAIL = 30 (targets >= 175 on
this 205-waypoint chain) sits 22 waypoints under the lowest true arrival and
above every place a false positive has fired. Usage: python apply_patch39.py [ROOT].
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "TABLE_CHECK_TAIL = 30" in c:
    raise SystemExit("ALREADY APPLIED")
edits_c = [
 ('''# false positives on 693 frames at non-table nodes (CLAUDE.md §3), so the gate
# bought nothing. An integer here restores the old gate for an experiment.
TABLE_CHECK_TAIL = None
''', '''# false positives on 693 frames at non-table nodes (CLAUDE.md §3), so the gate
# bought nothing. THEN IT DID: 2026-09-08 a detector change fired at k=58 (the
# office doorway facing the L&B storefront) and the walk "arrived" 47 s in.
# at_table() is the $50 gate. Every true closed-loop arrival on disk (64) had
# its target at 197-204 when the prompt appeared; the false one had 61. A tail
# of 30 waypoints (targets >= 175 on the 205-waypoint chain) sits 22 under the
# lowest true arrival, so a lagging estimate has that much room, and no false
# positive anywhere before the bar tables can end a walk.
TABLE_CHECK_TAIL = 30
'''),
]
edits_t_more = [
 ('''        # Literals, not the formula re-expressed. With the prompt checked on
        # every iteration the floor is the iterations k needs to reach the
        # last waypoint at 3 per step: ceil(999 / 3) = 333. The old tail gate
        # (an integer TABLE_CHECK_TAIL) is still honoured when passed.
        # ADVANCE_MAX is 1: every waypoint but the spawn needs an iteration.
        self.assertEqual(chain_walk.min_iterations(1000), 999)
        self.assertEqual(chain_walk.min_iterations(1000, window=3), 333)
        self.assertEqual(chain_walk.min_iterations(1000, tail=3, window=3), 333)
        self.assertEqual(chain_walk.min_iterations(10), 9)
        self.assertEqual(chain_walk.min_iterations(4), 3)
        self.assertEqual(chain_walk.min_iterations(2), 1)
''', '''        # Literals, not the formula re-expressed. With TABLE_CHECK_TAIL 30 the
        # prompt is believed once the target is within 30 of the end, so the
        # floor is one iteration past k reaching n - 31: 1 + ceil(969 / 1) =
        # 970, 1 + ceil(969 / 3) = 324. A chain shorter than the tail has the
        # gate open from the first frame: the floor is 1. An explicit tail is
        # still honoured when passed.
        self.assertEqual(chain_walk.min_iterations(1000), 970)
        self.assertEqual(chain_walk.min_iterations(1000, window=3), 324)
        self.assertEqual(chain_walk.min_iterations(1000, tail=3, window=3), 333)
        self.assertEqual(chain_walk.min_iterations(10), 1)
        self.assertEqual(chain_walk.min_iterations(4), 1)
        self.assertEqual(chain_walk.min_iterations(2), 1)
'''),
]
edits_t = [
 ('''        self.assertIsNone(chain_walk.TABLE_CHECK_TAIL)
''', '''        self.assertEqual(chain_walk.TABLE_CHECK_TAIL, 30)
'''),
 ('''    def test_the_walk_declares_itself_lost_instead_of_burning_the_cap(self):
''', '''    def test_a_prompt_seen_before_the_tail_does_not_end_the_walk(self):
        # Tenth launch trial 12: the prompt check fired at k=58 and the walk
        # "arrived" on the street. On a 205-waypoint chain the check is asked
        # only when the target is >= 175: a prompt "visible" from the fifth
        # capture is ignored until then, and believed at once after.
        self.assertEqual(chain_walk.TABLE_CHECK_TAIL, 30)
        ch = FakeChain(205, default=Fix(k=204))    # every push reaches its target
        rig = Rig(ch, table_at=5)
        res = without_stuck(rig.go, time_cap=10 ** 6)
        self.assertTrue(res["arrived"])
        self.assertGreaterEqual(res["fixes"][-1]["target"], 175, res["fixes"][-1])
        self.assertGreater(res["iterations"], 100, "the walk went on past the early prompt")
        # and a short chain is unaffected: n - 30 < 0, the gate is always open
        rig2 = Rig(FakeChain(6, [Fix(k=1)]), table_at=1)
        self.assertTrue(rig2.go()["arrived"])

    def test_the_walk_declares_itself_lost_instead_of_burning_the_cap(self):
'''),
]
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", c.count(a))
# the None pin appears in TWO tests (the every-iteration test and the min_iterations one): both move to 30
assert t.count(edits_t[0][0]) == 2, ("test anchor", edits_t[0][0][:50], t.count(edits_t[0][0]))
for a, b in edits_t[1:]: assert t.count(a) == 1, ("test anchor", a[:50], t.count(a))
for a, b in edits_t_more: assert t.count(a) == 1, ("test anchor (more)", a[:50], t.count(a))
for a, b in edits_c: c = c.replace(a, b)
t = t.replace(edits_t[0][0], edits_t[0][1])
for a, b in edits_t[1:]: t = t.replace(a, b)
for a, b in edits_t_more: t = t.replace(a, b)
open(C, "w").write(c); open(T, "w").write(t); print("patch39 applied to", ROOT)
