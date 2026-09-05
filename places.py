"""Which room am I in? — appearance-based localisation from labelled frames.

WHY THIS EXISTS
---------------
worldmap.py dead-reckons a position and says outright what it cannot do: it
does not know about walls, and it has no way to tell that its estimate has gone
wrong. Every recovery built on top of it — turn to a bearing, crab sideways,
retrace east — assumes we are roughly where the route thinks. Once that breaks,
nothing notices, because nothing measures it. Four route attempts on
2026-09-01 ended jammed in geometry for exactly this reason.

This answers the one question dead reckoning cannot: WHERE AM I, actually.

EDGES, NOT BRIGHTNESS. Measured 2026-09-01 on six hand-labelled frames:

    raw intensity   same-place 0.51 / 0.58, different-place 0.64 / 0.74
                    -> different places scored HIGHER than same places
    edge structure  same-place mean 0.646, different-place mean 0.395
                    -> separation +0.251, and every frame's nearest
                       neighbour was another frame from its own place

Intensity is dominated by how dark the room happens to be; structure is not.
This is the same failure that made a small template score ~0.5 on every frame
of a walk — a signal that matches everywhere carries no information.

THE HUD IS MASKED, and that is not cosmetic. The quest list, compass and health
coin are pixel-identical in every frame of the game. Left in, they are a large
constant shared by all frames, which drags every similarity toward 1.0 and
hides exactly the differences being looked for.

WHAT THIS IS NOT. It is not a metric position and cannot be interpolated
between rooms. It answers "which of the places I have been labelled does this
most resemble", and abstains when nothing resembles anything.
"""

import glob
import json
import os

import numpy as np
from PIL import Image, ImageFilter

PLACES_DIR = "places"

# Small on purpose. The question is "which room", not "which pixel", and a
# coarse grid is what makes the answer survive furniture moving, NPCs walking
# through, and the character standing a step to one side.
W, H = 64, 36

# A match must beat this to be believed at all. From the measurement above:
# different-place pairs ran 0.297-0.519, same-place 0.586-0.705.
MIN_SCORE = 0.55
# ...and must beat the runner-up by this, so a frame that resembles two places
# equally abstains instead of guessing. Being confidently in the wrong room is
# worse than not knowing: it is what sends a route walking at a doorway on
# another floor.
MIN_MARGIN = 0.06


def descriptor(img):
    """A place fingerprint: HUD-masked edge structure, unit length."""
    if isinstance(img, str):
        img = Image.open(img)
    a = np.asarray(img.convert("L").filter(ImageFilter.FIND_EDGES)
                   .resize((W, H)), dtype=float)
    a[:int(0.10 * H), :] = 0                 # compass bar
    a[:, :int(0.28 * W)] = 0                 # quest list
    a[int(0.85 * H):, :int(0.20 * W)] = 0    # health coin
    v = a.flatten()
    v -= v.mean()
    n = np.linalg.norm(v)
    return v / n if n else v


# How far a reference frame's heading may differ before it is a DIFFERENT VIEW
# rather than the same one. The camera sees 102 degrees, so two frames more
# than about half that apart share almost no scene — comparing them is
# comparing a room's north wall against its east wall and calling the low score
# evidence about which room it is.
HEADING_WINDOW_DEG = 55.0


def frame_heading(path):
    """The heading a reference frame was captured at, from its name, or None.

    panorama.py writes sweepNN_HHH.jpg. Frames added by hand carry no heading
    and are always eligible, which is the safe default: an unfiltered
    comparison is weaker, never wrong.
    """
    base = os.path.basename(path)
    if base.startswith("sweep") and "_" in base:
        try:
            return float(base.rsplit("_", 1)[1].split(".")[0])
        except ValueError:
            return None
    return None


def _room_dirs(root=PLACES_DIR):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


def load_places(root=PLACES_DIR):
    """{room: [(descriptor, heading_or_None), ...]} from the frames on disk."""
    out = {}
    for room in _room_dirs(root):
        vs = [(descriptor(p), frame_heading(p)) for p in
              sorted(glob.glob(os.path.join(root, room, "*.jpg")))
              if os.path.basename(p) != "pano.jpg"]
        if vs:
            out[room] = vs
    return out


