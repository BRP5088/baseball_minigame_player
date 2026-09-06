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

import numpy as np

import _harness
import compass

# ONE ROOM PER DRIVE. The name is not decoration: it is the only GROUND TRUTH
# in this whole pipeline. Nothing else can say where a frame was taken -- the
# localiser is exactly what is being repaired, so it cannot be the label -- and
# a human who can see the screen can. Every frame in this directory is labelled
# by the person who drove it.
#
# It also bounds the damage: a break costs one room, not the session. And Snoopy
# can reconstruct room one while room two is still being driven.
NAME = sys.argv[1] if len(sys.argv) > 1 else ""
PLACEHOLDERS = {"", "drive", "test", "tmp", "temp", "x", "asdf", "run"}
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
HZ = 5.0

# A FROZEN STREAM MUST NOT BE RECORDED AS A GOOD RUN. Without this a drive that
# froze at minute two of fifteen produced byte-identical frames, a written
# meta.json, and a summary reading "100% with a heading" -- and the coverage
# line said "repeat", which is documented to the driver as "you are filming the
# same angle, turn or move". It blamed the person driving for the stream being
# dead, and cost them thirteen minutes.
#
# THE THRESHOLD IS NOT A GUESS. Measured on this project's own frames:
#     live but still (camera parked)  n=29  min 1.84  median 4.04  max 5.47
#     frozen                          n=38  min/median/max 0.0000
# An empty gap 1.84 wide, matching section 8(g)'s 0.91-6.41 standing-still
# population. 0.35 sits inside it, and is the same constant collect_map.py
# already uses for the same question.
DEAD_DELTA = 0.35
DEAD_RUN_ABORT = 15        # consecutive dead pairs (3s at 5 Hz) before stopping

# ARE YOU MOVING TOO FAST? Reconstruction chains frame to frame, so consecutive
# frames must share enough of the scene to be matched. Measured over all 3357
# archived frames of the walks that DID reconstruct:
#     consecutive-frame inliers   p05 61   p25 521   median 751   p95 1296
# So those recordings dipped to 61 and still worked; below that is outside
# anything shown to reconstruct. This is a floor from real data, not a guess --
# but note it is a FLOOR, not a separation between two populations: nobody has
# recorded a walk fast enough to fail, so the true breaking point is unmeasured.
OVERLAP_SLOW = 400         # comfortable
OVERLAP_FAST = 61          # the p05 of recordings that reconstructed

# WHEN IS A ROOM DONE? Two things have to be true, and they fail differently:
#
#   ANGLES   you can stand everywhere in a room and still have filmed it from
#            one direction. The compass is split into 8 sectors and each is
#            counted, because a reference matched from the wrong side does not
#            match at all -- that is why the current reference set fails its own
#            leave-one-out 3 times in 9.
#
#   NOVELTY  the honest stopping rule. While the room still has unseen ground,
#            frames keep coming back NEW. When they stop, there is nothing left
#            to photograph -- whatever the map's own opinion is.
#
# Neither alone is enough: all 8 sectors from one spot is a panorama, not a
# room, and a NEW rate near zero with 2 sectors covered means you walked a line.
SECTORS = 8
COVERAGE_EVERY = 50        # frames, i.e. every 10s at 5 Hz
NEW_RATE_DONE = 0.10       # under 10% new over the last window = nothing left

# The controller, read directly. pygame was excluded from requirements.txt, but
# record_input.py genuinely imports it and a DualSense is visible on this Mac
# with six axes. Reading the stick exactly beats inferring distance from vision,
# which was measured to correlate only 0.55-0.58 with the real stick on walks
# and 0.14 on turns.
LOG_STICK = True

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drives",
                   f"{time.strftime('%Y%m%d_%H%M%S')}_{NAME}")
META = os.path.join(OUT, "meta.json")


def _feedback_setup():
    """Descriptors for everywhere the map already knows.

    ABSOLUTE PATH, AND A LOUD FAILURE IF IT IS EMPTY. places.PLACES_DIR is the
    relative string "places", and places._room_dirs returns [] for a missing
    directory without error. Run from any directory but the repo root, this
    loaded ZERO references -- and with no references `best` is always 0, so the
    KNOWN and thin branches cannot fire and every frame reads NEW. The driver
    would be told to keep filming ground the map already covers, for a whole
    session, with nothing on screen saying anything was wrong.

    Same frame, two working directories: repo root -> KNOWN (bar_pool_room
    1500); anywhere else -> NEW (best None 0).
    """
    import places
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    refs = places.load_keypoints(os.path.join(root, "places"))
    if not refs:
        raise SystemExit(
            f"no reference frames under {os.path.join(root, 'places')}.\n"
            f"Without them every frame reads NEW and the coverage advice is "
            f"worthless -- refusing to record a session you would be driving "
            f"blind.")
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


