"""The SENSOR for closed-loop navigation: where am I along a recorded chain?

    ch = chain.Chain.load("chains/route1")
    fix = ch.locate(img, k_hint=k)          # None = cannot say
    if ch.reached(fix, k + 1): k += 1

WHAT THIS IS FOR
----------------
Dead reckoning replays a recorded (bearing, duration) and looks only at the
leg's end; it arrives 5/10 per route (CLAUDE.md section 8a). The closed loop
LOOKS AFTER EVERY PUSH, so it needs an answer to "which recorded frame am I
standing at, and am I past it yet" that costs one capture and no console time.

A recorded sequence of frames IS the map. `locate()` answers with a chain
index; `reached()` turns that into the one decision the controller makes.

WHY THE SEARCH IS WINDOWED, AND WHY THAT IS NOT A SHORTCUT
----------------------------------------------------------
`places.identify()` searches globally and its gate sits INSIDE the overlap of
two measured populations (CLAUDE.md section 11): a genuine arrival at
`portrait_room` scored 137 matches while a frame taken OUTDOORS ON A STREET,
off the mapped route, scored 135 -- against MIN_MATCHES 140. This game's art
is a black-and-white cartoon of wood, walls and floors, so unrelated rich
frames score 100-155 against ANY room. No count threshold divides those.

A sequence prior does what a threshold cannot. The controller knows it was at
waypoint k a second and one push ago, so the only physically reachable answers
are k-1 .. k+window. Comparing against those alone removes the promiscuous
matches by construction rather than by tuning, which is the trap
`identify_edges`'s 0.906 dark-frame false positive and the ORB gate's overlap
both fell into.

The prior is also the risk: if the true position leaves the window the sensor
cannot say so, it can only report a bad best. `second` (the runner-up's
inliers) and `detail` are on the Fix so a caller can see how thin the win was,
and `tools/chain_validate.py` measures the two populations a MIN_INLIERS gate
would have to separate before any such gate is invented (CLAUDE.md 10.4).

WHAT IS REUSED, DELIBERATELY (SPEC: new files only, import don't reimplement)
-----------------------------------------------------------------------------
Every reimplementation of these on this project has been wrong at least once --
a validation script that mirrored `places._as_gray` without its HUD crop scored
an unmapped corpus ABOVE the references themselves, and a mirror of
`match_count` without its Hamming filter turned 9-of-9 leave-one-out into
3-of-9. So nothing here is copied:

    places._as_gray / places.keypoints   the HUD crop and ORB (nfeatures=1500)
    places._detector()                   the crossCheck Hamming BFMatcher
    places._HAMMING_MAX                  the match filter match_count uses
    pose._MAX_MATCHES / _MIN_INLIERS / _RANSAC_PX
                                         the exact RANSAC parameters pose.offset
                                         fits with (pose.py:107-116)

MIN_INLIERS IS None ON PURPOSE
------------------------------
"A threshold must sit BETWEEN two measured populations, never inside one"
(CLAUDE.md 10.4), and the populations for this sensor have not been measured.
So the knob exists, defaults to None = NEVER ABSTAIN, and the quantity it would
gate (`fix.inliers`) is on every Fix and in every log line, so the first sweep
and the first live run measure it. Setting it from anything but a measured
separation would be inventing a constant.
"""

import json
import math
import os

MIN_INLIERS = None
# Abstention gate on the BEST candidate's inlier count. None = never abstain.
# Read at CALL time inside locate(), never captured in a default argument:
# CLAUDE.md 10.18 -- `def rate(a, b, path=STORE)` bound STORE once at import,
# so an A/B that redirected the module knob changed nothing and said nothing.

_LOG_ONCE = set()


def _warn_once(key, msg):
    if key in _LOG_ONCE:
        return
    _LOG_ONCE.add(key)
    print(msg)


