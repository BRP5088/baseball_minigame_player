# THE RUNNER ON HOME PLATE IS COUNTED AS A SIXTH CARD IN THE HAND (2026-09-17)

The user's diagnosis, confirmed by measurement and visible in `_phantom_blowup.png`:
Donny Mekesz's card, STRANDED ON HOME PLATE, sits inside the hand crop carrying its
own BATTER banner, power disc (5) and shield (3). `local_hand.read_hand` finds
those discs and counts it as a hand card.

    row counts over 76 live frames of this state
        5 rows : 60      (79%)
        6 rows : 15
        7 rows :  1      (21% wrong)

    the phantom sits at hand-crop x = 453, between slot 1 (383) and slot 2 (548)
    blanking x 430-480 gives 76/76 five-row reads, with IDENTICAL digits

## Why it disables the whole input layer

`_look_settled` requires EXACTLY five rows, so a fifth of every read is rejected;
when LOOK_RETRIES runs out it hands the bad read back anyway. Everything else
follows from the shifted indices:

    "lost the cursor after 1 press"        a 6-row read, indices shifted
    "select_card did not land" x5          the lift was there, the row was not
    "select_card raised [4], expected 0"   a shift looked like a new card going up
    slot 2's y swinging 68 <-> 207         two objects under one row index
    selection flickering every ~2s         21% of frames read six rows

It is why a live $50 turn could not be played, and why FOUR separate explanations
offered during the session -- selection dims the halo, raising halves it, the card
covers the glow box, the gate is mis-set -- were all wrong. None of them was about
the row count, and there was never a stable reading to explain.

## THE FIX IS NOT BUILT, AND THIS SAYS WHY

The user's design is the right one and is recorded here rather than guessed at
later: when a runner is on HOME PLATE, disable slot 2's box and mark it
`homeplate_runner`, so the pipeline knows the slot is unresolvable. The label is
the important half -- CLAUDE.md 10.34 says discarding an occluder REVEALS the card
beneath, and that is true only when the occluder is a HAND card. A home-plate
runner is not, so a discard can never resolve it, and without the label the engine
would spend its last discard trying.

A candidate detector exists: `base_discs` over a home-plate box of
(0.43, 0.60, 0.56, 0.78) finds exactly one disc, on 20 of 20 of these frames.

**IT IS NOT VALIDATED AND MUST NOT SHIP UNTIL IT IS.** There is no negative
population on disk: the 15,832 archived frames in `screenshot_log/` are 2000x1292
(aspect 1.548), a geometry production never produces and one CLAUDE.md records as
breaking fractional readers outright. So the FALSE POSITIVE rate -- the only number
that matters, because a detector that fires on a normal hand would suppress slot 2
in every match -- is unknown. `at_table` is the precedent: a 500-frame sample said
zero and the 701st frame fired.

What would validate it: normal turn frames at 1920x1080, with no runner on home
plate, captured during an ordinary match. Nothing else on disk can do it.
