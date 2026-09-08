"""chain.locate() must place a frame on the chain, and reached() must not lie.

The closed loop asks two questions after every push: which recorded waypoint am
I at, and am I past it. `chain.py` answers both from the picture alone. This
pins the four properties the controller depends on, on SYNTHETIC frames built
from ONE real 1920x1080 capture so the ground truth is exact:

    a forward walk is, to first order, the scene getting BIGGER

so a chain is modelled as `cv2.warpAffine` of the same frame at increasing
scale, and a held-out frame at an intermediate scale has a KNOWN true position
between two waypoints. Lateral drift is a horizontal translation, whose sign is
likewise known.

WHAT IS PINNED, AND WHY EACH ONE EARNS ITS PLACE

  1. A held-out frame lands in its own bracket, and `k_float` recovers the
     sub-waypoint position. Without this the sensor could return a plausible
     integer and be measuring nothing.
  2. `dx` follows pose.offset's sign convention -- dx > 0 means the scene moved
     RIGHT, i.e. the camera is LEFT of the reference, so the controller strafes
     RIGHT. A flipped sign here drives the character away from the chain on
     every correction, and every symptom would look like a routing failure.
  3. `scale > 1` means CLOSER than the waypoint. The whole advance rule rests
     on it.
  4. `reached(fix, k)` is true exactly when the true position is at or past
     waypoint k -- checked against the KNOWN true position, not against the
     rule restated.
  5. The search is WINDOWED. A frame from a different scene, with a hint
     elsewhere in the chain, must NOT be matched to the scene it belongs to
     outside the window. That is the localiser's measured trap (CLAUDE.md
     section 11: a genuine arrival scored 137 matches and a frame taken
     OUTDOORS ON A STREET scored 135, against MIN_MATCHES 140), and the second
     fixture here IS that street frame.
  6. `MIN_INLIERS` is read at CALL time, not captured in a default argument
     (CLAUDE.md 10.18), so a harness or a test can redirect it.
  7. The HAMMING FILTER is applied, and `match_fit` fits nothing else. It is a
     SPEC requirement and the one deliberate difference from `pose.offset`, and
     until 2026-09-07 deleting it left every test green.
  8. `tools/chain_validate.py`'s ground truth is the frame's POSITION, so a
     waypoint frame can never be scored as a held-out test of itself.
  9. That tool's default hint is an ORACLE and its report and headline say so;
     `--hint closed` really replays the SPEC controller's own advance rule.
 10. `Fix.second` IS the runner-up's inlier count. It is a SPEC field and this
     module's only stated mitigation for the sequence prior's central risk --
     "if the true position leaves the window the sensor cannot say so, it can
     only report a bad best" -- so a caller judges the win by it. Nothing
     asserted it until 2026-09-07 and `self.second = 0` left the suite green:
     a permanent landslide, reported to a caller told to read it.
 11. That tool never averages an ABSTENTION into its accuracy. `within_*` is
     over PLACED frames, `within_*_all` over ALL held out, and both are
     printed. Unasserted, a mutant that divided `within_1` by every held-out
     row while still labelling it "of PLACED" left the suite green -- and that
     is the number the go/no-go is quoted from.

7 and 10 are the sensor; 8, 9 and 11 are the evidence tool that produces the
go/no-go, which is as load-bearing as the sensor: a validator that scores the
wrong frames against the wrong index, or divides by the wrong denominator,
prints a perfectly plausible number.

Offline: no console, no input path, no map, no network. `chain` imports only
`places`, `pose`, cv2 and numpy.
"""

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import chain                                                    # noqa: E402

CORRIDOR = os.path.join(_ROOT, "test_fixtures", "chain", "corridor_1920.jpg")
STREET = os.path.join(_ROOT, "test_fixtures", "chain", "street_1920.jpg")

# The chain: five waypoints, 6% closer each step. 6% is not a measured constant
# and gates nothing -- it is the synthetic ladder's spacing, chosen so adjacent
# waypoints still match each other richly (they do: every pair fits at the
# 200-match ceiling) while the scale differences are far outside RANSAC noise.
SCALES = [1.00, 1.06, 1.12, 1.18, 1.24]
_CACHE = {}


def _warper(path):
    """A function (scale, tx) -> PIL image, warped about the frame centre."""
    import cv2
    if path not in _CACHE:
        base = cv2.imread(path, cv2.IMREAD_COLOR)
        assert base is not None, f"fixture missing or unreadable: {path}"
        _CACHE[path] = base
    base = _CACHE[path]
    h, w = base.shape[:2]

    def warp(scale, tx=0.0):
        from PIL import Image
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0.0, scale)
        M[0, 2] += tx
        out = cv2.warpAffine(base, M, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REFLECT)
        return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    return warp


def _waypoint(img, index, path):
    import places
    kps, des = places.keypoints(img)
    return chain.Waypoint(index=index, path=path, kps=kps, des=des)


def _ladder(warp, scales=SCALES, start=0, tag="w"):
    return [_waypoint(warp(s), start + i, f"{tag}{i}")
            for i, s in enumerate(scales)]


def true_position(scale, scales=SCALES):
    """Where a frame at `scale` sits on the ladder, in chain steps.

    The ladder is linear in scale, so this is exact and owes nothing to the
    module under test.
    """
    for i in range(len(scales) - 1):
        lo, hi = scales[i], scales[i + 1]
        if lo <= scale <= hi:
            return i + (scale - lo) / (hi - lo)
    raise AssertionError(f"{scale} is off the ladder {scales}")


class _Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # staticmethod: a bare function stored on the class would bind `self`
        # as its first argument on every `self.warp(...)` call.
        cls.warp = staticmethod(_warper(CORRIDOR))
        cls.chain = chain.Chain(_ladder(cls.warp))


