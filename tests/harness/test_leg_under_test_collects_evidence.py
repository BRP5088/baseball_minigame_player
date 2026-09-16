"""The leg-under-test helper must collect evidence ABOUT THE LEG.

WHAT THIS GUARDS. `overnight/ab_jukebox_leg.py` and
`overnight/ab_stall_on_restored.py` both walked the leg under test with
`gw.walk_link`, which publishes NO leg-end frame: `_LAST_LEG_END` is set inside
`follow()`, right after its post-leg capture and BEFORE `recover_to_node` runs,
and only `follow_verified` pops it and classifies it. So the two harnesses whose
whole purpose is to report a leg's arrival BY FAILURE CLASS produced zero frames
of the leg they tested. There is no `at_bar_jukebox` frame anywhere on disk.
That is OPEN-1, and OPEN-14 was queued to run on top of it.

WHY THE CHECKS ARE ON CALLS, NOT ON SOURCE TEXT. The older
`test_failure_frame_is_the_leg.py` checked this with a source substring, and
CLAUDE.md records that re-introducing the bug with a second assignment passes
such a test. A stub `gw` records what was actually called with what arguments,
so the only way to pass is to genuinely make the call.

MUTATION TESTS (run 2026-09-06, all four fail as they should):
  * swap follow_verified -> walk_link        -> "walks the leg through
                                                follow_verified" fails
  * attempts=1 -> attempts=3                 -> "one attempt" fails
  * drop shots= / start_hint=                -> their checks fail
  * count every kind as leg-end              -> the provenance split fails
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import _harness

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


LEG_END = "the leg's own end"
FALLBACK = "before the attempt (PREVIOUS node) — weak evidence"


class StubGW:
    """Stands in for graph_walk. Records calls; walks nothing."""

    LEG_END_SOURCE = LEG_END

    def __init__(self, kinds, sources, log_lines=(), located="bar_jukebox"):
        self.calls = []
        self._LAST_FAILURE_KINDS = list(kinds)
        self._LAST_FAILURE_SOURCES = list(sources)
        self._log_lines = list(log_lines)
        self._located = located

    def follow_verified(self, m, route, log=print, attempts=3, shots=None,
                        start_hint=None):
        self.calls.append(("follow_verified", dict(
            route=list(route), attempts=attempts, shots=shots,
            start_hint=start_hint)))
        for line in self._log_lines:
            log(line)
        return True, list(route)

    def walk_link(self, m, a, b, log=print):
        # Present ON PURPOSE. If the helper reverts to calling this, the stub
        # records it and the check below names it, rather than the helper
        # failing with an AttributeError that reads like an unrelated bug.
        self.calls.append(("walk_link", {"a": a, "b": b}))

    def locate(self, m, log=print):
        return self._located, "stub"


def run(gw, start="bar_pool_room", target="bar_jukebox", shots="/tmp/shots"):
    return _harness.walk_leg_under_test(gw, object(), start, target,
                                        shots=shots, log=lambda *a: None)


# --- 1. it must go through follow_verified, and never through walk_link ------
gw = StubGW(kinds=[], sources=[])
r = run(gw)
names = [c[0] for c in gw.calls]
check("walks the leg through follow_verified", "follow_verified" in names)
check("and NEVER through walk_link, which publishes no leg-end frame",
      "walk_link" not in names)

kw = dict(gw.calls[0][1])
check("one attempt only -- the retrying primitive is a different quantity",
      kw["attempts"] == 1)
check("shots are handed down, or no frame is ever written",
      kw["shots"] == "/tmp/shots")
check("start_hint is the PROVEN start node, not the spawn",
      kw["start_hint"] == "bar_pool_room")
check("the route is exactly the one leg under test",
      kw["route"] == ["bar_jukebox"])

# --- 2. the provenance split -------------------------------------------------
# Three failures: two classified off the leg's own end, one off the pre-attempt
# view. A census that counts all three as evidence about the leg is the exact
# defect OPEN-1 describes.
gw = StubGW(kinds=["overshot", "wedged", "regressed"],
            sources=[LEG_END, FALLBACK, LEG_END])
r = run(gw)
check("every class is kept in failure_kinds, so no denominator goes missing",
      r["failure_kinds"] == ["overshot", "wedged", "regressed"])
check("failure_kinds_leg_end keeps ONLY the leg-end frames",
      r["failure_kinds_leg_end"] == ["overshot", "regressed"])
check("the fallback frame is excluded, not silently relabelled",
      "wedged" not in r["failure_kinds_leg_end"])
check("provenance is returned alongside, in lockstep",
      len(r["failure_sources"]) == len(r["failure_kinds"]) == 3)

# ANTI-VACUITY. If the split ever returns everything, the two lists are equal
# and the check above would still pass on a corpus where they happen to match.
check("the split is not a no-op on this corpus",
      r["failure_kinds"] != r["failure_kinds_leg_end"])

# --- 3. the recovery fan is reported separately from arrival ----------------
gw = StubGW(kinds=[], sources=[],
            log_lines=["      recovered bar_jukebox at 2 after 1 step(s)"])
r = run(gw)
check("a fan rescue is detected", r["fan_rescued"] is True)
check("and counted as the fan having run", r["fan_ran"] is True)

gw = StubGW(kinds=[], sources=[],
            log_lines=["      recovery fan did not find bar_jukebox"])
r = run(gw)
check("a failed fan counts as run", r["fan_ran"] is True)
check("but NOT as a rescue -- otherwise a bad leg passes by being rescued",
      r["fan_rescued"] is False)

gw = StubGW(kinds=[], sources=[], log_lines=["      -> walked 0.24 units"])
r = run(gw)
check("a clean leg reports no fan at all", r["fan_ran"] is False)

# --- 4. arrival is judged by locate(), independently of follow_verified -----
gw = StubGW(kinds=[], sources=[], located="bar_pool_room")
r = run(gw)
check("locate() disagreeing with follow_verified is visible, not swallowed",
      r["arrived"] is False and r["verified_arrived"] is True)

# --- 5. the row builder cannot drop a measurement ---------------------------
gw = StubGW(kinds=["overshot"], sources=[LEG_END])
r = run(gw)
row = _harness.leg_trial_row("restored", r, 91.4, True)
missing = [k for k in _harness.MEASURED_KEYS if k not in row]
check("leg_trial_row records every measured key", not missing)
check("and carries the arm, outcome and duration",
      row["arm"] == "restored" and row["arrived"] is True
      and row["seconds"] == 91.4)
check("MEASURED_KEYS is not empty -- an empty tuple passes the check above "
      "for free", len(_harness.MEASURED_KEYS) >= 8)

# --- 6. the reporter prints the leg-end census, not just the total ----------
rows = [_harness.leg_trial_row("restored", run(StubGW(
            kinds=["overshot", "wedged"], sources=[LEG_END, FALLBACK])),
        90.0, False)]
out = []
_harness.report_leg_arm("restored", rows, 0, out=out.append)
text = "\n".join(out)
check("the report names the leg-end census", "LEG-END frames only" in text)
check("and says how many were excluded as fallback frames",
      "EXCLUDED" in text and "1 classified off a fallback frame" in text)
check("and reports arrival with the fan subtracted",
      "WITHOUT the fan" in text)
check("an arm with no valid trials says so rather than printing 0/0",
      "NO VALID TRIALS" in (lambda o: (_harness.report_leg_arm(
          "x", [], 4, out=o.append), "\n".join(o))[1])([]))

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
