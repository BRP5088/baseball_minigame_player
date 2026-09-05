"""The demo walk as a DENSE trajectory: every second of real movement.

WHY THIS EXISTS ALONGSIDE route_data.py
---------------------------------------
route_data.DEMO_ROUTE is the turn-then-walk decomposition: 6 straight legs,
19.39s. It throws away the 17.79s during which the heading was changing while
the character was moving, because a turn-then-walk replay cannot reproduce a
curve.

This module keeps all of it. DENSE_ROUTE is the whole 37.18s of real movement
as a sequence of short constant-bearing segments, so a replay that can walk in
any direction independent of camera facing can trace the actual curved path.

    DENSE_ROUTE = [(bearing_degrees, seconds), ...]

Walk at each bearing for its duration, in order. Total is exactly 37.18s.

SOURCE AND METHOD
-----------------
Same recording and same segmentation as route_data.py -- see that module's
docstring for the texture-normalised motion metric, the measured 9.2 threshold
(verified-still max 7.51 vs verified-moving min 11.29), and the capture-stall
repair. Nothing about the moving/stationary split changed here; only the way
the moving frames are grouped.

Grouping rule: walk the moving frames in time order and start a new segment
whenever the frame's bearing departs from the running segment mean by more
than 4.0 degrees, or whenever a stationary pause breaks contiguity. Steady
stretches therefore collapse into one long entry (max 4.35s) and sweeping
stretches fall to one entry per captured frame (min 0.13s), which is as fine
as the ~5.9fps capture allows. 75 entries, median 0.22s.

Pauses are NOT in this list -- they are movement of zero distance. They are
recorded in PAUSES if the timing is wanted.

THE BEARINGS ARE MOVEMENT BEARINGS, AND THAT WAS CHECKED
--------------------------------------------------------
compass.read_bearing returns where the CAMERA points, which is only the
direction of travel if the human walked forward rather than strafing. Since
you can now decouple the two, this mattered enough to test.

For every steady-heading segment, the best-fit horizontal image shift between
consecutive frames was measured. A forward walk produces radial flow that no
horizontal shift explains; a strafe produces exactly such a shift. Result: 7 of
the 8 steady-heading segments give a best shift of 0.0 px and 0 percent
explained. The eighth (t=26.14-26.53) gives -9 px, but that segment is itself
rotating at -2.2 deg/s, which predicts -0.86 deg x 13.5 px/deg = -11.6 px on
its own.

So: no strafing anywhere in the recording. Camera heading == direction of
travel throughout, and DENSE_ROUTE bearings can be used directly as movement
bearings.

THE 313->67 CURVE AT t=42.80-46.13 -- WHAT IS ACTUALLY THERE
------------------------------------------------------------
You asked for this one specifically. It is a genuine curved walk, and it is the
most translation-heavy stretch in the recording.

Measuring how much of each frame-to-frame change a pure horizontal shift
explains (call it ROT, high = pivoting in place, low = translating):

    this curve, t=42.80-46.13 ......... median ROT  16 percent
    opening about-face, t=10.28-17.70 . median ROT  50 percent

Half the opening about-face is explained by pure rotation; only a sixth of this
one is. The character was walking hard the whole way round. Three sub-phases:

    43.15-44.24   sweeps 313->12 deg fast (37-65 deg/s), ROT 15-62
    44.42-45.66   drifts 12.7->33.8 deg slowly (2-24 deg/s), ROT 0-21
                  -- t=44.42 and t=44.57 are ROT 0 at ~2.5 deg/s: those two
                     frames are almost pure forward walking mid-curve
    45.80-46.13   sweeps 43->67 deg fast (65-74 deg/s), ROT 2-29
                  -- the tightest part; turning hardest AND still translating

It is 12 segments here, the shortest 0.14s, so the curvature is carried at full
capture resolution. This is the stretch most likely to expose any error in the
replay, and the one where a turn-then-walk approximation loses the most ground.

CONFIDENCE
----------
Bearings: compass was clean on this recording -- zero labelling shifts, 3 None
frames out of 378 (interpolated), largest single-frame change 12.6 deg during a
genuine fast turn. Independent geometric check: on turning stretches the
best-fit horizontal shift scales with bearing change at 13-14.5 px/deg.

Durations: integrated from real filename timestamps. The capture is ~5.9fps
(median interval 0.17s, range 0.12-0.43s), NOT the 8fps it was described as.

The excluded t=0.00-10.28 typewriter oscillation is not here, same as in
route_data -- heading pinned at 87.1 +/- 0.4 for 51 frames while the view
oscillates about the typewriter with no net progress (endpoints differ by MAD
14.1, adjacent frames by ~27).
"""

