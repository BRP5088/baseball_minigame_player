# Local vision/OCR experiments — full results log

Everything tried to replace or supplement the Claude vision API with
local processing, and what actually happened. Written 2026-08-24 for
outside review.

**Context**: this automates a turn-based baseball card minigame in
*Mouse: P.I. for Hire*, played over PS5 remote play (Chiaki-ng) on
macOS. Screenshots are captured with pyautogui at 2000x1292 (downscaled
from the native capture). The game renders in a 1930s rubber-hose
cartoon style — heavy grain, aged-paper textures, hand-inked lettering.
Currently a Claude vision API call reads game state each turn
(~1.5-3s latency); the goal is to move as much as possible to local
code for speed and cost.

---

## The card data model (matters for why some approaches work)

Every player card has:
- **name** — printed on a ribbon banner at the card's bottom, normal
  printed font (e.g. "RUBE SHARP")
- **power** — a digit in a round badge, top-right. Bold, stylized,
  hand-inked-looking font. Dark digit on light circle.
- **secondary** — a digit in a shield badge just below the power badge.
  Same font, inverted (light digit on dark shield). Only present on
  some cards.

The full card roster is **fixed game-wide** (33 catalogued so far) —
only *which* cards a given save has unlocked differs. This is the single
most important fact for what follows: **if you can read the name, you
get power and secondary for free from a lookup table**, no digit
recognition needed.

Where cards appear:
1. **Ban screen** — a scrollable 5-column grid, large upright cards,
   static. Best-conditioned target.
2. **Base positions** — one card resting at each of first/second/third
   on the diamond, upright, medium size.
3. **Hand** — 5 cards fanned across the bottom of the screen,
   overlapping, individually rotated (~±8°), smallest of the three, and
   **the name banner is cut off by the screen edge** — hand cards show
   only role ("BATTER"/"PITCHER") and the two badges.

---

## What worked

### 1. Scoreboard digits — tesseract, works perfectly

Plain printed scoreboard text (`JACK PEPPER 2 0 2 / OPPONENT 0 1 1`).

- `pytesseract`, `--psm 6`, no preprocessing beyond the crop.
- Only quirk: reads `0` as letter `O` about half the time — handled by
  treating `O`/`o`/`Q` as `0` when parsing.
- **Result: 6/6 numbers correct across 3 real screenshots.** Verified
  again live during a real match (agreed with vision every turn).

### 2. Base-runner names — tesseract + fuzzy roster match, works

Read the name banner off each base crop, fuzzy-match against the known
roster, return the roster's trusted power/secondary.

Preprocessing that made the difference:
```
crop name-banner strip -> grayscale -> 4x upscale
-> ImageOps.invert -> threshold(>190)
-> pytesseract --psm 6
```
Then: extract letters-only words per line, keep the longest line
(the ribbon's notched tail-ends produce junk lines above/below), fuzzy
match via `difflib.get_close_matches` (cutoff 0.5, plus a last-word
fallback at 0.6).

The fuzzy match is doing real work — raw OCR output like
`'\\ RUBE SHARP /'`, `'| . NUGC SHARP ?'`, `'JOHNNY ORAWERS'` all
resolve correctly.

- **Result: 3/3 occupied bases correct, plus empty base correctly
  returns None.**
- Also caught a real data error: live capture showed Harold "Fisto"
  Blunt with secondary=3, the roster table said 1. Table was wrong.

### 3. Ban-screen cards — tesseract + fuzzy roster match, works

Same recipe as base runners, applied to the ban grid. Card positions
come from code (`detect_ban_grid_locked()` uses local contrast to
determine which grid cells are locked/faded vs. legible), so vision is
never asked about *position* — only content.

- **Result: 18/18 known cards correct across 3 independently-scrolled
  frames.** Locked in as a regression test.
- One real bug found and fixed here: a tightly-tuned name-strip window
  (0.82–0.96 of card height) worked on one frame and completely missed
  on another. Cause: the ban screen scroll is animated, and
  "settled" captures land at slightly different sub-pixel offsets.
  Widening to (0.70, 1.0) fixed all cases — the "longest line" selection
  already discards the extra junk a wider crop picks up.

### 4. Payload cropping (not OCR, but relevant)

Instead of sending one full-frame image to the vision API, send a
low-res overview (900px, for screen-type classification) plus sharp
crops of just the regions that need precise reading (scoreboard, hand,
three bases).

- **Result: ~55-60% reduction in image tokens per call** (~3444 →
  ~1400). Verified live over a full session with no accuracy loss.

---

## What did not work

### 5. Badge digits (power/secondary) — tesseract, total failure

This is the crux. Tested on ban-screen cards (the *best* conditions:
large, upright, static, well-framed, crop visually confirmed correct):

- Tried both polarities (dark-on-light and inverted).
- 7 threshold values × 5 `--psm` modes, exhaustively.
- **Zero correct reads of the power digit.** Not wrong answers —
  no detection at all, or garbage.

Secondary/shield digits fared slightly better but still misread (a
clearly-legible "3" read as "1").

Conclusion: it's the glyph style, not resolution or framing. Tesseract's
trained models don't handle this bold hand-inked font.

### 6. Badge digits — EasyOCR, better model, still unreliable

EasyOCR (deep-learning detector+recognizer) instead of tesseract.

**When it works, it's excellent**: correctly read the exact power digit
tesseract never got (`'8'` at **0.9997 confidence**), and the shield "3"
tesseract misread (0.80 confidence).

**But it's brittle in a way that matters.** On an image where the digit
is large and unmistakable to the eye:

| upscale factor | result |
|---|---|
| 1x | nothing detected |
| 2x | nothing detected |
| **3x** | **'5' at 1.00 confidence** |
| 4x | nothing detected |
| 6x | nothing detected |

A one-step change in upscale factor flips it between perfect and blind.
That's the detector stage failing to localize text, not the recognizer
misreading it.

Batch results across 12 known ban-screen cards, position-based digit
assignment: **power 6/12, secondary 1/9.** Every failure was a
zero-confidence non-detection or a low-confidence wrong answer, never a
confident wrong answer.

### 7. Hand cards specifically — hardest target, multiple approaches

Hand cards have no name banner (cut off by screen edge), so the
"read the name, look up the stats" trick that solves the other two
surfaces **does not apply**. Badge digits are the only option.

Attempts:

**a) Rigid 1/5-width slot slicing** — the fanned cards overlap, so
fixed slices catch neighboring cards' digits. One slot returned two
different cards' digits; another returned nothing.

