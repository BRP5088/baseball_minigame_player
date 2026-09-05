"""The human-walked demo route, recovered from the demo3 screen recording.

WHAT THIS IS
------------
`DEMO_ROUTE` is the walk from the office save-typewriter to the Baseball Cards
table, expressed the way a closed-loop replay wants it:

    (absolute_bearing_degrees, seconds_of_ACTUAL_MOVEMENT, checkpoint_or_None)

A replay does `compass.turn_to(bearing)` and then holds forward for
`moving_seconds`. The turns are NOT in this list on purpose: turning is
closed-loop against the compass, so the wall-clock the human spent turning is
not a thing worth reproducing. What must be reproduced is DISTANCE, and
distance is bearing x seconds-actually-moving.

SOURCE
------
scratchpad/demo3/, 378 frames `f_SECONDS.jpg`, 1400x904, fullscreen capture.
NOTE: the capture is ~5.9 fps (median frame interval 0.17s, range 0.12-0.43s),
not the 8 fps it was described as. Every duration below is integrated from the
real filename timestamps, never from a frame count x a nominal 1/8s.

HOW MOVING TIME WAS SEPARATED FROM ELAPSED TIME
-----------------------------------------------
The human was asked to walk slowly and pause between legs, so elapsed time
between landmarks overstates the walking badly: 67.61s elapsed, 20.15s of it
standing still.

Frame-to-frame difference over the world region (rows 22-80%, cols 10-90% of
the frame, which excludes the compass bar and the bottom HUD), as mean absolute
grey-level difference (MAD).

  A RAW MAD THRESHOLD DOES NOT WORK HERE, and this was measured, not assumed.
  This game is dark, low-contrast and flat-shaded. Walking down the dim office
  hallway toward a plain door (t=20-22) produced MAD 3.6-5.7 -- LOWER than the
  1.7-5.2 the same metric shows while standing perfectly still at the table at
  the end. A raw threshold puts a real walking leg on the wrong side.

  So the metric is normalised by scene texture:

      disp_rate = MAD(prev, cur) / mean|spatial gradient| / dt

  which is roughly "apparent pixels of displacement per second" and is
  comparable between a bright street and a dark corridor.

  THRESHOLD = 9.2. Justified by measured separation, not by a percentile:
    * verified-STILL frames  (18s at the end-of-route prompt, plus the pauses
      at 17.93-18.21, 25.13, 26.71-27.37, 33.00-33.19, each confirmed by
      opening the frames): max disp_rate 7.51
    * verified-SLOWEST-MOVING frames (t=20.33-21.88, confirmed by opening
      f_0019.98 and f_0021.75 -- the character visibly closes on the hallway
      door): min disp_rate 11.29
  Separation 7.51 -> 11.29, a 1.5x gap with nothing in it. 9.2 is the geometric
  midpoint, so ~1.22x margin on each side.

CAPTURE STALLS
--------------
8 single frames (1.50, 1.97, 3.97, 6.95, 7.44, 41.90, 46.53, 47.54) sit below
threshold in the middle of obvious motion. They are capture stalls, not pauses:
the frame is near-identical to its predecessor while the NEXT frame is far from
both (e.g. t=47.54: mad(prev,cur)=2.6 but mad(cur,next)=27.4). A real pause has
all three distances small (t=18.08: 0.46 / 2.00 / 1.99). The 8 stalls are
counted as moving; the game kept rendering, the capture missed it.

BEARINGS
--------
`compass.read_bearing` on all 378 frames. It was clean on this recording:
  * 0 single-frame jumps anywhere near 90/180/270 -- no labelling shift
  * only 3 frames returned None (11.95, 24.85, 33.77), interpolated
  * largest single-frame change 12.6 deg, during a genuine fast turn
  * independent geometric cross-check: on turning stretches, the horizontal
    image shift that best explains consecutive frames scales with the bearing
    change at 13-14.5 px/deg, consistently across three separate turns. On
    walking legs no horizontal shift explains anything (residual = raw MAD),
    which is what translation rather than rotation should look like.
Each leg's bearing is the circular mean over its moving frames, weighted by
each frame's dt.

WHAT IS DELIBERATELY NOT IN THE ROUTE
-------------------------------------
t=0.00-10.28 reads as "moving" (disp_rate 12-63) but is NOT a leg. The player
is standing at the save typewriter with the "Typewriter / Save" prompt up,
heading pinned at 87.1 +/- 0.4 deg for 51 straight frames, and the view
oscillates about the typewriter instead of progressing: over that 10.28s the
first and last frames differ by MAD 14.1 while ADJACENT frames differ by ~27.
Endpoints closer together than neighbours is the signature of oscillation, not
travel. Confirmed by eye on f_0000.00 / f_0002.54 / f_0002.69 / f_0005.25 /
f_0010.50: same typewriter, same spot, wobbling. Counting it would have added a
bogus 10.3s leg heading due east into a desk.

CONFIDENCE
----------
  HIGH   legs A, C, D, E -- bearing span <= 1.0 deg across the whole leg
  MEDIUM leg F -- bearing drifts 69.5 -> 75.5 (6 deg)
  LOW    leg B -- bearing drifts 11.0 -> 357.7 (14 deg), see BEARING_UNCERTAIN

THE BIG CAVEAT, STATED PLAINLY
------------------------------
Of 37.18s of real movement after the typewriter, only 19.39s was walking on a
steady heading. The other 17.79s the heading was changing while the character
was moving -- the human walked round corners rather than stopping, turning and
setting off again. A turn-then-walk replay does not reproduce that curved
distance and WILL fall short, most likely at the 313->67 deg turn (t=42.80-
46.13), the one turn where a pure rotation clearly does not explain the frames.
The two landmark checkpoints exist to catch exactly that.
"""

