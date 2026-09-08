"""patch37: a stop TIE needs SEPARATION, and a strong look ends the look-around.

RULE 1. `STOP_TIE_FRAC` rejected a head-on stop verification whenever the
runner-up's inlier count was within 90% of the winner's. At a turn-only target
the runner-up IS the adjacent frame of the stationary run the target collapses
-- near-duplicates of one spot, 0.25 s apart -- so that ratio is 0.92-0.96
there BY CONSTRUCTION. Replaying 37 saved stop frames through chain.locate
(agent_progress/closed-loop/stop_tie/replay_stops.py -> replay_stops.json)
shows every one of the six stops of the four FASTEST arrivals ever recorded
would be called a tie today, though each verified head-on in 0.1-4.2 s at the
time; the rule-cost study attributes two thirds of the +34 s per arrival that
followed to this (agent_progress/closed-loop/rule_costs/notes.md).

So a tie now needs the two candidates to be TWO PLACES, on both axes the fit
offers at once: their indices not both inside the stop's own stationary-run
SPAN, and their dx disagreeing by more than STOP_TIE_DX_PX. chain.Fix gains
`second_k` and `second_dx` (optional, with defaults, so every existing caller
and test keeps working) because `second` alone answers neither question.

BOTH INDICES ARE TESTED, WHICH IS WHAT KEEPS THE RULE'S OWN MOTIVATING FRAME.
A first draft asked only "is the RUNNER-UP outside the span" -- and batch 5e
trial 6, the frame this constant exists for, is the mirror of that shape: its
WINNER sits at waypoint 132, past the stop's span 116..129, while the near-tied
runner-up at 128 IS the stop's own frame. Runner-up-only called that "not a
tie", verified the stop and strafed 0.54 s LEFT on the winner's dx of -386 px:
it trusted the candidate past the stop, which is the failure in the bug report.
Two indices inside one span are one spot 0.25 s apart; anything else is two
places. Re-scored over all 37 replayed stop fits, the ratio alone calls 28 of
them ties, runner-up-only calls 0, and this rule calls 2 -- the two stop-129
frames at 185 px, batch 5e trials 5 and 6.

WHAT THAT COSTS, SAID PLAINLY. Trial 5 ARRIVED reading the same signature at
the same stop (132 against 128, ratio 0.912, 185.0 px) as trial 6, which
finished short of the doorway. Nothing built from (best, second, dx) separates
them, so both go to the look-around: one extra disambiguation on an arriving
trial per 37 stops, in exchange for not guessing on the one shape with a
recorded live failure. The alternative was to guess "the winner is right" on
both.

RULE 2. The +-STOP_LOOK_DEG look-around, and the pan's looks, sampled EVERY
direction even when the first fitted overwhelmingly: 2 turns + 2 captures + 2
locates + a turn back, every time. A look at STRONG_MIN_INLIERS (165) is above
the wrong-place MAXIMUM of the live gate census (164), so the other direction
cannot change the verdict. Exit on the first strong look.

Usage: python apply_patch37.py [ROOT]
"""
import os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain.py")
W = os.path.join(ROOT, "chain_walk.py")
TW = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
TL = os.path.join(ROOT, "tests", "routing", "test_chain_locate.py")

c = open(C).read(); w = open(W).read()
tw = open(TW).read(); tl = open(TL).read()

if "STOP_TIE_DX_PX" in w or "second_k" in c:
    raise SystemExit("ALREADY APPLIED (patch37 markers present)")