**b) Overlapping windows centered on each card** — 2/5 correct.
Neighbor bleed persisted (slot1 picked up slot2's digit).

**c) Per-card de-rotation** (user's suggestion — the fan tilts each
card ~±8°, so rotate each back to upright before OCR). **This helped
measurably: 2/5 → 3/5**, and specifically fixed a neighbor-bleed case.
Good idea, real improvement, but didn't solve the two right-side cards.

**d) Angle sweep on the failures** — 9 angles (−16° to +2°) × 3 scales
on a crop where the "7" is large and plainly legible: **zero
detections**. Rules out rotation as the remaining blocker.

**e) Multi-scale sweep** to exploit the narrow sweet spot from #6 —
recovered one slot, still 2/5 overall.

### 8. Digit template matching — promising, ultimately not trustworthy

Since the digits are a closed set (0-9) in a fixed font, template match
instead of OCR.

Pipeline: Hough circle detection to locate the badge → crop its
interior → binarize → tighten to the glyph's ink bounding box →
normalize to 32×48 → compare against learned templates by mean
absolute difference.

Hough circle detection was the reliable part: **4/4 badges located**,
much better than contour-hunting (which grabbed the circle outline or
fragments instead of the digit).

Built a template set from 18 ban-screen cards with roster-known values,
**16/18 glyphs extracted**, then leave-one-out cross-validation:

- **12/16 correct (75%)** raw.
- Errors scored notably lower (0.63–0.92) than correct matches
  (0.95–0.98).
- **At a 0.93 confidence threshold: 11 accepted, all correct, 0 wrong,
  5 abstained** → looked like exactly the right shape (never lie,
  abstain and fall back to vision when unsure).

