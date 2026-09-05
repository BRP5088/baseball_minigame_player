# QA — vision / OCR readers

Adversarial review of `hand_digit_reader.py` and the vision/geometry half of
`orchestrator.py`. Scope was the readers, the region constants, the settle /
reveal / prompt detectors, and `validate_game_state`. `run()`'s guards,
`read_full_ban_collection`'s control flow, `decision_engine.py` and
`simulate.py` were out of scope and are not assessed here.

**Method.** Every claim below is measured against the real frame corpus
(`screenshot_log/`, 1,937 frames at 2000x1292 — 1,811 from `20260824`,
126 from `20260825`), the 260 hand-crop labels in `hand_labels*.json`, and
`KNOWN_BAN_ROSTER`. Anything I claim is covered by a test was checked by
mutating the code and confirming the test goes red; those checks ran in a
sandboxed copy of the tree. The real tree was not modified (verified by
checksum; the only changes during this session came from the two concurrent
agents, all inside `run()`/`save_progress`, none touching anything here). No
game was run, no keystroke sent — every `select_and_play`/`select_and_discard`/
`press` in the fuzz harness was stubbed and its calls captured.

**Tags.** `EXEC` = executed against real frames or real code.
`MUT` = verified by mutation. `REASONED` = argued from code, not executed.