def _next_name(d):
    """The next NNN.jpg in `d` that does not already exist.

    It used to be `len(glob("*.jpg"))`, which is a COUNT and bears no relation
    to the highest index in use. Any GAP in the numbering makes it collide:
    with 000, 001 and 002 present and 001 deleted, the count is 2 and it writes
    002.jpg, silently OVERWRITING a reference still in use. Non-numbered frames
    — route_*.jpg, live_*.jpg, pano.jpg, which every room here holds — shift
    the count again in an unrelated direction, sometimes hiding the collision
    and sometimes skipping indices.

    An overwritten reference is worse than a deleted one: load_keypoints()
    still finds the same filename, so nothing anywhere reports a missing
    frame — the room simply starts answering with a picture of somewhere else.
    It is the only caller-facing way places/ can be corrupted, and both callers
    (brett_walk.mark, Bretts_walk label) are a human deliberately saving a
    reference.

    Two guards, and each catches what the other misses:

      - HIGHEST NUMERIC STEM + 1, so a name is never reused. A deleted 001.jpg
        must not come back meaning a different picture. The +1 also matters
        when a stem is padded to another width: "0007.jpg" claims index 7 while
        the file "007.jpg" does not exist, so without it the next add lands on
        a second file claiming 7.
      - STEP PAST ANYTHING THAT EXISTS. Measured on this machine: glob("*.jpg")
        does NOT match "002.JPG", but the filesystem is case-insensitive and
        os.path.exists("002.jpg") is True — so the name looks free and saving
        there overwrites it, under a directory entry with a different name.
    """
    used = set()
    for q in glob.glob(os.path.join(d, "*.jpg")):
        stem = os.path.splitext(os.path.basename(q))[0]
        if stem.isdigit():
            used.add(int(stem))
    n = max(used) + 1 if used else 0
    while os.path.exists(os.path.join(d, f"{n:03d}.jpg")):
        n += 1
    return f"{n:03d}.jpg"


def add(room, img, root=PLACES_DIR, name=None, check=None, log=print):
    """Save a labelled frame for `room`. Returns the path written.

    An explicit `name` is written as given — the caller chose it, and
    overwriting is then their intent.

    REFUSES a frame that would break identifications that work today, by
    raising DisruptiveReference. See check_add() below for what is measured
    and why; `check=False` (or `places.CHECK_ADDS = False`) writes anyway.

    It RAISES rather than returning None on purpose. Both callers use the
    return value as a path and print it — `-> None` reads like a mild
    complaint and the poisoned set is on disk either way. This project's
    catalogue of expensive bugs is one shape, "the code did nothing and doing
    nothing looked exactly like working", and a refusal that cannot be
    distinguished from a success is that shape.
    """
    if CHECK_ADDS if check is None else check:
        rep = check_add(room, img, root=root, log=log)
        if rep["refuse"]:
            raise DisruptiveReference(rep["reason"])
    d = os.path.join(root, room)
    os.makedirs(d, exist_ok=True)
    if isinstance(img, str):
        img = Image.open(img)
    p = os.path.join(d, name or _next_name(d))
    img.convert("RGB").save(p, quality=88)
    return p


def identify(img, places=None, root=PLACES_DIR, heading=None):
    """Which room is this? -> (room, score, margin), or (None, ...) to abstain.

    DELEGATES TO KEYPOINT MATCHING as of 2026-09-01. `score` is therefore a
    MATCH COUNT (tens to hundreds) and `margin` a RATIO against the runner-up
    (1.0 = a tie), not the 0-1 cosine values every older comment and log line
    in this project quotes. Callers only ever test the room name, but any log
    that reads "0.62" from before that date is the old statistic.

    The measurement that justified it, held out on five arrival frames verified
    by eye, one demo reference per room: edge descriptor 1/5 correct with 4
    abstentions, keypoints 5/5 with none wrong. See identify_orb().

    identify_edges() below is the previous implementation, kept because the
    thresholds and findings recorded throughout this file were measured with it.

    IT ANSWERS A VIEW, NOT A POSITION, and every caller in this tree reads it
    as a position. Measured at one verified pose: turning the camera changes
    the answer to a DIFFERENT node, 500-540 matches at one heading and 355-482
    for another room 225 degrees away, both far above the thresholds. No score
    threshold separates "standing at it" from "looking at it" — see
    view_report(), which returns the same answer with the evidence attached
    and `position: None` stated outright.
    """
    return identify_orb(img, root=root)


