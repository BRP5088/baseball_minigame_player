# Overnight report — 2026-09-03

Written for you to read cold. Everything here is either MEASURED (a number I
observed) or flagged as inference. Where I was wrong earlier in the night, the
correction is stated rather than quietly dropped.

---

## THE HEADLINE: every button in the system was dead

`input_controller.press()` tries the FIFO first, sending buttons as
`buttons <bitmask>`. **Those bits do nothing on this console.** Measured live:

| path | result |
|---|---|
| FIFO `buttons 4096` (options) | **nothing after 4s** |
| keyboard `o` | **pause menu in 0.5s** |

The bug wasn't the wrong bits. `_inject_press` **returned True** because writing
to the pipe succeeded, so `press()` believed the button was pressed and never
fell through to the path that works. A success path and a no-op path with
identical output — the exact shape in your own diagnosis catalogue.

It silently disabled **every button**: resets, pause menu, menu navigation, card
selection, match play. Your `chiaki-patch/README.md` said the bits were never
confirmed; `CLAUDE.md` said they were measured. The README was right.

**Fixed:** `INJECT_BUTTONS = False`. Buttons use the keyboard; sticks stay on the
FIFO where they're proven. Immediately after, a full reset ran in **8.7s** —
before the fix it was failing with "never landed on 'Load Last Save'".

**This invalidates earlier navigation numbers**, including tonight's step-3
trials: those were measuring a broken reset, not routing. Re-measured results
are below where I had time to redo them.

Also: `osascript` leaves *Script Editor* frontmost, and the keyboard path checks
frontmost — so anything shelling out to osascript must re-front chiaki first.

---

## The navigation headline

**The recorded curve of a leg is never walked.** This is the best explanation
yet for why the same leg lands differently every run, and it came out of your
own observation from the stream — "you don't get close enough to Wanda... you
walk right out of the bar", then next run, "you did walk far enough".

`slow_traverse.TURN_TOLERANCE` is **4.0°**, and that is what the leg executor
uses. The leg `portrait_room -> bar_pool_room` commands bearings 286.6, 292.2,
285.6, 287.6 — a total curve of **6.6°**. From a character standing at 289.1°,
every one of those is inside tolerance, so `turn_to` returns *without turning*.

From that run's own log, two attempts at the same leg:

```
failed:    got 289.1  289.1  289.1  289.1     never turned at all
succeeded: got 286.2  290.1  288.1  288.1
```

And the log reads `step 2/4 bearing 292.2 (got 289.1)` — which looks exactly
like a turn that happened. Same shape as every bug in the 2026-09-01 catalogue:
*the code did nothing, and doing nothing looked like working.*

Per-leg maximum step-to-step bearing change, against the 4.0° tolerance:

| leg | max Δ | consequence |
|---|---|---|
| office_corridor → office_door | 0.3° | unsteered (straight anyway) |
| office_door → portrait_room | 8.7° | partly steered |
| portrait_room → bar_pool_room | 6.6° | observed as 4 no-ops in a row |
| **bar_pool_room → bar_jukebox** | **1.3°** | **nothing steers it after step 1** |
| bar_jukebox → dealer_table | 13.9° | partly steered |

The leg that fails most is the one nothing steers.

### The measurement, including the one I got wrong

I nearly reported a **vacuous statistic**: "68 of 68 turn steps were within
4.0°, so 100% are no-ops". That is circular — `turn_to` only returns once the
error is inside tolerance, so the inequality holds *by construction*. It
measured the loop's own exit condition and looked devastating.

The real test compares the spread of **commanded** bearings across a leg
against the spread of **achieved** headings:

| leg | commanded spread | achieved spread | |
|---|---|---|---|
| portrait_room → bar_pool_room | 6.6° | **0.0°** | the attempt that FAILED |
| portrait_room → bar_pool_room | 6.6° | 3.9° | the attempt that SUCCEEDED |
| bar_pool_room → bar_jukebox | 1.2° | 0.1° | nothing steered it |
| office_door → portrait_room | 0.8° | 3.8° | drifted *more* than commanded |

n=2 on the matched pair — a direction, not a coefficient. But the run that
turned is the run that arrived.

That last row is the other half of the defect: a ±4° band neither **executes** a
commanded change under 4° nor **corrects** drift under 4°. The heading wanders
freely inside it in both directions.

`graph_walk.LEG_TURN_TOLERANCE` now exists. **Default None = unchanged.** It
ships as a flag to be A/B'd, not as a fix — two well-motivated navigation
changes have already been reversed by measurement on this project.

