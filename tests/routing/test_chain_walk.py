"""chain_walk.walk() — the closed loop, driven entirely by stubs.

Nothing here touches the console, the map, or any input path: turn_to, the
forward push, the sidestep, the jump and at_table are all injected, and the
clock is a counter the stubs advance. What is pinned is the CONTROL LOGIC, one
clause per test, because each is somewhere this project has been wrong before:

  (a) the prompt STOPS everything at once, including on the very first frame
  (b) k advances on `reached` and NEVER further than one window in a step
  (c) STALL_MAX non-advancing fixes -> one escape, and never two in a row
  (d) MISS_MAX unmeasurable fixes -> one escape
  (e) at most ONE lateral push per iteration, gated on pose.ALIGN_TOL_PX,
      sized by the closed-loop gain, and in the direction pose.offset means
  (f) the time cap fails as "timed out", never as an arrival
  (g) every iteration is recorded, and with shots= every frame is saved
  (h) BOTH counters are CONSECUTIVE — a good fix resets the misses and an
      advance resets the stalls (added after a skeptic deleted each reset in
      turn and the suite stayed green)
  (i) the iteration arithmetic is reported, a timeout says whether the CHAIN or
      the NAVIGATION ran out, and the journal lands on disk AS THE WALK GOES
  (j) overnight/chain_trials.py's scoring: the harness's wall clock is never
      overwritten by walk()'s, a killed child's rows are recovered, and a
      slow setup is INVALID rather than a navigation failure
  (k) the END of the chain is a BOUNDED phase: k frozen is never "advanced",
      the stall counter rises there so the escape ladder can fire, and the walk
      gives up with a named failure instead of pushing on past the table
  (l) the DEFAULT wrappers — the only place this module's vocabulary meets
      slow_traverse.walk_leg's real axes — put the forward push on ly NEGATIVE
      and the sidestep on lx, with the signs pose.offset means
  (m) BLIND NEAR A TURN STOP TURNS EARLY, once per blockage and re-armed only
      by progress the sensor actually SAW, before any escape rung -- the NPC on
      the turn point (2026-09-07), whose whole cost was that the loop never
      reached the turn
  (n) PAST THE LAST STOP a huge dx is a TURN toward the dealer, not a sidestep,
      and the yaw it takes rides on every remaining heading -- the four trials
      that stood beside the table strafing at the cap against dx -460 to -777.
      It answers to every gate the strafe it replaces answers to: no end turn
      in an iteration that escaped or whose predecessor did, none on a dx the
      detour hold is suppressing, and a look-back regression drops the yaw

THE STRAFE SIGN, WHICH IS THE ONE THING HERE THAT COULD SILENTLY DO THE
OPPOSITE OF WHAT IT SAYS. `slow_traverse.walk_leg` sends `left_x = to_axis(lx)`
and `walk_steps.walk_forward` sends `left_x = to_axis(strafe)` — the same axis —
and `walk_steps.unstick` names -0.6 "left" and +0.6 "right". `pose.align_lateral`
picks `side = +1 if dx > 0` under the comment "the camera is LEFT of the
reference — so strafe RIGHT". So POSITIVE lx IS RIGHT, and a fix with dx = +80
must produce a strafe with lx > 0. An inverted sign would still walk, still log,
and still look like a working controller while doubling the error every time.

A NOTE ON THE CHAIN LENGTHS BELOW. at_table() is only believed within
TABLE_CHECK_TAIL waypoints of the end, so a 4-waypoint chain has the check live
from the first iteration and a 10-waypoint one does not. Both shapes are used
deliberately, and `test_the_prompt_is_only_believed_near_the_end` is the test
that pins the difference.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import chain_walk
import pose

# The harness that SCORES the walk. It is pure enough to test offline —
# `import _harness` pulls in nothing but the standard library, and no module
# name under overnight/ collides with a repo-root one — and it had no test at
# all until a skeptic pointed out that `classify`, the function that decides
# INVALID vs TIMED_OUT, was the least exercised code in the build.
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
import chain_trials

_AUTO = object()          # "give this waypoint a heading" vs. an explicit None


def _rows_on_disk(path):
    """How many complete JSON rows the journal holds RIGHT NOW."""
    try:
        with open(path) as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


class Fix:
    """What chain.locate() hands back. Attribute access only, like the real one."""

    def __init__(self, k, scale=1.0, dx=0.0, dy=0.0, inliers=120, second=5,
                 k_float=None, detail="stub", second_k=None, second_dx=0.0):
        self.k = k
        # WHO the runner-up was. None = "cannot say", the default a Fix built
        # before these fields existed reports, and NOT evidence of a tie.
        self.second_k = second_k
        self.second_dx = second_dx
        self.scale = scale
        self.dx = dx
        self.dy = dy               # chain.Fix carries it; recorded, never acted on
        self.inliers = inliers
        self.second = second
        self.k_float = float(k) if k_float is None else k_float
        self.detail = detail


class Wp:
    def __init__(self, i, heading=_AUTO):
        self.index = i
        self.heading = float(i * 10) if heading is _AUTO else heading


class FakeChain:
    """waypoints + a SCRIPTED locate(); reached() is the spec's rule verbatim."""

    def __init__(self, n, fixes=(), default=None, headings=None, wide=None,
                 lookback="script"):
        self.waypoints = [Wp(i, _AUTO if headings is None else headings[i])
                          for i in range(n)]
        self._fixes = list(fixes)
        self.default = default
        self.wide = wide              # what a WIDE search (window > 3) returns
        # A LOOK-BACK (window > WINDOW, < WIDE_AHEAD) is a second look at the
        # SAME image. By default it consumes the script like any locate() --
        # the regression tests script it that way -- but a test about a run
        # of consecutive fits must not have every other fit eaten by it.
        self.lookback = lookback
        self.locate_calls = []
        self.wide_calls = []

    def locate(self, img, k_hint, window=3):
        if window >= chain_walk.WIDE_AHEAD:
            # A WIDE search (the sixty-wide window; a look-back is narrower) is
            # served from `wide`, never from the script, so the scripted tests
            # do not depend on how often the loop looks far.
            self.wide_calls.append(k_hint)
            return self.wide
        if window > chain_walk.WINDOW and self.lookback != "script":
            return self.lookback
        self.locate_calls.append(k_hint)
        return self._fixes.pop(0) if self._fixes else self.default

    def reached(self, fix, k):
        return fix.k > k or (fix.k == k and fix.scale >= 1.0)


class FakeImage:
    def __init__(self, n):
        self.n = n

    def save(self, path, quality=88):
        with open(path, "w") as fh:
            fh.write(str(self.n))


def without_stuck(go, *a, **kw):
    """Run a walk with the no-progress rule OFF, for tests whose subject is the
    time cap on a scenario that never advances (the stuck rule would end it
    first, correctly, and hide the thing under test)."""
    old = chain_walk.NO_PROGRESS_MAX
    chain_walk.NO_PROGRESS_MAX = 10 ** 6
    try:
        return go(*a, **kw)
    finally:
        chain_walk.NO_PROGRESS_MAX = old


def always_turning(go, *a, **kw):
    """Run a walk with the turn-skip OFF, so every iteration costs the fake
    clock the same 1.0s (turn 0.5 + push 0.4 + capture 0.1) that the cap
    arithmetic in the counter tests was written against. A stalled target
    repeats its heading and the loop skips that turn by design."""
    old = chain_walk.TURN_SKIP_DEG
    chain_walk.TURN_SKIP_DEG = -1.0
    try:
        return go(*a, **kw)
    finally:
        chain_walk.TURN_SKIP_DEG = old


class Rig:
    """Every console call, in order, on one list — plus a clock only the stubs
    advance, so the `seconds` in the result is exactly determined."""

    TURN_SEC, CAPTURE_SEC, JUMP_SEC = 0.5, 0.1, 0.4

    def __init__(self, chain, table_at=None):
        self.chain = chain
        self.table_at = table_at      # capture number at which the prompt appears
        self.events = []
        self.t = 0.0
        self.captures = 0
        # Set by a test that passes journal=: how many rows were ON DISK at
        # each at_table call, which is the only way to show offline that the
        # journal is written AS THE WALK GOES rather than at the end.
        self.journal = None
        self.journal_lines = []

    # --- the injected console ---
    def now(self):
        return self.t

    def sleep(self, secs):
        self.t += secs
        self.events.append(("sleep", secs))

    def back(self, mag, secs):
        self.t += secs
        self.events.append(("back", mag, secs))

    def capture(self):
        self.captures += 1
        self.t += self.CAPTURE_SEC
        self.events.append(("capture", self.captures))
        return FakeImage(self.captures)

    def turn_to(self, heading):
        self.t += self.TURN_SEC
        self.events.append(("turn", heading))

    def push(self, mag, secs):
        self.t += secs
        self.events.append(("push", mag, secs))

    def strafe(self, lx, secs):
        self.t += secs
        self.events.append(("strafe", lx, secs))

    def jump(self):
        self.t += self.JUMP_SEC
        self.events.append(("jump",))

    def at_table(self, img):
        v = self.table_at is not None and img.n >= self.table_at
        self.events.append(("at_table", img.n, v))
        if self.journal:
            self.journal_lines.append(_rows_on_disk(self.journal))
        return v

    # --- helpers ---
    def go(self, **kw):
        return chain_walk.walk(
            self.chain, self.capture, lambda: 87.0, log=lambda *a: None,
            turn_to=self.turn_to, push=self.push, strafe=self.strafe,
            jump=self.jump, at_table=self.at_table, now=self.now,
            sleep=self.sleep, back=self.back, **kw)

    def count(self, name):
        return sum(1 for e in self.events if e[0] == name)

    def strafes(self):
        return [e for e in self.events if e[0] == "strafe"]


class ArrivalStopsEverything(unittest.TestCase):
    """(a) the prompt is the arrival authority and it stops the loop AT ONCE."""

    def test_prompt_on_the_first_frame_means_no_push_at_all(self):
        # A chain recorded to the table ENDS at the prompt, so a walk started
        # from there is already finished. One "just to get going" push would
        # walk the character out of the prompt zone.
        rig = Rig(FakeChain(6, [Fix(k=1)]), table_at=1)
        res = rig.go()
        self.assertTrue(res["arrived"])
        self.assertEqual(res["pushes"], 0)
        self.assertEqual(rig.count("push"), 0)
        self.assertEqual(rig.count("turn"), 0)
        self.assertEqual(rig.count("strafe"), 0)
        self.assertEqual(rig.count("jump"), 0)
        self.assertEqual(rig.chain.locate_calls, [],
                         "nothing needs locating once the prompt is on screen")
        self.assertEqual([f["action"] for f in res["fixes"]], ["arrived"])
        self.assertIsNone(res["failure"])

    def test_nothing_moves_after_the_prompt_appears(self):
        # n=4, so the tail check is live from the first iteration. The prompt
        # appears on capture 4 = the frame taken at the end of iteration 3.
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5, dx=200.0)),
                  table_at=4)
        res = rig.go()
        self.assertTrue(res["arrived"])
        self.assertEqual(res["pushes"], 3, "one push per iteration, then stop")
        self.assertEqual(rig.count("push"), 3)
        last = max(i for i, e in enumerate(rig.events)
                   if e[0] == "at_table" and e[2])
        after = [e for e in rig.events[last + 1:]
                 if e[0] in ("push", "turn", "strafe", "jump")]
        self.assertEqual(after, [],
                         f"the console was driven AFTER the prompt: {after}")
        self.assertEqual(res["fixes"][-1]["action"], "arrived")
        self.assertIsNone(res["fixes"][-1]["lateral"])
        # dx was 200 on every fix, so a lateral WOULD have fired on the
        # arriving iteration had the check not returned first. Without this the
        # test could pass on a walk that simply never corrects anything.
        self.assertEqual(rig.count("strafe"), 2,
                         "iterations 1 and 2 must have corrected laterally")

    def test_the_prompt_is_believed_on_every_iteration(self):
        # at_table is True from the second capture on, and k is far from the
        # end of a 10-waypoint chain: the walk stops at ONCE anyway. The old
        # tail gate would have pushed on twice; if k lagged while the
        # character stood in the prompt it would have escaped and walked away.
        self.assertEqual(chain_walk.TABLE_CHECK_TAIL, 30)
        rig = Rig(FakeChain(10, [Fix(k=3), Fix(k=6)]), table_at=2)
        res = rig.go()
        self.assertTrue(res["arrived"])
        self.assertEqual(res["pushes"], 1)
        self.assertEqual([f["action"] for f in res["fixes"]], ["arrived"])
        self.assertEqual([e[1] for e in rig.events if e[0] == "at_table"],
                         [1, 2], "asked on the first frame and after push 1")
        self.assertEqual(rig.chain.locate_calls, [],
                         "the sensor is not even asked once the prompt is up")

    def test_a_stationary_run_becomes_one_turn_only_target(self):
        # A recorded corner: walking east, a 4-frame stationary turn (ly 0.0,
        # headings 90 -> 0), then walking north. The plan turns ONCE to the
        # run's last heading and pushes nothing during the turn; the old loop
        # pushed 0.4 s along each intermediate heading and cut the corner.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (75.0, 0.0),
                                     (45.0, 0.0), (15.0, 0.0), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        plan = chain_walk.plan_indices(wps)
        # Push targets are one PUSH apart by the recorded stick (0.35 x 0.25 s
        # = 0.0875 u a frame against 0.18 u a push), so frame 2 is not a target;
        # the first walking frame after a stop always is, and so is the last.
        self.assertEqual(plan, [(1, True, 90.0), (6, False, 0.0), (7, True, 0.0),
                                (8, True, 0.0)])
        # Four locates: the turn-only iteration VERIFIES the stop against its
        # own frame (credible here), the arrival iteration asks nothing.
        ch = FakeChain(9, [Fix(k=1, scale=1.0), Fix(k=6, inliers=100),
                           Fix(k=7, scale=1.0), Fix(k=8, scale=1.0)])
        ch.waypoints = wps
        rig = Rig(ch, table_at=6)
        res = rig.go()
        self.assertTrue(res["arrived"])
        actions = [f["action"] for f in res["fixes"]]
        self.assertEqual(actions, ["advanced", "turned", "advanced",
                                   "advanced", "arrived"])
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [90.0, 0.0], "one turn per heading change, none per frame")
        pushes = [e for e in rig.events if e[0] == "push"]
        self.assertEqual(len(pushes), 4, "no push during the stationary run")

    def test_an_unknown_stick_is_walked_not_collapsed(self):
        # No controller on the Mac: the recorder writes lx=ly=0.0 and says so
        # in the note. Every such frame must stay a push target.
        w = [Wp(i, 10.0 * i) for i in range(4)]
        for x in w:
            x.lx = 0.0; x.ly = 0.0; x.note = "stick:unknown"
        self.assertEqual([p for _, p, _ in chain_walk.plan_indices(w)],
                         [True, True, True])
        for x in w:
            x.note = ""
        self.assertEqual([p for _, p, _ in chain_walk.plan_indices(w)],
                         [False], "the same zeros WITH a stick are one stationary run")

    def test_a_heading_the_compass_missed_inherits_cam_then_the_last_known(self):
        w = [Wp(0, 10.0), Wp(1, None), Wp(2, None), Wp(3, 30.0)]
        w[1].cam = 20.0
        plan = chain_walk.plan_indices(w)
        self.assertEqual([h for _, _, h in plan], [20.0, 20.0, 30.0])
        self.assertEqual([h for _, _, h in chain_walk.plan_indices(
            [Wp(0, None), Wp(1, None), Wp(2, None)])], [None, None],
            "a chain with no headings at all is never turned")


