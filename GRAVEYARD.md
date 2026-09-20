# The graveyard — changes that were built, reviewed, and measured, and did not help

**Read this before building any navigation change.** It is deliberately NOT
loaded into context automatically; it earns its keep at the one moment that
matters, which is before you write code.

13 well-motivated NAVIGATION AND RIG changes have died here — the two tables
below. The mapping attempts at the end are counted separately, because they were
not trying to move the character. (CLAUDE.md section 9 quotes the same 13; if
that number ever changes, both files say it, and a number that must be hand-synced
is a constant pretending to be evidence.) The point is not that
they were bad ideas — several were the leading candidate, everyone agreed with
them, and the mechanism was sound. **Plausibility is not evidence. Build the
measurement before believing the mechanism.**

Two patterns worth internalising before reading the table:

- **Every change that failed MOVED the character.** The only two survivors — the
  aim sweep at the table, and turning — move nothing. Turning cannot convert a
  heading error into a position error; walking can.
- **An association, however significant, is not a cause.** One entry below was
  motivated by observational evidence at Fisher p = 0.00039 and lost its
  interventional A/B outright.

---

## Navigation

| Change | Result | n | State today |
|---|---|---|---|
| **Merging consecutive same-bearing steps** — 40 accelerate/decelerate cycles over the route became 15, with distance preserved exactly. The recording is a human's stick samples, so a straight 5.13s walk arrives as seven "steps". | Verified depth **[0,4,0] mean 1.3** merged vs **[3,2,4] mean 3.0** unmerged. Likely mechanism: a merged push covers more ground than the stop-start sequence it replaces, so legs that used to stop short now run into furniture. An earlier A/B said the opposite — it was scored on `follow()`'s "reached", a routing claim, not a position. | 3/arm | `MERGE_STEPS = False` globally — **but leg 1 IS merged**, via `MERGE_STEPS_BY_LEG = {("office_corridor","office_door")}` added 2026-09-06 00:20. So the change this row records as failed is LIVE on one leg, and this row's own stated mechanism — "legs that used to stop short now run into furniture" — is what the failing log then reported: *BLOCKED on step 4, the view is featureless, this is geometry*. **REVERTED 2026-09-06 on a decisive A/B**: leg 1 at speed 3.0 AND merged arrived **2/10, median 323.7s**; leg 1 as recorded **10/10, median 51.6s**; Fisher exact **p = 0.000714**, zero invalid trials, interleaved (`overnight/ab_leg1.json`). The restored arm reproduces the lost 52.9s baseline at 51.6s. Both flags are off again. |
| **Walking legs at 60%**, letting the localiser close the gap. | Verified depth **[2,2,2]** vs **[3,3,3]** at full distance — perfectly consistent within each arm. The frames show why: with short legs the arrival at `bar_jukebox` still identifies as `portrait_room`. The character never left the first room. **A localiser search cannot substitute for distance.** | 3/arm | `SHORT_WALK = False` |
| **Collision anchoring** — walk deliberately into a wall so the game's own geometry zeroes accumulated drift, giving the last leg a fixed starting pose. This was the leading candidate and everyone liked it. | Contact detected **3/3** — the stall signal works fine. Pose repeatability **56px, 246px, 302px** against a 16.85px "same pose" threshold. It reliably HITS something and reliably ends up somewhere different. | 3 | no code survives |
| **Steering while walking** — hold the left stick, nudge the right. | A 30 deg heading lag became **METRES** of position error, and runs then tracked heading perfectly while standing in the wrong room. | — | never shipped |
| **Chunking a leg into more turn-then-walk cycles.** | Re-accelerates from standstill every chunk and walks the leg SHORT; once ended two rooms adrift. | — | one continuous push per recorded step |
| **Local recovery before reset** — a bounded local fan ought to be cheaper than rewinding the whole route to recover one node. | Local **5/6 arrived, median 155s** `[152,590,144,149,158,182]`; reset **4/4, median 75s** `[72,74,82,76]`. **No overlap between the time distributions.** The mechanism is obvious in hindsight: when the fan fails the reset still happens, so its cost is ADDITIVE. | 6 vs 4 | `LOCAL_RECOVERY_FIRST = False` |
| **`STALL_CHANGE` 6.0 -> 2.5** — the old threshold cut through a unimodal distribution (values 3.1 to 7.9) and fired on 5 of 20 as false positives, each firing the escape ladder and injecting unaccounted forward push. | 2.5 arrived **6/10**, 6.0 **8/10**, permutation **p = 0.63** — and the point estimate favours the ORIGINAL. Motivated by observational Fisher **p = 0.00039**. The low view-change was a SYMPTOM of an already-bad run, not its cause. | 10/arm | `STALL_CHANGE = 6.0` |
| **Re-recording `bar_pool_room -> bar_jukebox`** — **ROW VOID, see below** | — the first time the map was ever updated that way. | Old (2.1 deg, 3.30s) **4/8, best streak 3**; new (2.1 deg, 0.80s) **4/8, best streak 3**. **Identical.** The search: 2.1/0.80s went 2/2, while 337.1 — favoured by an earlier search AND by a confident (later refuted) diagnosis — went 0/2 and 1/2. **The bearing was right all along; only the duration was wrong.** | 8/arm | **REVERTED 2026-09-05** — the short leg is gone; `world_map.json` holds the recorded five steps (1.031 units, 3.30s). See the correction below. |
| **Reference pose: the bot's own arrival frames vs the human's** — swapping had left `align_at_node` pulling onto pose A while the leg was recorded from pose B, a real incoherence measured at dx -71 to -212px. | Bot `[1,1,0,1,0,0,0,1,1,0]` **5/10**, human `[0,1,0,0,1,1,1,1,0,1]` **6/10**, permutation **p = 1.0**. A flat null, zero invalid trials — the best-powered measurement on this project. The incoherence is real and is NOT what costs runs. | 10/arm | `REFERENCE_POSE = "bot"` |
| **Office legs at 3x speed**, capped at the measured-repeatable 0.60. | **8/8 both arms** — so the safety question is answered and speed x duration scaling holds up live. But median **71.7s vs 75.4s (~5%)** and the **mean is WORSE, 80.1 vs 76.1**, on one 185s outlier. It removes 7.3s of walking from a ~75s trial, because walking was never most of a trial. | 8/arm | **NO LONGER `{}` — turned back ON for leg 1 on 2026-09-05 at the user's direction**: `LEG_SPEED_BY_LEG = {("office_corridor","office_door"): 3.0}`. This row's own measurement says the mean was WORSE. **REVERTED 2026-09-06 on a decisive A/B**: leg 1 at speed 3.0 AND merged arrived **2/10, median 323.7s**; leg 1 as recorded **10/10, median 51.6s**; Fisher exact **p = 0.000714**, zero invalid trials, interleaved (`overnight/ab_leg1.json`). The restored arm reproduces the lost 52.9s baseline at 51.6s. Both flags are off again. |
| **Blind crabbing to get around an obstacle.** | Walked the character off the spot into a wall, ending with no table in view (ink 0.0). | — | removed |
| **ORB homing on the table.** | Over six rounds the "strongest" heading jumped 322 -> 350 -> 17 -> 319 -> 354 -> 22 while prompt ink FELL 0.0224 -> 0.0093. The table scores 109-129 keypoints at that distance and pure negatives already reach 114. **It is reading noise.** | 6 rounds | removed |

