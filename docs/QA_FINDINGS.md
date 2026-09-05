# QA Findings — Auto Baseball

Review date: 2026-08-24/25. Scope: `hand_digit_reader.py`, `orchestrator.py`,
`harvest_hands.py`, `hand_card_matcher.py`, `input_controller.py`,
`decision_engine.py`. No files were modified other than this one. Nothing was
run that sends input to the PS5.

Confidence is called out per finding. Where I checked something and it turned
out **not** to be a bug, I say so, so it doesn't get "re-found" later.

---

## Critical

### C1. A result screen that doesn't dismiss double-counts wins/losses and corrupts `progress.json`
`orchestrator.py:1580-1609`

The `screen == "result"` branch increments `wins`/`losses`/`draws`, writes
`progress.json`, presses `close_result`, and `continue`s. There is **no
idempotency guard** — no "already scored this result" flag, no requirement that
the screen change before scoring again. If `press("close_result")` is dropped
(a real, documented failure mode: `input_controller.py:57` calls `ACTION_DELAY`
"a starting guess, not a measured value", and `capture_screenshot_image`'s
docstring at `orchestrator.py:520-527` describes live focus races) or the result
overlay outlives `wait_for_screen_to_settle(max_wait=4.0)`, the very next poll
reads `screen == "result"` again and scores the **same match a second time**.

Note `stuck_count = 0` on line 1581, so the stuck-detector cannot break this out;
it will spin as fast as the poll loop allows, each pass writing a higher win
count. With `run(target_wins=17)` the loop would "reach" the target from a single
stuck result screen and exit with a permanently wrong `progress.json`.

Fix: track the last scored result (e.g. a `result_scored` flag cleared only when
a non-`result` screen is observed, or hash `(your_score, opp_score)` + require a
screen transition) before incrementing anything.

### C2. Same class, with money: `match_start_prompt` debits $50 per poll
`orchestrator.py:1611-1626`

`balance -= 50; spent += 50; save_progress(...)` runs every time a
`match_start_prompt` screen is read, before `press("start_match")`. If the start
press doesn't take (or the prompt lingers past the 4s settle), the next poll
debits another $50 from the tracked balance and the session `max_spend` budget.
`stuck_count` is reset to 0 here too, so nothing bounds it.

This does not spend real currency by itself — it desynchronises the script's
model of the balance from the game's. But the balance is what gates
`if balance < 50: break` and the `max_spend` cap that exists specifically because
"Taylere's real balance is $496, but she only wants $250 of it used"
(`orchestrator.py:1508-1511`). A drifted balance defeats exactly that guard.

Fix: same as C1 — require an observed screen transition before debiting, or
verify the match actually started before committing the debit.

### C3. The ban screen can loop forever, re-toggling bans on and off
`orchestrator.py:1628-1646`

If `select_bans_and_start_full()` returns without raising but the game stays on
the ban screen (wrong number of bans selected, a dropped `confirm_play`, the
cursor-start assumption in `input_controller.py:196-198` not holding), the loop
sets `stuck_count = 0` (line 1644) and `continue`s. Next pass:
`read_full_ban_collection()` returns the **cached** collection (line 1224), so
the identical ban set is re-selected — and since selection is a *toggle*
(`press("select_card")`), the second pass **un-bans** the three cards it banned
on the first. Then re-bans them. Forever, with no `stuck_count` bound.

Two contributing sub-issues in the same path:
- `choose_bans(collection, count=3)` (`decision_engine.py:172`) returns
  `sorted(...)[:3]` with no minimum check. If the collection read came back with
  fewer than 3 cards, fewer than 3 bans get toggled and the game (which shows
  "BANNED CARDS 0/3") will very likely refuse to start — landing exactly in this
  loop.
- `select_bans_and_start_full` matches by **name**
  (`input_controller.py:201`: `if card.name in banned_names`), not by position.
  Any duplicate name in `grid` toggles two physical cards for one intended ban,
  again producing the wrong count. Duplicate names are reachable — see I2.

Fix: increment `stuck_count` when the ban screen is still present on the next
poll; assert `len(bans) == 3` before pressing anything; select by `(row, col)`
identity rather than by name.

### C4. `PADDLE_VENV_PYTHON` defaults to a path under `/private/tmp` tied to one Claude Code session
`hand_digit_reader.py:47-51`

```python
PADDLE_VENV_PYTHON = os.environ.get(
    "PADDLE_VENV_PYTHON",
    "/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/"
    "07c64a48-18b0-43b7-af05-788324bac0fd/scratchpad/paddle_venv/bin/python",
)
```

