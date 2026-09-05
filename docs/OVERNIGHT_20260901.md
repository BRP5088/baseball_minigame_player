# Overnight run — 2026-08-31 into 2026-09-01

Running unattended cycles (reset → walk to table → play until broke → repeat)
and fixing whatever breaks. Appended to through the night; newest section last.

Starting state: **3W / 0L / 0D**, $246, `match_log.jsonl` 87 rows,
API budget 1200 calls (~$14.40).

---

## Fixed before the overnight run started

### 1. chiaki was running the STOCK build — no injection at all
`/Applications/chiaki-ng.app` has no `CHIAKI_INJECT_INPUT` string and never
opened the FIFO, so every injected input went nowhere. Two causes, both fixed:
`restart_chiaki.sh` killed only `chiaki-ng-build` processes (a stock app
launched by hand survived and fought for the stream — now matches on executable
name), and the `chiaki-analog` alias pointed at `launch.sh`, which starts the
patched build but never kills a running instance and never re-signs. Alias now
points at `restart_chiaki.sh`.

### 2. Tactics cards read as player cards — the biggest API cost sink
`Fielding Play` and `Power Swing` came back as `{"kind": "player", "power": 1}`,
which validation rejected as impossible and retried the WHOLE read at an API
call each. **10 of the session's first 17 retries.** The card's name already
settles what it is and `TACTICS_NAME_TO_KIND` was already in the file;
`repair_misread_cards()` now applies it at the one live read site. That retry
class went **6 → 0**.

### 3. `discards_left` retry storm
Vision read `4` off the same frame **11 polls running**, then `3` for 15
straight, which aborted a paid match. Retrying cannot fix a stable misread.
Now clamped — to **zero**, not to the cap, because an untrusted count must
never authorise a discard: a hallucinated count once drove 33 discard attempts
across 4 matches where at most 8 were possible. **24 → 0.**

### 4. A misread `result` screen threw away a $50 match
One card into a match, a 0-0 `result` read logged a **draw** and ended it. The
existing C5 guard can't catch this — it only asks whether this process paid for
a match, and it had. A match is 5 rounds, so a 0-0 result before
`MIN_PLAYS_FOR_RESULT = 4` plays is a transition overlay. It re-reads rather
than rejecting, and accepts after 3 polls agree, so a genuine 0-0 still scores.
Verified by disabling the guard and watching the new test fail.

### 5. The route judged arrival on a MOVING frame
`go.attempt()` captured its frame *before* `ar.clear()`, so `at_table()` was
evaluated on a character still walking — a true snapshot of someone passing
through the right spot. It now waits for the view to go still
(`_wait_until_still`, bounded at 8s) rather than sleeping a guessed duration,
because a fixed 1.5s was measurably not enough: `c_end` scored a genuine prompt
(correlation +0.32, +0.37 against a 0.15 bar) while the orchestrator's first
read moments later found the character against a wall at +0.009.

### 6. NPCs blocking the walk went unnoticed
`walk_forward()` RETURNS how far the view moved and both step loops discarded
it, so a step that walked into an NPC was indistinguishable from one that
worked — the nudge spent its whole budget shoving into somebody. Now
`_step_forward()` checks it and calls the existing `ws.unstick()` (crab left,
right, hard left).

Measured from the blocked run: walking moves the frame **16–59**; every sample
across the 45s stuck behind an NPC read **0.5–2.3**. `ws.STUCK_CHANGE` is 2.5,
which separates them with no new constant.

**When it applies and when it must not:** it is judged on the movement of a
step we JUST COMMANDED. Standing still legitimately looks identical — a real
12-second pause on the same run read 0.8–4.4, inside the stuck band — so a
general "the screen is frozen" rule would fire on it. Gating on a commanded
step removes that whole class of false positive and needs no NPC detector.

### 7. Cycle diagnostics overwrote each other
`go.main(n=1)` always writes to `attempt01`, so every cycle silently destroyed
the previous cycle's route frames. A conclusion was drawn from the wrong
cycle's evidence before this was caught. Each cycle/attempt now gets its own
folder.

### 8. Smaller ones
- `run_cycles.log()` didn't accept `flush`, which `go.main` passes — surfaced
  as "could not reach the table" three times, costing a whole 5-cycle run.
- `go.main` returns `(wins, best)`; truth-testing the tuple is always True, so
  a total miss would have marched on to buy a $50 match away from the table.
