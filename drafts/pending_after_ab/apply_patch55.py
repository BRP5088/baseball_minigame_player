"""patch55: BAR_STOP_EARLY_TURN -- one FEWER push before the bar's sharp turn.

THE USER SAW IT FIRST, watching the stream: "they walked too close to the bar
when they should have turned earlier." This is the mirror of the door-step
observation that already shipped and won (patch47/50, 10/10 against 9/10):
there the route needed one MORE push before the stairs turn; here it needs one
FEWER before the bar's.

THE MEASUREMENT THAT CORROBORATES IT. A fit's `scale` is how big the scene
looks against the recorded waypoint, so above 1.0 means the character is CLOSER
to it than the drive was. Over 2,560 credible fits (inliers >= FIX_MIN_INLIERS)
from the last 60 journals:

    waypoints      n     median scale
      0-14        72        1.00      the spawn, at the recorded distance
     30-89       917        1.24-1.28
     90-119      523        1.47-1.67
    120-134      246        1.41
    135-149      233        2.22      <-- the worst on the route, by far
    165-179      381        1.29      recovers once the turn is taken
    195-209      188        1.18

THE PLAN SAYS WHICH PUSH. plan[30] is the stop at 129 (turn to 303.3); plan[31]
to plan[35] push toward 130, 133, 136, 139, 142 along ~298; plan[36] is the stop
at 166, a 296-degree turn to 2.2 into the tables aisle. The 135-149 band IS
those last pushes, so the character arrives at the sharp turn already deep into
the bar.

WHAT IT DOES. With the flag on, when the entry about to be serviced is a PUSH
and the very next entry is the turn-only stop at BAR_STOP_INDEX, the pointer
steps over that push and the stop is taken one push early. It fires ONCE per
walk (a latch), it never skips a stop, and it never skips more than the entry
immediately before the named stop -- the wide relocalisations that jump the
pointer are a different population and are untouched.

WHY IT IS NOT A GRAVEYARD SHAPE. It REMOVES a push rather than adding chunks,
and it steers nothing mid-push. GRAVEYARD's summary is that every failed change
MOVED the character; this one moves it less, and the door-step patch of the same
family is the project's most recent measured win.

IT SHIPS OFF. `overnight/chain_trials.py --arms off,on --flag BAR_STOP_EARLY_TURN`
is the measurement. THE INSTRUMENT IS PRE-REGISTERED: the median fit scale in
the 135-149 band should fall toward 1.0 on the on-arm. Arrival is the outcome;
scale is the mechanism check, exactly as the 39-stop's scale decided the door
step.

Applies to: chain_walk.py, tests/routing/test_chain_walk.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch55.py [ROOT]
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
 ('''DOOR_STOP_EXTRA_PUSHES = 1''',
  '''DOOR_STOP_EXTRA_PUSHES = 1
# ONE FEWER PUSH BEFORE THE BAR'S SHARP TURN (patch55), the mirror of the door
# step and from the same source: the user, watching the stream, said "they
# walked too close to the bar when they should have turned earlier". The fit
# scale agrees -- over 2,560 credible fits the 135-149 band medians 2.22, the
# worst on the route, against 1.00 at the spawn and 1.29 once the turn is
# taken. Those waypoints are exactly plan[33..35], the last pushes before the
# 296-degree turn at 166. Ships OFF; --flag BAR_STOP_EARLY_TURN measures it,
# and the pre-registered instrument is that band's median scale falling
# toward 1.0.
BAR_STOP_EARLY_TURN = False
BAR_STOP_INDEX = 166'''),
 ('''def _near_stop(pi, plan):''',
  '''def _turn_early_at(pi, plan, index, latched):
    """Should the pointer step over plan[pi] to take a stop one push early?

    Pure, so every guard can be driven directly. Inside `walk` two of them --
    "the entry skipped must be a PUSH" and the once-per-walk latch -- are
    unreachable through anything `plan_indices` emits: it never puts two
    turn-only stops next to each other, and after a fired skip the next entry
    IS the stop. Mutants deleting them therefore survived a walk-level test,
    which is precisely the "guard that cannot fire" shape this project keeps
    finding. Held to their stated meaning here instead.
    """
    return (not latched
            and 0 <= pi
            and pi + 1 < len(plan)
            and plan[pi][1]              # the entry skipped must be a PUSH
            and not plan[pi + 1][1]      # ... and the next must be a stop
            and plan[pi + 1][0] == index)


def _near_stop(pi, plan):'''),
 ('''    door_stepped = False        # this SERVICING of DOOR_STOP_INDEX has had''',
  '''    bar_turned_early = False    # the once-per-walk latch for
                                # BAR_STOP_EARLY_TURN
    door_stepped = False        # this SERVICING of DOOR_STOP_INDEX has had'''),
 ('''        at_end = pi >= len(plan)''',
  '''        # TURN EARLY AT THE BAR (BAR_STOP_EARLY_TURN). Step over the push
        # immediately before the named stop, once per walk. It can only ever
        # skip a PUSH entry, and only when the very next entry is that stop,
        # so no stop is ever passed and the yaw-clearing rule above is
        # untouched.
        if (BAR_STOP_EARLY_TURN
                and _turn_early_at(pi, plan, BAR_STOP_INDEX,
                                   bar_turned_early)):
            bar_turned_early = True
            log(f"    turning EARLY at the bar: skipping the push to "
                f"{plan[pi][0]} so the stop at {BAR_STOP_INDEX} is taken one "
                f"push sooner (BAR_STOP_EARLY_TURN)")
            res["bar_turned_early"] = int(plan[pi][0])
            pi += 1
        at_end = pi >= len(plan)'''),
]

NEW_TESTS = '''
class BarStopEarlyTurn(unittest.TestCase):
    """patch55: one FEWER push before the bar's sharp turn.

    The user, watching the stream: "they walked too close to the bar when they
    should have turned earlier." The fit scale agrees -- over 2,560 credible
    fits the 135-149 band medians 2.22, the worst on the route, against 1.00 at
    the spawn and 1.29 once the turn is taken. Those waypoints are exactly the
    last pushes before the 296-degree turn at 166.

    The mirror of DOOR_STOP_EXTRA_PUSH, which shipped on the same kind of
    observation and won its A/B. This one ships OFF and the A/B decides, so
    every test drives the flag BOTH ways through a real walk.

    THE CHAIN: four walking pushes at one heading, then the turn-only stop
    (ly = 0.0), then one more push. plan_indices MERGES a run of same-heading
    pushes into as few entries as it can, and the shape that matters is that
    plan[1] is a PUSH whose next entry is the stop -- exactly the entry the
    rule exists to skip, and still AHEAD of the pointer when the branch runs.
    """

    ROWS = [(90.0, -0.35)] * 4 + [(0.0, 0.0), (10.0, -0.35)]

    def _wps(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate(self.ROWS, start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        return wps

    def _rig(self, table_at=6):
        ch = FakeChain(len(self._wps()),
                       [Fix(k=1), Fix(k=2), Fix(k=3), Fix(k=4), Fix(k=5),
                        Fix(k=6)],
                       default=None)
        ch.waypoints = self._wps()
        return Rig(ch, table_at=table_at)

    def _at(self, index):
        prev = chain_walk.BAR_STOP_INDEX
        chain_walk.BAR_STOP_INDEX = index
        self.addCleanup(setattr, chain_walk, "BAR_STOP_INDEX", prev)

    def _flag(self, on):
        prev = chain_walk.BAR_STOP_EARLY_TURN
        chain_walk.BAR_STOP_EARLY_TURN = on
        self.addCleanup(setattr, chain_walk, "BAR_STOP_EARLY_TURN", prev)

    def test_the_flag_ships_OFF_and_the_index_is_this_chains_bar_stop(self):
        # Literals (10.11). 166 is the turn-only stop in route_user_1853's plan
        # (its stops are 3, 39, 88, 129, 166, 196) and it is the 296-degree turn
        # the 135-149 overshoot precedes.
        self.assertIs(chain_walk.BAR_STOP_EARLY_TURN, False)
        self.assertEqual(chain_walk.BAR_STOP_INDEX, 166)
        # It invents no physical constant.
        self.assertEqual(chain_walk.PUSH_MAG, 0.45)
        self.assertEqual(chain_walk.PUSH_SEC, 0.40)

    def test_the_plan_this_class_uses_has_a_PUSH_right_before_its_stop(self):
        # ANTI-VACUITY for every test below: without a push immediately before
        # the stop, "one fewer push" would pass for the wrong reason. Note
        # plan_indices MERGES a run of same-heading pushes, so wp1 and wp2
        # become one entry -- which is why the entry before the stop is
        # plan[0], not plan[1].
        self.assertEqual(chain_walk.plan_indices(self._wps()),
                         [(1, True, 90.0), (4, True, 90.0), (5, False, 0.0),
                          (6, True, 10.0)])

    def _pushes(self, on, stop=5):
        """Run one walk at this arm and return (push count, result)."""
        prev_f, prev_i = (chain_walk.BAR_STOP_EARLY_TURN,
                          chain_walk.BAR_STOP_INDEX)
        chain_walk.BAR_STOP_EARLY_TURN, chain_walk.BAR_STOP_INDEX = on, stop
        try:
            rig = self._rig()
            res = rig.go()
            return rig.count("push"), res, rig
        finally:
            (chain_walk.BAR_STOP_EARLY_TURN,
             chain_walk.BAR_STOP_INDEX) = prev_f, prev_i

    def _turn_at(self, events, heading=0.0):
        """How many pushes happen BEFORE the stop's own turn."""
        for i, e in enumerate(events):
            if e[0] == "turn" and e[1] == heading:
                return sum(1 for x in events[:i] if x[0] == "push")
        return None

    def test_ON_takes_the_stops_turn_EARLIER_after_fewer_pushes(self):
        # WHAT THE RULE ACTUALLY DOES, and my first version of this test got it
        # wrong: skipping the plan entry does NOT delete a push, because the
        # loop still has to travel to the stop. It moves the stop's TURN
        # earlier -- the character turns after fewer pushes into the bar, which
        # is exactly "they should have turned earlier". Asserting a push
        # disappeared passed for no one and would have shipped a wrong claim.
        off, off_res, off_rig = self._pushes(False)
        on, on_res, on_rig = self._pushes(True)
        before_off = self._turn_at(off_rig.events)
        before_on = self._turn_at(on_rig.events)
        self.assertIsNotNone(before_off, "the stop's turn must happen at all")
        self.assertIsNotNone(before_on)
        self.assertLess(before_on, before_off,
                        f"the turn must come after FEWER pushes with the rule "
                        f"on (off={before_off}, on={before_on})")
        self.assertNotIn("bar_turned_early", off_res)
        self.assertEqual(on_res.get("bar_turned_early"), 4,
                         "the record names the push target that was skipped")

    def test_the_stop_is_still_TAKEN_never_skipped(self):
        # The guard is `plan[pi][1]`, and a turn-only stop is push=False. A rule
        # that skipped a STOP would drop its verification and its yaw clearing.
        _, _, rig = self._pushes(True)
        self.assertIn(("turn", 0.0), rig.events,
                      "the stop's own turn to 0.0 still happened")

    def test_it_fires_ONCE_per_walk(self):
        # The latch. Without it the branch re-fires and walks the pointer over
        # entries it was never meant to touch: the LAST push entry would be
        # skipped too and the walk would end without ever pushing past the stop.
        on, on_res, on_rig = self._pushes(True)
        self.assertEqual(on_res.get("bar_turned_early"), 4,
                         "recorded once, naming one skipped target")
        self.assertGreater(on, 0,
                           "a re-firing rule eats the pushes after the stop too")

    # ---- the predicate, where the defensive guards can be driven ----------

    PUSH_THEN_STOP = [(1, True, 90.0), (4, True, 90.0), (5, False, 0.0),
                      (6, True, 10.0)]

    def test_the_predicate_fires_on_a_push_immediately_before_the_stop(self):
        self.assertTrue(
            chain_walk._turn_early_at(1, self.PUSH_THEN_STOP, 5, False))

    def test_the_predicate_REFUSES_to_skip_a_STOP(self):
        # Unreachable through plan_indices, which never emits two adjacent
        # stops, so a walk-level test cannot kill a mutant that deletes this
        # guard. Driven directly.
        stop_then_stop = [(4, False, 0.0), (5, False, 0.0)]
        self.assertFalse(
            chain_walk._turn_early_at(0, stop_then_stop, 5, False),
            "the entry skipped must be a PUSH")

    def test_the_predicate_REFUSES_once_the_latch_is_set(self):
        self.assertFalse(
            chain_walk._turn_early_at(1, self.PUSH_THEN_STOP, 5, True),
            "the latch makes it once per walk")

    def test_the_predicate_REFUSES_a_push_before_another_PUSH(self):
        self.assertFalse(
            chain_walk._turn_early_at(0, self.PUSH_THEN_STOP, 5, False),
            "plan[1] is a push, not the stop")

    def test_the_predicate_REFUSES_a_PUSH_that_merely_shares_the_index(self):
        # The one case that isolates "the next entry must be a STOP": a PUSH
        # whose target happens to equal BAR_STOP_INDEX. Without this the guard
        # is decorative -- a mutant deleting it survived every other test here,
        # because no other case had a push carrying the stop's number.
        push_shares = [(1, True, 90.0), (5, True, 90.0), (6, False, 0.0)]
        self.assertFalse(
            chain_walk._turn_early_at(0, push_shares, 5, False),
            "plan[1] targets 5 but it is a PUSH, so this must not fire")
        # ... and the same shape WITH a stop there does fire, so the test is
        # not passing for want of any firing case at all.
        stop_there = [(1, True, 90.0), (5, False, 0.0), (6, True, 10.0)]
        self.assertTrue(chain_walk._turn_early_at(0, stop_there, 5, False))

    def test_the_predicate_REFUSES_the_wrong_stop_and_the_plans_end(self):
        self.assertFalse(
            chain_walk._turn_early_at(1, self.PUSH_THEN_STOP, 999, False))
        self.assertFalse(
            chain_walk._turn_early_at(3, self.PUSH_THEN_STOP, 5, False),
            "there is no entry after the last one")

    def test_pointed_at_a_DIFFERENT_stop_it_does_nothing_here(self):
        # It is not "skip a push somewhere near a stop": the next entry must be
        # the NAMED stop. Compared against the OFF arm, not an absolute count.
        off, _, _ = self._pushes(False)
        elsewhere, res, _ = self._pushes(True, stop=999)
        self.assertEqual(elsewhere, off,
                         "pointed at a stop this plan does not have, it must "
                         "change nothing")
        self.assertNotIn("bar_turned_early", res)

'''

edits_t = [
 ("class SettleProbe(unittest.TestCase):", NEW_TESTS + "\nclass SettleProbe(unittest.TestCase):"),
]

# ---------------------------------------- assert EVERYTHING, then write
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a[:50], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:50], t.count(a))
assert "BAR_STOP_EARLY_TURN" not in c and "BarStopEarlyTurn" not in t
assert "_turn_early_at" not in c
assert c.count("DOOR_STOP_EXTRA_PUSH = True") == 1, "the door step is untouched"
assert c.count("        at_end = pi >= len(plan)") == 1

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(c)
ast.parse(t)
assert c.count("BAR_STOP_EARLY_TURN = False") == 1
assert c.count("BAR_STOP_INDEX = 166") == 1
assert c.count("def _turn_early_at(") == 1
assert c.count("_turn_early_at(pi, plan, BAR_STOP_INDEX,") == 1
assert c.count("bar_turned_early = True") == 1
assert c.count("bar_turned_early = False") == 1
assert c.count("DOOR_STOP_EXTRA_PUSH = True") == 1
assert t.count("class BarStopEarlyTurn(unittest.TestCase):") == 1

open(C, "w").write(c)
open(T, "w").write(t)
print("patch55 applied to", ROOT)