class IndexAdvance(unittest.TestCase):
    """(b) reached -> k advances, and never further than one window."""

    def test_k_advances_by_at_most_the_window(self):
        # Every fix claims k=9 — one wrong match must not teleport the plan to
        # the end of the chain. WINDOW is 3, so k may only reach 3, 6, 9.
        rig = Rig(FakeChain(10, [Fix(k=9), Fix(k=9), Fix(k=9)]), table_at=5)
        res = rig.go()
        self.assertEqual(chain_walk.WINDOW, 3)
        self.assertEqual(chain_walk.ADVANCE_MAX, 1)
        self.assertEqual([f["k"] for f in res["fixes"]], [1, 2, 3, 3],
                         "k advanced further than ADVANCE_MAX in one step")
        self.assertEqual(rig.chain.locate_calls, [0, 1, 2],
                         "locate must be asked from the CURRENT k each time; "
                         "the arrival iteration never asks it")

    def test_a_weak_fix_neither_advances_nor_steers(self):
        # 13 inliers and a huge dx: trial 1's junk. It must not move k and it
        # must NOT strafe; four in a row are a stall, so the escape still fires.
        self.assertEqual(chain_walk.FIX_MIN_INLIERS, 29)
        # k=9 is further than WINDOW from every target it will be asked about,
        # so this weak fix is blindness, not corroboration (see the test below
        # for a weak fix that NAMES the target).
        ch = FakeChain(30, default=Fix(k=29, scale=1.2, dx=-131.0, inliers=13))   # clear of the tail cap
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=11.05)
        # k follows the PLAN (dead-reckoned to the target for BLIND_MAX
        # pushes), never the weak fix's own claim of 3.
        self.assertEqual([f["k"] for f in res["fixes"]], [1, 2, 3, 4, 5, 6, 6, 6, 6, 6, 6])
        self.assertNotIn(3, [f["k"] for f in res["fixes"]][4:])
        self.assertIn("weak", [f["action"] for f in res["fixes"]])
        # A lone weak dx never steers. Identical junk repeated is the one
        # thing the junk-run rule DOES steer on (every fourth agreeing fit),
        # so the strafes here are that rule's and nothing else's.
        lat = [(i, f["lateral"]) for i, f in enumerate(res["fixes"]) if f.get("lateral")]
        self.assertEqual(len(lat), len(rig.strafes()))
        self.assertTrue(lat and lat[0][0] >= chain_walk.JUNK_CONSISTENT_N - 1,
                        "no strafe before the fourth agreeing junk fit: %r" % lat)
        self.assertTrue(all(l.get("consistent") == chain_walk.JUNK_CONSISTENT_N for _, l in lat), lat)
        self.assertEqual(rig.count("jump"), 1, "four weak fixes are a stall")

    def test_a_weak_fix_that_names_the_target_advances_and_keeps_the_blind_budget(self):
        # Trial 1c: thin corridor fits (18-23 inliers) that were RIGHT ate the
        # blind budget, leaving none for the featureless door. A weak fix
        # within WINDOW of the target advances k to the TARGET and resets the
        # budget; it still never steers.
        fixes = [Fix(k=1, inliers=20, dx=-180.0),     # weak, names target 1
                 Fix(k=3, inliers=15, dx=150.0),      # weak, names 3 (target 2, within WINDOW)
                 None, None, None, None,              # four blind advances (budget intact)
                 None]                                # the fifth is a miss
        rig = Rig(FakeChain(30, fixes, default=None), table_at=None)
        res = always_turning(rig.go, time_cap=7.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced-weak", "advanced-weak"])
        self.assertEqual([f["k"] for f in res["fixes"]][:2], [1, 2],
                         "advance is to the TARGET, not to the weak fix's own k")
        self.assertEqual(rig.strafes(), [], "a weak dx never steers")
        self.assertEqual(acts[2:6], ["blind-advance"] * 4,
                         "the blind budget was not spent on the weak-but-right fits")

    def test_a_junk_fit_is_blindness_and_a_thin_fit_keeps_the_blind_budget(self):
        # Trial 3: nine pushes on 6-7-inlier fits walked into an NPC. Under
        # WEAK_MIN_INLIERS a fix is blindness (spends the budget); a thin fit
        # at or above it advances but neither spends nor restores the budget.
        self.assertEqual(chain_walk.WEAK_MIN_INLIERS, 15)
        self.assertEqual(chain_walk.BLIND_MAX, 6)
        junk = Fix(k=2, inliers=7)
        thin = Fix(k=5, inliers=20)     # names a LATER waypoint (audit)
        # Every locate past k=0 that is not credible is followed by a look-
        # back locate, which consumes the next scripted entry: main/look-back
        # pairs, so the thin fit is the SIXTH call.
        fixes = [junk] + [junk, junk] * 2 + [thin] + [None] * 12
        rig = Rig(FakeChain(20, fixes, default=None), table_at=None)
        res = always_turning(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:3], ["blind-advance"] * 3, "junk spends the budget")
        self.assertEqual(acts[3], "advanced-weak")
        # budget so far: 3 spent, the thin fit changed nothing -> 3 blind left
        self.assertEqual(acts[4:7], ["blind-advance"] * 3)
        self.assertNotIn("blind-advance", acts[7:], "the budget was 6, not 6 + 3")

    def test_every_blockage_starts_the_ladder_at_jump(self):
        # Two blockages in one walk, a credible advance between them. The
        # second must start at jump again (the rung counter used to carry on:
        # the second blockage got 'back', and a late wedge got only sidesteps).
        self.assertEqual(chain_walk.PROGRESS_ACTIONS, ("advanced", "relocalised", "regressed", "turned"))
        fixes = [None] * 9 + [Fix(k=7)] + [None] * 9
        ch = FakeChain(60, fixes, default=None, lookback=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertIn("advanced", acts[8:11], acts)
        self.assertEqual([a for a in acts if a.startswith("escape:")][:2],
                         ["escape:jump", "escape:jump"], acts)

    def test_a_sidestep_rung_is_a_detour_and_the_correction_back_is_held(self):
        # Pressed on an obstacle: six blind, misses, jump, back, LEFT 0.6 s.
        # Then a credible fix with the scene 200 px RIGHT (i.e. "strafe right"
        # = back into the obstacle) must be HELD; a fix with the scene further
        # LEFT still steers; three targets on, the right correction steers again.
        self.assertEqual((chain_walk.ESCAPE_STRAFE_SEC, chain_walk.DETOUR_TARGETS), (0.6, 3))
        fixes = [None] * 15 + [Fix(k=7, inliers=120, dx=200.0), Fix(k=8, inliers=120, dx=-200.0),
                 Fix(k=9, inliers=120, dx=200.0), Fix(k=10, inliers=120, dx=200.0), Fix(k=11, inliers=120, dx=200.0)]
        ch = FakeChain(60, fixes, default=Fix(k=12), lookback=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[14], "escape:left", acts)
        self.assertEqual(rig.strafes()[0], ("strafe", -0.45, 0.6), "the LEFT rung is a 0.6 s detour: %r" % rig.strafes()[:3])
        lat = [(i, f.get("lateral")) for i, f in enumerate(res["fixes"]) if f.get("lateral")]
        held = [l for _, l in lat if l.get("held") == "detour"]
        self.assertEqual([l["dx"] for l in held], [200.0], "the first right correction after the LEFT rung is held: %r" % lat)
        steered = [l["dx"] for _, l in lat if "held" not in l]
        self.assertEqual(steered[0], -200.0, "a correction further from the obstacle still steers")
        self.assertIn(200.0, steered[1:], "past DETOUR_TARGETS the right correction steers again")

    def test_the_right_rung_after_a_left_rung_covers_both_sides(self):
        rig = Rig(FakeChain(30, default=None), table_at=None)
        always_turning(rig.go, time_cap=400.0)
        s = [(x[1] > 0, x[2]) for x in rig.strafes()]
        self.assertEqual(s, [(False, 0.6), (True, 1.2)], "LEFT 0.6, then RIGHT 1.2 (0.6 net on the other side): %r" % s)

    def test_a_prompt_seen_before_the_tail_does_not_end_the_walk(self):
        # Tenth launch trial 12: the prompt check fired at k=58 and the walk
        # "arrived" on the street. On a 205-waypoint chain the check is asked
        # only when the target is >= 175: a prompt "visible" from the fifth
        # capture is ignored until then, and believed at once after.
        self.assertEqual(chain_walk.TABLE_CHECK_TAIL, 30)
        ch = FakeChain(205, default=Fix(k=204))    # every push reaches its target
        rig = Rig(ch, table_at=5)
        res = without_stuck(rig.go, time_cap=10 ** 6)
        self.assertTrue(res["arrived"])
        self.assertGreaterEqual(res["fixes"][-1]["target"], 175, res["fixes"][-1])
        self.assertGreater(res["iterations"], 100, "the walk went on past the early prompt")
        # and a short chain is unaffected: n - 30 < 0, the gate is always open
        rig2 = Rig(FakeChain(6, [Fix(k=1)]), table_at=1)
        self.assertTrue(rig2.go()["arrived"])

    def test_the_walk_declares_itself_lost_instead_of_burning_the_cap(self):
        self.assertEqual(chain_walk.LOST_MAX, 13)
        rig = Rig(FakeChain(30, default=None), table_at=None)
        res = always_turning(rig.go, time_cap=400.0)
        self.assertFalse(res["arrived"])
        self.assertTrue(res["failure"].startswith("lost at k="), res["failure"])
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:6], ["blind-advance"] * 6)
        self.assertEqual(acts[-1], "lost")
        self.assertEqual(len(acts), 6 + 13, "six blind, thirteen lost, then out")
        self.assertLess(res["seconds"], 60.0, "gave up long before the cap")

    def test_a_turn_stop_that_does_not_match_is_retried_after_one_more_push(self):
        # Chain: spawn, 2 walking frames east (90), a stop turning to 0, then
        # walking north. A retry still happens on evidence of being SHORT.
        #
        # WHY THE FIT HERE CHANGED (patch41). This test used to hand the stop
        # an 8-INLIER fit at the earlier waypoint 2 and call that "evidence of
        # being short, however thinly". It is not evidence of anything: 8 is
        # under WEAK_MIN_INLIERS (15), the count at which a fit stops being
        # junk, and b11 trial 13 was lost by exactly that reading -- a
        # 13-inlier scrap off an NPC's edges bought three retry pushes that
        # went through a side doorway into an unmapped corridor. A retry now
        # needs a fit of at least FIX_MIN_INLIERS naming an index below the
        # stop.
        #
        # A credible fit normally VERIFIES the stop outright (`verified` does
        # not look at the index), so the one shape that is credible AND
        # unverified is a TIE: 90 inliers against a 90-inlier runner-up that
        # is a different place. That is what this stop hands back three times
        # -- one step back, one wait, then the retry push -- and the fourth
        # read is clean, so the plan proceeds north.
        self.assertEqual(chain_walk.FIX_MIN_INLIERS, 29)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual(chain_walk.plan_indices(wps),
                         [(1, True, 90.0), (3, False, 0.0), (4, True, 0.0), (5, True, 0.0)])

        def tied_at(k):
            # near-tied counts, a runner-up at a DIFFERENT place, and a dx
            # that disagrees by more than STOP_TIE_DX_PX: credible, and not
            # verification.
            f = Fix(k=k, inliers=90, second=90)
            f.second_k, f.second_dx = 8, 900.0
            return f

        # locate calls: it1 push -> Fix(1); then the stop three times (head-on
        # plus its two looks each) reading a credible TIE at the EARLIER
        # waypoint 2; it5 the stop reads cleanly; it6 push -> Fix(4)
        ch = FakeChain(6, [Fix(k=1), tied_at(2), None, None, tied_at(2), None, None,
                           tied_at(2), None, None, Fix(k=3, inliers=90),
                           Fix(k=4), Fix(k=5)], default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=14)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:6], ["advanced", "turn-back", "turn-wait",
                                    "turn-retry", "turned", "advanced"], acts)
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        self.assertIn(335.0, turns, "the stop looks left")
        self.assertIn(25.0, turns, "... and right")
        self.assertIn(90.0, turns[4:], "the retry turns BACK to the walking heading")
        self.assertEqual(rig.chain.locate_calls[1], 3,
                         "the stop is verified against its OWN index")
        self.assertTrue(res["arrived"])

    def test_a_stop_is_advanced_unverified_only_after_STOP_REWIND_MAX_rewinds(self):
        # WHAT THIS TEST USED TO SAY, and why it could not stay (patch41). It
        # was `..._accepted_unverified_after_the_retries`: three 9-inlier fits
        # bought three retry pushes and then k was stamped at the stop. Both
        # halves are gone -- a thin fit no longer buys a retry (rule B), and
        # an unverified stop no longer advances on the first pass (rule C).
        # What survives is the END of that story, which is the part worth
        # keeping: after STOP_REWIND_MAX re-approaches that still cannot see
        # the stop, the stop IS advanced unverified exactly as before, so a
        # chain can never circle one stop forever.
        #
        # Nothing ever fits here after the first push. Two blind pushes carry
        # the estimate to 7, the stop at 9 fits nothing head-on or either
        # side, and the loop backs off, waits and REWINDS to 1 -- the last
        # waypoint a credible fit named. Twice. The third time it gives up and
        # takes the stop.
        self.assertEqual(chain_walk.STOP_REWIND_MAX, 2)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual(chain_walk.plan_indices(wps),
                         [(1, True, 90.0), (4, True, 90.0), (7, True, 90.0),
                          (9, False, 0.0), (10, True, 0.0), (13, True, 0.0)])
        ch = FakeChain(14, [Fix(k=1)], default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:16], [
            "advanced", "blind-advance", "blind-advance",
            "turn-back", "turn-wait", "turned-unverified",
            "blind-advance", "blind-advance",
            "turn-back", "turn-wait", "turned-unverified",
            "blind-advance", "blind-advance",
            "turn-back", "turn-wait", "turned-unverified"], acts)
        rewound = [f for f in res["fixes"] if "rewound_to" in f]
        self.assertEqual([f["rewound_to"] for f in rewound], [1, 1],
                         "exactly STOP_REWIND_MAX rewinds, both to the last credible k")
        self.assertEqual(res["fixes"][15]["k"], 9,
                         "the third time, the stop is taken unverified as before")
        self.assertNotIn("rewound_to", res["fixes"][15])
        self.assertEqual(chain_walk.TURN_RETRY_MAX, 3)

    def test_no_retry_pushes_at_a_stop_after_a_wall_scale_fit(self):
        # The same stop as above, but the last credible fit before it read
        # scale 2.9 (pressed close to something): the retry pushes along the
        # old heading are skipped and the stop is accepted unverified at once.
        # The control is the test above (scale 1.0: three retries).
        self.assertEqual(chain_walk.WALL_SCALE, 2.5)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # THE FIT AT THE STOP CHANGED (patch41). It used to be a 9-inlier
        # scrap, which under rule B cannot buy a retry whatever the scale --
        # so this test would have passed for the wrong reason with the
        # WALL_SCALE clause deleted. It is now a CREDIBLE tie at the earlier
        # waypoint 1, which IS retry evidence, and the wall-scale clause is
        # the only thing between it and a turn-retry. The control is the
        # retry test above: the same shape at scale 1.0, which does retry.
        def tied_at(k):
            f = Fix(k=k, inliers=90, second=90)
            f.second_k, f.second_dx = 8, 900.0
            return f

        ch = FakeChain(4, [Fix(k=1, scale=2.9, inliers=90),
                           tied_at(1), None, None, tied_at(1), None, None,
                           tied_at(1), None, None], default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=40.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertNotIn("turn-retry", acts, acts)
        self.assertEqual(acts[:4], ["advanced", "turn-back", "turn-wait",
                                    "turned-unverified"], acts)

    def test_an_unverified_stop_looks_left_and_right_before_giving_up(self):
        # Head-on the stop's frame fits nothing; looking 25 deg LEFT it fits
        # credibly with the scene 60 px right of centre in that view -> the
        # stop is verified, one strafe LEFT (the scene is ~430 px left of the
        # walking heading), then the plan goes on. No retry push.
        self.assertEqual(chain_walk.STOP_LOOK_DEG, (-25.0, 25.0))
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # locates: it1 push -> Fix(1); it2 stop head-on -> None; look -25 -> credible
        # (dx +60); look +25 -> None; it3 push -> Fix(3); it4 -> Fix(4)
        ch = FakeChain(5, [Fix(k=1), None, Fix(k=2, inliers=90, dx=60.0), None,
                           Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=7)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned-looked"])
        turns = [round(e[1]) for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns, [90, 0, 335, 25, 0], "look left, look right, back to the stop")
        strafes = rig.strafes()
        self.assertEqual(len(strafes), 1)
        self.assertLess(strafes[0][1], 0.0, "the scene was to the LEFT: strafe left")
        self.assertLessEqual(strafes[0][2], chain_walk.LATERAL_CAP_SEC,
                             "a yawed fit earns one ordinary correction, never a double one")
        self.assertNotIn("turn-retry", acts)
        self.assertEqual(res["fixes"][1]["lateral"]["deg"], -25.0)

    def test_a_stop_whose_frame_fits_nothing_is_looked_around_then_retried(self):
        # No fit at the stop and nothing on either side: no evidence of being
        # past, so the retry pushes run (batch 5b trials 5-6 were short of the
        # door with a junk fit and were wrongly read as "past").
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # it2: head-on None, looks None, None -> one step BACK for clearance;
        # it3: still nothing -> WAIT once; it4: head-on credible -> turned
        ch = FakeChain(5, [Fix(k=1), None, None, None, None, None, None, Fix(k=3, inliers=90), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=11)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:4], ["advanced", "turn-back", "turn-wait", "turned"])
        # C28: nothing here pinned that the wait actually WAITS -- an NPC in
        # the face needs time to move, and a mutant that zeroes STOP_WAIT_SEC
        # removes the whole point of the rung while every action above stays
        # unchanged. Pinned as a literal, not against the constant it guards.
        sleeps = [e[1] for e in rig.events if e[0] == "sleep"]
        self.assertEqual(sleeps, [2.0], "the wait must actually be STOP_WAIT_SEC (2.0s)")

    def test_a_junk_fit_at_a_later_waypoint_is_not_evidence_of_being_past(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # head-on a 9-inlier fit at 4 (junk), looks None. patch41: it is no
        # evidence of being PAST -- the claim this test exists for, unchanged
        # -- and it is no longer evidence of being SHORT either, so the stop
        # takes its step back for clearance instead of pushing forward on it.
        ch = FakeChain(5, [Fix(k=1), Fix(k=4, inliers=9), None, None, Fix(k=3, inliers=90), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=8)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turn-back", acts)
        self.assertNotIn("turned-past", acts, acts)

    def test_after_an_unverified_turn_blind_pushes_are_capped_at_two(self):
        wps = [Wp(0, 90.0)]
        # 40 walking frames after the stop: ~20 push targets, so the stop is
        # far from the six-target tail and only the unverified-turn cap can
        # explain two blind pushes. (A 12-frame chain put the whole plan in
        # the tail and the tail cap masked a mutant that removed this one.)
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0)] + [(0.0, -0.35)] * 40, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(43, [Fix(k=1)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=32.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1:3], ["turn-back", "turn-wait"])
        # patch41: the three retry pushes are gone (nothing fits, so there is
        # no evidence of being short), and there is nowhere to rewind TO --
        # the only credible fit named waypoint 1 and k is already 1 -- so the
        # stop is advanced unverified on the first pass, exactly as before.
        # The subject of the test, the blind cap AFTER that, is untouched.
        self.assertEqual(acts[3], "turned-unverified")
        self.assertNotIn("rewound_to", res["fixes"][3])
        self.assertEqual(acts[4:6], ["blind-advance"] * 2)
        self.assertEqual(acts[6], "miss", "an unverified turn allows two blind pushes, not six")

    def test_a_thin_fit_at_a_stop_is_nothing_and_never_pushes_forward(self):
        # b11 trial 13, the k=196 stop (agent_progress/closed-loop/review/
        # notes_cur_t13_1788843745.md): an NPC filled the frame and the
        # head-on fit read 13 inliers with a runner-up of 11 -- under
        # WEAK_MIN_INLIERS (15), so worthless, but neither None nor tied
        # (11 < 0.9 * 13). The back-off gates asked `fix_t is None or tied`,
        # so the step back and the wait were both skipped, and the only branch
        # left pushed forward three times along the old heading: past the NPC,
        # through a side doorway, into a service corridor the chain never
        # visits. Rule A: a fit under WEAK_MIN_INLIERS is NOTHING at a stop.
        #
        # `turn-retry` is the ONLY branch that pushes forward at a stop, so
        # its absence from the whole run is the claim "no push was spent here".
        self.assertEqual(chain_walk.WEAK_MIN_INLIERS, 15)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        thin = Fix(k=4, inliers=13, second=11)      # trial 13's own numbers
        ch = FakeChain(6, [Fix(k=1)], default=thin, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=120.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:4], ["advanced", "turn-back", "turn-wait",
                                    "turned-unverified"], acts)
        self.assertNotIn("turn-retry", acts, acts)
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        self.assertIn(335.0, turns, "the looks still run on a thin fit")
        self.assertIn(25.0, turns)

    def test_an_unverified_stop_rewinds_to_the_last_credible_k_and_re_approaches(self):
        # Rule C. Two blind pushes carry the estimate from 1 to 7; the stop at
        # 9 fits nothing head-on or either side. Stamping k = 9 there is what
        # put trial 13's estimate at the dealer's table while the character
        # stood in a corridor, and the audit's stop table says a stop taken
        # unverified arrives 1 in 14. Instead k goes BACK to 1 -- the last
        # waypoint a credible fit named -- the plan pointer rewinds with it,
        # and the loop walks the approach again. This time the fits are
        # credible, the stop verifies, and the walk arrives.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(14, [Fix(k=1)] + [None] * 11
                       + [Fix(k=4), Fix(k=7), Fix(k=9, inliers=90), Fix(k=10)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=17)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts, ["advanced", "blind-advance", "blind-advance",
                                "turn-back", "turn-wait", "turned-unverified",
                                "advanced", "advanced", "turned", "arrived"], acts)
        rew = res["fixes"][5]
        self.assertEqual(rew["k"], 1, "k is the last CREDIBLE k, not the stop")
        self.assertEqual(rew["rewound_to"], 1)
        self.assertEqual(rew["target"], 9, "the row still names the stop it refused")
        # ... and the re-approach really walked: two pushes before the stop,
        # two after the rewind, plus the one that started the walk.
        self.assertEqual(rig.count("push"), 6, "3 to the stop, 2 back to it, 1 at the end")
        self.assertTrue(res["arrived"])

    def test_the_rewind_budget_is_spent_PER_STOP_not_per_walk(self):
        # STOP_REWIND_MAX belongs to A STOP, not to the walk: a chain with two
        # turn stops that both fit nothing rewinds twice at EACH. Without the
        # per-stop reset the second stop would find the budget already spent
        # and be taken unverified on its first pass -- exactly the behaviour
        # rule C exists to remove, reappearing at every stop after the first.
        #
        # locate() answers by HINT here rather than by call order: this
        # scenario makes 40-odd calls and counting them would pin the test to
        # the loop's bookkeeping instead of to its decisions. Waypoint 4 and
        # waypoint 13 are the only two the sensor can ever see, so they are
        # the two rewind targets, one before each stop.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 8 + [(270.0, 0.0)]
                                    + [(270.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual([e for e in chain_walk.plan_indices(wps) if not e[1]],
                         [(9, False, 0.0), (18, False, 270.0)], "two turn stops")

        class ByHint(FakeChain):
            def locate(self, img, k_hint, window=3):
                if window >= chain_walk.WIDE_AHEAD:
                    self.wide_calls.append(k_hint)
                    return self.wide
                if window > chain_walk.WINDOW:
                    return None             # no look-back evidence anywhere
                self.locate_calls.append(k_hint)
                return {0: Fix(k=1), 1: Fix(k=4), 10: Fix(k=13)}.get(k_hint)

        ch = ByHint(23)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=600.0)
        self.assertEqual(
            [(f["target"], f["rewound_to"]) for f in res["fixes"] if "rewound_to" in f],
            [(9, 4), (9, 4), (18, 13), (18, 13)],
            "two rewinds at the first stop and two more at the second")
        taken = [f for f in res["fixes"]
                 if f["action"] == "turned-unverified" and "rewound_to" not in f]
        self.assertEqual([(f["target"], f["k"]) for f in taken], [(9, 9), (18, 18)],
                         "each stop is taken unverified once its own budget is spent")

    def test_a_rewind_re_approaches_on_the_ORDINARY_blind_budget(self):
        # THE FIRST DRAFT OF RULE C MANUFACTURED A LOST. It set
        # `unverified_turn = True` on the rewind, meaning to bound the blind
        # pushes the three approaches spend between them. `_blind_cap` reads
        # that flag with no regard to distance, so it held the WHOLE
        # re-approach to END_BLIND_MAX (2) -- and the flag means "k was
        # stamped on no evidence", which is the opposite of what a rewind
        # leaves behind: the estimate is back on the last thing the sensor
        # actually saw.
        #
        # Here a five-target run leads to a stop that never fits. The first
        # approach crosses it on FOUR blind advances, well inside BLIND_MAX.
        # Under the first draft the re-approach got two, bridged the shortfall
        # once with the near-stop turn-early, and the SECOND re-approach --
        # turn-early being one-shot per blockage, and every action a
        # re-approach makes being unevidenced so it never re-arms -- went
        # miss, escape, escape, escape, escape, LOST, at a k BEHIND the stop,
        # on ground the same walk had crossed twenty seconds earlier.
        self.assertEqual(chain_walk.BLIND_MAX, 6)
        self.assertEqual(chain_walk.END_BLIND_MAX, 2)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 14 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 30, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        plan = chain_walk.plan_indices(wps)
        self.assertEqual(plan[:6], [(1, True, 90.0), (4, True, 90.0),
                                    (7, True, 90.0), (10, True, 90.0),
                                    (13, True, 90.0), (15, False, 0.0)])
        # ANTI-VACUITY, and the mechanism named directly: at the corridor the
        # ONLY thing standing between BLIND_MAX and END_BLIND_MAX is the flag.
        # The chain is long deliberately -- on a short one the tail rule
        # (pi >= len(plan) - END_TAIL_TARGETS) caps both arms at
        # END_BLIND_MAX and this test would pass however the flag is set.
        self.assertEqual(chain_walk._blind_cap(4, plan, False, 1.0),
                         chain_walk.BLIND_MAX)
        self.assertEqual(chain_walk._blind_cap(4, plan, True, 1.0),
                         chain_walk.END_BLIND_MAX)

        ch = FakeChain(len(wps), [Fix(k=1)], default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=900.0)
        acts = [f["action"] for f in res["fixes"]]
        approach = ["blind-advance"] * 4 + ["turn-back", "turn-wait",
                                            "turned-unverified"]
        self.assertEqual(acts[:22], ["advanced"] + approach * 3, acts)
        self.assertEqual([f["rewound_to"] for f in res["fixes"]
                          if "rewound_to" in f], [1, 1])
        # ... and the stop is reached and taken on the third pass, rather than
        # the walk dying behind it.
        self.assertEqual(res["fixes"][21]["k"], 15)
        self.assertNotIn("rewound_to", res["fixes"][21])
        self.assertNotIn("escape:jump", acts[:22], acts)

    def test_a_relocalisation_is_the_rewind_floor_b11_trial_12(self):
        # THE INCIDENT RULE C DOES NOT CHANGE, PINNED SO NOBODY READS IT INTO
        # THE JOURNALS. b11 trial 12 (route_user_1853_t12_1788843644.jsonl
        # rows 34-37) went: WIDE relocalisation past the stop to waypoint 144
        # at 195 inliers, then straight into the k=166 stop, which fitted
        # nothing, backed off, waited, and was taken unverified. No push
        # between. The patch header once claimed rule C fixes that. It does
        # not, and it should not: the relocalisation IS the last credible
        # sighting, so `last_cred_k` equals k, the `rewound_k < k` guard holds,
        # and the stop is advanced exactly as before. The alternative -- not
        # crediting the relocalisation -- would fall back PAST a 195-inlier
        # wide fit onto whatever thin push fix came before it.
        #
        # Both relocalisation sites, because both write that credit: the one
        # inside the stop branch (rows 34-37 above) and the mid-chain one.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 4 + [(270.0, 0.0)]
                                    + [(270.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual([e for e in chain_walk.plan_indices(wps) if not e[1]],
                         [(9, False, 0.0), (14, False, 270.0)], "two turn stops")
        far = Fix(k=13, inliers=200)      # >= STRONG_MIN_INLIERS, past stop 9

        # (i) THE STOP'S OWN "maybe already past" RELOCALISATION. Credible push
        # fits to the stop at 9, nothing there, the wide search lands at 13 --
        # one short of the second stop, which then fits nothing either.
        ch = FakeChain(len(wps), [Fix(k=1), Fix(k=4), Fix(k=7)],
                       default=None, wide=far, lookback=None)
        ch.waypoints = wps
        res = Rig(ch, table_at=None).go(time_cap=900.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:7], ["advanced", "advanced", "advanced",
                                    "relocalised", "turn-back", "turn-wait",
                                    "turned-unverified"], acts)
        self.assertEqual(res["fixes"][3]["k"], 13)
        self.assertEqual(res["fixes"][6]["k"], 14, "the stop is taken, as before")
        self.assertEqual([f for f in res["fixes"] if "rewound_to" in f], [],
                         "nowhere to rewind TO: the relocalisation is the last "
                         "credible sighting and k already stands on it")

        # (ii) THE MID-CHAIN one, reached from a blind push instead.
        ch = FakeChain(len(wps), [Fix(k=1)], default=None, wide=far, lookback=None)
        ch.waypoints = wps
        res = Rig(ch, table_at=None).go(time_cap=900.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:6], ["advanced", "blind-advance", "relocalised",
                                    "turn-back", "turn-wait",
                                    "turned-unverified"], acts)
        self.assertEqual([f for f in res["fixes"] if "rewound_to" in f], [])

    def test_a_rewind_never_falls_back_past_a_stop_that_verified(self):
        # `last_cred_k` was written only by the push branch and the two wide
        # relocalisations, so a stop that VERIFIED left no mark on it. This
        # walk gets credible push fits at 1, 4 and 7, VERIFIES the stop at 9,
        # then blind-pushes to a second stop at 14 that fits nothing. Without
        # the acceptance crediting `last_cred_k = target_k` the rewind falls
        # to 7 -- back past a stop the loop had actually seen, re-walking
        # ground that was never in doubt and crossing whatever lies between.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 4 + [(270.0, 0.0)]
                                    + [(270.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual([e for e in chain_walk.plan_indices(wps) if not e[1]],
                         [(9, False, 0.0), (14, False, 270.0)], "two turn stops")
        def run(stop_inliers):
            ch = FakeChain(len(wps), [Fix(k=1), Fix(k=4), Fix(k=7),
                                      Fix(k=9, inliers=stop_inliers)],
                           default=None, lookback=None)
            ch.waypoints = wps
            res = Rig(ch, table_at=None).go(time_cap=900.0)
            return res, [f["action"] for f in res["fixes"]]

        res, acts = run(90)
        self.assertEqual(acts[:9], ["advanced", "advanced", "advanced", "turned",
                                    "blind-advance", "blind-advance",
                                    "turn-back", "turn-wait",
                                    "turned-unverified"], acts)
        self.assertEqual(res["fixes"][3]["k"], 9, "the first stop VERIFIED")
        # 7 is the live alternative, not a straw man: it is the last waypoint a
        # credible PUSH fit named, and it is what this rewind used to choose.
        self.assertEqual(res["fixes"][2]["k"], 7)
        self.assertEqual([f["rewound_to"] for f in res["fixes"]
                          if "rewound_to" in f], [9, 9],
                         "the rewind stops at the verified stop, not before it")

        # ... AND THE CREDIT IS GATED AT FIX_MIN_INLIERS, not at `verified`.
        # The head-on path verifies a stop from WEAK_MIN_INLIERS (15) up when
        # the fit names the stop's own window -- thin enough to turn on, too
        # thin to be the floor a later rewind falls back to. Same walk, same
        # verdict at the stop, a 20-inlier fit instead of 90: the stop still
        # verifies and the rewind still goes to the last CREDIBLE waypoint,
        # which is now 7 again.
        self.assertEqual(chain_walk.FIX_MIN_INLIERS, 29)
        res, acts = run(20)
        self.assertEqual(acts[:9], ["advanced", "advanced", "advanced", "turned",
                                    "blind-advance", "blind-advance",
                                    "turn-back", "turn-wait",
                                    "turned-unverified"], acts)
        self.assertEqual(res["fixes"][8]["rewound_to"], 7)
        # ... and from 7 the re-approach walks the FIRST stop again, which is
        # the honest cost of not crediting a thin one -- AND THE SHAPE THAT
        # USED TO HAND THE BUDGET BACK. The counter was a (which stop, how
        # many) pair reset whenever the target changed, so stop 9 refunded
        # stop 14's two rewinds and stop 14 refunded stop 9's, forever: this
        # exact walk spent 22 rewinds and its whole 400 s cap, TIMED OUT, with
        # STOP_REWIND_MAX = 2 in force throughout. Keyed by stop, the pool is
        # two per stop for the life of the walk.
        self.assertEqual([(f["target"], f["rewound_to"]) for f in res["fixes"]
                          if "rewound_to" in f], [(14, 7), (14, 7)], acts)
        self.assertNotEqual(res["failure"], "timed out", res["failure"])
        self.assertLess(len(res["fixes"]), 60, "the walk ends instead of "
                        "circling the two stops until the cap")

    def test_a_fit_at_exactly_WEAK_MIN_INLIERS_is_not_nothing_at_a_stop(self):
        # RULE A IS A STRICT `<`, AND THE BOUNDARY IS NOT PINNED ANYWHERE ELSE
        # -- a skeptic mutated it to `<=` and all 145 tests stayed green.
        # WEAK_MIN_INLIERS is the line between junk (6-13) and right-but-thin
        # (17-36); a fit AT it is the thinnest real answer there is, and a real
        # answer is not "nothing fits", so it buys neither the step back nor
        # the wait. It buys no retry either -- that needs FIX_MIN_INLIERS
        # (rule B) -- so the stop rewinds instead, which is the whole verdict
        # this test pins.
        #
        # 15 inliers naming waypoint 2 at a stop at 9: too far from the stop to
        # verify it (|2 - 9| > WINDOW), not past it, and too thin for the
        # looks to accept.
        self.assertEqual(chain_walk.WEAK_MIN_INLIERS, 15)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        edge = Fix(k=2, inliers=chain_walk.WEAK_MIN_INLIERS, second=0)
        ch = FakeChain(len(wps), [Fix(k=1)], default=edge, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=300.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "advanced-weak", "blind-advance",
                                    "blind-advance", "turned-unverified"], acts)
        self.assertEqual(res["fixes"][4]["rewound_to"], 1)
        self.assertNotIn("turn-back", acts, acts)
        self.assertNotIn("turn-wait", acts, acts)

    def test_a_credible_tie_at_the_stops_OWN_index_is_not_evidence_of_short(self):
        # RULE B IS A STRICT `<` TOO, AND THAT BOUNDARY WAS ALSO UNPINNED --
        # `kt <= target_k` survived all 145 tests. A retry exists for ONE
        # reading: the stop is ahead of the character. A credible fit naming
        # the stop ITSELF says the opposite, so pushing forward on it walks
        # PAST the stop -- and the only way a credible fit at the stop is not
        # a verification is a TIE, which is exactly the frame
        # STOP_TIE_FRAC exists for.
        #
        # The control is test_a_turn_stop_that_does_not_match_is_retried...
        # above: the same tie one waypoint EARLIER, which does retry.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual(chain_walk.plan_indices(wps)[1], (3, False, 0.0))

        def tied_at(k):
            f = Fix(k=k, inliers=90, second=90)
            f.second_k, f.second_dx = 8, 900.0
            return f

        def run(at):
            # head-on a credible tie at `at`, both looks blind; three passes.
            ch = FakeChain(6, [Fix(k=1), tied_at(at), None, None, tied_at(at),
                               None, None, tied_at(at), None, None],
                           default=None, lookback=None)
            ch.waypoints = wps
            rig = Rig(ch, table_at=None)
            return [f["action"] for f in rig.go(time_cap=300.0)["fixes"]]

        # THE CONTROL, in the same shape and the same test: one waypoint
        # earlier IS evidence of being short, and it does buy the retry. So an
        # empty `turn-retry` below cannot be the scenario failing to reach the
        # gate at all.
        before = run(2)
        self.assertEqual(before[:4], ["advanced", "turn-back", "turn-wait",
                                      "turn-retry"], before)
        at_it = run(3)
        self.assertEqual(at_it[:4], ["advanced", "turn-back", "turn-wait",
                                     "turned-unverified"], at_it)
        self.assertNotIn("turn-retry", at_it, at_it)

    def test_a_past_acceptance_advances_and_never_rewinds(self):
        # TURNED-PAST IS UNTOUCHED by the rewind. A thin-but-real fit at a
        # LATER waypoint is evidence the stop is behind the character, and
        # rewinding on it would walk back over ground already covered. k
        # advances to the stop and the row carries no `rewound_to`.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(5, [Fix(k=1), Fix(k=8, inliers=20), Fix(k=3), Fix(k=4)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=7)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turned-past", acts)
        self.assertEqual(res["fixes"][1]["k"], 2, "k advances to the stop")
        self.assertNotIn("rewound_to", res["fixes"][1])

    def test_a_real_fit_at_the_stop_with_a_large_offset_strafes_toward_the_scene(self):
        # Batch 5c trial 3: 26 inliers at the stop's own index, dx -297: the
        # doorway is LEFT of the loop. One strafe LEFT, stop counted as seen,
        # no retry, no blind march.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(5, [Fix(k=1), Fix(k=2, inliers=26, dx=-297.0), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=6)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned-aligned"])
        strafes = rig.strafes()
        self.assertEqual(len(strafes), 1)
        self.assertLess(strafes[0][1], 0.0, "dx < 0: the scene is left, strafe LEFT")
        self.assertNotIn("turn-retry", acts)
        self.assertEqual(res["fixes"][1]["lateral"]["dx"], -297)

    def test_a_past_acceptance_caps_blind_pushes_like_any_unverified_turn(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0)] + [(0.0, -0.35)] * 40, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(43, [Fix(k=1), Fix(k=7, inliers=20)], default=None)   # a thin fit PAST the stop's window
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turned-past")
        self.assertEqual(acts[2:4], ["blind-advance"] * 2)
        self.assertEqual(acts[4], "miss", "two blind pushes after a 'past' acceptance, not six")

    def test_a_stop_whose_frame_fits_a_later_waypoint_is_passed_not_short(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # it2: head-on a THIN but real fit (20 inliers, over WEAK_MIN 15 and
        # under FIX_MIN 29) at a LATER waypoint: evidence of being past
        ch = FakeChain(5, [Fix(k=1), Fix(k=8, inliers=20), Fix(k=3), Fix(k=4)], default=None)   # beyond the stop's window
        ch.waypoints = wps
        rig = Rig(ch, table_at=7)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turned-past")
        self.assertNotIn("turn-retry", acts)

    def test_after_the_blind_budget_a_strong_fix_far_ahead_relocalises(self):
        # One blind advance (k -> 1); from the NEXT blind iteration on the wide
        # search runs (hint k+1, window WIDE_AHEAD) and returns a STRONG fix at
        # 31: k jumps there and the walk goes on. Batch 3 trial 1 stood in the
        # portrait room at 160-188 inliers while the plan said "doorway" and
        # the old rule waited for the whole budget before looking.
        self.assertEqual(chain_walk.WIDE_AHEAD, 60)
        strong = Fix(k=31, inliers=170, second=160)   # the runner-up is the neighbour
        ch = FakeChain(60, default=None, wide=strong)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=10.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["blind-advance", "relocalised"])
        self.assertEqual([f["k"] for f in res["fixes"]][1], 31)
        self.assertEqual(ch.wide_calls[0], 2, "the wide search is hinted at k+1")
        self.assertEqual(ch.locate_calls[3], 31, "the next locate starts from the relocalised k")
        # W34 (report agent_progress/closed-loop/snoopy_sweep/report.md): the
        # blind budget must be FULL again after this relocalisation -- six
        # more blind pushes must survive before a miss, not five (which is
        # what a carried-over blind=1 from before the relocalisation would
        # allow, since the wide fix's own k=31 no longer beats k=31 and so
        # cannot mask the difference by relocalising a second time).
        self.assertEqual(acts[2:8], ["blind-advance"] * 6,
                         "blind budget not restored after a wide relocalisation")
        self.assertEqual(acts[8], "miss")

    def test_a_wide_fix_under_the_strong_count_is_not_believed(self):
        self.assertEqual(chain_walk.STRONG_MIN_INLIERS, 165)   # above the live wrong-place max of 164
        ch = FakeChain(60, default=None, wide=Fix(k=31, inliers=150, second=20))
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=8.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertNotIn("relocalised", acts)
        self.assertEqual(acts[:6], ["blind-advance"] * 6)
        self.assertTrue(ch.wide_calls, "the wide search WAS asked")

    def test_an_unverified_turn_stop_relocalises_when_a_strong_fix_is_past_it(self):
        # Reaching the stop at 3 the stop's frame does not fit (weak), but a
        # strong fix sits ahead at 9: no retry push, k jumps to 9.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0)] + [(0.0, -0.35)] * 8, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(12, [Fix(k=1), Fix(k=3, inliers=8)], default=None,
                       wide=Fix(k=9, inliers=170))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=4.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "relocalised"])
        self.assertEqual([f["k"] for f in res["fixes"]][1], 9)
        self.assertNotIn("turn-retry", acts)

    def test_the_blind_budget_is_full_again_after_a_turn_stop_relocalisation(self):
        # W33 (report agent_progress/closed-loop/snoopy_sweep/report.md): the
        # SAME blind-budget-restoration property as W34 above, but for the
        # OTHER `blind = 0` site -- the wide relocalisation that fires at an
        # unverified TURN STOP, not the one inside the main blind-push branch.
        # One blind push before the stop (blind: 0 -> 1); the stop then
        # relocalises far ahead via a strong fix. The budget must be FULL
        # again afterward: six more blind pushes survive before a miss, not
        # five (a carried-over blind=1 would allow only five).
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0)],
                                     start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        for i in range(4, 100):
            w = Wp(i, 0.0); w.lx = 0.0; w.ly = -0.35; wps.append(w)
        ch = FakeChain(100, default=None, wide=Fix(k=20, inliers=170))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=10.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["blind-advance", "relocalised"])
        self.assertEqual([f["k"] for f in res["fixes"]][1], 20)
        self.assertEqual(acts[2:8], ["blind-advance"] * 6,
                         "blind budget not restored after a relocalised turn stop")
        self.assertEqual(acts[8], "miss")

    def test_a_credible_fit_behind_the_target_with_a_large_scale_advances(self):
        self.assertEqual(chain_walk.PAST_SCALE, 1.6)
        # fix says k=0 but the scene is 2.1x larger than in frame 0: past it.
        ch = FakeChain(8, [Fix(k=0, scale=2.1, inliers=90), Fix(k=1, scale=2.4, inliers=80),
                           Fix(k=2, scale=1.2, inliers=80)], default=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=3.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts, ["advanced-past", "advanced-past", "stalled"])
        self.assertEqual([f["k"] for f in res["fixes"]], [1, 2, 2])

    def test_blind_pushes_are_capped_at_two_in_the_last_targets(self):
        self.assertEqual((chain_walk.END_TAIL_TARGETS, chain_walk.END_BLIND_MAX), (6, 2))
        # k starts at 10 of a 12-waypoint chain via credible fixes, then the
        # sensor goes blind: only two blind pushes, then misses.
        fixes = [Fix(k=i) for i in range(1, 6)]
        ch = FakeChain(12, fixes, default=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced"] * 5)
        self.assertEqual(acts[5:7], ["blind-advance"] * 2)
        self.assertEqual(acts[7], "miss", "the third blind push inside the tail is refused")

    def test_twelve_iterations_without_an_advance_end_the_walk_as_stuck(self):
        # Credible fixes that never reach the target (pushing at a door): the
        # sensor sees the room, LOST never fires, but nothing advances.
        self.assertEqual(chain_walk.NO_PROGRESS_MAX, 17)
        ch = FakeChain(30, default=Fix(k=0, scale=0.5))
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=400.0)
        self.assertFalse(res["arrived"])
        self.assertTrue(res["failure"].startswith("stuck at k=0"), res["failure"])
        self.assertEqual(len(res["fixes"]), 17)
        # Four stalls a rung: the whole ladder fires before the walk gives up.
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual([a for a in acts if a.startswith("escape:")],
                         ["escape:jump", "escape:back", "escape:left", "escape:right"])
        self.assertLess(res["seconds"], 60.0)

    def test_scattered_non_advances_never_accumulate_to_stuck(self):
        # W05 (report agent_progress/closed-loop/snoopy_sweep/report.md):
        # `since_advance` means CONSECUTIVE iterations without k rising. An
        # advance MUST reset it to zero, or the counter is really counting
        # every non-advancing iteration the walk has EVER had, cumulatively --
        # and a long, healthy walk (a ~1000-waypoint chain needs >= 333
        # iterations, CLAUDE.md §11 OPEN-15/min_iterations) is close to
        # certain to rack up NO_PROGRESS_MAX of those scattered across it.
        #
        # Fifteen cycles of (a credible fix that is READ but has not reached
        # the target yet, then a credible fix that reaches it): never two
        # non-advances in a row, so a mutant that drops the reset is the
        # ONLY way this walk ends STUCK. Sized off the LIVE constant so this
        # does not go stale if NO_PROGRESS_MAX is retuned again.
        cycles = chain_walk.NO_PROGRESS_MAX + 3
        fixes = []
        for k in range(1, cycles + 1):
            fixes.append(Fix(k=k - 1, scale=0.9, inliers=90))   # read, not reached
            fixes.append(Fix(k=k, scale=1.0, inliers=90))       # reaches k
        ch = FakeChain(cycles + 10, fixes, default=None, lookback=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=float(2 * cycles + 5))
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2 * cycles], ["stalled", "advanced"] * cycles,
                         "scattered stalls: no two non-advances in a row")
        self.assertFalse((res["failure"] or "").startswith("stuck"), res["failure"])

    def test_three_consistent_thin_fits_steer_once_by_their_median(self):
        # Batch 5e trials 13-14: five thin fits in a row, all with the scene
        # 120-320 px LEFT, refused every time. Three agreeing thin fits now
        # strafe LEFT once by their median; a lone thin fit still never does.
        self.assertEqual(chain_walk.CONSISTENT_N, 3)
        fixes = [Fix(k=1, inliers=20, dx=-150.0), Fix(k=2, inliers=18, dx=-204.0),
                 Fix(k=3, inliers=17, dx=-219.0), Fix(k=4, inliers=19, dx=-300.0)]
        ch = FakeChain(30, fixes, default=None, lookback=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=4.05)
        strafes = rig.strafes()
        self.assertEqual(len(strafes), 1, "exactly one strafe, on the third agreeing fit")
        self.assertLess(strafes[0][1], 0.0, "the scene is LEFT: strafe left")
        lat = [f["lateral"] for f in res["fixes"] if f.get("lateral")]
        self.assertEqual(lat[0]["dx"], -204.0, "the median of the first three")
        self.assertEqual(lat[0]["consistent"], 3)

    def test_four_same_side_junk_fits_steer_once_but_three_do_not(self):
        # The corridor drift cluster: 6-14-inlier fits reading the scene ever
        # further LEFT. Four agreeing steer once by their median; three never
        # do (three in a row occur in arriving trials, four never).
        self.assertEqual((chain_walk.JUNK_CONSISTENT_N, chain_walk.JUNK_MIN_INLIERS), (4, 6))
        fixes = [Fix(k=1, inliers=9, dx=-103.0), Fix(k=2, inliers=8, dx=-198.0),
                 Fix(k=3, inliers=11, dx=-241.0), Fix(k=4, inliers=7, dx=-252.0)]
        ch = FakeChain(30, fixes, default=None, lookback=None)
        rig = Rig(ch, table_at=None)
        always_turning(rig.go, time_cap=4.05)
        strafes = rig.strafes()
        self.assertEqual(len(strafes), 1)
        self.assertLess(strafes[0][1], 0.0)
        ch3 = FakeChain(30, fixes[:3], default=None, lookback=None)
        rig3 = Rig(ch3, table_at=None)
        always_turning(rig3.go, time_cap=3.05)
        self.assertEqual(rig3.strafes(), [], "three junk fits are not evidence")

    def test_stationary_runs_carry_each_frame_and_its_heading(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, 0.0), (60.0, 0.0), (30.0, 0.0), (30.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual(chain_walk.stationary_runs(wps), {4: [(2, 90.0), (3, 60.0), (4, 30.0)]})

    def test_the_pan_from_the_run_looks_along_recorded_headings_and_matches_their_own_frames(self):
        # Flag on: at the stop (run frames 2, 3, 4 at 90, 60, 30) the loop looks
        # at the run's first and middle headings and matches frame 2 at 90 and
        # frame 3 at 60 -- NOT the stop's frame 4. Flag off: the +-25 looks.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, 0.0), (60.0, 0.0), (30.0, 0.0), (30.0, -0.35), (30.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        old = chain_walk.STOP_PAN_FROM_RUN
        chain_walk.STOP_PAN_FROM_RUN = True
        try:
            # it1 push -> Fix(1); it2 stop head-on -> None; pan at 90 (frame 2) -> None;
            # pan at 60 (frame 3) -> credible with dx +80 -> verified, strafe RIGHT
            ch = FakeChain(7, [Fix(k=1), None, None, Fix(k=3, inliers=90, dx=80.0), Fix(k=5), Fix(k=6)], default=None)
            ch.waypoints = wps
            rig = Rig(ch, table_at=9)
            res = rig.go()
            acts = [f["action"] for f in res["fixes"]]
            self.assertEqual(acts[:2], ["advanced", "turned-looked"])
            turns = [round(e[1]) for e in rig.events if e[0] == "turn"]
            self.assertEqual(turns[:5], [90, 30, 90, 60, 30], "to the stop, the run's first and middle headings, back")
            self.assertEqual(ch.locate_calls[1:4], [4, 2, 3], "head-on at the stop, then each look at ITS OWN frame")
            self.assertGreater(rig.strafes()[0][1], 0.0, "dx > 0 from the run frame: strafe RIGHT, no un-yaw")
            self.assertEqual(res["fixes"][1]["lateral"]["pan_heading"], 60.0)
        finally:
            chain_walk.STOP_PAN_FROM_RUN = old

    def test_a_strong_first_pan_look_ends_the_pan(self):
        # The pan (shipped False) carries the same early exit as the
        # look-around, and without a test of its own it would be a branch
        # nothing exercises. The stop's run is frames 2, 3, 4 at 90, 60, 30;
        # the FIRST pick (frame 2 at 90) fits at 170 -- above the live gate
        # census's wrong-place maximum of 164 -- so the second pick is never
        # looked at. The shipped pan test above is the control: its first pick
        # misses and its second fits at 90, and BOTH looks run there.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, 0.0), (60.0, 0.0), (30.0, 0.0), (30.0, -0.35), (30.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        old = chain_walk.STOP_PAN_FROM_RUN
        chain_walk.STOP_PAN_FROM_RUN = True
        try:
            ch = FakeChain(7, [Fix(k=1), None, Fix(k=2, inliers=170, dx=80.0),
                               Fix(k=5), Fix(k=6)], default=None)
            ch.waypoints = wps
            rig = Rig(ch, table_at=5)
            res = rig.go()
            self.assertEqual([f["action"] for f in res["fixes"]][:2],
                             ["advanced", "turned-looked"])
            self.assertEqual([round(e[1]) for e in rig.events if e[0] == "turn"],
                             [90, 30, 90, 30],
                             "to the stop, the run's FIRST heading, back")
            self.assertEqual(ch.locate_calls[1:3], [4, 2],
                             "head-on at the stop, then ONE run frame")
            self.assertEqual(res["fixes"][1]["lateral"]["pan_heading"], 90.0)
        finally:
            chain_walk.STOP_PAN_FROM_RUN = old

    def test_the_pan_is_off_by_default_even_when_the_stop_has_a_run(self):
        # The control for the flag: the SAME stop with a stationary run, flag
        # off (as shipped), looks at +-STOP_LOOK_DEG and never asks a run
        # frame. A mutant that pans regardless of the flag passes every other
        # test because their chains have no runs to pan from.
        self.assertFalse(chain_walk.STOP_PAN_FROM_RUN)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, 0.0), (60.0, 0.0), (30.0, 0.0), (30.0, -0.35), (30.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(7, [Fix(k=1), None, None, None, Fix(k=5), Fix(k=6)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=9)
        rig.go()
        turns = [round(e[1]) for e in rig.events if e[0] == "turn"]
        looks = [round(30 + d) for d in chain_walk.STOP_LOOK_DEG]
        self.assertEqual(turns[2:4], looks, "the +-25 looks, not the run's headings: %r" % turns)
        # head-on at the stop, then both looks matched against the STOP's own
        # frame 4 (the pan would ask frames 2 and 3 here; a later look-back
        # legitimately asks 3, so only the stop's three calls are pinned)
        self.assertEqual(ch.locate_calls[1:4], [4, 4, 4], ch.locate_calls)

    def test_thin_fits_that_disagree_on_side_do_not_steer(self):
        fixes = [Fix(k=1, inliers=20, dx=-150.0), Fix(k=2, inliers=18, dx=+204.0),
                 Fix(k=3, inliers=17, dx=-219.0), Fix(k=4, inliers=19, dx=-300.0)]
        ch = FakeChain(30, fixes, default=None)
        rig = Rig(ch, table_at=None)
        always_turning(rig.go, time_cap=4.05)
        self.assertEqual(rig.strafes(), [])

    def test_a_credible_fit_near_the_stop_with_a_large_offset_also_aligns(self):
        # Trial 13: a 30-inlier fit at 41 (the stop is 39, within WINDOW) with
        # dx -128 was 'turned' with the offset thrown away.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(6, [Fix(k=1), Fix(k=4, inliers=30, dx=-128.0), Fix(k=3), Fix(k=4), Fix(k=5)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=7)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turned-aligned")
        self.assertLess(rig.strafes()[0][1], 0.0)

    def test_the_plan_pointer_rewinds_after_a_regression(self):
        # Audit: k regressed to 4 but the pointer stayed at the target past 6,
        # so reached() was impossible from then on. After the regression the
        # next target must be the first plan entry past the NEW k.
        fixes = [Fix(k=1), Fix(k=2), Fix(k=3), Fix(k=4), Fix(k=5), Fix(k=6),
                 None, Fix(k=4, inliers=80), Fix(k=5), Fix(k=6), Fix(k=7)]
        ch = FakeChain(30, fixes, default=None)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=10.05)
        rows = res["fixes"]
        self.assertEqual(rows[6]["action"], "regressed")
        self.assertEqual(rows[7]["target"], 5, "the target after regressing to 4 is 5, not the old 7")
        self.assertEqual([r["action"] for r in rows[7:10]], ["advanced"] * 3)

    def test_a_thin_advance_goes_no_further_than_the_fit_names(self):
        # Audit: a 20-inlier fit AT k (scale 0.8) used to advance k to the target.
        # A thin fit that always names 5: advances one TARGET per iteration
        # until k reaches 5, never beyond what the fit names.
        ch = FakeChain(30, default=Fix(k=5, inliers=20))
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=7.05)
        acts = [f["action"] for f in res["fixes"]]
        ks = [f["k"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced-weak"] * 5)
        self.assertEqual(ks[:5], [1, 2, 3, 4, 5])
        self.assertEqual(acts[5], "blind-advance", "at 5 the fit names nothing ahead: blindness")
        # A thin fit that names the CURRENT waypoint (scale 0.8, not even there)
        # is blindness from the first push (audit: it used to advance three).
        ch2 = FakeChain(30, default=Fix(k=0, inliers=20, scale=0.8))
        rig2 = Rig(ch2, table_at=None)
        res2 = always_turning(rig2.go, time_cap=3.05)
        self.assertEqual([f["action"] for f in res2["fixes"]][:3], ["blind-advance"] * 3)

    def test_a_thin_advance_stops_at_the_waypoint_the_fit_names_not_the_target(self):
        # Push targets three frames apart (stick 0.35 at 0.25 s = 0.0875 u a
        # frame against 0.18 u a push): targets 1, 4, 7... From k=1 the target
        # is 4; a thin fit naming 2 advances to 2, NOT to 4. (The mutant that
        # jumps to the target survived a test whose fit always named the
        # target's own waypoint.)
        wps = [Wp(0, 90.0)]
        for i in range(1, 12):
            w = Wp(i, 90.0); w.lx = 0.0; w.ly = -0.35; wps.append(w)
        plan = chain_walk.plan_indices(wps)
        self.assertEqual([i for i, p, _ in plan if p][:3], [1, 4, 7])
        ch = FakeChain(12, [Fix(k=1), Fix(k=2, inliers=20)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=2.05)
        rows = res["fixes"]
        self.assertEqual((rows[0]["action"], rows[0]["k"]), ("advanced", 1))
        self.assertEqual((rows[1]["action"], rows[1]["k"], rows[1]["target"]), ("advanced-weak", 2, 4))

    def test_a_well_aligned_thin_fit_at_the_stop_verifies_without_a_strafe(self):
        # Audit: a 20-inlier fit at the stop with dx 10 used to cost three
        # retry pushes while dx 300 verified. Both verify; only the large one strafes.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(5, [Fix(k=1), Fix(k=2, inliers=20, dx=10.0), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=6)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned"])
        self.assertEqual(rig.strafes(), [])
        self.assertNotIn("turn-retry", acts)

    def test_a_totally_occluded_stop_waits_once_before_retrying(self):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # it2: head-on None, looks None,None -> WAIT; it3: head-on credible -> turned
        ch = FakeChain(5, [Fix(k=1), None, None, None, Fix(k=2, inliers=90), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=8)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:3], ["advanced", "turn-back", "turned"])
        self.assertTrue(any(e[0] == "back" for e in rig.events), "one step back for clearance came first")
        self.assertEqual(rig.count("push"), 3, "one before the stop, none during the back step, two after")

    def test_no_lateral_correction_in_the_iteration_after_an_escape_sidestep(self):
        # Audit: the aligner undid the escape sidestep on the very next iteration.
        fixes = [Fix(k=0, scale=0.5)] * 4 + [Fix(k=0, scale=0.5, dx=300.0)] + [Fix(k=0, scale=0.5)] * 6
        ch = FakeChain(30, fixes, default=Fix(k=0, scale=0.5))
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[3], "escape:jump")
        # W28/W32 (report agent_progress/closed-loop/snoopy_sweep/report.md):
        # the ORIGINAL version of this test scripted the dx=300 fix onto the
        # escape iteration ITSELF (row 11 below), where the OTHER guard
        # (`not escaped`, W27, already caught) suppresses it regardless of
        # `escaped_prev` -- so it asserted row 12, whose own fix carries
        # dx=0.0, comfortably inside tolerance with or without the guard. A
        # mutant that deletes `escaped_prev` entirely still passed. Fixed:
        # four baseline stalls (escape lands on row 3), THEN the dx=300 fix,
        # so it lands on the row RIGHT AFTER the escape -- exactly what the
        # guard exists to block.
        fixes2 = [Fix(k=0, scale=0.5)] * 4 + [Fix(k=0, scale=0.5, dx=300.0),
                                              Fix(k=0, scale=0.5, dx=300.0)]
        ch2 = FakeChain(30, fixes2, default=Fix(k=0, scale=0.5))
        rig2 = Rig(ch2, table_at=None)
        res2 = always_turning(rig2.go, time_cap=6.05)
        acts2 = [f["action"] for f in res2["fixes"]]
        self.assertEqual(acts2[3], "escape:jump", "the escape lands on row 3, not row 11")
        self.assertIsNone(
            res2["fixes"][4]["lateral"],
            "no lateral undo in the iteration right after the escape sidestep "
            "-- row 4's own fix carries dx=300, so this is NOT vacuous")
        # THE CONTROL: the identical dx one iteration later, once escaped_prev
        # has gone back to False, DOES produce a strafe -- proving the guard
        # above is doing real work and not just describing a fixture with no
        # steerable dx at all.
        self.assertIsNotNone(
            res2["fixes"][5]["lateral"],
            "control: the same dx with escaped_prev now False must strafe")

    def _stop_with_a_two_frame_run(self):
        """spawn, one walking frame east, a TWO-frame stationary run turning to
        north (waypoints 2 and 3, so a runner-up can be INSIDE it), then two
        walking frames. Plan: push 1, turn-only 3, push 4, push 5."""
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        return wps

    def test_the_stop_span_is_the_whole_stationary_run_holes_and_all(self):
        # stationary_runs DROPS heading-None frames, so its list for this run
        # is [2] alone; the span must still be 2..3 or a runner-up at the
        # abstaining frame reads as a different place.
        wps = self._stop_with_a_two_frame_run()
        wps[3].heading = None
        self.assertEqual(chain_walk.stationary_runs(wps), {3: [(2, 0.0)]})
        self.assertEqual(chain_walk.stop_spans(wps), {3: 2})

    def test_a_winner_and_runner_up_both_at_the_stop_are_not_a_tie(self):
        # THE STRUCTURAL FALSE POSITIVE. A turn-only target collapses a run of
        # near-duplicate frames, so the runner-up there is at 0.92-0.96 of the
        # winner BY CONSTRUCTION -- measured on all six stops of the four
        # fastest arrivals ever recorded, which verified head-on in 0.1-4.2 s
        # (agent_progress/closed-loop/stop_tie/replay_stops.json). 95/100 =
        # 0.95, over the 0.9 ratio, but BOTH candidates are inside this stop's
        # own span (winner 3, runner-up 2, span 2..3): one spot 0.25 s apart,
        # so verified head-on with no look-around at all. Note the test is
        # BOTH indices, not the runner-up's alone -- the same runner-up with a
        # winner PAST the span is the trial-6 tie two tests below.
        #
        # BOTH dx values are run. The replayed both-inside pairs disagree by
        # 0.0-0.6 px, which is the realistic arm; the second arm disagrees by
        # 410 px so that `apart` is TRUE and the span is the only thing left
        # refusing the tie. Without it the test passed with the span lookup
        # deleted (`run_lo = target_k`), which is the wiring it exists to pin.
        for second_dx in (10.0, -400.0):
            with self.subTest(second_dx=second_dx):
                wps = self._stop_with_a_two_frame_run()
                ch = FakeChain(6, [Fix(k=1),
                                   Fix(k=3, inliers=100, second=95, second_k=2,
                                       second_dx=second_dx, dx=10.0),
                                   Fix(k=4), Fix(k=5)], default=None)
                ch.waypoints = wps
                rig = Rig(ch, table_at=4)
                res = rig.go()
                acts = [f["action"] for f in res["fixes"]]
                self.assertEqual(acts[:2], ["advanced", "turned"], acts)
                self.assertNotIn("turned-looked", acts)
                self.assertEqual(
                    [round(e[1]) for e in rig.events if e[0] == "turn"],
                    [90, 0],
                    "a look-around would add three turns: %r" % rig.events)

    def test_a_runner_up_past_the_run_that_agrees_on_dx_is_not_a_tie_either(self):
        # The runner-up one frame PAST the run (waypoint 4, outside the span)
        # but reading nearly the same offset. Two places by index, one place by
        # dx: 22 such pairs were replayed off arriving trials and their
        # |second_dx - dx| runs 0..95 px. 50 is inside that population, so it
        # is not a different place, and the dx half is what says so.
        wps = self._stop_with_a_two_frame_run()
        ch = FakeChain(6, [Fix(k=1),
                           Fix(k=3, inliers=100, second=95, second_k=4,
                               second_dx=60.0, dx=10.0),
                           Fix(k=4), Fix(k=5)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=4)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned"], acts)
        self.assertEqual([round(e[1]) for e in rig.events if e[0] == "turn"],
                         [90, 0], rig.events)

    def test_a_tied_fit_at_a_stop_is_ambiguity_not_verification(self):
        # UPDATED 2026-09-08 (patch37). This test used to script the batch 5e
        # trial 6 numbers alone -- 33 inliers against a runner-up of 33 -- and
        # a close count is no longer a tie on its own, because it is what a
        # stationary run produces at EVERY stop. What it pins now is one of the
        # two directions separation comes in: the WINNER is the stop (waypoint
        # 2, its own one-frame span) and the near-tied runner-up is a DIFFERENT
        # PLACE, outside the span and 426 px away from the winner's offset.
        # The other direction -- winner past the span, runner-up at the stop --
        # is the real trial-6 frame, and it has its own test below.
        self.assertEqual(chain_walk.STOP_TIE_FRAC, 0.9)
        self.assertEqual(chain_walk.STOP_TIE_DX_PX, 120.0)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # it2: head-on a TIED 33/33 fit at the stop -> not verified; looks None -> wait
        ch = FakeChain(5, [Fix(k=1),
                           Fix(k=2, inliers=33, second=33, dx=40.0,
                               second_k=4, second_dx=-386.0),
                           None, None,
                           Fix(k=2, inliers=90, second=30), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=9)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:3], ["advanced", "turn-back", "turned"])
        # ... and the look-around DID run: a tie is what sends it there.
        self.assertEqual([round(e[1]) for e in rig.events if e[0] == "turn"][:5],
                         [90, 0, 335, 25, 0], rig.events)

    def test_a_strong_first_look_ends_the_look_around(self):
        # +-STOP_LOOK_DEG used to sample BOTH directions however decisive the
        # first was: 2 turns, 2 captures, 2 locates and a turn back, every
        # time, at +20.9 s a trial (rule_costs/notes.md). A look at 170
        # inliers is above the live gate census's wrong-place MAXIMUM of 164,
        # so the other direction cannot change the verdict.
        self.assertEqual(chain_walk.STRONG_MIN_INLIERS, 165)
        wps = self._stop_with_a_two_frame_run()
        # it2: head-on None; the -25 look fits at 170 -> stop looking.
        ch = FakeChain(6, [Fix(k=1), None, Fix(k=3, inliers=170, dx=0.0),
                           Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=5)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned-looked"], acts)
        self.assertEqual([round(e[1]) for e in rig.events if e[0] == "turn"],
                         [90, 0, 335, 0],
                         "to the stop, ONE look, back -- not both looks")
        self.assertEqual(res["fixes"][1]["lateral"]["deg"], -25.0)
        self.assertEqual(rig.captures, 5, "one capture for the single look")

    def test_a_weak_first_look_still_samples_the_other_side(self):
        # THE CONTROL for the test above: at 90 inliers the first look is
        # credible but not strong, so the +25 look still runs and wins it.
        wps = self._stop_with_a_two_frame_run()
        ch = FakeChain(6, [Fix(k=1), None, Fix(k=3, inliers=90, dx=0.0),
                           Fix(k=3, inliers=100, dx=0.0), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=6)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned-looked"], acts)
        self.assertEqual([round(e[1]) for e in rig.events if e[0] == "turn"],
                         [90, 0, 335, 25, 0], "both looks, then back")
        self.assertEqual(res["fixes"][1]["lateral"]["deg"], 25.0,
                         "the SECOND look was the better one and must be used")

    def test_the_winner_past_the_run_with_the_stop_as_runner_up_is_a_tie(self):
        # THE MOTIVATING FRAME, IN THE SHAPE IT ACTUALLY HAS. Batch 5e trial 6,
        # stop 129: the WINNER is waypoint 132 -- PAST the stop's own span
        # 116..129 -- at 35 inliers and dx -386, and the near-tied runner-up
        # (33) is waypoint 128, the stop's OWN frame, at dx -201. Scaled to
        # this rig: span 2..3, winner 4, runner-up 2, the same 0.943 ratio and
        # the same 185.4 px disagreement.
        #
        # A separation test that asked only about the RUNNER-UP called this
        # "not a tie" -- the runner-up was inside the run, so it looked like a
        # near-duplicate -- verified the stop, and strafed on the winner's
        # -386 px: it acted on the candidate PAST the stop, which is the
        # failure the constant was written for (the loop finished short of the
        # doorway). Both indices are tested for that reason. Here the pair is
        # two places, so it is a tie: nothing verified, NOTHING STRAFED, and
        # the look-around runs. The two tests above are the controls -- same
        # rig, pairs that are ONE place, no look-around.
        #
        # Honest limit, kept where it will be read: the ARRIVING batch 5e trial
        # 5 reads this same stop at 34/31 with the same runner-up and the same
        # 185 px, so this rule cannot tell the failure from the arrival. It
        # does not try to. It sends both to the look-around instead of guessing
        # that the winner is right.
        self.assertEqual(chain_walk.STOP_TIE_FRAC, 0.9)
        self.assertEqual(chain_walk.STOP_TIE_DX_PX, 120.0)
        # BOTH trials are run, and both must tie. Trial 5's numbers are here to
        # pin the COST as behaviour rather than as a sentence: a later change
        # that quietly un-ties this shape to save the look-around fails here
        # too, and has to argue with the frame instead of with the clock.
        for who, inl, sec in (("t6, short of the doorway", 35, 33),
                              ("t5, ARRIVED on the same reading", 34, 31)):
            with self.subTest(trial=who):
                wps = self._stop_with_a_two_frame_run()
                ch = FakeChain(6, [Fix(k=1),
                                   Fix(k=4, inliers=inl, second=sec, second_k=2,
                                       second_dx=-201.0, dx=-386.4),
                                   None, None,
                                   Fix(k=3, inliers=90, second=30), Fix(k=4),
                                   Fix(k=5)], default=None)
                ch.waypoints = wps
                rig = Rig(ch, table_at=12)
                res = rig.go()
                acts = [f["action"] for f in res["fixes"]]
                self.assertEqual(acts[:3],
                                 ["advanced", "turn-back", "turned"], acts)
                self.assertEqual(
                    [round(e[1]) for e in rig.events if e[0] == "turn"][:5],
                    [90, 0, 335, 25, 0], rig.events)
                self.assertEqual(
                    rig.strafes(), [],
                    "the offset of a candidate PAST the stop must not be "
                    "acted on: %r" % (rig.strafes(),))

    def test_a_decisive_win_is_not_a_tie_however_far_the_runner_up_sits(self):
        # THE RATIO IS LOAD-BEARING TOO, and until 2026-09-08 nothing here said
        # so: a skeptic deleted the count clause and all 178 tests stayed
        # green. Separation alone must never make a tie. This fit wins 190 to
        # 20 -- a ratio of 0.105, nowhere near STOP_TIE_FRAC -- while its weak
        # runner-up happens to sit outside the stop's span AND to disagree by
        # 510 px, so BOTH new conditions are true and only the count says the
        # win is decisive. Without the clause a head-on win goes through the
        # whole back-step / wait / look-around ladder: the ~20 s a stop this
        # rule exists to stop paying, on the clearest fit there is.
        self.assertEqual(chain_walk.STOP_TIE_FRAC, 0.9)
        wps = self._stop_with_a_two_frame_run()
        ch = FakeChain(6, [Fix(k=1),
                           Fix(k=3, inliers=190, second=20, second_k=5,
                               second_dx=500.0, dx=-10.0),
                           Fix(k=4), Fix(k=5)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=8)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned"], acts)
        self.assertNotIn("turned-looked", acts)
        self.assertNotIn("turn-back", acts)
        self.assertEqual([round(e[1]) for e in rig.events if e[0] == "turn"],
                         [90, 0],
                         "a tie would add the look-around's three turns: %r"
                         % rig.events)


    def test_the_escape_ladder_cycles_so_a_jump_comes_round_again(self):
        rig = Rig(FakeChain(30, default=Fix(k=0, scale=0.5)), table_at=None)
        res = without_stuck(lambda **kw: always_turning(rig.go, **kw), time_cap=60.0)
        acts = [f["action"] for f in res["fixes"] if f["action"].startswith("escape")]
        self.assertEqual(acts[:5], ["escape:jump", "escape:back", "escape:left", "escape:right", "escape:jump"])

    def test_blind_after_a_wall_scale_fit_with_a_stop_ahead_gets_one_push(self):
        self.assertEqual((chain_walk.WALL_SCALE, chain_walk.NEAR_STOP_TARGETS), (2.5, 3))
        # walking frames 1..15 (push targets 1, 4, 7, 10, 13), a stop at 16,
        # walking after. From k=4 the stop is four targets away (no cap), from
        # k=7 it is within three (cap 1).
        wps = [Wp(0, 0.0)]
        for i, (h, ly) in enumerate([(0.0, -0.35)] * 15 + [(90.0, 0.0)] + [(90.0, -0.35)] * 30, start=1):   # long tail: the six-target tail cap stays clear
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        plan = chain_walk.plan_indices(wps)
        self.assertEqual([i for i, p, _ in plan][:6], [1, 4, 7, 10, 13, 16])
        # a credible fit at 3 with scale 2.9 (the wall a push away), then blind
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=2.9, inliers=90)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=8.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "advanced"])
        self.assertEqual(acts[2], "blind-advance", "toward 7 the stop is still four targets off: allowed")
        self.assertNotEqual(acts[3], "blind-advance", "toward 10 the stop is within three: one blind push was the budget")
        # the same without the wall scale: the full blind budget applies
        ch2 = FakeChain(47, [Fix(k=1), Fix(k=4, scale=1.2, inliers=90)], default=None)
        ch2.waypoints = wps
        rig2 = Rig(ch2, table_at=None)
        res2 = always_turning(rig2.go, time_cap=8.05)
        acts2 = [f["action"] for f in res2["fixes"]]
        self.assertEqual(acts2[2:4], ["blind-advance", "blind-advance"])

    def test_a_miss_looks_back_and_k_may_regress(self):
        # k is at 6 (advanced legitimately), then the forward window finds
        # nothing; the look-back from k-2 fits at 4 with 80 inliers -> k = 4.
        fixes = [Fix(k=1), Fix(k=2), Fix(k=3), Fix(k=4), Fix(k=5), Fix(k=6),
                 None, Fix(k=4, inliers=80)]
        ch = FakeChain(12, fixes)
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=7.05)
        ks = [f["k"] for f in res["fixes"]]
        self.assertEqual(ks[:7], [1, 2, 3, 4, 5, 6, 4])
        self.assertEqual([f["action"] for f in res["fixes"]][6], "regressed")
        self.assertEqual(rig.chain.locate_calls[6:8], [6, 4],
                         "the look-back is asked from k - LOOKBACK")
        self.assertEqual(rig.count("jump"), 0)

    def test_a_fix_that_has_not_reached_does_not_advance_k(self):
        rig = Rig(FakeChain(6, default=Fix(k=1, scale=0.4)), table_at=None)
        res = always_turning(rig.go, time_cap=3.05)      # exactly three 1.0s iterations
        self.assertEqual([f["k"] for f in res["fixes"]], [0, 0, 0])
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["stalled", "stalled", "stalled"])

    def test_scale_at_one_reaches_the_target(self):
        # reached(): fix.k == k and scale >= 1.0 means we are AT that waypoint.
        rig = Rig(FakeChain(6, [Fix(k=1, scale=1.0)]), table_at=3)
        res = rig.go()
        self.assertEqual(res["fixes"][0]["k"], 1)
        self.assertEqual(res["fixes"][0]["action"], "advanced")
        self.assertEqual(res["fixes"][0]["target"], 1)


