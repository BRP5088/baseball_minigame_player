"""CRAWL MODE: one action at a time, with a HUMAN label for what happened.

WHY THIS EXISTS. Nothing on this rig can tell, per push, whether the character
hit something. `slow_traverse.walk_leg` measures how far the view moved and
returns it -- and the closed loop calls it as a bare statement and DISCARDS the
value, which is CLAUDE.md 10.1's catalogued shape verbatim ("walk_forward
returns how far the view moved; both step loops threw it away, so walking into
an NPC looked like walking"). Mining it back out of the logs shows it carries
signal but cannot be calibrated: a push travelling under 5 px happens on 1.6% of
pushes in walks that ARRIVE and 10.9% in walks that FAIL (n = 4,969 / 384), and
"the walk failed" is not "this push was the collision". The label is at the
wrong resolution.

The user, watching the stream, proposed the fix: take one action, and they say
whether it hit a wall or the bar. That is the per-push ground truth no amount of
log mining can produce.

WHAT IT RECORDS PER STEP, so the labels can decide which signal separates:
  change        the frame delta walk_leg already computes, in the same units
  null_change   the SAME measurement with NO action -- the paired control
  delta_ratio   change / null_change. UNVALIDATED, see the citation note below.
  null_inliers  RANSAC inliers between the two NULL frames (nothing was sent)
  push_inliers  RANSAC inliers between the two PUSH frames
  inlier_ratio  push_inliers / null_inliers -- OPEN-1's signal, see below
  inliers/scale/k  the chain sensor's answer against the ROUTE, for context
  frame         the .jpg, so a disagreement can be adjudicated by eye

THE CITATION THIS FILE USED TO GET WRONG, and it mattered. An earlier version
computed only `change / null_change` and called it "the paired ratio CLAUDE.md's
OPEN-1 measured", quoting moved 0.10-0.34 / blocked 0.82 against it. That is the
wrong metric wearing another one's evidence. Read OPEN-1 again:

    frame delta   null 1 - 12      push 7 - 24      OVERLAP, unusable
    ORB inliers   null 353 - 1366  push 35 - 908    OVERLAP, unusable
    ... "PAIRED at the same heading, dividing the push's INLIER COUNT by that
    heading's own null: 0.10 0.11 0.26 0.30 0.34 | 0.82"

353 and 407 are INLIER COUNTS, not pixel deltas (whose absolute range there is
1-24). So the signal with the measured 0.49 gap is the paired ORB-INLIER ratio,
and OPEN-1 never tested a paired FRAME-DELTA ratio at all. Both are now
recorded, and `--report` judges each on THIS session's own labels:

  * `inlier_ratio` carries OPEN-1's prior evidence and reads HIGH when blocked.
  * `delta_ratio` carries NONE. It is a plausible untested substitute, kept
    because it is free once `change` and `null_change` are measured. If it
    separates here, that is a NEW result at this session's n, not a replication.

No threshold is written into this file for either one. "No threshold on this
quantity can separate these populations" is a legitimate result (10.4), and the
report prints the raw numbers and the misclassification count so a human can
tell one stray point from two overlapping distributions.

It writes one JSON line per step, with `label` left null. Label them afterwards
with --label, which is a separate step precisely so the numbers are recorded
BEFORE anyone knows the answer.

    .venv/bin/python -B tools/crawl.py --steps 12            # crawl and record
    .venv/bin/python -B tools/crawl.py --label '3,5=bar' '9=wall' '1,2,4=clean'
    .venv/bin/python -B tools/crawl.py --report             # do the signals separate?
    .venv/bin/python -B tools/crawl.py --selftest

It DRIVES THE CONSOLE, so it refuses while anything else is driving.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join("overnight", "crawl.jsonl")
FRAMES = os.path.join("overnight", "crawl_frames")

# The settle after the release, before the post-push capture. It is NOT a new
# constant -- it is the 0.35 that was already inline in the push sequence, named
# so the NULL window can be given the same wall-clock length (see crawl()).
SETTLE = 0.35

# The one label that means "nothing was hit". Everything else is a collision, so
# a typo in THIS word silently reclassifies a clean push -- hence the
# normalisation and the unknown-label warning in label().
CLEAN = "clean"
KNOWN_LABELS = (CLEAN, "bar", "wall", "npc", "furniture", "door", "stairs")

# The signals --report judges, in the order it prints them.
SIGNALS = ("change", "delta_ratio", "inlier_ratio")

# CLAUDE.md 10.3, measured ON THIS PROJECT: power to detect its own effect sizes
# is 0.00 at n=3, 0.72 at n=6, 0.94 at n=10. Three a side is the floor at which
# a verdict can be computed at all; below six it is announced as PROVISIONAL.
# These are quoted from that table, not chosen here.
MIN_PER_SIDE = 3
PROVISIONAL_BELOW = 6


def _pgrep(pattern):
    """PIDs whose full command line matches `pattern`, EXCLUDING this process.

    Self is excluded because the pattern is generic now: a guard that matches
    the process asking the question refuses every run, which is the
    cannot-fire shape inverted into always-fires.
    """
    out = subprocess.run(["pgrep", "-f", pattern],
                         capture_output=True, text=True).stdout
    me = os.getpid()
    return [int(p) for p in out.split() if p.isdigit() and int(p) != me]


def _cmdline(pid):
    return subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                          capture_output=True, text=True).stdout.strip()


# Every harness that drives this console lives in overnight/. Matching the
# DIRECTORY rather than a list of script names is deliberate: CLAUDE.md records
# that keep_awake was deleted with a hand-kept BUSY_PATTERNS list of seven names
# that matched no A/B harness, because "a guard whose trigger is a hand-kept
# list of NAMES rots silently -- nothing fails when a new name is missing".
# The previous version of this file was that same shape with a list of ONE.
LIVE_SCRIPT_PATTERN = r"overnight/[^ ]*\.py"


def _console_lock_holder():
    """console_lock's record of who declared they are driving, or None."""
    try:
        import console_lock
        return console_lock.holder()
    except Exception:
        return None


