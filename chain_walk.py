"""Walk a recorded CHAIN of reference frames by LOOKING AFTER EVERY PUSH.

Dead reckoning replays a recorded (bearing, duration) and looks only at the
leg's end; it arrives 5/10 per route after 13 measured changes (GRAVEYARD.md).
This is the closed loop the user asked for instead: stop, look, decide, push.
Position comes from the screen, never from the stick.

WHY THIS IS NOT ONE OF THE TWO CLOSED FAMILIES IN GRAVEYARD.md
--------------------------------------------------------------
* "Steering while walking" died because a 30 deg heading lag became METRES of
  position error. Nothing here steers mid-push: the camera is turned, the stick
  is held for PUSH_SEC, and only then is a frame taken.
* "Chunking a leg into more turn-then-walk cycles" died because each chunk
  re-accelerates from a standstill and the leg walks SHORT. That failure is a
  failure of DEAD RECKONING: a timer said the leg was done. Here the PICTURE
  says when a waypoint is reached, so a push that covers less ground than the
  recording's simply does not advance `k` and is repeated. Walking short costs
  time, not position.

WHAT IT NEVER DOES. No reset, no Square/Triangle/OPTIONS, no pause menu, no
write to world_map.json. The only button it presses is Cross, which is the JUMP
button (CLAUDE.md §8(g): four presses spiked 10.1-12.5 against a 4.67 idle
baseline).

THE ARRIVAL AUTHORITY IS THE PROMPT, AND IT STOPS EVERYTHING AT ONCE.
`table_prompt.at_table()` is checked on the very first frame (before any push --
a recorded chain may already END at the prompt, so the character can be standing
in it when the walk starts) and on every iteration once the walk is within
TABLE_CHECK_TAIL waypoints of the end. The instant it is True the function
returns: no further turn, no further push, no strafe. The user watched the
character win the table and then walk away from it; nothing moves after the
prompt is on screen.

EVERYTHING THAT TOUCHES THE CONSOLE IS INJECTABLE, and every default is resolved
INSIDE walk() at call time. A module-level knob captured in a `def` line is
bound once at import, so a test or an A/B that redirects it changes nothing and
nothing says so -- CLAUDE.md §10.18, measured on `leg_reliability`'s `path=STORE`
and on `press(post_delay=ACTION_DELAY)` before that.
"""

import json
import math
import os
import time

import pose

# ---------------------------------------------------------------------------
# Constants. Each carries the measurement it comes from; none is invented.
# ---------------------------------------------------------------------------

# CLAUDE.md §6, the walking table: 0.45 magnitude moves 70.6px per 0.40s push
# with a spread of 15, and walking is linear to ~0.75. Repeatability collapses
# above 0.60, so 0.45 sits inside the measured-repeatable band.
PUSH_MAG = 0.45
PUSH_SEC = 0.40                 # the duration that table was measured at

# Consecutive UNMEASURABLE fixes (locate() returned None) before an escape.
# Not measured -- there is no population of "how many blind frames in a row is
# normal" yet. Exposed as a knob and logged so the first live run measures it.
MISS_MAX = 3
# Consecutive fixes that did not advance k before an escape. Same status.
STALL_MAX = 4

# pose.align_lateral's CLOSED-LOOP gain (pose.py:152): 2400 px per
# unit-magnitude-second. The open-loop figure (126px per 0.30 x 0.35s, i.e.
# ~1200) is WRONG for control -- at it the alignment loop oscillated with
# growing amplitude (+175 -> -201 -> +211 -> -215). Imported, not copied.
LATERAL_GAIN = pose.PX_PER_STRAFE_SEC
LATERAL_MAG = pose.STRAFE_MAG            # 0.30, the magnitude that gain was fitted at
# A push under ~0.10s does not move the character at all (pose.ALIGN_MIN_SEC),
# so a correction shorter than this is a no-op that reads as a correction.
# align_lateral uses the minimum push rather than giving up: measured better
# (bailing stopped at 84-116px).
LATERAL_MIN_SEC = pose.ALIGN_MIN_SEC
LATERAL_CAP_SEC = 0.3           # never lunge; a narrow passage punishes overshoot
LATERAL_TOL_PX = pose.ALIGN_TOL_PX       # 35.0 = 1.8 deg at 18.6-20.8 px/deg

