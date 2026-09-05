# Overnight audit — prioritised backlog

Survey of architecture, edge cases, performance, dead code and stale docs.
Deliberately **not** covering vision-reader accuracy or test quality (separate
concurrent reviews).

**Every claim is tagged `[MEASURED]` (I ran it) or `[REASONED]` (I read it).**

## Reading notes

* **Line numbers are against `orchestrator.py` at 3334 lines.** The file was
  edited by another agent *during* this audit (3240 → 3334 lines: hardening in
  `validate_game_state`, a cutoff change in `ocr_runner_card`). Everything after
  L1601 shifted by +94 from the version at session start. `test_roster_matching.py`
  and `QA_VISION.md` also changed. None of those edits are mine.
* Nothing here ran the game, sent a keystroke, or wrote to real project data.
  All harnesses fake `press`, `capture_screenshot_image`,
  `wait_for_screen_to_settle` and `read_game_state`; `BASEBALL_MATCH_LOG` and
  `BASEBALL_DIAGNOSTICS_DIR` were redirected to temp paths throughout.
* Prior art credited where it exists: `QA_ROUND1.md` §590 and `QA_VISION.md`
  §845 already list the dead ban path. Items below add measurement, extent, and
  the consequences those notes did not draw.

---

## Severity summary

| # | Item | Sev | Evidence |
|---|---|---|---|
| 1 | Frozen stream resets every guard — unbounded loop | HIGH | MEASURED |
| 2 | 17 uncaught capture/input calls kill `run()` with no diagnostics | HIGH | MEASURED |
| 3 | `detect_ban_grid_locked` 7.19 s → 0.029 s, bit-identical | HIGH | MEASURED |
| 4 | `bans_done_this_match` not persisted; `match_in_progress` is | HIGH | MEASURED |
| 5 | Stale `match_in_progress` is a permanent, undiagnosable deadlock | HIGH | MEASURED |
| 6 | Two ground truths disagree on `secondary` | HIGH | MEASURED |
| 7 | `HEURISTICS.md` §2 documents the opposite of the current code | HIGH | MEASURED |
| 8 | `max_spend` resets on restart | MED | MEASURED |
| 9 | `TRUST_ROSTER_ONLY` removes the only position↔card cross-check | MED | REASONED |
| 10 | ~315 unreachable lines carrying the file's loudest warnings | MED | MEASURED |
| 11 | Test suite 457 s; 95% of one file is an unpatched audit screenshot | MED | MEASURED |
| 12 | 14 of 15 settle calls use the measured-worse region set | MED | MEASURED |
| 13 | Screenshot logger: 4.6 GB per run, old folders never pruned | MED | MEASURED |
| 14 | `LESSONS.md` §7 credits a now-dead code path with the ban-screen fix | MED | MEASURED |
| 15 | `LOCAL_VS_API.md` describes the ban path as live | MED | MEASURED |
| 16 | Source still carries the tesseract-era "unreadable badges" claim | MED | MEASURED |
| 17 | Phantom `"reveal"` settle region set | LOW | MEASURED |
| 18 | `_grab_animation_roi` has zero callers | LOW | MEASURED |
| 19 | `TEST_SUITE_AUDIT.md` runtime figure is 5.6× low | LOW | MEASURED |
| 20 | `report_misfire()` mutations survive `run()` | LOW | REASONED |
| 21 | `run_testing.py --reset` writes non-atomically | LOW | REASONED |

---

## 1. HIGH — A frozen stream resets every guard. The loop never stops. `[MEASURED]`

**`orchestrator.py:3260-3269`** (`stuck_count = 0` / `polls_without_progress = 0`
on a confirmed play).

This is the answer to "what happens on a Chiaki disconnect or the PS5 sleeping",
and it is the worst finding in the audit.

Both bounded-liveness guards are reset by *the same event*: a play landing.
`play_one_turn()` returns `played=True` whenever `select_and_play()` returns
without raising — and `select_and_play()` is just keystrokes, which return
normally whether or not anything is listening. So on a **frozen last frame**
(Chiaki stalled, PS5 asleep, stream stuck mid-turn):

* `screen_is_moving()` → `False` (a frozen frame is maximally still)
* `read_game_state()` → the same valid `turn` payload forever
* `play_one_turn()` → `(True, matchup_info)` forever
* `stuck_count = 0`, `polls_without_progress = 0` → **both reset every poll**

I ran the real `run()` against exactly this, with every boundary faked:

```
*** UNBOUNDED: still looping after 500 polls
    [input] 500 cards played, 0 suspected misfire(s) (0.0%) — input timing looks safe
```

It stopped only because my harness raised at poll 500 — and the loop absorbed
even that as an unreadable-screen retry. The final report line is the point: the
run declares its input healthy while having played 500 phantom turns.

Real-world cost per poll on this path: one vision API call, ~7-11 keystrokes
into whatever window holds focus, plus a 6 s `wait_for_reveal_cards` timeout and
up to 8 s of settle. That is ~18-22 s per iteration, so an overnight run is
~1,500 polls: **~1,500 wasted API calls and ~15,000 keystrokes into a dead
stream**, with no stall, no diagnostics bundle, and a cheerful summary.

**The detector already exists and is thrown away.** `wait_for_reveal_cards()`
returns `False` on a frozen frame, `orchestrator.py:3167` raises
`RuntimeError("reveal cards never appeared")` — and `orchestrator.py:3258`
swallows it with a bare `except Exception: pass`. On a healthy stream the reveal
fires on essentially every played turn; on a dead one it never fires.

