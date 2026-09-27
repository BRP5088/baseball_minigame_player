"""BASEBALL_DEAL_FLOOR: the deal gate's post-play floor, selectable for measurement.

WHY. agent_progress/animating-reads/progress.md (09-27): the user labelled 60 hand
reads the reader missed; 29 were read MID-ANIMATION, and 27 of those were released by
wait_for_hand_deal's "stable twice" rule at ~3.4s -- exactly POST_PLAY_MIN_WAIT (3.0)
plus the two polls the rule needs, not anywhere near the 8s READABLE_HAND_BOUND. 16/19
of those with a known prediction had >=1 base to travel, and the per-bases completeness
table elsewhere in that doc says a flat floor is far too short whenever a runner moves.
The stillness check cannot rescue this: two polls 0.15s apart can match by coincidence
during the animation's slow tail while a card still sits stacked behind its neighbour.

THIS FILE pins `deal_floor()` (the function BASEBALL_DEAL_FLOOR is read through) and the
gate-level effects of each mode -- default UNCHANGED, "scaled" and a numeric override
both actually delay release, the 20s cap still wins over an oversized floor, and the new
per-poll trace is written and capped. It does NOT re-pin the default gate's own release
timing -- test_readable_hand_gate.py and test_post_play_timing.py already do that, and
this change's whole point is that neither of them needed to change.
"""
import os
import sys
import time as _t

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ============================================================================
# 1. deal_floor() UNIT TESTS -- fast, no gate involved.
# ============================================================================

# ---- unset / "flat": POST_PLAY_MIN_WAIT exactly, whatever it currently is, bases
# ignored entirely -- this IS the "default unchanged" guarantee, and it also kills a
# "default changed to scaled" mutant: if unset silently meant scaled, bases=4 would
# come back DEAL_FLOOR_BY_BASES_DEFAULT (9.0), not POST_PLAY_MIN_WAIT (3.0) -- the two
# are different literals, so the mutant is distinguishable here without touching the
# real gate at all.
for _bases in (None, 0, 1, 2, 3, 4, 9):
    f, m = orchestrator.deal_floor(_bases, env={})
    check(f"flat (env unset), bases={_bases}: floor is POST_PLAY_MIN_WAIT",
          f == orchestrator.POST_PLAY_MIN_WAIT, f"got {f}")
    check(f"flat (env unset), bases={_bases}: mode is 'flat'", m == "flat", m)

f, m = orchestrator.deal_floor(4, env={"BASEBALL_DEAL_FLOOR": "flat"})
check("explicit 'flat' behaves the same as unset", (f, m) == (orchestrator.POST_PLAY_MIN_WAIT, "flat"))
f, m = orchestrator.deal_floor(4, env={"BASEBALL_DEAL_FLOOR": "  FLAT  "})
check("mode matching is case/whitespace-insensitive ('  FLAT  ')",
      (f, m) == (orchestrator.POST_PLAY_MIN_WAIT, "flat"))

# ---- "scaled": DEAL_FLOOR_BY_BASES, pinned as LITERALS (10.11) -- a bound written in
# terms of the table it guards passes forever even if the table is gutted.
_SCALED = {"BASEBALL_DEAL_FLOOR": "scaled"}
_expect = {0: 3.0, 1: 5.0, 2: 6.5, 3: 8.0, 4: 9.0, 9: 9.0}   # 4 and 9 both hit the 4+ bucket
for _bases, _want in _expect.items():
    f, m = orchestrator.deal_floor(_bases, env=_SCALED)
    check(f"scaled, bases={_bases}: floor is {_want}", f == _want, f"got {f}")
    check(f"scaled, bases={_bases}: mode is 'scaled'", m == "scaled", m)
f, m = orchestrator.deal_floor(None, env=_SCALED)
check("scaled, bases unknown (None): floor is 5.0", f == 5.0, f"got {f}")

# ---- a number: a fixed floor, bases ignored, mode reported as 'numeric'.
for _bases in (None, 0, 3, 9):
    f, m = orchestrator.deal_floor(_bases, env={"BASEBALL_DEAL_FLOOR": "12"})
    check(f"numeric '12', bases={_bases}: floor is 12.0", f == 12.0, f"got {f}")
    check(f"numeric '12', bases={_bases}: mode is 'numeric'", m == "numeric", m)
