"""Find DEALS in a recorded stream and dump every frame of each one.

WHY THIS EXISTS. The hail mary recovers an occluded card only if that card
appeared UNOCCLUDED in an earlier hand (orchestrator._hail_mary_card's own
stated limit). A card dealt STRAIGHT INTO occlusion -- its disc landing under
the lifted neighbour -- can therefore never be recovered, and one cost a live
turn on 2026-09-15: the incoming 8 scored 0.593 and the best card in the hand
was invisible to the engine.

But a card in FLIGHT is drawn on top of the fan. If that is true, the values
were on screen for some number of frames before the card settled, and
wait_for_hand_deal was looking at exactly those frames -- it grabs the hand
region every 0.15 s for the whole deal and keeps only a delta number.

This asks the question of the ARCHIVE first, before any code is changed:
overnight/runs/*/stream.mp4 are 1920x1080 at 60 fps, written by record_stream
from the same frame dump. Read-only; nothing here touches the console.

METHOD. Two passes, because reading every frame of a 98k-frame video costs
hours and 99% of them are not a deal.

  pass 1  mean-abs-delta on the HAND BAND only, every STRIDE frames. A deal is
          a burst. Cheap: a crop and a subtract.
  pass 2  around each burst, dump EVERY frame and run read_hand on it, so the
          per-slot readability is known frame by frame.

The output is one directory per deal holding the frames and a rows.json, which
is what a human (or a reader agent) adjudicates. NO THRESHOLD IS INVENTED for
"is this card readable" -- that is read_hand's own gate, unchanged.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The hand band as a fraction of the frame, taken from orchestrator's own map so
# this cannot drift from what the reader is actually handed.
import orchestrator as o
import local_hand

HAND_FRAC = o.GAMEPLAY_REGIONS_FRAC["hand"]

STRIDE = 12         # pass-1 sampling: 5 Hz on 60 fps footage
PRE_S, POST_S = 2.0, 3.0   # how much of each event to dump densely
LOOKBACK_S = 4.0    # how far back a "it was readable earlier" claim may reach
PERSIST_S = 3.0     # an occlusion persists; a 10.26 flicker does not


def _hand(bgr):
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = HAND_FRAC
    return bgr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def _pil(bgr):
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    tw = int(local_hand.ANCHOR_W)
    if im.width != tw:
        im = im.resize((tw, max(1, round(im.height * tw / im.width))), Image.LANCZOS)
    return im


def _slots(im):
    """{slot_index: True/False readable} for one hand crop, plus the row count.

    Slot index is POSITION IN THE FAN left to right, which is what read_hand's x
    ordering gives and what hand_index means downstream.
    """
    try:
        got = sorted(local_hand.read_hand(im), key=lambda r: r.get("x", 0))
    except Exception:
        return {}, 0
    out = {}
    for i, r in enumerate(got):
        if r.get("kind") == "player":
            out[i] = r.get("digit") is not None and r.get("secondary") is not None
        elif r.get("kind") == "tactics":
            out[i] = r.get("type") is not None and r.get("bonus") is not None
        else:
            out[i] = False
    return out, len(got)


def scan(path, stride=STRIDE):
    """Sample the video and ask read_hand, not a delta, where the deals are.

    THE FIRST VERSION RANKED BY MEAN-ABS-DELTA AND FOUND NOTHING, and the reason
    is worth keeping: the BIGGEST changes in a match recording are SCREEN
    TRANSITIONS -- turn to result, result to ban grid -- which dwarf a deal
    animation. Every one of its top bursts came back `max rows 0` or 2, i.e. not
    a turn screen at all. A delta cannot tell "the hand changed" from "the screen
    changed", which is 10.4's shape: one quantity, two populations, no threshold
    between them. So this asks the reader directly.
    """
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    samples, i = [], 0
    while True:
        if not cap.grab():
            break
        if i % stride == 0:
            ok, fr = cap.retrieve()
            if ok:
                slots, n = _slots(_pil(_hand(fr)))
                if n >= 4:                      # a turn screen, or close to one
                    samples.append((i, slots, n))
        i += 1
    cap.release()
    return samples, fps, i


def losses(samples, fps, lookback=LOOKBACK_S):
    """Every moment a slot went READABLE -> UNREADABLE. The whole question.

    A card dealt straight into occlusion is exactly this: visible in flight,
    then not. Each hit carries the frame where it was last readable, which is
    the frame that proves the values were on screen.
    """
    out = []
    for k, (idx, slots, n) in enumerate(samples):
        for slot, ok_now in slots.items():
            if ok_now:
                continue
            # walk back for the most recent sample where THIS slot read
            for j in range(k - 1, -1, -1):
                pidx, pslots, pn = samples[j]
                if (idx - pidx) / fps > lookback:
                    break
                if pslots.get(slot) is True and pn == n:
                    # PERSISTENCE, AND IT IS WHAT SEPARATES THE TWO POPULATIONS.
                    # The first version fired on any READ -> UNREAD edge and its
                    # top three hits were all 10.26 FLICKER: the fitted circle
                    # alternates r=19/r=20, read_digit resamples to a fixed
                    # 24x24, and the same motionless card reads 7 / unread / 7.
                    # Those recover within a frame or two and answer nothing.
                    #
                    # An OCCLUSION does not recover: 10.28 measured it live --
                    # "the occlusion is STABLE, not an animation", 0 of 15
                    # re-grabs recovered, and once it happens it persists for
                    # the whole hand. So require the slot to stay dark for
                    # PERSIST_S, which is the property the two classes differ on
                    # rather than a threshold cut through one of them.
                    need = [t for t in samples[k:]
                            if (t[0] - idx) / fps <= PERSIST_S and t[2] == n]
                    if len(need) >= 3 and all(t[1].get(slot) is False for t in need):
                        out.append({"frame": idx, "slot": slot, "rows": n,
                                    "last_good_frame": pidx,
                                    "gap_s": round((idx - pidx) / fps, 2),
                                    "stayed_dark_samples": len(need)})
                    break
            else:
                continue
            break
    # one hit per event, not one per sample of the same event
    dedup = []
    for h in out:
        if not dedup or h["frame"] - dedup[-1]["frame"] > fps * 3 or h["slot"] != dedup[-1]["slot"]:
            dedup.append(h)
    return dedup


def dump(path, centre, fps, outdir):
    """Every frame of one burst, with read_hand's answer per frame."""
    os.makedirs(outdir, exist_ok=True)
    lo = max(0, int(centre - PRE_S * fps))
    hi = int(centre + POST_S * fps)
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, lo)
    rows = []
    for n in range(lo, hi):
        ok, fr = cap.read()
        if not ok:
            break
        im = _pil(_hand(fr))
        try:
            got = local_hand.read_hand(im)
        except Exception as exc:
            got = []
            err = str(exc)
        else:
            err = None
        # ONE ROW PER FRAME, carrying every slot's own verdict. `readable` is
        # read_hand's gate, not a new one.
        cards = []
        for r in sorted(got, key=lambda r: r.get("x", 0)):
            cards.append({
                "x": r.get("x"), "kind": r.get("kind"),
                "digit": r.get("digit"), "score": r.get("score"),
                "secondary": r.get("secondary"),
                "type": r.get("type"), "bonus": r.get("bonus"),
            })
        rows.append({"frame": n, "t": round((n - lo) / fps, 3),
                     "n_rows": len(got), "cards": cards, "error": err})
        im.save(os.path.join(outdir, f"f{n:07d}.png"))
    cap.release()
    with open(os.path.join(outdir, "rows.json"), "w") as fh:
        json.dump(rows, fh, indent=1)
    return rows


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        print("usage: deal_frames.py <stream.mp4> <outdir> [max_events]")
        return 2
    path, outroot = argv[1], argv[2]
    cap = int(argv[3]) if len(argv) > 3 else 6
    samples, fps, total = scan(path)
    hits = losses(samples, fps)
    name = os.path.basename(os.path.dirname(path))
    print(f"{name}: {total} frames at {fps:.0f} fps, {len(samples)} turn samples, "
          f"{len(hits)} READABLE->UNREADABLE events", flush=True)
    os.makedirs(outroot, exist_ok=True)
    index = []
    for k, h in enumerate(hits[:cap]):
        outdir = os.path.join(outroot, f"loss_{h['frame']:07d}_slot{h['slot']}")
        rows = dump(path, h["frame"], fps, outdir)
        good = [r["frame"] for r in rows
                if len(r["cards"]) > h["slot"] and (
                    r["cards"][h["slot"]]["digit"] is not None
                    if r["cards"][h["slot"]]["kind"] == "player"
                    else r["cards"][h["slot"]]["type"] is not None)]
        print(f"  event {k}: slot {h['slot']} lost at frame {h['frame']} "
              f"({h['gap_s']}s after last good) -> {len(rows)} frames dumped, "
              f"slot readable in {len(good)} of them", flush=True)
        index.append({**h, "dir": outdir, "frames": len(rows),
                      "slot_readable_frames": good})
    with open(os.path.join(outroot, "index.json"), "w") as fh:
        json.dump({"video": path, "samples": len(samples), "events": len(hits),
                   "dumped": index}, fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
