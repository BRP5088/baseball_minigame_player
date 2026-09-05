# QA Findings — Auto Baseball, Round 4

Review date: 2026-08-25. Scope: `orchestrator.py`, `input_controller.py`,
`hand_digit_reader.py`, `harvest_hands.py`, `decision_engine.py`, all
`test_*.py`. No file was modified other than this one. Nothing was run that
sends input to the PS5. All **seven** `test_*.py` files were run offline and
**all pass**.

Every status below was read out of the code, not out of the change summary.
Round 3 caught two fixes that were claimed but never landed; this round I
re-checked each claim against the source and, where the fix is a *comment*,
against whether the comment's reasoning is actually true.

**Headline: the round-3 fixes are real, and the code is in good shape.** No
Critical and no Important findings. Three Minors, all of which are
documentation-or-one-line items rather than defects that can send wrong input
into a paid match.

---

## 1. Round-3 verification

| ID | Status | Evidence (read from the code) |
|---|---|---|
| **N15** aliased card object banned as a third ban | **FIXED** | `orchestrator.py:1937-1941` — `if len({id(b) for b in bans}) != 3: raise ValueError(...)`, placed *before* the position check at `:1942`. It is strictly stronger: with duplicate objects it fires first, which makes `len(banned_positions) != 3` unreachable (harmless redundancy). Verified no false positives — see §3. |
| **N12** `result` branch has no `try/except` | **PARTIAL** | The comment now exists (`:1808-1812`) and the scoring block *is* wrapped (`try:` `:1813`, `except` `:1841-1847`, `stuck_count += 1` + retry, `break` at `MAX_STUCK_ATTEMPTS`). But `press("close_result")` (`:1848`) and `wait_for_screen_to_settle()` (`:1849`) are still **outside** the try — and round 2's N12 named `press("close_result")` explicitly as one of the two bare calls. A `pyautogui` fail-safe there still propagates out of `run()`. N5's `finally` now stops the logger, so the residual impact is small. The except's own behaviour is also not what its comment says — see **N24**. |
| **N14** `turn` branch resets `stuck_count` unconditionally | **FIXED as documentation, but the documentation is wrong** | The comment is genuinely in the code this time (`:1987-1992`), unlike rounds 2 and 3. Its justification — *"play_one_turn() consumes a real card each time, so a repeat is progress"* — is false on the discard sub-path, where `play_one_turn()` returns `played=False` and its own docstring says no turn was used. See **N25**. |
| **Stale I2 comment** in `get_ban_grid_card_crop()` | **FIXED** | `:487-495` no longer mentions `BAN_GRID_ROW_Y_FRAC` as being used here, no longer quotes "18/18 -> 0/18", and now states the correct reason not to unify (measured 85-139 straddle vs 50-80 / 150-179). Contradiction with the N6 note at `:460-470` is gone. |
| **Unguarded JSON read** — `_learn_roster_entry()` | **FIXED** | `:1222-1230` wraps the re-read in `try/except (json.JSONDecodeError, OSError): raw = {}`. A corrupt cache now degrades identically at import and mid-scan, instead of warning once and then killing every ban scan. |
| **Unguarded JSON read** — `load_progress()` | **FIXED** | `:75-88` raises `RuntimeError("… Refusing to start and silently reset your progress …")` on `(JSONDecodeError, OSError)`. No caller depends on the old silent-default behaviour — `load_progress` has exactly one call site, `run():1695`, and no test or other module references it (`grep` over all `*.py`). The `balance is None` path at `:1696` is a separate, still-supported case (fresh file), unaffected. |
| **Unguarded JSON read** — `_load_learned_roster()` shape errors | **NOT FIXED** | Still `except (json.JSONDecodeError, OSError)` at `:1191`, with the risky work *after* the try: `:1196` `map(int, key.split(","))` raises `ValueError` on a bad key and `:1197` `v["name"]` raises `KeyError`/`TypeError` on a bad value — at **module scope**, so a valid-JSON-but-wrong-shape file still bricks `import orchestrator` for every script and every test. This was the second bullet of round 3's N18 and was not in the claimed-fix list. `except (ValueError, KeyError, TypeError, OSError)` around the whole block closes it (`JSONDecodeError` is a `ValueError` subclass, so nothing is lost). |
| **Logger start moved inside the `try`** | **FIXED** | `start_screenshot_logger()` is now at `:1728`, inside the `try` opened at `:1723`; `screenshot_stop = None` at `:1693` and the `finally` at `:2075-2077` guards on `is not None`. Both pre-try raisers N19 named (`load_progress()` `:1695`, `read_balance_from_pause_menu()` `:1701`) now run *before* the logger exists, so there is no path left where the logger is running outside the `finally`. AST re-check of `run()`: exactly **one** `Try` with a `finally` (7 others, all with handlers and no finally), **zero** `return`s, **one** `screenshot_stop.set()` (`:2077`), one `While` (`:1730`), 12 `break`s — the new one is `:1847` in the N12 except, correctly bound to the `while`. |
| **NEW TEST** `test_ban_grid_locked.py` | **FIXED, ground truth independently confirmed** | See §2 / §3. The expected grids are correct, and the test does fail on the plausible unification directions — but only one of its two fixtures discriminates, and it does not cover the *other* direction of unification. See **N23**. |

