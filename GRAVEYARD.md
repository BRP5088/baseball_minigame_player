# The graveyard — changes that were built, reviewed, and measured, and did not help

**Read this before building any navigation change.** It is deliberately NOT
loaded into context automatically; it earns its keep at the one moment that
matters, which is before you write code.

13 well-motivated changes have died here. The point is not that
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
| **Merging consecutive same-bearing steps** — 40 accelerate/decelerate cycles over the route became 15, with distance preserved exactly. The recording is a human's stick samples, so a straight 5.13s walk arrives as seven "steps". | Verified depth **[0,4,0] mean 1.3** merged vs **[3,2,4] mean 3.0** unmerged. Likely mechanism: a merged push covers more ground than the stop-start sequence it replaces, so legs that used to stop short now run into furniture. An earlier A/B said the opposite — it was scored on `follow()`'s "reached", a routing claim, not a position. | 3/arm | `MERGE_STEPS = False` |
| **Walking legs at 60%**, letting the localiser close the gap. | Verified depth **[2,2,2]** vs **[3,3,3]** at full distance — perfectly consistent within each arm. The frames show why: with short legs the arrival at `bar_jukebox` still identifies as `portrait_room`. The character never left the first room. **A localiser search cannot substitute for distance.** | 3/arm | `SHORT_WALK = False` |
| **Collision anchoring** — walk deliberately into a wall so the game's own geometry zeroes accumulated drift, giving the last leg a fixed starting pose. This was the leading candidate and everyone liked it. | Contact detected **3/3** — the stall signal works fine. Pose repeatability **56px, 246px, 302px** against a 16.85px "same pose" threshold. It reliably HITS something and reliably ends up somewhere different. | 3 | no code survives |
| **Steering while walking** — hold the left stick, nudge the right. | A 30 deg heading lag became **METRES** of position error, and runs then tracked heading perfectly while standing in the wrong room. | — | never shipped |
| **Chunking a leg into more turn-then-walk cycles.** | Re-accelerates from standstill every chunk and walks the leg SHORT; once ended two rooms adrift. | — | one continuous push per recorded step |
| **Local recovery before reset** — a bounded local fan ought to be cheaper than rewinding the whole route to recover one node. | Local **5/6 arrived, median 155s** `[152,590,144,149,158,182]`; reset **4/4, median 75s** `[72,74,82,76]`. **No overlap between the time distributions.** The mechanism is obvious in hindsight: when the fan fails the reset still happens, so its cost is ADDITIVE. | 6 vs 4 | `LOCAL_RECOVERY_FIRST = False` |
| **`STALL_CHANGE` 6.0 -> 2.5** — the old threshold cut through a unimodal distribution (values 3.1 to 7.9) and fired on 5 of 20 as false positives, each firing the escape ladder and injecting unaccounted forward push. | 2.5 arrived **6/10**, 6.0 **8/10**, permutation **p = 0.63** — and the point estimate favours the ORIGINAL. Motivated by observational Fisher **p = 0.00039**. The low view-change was a SYMPTOM of an already-bad run, not its cause. | 10/arm | `STALL_CHANGE = 6.0` |
| **Re-recording `bar_pool_room -> bar_jukebox`** — **ROW VOID, see below** | — the first time the map was ever updated that way. | Old (2.1 deg, 3.30s) **4/8, best streak 3**; new (2.1 deg, 0.80s) **4/8, best streak 3**. **Identical.** The search: 2.1/0.80s went 2/2, while 337.1 — favoured by an earlier search AND by a confident (later refuted) diagnosis — went 0/2 and 1/2. **The bearing was right all along; only the duration was wrong.** | 8/arm | **REVERTED 2026-09-05** — the short leg is gone; `world_map.json` holds the recorded five steps (1.031 units, 3.30s). See the correction below. |
| **Reference pose: the bot's own arrival frames vs the human's** — swapping had left `align_at_node` pulling onto pose A while the leg was recorded from pose B, a real incoherence measured at dx -71 to -212px. | Bot `[1,1,0,1,0,0,0,1,1,0]` **5/10**, human `[0,1,0,0,1,1,1,1,0,1]` **6/10**, permutation **p = 1.0**. A flat null, zero invalid trials — the best-powered measurement on this project. The incoherence is real and is NOT what costs runs. | 10/arm | `REFERENCE_POSE = "bot"` |
| **Office legs at 3x speed**, capped at the measured-repeatable 0.60. | **8/8 both arms** — so the safety question is answered and speed x duration scaling holds up live. But median **71.7s vs 75.4s (~5%)** and the **mean is WORSE, 80.1 vs 76.1**, on one 185s outlier. It removes 7.3s of walking from a ~75s trial, because walking was never most of a trial. | 8/arm | `LEG_SPEED_BY_LEG = {}` |
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
| **Splitting `tests/harness/` out of the parallel suite pass** — `test_no_side_effects` re-runs every other file, so heavy tests ran TWICE concurrently (`test_map_admit` is ~51s of real ORB work, charged twice, peak 12 processes). Running the harness alone at the end looked obviously right. | **322s split vs 241s folded in — 81s SLOWER.** The double execution costs CPU but not WALL CLOCK because it overlaps; serialising the harness just adds its whole duration. The fixture races it targeted were fixed independently by pid-suffixing the /tmp sinks, so the split had no remaining benefit. | `HARNESS_LAST=0` (default). Kept as a flag: it is the right shape if the harness ever stops re-running the suite. |
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