**Then it broke.** Harvesting additional templates from *shield* badges
(to cover digits 1/2/3, which power badges didn't supply) produced
degenerate near-blank extractions that matched **wrong digits at score
1.000** — a "4" matching a "3" perfectly, a "1" matching a "4"
perfectly.

That invalidates the threshold result: the "zero wrong answers at 0.93"
finding held only on a hand-curated clean subset. Once realistic messy
extractions enter the pool, high confidence stops implying correctness.
A confidently-wrong stat is the one failure mode that's unacceptable
here, since these values drive card selection.

Final shipped template set covers only digits **4, 5, 6, 8** (11 clean
templates). 1, 2, 3, 7, 9 have no usable templates.

### 9. Cross-context card-art matching (perceptual hashing) — failed

Separate attempt: identify hand cards by their *character art* rather
than reading digits, using perceptual hashing against reference images.

Reference images came from the ban screen; queries from the hand.
Result — same card across the two contexts scored **worse** than two
different cards within the same context:

| comparison | pHash distance |
|---|---|
| Same card, ban-screen vs in-game render | 28 |
| **Different** cards, both ban-screen | 22 |

Also tried ORB feature matching and `cv2.matchTemplate` on the same
data. On well-framed cards all three agreed cleanly; on the problem
case (rightmost fanned hand card) all three failed together — ORB found
2 good matches for a same-card pair vs. 40 for a known different-card
pair.

Root cause turned out to be upstream: the two captures genuinely didn't
frame the same content (position *and* scale differ frame-to-frame for
edge cards in the fan layout). No matching algorithm recovers from that.

### 10. CLIP embeddings — better signal, same blocker

`open_clip` ViT-B-32, cosine similarity between image embeddings.

Same-context hand-card pairs:

| slot | truth | similarity |
|---|---|---|
| 1 | same card | 0.985 |
| 2 | same card | 0.977 |
| 0 | different | 0.760 |
| 3 | different | **0.924** |
| 4 | **same card** | **0.926** |

Clean separation for well-framed cards, but slots 3 and 4 land within
0.002 of each other with opposite ground truth — no threshold separates
them. Cross-context (ban-screen vs in-game) also failed: same card
0.739 vs. different cards 0.815.

Latency: **55ms per embedding** on CPU (M-series Mac) — genuinely fast
enough, ~20-50x better than a network round-trip.

A self-populating cache was built around this (learn from vision on a
miss, match locally thereafter) and did work end-to-end live — first
real matches came back at 0.96-0.99 similarity. But it also revealed a
cache-poisoning problem: vision returns generic placeholders
("Batter", "Pitcher") when it can't identify a hand card, and learning
those made multiple distinct cards match one generic entry. Fixed by
requiring ≥2 words and canonicalizing through the roster fuzzy-matcher
before learning.

---

### 11. PaddleOCR — best result by far, and the recommended path

Gemini's suggestion, and it was right. PaddlePaddle has no wheels for
the main env's Python 3.14, so it runs in a Python 3.11 venv called via
subprocess (also keeps a heavy ML dep out of the orchestrator process).

Key insight that made it work: **feed it the whole hand strip, not
isolated badge crops.** PaddleOCR localizes the digits itself — no
per-card de-rotation, no badge isolation, no Hough circles. Every
earlier approach was hampered by my pre-cropping.

Results on real captures, read at 1x and 2x and merged:

| hand | truth | detected | result |
|---|---|---|---|
| handB | 8/1, 4/3, 4/3, 5/2 | 8/8 digits | **perfect 4/4 cards**, all 0.99-1.00 |
| live_hand | 5/0, 4/1, 6/0, 7/0, 9/2 | 5 of 7 digits | 3/5 cards; missed card0's power and card4's shield |

Compare with the same `live_hand` under earlier approaches: tesseract
0/5, EasyOCR 2-3/5. PaddleOCR also read digits (7 and 9) that **no**
other method ever detected once.

**Detection is now solved.** An earlier draft of this doc claimed two
digits on `live_hand` were undetectable due to occlusion — that was
wrong (and the cards in question simply have no shield; secondary=0 is
normal). Adding scale=4 to the sweep finds **all 7 digits on
`live_hand` and all 8 on `handB`**, every one at 0.97-1.00 confidence.
Different digits surface at different scales, so the sweep (1x, 2x, 4x)
matters:

| scale | digits found on `live_hand` |
|---|---|
| 1x | 4, 6, 7, 9 |
| 2x | 4, 6, **5**, 7, 9 |
| 4x | 4, **1**, 6, **2** |

**What remains is grouping, not recognition.** PaddleOCR reports where
a badge visually appears after fan overlap, which is not the same as
card order. On `live_hand` the leftmost card's power badge ("5") is
reported at x=0.467 — to the right of cards 1 and 2's badges. So naive
left-to-right x-clustering mis-assigns it as card 2's shield.

Measured pair geometry (a card's shield relative to its own power badge):

| hand | pair | Δx | Δy |
|---|---|---|---|
| handB | 8→1 | +0.027 | +0.245 |
| handB | 4→3 | +0.014 | +0.235 |
| handB | 4→3 | −0.002 | +0.225 |
| handB | 5→2 | −0.009 | +0.241 |
| live_hand | 4→1 | +0.054 | +0.249 |
| live_hand | 9→2 | −0.002 | +0.266 |
| live_hand | **6→5 (false pair)** | +0.017 | **+0.182** |

True pairs cluster tightly at Δy ≈ 0.225-0.266; the one false pair sits
at 0.182. A Δy band would separate them — but that is two hands' worth
of data, and tuning a threshold on it risks overfitting. Needs more
real hands before trusting it.

### 12. Roster-tuple validation as a grouping check — measured, weak

Suggested as a way to reject bad pairings: if a tentative
(power, secondary) pair isn't a stat line any real card has, reject it.

Measured against the 33-card roster:

- 33 cards → **18 distinct (power, secondary) combos**; only **9 cards**
  have a fully unique stat line.
- Observed powers 4-9, secondaries 0-3 → 24 possible combos, 18 valid.
- **The filter rejects only 6/24 (25%) of arbitrary pairings.**
  Invalid combos: (6,1), (6,3), (7,2), (7,3), (8,2), (8,3).

It *did* catch the real false pair from `live_hand`: (6,5) is not a
valid card — but only because 5 isn't a legal secondary value at all,
not because the roster is discriminating. Within the plausible space
~75% of mis-groupings would produce a valid-looking stat line and pass
silently.

**Verdict: worth keeping as a free veto on impossible combos, far too
weak to rely on as the primary grouping mechanism.**

### 13. Bulk hand-sample harvesting (data collection)

To resolve the grouping question with real data instead of two samples,
`harvest_hands.py` pulls distinct hand strips out of `screenshot_log/`.
At 10Hz the same hand appears dozens of times, so it dedupes by
comparing 64x24 grayscale thumbnails (mean per-pixel difference < 6.0 =
same hand), plus a cheap std-dev/brightness check to skip non-turn
screens (ban screen, result overlays, world map).

**Result: 260 distinct hand samples** from ~1800 logged frames across
tonight's matches — two orders of magnitude more grouping data than the
two hands the Δy geometry was originally measured on.

Caveat found immediately: the harvest filter is too loose. Of 40 samples
run through PaddleOCR, **15 detected zero digits** — a mix of ban-screen
frames and mid-deal animation frames that the std-dev/brightness check
let through. 14 of 40 had 8+ digits (clean full hands). The filter needs
tightening, but this doesn't affect the geometry analysis, which only
uses the clean hands.

### 14. Δy band — measured across 14 clean hands, and it holds

The open question was whether the Δy ≈ 0.23 pair spacing seen on two
hands was real structure or an artifact. Measured across every
below-pair within |Δx| < 0.05 on the 14 clean hands (56 pairs):

| Δy (bin 0.01) | count |
|---|---|
| 0.20 | 1 |
| 0.21 | 6 |
| 0.22 | 17 |
| 0.23 | 18 |
| 0.24 | 12 |
| 0.25 | 2 |

**Range 0.204–0.253, median 0.227, and exactly 4.0 pairs per hand.**

That tightness is itself the evidence: if these 56 included spurious
cross-card pairings, they would scatter. They don't. And the known false
pair from `live_hand` sits at **Δy = 0.182 — below the entire observed
range**, so a band cleanly excludes it.

Rule: pair a power badge with a shield when `|Δx| ≤ 0.06` and
`0.19 ≤ Δy ≤ 0.28`. Tested against both hands verified by eye:

- `live_hand` → {(4,1),(6,0),(5,0),(7,0),(9,2)} — **correct set**
- `handB` → [(8,1),(4,3),(4,3),(5,2)] — **exactly correct**

**CORRECTION — there is no card-ordering problem.** An earlier version
of this section claimed `live_hand`'s leftmost card had its power badge
detected at x=0.467, "proving" that fan overlap breaks left-to-right
x-sorting, and proposed fan-arc angle-sorting to fix it. **That was
wrong**, and it was caught by cross-checking against the labelling
agents' finding about decoy digits in the card art (§15f, §16c).

Looking at the actual pixels:
- The `5` detected at **x=0.467** is a **height-chart tick mark** on
  card 2's mugshot background — a false positive, not a badge at all.
- Card 0's real power badge (`5`) sits at **x≈0.176**, exactly where the
  leftmost card should be. PaddleOCR simply **never detected it**, at
  any scale in the sweep.

So badge-x ordering was never broken. The symptom was one missed
detection plus one false positive, both of which merely *looked* like a
geometry failure. **The fan-arc/pivot idea is unnecessary** — there is
no tangled coordinate system to untangle.

**CORRECTION — the sample is far smaller than "14 hands" suggests.**
A ground-truth labelling pass flagged that consecutive 10Hz screenshots
are near-duplicates, and checking the digit signatures confirms it: the
14 "clean hands" contain only 10 distinct signatures, and clustering
those by leading digits gives **roughly 3 genuinely distinct hands**:

| signature prefix | files | timestamp span |
|---|---|---|
| `043...` | 3 | 200800-200817 |
| `143...` | 1 | 200759 |
| `434...` | 10 | 200830-200918 |

So "56 pairs" is ~3 independent hands replicated across frames, not 56
independent observations. The dedupe threshold in `harvest_hands.py`
(mean pixel diff < 6.0 on a 64x24 thumbnail) is far too permissive —
it treats a hover-raised card or a single grain-flicker as a new hand.

The Δy band may well still be right — within a hand the pairs are
genuinely consistent, and the known false pair at 0.182 does sit outside
the observed range — but **cross-hand generalisation is barely tested**,
which is close to the original two-hand overfitting risk this analysis
was supposed to remove. Needs a stricter dedupe and a re-run before the
band is trusted.

Also note a subtle trap found here: adjacent fanned cards can put one
card's shield within ~0.03 (fraction of strip width) of the next card's
power badge. A multi-scale merge step with a generous dedupe radius
silently swallows real distinct digits. Radius had to come down to
0.015 in x / 0.05 in y.

## Current state

| Target | Method | Status |
|---|---|---|
| Screen-type classification | Claude vision (low-res overview) | Kept — genuinely open-ended, local pixel checks can't identify "unexpected screen" |
| Scoreboard | tesseract | **Local, verified** |
| Base-runner identity | tesseract + roster fuzzy match | **Local, verified** |
| Ban-screen cards | tesseract + roster fuzzy match | **Local, verified 18/18** |
| Hand-card digit *detection* | PaddleOCR global sweep + targeted shield pass (`hand_digit_reader.py`) | **98% of cards, 12/13 hands exact** (§24). Residual errors are silent, so still needs a cross-read to be trusted |
| Hand-card power↔shield *pairing* | Δy band (§14) | **Provisional** — correct on both hands verified by eye, but rests on only ~3 independent hands, and shield-badge tactics cards (§16a) are unhandled |
| Hand-card left-to-right *ordering* | badge x-sort | **Not actually broken** (§14 correction) — the apparent failure was a missed detection plus a decoy false positive |

### 15. Ground-truth labelling pass — findings that change the design

Independent labelling of 60 samples (indices 60-119; 45 usable, 225
cards, 20 marked not-confident) surfaced several things the OCR work had
assumed wrongly:

**a) SPEED BOOST tactics cards use a DARK SHIELD badge, not a white
circle.** Verified at 6x zoom. Its bonus digit sits in a black shield
with a white outline, in the same position where PITCH FOCUS and POWER
SWING put a white circle. Any logic keying "tactics ⇒ circle" or
"shield ⇒ secondary stat" misparses every SPEED BOOST — and it was the
most common tactics card in that slice (26 of 48).

**b) Badge icons are a free card-type signal.** PITCHER power circles
carry a small baseball; BATTER power circles carry a bat; shield badges
carry a glove/mitt; POWER SWING's circle carries a bat; SPEED BOOST's
shield carries a glove.