class HeldOutFramesLandOnTheChain(_Base):
    """Property 1: the right bracket, and a sub-waypoint position."""

    # (query scale, the hint the controller would have: the last waypoint it
    # believes it reached)
    CASES = [(1.03, 0), (1.04, 0), (1.09, 1), (1.10, 1),
             (1.15, 2), (1.16, 2), (1.21, 3)]

    def test_lands_in_its_own_bracket(self):
        import math
        for scale, hint in self.CASES:
            with self.subTest(scale=scale):
                p = true_position(scale)
                fix = self.chain.locate(self.warp(scale), k_hint=hint)
                self.assertIsNotNone(
                    fix, f"abstained on a frame 6% from a waypoint (p={p:.2f})")
                lo, hi = math.floor(p), math.ceil(p)
                self.assertTrue(
                    lo <= fix.k <= hi,
                    f"true position {p:.2f} is between waypoints {lo} and {hi}, "
                    f"but locate said k={fix.k} ({fix.detail})")

    def test_k_float_recovers_the_sub_waypoint_position(self):
        for scale, hint in self.CASES:
            with self.subTest(scale=scale):
                p = true_position(scale)
                fix = self.chain.locate(self.warp(scale), k_hint=hint)
                self.assertIsNotNone(fix)
                self.assertAlmostEqual(
                    fix.k_float, p, delta=0.15,
                    msg=f"k_float {fix.k_float:.3f} vs true {p:.3f} "
                        f"({fix.detail})")

    def test_the_window_is_the_one_the_spec_fixes(self):
        # k_hint-1 .. k_hint+window, clamped. One step BACK matters: a push can
        # fail to move the character at all.
        self.assertEqual(self.chain.window_bounds(2, 3), (1, 4))
        self.assertEqual(self.chain.window_bounds(0, 3), (0, 3))
        self.assertEqual(self.chain.window_bounds(4, 3), (3, 4))


class ScaleAndDxMeanWhatTheDocstringSays(_Base):
    """Properties 2 and 3, measured against ONE waypoint so nothing is a tie.

    A single-waypoint chain with window=0 leaves exactly one candidate, so the
    numbers below are the fit itself and not the outcome of a comparison.
    """

    def _one(self, wp_scale):
        return chain.Chain([_waypoint(self.warp(wp_scale), 0, "solo")])

    def test_closer_than_the_waypoint_reads_scale_above_one(self):
        ch = self._one(1.00)
        fix = ch.locate(self.warp(1.12), k_hint=0, window=0)
        self.assertIsNotNone(fix)
        self.assertGreater(
            fix.scale, 1.05,
            f"a frame 12% CLOSER than the waypoint must read scale > 1 "
            f"('the scene looks bigger'), got {fix.scale:.4f}")
        self.assertAlmostEqual(fix.scale, 1.12, delta=0.02)

    def test_further_than_the_waypoint_reads_scale_below_one(self):
        ch = self._one(1.12)
        fix = ch.locate(self.warp(1.00), k_hint=0, window=0)
        self.assertIsNotNone(fix)
        self.assertLess(
            fix.scale, 0.95,
            f"a frame further back than the waypoint must read scale < 1, "
            f"got {fix.scale:.4f}")

    def test_dx_sign_is_pose_offsets(self):
        # pose.offset: dx = median(dst - src) with src from the reference and
        # dst from the live frame. Translating the live scene RIGHT by +40px is
        # what happens when the camera is 40px LEFT of the reference, and the
        # controller reads dx > 0 as "strafe RIGHT".
        ch = self._one(1.12)
        right = ch.locate(self.warp(1.12, +40.0), k_hint=0, window=0)
        left = ch.locate(self.warp(1.12, -40.0), k_hint=0, window=0)
        self.assertIsNotNone(right)
        self.assertIsNotNone(left)
        self.assertGreater(right.dx, 0.0,
                           f"scene shifted RIGHT must give dx > 0: {right.detail}")
        self.assertLess(left.dx, 0.0,
                        f"scene shifted LEFT must give dx < 0: {left.detail}")
        self.assertAlmostEqual(right.dx, +40.0, delta=8.0, msg=right.detail)
        self.assertAlmostEqual(left.dx, -40.0, delta=8.0, msg=left.detail)


class ReachedMatchesTheTruePosition(_Base):
    """Property 4, checked against the KNOWN position, not the rule restated.

    `reached(fix, k)` must be True exactly when the character's true position
    is at or past waypoint k. Asserting `reached(fix, fix.k) == (fix.scale >=
    1)` would be the implementation copied into the test -- section 10.11's
    "a test must not assert against the constant it is guarding", one level up.
    """

    CASES = [1.03, 1.09, 1.15, 1.21]

    def test_reached_is_true_exactly_up_to_the_true_position(self):
        for scale in self.CASES:
            p = true_position(scale)
            fix = self.chain.locate(self.warp(scale), k_hint=int(p))
            self.assertIsNotNone(fix, f"abstained at p={p:.2f}")
            for k in range(len(SCALES)):
                with self.subTest(scale=scale, k=k):
                    self.assertEqual(
                        self.chain.reached(fix, k), p >= k,
                        f"true position {p:.2f}, waypoint {k}: reached said "
                        f"{self.chain.reached(fix, k)} ({fix.detail})")

    def test_an_abstention_is_not_an_arrival(self):
        # Not knowing where you are is not evidence of having got there --
        # pose.same_pose states the same rule for the same reason.
        self.assertFalse(self.chain.reached(None, 0))
        self.assertFalse(self.chain.reached(None, 3))