def console_driver(probe=_pgrep, lock=_console_lock_holder):
    """A sentence naming whoever is driving the console, or None.

    Two sources, in order of authority. `console_lock` is the project's own
    POSITIVE DECLARATION and is the general answer -- every overnight harness
    acquires it per trial. The pgrep is the backstop for anything that has not
    adopted the lock yet. Both are injected so the selftest can drive each arm.
    """
    rec = lock()
    if rec:
        return (f"console_lock: {rec.get('name')!r} (pid {rec.get('pid')}) has "
                f"declared it is driving")
    pids = probe(LIVE_SCRIPT_PATTERN)
    if pids:
        return "a live script is running -- " + "; ".join(
            f"pid {p} {_cmdline(p)}" for p in pids)
    return None


def harness_running(probe=_pgrep, lock=_console_lock_holder):
    """True if anything is driving the console. Injected so the selftest drives both."""
    return console_driver(probe, lock) is not None


def ratio(push, null):
    """push / null, the paired form -- None when the null is unusable.

    Paired because an ABSOLUTE reading cannot work: one heading's do-nothing
    null read 353 while another heading's real push read 407, so the same number
    means blocked in one place and moved in another (CLAUDE.md OPEN-1).
    Dividing by THIS spot's own null removes the scene, which is also what makes
    it robust to an NPC wandering through the shot.

    Used for BOTH ratios recorded here. Only the inlier one inherits OPEN-1's
    evidence; see the module docstring for why that distinction is load-bearing.
    """
    if push is None or null is None or null <= 0:
        return None
    return round(push / null, 3)


