# Local screen classification — feasibility study

Offline study, 2026-08-26. Deliverable: this document plus
`screen_classifier_experiment.py`, a standalone module nothing imports.
No game was run, no keystroke sent, no logged data modified.

**Question.** The per-turn loop spends one vision call on every poll purely to
answer "what screen is this?". Can that move local, with a safe abstain, at a
zero false-positive rate on held-out data?

**Answer: no, not as a single-frame classifier, and not yet with any variant
measured here.** The measured false-positive rate on held-out predicted
positives is **3 in 278 (1.08%)**, all of them the same failure — one card in
the hand still mid-flip while the deal finishes. Adding a second grab 0.5–2 s
later and requiring the hand row to be unchanged removes all of them, but that
variant has only been measured on this one log, and a separate failure (a
banner still fading over an otherwise-correct hand) survives it and has **no
threshold that separates it at all**.

What *is* ready is the coarse split: **ban screen vs overworld vs in-match**
separates by three orders of magnitude and made zero errors on 154 labelled
non-gameplay frames. That part could drive something today.

---

## 1. Data and how it was split

`screenshot_log/` holds 1937 frames at 2000×1292. Grouping by time gaps gives
four contiguous play sessions:

| session | when | frames | role |
|---|---|---|---|
| S1 | 2026-08-24 20:04–20:26 | 1075 | **FIT** — every threshold derived here |
| S2 | 2026-08-24 20:33–20:41 | 520 | held out |
| S3 | 2026-08-24 22:15–22:17 | 216 | held out |
| S4 | 2026-08-25 16:58–17:01 | 126 | held out |

Held out **by session**, never by random frame. S4 contains no settled
gameplay at all (ban screens, overworld, and the "PLAY AS THE BATTER"
transition), exactly as the brief said, so all gameplay validation rests on
S2 and S3.

### Ground truth

Every third frame of the whole log — **646 frames** — was labelled by eye from
contact sheets (full canvas above a zoom of the hand row), *before any
classifier existed*. Labels are not derived from `hand_labels*.json`; that
file's `usable` flag means "hand digits readable", which is a different
question.

| code | meaning | n | S1 (fit) | held out |
|---|---|---|---|---|
| `T` | settled turn: in-match, five fully rendered cards at rest, no banner | 268 | 176 | 92 |
| `Xh` | **hard negative** — in-match, hand absent / partial / face-down card / mid-flip. Acting reads a *wrong* hand | 201 | 121 | 80 |
| `Xs` | **soft negative** — hand complete but a phase banner is up. Hand reads correctly; the game is between input windows | 7 | 5 | 2 |
| `B` | ban screen / collection notebook | 136 | 41 | 95 |
| `M` | overworld / match-start prompt / menu | 18 | 6 | 12 |
| `R` | result modal (WINNER / DEFEAT! / DRAW!) | 16 | 10 | 6 |
| | **total** | **646** | **359** | **287** |

Negative-class sizes, stated plainly: held-out negatives total **195**
(B 95, Xh 80, M 12, R 6, **Xs 2**). The `Xs` class — the one the weakest gate
exists to catch — has **seven examples in the entire study and two held out**.
No rate quoted on it means anything.

**Label revisions, disclosed.** After the first classifier run, 19 frames
originally marked `X` had a complete-looking hand. Each was re-examined at full
resolution against a criterion written down first ("five fully rendered
cards, no face-down back, no partially flipped card, no missing slot"; a
hover-raised card counts as rendered). Five moved `X`→`T`, seven to `Xs`,
seven stayed hard negatives. One of those five (`20260824_221638_341`) was
moved *back* to `Xh` later when a full-resolution zoom showed its fourth card
squashed mid-flip — it is counted as a false positive below. This re-audit was
feature-guided in *which* frames it looked at, which is a real bias; the
independent number is §4, where predicted positives were audited one by one.

---

## 2. Why §4b's three brightness scalars could never have worked

The game's art flickers **globally, every frame**. On a screen that is visually
frozen for 13 seconds the whole-canvas mean oscillates 52 → 56 → 52 → 56,
forever:

```
frame means over a static settled turn:
  53.97 51.09 55.20 52.29 55.80 52.15 56.24 52.03 56.23 52.09 ...
mean-removed frame-to-frame difference: ~2.3 grey levels
z-normalised frame-to-frame difference: ~0.03
```

