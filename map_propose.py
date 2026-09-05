"""Turn a mapping run's frames into a PROPOSAL of which new places should exist.

OFFLINE ONLY. Nothing here touches the console, and nothing here writes to
`places/` or `world_map.json`. It reads frames, clusters them, and prints an
argued case for each candidate. A human does the adding.

    BASEBALL_TEST_RUN=1 .venv/bin/python map_propose.py
    BASEBALL_TEST_RUN=1 .venv/bin/python map_propose.py --run explore/2026... \
        --json report.json

WHY THIS EXISTS
---------------
A quarter of route failures are OVERSHOT: a detailed frame (744-1500
keypoints) that `places.identify()` cannot name, because the character has
walked somewhere with no reference. The run then goes blind and must reset.
If those spots were mapped, identify() would name them and the router could
recover instead of throwing the trial away.

THE CONSTRAINT THAT SHAPES EVERYTHING BELOW
-------------------------------------------
A place seeded from a bad frame poisons the localiser PERMANENTLY and cannot
be undone by a threshold. Measured: a near-featureless upstairs office door
matched `beside_dealer_table` at 0.906 / margin 0.366 — HIGHER than any
genuine live match (real arrivals score 0.51-0.78). Three references sit in
`places_quarantine/` for that reason, and removing them was necessary but NOT
sufficient. So a proposal that adds a mediocre reference is worse than
proposing nothing, and this script is built to REJECT.

THE MATCHER IS NOT REIMPLEMENTED HERE
-------------------------------------
Every score comes from `places.keypoints` and `places.match_count` — the same
ORB detector, the same crossCheck BFMatcher, the same _HAMMING_MAX. Clustering
on a different metric would produce clusters that do not predict what the
localiser will do with them, which is the whole question being asked.

`match_count` is SYMMETRIC (crossCheck keeps only mutual best pairs), verified
2026-09-04: frames 00001/00002 score 183 in both directions. Only the upper
triangle is computed.

THE DARK-FRAME TRAP BELONGS TO THE EDGE DESCRIPTOR, NOT TO THIS MATCHER
-----------------------------------------------------------------------
"Low-structure frames correlate with each other, so a cluster of near-blank
frames is not a place" is true, and it is the reason three references sit in
places_quarantine/. But it is a property of `places.descriptor()`, which
divides by the vector norm so a frame with no structure becomes mostly the
vignette every frame shares. Measured 2026-09-04 over the 8 sub-floor frames
in this corpus (4 explore, 4 archived route failures), all 28 pairs:

    edge descriptor   0.825 - 0.974, mean 0.907   28 of 28 clear MIN_SCORE
    ORB match_count       0 - 4,     mean 0.9      0 of 28 clear MIN_MATCHES

The edge figure reproduces the documented 0.906 false positive from an
independent set of frames. ORB is immune: crossCheck matching cannot return
more pairs than the smaller descriptor set, so 9-keypoint frames can produce
at most 9 matches against a threshold of 140.

So the FLOOR below is not what protects against that trap — `identify()` has
used ORB since 2026-09-01 and was never exposed to it. Confirmed by mutation:
with the floor removed the 14 sub-floor frames enter and each lands in its
OWN singleton cluster, none joining another. The floor is kept because a
frame that cannot become a reference should not be clustered at all, but do
not credit it with a protection it is not providing.

WHY AVERAGE LINKAGE, MEASURED
-----------------------------
Single linkage was tried first and is useless here. Measured 2026-09-04 over
the bar_area run (107 usable frames, 5671 pairs), splitting pairs by the
recorded heading difference — a proxy for "same view" that the clustering
itself never sees:

    same view  (dheading < 20)   n=589   p10 76   median 233   max 1077
    diff view  (dheading > 60)   n=3815  p10 39   median  85   max  236

The distributions OVERLAP. A handful of different-view pairs clear 140, and
single linkage needs only one such pair to weld two rooms together: at
threshold 140 it put 104 of 107 frames in ONE component with a cohesion of 93,
i.e. the median pair inside the "cluster" was below the threshold that built
it. Average linkage requires the whole merge to hold, not one lucky pair, and
recovers 11-22 heading-coherent clusters from the same matrix.

The recovered clusters are tight in HEADING even though heading is never an
input — clusters come out as 43-92, 270-297, 106-135, 152-204 degrees. That is
independent corroboration that the clustering is finding real viewpoints and
not arithmetic artefacts.

THRESHOLD. The default link is `places.MIN_MATCHES`, and deliberately not a
new number: average linkage at 140 means that ON AVERAGE, every frame in a
cluster would be identified as every other frame's place by the actual
localiser. That is the localiser's own definition of "same place", applied to
groups instead of to one pair. `--link` sweeps it, and the report prints the
sensitivity, because "how many distinct places" is a function of this choice
and hiding it would be dishonest.
"""

import argparse
import glob
import json
import os
import statistics
import sys

import places

LINK = places.MIN_MATCHES   # see THRESHOLD above