class TurnEarlyWhenBlindNearAStop(unittest.TestCase):
    """(m) blind, budget spent, a turn stop within reach: turn, do not escape.

    2026-09-07 22:00-22:10. Three trials in a row, both arms of an A/B, walked
    into an NPC standing at chain waypoint ~112-114 and were lost there. The
    drive stopped at 114 and panned 1.3 -> 303.3 deg on the spot, which compiles
    to pushes at ...112, 114 and then ONE turn-only stop at 129 -- so she stood
    ON the turn point. The estimate stalled at 112, the near-a-stop blind budget
    is one push (_blind_cap), and the rest of the walk went into misses and
    escape rungs pushing north into her. It never reached the stop, so it never
    turned left. The user: "you walked too close to her and should have turned
    left. It's okay that you got super close, you just didn't turn left enough."
    """

    # 15 walking frames compile to push targets 1, 4, 7, 10, 13 (the recorded
    # stick covers 0.0875 u a frame against a 0.180 u push), so a stop at 16 is
    # the sixth plan entry. Same shape as the wall-scale blind-cap test.
    @staticmethod
    def _wps(walk_frames, stop_heading, tail_frames, walk_heading=0.0):
        wps = [Wp(0, walk_heading)]
        rows = ([(walk_heading, -0.35)] * walk_frames
                + [(stop_heading, 0.0)]
                + [(stop_heading, -0.35)] * tail_frames)
        for i, (h, ly) in enumerate(rows, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        return wps

    # TWO stops, nine walking frames apart, so the plan reads
    # ... (13, True), (16, False), (17, True), (20, True), (23, True),
    # (26, False) ...: the second stop comes back into range two targets after
    # the first is left behind, which is what a per-BLOCKAGE mark has to get
    # right in both directions.
    @staticmethod
    def _two_stops():
        wps = [Wp(0, 0.0)]
        rows = ([(0.0, -0.35)] * 15 + [(90.0, 0.0)]
                + [(90.0, -0.35)] * 9 + [(180.0, 0.0)]
                + [(180.0, -0.35)] * 20)
        for i, (h, ly) in enumerate(rows, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        return wps

    def test_blind_near_a_turn_stop_turns_early_before_any_escape_rung(self):
        self.assertEqual((chain_walk.WALL_SCALE, chain_walk.NEAR_STOP_TARGETS),
                         (2.5, 3))
        wps = self._wps(15, 90.0, 30)
        plan = chain_walk.plan_indices(wps)
        self.assertEqual([(i, p) for i, p, _ in plan][:6],
                         [(1, True), (4, True), (7, True), (10, True),
                          (13, True), (16, False)])
        # A credible fit at 4 with the wall a push away (scale 2.9), then the
        # sensor goes blind: the budget near the stop is ONE push, and the
        # push after it is the one that used to walk into her.
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=2.9, inliers=90),
                            None, None, Fix(k=16, inliers=90)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=3.55)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "advanced", "blind-advance",
                                    "turn-early", "turned"])
        # The turn happened, to the STOP's heading, and no rung was spent.
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 90.0],
                         "one turn along the walk, then the stop's own heading")
        self.assertEqual(rig.count("jump"), 0)
        self.assertEqual(rig.count("back"), 0)
        self.assertEqual([a for a in acts if a.startswith("escape:")], [],
                         "a turn moves nothing: it comes before every rung")
        # The turn-early iteration itself pushes nothing extra and does not
        # claim to have moved: k is unchanged from the blind advance before it.
        early = next(f for f in res["fixes"] if f["action"] == "turn-early")
        self.assertEqual(early["k"], 7)
        self.assertEqual(early["target"], 10)
        self.assertEqual(res["fixes"][4]["target"], 16,
                         "the next target IS the stop")

    def test_a_stop_further_than_NEAR_STOP_TARGETS_ahead_is_not_turned_to(self):
        # The control. Same blindness, but the stop is beyond the window the
        # rule is allowed to look through, so the ladder fires exactly as it did
        # before the rule existed.
        wps = self._wps(40, 90.0, 5)
        plan = chain_walk.plan_indices(wps)
        stop_j = next(j for j, (_, p, _) in enumerate(plan) if not p)
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=2.9, inliers=90)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = without_stuck(rig.go, time_cap=12.05)
        acts = [f["action"] for f in res["fixes"]]
        # Six blind advances (the full budget: no stop is within three targets
        # of any of them), then misses, then the ladder.
        self.assertEqual(acts.count("blind-advance"), chain_walk.BLIND_MAX)
        first_escape = next(i for i, a in enumerate(acts) if a.startswith("escape:"))
        self.assertEqual(acts[first_escape], "escape:jump")
        self.assertNotIn("turn-early", acts)
        # ... and it really was out of range: the pointer when the budget ran
        # out sat more than NEAR_STOP_TARGETS entries before the stop.
        pi_when_spent = 2 + chain_walk.BLIND_MAX          # targets 1, 4, then six
        self.assertGreater(stop_j - pi_when_spent, chain_walk.NEAR_STOP_TARGETS)

    def test_one_early_turn_per_blockage_then_the_ladder(self):
        # Two stops. The first is turned to early, fits nothing, and is finally
        # accepted UNVERIFIED -- which advances k on no evidence at all. The
        # loop is still blind and the second stop is now within range: without
        # the once-per-blockage mark it would turn early again, and again, all
        # the way down the plan while standing in the same spot. It gets the
        # ladder instead.
        wps = self._two_stops()
        plan = chain_walk.plan_indices(wps)
        self.assertEqual([(i, p) for i, p, _ in plan][:10],
                         [(1, True), (4, True), (7, True), (10, True),
                          (13, True), (16, False), (17, True), (20, True),
                          (23, True), (26, False)])
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=2.9, inliers=90)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = without_stuck(rig.go, time_cap=40.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("turn-early"), 1,
                         f"one early turn per blockage, not {acts}")
        self.assertIn("turned-unverified", acts)
        # An early stop takes NO retry pushes along the old heading (they
        # walked into the NPC three more times live): back, wait, accept.
        seg = acts[acts.index("turn-early"):acts.index("turned-unverified")]
        self.assertNotIn("turn-retry", seg, seg)
        self.assertEqual(seg, ["turn-early", "turn-back", "turn-wait"], seg)
        after = acts[acts.index("turned-unverified"):]
        self.assertIn("escape:jump", after,
                      "the ladder takes over once the early turn is spent")
        self.assertNotIn("turn-early", after)

    def test_the_blind_budget_is_spent_first_and_the_rule_waits(self):
        # The same chain as the first test with an ordinary scale (1.2): the
        # near-a-stop cap does not apply, so the loop still has blind pushes to
        # make and MAKES them. The rule fires when the budget is spent, never
        # instead of it.
        wps = self._wps(15, 90.0, 30)
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=1.2, inliers=90)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        # The cap stops the walk after the fourth iteration (0.1 + 1.1 + 0.5 x 3
        # on the Rig's clock) so the list below is the whole record: at the
        # iteration where the rule COULD fire it blind-advances instead.
        res = rig.go(time_cap=2.15)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts, ["advanced", "advanced", "blind-advance",
                                "blind-advance"])
        self.assertNotIn("turn-early", acts)
        # The stop WAS within range on that last iteration -- the rule waited
        # for the budget, it was not simply out of reach.
        plan = chain_walk.plan_indices(wps)
        self.assertEqual(chain_walk._near_stop(3, plan), 5)

    def test_evidenced_progress_re_arms_the_early_turn(self):
        """The mark is spent per BLOCKAGE, and only the sensor can clear it.

        The first stop here is turned to early and then VERIFIED against its
        own frame on a strong fit (200 inliers) -- the sensor SAW the walk
        arrive -- so the next blockage gets its own early turn. A build that
        never re-arms fires the rule ONCE in a walk and has it off for the rest
        of the chain with nothing in the journal saying so, and that build
        passed every other test in this file: deleting the re-arm left 115/115
        green (skeptic-correctness mutant (f), 2026-09-07). This is the test
        that fails instead.
        """
        wps = self._two_stops()
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=2.9, inliers=90),
                            None, None, Fix(k=16, inliers=200)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=40.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:7], ["advanced", "advanced", "blind-advance",
                                    "turn-early", "turned", "blind-advance",
                                    "turn-early"])
        self.assertEqual(acts.count("turn-early"), 2,
                         f"the second blockage gets its own early turn: {acts}")
        # What re-armed it is EVIDENCE: a stop verified against a real fit, not
        # one of the two actions that advance k on nothing.
        self.assertEqual(res["fixes"][4]["action"], "turned")
        self.assertEqual(res["fixes"][4]["fix"]["inliers"], 200)
        # ... and the second early turn goes to the SECOND stop, not the first
        # one again: the iteration after it targets plan entry (26, False).
        self.assertEqual(res["fixes"][7]["target"], 26)

    def test_a_turn_that_advanced_k_on_nothing_does_not_re_arm(self):
        """The other member of UNEVIDENCED_ACTIONS, which nothing else covers.

        `turned-unverified` is the test above. This is `turned-past`: the stop
        is accepted because a THIN fit (20 inliers) named a waypoint outside
        the stop's window, and k jumps to the stop. That is a claim about the
        plan, not a sighting of the character -- so it must not re-arm the
        early turn, or one blockage turns early at stop after stop while
        standing in the same place.
        """
        self.assertEqual(chain_walk.UNEVIDENCED_ACTIONS,
                         ("turned-unverified", "turned-past"))
        wps = self._two_stops()
        plan = chain_walk.plan_indices(wps)
        ch = FakeChain(47, [Fix(k=1), Fix(k=4, scale=2.9, inliers=90),
                            None, None, Fix(k=21, inliers=20)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=40.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:7], ["advanced", "advanced", "blind-advance",
                                    "turn-early", "turned-past",
                                    "blind-advance", "miss"])
        self.assertEqual(acts.count("turn-early"), 1,
                         f"a turn that fitted nothing re-armed the rule: {acts}")
        # THE ANTI-VACUITY, and it is the whole test: on that "miss" iteration
        # the budget was spent AND a turn-only stop was two entries ahead, so
        # the rule was WITHHELD, not simply out of reach. It is also the second
        # guard on `and not turned_early` -- dropping it turns this miss into a
        # turn-early.
        self.assertEqual(res["fixes"][6]["target"], 20)
        self.assertEqual(chain_walk._near_stop(7, plan), 9)
        self.assertEqual(plan[9][:2], (26, False))


