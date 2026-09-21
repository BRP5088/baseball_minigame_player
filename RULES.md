# The rules of Baseball Cards

Everything here is about the GAME, not about this codebase. `CLAUDE.md` is what
is expensive to relearn about the RIG, the readers and the method; this file is
what is expensive to relearn about how the game itself behaves.

Each rule says where it came from. **"Measured"** means this project observed it
and can point at the evidence. **"From the user"** means the user supplied it,
usually against a community guide or by watching the screen — treat those as
instructions, not as measurements, unless a line also says confirmed.

---

## 1. The shape of a match

    new hand  ->  play as the BATTER   ->  inning 1 ends
    new hand  ->  play as the PITCHER  ->  inning 2 ends  ->  match over

*From the user, 2026-09-12.* The two innings ARE the two halves. You bat in
inning one and pitch in inning two; you never bat twice.

- **5 rounds per half**, so five at-bats batting and five pitching.
- Each half deals a **fresh hand of five**. Within a half the hand persists and
  is topped up ONE card per play.
- A match costs **$50**, taken at the dealer's prompt.

**The scoreboard is `[inning1, inning2, TOTAL]`.** The third box is the total,
not a third inning. Never sum it; take `[-1]`.

### A ROUND IS SIMULTANEOUS, THEN REVEALED

*From the user, 2026-09-20.* **Batting and pitching rounds are 1-to-1: both
players pick the cards they will play for that round, and when BOTH have
selected, the reveal phase starts.** There is no "your turn, then theirs" --
nobody is waiting on the opponent to move first.

**SO AN EMPTY BOARD IS NOT A BLOCKED TURN.** A hand that will not commit is
almost never the game refusing input; it is the commit not having been offered
yet, because nothing is selected. That distinction cost an hour on 2026-09-20:
five `select_card` presses were read as "the game is declining input" when the
real state was simply that no card had gone up yet.

**THE `△ PLAY` PROMPT IS A CONSEQUENCE OF SELECTION, NOT A PRECONDITION FOR
IT.** It appears once cards are selected and the round is ready to resolve, and
it gates the COMMIT. Do not wait for it before pressing select -- it cannot
appear until after. Read it as "the selection is done and the reveal is ready",
which makes it the right precondition for `confirm_play` and the wrong one for
`select_card`.

**PLAYING AND DISCARDING SHARE THE SELECT AND DIFFER AT THE COMMIT**, with a
different prompt for each:

    select a card       select_card      'enter'   -- the same for both
    commit a PLAY       confirm_play     'c'       -- the TRIANGLE / PLAY prompt
    commit a DISCARD    confirm_discard  '\\'

So the button that decides what a selection MEANS is the second one, not the
first. `select_and_discard` presses `select_card` then `confirm_discard` twice.

**AND THE COMMIT IS DECLINED AT THE SAME RATE AS ANY OTHER PRESS.** Measured
live 2026-09-20 on the pitching half: `confirm_play` was accepted by chiaki and
TRANSMITTED to the console (`[btnedge] id=8`) and the game ignored it **twice**
before the third press landed. CLAUDE.md section 5's 15.20% ignore rate, with
its documented clustering, applies to the committing press too -- so verify the
hand actually changed and press again, never assume a sent commit resolved.

**A DISCARD DOES NOT USE THE TURN.** It swaps one card for a new one and the
player still plays normally afterwards. *Confirmed by the user, 2026-09-16*, and
the arithmetic of that match agrees: the batting half took **2 discards AND 5
plays**, and a half is only 5 rounds -- five plays are impossible if a discard
costs one.

**Discards are 2 PER HALF, not 2 per match.** *Measured 2026-09-16:* the batting
half ended with `discards_left` 0 and the pitching half opened at 2. So a match
carries four discards in total, not two.

**You cannot pause an active match.** Mid-match OPTIONS opens a "Give up?"
dialog — NO is circle, YES is cross — never the pause menu.

---

## 2. Cards

**Every card is a BATTER or a PITCHER, and `secondary` means a different stat in
each: SPEED on a batter, FIELDING on a pitcher.**

    player powers        4 - 9        anything outside is a misread
    batter speed         1, 2, 3      NEVER 0
    pitcher fielding     0, 1, 2      NEVER 3