f, m = orchestrator.deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "0"})
check("numeric '0' is honoured (not treated as falsy/unset)", (f, m) == (0.0, "numeric"))

_raised = False
try:
    orchestrator.deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "nonsense"})
except ValueError:
    _raised = True
check("an unparseable BASEBALL_DEAL_FLOOR raises ValueError", _raised)

# ---- the floor never exceeds POST_PLAY_DEAL_MAX_WAIT (the 20s cap) -- kills a
# "cap removed" mutant directly at the function level.
f, m = orchestrator.deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "999"})
check("an oversized numeric floor is capped at POST_PLAY_DEAL_MAX_WAIT",
      f == orchestrator.POST_PLAY_DEAL_MAX_WAIT, f"got {f}")
check(orchestrator.DEAL_FLOOR_BY_BASES_DEFAULT <= orchestrator.POST_PLAY_DEAL_MAX_WAIT,
      "DEAL_FLOOR_BY_BASES_DEFAULT itself already sits under the cap")


# ============================================================================
# 2. READ AT CALL TIME, NOT AT IMPORT -- same property test_no_import_time_test_run_flag.py
#    checks for BASEBALL_TEST_RUN, applied to DEAL_FLOOR_ENV: every reference to the name
#    outside its own assignment and the function that reads it is INDENTED (inside a def),
#    never a bare top-level statement that would freeze a value at import.
# ============================================================================
_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
_bad_lines = []
for _n, _ln in enumerate(_src.splitlines(), 1):
    if "DEAL_FLOOR_ENV" not in _ln:
        continue
    _stripped = _ln.strip()
    if _stripped.startswith("DEAL_FLOOR_ENV ="):
        continue   # the constant's own definition
    _indent = len(_ln) - len(_ln.lstrip())
    if _indent == 0:
        _bad_lines.append(_n)
check("every use of DEAL_FLOOR_ENV besides its own assignment is inside a function "
      "(read at call time, never at import)", not _bad_lines, str(_bad_lines))

# Dynamic half of the same property: two calls with DIFFERENT env dicts in the same
# process must give different answers -- if the mode were cached at import/def time,
# both calls would return whatever was true the first time.
check("deal_floor() re-reads the env on every call, not a cached value",
      orchestrator.deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "7"})[0] == 7.0
      and orchestrator.deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "9"})[0] == 9.0)


# ============================================================================
# 3. GATE-LEVEL INTEGRATION -- a fake, instantly-advancing clock (same technique as
#    test_post_play_timing.py's run()) so a 12s or 20s floor costs no real wall time.
# ============================================================================
COMPLETE_SIG = tuple(("player", 5, None, None) for _ in range(5))


def drive(readable_from, max_wait, poll_interval=0.01, predicted_bases=None,
          floor_env=None):
    """Run the REAL gate with the capture/reader stack stubbed and time faked to
    advance only on time.sleep(). readable_from is the poll (grab) index at which the
    stubbed reader starts returning a complete, stable hand; before it, an empty `()`
    signature stands in for "still animating" (same convention as
    test_readable_hand_gate.py -- `()` is what local_hand._read_ungated actually
    returns for an unrecognised/empty table).

    Returns (released, elapsed_fake_seconds, row) where row is the single
    deal_timing.jsonl row this call produced (via the in-memory _OBSERVATIONS sink).
    """
    calls = {"n": 0}
    clock = [1000.0]

    def fake_grab_settle(names):
        calls["n"] += 1
        return {n: object() for n in names}

    def fake_sig(img):
        return COMPLETE_SIG if calls["n"] >= readable_from else ()

    saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
             orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
             orchestrator._fast_grab, orchestrator.time)
    saved_env = os.environ.get("BASEBALL_DEAL_FLOOR")
    try:
        if floor_env is None:
            os.environ.pop("BASEBALL_DEAL_FLOOR", None)
        else:
            os.environ["BASEBALL_DEAL_FLOOR"] = floor_env
        orchestrator._grab_settle_regions = fake_grab_settle
        orchestrator._mean_abs_delta = lambda a, b: 999.0   # the edge is always "seen"
        orchestrator._hand_signature = fake_sig
        orchestrator._fast_grab = lambda: object()
        orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
        orchestrator.time = type("C", (), {
            "sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s)),
            "time": staticmethod(lambda: clock[0]),
            "strftime": staticmethod(_t.strftime),
        })()
        orchestrator._OBSERVATIONS.clear()
        out = orchestrator.wait_for_hand_deal(max_wait=max_wait, poll_interval=poll_interval,
                                              baseline=object(), predicted_bases=predicted_bases)
        rows = [o for o in orchestrator._OBSERVATIONS if o.get("event") == "deal_timing"]
        return out, clock[0] - 1000.0, (rows[0] if rows else None)
    finally:
        (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.time) = saved
        if saved_env is None:
            os.environ.pop("BASEBALL_DEAL_FLOOR", None)
        else:
            os.environ["BASEBALL_DEAL_FLOOR"] = saved_env
        orchestrator._OBSERVATIONS.clear()


