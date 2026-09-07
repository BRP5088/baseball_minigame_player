"""overnight/ab_fast.py: the pure parts of the fast A/B harness.

reverse_steps walks a leg backwards (reversed order, bearings turned 180, same
durations); classify() scores an arrival slower than LEG_TIME_CAP as timed_out
and never as arrived; each arm sets only its own flags; the cap is a literal.
"""
import os
import sys
import types
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import ab_fast


class Pure(unittest.TestCase):

    def test_reverse_steps(self):
        steps = [{"bearing": 90.4, "dur": 0.79, "speed": 0.2}, {"bearing": 75.5, "dur": 0.40, "speed": 0.21}]
        rev = ab_fast.reverse_steps(steps)
        self.assertEqual([r["bearing"] for r in rev], [255.5, 270.4])
        self.assertEqual([r["dur"] for r in rev], [0.40, 0.79])
        self.assertEqual([r["speed"] for r in rev], [0.21, 0.2])
        self.assertEqual(steps[0]["bearing"], 90.4, "the input is not mutated")

    def test_reverse_of_the_recorded_goal_leg_points_back(self):
        import worldmap as wm
        import graph_walk as gw
        steps = wm.WorldMap.load().steps_for("bar_jukebox", "dealer_table")
        back = gw._leg_net_bearing(ab_fast.reverse_steps(steps))
        self.assertAlmostEqual((back - 86.1) % 360, 180.0, delta=0.5)

    def test_classify(self):
        self.assertEqual(ab_fast.classify(False, 10, 100), "missed")
        self.assertEqual(ab_fast.classify(True, 34, 100), "arrived")
        self.assertEqual(ab_fast.classify(True, 60, 400), "arrived")
        self.assertEqual(ab_fast.classify(True, 61, 100), "timed_out", "a slow leg is not an arrival")
        self.assertEqual(ab_fast.classify(True, 30, 401), "timed_out", "a slow TRIAL is a failure whatever the leg did")
        self.assertEqual(ab_fast.classify(False, 30, 401), "timed_out")
        self.assertEqual(ab_fast.classify(False, 999, 100), "missed", "a slow miss under the trial cap is a miss")

    def test_caps_are_literals(self):
        self.assertEqual(ab_fast.LEG_TIME_CAP, 60)
        self.assertEqual(ab_fast.TRIAL_TIME_CAP, 400)
        self.assertEqual(ab_fast.TIMEOUT, 420, "the external kill sits just above the trial cap")

    def test_each_arm_sets_only_its_own_flags(self):
        for exp in ab_fast.EXPERIMENTS.values():
            for name, setter in exp["arms"].items():
                gw = types.SimpleNamespace(GOAL_LEG_AS_RECORDED=False, GOAL_LEG_EXTRA_UNITS=0.0, LEG_TRIM_UNITS_BY_LEG={})
                setter(gw)
                touched = {k for k, v in vars(gw).items() if v not in (False, 0.0, {})}
                if name == "recorded" and exp["target"] == "dealer_table":
                    self.assertEqual(touched, {"GOAL_LEG_AS_RECORDED"})
                elif name == "extended":
                    self.assertEqual(touched, {"GOAL_LEG_AS_RECORDED", "GOAL_LEG_EXTRA_UNITS"})
                elif name == "trimmed":
                    self.assertEqual(touched, {"LEG_TRIM_UNITS_BY_LEG"})
                    self.assertEqual(list(gw.LEG_TRIM_UNITS_BY_LEG), [("bar_pool_room", "bar_jukebox")])
                else:
                    self.assertEqual(touched, set(), f"{name} must touch nothing")

    def test_fisher_reproduces_known_tables(self):
        self.assertAlmostEqual(ab_fast.fisher_two_sided(9, 0, 5, 5), 0.0325, delta=0.002)
        self.assertAlmostEqual(ab_fast.fisher_two_sided(10, 0, 2, 8), 0.000714, delta=0.0001)


if __name__ == "__main__":
    unittest.main(verbosity=2)