**c) The dominant failure mode is VERTICAL clipping, not horizontal.**
All 20 not-confident cards had the same cause: the card is
**hover-raised** (~40px lift on the selected card), pushing its badge
above the top of the hand crop. Horizontal cut-off at the left/right
edges — which earlier analysis assumed was the problem — was never the
limiting factor. **Fix: extend `GAMEPLAY_REGIONS_FRAC["hand"]` upward by
~40-50px**, or detect the raised card and re-crop. This likely explains
a chunk of the zero-detection samples in §13.

**d) ~25% of frames are mid-animation** in identifiable flavours: hand
slid off the bottom bar, a card back in flight, a played card floating
mid-screen, or an entirely different screen. A "count 5 settled cards"
gate would reject all of them.

**e) Missing shields confirmed normal at scale**: 45 of 177 player cards
(25%) had no shield → secondary 0. Distribution: 0×45, 1×56, 2×32, 3×44.
This independently confirms the correction in §11.

**f) Small tick digits on the card art are a false-positive trap.**
Player card mugshots have faint height-chart numbers ("5 / 4 / 3") along
the side margins. They're decoration, well away from badge positions,
but a naive digit detector will pick them up.

### 16. Second labelling pass — corroboration and new traps

Independent labelling of indices 120-181 (62 files; 45 usable, 225
cards, 13 not-confident) confirmed §15's findings and added:

**a) BOTH `SPEED BOOST` and `FIELDING PLAY` use dark shield badges**;
`POWER SWING` and `PITCH FOCUS` use white circles. §15a only caught
SPEED BOOST. So badge *shape* does not separate power from secondary —
the "shield ⇒ secondary" rule misclassifies two of the four tactics
cards, not one.

**b) Every badge carries a decorative icon overlapping its upper-left** —
mini baseball (PITCHER), mini bat (BATTER), mini rat/glove (shields).
Consistently present; can be mistaken for a second badge or a digit.

**c) The card art contains decoy WHITE CIRCLES, not just decoy digits.**
The `PITCHER 7` / `BATTER 7` artwork has a juggled baseball floating
just left of the real badge, at nearly the same size and tone. Combined
with §15f's height-chart tick digits, the art is actively adversarial to
a naive digit detector — and this is what produced the false "ordering
problem" corrected in §14.

