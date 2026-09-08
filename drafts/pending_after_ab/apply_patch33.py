"""TURN EARLY WHEN BLIND NEAR A TURN STOP. APPLY ONLY WHEN NO LIVE RUN IMPORTS chain_walk.

2026-09-07 22:00-22:10: three chain-walk trials in a row, both arms of an A/B,
walked into an NPC (Wanda Fuller) standing at chain waypoint ~112-114 in the
portrait room and were lost there. The user's drive (chains/route_user_1853)
walked north from 96 to 114, STOPPED, and panned the camera 1.3 -> 303.3 deg on
the spot over frames 116-129; plan_indices collapses that stationary run into
ONE turn-only stop at 129, so the plan there is pushes at 96..114 and then the
turn. Wanda stood ON the turn point. The loop's estimate stalled at k=112 with
her filling the frame, the blind budget near a stop is ONE (_blind_cap), and
after that one dead-reckoned push it sat at 112 issuing misses and escape rungs
into her. It never reached the stop, so it never turned left. The user, watching
the stream: "you walked too close to her and should have turned left. It's okay
that you got super close, you just didn't turn left enough."

THE RULE. In walk()'s blind branch, when the blind budget is spent and a
TURN-ONLY stop lies within NEAR_STOP_TARGETS plan entries of the pointer, move
the plan pointer TO that stop instead of taking the first escape rung: the next
iteration turns to the stop's heading and runs the EXISTING stop verification
unchanged. A turn moves the character NOTHING, so it costs less than any rung
and is tried before all of them. ONE per blockage, re-armed only by progress the
sensor actually saw -- "turned-unverified" and "turned-past" advance k with no
credible fit, so re-arming on them would cascade turn-early through the plan
while the character stands still.

WHAT THIS SCRIPT DOES. Two files, six edits, EVERY anchor asserted (count == 1)
BEFORE ANY FILE IS WRITTEN (CLAUDE.md §10.19 -- a sibling patch script that
asserted one file and wrote it before the next file's assert fired broke a live
run tonight). Both files are then written atomically, tmp + os.replace.

    python drafts/pending_after_ab/apply_patch33.py [ROOT]

ROOT defaults to the current working directory, so it can be verified on a
scratch copy of the tree before it is ever pointed at the checkout.
"""
import os
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
WALK = os.path.join(ROOT, "chain_walk.py")
TEST = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")

# ---------------------------------------------------------------------------
# chain_walk.py
# ---------------------------------------------------------------------------

W1_OLD = '''PROGRESS_ACTIONS = ("advanced", "relocalised", "regressed", "turned")
ESCAPE_STRAFE_MAG = 0.45
'''
W1_NEW = '''PROGRESS_ACTIONS = ("advanced", "relocalised", "regressed", "turned")
ESCAPE_STRAFE_MAG = 0.45
# ... and the two of them that carry NO evidence: both advance k at a stop that
# fitted nothing (or fitted thinly at a later waypoint), so neither is proof the
# character moved. They re-arm the escape ladder like any progress action; they
# do NOT re-arm the once-per-blockage turn-early, which would otherwise cascade
# from stop to stop while the character stands still against the same NPC.
UNEVIDENCED_ACTIONS = ("turned-unverified", "turned-past")
'''

W2_OLD = '''        if any(not push for _, push, _ in ahead):
            return 1
    return BLIND_MAX


def _fix_row(fix):'''
W2_NEW = '''        if any(not push for _, push, _ in ahead):
            return 1
    return BLIND_MAX


def _near_stop(pi, plan):
    """The plan index of a TURN-ONLY stop within NEAR_STOP_TARGETS of `pi`, or None.

    The same window `_blind_cap` uses to cut the blind budget to one push near a
    stop, read the other way round: not "is a stop close" but "which entry is
    it", so the loop can take that stop instead of an escape rung.
    """
    for j in range(pi, min(len(plan), pi + NEAR_STOP_TARGETS)):
        if not plan[j][1]:
            return j
    return None


def _fix_row(fix):'''

W3_OLD = '''    unverified_turn = False     # the last stop was accepted unverified
'''
W3_NEW = '''    unverified_turn = False     # the last stop was accepted unverified
    turned_early = False        # this blockage has already taken its early turn
'''

W4_OLD = '''        if action is not None and action.startswith(PROGRESS_ACTIONS):
            escapes = 0
        if at_end:'''
W4_NEW = '''        if action is not None and action.startswith(PROGRESS_ACTIONS):
            escapes = 0
            if action not in UNEVIDENCED_ACTIONS:
                # A turn-early is spent until the walk moves ON EVIDENCE. An
                # unverified turn is not that evidence -- it advances k at a
                # stop that fitted nothing -- so re-arming on it would let one
                # blockage turn early at stop after stop without moving.
                turned_early = False
        if at_end:'''