# --------------------------------------------------------------- chain.py
edits_c = [
 # (1) the Fix docstring names the two new fields
 ('''        second    the runner-up's inliers -- how thin the win was
''',
  '''        second    the runner-up's inliers -- how thin the win was
        second_k  the runner-up's INDEX, or None when nothing else fitted
        second_dx the runner-up's dx (0.0 when there is no runner-up)
'''),
 # (2) slots + signature + assignment. OPTIONAL, with defaults: a Fix built
 #     the old way still constructs, and answers "I cannot say".
 ('''    __slots__ = ("k", "k_float", "inliers", "dx", "dy", "scale", "second",
                 "detail", "candidates")

    def __init__(self, k, k_float, inliers, dx, dy, scale, second, detail,
                 candidates=None):
''',
  '''    __slots__ = ("k", "k_float", "inliers", "dx", "dy", "scale", "second",
                 "detail", "candidates", "second_k", "second_dx")

    def __init__(self, k, k_float, inliers, dx, dy, scale, second, detail,
                 candidates=None, second_k=None, second_dx=0.0):
'''),
 ('''        self.candidates = candidates or {}
''',
  '''        self.candidates = candidates or {}
        # WHO the runner-up was, not just how big it was. `second` alone cannot
        # tell an adjacent near-duplicate frame of one stationary run from a
        # candidate that describes a different place, and chain_walk's stop-tie
        # rule was refusing every turn stop on that ambiguity. Optional with
        # defaults so nothing that builds a Fix the old way breaks; None means
        # "no runner-up / cannot say", which a caller must not read as
        # separation (chain_walk reads it as NO evidence of a tie).
        self.second_k = None if second_k is None else int(second_k)
        self.second_dx = float(second_dx)
'''),
 ('''                "inliers": self.inliers, "second": self.second,
''',
  '''                "inliers": self.inliers, "second": self.second,
                "second_k": self.second_k,
                "second_dx": round(self.second_dx, 1),
'''),
 ('''        k, best = order[0]
        second = order[1][1]["inliers"] if len(order) > 1 else 0
''',
  '''        k, best = order[0]
        runner = order[1] if len(order) > 1 else None
        second = runner[1]["inliers"] if runner else 0
        second_k = runner[0] if runner else None
        second_dx = runner[1]["dx"] if runner else 0.0
'''),
 ('''                   second=second, detail=detail, candidates=fits)
''',
  '''                   second=second, detail=detail, candidates=fits,
                   second_k=second_k, second_dx=second_dx)
'''),
]

