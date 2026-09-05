# Documentation accuracy audit

Read-and-report only. No source file was edited, no game was run, no keystroke sent,
nothing written to `match_log.jsonl`, `progress*.json`, `known_ban_roster_learned.json`,
`diagnostics/` or `screenshot_log/`. Everything I executed ran against copies in a
scratch directory or read-only against the repo.

**Line numbers are as of 2026-08-26 00:48 and will drift.** Three other agents were
editing the tree throughout this audit: `simulate.py` changed at 00:29, and
`orchestrator.py` went 3,413 → 3,459 → 3,483 lines while I read it (the second change
replaced `MAX_IDENTICAL_FRAMES` with `FROZEN_STREAM_SECONDS` and extended the progress
file — see inverse-findings F and G, which I updated to match). Every finding therefore
quotes an **anchor string** as well as a line number; grep the anchor if the number has
moved. None of those edits touched any Tier-1 finding below.

**What "verified" means below.** Tags: `[REPRO]` = I re-ran the computation and state the
number I got. `[CROSS]` = contradicted by a measurement recorded elsewhere in this repo.
`[CODE]` = contradicted by the code as it currently stands. `[UNVERIFIABLE]` = the claim
cannot be reproduced from anything in the repo.

---

## Ranked summary

Ranked by how likely the staleness is to cause a **wrong decision** — a wrong card, a
wrong ban, a wrong spend, or a correct capability left unused.

| # | Where | Claim | Verdict |
|---|---|---|---|
| 1 | `HEURISTICS.md` §2 | "NOT CHANGED … Left as-is" | `[CODE]` defends code deleted 2026-08-25 |
| 2 | `decision_engine.py:113,144` | "match_log currently p=0.43" | `[REPRO]` script gives **0.192**; the fielding p was **0.74** |
| 3 | `orchestrator.py:663` | badges "genuinely unreadable … font-recognition limitation" | `[CROSS]` PaddleOCR reads them at ~1.00 |
| 4 | `hand_digit_reader.py:124`, `LOCAL_VS_API.md:30`, `LOCAL_VISION_EXPERIMENTS.md:467` | "98% of cards, 12/13 hands exact" | `[CROSS]` tuning set; held-out is **2/18**, 80% per-card |
| 5 | `orchestrator.py:2204-2241` | `read_full_ban_collection` docstring | `[CODE]` describes a vision scan that no longer runs |
| 6 | `PENDING_LIVE_VALIDATION.md:250-258` | "**Fixed**: raises `ValueError` if size ≠ `BAN_GRID_CALIBRATED_SIZE`" | `[CODE]` **that constant and that guard do not exist** |
| 7 | `orchestrator.py:455,480` | "`MASK_CONTRAST_THRESHOLD=100`… normal ~170-187, faded ~52-56" | `[CODE]` threshold is 124.0; `[REPRO]` second consumer got worse |
| 8 | `orchestrator.py:1357` | `regions` accepts `"reveal"` | `[CODE]` no such key; silently falls back to `"default"` |
| 9 | `orchestrator.py:3401-3403` | `opp_tactics_kind` from `.get("type")` | `[REPRO]` prompt never returns `type`; **None on 39/39 rows** |
| 10 | `LOCAL_VISION_EXPERIMENTS.md:91,466` | ban OCR "verified 18/18" | `[CROSS]` that is the **loose/broken** config; correct config is 16/18 + 2 abstentions |
| 11 | `hand_digit_reader.py:180-184` | "1,126 player cards … four independent readers (100% inter-rater agreement)" | `[REPRO]` double-counted; **600** unique cards, passes are disjoint |
| 12 | `hand_digit_reader.py:194-197` | tactics bonuses "1-3 … measured across 299 tactics cards" | `[REPRO]` **0 bonus-3 cards** in the corpus; max observed is 2 |
| 13 | `decision_engine.py:137` | "73.6% of them … 3.30 power on average" | `[REPRO]` only under an unstated all-player hand; 46.9%/2.76 under the repo's own model |
| 14 | `decision_engine.py:82`, `HEURISTICS.md:55,185` | "79% win rate" / "78.6% vs no-tactics" | `[REPRO]` now **86.2%** |
| 15 | `orchestrator.py:1197-1209` | settle table "1.6% vs 12.3%", "p90 6.01 s" | `[CROSS]` QA_VISION §2d: rate-coupled artefact |
| 16 | `orchestrator.py:812,842,845,847,2612` | screenshot logger "10 Hz" / "~1 s" / "~2 MB/s" | `[CODE]` file's own §"Fast capture backend" says the floor is 0.466 s |
| 17 | `LOCAL_VS_API.md:19` vs `:163-192` | `ocr_ban_card_name` is "the only genuine local-first … path" | `[CODE]` dormant under `TRUST_ROSTER_ONLY`; contradicts §4d in the same file |
| 18 | `MATCH_DATA_ANALYSIS.md:388-390` | "`best_pitching_play` … picks `max(secondary, power)`" | `[CODE]` rewritten |
| 19 | `orchestrator.py:170`, `HEURISTICS.md:83`, `PENDING_LIVE_VALIDATION.md:169` | "~150-200 logged turns" | `[CROSS]` MATCH_DATA says 284-1,133; the shipped script says ~156 |
| 20 | `orchestrator.py:1897-1931` roster + `simulate.py:35-41` | roster stat pairs | `[REPRO]` 4 roster pairs have **0** occurrences in the labelled corpus |
| 21 | `input_controller.py:9` | "KEYMAP below is intentionally blank" | `[CODE]` fully populated |
| 22 | `orchestrator.py:2301-2315`, `LESSONS.md` §7, `LOCAL_VISION_EXPERIMENTS.md:1040` | tactics-boundary stop "the tell is free and already computed" | `[CODE]` the OCR it relies on is never called |
| 23 | `orchestrator.py:1002`, `PENDING_LIVE_VALIDATION.md:75` | `ocr_scoreboard` "3 real screenshots" | `[CROSS]` corpus widened to 7 |
| 24 | `hand_digit_reader.py:219`, `orchestrator.py:1118`, `LOCAL_VS_API.md:30` | "~29% of player cards" have no shield | `[REPRO]` 29.0% is right; `MATCH_DATA_ANALYSIS.md:313`'s 31% is the inflated one |
| 25 | `LOCAL_VS_API.md:17` | `detect_ban_grid_locked` "7 call sites" | `[REPRO]` 2 |
| 26 | `PENDING_LIVE_VALIDATION.md:154,178-182` | "the blind 0.5 s sleep before `read_matchup_reveal()`" | `[CODE]` replaced by `wait_for_reveal_cards()` |
| 27 | `input_controller.py:273` | "Scroll-aware version of `select_bans_and_start`" | `[CODE]` that function is in `_obsolete/` |
| 28 | `SETTLE_TIMING_ANALYSIS.md:63,250,381` | "production code polls at 0.3 s"; "`max_wait=3.0`/`4.0` call sites" | `[CODE]` 0.15 s; all call sites are 6.0/8.0 |
| 29 | `orchestrator.py:68` | "roughly a minute of being stuck" | 15 × ~2 s = **30 s** |
| 30 | `QA_VISION.md:43,48` (V1, V6) | "Live in the only ban path that still runs" | `[CODE]` both were fixed after that doc was written |

---

## Tier 1 — likely to cause a wrong decision

### 1. `HEURISTICS.md` §2 defends deleted code, under a heading that says so

**Location:** `HEURISTICS.md:64` heading, `:72-77` body, `:86-94` "QA independently reproduced this".

**As written:**
> `## 2. Fielding-priority pitcher selection (NOT CHANGED — simulation blind spot)`
> … "Removing this logic to satisfy an incomplete simulation would mean optimizing for
> the test instead of the real game. **Left as-is.**" … "**Still not changing this without
> real data.**"

**Why it is wrong.** `best_pitching_play` was rewritten on 2026-08-25. The
fielding-priority pick (`max(key=(secondary, power))`) is gone; the function now maximises
power inside a bounded `FIELDING_POWER_BUDGET = 1`
(`decision_engine.py:157-180`). The section's own experiment — "stripping out
`best_pitching_play`'s fielding-priority pitcher pick … brought it to a near-even 35.6% vs
35.0%" (`:66-70`) — is essentially the change that was then applied. I re-ran
`simulate.py` unmodified: **current vs always-boost is now 35.8% vs 37.6%**, i.e. the
"stripped" row, not the 19.6%/58.4% the section reports for "current".

This is the most dangerous entry in the audit because §2 is cited as the live rationale
from three other places (`PENDING_LIVE_VALIDATION.md:172`, `orchestrator.py` N27 note,
`MATCH_DATA_ANALYSIS.md:397`). A reader following those pointers is told the old
behaviour is deliberate and protected.

**Corrected wording:**
> `## 2. Fielding-priority pitcher selection (CHANGED 2026-08-25 — see decision_engine.py)`
> The numbers below describe the OLD `max(key=(secondary, power))` selector, which no
> longer exists. It was replaced by power-first with a bounded `FIELDING_POWER_BUDGET`.
> Re-measured against the current code (`python3 simulate.py`, seed 42, 500 matches):
> current vs no-tactics 86.2%, current vs always-boost 35.8%/37.6%. The simulation blind
> spot argument still stands — `resolve()` still models no fielding effect — but it is now
> an argument for keeping the *budget* non-zero, not for the old selector.