# (bearing_degrees, seconds) -- walk each bearing for its duration, in order.
DENSE_ROUTE = [
    (  93.4, 0.470),   #  0  t= 10.28- 10.75
    ( 100.4, 0.330),   #  1  t= 10.75- 11.08
    ( 108.6, 0.500),   #  2  t= 11.08- 11.58
    ( 117.4, 0.370),   #  3  t= 11.58- 11.95
    ( 123.2, 0.180),   #  4  t= 11.95- 12.13
    ( 131.8, 0.290),   #  5  t= 12.13- 12.42
    ( 139.4, 0.280),   #  6  t= 12.42- 12.70
    ( 143.9, 0.260),   #  7  t= 12.70- 12.96
    ( 149.4, 0.190),   #  8  t= 12.96- 13.15
    ( 156.1, 0.360),   #  9  t= 13.15- 13.51
    ( 163.9, 0.220),   # 10  t= 13.51- 13.73
    ( 169.0, 0.180),   # 11  t= 13.73- 13.91
    ( 176.4, 0.220),   # 12  t= 13.91- 14.13
    ( 182.3, 0.190),   # 13  t= 14.13- 14.32
    ( 187.0, 0.200),   # 14  t= 14.32- 14.52
    ( 193.6, 0.240),   # 15  t= 14.52- 14.76
    ( 198.2, 0.160),   # 16  t= 14.76- 14.92
    ( 204.5, 0.300),   # 17  t= 14.92- 15.22
    ( 211.7, 0.140),   # 18  t= 15.22- 15.36
    ( 217.5, 0.160),   # 19  t= 15.36- 15.52
    ( 222.3, 0.220),   # 20  t= 15.52- 15.74
    ( 226.7, 0.150),   # 21  t= 15.74- 15.89
    ( 231.8, 0.170),   # 22  t= 15.89- 16.06
    ( 238.4, 0.180),   # 23  t= 16.06- 16.24
    ( 245.7, 0.320),   # 24  t= 16.24- 16.56
    ( 250.6, 0.160),   # 25  t= 16.56- 16.72
    ( 255.2, 0.150),   # 26  t= 16.72- 16.87
    ( 261.1, 0.330),   # 27  t= 16.87- 17.20
    ( 267.6, 0.300),   # 28  t= 17.20- 17.50
    ( 272.2, 0.200),   # 29  t= 17.50- 17.70
    ( 272.3, 2.880),   # 30  t= 18.21- 21.09
    ( 278.6, 0.660),   # 31  t= 21.09- 21.75
    ( 284.1, 0.290),   # 32  t= 21.75- 22.04
    ( 289.0, 0.150),   # 33  t= 22.04- 22.19
    ( 294.1, 0.190),   # 34  t= 22.19- 22.38
    ( 298.2, 0.160),   # 35  t= 22.38- 22.54
    ( 304.7, 0.160),   # 36  t= 22.54- 22.70
    ( 309.7, 0.160),   # 37  t= 22.70- 22.86
    ( 315.5, 0.130),   # 38  t= 22.86- 22.99
    ( 322.2, 0.200),   # 39  t= 22.99- 23.19
    ( 329.4, 0.350),   # 40  t= 23.19- 23.54
    ( 333.5, 0.150),   # 41  t= 23.54- 23.69
    ( 338.0, 0.140),   # 42  t= 23.69- 23.83
    ( 343.9, 0.170),   # 43  t= 23.83- 24.00
    ( 353.4, 0.500),   # 44  t= 24.00- 24.50
    (   2.1, 0.180),   # 45  t= 24.50- 24.68
    (   6.8, 0.170),   # 46  t= 24.68- 24.85
    (  11.4, 0.150),   # 47  t= 24.85- 25.00
    (   8.8, 1.010),   # 48  t= 25.13- 26.14
    (   4.1, 0.390),   # 49  t= 26.14- 26.53
    (   3.2, 0.150),   # 50  t= 26.89- 27.04
    (   2.3, 4.040),   # 51  t= 27.37- 31.41
    ( 357.7, 1.400),   # 52  t= 31.41- 32.81
    ( 357.8, 0.170),   # 53  t= 33.35- 33.52
    ( 357.8, 4.350),   # 54  t= 33.77- 38.12
    ( 350.7, 0.590),   # 55  t= 38.12- 38.71
    ( 344.4, 0.430),   # 56  t= 38.71- 39.14
    ( 338.1, 0.510),   # 57  t= 39.14- 39.65
    ( 329.8, 1.460),   # 58  t= 39.65- 41.11
    ( 325.3, 0.220),   # 59  t= 41.11- 41.33
    ( 313.7, 1.660),   # 60  t= 41.33- 42.99
    ( 323.2, 0.160),   # 61  t= 42.99- 43.15  # curve 313->67
    ( 334.2, 0.230),   # 62  t= 43.15- 43.38  # curve 313->67
    ( 343.3, 0.140),   # 63  t= 43.38- 43.52  # curve 313->67
    ( 354.1, 0.180),   # 64  t= 43.52- 43.70  # curve 313->67
    (   2.3, 0.170),   # 65  t= 43.70- 43.87  # curve 313->67
    (  11.8, 0.700),   # 66  t= 43.87- 44.57  # curve 313->67
    (  18.4, 0.350),   # 67  t= 44.57- 44.92  # curve 313->67
    (  24.7, 0.340),   # 68  t= 44.92- 45.26  # curve 313->67
    (  29.1, 0.200),   # 69  t= 45.26- 45.46  # curve 313->67
    (  33.8, 0.200),   # 70  t= 45.46- 45.66  # curve 313->67
    (  43.0, 0.140),   # 71  t= 45.66- 45.80  # curve 313->67
    (  55.6, 0.170),   # 72  t= 45.80- 45.97  # curve 313->67
    (  70.1, 1.050),   # 73  t= 45.97- 47.02  # curve 313->67
    (  75.2, 2.560),   # 74  t= 47.02- 49.58
]

