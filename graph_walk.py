"""Walk a routed path. The piece that was missing between route() and the game.

    import graph_walk, worldmap
    m = worldmap.WorldMap.load()
    graph_walk.follow(m, "bar_jukebox", "dealer_table")

WHY THIS EXISTS
---------------
`WorldMap.route()` returned a list of place names and NOTHING consumed it —
worldmap had zero production importers. Meanwhile go.attempt() navigated by
replaying 60.5s of recorded controller samples with one compass correction, and
reached the table on 6 of 20 attempts. This turns a route into movement.

THE THREE THINGS IT REFUSES TO DO
---------------------------------
1. **Walk a leg that has no steps.** `m.steps_for()` raises. A leg with a cost
   but no heading can be priced and not walked, and an executor that skipped it
   would report the route completed while standing still — the exact "did
   nothing, looked like working" shape this codebase keeps producing.

2. **Confirm arrival with the wrong instrument.** At the table it asks
   `table_prompt.at_table()`, never `places.identify()`: the descriptor does not
   mask the prompt box, so identify()'s whole confidence at `dealer_table` IS
   the prompt text. Two detectors reading the same pixels are not corroboration.

3. **Guess between places it cannot tell apart.** Nodes with no reference frames
   (the dark office pair) and nodes listed in the map's `confusable` are
   UNVERIFIABLE by appearance, and that is recorded per leg rather than
   papered over with a confident-looking answer.

WHY IT WALKS IN CHUNKS
----------------------
Through `slow_traverse.walk_leg`, which pushes for 0.25s at a time and measures
after each push. Two measured reasons, not a preference:

  - chiaki releases injected input after 5s (INJECT_TIMEOUT_MS), so a single
    stick write caps a leg at ~4.5s and the 15.68s leg could never complete;
  - `walk_steps.walk_forward` returns one before/after grey difference for the
    whole leg, which reads identically whether it walked cleanly or travelled
    two seconds and jammed on a doorframe.
"""

import os
import time

# The destination whose arrival is confirmed by the PROMPT, not by appearance.
GOAL = "dealer_table"

# Nodes that have no appearance reference at all, by deliberate choice — see
# build_world_map.SEED_PLACES. Their frames are too dark to fingerprint, and
# seeding them created false positives elsewhere.
UNSEEDED = ("office_corridor", "office_door")

# A step whose view changed less than this did not travel. Measured on a leg
# that walked into a wall: blocked steps produced 1.9-3.1 while the same leg's
# clean steps produced 14.7-17.6. Two in a row is a wall, not a quiet frame.
# HOW LITTLE MOVEMENT COUNTS AS BLOCKED.
#
# 6.0 CUT THROUGH THE MIDDLE OF A UNIMODAL DISTRIBUTION. Measured over 20 runs
# of `office_corridor -> office_door` step 7/7 (a 0.42s push in an unlit
# corridor), the view-change values were:
#
#     3.1 | 5.5 5.7 5.7 5.8 | 6.1 6.3 6.3 6.5 6.5 6.6 6.9 6.9 7.0 7.1 7.2 7.3
#         7.3 7.6 7.9
#
# One population, no low cluster — so the 6.0 gate fired on 5 of 20 as FALSE
# POSITIVES. Each false fire runs the escape ladder, which injects four
# SLIP_PUSH_SEC of unaccounted FORWARD push plus two strafes, displacing the
# character in a way nothing downstream accounts for.
#
# The damage is measured, not inferred: runs whose office leg went clean
# reached bar_pool_room 14/15; runs where the gate fired reached it 0/5.
# Fisher exact two-sided p = 0.00039.
#
# 2.5 WAS TRIED AND LOST ITS A/B. Keep 6.0.
#
# The motivation was good: over 20 runs of one leg the view-change values formed
# ONE population (3.1 to 7.9), so a gate at 6.0 cut through the middle of it and
# fired on 5 of 20 as false positives — each firing the escape ladder, which
# injects forward push nothing downstream accounts for. Runs whose office leg
# went clean reached the next node 14/15; runs where the gate fired, 0/5.
# Fisher p = 0.00039.
#
# Intervened on, 2.5 arrived 6/10 against 6.0's 8/10, permutation p = 0.63 —
# and the point estimate favours the ORIGINAL. So the low view-change was a
# SYMPTOM of an already-bad run, not its cause: the character was probably
# already displaced, which both reduced the view change AND caused the later
# miss. An association at p = 0.00039 bought nothing.
#
# This is the canonical example of the project's hardest-won rule: only an
# INTERVENTIONAL A/B counts. See GRAVEYARD.md.
#
# ITS UNITS ARE GREY LEVELS. Everything above was measured on
# `slow_traverse._change`, i.e. `np.abs(grey_a - grey_b).mean()` over a 0-255
# image — the mean absolute brightness difference between two frames. That is
# the ONLY quantity this constant may be compared against.
#
# It is NOT pixels. `_slip_past` returns PIXELS (pose.displacement, RANSAC
# median inlier displacement), and the two are unrelated: a stationary camera
# reads ~0 px but a nonzero grey delta, while a mover crossing a still frame
# reads a large grey delta at 0 px. See STALL_CHANGE_UNITS below, and the
# comparison site in walk_link, for the mismatch this caused.
STALL_CHANGE = 6.0
# The units `STALL_CHANGE` is expressed in, named so the mismatch below is
# greppable rather than a matter of remembering.
#
# WHAT WENT WRONG, 2026-09-05. `walk_link` did
#
#     best = max(best, best2)          # best  = GREY LEVELS from walk_leg
#                                      # best2 = PIXELS  from _slip_past
#     if best < STALL_CHANGE:          # ...compared against a GREY-LEVEL bar
#
# so a FAILED escape ladder that measured anything in [STALL_CHANGE,
# SLIP_PROGRESS_PX) pixels cleared the stall gate. That band is not empty: it
# straddles pose.py's own stationary-noise ceiling of 8.80px (n=23, median
# 3.58), i.e. a character that had not moved at all could read high enough to
# be declared unblocked. `pose.same_pose` would call 14.9px THE SAME POSE while
# this gate called it progress.
#
# MEASURED IMPACT ON DISK: zero. Harvested from the 85 escape-ladder episodes
# in overnight/{streak,streak2,failframes,newleg,phase1/step3}.log —
#
#     FAILED  ladders (n=65)   best2 px = {0.0: 63,  4.3: 1,  5.9: 1}
#     CLEARED ladders (n=20)   best2 px = 21.4 .. 917.5
#
# — the failed population tops out at 5.9px against the 6.0 bar, a margin of
# 0.1px. So at 6.0 the mismatch never once changed an outcome; it gave the
# right answer because 6.0 grey-levels happens to land in the same empty band
# as 20.0 pixels. At STALL_CHANGE = 2.5 it would have falsely cleared 2 of 65.
# (The CLEARED side is CENSORED by SLIP_PROGRESS_PX — a ladder returns the
# instant a rung reaches 20px — so it is not independent evidence for 20.0.
# The independent evidence is pose.py's calibration: stationary MAX 8.80px vs
# smallest real 0.2s step MIN 32.25px, and 20.0 sits inside that gap.)
STALL_CHANGE_UNITS = "grey_levels"
STALL_STEPS = 2
# A push at least this long that produced no view change is a wall by itself;
# it does not need a second push to confirm it.
LONG_PUSH_SEC = 1.0


class _Blocked:
    """A hazard shaped like slow_traverse's, raised at the leg level."""

    kind = "BLOCKED"

    def __init__(self, t, note):
        self.t, self.note, self.heading = t, note, None

    def __repr__(self):
        return f"BLOCKED t={self.t:5.2f}  {self.note}"


def _default_capture():
    import compass
    return compass.fast_capture()


def _default_heading():
    import walk_steps as ws
    return ws.read_heading()


def confirmable(m, node):
    """Can arrival at `node` be checked by looking? Measured, not assumed."""
    if node == GOAL:
        return True                      # by the prompt, not by appearance
    if node in UNSEEDED:
        return False
    for pair in getattr(m, "confusable", []) or []:
        if node in pair:
            return False
    return True


def confirm(m, node, img, log=print):
    """(verdict, detail) where verdict is True / False / None(=unverifiable)."""
    if node == GOAL:
        import table_prompt
        ok = bool(table_prompt.at_table(img))
        return ok, f"at_table={ok}"
    if not confirmable(m, node):
        why = ("no appearance reference by design" if node in UNSEEDED
               else "confusable with a neighbour")
        return None, why
    import places
    room, score, margin = places.identify(img)
    if room == node:
        return True, f"{room} {score:.3f}/{margin:.3f}"
    if room is None:
        # ABSTAINING IS NOT BEING LOST. Measured over every live run on
        # 2026-09-01: 10 mid-route confirmations failed and ALL TEN were
        # abstentions — identify() never once named a different room. Each one
        # I opened showed the character standing in the correct place; the
        # reference set simply did not cover that pose or that arrangement of
        # NPCs. Treating "I am not sure" as "I am lost" threw away routes that
        # were working, and the run stopped at node 1 of 5.
        return None, f"unverified, abstained ({score:.3f}/{margin:.3f})"
    return False, f"saw {room} ({score:.3f}/{margin:.3f})"


SPAWN = "office_corridor"     # where reset_environment() deterministically lands


# LOOK AROUND BEFORE DECLARING THE CHARACTER LOST.
#
# "Lost" triggers a reset, which rewinds to the spawn and re-walks the whole
# route — the single most expensive thing this system does (~75s of a 338s
# trial). But some of those are not lost at all: on 2026-09-03 the character
# stood in a known room facing a blown-out white wall, locate() abstained on a
# frame with almost no structure, and simply TURNING recovered it.
#
# Turning is the one recovery that CANNOT make position worse — measured, it
# does not move the character. That is what distinguishes this from the
# recovery FAN, which moves and was measured worse (155s vs 75s median,
# arriving less often, because its cost was additive to the reset that
# followed anyway).
#
# Bounded: a few bearings, capture at each, stop at the first confident answer.
# Costs a few seconds against a reset's ~75.
#
# IT LIVES IN go_to_node_verified, NOT IN locate(). locate() is a QUERY and
# must have no side effects: `Bretts_walk.py where` is documented as "MOVES
# NOTHING", and diagnostics call it constantly. Putting the turn inside locate
# gave every caller a hidden side effect and immediately broke a test that had
# been guarding go_to_table's reset behaviour — the test was right.
RELOCALISE_BY_TURNING = True
RELOCALISE_BEARINGS = (60.0, 120.0, 180.0, 240.0, 300.0)   # relative, in order


def _look_around_for_a_node(m, capture, log=print):
    """Turn in place, re-running locate() at each bearing. (node, detail)|None.

    Returns None if nothing was recognised anywhere, which is a genuinely lost
    character rather than one facing a wall.
    """
    import walk_steps as ws

    start = ws.read_heading()
    if start is None:
        # The caller resets after this — ~40-60s, discarding every node already
        # verified — so it matters enormously that "the sweep ran and
        # recognised nothing" and "the sweep never ran" are distinguishable.
        # They were not.
        log("      no compass reading — the relocalise sweep did NOT run "
            "(this is not 'nothing was recognised')")
        return None
    for rel in RELOCALISE_BEARINGS:
        ws.turn_to((start + rel) % 360.0, log=lambda *a: None)
        time.sleep(0.35)
        node, detail = locate(m, capture=capture, log=lambda *a: None)
        if node is not None:
            log(f"      re-localised by turning {rel:.0f} deg: {detail}")
            return node, detail
    # Put the camera back so the caller's next leg starts from the heading it
    # would have had. Turning does not move the character, so this is free.
    ws.turn_to(start, log=lambda *a: None)
    return None


def locate(m, img=None, capture=None, log=print):
    """Which graph node are we standing on? (node, detail), node may be None.

    Only ever answers with a node the GRAPH knows, because a name the router
    cannot plan from is no more useful than None — and answering a place that
    is not in the map is how a confident wrong room sends a route into a wall.
    """
    import places
    import table_prompt

    capture = capture or _default_capture
    img = capture() if img is None else img

    # The table first, and by the PROMPT. It is the destination, it is the one
    # node whose appearance signature is really the prompt text, and being
    # already there must not be mistaken for being anywhere else.
    if table_prompt.at_table(img):
        return GOAL, "at_table"

    room, score, margin = places.identify(img)
    if room is None:
        return None, f"unrecognised ({score:.3f}/{margin:.3f})"
    if room not in m.landmarks:
        # A labelled place that is not a graph node cannot be planned from.
        return None, f"{room} is labelled but not in the graph"
    if not confirmable(m, room):
        return None, f"{room} is not verifiable by appearance"
    return room, f"{room} {score:.3f}/{margin:.3f}"


def go_to_table(m, capture=None, read_heading=None, log=print, shots=None,
                allow_reset=True):
    """Get to the table from WHEREVER the character currently is.

    Two ways in, in order of cost:

      1. recognise the current node and route from it;
      2. failing that, reload the save — which puts the character on the spawn
         deterministically — and route from there.

    The fallback is what makes "from anywhere" true rather than "from anywhere
    I happen to recognise". It is not free (a reload discards an in-progress
    match) but it costs no money: the save restores the wallet.
    """
    capture = capture or _default_capture
    read_heading = read_heading or _default_heading

    node, detail = locate(m, capture=capture, log=log)
    log(f"  located: {node!r} ({detail})")
    if node == GOAL:
        log("  already at the table")
        return {"arrived": True, "reached": GOAL, "reason": "already_there",
                "legs": [], "reset": False}
    if node is not None:
        res = follow(m, node, GOAL, capture, read_heading, log=log, shots=shots)
        res["reset"] = False
        if res["arrived"]:
            return res
        log("  routing from the recognised node did not land it")
        if not allow_reset:
            return res

    if not allow_reset:
        return {"arrived": False, "reached": None, "reason": "unlocated",
                "legs": [], "reset": False}

    log("  cannot plan from here — reloading the save to reach a known start")
    import reset_env
    try:
        reset_env.reset_environment(log=log)
    except Exception as e:
        log(f"  reset failed ({type(e).__name__}: {e})")
        return {"arrived": False, "reached": None, "reason": "reset_failed",
                "legs": [], "reset": True}
    res = follow(m, SPAWN, GOAL, capture, read_heading, log=log, shots=shots)
    res["reset"] = True
    return res