W5_OLD = '''            wide = None
            if blind >= 1 and not at_end:'''
W5_NEW = '''            near_stop_j = None if at_end else _near_stop(pi, plan)
            wide = None
            if blind >= 1 and not at_end:'''

W6_OLD = '''                action = "blind-advance"
            elif fix is None:
                lost += 1'''
W6_NEW = '''                action = "blind-advance"
            elif near_stop_j is not None and not turned_early:
                # TURN EARLY, RATHER THAN PUSH INTO WHATEVER IS THERE. The blind
                # budget is spent and a TURN-ONLY stop is within
                # NEAR_STOP_TARGETS plan entries: take the stop NOW instead of
                # the first escape rung. 2026-09-07 22:00-22:10, three trials in
                # a row and both arms of an A/B: an NPC stood ON the turn point
                # in the portrait room (the drive walked north to waypoint 114,
                # stopped, and panned 1.3 -> 303.3 deg, which compiles to pushes
                # at ...112, 114 then one turn-only stop at 129). The estimate
                # stalled at 112 with her filling the frame, the near-a-stop
                # blind budget is ONE, and the walk spent itself on misses and
                # rungs pushing north into her without ever reaching the turn.
                # The user, watching: "you walked too close to her and should
                # have turned left." A turn moves the character NOTHING, so it
                # costs less than any rung and comes before all of them.
                #
                # Only the POINTER moves -- k is not touched, because the rule
                # is about what to do next, not a claim about where we are. The
                # stop's own verification (turned / -aligned / -looked /
                # turn-back / -wait / -retry / -unverified / -past) is unchanged
                # and decides whether the plan really is there. ONE per
                # blockage: see UNEVIDENCED_ACTIONS.
                pi = near_stop_j
                turned_early = True
                misses = 0
                stalls = 0
                action = "turn-early"
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix), "action": action,
                        "lateral": None, "at_end": at_end,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turn-early: "
                    f"blind with the budget spent and a turn stop at "
                    f"{plan[pi][0]} within {NEAR_STOP_TARGETS} targets — turning "
                    f"to {plan[pi][2]} now instead of pushing into whatever is "
                    f"in front")
                continue
            elif fix is None:
                lost += 1'''

# ---------------------------------------------------------------------------
# tests/routing/test_chain_walk.py
# ---------------------------------------------------------------------------

T1_OLD = '''      and the sidestep on lx, with the signs pose.offset means
'''
T1_NEW = '''      and the sidestep on lx, with the signs pose.offset means
  (m) BLIND NEAR A TURN STOP TURNS EARLY, once per blockage and re-armed only
      by progress the sensor actually SAW, before any escape rung -- the NPC on
      the turn point (2026-09-07), whose whole cost was that the loop never
      reached the turn
'''

T2_OLD = '''class Escapes(unittest.TestCase):
    """(c) and (d): stalls and misses each escape, and the escapes alternate."""
'''
T2_NEW = '''class TurnEarlyWhenBlindNearAStop(unittest.TestCase):
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
'''

EDITS = [(WALK, W1_OLD, W1_NEW), (WALK, W2_OLD, W2_NEW), (WALK, W3_OLD, W3_NEW),
         (WALK, W4_OLD, W4_NEW), (WALK, W5_OLD, W5_NEW), (WALK, W6_OLD, W6_NEW),
         (TEST, T1_OLD, T1_NEW), (TEST, T2_OLD, T2_NEW)]

# --- EVERY anchor first. Nothing is written until all of them are confirmed. --
src = {}
for path in (WALK, TEST):
    if not os.path.exists(path):
        raise SystemExit(f"no such file: {path}")
    with open(path) as fh:
        src[path] = fh.read()

for path, old, new in EDITS:
    text = src[path]
    if new.strip() and new in text:
        raise SystemExit(f"ALREADY APPLIED (or a collision) in {path}: "
                         f"{new.strip()[:60]!r}")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ANCHOR COUNT {count} (want 1) in {path}: "
                         f"{old.strip()[:70]!r} — NOTHING WAS WRITTEN")

for path, old, new in EDITS:
    src[path] = src[path].replace(old, new, 1)

for name, text in (("turn-early", src[WALK]), ("turn-early", src[TEST])):
    if name not in text:
        raise SystemExit("the patched text lost its own marker — NOT WRITTEN")

for path in (WALK, TEST):
    tmp = path + ".patch33.tmp"
    with open(tmp, "w") as fh:
        fh.write(src[path])
    os.replace(tmp, path)
    print(f"patched {path}")
print("patch 33 applied: turn early when blind near a turn stop")