## The rig

| Change | Result | n | State today |
|---|---|---|---|
| **chiaki timing the stick release on its own `steady_clock`** instead of waiting for Python to write the release. Well motivated, does exactly what it was designed to do. | Old path range **17.56 deg**, new path **17.28 deg** — **1.6%, i.e. nothing.** Python's `sleep` simply was not the bottleneck. What DID matter was stick magnitude: 1.0 -> 0.9 is 4.8x less absolute drift for 11% less stick. | 6/arm | `CHIAKI_TIMES_THE_HOLD = True` — kept; harmless, correct, and it removes a real failure mode even though it did not move the number |

---

## Built tonight, measured, and reverted (2026-09-05)

| Change | Result | State today |
|---|---|---|
| **Splitting `tests/harness/` out of the parallel suite pass** — `test_no_side_effects` re-runs every other file, so heavy tests ran TWICE concurrently (`test_map_admit` is ~51s of real ORB work, charged twice, peak 12 processes). Running the harness alone at the end looked obviously right. | **322s split vs 241s folded in — 81s SLOWER.** The double execution costs CPU but not WALL CLOCK because it overlaps; serialising the harness just adds its whole duration. The fixture races it targeted were fixed independently by pid-suffixing the /tmp sinks, so the split had no remaining benefit. | **GONE, and this cell used to say "kept as a flag".** `HARNESS_LAST` exists in no .py file in the tree (checked 2026-09-20 with `find \| xargs grep`, which unlike a bare `grep` here does not obey `.gitignore`). run_tests.sh:187-190 says why in its own words: the doubling it traded against was removed, "so it is gone too". Setting it does nothing, silently — the same shape as `compass.STABLE_MIN_AGREE`. |
| **Speeding the office legs 3x** (capped at the measured-repeatable 0.60) | 8/8 arrived both arms — so the `speed x duration` scaling holds live — but median 71.7s vs 75.4s (~5%) and the **mean is WORSE**, 80.1 vs 76.1, on one 185s outlier. It removes 7.3s of walking from a ~75s trial, because walking was never most of a trial. | `LEG_SPEED_BY_LEG = {}` |