def pair_inliers(kps_a, des_a, kps_b, des_b):
    """RANSAC inliers between two LIVE frames -- the RAW count, never gated.

    This is OPEN-1's ingredient: how much of the scene still lines up after the
    push, against how much lined up when nothing was sent.

    DELIBERATELY NOT `chain.match_fit`, which returns None below
    `pose._MIN_INLIERS`. That gate means "do not believe this fix"; here a LOW
    count IS the answer we are looking for (the character moved), so gating it
    away would discard exactly the measurement this tool exists to take --
    CLAUDE.md 10.1's shape #4. Everything else (the Hamming filter, the RANSAC
    parameters) is chain's own, imported rather than restated.

    Note the count is capped by `pose._MAX_MATCHES`, so the blocked end
    saturates; the RATIO is still the quantity, and both sides are capped alike.

    None means UNMEASURABLE (too few surviving matches, or no fit) -- never
    "identical". Measured: identical frames 200, adjacent chain frames 137-152,
    unrelated 5, and a dark 22-keypoint pair does not fit at all.
    """
    import cv2
    import numpy as np
    import chain as chain_mod

    if des_a is None or des_b is None or kps_a is None or kps_b is None:
        return None
    ms = chain_mod.hamming_filtered(des_a, des_b)
    if len(ms) < chain_mod.MIN_MATCHES_TO_FIT:
        return None
    _, _, ransac_px = chain_mod._fit_params()
    src = np.float32([kps_a[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([kps_b[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    _, inl = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=ransac_px)
    return None if inl is None else int(inl.sum())


def _min_misclassified(h, c, clean_higher):
    """Fewest samples that must be set aside for a single threshold to split.

    0 means the two populations separate. 1 means ONE stray point is the whole
    story -- a light brush the human still called clean, an NPC crossing the
    shot -- and the answer is to open that frame, not to abandon the signal. A
    min/max gap alone cannot tell those apart, which is how a well-separated
    quantity gets reported as unusable (10.4 asks for the distribution, and this
    is the distribution's one-number summary).

    No threshold is invented: the candidates are the session's own values.
    """
    best = None
    for t in sorted(set(h) | set(c)) + [float("inf")]:
        if clean_higher:
            err = sum(1 for x in h if x >= t) + sum(1 for x in c if x < t)
        else:
            err = sum(1 for x in c if x >= t) + sum(1 for x in h if x < t)
        best = err if best is None else min(best, err)
    return best


def summarise(rows):
    """-> (labelled rows, per-signal stats).

    A signal separates if a single threshold splits the two labelled
    populations, IN EITHER DIRECTION. Checking one direction only was a real
    defect: OPEN-1's own inlier ratio reads LOW when the character moved and
    HIGH when it was blocked, so a perfect separator of exactly the shape this
    tool is built to find was being reported as OVERLAPS.
    """
    import statistics as st
    lab = [r for r in rows if r.get("label")]
    hit = [r for r in lab if r["label"] != CLEAN]
    clean = [r for r in lab if r["label"] == CLEAN]
    out = {}
    for name in SIGNALS:
        h = sorted(r[name] for r in hit if r.get(name) is not None)
        c = sorted(r[name] for r in clean if r.get(name) is not None)
        if len(h) < MIN_PER_SIDE or len(c) < MIN_PER_SIDE:
            out[name] = None
            continue
        gap_clean_higher = min(c) - max(h)
        gap_hit_higher = min(h) - max(c)
        clean_higher = gap_clean_higher >= gap_hit_higher
        gap = gap_clean_higher if clean_higher else gap_hit_higher
        out[name] = {
            "hit_n": len(h), "clean_n": len(c),
            "hit_median": st.median(h), "clean_median": st.median(c),
            "hit_min": min(h), "hit_max": max(h),
            "clean_min": min(c), "clean_max": max(c),
            "direction": "clean_higher" if clean_higher else "hit_higher",
            "separates": gap > 0,
            "gap": round(gap, 3),
            "misclassified": _min_misclassified(h, c, clean_higher),
            "provisional": min(len(h), len(c)) < PROVISIONAL_BELOW,
        }
    return lab, out


def _load(path):
    """Rows, or a one-line refusal. Never a raw traceback at someone mid-session."""
    try:
        with open(path) as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except FileNotFoundError:
        raise SystemExit(f"no crawl recorded yet ({path} does not exist) -- "
                         f"run  --steps N  first")


def _duplicate_steps(rows):
    seen, dupes = set(), []
    for r in rows:
        s = r.get("step")
        if s in seen and s not in dupes:
            dupes.append(s)
        seen.add(s)
    return dupes


def _atomic_write(path, rows):
    """Rewrite the file via a temp file + os.replace, so a kill cannot truncate it.

    crawl() appends and flushes per row precisely so a killed crawl keeps its
    rows; label() used to open the SAME file with mode "w" and rewrite it in a
    loop, which truncates first and loses everything after the interruption
    point -- the instrument numbers, not just the labels. Demonstrated: an
    interruption at row 7 of 12 left 6 rows on disk. Same discipline, both
    halves.
    """
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def report(path=OUT):
    rows = _load(path)
    lab, out = summarise(rows)
    dupes = _duplicate_steps(rows)
    steps = len({r.get("step") for r in rows})
    print(f"{len(rows)} rows, {steps} distinct steps, {len(lab)} labelled")
    if dupes:
        print(f"  !! DUPLICATE step numbers {dupes} -- rows from more than one "
              f"run share a step number, so a label cannot be aimed at one of "
              f"them. They were recorded before step numbers were made unique.")
    if not lab:
        print("  nothing labelled yet -- run --label first")
        return
    from collections import Counter
    counts = Counter(r["label"] for r in lab)
    print("  labels:", dict(counts))
    unknown = [k for k in counts if k not in KNOWN_LABELS]
    if unknown:
        print(f"  !! labels not in the known set {list(KNOWN_LABELS)}: "
              f"{unknown} -- each is counted as a COLLISION. If one of those is "
              f"a typo for {CLEAN!r}, this verdict is wrong.")
    for name in SIGNALS:
        s = out.get(name)
        if s is None:
            print(f"  {name}: too few labelled samples on one side to judge "
                  f"(need {MIN_PER_SIDE} of each)")
            continue
        if s["separates"]:
            verdict = (f"SEPARATES, {s['direction']} (gap {s['gap']})")
        else:
            verdict = (f"OVERLAPS (gap {s['gap']}); the best single threshold "
                       f"still misclassifies {s['misclassified']} of "
                       f"{s['hit_n'] + s['clean_n']}")
        print(f"  {name}: hit n={s['hit_n']} median {s['hit_median']:.2f} "
              f"[{s['hit_min']:.2f}..{s['hit_max']:.2f}] | clean n={s['clean_n']} "
              f"median {s['clean_median']:.2f} "
              f"[{s['clean_min']:.2f}..{s['clean_max']:.2f}]  -> {verdict}")
        if s["provisional"]:
            print(f"     PROVISIONAL: fewer than {PROVISIONAL_BELOW} a side. "
                  f"CLAUDE.md 10.3 measured this project's own power at 0.00 "
                  f"(n=3), 0.72 (n=6), 0.94 (n=10).")
        if s["separates"] and s["misclassified"] == 0 and s["gap"] > 0:
            pass
        elif not s["separates"] and s["misclassified"] == 1:
            print("     ONE stray sample accounts for the whole overlap -- open "
                  "that step's frame before abandoning this signal.")
    print("\n  A threshold is only usable if it sits BETWEEN the two, with a "
          "gap.\n  Four bugs on this project came from cutting through ONE "
          "population (10.4).\n  Only inlier_ratio carries prior evidence "
          "(OPEN-1); delta_ratio is untested.")


def _split_spec(spec):
    """['3,5=bar 9=wall'] -> ['3,5=bar', '9=wall'].

    A shell-quoted spec with spaces in it -- which is what this tool's own
    documentation and its end-of-run hint both show -- arrives as ONE argv token
    under nargs='+'. partition("=") then splits at the FIRST '=' only, so
    everything after it became one mangled label applied to the first group and
    every other step stayed unlabelled, with no error and a "labelled 2 step(s)"
    that reads like success. Splitting on whitespace accepts both forms.

    Consequence, stated because it is the trade: a label may not contain a
    space. 'bar stool' is refused loudly by the steps=label check below.
    """
    return [p for tok in spec for p in tok.split()]


def _parse_steps(steps, part):
    out = []
    for s in steps.split(","):
        s = s.strip()
        if not s:
            raise SystemExit(f"empty step number in {part!r} -- a stray comma? "
                             f"expected e.g. 1,2,4={CLEAN}")
        try:
            out.append(int(s))
        except ValueError:
            raise SystemExit(f"{s!r} in {part!r} is not a step number")
    return out


def label(spec, path=OUT):
    """Apply labels to recorded steps: --label '3,5=bar' '9=wall' '1,2,4=clean'

    Also accepts one quoted string holding all three. Step numbers are the ones
    --steps printed; they are unique across runs.
    """
    rows = _load(path)
    dupes = _duplicate_steps(rows)
    by_step = {r["step"]: r for r in rows}
    chosen = {}                       # step -> label decided in THIS call
    for part in _split_spec(spec):
        steps, sep, name = part.partition("=")
        name = name.strip().lower()   # 'Clean' and ' clean ' must not become collisions
        if not sep or not name or not steps.strip():
            raise SystemExit(f"expected steps=label, got {part!r}")
        for s in _parse_steps(steps, part):
            if s in dupes:
                raise SystemExit(
                    f"step {s} appears more than once in {path} -- there is no "
                    f"way to know which row you mean. Split the file by run "
                    f"before labelling.")
            r = by_step.get(s)
            if r is None:
                raise SystemExit(f"no step {s} recorded")
            # A conflict is a RECALL error mid-session ("was it 3 or 4?"), and
            # last-write-wins turns it into silently wrong ground truth under a
            # success message. Refuse instead; nothing is written yet.
            if s in chosen and chosen[s] != name:
                raise SystemExit(
                    f"step {s} is given two different labels in one command: "
                    f"{chosen[s]!r} and {name!r}. Decide which, then re-run.")
            was = r.get("label")
            if was and was != name:
                raise SystemExit(
                    f"step {s} is already labelled {was!r} on disk and this "
                    f"would change it to {name!r}. If that is deliberate, edit "
                    f"{path} by hand -- a silent overwrite of a human label is "
                    f"exactly what this tool must not do.")
            chosen[s] = name
            r["label"] = name
    _atomic_write(path, rows)
    unknown = sorted({n for n in chosen.values() if n not in KNOWN_LABELS})
    print(f"labelled {len(chosen)} distinct step(s)")
    if unknown:
        print(f"  !! {unknown} not in the known set {list(KNOWN_LABELS)}. Each "
              f"is counted as a COLLISION. If one is a typo for {CLEAN!r}, the "
              f"report's verdict will be wrong.")
    todo = sorted(r["step"] for r in rows if not r.get("label"))
    if todo:
        print(f"  still unlabelled: {todo}")
    else:
        print("  every recorded step is labelled")


def crawl(steps, mag, sec, chain_name):
    import numpy as np
    import analog_replay as ar
    import compass
    import chain as chain_mod
    import places
    import walk_steps as ws

    run_id = time.strftime("%Y%m%d_%H%M%S")
    # Frames are namespaced by run and step numbers CONTINUE across runs. Both
    # halves matter: a second crawl used to write step001.jpg over the first
    # run's step001.jpg while both runs' rows survived in the jsonl, so old rows
    # pointed at the wrong picture -- and --label, keying rows by step number,
    # silently attached the human's label to whichever row came last.
    frame_dir = os.path.join(FRAMES, run_id)
    os.makedirs(frame_dir, exist_ok=True)
    existing = _load(OUT) if os.path.exists(OUT) else []
    first = max([r.get("step", 0) for r in existing], default=0) + 1

    ch = chain_mod.Chain.load(os.path.join("chains", chain_name),
                              log=lambda *a: None)

    def grey():
        im = compass.fast_capture()
        return im, np.asarray(im.convert("L"), dtype=float)

    def delta(a, b):
        return float(np.abs(b - a).mean())

    prev_k = 1
    with open(OUT, "a") as fh:
        for i in range(first, first + steps):
            print(f"  step {i:3d}  measuring the null ...", flush=True)
            # THE PAIRED NULL FIRST: the same measurement with nothing sent, so
            # this spot's own scene animation is divided out.
            #
            # THE TWO WINDOWS MUST SPAN THE SAME WALL-CLOCK TIME. The push
            # window is sec + SETTLE (the settle after the release); the null
            # was only sec, so it sampled ~0.35s less ambient drift on every
            # step and `change` was inflated against `null_change` even for a
            # push that moved nothing -- a bias toward "moved", which is the
            # direction that erodes the separation this tool measures. Pairing
            # only cancels the scene if both halves watch it for equally long.
            a0_im, a0 = grey()
            time.sleep(sec)
            time.sleep(SETTLE)
            a1_im, a1 = grey()
            null = delta(a0, a1)

            im0, b0 = grey()
            try:
                ar.send([f"left_x 0", f"left_y {ar.to_axis(-abs(mag))}",
                         "right_x 0", "right_y 0"])
                time.sleep(sec)
            finally:
                # A Ctrl-C inside that sleep used to skip the release and leave
                # the stick deflected until chiaki's own 5s runaway timeout.
                ar.send(["left_x 0", "left_y 0"])
            time.sleep(SETTLE)
            im1, b1 = grey()
            change = delta(b0, b1)

            # OPEN-1's own signal: the two frames of each window matched against
            # EACH OTHER, not against the route. The chain fix below answers a
            # different question ("where am I on the chain") and cannot stand in
            # for this one.
            ka0, da0 = places.keypoints(a0_im)
            ka1, da1 = places.keypoints(a1_im)
            kb0, db0 = places.keypoints(im0)
            kb1, db1 = places.keypoints(im1)
            null_inl = pair_inliers(ka0, da0, ka1, da1)
            push_inl = pair_inliers(kb0, db0, kb1, db1)

            fix = ch.locate(im1, prev_k, window=6)
            if fix is not None:
                prev_k = fix.k
            frame = os.path.join(frame_dir, f"step{i:03d}.jpg")
            im1.save(frame, quality=85)
            row = {"run": run_id, "step": i, "change": round(change, 2),
                   "null_change": round(null, 2),
                   "delta_ratio": ratio(change, null),
                   "null_inliers": null_inl, "push_inliers": push_inl,
                   "inlier_ratio": ratio(push_inl, null_inl),
                   "inliers": None if fix is None else fix.inliers,
                   "k": None if fix is None else fix.k,
                   "scale": None if fix is None else round(float(fix.scale), 2),
                   "heading": ws.read_heading(), "frame": frame, "label": None}
            fh.write(json.dumps(row) + "\n")
            fh.flush()          # written AS IT GOES: a killed crawl keeps its rows
            print(f"  step {i:3d}  change {change:6.1f}  null {null:5.1f}  "
                  f"delta_ratio {row['delta_ratio']}  inliers "
                  f"{push_inl}/{null_inl} -> {row['inlier_ratio']}  "
                  f"k {row['k']}  scale {row['scale']}", flush=True)
    last = first + steps - 1
    print(f"\n{steps} steps ({first}..{last}) -> {OUT}. Now say which hit "
          f"something, e.g.\n"
          f"  .venv/bin/python -B tools/crawl.py --label '{first},{first + 2}=bar' "
          f"'{first + 1}=wall'\n"
          f"and label the rest {CLEAN}. Then --report.", flush=True)


def _synthetic_frames():
    """Two deterministic images: one, and the same one shifted 220px.

    Built here rather than loaded so the selftest has no fixture dependency and
    cannot silently skip. It exercises the REAL cv2/ORB path.
    """
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(7)
    a = np.zeros((1080, 1920), np.uint8)
    for _ in range(400):
        x, y = int(rng.integers(0, 1800)), int(rng.integers(0, 1000))
        w, h = (int(v) for v in rng.integers(8, 60, 2))
        a[y:y + h, x:x + w] = int(rng.integers(60, 255))
    return (Image.fromarray(a).convert("RGB"),
            Image.fromarray(np.roll(a, -220, axis=1)).convert("RGB"))


def _crawl_smoke(tmp):
    """Run the REAL crawl() loop with only the console stubbed out.

    The loop's own rules -- the two measurement windows spanning the same
    wall-clock time, the release firing even when the push is interrupted, step
    numbers continuing across runs, frames namespaced per run -- are not
    checkable by reading the source, and every one of them was a defect. So they
    are exercised here against a fake capture, with the ORB pair REAL.

    Returns (sleeps, sends, rows) from one ordinary step.
    """
    import types
    import numpy as np
    from PIL import Image
    import compass
    import chain as chain_mod
    import places
    import walk_steps as ws

    rng = np.random.default_rng(3)
    base = np.zeros((720, 1280), np.uint8)
    for _ in range(300):
        x, y = int(rng.integers(0, 1200)), int(rng.integers(0, 650))
        w, h = (int(v) for v in rng.integers(8, 50, 2))
        base[y:y + h, x:x + w] = int(rng.integers(60, 255))
    state = {"shift": 0}

    def capture():
        a = np.roll(base, -state["shift"], axis=1)
        return Image.fromarray(a).convert("RGB")

    sleeps, sends = [], []
    fake_ar = types.ModuleType("analog_replay")
    fake_ar.to_axis = lambda m: int(m * 32767)
    fake_ar.send = lambda lines: sends.append(list(lines))

    class _NoFix:
        def locate(self, im, k, window=6):
            return None

    saved = {"cwd": os.getcwd(), "cap": compass.fast_capture,
             "head": ws.read_heading, "load": chain_mod.Chain.load,
             "sleep": time.sleep, "ar": sys.modules.get("analog_replay")}
    raised = []
    try:
        os.chdir(tmp)
        os.makedirs("overnight", exist_ok=True)
        compass.fast_capture = capture
        ws.read_heading = lambda: 87.0
        chain_mod.Chain.load = staticmethod(lambda *a, **k: _NoFix())
        sys.modules["analog_replay"] = fake_ar

        def rec(sec):
            sleeps.append(round(sec, 4))
        time.sleep = rec
        crawl(1, 0.45, 0.40, "unused")
        crawl(1, 0.45, 0.40, "unused")      # a SECOND run, into the same file

        # and now a push interrupted mid-hold: the release must still fire
        n = len(sends)
        def boom(sec):
            sleeps.append(round(sec, 4))
            if len(sends) > n:              # the push has been sent
                raise KeyboardInterrupt
        time.sleep = boom
        try:
            crawl(1, 0.45, 0.40, "unused")
        except KeyboardInterrupt:
            raised.append(True)
        rows = [json.loads(l) for l in open(OUT)]
    finally:
        time.sleep = saved["sleep"]
        compass.fast_capture = saved["cap"]
        ws.read_heading = saved["head"]
        chain_mod.Chain.load = saved["load"]
        if saved["ar"] is None:
            sys.modules.pop("analog_replay", None)
        else:
            sys.modules["analog_replay"] = saved["ar"]
        os.chdir(saved["cwd"])
    return sleeps, sends, rows, raised


def selftest():
    import tempfile

    # ---- the console guard: both sources, both arms, and NOT a name list
    assert harness_running(lambda p: [], lambda: {"name": "x", "pid": 1}) is True
    assert harness_running(lambda p: [7], lambda: None) is True
    assert harness_running(lambda p: [], lambda: None) is False
    seen = []
    harness_running(lambda p: seen.append(p) or [], lambda: None)
    assert len(seen) == 1, seen
    # the pattern must be GENERIC -- a hand-kept list of names rots silently,
    # which is why keep_awake was deleted. Any overnight harness must match.
    for name in ("overnight/chain_trials.py", "overnight/ab_goal_leg.py",
                 "overnight/streak_table.py", "overnight/prompt_zone.py"):
        assert re.search(seen[0], name), (seen[0], name)
    assert not re.search(seen[0], "tools/dashboard.py"), seen[0]
    assert console_driver(lambda p: [], lambda: None) is None
    assert "console_lock" in console_driver(
        lambda p: [], lambda: {"name": "ab", "pid": 2})

    # ---- the paired ratio
    assert ratio(10.0, 20.0) == 0.5
    assert ratio(10.0, 0) is None and ratio(10.0, None) is None
    assert ratio(None, 20.0) is None          # an unmeasurable push, not a 0

    # ---- OPEN-1's ingredient really is computed, and in the right direction
    import places
    im, shifted = _synthetic_frames()
    k0, d0 = places.keypoints(im)
    k1, d1 = places.keypoints(shifted)
    same = pair_inliers(k0, d0, k0, d0)
    moved = pair_inliers(k0, d0, k1, d1)
    assert same is not None and moved is not None, (same, moved)
    assert same > moved, (same, moved)        # nothing moved -> MORE agreement
    assert pair_inliers(k0, None, k1, d1) is None
    assert pair_inliers(k0, d0[:2], k1, d1) is None   # too few to fit

    # ---- separation, in BOTH directions
    def rows(label, **kw):
        return [dict(label=label, **kw) for _ in range(3)]
    hit = rows("bar", change=2.0, delta_ratio=0.1, inlier_ratio=0.9)
    clean = rows(CLEAN, change=20.0, delta_ratio=0.9, inlier_ratio=0.2)
    lab, out = summarise(hit + clean)
    assert len(lab) == 6
    assert out["change"]["separates"] is True
    assert out["change"]["direction"] == "clean_higher"
    # the reversed shape -- OPEN-1's OWN inlier ratio reads HIGH when blocked --
    # must be reported as separating, not as overlapping
    assert out["inlier_ratio"]["separates"] is True, out["inlier_ratio"]
    assert out["inlier_ratio"]["direction"] == "hit_higher"
    assert out["inlier_ratio"]["misclassified"] == 0
    # ... and GENUINELY overlapping populations (interleaved, so neither
    # direction splits them) must NOT be reported as separating. The fixture
    # this replaces was hit=25 against clean=20 -- which is a PERFECT separator
    # running the other way, and the old one-directional test called it an
    # overlap. The bug was in the check as well as in the code.
    inter = ([{"label": "bar", "change": v} for v in (2.0, 25.0, 12.0)]
             + [{"label": CLEAN, "change": v} for v in (20.0, 3.0, 18.0)])
    _, out2 = summarise(inter)
    assert out2["change"]["separates"] is False, out2["change"]
    assert out2["change"]["misclassified"] > 1, out2["change"]
    # one stray point is distinguishable from two overlapping populations
    stray = ([{"label": "bar", "change": v} for v in (1.0, 2.0, 3.0)]
             + [{"label": CLEAN, "change": v} for v in (20.0, 21.0, 2.5)])
    _, out3 = summarise(stray)
    assert out3["change"]["separates"] is False
    assert out3["change"]["misclassified"] == 1, out3["change"]
    # too few on one side is "cannot judge", never "separates"
    _, out4 = summarise(hit + clean[:1])
    assert out4["change"] is None
    # n below the project's own power floor is announced
    assert out["change"]["provisional"] is True
    big = (rows(CLEAN, change=20.0) * 3) + (rows("bar", change=2.0) * 3)
    _, out5 = summarise(big)
    assert out5["change"]["provisional"] is False

    # ---- the spec parser: the documented quoted form must not drop labels
    assert _split_spec(["3,5=bar 9=wall"]) == ["3,5=bar", "9=wall"]
    assert _split_spec(["3=bar", "9=wall"]) == ["3=bar", "9=wall"]

    # ---- label(), end to end on a temp file
    d = tempfile.mkdtemp()
    p = os.path.join(d, "crawl.jsonl")
    def write(n):
        with open(p, "w") as fh:
            for i in range(1, n + 1):
                fh.write(json.dumps({"step": i, "change": float(i),
                                     "label": None}) + "\n")
    def read():
        return [json.loads(l) for l in open(p)]

    write(9)
    label(["3,5=bar 9=wall"], p)                 # the docstring's own example
    got = {r["step"]: r["label"] for r in read()}
    assert got[3] == "bar" and got[5] == "bar" and got[9] == "wall", got
    assert got[1] is None
    label(["1,2,4=Clean"], p)                    # normalised, not a collision
    assert {r["step"]: r["label"] for r in read()}[4] == CLEAN

    write(5)                                     # a conflict within one command
    try:
        label(["2,3=bar", "3,4=wall"], p)
    except SystemExit as e:
        assert "two different labels" in str(e), e
    else:
        raise AssertionError("a conflicting label was accepted")
    assert all(r["label"] is None for r in read()), "wrote despite the conflict"

    write(5)                                     # a conflict against disk
    label(["2=bar"], p)
    try:
        label(["2=wall"], p)
    except SystemExit as e:
        assert "already labelled" in str(e), e
    else:
        raise AssertionError("a label was silently overwritten")
    assert {r["step"]: r["label"] for r in read()}[2] == "bar"

    write(5)                                     # a stray comma, not a traceback
    for bad, want in ((["1,2,=clean"], "stray comma"),
                      (["=clean"], "steps=label"),
                      (["9=bar"], "no step 9")):
        try:
            label(bad, p)
        except SystemExit as e:
            assert want in str(e), (bad, str(e))
        else:
            raise AssertionError(f"{bad} was accepted")

    # duplicate step numbers are refused, not silently aimed at the last row
    with open(p, "w") as fh:
        for s in (1, 2, 1):
            fh.write(json.dumps({"step": s, "change": 1.0, "label": None}) + "\n")
    assert _duplicate_steps(read()) == [1]
    try:
        label(["1=bar"], p)
    except SystemExit as e:
        assert "more than once" in str(e), e
    else:
        raise AssertionError("a label was aimed at a duplicated step")

    # a missing file is a sentence, not a traceback
    try:
        _load(os.path.join(d, "nope.jsonl"))
    except SystemExit as e:
        assert "no crawl recorded yet" in str(e), e
    else:
        raise AssertionError("a missing file did not refuse cleanly")

    # the rewrite is atomic: a kill mid-write cannot truncate the real file
    write(6)
    before = open(p).read()
    real_dumps = json.dumps
    def boom(o, *a, **k):
        if o.get("step") == 4:
            raise KeyboardInterrupt
        return real_dumps(o, *a, **k)
    json.dumps = boom
    try:
        label(["1=bar"], p)
    except KeyboardInterrupt:
        pass
    finally:
        json.dumps = real_dumps
    assert open(p).read() == before, "the file was truncated by a killed label()"

    # ---- the crawl loop itself, with only the console stubbed
    tmp = tempfile.mkdtemp()
    sleeps, sends, crows, raised = _crawl_smoke(tmp)
    # THE TWO WINDOWS MUST SPAN THE SAME WALL CLOCK. A step sleeps
    # [sec, SETTLE] for the null and [sec, SETTLE] for the push; the null used
    # to be `sec` alone, so it sampled less ambient drift and `change` was
    # inflated against `null_change` on every step.
    assert sleeps[:4] == [0.4, SETTLE, 0.4, SETTLE], sleeps[:4]
    assert sum(sleeps[:2]) == sum(sleeps[2:4]), sleeps[:4]
    assert raised == [True], "the interrupted push did not propagate"
    # the release fires even though the hold was interrupted
    assert sends[-1] == ["left_x 0", "left_y 0"], sends[-1]
    # step numbers CONTINUE across runs, so a label can name one row -- and the
    # interrupted third step wrote NO row, because the row is written only once
    # the step is complete
    assert [r["step"] for r in crows] == [1, 2], [r["step"] for r in crows]
    assert len({r["frame"] for r in crows}) == 2
    assert all(r["frame"].startswith(os.path.join(FRAMES, r["run"]))
               for r in crows), [r["frame"] for r in crows]
    assert all(os.path.exists(os.path.join(tmp, r["frame"])) for r in crows)
    # OPEN-1's ingredient is RECORDED, not computed and dropped
    r0 = crows[0]
    assert isinstance(r0["null_inliers"], int) and isinstance(r0["push_inliers"], int)
    assert r0["inlier_ratio"] == ratio(r0["push_inliers"], r0["null_inliers"])
    assert r0["delta_ratio"] == ratio(r0["change"], r0["null_change"])

    print("selftest OK: the console guard (lock + generic pattern, both arms), "
          "the paired ratio, OPEN-1's inlier pair and its direction, separation "
          "in BOTH directions, the stray-point count, the power caveat, the "
          "quoted --label spec, conflicts, duplicates, bad specs, and the "
          "atomic rewrite")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Crawl mode: one push at a time, recorded, then labelled by "
                    "a human watching the stream.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--steps", type=int, default=12,
                    help="how many single pushes to take and record")
    ap.add_argument("--mag", type=float, default=0.45,
                    help="left-stick magnitude for each push")
    ap.add_argument("--sec", type=float, default=0.40,
                    help="seconds to hold the stick; the null window is given "
                         "the same total length")
    ap.add_argument("--chain", default="route_user_1853",
                    help="chain under chains/ for the sensor's context fix")
    ap.add_argument("--label", nargs="+", metavar="STEPS=LABEL",
                    help="attach human labels to recorded steps, e.g. "
                         "--label '3,5=bar' '9=wall' '1,2,4=clean' (one quoted "
                         "string holding all three also works). Labels may not "
                         "contain spaces; anything but 'clean' counts as a "
                         "collision.")
    ap.add_argument("--report", action="store_true",
                    help="does any recorded signal separate the labelled "
                         "populations?")
    ap.add_argument("--selftest", action="store_true",
                    help="run the offline checks; drives nothing")
    a = ap.parse_args()
    if a.selftest:
        selftest(); raise SystemExit(0)
    if a.report:
        report(); raise SystemExit(0)
    if a.label:
        label(a.label); raise SystemExit(0)
    who = console_driver()
    if who:
        raise SystemExit(f"REFUSING: {who}. Crawl mode DRIVES THE STICK and "
                         f"would fight it.")
    crawl(a.steps, a.mag, a.sec, a.chain)
