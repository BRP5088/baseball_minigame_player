"""Is the character standing in the SAME PLACE as before? — to the pixel.

    pose.displacement(frame_a, frame_b)   -> median inlier displacement, px
    pose.same_pose(frame_a, frame_b)      -> bool

WHY NOT A MATCH COUNT
---------------------
places.identify() answers "which room is this", and a keypoint COUNT is fine for
that. It is useless for "is this the same spot to within a few centimetres":
counts measure how textured the scene is, not how close two poses are. Measured
2026-09-01, correct room identifications ranged 166 to 811 matches — a detailed
wall yields hundreds at any pose, a blank one yields few at an identical pose.

So this measures the GEOMETRY of the matches instead. Fit a partial affine
between the two frames' matched keypoints with RANSAC, and take the median
displacement of the inliers. Identical pose means matched points land on the
same screen coordinates, so the number goes to zero, independent of texture.

THE THRESHOLD IS MEASURED, NOT PICKED
-------------------------------------
Calibrated 2026-09-02 from a world_log session at the jukebox, captured through
compass.fast_capture() — the same path and the same JPEG artefacts the live
system sees, because calibrating on a cleaner representation than production is
how the ban counter and the reveal thresholds both broke:

    stationary, no input at all   n=23   median  3.58px   MAX  8.80px
    after a single 0.2s step      n=10   median 38.89px   MIN 32.25px

A 0.2s walk is therefore resolvable with a 3.7x margin. SAME_POSE_PX sits at the
geometric middle of the two populations, the same way reset_env's
CONFIRM_DELTA_MIN was set.
"""

import numpy as np

# Geometric middle of 8.80 (noise ceiling) and 32.25 (smallest real step).
SAME_POSE_PX = 16.85
_MAX_MATCHES = 200          # best N by descriptor distance, before RANSAC
_MIN_INLIERS = 6
_RANSAC_PX = 3.0


def _feats(img):
    import cv2
    import places
    g = places._as_gray(img)          # same HUD mask as the localiser
    if g is None:
        return None, None
    orb, _ = places._detector()
    return orb.detectAndCompute(g, None)


def displacement(a, b):
    """Median inlier displacement in pixels, or None if it cannot be measured.

    None means "unknown", NOT "the same". A caller that treats an unmeasurable
    pair as identical would accept exactly the frames it cannot see.
    """
    import cv2
    import places

    ka, da = _feats(a)
    kb, db = _feats(b)
    if da is None or db is None:
        return None
    _, bf = places._detector()
    ms = sorted(bf.match(da, db), key=lambda m: m.distance)[:_MAX_MATCHES]
    if len(ms) < 8:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=_RANSAC_PX)
    if M is None or inliers is None or int(inliers.sum()) < _MIN_INLIERS:
        return None
    keep = inliers.ravel().astype(bool)
    return float(np.median(np.linalg.norm(
        (src[keep] - dst[keep]).reshape(-1, 2), axis=1)))


def same_pose(a, b, tol=SAME_POSE_PX):
    """True only if the two frames were taken from the same spot.

    An unmeasurable pair answers False. Being unable to tell is not evidence of
    sameness, and the whole point of this module is to refuse to guess.
    """
    d = displacement(a, b)
    return d is not None and d <= tol


def offset(a, b):
    """(dx, dy) in pixels: how far frame b's view has shifted from frame a.

    The same RANSAC fit displacement() uses, but keeping the DIRECTION instead
    of throwing it away. That direction is what makes correction possible: a
    magnitude only says "you are not where you were", a vector says which way to
    go.

    Sign convention: dx > 0 means the scene moved RIGHT in the image, which
    happens when the camera moved LEFT (or yawed left). Null the yaw with the
    compass first and what remains is lateral translation.

    None when it cannot be measured — never (0, 0), which would read as
    "already aligned" for exactly the frames it cannot see.
    """
    import cv2

    ka, da = _feats(a)
    kb, db = _feats(b)
    if da is None or db is None:
        return None
    import places
    _, bf = places._detector()
    ms = sorted(bf.match(da, db), key=lambda m: m.distance)[:_MAX_MATCHES]
    if len(ms) < 8:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=_RANSAC_PX)
    if M is None or inliers is None or int(inliers.sum()) < _MIN_INLIERS:
        return None
    keep = inliers.ravel().astype(bool)
    d = (dst[keep] - src[keep]).reshape(-1, 2)
    return (float(np.median(d[:, 0])), float(np.median(d[:, 1])))