# ---- 3a. a numeric floor holds the gate even though the hand reads stable almost at
# once -- this is the exact shape the evidence found (stable at ~3.4s) and pins that a
# BASEBALL_DEAL_FLOOR=12 run would NOT have released early. Kills a "numeric floor
# ignored" mutant.
released, elapsed, row = drive(readable_from=1, max_wait=20.0, floor_env="12")
check("BASEBALL_DEAL_FLOOR=12: the gate still releases (a complete hand IS reached)",
      released is True, f"elapsed={elapsed}")
check("...but not before the 12s floor even though stable almost immediately",
      elapsed >= 12.0, f"released at {elapsed:.2f}s")
check("...and promptly once past the floor", elapsed < 12.0 + 0.05,
      f"released at {elapsed:.2f}s")
if row:
    check("the row records floor=12.0", row.get("floor") == 12.0, str(row))
    check("the row records floor_mode='numeric'", row.get("floor_mode") == "numeric", str(row))

# ---- 3b. "scaled" actually changes the release point per predicted_bases, and stays
# well under the 20s cap. Kills a "scaled ignores bases" mutant (bases=3's floor, 8.0,
# is neither bases=0's 3.0 nor a value blind to the argument).
released, elapsed, row = drive(readable_from=1, max_wait=20.0, floor_env="scaled",
                               predicted_bases=3)
check("scaled, bases=3: releases at the 8.0s floor, not earlier",
      released is True and elapsed >= 8.0, f"elapsed={elapsed}")
check("scaled, bases=3: releases promptly once past that floor", elapsed < 8.05,
      f"elapsed={elapsed}")
if row:
    check("the row records floor=8.0 for bases=3", row.get("floor") == 8.0, str(row))
    check("the row records predicted_bases=3", row.get("predicted_bases") == 3, str(row))

released0, elapsed0, _ = drive(readable_from=1, max_wait=20.0, floor_env="scaled",
                               predicted_bases=0)
check("scaled, bases=0: releases at 3.0s -- the SAME floor as flat's default",
      released0 is True and 3.0 <= elapsed0 < 3.05, f"elapsed={elapsed0}")

# ---- 3c. the 20s cap still wins over an oversized numeric floor -- this is the
# integration-level version of the "cap removed" mutant: without the clamp inside
# deal_floor(), a BASEBALL_DEAL_FLOOR=999 request would never release inside a 25s
# max_wait budget (999 > 25), so this would come back TIMED OUT instead of released
# at ~20s.
released, elapsed, row = drive(readable_from=1, max_wait=25.0, floor_env="999")
check("BASEBALL_DEAL_FLOOR=999 still releases (the cap, not the raw value, applies)",
      released is True, f"elapsed={elapsed}")
check("...and releases at the 20s cap, not anywhere near 999",
      20.0 <= elapsed < 20.05, f"released at {elapsed:.2f}s")
if row:
    check("the row's floor is capped at POST_PLAY_DEAL_MAX_WAIT, not 999",
          row.get("floor") == orchestrator.POST_PLAY_DEAL_MAX_WAIT, str(row))

# ---- 3d. default (unset) is unaffected by all of the above -- release still happens
# at the ordinary POST_PLAY_MIN_WAIT-governed point once the hand reads stable.
released, elapsed, row = drive(readable_from=1, max_wait=20.0, floor_env=None)
check("default (env unset): releases at POST_PLAY_MIN_WAIT, unchanged",
      released is True and orchestrator.POST_PLAY_MIN_WAIT <= elapsed < orchestrator.POST_PLAY_MIN_WAIT + 0.05,
      f"elapsed={elapsed}, POST_PLAY_MIN_WAIT={orchestrator.POST_PLAY_MIN_WAIT}")
