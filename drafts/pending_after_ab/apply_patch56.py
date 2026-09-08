"""patch56: BLIND_LOOK_AROUND -- LOOK instead of pushing blind AGAIN.

THE USER SAW IT FIRST, watching the stream: "The bar area seems to be an area
the player struggles to detect and know when to turn towards the jukebox. This
causes them to ram into the bar and waste time and potentially not finish runs."
And then: "The player also walks into the wall behind Wanda. they also walk into
wanda. the trigger to turn isn't being met." Their principle: "take a move, take
a screenshot and determine if there is needed error correction."

WHERE THE DAMAGE ACTUALLY IS -- NOT AT THE TURN. Over 58 walks the jukebox turn
at waypoint 166 was serviced on a CREDIBLE fit (>= FIX_MIN_INLIERS) in 57, with
a median of ZERO blind iterations before it. The loss comes AFTER it.

THE MOTIVATING FAILURE, READ FROM ITS OWN JOURNAL RATHER THAN FROM ITS SUMMARY
LINE. An earlier draft of this docstring quoted the trial's failure string --
"lost at k=169 of 204: 13 iterations with no credible fix after 6 blind
advances" -- and narrated it as "pushed forward SIX times into geometry". A
skeptic checked the per-iteration rows (overnight/chain_trials.log:1085-1133)
and the six is not an observed count. The real sequence is:

    it 39   the 166 stop taken `turned-unverified` (7 inliers, under
            FIX_MIN_INLIERS) -- so `unverified_turn` was set True
    it 40   blind-advance          (blind 1)
    it 41   blind-advance          (blind 2)   <- and that is ALL of them
    it 42   `weak` (6 inliers): a stall, not a blind push
    it 43-53  miss / escape:jump / escape:back / escape:left -- the ladder
    it 54   rescue-failed, then LOST

TWO blind advances, not six. The "6" is chain_walk.py's own hardcoded
`{BLIND_MAX}` in the LOST failure string, printed whatever cap `_blind_cap`
actually enforced -- a PRE-EXISTING DOCUMENTATION BUG in chain_walk.py, not
something this patch introduces and deliberately NOT fixed here: that string is
what the harnesses and readers parse and the A/B is running on it right now.
Worth its own patch at a boundary.

AND THE CAP THAT ACTUALLY BOUND THAT TRIAL WAS THE `unverified_turn` ONE.
`_blind_cap` returns END_BLIND_MAX (2) when `pi >= len(plan) - END_TAIL_TARGETS`
OR `unverified_turn`. At k=169 of 204, with targets ~2 apart, pi was some
sixteen entries from the end -- not the tail. It was the unverified turn at it39
that cut the budget to two. So this trial is the 1 of 58 where the 166 turn was
NOT serviced credibly, and in the COMMON case (57 of 58) the operative cap in
that stretch is BLIND_MAX (6), not END_BLIND_MAX. Both of those corrections are
carried into the constant's justification below, because the earlier draft's
"the bar sits inside END_BLIND_MAX's tail window" was simply wrong about where
that window is.

THE MECHANISM IS UNCHANGED BY ALL OF THAT, and is the point. When the sensor
cannot say where it is, the loop DEAD-RECKONS FORWARD: blind pushes up to the
cap, then LOST_MAX iterations of misses and escape rungs, then lost. Every blind
push drives the character further into whatever it could not see, and if it is
already jammed against the bar, a wall or Wanda, the next frame is the SAME
wall -- so the blindness is self-sustaining. Pushing cannot end it.

WHY THE WIDE SEARCH ALREADY THERE CANNOT FIX THIS. From the first blind push the
loop runs `_strong_ahead`, which re-matches THE SAME FRAME against WIDE_AHEAD
(60) more waypoints. That answers "am I further along than I thought"; it cannot
answer anything when the frame itself is a wall. No amount of re-matching a wall
finds the route. What is missing is a PHYSICAL look: turning the camera for a
DIFFERENT view -- exactly what the loop already does at an unverified stop
(STOP_LOOK_DEG) and what the lost rescue does, far too late, after the whole
blind budget and thirteen more iterations are gone.

WHAT IT DOES. With the flag on, on the BLIND_LOOK_AFTER'th consecutive blind
push the iteration LOOKS INSTEAD OF PUSHING: it turns to each of STOP_LOOK_DEG
about the heading it was about to walk, captures, and runs the SAME
`_strong_ahead` forward search on each new view. A strong fit moves k and the
walk carries on (`relocalised-look`, which behaves downstream exactly like the
wide search's `relocalised` because it starts with the same word). Nothing found
is recorded as `blind-look` and the loop pushes on next iteration as before.
The character is not moved either way.

HOW IT COMPOSES WITH THE RULES IT SITS BETWEEN, since a rule that fights them is
worse than no rule:

  * THE WIDE SEARCH is not replaced -- it IS the belief test here. `_strong_ahead`
    is called unchanged, on the looked frames instead of the forward one, so the
    gate (STRONG_MIN_INLIERS, above the live census's wrong-place MAXIMUM) and
    the span (WIDE_AHEAD) are the same ones the blind path already trusts. The
    forward search still runs on the next pushed frame.
  * THE LOST RESCUE is untouched and still last. It fires at lost >= LOST_MAX,
    which this rule cannot reach or spend: a look increments neither `lost` nor
    `blind`. The rescue also looks BACKWARD over the whole chain from
    `last_cred_k` and pays a step back for it; this looks only FORWARD and moves
    nothing, so it is the cheap version tried first, and the expensive one still
    runs if it fails.
  * TURN-EARLY owns the case near a stop. `_blind_cap` cuts the blind budget to
    ONE push when the last credible scale is at a wall and a turn-only stop is
    within NEAR_STOP_TARGETS, so `blind` never reaches 2 there and this rule
    cannot fire in front of turn-early.

WHY IT IS NOT A GRAVEYARD SHAPE. GRAVEYARD's summary is that every failed
navigation change MOVED the character and both survivors move nothing. This
REPLACES a blind push with a camera turn: it moves the character LESS, not more.
It is the same family as DOOR_STOP_EXTRA_PUSH and BAR_STOP_EARLY_TURN -- change
WHEN the loop turns rather than add motion -- and the door step is the project's
most recent measured win (10/10 against 9/10, decided by the fit scale at its
stop, not by arrival).

THE CONSTANTS ARE BORROWED, NOT INVENTED -- no new physical quantity:

    BLIND_LOOK_AFTER = END_BLIND_MAX (2)
        The loop's own answer to "how many blind pushes before another one is
        not worth the risk", taken from the ONE place it has already decided
        that question: past the last stop, and after an unverified turn --
        which is exactly the state the motivating failure was in when it spent
        its two. NOTE, corrected from an earlier draft: in the COMMON case at
        k=166-180 the operative cap is BLIND_MAX (6), so this does NOT mean
        "the budget runs out here". It means the look happens on the second
        blind push with FOUR pushes still in hand -- a look that finds nothing
        costs the walk none of its dead-reckoning, which is the whole reason
        the trigger is small rather than "when the budget is nearly gone".
    BLIND_LOOK_MAX   = 1, PER BLIND STRETCH
        LOST_RESCUE_MAX's value. Its SCOPE is LOST_MAX's own comment, "One full
        ladder per blockage": the budget resets when `blind` returns to 0, i.e.
        when a credible fit ends the stretch. An earlier draft made it per WALK
        and defended that in this docstring; a skeptic pointed out the hole,
        and it is a real one -- a walk that goes blind for two pushes ANYWHERE
        earlier would spend the only look there and reach the post-166 stretch
        with none, silently degrading to pre-patch behaviour for that trial
        while still counting as an on-arm trial. The rejected reason ("it needs
        `blind = 0` mirrored at six sites") was wrong: the reset reads `blind`,
        which every one of those six sites already zeroes, so it is ONE line.
        Note what that scope means for the bound: only a FAILED look spends
        budget, because a found one sets `blind = 0` and hands it straight
        back. So the rule can look many times in a walk -- but never twice for
        one blind run without finding the route in between, which is the
        property that matters and the one the loop's other rungs have too.
    the angles    = STOP_LOOK_DEG (-25, +25)
    the belief    = _strong_ahead -> STRONG_MIN_INLIERS (165), WIDE_AHEAD (60)

IT CANNOT LOOK TWICE WITHOUT PUSHING IN BETWEEN. The trigger is
`blind >= after + looks`, not `blind >= after`: each look already taken in this
stretch raises the bar by one, and only a blind PUSH raises `blind`. With the
shipped BLIND_LOOK_MAX = 1 that is the same condition -- but at any larger cap
the plain form fires on consecutive iterations with no new information between
them (verified: at after=1, cap=4 the plain form gives four identical looks at
the same k with `blind` reading [1,1,1,1]; this form gives [1,2,3,4], each after
a push). A bound that only holds at one value of its own constant is not a
bound.

WHY THE LOOKED FRAMES ARE **NOT** GIVEN AN at_table() CHECK, which is the one
place this block knowingly departs from "every capture is checked". Neither of
the two look-arounds it copies checks its frames either -- the stop look-around
(chain_walk.py ~1620) and the lost rescue (~2111) both capture, `_save` and
`locate` without a prompt check -- so this is the machinery's existing shape,
not a new hole. Adding it HERE ALONE would be worse than leaving it: it would
give the on-arm an arrival path (a prompt seen only because the camera was
turned 25 degrees) that the off-arm never has, and the A/B's primary outcome is
arrival. The right fix is one patch adding the check to all three sites, on a
day when no A/B depends on the difference.

IT SHIPS OFF. `overnight/chain_trials.py --arms off,on --flag BLIND_LOOK_AROUND`
is the measurement.

THE PRE-REGISTERED INSTRUMENT, because arrival may tie the way the door step's
nearly did:

  PRIMARY: the length of the blind run -- the number of consecutive
  `blind-advance` journal rows in the stretch that begins past waypoint 166 --
  should be SHORTER on the on-arm, and the fraction of those stretches ending in
  a credible fit rather than in `lost at k=1xx` should be HIGHER. Computed from
  BOTH arms' journals by the same code, because the off-arm records
  `blind-advance` rows too.

  SECONDARY, and the one that refutes the mechanism outright if it reads zero:
  of the on-arm's `blind_look` rows, how many carry `action ==
  "relocalised-look"` -- how often turning the camera found route the forward
  frame could not.

  MANDATORY WITH BOTH, and the skeptic's point: report WHERE each firing
  happened, not just whether it happened. Every look row carries `from_k` and
  its `iteration`, and `blind_look.in_stretch` says which look of its stretch it
  was. A firing at from_k well below BAR_STOP_INDEX (166) is a look spent
  somewhere else, and the post-166 numbers above must be credited only to
  trials that actually looked there. The per-stretch budget makes an early
  firing cheap rather than disqualifying -- but "the mechanism fired" and "the
  mechanism fired where the observation is about" are different claims and the
  report states both.

WHAT THE `cleared` FIELD IS FOR. On a found look the block zeroes `blind`,
`lost`, `misses` and `stalls`, mirroring the forward search's `relocalised`
field for field. Only `blind = 0` is reachable-and-load-bearing offline, and it
is pinned by its downstream effect (a found look hands back a FULL blind budget
-- BLIND_MAX more advances, not one fewer). The other three are, as far as the
code can be read, ALWAYS ALREADY ZERO at a firing: a look fires the first time
`blind >= BLIND_LOOK_AFTER` with budget, reaching that count needs that many
consecutive `blind-advance`s, each of which zeroes `misses` and `stalls`,
starting from `blind == 0` -- and every branch that sets `blind = 0` also sets
`lost = 0`. That is an argument, not a measurement, and the one corner it does
not cover is a `_blind_cap` that SHRINKS mid-stretch while the look is blocked
by `do_push`. So rather than assert the argument in a comment, the row records
the three values the look cleared: if any live journal ever shows a non-zero
`cleared`, the corner is real and those three assignments are doing work. A
skeptic deleted all three in a scratch copy and the whole suite stayed green;
that is expected and is why the check is a live instrument instead of a test.

A READER CAVEAT, recorded rather than fixed here (this patch touches two files).
`tools/live_gate_census.py:is_iteration_fit_row` counts a row as an iteration's
own in-window fit when it carries an iteration number and a fit and is not
`door-step`. A `relocalised-look` row qualifies, and its fit is a WIDE one --
but so is the existing `relocalised` row from the forward search, which that
census already counts, so this adds nothing new to the population. If the flag
ships ON, add `relocalised-look` to that exclusion the way `door-step` was
added. `tools/trial_sheet.py:row_for` is unaffected: a blind-look iteration
records exactly ONE row.

Applies to: chain_walk.py, tests/routing/test_chain_walk.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch56.py [ROOT]
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read()
t = open(T).read()

edits_c = [
 # ---------------------------------------------------------------- constants
 ('''BAR_STOP_INDEX = 166''',
  '''BAR_STOP_INDEX = 166
# LOOK INSTEAD OF PUSHING BLIND AGAIN (patch56). The user, watching the stream:
# "the bar area seems to be an area the player struggles to detect and know when
# to turn towards the jukebox. This causes them to ram into the bar"; and "they
# also walk into the wall behind Wanda. they also walk into wanda."
#
# The turn itself is NOT the problem -- over 58 walks the stop at 166 was
# serviced on a credible fit in 57, median ZERO blind iterations before it. The
# loss is AFTER it. Read from its own rows rather than its summary line, the
# motivating failure (chain_trials.log:1085-1133) is: the 166 stop taken
# `turned-unverified` on 7 inliers, TWO blind advances (the cap was 2 because
# that unverified turn set it, not because the tail did), a weak fit, then
# eleven iterations of misses and escape rungs, then lost. The "6 blind
# advances" in its failure string is this file's own hardcoded {BLIND_MAX}
# below and is not a count of anything -- a separate, pre-existing bug.
#
# Two blind pushes were still two pushes further into whatever it could not
# see, and a frame of wall stays a frame of wall however many waypoints
# `_strong_ahead` re-matches it against. Turning the camera is the one cheap
# thing that changes the FRAME, and the loop already knows how -- at an
# unverified stop and inside the lost rescue.
#
# On the BLIND_LOOK_AFTER'th consecutive blind push the iteration looks instead
# of pushing: STOP_LOOK_DEG about the heading it was going to walk, the same
# `_strong_ahead` on each view, and the walk carries on from a strong one. It
# moves the character LESS than the push it replaces, which is the opposite of
# every change in GRAVEYARD.
#
# Ships OFF; `--flag BLIND_LOOK_AROUND` measures it. Pre-registered instrument:
# the number of consecutive `blind-advance` rows in the stretch past waypoint
# 166 (shorter on the on-arm); how many `blind_look` rows carry
# `relocalised-look` (zero refutes the mechanism outright); and WHERE each
# firing happened -- `from_k`, reported per firing, because a look spent far
# from 166 is not evidence about 166.
BLIND_LOOK_AROUND = False
# HOW MANY CONSECUTIVE BLIND PUSHES BEFORE THE FIRST LOOK. Borrowed, not
# invented: END_BLIND_MAX is the loop's own answer to "how many blind pushes
# before another is not worth the risk", from the one place it has already
# decided that -- past the last stop, and after an unverified turn, which is
# the state the motivating failure was in. It does NOT mean the budget runs out
# here: in the common case that stretch is capped at BLIND_MAX (6), so this
# looks on the second blind push with four still in hand. A look that finds
# nothing therefore costs the walk none of its dead-reckoning, which is why the
# trigger is small rather than "when the budget is nearly gone".
# (Near a wall and a stop `_blind_cap` allows only ONE blind push, so `blind`
# never reaches this and TURN-EARLY still owns that case, untouched.)
BLIND_LOOK_AFTER = END_BLIND_MAX
# ... and the BOUND: LOST_RESCUE_MAX's value, with LOST_MAX's own scope -- "One
# full ladder per blockage". PER BLIND STRETCH, not per walk: the count resets
# when `blind` returns to 0, which is exactly when a credible fit ended the
# stretch. Per WALK was the first draft and it has a hole -- a walk that went
# blind for two pushes ANYWHERE earlier would spend its only look there and
# reach the bar with none, silently behaving as the off arm while still being
# scored as an on-arm trial. The reset reads `blind`, which every branch that
# ends a stretch already zeroes, so it is one line and not the six-site mirror
# that argument assumed.
BLIND_LOOK_MAX = 1
# The journal's name for a look that found nothing, and for one that did. The
# second starts with "relocalised" ON PURPOSE: `PROGRESS_ACTIONS` is tested with
# str.startswith, so it resets the escape ladder and re-arms turn-early exactly
# as the forward search's `relocalised` does, while still being greppable apart
# from it. A no-op path and a working path must not have identical output
# (10.1), which is why the failing look records a row at all.
BLIND_LOOK_ACTION = "blind-look"
BLIND_LOOK_FOUND_ACTION = "relocalised-look"'''),
 # ---------------------------------------------------------------- predicate
 ('''def _near_stop(pi, plan):''',
  '''def _blind_look_due(blind, looks, after, cap, pushing, at_end):
    """Should this iteration LOOK AROUND instead of pushing blind again?

    Pure, so every guard can be driven directly. patch55 learned this the
    expensive way: two of its guards were unreachable through anything the plan
    builder emits, so mutants deleting them survived a walk-level test. Two of
    the four here are the same shape -- `after >= 1` and `at_end` are hard or
    impossible to reach through a scripted walk -- and they are held to their
    stated meaning here instead.

    `after` and `cap` are PARAMETERS, never module-level defaults: a knob
    captured in a default cannot be redirected by a test or an A/B arm (10.18).

      after >= 1   a zero trigger would look before the walk has gone blind at
                   all, on a healthy walk, every iteration. `blind >= 0` is
                   true of every walk, so this one is NOT redundant.
      pushing      at a TURN-ONLY stop the stop's own look-around already runs,
                   and two look-arounds in one iteration would fight.
      not at_end   past the plan there is nothing ahead to find, the prompt
                   check runs every iteration anyway, and turning the camera
                   beside the dealer's table is where the walk can least afford
                   to spend an iteration.
      looks < cap  the budget for THIS blind stretch.

    `blind >= after + looks`, NOT `blind >= after`: A LOOK THAT FINDS NOTHING
    TOUCHES NEITHER `blind` NOR `k`, so the plain form is satisfied again on the
    very next iteration and the rule fires in a tight loop -- the same
    manoeuvre, the same k, the same heading, with no push and therefore no new
    information between attempts. Measured in a scratch copy at after=1, cap=4:
    the plain form gives four consecutive looks whose recorded `blind` reads
    [1, 1, 1, 1]; this form gives [1, 2, 3, 4], each separated by a blind push.
    It is dormant at the shipped cap of 1 -- which is exactly why it is written
    here rather than trusted to the cap: a bound that only holds at one value of
    its own constant is not a bound.

    A FIFTH CLAUSE WAS WRITTEN AND DELETED: `cap >= 1`, to make a zero cap
    disable the rule. `looks < cap` already refuses at cap 0 for every
    non-negative `looks`, so it could not change an answer -- its mutant
    survived the whole suite, which is how it was found. A guard that cannot
    fire is the shape this project keeps finding, so it is gone and the test
    that pins the BEHAVIOUR (cap 0 disables) stays.
    """
    return (after >= 1
            and bool(pushing)
            and not at_end
            and looks < cap
            and blind >= after + looks)


def _near_stop(pi, plan):'''),
 # ------------------------------------------------------------- the counter
 ('''    bar_turned_early = False    # the once-per-walk latch for''',
  '''    blind_looks = 0             # BLIND_LOOK_AROUND firings in the CURRENT
                                # blind stretch (the budget; reset with `blind`)
    blind_looks_total = 0       # ... and over the whole walk, for the report
    bar_turned_early = False    # the once-per-walk latch for'''),
 # ----------------------------------------------------------------- the block
 ('''        turned = False''',
  '''        # LOOK AROUND INSTEAD OF PUSHING BLIND AGAIN (BLIND_LOOK_AROUND).
        #
        # It sits HERE, before the turn and the push, because that is the only
        # place a push can be replaced: `blind` is not known until after the
        # push and the capture, so a rule that reads it inside the sensor branch
        # can only ever ADD a look to an iteration that already pushed. This one
        # reads the PREVIOUS iterations' `blind` and ends in `continue`, so the
        # iteration turns twice, captures twice, turns back, and travels NOWHERE.
        #
        # WHAT CHANGES IN THE EVENT LIST, stated because getting this wrong is
        # how a test passes for nobody: where the off-arm has (turn, push,
        # capture), the on-arm has (turn -25, capture, turn +25, capture, turn
        # back). No push. The character does not move; only the camera does.
        #
        # The belief is `_strong_ahead`, unchanged -- the SAME forward search the
        # blind path already runs, on a DIFFERENT view. That is the whole idea:
        # re-matching a frame of wall against sixty more waypoints cannot find
        # the route, and turning the camera is the cheapest thing that changes
        # the frame. It returns only fits at or above STRONG_MIN_INLIERS, which
        # the live gate census puts above the wrong-place MAXIMUM, so the first
        # direction that fits is believed and the second is not paid for.
        #
        # Neither `blind` nor `lost` is spent by a look, so the blind budget,
        # the escape ladder and the LOST RESCUE below are all reachable exactly
        # as before if it finds nothing. `blind_looks` is the bound.
        #
        # THE LOOKED FRAMES GET NO at_table() CHECK, and that is deliberate:
        # neither look-around this copies checks its own frames either, and
        # adding it HERE ALONE would hand the on-arm an arrival path the off-arm
        # does not have, in the A/B whose primary outcome is arrival. One patch,
        # all three sites, on a day nothing depends on the difference.
        if BLIND_LOOK_AROUND and blind == 0 and blind_looks:
            # THE BUDGET IS PER BLIND STRETCH, NOT PER WALK. `blind == 0` is
            # the loop's own definition of "the sensor has seen something
            # credible since": every branch that ends a blind stretch --
            # `relocalised`, `regressed`, `advanced`, and this rule's own found
            # path -- sets it. Without this line the first two-push blind run
            # anywhere in the walk spends the only look, and the stretch this
            # rule was built for gets none while the trial still counts as an
            # on-arm trial. One line, because they all zero `blind` already.
            blind_looks = 0
        if (BLIND_LOOK_AROUND and heading is not None
                and _blind_look_due(blind, blind_looks, BLIND_LOOK_AFTER,
                                    BLIND_LOOK_MAX, do_push, at_end)):
            blind_looks += 1
            blind_looks_total += 1
            res["blind_looks"] = blind_looks_total
            base = heading
            best = None                  # (degrees, inliers, fix)
            looks = 0
            for ddeg in STOP_LOOK_DEG:
                turn_to((base + ddeg) % 360.0)
                img2 = capture()
                looks += 1
                _save(shots, iteration, k, img2, log,
                      suffix=f"_blindlook{int(ddeg):+d}")
                f2 = _strong_ahead(chain, img2, k, n)
                if f2 is not None:
                    best = (ddeg, getattr(f2, "inliers", 0) or 0, f2)
                    break            # already believed; see STRONG_MIN_INLIERS
            # Back to the heading this iteration was going to walk, so the next
            # iteration's turn is the no-op TURN_SKIP_DEG makes it and the push
            # resumes on exactly the line it would have.
            turn_to(base)
            last_cmd = base
            look_row = {"looks": looks, "blind": blind, "from_k": k,
                        "to_k": None, "in_stretch": blind_looks,
                        # WHAT THIS LOOK CLEARED, read BEFORE clearing it. The
                        # argument says these three are always already zero at
                        # a firing (a look fires the first time `blind` reaches
                        # its trigger, which took that many `blind-advance`s,
                        # each of which zeroes misses and stalls, from a
                        # `blind == 0` that every producer pairs with
                        # `lost == 0`). The one corner it does not cover is a
                        # `_blind_cap` that shrinks mid-stretch while the look
                        # is blocked by `do_push`. An argument is not a
                        # measurement, so the row carries the values: a
                        # non-zero `cleared` in any live journal says the
                        # corner is real and those assignments do work.
                        "cleared": {"lost": lost, "misses": misses,
                                    "stalls": stalls},
                        "deg": None if best is None else best[0],
                        "inliers": None if best is None else best[1]}
            if best is not None:
                _, _, f2 = best
                k = min(int(f2.k), n - 1)
                last_cred_k = k
                look_row["to_k"] = k
                # Exactly the forward search's `relocalised` reset, field for
                # field, because it is the same evidence at the same gate --
                # and, like it, this does NOT clear end_yaw or stop_yaw: the
                # character has not moved, so no correction measured at a
                # position is refuted. The pointer re-derives from k at the top
                # of the next iteration, and the stops it steps over drop their
                # yaw there, as they do for every wide jump.
                blind = 0
                lost = 0
                misses = 0
                stalls = 0
                action = BLIND_LOOK_FOUND_ACTION
            else:
                action = BLIND_LOOK_ACTION
            record({"iteration": iteration, "k": k, "target": target_k,
                    "fix": _fix_row(None if best is None else best[2]),
                    "action": action, "lateral": None,
                    "blind_look": look_row, "at_end": at_end,
                    "seconds": round(now() - it_t0, 2),
                    "elapsed": round(now() - t0, 2)})
            if best is not None:
                log(f"    it {iteration:3d}  k={look_row['from_k']:3d} -> "
                    f"{target_k:3d}  {action}: {look_row['blind']} blind "
                    f"push(es) in, looked {looks} time(s) about {base:.1f} "
                    f"instead of pushing; {look_row['inliers']} inliers at "
                    f"{look_row['deg']:+.0f} deg put k at {k}")
            else:
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"{action}: {blind} blind push(es) in, looked {looks} "
                    f"time(s) about {base:.1f} instead of pushing; nothing at "
                    f"{STRONG_MIN_INLIERS}+ inliers")
            continue

        turned = False'''),
]

NEW_TESTS = '''
class BlindLookAround(unittest.TestCase):
    """patch56: LOOK instead of pushing blind AGAIN.

    The user, watching the stream: "the bar area seems to be an area the player
    struggles to detect and know when to turn towards the jukebox. This causes
    them to ram into the bar"; and "they also walk into the wall behind Wanda.
    they also walk into wanda."

    The turn at 166 is not the problem -- 57 of 58 walks serviced it on a
    credible fit. The loss is after it. Read from its own journal rows rather
    than its summary line, the motivating failure is: the stop taken
    `turned-unverified` on 7 inliers, TWO blind advances, a weak fit, then
    eleven iterations of misses and escape rungs. (Its failure string says
    "after 6 blind advances"; that 6 is chain_walk's own hardcoded BLIND_MAX
    literal, not a count -- a separate pre-existing bug, left alone because the
    harnesses parse that string.)

    THE THING THAT ACTUALLY CHANGES, and it is not the push count: where the
    off-arm's iteration is (turn, push, capture), the on-arm's is (turn -25,
    capture, turn +25, capture, turn back) and NO push. A sibling patch today
    shipped a first test asserting a push DISAPPEARED from the walk; it does
    not, because the loop still has to travel. Here the assertion is on the
    ITERATION'S OWN events, which is where the substitution really happens.

    THE CHAIN: 40 waypoints, one heading, a walking stick on every row, so
    plan_indices emits pushes only and the walk is one long blind stretch. The
    fake sensor answers None to everything, and `wide` is the single knob that
    decides what a look (or the forward search) finds.
    """

    N = 40
    HEADING = 90.0

    def _wps(self):
        wps = []
        for i in range(self.N):
            w = Wp(i, self.HEADING)
            w.lx = 0.0
            w.ly = 0.0 if i == 0 else -0.35
            wps.append(w)
        return wps

    def _rig(self, wide=None, wps=None, cls=FakeChain, fixes=(),
             lookback="script"):
        wps = self._wps() if wps is None else wps
        ch = cls(len(wps), fixes, default=None, wide=wide, lookback=lookback)
        ch.waypoints = wps
        return Rig(ch, table_at=None)

    def _run(self, on, after=1, cap=1, **kw):
        """One walk at one arm. Returns (rig, result)."""
        keep = (chain_walk.BLIND_LOOK_AROUND, chain_walk.BLIND_LOOK_AFTER,
                chain_walk.BLIND_LOOK_MAX)
        (chain_walk.BLIND_LOOK_AROUND, chain_walk.BLIND_LOOK_AFTER,
         chain_walk.BLIND_LOOK_MAX) = on, after, cap
        try:
            rig = self._rig(**kw)
            return rig, rig.go(time_cap=200.0)
        finally:
            (chain_walk.BLIND_LOOK_AROUND, chain_walk.BLIND_LOOK_AFTER,
             chain_walk.BLIND_LOOK_MAX) = keep

    @staticmethod
    def _looks(res):
        return [r for r in res["fixes"] if "blind_look" in r]

    @staticmethod
    def _actions(res):
        return [r.get("action") for r in res["fixes"]]

    # ---- what ships -------------------------------------------------------

    def test_it_ships_OFF_and_every_constant_is_a_borrowed_one(self):
        # Literals, never the constant guarding itself (10.11).
        self.assertIs(chain_walk.BLIND_LOOK_AROUND, False)
        self.assertEqual(chain_walk.BLIND_LOOK_AFTER, 2)
        self.assertEqual(chain_walk.BLIND_LOOK_AFTER, chain_walk.END_BLIND_MAX)
        self.assertEqual(chain_walk.BLIND_LOOK_MAX, 1)
        self.assertEqual(chain_walk.BLIND_LOOK_MAX, chain_walk.LOST_RESCUE_MAX)
        self.assertEqual(chain_walk.BLIND_LOOK_ACTION, "blind-look")
        self.assertEqual(chain_walk.BLIND_LOOK_FOUND_ACTION, "relocalised-look")
        # It invents NO physical constant: the angles, the gate and the span
        # are the ones the stop look-around and the forward search already use.
        self.assertEqual(chain_walk.STOP_LOOK_DEG, (-25.0, 25.0))
        self.assertEqual(chain_walk.STRONG_MIN_INLIERS, 165)
        self.assertEqual(chain_walk.WIDE_AHEAD, 60)

    def test_the_found_action_still_counts_as_PROGRESS(self):
        # It is spelled "relocalised-look" so it resets the escape ladder and
        # re-arms turn-early exactly as the forward search's own relocalisation
        # does -- PROGRESS_ACTIONS is tested with str.startswith -- while still
        # being greppable apart from it in a journal.
        self.assertTrue(
            chain_walk.BLIND_LOOK_FOUND_ACTION.startswith(
                chain_walk.PROGRESS_ACTIONS))
        self.assertNotIn(chain_walk.BLIND_LOOK_FOUND_ACTION,
                         chain_walk.UNEVIDENCED_ACTIONS)
        self.assertNotEqual(chain_walk.BLIND_LOOK_FOUND_ACTION, "relocalised")
        # ... and a look that found NOTHING is not progress.
        self.assertFalse(
            chain_walk.BLIND_LOOK_ACTION.startswith(chain_walk.PROGRESS_ACTIONS))

    # ---- the flag off changes nothing -------------------------------------

    def test_OFF_the_walk_is_byte_for_byte_what_it_is_today(self):
        off_rig, off_res = self._run(False, after=1)
        # Nothing of this rule reaches the journal or the result.
        self.assertEqual(self._looks(off_res), [])
        self.assertNotIn("blind_looks", off_res)
        # ... and the machinery is inert when it is ON but not DUE, which is
        # the only way to show offline that the TRIGGER, not the flag alone,
        # is doing the gating: a mutant dropping the blind-count clause fails
        # here.
        never_rig, never_res = self._run(True, after=10 ** 6)
        self.assertEqual(never_rig.events, off_rig.events)
        self.assertEqual(self._looks(never_res), [])
        # ANTI-VACUITY: the walk this compares must actually go blind and push,
        # or two identical empty event lists would pass.
        self.assertGreater(off_rig.count("push"), 3)
        self.assertIn("blind-advance", self._actions(off_res))

    # ---- the substitution -------------------------------------------------

    def test_ON_the_iteration_LOOKS_and_makes_NO_push(self):
        # THE ASSERTION IS ON THE FIRST DIVERGENCE BETWEEN THE ARMS, not on
        # "does a +-25 turn appear anywhere": the LOST RESCUE at the end of
        # this walk turns the same two angles about the same heading, so
        # searching the whole event list finds ITS turns in BOTH arms and an
        # `assertNotIn` there passes for nobody. Up to the first difference the
        # two arms are identical by construction; AT it the off-arm pushes and
        # the on-arm looks. That is the substitution, exactly.
        off_rig, _ = self._run(False, after=1)
        on_rig, on_res = self._run(True, after=1, cap=1)
        self.assertEqual(len(self._looks(on_res)), 1, "one firing at cap 1")
        i = next((j for j, (a, b) in enumerate(zip(off_rig.events,
                                                   on_rig.events)) if a != b),
                 None)
        self.assertIsNotNone(i, "the arms must diverge at all")
        self.assertEqual(off_rig.events[:i], on_rig.events[:i])
        self.assertEqual(off_rig.events[i][0], "push",
                         "what the off-arm does here is a blind push")
        window = on_rig.events[i:i + 5]
        self.assertEqual([e[0] for e in window],
                         ["turn", "capture", "turn", "capture", "turn"],
                         f"the on-arm turns, looks, turns, looks and turns "
                         f"back -- and pushes NOTHING: {window}")
        self.assertEqual(window[0], ("turn", (self.HEADING - 25.0) % 360.0))
        self.assertEqual(window[2], ("turn", (self.HEADING + 25.0) % 360.0))
        self.assertEqual(window[4], ("turn", self.HEADING),
                         "back on the line it was going to walk")
        self.assertNotIn("push", [e[0] for e in window])
        # AND THE LOOK **IS** THE ITERATION. The event window alone cannot say
        # this: the very next event is a push either way -- the next
        # iteration's, when the rule ends in `continue`, or this one's, when it
        # does not. A mutant turning that `continue` into `pass` therefore
        # survived the window assertion entirely; the difference it makes is
        # that the iteration then records TWO rows, the look's and the push's,
        # which is also the invariant tools/trial_sheet.py:row_for relies on.
        itn = self._looks(on_res)[0]["iteration"]
        self.assertEqual(
            [r["action"] for r in on_res["fixes"] if r["iteration"] == itn],
            ["blind-look"],
            "the look REPLACES the push, so nothing else happens in its "
            "iteration and it is that iteration's only row")

    def test_the_journal_NAMES_it_and_records_WHERE_and_WHAT_it_saw(self):
        # A working path and a no-op path must not have identical output
        # (10.1): a look that finds nothing still writes a row, and the row
        # says how many views it took, how blind the walk was, WHERE it was and
        # what the best of them scored. `from_k` and `iteration` are not
        # decoration -- the pre-registered instrument credits a firing to the
        # post-166 stretch only if it can see where the firing happened.
        _, on_res = self._run(True, after=1, cap=1)
        row = self._looks(on_res)[0]
        self.assertEqual(row["action"], "blind-look")
        self.assertIsNone(row["fix"], "nothing fit, so there is no fit to show")
        look = row["blind_look"]
        self.assertEqual(look["looks"], 2, "both directions, nothing found")
        self.assertEqual(look["blind"], 1, "the blind count that triggered it")
        self.assertEqual(look["in_stretch"], 1, "the first look of its stretch")
        self.assertIsNone(look["to_k"])
        self.assertIsNone(look["deg"])
        self.assertIsNone(look["inliers"])
        self.assertEqual(look["from_k"], row["k"])
        self.assertIsInstance(row["iteration"], int)
        # ... and what it cleared, which at a firing is always already nothing.
        self.assertEqual(look["cleared"], {"lost": 0, "misses": 0, "stalls": 0})
        # It is distinguishable from an ordinary blind push, which is the whole
        # point of recording it.
        self.assertNotEqual(row["action"], "blind-advance")
        self.assertIn("blind-advance", self._actions(on_res))

    def test_a_look_that_FINDS_something_carries_the_walk_on(self):
        # `wide` is what any WIDE_AHEAD-window search returns, so this is a
        # strong fit seen from a turned camera.
        found = Fix(k=5, inliers=200, scale=1.0)
        # ONE SHOT, because a found look ENDS the blind stretch and so hands
        # the budget straight back: with a constant `wide` this walk looks,
        # relocalises, goes blind, looks, relocalises ... three times over.
        # That is correct -- every one of those looks found the route -- but it
        # is not what this test is about.
        rig, res = self._run(True, after=1, cap=1, wide=found, cls=_OneShotWide)
        row = self._looks(res)[0]
        self.assertEqual(row["action"], "relocalised-look")
        self.assertEqual(row["blind_look"]["to_k"], 5)
        self.assertEqual(row["blind_look"]["inliers"], 200)
        self.assertEqual(row["blind_look"]["deg"], -25.0,
                         "the FIRST direction that fits is believed; "
                         "STRONG_MIN_INLIERS is above the wrong-place maximum")
        self.assertEqual(row["blind_look"]["looks"], 1,
                         "the second direction is not paid for")
        self.assertEqual(row["k"], 5, "the estimate moved to what it saw")
        self.assertEqual(row["fix"]["inliers"], 200)
        self.assertEqual(row["blind_look"]["in_stretch"], 1)
        # Exactly one look FOUND anything -- the shot -- and the result's
        # counter is the walk's total, so it agrees with the journal.
        self.assertEqual([r["action"] for r in self._looks(res)].count(
            "relocalised-look"), 1)
        self.assertEqual(res["blind_looks"], len(self._looks(res)))

    def test_a_FOUND_look_hands_back_a_FULL_blind_budget(self):
        # THE DOWNSTREAM EFFECT OF THE RESET, which is the only way to test it:
        # the row's own `blind` field is captured BEFORE the reset by design,
        # so no assertion on the row can see `blind = 0` at all. What it does
        # is give the walk its whole dead-reckoning budget back -- exactly what
        # the forward search's `relocalised` does -- so BLIND_MAX blind
        # advances follow the look, not BLIND_MAX - 1.
        found = Fix(k=5, inliers=200, scale=1.0)
        _, res = self._run(True, after=1, cap=1, wide=found, cls=_OneShotWide)
        acts = self._actions(res)
        self.assertIn("relocalised-look", acts)
        after = acts[acts.index("relocalised-look") + 1:]
        self.assertEqual(after.count("blind-advance"), chain_walk.BLIND_MAX,
                         f"a full budget after the look, not a spent one: "
                         f"{after}")
        # ANTI-VACUITY: the budget really is what ran out (the walk then falls
        # into the ladder), and BLIND_MAX is not trivially small.
        self.assertGreater(chain_walk.BLIND_MAX, 1)
        self.assertIn("miss", after)

    # ---- the bound --------------------------------------------------------

    def test_it_is_BOUNDED_and_does_not_look_again_forever(self):
        # The walk stays blind for the rest of its life here, so without the
        # bound the rule would look on every remaining iteration.
        _, on_res = self._run(True, after=1, cap=1)
        self.assertEqual(len(self._looks(on_res)), 1)
        self.assertEqual(on_res["blind_looks"], 1)
        # ANTI-VACUITY: many more iterations went by with the trigger satisfied.
        self.assertGreater(on_res["iterations"], 5)
        # ... and raising the cap raises the count, so the bound is the cap and
        # not some other accident of this scenario.
        _, many_res = self._run(True, after=1, cap=4)
        self.assertEqual(len(self._looks(many_res)), 4)

    def test_a_FAILED_look_needs_another_BLIND_PUSH_before_it_looks_again(self):
        # NOT A TIGHT LOOP. A failed look touches neither `blind` nor `k`, so a
        # plain `blind >= after` trigger is satisfied again on the very next
        # iteration: four structurally identical manoeuvres back to back, same
        # k, same heading, no push and therefore no new information between
        # them. Measured with that form in a scratch copy, the four firings
        # recorded `blind` as [1, 1, 1, 1]. With `blind >= after + looks` each
        # look raises its own bar and only a blind PUSH can clear it.
        _, res = self._run(True, after=1, cap=4)
        rows = self._looks(res)
        self.assertEqual([r["blind_look"]["blind"] for r in rows], [1, 2, 3, 4])
        self.assertEqual([r["blind_look"]["in_stretch"] for r in rows],
                         [1, 2, 3, 4])
        # ... and between every pair of looks the walk really did push blind.
        acts = self._actions(res)
        cuts = [i for i, a in enumerate(acts) if a == "blind-look"]
        for a, b in zip(cuts, cuts[1:]):
            self.assertIn("blind-advance", acts[a + 1:b],
                          f"nothing happened between two looks: {acts[a:b+1]}")

    def test_the_budget_is_PER_BLIND_STRETCH_not_per_walk(self):
        # THE HOLE A PER-WALK BUDGET HAS: a walk that goes blind for a couple
        # of pushes anywhere early spends its only look there and reaches the
        # stretch this rule was built for with none -- behaving as the off arm
        # while still being scored as an on-arm trial. Here the sensor goes
        # blind, the look fires and fails, a credible fit ends the stretch, and
        # the walk goes blind again: the second stretch gets its own look.
        # `lookback=None` so the look-back does not eat the script.
        fixes = [None, Fix(k=9, inliers=120, scale=1.0), None]
        _, res = self._run(True, after=1, cap=1, fixes=fixes, lookback=None)
        rows = self._looks(res)
        self.assertEqual(len(rows), 2,
                         f"one look per blind stretch: {self._actions(res)}")
        self.assertEqual([r["blind_look"]["in_stretch"] for r in rows], [1, 1])
        # ANTI-VACUITY: the two looks really are separated by a credible fit
        # that ended the first stretch, not by nothing.
        acts = self._actions(res)
        a, b = (i for i, x in enumerate(acts) if x == "blind-look")
        self.assertTrue(any(x == "advanced" for x in acts[a + 1:b]),
                        f"the stretch must actually have ENDED: {acts[a:b+1]}")

    # ---- where it must NOT fire -------------------------------------------

    def _wps_one_push_then_a_stop(self):
        """ONE walking row, then a stationary run, then more walking -- so the
        plan's first entry is a push and its second is a TURN-ONLY stop.

        The spacing matters. An earlier version of this test put four walking
        rows first, and it gave the `pushing` guard NO coverage at all: with
        `wide` None the rule re-fired on the same pre-stop waypoint until the
        look budget was spent, so by the stop's own iteration `looks == cap`
        already refused it whatever the guard said, and a mutant dropping the
        guard passed at every cap tried. With exactly one push before the stop,
        the walk is blind at the stop with its budget untouched.
        """
        rows = [(self.HEADING, -0.35)] + [(0.0, 0.0)] * 2 \\
            + [(self.HEADING, -0.35)] * 8
        wps = [Wp(0, self.HEADING)]
        for i, (h, ly) in enumerate(rows, start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        return wps

    def test_it_does_NOT_fire_at_a_TURN_ONLY_STOP(self):
        # The stop's own look-around runs there and turns the same +-25 degrees,
        # so the EVENTS cannot tell them apart -- the journal can.
        wps = self._wps_one_push_then_a_stop()
        plan = chain_walk.plan_indices(wps)
        stops = [i for i, push, _ in plan if not push]
        self.assertTrue(stops, "ANTI-VACUITY: this plan must contain a stop")
        self.assertTrue(plan[0][1] and not plan[1][1],
                        f"ANTI-VACUITY: one push, then the stop: {plan[:3]}")
        _, res = self._run(True, after=1, cap=1, wps=wps)
        serviced = [r["target"] for r in res["fixes"]]
        self.assertTrue(set(stops) & set(serviced),
                        "ANTI-VACUITY: the stop must actually be serviced")
        self.assertEqual([r for r in self._looks(res)
                          if r["target"] in stops], [],
                         "a turn-only stop has its own look-around; this rule "
                         "must not add a second one")

    def test_it_does_NOT_fire_when_no_heading_can_be_read(self):
        # Every waypoint's heading None: the plan carries None headings, the
        # loop turns to nothing and only pushes. Looking about `None` would
        # raise; the guard keeps the walk alive instead.
        wps = [Wp(i, None) for i in range(self.N)]
        for i, w in enumerate(wps):
            w.lx = 0.0
            w.ly = 0.0 if i == 0 else -0.35
        _, res = self._run(True, after=1, cap=9, wps=wps)
        self.assertEqual(self._looks(res), [])
        self.assertGreater(res["iterations"], 3, "the walk still ran")

    # ---- the predicate, where the defensive guards can be driven ----------

    def test_the_predicate_fires_on_a_blind_pushing_iteration(self):
        self.assertTrue(chain_walk._blind_look_due(
            2, 0, 2, 1, True, False))

    def test_the_predicate_REFUSES_before_the_trigger_count(self):
        self.assertFalse(chain_walk._blind_look_due(
            1, 0, 2, 1, True, False), "one blind push is not two")

    def test_the_predicate_REFUSES_once_the_budget_is_spent(self):
        self.assertFalse(chain_walk._blind_look_due(
            6, 1, 2, 1, True, False), "cap 1, one look already taken")

    def test_the_predicate_NEEDS_A_PUSH_BETWEEN_TWO_LOOKS(self):
        # One look already taken in this stretch and `blind` unchanged since:
        # nothing has happened, so there is nothing new to look at.
        self.assertFalse(chain_walk._blind_look_due(
            2, 1, 2, 4, True, False), "no blind push since the last look")
        # ... and one more blind push makes it due again.
        self.assertTrue(chain_walk._blind_look_due(
            3, 1, 2, 4, True, False))

    def test_the_predicate_REFUSES_a_ZERO_trigger(self):
        # Unreachable through the shipped constant, and catastrophic: a walk
        # that has never gone blind would look on every single iteration.
        self.assertFalse(chain_walk._blind_look_due(
            0, 0, 0, 1, True, False))

    def test_the_predicate_REFUSES_a_ZERO_cap(self):
        # The other way to disable it, and it must disable rather than wrap.
        self.assertFalse(chain_walk._blind_look_due(
            9, 0, 2, 0, True, False))

    def test_the_predicate_REFUSES_a_TURN_ONLY_iteration(self):
        self.assertFalse(chain_walk._blind_look_due(
            9, 0, 2, 1, False, False), "the stop has its own look-around")

    def test_the_predicate_REFUSES_past_the_END_of_the_plan(self):
        # Hard to reach through a scripted walk and worth holding anyway: past
        # the plan there is nothing ahead to find and the prompt check is
        # already running every iteration.
        self.assertFalse(chain_walk._blind_look_due(
            9, 0, 2, 1, True, True))

'''

ONE_SHOT = '''
class _OneShotWide(FakeChain):
    """FakeChain whose `wide` answer is served EXACTLY ONCE.

    A constant `wide` cannot show what a found blind-look hands back: the
    ordinary forward search would relocalise on every blind iteration
    afterwards and no blind run would ever form. One shot lets the look find
    something and the walk then go honestly blind again.
    """

    def locate(self, img, k_hint, window=3):
        if window >= chain_walk.WIDE_AHEAD:
            self.wide_calls.append(k_hint)
            served, self.wide = self.wide, None
            return served
        return super().locate(img, k_hint, window=window)


'''

edits_t = [
 ("class SettleProbe(unittest.TestCase):",
  ONE_SHOT + NEW_TESTS + "\nclass SettleProbe(unittest.TestCase):"),
]

# ---------------------------------------- assert EVERYTHING, then write
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a[:60], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:60], t.count(a))
assert "BLIND_LOOK_AROUND" not in c, "patch56 already applied?"
assert "_blind_look_due" not in c
assert "blind_looks" not in c
assert "BlindLookAround" not in t and "_blind_look_due" not in t
assert "_OneShotWide" not in t
# The constants this one BORROWS must all still be here, and be what the
# docstring says they are -- a borrowed constant that has moved is an invented
# one wearing a citation.
assert c.count("END_BLIND_MAX = 2") == 1, "BLIND_LOOK_AFTER's source"
assert c.count("LOST_RESCUE_MAX = 1") == 1, "BLIND_LOOK_MAX's source"
assert c.count("BLIND_MAX = 6") == 1, "the common-case cap the docstring cites"
assert c.count("STOP_LOOK_DEG = (-25.0, 25.0)") == 1
assert c.count("STRONG_MIN_INLIERS = 165") == 1
assert c.count("WIDE_AHEAD = 60") == 1
assert c.count("def _strong_ahead(chain, img, k, n):") == 1
assert c.count('PROGRESS_ACTIONS = ("advanced", "relocalised", "regressed", "turned")') == 1
# END_BLIND_MAX must be DEFINED ABOVE the block that reads it (module level runs
# top to bottom; a NameError here would be a live-run import failure).
assert c.index("END_BLIND_MAX = 2") < c.index("BAR_STOP_INDEX = 166")
# The two rules this one composes with are untouched.
assert c.count("DOOR_STOP_EXTRA_PUSH = True") == 1
assert c.count("BAR_STOP_EARLY_TURN = False") == 1
# The LOST message's hardcoded literal, named in the docstring as a separate
# pre-existing bug this patch deliberately does NOT touch. Asserted so that if
# someone fixes it, this docstring is known to be stale.
assert c.count("f\"with no credible fix after {BLIND_MAX} blind \"") == 1
# The two existing look-arounds whose "no at_table on the looked frame" shape
# this block matches on purpose.
assert c.count("suffix=f\"_look{int(ddeg):+d}\"") == 1
assert c.count('looks_plan = [(0.0, "_rescue_look0")]') == 1
# The test rig this patch's tests subclass and drive.
assert t.count("class FakeChain:") == 1
assert t.count("        self.lookback = lookback") == 1
assert t.count("        return self._fixes.pop(0) if self._fixes else self.default") == 1, \
    "FakeChain.locate's script tail -- the method _OneShotWide delegates to"

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(c)
ast.parse(t)
assert c.count("BLIND_LOOK_AROUND = False") == 1
assert c.count("BLIND_LOOK_AFTER = END_BLIND_MAX") == 1
assert c.count("BLIND_LOOK_MAX = 1") == 1
assert c.count('BLIND_LOOK_ACTION = "blind-look"') == 1
assert c.count('BLIND_LOOK_FOUND_ACTION = "relocalised-look"') == 1
assert c.count("def _blind_look_due(") == 1
assert c.count("and blind >= after + looks)") == 1
assert c.count("_blind_look_due(blind, blind_looks, BLIND_LOOK_AFTER,") == 1
assert c.count("blind_looks = 0") == 2, "the counter AND the per-stretch reset"
assert c.count("blind_looks += 1") == 1
assert c.count("blind_looks_total += 1") == 1
assert c.count('"cleared": {"lost": lost, "misses": misses,') == 1
assert c.count("        turned = False") == 1
assert c.count("DOOR_STOP_EXTRA_PUSH = True") == 1
assert c.count("BAR_STOP_EARLY_TURN = False") == 1
assert t.count("class BlindLookAround(unittest.TestCase):") == 1
assert t.count("class _OneShotWide(FakeChain):") == 1

open(C, "w").write(c)
open(T, "w").write(t)
print("patch56 applied to", ROOT)