---

### 2. `p=0.43` is the wrong statistic, and it is not reproducible

**Location:** `decision_engine.py:113` and `:144`.

**As written:**
> `:111-115` — "How much pitch focus we are willing to trade for fielding when runners are
> on. 1 is a deliberate hedge, not a measurement: the fielding effect is UNCONFIRMED
> (**match_log currently p=0.43**), while the power rule IS confirmed."
> `:143-145` — "The fielding/`secondary` effect is the open question `match_log.jsonl`
> exists to answer, and it **currently reads p=0.43** — *cannot conclude*."

**Three separate problems.**

1. **It cites the batter statistic, not the fielding one.** `p=0.43` comes from
   `MATCH_DATA_ANALYSIS.md:189`, which is the **batter speed** row. The row immediately
   below it (`:190`) is the one this comment is about: **pitcher fielding, p = 0.74**.
   Both sit in the same two-row table, so the wrong row was read off.

2. **Neither number is what the shipped analysis script produces.** `analyze_match_log.py`
   is seeded (`random.seed(20260826)`) and therefore deterministic. Run against the
   current `match_log.jsonl` (copied to a scratch path — the real file was not touched):

   ```
   39 genuine rows, 0 synthetic
   usable for analysis: 19/39
   secondary == 0 : n=11, mean margin +0.27
   secondary >  0 : n=8,  mean margin +1.25
   permutation p = 0.192  <- CANNOT CONCLUDE
   ```

   `0.192`, reproduced twice. So the repo now contains **three different p-values for
   "does secondary matter"** — 0.43, 0.74 and 0.192 — computed by three different
   protocols (stratified-by-margin batter speed; stratified pitcher fielding; pooled
   margin-vs-secondary), and the constant that governs a live decision cites the one that
   matches none of them.

3. **The provenance is unstated in the direction that matters.** All three are held-out
   in no sense at all: the same 39 rows are the only rows there have ever been, and
   `MATCH_DATA_ANALYSIS.md:346-364` shows only **5 of 39** rows carry zero quality flags
   and only **12 of 39** are usable for the secondary question at all.

**Why it can cause a wrong decision.** `FIELDING_POWER_BUDGET = 1` is the one knob that
still lets the pitcher selector give up confirmed power. Its entire justification is this
p-value. If a reader later "settles the question" by re-running the script and seeing
0.192, they may read that as movement toward significance and raise the budget.

**Corrected wording (`:111-116`):**
> ```
> # How much pitch focus we are willing to trade for fielding when runners are on.
> # 1 is a deliberate hedge, NOT a measurement. The current evidence, all from the
> # same 39-row match_log and none of it held out:
> #   analyze_match_log.py (pooled margin vs secondary)   p = 0.192
> #   MATCH_DATA_ANALYSIS.md, stratified pitcher fielding p = 0.74
> #   MATCH_DATA_ANALYSIS.md, stratified batter speed     p = 0.43
> # None is significant; only 12 of 39 rows are usable for the question at all.
> # Re-run `python3 analyze_match_log.py` before quoting any of these — the number
> # moves as rows are added. Set to 0 for pure power-first once it is settled.
> FIELDING_POWER_BUDGET = 1
> ```
> and at `:143-145`, replace "it currently reads p=0.43" with "the shipped analysis
> (`analyze_match_log.py`) currently reads p = 0.192 on 19 usable rows — *cannot
> conclude*, and it has never been recomputed on held-out data because there is only one
> dataset."

---

### 3. `ocr_ban_card_name` — the "unreadable badge" verdict (confirmed case, still unfixed)

**Location:** `orchestrator.py:656-670`, anchor `genuinely unreadable by tesseract`.

**As written:**
> "Deliberately doesn't attempt the power/secondary badges directly: live testing
> 2026-08-24 found the power circle's digit font **genuinely unreadable by tesseract**
> regardless of crop precision or polarity (tested exhaustively, both light-on-dark and
> dark-on-light, 7 thresholds x 5 psm modes, zero correct reads) — **a font-recognition
> limitation, not a framing problem.**"

**Why it is wrong.** `LOCAL_VISION_EXPERIMENTS.md:995-1047` already records the retraction,
verbatim: *"`ocr_ban_card_name()`'s docstring says the power/secondary badges are
'genuinely unreadable … a font-recognition limitation, not a framing problem.' That was
measured on 2026-08-24 **with tesseract**. PaddleOCR was added *after* that … **PaddleOCR
does read them.** On a real ban frame, the correct digit was detected at ~1.0 confidence
for every one of the 7 unlocked cards."* The correction was written on 2026-08-25 into the
experiments log and **never propagated into the docstring**, which is the version a reader
of the code sees.

The clause that does the damage is the causal one. "Font-recognition limitation" reads as
a property of the *problem*; the measurement only supports a property of *tesseract*.

**Corrected wording:**
> "Deliberately doesn't attempt the power/secondary badges directly. Measured 2026-08-24
> **with tesseract only**: zero correct reads across 7 thresholds x 5 psm modes, both
> polarities. That is a limit of tesseract on this font, **not of the problem** —
> PaddleOCR (added later, for the hand) reads the same badges at ~1.00 confidence on a
> real ban frame (LOCAL_VISION_EXPERIMENTS.md, 'the unreadable verdict is stale'). The
> remaining blockers are decoy digits in the card art, badge assignment, and 6/9 rotation
> ambiguity — best naive attempt 3/7. Resolving via the roster name is still the cheaper
> path, but do not repeat the tesseract-era claim that the badges cannot be read."

---

### 4. `hand_digit_reader` accuracy — tuning-set numbers presented as accuracy (confirmed case)

**Location:** `hand_digit_reader.py:119-125`; replicated verbatim in `LOCAL_VS_API.md:30`
and `LOCAL_VISION_EXPERIMENTS.md:467` and `:874-875`.

**As written:**
> "Patch size is critical and NON-MONOTONIC (measured, 50 shields) … Combined with the
> global pass this took **cards from 95% -> 98% correct and exact hands from 10/13 ->
> 12/13**."

**Why it is wrong.** `QA_VISION.md:277-294` measured the same pipeline end-to-end on **18
randomly sampled held-out hand crops** that the labels mark `usable: true`:

```
exact hand matches                        2 / 18  (11%)
hands with the wrong CARD COUNT          11 / 18  (17 cards silently dropped)
per-card, on the 7 count-matched hands   28 / 35  (80%)
```

and states plainly: *"`hand_digit_reader.py:120-124` reports '95% -> 98% correct and exact
hands from 10/13 -> 12/13'. Those are **tuning-set numbers**."*

The 13 hands the docstring reports are the hands the patch-size sweep was tuned on.
Nothing in the docstring says so, and the 95%→98% delta is exactly the kind of small gain
that does not survive a held-out split.

Worse, `QA_VISION.md:296-320` shows the dominant residual failure is **not** the missed
shield the docstring warns about. 5 of 7 wrong cards were a *lost power badge* that
promotes the shield to "power", turning a player card into a **`valid=True` tactics
card** — a kind flip, not a stat error.

**Corrected wording (`hand_digit_reader.py:119-125`):**
> ```
> # Patch size is critical and NON-MONOTONIC. TUNING SET, 50 shields / 13 hands —
> # these are the hands the sweep was fitted on, not an accuracy estimate:
> #   ... (table unchanged) ...
> # On the tuning set, global+targeted took cards 95% -> 98% and exact hands
> # 10/13 -> 12/13.
> #
> # HELD-OUT ACCURACY IS MUCH LOWER. On 18 randomly sampled labelled hands
> # (QA_VISION.md §3): 2/18 exact hands, 80% per-card on the 7 hands whose card
> # COUNT was right; 11/18 returned the wrong number of cards. The dominant error
> # is NOT the missed shield below — it is a lost power badge promoting the shield
> # to "power", which validate_card() accepts as a tactics card (5 of 7 errors).
> # Treat this reader as audit-only until those numbers move on held-out data.
> ```
> and in `LOCAL_VS_API.md:30` / `LOCAL_VISION_EXPERIMENTS.md:467`, replace
> "98% of cards, 12/13 hands exact" with
> "98% cards / 12-13 hands **on the tuning set**; **2/18 exact hands, 80% per-card** held
> out (QA_VISION §3)".

---

### 5. `read_full_ban_collection`'s docstring describes a path that no longer runs

**Location:** `orchestrator.py:2204-2241`, anchor `Scroll through the ban screen's full collection`.

**As written:** the whole docstring is about the vision scan —
> "Scroll through the ban screen's full collection, **reading it via vision** … The
> model's only job now is `read_ban_row_cards()` … If the count it returns doesn't match
> the expected unlocked-cell count, the whole batch is discarded … which reads as a
> mismatch every time, since `read_ban_row_cards()` is told to skip tactics cards…"

