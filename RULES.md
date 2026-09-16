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

### Tactics cards

    POWER SWING     +1 60%   +2 40%      the ONLY card ever above +1
    SPEED BOOST     +1 100%
    PITCH FOCUS     +1 100%
    FIELDING PLAY   +1 100%

*Measured over 299 hand-labelled tactics cards.* **A +3 does not exist.** Any
record showing one is a misread.

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

**A hit needs the batter's power to beat the pitcher's.** Margin does not
otherwise matter — except:

**Beating it by 3 or more is an automatic HOME RUN**, which clears every runner
on base plus the batter. *The rule is absolute*, confirmed by the user against
the live scoreboard and **measured 2026-09-16**: our 9 (7 + POWER SWING +2)
against their 6 (5 + PITCH FOCUS +1) is a margin of exactly 3, and the screen
printed HOME RUN! for 4 runs with the bases loaded.

**A TIE is a COIN FLIP, and winning one is capped at FIRST BASE** regardless of
the batter's speed. *Confirmed by the user, 2026-09-16*, and it explains an
at-bat the same day: our 9 against a 9, the batter stopped at first, and the
runners on second and third did not move at all.

**A losing at-bat can still advance runners.** An out is not "nothing happens".

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

**BLACK PITCHER BUFFS SUBTRACT RUNNER MOVEMENT** — that is what FIELDING does,
and it is why fielding only matters with runners on base.

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