if row:
    check("the row's floor_mode is 'flat' by default", row.get("floor_mode") == "flat", str(row))


# ============================================================================
# 4. THE PER-POLL TRACE -- written, shaped right, and capped.
# ============================================================================

# ---- the shape, on a short, simple run: one poll before completeness (rows_read=0,
# slots_read=0 -- `readable_from=2` means the FIRST _grab_settle_regions call, which
# happens before the reader runs, already brings calls["n"] to 1, so poll 1 is still
# the `()` "animating" shape and poll 2 onward is complete), then a complete/stable pair.
released, elapsed, row = drive(readable_from=2, max_wait=5.0, floor_env=None)
check("a released deal's row carries a polls list", isinstance((row or {}).get("polls"), list),
      str(row))
if row:
    _polls = row["polls"]
    check("polls is non-empty", len(_polls) > 0, str(_polls[:5]))
    check("each poll entry has 4 fields [t, rows_read, slots_read, signature_stable]",
          all(isinstance(p, list) and len(p) == 4 for p in _polls), str(_polls[:3]))
    _first = _polls[0]
    check("the first poll (still `()`, unread) reads rows_read=0, slots_read=0",
          _first[1] == 0 and _first[2] == 0, str(_first))
    _last = _polls[-1]
    check("the last poll (complete, stable hand) reads rows_read=5, slots_read=5, stable",
          _last[1] == 5 and _last[2] == 5 and _last[3] is True, str(_last))
    check("timestamps are non-decreasing", all(a[0] <= b[0] for a, b in zip(_polls, _polls[1:])),
          str([p[0] for p in _polls]))

# ---- the cap: a hand that NEVER completes runs the gate out to READABLE_HAND_BOUND at
# a fine poll_interval, producing far more than DEAL_POLL_TRACE_CAP raw polls -- the
# logged list must stop growing at the cap. Kills a "polls not capped" mutant.
released, elapsed, row = drive(readable_from=10 ** 9, max_wait=20.0, poll_interval=0.01,
                               floor_env=None)
check("a hand that never completes still records a row", row is not None)
if row:
    check(f"the polls list is capped at DEAL_POLL_TRACE_CAP ({orchestrator.DEAL_POLL_TRACE_CAP})",
          len(row["polls"]) == orchestrator.DEAL_POLL_TRACE_CAP,
          f"got {len(row['polls'])} entries over {elapsed:.1f}s")



# ============================================================================
# 5. ROUND 2 (deal-floor fixer r2) -- each check below FAILS on 1cfa1ab, the commit
# the Opus skeptic refuted (see agent_progress/skeptic-deal-floor/progress.md). Section
# 1-4 above are UNTOUCHED and still pin round 1's contract, including deal_floor()'s
# own raw behaviour (raises on garbage, honours an explicit numeric 0) -- these fixes
# live in a wrapper the gate calls, `_safe_deal_floor`, and in wait_for_hand_deal
# itself, not in deal_floor().
# ============================================================================

# ---- finding 1: _safe_deal_floor is what the live gate actually calls. Anything that
# is not 'flat', 'scaled', or a finite number >= POST_PLAY_MIN_WAIT must fall back to
# flat POST_PLAY_MIN_WAIT -- never raise, never go below today's 3.0, never hand back a
# floor (nan) that can never satisfy a >= comparison.
for _raw in ("abc", "-5", "0", "1.5", "-inf", "nan"):
    f, m = orchestrator._safe_deal_floor(None, env={"BASEBALL_DEAL_FLOOR": _raw})
    check(f"_safe_deal_floor({_raw!r}) falls back to flat POST_PLAY_MIN_WAIT",
          (f, m) == (orchestrator.POST_PLAY_MIN_WAIT, "flat"), f"got {(f, m)}")

