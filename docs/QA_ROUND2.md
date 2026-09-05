# QA Round 2 — verifying the round-1 fixes, and what they broke

Method: everything below was run against a **sandbox copy** of the tree
(`orchestrator.py`, `input_controller.py`, tests, fixtures, and 121 real ban
frames rsynced out). Nothing ran the game, sent a keystroke, or wrote to real
project data — `BASEBALL_MATCH_LOG` / `BASEBALL_DIAGNOSTICS_DIR` were redirected
to temp paths for every invocation. The real tree was verified byte-identical
afterwards (see the last section).

Baseline in the sandbox: **15/15 green.**

Tags used exactly as defined:

* **[MUT]** — the code was mutated and the suite's response observed.
* **[EXEC]** — the shipped, unmutated code was executed against a scripted
  screen sequence or real frames.
* **[REASONED]** — argued from source only. Said so every time.

Probes and the mutation driver live in the sandbox, not the project:
`…/scratchpad/mut2.py`, `…/scratchpad/sandbox/zz2_{crop,margin,margin2,partb}.py`.

---

## Part A verdict at a glance

| Round-1 finding | Fix real? | Test pins it? | Evidence |
|---|---|---|---|
| F1 untracked `start_match` presses | **YES** | **YES** | MUT: removing the `if match_in_progress` skip → 14 presses, red |
| F2 double-scoring an unpaid result | **YES** | **YES** (3 of 4 cases) | MUT: `if not match_in_progress:` → `if False:` → red |
| F3 unbounded alternation (the 120-poll bound) | **YES** | **YES** | MUT: bound → `10**9` and bound → `if False:` both red |
| F3 `bans_done_this_match` | code YES | **NO — asserted on the wrong harness** | MUT: guard deleted entirely → **green** |
| F3 C5 no longer zeroes `stuck_count` | code YES | **NO** | MUT: re-zero it → **green** |
| F5 ban-scan coverage | **PARTIAL** | flag still untested | MUT: `TRUST_ROSTER_ONLY=False` → **all 14 files green** |
| F6 cache poisoning | **YES** (for <3) | **YES** | MUT: unconditional cache → red |
| F7 `_synthetic` false positive | **YES** | **YES** | MUT: re-add the `BASEBALL_MATCH_LOG` key → `test_state_io.py` red |
| F8 stall exits set `stop_reason` | **INCOMPLETE** | partial | EXEC: 1 of 5 stall exits still writes no bundle |
| F9 `screen_is_moving()` try/except | **YES** | **YES** | MUT: unwrap → red with a traceback |
| NEW `detect_ban_grid_locked()` crop | **claim CONFIRMED** | **NO** | EXEC: bit-identical; MUT: `margin=0` → green |

Eight mutations survived. They are the findings below.

---

## Ranked findings

### 1. HIGH — a restart mid-match silently loses a genuine win  [EXEC]

`orchestrator.py:2715-2726`.

`match_in_progress` initialises to `False` at `:2508` and is only ever set True
by this process's own debit at `:2848`. So on **any** rerun — after a stall,
after `no_progress`, after Ctrl-C, after the operator restarts the script — the
loop believes no match is paid for. If the game is showing the result overlay of
the match the *previous* process paid for, the new process refuses to score it:

```
seed 4 wins, game shows a genuine WIN overlay on a restart
  Result screen with no paid match in progress — already scored, not counting it again (1/15).
  Result screen with no paid match in progress — already scored, not counting it again (2/15).
  -> wins after run: 4        (5 if the win had counted)
  -> close_result presses: 2  (the overlay is dismissed, so the loss is permanent)
```

