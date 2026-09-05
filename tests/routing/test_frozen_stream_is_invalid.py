"""A FROZEN STREAM IS AN INVALID TRIAL, NOT A ROUTE FAILURE.

Reproduced end to end 2026-09-05 before this test existed. With a capture
returning identical pixels:

    stream_is_live        -> False   (the picture is dead)
    follow_verified       -> arrived=False, reached=[]
    stick pushes issued   -> 0
    resets burned         -> 4
    failures_by_kind      -> {'overshot': 1}

Zero stick pushes, four resets, filed as a route failure classified OVERSHOT —
"rich frame, off the mapped route" — about a character that never moved. A
frozen frame of a real room IS a rich frame the localiser cannot place, so the
most plausible class is the wrong one, and it lands in `failures_by_kind`, which
is the number every queued A/B is scored on. Recording cannot-see as
did-not-arrive has already invalidated one whole A/B here (the leg-tolerance
run, 2026-09-03, where the console was falling asleep).

WHAT THIS FILE GUARDS, and why each half is needed:

  * the gate FIRES   — a dead picture is recorded as None and classified as
                       something that is not a position claim at all;
  * the gate SLEEPS  — a LIVE stream still produces a real failure with its real
                       signature. Without this half, wiring the gate to "always
                       invalid" would pass every check above it, and the run
                       would report nothing but invalid trials forever.

The four measured classes themselves are pinned by tests/routing/
test_failure_kind.py against the archived frames. This file must not restate
them; it only asserts that liveness gates them.
"""
import os
import os as _os
import sys
import tempfile
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
ROOT = _ROOT
sys.path.insert(0, ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np
from PIL import Image

import failure_kind as fk
import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# The four classes, spelled out as LITERALS. Asserting against fk.REAL_FAILURES
# alone would pass if somebody set UNMEASURABLE = "overshot": the constant under
# test must never be the yardstick it is measured with.
REAL = ("wedged", "overshot", "regressed", "unplaced")

ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]

# stream_is_live sleeps `gap` between its two captures, twice per trial. Nothing
# in this file measures time, so the sleeps are pure cost.
gw.time.sleep = lambda *a: None


# ---------------------------------------------------------------------------
# 1. failure_kind.classify: liveness gates the class, and only the class
# ---------------------------------------------------------------------------
def fake(room, score, margin, n):
    return ((lambda img: (room, score, margin)),
            (lambda img, cache_key=None: (None, [0] * n)))


# Every real signature, each one under a dead stream. Doing this for all four
# rather than just the observed 'overshot' is the point: NONE of them is a claim
# a frozen frame can support.
for label, args in [("wedged", (None, 1, 1.0, 10)),
                    ("overshot", (None, 105, 1.54, 1346)),
                    ("regressed", ("portrait_room", 480, 4.32, 1500)),
                    ("unplaced", ("office_door", 300, 2.0, 900))]:
    i, k = fake(*args)
    live_kind = fk.classify(None, "bar_jukebox", ROUTE, i, k, live=True)[0]
    dead_kind = fk.classify(None, "bar_jukebox", ROUTE, i, k, live=False)[0]
    check(f"a {label} frame on a LIVE stream keeps its real class",
          live_kind == label)
    check(f"the same frame on a DEAD stream is not a position claim",
          dead_kind not in REAL)

# THE POSITIVE CONTROL FOR THE DEFAULT. live is a THREE-state parameter and
# `None` means nobody checked — the historic behaviour, and how the archived
# corpus is classified. If None were folded into False by a stray bool(), every
# existing caller would silently start reporting 'unmeasurable'.
i, k = fake(None, 105, 1.54, 1346)
check("live=None (unchecked) classifies exactly as before",
      fk.classify(None, "bar_jukebox", ROUTE, i, k)[0] == "overshot")
check("live=None is not silently read as dead",
      fk.classify(None, "bar_jukebox", ROUTE, i, k, live=None)[0] == "overshot")

# A callable is accepted, so a caller can hand over the check rather than its
# result.
check("live may be a callable",
      fk.classify(None, "bar_jukebox", ROUTE, i, k, live=lambda: False)[0]
      not in REAL)