# ---------------------------------------------------------- chain_walk.py
edits_w = [
 # (1) the constant block: the correction, and the new separation threshold
 ('''# A stop fit whose runner-up is within this fraction of it is AMBIGUOUS, not
# verification: batch 5e trial 6 'verified' the bar-entrance stop on 33 inliers
# against a runner-up of 33 with dx -386, and was short of the doorway.
STOP_TIE_FRAC = 0.9
''',
  '''# A stop fit whose runner-up is within this fraction of it MAY be ambiguity
# rather than verification -- but the ratio ALONE never was evidence of it, and
# from 2026-09-08 it is only the first of three conditions.
#
# WHAT THE RATIO ACTUALLY MEASURES AT A STOP. A turn-only target is a
# STATIONARY RUN of the recording collapsed to one index: several frames of the
# same spot, 0.25 s apart. Their fits to one live frame are near-duplicates, so
# the runner-up sits at 0.92-0.96 of the winner BY CONSTRUCTION. Replaying 37
# saved stop frames through chain.locate (agent_progress/closed-loop/stop_tie/
# replay_stops.py) calls a tie at EVERY one of the six stops of the four
# fastest arrivals ever recorded -- each of which verified head-on at the time
# in 0.1-4.2 s. The rule-cost study puts two thirds of the +34 s per arrival
# that followed this constant on exactly that (rule_costs/notes.md).
#
# AND ALONE IT COULD NOT CATCH ITS OWN EXAMPLE EITHER. Batch 5e trial 6's stop
# 129 ("33 against 33 with dx -386") reads winner 132, runner-up 128, and the
# ARRIVING batch 5e trial 5 reads the same stop at 34/31 with the same runner-up
# and the same 185 px disagreement. Nothing built from (best, second, dx)
# separates those two frames -- so the rule cannot be "spot the failure"; it can
# only be "spot the AMBIGUITY and go and look".
STOP_TIE_FRAC = 0.9
# ... so a tie also needs the two candidates to be TWO PLACES: their indices not
# both inside the stop's own stationary-run span (below), AND their dx
# disagreeing by more than this.
#
# THE SPAN TEST IS ON BOTH INDICES, NOT JUST THE RUNNER-UP'S. Two indices inside
# one span are one spot 0.25 s apart, and neither being there is what makes the
# pair informative -- in EITHER direction. A first draft asked only about the
# runner-up and lost exactly the frame above, whose WINNER (132) is the one past
# the span and whose runner-up (128) is the stop's own frame: it verified the
# stop and strafed on the winner's -386 px, which is the bug.
#
# WHAT THIS GATE JUDGES, MEASURED. Over the 37 replayed stop fits, those with a
# close count and two places read |second_dx - dx| =
#     0 0 0 0 0 0 0.2 0.3 0.4 0.6 1 4 4 6 6 9 11 27 45 67 95   |   185.0 185.4
# TWO populations with a gap between them (10.4), not the one the runner-up-only
# draft had: the low group is every neighbour one to three frames off the stop,
# each in a trial that ARRIVED; the high pair is stop 129 in batch 5e trials 5
# and 6. 120 sits in the gap -- 1.26x the low maximum, 0.65x the high minimum.
STOP_TIE_DX_PX = 120.0
'''),
 # (2) the span map, built ALWAYS (unlike `runs`, gated by a shipped-False flag)
 ('''    runs = stationary_runs(wps) if STOP_PAN_FROM_RUN else {}
''',
  '''    runs = stationary_runs(wps) if STOP_PAN_FROM_RUN else {}
    # Built unconditionally: every stop of every walk asks the tie rule below
    # which indices are the SAME SPOT as this stop, and `runs` is gated by the
    # shipped-False pan flag.
    spans = stop_spans(wps)
'''),
 # (3) stop_spans(), beside stationary_runs()
 ('''    if run:
        runs[run[-1][0]] = [(i2, h2) for i2, h2 in run if h2 is not None]
    return runs


def plan_min_iterations(plan, window=None):
''',
  '''    if run:
        runs[run[-1][0]] = [(i2, h2) for i2, h2 in run if h2 is not None]
    return runs


def stop_spans(wps):
    """{last index of each stationary run: the FIRST index of that run}.

    The SAME SPOT as an index range, which is what the stop-tie rule needs.
    `stationary_runs` cannot answer it: it DROPS frames whose heading is None
    -- the compass abstains on 6-15% of frames inside the bar (OPEN-15) -- so
    its lists have holes (the user's drive records the run ending at 88 as
    65..80, 82, 84..88), and a hole is not a different place. A span cannot be
    broken by one. Same stationarity rule as `plan_indices`, so the keys are
    exactly the plan's turn-only targets.
    """
    spans, run = {}, []
    for i, w in enumerate(wps):
        if i == 0:
            continue
        lx = getattr(w, "lx", None) or 0.0
        ly = getattr(w, "ly", None)
        unknown = "stick:unknown" in (getattr(w, "note", "") or "")
        stationary = (not unknown and ly is not None
                      and abs(ly) <= STATIONARY_STICK and abs(lx) <= STATIONARY_STICK)
        if stationary:
            run.append(i)
            continue
        if run:
            spans[run[-1]] = run[0]
            run = []
    if run:
        spans[run[-1]] = run[0]
    return spans


def plan_min_iterations(plan, window=None):
'''),
 # (4) the tie itself
 ('''            sec_t = 0 if fix_t is None else (getattr(fix_t, "second", 0) or 0)
            tied = fix_t is not None and sec_t >= STOP_TIE_FRAC * max(1, inl_t)
''',
  '''            sec_t = 0 if fix_t is None else (getattr(fix_t, "second", 0) or 0)
            # Hoisted: `tied` reads the winner's index and offset now, and
            # `real` and the aligned block below read the same two locals.
            kt = None if fix_t is None else int(getattr(fix_t, "k", target_k))
            dxt = 0.0 if fix_t is None else (getattr(fix_t, "dx", 0.0) or 0.0)
            # A TIE NEEDS SEPARATION (see STOP_TIE_FRAC). Three conditions, all
            # required: a close count, the winner and the runner-up NOT BOTH
            # inside this stop's own stationary-run span, and a dx that
            # disagrees. `second_k` is None on a Fix built before it existed
            # (or by a caller that cannot say) -- that is NOT separation, so
            # no tie.
            #
            # BOTH indices, not just the runner-up's. Batch 5e trial 6 -- the
            # frame STOP_TIE_FRAC exists for -- has the WINNER past the span
            # (132 of 116..129) and the near-tied runner-up AT the stop (128).
            # A runner-up-only test called that "not a tie", verified the stop
            # and strafed 0.54 s LEFT on the winner's -386 px: it trusted the
            # candidate past the stop, which is the bug. Two indices inside one
            # span are one spot 0.25 s apart; anything else is two places.
            sec_k = None if fix_t is None else getattr(fix_t, "second_k", None)
            sec_dx = 0.0 if fix_t is None else (getattr(fix_t, "second_dx", 0.0) or 0.0)
            run_lo = spans.get(target_k, target_k)
            sec_here = sec_k is not None and run_lo <= sec_k <= target_k
            win_here = kt is not None and run_lo <= kt <= target_k
            separated = sec_k is not None and not (sec_here and win_here)
            apart = abs(sec_dx - dxt) > STOP_TIE_DX_PX
            tied = (fix_t is not None
                    and sec_t >= STOP_TIE_FRAC * max(1, inl_t)
                    and separated and apart)
'''),
 # (5) kt/dxt are defined with the tie above now: ONE definition, not two
 ('''            kt = None if fix_t is None else int(getattr(fix_t, "k", target_k))
            dxt = 0.0 if fix_t is None else (getattr(fix_t, "dx", 0.0) or 0.0)
            real = fix_t is not None and inl_t >= WEAK_MIN_INLIERS and not tied
''',
  '''            real = fix_t is not None and inl_t >= WEAK_MIN_INLIERS and not tied
'''),
 # (6) the look-around exits on the first STRONG look
 ('''                    if f2 is not None and i2 >= FIX_MIN_INLIERS and (best is None or i2 > best[1]):
                        best = (ddeg, i2, f2)
''',
  '''                    if f2 is not None and i2 >= FIX_MIN_INLIERS and (best is None or i2 > best[1]):
                        best = (ddeg, i2, f2)
                    if best is not None and best[1] >= STRONG_MIN_INLIERS:
                        # STOP LOOKING. STRONG_MIN_INLIERS (165) is above the
                        # wrong-place MAXIMUM of the live gate census (164,
                        # overnight/census/live_gate_census.json), so the other
                        # direction cannot change this verdict -- it can only
                        # cost a turn, a capture and a locate. The loop used to
                        # sample every direction whatever the first one said,
                        # and `turned-looked` is +20.9 s a trial
                        # (rule_costs/notes.md).
                        break
'''),
 # (6) ... and so does the pan
 ('''                    if f2 is not None and i2 >= FIX_MIN_INLIERS and (best is None or i2 > best[1]):
                        best = (h2, i2, f2)
''',
  '''                    if f2 is not None and i2 >= FIX_MIN_INLIERS and (best is None or i2 > best[1]):
                        best = (h2, i2, f2)
                    if best is not None and best[1] >= STRONG_MIN_INLIERS:
                        break            # same rule as the look-around below
'''),
 # (7) the journal carries the runner-up's identity, or nothing explains a tie
 ('''            ("k", "k_float", "inliers", "dx", "dy", "scale", "second", "detail")}
''',
  '''            ("k", "k_float", "inliers", "dx", "dy", "scale", "second",
             "second_k", "second_dx", "detail")}
'''),
]

