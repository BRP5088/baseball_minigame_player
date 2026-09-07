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

# ---- 4. TURN STOPS ARE VERIFIED (the user's correction, 2026-09-07 19:35: no NPC blocked the stairs).
# Trial 3 took the plan's turn stop at the door on thin/blind pushes while the character was still short of
# the door, so turning north faced the office, not the staircase. A turn stop's own chain frame is a picture:
# after turning, match it; if nothing credible fits, turn back to the walking heading, push once more, and
# retry the turn (up to TURN_RETRY_MAX). Diagnosis "an NPC on the stairs" was WRONG and is withdrawn.
s = open("chain_walk.py").read()
s = rep(s, "LOST_MAX = 9\n", '''LOST_MAX = 9
# A turn stop is verified against its own frame after the turn; if nothing
# credible fits, the loop turns back, pushes once more along the walking
# heading and retries, this many times, before accepting the turn unverified.
TURN_RETRY_MAX = 3
''')
s = rep(s, '''    lost = 0                    # iterations with nothing credible, budget spent
''', '''    lost = 0                    # iterations with nothing credible, budget spent
    turn_retries = 0            # retries spent on the current turn stop
    walk_heading = None         # the last heading a push was made along
''')
s = rep(s, '''        if do_push:
            push(PUSH_MAG, PUSH_SEC)
            res["pushes"] += 1
''', '''        if do_push:
            push(PUSH_MAG, PUSH_SEC)
            res["pushes"] += 1
            if heading is not None:
                walk_heading = heading
''')
s = rep(s, '''        if not do_push:
            # A turn-only target: a stationary run in the recording (a corner,
            # a settle). Turned on the spot, reached by construction, no locate.
            k = target_k
            misses = 0
            stalls = 0
            record({"iteration": iteration, "k": k, "target": target_k,
                    "fix": None, "action": "turned", "lateral": None,
                    "at_end": False, "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turned"
                f"{'' if turned else ' (skipped, same heading)'} to {heading}")
            continue
''', '''        if not do_push:
            # A turn-only target: a stationary run in the recording (a corner,
            # a settle). VERIFIED against the stop's own frame: if nothing
            # credible fits after the turn, the plan reached this stop on thin
            # or blind pushes while the character is still short of it (trial
            # 3 turned north into the office instead of onto the stairs), so
            # turn back, push once more along the walking heading, and retry.
            fix_t = chain.locate(img, target_k)
            inl_t = 0 if fix_t is None else (getattr(fix_t, "inliers", 0) or 0)
            verified = fix_t is not None and inl_t >= FIX_MIN_INLIERS
            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None):
                turn_retries += 1
                turn_to(walk_heading)
                last_cmd = walk_heading
                push(PUSH_MAG, PUSH_SEC)
                res["pushes"] += 1
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_t), "action": "turn-retry",
                        "lateral": None, "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turn-retry "
                    f"{turn_retries}/{TURN_RETRY_MAX}: the stop's frame did not "
                    f"fit ({inl_t} inliers); one more push along {walk_heading:.1f}")
                continue
            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            action = "turned" if verified else "turned-unverified"
            record({"iteration": iteration, "k": k, "target": target_k,
                    "fix": _fix_row(fix_t), "action": action, "lateral": None,
                    "at_end": False, "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action}"
                f"{'' if turned else ' (skipped, same heading)'} to {heading}"
                f"  ({inl_t} inliers at the stop)")
            continue
''')
open("chain_walk.py", "w").write(s); print("turn-stop verification patched")

t = open("tests/routing/test_chain_walk.py").read()
t = rep(t, '''    def test_a_miss_looks_back_and_k_may_regress(self):''', '''    def test_a_turn_stop_that_does_not_match_is_retried_after_one_more_push(self):
        # Chain: spawn, 2 walking frames east (90), a stop turning to 0, then
        # walking north. The first time the loop reaches the stop its frame
        # does not fit (weak): it turns BACK to 90, pushes once, then retries
        # the stop; the second time it fits and the plan proceeds north.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual(chain_walk.plan_indices(wps),
                         [(1, True, 90.0), (3, False, 0.0), (4, True, 0.0), (5, True, 0.0)])
        # locate calls in order: it1 push -> Fix(k=1); it2 turn-verify -> weak;
        # it3 (after the retry push) turn-verify -> credible; it4 push -> Fix(4)
        ch = FakeChain(6, [Fix(k=1), Fix(k=3, inliers=8), Fix(k=3, inliers=90),
                           Fix(k=4), Fix(k=5)])
        ch.waypoints = wps
        rig = Rig(ch, table_at=6)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:4], ["advanced", "turn-retry", "turned", "advanced"])
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns, [90.0, 0.0, 90.0, 0.0],
                         "turn to the stop, back to the walking heading, then the stop again")
        self.assertEqual(rig.chain.locate_calls[1:3], [3, 3],
                         "the stop is verified against its OWN index")
        self.assertTrue(res["arrived"])

    def test_a_turn_stop_is_accepted_unverified_after_the_retries(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(4, [Fix(k=1)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=8.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "turn-retry", "turn-retry", "turn-retry", "turned-unverified"])
        self.assertEqual(chain_walk.TURN_RETRY_MAX, 3)

    def test_a_miss_looks_back_and_k_may_regress(self):''')
open("tests/routing/test_chain_walk.py", "w").write(t); print("turn-stop tests added")