That venv exists right now (verified), but it lives in a per-session scratchpad
under `/private/tmp`: it will not survive a reboot, macOS tmp reaping, or a new
Claude Code session — the UUID `07c64a48-...` is this session's id. `paddleocr`
is confirmed *not* importable from the main env (Python 3.14), so there is no
fallback.

Once the path goes stale, `subprocess.run` raises `FileNotFoundError` on **every
turn** of a `compare_local_reads=True` run, which (a) is swallowed and printed,
and (b) leaks a temp file each time — see I1. The failure is silent-ish and
permanent rather than loud.

Fix: move the venv into the project (e.g. `./paddle_venv`), default to that, and
fail loudly once at startup if the interpreter is missing rather than per-turn.

---

## Important

### I1. Temp-file leak on the exception path in `log_local_read_comparison()`
`orchestrator.py:801-808`

```python
try:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        crops["hand"].save(tf.name)
        local_cards = group_into_cards(read_hand_digits(tf.name))
    os.unlink(tf.name)
except Exception as e:
    ...
```

`delete=False` plus an `os.unlink` that sits **outside** the `with` but **inside**
the `try` means any exception from `read_hand_digits` (missing venv interpreter →
`FileNotFoundError`, worker crash → `RuntimeError`, `subprocess.TimeoutExpired`)
or from `group_into_cards` skips the unlink entirely. Each hand crop is a
~1020x367 PNG, so a long session against a broken venv (see C4) leaves one
several-hundred-KB file per turn in the system temp dir.

Fix: `try: ... finally: os.unlink(tf.name)` around the whole block, or use a
`TemporaryDirectory()` context.

### I2. `BAN_GRID_ROW_Y_FRAC` is read as *width* fractions in one function and *height* fractions in another
`orchestrator.py:410` vs `orchestrator.py:449-451`

`detect_ban_grid_locked()` does `row_y = [(int(w * y0), int(w * y1)) ...]` —
width, matching the deliberate justification at lines 380-386.
`get_ban_grid_card_crop()` does `img.crop((int(w * x0), int(h * y0), int(w * x1),
int(h * (y0 + BAN_GRID_CARD_HEIGHT_FRAC))))` — **height**, for the same constant.

I rendered both box sets over a real ban capture (`screenshot_log/20260824_200601_124.jpg`,
2000x1292). Both currently land on usable regions, which is why
`test_ocr_ban_card.py` passes 18/18 — but they are offset from each other by
roughly half a card row, and they only coexist because of this frame's specific
1.548 aspect ratio. The lock-detector's row-1 box straddles grid rows 2 and 3;
the card-crop's row-1 name strip contains the banner with only a few pixels of
margin at the bottom (which is what `BAN_CARD_NAME_STRIP_FRAC` was widened to
paper over, `orchestrator.py:435-440`). Change the window size or letterbox
thickness and one of the two silently starts sampling the wrong row.

This matters because both feed `_learn_roster_entry()` (see I3): a misaligned
crop OCRs a *different card's* banner, `match_roster_name()` fuzzy-resolves it at
`cutoff=0.5`, and the wrong name/stats get persisted to disk at that position —
which is also how duplicate names get into `grid` and break
`select_bans_and_start_full`'s name matching (C3).

Fix: pick one interpretation for `BAN_GRID_ROW_Y_FRAC`, use it in both functions,
and re-verify `test_ocr_ban_card.py` against the corrected geometry.

### I3. Vision- and OCR-derived roster entries are written to disk permanently with no verification or invalidation
`orchestrator.py:1257-1265`, `1306-1315`, `1075-1083`

Both the local-OCR path and the vision fallback call `_learn_roster_entry(pos,
card)`, which writes `known_ban_roster_learned.json` and is merged into
`KNOWN_BAN_ROSTER` on every future import (`_load_learned_roster()`, line 1086 —
the file does not exist yet, so nothing is currently poisoned). After that,
`roster_hits` short-circuits (line 1245) and the position is **never re-read by
vision again**, on any save, ever.

The only gate on the vision path is a *count* match (`len(attempt_cards) ==
len(expected_positions)`), not a content check. The only gate on the OCR path is
`difflib.get_close_matches(..., cutoff=0.5)` — loose enough that a garbled banner
can resolve to the wrong roster name, and the returned `PlayerCard` then carries
that wrong card's power/secondary. Either way, one bad read becomes permanent
ground truth that drives which physical cards get banned.