def identify_edges(img, places=None, root=PLACES_DIR, heading=None):
    """(room, score, margin) for the best match, or (None, score, margin).

    A room scores as its BEST matching frame, not its average: rooms are
    photographed from several angles and averaging a match against the angle
    you are facing with two you are not just buries the signal.
    """
    places = load_places(root) if places is None else places
    if not places:
        return (None, 0.0, 0.0)
    v = descriptor(img)

    # HEADING IS DELIBERATELY NOT USED TO FILTER REFERENCES, and `heading` is
    # accepted only so callers need not care. It seemed obvious that comparing
    # against frames facing another way was noise. Measured 2026-09-01,
    # leave-one-out over 17 labelled frames:
    #
    #     heading ignored   correct 7   abstain 8   WRONG 2
    #     heading used      correct 2   abstain 9   WRONG 6
    #
    # It is worse, and the reason is structural rather than a tuning problem:
    # filtering strips the true room down to the two or three references facing
    # that way, while any room whose frames carry no heading keeps all of its
    # own. The correct answer is handicapped and its rivals are not.
    #
    # The room already holds views from every angle, so the max over all of
    # them IS the heading-aware answer — the matching frame wins on its own.
    scored = sorted(((max(float(np.dot(v, u)) for u, _h in vs), room)
                     for room, vs in places.items()), reverse=True)
    best, room = scored[0]
    runner = scored[1][0] if len(scored) > 1 else -1.0
    margin = best - runner
    if best < MIN_SCORE or (len(scored) > 1 and margin < MIN_MARGIN):
        return (None, best, margin)
    return (room, best, margin)


# =========================================================================
# KEYPOINT MATCHING — the actual localiser as of 2026-09-01
# =========================================================================
# The edge descriptor above is kept because it is what every historical
# measurement in this file was made with, but it is NO LONGER what identify()
# uses, and the reason is measured rather than aesthetic.
#
# Held-out comparison on five arrival frames I verified BY EYE, both methods
# given the same single demo-seeded reference per room:
#
#     edge descriptor   1/5 correct, 4 abstain
#     ORB keypoints     5/5 correct, 0 wrong, 0 abstain
#
# The descriptor is a GLOBAL statistic, so it fails exactly where a global
# statistic must: standing a step to one side, or an NPC wandering through,
# changes the whole vector. Keypoints match stable structure and simply ignore
# the parts that moved — which is the entire problem here, since the bar is
# full of NPCs that walk around and the executor never stops in quite the same
# spot twice.
#
# It also fixes the failure the descriptor could not be tuned out of: an
# upstairs office door scored 0.906 against beside_dealer_table, HIGHER than
# any genuine match. The same frame gets ONE keypoint match. Negatives
# measured 1-114 matches at ratios 1.00-1.22; positives 166-811 at 1.52-7.10.
MIN_MATCHES = 140          # geometric middle of 114 (worst negative) and 166
MIN_RATIO = 1.35           # ...and of 1.22 (worst negative) and 1.52
_HAMMING_MAX = 50          # a descriptor pair further apart than this is noise

_orb = None
_bf = None
# path -> (stamp, (keypoints, descriptors)). ONE entry per path, never one per
# version: a changed file replaces its own entry rather than accumulating.
_feat_cache = {}


def _detector():
    global _orb, _bf
    if _orb is None:
        import cv2
        _orb = cv2.ORB_create(nfeatures=1500)
        _bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    return _orb, _bf


def _as_gray(img):
    """A masked grayscale array from a path or a PIL image."""
    import cv2
    if isinstance(img, str):
        g = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
    else:
        g = np.asarray(img.convert("L"))
    if g is None:
        return None
    h, w = g.shape[:2]
    # Same masking intent as descriptor(): drop the compass bar, the quest list
    # and the health coin, all of which are pixel-identical in every frame and
    # would otherwise supply free "matches" between any two frames.
    return g[int(h * 0.10):int(h * 0.90), int(w * 0.28):]


def _stamp(path):
    """(mtime_ns, size) for a reference file, or None if it cannot be stat'd.

    WHY A CACHE KEYED ON THE PATH ALONE WAS WRONG. Reference frames on this
    project are REPLACED IN PLACE — three of the four route references were
    swapped for the executor's own arrival frames on 2026-09-03, and
    graph_walk.REFERENCE_POSE exists to A/B two different reference sets. With
    the path as the whole key, the first read of a file wins for the life of
    the process: identify() keeps answering from the OLD picture, nothing
    reports a missing or changed frame, and an A/B between two reference sets
    silently measures the same set twice. An experiment that cannot detect its
    own treatment is the diagnosis-catalogue shape — the code did nothing, and
    doing nothing looked exactly like working.

    NANOSECONDS, NOT SECONDS, AND SIZE AS WELL. Both halves are load-bearing
    and each catches what the other misses:

      - st_mtime at one-second resolution misses a same-second replacement,
        which is exactly how mutation testing on this project was silently
        running STALE BYTECODE: CPython validates a .pyc on (mtime, size), so
        an edit inside one second that preserves the size is invisible to it.
        Measured here: two writes to the same path 3.1ms apart share an
        st_mtime second and differ in st_mtime_ns.
      - size alone misses a same-size edit; mtime_ns alone misses a copy that
        preserves timestamps (cp -p, rsync --times, tar extraction).

    WHAT IT STILL DOES NOT CATCH, stated so nobody has to rediscover it: a
    replacement that preserves BOTH — the same byte count with an mtime
    restored exactly. Only hashing the content would, and that means reading
    every reference on every call; the stat costs 0.010ms against identify()'s
    measured 47ms, a hash would not. If a reference is ever swapped by
    something that preserves timestamps and the size, touch the file.

    Returning None means "this key cannot be stamped", and an unstampable key
    is NOT CACHED. Recomputing costs ~40ms; serving a stale descriptor costs a
    wrong room, so the safe degradation is the slow one.
    """
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    return (st.st_mtime_ns, st.st_size)