def _open_stick():
    """A joystick handle, or None. Never raises: no controller is not an error."""
    if not LOG_STICK:
        return None
    try:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            return None
        j = pygame.joystick.Joystick(0)
        j.init()
        return (pygame, j)
    except Exception:
        return None


def _read_stick(h):
    """{axis: value} or None. The left stick is what carries DISTANCE."""
    if h is None:
        return None
    try:
        pygame, j = h
        pygame.event.pump()
        n = j.get_numaxes()
        return {"lx": round(j.get_axis(0), 4) if n > 0 else 0.0,
                "ly": round(j.get_axis(1), 4) if n > 1 else 0.0,
                "rx": round(j.get_axis(2), 4) if n > 2 else 0.0,
                "ry": round(j.get_axis(3), 4) if n > 3 else 0.0}
    except Exception:
        return None


def _kp(img):
    import places
    return places.keypoints(img)


def _overlap(prev, img):
    """RANSAC-verified inliers against the frame about a second ago, or None."""
    try:
        import cv2
        import places
        k1, d1 = prev
        k2, d2 = places.keypoints(img)
        if d1 is None or d2 is None or len(d1) < 12 or len(d2) < 12:
            return None
        m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
        if len(m) < 12:
            return 0
        p1 = np.float32([k1[x.queryIdx].pt for x in m]).reshape(-1, 1, 2)
        p2 = np.float32([k2[x.trainIdx].pt for x in m]).reshape(-1, 1, 2)
        _, mask = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC,
                                              ransacReprojThreshold=6.0)
        return 0 if mask is None else int(mask.sum())
    except Exception:
        return None


def _delta(a, b):
    a = np.asarray(a.convert("L"), dtype=float)
    b = np.asarray(b.convert("L"), dtype=float)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    return float(np.abs(a[:h, :w] - b[:h, :w]).mean())