# Consecutive recorded steps within this many degrees are ONE push.
#
# The recording is a human's stick samples, so a straight 5.13s walk arrives as
# seven separate steps that happen to share a bearing. Replaying them as seven
# pushes means seven accelerations from standstill, and the distance lost to
# each one is exactly the drift that puts the character a metre out by the end.
# Measured 2026-09-01: the route was 40 separate accelerate/decelerate cycles
# over 25.5s of walking, and 11 of 12 end-to-end failures were the last leg
# missing its mark.
#
# The cap is chiaki's input watchdog: it releases the stick if nothing is
# written for INJECT_TIMEOUT_MS (5s), so no single push may approach that.
MERGE_TOL_DEG = 8.0
MERGE_MAX_SEC = 4.0

# OFF, because it was A/B tested twice and the honest test says it HURTS.
#
# The theory was good and everyone liked it: seven pushes to walk one straight
# 5.13s stretch means seven accelerations from standstill, and merging took the
# route from 40 accelerate/decelerate cycles to 15 with distance preserved.
#
# The first A/B looked neutral, but it measured follow()'s "reached", which is a
# routing claim rather than a position. Re-run 2026-09-02 measuring the last
# node the localiser actually VERIFIED:
#
#     merged    verified depth [0, 4, 0]   mean 1.3 of 5
#     unmerged  verified depth [3, 2, 4]   mean 3.0 of 5
#
# n=3 per arm, so treat 1.3 vs 3.0 as a direction and not a coefficient — but
# it is the opposite direction from the one the change was made for, and the
# unmerged arm is also far more consistent. The likely mechanism is overshoot:
# a merged push covers more ground than the stop-start sequence it replaces, so
# legs that used to stop short now run into furniture.
#
# Kept, not deleted, because it is measured, tested and may be right once legs
# are re-recorded from the executor's own poses rather than a human's.
MERGE_STEPS = False

# PER-LEG MERGING. The global flag above stays False — its A/B measured worse,
# and although that was n=3/arm (power 0.00 by 10.3) the stated mechanism is
# real: a merged push covers more ground than the stop-start sequence it
# replaces, so a leg that used to stop short can run into furniture.
#
# That argument does not apply to office_corridor -> office_door, and the reason
# it does not is measurable rather than hopeful: it is a straight CORRIDOR, all
# seven recorded steps within 0.33 deg of each other, walls on both sides so a
# distance error has little room to become a position error, no furniture and no
# NPCs, and it arrives 20/20 (n=20).
#
# WHY IT MATTERS MORE NOW THAN IT DID. Running the leg at LEG_SPEED_BY_LEG
# shortened each push to ~0.28s but left all seven SETTLE_SEC pauses at 0.35s:
#
#     7 pushes   1.71s of walking
#     7 settles  2.45s of standing still      -> 59% of the leg is a pause
#     merged     1.71s + one 0.35s settle = 2.06s
#
# So speeding the leg up made its overhead DOMINATE, and merging is what
# recovers the point of it. The user saw this directly on the stream — "you walk
# and stop a lot, kinda defeats the point of walking max speed" — before it was
# measured. Together the two changes take leg 1 from 5.13s to 2.06s.
#
# Add a leg here only when it has the same three properties: constrained on both
# sides, straight, and measured reliable. Not the bar.
MERGE_STEPS_BY_LEG = {("office_corridor", "office_door")}

# A MERGED LEG NEEDS A TIGHT TURN, and the two must be changed together.
#
# Seven pushes re-issue turn_to seven times, so a heading error gets another
# chance each step (mostly NO-OPs, but the opportunity is there). ONE push does
# not: whatever heading the single turn lands on is walked for the entire
# distance. Merging therefore makes turn accuracy matter MORE, not less.
#
# Observed immediately after merging leg 1, on the first live walk:
#
#     turn to 270.2: TURNED to 273.9 (err -3.7) in 2 push(es)
#     step 1/1 bearing 270.2 (got 273.9) 1.95s -> walked 1.95s
#
# turn_to stopped 3.7 deg out because TURN_TOLERANCE is 4.0 and 3.7 is "close
# enough" by that rule. The user, watching, put it exactly: "the reticle wasn't
# perfectly on the door." Over 1.168 walk-units a 3.7 deg error is ~0.075 units
# of lateral drift carried the whole way, and the leg ends against the door
# frame rather than square to it.
#
# THIS IS NOT OPEN-3. That asked whether to tighten the tolerance so mid-leg
# turns chase the RECORDED CURVE, and the answer was no — 22 of 23 of those
# curves are the human's left thumb, not camera movement. This tightens the
# ONE turn that aims a merged push, so the commanded heading is actually
# achieved. Different turn, different reason.
#
# 1.0 deg is achievable: the yaw-null added 2026-09-05 turns to 0.5 and the logs
# show "TURNED to 288.0 (err +0.1) in 1 push(es)". The ~3.8 deg quantum in
# section 6 is the floor at FULL stick; small corrections use less.
MERGED_TURN_TOLERANCE = 1.0


def merge_steps(steps, tol=MERGE_TOL_DEG, cap=MERGE_MAX_SEC):
    """Collapse consecutive same-bearing steps into single continuous pushes.

    Bearing of a merged push is the DURATION-WEIGHTED mean of its parts, so a
    slight drift across a run of steps is honoured rather than snapped to
    whichever one happened to come first.
    """
    out = []
    for s in steps:
        if out:
            prev = out[-1]
            gap = abs((s["bearing"] - prev["bearing"] + 180.0) % 360.0 - 180.0)
            if gap <= tol and prev["dur"] + s["dur"] <= cap:
                total = prev["dur"] + s["dur"]
                # Weighted circular mean, so 359 and 1 do not average to 180.
                import math
                x = (math.sin(math.radians(prev["bearing"])) * prev["dur"]
                     + math.sin(math.radians(s["bearing"])) * s["dur"])
                y = (math.cos(math.radians(prev["bearing"])) * prev["dur"]
                     + math.cos(math.radians(s["bearing"])) * s["dur"])
                prev["bearing"] = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
                prev["dur"] = total
                prev["speed"] = max(prev["speed"], s.get("speed", 0.22))
                continue
        out.append(dict(s))
    return out


# A blocked push is either a WALL or an NPC in the way, and it would be nice to
# tell them apart before choosing a response.
#
# THAT TEST WAS TRIED AND REMOVED. The idea was "a wall does not move": compare
# two frames while standing still and call a changing scene an NPC. Measured
# 2026-09-02, standing perfectly still produces scene changes of 0.91-6.41
# (median 4.09), so the 2.0 threshold sat UNDER the noise floor and called every
# blockage a mover — including walls. The same threshold-below-noise mistake
# that cost a day on reset_env.CONFIRM_DELTA_MIN.
#
# It could be fixed by raising the threshold, except the other side is not
# measurable on demand: an NPC has to actually wander in. Rather than pick a
# number for the half I cannot measure, the escape simply runs on every
# blockage. It is bounded (~10s), it undoes its own side-steps, and against a
# wall it costs time and nothing else.
WAIT_OUT_MOVERS = True
MOVER_WAIT_SEC = 2.5
# Real camera translation that counts as having got past something. A single
# 0.2s step measured 32-42px against a stationary noise ceiling of 8.8px
# (pose.py calibration), so this is comfortably inside the gap.
SLIP_PROGRESS_PX = 20.0


# The escape ladder's own constants. THESE WERE LOST for a few minutes on
# 2026-09-04 when _something_moved was deleted as a block — they sat between it
# and the next def, so the deletion took them with it and the ladder would have
# raised NameError on its first blockage. The undefined-name lint added the same
# day caught it immediately; that is what the lint is for.
SLIP_STRAFE = 0.30
SLIP_STRAFE_SEC = 0.25
SLIP_PUSH_SEC = 0.45
SLIP_JUMPS = 2


# Below this, the frame is a flat surface at close range and the blocker is
# GEOMETRY, not a mover. Measured over the archived wedge frames: 9, 10, 10, 11
# keypoints, against 744-1500 for every frame where the character was in open
# space. The gap is enormous and the classes never overlap.
#
# This is the discriminator the wall-vs-NPC test needed and did not have. That
# test was removed because "a wall does not move" was judged on SCENE CHANGE,
# and standing still already produces changes of 0.91-6.41 — the 2.0 threshold
# sat under the noise floor. Keypoint count is a different signal and does not
# have that problem: it does not care whether anything moved, only whether there
# is any structure in view.
#
# Why it is worth acting on: the escape ladder NEVER clears a geometry wedge.
# Every archived occurrence shows wait -> jump -> jump -> slip right -> slip
# left, each displacing 0.0px, then "nothing cleared it". It costs ~10s to
# confirm what the keypoint count says instantly.
#
# Conservative by construction: this only SKIPS the ladder when the frame is
# unambiguously featureless. An NPC blocking a passage leaves the passage
# visible and scores in the hundreds, so that case still runs the full ladder.
GEOMETRY_MAX_KEYPOINTS = 50
SKIP_LADDER_ON_GEOMETRY = True


# _something_moved() was DELETED 2026-09-04. It read MOVER_DELTA, which was
# defined nowhere in this module — an AST pass over all 215 non-vendored files
# found it was the ONLY genuine undefined name in the repo — so it would have
# raised NameError on its first call. It had zero callers.
#
# It is deleted rather than repaired because its subject is the wall-vs-NPC
# discriminator, which was removed deliberately: "a wall does not move" was
# judged on SCENE CHANGE, and standing perfectly still already produces changes
# of 0.91-6.41, so the threshold sat under the noise floor. Defining the missing
# constant would resurrect a measured-bad idea. The working discriminator is
# keypoint count, in SKIP_LADDER_ON_GEOMETRY.

def _looks_like_geometry(img):
    """True if the frame is a flat surface at close range, not a blocked view."""
    import places
    _, desc = places.keypoints(img)
    return (0 if desc is None else len(desc)) <= GEOMETRY_MAX_KEYPOINTS


def _slip_past(bearing, speed, dur, capture, read_heading, log=print):
    """Get past a blocker. Returns (best progress in px, how it cleared or None).

    Returns immediately when the view is featureless: that is geometry, and the
    ladder has never once cleared geometry (see GEOMETRY_MAX_KEYPOINTS).

    Progress is measured with pose.displacement(), NOT with raw view change.
    That distinction is the whole difficulty here: an NPC walking across the
    frame changes the picture a great deal while the character has not moved an
    inch, so a brightness delta reports success for exactly the situation this
    function exists to escape. Keypoint displacement with RANSAC rejects the
    mover as outliers and measures what the CAMERA did.
    """
    if SKIP_LADDER_ON_GEOMETRY:
        try:
            if _looks_like_geometry(capture()):
                log("      the view is featureless — this is geometry, not a "
                    "mover; skipping the escape ladder it has never cleared")
                return 0.0, None
        except Exception as e:
            log(f"      could not check for geometry ({e}); running the ladder")
    import walk_steps as ws
    import pose

    def moved_since(before_img):
        d = pose.displacement(before_img, capture())
        if d is None:
            # pose.displacement's own docstring: "None means 'unknown', NOT
            # 'the same'. A caller that treats an unmeasurable pair as
            # identical would accept exactly the frames it cannot see." This
            # caller did — and _slip_past then printed "displaced 0.0px" and
            # concluded "nothing cleared it — treating this as geometry, not an
            # NPC". A featureless or blown-out frame was recorded as a wall.
            log("      displacement UNMEASURABLE (too few keypoints) — "
                "NOT the same as 0px")
            return 0.0
        return d

    best = 0.0
    # 1. WAIT FIRST. Measured live 2026-09-02 in the narrow passage: jump
    # displaced 0.0px, jump again 0.0px, slip right 0.0px, slip left 0.0px —
    # then a 2.5s wait displaced 160.4px and the leg continued. When something
    # is genuinely filling a gap that is one character wide, there is nowhere to
    # go around it and nothing to jump over; the only thing that changes is the
    # NPC. It is also the cheapest and cannot wedge anything.
    ws.turn_to(bearing, log=lambda *a: None)
    before = capture()
    time.sleep(MOVER_WAIT_SEC)
    ws.walk_forward(abs(speed), dur)
    time.sleep(0.3)
    got = moved_since(before)
    best = max(best, got)
    log(f"      waited {MOVER_WAIT_SEC:.1f}s: displaced {got:.1f}px")
    if got >= SLIP_PROGRESS_PX:
        return best, "wait"

    # 2. Jump — no lateral movement, so nothing to undo.
    for k in range(SLIP_JUMPS):
        ws.turn_to(bearing, log=lambda *a: None)
        before = capture()
        import input_controller as ic
        ic.press("cross", hold_seconds=0.08)
        ws.walk_forward(abs(speed), SLIP_PUSH_SEC)
        time.sleep(0.3)
        got = moved_since(before)
        best = max(best, got)
        log(f"      jump {k + 1}: displaced {got:.1f}px")
        if got >= SLIP_PROGRESS_PX:
            return best, "jump"

    # 3. A small side-step, undone if it does not clear. LAST, because a
    # narrow passage punishes lateral movement — an earlier version crabbed
    # 0.55s and walked into the wall.
    for side, label in ((+1.0, "right"), (-1.0, "left")):
        ws.turn_to(bearing, log=lambda *a: None)
        before = capture()
        ws.walk_forward(0.0, SLIP_STRAFE_SEC, strafe=side * SLIP_STRAFE)
        time.sleep(0.25)
        ws.walk_forward(abs(speed), SLIP_PUSH_SEC)
        time.sleep(0.3)
        got = moved_since(before)
        best = max(best, got)
        log(f"      slip {label}: displaced {got:.1f}px")
        if got >= SLIP_PROGRESS_PX:
            return best, f"strafe_{label}"
        ws.walk_forward(0.0, SLIP_STRAFE_SEC, strafe=-side * SLIP_STRAFE)
        time.sleep(0.25)

    # Nothing worked: the wait did not clear it, and neither jumping nor
    # side-stepping moved the character at all. That is a WALL, not a mover.
    log("      nothing cleared it — treating this as geometry, not an NPC")
    return best, None


