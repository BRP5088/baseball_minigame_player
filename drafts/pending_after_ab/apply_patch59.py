"""patch59: ESCAPE_GATE -- the ladder's rung at the BAR-ENTRANCE STOP, and no
rung at all when a validated signal says the push MOVED.

THE ASK, from the user watching the stream: "the navigation is jumping around
in the bar area. getting onto the bar and ramming into it and somehow ending up
at the mini game table." They want the unnecessary movements in the bar removed.

===============================================================================
THE TABLE, REGENERATED. The first draft of this patch carried it as hand-copied
prose in a docstring and a skeptic could not reproduce it. It is now produced by
`agent_progress/closed-loop/escape_gate/census.py`, checked in beside the notes,
and THREE of its seven rows were wrong:

    region        rung   n   the draft said   census.py says
    BAR 115-150   left    8   8/8  (100%)      8/8  (100%)   ok
    BAR 115-150   jump   22   6/22 ( 27%)     13/22 ( 59%)   WRONG
    BAR 115-150   back    8   0/8  (  0%)      0/8  (  0%)   ok
    elsewhere     jump   41  32/41 ( 78%)     33/41 ( 80%)   WRONG
    elsewhere     back    7   4/7  ( 57%)      4/7  ( 57%)   ok
    elsewhere     left    5   2/5  ( 40%)      2/5  ( 40%)   ok
    elsewhere     right   3   0/3  (  0%)      1/3  ( 33%)   WRONG

Definition, so it can be argued with: a FIRING is a row whose action starts
"escape:"; CREDIBLE AFTER is any of the next three rows carrying a fit of at
least FIX_MIN_INLIERS (29); NO FIT AFTER is all three rows with a null fit; 60
journals, newest by mtime. `python3 census.py --split` reproduces every number
below. A number that cannot be regenerated is not evidence, and that is the
whole reason the script exists.

===============================================================================
AND THE TABLE'S OWN BUCKET HID THE FINDING. Split at the boundary
tools/collision_census.py already uses (115-129 "turn->bar entrance",
130-166 "bar counter->tables"):

    BAR-A 115-129   jump   7   0/7 (  0%)   no fit 7/7
    BAR-A 115-129   back   7   0/7 (  0%)   no fit 7/7
    BAR-A 115-129   left   7   7/7 (100%)   no fit 0/7
    BAR-B 130-150   jump  15  13/15 ( 87%)  no fit 1/15
    BAR-B 130-150   back   1   0/1           left   1   1/1

JUMP IN 130-150 IS THE BEST RUNG ANYWHERE IN THE DATASET. A ban across 115-150
bans it precisely where it works. And every BAR jump firing sits at k in
{129: 7, 130: 3, 136: 3, 139: 9}, so the whole bar finding is ONE WAYPOINT --
k = 129, the bar-entrance stop CLAUDE.md already calls "the lever". The bounds
are therefore 129..129, not 115..150.

===============================================================================
THE HEADLINE OF THE FIRST DRAFT WAS A LADDER-ORDER ARTEFACT, AND IT IS
WITHDRAWN. Printing the escape sequence per walk (census.py's own journals):

    it44/k129:jump.   it47/k129:back.   it50/k129:leftC
    it43/k129:jump.   it46/k129:back.   it49/k129:leftC      ... x7 walks

Seven walks, seven IDENTICAL triples, the firings exactly MISS_MAX iterations
apart, and in all seven the next credible fit lands exactly 7 iterations after
the first rung. The ladder is jump, back, left, right AND IT STOPS WHEN IT
WORKS, so the LAST rung tried always looks like the rung that worked. Left is
never tried first anywhere in this dataset. "left recovered 8 of 8" is
therefore "the blockage ended by the third rung" -- equally consistent with
"nine iterations is how long that blockage lasts". This is CLAUDE.md 10.2's
STALL_CHANGE shape: a strong association (Fisher on 7/7 against 0/7 gives
p = 3e-4) that is a symptom of the ORDER, not a property of the rung.

Worse for power than any n: the seven walks are not seven samples. Three rungs
each, a 7-iteration recovery each, the same sequence each -- effectively ONE
deterministic trajectory observed seven times. CLAUDE.md 10.3's floor (0.72 at
n=6, 0.94 at n=10) is generous to it.

WHAT SURVIVES, and it is only the position-matched half:

  * JUMP AS THE FIRST RUNG AT k=129: 0 of 7 credible, the picture lost on 7 of
    7. Jump ALWAYS goes first, so nothing about the order confounds this. It is
    also exactly what the user described: a hop, and then the loop cannot see.
  * BACK AS THE SECOND RUNG AT k=129: 0 of 7, lost 7 of 7. Unconfounded in the
    position it was measured in. (chain_walk.py has carried "credible fix
    follows `escape:back` 0 of 27 times in the bar stretch" since patch43 --
    known, written down, never acted on. This project's signature shape.)
  * JUMP AS THE FIRST RUNG EVERYWHERE ELSE: 33 of 41, including 13 of 15 at
    k 130-139. That is why the default order is untouched outside k=129.
  * LEFT'S 7 of 7: CONFOUNDED. It is the HYPOTHESIS this A/B tests, not the
    evidence for it. The patch says so in the constant's own comment.

So the falsifiable claim this ships is "jump first at k=129 does not work",
not "left works". Removing jump is supported; putting left first is a guess
constrained to the one waypoint where the supported removal applies.

A SECOND CLUSTER, RECORDED AND DELIBERATELY NOT TOUCHED: at k=166 (the 296-deg
jukebox turn) jump 0/3, back 0/3, left 0/3, right 0/2 -- eleven firings, zero
credible, ten of eleven losing the picture. NO rung order helps there and this
patch does not pretend to. At k=173 the opposite holds: back 4/4, jump 5/5,
left 2/2, right 1/1.

===============================================================================
THE SECOND SIGNAL, AND THE DISPATCH'S READING OF IT IS WRONG IN TWO PLACES.
I read overnight/crawl_labelled.jsonl and then opened the frames, which is the
whole of CLAUDE.md's "check frames before theorising".

The file is 12 rows the user labelled by hand, 6 `desk` and 6 `clean`. Their
`push_inliers` -- the ORB+Hamming+RANSAC count between the frame BEFORE a push
and the frame AFTER it (tools/crawl.py:pair_inliers):

    desk    28  166  148  153  154  164        (steps 1..6)
    clean   11   23   28   10  None None       (steps 7..12)

  (1) STEP 1 IS LABELLED `desk` AT 28, INSIDE THE CLEAN RANGE. It is not a
      counter-example to the signal, it is a counter-example to the LABEL's
      meaning. crawl.py's labels name WHAT WAS HIT, not whether the push moved,
      and step 1 is the push that TRAVELLED INTO the desk: its `change` is 29.2,
      the largest of the twelve, and its frame
      (overnight/crawl_frames/20260908_164204/step001.jpg) is a different
      viewpoint from step002.jpg -- a dark pillar fills the right of the frame
      in one and the landing and bannister show in the other. So the populations
      are BLOCKED 148-166 (n=5) and MOVED 10-28 or no fit (n=7), not 6 and 6.
      The gap, 28 | 148, is unchanged. `tools/crawl.py:_min_misclassified` on
      these counts is 1, and its own docstring says of exactly that case: "ONE
      stray point is the whole story ... the answer is to open that frame".
      This is that.
  (2) "148-166 INLIERS OF ~184-200 KEYPOINTS" -- that denominator is the
      `null_inliers` column, the PAIRED CONTROL, not a keypoint count. The file
      records no keypoint totals at all. It matters because a null costs a
      second measurement window (~0.75 s) per push and the closed loop cannot
      pay for one, so this ships with the RAW count and the honest caveat below.

WHAT THE RAW COUNT COSTS, STATED PLAINLY. CLAUDE.md's OPEN-1 measured the raw
ORB count as UNUSABLE (null 353-1366 against push 35-908, overlapping) and only
the PAIRED ratio as usable. The raw count separates HERE because these nulls sit
at or near pose._MAX_MATCHES (184-200 on the five blocked rows) -- a property of
that scene, not a general result. Rows 11 and 12 are the counter-case: their
nulls are 49 and 10, so nothing in that scene could have produced a high push
count either, and a low count there means nothing. Pairing buys nothing on this
data anyway -- inlier_ratio is desk 0.14/0.90/0.74/0.79/0.89/0.77 against clean
0.055/0.18/0.14/0.05, and step 1 is the same single stray under the ratio as
under the raw count. n = 5 and 7 is UNDER 10.3's power floor, and the gate ships
OFF with the raw count journalled on both arms precisely so the next batch
calibrates it at n in the hundreds.

The cheap stand-in for the null is the KEYPOINT FLOOR, and it is necessary
rather than sufficient. Inliers <= matches <= min(keypoints), so a frame pair
with fewer than the threshold's worth of keypoints CANNOT score BLOCKED, and a
low count from it is an artefact -- CLAUDE.md 10.1's "a measurement that returns
the same number everywhere and reads as a verdict". Under the floor the verdict
is NO SIGNAL and the loop behaves exactly as it does today. The floor does not
catch the rows-11-and-12 case (many keypoints, none of them matching), and that
failure points the DANGEROUS way: it reads MOVED, which suppresses an escape on
a character that is stuck. That is the whole reason the bound in part 3 exists,
and it is why the bound is not decoration.

===============================================================================
THE BOUND WAS UNSOUND IN THE FIRST DRAFT, AND IT COULD REMOVE EVERY RUNG.

`ESCAPE_SUPPRESS_MAX = MISS_MAX` (3) was borrowed. Two trigger families reach
the ladder and they have DIFFERENT CADENCES, and both increment `lost` on every
iteration under one budget, `LOST_MAX = 13`:

    the MISS family  (fix is None)                cadence MISS_MAX  = 3
                     triggers at lost = 3, 6, 9, 12   -- FOUR inside the budget
    the WEAK family  (a fit under FIX_MIN_INLIERS)  cadence STALL_MAX = 4
                     triggers at lost = 4, 8, 12      -- only THREE

LOST_MAX's own comment derives 13 as `MISS_MAX*4+1`, "let all four rungs fire
and be seen" -- which is true of the miss family and false of the weak one. A
cap of 3 therefore suppresses EVERY trigger the weak family gets, and the walk
reaches LOST_MAX having attempted no physical recovery at all, with a failure
line identical to the one it writes today.

REPRODUCED, not reasoned about: a scratch copy, FakeChain(4, default=Fix(k=0,
scale=0.5, inliers=10)), MOVED on every push, gate ON, bar bounds out of range:

    ESCAPE_SUPPRESS_MAX   weak family (inliers=10)      miss family (no fit)
        3                 rungs []          skips 3     rungs [jump]      skips 3
        2                 rungs [jump]      skips 2     rungs [jump,back] skips 2
        1                 rungs [jump,back] skips 1     rungs [j,b,left]  skips 1

SO THE CAP IS 2, and it is DERIVED rather than borrowed: the shortest trigger
sequence any family gets inside its own budget is THREE, so a cap of two leaves
at least one real rung in every family. The suppression still cannot LENGTHEN a
walk -- `lost`, `misses` and `stalls` are untouched, so the iteration count of a
blockage is identical either way -- but it can no longer empty it.

===============================================================================
WHAT THIS PATCH DOES, all of it behind ESCAPE_GATE, which ships False.

  1. RUNG ORDER BY REGION. `escape()` took `escapes % 4` over a fixed
     jump/back/left/right. It now takes an ORDER, chosen by
     `escape_rungs(k, ...)`: DEFAULT_ESCAPE_RUNGS everywhere (byte-identical to
     today), BAR_ESCAPE_RUNGS = ("left", "right", "back") at k = 129 alone.
     Jump is not in that order at all.
  2. THE MOVED/BLOCKED GATE. `slow_traverse.walk_leg` already holds the frame
     before the push and the frame after it and throws both away; it gains an
     `on_pair` hook (the shape patch54 gave `on_release`), chain_walk's default
     `push` wrapper turns that pair into one ORB match (~28 ms) and RETURNS the
     verdict, and an escape trigger whose push read MOVED records
     `escape-skipped` and fires no rung. The character is not stuck; it is
     blind, and BLIND_LOOK_AROUND or simply carrying on is the right answer.
  3. JOURNAL IT EVERY PUSH, FLAG ON OR OFF: `push_signal` carries the inlier
     count, both frames' keypoint totals and the verdict; `escape` carries the
     rung, the order it came from, why, and the suppression count. THIS PART
     CHANGES NO BEHAVIOUR and it is the reason the next batch can measure the
     two populations at n in the hundreds instead of at n = 12.

WHY THIS IS THE SAFE FAMILY, and it is the argument that decides it.
GRAVEYARD's summary is that every failed navigation change MOVED the character
and both survivors move nothing. This one REMOVES and REDIRECTS movement: at
one waypoint it deletes the jump that a position-matched census says is 0 of 7
and loses the picture 7 of 7, and it suppresses rungs a validated signal says
are pointless. On the off arm nothing is suppressed and the order is the order
it has always been, so the off arm is today's build with two extra journal
fields.

THE ONE THING IT IS NOT: 10.7 CLEAN. Two rules ride one flag, because the
harness switches one `--flag NAME`. They are the same intervention -- "stop
making the movement that does not help" -- and the pre-registered instruments
below separate the mechanisms even when arrival ties. If the on arm wins, the
follow-up A/B splits them; if it loses, the instruments say which half.

THE CONSTANTS AND WHERE EACH ONE COMES FROM:

    ESCAPE_GATE = False            the arm
    BAR_ESCAPE_FROM_K = 129        THE BAR-ENTRANCE STOP, and a range of one,
    BAR_ESCAPE_TO_K   = 129        because that is the whole of the evidence:
                                   every failing bar jump is at k=129 (0 of 7,
                                   picture lost 7 of 7), and at 130-139 jump is
                                   13 of 15, the best rung in the dataset. A
                                   wider window would ban it there. These are
                                   a property of THIS chain
                                   (chains/route_user_1853); another recording
                                   needs its own census before they mean
                                   anything.
    BAR_ESCAPE_RUNGS = ("left", "right", "back")
                                   JUMP IS REMOVED, and that is the supported
                                   half: it always went first, 0 of 7. LEFT
                                   FIRST IS THE HYPOTHESIS, not a measurement
                                   -- its 7 of 7 is the ladder's stop-when-it-
                                   works artefact, since left is only ever
                                   reached third. RIGHT second (the same
                                   clearance on the other side); BACK last and
                                   kept only so a two-rung ladder cannot
                                   alternate sidesteps for ever -- it is the
                                   one rung that changes the distance to what
                                   is in front. Not because it works: 0 of 7
                                   as the second rung here, 0 of 27 in the
                                   older census.
    DEFAULT_ESCAPE_RUNGS = ("jump", "back", "left", "right")
                                   today's `escapes % 4`, written out
    PUSH_BLOCKED_MIN_INLIERS = 88  the MIDPOINT of the measured gap, 28 | 148,
                                   over the twelve labels above (BLOCKED 148
                                   153 154 164 166, MOVED 10 11 23 28 + two no
                                   fits). n = 5 and 7 is UNDER 10.3's power
                                   floor: a gap between two THIN populations,
                                   not a calibrated gate, and the journal
                                   records the raw count on every push so the
                                   next batch calibrates it properly. It is
                                   also the keypoint floor, by arithmetic
                                   rather than by choice: inliers <=
                                   min(keypoints), so below it BLOCKED is
                                   unreachable and the answer is NO SIGNAL.
    ESCAPE_SUPPRESS_MAX = 2        DERIVED, not borrowed -- see the section
                                   above. The weak family gets only three
                                   triggers inside LOST_MAX, so a cap of three
                                   removed every rung it would ever have
                                   fired. Two leaves at least one in both
                                   families.

HOW IT COMPOSES WITH WHAT IT SITS BESIDE:

  * PATCH56's BLIND_LOOK_AROUND fires BEFORE the push, on the blind count, and
    ends in `continue`; this reads the verdict of a push that HAS happened, at
    the escape triggers, far below. They cannot both act in one iteration: a
    blind-look iteration never pushes, so `push_sig` is None there and the gate
    is inert. They are complementary by design -- patch56 answers "do not push
    blind again", this answers "do not thrash when the push worked".
  * THE LOST RESCUE (LOST_RESCUE_MAX) is untouched and still last, and its
    success block now resets `escape_suppressed` alongside the ten sibling
    counters it already resets (`escapes` among them). It did not, in the first
    draft: "rescued" starts with no PROGRESS_ACTIONS prefix, so the top-of-loop
    reset never caught it and a rescued walk carried a spent budget into ground
    it had just re-approached.
  * THE STALL AND MISS COUNTERS reset exactly as they do today at every trigger,
    suppressed or not, so the ladder's cadence is unchanged and only the ACTION
    differs. A suppression touches neither `lost` nor the counters, so it cannot
    lengthen a blockage -- but see the bound above for what it CAN do.
  * PITCH CORRECTION (patch57) blocks its PRESS on `escaped or escaped_prev`. A
    suppression returns escaped=False, so a suppressed iteration keeps its pitch
    correction -- correctly, because nothing displaced the character. Both flags
    ship OFF; the composition is pinned by a test rather than left to reasoning.
  * TURN-EARLY still comes before every rung; this changes nothing above it.
  * `escape-skipped` deliberately does NOT start with `escape:`, because
    `tools/collision_census.py` counts waste with `a.startswith("escape:")` and
    a suppression is the opposite of waste. It is not in PROGRESS_ACTIONS
    either: it is not evidence the walk moved on.

PRE-REGISTERED INSTRUMENTS, computed from BOTH arms' journals by census.py:

  (a) AT k = 129, the fraction of escapes followed by a credible fit within
      three rows -- baseline 7 of 21 -- and the number followed by NO fit at
      all -- baseline 14 of 21. The on arm should raise the first and cut the
      second.
  (b) THE RUNGS PER AFFECTED WALK AT k = 129 -- baseline exactly 3 on 7 of 7
      walks. If left-first is the rung, this falls to 1.
  (c) THE RECOVERY LENGTH: iterations from the first rung at k=129 to the next
      credible fit -- baseline exactly 7 on 7 of 7 walks (jump, +3 back, +3
      left, +1 the fit). If left-first is the rung it falls to about 1; if the
      blockage simply takes nine iterations whatever is done, it does not move,
      and THAT is what refutes the left hypothesis. This is the instrument the
      ladder-order confound demands and the first draft did not have.
  (d) FOR THE GATE, the two-population check on the journalled `push_signal`
      counts: split every push by whether the NEXT rows show the estimate
      advancing, and ask whether 88 still sits between them at n in the
      hundreds. Both arms journal it, so this is measurable even if the arm
      loses -- and it is the number that decides whether the threshold was a
      guess.
  (e) WHERE. Every `escape` row carries `k` and the `order` it drew from, so a
      firing outside k=129 is not evidence about the bar.

WHAT I COULD NOT VERIFY, recorded rather than left implicit:
  * the ~28 ms per ORB match is the dispatch's number; I did not time it.
  * FIX_MIN_INLIERS' 29 is taken as given; census.py reads it from the module.
  * the signal is journalled from the TWO TRACKED forward pushes only, but the
    ORB match is PAID at four call sites. `on_pair` is attached inside the one
    shared `push()` closure, and `push(PUSH_MAG, PUSH_SEC)` is called from four
    places in chain_walk.py: the two tracked forward pushes, DOOR_STOP_EXTRA_PUSH
    (once per walk at one stop) and the turn-retry (up to TURN_RETRY_MAX = 3 per
    stop). The latter two discard the return, so the match runs and its result
    is thrown away: up to four extra matches a walk, ~112 ms, no console call
    and no journal row. The first draft's phrasing ("they are not journalled and
    the gate never sees them") read as "no cost is paid there"; it is.
  * REAL FRAMES HAVE NOW BEEN THROUGH `pair_signal`, and here is exactly what
    that did and did not establish. On two real 1920x1080 crawl frames it
    returns the SAME number as calling `places.keypoints` + `crawl.pair_inliers`
    by hand (19 and 19), and a frame against ITSELF -- the extreme "nothing
    moved" case on real pixels -- reads BLOCKED at 121 inliers. So the wrapper
    adds nothing to the construction that was validated against the user's
    labels, which is the claim that matters (it is IMPORTED, never
    reimplemented: CLAUDE.md's localiser-inliers trap is a reimplementation that
    scored 3/9 where the original scored 9/9).
  * BUT NO LABELLED PUSH PAIR CAN BE REPRODUCED FROM DISK, and that is a real
    limit. tools/crawl.py saves only `im1` -- the frame AFTER each push -- so
    the BEFORE frames of all twelve labelled rows were never written. The
    twelve `push_inliers` are taken from the file on trust; nothing offline can
    re-derive them. Anyone re-opening this threshold needs a fresh crawl that
    saves both frames.
  * AND THE KEYPOINT COUNTS ON REAL FRAMES ARE MUCH LOWER THAN THE TESTS' 900:
    the four crawl frames measured here carry 34, 121, 137 and 447. So the 88
    floor will answer NO SIGNAL on genuinely dark frames fairly often -- the
    SAFE direction (no signal falls through to today's ladder), and the journal
    records `kp_before`/`kp_after` on every push so instrument (d) can say how
    often it happened rather than leaving it to be guessed at.

Applies to: chain_walk.py, slow_traverse.py, tests/routing/test_chain_walk.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch59.py [ROOT]
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
S = os.path.join(ROOT, "slow_traverse.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read()
s = open(S).read()
t = open(T).read()

# ---------------------------------------------------------------- slow_traverse
edits_s = [
 ('''def walk_leg(lx, ly, seconds, capture, read_heading, label="", log=print,
             step_sec=None, on_release=None):''',
  '''def walk_leg(lx, ly, seconds, capture, read_heading, label="", log=print,
             step_sec=None, on_release=None, on_pair=None):'''),
 ('''    hazards = []
    prev = _grey(capture())''',
  '''    hazards = []
    # THE PIL FRAME IS KEPT, NOT ONLY ITS GREY ARRAY (patch59). `_grey` returns
    # an unmasked float array; anything that wants ORB features has to go
    # through `places.keypoints`, whose `_as_gray` crops the compass, the quest
    # list and the health coin -- pixel-identical furniture that would hand any
    # two frames free "matches" and bias every answer toward "did not move".
    # Keeping the image costs a reference, not a capture.
    prev_im = capture()
    prev = _grey(prev_im)'''),
 ('''        now = _grey(capture())
        moved = _change(now, prev)
        prev = now''',
  '''        now_im = capture()
        now = _grey(now_im)
        moved = _change(now, prev)
        # THE PAIR THIS FUNCTION HAS ALWAYS HELD AND ALWAYS DISCARDED. `moved`
        # is the frame delta, which CLAUDE.md 10.4 measured as one population
        # (null 1-12 against push 7-24, overlapping) and therefore unusable as
        # a blocked/moved gate. The FRAMES are a different matter, and the
        # caller is handed them rather than a verdict: what to compute from
        # them is the caller's question, not this module's.
        #
        # Once per CHUNK. A chain push is one chunk (`step_sec == seconds`), so
        # there it is once per push; a long chunked leg gets one call per chunk
        # and the caller sees the last one.
        if on_pair is not None:
            on_pair(prev_im, now_im)
        prev_im, prev = now_im, now'''),
]

# ------------------------------------------------------------------ chain_walk
edits_c = [
 # ---------------------------------------------------------------- constants
 ('''BLIND_LOOK_FOUND_ACTION = "relocalised-look"''',
  '''BLIND_LOOK_FOUND_ACTION = "relocalised-look"

# THE ESCAPE GATE (patch59): the ladder's rung at the BAR-ENTRANCE STOP, and no
# rung at all when the push that led to it MOVED.
#
# The user, watching the stream: "the navigation is jumping around in the bar
# area. getting onto the bar and ramming into it and somehow ending up at the
# mini game table."
#
# THE CENSUS IS A SCRIPT, NOT PROSE:
# agent_progress/closed-loop/escape_gate/census.py regenerates every number
# here from the journals. The first draft of this patch carried a hand-copied
# table and three of its seven rows were wrong.
#
# Over the last 60 journals, 94 rungs fired; whether a CREDIBLE fit (>=
# FIX_MIN_INLIERS) followed within three rows, split at the boundary
# tools/collision_census.py already uses:
#
#     region          rung   n   credible   no fit
#     BAR-A 115-129   jump    7   0 (  0%)   7/7    <- ALL SEVEN AT k=129
#     BAR-A 115-129   back    7   0 (  0%)   7/7
#     BAR-A 115-129   left    7   7 (100%)   0/7    <- but see the confound
#     BAR-B 130-150   jump   15  13 ( 87%)   1/15   <- the BEST rung anywhere
#     elsewhere       jump   41  33 ( 80%)   3/41
#     elsewhere       back    7   4 ( 57%)   2/7
#     elsewhere       left    5   2 ( 40%)   3/5
#     elsewhere       right   3   1 ( 33%)   2/3
#
# THE CONFOUND, AND IT IS WHY THE COMMENT IS THIS LONG. The ladder is jump,
# back, left, right and IT STOPS WHEN IT WORKS, so the last rung tried always
# looks like the rung that worked. All seven k=129 blockages are the identical
# triple (jump., back., leftC) at exactly MISS_MAX iterations apart, with the
# next credible fit exactly 7 iterations after the first rung -- one
# deterministic trajectory observed seven times, not seven samples. Left is
# NEVER tried first anywhere in this dataset, so its 7 of 7 is an artefact of
# the ORDER (CLAUDE.md 10.2's STALL_CHANGE shape) and is a HYPOTHESIS here.
#
# What survives is position-matched only: JUMP ALWAYS WENT FIRST and at k=129
# it is 0 of 7 with the picture lost on 7 of 7 -- which is exactly the hop the
# user watched -- while everywhere else, first as well, it is 33 of 41. BACK
# always went second and is 0 of 7 here (LOST_RESCUE_MAX's comment below has
# carried "escape:back 0 of 27 times in the bar stretch" since patch43 without
# anything acting on it).
#
# NOT TOUCHED, and recorded so nobody reads its absence as a claim: at k=166
# every rung fails (jump 0/3, back 0/3, left 0/3, right 0/2, ten of eleven
# losing the picture). No rung order helps there.
#
# THIS REMOVES AND REDIRECTS MOVEMENT rather than adding any. GRAVEYARD's
# summary is that every failed navigation change MOVED the character and both
# survivors move nothing.
#
# Ships OFF; `--flag ESCAPE_GATE` measures it. Instruments: at k=129 the
# fraction of escapes followed by a credible fit (baseline 7 of 21) and the
# number followed by NO fit (14 of 21); the rungs per affected walk (baseline
# exactly 3 on 7 of 7); the iterations from the first rung to the next credible
# fit (baseline exactly 7 on 7 of 7 -- the instrument the confound demands);
# and the two-population check on the journalled push signal.
ESCAPE_GATE = False
# THE WINDOW IS ONE WAYPOINT, inclusive at both ends, IN THIS CHAIN
# (chains/route_user_1853): k = 129 is the bar-entrance stop. It is a range of
# one because that is the whole of the evidence -- every failing bar jump is
# there, and at k 130-139 jump is 13 of 15, the best rung in the dataset, so a
# wider window would ban it exactly where it works. The 115-150 span the first
# draft used came from a census bucket and hid that split.
#
# The test `k` is the ESTIMATE, which is what the census bucketed and which can
# be wrong; a rung chosen from a wrong estimate is the same risk the rest of
# the loop already runs, and every firing records its `k` so instrument (e) can
# throw out a firing that was not really here.
BAR_ESCAPE_FROM_K = 129
BAR_ESCAPE_TO_K = 129
# JUMP IS ABSENT, and that is the SUPPORTED half: it is the rung that always
# went first, 0 of 7 at this stop, and the one that loses the picture entirely,
# 7 times in 7 -- the hop the user watched climb the counter.
#
# LEFT FIRST IS A HYPOTHESIS, NOT A MEASUREMENT. Its 7 of 7 comes from the
# third rung of a ladder that stops when it works; nothing here has ever tried
# it first. RIGHT second: the same clearance on the other side. BACK last, and
# kept only because a two-rung ladder alternates sidesteps down the counter for
# ever while back is the one rung that changes the distance to whatever is in
# front -- NOT because it works (0 of 7 as the second rung, 0 of 27 in the
# older census). Which side "left" is relative to the counter is not
# established either.
BAR_ESCAPE_RUNGS = ("left", "right", "back")
# Today's `escapes % 4`, written out so the two orders sit side by side. With
# the gate off this is the order everywhere and the ladder is byte-identical.
DEFAULT_ESCAPE_RUNGS = ("jump", "back", "left", "right")
# THE MOVED/BLOCKED THRESHOLD, in RANSAC inliers between the frame before a
# push and the frame after it (tools/crawl.py:pair_inliers, imported not
# reimplemented). The twelve hand labels in overnight/crawl_labelled.jsonl:
#
#     BLOCKED (pressed on the desk, the push moved nothing)  148 153 154 164 166
#     MOVED   (travelled)                    10 11 23 28, and two with NO FIT
#
# 88 is the MIDPOINT of 28 | 148. Step 1 of that file is labelled `desk` at 28
# and belongs to the MOVED population: crawl.py's labels name what was HIT, and
# step 1 is the push that travelled INTO the desk -- its `change` is the
# largest of the twelve and its frame is a different viewpoint from step 2's.
# n = 5 and 7, UNDER 10.3's power floor (0.72 at n=6, 0.94 at n=10). This is a
# gap between two thin populations, not a calibrated gate; the raw count is
# journalled on every push, on BOTH arms, so the next batch calibrates it at
# scale.
#
# CLAUDE.md OPEN-1 measured the RAW count as unusable and only the PAIRED ratio
# (push / a null taken at the same spot) as usable. The raw count separates
# here because these nulls sit at pose._MAX_MATCHES (184-200 on the blocked
# rows); a null costs a second measurement window per push, which the loop
# cannot pay for. Rows 11-12 are the counter-case (nulls of 49 and 10), and
# they fail toward MOVED -- which suppresses an escape on a stuck character.
# ESCAPE_SUPPRESS_MAX below is the bound that exists for exactly that.
#
# IT IS ALSO THE KEYPOINT FLOOR, by arithmetic and not by choice: inliers <=
# matches <= min(keypoints), so a pair with fewer keypoints than this CANNOT
# read BLOCKED and its low count is an artefact rather than an answer (10.1's
# "a measurement that returns the same number everywhere"). Under the floor the
# verdict is None -- NO SIGNAL, today's behaviour -- and never "moved".
PUSH_BLOCKED_MIN_INLIERS = 88
PUSH_MOVED = "moved"
PUSH_BLOCKED = "blocked"
# THE LAST RESORT'S BOUND: this many consecutive suppressions per blockage,
# after which every trigger fires its rung until the walk moves on evidence.
#
# DERIVED FROM THE LOOP'S OWN CADENCES, not borrowed -- the first draft set it
# to MISS_MAX (3) and that could remove EVERY rung. Two families reach the
# ladder and both increment `lost` under one budget, LOST_MAX:
#
#     the MISS family (fix is None)   cadence MISS_MAX  = 3 -> lost 3, 6, 9, 12
#     the WEAK family (a thin fit)    cadence STALL_MAX = 4 -> lost 4, 8, 12
#
# LOST_MAX's own comment derives 13 as MISS_MAX*4+1, "let all four rungs fire
# and be seen" -- true of the miss family, false of the weak one, which gets
# only THREE triggers inside the budget. At a cap of 3 all three were
# suppressed and the walk reached LOST_MAX having attempted no physical
# recovery at all, with a failure line identical to today's. Reproduced on a
# scratch copy: cap 3 -> rungs [], cap 2 -> rungs [jump].
#
# So: the shortest trigger sequence any family gets is THREE, and a cap of TWO
# leaves at least one real rung in every family. A loop that can never escape
# is worse than one that escapes too often, and the failure this bounds is a
# real one: a scene whose own frames do not match each other (crawl rows 11-12)
# reads MOVED however stuck the character is.
ESCAPE_SUPPRESS_MAX = 2
# The action a suppressed trigger records. It deliberately does NOT start with
# "escape:", because tools/collision_census.py counts waste with
# `startswith("escape:")` and a rung not taken is the opposite of waste; and it
# is not in PROGRESS_ACTIONS, because it is not evidence the walk moved on. A
# no-op path and a working path must not have identical output (10.1), which is
# why a suppression writes a row at all.
ESCAPE_SKIPPED_ACTION = "escape-skipped"'''),
]

edits_c += [
 # ---------------------------------------------------------------- predicates
 ('''def _strong_ahead(chain, img, k, n):''',
  '''def escape_rungs(k, gate, from_k, to_k, bar_order, default_order):
    """The escape ladder's rung ORDER at estimate `k`.

    Pure, and every argument is a PARAMETER rather than a module-level default
    (10.18): a knob captured in a default cannot be redirected by a test or an
    A/B arm, which is how `leg_reliability.STORE` silently served one store to
    both arms.

    Three clauses, each of which a mutant can delete, each driven directly:

      gate         with the flag off this returns `default_order` for every k,
                   so the ladder is byte-identical to the one that has always
                   shipped. That is what makes the off arm today's build.
      k is not None  the estimate is never None in the loop today, but a rung
                   chosen from a missing estimate would be chosen from
                   `None <= 129`, which raises. Explicit beats a TypeError in
                   a live walk.
      from_k <= k <= to_k   inclusive at both ends. The shipped window is a
                   RANGE OF ONE (129..129), so both ends are the same waypoint
                   and an off-by-one at either is a firing in the wrong place.
    """
    if gate and k is not None and from_k <= k <= to_k:
        return bar_order
    return default_order


def push_verdict(inliers, kp_before, kp_after, thresh):
    """Did this push MOVE the character, or was it BLOCKED? None = no signal.

    `inliers` is tools/crawl.py's `pair_inliers` between the frame before the
    push and the frame after it -- None from it means UNMEASURABLE (too few
    surviving matches to fit), never "identical".

    THE KEYPOINT FLOOR COMES FIRST, and it is arithmetic rather than judgement:
    inliers <= matches <= min(keypoints), so a pair with fewer keypoints than
    the threshold cannot reach BLOCKED at all, and its low count would be a
    number that is low everywhere -- 10.1's measurement that reads as a verdict.
    Below the floor the answer is NO SIGNAL, which falls through to today's
    behaviour. It is never "moved": a suppressed escape on a stuck character is
    the expensive direction to be wrong in.

    ABOVE the floor, NO FIT IS THE MOVED POPULATION. Two of the six clean rows
    in overnight/crawl_labelled.jsonl have `push_inliers` None. What the floor
    cannot catch is a scene whose frames do not match each other at all (those
    same two rows have nulls of 49 and 10 on plenty of keypoints), and that
    case reads MOVED -- which is why the caller's suppression is bounded.
    """
    if min(kp_before, kp_after) < thresh:
        return None
    if inliers is None:
        return PUSH_MOVED
    return PUSH_BLOCKED if inliers >= thresh else PUSH_MOVED


def escape_is_suppressed(gate, verdict, suppressed, cap):
    """Should THIS escape trigger fire no rung at all?

    Pure, so each of the three clauses can be driven and mutated directly --
    patch55 learned that a guard reachable only through a scripted walk lets its
    mutant survive.

      gate                 the arm.
      verdict == MOVED     BLOCKED fires the rung, and so does NO SIGNAL. Only
                           a positive reading of "the character travelled"
                           earns a suppression.
      suppressed < cap     the bound, and it is load-bearing: at a cap of 3 the
                           WEAK family (cadence STALL_MAX = 4, three triggers
                           inside LOST_MAX = 13) had every one of its rungs
                           suppressed and reached the end of the walk having
                           attempted no physical recovery at all. See
                           ESCAPE_SUPPRESS_MAX.
    """
    return bool(gate) and verdict == PUSH_MOVED and suppressed < cap


def pair_signal(before, after, thresh=None):
    """One ORB match on the two frames around a push -> the journal's row.

    -> {"inliers": int|None, "kp_before": int, "kp_after": int,
        "verdict": "moved"|"blocked"|None}

    `pair_inliers` is IMPORTED from tools/crawl.py, which is where it was
    validated against the user's own labels, and NOT reimplemented here.
    CLAUDE.md records what a reimplementation of a project function costs: the
    localiser mirror that used a raw `len(bf.match(...))` instead of
    `places.match_count`'s Hamming filter scored the reference set 3 of 9 where
    the original scores 9 of 9, and a whole finding was written on it.

    The features come from `places.keypoints`, whose `_as_gray` masks the
    compass, the quest list and the coin -- pixel-identical HUD that would hand
    any two frames free matches and bias the answer toward BLOCKED.

    `thresh=None` resolves the constant at CALL time, so an A/B or a test can
    move `PUSH_BLOCKED_MIN_INLIERS` and be obeyed (10.18).
    """
    import places
    import tools.crawl as crawl
    t = PUSH_BLOCKED_MIN_INLIERS if thresh is None else thresh
    ka, da = places.keypoints(before)
    kb, db = places.keypoints(after)
    n_a = 0 if ka is None else len(ka)
    n_b = 0 if kb is None else len(kb)
    inliers = crawl.pair_inliers(ka, da, kb, db)
    return {"inliers": inliers, "kp_before": n_a, "kp_after": n_b,
            "verdict": push_verdict(inliers, n_a, n_b, t)}


def _strong_ahead(chain, img, k, n):'''),
 # ------------------------------------------------------- the push contract
 ('''        push(mag, secs)         ONE continuous forward push, mag > 0 = forward''',
  '''        push(mag, secs)         ONE continuous forward push, mag > 0 = forward
                                -> this push's MOVED/BLOCKED signal, or None
                                   when there is none (patch59). A stub that
                                   returns None is a stub with no signal, which
                                   is exactly today's behaviour.'''),
 # -------------------------------------------------------- the push wrapper
 ('''            # Forwarded ONLY when there is one, so the shipped call is the
            # call it has always been -- four tests stub walk_leg with today's
            # signature, and passing on_release=None to them is a TypeError.
            extra = {} if on_release is None else {"on_release": on_release}
            return _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                                label="chain push", log=log, step_sec=secs,
                                **extra)''',
  '''            # `on_release` is forwarded ONLY when there is one: it is the
            # settle probe's hook, it is off unless the environment arms it,
            # and passing on_release=None to a stub written before patch54 is
            # a TypeError.
            #
            # `on_pair` is forwarded ALWAYS, and that is a deliberate change to
            # the shipped call (patch59). The signal is journalled on every
            # push whether or not ESCAPE_GATE is on -- that is the whole point
            # of part 3, since a measurement taken only on the arm that uses it
            # cannot be compared -- so there is nothing to make it conditional
            # ON. The one stub in the tree that had to grow the parameter is in
            # tests/routing/test_chain_walk.py's DefaultConsoleWrappers.
            #
            # WHAT IT COSTS, STATED HONESTLY: one ORB match per push (~28 ms)
            # on two frames walk_leg has already captured. No extra capture, no
            # extra push, no console call -- which is why the off arm's event
            # list is unchanged. But this closure is shared, and the forward
            # push call `push(PUSH_MAG, ...)` is made from FOUR places in this
            # file: the two tracked forward pushes whose signal reaches the
            # journal, plus DOOR_STOP_EXTRA_PUSH (once per walk at one stop)
            # and the turn-retry (up to TURN_RETRY_MAX per stop). Those two
            # discard the return, so the match still runs and its answer is
            # thrown away -- up to four extra matches a walk, ~112 ms. That is
            # a cost paid, not a cost avoided, and it is written here rather
            # than left to be discovered.
            sig = {}

            def _pair(before, after, _sig=sig):
                # A MEASUREMENT MUST NEVER KILL A LIVE WALK. The failure is
                # recorded in the row rather than swallowed, so it cannot look
                # like "there was no signal here" -- a silent no-op and a
                # working path with identical output is 10.1's first entry.
                try:
                    _sig.update(pair_signal(before, after) or {})
                except Exception as exc:
                    _sig.update({"error": repr(exc)})
                    log(f"        push signal FAILED, the walk carries on: "
                        f"{exc!r}")

            extra = {} if on_release is None else {"on_release": on_release}
            _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                         label="chain push", log=log, step_sec=secs,
                         on_pair=_pair, **extra)
            # walk_leg's own (spent, best, hazards) was already discarded by
            # every caller of this wrapper; the signal replaces it as the
            # return value rather than being smuggled out through a closure.
            return sig or None'''),
 # ------------------------------------------------------------- the counter
 ('''    blind_looks_total = 0       # ... and over the whole walk, for the report''',
  '''    blind_looks_total = 0       # ... and over the whole walk, for the report
    escape_suppressed = 0       # ESCAPE_GATE suppressions in THIS blockage;
                                # reset wherever the ladder itself re-arms'''),
]

edits_c += [
 # ------------------------------------------------------------ escape() + gate
 ('''    def escape():
        """One escape. Jump first, then sidesteps alternating LEFT, RIGHT, ...

        Jump first because it moves nothing sideways, which is what a passage
        with stools on one side and a wall on the other requires; measured
        escape outcomes against real blockers were None, None, jump, None, None,
        None, wait, jump (§8(g)).
        """
        nonlocal escapes
        which = escapes % 4          # the ladder CYCLES: jump, back, left, right, jump, ...
        escapes += 1
        if which == 0:
            # Jump comes round again: the one arrival that beat the patron
            # wedge (batch 5c trial 2) had a jump; batch 5e trial 7, whose jump
            # had fired earlier in the street, got only sidesteps there.
            jump()
            return "escape:jump"
        if which == 1:
            back(PUSH_MAG, BACK_SEC)
            return "escape:back"
        nonlocal detour_side, detour_until
        side = LEFT if which == 2 else RIGHT
        secs = ESCAPE_STRAFE_SEC * (2 if (side > 0 and detour_side is not None and detour_side < 0) else 1)
        strafe(side * ESCAPE_STRAFE_MAG, secs)
        detour_side, detour_until = side, k + DETOUR_TARGETS
        return "escape:left" if side < 0 else "escape:right"''',
  '''    def escape(order=None):
        """One escape, taking the rung ORDER it should cycle through.

        Jump first in the DEFAULT order because it moves nothing sideways,
        which is what a passage with stools on one side and a wall on the other
        requires; measured escape outcomes against real blockers were None,
        None, jump, None, None, None, wait, jump (§8(g)). At the bar-entrance
        stop the order has no jump at all -- see BAR_ESCAPE_RUNGS: there it is
        the rung that always went first and never worked, 0 of 7, losing the
        picture 7 of 7.

        `order` defaults to DEFAULT_ESCAPE_RUNGS, so a caller that has not been
        told about regions gets exactly the ladder that has always shipped.
        """
        nonlocal escapes
        rungs = DEFAULT_ESCAPE_RUNGS if not order else tuple(order)
        # THE LADDER CYCLES its order, as `escapes % 4` did over
        # jump/back/left/right. The modulus is the order's own length, so a
        # three-rung order cycles three.
        rung = rungs[escapes % len(rungs)]
        escapes += 1
        if rung == "jump":
            # Jump comes round again: the one arrival that beat the patron
            # wedge (batch 5c trial 2) had a jump; batch 5e trial 7, whose jump
            # had fired earlier in the street, got only sidesteps there.
            jump()
            return "escape:jump"
        if rung == "back":
            back(PUSH_MAG, BACK_SEC)
            return "escape:back"
        nonlocal detour_side, detour_until
        side = LEFT if rung == "left" else RIGHT
        secs = ESCAPE_STRAFE_SEC * (2 if (side > 0 and detour_side is not None and detour_side < 0) else 1)
        strafe(side * ESCAPE_STRAFE_MAG, secs)
        detour_side, detour_until = side, k + DETOUR_TARGETS
        return "escape:left" if side < 0 else "escape:right"

    def escape_now(sig):
        """ONE escape TRIGGER: a rung and its order, or a suppression.

        -> (action, escaped, row). All three escape triggers go through here so
        the decision exists in ONE place; with ESCAPE_GATE off it resolves to
        `escape()` over the default order, which is the call the three sites
        made before this patch.

        `escaped` is what the iteration sets on itself, and a suppression does
        NOT set it: nothing displaced the character between the fit and now, so
        the lateral correction computed from that fit is still valid, and so is
        patch57's pitch press, which blocks on `escaped or escaped_prev`. That
        is the same reasoning those guards are built on, applied in the
        direction that gives the correction back.

        A suppression touches NOTHING ELSE -- not `lost`, not `misses`, not
        `stalls`, not `k`. The iteration count of a blockage is identical
        either way, so this cannot push a walk into LOST_MAX or NO_PROGRESS_MAX
        that would not have got there anyway. What it CAN do, unbounded, is
        reach LOST_MAX having fired no rung at all; ESCAPE_SUPPRESS_MAX is
        derived from the two trigger cadences so that it cannot.
        """
        nonlocal escape_suppressed
        verdict = (sig or {}).get("verdict")
        order = escape_rungs(k, ESCAPE_GATE, BAR_ESCAPE_FROM_K,
                             BAR_ESCAPE_TO_K, BAR_ESCAPE_RUNGS,
                             DEFAULT_ESCAPE_RUNGS)
        if escape_is_suppressed(ESCAPE_GATE, verdict, escape_suppressed,
                                ESCAPE_SUPPRESS_MAX):
            escape_suppressed += 1
            return (ESCAPE_SKIPPED_ACTION, False,
                    {"rung": None, "verdict": verdict, "k": k,
                     "order": list(order), "suppressed": escape_suppressed,
                     "cap": ESCAPE_SUPPRESS_MAX})
        rung = escape(order)
        return (rung, True,
                {"rung": rung, "verdict": verdict, "k": k,
                 "order": list(order), "suppressed": escape_suppressed,
                 "cap": ESCAPE_SUPPRESS_MAX})'''),
 # --------------------------------------------------------- the ladder re-arm
 ('''        if action is not None and action.startswith(PROGRESS_ACTIONS):
            escapes = 0''',
  '''        if action is not None and action.startswith(PROGRESS_ACTIONS):
            escapes = 0
            # ... and the gate's suppression budget, on the same event and for
            # the same reason: the budget is PER BLOCKAGE, and a progress
            # action is this loop's own definition of a blockage ending.
            escape_suppressed = 0'''),
 # ------------------------------------------- the rescue's own counter reset
 # "rescued" starts with no PROGRESS_ACTIONS prefix, so the re-arm above never
 # sees it. The rescue resets ten siblings including `escapes`; leaving the
 # gate's budget spent there would carry it into ground the rescue has just
 # re-approached, which is the one place a fresh ladder matters most.
 ('''                    lost = 0
                    misses = 0
                    stalls = 0
                    blind = 0
                    escapes = 0
                    unverified_turn = False
                    early_stop = False''',
  '''                    lost = 0
                    misses = 0
                    stalls = 0
                    blind = 0
                    escapes = 0
                    # patch59, beside `escapes` and for the same reason: the
                    # suppression budget is per BLOCKAGE, the rescue has just
                    # ended one, and "rescued" carries no PROGRESS_ACTIONS
                    # prefix so the top-of-loop re-arm never catches it.
                    escape_suppressed = 0
                    unverified_turn = False
                    early_stop = False'''),
 # ------------------------------------------------- the per-iteration signal
 ('''        settle_rows = None       # this iteration's probe samples, if armed''',
  '''        settle_rows = None       # this iteration's probe samples, if armed
        push_sig = None          # ... and this iteration's MOVED/BLOCKED
                                 # measurement, from the frames walk_leg holds
                                 # around the push. None on an iteration that
                                 # did not push, which is why a turn-only stop
                                 # and a blind look can never be gated.'''),
 ('''                push(PUSH_MAG, PUSH_SEC, on_release=_sample)
            else:
                push(PUSH_MAG, PUSH_SEC)''',
  '''                push_sig = push(PUSH_MAG, PUSH_SEC, on_release=_sample)
            else:
                push_sig = push(PUSH_MAG, PUSH_SEC)'''),
 # ------------------------------------------------------ the escape row reset
 ('''        escaped = False
        if regressed:''',
  '''        escaped = False
        escape_row = None        # this iteration's escape decision, journalled
        if regressed:'''),
 # ------------------------------------------------------ the three triggers
 ('''                misses += 1
                if misses >= MISS_MAX:
                    action = escape()
                    escaped = True
                    misses = 0
                else:
                    action = "miss"''',
  '''                misses += 1
                if misses >= MISS_MAX:
                    action, escaped, escape_row = escape_now(push_sig)
                    misses = 0
                else:
                    action = "miss"'''),
 ('''                if stalls >= STALL_MAX:
                    action = escape()
                    escaped = True
                    stalls = 0
                else:
                    action = "weak"''',
  '''                if stalls >= STALL_MAX:
                    action, escaped, escape_row = escape_now(push_sig)
                    stalls = 0
                else:
                    action = "weak"'''),
 ('''                if stalls >= STALL_MAX:
                    action = escape()
                    escaped = True
                    stalls = 0
                else:
                    action = "stalled"''',
  '''                if stalls >= STALL_MAX:
                    action, escaped, escape_row = escape_now(push_sig)
                    stalls = 0
                else:
                    action = "stalled"'''),
 # ------------------------------------------------------------------ the row
 ('''               **({"settle": settle_rows} if settle_rows else {}),''',
  '''               **({"settle": settle_rows} if settle_rows else {}),
               # patch59, ON EITHER ARM. `push_signal` is the measurement --
               # the inlier count, both frames' keypoint totals and the
               # verdict -- and `escape` is the decision, with the k and the
               # rung order it was made from so a firing outside the bar
               # stretch is not read as evidence about the bar.
               **({"push_signal": push_sig} if push_sig else {}),
               **({"escape": escape_row} if escape_row else {}),'''),
]

# ----------------------------------------------------------------- the tests
STUB = '''        def walk_leg(lx, ly, seconds, capture, read_heading, label="",
                     log=print, step_sec=None, on_pair=None):
            # `on_pair` (patch59) is forwarded on EVERY push, so a stub that
            # does not accept it is a TypeError on the first push. It is
            # accepted and ignored here: this class is about the AXES, and the
            # signal has its own tests below.
            self.t[0] += seconds
'''

NEW_TESTS = '''class _SignalRig(Rig):
    """A Rig whose push() returns a SCRIPTED moved/blocked signal.

    THE SEAM IS push()'s RETURN VALUE. On the live path the default wrapper
    hands `slow_traverse.walk_leg` an `on_pair` hook, turns the frame pair it
    already holds into one ORB match, and returns the verdict. The plain Rig
    returns None -- no signal -- which is why every test written before patch59
    is untouched by it, and this subclass is the only way a walk-level test can
    say "that push moved".
    """

    def __init__(self, chain, signals=(), default_signal=None, table_at=None):
        super().__init__(chain, table_at=table_at)
        self._signals = list(signals)
        self.default_signal = default_signal

    def push(self, mag, secs):
        super().push(mag, secs)
        return self._signals.pop(0) if self._signals else self.default_signal


MOVED_SIG = {"verdict": "moved", "inliers": 11,
             "kp_before": 900, "kp_after": 900}
BLOCKED_SIG = {"verdict": "blocked", "inliers": 160,
               "kp_before": 900, "kp_after": 900}
NO_SIGNAL = {"verdict": None, "inliers": None, "kp_before": 40, "kp_after": 40}


class EscapeGate(unittest.TestCase):
    """(p) patch59: the ladder's rung at the BAR-ENTRANCE STOP, and no rung
    when the push MOVED.

    The user, watching the stream: "the navigation is jumping around in the bar
    area. getting onto the bar and ramming into it and somehow ending up at the
    mini game table."

    THE EVIDENCE, regenerated by agent_progress/closed-loop/escape_gate/census.py
    over 60 journals (the first draft's hand-copied table had three wrong rows):
    at k = 129 -- and it IS one waypoint, every failing bar jump is there --
    jump is 0 of 7 with the picture lost 7 of 7, back 0 of 7, left 7 of 7. At
    k 130-139 jump is 13 of 15, the best rung in the whole dataset, which is
    why the window is 129..129 and not the census bucket's 115-150.

    AND LEFT'S 7 OF 7 IS AN ARTEFACT OF THE ORDER, so this class does not pin
    it as a finding. The ladder is jump, back, left, right and it STOPS WHEN IT
    WORKS; all seven blockages are the identical triple and left is never tried
    first. What is pinned is the supported half -- jump always went first and
    never worked HERE, and always went first and did work elsewhere.

    The second rule is the gate: a push whose own before/after frames say the
    character MOVED does not earn an escape at all.
    """

    # --- the constants, as LITERALS (10.11: a test that reads the constant it
    # --- guards rises with it and passes for ever) -----------------------
    def test_the_constants_are_the_censuss_own_literals(self):
        self.assertIs(chain_walk.ESCAPE_GATE, False, "it ships OFF")
        self.assertEqual(chain_walk.BAR_ESCAPE_FROM_K, 129)
        self.assertEqual(chain_walk.BAR_ESCAPE_TO_K, 129)
        self.assertEqual(chain_walk.BAR_ESCAPE_FROM_K,
                         chain_walk.BAR_ESCAPE_TO_K,
                         "A RANGE OF ONE: every failing bar jump is at k=129, "
                         "and at 130-139 jump is 13 of 15 -- the best rung in "
                         "the dataset. A wider window bans it where it works")
        self.assertEqual(chain_walk.BAR_ESCAPE_RUNGS, ("left", "right", "back"))
        self.assertNotIn("jump", chain_walk.BAR_ESCAPE_RUNGS,
                         "jump always went FIRST at this stop and is 0 of 7, "
                         "with the picture lost entirely on 7 of 7 -- the one "
                         "half of the census the ladder order does not confound")
        self.assertEqual(chain_walk.DEFAULT_ESCAPE_RUNGS,
                         ("jump", "back", "left", "right"),
                         "today's escapes % 4, unchanged")
        self.assertEqual(chain_walk.PUSH_BLOCKED_MIN_INLIERS, 88,
                         "the midpoint of the measured gap 28 | 148")
        self.assertEqual(chain_walk.ESCAPE_SUPPRESS_MAX, 2,
                         "DERIVED: the weak family gets only three triggers "
                         "inside LOST_MAX, so a cap of three removed every "
                         "rung it would ever have fired")
        self.assertLess(chain_walk.ESCAPE_SUPPRESS_MAX, 3,
                        "the shortest trigger sequence any family gets inside "
                        "its own budget is THREE (STALL_MAX cadence against "
                        "LOST_MAX): the cap must leave one real rung")
        self.assertEqual(chain_walk.ESCAPE_SKIPPED_ACTION, "escape-skipped")
        self.assertFalse(chain_walk.ESCAPE_SKIPPED_ACTION.startswith("escape:"),
                         "tools/collision_census.py counts waste with "
                         "startswith('escape:'); a rung NOT taken is not waste")
        self.assertFalse(
            chain_walk.ESCAPE_SKIPPED_ACTION.startswith(
                chain_walk.PROGRESS_ACTIONS),
            "a suppression is not evidence the walk moved on")

    def test_the_cap_is_derived_from_the_loops_own_two_cadences(self):
        # THE ARITHMETIC THE CONSTANT CLAIMS, done here rather than trusted.
        # Both trigger families increment `lost` every iteration under one
        # budget; the weak family's cadence is the longer one, so it gets the
        # fewest triggers, and the cap must be strictly under that count.
        triggers = len(range(chain_walk.STALL_MAX, chain_walk.LOST_MAX,
                             chain_walk.STALL_MAX))
        self.assertEqual(triggers, 3,
                         "STALL_MAX=4 against LOST_MAX=13 gives lost=4,8,12")
        self.assertLess(chain_walk.ESCAPE_SUPPRESS_MAX, triggers,
                        "at a cap equal to this the weak family fires NO rung "
                        "at all before the walk ends")

    # --- the three predicates, driven directly ---------------------------
    def test_the_rung_order_is_the_default_everywhere_but_the_bar(self):
        R = chain_walk.escape_rungs
        bar, dflt = ("left", "right", "back"), ("jump", "back", "left", "right")
        self.assertEqual(R(129, True, 129, 129, bar, dflt), bar, "the stop")
        self.assertEqual(R(128, True, 129, 129, bar, dflt), dflt, "one below")
        self.assertEqual(R(130, True, 129, 129, bar, dflt), dflt,
                         "one above -- and jump is 13 of 15 from here on")
        self.assertEqual(R(115, True, 129, 129, bar, dflt), dflt,
                         "the census BUCKET's low edge is not the window")
        self.assertEqual(R(150, True, 129, 129, bar, dflt), dflt)
        self.assertEqual(R(129, False, 129, 129, bar, dflt), dflt,
                         "with the flag OFF the bar is not special")
        self.assertEqual(R(None, True, 129, 129, bar, dflt), dflt,
                         "no estimate is not a region")
        # inclusive at both ends, shown on a window wider than one
        self.assertEqual(R(115, True, 115, 150, bar, dflt), bar, "inclusive low")
        self.assertEqual(R(150, True, 115, 150, bar, dflt), bar, "inclusive high")

    def test_the_verdict_sits_between_the_two_measured_populations(self):
        V = chain_walk.push_verdict
        # BLOCKED: steps 2-6 of overnight/crawl_labelled.jsonl, the pushes that
        # did not move the character off the desk.
        for inl in (148, 153, 154, 164, 166):
            self.assertEqual(V(inl, 900, 900, 88), "blocked", inl)
        # MOVED: steps 7-10, AND step 1 (28), which is labelled `desk` because
        # it travelled INTO the desk -- crawl.py's labels name what was hit.
        for inl in (10, 11, 23, 28):
            self.assertEqual(V(inl, 900, 900, 88), "moved", inl)
        # No fit, on frames rich enough to have produced one, IS the moved
        # population (two of the six clean rows read None).
        self.assertEqual(V(None, 900, 900, 88), "moved")
        # The boundary is the threshold itself, both sides of it.
        self.assertEqual(V(88, 900, 900, 88), "blocked")
        self.assertEqual(V(87, 900, 900, 88), "moved")

    def test_too_few_keypoints_is_NO_SIGNAL_and_never_MOVED(self):
        # inliers <= min(keypoints), so under the floor BLOCKED is unreachable
        # and a low count is a number that is low everywhere.
        V = chain_walk.push_verdict
        self.assertIsNone(V(None, 87, 900, 88), "the BEFORE frame is too thin")
        self.assertIsNone(V(None, 900, 87, 88), "the AFTER frame is too thin")
        self.assertIsNone(V(10, 40, 40, 88))
        self.assertEqual(V(None, 88, 88, 88), "moved",
                         "at the floor exactly, the signal counts")

    def test_only_a_positive_MOVED_earns_a_suppression_and_it_is_bounded(self):
        Sup = chain_walk.escape_is_suppressed
        self.assertTrue(Sup(True, "moved", 0, 2))
        self.assertTrue(Sup(True, "moved", 1, 2))
        self.assertFalse(Sup(True, "moved", 2, 2), "the bound")
        self.assertFalse(Sup(True, "blocked", 0, 2), "BLOCKED fires the rung")
        self.assertFalse(Sup(True, None, 0, 2), "NO SIGNAL fires the rung")
        self.assertFalse(Sup(False, "moved", 0, 2), "the flag")
'''

NEW_TESTS += '''
    # --- walk-level ------------------------------------------------------
    def _run(self, rig, gate, from_k=None, to_k=None, cap=None, **kw):
        """Run one walk with the gate's knobs set, restoring what was SHIPPED.

        Captured, never restored to a literal: two A/B harnesses on this project
        put back the default that was current on the day they were written and
        installed an arm while looking like tidiness.
        """
        names = {"ESCAPE_GATE": gate}
        if from_k is not None:
            names["BAR_ESCAPE_FROM_K"] = from_k
        if to_k is not None:
            names["BAR_ESCAPE_TO_K"] = to_k
        if cap is not None:
            names["ESCAPE_SUPPRESS_MAX"] = cap
        old = {n: getattr(chain_walk, n) for n in names}
        for n, v in names.items():
            setattr(chain_walk, n, v)
        try:
            return rig.go(**kw)
        finally:
            for n, v in old.items():
                setattr(chain_walk, n, v)

    @staticmethod
    def _rungs(res):
        return [f["action"] for f in res["fixes"]
                if f["action"].startswith("escape:")]

    def test_with_the_gate_OFF_not_one_console_call_changes(self):
        # THE ASSERTION IS THE EVENT LIST ITSELF, not what I expect to be in
        # it: the off arm must be today's build, and a signal on every push
        # must cost no capture, no push and no rung.
        base = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)), table_at=14)
        base_res = base.go()
        rig = _SignalRig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                         default_signal=MOVED_SIG, table_at=14)
        res = self._run(rig, gate=False, from_k=0, to_k=0, cap=99)
        self.assertEqual(rig.events, base.events,
                         "the OFF arm's console calls must be identical")
        self.assertEqual([f["action"] for f in res["fixes"]],
                         [f["action"] for f in base_res["fixes"]])
        self.assertEqual(self._rungs(res),
                         ["escape:jump", "escape:back", "escape:left"])

    def test_the_signal_is_journalled_with_the_flag_OFF(self):
        # Part 3 changes no behaviour and must be measurable on BOTH arms; a
        # measurement taken only on the arm that uses it cannot be compared.
        rig = _SignalRig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                         default_signal=MOVED_SIG, table_at=14)
        res = self._run(rig, gate=False, from_k=0, to_k=0)
        rows = [f for f in res["fixes"] if f.get("push_signal")]
        self.assertTrue(rows, "no push signal reached the journal")
        self.assertEqual(rows[0]["push_signal"], MOVED_SIG)
        self.assertNotIn(chain_walk.ESCAPE_SKIPPED_ACTION,
                         [f["action"] for f in res["fixes"]],
                         "OFF, a MOVED push must still get its rung")
        fired = [f for f in res["fixes"] if f.get("escape")]
        self.assertTrue(fired, "the escape decision is journalled too")
        self.assertEqual(fired[0]["escape"]["rung"], "escape:jump")
        self.assertEqual(fired[0]["escape"]["verdict"], "moved",
                         "the row records what the signal SAID even when the "
                         "flag ignored it -- that is instrument (d)")

    def test_ON_at_the_bar_stop_the_first_rung_is_LEFT_and_jump_never_fires(self):
        # THE WINDOW IS PINNED ON THE WALK'S OWN k, BOTH EDGES ON IT. This toy
        # walk sits at k=0 throughout, so from_k = to_k = 0 is the live k
        # exactly -- which is what makes an off-by-one at the CALL SITE
        # visible. `escape_rungs(k + 1, ...)` there lands outside the window
        # and the ladder reverts to jump-first; the wider ranges the first
        # draft used (0..3) swallowed that mutant whole.
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)), table_at=14)
        res = self._run(rig, gate=True, from_k=0, to_k=0)
        self.assertEqual(self._rungs(res),
                         ["escape:left", "escape:right", "escape:back"])
        self.assertEqual(rig.count("jump"), 0,
                         "jump at this stop is 0 of 7 and loses the picture 7 of 7")
        rows = [f for f in res["fixes"] if f.get("escape")]
        self.assertTrue(rows)
        self.assertEqual(rows[0]["escape"]["order"], ["left", "right", "back"])
        self.assertEqual([r["escape"]["k"] for r in rows], [0, 0, 0],
                         "the row records the k the ORDER was chosen from, so "
                         "instrument (e) can throw out a firing that was not "
                         "really at the stop")

    def test_the_bar_ladder_CYCLES_ITS_OWN_THREE_rungs(self):
        # THE MODULUS IS THE ORDER'S OWN LENGTH, not a hard-wired 4. Indexing a
        # three-rung order with `escapes % 4` walks off the end on the FOURTH
        # firing -- an IndexError in a live walk, at the one stop this patch
        # exists for, and every test that stops at three rungs lets that mutant
        # through. This one drives a fourth.
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)), table_at=20)
        res = self._run(rig, gate=True, from_k=0, to_k=0)
        self.assertEqual(self._rungs(res),
                         ["escape:left", "escape:right", "escape:back",
                          "escape:left"],
                         "the fourth firing comes round to left again")
        self.assertEqual(rig.count("jump"), 0)

    def test_ON_one_waypoint_either_side_the_ladder_is_unchanged(self):
        # The OTHER edge of the same off-by-one: a window that starts one ABOVE
        # the walk's k must NOT be entered. `escape_rungs(k + 1, ...)` at the
        # call site enters it and the assertion below fails.
        rig = Rig(FakeChain(4, default=Fix(k=0, scale=0.5)), table_at=14)
        res = self._run(rig, gate=True, from_k=1, to_k=950)
        self.assertEqual(self._rungs(res),
                         ["escape:jump", "escape:back", "escape:left"])
        self.assertEqual(rig.count("jump"), 1)
        first = next(f for f in res["fixes"] if f.get("escape"))
        self.assertEqual(first["escape"]["order"],
                         ["jump", "back", "left", "right"])
        self.assertEqual(first["escape"]["k"], 0)

    def test_ON_a_push_that_MOVED_suppresses_the_escape_and_records_why(self):
        # The cap is put out of reach here so the SUPPRESSION is what is being
        # measured; the bound has its own test below.
        rig = _SignalRig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                         default_signal=MOVED_SIG, table_at=14)
        res = self._run(rig, gate=True, from_k=900, to_k=950, cap=99)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(self._rungs(res), [], "no rung was earned")
        self.assertEqual(rig.count("jump"), 0)
        self.assertEqual(rig.strafes(), [])
        self.assertEqual([e for e in rig.events if e[0] == "back"], [])
        self.assertEqual(acts.count("escape-skipped"), 3, "one per trigger")
        row = next(f for f in res["fixes"] if f["action"] == "escape-skipped")
        self.assertIsNone(row["escape"]["rung"])
        self.assertEqual(row["escape"]["verdict"], "moved")
        self.assertEqual(row["escape"]["suppressed"], 1)
        self.assertEqual(row["escape"]["cap"], 99)

    def test_ON_a_push_that_was_BLOCKED_still_gets_its_rung(self):
        rig = _SignalRig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                         default_signal=BLOCKED_SIG, table_at=14)
        res = self._run(rig, gate=True, from_k=900, to_k=950)
        self.assertEqual(self._rungs(res),
                         ["escape:jump", "escape:back", "escape:left"])
        self.assertNotIn("escape-skipped", [f["action"] for f in res["fixes"]])

    def test_ON_a_push_with_NO_SIGNAL_falls_through_to_todays_behaviour(self):
        # Too few keypoints to judge: never "moved", always today's ladder.
        rig = _SignalRig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                         default_signal=NO_SIGNAL, table_at=14)
        res = self._run(rig, gate=True, from_k=900, to_k=950)
        self.assertEqual(self._rungs(res),
                         ["escape:jump", "escape:back", "escape:left"])
        rows = [f for f in res["fixes"] if f.get("push_signal")]
        self.assertTrue(rows, "a no-signal push is still journalled")
        self.assertIsNone(rows[0]["push_signal"]["verdict"])

    def test_the_last_resort_bound_holds_after_ESCAPE_SUPPRESS_MAX(self):
        # A loop that can never escape is worse than one that escapes too
        # often. At the SHIPPED cap the third trigger takes its rung.
        rig = _SignalRig(FakeChain(4, default=Fix(k=0, scale=0.5)),
                         default_signal=MOVED_SIG, table_at=20)
        res = self._run(rig, gate=True, from_k=900, to_k=950)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("escape-skipped"), 2)
        self.assertEqual(self._rungs(res), ["escape:jump", "escape:back"],
                         "the third trigger escapes anyway, and the fourth")
        self.assertEqual(rig.count("jump"), 1)
        skipped = [f["escape"]["suppressed"] for f in res["fixes"]
                   if f["action"] == "escape-skipped"]
        self.assertEqual(skipped, [1, 2], "the budget counts up, once each")

    def test_the_WEAK_fit_family_still_gets_a_real_rung_before_the_walk_ends(self):
        # THE BOUND'S REASON TO BE 2 AND NOT 3, driven rather than reasoned
        # about. A fit that is PRESENT but under FIX_MIN_INLIERS takes the
        # `weak` branch, whose cadence is STALL_MAX (4) against a LOST_MAX of
        # 13 -- three triggers, not four. At a cap of 3 every one of them was
        # suppressed and the walk ended having attempted NO physical recovery,
        # with a failure line identical to today's.
        def run(cap):
            rig = _SignalRig(
                FakeChain(4, default=Fix(k=0, scale=0.5, inliers=10)),
                default_signal=MOVED_SIG, table_at=None)
            res = self._run(rig, gate=True, from_k=900, to_k=950, cap=cap)
            return self._rungs(res), rig
        rungs, rig = run(chain_walk.ESCAPE_SUPPRESS_MAX)
        self.assertTrue(rungs, "the weak family must still get a real rung")
        self.assertEqual(rig.count("jump"), 1, "and it must reach the console")
        # ANTI-VACUITY, and it is the whole finding: at a cap of 3 the same
        # fixture fires nothing at all. If this stops failing, the cadences
        # have changed and the derivation above needs redoing.
        self.assertEqual(run(3)[0], [],
                         "at a cap of 3 this family fires NO rung -- that is "
                         "why ESCAPE_SUPPRESS_MAX is derived and not borrowed")

    def test_the_suppression_budget_is_PER_BLOCKAGE_not_per_walk(self):
        # The ladder re-arms on a PROGRESS_ACTION; so does this. Without that
        # line one early moved-push blockage spends the whole walk's budget and
        # the bar gets none, while the trial still counts as an on-arm trial.
        #
        # THE FIRST VERSION OF THIS TEST WAS VACUOUS, and the mutant is what
        # said so: deleting the reset left the whole suite green, because the
        # walk it drove never advanced, so no PROGRESS_ACTION ever fired and
        # the line under test could not run. A guard reachable only through a
        # path the test never takes is this project's signature shape, arrived
        # at in the test rather than in the code.
        #
        # This walk STALLS, suppresses, ADVANCES, and stalls again, at cap 1:
        # with the reset each blockage gets its own suppression; without it the
        # second blockage escapes on its very first trigger.
        fixes = ([Fix(k=0, scale=0.5)] * 4          # blockage 1
                 + [Fix(k=1, scale=1.0)]            # ... broken by an advance
                 + [Fix(k=1, scale=0.5)] * 8)       # blockage 2
        rig = _SignalRig(FakeChain(30, fixes=fixes,
                                   default=Fix(k=1, scale=0.5)),
                         default_signal=MOVED_SIG, table_at=None)
        res = self._run(rig, gate=True, from_k=900, to_k=950, cap=1)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[4], "advanced",
                         "ANTI-VACUITY: the walk must actually make progress "
                         "between the two blockages, or the reset never runs "
                         "and this test cannot fail")
        skips = [(f["iteration"], f["escape"]["suppressed"])
                 for f in res["fixes"] if f["action"] == "escape-skipped"]
        self.assertEqual(skips, [(4, 1), (9, 1)],
                         "one suppression per blockage, each counting from 1")
        first_rung = next(i for i, a in enumerate(acts)
                          if a.startswith("escape:"))
        self.assertGreater(first_rung, 8,
                           "no rung fires until the SECOND blockage has spent "
                           "its own budget")

    def test_a_suppressed_escape_leaves_patch57s_PITCH_press_alone(self):
        # THE COMPOSITION, pinned rather than reasoned about. patch57 blocks
        # its press on `escaped or escaped_prev`, because a rung's hop or
        # sidestep displaces the character between measuring dy and acting on
        # it. A SUPPRESSION displaces nothing, so `escaped` stays False and the
        # correction survives -- which is the direction that gives it back, and
        # is exactly what a mutant setting escaped=True on the suppression
        # branch would silently take away. Both flags ship OFF; the calibration
        # here is the class's own (PitchCorrection's precedent).
        names = {"PITCH_CORRECT": True, "PITCH_MODE": "act",
                 "PITCH_STEP_PX": 30.0, "PITCH_DOWN_DY_SIGN": -1}
        old = {n: getattr(chain_walk, n) for n in names}
        for n, v in names.items():
            setattr(chain_walk, n, v)
        try:
            rig = _SignalRig(
                FakeChain(4, default=Fix(k=0, scale=0.5, dy=300.0)),
                default_signal=MOVED_SIG, table_at=14)
            res = self._run(rig, gate=True, from_k=900, to_k=950, cap=99)
            acts = [f["action"] for f in res["fixes"]]
            self.assertEqual(acts.count("escape-skipped"), 3,
                             "ANTI-VACUITY: the suppression must have fired")
            self.assertEqual(self._rungs(res), [],
                             "and no rung, so nothing else could have blocked "
                             "the press")
            rows = [f["pitch"] for f in res["fixes"]
                    if f["action"] == "escape-skipped" and f.get("pitch")]
            self.assertTrue(rows, "a suppressed iteration still gets a row")
            self.assertTrue(any(r["acted"] for r in rows),
                            "and the press is NOT blocked: a suppression moved "
                            "nothing, so the dy it was measured from stands")
        finally:
            for n, v in old.items():
                setattr(chain_walk, n, v)
'''

NEW_TESTS += '''
    def test_the_LOST_RESCUE_re_arms_the_suppression_budget(self):
        # "rescued" starts with NO PROGRESS_ACTIONS prefix, so the top-of-loop
        # re-arm never sees it. The rescue resets ten sibling counters --
        # `escapes` among them -- and the first draft left the gate's budget
        # out of that list: a walk that spent it before the rescue carried an
        # empty ladder into ground the rescue had just re-approached, which is
        # the one place a fresh ladder matters most.
        class _RescueSignalRig(_SignalRig):
            def at_table(self, img):
                self.events.append(("at_table", img.n, False))
                return False

        ch = ScriptedWide(30, [Fix(k=i) for i in range(1, 11)],
                          default=None, lookback=None,
                          at_hint={0: [Fix(k=13, inliers=120),
                                       Fix(k=13, inliers=120),
                                       Fix(k=13, inliers=170)]})
        rig = _RescueSignalRig(ch, default_signal=MOVED_SIG, table_at=None)
        res = self._run(rig, gate=True, from_k=900, to_k=950, cap=1,
                        time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("rescued"), 1,
                         "ANTI-VACUITY: the rescue must actually fire, or the "
                         "line under test never runs and this cannot fail")
        i = acts.index("rescued")
        before = [f["escape"]["suppressed"] for f in res["fixes"][:i]
                  if f["action"] == "escape-skipped"]
        after = [f["escape"]["suppressed"] for f in res["fixes"][i:]
                 if f["action"] == "escape-skipped"]
        self.assertTrue(before, "the budget was spent before the rescue")
        self.assertTrue(after, "and the walk blocks again after it")
        self.assertEqual(after[0], 1,
                         "the budget counts from 1 again: only the rescue's "
                         "own reset can do this, since 'rescued' carries no "
                         "PROGRESS_ACTIONS prefix")

    # --- the wiring, with the matcher stubbed ----------------------------
    def test_walk_leg_hands_on_pair_the_frames_from_EITHER_SIDE_of_the_push(self):
        # The pair must straddle the stick, or it measures nothing: a hook
        # given two post-push frames would read BLOCKED on every push.
        import slow_traverse as st
        from PIL import Image
        shots = [Image.new("RGB", (8, 8), c) for c in ((1, 1, 1), (2, 2, 2))]
        taken, order, pairs = [], [], []
        real_send, real_sleep = st.ar.send, st.time.sleep

        def capture():
            im = shots[min(len(taken), len(shots) - 1)]
            taken.append(im)
            order.append(("capture", len(taken)))
            return im

        st.ar.send = lambda lines: order.append(("send", tuple(lines)))
        st.time.sleep = lambda s: order.append(("sleep", round(s, 3)))
        try:
            st.walk_leg(0.0, -0.45, 0.40, capture, lambda: 0.0,
                        log=lambda *a: None, step_sec=0.40,
                        on_pair=lambda a, b: pairs.append((a, b)))
        finally:
            st.ar.send, st.time.sleep = real_send, real_sleep
        self.assertEqual(len(pairs), 1, "one call per chunk; a push is one chunk")
        self.assertIs(pairs[0][0], shots[0], "the BEFORE frame")
        self.assertIs(pairs[0][1], shots[1], "the AFTER frame")
        kinds = [o[0] for o in order]
        self.assertLess(kinds.index("capture"), kinds.index("send"),
                        "the BEFORE frame is captured before the stick moves")

    def test_with_no_on_pair_walk_leg_is_the_path_it_has_always_been(self):
        import slow_traverse as st
        from PIL import Image
        shot = Image.new("RGB", (8, 8))
        order = []
        real_send, real_sleep = st.ar.send, st.time.sleep
        st.ar.send = lambda lines: order.append(("send", tuple(lines)))
        st.time.sleep = lambda s: order.append(("sleep", round(s, 3)))
        try:
            out = st.walk_leg(0.0, -0.45, 0.40, lambda: shot, lambda: 0.0,
                              log=lambda *a: None, step_sec=0.40)
        finally:
            st.ar.send, st.time.sleep = real_send, real_sleep
        self.assertEqual([o[0] for o in order],
                         ["send", "sleep", "send", "sleep"],
                         "push, wait, zero, settle -- and nothing else")
        self.assertEqual(len(out), 3, "the (spent, best, hazards) contract")

    def test_pair_signal_masks_the_HUD_and_reports_both_keypoint_totals(self):
        # The matcher is stubbed: the subject is the row and the verdict, not
        # ORB. `pair_inliers` is IMPORTED from tools/crawl.py rather than
        # reimplemented -- a reimplementation of a project function on this
        # project once scored the reference set 3 of 9 where the original
        # scores 9 of 9 -- so the stub goes on the module it lives in.
        import places
        import tools.crawl as crawl
        seen = []

        def keypoints(img, cache_key=None):
            seen.append(img)
            return (["kp"] * (300 if img == "BEFORE" else 400), "des")

        saved = (places.keypoints, crawl.pair_inliers)
        places.keypoints = keypoints
        crawl.pair_inliers = lambda ka, da, kb, db: 160
        try:
            got = chain_walk.pair_signal("BEFORE", "AFTER")
            thin = chain_walk.pair_signal("BEFORE", "AFTER", thresh=500)
        finally:
            places.keypoints, crawl.pair_inliers = saved
        self.assertEqual(seen[:2], ["BEFORE", "AFTER"], "in that order")
        self.assertEqual(got, {"inliers": 160, "kp_before": 300,
                               "kp_after": 400, "verdict": "blocked"})
        self.assertIsNone(thin["verdict"],
                          "thresh is read at CALL time, so an arm can move it "
                          "(10.18) -- and above the keypoints it is no signal")

    def test_the_default_push_wrapper_measures_the_frames_and_returns_them(self):
        # END TO END with ORB stubbed: walk_leg's own before/after frames ->
        # pair_signal -> push()'s return -> the journal row. `push` is NOT
        # injected here, so the wrapper under test is the shipped one.
        import slow_traverse as st
        import places
        import tools.crawl as crawl
        pairs = []

        def walk_leg(lx, ly, seconds, capture, read_heading, label="",
                     log=print, step_sec=None, on_release=None, on_pair=None):
            pairs.append(on_pair)
            on_pair("BEFORE", "AFTER")
            return seconds, 10.0, []

        saved = (st.walk_leg, places.keypoints, crawl.pair_inliers)
        st.walk_leg = walk_leg
        places.keypoints = lambda img, cache_key=None: (
            ["kp"] * (300 if img == "BEFORE" else 400), "des")
        crawl.pair_inliers = lambda ka, da, kb, db: 160
        rig = Rig(FakeChain(3, default=Fix(k=1, scale=1.0)), table_at=3)
        try:
            res = chain_walk.walk(
                rig.chain, rig.capture, lambda: 87.0, log=lambda *a: None,
                turn_to=rig.turn_to, strafe=rig.strafe, jump=rig.jump,
                at_table=rig.at_table, now=rig.now, sleep=rig.sleep,
                back=rig.back, pitch=rig.pitch)
        finally:
            st.walk_leg, places.keypoints, crawl.pair_inliers = saved
        self.assertTrue(pairs and pairs[0] is not None,
                        "the wrapper must forward on_pair on EVERY push")
        rows = [f for f in res["fixes"] if f.get("push_signal")]
        self.assertTrue(rows, "the signal never reached the journal")
        self.assertEqual(rows[0]["push_signal"],
                         {"inliers": 160, "kp_before": 300, "kp_after": 400,
                          "verdict": "blocked"})

    def test_a_failing_matcher_records_the_error_and_the_walk_carries_on(self):
        # A measurement must never kill a live walk -- and it must never fail
        # SILENTLY either, because "no signal here" and "the matcher exploded"
        # would then have identical output (10.1).
        import slow_traverse as st
        import places
        import tools.crawl as crawl

        def walk_leg(lx, ly, seconds, capture, read_heading, label="",
                     log=print, step_sec=None, on_release=None, on_pair=None):
            on_pair("BEFORE", "AFTER")
            return seconds, 10.0, []

        def boom(img, cache_key=None):
            raise RuntimeError("no cv2 here")

        saved = (st.walk_leg, places.keypoints, crawl.pair_inliers)
        st.walk_leg = walk_leg
        places.keypoints = boom
        rig = Rig(FakeChain(3, default=Fix(k=1, scale=1.0)), table_at=3)
        try:
            res = chain_walk.walk(
                rig.chain, rig.capture, lambda: 87.0, log=lambda *a: None,
                turn_to=rig.turn_to, strafe=rig.strafe, jump=rig.jump,
                at_table=rig.at_table, now=rig.now, sleep=rig.sleep,
                back=rig.back, pitch=rig.pitch)
        finally:
            st.walk_leg, places.keypoints, crawl.pair_inliers = saved
        self.assertTrue(res["fixes"], "the walk ran")
        rows = [f for f in res["fixes"] if f.get("push_signal")]
        self.assertTrue(rows, "the failure is RECORDED, not swallowed")
        self.assertIn("no cv2 here", rows[0]["push_signal"]["error"])
        self.assertNotIn("verdict", rows[0]["push_signal"],
                         "a failed measurement has no verdict, so the gate "
                         "falls through to today's behaviour")


'''

edits_t = [
 ('''        def walk_leg(lx, ly, seconds, capture, read_heading, label="",
                     log=print, step_sec=None):
            self.t[0] += seconds
''', STUB),
 # THE MODULE'S OWN IMPORT GUARD FIRED ON THIS PATCH, which is what it is for.
 # It is widened by exactly two names, each justified, and given a new check so
 # widening it does not also let a module-level import of a console-driving
 # script in.
 ('''        self.assertEqual(
            mods, {"time", "json", "math", "os", "pose", "slow_traverse",
                   "input_controller", "table_prompt"},
            "chain_walk must import nothing that resets, routes, or writes the map")''',
  '''        self.assertEqual(
            mods, {"time", "json", "math", "os", "pose", "slow_traverse",
                   "input_controller", "table_prompt", "places", "tools.crawl"},
            "chain_walk must import nothing that resets, routes, or writes the map")
        # patch59 added the last two, for `pair_signal`. `places.keypoints`
        # reads ORB features, and its `_as_gray` is the HUD mask the push
        # signal has to go through; `tools.crawl.pair_inliers` is the RANSAC
        # count that was validated against the user's own twelve labels, and it
        # is IMPORTED rather than reimplemented -- a mirror of a project
        # function on this project once scored the reference set 3 of 9 where
        # the original scores 9 of 9. Both are pure reads: neither resets,
        # routes, nor writes the map.
        #
        # BUT tools/crawl.py IS A CONSOLE-DRIVING SCRIPT, and importing it at
        # module level would drag it into every process that imports
        # chain_walk. Both are imported INSIDE `pair_signal`, and that is
        # pinned here rather than trusted, because widening an allowlist is
        # exactly when the thing it was protecting gets in.
        top = {a.name for node in self.tree.body
               if isinstance(node, ast.Import) for a in node.names}
        self.assertNotIn("places", top, "lazy, inside pair_signal")
        self.assertNotIn("tools.crawl", top, "lazy, inside pair_signal")
        import tools.crawl as crawl
        self.assertTrue(callable(crawl.pair_inliers),
                        "pair_signal resolves this by name at call time, so a "
                        "rename in tools/crawl.py is a live-run crash")'''),
 ("class NeverTouchesTheForbidden(unittest.TestCase):",
  NEW_TESTS + "class NeverTouchesTheForbidden(unittest.TestCase):"),
]

# ---------------------------------------- assert EVERYTHING, then write
# RULE 19: every anchor on every file is checked BEFORE any file is written, so
# a script that is half right cannot leave a tree that is half patched.
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a[:70], c.count(a))
for a, b in edits_s:
    assert s.count(a) == 1, ("slow_traverse anchor", a[:70], s.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:70], t.count(a))
assert "ESCAPE_GATE" not in c, "patch59 already applied?"
assert "escape_rungs" not in c and "push_verdict" not in c
assert "pair_signal" not in c and "escape_now" not in c
assert "on_pair" not in s, "slow_traverse already patched?"
assert "EscapeGate" not in t and "_SignalRig" not in t
assert "push_signal" not in t and "escape_rungs" not in t

# The constants this one READS OR DERIVES FROM must still be here and be what
# the docstring says: a cited constant that has moved is an invented one
# wearing a citation.
assert c.count("MISS_MAX = 3") == 1, "the miss family's cadence"
assert c.count("STALL_MAX = 4") == 1, "the weak family's cadence"
assert c.count("LOST_MAX = 13") == 1, "the budget both families share"
# ESCAPE_SUPPRESS_MAX = 2 IS DERIVED FROM THOSE THREE, so the derivation is
# recomputed here rather than trusted: the weak family's triggers land at
# lost = STALL_MAX, 2*STALL_MAX, ... under LOST_MAX, and the cap must be
# strictly under that count or every one of them is suppressed.
assert len(range(4, 13, 4)) == 3, "the weak family gets three triggers"
assert 2 < 3, "and the shipped cap leaves one of them real"
assert c.count("FIX_MIN_INLIERS = 29") == 1, "the 'credible fit' of the census"
assert c.count('PROGRESS_ACTIONS = ("advanced", "relocalised", "regressed", "turned")') == 1
assert c.count("ESCAPE_STRAFE_SEC = 0.6") == 1
assert c.count("BACK_SEC = 0.5") == 1
assert c.count("RIGHT = +1.0") == 1 and c.count("LEFT = -1.0") == 1
# MISS_MAX must be DEFINED ABOVE the constants block that cites it (module
# level runs top to bottom; a NameError here is a live-run import failure).
assert c.index("MISS_MAX = 3") < c.index('BLIND_LOOK_FOUND_ACTION = "relocalised-look"')
# The rules this one composes with are untouched by it.
assert c.count("BLIND_LOOK_AROUND = False") == 1, "patch56 must be in"
assert c.count("LOST_RESCUE_MAX = 1") == 1
assert c.count("DOOR_STOP_EXTRA_PUSH = True") == 1
assert c.count("STOP_YAW_SKIP_LAST_STOP = True") == 1
assert c.count("PITCH_CORRECT = False") == 1, "patch57, whose PRESS gate this composes with"
assert c.count("escaped=bool(escaped or escaped_prev))") == 1, \
    "the pitch press gate a suppression must NOT trip"
# The sentence this patch finally acts on, so that if someone rewrites it the
# docstring above is known to be stale.
assert c.count("credible fix follows `escape:back` 0 of 27 times in the bar") == 1
# The three escape triggers, and NOTHING else calling escape().
assert c.count("action = escape()") == 3, "the miss, weak and stalled triggers"
assert c.count("escaped = True") == 3
# THE FOUR CALL SITES OF THE SHARED push() CLOSURE. The signal is journalled
# from two of them; the ORB match is PAID at all four, and the docstring says
# so. If this count changes, that paragraph is stale.
assert c.count("push(PUSH_MAG, PUSH_SEC") == 4, \
    "two tracked pushes, DOOR_STOP_EXTRA_PUSH, and the turn-retry"
# walk_leg's own shape, which the on_pair hook rides on.
assert s.count("def walk_leg(") == 1
assert s.count("if on_release is not None:") == 1, "patch54's hook, the precedent"
assert s.count("SETTLE_SEC = 0.35") == 1
# tools/crawl.py's validated construction, imported and never reimplemented.
X = os.path.join(ROOT, "tools", "crawl.py")
x = open(X).read()
assert x.count("def pair_inliers(kps_a, des_a, kps_b, des_b):") == 1, \
    "pair_signal imports this; a rename here makes the import a live-run crash"
assert x.count("ms = chain_mod.hamming_filtered(des_a, des_b)") == 1, \
    "the Hamming filter is what a naive len(bf.match(...)) mirror gets wrong"
# places.keypoints and its HUD mask, the reason the PAIR goes through it.
P = os.path.join(ROOT, "places.py")
p = open(P).read()
assert p.count("def keypoints(img, cache_key=None):") == 1
assert p.count("def _as_gray(img):") == 1
# The labels the threshold was read off, so a re-labelled file is caught.
L = os.path.join(ROOT, "overnight", "crawl_labelled.jsonl")
lines = [ln for ln in open(L).read().splitlines() if ln.strip()]
assert len(lines) == 12, ("the twelve labels", len(lines))
assert sum('"push_inliers": 166' in ln for ln in lines) == 1
assert sum('"push_inliers": 28' in ln for ln in lines) == 2, \
    "step 1 (labelled desk, but it TRAVELLED into the desk) and step 9"
assert sum('"push_inliers": 148' in ln for ln in lines) == 1
# The test rig this patch's tests subclass and drive.
assert t.count("class Rig:") == 1
assert t.count("    def push(self, mag, secs):") == 1
assert t.count("class FakeChain:") == 1
assert t.count("class ScriptedWide(FakeChain):") == 1, "the rescue test drives this"
assert t.count("MOVED_SIG") == 0

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_s:
    s = s.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(c)
ast.parse(s)
ast.parse(t)
assert c.count("ESCAPE_GATE = False") == 1
assert c.count("BAR_ESCAPE_FROM_K = 129") == 1
assert c.count("BAR_ESCAPE_TO_K = 129") == 1
assert c.count('BAR_ESCAPE_RUNGS = ("left", "right", "back")') == 1
assert c.count('DEFAULT_ESCAPE_RUNGS = ("jump", "back", "left", "right")') == 1
assert c.count("PUSH_BLOCKED_MIN_INLIERS = 88") == 1
assert c.count("ESCAPE_SUPPRESS_MAX = 2") == 1
assert c.count('ESCAPE_SKIPPED_ACTION = "escape-skipped"') == 1
assert c.count("def escape_rungs(k, gate, from_k, to_k, bar_order, default_order):") == 1
assert c.count("def push_verdict(inliers, kp_before, kp_after, thresh):") == 1
assert c.count("def escape_is_suppressed(gate, verdict, suppressed, cap):") == 1
assert c.count("def pair_signal(before, after, thresh=None):") == 1
assert c.count("def escape(order=None):") == 1
assert c.count("def escape_now(sig):") == 1
assert c.count("action = escape()") == 0, "every trigger goes through escape_now"
assert c.count("action, escaped, escape_row = escape_now(push_sig)") == 3
# THE COUNTER, THE PROGRESS RE-ARM, AND THE RESCUE'S OWN RESET -- three sites.
# The rescue's was missing in the first draft and nothing caught it, because
# "rescued" carries no PROGRESS_ACTIONS prefix.
assert c.count("escape_suppressed = 0") == 3
assert c.count("escape_suppressed += 1") == 1
assert c.count("push_sig = push(PUSH_MAG, PUSH_SEC") == 2
assert c.count("push(PUSH_MAG, PUSH_SEC") == 4, "the two untracked sites are untouched"
assert c.count("on_pair=_pair") == 1
assert c.count('**({"push_signal": push_sig} if push_sig else {}),') == 1
assert c.count('**({"escape": escape_row} if escape_row else {}),') == 1
assert c.count("escape_row = None") == 1
assert s.count("on_pair=None):") == 1
assert s.count("if on_pair is not None:") == 1
assert s.count("on_pair(prev_im, now_im)") == 1
assert s.count("prev_im, prev = now_im, now") == 1
assert t.count("class EscapeGate(unittest.TestCase):") == 1
assert t.count("class _SignalRig(Rig):") == 1
assert t.count("log=print, step_sec=None, on_pair=None):") == 1
assert t.count('"input_controller", "table_prompt", "places", "tools.crawl"},') == 1

open(C, "w").write(c)
open(S, "w").write(s)
open(T, "w").write(t)
print("patch59 applied to", ROOT)
