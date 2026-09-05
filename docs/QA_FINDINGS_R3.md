# QA Findings — Auto Baseball, Round 3

Review date: 2026-08-25. Scope: `orchestrator.py`, `input_controller.py`,
`hand_digit_reader.py`, `harvest_hands.py`, `decision_engine.py`, `test_*.py`.
No file was modified other than this one. Nothing was run that sends input to
the PS5. All six `test_*.py` files were run offline and **all pass**.

Everything below is measured or reasoned directly from the code. Where I am
unsure, I say so.

**Headline: the round-2 fixes are real.** I independently re-ran the two
experiments that produced round 2's Critical and re-measured both failure
modes; both are gone in the form they were reported. What is left is one
narrow residual of N1 and a set of documentation/robustness items.

---

## 1. Round-2 verification

| ID | Status | Evidence |
|---|---|---|
| **N1** wrong physical ban | **PARTIAL** | Both halves are real: `ocr_ban_card_name()` (`orchestrator.py:526`) now abstains on all 8 of round 2's realistic not-in-roster names (0 wrong vs 8 wrong before), and the identity mapping (`:1894-1909`) plus `select_bans_and_start_full(grid, banned_positions)` removes name matching entirely. **But** if `choose_bans()` picks the *same aliased object twice*, the mapping yields 3 **distinct** positions and both guards pass while one wrong physical card is banned. Reproduced — see **N15**. |
| **N2** `acted_screen` re-armed by a misread frame | **FIXED** | `:1771` is now `if screen != acted_screen and screen != "other"`. `result -> other -> result` no longer re-scores; `match_start_prompt -> other -> prompt` no longer re-debits. One narrow residual on `discard_prompt` — see **N20**. |
| **N3** unguarded `discard_prompt` | **FIXED** | `:1930-1938` has the same repeat guard as the other three branches, `stuck_count` is no longer reset while suppressed, and the branch bails at `MAX_STUCK_ATTEMPTS`. |
| **N4** logger failure logging ~499/500 silent | **FIXED** | `:644, 655, 664-666` — separate `failures` counter, reset to 0 on success, prints on `failures == 1 or failures % 100 == 0`. First failure is always reported. |
| **N5** logger stop not in a `finally` | **FIXED** | `try:` at `:1715` wraps the whole loop; `finally: screenshot_stop.set()` at `:2033-2035`. AST check confirms one `Try`, zero handlers, exactly one `.set()` call, no `return` anywhere in `run()`, and all 11 `break`s scoped as before. Small startup gap remains — see **N19**. |
| **N6** row 1 had zero downward tolerance / returned wrong names | **FIXED** | Independently re-ran the shift sweep on `test_fixtures/`: **WRONG = 0 at every offset from −60 px to +100 px** (previously wrong names at −10/−15/−20 px). Usable band widened from ~45 px to ~60-80 px, and past the band it now **abstains** instead of misreading. I also isolated the two fixes: with the *old* lenient matching restored, the new geometry alone gives WRONG=0 across −40..+40 px — so the geometry fix carries real weight, not just the cutoff. |
| **N7** surname fallback collapsed collisions | **FIXED** | `:1262-1271` builds `surname -> [names]` and returns `None` when `len(names) != 1`. Verified: `'wzqxvbnmkl gain'` → `None` (was: some other Jody Gain). 13 realistic first-word garbles of colliding surnames resolve correctly via the whole-string path; only one contrived case (`'AROLD BLUNT'`, dropping a quoted middle name) still mis-resolves. |
| **N8** corrupt learned roster breaks import | **FIXED** | `_load_learned_roster()` `:1181-1187` catches `(json.JSONDecodeError, OSError)` and warns; `_atomic_write_json()` `:83-93` does temp + `flush` + `fsync` + `os.replace`. Two narrower load paths are still unguarded — see **N18**. |
| **N9** two-read learning gate rarely satisfiable | **NOT FIXED** | Unchanged and, per the change summary, not in scope this round. `_pending_roster` (`:1199`) is still in-memory only; every row except row 1 is still seen once per run; the OCR short-circuit at `:1422` still suppresses the vision read that the gate needs. Learning remains effectively dead. Not harmful. |
| **N10** pruner eats the OCR fixtures | **FIXED** | `test_fixtures/` holds all 3 JPEGs; `test_ocr_ban_card.py:27` reads `SRC_DIR = "test_fixtures"`; `_prune_screenshot_log()` only touches `SCREENSHOT_LOG_DIR`. |
| **N11** ban guard has no recovery action | **FIXED (as documentation)** | `:1869-1875` explains why a blind retry would un-ban and that this is a hard stop by design. |
| **N12** `result` branch has no `try/except` | **NOT FIXED** | The change summary lists N12 as "comment explaining a deliberate choice", but there is no `try/except` at `:1774-1823` **and no comment** — `grep` for `N12` in the repo returns nothing. `save_progress()` or `press("close_result")` raising still terminates `run()`. Impact is now smaller (N5's `finally` stops the logger), but the finding stands. |
| **N13** `save_progress()` not atomic | **FIXED** | `:96-98` routes through `_atomic_write_json()`. The *read* side (`load_progress`) is still unguarded — see **N18**. |
| **N14** `turn` branch resets `stuck_count` unconditionally | **NOT FIXED** | Same as N12: the change summary claims a comment was added; `:2017` is still a bare `stuck_count = 0` with no `N14` comment anywhere. This is now the only remaining unbounded live-input path — see **N21**. |

### Round-1 items that round 2 left PARTIAL / NOT FIXED

| ID | Status | Evidence |
|---|---|---|
| **C1** result double-scoring | **FIXED** | Closed by N2 + the `:1784` guard; the `other` re-arm hole is gone. |
| **C2** `$50` double-debit | **FIXED** | Same mechanism, `:1830`. |
| **C3** ban toggle loop | **FIXED (with N15/N22 residuals)** | Round 1's third recommendation ("select by `(row, col)` identity, not name") is now implemented in `input_controller.py:169-177`. |
| **I2** row-fraction width/height inconsistency | **FIXED** | `BAN_GRID_ROW_Y_FRAC` is now read as width fractions in exactly one place (`:425`); the card crop uses its own `BAN_CARD_ROW_TOP_FRAC` (`:463`). The one-constant-two-meanings defect is genuinely gone. The comment describing it was not removed — see **N16**. |
| **I3** unverified roster entries persisted | **PARTIAL** | Unchanged (N9). `known_ban_roster_learned.json` still does not exist on disk, so nothing is poisoned. |
| **I9** screenshot logger unbounded | **PARTIAL** | N4, N5 and N10 all fixed. The cap is still `SCREENSHOT_LOG_MAX_FILES = 20000` at ~200 KB/frame ≈ **4 GB** (`:615`). Acceptable if deliberate, but it is not a small number. |
| **M6** `validate_card` accepts 1-3 as tactics | **NOT ADDRESSED** | `hand_digit_reader.py:200-209` unchanged. Still audit-only, still low stakes. |
| **M8** stale interval history | **PARTIAL** | `:617` still says "bumped up three times" over the four transitions it then lists (`1s -> 2s -> 0.5s -> 0.2s -> 0.1s`), and `1s -> 2s` is still called a bump *up*. |
| **M14** `harvest_hands.py` O(n²) dedupe | **PARTIAL (accepted)** | Unchanged; round 1 called it acceptable. |

**Nothing regressed.** No round-2 fix broke something that previously worked.

---

## 2. New findings

### Critical

*(none)*

---

### Important

#### N15. An aliased card object selected twice still bans one wrong physical card — the new `len(banned_positions) != 3` guard does not catch it
`orchestrator.py:1894-1909`, `decision_engine.py:172`

The comment at `:1902-1904` says:

> Must resolve to exactly 3 DISTINCT positions. `len(bans) == 3` alone is not
> enough: a duplicated object yields `[X, X, Y]`, which is length 3 but only
> two real cards.

That reasoning holds only when the duplicated object sits at **one** grid
position. The duplicate arises precisely because a mis-resolved OCR read put
the *same* `PlayerCard` object (out of `ROSTER_BY_NAME`, which shares objects
with `KNOWN_BAN_ROSTER`) at a **second** position — so the mapping loop finds
two positions for it and the guard passes:

```
grid = [(0,0,weak), (0,1,B), (0,2,C), (6,3,weak)]   # `weak` is the SAME object twice
bans = choose_bans(collection, 3)   -> [Weak Guy, Weak Guy, B]   # picked twice
banned_positions                    -> {(0,0), (0,1), (6,3)}     # 3 DISTINCT
len(bans) != 3                      -> False   # passes
len(banned_positions) != 3          -> False   # passes
distinct cards actually intended    -> 2
```

`select_bans_and_start_full()` then toggles all three, one of which — `(6,3)` —
is a physically different card that was never actually read.

**Why it matters.** This is the same class as round 2's Critical: wrong physical
input into a $50 match. **Reachability is much lower than N1's was**, and I want
to be honest about that:

- The alias now requires a whole-string fuzzy match at `cutoff=0.85` with no
  surname fallback. All 8 of round 2's realistic unknown names abstain; only
  contrived one-character variants (`'Mickey Browne'`, `'Rube Sharpe'`) still
  resolve.
- With the **full** 33-card roster it is effectively unreachable: 8 cards tie at
  the minimum power 4, the alias is appended last so it sorts last among ties,
  and `sorted(...)[:3]` cannot pick both copies. I confirmed this — injecting
  the alias into the real roster produced 3 correct positions.
- It becomes plausible on a **partial** collection (e.g. Taylere's save), where
  few cards are unlocked and the aliased card can easily be the unique weakest.

**Fix (one line).** Add an identity check alongside the existing one:

```python
if len({id(b) for b in bans}) != 3:
    raise ValueError("choose_bans returned the same card object more than once "
                     "— a mis-resolved read aliased two grid positions")
```

That is strictly stronger than the position count and catches the case the
existing comment believes it already catches.

*Confidence: high on the mechanism (reproduced); medium on how often a real
uncatalogued card OCRs to ≥0.85 against a known name.*

---

### Minor

#### N16. `get_ban_grid_card_crop()`'s comment describes code that no longer exists, and contradicts the N6 comment 20 lines above it
`orchestrator.py:479-488`

```python
y0 = BAN_CARD_ROW_TOP_FRAC[rel_row]
y1 = y0 + BAN_GRID_CARD_HEIGHT_FRAC
# I2: BAN_GRID_ROW_Y_FRAC is interpreted as HEIGHT fractions here and as
# WIDTH fractions in detect_ban_grid_locked(). That inconsistency is real
# ... Left as-is deliberately; see I2 note in QA_FINDINGS.md.
```

The function no longer references `BAN_GRID_ROW_Y_FRAC` at all — that is exactly
what N6 changed, and the N6 comment at `:452-462` says so. A maintainer reading
only the in-function comment would believe I2 is still open here and could
"re-unify" the wrong constant. The same block also quotes "18/18 -> 0/18", but
the test's current state is 16 resolved / 2 abstained.

**Fix.** Delete the stale I2 paragraph; keep only the "must re-run
`test_ocr_ban_card.py` AND re-verify lock detection" sentence.

#### N17. Two ban-geometry comments are attached to the wrong constants
`orchestrator.py:443-450`, `:463-468`

- The trailing comment on `BAN_CARD_ROW_TOP_FRAC` (`:463`) reads "widened
  2026-08-24: tightly-tuned (0.82, 0.96) worked on one frame but missed the name
  banner…". Those are name-**strip** fractions. It belongs to
  `BAN_CARD_NAME_STRIP_FRAC = (0.70, 1.0)` at `:450`, which is now comment-less.
- The block at `:443-448` still says the full card "extends further down from
  each row's same top edge" as `BAN_GRID_ROW_Y_FRAC` — no longer true.

Pure documentation, but this is the geometry that feeds the mis-ban path, so
the comments being trustworthy has real value.

#### N18. Three JSON read paths are still unguarded, and one is inconsistent with the N8 fix itself
`orchestrator.py:1215-1217`, `:1188-1190`, `:75-80`

- `_learn_roster_entry()` re-reads the learned roster with a bare
  `json.load()`. So a corrupt file **warns and degrades gracefully at import**
  (N8's fix) but then **hard-fails on every ban scan** — the exception unwinds
  `read_full_ban_collection()`, gets caught by the ban branch, and the run dies
  after 15 retries. The import-time warning ("continuing with the built-in
  roster only") is misleading about what will actually happen.
- `_load_learned_roster()` catches only `(json.JSONDecodeError, OSError)`. A
  file that is *valid JSON but the wrong shape* still bricks import:
  `map(int, key.split(","))` raises `ValueError` on a bad key,
  `v["name"]` raises `KeyError`/`TypeError` on a bad value. Catching `ValueError`
  (a superclass of `JSONDecodeError`) plus `KeyError`/`TypeError` closes this.
- `load_progress()` (`:75-80`) has no `try/except`, while `run()`'s own docstring
  (`:1658-1661`) instructs the user to **hand-edit** `progress.json` to top up
  the balance. A typo there is a raw `JSONDecodeError` at startup.

Also on the write side: `_atomic_write_json()` uses a fixed `f"{path}.tmp"`
name. Two processes writing the shared `known_ban_roster_learned.json`
concurrently would interleave into the same temp file, and a process killed
between `open()` and `os.replace()` leaves a `<path>.tmp` behind (harmless —
nothing reads it — but it will accumulate). `f"{path}.{os.getpid()}.tmp"` fixes
both. Single-process use makes this very low risk.

#### N19. The screenshot logger is started *before* the `try`, so two startup paths still bypass N5's `finally`
`orchestrator.py:1685` vs `:1715`

```
1685  screenshot_stop = start_screenshot_logger()
1687  wins, losses, draws, balance = load_progress(progress_file)   # can raise (N18)
1693  balance = read_balance_from_pause_menu()                      # raises BY DESIGN
1715  try:
```

`read_balance_from_pause_menu()` raises `RuntimeError` whenever the pause-menu
read comes back `None` — and its own docstring flags the Options-key assumption
as "not yet confirmed". Both raise with the logger already running and outside
the `finally`. Practical impact is small (daemon thread, process exits anyway),
but it is the same shape as N5 and is a one-line fix: move
`start_screenshot_logger()` to the first line inside the `try`, or extend the
`try` upward to `:1687`.

#### N20. `discard_prompt` can be permanently suppressed by a single `other` frame
`orchestrator.py:1771`, `:1930-1938`

The N2 fix deliberately makes `other` *not* clear the guard. For `result`,
`match_start_prompt` and `ban_screen` this is safe — two legitimate occurrences
of those screens always have a recognized screen (`turn`, `ban_screen`,
`result`) between them. `discard_prompt` is the exception: it can legitimately
recur on consecutive turns, and if the poll between turn N and turn N+1 lands on
an animation frame classified as `other`, turn N+1's genuine prompt is
suppressed — the loop sleeps 1 s per poll, never presses `confirm_play`, and
stops after 15 polls.

Low priority: the branch's own comment says this screen has never been observed
live. **Fix:** clear the guard on `turn` regardless (a `turn` screen proves the
previous prompt resolved), or scope the `other` exclusion to the three
irreversible-action screens only.

#### N21. The `turn` branch is now the only unbounded live-input path left
`orchestrator.py:2017` (this is N14, restated with its new significance)

After N3, every branch that sends keypresses bounds its repeats except this one.
`stuck_count = 0` runs whenever `play_one_turn()` returns without raising —
which it does as long as the *hand read* is usable, regardless of whether the
game advanced. A turn screen that stops responding replays ~10 keypresses every
few seconds forever, and `MAX_STUCK_ATTEMPTS` can never trip.

Round 2 rated this Minor and it stays Minor (the presses are into a card-select
UI, not a purchase), but it is now the highest-value remaining `stuck_count`
gap. A cheap bound: only reset `stuck_count` when the observed hand or score
actually changed since the previous `turn` poll.

#### N22. An exception partway through `select_bans_and_start_full()` makes the retry un-ban what it just banned
`orchestrator.py:1912-1920`

`acted_screen = "ban_screen"` is set at `:1921`, *after* the call. If
`select_bans_and_start_full()` raises after its first `press("select_card")`,
the `except` at `:1913` increments `stuck_count` and `continue`s with
`acted_screen` still `None` — so the next poll re-enters the full path, gets the
**cached** collection, and toggles the same positions again, un-banning them.
That is C3's original mechanism, just narrowed to the exception path.

The function is well-built against this in one respect: its `ValueError` at
`:173-177` fires *before* any keypress. The realistic raiser is a mid-flight
`pyautogui` failure (fail-safe corner), which is uncommon. **Fix:** set
`acted_screen = "ban_screen"` immediately *before* the call, so any partial
toggle is treated as an action taken.

---

## 3. Explicitly checked and NOT a problem

- **The `try/finally` indentation did not change control flow.** AST-verified:
  `run()` contains exactly one `Try` (0 handlers, `finally` = one `If`), its body
  is the single `While`, there are no `return` statements anywhere in `run()`,
  all 11 `break`s target the loop they targeted before (the one at `:1901`
  belongs to the inner ban-mapping `for`, as intended), and only one
  `screenshot_stop.set()` call remains. Python has no block scope, so no variable
  moved.
- **`choose_bans` returning a card that is in no grid position** raises cleanly —
  `banned_positions` comes out short and `:1905` trips. Only the *aliased*
  direction (N15) slips through.
- **Do NOT "unify" the two ban-grid row constants.** I measured per-cell mean
  contrast on all 3 fixtures with the shipped width-fraction boxes vs a
  height-fraction box aligned to `BAN_CARD_ROW_TOP_FRAC`. Shipped: locked cells
  50-80, unlocked 150-179 — a wide margin either side of the 100 threshold.
  Height-aligned: row 0 lands at 85-139, straddling the threshold. The width
  reading for lock detection is empirically correct; keeping the two constants
  separate is the right call.
- **The drift hazard between them is real but contained.** They encode the same
  physical row pitch in different units and already disagree: 400 px
  (`BAN_GRID_ROW_Y_FRAC`, width) vs 366 px (`BAN_CARD_ROW_TOP_FRAC`, height) at
  2000x1292. This is harmless only because both arrays are length 2 and only two
  rows are ever sampled. Two latent traps worth a comment or an `assert`:
  (a) adding a third row to `BAN_GRID_ROW_Y_FRAC` makes
  `get_ban_grid_card_crop()` `IndexError` (`expected_positions` iterates
  `range(len(locked_grid))`, which is driven by the *other* constant);
  (b) `detect_ban_grid_locked()` has **no test at all**, so a future
  recalibration of either constant is unverifiable offline.
- **`roster_hits` / `absolute_positions` cannot `NameError`.** `:1422` and
  `:1430` are protected by the left-to-right short-circuit on
  `if expected_positions and ...`.
- **`select_bans_and_start_full()`'s row-only sort is safe.** `full_collection`
  is built in ascending `(row, col)` order (batch tops go 0, 1, 3, 5, 7 with only
  row 1 overlapping), and Python's stable sort therefore preserves ascending
  columns within a row — so `range(row - current_row)` is never negative.
- **All six `test_*.py` pass**, including `test_ocr_ban_card.py` at
  16/18 resolved, 2 abstained, 0 wrong. `test_known_ban_roster.py` cleans up its
  scratch file and leaves no `.tmp` behind.
- **C4 remains fixed.** `hand_digit_reader.py:49-52` points at
  `./paddle_venv/bin/python`; `check_paddle_venv()` runs once from `run()` at
  `:1677-1678`, before the logger starts.
- **`ocr_ban_card_name()`'s stricter cutoff costs nothing live.** The 2
  abstentions are both at positions already in `KNOWN_BAN_ROSTER`, which
  short-circuit before OCR is ever called.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| Important | 1 |
| Minor | 7 |

Round-2 status: **10 FIXED, 1 PARTIAL (N1), 3 NOT FIXED (N9, N12, N14)** — with
the caveat that the change summary claimed comments were added for N12 and N14
and they are not in the code. Round-1 carry-overs: C1/C2/C3/I2 are now genuinely
closed; I3, I9, M6, M8, M14 remain as previously described. Nothing regressed.

**Most important remaining thing: N15** — add
`if len({id(b) for b in bans}) != 3: raise ...` next to the existing guard at
`orchestrator.py:1905`. It is one line, it is strictly stronger than the check
already there, and it closes the last path by which this loop can send a wrong
physical ban into a $50 match. Everything else on this list is a comment fix, a
robustness nicety, or a bound on an already-bounded-in-practice loop.

If N15 is fixed, the honest assessment of the rest is **nothing blocking** — the
code is in materially better shape than it was in round 2, and the two
measurements that produced round 2's Critical both come back clean now.