class Escapes(unittest.TestCase):
    """(c) and (d): stalls and misses each escape, and the escapes alternate."""

    def test_stalls_escape_and_alternate_jump_left_right(self):
        self.assertEqual(chain_walk.STALL_MAX, 4)
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)), table_at=14)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual([i for i, a in enumerate(acts, 1)
                          if a.startswith("escape")], [4, 8, 12])
        self.assertEqual([acts[3], acts[7], acts[11]],
                         ["escape:jump", "escape:back", "escape:left"])
        self.assertEqual(acts[4:7], ["stalled"] * 3, "the counter must reset")
        # C21: nothing pinned the escape's BACK rung's own duration -- a
        # mutant that doubles BACK_SEC changes how far the character backs
        # off a wall and nothing here notices. Literal, not the constant.
        backs = [e for e in rig.events if e[0] == "back"]
        self.assertEqual(len(backs), 1)
        self.assertEqual(backs[0][2], 0.5, "the back rung must be BACK_SEC (0.5s)")
        # LEFT is negative lx, RIGHT positive — the same axis walk_leg drives.
        sides = [e[1] for e in rig.strafes()]
        self.assertEqual(len(sides), 1, "jump, back, then the first sidestep within 12 iterations")
        self.assertLess(sides[0], 0.0, "the first sidestep escape goes LEFT")
        self.assertEqual([abs(s) for s in sides], [chain_walk.ESCAPE_STRAFE_MAG])
        self.assertEqual([e[2] for e in rig.strafes()][:1],
                         [chain_walk.ESCAPE_STRAFE_SEC] * 1)

    def test_misses_escape_after_MISS_MAX(self):
        self.assertEqual(chain_walk.MISS_MAX, 3)
        rig = Rig(FakeChain(30, default=None), table_at=None)   # clear of the tail cap   # no prompt: the walk ends LOST
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual([i for i, a in enumerate(acts, 1)
                          if a.startswith("escape")], [9, 12, 15, 18],
                         "six blind advances first, then misses count; a rung "
                         "every MISS_MAX misses and LOST only after the fourth")
        self.assertEqual([acts[8], acts[11], acts[14], acts[17]],
                         ["escape:jump", "escape:back", "escape:left", "escape:right"])
        self.assertEqual(acts[-1], "lost")
        self.assertTrue(all(f["fix"] is None for f in res["fixes"]))
        self.assertEqual(rig.count("jump"), 1)

    def test_never_two_escapes_without_a_push_between(self):
        rig = Rig(FakeChain(12, default=None), table_at=15)
        rig.go()
        pushed = True
        for e in rig.events:
            if e[0] == "push":
                pushed = True
            elif e[0] == "jump" or (e[0] == "strafe"
                                    and abs(e[1]) == chain_walk.ESCAPE_STRAFE_MAG):
                self.assertTrue(pushed,
                                "two escapes in a row with no push between")
                pushed = False


