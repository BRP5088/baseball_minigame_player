> **CORRECTION 2026-09-16:** anything below about `select_and_discard` ending in `confirm_play` (Triangle) is STALE. That press has been REMOVED -- a discard does not use the turn, and Triangle there played whatever was still lifted whenever the Square press was dropped. See RULES.md and input_controller.select_and_discard.

# Test Suite Audit — where the green comes from

Audited 2026-08-25 against the 11 `test_*.py` files, all passing (`./run_tests.sh`,
81s wall, all green). No project file was modified. Nothing touching the PS5 was run.

**Method.** Every claim marked "measured" below comes from running the *unmodified*
test file in a private process after monkey-patching the thing it guards — a mutation
test. If the test still prints OK, it does not guard that thing. Harness lived in the
scratchpad; `orchestrator.py`, `input_controller.py` and the test files were never
touched on disk.

**Note:** `orchestrator.py` and `test_settle_regions.py` were edited by someone else at
13:16 while this audit was running (the `REVEAL_EDGE_THRESHOLD` 0.070 → 0.065 fix).
Line numbers below are against the 13:16 state, and every mutation result was re-run
against it. That edit is itself the sharpest evidence in this report — see §1.0.

## Verdict

The suite is **not** uniformly weak. Four files (`test_roster_matching.py`,
`test_ban_grid_locked.py`, `test_validate_game_state.py`, and most of
`test_state_io.py`) fail correctly when their subject breaks — verified, not assumed.

But three of the files carry docstrings claiming to guard invariants they demonstrably
do not, and one of those gaps is the exact regression that cost real money in
QA_FINDINGS_R2 N1. The geometry tests in particular assert *shape*, never *content*:
every gameplay crop can be pointed at the wrong part of the screen and the suite stays
green. And the two highest-money code paths — `run()`'s screen state machine and
`input_controller`'s key sequences — have no tests at all despite being pure, ordinary,
offline-testable logic.

---

## 1. Tests that would NOT catch their own regression

Ranked by what the miss costs on a live run.

### 1.0 The proof this is not hypothetical — it happened during the audit

At 13:16, mid-audit, someone changed `REVEAL_EDGE_THRESHOLD` from 0.070 to 0.065
(`orchestrator.py:1208`) because 0.070 sits above the mss capture path's present-minimum
of 0.0692, so on that path "the weakest genuine reveal never fired — silently".

`test_settle_regions.py` had been asserting `0.0624 < REVEAL_EDGE_THRESHOLD < 0.0775`.
**0.070 satisfied that. The suite was green for the entire life of the bug.**

The mechanism is exactly the pattern this report is about: the test pinned the constant
inside a band measured on *one* of the two capture paths, and called that "the measured
gap". It encoded the number, not the property ("the threshold must separate present from
absent on every path `_fast_grab()` can take"). The corrected version at
`test_settle_regions.py:115` is better — it uses the intersection of both paths — but it
is still a hard-coded band, so it will go stale again the next time a capture path,
display scale, or `SETTLE_CALIBRATION_WIDTH` changes.

The durable version computes the property instead of asserting a remembered number:
measure `_center_card_edge_fraction()` on saved present/absent fixture crops resampled
through both paths, and assert the threshold falls between the observed maxima and minima.
Everything else in §1 is the same failure mode caught before it cost anything.

### 1.1 CRITICAL — the N1 mis-ban fix is unguarded by the whole suite

`orchestrator.py:533` is the N1 fix:

```python
return match_roster_name(cleaned, cutoff=0.85, allow_surname_fallback=False)
```

Deleting those two kwargs is a one-line, plausible "cleanup". It reinstates the
Critical from QA_FINDINGS_R2 N1: an uncatalogued grid position gets force-matched onto
the nearest known name, fills `roster_hits`, suppresses the vision read that would have
corrected it, and toggles the wrong physical card in a $50 match.

**Measured.** I wrapped `match_roster_name` so that *only* calls originating inside
`ocr_ban_card_name` lose their strict arguments — the function itself untouched, which
is exactly what that one-line edit does:

