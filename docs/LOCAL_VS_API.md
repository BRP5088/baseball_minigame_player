# What runs locally vs. what still calls the API

Verified against the code on 2026-08-25 (not from memory — every entry traced
to its call sites).

**Headline: the per-turn decision path is still 100% vision API.** Only the ban
screen has real local-first behaviour. Several local readers are built,
measured, and passing tests — but they run in *audit mode* only, printing
alongside the vision read and never feeding a decision.

---

## 1. Fully local, driving real behaviour

| What | How | Fallback | Notes |
|---|---|---|---|
| **Ban-grid lock detection** | `detect_ban_grid_locked()` — PIL/numpy local contrast | none needed | Decides which grid cells hold a usable card. Pure pixel math, no model. 7 call sites. Covered by `test_ban_grid_locked.py`. |
| **Locked-card masking** | `mask_low_contrast_regions()` — PIL Max/Min filter | none needed | Blanks faded cards *before* the frame reaches the vision model, so it can't hallucinate stats for them. 5 call sites. |
| **Ban-card identity** | `ocr_ban_card_name()` — tesseract + strict roster match | **yes → vision** | Local-first: resolves a card's name and looks its stats up in `KNOWN_BAN_ROSTER`. Abstains (returns `None`) rather than guessing; the caller then falls through to `read_ban_row_cards()`. This is the only genuine local-first-with-API-fallback path in the project. |

## 2. Local, built and validated, but AUDIT-ONLY (does not drive anything)

All three are called exclusively from `log_local_read_comparison()`, which only
`print()`s. Enabled with `run(..., compare_local_reads=True)`.

| What | How | Measured accuracy | Why not wired in |
|---|---|---|---|
| **Scoreboard digits** | `ocr_scoreboard()` — tesseract | 7/7 frames exact | Ready. Blocked only by the fact that the same API call that would be saved is still needed for screen classification (see §4). |
| **Base-runner identity** | `ocr_runner_card()` — tesseract + roster match | 3/3 occupied + empty base correct | Same. |
| **Hand-card power/secondary** | `read_hand_digits()` — PaddleOCR in a separate venv | 98% of cards, 12/13 hands exact | Residual failures are **silent** — a missed shield reads as `secondary=0`, indistinguishable from the 29% of cards that genuinely have none. Not safe to trust without the cross-read. |

## 3. Still API — the whole per-turn loop

| What | Function | Frequency | Why it's still API |
|---|---|---|---|
| **Screen classification** | `read_game_state()` | **every poll** | Genuinely open-ended. Must recognise `turn` / `discard_prompt` / `result` / `ban_screen` / `match_start_prompt` / `other` — including screens never seen before. A local pixel check can confirm "this looks like X" but cannot identify "this is something unexpected", which is exactly what the `other` bucket needs to catch. |
| **Hand contents** | `read_game_state()` | every poll | Same call as above. |
| **Runners on base** | `read_game_state()` | every poll | Same call. |
| **Score / discards left** | `read_game_state()` | every poll | Same call. |
| **Ban-screen card reads** | `read_ban_row_cards()` | **disabled by default** | Only fires for grid positions `ocr_ban_card_name()` refused, or when the roster lookup can't cover the batch. |
| **Opponent's revealed card** | `read_matchup_reveal()` | once per played turn | Diagnostic only (`match_log.jsonl`). Slated for removal once the fielding/speed question is answered — see the `ponytail:` note on `MATCH_LOG_FILE`. |
| **Starting balance** | `read_balance_from_pause_menu()` | once, first run ever | Reads the pause-menu coin counter. Negligible. |

## 4. The reason localising the per-turn reads saves nothing yet

Scoreboard, hand, and runners are **not separate API calls**. They are all
fields of the single `read_game_state()` response, which also does screen
classification. The payload was already optimised (§4 of
LOCAL_VISION_EXPERIMENTS.md — a low-res overview plus sharp region crops, ~55-60%
fewer image tokens).

So replacing the scoreboard/runner/hand reads with the local versions would
**save zero API calls** while that one call still has to happen for screen
classification. The gain would be latency only, and modest.