class TheSearchIsWindowed(unittest.TestCase):
    """Property 5: the sequence prior, and the trap it exists to avoid.

    Chain: five waypoints of a CITY STREET (the frame a leg into the bar
    actually ended on -- CLAUDE.md section 8k), then five of the bar corridor.
    The live frame is the corridor; the hint says we are in the street segment.

    A global search finds the corridor at the 200-match ceiling and answers
    with total confidence. The windowed search must not, because the controller
    cannot have teleported five waypoints in one push. This is the localiser's
    measured failure in miniature.
    """

    @classmethod
    def setUpClass(cls):
        cls.wa = staticmethod(_warper(CORRIDOR))
        cls.wb = staticmethod(_warper(STREET))
        wps = _ladder(cls.wb, start=0, tag="street")
        wps += _ladder(cls.wa, start=5, tag="corridor")
        for i, w in enumerate(wps):
            w.index = i
        cls.chain = chain.Chain(wps)
        cls.query = cls.wa(1.02)

    def test_the_global_best_really_is_outside_the_window(self):
        # Anti-vacuity. If the two fixtures ever stop being distinguishable
        # this test would pass by finding nothing, so prove the trap is armed:
        # the out-of-window corridor waypoint must beat every in-window one.
        import places
        kps, des = places.keypoints(self.query)
        outside = chain.match_fit(self.chain.waypoints[5].kps,
                                  self.chain.waypoints[5].des, kps, des)
        self.assertIsNotNone(outside, "the corridor waypoint no longer fits")
        inside = []
        for j in range(0, 5):
            w = self.chain.waypoints[j]
            f = chain.match_fit(w.kps, w.des, kps, des)
            inside.append(0 if f is None else f["inliers"])
        self.assertGreater(
            outside["inliers"], 4 * max(inside),
            f"the trap is not armed: out-of-window {outside['inliers']} "
            f"inliers vs in-window {inside}")

    def test_locate_answers_inside_the_window_or_abstains(self):
        fix = self.chain.locate(self.query, k_hint=1, window=3)
        if fix is None:
            return                     # abstaining is a permitted answer
        self.assertTrue(
            0 <= fix.k <= 4,
            f"locate reached OUTSIDE its window [0,4] and matched the scene "
            f"the frame really belongs to: {fix.detail}")

    def test_the_same_frame_is_placed_correctly_from_the_right_hint(self):
        # The control: with an honest hint the same query lands on waypoint 5,
        # so the previous test is about the WINDOW and not about a sensor that
        # cannot see this frame at all.
        fix = self.chain.locate(self.query, k_hint=6, window=3)
        self.assertIsNotNone(fix)
        self.assertEqual(fix.k, 5, fix.detail)
        self.assertAlmostEqual(fix.k_float, 5 + true_position(1.02),
                               delta=0.15, msg=fix.detail)


class MinInliersKnobIsReadAtCallTime(_Base):
    """Property 6: the abstention gate is off, and redirectable.

    CLAUDE.md 10.4 -- no constant is invented, and the two populations this
    gate would have to separate have not been measured, so it ships None.
    10.18 -- a module-level knob a harness may redirect must be read at CALL
    time; `leg_reliability` captured one in a default argument and every
    redirect silently changed nothing.
    """

    def test_default_is_never_abstain(self):
        self.assertIsNone(
            chain.MIN_INLIERS,
            "MIN_INLIERS must stay None until tools/chain_validate.py shows "
            "the NEAR and FAR inlier populations actually separate")

    def test_setting_the_module_knob_takes_effect_on_the_next_call(self):
        saved = chain.MIN_INLIERS
        try:
            self.assertIsNotNone(self.chain.locate(self.warp(1.03), k_hint=0))
            chain.MIN_INLIERS = 10 ** 6
            self.assertIsNone(
                self.chain.locate(self.warp(1.03), k_hint=0),
                "the module knob was not read at call time -- a redirect that "
                "changes nothing is 10.18")
        finally:
            chain.MIN_INLIERS = saved
        self.assertIsNotNone(self.chain.locate(self.warp(1.03), k_hint=0))


class LoadReadsWhatTheRecorderWrites(unittest.TestCase):
    """Chain.load() is the seam between the three modules -- pin it.

    chain_record.py appends ONE JSON object per line and flushes, so load()
    must (a) put the waypoints in RECORDED order whatever order the lines
    arrive in, (b) survive a TRUNCATED final line, which is the crash the
    append-only format exists to tolerate, and (c) drop -- loudly -- a meta row
    whose jpg is missing rather than raising and losing the whole recording.

    Untested, this is the project's commonest bug shape: a load that silently
    returns something plausible looks exactly like a load that worked.
    """

    def test_load_orders_by_index_and_tolerates_a_truncated_tail(self):
        import json
        import tempfile
        warp = _warper(CORRIDOR)
        with tempfile.TemporaryDirectory() as d:
            rows = []
            for i, s in enumerate(SCALES[:3]):
                name = f"{i:04d}.jpg"
                warp(s).save(os.path.join(d, name), quality=88)
                rows.append({"index": i, "heading": 87.0 + i, "path": name,
                             "t": 0.25 * i, "lx": 0.0, "ly": -0.45,
                             "note": f"s={s}"})
            rows.append({"index": 9, "heading": None, "path": "9999.jpg",
                         "t": 9.0, "lx": 0.0, "ly": 0.0, "note": "no file"})
            with open(os.path.join(d, "meta.jsonl"), "w") as f:
                # DELIBERATELY out of recorded order, and with a half-written
                # last line -- what a kill at minute four leaves behind.
                for r in (rows[2], rows[0], rows[3], rows[1]):
                    f.write(json.dumps(r) + "\n")
                f.write('{"index": 4, "head')
            ch = chain.Chain.load(d, log=lambda *a: None)

        self.assertEqual([w.index for w in ch.waypoints], [0, 1, 2],
                         "load() must order by the recorded index, drop the "
                         "row whose jpg is missing, and skip the truncated tail")
        self.assertEqual([w.heading for w in ch.waypoints], [87.0, 88.0, 89.0])
        self.assertEqual(ch.waypoints[1].ly, -0.45)
        self.assertEqual(len(ch.skipped), 1)
        self.assertTrue(all(w.des is not None for w in ch.waypoints))
        # and the loaded chain is usable: standing exactly at waypoint 1 reads
        # k = 1, k_float = 1.0. All three candidates fit at the 200-match
        # ceiling (measured: inliers 200/200/200, scales 1.0598 / 1.0000 /
        # 0.9466), so `k` is decided ENTIRELY by locate's tie-break on
        # |scale - 1| -- best-by-inliers alone would answer whichever the dict
        # yielded first. That is why the tie-break exists and why the
        # controller advances on `reached()` (k AND scale) rather than on a raw
        # inlier ranking.
        fix = ch.locate(warp(SCALES[1]), k_hint=1, window=3)
        self.assertIsNotNone(fix)
        self.assertEqual(fix.k, 1, fix.detail)
        self.assertAlmostEqual(fix.k_float, 1.0, delta=0.15, msg=fix.detail)
        self.assertTrue(ch.reached(fix, 1), fix.detail)