```
callsite_loose_only / test_ocr_ban_card.py   -> PASS  ("18/18 resolved correctly, 0 abstained, 0 wrong")
callsite_loose_only / test_roster_matching.py -> PASS
```

Both tests pass. Worse, `test_ocr_ban_card.py` scores **better** under the regression
(18/18, zero abstentions) than it does correctly configured (16/18, two abstentions) —
so the metric the test prints actively rewards reintroducing the bug.

Why each misses it:

- `test_roster_matching.py:31` hard-codes its own strictness
  (`STRICT = dict(cutoff=0.85, allow_surname_fallback=False)`) and passes it explicitly.
  It tests that `match_roster_name` *can* be strict, never that the ban path *asks* it to be.
- `test_ocr_ban_card.py` fixtures (lines 45-64) are all 18 real roster members. A loose
  cutoff still resolves a roster member correctly, so the "never WRONG" property is never
  actually exercised against the input class it exists for — an uncatalogued position.

**Fix (concrete).** Add to `test_ocr_ban_card.py`, asserting the call site rather than
the function:

```python
# The N1 fix lives at the CALL SITE, not in match_roster_name.
import inspect, orchestrator
src = inspect.getsource(orchestrator.ocr_ban_card_name)
assert "cutoff=0.85" in src and "allow_surname_fallback=False" in src, (
    "ocr_ban_card_name() no longer resolves STRICTLY — see QA_FINDINGS_R2 N1")

# Behavioural half: a card at a position NOT in KNOWN_BAN_ROSTER must abstain.
# (6,3)/(6,4) are the real uncatalogued positions.
for probe in ["Frank Coker", "Nate Kelly", "Bobby Sharp"]:
    assert orchestrator.match_roster_name(
        probe, cutoff=0.85, allow_surname_fallback=False) is None
```

The source check is crude but it is the only thing that pins a *call site*, and this
call site is the one place in the project that sends wrong physical input into a paid loop.

### 1.2 HIGH — `test_gameplay_regions.py` cannot tell a correct crop from a wrong one

The five `GAMEPLAY_REGIONS_FRAC` crops are live path: `capture_state_images_b64`
(`orchestrator.py:830`) sends them to the vision model every single turn. If the `hand`
box is wrong, vision reads the wrong cards and the wrong card gets played.

The test asserts only (`test_gameplay_regions.py:18-33`): labels match the dict keys,
each crop is non-zero, and the crops total under half the full frame's JPEG bytes.

**Measured**, all against the unmodified test:

| mutation | result |
|---|---|
| every region collapsed to a `(0,0,0.01,0.01)` corner box | **PASS** — "5 regions cropped correctly … 1%" |
| every region shifted 30% right (same size, wrong content) | **PASS** — "…31%" |
| `hand` shrunk to a 1%×1% sliver containing no cards | **PASS** — "…22%" |

The byte-size assertion at line 31 is *inverted* as a safety net: making the crops
smaller and more wrong makes the assertion pass more comfortably.

`test_image_pipeline.py:54-62` has the same blind spot (non-zero, in-bounds only). It
does catch `all_regions_tiny`, but only incidentally — via the scoreboard OCR cases, not
via the geometry check. The `hand` sliver passes there too.

**Fix.** Assert content, not shape. The cheapest real check: OCR the `hand` crop of a
fixture and require at least one known card name or power digit; or, cheaper and
deterministic, assert the hand crop's ink — a correct hand crop on
`test_fixtures/20260824_201103_128.jpg` has substantial high-gradient area, a sliver or
an off-target box does not. Even a pinned-geometry tripwire
(`assert GAMEPLAY_REGIONS_FRAC["hand"] == (0.250, 0.716, 0.760, 1.000)`, with the
LOCAL_VISION_EXPERIMENTS §21 measurement in the message) beats what is there now, because
today *any* value passes.

### 1.3 HIGH — `test_settle_regions.py` asserts the symptom, not the invariant

You asked about this one specifically. The answer is: it asserts the symptom.

The test never calls `wait_for_screen_to_settle`. It only inspects constants.

**Measured**, all PASS on the unmodified test:

