# Match log analysis — `match_log.jsonl`, 2026-08-24 session

Analysis of all **39** logged turns (the brief said ~31; the file has 39 lines).
No files were modified other than this one. Nothing was run against the PS5.

---

## TL;DR — the actionable part

1. **The log cannot currently answer the question it was built to answer.** Not
   because of sample size — because the `outcome` field is derived, not
   observed, and its derivation has a known one-directional failure. Fix the
   labelling before logging another 100 turns, or those turns are wasted too.

2. **`outcome` is inferred from score/runner deltas, and both inputs are
   unreliable in a way that biases toward `"out"` and `"home_run"`.**
   `orchestrator.py:2003-2011` classifies a turn as `home_run` if the score
   rose, `hit` if the runner *count* rose, `out` otherwise. That misclassifies
   two whole categories of play:
   - a hit that drives a runner home raises the score without being a home run
     → logged as `home_run` (**3 rows affected: 5, 18, 30**);
   - a genuine hit whose new baserunner is missed by vision → logged as `out`.
     Runner false-negatives are *independently documented as real* in
     `orchestrator.py:1263-1270` ("vision repeatedly reporting an empty
     `runners` list while local OCR confidently found a real, roster-matching
     runner (confirmed 3x in one session)").

3. **`our_tactics_bonus` reproduces a bug this project already fixed
   elsewhere.** `orchestrator.py:1889` logs
   `decision.tactics_card.bonus` for *whatever* tactics card was attached —
   including `SPEED_BOOST` and `FIELDING_BOOST`, which per `simulate.py`'s
   `power_bonus()` fix (HEURISTICS.md, "Bug found and fixed along the way") do
   **not** add power. The same conflation the simulator was corrected for is
   live in the log. **5 rows** (4, 15, 16, 17, 18) have a bonus that may not be
   power at all. The opponent's tactics *type* is unknown on **all 8** rows
   where they used one — even though vision already returns the card's `name`,
   which would identify it. The name is read and then thrown away
   (`orchestrator.py:2318-2323` keeps only `bonus`).

4. **After every quality filter, only 2 of 39 rows are genuine, unexplained
   rule contradictions — and both point the same direction.** Neither
   overturns the confirmed rule; both are exactly what a missed baserunner
   would produce.

5. **Non-analysis but worth surfacing:** `progress.json` shows
   `balance: 12`. A match costs $50 (`"Baseball Cards - Play ($50)"`). That
   save cannot start another match. `progress_taylere.json` has $246 and a
   0-3-3 record.

---

## 1. Is the outcome data consistent with the stated rule?

### 1a. A correction to the method in the brief

The brief specifies computing `our_power + our_tactics_bonus` vs
`opp_power + opp_tactics_bonus` and testing `margin > 0 = hit`. That is correct
for **batting** rows only. On **pitching** rows the batter is the *opponent*,
and the `outcome` field is scored from `opp_score` / the opponent's baserunners
(`orchestrator.py:2003`) — so `hit` there means *they* hit. The margin must be
flipped for those 14 rows or the rule is being tested backwards.

| margin definition | rows consistent with the rule |
|---|---|
| naive `our − opp`, outcome read literally | 20 / 39 |
| **batter-perspective (pitching rows flipped)** | **24 / 39** |
| batter-perspective, ignoring opponent tactics | 25 / 39 |
| batter-perspective, ignoring all tactics | 22 / 39 |

Everything below uses the batter-perspective margin. Confidence: **high** —
this follows directly from which score field the labeller reads.

### 1b. Every row that contradicts the rule (15 of 39)

| row | phase | margin | rule says | log says | why it may not be a real contradiction |
|---|---|---|---|---|---|
| 2 | batting | +2 | hit | out | opp read `6/3` — a (power,secondary) pair absent from **both** ground-truth references |
| 3 | batting | −3 | out | hit | `opp_tactics_bonus=3`, a value never seen in 299 labelled tactics cards; type unknown |
| 5 | batting | +1 | hit | home_run | runner on base → RBI hit and HR give the identical score delta |
| 8 | pitching | +1 | hit | out | `opp_tactics_bonus=1`, type unknown (may add no power) |
| 9 | pitching | +1 | hit | out | opp read `8/2`; roster says Austin "Cur" Bunz is `8/1`; `8/2` unseen in 1126 labelled cards |
| 10 | pitching | 0 | out | home_run | opp named "Pitcher" *while they are batting*; identical stats to our card (`7/0`); our "Mickey" `7/0` vs roster `Mickey Brown 5/0` |
| 11 | batting | +1 | hit | out | **no explanation found — see 1c** |
| 17 | batting | −1 | out | hit | our `+1` tactics with a runner on → may be a speed boost (no power) |
| 18 | batting | +2 | hit | home_run | 2 runners on → RBI hit gives the same score delta |
| 22 | batting | +1 | hit | out | our own card logged as "Pitcher" during a *batting* half; opp `6/2` absent from labelled hands |
| 25 | batting | +2 | hit | out | `opp_power=3` — **structurally impossible**, player power is 4-9 |
| 26 | pitching | +2 | hit | out | `opp_tactics_bonus=2`, type unknown |
| 27 | batting | 0 | out | hit | our "Jackalhead McQueen" `9/1` vs opp "Jacob \"Cheesehead\" McQueen" `9/1` — **same card read twice** |
| 29 | pitching | +3 | home_run | hit | opp `9/1` absent from labelled hands |
| 34 | batting | +2 | hit | out | **no explanation found — see 1c** |

### 1c. Reconciliation ladder

| filter applied | contradictions remaining |
|---|---|
| none — all 39 rows, stated rule | **15** |
| drop rows where `home_run` is ambiguous with an RBI hit (runners on) | 13 |
| drop rows where a tactics bonus of unknown type sits on the margin | 9 |
| drop rows with impossible or roster-contradicted card stats, and same-card double reads | 4 |
| drop rows with a role inversion or a stat pair unseen in labelled hands | **2** |

**The two survivors — rows 11 and 34:**

```
row 11  batting  "J.J. Gain" 6/0, no tactics   vs "Jake Saucepan Black" 5/3, no tactics
                 runners=1 score=2   margin +1 → rule says hit → logged "out"
row 34  batting  "Batter" 8/1, no tactics      vs "Pitcher" 6/0, no tactics
                 runners=0 score=1   margin +2 → rule says hit → logged "out"
```

Both are the *same* error in the *same* direction: a small positive margin that
produced no recorded hit. That is precisely the signature of the documented
runner false-negative — a real hit whose new baserunner vision failed to see,
recorded as `out`.

### 1d. Why this is a measurement problem, not a rule problem

A naive threshold fit looks damning at first:

| margin | out | hit | HR | n |
|---|---|---|---|---|
| −4 to −1 | 12 | 2 | 0 | 14 |
| 0 | 5 | 1 | 1 | 7 |
| +1 | 4 | 2 | 1 | 7 |
| +2 | 4 | 0 | 1 | 5 |
| +3 | 0 | 1 | 2 | 3 |
| +4 | 0 | 0 | 2 | 2 |
| +6 | 0 | 0 | 1 | 1 |

A grid search over both thresholds picks `hit if margin ≥ 3` (30/39) over the
stated `hit if margin ≥ 1` (24/39) — and the stated rule scores *below* the
trivial always-predict-`out` baseline (25/39). Taken at face value that says the
hit threshold is +3, not +1.

**It should not be taken at face value.** The apparent step at +3 is exactly
what the labeller's asymmetry manufactures:

- **High margins produce home runs, which are detected via the score** — a
  reliable scoreboard OCR read. Every one of the 6 rows at margin ≥ +3 reached
  base. Zero misses.
- **Low positive margins produce plain hits, which are detected only via
  runner count** — the read with the documented false-negative. 8 of 12 rows at
  margin +1/+2 came back `out`.

So a detector that works at high margins and fails at low ones will fabricate a
threshold at exactly the point where the outcome type switches from
score-detected to runner-detected. The fit is an artefact of the instrument.

Two further facts make the rule-is-wrong reading much harder to hold:

- **Rows 16 and 17 differ in exactly two fields: `our_card_name` and
  `outcome`.** Both are batting, ours `5/3` with a +1 tactics bonus, opponent
  `Johnny Drawers 7/1` with none, 1 runner on, score 1. Row 16 is `out`, row 17
  is `hit`. The names are `"Batter"` and `"Unknown"` — neither identifies a
  card, so nothing distinguishes these two turns in the data. (Row 4 is the same
  matchup at `score_before = 0`, also `out`.) **Rows 23 and 29** are the
  pitching analogue — ours `6/0`, opp `9/1`, 0 runners, no tactics — differing
  only in `score_before` (1 vs 0) and `opp_card_name`, and produced `home_run`
  and `hit`.

  The outcome is therefore **not a deterministic function of the logged
  fields** — including `secondary`, which is identical within each pair.
  Something unlogged or mismeasured is driving the difference.
- Cross-checking each non-`out` label against the following same-phase row's
  state (a true home run must clear the bases; a true hit must leave a runner):
  5 labels confirm, 2 are inconsistent with a real home run (**rows 5 and 30** —
  both had runners on, both show a score delta of exactly +1, the RBI-hit
  signature), and 7 fall across a half or match boundary and cannot be checked.

**Verdict.** The data is **consistent with** the confirmed rule once the
labelling defect is accounted for. It does **not** confirm it, and it does not
have the resolution to reject it. Confidence that the rule is wrong: **low**.
Confidence that the labelling is wrong: **high** — the mechanism is visible in
the source, and 3 rows are demonstrably mislabelled by it.

---

## 2. Does `secondary` show any measurable effect?

**No. The honest answer is: cannot conclude — and by a wide margin.**

Stratifying by power margin (the only way to control for the dominant effect)
and permutation-testing the difference in mean secondary between reach-base and
out turns:

| stat | stratified difference | permutation p (20,000 shuffles) |
|---|---|---|
| batter speed | +0.327 | **0.43** |
| pitcher fielding | −0.136 | **0.74** |

Neither is close to significant, and the point estimates have opposite signs
from what the fielding hypothesis predicts (higher pitcher fielding associated
with *more* opponent success, not less).

**Why even this understates how little is here.** Of 10 margin strata, only
**5** contain both a reach-base row and an out row — the rest are unanimous and
contribute nothing. And only **12 of 39 rows** survive the filters needed for
the test at all (no tactics of unknown type on either side, no ambiguous
`home_run` label, no impossible stats, no same-card double read):
rows 1, 11, 12, 21, 22, 23, 29, 31, 34, 35, 38, 39. Their margins:
`{−2:1, −1:3, 0:2, +1:3, +2:1, +3:2}` — one or two rows per cell.

**The two matched pairs settle it directly.** Rows 16 and 17 carry identical
`secondary` on both sides (ours 3, theirs 1) and produced `out` and `hit`; rows
23 and 29 likewise (ours 0, theirs 1) and produced `home_run` and `hit`.
Whatever separates those turns, `secondary` is not it — it is held constant
across them.

### How many turns would be needed

Two-proportion test, α=0.05, 80% power, comparing reach-base rate between
low- and high-secondary groups:

| effect size to detect | informative turns needed | total logged turns at this log's boundary density |
|---|---|---|
| 20 percentage points | ~196 | **~284** |
| 15 percentage points | ~350 | **~506** |
| 10 percentage points | ~784 | **~1,133** |

"Informative" means margin in [−1, +2], where a secondary tiebreak could show —
27 of 39 rows here, so the density is favourable. Even so, the removal plan's
stated target of **"~150-200 logged turns" is too small** for anything under a
~25-point effect (`orchestrator.py:127-131`).

And all of these numbers assume the outcome labels are **fixed first**. With the
current labeller, more turns buy more turns of the same bias — a systematic
under-count of hits cannot be averaged away by sample size.

Confidence: **high** that no conclusion is available. **This is not a null
result about the game; it is a null result about the instrument.**

---

## 3. Data-quality audit

### 3a. Field integrity

| check | result |
|---|---|
| rows | 39 |
| missing `opp_tactics_bonus` | 1 (row 1 — the mid-session schema change) |
| all other fields present | yes, on all 39 rows |
| `our_power` / `opp_power` outside legal 4-9 | 1 (**row 25: `opp_power=3`**) |
| `secondary` outside 0-3 | 0 |
| `tactics_bonus` = 3 (never seen in 299 labelled tactics cards; labelled data has only 1 and 2) | 2 (rows 3, 24) |

### 3b. Name quality

**Opponent card name** (39 rows):

| category | count | rows |
|---|---|---|
| looks like a real card name | 19 | — |
| bare role label ("Pitcher"/"Batter"/"PITCHER") | 15 | 2, 6, 10, 13, 14, 15, 19, 20, 21, 25, 26, 34, 35, 37, 39 |
| role label + positional description | 3 | 5 `"Batter (opponent, top-left)"`, 23 `"Batter (Opponent)"`, 29 `"Batter (9)"` |
| **team** name, not a card | 2 | 33 `"Whiptails Pitcher"`, 36 `"Whiptails"` |

**Our own card name**: 25 bare role labels, 9 real names, **5 empty or
`"unknown"`** (rows 3, 4, 5, 15, 17). An empty `our_card_name` is not cosmetic —
`orchestrator.py:2302` uses `name != matchup_info["our_card_name"]` as the only
guard against picking our own card as the opponent's.

### 3c. Role inversions — 5 rows

The opponent's card must be the *opposite* role to ours in a given half.

| row | phase | problem |
|---|---|---|
| 5 | batting | opponent shown as `"Batter (opponent, top-left)"` while they are pitching |
| 10 | pitching | opponent shown as `"Pitcher"` while they are batting |
| 19 | pitching | opponent shown as `"PITCHER"` while they are batting |
| 22 | batting | **we** played a card named `"Pitcher"` while batting |
| 39 | batting | both — opponent is `"Batter"`, ours is `"Pitcher"` |

### 3d. Same-card double reads — 5 rows

The dedup guard is name equality only, so a *name misread* defeats it entirely.
These rows have our card and the "opponent's" card at identical power and
secondary:

| row | ours | opponent | name similarity |
|---|---|---|---|
| 19 | `"Pitcher"` 9/0 | `"PITCHER"` 9/0 | **1.00** — differs only in case, so `!=` passed |
| 27 | `"Jackalhead McQueen"` 9/1 | `"Jacob "Cheesehead" McQueen"` 9/1 | **0.68** |
| 10 | `"Mickey"` 7/0 | `"Pitcher"` 7/0 | 0.46 |
| 36 | `"Pitcher"` 9/2 | `"Whiptails"` 9/2 | 0.25 |
| 37 | `"M. J. Gain"` 7/0 | `"Pitcher"` 7/0 | 0.12 |

Row 19 is the clean demonstration: the guard was defeated by capitalisation
alone. Row 27 is the costly one — it is one of the 15 rule contradictions, and
it is very likely our own card compared against itself (margin 0 by
construction).

### 3e. Stats contradicted by the 33-card roster — 4 reads

| row | side | logged | `KNOWN_BAN_ROSTER` says |
|---|---|---|---|
| 9 | opp | `Austin "Cur" Bunz` **8/2** | 8/1 |
| 10 | our | `Mickey` **7/0** | `Mickey Brown` 5/0 |
| 28 | opp | `Timmeh Rattycum` **9/1** | **4/3** |
| 37 | our | `M. J. Gain` **7/0** | `Mama Jody Gain` 5/1 |

22 roster-matched reads agree, 4 disagree (**85% agreement**). Row 28 is the
worst: 9/1 vs 4/3 shares neither stat.

### 3f. §22 silent-miss check — and a ground-truth conflict

`secondary = 0` rate, log vs the 1,126 hand-labelled player cards:

| population | zeros |
|---|---|
| hand-labelled ground truth (all player cards) | 349/1126 = **31%** |
| log, batter-side (speed) | 8/39 = 21% |
| log, pitcher-side (fielding) | 22/39 = **56%** |
| log, opponent cards only (not chosen by our engine) | 12/39 = 31% |

The pitcher-side excess looks like the §22 silent miss, but **it is largely
selection, not misreading**: our engine picks max power, and in the labelled
data `corr(power, secondary) = −0.54`. Opponent cards — which our engine does
not select — sit exactly on the ground-truth 31%. So **§22 leaves no detectable
fingerprint in this log**, which is expected: the failure is silent by
construction. Confidence: **the log neither confirms nor rules out §22 losses.**

**Separately — the project's two ground-truth sources disagree.** Four
(power, secondary) pairs the roster asserts exist appear **zero** times in 1,126
labelled cards:

| pair | roster cards claiming it | occurrences in labelled hands |
|---|---|---|
| 4/0 | William Lee-Gains, Joshua Diaz | 0 (of 370 power-4 cards) |
| 6/2 | Zachary Lee, Noah "The Rat Baron" Kelly | 0 (of 128 power-6 cards) |
| 9/1 | Jacob "Cheesehead" McQueen | 0 (of 34 power-9 cards) |
| 9/3 | Harold "Fisto" Blunt | 0 |

Notably **every one of the 128 labelled power-6 cards has `secondary = 0`**,
while the roster lists two 6/2 cards. One of the two references is wrong about
`secondary`. This matters directly: `secondary` is the stat under investigation,
and there is currently no single trusted reference to validate a read against.
The roster comment already concedes one such correction
(`(0,2)` Harold "Fisto" Blunt, "live capture showed secondary=3, table had 1").

Three log reads land in **neither** reference: row 2 `opp 6/3`, row 9
`opp 8/2`, row 25 `opp 3/0`.

### 3g. What fraction is trustworthy?

| criterion | rows passing |
|---|---|
| card **stats** plausible (no impossible pair, roster conflict, or same-card duplicate) | **30 / 39 (77%)** |
| power **margin** fully determined (no tactics bonus of unknown type on either side) | **26 / 39 (67%)** |
| card **names** usable as identifiers | **19 / 39 (49%)** |
| `outcome` label not structurally ambiguous | 36 / 39 (92%) — but see below |
| **zero flags of any kind** | **5 / 39 (13%)** — rows 7, 11, 12, 31, 38 |
| **usable for the secondary-stat question** | **12 / 39 (31%)** |

The `outcome` figure is the misleading one: 92% counts only the three rows where
the label is *provably* ambiguous (`home_run` with runners on). The
missed-runner false negative can turn any `hit` into an `out` and leaves no
per-row trace, so **no `out` label in this file can be individually trusted.**

The 5 zero-flag rows are useless as a rule test anyway — all have margin ≤ +1
(four ≤ 0), so they only exercise the easy side of the threshold. 4 of the 5
are rule-consistent; the fifth is row 11.

---

## 4. Decision-quality review

**Stated limit, as requested:** the log records only the card that was played,
never the rest of the hand. Every judgement below is about whether the *played*
card was defensible, not whether a better one was available — that is
unknowable from this file. This is the single biggest reason the log cannot
grade the engine.

**No turn shows the engine misapplying its own stated heuristics.** Specifically:

- **24 of 39 turns attached no tactics card.** Under the always-boost rule from
  HEURISTICS.md §1, that means no usable boost was in hand — not a declined
  boost. Consistent throughout; no turn shows a boost being held back.
- **Redraw decisions are entirely invisible.** `play_one_turn` returns
  `(False, None)` on the discard branch, so redraw turns write no row.
  `should_redraw()`'s `power ≤ 4` threshold — flagged in HEURISTICS.md §3 as
  having no clear winner — **cannot be evaluated from this file at all.**

**The one decision worth flagging (n=2, nowhere near conclusive):**

`best_pitching_play`'s fielding-priority branch fires only when runners are on,
and it picks `max(secondary, power)` — so one fielding pip outranks any amount
of pitch focus. Exactly 2 logged turns exercise it:

| row | our pitcher | their batter | batter margin | outcome |
|---|---|---|---|---|
| **30** | **5 / 1** | 9 / 1 | **+4** | home run against |
| 36 | 9 / 2 | 9 / 2 | 0 | out |

Row 30 is the concrete instance HEURISTICS.md §2 was waiting on: a 5-power
pitcher played against a 9-power batter, conceding a 4-point margin. Under the
confirmed rule *any* pitcher of power ≥ 6 in that hand would have prevented the
hit outright, and power ≥ 7 would have made it comfortable. **Whether such a
card was in hand is not recorded**, so this is not evidence the heuristic is
wrong — it is one datapoint of the ~150+ §2 asks for, and it happens to point
the way the simulation did. Do not act on it.

**A latent bug worth checking (not confirmed):** rows 22 and 39 log
`our_card_name = "Pitcher"` during a *batting* half. This is most likely a name
misread — but it is also structurally possible, because **nothing filters cards
by role**. `hand_to_cards` splits only on `kind` ("player" vs "tactics"), and
`READ_STATE_PROMPT` assigns `kind: "player"` to both BATTER and PITCHER cards.
`best_batting_play` then takes `max(power)` over every player card handed to it.
If a hand can ever contain a pitcher during a batting half, the engine will
happily play it. Worth one look at a live hand to rule out; cheap to guard
against either way.

---

## 5. Everything else the data supports

**The opponent draws from our own 33-card roster.** All **19** opponent cards
with a real-looking name fuzzy-match a `KNOWN_BAN_ROSTER` entry — **19/19, zero
unmatched.** Repeat appearances: Johnny Drawers ×5, Mama Jody Gain ×3,
Austin "Cur" Bunz ×3, Jacob "Cheesehead" McQueen ×2. The OCR variants are
legible as the same cards ("M. J. Gain" / "P. J. Gain" / "J.J. Gain" →
Mama / Papa / Jenny-or-Joe Jody Gain; "Bare Sharp" → Rube Sharp;
`Austin "Our" Bunz` / `Austin "Cur" Bunz` / `AUSTIN "CUB" VANZ` → one card).
Confidence: **high** that the pool is shared. Practical consequence — the
`choose_bans()` result (HEURISTICS.md §4) plausibly shapes what the *opponent*
can draw too, which the simulation does not model.

**Scoring is home-run-dominated, but the exact share is unknowable.**
8 of 39 turns carry a `home_run` label — 8 of the 14 reach-base turns. But 3 of
those 8 (rows 5, 18, 30) had runners on base, where an RBI hit produces an
identical score delta. **True home runs are somewhere between 5 and 8 of 39.**
Row 5's next-row state (score +1, not the +2 a 1-runner home run requires) makes
that one specifically look like an RBI hit.

**Outcomes by phase:**

| phase | n | out | hit | HR | reach-base |
|---|---|---|---|---|---|
| batting | 25 | 15 | 5 | 5 | 10/25 |
| pitching | 14 | 10 | 1 | 3 | 4/14 |

The apparent split (we reach base 40% of the time, they reach 29%) is well
inside noise at these counts and is confounded by the labelling bias in both
directions. **Do not read a defensive edge into it.**

**Board states are sparse.** `runners_before` was 0 on 26 of 39 turns, 1 on 12,
2 on **1**, and 3 on none. `score_before` was 0 on 22 turns, 3 at most. So the
fielding/speed hypothesis — which by every account only matters *with runners
on* — is being tested on the 13 turns where runners existed, of which one had
more than a single runner. Even the "informative turns" count in §2 is
optimistic on this axis.

**Power distribution.** We played: 5 ×9, 6 ×6, 7 ×8, 8 ×11, 9 ×5 — consistent
with a max-power selector working off five-card hands. Opponents showed:
3 ×1 (impossible), 4 ×1, 5 ×6, 6 ×6, 7 ×10, 8 ×5, 9 ×10. Their distribution
skews high, which is what a shared pool plus their own selection heuristic
would produce.

**Tactics usage.** We attached a bonus on 15 of 39 turns (12 ×+1, 3 ×+2);
opponents on 8 (3 ×+1, 3 ×+2, 2 ×+3). Labelled ground truth contains only +1
and +2 bonuses across 299 tactics cards, so **both `+3` opponent readings
(rows 3, 24) are suspect.**

**Match record context.** `progress.json`: 4W-4L-1D, balance **12**.
`progress_taylere.json`: 0W-3L-3D, balance 246. At $50/match the first save is
below the entry cost. The 39 logged turns cannot be attributed to specific
matches — no match or turn ID is recorded — and `score_before` resets show at
least four half-boundaries, but the log is not reconstructible into matches.

---

## The single most valuable thing this data revealed

**The `outcome` field is manufactured from two unreliable screen reads, and its
error is one-directional — so the log's central column is biased, not merely
noisy.** `home_run` means "the score went up" (which an RBI hit also does — 3
rows demonstrably affected) and `hit` means "the runner count went up" (which
vision is documented to miss). Every one of the 15 rule contradictions is
explainable by that plus card-read errors; only rows 11 and 34 survive all
filters, and both are the exact false-`out` the runner miss predicts.

This inverts the log's premise. It was built to test the secondary stat against
the confirmed rule; what it actually surfaced is that **its own outcome column
cannot support either test.** A naive fit even "discovers" a hit threshold of +3
that is a pure artefact of the instrument switching detection method at that
margin. Collecting the planned 150-200 turns without fixing this first would
produce a confidently wrong answer rather than a null one.

## The single most valuable thing that could be logged but isn't

**The tactics card's type (or just its name) on both sides.**

It is the cheapest possible fix and the highest-leverage one, because the
information is *already being read and then discarded*:

- **Ours** — `orchestrator.py:1889` logs `decision.tactics_card.bonus` but not
  `.kind`, even though `decision_engine.py` already has it as a typed enum.
  `SPEED_BOOST` and `FIELDING_BOOST` add no power, a distinction this project
  already fixed once in `simulate.py`'s `power_bonus()`. **Zero cost:** one
  dictionary key.
- **Theirs** — `READ_MATCHUP_PROMPT` already returns
  `{"kind": "tactics", "name", "bonus", "paired_with"}`, and
  `orchestrator.py:2323` keeps only `bonus`, dropping the `name` that
  distinguishes "Power Swing" from "Speed Boost". **Zero cost:** it is already
  in the response, and the code already locates the right entry.

Without it, **13 of 39 rows have an effective power that cannot be computed** —
exactly the confound the 2026-08-24 opponent-tactics fix was added to remove.
That fix captured the *magnitude* and dropped the *type*, which is the half that
determines whether the magnitude applies at all.

Runner-up, and it should be done in the same pass: **log the raw
`your_score` / `opp_score` / `runners` before *and* after each turn instead of
only the derived `outcome` label.** That does not fix the vision misses, but it
makes them *visible* — a home run that does not clear the bases, or a score that
jumps by more than `runners_before + 1`, becomes checkable after the fact
instead of silently wrong. Adding a match ID and turn index alongside would make
the log reconstructible into matches, which it currently is not.

---

*Analysis performed 2026-08-25 against `match_log.jsonl` (39 rows),
`orchestrator.py`, `decision_engine.py`, `HEURISTICS.md`,
`LOCAL_VISION_EXPERIMENTS.md` §22-25, `hand_labels*.json` (1,126 player cards +
299 tactics cards), and both progress files. No project file was modified.*