# Measured at portrait_room, 2026-09-02, one 0.35s push at stick magnitude 0.30:
#
#     strafe right   dx = -126.0   dy =  0.0
#     strafe left    dx = +132.7   dy =  0.0
#     forward        dx =   +5.5   dy = -8.6
#     back           dx =  -14.3   dy = -24.5
#
# So horizontal image shift is driven almost entirely by LATERAL movement, and
# near-symmetrically. Forward/back barely register — monocular depth is weak,
# which is why only the lateral axis is corrected here. In a narrow passage
# (bar stools one side, wall the other) lateral is the axis that matters.
#
# The OPEN-LOOP number above (126px per 0.30 x 0.35s = ~1200 px per
# unit-magnitude-second) is WRONG for control, because that push accelerated
# from a standstill. Measured again from the correction loop itself, where the
# pushes are longer and already moving:
#
#     0.60s at 0.30 corrected 405px  ->  2250
#     0.49s at 0.30 corrected 376px  ->  2558
#
# At the open-loop figure every correction travelled about twice as far as
# intended and the loop OSCILLATED, growing each time: dx went +175 -> -201 ->
# +211 -> -215. Use the closed-loop gain, and damp it: a narrow passage punishes
# overshoot far more than it punishes taking an extra step.
PX_PER_STRAFE_SEC = 2400.0
ALIGN_DAMPING = 0.6
STRAFE_MAG = 0.30
# TOLERANCE IS SET BY THE ACTUATOR, not by the measurement. The offset is
# measurable to ~0px (two stationary frames measured exactly 0.0), but the stick
# cannot deliver an arbitrarily small correction: below about 0.10s a push does
# not move the character at all. Measured 2026-09-02, the loop converged
# 570 -> 256 -> 90 -> 32 and then stalled at 31-34 while issuing 0.03s pushes
# that did nothing.
#
# So 35px is where the loop can actually finish, and claiming 15 would just mean
# never reporting success. For a passage with stools on one side and a wall on
# the other, going from ~400px out to ~25px is the correction that matters.
ALIGN_TOL_PX = 35.0
# Below this a push does not register; asking for less is asking for nothing.
ALIGN_MIN_SEC = 0.10
# A correction that changes dx by less than this did not move the character.
#
# THE OLD JUSTIFICATION HERE WAS A MODEL, NOT A MEASUREMENT, AND IT WAS WRONG.
# It read "one minimum push should shift the view ~72px, so 20px is well under a
# real correction" — but 72 is just ALIGN_MIN_SEC * STRAFE_MAG *
# PX_PER_STRAFE_SEC (0.10 * 0.30 * 2400), the loop's own gain model evaluated at
# the minimum push. Nobody had checked it against a push.
#
# Checked 2026-09-04 against every 0.10s push in the overnight logs
# (newleg, failframes, streak, streak2, phase1/run, phase1/step3 — 127
# align_lateral calls, 221 pushes, all at the CURRENT constants). The sample is
# COMPLETE for minimum pushes: every push ends either in the stuck branch (whose
# `after` is logged) or in the next iteration (whose dx is logged), so nothing
# is dropped.
#
#     one 0.10s push moves the view    n=129
#     min 0   p25 19   MEDIAN 30   p75 41   max 206
#     92% of real minimum pushes move LESS than 55px
#
# So the model over-predicts a minimum push by ~2.4x, and the "~55, the
# geometric middle of the blocked band and one real correction" candidate is
# built on the half of that pair which does not exist.
#
# WHAT RAISING IT WOULD COST, measured as a counterfactual over the 82 calls
# that demonstrably CONVERGED (an outcome the threshold did not influence —
# they reached tolerance):
#
#     STUCK_PX  20 -> aborts  2 of 82 converging calls as "blocked sideways"
#               30 -> aborts 20 of 82
#               55 -> aborts 40 of 82        <- the candidate
#               72 -> aborts 46 of 82
#
# 55 would turn a detector that is merely LATE into one that is WRONG on half
# the calls that were working, which is the opposite of the intent.
#
# AND NO THRESHOLD ON THIS QUANTITY CAN SEPARATE THE TWO POPULATIONS. They
# touch — fired reaches 20, not-fired starts at 3.2 — and worse, the not-fired
# population is CENSORED BY STUCK_PX ITSELF: a step only reaches the next
# iteration because this quantity exceeded 20. Fitting the threshold to it
# measures the loop's own exit condition (CLAUDE.md 10.6, the vacuous
# statistic). Separating "blocked" from "slow" needs a signal that is not this
# difference — the keypoint count already used by failure_kind is the obvious
# candidate, since a character jammed into panelling scores 9-11 against 744+
# in open space.
#
# AND THE DETECTOR IS NOT ACTUALLY LATE. Over the 43 stuck calls it fired after
# a mean of 2.67 strafes and on the FIRST step 28% of the time (12/43).
#
# LEFT AT 20.0 DELIBERATELY. It is not defensible from these populations, but
# neither is any other number, and every alternative measured is worse.
STUCK_PX = 20.0
# How much bigger this step's |dx| must be than the previous step's before the
# loop calls itself diverging and stops. MEASURED 2026-09-04 over the same 127
# calls / 129 consecutive step pairs, all at the current gain:
#
#     pairs inside calls that CONVERGED (n=51)   ratio max 1.186
#     the one genuine divergence on record       ratio 2.733 and 5.695
#
# 1.5 sits in that gap (geometric middle 1.80) and FIRES on the divergence:
# overnight/phase1/step3.log:140, dx +715.2 -> -160.8 -> +915.7 -> -162.0 ->
# -118.8 -> +324.7, which trips at step 2 (915.7 > 160.8 * 1.5).
#
# THE ARGUMENT FOR LOWERING IT TO ~1.10 IS BASED ON THE WRONG OSCILLATION. The
# +175 -> -201 -> +211 -> -215 sequence quoted for it (ratios 1.15, 1.05, 1.02,
# all under 1.5) was measured under the OPEN-LOOP gain of ~1200. Reconstructing
# the commanded `secs` from the logged dx settles which gain produced each log:
# 221 of 221 pushes reproduce exactly at PX_PER_STRAFE_SEC = 2400, and only 56
# of 221 at 1200. So a divergence HAS been measured under the current gain, it
# looks nothing like the open-loop one, and 1.5 catches it.
#
# Lowering to 1.10 was checked and is WORSE: it additionally aborts
# streak2.log:1007, which went 160.7 -> 190.6 -> 119.2 -> 78.0 -> 55.0 and
# CONVERGED to 11.4px. One real convergence lost, no divergence gained.
#
# WHAT IS NOT KNOWN: n=1 on the divergence event. One transient sits between
# 1.5 and the divergence — streak.log:168, 71.0 -> 120.3 -> 79.7, which
# recovered — so 1.5 also fires once in 127 calls on a call that recovered
# (and that call ended blocked anyway). Raising to ~1.8 would spare it. That is
# a one-sample argument on each side, so the value is NOT retuned on it; the
# per-step "dx (prev ...)" logging is already in place to settle it from a run.
DIVERGENCE_FACTOR = 1.5
ALIGN_MAX_STEPS = 6
ALIGN_MAX_SEC = 0.6           # never lunge; a narrow passage punishes overshoot


