# Settle-detector timing analysis

Measurement-only study of `wait_for_screen_to_settle()` against the captured
frame log. Nothing in the automation was modified or executed.

- **Data:** `screenshot_log/`, 1811 JPEG frames, 2000x1292, captured 2026-08-24
  20:04:58 -> 22:17:41.
- **Metric:** mean absolute per-pixel difference between consecutive frames,
  grayscale, computed exactly the way `orchestrator.py` does it — crop the RGB
  frame to the fractional region, then `.convert("L")`, then mean `|a - b|`.
  This reproduces the `ImageChops.difference` + histogram average in
  `wait_for_screen_to_settle()` to within floating-point error.
- **Resolution:** full native 2000x1292. No downscaling was used anywhere.
  Decoding proved cheap (~7 ms/frame, 18.5 s for the whole log), so the
  4x-downscale shortcut suggested in the brief was unnecessary and is not a
  caveat on any number here.

## Region definitions used (reproducible)

Fractions of width/height as `(x0, y0, x1, y1)`, matching the source:

| name | fraction | pixels @2000x1292 | source |
|---|---|---|---|
| `current_roi` | `(0.0, 0.15, 0.75, 0.65)` | 1500 x 646 | `ANIMATION_ROI_FRACTION`, orchestrator.py:942 |
| `hand` | `(0.25, 0.716, 0.76, 1.0)` | 1020 x 367 | `GAMEPLAY_REGIONS_FRAC["hand"]`, orchestrator.py:737 |
| `scoreboard` | `(0.018, 0.175, 0.205, 0.405)` | 374 x 297 | `GAMEPLAY_REGIONS_FRAC["scoreboard"]`, orchestrator.py:729 |
| `center` | `(0.42, 0.28, 0.62, 0.58)` | 400 x 388 | faceoff area (brief) |

**Geometry that turns out to matter a great deal:**

