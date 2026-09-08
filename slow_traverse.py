"""Walk the recorded route SLOWLY, watching for the things that go wrong.

WHY SLOW
--------
Every fast replay failed the same way: it ended somewhere unexpected with no
record of where it went wrong. Walking the same path in small increments, and
looking after each one, turns "it ended in the wrong room" into "it stopped
making progress at 14.2s while pointed at a doorframe" — which is a fixable
statement.

THE HAZARDS THIS WATCHES FOR, named by the person who walked the route:

  STUCK        the character is pushing but the view has stopped changing —
               wedged on a doorframe or between a door and the wall. This is
               the failure that ended runs inside the first building.
  SHORT        a leg finished but the view barely changed, so it did not
               actually travel. Distinct from STUCK: nothing is blocking, the
               push was simply too small.
  UNDERTURNED  a turn finished away from its target heading, so everything
               after it is aimed wrong.

Each is recorded with the time, heading and frame, so the route can be rebuilt
around them rather than through them.
"""

import json
import math
import os
import time

import numpy as np

import analog_replay as ar
import turn_curve as tc

STEP_SEC = 0.25            # default granularity for a long, watched leg
# chiaki releases injected input after INJECT_TIMEOUT_MS (5s) if nothing is
# written, so no single push may approach that. 4.0 leaves headroom for the
# write itself and for a slow capture.
MAX_PUSH_SEC = 4.0
SETTLE_SEC = 0.35
STUCK_RATIO = 0.25         # travel below this fraction of the leg's best = stuck
SHORT_ABS = 3.0            # mean frame change below this = went nowhere
TURN_TOLERANCE = 4.0       # degrees


def _grey(img):
    return np.asarray(img.convert("L"), dtype=float)


def _change(a, b):
    return float(np.abs(a - b).mean())


class Hazard:
    def __init__(self, kind, t, heading, note):
        self.kind, self.t, self.heading, self.note = kind, t, heading, note

    def __repr__(self):
        h = "--" if self.heading is None else f"{self.heading:.1f}"
        return f"{self.kind:11} t={self.t:5.2f} heading={h:>6}  {self.note}"


def walk_leg(lx, ly, seconds, capture, read_heading, label="", log=print,
             step_sec=None, on_release=None):
    """Walk one leg, reporting travel per step and any hazard.

    `step_sec` is how long a single continuous push lasts. It defaults to
    STEP_SEC (0.25s), which is right for a LONG leg that has to be watched as it
    goes, and WRONG for a short one:

    the character accelerates from a standstill, so N pushes of 0.25s separated
    by SETTLE_SEC stops cover markedly less ground than one push of 0.25*N.
    Measured consequence 2026-09-01 — replaying recorded steps (all <= 0.80s)
    at the 0.25s default walked the route short and ended in the wrong room,
    while the recording that produced them was one continuous push per step.

    Chunking exists for chiaki's 5s input watchdog (INJECT_TIMEOUT_MS), which
    releases the stick if nothing is written. That bounds a single push at about
    4.5s — it does not require breaking up a 0.8s one.
    """
    hazards = []
    prev = _grey(capture())
    best = 0.0
    spent = 0.0
    quiet = 0
    series = []                # every chunk's travel, not just the best one
    chunk = min(step_sec or STEP_SEC, MAX_PUSH_SEC)
    while spent < seconds - 1e-3:
        step = min(chunk, seconds - spent)
        ar.send([f"left_x {ar.to_axis(lx)}", f"left_y {ar.to_axis(ly)}",
                 "right_x 0", "right_y 0"])
        time.sleep(step)
        ar.send(["left_x 0", "left_y 0"])
        # THE INSTANT THE STICK IS ZEROED, before the settle. Anything hooked
        # after this function returns starts SETTLE_SEC late and cannot see the
        # window it exists to measure (patch54). Default None: the two lines
        # around this are the shipped path, untouched.
        if on_release is not None:
            on_release()
        time.sleep(SETTLE_SEC)
        spent += step

        now = _grey(capture())
        moved = _change(now, prev)
        prev = now
        best = max(best, moved)
        series.append(moved)

        if best > 0 and moved < max(SHORT_ABS, best * STUCK_RATIO):
            quiet += 1
            if quiet >= 2:
                h = read_heading()
                hazards.append(Hazard(
                    "STUCK", spent, h,
                    f"{label}: pushing but view stopped changing "
                    f"({moved:.1f} vs best {best:.1f}) — likely wedged"))
                break
        else:
            quiet = 0
    if best < SHORT_ABS:
        hazards.append(Hazard("SHORT", spent, read_heading(),
                              f"{label}: leg finished but never travelled "
                              f"(best change {best:.1f})"))
    # ONE summary line, not one per chunk. Only `best` survives to the caller,
    # so the per-chunk series is the only record of HOW the leg travelled, and
    # `log` was accepted here and never called — functionally identical to
    # passing `lambda m: None`, item 1 in the diagnosis catalogue.
    if not series:
        why = (" — NOTHING WAS PUSHED (seconds <= 0), so the caller's "
               "'walked 0.00s' is not a blocked leg")
    elif len(series) > 1:
        why = (" — the caller is told only the best chunk, so a leg that "
               "moved once and then jammed looks even there")
    else:
        why = " — one push, so `best` IS the whole leg's travel"
    log(f"        {label}: {len(series)} chunk(s) of {chunk:.2f}s, change "
        f"{'/'.join(f'{m:.1f}' for m in series) or 'none'}, best {best:.1f}, "
        f"hazards {'/'.join(h.kind for h in hazards) or 'none'}" + why)
    return spent, best, hazards


