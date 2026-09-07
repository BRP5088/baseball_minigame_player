"""Census of the bar-area explore corpus, by the leg-failure classifier's classes.

WHY THIS EXISTS. CLAUDE.md OPEN-6 WITHDREW the statistic "OVERSHOT is a quarter
of failures": it was 2 of 8 POST-FAN frames, inadmissible as evidence about a
leg, and even taken at face value a 95% Wilson interval of [0.07, 0.59]. §7
measured, on explore/20260904_152521_bar_area (160 frames), that 100 were RICH
AND UNNAMED -- median 1500 keypoints, median best match 128 against MIN_MATCHES
140, "just under the bar" -- but that figure was reported without an interval,
without the WEDGED count beside it, and by a script that no longer exists. This
one re-takes it through the project's own functions and prints the numbers that
make it checkable: counts by class, a Wilson interval, and where the unnamed
frames' best scores sit relative to the bar. Section 8(f) says to report by
class and with an interval; §10.8 says to state n beside every rate.

"RICH-UNNAMED" IS NOT failure_kind.OVERSHOT. Read this before quoting anything
it prints. failure_kind.classify() labels a frame OVERSHOT when (a) the frame
was captured AT THE END OF A LEG that failed to verify its TARGET on a ROUTE,
(b) the localiser abstains on it, and (c) it holds more than
WEDGED_MAX_KEYPOINTS keypoints. On an EXPLORE corpus there is no leg, no target
and no route: these frames are a mapping run that was DRIVEN OFF the mapped
nodes on purpose (§7: "a deliberate mapping run, 160 frames, 17 stops"), so a
rich frame the localiser cannot name is, in the ordinary case, unmapped ground
the driver went to -- not a leg that ended somewhere it should not have. (b)
and (c) are exactly what this script measures, and it measures them with
failure_kind.classify() itself so the WEDGED/rich boundary is the classifier's
own and not a copy of it; (a) it cannot supply, and no explore corpus can.

Why it is still the closest measurable proxy: the classifier's OVERSHOT verdict
is a statement about APPEARANCE (abstained, and rich) applied to a frame whose
PROVENANCE (a failed leg end) makes it a failure. The provenance half needs
frames only follow_verified's at_<node>_<epoch_ms>.jpg path can write, and
OPEN-1 records how few of those exist. The appearance half can be taken on any
frame off the nodes, and this corpus is the largest set of such frames on disk
with a heading on every one. So what this answers is "when the character is off
the mapped nodes, how often does the frame look OVERSHOT-shaped rather than
WEDGED-shaped or NAMED" -- a bound on what a real census could show, and a
direct check on §7's "two-thirds unmapped". What it does NOT answer is OPEN-1's
question, how LEG FAILURES are distributed; only leg-end frames do.

Two more things it cannot see, stated so nobody reads them in. Liveness: every
frame is archived, so classify() runs with live=None -- "nobody checked" -- and
UNMEASURABLE can never fire; a frozen stream in this corpus would be counted as
whatever it looks like. And NAMED is a VIEW answer, not a position:
places.view_report's own caveat, measured -- a frame taken standing at
bar_pool_room and looking into the portrait room names portrait_room.

ONLY PROJECT FUNCTIONS DO THE MEASURING. places.keypoints() for the count and
the descriptors, places.room_scores() + places.verdict() for the localiser's
answer -- the same composition places.view_report() runs, and view_report()
itself is called on the first frames to prove the two still agree -- and
failure_kind.classify() for the class. Nothing here re-implements _as_gray or
the Hamming filter, because that is precisely how
agent_progress/localiser-inliers/validate.py got this corpus wrong twice:
without the HUD crop it scored the unmapped frames at a median of 777 against a
140 gate (it was measuring the HUD matching itself, 160 times), and with a raw
len(bf.match()) instead of the filtered count it produced six false abstentions
in leave-one-out. A mirror of a project function means nothing until it is
checked against the original, and the cheapest way to pass that check is not to
write the mirror.

WHAT IT COSTS TO RUN. One ORB pass per frame (~40ms) plus the reference load,
on the order of ten seconds for 160 frames -- and it reads every frame from
disk. Do NOT run it while a live experiment is driving the console from this
machine: §10.13 records disk load degrading sleep() from ~5ms to 242ms, which
corrupts every walked leg.

    .venv/bin/python -B tools/overshot_census.py
    .venv/bin/python -B tools/overshot_census.py \
        --out overnight/census/overshot_census_20260904_bar_area.json

The JSON is written ONLY when --out is given; the default is print-only. An
existing --out is never overwritten -- a census is a record, not a tunable.
"""
# No shebang on purpose: `env python` on this machine can resolve to
# paddle_venv (Python 3.11, no cv2 for this tree). Invoke through .venv as
# documented above.
import argparse
import datetime
import glob
import json
import math
import os
import statistics
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# failure_kind imports nothing at module level (places is imported lazily
# inside classify()), so this is free. `places` is imported inside main() on
# purpose: importing THIS module must stay free of numpy/cv2 so that wilson()
# and the kind->class mapping can be checked offline without touching a frame.
import failure_kind  # noqa: E402