check("...and a callable saying live keeps the real class",
      fk.classify(None, "bar_jukebox", ROUTE, i, k, live=lambda: True)[0]
      == "overshot")

check("the unmeasurable class is not one of the real failures",
      fk.UNMEASURABLE not in REAL)
check("REAL_FAILURES lists exactly the four measured classes",
      tuple(fk.REAL_FAILURES) == REAL)


# ---------------------------------------------------------------------------
# 2. END TO END through consecutive_arrivals, with a real frozen capture
# ---------------------------------------------------------------------------
FRAME = _os.path.join(ROOT, "overnight", "failframes_prerecovery",
                      "fail_bar_jukebox_1788513815.jpg")
# 1346 keypoints and unrecognised — i.e. the frame that classified 'overshot'
# in the reproduction. Using the exact frame that produced the wrong answer is
# deliberate; a synthetic blank one would be classified 'wedged' and would not
# exercise the failure this file exists for.
if not _os.path.exists(FRAME):
    # LOUDLY, not as a skip. A fixture that vanishes must not turn a guard into
    # a no-op: tests/routing/test_read_ban_counter lost all its coverage that
    # way and reported a missing fixture for days while passing.
    print(f"FAIL the archived frame this test is built on is gone: {FRAME}")
    sys.exit(1)
FROZEN = Image.open(FRAME).copy()


def _shifted(k):
    """A frame that genuinely differs from its neighbours, for a LIVE stream."""
    a = np.asarray(FROZEN.convert("RGB")).astype(int)
    return Image.fromarray(((a + k * 40) % 255).astype("uint8"))


class Rig:
    """A capture that is live for its first `live_calls` frames, then sticks."""

    def __init__(self, live_calls=0):
        self.n = 0
        self.live_calls = live_calls

    def __call__(self):
        self.n += 1
        return _shifted(self.n) if self.n <= self.live_calls else FROZEN.copy()


class Map:
    def route_reason(self, a, b):
        return "ok"

    def route(self, a, b):
        return [a, b]

    def route_cost(self, p):
        return 1.0

    def steps_for(self, a, b):
        return [{"bearing": 1.0, "dur": 0.5, "speed": 0.3}]


resets = {"n": 0}
fake_reset = types.ModuleType("reset_env")


def _count_reset(log=None):
    resets["n"] += 1


fake_reset.reset_environment = _count_reset
_saved_reset = sys.modules.get("reset_env")
sys.modules["reset_env"] = fake_reset