def keypoints(img, cache_key=None):
    """(keypoints, descriptors), cached per FILE VERSION when `cache_key` is a
    path. A file replaced in place is re-read — see _stamp()."""
    stamp = None if cache_key is None else _stamp(cache_key)
    if cache_key is not None and stamp is None:
        # Every caller in the tree passes a real path, so this is a wiring
        # error rather than a condition to live with. Say so once: the only
        # other symptom is that the run is quietly slower.
        _warn_once(
            f"unstampable:{cache_key!r}",
            f"  [places] cache_key {cache_key!r} cannot be stat'd, so its "
            f"features will be recomputed on every call. Correct, but slow — "
            f"cache_key is meant to be the path of a reference frame.")
    if stamp is not None:
        hit = _feat_cache.get(cache_key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    orb, _ = _detector()
    g = _as_gray(img)
    out = (None, None) if g is None else orb.detectAndCompute(g, None)
    if stamp is not None:
        _feat_cache[cache_key] = (stamp, out)
    return out


_warned = set()


def _warn_once(key, msg):
    """Print `msg` the first time `key` is seen in this process, then never.

    For conditions that are true for a whole run — an empty reference
    directory, say — where repeating the line once per confirmation would bury
    the log rather than inform it.
    """
    if key in _warned:
        return
    _warned.add(key)
    print(msg)


def match_count(desc_a, desc_b):
    if desc_a is None or desc_b is None:
        return 0
    _, bf = _detector()
    return sum(1 for m in bf.match(desc_a, desc_b) if m.distance < _HAMMING_MAX)


def load_keypoints(root=PLACES_DIR):
    """{room: [descriptors]} for every reference frame on disk."""
    out = {}
    for room in _room_dirs(root):
        for p in sorted(glob.glob(os.path.join(root, room, "*.jpg"))):
            if os.path.basename(p) == "pano.jpg":
                continue
            _, d = keypoints(p, cache_key=p)
            if d is not None:
                out.setdefault(room, []).append(d)
    return out


def identify_orb(img, refs=None, root=PLACES_DIR):
    """(room, matches, ratio) — the keypoint localiser. Abstains as (None,...).

    Scored as the BEST single reference per room, for the same reason
    identify() always has: rooms are photographed from several angles and
    averaging the angle you are facing with two you are not buries the signal.
    """
    refs = load_keypoints(root) if refs is None else refs
    # TWO "CANNOT ANSWER" RETURNS THAT LOOK EXACTLY LIKE A GENUINE ABSTENTION.
    # Both surface downstream as `unverified, abstained (0.000/0.000)` — the
    # same string a real abstention produces, and readers are taught to read
    # that as "a gap in the reference set, not evidence of being somewhere
    # else". Neither of these is that: nothing was compared at all.
    if not refs:
        # Once per process: this is a property of the run, not of the frame.
        # An empty or mis-rooted places/ makes the WHOLE run abstain at EVERY
        # node, and every log line would still read like ordinary bad luck.
        _warn_once(
            "no-refs",
            f"  [places] NO reference frames under {root!r} — identify_orb "
            f"will abstain on every frame for the rest of this run. The log "
            f"line is identical to a genuine abstention, but nothing was "
            f"compared: this is a missing reference set, not an unmapped "
            f"location.")
        return (None, 0, 0.0)
    _, d = keypoints(img)
    if d is None:
        # PER CALL, and deliberately so: this is a property of THIS frame, and
        # it is affordable at confirmation cadence (identify is 43ms). A frame
        # with no keypoints is a blank, black or dead capture — the same
        # signature as the wedged-against-geometry frames, which is a very
        # different diagnosis from "somewhere unphotographed".
        print("  [places] this frame yielded NO keypoints — identify_orb "
              "abstains because there was nothing to compare, not because the "
              "location is unmapped. Suspect the CAPTURE (blank/dead stream) "
              "or a frame pressed flat against geometry.")
        return (None, 0, 0.0)
    return verdict(room_scores(d, refs))


def room_scores(desc, refs):
    """{room: its BEST reference's match count} for one frame's descriptors.

    Best rather than mean, for the reason identify() has always used: rooms
    are photographed from several angles and averaging the angle you are
    facing with two you are not buries the signal.
    """
    return {room: max(match_count(desc, r) for r in rs)
            for room, rs in refs.items()}


def verdict(scores):
    """{room: matches} -> (room, matches, ratio), or (None, ...) to abstain.

    THE ONE PLACE THE DECISION IS MADE. identify_orb() used to inline it and
    check_add() needs the same arithmetic to answer "what would this addition
    do"; two copies of a rule is how the FIFO button bits and the keyboard
    KEYMAP came to disagree on this project, and the symptom there was the
    wrong button pressed with the detector blamed for it.
    """
    if not scores:
        return (None, 0, 0.0)
    order = sorted(scores.items(), key=lambda t: -t[1])
    best = order[0][1]
    second = order[1][1] if len(order) > 1 else 0
    ratio = best / max(second, 1)
    if best < MIN_MATCHES or ratio < MIN_RATIO:
        return (None, best, round(ratio, 2))
    return (order[0][0], best, round(ratio, 2))


# =========================================================================
# ADDING A REFERENCE — the check the write paths never had
# =========================================================================
# `map_propose.admit()` puts a candidate through five gates before anyone may
# add it, because "a place seeded from a bad frame poisons the localiser
# PERMANENTLY and cannot be undone by a threshold". The two INTERACTIVE write
# paths — `Bretts_walk.py label` and `brett_walk.mark` — bypassed every one of
# them. Their only guard was a 200-keypoint structure floor, and it lives in
# the callers, not here.
#
# WHAT THAT COST, measured 2026-09-05 against the real places/ (9 references,
# 4 rooms) with the 160-frame bar_area run plus the references as witnesses,
# 59 of which identify today. One frame of that run, taken STANDING AT
# bar_pool_room and therefore labelled `bar_pool_room` in perfectly good
# faith, added as a reference for it:
#
#     explore/20260904_152521_bar_area/00004.jpg -> bar_pool_room
#         24 of 59 working identifications BROKEN
#         23 of those became a CONFIDENT WRONG ROOM
#         e.g. 00019.jpg  portrait_room 436/3.63 -> bar_pool_room ...
#
# The frame is honest about POSITION and wrong about VIEW: at heading 61 from
# that spot the camera is looking INTO the portrait room, and identify()
# matches VIEWS. Filing that view under `bar_pool_room` teaches the localiser
# that the portrait room is the pool room.
#
# THE SCALE OF IT. Every frame of that run filed under every existing room —
# 640 pairs, each simulated in full:
#
#     POISON  >= 1 confident-wrong break     307   48%
#     SOFT    breaks only into abstentions   162   25%
#     SAFE    breaks nothing                 171   27%
#
# Half of the hand-adds available from one mapping run are poison. This is not
# an exotic mistake to guard against; it is the median outcome.
#
# TWO GATES, AND THE MEASUREMENT THAT SAYS BOTH ARE NEEDED
# --------------------------------------------------------
# G1 CONTRADICTION — the candidate already identifies CONFIDENTLY as another
#    room. Needs no corpus at all: it is one identify() against the references
#    that are being added to. Over those 640 pairs:
#
#        contradicts a confident identify()   150 pairs   150 POISON, 0 other
#        agrees, or the localiser abstains    490 pairs     0 fired
#
#    150 of 150. Perfect precision on this corpus, and it catches every one of
#    the worst cases (the 24-break pairs are all contradictions). It is only
#    half the recall — 157 poison pairs identify as nothing at all — which is
#    exactly why G2 exists.
#
# G2 NON-DISRUPTION — simulate the addition against WITNESS frames and refuse
#    if any identification that works today turns into a different confident
#    room. This is `map_propose.admit()`'s G3, applied to the hand-add path.
#    It is the only gate that can see the 34% of poison adds whose candidate
#    the localiser abstains on (150 of the 440 abstaining pairs).
#
# WHY NOT CHECK AGAINST places/ ITSELF, which is always available and free:
# MEASURED, IT HAS NO POWER. Leave-one-out over the 9 references (each scored
# against the rest of its own room), adding the poison frame above:
#
#     breaks 0 of 9
#
# The references of a room are near-duplicates of each other — portrait_room's
# two score 698 against each other — so nothing a new reference can score will
# displace them. They are the most robust queries in existence and therefore
# the worst possible witnesses. A check built on them would refuse nothing,
# forever, and look exactly like a check. Witnesses must be ORDINARY frames.
#
# WHAT THIS DOES NOT DO. It does not decide whether the label is RIGHT — that
# is map_propose's G6, "unresolved offline; a human must name the room". It
# only refuses a frame that would make the answers we already have worse.


class DisruptiveReference(ValueError):
    """add() refused: this frame would break identifications that work today.

    A ValueError so that a caller with a broad `except ValueError` still sees
    it, and its own class so a caller can catch exactly this and print the
    reason instead of a traceback.
    """


# The master switch, for a batch tool or an A/B that must add without asking.
# Both interactive callers go through the default.
CHECK_ADDS = True

# Where WITNESS frames come from: ordinary world frames that the localiser is
# expected to keep answering the same way about. Globs of DIRECTORIES, resolved
# beside the reference root rather than against the process CWD — the archives
# live next to places/, and a check on a temporary or experimental reference
# set must not drag the production corpus in.
#
# screenshot_log/ (15831 frames) and demos/ (3262) are deliberately absent:
# all three screenshot_log archives are MATCH-PLAYING runs, so a clustering
# pass over 14437 of them returned 8 "distinct viewpoints" that were every one
# a ban or gameplay screen. They are not world frames and would only add cost.
WITNESS_DIRS = ("explore/*", "world_log/*")

# A deterministic stride sample if the archives grow. Not a quality judgement:
# a cap keeps an interactive command interactive, and the report always says
# how many frames were actually examined so a thin check cannot pass for a
# thorough one.
WITNESS_LIMIT = 400

# EXACT ARITHMETIC, NOT A TUNED THRESHOLD — and unlike every gate in this
# project it does not sit between two measured populations, because there are
# no populations here to sit between. Filing a candidate under room R can only
# RAISE R's score for a witness frame. A witness that identifies today has a
# best score s1 >= MIN_MATCHES; the candidate can only take the lead if
# hit > s1, and can only spoil the winner's RATIO if hit > s1 / MIN_RATIO. So
# a witness scoring below MIN_MATCHES / MIN_RATIO against the candidate is
# PROVABLY unaffected and needs no per-room scoring at all.
#
# It is a pure speed-up with no effect on the answer: the frames it skips
# cannot change their verdict. Measured, it is what makes the check cheap
# enough to sit in front of a human typing `label`.
AT_RISK = MIN_MATCHES / MIN_RATIO


def witness_paths(root=PLACES_DIR, dirs=WITNESS_DIRS, limit=WITNESS_LIMIT):
    """Ordinary world frames beside `root`, as a deterministic list."""
    home = os.path.dirname(os.path.abspath(root))
    out = set()
    for pat in dirs:
        for d in sorted(glob.glob(os.path.join(home, pat))):
            if os.path.isdir(d):
                out.update(glob.glob(os.path.join(d, "*.jpg")))
    got = sorted(out)
    if limit and len(got) > limit:
        step = len(got) / float(limit)
        got = [got[int(i * step)] for i in range(limit)]
    return got


def check_add(room, img, root=PLACES_DIR, witnesses=None, log=print):
    """What would adding `img` as a reference for `room` do? Writes NOTHING.

    -> {"refuse", "reason", "contradiction", "witnesses", "at_risk",
        "working", "wrong", "faded", "rescued"}

    `wrong` is the list that refuses: witness frames that identify confidently
    today and would identify as a DIFFERENT confident room afterwards. `faded`
    is the softer class — a confident answer that becomes an abstention — and
    it only warns, on this project's own measured asymmetry: identify() has
    never once named a wrong room in a failed confirmation (10 of 10 were
    abstentions), and an abstention is advisory downstream while a confident
    wrong room sends a route walking at a doorway on another floor.

    The frame is judged AS CAPTURED. add() then writes a quality-88 JPEG of
    it, so the saved reference's keypoints differ slightly from the ones
    measured here.
    """
    _, cd = keypoints(img)
    if cd is None:
        return {"refuse": True, "contradiction": None, "witnesses": 0,
                "at_risk": 0, "working": 0, "wrong": [], "faded": [],
                "rescued": 0,
                "reason": (
                    "this frame yields NO keypoints, so it can never match "
                    "anything and is not a fingerprint of anywhere. Suspect "
                    "the capture (blank/dead stream) or a frame pressed flat "
                    "against geometry.")}

    refs = load_keypoints(root)

    # G1 — CONTRADICTION. The candidate already reads confidently as another
    # room. 150 of 150 such pairs were poison in the measurement above, and
    # every one of the worst cases is one of them.
    seen = verdict(room_scores(cd, refs)) if refs else (None, 0, 0.0)
    contra = seen[0] if seen[0] is not None and seen[0] != room else None

    # G2 — NON-DISRUPTION, against ordinary frames.
    paths = witness_paths(root) if witnesses is None else list(witnesses)
    # A frame cannot witness against ITSELF. Live callers hand in a fresh
    # capture and can never hit this, but a frame re-added from the archive
    # would score a perfect self-match, flip to `room` trivially, and be
    # refused on the strength of the one break it is guaranteed to cause.
    # map_propose.admit() holds its failure frames out of the candidate pool
    # for the mirror-image reason: left in, they rescue themselves at 1346
    # matches and report the problem solved.
    if isinstance(img, str):
        me = os.path.realpath(img)
        paths = [p for p in paths if os.path.realpath(p) != me]
    wrong, faded, rescued, at_risk, working = [], [], 0, 0, 0
    for p in paths:
        _, wd = keypoints(p, cache_key=p)
        if wd is None:
            continue
        hit = match_count(wd, cd)
        if hit < AT_RISK:
            continue            # provably unaffected; see AT_RISK
        at_risk += 1
        before_scores = room_scores(wd, refs)
        before = verdict(before_scores)
        after_scores = dict(before_scores)
        after_scores[room] = max(after_scores.get(room, 0), hit)
        after = verdict(after_scores)
        if before[0] is not None:
            working += 1
            if after[0] != before[0]:
                (wrong if after[0] is not None else faded).append(
                    (p, before, after))
        elif after[0] is not None:
            rescued += 1

    rep = {"contradiction": contra, "witnesses": len(paths),
           "at_risk": at_risk, "working": working, "wrong": wrong,
           "faded": faded, "rescued": rescued}

    if not paths:
        # NOT a pass. Nothing was compared, and a check that proves nothing
        # must not read like a check that found nothing — that is the shape
        # identify_orb's own "no references" warning exists for.
        where = (f"the caller supplied an empty witness list"
                 if witnesses is not None else
                 f"none were found beside {root!r} (looked in "
                 f"{', '.join(WITNESS_DIRS)})")
        _warn_once(
            "no-witnesses",
            f"  [places] NO witness frames: {where}. The non-disruption check "
            f"could not run, so this add is being accepted UNCHECKED — a "
            f"missing corpus, not a clean bill of health.")

    lines = []
    if contra:
        lines.append(
            f"the localiser already reads this frame as {contra!r} "
            f"({seen[1]} matches, ratio {seen[2]}), not {room!r}. identify() "
            f"matches VIEWS, not positions: filing this view under {room!r} "
            f"teaches it that {contra} IS {room}. Measured on the bar_area "
            f"run, 150 of 150 adds that contradicted a confident identify() "
            f"turned working identifications into confident wrong rooms.")
    if wrong:
        lines.append(
            f"it breaks {len(wrong)} of {working} working identifications "
            f"into a DIFFERENT confident room:")
        for p, b, a in wrong[:5]:
            lines.append(f"      {os.path.basename(p)}: {b[0]} "
                         f"({b[1]}/{b[2]}) -> {a[0]} ({a[1]}/{a[2]})")
        if len(wrong) > 5:
            lines.append(f"      ... and {len(wrong) - 5} more")
    rep["refuse"] = bool(contra or wrong)
    rep["reason"] = ("" if not rep["refuse"] else
                     f"REFUSING to add this frame as {room!r}:\n  "
                     + "\n  ".join(lines)
                     + f"\n  Checked against {at_risk} of {len(paths)} "
                       f"witness frames ({len(paths) - at_risk} scored under "
                       f"{AT_RISK:.0f} against it and are provably "
                       f"unaffected).\n  A poisoned reference cannot be undone "
                       f"by a threshold, so this refuses rather than warns. If "
                       f"you are certain, places.add(..., check=False) — or "
                       f"set places.CHECK_ADDS = False — writes it anyway.")

    if log:
        log(f"  check_add {room}: {len(paths)} witnesses, {at_risk} could be "
            f"affected, {working} of those identify today")
        if contra:
            log(f"    CONTRADICTION: the localiser reads this frame as "
                f"{contra} ({seen[1]}/{seen[2]})")
        if faded:
            log(f"    WARNING: {len(faded)} confident identification(s) "
                f"become abstentions — allowed, but they are answers you "
                f"have today and will not have afterwards:")
            for p, b, a in faded[:5]:
                log(f"      {os.path.basename(p)}: {b[0]} ({b[1]}/{b[2]}) "
                    f"-> abstain ({a[1]}/{a[2]})")
        if rescued:
            log(f"    it would also RESCUE {rescued} abstaining frame(s)")
    return rep


# =========================================================================
# THE ANSWER IS A VIEW, NOT A POSITION
# =========================================================================
# identify() matches a FRAME against reference FRAMES, so what it names is
# what the camera is POINTED AT. Every caller reads it as where the character
# IS. Those are different questions and the gap between them is large enough
# to cost runs.
#
# MEASURED at one verified pose (the harness's own arrival at bar_pool_room),
# 32 frames, one localiser call each:
#
#     heading 284-288   bar_pool_room   500-540 matches, ratio 4.10-4.86
#     heading  57- 61   portrait_room   355-482 matches, ratio 2.80-3.64
#     the other 24      abstain
#
# From ONE standing position, turning the camera changes the answer to a
# DIFFERENT node, both far above MIN_MATCHES 140 / MIN_RATIO 1.35. Nothing is
# malfunctioning: the character is standing in the pool room looking at the
# portrait room, and identify() reports what it can see.
#
# NO SCORE THRESHOLD SEPARATES "AT IT" FROM "ONE STEP OFF IT". Measured over
# the bar_area run, grouped by the NOTE each sweep carries: four sweeps were
# taken at the node (go_to_node_verified ran before every fan arm) and the
# rest one to four short pushes out along four bearings. Best bar_pool_room
# score in each group, recomputed against today's references:
#
#     AT the node (4 verified sweeps)   540  521  517  500
#     one step off  (0.35s at 0.30)     507  469  446  434
#     two steps off                     374  360  314  284
#     three steps off                   255  210  179  172
#     four steps off                    never named at all
#
# The at-node MINIMUM (500) sits BELOW the one-step-off MAXIMUM (507): the two
# populations overlap, so no threshold divides them — and raising MIN_MATCHES
# to try would start discarding genuine arrivals (249-698) first. Past one step
# it does separate. So at best this localiser resolves position to about one
# short push, and only when the camera happens to be aimed at the node reference
# view. That is CLAUDE.md's "the localiser is not the bottleneck, position is",
# measured from the other direction.
#
# BEWARE THE STOP IDS IN THAT RUN, which is why the grouping is by note.
# explore.Explorer increments stop_id only inside step(), and
# overnight/map_unknown.py re-walks to the node between fan arms WITHOUT
# stepping — so stops 4, 8 and 12 each hold two sweeps taken at two different
# physical positions ("fan N, step 4" and "at bar_pool_room, before fan M").
# Grouping by `stop` silently averages an at-node sweep with one four pushes
# away; the first version of the table above did exactly that and reported the
# score as NOT MONOTONE in distance, which it is.
#
# WHAT DOES CARRY INFORMATION IS THE HEADING. Over all 160 frames:
#
#     bar_pool_room is named at heading 243-297   (WNW)
#     portrait_room is named at heading  44- 92   (ENE)
#
# The same two arcs from every position in that half of the bar. identify() is
# reporting a BEARING TO A LANDMARK, and a bearing to one landmark is a line,
# not a point. It also limits the obvious repair: corroborating across headings
# separates FAR from near (four steps out, bar_pool_room is never named at all)
# but not one step from zero — a sweep one push off the node names the same two
# rooms in the same two arcs as a sweep on it.
#
# So this module cannot answer "where am I" and should stop being read as if
# it could. view_report() says so in its return value.

def view_report(img, root=PLACES_DIR, refs=None, heading=None):
    """identify(), and everything needed to treat it as the VIEW answer it is.

    -> {"room", "matches", "ratio", "scores", "heading", "position", "caveat"}

    `position` is ALWAYS None, and that is the point of the function rather
    than an omission: one frame cannot locate the camera, only what the camera
    is aimed at (see the measurements above). A caller that needs a position
    must corroborate with something that is not this localiser — the heading
    it was obtained at, the leg just walked, table_prompt.at_table() — and
    `scores` and `heading` are returned so it can.
    """
    refs = load_keypoints(root) if refs is None else refs
    _, d = keypoints(img)
    scores = {} if (d is None or not refs) else room_scores(d, refs)
    room, matches, ratio = verdict(scores)
    return {"room": room, "matches": matches, "ratio": ratio,
            "scores": scores, "heading": heading, "position": None,
            "caveat": (
                f"{room!r} is what this frame is LOOKING AT, not where the "
                f"character is standing. Measured: from one verified pose the "
                f"answer changes to a different node on turning, and four "
                f"positions one to four steps off a node scored within 6% of "
                f"the node itself. Corroborate before treating this as a "
                f"position." if room else
                "abstained — nothing resembles anything, which is a statement "
                "about the reference set, not about position")}