def turn_to(target, read_heading, capture, log=print, tolerance=TURN_TOLERANCE,
            max_steps=14):
    """Turn to an absolute heading, reporting if it cannot get there.

    EVERY EXIT LOGS, because a turn that never happened used to be
    indistinguishable from one that did. The caller's line reads

        step 2/4 bearing  292.2 (got  289.1) 0.79s -> walked 0.79s

    whether the character turned to 292.2 or was already inside `tolerance` and
    NOTHING WAS SENT — and it cannot be told apart after the fact either, since
    an executed turn also ends inside tolerance. With TURN_TOLERANCE = 4.0 and
    the leg portrait_room -> bar_pool_room commanding 286.6 / 292.2 / 285.6 /
    287.6 (a 6.6 degree curve), a character standing at 289.1 is inside
    tolerance for all four, so the recorded curve is discarded four times over.

    The NO-OP line is what makes that COUNTABLE from logs already on disk,
    which is the evidence OPEN-3 needs. Observability only: no threshold and no
    control-flow decision changed here.
    """
    asked, sent = 0.0, 0.0      # the FIRST error seen, and the stick time
    for i in range(max_steps):   # spent on it; both for the log line only
        now = read_heading()
        if now is None:
            log(f"        turn to {target:.1f}: NO compass reading, abandoned "
                f"BEFORE turning — the caller's 'got --' is an unread heading, "
                f"not a heading that was reached")
            break
        err = (target - now + 540) % 360 - 180
        if i == 0:
            asked = err
        if abs(err) <= tolerance:
            if i == 0:
                log(f"        turn to {target:.1f}: NO-OP, already inside "
                    f"{tolerance:.1f} deg (at {now:.1f}, err {err:+.1f}) — "
                    f"nothing was sent, the recorded curve was discarded, and "
                    f"the caller's step line will look like a turn that "
                    f"happened")
            else:
                # `err` here is what is LEFT, which is inside `tolerance` by
                # construction and so says nothing (10.12). `asked` is the
                # error this call was given and `sent` the stick time it spent
                # -- the two numbers needed to ask whether TURN_TOLERANCE and
                # the 0.35 s settle below are worth what turning costs (~40% of
                # the walk). Recorded, not acted on.
                log(f"        turn to {target:.1f}: TURNED to {now:.1f} "
                    f"(err {err:+.1f}) in {i} push(es), asked "
                    f"{asked:+.1f} deg, stick {sent:.2f}s")
            return now, []
        # Use the MEASURED response curve, not a linear gain. The stick is
        # dead below ~0.35 and triples between 0.90 and 1.00, so a linear
        # gain either does nothing or wildly overshoots — which is why an
        # earlier turn to 263 degrees reached 113.
        mag, secs = tc.plan_turn(err)
        if mag == 0.0:
            log(f"        turn to {target:.1f}: err {err:+.1f} is below the "
                f"0.5 deg plan_turn will act on, so NOTHING was sent — the "
                f"UNDERTURNED hazard below is the stick's floor, not a turn "
                f"that was attempted and missed")
            break
        ar.send([f"right_x {ar.to_axis(mag if err > 0 else -mag)}",
                 "right_y 0", "left_x 0", "left_y 0"])
        sent += secs
        time.sleep(secs)
        ar.send(["right_x 0"])
        time.sleep(0.35)
    else:
        log(f"        turn to {target:.1f}: {max_steps} pushes and still "
            f"outside {tolerance:.1f} deg — this turn RAN and did not "
            f"converge; the UNDERTURNED hazard below is not a no-op")
    now = read_heading()
    err = None if now is None else (target - now + 540) % 360 - 180
    return now, [Hazard("UNDERTURNED", 0.0, now,
                        f"wanted {target:.1f}, reached "
                        f"{'--' if now is None else f'{now:.1f}'} "
                        f"(off by {'--' if err is None else f'{err:+.1f}'})")]