# A frame this rich but unnamed is the failure mode worth mapping — the
# OVERSHOT case (744-1500 keypoints, identify None). Below it, an unnamed
# frame is more likely to be a face full of furniture than a place.
RICH_KP = 400

# A cluster smaller than this was seen from essentially one spot and may be a
# transient — an NPC crossing, a door mid-swing. A reference wants
# corroboration from more than one stop.
MIN_CLUSTER = 3

# The structure floor. It EQUALS places.MIN_MATCHES because it is the same
# fact, not a second opinion: crossCheck matching returns mutual best pairs,
# so a frame with fewer keypoints than MIN_MATCHES can never reach
# MIN_MATCHES against anything and is unusable as a reference by
# construction. It is named separately only so a mutation test can break the
# floor WITHOUT also moving identify()'s own threshold — mutating
# places.MIN_MATCHES changes both at once and the test proves nothing.
FLOOR = places.MIN_MATCHES


# =========================================================================
# Loading
# =========================================================================

def _index_rows(run_dir):
    """{basename: row} from a run's index.jsonl, or {} if it has none."""
    p = os.path.join(run_dir, "index.jsonl")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue        # a run still writing can leave a torn line
            out[os.path.basename(r.get("file", ""))] = r
    return out


def collect(runs, extras):
    """[{path, source, kp, desc, meta}] for every frame worth looking at."""
    frames = []
    for run in runs:
        meta = _index_rows(run)
        for p in sorted(glob.glob(os.path.join(run, "*.jpg"))):
            frames.append({"path": p, "source": os.path.basename(run),
                           "meta": meta.get(os.path.basename(p), {})})
    for d in extras:
        for p in sorted(glob.glob(os.path.join(d, "*.jpg"))):
            frames.append({"path": p,
                           "source": os.path.basename(d.rstrip("/")),
                           "meta": {}})
    for f in frames:
        _, desc = places.keypoints(f["path"], cache_key=f["path"])
        f["desc"] = desc
        f["kp"] = 0 if desc is None else len(desc)
    return frames


# =========================================================================
# Clustering
# =========================================================================

def pairwise(frames):
    """Upper-triangular match counts. m[(i, j)] for i < j."""
    m = {}
    for i in range(len(frames)):
        di = frames[i]["desc"]
        for j in range(i + 1, len(frames)):
            m[(i, j)] = places.match_count(di, frames[j]["desc"])
    return m


def sim(m, i, j):
    return m[(i, j)] if i < j else m[(j, i)]


def average_linkage(n, m, link=LINK):
    """Agglomerate while the AVERAGE similarity across a merge clears `link`.

    Single linkage chains catastrophically on this data (see the module
    docstring); average linkage does not, because welding two rooms together
    requires most of their cross-pairs to agree, not one outlier.

    Sums are carried across merges (Lance-Williams) so the average is exact
    rather than recomputed from members.
    """
    cl = {i: [i] for i in range(n)}
    tot = {}
    for i in range(n):
        for j in range(i + 1, n):
            tot[(i, j)] = float(m[(i, j)])
    while len(cl) > 1:
        best_v, best_p = -1.0, None
        for (a, b), s in tot.items():
            v = s / (len(cl[a]) * len(cl[b]))
            if v > best_v:
                best_v, best_p = v, (a, b)
        if best_p is None or best_v < link:
            break
        a, b = best_p
        cl[a] = cl[a] + cl[b]
        del cl[b]
        for c in list(cl):
            if c == a:
                continue
            ka = (min(a, c), max(a, c))
            kb = (min(b, c), max(b, c))
            tot[ka] = tot.get(ka, 0.0) + tot.get(kb, 0.0)
        for k in [k for k in tot if b in k]:
            del tot[k]
    return sorted(cl.values(), key=len, reverse=True)


def cohesion(idx, m):
    """Median match count over every pair inside a cluster.

    Printed for every cluster so chaining stays visible: a cluster whose
    cohesion sits below the link threshold that built it is not one viewpoint.
    """
    idx = sorted(idx)
    vals = [m[(a, b)] for k, a in enumerate(idx) for b in idx[k + 1:]]
    return statistics.median(vals) if vals else 0


def medoid(idx, m):
    """The frame with the highest MEDIAN match to the rest of its cluster.

    Median rather than mean: the most representative view, not the one that
    happens to sit beside an outlier. This is the frame a proposal would seed,
    so it is chosen to be the one most likely to match again.
    """
    if len(idx) == 1:
        return idx[0], 0
    best, best_v = idx[0], -1
    for a in idx:
        v = statistics.median([sim(m, a, b) for b in idx if b != a])
        if v > best_v:
            best, best_v = a, v
    return best, best_v


# =========================================================================
# Against what already exists
# =========================================================================

def best_against_places(desc, refs):
    """[(room, matches)] sorted best first — the raw per-room scores."""
    return sorted(((room, max(places.match_count(desc, r) for r in rs))
                   for room, rs in refs.items()), key=lambda t: -t[1])