# Wall-clock window each entry came from, same order, for auditing.
DENSE_WINDOWS = [
    ( 10.28,  10.75),
    ( 10.75,  11.08),
    ( 11.08,  11.58),
    ( 11.58,  11.95),
    ( 11.95,  12.13),
    ( 12.13,  12.42),
    ( 12.42,  12.70),
    ( 12.70,  12.96),
    ( 12.96,  13.15),
    ( 13.15,  13.51),
    ( 13.51,  13.73),
    ( 13.73,  13.91),
    ( 13.91,  14.13),
    ( 14.13,  14.32),
    ( 14.32,  14.52),
    ( 14.52,  14.76),
    ( 14.76,  14.92),
    ( 14.92,  15.22),
    ( 15.22,  15.36),
    ( 15.36,  15.52),
    ( 15.52,  15.74),
    ( 15.74,  15.89),
    ( 15.89,  16.06),
    ( 16.06,  16.24),
    ( 16.24,  16.56),
    ( 16.56,  16.72),
    ( 16.72,  16.87),
    ( 16.87,  17.20),
    ( 17.20,  17.50),
    ( 17.50,  17.70),
    ( 18.21,  21.09),
    ( 21.09,  21.75),
    ( 21.75,  22.04),
    ( 22.04,  22.19),
    ( 22.19,  22.38),
    ( 22.38,  22.54),
    ( 22.54,  22.70),
    ( 22.70,  22.86),
    ( 22.86,  22.99),
    ( 22.99,  23.19),
    ( 23.19,  23.54),
    ( 23.54,  23.69),
    ( 23.69,  23.83),
    ( 23.83,  24.00),
    ( 24.00,  24.50),
    ( 24.50,  24.68),
    ( 24.68,  24.85),
    ( 24.85,  25.00),
    ( 25.13,  26.14),
    ( 26.14,  26.53),
    ( 26.89,  27.04),
    ( 27.37,  31.41),
    ( 31.41,  32.81),
    ( 33.35,  33.52),
    ( 33.77,  38.12),
    ( 38.12,  38.71),
    ( 38.71,  39.14),
    ( 39.14,  39.65),
    ( 39.65,  41.11),
    ( 41.11,  41.33),
    ( 41.33,  42.99),
    ( 42.99,  43.15),
    ( 43.15,  43.38),
    ( 43.38,  43.52),
    ( 43.52,  43.70),
    ( 43.70,  43.87),
    ( 43.87,  44.57),
    ( 44.57,  44.92),
    ( 44.92,  45.26),
    ( 45.26,  45.46),
    ( 45.46,  45.66),
    ( 45.66,  45.80),
    ( 45.80,  45.97),
    ( 45.97,  47.02),
    ( 47.02,  49.58),
]