# ------------------------------------------------ tests/test_chain_walk.py
edits_tw = [
 # the stub Fix learns the two new fields
 ('''    def __init__(self, k, scale=1.0, dx=0.0, dy=0.0, inliers=120, second=5,
                 k_float=None, detail="stub"):
        self.k = k
''',
  '''    def __init__(self, k, scale=1.0, dx=0.0, dy=0.0, inliers=120, second=5,
                 k_float=None, detail="stub", second_k=None, second_dx=0.0):
        self.k = k
        # WHO the runner-up was. None = "cannot say", the default a Fix built
        # before these fields existed reports, and NOT evidence of a tie.
        self.second_k = second_k
        self.second_dx = second_dx
'''),
 # the journal's key set, pinned by Bookkeeping
 ('''        self.assertEqual(
            set(res["fixes"][0]["fix"]),
            {"k", "k_float", "inliers", "dx", "dy", "scale", "second", "detail"})
''',
  '''        self.assertEqual(
            set(res["fixes"][0]["fix"]),
            {"k", "k_float", "inliers", "dx", "dy", "scale", "second",
             "second_k", "second_dx", "detail"})
'''),
 # the pan's looks stop early too
 ('''    def test_the_pan_is_off_by_default_even_when_the_stop_has_a_run(self):
''',
  '''    def test_a_strong_first_pan_look_ends_the_pan(self):
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
'''),
 # the tie tests
 ('''    def test_a_tied_fit_at_a_stop_is_ambiguity_not_verification(self):
        # Batch 5e trial 6: 33 inliers against a runner-up of 33 at the bar
        # stop was 'verified' and the loop was short of the doorway.
        self.assertEqual(chain_walk.STOP_TIE_FRAC, 0.9)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)], start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        # it2: head-on a TIED 33/33 fit at the stop -> not verified; looks None -> wait
        ch = FakeChain(5, [Fix(k=1), Fix(k=2, inliers=33, second=33), None, None,
                           Fix(k=2, inliers=90, second=30), Fix(k=3), Fix(k=4)], default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=9)
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:3], ["advanced", "turn-back", "turned"])
''',
  '''    def _stop_with_a_two_frame_run(self):
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

'''),
]