def verdict(scored):
    """identify_orb's own decision, recomputed from per-room scores."""
    if not scored:
        return (None, 0, 0.0)
    room, best = scored[0]
    second = scored[1][1] if len(scored) > 1 else 0
    ratio = best / max(second, 1)
    if best < places.MIN_MATCHES or ratio < places.MIN_RATIO:
        return (None, best, round(ratio, 2))
    return (room, best, round(ratio, 2))


def base_scores(queries, refs):
    """[{room: best_match}] for every query against the CURRENT references.

    Computed once. Every what-if below then costs one match per query instead
    of one per query per reference — without this the four-room sweep over a
    dozen candidates does not finish.
    """
    out = []
    for q in queries:
        if q["desc"] is None:
            out.append(None)
            continue
        out.append({room: max(places.match_count(q["desc"], r) for r in rs)
                    for room, rs in refs.items()})
    return out


def _verdict_from(scores):
    return verdict(sorted(scores.items(), key=lambda t: -t[1]))


def whatif(queries, base, cand_hits, room=None, name="candidate"):
    """Re-identify everything with the candidate added. -> (broken, rescued).

    `room=None` adds it as a NEW NODE (a fresh competitor for the ratio);
    `room=X` files it as another angle on X (which can only raise X, so it
    adds no competitor, but a frame belonging elsewhere can still flip to X).
    """
    broken, saved = [], []
    for q, b, hit in zip(queries, base, cand_hits):
        if b is None:
            continue
        before = _verdict_from(b)
        after_scores = dict(b)
        if room is None:
            after_scores[name] = hit
        else:
            after_scores[room] = max(after_scores.get(room, 0), hit)
        after = _verdict_from(after_scores)
        if before[0] is not None and after[0] != before[0]:
            broken.append((q["path"], before, after))
        elif before[0] is None and after[0] is not None:
            saved.append((q["path"], after))
    return broken, saved



def reference_frames(root):
    """The place references as query frames, for the poison check."""
    out = []
    for room in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, room)
        if not os.path.isdir(d):
            continue
        for p in sorted(glob.glob(os.path.join(d, "*.jpg"))):
            if os.path.basename(p) == "pano.jpg":
                continue
            _, desc = places.keypoints(p, cache_key=p)
            out.append({"path": p, "desc": desc, "room": room})
    return out


DOMINANCE = 0.60      # see home_node


def sweep_exclusivity(frames):
    """{stop: {room: votes}} — what each single standing position identifies as.

    A sweep is 8 headings from ONE spot; turning does not move the character
    (explore.py relies on the same fact). So every label in a stop's row was
    produced from the SAME position, and a row naming two rooms means the
    localiser calls one spot two different places depending on facing.
    """
    by = {}
    for f in frames:
        s, r = f["meta"].get("stop"), f["meta"].get("identify")
        if s is None:
            continue
        by.setdefault(s, {})
        if r:
            by[s][r] = by[s].get(r, 0) + 1
    return by


def home_node(idx, frames, dominance=DOMINANCE):
    """Which MAPPED room was this cluster photographed FROM?

    -> (room_or_None, votes, total, reason)

    THE IDEA, AND WHY IT MOSTLY REFUSES. Appearance cannot answer this — that
    is the thing that fails — so it is answered from the run's geometry
    instead: a sweep is 8 headings from one spot, so if any frame of that
    sweep was identified, every frame of it was taken from inside that room.

    MEASURED 2026-09-04, and the premise does not hold on this data: 16 of 17
    stops in the bar_area run identify as TWO OR MORE different rooms, and
    stops 8-12 name three (portrait_room, bar_pool_room, bar_jukebox) from a
    single standing position. The place nodes are not spatially exclusive —
    they are VIEW BUNDLES, and the references of three nodes are all visible
    from one spot.

    So this refuses unless one room holds a clear majority of the votes at
    the cluster's own stops. It refuses LOUDLY rather than returning the
    plurality: a plurality vote here returned `portrait_room` for every
    cluster in the run, including one that is visibly the bar counter, purely
    because portrait_room is the commonest label overall. That is the
    "success path and no-op path with identical output" shape this project
    keeps paying for, so the refusal carries its reason.

    IT IS STILL NOT TRUSTWORTHY, AND NOTHING HERE LETS IT DECIDE. Measured
    2026-09-04: even at 60% dominance it filed cluster 8 — five frames that
    are visibly the BAR COUNTER, stool row and bottle shelf — under
    `portrait_room`, because portrait_room dominates the label counts at
    every stop in the run. The output is printed as an advisory beside the
    contradicting evidence and never selects a room. Which node a new view
    belongs to is left to a human looking at the image, because neither
    appearance (that is the thing that fails) nor position (16 of 17 stops
    are ambiguous) can answer it offline.
    """
    stops = {frames[i]["meta"].get("stop") for i in idx}
    stops.discard(None)
    if not stops:
        return (None, 0, 0, "no stop metadata")
    votes = {}
    for f in frames:
        if f["meta"].get("stop") in stops and f["meta"].get("identify"):
            r = f["meta"]["identify"]
            votes[r] = votes.get(r, 0) + 1
    total = sum(votes.values())
    if not total:
        return (None, 0, 0, "no frame at these stops was ever identified")
    room = max(votes, key=votes.get)
    if votes[room] / total < dominance:
        return (None, votes[room], total,
                f"the stops are ambiguous — {votes}, no room holds "
                f"{int(dominance * 100)}% of the votes")
    return (room, votes[room], total, "")