**Fix.** Count consecutive `wait_for_reveal_cards()` failures and stop at a
threshold (5 is ~2 minutes). Independently, add the guard the pile is actually
missing: *screen content unchanged*. Every existing guard bounds "the screen
keeps changing in a way that isn't progress"; none bounds "the screen never
changes at all." A hash of the `hand` crop compared across polls is ~10 lines
and closes it directly.
**Effort: 1-2 hours** (the counter), **+2 hours** for the frame-identity bound.

---

## 2. HIGH — 17 uncaught capture/input calls; any display fault kills the run silently `[MEASURED]`

**`orchestrator.py:1240-1260`** (`_fast_grab`), **21 call sites in `run()`**.

`QA1-F9` added a `try/except` around **one** call — `screen_is_moving()` at
`orchestrator.py:2650` — with an explicit rationale:

> `_fast_grab()` calls `_MSS.grab()`, whose real failure modes on this machine
> are display reconfiguration, revoked screen-recording permission, and an mss
> handle invalidated over a long session.

That reasoning applies verbatim to every other caller of the same primitive, and
none of them got the guard. AST analysis of `run()`, counting only `try` blocks
that actually have handlers:

```
UNCAUGHT I/O calls in run(): 21
  wait_for_screen_to_settle: 11   press: 6   save_progress: 2
  record_observation: 1           _safe_prompt_check: 1
```

`record_observation` and `_safe_prompt_check` are internally safe. The live
exposure is **11 `wait_for_screen_to_settle` + 6 `press` = 17 sites**
(L2806, 2840, 2886, 2913, 2916, 2951, 2982, 2997, 3076, 3101, 3282 and
L2805, 2839, 2885, 2915, 2981, 3100).

Neither `_fast_grab` nor `_grab_settle_regions` nor `wait_for_screen_to_settle`
contains a `try` (verified by AST). So one mss fault anywhere raises straight
out of `run()`. The `finally` at `orchestrator.py:3295` then sees
`stop_reason is None` — the "stopped cleanly" sentinel — and **writes no
diagnostics bundle**. The most informative failure produces the least
information.

**Display change mid-run is worse than a crash.** `_MSS.monitors` is cached for
the process lifetime (`orchestrator.py:1214`) and the aspect-ratio sanity check
at `orchestrator.py:1226-1237` runs **once, at import**. Plug in a monitor, close
the lid, or let the stream renegotiate resolution, and every fractional crop
silently targets the wrong pixels with no warning and no raise —
`preflight.py:60-79` checks the same thing, also only before the run starts.

**Fix.** Move the guard down to the primitive: wrap the mss path inside
`_fast_grab()` and fall back to `pyautogui.screenshot()` (the fallback branch
already exists for `_MSS is None`). That fixes all 11 settle sites at once and
lets `QA1-F9`'s special case be deleted. Separately, re-check monitor geometry
periodically — cheap, and it converts a silent wrong-pixel run into a warning.
**Effort: 1 hour** for the unified guard; **2-3 hours** for periodic geometry
re-validation.

---

## 3. HIGH (performance) — `detect_ban_grid_locked` is 7.19 s; a bit-identical version is 0.029 s `[MEASURED]`

**`orchestrator.py:489-544`.**

Measured on 7 real fixture frames at 2000×1292:

```
detect_ban_grid_locked (cropped)   n=7  mean=7185.1ms  min=6568.2ms  max=7998.0ms
crop_gameplay_regions              n=7  mean=   0.5ms
input_prompt_visible               n=7  mean=   0.1ms
_encode_jpeg_b64                   n=7  mean=   7.8ms
_mean_abs_delta                    n=7  mean=   1.0ms
```

Every other local operation in the file is sub-10 ms. This one function is
~700× the cost of all of them combined, and the earlier crop optimisation (the
one recorded as taking it from ~13.8 s to ~6.4 s) left the real problem intact.

**The real problem is the algorithm, not the area.** `ImageFilter.MaxFilter(41)`
is a naive O(n·k²) morphological dilation — 1,681 operations per pixel. A square
max/min filter is **separable**: max over rows, then max over columns, which is
O(n·2k) = 82 operations per pixel. numpy's `sliding_window_view` does this with
no new dependency (numpy is already imported at `orchestrator.py:41`).

I implemented it and compared against the current code on **15 real frames**
(7 fixtures + 8 real ban frames from `screenshot_log/20260825_1659*`):

```
identical grids: 15/15   mismatches: 0
  PIL  MaxFilter/MinFilter : mean   7881.4 ms
  numpy separable          : mean     29.4 ms
  SPEEDUP                  : 267.9x
```

Then verified at array level, not just at the boolean-grid level:

```
crop shape (824, 1384)
EXACT array equality over WHOLE crop : True   maxdiff 0
EXACT equality excluding K/2 border  : True
cells vs border: min inset = 22  (needs >= 20)
```

**Bit-identical, maxdiff 0.** The same "cropping with a margin wider than the
kernel radius is exact" argument the current code already makes for its crop
(`orchestrator.py:514-518`) applies here too — the sampled cells sit 22 px from
the crop edge against a 20 px radius, so edge-handling differences cannot reach
them.

**What this costs today.** A production ban scan runs 5 iterations (traced:
`top_row` = 0, 1, 3, 5, 7, stopping at "No roster coverage at rows 7+"):

* now: **~36 s of blocking single-threaded CPU** per ban screen
* after: **~0.15 s**

During those 36 s the loop polls nothing and cannot react to anything on screen.
The `_cached_ban_collection` cache means only the first match of a process pays,
but `run_testing.py` and `run_tonight.py` both run 3-5 matches, so it is ~36 s
per session — and it is also why `test_ban_scan.py` had to build a memoisation
layer (`test_ban_scan.py:79-92`) just to stay tolerable.