class TheHammingFilterIsLoadBearing(unittest.TestCase):
    """Property 7: `match_fit` fits FILTERED matches, and that is the point.

    The SPEC says "Hamming-filtered matches -> cv2.estimateAffinePartial2D
    RANSAC", and it is the one place this module deliberately differs from
    `pose.offset`, which fits the best 200 UNFILTERED. Deleting the filter left
    the whole suite green until 2026-09-07 -- a declared design decision with no
    guard, which on this project is how a decision quietly stops being true.

    WHAT IS ASSERTED, AND WHAT DELIBERATELY IS NOT. The filter's effect is at
    the MATCH level, where it is huge and deterministic (measured over 25
    street x corridor scale combinations and 8 same-scene ones,
    agent_progress/closed-loop/fix-sensor/measure_survivors.py):

        UNRELATED  street x corridor    294-357 crossCheck matches, 67-99 survive
        RELATED    corridor x corridor  879-1080 matches,          845-1058 survive
        descriptor distance, median:    unrelated 56-58   related 17-24

    At the FIT level, on the other hand, an unrelated pair sits on the RANSAC
    floor in BOTH arms and which arm returns None is a coin flip -- filtered
    None / unfiltered 6 inliers on one pair, and exactly the reverse on the
    next, each stable over 10 runs. So "the filter makes unrelated pairs
    abstain" is FALSE as a per-pair rule and is NOT asserted here; asserting it
    would have been a test that passes for the wrong reason on the pair that
    happened to be chosen. What the filter buys, measured over 160 held-out
    office-drive frames, is false-positive SUPPRESSION in aggregate: FAR >= NEAR
    on 3/112 filtered against 15/134 unfiltered.
    """

    @classmethod
    def setUpClass(cls):
        cls.corridor = staticmethod(_warper(CORRIDOR))
        cls.street = staticmethod(_warper(STREET))

    def _descs(self, img):
        import places
        return places.keypoints(img)[1]

    def _n_filtered(self, a, b, gate=None):
        """len(chain.hamming_filtered(a, b)) with `places._HAMMING_MAX` moved.

        The gate is read at call time inside `hamming_filtered`, so moving it
        here exercises the module's own code path in both arms -- no mirror of
        the matcher, which is the reimplementation trap that once scored an
        unmapped corpus above the references themselves.
        """
        import places
        saved = places._HAMMING_MAX
        try:
            if gate is not None:
                places._HAMMING_MAX = gate
            return len(chain.hamming_filtered(self._descs(a), self._descs(b)))
        finally:
            places._HAMMING_MAX = saved

    # 140 = the geometric middle of the two MEASURED populations below: 99 (the
    # most an unrelated pair ever kept, over 25 combinations) and 200 (the
    # pose._MAX_MATCHES cap, which every related pair reaches). It is not a
    # behavioural constant -- nothing in chain.py reads it -- it is where this
    # test cuts, and CLAUDE.md 10.4 says a cut goes BETWEEN two populations.
    SURVIVOR_CUT = 140

    def test_an_unrelated_pair_loses_most_of_its_matches_to_the_filter(self):
        for sa, sb in [(1.00, 1.00), (1.00, 1.12), (1.06, 1.24),
                       (1.12, 1.00), (1.24, 1.18)]:
            with self.subTest(street=sa, corridor=sb):
                a, b = self.street(sa), self.corridor(sb)
                kept = self._n_filtered(a, b)
                opened = self._n_filtered(a, b, gate=256)
                self.assertEqual(
                    opened, 200,
                    "control: with the gate open this unrelated pair should "
                    "fill the pose._MAX_MATCHES cap, as pose.offset would")
                self.assertLess(
                    kept, self.SURVIVOR_CUT,
                    f"the Hamming filter is not being applied: an UNRELATED "
                    f"pair kept {kept} matches, and unfiltered it keeps "
                    f"{opened}. Measured range for unrelated pairs is 67-99.")

    def test_a_related_pair_loses_nothing_that_reaches_the_fit(self):
        # The control that stops the test above from being satisfied by a
        # filter that simply destroys everything.
        for sa, sb in [(1.00, 1.06), (1.00, 1.12), (1.00, 1.24), (1.12, 1.24)]:
            with self.subTest(a=sa, b=sb):
                a, b = self.corridor(sa), self.corridor(sb)
                self.assertEqual(self._n_filtered(a, b), 200)
                self.assertEqual(self._n_filtered(a, b, gate=256), 200)

    def test_match_fit_fits_only_the_matches_that_pass_the_filter(self):
        """The WIRING: hamming_filtered can filter perfectly and match_fit can
        still ignore it. Lower the gate until a RELATED pair keeps fewer than
        the 200-match cap, and match_fit must fit exactly those."""
        import places
        a, b = self.corridor(1.00), self.corridor(1.12)
        saved = places._HAMMING_MAX
        try:
            places._HAMMING_MAX = 15          # measured: 131 of 879 survive
            ka, da = places.keypoints(a)
            kb, db = places.keypoints(b)
            n = len(chain.hamming_filtered(da, db))
            fit = chain.match_fit(ka, da, kb, db)
        finally:
            places._HAMMING_MAX = saved
        self.assertGreaterEqual(n, chain.MIN_MATCHES_TO_FIT)
        self.assertLess(n, 200, "anti-vacuity: at this gate the survivors must "
                                "fall BELOW the cap, or the equality below "
                                "holds however match_fit selects its matches")
        self.assertIsNotNone(fit, "a same-scene pair must still fit at gate 15")
        self.assertEqual(
            fit["matches"], n,
            f"match_fit fitted {fit['matches']} matches where the filter kept "
            f"{n} -- it is not going through hamming_filtered")

    def test_the_fit_floor_cannot_sit_under_poses_inlier_minimum(self):
        # 10.11: pin the LITERAL, not the constant being guarded. A floor below
        # pose._MIN_INLIERS could never help -- a fit cannot have more inliers
        # than it has matches -- so this is a real bound, not a restatement.
        import pose
        self.assertEqual(chain.MIN_MATCHES_TO_FIT, 8)
        self.assertGreaterEqual(chain.MIN_MATCHES_TO_FIT, pose._MIN_INLIERS)