TOTAL_MOVING_SECONDS = 37.18      # == sum of DENSE_ROUTE durations
FIRST_MOVING_T = 10.28            # dense route starts here (typewriter excluded)
LAST_MOVING_T = 49.58             # arrival at the table
TYPEWRITER_OSCILLATION = 10.28    # excluded, see docstring
BEARING_MERGE_TOLERANCE = 4.0     # degrees
MOVE_THRESHOLD = 9.2              # normalised disp_rate, px/s

# Stationary stretches, excluded from DENSE_ROUTE (start, end, seconds).
# The 18.03s final one is standing at the table with the prompt up.
PAUSES = [
    (17.70, 18.21, 0.51),
    (25.00, 25.13, 0.13),
    (26.53, 26.89, 0.36),
    (27.04, 27.37, 0.33),
    (32.81, 33.35, 0.54),
    (33.52, 33.77, 0.25),
    (49.58, 67.61, 18.03),
]

# The 313->67 curve, as an index range into DENSE_ROUTE.
# entries [61:73] = 12 entries, t=42.99-45.97, 2.98s, sweeping 323 -> 56 deg.
# The last ~0.16s of the sweep (reaching 67.4 deg at t=46.13) falls inside
# entry 73, which also carries the settle onto the final 75 deg approach.
CURVE_313_TO_67 = (61, 73)

# --- landmark polling -------------------------------------------------------
# sees_lb_building is CONFIRM-ONLY (True or None, never False) and fires on
# only 15 of the 29 frames in its window -- 52 percent. It does NOT fire at
# t=32.81, which is where route_data's leg B ends, so asserting it at a leg
# boundary fails on a correct walk. Poll it across LB_WINDOW instead and treat
# a single True as confirmation.
#
# Longest gap between consecutive fires inside the window is 1.26s
# (32.09 -> 33.35), so poll at least twice a second to be sure of catching one.
LB_SIGHTINGS = [
    31.88, 32.09, 33.35, 34.04, 34.22, 34.70, 34.83, 34.98,
    35.11, 35.45, 35.76, 35.93, 36.24, 36.50, 36.72,
]
LB_WINDOW = (31.88, 36.72)
LB_FIRE_RATE = 0.52               # 15 of 29 frames in the window
LB_MAX_GAP = 1.26                 # seconds between consecutive fires

# at_baseball_table is the reliable one: True from 49.10 continuously to the
# end of the recording (102 frames, no dropouts). Safe to assert at a point.
TABLE_FIRST_SEEN = 49.10