### Round-3 findings not claimed as fixed (status for completeness)

| ID | Status | Evidence |
|---|---|---|
| **N16** stale I2 paragraph | **FIXED** | See table above. |
| **N17** two ban-geometry comments on the wrong constants | **NOT FIXED** | `:471-476` still attaches "widened 2026-08-24: tightly-tuned (0.82, 0.96) …" to `BAN_CARD_ROW_TOP_FRAC = [0.195, 0.478]` — those are name-**strip** fractions belonging to `BAN_CARD_NAME_STRIP_FRAC` at `:458`, which is still comment-less. `:453-454` still says the full card "extends further down from **each row's same top edge**"; the two constants' row-0 tops are numerically both `0.195` but in different units — 390 px vs 252 px at 2000x1292 — and row 1 is `0.395` vs `0.478`. Same top edge is now false in both senses. |
| **N18** unguarded JSON reads | **PARTIAL** | 2 of 3 fixed (above). `_atomic_write_json()`'s fixed `f"{path}.tmp"` name (`:96`) is unchanged; single-process use makes it very low risk, as round 3 said. |
| **N19** logger started before the `try` | **FIXED** | See table above. |
| **N20** `discard_prompt` suppressible by one `other` frame | **NOT FIXED** | `:1785` is still `if screen != acted_screen and screen != "other"`, and `:1966-1974` still suppresses on `acted_screen == "discard_prompt"` with no `turn`-clears-the-guard exception. Unchanged from round 3; the branch's own comment (`:1980`) still says the screen has never been observed live. |
| **N21 / N14** unbounded `turn` branch | **NOT FIXED (documented instead)** | See **N25**. |
| **N22** partial `select_bans_and_start_full()` un-bans on retry | **NOT FIXED** | `acted_screen = "ban_screen"` is still at `:1957`, *after* the `select_bans_and_start_full(grid, banned_positions)` call at `:1948`. A mid-flight raise still lands in the `except` at `:1949` with `acted_screen` unset. As round 3 noted, `input_controller.py:173-177` raises before any keypress, so the realistic raiser is a `pyautogui` failure mid-toggle. |
| **N9**, **I9**, **M6**, **M8**, **M14** | **NOT FIXED (deliberate)** | Confirmed unchanged; excluded from re-reporting per the review brief. Noted only because N9 is load-bearing for §3's safety argument. |

**Nothing regressed.** Every round-3 change is additive and none of them broke a
behaviour that previously worked. All seven tests pass:
`test_ban_grid_locked` (20 cells, 2 frames), `test_ocr_ban_card` (16/18
resolved, 2 abstained, 0 wrong), `test_known_ban_roster`,
`test_validate_game_state`, `test_ocr_runner`, `test_ocr_scoreboard`,
`test_gameplay_regions`.

---

## 2. Independent verification of `test_ban_grid_locked.py`

I did not trust the per-frame comments. Three checks:

**(a) Ground truth is correct.** I re-derived the contrast grid myself
(MaxFilter/MinFilter difference, kernel 41, width fractions) and then rendered
the actual card crops to look at them:

```
20260824_200520_984.jpg  row0 [151.7 167.3  53.3 165.2 158.9]  row1 [ 78.2  62.2 178.9 162.7 163.7]
20260824_200601_124.jpg  row0 [170.2 167.1  50.4 163.7 151.1]  row1 [169.0 162.5  74.9 161.9 159.1]
```