TIME_CAP = 400.0                # the spec's "timed out" boundary; the harness
                                # kills the child at 420s from OUTSIDE (§10.14)

# chain.locate()'s own default window. k may never advance past k + WINDOW in
# one step: a single fix is one picture, and letting it skip an arbitrary
# distance ahead would let one wrong match teleport the plan to the end of the
# chain -- exactly the "reached is a routing claim, not evidence of position"
# failure in CLAUDE.md §8(e).
WINDOW = 3
# ADVANCE at most this many waypoints per iteration, whatever the sensor says.
# One push is 0.18 u and the user's drive put waypoints ~0.2 u apart, so a push
# passes about ONE waypoint. Trial 1 (2026-09-07 19:05) advanced 3 per push on
# fits of 13-28 inliers, ran ~6 waypoints ahead of the character in 5 pushes,
# and then found nothing in a window the character had not reached. Lagging is
# safe (the window still holds the truth); running ahead was fatal.
ADVANCE_MAX = 1
# A fix under this many RANSAC inliers neither advances k nor steers. It is the
# 5th percentile of TRUE-position inliers on the route chain's own held-out
# frames (overnight/census/chain_user_1853_closed.json: near p05 29, median
# 146; far median 7) -- measured on this chain, not chosen. Trial 1's junk fixes
# (13 and 19 inliers, dx -66 and -131) strafed the character into the wall.
FIX_MIN_INLIERS = 29
# On a miss or a weak fix, look BACK this many waypoints before counting it,
# and let k REGRESS if the look-back fits. An over-advanced k was otherwise
# permanent: the window only ever looked forward.
LOOKBACK = 2

# THE PROMPT IS CHECKED ON EVERY ITERATION (None = no tail gate). It used to be
# asked only when the target was within 3 waypoints of the end; if the sensor's
# k lagged while the character already stood in the prompt, the loop would
# stall, escape and walk away from a won table -- the exact failure the user
# watched under dead reckoning. at_table() costs milliseconds and measured 0
# false positives on 693 frames at non-table nodes (CLAUDE.md §3), so the gate
# bought nothing. An integer here restores the old gate for an experiment.
TABLE_CHECK_TAIL = None

# THE PLAN. The recorder samples every 0.25 s and ~40% of an executor-recorded
# chain is STATIONARY: the camera turns between steps and the 0.35 s settle
# after each push. Servoing onto those frames would turn to each intermediate
# heading of a corner and PUSH along it -- a curve into the inside wall. So the
# chain is compiled into a plan: walking frames every STRIDE, and each
# stationary run collapsed to ONE turn-only target carrying the run's last
# heading (turn on the spot, no push, no locate). STRIDE 1 costs no extra
# iterations because the sensor's fix.k, not the target, drives the advance.
STRIDE = 1
# |stick| at or under this is "not walking": the tap records the COMMANDED value
# and a settle or a turn is exactly 0.0. Frames whose ly is None (no tap, or a
# chain older than this field) count as walking, so nothing is silently skipped.
STATIONARY_STICK = 0.05
# A target whose heading is within this of the LAST COMMANDED heading is not
# turned to again: the camera holds its yaw while walking (only the right stick
# yaws it, §5), so re-issuing a heading only pays turn_to's compass reads, and
# inside the bar the compass abstains on ~15% of frames (OPEN-15). Scheduling,
# not a population threshold; logged per iteration.
TURN_SKIP_DEG = 1.0