**d) Hover-raise clipping independently confirmed** as the top source of
uncertainty (9 of 13 not-confident marks). Notably: **the shield stays
visible while the power circle disappears above the crop.** So a
pipeline that assumes "power is always present" will break on exactly
these frames.

**e) Rightmost card's shield sits near the bottom letterbox band**
(y > ~250 in the 1020×298 crop) and clips easily. Combined with (d),
the crop needs headroom at BOTH top and bottom.

**f) Hands are type-homogeneous** — all five cards were either
PITCHER-family or BATTER-family in every frame, never mixed (tactics
appear in both). Useful as a sanity check on a parse.

**g) Concrete non-hand reject signals**: fewer than 5
BATTER/PITCHER/tactics banners; a face-down card back (distinctive two
long "rabbit ears"); a `PLAY` button glyph; a serif-caps name banner at
the bottom (reveal/ban screens).

### 17. Third labelling pass + the ground-truth dataset

A third independent pass (indices 180-259; 80 files, 44 usable, 220
cards) added one important new false-positive source and confirmed the
rest:

**a) Painted scoreboard digits inside the card frame.** The
J.J. GAIN / JENNY JODY GAIN card art has "5", "5", "4", "2" painted into
its background wall, running down the **right edge inside the card
border — exactly where a shield badge would sit.** Verified at ~x=545,
y=118/155 in original coordinates.

This independently explains the false positive that produced the phantom
"ordering problem" in §14: the decoy `5` at x=0.467 in `live_hand` is on
the J.J. GAIN card (PaddleOCR read the name `J.J.GAIN` in that same
frame). Two labelling agents and a direct pixel inspection now agree.

**b) Hover ENLARGES the card, not just raises it** — it grows in place,
reveals a bottom nameplate, and pushes the power circle off the top of
the strip while the shield often stays visible. All 13 not-confident
cards in this slice were this case.

**c) Loose baseballs in the art** produce isolated baseball glyphs with
no circle beside them, defeating a "find the baseball, then look right
for the circle" heuristic.

**d) Secondary distribution across 181 player cards**: 0×56 (31%), 3×56,
1×48, 2×21. Power range observed 4-9 only.

### 18. Ground truth established — and the first honest accuracy numbers

Four independent labelling passes produced **249 usable hands / 1,245
labelled cards**. One pass overshot its slice, which accidentally
created overlap with the other three — free inter-rater agreement data:

| overlap | files | usable-flag agreement | card-value agreement |
|---|---|---|---|
| pass1 ∩ pass2 | 60 | 60/60 (100%) | **225/225 (100%)** |
| pass1 ∩ pass3 | 62 | 58/62 (94%) | **205/205 (100%)** |
| pass1 ∩ pass4 | 25 | 24/25 (96%) | **55/55 (100%)** |

**485 of 485 overlapping cards agree**, between readers that never saw
each other's work. The few usable-flag disagreements are edge-case
judgement calls on marginal frames. The ground truth is trustworthy.

**Measuring PaddleOCR against it** (13 labelled-usable hands that also
have OCR output):

- Digit **recall by count**: 111 of 120 expected digits (92%).
- Hands where the detected digit multiset is **exactly** right:
  **6 of 13 (46%)**.
- False positives: **4**. False negatives: **13**.

So the honest picture is: **misses dominate errors 3:1**, and fewer than
half of hands parse perfectly. This is far below the "detection solved"
claim made earlier from two hands, and it is the number that should
drive any decision about wiring this in.

Important caveat that likely inflates the miss count: several of these
hands contain hover-enlarged cards whose power badge is genuinely
**outside the crop** (§16d, §17b). Those are crop-geometry failures, not
OCR failures, and extending the crop upward should recover them. The
92%/46% figures are therefore a floor, not a ceiling.

### 19. Complete labelling pass — the full dataset and the decisive finding

A fourth pass labelled the **entire 260-file directory**: 151 usable,
109 unusable, **755 cards**, 53 marked not-confident (7%). Combined with
the three slice passes, the corpus is 1,245 labelled cards with the
100%-agreement validation in §18.

**a) The crop is too short — this is the headline.** 78 of 151 usable
frames contain a hover-raised card, and in **52 of those the raised
card's badge is clipped by or entirely above the top edge**. Every one
of the 53 not-confident cards is this case. Recommended fix: **60-80px
more headroom** above the current top. This is now confirmed by all four
independent passes and is the single highest-value change available.

**b) Card ordering was never ambiguous — third independent
confirmation.** Left/right edge clipping was noted in only 3 of 260
frames, and no rightmost card was ever cut badly enough to block a read.
Each card's circle sits near its own top-right with its shield directly
below-right, and the neighbour's card edge always started clear of it.
This closes out the phantom problem corrected in §14.

**c) Complete tactics badge table** (shape is fixed per card *name*):

| card | badge | digit | icon |
|---|---|---|---|
| `POWER SWING` | white circle | dark | bat |
| `PITCH FOCUS` | white circle | dark | ball |
| `SPEED BOOST` | **dark shield** | white | bat |
| `FIELDING PLAY` | **dark shield** | white | ball |

Note the labeller misread SPEED BOOST as a circle at 1x and had to zoom
to catch it — "a pipeline reading at native resolution will make the
same mistake."

**d) Cheap menu-screen discriminator**: mean brightness of the top-left
60×40 px is >140 on deck/collection menu screens vs ~55 on gameplay
hands. The first 19 files in the directory are menu screens, not hands.

**e) Full stat distributions** (600 player cards): secondary 0→174
(29%), 1→146, 2→78, 3→202. Power 4→205, 5→211, 6→64, 7→54, 8→50, 9→16 —
**no power below 4 observed at all**, a usable sanity bound.

