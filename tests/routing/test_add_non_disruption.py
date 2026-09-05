"""places.add() must REFUSE a reference that breaks identifications that work,
and identify() must stop being read as a POSITION.

WHY THIS EXISTS
---------------
`map_propose.admit()` puts a candidate through five gates before anyone may
add it. The two INTERACTIVE write paths — `Bretts_walk.py label` and
`brett_walk.mark` — went through none of them; their only guard was a
200-keypoint structure floor, and that lives in the callers.

Measured 2026-09-05 against the real places/ (9 references, 4 rooms) with the
160-frame bar_area run as witnesses: ONE frame taken standing at
`bar_pool_room` and labelled `bar_pool_room` in perfectly good faith broke 22
of 37 working identifications, every one of them into a CONFIDENT WRONG ROOM.
Over all 640 (frame, room) pairs of that run, 48% are poison of that kind.

WHY EVERY CASE HERE IS A MATCHED PAIR
-------------------------------------
A test that only checks "the bad frame was refused" passes just as happily
with `refuse` hard-wired True, which would make `label` and `mark` useless —
and those two commands are the only way a human can fix the localiser where it
fails. So every refusal below is paired with an acceptance that must survive:
same code path, same witnesses, one thing changed.

The gates are also separated from each other. G1 (the candidate already reads
as a DIFFERENT room) needs no witnesses at all; G2 (the addition breaks
witness identifications) is the only gate that can see a poison frame the
localiser abstains on — 34% of the abstaining pairs in that measurement. Each
is tested with the other unable to fire, so neither can cover for the other's
removal.

Offline. Reads frames already on disk and writes only to a temp directory;
nothing here touches places/, world_map.json or the console.
"""
import glob
import os
import os as _os
import shutil
import sys
import tempfile
import unittest

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import places

RUN = os.path.join(_ROOT, "explore", "20260904_152521_bar_area")

# The demonstration frame. Stop 0 is AT bar_pool_room, so labelling it
# `bar_pool_room` is honest about position — but at heading 61 the camera is
# looking INTO the portrait room, and identify() matches views.
POISON = "00004.jpg"
POISON_ROOM = "bar_pool_room"

# The positive control: the same stop, heading 286, actually looking at the
# pool room. Measured: 0 breaks, 2 abstentions rescued.
GOOD = "00001.jpg"
GOOD_ROOM = "bar_pool_room"

# A poison frame the localiser ABSTAINS on (best match 199, ratio 1.08), so G1
# cannot see it. Filed under dealer_table it newly names five bar frames
# `dealer_table`. This is the case that makes G2 load-bearing.
QUIET = "00082.jpg"
QUIET_ROOM = "dealer_table"

# Witnesses, chosen to be the frames those two candidates actually break plus
# enough unaffected ones to keep the set honest. Small on purpose: each
# witness costs an ORB detection, and this file must stay a test, not a sweep.
WITNESSES = ["00010.jpg", "00018.jpg", "00019.jpg", "00027.jpg", "00034.jpg",
             "00096.jpg", "00104.jpg", "00111.jpg", "00112.jpg", "00119.jpg",
             "00124.jpg", "00145.jpg"]


