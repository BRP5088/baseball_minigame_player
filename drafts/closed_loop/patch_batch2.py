"""Batch-2 controller changes from trial 3 (2026-09-07 19:2x). APPLY ONLY WHEN NO chain_trials.py IS RUNNING.

1. The 'weak but consistent' rule was VACUOUS: locate() only searches [k-1, k+3] and the target is k+1..k+3,
   so every weak fix is 'within WINDOW of the target' by construction. Trial 3 advanced nine pushes on fits of
   6-7 inliers straight into an NPC on the stairs. Replace with a real gate: inliers >= WEAK_MIN_INLIERS (15,
   provisional: right-but-thin fits in trials 1-3 read 17-36, junk read 6-13; n ~15, re-measure from the
   journals) -- and a weak advance no longer RESETS the blind budget (it neither spends nor restores it).
2. BLIND_MAX 4 -> 6 (1.1 u): the corridor-to-door stretch needed 4-6 pushes without a credible fix.
3. LOST: after LOST_MAX = 9 consecutive iterations with no credible fix once the blind budget is spent (three
   escape cycles), return failure 'lost' at once instead of burning the 400 s cap. Off the route there is
   nothing to match; the harness scores it FAILED and the next trial starts ~300 s sooner.
"""
def rep(s, old, new):
    assert s.count(old) == 1, (s.count(old), old[:90]); return s.replace(old, new)
p = "chain_walk.py"; s = open(p).read()
s = rep(s, "BLIND_MAX = 4\n", '''BLIND_MAX = 6
# A weak fix (under FIX_MIN_INLIERS) still corroborates the plan when it has at
# least this many inliers: right-but-thin fits in trials 1-3 read 17-36, junk
# read 6-13 (n ~ 15, provisional; re-measure from overnight/chain_journals/).
WEAK_MIN_INLIERS = 15
# Consecutive iterations with no credible fix AFTER the blind budget is spent
# before the walk declares itself LOST (three escape cycles). Off the route
# nothing can match; burning the rest of the cap only delays the next trial.
LOST_MAX = 9
''')
s = rep(s, '''        elif weak and abs(int(fix.k) - target_k) <= WINDOW:
''', '''        elif weak and inl >= WEAK_MIN_INLIERS:
''')
s = rep(s, '''            misses = 0
            stalls = 0
            blind = 0
            k = min(target_k, n - 1)
            action = "advanced-weak"
''', '''            misses = 0
            stalls = 0
            lost = 0
            # The blind budget is neither spent nor restored by a thin fit.
            k = min(target_k, n - 1)
            action = "advanced-weak"
''')
s = rep(s, '''    blind = 0                   # consecutive pushes made with no credible fix
''', '''    blind = 0                   # consecutive pushes made with no credible fix
    lost = 0                    # iterations with nothing credible, budget spent
''')
s = rep(s, '''            elif fix is None:
                misses += 1
''', '''            elif fix is None:
                lost += 1
                misses += 1
''')
s = rep(s, '''            else:
                misses = 0
                stalls += 1
                if stalls >= STALL_MAX:
                    action = escape()
                    escaped = True
                    stalls = 0
                else:
                    action = "weak"
        else:
            misses = 0
            blind = 0
''', '''            else:
                lost += 1
                misses = 0
                stalls += 1
                if stalls >= STALL_MAX:
                    action = escape()
                    escaped = True
                    stalls = 0
                else:
                    action = "weak"
            if lost >= LOST_MAX:
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix), "action": "lost", "lateral": None,
                        "at_end": at_end, "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"  chain_walk: LOST — {lost} iterations with nothing "
                    f"credible after the blind budget at k={k} of {n - 1}")
                return finish(f"lost at k={k} of {n - 1}: {lost} iterations "
                              f"with no credible fix after {BLIND_MAX} blind "
                              f"advances")
        else:
            misses = 0
            blind = 0
            lost = 0
''')
s = rep(s, '''        if regressed:
            misses = 0
            stalls = 0
            blind = 0
''', '''        if regressed:
            misses = 0
            stalls = 0
            blind = 0
            lost = 0
''')
open(p, "w").write(s); print("chain_walk.py patched for batch 2")

# ---- tests (tests/routing/test_chain_walk.py is not imported by a running trial child, but keep it with the code)
p = "tests/routing/test_chain_walk.py"; t = open(p).read()
t = rep(t, '''    def test_a_miss_looks_back_and_k_may_regress(self):''', '''    def test_a_junk_fit_is_blindness_and_a_thin_fit_keeps_the_blind_budget(self):
        # Trial 3: nine pushes on 6-7-inlier fits walked into an NPC. Under
        # WEAK_MIN_INLIERS a fix is blindness (spends the budget); a thin fit
        # at or above it advances but neither spends nor restores the budget.
        self.assertEqual(chain_walk.WEAK_MIN_INLIERS, 15)
        self.assertEqual(chain_walk.BLIND_MAX, 6)
        junk = Fix(k=2, inliers=7)
        thin = Fix(k=2, inliers=20)
        fixes = [junk] * 3 + [thin] + [None] * 3 + [None] * 4
        rig = Rig(FakeChain(20, fixes, default=None), table_at=None)
        res = always_turning(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:3], ["blind-advance"] * 3, "junk spends the budget")
        self.assertEqual(acts[3], "advanced-weak")
        # budget so far: 3 spent, the thin fit changed nothing -> 3 blind left
        self.assertEqual(acts[4:7], ["blind-advance"] * 3)
        self.assertNotIn("blind-advance", acts[7:], "the budget was 6, not 6 + 3")

    def test_the_walk_declares_itself_lost_instead_of_burning_the_cap(self):
        self.assertEqual(chain_walk.LOST_MAX, 9)
        rig = Rig(FakeChain(30, default=None), table_at=None)
        res = always_turning(rig.go, time_cap=400.0)
        self.assertFalse(res["arrived"])
        self.assertTrue(res["failure"].startswith("lost at k="), res["failure"])
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:6], ["blind-advance"] * 6)
        self.assertEqual(acts[-1], "lost")
        self.assertEqual(len(acts), 6 + 9, "six blind, nine lost, then out")
        self.assertLess(res["seconds"], 60.0, "gave up long before the cap")

    def test_a_miss_looks_back_and_k_may_regress(self):''')
open(p, "w").write(t); print("tests added")