class Lateral(unittest.TestCase):
    """(e) one lateral push per iteration, gated, sized and SIGNED."""

    def _one(self, dx):
        # n=4 and table_at=3: iteration 1 corrects, iteration 2 arrives.
        rig = Rig(FakeChain(4, [Fix(k=1, scale=1.0, dx=dx)]), table_at=3)
        res = rig.go()
        self.assertTrue(res["arrived"])
        return rig, rig.strafes()

    def test_dx_positive_strafes_RIGHT(self):
        # pose.offset: dx > 0 = the scene moved RIGHT = the camera is LEFT of
        # the reference. The correction is therefore to the RIGHT, which is
        # POSITIVE lx (walk_steps.unstick names +0.6 "right").
        rig, st = self._one(+80.0)
        self.assertEqual(len(st), 1, "exactly one lateral push per iteration")
        self.assertGreater(st[0][1], 0.0, "dx=+80 must strafe RIGHT (lx > 0)")
        self.assertEqual(st[0][1], pose.STRAFE_MAG)
        self.assertAlmostEqual(
            st[0][2], 80.0 / (chain_walk.LATERAL_GAIN * chain_walk.LATERAL_MAG),
            places=9)

    def test_dx_negative_strafes_LEFT(self):
        _, st = self._one(-80.0)
        self.assertEqual(len(st), 1)
        self.assertLess(st[0][1], 0.0, "dx=-80 must strafe LEFT (lx < 0)")
        self.assertEqual(abs(st[0][1]), pose.STRAFE_MAG)

    def test_inside_the_tolerance_nothing_is_sent(self):
        self.assertEqual(chain_walk.LATERAL_TOL_PX, pose.ALIGN_TOL_PX)
        _, st = self._one(30.0)
        self.assertEqual(st, [], "|dx| under ALIGN_TOL_PX must not be corrected")

    def test_the_push_is_capped_and_floored(self):
        # C05 (CLAUDE.md §10.11): asserting the capped push against
        # `chain_walk.LATERAL_CAP_SEC` rises with the constant and passes
        # forever -- a mutant that doubles the cap to 0.6s (the worst single
        # sidestep in a narrow passage) left this green. Pin the literal, and
        # prove the fixture actually NEEDS capping (5000px uncapped would
        # take far longer than 0.3s at this gain) so the assertion is not
        # vacuously true regardless of the cap's value.
        self.assertEqual(chain_walk.LATERAL_CAP_SEC, 0.3)
        uncapped = 5000.0 / (chain_walk.LATERAL_GAIN * chain_walk.LATERAL_MAG)
        self.assertGreater(uncapped, 0.6,
                           "the fixture must exceed even a doubled cap to be a real test")
        _, big = self._one(5000.0)          # never lunge
        self.assertEqual(big[0][2], 0.3)
        # 36px works out at 0.05s, and a push under ~0.10s does not move the
        # character at all — it would read as a correction and be none.
        _, small = self._one(36.0)
        self.assertEqual(small[0][2], chain_walk.LATERAL_MIN_SEC)
        self.assertEqual(chain_walk.LATERAL_MIN_SEC, pose.ALIGN_MIN_SEC)
        self.assertEqual(chain_walk.LATERAL_GAIN, pose.PX_PER_STRAFE_SEC)

    def test_an_unmeasurable_fix_is_never_corrected(self):
        rig = Rig(FakeChain(4, [None]), table_at=3)
        rig.go()
        self.assertEqual(rig.strafes(), [])

    def test_an_escaping_iteration_does_not_also_strafe_laterally(self):
        # The escape sidestep is ~324px at the closed-loop gain, so a lateral
        # computed from the PRE-escape dx is stale and fights it.
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5, dx=400.0)),
                  table_at=6)
        res = rig.go()
        self.assertEqual(res["fixes"][3]["action"], "escape:jump")
        self.assertIsNone(res["fixes"][3]["lateral"])
        self.assertIsNotNone(res["fixes"][0]["lateral"])
        self.assertEqual(res["fixes"][0]["lateral"]["side"], "right")