| mutation | result |
|---|---|
| `wait_for_screen_to_settle` replaced with `lambda *a, **k: 0.0` (waits for nothing, ever) | **PASS** |
| `regions=` argument silently dropped, so every caller falls back to `default` | **PASS** |
| `SETTLE_THRESHOLDS["hand"] = 10_000.0` (hand motion can never register) | **PASS** |
| `GAMEPLAY_REGIONS_FRAC["hand"]` shrunk to a sliver away from the cards | **PASS** |

To its credit it *does* catch the literal original bug — setting
`SETTLE_REGION_SETS["turn"] = ("legacy_roi",)` fails correctly with the intended message.
But the invariant is "the loop does not read a hand that is still animating", and the
test's grip on that is: one membership check on a tuple.

Two specific holes worth closing, both one-liners:

- **Line 40 is one-sided.** `if SETTLE_THRESHOLDS.get("hand", 0) < 7.0` has a floor and
  no ceiling. `hand: 10000.0` passes. Real thresholds live between an idle p95 of 7.63
  and a "real motion" peak of 56.2, so:
  `assert 7.0 <= SETTLE_THRESHOLDS["hand"] <= 20.0`.
- **Nothing pins the call site.** `orchestrator.py:2395` is
  `wait_for_screen_to_settle(max_wait=8.0, regions="turn")` and deleting `regions="turn"`
  is invisible to the suite. Same `inspect.getsource` trick as 1.1, or better: call
  `wait_for_screen_to_settle` with `_grab_settle_regions` patched to a recorder and assert
  it sampled `hand` — that converts the test from a constant check into a behaviour check
  without any screen capture.

### 1.4 MEDIUM — `test_known_ban_roster.py`'s "short-circuit logic" section is a tautology

Lines 18-26 claim to test the roster-hit short-circuit. They re-implement the dict
comprehension from `read_full_ban_collection` inside the test and then assert the
re-implementation behaves as written:

```python
roster_hits = {pos: KNOWN_BAN_ROSTER[pos] for pos in known_batch if pos in KNOWN_BAN_ROSTER}
assert len(roster_hits) == len(known_batch)
```

This asserts that `(0,0)`, `(0,1)`, `(0,2)` are keys in a dict. It cannot observe
`orchestrator` at all.

**Measured.** Replacing `read_full_ban_collection` with `lambda *a, **k: []` — the
function gutted entirely — leaves the test printing
"OK: KNOWN_BAN_ROSTER self-check passed (33+ entries, short-circuit logic, two-read learning)".

The rest of the file (the two-read learning round-trip, lines 29-66) is genuinely good and
exercises real `orchestrator` code. Only the middle section is theatre. Either delete
lines 18-26 or replace them with a real call to `read_full_ban_collection` under fakes
(see §3.1 — it is testable).

### 1.5 MEDIUM — the atomic-write test does not test atomicity

`test_state_io.py:34-38` is labelled "QA N13: writes must be atomic" and checks that no
`.tmp` file is left behind.

**Measured.** Replacing `_atomic_write_json` with a plain truncating
`open(path, "w"); json.dump(...)` — atomicity completely gone, which is exactly the N13
defect — leaves the test printing
"OK: progress round-trip + atomic write + corrupt-refusal…". A non-atomic write also
leaves no `.tmp` behind, so the assertion is satisfied *more* easily by the broken version.

**Fix.** Test the property, which is "an interrupted write leaves the previous file
intact":

```python
save_progress(9, 9, 9, 999, pf)
import json as _json
real_dump = _json.dump
_json.dump = lambda *a, **k: (_ for _ in ()).throw(IOError("simulated crash mid-write"))
try:
    save_progress(1, 1, 1, 1, pf)
except IOError:
    pass
finally:
    _json.dump = real_dump
if load_progress(pf) != (9, 9, 9, 999):
    failures.append("an interrupted write corrupted the previous progress record")
```

That fails on the plain-write version and passes on the shipped one.

### 1.6 MEDIUM — `test_image_pipeline.py`'s masking section never checks *which* pixels get blanked

