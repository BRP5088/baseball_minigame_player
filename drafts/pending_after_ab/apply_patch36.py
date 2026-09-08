"""patch36: no retry pushes at a stop when the last credible fit had WALL scale.

The fast-vs-slow study (agent_progress/closed-loop/fast_runs/notes.md): the
slow arrivals lose their time at stops 88 and 129, where the stop's frame
fits nothing, three retry pushes along the old heading find nothing, the
stop is accepted unverified and the escape ladder runs anyway (30-45 s).
Both such stalls carried a last credible fit at scale 2.62 and 2.21 -- the
character was pressed close to something (WALL_SCALE 2.5 is _blind_cap's own
"a wall a push away" signal) -- while the two retries that legitimately
helped (stop 39) carried 1.12-1.18. The ab4 trial 6 reader saw the same at
166: retries with the looks reading +518..+810 px, accepted at 12 inliers,
then a wedge in a dartboard alcove. Usage: python apply_patch36.py [ROOT].
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "last_cred_scale < WALL_SCALE" in c:
    raise SystemExit("ALREADY APPLIED")
edits_c = [
 ('''            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None and not early_stop):
''', '''            # ... and none when the last credible fit had WALL scale: pressed
            # close to something, three pushes along the old heading found
            # nothing at stops 88 and 129 in every slow arrival tonight, and
            # the ladder ran anyway (fast_runs/notes.md). The retries that
            # helped carried scale 1.1-1.2.
            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None and not early_stop
                    and last_cred_scale < WALL_SCALE):
'''),
]
edits_t = [
 ('''    def test_an_unverified_stop_looks_left_and_right_before_giving_up(self):
''', '''    def test_no_retry_pushes_at_a_stop_after_a_wall_scale_fit(self):
        # The same stop as above, but the last credible fit before it read
        # scale 2.9 (pressed close to something): the retry pushes along the
        # old heading are skipped and the stop is accepted unverified at once.
        # The control is the test above (scale 1.0: three retries).
        self.assertEqual(chain_walk.WALL_SCALE, 2.5)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(4, [Fix(k=1, scale=2.9, inliers=90)], default=Fix(k=1, inliers=9))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=14.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertNotIn("turn-retry", acts, acts)
        self.assertEqual(acts[:2], ["advanced", "turned-unverified"], acts)

    def test_an_unverified_stop_looks_left_and_right_before_giving_up(self):
'''),
]
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", t.count(a))
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
open(C, "w").write(c); open(T, "w").write(t); print("patch36 applied to", ROOT)