§4b's separations were "top-left brightness 5.8 ± 0.7 vs 7.8". A ±2 level
global oscillation sits *on top of* that. The rule was fitting noise, which is
exactly what 20 random splits then showed. Two further traps in the same
direction: the screenshot is the whole desktop (macOS menu bar, Dock strip,
letterboxing), so a "top-left" region is partly chrome; and OS overlays
(Control Center, notification toasts) appear over the game in several dozen
frames.

Everything below is either normalised cross-correlation (exactly invariant to
gain and offset) or computed on a z-normalised canvas, inside the game's own
rectangle (`CANVAS = (0, 72, 1949, 1231)`).

---

## 3. Features tried

All are structural anchors — UI furniture that is present or absent by
construction — not statistics of the scene.

| # | feature | what it anchors on | verdict |
|---|---|---|---|
| 1 | `ncc_sb` | NCC of the scoreboard's static word block ("JACK PEPPER / OPPONENT / ROUND / DISCARDS"), located by `cv2.matchTemplate` over ±32 px | **excellent.** in-match ≥ 0.981; ban screen ≤ 0.032; overworld ≤ 0.202 |
| 2 | `cen_frac` | bright fraction of the table centre | good for modals: result ≥ 0.224, settled turn ≤ 0.117 |
| 3 | `banner_px` | bright glyph pixels in a 30-row strip the phase banners cross | **weak — see §5** |
| 4 | `hand_cols` | columns of the fan carrying card pixels | settled ≥ 887, but hard negatives reach 924 |
| 5 | `hand_gap` | columns with a *hole* between first and last card | settled ≤ 1; catches face-down cards and missing slots, misses mid-flip |
| 6 | `hand_top` | median row of the card mass's top edge | settled 31–92 (low values = hover-raised card) |
| 7 | `hand_spread` | p90−p10 of that top edge — the fan's staircase | settled ≥ 96 |
| 8 | `hand_move` | mean \|Δ\| of the z-normalised hand row vs a second grab | **the one that fixes §4** |

Tried and discarded:

* **SSIM / NCC against a settled-hand template** — card art changes every deal,
  so there is nothing static to correlate against below the scoreboard.
* **Card left-edge peak detection** in a strip through the fan — card art
  produces as many strong vertical edges as the card borders do; peak counts
  ranged 3–13 on genuine settled turns and 5–13 on mid-deal frames.
* **Card-back brightness** (a face-down back is nearly solid white) — settled
  turns reach 0.456 on the measure, a real card-back frame 0.510. No margin.
* **Top-edge profile matching** — settled and mid-flip profiles are the same
  staircase; a squashed card only perturbs a handful of columns.
* **Separating `result_modal` from mid-animation** — abandoned. Result modals
  bottom out at `cen_frac` 0.224 and cards flying across the table top out at
  0.227. The classifier abstains on both rather than claim a screen it cannot
  tell apart; abstaining costs one API call, which is the cheap direction.

Thresholds were fitted on **S1 only**, by a rule declared before the held-out
sessions were scored: an upper bound is the S1 settled-turn maximum × 1.25, a
lower bound is the S1 minimum × 0.97 (counts) / 0.90 (spread) / 0.75 (top).
`ncc_sb` and `cen_frac` are cut inside their class gap instead — their
separation is so wide that any value in the gap is arbitrary.

---

## 4. Results

### 4.1 On the labelled set

```
=== FIT  (S1)   n=359
    true     n | turn_settled  ban_screen  menu_or_overworld  abstain
    T      176 | 176           0           0                  0
    Xh     121 | 1             0           0                  120
    Xs       5 | 1             0           0                  4
    B       41 | 0             41          0                  0
    M        6 | 0             0           6                  0
    R       10 | 0             0           0                  10
    settled-turn coverage : 176/176 = 100.0%
    FALSE POSITIVES       : 2 of 183 non-settled frames = 1.09%

=== HELD OUT (S2+S3+S4)   n=287
    true     n | turn_settled  ban_screen  menu_or_overworld  abstain
    T       92 | 92            0           0                  0
    Xh      80 | 1             0           0                  79
    Xs       2 | 0             0           0                  2
    B       95 | 0             95          0                  0
    M       12 | 0             0           12                 0
    R        6 | 0             0           0                  6
    settled-turn coverage : 92/92 = 100.0%
    FALSE POSITIVES       : 1 of 195 non-settled frames = 0.51%
```

Coverage reads 100% in both, which flatters the classifier: the ground-truth
criterion ("five fully rendered cards at rest, no banner") and what the
classifier measures are close to the same statement. **Take the coverage
figure as near-meaningless and the false-positive figure as the result.**