def purity(clusters, frames):
    """Do the clusters agree with the labels the localiser already produced?

    A validation, not a gate. Every frame the live run named is a label the
    clustering never saw. If two frames the localiser both called
    `portrait_room` land in different clusters that is fine (different views
    of one room), but a cluster holding frames the localiser named as TWO
    DIFFERENT rooms is a merge error, and that is worth knowing.
    """
    bad = []
    for n, idx in enumerate(clusters, 1):
        named = {frames[i]["meta"].get("identify") for i in idx}
        named.discard(None)
        if len(named) > 1:
            bad.append((n, sorted(named), len(idx)))
    return bad


# =========================================================================
# Report
# =========================================================================

def analyse(runs, extras, places_root=places.PLACES_DIR, link=LINK,
            log=print):
    frames = collect(runs, extras)
    if not frames:
        log("no frames found")
        return {"frames": 0, "clusters": [], "proposals": []}
    refs = places.load_keypoints(places_root)
    ref_frames = reference_frames(places_root)

    # GATE 1 — the structure floor. Arithmetic, not a tuned threshold.
    # places.match_count uses a crossCheck BFMatcher, so its result is a count
    # of MUTUAL best pairs and can never exceed min(len(a), len(b)). A frame
    # with fewer than MIN_MATCHES keypoints therefore cannot reach MIN_MATCHES
    # against anything, ever — it is unusable as a reference by construction.
    # This is what keeps the known trap (low-structure frames correlating with
    # each other) out of the cluster set without inventing a number to do it.
    usable = [f for f in frames if f["kp"] >= FLOOR]
    floored = [f for f in frames if f["kp"] < FLOOR]

    log(f"frames {len(frames)}   usable {len(usable)}   "
        f"below the {FLOOR}-keypoint floor {len(floored)}")
    log("  the floor is arithmetic: crossCheck matching returns mutual best")
    log("  pairs, so a frame with fewer keypoints than MIN_MATCHES can never")
    log("  reach MIN_MATCHES against anything. Excluded before clustering.")
    for f in floored:
        log(f"    {f['path']}  {f['kp']} kp")

    log(f"\nreference set {places_root}: " +
        ", ".join(f"{r} ({len(v)})" for r, v in sorted(refs.items())))
    log(f"link threshold {link} matches (places.MIN_MATCHES), average linkage")

    # Are the existing nodes spatially exclusive? A sweep is 8 headings from
    # ONE spot, so a stop that identifies as two rooms means the localiser
    # calls one standing position two different places depending on facing.
    # This is checked BEFORE the clustering because it governs how the
    # clustering may be read: if the nodes are view bundles rather than
    # rooms, "which room is this cluster in" has no answer to look up.
    sw = sweep_exclusivity(usable)
    mixed = [s for s, v in sw.items() if len(v) > 1]
    named = sum(sum(v.values()) for v in sw.values())
    log(f"\nspatial exclusivity: {len(mixed)} of {len(sw)} standing positions "
        f"identify as 2+ different rooms")
    for s in sorted(sw):
        if len(sw[s]) > 1:
            log(f"    stop {s}: {sw[s]}")
    if mixed:
        log("  The place nodes are NOT spatially exclusive — they are VIEW")
        log("  BUNDLES. One spot can see the references of several nodes, so")
        log("  'which room am I in' is not a question this reference set")
        log("  answers, and a cluster cannot be filed under a node by asking")
        log("  where it was standing.")
    log(f"  {named} of {len(usable)} usable frames are named at all "
        f"({100 * named // max(len(usable), 1)}%)")

    # The what-if baseline: every query's current per-room scores, computed
    # once. The reference frames are in the query set on purpose — a
    # reference that stops identifying as its own room is the loudest
    # possible symptom of a poisoned addition.
    queries = ref_frames + frames
    base = base_scores(queries, refs)
    n_working = sum(1 for b in base if b and _verdict_from(b)[0] is not None)
    log(f"  {n_working} of {len(queries)} query frames "
        f"(corpus + the references themselves) identify today")

    m = pairwise(usable)
    groups = average_linkage(len(usable), m, link)
    log(f"\n{len(groups)} clusters over {len(usable)} usable frames\n")

    bad = purity(groups, usable)
    if bad:
        log("PURITY WARNING — clusters holding frames the live localiser")
        log("named as different rooms (a merge error):")
        for n, names, size in bad:
            log(f"  cluster {n} (n={size}): {names}")
    else:
        log("purity: no cluster mixes frames the live localiser named as")
        log("different rooms. The clustering never saw those labels.")
    log("")

    clusters, proposals = [], []
    for n, idx in enumerate(groups, 1):
        idx = sorted(idx)
        kps = [usable[i]["kp"] for i in idx]
        med_i, med_v = medoid(idx, m)
        med = usable[med_i]
        scored = best_against_places(med["desc"], refs)
        v = verdict(scored)
        coh = cohesion(idx, m)
        hs = sorted(round(usable[i]["meta"]["heading"]) for i in idx
                    if usable[i]["meta"].get("heading") is not None)
        stops = sorted({usable[i]["meta"].get("stop") for i in idx
                        if usable[i]["meta"].get("stop") is not None})
        c = {
            "id": n, "size": len(idx),
            "median_keypoints": int(statistics.median(kps)),
            "cohesion": int(coh),
            "medoid": med["path"], "medoid_median_link": int(med_v),
            "sources": sorted({usable[i]["source"] for i in idx}),
            "heading_range": [hs[0], hs[-1]] if hs else None,
            "stops": stops,
            "best_existing": scored[:3],
            "identify": {"room": v[0], "matches": v[1], "ratio": v[2]},
            "members": [usable[i]["path"] for i in idx],
        }
        clusters.append(c)

        hr = (f"{hs[0]}-{hs[-1]} deg" if hs else "unrecorded")
        log(f"cluster {n}: {len(idx)} frames  median {c['median_keypoints']} kp"
            f"  cohesion {c['cohesion']}  headings {hr}  stops {stops}")
        log(f"  medoid {med['path']} (median link {int(med_v)})")
        log("  vs places/  " + ", ".join(f"{r} {s}" for r, s in scored[:3])
            + f"   -> {v[0] or 'ABSTAIN'} ({v[1]}, ratio {v[2]})")

        # GATE 2 — already mapped.
        if v[0] is not None:
            log(f"  NOT NEW — the localiser already names this {v[0]}.\n")
            c["decision"] = "already_mapped"
            continue
        if len(idx) < MIN_CLUSTER:
            log(f"  REJECT — only {len(idx)} frames. One sighting may be a "
                f"transient (an NPC crossing, a door mid-swing).\n")
            c["decision"] = "too_few"
            continue
        if c["median_keypoints"] < RICH_KP:
            log(f"  REJECT — median {c['median_keypoints']} kp is under the "
                f"{RICH_KP} 'rich enough to be a place' line.\n")
            c["decision"] = "thin"
            continue
        if coh < link:
            log(f"  REJECT — cohesion {int(coh)} is under the link threshold, "
                f"so the medoid does not represent its own cluster.\n")
            c["decision"] = "incoherent"
            continue

        # GATE 3 — the poison simulation, run for BOTH ways of using this
        # cluster. They are not the same risk:
        #
        #   NEW NODE     creates a competitor. Every genuine arrival at every
        #                other room now has one more runner-up, so a
        #                resemblance that is harmless as a score becomes fatal
        #                as a RATIO. This is the expensive option.
        #   EXTRA ANGLE  files the frame under the room it was photographed
        #                FROM (see home_node). It can only raise that room, so
        #                it adds no competitor — but a frame belonging to some
        #                other room can still flip to it.
        #
        # Extra-angle is preferred wherever a home node is known, because it
        # is the option the reference set is designed around: places.py scores
        # a room as its BEST frame precisely so a room can hold many angles.
        home, votes, total, why = home_node(idx, usable)
        c["home_node"] = home
        c["home_votes"] = [votes, total]
        c["home_reason"] = why

        mine = set(c["members"])
        hits = [0 if q["desc"] is None else
                places.match_count(q["desc"], med["desc"]) for q in queries]
        nb, ng = whatif(queries, base, hits, room=None, name=f"candidate_{n}")
        log(f"  as a NEW NODE:    {len(nb)} of {n_working} working "
            f"identifications break, {len(ng)} abstentions rescued")
        for p, b, a in nb[:4]:
            log(f"      {p.split('/')[-1]}: {b[0]} ({b[1]}/{b[2]}) -> "
                f"{a[0] or 'ABSTAIN'} ({a[1]}/{a[2]})")

        c["as_new_node"] = {"checked": n_working, "broken": len(nb),
                            "rescues": len(ng), "broke": [b[0] for b in nb]}

        # Every EXISTING room this view could be filed under, with what each
        # option costs and buys. The script does not CHOOSE: which node a
        # view belongs to cannot be answered offline (appearance is the thing
        # that fails; position is ambiguous at 16 of 17 stops), so the
        # options are laid out and a human picks by looking at the frame.
        opts = {}
        for room in sorted(refs):
            b, g = whatif(queries, base, hits, room=room)
            inc = [x for x in g if x[0] in mine]
            opts[room] = {"breaks": len(b), "rescues": len(g),
                          "rescues_in_cluster": len(inc),
                          "rescues_elsewhere": len(g) - len(inc),
                          "broke": [x[0] for x in b],
                          "elsewhere": [x[0] for x in g if x[0] not in mine]}
        c["as_extra_angle"] = opts
        log("  as an EXTRA ANGLE on an existing room:")
        log("      room             verdict  breaks  rescues(own view/other)")
        for room, o in opts.items():
            safe = "safe" if o["breaks"] == 0 else "BREAKS"
            log(f"      {room:16} {safe:7}  {o['breaks']:6}  "
                f"{o['rescues_in_cluster']:3} / {o['rescues_elsewhere']}")
        # A rescue is only a GAIN if the frame really is that place, and
        # nothing offline can confirm that. A rescue of a frame from this
        # cluster's own view family is self-consistent; a rescue of a frame
        # from somewhere else is a NEW CONFIDENT ANSWER about a view this
        # reference has never seen, which is the expensive kind of wrong.
        # identify() currently abstains rather than misnaming — measured, 10
        # failed confirmations and all ten abstentions, none wrong — and that
        # property is exactly what an out-of-cluster rescue spends.
        worst = max((o["rescues_elsewhere"] for o in opts.values()), default=0)
        if worst:
            log(f"      NOTE: up to {worst} rescues are frames OUTSIDE this "
                f"cluster — new confident answers about views this reference")
            log("      has never seen. Unverifiable offline; treat as risk, "
                "not gain.")
        log(f"  advisory home node from sweep geometry: {home or 'refused'}"
            + (f" ({votes}/{total})" if home else f" — {why}"))
        log("    (advisory only — this vote filed a bar-counter cluster under")
        log("     portrait_room once already; it never selects a room here)")

        c["new_node_rescues_in_cluster"] = len([x for x in ng if x[0] in mine])
        c["new_node_rescues_elsewhere"] = len([x for x in ng if x[0] not in mine])

        if not nb:
            c["decision"] = "propose"
            c["rescues"] = len(ng)
            if not ng:
                c["decision"] = "no_gain"
                log("  REJECT — safe but useless: breaks nothing and rescues "
                    "nothing, so it is pure added risk.\n")
                continue
            proposals.append(c)
            log(f"  PROPOSE — rich, corroborated, unnamed, breaks nothing as "
                f"a new node, rescues {len(ng)} abstaining frames.\n")
            continue

        safe_rooms = [r for r, o in opts.items()
                      if o["breaks"] == 0 and o["rescues"] > 0]
        if safe_rooms:
            c["decision"] = "propose_extend_only"
            c["rescues"] = max(opts[r]["rescues"] for r in safe_rooms)
            proposals.append(c)
            log(f"  PROPOSE, BUT ONLY AS AN EXTRA ANGLE — it breaks "
                f"{len(nb)} identifications as a new node, and is safe only "
                f"under: {', '.join(safe_rooms)}.\n")
            continue

        c["decision"] = "poisons"
        log("  REJECT — every way of adding this costs identifications that "
            "work today.\n")

    # GATE 4 — the candidates against EACH OTHER. Adding two references that
    # resemble one another means neither will ever clear MIN_RATIO again, so
    # a set of individually-safe proposals can still be unsafe together.
    log("=" * 72)
    if len(proposals) > 1:
        # A set of individually-safe proposals can still be unsafe together:
        # two references that resemble each other tie, and neither ever
        # clears MIN_RATIO again. This only bites if they become SEPARATE
        # NODES — two frames filed under the SAME room are supposed to look
        # alike, and a room scores as its best frame, so resemblance there is
        # the design working rather than a collision.
        log("candidate-vs-candidate: two SEPARATE new nodes that resemble")
        log("each other would tie and make both abstain. Pairs that would")
        log("join the same existing room are exempt — a room scores as its")
        log("best frame, so its own angles are meant to look alike.")
        by_path = {f["path"]: f["desc"] for f in usable}
        worst = 0
        for a in range(len(proposals)):
            for b in range(a + 1, len(proposals)):
                pa, pb = proposals[a], proposals[b]
                mc = places.match_count(by_path[pa["medoid"]],
                                        by_path[pb["medoid"]])
                sa = {r for r, o in pa["as_extra_angle"].items()
                      if o["breaks"] == 0}
                sb = {r for r, o in pb["as_extra_angle"].items()
                      if o["breaks"] == 0}
                shared = sa & sb
                if mc < places.MIN_MATCHES:
                    note = "ok"
                elif shared:
                    note = ("ok if both filed under " + "/".join(sorted(shared))
                            + " — COLLIDES only as separate nodes")
                else:
                    note = "COLLIDES and shares no safe room"
                    worst = max(worst, mc)
                log(f"  cluster {pa['id']} vs {pb['id']}: {mc:4}  {note}")
        log(f"  unresolvable collisions: "
            f"{'none' if not worst else worst}")

    log("")
    log(f"{len(clusters)} clusters, {len(proposals)} proposals")
    for c in proposals:
        safe = [r for r, o in c["as_extra_angle"].items() if o["breaks"] == 0]
        what = ("safe either as a NEW NODE or as an extra angle"
                if c["decision"] == "propose"
                else "safe ONLY as an extra angle")
        log(f"  cluster {c['id']}: {what}")
        log(f"      seed    {c['medoid']}")
        log(f"      support {c['size']} frames over stops {c['stops']}, "
            f"{c['median_keypoints']} kp, headings {c['heading_range']} deg")
        log(f"      rescues up to {c.get('rescues', 0)} abstaining frames; "
            f"nearest existing {c['best_existing'][0]}")
        log(f"      may join  {', '.join(safe) if safe else 'no existing room'}")
    if not proposals:
        log("  nothing clears every gate. Proposing nothing is the correct")
        log("  output when the evidence is thin: a mediocre reference cannot")
        log("  be undone by a threshold.")
    return {"frames": len(frames), "usable": len(usable), "link": link,
            "purity_warnings": bad, "clusters": clusters,
            "proposals": proposals}