# THE END OF THE CHAIN, WHICH USED TO BE A 400-SECOND FORWARD WALK.
#
# `target_k` is clamped to the last waypoint, so once k reaches it the loop can
# only ever aim at the waypoint it is already standing on. A locate() that
# honestly answers "I am at or past the last waypoint" then satisfies
# `chain.reached` on EVERY iteration forever: k is frozen, so the stall counter
# never rose, the escape ladder was unreachable, and every row still said
# "advanced" — CLAUDE.md §10.1's "a success path and a no-op path with identical
# output". Measured by the skeptic on a 6-waypoint chain with the prompt absent:
# 120 iterations, 120 forward pushes, 0 escapes, 118 of 120 rows "advanced" with
# k frozen (agent_progress/closed-loop/verify-controller/endchain.py).
#
# What SHOULD happen there is not obvious, so it is derived rather than picked.
# The chain's last waypoint is where the RECORDING stopped, and chain_record
# only keeps a chain whose end saw the prompt. So "k == n-1 and no prompt" means
# either the sensor is early or the walk landed somewhere the prompt is not —
# both measured in OPEN-22, where the goal leg ended at the round table BESIDE
# the dealer's in two recorded walks of three.
#
# OPEN-22 also holds the ONLY number anyone has about how far the prompt is from
# where a goal leg stops: at the recorded endpoint the prompt was absent at all
# five headings, and 0.05 walk-units FORWARD it appeared at four of five. One
# push here is PUSH_MAG * PUSH_SEC = 0.180 walk-units, so a SINGLE terminal push
# already covers 3.6x that measured gap.
#
# Past that, more forward pushing is the failure the user reported on day one
# and a leg-end frame has since caught: a walk into the bar that ended on a CITY
# STREET (§8(k), test_fixtures/leg_failures/overshot_outdoors_*.jpg). So the
# terminal phase is BOUNDED, and running out of it is a named FAILURE — never a
# silent 400s of forward pushes logged as progress.
END_PUSH_UNITS = 0.05           # OPEN-22's measured prompt-zone offset

ESCAPE_STRAFE_SEC = 0.3
ESCAPE_STRAFE_MAG = 0.45

# Sign convention, verified in three places rather than assumed:
#   slow_traverse.walk_leg sends `left_x = ar.to_axis(lx)`
#   walk_steps.walk_forward sends `left_x = ar.to_axis(strafe)`   (same axis)
#   walk_steps.unstick names -0.6 "left" and +0.6 "right"
#   pose.align_lateral: `side = +1 if dx > 0` with the comment "dx > 0 means the
#     scene sits RIGHT of where it should, i.e. the camera is LEFT of the
#     reference -- so strafe RIGHT, which measured dx<0"
# So: POSITIVE lx = RIGHT, and dx > 0 -> strafe RIGHT.
RIGHT = +1.0
LEFT = -1.0


def _fix_row(fix):
    """The Fix's fields as plain JSON, by attribute access only.

    chain.py is the SENSOR agent's file and is NOT imported here: chain_walk
    only ever calls `chain.locate(...)` / `chain.reached(...)` on the object it
    is handed. getattr with a default means a Fix that grows or loses a field
    does not crash a live run at minute nine.
    """
    if fix is None:
        return None
    return {name: getattr(fix, name, None) for name in
            ("k", "k_float", "inliers", "dx", "dy", "scale", "second", "detail")}


def _save(shots, iteration, k, img, log):
    if not shots:
        return
    try:
        os.makedirs(shots, exist_ok=True)
        img.save(os.path.join(shots, f"it_{iteration:03d}_k{k}.jpg"), quality=88)
    except Exception as e:                    # never let bookkeeping end a walk
        log(f"    could not save frame {iteration}: {type(e).__name__}: {e}")


def _journal(path, row, log):
    """Append one iteration's row as JSON, open-append-write-flush-close.

    WHY THIS EXISTS. The harness runs each trial as a subprocess and KILLS it at
    the external ceiling (`_harness.run_trial`, CLAUDE.md §10.14 — signal.alarm
    did not interrupt a trial blocked inside a capture). A killed child prints
    no JSON, so its `fixes` — the per-iteration record that is the whole point
    of a closed loop — died with it, on exactly the trials that need explaining.
    Written as it goes, the evidence survives the kill: §10.16, "a file written
    on completion is lost in precisely the case it exists for". Same
    append-and-flush shape as chain_record's meta.jsonl, and for the same
    reason: a crash at minute four keeps four minutes.
    """
    if not path:
        return
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
    except Exception as e:                    # never let bookkeeping end a walk
        log(f"    could not journal iteration {row.get('iteration')}: "
            f"{type(e).__name__}: {e}")