---

## Phase 1 — the reference-swap experiment

### Steps 1 & 2: DONE

All three nodes reached and verified, all at the 1500-keypoint ORB cap:

| node | verified | keypoints | bearing |
|---|---|---|---|
| portrait_room | yes | 1500 | 1.5° |
| bar_pool_room | yes | 1500 | 288.1° |
| bar_jukebox | yes | 1500 | 0.9° |

`bar_pool_room` came back an **open, feature-rich view of the bar**, not the
furniture-pressed frame the record predicted.

Adopted as the new `route_*.jpg` references, same filenames so nothing that
globs them changes behaviour. Originals in `places_backup_20260903_020639/`.

**Revert:** `./overnight/revert_references.sh`

Caveat: the bartender NPC is in the `bar_pool_room` reference. 1500 static
keypoints should swamp it, but NPCs move and this is the kind of thing that
bites later.

### Step 3: see RESULTS section below

---

## Phase 2 — offline QA

(filled in below)

---

## Phase 3 — corrections to things I said earlier tonight

**`turn_curve` is NOT 10% wrong.** I claimed it was. Measured against six live
1.0s turns per magnitude:

| mag | table | measured | error | |
|---|---|---|---|---|
| 0.90 | 74.8 | 72.01 | +3.9% | in usable band |
| 0.70 | 37.3 | 35.49 | +5.1% | in usable band |
| 1.00 | 197.7 | 209.45 | −5.6% | above USABLE_MAX, never used |

I had compared a *steady-state* estimate against a table of *averages over a
hold*. Different quantities. The real defect was the docstring not saying which.

**The chiaki timed-hold patch bought 1.6%, i.e. nothing.** Old path 17.56°
spread, new path 17.28°, n=6 each. It is correct and it is in, as insurance
against a lost release packet (~44° runaway), but it is not a drift fix.

**What actually cut drift: stick magnitude.** 1.0 → 0.9 is 17.28° → 3.61°,
**4.8× less**, zero code. 0.9 is a sweet spot — relative error is worse at both
1.0 (8.3%) and 0.7 (8.2%) than at 0.9 (5.0%).

**My own mutation harness was lying.** Four `turn_curve` mutants reported
"caught by nothing" because every mutation preserved file *size*, and CPython
validates `.pyc` on (mtime, size). Stale bytecode ran. Any mutation harness here
must delete `__pycache__/<module>*.pyc` between mutants.

---

## Analytics — `tactics_effect.py`

Ready for tomorrow's farming. Reuses `analyze_match_log`'s `load()`,
`permutation_p()` and `effective_power()` rather than reimplementing them.

On the current 143-row log:

| tactic | n | win rate | baseline | p |
|---|---|---|---|---|
| speed_boost | 3 | — | — | **INSUFFICIENT** |
| fielding_boost | 2 | — | — | **INSUFFICIENT** |
| swing_boost | 24 | 0.542 | 0.273 | 0.080 |
| pitch_boost | 17 | 0.294 | 0.483 | 0.237 |

**Speed and fielding cannot be answered from this log.** n=3 and n=2 is not a
weak result, it is not a result, and the script abstains rather than printing a
number that looks like evidence. 97 of 143 rows have no `tactics_kind` at all.

To answer it tomorrow you need matches that actually *play* those tactics —
roughly 100 per arm to separate a real 10-point effect from binomial noise.

---

## Suite

68 files, all green.

---

## The other half of the last-leg failure: the leg is 4× too long

Offline, from `world_map.json` against the search result already recorded in
CLAUDE.md. The recorded `bar_pool_room -> bar_jukebox` leg is:

```
1: bearing   2.1  dur 0.80      2: bearing   1.2  dur 0.79
3: bearing   0.8  dur 0.80      4: bearing 359.4  dur 0.79
5: bearing 359.6  dur 0.14      -> 3.30s, essentially dead straight north
```

But a search from the executor's OWN arrival at `bar_pool_room` found
**337.1° for 0.80s** reaches `bar_jukebox` (240 matches).