Lines 64-97 assert: the frame size is unchanged, between 1% and 90% of pixels went black,
nothing got brighter, and a second pass adds under 5%.

**Measured.** Replacing `mask_low_contrast_regions` with a function that ignores contrast
entirely and paints a fixed black bar over the top 5% of the frame — so no locked card is
masked at all, which is the whole failure class the function exists to remove — leaves the
test printing "OK: … masking blanked 11.1% and is idempotent". Shifting
`MASK_CONTRAST_THRESHOLD` from 100.0 to 130.0 also passes (69.1% blanked).

The 1%–90% band is ~89 percentage points wide around a real value of 61.5%. Nothing in
that range is diagnostic.

**Fix — and the numbers are already available.** The locked cells are known ground truth
from `test_ban_grid_locked.py`. I measured the post-mask black fraction of every cell:

```
20260824_200520_984.jpg   locked (0,2) 0.858  (1,0) 0.599  (1,1) 0.733
                          unlocked: 0.357 0.345 0.250 0.351 0.335 0.052 0.053
20260824_200601_124.jpg   locked (0,2) 0.858  (1,2) 0.809
                          unlocked: 0.255 0.264 0.205 0.254 0.051 0.157 0.072 0.049
```

Clean separation on both frames. Assert it scale-free rather than with a magic constant:

```python
for fname, locked in KNOWN_LOCKED.items():          # reuse test_ban_grid_locked's table
    masked = mask_low_contrast_regions(Image.open(os.path.join(FIX, fname)))
    black = {}
    for r in range(2):
        for c in range(5):
            a = np.asarray(get_ban_grid_card_crop(masked, r, c).convert("L"))
            black[(r, c)] = float((a == 0).mean())
    lo = min(black[p] for p in locked)
    hi = max(v for p, v in black.items() if p not in locked)
    if lo <= hi:
        failures.append(f"{fname}: masking does not separate locked ({lo:.3f}) "
                        f"from legible ({hi:.3f}) cells")
```

That fails on the contrast-blind mutation and on a threshold shift large enough to matter,
while tolerating frame-to-frame variation.

### 1.7 LOW — `test_ban_grid_locked.py` overclaims in its docstring

Lines 9-11 say the test "is what makes an accidental 'unification' of those two fail
loudly". Half true, and worth knowing which half:

- Reading the row fractions as **height** instead of width (the confusion every docstring
  in that area warns about) — **correctly FAILS**, with a clear diff. Good.
- `detect_ban_grid_locked` stubbed to "everything unlocked" — **correctly FAILS**. Good.
- Setting `BAN_GRID_ROW_Y_FRAC = [(0.195, 0.478), (0.478, 0.761)]`, i.e. copying the card-crop
  pitch into the lock-detection constant while still reading it as width — **PASSES**.

So the constant's *value* can be unified with the card-crop geometry undetected; only the
width-vs-height *reading* is guarded. Either narrow the docstring claim or add
`assert BAN_GRID_ROW_Y_FRAC == [(0.195, 0.385), (0.395, 0.585)]` alongside the existing
`MASK_CONTRAST_THRESHOLD == 100.0` tripwire at line 63 — the file already uses that pattern.

### 1.8 LOW — `test_validate_game_state.py` does not test the docstring's actual claim

`validate_game_state`'s docstring (`orchestrator.py:1242-1249`) promises to raise
`ValueError` on any read "that would otherwise crash deeper in the pipeline
(hand_to_cards, play_one_turn) with a confusing IndexError/KeyError/TypeError". The test
only probes screen/phase/hand-shape.

**Measured** (with all input functions replaced by recorders):

| state | `validate_game_state` | `play_one_turn` |
|---|---|---|
| `{"screen":"turn","phase":"batting","hand":[<one valid player card>]}` | PASS | **KeyError: 'runners'** |
| valid turn whose hand is tactics-only | PASS | **IndexError: list index out of range** |

Both are precisely the class the validator exists to convert. A tactics-only hand is not
exotic — it is what a mid-deal or partially-legible frame produces, i.e. the same failure
mode the settle work exists to prevent. Consequence is bounded (`run()`'s turn
`try/except` retries, and 15 in a row stops the loop), so this is a robustness gap, not a
money gap — but the test currently certifies a guarantee the function does not provide.