# Fraction of a recorded leg to actually walk when the destination is one the
# localiser can confirm. The recorded distance is right for the pose the HUMAN
# started from; the executor starts a little differently every run, so walking
# the full distance overshoots into furniture — measured, arrivals 6-10
# keypoints deep in a wall. Deliberately stopping short and letting
# recover_to_node() close the gap trades a guess for a measurement.
#
# Only applied where there is something to close the gap WITH: office_door has
# no appearance reference by design, and the table is confirmed by its prompt,
# so both walk their full recorded distance.
LEG_FRACTION = 0.6


def walk_link(m, a, b, capture=None, read_heading=None, log=print,
              fraction=1.0):
    """Walk one recorded leg. Returns a dict describing what happened."""
    import slow_traverse as st

    capture = capture or _default_capture
    read_heading = read_heading or _default_heading
    steps = m.steps_for(a, b)            # raises on an unwalkable leg
    if fraction != 1.0:
        steps = [dict(st, dur=st["dur"] * fraction) for st in steps]
        log(f"      walking {fraction:.0%} of the recorded distance, then "
            f"letting the localiser close the gap")

    if MERGE_STEPS:
        steps = merge_steps(steps)
    steps = _scaled(steps, leg_scale(a, b))
    if (a, b) in MERGE_STEPS_BY_LEG:
        steps = merge_steps(steps)
    # Aim the doorway traverse away from the door it currently clips. A no-op
    # unless DOORWAY_CLEARANCE_DEG is set AND this is the leg it names, so it
    # cannot quietly affect anything else.
    steps = _doorway_biased(a, b, steps)
    travelled, hazards, stalled, blockers = 0.0, [], 0, []
    for i, s in enumerate(steps, 1):
        bearing, dur, speed = s["bearing"], s["dur"], s.get("speed", 0.25)
        # None must not reach turn_to: `abs(err) <= None` raises, and it would
        # raise mid-leg on the live console rather than in a test.
        # A merged leg's single push inherits this turn's error for its whole
        # length, so it is aimed tightly. See MERGED_TURN_TOLERANCE.
        _tol = (MERGED_TURN_TOLERANCE if (a, b) in MERGE_STEPS_BY_LEG
                else LEG_TURN_TOLERANCE)
        turn_kw = {} if _tol is None else {"tolerance": _tol}
        got, turn_haz = st.turn_to(bearing, read_heading, capture, log=log,
                                   **turn_kw)
        hazards.extend(turn_haz)
        # Forward is left_y NEGATIVE (walk_steps.walk_forward:105). Getting this
        # sign wrong walks the whole route backwards.
        # ONE CONTINUOUS PUSH PER STEP. The recorded steps are all <= 0.80s and
        # were made as single pushes; replaying them as 0.25s chunks with a stop
        # between each makes the character re-accelerate every chunk and walk
        # the route SHORT — measured 2026-09-01, it ended two rooms adrift.
        spent, best, walk_haz = st.walk_leg(
            0.0, -abs(speed), dur, capture, read_heading,
            label=f"{a}->{b} step {i}/{len(steps)}", log=log, step_sec=dur)
        travelled += spent
        hazards.extend(walk_haz)
        log(f"      step {i}/{len(steps)} bearing {bearing:6.1f} "
            f"(got {'--' if got is None else f'{got:6.1f}'}) "
            f"{dur:.2f}s -> walked {spent:.2f}s, best change {best:.1f}")

        # SURVEY: the frame is already in hand, so noticing an unmapped place
        # costs one identify(). Never fatal — a survey failure must not end a
        # leg, since this is bookkeeping, not navigation.
        if SURVEY_WHILE_WALKING:
            try:
                import survey
                survey.consider(capture(), {"leg": f"{a}->{b}", "step": i},
                                log=log)
            except Exception as e:
                log(f"      survey skipped ({type(e).__name__})")
        # PROGRESS IS CHECKED HERE, not inside walk_leg. Each recorded step is
        # pushed in ONE go (that is what makes the distance right), and
        # slow_traverse's own STUCK detector needs two consecutive quiet CHUNKS
        # within a single call — with one chunk it can never fire. So a blocked
        # character was ground into a wall for three more steps in silence:
        # measured 2026-09-01, movement fell to 3.1, 3.0, 1.9 while the leg
        # reported every step as walked, and the frame at the end was a blank
        # dark wall.
        #
        # `best` is in GREY LEVELS (slow_traverse._change), which is what
        # STALL_CHANGE was calibrated on. Nothing in this block may put a
        # PIXEL quantity into it — see STALL_CHANGE_UNITS.
        escaped = False          # did the escape ladder actually clear it?
        if best < STALL_CHANGE and WAIT_OUT_MOVERS:
            # A WALL DOES NOT MOVE. The gap between the pool room and the
            # jukebox is a narrow passage — bar stools on one side, wall on the
            # other — and NPCs walk into it (user, 2026-09-02). That is why the
            # same leg blocked at 0.8s, at 3.2s and not at all across three
            # identical trials.
            #
            # Crabbing around is exactly wrong there: the passage is too narrow,
            # and the measured result was walking into the wall. Waiting costs
            # only time and cannot wedge the character.
            log(f"      step {i} blocked but the scene is MOVING — an NPC in "
                f"the passage, not a wall")
            best2, how = _slip_past(bearing, speed, dur, capture,
                                    read_heading, log)
            travelled += dur
            # DO NOT WRITE `best = max(best, best2)` HERE. That was the bug:
            # best2 is PIXELS and best is GREY LEVELS, and the result was then
            # tested against a grey-level STALL_CHANGE. See STALL_CHANGE_UNITS
            # for the measured populations and for what it cost.
            #
            # The question this branch has to answer — "did the ladder get the
            # character moving again?" — is a PIXEL question, and it already
            # has a pixel answer: `_slip_past` returns `how` non-None exactly
            # when some rung reached SLIP_PROGRESS_PX (20.0 px), which sits
            # inside pose.py's measured gap between stationary (max 8.80px) and
            # one real 0.2s step (min 32.25px). So take the ladder's own
            # verdict, in its own units, instead of laundering its magnitude
            # through a threshold that means something else.
            escaped = how is not None
            # `how`, not `escaped`, drives the wording. The obvious phrasing,
            # `'CLEARED by ' + how if escaped else ...`, reads fine and raises
            # TypeError on the live console the moment the two stop agreeing —
            # a diagnostic that kills the run it was added to explain. Found by
            # mutating `escaped` while writing the test for this fix.
            log(f"      escape ladder: "
                f"{'CLEARED by ' + how if how is not None else 'did NOT clear'}"
                f" (best {best2:.1f} PIXELS, against SLIP_PROGRESS_PX "
                f"{SLIP_PROGRESS_PX:.1f}px — NOT against STALL_CHANGE "
                f"{STALL_CHANGE:.1f}, which is {STALL_CHANGE_UNITS})")
            # RECORD THAT A BLOCKER WAS ACTUALLY MET. Without this, a run that
            # simply never met an NPC is indistinguishable from one whose
            # escape worked — and the escape would look proven by runs that
            # never exercised it.
            blockers.append({"step": i, "cleared_by": how,
                             "displaced_px": round(best2, 1)})
        if best < STALL_CHANGE and not escaped:
            # A LONG push that moved nothing is blocked on its own evidence.
            # Requiring two stalls in a row was right when every recorded step
            # was a separate push; after merging, a whole leg can be one 3s
            # push, and demanding a second one means never reporting a wall.
            stalled += 2 if dur >= LONG_PUSH_SEC else 1
            # `best` here is the GREY-LEVEL delta straight out of walk_leg. It
            # used to be max()'d with the ladder's PIXEL figure, so this line
            # could print a pixel count and call it a view change.
            log(f"      step {i} moved only {best:.1f} {STALL_CHANGE_UNITS} "
                f"(< {STALL_CHANGE}) over {dur:.2f}s — stall score {stalled}")
        else:
            stalled = 0
        if any(h.kind == "STUCK" for h in walk_haz) or stalled >= STALL_STEPS:
            hazards.append(_Blocked(spent, f"{a}->{b}: no progress for "
                                           f"{stalled} step(s) at step {i}"))
            log(f"      BLOCKED on step {i}; abandoning the rest of this leg "
                f"rather than pushing into whatever is in the way")
            break
    return {"a": a, "b": b, "steps": len(steps), "travelled": round(travelled, 2),
            "hazards": hazards, "blockers": blockers}


# Headings to try when hunting for the dealer prompt, relative to where the
# final leg leaves the camera. Measured 2026-09-01: after the last leg the
# character stood correctly at the table but faced ~76-90 and the prompt was
# absent (ink 0.019 against a 0.024 threshold); the SAME position at bearing 60
# read 0.0395 with the prompt up. Walking closer barely moved it (0.0187 ->
# 0.0216 over eight pushes) because the character was already against the
# table. The missing step was aiming, not travelling.
# A FULL CIRCLE, in 20-degree steps, ordered outward from where the leg left
# the camera so the common case still resolves in one or two turns.
#
# It was +/-30 and that was too narrow: the final leg lands the character
# facing anywhere from a wall to the room, and turning is the ONE recovery that
# does not cost the position the leg earned (both movement-based recoveries
# were measured and both lost it — see reach_table). Sweeping the whole circle
# costs a few seconds and can only help.
FACE_SWEEP = (0.0,) + tuple(
    float(off) for pair in zip(range(20, 181, 20), range(-20, -181, -20))
    for off in pair
)


def face_the_table(capture=None, read_heading=None, log=print):
    """Turn on the spot until the dealer's prompt is on screen.

    Closed-loop on the PROMPT, which is the only signal here that separates
    cleanly (ink 0.000-0.013 when absent against 0.027-0.047 when present).
    The recorded route ends with a fixed final camera heading, and that is not
    enough: where the character comes to rest varies by a few degrees' worth of
    position, and the prompt only shows over a narrow arc.
    """
    import compass
    import table_prompt as tp
    import walk_steps as ws

    capture = capture or _default_capture
    img = capture()
    if tp.at_table(img):
        return True, compass.read_bearing(img)

    base = compass.read_bearing(img)
    if base is None:
        log("      no compass reading, so there is no arc to sweep")
        return False, None

    best = (0.0, None)
    for off in FACE_SWEEP:
        target = (base + off) % 360.0
        ws.turn_to(target, log=lambda *a: None)
        time.sleep(0.45)
        img = capture()
        ink = tp.ink(img)
        if ink > best[0]:
            best = (ink, target)
        if tp.at_table(img):
            log(f"      facing {target:.0f} ({base:.0f}{off:+.0f}): prompt up "
                f"(ink {ink:.4f})")
            return True, target
    # Nothing triggered: leave the camera where the prompt was strongest rather
    # than wherever the sweep happened to stop, so a caller that retries starts
    # from the best-known aim.
    if best[1] is not None:
        ws.turn_to(best[1], log=lambda *a: None)
    log(f"      swept {len(FACE_SWEEP)} headings around {base:.0f}; best ink "
        f"{best[0]:.4f} at {best[1]}, prompt never appeared")
    return False, best[1]


# How far to crab sideways when something is standing on the last few feet of
# the route, and how many times to try. Measured 2026-09-01: six consecutive
# runs reached the table area and failed identically, and the frame showed an
# NPC ("Wanda Fuller [] Talk") filling the screen. She stands ON the approach,
# so no amount of re-aiming finds the prompt — the character has to step around
# her. go.py carries the same idea as WANDA_GOAROUNDS.
GOAROUND_STRAFE = 0.35
GOAROUND_SEC = 0.55
GOAROUNDS = 3


# A full turn, sampled. The dealer table is a fixed object, so the question
# "which way is it from here" has an answer at every position — unlike dead
# reckoning, which only works from the exact spot the recording started at.
HOME_SWEEP_STEP = 30.0
HOME_ADVANCE_SEC = 0.9
HOME_ROUNDS = 6
# Prompt ink this close to table_prompt's threshold means the table is right
# there and only the aim is off.
NEARLY_THERE_INK = 0.018


def _table_visibility(img):
    """How strongly the dealer table is in view: ORB matches against its refs."""
    import places
    refs = places.load_keypoints().get(GOAL, [])
    if not refs:
        return 0
    _, d = places.keypoints(img)
    if d is None:
        return 0
    return max(places.match_count(d, r) for r in refs)