class EndTurnTowardTheDealer(unittest.TestCase):
    """(n) ON THE FINAL APPROACH A HUGE dx IS A TURN, NOT A SIDESTEP.

    2026-09-07 22:00-23:20. chains/route_user_1853 ends with a turn-only stop at
    196 (heading 89.5) and pushes at 197, 200, 203, 204 toward the dealer across
    a table. Four trials verified the 196 stop and then read her scene 460-777
    px to the LEFT of where the reference has it (dx -777, -490, -481, -512 at
    112, 52, 48, 41 inliers), strafed LEFT at LATERAL_CAP_SEC every time without
    the offset shrinking, pushed along the recorded 89.5 into the bar counter,
    and ran the plan out by count. None found the prompt; the one arrival at
    that spot had |dx| 286-342. The user: "they made it to the mini game table
    but weren't close enough to get the prompt to start the game. They turned
    directly into the bar and just kept getting stuck."

    THE SIGN IS THE THING THAT COULD SILENTLY DO THE OPPOSITE. It comes from the
    stop look-around's own un-yaw, `px = dx2 + ddeg * PX_PER_DEG` with
    `turn_to(heading + ddeg)`: a frame measured at h + D reads
    `dx_at_h - D * PX_PER_DEG`, so D = dx / PX_PER_DEG and a NEGATIVE dx turns
    LEFT (decreasing heading). Every expected heading below is a LITERAL, so an
    inverted sign fails instead of tracking the code (§10.11).

    THE LAST FOUR TESTS ARE THE INTERACTION SUITE, one per bypass a skeptic
    demonstrated on 2026-09-08 against the first draft of this rule. They matter
    more than their size suggests: a wrong SIDESTEP costs one iteration, while a
    wrong END TURN rides every remaining heading for the rest of the walk and
    spends one of only three slots.
    """

    # 15 walking frames at 0.35 stick compile to push targets 1, 4, 7, 10, 13
    # (0.0875 u a frame against PLAN_STEP_UNITS 0.180), then ONE stationary
    # frame is the turn-only stop at 16, then the tail -- the same shape as the
    # real chain's 196 stop and its 197..204 approach.
    @staticmethod
    def _wps(tail_headings, walk_frames=15, stop_heading=89.5, walk_heading=0.0):
        wps = [Wp(0, walk_heading)]
        rows = ([(walk_heading, -0.35)] * walk_frames + [(stop_heading, 0.0)]
                + [(h, -0.35) for h in tail_headings])
        for i, (h, ly) in enumerate(rows, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        return wps

    @staticmethod
    def _rig(wps, fixes, table_at=None, lookback=None):
        ch = FakeChain(len(wps), fixes, default=None, lookback=lookback)
        ch.waypoints = wps
        return Rig(ch, table_at=table_at)

    # The six fixes that walk the plan to the stop and verify it: one per push
    # target, then the stop's own frame at 16.
    TO_THE_STOP = (1, 4, 7, 10, 13, 16)

    def test_the_constants_are_the_measured_ones_and_there_is_ONE_px_per_deg(self):
        # §10.11: pin the literals, not the constants they guard.
        self.assertEqual(chain_walk.END_TURN_PX, 400.0)
        self.assertEqual(chain_walk.END_TURN_MAX_DEG, 45.0)
        self.assertEqual(chain_walk.END_TURN_MAX, 3)
        self.assertEqual(chain_walk.PX_PER_DEG, 19.7)
        # 400 sits between the two measured populations at that spot (§10.4):
        # the arrival's |dx| 286-342, the four failures' 460-777.
        self.assertLess(342.0, chain_walk.END_TURN_PX)
        self.assertLess(chain_walk.END_TURN_PX, 460.0)
        with open(os.path.join(_ROOT, "chain_walk.py")) as fh:
            src = fh.read()
        self.assertIn("ddeg * PX_PER_DEG", src,
                      "the stop look-around must un-yaw with the NAME")
        self.assertEqual(src.count("19.7"), 1,
                         "px-per-degree must appear as ONE literal, in "
                         "PX_PER_DEG — the un-yaw and the end turn invert the "
                         "same relation and must not drift apart")

    def test_last_stop_index_names_the_LAST_turn_only_entry(self):
        plan = chain_walk.plan_indices(self._wps([89.5] * 6))
        self.assertEqual([(i, p) for i, p, _ in plan][:7],
                         [(1, True), (4, True), (7, True), (10, True),
                          (13, True), (16, False), (17, True)])
        self.assertEqual(chain_walk._last_stop_index(plan), 5)
        # A plan with no stop at all opens the rule only at_end.
        self.assertIsNone(chain_walk._last_stop_index(
            [(1, True, 0.0), (2, True, 0.0)]))

    def test_past_the_last_stop_a_huge_dx_TURNS_and_does_not_strafe(self):
        # The tail: targets 17 (heading 89.5) and 20 (heading 95.0). The fit at
        # 17 reads the dealer 600 px LEFT -- the trials' -481 to -777 -- so the
        # loop turns LEFT by 600 / 19.7 = 30.5 deg to 59.0 and does not strafe;
        # the NEXT push then turns to 95.0 - 30.5 = 64.5, not to 95.0.
        wps = self._wps([89.5] * 3 + [95.0] * 10)
        rig = self._rig(wps, [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-600.0), Fix(k=20)], table_at=10)
        res = rig.go()
        self.assertTrue(res["arrived"])
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 59.0, 64.5],
                         "walk east, turn at the stop, TURN TOWARD THE SCENE, "
                         "then carry the offset onto the next recorded heading")
        self.assertEqual(rig.strafes(), [],
                         "a turn replaces the sidestep; it does not join it")
        row = res["fixes"][6]
        self.assertEqual(row["iteration"], 7)
        self.assertEqual(row["action"], "advanced")
        self.assertEqual(row["lateral"], {"end_turn": -30.5, "dx": -600.0,
                                          "heading": 59.0, "n": 1})
        # ANTI-VACUITY: this dx is far past the lateral tolerance, so the old
        # build DID strafe here (that is the failure) -- the empty strafe list
        # above is the rule working, not a walk that never corrects anything.
        self.assertGreater(600.0, chain_walk.LATERAL_TOL_PX)
        self.assertEqual(chain_walk._last_stop_index(
            chain_walk.plan_indices(wps)), 5)

    def test_a_positive_dx_turns_RIGHT(self):
        # The mirror image: dx > 0 is the scene sitting RIGHT of where the
        # reference has it, so the camera turns RIGHT (increasing heading).
        rig = self._rig(self._wps([89.5] * 3 + [95.0] * 10),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=+600.0), Fix(k=20)], table_at=10)
        rig.go()
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 120.0, 125.5])

    def test_the_turn_is_capped_at_END_TURN_MAX_DEG(self):
        # A wrong match with an enormous dx must not spin the camera: 2000 px
        # would be 101.5 deg, and the cap holds it to 45.
        self.assertGreater(2000.0 / chain_walk.PX_PER_DEG,
                           chain_walk.END_TURN_MAX_DEG,
                           "the fixture must exceed the cap to be a real test")
        rig = self._rig(self._wps([89.5] * 3 + [95.0] * 10),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-2000.0), Fix(k=20)], table_at=10)
        res = rig.go()
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 44.5, 50.0])
        self.assertEqual(res["fixes"][6]["lateral"]["end_turn"], -45.0)

    def test_below_END_TURN_PX_the_ordinary_lateral_correction_runs(self):
        # 300 px is the arrival's own band (286-342). Nothing turns; the
        # sidestep happens exactly as it did before this rule existed, and the
        # next push goes to the RECORDED 95.0 with no offset on it.
        rig = self._rig(self._wps([89.5] * 3 + [95.0] * 10),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-300.0), Fix(k=20)], table_at=10)
        res = rig.go()
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 95.0])
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)])
        self.assertEqual(res["fixes"][6]["lateral"],
                         {"dx": -300.0, "side": "left", "seconds": 0.3})
        self.assertNotIn("end_turn", res["fixes"][6]["lateral"])

    def test_the_same_dx_MID_CHAIN_strafes_and_never_turns(self):
        # THE CONTROL, and the whole reason the rule is gated on position: the
        # identical -600 px five targets BEFORE the last stop is the lateral
        # displacement the strafe exists for. Turning there would aim every
        # later push off the recorded line -- GRAVEYARD's closed "steering
        # while walking" family.
        wps = self._wps([89.5] * 3 + [95.0] * 10)
        rig = self._rig(wps, [Fix(k=1), Fix(k=4), Fix(k=7), Fix(k=10),
                              Fix(k=13, dx=-600.0), Fix(k=16)], table_at=8)
        res = rig.go()
        self.assertTrue(res["arrived"])
        self.assertEqual([r["lateral"] for r in res["fixes"]
                          if r["lateral"] and "end_turn" in r["lateral"]], [],
                         "no end turn may fire before the last stop")
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)])
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5], "the recorded headings, unoffset")
        # ANTI-VACUITY: the pointer really was before the last stop when that
        # dx arrived (target 13 is plan entry 4; the stop is entry 5), so the
        # rule was WITHHELD, not simply unreachable in this fixture.
        self.assertEqual(res["fixes"][4]["target"], 13)
        self.assertEqual(chain_walk._last_stop_index(
            chain_walk.plan_indices(wps)), 5)

    def test_the_END_BUDGET_pushes_along_the_final_heading_PLUS_the_offset(self):
        # Past the plan there are no targets left and the loop pushes along
        # `plan_last_heading` inside the end budget. That heading must carry the
        # offset too, or the last push of the walk -- the one nearest the
        # prompt -- goes back to aiming at the bar. always_turning so the turn
        # is visible on every iteration rather than skipped as a repeat.
        wps = self._wps([89.5] * 3 + [110.0] * 2)
        rig = self._rig(wps, [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-600.0), Fix(k=20), Fix(k=21)])
        res = always_turning(rig.go)
        self.assertIsNotNone(res["failure"])
        self.assertTrue(res["failure"].startswith("reached the last waypoint"),
                        res["failure"])
        self.assertTrue(res["fixes"][-1]["at_end"])
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns[-3:], [79.5, 79.5, 79.5],
                         "110.0 - 30.5: the two tail targets AND the end "
                         "budget's push along the plan's final heading")
        self.assertNotIn(110.0, turns,
                         "the recorded final heading was never commanded bare "
                         "once the end turn had been taken")

    def test_a_regression_in_the_end_phase_takes_no_fresh_end_turn(self):
        # The recheck skeptic's probe: one end turn at 17 (-30.5), then at
        # the last target the sensor sees nothing and the look-back names
        # waypoint 1 with dx +600 -- a REGRESSION. at_end was computed before
        # the regression reset the pointer, so without 'not regressed' the
        # block fired a second, bogus end turn off the stale tail heading and
        # the offset rode onto the recorded 0.0 of the next push (329.5).
        wps = self._wps([89.5] * 6)
        fixes = [Fix(k=1), Fix(k=4), Fix(k=7), Fix(k=10), Fix(k=13), Fix(k=16),
                 Fix(k=17, dx=-600.0), Fix(k=20), Fix(k=22)]
        ch = FakeChain(len(wps), fixes, default=None, lookback=Fix(k=1, dx=600.0, inliers=120))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = without_stuck(rig.go, time_cap=30.0)
        rows = res["fixes"]
        reg = [r for r in rows if r["action"] == "regressed"]
        self.assertEqual(len(reg), 1, [r["action"] for r in rows[:12]])
        self.assertNotIn("end_turn", reg[0]["lateral"] or {}, reg[0]["lateral"])
        self.assertEqual(sum(1 for r in rows if r.get("lateral") and "end_turn" in r["lateral"]), 1)
        turns = [round(e[1], 1) for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns[:4], [0.0, 89.5, 59.0, 0.0],
                         "after the regression the next turn is the RECORDED heading: %r" % turns[:6])

    def test_END_TURN_MAX_caps_the_turns_and_the_strafe_returns_after(self):
        # Three end turns, accumulating: 89.5 -> 59.0 -> 28.5 -> 358.0. The
        # fourth huge dx gets the ordinary correction, because a match that
        # keeps reading 600 px off after three turns is not a heading error.
        rig = self._rig(self._wps([89.5] * 20),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-600.0), Fix(k=20, dx=-600.0),
                           Fix(k=23, dx=-600.0), Fix(k=26, dx=-600.0)],
                        table_at=12)
        res = rig.go()
        self.assertTrue(res["arrived"])
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 59.0, 28.5, 358.0],
                         "the offset ACCUMULATES across end turns")
        turned = [r["lateral"] for r in res["fixes"]
                  if r["lateral"] and "end_turn" in r["lateral"]]
        self.assertEqual([t["n"] for t in turned], [1, 2, 3])
        self.assertEqual(chain_walk.END_TURN_MAX, 3)
        # The fourth: no turn, and the sidestep the rule had been replacing.
        self.assertEqual(res["fixes"][9]["lateral"],
                         {"dx": -600.0, "side": "left", "seconds": 0.3})
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)])

    # --- the interaction suite: the three gates the strafe already had -------

    def test_an_iteration_that_ESCAPED_takes_no_end_turn(self):
        """THE ESCAPE COLLISION. `escape:jump` and a 30.5 deg turn fired off the
        SAME pre-escape frame: the jump's displacement is not in that dx, which
        is precisely why the ordinary strafe is gated on `not escaped and not
        escaped_prev`. An end turn is worse than the strafe it replaces there,
        because it rides every later heading and spends one of three slots.

        The fixture stalls three times on a dx BELOW the tolerance (so nothing
        corrects and nothing turns), and the fourth stall -- the one that trips
        STALL_MAX and escapes -- is the one carrying -600.
        """
        rig = self._rig(self._wps([89.5] * 20),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=16, scale=0.5, dx=0.0)] * 3
                        + [Fix(k=16, scale=0.5, dx=-600.0)] * 3, table_at=14)
        res = rig.go()
        rows = {r["iteration"]: r for r in res["fixes"]}
        self.assertEqual(chain_walk.STALL_MAX, 4)
        self.assertEqual(rows[10]["action"], "escape:jump",
                         "the fixture must really escape on that iteration")
        self.assertIsNone(rows[10]["lateral"],
                          "no end turn in the iteration that escaped")
        self.assertEqual(rows[11]["action"], "stalled")
        self.assertIsNone(rows[11]["lateral"],
                          "nor in the one after it: escaped_prev, the same "
                          "gate the strafe has")
        # DEFERRED, NOT LOST: the first clean iteration takes the turn.
        self.assertEqual(rows[12]["lateral"],
                         {"end_turn": -30.5, "dx": -600.0, "heading": 59.0,
                          "n": 1})
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 59.0])
        # ANTI-VACUITY: the dx and the position both opened the rule on
        # iteration 10 -- it was the escape that closed it, not the fixture.
        self.assertGreater(600.0, chain_walk.END_TURN_PX)
        self.assertEqual(rows[10]["target"], 17)
        self.assertEqual(chain_walk._last_stop_index(
            chain_walk.plan_indices(rig.chain.waypoints)), 5)

    def test_a_REGRESSION_drops_the_end_yaw_before_it_rides_a_MID_CHAIN_heading(self):
        """THE REGRESSION LEAK. The end turn fires only past the last stop, but
        the OFFSET was applied to whatever heading the current plan pointer
        named -- and the look-back regression branch sets `pi = 0`. Demonstrated:
        after one end turn at the tail, a regression to waypoint 1 commanded the
        recorded mid-chain 0.0 as 329.5, which is the "steering while walking"
        family GRAVEYARD closed. A regression is the loop saying the position
        that measured the dx was wrong, so the yaw goes with it.
        """
        wps = self._wps([89.5] * 3 + [95.0] * 10)
        rig = self._rig(wps, [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-600.0),
                           Fix(k=17, scale=0.5, inliers=5)]
                        + [Fix(k=4)] * 4, table_at=10,
                        lookback=Fix(k=1, inliers=120))
        res = rig.go()
        rows = {r["iteration"]: r for r in res["fixes"]}
        # The end turn happened (iteration 7), then a thin fit at 17 sent the
        # look-back back to waypoint 1 (iteration 8).
        self.assertEqual(rows[7]["lateral"], {"end_turn": -30.5, "dx": -600.0,
                                              "heading": 59.0, "n": 1})
        self.assertEqual(rows[8]["action"], "regressed")
        self.assertEqual(rows[8]["k"], 1)
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 59.0, 64.5, 0.0],
                         "0.0 is the RECORDED mid-chain heading: the offset "
                         "died with the position that earned it (the leak "
                         "commanded 329.5 here)")
        # ANTI-VACUITY: the offset really was live on the iteration before the
        # regression -- 95.0 - 30.5 = 64.5 above -- so this is the yaw being
        # dropped, not a walk that never took one.
        self.assertEqual(rows[9]["target"], 4)
        self.assertTrue(res["arrived"])

    def test_the_DETOUR_HOLD_is_not_bypassed_by_the_end_turn(self):
        """THE DETOUR-HOLD BYPASS. Three escape rungs sidestep LEFT around a
        blockage and hold any correction toward the RIGHT until the plan has
        moved DETOUR_TARGETS past it. Spliced above that hold, the end turn read
        the very dx the hold had suppressed and turned the camera 30.5 deg back
        toward the obstacle -- permanently, since the yaw rides every later
        heading. The rule now sits below the hold, which has already set dx to
        None, and the row still reads `held: detour`.

        The +600 arrives two iterations after the escape, so neither `escaped`
        nor `escaped_prev` is what suppresses it: this pins the HOLD.
        """
        rig = self._rig(self._wps([89.5] * 20),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=16, scale=0.5, dx=0.0)] * 13
                        + [Fix(k=16, scale=0.5, dx=+600.0)], table_at=22)
        res = rig.go()
        rows = {r["iteration"]: r for r in res["fixes"]}
        self.assertEqual(rows[18]["action"], "escape:left",
                         "the fixture must reach the sidestep rung that arms "
                         "the detour hold")
        self.assertEqual(rows[19]["action"], "stalled",
                         "and the +600 must land clear of escaped_prev")
        self.assertEqual(rows[20]["lateral"],
                         {"held": "detour", "dx": 600.0, "side": "held",
                          "seconds": 0.0},
                         "held, exactly as it was before this rule existed")
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5],
                         "no camera turn back toward the obstacle the detour "
                         "had just gone around")
        self.assertEqual(rig.strafes(), [("strafe", -0.45, 0.6)],
                         "the escape's own sidestep, and nothing after it")
        # ANTI-VACUITY: the same +600 with no detour armed DOES turn right --
        # test_a_positive_dx_turns_RIGHT -- and the hold is live here because
        # k has not reached detour_until.
        self.assertEqual(rows[20]["k"], 16)
        self.assertEqual(chain_walk.DETOUR_TARGETS, 3)

    def test_what_turn_to_REPORTED_is_recorded_and_gates_nothing(self):
        """The end turn is the one site that turns a turn_to into PERSISTENT
        state, so what turn_to said goes in the row. It is NOT a gate: §3 says
        the compass abstains reliably inside the bar, which is exactly where
        this rule fires, and slow_traverse.turn_to reports UNDERTURNED whenever
        it cannot read a heading — refusing the turn on that would switch the
        rule off precisely where it exists to work (§10.1).
        """
        class _Hazard:
            kind = "UNDERTURNED"

        rig = self._rig(self._wps([89.5] * 3 + [95.0] * 10),
                        [Fix(k=i) for i in self.TO_THE_STOP]
                        + [Fix(k=17, dx=-600.0), Fix(k=20)], table_at=10)
        plain = rig.turn_to

        def reporting_turn_to(heading, _plain=plain):
            _plain(heading)
            return None, [_Hazard()]      # slow_traverse's shape: (now, hazards)

        rig.turn_to = reporting_turn_to
        res = rig.go()
        self.assertEqual(res["fixes"][6]["lateral"],
                         {"end_turn": -30.5, "dx": -600.0, "heading": 59.0,
                          "n": 1,
                          "turn": {"reached": None,
                                   "hazards": ["UNDERTURNED"]}})
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [0.0, 89.5, 59.0, 64.5],
                         "the hazard is recorded and the turn still happens")
        # A stub that reports nothing (the plain Rig, and every other test in
        # this class) leaves the row exactly as it was — no invented key.
        self.assertIsNone(chain_walk._turn_report(None))
        self.assertIsNone(chain_walk._turn_report((1, 2, 3)))
        self.assertEqual(chain_walk._turn_report((59.04, [])),
                         {"reached": 59.0, "hazards": []})