**Fix.** Add `runners`, `your_score`, `opp_score` presence checks and a "hand contains at
least one player card" check to the *function*, and add both rows above to `bad_cases`
(lines 18-34).

---

## 2. Weak assertions worth tightening

Beyond the replacements already given in §1:

**`test_ocr_ban_card.py:87` — is `MAX_ABSTENTIONS = 2` reasonable?**
Yes in the degradation direction, no in the safety direction. Measured sensitivity, all
against the real fixtures:

| perturbation | abstentions | verdict |
|---|---|---|
| shipped | 2 / 18 | at the limit, zero headroom |
| `BAN_CARD_ROW_TOP_FRAC` +0.010 (≈13 px) | 3 | **FAIL** |
| +0.020 | 4 | **FAIL** |
| +0.030 | 7 | **FAIL** |
| −0.020 | 2 | pass (asymmetric margin, as the N6 comment intends) |
| `BAN_CARD_NAME_STRIP_FRAC` back to the old (0.82, 0.96) | 14 | **FAIL** |

So the bound is tight, not loose: a 1% downward crop drift already trips it. It does not
mask degradation. The real problem is that the metric is **one-sided** — *fewer*
abstentions is silently treated as better, and as §1.1 shows, zero abstentions is what
the dangerous regression produces. Add the lower bound with a comment explaining why:

```python
assert 1 <= len(abstained) <= MAX_ABSTENTIONS, (
    f"{len(abstained)} abstentions. Zero is not an improvement: these two cards "
    "abstain because resolution is STRICT (N1). Zero abstentions means the strict "
    "cutoff was lost — measured: reverting it scores 18/18 here while reinstating "
    "the wrong-card ban.")
```

**`test_ocr_ban_card.py:36-38` is a tautology.** `BAN_CARD_ROW_TOP_FRAC[0]` and
`BAN_GRID_ROW_Y_FRAC[0][0]` are both `0.195`, so the first clause of the `or` is always
False and the assertion degenerates to `_pitch > 0.25` — already implied by the assert
three lines above. It reads like two independent checks and is one.

**`test_state_io.py:97-113` — `extract_json` is certified for a property it lacks.**
The docstring at `orchestrator.py:334-338` claims the regex is "tolerant … regardless of
what surrounds it". `re.search(r"\{.*\}", ..., DOTALL)` is greedy, so any brace *outside*
the JSON breaks it. Measured:

```
'The hand {5 cards} is:\n```json\n{"a": 1}\n```'  -> JSONDecodeError
'```json\n{"a": 1}\n```\nNote: {done}'            -> JSONDecodeError
'{"a": 1}\n{"b": 2}'                              -> JSONDecodeError
```

The four happy cases at lines 97-102 all use brace-free prose, so they confirm the fix
for the exact string that motivated it and nothing more. Either add those three as
expected-to-work cases and make the extractor brace-balancing, or add them as
*documented* known limitations so the next reader does not trust the docstring. Impact is
bounded (retry, then `MAX_STUCK_ATTEMPTS` halts the run) but it is a silent-halt path.

**`test_gameplay_regions.py:31`** — the `crop_bytes < full_bytes * 0.5` check is a
token-cost guard dressed as a correctness check. Keep it, but label it as a cost budget
and add the content check from §1.2; on its own it rewards being more wrong.

---

## 3. Coverage gaps, ranked by live-run risk

Ranking is by "what does a regression here cost during a real $50/match session", not by
line count.

### 3.1 `run()`'s screen state machine — HIGHEST RISK, and fully testable offline

`orchestrator.py:1935-2399`. Zero tests. It holds every irreversible action in the
project and every guard written in response to a QA finding:

- C1: double-scoring a `result` screen permanently corrupts `progress.json`, possibly past
  `target_wins`.
- C2: double-debiting `match_start_prompt` silently defeats `max_spend`.
- C3/N11: re-entering the ban screen un-bans what was just banned.
- N2: `"other"` must NOT re-arm `acted_screen` — this is what stopped `result → other →
  result` double-scoring.