The $50 was spent by the previous process, the match was won, and the win is
discarded with a message that asserts the opposite of what happened ("already
scored"). It is not "already scored" — it was never scored by anyone.

This is the exact question the round-1 write-up flagged as *"a decision, not a
patch"* (F2, item 3 of its next-steps list). The patch shipped; the decision
about the restart case does not appear to have been made. Every stall exit in
this loop is followed by "just rerun the script to pick back up", so the restart
path is the *designed* recovery, and it is the path that drops wins.

Severity is HIGH because the failure is silent, self-describing as normal, and
the run's whole purpose is accumulating a win count.

**Shape of a fix:** the safe direction is not "never score an unpaid result", it
is "never score the *same* result twice". Persisting `match_in_progress`
alongside wins/balance in `progress.json` makes the restart case correct without
reopening F2 — the flag then means what its name says across process
boundaries. A cheaper stopgap: score the first result seen in a fresh process
if `spent == 0` and no result has been scored yet this process.

---

### 2. HIGH — `TRUST_ROSTER_ONLY` still survives a flip across the entire suite  [MUT]

`orchestrator.py:2029`, `:2073-2074`.

Round 1's F5 said the flag flip "survives the whole suite". `test_ban_scan.py`
was added in response. It does not close this: **every call in the new file
passes `trust_roster=` explicitly** (`test_ban_scan.py:96, 125, 131, 155, 167`),
so the production binding — `if trust_roster is None: trust_roster =
TRUST_ROSTER_ONLY` — is never exercised.

```
[TRUST_ROSTER_ONLY = True -> False]
  test_ban_grid_locked  PASS    test_ocr_ban_card     PASS
  test_ban_scan         PASS    test_ocr_runner       PASS
  test_gameplay_regions PASS    test_ocr_scoreboard   PASS
  test_image_pipeline   PASS    test_roster_matching  PASS
  test_input_timing     PASS    test_run_state_machine PASS
  test_known_ban_roster PASS    test_settle_regions   PASS
  test_state_io         PASS    test_validate_game_state PASS
                                                   14/14 SURVIVED
[trust_roster default rebound to False]  test_ban_scan  PASS   SURVIVED
```

What did improve is real and worth keeping: `read_full_ban_collection()` is now
*executed*, the local path is proven to make 0 vision calls and 0 OCR calls, the
scroll unwind is asserted balanced, and F6 is genuinely pinned. The gap is
narrower than round 1's but it is the same gap: flipping the documented rollback
switch changes production behaviour (vision calls, cost, latency, which cards
resolve) and nothing goes red.

**Fix:** one test that calls `read_full_ban_collection()` with **no**
`trust_roster` argument and asserts behaviour consistent with the module flag.
Two lines.

---

### 3. HIGH — `bans_done_this_match` has no assertion at all; the F3 ban check reads the wrong harness  [MUT]

`orchestrator.py:2862-2871`; `test_run_state_machine.py:461-463`.

Deleting the entire `bans_done_this_match` guard leaves
`test_run_state_machine.py` **green**.

Cause, and it is textbook LESSONS §1: the assertion

```python
check(len(h.bans_submitted) <= 2, "QA1-F3: ... bans are once per match ...")
```

is evaluated against the `h` bound at line 448 — the
`discard_prompt`/`turn` harness, which **contains no `ban_screen` at all**. So
`len(h.bans_submitted)` is `0`, and `0 <= 2` is vacuously true. The harness that
does exercise bans (line 432, `match_start_prompt` ↔ `ban_screen` × 400) is
overwritten before the check runs, and its own comment even says the ban guard
"now catches [that pair] independently" — the very property the reassignment
stopped it from asserting.

Two more mutations in the same family survive, both from the F3 fix:

| Mutation | `test_run_state_machine.py` |
|---|---|
| delete the `bans_done_this_match` guard | **PASS — survived** |
| delete `bans_done_this_match = False` on debit (`:2849`) | **PASS — survived** |
| C5 branch re-zeroes `stuck_count` instead of incrementing (`:2829`) | **PASS — survived** |

The middle one is the dangerous direction and is exactly the coordinator's
question: with that reset gone, **match 2 is never banned** — the loop reaches
the ban screen with the flag still True from match 1, refuses to toggle, and
stalls out 15 polls later having already paid $50. Nothing in the suite notices.

The third survives because the *new global bound catches the same observable at
120 polls* — LESSONS §1's "something else produces the same observable", created
by the F3 fix itself. Defence-in-depth, so lower severity, but the comment at
`:2823-2828` claims a property no test holds.

**Fix:** move `check(len(h.bans_submitted) …)` to operate on the line-432
harness and require `== 1`, and add a two-match sequence asserting `== 2`.

---

### 4. MED-HIGH — `polls_without_progress` is untested in the false-fire direction, and a placed ban is not "progress"  [MUT] + [EXEC]

`orchestrator.py:71`, `:2633-2639`, resets at `:2756`, `:2850`, `:3010`.

Measured boundary, shipped code, scripted sequences:

```
MAX_POLLS_WITHOUT_PROGRESS = 120     MAX_STUCK_ATTEMPTS = 15

300 consecutive successful plays        -> 302 screens, bound never fires   OK
1 play then 3 redraws, x75              -> 301 screens, bound never fires   OK
a play every 100 polls                  -> 607 screens, bound never fires   OK
a play every 119 polls                  -> 715 screens, bound never fires   OK
a play every 121 polls                  -> 122 screens, no_progress FIRES
a play every 200 polls                  -> 122 screens, no_progress FIRES
```

So the bound is exactly where it says it is, and it does **not** fire on a
healthy match. To the coordinator's specific worry: a full ban scan is **one**
loop iteration, not five — `read_full_ban_collection()` is called inside the
`ban_screen` branch at `:2894` and does all its scrolling and settle waits
without returning to the poll loop. It costs 1 poll of the 120, not 5, and its
measured 149s of wall time is invisible to this counter. **No false-fire risk
from the ban scan.**

The real problems are the untested directions:

| Mutation | `test_run_state_machine.py` |
|---|---|
| `polls_without_progress = 0` on a played card deleted (`:3010`) | **PASS — survived** |
| `polls_without_progress = 0` on a scored result deleted (`:2756`) | **PASS — survived** |

Both mutations turn a healthy match into a forced abort at poll 121, mid-match,
after the fee is paid — and the suite is green. The suite asserts only that the
bound **fires**; nothing asserts it **does not fire** while the session is
advancing. That is LESSONS §1's one-sided-bound pattern, in a guard whose whole
risk profile is false positives.

Related gap, [EXEC]: **a successfully placed ban does not reset the counter**
(`:2936-2937` sets `bans_done_this_match` but not `polls_without_progress`).
Verified: `debit → ban_screen → other` places 1 ban and leaves the counter at 2.
Today the debit one poll earlier zeroes it, so there is ~118 polls of headroom
and no live risk. It is on the list because "a debit, a scored result, or a
played card" is the documented definition of progress and placing three bans is
plainly progress by any reading — the omission is invisible until something
changes upstream.

**Fix:** add the mirror assertion — a 200-poll match that plays a card every
~30 polls must run to completion and must NOT write a `no_progress` bundle. Then
the two survivors above go red.

---

### 5. MED — F8 is incomplete: one stall exit still writes no diagnostics bundle  [EXEC]

`orchestrator.py:3141-3145`.

```python
                    stuck_count += 1
                    if stuck_count >= MAX_STUCK_ATTEMPTS:
                        print("Discarding repeatedly with no play landing — "
                              "stopping. Check the game manually.")
                        break                      # <-- no stop_reason
```

Every stall path driven to its exit against the shipped code:

```
NO BUNDLE   N25 discard/redraw never lands        <-- still silent
BUNDLE      C3 ban screen never advances               (fixed)
BUNDLE      bans_done re-entry (new exit)              (correct)
BUNDLE      C1 result never dismisses                  (fixed)
BUNDLE      unrecognized screen
```

Round 1 listed three silent exits; two were fixed and this one was missed. It
`break`s with `stop_reason` still `None`, so the `finally` at `:3170` skips
`dump_diagnostics()`, and the run then prints the same closing line as a healthy
early stop. From the terminal it is indistinguishable from running out of money.

Also [MUT], a second-order gap: deleting `stop_reason = "ban_screen_stuck"` from
the *new* `bans_done_this_match` exit (`:2868`) leaves the suite **green** — the
F8 regression test at `test_run_state_machine.py:486-490` covers only the C1
result path, so the other stall exits' `stop_reason` assignments are unpinned.

**Fix:** `stop_reason = "discard_never_lands"` before that `break`, and make the
F8 test loop over the stall paths instead of testing one.

---

### 6. MED — the `detect_ban_grid_locked()` crop claim is CORRECT, and nothing protects it  [EXEC] + [MUT]

`orchestrator.py:493-527`.

**The claim is confirmed independently.** I reimplemented the pre-crop
(full-frame) version from the shipped constants and compared cell-by-cell.

*Analytically*, across every distinct image geometry in the tree (18 sizes, 137
frames, from 1999×1292 through 3376×2120):

```
MASK_KERNEL=41  radius=20  margin=22
every size: margins L22 R22 T22 B22   OK   (crop edge never clamps to the image)
```

Because `margin = MASK_KERNEL//2 + 2 = 22 > radius 20`, every sampled pixel's
Max/Min kernel window lies entirely inside the crop, so its value is
bit-identical. This matters more than the docstring implies: PIL's `RankFilter`
pads with **zeros** via `Image.expand`, not by edge replication, so a margin
*below* the radius would silently darken the border and change the contrast
means. The chosen margin is on the right side of that line, with 2px to spare.

*Empirically*, on real frames:

```
margin=  0   max cell-mean delta 0.881 - 1.352   bool flips 0
margin=  4   max cell-mean delta 0.260 - 0.738   bool flips 0
margin= 10   max cell-mean delta 0.190 - 0.428   bool flips 0
margin= 20   max cell-mean delta 0.000           bit-identical
margin= 22   max cell-mean delta 0.000           bit-identical   <-- shipped
                                       (10 frames: 4 fixtures + 6 live ban frames)
```

and a full old-vs-new comparison on the two `test_fixtures` ban frames:

```
identical booleans   : 2/2
bit-identical means  : 2/2
worst cell-mean delta: 0.0
time old / new       : 28.3s / 15.0s  ->  1.88x
```

So: **exact — verified, not taken on trust.** One correction to the comment at
`:501`: I measure **1.88x**, not 2.2x, on this machine at 2000×1292. Directionally
right, the number is optimistic.

The problem is that none of this is defended:

| Mutation | `test_ban_grid_locked.py` | `test_ban_scan.py` |
|---|---|---|
| `margin = MASK_KERNEL // 2 + 2` → `margin = 0` | **PASS** | **PASS** |
| `margin` → `4` (below the radius) | **PASS** | **PASS** |
| shift `gy0` by +10px | **PASS** | **PASS** |

The reason margin=0 survives is visible in the table above: the perturbation is
~1.3 contrast units against a 100.0 threshold and a measured 52–56 / 170–187
class separation. On *these* frames it flips nothing. It is a latent
correctness loss that only becomes visible on a frame that sits near the
threshold — i.e. exactly the frame where a wrong answer bans the wrong card.
The "12/12 identical" validation was a one-off manual check, not a regression
guard; if `MASK_KERNEL` is ever raised or the grid fractions move toward an
edge, nothing will tell you.

**Fix:** assert the property directly rather than the outcome — compute the grid
at `margin` and at `margin + 60` in the test and require the cell means to be
bit-identical. That is cheap (one extra crop, no full-frame filter) and it goes
red for every mutation above.

---

### 7. MED — `test_ban_scan.py` silently skips when its fixtures are gone, and its fixtures live in a directory the run prunes  [EXEC]

`test_ban_scan.py:40-44`.

```python
FRAMES = sorted(glob.glob(... "screenshot_log", "20260825_1659*.jpg"))
if not FRAMES:
    print("SKIP: no reference ban frames available")
    raise SystemExit(0)
```

Executed with those 27 frames moved aside:

```
SKIP: no reference ban frames available
exit=0            -> run_tests.sh prints "test_ban_scan.py  PASS"
```

The entire F5 remedy evaporates into a green line. And the fixtures are not in
`test_fixtures/` — they are in `screenshot_log/`, a **runtime output directory
that the orchestrator itself prunes** (`_prune_screenshot_log()`,
`orchestrator.py:782-793`, called from the logger thread at `:816`). Round 1
already noted that the prune global's *default* is the corpus root
(`orchestrator.py:766`). One `screenshot_log` cleanup, and the only test that
executes `read_full_ban_collection()` reports PASS while asserting nothing.

This is LESSONS §7's closing line — "a mutation check is only as good as the
test's ability to run at all" — recurring one file later.

**Fix:** copy 2–3 of those frames into `test_fixtures/` and glob there; make the
missing-fixture case a hard failure, not `SystemExit(0)`.

---

### 8. LOW-MED — F6 fixed the empty-scan case; the partial-scan case is unchanged  [REASONED]

`orchestrator.py:2282-2288`, caller at `:2894`.

The `len(full_collection) >= 3` gate genuinely closes round-1's headline case
(mutation to unconditional caching turns `test_ban_scan.py` red with the right
message). Round 1's stated *milder variant* is untouched: if only the **first**
frame is bad, row 0 is skipped, and a 28-card collection from a 33-card
collection is ≥3, so it is cached for the whole process and `choose_bans()`
picks from an incomplete pool with nothing printed.

Round 1's suggested fix had a second half — *"make the caller's retry force
`use_cache=False`"* — which was not applied: `:2894` is still a bare
`read_full_ban_collection()`. That half no longer matters for the <3 case
(nothing is cached, so the retry re-captures) but it is the only thing that
would recover a partial cache.

Not raised higher because I could not construct the partial case offline without
fabricating a frame; flagged as REASONED, and it is the same shape round 1
described.

---

## Part B: where I looked and found nothing

Stated explicitly so the absences are informative.

* **Can `bans_done_this_match` block a legitimate second match's bans?**
  **No.** [EXEC] The normal two-match flow
  `prompt → ban → turn → result → prompt → ban → turn → result` submits bans
  **twice** and costs $100 for 2 wins. The flag is reset by the debit that
  necessarily precedes every legitimate ban screen. The only way to reach a
  second ban screen with the flag still True is the no-second-debit path, which
  requires `match_in_progress` to already be stuck (finding 3 / below), and that
  run is stalling regardless.

* **Can `polls_without_progress` fire during a legitimately long stretch?**
  **No, on the sequences I could construct.** Measured boundary is exactly 120,
  a play every ≤119 polls never trips it, and the ban scan costs 1 poll rather
  than 5 (see finding 4). 120 polls is also ≥8× the `MAX_STUCK_ATTEMPTS` bound
  that governs every screen a real match dwells on. The risk is not the value,
  it is that no test defends the value from the other side.

* **Can `match_in_progress` get stuck True and deadlock the run?**
  **It stalls; it does not spin.** [EXEC] A match that ends without a scoreable
  result screen (`prompt → turn → other → other → prompt × 30`) leaves the flag
  True, and the next genuine prompt takes the C5 branch: **1 debit, 1
  `start_match` press, 17 screens, then a clean `match_start_prompt_during_match`
  stall with a diagnostics bundle.** F1's fix holds — round 1's 15 untracked
  presses are gone, confirmed both by mutation (removing the skip restores 14
  presses) and by execution of the shipped code. The cost of the stuck flag is
  one abandoned $50 match and a session that ends, not an unbounded loop.

* **Double-debiting.** I could construct no sequence that debits twice for one
  match. `F1`, `F2`, `F3a/b`, `F6`, `F7`, `F8a`, `F9` all turn the suite red, so
  those guards are genuinely pinned.

* **F7 (`_synthetic`).** Correctly fixed *and* correctly tested — the mutation
  re-adding `or os.environ.get("BASEBALL_MATCH_LOG")` turns `test_state_io.py`
  red with an accurate message (`"a redirected log alone marked the run
  synthetic"`). Round 1's note that `test_state_io.py` could not catch this no
  longer applies; a subprocess case covering redirect-only was added.

* **F9 (motion gate).** Correctly fixed and tested — unwrapping the try/except
  turns `test_run_state_machine.py` red with the `OSError` traceback.

* **The crop's grid output.** Bit-identical to the pre-crop implementation on
  every frame and every geometry checked (finding 6). No card-selection change.

---

## What I did NOT get to

Named so nothing is silently assumed clean:

* **Round-1 findings 10–16 were not re-examined** — the `select_bans_and_start_full()`
  column unwind, module state leaking across `run()`, the atomic-write test, the
  `test_no_side_effects.py` env inheritance, the silent focus failure, and the
  unvalidated balance. The brief scoped me to F1/F2/F3/F5/F6/F7/F8/F9 plus the
  crop; those seven are as round 1 left them unless someone fixed them
  incidentally, which I did not check.
* **The full old-vs-new crop comparison ran on 2 frames, not 137.** The
  full-frame implementation costs ~14s per frame, so the exhaustive run was cut.
  The *margin-sensitivity* sweep (which isolates the same property more cheaply)
  ran on 10 frames, and the *analytic* margin check covered all 137. I am
  confident in the exactness claim; the "12/12 identical" number itself I
  reproduced on 2, not 12.
* **No per-mutation full-suite runs except for `TRUST_ROSTER_ONLY`.** Every
  other mutation was scored against the file(s) that plausibly cover it. A
  mutation I recorded as SURVIVED might be caught by an unrelated file I did not
  run — though for the state-machine mutations, `test_run_state_machine.py` is
  the only file that executes `run()`.
* **`input_controller.py` was not touched this round.**
* **Nothing was validated against the live game**, per the constraints.

---

## Highest-value next steps, in order

1. **Decide the restart case** (finding 1). It is the only finding here that
   loses real, already-paid-for results, and the fix reopens F2 if done
   carelessly. Persisting `match_in_progress` to `progress.json` is the version
   that satisfies both.
2. **Fix the misdirected ban assertion** (finding 3) — one line moved, and three
   surviving mutations go red.
3. **Add the mirror assertion for `polls_without_progress`** (finding 4): a long
   healthy match must complete and must write no bundle.
4. **Give `test_ban_scan.py` durable fixtures** (finding 7) — otherwise
   findings 2 and 4's remedies can evaporate the same way.
5. **`stop_reason` on the N25 exit** (finding 5), and make the F8 test loop.
6. **One assertion pinning the crop margin** (finding 6): grid at `margin` vs
   `margin + 60` must be bit-identical.
7. **One test calling `read_full_ban_collection()` with no `trust_roster`
   argument** (finding 2).

---

## Sandbox hygiene

All mutation and probe work was done on a copy at
`…/scratchpad/sandbox/`. The real tree was checksummed before
(`baseline_md5.txt`, 358 files) and re-verified after: **no file in the project
was modified, added, or deleted** by this review, other than this report.
`screenshot_log/` was read from and copied out of, never written to (still 1937
files).

One caveat on that comparison, recorded rather than glossed: the checksum sweep
flagged `test_ban_scan.py` as changed. It was **not** changed by me — the file
was edited externally at 22:31:33, a moment after my baseline hash pass and a
moment before my `rsync`, so the baseline captured the older bytes while the
sandbox captured the newer ones. Verified: the sandbox copy and the live file
are byte-identical (`37182a76…`) with the same mtime, and `orchestrator.py` —
the file every mutation touched — is byte-identical to the sandbox too. So
everything reported above was measured against the version of
`test_ban_scan.py` currently on disk, and nothing I ran wrote into the project.
