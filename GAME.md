# What things cost, and the game's own rules (§4)

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

---

## §4 What things cost, and the game's own rules

- A match costs **$50** in-game. BOX/Square at the table starts one.
- "Load Last Save" restores the wallet to **$246** (4 matches).
- **SO MONEY SPENT IS RECOVERABLE, AND THAT IS WHAT MAKES UNATTENDED ONLINE WORK
  AFFORDABLE.** The user's call, 2026-09-13: *"You can do online work too. A reset
  recovers spent money."* A match that goes wrong costs TIME, not money -- one
  `reset_env.reset_environment(progress_file=...)` restores the wallet to $246 AND
  clears `match_in_progress` (see "A RESET IS THE MONEY RECONCILER" below, walked
  end to end on the live rig). The tracked balance is still set BY HAND afterwards,
  because the wallet is not read from the game.

  **What this does and does not license.** It removes MONEY as a reason to refuse
  an overnight run. It does not remove the others, and they are the ones that
  matter: a run that bans the WRONG CARD and reports 3/3 produces a result nobody
  can attribute, and no reset repairs a conclusion drawn from it. Cheap to redo is
  not the same as safe to trust -- spend the recovered money on runs whose OUTPUT
  will mean something.
- `api_budget` is a HARD ceiling for the whole process, set via
  `BASEBALL_API_BUDGET`. Every retry on a bad read is a paid call.
- A **stable misread cannot be fixed by retrying** — same frame, same prompt,
  same wrong answer. Repair or clamp it instead of looping.

### THE SHAPE OF A MATCH (from the user, 2026-09-12 — the model had this wrong)

    new hand  ->  play as the BATTER   ->  inning 1 ends
    new hand  ->  play as the PITCHER  ->  inning 2 ends  ->  match over

**The two innings ARE the two halves.** You bat in inning ONE and pitch in inning
TWO; you never bat twice. Each half deals a FRESH hand of 5, and within a half the
hand persists and is topped up ONE card per play — `wait_for_hand_deal` blocks
"until the replacement card has visibly landed", singular, and a discard keeps the
rest of the hand. **5 rounds PER HALF**, so five at-bats batting and five pitching.

**The scoreboard is `[inning1, inning2, TOTAL]` — the third box is the total, NOT a
third inning. Never sum it; take `[-1]`.** `ocr_scoreboard` has documented this all
along and the live consumer takes `[-1]` correctly. A live board reading
`your [2, 0, 2]` against `opponent [0, 0, 0]` is the whole structure in one glance:
we scored 2 batting in inning 1, we do not bat in inning 2, and the opponent has yet
to score in the inning they are batting now.

`simulate.py` got this wrong twice in one day and both mistakes are worth knowing:
it redrew BOTH hands every ROUND (so card economy could not exist — nothing survived
to a later turn), and a "fix" then looped the match over two innings, playing four
halves and doubling every score. The A-bats-then-B-bats shape was right all along.

### WHAT THE CARDS ARE WORTH, MEASURED

Counted over **299 tactics cards labelled BY HAND** in `hand_labels*.json` — human
labels, so this is not one of this project's readers marking its own homework:

    POWER SWING     n= 95    +1 60%   +2 40%     <- the ONLY card ever above +1
    SPEED BOOST     n=132    +1 100%
    PITCH FOCUS     n= 35    +1 100%
    FIELDING PLAY   n= 37    +1 100%
                             zero 3s, zero unlabelled

**A +3 DOES NOT EXIST.** The user said so and was right; the paid vision model's
eleven "bonus 3" rows are misreads, from the same source that once recorded a bonus
of **ELEVEN**. That is the seventh documented way that model was wrong about cards.

**`KNOWN_BAN_ROSTER` CANNOT ANSWER A TACTICS QUESTION** — it is 33 `PlayerCard`s and
no tactics cards at all. Player powers run **4–9**; a power outside that is a misread.

### EVERY CARD IS A BATTER OR A PITCHER, AND `secondary` MEANS A DIFFERENT STAT IN EACH

The user's call, 2026-09-13: *"it might be useful to also read the players type, so you
don't mark a pitcher with speed since that doesn't make sense."* `PlayerCard.secondary` is
SPEED on a batter and FIELDING on a pitcher -- the field's own comment always said so --
and there was no role field, so nothing could tell them apart. `simulate.draw_hand` dealt
all 33 cards in BOTH directions: a pitcher dealt as a batter had its fielding read as
speed, and a batter dealt as a pitcher brought a fielding of 3, which no pitcher has.

**THE TWO RANGES ARE DISJOINT WHERE IT MATTERS**, over 131 HAND-LABELLED cards split by
whether the hand they came from was batting or pitching:

    batters   speed     1 x14   2 x14   3 x38    n=66   NEVER 0
    pitchers  fielding  0 x39   1 x23   2 x3     n=65   NEVER 3

