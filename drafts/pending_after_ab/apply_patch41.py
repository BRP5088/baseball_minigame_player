"""patch41: at a turn stop, a THIN fit is nothing, a RETRY needs evidence of
being short, and an UNVERIFIED stop REWINDS instead of advancing.

THE EVIDENCE.

b11 trial 13 (2026-09-08 00:5x, agent_progress/closed-loop/review/
notes_cur_t13_1788843745.md). At the k=196 stop an NPC filled the frame. The
head-on fit was 13 inliers with a runner-up of 11: under FIX_MIN_INLIERS (29)
and under WEAK_MIN_INLIERS (15), so worthless -- but neither None nor tied
(11 < 0.9 * 13), and the back-off gates read exactly `fix_t is None or tied`.
turn-back and turn-wait were therefore SKIPPED, and the only remaining branch
was turn-retry: three pushes along the old walking heading carried the
character past the NPC, through a side doorway, into a stone service corridor
the chain never visits. `turned-unverified` then stamped k = 196 while the
character stood in that corridor, and the walk was lost twelve iterations
later with every escape rung fired and nothing to match.

b11 trial 12 was cited here as a second rule C case and IS NOT ONE. Its
journal (route_user_1853_t12_1788843644.jsonl rows 34-37) has the WIDE
"maybe already past" relocalisation land the estimate at 144 with 195
inliers and the very next iteration fail the k=166 stop, with no push
between -- so the last credible sighting IS where k already stands and the
rewind is a no-op by construction. It stays written down because the
mistake is the cheap one this project keeps making: a docstring claiming a
fix the code does not make, which is a stale evidence trail the moment it
reaches CLAUDE.md. See WHAT RULE C DOES NOT FIX below.

The audit's stop table (agent_progress/closed-loop/audit/stop_table.md, 43
journals): a trial that takes the bar-entrance stop 129 UNVERIFIED arrives 1
in 14, and stop 166 unverified arrives 0 in 6. Advancing on no evidence is not
a neutral default; it is the shape that loses the walk.

THE THREE RULES.

A. A THIN FIT AT A STOP IS NOTHING. The back-off gates (turn-back, turn-wait)
   ask "did anything fit". A fit under WEAK_MIN_INLIERS is not an answer --
   WEAK_MIN_INLIERS already exists for exactly this line (right-but-thin fits
   read 17-36, junk read 6-13), so no constant is invented. The 13/11 case now
   takes the step back and the wait, which is what an NPC in the face needs.
   The look-around is unchanged: it already fires on any unverified,
   not-past stop, so a thin fit always reached it.

B. A RETRY NEEDS CREDIBLE EVIDENCE OF SHORT. The retries exist for one thing
   -- the stop's frame fitting an EARLIER waypoint, i.e. the character is
   short of the stop -- and the comment above WIDE_AHEAD has said so since
   they were written ("however thinly", which is the part that was wrong).
   "Nothing fits" is an occluded view, not a distance, and pushing forward on
   it is what walked into Wanda three times (batch 4 trial 8) and through the
   doorway in trial 13. The gate now requires a fit of at least
   FIX_MIN_INLIERS naming an index BELOW the stop. Every existing gate stays
   (TURN_RETRY_MAX, early_stop, last_cred_scale < WALL_SCALE).

C. AN UNVERIFIED STOP REWINDS. When the stop's verification is exhausted with
   nothing credible, the estimate is not evidence that the character is at the
   stop -- it is evidence that nobody knows where it is. k goes BACK to the
   last credible k (the waypoint the last fit of at least FIX_MIN_INLIERS
   named, or the last relocalisation; never forward of where k already is),
   the plan pointer rewinds to 0 so it re-derives from that k -- the same
   thing the look-back regression does, and for the same reason -- and the
   loop RE-APPROACHES the stop with the machinery it already has: the wide
   search from the first blind push, the ladder on stalls, the back-off and
   the looks at the stop. The row keeps the name `turned-unverified` and
   carries `rewound_to`, so no journal loses the event.

   STOP_REWIND_MAX = 2 bounds it. A rewind moves the estimate, not
   necessarily the character, so an unbounded version could circle one stop
   forever; after two the stop is advanced unverified exactly as today, and
   LOST / STUCK / the time cap still end the walk. 2 is a LIVELOCK BOUND, not
   a measured quantity, and says so in its comment.

   AND THE BUDGET IS NEVER REFUNDED, which an earlier draft of this patch got
   wrong in a way that made STOP_REWIND_MAX no bound at all. It kept a
   (which stop, how many) PAIR and reset the count whenever the target
   changed. But a rewind can land BEFORE an earlier stop; that stop then
   fails too and resets the count, and coming back to the later stop its two
   rewinds have been handed back. Measured on a two-stop chain: 184 rows,
   **22 rewinds**, `timed out`, the whole 400 s cap spent oscillating between
   two stops with STOP_REWIND_MAX = 2 in force throughout. `rewinds_at` keys
   the count by STOP, so the pool is two per stop for the life of the walk
   and the same chain now ends in 32-38 rows with exactly two.

   THE RE-APPROACH GETS THE ORDINARY BLIND BUDGET, and an earlier draft of
   this patch did not -- it set `unverified_turn = True` on the rewind to
   hold the re-approach to END_BLIND_MAX (2) so "the three approaches
   together spend no more blind pushes than BLIND_MAX would have". That
   reading of the flag is wrong twice over. `_blind_cap` returns
   END_BLIND_MAX on it with no regard to distance, so it applies to the
   WHOLE re-approach, not the last stretch; and the flag means "the estimate
   was stamped on no evidence", which is the opposite of what a rewind
   leaves behind -- the estimate is back on the last thing the sensor
   actually saw. Demonstrated offline on a five-target run to a stop that
   never fits: the first approach crosses it on 4 blind advances under
   BLIND_MAX, the re-approach gets 2, bridges the shortfall once with the
   near-stop turn-early, and the SECOND re-approach cannot bridge it at all
   (turn-early is one-shot per blockage and every action a re-approach makes
   is unevidenced) -- miss, escape, escape, escape, escape, LOST, at a k
   BEHIND the stop, on ground the same walk had crossed twenty seconds
   earlier. A hard walk-ending failure manufactured by the fix. So the
   rewind clears the flag, and the bound on a rewind is STOP_REWIND_MAX,
   LOST, STUCK and the cap -- never a starved blind budget.

   A VERIFIED STOP IS ALSO A CREDIBLE SIGHTING. Only the push path's
   credible-fix branch and the two wide relocalisations recorded one, so a
   walk that verified stop A on a look-around and then failed at stop B
   rewound to a push fix from BEFORE A -- back past a stop it had actually
   seen, re-walking ground that was never in doubt. The acceptance now
   credits `last_cred_k = target_k`, and only at FIX_MIN_INLIERS: the
   head-on `real` path verifies from WEAK_MIN_INLIERS (15) up, which is
   thin enough to advance on and too thin to be a floor.

WHAT RULE C DOES NOT FIX, NAMED SO NOBODY READS IT INTO THE JOURNALS. The
rewind fires exactly when there is ground between the last credible sighting
and where k stands -- that is the whole content of the `rewound_k < k` guard.
Trial 13's shape has it (blind and thin pushes carried the estimate to the
stop). Trial 12's shape does not: the wide relocalisation that carried the
estimate to the stop is ITSELF the last credible sighting. Rule C leaves that
incident byte for byte as it was -- back off, wait, then take the stop
unverified -- and the no-op is right, not a hole to code around: the
alternative is falling back past a 195-inlier wide fit onto a 42-inlier one.
What trial 12 gets from this patch is rules A and B, nothing more.

Turned-past (a credible fit at a LATER index) is untouched.

Usage: python apply_patch41.py [ROOT].
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "STOP_REWIND_MAX" in c:
    raise SystemExit("ALREADY APPLIED")

edits_c = [
 # (1) the constant, beside the retry budget it bounds
 ('''# A turn stop is verified against its own frame after the turn; if nothing
# credible fits, the loop turns back, pushes once more along the walking
# heading and retries, this many times, before accepting the turn unverified.
TURN_RETRY_MAX = 3
''',
  '''# A turn stop is verified against its own frame after the turn; if nothing
# credible fits, the loop turns back, pushes once more along the walking
# heading and retries, this many times, before accepting the turn unverified.
TURN_RETRY_MAX = 3
# ... and when the verification is exhausted with nothing credible, the stop is
# NOT where the estimate is: k rewinds to the last credible waypoint and the
# loop re-approaches. A rewind moves the ESTIMATE, not necessarily the
# character, so without a bound one stop could be circled forever. After this
# many rewinds the stop is advanced unverified as it always was, and LOST,
# STUCK and the time cap still end the walk. It is spent PER STOP and NEVER
# REFUNDED (see `rewinds_at`): a counter that resets when the walk visits
# another stop is not a bound at all, and measured 22 rewinds against this 2.
# A LIVELOCK BOUND, not a measured
# quantity: two re-approaches is what a 400 s cap can afford beside the ~90 s
# an arriving trial takes, and the stop table (audit/stop_table.md) says a
# stop taken unverified arrives 1 in 14 at 129 and 0 in 6 at 166, so a third
# re-approach is worth less than the seconds it costs.
STOP_REWIND_MAX = 2
'''),
 # (2) the locals the rewind reads
 ('''    last_cred_scale = 1.0       # scale of the last CREDIBLE fit
''',
  '''    last_cred_scale = 1.0       # scale of the last CREDIBLE fit
    last_cred_k = 0             # ... and the waypoint it NAMED. Waypoint 0 is
                                # the reset spawn, trusted the way k is trusted
                                # above, so it is the floor a rewind falls to.
    rewinds_at = {}             # stop -> rewinds already spent AT THAT STOP.
                                # A dict rather than a (which stop, how many)
                                # pair, because a pair is REFUNDABLE: a rewind
                                # can land BEFORE an earlier stop, that stop
                                # then fails too, and coming back the counter
                                # has been reset by the other stop. Measured
                                # on a two-stop chain: 22 rewinds and the whole
                                # 400 s cap spent oscillating, with
                                # STOP_REWIND_MAX = 2 in force the whole time.
                                # Keyed by stop, the pool is finite -- two per
                                # stop for the life of the walk.
'''),
 # (3) a credible fix is what "last credible k" MEANS
 ('''            last_cred_scale = float(getattr(fix, "scale", 1.0) or 1.0)
''',
  '''            last_cred_scale = float(getattr(fix, "scale", 1.0) or 1.0)
            # The waypoint a CREDIBLE fit named is the rewind target. It is the
            # fit's own index, not k: k may be held back by `reached`, and what
            # a rewind wants is the last place the sensor could actually see.
            last_cred_k = min(int(fix.k), n - 1)
'''),
 # (4) a relocalisation AT A STOP is credible by construction (STRONG_MIN_INLIERS)
 ('''                if wide is not None:
                    k = min(int(wide.k), n - 1)
                    blind = 0
''',
  '''                if wide is not None:
                    k = min(int(wide.k), n - 1)
                    last_cred_k = k
                    blind = 0
'''),
 # (5) ... and so is the mid-chain one
 ('''                k = min(int(wide.k), n - 1)
                fix = wide
                weak = False
''',
  '''                k = min(int(wide.k), n - 1)
                last_cred_k = k
                fix = wide
                weak = False
'''),
 # (6) RULE A, at the turn-back gate
 ('''            if (not verified and (fix_t is None or tied) and looked is None
                    and turn_retries == 0 and not backed_here):
                backed_here = True
''',
  '''            # RULE A: A THIN FIT AT A STOP IS NOTHING. These two gates ask
            # "did anything fit at all", and a fit under WEAK_MIN_INLIERS is
            # not an answer: b11 trial 13 read 13 inliers with a runner-up of
            # 11 at the k=196 stop with an NPC filling the frame -- neither
            # None nor tied (11 < 0.9 * 13) -- so the step back and the wait
            # were both skipped and three retry pushes went through a side
            # doorway into an unmapped corridor. WEAK_MIN_INLIERS is reused
            # rather than a new constant invented: it is already the line
            # between right-but-thin (17-36) and junk (6-13).
            nothing_t = fix_t is None or tied or inl_t < WEAK_MIN_INLIERS
            if (not verified and nothing_t and looked is None
                    and turn_retries == 0 and not backed_here):
                backed_here = True
'''),
 # (7) RULE A, at the turn-wait gate
 ('''            if (not verified and (fix_t is None or tied) and looked is None
                    and turn_retries == 0 and not waited_here):
                waited_here = True
''',
  '''            if (not verified and nothing_t and looked is None
                    and turn_retries == 0 and not waited_here):
                waited_here = True
'''),
 # (8) RULE B, at the retry gate
 ('''            if (not verified and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None and not early_stop
                    and last_cred_scale < WALL_SCALE):
                turn_retries += 1
''',
  '''            # RULE B: and it needs EVIDENCE OF BEING SHORT, which is the
            # stop's frame fitting an EARLIER waypoint CREDIBLY. A thin fit is
            # not that evidence and neither is silence; both mean "I cannot
            # see", and a push forward on "I cannot see" is how trial 13 left
            # the room. locate() bounds its answer to [stop-1, stop+3], so
            # `kt < target_k` is the whole of the short case.
            short_ev = (fix_t is not None and inl_t >= FIX_MIN_INLIERS
                        and kt is not None and kt < target_k)
            if (not verified and short_ev and turn_retries < TURN_RETRY_MAX
                    and walk_heading is not None and not early_stop
                    and last_cred_scale < WALL_SCALE):
                turn_retries += 1
'''),
 # (9) RULE C: the unverified acceptance rewinds first
 ('''            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            waited_here = False
            backed_here = False
            early_stop = False
            unverified_turn = not verified
            action = "turned" if verified else "turned-unverified"
''',
  '''            if not verified:
                # RULE C: AN UNVERIFIED STOP REWINDS. Nothing credible fitted
                # here, so "I am at the stop" is not a reading -- it is the
                # plan talking. Stamping k = target_k there put trial 13's
                # estimate at the dealer's table while the character stood in
                # a service corridor, and the stop table (audit/stop_table.md)
                # says a stop taken unverified arrives 1 in 14 at 129 and 0 in
                # 6 at 166. Go BACK to the last credible waypoint, rewind the
                # plan pointer so it re-derives from there -- the same thing
                # the look-back regression does, and for the same reason --
                # and let the ordinary machinery re-approach: the wide search
                # from the first blind push, the ladder on stalls, the
                # back-off and the looks here.
                #
                # min(), so a rewind never moves the estimate FORWARD: a
                # look-back regression may already have put k behind the last
                # credible fit, and that regression is the better evidence.
                #
                # `rewound_k < k` is the no-op guard, and it is also the
                # honest statement of WHEN THIS RULE APPLIES: only when there
                # is ground between the last credible sighting and where k
                # stands. When the last credible fit IS where k already stands
                # there is nothing to re-approach -- the pointer would
                # re-derive to this same stop and the loop would repeat this
                # iteration, spending a rewind and a stop cycle to change
                # nothing (CLAUDE.md 10.1's no-op path that logs like an
                # action) -- so the stop is advanced unverified exactly as
                # before. b11 trial 12 is that case and is NOT fixed here: its
                # wide relocalisation to 144 (195 inliers) is itself the last
                # credible sighting, and the alternative would be falling back
                # past it onto a 42-inlier fit. Trial 13 is the case that IS
                # fixed: blind and thin pushes carried its estimate to the
                # stop, so there is real ground to re-walk.
                #
                # `blind = 0` and `unverified_turn = False` because the
                # estimate is back on the last thing the SENSOR SAW, which is
                # the opposite of the unverified stamp that flag means -- and
                # `_blind_cap` reads it with no regard to distance, so setting
                # it here would hold the WHOLE re-approach to END_BLIND_MAX
                # (2). A five-target run to a stop that never fits then
                # crosses on 4 blind advances the first time, gets 2 on the
                # re-approach, bridges once with the near-stop turn-early
                # (one-shot per blockage, and every action a re-approach makes
                # is unevidenced so it never re-arms), and the second
                # re-approach goes miss/escape/LOST at a k BEHIND the stop --
                # a walk-ending failure on ground it had just crossed. The
                # bound on a rewind is STOP_REWIND_MAX, LOST, STUCK and the
                # cap. `lost` is NOT reset: a walk that cannot see must still
                # end.
                rewound_k = min(last_cred_k, k)
                if rewinds_at.get(target_k, 0) < STOP_REWIND_MAX and rewound_k < k:
                    rewinds_at[target_k] = rewinds_at.get(target_k, 0) + 1
                    k = rewound_k
                    pi = 0
                    blind = 0
                    misses = 0
                    stalls = 0
                    turn_retries = 0
                    waited_here = False
                    backed_here = False
                    early_stop = False
                    unverified_turn = False
                    action = "turned-unverified"
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(fix_t), "action": action,
                            "lateral": None, "rewound_to": k, "at_end": False,
                            "seconds": round(now() - it_t0, 2),
                            "elapsed": round(now() - t0, 2)})
                    log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                        f"{action}: nothing credible fitted the stop — REWOUND "
                        f"to {k} (rewind {rewinds_at[target_k]}"
                        f"/{STOP_REWIND_MAX} at this stop) "
                        f"rather than claiming the stop")
                    continue
            k = target_k
            misses = 0
            stalls = 0
            turn_retries = 0
            waited_here = False
            backed_here = False
            early_stop = False
            unverified_turn = not verified
            if verified and inl_t >= FIX_MIN_INLIERS:
                # A VERIFIED STOP IS A CREDIBLE SIGHTING, and nothing recorded
                # it as one: `last_cred_k` was written only by the push path's
                # credible-fix branch and the two wide relocalisations. So a
                # walk that verified stop A on a look-around and then failed
                # at stop B rewound to a push fix from BEFORE A, re-walking
                # ground that was never in doubt and crossing back through
                # whatever is between them. FIX_MIN_INLIERS, not `verified`
                # alone: the head-on `real` path verifies from
                # WEAK_MIN_INLIERS (15) up, thin enough to advance on and too
                # thin to be the floor a later rewind falls to. The pan path
                # matched an index inside this stop\'s own stationary run,
                # where the character does not move, so target_k is the right
                # credit for all three.
                last_cred_k = target_k
            action = "turned" if verified else "turned-unverified"
'''),
]

edits_t = [
 # ---- (T1) the short-evidence retry test: the fit it hands the stop was 8
 # inliers, which rule B no longer accepts. It becomes a CREDIBLE tie.
 ('''    def test_a_turn_stop_that_does_not_match_is_retried_after_one_more_push(self):
        # Chain: spawn, 2 walking frames east (90), a stop turning to 0, then
        # walking north. The first time the loop reaches the stop its frame
        # does not fit (weak): it turns BACK to 90, pushes once, then retries
        # the stop; the second time it fits and the plan proceeds north.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, -0.35), (0.0, 0.0),
                                     (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        self.assertEqual(chain_walk.plan_indices(wps),
                         [(1, True, 90.0), (3, False, 0.0), (4, True, 0.0), (5, True, 0.0)])
        # locate calls in order: it1 push -> Fix(k=1); it2 turn-verify -> a thin
        # fit to the EARLIER waypoint 2 (evidence of being short); it3 (after
        # the retry push) turn-verify -> credible; it4 push -> Fix(4)
        # the two look-around locates at the stop see nothing (None, None)
        ch = FakeChain(6, [Fix(k=1), Fix(k=2, inliers=8), None, None, Fix(k=3, inliers=90),
                           Fix(k=4), Fix(k=5)])
        ch.waypoints = wps
        rig = Rig(ch, table_at=8)   # the looks add two captures
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:4], ["advanced", "turn-retry", "turned", "advanced"])
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns, [90.0, 0.0, 335.0, 25.0, 0.0, 90.0, 0.0],
                         "turn to the stop, look left and right, back to the stop, back to "
                         "the walking heading for the retry push, then the stop again")
        self.assertEqual(rig.chain.locate_calls[1:3], [3, 3],
                         "the stop is verified against its OWN index")
        self.assertTrue(res["arrived"])
''',
  '''    def test_a_turn_stop_that_does_not_match_is_retried_after_one_more_push(self):
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
'''),
 # ---- (T2) the "accepted unverified after the retries" test becomes the
 # STOP_REWIND_MAX test: both of its halves were changed by rules B and C.
 ('''    def test_a_turn_stop_is_accepted_unverified_after_the_retries(self):
        # Every verify fits an EARLIER waypoint thinly: three retries, then
        # the turn is accepted unverified.
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(4, [Fix(k=1)], default=Fix(k=1, inliers=9))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=14.05)   # each retry now also looks left and right
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "turn-retry", "turn-retry", "turn-retry", "turned-unverified"])
        self.assertEqual(chain_walk.TURN_RETRY_MAX, 3)
''',
  '''    def test_a_stop_is_advanced_unverified_only_after_STOP_REWIND_MAX_rewinds(self):
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
'''),
 # ---- (T3) the wall-scale test needs a fit that WOULD earn a retry, or the
 # clause it guards is no longer what suppresses one.
 ('''        ch = FakeChain(4, [Fix(k=1, scale=2.9, inliers=90)], default=Fix(k=1, inliers=9))
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = always_turning(rig.go, time_cap=14.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertNotIn("turn-retry", acts, acts)
        self.assertEqual(acts[:2], ["advanced", "turned-unverified"], acts)
''',
  '''        # THE FIT AT THE STOP CHANGED (patch41). It used to be a 9-inlier
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
'''),
 # ---- (T4) the junk-fit test: its claim is unchanged, its action is not
 ('''        # head-on a 9-inlier fit at 4 (junk), looks None -> retry, then credible
        ch = FakeChain(5, [Fix(k=1), Fix(k=4, inliers=9), None, None, Fix(k=3, inliers=90), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=8)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1], "turn-retry")
''',
  '''        # head-on a 9-inlier fit at 4 (junk), looks None. patch41: it is no
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
'''),
 # ---- (T5) the blind-cap test: same subject, no retries in the way
 ('''        res = always_turning(rig.go, time_cap=32.05)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[1:3], ["turn-back", "turn-wait"])
        self.assertEqual(acts[3:6], ["turn-retry"] * 3)
        self.assertEqual(acts[6], "turned-unverified")
        self.assertEqual(acts[7:9], ["blind-advance"] * 2)
        self.assertEqual(acts[9], "miss", "an unverified turn allows two blind pushes, not six")
''',
  '''        res = always_turning(rig.go, time_cap=32.05)
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
'''),
 # ---- (T6) the three new tests
 ('''    def test_a_real_fit_at_the_stop_with_a_large_offset_strafes_toward_the_scene(self):
''',
  '''    def test_a_thin_fit_at_a_stop_is_nothing_and_never_pushes_forward(self):
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
'''),
]

for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", a.split("\n")[0][:70], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a.split("\n")[0][:70], t.count(a))
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
open(C, "w").write(c); open(T, "w").write(t); print("patch41 applied to", ROOT)
