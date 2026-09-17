# THE CURSOR CANNOT BE READ ON THIS HAND, AND RAISING A CARD HELPS (2026-09-17)

Two frames, the SAME cursor on the SAME slot, differing in one thing: whether
that card is selected. The user performed the deselect; nothing here pressed.

    cursor_slot4_raised.png       slot 4 RAISED       glow[4] = 10.9   cursor -> 4
    cursor_slot4_NOT_raised.png   slot 4 not raised   glow[4] =  7.0   cursor -> None

Ground truth for both, from the user watching the screen: THE CURSOR IS ON SLOT 4.

## The first version of this file had it backwards

It said "a cursor on a RAISED card reads half what the census claims", i.e. that
being raised DEPRESSED the reading. The controlled deselect above shows the
opposite: raising ADDS about 3.9, and without it the cursor falls under
CURSOR_GLOW_MIN and cannot be read at all. That claim was reasoned from one frame
and committed before the control existed (CLAUDE.md 10.32).

## What is actually established

`cursor_slot`'s docstring reports a census over 74 labelled frames:

    the card with the cursor     20.7 .. 36.1
    every other card              0.0 ..  8.4

BOTH readings here are below that floor -- 10.9 and 7.0 -- on a cursor the user
confirms is real. So the depression is a property of THIS HAND, not of the raise,
and the raise merely lifts one of the two readings back over the gate.

**The engine is BLIND on this hand whenever nothing is selected.** Max glow 7.0
against a gate of 10.0, so `cursor_slot` returns None and the selection path
refuses. That is the failure that made a live turn unplayable, and it is not
explained by anything measured yet.

## What is NOT established, and must not be guessed again

WHY this hand reads low. A batter is STRANDED ON HOME PLATE in both frames (see
test_fixtures/blocked_runner/) and his card lies across the fan, covering slot 2
entirely -- but slot 4 is nowhere near him, and slot 4 is the one that fails. Three
explanations were offered during the session and all three were wrong; the fourth
is not offered here.

What would settle it: the same before/after pair on a hand with NO stranded batter.
If the cursor reads 20+ there, the stranded card is implicated; if it reads ~7, the
census band is simply not general and the gate is doing all the work.
