"""patch35: a stop reached by turn-early takes no retry pushes.

Third pan A/B, trial 3 (23:2x): turn-early fired at k=109 (Wanda in the
face), the stop's frame fit nothing, and the stop's verification then pushed
NORTH three more times along the old heading (turn-retry 1/3..3/3, 0 inliers)
-- into her -- before accepting the turn. The user: "they moved too close to
Wanda and got stuck on the right side of her ... they should have never
gotten stuck." The retries exist for evidence of being SHORT of a stop; an
early turn has none by construction. Usage: python apply_patch35.py [ROOT].
All anchors asserted for both files before any write; refuses a second run.
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "early_stop" in c:
    raise SystemExit("ALREADY APPLIED")
edits_c = [
 ('''    turned_early = False        # this blockage has already taken its early turn
''', '''    turned_early = False        # this blockage has already taken its early turn
    early_stop = False          # the current stop was reached by turn-early: no retry pushes
'''),
 ('''                pi = near_stop_j
                turned_early = True
''', '''                pi = near_stop_j
                turned_early = True
                early_stop = True
'''),
 ('''            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None):
''', '''            # A stop reached by turn-early gets NO retry pushes: the retries are
            # for evidence of being short, and an early turn was taken BECAUSE
            # nothing fits (an NPC in the face). Pushing along the old heading
            # there walked into her three more times (third A/B, trial 3).
            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None and not early_stop):
'''),
 ('''            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            waited_here = False
            backed_here = False
''', '''            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            waited_here = False
            backed_here = False
            early_stop = False
'''),
 ('''                    stalls = 0
                    turn_retries = 0
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(wide), "action": "relocalised",
''', '''                    stalls = 0
                    turn_retries = 0
                    early_stop = False
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(wide), "action": "relocalised",
'''),
 ('''                turn_retries = 0
                unverified_turn = True          # accepted on thin evidence
''', '''                turn_retries = 0
                early_stop = False
                unverified_turn = True          # accepted on thin evidence
'''),
]
edits_t = [
 ('''        self.assertIn("turned-unverified", acts)
        after = acts[acts.index("turned-unverified"):]
        self.assertIn("escape:jump", after,
                      "the ladder takes over once the early turn is spent")
        self.assertNotIn("turn-early", after)
''', '''        self.assertIn("turned-unverified", acts)
        # An early stop takes NO retry pushes along the old heading (they
        # walked into the NPC three more times live): back, wait, accept.
        seg = acts[acts.index("turn-early"):acts.index("turned-unverified")]
        self.assertNotIn("turn-retry", seg, seg)
        self.assertEqual(seg, ["turn-early", "turn-back", "turn-wait"], seg)
        after = acts[acts.index("turned-unverified"):]
        self.assertIn("escape:jump", after,
                      "the ladder takes over once the early turn is spent")
        self.assertNotIn("turn-early", after)
'''),
]
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", a[:70], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a[:70], t.count(a))
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
open(C, "w").write(c); open(T, "w").write(t); print("patch35 applied to", ROOT)
