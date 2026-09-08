"""patch46's evidence: every STOP YAW firing in a FROZEN, NAMED population.

WHY THIS EXISTS RATHER THAN A GLOB. The first version of this census globbed
`overnight/chain_journals/route_user_1853_t*_17888[6-9]*.jsonl` -- a directory
the LIVE batch writes into. Two runs 2 minutes apart returned 41 and 42 rows,
and the counts baked into the patch's comment (39 firings) were already stale
when a skeptic re-ran them, because batch 23 was appending firings underneath.
That is CLAUDE.md's own rule ("a test must never glob a directory a live run
writes to -- name the fixture files") one level up: an EVIDENCE claim must not
glob one either.

THE POPULATION IS THEREFORE CLOSED AT BOTH ENDS and named:

    every journal of chain `route_user_1853` whose launch timestamp is in
    [1788860099, 1788872964] -- 2026-09-08 05:36 to 09:09 EDT, ending with the
    last trial of batch 22 (`overnight/chain_trials_batch22.json`, whose run
    rows name their own journals). Batch 23 launched at 09:11 and every journal
    it writes has a LARGER timestamp, so the window cannot grow.

`freeze` writes patch46_yaw_firings.json (manifest with a sha256 per journal,
the extracted firings, and the tally). The default mode RECOUNTS from that file
and, where the journals are still on disk, re-extracts and reports any drift --
so the numbers in chain_walk.py's comment can be checked in one command years
after the journals are gone.

    python -B drafts/pending_after_ab/patch46_yaw_census.py            # recount
    python -B drafts/pending_after_ab/patch46_yaw_census.py freeze     # re-freeze

A firing is a journal row whose `lateral` carries a `yaw` (chain_walk's
STOP_LOOK_YAW block). It is scored on the FIRST CREDIBLE FIT (>= 29 inliers,
chain_walk.FIX_MIN_INLIERS) in the five rows after it: that fit's `dx` is what
the yaw left behind. `off` is the look's own fit index minus the stop's index --
the quantity STOP_YAW_NEAR_FIT_ONLY gates on.
"""
import collections
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "patch46_yaw_firings.json")
CHAIN = "route_user_1853"
TS_LO, TS_HI = 1788860099, 1788872964          # closed at both ends, see above
CREDIBLE = 29                                  # chain_walk.FIX_MIN_INLIERS
AHEAD = 5                                      # rows scored after a firing
TOL = 1                                        # STOP_YAW_FIT_TOL


def journals(root):
    out = []
    for p in sorted(glob.glob(os.path.join(
            root, "overnight", "chain_journals", "%s_t*.jsonl" % CHAIN))):
        try:
            ts = int(os.path.basename(p).rsplit("_", 1)[1].split(".")[0])
        except (IndexError, ValueError):
            continue
        if TS_LO <= ts <= TS_HI:
            out.append(p)
    return out


def firings(path):
    """The firings in one journal, with the outcome of the trial that wrote it."""
    raw = open(path, "rb").read()
    rows = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
    outcome = "ARRIVED" if any(r.get("action") == "arrived" for r in rows) else "FAILED"
    out = []
    for i, r in enumerate(rows):
        lat = r.get("lateral") or {}
        if not (isinstance(lat, dict) and "yaw" in lat):
            continue
        fix = r.get("fix") or {}
        nxt = next((rr for rr in rows[i + 1:i + 1 + AHEAD]
                    if ((rr.get("fix") or {}).get("inliers") or 0) >= CREDIBLE), None)
        k = fix.get("k")
        out.append({"journal": os.path.basename(path), "stop": r["target"],
                    "fit_k": k, "off": None if k is None else k - r["target"],
                    "look_inliers": fix.get("inliers"),
                    "yaw_px": lat["yaw"]["px"], "yaw_deg": lat["yaw"]["deg"],
                    "dx_after": (round(nxt["fix"].get("dx") or 0) if nxt else None),
                    "outcome": outcome})
    return raw, out