try:
    # --- 2a. dead from the first frame -------------------------------------
    # The whole real stack runs: consecutive_arrivals -> follow_verified ->
    # go_to_node_verified -> locate -> follow. Nothing is stubbed except the
    # map and the reset.
    resets["n"] = 0
    r = gw.consecutive_arrivals(Map(), ROUTE, 1, capture=Rig(live_calls=0),
                                read_heading=lambda: 90.0,
                                log=lambda *a: None, shots=None)
    check("a frozen trial is recorded as INVALID (None)", r["outcomes"] == [None])
    check("...and NOT as a route failure", False not in r["outcomes"])
    check("...and does not count toward the valid denominator", r["valid"] == 0)
    check("...and is counted as invalid", r["invalid"] == 1)
    check("...and carries no failure signature at all",
          r["failures_by_kind"] == {})
    # Catches DELETION of the before-trial check specifically: without it the
    # walk still ends up invalid (the mid-walk check sees the same dead
    # picture), so only the wasted work distinguishes the two.
    check("a dead picture does not burn a reset before anyone looks",
          resets["n"] == 0)

    # --- 2b. the stream dies MID-trial -------------------------------------
    # live_calls=2 covers exactly the before-trial liveness check, so the trial
    # starts legitimately and the picture sticks once walking begins. This is
    # the path that reaches failure_kind.classify with a real frame in hand.
    resets["n"] = 0
    shots = tempfile.mkdtemp()
    lines = []
    r = gw.consecutive_arrivals(Map(), ROUTE, 1, capture=Rig(live_calls=2),
                                read_heading=lambda: 90.0,
                                log=lines.append, shots=shots)
    check("a stream that dies mid-trial is INVALID too", r["outcomes"] == [None])
    check("...and still is not a route failure", False not in r["outcomes"])
    check("...and reports zero valid trials", r["valid"] == 0 and r["invalid"] == 1)
    # THE EXACT WRONG ANSWER THE BUG PRODUCED.
    check("...and NOTHING is filed as 'overshot'",
          "overshot" not in r["failures_by_kind"])
    check("...nor as any other real failure class",
          not any(k in REAL for k in r["failures_by_kind"]))
    check("the run says WHY the trial was invalid",
          any("frozen" in w or "not updating" in w
              for w in r["invalid_reasons"]))
    # It walked, so it must have kept the picture — an invalid trial is still
    # worth a frame, it is just not worth a verdict.
    import glob
    check("the frame is still saved for a human to look at",
          len(glob.glob(shots + "/fail_*.jpg")) == 1)
    # AND THE LOG BESIDE IT MUST NOT LIE. The tally is only half of what a
    # human reads; the per-failure line is the other half, and it is the half
    # that named 'overshot' in the reproduction. This is what fails if
    # follow_verified stops telling classify() whether the picture was live —
    # the trial would still come out invalid, so nothing else here would move.
    kind_lines = [ln for ln in lines if "failure kind:" in ln]
    check("the run logs a failure kind for the frame it kept",
          len(kind_lines) == 1)
    check("...and that logged kind is not a real position claim either",
          not any(f"failure kind: {k}" in ln for ln in kind_lines for k in REAL))

    # --- 2c. THE POSITIVE CONTROL: a LIVE stream still fails properly ------
    # Without this, `return UNMEASURABLE` unconditionally would pass 2a and 2b.
    # go_to_node_verified is stubbed only to keep this cheap; everything that
    # decides valid-vs-invalid and the failure class is real.
    real_gtnv = gw.go_to_node_verified
    try:
        gw.go_to_node_verified = (
            lambda m, node, capture=None, read_heading=None, log=None,
            attempts=3, shots=None: False)
        r = gw.consecutive_arrivals(Map(), ROUTE, 1,
                                    capture=Rig(live_calls=10 ** 6),
                                    read_heading=lambda: 90.0,
                                    log=lambda *a: None,
                                    shots=tempfile.mkdtemp())
        check("a LIVE stream still records a real FAILURE", r["outcomes"] == [False])
        check("...counted as a valid trial", r["valid"] == 1 and r["invalid"] == 0)
        check("...and it still gets a real signature",
              any(k in REAL for k in r["failures_by_kind"]))

        gw.go_to_node_verified = (
            lambda m, node, capture=None, read_heading=None, log=None,
            attempts=3, shots=None: True)
        r = gw.consecutive_arrivals(Map(), ROUTE, 1,
                                    capture=Rig(live_calls=10 ** 6),
                                    read_heading=lambda: 90.0,
                                    log=lambda *a: None)
        check("a LIVE stream still records an ARRIVAL",
              r["outcomes"] == [True] and r["arrived"] == 1)
        check("...counted as a valid trial", r["valid"] == 1 and r["invalid"] == 0)

        # --- 2d. the stream dies AFTER the walk --------------------------
        # Nothing failed, so follow_verified never spends a liveness check —
        # this is the case only the AFTER-trial check can catch, and it is the
        # documented reason for checking twice (overnight/_harness.py item 3:
        # a console that falls asleep mid-run makes both arms of an A/B degrade
        # together and looks exactly like a failed change).
        #
        # live_calls=2 covers exactly the before-trial check; with shots=None
        # nothing else captures until the after-trial check, which then sees
        # two identical frames.
        #
        # This deliberately DISCARDS an apparent arrival. That is the trade
        # ab_attempts.py already makes: a lost trial costs n, a mislabelled one
        # costs the conclusion.
        r = gw.consecutive_arrivals(Map(), ROUTE, 1, capture=Rig(live_calls=2),
                                    read_heading=lambda: 90.0,
                                    log=lambda *a: None)
        check("a stream that dies after the walk invalidates the trial",
              r["outcomes"] == [None] and r["invalid"] == 1)
        check("...so an unverifiable 'arrival' is not counted as one",
              r["arrived"] == 0 and r["valid"] == 0)
        check("...and it says the stream died during the trial",
              any("during the trial" in w for w in r["invalid_reasons"]))
    finally:
        gw.go_to_node_verified = real_gtnv