# The corpus §7 measured: 160 frames, 17 stops, 15 clusters, "two-thirds
# unmapped". Its index.jsonl carries the 2026-09-04 run's own keypoints /
# identify / score / margin columns, which this script uses as a control
# (see _index_control) -- not as truth.
DEFAULT_CORPUS = os.path.join(PROJECT_ROOT, "explore", "20260904_152521_bar_area")

# "How many rich-unnamed frames sit within this many matches BELOW MIN_MATCHES."
# 20 is the width asked for and is about the gap §7 quotes (median best 128
# against 140, i.e. 12 under). It is a reporting window, not a threshold on
# anything, and --near overrides it.
NEAR_BAR = 20

# Bin width, in matches relative to MIN_MATCHES, for the best-score histogram.
HIST_BIN = 20

# Cross-check this many frames against places.view_report() -- the function
# named in the task -- so that a change to view_report's composition (a new
# guard, a different scorer) is caught here rather than silently diverged from.
# One extra ORB pass each; three is enough to see a systematic difference and
# cheap enough not to matter.
CROSSCHECK_FRAMES = 3

# Class names as printed. Deliberately NOT failure_kind's constants: two of the
# four route classes (REGRESSED / UNPLACED) collapse into NAMED here because
# there is no route to be earlier than, and OVERSHOT is renamed to say what was
# measured rather than what it would mean at a leg end (see the docstring).
WEDGED = "wedged"
NAMED = "named"
RICH_UNNAMED = "rich-unnamed"
UNREADABLE = "unreadable"        # excluded from every denominator
CLASSES = (WEDGED, NAMED, RICH_UNNAMED)

# failure_kind kind -> census class. classify() is called with an EMPTY route,
# so REGRESSED is unreachable (nothing is earlier than anything) but is mapped
# anyway: it and UNPLACED both mean "the localiser named a room". UNMEASURABLE
# is unreachable with live=None and is deliberately ABSENT, so that a future
# classify() emitting something new here raises instead of being filed
# somewhere plausible.
_KIND_TO_CLASS = {
    failure_kind.WEDGED: WEDGED,
    failure_kind.OVERSHOT: RICH_UNNAMED,
    failure_kind.REGRESSED: NAMED,
    failure_kind.UNPLACED: NAMED,
}

WILSON_Z = 1.959964   # two-sided 95%

# The two intervals this project already quotes, from the same formula:
# 2/8 -> [0.07, 0.59] (failure_kind.py:29, CLAUDE.md OPEN-6) and
# 8/10 -> [0.49, 0.94] (CLAUDE.md, the bar_pool_room leg-end census).
# wilson() must reproduce both before any census is reported, so a wrong
# formula REFUSES rather than printing a plausible interval -- a number that
# looks like evidence and is not is this project's signature failure (§10.1).
_WILSON_PINS = (
    ((2, 8), (0.07, 0.59)),
    ((8, 10), (0.49, 0.94)),
)


def wilson(k, n, z=WILSON_Z):
    """Wilson score interval for k successes in n, as (lo, hi).

    n <= 0 has no information and returns (0.0, 1.0), never a division error.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def check_wilson():
    """Refuse to report unless wilson() reproduces the project's quoted intervals."""
    for (k, n), (lo, hi) in _WILSON_PINS:
        got = wilson(k, n)
        if (round(got[0], 2), round(got[1], 2)) != (lo, hi):
            raise AssertionError(
                f"wilson({k}, {n}) = ({got[0]:.4f}, {got[1]:.4f}) does not "
                f"reproduce the project's own quoted [{lo}, {hi}] -- refusing "
                f"to report an interval from a formula that disagrees with "
                f"the ones already in CLAUDE.md")


def census_class(kind):
    """failure_kind kind -> census class, refusing anything unmapped."""
    try:
        return _KIND_TO_CLASS[kind]
    except KeyError:
        raise RuntimeError(
            f"failure_kind.classify returned {kind!r}, which this census has "
            f"no class for -- the classifier has grown a kind since this "
            f"script was written; decide where it belongs rather than filing "
            f"it silently") from None