**f) Mid-deal rejection rule**: presence of a face-down card back (black
card, crossed bats, ball), or a horizontally squashed mid-flip card, or
fewer than 5 card bodies of near-equal width. Would catch nearly all 66
deal/play-animation frames.

### 20. Value bounds — a second, independent correctness check (APPLIED)

Two fully independent sources agree exactly on the legal value ranges:

| source | surface | reader | cards | power | secondary |
|---|---|---|---|---|---|
| `KNOWN_BAN_ROSTER` | ban screen | tesseract + roster match | 33 | **4-9** | **0-3** |
| hand labels | hand strip | 4 independent vision readers | 1,126 | **4-9** | **0-3** |

**1,159 observations, none outside those ranges.** Different screen,
different pipeline, different readers — so this isn't one method's blind
spot echoing itself.

Wired into `hand_digit_reader.validate_card()`; every grouped card now
carries a `valid` flag.

Why this matters beyond a sanity check: **it catches the known false
pair from `live_hand` (power 6 + "secondary" 5) without using the Δy
geometry at all.** A secondary outside 0-3 is a strong tell that a digit
was mis-paired or picked up from card artwork. Two independent
mechanisms now reject the same error, which is exactly the redundancy
this pipeline needs given how adversarial the art turned out to be
(§15f, §16c, §17a).

Note this is strictly stronger than the roster-tuple validation measured
in §12, which only rejected 25% of arbitrary pairings. Range-checking is
cruder but catches a different, more common failure: digits that aren't
badges at all.

### 21. Crop headroom fix — measured, applied (BIGGEST SINGLE WIN)

All four labelling passes independently identified the same dominant
failure: the **cursor-selected** card is enlarged in place, pushing its power
badge above the top of the hand crop while the shield stays visible.
78 of 151 usable frames had a raised card; 52 had a clipped badge.

(The labelling passes called this "hover", a mouse-centric assumption.
The game is controller-driven: a card is raised because it is
*selected*. Importantly **up to TWO cards can be raised at once** — a
play is a player card plus an optional tactics/stat-modifier card, and
`input_controller.select_and_play(card_index, tactics_index)` presses
select on both before confirming. So a frame captured mid-selection can
have two clipped badges, not one.

Practically useful: the pipeline already knows both indices, because it
is what moved the cursor and pressed select. A parser can therefore
*predict* which cards will be raised rather than discover it — and
should never assume at most one.)

Independently corroborated by the labelling notes, which describe
exactly this without having been told to look for it:
- `201538_417`: *"cards 3 and 4 raised; **power swing** badge and card 4
  power circle clipped/above the crop"* — a tactics card and a player
  card raised together.
- `202313_340`: *"cards 2 and 3 raised; both their top badges are above
  the crop"*.

4 labelled frames have two clipped cards simultaneously.

Tested directly — same 13 labelled-usable hands, same OCR pipeline, only
the crop changed (+70px headroom):

| crop | hands exactly right | false positives | false negatives |
|---|---|---|---|
| original (`y0=0.770`) | 6/13 (46%) | 4 | 13 |
| **+70px (`y0=0.716`)** | **9/13 (69%)** | **1** | **3** |

**False negatives fell 77%, false positives 75%.** Payload cost: the
region grew from 39% to 42% of a full frame — negligible.

**Applied** to `GAMEPLAY_REGIONS_FRAC["hand"]` in `orchestrator.py`.
Note this also improves what the *vision* API sees on every turn, not
just local OCR, since both read the same crop.

Visual confirmation on a frame flagged by the labellers: the
cursor-selected BARTHOLOMEW CREASLEY card's badge is cut off under the old
crop and fully visible (`PITCHER 5`, shield `1`) under the new one. That
is the same card one labelling pass had to infer from adjacent frames
and honestly flagged as "derived rather than observed" — the inference
was correct, and is now directly observable.

**Remaining after the fix**: 4 of 13 hands still imperfect, 1 false
positive, 3 misses. Those are the genuinely adversarial cases —
painted-in scoreboard digits and decoy baseballs in the artwork
(§15f, §16c, §17a) — which the §20 value-bounds check is designed to
catch rather than the crop.

### 22. Silent-failure analysis — why 69% is the wrong question

Accuracy alone doesn't decide whether this can be wired in. What matters
is whether a *wrong* parse can be **detected**, because an undetected
wrong stat feeds a real play decision. Measured on the 13 labelled hands
using the improved crop.

First, a scoring correction: §21's "9/13" compared digit *multisets*,
which flags a hand as failed even when every card parsed correctly but a
stray digit was detected and then discarded during grouping. Comparing
the parsed **cards** to truth instead:

- **10 of 13 hands exactly right (77%)**
- **60 of 65 cards correct (92%)**

Then the gates. Applying every check available — exactly 5 cards, power
in 4-9 (player) or 1-3 (tactics), secondary in 0-3:

| outcome | count |
|---|---|
| accepted & correct | 9 |
| **accepted but WRONG (silent failure)** | **4** |
| rejected → safe vision fallback | **0** |

**The gates caught nothing.** Every wrong parse passed as legal.

The reason is structural, and it kills the idea of gating our way to
safety: **3 of the 5 card errors are a missed shield, which reads as
`secondary = 0`.** That is indistinguishable from a card that genuinely
has no shield — and 29% of player cards genuinely have none (§19e).
`(4, 0)` is a perfectly legal card either way.

So the error distribution is **systematically biased toward
under-reporting secondary**, silently. That is exactly the stat
`best_pitching_play()` uses for its fielding-priority choice, so the
failure lands directly on a decision path.

**This also corrects a premise**: the remaining failures are *not*
adversarial-artwork false positives. The diffs are dominated by
**missing** digits, not extra ones. Icon-presence verification (checking
for the bat/ball/glove on a badge) would filter decoys — a precision
fix — but the live problem is **recall**: a badge that was never
detected at all. Icon checks cannot recover what was not seen.

