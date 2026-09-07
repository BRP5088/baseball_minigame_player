"""Offline go/no-go for the chain SENSOR: can it place a frame on a chain?

    .venv/bin/python -B tools/chain_validate.py <frames_dir> --out <file.json>
    .venv/bin/python -B tools/chain_validate.py <frames_dir> --hint closed --out ...

Builds a chain from every Nth frame of a recorded sequence, holds the rest out,
and walks the held-out frames IN ORDER, asking `chain.locate` to place each one.

TWO HINT MODES, AND THE DEFAULT IS AN ORACLE
--------------------------------------------
`--hint oracle` (the default) hands `locate` the previous TRUE chain index.
That is an ORACLE: it is NOT the prior the controller will have, and every
number produced under it must be quoted as "under an oracle hint". This
docstring claimed the opposite until 2026-09-07 -- "the same prior the
controller will have, because the controller always knows which waypoint it
last reached" -- and it is false in the way that matters: the SPEC's controller
sets its k from THIS SENSOR's own output (`if chain.reached(fix, k+1): k =
min(fix.k, k+window)`), so a placement error feeds back into the next window,
and once k leads or lags by more than the window the true position sits outside
[k-1, k+window] and `locate` cannot recover it by construction.

`--hint closed` replays the same frames under exactly that advance rule,
starting from k = 0, and additionally reports how often the true position fell
OUTSIDE the search window and where k finished. Measured by the skeptic on 200
held-out office-drive frames: abstentions 48 -> 111, true position outside the
window 4 -> 76, final k 28 of 49 instead of 49.

**Neither mode is a live prediction, and closed mode is the more honest of the
two rather than the true one.** A fixed-frame replay advances the WORLD one
frame per step whatever k does, whereas the live controller keeps pushing
toward the waypoint it believes it is at -- so a lagging k in a replay can
never be caught up, and live it can. What closed mode demonstrates is the
MECHANISM and its direction; the oracle mode is the sensor's ceiling.

WHAT IT REPORTS AND WHY EACH NUMBER IS THERE
--------------------------------------------
1. A HISTOGRAM of |estimated k - true k| in chain steps. This is the go/no-go
   for the whole closed-loop plan: if held-out frames cannot be placed within
   one chain step most of the time, the sensor cannot drive a servo loop and a
   clean negative is a real result (CLAUDE.md 10.2 -- measure, do not reason).
2. ABSTENTIONS, separately. `locate()` returning None is not a wrong answer and
   must never be averaged into one.
3. THE TWO POPULATIONS a MIN_INLIERS gate would have to separate:
      NEAR -- the best in-window inlier count on a held-out frame
      FAR  -- the best inlier count of the SAME frame against waypoints more
              than 2 chain steps outside its window
   CLAUDE.md 10.4: a threshold must sit BETWEEN two measured populations, never
   inside one. Four bugs on this project were exactly that shape, including the
   localiser's own MIN_MATCHES, where a genuine arrival scored 137 and an
   OUTDOOR STREET frame scored 135. `chain.MIN_INLIERS` stays None until these
   two populations are plotted and seen to separate. This tool measures them;
   it deliberately does NOT propose a value.
4. The same histogram for WALKING frames alone, where the drive meta or a
   demo's input.json says the left stick was out of the deadzone. Turning on
   the spot is the easy case (the scene shears but the camera does not move);
   walking is what the loop has to survive.

WHAT IT DOES NOT DO
-------------------
It never touches the console, never reads a bearing off a saved JPEG (CLAUDE.md
"SAVING A FRAME CAN MAKE THE COMPASS READ 90 DEGREES WRONG" -- headings come
from the recording's own live reads or are left None), and writes its JSON with
tmp + os.replace so an interrupted run cannot leave a half-file that reads like
a result.

CORPORA (both 5 frames apart at N=5, so a chain step is ~1 s of the drive):
    overnight/drives/20260906_172413_office   1064 frames 1920x1080, meta.json
    demos/walk3_full_20260828_050731           710 frames 1400x787,  input.json
"""

import argparse
import glob
import json
import math
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Left-stick magnitude above which a frame is called WALKING. This is a
# REPORTING split for the histogram only -- it sets no behaviour, gates no
# decision and becomes no constant in chain.py. 0.15 is above the recordings'
# resting noise (the drive's idle samples read |lx|,|ly| <= 0.03) and below the
# smallest magnitude section 6 measures a displacement for (0.25).
WALK_MAG = 0.15
# How far outside the window a "FAR" candidate must be, in chain steps.
FAR_GAP = 2
# How many FAR candidates to fit per held-out frame (spread over the chain).
FAR_SAMPLES = 8