class Waypoint:
    """One recorded frame, with its ORB features precomputed.

    `index` is the recorder's own frame number from meta.jsonl. `k` everywhere
    else in this module is the POSITION in `Chain.waypoints`, which is what
    locate() returns and reached() compares. They coincide whenever the
    recorder writes contiguous indices from 0 (chain_record.py does), and
    `Chain.load` sorts by `index` so the order is the recorded order either
    way. Anything that must map a k back to a recorded frame reads
    `chain.waypoints[k].index` or `.path`, never the k itself.
    """

    __slots__ = ("index", "heading", "cam", "path", "t", "lx", "ly", "note",
                 "kps", "des")

    def __init__(self, index, heading=None, path="", t=0.0, lx=0.0, ly=0.0,
                 note="", kps=None, des=None, cam=None):
        self.index = int(index)
        self.heading = None if heading is None else float(heading)
        # The recorder's COMMANDED camera heading: chain_walk.plan_indices
        # falls back to it when the compass abstained on this frame.
        self.cam = None if cam is None else float(cam)
        self.path = path
        self.t = float(t)
        self.lx = float(lx)
        self.ly = float(ly)
        self.note = note
        self.kps = kps
        self.des = des

    @property
    def n_features(self):
        return 0 if self.des is None else len(self.des)

    def __repr__(self):
        h = "None" if self.heading is None else f"{self.heading:.1f}"
        return (f"<Waypoint {self.index} h={h} kp={self.n_features} "
                f"{os.path.basename(self.path)}>")


class Fix:
    """Where locate() thinks we are, with the evidence attached.

        k         best candidate by INLIER COUNT (a position in Chain.waypoints)
        k_float   k, refined by where the similarity scale crosses 1.0 between
                  two adjacent fitted candidates; == float(k) when no adjacent
                  pair brackets it
        inliers   RANSAC inliers of the winning candidate
        second    the runner-up's inliers -- how thin the win was
        second_k  the runner-up's INDEX, or None when nothing else fitted
        second_dx the runner-up's dx (0.0 when there is no runner-up)
        dx, dy    pixel offset, pose.offset's convention (see below)
        scale     the similarity transform's scale (see below)
        detail    a one-line string for the log
        candidates {k: {"inliers", "dx", "dy", "scale", "matches"}} for every
                  candidate in the window that fitted at all (additive; the
                  three modules' fixed interface does not depend on it)

    dx SIGN -- pose.offset's convention, with the WAYPOINT as frame `a` and the
    LIVE frame as frame `b`. pose.offset takes `src` from `a`, `dst` from `b`
    and returns `median(dst - src)`, so dx > 0 means the scene has moved RIGHT
    in the image between the waypoint and now, which happens when the camera
    has moved LEFT. A controller closing that offset strafes RIGHT.

    scale -- sqrt(a^2 + b^2) of the 2x2 block of the partial affine that maps
    the WAYPOINT's points onto the LIVE frame's. scale > 1 means the scene
    looks BIGGER now than it did in the reference, i.e. we are CLOSER to what
    the waypoint was looking at than the waypoint was -- so, walking toward it,
    we are AT or PAST that waypoint. scale < 1 means it is still ahead.
    """

    __slots__ = ("k", "k_float", "inliers", "dx", "dy", "scale", "second",
                 "detail", "candidates", "second_k", "second_dx")

    def __init__(self, k, k_float, inliers, dx, dy, scale, second, detail,
                 candidates=None, second_k=None, second_dx=0.0):
        self.k = int(k)
        self.k_float = float(k_float)
        self.inliers = int(inliers)
        self.dx = float(dx)
        self.dy = float(dy)
        self.scale = float(scale)
        self.second = int(second)
        self.detail = detail
        self.candidates = candidates or {}
        # WHO the runner-up was, not just how big it was. `second` alone cannot
        # tell an adjacent near-duplicate frame of one stationary run from a
        # candidate that describes a different place, and chain_walk's stop-tie
        # rule was refusing every turn stop on that ambiguity. Optional with
        # defaults so nothing that builds a Fix the old way breaks; None means
        # "no runner-up / cannot say", which a caller must not read as
        # separation (chain_walk reads it as NO evidence of a tie).
        self.second_k = None if second_k is None else int(second_k)
        self.second_dx = float(second_dx)

    def as_dict(self):
        return {"k": self.k, "k_float": round(self.k_float, 3),
                "inliers": self.inliers, "second": self.second,
                "second_k": self.second_k,
                "second_dx": round(self.second_dx, 1),
                "dx": round(self.dx, 1), "dy": round(self.dy, 1),
                "scale": round(self.scale, 4), "detail": self.detail}

    def __repr__(self):
        return f"<Fix {self.detail}>"


