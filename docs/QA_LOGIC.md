# QA — game logic (decision_engine.py, simulate.py, the decision path in orchestrator.py)

Adversarial review of **what the bot decides**, not the plumbing. Scope was
`decision_engine.py`, `simulate.py`, `play_one_turn()`, `hand_to_cards()`, and
everything feeding `best_batting_play` / `best_pitching_play` / `choose_bans` /
`should_redraw` / `power_bonus`. `run()`'s guards, `read_full_ban_collection`,
and `input_controller.py` were deliberately not touched (reviewed concurrently
by another pass).

No game was run, no keystroke was sent, no real project data was written. All
mutation work happened on a sandbox copy under `$SCRATCH/qalogic/`. This file is
the only thing this pass added to the tree. Verified at the end by `shasum`
against a baseline taken at the start: `decision_engine.py`, `simulate.py`, and
`input_controller.py` unchanged; `match_log.jsonl` and all three
`progress*.json` unchanged; `screenshot_log/` unchanged; no `diagnostics/`
created. `orchestrator.py` **did** change during the review — the concurrent
pass landed its `match_in_progress` persistence work in `load_progress` /
`save_progress` / `run()`. That is outside this scope and none of it touches the
decision path; the `orchestrator.py` line numbers below have been re-derived
against the tree as it stands after that change.

Every finding is tagged **MUT** (mutation-proved), **EXEC** (executed a probe),
or **REASONED**. Per LESSONS.md §1, nothing here is claimed as "tested" without
having broken the code and watched something fail.

---

## Summary

The plumbing is careful and heavily defended. **The game logic is not, and it has
never been tested at all.** The single biggest problem is `best_pitching_play`:
on the turns where it matters most it plays a deliberately bad card *and* throws
away a good tactics card, and under the project's only confirmed rule it more
than triples the runs it concedes.

| # | Severity | Finding | Tag |
|---|---|---|---|
| L1 | **Critical** | `best_pitching_play` fielding priority is lexicographic — one fielding pip outranks any amount of pitch focus | EXEC |
| L2 | **Critical** | `best_pitching_play` discards a pitch boost for a fielding boost; batting does the exact opposite | EXEC |
| L3 | **High** | Every decision function has **zero** test coverage — all five can be inverted and the suite stays green | **MUT** |
| L4 | **High** | `choose_bans` tie-break is arbitrary grid order, and HEURISTICS §4's evidence for banning is contradicted by the match log | EXEC |
| L5 | Medium | `batters_used` never resets between matches (new, on top of the documented redraw undercount) | EXEC |
| L6 | Medium | Six input shapes `validate_game_state` accepts crash `play_one_turn` | EXEC |
| L7 | Medium | Speed/fielding boosts are held back for no reason the project's own doctrine supports (14.7% / 9.8% of hands) | EXEC |
| L8 | Low | `discards_left` misread → redraws silently disabled for a whole match | EXEC |
| L9 | Low | No role filter: a PITCHER card in a batting hand gets played | EXEC |
| L10 | Low | `target_score` is set unconditionally on the pitching half — a landmine for HEURISTICS §5 Variant A | REASONED |
| L11 | Low | `power_bonus` falls through to `0` for an unrecognised `TacticsType` | EXEC |
| L12 | Low | `choose_bans` silently returns fewer than `count` | EXEC |
| L13 | Info | The discard branch discards whatever the *play* heuristic picked | EXEC |

**Where I found nothing** is in its own section at the bottom, and it is not
short — the card-index identity mapping, `power_bonus`'s type handling,
`should_redraw`'s blindness to tactics, and the `redraws_left` arithmetic all
came back clean, three of them after I had a concrete theory that they were
broken.

---

## L1 — CRITICAL. Fielding priority is lexicographic: one pip beats any amount of power

`decision_engine.py:132-137`

```python
if runners_on and any(c.secondary > 0 for c in hand_players):
    best_pitcher = max(hand_players, key=lambda c: (c.secondary, c.power))
```

`secondary` is the **primary** sort key and `power` is only the tiebreak. There
is no threshold, no cap, no notion of "how much power is this worth". Any card
with `secondary >= 1` outranks every card with `secondary == 0` no matter how
large the power gap. The guard `any(c.secondary > 0 ...)` fires on 67% of the
real 33-card roster.

**Concrete scenario (EXEC, `p2_engine.py` case C):**