Ban screen and overworld are exact in both halves — 136/136 and 18/18 — and
not narrowly: `ncc_sb` is 0.03 and 0.20 against 0.981 for anything in-match.

### 4.2 On the whole log, by auditing the positives

Coverage percentages on a labelled sample are not the number that matters. The
number that matters is: of the frames the classifier *accepts*, how many are
wrong? So every predicted positive in the held-out sessions was inspected by
eye at full resolution.

| | frames | accepted as `turn_settled` | audited | confirmed false positives |
|---|---|---|---|---|
| S1 (fit) | 1075 | 541 | 35 stillness-flagged, at full zoom, + the 176 in the labelled sample | **2** (1 hard, 1 soft) |
| **S2+S3+S4 (held out)** | **862** | **278** | **all 278** | **3, all hard = 1.08% of accepted** |

Against the negative class rather than the accepted class: the held-out
sessions hold roughly 586 non-settled frames (862 total, ~32% settled by the
labelled sample), so 3/586 ≈ **0.5% of held-out negatives**.

The five confirmed false positives, all of them:

| frame | session | what it actually is |
|---|---|---|
| `20260824_201924_394` | S1 | **hole in the fan** — four cards, table visible through the gap |
| `20260824_204124_273` | S2 | middle card squashed mid-flip |
| `20260824_221638_341` | S3 | fourth card squashed mid-flip |
| `20260824_221702_982` | S3 | middle card squashed mid-flip |
| `20260824_201417_083` | S1 | OPPONENT'S TURN banner still fading; hand itself correct |

Four of the five are one failure mode: **the classifier cannot see a card that
is still flipping in.** The fan spans the right columns, sits at the right
height, and has no gap wide enough to count, because the neighbouring cards
close over the squashed one. At the resolution these features work at, a
mid-flip card and a settled card are the same object.

Note also that 0 false positives out of 278 would *still* not have been proof
of zero. The rule-of-three bound on 0/278 is 1.1%.

### 4.3 Adding a second frame

The four hard failures are invisible in space and obvious in time. Comparing
the z-normalised hand row against the previous logged frame:

```
accepted frames, hand-row mean |delta| : <= 0.443
the four hard false positives          : 1.02, 1.05, 1.08, 1.11
```

Better than a 2× margin. Re-running the whole log with that gate:

```
single frame :  819 turn_settled of 1937 frames (42.3%)
two frame    :  776 turn_settled of 1937 frames (40.1%)
dropped by the stillness gate: 41
known false positives still accepted: 1  (20260824_201417_083 — the fading banner)
```

So the two-frame version costs 2.2 points of coverage and removes every hard
false positive found. Caveats that stop this being a clean win:

* The 0.45 threshold is fitted on the same data, on n=4 positives.
* The log's spacing is 0.5–2 s. The live loop would compare grabs ~0.15 s
  apart, where a mid-flip card has moved less. Untested at that interval.
* It does nothing for the soft failure.

---

## 5. The weakest link: the banner gate has no threshold

The gate that is supposed to catch "hand is dealt but the game is showing
YOUR TURN / OPPONENT'S TURN" counts bright glyph pixels in a 30-row strip.
Measured across all 819 accepted frames and every frame the gate rejected:

```
accepted (genuine settled turns) : ... 51, 54, 55, 55, 56, 64, 67
rejected by this gate only       : 70, 72, 79, 85, 101, 304, 516, 8437, ...
```

Rendering that strip contrast-stretched settles what those numbers are:

* the accepted frames at 55 and 64 have a **blank** strip — the count comes
  from a runner's card on first or third base clipping the strip's top rows;
* the accepted frame at 67 (`201417_083`) has a **real, faintly visible
  OPPONENT'S TURN**;
* the rejected frames at 70, 72, 79 and 85 have a **blank** strip — they are
  being rejected for a reason that is not there, and three of them happen to
  be hard negatives that the hand gates should have caught and didn't;
* only from 101 upward is the text genuinely present.

There is no value that separates them. Lowering the threshold to catch 67
starts rejecting genuine turns at 64; raising it lets more banners through.
The gate currently works partly by accident. With n=7 soft negatives in the
whole study this could not have been detected from the class statistics — it
only shows up by looking at the pixels.

---

## 6. Runtime

Measured over 200 logged JPEGs on this machine:

