"""Route to the Baseball Cards table, from the recording of 2026-08-27 21:25.

Source: demos/spawn_to_table_20260827_212516 (539 frames, 90s, 6fps).
Heading decoded per frame; travelling-vs-standing from frame-to-frame picture
change. Only segments where the character was TRAVELLING appear below.

The walk takes ~48s. From 48.3s the recording is motionless at 87.4 degrees for
the remaining 39s — that stillness IS the arrival, and 87.4 is the heading to
end on.

EACH ARC IS FOLLOWED BY A CORRECTIVE turn_to.
The previous attempt chained sixteen arcs open-loop, never re-reading the
compass. A single arc calibrated to within 0.5 degrees, but the errors
compounded: by the ninth the heading was 15 degrees off a target it should have
hit exactly, and the character was walking somewhere else entirely while the
script reported progress. Re-reading between arcs is not optional.
"""

# (heading_at_start, heading_at_end, seconds, note)
ARCS = [
    (87.0, 270.9, 6.86, "the long curve east-then-west around the desk"),
    (270.9, 270.9, 1.34, "straight west along the corridor"),
    (300.4, 353.4, 1.18, "curving right toward the stairs"),
    (355.7, 1.9, 0.50, "lined up"),
    (1.9, 1.9, 2.17, "north — the stairs"),
    (1.9, 358.7, 2.67, "off the stairs"),
    (358.7, 358.7, 4.01, "across the street toward L&B"),
    (356.6, 297.5, 2.51, "into L&B, bearing left"),
    (297.8, 297.3, 1.50, "through the interior"),
    (297.9, 0.9, 2.34, "curving right"),
    (11.2, 87.0, 5.18, "the long curve right toward the table"),
    (87.2, 87.4, 2.01, "final approach"),
]

ARRIVED_HEADING = 87.4

# NEVER press this at the prompt. Each match costs $50 of in-game money, and
# the goal is to ARRIVE. Standing at the prompt is free.
DO_NOT_PRESS = "box"