- `center` is **fully contained inside** `current_roi`.
- `scoreboard` is **fully contained inside** `current_roi`.
- `hand` is **disjoint** from `current_roi` (its y-range starts at 0.716, below
  the ROI's 0.65 bottom edge) — confirming the bug premise.

So `current_roi` is not an independent signal. It is a superset of the two
regions it already watches, and its behaviour is dominated by whichever of them
moves longest. That single fact explains most of what follows.

---

## 0. The log is not 10 Hz — read this before the rest

The brief states frames are 0.1 s apart. **They are not.** Parsed from the
filenames, the inter-frame gap distribution over all 1810 pairs is:

| gap | count | share |
|---|---|---|
| 0.40–0.80 s (mode 0.53–0.55 s) | 723 | 40% |
| 0.90–1.30 s (mode 1.005 s) | 995 | 55% |
| 1.9–2.1 s | 73 | 4% |
| > 3 s (session breaks) | 18 | 1% |

**No gap anywhere in the log is below 0.466 s.** The capture ran at roughly
1 Hz for the first ~17 minutes and roughly 1.9 Hz afterwards, in 19 bursts
separated by breaks (one break is 94 minutes). Total wall-clock span is 7963 s
for 1811 frames — a mean of 4.4 s per frame.

Consequences, which constrain everything below:

1. Timings are reported **in seconds**, not "frames x 0.1 s". The finest
   resolution available is **0.53 s**.
2. The production code polls at **0.3 s**, which is **finer than this log can
   resolve**. Anything that depends on sub-0.5 s behaviour — most importantly
   the exact behaviour of `stable_polls_required=2` (a 0.6 s window) — cannot be
   measured directly here. Where that bites, it is called out explicitly rather
   than extrapolated.
3. A diff measured across a 1.0 s gap is larger than one across 0.3 s for the
   same motion. Idle floors reported here are therefore **upper bounds** on what
   the live 0.3 s-spaced polling sees, and animation peaks are overstated
   relative to production. Both distributions are also reported split by
   cadence so the effect is visible.

### Is the noise floor a JPEG artifact?

No. Checked directly, because it would invalidate the thresholds:

- JPEG encoding is deterministic. A pixel-identical pair of frames would produce
  byte-identical files and a diff of exactly 0. **0 of 400** consecutive quiet
  pairs were byte-identical, so the source frames genuinely differ.
- Re-encoding decoded frames with their own quantization tables and re-diffing
  gives a second-generation/first-generation ratio of **1.000** (p10 1.000,
  p90 1.001, n=40). JPEG requantization is diff-preserving at this quality
  (luma DC quantizer = 6, roughly quality 88).

The floor is real frame-to-frame change in the source. Note the live pipeline
screenshots a Chiaki remote-play window, so it inherits the same H.264/HEVC
decode noise this log inherited before JPEG. I cannot *prove* the live floor
equals the logged floor without a lossless capture, but there is no evidence of
a JPEG-induced inflation to correct for.

---

## 1. Idle baseline per region

**Definition of "idle".** Runs of >= 4 consecutive pairs, within one capture
burst, where the max diff across all four regions stays below a cutoff C. The
cutoff was swept to check the result is not an artifact of the choice:

| C | n pairs | current_roi p90 / p99 | hand p90 / p99 | scoreboard p90 / p99 | center p90 / p99 |
|---|---|---|---|---|---|
| 5 | 199 | 3.92 / 4.35 | 3.86 / 4.68 | 4.37 / 4.87 | 4.40 / 4.84 |
| 6 | 400 | 4.11 / 5.23 | 4.70 / 5.77 | 5.20 / 5.75 | 4.58 / 5.68 |
| 8 | 756 | 4.97 / 5.93 | 6.22 / 7.67 | 6.58 / 7.60 | 5.17 / 7.52 |
| **10** | **838** | **5.05 / 6.13** | **6.75 / 9.10** | **6.81 / 8.03** | **5.31 / 7.72** |
| 12 | 869 | 5.08 / 6.41 | 6.98 / 10.32 | 6.83 / 8.21 | 5.36 / 8.31 |
| 15 | 954 | 5.14 / 7.06 | 7.68 / 13.78 | 6.80 / 8.19 | 5.48 / 13.09 |

The values converge between C=8 and C=12, and at C=10 every region's p99 sits
well below the cutoff, so the selection is not clipping the tail it reports.
**C = 10, run length 4** is used for all "idle" figures below: **838 pairs,
47% of all in-burst pairs.**

### Idle diff distribution

| region | cadence | n | p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| current_roi | 0.54 s | 382 | 3.28 | 3.88 | 4.37 | 4.83 | 6.03 | 7.46 |
| current_roi | 1.00 s | 434 | 3.86 | 4.86 | 5.23 | 5.50 | 6.22 | 7.32 |
| **current_roi** | **pooled** | **838** | **3.49** | **4.36** | **5.05** | **5.41** | **6.13** | **7.46** |
| hand | 0.54 s | 382 | 3.34 | 4.33 | 5.78 | 6.84 | 9.16 | 9.65 |
| hand | 1.00 s | 434 | 4.80 | 5.90 | 7.17 | 7.81 | 8.89 | 9.71 |
| **hand** | **pooled** | **838** | **4.14** | **5.26** | **6.75** | **7.63** | **9.10** | **9.71** |
| scoreboard | 0.54 s | 382 | 3.37 | 4.62 | 5.68 | 6.45 | 7.44 | 8.83 |
| scoreboard | 1.00 s | 434 | 5.05 | 6.36 | 7.09 | 7.52 | 8.32 | 9.17 |
| **scoreboard** | **pooled** | **838** | **4.23** | **5.60** | **6.81** | **7.23** | **8.03** | **9.17** |
| center | 0.54 s | 382 | 3.30 | 4.16 | 5.22 | 6.11 | 7.87 | 9.68 |
| center | 1.00 s | 434 | 3.66 | 4.35 | 5.46 | 6.38 | 7.60 | 8.39 |
| **center** | **pooled** | **838** | **3.49** | **4.27** | **5.31** | **6.24** | **7.72** | **9.68** |

### Do the regions need separate thresholds? Yes.

Share of **genuinely idle** pairs that exceed the shared `DIFF_THRESHOLD = 6.0`:

| region | idle pairs above 6.0 |
|---|---|
| current_roi | **1.4%** |
| center | 5.8% |
| hand | **17.4%** |
| scoreboard | **20.2%** |

`DIFF_THRESHOLD = 6.0` is well calibrated **for `current_roi` specifically** —
it sits just below that region's idle p99 of 6.13. It is *not* transferable.
Dropping `hand` or `scoreboard` into the same 6.0 gate would have them reading
as "still moving" on roughly one in five completely static frames, so a gate
including them at 6.0 would spend extra polls, and at 1.0 s cadence the
scoreboard's idle p90 (7.09) is above the threshold outright.

The reason is size and content, not calibration error: `hand` and `scoreboard`
are 3–9x smaller than `current_roi` in pixel count, so per-pixel noise averages
out less, and both contain high-contrast card art and glyph edges where the
video codec churns most.

**Per-region thresholds are required. A single shared constant cannot serve all
four.**

---

## 2. Settle lag — does `current_roi` settle before `hand`?

### Event detection

An event is a burst where the max diff across all four regions reaches >= 15.0
(comfortably above every region's idle max of 9.71), preceded by >= 2 quiet
pairs, detected within a single capture burst. **126 events found; 122 have all
four regions returning below their idle p90 within the window and are used
throughout.** Cadence mix: 65 at 1.0 s, 54 at 0.53–0.55 s, 6 at 2.0 s.

### Time from event onset to settle (below that region's idle p90)

| region | p10 | p25 | p50 | p75 | p90 | max |
|---|---|---|---|---|---|---|
| scoreboard | 0.00 | 0.00 | 1.00 | 2.01 | 5.02 | 13.06 |
| hand | 0.00 | 0.63 | 2.01 | 3.85 | 6.03 | 20.05 |
| current_roi | 0.55 | 1.09 | **3.98** | 11.04 | **16.97** | 31.13 |
| center | 0.05 | 1.32 | **5.02** | 11.04 | 16.07 | 26.12 |

### The headline answer is not the one the bug report predicted

Across all 122 events, `hand` settles **earlier** than `current_roi` 72% of the
time, later only 16% (same frame 11.5%). Median lag is **-2.01 s** (hand first).

That is because `current_roi` geometrically contains `center`, and `center` is
by far the slowest region to settle (p50 5.02 s, p90 16.07 s). `current_roi`
inherits that slowness. So on the majority of events — the 54% where `center`
is the dominant mover, i.e. faceoff/reveal animations — the current detector is
**over-conservative**, not blind. It waits for the long center animation, by
which time the hand has been still for seconds.

### The bug is real, but it lives in a specific class of events

Restricting to events where the hand actually animates (`hand` peak >= 20,
**n = 71**), the lag distribution is still hand-first in 85% of cases. The
dangerous class is narrower and defined by `current_roi` being *quiet* while the
hand moves:

| filter | n |
|---|---|
| hand peak >= 20 and current_roi peak < 10 | 18 |
| hand peak >= 20 and current_roi peak < 8 | 13 |
| **hand peak >= 25 and current_roi peak < 6** (below the code's own threshold) | **8** |

Those 8 events are pure blind spots — `current_roi` never once crosses
`DIFF_THRESHOLD = 6.0` for the entire animation, so the detector declares
settled on its first two polls while cards are physically sliding into the hand:

| onset frame | hand peak | current_roi peak | hand settle | current_roi settle | blind window |
|---|---|---|---|---|---|
| `20260824_201042_035.jpg` | 27.14 | 5.46 | 2.00 s | 4.02 s | — (roi later) |
| `20260824_201423_112.jpg` | 29.74 | 5.25 | 2.01 s | 4.02 s | — (roi later) |
| `20260824_201703_788.jpg` | 36.57 | 5.83 | 2.01 s | 3.01 s | — (roi later) |
| `20260824_202204_071.jpg` | 31.34 | 4.52 | 3.01 s | 1.00 s | **2.01 s** |
| `20260824_202255_273.jpg` | 33.87 | 4.79 | 2.01 s | 0.00 s | **2.01 s** |
| `20260824_203937_486.jpg` | 36.47 | 4.03 | 2.18 s | 0.50 s | **1.68 s** |
| `20260824_204019_296.jpg` | 34.94 | 4.55 | 1.60 s | 0.54 s | **1.06 s** |
| `20260824_204056_999.jpg` | 32.47 | 5.00 | 3.32 s | 1.64 s | **1.68 s** |

**Visually confirmed** on `20260824_202255_273.jpg` and the four frames after
it: the hand region goes from empty to a fan of five cards physically sliding
upward into place over ~4 s, while `current_roi` peaks at 4.79 — below its own
threshold the entire time. The blind window in this class is **1.0–2.0 s**.

### The operational number that matters

Rather than comparing settle times, simulate the actual function and ask what
the hand is doing at the instant it declares settled. Gate = `current_roi < 6.0`,
2 consecutive sub-threshold pairs, starting from event onset, over all 122
events:

- Declares settled in **122/122** events, median **2.24 s** after onset.
- Hand diff at that instant: p50 4.92, p75 10.55, p90 **31.24**, max **38.04**.
- Hand diff **>= 10** (unambiguously mid-animation, above idle max 9.71):
  **32 events, 26%**.
- Hand diff **>= 20**: 23 events (19%). Hand diff **>= 30**: 14 events (11%).

**In roughly a quarter of animation events the current detector hands the vision
pipeline a frame in which the hand is visibly mid-motion.**

Caveat on this simulation: two consecutive log pairs span 1.08 s (0.54 s
cadence) or 2.00 s (1.0 s cadence), whereas the production code's two polls span
0.6 s. The simulation therefore requires *more* stability than production does,
so **26% is a lower bound** on the real rate.

---

## 3. Stability requirement — is 2 consecutive polls enough?

### What can and cannot be measured

The code requires 2 polls at 0.3 s = a 0.6 s stability window. **The log's
finest spacing is 0.53 s, so a 0.6 s window cannot be evaluated directly.** The
measurable question is how the false-settle rate responds to *longer* stability
windows, which bounds the answer by monotonicity.

### False settle, bounded-lookahead definition

A first attempt using "does the region spike again anywhere later in the event"
returned 97–99% for every region — an artifact: the 60-frame window spans
whole turn cycles at 1.0 s cadence and was catching the *next* animation. That
number is discarded.

The sound definition: after a declaration, does the region cross back above
threshold within a bounded lookahead? A **0.6 s lookahead** (the very next frame)
isolates "this animation was still running". A 2–3 s lookahead is dominated by
the next animation starting, which no amount of waiting prevents.

Gate = `current_roi < 6.0`, judged on whether **hand** re-crosses 10.0
(above idle max), n = 122 events:

| lookahead | 0.6 s | 1.0 s | 1.5 s | 2.0 s | 3.0 s |
|---|---|---|---|---|---|
| CURRENT `current_roi<6.0` | 20% | 20% | 36% | 39% | 55% |
| `hand<7.0` | **2%** | **2%** | 25% | 33% | 52% |
| `current_roi<5.0 AND hand<7.0` | 7% | 7% | 16% | 16% | 38% |

The convergence at 3 s (55% vs 52%) confirms the far tail is the game's own
rhythm, not premature detection. The 0.6 s column is the bug signal.

### Effect of `stable_polls_required` (K)

Judged on a fixed yardstick — hand diff >= 10.0 within 0.6 s of declaration —
so every configuration is scored identically. 95% CI in brackets, n = 122:

| gate | K | continuation | latency p50 | p90 |
|---|---|---|---|---|
| **CURRENT `current_roi<6.0`** | **2** | **12.3% [6.5, 18.1]** | 2.24 s | 14.07 s |
| `hand<6.0` | 2 | 1.6% [0.0, 3.9] | 2.89 s | 9.93 s |
| `hand<7.0` | 2 | 1.6% [0.0, 3.9] | 2.40 s | 7.03 s |
| **`hand<8.0`** | **2** | **1.6% [0.0, 3.9]** | **2.01 s** | **6.01 s** |
| `hand<9.0` | 2 | 1.6% [0.0, 3.9] | 2.01 s | 5.03 s |
| `hand<8.0` | **3** | 1.6% [0.0, 3.9] | 3.11 s | 8.04 s |
| `current_roi<6.0 AND hand<8.0` | 2 | 3.3% [0.1, 6.4] | 4.06 s | 17.97 s |
| `current_roi<5.0 AND hand<7.0` | 2 | 2.5% [0.0, 5.2] | 7.92 s | 20.70 s |

Sweeping K on the current gate alone (2/3/4) moves the un-normalised rate from
41% to 37% to 22% but costs a median latency of 2.24 -> 6.15 -> 9.36 s.

**Answer to "is 2 enough": yes, and the question is misdirected.** Going from
K=2 to K=3 on the recommended gate changes the continuation rate not at all
(1.6% in both) while adding ~1.1 s to median latency and ~2 s to p90. Raising K
on the *current* gate does help somewhat, but only because it accidentally
stalls long enough for the hand to finish — an expensive way to buy what
watching the hand gives for free. **The failure is which region is watched, not
how long it is watched.**

I cannot resolve K=2-at-0.3 s directly. But since the false-settle rate falls
monotonically with the stability window and is already flat between 1.08 s and
2.16 s, there is no evidence in this data that a longer window is worth its
latency.

---

## 4. Recommended parameters

### Per-region thresholds

Set each region's threshold between its idle p95 and p99, so a genuinely static
screen almost never reads as moving while real motion (peaks of 27–105) remains
far above:

| region | idle p95 | idle p99 | idle max | **recommended** | idle pairs blocked |
|---|---|---|---|---|---|
| `current_roi` | 5.41 | 6.13 | 7.46 | **6.0** (unchanged) | 1.4% |
| `hand` | 7.63 | 9.10 | 9.71 | **8.0** | 3.2% |
| `scoreboard` | 7.23 | 8.03 | 9.17 | **8.0** | ~3% |
| `center` | 6.24 | 7.72 | 9.68 | **6.5** | 4.2% |

The existing `DIFF_THRESHOLD = 6.0` is kept for `current_roi` because the data
says it is correctly calibrated for that region — it is only wrong as a
*shared* constant.

Hand-threshold sweep showing the choice is not sensitive in the 6–9 band
(continuation flat at 1.6% throughout); 8.0 is picked for the latency and
idle-cost balance:

| hand thr | idle pairs blocked | continuation | latency p50 | p90 |
|---|---|---|---|---|
| 6.0 | 17.4% | 1.6% | 2.89 s | 9.93 s |
| 7.0 | 8.2% | 1.6% | 2.40 s | 7.03 s |
| **8.0** | **3.2%** | **1.6%** | **2.01 s** | **6.01 s** |
| 9.0 | 1.3% | 1.6% | 2.01 s | 5.03 s |

### Consecutive stable polls

**Keep `stable_polls_required = 2`.** K=3 buys zero measured safety on the
recommended gate and costs ~1.1 s median. Do not raise it.

### Which regions gate which read

| read type | gate on | threshold | K | suggested `max_wait` |
|---|---|---|---|---|
| **turn** (reading the hand) | `hand` **alone** | 8.0 | 2 | **8 s** |
| **reveal** (reading the faceoff) | `center` | 6.5 | 2 | **16 s** |

**Turn read — gate on `hand` alone, and specifically do *not* also require
`current_roi`.** This is the least intuitive recommendation and it is the one
the data supports most strongly:

- Continuation drops from **12.3%** to **1.6%**, a ~7.7x reduction. The CIs do
  not overlap (6.5–18.1 vs 0.0–3.9), so this is not noise at n=122.
- Median latency *improves* slightly (2.24 -> 2.01 s) and p90 more than halves
  (14.07 -> 6.01 s), because the gate is no longer waiting on the long center
  animation that a turn read does not care about.
- Adding `current_roi` back in (`current_roi<6.0 AND hand<8.0`) makes it
  measurably **worse**: 3.3% continuation, p90 latency 17.97 s. Waiting longer
  pushes the declaration into the window where the *next* animation begins. The
  combined gate is both slower and less safe than the hand alone.

**Reveal read — gate on `center`.** Continuation on the center region falls from
23.8% (current gate) to 11.5% (`center<6.5`). Adding scoreboard to the reveal
gate changes it only from 11.5% to 10.7% — not worth the extra latency, so
`center` alone is enough.

**Do not use `scoreboard` as a gate for anything.** Its peak diff during actual
animation events is p50 6.59 / p90 10.96, against its own idle p90 of 6.81 — the
signal barely rises above its own noise, so it cannot discriminate motion from
rest.

### `max_wait`

Present calls use 3.0–4.0 s (orchestrator.py:1533, 1557, 1576, 1835, 1887,
1903, 1919, 1997, 2021) and the 8.0 s default at line 2117. Measured latency for
the recommended turn gate (`hand<8.0`, K=2):

| percentile | p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| latency | 2.01 s | 3.97 s | 6.01 s | 7.84 s | 9.83 s | 10.04 s |

| `max_wait` | events truncated (loop gives up, caller reads un-settled) |
|---|---|
| 3 s | 38% |
| 4 s | 25% |
| 6 s | 12% |
| **8 s** | **5%** |
| 10 s | 2% |

**The `max_wait=3.0`/`4.0` call sites are truncating 25–38% of events.** When
the cap is hit the function returns without having settled and the caller reads
anyway — an independent source of bad reads that no threshold change fixes.
8 s brings truncation to 5%. For the reveal gate, `center<6.5` needs 16 s to get
truncation down to 11% (p90 is 16.97 s); center animations are genuinely long
and the current 3–4 s caps cannot cover them.

---

## Things that surprised me, and things the data does NOT support

**Surprises:**

1. **The log is not 10 Hz.** It is ~1 Hz and ~1.9 Hz in bursts. This was the
   single biggest constraint on the analysis and it invalidates any
   "frames x 0.1 s" arithmetic.
2. **The stated bug direction is wrong in the majority of events.** `hand`
   settles *before* `current_roi` 72% of the time, because `current_roi`
   geometrically contains the slow `center` region. The current detector's more
   common failure is over-waiting (and then hitting `max_wait`), not
   under-waiting. The under-waiting failure is real but confined to hand-only
   animations — 8 unambiguous blind-spot events out of 122.
3. **`DIFF_THRESHOLD = 6.0` is well chosen for `current_roi`** — it sits right
   at that region's idle p99. It is only wrong as a shared constant.
4. **Adding `current_roi` to the turn gate makes things worse, not better.**
   The obvious "watch both regions" fix is measurably inferior to watching the
   hand alone, on both safety and latency.
5. **Increasing `stable_polls_required` is nearly useless.** Almost all of the
   improvement available comes from region choice.

**Not supported by this data:**

- **Any claim about behaviour at 0.3 s poll spacing.** The log cannot resolve
  below 0.53 s. Statements about K=2-at-0.6 s are bounded by monotonicity
  arguments, not measured.
- **Precise blind-window durations.** Quantised to 0.53 s / 1.0 s. "1.0–2.0 s"
  is real; "1.68 s" specifically is one sample at one cadence.
- **That live-pipeline noise floors equal these.** The live code diffs lossless
  in-memory screenshots of a Chiaki window; this log adds a JPEG generation.
  That generation was shown to be diff-preserving (ratio 1.000), and the
  dominant noise source — remote-play video decode — is common to both, but the
  equality is not proven. Thresholds should be re-checked against a short
  lossless capture before being treated as final.
- **Any per-screen breakdown** (turn vs ban screen vs result). Screen identity
  was never read; events are classified only by which region moved. Frames near
  match/menu transitions were not separated out, though the >= 15 onset
  threshold and the idle-run selection keep them out of the baseline figures.
- **The 6 events at 2.0 s cadence** are included in pooled figures but are too
  few and too coarse to say anything about on their own.
- **Sample sizes are what they are:** 838 idle pairs, 122 complete events, 71
  hand-animating events, 8 pure blind-spot events. The 8 are individually
  listed above precisely because 8 is too few to summarise statistically.