**Fix.** Replace the two `filter()` calls with the separable numpy version.
Keep the existing crop. `test_ban_grid_locked.py` already pins the behaviour
against known frames, so the change is verifiable in seconds.
**Effort: 1-2 hours including verification.**

> Note: `MASK_KERNEL` is calibrated to `SCREENSHOT_MAX_WIDTH` and downscaling was
> already tried and correctly rejected (`orchestrator.py:520-524`). This finding
> is orthogonal — it changes the algorithm, not the resolution or the threshold.

---

## 4. HIGH — `bans_done_this_match` is not persisted, but `match_in_progress` is `[MEASURED]`

**`orchestrator.py:2643`** (`bans_done_this_match = False`, hardcoded at run
start) vs **`orchestrator.py:112-130`** (`save_progress` persists
`match_in_progress`).

These two flags describe the *same* match lifecycle, and they have different
lifetimes. `QA2-1` persisted `match_in_progress` precisely because "just rerun
the script" is the documented recovery path and an in-memory flag lost the paid
match. Its sibling never got the same treatment.

Scenario, run against the real `run()`:

```
### RESTART mid-match, screen = ban_screen (bans already placed in game)
  seed        : {'balance': 500, 'match_in_progress': True, ...}
  ban submits : 1  [[(0, 0), (0, 1), (0, 2)]]
  stop line   : Ban screen never cleared — stopping.
```

Pay $50, place 3/3 bans, get killed, rerun as instructed. `match_in_progress`
restores to `True` — but `bans_done_this_match` starts `False`, so the loop
re-scans and **re-toggles the same three cards, un-banning them**, then
double-presses `confirm_play` against a `0/3` ban screen the game will not
accept. It then stalls on its own `bans_done_this_match` guard.

Net result: **a paid match rendered unplayable by the documented recovery path** —
the exact loss class `QA2-1` exists to prevent, arriving through the guard that
was not persisted. `N11` (`orchestrator.py:3009-3015`) deliberately removed the
recovery press from the ban branch, so there is no self-healing either.

**Fix.** Fold both flags into one persisted `match_phase` field (see §22).
**Effort: included in §22.** Stopgap: persist `bans_done_this_match` alongside
`match_in_progress` — **30 minutes**, and strictly better than today.

---

## 5. HIGH — A stale `match_in_progress` is a permanent deadlock with no diagnosis `[MEASURED]`

**`orchestrator.py:2977-2982`** — `save_progress()` runs *before*
`press("start_match")`.

The ordering is right (record the debit before spending it). But it opens a
window: if the process dies, or `press()` raises (§2), after the save and before
the keypress, disk now says `balance -$50, match_in_progress=True` while no match
ever started.

Run against the real loop:

```
### RESTART with stale match_in_progress, screen = match_start_prompt
  seed  : {'balance': 450, 'match_in_progress': True, ...}
  after : {'balance': 450, 'match_in_progress': True, ...}
  stop  : Match never started — stopping. Check the game manually.
```

`after == seed`. The state is **fixed**. The C5 guard at `orchestrator.py:2934`
refuses to debit, the C2 guard refuses to re-press, the loop burns 15 polls and
stops — and writes the same state back. **Every subsequent rerun does exactly
this, forever.**

Three things make it worse than a normal stall:

1. The message says "Check the game manually" — the game is fine. The problem is
   in `progress*.json`, and nothing says so.
2. `preflight.py:80-99` reads that exact file and reports
   `wins/losses/draws/balance`. It never looks at `match_in_progress`, so it
   prints **READY** and the run dies 30 seconds later, every time.
3. The only recovery is hand-editing JSON, which is documented nowhere.

**Fix.** (a) Add `match_in_progress` to preflight's money section as a WARN with
the remedy spelled out — **20 minutes**, and it converts a silent recurring dead
end into a one-line instruction. (b) Have the `match_start_prompt_during_match`
and `match_never_started` stall messages name the field and the file —
**15 minutes**. (c) Structurally, §22.

---

## 6. HIGH — Two ground-truth sources disagree, on exactly the stat the project exists to measure `[MEASURED]`

**`orchestrator.py:1839-1873`** (`KNOWN_BAN_ROSTER`) vs
**`simulate.py:36-54`** (`CARD_POOL`).

Both are hand-maintained 33-card tables of the same collection. Diffed:

```
roster entries: 33  unique names: 33
simulate CARD_POOL: 33  unique names: 33
names in roster not in pool : (none)
names in pool not in roster : (none)
STAT DISAGREEMENTS:
   'Harold "Fisto" Blunt': orchestrator=(9, 3)  simulate=(9, 1)
   'Papa Jody Gain':       orchestrator=(5, 0)  simulate=(5, 2)
total disagreements: 2
```

Powers match on all 33. **Both disagreements are in `secondary`** — the
fielding/speed stat that `match_log.jsonl`, `run_testing.py`'s whole ~500-turn
data-collection plan, and `FIELDING_POWER_BUDGET` all exist to resolve.

`orchestrator.py:1842` carries `# corrected 2026-08-24: live capture showed
secondary=3, table had 1`. That correction was applied to the roster and never
propagated to `simulate.py`. So every simulation result about fielding was
computed against a *known-superseded* copy of the very variable under test.

Concretely this poisons **`HEURISTICS.md` §2**, whose entire argument is about
fielding-priority pitcher selection, and any future rerun of that experiment.
§4 (ban strategy) is safe — it keys on `power`, which matches.