# =========================================================================
# The admission test
# =========================================================================
# A candidate is ADMITTED only if it would behave like a reference the
# localiser can use, and REJECTED otherwise. It is built to reject: adding a
# mediocre reference is worse than adding nothing, because a wrong confident
# answer sends a route walking at a doorway on another floor and no threshold
# undoes it.
#
# The gates are ordered cheapest-first and every one carries the two
# populations it was measured to separate. Two of them are new here, and both
# exist because the break/rescue test alone was measured to be INSUFFICIENT:
#
# G4 DISCRIMINATION. "Breaks nothing" is not "is a place". Measured on the
#    bar_area corpus, the SAME bar-counter frame (00032) scored 0 breaks filed
#    under EVERY existing room -- bar_jukebox, bar_pool_room, dealer_table and
#    portrait_room alike -- and as a new node. A test that returns the same
#    verdict for the right answer and for `dealer_table` is not choosing
#    anything. Filed under dealer_table it would newly name three bar-counter
#    frames `dealer_table`: three confident wrong answers, scored "safe".
#
# G5 RECOVERABILITY. A proposal must name at least one frame from the failure
#    population it claims to fix. Without this gate a candidate can pass
#    everything and still leave the route exactly as blind as it was, which is
#    the case for every cluster in the bar_area run.
#
# G6 is not a gate this file can apply. WHICH node a new view belongs to
#    cannot be decided offline -- see home_node() -- so a human names it.