# ------------------------------------------------------------------ corpora

def _t_from_name(path):
    """The recorded timestamp in `f_0054.32.jpg`, or None."""
    m = re.search(r"f_(\d+\.\d+)\.jpg$", os.path.basename(path))
    return float(m.group(1)) if m else None


def _sorted_frames(d):
    """Every jpg in `d`, ordered numerically by the digits in its name."""
    out = []
    for p in glob.glob(os.path.join(d, "*.jpg")):
        digits = re.findall(r"\d+", os.path.basename(p))
        out.append(((tuple(int(x) for x in digits), os.path.basename(p)), p))
    return [p for _, p in sorted(out)]


def _from_drive_meta(d, meta):
    """world_log/drive meta.json: {'frames': [{t, frame, bearing, stick}]}."""
    rows = []
    for i, f in enumerate(meta["frames"]):
        st = f.get("stick") or {}
        rows.append({"i": i,
                     "path": os.path.join(d, f["frame"]),
                     "t": f.get("t", 0.0),
                     "heading": f.get("bearing"),
                     "lx": st.get("lx"), "ly": st.get("ly")})
    return [r for r in rows if os.path.isfile(r["path"])]


def _from_input_json(d, samples):
    """demos/*/input.json: a ~50 Hz controller log, NOT one row per frame.

    Frames carry their own timestamp in the filename, so each frame takes the
    stick from the nearest sample in time. Headings stay None -- this corpus
    has no recorded compass read, and re-reading the saved JPEG for one is the
    single thing CLAUDE.md forbids outright.
    """
    ts = [s.get("t", 0.0) for s in samples]
    rows = []
    for i, p in enumerate(_sorted_frames(d)):
        t = _t_from_name(p)
        lx = ly = None
        if t is not None and ts:
            j = min(range(len(ts)), key=lambda n: abs(ts[n] - t))
            ax = samples[j].get("axes") or {}
            lx, ly = ax.get("lx"), ax.get("ly")
        rows.append({"i": i, "path": p, "t": t or float(i),
                     "heading": None, "lx": lx, "ly": ly})
    return rows


def _from_index_jsonl(d):
    """world_log / explore index.jsonl: one JSON object per frame."""
    rows = []
    with open(os.path.join(d, "index.jsonl")) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            name = r.get("frame") or r.get("file") or r.get("path") or ""
            p = name if os.path.isabs(name) else os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            st = r.get("stick") or {}
            rows.append({"i": i, "path": p, "t": r.get("t", float(i)),
                         "heading": r.get("bearing") or r.get("heading"),
                         "lx": st.get("lx"), "ly": st.get("ly")})
    return rows


def load_frames(d):
    """[{pos, i, path, t, heading, lx, ly}] in recorded order, for any corpus.

    Order comes from the meta when there is one, and from the digits in the
    filenames otherwise -- never from `glob`'s arbitrary order, which would
    silently scramble the chain and make every number below meaningless.

    `pos` IS THE ONLY GROUND TRUTH. It is the row's POSITION in this list,
    which is what `rows[::every]` selects on and therefore what a chain index
    means. `i` is the loader's own count and is NOT the position: three of the
    four loaders below can drop a row after numbering it (`_from_drive_meta`
    assigns `i` before filtering missing files; `_from_index_jsonl` counts
    lines including blank and unparseable ones, and skips missing files). This
    tool used `i / every` as the true position until 2026-09-07, which on
    `world_log/20260901_235855_anchor_calib` -- one of the SPEC's own corpora,
    where a leading blank line makes i == pos + 1 for every row -- put the
    WAYPOINT frames into the held-out set and scored them against a true
    position of 0.2, then printed a perfectly plausible go/no-go. The only
    visible symptom was two frame counts disagreeing in adjacent printed lines.
    `sweep()` now asserts the invariant instead of trusting it.
    """
    rows = None
    mj = os.path.join(d, "meta.json")
    if os.path.isfile(mj):
        meta = json.load(open(mj))
        if isinstance(meta, dict) and meta.get("frames"):
            rows = _from_drive_meta(d, meta)
    if rows is None:
        ij = os.path.join(d, "input.json")
        if os.path.isfile(ij):
            samples = json.load(open(ij))
            if isinstance(samples, list):
                rows = _from_input_json(d, samples)
    if rows is None and os.path.isfile(os.path.join(d, "index.jsonl")):
        rows = _from_index_jsonl(d) or None
    if rows is None:
        rows = [{"i": i, "path": p, "t": _t_from_name(p) or float(i),
                 "heading": None, "lx": None, "ly": None}
                for i, p in enumerate(_sorted_frames(d))]
    for pos, r in enumerate(rows):          # the ONLY ground truth (see above)
        r["pos"] = pos
    return rows


