"""(c) LEG_TRIM_UNITS_BY_LEG: trim the END of a recorded leg by N walk-units. APPLY ONLY WHEN NO LIVE RUN IMPORTS graph_walk."""
p = "graph_walk.py"; s = open(p).read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:60]); s = s.replace(old, new)
rep("LEG_SPEED_BY_LEG = {}\n", '''LEG_SPEED_BY_LEG = {}
# TRIM THE END OF A RECORDED LEG by this many walk-units (dur x speed), taken
# off its last step(s). Every leg ends by walking into something (§11): the
# human decelerated into the destination, the executor replays the tail as a
# fresh push. 2026-09-07 the jukebox leg ended WEDGED in 69 of 106 executions,
# pressed into the jukebox cabinet itself (dark frame, no compass strip). Its
# last step is 0.14s at 0.319 = 0.045u. Ships EMPTY; flips only on an A/B
# (overnight/ab_jukebox_trim.py). Keyed like LEG_SPEED_BY_LEG.
LEG_TRIM_UNITS_BY_LEG = {}


def _trimmed(steps, units):
    """Remove `units` of dur x speed from the END of `steps`; never below zero."""
    if not units or units <= 0:
        return steps
    out = [dict(st) for st in steps]
    left = float(units)
    while out and left > 1e-9:
        st = out[-1]
        sp = st.get("speed", 0.2)
        have = st["dur"] * sp
        if have <= left + 1e-9:
            out.pop(); left -= have
        else:
            st["dur"] = round((have - left) / sp, 4); left = 0.0
    return out
''')
rep("    steps = _scaled(steps, leg_scale(a, b))\n", "    steps = _scaled(steps, leg_scale(a, b))\n    steps = _trimmed(steps, LEG_TRIM_UNITS_BY_LEG.get((a, b), 0.0))\n")
open(p, "w").write(s); print("patched graph_walk.py (leg trim)")

open("tests/routing/test_leg_trim.py", "w").write('''"""LEG_TRIM_UNITS_BY_LEG takes walk-units off the END of a recorded leg, in walk_link.

Pinned against the recorded jukebox leg (five steps north, last 0.14s at 0.319 =
0.045u): a 0.045u trim removes exactly the last step, 0.10u removes it and
0.17s of the fourth, 0 changes nothing, and walk_link applies the flag for the
keyed leg only. Offline; slow_traverse is stubbed.
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import graph_walk as gw
import worldmap as wm

LEG = ("bar_pool_room", "bar_jukebox")


def units(steps):
    return sum(s["dur"] * s.get("speed", 0.2) for s in steps)


class Trim(unittest.TestCase):

    def setUp(self):
        self.steps = wm.WorldMap.load().steps_for(*LEG)
        self.assertEqual(len(self.steps), 5)
        self.assertAlmostEqual(self.steps[-1]["dur"] * self.steps[-1]["speed"], 0.0447, delta=0.001)

    def test_zero_is_identity(self):
        self.assertEqual(gw._trimmed(self.steps, 0.0), self.steps)
        self.assertEqual(gw._trimmed(self.steps, None), self.steps)

    def test_last_step_exactly(self):
        out = gw._trimmed(self.steps, 0.0447)
        self.assertEqual(len(out), 4)
        self.assertAlmostEqual(units(self.steps) - units(out), 0.0447, delta=0.002)

    def test_into_the_fourth_step(self):
        out = gw._trimmed(self.steps, 0.10)
        self.assertEqual(len(out), 4)
        self.assertAlmostEqual(units(self.steps) - units(out), 0.10, delta=0.002)
        self.assertLess(out[-1]["dur"], self.steps[3]["dur"])
        self.assertEqual(out[:3], self.steps[:3], "earlier steps untouched")

    def test_never_negative(self):
        self.assertEqual(gw._trimmed(self.steps, 99.0), [])

    def test_walk_link_applies_the_keyed_trim_only(self):
        seen = {}
        import slow_traverse as st
        saved = (st.walk_leg, st.turn_to, gw.LEG_TRIM_UNITS_BY_LEG, gw.stream_is_live)
        try:
            st.turn_to = lambda bearing, read_heading, capture, **kw: (bearing, [])
            def walk_leg(lx, ly, dur, *a, **kw):
                seen.setdefault("durs", []).append(round(dur, 4)); return 0.0, 10.0, []
            st.walk_leg = walk_leg
            gw.stream_is_live = lambda *a, **k: True
            gw.LEG_TRIM_UNITS_BY_LEG = {LEG: 0.0447}
            m = wm.WorldMap.load()
            try:
                gw.walk_link(m, *LEG, capture=lambda: None, read_heading=lambda: 0.0, log=lambda *a: None)
            except Exception as e:                 # the stubbed stack may not run to the end
                if not seen.get("durs"):
                    raise
            self.assertEqual(len(seen["durs"]), 4, seen)
            seen.clear()
            gw.walk_link(m, "portrait_room", "bar_pool_room", capture=lambda: None,
                         read_heading=lambda: 0.0, log=lambda *a: None)
            self.assertEqual(len(seen["durs"]), len(m.steps_for("portrait_room", "bar_pool_room")),
                             "an unkeyed leg is not trimmed")
        finally:
            st.walk_leg, st.turn_to, gw.LEG_TRIM_UNITS_BY_LEG, gw.stream_is_live = saved

    def test_shipped_flag_is_empty(self):
        self.assertEqual(gw.LEG_TRIM_UNITS_BY_LEG, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
''')
print("wrote tests/routing/test_leg_trim.py")