**Why it is wrong.** `TRUST_ROSTER_ONLY = True` (`:2196`). On the default path the
function takes the `trust_roster` branch at `:2318-2338`: positions resolve from
`KNOWN_BAN_ROSTER` by `(row, col)`, `ocr_ban_card_name` is skipped by an explicit
`continue` (`:2278-2281`), `read_ban_row_cards` is never called, and there is no
mismatch/retry bookkeeping at all. Every mechanism the docstring explains is dormant.
The parameter that switches this — `trust_roster` — is **not mentioned in the docstring**,
even though it is in the signature.

**Why it can cause a wrong decision.** A reader debugging a bad ban will look for the
count-mismatch guard the docstring promises ("the whole batch is discarded rather than
risk assigning any card to the wrong grid position") and conclude that a wrong position is
structurally impossible. On the live path that guard is not running; the only thing
standing between a wrong lock read and a wrong physical ban is
`detect_ban_grid_locked`. `orchestrator.py:450-452` says exactly this
("with TRUST_ROSTER_ONLY the lock detector is the ONLY live vision component left on the
ban path"), but that note is 1,750 lines away and this docstring contradicts it.

**Corrected wording — add as the first paragraph:**
> "**Default path (TRUST_ROSTER_ONLY = True) is 100% local and none of the vision
> machinery below runs.** `detect_ban_grid_locked()` says which cells are unlocked;
> `KNOWN_BAN_ROSTER[(row, col)]` says what card is there; a position the roster does not
> know is simply not a ban candidate. No name OCR, no vision call, no mismatch/retry.
> That makes the lock detector the single point of failure on this path — see the
> `MASK_CONTRAST_THRESHOLD` note. Everything from 'Positions are determined entirely in
> code' onward describes the `trust_roster=False` fallback."

---

### 6. A documented fail-loud guard that does not exist

**Location:** `PENDING_LIVE_VALIDATION.md:250-258`.

**As written:**
> "**Fixed**: `BAN_GRID_COL_X/ROW_Y` are hardcoded pixel boxes tied to a specific
> screenshot resolution — a Chiaki-ng window resize or macOS display-scaling change would
> silently misalign every box against the actual cards, producing confidently wrong lock
> detection instead of an obvious failure. `detect_ban_grid_locked()` now **raises a clear
> `ValueError` if the screenshot size doesn't match `BAN_GRID_CALIBRATED_SIZE`**, so a
> scaling change fails loud (caught by the existing retry/exception handling) instead of
> quietly producing wrong bans."

**Why it is wrong.** `BAN_GRID_CALIBRATED_SIZE` **occurs nowhere in the repo except in
that sentence**. `detect_ban_grid_locked` (`orchestrator.py:549-603`) contains no `raise`
of any kind. The stated remedy — expressing the boxes as fractions — *was* done, but
fractions do not fail loud; they fail silently on a display of a different aspect ratio,
which is precisely the scenario the entry claims to have closed.

What actually exists is weaker and lives somewhere else: an aspect-ratio **warning**
(print, not raise) on the mss monitor at `orchestrator.py:1284-1295`, which only covers
the settle path's capture backend, not `capture_screenshot_image()` (pyautogui), which is
what feeds the ban scan.

**Why it can cause a wrong decision.** This is the highest-severity doc entry in the repo
because it converts an open risk into a closed one in the reader's mind, on the path that
sends physical input into a paid match. Under `TRUST_ROSTER_ONLY` a misaligned grid means
the lock detector reads the wrong pixels, which means a card the player does not own can
become a ban candidate, or vice versa — with nothing downstream to catch it.

**Corrected wording:**
> "- **Partially addressed, NOT fail-loud**: `BAN_GRID_COL_X/ROW_Y` are now fractions of
>   width rather than hardcoded pixels, which survives a pure resize. It does **not**
>   survive a change of aspect ratio or of which display the game is on — the fractions
>   land on the wrong pixels and nothing raises. There is no size assertion in
>   `detect_ban_grid_locked()`; the only guard anywhere is a printed aspect warning on the
>   mss monitor (`orchestrator.py`, `_CALIBRATED_ASPECT`), which does not cover
>   `capture_screenshot_image()`, the capture the ban scan actually uses. Still open."

---

### 7. `MASK_CONTRAST_THRESHOLD` 100.0 → 124.0: stale docstring, zombie comment, undocumented second consumer

**Location:** `orchestrator.py:439-456` (the new justification), `:455` (trailing zombie),
`:480` (the docstring), `:499-505` (the calibration note).

**(a) The docstring still states the old value.** `:480`, anchor
`MASK_CONTRAST_THRESHOLD=100 sits`:
> "Verified live against a real ban screen: legible cards measured ~170-187, faded/locked
> cards ~52-56 — **MASK_CONTRAST_THRESHOLD=100 sits with a wide margin between both.**"

The constant is `124.0` (`:439`).

**(b) A zombie comment survives on the same line as the new conclusion.** `:455`:
> "124.0 is the gap midpoint, so cursor-lifted locked cards (max 106.5) and genuine
> unlocked cards (min 142.5) both sit ~18 clear of it.  `# normal cards measured ~170-187,
> faded ones ~52-56 — wide margin`"

The two halves of that line contradict each other: the new measurement (95 frames, 950
cells) puts the locked cluster up to **106.5**, the old comment says locked is 52-56. A
reader scanning for "what does a locked card measure" will find both numbers on one line.

**(c) The calibration note at `:499-505` is from the superseded sample.**
> "see PENDING_LIVE_VALIDATION.md for the sampled contrast values that validated these
> boxes: every one of 10 cells across 2 rows landed either **51-64 [locked] or 160-180
> [normal]**, a huge margin either side of MASK_CONTRAST_THRESHOLD"

10 cells, 1 frame, versus the new 950 cells across 95 frames. Both are labelled as
validating the same constant.

**(d) The undocumented part — `MASK_CONTRAST_THRESHOLD` has two consumers, and only one
was recalibrated.** `[REPRO]` The new justification (`:436-453`) is written entirely about
`detect_ban_grid_locked`, which uses `_local_contrast` over **whole grid cells**. The same
constant is also read by `mask_low_contrast_regions` (`:495`), which uses **PIL
MaxFilter/MinFilter over 60px tile means** on *any* frame, including gameplay frames via
`capture_state_images_b64(mask_low_contrast=True)`. Two different statistics, one
threshold, and raising it makes the second one strictly more aggressive.

I measured the blacked-out tile fraction of each gameplay crop on four real settled turn
frames from `screenshot_log/` (read-only):

| frame | region | at 100.0 | at 124.0 |
|---|---|---|---|
| `20260824_200812_398` | third_base | 80% | **95%** |
| `20260824_200812_398` | first_base | 65% | **95%** |
| `20260824_200812_398` | second_base | 37% | **63%** |
| `20260824_200812_398` | hand | 45% | **55%** |
| `20260824_200817_424` | third_base | 80% | **95%** |

This reproduces `QA_VISION.md:51` (V9: "blacks out 62-79% of every base crop on a gameplay
frame") and shows the 100 → 124 change **made it materially worse**. It is latent only
because `read_game_state()` is always called with the default `mask_low_contrast=False`
— a fact recorded in QA_VISION but not next to the constant.

**Corrected wording — replace `:455` and `:480`, and add to the constant block:**
> ```
> # 124.0 is the gap midpoint, so cursor-lifted locked cards (max 106.5) and genuine
> # unlocked cards (min 142.5) both sit ~18 clear of it. This supersedes the earlier
> # "normal ~170-187 / faded ~52-56" figure (10 cells, 1 frame, 2026-08-23) and the
> # 51-64 / 160-180 figures quoted in PENDING_LIVE_VALIDATION.md.
> #
> # TWO CONSUMERS, ONLY ONE CALIBRATED. detect_ban_grid_locked() compares this against
> # _local_contrast() over whole grid cells — that is what 124.0 was fitted to.
> # mask_low_contrast_regions() compares it against PIL Max/Min over 60px TILE MEANS on
> # arbitrary frames. On a gameplay frame the raise from 100 to 124 takes the base crops
> # from ~65-80% blacked out to ~95%. Harmless today only because read_game_state() is
> # always called with mask_low_contrast=False. Give the two consumers separate
> # constants before ever enabling masking on a gameplay read.
> ```
> and at `:480`: "Verified live against a real ban screen and re-measured 2026-08-26 over
> 950 cells: locked cluster tops out at 106.5, unlocked starts at 142.5,
> `MASK_CONTRAST_THRESHOLD = 124.0` is the gap midpoint. **Note this function's statistic
> is tile-mean-of-PIL-filter, not the whole-cell `_local_contrast` the 124.0 was fitted
> to.**"

---

### 8. `wait_for_screen_to_settle` advertises a region set that does not exist

**Location:** `orchestrator.py:1357-1359`, anchor `picks a set from SETTLE_REGION_SETS`.

**As written:**
> "`regions` picks a set from `SETTLE_REGION_SETS` (**"turn", "reveal", "default"**)."

**Why it is wrong.** `SETTLE_REGION_SETS` (`:1215-1219`) has exactly two keys: `"turn"`
and `"default"`. `"reveal"` was a *recommendation* in `SETTLE_TIMING_ANALYSIS.md:350-353`
(gate on `center`, threshold 6.5, `max_wait` 16 s) that was never implemented — the reveal
path went a different way entirely (`wait_for_reveal_cards()`, a rising-edge presence
detector).

**Why it can cause a wrong decision.** Both `wait_for_screen_to_settle` (`:1378`) and
`screen_is_moving` (`:1550`) use `SETTLE_REGION_SETS.get(regions, SETTLE_REGION_SETS["default"])`.
A caller who follows the docstring and passes `regions="reveal"` gets
`("legacy_roi", "hand")` **silently** — no exception, no warning, and specifically the
combined gate that the same file's own table (`:1204`) records as *both slower and less
safe* (3.3% continuation, p90 17.97 s). A documented-but-nonexistent option that
silently degrades to the worst available option is the shape of bug this project keeps
finding.

**Corrected wording:**
> "`regions` picks a set from `SETTLE_REGION_SETS` — currently only `"turn"` and
> `"default"`. **An unrecognised name silently falls back to `"default"`**, which is the
> combined `legacy_roi + hand` gate measured below as the slowest and least safe option,
> so do not rely on a typo failing loudly. There is deliberately no `"reveal"` set:
> SETTLE_TIMING_ANALYSIS.md §4 recommended one, but the reveal is detected by presence
> (`wait_for_reveal_cards()`), not by settling — see REVEAL_CENTER_REGION for why."

---

### 9. `opp_tactics_kind` reads a field the prompt never returns

**Location:** `orchestrator.py:3401-3403`; `READ_MATCHUP_PROMPT` at `:388-417`.

**As written (`:3401-3403`):**
> ```
> # See our_tactics_kind: bonus without type can't
> # be turned into effective power.
> matchup_info["opp_tactics_kind"] = opp_tactics.get("type") if opp_tactics else None
> ```

**Why it is wrong.** `READ_MATCHUP_PROMPT`'s tactics schema (`:398-401`) is
`{"kind": "tactics", "name": str, "bonus": int, "paired_with": str}` — there is **no
`type` field**. `.get("type")` therefore returns `None` unconditionally.

`[REPRO]` Across all 39 rows of `match_log.jsonl`: `opp_tactics_kind` is `None` **39/39**,
including the 8 rows where `opp_tactics_bonus` is non-zero (3×1, 3×2, 2×3).

The consequence is downstream and exact: `analyze_match_log.py:65-76` returns `None` for
effective power whenever a bonus is present but the kind is not, so those rows are
excluded — the script's own output reports `excluded 5: opponent card not captured / kind
missing`. The comment says the field is being captured for exactly this reason; it never is.

The prompt *does* return the tactics card's **name**, and the four names are enumerable
(`KNOWN_TACTICS_NAMES`, `:2155`), so the kind is recoverable — which is what
`MATCH_DATA_ANALYSIS.md:35-38` means by "the name is read and then thrown away". Note that
doc names the wrong mechanism now (it says the code "keeps only `bonus`"; the code keeps a
`type` that is always `None`), so both descriptions are stale in different directions.

**Corrected wording:**
> ```
> # BROKEN — reads a field READ_MATCHUP_PROMPT does not return, so this is None on
> # every row (verified: 39/39 in match_log.jsonl, including 8 rows with a non-zero
> # opp bonus). Those rows are then dropped by analyze_match_log.py as
> # "opponent card not captured / kind missing". Fix by mapping the tactics NAME,
> # which the prompt does return, through KNOWN_TACTICS_NAMES -> TacticsType, or by
> # adding "type" to the prompt schema.
> matchup_info["opp_tactics_kind"] = opp_tactics.get("type") if opp_tactics else None
> ```

---

### 10. The ban-OCR "18/18" is the number the broken configuration produces

**Location:** `LOCAL_VISION_EXPERIMENTS.md:91` and `:466`.

**As written:**
> `:91` — "**Result: 18/18 known cards correct across 3 independently-scrolled frames.**
> Locked in as a regression test."
> `:466` — "| Ban-screen cards | tesseract + roster fuzzy match | **Local, verified 18/18** |"

**Why it is wrong.** `TEST_SUITE_AUDIT.md:77-83` and `test_ocr_ban_card.py:98-105` both
record that 18/18 is what you get **with the safety feature removed**:

> "`test_ocr_ban_card.py` scores **better** under the regression (**18/18, zero
> abstentions**) than it does correctly configured (**16/18, two abstentions**) — so the
> metric the test prints actively rewards reintroducing the bug."

The correctly-configured result — `cutoff=0.85, allow_surname_fallback=False` — is
**16 resolved + 2 safe abstentions + 0 wrong**. `LESSONS.md:17` lists this as failure
pattern #1 of the whole project. The headline number in the experiments log is the one
that pattern is about.

**Corrected wording:**
> `:91` — "**Result: 16/18 known cards resolved, 2 safe abstentions, 0 wrong**, across 3
> independently-scrolled frames, with the strict settings the ban path actually uses
> (`cutoff=0.85, allow_surname_fallback=False`). Note 18/18 with zero abstentions is what
> you see if those settings are removed — that is the N1 regression, not an improvement.
> See LESSONS.md §1."
> `:466` — "| Ban-screen cards | tesseract + strict roster match | **16/18 + 2 abstain, 0
> wrong** (dormant: `TRUST_ROSTER_ONLY` skips this path) |"

---

## Tier 2 — measured numbers with wrong provenance or wrong denominators

### 11. The hand-label corpus is double-counted, and "inter-rater agreement" has almost no overlap to measure

**Location:** `hand_digit_reader.py:180-197`.

**As written:**
> "Observed value bounds, confirmed across two fully independent sources:
>   - KNOWN_BAN_ROSTER: 33 cards read off the ban screen
>   - **1,126 player cards** hand-labelled from gameplay by **four independent readers
>     (100% inter-rater agreement**, see LOCAL_VISION_EXPERIMENTS.md §18)
> **1,159 observations**, none outside these ranges."
> and "…measured across **299 tactics cards and 1,126 player cards**."

**`[REPRO]` What the label files actually contain.**

```
hand_labels.json    260 frames   (master; contains every frame in the other three)
hand_labels_2.json   60 frames   ⊂ master
hand_labels_3.json   62 frames   ⊂ master
hand_labels_4.json   80 frames   ⊂ master

pairwise overlap: _2∩_3 = 0,  _2∩_4 = 0,  _3∩_4 = 2
union = 260 unique frames;  naive sum = 462
```

Summing all four files gives 1,126 player + 299 tactics cards — exactly the figures in the
docstring. Deduplicating to the 260 unique frames gives **600 player + 155 tactics cards**
across **151 usable frames**. The corpus is inflated ~1.9x by counting the master file's
copy of each pass alongside the pass itself.

**"Four independent readers, 100% inter-rater agreement" is not supportable from these
files.** The three pass files cover essentially disjoint frame ranges (`_2` = 201103-201715,
`_3` = 201720-202556, `_4` = 202538-221736), so there is nothing to compare between raters
except **2 frames** shared by `_3` and `_4`. Those 2 do agree card-for-card. Comparing a
pass against the master is self-comparison, and it is not even clean: the master's card
list differs from `_2` on 1 frame, `_3` on 5 frames, and `_4` on 4 frames — 10
disagreements that a "100% agreement" claim does not survive.

**What survives.** The *ranges* themselves hold on the deduplicated set:
power 4-9, secondary 0-3, no exceptions in 600 cards. `1,126 + 33 = 1,159` is arithmetically
consistent but rests on the inflated count; the honest figure is **600 + 33 = 633**.

The same inflated denominators propagate into `MATCH_DATA_ANALYSIS.md:331-334`
("0 of 370 power-4 cards", "0 of 128 power-6 cards", "0 of 34 power-9 cards"); the
deduplicated counts are 205, 64 and 16. The *conclusions* there survive — see finding 20 —
but the sample sizes are ~1.9x smaller than stated.

**Corrected wording:**
> ```
> # Observed value bounds, confirmed across two independent sources:
> #   - KNOWN_BAN_ROSTER: 33 cards read off the ban screen
> #   - 600 player cards over 151 usable frames, hand-labelled from gameplay
> #     (hand_labels.json is the master set of 260 unique frames; hand_labels_2/3/4
> #     are per-pass SUBSETS of it, so summing the four files double-counts —
> #     the 1,126 figure previously quoted here was that sum).
> # 633 observations, none outside these ranges.
> #
> # NOT an inter-rater agreement figure: the three passes cover disjoint frame
> # ranges (only 2 frames overlap between passes, and those agree). The master
> # differs from the passes on 10 frames.
> ```

---

### 12. `MAX_TACTICS_BONUS = 3` is not supported by the measurement cited for it

**Location:** `hand_digit_reader.py:194-197`.

**As written:**
> "Tactics bonuses (1-3) and player powers (4-9) are DISJOINT — **measured across 299
> tactics cards and 1,126 player cards**. So the top badge digit alone identifies the card
> type; no icon detection needed."
> `MIN_TACTICS_BONUS, MAX_TACTICS_BONUS = 1, 3`

**`[REPRO]` What the corpus shows.** Over the deduplicated 155 labelled tactics cards
(and over all 299 raw records):

```
bonus 1: 134    bonus 2: 21    bonus 3: 0
names: SPEED BOOST 67, POWER SWING 51, FIELDING PLAY 19, PITCH FOCUS 18
```

**No bonus-3 tactics card appears anywhere in the labelled data.** The observed range is
**1-2**. The upper bound of 3 is inherited from `simulate.py`'s assumed
`TACTICS_POOL_BATTING` / `TACTICS_POOL_PITCHING` (`:62-71`), which are modelling guesses,
not observations. `MATCH_DATA_ANALYSIS.md:78` independently flags the same thing about a
logged row: *"`opp_tactics_bonus=3`, **a value never seen in 299 labelled tactics
cards**"*.

**Why this can cause a wrong decision.** `validate_card` (`:203-212`) accepts
`power ∈ [1,3]` with `secondary == 0` as a legal tactics card. `QA_VISION.md:300-313`
shows the single most common held-out failure is a lost power badge promoting the shield
(0-3) into the "power" slot — five instances, all `valid=True`:

```
(7,1) -> (1,0)   (5,1) -> (1,0)   (5,1) -> (1,0)   (4,3) -> (3,0)   (1,0) -> (3,0)
```

Two of those five land on `power=3`, which is only accepted because `MAX_TACTICS_BONUS`
is 3. Tightening the bound to the measured 2 would convert those two silent kind-flips
into `valid=False`, i.e. into a fall-back-to-vision. The bound that widens the hole is the
one with no measurement behind it.

**Corrected wording:**
> ```
> # Tactics bonuses and player powers are DISJOINT, so the top badge digit alone
> # identifies the card type; no icon detection needed.
> #
> # MEASURED: 600 player cards, powers 4-9, no exceptions. 155 tactics cards,
> # bonuses 1 and 2 ONLY — a bonus of 3 has never been observed in the labelled
> # corpus (one match_log row claims opp bonus 3; see MATCH_DATA_ANALYSIS.md:78,
> # which flags it as unseen). The 3 below is inherited from simulate.py's ASSUMED
> # tactics pool, not from data.
> #
> # This bound is not cosmetic: a lost power badge promotes the shield (0-3) into
> # the power slot, and validate_card() then accepts it as a legal tactics card —
> # the dominant held-out failure (QA_VISION §3, 5 of 7 wrong cards). Two of those
> # five land exactly on power=3. Narrowing to 2 would catch them; do it only with
> # a live check that bonus-3 cards really do not exist.
> MIN_TACTICS_BONUS, MAX_TACTICS_BONUS = 1, 3
> ```

---

### 13. `73.6%` / `3.30 power` reproduce only under an unstated hand model

**Location:** `decision_engine.py:133-138`.

**As written:**
> "Measured over **20,000 simulated runner turns against the real roster's stat
> distribution**, that gave up a stronger pitcher on **73.6%** of them, surrendering
> **3.30 power on average** (up to 5)."

**`[REPRO]` What I get.** Comparing `max(key=(secondary, power))` against
`max(key=power)` over 20,000 runner turns:

| hand model | gave up power on | mean sacrificed | max |
|---|---|---|---|
| `simulate.draw_hand("pitching")` — the repo's own model, `TACTICS_FRACTION = 0.5` | **46.9%** | 2.76 | 5 |
| 3 player cards drawn from `CARD_POOL` | 61.4% | 2.77 | 5 |
| 4 player cards | 70.4% | 3.02 | 5 |
| **5 player cards** (no tactics slots) | **74.1%** | **3.22** | 5 |

The quoted 73.6%/3.30 sits on the **5-player** row. That is an all-player hand — a hand
composition `simulate.py:73` explicitly models as roughly half tactics cards, giving ~2.5
player cards in practice. The "up to 5" is right in every variant.

So the claim is not wrong about the roster; it is silent about the term that dominates the
answer. Stated against the project's own hand model the effect is **46.9% / 2.76**, still
a strong argument for the rewrite, but 1.6x smaller than advertised.

**Corrected wording:**
> "Measured over 20,000 simulated runner turns against the real roster's stat
> distribution. The result depends heavily on how many PLAYER cards a hand is assumed to
> hold, which the roster does not determine: with the 5-player hand used for the original
> measurement it gave up a stronger pitcher on **73.6%** of turns for **3.30** power on
> average; under `simulate.draw_hand("pitching")` (`TACTICS_FRACTION = 0.5`, ~2.5 player
> cards) it is **46.9%** for **2.76**. Worst case is 5 power either way. Re-derivable with
> `simulate.draw_hand` — state the hand model when quoting this."

---

### 14 & 15. The simulator win rates no longer reproduce

**Locations:** `decision_engine.py:79-83`; `HEURISTICS.md:40-56`, `:66-70`, `:185`.

**As written:**
> `decision_engine.py:80-83` — "Simulation-informed (2026-08-23, see simulate.py): a
> 500-match heuristic-vs-heuristic tournament showed always-boosting beats holding tactics
> back 'for a bigger payoff turn' by a wide margin (**79% win rate**)."
> `HEURISTICS.md:55` — "**78.6% vs. no-tactics**, up from the old logic's 72.2% — real,
> validated improvement."

**`[REPRO]`** `python3 simulate.py`, unmodified, seed 42, 500 matches:

```
current heuristic vs naive (no tactics)   : 86.2% / 3.4%  (draws 10.4%)
current heuristic vs naive (always boost) : 35.8% / 37.6% (draws 26.6%)
naive (no tactics) vs naive (always boost):  3.6% / 86.2% (draws 10.2%)
```

Two problems.

**(a) The numbers moved** because `best_pitching_play` changed. 78.6% → **86.2%**.

**(b) The docstring attributes the figure to the wrong comparison.** "79% win rate" is
offered as evidence that *always-boosting beats holding tactics back*. Per
`HEURISTICS.md:40-45`, that comparison is the second table row — situational vs
always-boost, where situational won **11.2%**. The ~79% figure is
*current vs no-tactics*, a different experiment. The conclusion is still supported; the
citation is not.

**(c) Even the unchanged rows drift.** `no-tactics vs always-boost` involves no project
heuristic at all, yet it moved 3.0% → 3.6%, because `simulate.py`'s `__main__` seeds once
and runs three tournaments off one RNG stream — so any change to the first tournament
shifts the third. Nothing documents that the three results are not independently seeded.

**Corrected wording (`decision_engine.py:79-85`):**
> "Simulation-informed (`simulate.py`, seed 42, 500 matches). Two distinct results, often
> conflated: (1) always-boost beats the old hold-tactics-back logic decisively — the old
> logic won only **11.2%** of matches against it; (2) the current heuristic beats a
> no-tactics baseline. Figure (2) was 78.6% on 2026-08-23 and is **86.2%** after the
> 2026-08-25 `best_pitching_play` rewrite. Re-run before quoting; note `__main__` seeds
> once for all three tournaments, so any change shifts every later result."

---

### 16. The settle-gate table is a rate-coupled artefact

**Location:** `orchestrator.py:1197-1219`, anchor `hand alone (< 8.0)`.

**As written:**
> ```
> #   gate                          continuation   latency p50   p90
> #   hand alone (< 8.0)                  1.6%        2.01 s    6.01 s
> #   hand AND legacy_roi                 3.3%        ~2.2 s   17.97 s
> #   legacy_roi alone (the old code)    12.3%        2.24 s   14.07 s
> ```
> "**COUNTERINTUITIVE, AND THE DATA IS STRONG** … CIs for 12.3% vs 1.6% do not overlap at
> n=122."

**Why it is not verifiable as stated.** `QA_VISION.md:202-234` re-measured the same gate on
the same frames with the look-ahead window **held fixed** instead of tied to the poll rate:

```
fixed 2.16 s window:   poll 0.54 s -> 14.4%      poll 1.08 s -> 16.6%     (1.15x)
rate-coupled (as in the source's table): 1.7%              6.6%           (4x)
```

> "Almost all of the apparent safety gain is the metric's window shrinking with the poll,
> not the gate getting better. The '1.6%' quoted in the source is a rate-coupled number
> derived at ~1 Hz … **This is the number that should not be trusted, and it is the one
> the region-set choice rests on.**"

QA_VISION is careful not to claim the hand-alone gate is *wrong*, only that the evidence
does not survive restatement. Two further caveats the comment omits: the numbers come
from `SETTLE_TIMING_ANALYSIS.md`, which was **simulated** against a **~1 Hz single-session
log** (its own §"Not supported by this data" says "Any claim about behaviour at 0.3 s poll
spacing" is unsupported), and production now polls at **0.15 s**, twice as fine again.
`QA_VISION.md:171-189` extrapolates the p90 of *genuine* hand motion at 0.15 s to **7.5
against a threshold of 8.0** — i.e. real animation may fall under the gate.

The file already carries an honest note about this at `:1405-1413` ("The percentiles are
therefore upper bounds of unknown tightness"), but it sits 200 lines below the table and
does not qualify the "DATA IS STRONG" claim.

**Corrected wording — insert above the table:**
> ```
> # CAVEAT FIRST: every figure in this table is SIMULATED against a ~1 Hz single-session
> # frame log, and the continuation rate is rate-coupled — its look-ahead window shrinks
> # with the poll interval. Re-measured with the window held fixed (QA_VISION.md §2d),
> # halving the poll moves it 16.6% -> 14.4%, not 6.6% -> 1.7%. So the 1.6-vs-12.3 gap
> # below is mostly the metric, not the gate. Gating on `hand` alone is still the right
> # call on latency and on the geometric argument (legacy_roi does not contain the hand
> # at all), but do not cite these percentages as measured safety.
> # Separately: at the production 0.15 s poll the p90 of GENUINE hand animation
> # extrapolates to ~7.5 against SETTLE_THRESHOLDS["hand"] = 8.0 (QA_VISION §2c) — the
> # margin may be negative. settle_stats_summary() is the instrument that will settle it.
> ```

---

### 17. `LOCAL_VS_API.md` contradicts itself about whether the ban OCR path runs

**Location:** `LOCAL_VS_API.md:19` and `:40` vs `:163-192`.

**As written:**
> `:19` — "**Ban-card identity** … Local-first: resolves a card's name and looks its stats
> up in `KNOWN_BAN_ROSTER`. Abstains … the caller then falls through to
> `read_ban_row_cards()`. **This is the only genuine local-first-with-API-fallback path in
> the project.**"
> `:40` — "**Ban-screen card reads** … Only fires for grid positions `ocr_ban_card_name()`
> refused, or when the roster lookup can't cover the batch."
> `:163-172` (§4d) — "`TRUST_ROSTER_ONLY = True` removes vision from the ban screen
> entirely… | | vision calls | local name OCRs | | before | 4 | 12 | | after | **0** |
> **0** |"

§1 and §3 describe the pre-`TRUST_ROSTER_ONLY` design; §4d, in the same document,
documents its removal. §1 is the table a reader consults for "what runs locally today",
and it is the wrong one.

Also in §1: **"7 call sites"** for `detect_ban_grid_locked` `[REPRO]` — there are **2**
actual invocations (`orchestrator.py:2256`, `test_ban_grid_locked.py:47`); the other five
hits are prose mentions. `mask_low_contrast_regions`'s "5 call sites" is correct.
And `detect_ban_grid_locked` is described as "PIL/numpy local contrast" — it stopped using
PIL filters when `_local_contrast` was introduced.

**Corrected wording:**
> `:19` — "**Ban-card identity** | `ocr_ban_card_name()` — tesseract + strict roster match
> | **DORMANT** | Skipped entirely while `TRUST_ROSTER_ONLY = True` (see §4d) —
> `read_full_ban_collection` `continue`s past it. Still the design of record for
> `trust_roster=False`, where it is the only genuine local-first-with-API-fallback path."
> `:17` — "…Pure pixel math, no model. **Separable numpy** (`_local_contrast`), not PIL,
> since 2026-08-26. **2 call sites.** With `TRUST_ROSTER_ONLY` this is the only live
> vision component on the ban path."

---

### 18. `MATCH_DATA_ANALYSIS.md` §4 grades a selector that no longer exists

**Location:** `MATCH_DATA_ANALYSIS.md:386-403`.

**As written:**
> "`best_pitching_play`'s fielding-priority branch fires only when runners are on, and it
> picks `max(secondary, power)` — so **one fielding pip outranks any amount of pitch
> focus**… Row 30 is the concrete instance HEURISTICS.md §2 was waiting on: a 5-power
> pitcher played against a 9-power batter… **Do not act on it.**"

**Why it is wrong.** The selector was replaced. Row 30's failure mode — a 5/1 chosen over
a stronger pitcher — is now bounded to at most 1 power by `FIELDING_POWER_BUDGET`.
The section is a correct historical record of a defect that has since been fixed, but it
reads in the present tense and ends with an instruction ("do not act on it") that was
overtaken. A reader arriving from `HEURISTICS.md:79-84` gets a coherent, entirely stale
picture.

**Corrected wording — prepend to `:386`:**
> "**(Superseded 2026-08-25.)** `best_pitching_play` no longer uses
> `max(key=(secondary, power))`. It maximises power and may pay at most
> `FIELDING_POWER_BUDGET = 1` for fielding, so the row-30 pattern below — 4 power
> conceded for 1 fielding pip — can no longer occur. Kept as the record of the defect
> that motivated the change."

---

### 19. The `~150-200 logged turns` target is contradicted by two other analyses

**Locations:** `orchestrator.py:170-172` (the `MATCH_LOG_FILE` removal plan),
`HEURISTICS.md:83`, `PENDING_LIVE_VALIDATION.md:169`.

**As written:** all three say the log needs "~150-200" turns before the secondary question
can be answered.

**Contradicted twice, in opposite directions.**
- `MATCH_DATA_ANALYSIS.md:210-224` computes the requirement properly and says
  **"the removal plan's stated target of '~150-200 logged turns' is too small"** — ~284
  logged turns to detect a 20-point effect, ~506 for 15, ~1,133 for 10.
- `analyze_match_log.py`, run today, prints its own estimate from the observed effect
  size: **"roughly 38 usable rows per group … about 156 logged turns (~8 matches)"** —
  which lands back on ~150-200 by a different route.

So the shipped script agrees with the number that the shipped analysis document says is
wrong, and nothing reconciles them. The difference is that the script's estimate is
powered on the *observed* effect size (0.64 sd, from 19 rows), which is itself the
quantity in question — a circularity the script does not flag.

**Corrected wording (`orchestrator.py:170-172`):**
> "REMOVAL PLAN: once match_log.jsonl has enough rows to answer the secondary question.
> **The required number is disputed:** `analyze_match_log.py` estimates ~156 turns from
> the *observed* effect size (circular — that estimate moves with the data), while
> `MATCH_DATA_ANALYSIS.md` §2 computes ~284 turns for a 20-point effect and ~1,133 for a
> 10-point one. It also warns that no number is meaningful until the `outcome` labeller is
> fixed, since the bias it introduces cannot be averaged away. Do not treat '150-200' as
> settled."

---

### 20. `KNOWN_BAN_ROSTER` stats contradicted by the labelled corpus, with the contradiction undocumented

**Locations:** `orchestrator.py:1897-1931` (roster), `:1900` (the "corrected" comment),
`simulate.py:35-41` (the duplicate pool).

**As written (`:1897`):**
> `(0, 2): PlayerCard('Harold "Fisto" Blunt', 9, 3),  # corrected 2026-08-24: live capture showed secondary=3, table had 1`

and the roster's header (`:1881-1896`) says the table is "compiled from this session's
clean 33-card scan" and "if a future vision fallback ever disagrees with an entry here,
trust the vision read over this table for that run."

**`[REPRO]` What the labelled corpus says.** Over the 600 deduplicated labelled player
cards, four `(power, secondary)` pairs the roster asserts have **zero** occurrences:

| pair | roster cards claiming it | occurrences |
|---|---|---|
| 4/0 | William Lee-Gains, Joshua Diaz | 0 (of 205 power-4 cards) |
| 6/2 | Zachary Lee, Noah "The Rat Baron" Kelly | 0 (of 64 power-6 cards) |
| 9/1 | Jacob "Cheesehead" McQueen | 0 (of 16 power-9 cards) |
| 9/3 | Harold "Fisto" Blunt | 0 |

Every one of the 64 labelled power-6 cards has `secondary = 0`, while the roster lists two
6/2 cards. This reproduces `MATCH_DATA_ANALYSIS.md:325-342` (at its inflated denominators).

**Why the `(0,2)` comment is the sharp end.** It records the correction to 9/3 as a settled
fact ("live capture showed secondary=3"), and that value has **zero** support in the
largest ground-truth set in the repo. The comment does not say the two references disagree;
`MATCH_DATA_ANALYSIS.md:338-339` does — *"One of the two references is wrong about
`secondary`. This matters directly: `secondary` is the stat under investigation, and there
is currently no single trusted reference to validate a read against."* None of that is
visible at the roster.

`simulate.py:35-41` handles the same class of problem well and is worth copying: it names
the conflict, names the enforcing test, and names the unresolved case ("Papa Jody Gain
remains disputed (roster 5/0, here 5/2) with no evidence either way"). `[REPRO]` I diffed
`CARD_POOL` against `KNOWN_BAN_ROSTER` by AST: 33 vs 33, one disagreement, exactly the one
documented.

**Under `TRUST_ROSTER_ONLY` this table is the sole input to `choose_bans()`.** `choose_bans`
sorts on `power` only, so a wrong `secondary` cannot currently mis-ban — but it does feed
`simulate.py`'s tournaments (which reason about `secondary`) and every roster-vs-log
comparison.

**Corrected wording — add above the dict:**
> "**Known conflict with the other ground-truth source.** Four `(power, secondary)` pairs
> in this table appear ZERO times in the 600 hand-labelled gameplay cards: 4/0, 6/2, 9/1,
> 9/3 — and all 64 labelled power-6 cards read `secondary = 0` while this table lists two
> 6/2 cards. One of the two references is wrong about `secondary`, and nothing currently
> arbitrates (MATCH_DATA_ANALYSIS.md §3f). `power` is not in dispute and is the only field
> `choose_bans()` reads, so bans are unaffected; anything that reasons about `secondary`
> from this table is on contested ground."
> and at `:1900`: "`# 'corrected' 2026-08-24 from one live capture (table had 1). NOT
> corroborated: 9/3 appears 0 times in 600 labelled cards.`"

---

### 21-30. Shorter items

**21. `input_controller.py:9` — "KEYMAP below is intentionally blank."** `[CODE]` It has
been fully populated since 2026-08-23, with per-key confirmation notes. The docstring also
says "Everything else here is ready to go", implying the module is unfinished. *Corrected:*
"KEYMAP is filled in from the Chiaki-ng Keys settings screen; every entry carries a note
saying whether the binding and its meaning were confirmed against this game. Two are still
assumptions — `select_card` and `toggle_pause`."

**22. The tactics-boundary stop describes a mechanism that no longer runs.**
`orchestrator.py:2301-2315`, anchor `The tell is free and already computed`:
> "tactics cards have no player-name banner, so `ocr_ban_card_name` returns None for every
> position (verified against real tactics frames — all ten positions OCR to empty)."

`[CODE]` Under `TRUST_ROSTER_ONLY` the loop `continue`s past `ocr_ban_card_name` at
`:2278-2281`, so `roster_hits` being empty now means only "no roster coverage" — a much
weaker signal than the OCR evidence described, and the branch fires on it. The same stale
story is told in `LESSONS.md:188-200` and `LOCAL_VISION_EXPERIMENTS.md:1040-1042` ("That is
fixed by the local tactics-boundary stop"), both of which also still present the 149-of-175
seconds ban-screen cost as current — that measurement predates both `TRUST_ROSTER_ONLY`
and the 6.27 s → 22 ms `_local_contrast` change. *Corrected:* "…so with `trust_roster=False`
`ocr_ban_card_name` returns None everywhere here. **Under `TRUST_ROSTER_ONLY` that OCR is
never run**, and this condition degenerates to 'the roster does not cover these rows',
which the `trust_roster` branch below handles on its own. The message's '~2 vision calls'
saving applies only to the fallback path."

**23. `ocr_scoreboard` "3 real screenshots".** `orchestrator.py:1002`:
> "Verified 2026-08-24 against 3 real screenshots (different save states), exact match on
> all 6 numbers every time."

`[CROSS]` `test_image_pipeline.py:8` says the corpus was "widened from 3 to 7 real frames",
and `LOCAL_VS_API.md:28` reports "7/7 frames exact". `PENDING_LIVE_VALIDATION.md:75-76`
also still says "6/6 numbers across 3 real screenshots". *Corrected:* "Verified against 7
real frames (widened from the original 3 on 2026-08-25; see `test_image_pipeline.py`),
exact on every number."

**24. "29% of cards genuinely have none" — right number, wrong denominator elsewhere.**
`[REPRO]` On the deduplicated corpus: **174/600 = 29.0%**. So
`hand_digit_reader.py:219`, `orchestrator.py:1118` and `LOCAL_VS_API.md:30` are correct,
and `MATCH_DATA_ANALYSIS.md:313`'s "349/1126 = **31%**" is the one distorted by the
double-count. Neither states the denominator it used. *Corrected:* quote it as
"29% (174 of 600 deduplicated labelled player cards)" everywhere, and fix
`MATCH_DATA_ANALYSIS.md:313`.

**25.** Covered in finding 17.

**26. The "blind 0.5 s sleep" no longer exists.** `PENDING_LIVE_VALIDATION.md:154-157` and
`:178-182` both describe "the blind 0.5s sleep before `read_matchup_reveal()`, in `run()`'s
'turn' branch" as the outstanding risk. `[CODE]` `orchestrator.py:3302-3311` replaced it
with `wait_for_reveal_cards()` and says so explicitly ("Was a blind `time.sleep(0.5)`").
The item is also still listed under "Waiting on real match data" as untested, when the
mechanism it names is gone. Same doc, `:130`, points at "around line 1410" for code now at
~3356. *Corrected:* mark item 2 as "mechanism replaced 2026-08-25 by
`wait_for_reveal_cards()` (rising-edge presence detection, not a settle); still never
validated against a live reveal, so the *question* stands but the *risk described* does
not."

**27. `select_bans_and_start_full` references a deleted function.** `input_controller.py:273`
opens "Scroll-aware version of `select_bans_and_start` for a collection that extends below
the initially-visible rows." `[CODE]` `select_bans_and_start` lives in
`_obsolete/input_controller_dead_fns.py`. A reader looking for the non-scroll-aware
"original" will not find one in the live tree. *Corrected:* "Selects bans across a
collection that extends below the initially-visible rows. (Replaced the name-based
`select_bans_and_start`, now in `_obsolete/` — see N1 below for why position, not name.)"

**28. `SETTLE_TIMING_ANALYSIS.md` is written against a superseded poll interval and
superseded call sites.** `:63-64` "The production code polls at **0.3 s**"; `:250` "The code
requires 2 polls at 0.3 s = a 0.6 s stability window"; `:381-382` "Present calls use
3.0-4.0 s (orchestrator.py:1533, 1557, …) and the 8.0 s default at line 2117";
`:397` "The `max_wait=3.0`/`4.0` call sites are truncating 25-38% of events."

`[CODE]` `poll_interval` is **0.15 s** (`orchestrator.py:1349`) and every `max_wait` in the
file is now 6.0 or 8.0 — the 3.0/4.0 sites are gone. This matters beyond tidiness: the
document's central caveat is that its 0.53 s log cannot resolve the production rate, and
the true gap is 3.5x worse than the 0.3 s it assumes, which weakens the monotonicity
argument it leans on at `:306-309`. Its region table at `:24-26` also cites
`orchestrator.py:942/737/729` for constants now at 1176/971/963. *Corrected:* add a header
note — "Written when the loop polled at 0.3 s and `max_wait` was 3.0-4.0 s. Production now
polls at **0.15 s** and every `max_wait` is 6.0-8.0 s. The resolution caveat in §0 is
therefore understated by ~2x; see QA_VISION.md §2 for a rate-independent restatement."

**29. `MAX_STUCK_ATTEMPTS` arithmetic.** `orchestrator.py:66-69`: "If the screen goes
unrecognized … for this many polls in a row, stop … At the ~2s poll interval used below,
this is **roughly a minute** of being stuck." 15 × 2 s = **30 s**. In practice the guarded
branches also call `wait_for_screen_to_settle(max_wait=8.0)`, so real elapsed time varies
from ~30 s to ~2.5 min depending on which branch is looping — which is the useful thing to
say. *Corrected:* "…this is ~30 s on the bare `time.sleep(2)` paths and up to ~2.5 min on
the branches that also wait for the screen to settle."

**30. Two QA_VISION findings are now stale in the *other* direction.** `QA_VISION.md:43`
(V1) says the cursor-highlight lock flip "crosses the **100** threshold" and is "Live in
the only ban path that still runs" — the threshold has since been raised to 124.0
specifically to fix it (`orchestrator.py:439-456` cites the same +20-26 cursor effect).
`QA_VISION.md:48` (V6) says `ocr_runner_card` "calls `match_roster_name` with the **loose**
defaults" — it now passes `cutoff=0.70` (`orchestrator.py:2149`). Both should be marked
FIXED with the date, or the summary table will send a reader to re-fix them. Note the two
docs also disagree on the V6 experiment's size: QA_VISION says "21 of 25 plausible
uncatalogued names", the code comment says "15 plausible names … force-matched 12 of them".

---

## The inverse: important non-obvious behaviour with no documentation

The repo has a documented instance of the cost here — `orchestrator.py:614-624` and
`:637-647`, where unifying `BAN_GRID_ROW_Y_FRAC` (read as **width** fractions) with
`BAN_CARD_ROW_TOP_FRAC` (**height** fractions) took a reader from 6/6 to 0/6 and returned
*wrong names* rather than `None`. That comment is exemplary and should not be touched.
These are the places with the same shape and no such warning.

**A. `SETTLE_REGION_SETS.get(name, default)` swallows unknown names.**
`orchestrator.py:1378` and `:1550`. An unrecognised region set is not an error; it silently
becomes the combined gate that this same file measures as the slowest and least safe. The
docstring actively advertises a name (`"reveal"`) that triggers it. *Add:* a comment at
`SETTLE_REGION_SETS` saying the lookup is deliberately forgiving and that a typo therefore
degrades silently — or raise on an unknown key.

**B. `MASK_CONTRAST_THRESHOLD` serves two functions computing two different statistics.**
Covered in finding 7. Nothing at the constant, at `mask_low_contrast_regions`, or at
`detect_ban_grid_locked` mentions the other consumer. A future reader recalibrating for the
ban grid — as just happened — has no way to know they are also changing how much of a
gameplay frame gets blacked out. This is the single most "simplify-able" hazard I found:
the two look like the same measurement and are not.

**C. The `trust_roster` parameter is invisible from the docstring.**
`read_full_ban_collection(max_presses, use_cache, trust_roster=None)` — the parameter that
decides whether ~80% of the function's body executes is not named in its docstring
(finding 5). Someone deleting "dead" code (`_read_ban_rows_separately`, the per-row retry,
the mismatch counter) would find no test exercising them on the default path and no
docstring explaining they are the `trust_roster=False` fallback.

**D. `hand_to_cards` does not filter by role.** `orchestrator.py:2502-2511` splits only on
`kind` ("player" vs "tactics"), and `READ_STATE_PROMPT` assigns `kind: "player"` to both
BATTER and PITCHER cards. `best_batting_play` then takes `max(power)` over everything
handed to it. If a hand can ever contain a pitcher during a batting half, the engine plays
it. This is written down **only** in `MATCH_DATA_ANALYSIS.md:405-413`, which also notes two
logged rows with `our_card_name = "Pitcher"` during a batting half. Nothing in the code
says the invariant "a hand is role-homogeneous" is an assumption rather than a guarantee.
*Add:* a one-line note at `hand_to_cards`.

**E. `group_into_cards`' `x_tolerance = 0.06` contradicts its own file's dedupe note.**
`hand_digit_reader.py:212` clusters columns at 0.06, while `:104-106` (inside the worker)
says badges from adjacent fanned cards "can sit **~0.03 apart in x**" and that the dedupe
radius "must stay TIGHT" at 0.015 for exactly that reason. Two constants in one file,
governing the same geometry, differing by 4x, with a rationale attached to only one.
`QA_VISION.md:333-341` shows the consequence: nine digits 0.05 apart chain transitively
into a single card, and two real cards 0.05 apart collapse into one fabricated
`valid=True` card. *Add:* a note at `x_tolerance` saying why it is 4x the dedupe radius,
or reconcile them.

**F. The frozen-stream detector hashes only the `hand` region.**
`orchestrator.py:2826-2845` computes `blake2b` over `_grab_settle_regions(("hand",))`
alone. On a ban screen or a menu that crop is not a hand at all, and nothing explains why a
hand-region digest is an adequate proxy for whole-screen liveness.

*Partially addressed mid-audit.* A concurrent agent replaced `MAX_IDENTICAL_FRAMES = 12`
with `FROZEN_STREAM_SECONDS = 90.0` at 00:47, which fixes the poll-rate coupling I was
about to flag (12 polls was ~2.4 s, short enough to abort on a legitimately paused game)
and adds a vision probe that distinguishes "paused" from "dead". The new comment carries a
fresh measured claim, and **it reproduces exactly**: `[REPRO]` over all 1,937 logged frames
from both sessions, the longest run of consecutive byte-identical `hand` crops is **0** —
so the detector cannot fire on live play. Good claim, correctly stated, sample size given.

What remains undocumented is the region choice. The measurement is of the `hand` crop
specifically, and the supporting reasoning ("even menus and idle turn screens differ frame
to frame") rests on a corpus whose newer session is 111/126 ban-screen frames — so the menu
case is covered, but *why this region* is still unanswered in writing. *Add:* one line
saying the digest uses the hand crop because it is already grabbed for the settle gate, and
that the zero-run figure is measured on that crop rather than on the whole frame.

**G. `load_progress` has no docstring, and its return shape changed twice in one day.**
`orchestrator.py:98-116`. It returned a 4-tuple, then a 5-tuple (`match_in_progress`), and
as of 00:47 a **6-tuple** (`bans_done_this_match`) — with no docstring at any point. The
return shape is exactly the thing a caller can get wrong, and it is the only thing not
written down. `save_progress` got a thorough docstring for the `match_in_progress` change
(`:133-149`), and that docstring was **not** extended when `bans_done_this_match` was added
in the same edit — so it now explains one of its two persisted flags and silently carries
the other. Only `orchestrator.run()` and `test_state_io.py` unpack `load_progress` today.

*Add:* to `load_progress`, "Returns `(wins, losses, draws, balance, match_in_progress,
bans_done_this_match)`; `balance` is `None` and both flags are `False` when there is no file
yet." And extend `save_progress`'s docstring to say why `bans_done_this_match` is persisted
(ban selection is a toggle, so re-entering the ban screen after a restart would un-ban what
was already banned).

**H. Cross-file line references drift and there are many of them.**
`decision_engine.py:149` and `orchestrator.py:2589` both cite "`simulate.py:97`" for
`power_bonus`, which moved to `simulate.py:93` when another agent edited the file **during
this audit**. `test_ocr_ban_card.py:100` and `:140` cite "orchestrator.py:533" for a call
site now at 675 — and `:140` is inside an assertion *message*, so a failing test points a
reader at the wrong line. `MATCH_DATA_ANALYSIS.md` cites `:2003-2011`, `:1263-1270`,
`:1889`, `:2318-2323`; `SETTLE_TIMING_ANALYSIS.md` cites `:942`, `:737`, `:729`, `:1533`,
`:2117`; `QA_VISION.md` cites `:1139-1156`, `:1997`, `:1890`. None resolve today. *Suggest:*
cite function names, not line numbers, in anything that outlives a session.

---

## Things I checked that hold up

Recorded so they are not re-audited.

- **`_local_contrast`'s performance claim is if anything understated.** `[REPRO]` On a real
  2000x1292 frame: PIL `MaxFilter(41)`+`MinFilter(41)` pair = **14.2 s** full-frame
  (comment says ~13.8 s) and **7.4 s** on the grid crop (comment says 6.27 s); the
  separable version is **50 ms / 30 ms** (comment says 22 ms) — **250-282x**, against a
  claimed 291x. Machine variance, same conclusion. The equality claim is *stronger* than
  written: the comment says "byte-for-byte equal on the sampled cells across 6 real ban
  frames"; I got exact array equality over the **entire frame**, which is what the
  separability argument predicts.
- **Token-cost arithmetic.** "~45% cut" (386 → 211), "~25% MORE" (167+168 = 335 vs 268),
  "~55-60%" (3444 → ~1400 = 59%) all check out.
- **Value bounds.** `MIN_POWER..MAX_POWER = 4..9` and `MIN_SECONDARY..MAX_SECONDARY = 0..3`
  hold with zero exceptions across the deduplicated 600 labelled player cards.
- **`simulate.py` / `KNOWN_BAN_ROSTER` agreement.** `[REPRO]` AST diff: 33 vs 33 cards, one
  disagreement (Papa Jody Gain 5/2 vs 5/0), and `simulate.py:35-41` already documents it
  precisely, including the `_DISPUTED` set that enforces it. This is the model the rest of
  the repo's duplicated constants should follow.
- **`analyze_match_log.py`'s docstring** is accurate throughout, and unusually good about
  provenance — every one of its five numbered caveats matches what the code does, and the
  `outcome`-is-manufactured warning is exactly right.
- **`_running_under_test`, `norm_name`, `press`'s default-argument note, the N27
  `played=False` correction, `_learn_roster_entry`'s two-agreeing-reads rule, and the
  C1/C2/C3/C5 guard comments** all describe the code as it currently stands.
- **`match_log.jsonl` is clean:** 39 rows, 0 stamped `_synthetic`. The `LESSONS.md` §2
  "30 of 69 rows" figure refers to the pre-cleanup file, which is preserved as
  `match_log.jsonl.contaminated_backup_20260825_170324`.
- **`FROZEN_STREAM_SECONDS`' new measured claim** (added 00:47 by a concurrent agent):
  "the longest run of byte-identical consecutive hand crops is ZERO" over 1,937 frames.
  `[REPRO]` Exactly reproduced — 0. Sample size stated, protocol inferable, claim correct.
- **`clear_match_state.py`** (new, 00:47, concurrent agent): its docstring accurately
  describes what it does and why the stale-flag case exists. Not otherwise audited.

---

## Reproduction notes

Everything numeric above can be re-derived. Commands, all read-only:

```
python3 simulate.py                                   # win rates (findings 1, 14)
cp match_log.jsonl /tmp/x && python3 analyze_match_log.py /tmp/x   # p = 0.192 (finding 2)
```

For the label-corpus figures (findings 11, 12, 20, 24), the key facts are that
`hand_labels.json` is a 260-frame master and `hand_labels_2/3/4.json` are subsets of it:
deduplicate on frame name before counting. For finding 7's mask fractions, apply
`mask_low_contrast_regions`' tile rule to `GAMEPLAY_REGIONS_FRAC` crops of a settled turn
frame at both 100.0 and 124.0.

## Tree integrity

`DOC_AUDIT.md` is the only file I created. **I edited no source file.** A snapshot of the
tree (excluding `paddle_venv/`, `__pycache__/`, `screenshot_log/`, `hand_samples/`,
`test_fixtures/`, `_obsolete/`, `Photos*`) was taken at 00:31:39 and diffed at 00:47:35.
The diff is:

```
Files ... /orchestrator.py           differ    <- concurrent agent (frozen-stream + bans_done_this_match)
Files ... /preflight.py              differ    <- concurrent agent
Files ... /run_testing.py            differ    <- concurrent agent
Files ... /test_run_state_machine.py differ    <- concurrent agent
Files ... /test_state_io.py          differ    <- concurrent agent
Only in .: DOC_AUDIT.md                        <- this report
Only in .: clear_match_state.py                <- concurrent agent (new)
```

Every source change is attributable to the concurrent agents' work on `run()`'s guards and
progress-file state, which is their lane, not this audit's. I inspected the
`orchestrator.py` diff only far enough to confirm it did not invalidate findings above —
it changed two of them (inverse F and G), both updated. Nothing was written to
`match_log.jsonl`, `progress*.json`, `known_ban_roster_learned.json`, `diagnostics/` or
`screenshot_log/`; `match_log.jsonl` was copied to a scratch path before
`analyze_match_log.py` was run against the copy.