def home_to_table(capture=None, read_heading=None, log=print):
    """Walk to the table by LOOKING for it, not by replaying a distance.

    The recorded last leg fails for a reason no amount of tuning fixes: it is a
    fixed distance on a fixed bearing, and the character never arrives at the
    previous node in quite the same spot, so it ends a metre out — sometimes
    facing a wall, sometimes with an NPC ("Wanda Fuller [] Talk") standing on
    the approach. Six consecutive runs failed there identically.

    So: turn all the way round sampling how much of the table is in view, face
    the best direction, walk a little, and repeat. Keypoint matching is what
    makes this possible — it recognises the table from angles and distances no
    global descriptor could, and it is unbothered by whoever is standing in
    front of it.
    """
    import compass
    import table_prompt as tp
    import walk_steps as ws

    capture = capture or _default_capture
    for rnd in range(HOME_ROUNDS):
        img = capture()
        if tp.at_table(img):
            log(f"      at the table after {rnd} homing round(s)")
            return True
        # ws.read_heading() RETRIES; compass.read_bearing() does not. A single
        # unreadable frame ended a homing run that was converging nicely
        # (keypoint matches 84 -> 125 -> 127, prompt ink 0.0 -> 0.0213 against a
        # 0.024 threshold) — the compass fails on roughly 6% of world frames and
        # more in bright rooms, so one raw read is not a decision.
        base = ws.read_heading()
        if base is None:
            log("      no compass reading after retries; cannot sweep")
            return False
        best = (-1, None)
        best_ink = 0.0
        n = int(360 / HOME_SWEEP_STEP)
        for k in range(n):
            target = (base + k * HOME_SWEEP_STEP) % 360.0
            ws.turn_to(target, log=lambda *a: None)
            time.sleep(0.35)
            img = capture()
            if tp.at_table(img):
                log(f"      prompt found while sweeping, at {target:.0f}")
                return True
            best_ink = max(best_ink, tp.ink(img))
            v = _table_visibility(img)
            if v > best[0]:
                best = (v, target)
        if best[1] is None or best[0] <= 0:
            log("      the table is not visible from anywhere on this circle")
            return False
        log(f"      round {rnd + 1}: table strongest at {best[1]:.0f} "
            f"({best[0]} keypoint matches, prompt ink {best_ink:.4f}) — advancing")
        ws.turn_to(best[1], log=lambda *a: None)
        time.sleep(0.3)
        ws.walk_forward(0.22, HOME_ADVANCE_SEC)
        time.sleep(0.4)
        # CLOSE COUNTS. The prompt shows over a narrow arc, so once its ink is
        # within reach of the threshold the missing piece is aim, not distance —
        # measured, a run sat at 0.0213 against 0.024 and one fine sweep would
        # have tipped it over.
        if best_ink >= NEARLY_THERE_INK:
            ok, _ = face_the_table(capture, read_heading, log=log)
            if ok:
                log(f"      fine aim found the prompt after round {rnd + 1}")
                return True
    img = capture()
    return bool(tp.at_table(img))


# The final leg is walked in SMALL STEPS with a check after each, rather than as
# one recorded push. Measured 2026-09-01: 11 of 12 end-to-end failures were this
# one 4.2s leg, while the four legs before it landed every time. The recorded
# distance is right for the spot the HUMAN started it from; the executor arrives
# at the jukebox a little differently each run, so a fixed push ends a metre out
# — sometimes at a wall, sometimes with an NPC on the approach.
#
# at_table() is the signal to close the loop on: it demands contrast AND prompt
# ink AND stroke-shape together, and measured cleanly (absent 0.000-0.014,
# present 0.027-0.047) where every other candidate signal did not.
APPROACH_STEP_SEC = 0.4
APPROACH_OVERSHOOT = 1.6      # of the recorded duration, then give up
APPROACH_AIM_EVERY = 3        # steps between aim sweeps


def approach_goal(steps, capture=None, read_heading=None, log=print):
    """Walk the last leg incrementally, stopping the moment the prompt appears.

    Returns True as soon as at_table() is satisfied. Never walks more than
    APPROACH_OVERSHOOT of the recorded distance, so a leg aimed at a wall costs
    a few seconds rather than grinding.
    """
    import table_prompt as tp
    import walk_steps as ws

    capture = capture or _default_capture
    total = sum(s["dur"] for s in steps)
    budget = total * APPROACH_OVERSHOOT
    bearing = steps[-1]["bearing"]
    speed = steps[-1].get("speed", 0.22)

    if tp.at_table(capture()):
        return True
    spent, since_aim = 0.0, 0
    while spent < budget:
        ws.turn_to(bearing, log=lambda *a: None)
        ws.walk_forward(abs(speed), APPROACH_STEP_SEC)
        time.sleep(0.3)
        spent += APPROACH_STEP_SEC
        since_aim += 1
        img = capture()
        if tp.at_table(img):
            log(f"      prompt appeared after {spent:.1f}s of stepping")
            return True
        if since_aim >= APPROACH_AIM_EVERY:
            since_aim = 0
            ok, _ = face_the_table(capture, read_heading, log=log)
            if ok:
                log(f"      prompt found by aiming after {spent:.1f}s")
                return True
    log(f"      stepped {spent:.1f}s of a {budget:.1f}s budget without finding "
        f"the prompt")
    return False


