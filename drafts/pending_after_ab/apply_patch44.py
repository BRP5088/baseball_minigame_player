"""patch44 (2026-09-08): STOP_LOOK_YAW -- at a stop the LOOK-AROUND verified,
correct the HEADING, not the position. Ships False; the A/B decides.

THE MEASUREMENT. agent_progress/closed-loop/review/after_look129_census.py
(and .out), over the 113 journals on disk that carry a `turned-looked` stop at
chain 129 -- the bar entrance, the stop the audit's own stop table names as the
lever (agent_progress/closed-loop/audit/stop_table.md):

  * the look fits at -25 deg on EVERY one of those trials, with the scene a
    further +dx to the RIGHT inside that yawed frame. The residual heading
    error the two together imply, theta = -25 + dx / PX_PER_DEG, has median
    -19.7 deg on the trials that went on to arrive and -19.2 on the ones that
    failed. It is the same offset either way: not a symptom of a bad trial.
  * the loop answers it with a SIDESTEP -- px = dx + ddeg * PX_PER_DEG is
    negative, so it strafes LEFT for the capped 0.3 s.
  * and the FIRST head-on fit after that strafe reads dx median **-300 px** on
    arrivals (93 of 96 credible, -379..-17) and -269 on failures. The scene is
    still ~15 deg left of the walking heading. The sidestep changed nothing
    measurable, because the offset is a YAW and a sidestep cannot fix a yaw.
  * what the sidestep DOES do is move the character. Six of tonight's failures
    put it into the doorway corner or into an NPC and the view then did not
    change for twenty rows (census_after_129_notes.md; the readers
    notes_cur_t12_1788856027.md and notes_b17_t08.md). The arrivals instead
    carry the offset all the way through waypoints 130-142, "firing LEFT on
    393 of 419 fits and not converging"
    (agent_progress/closed-loop/waste/bar-counter.md).

THE CHANGE, and it is a shape this project already ships. The END TURN
(chain_walk.py, see END_TURN_PX) reads exactly this quantity in the tail and
answers it as a yaw: ddeg = dx / PX_PER_DEG, clamped to END_TURN_MAX_DEG,
turn, and add it to every remaining heading through `end_yaw`. STOP_LOOK_YAW
is that rule at a looked stop:

  * the same formula and the same cap, referenced not copied, so the two
    cannot drift into two different numbers;
  * the same sign convention (pose.offset): a NEGATIVE px -- the scene sits
    LEFT of the walking heading -- turns LEFT, i.e. DECREASING heading;
  * the offset rides every push until the NEXT TURN-ONLY STOP through
    `stop_yaw` -- reached or passed -- exactly as `end_yaw` rides the tail,
    because otherwise the next turn to a recorded heading would undo it;
  * and NO strafe. The strafe is what it replaces.

It is HANDOFF_NOW.md item (e) for the look-around only, behind a flag, for an
A/B. It moves NOTHING: GRAVEYARD's two survivors out of thirteen navigation
changes are the aim sweep and turning, and every change that failed MOVED the
character. This one removes a movement.

WHERE stop_yaw IS CLEARED, and why each one:

  (a) AT THE NEXT TURN-ONLY STOP -- REACHED **OR PASSED**, before that stop's
      own turn. A stop is verified against the recording's frame at the
      recording's heading, and the yaw was a correction measured at a
      DIFFERENT stop from a position the walk has since left. The stop is
      approached square and its own look-around measures the residual afresh.

      "OR PASSED" is a skeptic's CONFIRMED defect against the first draft
      (2026-09-08). The clear sat on the UNPACK of `plan[pi]`, and a wide
      relocalisation jumps k over whole plan entries -- the stop branch's
      "relocalised past the stop", the blind path's forward search, the lost
      rescue -- which are then never unpacked. Reproduced: a yaw taken at
      chain 2 rode EVERY push from chain 25 on, twenty waypoints past the
      stop that should have ended it. The plan-pointer advance now clears on
      any turn-only entry it walks over, and `pi` at the top of an iteration
      is still the entry the previous one serviced, so the stop the loop just
      took -- whose own look-around set the yaw -- is left alone. A jump over
      PUSH entries alone does NOT clear, and that is pinned in both
      directions: a wide fix says the character is further along than the
      loop thought, not that the camera is back on the recorded line.
  (b) ON A LOOK-BACK REGRESSION, beside `end_yaw = 0.0` and for the reason
      that branch already gives in its own comment: the loop has just said the
      character is behind where it thought, which is the position the offset
      was measured from, and the branch rewinds the plan pointer to 0 -- so
      without this the offset would ride the recorded mid-chain headings from
      there, which is the "steering while walking" family GRAVEYARD closed.
  (c) ON A LOST RESCUE (patch43/43b, commit 32e4400, already in the tree),
      beside that branch's `end_yaw = 0.0` and `turned_early = False`, for the
      same reason: the rescue backs the character out and re-aims from a
      believed look. Applied ONLY if that branch is present -- the script says
      which it did, and the test for it is inserted under the same condition,
      because a test for a branch that is not there fails for the wrong
      reason.

It is deliberately NOT cleared by a later credible fit. If the yaw was right,
the next head-on fit reads dx ~ 0 and the lateral logic is idle; if it was
wrong, the ordinary lateral correction strafes exactly as it does today.

THE HARNESS. overnight/chain_trials.py's `--arms off,on` set ONE hard-coded
attribute (STOP_PAN_FROM_RUN). Generalised minimally: `--flag NAME` names the
chain_walk attribute the arm sets, defaulting to STOP_PAN_FROM_RUN so every
invocation written before this behaves exactly as it did. The name reaches the
CHILD through BASEBALL_CHAIN_ARM_FLAG beside the arm's own value (process
death is the restore, §10.17), the child logs `arm: <NAME> = ...`, the result
records the flag name and its value, and the tally line prints the LABEL. A
`--flag` that names no chain_walk attribute is refused in the parent AND in
the child rather than silently arming nothing -- that is §10.1's no-op that
logs like a change, in the one place where it would cost a whole A/B.

AND THE LABEL IS NOT THE FLAG NAME WHEN THE FLAG IS THE DEFAULT. A skeptic's
second CONFIRMED defect: the first draft wrote `row["arm"]` and the tally line
as `f"{flag}-{arm}"`, so an `--arms off,on` with no `--flag` -- the invocation
the option was built to leave alone -- silently renamed every row from
`pan-on` to `STOP_PAN_FROM_RUN-on`. `arm_label(flag)` returns "pan" for the
default and the flag's own name otherwise, which is the same rule this patch
already applies to `res["pan"]`: an old chain_trials.json and tonight's
compare row for row, and a reader watching the log sees no change.

AND THE READER GOES WITH IT. `tools/trial_sheet.py` -- what the user's
standing rule runs on every failed trial -- matched the arm label with the
literal `pan-\\w+`. With the label now the flag's own name it did not
mis-parse those lines, it REFUSED every one of them ("cannot parse the trial
line") for the whole batch. The pattern is hoisted to `LINE_RE` and widened to
any `<NAME>-on|off`, and a test carries the old label, the new one, and a line
with no arm at all.

TESTS: class StopLookYaw (13) and seven in HarnessScoring, in
tests/routing/test_chain_walk.py. Verified on a scratch COPY of the tree with
patch43 in it: 165 tests before, 185 after, all green.

MUTANTS, one at a time on that copy, restore in a `finally`, __pycache__
deleted between and the file SIZE asserted to change (10.10) --
agent_progress/closed-loop/stop_yaw/mutants.py, all fifteen caught:

  the yaw's sign flipped            -> ...TURNS_by_the_offset..., and 4 more
  stop_yaw not added to the pushes  -> the same five
  not cleared at the next stop      -> ..._cleared_at_the_next_turn_only_stop
  the flag ignored (yaw when off)   -> ..._with_the_flag_OFF_the_stop_STRAFES...
                                       and three EXISTING look-around tests
  the clamp removed                 -> ..._capped_at_END_TURN_MAX_DEG
  the LATERAL_TOL_PX gate removed   -> ..._inside_LATERAL_TOL_PX_neither...
  the regression clear removed      -> ..._a_REGRESSION_BEHIND_EVERY_STOP...
    (the ORIGINAL regression test no
     longer catches this on its own:
     it regresses to the stop's own
     index, which the new skip clear
     re-passes and drops the yaw at.
     One rule masking another -- so
     the second regression test lands
     the look-back at waypoint 0,
     behind every stop, where the
     explicit clear is alone.)
  the LOST RESCUE's clear removed   -> ..._a_LOST_RESCUE_drops_the_stop_yaw
  the harness arming the pan flag
    regardless of --flag            -> ..._the_arm_sets_the_flag_the_run_NAMED
  the SKIPPED-stop clear removed    -> ..._a_SKIPPED_turn_only_stop_drops...
  that clear OVER-firing (dropping
    `pi > pi_serviced`, so the stop
    the loop just took clears the
    yaw it has only now set)        -> ..._TURNS_by_the_offset..., and 4 more
  that clear ignoring TURN-ONLY
    (dropping `not plan[pi][1]`)    -> ..._a_jump_over_PUSHES_ALONE_keeps...
  the PAN branch yawing too         -> ..._the_PAN_branch_takes_no_yaw...
    (SURVIVED the first draft: no
     test armed both flags at once)
  the arm LABEL back to the flag
    name, in the function and at
    the row                         -> ..._the_default_arms_ROW_LABEL_is_still_pan
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
H = os.path.join(ROOT, "overnight", "chain_trials.py")
TS = os.path.join(ROOT, "tools", "trial_sheet.py")
c = open(C).read()
t = open(T).read()
h = open(H).read()
ts = open(TS).read()
if ("STOP_LOOK_YAW" in c or "class StopLookYaw" in t
        or "ARM_FLAG_ENV" in h or "LINE_RE" in ts):
    raise SystemExit("ALREADY APPLIED")

# ---------------------------------------------------------------- chain_walk
CONSTANTS = '''STOP_PAN_LOOKS = 2              # how many run frames to look at (first, middle)
# AT A STOP THE LOOK-AROUND VERIFIED, CORRECT THE HEADING, NOT THE POSITION
# (ships False; the A/B decides).
#
# THE MEASUREMENT (agent_progress/closed-loop/review/after_look129_census.py
# and .out, over the 113 journals carrying a `turned-looked` stop at chain
# 129 -- the bar entrance, the stop the audit's own table names as the lever):
# the look fits at -25 deg on EVERY one of them, with the scene a further +dx
# to the RIGHT inside that yawed frame, so the residual heading error
# theta = -25 + dx / PX_PER_DEG has the SAME median on the trials that
# arrived and on the ones that failed -- close to -20 deg either way, so it is
# not a symptom of a bad trial. The loop answers it with a SIDESTEP, and the
# FIRST head-on fit after that strafe still reads dx median -300 px on
# arrivals (93 of 96 credible, -379..-17) and -269 on failures: the scene is
# still ~15 deg left of the walking heading. The sidestep changes NOTHING
# measurable, because the offset is a YAW and a sidestep cannot fix a yaw.
# What it DOES do is move the character -- six of 2026-09-08's failures put it
# into the doorway corner or into an NPC, the view then unchanged for twenty
# rows -- while the arrivals carry the offset all the way through waypoints
# 130-142, correcting LEFT on 393 of 419 fits without converging
# (agent_progress/closed-loop/waste/bar-counter.md).
#
# (The exact median residual is in that script's .out and is deliberately not
# repeated as a number here: px-per-degree is ONE literal in this file,
# PX_PER_DEG, and tests/routing/test_chain_walk.py counts the occurrences.)
#
# So turn by it. This is the END TURN's own rule (see END_TURN_PX) applied at
# a looked stop instead of only in the tail, referencing its formula and its
# cap rather than copying them, and it is what HANDOFF_NOW.md item (e) asked
# for. It MOVES NOTHING: GRAVEYARD's two survivors out of thirteen navigation
# changes are the aim sweep and turning, and every change that failed moved
# the character. `stop_yaw` carries it until the next turn-only stop.
STOP_LOOK_YAW = False
'''

LOOPVAR = '''    end_yaw = 0.0               # degrees added to every remaining tail heading
    stop_yaw = 0.0              # ... and the degrees a LOOKED STOP's yaw adds
                                # to every push until the next turn-only stop
                                # (STOP_LOOK_YAW). Zero unless that flag is on.
'''

ADVANCE = '''        # THE PLAN POINTER: the next target is the first plan entry past k.
        #
        # A TURN-ONLY STOP THE POINTER PASSES WITHOUT TAKING IT DROPS THE YAW,
        # exactly as a stop the loop actually takes does. The clear below lives
        # on the UNPACK of `plan[pi]`, and a SKIPPED entry is never unpacked: k
        # jumps on a wide relocalisation -- the stop branch's "relocalised past
        # the stop", the blind path's forward search, the lost rescue -- and
        # the pointer then walks over whatever lies between. Reproduced
        # (agent_progress/closed-loop/stop_yaw): a yaw taken at chain 2 rode
        # every push from chain 25 on, twenty waypoints past the stop that
        # should have ended it, which is the "steering while walking" family
        # GRAVEYARD closed. The ordinary advance cannot do this -- ADVANCE_MAX
        # is 1 and `new_k` is capped at `target_k` -- and `_near_stop` returns
        # the FIRST turn-only entry in its window, so turn-early skips only
        # pushes; the wide jumps are the whole population.
        #
        # `pi` here is STILL the entry the previous iteration serviced, since
        # nothing moves it after the unpack. So `pi > pi_serviced` is precisely
        # "this entry was jumped over", and the stop the loop just took --
        # whose own look-around is what set the yaw -- is left alone.
        pi_serviced = pi
        while pi < len(plan) and plan[pi][0] <= k:
            if pi > pi_serviced and not plan[pi][1]:
                stop_yaw = 0.0
            pi += 1
'''

CLEAR_AT_STOP = '''        else:
            target_k, do_push, heading = plan[pi]
        if not do_push:
            # A TURN-ONLY STOP TURNS TO THE PLAN'S OWN HEADING. A stop is
            # verified against the recording's frame at the recording's
            # heading, and STOP_LOOK_YAW's offset was a correction measured at
            # a DIFFERENT stop, from a position the walk has since left.
            # Cleared HERE, before the turn below, so the stop is approached
            # square and its own look-around measures the residual afresh.
            stop_yaw = 0.0
'''

GUARD = '''        if (end_yaw or stop_yaw) and heading is not None:
'''

SUM = '''            # ... and STOP_LOOK_YAW's `stop_yaw` rides the same way and for
            # the same reason: a yaw taken at a stop has to survive until the
            # next turn-only stop, or the very next turn to a recorded heading
            # would undo the correction that earned it. It is cleared at that
            # stop, on a look-back regression, and on a lost rescue.
            heading = (heading + end_yaw + stop_yaw) % 360.0
'''

LOOK_OLD = '''                    px = dx2 + ddeg * PX_PER_DEG
                    # ONE ordinary correction, not a double one: batch 7 trial
                    # 1's look fit (77 inliers, yawed 25 deg) drove a 0.6 s
                    # strafe RIGHT that three credible head-on fits then undid
                    # LEFT. A yawed fit sees the scene half out of frame; it
                    # earns a normal step, and the next head-on fit decides.
                    secs = min(LATERAL_CAP_SEC, abs(px) / (LATERAL_GAIN * LATERAL_MAG))
                    if secs >= LATERAL_MIN_SEC:
                        side = RIGHT if px > 0 else LEFT
                        strafe(side * LATERAL_MAG, secs)
                        looked["strafe"] = {"side": "right" if side > 0 else "left",
                                            "seconds": round(secs, 3), "px": round(px)}
'''

LOOK_NEW = '''                    px = dx2 + ddeg * PX_PER_DEG
                    if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:
                        # THE OFFSET AT A LOOKED STOP IS A YAW, NOT A POSITION
                        # (see STOP_LOOK_YAW): turn by it instead of stepping
                        # sideways, and let it ride every push until the next
                        # turn-only stop. The END TURN's own formula and cap,
                        # referenced rather than copied so the two cannot drift
                        # into two different numbers, and its sign convention:
                        # a NEGATIVE px -- the scene sits LEFT of the walking
                        # heading -- turns LEFT, i.e. DECREASING heading, which
                        # is pose.offset's convention. NO strafe: the strafe is
                        # the thing this replaces, and the census says it moved
                        # the character without moving the offset.
                        ddeg_fix = round(max(-END_TURN_MAX_DEG,
                                             min(END_TURN_MAX_DEG,
                                                 float(px) / PX_PER_DEG)), 1)
                        stop_yaw = ddeg_fix
                        new_heading = (heading + stop_yaw) % 360.0
                        turn_to(new_heading)
                        last_cmd = new_heading
                        looked["yaw"] = {"deg": ddeg_fix, "px": round(px)}
                    else:
                        # ONE ordinary correction, not a double one: batch 7 trial
                        # 1's look fit (77 inliers, yawed 25 deg) drove a 0.6 s
                        # strafe RIGHT that three credible head-on fits then undid
                        # LEFT. A yawed fit sees the scene half out of frame; it
                        # earns a normal step, and the next head-on fit decides.
                        secs = min(LATERAL_CAP_SEC, abs(px) / (LATERAL_GAIN * LATERAL_MAG))
                        if secs >= LATERAL_MIN_SEC:
                            side = RIGHT if px > 0 else LEFT
                            strafe(side * LATERAL_MAG, secs)
                            looked["strafe"] = {"side": "right" if side > 0 else "left",
                                                "seconds": round(secs, 3), "px": round(px)}
'''

STOP_LOG_OLD = '''            log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action}"
                f"{'' if turned else ' (skipped, same heading)'} to {heading}"
                f"  ({inl_t} inliers at the stop)")
'''

STOP_LOG_NEW = '''            log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  {action}"
                f"{'' if turned else ' (skipped, same heading)'} to {heading}"
                f"  ({inl_t} inliers at the stop)"
                # A STOP YAW has no side and no seconds; naming it in the log
                # is how a reader tells it from the sidestep it replaced.
                + (f"  STOP YAW {looked['yaw']['deg']:+.1f} deg on "
                   f"{looked['yaw']['px']} px, no strafe"
                   if looked is not None and "yaw" in looked else ""))
'''

REGRESSION = '''            end_yaw = 0.0
            # ... and STOP_LOOK_YAW's yaw with it, for the reason above word
            # for word: it was measured at a stop the look-back has just said
            # the character is behind, and this branch rewinds the plan
            # pointer to 0, so the offset would otherwise ride the recorded
            # mid-chain headings from there.
            stop_yaw = 0.0
            action = "regressed"
'''

# (c) ONLY IF patch43's LOST RESCUE is in the tree.
RESCUE_OLD = '''                    turned_early = False
                    action = "rescued"
'''
RESCUE_NEW = '''                    turned_early = False
                    # ... and STOP_LOOK_YAW's yaw, for the same reason as the
                    # end turn's above: the rescue has backed the character
                    # out and re-aimed it from a believed look, so a heading
                    # correction measured at a stop it has left is refuted.
                    stop_yaw = 0.0
                    action = "rescued"
'''

edits_c = [
 (CONSTANTS.split("\n")[0] + "\n", CONSTANTS),
 ('''    end_yaw = 0.0               # degrees added to every remaining tail heading
''', LOOPVAR),
 ('''        # THE PLAN POINTER: the next target is the first plan entry past k.
        while pi < len(plan) and plan[pi][0] <= k:
            pi += 1
''', ADVANCE),
 ('''        else:
            target_k, do_push, heading = plan[pi]
''', CLEAR_AT_STOP),
 ('''        if end_yaw and heading is not None:
''', GUARD),
 ('''            heading = (heading + end_yaw) % 360.0
''', SUM),
 (LOOK_OLD, LOOK_NEW),
 (STOP_LOG_OLD, STOP_LOG_NEW),
 ('''            end_yaw = 0.0
            action = "regressed"
''', REGRESSION),
]
RESCUE_PRESENT = c.count(RESCUE_OLD) == 1
if RESCUE_PRESENT:
    edits_c.append((RESCUE_OLD, RESCUE_NEW))

# ------------------------------------------------------------ chain_trials
edits_h = [
 ('''PAN_ENV = "BASEBALL_CHAIN_PAN"
''',
  '''PAN_ENV = "BASEBALL_CHAIN_PAN"
# ... and WHICH chain_walk attribute that value sets. `--flag NAME` names it;
# the default is the flag the option was built for, so every invocation
# written before `--flag` behaves exactly as it did. The name travels to the
# child beside the value, for the same reason (process death is the restore).
ARM_FLAG_ENV = "BASEBALL_CHAIN_ARM_FLAG"
DEFAULT_ARM_FLAG = "STOP_PAN_FROM_RUN"
'''),
 ('''USAGE = (".venv/bin/python -B overnight/chain_trials.py <chain-name> "
         "[--trials N] [--no-shots]")
''',
  '''USAGE = (".venv/bin/python -B overnight/chain_trials.py <chain-name> "
         "[--trials N] [--no-shots] [--arms off,on] [--flag CHAIN_WALK_FLAG]")
'''),
 ('''def _assert_live():
''',
  '''def arm_flag_name(argv=None):
    """The chain_walk attribute `--arms` switches, from `--flag NAME`.

    Read at CALL time from argv, never captured in a default (CLAUDE.md
    10.18): a module-level knob a test or a harness may redirect is resolved
    when it is used.
    """
    argv = list(sys.argv if argv is None else argv)
    if "--flag" in argv:
        i = argv.index("--flag")
        if i + 1 >= len(argv):
            raise SystemExit("--flag takes a chain_walk attribute name")
        return argv[i + 1]
    return DEFAULT_ARM_FLAG


def arm_label(flag):
    """The TEXT an arm's row and its tally line carry, from the flag it sets.

    THE DEFAULT FLAG KEEPS THE LABEL IT HAS ALWAYS HAD. Every `--arms off,on`
    written before `--flag` must produce the same bytes it did, so an old
    chain_trials.json's `pan-on` rows and tonight's compare row for row and a
    reader watching the log by eye sees no change -- the same rule this patch
    already applies to `res["pan"]`, which it leaves untouched beside the new
    `res["arm_flag"]`. A NAMED flag carries its own name, which is the point
    of naming it.
    """
    return "pan" if flag == DEFAULT_ARM_FLAG else flag


def apply_arm(chain_walk, log, env=None):
    """Set the armed flag INSIDE the child and say which one it was.

    Returns the attribute name, or None when no arm was requested. The
    environment is read at CALL time so a test can hand it one. A name that
    is not a chain_walk attribute is REFUSED rather than set: `setattr` on a
    typo binds something nothing reads, both arms then run the shipped
    default, and the A/B reports a clean interleave of one arm with itself --
    CLAUDE.md 10.1's no-op that logs like a change, in the one place where it
    costs the whole measurement.
    """
    env = os.environ if env is None else env
    arm = env.get(PAN_ENV)
    if arm is None:
        return None
    name = env.get(ARM_FLAG_ENV) or DEFAULT_ARM_FLAG
    if not hasattr(chain_walk, name):
        raise SystemExit(f"--flag names no chain_walk attribute: {name}")
    setattr(chain_walk, name, arm == "on")
    log(f"  arm: {name} = {getattr(chain_walk, name)}")
    return name


def _assert_live():
'''),
 ('''    pan = os.environ.get(PAN_ENV)
    if pan is not None:
        chain_walk.STOP_PAN_FROM_RUN = (pan == "on")
        log(f"  arm: STOP_PAN_FROM_RUN = {chain_walk.STOP_PAN_FROM_RUN}")
''',
  '''    armed = apply_arm(chain_walk, log)
'''),
 ('''    res["pan"] = bool(chain_walk.STOP_PAN_FROM_RUN)
''',
  '''    res["pan"] = bool(chain_walk.STOP_PAN_FROM_RUN)
    # WHICH flag this trial's arm set, and to what. `pan` above is kept
    # unchanged so every result recorded before `--flag` still reads the same.
    res["arm_flag"] = armed or DEFAULT_ARM_FLAG
    res["arm_value"] = bool(getattr(chain_walk, res["arm_flag"], False))
'''),
 ('''        arms = spec.split(",")
        if any(a not in ("off", "on") for a in arms):
            raise SystemExit("--arms takes off/on values, e.g. --arms off,on")
''',
  '''        arms = spec.split(",")
        if any(a not in ("off", "on") for a in arms):
            raise SystemExit("--arms takes off/on values, e.g. --arms off,on")
    flag = arm_flag_name()
    label = arm_label(flag)
    if "--flag" in sys.argv:
        args = [a for a in args if a != flag]
'''),
 ('''    import console_lock
    import chain_walk
''',
  '''    import console_lock
    import chain_walk

    # Refused in the PARENT as well as the child, so a typo costs one second
    # rather than a whole interleaved batch of one arm against itself.
    if not hasattr(chain_walk, flag):
        raise SystemExit(f"--flag names no chain_walk attribute: {flag}")
'''),
 ('''           "arms": arms,
''',
  '''           "arms": arms,
           "arm_flag": flag,
'''),
 ('''            if arm is not None:
                os.environ[PAN_ENV] = arm
''',
  '''            if arm is not None:
                os.environ[PAN_ENV] = arm
                # ... and WHICH flag it sets. Set HERE, inside main(), never
                # at import (CLAUDE.md 5, and tests/harness scans for it).
                os.environ[ARM_FLAG_ENV] = flag
'''),
 ('''                row["arm"] = "pan-" + arm
''',
  '''                row["arm"] = f"{label}-{arm}"
'''),
 ('''            rs = [r for r in got if r.get("arm") == "pan-" + a]
            tally[a] = (sum(1 for r in rs if r["outcome"] == ARRIVED), len(rs))
            log(f"  pan-{a}: arrived {tally[a][0]}/{tally[a][1]} valid")
''',
  '''            rs = [r for r in got if r.get("arm") == f"{label}-{a}"]
            tally[a] = (sum(1 for r in rs if r["outcome"] == ARRIVED), len(rs))
            log(f"  {label}-{a}: arrived {tally[a][0]}/{tally[a][1]} valid")
'''),
]

# -------------------------------------------------------------- trial_sheet
edits_ts = [
 ('''def main(tn, log=os.path.join(ROOT, "overnight", "chain_trials.log")):
''',
  '''# THE ARM LABEL IS THE ARMED FLAG'S OWN NAME (chain_trials `--flag`), not
# always "pan-": `--flag STOP_LOOK_YAW` writes `STOP_LOOK_YAW-on`. A pattern
# that only knew "pan-" did not mis-parse those lines, it REFUSED every one of
# them ("cannot parse the trial line") for the whole batch -- and this tool is
# what the user's standing rule runs on every failed trial. Hoisted so a test
# can reach it without the console, cv2 or a log on disk.
LINE_RE = re.compile(
    r"\\[ *(\\d+)\\] (\\w+)\\s+(?:([A-Za-z_][\\w.]*-(?:on|off))\\s+)?"
    r"k=(\\d+)/\\d+\\s+it=(\\d+)\\s+pushes=(\\d+)\\s+seconds=([\\d.]+)"
    r".*?failure=(.*)")


def main(tn, log=os.path.join(ROOT, "overnight", "chain_trials.log")):
'''),
 ('''    m = re.match(r"\\[ *(\\d+)\\] (\\w+)\\s+(?:(pan-\\w+)\\s+)?k=(\\d+)/\\d+\\s+it=(\\d+)\\s+pushes=(\\d+)\\s+seconds=([\\d.]+).*?failure=(.*)", line.strip())
''',
  '''    m = LINE_RE.match(line.strip())
'''),
]

# ------------------------------------------------------------ test_chain_walk
NEW_TESTS = '''class StopLookYaw(unittest.TestCase):
    """(n) AT A LOOKED STOP THE OFFSET IS A YAW, AND A SIDESTEP CANNOT FIX ONE.

    agent_progress/closed-loop/review/after_look129_census.py over the 113
    journals with a `turned-looked` stop at chain 129: the look fits at -25 deg
    on every one, the scene sits a further +dx RIGHT inside that yawed frame,
    and the implied residual heading error has median -19.7 deg on arrivals
    and -19.2 on failures. The loop strafes LEFT for the capped 0.3 s -- and
    the first head-on fit afterwards still reads dx median -300 px. The
    sidestep moved the character and not the offset.

    STOP_LOOK_YAW turns by it instead, using the END TURN's own formula and
    cap, and carries the offset on every push until the next turn-only stop.
    It ships False; these tests drive it both ways and pin the shipped path
    as literals, because a mutant that ignores the flag must fail.
    """

    # wp2 is the STOP (ly = 0, a stationary run of one). The pushes after it
    # carry a DIFFERENT heading from the stop's, so a yaw riding the next push
    # shows up as its own turn instead of being hidden by TURN_SKIP_DEG.
    AFTER = [(10.0, -0.35), (10.0, -0.35)]

    def _wps(self, after=None):
        rows = [(90.0, -0.35), (0.0, 0.0)] + list(
            self.AFTER if after is None else after)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate(rows, start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        return wps

    def _rig(self, wps, fixes, table_at, lookback="script"):
        ch = FakeChain(len(wps), fixes, default=None, lookback=lookback)
        ch.waypoints = wps
        return Rig(ch, table_at=table_at)

    @staticmethod
    def _on(go, *a, **kw):
        """Run a walk with STOP_LOOK_YAW ON, restored in a finally."""
        old = chain_walk.STOP_LOOK_YAW
        chain_walk.STOP_LOOK_YAW = True
        try:
            return go(*a, **kw)
        finally:
            chain_walk.STOP_LOOK_YAW = old

    @staticmethod
    def turns(rig):
        return [round(e[1], 1) for e in rig.events if e[0] == "turn"]

    def test_the_flag_ships_OFF_and_reuses_the_END_TURNs_own_constants(self):
        # Literals (10.11): a test that reads the constant it guards passes
        # forever. STOP_LOOK_YAW invents no number of its own.
        self.assertIs(chain_walk.STOP_LOOK_YAW, False)
        self.assertEqual(chain_walk.PX_PER_DEG, 19.7)
        self.assertEqual(chain_walk.END_TURN_MAX_DEG, 45.0)
        self.assertEqual(chain_walk.LATERAL_TOL_PX, 35.0)
        self.assertEqual(chain_walk.STOP_LOOK_DEG, (-25.0, 25.0))

    def test_a_looked_stop_TURNS_by_the_offset_and_the_next_push_carries_it(self):
        # The census's own shape: the -25 look fits, and inside that yawed
        # frame the scene sits a further +235 px RIGHT, so the offset from the
        # WALKING heading is 235 - 25*19.7 = -257.5 px = -13.1 deg. LEFT.
        rig = self._rig(self._wps(),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                         None, Fix(k=3)], table_at=7)
        res = self._on(rig.go)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["advanced", "turned-looked"], acts)
        self.assertEqual(self.turns(rig),
                         [90.0, 0.0, 335.0, 25.0, 0.0, 346.9, 356.9],
                         "the stop, both looks, back to the stop, THE YAW "
                         "(0 - 13.1), then the NEXT PUSH's own plan heading "
                         "with the same yaw on it (10 - 13.1)")
        self.assertEqual(rig.strafes(), [],
                         "a yaw REPLACES the sidestep; it never does both")
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["yaw"], {"deg": -13.1, "px": -258})
        self.assertNotIn("strafe", lat)
        self.assertTrue(res["arrived"])

    def test_the_yaw_is_cleared_at_the_next_turn_only_stop(self):
        # A stop is verified against the recording's frame at the recording's
        # heading, so it is approached SQUARE: the yaw taken at the previous
        # stop was measured somewhere the walk has left.
        rig = self._rig(self._wps(after=[(10.0, -0.35), (20.0, 0.0),
                                         (30.0, -0.35)]),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                         None, Fix(k=3), Fix(k=4, inliers=200)], table_at=8)
        res = self._on(rig.go)
        turns = self.turns(rig)
        self.assertIn(346.9, turns, "ANTI-VACUITY: the yaw was taken")
        self.assertIn(356.9, turns, "... and it rode the push after it")
        self.assertEqual(turns,
                         [90.0, 0.0, 335.0, 25.0, 0.0, 346.9, 356.9,
                          20.0, 30.0],
                         "the SECOND stop turns to the plan's own 20.0 (not "
                         "6.9), and the push after it to 30.0 (not 16.9)")
        self.assertEqual([f["action"] for f in res["fixes"]][:4],
                         ["advanced", "turned-looked", "advanced", "turned"])
        self.assertTrue(res["arrived"])

    def test_with_the_flag_OFF_the_stop_STRAFES_exactly_as_today(self):
        # THE CONTROL, and the shipped path. Pinned as literals so a mutant
        # that yaws regardless of the flag fails here, and so that "the flag
        # off is byte-for-byte today's behaviour" is a measurement.
        self.assertIs(chain_walk.STOP_LOOK_YAW, False)
        rig = self._rig(self._wps(),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                         None, Fix(k=3)], table_at=7)
        res = rig.go()
        self.assertEqual(self.turns(rig), [90.0, 0.0, 335.0, 25.0, 0.0, 10.0],
                         "no yaw turn, and the next push takes the plan's raw "
                         "10.0")
        self.assertEqual(rig.strafes(), [("strafe", -0.3, 0.3)],
                         "LEFT at LATERAL_MAG for the capped LATERAL_CAP_SEC")
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat, {"deg": -25.0, "inliers": 90,
                               "strafe": {"side": "left", "seconds": 0.3,
                                          "px": -258}})
        self.assertNotIn("yaw", lat)

    def test_the_yaw_is_capped_at_END_TURN_MAX_DEG(self):
        # 1600 px inside the +25 frame is 1600 + 25*19.7 = 2092.5 px = 106.2
        # deg from the walking heading. A wrong match with a huge dx must not
        # spin the camera -- the END TURN's reason, and its constant.
        rig = self._rig(self._wps(),
                        [Fix(k=1), None, None,
                         Fix(k=2, inliers=90, dx=1600.0), Fix(k=3)],
                        table_at=7)
        res = self._on(rig.go)
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["deg"], 25.0, "the +25 look was the credible one")
        self.assertEqual(lat["yaw"]["deg"], 45.0)
        self.assertEqual(lat["yaw"]["deg"], chain_walk.END_TURN_MAX_DEG)
        self.assertEqual(self.turns(rig),
                         [90.0, 0.0, 335.0, 25.0, 0.0, 45.0, 55.0])

    def test_inside_LATERAL_TOL_PX_neither_a_yaw_nor_a_strafe(self):
        # 500 px inside the -25 frame is 500 - 492.5 = 7.5 px from the walking
        # heading: the look found the stop essentially straight ahead. The
        # yaw answers to the same gate the sidestep does.
        rig = self._rig(self._wps(),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=500.0),
                         None, Fix(k=3)], table_at=7)
        res = self._on(rig.go)
        lat = res["fixes"][1]["lateral"]
        self.assertNotIn("yaw", lat)
        self.assertNotIn("strafe", lat)
        self.assertEqual(rig.strafes(), [])
        self.assertEqual(self.turns(rig), [90.0, 0.0, 335.0, 25.0, 0.0, 10.0],
                         "the next push takes the plan's raw heading")

    def test_a_REGRESSION_drops_the_stop_yaw(self):
        """A look-back regression says the character is BEHIND where the loop
        thought -- which is the position the yaw was measured from -- and the
        branch rewinds the plan pointer to 0. The END TURN's yaw is dropped
        there for exactly this reason and says so in its own comment; without
        this the stop's offset would ride the recorded mid-chain headings from
        the start of the plan, which is the family GRAVEYARD closed.
        """
        rig = self._rig(self._wps(after=[(10.0, -0.35), (20.0, -0.35),
                                         (30.0, -0.35), (40.0, -0.35),
                                         (40.0, -0.35)]),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                         None, Fix(k=3), None, Fix(k=3)],
                        table_at=9, lookback=Fix(k=2, inliers=120))
        res = self._on(rig.go)
        acts = [f["action"] for f in res["fixes"]]
        turns = self.turns(rig)
        self.assertEqual(acts[:5], ["advanced", "turned-looked", "advanced",
                                    "regressed", "advanced"], acts)
        self.assertEqual(turns[5:8], [346.9, 356.9, 26.9],
                         "ANTI-VACUITY: the yaw was live on both pushes "
                         "before the regression (10 - 13.1, 40 - 13.1)")
        self.assertEqual(turns[8], 10.0,
                         "the RECORDED heading: the offset died with the "
                         "position that earned it (the leak commands 356.9)")

    def test_a_REGRESSION_BEHIND_EVERY_STOP_still_drops_the_yaw(self):
        """The regression clear on its own, with nothing else able to do it.

        The test above regresses to the stop's own index, so the plan pointer
        re-passes that stop on the next iteration and the SKIP clear would
        drop the yaw even if the `regressed` branch did not -- one rule
        masking the other, and a mutant that deletes the regression clear
        passes. Here the look-back lands at waypoint 0, BEHIND every stop in
        the plan: nothing is passed, the next target is a push, and the
        explicit clear is the only thing standing between the yaw and the
        recorded mid-chain headings the branch's own comment is about.
        """
        rig = self._rig(self._wps(after=[(10.0, -0.35), (20.0, -0.35),
                                         (30.0, -0.35), (40.0, -0.35),
                                         (40.0, -0.35)]),
                        [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                         None, Fix(k=3), None, Fix(k=3)],
                        table_at=9, lookback=Fix(k=0, inliers=120))
        res = self._on(rig.go)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:4], ["advanced", "turned-looked", "advanced",
                                    "regressed"], acts)
        self.assertEqual([f["k"] for f in res["fixes"]][3], 0,
                         "ANTI-VACUITY: the look-back landed BEHIND the stop, "
                         "so nothing but the regression clear can fire")
        turns = self.turns(rig)
        self.assertEqual(turns[5:8], [346.9, 356.9, 26.9],
                         "ANTI-VACUITY: the yaw was live on both pushes "
                         "before the regression")
        self.assertEqual(turns[8], 90.0,
                         "back to plan entry 0's RECORDED heading; the leak "
                         "commands 76.9")

    def test_a_SKIPPED_turn_only_stop_drops_the_yaw_TOO(self):
        """A stop the PLAN POINTER PASSES ends the yaw as surely as one the
        loop takes.

        The reproduction a skeptic built against the first draft of this patch
        (2026-09-08, agent_progress/closed-loop/stop_yaw). The clear above
        lives on the UNPACK of plan[pi], and a wide relocalisation jumps k over
        whole entries -- those are never unpacked. A yaw taken at the stop at
        chain 2 then rode EVERY push from chain 25 on, twenty waypoints past
        the stop that should have ended it, and that is the steering-while-
        walking family GRAVEYARD closed, arriving by the back door.

        The stop at 10 is genuinely skipped, not merely unverified: its own
        index never reaches chain.locate().
        """
        wps = [Wp(i) for i in range(30)]
        wps[2].lx = wps[2].ly = 0.0          # the stop that takes the yaw
        wps[10].lx = wps[10].ly = 0.0        # the stop the pointer JUMPS OVER
        ch = ScriptedWide(30,
                          [Fix(k=1),                        # push -> advanced
                           None,                            # the stop's frame
                           Fix(k=2, inliers=90, dx=235.0),  # the -25 look fits
                           None],                           # the +25 does not
                          default=None, lookback=None,
                          at_hint={4: [Fix(k=25, inliers=170)]})
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = self._on(always_turning, rig.go, time_cap=40.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:4], ["advanced", "turned-looked",
                                    "blind-advance", "relocalised"], acts)
        self.assertNotIn(10, ch.locate_calls,
                         "the stop at 10 must be SKIPPED, not visited and "
                         "left unverified -- otherwise this tests the clear "
                         "that already works")
        turns = self.turns(rig)
        self.assertEqual(turns[:9],
                         [10.0, 20.0, 355.0, 45.0, 20.0, 6.9, 16.9, 26.9,
                          260.0],
                         "to the push, the stop, both looks, back to the stop, "
                         "THE YAW (20 - 13.1), the two pushes that carry it "
                         "(30 - 13.1, 40 - 13.1) -- and then the relocalised "
                         "push at the plan's RAW 260.0. The leak commands "
                         "246.9 there and 266.9 for the rest of the walk.")
        self.assertNotIn(246.9, turns, turns)

    def test_a_jump_over_PUSHES_ALONE_keeps_the_yaw(self):
        """THE CONTROL for the test above, and the predicate it pins.

        The same walk with the stop at 10 taken out: the relocalisation now
        skips ten PUSH entries and nothing else, and the yaw SURVIVES. That is
        the rule as written -- a yaw dies at a turn-only stop, reached or
        passed, and nowhere else -- and it is deliberate: a wide fix says the
        character is further along than the loop thought, not that the camera
        is back on the recorded line. Only a stop re-measures that, against
        the recording's own frame at the recording's own heading.

        Without this the `not plan[pi][1]` half of the skip clear is untested
        and a mutant that drops it passes: in the test above the stop and the
        pushes beside it are skipped together, so clearing on either gives the
        same answer.
        """
        wps = [Wp(i) for i in range(30)]
        wps[2].lx = wps[2].ly = 0.0          # the only turn-only stop
        ch = ScriptedWide(30,
                          [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                           None],
                          default=None, lookback=None,
                          at_hint={4: [Fix(k=25, inliers=170)]})
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = self._on(always_turning, rig.go, time_cap=40.0)
        self.assertEqual([f["action"] for f in res["fixes"]][:4],
                         ["advanced", "turned-looked", "blind-advance",
                          "relocalised"])
        turns = self.turns(rig)
        self.assertEqual(turns[:9],
                         [10.0, 20.0, 355.0, 45.0, 20.0, 6.9, 16.9, 26.9,
                          246.9],
                         "the same walk as the skipped-stop test up to the "
                         "jump, and then 260 - 13.1: the yaw is STILL ON")
        self.assertNotIn(260.0, turns,
                         "no stop was passed, so nothing cleared it")

    def test_the_PAN_branch_takes_no_yaw_even_with_BOTH_flags_on(self):
        """A stop WITH a recorded run sidesteps as it always did.

        The pan and the look-around are the two arms of one if/elif and only
        the elif consults STOP_LOOK_YAW, so this holds by construction -- but
        untested it held for the wrong reason: a mutant that put the same yaw
        block inside the PAN branch passed all 179 tests (skeptic 1,
        2026-09-08), because no test had ever armed both flags at once. The
        pan's dx is measured against the run frame's OWN heading and needs no
        un-yawing, which is exactly why it is not a yaw.
        """
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35), (90.0, 0.0), (60.0, 0.0),
                                     (30.0, 0.0), (30.0, -0.35), (30.0, -0.35)],
                                    start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        ch = FakeChain(7, [Fix(k=1), None, None,
                           Fix(k=3, inliers=90, dx=80.0), Fix(k=5), Fix(k=6)],
                       default=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=9)
        old = chain_walk.STOP_PAN_FROM_RUN
        chain_walk.STOP_PAN_FROM_RUN = True
        try:
            res = self._on(rig.go)
        finally:
            chain_walk.STOP_PAN_FROM_RUN = old
        lat = res["fixes"][1]["lateral"]
        self.assertEqual(lat["pan_heading"], 60.0,
                         "ANTI-VACUITY: the PAN branch ran, not the "
                         "look-around")
        self.assertNotIn("yaw", lat)
        self.assertEqual(lat["strafe"], {"side": "right", "seconds": 0.111,
                                         "px": 80})
        self.assertEqual(self.turns(rig)[:5], [90.0, 30.0, 90.0, 60.0, 30.0],
                         "to the stop, the run's first and middle headings, "
                         "BACK TO THE STOP'S OWN HEADING -- no yaw on it")

    def test_the_LAST_stops_yaw_rides_the_tail_and_an_END_TURN_STACKS_on_it(self):
        """Nothing clears the yaw taken at the plan's LAST turn-only stop, and
        that is deliberate: there is no next stop to approach square, and the
        tail is the one place the loop is allowed to aim at the scene.

        Pinned in both directions because it was reasoned and never measured
        (skeptic 2, 2026-09-08). The END TURN reads the dx of a frame captured
        at the ALREADY-YAWED heading, so its own ddeg is a residual on top and
        the two accumulate without double-counting -- the same way two END
        TURNS accumulate. Every heading here is a literal.
        """
        wps = [Wp(0, 0.0)]
        rows = ([(0.0, -0.35)] * 15 + [(89.5, 0.0)]
                + [(89.5, -0.35), (95.0, -0.35), (95.0, -0.35)])
        for i, (h, ly) in enumerate(rows, start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        plan = chain_walk.plan_indices(wps)
        self.assertEqual(chain_walk._last_stop_index(plan), 5,
                         "ANTI-VACUITY: the stop at 16 IS the last one")
        ch = FakeChain(len(wps),
                       [Fix(k=1), Fix(k=4), Fix(k=7), Fix(k=10), Fix(k=13),
                        None,                              # the stop's frame
                        Fix(k=16, inliers=90, dx=235.0),   # the -25 look fits
                        None,                              # the +25 does not
                        Fix(k=17, inliers=120, dx=-600.0)],
                       default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = self._on(rig.go, time_cap=20.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:7], ["advanced"] * 5 + ["turned-looked",
                                                       "advanced"], acts)
        lat = res["fixes"][6]["lateral"]
        self.assertEqual(lat["end_turn"], -30.5,
                         "-600 px / 19.7 = -30.5 deg, the END TURN's own rule")
        self.assertEqual(round(lat["heading"], 1), 45.9,
                         "STACKED on the yawed 76.4, not on the recorded 89.5")
        self.assertEqual(rig.strafes(), [],
                         "neither correction sidesteps")
        turns = self.turns(rig)
        self.assertEqual(turns[:5], [0.0, 89.5, 64.5, 114.5, 89.5],
                         "the five pushes share the recorded 0.0 and TURN_SKIP "
                         "commands it once, then the stop and its two looks "
                         "and back to the stop's own heading")
        self.assertEqual(turns[5:], [76.4, 45.9, 51.4],
                         "THE YAW (89.5 - 13.1); then the END TURN on top of "
                         "it (76.4 - 30.5); then the next tail push carrying "
                         "BOTH (95.0 - 13.1 - 30.5)")
'''

# Only when patch43's LOST RESCUE is in the tree: a test for a branch that is
# not there would fail for the wrong reason.
RESCUE_TEST = '''
    def test_a_LOST_RESCUE_drops_the_stop_yaw(self):
        """The rescue backs the character out and re-aims it from a believed
        look, so a heading correction measured at a stop it has now left is
        refuted -- the same argument that branch already makes, in its own
        words, for the END TURN's yaw and for the one-shot turn-early.

        The chain is patch43's own (30 all-push waypoints, credible to 10,
        then blind) with ONE turn-only stop inserted at index 2, so the walk
        takes a yaw there and then goes blind, lost, and rescued.
        """
        wps = [Wp(i) for i in range(30)]
        wps[2].lx = wps[2].ly = 0.0          # the one turn-only stop
        ch = ScriptedWide(30,
                          [Fix(k=1), None, Fix(k=2, inliers=90, dx=235.0),
                           None] + [Fix(k=i) for i in range(3, 11)],
                          default=None, lookback=None,
                          at_hint={0: [Fix(k=13, inliers=170)]})
        ch.waypoints = wps
        rig = RescueRig(ch, table_at=None)
        res = self._on(rig.go, time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("rescued"), 1, acts)
        self.assertTrue(res["arrived"])
        turns = self.turns(rig)
        self.assertIn(16.9, turns,
                      "ANTI-VACUITY: the yaw was live on the pushes after the "
                      "stop (waypoint 3's recorded 30.0, minus 13.1)")
        self.assertEqual(turns[turns.index(140.0):], [140.0],
                         "the rescue re-aims to the plan's RAW heading and "
                         "every push after it keeps it: nothing turns to 126.9")
'''

NEW_TESTS = NEW_TESTS + (RESCUE_TEST if RESCUE_PRESENT else "") + "\n\n"

HARNESS_TESTS = '''    # --- the ARM, and WHICH flag it sets -----------------------------------

    def test_the_flag_name_is_read_from_argv_at_CALL_time(self):
        # A module-level knob a harness may redirect is resolved when it is
        # used, never captured in a default (10.18).
        self.assertEqual(chain_trials.arm_flag_name(["chain_trials.py"]),
                         chain_trials.DEFAULT_ARM_FLAG)
        self.assertEqual(chain_trials.DEFAULT_ARM_FLAG, "STOP_PAN_FROM_RUN")
        self.assertEqual(
            chain_trials.arm_flag_name(["chain_trials.py", "route", "--flag",
                                        "STOP_LOOK_YAW"]),
            "STOP_LOOK_YAW")
        with self.assertRaises(SystemExit):
            chain_trials.arm_flag_name(["chain_trials.py", "--flag"])

    def test_the_arm_sets_the_flag_the_run_NAMED(self):
        # THE MUTANT THIS EXISTS FOR: a child that sets STOP_PAN_FROM_RUN
        # whatever --flag says. Both arms would then run the shipped default
        # of the flag under test, and the A/B would report a clean interleave
        # of one arm against itself.
        old = (chain_walk.STOP_LOOK_YAW, chain_walk.STOP_PAN_FROM_RUN)
        chain_walk.STOP_LOOK_YAW = chain_walk.STOP_PAN_FROM_RUN = False
        try:
            name = chain_trials.apply_arm(
                chain_walk, self.log,
                env={chain_trials.PAN_ENV: "on",
                     chain_trials.ARM_FLAG_ENV: "STOP_LOOK_YAW"})
            self.assertEqual(name, "STOP_LOOK_YAW")
            self.assertTrue(chain_walk.STOP_LOOK_YAW)
            self.assertFalse(chain_walk.STOP_PAN_FROM_RUN,
                             "the pan flag must not move when it is not armed")
            self.assertEqual(self.logs[-1], "  arm: STOP_LOOK_YAW = True",
                             "the child's log names the flag it set")
            chain_trials.apply_arm(
                chain_walk, self.log,
                env={chain_trials.PAN_ENV: "off",
                     chain_trials.ARM_FLAG_ENV: "STOP_LOOK_YAW"})
            self.assertFalse(chain_walk.STOP_LOOK_YAW, "the OTHER arm")
        finally:
            chain_walk.STOP_LOOK_YAW, chain_walk.STOP_PAN_FROM_RUN = old

    def test_the_default_arm_flag_is_still_the_pan(self):
        # Every invocation written before --flag must behave exactly as it did.
        old = (chain_walk.STOP_LOOK_YAW, chain_walk.STOP_PAN_FROM_RUN)
        chain_walk.STOP_LOOK_YAW = chain_walk.STOP_PAN_FROM_RUN = False
        try:
            name = chain_trials.apply_arm(chain_walk, self.log,
                                          env={chain_trials.PAN_ENV: "on"})
            self.assertEqual(name, "STOP_PAN_FROM_RUN")
            self.assertTrue(chain_walk.STOP_PAN_FROM_RUN)
            self.assertFalse(chain_walk.STOP_LOOK_YAW)
        finally:
            chain_walk.STOP_LOOK_YAW, chain_walk.STOP_PAN_FROM_RUN = old

    def test_the_default_arms_ROW_LABEL_is_still_pan(self):
        # THE LABEL IS TEXT SOMEONE READS AND SOMETHING GREPS. `--flag` names
        # the attribute; it must not rename the rows of every batch written
        # before it, or an old chain_trials.json's `pan-on` and tonight's stop
        # comparing row for row and the log line a reader knows changes under
        # them. Same rule as `res["pan"]`, which this patch leaves alone.
        self.assertEqual(chain_trials.arm_label(chain_trials.DEFAULT_ARM_FLAG),
                         "pan")
        self.assertEqual(chain_trials.arm_label("STOP_PAN_FROM_RUN"), "pan")
        self.assertEqual(chain_trials.arm_label("STOP_LOOK_YAW"),
                         "STOP_LOOK_YAW", "a NAMED flag carries its own name")
        # ... and that main() uses it. main() cannot run offline (_assert_live,
        # console_lock, _harness.run_trial), so this half is a source check and
        # is honest about being one: it pins the three sites that write the
        # label and asserts the FLAG name reaches none of them.
        with open(os.path.join(_ROOT, "overnight", "chain_trials.py")) as fh:
            src = fh.read()
        self.assertIn("    label = arm_label(flag)", src)
        self.assertIn('row["arm"] = f"{label}-{arm}"', src)
        self.assertIn('r.get("arm") == f"{label}-{a}"', src)
        self.assertIn('log(f"  {label}-{a}: arrived', src)
        self.assertNotIn('f"{flag}-', src,
                         "the flag NAME is not the row label")

    def test_no_arm_in_the_environment_sets_nothing_at_all(self):
        old = (chain_walk.STOP_LOOK_YAW, chain_walk.STOP_PAN_FROM_RUN)
        chain_walk.STOP_LOOK_YAW = chain_walk.STOP_PAN_FROM_RUN = False
        try:
            self.assertIsNone(chain_trials.apply_arm(chain_walk, self.log,
                                                     env={}))
            self.assertFalse(chain_walk.STOP_PAN_FROM_RUN)
            self.assertFalse(chain_walk.STOP_LOOK_YAW)
            self.assertEqual(self.logs, [], "and says nothing")
        finally:
            chain_walk.STOP_LOOK_YAW, chain_walk.STOP_PAN_FROM_RUN = old

    def test_a_flag_naming_no_chain_walk_attribute_is_REFUSED(self):
        # setattr on a typo binds something nothing reads: 10.1's no-op that
        # logs like a change, in the one place where it costs a whole A/B.
        with self.assertRaises(SystemExit):
            chain_trials.apply_arm(
                chain_walk, self.log,
                env={chain_trials.PAN_ENV: "on",
                     chain_trials.ARM_FLAG_ENV: "STOP_LOOK_YWA"})

    def test_the_trial_sheet_still_reads_a_line_whose_ARM_IS_NOT_THE_PAN(self):
        # THE READER GOES WITH THE LABEL. trial_sheet is what the user's
        # standing rule runs on every failed trial, and its pattern knew only
        # "pan-": against a `--flag STOP_LOOK_YAW` batch it did not mis-parse
        # the lines, it REFUSED every one of them. Loaded BY PATH so this
        # needs no sys.path change and cannot pick up another module.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "trial_sheet_under_test", os.path.join(_ROOT, "tools",
                                                   "trial_sheet.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tail = ("k=204/205  it=41  pushes=33  seconds=104.9 "
                "(walk 84.0, setup 20.1)  failure=None")
        for label in ("STOP_LOOK_YAW-on", "STOP_LOOK_YAW-off", "pan-off"):
            m = mod.LINE_RE.match(f"[ 3] ARRIVED   {label} {tail}")
            self.assertIsNotNone(m, f"the reader refused {label}")
            self.assertEqual(m.group(2), "ARRIVED")
            self.assertEqual(m.group(3), label)
            self.assertEqual(int(m.group(4)), 204)
        # ... and a line with NO arm at all, which is every non-A/B batch.
        m = mod.LINE_RE.match(f"[ 3] FAILED    {tail}")
        self.assertIsNotNone(m)
        self.assertIsNone(m.group(3))
        self.assertEqual(int(m.group(4)), 204)

'''

edits_t = [
 ('''class EndTurnTowardTheDealer(unittest.TestCase):
''', NEW_TESTS + '''class EndTurnTowardTheDealer(unittest.TestCase):
'''),
 ('''    def test_a_chain_name_may_not_be_a_path(self):
''', HARNESS_TESTS + '''    def test_a_chain_name_may_not_be_a_path(self):
'''),
]

# ------------------------------------------------ every anchor, before any write
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a.split("\n")[0][:70], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a.split("\n")[0][:70], t.count(a))
for a, b in edits_h:
    assert h.count(a) == 1, ("chain_trials anchor", a.split("\n")[0][:70], h.count(a))
for a, b in edits_ts:
    assert ts.count(a) == 1, ("trial_sheet anchor", a.split("\n")[0][:70], ts.count(a))

# the load-bearing text of the change itself, asserted in the blocks about to
# be written, so a hand-edit that drops one cannot apply silently.
assert "STOP_LOOK_YAW = False\n" in CONSTANTS
assert "    stop_yaw = 0.0" in LOOPVAR
assert "        if not do_push:\n" in CLEAR_AT_STOP and "stop_yaw = 0.0" in CLEAR_AT_STOP
assert "        pi_serviced = pi\n" in ADVANCE
assert "            if pi > pi_serviced and not plan[pi][1]:\n" in ADVANCE
assert ADVANCE.count("stop_yaw = 0.0") == 1 and ADVANCE.count("pi += 1") == 1
assert "(end_yaw or stop_yaw)" in GUARD
assert "(heading + end_yaw + stop_yaw) % 360.0" in SUM
assert "if STOP_LOOK_YAW and abs(px) > LATERAL_TOL_PX:" in LOOK_NEW
assert "min(END_TURN_MAX_DEG,\n" in LOOK_NEW and "-END_TURN_MAX_DEG" in LOOK_NEW
assert LOOK_NEW.count("strafe(side * LATERAL_MAG, secs)") == 1
assert LOOK_NEW.count("turn_to(new_heading)") == 1
assert REGRESSION.count("stop_yaw = 0.0") == 1
assert "class StopLookYaw" in NEW_TESTS
assert "def test_a_REGRESSION_drops_the_stop_yaw" in NEW_TESTS
assert "def test_a_SKIPPED_turn_only_stop_drops_the_yaw_TOO" in NEW_TESTS
assert "def test_the_PAN_branch_takes_no_yaw_even_with_BOTH_flags_on" in NEW_TESTS
assert "def test_the_LAST_stops_yaw_rides_the_tail" in NEW_TESTS
assert "def test_the_default_arms_ROW_LABEL_is_still_pan" in HARNESS_TESTS
assert "def apply_arm(chain_walk, log, env=None):" in edits_h[2][1]
assert "def arm_label(flag):" in edits_h[2][1]
assert "    label = arm_label(flag)\n" in edits_h[5][1]
assert "LINE_RE = re.compile(" in edits_ts[0][1]

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)
for a, b in edits_h:
    h = h.replace(a, b)
for a, b in edits_ts:
    ts = ts.replace(a, b)
ast.parse(c)
ast.parse(t)
ast.parse(h)
ast.parse(ts)
open(C, "w").write(c)
open(T, "w").write(t)
open(H, "w").write(h)
open(TS, "w").write(ts)
print("patch44 applied to", ROOT)
print("  the LOST RESCUE's stop_yaw reset:",
      "applied (patch43 is in this tree)" if RESCUE_PRESENT
      else "SKIPPED -- patch43 is NOT in this tree, so there is no rescue "
           "branch to reset. Apply patch43 first, then re-check.")
