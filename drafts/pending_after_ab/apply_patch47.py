"""patch47: DOOR_STOP_EXTRA_PUSH -- one more step toward the door before the
office-door / top-of-the-stairs turn stop. Ships OFF; the A/B decides.

THE USER, watching the live stream during batch 23 (2026-09-08 09:50,
verbatim):

    "an observation, you should take 1 more step towards the door in the
    beginning of the route. saves you from rubbing against the banister."

THE CENSUS AGREES, and it is the instrument the A/B reads
(agent_progress/closed-loop/review/census_after_129_notes.md, 226 walks since
batch 16). At the turn-only stop at chain 39 the VERIFYING FIT'S SCALE says
where the character stands when it turns:

    39 verified head-on (turned / turned-aligned, 195):  scale median 1.03-1.04, dy ~300;  20 failed (10%)
    39 verified by the LOOK-AROUND (31):                 scale median 0.87-0.88, dy ~236;   9 failed (29%)
    39 unverified (2):                                   scale 0.78-0.79;                   2 failed

Scale under 1 is the scene SMALLER than the reference, i.e. the character
SHORT of the door when it turns -- and the office corridor (chain k 4-19) is
blind for the sensor on every walk: the last credible fit is at k 4-10 and the
pushes to 13, 16 and 19 are dead-reckoned, so nothing in the loop can notice.
The stairs losses of batches 17-23 all begin from that short position (b17 t9,
b18 t14, b19 t17: the look ties at ~31-34 inliers, the un-yaw goes left into
the bannister alcove or into the mouse NPC beside the newel post).

WHAT THIS ADDS: one more push along the WALKING heading, before the stop's
turn, at the same PUSH_MAG and PUSH_SEC as every other push -- no new physical
constant, no new geometry, and the stop's own verification is untouched. It
MOVES THE CHARACTER, which is the shape GRAVEYARD says has failed thirteen
times out of thirteen, so it ships OFF behind a flag and the A/B decides:

    overnight/chain_trials.py ... --arms off,on --flag DOOR_STOP_EXTRA_PUSH

with a per-trial instrument besides arrival: the fit scale of the 39 stop's
verifying fit (0.87 on the looked stops today; ~1.0 if the user is right).

Apply:  .venv/bin/python -B drafts/pending_after_ab/apply_patch47.py [ROOT]
Refuses a second run. All anchors are asserted BEFORE any file is written.
"""
import ast, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read()
t = open(T).read()

if "DOOR_STOP_EXTRA_PUSH" in c or "DOOR_STOP_EXTRA_PUSH" in t:
    raise SystemExit("ALREADY APPLIED")

# --------------------------------------------------------------------------
# chain_walk.py
# --------------------------------------------------------------------------

CONST_ANCHOR = "STOP_TIE_DX_PX = 120.0\n"