This also directly contradicts the stated policy at `orchestrator.py:1017-1020`
("if a future vision fallback ever disagrees with an entry here, trust the vision
read over this table for that run") — the code never gives vision a chance to
disagree.

Fix: at minimum, require two agreeing independent reads before persisting; store
a provenance/confidence field; and provide a way to invalidate. Given the file
doesn't exist yet, this is cheap to fix now.

### I4. Dead CLIP/torch import at the top of `log_local_read_comparison()` gates the whole audit
`orchestrator.py:767`

```python
from hand_card_matcher import match_hand_card, learn_hand_card  # lazy: heavy CLIP/torch
```

Neither name is used anywhere in the function (or anywhere else — grepped). It's
left over from before the rewrite to PaddleOCR. It still pays `open_clip` +
`torch` import cost on first call, and if either package is ever missing or
broken the `ImportError` fires **before** the scoreboard/runner/hand checks run,
so the entire per-turn audit silently degrades to one printed error line. Both
packages happen to be installed here, so this is currently latent.

`run()`'s docstring (`orchestrator.py:1487-1488`) still says the flag "Pulls in
hand_card_matcher's CLIP/torch dependency on first use" — accurate only because
of this dead import.

Fix: delete the import line and the docstring sentence.

### I5. The local/vision hand comparison aligns by list position, not by hand index
`orchestrator.py:810-828`

`vision_hand` is keyed by `hand_index`, but `local_cards[i]` is the *i*-th column
the grouper produced. The documented residual failure modes are precisely a
missed detection or a decoy digit from the card artwork (`hand_digit_reader.py:193-198`,
LOCAL_VISION_EXPERIMENTS §15f/§16c) — either one shifts every subsequent column
by one, so a single miss in slot 0 prints four spurious `<<< DISAGREE` lines and
one real one. Entries past index 4 are dropped silently by `for i in range(5)`.

Since the entire stated purpose of this function is to measure the local reader's
discrepancy rate over a live session (LOCAL_VISION_EXPERIMENTS §25), a
misalignment that inflates disagreement 5x makes the measurement unusable. It
does **not** affect gameplay — see the confirmation note below.

Fix: only compare when `len(local_cards) == 5`, or align by nearest `x` fraction
to each expected hand slot, and print the raw count mismatch as its own signal.

### I6. `harvest_hands.py` writes new-geometry crops into a directory of old-geometry crops, with old-geometry labels
`harvest_hands.py:32-35, 64`; `hand_samples/`; `hand_labels*.json`

All 260 files in `hand_samples/` are **1020x298** — that is `y0=0.770`, the
pre-change crop. The new `y0=0.716` produces 1020x367. `hand_labels.json`,
`hand_labels_2/3/4.json` are keyed by those old filenames.

`hand_crop()` now reads `GAMEPLAY_REGIONS_FRAC["hand"]` live, so re-running
`harvest_hands.py` drops 367px crops into the same directory alongside the 298px
ones under similar names. Any subsequent offline measurement that mixes them (or
reuses `hand_labels*.json` against a regenerated sample) silently mixes two
coordinate systems — and normalised y fractions differ by a factor of ~1.23
between them, which is exactly the scale of the `SHIELD_DY` / Δy constants.

Offline analysis only, no gameplay impact, but it will produce confidently wrong
numbers if not caught.

Fix: version the output directory (e.g. `hand_samples_y0716/`) or stamp the crop
fractions into the filename, and regenerate the labels rather than reusing them.

### I7. `state_json["phase"]` is unguarded and `None` silently selects the pitching strategy
`orchestrator.py:1660`, `1434`, `1446-1449`

`READ_STATE_PROMPT` explicitly allows `"phase": null` (line 152), and
`validate_game_state()` never checks `phase` even when `screen == "turn"`. Line
1660 (`if state_json["phase"] != last_phase`) is **outside** the try/except that
guards `play_one_turn`, so a missing key crashes `run()` outright. And if the key
is present but `null`, `play_one_turn` falls through
`if state_json["phase"] == "batting": ... else: best_pitching_play(...)` — a
misread phase plays the wrong strategy with no warning, on a real match.

Fix: add `phase in {"batting", "pitching"}` to `validate_game_state()` when
`screen` is `"turn"`/`"discard_prompt"`, so a null phase becomes a retryable
`ValueError` instead of a silently wrong play.

### I8. `read_full_ban_collection()` can `KeyError` on a missing `secondary`
`orchestrator.py:1291-1296, 1308`

The candidate filter checks `name` and `isinstance(c.get("power"), int)` but not
`secondary`; line 1308 then does `PlayerCard(c["name"], c["power"], c["secondary"])`.
A model response that omits `secondary` (the prompt permits nulls elsewhere)
raises `KeyError` mid-loop, unwinds through the `finally` (which does
`presses_so_far` × `move_up`), and aborts the whole scan into the ban-screen
retry path.

Fix: add `isinstance(c.get("secondary"), int)` to the filter, or
`c.get("secondary", 0)` at construction.

### I9. Screenshot logger has no disk cap; 10Hz is ~2.2 MB/s
`orchestrator.py:565-572, 575-589`

`screenshot_log/` is already **401 MB from ~3 minutes** of capture (1,815 files).
That extrapolates to ~8 GB/hour. The comment at lines 570-572 acknowledges this
("watch disk usage closely") but nothing enforces it — no frame cap, no
size budget, no rotation, and `start_screenshot_logger()`'s returned stop event
is discarded by `run()` (line 1514) so there is no way to stop it mid-run. A
long overnight session with `log_screenshots=True` will fill the volume, and the
exception swallow at line 586-587 means `ENOSPC` failures are invisible.

Fix: cap total frames or bytes and prune oldest; keep the stop event in `run()`.

---

## Minor

### M1. Obsolete module: `hand_card_matcher.py` + `hand_card_embeddings.json`
The CLIP matcher is referenced only by the dead import in I4. Its 113 KB
embedding cache was built at 20:41 against per-card crops taken from the **old**
hand geometry, so it is stale as well as unused. Its own docstring (lines 9-10)
still says "NOT wired into the live pipeline", which is now the correct state
again after the rewrite. Candidate for deletion along with the cache file.

### M2. Obsolete module: `digit_recognizer.py` + `digit_templates/`
Not imported by anything (grepped). `hand_digit_reader.py:20-23` documents the
template approach as rejected ("matching WRONG digits at score 1.000. Unusable").
Dead.

### M3. `hand_digit_reader.py` module docstring contradicts reality
Lines 39-41: *"STATUS: validated offline against real captures, NOT yet wired
into `read_game_state()`. Vision still reads hand cards in the live loop."*
It **is** now wired into `log_local_read_comparison()`. The second sentence is
still true and is the important part; the first is misleading. Suggest: "wired in
as an audit-only cross-read; vision remains authoritative."

### M4. `hand_digit_reader.py:53-54` — "read at two scales", code reads three
`hits = detect(img, 1) + detect(img, 2) + detect(img, 4)` (line 77). Comment says
"1x catches most, 2x recovers the occasional miss. Neither alone was complete."

### M5. `group_into_cards()` docstring cites old-crop Δy figures for a rule it doesn't implement
`hand_digit_reader.py:188-190`: *"Measured pair spacing across real hands: Δy
0.204-0.253 (median 0.227) ... See LOCAL_VISION_EXPERIMENTS.md §14."*

Two problems: (a) §14 measured those on the 298px old crop; in the current 367px
crop the same physical spacing is ~0.166-0.205 (and §23's own tall-crop
measurement is Δy 0.169-0.191, consistent with that). (b) `group_into_cards`
doesn't use a Δy band at all — it clusters by x and takes upper=power,
lower=secondary. The docstring describes a rule that was designed in §14 and
never implemented here.

**Explicitly not a bug:** `SHIELD_DY = 0.175` (line 102) *is* correct for the new
tall crop — §23/§24 measured it in tall-crop fractions. I checked this because it
was the obvious stale-calibration suspect and it holds up. Worth noting in the
comment that §23 also found the offset is position-dependent across the fan
(Δy 0.169→0.191 left to right) and that the fixed vector works only because the
±0.090/±0.130 patch is large enough to absorb the drift.

### M6. `validate_card()` now accepts powers 1-3 as "tactics", weakening the player-card check
`hand_digit_reader.py:167-176`. Before the change, a player power misread as `3`
was rejected as invalid. Now it validates as a tactics card with
`secondary == 0`. The disjoint-range argument is sound for *correctly read*
cards, but the check's stated job is catching *mis-reads*, and this is a real
(small) loss of coverage. Audit-only today, so low stakes — worth remembering if
this ever gates a decision.

### M7. `ROSTER_BY_NAME` is not rebuilt when an entry is learned, contrary to its comment
`orchestrator.py:1088-1092`: *"rebuilt whenever a new roster entry is learned so
newly-seen names are immediately matchable without a script restart."*
`_learn_roster_entry()` (lines 1075-1083) updates `KNOWN_BAN_ROSTER` and the JSON
file but never touches `ROSTER_BY_NAME`. Entries learned mid-run are only
name-matchable after a restart. Either rebuild it in `_learn_roster_entry()` or
fix the comment.

### M8. Stale "1Hz" in two places
`orchestrator.py:593` (`start_screenshot_logger` docstring) and
`orchestrator.py:1490` (`run` docstring) both say "1Hz"; the interval is 0.1s
(10Hz). Line 566's history string is also off — *"bumped up three times tonight
(1Hz -> 0.5Hz -> 2Hz -> 5Hz -> 10Hz)"* is four bumps, and 1Hz→0.5Hz is a
slow-*down*, presumably meaning "0.5s interval".

### M9. Module docstring names the wrong env var
`orchestrator.py:25` says *"Requires: ANTHROPIC_API_KEY set in your
environment"*; line 52 reads `os.environ["PERSONAL_ANTHROPIC_API_KEY"]`. The
`Requires: pip install` line (24) also omits `pytesseract`, `numpy`, and
`Pillow`, all of which are hard imports.

### M10. `input_controller.select_bans_and_start()` and `navigate_grid()` are dead
Only `select_bans_and_start_full()` is imported by `orchestrator.py`;
`navigate_grid` is used exclusively by the dead non-full variant.

### M11. `select_bans_and_start_full()` presses `confirm_play` twice with no explanation
`input_controller.py:218-220`. The non-full variant presses once (line 176) and
the docstring mentions only one confirm. If the second press is intentional
(a confirmation dialog), it needs a comment; if it's a leftover, it's an extra
input into a menu. **I could not determine which from the code alone** — flagging
as a question rather than asserting a bug.

### M12. `read_hand_digits()` ignores the subprocess return code
`hand_digit_reader.py:135-144`. It scans stdout for a line starting with `[` and
raises only if none is found. A worker that crashed *after* printing a JSON line
(or printed a `[`-prefixed log line before failing) would be treated as success.
Low risk given the worker's structure, but checking `result.returncode` is free.

### M13. Possible self-suppression in the shield recovery pass (low confidence)
`hand_digit_reader.py:105-125`. The "global pass already found this shield" check
on line 108 iterates `merged`, which the loop body appends to. A shield recovered
for card A can therefore satisfy the check for a later card B if B's power badge
is within `|Δx| < 0.06` and 0.10-0.30 *above* A's recovered shield — suppressing
B's own recovery. Fan spacing makes this unlikely (adjacent columns are usually
>0.06 apart, which is also `group_into_cards`'s `x_tolerance`), and I have not
seen it happen. Flagging as a latent edge case, not a confirmed bug. Comparing
against a snapshot taken before the loop would remove the question entirely.

### M14. `harvest_hands.py` re-encodes JPEG and is O(n²)
Line 64 saves a JPEG-decoded crop back to JPEG (generation loss on the very
images used for OCR calibration — PNG would be safer). Line 61 compares each
frame against every kept thumbnail; at 1,815 frames × 260 kept it's fine, but it
grows quadratically with the log.

---

## Explicitly checked and NOT a problem

- **The local OCR cannot influence a decision.** `log_local_read_comparison()`
  only calls `print()`; nothing it computes is returned, stored, or read by
  `play_one_turn`/`decision_engine`. The call site (`orchestrator.py:1551-1555`)
  is wrapped in its own try/except. Audit-only, as intended.
- **`SHIELD_DY = 0.175` is not stale** — see M5.
- **`x_tolerance = 0.06` is not stale** — the hand crop's x fractions
  (0.250-0.760) were unchanged by the y0 edit, so x-normalised constants carry
  over unaffected.
- **`_last_gameplay_crops`** is written and read on the same thread, from the same
  frame, within one loop iteration — no race with the screenshot logger thread
  (which never touches it).
- **`for x, y, t, s in list(merged)`** (`hand_digit_reader.py:105`) correctly
  snapshots before appending — no mutation-during-iteration bug there.
- **`known_ban_roster_learned.json` does not exist yet**, so no bad learned data
  is currently on disk. I3 is a "fix before first live ban scan" item, not a
  cleanup.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 4 |
| Important | 9 |
| Minor | 14 |

**Fix first: C1 (and C2, which is the same defect).** The result-screen branch
increments and persists the win/loss record with no idempotency guard and with
`stuck_count` reset to zero, so a single result overlay that outlives the 4-second
settle silently inflates `progress.json` — potentially past `target_wins`, ending
the run on a fabricated record. It's the only finding that corrupts persisted
state rather than just wasting a turn, and the same one-line guard (require an
observed screen transition before acting on `result` / `match_start_prompt`)
fixes C2's money-tracking drift at the same time.

C4 is the most *likely* to bite tonight — the PaddleOCR venv path is tied to a
session scratchpad under `/private/tmp` and will break on the next reboot — but
it only degrades the audit, not gameplay.