|  | recorded (human) | measured (bot's pose) |
|---|---|---|
| bearing | 2.1° | 337.1° |
| duration | 3.30s | 0.80s |

**25° apart and 4× the distance.** That is not a leg needing correction, it is a
different journey — the human's `bar_pool_room` and the bot's are far apart
inside one large room. `places.identify()` answers *which room*; the leg assumes
*a point*.

This is a strong, independent reason the last leg fails, and it plausibly IS
the "you walk right out of the bar" the user saw: walking 3.3s when 0.8s is
needed overshoots by roughly four times.

**It also argues for re-recording the leg regardless of whether
`align_lateral` converges** — no amount of lateral correction fixes a leg whose
distance is 4× wrong. I am still honouring the stated gate (step 4 only on
convergence) rather than acting on this unilaterally, but it should be the
first thing done next.

---

## Phase 1 step 3 — RESULT: encouraging, but n=1

```
trial 1: could not reach bar_pool_room  (abandoned, not counted as a stall)
trial 2: could not reach bar_pool_room  (abandoned)
trial 3: reached.  dx 51.5 -> 11.4      CONVERGED (tolerance 35px)
```

**Before** (aiming at the human-walk reference): four corrections left dx at
−136, −179, −156, −158. It did not move at all.

**After** (aiming at the bot's own arrival pose): 51.5 → 11.4 in one trial.

Two things changed, and both point the same way. The *starting* offset fell from
~150px to 51.5px — which is the mechanism, since the reference is now a pose the
bot actually reaches — and the correction then converged instead of stalling.

**I am not calling this established.** n=1. The script's gate says "all measured
trials converged" and there was one measurable trial. Given this project has
reversed two navigation changes that looked at least this good, one trial is a
direction, not a result.

**The bigger finding is the denominator.** 2 of 3 trials never reached
`bar_pool_room` at all, so the experiment could not run. Earlier the same night
the capture reached all three nodes on its first pass. Same code, same session.

**That is the actual bottleneck: the route does not reliably deliver the bot
anywhere.** Alignment is a correction on top of arrival, and arrival is what
fails. Which is why the leg-tolerance A/B — running now — matters more than
this experiment did.


---

## The leg-tolerance A/B — first positive navigation result

Run **after** the button fix, arms interleaved, measured on verified positions:

| arm | verified depth (of 3) | mean | full routes |
|---|---|---|---|
| baseline (4.0°) | 2, 1, 2 | 1.67 | **0 / 3** |
| **tight (1.0°)** | **2, 3, 3** | **2.67** | **2 / 3** |

Tight wins on every comparison and produced the **first full-route completions
of the session**. That matches the mechanism: at 4° the recorded curve sits
inside tolerance and is never executed, so the leg is walked straight at
whatever heading the bot arrived with.

**Caveats, stated plainly:** n=3 per arm — the 4th baseline trial wedged in a
retry loop (console stayed healthy; my script's fault). The merge A/B was also
n=3 and it *reversed* an earlier n=3. So `LEG_TURN_TOLERANCE` stays at **None
(unchanged)** until confirmed.

**Confirming this is the highest-value next experiment.**

---

## Where things stand

| item | state |
|---|---|
| Buttons dead over FIFO | **FIXED**, reset now 8.7s |
| Leg turn tolerance | flag added, A/B positive n=3, **default unchanged** |
| Reference frames | swapped to bot's own poses, backed up, revert available |
| align_lateral | converged 51.5 → 11.4 once (n=1) |
| Last leg 4× too long | diagnosed, not yet re-recorded |
| Analytics | `tactics_effect.py` done; speed/fielding unanswerable (n=3, n=2) |
| Phase 2 QA | subagents ran; see their section |
| Suite | green |

**The console is parked** (input released, stream healthy, bearing 266.8).

## What I'd do next, in order

1. **Confirm the tolerance A/B** with 6+ trials per arm. If it holds, flip the
   default — it is the first thing that has moved the needle.
2. **Re-record `bar_pool_room → bar_jukebox`** from the bot's own pose. The
   recorded leg is 25° and 4× too long; no correction fixes that. Script is
   staged and gated at `overnight/phase1_step4_rerecord.py`.
3. Re-measure `align_lateral` properly (n=1 is not a result).
4. Only then think about the 25-consecutive bar.

---

## A process lesson that cost the confirmation run

I launched the Phase 2 mutation sweep (4 subagents) and live console
measurements at the same time. Load average hit **273–333**, the suite slowed to
~2 files per 4 minutes, and an A/B trial that normally takes ~90s ran 851s
without finishing.

No runaway Python, no zombies — the CPU consumers were ordinary apps. The likely
cause is **Sophos** scanning the thousands of file writes mutation testing
generates. I did not touch it; you've said not to weaken security on this
machine.

**Why this matters beyond being slow:** I measured earlier tonight that Python's
`sleep` degrades from ~5ms to 242ms under saturation. Any leg walked in that
state is mistimed, so **live measurements taken during a mutation sweep are
worthless**. Offline sweeps and console work must run in series.

The n=3 A/B result stands because its arms were **interleaved** — contention hit
both equally. The confirmation run (6 per arm) did not complete and is not
included.

---

## Phase 2 — status and one regression I had to quarantine

The Phase 2 workflow (4 audit areas × mutation verification) was **still running
when I stopped**, after ~2.5 hours. It slowed itself down: the mutation sweeps
are what saturated the machine. Its findings will land in the workflow result,
not here.

It did produce work, and one piece of it broke the suite:

**`tests/test_ban_ocr_confusion.py` HANGS.** Zero output, verified twice (180s
buffered, 100s with `python -u`), so it is stuck at import or module-level setup
rather than partway through. It was stopping `./run_tests.sh` after 5 files —
meaning every later test was silently not running and the pass count was
meaningless. That is precisely the failure your notes already record.

**Moved to `tests_quarantine/`, not deleted** — the confusion-mapping work in it
is wanted. `tests_quarantine/README.md` says what to fix: find what blocks at
import (31 OCR/loop calls; the `orchestrator` import and any module-level
Tesseract work are the first suspects), bound the frame count, and confirm it
finishes in seconds before returning it.

I did not "fix" it by editing a subagent's in-progress work.

---

## Honest summary of the night

**Solidly established:**
- Every button in the system was dead over the FIFO. Fixed; resets now take 8.7s.
- Full stick is 4.8× worse than 0.9 for camera drift, and 0.9 is a sweet spot.
- Drift is quantised to game frames (3.795° at full stick); no patch beats it.
- `turn_curve`'s table is accurate to ~5% where the system uses it (I was wrong
  to call it 10% off).
- The chiaki patch is rebuildable again, and was missing two silent edits.

**Promising but not established:**
- Tightening the leg turn tolerance: depth 2.67 vs 1.67, 2/3 full routes vs 0/3.
  **n=3.** Default left unchanged.
- `align_lateral` converging on the bot's own reference: 51.5 → 11.4px. **n=1.**

**Diagnosed, not fixed:**
- `bar_pool_room → bar_jukebox` is recorded 25° off and 4× too long.

**Not attempted:** the 25-consecutive-arrival bar. Still far off.

---

# A/B CONFIRMATION: BLOCKED — and why that was worth it

You asked me to confirm the tolerance A/B with more trials. **I could not**, and
the reason is a bug that was about to cost you the session.

All 12 confirmation trials failed with
`ResetError: cannot tell which menu entry is selected`. Chasing it found this,
on a real frame where **"Load Last Save" was visibly highlighted**:

```
Resume             0.0003
Load Last Save     0.0771   <- actually selected, BELOW the 0.1 bar
Load               0.0006
Quit to Main Menu  0.1075   <- returned, ABOVE the bar
```

`pause_menu.selected_item()` scores each row by **white fraction**, so the score
rises with how much *text* a row has. A long unselected entry outscored a short
selected one. Exactly one row cleared the bar, so it returned
**"Quit to Main Menu" confidently** — and the caller presses `cross` on whatever
it names.

**An unattended run would have quit your game to the main menu.** The only thing
that stopped it tonight was `reset_env` requiring four consistent reads and
refusing to press blindly.

**Made safe:** `SELECTED_MARGIN = 2.0` — the winner must beat the runner-up 2×
or it abstains. The failing frame was 1.39×, so it now returns None. Resets fail
loudly instead of quitting the game. Mutation-tested 2/2.

**Not fixed, and it blocks every live experiment.** The repair is to measure the
*highlight* instead of the letter count — the selected entry renders LARGER and
pure white, so peak brightness or glyph height within the row separates
cleanly. That is a small, well-specified job and it is the first thing to do,
because nothing needing a reset can run until it lands.

## So the A/B still stands at n=3

| arm | depth (of 3) | mean | full routes |
|---|---|---|---|
| baseline 4.0° | 2, 1, 2 | 1.67 | 0/3 |
| **tight 1.0°** | **2, 3, 3** | **2.67** | **2/3** |

`LEG_TURN_TOLERANCE` remains **None (unchanged)**. Confirming it is still the
highest-value experiment — it just needs working resets first.

**Console parked:** pause menu closed, input released, in-world at bearing 292°.