class AddNonDisruption(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(RUN):
            # MUST NOT SILENTLY SKIP. A fixture that has moved has to fail
            # loudly, or this whole file goes uncovered while the suite
            # reports green — which is exactly how read_ban_counter lost its
            # coverage for a week.
            raise AssertionError(f"fixture run missing: {RUN}")
        src_places = os.path.join(_ROOT, "places")
        if not os.path.isdir(src_places):
            raise AssertionError(f"fixture missing: {src_places}")

        # A whole project-shaped temp tree, because witness_paths() resolves
        # its archives beside the REFERENCE ROOT. places/ is copied so that a
        # bug here can never write into the real reference set.
        cls.tmp = tempfile.mkdtemp(prefix="places_add_check_")
        cls.root = os.path.join(cls.tmp, "places")
        shutil.copytree(src_places, cls.root)
        cls.corpus = os.path.join(cls.tmp, "explore", "corpus")
        os.makedirs(cls.corpus)
        for n in WITNESSES:
            shutil.copy(os.path.join(RUN, n), os.path.join(cls.corpus, n))
        cls.witnesses = sorted(glob.glob(os.path.join(cls.corpus, "*.jpg")))
        cls.poison = os.path.join(RUN, POISON)
        cls.good = os.path.join(RUN, GOOD)
        cls.quiet = os.path.join(RUN, QUIET)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _check(self, room, img, witnesses=None):
        return places.check_add(
            room, img, root=self.root,
            witnesses=self.witnesses if witnesses is None else witnesses,
            log=None)

    def _files(self, room):
        return sorted(glob.glob(os.path.join(self.root, room, "*")))

    # ---- the pair that matters ------------------------------------------

    def test_a_disruptive_reference_is_refused(self):
        """The demonstrated poison add. add() must raise and write nothing."""
        before = self._files(POISON_ROOM)
        with self.assertRaises(places.DisruptiveReference) as cm:
            places.add(POISON_ROOM, self.poison, root=self.root,
                       log=None)
        self.assertEqual(self._files(POISON_ROOM), before,
                         "a refused add still wrote a file")
        # The message has to name what breaks. A refusal nobody can act on
        # gets overridden blind, and the override writes the poison anyway.
        self.assertIn(POISON_ROOM, str(cm.exception))
        self.assertIn("portrait_room", str(cm.exception))

    def test_a_good_reference_is_still_accepted(self):
        """THE POSITIVE CONTROL, and the reason this file is not one-sided.

        Without it every assertion above passes with `refuse` hard-wired True,
        and `label` and `mark` — the only way a human can fix the localiser
        where it fails — stop working entirely.
        """
        before = self._files(GOOD_ROOM)
        p = places.add(GOOD_ROOM, self.good, root=self.root, log=None)
        self.assertTrue(os.path.exists(p))
        self.assertEqual(len(self._files(GOOD_ROOM)), len(before) + 1)
        os.remove(p)        # leave the reference set as it was found

    # ---- the two gates, each with the other unable to fire ---------------

    def test_g1_refuses_with_no_witnesses_at_all(self):
        """CONTRADICTION needs no corpus: it is one identify() against the
        references being added to. Measured over 640 pairs, 150 of 150 adds
        that contradicted a confident identify() were poison."""
        rep = self._check(POISON_ROOM, self.poison, witnesses=[])
        self.assertEqual(rep["witnesses"], 0)
        self.assertEqual(rep["wrong"], [], "G2 fired; this case must isolate G1")
        self.assertEqual(rep["contradiction"], "portrait_room")
        self.assertTrue(rep["refuse"])

    def test_g2_refuses_a_frame_g1_cannot_see(self):
        """The localiser ABSTAINS on this frame, so G1 is silent — and filing
        it under dealer_table still newly names five bar frames dealer_table."""
        rep = self._check(QUIET_ROOM, self.quiet)
        self.assertIsNone(rep["contradiction"],
                          "G1 fired; this case must isolate G2")
        self.assertGreaterEqual(len(rep["wrong"]), 5)
        self.assertTrue(rep["refuse"])
        for _p, b, a in rep["wrong"]:
            self.assertIsNotNone(b[0])
            self.assertEqual(a[0], QUIET_ROOM)

    def test_the_quiet_frame_passes_when_nothing_witnesses_it(self):
        """The pair for the case above: same frame, same label, no witnesses.

        It must be ACCEPTED, which proves the refusal above came from G2 and
        not from something else — and it is also the honest statement of the
        limitation, since a witness set that does not cover the area cannot
        see this class of poison at all.
        """
        rep = self._check(QUIET_ROOM, self.quiet, witnesses=[])
        self.assertFalse(rep["refuse"])

    # ---- the properties the gates rest on --------------------------------

    def test_the_at_risk_prefilter_changes_no_answer(self):
        """AT_RISK is an exact skip, not a tuned threshold.

        Filing under room R can only RAISE R's score, so a witness scoring
        below MIN_MATCHES / MIN_RATIO against the candidate can neither take
        the lead nor spoil the winner's ratio. Removing the filter must
        therefore produce the IDENTICAL verdict, only slower — if it does not,
        the derivation is wrong and frames are being skipped that matter.
        """
        full = self._check(QUIET_ROOM, self.quiet)
        real = places.AT_RISK
        places.AT_RISK = 0
        try:
            unfiltered = self._check(QUIET_ROOM, self.quiet)
        finally:
            places.AT_RISK = real
        self.assertEqual(sorted(p for p, _b, _a in full["wrong"]),
                         sorted(p for p, _b, _a in unfiltered["wrong"]))
        self.assertEqual(len(full["faded"]), len(unfiltered["faded"]))
        self.assertGreater(unfiltered["at_risk"], full["at_risk"],
                           "the filter skipped nothing, so this proves nothing")

    def test_a_frame_does_not_witness_against_itself(self):
        """A candidate re-added from the archive would self-match perfectly,
        flip to its new room, and be refused for the one break it is
        guaranteed to cause. map_propose.admit() holds its failure frames out
        of the candidate pool for the mirror-image reason."""
        mine = os.path.join(self.corpus, "self.jpg")
        shutil.copy(self.poison, mine)
        try:
            rep = places.check_add(
                POISON_ROOM, mine, root=self.root,
                witnesses=self.witnesses + [mine], log=None)
        finally:
            os.remove(mine)
        self.assertNotIn(mine, [p for p, _b, _a in rep["wrong"]])

    def test_a_faded_identification_warns_but_does_not_refuse(self):
        """Losing a confident answer to an ABSTENTION is not the fatal class.

        Measured on this project: identify() has never once named a wrong room
        in a failed confirmation — 10 of 10 were abstentions — and an
        abstention is advisory downstream, while a confident wrong room sends
        a route walking at a doorway on another floor. So `faded` is reported
        and `wrong` is what refuses.
        """
        rep = self._check(GOOD_ROOM, self.good)
        self.assertFalse(rep["refuse"])
        # and the classes must be disjoint: an entry that ends confidently
        # somewhere else is `wrong`, never `faded`.
        for _p, _b, a in rep["faded"]:
            self.assertIsNone(a[0])

    def test_an_unchecked_add_says_so(self):
        """No witnesses is NOT a clean bill of health.

        This is the diagnosis-catalogue shape the whole project keeps paying
        for: a check that could not run must not read like a check that found
        nothing.
        """
        places._warned.discard("no-witnesses")
        bare = tempfile.mkdtemp(prefix="places_bare_")
        try:
            shutil.copytree(self.root, os.path.join(bare, "places"))
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rep = places.check_add(GOOD_ROOM, self.good,
                                       root=os.path.join(bare, "places"),
                                       log=None)
            self.assertEqual(rep["witnesses"], 0)
            self.assertIn("UNCHECKED", buf.getvalue())
        finally:
            shutil.rmtree(bare, ignore_errors=True)

    def test_witnesses_are_found_beside_the_reference_root(self):
        """Not against the process CWD. A check on a temporary reference set
        must not drag the production corpus in, and a real `label` run must
        find explore/ and world_log/ whatever directory it was started from."""
        here = os.getcwd()
        os.chdir(tempfile.gettempdir())
        try:
            got = places.witness_paths(root=self.root)
        finally:
            os.chdir(here)
        self.assertEqual(sorted(got), self.witnesses)

    def test_the_override_still_writes(self):
        """A refusal a human cannot overrule is a broken tool: the localiser
        can itself be wrong, and `label` exists to correct it."""
        before = self._files(POISON_ROOM)
        p = places.add(POISON_ROOM, self.poison, root=self.root,
                       check=False, log=None)
        try:
            self.assertTrue(os.path.exists(p))
            self.assertEqual(len(self._files(POISON_ROOM)), len(before) + 1)
        finally:
            os.remove(p)

    def test_add_defaults_to_checking(self):
        """CHECK_ADDS is the master switch and it must ship ON.

        Pinned as a literal rather than compared against the constant it
        guards — `assert places.CHECK_ADDS == places.CHECK_ADDS` is the shape
        that passes forever.
        """
        self.assertIs(places.CHECK_ADDS, True)


class ViewAnswerIsNotAPosition(unittest.TestCase):
    """The other half of what the write-path audit turned up.

    `identify()` matches a VIEW; every caller reads it as a POSITION. These
    pin the two measurements that say so, so that nobody repairs the symptom
    by moving MIN_MATCHES — the populations overlap, and raising it would
    discard genuine arrivals first.
    """

    # From the four sweeps map_unknown.py took AT bar_pool_room (it ran
    # go_to_node_verified before every fan arm). Same standing position, two
    # different confident answers.
    AT_NODE_LOOKING_AT_IT = "00001.jpg"          # heading 286
    AT_NODE_LOOKING_AWAY = "00004.jpg"           # heading 61
    # The WEAKEST of the four at-node views, and the STRONGEST view from one
    # short push away (0.35s at speed 0.30). Grouped by the sweep's `note`:
    # the run's stop ids collide across fan arms and would mix the two.
    AT_NODE_WEAKEST = "00081.jpg"                # "at bar_pool_room, before fan 20"
    ONE_STEP_OFF_BEST = "00134.jpg"              # "fan 60, step 1"

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(RUN):
            raise AssertionError(f"fixture run missing: {RUN}")
        cls.root = os.path.join(_ROOT, "places")
        cls.refs = places.load_keypoints(cls.root)

    def _v(self, name):
        p = os.path.join(RUN, name)
        return places.view_report(p, root=self.root, refs=self.refs)

    def test_one_position_gives_two_confident_answers(self):
        """Turning the camera changes the room, from the SAME verified pose."""
        a = self._v(self.AT_NODE_LOOKING_AT_IT)
        b = self._v(self.AT_NODE_LOOKING_AWAY)
        self.assertEqual(a["room"], "bar_pool_room")
        self.assertEqual(b["room"], "portrait_room")
        for r in (a, b):
            self.assertGreaterEqual(r["matches"], 300)
            self.assertGreaterEqual(r["ratio"], 2.5)

    def test_one_step_off_the_node_outscores_the_node(self):
        """So no score threshold can separate "at it" from "one step off it".

        Measured over the whole run, best bar_pool_room score per group:
        at the node 540/521/517/500, one step off 507/469/446/434. The at-node
        MINIMUM is below the one-step-off MAXIMUM. If this ever fails, the
        reference set has changed and the measurement needs retaking — it does
        not mean a threshold has become viable.
        """
        at = self._v(self.AT_NODE_WEAKEST)
        off = self._v(self.ONE_STEP_OFF_BEST)
        self.assertEqual(at["room"], "bar_pool_room")
        self.assertEqual(off["room"], "bar_pool_room")
        self.assertGreater(off["matches"], at["matches"])

    def test_the_report_never_claims_a_position(self):
        """Even on the most confident frame in the corpus."""
        r = self._v(self.AT_NODE_LOOKING_AT_IT)
        self.assertIsNone(r["position"])
        self.assertIn("LOOKING AT", r["caveat"])

    def test_the_report_cannot_drift_from_identify(self):
        """Same frame, same decision. Two copies of a rule is how the FIFO
        button bits and the keyboard KEYMAP came to disagree."""
        p = os.path.join(RUN, self.AT_NODE_LOOKING_AWAY)
        r = places.view_report(p, root=self.root, refs=self.refs)
        self.assertEqual((r["room"], r["matches"], r["ratio"]),
                         places.identify(p, root=self.root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
