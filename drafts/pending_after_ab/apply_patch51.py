"""patch51: STOP_YAW_SKIP_LAST_STOP -- no stop yaw at the plan's LAST turn-only stop.

WHAT THE STOP YAW IS FOR. A looked stop's offset is a heading error, and the
yaw (STOP_LOOK_YAW, patch44/45) turns by it and lets it ride every push until
the NEXT turn-only stop clears it -- the next stop is approached square, so
the yaw is a correction for the pushes in between. The plan's last stop has
no next stop. A yaw taken there rides the whole final approach, and the end
turn (END_TURN_PX) then aims the tail at the scene ON TOP of it.

THE CENSUS (agent_progress/closed-loop/review/census_after_129_notes.md,
"Added 12:15", 2026-09-08; the 196 stop over 266 walks since batch 16):

    verified head-on, or looked and STRAFED     225 arrived / 1 ended at the
                                                chain's end without the prompt
                                                / 1 failed
    looked and YAWED (6 firings)                4 arrived / 2 ended at 204
                                                without the prompt
                                                (b24 t12 +29.2 deg, b26 t1
                                                +10.6 deg)

Two of six against one of 227. Mechanism: the last three pushes go straight
at the dealer, the prompt zone is 0.05 u wide (OPEN-22), and a rotated final
approach walks past it. n = 6 is small, and the rule is not sold on the
count: the yaw at the last stop has no upside the end turn does not already
cover, and the strafe there is the measured 225/227 behaviour.

WHAT IT DOES. `STOP_YAW_SKIP_LAST_STOP` (ships True) refuses the yaw when the
stop being serviced is `_last_stop_index(plan)` -- the same index the end turn
already keys on. The EXISTING strafe path runs instead, byte for byte, and the
`yaw_skipped` marker carries `"reason": "last stop"` with a matching log line,
so a stop this rule sent to the strafe is distinguishable from a stop the
near-fit gate sent there and from a stop the flag was off for (10.1).

WHAT IT IS NOT. Not a change to any mid-route stop, the end turn, the pan
branch, the head-on path, the rescue, or any constant; no guard is removed.
`overnight/chain_trials.py --arms off,on --flag STOP_YAW_SKIP_LAST_STOP` is
the measurement if one is wanted; the census above is the reason it ships on.

Usage: python apply_patch51.py [ROOT]      (asserts every anchor, THEN writes)
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read()
t = open(T).read()

edits_c = [
 # (1) the constant, beside the near-fit gate's tolerance.
 ("""STOP_YAW_FIT_TOL = 1
""",
  """STOP_YAW_FIT_TOL = 1
# NO STOP YAW AT THE PLAN'S LAST TURN-ONLY STOP (patch51). The yaw is cleared
# at the NEXT turn-only stop; the last stop has none, so a yaw taken there
# rides the whole final approach and the end turn then aims the tail ON TOP
# of it. Census of the 196 stop over 266 walks since batch 16
# (agent_progress/closed-loop/review/census_after_129_notes.md, 2026-09-08):
# head-on or strafed, 225 arrived / 1 ended without the prompt / 1 failed;
# looked and YAWED (6), 4 arrived / 2 ended at 204 without the prompt (b24
# t12 +29.2 deg, b26 t1 +10.6 deg). The last three pushes go straight at the
# dealer and the prompt zone is 0.05 u wide (OPEN-22): a rotated final
# approach walks past it. The strafe there is the measured 225/227 path.
STOP_YAW_SKIP_LAST_STOP = True
"""),
 # (2) the decision: one more term, keyed on the index the end turn uses.
 ("""                    fit_off = int(getattr(f2, "k", target_k)) - target_k
                    near_fit = (not STOP_YAW_NEAR_FIT_ONLY
                                or abs(fit_off) <= STOP_YAW_FIT_TOL)
                    if STOP_LOOK_YAW and near_fit and abs(px) > LATERAL_TOL_PX:
""",
  """                    fit_off = int(getattr(f2, "k", target_k)) - target_k
                    near_fit = (not STOP_YAW_NEAR_FIT_ONLY
                                or abs(fit_off) <= STOP_YAW_FIT_TOL)
                    # ... and never at the plan's LAST stop: nothing clears
                    # the yaw after it, so it would ride the whole final
                    # approach under the end turn (STOP_YAW_SKIP_LAST_STOP).
                    last_stop = (STOP_YAW_SKIP_LAST_STOP
                                 and last_stop_j is not None
                                 and pi == last_stop_j)
                    if (STOP_LOOK_YAW and near_fit and not last_stop
                            and abs(px) > LATERAL_TOL_PX):