CONST_NEW = CONST_ANCHOR + '''# ONE MORE STEP TOWARD THE DOOR BEFORE THE OFFICE-DOOR STOP TURNS (ships OFF;
# the A/B decides).
#
# THE USER, watching the live stream during batch 23 (2026-09-08 09:50,
# verbatim): "an observation, you should take 1 more step towards the door in
# the beginning of the route. saves you from rubbing against the banister."
#
# THE STOP'S OWN FIT SCALE SAYS THE SAME THING, and it is this rule's
# instrument (agent_progress/closed-loop/review/census_after_129_notes.md,
# 226 walks since batch 16):
#     39 verified head-on (195 walks)      scale median 1.03-1.04   10% failed
#     39 verified by the LOOK-AROUND (31)  scale median 0.87-0.88   29% failed
#     39 unverified (2)                    scale 0.78-0.79          both failed
# Scale under 1 is the scene SMALLER than the reference: the character SHORT
# of the door when it turns. The corridor is blind for the sensor on every
# walk -- the last credible fit is at chain 4-10 and the pushes to 13, 16 and
# 19 are dead-reckoned -- so nothing in the loop can notice, and the stairs
# losses of batches 17-23 all begin from that short position (the turn goes
# into the bannister alcove, or into the mouse NPC beside the newel post).
#
# HOW FAR ONE PUSH IS, READ OFF THE CHAIN ITSELF rather than chosen: the
# corridor's push targets are 10, 13, 16 and 19, one PLAN_STEP_UNITS apart,
# and the 39 stop's own stationary run spans waypoints 21..39 (the human
# standing still and turning). So one more PUSH_MAG x PUSH_SEC push carries
# the character about three recorded frames -- from waypoint 19's spot INTO
# the span the recording turned in, not past it.
#
# WHAT IT CANNOT DO, said plainly: the step is taken BEFORE the stop's turn,
# so it cannot be conditioned on the stop's fit -- that fit is only measured
# after the turn, and the 195 head-on walks that already stand at scale 1.03
# get the step too. Gating on the scale would need a number inside a
# population the loop cannot read until it is too late to act on it (10.4).
# That cost is exactly what the A/B weighs, and the `door-step` row carries
# the fit taken right after the push, so the on arm's own rows say whether it
# overshoots rather than leaving it to be argued about.
#
# It MOVES THE CHARACTER, which is the shape GRAVEYARD closed thirteen times
# out of thirteen (both survivors move nothing), so it ships OFF and an A/B
# decides: `--arms off,on --flag DOOR_STOP_EXTRA_PUSH`.
DOOR_STOP_EXTRA_PUSH = False
# THE STOP IT APPLIES TO, AND IT IS CHAIN-SPECIFIC: 39 is the office-door /
# top-of-the-stairs turn-only stop of chains/route_user_1853, the drive every
# batch walks. It is an index into THAT recording and not a property of the
# world -- another chain's door stop is another number, and a chain with no
# stop there leaves the rule dormant, because no plan entry ever equals it.
DOOR_STOP_INDEX = 39
# How many extra pushes. ONE, because one step is what the user asked for.
DOOR_STOP_EXTRA_PUSHES = 1
'''

INIT_ANCHOR = ("    walk_heading = None         # the last heading a push was made along\n"
               "    last_cmd = None             # the last heading actually commanded\n")

INIT_NEW = INIT_ANCHOR + (
    "    door_stepped = False        # this SERVICING of DOOR_STOP_INDEX has had\n"
    "                                # its extra push (DOOR_STOP_EXTRA_PUSH)\n")

STEP_ANCHOR = "        turned = False\n        if heading is not None and (\n"

STEP_NEW = '''        # ONE MORE STEP TOWARD THE DOOR (DOOR_STOP_EXTRA_PUSH), BEFORE THE
        # TURN AND NOT AFTER. The point is to reach the stop and turn THERE:
        # the user watched the loop turn short and rub along the banister, and
        # the stop's verifying fit scale of 0.87 on the looked stops measures
        # the same thing. A push taken AFTER the turn would run along the
        # STOP'S heading -- into the stairs -- which is the opposite change.
        #
        # ONCE PER SERVICING. A turn-back, a turn-wait and a turn-retry all
        # come round the loop to this same plan entry, and that is the same
        # stop, not a second step; `door_stepped` is cleared only by an
        # iteration that services something else, so a re-approach after a
        # rescue or a look-back regression -- which walks other targets to get
        # back here -- takes the step again, deliberately. A stop the plan
        # SKIPS (a wide relocalisation carrying k past it) is never unpacked
        # as `plan[pi]` at all, so this cannot fire on one.
        #
        # Nothing else changes: the push is the ordinary PUSH_MAG/PUSH_SEC one
        # along the heading the walk arrived on, its frame is captured and
        # recorded as evidence, and the stop is then turned to and verified
        # exactly as before. The row is evidence only -- it moves no counter,
        # spends no blind budget and gates nothing.
        servicing_door_stop = not do_push and target_k == DOOR_STOP_INDEX
        if not servicing_door_stop:
            door_stepped = False
        elif (DOOR_STOP_EXTRA_PUSH and not door_stepped
                and walk_heading is not None):
            door_stepped = True
            for step_i in range(1, max(1, int(DOOR_STOP_EXTRA_PUSHES)) + 1):
                if (last_cmd is None
                        or abs((walk_heading - last_cmd + 540.0) % 360.0 - 180.0)
                        > TURN_SKIP_DEG):
                    turn_to(walk_heading)
                    last_cmd = walk_heading
                push(PUSH_MAG, PUSH_SEC)
                res["pushes"] += 1
                img_d = capture()
                _save(shots, iteration, k, img_d, log, suffix=f"_door{step_i}")
                fix_d = chain.locate(img_d, target_k)
                inl_d = 0 if fix_d is None else (getattr(fix_d, "inliers", 0) or 0)
                sc_d = None if fix_d is None else getattr(fix_d, "scale", None)
                sc_d = None if sc_d is None else round(float(sc_d), 2)
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_d), "action": "door-step",
                        "lateral": None,
                        "door_step": {"n": step_i,
                                      "heading": round(walk_heading, 1)},
                        "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"door-step {step_i}/{DOOR_STOP_EXTRA_PUSHES}: one more "
                    f"push along {walk_heading:.1f} before the stop turns "
                    f"(the frame after it fits {inl_d} inliers, scale {sc_d})")

''' + STEP_ANCHOR