**The lesson both share:** the intuitive bottleneck was not the bottleneck.
Profiling one whole trial found `read_bearing` at 21% — fixed by installing
`tesserocr` (261ms -> 31ms, 8.4x) for more gain than either of the above, with
no added variance. **Measure the whole thing before optimising any part of it.**

## Two families that are closed on BOTH sides

"Correct more often during a leg" has no remaining room:

- **Steer while walking** — measured worse (heading error becomes position error).
- **Chunk a leg into more cycles** — measured worse (walks the leg short).

Any proposal of that shape is a rediscovery unless it brings new evidence.

**`LEG_TURN_TOLERANCE` was deliberately NOT that shape** — it adds no chunks and
does not steer while walking — which is why it survived as the one in-leg idea
worth testing. **It died on 2026-09-05 without ever being run, and it is the only
entry here killed by arithmetic rather than by trials.** See the row below.

---

## Also do not retry these

- **A better (bearing, duration) for the jukebox leg.** Re-recorded from the
  executor's own pose: 4/8 -> 4/8. The start pose is not one place, so no single
  constant is right from every start.
- **Lowering `MIN_MATCHES` / `MIN_RATIO`.** Leave-one-out shows a genuine arrival
  scores 249-698 matches at 2.6-5.3x ratio. The failures are POSITION failures;
  the localiser is not the bottleneck.
- **Seeding a new place from a failure frame or from the survey.**
  `map_propose.py --admit` rejected 15 of 15 clusters, all on recoverability.
  Failure frames left in the pool "rescue themselves" and report the problem
  solved.
- **Any further leg-speed scaling.** Walking is ~20s of an ~85s trial; the
  profiled win was `read_bearing` (261ms -> 31ms), not the legs.
- **Any n=3 A/B.** Power 0.00 here. Ten per arm, interleaved, or do not write it
  up as a result.


## Cancelled before it ran (2026-09-05) — `LEG_TURN_TOLERANCE`