MIN_STOPS = 3          # corroboration must come from more than one standing
                       # position; one stop cannot tell a place from a
                       # transient (an NPC crossing, a door mid-swing).
DISCRIM = 1.35         # = places.MIN_RATIO, and the same fact: a reference
                       # whose in-cluster support does not beat its best match
                       # elsewhere by the localiser's own ratio will not be
                       # identified when it is used.


def outside_best(idx, m, n):
    """Best match between any frame IN the cluster and any frame OUTSIDE it."""
    inside = set(idx)
    return max((sim(m, a, b) for a in idx for b in range(n) if b not in inside),
               default=0)


def admit(runs, extras, failures=(), places_root=places.PLACES_DIR, link=LINK,
          log=print):
    """Apply the admission gates to every cluster. Writes NOTHING.

    -> [{cluster, seed, gates, admitted}]. `failures` is the population of
    frames the proposal claims to make recoverable; a candidate that names
    none of them is rejected however clean it looks.
    """
    frames = collect(runs, extras)
    fail_paths = set()
    for d in failures:
        fail_paths.update(glob.glob(os.path.join(d, "*.jpg")))
    # A frame cannot be proposed as the reference that rescues ITSELF, so the
    # failure population is held out of the candidate pool. Leaving it in
    # scores every failframe as a perfect self-match (1346 and 744 against a
    # threshold of 140) and reports the problem as solved.
    pool = [f for f in frames
            if f["kp"] >= FLOOR and f["path"] not in fail_paths]
    log(f"candidate pool {len(pool)} frames "
        f"({len(frames) - len(pool)} dropped: below the {FLOOR}-keypoint "
        f"floor, or held out as failure frames)")
    if not pool:
        return []

    m = pairwise(pool)
    clusters = [sorted(c) for c in average_linkage(len(pool), m, link)]
    refs = places.load_keypoints(places_root)
    queries = [{"path": f["path"], "desc": f["desc"]} for f in pool]
    queries += reference_frames(places_root)
    base = base_scores(queries, refs)

    fdesc = {}
    for fp in sorted(fail_paths):
        _, d = places.keypoints(fp, cache_key=fp)
        if d is not None and len(d) >= FLOOR:
            fdesc[fp] = d
    log(f"failure population {len(fdesc)} usable of {len(fail_paths)} "
        f"(the rest are below the floor: wedged against geometry, "
        f"unmappable by construction)")

    out = []
    for ci, idx in enumerate(clusters, 1):
        seed_i, _ = medoid(idx, m)
        seed = pool[seed_i]
        stops = {pool[i]["meta"].get("stop") for i in idx}
        stops.discard(None)
        coh = cohesion(idx, m)
        out_best = outside_best(idx, m, len(pool))
        support = statistics.median(
            [sim(m, seed_i, b) for b in idx if b != seed_i]) if len(idx) > 1 else 0

        g = {}
        g["G1 floor"] = (seed["kp"] >= FLOOR,
                         f"{seed['kp']} kp vs floor {FLOOR}")
        g["G2 corroboration"] = (
            len(idx) >= MIN_CLUSTER and len(stops) >= MIN_STOPS and coh >= link,
            f"{len(idx)} frames over {len(stops)} stops, cohesion {int(coh)} "
            f"vs link {link}")
        hits = [0 if q["desc"] is None
                else places.match_count(q["desc"], seed["desc"]) for q in queries]
        broken, saved = whatif(queries, base, hits, room=None,
                               name=f"cand_{ci}")
        g["G3 non-disruption"] = (not broken,
                                  f"{len(broken)} working identifications broken")
        g["G4 discrimination"] = (
            support >= link and support >= DISCRIM * max(out_best, 1),
            f"support {int(support)} vs {int(out_best)} outside "
            f"(need >= {link} and >= {DISCRIM} x outside)")
        rescued = []
        for fp, d in fdesc.items():
            hit = max(places.match_count(d, pool[i]["desc"]) for i in idx)
            sc = {room: max(places.match_count(d, r) for r in rs)
                  for room, rs in refs.items()}
            sc[f"cand_{ci}"] = hit
            if verdict(sorted(sc.items(), key=lambda t: -t[1]))[0] == f"cand_{ci}":
                rescued.append((os.path.basename(fp), hit))
        g["G5 recoverability"] = (
            bool(rescued),
            f"names {len(rescued)} of {len(fdesc)} failure frames"
            + (f" {rescued}" if rescued else ""))

        ok = all(v for v, _ in g.values())
        out.append({"cluster": ci, "n": len(idx), "seed": seed["path"],
                    "gates": {k: [v, d] for k, (v, d) in g.items()},
                    "admitted": ok, "rescues": rescued})

    log("")
    for r in out:
        head = "ADMIT" if r["admitted"] else "REJECT"
        log(f"{head}  cluster {r['cluster']} (n={r['n']})  {r['seed']}")
        for k, (v, d) in r["gates"].items():
            log(f"     {'pass' if v else 'FAIL'}  {k:18} {d}")
        if r["admitted"]:
            log("     G6 label            UNRESOLVED OFFLINE — a human must "
                "name the room; see home_node()")
    n_ok = sum(1 for r in out if r["admitted"])
    log(f"\n{len(out)} clusters, {n_ok} admitted")
    if not n_ok:
        log("NONE QUALIFY. Adding nothing is the correct outcome — collect "
            "more frames rather than lowering a gate.")
    return out


