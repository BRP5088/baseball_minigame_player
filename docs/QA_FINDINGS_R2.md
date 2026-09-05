# QA Findings — Auto Baseball, Round 2

Review date: 2026-08-25. Scope: `orchestrator.py`, `hand_digit_reader.py`,
`input_controller.py`, `harvest_hands.py`, `decision_engine.py`, `test_*.py`.
No files were modified other than this one. Nothing was run that sends input to
the PS5. All six `test_*.py` files were run offline and **all pass**.

Everything below is either measured or reasoned directly from the code. Where I
am unsure, I say so.

---

## 1. Round-1 verification

| ID | Status | Evidence |
|---|---|---|
| **C1** result double-scoring | **PARTIAL** | The `acted_screen == "result"` guard (`orchestrator.py:1709`) blocks *consecutive* result polls, but `acted_screen` is cleared by **any** different screen (`:1696-1697`), including the `other` catch-all. `result → other → result` re-scores. See **N2**. |
| **C2** `match_start_prompt` $50 double-debit | **PARTIAL** | Identical mechanism at `:1755` / `:1696`. One `other` frame between two prompt polls re-arms the debit. See **N2**. |
| **C3** ban-screen toggle loop | **PARTIAL** | Repeats are now bounded (`:1787-1795`), and `len(bans) != 3` is checked (`:1804`). But round 1's third recommendation — "select by `(row, col)` identity rather than by name" — was **not** implemented: `input_controller.py:165` still does `if card.name in banned_names`. I reproduced **4 physical toggles for 3 intended bans** with the `len(bans) != 3` guard passing. See **N1**. |
| **C4** `PADDLE_VENV_PYTHON` under `/private/tmp` | **FIXED** | Default is now `os.path.dirname(__file__)/paddle_venv/bin/python` (`hand_digit_reader.py:49-52`). I verified the relocated venv actually works: `./paddle_venv/bin/python -c "import paddleocr"` → 3.7.0 on Python 3.11.12, and an end-to-end `read_hand_digits()` on a real sample returned cleanly (returncode 0). `check_paddle_venv()` is called once from `run()` at `:1614`. |
| **I1** temp-file leak | **FIXED** | `tmp_path` is captured before the `with`, and unlinked in a `finally` with its own `OSError` guard (`orchestrator.py:844-860`). |
| **I2** row-fraction width/height inconsistency | **NOT FIXED (deliberate)** — and the in-code justification is partly wrong | The comment at `:453-462` claims "Height is empirically correct for locating the card body". It is not: at 2000x1292 the height reading puts row 0's card top at y=251 when the real card starts at ~520. What is correct is the *row pitch* interpretation for the name strip, with a ~0.28·h offset absorbed by an inflated `BAN_GRID_CARD_HEIGHT_FRAC`. I measured the practical consequence — see **N6** (row 1 has **zero** downward margin). |
| **I3** unverified roster entries persisted | **PARTIAL** | The two-read gate exists and `test_known_ban_roster.py` covers it. But the two reads are not reliably independent, the gate is rarely satisfiable at all (**N9**), and it does not protect against the dominant failure — a deterministic wrong fuzzy match that would agree with itself (**N1**, **N7**). `known_ban_roster_learned.json` still does not exist on disk, so nothing is poisoned yet. |
| **I4** dead CLIP import | **FIXED** | No `hand_card_matcher` / `open_clip` reference remains outside `_obsolete/`. `run()`'s docstring updated (`:1584-1585`). |
| **I5** hand comparison misalignment | **FIXED** | `:869-885` only aligns slot-by-slot when `len(local_cards) == 5`; otherwise it prints the count mismatch as the finding. |
| **I6** `harvest_hands.py` geometry mixing | **FIXED** | `OUT_DIR = f"hand_samples_y{_Y0:.3f}"` → `hand_samples_y0716`, and output is PNG (`harvest_hands.py:30-31, 73`). Old `hand_samples/` (JPEG, 1020x298) is untouched. |
| **I7** unguarded `phase` | **FIXED** | `validate_game_state()` `:964-966` rejects a `turn`/`discard_prompt` screen whose phase isn't `batting`/`pitching`; `test_validate_game_state.py` covers missing/null/nonsense phase and passes. |
| **I8** `KeyError` on missing `secondary` | **FIXED** | `isinstance(c.get("secondary"), int)` added to the candidate filter (`:1391`). |
| **I9** screenshot logger unbounded | **PARTIAL** | Cap + oldest-first prune work, and there is **no writer race** — `_prune_screenshot_log()` is called from the logger thread itself (`:619-620`), and Pillow's macOS `ImageGrab.grab()` uses `tempfile.mkstemp()` per call, so concurrent screenshots from the two threads cannot collide (checked the installed Pillow 12.3.0 source). But: the error-reporting throttle is broken (**N4**), the stop handle is not in a `finally` despite the comment saying it is (**N5**), the cap is ~4 GB, and the prune will eat the offline test fixtures (**N10**). |
| **M1/M2/M10** obsolete modules | **FIXED** | Moved to `_obsolete/` with a README; `navigate_grid`/`select_bans_and_start` gone from `input_controller.py`; nothing imports them. |
| **M3** `hand_digit_reader` docstring | **FIXED** | `hand_digit_reader.py:39-42` now says "wired in as an AUDIT-ONLY cross-read … Vision remains authoritative". |
| **M4** "two scales" vs three | **FIXED** | `hand_digit_reader.py:75-78` now says "THREE scales (1x, 2x, 4x)". |
| **M5** `group_into_cards` docstring | **FIXED** | `hand_digit_reader.py:222-226` now states the Δy rule was never implemented and that §14's figures don't transfer. |
| **M6** `validate_card` accepts 1-3 as tactics | **NOT ADDRESSED** | `hand_digit_reader.py:200-209` unchanged. Round 1 framed this as informational, not a required fix; still audit-only, so still low stakes. |
| **M7** `ROSTER_BY_NAME` not rebuilt | **FIXED** | Updated in `_learn_roster_entry()` (`:1162`) and refreshed after `_load_learned_roster()` (`:1183`); asserted in `test_known_ban_roster.py`. |
| **M8** stale "1Hz" | **PARTIAL** | Both docstrings fixed (`:631`, `:1587`) and the history line is now in intervals. The count is still wrong: `:582-583` says "bumped up three times" over **four** transitions (`1s -> 2s -> 0.5s -> 0.2s -> 0.1s`), and `1s -> 2s` is still described as a bump *up*. |
| **M9** wrong env var in docstring | **FIXED** | `:24-27` names `PERSONAL_ANTHROPIC_API_KEY` and lists `pytesseract numpy Pillow`. |
| **M11** double `confirm_play` | **FIXED (as documentation)** | `input_controller.py:183-189` explains it and warns against "cleaning it up". |
| **M12** subprocess returncode ignored | **FIXED** | `hand_digit_reader.py:169-172`. |
| **M13** shield-recovery self-suppression | **FIXED** | `_global = list(merged)` snapshot taken before the loop; the membership test uses `_global` (`hand_digit_reader.py:133-137`). |
| **M14** JPEG re-encode + O(n²) | **PARTIAL** | PNG output done (`harvest_hands.py:73`). The O(n²) dedupe at `:67` is unchanged — round 1 called that acceptable, so this is fine. |