| Change | Why it was cancelled | Cost avoided |
|---|---|---|
| **Tightening `LEG_TURN_TOLERANCE` below `slow_traverse.TURN_TOLERANCE = 4.0`**, so that the mid-leg turns currently discarded as NO-OPS actually execute. The mechanism was verified and this was billed as "the highest-value navigation experiment available". | The mechanism IS real — from the two live traces at `graph_walk.py:1339-1340`, the failed attempt walked `portrait_room -> bar_pool_room` at a spread of **0.00 deg** against a commanded 6.59. But integrating both traces, **they end 0.0021 walk-units apart on a 0.7203-unit leg**, and the flat one was the MORE faithful to the recording. Across all five legs the tolerance costs **0.37 / 2.63 / 0.27 / 2.32 / 0.83 %** of leg displacement — and **6.79% worst-case** on the worst leg once the entry offset the tolerance also permits is priced in (corrected on review; the first pass modelled only the discarded turns). Either way the project's own leg-distance pin accepts 15%, the shortfall that genuinely broke the jukebox leg was 68%, and tightening 4.0 -> 1.0 buys **0.258 walk-units over the whole route** against that 0.703-unit shortfall. Separately, `cam` shows the "recorded curve" is the human's LEFT THUMB: **\|delta cam\| exceeds 4 deg on 1 of 64 transitions, \|delta bearing\| on 23 of 64** — and `walk_link` passes `lx = 0.0`, so the executor cannot strafe and would be turning the camera to chase that jitter. | **20 trials, ~2 h of console.** At 338 s/trial and a 0.60 baseline, detecting +2 points at 80% power needs 9,337 trials per arm. 10/arm can see about +30 points. The A/B could only ever have returned a meaningless null. |

**The lesson is new to this file.** Every other row here was killed by trials.
This one was killed by asking, before booking the console, *how large can the
effect possibly be* — bounding it from the recordings alone. The bound took an
afternoon offline and is pinned by
`tests/routing/test_leg_curve_is_stick_not_camera.py`. Two of the rows above
(`STALL_CHANGE`, the reference pose) would have survived that question; several
would not.

### The full OPEN-3 ticket, moved from CLAUDE.md §11 (2026-09-07)

**OPEN-3 — CLOSED 2026-09-05, DROPPED WITHOUT RUNNING IT.** `LEG_TURN_TOLERANCE`
ships `None` — unchanged, i.e. `slow_traverse.TURN_TOLERANCE = 4.0` — and the
20-trial A/B this file called "the highest-value navigation experiment available"
is CANCELLED. Settled offline from the recordings, as the `cam` section above
demanded. (`None` must still never reach `st.turn_to`: `abs(err) <= None`
raises.)

**The mechanism is REAL. It is also worth a few percent of a leg.** Both halves
are measured, and the second is why this is dropped rather than run. Scored the
one non-vacuous way (§10.12 — the spread of ACHIEVED headings, never
`|want - got|`), the two live traces `graph_walk` recorded for
`portrait_room -> bar_pool_room` in one run read: commanded 286.57 / 292.18 /
285.59 / 287.59, spread 6.59 deg; the FAILED attempt achieved 289.1 four times,
spread **0.00**; the SUCCEEDED attempt 286.2 / 290.1 / 288.1 / 288.1, spread
3.90. So the tolerance really does flatten the recorded curve to nothing. But
integrated at the recorded speeds and durations those two traces end **0.0021
walk-units apart on a 0.7203-unit leg**, and the FLAT, never-turned trace was the
MORE faithful to the recording's own endpoint (0.0011 against 0.0022). Whatever
separated those two attempts, it was not the heading.

**The premise was also wrong about what the curve IS.** `graph_walk.walk_link`
calls `st.walk_leg(0.0, -abs(speed), ...)` — `lx` hard-coded to zero — so the
executor CANNOT strafe mid-leg, and it reproduces the human's travel direction by
turning the CAMERA to a heading the human never held. Over all 64 inter-step
transitions in both recordings, `|delta cam|` exceeds 4 deg on **1**, while
`|delta bearing|` exceeds it on **23**. Twenty-two of the twenty-three "curves"
are the human's left thumb. Tightening the tolerance makes the executor chase
thumb jitter: on `bar_jukebox -> dealer_table` it would sweep the camera 25.6 deg
over 4.07s of walking, where the human held `cam` at 86.8 ± 0.14.

