# Post-match analysis — 28 Aug

## What happened

One match was bought and played to ~51 cards, leading 1-0, before it ended. Two
things ended it, both mine:

* I pressed CIRCLE four times to back out of a stuck ban screen. That opened a
  "Give up?" dialog, and a later press confirmed it.
* The console then dropped off the network entirely
  (`Discovery failed to send: Can't assign requested address`), leaving chiaki
  displaying a frozen frame. Not recoverable from this side.

**No match completed, so there is no win/loss to analyse.** What follows is what
the 51 cards revealed about the machinery, which is where the improvements are.

## The finding that matters most: nothing was being learned

`match_log.jsonl` began the session at 72 rows and ended at 72. Every turn
failed with "reveal cards never appeared" — 23+ of them. An entire match of play
produced zero data.

Measured rather than guessed: over 2445 frames of that match, the centre-edge
signal reads **0.0435 with no cards** and peaks at **0.1456 with them**, so the
0.065 trigger separates them cleanly and fired on 45 frames. The detector was
never wrong.

`wait_for_reveal_cards` waited **6 seconds**. The post-play notes twenty lines
below that function record the game taking **~17 seconds** to finish dealing.
The window closed before the cards arrived. Now 20s.

This is the single highest-value fix of the session: without it, no amount of
play produces anything to learn from.

## The discard bug (spotted by the user, not by the logs)

Reported live: "made a bad discard choice. threw away a power+2 when there was a
card with batter of 4". The log said it discarded a power-4 player.

Both are true. The engine CHOOSES the weakest player card, but
`_move_cursor_to` navigates from a REMEMBERED cursor position, and a dropped
keypress puts it one slot off — so a different card is thrown than the one
chosen. The log records the intent; the screen shows the result.

The ban scanner already learned this exact lesson and states it plainly: *"the
press count cannot see a dropped keystroke"*. Discards now home the cursor first
(`reset_hand_cursor(force=True)`), which is the cheap version of trusting a
measurement over a count.

## Cost

90 API calls for ~51 cards played — about **1.8 calls per card, $1.08** for a
partial match. A full match is $2-3. Two things inflate it:

* **Rejected reads cost a call each.** Vision read a `Fielding Play` tactics
  card as a player with power 1 (valid range is 4-9), and read `discards_left`
  as 5 when the cap is 2. Each rejection is a retry.
* **Every turn pays**, even though the local reader agrees on the numbers that
  matter. The `compare_local_reads` output shows local OCR matching vision on
  POWER almost always, and disagreeing mainly on the SECONDARY stat. If power is
  what decides a hit, most turns may not need vision at all.

## Model choice, tested rather than assumed

Haiku was measured against Sonnet on real frames.

**Card reading** — Haiku is 1.6x faster and unusable: it misread one card three
different ways across three frames ("BRANDON \"BINGER\" ORTIZ" became ANDON
PINGO / ANDON BINGO / ANDON DINO), and got a POWER value wrong (8 vs 9), which
is the number that decides a hit.

**Screen classification** — tested against a labelled set. Sonnet 6/8, Haiku
4/8, and Haiku was not faster on this call (5.1s vs 4.5s) because it sends
multiple crops rather than one image. Haiku errored on both
`match_start_prompt` frames.

Recommendation: keep Sonnet for both. Caveat: the two `turn` frames in the
labelled set are watermarked stock images with different framing and BOTH models
failed them, so that part of the score reflects the test set, not the models.

## What was working

* **Input is reliable.** 51 cards played, **0 suspected misfires (0.0%)**.
* **The ban scrollbar reads correctly now** — 438/479 frames resolve to a level,
  9% refused as mid-animation, against an original expectation of ~17%.
* The route reaches the table and the match starts.

## Ranked next steps

1. **Confirm turns log** with the 20s reveal window. Everything else depends on
   having data.
2. **Cut the API bill** by trusting local reads where they agree with vision.
   The comparison data to justify it is already being logged every turn.
3. **Fix the two read rejections** — a tactics card should never be validated as
   a player, and `discards_left` misreads are costing retries.
4. Only then tune the play itself. Tuning strategy before the log works would be
   tuning against nothing.
