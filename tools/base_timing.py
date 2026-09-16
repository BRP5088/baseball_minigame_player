"""How long does a runner take to go from base to base? Ask the archive.

THE QUESTION. A hit sets runners moving, and nothing on this project has ever
measured how long that takes -- agent_progress/HARVEST/play_timing.jsonl holds
ONE row and it is an out with nobody on. CLAUDE.md's deal-timing entry says the
dataset needs "matches WITH RUNNERS", and the 60 fps recordings have them.

THE INSTRUMENT. local_state.read_base answers "is this base occupied" per frame.
Watching all three across a play gives the exact frame each base flips, and the
gaps between flips ARE the baserunning time. No constant is invented anywhere:
the occupancy reader is the shipped one and its own gate decides.

TWO THINGS THAT WOULD MAKE THIS LIE, both guarded:

  * THE BASE CROPS LIE OFF A TURN SCREEN. On a ban grid they land on grid cards,
    and a grid card is a power disc with no diamond coin -- which is read_base's
    own `occupied` rule, so it reports runners that do not exist (368 ban frames,
    144 of 1104 base crops called OCCUPIED). Every frame here is gated on
    orchestrator.on_turn_screen first.
  * A FLICKER IS NOT A RUNNER. A single frame's change is read as an event only
    if the new state HOLDS -- the same discipline the deal-frame miner needed
    after its first three hits turned out to be 10.26 flicker.

Read-only. Operates on recordings already on disk; touches no console.
"""
import json
import os
import sys

import cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import orchestrator as o
import local_state as ls

BASES = ("third_base", "second_base", "first_base")
STRIDE = 12        # pass 1: 5 Hz on 60 fps
HOLD = 6           # frames a new state must hold to count as a real change
PRE_S, POST_S = 1.0, 12.0    # a full clearing of the bases is the longest animation


def _crops(bgr):
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    return dict(o.crop_gameplay_regions(im))


def _occ(crops, full=None):
    """(third, second, first) occupancy, or None when the diamond cannot be trusted.

    THE GATE CANNOT BE on_turn_screen, AND THAT WAS THE FIRST VERSION'S BUG. It
    asks whether the HAND reads, and during the very animation this exists to
    measure the hand is mid-deal and does not -- so the instrument went blind at
    exactly the moment of interest and reported flips from the frames either side
    of the gap.

    What the base crops actually need protecting from is the BAN GRID, where they
    land on grid cards and a card is a power disc with no diamond coin, which is
    read_base's own `occupied` rule (144 of 1104 crops called OCCUPIED over 368
    ban frames). The RESULT screen has no diamond either. Both have their own
    shipped detectors, so gate on those instead and let every turn-or-animation
    frame through.
    """
    if full is not None:
        try:
            if o.read_ban_counter(full) is not None:
                return None
            if ls.read_result(full).get("is_result"):
                return None
        except Exception:
            pass
    try:
        out = ls.read_runners(*[crops[b] for b in BASES])
    except Exception:
        return None
    b = out["bases"]
    return (b["third"]["occupied"], b["second"]["occupied"], b["first"]["occupied"])


def scan(path, stride=STRIDE):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    samples, i = [], 0
    while True:
        if not cap.grab():
            break
        if i % stride == 0:
            ok, fr = cap.retrieve()
            if ok:
                st = _occ(_crops(fr), Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
                if st is not None and None not in st:
                    samples.append((i, st))
        i += 1
    cap.release()
    return samples, fps, i


def events(samples, fps, gap_s=8.0):
    """Frames where occupancy changed and the new state HELD."""
    out = []
    for k in range(1, len(samples)):
        prev, cur = samples[k - 1][1], samples[k][1]
        if prev == cur:
            continue
        if not all(s[1] == cur for s in samples[k:k + 2]):
            continue                      # did not hold -> flicker
        idx = samples[k][0]
        if out and (idx - out[-1]["frame"]) / fps < gap_s:
            continue
        out.append({"frame": idx, "before": prev, "after": cur})
    return out


def time_event(path, centre, fps, outdir=None):
    """Every frame across one event; when did each base flip, and how far apart?"""
    lo, hi = max(0, int(centre - PRE_S * fps)), int(centre + POST_S * fps)
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, lo)
    seq = []
    for n in range(lo, hi):
        ok, fr = cap.read()
        if not ok:
            break
        st = _occ(_crops(fr), Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
        seq.append({"frame": n, "t": round((n - lo) / fps, 3), "occ": st})
    cap.release()
    # per-base flip times, taking only changes that HOLD
    flips = []
    for b, name in enumerate(("third", "second", "first")):
        last = None
        for j, s in enumerate(seq):
            if s["occ"] is None:
                continue
            v = s["occ"][b]
            if last is None:
                last = v
                continue
            # all([]) IS TRUE, and that is how a flip got accepted with NO
            # evidence behind it: mid-animation every frame in the hold window
            # read None, the comprehension filtered them all out, and the empty
            # `all` waved it through. The window must contain real observations.
            window = [x["occ"][b] for x in seq[j:j + HOLD] if x["occ"] is not None]
            if v != last and len(window) >= max(2, HOLD // 2) and all(w == v for w in window):
                flips.append({"base": name, "t": s["t"], "to": v})
                last = v
    flips.sort(key=lambda f: f["t"])
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "seq.json"), "w") as fh:
            json.dump({"seq": seq, "flips": flips}, fh)
    return seq, flips


if __name__ == "__main__":
    # SET INSIDE __main__, NEVER AT IMPORT. tests/harness/test_no_import_time_
    # test_run_flag.py AST-scans tools/ for exactly that, because an import-time
    # flag once silently disabled stick injection inside a LIVE harness. Here it
    # marks this process as offline analysis, so the readers do not write the
    # rig's hand_memory.json with a recording's cards.
    os.environ["BASEBALL_TEST_RUN"] = "1"
    path = sys.argv[1]
    outroot = sys.argv[2] if len(sys.argv) > 2 else "agent_progress/base-timing"
    cap_n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    samples, fps, total = scan(path)
    evs = events(samples, fps)
    name = os.path.basename(os.path.dirname(path))
    print(f"{name}: {total} frames at {fps:.0f} fps, {len(samples)} clean turn samples, "
          f"{len(evs)} occupancy events", flush=True)
    os.makedirs(outroot, exist_ok=True)
    rows = []
    for k, e in enumerate(evs[:cap_n]):
        d = os.path.join(outroot, f"ev_{e['frame']:07d}")
        seq, flips = time_event(path, e["frame"], fps, d)
        span = (flips[-1]["t"] - flips[0]["t"]) if len(flips) > 1 else None
        print(f"  event {k}: {e['before']} -> {e['after']}  flips="
              + ", ".join(f"{f['base']}{'+' if f['to'] else '-'}@{f['t']:.2f}s" for f in flips)
              + (f"   SPAN {span:.2f}s" if span is not None else "   (single flip)"),
              flush=True)
        rows.append({**e, "flips": flips, "span_s": span, "dir": d})
    with open(os.path.join(outroot, "index.json"), "w") as fh:
        json.dump({"video": path, "fps": fps, "events": len(evs), "timed": rows}, fh, indent=1)
