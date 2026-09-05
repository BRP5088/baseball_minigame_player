Frames from the anchor calibration session (2026-09-02), captured through
compass.fast_capture() — the same path, resolution and JPEG artefacts the live
system sees.

  stationary_*.jpg   consecutive frames with NO input at all
  moved_*.jpg        the same spot after several deliberate 0.2s steps

They exist so pose.SAME_POSE_PX stays anchored to real measurements rather than
drifting to whatever makes a test pass. The calibration behind it:

    stationary, no input   n=23  median  3.58px  MAX  8.80px
    after one 0.2s step    n=10  median 38.89px  MIN 32.25px