def main():
    if NAME.strip().lower() in PLACEHOLDERS:
        raise SystemExit(
            "name the ROOM you are about to drive, e.g. bar, office, stairs, "
            "portrait_room.\n"
            "It is the only ground truth this pipeline has: nothing else can "
            "say where these frames were taken.\n"
            "  .venv/bin/python overnight/record_drive.py bar 300")
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
    stick = _open_stick()
    print("  controller: " + ("DualSense/joystick found — logging the stick, "
                              "so distance is exact"
                              if stick else
                              "NONE found — distance will have to come from "
                              "vision, which tracks only 0.55 on walks"), flush=True)
    t0 = time.time()
    meta, n, unreadable, dark_run = [], 0, 0, 0
    prev_img, dead_run, last_kp, last_verdict = None, 0, None, None
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

            # LIVENESS, checked every frame against the previous one.
            d = None if prev_img is None else _delta(prev_img, img)
            if d is not None and d <= DEAD_DELTA:
                dead_run += 1
            elif d is not None:
                dead_run = 0
            prev_img = img

            # The coverage verdict is SAVED, not merely printed. Without it no
            # later reconstruction can know which frames were new ground, and
            # the whole point of the drive is to find new ground.
            meta.append({"t": round(t, 2), "frame": fn, "bearing": b,
                         "stick": _read_stick(stick), "delta": d,
                         "verdict": last_verdict})
            if n % COVERAGE_EVERY == 0:
                secs_seen = {int(m["bearing"] // (360 / SECTORS))
                             for m in meta if m.get("bearing") is not None}
                recent = [m for m in meta[-COVERAGE_EVERY:]
                          if m.get("verdict")]
                new_rate = (sum(1 for m in recent if m["verdict"] == "NEW")
                            / max(len(recent), 1))
                bar = "".join("#" if i in secs_seen else "." 
                              for i in range(SECTORS))
                done = (len(secs_seen) >= SECTORS - 1
                        and new_rate <= NEW_RATE_DONE)
                print(f"\n  --- {t:5.0f}s  angles [{bar}] {len(secs_seen)}/{SECTORS}"
                      f"   new {100*new_rate:3.0f}% of the last {len(recent)}"
                      + ("   THIS AREA LOOKS DONE — move to the next room"
                         if done else
                         "   keep going" if new_rate > NEW_RATE_DONE
                         else "   turn to fill the missing angles") + "\n",
                      flush=True)

            if dead_run >= DEAD_RUN_ABORT:
                print(f"\n  STOPPING: the picture has not changed for "
                      f"{dead_run} frames ({dead_run/HZ:.0f}s).\n"
                      f"  That is a FROZEN STREAM, not you standing still -- "
                      f"standing still still measures 1.8 or more.\n"
                      f"  Everything up to here is saved and usable. Fix the "
                      f"stream and start a new drive for this room.",
                      flush=True)
                break
            n += 1
            # FLUSH AS WE GO. Written once at the end, a drive killed at 4:30 of
            # 5:00 leaves 1350 jpegs and NO headings -- and a heading is what
            # makes a frame placeable, so the whole session would be unusable
            # while looking like a full directory. Ten seconds is the most that
            # can now be lost.
            if n % (int(HZ) * 10) == 0:
                _harness.save_result(META, {"room": NAME, "hz": HZ,
                                            "complete": False, "frames": meta})
            if n % 5 == 0:                      # about once a second
                room, score, verdict = _novelty(img, refs, seen)
                last_verdict = verdict
                # OVERLAP with the frame ~1s ago, which is what reconstruction
                # actually needs. Turning fast breaks it sooner than walking
                # fast does, because the whole view leaves the frame.
                speed = ""
                if last_kp is not None:
                    ov = _overlap(last_kp, img)
                    if ov is not None and ov < OVERLAP_FAST:
                        speed = f"   TOO FAST (overlap {ov}, need {OVERLAP_FAST}+)"
                    elif ov is not None and ov < OVERLAP_SLOW:
                        speed = f"   brisk (overlap {ov})"
                last_kp = _kp(img)
                tally[verdict] = tally.get(verdict, 0) + 1
                bs = "  --  " if b is None else f"{b:6.1f}"
                note = ""
                if dark_run >= 10:
                    note = "   <-- no compass for 2s+, this stretch cannot be placed"
                print(f"  {t:6.1f}s  hdg {bs}  {verdict:11} "
                      f"(best {room or '-'} {score})" + speed + note, flush=True)
            time.sleep(max(0.0, 1.0 / HZ - (time.time() - tick)))
    except KeyboardInterrupt:
        print("\n  stopped by hand")
    # `complete` distinguishes a finished drive from an interrupted one on
    # disk. Without it a directory that lost its last minute is indistinguishable
    # from one that ran to the end, and the reconstruction would treat both the
    # same.
    _harness.save_result(META, {"room": NAME, "hz": HZ, "complete": True,
                                "frames": meta})
    live = sum(1 for m in meta if m.get("delta") is not None
               and m["delta"] > DEAD_DELTA)
    checked = sum(1 for m in meta if m.get("delta") is not None)
    got_stick = sum(1 for m in meta if m.get("stick"))
    print(f"\n  {n} frames, {n-unreadable} with a heading "
          f"({100*(n-unreadable)/max(n,1):.0f}%)")
    print(f"  stream alive on {live}/{checked} frame pairs"
          + ("" if checked and live == checked
             else "   <-- a dead stretch is NOT usable data"))
    print(f"  stick logged on {got_stick}/{n} frames"
          + ("" if got_stick else "   <-- no controller seen"))
    if tally:
        print("  coverage seen: " + ", ".join(f"{k}={v}" for k, v in
                                              sorted(tally.items())))
    secs_seen = {int(m["bearing"] // (360 / SECTORS))
                 for m in meta if m.get("bearing") is not None}
    bar = "".join("#" if i in secs_seen else "." for i in range(SECTORS))
    late = [m for m in meta[-COVERAGE_EVERY:] if m.get("verdict")]
    rate = sum(1 for m in late if m["verdict"] == "NEW") / max(len(late), 1)
    print(f"  angles filmed  [{bar}] {len(secs_seen)}/{SECTORS} compass sectors")
    print(f"  still finding new ground at the end: {100*rate:.0f}%"
          + ("   <-- there is more here, consider another pass"
             if rate > NEW_RATE_DONE else "   (looks covered)"))
    print(f"  -> {OUT}")
    print(f"\n  ship it to Snoopy with:")
    print(f"    tools/ship_drive.sh {os.path.relpath(OUT)}")


main()