- The reset's confirm-dialog check slept a fixed 1.2s and measured once; the
  dialog animated in slower, the single reading caught 2.7 of noise above the
  2.0 bar, and the YES press became the one that OPENED the dialog. Now polls.
- `reset_env` is contractually fail-fast (its tests pin it to 2 crosses and a
  60s ceiling), so the retry now lives in the caller.
- Wrong progress file: `run()` defaults to `progress.json` while recent
  training uses `progress_testing.json`. Scoring into the wrong ledger would
  have corrupted both.

---

## Measured and NOT acted on

**The `secondary` (fielding/speed) question is still open, despite p=0.003.**
The pooled figure crossed significance and does not survive inspection:
batting p=0.007, **pitching p=0.937** — and pitching is the half
`FIELDING_POWER_BUDGET` is actually about. The groups also differ in raw power
(7.44 vs 8.16, p=0.049), so part of the margin gap is just stronger cards.
`analyze_match_log.py` now prints both checks every run so this cannot be
missed again. `FIELDING_POWER_BUDGET` stays at 1.

**The jukebox landmark cannot be used to course-correct.** Measured across the
walk, the jukebox template scores **0.48–0.58 on every frame** — including
frames where the character is wedged in the middle of the bar facing a wall.
It matches everything, so it carries no positional information; steering on it
would be steering on noise. The dealer never exceeded **0.305** in the same
sequence against a `RECOVER_IN_VIEW` bar of 0.42, so `_recover` gives up there
every time. This is the same trap the code already documents: "adding thirteen
templates raised the match score everywhere rather than sharpening it."

**Local OCR matched vision on card POWER 41/41 times.** Every one of the 10
disagreements was on `secondary`, none on power — and power is what drives
every decision. That is the strongest lead for cutting API cost, but 41
comparisons is a signal, not a mandate, so it needs a few hundred and a stated
threshold first.

---

## Corrections I had to make to my own reported findings

Worth recording because the pattern matters more than the individual errors:
each was me narrating what a frame showed instead of confirming it.

1. **The bottom-left coin is HEALTH, not money.** Twice. It produced "the
   tracked balance drifted, correct it to 100" (overwriting a correct value)
   and "the save only restores $100" (it restores 246). Money is visible only
   on the pause menu. Now in `CLAUDE.md` and memory.
2. **"The dealer is at the right edge"** — that was a different mouse NPC
   standing outside the bar, seen through the window. She is a live hazard for
   the dealer template too, so she is now documented.
3. **"The frames prove the route was fine"** — those were the *next* cycle's
   frames, because of the overwrite bug in §7. Cycle 1's evidence was already
   gone.
4. **"The adaptive backoff is broken"** — it isn't;
   `MISFIRES_BEFORE_BACKOFF = 2` is deliberate and it fired correctly at 0.40s
   then 0.45s.
5. **"The analyzer's identical ternary is a bug manufacturing the
   significance"** — it is dead code, but always using `our_secondary` is
   correct on both halves.

---

## Overnight, run 2 (relaunched ~00:15)

Run 1 died at cycle 1: the walk missed 3 times and `cycle()` returned False,
which ended all 20 cycles. Three fixes before relaunching.

### 9. A missed walk ended the entire run
The route is ~85% per attempt and its failures are position-dependent, so the
single most effective remedy is a fresh reset — which is exactly what the next
cycle begins with. Ending 20 cycles because one walk missed three times wastes
the whole night. A missed route now skips to the next cycle, bounded by
`MAX_CONSECUTIVE_ROUTE_FAILURES = 3` so it cannot circle forever.

### 10. A dead branch that logged something it never did
In `go.attempt()`:

    if ahead >= DEALER_AHEAD:
        img = _nudge(...)
    else:
        log("dealer not ahead; retracing first")
        img = _nudge(...) if ahead < DEALER_AHEAD else _back_off(...)

Inside that `else`, `ahead < DEALER_AHEAD` is necessarily true, so the ternary
always chose `_nudge` — `_back_off` was unreachable and the "retracing first"
message described something the code never did. Collapsed to a plain `_nudge`,
because the outer `if not at_table` below already falls back to `_back_off`,
so nudge-then-retrace was the real behaviour either way.

The score could not carry that decision regardless: the dealer template
measured **0.21–0.31** across a whole approach, under the 0.41 bar even in
frames where she was plainly visible.

