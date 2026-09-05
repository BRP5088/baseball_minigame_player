# QA Round 1 — adversarial review of the 2026-08-25 evening changes

Method: every claim below was reproduced against a **copy** of the tree in a
scratch sandbox (`orchestrator.py`, `input_controller.py`, tests, fixtures and
photo corpora rsynced out). Nothing here ran the game, sent a keystroke, or
wrote to real project data. Baseline suite in the sandbox: green (14/14 once
the photo dirs were copied).

Each finding is tagged:

* **[MUT]** — proved by mutating the code and observing what the suite did.
* **[EXEC]** — proved by executing the real code path against a faked screen
  sequence / faked capture (no mutation; the code is as shipped).
* **[REASONED]** — argued from the source only, not executed. Called out as
  such every time.

Probe scripts live in the sandbox, not in the project:
`…/scratchpad/sandbox/zz_probe_{c5,ban,guards,diag,bound,bound2}.py`,
mutation driver `…/scratchpad/mutate.py` + `m1..m5.py`.

---

## Summary of the ranked findings

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| 1 | HIGH | C5 stops the *accounting*, not the *keystroke* — up to 15 `start_match` presses while the tracker debits $50 once | EXEC |
| 2 | HIGH | C5 guards only half the match cycle; `result → misread prompt → result` double-scores **and** debits $50 | EXEC |
| 3 | HIGH | No global progress bound: two alternating screens loop forever with keypresses, no stall, no diagnostics | EXEC |
| 4 | HIGH | The C2 regression test now passes with the C2 guard deleted — C5 produces the same observable | MUT |
| 5 | HIGH | `TRUST_ROSTER_ONLY` and the tactics early-stop have **zero** behavioural coverage; flag flip survives the whole suite | MUT |
| 6 | MED-HIGH | One bad capture poisons `_cached_ban_collection` for the whole process; the 15 retries are no-ops | EXEC |
| 7 | MED | `_running_under_test()` still keys on the redirect → a real run with `BASEBALL_MATCH_LOG` stamps genuine rows `_synthetic` | EXEC |
| 8 | MED | 3 of 8 stall exits write no diagnostics bundle and print the clean-stop message | EXEC |
| 9 | MED | `screen_is_moving()` is the only unguarded call in the loop; one raise kills the session with no bundle | EXEC |
| 10 | MED | `select_bans_and_start_full()` unwinds rows but never columns; match 2+ bans from a shifted origin | EXEC (code) / REASONED (game) |
| 11 | MED | All three ban-safety checks in `run()` survive deletion | MUT |
| 12 | LOW-MED | Module state leaks across `run()` calls: ban cache, `ACTION_DELAY`, `FOCUS_TTL`, `_misfires_seen` | EXEC |
| 13 | LOW | Atomic-write test still does not test atomicity (known, unfixed) | MUT |
| 14 | LOW | `test_no_side_effects.py` inherits the parent env and can mask the exact failure it guards | REASONED |
| 15 | LOW | Focus-cache failure is invisible: `check=False`, result ignored, then cached for the TTL | REASONED |
| 16 | LOW | `read_balance_from_pause_menu()` returns unvalidated model output straight into `balance` | REASONED |

---

## 1. HIGH — C5 blocks the debit but not the keypress: up to 15 untracked `start_match` presses  [EXEC]

`orchestrator.py:2695-2702` (C5) and `orchestrator.py:2668-2678` (C2).

C5 correctly refuses the second debit — and then sets
`acted_screen = "match_start_prompt"` and continues. On the **next** poll the
C2 branch matches first, and C2's recovery path does
`press("start_match")` — 14 more times, until `MAX_STUCK_ATTEMPTS`.

C5's whole premise is "this prompt is probably not real, do not act on it".
One iteration later the loop acts on it anyway, 15 times, and never reconciles
that with `balance` or `spent`.

Failure scenario (executed, `zz_probe_c5.py` PROBE 1):

```
screens: match_start_prompt, turn, other, other, match_start_prompt × N
         (a match whose result overlay was never classified as "result")

tracked balance after : $450       (one $50 debit)
start_match presses SENT to the game : 15
in-game cost if each landed          : $750
```

`match_in_progress` is only cleared at `:2646`, inside the result branch. Any
match that ends without a scoreable result screen leaves the flag stuck True,
and the *next genuine* prompt takes the path above: no tracked debit, 15 real
presses, `max_spend` bypassed entirely because nothing increments `spent`.