# ---------------------------------------------- tests/test_chain_locate.py
edits_tl = [
 ('''    def test_no_runner_up_reads_zero(self):
''',
  '''    def test_second_k_and_second_dx_name_the_runner_up(self):
        """`second` says how big the runner-up was; these say WHO it was.

        chain_walk's stop-tie rule has to tell an adjacent near-duplicate frame
        of one stationary run from a candidate describing a different place,
        and the count alone cannot: at a turn stop the runner-up is 0.92-0.96
        of the winner by construction. Run both ways round so neither field can
        pass by naming a fixed position.
        """
        for thin_at, whole_at in ((1, 0), (0, 1)):
            with self.subTest(thin_at=thin_at):
                wps = [None, None]
                wps[whole_at] = _waypoint(self.warp(1.00 + 0.06 * whole_at),
                                          whole_at, "whole")
                wps[thin_at] = self._thin(1.00 + 0.06 * thin_at, thin_at)
                ch = chain.Chain(wps)
                fix = ch.locate(self.warp(1.03), k_hint=0, window=1)
                self.assertIsNotNone(fix)
                self.assertEqual(sorted(fix.candidates), [0, 1], fix.detail)
                self.assertEqual(fix.k, whole_at, fix.detail)
                self.assertEqual(fix.second_k, thin_at,
                                 f"second_k must be the RUNNER-UP's index, not "
                                 f"the winner's ({fix.detail})")
                self.assertNotEqual(fix.second_k, fix.k, fix.detail)
                self.assertEqual(fix.second_dx,
                                 fix.candidates[thin_at]["dx"], fix.detail)
                self.assertEqual(fix.as_dict()["second_k"], fix.second_k)

    def test_a_fix_built_without_the_runner_up_fields_says_it_cannot_say(self):
        # They are OPTIONAL with defaults so every existing caller and test
        # keeps working; None is "cannot say", which chain_walk must not read
        # as separation.
        f = chain.Fix(k=0, k_float=0.0, inliers=9, dx=1.0, dy=2.0, scale=1.0,
                      second=3, detail="d")
        self.assertIsNone(f.second_k)
        self.assertEqual(f.second_dx, 0.0)

    def test_no_runner_up_reads_zero(self):
'''),
 ('''        self.assertEqual(sorted(fix.candidates), [0])
        self.assertEqual(
            fix.second, 0,
            f"with one candidate there is no runner-up, and 0 is what says so "
            f"({fix.detail})")
''',
  '''        self.assertEqual(sorted(fix.candidates), [0])
        self.assertEqual(
            fix.second, 0,
            f"with one candidate there is no runner-up, and 0 is what says so "
            f"({fix.detail})")
        self.assertIsNone(fix.second_k, fix.detail)
        self.assertEqual(fix.second_dx, 0.0, fix.detail)
'''),
]

PLAN = [(C, c, edits_c), (W, w, edits_w), (TW, tw, edits_tw), (TL, tl, edits_tl)]

# EVERY anchor in EVERY file is checked BEFORE ANY write (10.19).
for path, text, edits in PLAN:
    for old, new in edits:
        n = text.count(old)
        assert n == 1, (os.path.basename(path), n, old.splitlines()[0][:70])

out = []
for path, text, edits in PLAN:
    for old, new in edits:
        text = text.replace(old, new, 1)
    out.append((path, text))
for path, text in out:
    open(path, "w").write(text)
print("patch37 applied to", ROOT)