Visual inspection of the rendered grids confirms it cell by cell: in frame 1,
`Harold "Fisto" Blunt` (0,2) is the only faded card in row 0, and `Claude Ewer`
(1,0) and `William Lee-Gains` (1,1) are both washed out in row 1 while
`Brandon "Binger" Ortiz` / `Joshua Diaz` / `Justin Young` are fully rendered. In
frame 2, `Jacob "Cheesehead" McQueen` (0,2) and `Brian Coker` (1,2) are the
faded ones. The names also line up with `KNOWN_BAN_ROSTER` rows 0/1 and 3/4
respectively, and with which positions `test_ocr_ban_card.py` chooses to
exercise. **The expected grids in the test are right.**

Margins are wide: locked cells measure 50-80, unlocked 149-179, against a
threshold of 100. The single closest call is frame 3's (1,3) at **127.3** —
and frame 3 (`20260824_200604_139.jpg`) is *not* one of the test's two cases.
That is not wrong, just worth knowing.

**(b) It does fail if someone unifies the row constants — in one direction.**
I ran the two fixtures through three plausible unifications:

```
FAILS   rows from BAN_CARD_ROW_TOP_FRAC as HEIGHT fracs + 0.40 card height
FAILS   rows from BAN_CARD_ROW_TOP_FRAC as HEIGHT fracs, same 0.19 band
FAILS   same BAN_GRID_ROW_Y_FRAC values but read as HEIGHT
PASSES  BAN_GRID_ROW_Y_FRAC values replaced by the card-top pitch, still WIDTH
```

So yes — any change that makes `detect_ban_grid_locked()` sample on the
card-crop geometry is caught. Every one of those failures comes from
**frame 1 only**; frame 2 is misread by none of them, so the test's
discriminating power against this hazard rests entirely on
`20260824_200520_984.jpg`.

**(c) The other direction of unification is not caught at all** — see **N23**.

---

## 3. New findings

### Critical

*(none)*

### Important

*(none)*

---

### Minor

#### N23. The unification guard is one-directional: reverting the *card crop* to the shared constant leaves every test green
`test_ban_grid_locked.py:8-11`, `orchestrator.py:479-496`

The new test's docstring says:

> This test is what makes an accidental "unification" of those two fail loudly.

That is true only for changes to `detect_ban_grid_locked()`. The opposite —
and, judging by the history, more likely — edit is deleting
`BAN_CARD_ROW_TOP_FRAC` and putting `get_ban_grid_card_crop()` back on
`BAN_GRID_ROW_Y_FRAC` (the exact pre-N6 code). `detect_ban_grid_locked()` is
untouched by that, so `test_ban_grid_locked.py` still passes — and I measured
what `test_ocr_ban_card.py` does under the reverted geometry:

```
shipped geometry (BAN_CARD_ROW_TOP_FRAC):  16 resolved, 2 abstained, 0 wrong
pre-N6 geometry (BAN_GRID_ROW_Y_FRAC):     17 resolved, 1 abstained, 0 wrong   <- PASSES, and looks BETTER
```

A maintainer making that change sees all tests green *and* an apparently
improved OCR score, and concludes the unification was fine. It is not — the
row-1 cliff comes straight back. Shift sweep across the same 18 cases:

```
pre-N6 geometry   dy=-30/-20/-10 px: 11 resolved, 7 abstained   dy=0: 17 resolved
shipped geometry  dy=-30..+30 px:    15-16 resolved throughout
```

Six of the eighteen cards (all of row 1) drop out at a 10 px upward drift under
the reverted geometry, exactly as round 2 measured; the shipped geometry is
flat. The one thing that has genuinely improved since round 2 is that
`ocr_ban_card_name()`'s `cutoff=0.85` / no-surname-fallback now makes those
losses **abstentions, not wrong names** — so this is a robustness regression
(six extra vision calls, or a dropped batch) rather than a mis-ban. Hence
Minor, not Important.

**Fix.** Give the hazard a test that lives where the hazard is. Cheapest
version: assert the pitch in `test_ocr_ban_card.py`, e.g.
`assert abs((BAN_CARD_ROW_TOP_FRAC[1] - BAN_CARD_ROW_TOP_FRAC[0]) - 0.283) < 1e-9`
with a comment pointing at the measured 366 px row pitch. Better version: run
the existing 18 cases at `dy = ±10 px` and require row 1 to survive.