Even in the benign case (the prompt really is a ROUND overlay), 15 stray
`start_match` presses — which is `\` , the same key as `confirm_discard` — land
on a live match screen.

**Suggested shape of a fix:** the C2 recovery press must be conditional on
`not match_in_progress`. If a paid match is running, a repeat prompt should
wait, not press.

---

## 2. HIGH — C5 covers only the debit→result half of the cycle; the result→debit half double-scores  [EXEC]

`orchestrator.py:2585` (guard clearing) and `:2588-2661` (result branch).

`match_in_progress` is True from debit until a result is scored. The window
from a scored result until the next genuine prompt is unprotected, and the
result branch still relies on the plain `acted_screen` rule — the exact
mechanism the C5 write-up says "cannot see a repeat with another screen in
between".

Executed (`zz_probe_guards.py` section B), one result overlay, one intervening
misread:

```
result -> discard_prompt      -> result   wins=2  balance=$500   <-- same match scored twice
result -> turn                -> result   wins=2  balance=$500
result -> ban_screen          -> result   wins=2  balance=$500
result -> match_start_prompt  -> result   wins=2  balance=$450   <-- + a $50 debit for nothing
result -> other               -> result   wins=1  balance=$500   (N2 holds)
```

The last-but-one line is the live-observed failure with the screens swapped:
a transition overlay misclassified as `match_start_prompt` is precisely what
happened at 17:01:46 on 2026-08-25. Between two polls of a result overlay that
has not dismissed, it produces a fabricated win *and* a $50 debit.

`discard_prompt` is the easiest bypass, because it is the least-validated
recognized screen. Confirmed against `validate_game_state()` directly
(`zz_probe_guards.py` section A):

```
ACCEPTED : {"screen": "discard_prompt", "phase": "batting"}     <- no hand, no scores
ACCEPTED : {"screen": "result"}                                  <- nothing at all
ACCEPTED : {"screen": "ban_screen"} / {"screen": "match_start_prompt"}
rejected : {"screen": "turn", ... "hand": []}                    <- the only one with a real bar
```

So a single frame that the model calls `discard_prompt` clears every guard and
sends a `confirm_play`. On the ban screen `confirm_play` is the key that
commits the ban selection.

Same hole in C3 (`zz_probe_guards.py` section C):

```
ban -> discard_prompt -> ban    ban submissions = 2   <-- un-bans exactly what it just banned
ban -> turn           -> ban    ban submissions = 2
ban -> other          -> ban    ban submissions = 1
```

**Note the test suite pins the permissive behaviour**:
`test_run_state_machine.py:214-217` asserts `result → turn → result` scores
*two* wins. In the real flow a second match cannot occur without an
intervening `match_start_prompt` (the loop pays for every match), so that
assertion encodes "a match can be scored without ever being paid for". Gating
the result branch on `match_in_progress` — the symmetric fix to C5 — is a
one-line change, but it contradicts that existing test, which is why it needs
a decision rather than a patch.

---

## 3. HIGH — no global progress bound: two alternating screens loop forever  [EXEC]

`orchestrator.py:2700` (`stuck_count = 0` in the C5 branch), plus `:2797`
(ban) and `:2816` (discard).

`stuck_count` only counts *consecutive repeats of one screen*. Every branch
resets it on success, and C5 now resets it on a poll where **no action is
taken at all**. Two screens that each clear the other's guard therefore spin
without any bound.

Executed (`zz_probe_bound.py`, `zz_probe_bound2.py`), current unmutated code:

```
match_start_prompt <-> ban_screen      3000/3000 screens consumed, 1500 ban submissions  UNBOUNDED
match_start_prompt <-> discard_prompt  2000/2000 screens consumed, 1001 keypresses       UNBOUNDED
match_start_prompt <-> other              16/2000 screens consumed                       bounded
```

1500 ban submissions means the chosen cards are toggled on and off 1500 times.
No stall is declared, no diagnostics bundle is written, nothing prints except
the per-iteration lines.

Plausibility is not exotic: the ban screen carries the same on-screen "PLAY"
prompt as the match-start prompt (documented at `orchestrator.py:1398-1400`),
so `ban_screen`↔`match_start_prompt` is a *likely* confusion pair, and the
2026-08-25 run already demonstrated one member of it being misread.

Before today, this alternation was bounded by money (each prompt debited $50
until the cap stopped it). C5 removed the debit and left nothing in its place,
so a money bug became a silent hang.

**Suggested shape of a fix:** a monotonic "polls since the last state change
that actually advanced the match" counter, checked once per iteration,
independent of which screen is showing.

---

## 4. HIGH — the C2 test now passes with the C2 guard deleted  [MUT]

Mutation `M26`: replace `if acted_screen == "match_start_prompt":`
(`orchestrator.py:2668`) with `if False:`.

Result: **`test_run_state_machine.py` PASSES.**

The test at `test_run_state_machine.py:241-244` feeds
`["match_start_prompt"] * 4` and asserts the balance fell by exactly $50 —
which is now satisfied by C5 rather than by C2, because the first poll sets
`match_in_progress = True`. This is LESSONS §1's pattern exactly ("something
else produces the same observable"), created today, in the money guard.

It is not a harmless duplicate. With C2 removed, a genuinely stuck prompt falls
into the C5 branch every poll, which sets `stuck_count = 0` and never presses
anything — an infinite loop (see finding 3). The suite cannot tell the
difference between "guarded" and "hangs forever" here.

For contrast, these money mutations are genuinely caught (suite went red):
`M1` C5 off, `M2` flag never cleared, `M3` flag never set, `M27` `max_spend`
ignored, `M28` balance floor ignored, `M12` "other" re-arms the guard.

---

## 5. HIGH — `TRUST_ROSTER_ONLY` and the tactics early-stop have zero behavioural coverage  [MUT]

Three separate mutations, each run against
`test_known_ban_roster.py, test_run_state_machine.py, test_ocr_ban_card.py,
test_ban_grid_locked.py, test_roster_matching.py, test_state_io.py,
test_validate_game_state.py, test_settle_regions.py, test_image_pipeline.py`
(the remaining files never import the ban scan):

| Mutation | Result |
|---|---|
| `M4` `TRUST_ROSTER_ONLY = True → False` (the documented rollback flag) | **all 9 PASS** |
| `M5` delete the trust-roster fast path (`orchestrator.py:2118`) | **all 9 PASS** |
| `M6` delete the early tactics-boundary stop (`orchestrator.py:2111-2116`) | **all 9 PASS** |

`read_full_ban_collection()` — the function that decides which physical cards
get toggled — has **no test that executes it**. `test_run_state_machine.py:169`
replaces it with a lambda; `test_known_ban_roster.py:119-146` only asserts
properties of the roster *data* (entry count, no `locked` attribute), which is
true whatever the flag is set to. `TEST_SUITE_AUDIT.md §3.3` called this out
before today's change; today's change made the untested path the *only* path.

The one mutation this file does catch is real: `M7` (freezing
`_max_roster_row()` at import) turns `test_known_ban_roster.py:104` red, with
the right message. Worth noting though that the property it protects —
self-extension — cannot occur in production any more: with `trust_roster`
True, `_learn_roster_entry()` is never reached from the scan, so the roster
never extends and the boundary never moves.

**Inverted coverage.** The suite's two most expensive tests
(`test_ocr_ban_card.py`, `test_roster_matching.py`, ~2 of the 3.5 min runtime)
now guard `ocr_ban_card_name()` / `match_roster_name()`, which
`TRUST_ROSTER_ONLY = True` has switched off in production, while the code that
actually runs has none. That is not an argument for deleting them — they are
the rollback path (see finding on dead code below) — but the suite currently
reports health for the disabled branch.

What the scan does do correctly, verified by executing it against a faked
capture (`zz_probe_ban.py` probes A, C, D):

* full scan returns all 33 roster cards, rows 0-6, no position missed;
* `move_down` 8 / `move_up` 8 — the unwind is exactly balanced, no off-by-one;
* a roster gap in the middle of the collection (row 2 removed) does **not**
  trigger the early stop — the scan carries on and returns rows 0,1,3-6.

So the scroll arithmetic and `top_row = max(0, presses_so_far - 1)` are right.
The problems are elsewhere (findings 6 and 10).

---

## 6. MED-HIGH — one bad capture poisons the ban cache for the whole process  [EXEC]

`orchestrator.py:2242-2243` caches unconditionally; `:2044` returns the cache
before capturing anything.

If the first captured frame is mid-animation, `detect_ban_grid_locked()`'s
contrast test reads every cell as locked, `expected_positions` is empty, and
the scan exits at `:2217` returning `[]`. That `[]` is then cached.

Executed (`zz_probe_ban.py` PROBE B):

```
scan #1 (2 bad frames)          -> 0 cards, cache = []
scan #2 (screen now perfect)    -> 0 cards   STILL EMPTY (cache poisoned)
                                   0 captures, 0 OCR, 0 vision calls