def align_lateral(ref_img, capture, walk_forward, log=print,
                  tol=ALIGN_TOL_PX, max_steps=ALIGN_MAX_STEPS):
    """Strafe until the view matches `ref_img` horizontally. Returns final |dx|.

    This is the pose correction the router has been missing. places.identify()
    answers "which ROOM", which is not enough to start a dead-reckoned leg from
    — the room is large and the leg assumes a point. This closes that gap on the
    axis that can actually be measured.

    Returns None if the offset could never be measured, which is NOT the same as
    aligned: a blank wall yields no keypoints, and reporting success there would
    be reporting success for exactly the frames it cannot see.
    """
    import time

    last = None
    for i in range(max_steps):
        o = offset(ref_img, capture())
        if o is None:
            log(f"      align: offset unmeasurable (step {i + 1})")
            return last
        dx, _ = o
        prev = last          # the PREVIOUS iteration's dx, for the divergence
                             # test below; `last` is reassigned right after and
                             # cannot be compared against itself.
        last = abs(dx)
        if abs(dx) <= tol:
            log(f"      align: within {tol:.0f}px (dx={dx:+.1f}) after {i} step(s)")
            return abs(dx)
        log(f"      align: step {i + 1}/{max_steps} dx={dx:+.1f} "
            f"(prev {'--' if prev is None else f'{prev:+.1f}'})")
        secs = min(abs(dx) * ALIGN_DAMPING / PX_PER_STRAFE_SEC / STRAFE_MAG,
                   ALIGN_MAX_SEC)
        if secs < ALIGN_MIN_SEC:
            # Use the MINIMUM push rather than giving up. Bailing here was
            # measured worse: it stopped at 84-116px because the damped push for
            # ~106px works out under the floor, while a minimum push moves ~72px
            # and would have closed most of it. Overshoot is caught by the
            # divergence check below.
            if abs(dx) < ALIGN_MIN_SEC * STRAFE_MAG * PX_PER_STRAFE_SEC * 0.5:
                log(f"      align: dx={dx:+.1f} is finer than one minimum push "
                    f"can place — as close as the stick gets")
                return abs(dx)
            secs = ALIGN_MIN_SEC
        # dx > 0 means the scene sits RIGHT of where it should, i.e. the camera
        # is LEFT of the reference — so strafe RIGHT, which measured dx<0.
        side = +1.0 if dx > 0 else -1.0
        log(f"      align: dx={dx:+.1f} -> strafe {'right' if side > 0 else 'left'} "
            f"{secs:.2f}s")
        walk_forward(0.0, secs, strafe=side * STRAFE_MAG)
        time.sleep(0.4)
        # GIVE UP IF IT IS DIVERGING. The first version oscillated with a
        # growing amplitude, so each extra step made the pose worse; stopping at
        # the best seen beats "correcting" past the target repeatedly.
        # THIS COMPARED dx AGAINST ITSELF UNTIL 2026-09-04. `last` is assigned
        # `abs(dx)` ~25 lines above, so the test read `abs(dx) > abs(dx) * 1.5`
        # — always False. The guard never fired once since it was written, and
        # because this branch owns the only "diverging" line, its absence from
        # every log read as "it never diverged". A bound that cannot be reached,
        # sitting inside a branch that writes nothing: two catalogue items at
        # once. It now compares against the PREVIOUS step.
        #
        # The FACTOR was then checked against the logs rather than inherited —
        # see DIVERGENCE_FACTOR. It fires on the one divergence on record under
        # the current gain and on no call that converged. (`i > 0` is redundant:
        # `prev` is None only at i == 0. Kept because it states the intent.)
        if prev is not None and abs(dx) > prev * DIVERGENCE_FACTOR and i > 0:
            log(f"      align: diverging ({abs(dx):.0f}px vs {prev:.0f}px "
                f"before) — stopping")
            return abs(dx)
        # NOT MOVING AT ALL means the character is blocked LATERALLY — pushing
        # sideways into a wall or a bar stool does nothing, and repeating it
        # just burns the budget. Measured 2026-09-02 at bar_pool_room: four
        # corrections in a row left dx at -136, -179, -156, -158.
        # NOTE, measured 2026-09-04, NOT acted on: comparing MAGNITUDES means an
        # overshoot through zero reads as "did not move". 2 of the 43 blocked
        # reports in the logs are this — (+37 -> -21) and (+46 -> -36), both of
        # which travelled ~58-82px and landed INSIDE tol. The returned value is
        # right in those cases (it returns abs(after[0]), i.e. 21 and 36), so
        # the only damage is a wrong log line, 2 times in 43. Left alone because
        # changing it is a behaviour change with no A/B behind it.
        after = offset(ref_img, capture())
        if after is not None and abs(abs(after[0]) - abs(dx)) < STUCK_PX:
            log(f"      align: dx barely changed ({dx:+.0f} -> {after[0]:+.0f}) "
                f"— blocked sideways, cannot correct from here")
            return abs(after[0])
    o = offset(ref_img, capture())
    if o is None:
        log(f"      align: {max_steps} steps used and the final offset is "
            f"UNMEASURABLE")
        return None
    log(f"      align: {max_steps} steps used, still {abs(o[0]):.0f}px out")
    return abs(o[0])