- N25: `stuck_count` resets only on a confirmed play, never on a discard.

Every one of these is a pure function of a *sequence of screen dicts*. The loop's only
external dependencies are `read_game_state()`, `press()`, `wait_for_screen_to_settle()`,
`play_one_turn()` and `save_progress()` — all module-level names, all patchable. A test
that feeds a scripted screen sequence and asserts on the resulting `progress.json` and
press log needs no game, no API key, no screenshots. Concretely:

```python
SCREENS = ["result", "result", "other", "result", "match_start_prompt",
           "match_start_prompt", "other", "match_start_prompt"]
# expect: exactly 1 win scored, exactly 1 x $50 debited
```

Today nothing would notice if the `and screen != "other"` clause at `orchestrator.py:2068`
were dropped — the N2 fix reverted, double-scoring restored.

### 3.2 `input_controller.py` — HIGH RISK, trivially testable, currently 0%

Every function is deterministic given its arguments and emits an ordered list of logical
actions. I verified this offline (with `press`, `pyautogui` and `subprocess` all replaced
by recorders, so no key could reach the machine):

```
select_and_play(1, 4)  -> [L,L,L,L, R, select, R,R,R, select, confirm_play]
select_and_discard(3)  -> [L,L,L,L, R,R,R, select, confirm_discard, confirm_play]
bans {(0,1),(3,4),(6,0)} ->
   [R, select, D,D,D, R,R,R, select, D,D,D, L,L,L,L, select, U×6, confirm_play, confirm_play]
duplicate-name grid, ban only (0,1) -> [R, select, confirm_play, confirm_play]
missing position -> ValueError("ban positions not all present in grid…")
```

Four load-bearing, live-verified invariants are sitting there unguarded:

1. **N1** — bans are selected by `(row, col)`, never by name. The duplicate-name probe
   above shows one toggle for one intended ban; the pre-fix behaviour was 4 toggles for 3
   bans. Nothing currently pins that.
2. **M11** — exactly *two* trailing `confirm_play` presses. `input_controller.py:193-199`
   explicitly says "Do not 'clean up' to a single press without live-testing it" — a
   comment is the entire defence today.
3. **Row-order-only navigation** — targets are processed in ascending row and the cursor
   never moves back up mid-selection, then unwinds `current_row` presses at the end.
4. **`reset_hand_cursor` normalisation** — `MAX_HAND_SIZE - 1` left presses before any
   navigation, because the game does not reset the cursor between turns.

A ~40-line test with a fake `press` locks all four. This is the best effort/value ratio in
the project.

### 3.3 `read_full_ban_collection()` — HIGH RISK, partially testable

`orchestrator.py:1620-1793`. The `zip(expected_positions, cards)` at line 1747 is the step
that assigns a card to a grid position; getting it wrong navigates to and toggles the wrong
physical card. Its guards (count-mismatch → discard the whole batch; two retries;
`consecutive_mismatches >= 2` → stop) are all untested. With `capture_screenshot_image`,
`read_ban_row_cards`, `press` and `wait_for_screen_to_settle` faked, the batching, the
`top_row = max(0, presses_so_far - 1)` scroll arithmetic, and the dedupe by absolute
position are all checkable against a real fixture image.

### 3.4 `decision_engine.py` — MEDIUM RISK, 0% coverage, pure functions