**Fix.** Delete `CARD_POOL` and import `KNOWN_BAN_ROSTER.values()` in
`simulate.py`. One source, no drift. Then re-run `HEURISTICS.md` §2 and §5.
**Effort: 30 minutes for the change, ~1 hour to re-run and update the doc.**

> This is *not* the same as the row-geometry case at `orchestrator.py:583-591`,
> where unifying two independently measured constants took a reader from 18/18
> to 0/18. That comment is correct and should be left alone: those two constants
> encode different *measurements* (width-fractions for contrast sampling vs
> height-fractions for card crops). `CARD_POOL` and `KNOWN_BAN_ROSTER` encode the
> *same* fact, twice. Unify the duplicated fact; keep the distinct measurements
> apart.

---

## 7. HIGH (docs) — `HEURISTICS.md` §2 documents the opposite of what the code does `[MEASURED]`

**`HEURISTICS.md:64-94`** vs **`decision_engine.py:119-192`**.

The doc's heading is:

> `## 2. Fielding-priority pitcher selection (NOT CHANGED — simulation blind spot)`

and it concludes "Left as-is" and "Still not changing this without real data."

It **was** changed. `decision_engine.py:133-155` documents the 2026-08-25 rewrite
in detail: the old `(secondary, power)` sort — one fielding pip outranking any
amount of pitch focus — was measured to give up a stronger pitcher on 73.6% of
runner turns, surrendering 3.30 power on average, and was replaced by
`FIELDING_POWER_BUDGET = 1`.

A reader who opens `HEURISTICS.md` (the file *named* for heuristic decisions)
comes away believing fielding-priority is still live. This is the single most
misleading document in the tree because the doc and the code both read as
authoritative and they state opposite conclusions.

Same file, lower severity: §5's premise that `batters_used`/`target_score` are
set but never read is still accurate — but `orchestrator.py:2476-2482` (`N27`)
records that `turns_this_half` *undercounts on redraw turns*, which would make
the heuristic wrong if §5 is ever acted on. §5 does not mention it.

**Fix.** Rewrite §2's heading and conclusion to record the change and its date,
keeping the historical numbers as history. Cross-reference `N27` from §5.
**Effort: 30 minutes.**

---

## 8. MED — `max_spend` silently resets on every restart `[MEASURED]`

**`orchestrator.py:2597`** (`spent = 0`).

`balance` and `match_in_progress` are persisted; `spent` is not. So the session
cap restarts from zero on every rerun:

```
### max_spend=150 AFTER a restart (spent resets to 0)
  after       : {'wins': 3, 'balance': 350, ...}
  presses     : {'start_match': 3, 'close_result': 3}
  stop line   : Spend cap reached ($150/$150 spent this session) — stopping.
```

`run()`'s own docstring says "this session", so this is arguably as designed —
but it collides with two things the project states elsewhere:

* `run_tonight.py:9-19` frames `max_spend=150` as *the* stopping condition,
  chosen because the balance is **someone else's money** ($246 real vs $150
  capped).
* `run()`'s own exit message is "Progress is saved — just rerun the script to
  pick back up." Following that instruction after any stall spends another $150.

Three stalls in a night = $450 against a $150 intended cap.

**Fix.** Persist `spent` in `progress*.json` and treat `max_spend` as a
lifetime-of-file cap, or add an explicit `--new-session` flag to reset it.
**Effort: 1 hour** including a regression test alongside the existing spend-cap
cases in `test_run_state_machine.py`.

---

## 9. MED — `TRUST_ROSTER_ONLY` gives up more than its comment says `[REASONED]`

**`orchestrator.py:2120-2140`.**

The flag's comment states the cost plainly and, I think, incompletely:

> WHAT THIS GIVES UP, stated plainly: the ability to DISCOVER a card the roster
> has never seen.

