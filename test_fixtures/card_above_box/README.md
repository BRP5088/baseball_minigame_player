# THE GLOW BOX IS BOUNDED HORIZONTALLY AND NOT VERTICALLY (2026-09-17)

Three frames from one 10 Hz burst in `run_20260828_140236`, kept because
`screenshot_log` is pruned oldest-first (`SCREENSHOT_KEEP_RUNS = 3`) and this is
the only recorded instance of the state.

    unsettled_card_above_28.jpg   cursor_slot -> 4   glow [0.0, 0.4, 0.0, 0.0, 28.2]
    unsettled_card_above_21.jpg   cursor_slot -> 4   glow [0.0, 0.4, 0.0, 0.0, 21.0]
    unsettled_same_burst_04.jpg   cursor_slot -> None glow [0.0, 0.2, 0.0, 0.0,  0.4]

## What IS established

`cursor_glow` bounds each card's window **horizontally** -- a card owns the band
between the midpoints to its neighbours, so the box can never sample the card
BESIDE it, and that bound's own comment records the live failure it prevents.
**Nothing bounds it vertically.** On these frames the fan is mid-play and the
rows the box samples for slot 4 sit inside another card.

Measured by walking up from the disc to the first sustained dark backdrop:

    slot 4, these frames                 122 .. 132 px above the disc
    a settled fan's own exposed rim       43 ..  59 px

## What is NOT established -- do not "fix" this on the strength of the above

The burst is a cursor MOVE during a card being played, not a dead hand:

    slot 3  16.6, 16.6, 34.9      then its disc->backdrop falls to 1: card PLAYED
    slot 4  28.2, 21.0, 6.0, 0.4  <- these frames
    slot 1  28.6 and steady for twelve frames

So the 28.2 may be a genuine cursor on slot 4 mid-animation rather than the box
reading a neighbour. **Nothing here distinguishes them.**

And the obvious instrument does not: taking slot 1 above, where the cursor is
unambiguous for twelve consecutive frames,

    slot 1 while NOT the cursor    disc -> backdrop  37-38
    slot 1 while IS  the cursor    disc -> backdrop  49-50

**the measurement rises WITH the halo**, because the halo is bright and pushes
the first dark row up. It is not independent of what it would be policing, and a
gate at 80 would zero a plausibly-genuine reading of 142 at slot 3 mid-play --
blinding the reader exactly when a card is being played, on the $50 path.

## Why it was not settled with more data

The whole archive yields **4,183 five-row turn frames, of which 4,142 are this one
run**. At 10 Hz that is a handful of independent moments, not a population
(CLAUDE.md 10.8). Fitting a gate to it would be fitting to one match.

The independent label that would settle it exists and is cheap: a card that RISES
above its fan anchor was selected, and selecting requires the cursor to be on it,
so the frame before a slot newly rises has a known cursor slot -- geometry, not
brightness, and therefore not circular (10.22). See
`agent_progress/card-location/progress.md`.
