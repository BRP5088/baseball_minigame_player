# A WINNING AT-BAT THAT ADVANCED NOBODY (2026-09-17)

    ours   Donny Mekesz 5/3 + POWER SWING +1 = 6
    theirs 5, no tactics card
    margin +1 -- a HIT by the game's own rule

And nothing moved. `local_state.read_runners` on this frame:

    first  OCCUPIED, power 8, speed 1   <- Rube Sharp, unchanged from the turn before
    second empty      third empty       count 1, score 2-0

The batter is on HOME PLATE, his card overlapping the hand fan. Two players
cannot occupy the same base, so with the runner pinned by the pitcher's FIELDING
the batter had nowhere to go.

`blocked_hit_2026-09-17.png` is the full 1920x1080 frame; `diamond_crop.png` is
the diamond and hand, where both the stranded batter and the covered hand slot
are visible at once.

TWO THINGS THIS FRAME PINS, and both are in RULES.md:

  * a hit can produce ZERO base-movements -- the shortest animation the game has,
    against ten for a home run with the bases loaded
  * the played card on home plate OCCLUDES the hand slot beneath it. A STRANDED
    BATTER IS A PERSISTENT DISPLAY: watched 18s with no input, the card stayed and
    the slot stayed unreadable in 10 of 10 samples. An earlier line here called it
    transient; that was reasoned, not observed.