```

Downstream (`zz_probe_c5.py` PROBE 3), that is a guaranteed dead end:

```
ban_screen seen 15 times: 15 scan attempts, 0 ban submissions,
stop_reason = ban_screen_stuck — after the $50 was already debited
```

The `except → stuck_count += 1 → retry` block at `orchestrator.py:2787-2795`
looks like a recovery path and cannot recover, because every retry is served
from the poisoned cache. A single bad frame costs the match fee and ends the
session; restarting the process is the only cure.

Milder variant, same cause: if only the *first* frame is bad, row 0 is skipped
entirely and a 28-card collection is cached for the rest of the session —
`choose_bans()` then picks from an incomplete pool with nothing printed.

**Suggested shape of a fix:** only cache a result that looks complete (e.g.
`len(full_collection) >= 3`, or "reached a stop condition other than an empty
first batch"), and make the caller's retry force `use_cache=False`.

---

## 7. MED — a real run that redirects its match log gets its genuine rows stamped `_synthetic`  [EXEC]

`orchestrator.py:170-174`.

```python
if os.environ.get("BASEBALL_TEST_RUN") or os.environ.get("BASEBALL_MATCH_LOG"):
    return True
```

The comment block above it (`:160-169`) says the stamp is "KEYED ON 'AM I A
TEST', NOT ON 'IS THE LOG REDIRECTED'", and LESSONS §2 records that keying on
the redirect was the bug. The redirect check is still there, ORed in.

Executed, simulating a real session that keeps tonight's data in its own file
(no `BASEBALL_TEST_RUN`, `sys.argv[0] = run_tonight.py`):

```
_SYNTHETIC_LOG = True
row written: {'our_card_name': 'Real Card', 'our_power': 7,
              '_synthetic': True, '_source': 'test-suite',
              '_written': '2026-08-25T20:18:44'}
