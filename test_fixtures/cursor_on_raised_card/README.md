# A CURSOR ON A *RAISED* CARD READS HALF WHAT THE CENSUS SAYS (2026-09-17)

`cursor_slot4_raised.png` — full 1920x1080 frame, live, mid-match.

GROUND TRUTH, from the user watching the screen:

    the cursor is on SLOT 4
    slot 4 is RAISED (selected)

WHAT THE READER SAYS (reader_says.json, taken from this exact frame):

    glow        [0.1, 0.1, 3.1, 0.0, 10.9]
    selected    [4]
    cursor_slot 4          <- CORRECT

WHY IT MATTERS. `local_hand.cursor_slot`'s docstring reports a census over 74
labelled frames:

    the card with the cursor     20.7 .. 36.1
    every other card              0.0 ..  8.4    (selected but not hovered: <= 5.7)

This frame's cursor reads **10.9** -- less than half that lower bound, and only
0.9 above CURSOR_GLOW_MIN. It is a true cursor by ground truth, so the 20.7 floor
does not describe every cursor: those 74 frames appear to contain none where the
cursor sits on a card that is ALSO SELECTED. The band is stated in the docstring
as if it were the whole population (CLAUDE.md 10.31).

`CURSOR_GLOW_MIN = 10.0` is what makes this frame work, and its own derivation
cites "8.4 (fixture false MAX) and 12.4 (live true)" -- a live true of 12.4 is in
the same low band as this 10.9, so the gate was very likely fitted against exactly
this case even though the census beside it suggests a much higher floor.

THE HEADROOM IS 0.9, WHICH IS THE POINT. Do not raise the gate toward the census
band without frames like this one in the sample: it would reject a real cursor on
every selected card, and the selection path REFUSES when the cursor cannot be
read -- which is how a live turn came to be unplayable twice this evening.

THE REST OF THE STATE, for anyone re-scoring this frame: a batter is STRANDED ON
HOME PLATE (see test_fixtures/blocked_runner/) and his card covers slot 2's glow
window, which reads 3.1 here. Slot 2 is genuinely unreadable; slot 4 is not.