**COST, priced the honest way — quote 6.79% and 0.258 units, never 2.63%.** The
first pass under-priced this 2.6x by seeding each leg exactly on its first
commanded bearing. `turn_to` compares against the MEASURED heading, so a leg also
STARTS up to `tolerance` off and is walked there until some step exceeds the
band — which is the second half of this ticket's own stated mechanism, and it is
the case the single real trace shows (commanded 286.57, character at 289.1, entry
turn a NO-OP). Swept adversarially over the permitted entry offset, discarding
sub-4-degree turns costs **6.79% on the worst leg**, and tightening 4.0 -> 1.0
buys **0.258 walk-units over the whole route**. For scale, the leg-distance pin
accepts 15%, and the shortfall that genuinely broke the jukebox leg was 0.703 of
1.031 units — **68%**.

**The arithmetic that ends it.** At the §8(a) baseline of 0.60 and 338 s/trial,
detecting +2 percentage points at 80% power needs ~9,300 trials per arm, about
1,750 console hours; +5 points ~1,470 per arm; +10 points ~360. Ten per arm can
only see an effect of about +30 points. There is no version of this experiment
that fits in the time available and could detect the effect the mechanism allows.

A hard floor nobody had noticed, worth keeping: `turn_curve.plan_turn` returns
`(0.0, 0.0)` under 0.5 deg, so `turn_to` can never satisfy `abs(err) <=
tolerance` below that — it breaks out and files an UNDERTURNED hazard on every
step of every leg. Against a perfect simulated console, tolerance 0.40 filed 297
of 2800 and 0.0 filed all 2800. **The usable range is (0.5, 4.0].**

Pinned by `tests/routing/test_leg_curve_is_stick_not_camera.py`, which re-derives
the whole argument from `route3_steps.json`, `route2_steps.json` and
`world_map.json` rather than restating it — including that each map leg IS the
corresponding route3 slice, since everything else attributes route3's `cam` to
the map's legs.

**THIS CLOSURE ORPHANS A USER OBSERVATION.** `graph_walk`'s own
`LEG_TURN_TOLERANCE` comment claims this mechanism explains §8(k) — "you actually
walk right out of the bar". A few percent of a leg's displacement cannot do that,
so §8(k) is back to having NO candidate explanation, and that comment now asserts
something this closure disproves.

**The NO-OP/TURNED instrument (2026-09-04) has never actually run.**
`slow_traverse.turn_to` logs every exit, paired:

    turn to 292.2: NO-OP, already inside 4.0 deg (at 289.1, err +3.1) —
                   nothing was sent, the recorded curve was discarded
    turn to 292.2: TURNED to 292.0 (err +0.2) in 1 push(es)

but no log, transcript or json on disk contains either string, so nothing can be
re-scored — do not try. It costs nothing and answers the mechanism question a
caller's step line never can (an executed turn also ends inside tolerance, which
is precisely why this was invisible). **Let it ride along on whatever A/B runs
next.**


**Update 2026-09-07 — the NO-OP/TURNED instrument the ticket below says "has
never actually run" ran.** `overnight/ab_leg1.log`, 20 trials: **394 NO-OP
against 379 TURNED** — roughly half of every recorded curve is discarded by the
4.0 deg tolerance. That is the OPEN-3 mechanism measured, and it does not reopen
the ticket: the displacement bound above is what closed it, and that bound is
unchanged by how often the no-op fires.

---

## CORRECTION 2026-09-05 — the re-record row was not a null, it was a regression

The row above reads 4/8 -> 4/8 as "the leg parameters do not matter". They do.