def min_iterations(n, window=None, tail=None):
    """The FEWEST iterations in which this chain could possibly arrive.

    Arrival needs an iteration whose `target_k >= n - TABLE_CHECK_TAIL`, and
    `target_k = k + 1` is computed from the k the PREVIOUS iterations left
    behind. So k must first reach `n - tail - 1`, which takes
    `ceil((n - tail - 1) / window)` iterations because k rises by at most
    `window` per iteration (deliberately — one picture may not move the plan an
    arbitrary distance), and the arrival then happens on the iteration AFTER
    that. Hence the `+ 1`.

    THAT `+ 1` WAS MISSING and the count was low by exactly one for every chain
    (skeptic's `../verify-controller/minit.py` drove walk() with the most
    generous locate possible and counted: n=1000 claimed 332, needed 333; n=10
    claimed 2, needed 3). A chain recorded at chain_record's 0.25s period over
    the 244s route is ~1000 waypoints and needs >= 333 iterations, and an
    iteration is one turn, one push, three captures and a locate.

    Nothing here refuses a long chain on its own (see `iteration_sec_floor`) —
    but a run that spends ten trials reporting TIMED_OUT must be able to say
    whether the chain was arithmetically unwalkable or the navigation failed,
    and those two need different responses. Reported on every walk.
    """
    window = ADVANCE_MAX if window is None else window
    tail = TABLE_CHECK_TAIL if tail is None else tail
    if tail is None:
        # The prompt is believed on any iteration, so the floor is just the
        # iterations k needs to reach the last waypoint at ADVANCE_MAX per step.
        return max(1, math.ceil(max(0, n - 1) / max(1, window)))
    return 1 + math.ceil(max(0, n - tail - 1) / max(1, window))


def plan_indices(wps, stride=None):
    """Compile the chain into targets: (chain index, push?, heading).

    Walking frames every `stride`; each STATIONARY run (a turn, a settle)
    collapses to ONE turn-only target carrying the run's last heading, so a
    corner is turned on the spot instead of pushed around. A heading falls
    back to the recorder's commanded `cam`, then to the last known heading, so
    an abstaining compass cannot silently skip a corner (it abstains on 6-15%
    of frames live). Index 0, the trusted spawn, is never a target; the final
    waypoint always is.
    """
    stride = STRIDE if stride is None else max(1, int(stride))
    plan, run, last_heading, walked = [], [], None, 0
    n = len(wps)
    for i, w in enumerate(wps):
        heading = getattr(w, "heading", None)
        if heading is None:
            heading = getattr(w, "cam", None)
        if heading is None:
            heading = last_heading
        else:
            last_heading = heading
        lx = getattr(w, "lx", None) or 0.0
        ly = getattr(w, "ly", None)
        # The recorder writes 0.0 with `stick:unknown` in the note when it had
        # NO stick to read (a user drive with no controller on the Mac). That
        # is unknown, not stationary: treating it as stationary would collapse
        # a whole drive into one turn-only target.
        unknown = "stick:unknown" in (getattr(w, "note", "") or "")
        stationary = (not unknown and ly is not None
                      and abs(ly) <= STATIONARY_STICK
                      and abs(lx) <= STATIONARY_STICK)
        if i == 0:
            continue
        if stationary:
            run.append((i, heading))
            continue
        if run:
            plan.append((run[-1][0], False, run[-1][1]))
            run, walked = [], 0
        if walked % stride == 0:
            plan.append((i, True, heading))
        walked += 1
    if run:
        plan.append((run[-1][0], False, run[-1][1]))
    if n > 1 and (not plan or plan[-1][0] != n - 1):
        plan.append((n - 1, True, last_heading))
    return plan


def plan_min_iterations(plan, window=None):
    """Fewest iterations for a plan: one per turn-only target, and the push
    targets at ADVANCE_MAX per iteration."""
    window = ADVANCE_MAX if window is None else window
    turns = sum(1 for _, push, _ in plan if not push)
    pushes = len(plan) - turns
    return max(1, turns + math.ceil(pushes / max(1, window)))


def end_iteration_budget(push_mag=None, push_sec=None, units=None):
    """How many iterations the loop may spend ON the last waypoint.

    DERIVED, not chosen: `units` is OPEN-22's measured prompt-zone offset
    (0.05 walk-units forward of where the recorded goal leg stops) and one push
    covers `push_mag * push_sec` walk-units, so this is the number of pushes
    that covers the gap, floored at one. At the shipped 0.45 x 0.40 = 0.180
    units a push, that is ONE — a single push already covers 3.6x the measured
    gap, and everything beyond it is walking past the table.

    Exposed as a knob on `walk()` because 0.05 is ONE measurement at ONE spot
    (three walks, one of which reached the zone) and a live run may need to
    move it. It is logged on every walk so the first live run measures it.
    """
    mag = PUSH_MAG if push_mag is None else push_mag
    sec = PUSH_SEC if push_sec is None else push_sec
    units = END_PUSH_UNITS if units is None else units
    per_push = abs(mag) * abs(sec)
    if per_push <= 0:
        return 1
    return max(1, math.ceil(units / per_push))