def _fit_params():
    """(max_matches, min_inliers, ransac_px) as pose.offset uses them.

    Imported rather than restated so that a change to pose.py's RANSAC cannot
    leave this module fitting with different parameters and nobody noticing.
    """
    import pose
    return pose._MAX_MATCHES, pose._MIN_INLIERS, pose._RANSAC_PX


MIN_MATCHES_TO_FIT = 8
# Below this many surviving matches the pair is not fitted at all. It mirrors
# the literal floor pose.offset and pose.displacement use (`if len(ms) < 8`,
# pose.py:67 and :113) -- unlike the RANSAC parameters it CANNOT be imported,
# because pose states it inline rather than as a constant. It is named here so
# the duplication is visible, and `test_chain_locate` pins it at or above
# pose._MIN_INLIERS: a floor under the inlier minimum could never help, since a
# fit cannot have more inliers than it has matches.


def hamming_filtered(ref_des, live_des):
    """The matches `match_fit` will actually fit: crossCheck pairs closer than
    `places._HAMMING_MAX`, best `pose._MAX_MATCHES` of them by distance.

    THIS FILTER IS THE DELIBERATE DIFFERENCE FROM `pose.offset`, which takes
    the best 200 UNFILTERED. It is `places.match_count`'s own rule
    (places.py:405-409), and it is here because the sequence window compares
    frames that may be genuinely unrelated whenever `k_hint` is wrong -- which
    is the case where noise matches inflate a fit. Measured on the two chain
    fixtures (agent_progress/closed-loop/fix-sensor/measure_survivors.py):

        UNRELATED  street x corridor    294-357 matches,   67-99  survive  21-30%
        RELATED    corridor x corridor  879-1080 matches,  845-1058 survive 96-98%

    so the filter costs a related pair ~2-4% of its evidence and takes ~3/4 of
    an unrelated pair's away. Independently, over 160 held-out office-drive
    frames the skeptic measured FAR >= NEAR on 3/112 filtered against 15/134
    unfiltered. `places._HAMMING_MAX` is read HERE, at call time, so a test can
    move it and see the answer move (10.18).

    Returns a list (possibly empty). It is the only place the filter lives, and
    `test_chain_locate.TheHammingFilterIsLoadBearing` pins both halves: that
    this function filters, and that `match_fit` fits nothing else.
    """
    import places
    if ref_des is None or live_des is None:
        return []
    max_matches, _, _ = _fit_params()
    _, bf = places._detector()
    ms = [m for m in bf.match(ref_des, live_des)
          if m.distance < places._HAMMING_MAX]
    ms.sort(key=lambda m: m.distance)
    return ms[:max_matches]


