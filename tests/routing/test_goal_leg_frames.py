"""The goal leg: which executor walks it, and which frame describes it.

Three claims, each pinned behaviourally (calls and identities, never source
text), because each was wrong on 2026-09-07 in a way no log line showed:

  1. GOAL_LEG_AS_RECORDED chooses the executor for the goal leg: off, the
     straight-line approach_goal(); on, walk_link() like every other leg. Both
     are followed by reach_table()'s sweep.
  2. follow() publishes the goal's leg-end frame BEFORE reach_table turns the
     camera, and confirm() judges the frame taken AFTER it. All 37 OPEN-14
     table-leg frames were post-sweep and described the sweep, not the leg.
  3. follow_verified's success frame is the frame follow() published at the
     leg's end, not `before` -- both OPEN-14 ok_dealer_table frames were the
     previous node's arrival.

Offline. Every collaborator that moves the character or reads the screen is a
stub; the only files written are jpeg names under a temp directory.
"""
import glob
import os
import shutil
import sys
import tempfile
import types
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

SAVED = []          # (path, tag) for every Frame.save


class Frame:
    def __init__(self, tag):
        self.tag = tag

    def convert(self, _m):
        return self

    def save(self, path, **k):
        SAVED.append((path, self.tag))


class Map:
    landmarks = {"bar_jukebox": (0, 0), "dealer_table": (1, 0)}
    confusable = []

    def route_reason(self, a, b): return "ok"
    def route(self, a, b): return [a, b]
    def route_cost(self, p): return 1.0
    def steps_for(self, a, b): return [{"bearing": 75.5, "dur": 0.5, "speed": 0.2}] * 8


FLAGS = ("GOAL_LEG_AS_RECORDED", "ALIGN_AT_NODES", "RECOVER_MISSED")
FUNCS = ("stream_is_live", "walk_link", "approach_goal", "reach_table",
         "confirm", "confirmable", "recover_to_node", "go_to_node_verified")


class _Stubbed(unittest.TestCase):
    """Save and restore every module attribute a case may replace."""

    def setUp(self):
        SAVED.clear()
        self._orig = {n: getattr(gw, n) for n in FLAGS + FUNCS}
        self._sleep = gw.time.sleep
        gw.time.sleep = lambda *a: None
        gw._LAST_LEG_END.clear()
        self.tmp = tempfile.mkdtemp(prefix="goalframes_")
        self.assertEqual(gw.GOAL, "dealer_table")

    def tearDown(self):
        for n, v in self._orig.items():
            setattr(gw, n, v)
        gw.time.sleep = self._sleep
        gw._LAST_LEG_END.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)


class GoalLegExecutor(_Stubbed):

    def _run_follow(self, as_recorded, frames):
        calls = []
        gw.GOAL_LEG_AS_RECORDED = as_recorded
        gw.ALIGN_AT_NODES = False
        gw.RECOVER_MISSED = False
        gw.stream_is_live = lambda *a, **k: True
        gw.confirmable = lambda m, node: True

        def walk_link(m, a, b, capture=None, read_heading=None, log=print, fraction=1.0):
            calls.append(("walk_link", b, fraction))
            return {"a": a, "b": b, "steps": 8, "travelled": 1.0, "hazards": []}

        def approach_goal(steps, capture=None, read_heading=None, log=print):
            calls.append(("approach_goal", len(steps)))
            return False

        def reach_table(capture=None, read_heading=None, log=print):
            calls.append(("reach_table",))
            return False

        judged = []

        def confirm(m, node, img, log=print):
            judged.append((node, getattr(img, "tag", None)))
            return False, "stub"          # False stops follow() cleanly

        gw.walk_link, gw.approach_goal = walk_link, approach_goal
        gw.reach_table, gw.confirm = reach_table, confirm
        it = iter(frames)
        gw.follow(Map(), "bar_jukebox", "dealer_table", capture=lambda: next(it),
                  read_heading=lambda: 75.5, log=lambda *a: None, shots=self.tmp)
        return calls, judged

    def test_flag_off_uses_approach_goal_then_sweeps(self):
        calls, _ = self._run_follow(False, [Frame("PRE"), Frame("POST")])
        names = [c[0] for c in calls]
        self.assertEqual(names, ["approach_goal", "reach_table"], calls)

    def test_flag_on_walks_the_recorded_leg_then_sweeps(self):
        calls, _ = self._run_follow(True, [Frame("PRE"), Frame("POST")])
        names = [c[0] for c in calls]
        self.assertEqual(names, ["walk_link", "reach_table"], calls)
        self.assertEqual(calls[0][1:], ("dealer_table", 1.0),
                         "the goal leg is walked whole, never a SHORT_WALK fraction")

    def test_leg_end_frame_precedes_the_sweep_and_confirm_judges_the_post_sweep_one(self):
        # Two captures: the first is taken when the leg ends, the second after
        # reach_table has turned the camera. The published frame must be the
        # first; the frame confirm() judges must be the second.
        for as_recorded in (False, True):
            SAVED.clear()
            gw._LAST_LEG_END.clear()
            _, judged = self._run_follow(as_recorded, [Frame("PRE"), Frame("POST")])
            published = getattr(gw._LAST_LEG_END.get("dealer_table"), "tag", None)
            self.assertEqual(published, "PRE",
                             f"published the post-sweep frame (flag={as_recorded})")
            self.assertEqual(judged, [("dealer_table", "POST")],
                             f"confirm() must judge the post-sweep frame (flag={as_recorded})")
            stems = sorted((os.path.basename(p).rsplit("_", 1)[0], t) for p, t in SAVED)
            self.assertEqual(stems, [("at_dealer_table", "PRE"),
                                     ("at_dealer_table_postsweep", "POST")], SAVED)

    def test_shipped_default_is_off(self):
        # Pinned as a literal (CLAUDE.md 10.11): it flips only on a measured A/B.
        self.assertIs(self._orig["GOAL_LEG_AS_RECORDED"], False)


class SuccessFrame(_Stubbed):

    def test_success_frame_is_the_leg_end_not_before(self):
        gw.stream_is_live = lambda *a, **k: True

        def gtnv(m, node, **kw):
            gw._LAST_LEG_END[node] = Frame("LEG-END")
            return True
        gw.go_to_node_verified = gtnv
        reset = types.ModuleType("reset_env")
        reset.reset_environment = lambda **k: None
        saved = sys.modules.get("reset_env")
        sys.modules["reset_env"] = reset
        try:
            ok, reached = gw.follow_verified(
                Map(), ["bar_jukebox"], capture=lambda: Frame("BEFORE"),
                read_heading=lambda: 0.0, log=lambda *a: None,
                attempts=1, shots=self.tmp)
        finally:
            if saved is None:
                sys.modules.pop("reset_env", None)
            else:
                sys.modules["reset_env"] = saved
        self.assertTrue(ok and reached == ["bar_jukebox"], (ok, reached))
        ok = [(p, t) for p, t in SAVED if "/success/ok_bar_jukebox_" in p]
        self.assertEqual(len(ok), 1, SAVED)
        self.assertEqual(ok[0][1], "LEG-END",
                         "the success frame is the previous node's arrival again")
        self.assertRegex(os.path.basename(ok[0][0]), r"^ok_bar_jukebox_\d{13}\.jpg$",
                         "stamped in milliseconds, like every other frame")


if __name__ == "__main__":
    unittest.main(verbosity=2)