def measure_frame(path, refs, places):
    """One frame -> a record, through project functions only.

    The composition is places.view_report()'s own body (places.py:831):
    keypoints -> room_scores -> verdict, with the same `desc is None or not
    refs` guard. It is inlined rather than called so that the keypoint COUNT
    and the VERDICT come from ONE ORB pass over one detection, and so the same
    descriptors can be handed to failure_kind.classify() through its injection
    seams without a second pass. crosscheck() proves the inlining still
    matches view_report() on the first frames of every run.
    """
    kps, desc = places.keypoints(path)
    if kps is None:
        # cv2.imread returned None: the file could not be decoded. That is
        # missing data, not a wedged frame, and §10.6 says record None, never
        # a failure. (A readable frame with ZERO keypoints comes back as
        # kps=() / desc=None and falls through -- classify() counts it as
        # n=0, which is genuinely wedged-shaped.)
        return {"file": os.path.basename(path), "class": UNREADABLE,
                "keypoints": 0, "room": None, "best": 0, "ratio": 0.0,
                "scores": {}, "kind": None, "detail": "file could not be read"}
    scores = {} if (desc is None or not refs) else places.room_scores(desc, refs)
    room, best, ratio = places.verdict(scores)
    kind, detail = failure_kind.classify(
        path, target=None, route=(),
        identify=lambda _img: (room, best, ratio),
        keypoints=lambda _img: (kps, desc),
        live=None)
    return {"file": os.path.basename(path), "class": census_class(kind),
            "keypoints": len(kps), "room": room, "best": int(best),
            "ratio": float(ratio),
            "scores": {r: int(s) for r, s in scores.items()},
            "kind": kind, "detail": detail}


def crosscheck(path, rec, refs, places):
    """Raise if places.view_report() disagrees with measure_frame() on `path`."""
    rep = places.view_report(path, refs=refs)
    want = (rep["room"], int(rep["matches"]), float(rep["ratio"]))
    got = (rec["room"], rec["best"], rec["ratio"])
    if want != got:
        raise RuntimeError(
            f"{rec['file']}: places.view_report says {want}, this script's "
            f"composition says {got}. view_report's body has changed since "
            f"this script inlined it (places.py:831) -- fix measure_frame() "
            f"to match before trusting a single number here")


def summarise(records, near, min_matches, min_ratio):
    """Counts, fractions, Wilson intervals and the rich-unnamed score spread."""
    counted = [r for r in records if r["class"] != UNREADABLE]
    n = len(counted)
    rows = {}
    for c in CLASSES:
        k = sum(1 for r in counted if r["class"] == c)
        lo, hi = wilson(k, n)
        rows[c] = {"n": k, "frac": (k / n) if n else 0.0,
                   "wilson95": [round(lo, 3), round(hi, 3)]}

    named_rooms = {}
    for r in counted:
        if r["class"] == NAMED:
            named_rooms[r["room"]] = named_rooms.get(r["room"], 0) + 1

    rich = [r for r in counted if r["class"] == RICH_UNNAMED]
    bests = sorted(r["best"] for r in rich)
    hist = {}
    for b in bests:
        lo = int(math.floor((b - min_matches) / HIST_BIN)) * HIST_BIN
        hist[lo] = hist.get(lo, 0) + 1
    rich_summary = {
        "n": len(rich),
        "best_min": bests[0] if bests else None,
        "best_median": statistics.median(bests) if bests else None,
        "best_max": bests[-1] if bests else None,
        "keypoints_median": (statistics.median(r["keypoints"] for r in rich)
                             if rich else None),
        "ratio_median": (statistics.median(r["ratio"] for r in rich)
                         if rich else None),
        # best >= MIN_MATCHES and still abstained: refused on the RATIO gate
        # alone. This is the signature CLAUDE.md §11 records for the
        # portrait_room regression (ratio 1.16-1.21 against 1.35), kept as its
        # own line because it is a different failure from "not enough matches".
        "at_or_above_bar_ratio_only": sum(1 for r in rich
                                          if r["best"] >= min_matches),
        "near_window": near,
        "within_near_below_bar": sum(1 for r in rich
                                     if min_matches - near <= r["best"]
                                     < min_matches),
        "hist_bin": HIST_BIN,
        "hist": [{"lo": lo, "hi": lo + HIST_BIN, "n": hist[lo]}
                 for lo in sorted(hist)],
    }
    return {"classified": n,
            "unreadable": len(records) - n,
            "by_class": rows,
            "named_by_room": named_rooms,
            "rich_unnamed": rich_summary,
            "gates": {"MIN_MATCHES": min_matches, "MIN_RATIO": min_ratio,
                      "WEDGED_MAX_KEYPOINTS": failure_kind.WEDGED_MAX_KEYPOINTS}}