*Measured over 131 hand-labelled cards.* The two ranges are disjoint where it
matters: secondary 0 implies PITCHER, 3 implies BATTER; 1 and 2 are shared and
need the card's banner.

**Card values do not change between games.** *Measured:* 1,691 player cards
across 540 hand crops on many days produced zero novel (power, secondary) pairs.

### The collection / ban grid

*From the user, 2026-09-21:*

- **The ban grid shows ALL cards.** A LOCKED card is one the player has not
  unlocked yet, not a missing one.
- **Locked cards are NEVER dealt to the player**, so the draw pool is the OWNED
  cards only (31 today: Coker and Lee are locked in this save).
- **The game will not let you select a locked card as a ban** — a ban aimed at
  one is simply lost, the press does nothing — so the ban chooser must skip
  locked cards.

### Tactics cards

    POWER SWING     +1 60%   +2 40%
    SPEED BOOST     +1 100%
    PITCH FOCUS     +1 100%
    FIELDING PLAY   +1 100%

*Measured over 299 hand-labelled tactics cards **FROM OUR OWN HAND**.* **A +3
does not exist.** Any record showing one is a misread.

**THAT TABLE DESCRIBES OUR DECK. IT IS NOT A STATEMENT ABOUT THE GAME, BECAUSE
THE TWO PLAYERS HOLD SEPARATE DECKS AND DO NOT SHARE CARDS.** The user's point,
2026-09-17, and it is the right way round: *"since both players have separate
decks, one should conclude they can have different cards than us. we don't
share."* So nothing measured from our hand is evidence about what the opponent
can play, and the table above must never be used to resolve one of their cards.

**THE LINE THIS REPLACES SAID "POWER SWING ... the ONLY card ever above +1", AND
A LEGIBLE FRAME REFUTED IT (2026-09-17).** Turn 1 of a live match, read off the
reveal and confirmed by eye: our Austin "Cur" Bunz 8 + **POWER SWING +2** = 10
against their Jenny Jody Gain 6 + **PITCH FOCUS +2** = 8, margin 2 -- a hit, no
home run, runner to first, exactly as the screen then showed. **A PITCH FOCUS +2
exists.**

The provenance is what makes this predictable rather than unlucky: every key in
`hand_labels*.json` is a `hand_*.jpg` fan crop, so the opponent's played cards
were never in the sampled population at all. A census cannot discover a class it
never sampled (CLAUDE.md 10.31), and the separate decks mean our sample could
never have covered theirs however large it grew. **n=35 PITCH FOCUS all at +1 is
a fact about our deck; at 40% it would be a 1-in-10^8 coincidence, so this is
most likely a card we simply do not own.**

**WHERE IT IS LOAD-BEARING:** `reveal_cards.margin_from` infers "a +2 must be a
Power Swing, which adds power" whenever the banner does not read -- and the
banner abstains often (both sides abstained on the turn above). The margin came
out right only because Power Swing and Pitch Focus BOTH add power. A **FIELDING
PLAY +2** on their mound would be credited 2 power it does not have, which is
the difference between a logged hit and a logged out.

**Only SWING and PITCH boosts add power.** Speed and fielding boosts carry a
nonzero bonus that adds NONE, so the tactics KIND has to be known before a bonus
may enter a power calculation.

**A speed boost applies to the batter who played it, for that hit only**, and is
then discarded — the runner reverts to baseline speed for any later advance.
*From the user's sources, 2026-09-12.* An open question: two runners have been
read at +1 over their card, which would mean it persists. Modelled either way it
moves a speed boost's worth by about a third and cannot flip a decision.

**Observed in play, both halves, 2026-09-16:** the BATTER's attached tactics was
POWER SWING and the PITCHER's was PITCH FOCUS in all 17 readable reveals out of
54 — on both sides of the at-bat, so the game's own AI does it too. Zero Speed
Boosts or Fielding Plays were seen attached in any archived reveal.

---

## 3. Resolving an at-bat