def tally(rows):
    """The table the patch quotes: per stop, split at STOP_YAW_FIT_TOL."""
    g = collections.defaultdict(list)
    for r in rows:
        near = r["off"] is not None and abs(r["off"]) <= TOL
        g[(r["stop"], "within +-%d" % TOL if near else "further off")].append(r)
    out = []
    for key in sorted(g):
        rr = g[key]
        dx = sorted(x["dx_after"] for x in rr if x["dx_after"] is not None)
        out.append({"stop": key[0], "fit": key[1], "firings": len(rr),
                    "arrived": sum(1 for x in rr if x["outcome"] == "ARRIVED"),
                    "offs": sorted(set(x["off"] for x in rr)),
                    "dx_after": dx,
                    "dx_all_positive": bool(dx) and all(x > 0 for x in dx),
                    "dx_both_signs": bool(dx) and min(dx) < 0 < max(dx)})
    return out


def show(rows, manifest):
    print("%d journals, %d firings, window [%d, %d]"
          % (len(manifest), len(rows), TS_LO, TS_HI))
    print("  stop  fit          firings  arrived  offs        dx after the yaw")
    for t in tally(rows):
        # a label only where there is a population to have a sign: one
        # reading is not "all positive", it is one reading.
        sign = ("n < 2" if len(t["dx_after"]) < 2
                else "ALL POSITIVE" if t["dx_all_positive"]
                else "BOTH SIGNS" if t["dx_both_signs"] else "one sign")
        print("  %4d  %-12s %7d  %7d  %-11s %s  %s"
              % (t["stop"], t["fit"], t["firings"], t["arrived"],
                 ",".join("%+d" % o for o in t["offs"]),
                 "%+d..%+d" % (t["dx_after"][0], t["dx_after"][-1])
                 if t["dx_after"] else "-", sign))


def freeze():
    paths = journals(ROOT)
    manifest, rows = [], []
    for p in paths:
        raw, fs = firings(p)
        manifest.append({"journal": os.path.basename(p), "bytes": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()})
        rows.extend(fs)
    doc = {"what": "every STOP YAW firing in a closed, named population; see "
                   "patch46_yaw_census.py for how it is scored",
           "chain": CHAIN, "ts_window": [TS_LO, TS_HI],
           "credible_inliers": CREDIBLE, "rows_scored_after": AHEAD,
           "fit_tol": TOL, "journals": len(manifest), "firings": len(rows),
           "tally": tally(rows), "manifest": manifest, "rows": rows}
    with open(OUT, "w") as fh:
        json.dump(doc, fh, indent=1)
    show(rows, manifest)
    print("froze", OUT)


def recount():
    doc = json.load(open(OUT))
    rows, manifest = doc["rows"], doc["manifest"]
    show(rows, manifest)
    if tally(rows) != doc["tally"]:
        print("MISMATCH: the stored tally does not match the stored rows")
        return 1
    print("  the stored tally matches the stored rows")
    seen = 0
    for m in manifest:
        p = os.path.join(ROOT, "overnight", "chain_journals", m["journal"])
        if not os.path.exists(p):
            continue
        seen += 1
        raw = open(p, "rb").read()
        if hashlib.sha256(raw).hexdigest() != m["sha256"]:
            print("  DRIFT:", m["journal"], "has changed on disk since the freeze")
            return 1
    print("  %d of %d journals still on disk, every sha256 unchanged"
          % (seen, len(manifest)))
    live = [p for p in glob.glob(os.path.join(
        ROOT, "overnight", "chain_journals", "%s_t*.jsonl" % CHAIN))
        if int(os.path.basename(p).rsplit("_", 1)[1].split(".")[0]) > TS_HI]
    print("  (%d journals on disk are AFTER the window and are not the "
          "population)" % len(live))
    return 0


if __name__ == "__main__":
    sys.exit(freeze() if "freeze" in sys.argv[1:] else recount())