def load_index(corpus):
    """{basename: row} from the corpus's index.jsonl, or None if absent."""
    p = os.path.join(corpus, "index.jsonl")
    if not os.path.exists(p):
        return None
    out = {}
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                out[os.path.basename(row["file"])] = row
    return out


def index_control(records, index):
    """Agreement with the run's own index.jsonl -- a CONTROL, not a verdict.

    The index was written by the 2026-09-04 run with THAT day's reference set.
    References on this project are replaced in place (places._stamp's
    docstring) and REFERENCE_POSE A/Bs swap whole sets, so a ROOM disagreement
    here is a finding -- "the localiser's answer on this corpus has changed
    since it was indexed" -- and not an error in either. KEYPOINT counts should
    agree exactly: ORB is deterministic and the frames are on disk unchanged,
    so a keypoint disagreement means a different crop or detector, which IS an
    error in one of the two. The 'score' column is the best match, which moves
    with the reference set like the room does.
    """
    compared = room_diff = kp_diff = score_diff = 0
    worst_kp = worst_score = 0
    examples = []
    for r in records:
        row = index.get(r["file"])
        if row is None or r["class"] == UNREADABLE:
            continue
        compared += 1
        if row.get("identify") != r["room"]:
            room_diff += 1
            if len(examples) < 5:
                examples.append({"file": r["file"],
                                 "index": [row.get("identify"), row.get("score")],
                                 "now": [r["room"], r["best"]]})
        dk = abs(int(row.get("keypoints") or 0) - r["keypoints"])
        ds = abs(int(row.get("score") or 0) - r["best"])
        if dk:
            kp_diff += 1
            worst_kp = max(worst_kp, dk)
        if ds:
            score_diff += 1
            worst_score = max(worst_score, ds)
    return {"compared": compared, "room_disagreements": room_diff,
            "keypoint_disagreements": kp_diff, "keypoint_max_delta": worst_kp,
            "score_disagreements": score_diff, "score_max_delta": worst_score,
            "examples": examples}


