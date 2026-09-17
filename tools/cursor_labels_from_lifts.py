#!/usr/bin/env python3
"""Label archived frames with the cursor's TRUE slot, WITHOUT asking the reader.

    .venv/bin/python -B tools/cursor_labels_from_lifts.py screenshot_log/run_YYYYMMDD_HHMMSS

Every previous census of `local_hand.cursor_slot` scored it against its own
answer (CLAUDE.md 10.22) or against a human reading a contact sheet. This is the
first independent label, and it costs nothing: no console, no live change, no
paid call. It runs on frames already on disk.

THE SIGNAL. `local_hand.selected_cards` reports which card has RISEN above its
own fan anchor. That is GEOMETRY -- a y offset -- and the glow reader cannot
influence it. Selecting a card requires the cursor to be on it, so the frame
BEFORE a slot newly rises is a frame whose cursor slot is known.

THE TRAP, and it removes 86% of the raw labels. A lift seen on ONE frame is not a
selection: during a deal the fan's anchors shift and a card reads as risen for a
frame or two with nothing selected. Measured over 14,437 frames of
`run_20260828_140236`:

    raw lift transitions                        29
    still lifted HOLD frames later               4      <- real selections
    dropped as transient                        25

and the raw set is dominated by exactly the artefact you would expect -- 19 of
its 20 "the reader went blind" cases were slot 0, i.e. deal frames with no cursor
on screen at all, where the reader is RIGHT to answer None.

So the filter is doing most of the work, and it is reported rather than hidden:
a filter that silently removes most of its input has changed what is being
measured. Against the 4 that survive, the shipped reader is 4/4 -- which proves
the METHOD and nothing about the reader, at that n.

YIELD is about 4 labels per recorded run, so the corpus grows by itself: point
this at every future run's frames and the numbers accumulate with no extra work.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                            # noqa: E402
from PIL import Image                                         # noqa: E402

import local_hand as lh                                       # noqa: E402
import orchestrator as o                                      # noqa: E402

HOLD = 3          # frames a lift must persist to count as a real selection


def _say(*a):
    """print that FLUSHES. Redirected to a file, print() buffers in 4 KB blocks,
    so a 14,000-frame scan shows ZERO bytes for minutes and "still starting up"
    is indistinguishable from "died on import" (CLAUDE.md 1, and 10.1's family).
    This bit during this tool's own validation run."""
    print(*a, flush=True)


def _selected(path):
    """The set of risen slots on one frame, or None if the hand does not read."""
    try:
        hand = dict(o.crop_gameplay_regions(Image.open(path)))["hand"]
        rows = lh.read_hand(hand)
        if len(rows) != 5:
            return None
        return set(lh.selected_cards(rows, hand.width / lh.ANCHOR_W))
    except Exception:
        return None


def labels_for(run_dir, hold=HOLD, log=_say):
    """[(frame, slot)] -- frames whose cursor slot is known from a later lift."""
    files = sorted(glob.glob(os.path.join(run_dir, "*.jpg")))
    log("frames: %d" % len(files))
    raw = []
    prev_sel = prev = None
    for n, p in enumerate(files):
        if n % 1000 == 0:
            log("  scanning %d/%d  raw=%d" % (n, len(files), len(raw)))
        sel = _selected(p)
        if sel is None:
            prev_sel = prev = None
            continue
        if prev_sel is not None:
            new = sel - prev_sel
            if len(new) == 1:          # exactly one card newly rose
                raw.append((prev, int(next(iter(new))), n))
        prev_sel, prev = sel, p

    kept = []
    for frame, slot, idx in raw:
        held = True
        for k in range(1, hold + 1):
            if idx + k >= len(files):
                held = False
                break
            s = _selected(files[idx + k])
            if s is None or slot not in s:
                held = False
                break
        if held:
            kept.append((frame, slot))
    log("raw lift transitions %d -> persisted %d frames: %d (dropped %d)"
        % (len(raw), hold, len(kept), len(raw) - len(kept)))
    return kept


def score(labels, log=_say):
    """How the SHIPPED reader does against them. Wrong is the only costly column."""
    ok = blind = wrong = 0
    for frame, slot in labels:
        try:
            hand = dict(o.crop_gameplay_regions(Image.open(frame)))["hand"]
            cur, glow, _rows = lh.cursor_glow(hand)
        except Exception:
            continue
        if cur == slot:
            ok += 1
        elif cur is None:
            blind += 1
        else:
            wrong += 1
            log("  WRONG: %s true=%d read=%s glow=%s"
                % (os.path.basename(frame), slot, cur, [round(g, 1) for g in glow]))
    tot = ok + blind + wrong
    if not tot:
        log("NOTHING TO SCORE -- no label survived, so this says nothing either way")
        return ok, blind, wrong
    log("\n  cursor_slot against %d INDEPENDENT labels" % tot)
    log("    correct      %-4d (%.1f%%)" % (ok, 100.0 * ok / tot))
    log("    blind (None) %-4d (%.1f%%)   costs a poll" % (blind, 100.0 * blind / tot))
    log("    WRONG card   %-4d (%.1f%%)   the only one that costs money"
        % (wrong, 100.0 * wrong / tot))
    log("\n  n is small by construction (~4 a run). Quote it WITH the n (10.8).")
    return ok, blind, wrong


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    labels = labels_for(argv[1])
    score(labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