---

## 2. New findings

### Critical

#### N1. A ban-grid position that isn't in `KNOWN_BAN_ROSTER` gets silently resolved to the *wrong* known card, which then bans the wrong physical card
`orchestrator.py:466-491` (`ocr_ban_card_name`), `:1186-1208` (`match_roster_name`),
`:1348-1357` (the OCR short-circuit), `input_controller.py:164-167`

`ocr_ban_card_name()` ends in `return match_roster_name(cleaned)` — so it **can
only ever return a card that is already in the roster**. For a grid position not
yet catalogued (the table's own comment at `:1080-1083` says row 6 cols 3-4 were
never captured), the OCR reads the card's real name and `match_roster_name()`
fuzzy-matches it against the 33 known names at `cutoff=0.5`, with a surname
fallback at `cutoff=0.6`. I fed it 17 plausible not-in-roster names:

```
'Bobby Sharp'   -> 'Rube Sharp'        'Mickey Lee'   -> 'Mickey Brown'
'Thomas Brown'  -> 'Thomas Thomas'     'Jose Diaz'    -> 'Joshua Diaz'
'Frank Coker'   -> 'Brian Coker'       'Nate Kelly'   -> 'Noah "The Rat Baron" Kelly'
'Randy Curd'    -> 'Jeremiah Curd'     'Otis Black'   -> 'Jake Saucepan Black'
... 15 of 17 resolved to a wrong roster card; only 2 returned None.
```

