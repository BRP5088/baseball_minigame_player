"""Record while YOU drive. Sends nothing to the console.

The auto-explorer picks its own way through free space, which covers a corridor
adequately and interesting corners badly. A person driving reaches the places
worth photographing -- the doorway, the stairs, the far side of the pool table,
wherever the map is thin -- in a fraction of the time.

So this drives NOTHING. It only watches: a frame, a compass bearing and a
timestamp, at about 5 Hz, in the same shape as demos/ so the existing
reconstruction reads it without changes.

    .venv/bin/python overnight/record_drive.py bar_area 300

Stop it with Ctrl-C, or let the seconds run out. Frames land in
overnight/drives/<stamp>_<name>/ and the bearings the Mac computed go beside
them, because the compass reader is macOS-bound and Snoopy cannot recompute it.

WHY THE BEARING IS SAVED PER FRAME. Absolute heading is what makes this
reconstructible: it is why rotational drift cannot accumulate over a long walk.
A frame without one is still worth keeping -- the run either side of it carries
the heading -- so an unreadable compass is recorded as null rather than dropped.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import _harness
import compass

NAME = sys.argv[1] if len(sys.argv) > 1 else "drive"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
HZ = 5.0

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drives",
                   f"{time.strftime('%Y%m%d_%H%M%S')}_{NAME}")


def _feedback_setup():
    """Descriptors for everywhere the map already knows."""
    import places
    refs = places.load_keypoints(places.PLACES_DIR)
    return refs


def _novelty(img, refs, seen):
    """(best known room, its score, how new this view is).

    NEW is what matters while driving. A view the reference set already matches
    strongly adds nothing; the map is thin exactly where nothing matches. `seen`
    holds what THIS drive has already photographed, so circling one spot stops
    reading as new after the first pass.
    """
    import places
    k, d = places.keypoints(img)
    if d is None or len(d) < 30:
        return None, 0, "FEATURELESS"
    best_room, best = None, 0
    for room, rs in refs.items():
        v = max(places.match_count(d, r) for r in rs)
        if v > best:
            best_room, best = room, v
    here = max((places.match_count(d, x) for x in seen), default=0)
    if len(seen) < 40 and (here < 120):
        seen.append(d)
    # TWO DIFFERENT QUESTIONS, and the first version conflated them into one
    # verdict that read "covered" while the map scored 107 -- below its own
    # recognition gate of 140. Standing still made consecutive frames match each
    # other, and that was reported as if the MAP knew the place.
    #
    #   KNOWN   the reference set recognises this. Nothing to add here.
    #   repeat  the map does NOT know it, but you already shot this angle in
    #           this drive. Move or turn; do not keep filming it.
    #   NEW     neither. This is the ground worth covering.
    if best >= 200:
        return best_room, best, "KNOWN"
    if here >= 300:
        return best_room, best, "repeat"
    if best >= 140:
        return best_room, best, "thin"
    return best_room, best, "NEW"


def main():
    os.makedirs(OUT, exist_ok=True)
    refs = _feedback_setup()
    seen = []
    print(f"recording to {OUT}")
    print(f"  {SECONDS:.0f}s at {HZ:.0f} Hz — DRIVE THE CHARACTER NOW. "
          f"Ctrl-C to stop early.\n")
    print("  I will call out coverage as you go:")
    print("     NEW         the map does not know this — this is what I want")
    print("     thin        recognised, but barely; another angle helps")
    print("     KNOWN       already well photographed, move on")
    print("     repeat      you are filming the same angle — turn or move")
    print("     FEATURELESS pressed against something, or too dark to use")
    print("     no compass  heading unreadable; this stretch cannot be placed\n",
          flush=True)
    t0 = time.time()
    meta, n, unreadable, dark_run = [], 0, 0, 0
    tally = {}
    try:
        while time.time() - t0 < SECONDS:
            tick = time.time()
            t = tick - t0
            img = compass.fast_capture()
            fn = f"f_{t:07.2f}.jpg"
            img.convert("RGB").save(os.path.join(OUT, fn), quality=88)
            b = compass.read_bearing(img)
            if b is None:
                unreadable += 1; dark_run += 1
            else:
                dark_run = 0
            meta.append({"t": round(t, 2), "frame": fn, "bearing": b})
            n += 1
            if n % 5 == 0:                      # about once a second
                room, score, verdict = _novelty(img, refs, seen)
                tally[verdict] = tally.get(verdict, 0) + 1
                bs = "  --  " if b is None else f"{b:6.1f}"
                note = ""
                if dark_run >= 10:
                    note = "   <-- no compass for 2s+, this stretch cannot be placed"
                print(f"  {t:6.1f}s  hdg {bs}  {verdict:11} "
                      f"(best {room or '-'} {score})" + note, flush=True)
            time.sleep(max(0.0, 1.0 / HZ - (time.time() - tick)))
    except KeyboardInterrupt:
        print("\n  stopped by hand")
    _harness.save_result(os.path.join(OUT, "meta.json"), meta)
    print(f"\n  {n} frames, {n-unreadable} with a heading "
          f"({100*(n-unreadable)/max(n,1):.0f}%)")
    if tally:
        print("  coverage seen: " + ", ".join(f"{k}={v}" for k, v in
                                              sorted(tally.items())))
    print(f"  -> {OUT}")
    print(f"\n  ship it with:  scp -r -i ~/.ssh/id_ed25519_snoopy "
          f"{OUT} Brett@snoopy:C:/baseball/data/drives/")


main()
