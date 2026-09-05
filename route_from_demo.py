"""The route to the Baseball Cards table, recovered from recorded demos.

WHERE THIS CAME FROM
--------------------
Not from exploration — from test_fixtures/landmarks/, which holds frames from
THREE human-driven demo walks (demo, demo2, demo3), each filename naming the
landmark and the frame number it was captured at. Decoding the compass out of
each frame gives an ordered sequence of headings, which is the route.

This existed the whole time I was guessing at bearings. Check the fixtures
before exploring.

DEMO 3 — the most complete run, bearings decoded 2026-08-27:

    frame  landmark            bearing
     1028  typewriter (spawn)     90.6
     2013  corridor              272.1
     2899  stairs                  3.2
     3209  L&B exterior          357.7
     3483  L&B exterior          357.4
     3608  L&B exterior          357.9
     3685  L&B exterior          357.9
     3965  L&B interior          335.6
     4300  L&B interior          313.5
     4689  dining room            71.6
     4941  TABLE                  74.9   <- "Baseball Cards / Play ($50)"
     5513  TABLE                  75.1
     6761  TABLE                  75.1

CONFIRMED BY THE OTHER TWO DEMOS, which is what makes these trustworthy rather
than one person's single run:

    landmark        demo    demo2   demo3
    typewriter      95.5    95.9     90.6
    stairs          13.8      -       3.2
    L&B exterior     8.3      6.6   357.7
    L&B interior     4.1      5.7   335.6
    dining room     55.3     89.4    71.6
    table           93.6     90.0    75.1

The spread is real and matters: the table was approached facing 75 in one demo
and 93 in another, so these are not a single canonical path. What IS consistent
is the ORDER of landmarks and the rough heading family at each — that is the
part to steer by, confirming each landmark by sight before moving on.
"""

# (landmark, demo3 bearing, what you should see when you are there)
SEQUENCE = [
    ("typewriter", 90.6, "the typewriter and its 'Typewriter / Save' prompt"),
    ("corridor", 272.1, "a corridor out of the office"),
    ("stairs", 3.2, "a staircase with banisters, descending"),
    ("lb_exterior", 357.7, "the LITTLE & BIG facade and the L&B doorway"),
    ("lb_interior", 335.6, "inside L&B: portraits, rug"),
    ("lb_interior_2", 313.5, "further in"),
    ("dining_room", 71.6, "a dining room"),
    ("table", 74.9, "'Baseball Cards / Play ($50)' prompt at the card table"),
]

# NEVER press the prompt. Each match costs $50 of in-game money and the goal is
# to ARRIVE, not to play. Reaching the prompt is free.
DO_NOT_PRESS = "box"

FIXTURES = "test_fixtures/landmarks"