Three things follow, in the same pass:

1. **The vision read that would have corrected it is skipped.** `roster_hits[pos]
   = local_card` (`:1353`), and the branch at `:1359` is
   `len(roster_hits) == len(expected_positions)` — a *count* test. A wrong OCR
   match still counts, so the batch short-circuits and `read_ban_row_cards()`
   never runs for that view.
2. **`grid` now contains the same name at two positions**, and — because
   `roster_hits[pos]` is the *same `PlayerCard` object* out of
   `KNOWN_BAN_ROSTER` — the same object twice in `collection`.
3. **`select_bans_and_start_full()` toggles by name** (`input_controller.py:165`),
   so both positions get toggled for one intended ban.

I reproduced this against the real roster:

```
grid += [(6, 3, KNOWN_BAN_ROSTER[(1,1)])]     # false OCR match, same object
bans = choose_bans(collection, 3)              -> 3 cards
len(bans) != 3 guard trips?                    -> False        # passes
physical cards that would be TOGGLED           -> 4
   (1,1) William Lee-Gains, (1,3) Joshua Diaz,
   (2,1) Johnny "Blaze" Sweets, (6,3) William Lee-Gains
```

A related variant of the same hole: when the duplicated object lands inside
`sorted(...)[:3]`, `bans` is `[X, X, Y]` — `len(bans) == 3` passes, but
`banned_names = {X, Y}` is only **two** distinct cards. The `len(bans) != 3`
check at `:1804` measures the wrong thing.

**Why it matters.** This is the only path in the current code that sends *wrong
physical input* into a $50-per-match loop. Best case the game shows the wrong
ban count and refuses to start, and the C3 guard stops the run after 15 polls
(~30 s of a jammed ban screen). Worst case three or four wrong cards get banned
for the match. It is also reachable on the very next full-collection scan of a
complete save, since (6,3) and (6,4) are exactly the uncatalogued positions.

**Fix.** (a) Have `read_full_ban_collection()` key everything on `(row, col)` and
pass positions, not names, to `select_bans_and_start_full()`; assert the number
of toggles equals 3 before pressing anything. (b) Make `ocr_ban_card_name()`
refuse to resolve a position that isn't already catalogued — or require a much
stricter match there (whole-string only, high cutoff, no surname fallback), and
fall through to vision on failure. (c) Change `:1804` to check
`len({c.name for c in bans}) == 3` as well.

---

### Important

#### N2. The `acted_screen` guard is re-armed by a single misread frame
`orchestrator.py:1696-1697`

```python
if screen != acted_screen:
    acted_screen = None
```

Any different screen clears the guard — including `"other"`, which the prompt
defines as the catch-all for "menus, overworld, dialogue, loading, etc". The
result overlay's own fade/animation frames are prime candidates for that
classification. Trace:

```
poll 1: result  acted=None  -> SCORE, acted="result"
poll 2: other   acted="result" -> cleared -> stuck_count += 1
poll 3: result  acted=None  -> SCORE AGAIN
```

The same three lines double-debit $50 on `match_start_prompt` and re-toggle bans
on `ban_screen`. C1/C2/C3 are narrowed (a *consecutive* repeat is now caught) but
not closed: one noisy frame between two polls of the same lingering screen is
enough.

**Fix.** Make the guard content-based rather than transition-based: remember the
`(your_score, opp_score)` pair scored, or require an intervening screen from an
allow-list (`turn` / `ban_screen` / `match_start_prompt`) rather than "anything
different".

*Confidence: high on the code path; medium on how often vision actually emits
`other` mid-result-overlay — that needs one live session with
`log_screenshots=True` to confirm.*

#### N3. The `discard_prompt` branch has no guard and resets `stuck_count`
`orchestrator.py:1823-1832`

```python
elif screen == "discard_prompt":
    stuck_count = 0
    press("confirm_play")
    wait_for_screen_to_settle(max_wait=4.0)
    continue
```