**Bonus finding — a free card-type discriminator.** Tactics bonus values
and player power values are **disjoint**: tactics 1-3 (1-2 observed
across 299 tactics cards, 3 seen in match logs), player power 4-9. So
the top badge digit alone identifies the card type; no icon detection
needed for that either.

### 23. Targeted shield-recall pass — INCONCLUSIVE (test was flawed)

Idea: since the failure mode is *recall* (a shield never localized by the
global detector), don't rely on the detector — crop a patch at the
**expected** shield position relative to each detected power badge and
OCR only that patch, at high zoom (4x/6x/8x).

Measured offset in tall-crop fractions: Δy ≈ 0.175, Δx ≈ 0.

**Result: 10/54 shields correct (19%), 39 read as absent.** Far worse
than the global pass (92% of cards correct). But the test has two known
defects, so this is *not* a fair verdict on the approach:

**Defect 1 — the offset is not constant.** It varies systematically with
position across the fan, which is the card rotation showing up in the
geometry:

| power badge x | mean Δx to its shield | mean Δy |
|---|---|---|
| 0.00-0.25 | **+0.0078** | 0.169 |
| 0.25-0.45 | +0.0012 | 0.170 |
| 0.45-0.65 | −0.0017 | 0.176 |
| 0.65-0.85 | +0.0000 | 0.191 |
| 0.85-1.00 | **−0.0074** | 0.179 |

A single fixed vector is wrong by construction. A rotation-aware offset
(interpolating Δx and Δy by x position) is the correct version and was
not tested.

**Defect 2 — the evaluation itself was buggy.** It matched a prediction
to truth *by power value*, so in a hand containing two power-4 cards
(one with shield 3, one with none) it could score against the wrong
card. Several test hands have exactly that shape.

Visual debugging confirmed the patches land correctly on the middle
cards and drift off on the outer ones — consistent with defect 1.

**Status: worth retrying with a position-dependent offset and a fixed
evaluation.** Not evidence the idea is wrong.

Caveat that holds regardless: even at perfect shield recall this does
not make failures *visible*. A patch that finds nothing still yields
`secondary = 0`, indistinguishable from a genuinely shield-less card
(§22). Improving recall shrinks the error rate; it does not make the
remaining errors detectable. Only a cross-check against an independent
reader does that.

### 24. Shield recall SOLVED — patch size was the variable (APPLIED)

§23's targeted pass scored 19% and I blamed the offset geometry. Wrong
diagnosis. Re-testing with a corrected evaluation (matching predictions
to truth by **left-to-right position**, and only scoring hands whose
power sequence already agrees — eliminating §23's match-by-power-value
bug) and a sweep of patch sizes:

| patch half-size | shields correct | missed | wrong |
|---|---|---|---|
| ±0.050 / ±0.075 (tight) | 10/50 (20%) | 38 | 2 |
| **±0.090 / ±0.130 (medium)** | **38/50 (76%)** | **10** | 2 |
| ±0.140 / ±0.200 (wide) | 27/50 (54%) | 15 | **8** |

**Non-monotonic, with a clear optimum.** Too tight starves the detector
of context and it fails to localize at all (recall collapses); too wide
pulls in neighbouring cards' badges (wrong answers jump 2 → 8).

This is the *same* lesson as §11 — PaddleOCR does better with context
than with isolated crops — which §23 had accidentally contradicted by
cropping too tightly. Consistent story, not a contradiction.

**Combined with the global pass:**

| | cards correct | hands exact |
|---|---|---|
| global only | 62/65 (95%) | 10/13 |
| **global + targeted** | **64/65 (98%)** | **12/13** |

**Applied** to `hand_digit_reader.py` as a second pass: for any power
badge (4-9) with nothing detected below it, look directly at the
expected shield position (Δy 0.175) with a medium patch at 4x/6x.
Verified on a hand that previously misread `(4,0)` for `(4,3)` — now
exact.

**What this does and does not fix.** It attacks *recall*, which was the
real problem (§22). It does **not** make failures visible: a targeted
patch that finds nothing still yields `secondary = 0`, still
indistinguishable from a genuinely shield-less card. The residual error
rate is now ~2% of cards rather than ~8%, but those errors remain
silent. A cross-check against an independent reader is still the only
thing that surfaces them — and that is free, since the vision call
already happens each turn for screen classification and already receives
this same hand crop.

### 25. Vision cross-check wired in (APPLIED) — making failures visible

The residual ~2% error is *silent* (§22, §24): a missed shield reads as
`secondary = 0`, indistinguishable from the 29% of cards that genuinely
have none. No local gate can catch it. The only mechanism that can is an
independent second reader.

**Wired into `log_local_read_comparison()`** in `orchestrator.py`,
enabled with `run(..., compare_local_reads=True)`. Each turn it runs the
local PaddleOCR pipeline on the hand crop and prints it beside what
vision reported, tagging each slot AGREE / DISAGREE / INVALID.

**Zero additional API cost.** Vision already receives this exact crop
every turn for screen classification (§4), so the comparison is free —
it reads an existing response rather than making a new request.

Verified with a deliberately-injected vision error:

```
hand[0]: local power=4 sec=3  vs vision: power=4 sec=3  AGREE
hand[1]: local power=4 sec=3  vs vision: power=4 sec=0  <<< DISAGREE
hand[3]: local power=4 sec=2  vs vision: power=4 sec=2  AGREE
hand[4]: local power=5 sec=3  vs vision: power=5 sec=3  AGREE
```

It flags the divergence without presuming which reader is right — here
the *local* one was correct, which is exactly why the audit logs
disagreement rather than auto-trusting either side.