def _git_head():
    try:
        out = subprocess.run(["git", "-C", PROJECT_ROOT, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def report(corpus, root, refs, summary, control):
    s = summary
    g = s["gates"]
    print(f"\novershot census -- {corpus}")
    print(f"  places root   {root}   "
          f"({len(refs)} rooms, {sum(len(v) for v in refs.values())} references)")
    print(f"  gates         MIN_MATCHES {g['MIN_MATCHES']}   MIN_RATIO {g['MIN_RATIO']}"
          f"   WEDGED_MAX_KEYPOINTS {g['WEDGED_MAX_KEYPOINTS']}")
    print(f"  frames        {s['classified'] + s['unreadable']} read, "
          f"{s['unreadable']} unreadable (excluded from every denominator)")
    print()
    print(f"  {'class':<14}{'n':>5}{'%':>8}   Wilson 95%")
    for c in CLASSES:
        row = s["by_class"][c]
        lo, hi = row["wilson95"]
        print(f"  {c:<14}{row['n']:>5}{100 * row['frac']:>7.1f}%   [{lo:.2f}, {hi:.2f}]")
    print(f"  {'total':<14}{s['classified']:>5}")
    if s["named_by_room"]:
        print("\n  named, by room:  " + "  ".join(
            f"{room} {k}" for room, k in
            sorted(s["named_by_room"].items(), key=lambda t: -t[1])))
    r = s["rich_unnamed"]
    print(f"\n  rich-unnamed best match against MIN_MATCHES {g['MIN_MATCHES']}  (n={r['n']})")
    if r["n"]:
        print(f"    best  min / median / max      {r['best_min']} / {r['best_median']} / {r['best_max']}")
        print(f"    keypoints median              {r['keypoints_median']}")
        print(f"    ratio median                  {r['ratio_median']:.2f}")
        print(f"    at or above the bar, refused on ratio alone (< {g['MIN_RATIO']})   "
              f"{r['at_or_above_bar_ratio_only']}")
        lo_w = g["MIN_MATCHES"] - r["near_window"]
        print(f"    within {r['near_window']} below the bar  [{lo_w}, {g['MIN_MATCHES']})"
              f"{'':>10}{r['within_near_below_bar']}")
        print(f"    best - MIN_MATCHES, {r['hist_bin']}-wide bins")
        for b in r["hist"]:
            print(f"      [{b['lo']:>5}, {b['hi']:>5})  {b['n']:>4}  {'#' * min(b['n'], 60)}")
    print("\n  §7 recorded on this corpus: 100 of 160 rich-and-unnamed, median "
          "keypoints 1500, median best 128. Compare before quoting either.")
    if control is None:
        print("\n  control: no index.jsonl beside the frames -- nothing to compare against")
    else:
        c = control
        print(f"\n  control: agreement with the corpus's own index.jsonl (written by its run)")
        print(f"    compared {c['compared']}   room disagreements {c['room_disagreements']}"
              f"   keypoint disagreements {c['keypoint_disagreements']}"
              f" (max |d| {c['keypoint_max_delta']})"
              f"   best-score disagreements {c['score_disagreements']}"
              f" (max |d| {c['score_max_delta']})")
        if c["keypoint_disagreements"]:
            print("    KEYPOINT counts differ: ORB is deterministic on an unchanged file, "
                  "so one of the two used a different crop or detector. Treat as an ERROR.")
        if c["room_disagreements"]:
            print("    room answers differ: the reference set has changed since the index "
                  "was written (references are replaced in place). A finding, not an error.")
            for e in c["examples"]:
                print(f"      {e['file']}  index {e['index']}  now {e['now']}")
    print()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Do not run while a live experiment is driving the console -- "
               "this reads every frame from disk (CLAUDE.md 10.13).")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS,
                    help="directory of *.jpg frames (default: the §7 bar-area run)")
    ap.add_argument("--root", default=None,
                    help="places/ reference root (default: places.PLACES_DIR under the project)")
    ap.add_argument("--out", default=None,
                    help="write the full result as JSON here; default is print only. "
                         "Never overwrites.")
    ap.add_argument("--near", type=int, default=NEAR_BAR,
                    help=f"width of the 'within N below MIN_MATCHES' window (default {NEAR_BAR})")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the per-frame lines")
    args = ap.parse_args(argv)

    check_wilson()

    if args.out is not None:
        if os.path.exists(args.out):
            print(f"refusing: {args.out} already exists -- a census is a record; "
                  f"pick another name or move the old one aside")
            return 2
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if not os.path.isdir(out_dir):
            print(f"refusing: {out_dir} is not a directory")
            return 2

    # Lazy on purpose -- see the note at the top-level imports.
    import places

    root = args.root or os.path.join(PROJECT_ROOT, places.PLACES_DIR)
    frames = sorted(glob.glob(os.path.join(args.corpus, "*.jpg")))
    if not frames:
        print(f"refusing: no *.jpg under {args.corpus}")
        return 2

    refs = places.load_keypoints(root)
    if not refs:
        # With no references verdict() abstains on EVERY frame, so every rich
        # frame becomes rich-unnamed and the census reads ~100% "overshoot"
        # while measuring nothing. identify_orb() warns once about this state;
        # here it is a refusal, because the output would look like a result.
        print(f"refusing: no reference frames under {root!r} -- every frame would "
              f"abstain and the census would be vacuous")
        return 2

    records = []
    for i, path in enumerate(frames):
        rec = measure_frame(path, refs, places)
        if i < CROSSCHECK_FRAMES and rec["class"] != UNREADABLE:
            crosscheck(path, rec, refs, places)
        records.append(rec)
        if not args.quiet:
            room = rec["room"] or "-"
            print(f"  {rec['file']:<12} kp {rec['keypoints']:>5}  best {rec['best']:>4}"
                  f"  ratio {rec['ratio']:>5.2f}  {room:<16} {rec['class']}")

    summary = summarise(records, args.near, places.MIN_MATCHES, places.MIN_RATIO)
    index = load_index(args.corpus)
    control = index_control(records, index) if index else None
    report(args.corpus, root, refs, summary, control)

    if args.out is not None:
        result = {
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "git_head": _git_head(),
            "corpus": os.path.abspath(args.corpus),
            "places_root": os.path.abspath(root),
            "references_per_room": {room: len(v) for room, v in refs.items()},
            "crosschecked_against_view_report": min(CROSSCHECK_FRAMES, len(frames)),
            "summary": summary,
            "index_control": control,
            "frames": records,
        }
        with open(args.out, "w") as f:
            json.dump(result, f, indent=1)
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