# Each leg: (bearing_degrees, moving_seconds, checkpoint_or_None)
DEMO_ROUTE = [
    (272.2, 2.68, None),                 # A office hallway, west to the door
    (2.5,   6.99, "sees_lb_building"),   # B through the door, north onto the street
    (357.9, 4.25, None),                 # C across the street, through the archway
    (329.3, 0.94, None),                 # D inside L&B, past the bar
    (313.3, 1.08, None),                 # E deeper into the bar room
    (74.0,  3.45, "at_baseball_table"),  # F east to the Baseball Cards table
]

# Heading the character holds at spawn, standing at the save typewriter.
# Circular mean of 51 frames t=0.00-9.55; observed range 86.82-87.55.
SPAWN_BEARING = 87.1

# Legs whose bearing wandered while walking: the human was still turning. A
# replay that holds one fixed heading for these will drift laterally.
# leg index -> (first_bearing, last_bearing, total_span_degrees)
BEARING_UNCERTAIN = {
    1: (11.0, 357.7, 14.0),   # leg B, still settling out of the preceding 97 deg turn
    5: (69.5, 75.5, 6.0),     # leg F, final approach curves onto the table
}

# Where each leg came from in the recording, for auditing (t_start, t_end).
# t_end - t_start is WALL CLOCK and is always >= the leg's moving_seconds,
# because pauses inside the window are excluded from moving_seconds.
LEG_WINDOWS = [
    (18.21, 20.89),
    (25.13, 32.81),
    (33.35, 37.85),
    (40.02, 40.96),
    (41.72, 42.80),
    (46.13, 49.58),
]

# Measured totals for the whole recording (seconds).
TOTAL_ELAPSED = 67.61
TOTAL_MOVING = 47.46          # every stretch above threshold, typewriter included
TOTAL_STATIONARY = 20.15      # TOTAL_ELAPSED - TOTAL_MOVING
TYPEWRITER_OSCILLATION = 10.28  # excluded from the route, see docstring
TOTAL_TURNING = 17.79         # moving, but heading was changing
TOTAL_WALKING = 19.39         # == sum of DEMO_ROUTE moving_seconds

# Motion segmentation constants, kept here so the test can re-assert them.
MOVE_THRESHOLD = 9.2          # normalised disp_rate, px/s
STILL_MAX_OBSERVED = 7.51     # highest disp_rate on a verified-still frame
MOVE_MIN_OBSERVED = 11.29     # lowest disp_rate on a verified-moving frame

# Landmark first-appearance times, from landmarks.py over all 378 frames.
# NOTE ON THE L&B CHECKPOINT: sees_lb_building is confirm-only (True or None)
# and fires on only 15 of the ~35 frames between 31.88 and 36.72 -- including
# NOT at t=32.81, where leg B ends. It must be POLLED DURING legs B and C, not
# asserted once at a leg boundary. at_baseball_table is the reliable one: it
# goes True at 49.10 and stays True for all 102 remaining frames, so it does
# assert cleanly at the end of leg F.
LANDMARK_FIRST_SEEN = {
    "sees_lb_building": 31.88,   # last confirmed 36.72
    "at_baseball_table": 49.10,  # continuous to end of recording
}