# --------------------------------------------------------------------------
# tests/routing/test_chain_walk.py
# --------------------------------------------------------------------------

TEST_ANCHOR = "class NeverTouchesTheForbidden(unittest.TestCase):\n"

TEST_NEW = '''class DoorStopExtraPush(unittest.TestCase):
    """(o) ONE MORE STEP TOWARD THE DOOR before the office-door stop turns.

    The user, watching the live stream during batch 23 (2026-09-08, verbatim):
    "an observation, you should take 1 more step towards the door in the
    beginning of the route. saves you from rubbing against the banister."

    The census says the same thing (agent_progress/closed-loop/review/
    census_after_129_notes.md, 226 walks): the chain-39 stop verified head-on
    fits at scale 1.03 and fails 10% of the time; verified only by the
    look-around it fits at 0.87 -- the scene 13% smaller than the reference,
    i.e. the character SHORT of the door -- and fails 29%. The corridor is
    blind for the sensor (last credible fit at k 4-10; 13/16/19 dead-reckoned),
    so the loop cannot see that it stopped short.

    The flag ships OFF and the A/B decides, so these tests drive it BOTH ways
    and pin the OFF path's console events as literals: a mutant that ignores
    the flag must fail here.

    THE CHAIN. wp2 is the turn-only stop (ly = 0.0, a stationary run of one),
    reached after one walking push at 90 deg; the pushes after it carry 10 deg,
    so every turn shows up in the event list as its own entry.
    """

    ROWS = [(90.0, -0.35), (0.0, 0.0), (10.0, -0.35), (10.0, -0.35)]

    def _wps(self, rows=None):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate(rows or self.ROWS, start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        return wps

    def _rig(self, wps, fixes, table_at, wide=None, lookback="script"):
        ch = FakeChain(len(wps), fixes, default=None, wide=wide,
                       lookback=lookback)
        ch.waypoints = wps
        return Rig(ch, table_at=table_at)

    def _at(self, index):
        """Point the rule at THIS chain's stop, restored afterwards."""
        prev = chain_walk.DOOR_STOP_INDEX
        chain_walk.DOOR_STOP_INDEX = index
        self.addCleanup(setattr, chain_walk, "DOOR_STOP_INDEX", prev)

    def _flag(self, on):
        prev = chain_walk.DOOR_STOP_EXTRA_PUSH
        chain_walk.DOOR_STOP_EXTRA_PUSH = on
        self.addCleanup(setattr, chain_walk, "DOOR_STOP_EXTRA_PUSH", prev)

    # ---- the constants -----------------------------------------------------

    def test_the_flag_ships_OFF_and_the_index_is_this_chains_door_stop(self):
        # Literals (10.11): a test that reads the constant it guards passes
        # forever. 39 is chains/route_user_1853's office-door stop and ONE
        # push is what the user asked for.
        self.assertIs(chain_walk.DOOR_STOP_EXTRA_PUSH, False)
        self.assertEqual(chain_walk.DOOR_STOP_INDEX, 39)
        self.assertEqual(chain_walk.DOOR_STOP_EXTRA_PUSHES, 1)
        # It invents no physical constant: the push is the ordinary one.
        self.assertEqual(chain_walk.PUSH_MAG, 0.45)
        self.assertEqual(chain_walk.PUSH_SEC, 0.40)

    def test_the_plan_this_class_uses_has_its_stop_where_it_says(self):
        # ANTI-VACUITY for every test below: if the plan had no turn-only
        # target at 2, "no extra push" would pass for the wrong reason.
        self.assertEqual(chain_walk.plan_indices(self._wps()),
                         [(1, True, 90.0), (2, False, 0.0), (3, True, 10.0),
                          (4, True, 10.0)])

    # ---- the OFF path, pinned as literals ----------------------------------

    def test_with_the_flag_OFF_the_console_sequence_is_UNCHANGED(self):
        # THE CONTROL, and the shipped path. Every console call, in order.
        self._flag(False)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=200)], table_at=4)
        res = rig.go()
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("turn", 0.0), ("capture", 3), ("at_table", 3, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 4), ("at_table", 4, True)])
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["advanced", "turned", "arrived"])
        self.assertEqual(res["pushes"], 2)
        self.assertTrue(res["arrived"])

    # ---- the ON path -------------------------------------------------------

    def test_the_extra_push_comes_BEFORE_the_stops_turn_and_only_once(self):
        # The same walk with the flag on: ONE more push, along the WALKING
        # heading (90, already commanded, so no turn of its own), before the
        # turn to the stop's 0.0 -- and the stop then verifies exactly as it
        # did with the flag off.
        self._flag(True)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                         Fix(k=2, inliers=200)], table_at=5)
        res = rig.go()
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("push", 0.45, 0.4), ("capture", 3),          # THE DOOR STEP
            ("turn", 0.0), ("capture", 4), ("at_table", 4, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 5), ("at_table", 5, True)])
        pushes = [i for i, e in enumerate(rig.events) if e[0] == "push"]
        turn0 = next(i for i, e in enumerate(rig.events)
                     if e[0] == "turn" and e[1] == 0.0)
        self.assertEqual(len([i for i in pushes if i < turn0]), 2,
                         "the walking push and the door step, both before the "
                         "stop's turn")
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["advanced", "door-step", "turned", "arrived"])
        self.assertEqual(res["pushes"], 3, "the door step counts as a push")
        self.assertTrue(res["arrived"])

    def test_the_door_step_row_carries_its_own_fix_and_says_which_push_it_was(self):
        # The row is EVIDENCE: the fit after the extra push is what the A/B's
        # instrument (the stop's fit scale) is read from, so it is recorded
        # rather than thrown away (10.1, "a measurement taken and discarded").
        self._flag(True)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                         Fix(k=2, inliers=200)], table_at=5)
        res = rig.go()
        row = res["fixes"][1]
        self.assertEqual(row["action"], "door-step")
        self.assertEqual(row["k"], 1, "k is untouched by the extra push")
        self.assertEqual(row["target"], 2)
        self.assertIsNone(row["lateral"])
        self.assertEqual(row["door_step"], {"n": 1, "heading": 90.0})
        self.assertEqual(row["fix"]["inliers"], 90)
        self.assertEqual(row["fix"]["scale"], 0.87)
        self.assertEqual(rig.chain.locate_calls[1], 2,
                         "the door step's frame is located against the STOP, "
                         "which is the scene it was pushed toward")
        self.assertEqual(rig.strafes(), [], "it steers nothing")

    def test_a_stop_that_is_not_the_DOOR_STOP_gets_no_extra_push(self):
        # THE MUTANT THIS EXISTS FOR: a rule that fires at every stop. With
        # the flag ON and the index pointing somewhere this chain never
        # reaches, the sequence is the OFF one, call for call.
        self._flag(True)
        self._at(7)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=200)], table_at=4)
        res = rig.go()
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("turn", 0.0), ("capture", 3), ("at_table", 3, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 4), ("at_table", 4, True)])
        self.assertNotIn("door-step", [f["action"] for f in res["fixes"]])
        self.assertEqual(res["pushes"], 2)

    def test_one_door_step_per_SERVICING_however_often_the_stop_comes_round(self):
        # A stop whose frame fits nothing is served again and again -- one step
        # back, one wait, then a retry push -- and every one of those returns
        # to this same plan entry. That is the SAME stop, not four more steps.
        self._flag(True)
        self._at(2)
        wps = self._wps([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)])

        def tied_at(k):
            # Credible, and NOT verification: a near-tied runner-up at another
            # place whose dx disagrees. The one shape that buys a retry (see
            # test_a_turn_stop_that_does_not_match_is_retried_after_one_more_push).
            f = Fix(k=k, inliers=90, second=90)
            f.second_k, f.second_dx = 8, 900.0
            return f

        # it1 push -> Fix(1); the door step's own frame; then the stop reads a
        # credible TIE at the EARLIER waypoint 1 three times, with both looks
        # blank each time (back, wait, retry), and the fourth read verifies.
        rig = self._rig(wps, [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                              tied_at(1), None, None,   # stop + both looks
                              tied_at(1), None, None,   # ... after the step back
                              tied_at(1), None, None,   # ... after the wait
                              Fix(k=2, inliers=200)], table_at=99,
                        lookback=None)
        res = without_stuck(rig.go, time_cap=60.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "door-step", "turn-back",
                                    "turn-wait", "turn-retry"], acts)
        self.assertEqual(acts.count("door-step"), 1,
                         "one servicing of the stop, one step toward the door")
        self.assertIn("turned", acts, "ANTI-VACUITY: the stop was serviced "
                                      "four times and did verify in the end")

    def test_a_stop_SKIPPED_by_a_relocalisation_takes_no_step(self):
        # The pointer walks over a turn-only entry when a wide relocalisation
        # carries k past it: no turn_to, no push, no stop. The step must not
        # fire for a stop the walk never serviced.
        self._flag(True)
        self._at(5)
        rows = [(90.0, -0.35)] * 4 + [(0.0, 0.0)] + [(10.0, -0.35)] * 3
        wps = self._wps(rows)
        self.assertEqual([p for p in chain_walk.plan_indices(wps) if not p[1]],
                         [(5, False, 0.0)], "the stop is at 5")
        rig = self._rig(wps, [], table_at=4,
                        wide=Fix(k=7, inliers=170, second=20))
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["blind-advance", "relocalised"], acts)
        self.assertNotIn("door-step", acts)
        self.assertEqual([f["k"] for f in res["fixes"]][1], 7,
                         "ANTI-VACUITY: k really did jump past the stop at 5")


'''

# --------------------------------------------------------------------------
# assert EVERY anchor, exactly once, BEFORE any write (10.19)
# --------------------------------------------------------------------------
for name, hay, anchor in (("chain_walk CONST", c, CONST_ANCHOR),
                          ("chain_walk INIT", c, INIT_ANCHOR),
                          ("chain_walk STEP", c, STEP_ANCHOR),
                          ("test ANCHOR", t, TEST_ANCHOR)):
    n = hay.count(anchor)
    assert n == 1, (name, repr(anchor[:60]), n)

c = c.replace(CONST_ANCHOR, CONST_NEW)
c = c.replace(INIT_ANCHOR, INIT_NEW)
c = c.replace(STEP_ANCHOR, STEP_NEW)
t = t.replace(TEST_ANCHOR, TEST_NEW + TEST_ANCHOR)

ast.parse(c)
ast.parse(t)
open(C, "w").write(c)
open(T, "w").write(t)
print("patch47 applied to", ROOT)