survives the documented `grep -v '"_synthetic": true'` cleanup?  False
```

Every genuine turn would be labelled test data, sourced to "test-suite", and
deleted by the documented recovery one-liner. This is the same shape as the
original bug, mirrored: the first version stamped nothing in the case that
mattered; this one stamps everything in a case that must not be stamped.

Note `test_state_io.py:178-186` cannot catch it — it strips *both* variables
before checking that a real run is unstamped, so the redirect-only case is
never exercised. (`M17` stamp removal and `M18` "key on redirect only" are both
caught, so the rest of that test is genuine.)

Low likelihood while nothing in the repo sets the variable — but the QA
instructions for this very review prescribe setting it, which is exactly the
kind of operator action that produces the failure.

---

## 8. MED — three stall exits write no diagnostics bundle and look like a clean stop  [EXEC]

`orchestrator.py:2603-2604`, `:2732-2733`, `:2991-2993` all `break` without
setting `stop_reason`, so the `finally` at `:3018` skips `dump_diagnostics()`.

Executed (`zz_probe_diag.py`), every stall path driven to its exit:

```
result overlay never dismisses (C1)     bundle: NO
ban screen never advances (C3)          bundle: NO
discard/redraw never lands (N25)        bundle: NO
unrecognized screen                     bundle: YES
discard prompt never clears (N3)        bundle: YES
turn action keeps raising               bundle: YES
match-start prompt never dismisses (C2) bundle: YES
out of money (clean stop)               bundle: NO   (correct)
```

The three silent ones are the guard-suppressed stalls — the states where the
loop knows it is stuck in a specific guard, i.e. where the observation trail is
most informative. All three then print the same closing line as a healthy
early stop ("Progress is saved — just rerun the script to pick back up"), so
from the terminal a stall is indistinguishable from running out of money.

`M24` (deleting the diagnostics call) is caught by the suite, so the mechanism
is genuine — it just is not wired to 3 of the 8 exits.

---

## 9. MED — `screen_is_moving()` is unguarded; one raise ends the session with no bundle  [EXEC]

`orchestrator.py:2496`. Every other per-iteration call in the loop is wrapped:
`read_game_state` (`:2511`), `play_one_turn` (`:2842`), the matchup logging
(`:2541`, `:2880`), even the prompt audit has a dedicated `_safe_prompt_check()`
(`:1416`). The motion gate — added today, and the *first* thing every iteration
does — has nothing.

`_fast_grab()` (`:1192`) calls `_MSS.grab()`, whose failure modes are exactly
the ones this machine has (display disconnect/reconfiguration, permission
revoked, mss handle invalidated in a long session).

Executed (`zz_probe_guards.py` section D), with `screen_is_moving` raising
`OSError`:

```
UNCAUGHT: OSError: mss: display disconnected
-> the run dies mid-match; stop_reason is None so NO diagnostics bundle is written
```

The `finally` still runs (logger stopped, settle summary printed), then the
traceback propagates out of `run()` into `run_tonight.py`. Mid-match, after the
fee is paid, with no bundle. Wrapping it to return `False` on error costs one
`try` and degrades to the old always-read behaviour.

---

## 10. MED — `select_bans_and_start_full()` restores the row but never the column  [EXEC on code / REASONED on the game]

`input_controller.py:307-319`.

```python
current_row, current_col = 0, 0
...
for _ in range(current_row):   # back to the top before confirming
    press("move_up")