### 11. My own edit made the match call unreachable
Adding the route-failure return left a stray `return True` above
`orchestrator.run(...)`, so every cycle would have reset, walked to the table,
and then never played a match — silently, all night. Caught by reading the
resulting file rather than trusting the edit, and by an AST check that the call
is still reachable.

### Route diagnostics now in place
Run 1's three misses read ink 0.0076 / 0.0110 / 0.0149 against a 0.024 bar,
with **no** `crabbing` or `still moving after clear` messages — so the new
detectors were quiet and correct: the character was not stuck and not drifting,
it simply ended short. That is the remaining route problem, and it is now
cleanly separated from the two failure modes that were being confused with it.

---

## Morning session — navigation (2026-09-01)

The overnight run produced nothing: the PS5 went to standby at 00:20:54, four
minutes in, and `ensure_stream` could not wake it inside its 150s budget. Zero
cycles, zero matches, zero API calls. I reported it as running and then waited
on monitor events — but a dead run and a healthy one produce the same silence,
and I never checked which I had.

chiaki logs `[I] Ctrl received Heartbeat, sending reply` while a console is
connected. That is a real liveness signal and silence is not.

### 12. The compass cannot tell you WHERE you are
The user's correction, and it reframes most of what I built: north indoors and
north outdoors read identically. Every recovery in the route — turn to a
bearing, retrace east, correct to the recorded heading — is heading-based, and
heading is location-blind. Demonstrated exactly: multi-checkpoint correction
took the end heading from 124.8 (38 degrees off) to 87.68 against a 87.0
target, and the character was still jammed in a wall. The only measurable thing
was corrected and it was not the broken thing.

### 13. Appearance-based localisation (`places.py`)
Answers the question dead reckoning cannot. Measured before building:

    raw intensity   same-place 0.51/0.58, different-place 0.64/0.74
                    -> DIFFERENT places scored HIGHER. Unusable.
    edge structure  same-place 0.646, different-place 0.395  (+0.251)

The HUD is masked, and that is load-bearing: quest list, compass and health coin
are pixel-identical in every frame, so leaving them in drags every comparison
toward 1.0.

Leave-one-out over the labelled set: **17/17 correct, 0 abstentions, 0 wrong.**
It abstains below 0.55, or when two rooms are within 0.06 of each other —
being confidently in the wrong room is what sends a route at a doorway on
another floor.

### 14. Heading-conditioned matching: tried, measured WORSE, reverted
Filtering references by heading seemed obviously right. Leave-one-out, n=17:

    heading ignored   correct 7   abstain 8   WRONG 2
    heading used      correct 2   abstain 9   WRONG 6

Structural, not tuning: filtering strips the true room to the two or three
frames facing that way while rooms whose frames carry no heading keep all of
theirs. The measurement is recorded in `places.py` so it is not re-attempted.

### 15. Walkable graph + Dijkstra (`worldmap.py`)
`worldmap` dead-reckoned positions and answered with straight lines — its own
docstring warns "a straight line between two mapped points may go through a
building". Added `connect()` (legs actually walked, cost in walk-seconds) and
`route()` (Dijkstra). Refuses unconnected goals with None rather than a
bearing. Verified by breaking it: with the relaxation clause removed it returns
the 23-cost path instead of the 13-cost one, and the test fails.

### 16. Panoramas placed by measured heading (`panorama.py`)
No feature matching needed: the compass reads yaw off the frame and the FOV was
measured at 102 degrees, so each slit goes at its true angular position. Found
and fixed a real defect — uniform slit widths assume an even sweep and left
**420 of 3600 columns uncovered** at a few degrees of overshoot. Giving each
slit its own angular share (midpoint to midpoint) tiles exactly whatever the
sweep did: 0 uncovered at ±4 and ±12 degrees.

### 17. A labelling error the test caught
`wedge_spot` and `beside_dealer_table` matched at 0.969 — because they were the
same spot: the panorama was swept from exactly where the wedged route ended and
given a second name. Merged. Leave-one-out went from 7/17 with 2 wrong to
17/17 with none wrong.

### Where the route actually fails, now that rooms are named
The user identified the failure spot as **beside the dealer table** — one spot
from the target, not lost in the building. From there the prompt-ink signal
peaks at heading ~295 (0.0217, just under the 0.024 bar), i.e. BEHIND the
character: the walk overshoots eastward past the table. Walking that bearing
did not recover it — the crab freed the character with a 34.8 lateral jump and
ink collapsed to 0.0000 for every step after. The best position was before
moving at all.