def _timeout_diagnosis(res, n, min_iters, time_cap):
    """Why did the cap run out: the chain's LENGTH, or the walking?

    A timeout with no diagnosis is CLAUDE.md §10.1's "two paths with identical
    output": ten trials of a chain too long to finish look exactly like ten
    navigation failures, and the fix for each is the opposite of the other.
    """
    per = sorted(r["seconds"] for r in res["fixes"] if r.get("iteration"))
    if not per:
        return (f"no iteration completed inside the {time_cap:.0f}s cap — "
                f"suspect the console, not the chain")
    med = per[len(per) // 2]
    need = med * min_iters
    advanced = sum(1 for r in res["fixes"] if r.get("action") == "advanced")
    if need > time_cap:
        return (f"ARITHMETIC: {n} waypoints need >= {min_iters} iterations and "
                f"the median iteration took {med:.2f}s, i.e. >= {need:.0f}s "
                f"against a {time_cap:.0f}s cap — this chain could not be "
                f"walked in the cap however well it navigated. Record a "
                f"sparser chain or raise the cap; do not read this as a "
                f"navigation failure.")
    return (f"NAVIGATION: {len(per)} iterations at a median {med:.2f}s "
            f"({advanced} advanced) — the cap allowed the >= {min_iters} "
            f"iterations this chain needs, so the time went into not "
            f"advancing. k stopped at {res['k_final']} of {n - 1}.")


def walk(chain, capture, read_heading, log=print, time_cap=None, shots=None,
         journal=None, iteration_sec_floor=None, end_iterations=None,
         turn_to=None, push=None, strafe=None, jump=None, at_table=None,
         now=time.time):
    """Servo along `chain` until the dealer prompt is on screen.

    Returns {arrived, seconds, pushes, k_final, iterations, waypoints,
    min_iterations, iteration_budget_sec, end_iterations, fixes, failure}.

    `journal` is a path each iteration's row is appended to as it happens, so a
    child killed at the harness ceiling still leaves its evidence on disk.

    `iteration_sec_floor` is the OPTIONAL up-front feasibility check: given a
    floor on what one iteration costs, a chain needing more than the cap is
    refused before a single push instead of burning the whole cap to say so.
    It defaults to None — NEVER refuse — because no such floor has been
    measured on this rig yet, and SPEC's rule is that an unmeasured gate is a
    knob defaulted to off with the quantity logged, never an invented constant.

    `end_iterations` is how many iterations may be spent standing ON the last
    waypoint before the walk gives up. It defaults to `end_iteration_budget()`,
    which is DERIVED from OPEN-22's measured prompt-zone offset rather than
    chosen. `time_cap` defaults to TIME_CAP. Both are resolved here rather than
    in the signature: a module-level knob captured in a `def` line is bound
    once at import, so redirecting it changes nothing and nothing says so
    (§10.18).

    `turn_to`, `push`, `strafe`, `jump` and `at_table` default to the real
    console functions, resolved HERE rather than in the signature (§10.18).
    Their contracts, so a stub and the real thing cannot drift apart:

        turn_to(heading)        turn the camera to an absolute bearing
        push(mag, secs)         ONE continuous forward push, mag > 0 = forward
        strafe(lx, secs)        ONE continuous sidestep, lx > 0 = RIGHT
        jump()                  press Cross once
        at_table(img) -> bool   is the BASEBALL CARDS prompt on screen
    """
    if time_cap is None:
        time_cap = TIME_CAP
    end_budget = (end_iteration_budget() if end_iterations is None
                  else max(1, int(end_iterations)))
    if turn_to is None:
        import slow_traverse as st
        def turn_to(heading, _st=st):
            return _st.turn_to(heading, read_heading, capture, log=log)
    if push is None:
        import slow_traverse as st
        def push(mag, secs, _st=st):
            # step_sec == seconds is ONE continuous push. Chunking it would
            # re-accelerate from a standstill and cover less ground -- the
            # GRAVEYARD row that ended two rooms adrift.
            return _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                                label="chain push", log=log, step_sec=secs)
    if strafe is None:
        import slow_traverse as st
        def strafe(lx, secs, _st=st):
            return _st.walk_leg(lx, 0.0, secs, capture, read_heading,
                                label="chain strafe", log=log, step_sec=secs)
    if jump is None:
        import input_controller as ic
        def jump(_ic=ic):
            # Cross IS the jump button (§8(g)). It is also the ONLY button this
            # module is allowed to press.
            return _ic.press("cross")
    if at_table is None:
        import table_prompt
        at_table = table_prompt.at_table

    t0 = now()
    res = {"arrived": False, "seconds": 0.0, "pushes": 0, "k_final": 0,
           "iterations": 0, "fixes": [], "failure": None}
    wps = chain.waypoints
    n = len(wps)
    if n < 2:
        res["failure"] = f"chain has {n} waypoint(s); nothing to walk"
        log(f"  chain_walk: {res['failure']}")
        return res

    # THE ARITHMETIC, BEFORE ANYTHING MOVES, because a TIMED_OUT with no
    # arithmetic beside it cannot be told from a navigation failure.
    plan = plan_indices(wps)
    n_turn = sum(1 for _, push, _ in plan if not push)
    n_push = len(plan) - n_turn
    min_iters = max(min_iterations(n), plan_min_iterations(plan))
    res["waypoints"] = n
    res["plan_targets"] = len(plan)
    res["plan_pushes"] = n_push
    res["plan_turns"] = n_turn
    res["min_iterations"] = min_iters
    res["iteration_budget_sec"] = round(time_cap / min_iters, 3)
    res["end_iteration_budget"] = end_budget
    log(f"  chain_walk: {n} waypoints -> plan of {len(plan)} targets "
        f"({n_push} push, {n_turn} turn-only); the prompt is checked on every "
        f"iteration; k rises by at most {ADVANCE_MAX} per iteration, so >= "
        f"{min_iters} iteration(s). The {time_cap:.0f}s cap allows "
        f"{res['iteration_budget_sec']:.2f}s each. At the last waypoint the "
        f"walk may spend {end_budget} more iteration(s) — "
        f"{end_budget * PUSH_MAG * PUSH_SEC:.3f} walk-units of forward push "
        f"against OPEN-22's measured {END_PUSH_UNITS} — and then gives up "
        f"rather than walking on past the table.")

    k = 0                       # the last waypoint we believe we are AT.
                                # 0 is the reset spawn, which is trusted the way
                                # graph_walk.TRUST_RESET_SPAWN trusts it: the
                                # spawn is deterministic (bearing 86.9/87/87).
    misses = 0
    stalls = 0
    escapes = 0
    iteration = 0
    end_iters = 0               # iterations spent standing ON the last waypoint
    pi = 0                      # the plan pointer: first target past k
    last_cmd = None             # the last heading actually commanded
    plan_last_heading = next((h for _, _, h in reversed(plan) if h is not None),
                             None)

    def finish(failure=None):
        res["seconds"] = round(now() - t0, 2)
        res["k_final"] = k
        res["iterations"] = iteration
        res["end_iterations"] = end_iters
        res["failure"] = failure
        if failure == "timed out":
            res["timeout_diagnosis"] = _timeout_diagnosis(
                res, n, min_iters, time_cap)
            log(f"  chain_walk: {res['timeout_diagnosis']}")
        return res

    def record(row):
        """One row, in the result AND on disk. Never one without the other."""
        res["fixes"].append(row)
        _journal(journal, row, log)

    if iteration_sec_floor is not None:
        need = min_iters * float(iteration_sec_floor)
        if need > time_cap:
            log(f"  chain_walk: REFUSING before the first push — {n} waypoints "
                f"need >= {min_iters} iterations at >= {iteration_sec_floor}s "
                f"each = {need:.0f}s, against a {time_cap:.0f}s cap.")
            return finish(
                f"chain too long for the cap: {n} waypoints need >= "
                f"{min_iters} iterations at >= {iteration_sec_floor}s each "
                f"= {need:.0f}s > {time_cap:.0f}s")

    def escape():
        """One escape. Jump first, then sidesteps alternating LEFT, RIGHT, ...

        Jump first because it moves nothing sideways, which is what a passage
        with stools on one side and a wall on the other requires; measured
        escape outcomes against real blockers were None, None, jump, None, None,
        None, wait, jump (§8(g)).
        """
        nonlocal escapes
        which = escapes
        escapes += 1
        if which == 0:
            jump()
            return "escape:jump"
        side = LEFT if which % 2 == 1 else RIGHT
        strafe(side * ESCAPE_STRAFE_MAG, ESCAPE_STRAFE_SEC)
        return "escape:left" if side < 0 else "escape:right"

    # THE FIRST FRAME, BEFORE ANYTHING MOVES. A chain recorded to the table ends
    # at the prompt, so a walk started from there is already finished; pushing
    # once "to get going" would walk the character out of the prompt zone, which
    # the user has watched happen.
    img = capture()
    _save(shots, iteration, k, img, log)
    if at_table(img):
        res["arrived"] = True
        record({"iteration": 0, "k": 0, "target": None,
                "fix": None, "action": "arrived",
                "lateral": None, "at_end": False, "seconds": 0.0,
                "elapsed": round(now() - t0, 2)})
        log("  chain_walk: the prompt is ALREADY on screen — stopping before "
            "the first push")
        return finish()

    while True:
        elapsed = now() - t0
        if elapsed >= time_cap:
            log(f"  chain_walk: {elapsed:.1f}s >= cap {time_cap:.0f}s at k={k} "
                f"of {n - 1} — TIMED OUT")
            return finish("timed out")

        # THE PLAN POINTER: the next target is the first plan entry past k.
        while pi < len(plan) and plan[pi][0] <= k:
            pi += 1
        # THE END OF THE CHAIN IS A BOUNDED PHASE. Past the last target there
        # is nothing left to servo onto: every further push is dead reckoning
        # with no reference, which is the thing this module exists to replace.
        at_end = pi >= len(plan)
        if at_end:
            end_iters += 1
            if end_iters > end_budget:
                log(f"  chain_walk: at the LAST waypoint ({k} of {n - 1}) and "
                    f"the prompt is not on screen after {end_budget} terminal "
                    f"iteration(s) — giving up rather than walking on past the "
                    f"table")
                return finish(
                    f"reached the last waypoint ({k} of {n - 1}) without the "
                    f"prompt; spent the {end_budget}-iteration end budget "
                    f"(~{end_budget * PUSH_MAG * PUSH_SEC:.3f} walk-units "
                    f"against OPEN-22's measured {END_PUSH_UNITS} to the "
                    f"prompt zone). Either the sensor is early or the walk "
                    f"landed where the prompt is not — OPEN-22 measured both.")

        iteration += 1
        it_t0 = now()
        if at_end:
            # Nothing left in the plan: push toward the last waypoint along
            # the plan's final heading, inside the end budget above.
            target_k, do_push, heading = n - 1, True, plan_last_heading
        else:
            target_k, do_push, heading = plan[pi]

        turned = False
        if heading is not None and (
                last_cmd is None
                or abs((heading - last_cmd + 540.0) % 360.0 - 180.0) > TURN_SKIP_DEG):
            turn_to(heading)
            last_cmd = heading
            turned = True
        if do_push:
            push(PUSH_MAG, PUSH_SEC)
            res["pushes"] += 1

        img = capture()
        _save(shots, iteration, k, img, log)

        # STOP AT ONCE, ON EVERY ITERATION, BEFORE THE SENSOR IS EVEN ASKED.
        # This sits before every branch that could move anything.
        if (TABLE_CHECK_TAIL is None or target_k >= n - TABLE_CHECK_TAIL) \
                and at_table(img):
            res["arrived"] = True
            record({"iteration": iteration, "k": k,
                    "target": target_k, "fix": None,
                    "action": "arrived", "lateral": None,
                    "at_end": at_end,
                    "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            log(f"  chain_walk: ARRIVED at iteration {iteration}, k={k} "
                f"(target {target_k} of {n - 1}), {res['pushes']} push(es)")
            return finish()

        if not do_push:
            # A turn-only target: a stationary run in the recording (a corner,
            # a settle). Turned on the spot, reached by construction, no locate.
            k = target_k
            misses = 0
            stalls = 0
            record({"iteration": iteration, "k": k, "target": target_k,
                    "fix": None, "action": "turned", "lateral": None,
                    "at_end": False, "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  turned"
                f"{'' if turned else ' (skipped, same heading)'} to {heading}")
            continue

        fix = chain.locate(img, k)
        inl = None if fix is None else (getattr(fix, "inliers", 0) or 0)
        weak = fix is not None and inl < FIX_MIN_INLIERS
        regressed = False
        if (fix is None or weak) and k > 0:
            # LOOK BACK before believing a miss: the hint two behind widens the
            # window to [k-3, k+1], which is where an over-advanced k's truth is.
            back = chain.locate(img, max(0, k - LOOKBACK))
            binl = None if back is None else (getattr(back, "inliers", 0) or 0)
            if back is not None and binl >= FIX_MIN_INLIERS and (fix is None or binl > inl):
                fix, inl, weak = back, binl, False
                if int(back.k) < k:
                    k = max(0, int(back.k))
                    regressed = True

        escaped = False
        if regressed:
            misses = 0
            stalls = 0
            action = "regressed"
        elif fix is None:
            misses += 1
            if misses >= MISS_MAX:
                action = escape()
                escaped = True
                misses = 0
            else:
                action = "miss"
        elif weak:
            # Readable but not credible: neither an advance nor a miss. It
            # counts as a stall so a run of them still reaches the escape.
            misses = 0
            stalls += 1
            if stalls >= STALL_MAX:
                action = escape()
                escaped = True
                stalls = 0
            else:
                action = "weak"
        else:
            misses = 0
            # Never further than ADVANCE_MAX ahead (one push passes about one
            # waypoint; a wrong match must not run the plan ahead of the
            # character) and never past the last waypoint (locate() may
            # honestly answer "past the end of the chain").
            new_k = min(int(fix.k), k + ADVANCE_MAX, n - 1)
            # AN ADVANCE IS k ACTUALLY MOVING, not `reached` returning True.
            # At the last waypoint `target_k` IS k, so an honest "I am at or
            # past it" satisfies `reached` on every iteration forever: the
            # stall counter never rose, the escape ladder was unreachable, and
            # 118 of 120 measured rows said "advanced" with k frozen. A success
            # path and a no-op path with identical output (§10.1). Mid-chain
            # this changes nothing — `reached(fix, k+1)` forces `fix.k >= k+1`,
            # so `new_k > k` always holds there.
            if chain.reached(fix, target_k) and new_k > k:
                k = new_k
                stalls = 0
                action = "advanced"
            else:
                stalls += 1
                if stalls >= STALL_MAX:
                    action = escape()
                    escaped = True
                    stalls = 0
                else:
                    action = "stalled"

        # AT MOST ONE LATERAL PUSH PER ITERATION, and none in an iteration that
        # already escaped: a 0.3s sidestep at 0.45 is ~324px at the closed-loop
        # gain, so a correction computed from the PRE-escape dx would be stale
        # and would fight the escape it just paid for.
        lateral = None
        dx = None if (fix is None or weak) else getattr(fix, "dx", None)
        if dx is not None and not escaped and abs(dx) > LATERAL_TOL_PX:
            secs = min(LATERAL_CAP_SEC, abs(dx) / (LATERAL_GAIN * LATERAL_MAG))
            if secs < LATERAL_MIN_SEC:
                secs = LATERAL_MIN_SEC     # a shorter push does not move at all
            side = RIGHT if dx > 0 else LEFT
            strafe(side * LATERAL_MAG, secs)
            lateral = {"dx": float(dx),
                       "side": "right" if side > 0 else "left",
                       "seconds": round(secs, 3)}

        # `at_end` is what tells a terminal stall from a mid-chain one in
        # the journal: at the last waypoint k == target and no push can
        # advance it, so the two need different readings.
        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,
               "seconds": round(now() - it_t0, 2),
               "elapsed": round(now() - t0, 2)}
        record(row)
        log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action:14s}"
            f"  fix={_fix_row(fix)}"
            + (f"  strafe {lateral['side']} {lateral['seconds']:.2f}s"
               if lateral else ""))