Line numbers are against `orchestrator.py` as of 3,240 lines (23:20, after the
concurrent agents' `match_in_progress` change). Re-verified at the end of the
session: all nine test files I mutated against are byte-identical to the
current tree, and every mutation target string still occurs exactly once in the
current `orchestrator.py` — so every §8 result applies to the tree as it
stands, not to a stale copy.

---

## Answer to the headline question first

**The crops have not drifted.** The `20260825` session is pixel-identical to
`20260824` in frame geometry, and every reader that lands correctly on one
lands correctly on the other. That was the thing most likely to be wrong and
it is not (§1).

The real defects are elsewhere, and three of them are live:

| # | Severity | Finding |
|---|---|---|
| V1 | **High** | `detect_ban_grid_locked` reads a **locked** card as unlocked when the ban cursor sits on it (+20…+26 contrast, crosses the 100 threshold). Live in the only ban path that still runs. |
| V2 | **High** | `read_hand_digits`→`group_into_cards` has a second silent mode, **more common than `secondary=0`**: a lost power badge promotes the shield to "power", flipping a player card into a *valid* tactics card. 5 of 7 wrong cards in a held-out sample. Exact-hand accuracy on held-out data is **2/18**, not the 12/13 in the docstring. |
| V3 | **High** | `validate_game_state` — 5 of its 7 per-card checks are dead weight in the test, and 12 malformed payloads reach `play_one_turn` and **send real input** with fabricated values. |
| V4 | **Medium** | `input_prompt_visible` fires on **45.8%** of real ban/menu frames (196/428). The test that says otherwise picked 2 of the 8 frames in a 36-frame stretch that don't fire. |
| V5 | **Medium** | `SETTLE_THRESHOLDS`' safety margin is a sample-rate artefact. Held-fixed-window measurement: the "continuation rate" barely improves with a finer poll (16.6% → 14.4%), while the metric the constants were chosen with improves 4x (6.6% → 1.7%). At 0.15 s the p90 of genuine hand motion extrapolates to **7.5 vs a threshold of 8.0**. |
| V6 | **Medium** | `ocr_runner_card` calls `match_roster_name` with the **loose** defaults — the exact N1 defect that was fixed for the ban path. 21 of 25 plausible uncatalogued names force-match to a wrong roster card, with that card's power/secondary. |
| V7 | **Medium** | `wait_for_reveal_cards` fires on idle turn screens: the permanently-face-down pitcher card sits inside `REVEAL_CENTER_REGION` and a neighbour card is clipped by its right edge. 4 of 15 sampled frames above threshold had no reveal. |
| V8 | **Medium** | `ocr_scoreboard` never abstains on a garbled row label — it silently assigns the **opponent's** or the **ROUND dot** row to `your`. |
| V9 | **Low/latent** | `mask_low_contrast_regions` is correct on ban screens but blacks out **62–79%** of every base crop on a gameplay frame. Latent only because `read_game_state()` is always called with the default `mask_low_contrast=False`. |
| V10 | **Low** | `norm_name(123)` raises `AttributeError`, not the `ValueError` the pipeline contract promises. |

Coverage gaps found by mutation are collected in §8; the ones that matter most
are that the **hand crop can be pointed anywhere on screen** and that
`SETTLE_THRESHOLDS["hand"]` can be set to 100.0, both with a fully green suite.

---

## 1. Do the region crops still land correctly on `20260825`? — **Yes** (EXEC)

### 1a. Frame geometry is identical between sessions

Normalised cross-correlation of row and column brightness profiles between
`20260824_200458_664.jpg` and `20260825_165903_259.jpg` (both ban screens):

```
row shift   0 px   correlation 0.9978
col shift   0 px   correlation 0.9984
```

Both sessions are 2000x1292, both show the Chiaki-ng window in the same
position on the same desktop (menu bar top, dock strip right). Overlaying all
five `GAMEPLAY_REGIONS_FRAC` boxes plus `INPUT_PROMPT_REGION` and
`REVEAL_CENTER_REGION` on one frame from each session puts every box on the
same feature.

Grid scroll phase: of the 112 `20260825` ban-session frames, 27 correlate
≥0.90 with the reference frame's layout, and **all 27 sit at exactly 0 px
offset**. (The other 85 are at other scroll positions, so this estimator
cannot judge them — that is a limit of the method, not evidence of drift.)

### 1b. Ban-card OCR resolves consistently on `20260825`

`ocr_ban_card_name` run over 32 sampled `20260825` frames x 10 grid positions
(320 reads). Every name that resolved was consistent with a single coherent
`KNOWN_BAN_ROSTER` row per visible row, with **zero cross-row contamination
and zero wrong names**:

```
165901  rel0 -> roster row 0  (Johnny Drawers, Mama Jody Gain, Jenny Jody Gain, Donny Mekesz)
        rel1 -> roster row 1  (Joshua Diaz, Justin Young)
165924  rel0 -> row 1, rel1 -> row 2
165942  rel0 -> row 3, rel1 -> row 4
170002  rel0 -> row 5, rel1 -> row 6
170136  rel0 -> row 2, rel1 -> row 3
```

### 1c. Vertical tolerance is ±35 px, and there is no row-1 cliff

Synthetic frame-drift sweep, 6 frames (3 per session) x 17 shifts
(dy −40…+40 px) x 10 positions = 1,020 reads:

```
dy  -35 .. +40   correct reads unchanged (5/5 or 7/7 depending on frame)
dy  -40          drops to 3-4 correct
WRONG names at any shift, any frame: 0
```

`BAN_CARD_ROW_TOP_FRAC`'s N6 fix holds. Mutating it back to the pre-N6
geometry `[0.195, 0.395]` costs correct reads (row 1 goes 7→4 at dy ≥ +10) but
still produces **zero wrong names** — the strictness at `orchestrator.py:629`
(`cutoff=0.85, allow_surname_fallback=False`) is what actually holds the safety
property, not the geometry.

**Found nothing** on: horizontal drift (a 2% column shift is absorbed —
see M27 in §8), aspect/scale drift, and JPEG-quality differences between
sessions.

### 1d. Caveat that limits what `20260825` can prove

There are only **11 gameplay frames in the whole `20260825` session**
(`170142`–`170147`), and all 11 are the "PLAY AS THE BATTER" transition
overlay — no settled turn, no hand, no scoreboard, no runners. The 126 frames
break down as 4 bar-screen / 111 ban-screen / 11 transition. So the *gameplay*
crops (`hand`, `scoreboard`, the three bases) are validated on `20260825` only
by whole-frame alignment (§1a), not by content. Anything claiming to be
"validated on the newer session" for gameplay regions is claiming more than
the corpus supports.

---

## 2. `SETTLE_THRESHOLDS` / `REVEAL_EDGE_THRESHOLD` — how wrong can they be? (EXEC)

### 2a. The actual sample rates

```
20260824 log   n=1811   inter-frame gap  min 0.466  p50 1.003  p90 1.005 s
20260825 log   n= 126   inter-frame gap  min 0.493  p50 0.546  p90 0.601 s
production                                          0.15 s poll
```

The constants were derived from the `20260824` log: median gap **1.003 s**,
i.e. **6.7x coarser** than the loop they govern.

### 2b. Delta scales with gap; noise does not

Measured over 1,902 region pairs from three contiguous 0.5 s-cadence gameplay
runs (`203801-203918`, `203919-204125`, `221621-221724`), computing
`_mean_abs_delta` on the real `hand`/`legacy_roi`/`scoreboard` crops at k = 1…4
frames apart:

| region | gap 0.54 s | 1.08 s | 1.62 s | 2.16 s |
|---|---|---|---|---|
| hand p50 | 4.09 | 6.81 | 7.04 | 7.02 |
| hand p90 | **20.04** | **34.02** | 37.14 | 40.01 |
| legacy_roi p90 | **9.94** | **15.22** | 14.94 | 13.83 |

Isolating genuinely idle stretches (5 consecutive quiet steps):

| region | idle p99 @0.54 s | idle p99 @1.08 s | idle p99 @2.16 s |
|---|---|---|---|
| hand | **4.76** | 7.34 | 6.62 |
| legacy_roi | 3.58 | 5.81 | 2.53 |
| scoreboard | 4.78 | 7.95 | 4.84 |

So the noise floor is roughly **flat below ~1 s** while the motion signal keeps
shrinking. The thresholds were set "between idle p95 and p99" at the 1.0 s gap
— `hand: 8.0` sits just above that gap's idle p99 of 7.34.

### 2c. The quantified error

Fitting `delta ∝ gap^b` on the p90 band between the two gaps I can actually
measure:

```
hand        b = log(34.02/20.04)/log 2 = 0.76
            -> delta(0.15 s) = 34.02 * (0.15/1.08)^0.76 = 7.5   threshold 8.0
legacy_roi  b = log(15.22/9.94)/log 2  = 0.62
            -> delta(0.15 s) = 15.22 * (0.15/1.08)^0.62 = 4.5   threshold 6.0
```

**At the production poll interval the p90 of genuine animation lands below the
threshold in both gated regions.** The bounding cases: if motion were linear in
gap (b = 1) it would be 4.7 / 3.2 — worse; if the process were fully
decorrelated below 0.5 s (b = 0) it would be unchanged — fine. The 1 Hz log
cannot distinguish those, which is the concrete size of the uncertainty:
**the p90 hand delta at production rate is somewhere in [4.7, 34.0] against a
threshold of 8.0.**

Corroborating, without any extrapolation: the fraction of pairs reading
"moving" against each region's own threshold

```
hand        thr 8.0   0.54 s: 24.0%   1.08 s: 41.5%   1.62 s: 40.9%   2.16 s: 43.3%
legacy_roi  thr 6.0   0.54 s: 25.8%   1.08 s: 47.8%   1.62 s: 47.7%   2.16 s: 43.5%
```

Halving the gap from the calibration rate already halves how often the gate
blocks. Three more halvings separate 0.54 s from 0.15 s.

### 2d. The comment's "continuation rate" table measures the sample rate

`SETTLE_REGION_SETS`' justifying comment (`orchestrator.py:1139-1156`) justifies gating a turn
read on `hand` alone with "continuation 1.6% vs 12.3%". Simulating the actual
gate (`2 consecutive polls under threshold`) on the same frames, at two
cadences, with the look-ahead window **held fixed at 2.16 s** for both:

```
hand thr=8.0  poll 0.54 s: settled 292x, 42 (14.4%) followed by real animation within 2.2 s
hand thr=8.0  poll 1.08 s: settled 193x, 32 (16.6%) followed by real animation within 2.2 s
```

versus the rate-coupled version (look-ahead = one poll), which is what the
1 Hz analysis could compute:

```
hand thr=8.0  poll 0.54 s: 1.7%
hand thr=8.0  poll 1.08 s: 6.6%
```

The rate-coupled figure improves **4x** when you halve the poll interval; the
fixed-window figure improves **1.15x**. Almost all of the apparent safety gain
is the metric's window shrinking with the poll, not the gate getting better.
The "1.6%" quoted in the source is a rate-coupled number derived at ~1 Hz; at
0.15 s the same metric would read ~0.2% while the underlying risk is
essentially where it was. **This is the number that should not be trusted, and
it is the one the region-set choice rests on.**

I am *not* claiming the hand-alone gate is wrong — `legacy_roi` and `hand`
cannot be compared on my per-region metric, which counts "did *this* region
animate again", and the hand animates far more often by construction. The
claim is narrower: the evidence offered for the gate does not survive a
rate-independent restatement.

### 2e. `_fast_grab`'s width normalisation is **not** load-bearing — found nothing

`orchestrator.py:1240-1260` says mean-absolute-delta is "scale-sensitive … so
feeding a different resolution silently shifts every threshold". Measured on
160 real frame pairs, comparing deltas computed at 2000 px vs 1728 px:

```
hand        2000px p50 4.20 p90 13.92 | 1728px p50 4.02 p90 13.76  (ratio 0.96 / 0.99)
legacy_roi  2000px p50 3.92 p90  7.90 | 1728px p50 3.86 p90  7.83  (ratio 0.99 / 0.99)
```

And simulating the mss path proper (2000 → 1728 → 2000, i.e. the interpolation
loss `_fast_grab` adds):

```
hand        ratio mss/native  median 0.957  (on moving pairs, native>10: 0.992)
legacy_roi  ratio mss/native  median 0.980  (on moving pairs: 0.993)
```

≤4.3% either way. The normalisation is harmless but the risk it was written to
prevent does not exist for this metric. (It *does* exist for the reveal
gradient — see below — which is presumably where the intuition came from.)

### 2f. `REVEAL_EDGE_THRESHOLD` — the code's own numbers check out (EXEC)

Computing `_center_card_edge_fraction`'s statistic over all 1,937 frames on
both paths:

```
native p50 0.0391  p90 0.0854   |  mss p50 0.0354  p90 0.0761
mss/native ratio at p50 0.905, at p90 0.891
```

The source claims mss present-min 0.0692 vs native 0.0779 (ratio 0.888). That
reproduces. The mss-vs-native reasoning behind `0.065` is sound. The *region*
is not — see V7 in §5.

---

## 3. Silent failure modes beyond `secondary=0` (EXEC + MUT)

### V2 — `read_hand_digits` / `group_into_cards`, measured on held-out labels

PaddleOCR run end-to-end (`read_hand_digits` → `group_into_cards`) on **18
randomly sampled hand crops that `hand_labels*.json` marks `usable: true`**
(i.e. the human labeller confirmed the digits are readable). Only 7 of the 90
labelled cards carry `confident: false`, so the ground truth is solid.

```
exact hand matches            2 / 18   (11%)
hands with the wrong CARD COUNT   11 / 18   (17 cards silently dropped)
per-card, on the 7 count-matched hands   28 / 35 correct (80%)
   of the 7 wrong cards: 6 flagged valid=True, 1 flagged valid=False
```

`hand_digit_reader.py:120-124` reports "95% -> 98% correct and exact hands from
10/13 -> 12/13". Those are **tuning-set numbers**; on held-out labelled frames
the same pipeline gets 11% exact hands and 80% per-card. `validate_card()`
caught 1 of 7 errors.

Taxonomy of the 7 wrong cards:

| mode | n | what the caller sees |
|---|---|---|
| **power badge lost, shield promoted to "power"** | **5** | a *player* card becomes a **valid tactics card** |
| missed shield → `secondary=0` (the known one) | 2 | plausible player card, wrong secondary |

Concrete instances (label → read):

```
hand_20260824_200817_424   card 3   (7,1) -> (1,0)   valid=True
hand_20260824_204109_161   card 2   (5,1) -> (1,0)   valid=True
hand_20260824_204110_337   card 2   (5,1) -> (1,0)   valid=True
hand_20260824_201607_545   card 0   (4,3) -> (3,0)   valid=True
hand_20260824_202204_071   card 0   (1,0) -> (3,0)   valid=True
hand_20260824_204108_010   card 4   (9,2) -> (9,0)   valid=True   <- missed shield
hand_20260824_204110_337   card 4   (9,2) -> (9,0)   valid=True   <- missed shield
```

The kind-flip is **worse than `secondary=0`** and is baked into the design:
`hand_digit_reader.py:196-197` states that powers 4-9 and tactics bonuses 1-3
are disjoint, so "the top badge digit alone identifies the card type". When the
power badge is missed, the shield (0-3) *becomes* the top digit and
`validate_card(2, 0)` returns `True` for exactly the reason the design relies
on. A power-7 batter is indistinguishable from a bonus-1 tactics card.

Two more, both unguarded:

- **No card-count check.** A hand is always 5 cards; 11 of 18 reads returned
  fewer and nothing anywhere compares against 5.
- **Artwork digits are accepted as shields.** `group_into_cards`' docstring
  names the hazard ("painted scoreboard digits run down the right edge inside
  some card frames, exactly where a shield sits"), but `validate_card` only
  range-checks, so any artwork digit in 0-3 lands as a valid `secondary`.
  Executed: `[{x:.30,y:.20,digit:8},{x:.31,y:.40,digit:3}]` →
  `{power:8, secondary:3, valid:True}`.

**Column chaining — latent, not observed.** `group_into_cards` clusters against
`cols[-1][-1]` (the column's *most recent* member), so digits chain
transitively without bound. Executed: 9 digits spaced 0.05 apart across
x 0.05→0.45 collapse into **one** card. Two cards 0.05 apart giving
`power 7` then `shield 2` collapse into `{power:7, secondary:2, valid:True}` —
a fabricated card that passes validation while one real card vanishes.
`hand_digit_reader.py:105-106` states that badges from adjacent fanned cards
"can sit ~0.03 apart in x", which is **half** the `x_tolerance=0.06` used for
clustering. Measured on the 18 real hands, though, the smallest inter-card gap
was **0.094** (p05 0.136, p50 0.202), so this did not fire in practice. Either
the 0.03 note is about a configuration not present in this corpus, or the
tolerance is a live hazard that this sample missed; both readings are open.

### V6 — `ocr_runner_card` still has the N1 defect (`orchestrator.py:1997`)

`ocr_ban_card_name` was hardened to `cutoff=0.85, allow_surname_fallback=False`
after a wrong roster match banned the wrong physical card. `ocr_runner_card`
calls `match_roster_name(cleaned)` — **the loose defaults**. Executed against
25 plausible names not in `KNOWN_BAN_ROSTER`:

```
loose  (ocr_runner_card's actual settings):  21 / 25 force-matched to a real card
strict (the ban path's settings):             2 / 25
```

```
'Frank Coker'    -> 'Brian Coker'        (power=8, secondary=1)
'Sarah Lee'      -> 'Zachary Lee'        (power=6, secondary=2)
'Willie Brown'   -> 'William Brown'      (power=4, secondary=3)
'Joe Black'      -> 'Joel Blunt'         (power=9, secondary=0)
'Nancy Drew'     -> 'Johnny Drawers'     (power=7, secondary=1)
'Austin Powers'  -> 'Justin Young'       (power=6, secondary=0)
'Charlie Brown'  -> 'Charlie Pepper'     (power=8, secondary=0)
...21 of 25
```

Each returns the roster's *trusted* power/secondary for the wrong player. Pure
OCR noise is safe (0/40 random letter strings matched) — it is specifically
**plausible names** that get force-matched, which is the case that occurs.

This is audit-only today (`log_local_read_comparison`, `orchestrator.py:1050`).
But `read_game_state`'s own comment (`orchestrator.py:1683-1691`) argues for
promoting it, citing "local OCR confidently found a real, roster-matching
runner … confirmed 3x". Three correct matches cannot distinguish a working
matcher from a lucky one at an 84% force-match rate.

Mutation M24 confirms `test_ocr_runner.py` would go red if the strict settings
were adopted — so the loose call is *pinned in place* by the current test.

### V8 — `ocr_scoreboard` assigns rather than abstains

`orchestrator.py:961-970`: the row label is matched with `startswith`, and any
non-`OPPONENT` line with three single-character digit tokens becomes `your`
via `elif result["your"] is None`. Executed with the tesseract stage stubbed:

```
'OPPONEHT 0 1 1\nJACK PEPPER 2 0 2'        -> {'your': [0, 1, 1], 'opponent': None}
'R0UND 1 1 1\nJACK PEPPER 2 0 2\n...'      -> {'your': [1, 1, 1], 'opponent': [0,1,1]}
'D1SCARDS 0 0 0\nJACK PEPPER 2 0 2\n...'   -> {'your': [0, 0, 0], 'opponent': [0,1,1]}
'J@CK P3PP3R\nOPPONEHT 0 1 1'              -> {'your': [0, 1, 1], 'opponent': None}
```

One garbled character in a row *label* silently makes the opponent's score, or
a ROUND dot row, the player's score. There is no check that the assigned line
is the player's. Safe modes do exist: a two-digit score (10+) drops out of the
single-character `re.fullmatch(r"[0-9OoQ]", t)` filter and correctly yields
`None`, as does a blank crop.

Audit-only today (`orchestrator.py:1044`), so this is a data-quality issue for
`log_local_read_comparison`, not a live decision path.

### V10 — `norm_name` contract (`orchestrator.py:1890`)

```
norm_name(None)  -> ''
norm_name(123)   -> AttributeError: 'int' object has no attribute 'strip'
norm_name(['a']) -> AttributeError
```

`(s or "").strip()` passes non-empty non-strings straight through. Reached from
`_read_ban_rows_separately` (`norm_name(c["name"])` on raw vision output) and
from `_learn_roster_entry`. `_load_learned_roster` already guards this at
module scope (the N26 note) — the same guard is missing on the vision path.

---

## 4. `validate_game_state` — what still gets through (EXEC)

36 payloads run through `validate_game_state` and, when they passed and the
screen was `"turn"`, on into `play_one_turn` with every input function stubbed.

### 4a. Passes validation AND sends input with a fabricated value — highest severity

| id | payload | what happens |
|---|---|---|
| **H2c** | `"power": true` | `isinstance(True, int)` is `True`. Plays the card. Logs `our_power: true` into `match_log.jsonl`. |
| **H2d** | `"power": 0` | `should_redraw` fires (`max power <= 4`) → **burns a discard**. This is precisely the "power 0" defensive-discard failure that `SETTLE_REGION_SETS`' comment attributes to an unsettled frame — and the validator does not stop it, even though the ban path filters `c["power"] > 0` and `hand_digit_reader` defines `MIN_POWER = 4`. |
| **H2e/H2f** | `"power": -5` / `999` | Plays it. No range check anywhere. |
| **H2h** | `"secondary": "x"` | Plays it (batting never touches `secondary`). |
| **H3b** | tactics `"bonus": null`, one boost in hand | **Plays the tactics card**, prints "attaching swing boost (+None)", logs `our_tactics_bonus: null`. With *two* boosts of the same kind the same payload crashes instead — behaviour depends on hand composition. |
| **H3d** | tactics `"bonus": "three"` | Plays it, logs `"three"`. |
| **H4c** | 5 runners on a 3-base diamond | Accepted. Flips `best_pitching_play` into its runners-on branch. |
| **H5a** | `"your_score": null` | Accepted; `score_before: null` in `match_log`. Only `key not in state` is checked (`orchestrator.py:1661-1663`). |
| **H5b** | `"opp_score": "seven"` | Accepted. |
| **H6b** | `"discards_left": 99` | **Discards** even though the game allows 2-3. `discards_left` is never validated or clamped. |
| **H12/H13** | `"name": null` / `12345` | Plays; logs `our_card_name: null`. |
| **H7** | `{"screen": "result"}` — no `result_won`, no scores | Passes. `run()` (`orchestrator.py:2744`) does `"win" if state_json.get("result_won") else "loss"` → **recorded as a loss**. |

### 4b. Passes validation, then crashes in `play_one_turn`

Retryable (the branch is inside `try/except`), but each burns a
`MAX_STUCK_ATTEMPTS` slot:

```
H2a  player card missing 'secondary'      KeyError: 'secondary'
H2b  player card missing 'name'           KeyError: 'name'
H3a  tactics card missing 'bonus'         KeyError: 'bonus'
H2g  'secondary': null, pitching+runners  TypeError: '>' NoneType vs int
H3c  'bonus': null with 2 boosts          TypeError: '>' int vs NoneType
H4a  'runners': [{}]                      KeyError: 'name'
H4b  'runners': 'none'                    TypeError: string indices...
H4d  'runners': [null]                    TypeError: not subscriptable
H6a  'discards_left': '3'                 TypeError: '<=' str vs int
```

The root cause of the first three: the validator checks `power` and `type` but
never `name`, `secondary`, or `bonus`, while `hand_to_cards`
(`orchestrator.py:2367-2368`) indexes all of them directly.

### 4c. Escapes as the wrong exception type

The docstring promises a `ValueError`. These give `AttributeError`:

```
H8a  "hand": {"a": 1}   -> AttributeError: 'str' object has no attribute 'get'   (iterating a dict yields keys)
H8b  "hand": "none"     -> AttributeError (iterating a string yields chars)
H15  state is a list    -> AttributeError: 'list' object has no attribute 'get'
```

Callers catch broad `Exception`, so this is cosmetic today — but the message
names `'str'` when the payload was a dict, which is actively misleading.

### 4d. `discard_prompt` — the previously-reported hole, re-checked

`{"screen": "discard_prompt", "phase": "batting"}` with no hand, no scores and
no runners still passes (only the `"turn"` branch at `orchestrator.py:1660`
enforces completeness). It does **not** crash: `run()`'s `discard_prompt`
branch never calls `play_one_turn`, it just presses `confirm_play`. So the
consequence is a blind confirm keypress on a possibly-misclassified screen —
real, but far below the §4a items.

### 4e. Bool-as-int, three times

`isinstance(True, int)` is `True` in Python, and the validator relies on
`isinstance(..., int)` in three places: `hand_index` (1630), player `power`
(1638), and collection `row`/`col` (1647). Executed:
`{"screen": "ban_screen", "collection": [{"row": True, "col": False}]}` passes.

---

## 5. `mask_low_contrast_regions` and the lock detector (EXEC)

### V1 — the cursor flips a locked card to "unlocked". This is the live one.

`detect_ban_grid_locked` is the **only** vision/geometry component still on the
ban path. With `TRUST_ROSTER_ONLY = True` (`orchestrator.py:2046`), the
`if trust_roster: continue` at `orchestrator.py:2126` skips `ocr_ban_card_name`
entirely, and the `elif expected_positions:` branch that calls
`mask_low_contrast_regions` (2208) and `read_ban_row_cards` is unreachable. A
grid position is mapped to a card by `detect_ban_grid_locked` plus
`top_row = presses_so_far - 1`, and nothing else.

Paired measurement of one physical card — **Zachary Lee, `KNOWN_BAN_ROSTER[(2,0)]`,
visibly faded/locked in every frame** — as the ban cursor moves on and off it:

```
frame                      cell (rel 1,0) mean contrast    cursor on this cell?
20260825_170132_165.jpg              84.3                  no
20260825_170133_363.jpg              78.8                  no
20260825_170134_398.jpg              82.9                  no
20260825_165925_430.jpg              97.5                  YES
20260825_165924_368.jpg             104.8                  YES   <- > 100, reads UNLOCKED
```

`MASK_CONTRAST_THRESHOLD = 100.0`. The cursor's white selection frame plus its
glow adds **+15 to +26** to the cell mean, and in `165924_368` that crosses the
threshold. Shrinking the sample box by 12% on each side (to exclude the border)
brings 104.8 → 96.8 and 97.5 → 89.6, so roughly a third of the lift is the
border and the rest is the card-body highlight.

The value oscillates across the threshold *between adjacent frames*
(104.8 then 97.5, 1.06 s apart), so on any given capture this card is roughly a
coin flip.

Consequence, with `TRUST_ROSTER_ONLY = True`: `(2,0)` enters
`expected_positions` → `roster_hits[(2,0)] = PlayerCard("Zachary Lee", 6, 2)` →
it becomes a ban candidate the player does not own. `choose_bans` picks the
three *lowest* powers, so a power-6 card rarely wins — but the same mechanism
applies to every cell the cursor visits, and the cursor visits every cell.

Distribution across 56 sampled `20260825` ban frames (560 cells):

```
<60      12.9%   |  60-80  14.5%  |  80-95   3.2%
95-105    2.0%  <- straddling the threshold
105-120   3.2%   |  120-150 8.0%  |  >150   56.2%
within +-15 of the threshold:  25 / 560  (4.5%)
16 of 56 frames contain at least one straddling cell
```

`PENDING_LIVE_VALIDATION.md`'s claim of "51-64 [locked] or 160-180 [normal], a
huge margin either side" no longer holds. It was already untrue on `20260824`
(`200520_984` has a cell at 78.2, `200601_124` at 74.9), and the `20260825`
session produces 95.7, 97.5, 104.8, 106.3, 111.7.

**Regression test that fails today.** Add to `test_ban_grid_locked.py`:

```python
# Row 0: [Claude Ewer LOCKED], [William Lee-Gains LOCKED], Brandon "Binger" Ortiz,
#        Joshua Diaz, Justin Young
# Row 1: [Zachary Lee LOCKED — cursor is on it], Johnny "Blaze" Sweets,
#        Johnny C-Train Goudenberg, Charlie Pepper, Josef Bunz-Konicky
("20260825_165924_368.jpg",
 [[True,  True,  False, False, False],
  [True,  False, False, False, False]]),
```

The detector returns `False` at `(1,0)`. Both existing fixtures happen to have
the cursor on an *unlocked* card, which is why this has never been caught.
(Copy the frame into `test_fixtures/` — `test_ocr_ban_card.py`'s N10 note
explains why.)

### V9 — `mask_low_contrast_regions` itself: correct on ban screens, destructive on gameplay

Per-cell blacked-out fraction after masking, against ground truth read off the
rendered frames:

```
20260825_165903_259  locked (0,2) 0.962  (1,0) 1.000  (1,1) 0.936 | unlocked max 0.199
20260825_165924_368  locked (0,0) 0.907  (0,1) 0.871  (1,0) 0.609 | unlocked max 0.080
20260825_170133_363  locked (0,0) 0.996  (0,1) 0.871  (1,0) 0.776 | unlocked max 0.121
20260824_200520_984  locked (0,2) 0.962  (1,0) 0.870  (1,1) 0.936 | unlocked max 0.199
```

**It never masks a genuinely playable card** — worst unlocked cell is 19.9%
blacked, and visual inspection confirms name and badges survive intact. It
always masks a locked one, though the cursor-highlighted case degrades to
60.9%; visually the name and stats are still gone at that level, so the
function's stated purpose holds.

On a **gameplay** frame it is a different story:

```
20260824_201129_262   scoreboard 0.217  hand 0.349  third_base 0.618  first_base 0.669  second_base 0.394
20260824_203856_523   scoreboard 0.221  hand 0.349  third_base 0.790  first_base 0.669  second_base 0.432
```

Two thirds of every base crop is blacked out, including the base coins
themselves. `capture_screenshot_b64`'s docstring says masking "hasn't been
checked against every other screen type … a legitimately low-contrast but
still-relevant region elsewhere *could* get blacked out". Measured, it is not
"could" — it does, at 62-79% of the crops the runner read depends on. Latent
only because `run()` calls `read_game_state()` with the default
`mask_low_contrast=False` (`orchestrator.py:2609`); the parameter is a loaded
gun.

### V7 — `REVEAL_CENTER_REGION` includes a permanent card

`REVEAL_CENTER_REGION = (0.42, 0.28, 0.62, 0.58)` contains the
always-face-down pitcher-indicator card at the diamond centre, and its right
edge clips a second card. The source's own comment
(`orchestrator.py:897-903`) identifies that
face-down card as a known trap for the base crops — it was not applied here.

Over the 1,509 gameplay frames, 234 (15.5%) exceed `REVEAL_EDGE_THRESHOLD`
natively / 165 (10.9%) on the mss path. Labelling a random sample of 15 of
those by eye:

```
201936 (0.0659)  idle turn, hand dealt, no reveal cards   FALSE POSITIVE
202506 (0.0684)  idle turn, hand dealt, no reveal cards   FALSE POSITIVE
221612 (0.0664)  idle turn, hand dealt, no reveal cards   FALSE POSITIVE
201916 (0.0718)  mid-resolution, cards gone, fires on the flying BALL  FALSE POSITIVE
(the remaining 11 do show cards at centre)
```

and in the borderline band 0.055-0.080, four more idle-turn frames read
0.0703-0.0800. The source's "no cards: 0.0220-0.0624" range came from one
traced play; across the corpus, idle turn screens reach **0.0800**.

Ban screens are far above it — `165941` 0.1364, `170125` 0.1339, `200525`
0.1377 — so `wait_for_reveal_cards()` returns `True` on the first poll of a ban
screen too.

Consequence: `wait_for_reveal_cards` returning `True` spuriously means
`read_matchup_reveal()` spends a vision call on a frame with no reveal and
writes a matchup row into `match_log.jsonl` — the dataset LESSONS §2 is about.
The failure is silent in exactly the way §2 warns: the row is
indistinguishable from a genuine one.

---

## 6. `input_prompt_visible` — true accuracy (EXEC)

Bright-pixel fraction computed for all 1,937 frames on both capture paths.

### 6a. On gameplay turns the detector is excellent

Stratified sample of 20 gameplay frames (10 each side of the threshold),
labelled by eye from the bottom-left crop:

```
detector positive (n=10):  "PLAY" fully inside the box,  frac 0.0493 - 0.0522
detector negative (n=10):  box empty,                    frac 0.0000 - 0.0027
```

Perfectly bimodal with a ~19x margin. Threshold 0.02 sits in the gap. Native
vs mss paths disagree on 12 of 1,937 frames (0.62%).

### 6b. On ban / menu screens it is noise, and the test says otherwise

```
0824 gameplay  n=1498   fires on  114   ( 7.6%)
0824 bright    n= 313   fires on  142   (45.4%)
0825 bright    n= 115   fires on   54   (47.0%)
0825 gameplay  n=  11   fires on    0   ( 0.0%)   <- all 11 are the transition overlay
                        ------------------------
ban / menu total        196 / 428      (45.8%)
```

Rendering the box on firing ban frames shows why: it lands on **ban-grid card
art**, and fires whenever the scroll position puts a bright card body under it.
`20260824_200525_005` frac 0.0677 (light card body), `20260824_200646_254`
frac 0.0369 (bright tactics card) — both fire; `20260824_200458_664` frac
0.0003 (faded card banner) does not.

`test_gameplay_regions.py:53` asserts this with two frames:

```
20260824_200458_664.jpg  frac=0.00034  -> passes
20260824_200504_992.jpg  frac=0.00077  -> passes
```

In the same 36-frame `20:04-20:06` stretch, **28 frames (78%) fire**. Ten
randomly drawn from it:

```
200503_987  0.00282  passes      200524_000  0.05782  FIRES -> test fails
200519_979  0.00085  passes      200525_005  0.06765  FIRES -> test fails
                                 200605_144  0.03829  FIRES -> test fails
                                 200637_210  0.03487  FIRES -> test fails
                                 200639_221  0.03291  FIRES -> test fails
                                 200641_231  0.03248  FIRES -> test fails
                                 200646_254  0.03688  FIRES -> test fails
                                 200648_259  0.02953  FIRES -> test fails
```

Swapping either `_PROMPT_ABSENT` fixture for almost any other real ban frame
turns the assertion red on unmutated code. The test's message —
"2 ban screens correctly ignored" — is true of those two frames and false of
the population.

### 6c. Two structural problems with the audit itself

- `_safe_prompt_check()` is called **unconditionally on every poll for every
  screen** (`orchestrator.py:2680`, inside `record_observation`). Combined with
  6b, the `prompt=` field in `_OBSERVATIONS` — and therefore in every
  `dump_diagnostics()` bundle — is wrong ~46% of the time on the ban screen,
  which is where the run spends most of its time (LESSONS §7: 149 of 175 s).
  A stall diagnosed from that bundle would be diagnosed from a field that is
  noise.
- `_safe_prompt_check()` calls `input_prompt_visible()` with `img=None`, so it
  takes a **fresh `_fast_grab()`** rather than reusing the frame the vision
  read used. The two samples are separated by a full vision round-trip
  (~2-4 s). The audit's stated question — "does the game's own prompt agree
  with what the vision model called this screen?" — is being asked of two
  different moments.

### 6d. What `20260825` cannot tell us

The brief asked for accuracy on `20260825` gameplay frames. There are 11, all
of them the "PLAY AS THE BATTER" transition, and the detector correctly returns
`False` on all 11 (no prompt is on screen). That is 11 true negatives on a
screen type nobody disputes. **The `20260825` session contains no settled
gameplay turn**, so it cannot validate the detector at all. Everything in 6a is
from `20260824`.

---

## 7. `capture_screenshot_image` / `_fast_grab` (REASONED + EXEC)

Two capture paths with different effective resolutions feed different
consumers:

```
capture_screenshot_image()   pyautogui, 3456 physical px -> 2000   -> vision reads, ban crops, lock detection
_fast_grab()                 mss, 1728 logical px -> upscaled 2000 -> settle, reveal, prompt, dump_diagnostics
```

Measured impact on the settle metric: ≤4.3% (§2e) — immaterial. Measured
impact on the reveal gradient: ~11% (§2f) — material, and already handled.

The unguarded risk is different and is **not** display scaling, which the
fractional-coordinate scheme handles. It is that **the game is a window, not
fullscreen**. Every frame in the corpus shows the macOS menu bar, a dock strip
down the right edge, and the Chiaki-ng title bar. All fractions are of the
*screen*, so moving or resizing that window silently invalidates every crop in
this file, and nothing checks for it. The `_CALIBRATED_ASPECT` guard at import
(`orchestrator.py:1226`) checks the *display*, runs once, and would not see a
window move at all.

Measured tolerance before something breaks: ±35 px vertical for the ban card
crops (§1c), and ~70 px for the hand crop (the y0 0.770 → 0.716 change that
`GAMEPLAY_REGIONS_FRAC` documents as taking exact-hand parsing 6/13 → 9/13).
So roughly 3-5% of frame height. Within these two sessions the window did not
move (0 px shift, §1a), so this is a hazard, not an observed defect.

**Found nothing** on: `_grab_settle_regions` sampling different moments per
region (it takes one capture, correctly), the crop-margin exactness argument in
`detect_ban_grid_locked` (the `MASK_KERNEL//2 + 2` margin is correct and is
asserted by `test_ban_grid_locked.py`), and the `_fast_grab` pyautogui
fallback.

---

## 8. Mutation results — what the suite actually protects (MUT)

Each mutation applied to a sandboxed copy, then the eight offline vision tests
run. `screenshot_log/` was symlinked in, so the frame-dependent assertions were
live.

| id | mutation | result |
|---|---|---|
| M1 | `validate`: drop the `hand_index` range check | **NONE — uncovered** |
| M2 | `validate`: drop the turn-completeness block | `test_validate_game_state` |
| M3 | `validate`: drop "no player card in hand" | `test_validate_game_state` |
| M29 | `validate`: drop the tactics `type` check | **NONE — uncovered** |
| M30 | `validate`: drop the "invalid kind" else-branch | **NONE — uncovered** |
| M31 | `validate`: drop the player `power is int` check | **NONE — uncovered** |
| M32 | `validate`: drop the duplicate-`hand_index` check | **NONE — uncovered** |
| M33 | `validate`: drop the collection `row`/`col` check | `test_validate_game_state` |
| M4 | `hand` crop y0 `0.716` → `0.770` (the pre-fix clip) | **NONE — uncovered** |
| M5 | `hand` crop → the top-left corner of the screen | **NONE — uncovered** |
| M6 | `scoreboard` crop shifted 5% right | `test_ocr_scoreboard`, `test_image_pipeline` |
| M21 | `third_base` crop moved off the coin entirely | **NONE — uncovered** |
| M22 | `first_base` crop moved off the coin entirely | `test_ocr_runner` |
| M23 | `second_base` crop moved off the coin entirely | `test_ocr_runner` |
| M7 | `SETTLE_THRESHOLDS["hand"]` `8.0` → `100.0` | **NONE — uncovered** |
| M8 | `SETTLE_REGION_SETS["turn"]` gates on `scoreboard` | `test_settle_regions` |
| M9 | `REVEAL_EDGE_THRESHOLD` `0.065` → `0.030` | `test_settle_regions` |
| M10 | `REVEAL_CENTER_REGION` moved off the diamond | `test_settle_regions` |
| M11 | `INPUT_PROMPT_REGION` → the DISCARD side | `test_gameplay_regions` |
| M12 | `INPUT_PROMPT_THRESHOLD` → `0.0` (always true) | `test_gameplay_regions` |
| M24 | `ocr_runner_card` uses the strict matcher | `test_ocr_runner` |
| M26 | `MASK_CONTRAST_THRESHOLD` `100` → `40` | `test_ban_grid_locked` |
| M27 | `BAN_GRID_COL_X_FRAC` shifted 2% (40 px) right | **NONE** (absorbed — see §1c) |
| M28 | `_fast_grab`: drop the width normalisation | **NONE** (no effect — see §2e) |

### The three that matter

**8a. `validate_game_state`'s per-card checks are all dead in the test.**
M1, M29, M30, M31, M32 — five of the seven checks — can be deleted with a green
suite. Every one of `test_validate_game_state.py`'s card-shaped `bad_cases`
(lines 26-33) omits `runners`/`your_score`/`opp_score`, so once the
turn-completeness block was added at the end of the function
(`orchestrator.py:1660-1663`), *that* block became the thing rejecting them.
The test file's own comment says the ordering was chosen "so a malformed CARD
still reports as a malformed card" — which is true of the error *message* and
irrelevant to coverage. This is LESSONS §1 pattern #1, live again, in the test
that guards the validator.

Fix: give every card-shaped case the completeness fields, e.g.

```python
{"screen": "turn", "phase": "batting", "runners": [], "your_score": 0, "opp_score": 0,
 "hand": [{"kind": "player", "name": "A", "power": 5, "secondary": 1, "hand_index": 7}]},
```

so it can only be rejected by the `hand_index` check. Verified: with the
completeness fields added, M1 goes red.

**8b. The hand crop has no geometric test at all.**
M4 and M5 both pass. `test_gameplay_regions.py` only asserts the crops are
non-zero-sized and that their combined JPEG is under half the full frame — both
true of a crop pointed at the wall. The hand is the single input every turn
decision reads, and the exact regression that was found and fixed on
2026-08-24 (y0 0.770, 52 of 151 frames with a clipped power badge) can be
reintroduced with a green suite. `third_base` is the same story (M21): its only
assertion is that an empty base reads as `None`, which any misaimed crop also
satisfies — and the source comment records that this exact bug ("centered on
the always-face-down pitcher-indicator card") shipped once already.

**8c. `test_gameplay_regions.py`'s prompt assertions are conditionally vacuous.**
Lines 57 and 62 guard every check with `if os.path.exists(_p)`. Demonstrated:
with `screenshot_log/` absent and the detector mutated to
`INPUT_PROMPT_REGION = (0.40, 0.40, 0.55, 0.50)`, `INPUT_PROMPT_THRESHOLD = 0.0`
(a box in the middle of the screen with an always-true threshold), the test
exits 0 and prints:

```
OK: input-prompt detector — 3 visible detected, 2 ban screens correctly ignored
    (region=(0.4, 0.4, 0.55, 0.5), thr=0.0)
```

It prints the mutated values in the line asserting they work.
`test_ocr_ban_card.py` moved its fixtures into `test_fixtures/` for exactly
this reason (its N10 note); `test_gameplay_regions.py` did not.

---

## 9. Dead paths worth knowing about (REASONED)

With `TRUST_ROSTER_ONLY = True` (`orchestrator.py:2046`), these are unreachable
in production:

- `ocr_ban_card_name` (595) — skipped by `if trust_roster: continue` (2126)
- `mask_low_contrast_regions` (424) — only called at 2208, in the
  `elif expected_positions:` branch
- `read_ban_row_cards`, `_read_ban_rows_separately`
- `match_roster_name`'s surname fallback, for the ban path

`test_ocr_ban_card.py` — including its whole N1 call-site guard, the most
carefully-reasoned test in the suite — is therefore guarding a path that does
not execute. That is fine as insurance against `TRUST_ROSTER_ONLY` being
flipped back, but it means **the only live vision component on the ban path is
`detect_ban_grid_locked`**, which has 2 fixture frames and 20 cells of coverage
and carries V1.

Related: the early-tactics-boundary comment at 2135-2152 explains the stop
using `ocr_ban_card_name` returning `None` on tactics cards. Under
`trust_roster` that function never runs; the stop is actually driven by
`roster_hits` being empty from a position lookup. The behaviour is correct, the
explanation is stale.

`ocr_scoreboard`, `ocr_runner_card` and `read_hand_digits` are all reached only
from `log_local_read_comparison` (1044-1072), which is audit-only. V2, V6 and
V8 therefore affect diagnostic output today, not play — but each is described
in the source as a candidate for replacing a vision call, and none is safe to
promote as written.

---

## 10. Where I found nothing

Stated explicitly so a future round does not re-tread these:

- **Crop drift between sessions.** 0 px, correlation 0.998. §1a.
- **Ban-name OCR correctness on `20260825`.** 320 reads, 0 wrong names, all
  row-consistent. §1b.
- **The N6 row-1 cliff.** Gone; ±35 px of tolerance, 0 wrong names across 1,020
  shifted reads. §1c.
- **`_fast_grab`'s width normalisation.** ≤4.3% effect on the settle metric;
  the risk its comment describes is not real for mean-abs-delta. §2e.
- **`REVEAL_EDGE_THRESHOLD`'s mss-vs-native reasoning.** Reproduced (ratio
  0.89-0.91 vs the source's 0.888). The *threshold* is sound; the *region* is
  not. §2f, §5.
- **`mask_low_contrast_regions` masking a playable card.** Never. Worst
  unlocked-cell black fraction 0.199 over 40 cells; the card stays legible. §5.
- **`match_roster_name` on OCR noise.** 0 of 40 random letter strings matched.
  It is specifically *plausible* names that are dangerous. §3/V6.
- **`group_into_cards` column chaining, in practice.** Minimum observed
  inter-card gap 0.094 vs `x_tolerance` 0.06 across 55 gaps in 18 real hands.
  Demonstrable synthetically, not observed on real data. §3/V2.
- **`_grab_settle_regions` sampling skew.** One capture per poll, correct.
- **The `detect_ban_grid_locked` crop-margin exactness argument.** Correct and
  already asserted.

## 11. Things I could not settle

- **Whether the settle gate actually mis-fires at 0.15 s.** §2c bounds the p90
  hand delta at production rate to [4.7, 34.0] against a threshold of 8.0. No
  logged frame is closer together than 0.466 s, so this cannot be closed from
  the existing corpus — only by `settle_stats_summary()` on a real session, or
  by capturing a short burst at the production rate.
- **Whether the ban grid is ever read mid-scroll.** I built a scroll-phase
  estimator and it was not reliable enough to quote for frames at scroll
  positions other than the reference. The indirect evidence (§1b row
  consistency) says no read landed mid-row in this session.
- **Whether `hand_digit_reader`'s "~0.03 apart" note describes a real
  configuration.** It contradicts `x_tolerance = 0.06` directly, but no frame in
  the 18-hand sample got closer than 0.094.
