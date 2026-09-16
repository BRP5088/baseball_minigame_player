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


# The fan's own slot anchors, both banks. A row is assigned to the slot whose
# anchor it is nearest in x -- NOT to its position in the row list.
_ANCHOR_X = [(p[0] + t[0]) / 2.0
             for p, t in zip(local_hand.SLOT_PLAYER, local_hand.SLOT_TACTICS)]
# Half the tightest gap between neighbouring anchors: past that a row is closer
# to a different slot, so it is not evidence about this one.
_SLOT_TOL = min(b - a for a, b in zip(_ANCHOR_X, _ANCHOR_X[1:])) / 2.0


def _slots(im):
    """{slot: readable} keyed on the FAN'S GEOMETRY, plus the row count.

    THE FIRST VERSION KEYED ON POSITION IN THE ROW LIST and it measured the
    wrong thing. When the hand TURNS OVER -- a card played, the fan re-dealing
    -- cards[1] is a different physical card from one frame to the next, so
    "slot 1 went dark" was reporting a position shift as an occlusion. A contact
    sheet settled it in one glance: a PITCHER 5/0 read at 0.98-0.996 for 1.9 s,
    then a different card swept through and a 9 arrived at the same index. That
    is CLAUDE.md 10.22 -- a pipeline whose own output defines the alignment
    cannot be scored on that alignment -- and it is why this keys on x instead.

    A row further than _SLOT_TOL from every anchor is DROPPED rather than
    assigned to its nearest: mid-animation a card sits between slots, and
    forcing it into one manufactures exactly the false transition this is
    trying to avoid.
    """
    try:
        got = local_hand.read_hand(im)
    except Exception:
        return {}, 0
    out = {}
    for r in got:
        x = r.get("x")
        if x is None:
            continue
        best = min(range(len(_ANCHOR_X)), key=lambda i: abs(_ANCHOR_X[i] - x))
        if abs(_ANCHOR_X[best] - x) > _SLOT_TOL:
            continue
        if r.get("kind") == "player":
            ok = r.get("digit") is not None and r.get("secondary") is not None
        elif r.get("kind") == "tactics":
            ok = r.get("type") is not None and r.get("bonus") is not None
        else:
            ok = False
        # A slot already claimed by a nearer row wins; mid-animation two rows can
        # land in one slot's basin.
        out[best] = out.get(best, False) or ok
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


def dark_slots(samples, fps, gap_s=6.0):
    """Every moment a FULL hand has a slot the reader cannot read.

    WHY THIS EXISTS ALONGSIDE losses(). losses() requires the slot to have been
    READABLE in an earlier 5 Hz sample. If a card is dealt straight into
    occlusion and its clear window is shorter than a sample interval, that
    requirement can never be met -- so "no events" would mean "the instrument
    cannot fire", which is indistinguishable from "the card was never visible"
    (CLAUDE.md 10.1). Two recordings came back 0 of 2,496 turn samples on
    losses() alone, and that is exactly the ambiguity.

    This assumes NOTHING about earlier readability. It finds a five-row hand
    with a dark slot, and the 60 fps dump around it -- which reads EVERY frame,
    not every twelfth -- is what answers whether the card was ever visible.
    """
    out = []
    for idx, slots, n in samples:
        if n != 5:
            continue
        dark = [i for i, ok in slots.items() if not ok]
        if len(dark) != 1:
            continue
        if out and (idx - out[-1]["frame"]) / fps < gap_s and out[-1]["slot"] == dark[0]:
            continue
        out.append({"frame": idx, "slot": dark[0], "rows": n})
    return out


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
            _x = r.get("x")
            _slot = None
            if _x is not None:
                _b = min(range(len(_ANCHOR_X)), key=lambda i: abs(_ANCHOR_X[i] - _x))
                if abs(_ANCHOR_X[_b] - _x) <= _SLOT_TOL:
                    _slot = _b
            cards.append({
                "slot": _slot,
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
    mode = os.environ.get('DEAL_MODE', 'losses')
    hits = dark_slots(samples, fps) if mode == 'dark' else losses(samples, fps)
    name = os.path.basename(os.path.dirname(path))
    print(f"{name}: {total} frames at {fps:.0f} fps, {len(samples)} turn samples, "
          f"{len(hits)} {mode} events", flush=True)
    os.makedirs(outroot, exist_ok=True)
    index = []
    for k, h in enumerate(hits[:cap]):
        outdir = os.path.join(outroot, f"loss_{h['frame']:07d}_slot{h['slot']}")
        rows = dump(path, h["frame"], fps, outdir)
        def _at(r, slot):
            """The card in THIS slot on this frame, by the fan's geometry.

            Indexing r["cards"] by slot number is what produced a false
            occlusion: mid-turnover the list is a different set of cards.
            """
            for c in r["cards"]:
                if c.get("slot") == slot:
                    return c
            return None

        def _ok(c):
            if not c:
                return False
            return ((c["digit"] is not None and c["secondary"] is not None)
                    if c["kind"] == "player" else c["type"] is not None)

        good = [r["frame"] for r in rows if _ok(_at(r, h["slot"]))]
        # THE NUMBER THAT MATTERS: the LONGEST RUN of consecutive 60 fps frames
        # in which the dark slot reads. A poll every 0.15 s catches a window only
        # if that window is at least 9 frames long at 60 fps.
        run = best = 0
        for r in rows:
            run = run + 1 if _ok(_at(r, h["slot"])) else 0
            best = max(best, run)
        h["longest_visible_run"] = best
        print(f"  event {k}: slot {h['slot']} dark at frame {h['frame']} -> "
              f"{len(rows)} frames dumped, slot readable in {len(good)}, "
              f"LONGEST RUN {best} frames ({best / fps * 1000:.0f} ms)", flush=True)
        index.append({**h, "dir": outdir, "frames": len(rows),
                      "slot_readable_frames": good})
    with open(os.path.join(outroot, "index.json"), "w") as fh:
        json.dump({"video": path, "samples": len(samples), "events": len(hits),
                   "dumped": index}, fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