Open: the final leg from `beside_dealer_table` to `dealer_table` is one small
correction and is not yet learned. That leg is the whole remaining gap.

---

## Afternoon session — turn logging (2026-09-01)

### 18. The reveal window was closing before the cards arrived
`reveal cards never appeared` was losing **180 of 215 cards (84%)** — an hour
of pure waiting per run, and the reason a whole run grew match_log.jsonl by 2
rows. Measured over 877 frames sampled at 2s:

    reveal visible in            129/877 frames (14.7%)
    distinct reveal events       40
    each stays up for            8-12 seconds
    turn period (reveal->reveal) p50 33s, p75 52s
    turn periods exceeding 20s   82%

82% of turn periods longer than the 20s window against an 84% failure rate is
the whole explanation. The detector was never at fault — the cards are on
screen for ten seconds at a time, which a 0.25s poll cannot miss.

`REVEAL_MAX_WAIT` 20s -> 45s. Nearly free: the wait returns the moment it sees
the reveal, so a working turn is not slowed; only a turn with no reveal coming
pays, and those were already paying 20s to fail.

**Result, measured live: rows per card 1% -> 35%.** A 35x change in data yield.
I predicted ~80% and got 35%, so the magnitude was wrong — fixing the timeout
exposed the next bottleneck rather than reaching the ceiling.

### 19. Four silent failures, all the same shape
Every bug today was a failure that produced the same output as success. The
fixes are two or three lines each; finding them took the day.

| where | did nothing, silently | now |
|---|---|---|
| `chiaki_pid()` | cached a pid forever; after a chiaki restart every CGEventPostToPid hit a dead process, delivered nothing, raised nothing, and reported success | verifies with `os.kill(pid, 0)` and re-resolves |
| `press()` | fell through to focus+pyautogui — typing into whatever window is frontmost — when injection failed | announces the fallback and where keys will go |
| `run_tests.sh` | printed "all green" for ZERO tests; no per-test timeout, so one hang blocked the suite forever | counts files, fails on zero, kills at `TEST_TIMEOUT` |
| `go.main()` | `attempt(log=lambda m: None)` discarded every route diagnostic | passes the log through |

The `go.main` one produced a false conclusion I reported: "no crabbing
messages, so nothing was stuck" was read off a log that could not have
contained them.

### 20. Route: measured, not guessed
- Heading corrections **never ran** — a single `read_bearing()` on a
  post-walk frame returns None often, and the function returned silently. Now
  retries via `ws.read_heading()` and reports either way.
- Multi-checkpoint corrections **made it worse**: 0/3 attempts with ink 0.0000
  every time, versus 3/8 with ink up to 0.046 on the single correction. The
  corrections were injecting the drift they then corrected — error at t=50 was
  -20.2 with them and -0.9 without.
- A crab of 2.6 counted as "escaped" because `ws.unstick()` reports success at
  `STUCK_CHANGE` (2.5), which only means "not completely dead". Walking moves
  the frame 16-59; a real escape measured 34.8. `ESCAPED_CHANGE = 8.0` sits in
  the gap. Before: twelve nudge steps twitching against a wall.
- The Wanda go-around was **unbounded** — it fired on all twelve steps of one
  nudge, detect/crab/`continue`/detect, ending at ink 0.0163 having spent every
  step sidestepping on the spot. Now capped at 3.

### 21. Where the turn losses now are
Cumulative this cycle, 31 cards:

    reveal cards never appeared   7 (23%)
    intended card absent          9 (29%)
    no OPPONENT card identified   2 (6%)
    rows logged                  11 (35%)

`intended card absent` is NOT dropped input (3x slower changed nothing) and NOT
misread powers (accurate against the roster). Live reveal frames show both
sides face up, so it is not a timing problem either. Eleven frames are saved in
`test_fixtures/reveal_occlusion/`; they show a played card substantially
occluded by its own paired tactics card, and base runners drawn face-up on the
diamond as extra player cards competing for the read's 2-per-side contract.
Since `best_batting_play()` always attaches a boost when it has one, OUR card
is the one systematically hardest to see — which also explains why every
revealed power is lower than what we played.