# valid values must pass through completely unharmed.
f, m = orchestrator._safe_deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "12"})
check("_safe_deal_floor('12') is unaffected (a valid numeric floor)", (f, m) == (12.0, "numeric"))
f, m = orchestrator._safe_deal_floor(3, env={"BASEBALL_DEAL_FLOOR": "scaled"})
check("_safe_deal_floor(scaled, bases=3) is unaffected", (f, m) == (8.0, "scaled"))
f, m = orchestrator._safe_deal_floor(None, env={"BASEBALL_DEAL_FLOOR": "inf"})
check("_safe_deal_floor('inf') still clamps to the 20s cap rather than falling back",
      (f, m) == (orchestrator.POST_PLAY_DEAL_MAX_WAIT, "numeric"), f"got {(f, m)}")

# the gate itself: garbage must not raise out of wait_for_hand_deal (this crashed the
# turn loop on 1cfa1ab -- a bare `orchestrator.deal_floor()` call at the site the gate
# used to call directly).
released, elapsed, row = drive(readable_from=1, max_wait=20.0, floor_env="abc")
check("BASEBALL_DEAL_FLOOR=abc does not raise out of wait_for_hand_deal",
      released is True, f"released={released}")
check("...and falls back to flat POST_PLAY_MIN_WAIT rather than 0",
      elapsed >= orchestrator.POST_PLAY_MIN_WAIT, f"elapsed={elapsed}")
if row:
    check("the row records floor_mode='flat' for a garbage value", row.get("floor_mode") == "flat",
          str(row))

# nan must not spin out the full 20s timeout either.
released, elapsed, row = drive(readable_from=1, max_wait=20.0, floor_env="nan")
check("BASEBALL_DEAL_FLOOR=nan releases promptly (falls back to flat), not a 20s timeout",
      released is True and elapsed < 10.0, f"released={released} elapsed={elapsed}")


# ---- a second driver, extending `drive()` above for round-2 findings: discard_redeal
# and no_motion_needed passthrough. A separate function so section 1-4's `drive()` and
# every check built on it is untouched.
def drive2(readable_from, max_wait, poll_interval=0.01, predicted_bases=None,
           floor_env=None, discard_redeal=False, no_motion_needed=False, margin=None):
    calls = {"n": 0}
    clock = [1000.0]

    def fake_grab_settle(names):
        calls["n"] += 1
        return {n: object() for n in names}

    def fake_sig(img):
        return COMPLETE_SIG if calls["n"] >= readable_from else ()

    saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
             orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
             orchestrator._fast_grab, orchestrator.time)
    saved_env = os.environ.get("BASEBALL_DEAL_FLOOR")
    try:
        if floor_env is None:
            os.environ.pop("BASEBALL_DEAL_FLOOR", None)
        else:
            os.environ["BASEBALL_DEAL_FLOOR"] = floor_env
        orchestrator._grab_settle_regions = fake_grab_settle
        orchestrator._mean_abs_delta = lambda a, b: 999.0
        orchestrator._hand_signature = fake_sig
        orchestrator._fast_grab = lambda: object()
        orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
        orchestrator.time = type("C", (), {
            "sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s)),
            "time": staticmethod(lambda: clock[0]),
            "strftime": staticmethod(_t.strftime),
        })()
        orchestrator._OBSERVATIONS.clear()
        out = orchestrator.wait_for_hand_deal(
            max_wait=max_wait, poll_interval=poll_interval, baseline=object(),
            predicted_bases=predicted_bases, margin=margin,
            discard_redeal=discard_redeal, no_motion_needed=no_motion_needed)
        rows = [o for o in orchestrator._OBSERVATIONS if o.get("event") == "deal_timing"]
        return out, clock[0] - 1000.0, (rows[0] if rows else None)
    finally:
        (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.time) = saved
        if saved_env is None:
            os.environ.pop("BASEBALL_DEAL_FLOOR", None)
        else:
            os.environ["BASEBALL_DEAL_FLOOR"] = saved_env
        orchestrator._OBSERVATIONS.clear()


# ---- finding 2: the discard redeal (discard_redeal=True) must stay flat
# POST_PLAY_MIN_WAIT in EVERY BASEBALL_DEAL_FLOOR mode -- no runner moves on a discard,
# so scaled/numeric must never apply to it.
for _env in ("scaled", "12", None):
    released, elapsed, row = drive2(readable_from=1, max_wait=20.0, floor_env=_env,
                                    discard_redeal=True)
    check(f"discard_redeal stays flat under BASEBALL_DEAL_FLOOR={_env!r}",
          released is True and orchestrator.POST_PLAY_MIN_WAIT <= elapsed
          < orchestrator.POST_PLAY_MIN_WAIT + 0.05, f"elapsed={elapsed}")
    if row:
        check(f"...and the row records floor_mode='flat' under {_env!r}",
              row.get("floor_mode") == "flat", str(row))
        check(f"...and floor={orchestrator.POST_PLAY_MIN_WAIT} under {_env!r}",
              row.get("floor") == orchestrator.POST_PLAY_MIN_WAIT, str(row))