def is_walking(row):
    """True / False / None (unknown) from the recorded left stick."""
    lx, ly = row.get("lx"), row.get("ly")
    if lx is None and ly is None:
        return None
    return ((lx or 0.0) ** 2 + (ly or 0.0) ** 2) ** 0.5 >= WALK_MAG


# ------------------------------------------------------------------ the sweep

def _stats(xs):
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    n = len(s)

    def q(p):
        return s[min(n - 1, max(0, int(round(p * (n - 1)))))]
    return {"n": n, "min": s[0], "p05": q(0.05), "p25": q(0.25),
            "median": q(0.50), "mean": round(sum(s) / n, 2),
            "p75": q(0.75), "p95": q(0.95), "max": s[-1]}


def _hist(errs):
    h = {}
    for e in errs:
        key = str(e) if e < 5 else "5+"
        h[key] = h.get(key, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: (kv[0] == "5+", kv[0])))


def _within(errs, k):
    return 0.0 if not errs else round(sum(1 for e in errs if e <= k) / len(errs), 4)


HINT_MODES = ("oracle", "closed")


def sweep(d, every=5, window=3, far_samples=None, limit=None,
          start=0, hint_mode="oracle", log=print):
    """Build / hold out / place, and return the whole report as a dict.

    `far_samples=None` resolves to the module knob AT CALL TIME. Binding it in
    the signature (`far_samples=FAR_SAMPLES`) is 10.18's shape exactly -- the
    default is evaluated once when the `def` runs, so setting the module knob
    afterwards would change nothing and say nothing.

    `hint_mode`:
      "oracle" -- hint = the previous TRUE index. The sensor's ceiling; NOT
                  what the controller will have. Every headline taken from this
                  mode must carry the word ORACLE.
      "closed" -- hint = the k the SPEC's controller would be holding, advanced
                  only by this sensor's own answers:
                      if chain.reached(fix, k+1): k = min(fix.k, k + window)
                  A placement error therefore feeds back, which is the failure
                  the oracle cannot see. Read the module docstring for why the
                  magnitude is still not a live prediction.
    """
    import chain
    import places

    if hint_mode not in HINT_MODES:
        raise SystemExit(f"--hint must be one of {HINT_MODES}, got {hint_mode!r}")
    if far_samples is None:
        far_samples = FAR_SAMPLES

    rows = load_frames(d)
    if start or limit:
        # A SLICE of a recording is its own corpus: renumber
        # `pos` so it stays the position in what is actually
        # swept, which is what the chain is built from.
        rows = rows[start:None if not limit else start + limit]
        for n, r in enumerate(rows):
            r["pos"] = n
    if len(rows) < every * 3:
        raise SystemExit(f"{d}: only {len(rows)} frames -- nothing to hold out")

    # GROUND TRUTH IS THE POSITION, NOT THE LOADER'S COUNT (see load_frames).
    # The assertion is the guard: on a corpus where the loader dropped a row,
    # `i` and `pos` diverge silently and every number below becomes fiction.
    assert all(r["pos"] == n for n, r in enumerate(rows)), \
        "load_frames must number rows by position"
    renumbered = sum(1 for r in rows if r.get("i") != r["pos"])
    if renumbered:
        log(f"  [!] {renumbered} of {len(rows)} rows have a loader index that is "
            f"NOT their position -- the loader dropped or renumbered rows. "
            f"Ground truth uses the POSITION, so this is reported, not fatal.")

    chain_rows = rows[::every]
    chain_paths = {r["path"] for r in chain_rows}
    wps = []
    for pos, r in enumerate(chain_rows):
        kps, des = places.keypoints(r["path"], cache_key=r["path"])
        wps.append(chain.Waypoint(index=pos, heading=r["heading"],
                                  path=r["path"], t=r["t"],
                                  lx=r["lx"] or 0.0, ly=r["ly"] or 0.0,
                                  note=str(r["i"]), kps=kps, des=des))
    ch = chain.Chain(wps, root=d)

    held = [r for r in rows if r["pos"] % every != 0]
    # Two counts that must agree, and did not before 2026-09-07: the held-out
    # set is exactly the complement of the chain. When they disagreed, WAYPOINT
    # frames were being scored as held-out frames against a wrong true index.
    assert len(held) == len(rows) - len(chain_rows), (
        f"{len(held)} held out but frames - waypoints = "
        f"{len(rows) - len(chain_rows)}")
    assert not (chain_paths & {r["path"] for r in held}), \
        "a chain waypoint's own frame is in the held-out set"
    log(f"  chain: {len(ch)} waypoints from every {every}th of {len(rows)} "
        f"frames; {len(held)} held out; hint={hint_mode}")

    k_closed = 0                       # the controller's belief, closed mode
    outside = 0
    out_rows = []
    for r in held:
        true_f = r["pos"] / every                    # true position, in steps
        hint = int(true_f) if hint_mode == "oracle" else k_closed
        lo, hi = ch.window_bounds(hint, window)
        fix = ch.locate(r["path"], k_hint=hint, window=window)

        # Is the truth even reachable from this hint? A held-out frame sits
        # between floor(true) and ceil(true); if NEITHER is in the window the
        # sensor cannot be right, and no accuracy number means anything for
        # that row. Under the oracle this is 0 by construction.
        out_of_window = not (lo <= math.floor(true_f) <= hi
                             or lo <= math.ceil(true_f) <= hi)
        outside += 1 if out_of_window else 0

        far = None
        if far_samples:
            pool = [j for j in range(len(ch))
                    if j < lo - FAR_GAP or j > hi + FAR_GAP]
            if pool:
                step = max(1, len(pool) // far_samples)
                pick = pool[::step][:far_samples]
                kps, des = places.keypoints(r["path"])
                best = 0
                for j in pick:
                    w = ch.waypoints[j]
                    f = chain.match_fit(w.kps, w.des, kps, des)
                    if f and f["inliers"] > best:
                        best = f["inliers"]
                far = best

        out_rows.append({
            "pos": r["pos"], "i": r["i"], "true": round(true_f, 3),
            "hint": hint, "out_of_window": out_of_window,
            "walking": is_walking(r),
            "k": None if fix is None else fix.k,
            "k_float": None if fix is None else round(fix.k_float, 3),
            "inliers": None if fix is None else fix.inliers,
            "second": None if fix is None else fix.second,
            "dx": None if fix is None else round(fix.dx, 1),
            "scale": None if fix is None else round(fix.scale, 4),
            "far_inliers": far,
        })

        if hint_mode == "closed":
            # The SPEC's controller advance rule, and nothing else.
            if ch.reached(fix, k_closed + 1):
                k_closed = min(fix.k, k_closed + window)

    return _report(d, every, window, len(rows), len(ch), out_rows,
                   hint_mode=hint_mode, far_samples=far_samples,
                   start=start, limit=limit,
                   renumbered=renumbered, outside=outside,
                   final_k=k_closed if hint_mode == "closed" else None)


def _slice(rows, keep):
    sel = [r for r in rows if keep(r)]
    placed = [r for r in sel if r["k"] is not None]
    errs = [abs(r["k"] - int(r["true"] + 0.5)) for r in placed]
    # A held-out frame lies BETWEEN two waypoints, so "nearest" is a harsher
    # question than "in the right gap". Both are reported; the go/no-go quoted
    # in the report is the NEAREST one.
    brk = []
    for r in placed:
        lo, hi = int(r["true"]), int(r["true"]) + 1
        brk.append(0 if lo <= r["k"] <= hi else min(abs(r["k"] - lo),
                                                    abs(r["k"] - hi)))
    fl = [abs(r["k_float"] - r["true"]) for r in placed
          if r["k_float"] is not None]
    return {
        "frames": len(sel),
        "placed": len(placed),
        "abstained": len(sel) - len(placed),
        "abstain_rate": round((len(sel) - len(placed)) / len(sel), 4) if sel else None,
        "hist_nearest": _hist(errs),
        # within_* are over PLACED frames -- an abstention is not a wrong
        # answer and must not be averaged into one. within_*_all divides by
        # EVERY held-out frame instead, counting an abstention as "not placed
        # within k", which is the number a controller actually experiences.
        # Both are here on purpose: quoting only the first flatters the sensor
        # exactly as much as the abstention rate, and quoting only the second
        # hides whether the misses are wrong answers or refusals.
        "within_0": _within(errs, 0),
        "within_1": _within(errs, 1),
        "within_2": _within(errs, 2),
        "within_0_all": round(sum(1 for e in errs if e <= 0) / len(sel), 4) if sel else None,
        "within_1_all": round(sum(1 for e in errs if e <= 1) / len(sel), 4) if sel else None,
        "within_2_all": round(sum(1 for e in errs if e <= 2) / len(sel), 4) if sel else None,
        "hist_bracket": _hist(brk),
        "bracket_exact": _within(brk, 0),
        "k_float_abs_err": _stats([round(x, 3) for x in fl]),
        "inliers_best": _stats([r["inliers"] for r in placed]),
    }


def _report(d, every, window, n_frames, n_wp, rows, hint_mode="oracle",
            far_samples=None, renumbered=0, outside=0, final_k=None,
            start=0, limit=None):
    near = [r["inliers"] for r in rows if r["inliers"] is not None]
    far = [r["far_inliers"] for r in rows if r["far_inliers"] is not None]
    paired = [(r["inliers"], r["far_inliers"]) for r in rows
              if r["inliers"] is not None and r["far_inliers"] is not None]
    return {
        "dir": d, "every": every, "window": window,
        "frames": n_frames, "waypoints": n_wp, "held_out": len(rows),
        # The provenance of every number below. `hint_mode` especially: an
        # "oracle" report is the sensor's CEILING and must be quoted as such.
        # `far_samples` is recorded because the FAR population is the whole
        # basis of the MIN_INLIERS decision and its sample size was previously
        # unrecoverable from the artefact.
        "hint_mode": hint_mode,
        "hint_note": ("ORACLE HINT: every accuracy figure in this report was "
                      "measured with the previous TRUE index as the prior. "
                      "The controller's own k comes from this sensor, so this "
                      "is a ceiling, not a prediction."
                      if hint_mode == "oracle" else
                      "CLOSED-LOOP HINT: k advanced only by this sensor's own "
                      "answers (reached -> k = min(fix.k, k+window)). A "
                      "fixed-frame replay advances the world whatever k does, "
                      "so a lagging k can never be caught up here and it can "
                      "live -- the MECHANISM is what this demonstrates."),
        "far_samples": far_samples,
        "rows_renumbered_by_loader": renumbered,
        "true_outside_window": outside,
        "final_k": final_k,
        "start": start, "limit": limit,
        "walk_mag": WALK_MAG, "far_gap": FAR_GAP,
        "all": _slice(rows, lambda r: True),
        "walking": _slice(rows, lambda r: r["walking"] is True),
        "not_walking": _slice(rows, lambda r: r["walking"] is False),
        "walking_unknown": _slice(rows, lambda r: r["walking"] is None),
        "gate_populations": {
            "note": "NEAR = best in-window inliers on a held-out frame. "
                    "FAR = best inliers of the SAME frame against waypoints "
                    f"more than {FAR_GAP} chain steps outside its window. "
                    "A MIN_INLIERS gate must sit BETWEEN these two, and only "
                    "if they separate (CLAUDE.md 10.4). No value is proposed "
                    "here. NOTE both are CENSORED AT pose._MAX_MATCHES (200): "
                    "the fit keeps at most that many matches, so no inlier "
                    "count can exceed it and a median of 200 means 'at the "
                    "ceiling', not 'exactly 200'.",
            "near": _stats(near),
            "far": _stats(far),
            "far_ge_near": sum(1 for a, b in paired if b >= a),
            "paired": len(paired),
        },
        "rows": rows,
    }


def _summary(rep):
    L = []
    a, w = rep["all"], rep["walking"]
    L.append(f"{rep['dir']}  N={rep['every']}  window={rep['window']}  "
             f"{rep['frames']} frames -> {rep['waypoints']} waypoints, "
             f"{rep['held_out']} held out")
    L.append(f"  HINT = {rep['hint_mode'].upper()}  --  {rep['hint_note']}")
    if rep.get("rows_renumbered_by_loader"):
        L.append(f"  [!] {rep['rows_renumbered_by_loader']} rows had a loader "
                 f"index != their position (dropped/renumbered rows); ground "
                 f"truth is the POSITION")
    if rep["hint_mode"] == "closed":
        L.append(f"  closed loop: true position OUTSIDE the search window on "
                 f"{rep['true_outside_window']} of {rep['held_out']} frames; "
                 f"k finished at {rep['final_k']} of {rep['waypoints'] - 1}")
    for name in ("all", "walking", "not_walking", "walking_unknown"):
        s = rep[name]
        if not s["frames"]:
            continue
        L.append(f"  {name:16s} n={s['frames']:5d}  abstain={s['abstained']:4d} "
                 f"({(s['abstain_rate'] or 0) * 100:5.1f}%)  "
                 f"of PLACED: |err|=0 {s['within_0'] * 100:5.1f}%  "
                 f"<=1 {s['within_1'] * 100:5.1f}%  <=2 {s['within_2'] * 100:5.1f}%   "
                 f"hist {s['hist_nearest']}")
        L.append(f"  {'':16s} of ALL held out (abstention counts as a miss): "
                 f"|err|=0 {(s['within_0_all'] or 0) * 100:5.1f}%  "
                 f"<=1 {(s['within_1_all'] or 0) * 100:5.1f}%  "
                 f"<=2 {(s['within_2_all'] or 0) * 100:5.1f}%")
        L.append(f"  {'':16s} inliers median={s['inliers_best'].get('median')} "
                 f"mean={s['inliers_best'].get('mean')}  "
                 f"k_float |err| median={s['k_float_abs_err'].get('median')}")
    g = rep["gate_populations"]
    L.append(f"  GATE POPULATIONS  near {g['near']}")
    L.append(f"                    far  {g['far']}")
    overlap = (" -- the two populations OVERLAP, so no MIN_INLIERS gate "
               "separates them" if g["far_ge_near"] else
               " -- no overlap on paired frames")
    L.append(f"                    far >= near on {g['far_ge_near']} of "
             f"{g['paired']} paired frames{overlap}")
    if w["frames"]:
        who, pop = "walking frames", w
    else:
        who, pop = ("all held-out frames (no frame met the walking split)"
                    if rep["walking_unknown"]["frames"] == 0
                    else "all held-out frames (no stick data in this corpus)"), a
    # The headline carries its own provenance, so it cannot be quoted without
    # it: an ORACLE figure read as a controller figure is finding 2.
    L.append(f"  GO/NO-GO under the {rep['hint_mode'].upper()} hint "
             f"(|err| <= 1 on {who}): "
             f"{pop['within_1'] * 100:.1f}% of placed, "
             f"{(pop['within_1_all'] or 0) * 100:.1f}% of all held out "
             f"({pop['abstained']} abstentions of {pop['frames']})")
    return "\n".join(x for x in L if x)


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def main(argv=None):
    # The flag is set HERE, inside main(), never at import: an import-time set
    # switched stick injection off inside a LIVE harness and cost three runs
    # (CLAUDE.md section 5 / 10.1). This tool sends nothing either way; the
    # flag is belt and braces for anything it imports.
    os.environ.setdefault("BASEBALL_TEST_RUN", "1")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--every", type=int, default=5,
                    help="build the chain from every Nth frame (default 5)")
    ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--far-samples", type=int, default=None,
                    help=f"FAR candidates per frame (default {FAR_SAMPLES}); "
                         f"0 skips the FAR population (faster smoke tests)")
    ap.add_argument("--limit", type=int, default=None,
                    help="use only the first N frames (smoke test)")
    ap.add_argument("--start", type=int, default=0,
                    help="skip the first N frames, so a SLICE of a long "
                         "recording can be swept and reproduced exactly")
    ap.add_argument("--hint", choices=HINT_MODES, default="oracle",
                    help="oracle (default): hint = the previous TRUE index -- "
                         "the sensor's CEILING. closed: hint = the k the "
                         "controller would hold, advanced by this sensor's own "
                         "answers.")
    ap.add_argument("--out", default=None, help="JSON output path")
    args = ap.parse_args(argv)

    rep = sweep(args.dir, every=args.every, window=args.window,
                far_samples=args.far_samples, limit=args.limit,
                start=args.start, hint_mode=args.hint)
    print(_summary(rep))
    if args.out:
        _write(args.out, rep)
        print(f"  wrote {args.out}")
    return rep


if __name__ == "__main__":
    main()