No `test_*.py` file imports it for its own sake, and `run_tests.sh:5` globs `test_*.py`
only — so the two asserts in `decision_engine.py:199` and `:207` **never run**. Every card
played and every card banned goes through `best_batting_play` / `best_pitching_play` /
`should_redraw` / `choose_bans`, and they are the cheapest possible things to test (no I/O,
no images). Notable untested edges: `choose_bans` returns fewer than `count` on a short
collection (only `run()`'s `len(bans) != 3` check catches it), and `should_redraw` uses
`max(...)` on `hand_players`, which raises on an empty list.

### 3.5 `play_one_turn()` — MEDIUM RISK

Testable today with `select_and_play`/`select_and_discard` replaced by recorders (verified
— see the table in §1.8). The invariant worth pinning is the one `test_state_io.py:128-129`
gestures at but does not reach: *the pressed index is the `hand_index` of the card the
decision engine chose*. That mapping is what `select_and_play` presses against; a
one-position slip plays a different card every turn, silently.

### 3.6 Not worth covering

`ocr_runner_card` and `ocr_scoreboard` are **diagnostic-only** — their sole caller is
`log_local_read_comparison` (`orchestrator.py:868, 874`), which runs only under
`compare_local_reads=True` (off by default) and feeds no decision. They currently have
7 scoreboard frames and 4 runner cases across `test_ocr_scoreboard.py`,
`test_ocr_runner.py` and `test_image_pipeline.py:31-48`. That is more coverage than
`decision_engine.py`, `input_controller.py` and `run()` have combined. Not an argument for
deleting them — they are cheap and they will matter when the local read is promoted — but
worth knowing that ~3 of the 11 files guard code that cannot affect a live match.

---

## 4. Brittleness / false-alarm risks

**`test_known_ban_roster.py:14` will fail on a legitimate live session.**
`assert 0 <= row <= 6` bounds *learned* data. `KNOWN_BAN_ROSTER` currently spans rows 0-6
with row 6 only partly filled (cols 0, 1, 2), and `read_full_ban_collection` scrolls up to
`max_presses=40`, so absolute rows well past 6 are reachable by design. The moment a real
run discovers a row-7 card and `_learn_roster_entry` persists it to
`known_ban_roster_learned.json` (which does not exist yet), the suite goes red for a
non-bug. Change to `0 <= row <= 40 and 0 <= col <= 4`, or drop the upper row bound entirely.

**`test_validate_game_state.py:3` is the only test that does not guard its own API key.**
The other ten do `os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", ...)` before importing
`orchestrator`; this one imports at line 3 with no guard. Verified: run it without the
variable set and it dies with `KeyError: 'PERSONAL_ANTHROPIC_API_KEY'` from
`orchestrator.py:54`. `run_tests.sh:7` masks this, so it only bites someone running the
file directly. One-line fix.

**Three tests depend on `Photos to train on/`, which is not a fixture directory.**
`test_gameplay_regions.py:12-13`, `test_ocr_scoreboard.py:10`, `test_ocr_runner.py:11` all
do `next(f for f in os.listdir(SRC_DIR) if "9.49" in f)`. Two failure modes:
(a) if the photo is renamed or cleaned up, the test dies with a bare `StopIteration`, not a
useful message; (b) `"9.49"` is a substring match over `os.listdir` in arbitrary order — it
happens to be unique today (checked: 1 match each for "9.49", "9.46", "9.32"), but adding a
second screenshot from that minute silently changes which file is tested. `test_fixtures/`
exists precisely for this and both `test_ocr_ban_card.py:40-43` and
`test_image_pipeline.py:9-12` explain why (the N10 pruner). These three predate that move
and should follow it.

**`screenshot_log/` pruning:** checked — no test reads from it. That hazard is genuinely
closed. `SCREENSHOT_LOG_MAX_FILES = 20000` vs 1,811 files present; the fixtures are safely
in `test_fixtures/`.

**`test_known_ban_roster.py:31` writes into the project directory.**
`test_learned_roster_scratch.json` is created in the repo root rather than a temp dir. The
`finally` at lines 62-66 cleans it up, but a hard kill mid-test leaves a stray file. Minor;
`test_state_io.py:22` already does the right thing with `tempfile.mkdtemp`.

**OCR nondeterminism:** not a real risk here. Tesseract is deterministic for identical
input, and the abstention count reproduced exactly across every run. The exposure is a
*tesseract version upgrade*, which would shift the 2/18 abstention count with zero headroom
(§2). Worth a comment in the file recording the tesseract version the 2 was measured against.

**Runtime:** 81 s for 11 files, dominated by the tesseract passes in `test_ocr_ban_card.py`
and `test_image_pipeline.py`'s `MaxFilter(41)`. Tolerable, but it is enough friction that
people will skip it — a reason to keep the fast, pure-logic tests recommended above
separable from the image ones.

---

## 5. Tests that are genuinely solid — leave these alone

Verified by mutation, not assumed:

- **`test_roster_matching.py`** — the strongest file in the suite. It tests real behaviour
  with real captured OCR garble, encodes the asymmetry (strict refuses / loose recovers)
  deliberately, covers the N7 ambiguous-surname collision and degenerate input, and its
  comment at lines 84-93 honestly documents the *scope limit* of the N7 guard rather than
  overstating it. Mutation: dropping strict mode from `match_roster_name` produces 12
  failures with precise messages. Its one blind spot is that it cannot see call sites (§1.1)
  — that is not a flaw in this file, it is a missing test elsewhere.
- **`test_ban_grid_locked.py`** — real fixtures, exact 2×5 ground truth, catches both the
  width/height misread and a stubbed detector, plus a deliberate tripwire on
  `MASK_CONTRAST_THRESHOLD`. Only the docstring overclaims (§1.7).
- **`test_state_io.py`, lines 54-92** (the malformed learned-roster section) — seven
  malformed shapes, and crucially it re-runs the *downstream* `ROSTER_BY_NAME` `.lower()`
  at line 78 rather than only the loader, which is where the N26 breakage actually
  surfaced. Mutation: removing the `isinstance(name, str)` guard fails with exactly the two
  expected messages. This is what a bug-derived regression test should look like.
- **`test_validate_game_state.py`** — ten bad cases against the real function, each mapped
  to a concrete downstream crash. Under-scoped versus its docstring (§1.8) but everything it
  does assert, it asserts honestly.
- **`test_known_ban_roster.py`, lines 29-66** (the two-read learning round-trip) — exercises
  real `_learn_roster_entry` behaviour including the disagreeing-second-read case and the
  M7 `ROSTER_BY_NAME` refresh, with proper cleanup. Only lines 18-26 are hollow.
- **`test_ocr_ban_card.py`'s row-pitch assertion** (lines 31-35) — a genuine, measured
  tripwire on the N6 geometry, and the N23 comment above it is the most valuable paragraph
  in the suite: it records that the *pass rate went up* when the bug was reintroduced. That
  insight is correct and, as §1.1 shows, still applies to a regression the file cannot see.

---

## The one test most worth adding

**A `run()` state-machine test driven by a scripted screen sequence, with `read_game_state`,
`press`, `play_one_turn`, `wait_for_screen_to_settle` and `read_full_ban_collection` faked.**

Invariant: *one irreversible action per screen occurrence, and a `"other"` misread between
two identical screens is not a new occurrence.* Feed
`["result", "result", "other", "result", "match_start_prompt", "match_start_prompt",
"other", "match_start_prompt"]` and assert exactly one win is written to `progress.json`
and exactly one $50 debit lands.

Why this one: it is the only untested code that can *permanently corrupt persisted state or
spend real money*, every guard in it (C1, C2, C3, N2, N11, N25) was written in response to
a QA finding rather than a hypothetical, it needs no game/API/screenshots, and today
reverting any one of those guards leaves the suite fully green.

Second choice, and nearly as valuable for a tenth of the effort: the `input_controller` key-sequence
test in §3.2 — the fake-`press` harness already works, and it pins the N1 position-based
selection and the M11 double-confirm that currently rest on comments alone.

## The one existing test most worth strengthening

**`test_ocr_ban_card.py`.** It guards the highest-consequence path in the project (a wrong
ban = wrong physical card in a paid match) and it is the file that most actively misleads:
under the regression that reinstates QA_FINDINGS_R2 N1, it prints a *better* score than it
does when the code is correct.

Three changes, all small:
1. Pin the call site's strictness (§1.1) — this is the actual fix.
2. Make `MAX_ABSTENTIONS` two-sided: `1 <= len(abstained) <= 2`, with the reason in the
   message (§2).
3. Delete or repair the tautological assertion at lines 36-38.

After that it guards the property its own docstring claims — "this must never return the
WRONG card" — rather than the property it currently measures, which is "these 18 known
cards still read correctly".
