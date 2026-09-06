"""Map unknown ground SLOWLY and deliberately. Coverage, never speed.

THE PRINCIPLE (user, 2026-09-04): "for the areas that are unknown, I don't care
about speed at all. I would rather you move slow but with intention. that way,
it's fully mapped and you can optimize the known route later."

Explore slow, exploit fast. Everything the speed work established — the 0.60
repeatability cliff, LEG_SPEED_SCALE — belongs to the KNOWN route. Here the
opposite applies: short pushes at low magnitude, where the measured spread is
tightest (~15px at 0.25-0.45 against 476px at 0.85), so each sample sits where
the recorder thinks it does.

WHY A SWEEP AT EVERY SPOT. `places.identify()` matches a VIEW, not a place. A
spot photographed facing one way is invisible from the same spot facing another,
which is how a route can stand inside a mapped room and still fail to recognise
it. So each stop records the full circle.

IT ADDS NOTHING TO THE MAP. Frames and metadata go to disk for an offline pass
to judge. A place seeded from a bad frame poisons the localiser permanently.
"""

import json
import os
import time

STEP_SEC = 0.35           # short: a small mistake stays small
STEP_SPEED = 0.30         # inside the measured-repeatable band
SWEEP_BEARINGS = 8        # every 45 degrees
SETTLE = 0.45             # let the camera stop before the shutter
OUT_ROOT = "explore"


class Explorer:
    """Walks a little, looks all around, writes down everything it saw."""

    def __init__(self, name, log=print, root=OUT_ROOT):
        self.dir = os.path.join(root, f"{time.strftime('%Y%m%d_%H%M%S')}_{name}")
        os.makedirs(self.dir, exist_ok=True)
        self.log = log
        self.n = 0
        self.index = os.path.join(self.dir, "index.jsonl")

    def _write(self, row):
        with open(self.index, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def sweep(self, note=""):
        """Record the full circle from where we stand. Returns rows written.

        Turning does not move the character, so a sweep cannot make the map
        worse by displacing the thing it is mapping.
        """
        import compass
        import places
        import walk_steps as ws

        # A SWEEP OWNS ITS OWN ID. stop_id used to be incremented only by
        # step(), so a fan's last sweep and the next "at the node" sweep — with
        # no step() between them, because the character was walked back — shared
        # a stop id. In the 2026-09-04 bar run that merged TWO DIFFERENT
        # POSITIONS under one id on 3 of 17 stops, and it merged the "at the
        # node" sweep with a sweep three pushes away: exactly the two classes
        # anyone analysing this data is trying to tell apart. 24 (stop, k) pairs
        # occurred twice, so a frame could not even be addressed uniquely.
        #
        # Nothing errored. The index stayed valid JSON and the row count was
        # right; only the labels were wrong, which is why it survived a whole
        # analysis before being noticed.
        #
        # `pos` keeps what stop_id was meant to carry — how many pushes from the
        # start — so "two sweeps at the same position" is still expressible,
        # explicitly, instead of by collision.
        self.stop_id += 1
        start = ws.read_heading()
        if start is None:
            self.log("  no compass here — sweeping blind, headings unrecorded")
        rows = []
        for k in range(SWEEP_BEARINGS):
            if start is not None:
                ws.turn_to((start + k * (360.0 / SWEEP_BEARINGS)) % 360.0,
                           log=lambda *a: None)
            time.sleep(SETTLE)
            img = compass.fast_capture()
            _, desc = places.keypoints(img)
            kp = 0 if desc is None else len(desc)
            room, score, margin = places.identify(img)
            self.n += 1
            f = os.path.join(self.dir, f"{self.n:05d}.jpg")
            img.save(f)
            row = {"file": f, "stop": self.stop_id, "pos": self.pos_id, "k": k,
                   "heading": compass.read_bearing(img), "keypoints": kp,
                   "identify": room, "score": score, "margin": margin,
                   "note": note}
            self._write(row)
            rows.append(row)
            self.log(f"    {k+1}/{SWEEP_BEARINGS}: {kp:5} kp  "
                     f"{room or 'unknown':16} ({score:.0f}/{margin:.2f})")
        if start is not None:
            ws.turn_to(start, log=lambda *a: None)
        return rows

    stop_id = 0        # one per SWEEP — unique, so (stop, k) addresses a frame
    pos_id = 0         # one per PUSH — how far the character has walked

    def step(self, bearing, seconds=STEP_SEC, speed=STEP_SPEED):
        """One short, deliberate push. Returns how far the view moved."""
        import walk_steps as ws

        ws.turn_to(bearing % 360.0, log=lambda *a: None)
        moved = ws.walk_forward(speed, seconds) or 0.0
        time.sleep(SETTLE)
        self.pos_id += 1
        self.log(f"  step -> bearing {bearing % 360.0:.0f} for {seconds:.2f}s "
                 f"(view moved {moved:.1f})")
        return moved

    def summary(self):
        rows = [json.loads(l) for l in open(self.index)] if os.path.exists(self.index) else []
        unknown = [r for r in rows if r["identify"] is None and r["keypoints"] >= 400]
        return {"dir": self.dir, "frames": len(rows),
                "unmapped_rich_views": len(unknown),
                "stops": len({r["stop"] for r in rows}),
                "positions": len({r.get("pos") for r in rows})}