**A hit needs the batter's power to beat the pitcher's; anything less is an
OUT.** *The user's sources: "If the batter's skill is lower than the pitcher's
skill, the batter misses and is out."* Margin does not otherwise matter —
except:

**Beating it by 3 or more is an automatic HOME RUN**, which clears every runner
on base plus the batter. *The rule is absolute*, confirmed by the user against
the live scoreboard and **measured 2026-09-16**: our 9 (7 + POWER SWING +2)
against their 6 (5 + PITCH FOCUS +1) is a margin of exactly 3, and the screen
printed HOME RUN! for 4 runs with the bases loaded.

**A TIE is a COIN FLIP, and winning one is capped at FIRST BASE** regardless of
the batter's speed. *Confirmed by the user, 2026-09-16*, and it explains an
at-bat the same day: our 9 against a 9, the batter stopped at first, and the
runners on second and third did not move at all.

**A LOSING AT-BAT STILL ADVANCES THE RUNNERS ALREADY ON BASE, AND FIELDING IS
WHAT STOPS IT.** Measured 2026-09-16 as a two-condition experiment, one at-bat
each, both OUTS, differing only in whether a fielding boost was attached:

    our 8 + FIELDING PLAY +1  vs their 4   margin -4  OUT   runner did NOT move
    our 9, NO tactics         vs their 7   margin -2  OUT   runner first -> second

The runner's speed was 1 and it advanced exactly 1 base. The batter reached no
base in either case (first was empty afterwards), so neither was a hit misread
as an out.

**A SOURCE SAID THE OPPOSITE AND THE MEASUREMENT BEAT IT.** A Steam discussion
and a video guide, supplied 2026-09-16, both say "only successful hits allow the
batter and existing runners to move across the bases". That was written into
this file and into CLAUDE.md, and the second at-bat above disproved it within
the hour. The first at-bat had been flagged as unable to separate "runners only
move on a hit" from "the boost ate the movement" -- and the rule was written
anyway, before the experiment that separated them had been run. n=1 per arm, so
the DIRECTION is established and the rate is not.

**AND THE CONVERSE IS ALSO TRUE: A WINNING AT-BAT CAN ADVANCE NOBODY, AND THE
BATTER IS LEFT STANDING ON HOME PLATE.** Seen live 2026-09-17, spotted by the
user watching the stream and captured in
`test_fixtures/blocked_runner/` --

    ours Donny Mekesz 5/3 + POWER SWING +1 = 6   vs   theirs 5
    margin +1, so a HIT by the game's own rule

...and nothing moved. Rube Sharp (8/1) stayed on FIRST where he had been since
the turn before, the score stayed 2-0, and our batter sat on HOME PLATE with his
card overlapping the hand. **Two players cannot occupy the same base**, so with
the runner pinned the batter had nowhere to go.

The mechanism is fielding, already recorded above: the PITCHER'S FIELDING
SUBTRACTS RUNNER MOVEMENT, and it can subtract all of it. `bases_to_travel`'s own
tests have pinned the arithmetic all along -- *"fielding 2 pins them all; only the
batter moves"*, and `bases_to_travel(bases(first=3), 1, -2, 3) == 0`. What was not
known is that the pin can cascade: pin the runner and you pin the BATTER behind
him, so a hit produces ZERO base-movements.

**WHAT IT COSTS ELSEWHERE.** `classify_outcome` returned plain `"hit"` here --
true, and indistinguishable from a bases-clearing one. It now returns
`hit_no_advance`, but ONLY when both runner counts were actually read: `rose` is
False both when nothing moved and when the runner reader abstained, and those two
must not collapse into one label.

**AND IT IS THE CHEAPEST CASE FOR THE DEAL GATE**, which is why it matters beyond
the record: zero base-movements is the shortest animation the game has, against a
home run with the bases loaded at ten. That spread is what `predicted_bases` was
always meant to carry.