The re-record left the leg **4.3x TOO SHORT** — 0.240 walk-units against a
recorded 1.032 — and from the far edge of its origin's recognition basin it
landed 0.703 units short of its destination's. It could not arrive. So the 4/8
it scored cannot have come from the leg; it came from the recovery fan.

The A/B was sound in method and measured something other than what it named.
That is a different failure from the others in this file: not "a good idea that
did not help", but "a measurement pointed at the wrong thing". Leg restored, and
`tests/routing/test_leg_distances_match_recording.py` now pins every leg against
its own recording.


## Mapping — building geometry from the frames (2026-09-06)

Three attempts, all dead. The first two failed for one reason; the third failed
for a different one that is worth more.

| Attempt | Result | Why it is dead |
|---|---|---|
| **Triangulate a hand-driven office drive** — 1064 frames, 95% with a compass heading, all eight approach angles filled. By every check available at the time it was a perfect collection. | Kept **3 points of 196,198 tracks**. The driver spent 61% turning, 17% walking, and camera translation over three frames had a MEDIAN OF ZERO. | Triangulation needs the camera to MOVE. Turning on the spot leaves the lens still, the rays stay parallel, and every depth fits equally well. The filter that rejected 196,195 tracks was CORRECT — the data carried no depth. |
| **Multi-view with proper filters** — cheirality, reprojection, three or more views, real parallax — on the same drive. | The same answer, honestly this time. An earlier pairwise pass with none of those filters produced 644,872 points that rendered as radial starbursts, 19.6% of them lying between or behind the two cameras. | Filters cannot manufacture a baseline nobody drove. |
| **Stitch the frames onto the FLOOR PLANE** — the user's idea, and geometrically sound: a homography needs POSE, not parallax, so it works on exactly the frames triangulation could not use. | **The rendered map is an artifact.** Fed a single FLAT GREY value — no scene content at all — the identical pipeline reproduces the map's silhouette to the last cell: seen-cell IoU **1.000**, coverage correlation **1.000**, including the top-left room, the arc, the central corridor, both bottom rooms and the black gap. Real scene content correlates only **0.130** with the render. | The canvas is the camera path dilated by the frustum radius, arithmetically: path span 3.70 x 11.09 plus 2 x `MAX_RANGE` 3.2 predicts the measured 8.64 x 15.94. **Everything that looked like architecture was the shape of the walk.** |

**The third one is not fixable by better fitting.** The ground-plane assumption
treats every pixel below the horizon as floor at one constant height. In this
game that region is a desk, a table top, bottles, chairs, a typewriter in
extreme close-up, and — at t=30s of the route walk — an OUTDOOR STREET at a
different elevation. On top of that the floor is dark, vignetted and nearly
untextured: phase correlation on it gives peaks of 0.05-0.33 with the shift
flipping sign between adjacent frame pairs. The walls carry this game's
contrast; the floor does not.

**Three fitting objectives were tried and each was gamed in a different
direction.** This is the transferable part:

- maximise self-agreement between frames -> chose a pitch that calls **59.7%**
  of the floor the player physically STOOD ON an obstacle. A consistent error
  agrees with itself perfectly.
- minimise error against the walked path -> chose a scale that collapses the
  whole walk into one blob where nothing can be blocked: **0.0% wrong, 0%
  agreement**.
- both together, as gate and score -> the same degenerate scale again.

Each is a global statistic over a map whose EXTENT the fitted parameter
controls, so the parameter can always buy a better score by shrinking the
question. And **76.4% of frame-to-frame steps in the source recording were
exactly zero** — the camera was standing still — which no fitting can repair.

**The lesson, and it is section 10.12 in a new costume.** Both validation scores
built for this were satisfiable with no scene information at all, and neither
could report that. The user said "the images don't look right" and was correct
before either number was. **A control that renders the same pipeline from a
CONSTANT image costs two minutes and would have killed this on day one.** Run it
before believing any result that accumulates frames into a canvas.