This is the exact defect class C1/C2/C3 were about, left un-fixed on the one
branch that wasn't in round 1's list. If the prompt doesn't dismiss, this presses
Triangle every ~2 s **forever** — `stuck_count = 0` on every pass means
`MAX_STUCK_ATTEMPTS` can never trip. It doesn't corrupt persisted state, but it
is an unbounded stream of live input into the game, and the branch's own comment
says this screen has "never [been] observed live yet", so its dismissal behaviour
is unverified.

**Fix.** Give it the same `acted_screen` treatment as the other three branches.

#### N4. The screenshot logger's failure message is ~499/500 silent — I9's actual complaint is not fixed
`orchestrator.py:608-625`

```python
frames = 0
...
    img = pyautogui.screenshot()
    ...
    frames += 1                      # <- only on success
except Exception as e:
    if frames % 500 == 0:
        print(f"[screenshot-logger] write failed ({e})")
```

`frames` never advances while writes are failing, so `frames % 500` is a
**constant** for the entire duration of the failure. Either it happens to be 0 —
and the message prints 10x/second forever, drowning the real loop's output — or
it isn't, and the failure is **completely silent**, which is precisely what I9
said was wrong ("the exception swallow means `ENOSPC` failures are invisible").
There is a 1-in-500 chance of the noisy branch and 499-in-500 of the silent one.

**Fix.** Count failures in their own counter, or throttle on wall-clock time
(`if now - last_warn > 30`).

#### N5. `screenshot_stop.set()` is not in a `finally`, contradicting its own comment
`orchestrator.py:1617-1623` vs `:1917-1925`

The comment at `:1621` says *"Stopped in the `finally` below."* There is no
`finally` in `run()` — the two `screenshot_stop.set()` calls sit inside the
`if wins >= target_wins:` / `else:` tail. Any exception that escapes the loop
(e.g. `press("close_result")` raising in the un-guarded result branch — see N12,
or `save_progress` hitting a disk error) skips both. Impact is limited because
the thread is a daemon, but the comment is actively misleading and an
interactive `KeyboardInterrupt` leaves the logger writing until the process dies.

**Fix.** Wrap the loop in `try/finally` and set the event there once.

#### N6. Row 1 of the ban grid has **zero** downward tolerance, and past that boundary it returns *wrong names*, not misses
`orchestrator.py:445-463` (this is the concrete cost of leaving I2 unfixed)

I re-ran the 18 `test_ocr_ban_card.py` cases while shifting
`BAN_GRID_ROW_Y_FRAC` by a few pixels of frame height:

```
y shift  -40px: row0 12/12  row1 0/6
y shift  -20px: row0 12/12  row1 0/6
y shift  -10px: row0 12/12  row1 0/6      <- 0.8% of frame height
y shift   +0px: row0 12/12  row1 6/6
y shift  +40px: row0 12/12  row1 6/6
y shift  +60px: row0 12/12  row1 6/6      (row0 starts failing at +60)
```

The 18/18 pass rate is real but sits on a cliff edge. Worse, inside the failure
band the reads are not `None`:

```
-20px:  Joe Jody Gain -> WRONG: 'Claude Ewer'
-15px:  Mickey Brown  -> WRONG: 'Zachary Lee'
```

Root cause, measured on `screenshot_log/20260824_200601_124.jpg` (2000x1292): the
true card-row pitch is ~366 px. `detect_ban_grid_locked()`'s width reading gives
a pitch of 400 px (close); `get_ban_grid_card_crop()`'s height reading gives
259 px (far). So the name strip drifts ~107 px per row — row 0's banner sits at
the top of its strip, row 1's at the very bottom. `BAN_CARD_NAME_STRIP_FRAC`
being widened to `(0.70, 1.0)` is what is holding row 1 in, with nothing to
spare. The two rows have no shared safety margin at all: the usable window is
roughly −5 px to +40 px.

This matters because the geometry is fractions of a **full-screen** capture, so
the Chiaki-ng window moving, being resized, or a different letterbox thickness
shifts everything — and the failure mode is a wrong name feeding N1.

**Fix.** Re-derive `BAN_GRID_ROW_Y_FRAC` (or a separate constant) from the real
366 px pitch, in one interpretation, and re-run `test_ocr_ban_card.py` plus a
lock-detection check. Round 1's "0/18 when switched to width" result is
consistent with this — switching the interpretation alone, without also fixing
the pitch and the `0.40` card-height fudge, cannot work.