So secondary 0 implies PITCHER and 3 implies BATTER; 1 and 2 are shared and need the card's
banner. 33 of 33 are typed from FOUR signals that never once disagreed: the ban-grid banner
read by OCR, that range rule, the user reading cards off a ban grid, and **a card seen on a
BASE is a batter** (runners belong to the batting side, so occupancy types a card for free).
Brian Coker (8/1) and Zachary Lee (6/2) were typed BATTER on 2026-09-21, from three ban-grid
frames each (the TYPE banner survives the locked-card fade even though the NAME banner does
not), user-confirmed by eye. All 33 are typed now and `simulate.UNTYPED` is empty.

Splitting the pools moved the model **1.7223 -> 1.7862 runs/half (+3.7%, 4.6 sigma** at
n=20,000 per arm) -- the size of the error the unsplit pool was carrying.

**A CORRECTION THIS FORCED.** "30.5% of hand-labelled player cards are speed 0" was reported
here and a finding built on it -- that `bases_to_travel` and `simulate` disagree about a
speed-0 batter. Those cards were PITCHERS, pooled with batters precisely because there was
no role. **A batter's speed is never 0**, so that disagreement does not arise. It is still
reachable through fielding subtraction, which is a different open question.

**DO CARD VALUES CHANGE PER GAME? NO.** 1,691 player cards read across 540 hand crops
recorded on many different days: every (power, secondary) pair is already one of the
roster's, and ZERO novel pairs appeared. Six of the 24 possible combinations are absent from
the roster and none was ever drawn.

**CORRECTION 2026-09-13: THERE ARE AT LEAST TWO POWER SWING CARDS, NOT ONE.** Seen live on
the ban grid, side by side in the same row, both reading POWER SWING and carrying DIFFERENT
badges -- one **+1** and one **+2**. That is consistent with the bonus census two paragraphs
up (POWER SWING is the only card ever above +1: +1 60%, +2 40%) and it means the count below
is a floor, not a roster. It was taken by eye off one scroll position. The rest of the line
still stands as far as it goes.

**THE COLLECTION ALSO HOLDS TACTICS CARDS**, at the bottom of the ban grid: 1 Power Swing,
3 Speed Boost, 3 Pitch Focus, 3 Fielding Play. Every OWNED one shows a badge of **1** --
an independent confirmation of the +1 bonus census, from a different source entirely.

**So the maximum effective batter power is 9 + 2 = 11**, and that decides a pitching
choice the engine cannot see: a pitcher playing a **9 CANNOT concede a home run**
(margin 2), while one playing an **8 can** (margin 3).

Game rules:

- A hit needs the batter's power to beat the pitcher's; beating it by **3+** is
  an automatic home run. Margin does not otherwise matter. **The rule is ABSOLUTE**
  — confirmed by the user against the live scoreboard, 2026-09-12. Any record that
  shows a 3+ margin without a run is a bad LABEL, not a counterexample: 26 such rows
  in `match_log.jsonl` all came from the old "the score went up" classifier, which is
  why the outcome is now taken from the REVEAL's margin instead
  (`orchestrator.classify_outcome`).
- Only SWING_BOOST and PITCH_BOOST add power. Speed and fielding boosts have a
  nonzero bonus that adds NO power — analysis needs the tactics KIND.
- **Runners can be lapped**: this game lets base runners pass each other, so
  real-baseball intuitions about ordering are unsafe.
- **THE SCORE DOES NOT CHANGE WHICH CARD TO PLAY, and that is correct.** Neither
  `best_batting_play` nor `best_pitching_play` reads `your_score`/`opp_score`, and the
  match's shape is why: you bat once and then defend a fixed total, so you can never
  want fewer runs while batting and can only want outs while pitching. Max power both
  ways. The ONE place the score matters is RISK TOLERANCE when defending a lead —
  conceding a solo home run at +2 still leaves you ahead — which is a variance question,
  not a card-choice one. `target_score` is the one live score field, and only while
  pitching.

### The baserunning rules (from the user, 2026-09-10, with two sources)

Supplied by the user against a community guide and a Reddit write-up, and each
one CHANGES A DECISION the engine currently makes blind. Confirmed live where
noted; the rest is the user's reading, not this project's measurement.

