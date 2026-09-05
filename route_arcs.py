"""The demo3 walk as ARCS — turning while moving, the way it was performed.

Each entry is (heading_at_start, heading_at_end, seconds). Segments where the
demo was standing still are omitted; they carry no displacement.

Derived from the demo3 timeline by pairing decoded heading with frame-to-frame
picture change, so every arc below covers a stretch where the character was
demonstrably TRAVELLING, not just turning on the spot.
"""

ARCS = [
    (87.0, 92.0, 10.5, "east away from the typewriter desk"),
    (92.0, 232.0, 5.5, "the long curve right, around the desk"),
    (232.0, 263.0, 1.0, "settling onto west"),
    (263.0, 272.0, 1.4, "west along the corridor"),
    (272.0, 354.0, 2.1, "curving right toward the stairs"),
    (354.0, 14.0, 0.3, "lined up on the stairs"),
    (6.5, 3.0, 1.7, "DOWN THE STAIRS"),
    (3.0, 357.0, 2.3, "off the stairs, out toward the street"),
    (357.0, 358.0, 3.3, "across the street into L&B"),
    (358.0, 354.0, 2.0, "inside, bearing left"),
    (354.0, 329.0, 2.0, "further left"),
    (329.0, 313.0, 1.8, "deepest point inside L&B"),
    (313.0, 2.0, 0.9, "sharp right"),
    (2.0, 21.0, 0.8, "continuing right"),
    (21.0, 56.0, 0.9, "continuing right"),
    (56.0, 75.0, 2.9, "ARRIVE at the card table"),
]

ARRIVED_HEADING = 74.9

# NEVER press this at the prompt. Each match costs $50 and the goal is to
# ARRIVE. Standing at the prompt is free.
DO_NOT_PRESS = "box"