finally:
    if _saved_reset is not None:
        sys.modules["reset_env"] = _saved_reset
    else:
        sys.modules.pop("reset_env", None)


# ---------------------------------------------------------------------------
# 3. What an invalid trial must NOT do to the numbers around it
# ---------------------------------------------------------------------------
real_follow = gw.follow_verified
try:
    def scripted(seq):
        """(arrived, measurable, kinds) per trial."""
        s = list(seq)

        def f(m, route, capture=None, read_heading=None, log=None, attempts=3,
              shots=None):
            arrived, measurable, kinds = s.pop(0)
            gw._LAST_FAILURE_KINDS[:] = list(kinds)
            gw._LAST_TRIAL_MEASURABLE = measurable
            return arrived, (route if arrived else [])
        return f

    # An unmeasurable trial in the middle of a streak did not break the route,
    # so it must not break the streak either.
    gw.follow_verified = scripted([
        (True, True, []), (False, False, ["overshot"]), (True, True, [])])
    r = gw.consecutive_arrivals(None, ROUTE, 3, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("an invalid trial does not break the streak", r["best_streak"] == 2)
    check("...and is not counted as arrived or as valid",
          r["arrived"] == 2 and r["valid"] == 2 and r["invalid"] == 1)
    # THE CONFIDENT WRONG LABEL. The reproduction's whole harm was this one
    # entry reaching the tally.
    check("an invalid trial's signature is DISCARDED, not tallied",
          r["failures_by_kind"] == {})

    # The control: the same signature from a MEASURABLE trial must survive.
    gw.follow_verified = scripted([(False, True, ["overshot"])])
    r = gw.consecutive_arrivals(None, ROUTE, 1, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("a real failure's signature is still tallied",
          r["failures_by_kind"] == {"overshot": 1})
    check("...and the trial is valid", r["valid"] == 1 and r["invalid"] == 0)

    # A VERDICT MUST NOT LEAK INTO THE NEXT TRIAL. The measurable flag is a
    # module global, so one trial proving the picture dead must not condemn the
    # one after it. The real follow_verified clears it on entry; this asserts
    # the harness does not depend on that, because every offline test — and
    # every A/B arm that stubs the walk — substitutes something that does not.
    seen = {"n": 0}

    def leaky(m, route, capture=None, read_heading=None, log=None, attempts=3,
              shots=None):
        seen["n"] += 1
        if seen["n"] == 1:
            gw._LAST_TRIAL_MEASURABLE = False       # trial 1: picture dead
            return False, []
        return True, route                          # trial 2: sets nothing

    gw.follow_verified = leaky
    r = gw.consecutive_arrivals(None, ROUTE, 2, capture=lambda: None,
                                log=lambda *a: None, reset_between=False)
    check("a dead-picture verdict does not condemn the NEXT trial",
          r["outcomes"] == [None, True])
    check("...so the good trial still counts",
          r["arrived"] == 1 and r["valid"] == 1 and r["invalid"] == 1)

    # ANY REPORTED RATE MUST STATE ITS INVALID COUNT. A rate over an unstated
    # denominator is how "both arms degraded together" got read as a result
    # rather than as a dying console.
    lines = []
    gw.follow_verified = scripted([
        (True, True, []), (False, False, ["wedged"]), (True, True, [])])
    r = gw.consecutive_arrivals(None, ROUTE, 3, capture=lambda: None,
                                log=lines.append, reset_between=False)
    summary = [ln for ln in lines if "arrived" in ln and "invalid" in ln]
    check("the summary states the rate AND the invalid count", len(summary) == 1)
    check("...with the honest denominator", summary and "2/2" in summary[0])
    check("...and the number excluded", summary and "1 of 3 invalid" in summary[0])
    check("the returned dict exposes the invalid count too", r["invalid"] == 1)
finally:
    gw.follow_verified = real_follow

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