class TimeCap(unittest.TestCase):
    """(f) running out of time is a TIMED OUT failure, never an arrival."""

    def test_time_cap_fails_and_says_so(self):
        rig = Rig(FakeChain(6, default=Fix(k=0, scale=0.5)), table_at=None)
        res = without_stuck(rig.go, time_cap=10.0)
        self.assertFalse(res["arrived"])
        self.assertEqual(res["failure"], "timed out")
        self.assertGreaterEqual(res["seconds"], 10.0)
        self.assertGreater(res["pushes"], 0, "it must actually have tried")
        self.assertEqual(res["pushes"], rig.count("push"))

    def test_the_cap_default_is_read_at_CALL_time_not_bound_at_import(self):
        # §10.18: a module-level knob captured in a `def` line is bound once
        # when the `def` runs, so a test or an A/B that redirects it changes
        # NOTHING and nothing says so. Measured on leg_reliability's
        # `path=STORE` and on `press(post_delay=ACTION_DELAY)` before that.
        rig = Rig(FakeChain(6, default=Fix(k=0, scale=0.5)), table_at=None)
        old = chain_walk.TIME_CAP
        try:
            chain_walk.TIME_CAP = 3.05
            res = always_turning(rig.go, )
        finally:
            chain_walk.TIME_CAP = old
        self.assertEqual(res["failure"], "timed out")
        self.assertEqual(res["iterations"], 3,
                         "walk() ignored the redirected TIME_CAP")

    def test_the_default_cap_is_the_measured_one(self):
        # Pinned as a literal: asserting against the constant it guards would
        # rise with the constant and pass forever (CLAUDE.md §10.11).
        self.assertEqual(chain_walk.TIME_CAP, 400.0)
        self.assertEqual(chain_walk.PUSH_MAG, 0.45)
        self.assertEqual(chain_walk.PUSH_SEC, 0.40)


class Bookkeeping(unittest.TestCase):
    """(g) every iteration is recorded; with shots= every frame is on disk."""

    def test_every_iteration_appends_a_row(self):
        rig = Rig(FakeChain(4, [Fix(k=1, scale=1.0), None, None,  # the miss's look-back gets the 2nd None
                                Fix(k=2, scale=1.0)]), table_at=5)
        res = rig.go()
        self.assertEqual(len(res["fixes"]), 4)
        for row in res["fixes"]:
            for key in ("iteration", "k", "target", "fix", "action",
                        "lateral", "seconds", "elapsed"):
                self.assertIn(key, row)
        self.assertEqual([r["iteration"] for r in res["fixes"]], [1, 2, 3, 4])
        self.assertIsNone(res["fixes"][1]["fix"], "a miss records fix=None")
        self.assertEqual(
            set(res["fixes"][0]["fix"]),
            {"k", "k_float", "inliers", "dx", "dy", "scale", "second",
             "second_k", "second_dx", "detail"})
        self.assertEqual(res["fixes"][0]["fix"]["inliers"], 120)
        # The clock is only advanced by the stubs, so this is exact:
        # turn 0.5 + push 0.4 + capture 0.1.
        self.assertAlmostEqual(res["fixes"][0]["seconds"], 1.0, places=6)
        self.assertEqual(res["k_final"], 2)

    def test_shots_writes_one_frame_per_capture(self):
        d = tempfile.mkdtemp(prefix="chain_shots_")
        try:
            rig = Rig(FakeChain(4, [Fix(k=1, scale=1.0)]), table_at=3)
            rig.go(shots=d)
            self.assertEqual(sorted(os.listdir(d)),
                             ["it_000_k0.jpg", "it_001_k0.jpg",
                              "it_002_k1.jpg"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_waypoint_with_no_heading_is_not_turned_to(self):
        ch = FakeChain(4, [Fix(k=1, scale=1.0), Fix(k=2, scale=1.0)],
                       headings=[0.0, 111.0, None, 333.0])
        rig = Rig(ch, table_at=4)
        rig.go()
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [111.0, 333.0])

    def test_a_chain_too_short_to_walk_is_refused(self):
        rig = Rig(FakeChain(1), table_at=None)
        res = rig.go()
        self.assertFalse(res["arrived"])
        self.assertIn("waypoint", res["failure"])
        self.assertEqual(rig.count("push"), 0)


class ConsecutiveCounters(unittest.TestCase):
    """(h) BOTH counters mean CONSECUTIVE, and both resets are load-bearing.

    A skeptic deleted `misses = 0` and `stalls = 0` in turn and the whole suite
    stayed green: no test mixed a good fix with misses, or an advance with
    stalls. Cumulative counters would fire an escape on essentially every
    iteration once the totals were reached, and one escape is a 0.3s sidestep
    at 0.45 — GRAVEYARD.md's "blind crabbing to get around an obstacle: walked
    the character off the spot into a wall, ending with no table in view".

    Each test runs to the TIME CAP rather than an arrival, so the actions of
    every iteration are on the record; the clock is the stubs' own, so the
    iteration count is exact.
    """

    def test_a_readable_fix_resets_the_miss_counter(self):
        self.assertEqual(chain_walk.MISS_MAX, 3)
        # miss, miss, a fix that is READ but does not advance, miss, miss.
        # Consecutively that is never 3, so nothing escapes. Cumulatively it is
        # 4, and the escape fires on the fourth iteration.
        # A blind sensor first dead-reckons BLIND_MAX pushes (the target is
        # believed reached); only then do misses count. Every miss past k=0
        # also asks a look-back, which consumes a scripted entry: the credible
        # fix is the 16th scripted locate call (wide searches are served apart). It does not advance (scale 0.5) but it
        # is READ, so the two misses before it never sum with anything after:
        # a credible fix also restores the blind budget.
        self.assertEqual(chain_walk.BLIND_MAX, 6)
        rig = Rig(FakeChain(30, [None] * 15 + [Fix(k=6, scale=0.5)]),   # 30: clear of the six-target tail cap   # wide searches never consume the script
                  table_at=None)
        res = always_turning(rig.go, time_cap=11.05)         # exactly eleven 1.0s iterations
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["blind-advance"] * 6 + ["miss", "miss", "stalled",
                                                  "blind-advance", "blind-advance"],
                         "a READ fix resets both the miss count and the blind budget")
        self.assertEqual(rig.count("jump"), 0,
                         "a fix that could be READ must reset the miss count")
        self.assertEqual(rig.strafes(), [])

    def test_a_readable_fix_resets_the_miss_counter_with_no_blind_advance_to_mask_it(self):
        # W22 (report agent_progress/closed-loop/snoopy_sweep/report.md): the
        # test above CANNOT fail on a mutant that deletes the credible
        # branch's own `misses = 0` -- a credible fix ALSO resets `blind`
        # unconditionally (unmutated), so the very next None/weak fix always
        # takes the blind-advance branch first (its own cap is never 0),
        # which ALSO sets `misses = 0` on its way to exhausting the budget
        # again. The credible branch's reset is masked in every fixture that
        # relies on a later blind-advance ladder to surface it.
        #
        # At the chain's LAST waypoint the blind-advance branch is gated off
        # entirely by `not at_end`, so a subsequent miss goes straight to the
        # miss counter with no such mask. Two misses (misses=2), a credible
        # fix that is READ but does not advance, then one more miss:
        # consecutively that is 1, never MISS_MAX, so nothing escapes.
        # Cumulatively (the bug) it is 2 + 1 = 3 and the third miss escapes.
        self.assertEqual(chain_walk.MISS_MAX, 3)
        rig = Rig(FakeChain(2, [Fix(k=1, scale=1.0), None, None,
                                Fix(k=1, scale=0.9), None], lookback=None),
                  table_at=None)
        res = rig.go(time_cap=10.0, end_iterations=10)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(
            acts[:5], ["advanced", "miss", "miss", "stalled", "miss"],
            "a fix that is READ but does not advance must still reset the "
            "miss count -- a mutant that drops the reset escapes on the "
            "5th action instead of a third miss")

    def test_an_advance_resets_the_stall_counter(self):
        self.assertEqual(chain_walk.STALL_MAX, 4)
        # three stalls, an ADVANCE, three more stalls: consecutively never 4.
        # Cumulatively the sixth would escape.
        rig = Rig(FakeChain(8, [Fix(k=0, scale=0.5), Fix(k=0, scale=0.5),
                                Fix(k=0, scale=0.5), Fix(k=1, scale=1.0),
                                Fix(k=1, scale=0.5), Fix(k=1, scale=0.5),
                                Fix(k=1, scale=0.5)]),
                  table_at=None)
        res = always_turning(rig.go, time_cap=7.05)          # exactly seven 1.0s iterations
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["stalled", "stalled", "stalled", "advanced",
                          "stalled", "stalled", "stalled"])
        self.assertEqual([f["k"] for f in res["fixes"]],
                         [0, 0, 0, 1, 1, 1, 1])
        self.assertEqual(rig.count("jump"), 0,
                         "an advance must reset the stall count")
        self.assertEqual(rig.strafes(), [])


class PlanMinIterations(unittest.TestCase):
    """W01 (report agent_progress/closed-loop/snoopy_sweep/report.md):
    `plan_min_iterations` -- what `walk()` ACTUALLY uses for
    `res["min_iterations"]`, `iteration_budget_sec` and the ARITHMETIC-vs-
    NAVIGATION timeout diagnosis -- had no test of its own; only the simpler
    `min_iterations()` (a different function, see IterationArithmetic below)
    was pinned. A mutant that drops turn-only targets from the floor entirely
    makes a chain with several stops look arithmetically cheaper than it is,
    so a genuinely unwalkable chain gets blamed on NAVIGATION instead.
    """

    def test_turn_only_targets_add_one_iteration_each_on_top_of_the_pushes(self):
        # 2 turn-only stops + 9 push targets at window 3: two turns (one
        # iteration each, never batched) plus ceil(9/3) for the pushes.
        plan = [(1, False, 10.0), (2, False, 20.0)] + [(i, True, 0.0) for i in range(3, 12)]
        self.assertEqual(chain_walk.plan_min_iterations(plan, window=3), 5)

    def test_a_plan_of_only_turns_needs_one_iteration_each(self):
        plan = [(i, False, float(i)) for i in range(4)]
        self.assertEqual(chain_walk.plan_min_iterations(plan, window=3), 4)

    def test_the_default_window_is_ADVANCE_MAX(self):
        self.assertEqual(chain_walk.ADVANCE_MAX, 1)
        plan = [(1, False, 0.0)] + [(i, True, 0.0) for i in range(2, 5)]
        # one turn + three pushes at the default window (1): 1 + 3 = 4.
        self.assertEqual(chain_walk.plan_min_iterations(plan), 4)

    def test_an_empty_plan_still_needs_at_least_one_iteration(self):
        self.assertEqual(chain_walk.plan_min_iterations([], window=3), 1)


class PlanIndicesStrideAndBoundary(unittest.TestCase):
    """P01/P02/P06 (report agent_progress/closed-loop/snoopy_sweep/report.md):
    the caller's `stride` argument and the stationary boundary had no
    coverage at all -- every existing test either takes the default stride
    or drives stationarity through recorded `ly`, never at exactly
    STATIONARY_STICK.
    """

    def test_a_caller_supplied_stride_is_honoured(self):
        # P01/P06: with no stick data every frame is "unknown", so stride is
        # the ONLY thing deciding which frames emit. stride=3 must emit
        # every third frame, not every frame (P01: the argument silently
        # replaced by the module default) and not EVERY frame regardless of
        # the count (P06: the stride gate itself deleted) -- both mutants
        # give [1, 2, 3] here instead of [1, 4, 7].
        wps = [Wp(0, 0.0)] + [Wp(i, float(i)) for i in range(1, 10)]
        plan = chain_walk.plan_indices(wps, stride=3)
        pushes = [i for i, p, _ in plan if p]
        self.assertEqual(pushes[:3], [1, 4, 7], "stride=3 was not honoured")

    def test_the_default_stride_is_one(self):
        self.assertEqual(chain_walk.STRIDE, 1)
        wps = [Wp(0, 0.0)] + [Wp(i, float(i)) for i in range(1, 6)]
        plan = chain_walk.plan_indices(wps)
        self.assertEqual([i for i, p, _ in plan if p], [1, 2, 3, 4, 5])

    def test_the_stationary_boundary_is_inclusive_at_the_threshold(self):
        # P02: a stick magnitude of EXACTLY STATIONARY_STICK must count as
        # stationary (<=), not walking (<) -- the threshold must sit AT the
        # measured value, not just below it (CLAUDE.md §10.4).
        self.assertEqual(chain_walk.STATIONARY_STICK, 0.05)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.05), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        plan = chain_walk.plan_indices(wps)
        self.assertEqual(plan, [(1, True, 90.0), (2, False, 0.0), (3, True, 0.0)],
                         "ly == STATIONARY_STICK must be treated as stationary")


class IterationArithmetic(unittest.TestCase):
    """(i) k rises by at most WINDOW, so a dense chain may not fit the cap.

    A chain recorded at chain_record's 0.25s period over the 244s route is
    ~1000 waypoints and cannot reach its own tail inside 400s at any plausible
    per-iteration cost. Nothing used to say so, and ten TIMED_OUTs of that kind
    are indistinguishable from ten navigation failures while needing the
    opposite response.
    """

    def test_the_minimum_iteration_count_is_the_windowed_arithmetic(self):
        self.assertEqual(chain_walk.WINDOW, 3)
        self.assertEqual(chain_walk.TABLE_CHECK_TAIL, 30)
        # Literals, not the formula re-expressed. With TABLE_CHECK_TAIL 30 the
        # prompt is believed once the target is within 30 of the end, so the
        # floor is one iteration past k reaching n - 31: 1 + ceil(969 / 1) =
        # 970, 1 + ceil(969 / 3) = 324. A chain shorter than the tail has the
        # gate open from the first frame: the floor is 1. An explicit tail is
        # still honoured when passed.
        self.assertEqual(chain_walk.min_iterations(1000), 970)
        self.assertEqual(chain_walk.min_iterations(1000, window=3), 324)
        self.assertEqual(chain_walk.min_iterations(1000, tail=3, window=3), 333)
        self.assertEqual(chain_walk.min_iterations(10), 1)
        self.assertEqual(chain_walk.min_iterations(4), 1)
        self.assertEqual(chain_walk.min_iterations(2), 1)

    def test_every_walk_reports_the_arithmetic(self):
        rig = Rig(FakeChain(10, [Fix(k=3), Fix(k=6)]), table_at=2)
        res = rig.go()
        self.assertEqual(res["waypoints"], 10)
        self.assertEqual(res["min_iterations"], 9)
        self.assertEqual(res["iteration_budget_sec"], 44.444)  # 400 / 9
        self.assertEqual(res["iterations"], 1,
                         "the prompt was up after push 1 and was believed")
        self.assertEqual(res["plan_targets"], 9)
        self.assertEqual(res["plan_turns"], 0)

    def test_a_chain_too_long_for_the_cap_is_refused_before_it_moves(self):
        # 100 waypoints need 99 iterations at ADVANCE_MAX 1; at a 1.5s floor that is 148s.
        rig = Rig(FakeChain(100, default=Fix(k=0, scale=0.5)), table_at=None)
        res = rig.go(time_cap=10.0, iteration_sec_floor=1.5)
        self.assertFalse(res["arrived"])
        self.assertIn("too long for the cap", res["failure"])
        self.assertIn("99 iterations", res["failure"])
        self.assertEqual(res["pushes"], 0)
        self.assertEqual(rig.events, [],
                         "the refusal must come before the first capture")

    def test_without_a_floor_nothing_is_ever_refused(self):
        # The control. The floor is a knob defaulted to OFF because no such
        # floor has been measured on this rig; with it unset the same chain
        # must walk and time out normally, or the check above would be a gate
        # that silently refuses live runs.
        rig = Rig(FakeChain(100, default=Fix(k=0, scale=0.5)), table_at=None)
        res = without_stuck(rig.go, time_cap=10.0)
        self.assertEqual(res["failure"], "timed out")
        self.assertGreater(res["pushes"], 0)

    def test_a_timeout_says_whether_it_was_the_chain_or_the_walking(self):
        long_chain = Rig(FakeChain(100, default=Fix(k=0, scale=0.5)),
                         table_at=None)
        res = long_chain.go(time_cap=5.05)
        self.assertTrue(res["timeout_diagnosis"].startswith("ARITHMETIC"),
                        res["timeout_diagnosis"])
        self.assertIn("99 iterations", res["timeout_diagnosis"])

        short_chain = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                          table_at=None)
        res = short_chain.go(time_cap=5.05)
        self.assertTrue(res["timeout_diagnosis"].startswith("NAVIGATION"),
                        res["timeout_diagnosis"])
        self.assertIn("k stopped at 0", res["timeout_diagnosis"])

    def test_a_timeout_with_no_iteration_at_all_blames_neither(self):
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)), table_at=None)
        res = rig.go(time_cap=0.05)          # the first capture already exceeds it
        self.assertEqual(res["iterations"], 0)
        self.assertIn("no iteration completed", res["timeout_diagnosis"])


