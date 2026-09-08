"""Batch-4 trial 8: a stop whose frame fits NOTHING is occluded or already passed, not reached short. APPLY WHEN NO TRIAL RUNS.

Evidence: when the loop was short of the door stop (batches 1-4) the stop's frame fitted an EARLIER waypoint
(the corridor still ahead: 28, 14, 10, 8 inliers at k < stop). When Wanda stood in its face at the bar stop
(batch 4 trial 8) the frame fitted nothing (None, then 6 inliers at k=128, then None) and the three retry
pushes walked into her and past the spot. Retry only on evidence of being short.
"""
def rep(s, old, new):
    assert s.count(old) == 1, (s.count(old), old[:90]); return s.replace(old, new)
p = "chain_walk.py"; s = open(p).read()
s = rep(s, "TURN_RETRY_MAX = 3\n", '''TURN_RETRY_MAX = 3
# A retry (turn back, one more push) needs EVIDENCE of being short: the stop's
# frame fitting an EARLIER waypoint, however thinly. A frame that fits nothing
# is an occluded view or a stop already passed (batch 4 trial 8: Wanda the
# camera mouse in the loop's face at the bar-entrance stop; three retry pushes
# walked into her and past the spot). Then: turn and go on.
''')
s = rep(s, '''            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None):
''', '''            short = (not verified and fix_t is not None
                     and int(getattr(fix_t, "k", target_k)) < target_k)
            if not verified and not short:
                k = target_k
                misses = 0
                stalls = 0
                turn_retries = 0
                why = "occluded" if fix_t is None else "past"
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_t), "action": f"turned-{why}",
                        "lateral": None, "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turned-{why} "
                    f"to {heading}: the stop's frame fits "
                    f"{'nothing' if fix_t is None else f'waypoint {int(fix_t.k)} at {inl_t} inliers'}"
                    f", no evidence of being short")
                continue
            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None):
''')
open(p, "w").write(s); print("chain_walk.py: retry only on evidence of being short")
t = open("tests/routing/test_chain_walk.py").read()
# the existing retry test: the stop's frame must fit an EARLIER waypoint to count as short
t = rep(t, '''        ch = FakeChain(6, [Fix(k=1), Fix(k=3, inliers=8), Fix(k=3, inliers=90),
                           Fix(k=4), Fix(k=5)])''', '''        ch = FakeChain(6, [Fix(k=1), Fix(k=2, inliers=8), Fix(k=3, inliers=90),
                           Fix(k=4), Fix(k=5)])''')
t = rep(t, '''        # locate calls in order: it1 push -> Fix(k=1); it2 turn-verify -> weak;
        # it3 (after the retry push) turn-verify -> credible; it4 push -> Fix(4)''',
           '''        # locate calls in order: it1 push -> Fix(k=1); it2 turn-verify -> a thin
        # fit to the EARLIER waypoint 2 (evidence of being short); it3 (after
        # the retry push) turn-verify -> credible; it4 push -> Fix(4)''')
t = rep(t, '''    def test_a_turn_stop_is_accepted_unverified_after_the_retries(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(4, [Fix(k=1)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=8.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "turn-retry", "turn-retry", "turn-retry", "turned-unverified"])
        self.assertEqual(chain_walk.TURN_RETRY_MAX, 3)''', '''    def test_a_turn_stop_is_accepted_unverified_after_the_retries(self):
        # Every verify fits an EARLIER waypoint thinly: three retries, then
        # the turn is accepted unverified.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(4, [Fix(k=1)], default=Fix(k=1, inliers=9))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=8.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "turn-retry", "turn-retry", "turn-retry", "turned-unverified"])
        self.assertEqual(chain_walk.TURN_RETRY_MAX, 3)

    def test_a_stop_whose_frame_fits_nothing_is_occluded_not_short(self):
        # Batch 4 trial 8: an NPC in the face. No fit at the stop -> no retry
        # push; turn and go on.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(5, [Fix(k=1), None, Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=5)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned-occluded"])
        self.assertNotIn("turn-retry", acts)
        self.assertEqual(rig.count("push"), 3, "no retry push: 1 + 2 walking + the arrival push")

    def test_a_stop_whose_frame_fits_a_later_waypoint_is_passed_not_short(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(5, [Fix(k=1), Fix(k=3, inliers=9), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=5)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turned-past")
        self.assertNotIn("turn-retry", acts)''')
open("tests/routing/test_chain_walk.py", "w").write(t); print("tests patched")