> Pitching, one runner on second. Hand: `Ace 9/0`, `Scrub 4/1`.
> → plays **Scrub, power 4**, surrendering 5 pitch focus to gain one fielding pip.

**Worst case found by random search over 200,000 realistic hands (EXEC,
`p3_fielding_cost.py`):**

> Hand: `Jacob "Cheesehead" McQueen 9/1`, `Brian Coker 8/1`, `Timmeh Rattycum 4/3`
> → plays **Timmeh Rattycum, power 4**.

**How often, and how much:**

| with a runner on base, 200k hands from the real pool | |
|---|---|
| hands where the fielding pick gives up power | **50.8%** |
| mean power surrendered, across all hands | 1.47 |
| mean power surrendered when it fires | **2.89** |
| distribution of power given up | −1: 18.4%, −2: 22.0%, −3: 23.6%, −4: 23.7%, −5: 12.3% |

**The cost under the only rule this project has confirmed** (EXEC,
`p4_hr_risk.py`, 300,000 turns, identical draws for both policies, opposing
batter = our own `best_batting_play`):

| our pitching policy, 1 runner on | out | hit | **home run** | runs conceded/turn |
|---|---|---|---|---|
| current (fielding priority) | 23.8% | 24.4% | **51.8%** | **1.036** |
| power-max + always pitch boost | 60.4% | 24.1% | **15.5%** | **0.309** |

**3.35× the runs conceded, on exactly the turns the heuristic exists to protect.**
Identical at 2 and 3 runners (+1.09 and +1.45 runs/turn).

### Why the "simulation blind spot" defence does not cover this

HEURISTICS.md §2 declines to change this because `resolve()` cannot model
fielding, and §2 is right about that. But §2 tested only one alternative:
**removing fielding priority entirely.** The blind-spot objection applies fully
to that variant and barely at all to a *graded* one.

The confirmed rule is that beating the defender by 3+ is a home run that clears
every runner at once. Fielding, whatever it does, is described everywhere in this
project as affecting **baserunner advancement** — nothing in the confirmed rule
leaves room for it to prevent a home run. So the trade is not
"unknown upside vs unknown downside". It is **an unknown upside against a
confirmed, measured, catastrophic downside**, taken at any price.

**Ablation (EXEC, `p7b.py`, n=3000 × 4 seeds; noise floor measured at ±2.5 pts
by a current-vs-itself control):**