```
decode + crop to canvas :  6.9 ms/frame
feature extraction + rule:  4.1 ms/frame   (of which ~1 ms is the template search)
total, single frame     : 11.0 ms/frame
estimated two-frame cost: ~19 ms  (second grab + two hand signatures)
full 1937-frame scan    : 19.3 s
```

Against a 2–4 s vision call that is 180–360× cheaper, so cost is not the
constraint here; correctness is. For comparison, `detect_ban_grid_locked` is
~29 ms.

## 7. Robustness to window geometry

All four sessions were captured with the game window in the identical
position, so this was tested by synthetically shifting and rescaling a frame.

The first version pinned every region to fixed canvas pixels, and **an 8 px
vertical shift or a 1% window resize dropped `ncc_sb` from 0.998 to below the
gate** — everything abstained. That fails safe, but it would have silently
stopped saving any API calls the first time the window moved, with no signal
that anything was wrong. The module now locates the scoreboard anchor with
`cv2.matchTemplate` over ±32 px and offsets every other region by the result:

```
shift (0,0) .. (±32,±32) : ncc 0.998, anchor found exactly, verdict unchanged
scale 1.01               : ncc 0.959, still classified
scale 1.02 and beyond    : abstain
shift beyond the search  : abstain (aliased partial match scores ~0.5, below the 0.80 gate)
```

This is a synthetic test. Real validation needs frames captured at a different
window position, and none exist.

---

## 8. Verdict

**Not ready to drive anything.** Specifically:

1. **False positives are 1.08% on held-out predicted positives, not zero.**
   The brief's bar was zero. It is not met.
2. **The dominant failure is undetectable at this resolution.** Four of five
   confirmed FPs are a card still flipping in. No cheap single-frame feature
   tried separates them; the margins on the ones that came closest
   (`hand_cols` 895 vs 887, card-back brightness 0.510 vs 0.456) are inside
   the noise.
3. **The banner gate works by accident** (§5). Genuine turns and genuinely
   faint banners overlap; there is no threshold.
4. **The negative class that matters most has n=7.** Any figure quoted for
   "banner over a complete hand" is not a measurement.
5. **Window geometry is validated only synthetically.**

**What is ready now, and is not a marginal call:** telling a ban screen or the
overworld apart from an in-match screen. `ncc_sb` is 0.032 / 0.202 against
0.981, three orders of separation, 154/154 correct across two sessions of
held-out data, ~11 ms. If the loop only needs "am I still on the ban screen /
have I dropped back to the overworld", that can be answered locally today with
an abstain for everything else.

### What would change the answer

1. **Adversarial negatives, not more of the same.** All the failures live in a
   1–2 s window at the end of each deal, and this log samples it at ~1 Hz.
   Capture two fresh sessions at 10 Hz through ~50 deal-completion and
   banner-fade transitions. That is a few hundred hard negatives instead of
   the current handful, and it is what any zero-FP claim has to survive.
2. **Compose with §4c rather than competing with it.** Reader
   self-validation — "the hand parses to exactly five valid cards" — attacks
   the failure mode this classifier is blind to *directly*: a squashed card
   has no readable badge pair and a hole yields four cards. The right shape is
   the classifier as the cheap outer gate (it kills ban screens, menus, result
   modals, banners and empty-hand frames for 11 ms) with the hand reader as
   the inner confirmation on whatever survives. Neither alone reaches the bar.
3. **A banner gate with real margin** — NCC against templates of the actual
   banner words, or the full 570–640 row band with the base-card columns
   masked out, instead of a raw bright-pixel count.
4. **Live audit mode.** Run it behind `compare_local_reads=True`, logging what
   it *would* have decided next to what vision actually said, for a full
   overnight session, before it is allowed to decide anything.
5. **Frames from a moved window.**

Until at least 1, 2 and 4 are done, this should stay exactly where it is: a
standalone module that nothing imports.

---

## 9. Reproducing

`screen_classifier_experiment.py` is self-contained (all 646 labels are
embedded) and read-only against `screenshot_log/`.

```
python3 screen_classifier_experiment.py eval    # §4.1 fit vs held-out tables
python3 screen_classifier_experiment.py scan    # classify all 1937 frames
python3 screen_classifier_experiment.py pairs   # §4.3 two-frame stillness gate
python3 screen_classifier_experiment.py time    # §6 runtime
python3 screen_classifier_experiment.py sheet out.png <frame.jpg> ...   # the contact sheets used for labelling
```

The template is rebuilt at run time by averaging the scoreboard crop of five
named S1 frames. A production version would ship that as a ~40 KB PNG instead
of depending on the log.