**A real bug this surfaced**: `validate_card()` only knew player ranges
(power 4-9), so every tactics card was flagged `[INVALID]` — noise on
essentially every turn. Fixed to accept both card types, using the
disjoint-range property from §22 (tactics bonus 1-3, player power 4-9,
tactics never carry a shield) as the discriminator.

**Why this over icon-presence verification.** Icon checks (looking for
the bat/ball/glove overlapping each real badge) target *precision*. But
precision is no longer the bottleneck: 2 wrong out of 50 shields at the
tuned patch size, and the single remaining card error out of 65 is a
**miss**, not a decoy. Icon detection would address a largely-solved
problem while adding a new small-object detection task with its own
failure modes. Deferred.

**Next step**: a live session with the audit on. That yields discrepancy
rates over hundreds of hands instead of the 13 measured offline, and
identifies whether the residual errors cluster on particular cards or
board states.

## The open question

Hand cards are the remaining gap, and they're the highest-value target
(read every turn, whereas the ban screen is once per match).

**The problem is narrower than previously stated, and different in
kind.** Two conclusions from earlier in this document have been
withdrawn (see the corrections in §14):

1. Detection is **not** fully solved. It was called solved on the
   strength of two hands. Cross-checking against labelled data showed
   PaddleOCR both **missing a large, plainly-visible power badge**
   (card 0 of `live_hand`, at x≈0.176, never found at any scale) and
   **firing confidently on decoy art** (a height-chart tick digit at
   x=0.467).
2. Card ordering was **never broken**. The "fan overlap scrambles
   badge-x" conclusion was an artifact of exactly those two errors
   pretending to be a geometry problem. No pivot, no angle sort, no
   perspective correction is needed.

So the single open problem is **detection precision and recall on
adversarial art**, not geometry:

- **Recall**: a clearly legible badge can be missed entirely. Unknown
  how often — needs measuring against the labelled set.
- **Precision**: the art contains both decoy digits (height-chart ticks,
  §15f) and decoy white circles (a juggled baseball beside the real
  badge, §16c) at comparable size and tone.

Promising constraints to exploit, all from the labelling passes:
- Badges carry consistent icons (baseball/bat/glove) that decoys lack
  (§16b) — a real classification signal.
- Hands are type-homogeneous (§16f) and always 5 cards — strong
  structural priors for rejecting a bad parse.
- Missing power is a *real state* during hover-raise (§16d), so
  "power always present" is a wrong assumption to build on.
- Crop needs headroom at both top (hover-raise) and bottom (rightmost
  shield near the letterbox) — §16d/e. This is likely the cheapest
  single fix and may recover the missed badge above.

Also still open, lower priority:
- **Harvest filter is too loose** (§13) — 15 of 40 samples had zero
  detectable digits (ban-screen and mid-deal frames). Doesn't affect
  the geometry work, but wastes analysis time.
- **The local reader still is not driving decisions.** `hand_digit_reader.py`
  now runs live in audit mode (§25) — logged beside vision, never acted
  on. The live loop still reads hand cards via vision. Worth
  noting the economics: the hand read is part of the same per-turn
  `read_game_state()` call that also classifies the screen, and screen
  classification genuinely needs vision. So localizing hand cards saves
  **zero API calls** unless screen classification also goes local — the
  gain would be latency, not cost. That materially weakens the case for
  wiring this in before it's fully trustworthy.

## Ban-screen badges: the "unreadable" verdict is stale, but it barely matters

Tested 2026-08-25, prompted by "why can't you just do OCR locally on the ban
screen?"

`ocr_ban_card_name()`'s docstring says the power/secondary badges are
"genuinely unreadable ... a font-recognition limitation, not a framing
problem." That was measured on **2026-08-24 with tesseract**, exhaustively (7
thresholds x 5 psm modes, zero correct reads). PaddleOCR was added *after* that,
for the hand, and reads the same badge style at 98%. Nobody retried the ban
screen with it.

**PaddleOCR does read them.** On a real ban frame, the correct digit was
detected at ~1.0 confidence for every one of the 7 unlocked cards:

```
r0c0  truth (7,1)  detected '7'@1.00, '1'@1.00   exact
r0c1  truth (5,1)  detected '5'@1.00, '1'@1.00   exact
r0c4  truth (5,3)  detected '5'@1.00, '3'@1.00   exact
```

So the font is not the blocker. The blockers are the same ones the hand reader
took a full session to solve:

1. **Decoy digits in the card art.** Several cards carry a printed number scale
   (Jenny Jody Gain shows 5/4/3/2 down the side). A whole-card crop reads those
   instead of the badge — the same class of error as the J.J. Gain scoreboard
   decoy found during hand-reader work.
2. **Assignment, not detection.** With extra detections at similar `y`, naive
   "topmost = power, next = secondary" mis-assigns: `(5,3)` read as `(5,5)`,
   `(5,2)` read as `(2,5)`. `hand_digit_reader` solves this with
   `group_into_cards()` + `validate_card()` + targeted shield recovery at
   measured offsets; a ban reader needs its own equivalent.
3. **Rotation-ambiguous digits.** One card's `6` read as `9`.

Best naive attempt: **3/7**. Not usable.

### The important part: this is a low-value unlock

Measured on the same session's 23 ban frames, **`KNOWN_BAN_ROSTER` covers 100%
of visible unlocked positions by (row, col) lookup alone** — no OCR of any kind
needed. Badge reading is only required for a card that is *not yet in the
roster*, i.e. genuine discovery, which happens at most a handful of times ever
and is already handled by the vision fallback plus two-agreeing-read learning.

The 149-of-175-seconds problem was never badge recognition. It was the scan
grinding past the roster into the tactics section, spending two vision calls per
wasted batch. That is fixed by the local tactics-boundary stop.

**Verdict: worth knowing the door is open, not worth walking through yet.**
Revisit only if the roster stops covering the collection (a save with cards past
the catalogued rows). Do not repeat the tesseract-era claim that the badges are
unreadable — they are not.