*Aside, same file:* `test_ban_grid_locked.py:61` opens frame 1 into `img` and
never uses it — the two asserts that follow read module constants only. Either
delete the line or finish what it was clearly meant to do (assert the measured
per-cell contrast separation, which is the claim the comment above it makes).

#### N24. The result-branch `except` can never actually retry, contradicting its own comment
`orchestrator.py:1808-1850`

The comment at `:1811-1812` promises:

> Score defensively; on failure fall through to close_result and let the next
> poll re-read.

But `acted_screen = "result"` is the **first** statement inside the `try`
(`:1814`), before any of the work that can raise. So on a scoring exception the
guard is already armed, and the next poll — which will still read `result` —
takes the suppression branch at `:1798-1807` and presses `close_result` without
ever re-scoring. The result is not re-read; it is dropped.

State coherence on that path is otherwise fine, and I checked the two specific
hazards:

- **Double-count on a post-`save_progress` exception: not possible.**
  `save_progress()` (`:1840`) is the last statement in the `try`; there is no
  code after it that can raise, and the armed guard prevents a second pass
  regardless. If `save_progress` itself fails, `wins` is already correct
  in memory and gets persisted by the next `match_start_prompt` write (`:1877`).
- **`stuck_count`:** `= 0` at `:1815`, `+= 1` in the handler → 1, and the
  suppression branch keeps incrementing on later polls, so
  `MAX_STUCK_ATTEMPTS` still trips. Coherent.

So the placement is the *safe* direction — it trades a possible undercount for
an impossible double-count, which is the right trade for persisted state. The
defect is that the comment describes the opposite behaviour, and the actual
cost (a real win silently not counted, so the run buys one extra $50 match to
reach `target_wins`) is invisible to anyone reading it. `your_score`/`opp_score`
are never type-checked — `validate_game_state()` (`:994-1039`) validates
`screen`, `phase`, `hand` and `collection` only — so a model response with
`"your_score": "3"` raises `TypeError` at `:1822` and lands exactly here.

**Fix.** Correct the comment to say what the code does ("the result is dropped
rather than risk a double count — `acted_screen` is armed before any work that
can raise"), and optionally add `your_score`/`opp_score` int-checks to
`validate_game_state()` for `screen == "result"` so a malformed payload becomes
a retryable read error upstream instead of a dropped win here.

#### N25. The new N14 comment's justification is false on the discard path, which is the one path that really can loop
`orchestrator.py:1987-1992` vs `:1629`, `:2059`

The comment added for N14 says:

> A recurring "turn" screen is the normal steady state … and `play_one_turn()`
> consumes a real card each time, so a repeat is progress, not a stuck screen.

`play_one_turn()` does not always consume a card. On the redraw path it returns
`False, None` (`:1629`) and its own docstring (`:1589-1592`) says so
explicitly: *"False if a card was discarded instead (a redraw doesn't use up a
turn — the same slot gets played for real on the next poll)"*. And
`stuck_count = 0` at `:2059` sits **outside** `if played:` (`:2009`), at the
same indentation, so it runs on the discard path too.

Concretely: a weak hand (`max(power) <= 4`) with `discards_left` reported as
non-zero satisfies `should_redraw()` (`decision_engine.py:150-161`). If
`select_and_discard()`'s presses don't land, the next poll sees the identical
hand and the identical `discards_left`, redraws again, and returns
`played=False` again — three keypresses per pass, forever, with
`MAX_STUCK_ATTEMPTS` permanently unreachable because `stuck_count` is zeroed
every pass.
That is precisely the unbounded-live-input shape the comment argues cannot
occur, and it is the only branch left without a bound.

Still Minor — the presses go into a card-select UI, not a purchase, and it
needs a genuinely stuck turn screen to trigger. But the round-3 response was to
document *why the bound isn't needed*, and the documented reason does not hold.

**Fix.** Either move `stuck_count = 0` inside `if played:` (a discard then a
play gives `1 → 0`, so normal play is unaffected and only a non-advancing
discard accumulates), or narrow the comment to say the reset is justified only
when `played` is True and that the discard path is knowingly unbounded.

---

## 4. Explicitly checked and NOT a problem