# ===========================================================================
# TRANSLATION vs ROTATION
# ===========================================================================
# Added after a live replay of DENSE_ROUTE walked the character into furniture
# for its first 29 segments: measured frame delta ~0.9-1.1 (nothing moved),
# against ~4-17 for real travel from segment 30 on.
#
# WHY THE OBVIOUS METRIC DOES NOT WORK, AND A CORRECTION
# ------------------------------------------------------
# My earlier claim that the 313->67 curve was "16 percent rotation" was partly
# an artifact: the horizontal-shift search was capped at +/-110 px, but the
# fastest turn frames genuinely shift up to 192 px, so the search was clipping
# and inflating the residual. Re-run at +/-260 px, the shift-per-degree comes
# out at a consistent 13.3-15.2 px/deg across every fast frame in the
# recording. The corrected numbers are used below.
#
# More importantly, the whole approach of asking "how much of the frame change
# is explained by a pure pan" cannot answer this question, and it is worth
# saying why so nobody retries it. This is a third-person camera: turning
# ORBITS the camera around the character on an arc of several metres. So a
# stationary character still produces a large, genuinely translational optical
# flow. Measured, as texture-normalised residual after removing the best pan:
#
#     character STATIONARY (segments 0-29) ... median 18.8 /s
#     character WALKING    (segments 30-74) ... median 25.8 /s
#
# Overlapping distributions. Vertical flow divergence, which should isolate
# forward motion, separates no better (stationary -12.4 /s, walking -22.7 /s,
# ranges overlapping in both directions). There is no threshold in either that
# reproduces the live result, and picking one would have been fitting noise.
#
# WHAT THE CLASSIFICATION IS ACTUALLY BASED ON
# --------------------------------------------
# Converging structural evidence that the opening stretch is one continuous
# episode of the character PINNED AGAINST THE TYPEWRITER DESK -- not the human
# choosing to pivot, but the character unable to move:
#
#   * The "Typewriter / Save" interaction prompt is on screen from t=0.42 to
#     t=11.25. Scanning landmarks.read_prompt across all 378 frames, that and
#     the destination table (from t=48.01) are the ONLY two real interaction
#     episodes in the recording -- so this is the only place in the whole walk
#     where the character is up against a piece of furniture.
#   * Over t=0.00-10.28 the character makes zero net progress: first and last
#     frames differ by MAD 14.1 while ADJACENT frames differ by ~27. It crept
#     into the desk and stopped.
#   * The episode ends at the first verified full stop of the recording,
#     t=17.70-18.21, after which every metric and the live replay agree there
#     is travel.
#   * The live replay is the ground truth and says exactly this: segments 0-29
#     produce no movement, segment 30 onward do.
#
# So the human's 180 degree about-face at t=10.28-17.70 was camera rotation
# performed while the character was stuck against the desk. There is no
# translation there to reproduce, and replaying it as walking just presses
# into the desk again.
#
# NO SECOND PIVOT. The prompt scan rules one out: nothing else in the walk has
# the character against an object. Both later turns are genuine curved walking
# and are kept in full --the 274->11 turn (segments 31-47), which the live
# replay confirms travels, and the 313->67 curve (segments 61-72, 2.98s, 12
# entries), which is retained entirely.
#
# CONFIDENCE: high on the drop, because four independent lines of evidence
# agree and one of them is a live measurement. Lower on the exact boundary --
# it is placed at the verified full stop t=17.70-18.21, which is the only
# defensible seam, but if the character came free part-way through the sweep
# (say once it had turned away from the desk at t=11.44 when the prompt drops)
# then TRAVEL_ONLY is short by up to a few metres. The at_baseball_table
# checkpoint is what catches that.

