"""patch46: STOP_YAW_NEAR_FIT_ONLY -- the stop yaw only where its formula holds.

WHAT THE YAW ASSUMES. `px = dx + ddeg * PX_PER_DEG` (chain_walk, the look-around
branch) un-rotates the look's own offset back to the walking heading. It assumes
the frame that matched IS the stop's frame: `dx` is read against the recording's
waypoint, and `ddeg` is the angle the camera was turned to see it. A fit two or
three waypoints PAST the stop is a different pose of the recording, so the sum
answers about somewhere the character is not -- and it does so in one direction,
which is what a census can see.

THE CENSUS, AND WHY IT IS A NAMED POPULATION RATHER THAN A GLOB. The first
version of this evidence globbed `overnight/chain_journals/` -- a directory the
LIVE batch writes into. Two runs two minutes apart returned 41 and 42 rows, and
the counts quoted here were stale before they were read, because batch 23 was
appending firings underneath (skeptic 1, 2026-09-08). CLAUDE.md's own rule --
a test must never glob a directory a live run writes to, name the files -- holds
for evidence one level up. The population is now closed at both ends and named
in `drafts/pending_after_ab/patch46_yaw_firings.json` (120 journals, a sha256
each); `patch46_yaw_census.py` recounts from it in one command and reports drift.

    120 journals, 39 firings, 2026-09-08 05:36-09:09 (ending with the last
    trial of batch 22), scored on the FIRST CREDIBLE FIT (>= FIX_MIN_INLIERS,
    29) in the five rows after the yaw:

    bar entrance, stop 129, look fit within +-1 (k 128/129/130)
        22 firings   dx after the yaw  -232..+263, |dx| median 96.5, BOTH SIGNS
                     (14 positive, 8 negative), 20 of 22 ARRIVED
    bar entrance, stop 129, look fit +2 / +3 (k 131/132)
         6 firings   dx after the yaw  +141 +150 +188 +225 +227 +230
                     ALL POSITIVE, 4 of 6 ARRIVED; the two losses are
                     b21 t13 (t13_1788869023) and b21 t17 (t17_1788869429),
                     each blind into geometry in the rows straight after
                     (agent_progress/closed-loop/review/notes_t13.md)

The fit-ahead rows sit at the extreme of the yaw range (-20.1..-25.1 deg against
-9.4..-23.8 deg for the fits at the stop) and leave +141..+230 px of the yaw's
own sign reversed -- an OVER-TURN of 29-57% of itself on six firings out of six.
Where the fit is at the stop the leftover is unbiased, which is the shape a
correction that landed has. So the condition is STRUCTURAL, not a tuned
threshold: the gate asks the one question the formula needs answered.

WHAT IT DOES. `STOP_YAW_NEAR_FIT_ONLY` (ships False) requires the look's fit
index to be within `STOP_YAW_FIT_TOL` = 1 of the stop's own index before the
yaw may fire. When it is not, the EXISTING strafe path runs -- the pre-patch44
path, byte for byte, same seconds, same side, same record -- plus a
`yaw_skipped` marker in the journal and a sibling log line, so a stop the gate
sent to the strafe is distinguishable from a stop the flag was simply off for
(10.1: a no-op and a working path must not have identical output).

WHAT IT IS NOT. It is not a special case for one stop, and the census does not
pretend the signal is everywhere. The over-turn signature is at stop 129 ONLY:
at the stairs stop 39 the look fits +3 on 8 of 9 firings, the yaws asked are
half the size (-104..-210 px against -396..-494), and the leftovers are -9..+174
-- BOTH SIGNS, i.e. no over-turn signature at all, 5 of 8 arrived. The flag
sends those eight to the strafe too, deliberately, on a rule whose evidence is
at 129; whether that costs anything is exactly what the A/B is for. No physical
constant moves, no guard is removed, the pan branch / the head-on path / the end
turn / the rescue are untouched, and the harness needs no change:
`overnight/chain_trials.py:apply_arm` arms any boolean chain_walk attribute, so
`--arms off,on --flag STOP_YAW_NEAR_FIT_ONLY` is the measurement.

VERIFIED on a scratch copy of the checkout (cp, never ln; 10.16a) before
delivery: tests/routing/test_chain_walk.py 185 -> 192 tests, all green, and
eight mutants each caught by a named test -- including the one that survived
the 191-test build this patch shipped first, the marker guard's own px check
(see agent_progress/closed-loop/yaw_fit_gate/progress.md).
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read()
t = open(T).read()
if "STOP_YAW_NEAR_FIT_ONLY" in c or "STOP_YAW_NEAR_FIT_ONLY" in t:
    raise SystemExit("ALREADY APPLIED")

# ---------------------------------------------------------------- chain_walk
edits_c = [
 # (1) the two constants, beside the flag they qualify.
 ("""STOP_LOOK_YAW = True