- **The `id()` ban check has no false positives.** `PlayerCard` is a plain
  mutable `@dataclass` (`decision_engine.py:29-34`), and all 33
  `KNOWN_BAN_ROSTER` entries are separate literals, so distinct positions hold
  distinct objects. `read_full_ban_collection()` dedupes by absolute `(row, col)`
  via `seen_positions` (`:1444-1446`, `:1485-1487`), so the row-1 overlap
  between scan batches cannot put the same object into `grid` twice either. The
  only way to get a duplicate object is the mis-resolved-OCR alias the guard was
  written for. Two genuinely identical physical cards at two positions would
  still be two distinct `PlayerCard` objects and would pass.
- **The identity guard cannot become a permanent hard stop via the learned
  roster — but only because N9 blocks it.** If an alias were ever persisted,
  `KNOWN_BAN_ROSTER` would hold one object at two positions on every subsequent
  run and the guard would raise on every ban screen forever, with an error
  message that never mentions `known_ban_roster_learned.json`. It cannot happen
  today: `_learn_roster_entry()` needs two agreeing reads of the same position
  (`:1210-1217`), and the scan's visible rows are `[0,1] [1,2] [3,4] [5,6] [7,8]`
  (`top_row = max(0, presses_so_far - 1)`, `:1402`, stepping by 2), so the only
  uncatalogued positions — (6,3)/(6,4) — are seen exactly once per run. Worth
  remembering if N9 is ever "fixed".
- **The ban-position mapping's first-match-wins ordering is currently safe.**
  With an aliased object at two positions and only one copy in `bans`, the loop
  at `:1923-1928` takes whichever position appears first in `grid`. Aliases can
  only arise at positions missing from `KNOWN_BAN_ROSTER` — i.e. (6,3)/(6,4) and
  beyond — which are always scanned *after* the true card's position, so the
  correct physical card wins. This is an emergent property of the scan order,
  not an enforced one; a future roster gap in an early row would break it.
- **`load_progress()` raising breaks no caller.** One call site (`:1695`), no
  test or other module references it. The fresh-file path still returns
  `(0, 0, 0, None)` and `:1696` handles `balance is None`.
- **The `finally` still covers every exit.** AST-verified again after the N12
  change: one `Try`+`finally` in `run()`, no `return`s, one `.set()`, and the
  new `break` at `:1847` is bound to the `while` at `:1730`.
- **`_prune_screenshot_log()` still cannot eat the fixtures.** It only lists
  `SCREENSHOT_LOG_DIR` (`:637`); all three fixtures live in `test_fixtures/`,
  which both OCR tests read (`test_ocr_ban_card.py:27`,
  `test_ban_grid_locked.py:24`).
- **N4's failure throttle is correct.** `failures` is its own counter, reset on
  success at `:662`, and `failures == 1 or failures % 100 == 0` (`:672`)
  guarantees the first failure prints.
- **The N2 guard is intact.** `:1785` still excludes `"other"`, so
  `result -> other -> result` and `prompt -> other -> prompt` cannot re-arm.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| Important | 0 |
| Minor | 3 |

Round-3 status: **5 FIXED** (N15, the stale I2 comment, `_learn_roster_entry`,
`load_progress`, the logger-start move), **1 FIXED-but-with-a-false-rationale**
(N14 → N25), **1 PARTIAL** (N12 — the scoring is wrapped, `press("close_result")`
still is not), **1 NOT FIXED from the claimed set** (`_load_learned_roster()`'s
wrong-shape JSON, the second bullet of N18). N17, N20, N21 and N22 were not
claimed and are unchanged. Nothing regressed. All seven tests pass, and the new
`test_ban_grid_locked.py`'s ground truth is independently confirmed correct.

**Nothing blocking — safe to stop iterating.** The one path that could send
wrong physical input into a $50 match is now closed at three independent
layers: `ocr_ban_card_name()` abstains rather than guessing, bans are selected
by `(row, col)` position rather than by name, and the identity check catches a
duplicated object before any keypress. I could not construct a reachable
mis-ban against the current code.

If one more thing gets touched, make it **N23** — not because it is dangerous
today, but because it is the only finding that could *undo* work already done:
the geometry separation that closed N6 is currently protected by a comment and
by a test that does not actually cover the direction a maintainer is most
likely to change. A two-line assertion in `test_ocr_ban_card.py` makes that
protection real. N24 and N25 are both comments that describe behaviour the code
does not have, which is the specific failure mode this review loop has now hit
three rounds running — worth correcting, not worth another round.