# (bearing_degrees, seconds, is_translation) -- the full DENSE_ROUTE, labelled.
SEGMENT_CLASSIFIED = [
    (  93.4, 0.470, False),   #  0  t= 10.28- 10.75
    ( 100.4, 0.330, False),   #  1  t= 10.75- 11.08
    ( 108.6, 0.500, False),   #  2  t= 11.08- 11.58
    ( 117.4, 0.370, False),   #  3  t= 11.58- 11.95
    ( 123.2, 0.180, False),   #  4  t= 11.95- 12.13
    ( 131.8, 0.290, False),   #  5  t= 12.13- 12.42
    ( 139.4, 0.280, False),   #  6  t= 12.42- 12.70
    ( 143.9, 0.260, False),   #  7  t= 12.70- 12.96
    ( 149.4, 0.190, False),   #  8  t= 12.96- 13.15
    ( 156.1, 0.360, False),   #  9  t= 13.15- 13.51
    ( 163.9, 0.220, False),   # 10  t= 13.51- 13.73
    ( 169.0, 0.180, False),   # 11  t= 13.73- 13.91
    ( 176.4, 0.220, False),   # 12  t= 13.91- 14.13
    ( 182.3, 0.190, False),   # 13  t= 14.13- 14.32
    ( 187.0, 0.200, False),   # 14  t= 14.32- 14.52
    ( 193.6, 0.240, False),   # 15  t= 14.52- 14.76
    ( 198.2, 0.160, False),   # 16  t= 14.76- 14.92
    ( 204.5, 0.300, False),   # 17  t= 14.92- 15.22
    ( 211.7, 0.140, False),   # 18  t= 15.22- 15.36
    ( 217.5, 0.160, False),   # 19  t= 15.36- 15.52
    ( 222.3, 0.220, False),   # 20  t= 15.52- 15.74
    ( 226.7, 0.150, False),   # 21  t= 15.74- 15.89
    ( 231.8, 0.170, False),   # 22  t= 15.89- 16.06
    ( 238.4, 0.180, False),   # 23  t= 16.06- 16.24
    ( 245.7, 0.320, False),   # 24  t= 16.24- 16.56
    ( 250.6, 0.160, False),   # 25  t= 16.56- 16.72
    ( 255.2, 0.150, False),   # 26  t= 16.72- 16.87
    ( 261.1, 0.330, False),   # 27  t= 16.87- 17.20
    ( 267.6, 0.300, False),   # 28  t= 17.20- 17.50
    ( 272.2, 0.200, False),   # 29  t= 17.50- 17.70
    ( 272.3, 2.880, True ),   # 30  t= 18.21- 21.09
    ( 278.6, 0.660, True ),   # 31  t= 21.09- 21.75
    ( 284.1, 0.290, True ),   # 32  t= 21.75- 22.04
    ( 289.0, 0.150, True ),   # 33  t= 22.04- 22.19
    ( 294.1, 0.190, True ),   # 34  t= 22.19- 22.38
    ( 298.2, 0.160, True ),   # 35  t= 22.38- 22.54
    ( 304.7, 0.160, True ),   # 36  t= 22.54- 22.70
    ( 309.7, 0.160, True ),   # 37  t= 22.70- 22.86
    ( 315.5, 0.130, True ),   # 38  t= 22.86- 22.99
    ( 322.2, 0.200, True ),   # 39  t= 22.99- 23.19
    ( 329.4, 0.350, True ),   # 40  t= 23.19- 23.54
    ( 333.5, 0.150, True ),   # 41  t= 23.54- 23.69
    ( 338.0, 0.140, True ),   # 42  t= 23.69- 23.83
    ( 343.9, 0.170, True ),   # 43  t= 23.83- 24.00
    ( 353.4, 0.500, True ),   # 44  t= 24.00- 24.50
    (   2.1, 0.180, True ),   # 45  t= 24.50- 24.68
    (   6.8, 0.170, True ),   # 46  t= 24.68- 24.85
    (  11.4, 0.150, True ),   # 47  t= 24.85- 25.00
    (   8.8, 1.010, True ),   # 48  t= 25.13- 26.14
    (   4.1, 0.390, True ),   # 49  t= 26.14- 26.53
    (   3.2, 0.150, True ),   # 50  t= 26.89- 27.04
    (   2.3, 4.040, True ),   # 51  t= 27.37- 31.41
    ( 357.7, 1.400, True ),   # 52  t= 31.41- 32.81
    ( 357.8, 0.170, True ),   # 53  t= 33.35- 33.52
    ( 357.8, 4.350, True ),   # 54  t= 33.77- 38.12
    ( 350.7, 0.590, True ),   # 55  t= 38.12- 38.71
    ( 344.4, 0.430, True ),   # 56  t= 38.71- 39.14
    ( 338.1, 0.510, True ),   # 57  t= 39.14- 39.65
    ( 329.8, 1.460, True ),   # 58  t= 39.65- 41.11
    ( 325.3, 0.220, True ),   # 59  t= 41.11- 41.33
    ( 313.7, 1.660, True ),   # 60  t= 41.33- 42.99
    ( 323.2, 0.160, True ),   # 61  t= 42.99- 43.15
    ( 334.2, 0.230, True ),   # 62  t= 43.15- 43.38
    ( 343.3, 0.140, True ),   # 63  t= 43.38- 43.52
    ( 354.1, 0.180, True ),   # 64  t= 43.52- 43.70
    (   2.3, 0.170, True ),   # 65  t= 43.70- 43.87
    (  11.8, 0.700, True ),   # 66  t= 43.87- 44.57
    (  18.4, 0.350, True ),   # 67  t= 44.57- 44.92
    (  24.7, 0.340, True ),   # 68  t= 44.92- 45.26
    (  29.1, 0.200, True ),   # 69  t= 45.26- 45.46
    (  33.8, 0.200, True ),   # 70  t= 45.46- 45.66
    (  43.0, 0.140, True ),   # 71  t= 45.66- 45.80
    (  55.6, 0.170, True ),   # 72  t= 45.80- 45.97
    (  70.1, 1.050, True ),   # 73  t= 45.97- 47.02
    (  75.2, 2.560, True ),   # 74  t= 47.02- 49.58
]