**The unlock is screen classification.** If that moved local, the entire
per-turn API call could disappear on ordinary turns — and only then do the
already-built local readers pay off. That is the single highest-leverage
remaining item, and it is also the one with the clearest safety objection
(misclassifying an unexpected screen as a normal turn means acting blindly on
a screen the code doesn't understand).

## 4b. Feasibility test: local screen classification with API fallback

Tested 2026-08-25. The design proposed — classify locally, and call the API
only when the local classifier is *unsure* — is the right shape. It inverts the
objection in §4: local never has to identify an unknown screen, it only has to
recognise known ones confidently and abstain otherwise. Same
abstain-don't-guess pattern that made ban-card OCR safe.

**Ground truth**: 260 labelled frames from the 2026-08-24 session — 157 `turn`,
74 transition/animation, 29 menu/ban — derived from the hand-labelling passes.

**Feature separation** (cheap, geometry-light):

| feature | turn | not-turn |
|---|---|---|
| top-left brightness | 5.8 ± 0.7 | 7.8 (menu/ban 12.9 ± 2.0) |
| hand-region mean | 87.1 ± 5.6 | 83.0 (transition 69.1 ± 11.2) |
| hand-region std | 70.0 ± 3.5 | 62.4 |

Menu/ban separates cleanly. Turn vs transition overlaps, which is expected — a
mid-deal frame *is* a turn screen, mid-animation.

**Result — the prototype fails the safety bar.** A binary "is this definitely a
settled turn?" rule fit on all 260 frames reached zero false positives at 41%
turn coverage (~25% of polls). But **that did not survive cross-validation**:

```
20 random 50/50 splits, rule fit on train, evaluated on held-out half:
  false positives held-out: mean 0.70, max 2, zero-FP in only 11/20 trials
  turn coverage held-out:   mean 50%
```

So the zero-FP was fit to the data, not a real property. On unseen frames the
rule misclassifies — and a false positive here means **acting on a screen the
code has misread**, which is the dangerous direction.

**Verdict: the approach is sound, this implementation is not.** What it would
need:
1. **Better features.** Three hand-picked scalars is crude. Structural signals
   would likely separate far better: the scoreboard box border, the
   PLAY/DISCARD prompt glyph, card-edge count in the hand region, the
   face-down card back that marks a mid-deal frame (the labelling passes
   identified all of these as reliable by eye).
2. **A calibrated classifier**, not hand-tuned thresholds — so "unsure" is a
   real probability rather than a margin someone guessed.
3. **Multi-session data.** All 260 frames come from one session, one lighting
   condition, one window position. Generalisation across sessions is exactly
   what was not tested and is the thing most likely to break.
4. **An asymmetric acceptance test**: false positives must be ~0 on held-out
   data before this drives anything; coverage is negotiable, safety is not.

## 4c. A better answer: reader self-validation instead of a classifier

Follow-up test, same day. Rather than train a screen classifier, use the local
readers themselves as the confidence signal — a frame is a settled turn if, and
only if, the readers can produce a coherent parse of it. No model, no
thresholds, no training data.

Two checks, both properties of readers already needed anyway:

1. **Scoreboard parses coherently** (`ocr_scoreboard`) — separates gameplay
   from menus/ban screens.
2. **Hand yields exactly 5 cards, all values in range** (`hand_digit_reader`) —
   separates a settled hand from mid-animation.

Measured on the labelled frames:

| frame class | scoreboard parses | hand coherent | **conjunction** |
|---|---|---|---|
| `turn` (n=157 / 12) | 157/157 (100%) | 9/12 (75%) | **~75% pass** |
| `transition` (n=74 / 12) | 72/74 (97%) | **0/12** | **0% pass** |
| `menu_or_ban` (n=29 / 8) | 2/29 (7%) | **0/8** | **0% pass** |

**Zero false positives across all 20 non-turn frames tested**, versus the
classifier prototype's 0.7 average on held-out data (§4b).

The important difference is *why* it abstains. The classifier's zero-FP was a
threshold fitted to one session's pixel statistics, and it evaporated on unseen
frames. This is **structural**: a card in mid-flight genuinely does not produce
five valid badge pairs, so the reader fails for the same reason a human would
say "the cards aren't dealt yet." Nothing to overfit.

Note the two checks are complementary, and both are needed: the scoreboard
check alone lets 2/29 menu frames through, and the hand check alone would admit
nothing but is only meaningful once you know you are in a match.

Cost: ~25% of genuine turns are rejected and fall back to the API. That is the
cheap direction.

**Caveats before this drives anything.** Sample sizes for the negative classes
are small (12 transition, 8 menu/ban) and all from a single session. It should
run in audit mode against live play first — logging what it *would* have
decided next to what vision actually said — exactly as the current local
readers do. The existing `compare_local_reads=True` hook is where that goes.

Also note the payoff is capped: `read_game_state()` still runs on the ~25% of
turns that abstain plus every non-turn screen, and hand reads retain the silent
shield-miss failure mode (§2). This is a meaningful reduction, not an
elimination.

## 4d. The ban screen is now 100% local (2026-08-25)

`TRUST_ROSTER_ONLY = True` removes vision from the ban screen entirely.
Simulated against real frames at five scroll depths:

| | vision calls | local name OCRs |
|---|---|---|
| before | 4 | 12 |
| after | **0** | **0** |

It works because two independent facts compose:

* **Which positions are unlocked** is per-save, and is read live from the
  screen by `detect_ban_grid_locked()` — pure local contrast, no catalogue
  involved. This is the part that varies between players.
* **What card sits at a position** is game-wide and constant, which is all
  `KNOWN_BAN_ROSTER` stores. Measured: 100% coverage of visible unlocked
  positions across 23 real ban frames.

Nothing about unlock state is baked into the roster, which is why one
catalogue serves every save.

**What is given up:** discovering a card the roster has never seen. That
machinery existed so a game update adding cards would be picked up
automatically; the owner is renting the game and does not need it. The two
catalogue gaps, `(6,3)` and `(6,4)`, are skipped as ban candidates —
`choose_bans()` picks the best 3 from what it sees, so missing two of ~33
cards cannot cause a wrong ban, only a marginally less optimal one.

Set `TRUST_ROSTER_ONLY = False` to restore vision-backed discovery.

## 5. Summary

- **3** things fully local and driving behaviour (all ban-screen related)
- **3** things local, validated, audit-only
- **1** per-poll API call doing screen + hand + runners + score together
- **3** additional API calls: ban fallback (conditional), matchup logging
  (diagnostic, removable), balance (once ever)

Nothing that drives a live gameplay decision is read locally today except the
ban screen.