def reach_table(capture=None, read_heading=None, log=print):
    """Aim for the dealer prompt, stepping around whatever is in the way.

    The last leg puts the character AT the table; what varies is the aim and
    whether an NPC is standing on the spot. So: sweep for the prompt, and if it
    is nowhere on the arc, crab sideways and sweep again.
    """
    import walk_steps as ws

    capture = capture or _default_capture
    ok, aim = face_the_table(capture, read_heading, log=log)
    if ok:
        return True
    # NEITHER RECOVERY BELOW IS ENABLED, and both are kept only because the
    # measurements that killed them are worth not repeating:
    #
    #   home_to_table()  — sweep for the table by keypoint count and walk at it.
    #     Measured: it WANDERS. Across six rounds the "strongest" heading jumped
    #     322 -> 350 -> 17 -> 319 -> 354 -> 22 while prompt ink FELL from 0.0224
    #     to 0.0093, because at that distance the table scores 109-129 matches
    #     and pure negatives already reach 114. It is reading noise.
    #
    #   crabbing (below) — step sideways past whatever is in the way.
    #     Measured: it walked the character off the spot and into a wall,
    #     ending with no table in view at all (ink 0.0).
    #
    # Both MOVE the character, and moving on a bad signal is worse than standing
    # still: the aim sweep alone at least leaves the position that the leg
    # earned. Re-enable either only with a signal that separates.
    return False
    for i in range(GOAROUNDS):
        # Alternate sides, widening: whatever is in the way could be on either.
        strafe = GOAROUND_STRAFE * (1 if i % 2 == 0 else -1) * (1 + i // 2)
        log(f"      prompt not on the arc — stepping around "
            f"({'right' if strafe > 0 else 'left'}, attempt {i + 1}/{GOAROUNDS})")
        ws.walk_forward(0.0, GOAROUND_SEC, strafe=strafe)
        time.sleep(0.35)
        ws.walk_forward(0.20, 0.35)          # and forward a little
        time.sleep(0.35)
        ok, aim = face_the_table(capture, read_heading, log=log)
        if ok:
            log(f"      reached the prompt after {i + 1} go-around(s)")
            return True
    return False


# A frozen stream produces IDENTICAL frames, and identical frames satisfy
# almost every check in this module: nothing moves, so nothing looks blocked;
# nothing changes, so a confirmation that passed once passes forever. Measured
# 2026-09-02, follow() reported arrived=True having walked a whole route into a
# picture that had not updated in minutes (chiaki's decode queue had overflowed:
# "pending_overflow_evict ... overflow queue full").
#
# Two captures this far apart on a LIVE stream always differ — idle in-world
# noise alone measures 14-20, and even a static menu measures ~3.
FROZEN_DELTA = 0.35


def stream_is_live(capture=None, gap=1.2, log=None):
    """False if two captures a moment apart are pixel-identical.

    `log` only redirects the fail-open warning; it DEFAULTS TO print, so no
    existing caller loses it. It exists because this is now called twice per
    trial by consecutive_arrivals, and the offline tests hand it a stub capture
    that cannot be converted — 66 lines of fail-open warning drowning 19 lines
    of PASS/FAIL is its own way of hiding a signal.
    """
    import numpy as np

    log = log or print
    capture = capture or _default_capture
    try:
        a = np.asarray(capture().convert("L"), dtype=float)
        time.sleep(gap)
        b = np.asarray(capture().convert("L"), dtype=float)
    except Exception as e:
        # Failing OPEN is deliberate — do not block a run on a bad grab. But
        # this gate exists because a frozen stream once made follow() report
        # arrived=True having walked a whole route into a stale picture, and
        # a silent fail-open logs identically to a verified-live stream.
        log(f"  [stream] liveness check FAILED ({type(e).__name__}: {e}) — "
            f"assuming live and walking anyway; this is NOT proof the "
            f"picture updates")
        return True
    return float(np.abs(a - b).mean()) > FROZEN_DELTA


# A CALLER THAT HAS JUST RESET KNOWS WHERE THE CHARACTER IS. WE WERE PAYING
# ~24 SECONDS A TRIAL TO REDISCOVER IT, AND FAILING.
#
# reset_environment() lands the character on SPAWN = office_corridor, which is
# in UNSEEDED — it has no appearance reference BY DESIGN (CLAUDE.md 7: seeding
# office_door from a dark frame instantly created false positives). So locate()
# cannot name it, ever. go_to_node_verified therefore read `start is None`,
# concluded "lost", spent a 13.9s relocalise sweep that had nothing to find, and
# then RESET A SECOND TIME to get back to the place it was already standing.
#
# Measured 2026-09-05 across three complete archived runs — streak2.log 10/10
# trials, failframes.log 8/8, newleg.log 8/8, **26 of 26** — every one opens
# with "not at portrait_room and cannot say where this is — reloading to a known
# start", immediately after the harness's own reset. Cost, from
# overnight/profile.json's own numbers: sweep 13.9s (its `turn_to 6 calls
# 11.41s` IS this sweep) + reset 8.96s + sleep 1.2s = **~24s per trial**, in
# every harness shaped `reset; go_to_node_verified(target)`.
#
# The sweep is NOT useless in general and is not being removed: **11 of 82
# sweeps re-localised (13.4%)**, each saving a reset. (This first read "22 of
# 85 (26%)", which was a DOUBLE COUNT — one successful sweep prints TWO lines,
# `re-localised by turning N deg:` from _look_around_for_a_node and
# `re-localised at X by turning; routing from there` from the caller, so a grep
# for "re-localised" counts every success twice. The corrected count is over
# all six archived logs that contain the string: overnight/{streak2,failframes,
# newleg,streak}.log and overnight/phase1/{run,step3}.log — 71 sweeps that
# reloaded plus 11 that re-localised. 85 was the ESCAPE-LADDER count from a
# different analysis and does not belong here.) It is useless only where the
# answer is already known — at the spawn, straight after a reset.
#
# THIS ASSERTS NOTHING NEW. go_to_node_verified already sets `start = SPAWN`
# after its OWN reset, unverified, on the same grounds (CLAUDE.md 8d: the spawn
# bearing reads 86.9/87/87 on every reset). All that changes is who paid for the
# reset. The hint is consumed on the FIRST attempt only, so a second attempt —
# where the character HAS moved — behaves exactly as before.
#
# UNMEASURED SIDE EFFECT, stated rather than hidden: the route now starts ~24s
# earlier after the load, so the NPCs in the passage have wandered ~24s less.
# That is a real mechanism by which arrival could move, in either direction.
# Flip this to False for the control arm; the A/B is cheap precisely because the
# True arm is 24s a trial faster.
TRUST_RESET_SPAWN = True


def go_to_node_verified(m, node, capture=None, read_heading=None, log=print,
                        attempts=3, shots=None, start_hint=None):
    """Stand at `node` and PROVE it, or report failure. Returns bool.

    `start_hint` is where the CALLER knows the character is standing, and is
    believed only on the first attempt and only when locate() cannot answer.
    Pass SPAWN after a reset_environment() that returned normally; see
    TRUST_RESET_SPAWN.

    follow() deliberately treats an unrecognised node as advisory and carries on
    — the goal's own prompt is the authoritative check, and stopping on every
    abstention ended runs at node 1 of 5. The cost is that follow()'s "reached"
    is a ROUTING CLAIM, not evidence of position: on 2026-09-02 it reported
    reaching bar_jukebox while the character was in a stairwell, and a scouting
    pass then photographed the wrong room entirely.

    So anything that needs to actually BE somewhere — calibration, scouting,
    recording a leg — must use this instead, which believes only locate().
    """
    capture = capture or _default_capture
    for i in range(attempts):
        # WHICH attempt. Three reset-and-rewalk cycles used to produce three
        # indistinguishable blocks of output, so a log could not be read back
        # to see whether a node fell on the first try or the third — which is
        # exactly the per-attempt rate OPEN-4 needs.
        log(f"  attempt {i + 1}/{attempts} at {node}")
        # SPEND THE HINT HERE, BEFORE ANYTHING CAN DECIDE NOT TO USE IT.
        #
        # It used to be consumed inside the `start is None` branch below, which
        # meant a hint survived any attempt that DID locate a node — so attempt
        # 1 could walk a leg from a located start and attempt 2 could then use
        # "the caller just reset onto SPAWN" one leg later. That is the stale
        # cached handle from CLAUDE.md 10's catalogue, and it is exactly what
        # the comment below already promised did not happen. Found 2026-09-05:
        # a mutant that dropped the `start is None` guard passed the whole
        # suite, which is what sent someone looking at this line.
        hint, start_hint = start_hint, None
        where, detail = locate(m, capture=capture, log=log)
        if where == node:
            log(f"  verified at {node} ({detail})")
            return True
        start = where
        # KNOWN BUT UNREACHABLE IS AS STUCK AS LOST, AND USED TO BE INVISIBLE.
        #
        # Legs are ONE-WAY by design (worldmap.connect defaults to one_way), so
        # once the character is PAST a node there is no edge back to it. When
        # that happened, locate() answered confidently, the reset was skipped
        # because position was "known", follow() found no route and returned
        # without walking, and locate() said the same thing on the next
        # attempt. Three attempts of doing nothing, and nothing in the log said
        # so — the run just failed.
        #
        # Measured 2026-09-04: a re-record run reached its start node 0 of 20
        # times while the character stood at bar_jukebox, one node PAST the
        # bar_pool_room it was trying to reach. route_reason() called it
        # "unreachable" the whole time and nobody asked.
        #
        # A reset is the only way back, so treat unreachable exactly like lost.
        if start is not None and start != node:
            why = m.route_reason(start, node) if hasattr(m, "route_reason") else "ok"
            if why not in ("ok", "same"):
                log(f"  at {start} but {node} is {why} from here (legs are "
                    f"one-way) — reloading rather than walking a route that "
                    f"does not exist")
                start = None
        # BELIEVE THE CALLER BEFORE SPENDING A SWEEP AND A RESET ON A PLACE THE
        # LOCALISER IS DESIGNED NOT TO RECOGNISE. See TRUST_RESET_SPAWN for the
        # 26-of-26 measurement. `start is None` first, deliberately: the hint is
        # the caller's CLAIM and locate() is EVIDENCE, so a named, routable node
        # always wins. The hint was already spent at the top of the loop, so
        # only attempt 1 can reach this at all.
        if start is None and hint is not None:
            why = (m.route_reason(hint, node) if hasattr(m, "route_reason")
                   else "ok")
            if why == "ok":
                log(f"  locate() cannot name {hint} (it has no appearance "
                    f"reference by design) but the caller reset onto it — "
                    f"routing from there instead of sweeping and reloading")
                start = hint
            else:
                log(f"  caller's start hint {hint!r} is {why} for {node} — "
                    f"ignoring it and recovering normally")
        if start is None:
            # TRY A LOCAL SEARCH BEFORE THROWING THE RUN AWAY.
            #
            # Resetting rewinds to the spawn and re-walks the ENTIRE route to
            # get back here, discarding every node already verified. At the
            # measured ~55% arrival per node that is the dominant cost of a
            # trial: a 10-trial streak run took over 30 minutes and most of it
            # was re-walking ground that had already been walked correctly.
            #
            # recover_to_node() is a bounded fan around the current position —
            # 5 bearings x 3 steps of 0.5s, so ~10 seconds against a reset's
            # ~40-60. It is worth trying because the localiser is NOT the weak
            # part: measured leave-one-out, a node scores 249-698 matches with
            # 2.6-5.3x ratio when the character is genuinely standing at it. A
            # miss is usually a metre, not a room.
            #
            # Bounded and self-limiting: if the fan does not find the node, the
            # reset still happens, so this can cost time but cannot lose a run.
            # Cheapest recovery first: just look around. Turning cannot move
            # the character, so this risks nothing but a few seconds, and a
            # frame full of blank wall is a known cause of a false "lost".
            if RELOCALISE_BY_TURNING:
                found = _look_around_for_a_node(m, capture, log=log)
                if found is not None and found[0] == node:
                    log(f"  re-localised at {node} by turning — no reset needed")
                    return True
                if found is not None:
                    start = found[0]
                    log(f"  re-localised at {start} by turning; routing from there")
                    follow(m, start, node, capture, read_heading, log=log,
                           shots=shots)
                    continue

            if LOCAL_RECOVERY_FIRST:
                log(f"  not at {node} ({detail}) — trying a local search "
                    f"before resetting")
                try:
                    if recover_to_node(m, node, capture=capture,
                                       read_heading=read_heading, log=log):
                        log(f"  recovered locally to {node} — no reset needed")
                        return True
                except Exception as e:
                    log(f"  local search failed ({type(e).__name__}: {e})")
            import reset_env
            log(f"  not at {node} and cannot say where this is ({detail}) — "
                f"reloading to a known start")
            try:
                reset_env.reset_environment(log=log)
            except Exception as e:
                log(f"  reset failed ({type(e).__name__}: {e})")
                return False
            time.sleep(1.2)
            start = SPAWN
        # shots= ON BOTH CALL SITES. It was added at the reset path above and
        # missed here, which is the ORDINARY path — so failure frames kept
        # coming from `before` (the previous node's arrival) instead of
        # follow()'s own at_<node>.jpg, taken before the recovery fan.
        #
        # The consequence was not one wrong label: since `before` is always the
        # previous node, a failure at route index >= 1 classified as `regressed`
        # every time and index 0 as `wedged` every time. failures_by_kind was a
        # re-encoding of WHICH node failed, carrying nothing about what happened.
        follow(m, start, node, capture, read_heading, log=log, shots=shots)
    where, detail = locate(m, capture=capture, log=log)
    log(f"  could not verify {node} after {attempts} attempt(s); here is "
        f"{where!r} ({detail})")
    return where == node


# When a leg lands short or wide, hunt for the destination nearby rather than
# walking the next leg from an unknown spot. Bounded: a recovery, not a search
# of the building.
# TRIMMED 2026-09-02. Watching the stream, the old fan (7 bearings x 4 steps out
# AND back = up to 56 pushes) reads as the character wandering and backtracking
# for a long time in the narrow passage — the user saw it and said so. Most
# recoveries that work, work on the first or second bearing; the long tail
# mostly walks the character around and costs iteration time.
RECOVER_FAN = (0.0, 40.0, -40.0, 80.0, -80.0)
RECOVER_STEP_SEC = 0.5
# Reach = RECOVER_STEPS * RECOVER_STEP_SEC. At 2 steps the fan reached 1.0s,
# while the legs it has to rescue are 2.0-4.1s long — so a leg that landed more
# than a second out was simply beyond it. Measured 2026-09-02, recovery lifted
# mean verified depth from 2.4 to 3.0 of 5 even at that reach, and the failures
# that remained were arrivals 6-10 keypoints deep in a wall, i.e. far out.
RECOVER_STEPS = 3
RECOVER_MISSED = True
# OFF. A/B tested 2026-09-02, n=3 per arm and perfectly consistent within
# each: full legs reached verified depth [3, 3, 3], legs walked at 60%
# reached [2, 2, 2]. The mechanism is visible in the frames — with short
# legs the arrival at bar_jukebox still identifies as PORTRAIT_ROOM, i.e.
# the character never left the first room, and the recovery fan then
# wanders locally instead of covering the missing distance.
#
# The idea was that walking full distance overshoots into furniture and a
# localiser-guided search should close the gap. The search is real and
# helps (see RECOVER_MISSED), but it cannot substitute for distance.
SHORT_WALK = False

# WALK THE RELIABLE LEGS FASTER, to buy experiment throughput.
#
# Measured per-leg walking time against measured per-leg arrival:
#
#     office_door -> portrait_room     11.04s   48% of the route   20/20 arrival
#     office_corridor -> office_door    5.13s   22%                (no reference)
#     portrait_room -> bar_pool_room    1.97s    9%                14/21
#     bar_pool_room -> bar_jukebox      0.80s    3%                 6/15
#
# **70% of the walking is in the two office legs, and the biggest single chunk
# is the one that has never failed.** The legs that actually fail total 2.77s.
# So the time is being spent almost entirely where there is no problem, and at
# 338s per trial that time is the binding constraint on learning.
#
# Scaling holds speed x duration constant, which preserves distance IF velocity
# is roughly proportional to stick magnitude. That is an ASSUMPTION and the
# reason this ships at 1.0: turning is badly non-linear over its range
# (turn_curve: 74.8 deg/s at 0.90 against 197.7 at 1.00), and walking has never
# been characterised the same way. If walking is also non-linear, a scaled leg
# covers the wrong distance and the leg will miss.
#
# Only ever raise this for legs that are MEASURED reliable — a faster unreliable
# leg is just a faster failure. And measure BOTH arrival and seconds: the whole
# point is time, so a flat arrival with less time is a WIN, not a null.
LEG_SPEED_SCALE = 1.0
# MEASURED 2026-09-04 in the office corridor, displacement per 0.40s push
# (pose.displacement, RANSAC on keypoints), 3 samples per magnitude:
#
#     mag    samples                    median   spread
#     0.25   [23.1, 38.1, 34.6]          34.6      15
#     0.35   [43.0, 48.3, 58.1]          48.3      15
#     0.45   [58.8, 73.6, 70.6]          70.6      15
#     0.60   [57.4, 84.7, 71.2]          71.2      27
#     0.75   [53.1, 106.0, 177.2]       106.0     124   <- collapsing
#     0.85   [591.1, None, 114.8]       352.9     476   <- chaotic
#     1.00   [107.8, 181.2, 113.4]      113.4      73
#
# TWO findings, and the second is the one that sets this constant.
#
# 1. Walking IS roughly linear in stick magnitude up to ~0.75 (ratio to linear
#    0.86-1.13). That VALIDATES the speed x duration scaling, which had been an
#    assumption borrowed from nothing.
#
# 2. REPEATABILITY COLLAPSES ABOVE 0.60. Spread is a steady ~15px through 0.45,
#    then 27, then 124, then 476 with one push the localiser could not measure
#    at all. The median stays fine; the variance does not.
#
# Variance is what makes a dead-reckoned leg miss, so the cap is set by (2), not
# by (1). Same shape as the turn-magnitude result: at full stick the median was
# reasonable and the SPREAD was 4.8x worse.
#
# The previous value of 0.85 was borrowed from turn_curve.USABLE_MAX — a
# constant about the RIGHT stick (camera rotation). It is a different stick and
# was never evidence for this one.
LEG_SPEED_MAX = 0.60

# PER-LEG overrides. Speed belongs on the legs that are measured reliable, and
# the office legs are the obvious candidates for a second reason beyond their
# arrival rate: they are CORRIDORS. Walls on both sides constrain the path, so
# a distance error has far less room to become a position error, and neither
# has the furniture or the NPCs that the bar does.
#
#     office_corridor -> office_door    5.13s   unlit corridor, no reference
#     office_door -> portrait_room     11.04s   20/20 arrival
#
# Together 16.17s of the route's 23.00s, and neither has ever been the failure.
# The corridor leg cannot be verified directly (no reference by design), but it
# does not need to be: if speeding it up breaks anything, arrival at
# portrait_room drops off 20/20 immediately, which is a very sensitive detector.
#
# Empty = every leg uses LEG_SPEED_SCALE. Populate it to speed up only the
# legs that have earned it.
# DOORWAY CLEARANCE. The stairs leg passes through a doorway whose open door
# swings toward the camera, and the character walks nearer the door than the
# jamb: measured off a labelled capture on 2026-09-05, the gap is ~455px wide
# with 180px of clearance to the DOOR and 275px to the jamb, so the character is
# aimed ~47-95px (2.5-5.0 deg) left of the gap's centre. The user observed the
# bump directly before any of this was measured: "you slightly bump into the
# door and that causes small amounts of drift which compounds."
#
# The drift is corroborated in the OPEN-4 run: pre-alignment dx at portrait_room
# was +49.4 +49.7 +51.0 +86.3 +133.9 +165.9 and one -48.8 — 6 of 7 positive,
# median +51px. A bias, with a spread far larger than the bias, which is why the
# fix is CLEARANCE rather than a better aim: no achievable aim survives +-100px
# of variance through a gap this tight.
#
# WHY IT IS A BEARING OFFSET AND NOT A STRAFE. slow_traverse.TURN_TOLERANCE is
# 4.0 deg, so any correction under that is a NO-OP — turn_to compares the error,
# finds it inside tolerance and sends nothing. A 2.5 deg fix is unexpressible.
# 4.0 is the smallest offset the executor can actually perform, and it happens
# to sit in the measured range. That is luck, not design, and it is the reason
# this is worth trying before the larger left-stick work (OPEN-20).
#
# APPLIED ONLY TO THE DOORWAY TRAVERSE, steps 9-14: the sustained north run at
# bearing ~358 and speed 0.43. The final step is left alone.
#
# THE RISK, STATED: this leg arrives 20/20 (n=20). Over the 2.38 walk-units
# those steps cover, +4 deg is ~0.17 units of endpoint shift, so the leg ends
# right of where it did. align_lateral DOES work at portrait_room (dx +0.9 to
# +26.9, corrected in 7 of 10 OPEN-4 trials) unlike at bar_pool_room, so it
# should absorb that — but if arrival drops, this is the first thing to revert.
# Baseline to beat: 10/10 arrivals, median 52.9s (overnight/primitive_open4_baseline.json).
DOORWAY_CLEARANCE_DEG = 0.0
DOORWAY_STEPS = ("office_door", "portrait_room", range(9, 15))


def _doorway_biased(a, b, steps):
    """The doorway traverse aimed away from the door it currently clips."""
    if not DOORWAY_CLEARANCE_DEG:
        return steps
    fa, fb, span = DOORWAY_STEPS
    if (a, b) != (fa, fb):
        return steps
    out = []
    for i, st in enumerate(steps):
        if i in span:
            out.append({**st,
                        "bearing": (st["bearing"] + DOORWAY_CLEARANCE_DEG) % 360.0})
        else:
            out.append(st)
    return out


LEG_SPEED_BY_LEG = {
    # LEG 1 AT THE CAP. office_corridor -> office_door is a straight corridor —
    # all seven recorded steps sit at bearing 270.1-270.4, a spread of 0.33 deg —
    # and it arrives 20/20 (n=20, CLAUDE.md 8b). At 3.0 every step reaches
    # LEG_SPEED_MAX and the leg runs 5.13s -> 1.95s, saving 3.18s a trial with
    # distance preserved EXACTLY (1.168 walk-units both ways, by construction:
    # _scaled multiplies speed by k and divides dur by the same k).
    #
    # THIS IS NOT A NEW EXPERIMENT. GRAVEYARD measured office legs at 3x, capped
    # at 0.60, and got 8/8 ARRIVED IN BOTH ARMS — the safety question is answered
    # and speed x duration scaling was verified live. It was left off because the
    # median only moved ~5% and the mean was worse on ONE 185s outlier at n=8,
    # which is noise by this project's own standard (10.3: n=3 has power 0.00).
    #
    # Turned on 2026-09-05 at the user's direction, for a reason the original
    # A/B did not weigh: a few seconds compounds across every future run. At ten
    # trials an arm and six queued A/Bs, 3.18s is over an hour of console time.
    # The saving is in WALL CLOCK, not arrival — do not expect it to move a rate.
    #
    # The stairs leg (office_door -> portrait_room) is deliberately NOT here.
    ("office_corridor", "office_door"): 3.0,
}

# Record rich-but-unrecognised views seen while walking, as map candidates.
#
# The motivating class is OVERSHOT: a detailed frame (744-1500 keypoints) that
# identify() cannot name, because the character has walked somewhere the map
# has no reference for. The run is then blind — it cannot route back, so it
# resets and re-walks everything. Those places can only be mapped if something
# looks at them, and the route walks through them several times a trial while
# throwing every frame away.
#
# HOW OFTEN THAT HAPPENS IS NOT KNOWN. This comment said "a quarter of route
# failures", which was 2 of the 8 frames in overnight/failframes_prerecovery/ —
# frames captured after the recovery fan, so they describe the fan and not the
# leg, and 2/8 carries a 95% Wilson interval of [0.07, 0.59] even if they were
# admissible. No live run has ever recorded a class census. Re-derive the
# distribution from leg-end frames before this flag is turned on: it is the
# only number that says whether surveying is worth anything.
#
# Affordable only since tesserocr: one identify() per sample is 43ms, and the
# frames are already captured for the view-change measurement so they are free.
# A bearing read alone used to cost 261ms and there was no budget for this.
#
# It only ever writes candidates to disk. Nothing is added to the map — a place
# seeded from a bad frame poisons the localiser permanently.
SURVEY_WHILE_WALKING = False


# Let a leg's own measured record decide its speed, instead of a hand-kept
# list. Explicit overrides still win, so an experiment can force either arm.
SPEED_FROM_RELIABILITY = False


def leg_scale(a, b):
    """The speed scale for one leg.

    Order: an explicit override, then the leg's EARNED scale if reliability is
    driving speed, then the global default. A leg only goes fast once it has
    proven it deserves to, and slows itself again if it starts failing — which
    is the point of deriving this rather than maintaining a list that goes
    stale exactly when behaviour changes.
    """
    if (a, b) in LEG_SPEED_BY_LEG:
        return LEG_SPEED_BY_LEG[(a, b)]
    if SPEED_FROM_RELIABILITY:
        try:
            import leg_reliability
            return leg_reliability.scale_for(a, b)
        except Exception:
            return LEG_SPEED_SCALE          # never let bookkeeping stop a walk
    return LEG_SPEED_SCALE


def _scaled(steps, scale=None):
    """Steps walked faster, preserving speed x duration (i.e. distance)."""
    scale = LEG_SPEED_SCALE if scale is None else scale
    if scale == 1.0:
        return steps
    out = []
    for st in steps:
        sp = st.get("speed", 0.25)
        k = min(scale, LEG_SPEED_MAX / sp) if sp > 0 else 1.0
        if k <= 1.0:
            out.append(st)
            continue
        out.append({**st, "speed": sp * k, "dur": st["dur"] / k})
    return out


# Search locally before resetting to the spawn when position is unknown.
#
# A reset costs a full route re-walk (~40-60s) and discards every node already
# verified; a bounded local fan costs ~10s. Measured 2026-09-03: arrival is
# ~55% per node, so resets dominate a trial's cost — a 10-trial streak run ran
# over 30 minutes, mostly re-walking ground already walked correctly.
#
# A flag, not a fix: it must be A/B'd on arrival rate like everything else here.
LOCAL_RECOVERY_FIRST = False

# How close the heading must be before a leg step stops turning.
#
# THE PROBLEM THIS EXISTS FOR, measured 2026-09-03 from a live run's own log.
# slow_traverse's default is 4.0 degrees. The leg portrait_room -> bar_pool_room
# commands bearings 286.6, 292.2, 285.6, 287.6 — a total curve of 6.6 degrees —
# so from a character sitting at 289.1 EVERY step is inside tolerance and
# turn_to returns without turning. The log still reads
#
#     step 2/4 bearing  292.2 (got  289.1) 0.79s
#
# which looks exactly like a turn that happened. Two attempts at that same leg
# in one run:
#
#     failed:    got 289.1  289.1  289.1  289.1   (never turned at all)
#     succeeded: got 286.2  290.1  288.1  288.1
#
# So the recorded curve is discarded and the leg is walked STRAIGHT at whatever
# heading the character arrived with, anywhere in a +-4 degree band. The user
# watching the stream described exactly this: the same leg sometimes stops short
# and leaves the bar, and sometimes walks far enough.
#
# It is worst on the leg that fails most: bar_pool_room -> bar_jukebox changes
# by at most 1.3 degrees step to step, so after the initial turn NOTHING steers
# it for the rest of the leg.
#
# None = keep slow_traverse's default (the behaviour every existing measurement
# was taken under). A number tightens it. NOT changed by default: this project
# has reversed two well-motivated navigation changes on measurement, so it ships
# as a flag to be A/B'd on VERIFIED positions, not as a fix.
LEG_TURN_TOLERANCE = None


def recover_to_node(m, node, capture=None, read_heading=None, log=print):
    """Try to reach `node` from just-missed. True if the localiser agrees.

    Worth doing because the localiser is NOT the weak part. Measured over 11
    routed passes, `portrait_room` was recognised with ~1500 keypoints every
    single time, and the other rooms score 400-1500 whenever the character is
    genuinely standing in them. What loses runs is walking blind past a node
    that was missed by a metre.

    Deliberately small — seven bearings, at most two 0.5s steps each, walking
    back after every failed probe. Wandering is what turned the earlier
    movement-based recoveries into new failures.
    """
    import walk_steps as ws

    capture = capture or _default_capture
    here, _ = locate(m, capture=capture, log=lambda *a: None)
    if here == node:
        return True
    base = ws.read_heading()
    if base is None:
        log("      no compass; cannot run a recovery fan")
        return False
    for off in RECOVER_FAN:
        b = (base + off) % 360.0
        taken = 0
        for _ in range(RECOVER_STEPS):
            ws.turn_to(b, log=lambda *a: None)
            ws.walk_forward(0.22, RECOVER_STEP_SEC)
            time.sleep(0.35)
            taken += 1
            here, detail = locate(m, capture=capture, log=lambda *a: None)
            if here == node:
                log(f"      recovered {node} at {b:.0f} after {taken} step(s)")
                return True
        for _ in range(taken):          # walk back; do not accumulate drift
            ws.turn_to((b + 180.0) % 360.0, log=lambda *a: None)
            ws.walk_forward(0.22, RECOVER_STEP_SEC)
            time.sleep(0.3)
    log(f"      recovery fan did not find {node}")
    return False


# Align the character laterally to a node's RECORDED pose before walking the leg
# that was recorded from it. This is the fix for the mismatch that has cost every
# run: places.identify() answers "which ROOM", the rooms are large, and a
# dead-reckoned leg assumes a POINT. Measured 2026-09-02, the correction takes
# ~200-360px of lateral error down to 7-27px, 3 of 3.
#
# The reference is the node's route_*.jpg — the frame from the recorded walk,
# i.e. exactly the pose the outgoing leg was recorded from.
ALIGN_AT_NODES = True


# WHICH POSE SHOULD align_at_node PULL THE CHARACTER ONTO?
#
# "human"  the frame the outgoing LEG was recorded from. Coherent with the leg,
#          but the bot often cannot physically reach it — at bar_pool_room it is
#          against the stools and four corrections moved dx by nothing
#          (-136, -179, -156, -158).
# "bot"    the bot's own verified arrival frame, captured 2026-09-03. Reachable
#          by construction, so alignment converges (51.5 -> 11.4px measured).
#
# THE TRAP, and it is live right now: places/<node>/route_*.jpg was OVERWRITTEN
# with the bot frames on 2026-09-03, while world_map.json still holds the
# HUMAN's legs. Measured separation between the two poses:
#
#     portrait_room  dx  -71.1  dy +65.7   (heading differs 0.74 deg)
#     bar_pool_room  dx -212.2  dy -87.1   (heading differs 6.87 deg)
#     bar_jukebox    dx -135.5  dy -85.4   (heading differs 1.81 deg)
#
# The dy terms cannot come from yaw, so these are genuinely different places.
# So alignment now pulls onto pose A and then walks a leg recorded from pose B,
# every run — a SYSTEMATIC error larger than any correction being contemplated.
#
# Neither option is right on its own. The coherent end state is bot references
# WITH legs re-recorded from those same poses. Until that exists this is a flag,
# defaulting to what is on disk, so the two can be A/B'd instead of assumed.
REFERENCE_POSE = "bot"          # "bot" = what places/ holds today; "human" = backups
HUMAN_REFERENCE_DIR = "places_backup_20260903_020639"


def _recorded_reference(node):
    """The frame align_at_node corrects toward, or None.

    NOT necessarily the pose the outgoing leg was recorded from — see
    REFERENCE_POSE above. That mismatch is the point of the flag.
    """
    import glob
    if REFERENCE_POSE == "human":
        hits = sorted(glob.glob(os.path.join(HUMAN_REFERENCE_DIR, node,
                                             "route_*.jpg")))
        if hits:
            return hits[0]
    hits = sorted(glob.glob(os.path.join("places", node, "route_*.jpg")))
    return hits[0] if hits else None


# NULL THE YAW BEFORE MEASURING LATERAL OFFSET.
#
# pose.offset's own docstring states the precondition — "Null the yaw with the
# compass first and what remains is lateral translation" — and until 2026-09-05
# NOTHING did. align_at_node measured dx and strafed on it, so every degree of
# heading error was corrected as if it were sideways displacement.
#
# MEASURED at the live geometry (7 pure camera-turn pairs, character
# stationary, world_log/20260903_000028_brett): 18.6-20.8 px per degree, sign
# consistent, corroborated by camera_fov.json (1920 / 102 deg = 18.8).
#
# So the units collide badly:
#     ALIGN_TOL_PX  35.0   is 1.8 DEGREES of heading
#     SAME_POSE_PX  16.85  is 0.87 DEGREES
# while the leg executor turns with a 4.0 degree tolerance. A character parked
# perfectly on the reference POSITION but 2 degrees off its heading reads ~40px
# and gets strafed sideways to "fix" it.
#
# There is a systematic component too, not just noise: each node's reference
# frame heading differs from its leg's last commanded bearing by
# 2.56 / 1.02 / -0.50 degrees (portrait_room / bar_jukebox / bar_pool_room),
# i.e. a standing phantom of ~50 / ~20 / ~10 px. portrait_room's exceeds
# ALIGN_TOL_PX on its own.
#
# The fix uses this project's own principle: TURNING DOES NOT MOVE THE
# CHARACTER, walking does. So turn to the reference's own heading first, then
# measure — rather than trying to subtract an estimated yaw term.
#
# Flagged so it can be A/B'd, but it defaults ON because the current behaviour
# violates a documented precondition rather than merely being tuned differently.
# Its effect on ARRIVAL RATE is unmeasured; that is the experiment to run.
# Measured at the live geometry: 18.6-20.8 px of apparent horizontal shift per
# degree of yaw (7 pure camera-turn pairs, character stationary), corroborated
# by camera_fov.json (1920 / 102 deg = 18.8).
PX_PER_DEG = 18.8

# How close the heading must be before the lateral measurement is trusted.
# NOT slow_traverse's 4.0: that is a WALKING tolerance, and 4.0 deg is ~75px of
# phantom dx against an ALIGN_TOL_PX of 35 — the correction would chase an
# error twice its own target.
YAW_NULL_TOLERANCE_DEG = 0.5

NULL_YAW_BEFORE_ALIGN = True

# Cache of reference-frame headings, so the compass read happens once per node
# per process rather than on every alignment.
_REF_HEADING = {}


def reference_heading(node):
    """The heading the reference frame for `node` was captured at, or None.

    KEYED ON (REFERENCE_POSE, node), NOT node. The value comes from
    _recorded_reference(node), which picks a DIFFERENT file depending on
    REFERENCE_POSE — that mismatch is the entire point of the flag. Keyed on the
    node alone, an A/B that flips the flag in-process kept serving the first
    arm's heading to the second, so both arms nulled yaw to the same reference
    and the comparison measured nothing. An A/B harness that silently returns
    one arm's value for both is the worst shape available here: it produces a
    clean null result and no error.
    """
    key = (REFERENCE_POSE, node)
    if key in _REF_HEADING:
        return _REF_HEADING[key]
    h = None
    ref = _recorded_reference(node)
    if ref is not None:
        try:
            import compass
            from PIL import Image
            h = compass.read_bearing(Image.open(ref))
        except Exception:
            h = None
    _REF_HEADING[key] = h
    return h


def align_at_node(node, capture=None, read_heading=None, log=print):
    """Correct the character onto REFERENCE_POSE's frame for `node`.

    NOTE: with REFERENCE_POSE = "bot" this is NOT the pose the outgoing leg was
    recorded from — the two are 71-212px apart AS MEASURED, but a large part of
    that is YAW, not position: at 18.8 px/deg the 6.87 degree heading difference
    at bar_pool_room accounts for ~129px of its -212.2, i.e. 62%. The dy terms
    are unaffected by yaw and remain the evidence that these really are
    different places. The docstring used to claim it
    was, which stopped being true the moment the references were swapped.
    """
    import pose
    import slow_traverse as st
    import walk_steps as ws

    ref = _recorded_reference(node)
    if ref is None:
        # NOT the same as "could not measure". This exit means alignment never
        # ran at all — there is no route_*.jpg on disk for this node — and a
        # node in that state skips correction silently on every run forever.
        # The caller used to report it as "could not correct", which is the
        # wrong explanation and would send a reader looking at the stools.
        log(f"      align at {node}: NO REFERENCE FRAME on disk "
            f"(REFERENCE_POSE={REFERENCE_POSE!r}) — alignment did not run")
        return None
    capture = capture or _default_capture
    from PIL import Image
    ref_img = Image.open(ref)

    # Make pose.offset's precondition TRUE before relying on it.
    if NULL_YAW_BEFORE_ALIGN:
        want = reference_heading(node)
        if want is None:
            log(f"      align at {node}: reference heading UNREADABLE — "
                f"measuring dx with the yaw NOT nulled, so part of it is "
                f"heading error, not displacement")
        else:
            try:
                # EXPLICIT TOLERANCE. Omitting it defaulted to
                # slow_traverse.TURN_TOLERANCE = 4.0, and every offset this
                # exists to remove is INSIDE 4.0 (2.56 / -0.50 / -1.47 deg at
                # the three nodes) — so it turned on 0 of 3 nodes while logging
                # as though it had. A no-op that reports success is the exact
                # shape this fix was written to remove, committed inside the
                # fix itself.
                #
                # 0.5 deg is ~9px at the measured 18.8 px/deg, comfortably
                # under ALIGN_TOL_PX = 35. At 4.0 the residual alone is ~75px,
                # i.e. twice the tolerance the aligner then tries to reach.
                got_h, _hz = st.turn_to(want, read_heading=read_heading,
                                        capture=capture, log=log,
                                        tolerance=YAW_NULL_TOLERANCE_DEG)
                if got_h is None:
                    log(f"      align at {node}: could not turn to the "
                        f"reference heading {want:.1f} — dx below still "
                        f"carries yaw")
                else:
                    # REPORT THE RESIDUAL AS A RESIDUAL. The first version
                    # printed "N deg out = ~Npx of phantom dx removed" — the
                    # error still PRESENT, described as the error removed, in a
                    # run where ar.send was called zero times.
                    err = abs((got_h - want + 180) % 360 - 180)
                    log(f"      align at {node}: yaw nulled to {got_h:.1f} "
                        f"(reference {want:.1f}) — {err:.1f} deg REMAINING "
                        f"= ~{err * PX_PER_DEG:.0f}px of phantom dx still in "
                        f"the dx below")
            except Exception as e:
                log(f"      align at {node}: yaw null FAILED "
                    f"({type(e).__name__}: {e}) — dx still carries heading error")

    got = pose.align_lateral(ref_img, capture, ws.walk_forward, log=log)
    log(f"      aligned at {node}: "
        f"{'unmeasurable' if got is None else f'{got:.0f}px from the recorded pose'}")
    return got


# The leg-end frame per node, published by follow() and read by
# follow_verified. A module global rather than a return value because follow()
# is called through go_to_node_verified, and threading a frame back up three
# signatures to fix a diagnostic is not worth the churn.
#
# It exists because follow_verified was classifying `before` — a frame captured
# at the TOP of its own loop, i.e. the PREVIOUS node's successful arrival. Four
# frames saved that way on 2026-09-04 all identified as bar_pool_room at 506-734
# matches while claiming to show the jukebox leg, so failures_by_kind was a
# re-encoding of WHICH node failed, not why.
_LAST_LEG_END = {}


def follow(m, start, goal=GOAL, capture=None, read_heading=None, log=print,
           shots=None):
    """Walk from `start` to `goal` over the recorded graph.

    Re-checks position after EVERY leg and stops at the first mismatch. It does
    not carry on hoping: a route walked from the wrong node puts the character
    somewhere no leg describes, which is how four attempts ended jammed in
    geometry.
    """
    capture = capture or _default_capture
    read_heading = read_heading or _default_heading

    if not stream_is_live(capture):
        log("  the stream is FROZEN — refusing to walk. Every frame would be "
            "identical, so nothing would look blocked and any confirmation "
            "that passed once would pass forever.")
        return {"arrived": False, "reached": start, "reason": "stream_frozen",
                "legs": [], "unverified": []}

    reason = m.route_reason(start, goal)
    if reason != "ok":
        log(f"  no route {start} -> {goal}: {reason}")
        return {"arrived": False, "reached": start, "reason": reason, "legs": []}

    path = m.route(start, goal)
    log(f"  route: {' -> '.join(path)}  ({m.route_cost(path):.1f}s of walking)")

    legs, at, unverified = [], start, []
    for a, b in zip(path, path[1:]):
        log(f"    leg {a} -> {b}")
        if b == GOAL:
            # The recorded push is replaced by a checked approach; see
            # approach_goal(). Everything upstream still replays as recorded.
            _reached = approach_goal(m.steps_for(a, b), capture,
                                     read_heading, log=log)
            # RECORD IT. This return was discarded, so a leg that walked its
            # whole length without the prompt ever appearing logged exactly
            # what a clean arrival logged. "A measurement taken and discarded"
            # is item three in the diagnosis catalogue.
            log(f"      approach_goal: prompt {'FOUND' if _reached else 'not seen'}")
            leg = {"a": a, "b": b, "steps": len(m.steps_for(a, b)),
                   "travelled": None, "hazards": []}
        else:
            # Stop short on legs whose destination can be RECOGNISED, so the
            # gap is closed by measurement instead of by dead reckoning.
            frac = (LEG_FRACTION if (SHORT_WALK and confirmable(m, b)
                                     and b != GOAL) else 1.0)
            leg = walk_link(m, a, b, capture, read_heading, log=log,
                            fraction=frac)
        # ARRIVING AT THE TABLE IS AN AIM, NOT JUST A POSITION. The last leg
        # leaves the character at the table but facing a heading that varies
        # with where it came to rest, and the prompt only shows over a narrow
        # arc — so sweep for it before calling the leg failed.
        if b == GOAL:
            _at_table = reach_table(capture, read_heading, log=log)
            log(f"      reach_table: {'at the table' if _at_table else 'GAVE UP'}")
        img = capture()
        # THIS IS THE FRAME THAT CAN DIAGNOSE THE LEG: the leg has ended and
        # recover_to_node (below) has not run yet. Publish it so follow_verified
        # can classify the leg rather than the frame it happens to hold — see
        # _LAST_LEG_END.
        _LAST_LEG_END[b] = img
        if shots:
            os.makedirs(shots, exist_ok=True)
            # STAMPED, NOT `at_{b}.jpg`. A fixed name is overwritten by every
            # attempt and every trial, so a 10-trial A/B ended with ONE frame
            # per node — the last one — and the failures it was collected to
            # explain had already been overwritten by later successes.
            img.convert("RGB").save(
                os.path.join(shots, f"at_{b}_{int(time.time() * 1000)}.jpg"),
                quality=85)
        verdict, detail = confirm(m, b, img, log=log)
        # A leg that did not land is worth a short hunt BEFORE walking the next
        # one from an unknown spot. Only for nodes the localiser can confirm —
        # for the rest there is nothing to hunt with.
        if verdict is None and RECOVER_MISSED and confirmable(m, b) and b != GOAL:
            if recover_to_node(m, b, capture, read_heading, log=log):
                img = capture()
                verdict, detail = confirm(m, b, img, log=log)
        leg["verdict"], leg["detail"] = verdict, detail
        legs.append(leg)
        log(f"      arrived? {verdict}  ({detail})")
        if verdict is None:
            # Advisory only. The AUTHORITATIVE check is the goal's own prompt,
            # which separates cleanly; a mid-route node that cannot be
            # recognised is a gap in the reference set, not evidence of being
            # somewhere else.
            unverified.append(b)
        if verdict is False:
            log(f"    STOPPING at leg {a} -> {b}: the destination did not check "
                f"out, so every leg after this one would be walked from an "
                f"unknown position")
            return {"arrived": False, "reached": at, "failed_leg": (a, b),
                    "reason": "wrong_room", "legs": legs,
                    "unverified": unverified}
        at = b
        # Now that we KNOW where we are, put the character back on the pose the
        # next leg was recorded from, before walking it.
        if ALIGN_AT_NODES and verdict is True and b != GOAL:
            _dx = align_at_node(b, capture, read_heading, log=log)
            # None means the aligner could NOT MEASURE — a different thing from
            # "measured, already aligned", and the two were indistinguishable
            # in the log. At bar_pool_room the character is against the stools
            # and strafing does nothing, so this is the expected shape of the
            # failure that costs runs.
            if _dx is None:
                # align_at_node has already said WHICH kind of None this is —
                # no reference frame on disk, or a frame it could not measure.
                # This line used to assert "could not correct", which is the
                # wrong explanation for the first case.
                log(f"      align at {b}: no dx (see the reason above)")
            else:
                log(f"      align at {b}: dx {_dx:+.1f}px")
    if unverified:
        log(f"  arrived, but {len(unverified)} node(s) could not be confirmed "
            f"on the way: {unverified} — each is a hole in the reference set")
    return {"arrived": True, "reached": at, "reason": "ok", "legs": legs,
            "unverified": unverified}


# ---------------------------------------------------------------------------
# VERIFIED ROUTE EXECUTION
# ---------------------------------------------------------------------------
# WHY THIS EXISTS, and why it is not just follow() with a stricter check.
#
# Measured 2026-09-03, n=20 with zero invalid trials: the route reaches
# bar_pool_room about **55%** of the time. follow() then walks the NEXT leg
# regardless, because it treats an abstention as advisory — a decision that was
# correct at the time (stopping on every abstention ended runs at node 1) but
# which means depth is a routing CLAIM, not a position.
#
# The arithmetic is what forces the rewrite. At 55% per node a three-node route
# arrives 0.55^3 = 17% of the time at best, and the requirement is 25
# CONSECUTIVE arrivals: 0.17^25 is effectively never. No leg tuning closes that
# — per-node arrival has to approach ~99% before 25 in a row is even
# arithmetically reachable.
#
# So the goal is not a better leg. It is NEVER WALKING A LEG FROM AN
# UNCONFIRMED POSE. go_to_node_verified() already refuses to do that, and this
# builds the route out of it.

# Filled in by follow_verified so consecutive_arrivals can report a run BY
# FAILURE SIGNATURE. A module global rather than a return value because
# follow_verified's (arrived, reached) signature is already used elsewhere.
_LAST_FAILURE_KINDS = []

# The frame a failure was classified FROM is not always the leg's own end —
# when no leg into `node` ever completed (the reset raised, the route was
# unreachable, follow() stopped at an earlier leg on every attempt) the
# classifier is handed the pre-attempt frame or the post-recovery view
# instead. Those two are the exact frames OPEN-1 was opened about: eight
# post-fan frames read bearing 98-106 against a leg commanded 2.1, and four
# pre-attempt frames identified as the node the leg DEPARTS FROM at 506-734
# matches. Both were classified confidently, and both described something
# other than the leg.
#
# So the class alone is not the measurement — the class AND where its frame
# came from is. This list runs in lockstep with _LAST_FAILURE_KINDS so a
# census can be taken over the admissible frames only, instead of over a
# mixture that no number in the result distinguishes.
_LAST_FAILURE_SOURCES = []

# The one provenance that is evidence about the leg. Named rather than spelled
# out at each site: the whole point is that the census compares against the
# SAME string the classifier recorded, and two copies of a sentence drift.
LEG_END_SOURCE = "the leg's own end"

# False when the last follow_verified PROVED the picture was not updating. Same
# reason for being a global as the list above, and read by consecutive_arrivals
# to record that trial as INVALID rather than as a route failure.
#
# It starts True and is reset at the top of every follow_verified, so a stale
# False from a previous trial can never invalidate the next one. Note that True
# here means "not proven dead", NOT "proven live": follow_verified only spends a
# liveness check when a node fails, so a clean run never sets it either way.
# consecutive_arrivals does its own before/after checks and does not rely on it.
_LAST_TRIAL_MEASURABLE = True

# Write each leg's outcome to leg_reliability.json as runs happen. Off by
# default: a measurement harness that also mutates state it reads is a way to
# make an A/B quietly non-reproducible.
RECORD_RELIABILITY = False


def follow_verified(m, route, capture=None, read_heading=None, log=print,
                    attempts=3, shots=None, start_hint=None):
    """Walk `route` node by node, PROVING position at each one.

    Returns (arrived_at_all, reached) where `reached` is the list of nodes
    actually verified, in order. Stops at the first node it cannot prove.

    The difference from follow() is not strictness for its own sake: a leg is
    dead-reckoned from an assumed starting pose, so walking one from an
    unverified position is walking a path that describes somewhere else. Every
    such leg compounds the error instead of correcting it.
    """
    global _LAST_TRIAL_MEASURABLE
    capture = capture or _default_capture
    _LAST_FAILURE_KINDS.clear()
    _LAST_FAILURE_SOURCES.clear()
    _LAST_TRIAL_MEASURABLE = True
    reached, kinds = [], []
    for node in route:
        # CAPTURE BEFORE RECOVERY. go_to_node_verified runs recover_to_node on
        # a miss, and its fan travels FURTHER than the leg it is rescuing
        # (0.33 speed-seconds per bearing over 5 bearings, against a 0.24
        # leg — ~7x cumulatively). A frame saved after that describes where the
        # FAN went, not where the leg ended.
        #
        # Measured: six archived fail_bar_jukebox frames sit at bearing
        # 98.1-105.8 while the leg commands 2.1 — a ~100 degree offset that is
        # exactly the fan walking back at +180 after its -80 offset. Six of six.
        # Every overshoot frame collected before this described the fan, and a
        # confident diagnosis was built on them and was wrong.
        # Drop any leg-end frame left over from an earlier trial, so a failure
        # can never be diagnosed with a picture of a different run.
        _LAST_LEG_END.pop(node, None)
        before = None
        if shots:
            try:
                before = capture()
            except Exception:
                before = None

        # Hand `shots` DOWN. follow() saves the arrival frame at :1419, BEFORE
        # recover_to_node runs at :1425 — the leg's own end, which is the frame
        # that can diagnose a failure. Capturing here instead photographs the
        # moment before the whole attempt, i.e. the PREVIOUS node's successful
        # arrival: the four frames taken that way on 2026-09-04 all identified
        # as bar_pool_room at 506-734 matches while claiming to show the
        # jukebox leg. The fix produced output, the output looked like
        # evidence, and it was not.
        # THE HINT IS FOR THE FIRST NODE ONLY, and is consumed here. After
        # node 1 the character has walked a leg, so the caller's "I just reset
        # onto SPAWN" is no longer true — passing it on would be the stale
        # cached handle from CLAUDE.md's catalogue, one leg later.
        hint, start_hint = start_hint, None
        ok = go_to_node_verified(m, node, capture=capture,
                                 read_heading=read_heading, log=log,
                                 attempts=attempts, shots=shots,
                                 start_hint=hint)
        # Record it where arrival is actually KNOWN, so the reliability record
        # builds itself from real runs rather than being hand-maintained.
        if RECORD_RELIABILITY and reached:
            try:
                import leg_reliability
                leg_reliability.record(reached[-1], node, ok)
            except Exception:
                pass                        # bookkeeping must never end a run
        # THE CONTROL GROUP. Failures have been saved since 2026-09-04;
        # successes never were. So "the 4 failures cluster within 27-87px" had
        # nothing to compare against — a spread means nothing without the
        # spread of the arrivals. One jpeg per arrival buys the comparison.
        if shots and ok and before is not None:
            try:
                import os as _os
                _d = _os.path.join(shots, "success")
                _os.makedirs(_d, exist_ok=True)
                before.save(_os.path.join(_d, f"ok_{node}_{int(time.time())}.jpg"))
            except Exception:
                pass                        # bookkeeping must never end a run
        if not ok:
            log(f"  could not verify {node} — stopping rather than walking the "
                f"next leg from an unknown pose")
            # CANNOT SEE IS NOT DID NOT ARRIVE, AND THIS IS WHERE THE TWO GET
            # CONFLATED. A frozen picture fails every confirmation there is, so
            # a dead stream produces character-for-character the log of a route
            # that missed its first node.
            #
            # Reproduced end to end 2026-09-05 with a capture returning
            # identical pixels: zero stick pushes issued, three resets, and the
            # trial recorded as a route FAILURE classified 'overshot' — "rich
            # frame, off the mapped route" — about a character that never moved.
            # follow() has refused to walk a frozen stream since 2026-09-02, but
            # its refusal returns quietly and everything above it read the
            # silence as a miss.
            #
            # Checked HERE, outside the `if shots:` block, because the check has
            # to happen whether or not a frame is being saved: consecutive_
            # arrivals is called without `shots` by measure_streak.py.
            live = stream_is_live(capture, log=log)
            if not live:
                _LAST_TRIAL_MEASURABLE = False
                log("      THE PICTURE IS NOT UPDATING. This trial measured "
                    "nothing — it is INVALID, not a route failure, and the "
                    "frame below is evidence of a dead stream, not a position.")
            # SAVE THE FRAME. Cause B (the jukebox leg, 9 of 9 of its failures)
            # is DETECTED but not diagnosed, and the reason is simply that no
            # run ever kept a picture of it. The obvious hypothesis — a bad pose
            # at bar_pool_room — was tested and rejected (p = 0.33), so the
            # answer is not in the numbers already collected. One jpeg per
            # failure costs nothing and is the only way to see it.
            # THE LEG'S OWN END, not `before`. `before` is captured at the
            # top of this loop, so it photographs the PREVIOUS node's
            # successful arrival — classifying it produced a census that just
            # re-encoded which node failed. follow() publishes the frame it took
            # when the leg ended and before recover_to_node ran, which is the
            # only one that can diagnose the leg.
            img = _LAST_LEG_END.pop(node, None)
            source = LEG_END_SOURCE
            if img is None:
                img = before
                source = "before the attempt (PREVIOUS node) — weak evidence"
            if img is None:
                try:
                    img = capture()
                    source = "after recovery — shows the fan, not the leg"
                except Exception:
                    img = None

            # CLASSIFY OUTSIDE `if shots:`. This whole block used to sit inside
            # it, and measure_streak.py calls consecutive_arrivals with no
            # shots — so on the runs that actually score the requirement, the
            # class census was silently EMPTY while still being reported.
            # Reporting arrival only in TOTAL averages several different
            # failures together, which is a leading explanation for why so many
            # well-motivated changes measured flat.
            if img is not None:
                try:
                    import failure_kind as fk
                    kind, detail = fk.classify(img, node, list(route),
                                               live=live)
                    log(f"      failure kind: {kind} — {detail} "
                        f"[frame: {source}]")
                    kinds.append(kind)
                    _LAST_FAILURE_KINDS.append(kind)
                    # LOCKSTEP. A kind recorded without its provenance is
                    # indistinguishable from one classified off the fan.
                    _LAST_FAILURE_SOURCES.append(source)
                except Exception as e:
                    log(f"      could not classify: {e}")
            else:
                log("      no frame to classify — this failure is uncategorised")

            if shots and img is not None:
                try:
                    import os as _os
                    _os.makedirs(shots, exist_ok=True)
                    path = _os.path.join(
                        shots, f"fail_{node}_{int(time.time() * 1000)}.jpg")
                    img.convert("RGB").save(path, quality=85)
                    log(f"      saved the failing frame to {path} ({source})")
                except Exception as e:
                    log(f"      could not save the failing frame: {e}")
            return False, reached
        reached.append(node)
    return True, reached


def consecutive_arrivals(m, route, trials, capture=None, read_heading=None,
                         log=print, reset_between=True, shots=None):
    """Run the route `trials` times and report the LONGEST CONSECUTIVE streak.

    The requirement is 25 in a row, so the streak — not the mean depth — is the
    number that matters. A 90% success rate with an independent failure every
    tenth run never produces 25 consecutively; reporting a mean would hide that
    completely.

    THE STREAM IS CHECKED BEFORE AND AFTER EVERY TRIAL, and a trial that cannot
    be measured is recorded as None — never as a non-arrival. A frozen picture
    fails every confirmation there is, so a sleeping console writes exactly the
    log of a route that missed, and reproducing it end to end produced
    arrived=False with ZERO stick pushes issued and a confident 'overshot'
    signature. Recording that as a failure has already invalidated one whole A/B
    on this project (the leg-tolerance run, 2026-09-03), and every experiment
    queued behind this one is scored on arrivals.

    Same before-and-after discipline as overnight/_harness.alive() and
    overnight/ab_attempts.py, deliberately rather than a third variant. It costs
    ~2.4s of a ~338s trial and it discards the occasional genuine arrival whose
    stream died a second later — which is the right way round to be wrong: a
    lost trial costs n, a mislabelled one costs the conclusion.
    """
    import reset_env
    global _LAST_TRIAL_MEASURABLE

    outcomes, streak, best = [], 0, 0
    all_kinds, invalid_why = [], []
    # Provenance, in lockstep with all_kinds. See _LAST_FAILURE_SOURCES.
    all_sources = []

    def invalid(i, why):
        # NOT `outcomes.append(False)`. The streak is deliberately left alone:
        # an unmeasurable trial is not evidence that the route broke, so it
        # must not break a streak the route never broke.
        log(f"  trial {i + 1}/{trials}: INVALID — {why}. Recorded as invalid, "
            f"NOT as a failure (cannot-see is not did-not-arrive).")
        outcomes.append(None)
        invalid_why.append(why)

    for i in range(trials):
        # BEFORE. A trial started on a dead picture can only produce a fake
        # failure, so do not spend the reset or the walk on it.
        if not stream_is_live(capture, log=log):
            invalid(i, "the stream was not updating before the trial")
            continue
        if reset_between:
            try:
                reset_env.reset_environment(log=log)
                time.sleep(1.2)
            except Exception as e:
                invalid(i, f"the reset failed ({type(e).__name__}: {e})")
                continue
        # Reset explicitly rather than trusting follow_verified to do it: a
        # stubbed follow_verified (every offline test has one) would otherwise
        # leave the previous trial's verdict standing.
        _LAST_TRIAL_MEASURABLE = True
        # THE RESET ABOVE ALREADY PUT THE CHARACTER ON SPAWN. Telling
        # follow_verified so saves the 13.9s sweep plus the second reset that
        # opened 26 of 26 archived trials — see TRUST_RESET_SPAWN. Only sent
        # when reset_between actually reset on THIS iteration; otherwise the
        # character is wherever the previous trial left it.
        ok, reached = follow_verified(m, route, capture=capture,
                                      read_heading=read_heading, log=log,
                                      shots=shots,
                                      start_hint=(SPAWN if (reset_between
                                                  and TRUST_RESET_SPAWN)
                                                  else None))
        kinds = list(_LAST_FAILURE_KINDS)
        sources = list(_LAST_FAILURE_SOURCES)
        # AFTER, and follow_verified's own verdict first. The two catch
        # different things and neither is redundant: follow_verified only
        # spends a liveness check when a node FAILS, so a trial that walked
        # cleanly and then hit a dead picture is caught only by the capture
        # comparison here.
        why = None
        if not _LAST_TRIAL_MEASURABLE:
            why = "the picture was proven frozen during the walk"
        elif not stream_is_live(capture, log=log):
            why = "the stream stopped updating during the trial"
        if why is not None:
            # Drop this trial's signatures too. They describe a photograph of a
            # dead stream, and failures_by_kind is what the next A/B is read
            # from.
            invalid(i, why)
            continue
        all_kinds.extend(kinds)
        all_sources.extend(sources)
        outcomes.append(bool(ok))
        streak = streak + 1 if ok else 0
        best = max(best, streak)
        log(f"  trial {i + 1}/{trials}: {'ARRIVED' if ok else 'failed'} "
            f"(verified {len(reached)}/{len(route)})  streak {streak}, best {best}")
    import failure_kind as fk
    by_kind = fk.tally(all_kinds)
    # THE CENSUS THAT IS EVIDENCE ABOUT THE LEGS is the one taken over frames
    # that came from a leg's own end. The rest were classified off the
    # pre-attempt view or the post-recovery view, and OPEN-1 exists because
    # exactly those two frames were once reported as a failure census.
    #
    # Reported as a SEPARATE key rather than by silently filtering by_kind:
    # dropping frames without saying so is how a denominator goes missing, and
    # a census over 3 of 11 failures that reads like a census over 11 is worse
    # than no census.
    leg_kinds = [k for k, src in zip(all_kinds, all_sources)
                 if src == LEG_END_SOURCE]
    by_kind_leg = fk.tally(leg_kinds)
    n_other = len(all_kinds) - len(leg_kinds)
    if by_kind:
        log("  failures by signature: " +
            ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())))
        log(f"    of which classified from the leg's own end: "
            f"{len(leg_kinds)}/{len(all_kinds)}" +
            (f"  ({', '.join(f'{k}={v}' for k, v in sorted(by_kind_leg.items()))})"
             if by_kind_leg else ""))
        if n_other:
            log(f"    {n_other} classified from a fallback frame (the "
                f"pre-attempt view or the post-recovery view) — NOT evidence "
                f"about the leg; excluded from failures_by_kind_leg_end")
    n_valid = sum(1 for o in outcomes if o is not None)
    n_invalid = sum(1 for o in outcomes if o is None)
    # STATE THE INVALID COUNT WHEREVER THE RATE IS STATED. A rate over an
    # unstated denominator is how "both arms degraded together" got read as a
    # result instead of as a dying console.
    log(f"  arrived {sum(1 for o in outcomes if o)}/{n_valid} VALID trials "
        f"({n_invalid} of {trials} invalid and excluded); best streak {best}")
    for w in sorted(set(invalid_why)):
        log(f"    invalid x{invalid_why.count(w)}: {w}")
    return {"outcomes": outcomes, "best_streak": best,
            "arrived": sum(1 for o in outcomes if o),
            "valid": n_valid,
            "invalid": n_invalid,
            "invalid_reasons": invalid_why,
            "failures_by_kind": by_kind,
            "failures_by_kind_leg_end": by_kind_leg,
            "failures_from_fallback_frame": n_other}