#### N7. `match_roster_name`'s surname fallback silently drops colliding surnames
`orchestrator.py:1204`

```python
last_word_map = {name.split()[-1]: name for name in ROSTER_BY_NAME}
```

Dict-comprehension keys collapse. The current roster has three collisions:

```
gain  -> 4 names, resolves only to 'papa jody gain'
blunt -> 2 names, resolves only to 'joel blunt'
brown -> 2 names, resolves only to 'mickey brown'
```

The surname fallback exists specifically because "OCR noise … tends to hit the
first word harder" (`:1189-1193`). So the exact case it was written for — a
garbled first word on a Jody Gain card — returns *some other* Jody Gain, with
that card's power/secondary, which the docstring advertises as "trusted". Powers
across the four Gains are 5/6/6/5 and secondaries 1/0/0/0, so the returned stats
can be wrong. This feeds both `ocr_ban_card_name()` (ban selection) and
`ocr_runner_card()` (runner stats into `best_pitching_play`).

**Fix.** Make the fallback return `None` when a surname is ambiguous, or match
against `(surname, first-initial)`.

#### N8. A truncated `known_ban_roster_learned.json` breaks `import orchestrator` for everything
`orchestrator.py:1132-1139` (load, at module scope via `:1182`), `:1169-1170` (write)

`_load_learned_roster()` calls `json.load()` with no `try`, at **import time**.
The write is `open(..., "w")` + `json.dump()` — not atomic, and it now runs
mid-ban-scan on a live run. A Ctrl-C or crash between truncate and flush leaves a
partial file, after which `import orchestrator` raises `JSONDecodeError` — taking
down `run()`, `harvest_hands.py`, and all six `test_*.py` files, with an error
that points at nothing useful.

Round 1 correctly noted the file doesn't exist yet. It will as soon as the
learning path fires, so this is a "fix before the first live ban scan" item.

**Fix.** Write to a temp file and `os.replace()`; wrap the load in
`try/except (OSError, ValueError)` and warn rather than raise.

---

### Minor

#### N9. The "two independent agreeing reads" gate is rarely satisfiable, so learning is mostly dead
`orchestrator.py:1148-1171`, `:1326`, `:1348-1357`

`_pending_roster` is in-memory only and dies with the process. Within one run the
scan reads `top_row = max(0, presses_so_far - 1)` with `presses_so_far` stepping
by 2, so visible rows are `[0,1] [1,2] [3,4] [5,6] …` — every row except row 1 is
seen **exactly once per run**. And `read_full_ban_collection()` caches, so there
is only one scan per run.

Net effect: an entry can only ever be persisted when the local-OCR read and the
vision read land in the *same batch* and agree. But if OCR resolves every
position in the batch, the vision call is skipped entirely (`:1359`) — so the
common case learns nothing, ever, on any number of runs.

Not harmful (the current scan still uses the OCR result), but it means I3's fix
effectively disabled the self-extending roster rather than gating it. Worth
either persisting `_pending_roster` to disk or accepting and documenting that
learning now requires an OCR+vision agreement in one batch.

*The inverse also holds and is worth noting: for a row seen twice in one scan
(row 1), the two "independent" reads are the same deterministic OCR+fuzzy
pipeline on the same position, so a wrong match would agree with itself and be
persisted permanently. Row 1 is fully catalogued today so the OCR path isn't
taken for it — but the gate does not actually guarantee independence.*

#### N10. The new pruner will delete `test_ocr_ban_card.py`'s fixtures
`orchestrator.py:592-603`, `test_ocr_ban_card.py:16`

`_prune_screenshot_log()` deletes oldest-first from `screenshot_log/`, which is
where the only offline regression test for ban-card OCR keeps its three
reference frames (`20260824_200520_984.jpg`, `..._200601_124.jpg`,
`..._200604_139.jpg`). The directory holds 1,815 files today and the cap is
20,000, so nothing is at risk yet — but one long `log_screenshots=True` session
(~33 min) starts eating them, and the test then dies on `Image.open`.

**Fix.** Copy the 3 fixtures into a `test_fixtures/` directory the pruner never
touches.

#### N11. The ban-screen guard has no recovery action
`orchestrator.py:1787-1795`