# Rotation-dominated segments removed. This is the list to replay.
TRAVEL_ONLY = [
    ( 272.3, 2.880),
    ( 278.6, 0.660),
    ( 284.1, 0.290),
    ( 289.0, 0.150),
    ( 294.1, 0.190),
    ( 298.2, 0.160),
    ( 304.7, 0.160),
    ( 309.7, 0.160),
    ( 315.5, 0.130),
    ( 322.2, 0.200),
    ( 329.4, 0.350),
    ( 333.5, 0.150),
    ( 338.0, 0.140),
    ( 343.9, 0.170),
    ( 353.4, 0.500),
    (   2.1, 0.180),
    (   6.8, 0.170),
    (  11.4, 0.150),
    (   8.8, 1.010),
    (   4.1, 0.390),
    (   3.2, 0.150),
    (   2.3, 4.040),
    ( 357.7, 1.400),
    ( 357.8, 0.170),
    ( 357.8, 4.350),
    ( 350.7, 0.590),
    ( 344.4, 0.430),
    ( 338.1, 0.510),
    ( 329.8, 1.460),
    ( 325.3, 0.220),
    ( 313.7, 1.660),
    ( 323.2, 0.160),
    ( 334.2, 0.230),
    ( 343.3, 0.140),
    ( 354.1, 0.180),
    (   2.3, 0.170),
    (  11.8, 0.700),
    (  18.4, 0.350),
    (  24.7, 0.340),
    (  29.1, 0.200),
    (  33.8, 0.200),
    (  43.0, 0.140),
    (  55.6, 0.170),
    (  70.1, 1.050),
    (  75.2, 2.560),
]

TRAVEL_ONLY_SECONDS = 29.76       # == sum of TRAVEL_ONLY durations
DROPPED_SECONDS = 7.42            # segments 0-29, the pinned about-face
DROPPED_SEGMENTS = (0, 30)        # SEGMENT_CLASSIFIED[0:30] are the dropped ones
DROPPED_SPAN = (10.28, 17.70)     # wall clock of the dropped stretch
DROPPED_BEARINGS = (93.4, 272.2)  # heading swept while pinned

# Sanity check the coordinator asked for: TRAVEL_ONLY must land strictly
# between the 19.39s of steady-heading legs in route_data.DEMO_ROUTE and the
# 37.18s of all movement. It comes out at 29.76s, so the curved stretches
# contribute 10.37s of real travel that the turn-then-walk route threw away.
STEADY_HEADING_SECONDS = 19.39
CURVE_CONTRIBUTION = 10.37        # TRAVEL_ONLY_SECONDS - STEADY_HEADING_SECONDS
