"""AT THE END, TURN TOWARD THE DEALER INSTEAD OF STRAFING. APPLY ONLY WHEN NO
LIVE RUN IMPORTS chain_walk.

2026-09-07 22:00-23:20. chains/route_user_1853 ends with a turn-only stop at
index 196 (heading 89.5, east) and pushes at 197, 200, 203, 204 toward the
dealer, who sits across a table (chain frames 0196-0204 show her). The prompt
"Baseball Cards [] Play" is offered on PROXIMITY to the dealer and is
screen-fixed (OPEN-22); at_table() is checked every iteration and ends the walk
as ARRIVED the instant it is True.

Four trials verified the 196 stop and then read the dealer's scene 460 to 777 px
to the LEFT of where the reference has it (dx -777, -490, -481, -512 at 112, 52,
48, 41 inliers: overnight/chain_journals/route_user_1853_t03_1788833772.jsonl
iterations 49-59, ..._t01_1788837390.jsonl iterations 50-57, and two earlier
ones). The loop strafed LEFT at LATERAL_CAP_SEC on every one of them without the
offset shrinking, pushed along the recorded heading 89.5 into the bar counter,
and ran the plan out to 204 by count: "reached the last waypoint without the
prompt". None of the four found the prompt; the one arrival at that spot had
|dx| 286-342. The user, watching the stream: "they made it to the mini game
table but weren't close enough to get the prompt to start the game. They turned
directly into the bar and just kept getting stuck."

THE RULE. Past the LAST turn-only stop of the plan -- the final approach -- a dx
over END_TURN_PX (400) is answered with a TURN toward the scene, dx /
PX_PER_DEG degrees, capped at END_TURN_MAX_DEG (45) an iteration and
END_TURN_MAX (3) a walk, and NO strafe that iteration. The turn is kept as an
END YAW OFFSET added to every remaining heading -- otherwise the next push's
turn-to-the-recorded-heading undoes it immediately -- including the end budget's
pushes along the plan's final heading. It moves the character NOTHING, which is
the same argument that puts turn-early ahead of every escape rung and is
GRAVEYARD's summary of the only two navigation changes that ever survived.

SIGN, DERIVED FROM THE CODE RATHER THAN GUESSED. The stop look-around already
un-yaws a look with `px = dx2 + ddeg * <px per degree>`, where `ddeg` is the yaw
applied relative to `heading` (`turn_to((heading + ddeg) % 360)`). So a frame
measured at heading h + D reads `dx_at_h - D * PX_PER_DEG`, and the yaw that
puts the scene back in the middle is D = dx / PX_PER_DEG: a NEGATIVE dx (the
scene sits LEFT of where the reference has it) turns LEFT, i.e. DECREASING
heading. That agrees with pose.offset's convention (dx < 0 = scene left = camera
right). The px-per-degree value is NAMED (PX_PER_DEG) and the look-around is
switched to the name, so there is one literal and not two.

THE END TURN OBEYS THE SAME THREE GATES AS THE STRAFE IT REPLACES (2026-09-08,
after a skeptic demonstrated all three on the rig's own stubs). The first draft
of this patch spliced the rule in ABOVE the detour hold and asked only about dx,
the position and the budget. It therefore bypassed every mechanism that exists
to stop a correction acting on a dx that something else has already contested --
and each bypass was worse than the strafe it replaced, because a bad sidestep
costs one iteration while a bad end turn rides EVERY remaining heading and
spends one of only three slots:

  1. AN ITERATION THAT ESCAPED took an end turn off the PRE-escape frame:
     `escape:jump` and `turn_to(59.0)` in the same iteration, the jump's
     displacement not yet in any measurement (the strafe is gated on
     `not escaped and not escaped_prev` for exactly that reason). Now gated the
     same way, so the turn is DEFERRED to the first clean iteration, not lost.
  2. A LOOK-BACK REGRESSION left the offset riding a mid-chain heading. The
     firing test asks `pi > last_stop_j`, but the OFFSET was applied to whatever
     heading the current `pi` named, and the regression branch sets `pi = 0`: a
     recorded 0.0 was commanded as 329.5, five waypoints from the start. A
     regression is the loop saying the position that measured the dx was wrong,
     so it now CLEARS the offset -- which also covers the walk that regresses
     and then re-approaches. The BUDGET stays spent: re-arming it on a
     regression would let a regress/advance cycle turn without bound.
  3. THE DETOUR HOLD was bypassed: three escape rungs had just sidestepped LEFT
     around a blockage, and the next credible fit's +600 px -- the very side the
     hold suppresses -- turned the camera 30.5 deg back toward the obstacle, for
     the rest of the walk. The block now sits BELOW the hold, so a held dx is
     None by the time the rule looks and the row still reads `held: detour`.

WHAT IS DELIBERATELY NOT A GATE: what `turn_to` REPORTED. `slow_traverse.turn_to`
returns `(heading_now, hazards)` and says UNDERTURNED when it ran without
converging, or when the compass could not be read at all. Every call site in
walk() discards that, which is harmless for a heading the next iteration
re-commands -- turn_to is ABSOLUTE and closed-loop, so an underturn is simply
re-attempted -- but the end turn is the first site to convert it into persistent
state. Refusing the turn on a hazard is NOT the answer: §3 says the compass
abstains reliably INSIDE THE BAR, which is exactly where this rule fires, and
turn_to reports UNDERTURNED whenever it cannot read a heading -- so that gate
would switch the rule off precisely where it exists to work, §10.1's shape. This
module's own rule for an unmeasured gate is a knob defaulted off with the
QUANTITY LOGGED, never an invented constant. So the report is RECORDED on the
end-turn row (`lateral["turn"]`) and gates nothing; the next live run measures
how often it says UNDERTURNED, and that measurement is what could earn a gate.

WHAT THIS SCRIPT DOES. Two files, eleven edits, EVERY anchor asserted (count ==
1) for BOTH files BEFORE ANY FILE IS WRITTEN (CLAUDE.md §10.19 -- a sibling
patch script that asserted one file and wrote it before the next file's assert
fired broke a live run). Both files are then written atomically, tmp +
os.replace, and a second run refuses on its own output.

    python drafts/pending_after_ab/apply_patch34.py [ROOT]

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

W1_OLD = '''LATERAL_CAP_SEC = 0.3           # never lunge; a narrow passage punishes overshoot
LATERAL_TOL_PX = pose.ALIGN_TOL_PX       # 35.0 = 1.8 deg at 18.6-20.8 px/deg

TIME_CAP = 400.0                # the spec's "timed out" boundary; the harness
'''
W1_NEW = '''LATERAL_CAP_SEC = 0.3           # never lunge; a narrow passage punishes overshoot
LATERAL_TOL_PX = pose.ALIGN_TOL_PX       # 35.0 = 1.8 deg at 18.6-20.8 px/deg

# PIXELS PER DEGREE OF YAW at the live 1920-wide capture. CLAUDE.md §8(j):
# 18.6-20.8 px/deg over 7 pure camera-turn pairs with the character stationary,
# corroborated by camera_fov.json (1920 / 102 deg = 18.8). This is the value the
# stop look-around's un-yaw already used as a bare literal; it is NAMED here so
# that un-yaw and the end turn below cannot drift into two different numbers.
PX_PER_DEG = 19.7

# AT THE END, TURN TOWARD THE DEALER INSTEAD OF STRAFING.
#
# chains/route_user_1853 ends with a turn-only stop at 196 (heading 89.5) and
# pushes at 197, 200, 203, 204 toward the dealer, who sits across a table. The
# prompt is offered on PROXIMITY and is screen-fixed (OPEN-22), and at_table()
# ends the walk the instant it is True.
#
# Four trials on 2026-09-07 22:00-23:20 verified the 196 stop and then read the
# dealer's scene 460-777 px to the LEFT of where the reference has it (dx -777,
# -490, -481, -512 at 112, 52, 48, 41 inliers: the t03_1788833772 and
# t01_1788837390 journals, iterations 49-59 and 50-57, and two earlier ones).
# Every one strafed LEFT at LATERAL_CAP_SEC without the offset shrinking, pushed
# along the recorded 89.5 into the bar counter, and ran the plan out by count.
# None found the prompt. The user, watching: "they made it to the mini game
# table but weren't close enough to get the prompt ... They turned directly into
# the bar and just kept getting stuck." A person facing that turns to FACE the
# dealer and walks up to her.
#
# A 0.3 s sidestep is ~324 px at the closed-loop gain and CANNOT close 777 px
# five times over; a 39 deg turn closes it once, and a turn moves the character
# NOTHING -- the same argument that puts turn-early ahead of every escape rung,
# and GRAVEYARD's own summary that the only two navigation changes which ever
# survived move nothing.
#
# THE THRESHOLD SITS BETWEEN TWO SMALL POPULATIONS (§10.4): the one arrival at
# that spot carried |dx| 286-342, and every one of the four failures 460 or
# more. n = 4 failures and 1 arrival, so 400 is a gap between two THIN
# populations, not a calibrated gate -- it is recorded in the journal row on
# every firing so the next run measures it.
END_TURN_PX = 400.0
# The largest offset seen is 777 px = 39.4 deg, so one iteration may never turn
# further than this: a wrong match with a huge dx must not spin the camera.
END_TURN_MAX_DEG = 45.0
# ... and at most this many end turns in a walk, for the same reason. After
# three, the ordinary lateral correction takes over.
END_TURN_MAX = 3

TIME_CAP = 400.0                # the spec's "timed out" boundary; the harness
'''

W2_OLD = '''    for j in range(pi, min(len(plan), pi + NEAR_STOP_TARGETS)):
        if not plan[j][1]:
            return j
    return None


def _fix_row(fix):'''
W2_NEW = '''    for j in range(pi, min(len(plan), pi + NEAR_STOP_TARGETS)):
        if not plan[j][1]:
            return j
    return None


def _last_stop_index(plan):
    """The plan index of the LAST turn-only stop, or None if the plan has none.

    THE END TURN FIRES ONLY PAST THIS ENTRY. Past the last stop the plan is a
    straight approach and the only thing that matters is being close enough for
    the prompt, so aiming the remaining pushes at the scene is free. Before it,
    a large dx is the lateral displacement the strafe exists for, and turning
    would aim every subsequent push off the recorded line -- the "steering while
    walking" family GRAVEYARD closed. A plan with no turn-only stop at all
    returns None, and then only `at_end` opens the rule.
    """
    last = None
    for j, (_, push_target, _) in enumerate(plan):
        if not push_target:
            last = j
    return last


def _turn_report(reported):
    """What `turn_to` SAID about a turn, or None if it said nothing at all.

    `slow_traverse.turn_to` returns `(heading_now, hazards)`: no hazards when
    the camera arrived, one UNDERTURNED when the turn ran without converging or
    when the compass could not be read (`heading_now` None, and then NOTHING
    was sent). Every call site in walk() throws that away, which costs little
    for a heading the next iteration re-commands -- turn_to is ABSOLUTE and
    closed-loop, so an underturn is simply re-attempted.

    THE END TURN IS THE ONE SITE THAT MAKES IT PERSISTENT: its yaw rides every
    remaining heading and spends one of END_TURN_MAX slots, so a turn that did
    not happen would be counted as one that did. IT IS STILL NOT A GATE. §3:
    the compass abstains reliably INSIDE THE BAR, which is exactly where this
    rule fires, and turn_to reports UNDERTURNED whenever it cannot read one --
    refusing the turn on that report would switch the rule off precisely where
    it exists to work, which is §10.1's shape. This module's rule for an
    unmeasured gate is a knob defaulted off with the QUANTITY LOGGED; this is
    the quantity, and the next live run is what could earn the gate.

    A caller whose turn_to returns something else (the test rig's stub returns
    None) reports None, and the journal row is left exactly as it was.
    """
    if not isinstance(reported, tuple) or len(reported) != 2:
        return None
    now, hazards = reported
    return {"reached": None if now is None else round(float(now), 1),
            "hazards": [getattr(h, "kind", None) or str(h)
                        for h in (hazards or ())]}


def _fix_row(fix):'''

W3_OLD = '''    plan_last_heading = next((h for _, _, h in reversed(plan) if h is not None),
                             None)
'''
W3_NEW = '''    plan_last_heading = next((h for _, _, h in reversed(plan) if h is not None),
                             None)
    last_stop_j = _last_stop_index(plan)   # the end turn fires only past this
    end_yaw = 0.0               # degrees added to every remaining tail heading
    end_turns = 0               # end turns spent this walk (END_TURN_MAX)
'''

W4_OLD = '''        else:
            target_k, do_push, heading = plan[pi]

        turned = False
'''
W4_NEW = '''        else:
            target_k, do_push, heading = plan[pi]
        if end_yaw and heading is not None:
            # THE END TURN RIDES ON EVERY REMAINING HEADING, including the end
            # budget's pushes along the plan's final heading. Each target of
            # the tail carries its own recorded heading and the loop turns to
            # it before pushing, so without this the very next push would undo
            # the turn toward the dealer and the loop would walk into the bar
            # again. It accumulates across end turns. The ONE thing that clears
            # it is a look-back REGRESSION, which is the loop saying the
            # position that measured the dx was not where it thought (see the
            # `regressed` branch); short of that the walk either arrives or
            # ends, and there is nothing after the final approach to restore
            # the recorded line for.
            heading = (heading + end_yaw) % 360.0

        turned = False
'''

W5_OLD = '''            lateral = {"held": "detour", "dx": float(dx), "side": "held", "seconds": 0.0}
            dx = None
        if dx is not None and not escaped and not escaped_prev and abs(dx) > LATERAL_TOL_PX:
'''
W5_NEW = '''            lateral = {"held": "detour", "dx": float(dx), "side": "held", "seconds": 0.0}
            dx = None
        # TURN TOWARD THE SCENE INSTEAD OF STRAFING, ON THE FINAL APPROACH.
        #
        # It sits HERE, immediately above the strafe and below everything that
        # can contest a dx, because it REPLACES that strafe and must answer to
        # the same three gates -- a skeptic demonstrated all three bypasses on
        # 2026-09-08, and each was worse than the sidestep it replaced: a bad
        # sidestep costs one iteration, a bad end turn rides every remaining
        # heading and spends one of END_TURN_MAX slots.
        #
        #   - `not escaped and not escaped_prev`: an escape's jump or sidestep
        #     has moved the character since this dx was measured. The old
        #     placement fired `escape:jump` and a 30.5 deg turn off the same
        #     pre-escape frame in one iteration. Deferred, not lost: the first
        #     clean iteration still turns.
        #   - BELOW the detour hold, which sets dx to None: three rungs had
        #     just sidestepped LEFT around a blockage and the next fit's +600
        #     turned the camera back into it, permanently.
        #   - the position and budget tests below.
        #
        # dx here is what the strafe would have acted on: a credible fit's dx,
        # the CONSISTENT_N thin-fit median, or the JUNK run's. It cannot fire on
        # a turn-only target: those `continue` long before this point.
        # See END_TURN_PX for the four trials.
        if (dx is not None and abs(dx) > END_TURN_PX and heading is not None
                and not escaped and not escaped_prev
                and end_turns < END_TURN_MAX
                and not regressed
                and (at_end or (last_stop_j is not None and pi > last_stop_j))):
            # D = dx / PX_PER_DEG, from the stop look-around's own un-yaw: a
            # frame measured at heading h + D reads dx_at_h - D * PX_PER_DEG,
            # so this is the yaw that puts the scene back in the middle. A
            # NEGATIVE dx (the scene sits LEFT of where the reference has it)
            # turns LEFT, i.e. DECREASING heading -- pose.offset's convention.
            ddeg = round(max(-END_TURN_MAX_DEG,
                             min(END_TURN_MAX_DEG, float(dx) / PX_PER_DEG)), 1)
            end_yaw += ddeg
            end_turns += 1
            new_heading = (heading + ddeg) % 360.0
            said = _turn_report(turn_to(new_heading))
            last_cmd = new_heading
            lateral = {"end_turn": ddeg, "dx": float(dx),
                       "heading": new_heading, "n": end_turns}
            if said is not None:
                # WHAT THE TURN REPORTED, RECORDED AND GATING NOTHING; see
                # _turn_report for why a hazard must not refuse the turn.
                lateral["turn"] = said
            dx = None           # a turn, not a sidestep: nothing strafes here
        if dx is not None and not escaped and not escaped_prev and abs(dx) > LATERAL_TOL_PX:
'''

W6_OLD = '''        record(row)
        log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action:14s}"
            f"  fix={_fix_row(fix)}"
            + (f"  strafe {lateral['side']} {lateral['seconds']:.2f}s"
               if lateral else ""))'''
W6_NEW = '''        record(row)
        # An end turn has no `side` and no `seconds`; the old one-line format
        # would have raised KeyError on it, and padding the dict with a
        # "strafe left 0.00s" that never happened is §10.1's no-op that reads
        # as a success. It gets its own words instead.
        if lateral and "end_turn" in lateral:
            note = (f"  END TURN {lateral['end_turn']:+.1f} deg to heading "
                    f"{lateral['heading']:.1f} on dx {lateral['dx']:.0f} px "
                    f"({end_turns}/{END_TURN_MAX}) — no strafe"
                    + (f", turn_to said {lateral['turn']}"
                       if "turn" in lateral else ""))
        elif lateral:
            note = f"  strafe {lateral['side']} {lateral['seconds']:.2f}s"
        else:
            note = ""
        log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action:14s}"
            f"  fix={_fix_row(fix)}" + note)'''

W7_OLD = '''                    # Yawing LEFT by d moves the scene RIGHT in the image by
                    # ~19.7 px/deg; un-yaw it: the scene's offset from the
                    # walking heading is dx + ddeg * 19.7 (ddeg < 0 = left).
                    dx2 = getattr(f2, "dx", 0.0) or 0.0
                    px = dx2 + ddeg * 19.7'''
W7_NEW = '''                    # Yawing LEFT by d moves the scene RIGHT in the image by
                    # PX_PER_DEG; un-yaw it: the scene's offset from the walking
                    # heading is dx + ddeg * PX_PER_DEG (ddeg < 0 = left). This
                    # is the relation the END TURN inverts; ONE literal, named.
                    dx2 = getattr(f2, "dx", 0.0) or 0.0
                    px = dx2 + ddeg * PX_PER_DEG'''

W8_OLD = '''        escaped = False
        if regressed:
            misses = 0
            stalls = 0
            blind = 0
            lost = 0
            action = "regressed"
'''
W8_NEW = '''        escaped = False
        if regressed:
            misses = 0
            stalls = 0
            blind = 0
            lost = 0
            # A REGRESSION REFUTES THE END TURN'S OWN MEASUREMENT, so the yaw
            # it took goes with it. The look-back has just said the character
            # is BEHIND where the loop thought, which is the position the dx
            # that earned the turn was measured from; the regression branch
            # also rewinds the plan pointer to 0, and without this the offset
            # would ride the recorded mid-chain headings from there (a
            # demonstrated 0.0 commanded as 329.5, five waypoints from the
            # start) -- the "steering while walking" family GRAVEYARD closed.
            # The BUDGET is deliberately NOT restored: a walk that regresses
            # and re-approaches gets the turns it has left, never a fresh
            # three per regression.
            end_yaw = 0.0
            action = "regressed"
'''

# ---------------------------------------------------------------------------
# tests/routing/test_chain_walk.py
# ---------------------------------------------------------------------------

T1_OLD = '''  (m) BLIND NEAR A TURN STOP TURNS EARLY, once per blockage and re-armed only
      by progress the sensor actually SAW, before any escape rung -- the NPC on
      the turn point (2026-09-07), whose whole cost was that the loop never
      reached the turn
'''
T1_NEW = '''  (m) BLIND NEAR A TURN STOP TURNS EARLY, once per blockage and re-armed only
      by progress the sensor actually SAW, before any escape rung -- the NPC on
      the turn point (2026-09-07), whose whole cost was that the loop never
      reached the turn
  (n) PAST THE LAST STOP a huge dx is a TURN toward the dealer, not a sidestep,
      and the yaw it takes rides on every remaining heading -- the four trials
      that stood beside the table strafing at the cap against dx -460 to -777.
      It answers to every gate the strafe it replaces answers to: no end turn
      in an iteration that escaped or whose predecessor did, none on a dx the
      detour hold is suppressing, and a look-back regression drops the yaw
'''

T2_OLD = '''class TimeCap(unittest.TestCase):
    """(f) running out of time is a TIMED OUT failure, never an arrival."""
'''
T2_NEW = '''class EndTurnTowardTheDealer(unittest.TestCase):
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
'''

EDITS = [(WALK, W1_OLD, W1_NEW), (WALK, W2_OLD, W2_NEW), (WALK, W3_OLD, W3_NEW),
         (WALK, W4_OLD, W4_NEW), (WALK, W5_OLD, W5_NEW), (WALK, W6_OLD, W6_NEW),
         (WALK, W7_OLD, W7_NEW), (WALK, W8_OLD, W8_NEW),
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

# The patched text must carry its own markers, and the px-per-degree literal
# must survive as exactly ONE occurrence — the whole point of naming it.
for marker in ("END_TURN_PX", "PX_PER_DEG", "_last_stop_index", "_turn_report"):
    if marker not in src[WALK]:
        raise SystemExit(f"the patched chain_walk lost {marker} — NOT WRITTEN")
if src[WALK].count("19.7") != 1:
    raise SystemExit(f"chain_walk would hold {src[WALK].count('19.7')} copies "
                     f"of the px-per-degree literal (want 1) — NOT WRITTEN")
# THE ORDER OF THE THREE GATES IS THE FIX, so it is asserted rather than
# assumed: the end turn must sit BELOW the detour hold and ABOVE the strafe,
# and must ask about `escaped` -- a future edit that moves it back above the
# hold, or drops the escape gate, fails here before anything is written.
_hold = src[WALK].index('lateral = {"held": "detour"')
_turn = src[WALK].index("if (dx is not None and abs(dx) > END_TURN_PX")
_strafe = src[WALK].index("if dx is not None and not escaped and not "
                          "escaped_prev and abs(dx) > LATERAL_TOL_PX:")
if not _hold < _turn < _strafe:
    raise SystemExit("the end turn must sit BELOW the detour hold and ABOVE "
                     "the ordinary strafe — NOT WRITTEN")
if "and not escaped and not escaped_prev" not in src[WALK][_turn:_strafe]:
    raise SystemExit("the end turn must be gated on escaped/escaped_prev like "
                     "the strafe it replaces — NOT WRITTEN")
if "end_yaw = 0.0\n            action = \"regressed\"" not in src[WALK]:
    raise SystemExit("a regression must clear the end yaw — NOT WRITTEN")
if "EndTurnTowardTheDealer" not in src[TEST]:
    raise SystemExit("the patched test file lost its class — NOT WRITTEN")

for path in (WALK, TEST):
    tmp = path + ".patch34.tmp"
    with open(tmp, "w") as fh:
        fh.write(src[path])
    os.replace(tmp, path)
    print(f"patched {path}")
print("patch 34 applied: at the end, turn toward the dealer instead of strafing")
