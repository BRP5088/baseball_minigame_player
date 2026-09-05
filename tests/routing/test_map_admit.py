"""The admission gates must ADMIT a real place and REJECT everything else.

A one-sided test would be worthless here. `admit()` rejects 15 of 15 clusters
on the real corpus, so a test that only checks "nothing was admitted" passes
just as happily with every gate deleted, or with `admitted` hard-wired False.
Every case below therefore comes in a matched pair: the same corpus, one
thing changed, opposite verdicts.

Offline. Reads frames already on disk and writes only to a temp directory;
nothing here touches places/, world_map.json or the console.
"""
import json
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

import map_propose as mp

RUN = "explore/20260904_152521_bar_area"
# Cluster 8 of the bar_area run: five frames of the bar counter, headings
# 314-331, one per stop 0-4. Held-out member 00002 is the failure frame the
# other four must be able to name.
PLACE = ["00016.jpg", "00024.jpg", "00032.jpg", "00040.jpg"]
HELD_OUT = "00002.jpg"
# Cluster 9, headings 18-23 — a different view entirely, and the negative
# control for G5: no cluster of bar-counter frames should name it.
ELSEWHERE = "00113.jpg"


def _root():
    here = _ROOT
    return os.path.join(here, RUN)


_REAL = []


def _real_corpus():
    """admit() over the whole bar_area run — computed once, it is slow."""
    if not _REAL:
        here = _ROOT
        fail = os.path.join(here, "overnight", "failframes")
        if not os.path.isdir(fail):
            raise AssertionError(f"fixture missing: {fail}")
        _REAL.append(mp.admit([_root()], [fail], failures=[fail],
                              log=lambda *a: None))
    return _REAL[0]


class AdmissionGates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        src = _root()
        if not os.path.isdir(src):
            # MUST NOT SILENTLY SKIP: a fixture that has moved has to fail
            # loudly, or the gates go uncovered while the suite reports green.
            raise AssertionError(f"fixture run missing: {src}")
        cls.tmp = tempfile.mkdtemp(prefix="admit_")
        cls.rundir = os.path.join(cls.tmp, "run")
        cls.faildir = os.path.join(cls.tmp, "fail")
        cls.otherdir = os.path.join(cls.tmp, "other")
        for d in (cls.rundir, cls.faildir, cls.otherdir):
            os.makedirs(d)
        rows = []
        for stop, name in enumerate(PLACE):
            shutil.copy(os.path.join(src, name), os.path.join(cls.rundir, name))
            rows.append({"file": f"run/{name}", "stop": stop})
        # The failure directory is passed as BOTH an --extra and a --failures
        # population, which is exactly how the real run is invoked
        # (overnight/failframes is both). That is the only arrangement in
        # which the hold-out does any work.
        shutil.copy(os.path.join(src, HELD_OUT), os.path.join(cls.faildir, HELD_OUT))
        shutil.copy(os.path.join(src, ELSEWHERE), os.path.join(cls.otherdir, ELSEWHERE))
        with open(os.path.join(cls.rundir, "index.jsonl"), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _admit(self, failures):
        # `failures` is handed in as an extra source too: the failure frames
        # are ON DISK among the candidates, and the hold-out is what keeps
        # them out of the pool.
        return mp.admit([self.rundir], list(failures), failures=list(failures),
                        log=lambda *a: None)

    def test_admits_a_real_place_that_names_its_failure(self):
        """Four corroborating views of one spot, and they name the failure."""
        res = self._admit([self.faildir])
        ok = [r for r in res if r["admitted"]]
        self.assertTrue(ok, f"nothing admitted; gates: "
                            f"{[r['gates'] for r in res]}")
        self.assertTrue(any(r["rescues"] for r in ok))

    def test_rejects_when_the_failure_is_somewhere_else(self):
        """Same frames, same clusters — only the failure population changes.

        This is the pair for the test above. G5 is the whole difference, so
        deleting G5 makes these two cases identical and one of them fails.
        """
        res = self._admit([self.otherdir])
        self.assertFalse([r for r in res if r["admitted"]])
        for r in res:
            self.assertFalse(r["gates"]["G5 recoverability"][0])

    def test_failure_frames_are_held_out_of_the_pool(self):
        """A frame may not be the reference that rescues itself.

        HELD_OUT sits in the run directory too. If the hold-out is broken it
        joins the pool, matches itself perfectly, and G5 passes for a reason
        that proves nothing.
        """
        res = self._admit([self.faildir])
        for r in res:
            self.assertNotEqual(os.path.basename(r["seed"]), HELD_OUT,
                                "a failure frame was seeded as a candidate")
            for _name, hit in r["rescues"]:
                self.assertLess(hit, 1000,
                                "a self-match slipped into the pool")

    def test_real_corpus_admits_nothing(self):
        """The measured result on the whole bar_area run: 0 of 15."""
        res = _real_corpus()
        self.assertEqual([r["cluster"] for r in res if r["admitted"]], [])
        self.assertGreaterEqual(len(res), 10)

    def test_each_gate_rejects_on_the_real_corpus(self):
        """Every gate must still be doing work.

        Measured 2026-09-04 over the 15 clusters of the bar_area run:
        G2 rejects 4, G3 rejects 12, G4 rejects 12, G5 rejects 15. Pinned with
        margin, because "0 admitted" on its own passes just as well with a
        gate neutered — a threshold moved to zero, a condition replaced by
        True — and the other gates covering for it. A drop here is that
        neutering showing up.
        """
        res = _real_corpus()
        got = {g: sum(1 for r in res if not r["gates"][g][0])
               for g in res[0]["gates"]}
        for gate, floor in (("G2 corroboration", 3), ("G3 non-disruption", 8),
                            ("G4 discrimination", 8), ("G5 recoverability", 12)):
            self.assertGreaterEqual(
                got[gate], floor,
                f"{gate} rejects {got[gate]} clusters, measured ~"
                f"{floor}+; has it been weakened? full profile {got}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