def sweep(runs, extras, links=(120, 140, 160, 180, 200, 240)):
    """How sensitive is "how many places" to the link threshold?

    Measured 2026-09-04 on the bar_area run: the RAW cluster count runs 13 to
    33 over this range, so quoting one number for "distinct places" without
    the threshold beside it says almost nothing. The CORROBORATED count
    (clusters of 3+ frames) is far steadier — 8, 11, 10, 11, 13, 14 — which
    is why proposals are drawn only from those.
    """
    frames = collect(runs, extras)
    usable = [f for f in frames if f["kp"] >= FLOOR]
    m = pairwise(usable)
    print(f"{len(usable)} usable frames")
    print("link  clusters  with 3+  largest  median cohesion  purity warnings")
    for t in links:
        g = average_linkage(len(usable), m, t)
        big = [c for c in g if len(c) >= MIN_CLUSTER]
        cohs = [cohesion(c, m) for c in g if len(c) > 1]
        bad = purity([sorted(c) for c in g], usable)
        print(f"{t:4}  {len(g):8}  {len(big):7}  {len(g[0]):7}  "
              f"{int(statistics.median(cohs)) if cohs else 0:15}  {len(bad)}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="append", default=None,
                    help="a mapping-run directory (repeatable); "
                         "default: every directory under explore/")
    ap.add_argument("--extra", action="append",
                    default=["overnight/failframes"],
                    help="a flat directory of loose frames (repeatable)")
    ap.add_argument("--places", default=places.PLACES_DIR)
    ap.add_argument("--link", type=int, default=LINK)
    ap.add_argument("--json", default=None)
    ap.add_argument("--admit", action="store_true",
                    help="apply the admission gates and print a per-gate "
                         "verdict per cluster. Writes nothing.")
    ap.add_argument("--failures", action="append",
                    default=["overnight/failframes"],
                    help="a directory of frames the proposal claims to make "
                         "recoverable (repeatable). G5 rejects any candidate "
                         "that names none of them.")
    ap.add_argument("--sweep", action="store_true",
                    help="print how the cluster count varies with --link "
                         "and exit. 'How many distinct places' is a function "
                         "of the threshold; this shows how much.")
    a = ap.parse_args(argv)

    runs = a.run or sorted(d for d in glob.glob("explore/*") if os.path.isdir(d))
    extras = [d for d in a.extra if os.path.isdir(d)]
    if a.sweep:
        return sweep(runs, extras)
    if a.admit:
        res = admit(runs, extras,
                    failures=[d for d in a.failures if os.path.isdir(d)],
                    places_root=a.places, link=a.link)
        if a.json:
            with open(a.json, "w") as fh:
                json.dump(res, fh, indent=2, default=str)
            print(f"\nwrote {a.json}")
        return 0
    out = analyse(runs, extras, places_root=a.places, link=a.link)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