# ---- finding 3: a no_motion_needed row must log floor=0 / floor_mode='none' -- no
# floor ever gates this caller, so the row must not claim one (was 5.0/12.0 -- whatever
# deal_floor() happened to compute -- even though the release check never used it).
released, elapsed, row = drive2(readable_from=1, max_wait=20.0, floor_env="scaled",
                                no_motion_needed=True, predicted_bases=4)
check("no_motion_needed row logs floor=0.0, not the scaled value that never applied",
      row is not None and row.get("floor") == 0.0, str(row))
check("no_motion_needed row logs floor_mode='none'",
      row is not None and row.get("floor_mode") == "none", str(row))
released, elapsed, row = drive2(readable_from=1, max_wait=20.0, floor_env="12",
                                no_motion_needed=True)
check("no_motion_needed row logs floor=0.0 under a numeric BASEBALL_DEAL_FLOOR too",
      row is not None and row.get("floor") == 0.0, str(row))


# ---- a time-based driver (adapted from the skeptic's own probe.py,
# agent_progress/skeptic-deal-floor/probe.py) for findings 4, 5 and 6: those need the
# stubbed hand signature to depend on ELAPSED TIME (so it can change again AFTER first
# reading complete/stable), not on a poll count.
def drive_t(sigfn, floor_env, max_wait=20.0, poll=0.15, **kw):
    calls = {"n": 0}
    clock = [1000.0]

    def grab(names):
        calls["n"] += 1
        return {n: object() for n in names}

    def sig(img):
        return sigfn(clock[0] - 1000.0)

    saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
             orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
             orchestrator._fast_grab, orchestrator.time)
    saved_env = os.environ.get("BASEBALL_DEAL_FLOOR")
    try:
        if floor_env is None:
            os.environ.pop("BASEBALL_DEAL_FLOOR", None)
        else:
            os.environ["BASEBALL_DEAL_FLOOR"] = floor_env
        orchestrator._grab_settle_regions = grab
        orchestrator._mean_abs_delta = lambda a, b: 999.0
        orchestrator._hand_signature = sig
        orchestrator._fast_grab = lambda: object()
        orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
        orchestrator.time = type("C", (), {
            "sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s)),
            "time": staticmethod(lambda: clock[0]),
            "strftime": staticmethod(_t.strftime),
        })()
        orchestrator._OBSERVATIONS.clear()
        out = orchestrator.wait_for_hand_deal(max_wait=max_wait, poll_interval=poll, **kw)
        rows = [r for r in orchestrator._OBSERVATIONS if r.get("event") == "deal_timing"]
        return out, round(clock[0] - 1000.0, 2), (rows[0] if rows else None)
    finally:
        (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.time) = saved
        if saved_env is None:
            os.environ.pop("BASEBALL_DEAL_FLOOR", None)
        else:
            os.environ["BASEBALL_DEAL_FLOOR"] = saved_env
        orchestrator._OBSERVATIONS.clear()


A5 = tuple(("player", 5, None, None) for _ in range(5))
B5 = tuple(("player", 7, None, None) for _ in range(5))
PART4 = tuple(("player", 5, None, None) for _ in range(4))

# ---- finding 4: the per-poll trace must not go stale once probe_at/first_complete_at
# have both latched (which happens almost immediately here, since A5 is complete and
# stable from t=0). Hand A5 (complete) until t=3.0, PART4 (incomplete) 3.0-5.0, then B5
# (complete, DIFFERENT from A5) from t=5.0; floor 12 so the gate keeps polling long
# after both changes. On 1cfa1ab every poll from ~0.3s onward logs the SAME frozen
# [t, 5, 5, True] row forever; fixed, later polls must show PART4's incompleteness and
# then B5's fresh, not-yet-stable signature.
released, elapsed, row = drive_t(lambda t: A5 if t < 3.0 else (PART4 if t < 5.0 else B5),
                                 "12", baseline=object())