| variant vs. current | win rate |
|---|---|
| slack=0 (fielding as a pure tiebreak among equal-power cards) | 47.9–49.2% vs 29.0–30.9% |
| slack=1 (pay at most 1 power for fielding) | **47–48% vs 30–33%** |
| slack=2 | 45–46% vs 31–34% |
| slack=3 | 43–44% vs 34–36% |
| no fielding priority at all (§2's variant) | 55–58% vs 21–23% |
| slack=1 **and** pitch-boost-first (L2) | **54–56% vs 22–24%** |

The ordering is monotone in slack, which is exactly what a power-blind simulator
*must* produce, so the ordering is **not** evidence about the right slack value.
What is evidence: **every** point on that axis beats the current rule by 10–35
points, far outside the ±2.5 noise floor, and the current rule sits at the
extreme endpoint (infinite slack). Whatever fielding is worth, "any price" is
not it.

**Real-data corroboration** (already in MATCH_DATA_ANALYSIS.md §3, n=2, not
conclusive on its own): row 30 played a 5/1 pitcher against a 9-power batter and
conceded a home run.

**Also note the sim under-weights this branch:** it puts a runner on base on
23.4% of turns; `match_log.jsonl` shows 33.3% (13 of 39). The measured gap is if
anything conservative.

**Recommended fix** — smallest change that keeps the fielding preference intact
where it is cheap:

```python
best_power = max(c.power for c in hand_players)
pool = [c for c in hand_players if c.power >= best_power - FIELDING_SLACK]  # 0 or 1
best_pitcher = max(pool, key=lambda c: (c.secondary, c.power))
```

---

## L2 — CRITICAL. Pitching throws away a pitch boost for a fielding boost; batting does the opposite

`decision_engine.py:140-145`

```python
if runners_on and field_boosts:
    tactics_choice = max(field_boosts, key=lambda t: t.bonus)
elif pitch_boosts:
    tactics_choice = max(pitch_boosts, key=lambda t: t.bonus)
```

A fielding boost adds **zero** power (`simulate.py:97`, verified — see "found
nothing" §N2). A pitch boost adds its full bonus. With runners on, the fielding
boost wins unconditionally, however small, however large the pitch boost.

**Concrete scenario (EXEC, `p2_engine.py` case D):**

> Pitching, runner on. Hand holds `Pitch Focus +3` **and** `Fielding Play +1`.
> → attaches **Fielding Play +1**, discarding a confirmed +3 power for an
> unconfirmed effect.

**The same file does the opposite on the batting side** (`decision_engine.py:98-106`):

> Batting, runner on. Hand holds `Power Swing +1` **and** `Speed Boost +3`.
> → attaches **Power Swing +1** — the power boost, correctly.

Same situation, mirrored stats, opposite policy. One of the two is wrong and
nothing in HEURISTICS.md explains the asymmetry.

**Frequency (EXEC, 200k hands, runner on base):** 165,513 hands contained a
pitch boost; **63.2%** of them passed it over for a fielding boost, discarding a
mean of **+2.24 power** each time.

**This has never been tested.** HEURISTICS §2 isolated only the *pitcher
selection*; the tactics choice was never varied. Isolating it (EXEC, `p7b.py`):
**pitch-boost-first alone wins 44.5–46.1% vs current's 31.9–34.5%** across four
seeds — a 12-point swing from a change that never alters which pitcher is played.

**Combined worst case, one turn:**

> Hand: `Josef Bunz-Konicky 9/2`, `Joel Blunt 9/0`, `Pitch Focus +3`, `Fielding Play +1`, runner on.
> → effective pitch power **9**. Best available was **12**.

**Recommended fix:** prefer the pitch boost; fall back to the fielding boost only
when no pitch boost is in hand (which still plays it — see L7).

---

## L3 — HIGH. Zero test coverage. All five decision functions can be inverted and the suite stays green

**MUT-proved.** Five mutations applied to a sandbox `decision_engine.py`:

| # | mutation |
|---|---|
| M1 | `best_batting_play` plays the **lowest**-power batter |
| M2 | `best_batting_play` **never** attaches a swing boost |
| M3 | `best_pitching_play` plays the **lowest**-power pitcher |
| M4 | `should_redraw` returns **`True` unconditionally** (burns every discard immediately) |
| M5 | `choose_bans` bans the **three strongest** cards in the collection |

Full `./run_tests.sh` before and after, output diffed:

```
IDENTICAL — no test detected any of the 5 mutations
13 PASS, 3 FAIL
```

(The 3 FAILs are identical in both runs and are sandbox artefacts — I excluded
`Photos to train on/` from the copy, so `test_gameplay_regions`,
`test_ocr_runner`, `test_ocr_scoreboard` cannot find their fixtures. They are
image tests and cannot detect a decision mutation either way.)

Why nothing catches it:

- `run_tests.sh:5` globs `test_*.py`. **`decision_engine.py`'s `__main__` block
  — which contains the only two assertions about play quality in the repo
  (lines 199 and 207) — is never executed by anything.** Same for `simulate.py`.
- `test_run_state_machine.py:170` **stubs `play_one_turn` out entirely**
  (`"play_one_turn": self._play_one_turn`), so no test ever runs a real decision.
- `choose_bans` *is* live in that harness, but the only assertions are
  `len(bans_submitted) == 1` (line 295) and `len(bans_submitted[0]) == 3`
  (line 298) — **count, never identity.** M5 passes cleanly.
- `test_state_io.py:116-127` covers `hand_to_cards`'s index mapping only.
- `test_settle_regions.py:9` and `test_ban_grid_locked.py:6` merely mention
  `should_redraw` / `choose_bans` in comments.

This is the LESSONS.md §1 pattern in its purest form: the suite is green and
asserts nothing about the thing it appears to cover. Everything else in this
document exists because nothing was watching.

**Minimum useful coverage** (a `test_decision_engine.py` that would have caught
all five): assert the batter chosen is the max-power one; assert a swing boost is
always attached when present; assert the pitcher chosen when runners are on is
within N power of the best; assert `should_redraw` is False at power 5 and True
at power 4 **and** False when `redraws_left == 0`; assert `choose_bans` on the
real `KNOWN_BAN_ROSTER` returns three specific named cards.

---

## L4 — HIGH. `choose_bans`: right direction, arbitrary tiebreak, and its supporting evidence is contradicted by the match log

`decision_engine.py:163-172` — `return sorted(collection, key=lambda c: c.power)[:count]`

### Direction is correct — we are not supposed to be banning the opponent's cards

The ban screen shows **our own collection**: `READ_STATE_PROMPT`
(`orchestrator.py:264`) defines `ban_screen` as *"the 'BANNED CARDS x/3'
pre-match screen showing a grid of your collection"*, and
`read_full_ban_collection` resolves every grid cell against `KNOWN_BAN_ROSTER`,
which is our roster. So `sorted(...)` ascending (weakest first) is the right
direction and banning "the opponent's best cards" is not a thing this screen can
do. **No defect here.**

### But the tiebreak is arbitrary grid order, and it demonstrably bans the wrong card

`sorted()` is stable, so ties are broken by position in the list, which is the
row-major scan order out of `read_full_ban_collection`. On the real 33-card
roster **eight cards tie at the minimum power of 4** (EXEC, `p1_bans.py`):

```
ACTUAL bans:   William Lee-Gains 4/0
               Joshua Diaz 4/0
               Johnny "Blaze" Sweets 4/3   <-- max secondary in the whole pool
kept instead:  Marian Bunz-Twarog 4/1, Jedediah Wetters 4/2, ...
```

We ban a `secondary=3` card and keep a `secondary=1` card of identical power.
Mean secondary of the surviving pool: **1.300** now vs **1.367** with a
`(power, secondary)` tiebreak; mean power is **6.200 either way** — the fix is
strictly free.

This matters by the project's own lights: `best_pitching_play` treats `secondary`
as its top priority (L1), so `choose_bans` is actively removing the cards that
branch depends on.

**The simulation cannot see this and never will** — `resolve()` compares power
only, so a `(power, secondary)` tiebreak measures inside the noise floor
(39.0–40.4% vs 37.3–40.5%, four seeds, n=2000). That is a null result about the
instrument, not about the change. Recommend it on the free-and-consistent
argument, not on a simulated win rate.

### HEURISTICS §4's "banning clearly helps" rests on a modelling assumption the match log contradicts

§4 measured ban-weakest by removing cards from **our** pool while the opponent
kept the full 33 (`simulate.py`'s separate `player_pool` / `defender_player_pool`).
MATCH_DATA_ANALYSIS.md §5 found **19 of 19** opponent cards fuzzy-match
`KNOWN_BAN_ROSTER` — the pool is shared — and noted the simulation does not model
that.

I measured both models (EXEC, `p5_bans_shared.py`, n=2000 × 4 seeds):

| model | result |
|---|---|
| **separate pools** (what §4 measured) | ban-weakest **43.1–45.5%** vs no-ban **33.2–35.8%** — reproduces §4 |
| **shared pool** (what the log implies) | mean runs/match **1.916–1.954** banned vs **1.905–1.934** full — **no effect** |

Under a shared pool the ban raises both sides equally and is worth exactly zero.
Banning is mandatory to start a match, so this is not "stop banning" — it is that
**the claim "ban-weakest is a validated advantage" does not survive the project's
own data.** §4 should be re-labelled as contingent on the separate-pool
assumption.

---

## L5 — MEDIUM. `batters_used` never resets between matches

`orchestrator.py:2505-2506` (initialised once, before the loop),
`2990-2992` (reset **only** on a phase change), `3008` (incremented only when
`played`).

EXEC, `p8_batters_used.py`, driving the real `run()` loop through the project's
own `Harness` with `play_one_turn` spied on:

**(a) the documented redraw undercount (N27) reproduces:**
6 batting turns with plays at 1,3,5,6 → `batters_used` handed in as
`[0, 1, 1, 2, 2, 3]`.

**(b) new — cross-match carryover:**
match 1 (2 batting turns) → win → pay → ban → match 2 (batting).
`batters_used` handed to **match 2's first batter was `2`, not `0`.**

`last_phase` is initialised to `None` once at line 2488 and cleared nowhere else;
`match_in_progress = False` at line 2755 does not touch it. Any two consecutive
matches that open on the same phase continue the previous count. Over a long
session `batters_used` drifts arbitrarily far from reality.

Inert today because no decision function reads it (see §N5) — but HEURISTICS.md
§5's Variant B is precisely "redraw threshold by turn position", i.e. the code
that would read it. N27 warns about the redraw undercount; it does not mention
this one. `grep -rn batters_used --include=test_*.py` → **no hits**.

---

## L6 — MEDIUM. Six input shapes `validate_game_state` accepts crash `play_one_turn`

`orchestrator.py:2356-2358` (`hand_to_cards`) and `2389` (runners) index keys the
validator never checks. `validate_game_state` checks `power` is an `int` for
player cards and `type` is a valid enum for tactics — it checks **nothing** about
`secondary`, `bonus`, or runner dicts at all (`orchestrator.py:1627-1671`).

EXEC, `p9_play_one_turn.py` §E (each state passed `validate_game_state` first,
then crashed):

| input | crash |
|---|---|
| hand player card with no `"secondary"` key | `KeyError: 'secondary'` |
| hand player card `"secondary": null`, pitching + runner on | `TypeError: '>' not supported between NoneType and int` |
| tactics card with no `"bonus"` key | `KeyError: 'bonus'` |
| two swing boosts, one with `"bonus": null` | `TypeError: '>' not supported between int and NoneType` |
| runner dict with no `"secondary"` key | `KeyError: 'secondary'` |
| runner dict with no `"power"` key | `KeyError: 'power'` |

These are caught by `run()`'s per-turn `try/except` (`orchestrator.py:3018`) and
retried, so they are not fatal — but each burns a vision call and a
`stuck_count`, and a *systematic* vision quirk (the model omitting `secondary`
on a card style it finds hard to read) exhausts `MAX_STUCK_ATTEMPTS` and ends
the run mid-match. This is the same class the project already fixed once for the
ban path — see the `I8` comment at `orchestrator.py:2220`, *"the prompt permits
nulls, and the line below indexes `c["secondary"]` directly"* — the identical
hole in the hand/runner path was never closed.

Cheap fix: extend the existing per-card loop in `validate_game_state` to require
`isinstance(card.get("secondary"), int)` for players and
`isinstance(card.get("bonus"), int)` for tactics, and validate runner dicts the
same way it validates hand cards.

---

## L7 — MEDIUM. Speed and fielding boosts are held back for no reason the project's own doctrine supports

`decision_engine.py:104` (`elif speed_boosts and state.runners`) and `140`
(`if runners_on and field_boosts`). With the bases empty, a speed-boost-only or
fielding-boost-only hand plays **no tactics card at all**.

EXEC, `p10_power_bonus.py` §C, 200k hands per phase, runners on ~1/3 of turns:

| phase | hands holding ≥1 tactics card | of those, play none | why |
|---|---|---|---|
| batting | 96.8% | **14.7%** | speed-boost-only, bases empty |
| pitching | 96.7% | **9.8%** | fielding-boost-only, no runners |

HEURISTICS.md §1's stated reason for always attaching a boost is:

> *"hands redraw fresh each round rather than depleting a shared pool worth
> conserving"*

That argument is about the **cost** of playing a card, and it is exactly as true
for a speed boost as for a swing boost. Playing an unused speed boost is free.
If speed does anything at all — including helping the batter himself, who becomes
a runner on a hit — playing it weakly dominates holding it. The `and
state.runners` conditions contradict §1's own reasoning.

Low confidence in the size of the gain (the simulation is blind to it by
construction), high confidence that it costs nothing.

---

## L8 — LOW. A misread `discards_left` silently disables redraws for the whole match

`orchestrator.py:2393-2395`:

```python
discards_left = state_json.get("discards_left")
if discards_left is None:
    discards_left = 0
```

EXEC (`p9_play_one_turn.py` §D): with `discards_left` null *or* the key absent, a
hand whose best card is power 4 plays it rather than redrawing.

The direction is deliberate and correct — over-discarding sends real keypresses
into a paid match. But `READ_STATE_PROMPT` explicitly permits null
(*"Use null if this counter isn't visible on screen"*) and the counter is a dot
graphic, the sort of thing OCR gets wrong systematically rather than randomly.
If it reads null every turn, the bot never redraws for an entire session and
**nothing says so** — the printed decision line just reads "Playing X (power 4)"
like any other turn. Worth one `print()` when the default is taken, so the
capability loss is visible in the log rather than inferred.

---

## L9 — LOW. No role filter: a PITCHER card in a batting hand gets played

EXEC (`p9_play_one_turn.py` §G): a batting hand of `Batter Bob 6/1` and
`Pitcher Pete 9/0` plays **Pitcher Pete**.

`READ_STATE_PROMPT` tags both BATTER and PITCHER cards as `kind: "player"`
(`orchestrator.py:298-300` describes the BATTER/PITCHER label only for the ban
grid), `hand_to_cards` splits on `kind` alone, and `best_batting_play` takes the
max over everything handed to it. Flagged as structurally possible in
MATCH_DATA_ANALYSIS.md §3 off rows 22 and 39; this confirms the **code** behaves
that way. Whether such hands actually occur still needs one live look.

---

## L10 — LOW. `target_score` is set unconditionally on the pitching half

`orchestrator.py:2402`:

```python
target_score=state_json["your_score"] if state_json["phase"] == "pitching" else None,
```

`GameState.target_score` is documented as *"known only while pitching (your final
batting score)"*. But if the bot ever pitches the **first** half of a match, our
score is `0` and is not a target at all — the field would read `target_score=0`
while meaning "we haven't batted yet".

`simulate.py:187` models exactly that case correctly (`defender_target_score=None`
for the first half) — so the simulator and the orchestrator disagree about what
this field means.

Inert today (nothing reads `target_score` — §N5). It becomes live the moment
HEURISTICS §5 Variant A is applied: its condition is `opp_score >= target_score`,
which with `target_score == 0` is **true from the first pitch of the half**,
silently disabling every redraw. That is the same shape of bug §5 already caught
once ("the condition could never fire") — this time it would always fire.

---

## L11 — LOW. `power_bonus` falls through to 0 for an unknown `TacticsType`

`simulate.py:87-99`. All four current members are handled correctly (see §N2).
But the function ends in a bare `return 0`, so a fifth `TacticsType` added later
is silently priced at zero power with no error and no warning — and every
HEURISTICS.md number would quietly shift. EXEC: an object with an unrecognised
`kind` and `bonus=5` returns `0`.

A `raise ValueError(f"unhandled tactics kind: {tactics_card.kind}")` on the
fall-through costs nothing and fails loudly instead.

---

## L12 — LOW. `choose_bans` silently returns fewer than `count`

`decision_engine.py:172` — `sorted(...)[:count]` with no minimum check. EXEC: a
2-card collection with `count=3` returns 2 cards, no complaint. The caller does
check (`orchestrator.py:2923`, `if len(bans) != 3: raise`), and that check is
good — but the function itself is happy to under-deliver, and it is the function
that documents itself as choosing "which player cards to ban".

---

## L13 — INFO. The discard branch discards whatever the *play* heuristic picked

`orchestrator.py:2415-2419`. `should_redraw`'s rationale is about **power**
("your best available card is weak"), but the index it discards is
`decision.player_card`'s — and on a pitching turn with runners on, that card was
chosen by **fielding** (L1), not power.

EXEC (`p9_play_one_turn.py` §C): pitching hand `LowField 4/0` at index 0 and
`HighField 4/3` at index 1, runner on → **discards index 1**, the high-fielding
card, while the printed reason talks about power.

**This is currently harmless** and I want to be precise about why:
`input_controller.select_and_discard` is `confirm_discard` → `confirm_play`, so
the replacement card is auto-lifted and played immediately; the rest of the hand
never gets used, and hands redraw fresh each round. Which card you discard
therefore cannot matter. But nothing in either file records that dependency, and
it silently becomes a real bug if discard ever stops auto-playing the
replacement. Worth a one-line comment at `orchestrator.py:2416`.

---

# Where I found nothing

Four of these had a concrete failure theory going in. All four came back clean;
recording them so the next pass does not re-spend the time.

### N1 — Card index mapping is correct, including for equal-but-distinct cards

The identity check `next(i for i, p in players if p is decision.player_card)`
(`orchestrator.py:2416`, `2424`, `2427`) is **safe**.

EXEC (`p9_play_one_turn.py` §A-B):

- `hand_to_cards` (`orchestrator.py:2356`) constructs a **fresh** `PlayerCard`
  per hand entry, so two byte-identical cards at different hand positions are
  still distinct objects. A hand of `Twin 8/1` at index 0 and `Twin 8/1` at index
  3 plays **index 0**, correctly and unambiguously. (`==` would match both —
  `PlayerCard("Twin",8,1) == PlayerCard("Twin",8,1)` is `True` — so `is` is not
  just adequate here, it is the *only* correct choice.)
- The same object cannot appear twice, because there is no shared-object path
  into a hand (unlike the ban grid, where `roster_hits[pos] = KNOWN_BAN_ROSTER[pos]`
  at `orchestrator.py:2113` **does** share objects — already guarded by the N15
  `len({id(b) for b in bans}) != 3` check at line 2948).
- `validate_game_state` rejects duplicate `hand_index` (line 1633), so the
  recovered index is always a real, distinct slot.
- Non-contiguous indices survive: a hand with the only player card at index 4
  presses index 4.

The only latent wart is that `next()` has no default, so a decision function
returning a card not from the hand would raise a bare `StopIteration` with an
empty message — `run()` would print `Couldn't act on this turn ()`. Unreachable
today; a `default=None` plus an explicit raise would be clearer.

### N2 — `power_bonus` handles every `TacticsType` correctly; speed and fielding genuinely add no power

EXEC (`p10_power_bonus.py` §A). All four members enumerated:
`SWING_BOOST → bonus`, `PITCH_BOOST → bonus`, `SPEED_BOOST → 0`,
`FIELDING_BOOST → 0`, `None → 0`. `TacticsType` has exactly these four members
and `validate_game_state:1624` rejects any `type` outside them, so no unhandled
value can reach it from a real read. The 2026-08-23 fix recorded in the docstring
is correct and complete. (The fall-through for a hypothetical *future* member is
L11, a robustness nit, not a live bug.)

### N3 — `should_redraw`'s blindness to tactics is real but is NOT a defect

`should_redraw(hand_players, state)` takes no tactics argument
(`decision_engine.py:150`), so a hand of `Batter 4/0` + `Power Swing +3` —
effective power 7 — is discarded rather than played. That looks obviously wrong.
It measured **neutral to slightly negative**:

- Turn level (EXEC, `p6_redraw.py`, 200k samples on exactly the contested hands):
  playing the boosted card scores **fewer** runs than discarding
  (0.0017 vs 0.0139 at 0 runners; 0.2055 vs 0.2928 at 1 runner).
- Match level (EXEC, `p7_redraw_match.py`, a tactics-aware `should_redraw`
  through an otherwise identical simulator, n=3000 × 4 seeds):
  **37.7–40.3% vs current's 39.2–42.1%** — inside the ±2.5 point noise floor
  measured by the current-vs-itself control on the same run.

The reason is not subtle once measured: `should_redraw` only fires when the best
card is power ≤4, so the boosted ceiling is 4+3 = **7**, while a random
replacement from the real pool has mean 6.0 and reaches **9**. Against a defender
playing max power plus a boost, only the 9s win. The discard's upside is worth
more than the boost's certainty.

For the record: 6.3% of batting hands trigger `should_redraw`, and 90.1% of those
do hold a swing boost — so the blind spot bites constantly. It is simply not
costing anything.

### N4 — No off-by-one in `redraws_left`

`discards_left` is documented and prompted as the count of **remaining** usable
discards (`orchestrator.py:2393`, `READ_STATE_PROMPT` line ~275), and
`should_redraw` guards `if state.redraws_left <= 0: return False`
(`decision_engine.py:158`). That is the correct comparison for a
remaining-count. Nothing decrements it locally — it is re-read from vision every
turn — so there is no drift to be off by. Clean.

### N5 — `runners`, `score`, `target_score`, `half`: used correctly, or not used at all

Introspection of the three decision functions (EXEC, `p2_engine.py` §I):

| function | `state.*` fields actually read |
|---|---|
| `best_batting_play` | `runners` |
| `best_pitching_play` | `runners` |
| `should_redraw` | `redraws_left` |

`batters_used`, `your_score`, `opp_score`, `target_score`, and `half` are set by
`play_one_turn` and read by nothing — consistent with HEURISTICS.md §5, which
tested reinstating two of them and found no benefit. `runners` is used correctly
in both halves (on a pitching turn the runners on base *are* the opponent's, so
the same field is the right one). `half` is redundant because `play_one_turn`
branches on `state_json["phase"]` directly (`orchestrator.py:2410`) rather than
on `state.half`, so the two cannot disagree.

L5 and L10 above are about the *values* being wrong, not the reads — they are
latent, not live, precisely because of this table.

### N6 — The all-tactics-hand crash is unreachable in production

The ordering concern is real at the function level: `play_one_turn` calls
`best_batting_play` at line 2411 **before** `should_redraw` at 2415, and an empty
`hand_players` raises `IndexError: list index out of range` at
`decision_engine.py:89-90` (`best_pitching_play` raises
`ValueError: max() iterable argument is empty`) — so the discard path, which is
the correct response to an all-tactics hand, is never reached.

But `validate_game_state:1650-1653` rejects a `turn` screen with no player card
first, and `play_one_turn` is only ever called from the `screen == "turn"` branch
(`orchestrator.py:3017`; the `discard_prompt` branch at 2975 presses
`confirm_play` instead and never calls it). EXEC-confirmed both halves.

Residual risk, flagged rather than claimed: **if a genuine all-tactics hand can
occur**, the bot cannot play it at all — every read is rejected as invalid and
retried until `MAX_STUCK_ATTEMPTS`, ending the run mid-match. The codebase
asserts this cannot happen (`simulate.py:71` rerolls such hands "since every real
hand has at least one" player card; the validator's own message calls it "likely
a mid-deal or partial read"). If that belief is ever falsified, this becomes a
hard deadlock, not a graceful discard.

### N7 — `best_batting_play`'s core policy is correct

Highest-power batter, always attach the best swing boost, fall back to a speed
boost only with runners on. Re-verified as the right shape: it reads the pool
correctly, the always-boost finding reproduces, and I found no scenario where it
plays a strictly worse card than an alternative in hand. Its only defects are the
arbitrary tiebreak among equal-power batters (it ignores `secondary` entirely —
the pick flips with hand order, EXEC `p2_engine.py` §A; same free fix as L4) and
the held-back speed boost (L7).

### N8 — `simulate.py`'s board states are a reasonable match for the real log

Given that every number in HEURISTICS.md comes out of this simulator, I checked
its fidelity against `match_log.jsonl` (39 non-synthetic turns) rather than
assuming it (EXEC, 40,000 simulated halves):

| runners on base at the start of a turn | simulate.py | match_log |
|---|---|---|
| 0 | 76.6% | 66.7% |
| 1 | 18.5% | 30.8% |
| 2 | 4.1% | 2.6% |
| 3+ | 0.8% | 0.0% |

| outcome | simulate.py | match_log (labels known-biased) |
|---|---|---|
| out | 52.0% | 64.1% |
| hit | 23.8% | 15.4% |
| home run | 24.1% | 20.5% |

Close enough that the relative comparisons in HEURISTICS.md are not obviously
invalidated. Two caveats worth recording:

1. `simulate_batting_half` (`simulate.py:166-171`) **never scores a run on a
   plain hit** — runners only ever score via a home run, and there is no cap on
   how many can be on base. That systematically over-rewards power-maximising
   strategies, which is the direction of §1's always-boost finding. §1 is almost
   certainly still right (it also wins at every `TACTICS_FRACTION` tested), but
   its *magnitude* should be read as an upper bound.
2. The simulator puts a runner on base on 23.4% of turns vs the log's 33.3%, so
   it **under**-weights every runners-on branch — including L1 and L2. Those
   measured gaps are conservative.

---

## Reproduction

All probes are self-contained and live in the session scratchpad
(`.../scratchpad/qalogic/`), reading `decision_engine.py` / `simulate.py` from a
copy and `KNOWN_BAN_ROSTER` by parsing the real `orchestrator.py` (never
importing it for the pure-logic probes):

| file | what it establishes |
|---|---|
| `p1_bans.py` | L4 ban tiebreak on the real 33-card roster |
| `p2_engine.py` | L1, L2, L7, L12, N5, N7 — direct decision probes |
| `p3_fielding_cost.py` | L1/L2 frequency and magnitude, 200k hands |
| `p4_hr_risk.py` | L1 home-run cost under the confirmed rule, 300k turns |
| `p5_bans_shared.py` | L4 separate-pool vs shared-pool ban models |
| `p6_redraw.py`, `p7_redraw_match.py`, `p7b.py` | N3 (negative) and the L1/L2 ablation |
| `p8_batters_used.py` | L5, driven through the project's own `Harness` |
| `p9_play_one_turn.py` | L6, L9, L13, N1, N6 — `play_one_turn` with input stubbed |
| `p10_power_bonus.py` | N2, L7, L11 |
| `suite_baseline.txt` / `suite_mutated.txt` | L3, the five-mutation MUT proof |

Sandbox copies live in `qalogic/proj/` (mutated) and `qalogic/proj_clean/`
(pristine); `qalogic/proj/decision_engine.py.orig` holds the pre-mutation file.