**A SECOND OCCLUSION MECHANISM, VISIBLE IN THE SAME FRAME.** The played card
resting on home plate covers the hand slot beneath it, so a card can be
unreadable for reasons that have nothing to do with its neighbours in the fan.
**CORRECTION, SAME EVENING: IT IS NOT TRANSIENT, AND THE FIRST VERSION OF THIS
PARAGRAPH SAID IT WAS.** "Transient, clears when the at-bat resolves" was
REASONED, not observed, and it was committed that way. Watched for 18 s with no
input: frame deltas 1.3-3.7 (idle-animation level -- standing still measures
0.91-6.41), slot 2 unreadable in 10 of 10 samples, and the batter still on the
plate. The at-bat HAD resolved -- the turn screen was up and the engine was
taking decisions against it.

A STRANDED BATTER IS A PERSISTENT DISPLAY. He stays on home plate until something
moves him, so the slot beneath him is covered for the rest of the half. In effect
it is as permanent as 10.28's fan-neighbour occlusion; what differs is only the
OCCLUDER (a played card rather than a hand card), and that difference buys nothing
if you are waiting for it to clear.

**WHAT AN OUT DOES NOT DO** is advance the batter: they are out, and no base
gains an occupant.

**Since the maximum effective batter power is 9 + 2 = 11**, a pitcher playing a
**9 cannot concede a home run** (margin 2) while one playing an **8 can**.

---

## 4. Baserunning

**SPEED is how many bases that player runs.** A runner's CURRENT speed is
readable off the shield badge on their base, and it is a LIVE number, not the
card's roster `secondary` — the same named card shows different values at
different moments.

**Runners can be lapped**: this game lets base runners pass each other, so
real-baseball intuitions about ordering are unsafe. They cannot share a base.

**FIELDING SUBTRACTS RUNNER MOVEMENT, BY THE NUMBER SPECIFIED.** A runner
advances (its SPEED minus the pitcher's total FIELDING) bases, floored at zero.
Total fielding is the pitcher card's own `secondary` plus any Fielding Play
bonus attached. *From the user, 2026-09-16.*

**BOTH MEASUREMENTS FIT IT EXACTLY**, two outs differing only in the boost:

    our 8/0 + FIELDING PLAY +1  ->  fielding 1   runner speed 1 - 1 = 0   did NOT move
    our 9/0, no tactics         ->  fielding 0   runner speed 1 - 0 = 1   moved 1 base

It is why fielding only matters with runners on base, and why the engine holds
the boost back until there are some.

### Timing, measured 2026-09-16

The first baserunning timings this project has taken, from 60 fps sampling of
the diamond across two plays.

    per base            mean 0.98s   median 1.02s   n=8 legs   sd 0.23s
    the animation is    STRICTLY SEQUENTIAL -- each runner completes its whole
                        journey before the next one starts

A bases-loaded home run, all four scoring:

    run 1   4.63s   from third    (1 base)
    run 2   6.58s   from second   (2 bases)
    run 3   9.86s   from first    (3 bases)
    run 4  14.37s   from home     (4 bases)
    bases fully clear at 16.65s

So a post-play wait is the SUM of the runners' journeys, not the longest one,
and **~16.7 s is the ceiling** the game can produce.

---

## 5. Where things are on screen

    the scoreboard      top left: two score rows, then ROUND pips, then DISCARDS pips
    the diamond         centre: third at LEFT, second at TOP, first at RIGHT
    the hand            a five-card fan along the bottom
    the reveal          the PITCHER's card at the MOUND, the BATTER's at HOME PLATE
                        -- fixed by ROLE, not by owner, so they swap with the phase

**The big round coin bottom-left of the WORLD hud is HEALTH, not money.** Money
is readable only on the pause menu. This has been misread three times.

**The reveal prints its own outcome**: PLAY BALL! as it opens, then HOME RUN!
when one happens.

---

## 6. What the engine does with all this

- **The score never changes which card to play.** You bat once and then defend a
  fixed total, so you can never want fewer runs while batting and can only want
  outs while pitching. Max power both ways.
- Attach a swing boost while batting; hold a fielding boost until runners are
  actually on base, since it does nothing otherwise.
- **The 79% win rate behind "always attach a swing boost" was measured in a
  simulator where a speed boost does nothing by construction.** It shows swing
  beats NOTHING; it has never compared swing against speed.