```

Rows are unwound, columns are not. Executed with a recorded `press`
(`zz_probe_ban.py` PROBE E), banning {(0,0), (1,3), (3,2)}:

```
[select, D, R,R,R, select, D,D, L, select, U,U,U, confirm_play, confirm_play]
net vertical   : 0
net horizontal : +2      <-- the cursor is left two columns right of origin
```

The docstring says "Assumes the caller starts at (0, 0)". For match 1 that
holds (the scan's `finally` unwinds the rows it pressed, and it never moves
horizontally). For match 2 onward it holds only if the game resets the ban
cursor between ban screens — which is **the opposite of the documented
behaviour of the hand cursor**: `input_controller.py:220-226` records that the
game does *not* reset the cursor between turns, which is why
`reset_hand_cursor()` exists. There is no `reset_ban_cursor()`.

If the ban cursor persists, every ban from match 2 on is computed from
`current_col = 0` while the cursor sits at column 2 — banning cards that were
never chosen, with nothing to detect it: the collection is served from cache so
the choice is identical every match, and the "BANNED CARDS n/3" counter is
never read back.

I could not settle this offline, and the live evidence cannot either: the
2026-08-25 session completed exactly **one** ban screen (LESSONS §5). This is
the highest-value thing to check on the next live run — one frame of the second
match's ban screen answers it. The cheap defensive fix is to mirror
`reset_hand_cursor()`: press `move_left` 4× (and `move_up` to the roster
height) before the first target, instead of assuming the origin.

Related, same function, REASONED: the row unwind also assumes toggling a ban
does not move the cursor or reflow the grid.

---

## 11. MED — every ban-safety check in `run()` survives deletion  [MUT]

All against `test_run_state_machine.py`:

| Mutation | Result |
|---|---|
| `M13` remove the distinct-`id()` check (`orchestrator.py:2775`, the N15 duplicate-object guard) | **PASS** |
| `M14` remove the 3-distinct-positions check (`:2780`) | **PASS** |
| `M15` remove the exactly-3-bans check (`:2750`) | **PASS** |

The harness always supplies a clean 5-card grid, so none of these guards ever
fires in any test. Each exists because of a real incident (4 physical toggles
for 3 intended bans; a mis-resolved read putting one `PlayerCard` object at two
positions; `choose_bans()` silently returning fewer than 3). The comments at
`:2767-2779` are the only thing keeping them alive.

Three grids would pin all of them: one with a duplicated `PlayerCard` object,
one where a chosen card is absent from the grid, one with a 2-card collection.
None needs a screenshot.

For contrast, the equivalent guard one layer down *is* now genuinely tested:
`M25` (removing `cutoff=0.85, allow_surname_fallback=False` from
`ocr_ban_card_name`, `orchestrator.py:581`) turns `test_ocr_ban_card.py` red
with three named mis-resolutions. LESSONS §1 item 1 is fixed and stays fixed.

---

## 12. LOW-MED — module state that survives `run()` inside one process  [EXEC]

`run()` deliberately clears `_OBSERVATIONS` and `_SETTLE_STATS` at `:2471-2472`
"so a second `run()` in the same process would otherwise dump the PREVIOUS
run's trail". Four other module globals were not given the same treatment
(`zz_probe_c5.py` PROBES 2 and 4):

* `orchestrator._cached_ban_collection` (`:1972`) — survives `run()`. Its own
  comment says the collection "belongs to whichever save file is currently
  playing… persisting it risks serving stale or wrong-player data". Two
  `run()` calls with different `progress_file`s in one process do exactly
  that; the second reused the first save's collection.
* `input_controller.ACTION_DELAY`, `FOCUS_TTL`, `_misfires_seen`,
  `_backoff_applied` — `report_misfire()` prints "for the rest of the run" but
  the effect is process-lifetime. Measured: after two misfires, a fresh
  completed `run()` still starts at `ACTION_DELAY=0.45, FOCUS_TTL=0.0,
  _misfires_seen=2` — so the *next* run's first misfire trips the backoff
  immediately, and its focus cache is off from the first keystroke.

Today's entry points call `run()` once per process, so this is latent rather
than live. It is on the list because it is the documented failure class and
because `_cached_ban_collection` is the same object as finding 6.

---

## 13. LOW — the atomic-write test still does not test atomicity  [MUT]

`M16`: replace `_atomic_write_json`'s temp+fsync+`os.replace` body
(`orchestrator.py:99-104`) with a plain truncating `open(path, "w")`.
`test_state_io.py` **PASSES**, `test_run_state_machine.py` **PASSES**.

The assertion (`test_state_io.py:36-38`) is "no `.tmp` file was left behind",
which is also true when there is no temp file at all. Already documented in
`TEST_SUITE_AUDIT.md §1.5`; re-measured here and still unfixed. A test that
kills the process mid-write is awkward, but asserting the file is complete
after a simulated failed write (or simply that `os.replace` is used) is not.

---

## 14. LOW — `test_no_side_effects.py` can be defeated by the shell it is run from  [REASONED]

`test_no_side_effects.py:74-81` builds the child env with `dict(os.environ)`
and comments that it deliberately does *not* set `BASEBALL_MATCH_LOG` /
`BASEBALL_DIAGNOSTICS_DIR`, "since setting the overrides from this side would
mask a test that forgot to". Inheriting them from the parent has the same
effect: run `./run_tests.sh` from a shell that exports either variable (the
documented way to run things safely, including in this review's own brief) and
a test that forgot to redirect will pass silently.

Two lines fix it: pop both keys from the child env.

Second, smaller gap in the same file: `TRACKED_DIRS` compares
`sorted(os.listdir(p))` — names only. A test that *modifies* an existing file
inside `diagnostics/` or `screenshot_log/` (rather than adding one) is not
detected. Tracked files are hashed; tracked directories are not.

---

## 15. LOW — a failed focus call is invisible and then cached  [REASONED]

`input_controller.py:178-184`. `subprocess.run(..., check=False)`, return code
ignored, `_last_focus_at` stamped regardless. If Chiaki is not running, is
named differently, or System Events is denied, the call fails silently and the
next `FOCUS_TTL` seconds of keystrokes are sent with no focus assertion at all
— into whatever window is frontmost, plausibly the terminal running the script.

Before today every press retried the focus call; now a failure is trusted for
1.5s. `focus_cache_summary()` counts calls, not successes, so the end-of-run
report shows a healthy cache either way. Checking `returncode` and printing
once on failure costs nothing.

---

## 16. LOW — the balance comes straight out of the vision model with no validation  [REASONED]

`orchestrator.py:2279-2286`: `money = result.get("money")`, checked only for
`None`. The value goes into `balance`, which is compared (`balance < 50`),
decremented, and persisted to `progress.json`. A string (`"246"`, `"1,246"`)
raises `TypeError` at the first comparison — uncaught, outside any handler, so
the run dies with a traceback and no bundle; a float silently persists a float
balance. One `isinstance(money, int)` check at the boundary.

---

## Where I looked and found nothing

Stated explicitly so the absences are informative:

* **Double-debiting through the tracked accounting.** I could not construct any
  screen sequence where `balance`/`spent` are decremented twice for one match
  while C5 is in place. `M1`, `M2`, `M3`, `M27` (max_spend), `M28` (balance
  floor) all turn the suite red, so those guards are genuinely tested. Every
  money problem I found is either "keystrokes sent with no accounting"
  (finding 1) or "accounting for a match that never started" (finding 2).
* **`progress*.json` corruption via I/O.** `_atomic_write_json()` is correct
  (temp → flush → fsync → `os.replace`), `load_progress()` refuses a corrupt
  file rather than resetting, and `test_state_io.py`'s seven malformed
  learned-roster shapes are real assertions. The corruption risk is logical
  (finding 2's double-score), not a write hazard. The fixed `.tmp` filename is
  a pre-existing note from round 3 and remains low risk in a single process.
* **Off-by-one / wrong-origin in the ban scroll.** Executed: the scan reaches
  every catalogued row 0-6, returns all 33 positions, and `move_down` count
  equals `move_up` count exactly. `top_row = max(0, presses_so_far - 1)` and
  the 2-press stride leave no row uncovered (batches cover rows 0-1, 1-2, 3-4,
  5-6). The only navigation defect is the column (finding 10).
* **The motion gate acting when it should skip.** `M11` (removing the gate)
  turns the suite red on two assertions, and the gate structurally can only
  `continue`. The bound is genuinely tested with a virtual clock. Its only
  problem is the missing `try` (finding 9).
* **Misfire detection.** `M8` (deleting the check) and `M9` (recording it under
  a different event name) both turn the suite red, as does `M10` (making
  `norm_name` an identity function, which fails in three separate files). This
  mechanism is real and correctly tested.
* **The focus cache and adaptive backoff.** `M21` (cache disabled), `M22` (the
  default-argument trap reintroduced), `M23` (ceiling removed) are all caught
  with accurate messages. `test_input_timing.py` is the strongest file in the
  suite; the delta-based timing assertion does what its comment claims.
* **Reveal threshold.** `M30` (0.065 → 0.070, the silent-failure direction on
  the mss path) is caught by `test_settle_regions.py` *and* by `preflight.py`.
* **Screenshot logger / pruner.** `_prune_screenshot_log()` is correctly scoped
  to `_screenshot_run_dir`, which `start_screenshot_logger()` sets before the
  thread starts; the flat calibration corpus cannot be pruned. The only smell
  is that the global's *default* is the corpus root (`:735`), so any future
  caller that prunes before starting a run would delete calibration frames.

## Dead / unreachable code from today's changes

With `TRUST_ROSTER_ONLY = True`, these are unreachable in production:
`ocr_ban_card_name()`, `_read_ban_rows_separately()`, `read_ban_row_cards()`,
the two-consecutive-mismatch stop (`:2218-2228`), and `_learn_roster_entry()`
as called from the scan — so the roster can no longer self-extend.

**They should not be removed**: they are exactly what `TRUST_ROSTER_ONLY =
False` restores, and that rollback is documented as the escape hatch at
`:1997-1998`. The one piece that is genuinely pointless is the loop at
`:2077-2081`, which iterates over every expected position only to `continue`
when `trust_roster` is set; hoisting the flag check above the loop makes the
control flow honest without touching the rollback path.

Worth recording next to the flag, though: while it is on, `test_ocr_ban_card.py`
and `test_roster_matching.py` are testing code that never runs, and
`test_known_ban_roster.py`'s self-extension mutation check protects a property
that can no longer change.

## Highest-value next steps, in order

1. Make the C2 recovery press conditional on `not match_in_progress`
   (finding 1) — smallest change, largest untracked-money exposure.
2. Add a global no-progress bound independent of the current screen
   (finding 3), and give the three silent `break`s a `stop_reason`
   (finding 8).
3. Decide the C1 question: should scoring a result require
   `match_in_progress`? (finding 2). It contradicts an existing assertion, so
   it is a decision, not a patch.
4. Stop caching an incomplete ban scan (finding 6).
5. Write the first test that actually executes `read_full_ban_collection()`
   with faked capture + lock grid (finding 5). The probe in
   `zz_probe_ban.py` is ~40 lines and already does it; promoting it to
   `test_ban_scan.py` would cover the trust-roster path, the early stop, the
   scroll arithmetic and the cache in one file.
6. Drop `BASEBALL_MATCH_LOG` from `_running_under_test()` (finding 7).
