"""Route to the Baseball Cards table, recovered from a recorded human walk.

SOURCE: demo3 — 379 frames over 67.6s of a person walking spawn -> table.
Heading came from decoding the compass in every frame; MOVEMENT came from the
frame-to-frame picture change, which is what separates "walking on this
heading" from "standing still facing it".

WHY BOTH SIGNALS ARE NEEDED
---------------------------
An earlier attempt used heading alone and read the segments as walk legs. The
first segment held ~87 degrees for eleven seconds, but that was WALKING EAST —
and a route built from headings-where-they-changed instead started by walking
262 (west) and drove into a wall on leg one. Every later leg then began from
the wrong place. Heading says where you face; only motion says whether you
went anywhere.

THE WALK, as actually performed (heading, seconds, what happens):
"""

# (heading, seconds, note) — only segments where the picture was CHANGING,
# i.e. the character was actually travelling.
LEGS = [
    (88.0, 10.9, "east away from the typewriter desk"),
    (139.0, 1.2, "curving right"),
    (203.0, 1.5, "still curving"),
    (231.8, 1.0, "still curving"),
    (262.8, 1.0, "now heading west"),
    (271.3, 1.4, "west along the corridor (a pause at 17.9-18.2s)"),
    (322.2, 1.0, "turning toward the stairs"),
    (354.3, 0.8, "lining up on the stairs"),
    (3.0, 1.7, "DOWN THE STAIRS"),
    (359.0, 2.3, "off the stairs, out toward the street"),
    (358.0, 3.5, "across to L&B and in through the doorway"),
    (351.0, 1.9, "inside, bearing left"),
    (342.0, 0.9, "further left"),
    (329.3, 1.1, "further left"),
    (313.3, 1.8, "deepest point inside L&B"),
    (2.3, 0.9, "sharp right"),
    (21.5, 0.8, "continuing right"),
    (55.6, 0.9, "continuing right"),
    (74.0, 2.9, "ARRIVE: 'Baseball Cards / Play ($50)' prompt"),
]

# From 49.7s onward the demo is STILL at ~75 degrees — standing at the table.
# That stillness is how the arrival is recognised.
ARRIVED_HEADING = 74.9

# NEVER press this at the prompt. Each match costs $50 of in-game money and the
# goal is to ARRIVE. Standing at the prompt is free.
DO_NOT_PRESS = "box"