class Journal(unittest.TestCase):
    """(i) the per-iteration rows reach disk AS THEY HAPPEN.

    The harness kills a trial at the external ceiling and a killed child prints
    no JSON, so `fixes` used to die with it — on exactly the trials that need
    explaining. §10.16: a file written on completion is lost in precisely the
    case it exists for.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="chain_journal_")
        self.path = os.path.join(self.d, "j.jsonl")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_the_journal_holds_exactly_the_rows_the_result_does(self):
        rig = Rig(FakeChain(4, [Fix(k=1, scale=1.0), None]), table_at=4)
        rig.journal = self.path
        res = rig.go(journal=self.path)
        self.assertTrue(res["arrived"])
        with open(self.path) as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(rows, res["fixes"])
        self.assertEqual(len(rows), 3)

    def test_rows_are_on_disk_before_the_walk_ends(self):
        rig = Rig(FakeChain(4, [Fix(k=1, scale=1.0), None]), table_at=4)
        rig.journal = self.path
        rig.go(journal=self.path)
        # at_table runs before that iteration's row is recorded, so the counts
        # lag by one. All zeros would mean the journal was written at the end.
        self.assertEqual(rig.journal_lines, [0, 0, 1, 2])

    def test_an_unwritable_journal_never_ends_a_walk(self):
        rig = Rig(FakeChain(4, [Fix(k=1, scale=1.0)]), table_at=3)
        res = rig.go(journal=os.path.join(self.d, "nope", "j.jsonl"))
        self.assertTrue(res["arrived"], "bookkeeping must not end a walk")
        self.assertEqual(len(res["fixes"]), 2)


class HarnessScoring(unittest.TestCase):
    """(j) overnight/chain_trials.py: the scoring, offline, with no console."""

    def setUp(self):
        self._alive = chain_trials._harness.alive
        self.logs = []

    def tearDown(self):
        chain_trials._harness.alive = self._alive

    def log(self, m):
        self.logs.append(m)

    # --- the ceiling arithmetic (the finding that started this class) -------

    def test_the_ceiling_covers_the_setup_as_well_as_the_walk(self):
        # Pinned as literals (§10.11). The child spends its interpreter start,
        # the reset and Chain.load's ORB pass BEFORE walk() starts its clock;
        # at the old 420s ceiling against a 400s cap, walk() would have been
        # killed at ~350s and could never have reported its own timeout.
        self.assertEqual(chain_trials.TIME_CAP, 180.0)
        self.assertEqual(chain_trials.SETUP_BUDGET, 180.0)
        self.assertEqual(chain_trials.CEILING, 360)
        self.assertEqual(chain_trials.CEILING - chain_trials.TIME_CAP,
                         chain_trials.SETUP_BUDGET,
                         "the ceiling must be the cap PLUS the setup budget")

    def test_a_setup_that_overruns_its_budget_is_invalid_not_a_failure(self):
        self.assertIsNone(chain_trials.setup_verdict(30.0))
        self.assertIsNone(
            chain_trials.setup_verdict(chain_trials.SETUP_BUDGET - 0.1))
        over = chain_trials.setup_verdict(chain_trials.SETUP_BUDGET + 1,
                                          waypoints=900)
        self.assertTrue(over["setup_over_budget"])
        self.assertFalse(over["arrived"])
        self.assertEqual(over["waypoints"], 900)
        # And it must SCORE as INVALID even at a time that would otherwise read
        # as a timeout — a slow console is never a navigation result (§10.6).
        self.assertEqual(
            chain_trials.classify(over, chain_trials.CEILING, self.log),
            chain_trials.INVALID)

    # --- classify ----------------------------------------------------------

    def test_classify_reads_the_result_when_there_is_one(self):
        self.assertEqual(chain_trials.classify({"arrived": True}, 90, self.log),
                         chain_trials.ARRIVED)
        self.assertEqual(
            chain_trials.classify({"arrived": False, "failure": "timed out"},
                                  410, self.log), chain_trials.TIMED_OUT)
        self.assertEqual(
            chain_trials.classify({"arrived": False, "failure": "wedged"},
                                  chain_trials.CEILING, self.log),
            chain_trials.TIMED_OUT)
        self.assertEqual(
            chain_trials.classify({"arrived": False, "failure": "wedged"},
                                  120, self.log), chain_trials.FAILED)

    def test_a_killed_trial_is_timed_out_only_while_the_stream_is_alive(self):
        chain_trials._harness.alive = lambda: True
        self.assertEqual(
            chain_trials.classify(None, chain_trials.CEILING, self.log),
            chain_trials.TIMED_OUT)
        chain_trials._harness.alive = lambda: False
        self.assertEqual(
            chain_trials.classify(None, chain_trials.CEILING, self.log),
            chain_trials.INVALID,
            "a dead console is never a navigation result (§10.6)")

    def test_a_crash_before_the_ceiling_is_invalid(self):
        chain_trials._harness.alive = lambda: True
        self.assertEqual(chain_trials.classify(None, 12.0, self.log),
                         chain_trials.INVALID)

    def test_a_stream_check_that_raises_is_invalid_and_says_so(self):
        def boom():
            raise RuntimeError("capture died")
        chain_trials._harness.alive = boom
        self.assertEqual(
            chain_trials.classify(None, chain_trials.CEILING, self.log),
            chain_trials.INVALID)
        self.assertTrue(any("could not check the stream" in m
                            for m in self.logs), self.logs)

    # --- the row: two clocks that must not wear one name -------------------

    def test_the_harness_wall_clock_survives_the_merge(self):
        # walk()'s own clock starts after the reset and Chain.load, so the two
        # differ by a minute or more. `row.update(r)` last put walk's number
        # under the harness's name and the median then mixed the two.
        r = {"seconds": 118.4, "arrived": True, "k_final": 9, "pushes": 40}
        row = chain_trials.trial_row(3, chain_trials.ARRIVED, 189.7, r)
        self.assertEqual(row["seconds"], 189.7)
        self.assertEqual(row["walk_seconds"], 118.4)
        self.assertEqual(row["trial"], 3)
        self.assertEqual(row["outcome"], chain_trials.ARRIVED)
        self.assertEqual(row["k_final"], 9)
        self.assertNotEqual(row["seconds"], r["seconds"])

    def test_a_result_may_not_overwrite_the_trial_or_the_outcome_either(self):
        row = chain_trials.trial_row(
            2, chain_trials.FAILED, 77.0,
            {"trial": 99, "outcome": "ARRIVED", "seconds": 5.0})
        self.assertEqual((row["trial"], row["outcome"], row["seconds"]),
                         (2, chain_trials.FAILED, 77.0))

    # --- the journal: a killed child still leaves its evidence --------------

    def test_a_killed_trials_rows_are_recovered_from_the_journal(self):
        d = tempfile.mkdtemp(prefix="chain_recover_")
        try:
            p = os.path.join(d, "j.jsonl")
            with open(p, "w") as fh:
                fh.write(json.dumps({"iteration": 0, "k": 0,
                                     "action": "start"}) + "\n")
                for i in (1, 2, 3):
                    fh.write(json.dumps({"iteration": i, "k": i,
                                         "action": "advanced"}) + "\n")
                fh.write('{"iteration": 4, "k": 4, "acti')   # the kill landed
            row = chain_trials.trial_row(5, chain_trials.TIMED_OUT, 580.0,
                                         None, journal=p)
            self.assertTrue(row["recovered"])
            self.assertEqual(len(row["fixes"]), 4)
            self.assertEqual(row["k_final"], 3)
            self.assertEqual(row["iterations"], 3)
            self.assertEqual(row["pushes"], 3,
                             "the pre-loop row is not a push")
            self.assertEqual(row["seconds"], 580.0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_missing_journal_is_not_an_error(self):
        row = chain_trials.trial_row(1, chain_trials.INVALID, 12.0, None,
                                     journal="/nonexistent/j.jsonl")
        self.assertEqual(row["seconds"], 12.0)
        self.assertNotIn("fixes", row)

    # --- the arithmetic the operator sees BEFORE spending ten trials -------

    def test_the_chain_is_counted_without_running_orb(self):
        d = tempfile.mkdtemp(prefix="chain_size_")
        try:
            with open(os.path.join(d, "meta.jsonl"), "w") as fh:
                fh.write('{"index": 0}\n{"index": 1}\n\n{"index": 2}\n')
            self.assertEqual(chain_trials.chain_size(d), 3)
            self.assertIsNone(chain_trials.chain_size(
                os.path.join(d, "missing")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_recorded_config_carries_every_knob_that_decides_something(self):
        # Including the end-of-chain budget, which decides when the walk gives
        # up at the last waypoint. Literals (§10.11), and a floor so the check
        # cannot pass by finding an empty dict.
        cfg = chain_trials.config()
        self.assertEqual(cfg["END_PUSH_UNITS"], 0.05)
        self.assertEqual(cfg["end_iteration_budget"], 1)
        self.assertEqual(cfg["PUSH_MAG"], 0.45)
        self.assertEqual(cfg["PUSH_SEC"], 0.40)
        for key in ("MISS_MAX", "STALL_MAX", "WINDOW", "LATERAL_GAIN",
                    "LATERAL_MAG", "LATERAL_CAP_SEC", "LATERAL_TOL_PX",
                    "TABLE_CHECK_TAIL"):
            self.assertIn(key, cfg)
        self.assertEqual(len(cfg), 12)

    def test_a_chain_name_may_not_be_a_path(self):
        # run_trial builds its temp filenames from this argument.
        for bad in ("a/b", "..", ".", "../chains/x"):
            with self.assertRaises(SystemExit):
                chain_trials.chain_dir(bad)
        self.assertEqual(chain_trials.chain_dir("route1"),
                         os.path.join(chain_trials.CHAINS, "route1"))


class EndOfChain(unittest.TestCase):
    """(k) THE LAST WAYPOINT IS A BOUNDED PHASE, NOT AN ENDLESS FORWARD WALK.

    `target_k` is clamped to n-1, so once k reaches it the loop aims at the
    waypoint it is already standing on, and `chain.reached` is then satisfied
    by any honest "I am at or past it" — on every iteration, forever. k was
    frozen, the `else` branch that owns `stalls += 1` was DEAD CODE, the escape
    ladder was structurally unreachable, and every row still said "advanced":
    §10.1's success path and no-op path with identical output.

    A skeptic measured it on a 6-waypoint chain with the prompt absent
    (agent_progress/closed-loop/verify-controller/endchain.py): 120 iterations,
    120 forward pushes, 0 escapes, 118 of 120 rows "advanced" with k frozen. At
    the shipped 400s cap that is ~400 unchecked 0.45x0.40s pushes — §6 measures
    ~70.6px each — past the end of the chain, with the module's only blockage
    handling switched off, and the timeout then read "NAVIGATION: 120
    iterations (120 advanced)" when there had been 2 advances.

    The bound comes from OPEN-22, the only measurement of how far the prompt is
    from where a goal leg stops, and NOT from a number someone liked.
    """

    def _at_end(self, n=4, **kw):
        """A chain whose locate() honestly names the LAST waypoint from the
        first look, so the terminal state is reached in one iteration."""
        rig = Rig(FakeChain(n, default=Fix(k=n - 1, scale=1.2)), table_at=None)
        return rig, rig.go(time_cap=60.0, **kw)

    def test_the_walk_gives_up_at_the_last_waypoint_rather_than_pushing_on(self):
        rig, res = self._at_end()
        self.assertFalse(res["arrived"])
        self.assertNotEqual(res["failure"], "timed out",
                            "the cap must not be what stops this")
        self.assertTrue(res["failure"].startswith("reached the last waypoint"),
                        res["failure"])
        self.assertIn("0.180 walk-units", res["failure"],
                      "the failure must say how far past the recording it went")
        # ONE terminal push — the derived budget — and then it stops. Before
        # the fix this was 120 pushes and the whole cap.
        self.assertEqual(res["pushes"], 4)
        self.assertEqual(rig.count("push"), 4)
        self.assertEqual(res["end_iterations"], 2)
        self.assertLess(res["seconds"], 10.0,
                        "it must stop long before the 60s cap")

    def test_a_frozen_k_is_never_logged_as_an_advance(self):
        _, res = self._at_end()
        self.assertEqual([r["action"] for r in res["fixes"]],
                         ["advanced", "advanced", "advanced", "stalled"])
        ks = [r["k"] for r in res["fixes"]]
        self.assertEqual(ks, [1, 2, 3, 3])
        for prev, row in zip(ks, res["fixes"][1:]):
            if row["k"] == prev:
                self.assertNotEqual(row["action"], "advanced",
                                    "a row said 'advanced' while k did not move")
        # And the journal says WHICH stall this is: at the last waypoint no
        # push can advance k, so a terminal stall and a mid-chain one need
        # different readings.
        self.assertEqual([r["at_end"] for r in res["fixes"]], [False, False, False, True])

    def test_the_escape_ladder_is_reachable_at_the_end_of_the_chain(self):
        # The branch that was dead code. With a larger end budget the terminal
        # stalls accumulate and the ladder fires exactly as it does mid-chain.
        rig, res = self._at_end(end_iterations=10)
        acts = [r["action"] for r in res["fixes"]]
        self.assertEqual(acts[0], "advanced")
        self.assertEqual([i for i, a in enumerate(acts)
                          if a.startswith("escape")], [6, 10])
        self.assertEqual([acts[6], acts[10]], ["escape:jump", "escape:back"])
        self.assertEqual(rig.count("jump"), 1)
        self.assertEqual(res["end_iterations"], 11)
        self.assertTrue(res["failure"].startswith("reached the last waypoint"),
                        res["failure"])

    def test_a_fix_past_the_end_of_the_chain_does_not_run_off_the_list(self):
        # locate() may honestly answer "past the last waypoint"; k must clamp
        # to n-1 rather than indexing off the end of waypoints[].
        rig = Rig(FakeChain(4, default=Fix(k=99, scale=2.0)), table_at=None)
        res = rig.go(time_cap=60.0)
        self.assertEqual([r["k"] for r in res["fixes"]], [1, 2, 3, 3])
        self.assertEqual(res["k_final"], 3)
        self.assertEqual([e[1] for e in rig.events if e[0] == "turn"],
                         [10.0, 20.0, 30.0],
                         "the target may never be a waypoint that does not exist")

    def test_the_end_budget_is_derived_from_the_measured_prompt_zone(self):
        # OPEN-22: at the recorded goal leg's endpoint the prompt was absent at
        # all five headings, and 0.05 walk-units FORWARD it appeared at four of
        # five. One push is PUSH_MAG * PUSH_SEC = 0.180 units, so ONE push
        # already covers 3.6x that gap. Literals, never the formula
        # re-expressed — a test that recomputes the constant it guards rises
        # with it and passes forever (§10.11).
        self.assertEqual(chain_walk.END_PUSH_UNITS, 0.05)
        self.assertEqual(chain_walk.end_iteration_budget(), 1)
        self.assertEqual(chain_walk.end_iteration_budget(units=0.5), 3)
        self.assertEqual(chain_walk.end_iteration_budget(units=0.0), 1,
                         "the budget is floored at one push, never zero")
        self.assertEqual(
            chain_walk.end_iteration_budget(push_mag=0.10, push_sec=0.10), 5)

    def test_the_walk_reports_the_end_budget_it_is_using(self):
        # A knob, because 0.05 is ONE measurement at ONE spot (three walks, one
        # of which reached the zone), and it is logged so a live run measures it.
        _, res = self._at_end()
        self.assertEqual(res["end_iteration_budget"], 1)
        _, wide = self._at_end(end_iterations=4)
        self.assertEqual(wide["end_iteration_budget"], 4)
        self.assertEqual(wide["end_iterations"], 5)
        self.assertEqual(wide["pushes"], 7)


class DefaultConsoleWrappers(unittest.TestCase):
    """(l) THE WRAPPERS THAT TURN THIS MODULE'S VOCABULARY INTO walk_leg's AXES.

    Every other test injects turn_to/push/strafe/jump/at_table through
    `Rig.go()`, so the wrapper bodies never ran at all. A skeptic inverted the
    forward push (`walk_leg(0.0, -abs(mag))` -> `+abs(mag)`, which walks the
    character BACKWARD down the chain on every push) and inverted the strafe
    axis (`walk_leg(lx, ...)` -> `-lx`, which doubles every lateral error
    instead of correcting it), and all 46 tests stayed green.

    A stub can only pin the value chain_walk hands IT. Only walk_leg's own
    (lx, ly) pins which AXIS that value lands on and with which SIGN — so these
    tests omit push=/strafe=/turn_to=/jump=/at_table= entirely and monkeypatch
    `slow_traverse.walk_leg`, `slow_traverse.turn_to`, `input_controller.press`
    and `table_prompt.at_table` instead. Nothing reaches the console: those four
    are the only functions in this module that can send anything.
    """

    def setUp(self):
        import input_controller
        import slow_traverse
        import table_prompt
        self.st, self.ic, self.tp = slow_traverse, input_controller, table_prompt
        self._saved = (slow_traverse.walk_leg, slow_traverse.turn_to,
                       input_controller.press, table_prompt.at_table)
        self.legs, self.turns, self.presses, self.tables = [], [], [], []
        self.t = [0.0]
        self.table_at = None

        def walk_leg(lx, ly, seconds, capture, read_heading, label="",
                     log=print, step_sec=None):
            self.t[0] += seconds
            self.legs.append({"lx": lx, "ly": ly, "seconds": seconds,
                              "step_sec": step_sec, "label": label})
            return seconds, 10.0, []

        def turn_to(target, read_heading, capture, log=print, **kw):
            self.t[0] += 0.5
            self.turns.append(target)
            return target, []

        def press(name, *a, **kw):
            self.presses.append(name)
            return True

        def at_table(img):
            self.tables.append(img.n)
            return self.table_at is not None and img.n >= self.table_at

        slow_traverse.walk_leg = walk_leg
        slow_traverse.turn_to = turn_to
        input_controller.press = press
        table_prompt.at_table = at_table

    def tearDown(self):
        (self.st.walk_leg, self.st.turn_to,
         self.ic.press, self.tp.at_table) = self._saved

    def _walk(self, chain, **kw):
        captures = [0]

        def capture():
            captures[0] += 1
            self.t[0] += 0.1
            return FakeImage(captures[0])

        return chain_walk.walk(chain, capture, lambda: 87.0,
                               log=lambda *a: None, now=lambda: self.t[0], **kw)

    def test_the_forward_push_reaches_walk_leg_as_ly_NEGATIVE(self):
        self.table_at = 3
        res = self._walk(FakeChain(4, [Fix(k=1, scale=1.0)],
                                   headings=[0.0, 111.0, None, 333.0]))
        self.assertTrue(res["arrived"])
        fwd = self.legs[0]
        self.assertEqual(fwd["lx"], 0.0,
                         "a forward push must not touch the strafe axis")
        self.assertLess(fwd["ly"], 0.0,
                        "walk_leg takes ly NEGATIVE as FORWARD — positive walks "
                        "the character BACKWARD down the chain")
        self.assertEqual(fwd["ly"], -chain_walk.PUSH_MAG)
        self.assertEqual(fwd["seconds"], chain_walk.PUSH_SEC)
        self.assertEqual(fwd["step_sec"], chain_walk.PUSH_SEC,
                         "step_sec == seconds is ONE continuous push; chunking "
                         "re-accelerates and walks the leg short (GRAVEYARD)")
        self.assertEqual(self.turns, [111.0],
                         "the camera goes to the TARGET waypoint's heading")
        self.assertEqual(self.tables, [1, 2, 3])

    def test_a_RIGHT_correction_reaches_walk_leg_on_the_lx_axis(self):
        self.table_at = 3
        self._walk(FakeChain(4, [Fix(k=1, scale=1.0, dx=+80.0)]))
        lat = [l for l in self.legs if l["lx"] != 0.0]
        self.assertEqual(len(lat), 1)
        self.assertEqual(lat[0]["ly"], 0.0, "a sidestep must not drive forward")
        self.assertGreater(lat[0]["lx"], 0.0,
                           "dx=+80 means the camera is LEFT of the reference, so "
                           "the correction must reach walk_leg's OWN lx POSITIVE")
        self.assertEqual(lat[0]["lx"], pose.STRAFE_MAG)

    def test_a_LEFT_correction_reaches_walk_leg_as_negative_lx(self):
        self.table_at = 3
        self._walk(FakeChain(4, [Fix(k=1, scale=1.0, dx=-80.0)]))
        lat = [l for l in self.legs if l["lx"] != 0.0]
        self.assertEqual(len(lat), 1)
        self.assertEqual(lat[0]["ly"], 0.0)
        self.assertLess(lat[0]["lx"], 0.0)
        self.assertEqual(lat[0]["lx"], -pose.STRAFE_MAG)

    def test_the_escape_presses_CROSS_and_sidesteps_on_the_same_axis(self):
        self.table_at = 30                        # no prompt until the ladder has run
        self._walk(FakeChain(12, default=None))   # long enough to be blind, then miss
        self.assertEqual(self.presses, ["cross"],
                         "Cross IS jump (§8(g)) and is the only button this "
                         "module may press")
        esc = [l["lx"] for l in self.legs if l["lx"] != 0.0]
        # Six blind, then misses: a rung every MISS_MAX misses -- jump, back,
        # left, right -- and LOST_MAX (13) ends the walk only after the fourth
        # rung's effect has been seen. Check the back rung reached walk_leg
        # with ly POSITIVE (backward on its axis) and both sidesteps landed.
        backs = [l for l in self.legs if l["ly"] > 0.0]
        self.assertEqual(len(backs), 1, "the back rung is one walk_leg with ly > 0")
        self.assertEqual([e < 0 for e in esc], [True, False], "left, then right, before lost: %r" % esc)

    def test_the_default_prompt_check_is_table_prompt_at_table(self):
        # at_table() is the arrival authority AND the $50 gate. If walk() ever
        # resolved something else by default, an arrival would mean nothing.
        self.table_at = 1
        res = self._walk(FakeChain(4, default=None))
        self.assertTrue(res["arrived"])
        self.assertEqual(self.tables, [1])
        self.assertEqual(self.legs, [],
                         "nothing may move once the prompt is on screen")


class NeverTouchesTheForbidden(unittest.TestCase):
    """The module may press exactly one button, and it is Cross.

    Read from the AST, not from the text: a source-substring scan trips over
    this module's own prose (it explains what it must never press) and would
    have to be weakened until it caught nothing.
    """

    def setUp(self):
        with open(os.path.join(_ROOT, "chain_walk.py")) as fh:
            self.tree = ast.parse(fh.read())

    def test_the_only_button_pressed_is_cross(self):
        pressed = [node.args[0].value for node in ast.walk(self.tree)
                   if isinstance(node, ast.Call)
                   and getattr(node.func, "attr", None) == "press"
                   and node.args and isinstance(node.args[0], ast.Constant)]
        self.assertEqual(pressed, ["cross"])

    def test_it_imports_nothing_that_could_reset_or_edit_the_map(self):
        mods = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.add(node.module or "")
        self.assertEqual(
            mods, {"time", "json", "math", "os", "pose", "slow_traverse",
                   "input_controller", "table_prompt"},
            "chain_walk must import nothing that resets, routes, or writes the map")


if __name__ == "__main__":
    unittest.main(verbosity=2)