Discovery is the *lesser* loss. The larger one: with `trust_roster` on, card
identity comes **only** from `KNOWN_BAN_ROSTER[(row, col)]`. Nothing ever looks
at the card's art, name or badges. The position itself is derived from
`detect_ban_grid_locked()` plus `top_row = max(0, presses_so_far - 1)` —
arithmetic resting on a behavioural assumption about the game's scroll
(`orchestrator.py:2170-2173`: "the first move_down just moves the cursor... every
move_down after that scrolls by exactly 1 row").

If a game update shifts grid geometry, or changes that scroll behaviour, or
inserts a row, then **every position resolves to the wrong card and the loop
bans three cards it never intended** — silently. All three integrity checks in
the ban branch (`N1` object identity, `N15` distinctness, the 3-distinct-positions
check at `orchestrator.py:3020-3028`) verify *internal consistency*, not
*correctness against the screen*. Three wrong cards pass all three.

The vision read that would have caught it — `read_ban_row_cards()`, which
reports what is actually legible — is exactly what the flag disables.

This is a deliberate trade ("the owner is renting the game"), and I am not
arguing to reverse it. I am arguing the comment understates the exposure, and
that a cheap cross-check would restore most of the safety:

**Fix.** On the first ban screen of a session only, OCR one known cell's name
(`ocr_ban_card_name` already exists and is otherwise dead — §10) and assert it
matches `KNOWN_BAN_ROSTER` for that position. One tesseract call, ~200 ms, turns
a silent mis-ban into a loud stop. Also amend the flag comment.
**Effort: 2-3 hours.**

---

## 10. MED — ~315 unreachable lines, carrying the file's most emphatic warnings `[MEASURED]`

Traced by executing `read_full_ban_collection()` with the **production default**
(no `trust_roster` argument) against a real ban frame under `trace.Trace`:

```
read_full_ban_collection: 101 statements, 55 NEVER EXECUTED under the production default
```

Genuinely unreachable statement blocks (excluding trace-entry artifacts):

| Lines | What |
|---|---|
| 2224-2231 | local name-OCR fallback + `_learn_roster_entry` |
| 2255-2258 | the tactics-boundary early stop |
| 2282-2295 | roster full-coverage short-circuit |
| 2302-2359 | vision read, per-row retry, vision-side roster learning |
| 2368-2372 | `consecutive_mismatches` stop, `max_presses` stop |

Plus these whole definitions, unreachable in production:

| Location | Lines |
|---|---|
| `orchestrator.py:424-461` `mask_low_contrast_regions` | 38 |
| `orchestrator.py:575-592` `get_ban_grid_card_crop` | 18 |
| `orchestrator.py:595-629` `ocr_ban_card_name` | 35 |
| `orchestrator.py:632-664` `_read_ban_rows_separately` | 33 |
| `orchestrator.py:667-714` `read_ban_row_cards` | 48 |
| `orchestrator.py:1933-1958` `_learn_roster_entry` (+ `_pending_roster`, L1930) | 26 |
| `orchestrator.py:344-367` `READ_BAN_ROW_CARDS_PROMPT` | 24 |
| `orchestrator.py:553-573` ban card-crop geometry constants | 21 |
| `orchestrator.py:2097`, `2105` `KNOWN_TACTICS_NAMES`, `PLACEHOLDER_CARD_NAMES` | 2 |

**~315 lines, ~9.4% of the file.** Confirmed dead by side effect too:
`known_ban_roster_learned.json` **does not exist** — the self-extending roster
has never persisted a single entry and, with the flag on, never can.

**Why this ranks above "tidy up later".** `QA_ROUND1.md:590-599` already argues
these should be *kept* as the rollback path, and I agree. The problem is that
nothing at the code marks them dead, and this region carries the most alarming
comments in the file — `N1`'s "15 of 17 plausible unknown names resolved to a
WRONG roster card", `I8`'s KeyError warning, the per-row retry's token
arithmetic, `I3`'s "a learned entry becomes permanent ground truth". A future
reader debugging a mis-ban will spend hours in code that cannot run.

Two of these are actively misleading rather than merely dormant:

* **The tactics-boundary stop (`orchestrator.py:2252-2258`) is unreachable even
  in principle at the current roster extent.** It requires
  `top_row > _max_roster_row() + 1`; `_max_roster_row()` is 6, so it needs
  `top_row ≥ 8`. `top_row` takes values 0, 1, 3, 5, 7, 9… and the scan already
  breaks at `top_row = 7` via "No roster coverage at rows 7+"
  (`orchestrator.py:2271-2274`). It can never fire. See §14 — a `LESSONS.md`
  section credits it with a headline win.
* **`ocr_ban_card_name`'s docstring is wrong on the facts.** See §16.

**Fix.** Do not delete. Add one banner comment at the top of each dead
definition: `UNREACHABLE while TRUST_ROSTER_ONLY is True (orchestrator.py:2140)
— rollback path, see QA_ROUND1.md §5.` Then hoist the flag check above the
scroll loop so the live path reads as a straight line (`QA_ROUND1.md:599`
already suggests this).
**Effort: 1 hour for the banners; 3-4 hours for the hoist + re-verification
against `test_ban_scan.py`.**

---

## 11. MED (performance) — Test suite is 457 s; 95% of its second-slowest file is one unpatched audit call `[MEASURED]`

Timed per file, in an isolated copy, with logs and diagnostics redirected:

```
test_no_side_effects.py            183.1s      test_ban_scan.py            37.3s
test_run_state_machine.py          126.5s      test_ban_grid_locked.py     23.0s
test_image_pipeline.py              37.2s      test_state_io.py            22.8s
(10 others: 27.4s combined)
--------------------------------------------------------------
whole suite      : 457.3 s (7.6 min)
test_no_side_effects.py alone: 183.1 s (40% of suite)
```

Two separate causes:

**(a) Everything runs twice.** `test_no_side_effects.py:79-81` runs every other
test file in a subprocess. `run_tests.sh` then runs all 16 files including that
one. The suite is ~1.75× the work it needs to be. That is by design and the
design is sound — but it means every second saved elsewhere is saved twice, and
it is why the fixes below pay double.

**(b) `test_run_state_machine.py` spends 95% of its time screenshotting the
desktop.** I instrumented it:

```
--- WHERE test_run_state_machine.py's TIME GOES ---
  total wall                 :   75.1s
  _fast_grab                 :   1423 calls    71.3s  (94.9% of file)
  input_prompt_visible       :   1387 calls    69.6s  (92.7% of file)
  dump_diagnostics           :     36 calls     4.3s  ( 5.8% of file)
```

`Harness` (`test_run_state_machine.py:163-179`) fakes every game boundary but not
`input_prompt_visible`. So `record_observation(prompt=_safe_prompt_check(), ...)`
at `orchestrator.py:2770-2774` takes a **real full-screen mss grab plus a resize
to 2000 px on every single loop iteration** — 1,387 of them, at ~50 ms each.

That call is documented as audit-only: *"AUDIT ONLY, drives nothing yet"*
(`orchestrator.py:1426`). So ~70 s per run, ~140 s across the suite (31% of
total), is spent on a signal nothing consumes. It also makes the suite
non-hermetic — it photographs whatever the user has on screen, ~2,800 times per
full run — and `dump_diagnostics` writes 36 desktop PNGs.

**Fix.** Add `"input_prompt_visible": lambda *a, **k: None` to `Harness`'s patch
dict — **one line, ~140 s off the suite**. Combined with §3's ban-grid fix
(another ~55 s across `test_ban_grid_locked` + `test_ban_scan`, doubled by the
re-run), the suite should land near **2.5 minutes**, which also cuts
`preflight.py:144`'s cost — preflight currently runs the whole 7.6-minute suite
before every session.
**Effort: 15 minutes** for the patch line.

> Flagged as performance, not test quality — the fix is a one-line patch entry
> and the win is mostly in `preflight`, which gates every real run.

---

## 12. MED — 14 of 15 settle calls use the region set the data says is worse `[MEASURED]`

**`orchestrator.py:1157-1161`** and 15 call sites.

`SETTLE_TIMING_ANALYSIS.md` measured this over 122 real animation events, and
`orchestrator.py:1139-1152` records the result:

```
gate                          continuation   latency p50   p90
hand alone (< 8.0)                  1.6%        2.01 s    6.01 s
hand AND legacy_roi                 3.3%        ~2.2 s   17.97 s
legacy_roi alone (the old code)    12.3%        2.24 s   14.07 s
```

with the conclusion that the combined gate is "both slower AND less safe".
`SETTLE_REGION_SETS["default"]` **is** the combined gate.

Grepping every call site: exactly one — `orchestrator.py:3282` in the turn
branch — passes `regions="turn"`. The other fourteen (L2376, 2413, 2432, 2806,
2840, 2886, 2913, 2916, 2951, 2982, 2997, 3076, 3101 and the `read_balance`
pair) take the default.

This is defensible for non-turn screens, where `hand` is meaningless — but that
reasoning is nowhere in the code, and `p90 = 17.97 s` against `max_wait = 8.0`
means those calls frequently *truncate*, printing "still moving after 8.0s —
reading anyway". The measured-best configuration is used on one call site out of
fifteen and the rest were never revisited.

**Fix.** Name the sets explicitly per screen type (`"result"`, `"menu"`,
`"ban"`) even if several alias to the same regions, so each call site declares
what it waits on. Then use `settle_stats_summary()` — already wired at
`orchestrator.py:3309` — to check truncation rates per set after one live
session, and set `max_wait` from that instead of from the ~1 Hz proxy log.
**Effort: 2 hours** for the naming; the tuning is one live session of data.

---

## 13. MED — Screenshot logger: 4.6 GB per run, and old run folders are never pruned `[MEASURED]`

**`orchestrator.py:787-796`** and **`orchestrator.py:799-814`**.

Measured against the existing corpus:

```
1937 frames, 449.3 MB, mean 227 KB/frame
20000-frame cap => 4.6 GB per run folder
free space: 466 Gi available
```

`SCREENSHOT_LOG_MAX_FILES = 20000` is annotated "~30 min at 10Hz". At the
measured 227 KB/frame that is **4.6 GB**, not the ~4 GB the `I9` comment
estimates, and the real capture floor is ~0.47 s/frame (documented at
`orchestrator.py:1196-1198`), so 20,000 frames is closer to **2.6 hours** than
30 minutes — the cap will rarely bind on a normal session and session length is
the real bound.

Both production entry points pass `log_screenshots=True`
(`run_tonight.py:95`, `run_testing.py:105`).

The compounding problem is scope: `_prune_screenshot_log()` prunes **only the
current run's folder** (`orchestrator.py:800-804`), deliberately, so the
calibration corpus survives. Correct — but it means *nothing* ever prunes
completed run folders. `run_testing.py:20-22` plans ~7 re-copies; at ~1-4 GB per
session that is **10-30 GB accumulating with no ceiling and no warning**.

Disk-full behaviour itself is handled well: `orchestrator.py:834-842` catches and
throttles on a failure counter (`N4`). The gap is that nothing bounds total
growth.

**Fix.** Add a corpus-wide cap that prunes whole `run_*/` folders oldest-first
while never touching the flat top-level calibration frames — the existing
foldering (`orchestrator.py:851-856`) already makes that distinction trivial.
**Effort: 1-2 hours.**

---

## 14. MED (docs) — `LESSONS.md` §7 credits a code path that can no longer run `[MEASURED]`

**`LESSONS.md:174-200`** and **`LOCAL_VISION_EXPERIMENTS.md:1040-1043`**.

Both attribute the ban-screen speed fix to the tactics-boundary early stop:

> The fix costs nothing: tactics cards have no player-name banner, so
> `ocr_ban_card_name` already returns `None` for every position there […] so the
> scan stops before spending any vision call.

Two problems, both measured:

1. **That stop never executes.** Traced under the production default — the block
   at `orchestrator.py:2252-2258` is in the never-executed set. `trust_roster`'s
   simpler `if not roster_hits: break` (`orchestrator.py:2271-2274`) fires first,
   and the arithmetic makes it unreachable anyway (see §10).
2. **"Stops before spending any vision call" was never true**, even with
   `trust_roster=False`. The comment at `orchestrator.py:2249-2251` deliberately
   allows "one batch of slack past the roster", so the first unrecognised batch
   still falls through to the vision branch — up to 2 vision calls plus a
   per-row retry — before the stop can fire on the *second*.

The consequence is concrete: someone optimising the ban screen reads §7, looks
at the tactics stop, and misses that the actual remaining cost is
`detect_ban_grid_locked` at 7.19 s × 5 iterations = **~36 s** (§3).

**Fix.** Amend both sections: the ban screen is now fast because of
`TRUST_ROSTER_ONLY`, not the tactics stop; the tactics stop is dormant; the
remaining cost is the lock detector. **Effort: 30 minutes.**

---

## 15. MED (docs) — `LOCAL_VS_API.md` describes the ban path as live `[MEASURED]`

**`LOCAL_VS_API.md:19`** and **`LOCAL_VS_API.md:40`**.

> **Ban-card identity** | `ocr_ban_card_name()` […] Local-first: […] the caller
> then falls through to `read_ban_row_cards()`. **This is the only genuine
> local-first-with-API-fallback path in the project.**

> **Ban-screen card reads** | `read_ban_row_cards()` | Only fires for grid
> positions `ocr_ban_card_name()` refused […]

Neither function can run (§10). The document's single most confident
architectural claim — "the only genuine local-first-with-API-fallback path" —
describes code that `TRUST_ROSTER_ONLY` switched off. `LOCAL_VS_API.md:165` even
says `TRUST_ROSTER_ONLY = True` "removes vision from the ban screen entirely",
so the file contradicts itself 146 lines apart.

**Fix.** Mark both rows dormant and cross-reference L165. **Effort: 20 minutes.**

---

## 16. MED (docs-in-source) — The tesseract-era "unreadable badges" claim survives in the code `[MEASURED]`

**`orchestrator.py:603-610`** (`ocr_ban_card_name` docstring):

> live testing 2026-08-24 found the power circle's digit font **genuinely
> unreadable by tesseract** regardless of crop precision or polarity (tested
> exhaustively, both light-on-dark and dark-on-light, 7 thresholds x 5 psm
> modes, zero correct reads) — **a font-recognition limitation, not a framing
> problem.**

`LOCAL_VISION_EXPERIMENTS.md:995-1047` retracts this in detail: PaddleOCR reads
the same badges at ~1.00 confidence on all 7 unlocked cards of a real ban frame,
and the doc closes with "**Do not repeat the tesseract-era claim that the badges
are unreadable — they are not.**"

The correction landed in the markdown and never made it back to the source. The
docstring's "font-recognition limitation" framing is the misleading part: it
tells a future reader the door is closed when the real blockers are decoy digits
in card art, digit-to-badge assignment, and rotation ambiguity — all solved
problems in `hand_digit_reader.py`.

Compounding it: this docstring sits on a function that cannot run (§10), so it
is stale advice inside dead code — maximum chance of being believed, zero chance
of being contradicted by behaviour.

**Fix.** Replace the claim with a pointer to `LOCAL_VISION_EXPERIMENTS.md:995`.
**Effort: 15 minutes.**

---

## 17. LOW — Phantom `"reveal"` settle region set `[MEASURED]`

**`orchestrator.py:1299`** advertises three sets; **`orchestrator.py:1157-1161`**
defines two:

```
 keys: ['turn', 'default']
 docstring advertises: ['turn', 'reveal', 'default']
 regions="reveal" resolves to: ('legacy_roi', 'hand')
```

`SETTLE_REGION_SETS.get(regions, ...)` at `orchestrator.py:1320` silently falls
back, so a caller passing `"reveal"` gets the default and no error. Given
`REVEAL_CENTER_REGION` exists and the reveal path is explicitly documented as
needing a *different* trigger from settling (`orchestrator.py:1533-1548`), this
is a trap set for exactly the person who reads that section and tries to use it.

**Fix.** Either add the set or drop it from the docstring, and raise `KeyError`
on an unknown name instead of falling back. **Effort: 20 minutes.**

---

## 18. LOW — `_grab_animation_roi` has zero callers `[MEASURED]`

**`orchestrator.py:1286-1288`.** Comment says "kept for anything still calling
it directly"; `grep` across all `.py` and `.md` returns only the definition.
Genuinely dead, unlike §10 (no rollback value).
**Fix: delete. Effort: 5 minutes.**

---

## 19. LOW (docs) — `TEST_SUITE_AUDIT.md` runtime is 5.6× low `[MEASURED]`

**`TEST_SUITE_AUDIT.md:4`** and **`:525`**: "81s wall, all green" / "81 s for 11
files, dominated by the tesseract passes in `test_ocr_ban_card.py`".

Measured today: **457 s for 16 files**. And `test_ocr_ban_card.py` is now 5.0 s —
0.5% of the total, not the dominant cost. The real dominators are
`test_no_side_effects.py` (183 s) and `test_run_state_machine.py` (126 s), which
did not exist at the time.

Minor on its own, but it is the number someone consults before deciding whether
the suite is cheap enough to run in a loop — and `preflight.py` runs it on every
session start.
**Fix: update both figures. Effort: 10 minutes.**

---

## 20. LOW — `report_misfire()` mutations survive `run()` `[REASONED]`

**`input_controller.py:104-121`.** `ACTION_DELAY`, `FOCUS_TTL`,
`_backoff_applied` and `_misfires_seen` are module globals mutated in place and
never reset. `run()` clears `_OBSERVATIONS` and `_SETTLE_STATS`
(`orchestrator.py:2650-2651`) for exactly this reason but does not reset input
pacing. A second `run()` in one process inherits a degraded `ACTION_DELAY` and
permanently disabled focus caching.

Both entry points call `run()` once, so this is latent. It becomes real the
moment anything retries `run()` in-process.
**Fix.** Add a `reset_pacing()` alongside the existing `_OBSERVATIONS.clear()`.
**Effort: 30 minutes.**

---

## 21. LOW — `run_testing.py --reset` writes `progress_testing.json` non-atomically `[REASONED]`

**`run_testing.py:60-61`** uses a plain `open(...,"w") + json.dump`.
`orchestrator._atomic_write_json` exists precisely because
`orchestrator.py:99-103` argues a truncated `progress.json` "loses the win/loss
record", and `load_progress` (`orchestrator.py:87-93`) now *refuses to start* on
an unreadable file. So an interrupted `--reset` produces a file the orchestrator
will hard-refuse.

The window is tiny and the file is a throwaway save's bookkeeping.
**Fix.** Import and use `_atomic_write_json`. **Effort: 15 minutes.**

---

## 22. The state-machine question: what I would actually do

The brief asks whether the five-guard pile on `run()`'s loop is now the risk, and
what an explicit state machine would cost. My answer is *partly* — and a single
FSM is the wrong shape.

The five guards are not one mechanism. They are **two**, tangled together:

**(a) Match lifecycle** — `match_in_progress` (L2939, persisted) and
`bans_done_this_match` (L2643, not persisted). These genuinely are a state
machine: `IDLE → PAID → BANNED → PLAYING → SCORED`. Encoding it as two booleans
with *different persistence lifetimes* is what produced §4 and §5 — both are
real, both are reachable via the documented recovery path, and both were
invisible to a suite that covers each flag separately.

**(b) Liveness bounds** — `acted_screen` (L2607), `stuck_count` (L2598),
`polls_without_progress` (L2638), plus `motion_wait_started` (L2610) and
`MAX_CONTINUOUS_MOTION_WAIT` (L1515). Four overlapping answers to "is this going
anywhere?", each added after a specific incident (C1/C2/C3, QA1-F3, N25).

**Recommendation: extract (a), leave (b) as counters, add the missing one.**

* **Extract (a) into one persisted `match_phase` enum.** This fixes §4 and §5
  *by construction* — one field, one lifetime, one thing to inspect and reset.
  It also gives `preflight.py` something meaningful to check, and gives the
  stall messages something specific to name.
  **Cost: ~1 day.** Lower than it looks: `test_run_state_machine.py` already
  pins C1/C2/C3/C5/N3/N25, the resume path, and the spend cap across ~30 `run()`
  invocations, so the refactor is verifiable rather than faith-based. That test
  file is the reason this is affordable.

* **Do not fold (b) into the FSM.** Those counters are load-bearing and each one
  documents a real incident; collapsing them risks re-opening bugs whose
  reproductions are expensive (they needed live matches and real money). They
  are ugly but they are *earned*.

* **Add the guard the pile is missing: "the screen never changed at all."**
  Every existing bound catches motion-without-progress. None catches
  stillness-without-progress, which is §1 — the most consequential hole found,
  and the one a bigger FSM would *not* have caught, because the loop is
  transitioning correctly through a state that happens to be a lie.

### Other places guards piled up rather than being unified

* **`read_full_ban_collection` (`orchestrator.py:2143-2399`) has six loop-exit
  conditions** — `max_presses`, `new_count == 0 and not expected_positions`,
  `consecutive_mismatches >= 2`, the tactics-boundary stop, "no roster
  coverage", and the `len >= 3` cache gate. **Three of the six are unreachable**
  (§10). A 257-line function with six ways out, half of them dead, is the same
  accretion pattern as `run()` at one-third the scale.
* **Screen readiness has five mechanisms**: `screen_is_moving`,
  `wait_for_screen_to_settle`, `wait_for_reveal_cards`, `input_prompt_visible`,
  and `MAX_CONTINUOUS_MOTION_WAIT` — across two region sets and seven
  thresholds. Each is individually well-justified and measured; there is no
  single place that says which to use when. §12 and §17 are both consequences.
* **"Am I a test" has five overlapping signals**: `BASEBALL_TEST_RUN`, `argv`
  sniffing (`orchestrator.py:191-201`), `BASEBALL_MATCH_LOG`,
  `BASEBALL_DIAGNOSTICS_DIR`, and the `_synthetic` stamp — plus
  `test_no_side_effects.py` guarding the class. This one I would **leave alone**:
  `orchestrator.py:169-190` argues explicitly that the mechanisms must fail
  independently, and the history (30 synthetic rows in real data) supports it.
  Redundancy here is the design, not the debt.
* **Input pacing spreads across seven `input_controller` globals** mutated from
  two modules (§20).

---

## Suggested order of work

| Order | Items | Why first |
|---|---|---|
| 1 | §3 (ban-grid filter), §11 (test patch line) | Pure wins, hours not days, no behaviour change, both verifiable against existing tests. §3 also removes 36 s of blind time from every session. |
| 2 | §2 (unify capture guard), §1 (reveal-failure counter) | The two ways an overnight run currently burns money or API calls without stopping. |
| 3 | §5 (preflight + message), §8 (persist `spent`) | Cheap, and they protect someone else's money on the documented recovery path. |
| 4 | §6, §7, §14, §15, §16 (docs + duplicated truth) | A day's work total; removes the misleading claims a future reader is most likely to act on. |
| 5 | §22 (`match_phase` extraction), §4 | The structural fix. Do it after the docs so the refactor lands against accurate notes. |
| 6 | §9, §12, §13, §17-§21 | Real but bounded. |

---

## Verification

* **No source file was modified by this audit.** The only file created is this
  one. Verified by SHA manifest taken before and after; see the closing note on
  concurrent edits by another agent to `orchestrator.py`,
  `test_roster_matching.py`, `QA_VISION.md` and `_lockdist.py`, which are not
  mine.
* **No game input, no capture of a live session, no writes to** `match_log.jsonl`,
  `progress*.json`, `known_ban_roster_learned.json`, `diagnostics/`,
  `screenshot_log/` or `state_backups/`. `BASEBALL_MATCH_LOG` and
  `BASEBALL_DIAGNOSTICS_DIR` were redirected to a scratch directory for every
  command that could write.
* `./run_tests.sh` was never invoked; test files were timed individually in an
  isolated copy of the tree.