def match_fit(ref_kps, ref_des, live_kps, live_des):
    """RANSAC-fit the LIVE frame onto a REFERENCE frame's features.

    Returns {"matches", "inliers", "dx", "dy", "scale"} or None when the pair
    cannot be measured. None means UNKNOWN, never "identical" -- pose.py makes
    the same point about `displacement`, and a caller that reads an
    unmeasurable pair as a match accepts exactly the frames it cannot see.

    The matches come from `hamming_filtered` (see there for why the filter is
    not optional); they then go to `cv2.estimateAffinePartial2D` with
    pose.offset's own RANSAC parameters.
    """
    import cv2
    import numpy as np

    if ref_des is None or live_des is None or ref_kps is None or live_kps is None:
        return None
    _, min_inliers, ransac_px = _fit_params()
    ms = hamming_filtered(ref_des, live_des)
    if len(ms) < MIN_MATCHES_TO_FIT:
        return None
    src = np.float32([ref_kps[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([live_kps[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=ransac_px)
    if M is None or inl is None:
        return None
    n = int(inl.sum())
    if n < min_inliers:
        return None
    keep = inl.ravel().astype(bool)
    d = (dst[keep] - src[keep]).reshape(-1, 2)
    return {"matches": len(ms),
            "inliers": n,
            "dx": float(np.median(d[:, 0])),
            "dy": float(np.median(d[:, 1])),
            "scale": float(math.hypot(float(M[0, 0]), float(M[1, 0])))}


class Chain:
    """A recorded route as an ordered list of Waypoints."""

    def __init__(self, waypoints=(), root=""):
        self.waypoints = list(waypoints)
        self.root = root
        self.skipped = []          # meta rows whose jpg was missing

    def __len__(self):
        return len(self.waypoints)

    def __repr__(self):
        return f"<Chain {len(self.waypoints)} waypoints {self.root!r}>"

    # ---------------------------------------------------------------- load

    @classmethod
    def load(cls, d, log=print):
        """Read `d/meta.jsonl` + its frames, precomputing ORB on every one.

        The recorder appends one JSON object per line and flushes, so a crash
        can leave a TRUNCATED final line: it is skipped with a warning rather
        than killing the load, which is the whole point of the append-only
        format. A meta row whose jpg is missing is skipped and recorded in
        `self.skipped` -- loudly, because CLAUDE.md section 10's commonest bug
        here is code that did nothing while looking exactly like it worked.
        """
        import places
        meta = os.path.join(d, "meta.jsonl")
        rows = []
        with open(meta) as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    log(f"  [chain] {meta}:{ln} is not valid JSON (a truncated "
                        f"tail from an interrupted recording?) -- skipped")
        rows.sort(key=lambda r: r.get("index", 0))
        ch = cls(root=d)
        for pos, r in enumerate(rows):
            path = r.get("path") or f"{int(r.get('index', pos)):04d}.jpg"
            if not os.path.isabs(path):
                path = os.path.join(d, path)
            if not os.path.isfile(path):
                ch.skipped.append(path)
                log(f"  [chain] meta names {path!r} but the file is missing "
                    f"-- that waypoint is dropped, so chain positions after it "
                    f"shift by one")
                continue
            kps, des = places.keypoints(path, cache_key=path)
            ch.waypoints.append(Waypoint(
                index=r.get("index", pos), heading=r.get("heading"),
                path=path, t=r.get("t", 0.0),
                lx=r.get("lx", 0.0), ly=r.get("ly", 0.0),
                note=r.get("note", ""), kps=kps, des=des,
                cam=r.get("cam")))
        blind = [w.index for w in ch.waypoints if w.des is None]
        if blind:
            log(f"  [chain] {len(blind)} waypoint(s) yielded NO keypoints "
                f"{blind[:8]} -- they can never be matched. Suspect a blank "
                f"capture or a frame pressed flat against geometry.")
        return ch

    # -------------------------------------------------------------- locate

    def window_bounds(self, k_hint, window=3):
        """(lo, hi) INCLUSIVE candidate range for a hint, clamped to the chain."""
        n = len(self.waypoints)
        if n == 0:
            return (0, -1)
        lo = max(0, int(k_hint) - 1)
        hi = min(n - 1, int(k_hint) + int(window))
        return (lo, hi)

    def locate(self, img, k_hint, window=3):
        """Which waypoint is this frame at? -> Fix, or None to abstain.

        Compares ONLY waypoints[k_hint-1 .. k_hint+window] (see the module
        docstring: a global search is the localiser's known trap). One step
        BACK is included because a push can fail to move the character at all,
        and because the lateral correction can slide the pose backwards
        relative to the last waypoint.

        None means "cannot say": no candidate fitted, the frame yielded no
        keypoints, or -- once MIN_INLIERS is set from a measurement -- the best
        candidate was under it. It never means "not there yet".
        """
        import places

        n = len(self.waypoints)
        if n == 0:
            return None
        lo, hi = self.window_bounds(k_hint, window)
        if hi < lo:
            return None
        kps, des = places.keypoints(img)
        if des is None:
            _warn_once("no-kp", "  [chain] a live frame yielded NO keypoints -- "
                                "locate() abstains because there was nothing to "
                                "compare. Suspect the CAPTURE or a pose pressed "
                                "flat against geometry.")
            return None

        fits = {}
        for j in range(lo, hi + 1):
            w = self.waypoints[j]
            f = match_fit(w.kps, w.des, kps, des)
            if f is not None:
                fits[j] = f
        if not fits:
            return None

        # Best by INLIERS, ties broken by |scale - 1| -- the candidate we are
        # physically nearest. Inlier counts SATURATE at pose._MAX_MATCHES
        # (200), so on a rich scene several adjacent waypoints reach the
        # ceiling and "best by inliers" alone is decided by dict order. Pinned
        # by test_chain_locate.LoadReadsWhatTheRecorderWrites: a frame taken
        # standing exactly AT waypoint 1 fits waypoints 0, 1 and 2 all at 200,
        # and lowest-index-wins answered k=0, so `reached(fix, 1)` said "not
        # yet" while the character was standing on it. Scale does not saturate.
        order = sorted(fits.items(),
                       key=lambda kv: (-kv[1]["inliers"],
                                       abs(kv[1]["scale"] - 1.0)))
        k, best = order[0]
        runner = order[1] if len(order) > 1 else None
        second = runner[1]["inliers"] if runner else 0
        second_k = runner[0] if runner else None
        second_dx = runner[1]["dx"] if runner else 0.0

        gate = MIN_INLIERS          # module knob, read at CALL time (10.18)
        if gate is not None and best["inliers"] < gate:
            return None

        k_float = self._interpolate(k, fits)
        detail = (f"k={k} ({k_float:.2f}) inliers={best['inliers']} "
                  f"second={second} dx={best['dx']:+.0f} "
                  f"scale={best['scale']:.3f} window=[{lo},{hi}] "
                  f"fitted={sorted(fits)}")
        return Fix(k=k, k_float=k_float, inliers=best["inliers"],
                   dx=best["dx"], dy=best["dy"], scale=best["scale"],
                   second=second, detail=detail, candidates=fits,
                   second_k=second_k, second_dx=second_dx)

    @staticmethod
    def _interpolate(k, fits):
        """Sub-waypoint position from where `scale` crosses 1.0.

        Walking forward along the chain, a waypoint already passed looks BIGGER
        than its reference (scale > 1) and one still ahead looks SMALLER
        (scale < 1), so scale falls as the candidate index rises and the
        crossing of 1.0 is the character's position between two waypoints.

        Only ADJACENT fitted candidates (j, j+1) that actually bracket 1.0 are
        used; the bracket nearest the best k wins. With no such pair -- which
        is the ordinary case at the ends of the window, and whenever the scales
        are not monotone -- this returns float(k) and claims nothing.
        """
        ks = sorted(fits)
        brackets = []
        for a, b in zip(ks, ks[1:]):
            if b != a + 1:
                continue
            sa, sb = fits[a]["scale"], fits[b]["scale"]
            if sa >= 1.0 > sb:
                brackets.append(a + (sa - 1.0) / (sa - sb))
        if not brackets:
            return float(k)
        return float(min(brackets, key=lambda v: abs(v - k)))

    # ------------------------------------------------------------- reached

    def reached(self, fix, k):
        """Has the character reached waypoint `k`?

        True when the fix places us PAST it (fix.k > k), or AT it and no longer
        approaching -- fix.k == k with scale >= 1.0, i.e. that waypoint's scene
        already looks at least as big as it did in the reference.

        An abstention is False: not knowing where we are is not evidence of
        having arrived, which is the same rule `pose.same_pose` states.
        """
        if fix is None:
            return False
        if fix.k > k:
            return True
        return fix.k == k and fix.scale >= 1.0