check("finding 4 setup: the gate releases", released is True, f"elapsed={elapsed}")
if row:
    polls = row["polls"]
    _mid = [p for p in polls if 3.05 <= p[0] <= 4.9]
    check("polls during the PART4 window (3.0-5.0s) show the incomplete hand "
          "(slots_read < 5), not a frozen complete reading from before t=3.0",
          bool(_mid) and all(p[2] < 5 for p in _mid), str(_mid[:5]))
    _late = [p for p in polls if 5.0 <= p[0] < 5.2]
    check("the first poll after B5 lands (5.0-5.2s) shows a complete-but-not-yet-stable "
          "read (rows/slots=5, stable=False), not the frozen [5, 5, True] from t<3.0",
          bool(_late) and _late[0][2] == 5 and _late[0][3] is False, str(_late))

# ---- finding 5: a floor >= READABLE_HAND_BOUND must not release on a single read
# without the stable-twice check. scaled bases=3 -> floor 8.0, exactly
# READABLE_HAND_BOUND; the hand changes just as the floor opens (7.95 -> the floor
# first admits a poll at >=8.0). On 1cfa1ab this releases on that single, just-changed
# read at ~8.1s with reason "stable_bound"; fixed, it must wait for two matching reads.
released, elapsed, row = drive_t(lambda t: A5 if t < 7.95 else B5, "scaled",
                                 baseline=object(), predicted_bases=3)
check("finding 5: floor==8.0 (scaled, bases=3) does not release on the single "
      "just-changed read", released is True and elapsed >= 8.25, f"elapsed={elapsed}")
if row:
    check("...and the release reason is genuine stable-twice, not stable_bound",
          row.get("reason") == "stable", str(row))

# a numeric floor above READABLE_HAND_BOUND (12) with the hand changing right at the
# floor -- the skeptic's own probe case.
released, elapsed, row = drive_t(lambda t: A5 if t < 12.05 else B5, "12", baseline=object())
check("finding 5: numeric floor 12, hand changes at 12.05s -- waits for stable-twice, "
      "not a single-read bound release", released is True and elapsed >= 12.3,
      f"elapsed={elapsed}")
if row:
    check("...reason is 'stable', not 'stable_bound'", row.get("reason") == "stable", str(row))

# a hand that never completes under a floor >= READABLE_HAND_BOUND must still be
# bounded -- by the 20s cap (max_wait), the last resort -- not released early on a
# single incomplete read either.
released, elapsed, row = drive_t(lambda t: (), "12", baseline=object())
check("finding 5: a hand that never completes under floor=12 times out at the 20s cap, "
      "not an early single-read release", released is False and elapsed >= 20.0,
      f"released={released} elapsed={elapsed}")

# ---- finding 6 (kills mutant M1: floor computed before predicted_bases exists). Every
# check above this point passes predicted_bases directly, which is why M1 survived --
# this drives the MARGIN path instead (pop_deal_inputs + bases_to_travel), exactly like
# the one real caller that ever supplies predicted_bases this way (:11296).
_real_pop, _real_btt = orchestrator.pop_deal_inputs, orchestrator.bases_to_travel
orchestrator.pop_deal_inputs = lambda: {"bases": [1, 0, 0], "batter_speed": 1,
                                        "fielding": 0, "seq": 1}
orchestrator.bases_to_travel = lambda *a, **kw: 3
try:
    released, elapsed, row = drive_t(lambda t: A5, "scaled", baseline=object(), margin=4)
finally:
    orchestrator.pop_deal_inputs, orchestrator.bases_to_travel = _real_pop, _real_btt
check("finding 6 (M1): predicted_bases reaches the row via the margin path",
      row is not None and row.get("predicted_bases") == 3, str(row))
check("finding 6 (M1): the floor reflects THAT predicted_bases (scaled, bases=3 -> "
      "8.0) -- 5.0 (DEAL_FLOOR_UNKNOWN) is what a floor computed before predicted_bases "
      "exists would produce here",
      row is not None and row.get("floor") == 8.0, str(row))
check("...and the gate actually waited that long, not 5.0s", elapsed >= 8.0,
      f"elapsed={elapsed}")


print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