# A waypoint holding only the first 30 of a scene's own ORB descriptors.
# crossCheck returns at most one pair per REFERENCE descriptor, so such a
# waypoint CANNOT reach the pose._MAX_MATCHES cap however well it matches: it
# fits (measured 25-26 inliers over 5 runs, against pose._MIN_INLIERS 6 and
# chain.MIN_MATCHES_TO_FIT 8) but can only ever be the runner-up. That is what
# makes a strictly-lower `second` reproducible -- on the ordinary ladder every
# candidate saturates at ~200 and the runner-up EQUALS the winner by
# construction (measured, agent_progress/closed-loop/fix-sensor/
# measure_second.py and measure_second2.py). 30 is a fixture parameter, not a
# threshold: nothing in chain.py reads it.
THIN_DESCRIPTORS = 30


class TheRunnerUpIsOnTheFix(_Base):
    """Property 10: `Fix.second` is the RUNNER-UP's inlier count.

    The SPEC fixes `second:int (runner-up inliers)` on the Fix, and chain.py's
    module docstring makes it the one declared mitigation for the sequence
    prior's declared central risk: "if the true position leaves the window the
    sensor cannot say so, it can only report a bad best. `second` (the
    runner-up's inliers) and `detail` are on the Fix so a caller can see how
    thin the win was."

    Nothing asserted it until 2026-09-07. Replacing `self.second = int(second)`
    with `self.second = 0` left all 28 tests green -- the field a caller is
    told to judge the win by, reporting a permanent landslide, on every fix,
    forever. Every other SPEC field of Fix was already exercised; this one was
    the hole.
    """

    def _thin(self, scale, index):
        """A waypoint with only THIN_DESCRIPTORS of the same scene's features."""
        import places
        kps, des = places.keypoints(self.warp(scale))
        return chain.Waypoint(index=index, path=f"thin{index}",
                              kps=kps[:THIN_DESCRIPTORS],
                              des=des[:THIN_DESCRIPTORS])

    def test_second_is_the_runner_up_of_a_real_window(self):
        # Ranked independently from the raw per-candidate fits, not from
        # locate's own sort key -- 10.11 one level up.
        fix = self.chain.locate(self.warp(1.03), k_hint=0)
        self.assertIsNotNone(fix)
        counts = sorted((c["inliers"] for c in fix.candidates.values()),
                        reverse=True)
        self.assertGreaterEqual(
            len(counts), 2,
            f"anti-vacuity: a runner-up must exist for `second` to mean "
            f"anything, and only {len(counts)} candidate(s) fitted "
            f"({fix.detail})")
        self.assertEqual(fix.inliers, counts[0], fix.detail)
        self.assertEqual(
            fix.second, counts[1],
            f"second must be the SECOND-ranked candidate's inliers: candidates "
            f"{sorted(fix.candidates.items())} ({fix.detail})")
        self.assertGreater(
            fix.second, 0,
            f"a window in which several waypoints fitted richly reported NO "
            f"runner-up: {fix.detail}")

    def test_second_is_the_runner_ups_count_and_not_the_winners(self):
        """The discriminating case: a runner-up that is genuinely thinner.

        Run BOTH ways round so `second` cannot be passing by naming a fixed
        position -- the winner is waypoint 0 in one arm and waypoint 1 in the
        other.
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
                self.assertEqual(sorted(fix.candidates), [0, 1],
                                 f"both waypoints must fit for this to be a "
                                 f"test about the runner-up ({fix.detail})")
                self.assertEqual(fix.k, whole_at, fix.detail)
                self.assertEqual(
                    fix.second, fix.candidates[thin_at]["inliers"],
                    f"second is not the thin waypoint's count: candidates "
                    f"{sorted(fix.candidates.items())} ({fix.detail})")
                self.assertGreater(fix.second, 0, fix.detail)
                self.assertLess(
                    fix.second, fix.inliers / 2.0,
                    f"second ({fix.second}) is not below the winner "
                    f"({fix.inliers}) -- the win is being reported as thin "
                    f"when it is a landslide, or as a landslide either way "
                    f"({fix.detail})")

    def test_second_k_and_second_dx_name_the_runner_up(self):
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
        solo = chain.Chain([_waypoint(self.warp(1.00), 0, "solo")])
        fix = solo.locate(self.warp(1.03), k_hint=0, window=0)
        self.assertIsNotNone(fix)
        self.assertEqual(sorted(fix.candidates), [0])
        self.assertEqual(
            fix.second, 0,
            f"with one candidate there is no runner-up, and 0 is what says so "
            f"({fix.detail})")
        self.assertIsNone(fix.second_k, fix.detail)
        self.assertEqual(fix.second_dx, 0.0, fix.detail)

    def test_second_reaches_the_caller_in_the_dict_and_the_log_line(self):
        # chain_walk records `fix.as_dict()` per iteration and that JSON is the
        # only record a later reader has, so a `second` that never leaves the
        # object is a field nobody can judge a win by.
        ch = chain.Chain([_waypoint(self.warp(1.00), 0, "whole"),
                          self._thin(1.06, 1)])
        fix = ch.locate(self.warp(1.03), k_hint=0, window=1)
        self.assertIsNotNone(fix)
        self.assertLess(fix.second, fix.inliers, fix.detail)
        self.assertEqual(fix.as_dict()["second"], fix.second)
        self.assertIn(f"second={fix.second}", fix.detail)


# --------------------------------------------------------------------------
# tools/chain_validate.py -- the evidence tool that produces the go/no-go.
# Its bookkeeping is as load-bearing as the sensor: a validator that scores the
# wrong frames against the wrong index prints a plausible number and nothing
# else looks wrong.
# --------------------------------------------------------------------------

sys.path.insert(0, os.path.join(_ROOT, "tools"))
import chain_validate                                            # noqa: E402


def _tiny_corpus(d, n=9, note_line=True):
    """`n` small frames + an index.jsonl whose loader index is NOT the position.

    A leading `{"kind": "note"}` row is what `world_log` recordings actually
    contain (`world_log/20260901_235855_anchor_calib` opens with one), and
    `_from_index_jsonl` counts it while dropping it -- so every row's `i` is
    its position PLUS ONE. That is the divergence finding 3 is about, and it is
    reproduced here rather than described.
    """
    import cv2
    import json
    base = cv2.imread(CORRIDOR, cv2.IMREAD_COLOR)
    small = cv2.resize(base, (480, 270))
    h, w = small.shape[:2]
    lines = []
    if note_line:
        lines.append(json.dumps({"kind": "note", "t": 0.0, "name": "start"}))
    for i in range(n):
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0.0, 1.0 + 0.02 * i)
        cv2.imwrite(os.path.join(d, f"{i:05d}.jpg"),
                    cv2.warpAffine(small, M, (w, h),
                                   borderMode=cv2.BORDER_REFLECT))
        lines.append(json.dumps({"kind": "frame", "t": 0.25 * i,
                                 "file": f"{i:05d}.jpg", "heading": None,
                                 "stick": {"lx": 0.0, "ly": -0.45}}))
    with open(os.path.join(d, "index.jsonl"), "w") as f:
        f.write("\n".join(lines) + "\n")


def _stubbed_sweep(fix_for, hint_mode="oracle", n=15, every=3):
    """`chain_validate.sweep` with `Chain.locate` STUBBED; (hints, report).

    `fix_for(k_hint, call_index)` returns a `_StubFix` or None, so a test
    controls the placements AND the abstentions exactly. That second half is
    what pins the abstention bookkeeping: with the real sensor, which frames
    abstain is a property of the pictures and no assertion can be exact.

    15 frames at every=3 is the corpus for both classes below: 5 waypoints,
    and held-out positions 1,2,4,5,7,8,10,11,13,14.
    """
    import tempfile
    seen = []

    def stub(self_, img, k_hint, window=3):
        i = len(seen)
        seen.append(k_hint)
        return fix_for(k_hint, i)

    real = chain.Chain.locate
    chain.Chain.locate = stub
    try:
        with tempfile.TemporaryDirectory() as d:
            _tiny_corpus(d, n=n)
            rep = chain_validate.sweep(d, every=every, far_samples=0,
                                       hint_mode=hint_mode,
                                       log=lambda *a: None)
    finally:
        chain.Chain.locate = real
    return seen, rep


class ValidatorGroundTruthIsThePosition(unittest.TestCase):
    """Finding 3: the chain is built from LIST POSITIONS, so the truth must be.

    `chain_rows = rows[::every]` selects by position while the ground truth was
    `row["i"] / every` -- the loader's own count, which three of the four
    loaders can renumber by dropping a row. On a corpus where they diverge, the
    WAYPOINT frames land in the held-out set and are scored against a true
    position of 0.2, and the tool prints a perfectly plausible go/no-go.
    (Measured on `world_log/20260901_235855_anchor_calib`, one of the SPEC's
    own corpora: |err| <= 1 read 78.7% under the bug and 98.0% after the fix.)

    A frame cannot be both a waypoint and a held-out test of that waypoint, so
    that overlap is the invariant. `sweep()` asserts it internally as well; if
    the internal guard fires first this test still fails, which is the point.
    """

    EVERY = 3

    def _sweep(self, **kw):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _tiny_corpus(d, n=9)
            rep = chain_validate.sweep(d, every=self.EVERY, far_samples=0,
                                       log=lambda *a: None, **kw)
            waypoint_paths = {os.path.basename(p) for p in
                              [os.path.join(d, f"{i:05d}.jpg")
                               for i in range(0, 9, self.EVERY)]}
        return rep, waypoint_paths

    def test_the_loader_index_really_does_diverge_from_the_position(self):
        # Anti-vacuity: if this corpus stopped reproducing the divergence, the
        # tests below would pass while guarding nothing.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _tiny_corpus(d, n=9)
            rows = chain_validate.load_frames(d)
        self.assertEqual([r["pos"] for r in rows], list(range(9)))
        self.assertEqual([r["i"] for r in rows], list(range(1, 10)),
                         "the note row should push every loader index up by one")

    def test_no_waypoint_frame_is_also_a_held_out_frame(self):
        rep, waypoints = self._sweep()
        self.assertEqual(rep["waypoints"], 3)
        self.assertEqual(rep["held_out"], 6)
        self.assertEqual(rep["held_out"], rep["frames"] - rep["waypoints"],
                         "the held-out set must be the complement of the chain")
        held_pos = sorted(r["pos"] for r in rep["rows"])
        self.assertEqual(held_pos, [1, 2, 4, 5, 7, 8],
                         f"held-out positions {held_pos} include a waypoint "
                         f"position (waypoints are {sorted(waypoints)})")

    def test_the_true_position_is_the_position_over_every(self):
        rep, _ = self._sweep()
        for r in rep["rows"]:
            with self.subTest(pos=r["pos"]):
                self.assertAlmostEqual(r["true"], r["pos"] / self.EVERY,
                                       places=3)
                self.assertNotEqual(
                    r["true"], r["i"] / self.EVERY,
                    "the true position is being taken from the loader's index")

    def test_the_divergence_is_reported_not_swallowed(self):
        rep, _ = self._sweep()
        self.assertEqual(rep["rows_renumbered_by_loader"], 9)
        self.assertIn("position", chain_validate._summary(rep))


class _StubFix:
    """The minimum of `chain.Fix` that `sweep` and `reached` read."""

    def __init__(self, k, scale=1.0):
        self.k = k
        self.k_float = float(k)
        self.inliers = 99
        self.second = 0
        self.dx = 0.0
        self.dy = 0.0
        self.scale = scale
        self.detail = "stub"


class ValidatorHintModeIsHonest(unittest.TestCase):
    """Finding 2: the default hint is an ORACLE and must say so.

    The tool handed `locate` the previous TRUE index and its docstring called
    that "the same prior the controller will have, because the controller
    always knows which waypoint it last reached". It is not: the SPEC's
    controller sets k from THIS SENSOR's own output, so a placement error feeds
    back into the next window. Replayed through the shipped tool on 160
    held-out office-drive frames, the difference is abstentions 48 -> 71 and
    the true position outside the search window on 32 frames (`--hint closed`,
    `agent_progress/closed-loop/fix-sensor/office_795_200_*.json`).

    `locate` is STUBBED here so the hints are the only thing under test: what
    is pinned is where the hint comes from, not whether the sensor is right.
    """

    EVERY = 3

    def _hints(self, hint_mode, fix_for):
        """Run a sweep with `Chain.locate` stubbed; return (hints, report)."""
        # `every` is forwarded rather than left to the helper's default, so
        # the class attribute above stays load-bearing: a knob a caller can
        # set and that changes nothing is 10.18's shape.
        return _stubbed_sweep(lambda k, i: fix_for(k), hint_mode=hint_mode,
                              every=self.EVERY)

    def test_oracle_mode_hands_over_the_true_index(self):
        seen, rep = self._hints("oracle", lambda k: _StubFix(0, scale=0.5))
        self.assertEqual(rep["hint_mode"], "oracle")
        self.assertEqual(seen, [int(r["true"]) for r in rep["rows"]])
        self.assertEqual(seen[-1], 4, f"the oracle hint must track the truth "
                                      f"to the end of the chain: {seen}")

    def test_closed_mode_hands_over_only_what_the_sensor_earned(self):
        # The stub never reports reaching anything, so a closed loop is stuck
        # at k = 0 while the world walks away from it. Under the oracle the
        # same run would climb to 4.
        seen, rep = self._hints("closed", lambda k: _StubFix(0, scale=0.5))
        self.assertEqual(rep["hint_mode"], "closed")
        self.assertEqual(set(seen), {0},
                         f"closed mode is not using the controller's own k: "
                         f"hints were {seen}")
        self.assertEqual(rep["final_k"], 0)
        self.assertGreater(
            rep["true_outside_window"], 0,
            "with k pinned at 0 the truth must leave the window, and the "
            "report must say so -- that is the failure the oracle hides")

    def test_closed_mode_does_advance_when_the_sensor_says_so(self):
        # The control for the test above: closed mode is not simply "k = 0".
        # A sensor reporting the next waypoint reached, every frame, must move
        # k by exactly one each time.
        seen, rep = self._hints("closed",
                                lambda k: _StubFix(k + 1, scale=1.0))
        self.assertEqual(seen, list(range(len(seen))),
                         f"k must advance one waypoint per 'reached': {seen}")
        self.assertEqual(rep["final_k"], seen[-1] + 1)

    def test_closed_mode_advances_no_further_than_one_window(self):
        # `k = min(fix.k, k + window)`. A sensor claiming a distant waypoint
        # cannot teleport the controller's belief past its own window -- the
        # rule the SPEC fixes, pinned here rather than restated.
        window = 3
        seen, rep = self._hints("closed", lambda k: _StubFix(k + 10, scale=1.0))
        self.assertEqual(seen, list(range(0, window * len(seen), window)),
                         f"advance was not capped at k + {window}: {seen}")

    def test_the_headline_cannot_be_quoted_without_its_provenance(self):
        _, rep = self._hints("oracle", lambda k: _StubFix(0, scale=0.5))
        text = chain_validate._summary(rep)
        self.assertIn("ORACLE", text)
        self.assertIn("GO/NO-GO under the ORACLE hint", text)
        self.assertIn("ceiling", rep["hint_note"])

    def test_far_samples_is_resolved_at_call_time(self):
        # 10.18 again: `def sweep(..., far_samples=FAR_SAMPLES)` bound the knob
        # when the def ran, so redirecting the module changed nothing.
        import tempfile
        saved = chain_validate.FAR_SAMPLES
        try:
            chain_validate.FAR_SAMPLES = 0
            with tempfile.TemporaryDirectory() as d:
                _tiny_corpus(d, n=9)
                rep = chain_validate.sweep(d, every=self.EVERY,
                                           log=lambda *a: None)
        finally:
            chain_validate.FAR_SAMPLES = saved
        self.assertEqual(rep["far_samples"], 0,
                         "the module knob was not read at call time")
        self.assertTrue(all(r["far_inliers"] is None for r in rep["rows"]))


class ValidatorNeverAveragesAnAbstentionIntoTheAccuracy(unittest.TestCase):
    """Property 11 / SPEC report requirement 2.

    "ABSTENTIONS, separately. `locate()` returning None is not a wrong answer
    and must never be averaged into one." The tool does it correctly --
    `within_*` over PLACED, `within_*_all` over ALL held out, both printed --
    and until 2026-09-07 nothing asserted either family, nor `abstained`, nor
    `abstain_rate`. A mutant that redefined `within_1` as
    `sum(e <= 1) / len(sel)` -- the forbidden averaging, still printed under
    the label "of PLACED" -- left all 28 tests green. That is the number the
    manager reads the go/no-go from.

    THE ARITHMETIC IS EXACT BY CONSTRUCTION, which is why `locate` is stubbed:
    15 frames at every=3 hold out positions 1,2,4,5,7,8,10,11,13,14, whose
    true positions are pos/3 and whose NEAREST waypoint is alternately the
    oracle hint itself and one past it. So a stub answering `k = hint` scores
    |err| = 0,1,0,1,... down the list, and abstaining on alternate frames
    selects one population or the other with no picture involved.
    """

    def _run(self, place_when):
        return _stubbed_sweep(
            lambda k, i: _StubFix(k) if place_when(i) else None)

    def test_the_alternating_error_pattern_this_class_rests_on(self):
        # Anti-vacuity. Every expected number below is derived from this
        # pattern, so measure it once instead of assuming it.
        _, rep = self._run(lambda i: True)
        errs = [abs(r["k"] - int(r["true"] + 0.5)) for r in rep["rows"]]
        self.assertEqual(errs, [0, 1] * 5,
                         f"the corpus no longer alternates: {errs}")

    def test_accuracy_of_placed_frames_excludes_the_abstentions(self):
        s = self._run(lambda i: i % 2 == 0)[1]["all"]     # places every err=0
        self.assertEqual((s["frames"], s["placed"], s["abstained"]),
                         (10, 5, 5))
        self.assertEqual(s["abstain_rate"], 0.5)
        self.assertEqual(
            (s["within_0"], s["within_1"], s["within_2"]), (1.0, 1.0, 1.0),
            "within_* is over PLACED frames: all five placed frames are exact, "
            "so anything below 1.0 has averaged the five abstentions in")
        self.assertEqual(
            (s["within_0_all"], s["within_1_all"], s["within_2_all"]),
            (0.5, 0.5, 0.5),
            "within_*_all is over ALL held-out frames, counting an abstention "
            "as not-placed-within-k: 5 of 10")
        self.assertEqual(
            sum(s["hist_nearest"].values()), s["placed"],
            f"the histogram counted an abstention as an error: "
            f"{s['hist_nearest']} over {s['placed']} placed")

    def test_the_other_half_scores_the_other_population(self):
        # The same corpus, the complementary five frames, all off by one.
        s = self._run(lambda i: i % 2 == 1)[1]["all"]
        self.assertEqual((s["placed"], s["abstained"]), (5, 5))
        self.assertEqual((s["within_0"], s["within_1"]), (0.0, 1.0))
        self.assertEqual((s["within_0_all"], s["within_1_all"]), (0.0, 0.5))
        self.assertEqual(s["hist_nearest"], {"1": 5})

    def test_with_nothing_abstaining_the_two_denominators_agree(self):
        # The control. Without it "the two families differ" could be satisfied
        # by two unrelated formulas rather than by two honest denominators.
        s = self._run(lambda i: True)[1]["all"]
        self.assertEqual((s["placed"], s["abstained"]), (10, 0))
        self.assertEqual(s["abstain_rate"], 0.0)
        for k in ("0", "1", "2"):
            self.assertEqual(s[f"within_{k}"], s[f"within_{k}_all"],
                             f"with no abstentions within_{k} and "
                             f"within_{k}_all must be the same number")
        self.assertEqual((s["within_0"], s["within_1"]), (0.5, 1.0))

    def test_the_summary_prints_both_denominators_with_their_own_numbers(self):
        # The manager reads the printed summary, not the JSON. A tool that
        # computes both and prints one is the same finding one line later.
        rep = self._run(lambda i: i % 2 == 0)[1]
        lines = chain_validate._summary(rep).splitlines()
        placed = [l for l in lines if "of PLACED" in l]
        every = [l for l in lines if "of ALL held out" in l]
        self.assertTrue(placed, "the summary no longer reports of-PLACED "
                                "accuracy")
        self.assertTrue(every, "the summary no longer reports the "
                               "of-ALL-held-out accuracy, so an abstention "
                               "rate can be read past")
        self.assertIn("abstain=", placed[0])
        self.assertIn("100.0%", placed[0])
        self.assertIn("50.0%", every[0])
        self.assertNotIn(
            "100.0%", every[0],
            f"the of-ALL line is printing the of-PLACED numbers: {every[0]!r}")


class TheCommandedHeadingRidesAlong(unittest.TestCase):
    """The recorder writes `cam` (the commanded camera heading) beside the
    compass read; chain_walk.plan_indices falls back to it when the compass
    abstained. A loader that drops it makes every abstained corner blind."""

    def test_load_carries_cam_and_tolerates_its_absence(self):
        import json, shutil, tempfile
        d = tempfile.mkdtemp(prefix="chain_cam_")
        try:
            src = os.path.join(_ROOT, "test_fixtures", "chain", "corridor_1920.jpg")
            for i in range(2):
                shutil.copy(src, os.path.join(d, f"{i:04d}.jpg"))
            with open(os.path.join(d, "meta.jsonl"), "w") as fh:
                fh.write(json.dumps({"index": 0, "heading": None, "cam": 87.2,
                                     "lx": 0.0, "ly": 0.0}) + "\n")
                fh.write(json.dumps({"index": 1, "heading": 90.5,
                                     "lx": 0.0, "ly": -0.35}) + "\n")
            ch = chain.Chain.load(d, log=lambda m: None)
            self.assertEqual([w.cam for w in ch.waypoints], [87.2, None])
            self.assertEqual([w.heading for w in ch.waypoints], [None, 90.5])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