The suppressed branch only does `time.sleep(2); continue`. Unlike the result and
match-start guards (which re-press their button), a ban screen that is one
`confirm_play` short of advancing can never recover — the run just burns 15 polls
and stops. That is the safe choice given the toggle semantics, but combined with
M11's "NOT verified against the game's UI frame-by-frame" note on the double
confirm, it means any drift in that press count is a hard stop rather than a
retry. Worth a comment at minimum.

#### N12. The `result` branch has no `try/except`
`orchestrator.py:1699-1748`

Every other action branch wraps its work. This one calls `save_progress()` and
`press("close_result")` bare; either raising (disk error, `osascript` failure,
`pyautogui` fail-safe) propagates out of `run()` and terminates the session —
after `acted_screen` was already set and, depending on where it raised, after the
win was counted. Combined with N5, the screenshot logger is left running.

#### N13. `save_progress()` is not atomic
`orchestrator.py:83-85`

`progress.json` is rewritten on every result and every match start. A crash mid-
write leaves a partial file, and `load_progress()` (`:76-80`) has no
`try/except` — the next start dies on `json.JSONDecodeError` with the win/loss
record gone. Same one-line fix as N8 (`os.replace`).

#### N14. The `turn` branch also resets `stuck_count` unconditionally
`orchestrator.py:1901`

Same shape as N3, lower stakes: if `play_one_turn()` "succeeds" (sends its
keypresses) but the game doesn't advance, the loop replays ~10 keypresses every
few seconds indefinitely, and `MAX_STUCK_ATTEMPTS` can never trip. Arguably
correct — a turn screen that stays up may genuinely need another attempt — but
it is unbounded and should probably cap out somewhere.

---

## Explicitly checked and NOT a problem

- **No screenshot race between the logger thread and the main loop.** Pillow
  12.3.0's macOS `ImageGrab.grab()` allocates a fresh `tempfile.mkstemp()` per
  call, and pyscreeze delegates to it for Pillow ≥ 6.2.1. Confirmed by reading
  the installed source.
- **No writer/pruner race.** `_prune_screenshot_log()` is called from inside
  `_screenshot_logger_loop()` (`:619-620`), i.e. the same thread that writes.
- **The relocated `paddle_venv` works.** `pyvenv.cfg` still records the old
  `/private/tmp` build path, but venvs on macOS derive `sys.prefix` from the
  interpreter's own location, and `bin/python3.11` symlinks to
  `/opt/homebrew/...`. `import paddleocr` succeeds and a real
  `read_hand_digits()` call returned cleanly.
- **`get_ban_grid_card_crop`'s height reading is genuinely required** — I
  re-confirmed round 1's finding that swapping it to width breaks all 18 OCR
  cases. The problem is the *pitch*, not the axis (N6).
- **All six `test_*.py` pass** as of this review, including the two new ones
  (`test_validate_game_state.py`, and the two-read learning round-trip in
  `test_known_ban_roster.py`).
- **`validate_game_state()`'s new phase check does not affect result screens** —
  the check is scoped to `turn`/`discard_prompt` only (`:964`). One thing to
  watch live: if vision returns `phase: null` on real turn screens more often
  than expected, the run now *halts* after 15 retries instead of silently
  playing the pitching strategy. That is the right trade, but it is a behaviour
  change worth observing on the next session.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 1 |
| Important | 7 |
| Minor | 6 |

Round-1 status: **4 FIXED, 4 PARTIAL, 1 NOT FIXED (deliberate)** among C/I
items; **9 FIXED, 3 PARTIAL, 1 not addressed** among M items. Nothing regressed
outright — the round-1 fixes are real improvements, and C4/I1/I4/I5/I6/I7/I8 are
cleanly done.

**Fix first: N1.** It is the only finding that causes wrong physical input into a
match that costs $50, it is reachable on the next full-collection scan (positions
(6,3)/(6,4) are uncatalogued by the roster's own admission), and it defeats both
round-1 guards it passes through — the `len(bans) != 3` check passes while four
cards get toggled, and the count-based `roster_hits` short-circuit suppresses the
vision read that would have caught the wrong name. The minimal version is two
changes: pass `(row, col)` instead of names into
`select_bans_and_start_full()` and assert exactly three toggles, and make
`ocr_ban_card_name()` refuse to resolve a position that isn't already in
`KNOWN_BAN_ROSTER`. N6 and N7 are the two mechanisms that produce the wrong name
in the first place and should follow immediately after.