"""),
 # (3) the marker says WHICH rule refused the yaw.
 ("""                        if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:
                            looked["yaw_skipped"] = {
                                "fit_k": int(getattr(f2, "k", target_k)),
                                "off": fit_off}
""",
  """                        if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:
                            looked["yaw_skipped"] = {
                                "fit_k": int(getattr(f2, "k", target_k)),
                                "off": fit_off}
                            if last_stop:
                                looked["yaw_skipped"]["reason"] = "last stop"
"""),
 # (4) ... and so does the log line.
 ("""                + ((f"  STOP YAW skipped (fit "
                    f"{looked['yaw_skipped']['off']:+d} from the stop), strafe "
                    + (f"{looked['strafe']['side']} for "
""",
  """                + (("  STOP YAW skipped ("
                    + (looked["yaw_skipped"]["reason"]
                       if "reason" in looked["yaw_skipped"] else
                       f"fit {looked['yaw_skipped']['off']:+d} from the stop")
                    + "), strafe "
                    + (f"{looked['strafe']['side']} for "
"""),
]

NEW_TESTS = '''    # -- patch51: no yaw at the plan's LAST turn-only stop --------------------

    @staticmethod
    def _skip_last(go, *a, **kw):
        """Run a walk with the yaw ON and its LAST-STOP rule on: the shipped pair."""
        old = (chain_walk.STOP_LOOK_YAW, chain_walk.STOP_YAW_SKIP_LAST_STOP)
        chain_walk.STOP_LOOK_YAW = True
        chain_walk.STOP_YAW_SKIP_LAST_STOP = True
        try:
            return go(*a, **kw)
        finally:
            (chain_walk.STOP_LOOK_YAW,
             chain_walk.STOP_YAW_SKIP_LAST_STOP) = old

    def test_the_last_stop_rule_ships_ON(self):
        # Literal (10.11), read as IMPORTED: setUp turns the flag off for the
        # single-stop rig, so the live attribute is False inside every test
        # here. The 196 census: yawed 2 of 6 ended without the prompt
        # against 1 of 227 head-on or strafed.
        self.assertIs(self.shipped_skip_last, True)
        self.assertIs(chain_walk.STOP_YAW_SKIP_LAST_STOP, False,
                      "ANTI-VACUITY: setUp did switch it off for the rig")

    def test_at_the_plans_LAST_stop_the_look_STRAFES_and_says_why(self):
        # The default rig's only stop IS the plan's last. The fit is AT the
        # stop (off 0) and px is the yaw tests' own -257.5 -- everything that
        # fires the yaw at a mid stop -- and the strafe runs instead, byte for
        # byte the flag-off path, with the reason in the journal.
        rig = self._look_at(2)
        res = self._skip_last(rig.go)
        self.assertEqual(self.turns(rig), self.STRAFE_TURNS,
                         "no yaw turn; the next push takes the plan's raw 10.0")
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)])
        lat = res["fixes"][1]["lateral"]
        self.assertNotIn("yaw", lat)
        self.assertEqual(lat, {"deg": -25.0, "inliers": 90,
                               "yaw_skipped": {"fit_k": 2, "off": 0,
                                               "reason": "last stop"},
                               "strafe": self.STRAFE_LAT},
                         "the journal names the rule that refused the yaw")
        self.assertTrue(res["arrived"])

    def test_a_MID_stop_still_YAWS_with_the_last_stop_rule_on(self):
        # Two stops. The yaw fires at the first and is cleared at the second,
        # which is the plan's last and is verified head-on here -- the same
        # rig and the same turn list as
        # test_the_yaw_is_cleared_at_the_next_turn_only_stop, with the
        # shipped pair on. A mutant that refuses every stop fails here.
        rig = self._rig(self._wps(after=[(10.0, -0.35), (20.0, 0.0),
                                         (30.0, -0.35)]),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                         None, Fix(k=3), Fix(k=4, inliers=200)], table_at=8)
        res = self._skip_last(rig.go)
        self.assertEqual(self.turns(rig),
                         [90.0, 0.0, 335.0, 25.0, 0.0, 346.9, 356.9,
                          20.0, 30.0])
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["yaw"], {"deg": -13.1, "px": -258})
        self.assertNotIn("yaw_skipped", lat)
        self.assertEqual(rig.strafes(), [])
        self.assertTrue(res["arrived"])

    def test_with_the_rule_OFF_the_last_stop_YAWS_as_it_did_before(self):
        # The control (the A/B's off arm): the pre-patch51 path, pinned.
        prev = chain_walk.STOP_YAW_SKIP_LAST_STOP
        chain_walk.STOP_YAW_SKIP_LAST_STOP = False
        self.addCleanup(setattr, chain_walk, "STOP_YAW_SKIP_LAST_STOP", prev)
        rig = self._look_at(2)
        res = self._on(rig.go)
        self.assertEqual(self.turns(rig), self.YAW_TURNS)
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["yaw"], {"deg": -13.1, "px": -258})
        self.assertNotIn("yaw_skipped", lat)
        self.assertEqual(rig.strafes(), [])

'''

edits_t = [
 # (5) the class docstring gains the third flag.
 ("""    flag sends that second population to the sidestep instead, and its tests
    drive it both ways for the same reason.
    \"\"\"
""",
  """    flag sends that second population to the sidestep instead, and its tests
    drive it both ways for the same reason.

    STOP_YAW_SKIP_LAST_STOP (patch51) is the third flag and it ships True: no
    yaw at the plan's LAST turn-only stop, because nothing clears it after
    that and it rides the whole final approach under the end turn (the 196
    census: yawed 2 of 6 ended without the prompt, head-on or strafed 1 of
    227). The single-stop rig every test above drives has its only stop AS
    the plan's last, so setUp turns that flag OFF for them: they are the
    yaw's own mechanics and the A/B's off arm, and the patch51 tests below
    turn it on explicitly.
    \"\"\"

    def setUp(self):
        prev = chain_walk.STOP_YAW_SKIP_LAST_STOP
        self.shipped_skip_last = prev      # the value as imported, for the pin
        chain_walk.STOP_YAW_SKIP_LAST_STOP = False
        self.addCleanup(setattr, chain_walk, "STOP_YAW_SKIP_LAST_STOP", prev)
"""),
 # (6) the tests, before the first of the yaw-clearing tests (patch46's seam).
 ("    def test_a_REGRESSION_drops_the_stop_yaw(self):\n",
  NEW_TESTS + "    def test_a_REGRESSION_drops_the_stop_yaw(self):\n"),
]

# ------------------------------------------------- assert EVERYTHING, then write
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a[:60], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:60], t.count(a))
assert "STOP_YAW_SKIP_LAST_STOP" not in c and "STOP_YAW_SKIP_LAST_STOP" not in t
# the index the rule keys on is the end turn's own, bound once per walk
assert c.count("    last_stop_j = _last_stop_index(plan)") == 1
assert c.count("last_stop_j") == 3, c.count("last_stop_j")
# the strafe fallback is not touched
assert c.count("                            side = RIGHT if px > 0 else LEFT\n") == 1
# the class has no setUp of its own yet
cls = t.index("class StopLookYaw(unittest.TestCase):")
nxt = t.index("\nclass ", cls + 1)
assert "def setUp(" not in t[cls:nxt]
assert t.count("    def _look_at(self, k, after=None, fixes_after=(), "
               "table_at=7, dx=235.0):") == 1

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(c)
ast.parse(t)
assert c.count("STOP_YAW_SKIP_LAST_STOP = True") == 1
assert c.count("STOP_YAW_SKIP_LAST_STOP") == 3, c.count("STOP_YAW_SKIP_LAST_STOP")  # def, comment, decision
assert c.count("last_stop_j") == 5, c.count("last_stop_j")
assert c.count("not last_stop\n") == 1
assert c.count('looked["yaw_skipped"]["reason"] = "last stop"') == 1
assert c.count('"reason" in looked["yaw_skipped"]') == 1
assert t.count("def setUp(self):") >= 1
assert t.count("def test_at_the_plans_LAST_stop_the_look_STRAFES_and_says_why") == 1

open(C, "w").write(c)
open(T, "w").write(t)
print("patch51 applied to", ROOT)