# A stop whose frame and both looks fit NOTHING is most likely an NPC in the
""",
  '''STOP_LOOK_YAW = True
# ... AND THE UN-YAW ONLY MEANS ANYTHING WHEN THE LOOK FOUND THE STOP ITSELF.
# `px = dx + ddeg * PX_PER_DEG` assumes the frame that matched IS the stop's
# frame. A fit two or three waypoints PAST the stop is a different pose of the
# recording, so the sum answers about somewhere the character is not.
#
# THE CENSUS IS A NAMED POPULATION, NOT A GLOB. overnight/chain_journals/ is
# written by the LIVE batch: globbing it returned 41 rows and then 42 two
# minutes later, so counts taken that way are stale before they are read
# (CLAUDE.md's "name the fixture files", one level up). The 120 journals of
# 2026-09-08 05:36-09:09, ending with the last trial of batch 22, are listed
# with a sha256 each in drafts/pending_after_ab/patch46_yaw_firings.json and
# recounted by patch46_yaw_census.py beside it. 39 firings, each scored on the
# first credible fit (>= FIX_MIN_INLIERS) in the five rows after it:
#
#   stop 129, look fit within +-1   22 firings   dx -232..+263, BOTH SIGNS
#                                                (14 pos, 8 neg), 20 ARRIVED
#   stop 129, look fit +2 / +3       6 firings   dx +141..+230, ALL POSITIVE
#                                                4 ARRIVED; the two losses
#                                                (b21 t13, t17) went blind into
#                                                geometry in the rows after
#   stop  39, look fit +3            8 firings   dx -9..+174, BOTH SIGNS
#   stops 39 / 166 / 196 at the stop 3 firings
#
# A leftover that keeps the yaw's own sign reversed on six firings out of six is
# an OVER-TURN of 29-57% of the yaw, not scatter -- and those rows sit at the
# extreme of the yaw range (-20.1..-25.1 deg against -9.4..-23.8 at the stop).
# Where the fit is at the stop the leftover is unbiased, which is the shape a
# correction that landed has.
#
# So gate the yaw on the STRUCTURAL condition its formula needs, and fall back
# to the sidestep -- the pre-STOP_LOOK_YAW path, unchanged -- when it does not
# hold. SHIPS OFF: an A/B decides it, the way patch45's did
# (`--arms off,on --flag STOP_YAW_NEAR_FIT_ONLY`). It is NOT a special case for
# one stop, and equally the signature is only AT one stop: the stairs stop 39
# asks half the yaw (-104..-210 px) and its leftovers are both signs, so the
# eight firings the flag sends to the strafe there ride a rule whose evidence is
# at 129. What that costs is what the measurement is for.
STOP_YAW_NEAR_FIT_ONLY = False
# How far the look's fit may sit from the stop's own index and still be "the
# stop seen": ONE waypoint, which at the recording's 0.25 s is a quarter second
# of the user's walk. It is the census's own boundary -- the unbiased population
# above is exactly 128/129/130 -- and not a tuned number.
STOP_YAW_FIT_TOL = 1
# A stop whose frame and both looks fit NOTHING is most likely an NPC in the
'''),
 # (2) the decision: one more conjunct, and the offset it reads.
 ('''                    dx2 = getattr(f2, "dx", 0.0) or 0.0
                    px = dx2 + ddeg * PX_PER_DEG
                    if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:
''',
  '''                    dx2 = getattr(f2, "dx", 0.0) or 0.0
                    px = dx2 + ddeg * PX_PER_DEG
                    # ... and that formula assumes the frame that matched IS
                    # the stop's own (see STOP_YAW_NEAR_FIT_ONLY): a fit two or
                    # three waypoints on is a different pose, and the census
                    # says it then over-turns by 29-57% of itself, one way.
                    # `f2.k` is the look's own index; the default keeps a Fix
                    # without one inside the gate rather than outside it.
                    fit_off = int(getattr(f2, "k", target_k)) - target_k
                    near_fit = (not STOP_YAW_NEAR_FIT_ONLY
                                or abs(fit_off) <= STOP_YAW_FIT_TOL)
                    if STOP_LOOK_YAW and near_fit and abs(px) > LATERAL_TOL_PX:
'''),
 # (3) the fallback says WHY it is the fallback.
 ('''                    else:
                        # ONE ordinary correction, not a double one: batch 7 trial
''',
  '''                    else:
                        # THE NEAR-FIT GATE REFUSED THIS ONE. Name it in the
                        # journal: a stop the gate sent to the sidestep and a
                        # stop the flag was simply off for take the same path,
                        # and 10.1 is that a no-op and a working path must not
                        # have identical output. Recorded only where a yaw
                        # would otherwise have fired -- inside LATERAL_TOL_PX
                        # there is nothing to skip, and a marker there would
                        # claim the gate refused a correction never on offer.
                        if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:
                            looked["yaw_skipped"] = {
                                "fit_k": int(getattr(f2, "k", target_k)),
                                "off": fit_off}
                        # ONE ordinary correction, not a double one: batch 7 trial
'''),
 # (4) the log line's sibling.
 ('''                + (f"  STOP YAW {looked['yaw']['deg']:+.1f} deg on "
                   f"{looked['yaw']['px']} px, no strafe"
                   if looked is not None and "yaw" in looked else ""))
''',
  '''                + (f"  STOP YAW {looked['yaw']['deg']:+.1f} deg on "
                   f"{looked['yaw']['px']} px, no strafe"
                   if looked is not None and "yaw" in looked else "")
                # ... and a yaw the near-fit gate refused names the offset that
                # refused it, beside the sidestep that ran in its place.
                + ((f"  STOP YAW skipped (fit "
                    f"{looked['yaw_skipped']['off']:+d} from the stop), strafe "
                    + (f"{looked['strafe']['side']} for "
                       f"{looked['strafe']['seconds']:.2f}s on "
                       f"{looked['strafe']['px']} px"
                       if "strafe" in looked else "under the minimum, none"))
                   if looked is not None and "yaw_skipped" in looked else ""))
'''),
]

# --------------------------------------------------------------------- tests
NEW_TESTS = '''    @staticmethod
    def _gated(go, *a, **kw):
        """Run a walk with the yaw ON and its NEAR-FIT GATE on too."""
        old = (chain_walk.STOP_LOOK_YAW, chain_walk.STOP_YAW_NEAR_FIT_ONLY)
        chain_walk.STOP_LOOK_YAW = True
        chain_walk.STOP_YAW_NEAR_FIT_ONLY = True
        try:
            return go(*a, **kw)
        finally:
            (chain_walk.STOP_LOOK_YAW,
             chain_walk.STOP_YAW_NEAR_FIT_ONLY) = old

    def _look_at(self, k, after=None, fixes_after=(), table_at=7, dx=235.0):
        """The StopLookYaw rig with the -25 deg look fitting waypoint `k`.

        The stop is waypoint 2 and the look reads the default 235 px inside
        the same -25 frame, so px (-257.5) and the yaw it implies (-13.1 deg)
        are IDENTICAL across the gate tests below: the only thing that varies
        is where the sensor says that frame was, and any difference in the
        turn list is the gate and nothing else. `dx` is overridden by exactly
        one test, the one that needs px INSIDE LATERAL_TOL_PX.
        """
        return self._rig(self._wps(after=after),
                         [Fix(k=1), None, Fix(k=k, inliers=90, dx=dx),
                          None, Fix(k=3)] + list(fixes_after),
                         table_at=table_at)

    # The stop, both looks, back to the stop, THE YAW, then the next push's own
    # plan heading with the yaw on it -- and the same list with neither.
    YAW_TURNS = [90.0, 0.0, 335.0, 25.0, 0.0, 346.9, 356.9]
    STRAFE_TURNS = [90.0, 0.0, 335.0, 25.0, 0.0, 10.0]
    STRAFE_LAT = {"side": "left", "seconds": 0.3, "px": -258}

    def test_the_near_fit_gate_ships_OFF_and_its_tolerance_is_ONE_waypoint(self):
        # Literals (10.11): a test that reads the constant it guards passes
        # forever. The tolerance is the census's own boundary -- the unbiased
        # population at the 129 stop is exactly the fits at 128/129/130.
        self.assertIs(chain_walk.STOP_YAW_NEAR_FIT_ONLY, False)
        self.assertEqual(chain_walk.STOP_YAW_FIT_TOL, 1)

    def test_gated_a_look_fitting_ONE_PAST_the_stop_still_YAWS(self):
        # Inside the tolerance, so the gate must change NOTHING: this is the
        # census's 22-firing population, the one whose leftover is unbiased.
        rig = self._look_at(3)
        res = self._gated(rig.go)
        self.assertEqual(self.turns(rig), self.YAW_TURNS,
                         "the yaw fires exactly as it does today")
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["yaw"], {"deg": -13.1, "px": -258})
        self.assertNotIn("yaw_skipped", lat)
        self.assertEqual(rig.strafes(), [],
                         "a yaw REPLACES the sidestep; it never does both")
        self.assertTrue(res["arrived"])

    def test_gated_a_look_fitting_TWO_PAST_the_stop_STRAFES_AND_SAYS_SO(self):
        # The census's 6-firing population: dx +141..+230 after the yaw, all
        # one way. The fallback is the OLD path, and it must be the old path
        # exactly -- same seconds, same side, same px as the flag-off control
        # two tests up.
        rig = self._look_at(4)
        res = self._gated(rig.go)
        self.assertEqual(self.turns(rig), self.STRAFE_TURNS,
                         "no yaw turn, and the next push takes the plan's raw "
                         "10.0")
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)],
                         "LEFT at LATERAL_MAG for the capped LATERAL_CAP_SEC "
                         "-- the same sidestep the flag-off path takes")
        lat = res["fixes"][1]["lateral"]
        self.assertNotIn("yaw", lat)
        self.assertEqual(lat, {"deg": -25.0, "inliers": 90,
                               "yaw_skipped": {"fit_k": 4, "off": 2},
                               "strafe": self.STRAFE_LAT},
                         "the journal says WHY no yaw fired; without the "
                         "marker a gated stop and a flag-off stop are the "
                         "same row (10.1)")

    def test_gated_the_rule_is_SYMMETRIC_a_fit_two_BEHIND_also_strafes(self):
        # The formula fails on the OFFSET, not on the direction: a fit behind
        # the stop is as much "a different pose" as one ahead. Nothing on disk
        # measures the behind case (locate bounds its answer to [stop-1,
        # stop+3]), so this is the gate's stated shape held to, not a claim
        # about frequency.
        rig = self._look_at(0)
        res = self._gated(rig.go)
        self.assertEqual(self.turns(rig), self.STRAFE_TURNS)
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)])
        lat = res["fixes"][1]["lateral"]
        self.assertNotIn("yaw", lat)
        self.assertEqual(lat["yaw_skipped"], {"fit_k": 0, "off": -2})
        self.assertEqual(lat["strafe"], self.STRAFE_LAT)

    def test_with_the_gate_OFF_a_FAR_fit_YAWS_exactly_as_it_ships_today(self):
        # THE MATCHED CONTROL. Same rig as the +2 test, same look, same px --
        # the flag is the ONLY difference, so a mutant that applies the gate
        # whatever the flag says fails here and nowhere else.
        self.assertIs(chain_walk.STOP_YAW_NEAR_FIT_ONLY, False)
        self.assertIs(chain_walk.STOP_LOOK_YAW, True)
        rig = self._look_at(4)
        res = rig.go()
        self.assertEqual(self.turns(rig), self.YAW_TURNS)
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["yaw"], {"deg": -13.1, "px": -258})
        self.assertNotIn("yaw_skipped", lat)
        self.assertEqual(rig.strafes(), [])
        # ... and at +3, the far end of what locate() can return, both ways:
        # shipped it yaws, gated it does not.
        far = dict(after=[(10.0, -0.35), (10.0, -0.35), (10.0, -0.35)],
                   fixes_after=[Fix(k=4), Fix(k=5)], table_at=9)
        rig3 = self._look_at(5, **far)
        lat3 = rig3.go()["fixes"][1]["lateral"]
        self.assertEqual(lat3["yaw"], {"deg": -13.1, "px": -258})
        self.assertIn(346.9, self.turns(rig3), "ANTI-VACUITY: the yaw was taken")
        rig3g = self._look_at(5, **far)
        lat3g = self._gated(rig3g.go)["fixes"][1]["lateral"]
        self.assertNotIn("yaw", lat3g)
        self.assertEqual(lat3g["yaw_skipped"], {"fit_k": 5, "off": 3})
        self.assertNotIn(346.9, self.turns(rig3g))

    def test_inside_LATERAL_TOL_PX_the_gate_MARKS_NOTHING_however_far_the_fit(self):
        """A stop with nothing to correct records no skip -- either flag, any fit.

        The marker's own guard is `if STOP_LOOK_YAW and abs(px) >
        LATERAL_TOL_PX`, and its px half had no test: dropping it survived all
        191 tests (skeptic 2, 2026-09-08), because
        test_inside_LATERAL_TOL_PX_neither_a_yaw_nor_a_strafe pins the yaw and
        the strafe but never the new key. Without the px half, a stop whose
        look found the scene straight ahead is journalled as a yaw the near-fit
        gate refused -- a correction that was never on offer -- and at fit +2
        with the gate ON it says so on the one population the A/B reads. 500 px
        inside the -25 frame is 500 - 492.5 = 7.5 px from the walking heading,
        so nothing fires and nothing is recorded whatever the fit index is.
        """
        for gated in (False, True):
            for fit_k, off in ((2, 0), (4, +2)):
                with self.subTest(gated=gated, fit_off=off):
                    rig = self._look_at(fit_k, dx=500.0)
                    res = (self._gated if gated else self._on)(rig.go)
                    lat = res["fixes"][1]["lateral"]
                    self.assertNotIn("yaw", lat)
                    self.assertNotIn("strafe", lat)
                    self.assertNotIn("yaw_skipped", lat)
                    self.assertEqual(lat, {"deg": -25.0, "inliers": 90},
                                     "the look is recorded and nothing else")
                    self.assertEqual(rig.strafes(), [])
                    self.assertEqual(self.turns(rig), self.STRAFE_TURNS,
                                     "the next push takes the plan's raw "
                                     "heading, no yaw on it")

    def test_the_PAN_branch_takes_no_yaw_and_no_SKIP_with_ALL_flags_on(self):
        """The pan sidesteps as it always did, and records neither.

        The pan and the look-around are the two arms of one if/elif and only
        the elif consults these flags -- but that held for the wrong reason
        once already: a mutant that put the yaw block inside the PAN branch
        passed all 179 tests (skeptic 1, 2026-09-08) because no test had armed
        both flags at once. The pan's fit here sits TWO past the stop, so a
        gate copied into the pan would have something to refuse, and a
        `yaw_skipped` leaking in would show. The pan's dx is measured against
        the run frame's OWN heading and needs no un-yawing, which is exactly
        why there is no yaw here to gate.
        """
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, 0.0), (60.0, 0.0),
                                     (30.0, 0.0), (30.0, -0.35), (30.0, -0.35)],
                                    start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        ch = FakeChain(7, [Fix(k=1), None, None,
                           Fix(k=6, inliers=90, dx=80.0), Fix(k=5), Fix(k=6)],
                       default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=9)
        old = chain_walk.STOP_PAN_FROM_RUN
        chain_walk.STOP_PAN_FROM_RUN = True
        try:
            res = self._gated(rig.go)
        finally:
            chain_walk.STOP_PAN_FROM_RUN = old
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["pan_heading"], 60.0,
                         "ANTI-VACUITY: the PAN branch ran, not the "
                         "look-around")
        self.assertNotIn("yaw", lat)
        self.assertNotIn("yaw_skipped", lat)
        self.assertEqual(lat["strafe"], {"side": "right", "seconds": 0.111,
                                         "px": 80})
        self.assertEqual(self.turns(rig)[:5], [90.0, 30.0, 90.0, 60.0, 30.0],
                         "to the stop, the run's first and middle headings, "
                         "BACK TO THE STOP'S OWN HEADING -- no yaw on it")

'''

edits_t = [
 # (5) the class docstring: patch45 left "It ships False" behind, and the
 #     second flag belongs beside the first.
 ("""    STOP_LOOK_YAW turns by it instead, using the END TURN's own formula and
    cap, and carries the offset on every push until the next turn-only stop.
    It ships False; these tests drive it both ways and pin the shipped path
    as literals, because a mutant that ignores the flag must fail.
    \"\"\"
""",
  """    STOP_LOOK_YAW turns by it instead, using the END TURN's own formula and
    cap, and carries the offset on every push until the next turn-only stop.
    It ships True (patch45); these tests drive it both ways and pin the
    shipped path as literals, because a mutant that ignores the flag must
    fail.

    STOP_YAW_NEAR_FIT_ONLY (patch46) is the second flag here and it ships
    False. The un-yaw assumes the frame that matched IS the stop's own frame.
    Over the 39 firings in a CLOSED, NAMED population -- 120 journals, the
    manifest and a sha256 each in drafts/pending_after_ab/
    patch46_yaw_firings.json, recounted by patch46_yaw_census.py, because
    overnight/chain_journals/ is written by the live batch and a glob over it
    is not a population -- the leftover after the yaw is UNBIASED where the
    look's fit sits within one waypoint of the stop (22 firings, dx -232..+263
    both signs, 20 arrived) and ALL POSITIVE where it sits two or three ahead
    (6 firings, +141..+230, an over-turn of 29-57% of the yaw, 4 arrived). The
    flag sends that second population to the sidestep instead, and its tests
    drive it both ways for the same reason.
    \"\"\"
"""),
 # (6) the tests themselves, before the first of the yaw-clearing tests.
 ("    def test_a_REGRESSION_drops_the_stop_yaw(self):\n",
  NEW_TESTS + "    def test_a_REGRESSION_drops_the_stop_yaw(self):\n"),
]

# ------------------------------------------------- assert EVERYTHING, then write
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a[:60], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:60], t.count(a))
# the fallback must stay the flag-off path: the strafe block is not touched
assert c.count("                            side = RIGHT if px > 0 else LEFT\n") == 1
assert "STOP_YAW_NEAR_FIT_ONLY" not in c and "STOP_YAW_FIT_TOL" not in c
# the test the new coverage test names must be there to be extended, not replaced
assert t.count("def test_inside_LATERAL_TOL_PX_neither_a_yaw_nor_a_strafe") == 1

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(c)
ast.parse(t)
assert c.count("STOP_YAW_NEAR_FIT_ONLY = False") == 1
assert c.count("STOP_YAW_FIT_TOL = 1") == 1
assert c.count("near_fit") == 2, c.count("near_fit")
assert c.count("fit_off") == 3, c.count("fit_off")
assert c.count('looked["yaw_skipped"]') == 1
# the marker's own guard, and the test that now pins its px half
assert c.count("if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:") == 1
assert t.count("def test_inside_LATERAL_TOL_PX_the_gate_MARKS_NOTHING_"
               "however_far_the_fit") == 1
assert t.count('self.assertNotIn("yaw_skipped", lat)') == 4

open(C, "w").write(c)
open(T, "w").write(t)
print("patch46 applied to", ROOT)