- **SPEED (the `secondary` stat on a batter) is how many bases that player runs.**
  The badge it is read from made it look like a "shield" and this file called it
  that; it is speed. On a pitcher the same field is FIELDING. `decision_engine`
  already says so in one comment (`secondary: speed (batter) or fielding
  (pitcher)`) and nothing downstream used it.
  *Observed live:* a speed-1 batter advanced exactly 1 base, and a speed-1 runner
  advanced exactly 1 base on the next hit. Speed >= 2 is UNTESTED.
  **A SPEED BOOST APPLIES TO THE BATTER WHO PLAYED IT, FOR THAT HIT ONLY, AND IS THEN
  DISCARDED** — the runner reverts to baseline speed for any later advance (user's
  sources, 2026-09-12). That is why `simulate.speed_bonus` is added at the batter's own
  step and nowhere else: a runner is stored as its CARD and `advance_runners` re-derives
  speed from `card.secondary`, so reverting is free. It was worth ZERO until then
  (`batter_speed` was computed and never read).

  **RE-MEASURED 2026-09-13 ON THE ROLE-SPLIT POOLS, and the speed figure was wrong by 4x.**
  The numbers below it replaced (+0.034 speed, +0.726 swing, "21x less") were taken on the
  SCRAMBLED pool, before cards had roles: pitchers were dealt as batters with their FIELDING
  read as SPEED, so a third of "batters" had speed 0 and a speed boost on them bought
  almost nothing. A speed measurement taken where a third of the batters are pitchers is
  not a speed measurement. Same harness, same seeds, correct pools, n=20,000 halves an arm:

      no tactics     0.9589 runs/half
      SWING boost    1.5727   delta +0.614  (+52.8 sigma)
      SPEED boost    1.0901   delta +0.131  (+12.4 sigma)

  **THE CONCLUSION SURVIVES AND THE MARGIN DOES NOT.** Swing still wins decisively, so the
  engine's preference for it is unchanged and 99/1 still describes a tie-break rather than a
  trade. But the ratio is **4.7x, not 21x**, and any argument that leaned on "21x" as
  evidence that speed is negligible was leaning on an artefact.

  It is worth **+0.131 runs/half**, still less than a SWING boost's **+0.614**, which is
  power over speed.
  **AND THE OPEN QUESTION IS PRICED (2026-09-13).** Two runners have been read at +1 over
  their card -- Rube Sharp 1->2, Noah Kelly 2->3, both batters, both exactly a speed
  boost's +1 -- which would mean the boost PERSISTS on base, against the source above.
  Modelled by putting the boosted batter on base as a card whose secondary already includes
  the boost (same harness, same seeds, role-split pools, n=20,000 an arm):

      boost REVERTS (shipped)   1.0901 runs/half
      boost PERSISTS            1.1361   delta +0.046  (+4.2 sigma)

  So it is REAL AND LOW-STAKES. It moves a speed boost's worth by about a third, and even
  if it persists the total (0.177) is nowhere near a swing boost's 0.614 -- **it cannot flip
  the engine's preference.** Worth one live at-bat to settle; not worth planning around.

  **A RUNNER'S CURRENT SPEED IS READABLE OFF THEIR BASE**, from the shield badge:
  `local_state.read_runners()["speeds"]`. 171 of 172 occupied bases read it, zero of
  1,106 bare bases read anything. **It is NOT the card's roster `secondary`** — the same
  named card shows different values at different moments, so it is a LIVE number: what
  this runner advances NOW.
- **A TIE IS A COIN FLIP, AND WINNING ONE IS CAPPED AT FIRST BASE** regardless of
  the batter's speed. So landing exactly on the pitcher's power is the worst
  place to be: half the time nothing, half the time a minimum-value hit.
  *This invalidated a conclusion drawn here the same hour* — a speed-2 batter that
  stopped at first was read as "the batter always goes to first", when it was a
  5-v-5 tie. Two data points, one of them a special case, and a rule was written
  from them.
- **A LOSING AT-BAT CAN STILL ADVANCE RUNNERS, AND FIELDING IS WHAT STOPS IT.**
  Re-established 2026-09-16 by a two-condition experiment -- two OUTS differing
  only in an attached fielding boost: with it the runner did not move, without it
  the runner went first -> second, exactly its speed of 1. So this stays as the
  explanation for outs having a median reveal of 4.2 s and a MAXIMUM of 14.9 s
  (n=160).

  **IT WAS WITHDRAWN FOR AN HOUR ON A SOURCE AND THE MEASUREMENT PUT IT BACK.**
  Two community sources say only a hit moves anyone; the second at-bat disproved
  that directly. The first at-bat had ALREADY been flagged here as unable to
  separate the two explanations, and the rule was rewritten anyway before the
  experiment that separates them had been run. 10.2's shape in a new place: a
  plausible account is not evidence, and that includes a plausible account with a
  citation. See RULES.md.
- **BLACK PITCHER BUFFS SUBTRACT RUNNER MOVEMENT** — that is what FIELDING does,
  and it is why it only matters with runners on base.
  **This settles `decision_engine.FIELDING_POWER_BUDGET`, whose own comment says
  "the fielding effect is UNCONFIRMED ... Set to 0 for pure power-first once the
  question is settled" (it measured p=0.192 on 19 rows).** The question is now
  settled the OTHER way: do NOT zero it. The existing rule already pays the
  premium only when runners are on, which is exactly when the effect exists.

