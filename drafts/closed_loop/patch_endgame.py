"""Batch 5b trial 3 (lost through the bar's back door): two endgame rules. APPLY WHEN NO TRIAL RUNS.

1. PAST_SCALE: a credible fit at k (the waypoint behind the target) with scale >= 1.6 means the character is
   well past that waypoint: count it as reaching the target instead of 'stalled'. Trial 3 stalled at 166
   with scales 2.1 and 2.6 while standing at ~181, then went blind and dead-reckoned into the back door.
   Arriving trials advanced through the same stretch at scales 1.0-1.5 on credible fixes.
2. END_TAIL_TARGETS / END_BLIND_MAX: inside the last 6 plan targets a blind push is capped at 2 (not 6):
   past the last stop, overshooting means the back door, and the prompt check plus the look-around are the
   right search there, not more forward pushes.
"""
def rep(s, old, new):
    assert s.count(old) == 1, (s.count(old), old[:90]); return s.replace(old, new)
p = "chain_walk.py"; s = open(p).read()
s = rep(s, "BLIND_MAX = 6\n", '''BLIND_MAX = 6
# Inside the last END_TAIL_TARGETS plan targets a blind push is capped at
# END_BLIND_MAX: past the final stop, overshooting means the bar's back door
# (batch 5b trial 3, 2026-09-07 20:20), and the prompt check runs every
# iteration anyway.
END_TAIL_TARGETS = 6
END_BLIND_MAX = 2
# A credible fit at the waypoint BEHIND the target whose scale says the scene
# is this much larger than in that frame means the character is well past it:
# count it as reaching the target. Arriving trials advanced through the bar at
# scales 1.0-1.5; trial 3 stalled at 166 with 2.1 and 2.6 while at ~181.
PAST_SCALE = 1.6
''')
s = rep(s, '''            if chain.reached(fix, target_k) and new_k > k:
                k = new_k
                stalls = 0
                action = "advanced"
''', '''            past = (int(fix.k) == k and (getattr(fix, "scale", 1.0) or 1.0) >= PAST_SCALE)
            if past and new_k <= k:
                new_k = min(target_k, n - 1)
            if (chain.reached(fix, target_k) or past) and new_k > k:
                k = new_k
                stalls = 0
                action = "advanced-past" if past and not chain.reached(fix, target_k) else "advanced"
''')
s = rep(s, '''            elif blind < BLIND_MAX and not at_end:
                blind += 1
''', '''            elif blind < (END_BLIND_MAX if pi >= len(plan) - END_TAIL_TARGETS else BLIND_MAX) and not at_end:
                blind += 1
''')
open(p, "w").write(s); print("chain_walk.py: PAST_SCALE advance, endgame blind cap")
t = open("tests/routing/test_chain_walk.py").read()
t = rep(t, '''    def test_a_miss_looks_back_and_k_may_regress(self):''', '''    def test_a_credible_fit_behind_the_target_with_a_large_scale_advances(self):
        self.assertEqual(chain_walk.PAST_SCALE, 1.6)
        # fix says k=0 but the scene is 2.1x larger than in frame 0: past it.
        ch = FakeChain(8, [Fix(k=0, scale=2.1, inliers=90), Fix(k=1, scale=2.4, inliers=80),
                           Fix(k=2, scale=1.2, inliers=80)], default=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=3.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts, ["advanced-past", "advanced-past", "stalled"])
        self.assertEqual([f["k"] for f in res["fixes"]], [1, 2, 2])

    def test_blind_pushes_are_capped_at_two_in_the_last_targets(self):
        self.assertEqual((chain_walk.END_TAIL_TARGETS, chain_walk.END_BLIND_MAX), (6, 2))
        # k starts at 10 of a 12-waypoint chain via credible fixes, then the
        # sensor goes blind: only two blind pushes, then misses.
        fixes = [Fix(k=i) for i in range(1, 6)]
        ch = FakeChain(12, fixes, default=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced"] * 5)
        self.assertEqual(acts[5:7], ["blind-advance"] * 2)
        self.assertEqual(acts[7], "miss", "the third blind push inside the tail is refused")

    def test_a_miss_looks_back_and_k_may_regress(self):''')
open("tests/routing/test_chain_walk.py", "w").write(t); print("tests added")
