"""locate() may never confirm the GOAL by appearance.

CLAUDE.md §7: dealer_table is a POSE, not a place -- arrival is the PROMPT,
checked by table_prompt.at_table(), never places.identify(). confirm()
enforced that; locate() did not, and OPEN-14 trial 6 (2026-09-07) was scored
as an arrival on "verified at dealer_table (dealer_table 194.000/1.530)" while
at_table() read False 0.8s later. The prompt gates a $50 Square press, so a
locate() that names the table without it both records an arrival that did
not happen and can commit money at nothing.

Offline: places and table_prompt are replaced by stubs; nothing touches the
console, the map on disk or any input path.
"""
import os
import sys
import types
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import graph_walk as gw

FRAME = object()          # locate() only forwards it; the stubs ignore it


class _Map:
    landmarks = {"bar_jukebox": (0, 0), "dealer_table": (1, 0)}
    confusable = []


def _stub(at_table, answer):
    """Install fake `table_prompt` and `places`; return the identify() call log."""
    calls = []
    tp = types.ModuleType("table_prompt")
    tp.at_table = lambda img: at_table
    pl = types.ModuleType("places")

    def identify(img, **kw):
        calls.append(img)
        return answer
    pl.identify = identify
    sys.modules["table_prompt"] = tp
    sys.modules["places"] = pl
    return calls


class LocateGoalIsAPose(unittest.TestCase):

    def setUp(self):
        self._saved = {k: sys.modules.get(k) for k in ("table_prompt", "places")}
        self.assertEqual(gw.GOAL, "dealer_table")

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_prompt_confirms_the_goal(self):
        calls = _stub(at_table=True, answer=(None, 0.0, 0.0))
        node, detail = gw.locate(_Map(), img=FRAME, log=lambda *a: None)
        self.assertEqual(node, gw.GOAL)
        self.assertIn("at_table", detail)
        self.assertEqual(calls, [], "the prompt answered; identify() must not be consulted")

    def test_appearance_never_confirms_the_goal(self):
        # The OPEN-14 trial-6 answer, verbatim: identify() names the table at
        # 194 matches / ratio 1.53 with no prompt on screen.
        calls = _stub(at_table=False, answer=("dealer_table", 194.0, 1.53))
        node, detail = gw.locate(_Map(), img=FRAME, log=lambda *a: None)
        self.assertEqual(len(calls), 1, "guard must sit AFTER identify() ran, not before")
        self.assertIsNone(node, f"locate() confirmed the GOAL by appearance: {detail!r}")
        self.assertIn("pose", detail)
        self.assertIn("194.000", detail, "detail must carry the evidence it refused")

    def test_other_rooms_still_answer(self):
        # Control: the guard is about the GOAL only. A room identify() names
        # with the same shape of evidence is still a routable answer.
        _stub(at_table=False, answer=("bar_jukebox", 295.0, 2.11))
        node, _ = gw.locate(_Map(), img=FRAME, log=lambda *a: None)
        self.assertEqual(node, "bar_jukebox")

    def test_abstention_still_abstains(self):
        _stub(at_table=False, answer=(None, 87.0, 1.16))
        node, detail = gw.locate(_Map(), img=FRAME, log=lambda *a: None)
        self.assertIsNone(node)
        self.assertIn("unrecognised", detail)


class RealFrame(unittest.TestCase):
    """The same guard against the REAL detectors on trial 6's own frame.

    overnight/streak_table_failframes/at_dealer_table_1788771394587.jpg is the
    post-sweep leg-end frame of OPEN-14 trial 6: places.identify() names the
    table (182/1.42 on the saved JPEG; 194/1.53 live) and table_prompt sees no
    prompt (ink 0.010 against INK_MIN 0.024). Both pins below are anti-vacuity
    checks: if a reference change ever stops identify() naming the table here,
    the guard is no longer being exercised and this test must say so.
    """
    FIX = os.path.join(_ROOT, "test_fixtures", "locate",
                       "identify_names_table_no_prompt.jpg")

    def test_trial_6_frame_is_not_an_arrival(self):
        for k in ("places", "table_prompt"):
            sys.modules.pop(k, None)               # the real modules, not a stub
        import places
        import table_prompt
        from PIL import Image
        self.assertTrue(os.path.isfile(self.FIX), f"fixture missing: {self.FIX}")
        img = Image.open(self.FIX)
        self.assertFalse(table_prompt.at_table(img), "the fixture must show NO prompt")
        room, score, margin = places.identify(img)
        self.assertEqual(room, gw.GOAL,
                         f"fixture no longer exercises the guard: identify() -> {room} {score}/{margin}")
        node, detail = gw.locate(_Map(), img=img, log=lambda *a: None)
        self.assertIsNone(node, f"locate() confirmed the table by appearance: {detail!r}")
        self.assertIn("pose", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