**WHAT THE ENGINE STILL CANNOT SEE — and THREE claims that used to sit here are
WITHDRAWN, because they described code that is gone (corrected 2026-09-16).** The
paragraph read that `best_batting_play` "sorts on POWER alone and attaches a speed
boost only as a fallback, and only when runners are already on base", that it
"cannot value a fast batter who wins outright", and that `simulate.py` consults
speed never. All three are false at HEAD, and `decision_engine`'s own docstring had
already said so while this file kept the old version:

    best_batting_play   scores every (batter, tactics) PAIR at
                        POWER_WEIGHT * power + SPEED_WEIGHT * speed, 99/1, and
                        takes the best -- so speed is read, and a boost attaches
                        whenever it costs no power, runners or no runners
    simulate.py         MODEL_SPEED = True since 2026-09-12; _step reads the
                        card's secondary and speed_bonus reaches the batter

Caught live on 2026-09-16 the cheapest possible way: the engine attached a speed
boost with the bases EMPTY, which this file said it could not do. **A doc claim
about what code cannot do is only worth the day it was written** — nothing fails
when the code outgrows it, which is 10.1's family pointed at prose.

**What survives, and it is the part that matters.** 99/1 is a TIE-BREAK, not a
trade: powers are integers, so one point of power is 0.99 against a widest-possible
speed gap of about 0.06 — speed decides between equal-power plays and nothing else.

**AND "NO NOTION OF TIE RISK" IS NOT A GAP. MEASURED 2026-09-17, and this file
called it "a real gap" until then.** Ties are common and they are worth something:
over 100,000 simulated at-bats **17.2% are ties**, and the coin is worth **0.30
runs/half** of spread -- 1.6362 if every tie were lost against 1.9399 if every one
were won, on a baseline of 1.7917. So the question was live, not academic.

It is still UNACTIONABLE, and the A/B says so at every weight. Take
best_batting_play's OWN scorer and subtract `tie_w x P(the defence shows exactly
this power)` -- one change, nothing else touched, 12,000 halves x 3 seeds:

    tie_w  0.0          1.7903   +0.0000   <- control: must equal shipped, and does
    tie_w  0.05 .. 10   1.7903   +0.0000   <- ZERO decisions changed at any of them
    tie_w 25.0          1.6588   -0.1315   <- the first weight that changes anything

**Any weight small enough to preserve power changes no decision; the first weight
large enough to change one costs 0.13 runs/half.** The mechanism is one sentence: a
TIE IS A 50% WIN, and the only way off a tie at power P is to play P-1 or lower,
which converts a coin flip against those same cards into a certain loss. Do not
rebuild this; it is closed.

**THE FIRST VERSION OF THE EXPERIMENT WAS WRONG AND THE SWEEP CAUGHT IT.** It scored
plays on power and tie risk alone, measured -0.22 runs/half, and looked like a clean
refutation. But every weight returned the IDENTICAL number, tie_w = 0 included --
and a knob that changes nothing is not measuring what its name says. That variant
had dropped the SPEED term, so it never attached a speed boost: two changes, one
attribution (10.7). The fix is the control -- tie_w = 0 must reproduce the shipped
number exactly.

And the 79%
win rate that justifies "always attach a swing boost" WAS measured in a model where
a speed boost does nothing by construction, so it shows swing-boost beats NOTHING
and has never compared swing against speed. Use the 2026-09-13 role-split figures
above (+0.614 against +0.131) for that comparison, never the 79%.
- A match is 5 rounds PER HALF (see the match shape above) and allows 2 discards
  PER HALF, so four across a match (measured 2026-09-16: the batting half ended
  at 0 and the pitching half opened at 2).
- **A DISCARD DOES NOT CONSUME A TURN, and N27 said it did.** The user confirmed
  it 2026-09-16, and that match's own arithmetic says so: 2 DISCARDS AND 5 PLAYS
  in a 5-round half. N27's claim rested entirely on select_and_discard ending in
  confirm_play -- a press that is now REMOVED, because it committed nothing
  useful and, whenever the Square press was dropped, played whatever was still
  lifted. It pitched the worst card in a hand at the opponent that day. See
  RULES.md.
- **You cannot pause an active match.** Mid-match OPTIONS opens a "Give up?"
  dialog (NO = circle, YES = cross), never the pause menu — so Load Last Save
  and the money readout are unreachable until the match ends.
  `reset_env.give_up_dialog()` detects it; answering YES costs nothing because
  the reload discards the match.
- The ban screen shows **"PLAY" against TRIANGLE**, and triangle commits
  whatever is banned and starts the match — it works at 1/3 bans. It is a safe
  way out of a ban screen that will not clear.

---
