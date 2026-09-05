"""Record a MAPPING session — world frames only, kept away from match frames.

    from world_log import Recorder
    with Recorder("bar_sweep") as rec:
        rec.note("turn_to", bearing=90)
        ...

WHY A SEPARATE LOG
------------------
screenshot_log/ is written by match play. All three archives there turned out
to be match-playing runs, so an attempt to mine them for world waypoints
returned 8 "distinct viewpoints" that were all ban and gameplay screens — the
clustering was measuring card art. Mapping frames therefore live in their own
tree, under world_log/, and nothing that plays a match writes here.

WHY IT RECORDS METADATA, NOT JUST PIXELS
----------------------------------------
A graph needs edges with COSTS, and a cost is a duration between two places.
That is recoverable offline only if each frame carries the time it was taken
and the heading the camera was on, and only if the ACTIONS taken between
frames are in the same stream. So every frame writes an index row, and note()
puts the commands in the same timeline. One live walk then yields the whole
graph offline, which matters because live game time is the scarce resource
here and a walk cannot be repeated identically.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not drive the character, and it does not decide what anything IS. It
records. Labelling a place and connecting two places are offline steps done by
looking at the frames, because a place named by the same code that will later
be graded on finding it is not evidence of anything.
"""

import json
import os
import threading
import time

SESSION_ROOT = "world_log"
# Measured 2026-09-02: compass.fast_capture() takes 29ms (max 32), so capture
# tops out near 35fps. 6Hz is chosen rather than that ceiling, and the reason is
# not disk:
#
# For EVENTS — a collision, the ~2-3s reveal window, an NPC walking into frame —
# density wins outright, and 2Hz was under-sampling them badly.
#
# For MOTION measured between consecutive frames it is the opposite. Walking
# produces roughly 160-210 px/s of keypoint displacement (from the 0.2s step
# calibration: 32-42px) against a stationary noise floor of 8.8px. At 30fps
# consecutive frames differ by ~5-7px — BELOW the noise — so a moving character
# would look identical to a still one. At 6Hz it is ~27-35px, comfortably clear.
#
# Anything wanting a bigger signal should compare frames further APART in time
# rather than capture faster; the two are independent.
DEFAULT_HZ = 6.0


class Recorder:
    """Captures frames + metadata to world_log/<session>/ on a background thread.

    The thread NEVER raises into the caller: a failed grab or an unreadable
    compass writes a row with nulls and carries on. A mapping walk that dies
    halfway because one frame failed would cost a whole live pass, and the
    missing row is visible in the index either way.
    """

    def __init__(self, session, hz=DEFAULT_HZ, root=SESSION_ROOT):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.dir = os.path.join(root, f"{stamp}_{session}")
        self.hz = hz
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._n = 0
        self.t0 = None
        self.index_path = os.path.join(self.dir, "index.jsonl")

    # --- lifecycle -------------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False

    def start(self):
        os.makedirs(self.dir, exist_ok=True)
        self.t0 = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        return self.dir

    # --- writing ---------------------------------------------------------
    def _write(self, row):
        with self._lock:
            with open(self.index_path, "a") as fh:
                fh.write(json.dumps(row) + "\n")

    def note(self, action, **fields):
        """Put a COMMAND into the same timeline as the frames.

        Legs are recovered by pairing a note with the frames around it, so an
        action that is not in this stream may as well not have happened.
        """
        row = {"kind": "note", "t": round(time.time() - (self.t0 or time.time()), 3),
               "action": action}
        row.update(fields)
        self._write(row)
        return row

    def _capture_row(self):
        import compass
        import places
        import table_prompt

        row = {"kind": "frame", "t": round(time.time() - self.t0, 3)}
        try:
            img = compass.fast_capture()
        except Exception as e:
            row["error"] = f"grab: {type(e).__name__}"
            return row, None
        name = f"{self._n:05d}.jpg"
        self._n += 1
        row["file"] = name
        try:
            img.convert("RGB").save(os.path.join(self.dir, name), quality=82)
        except Exception as e:
            row["error"] = f"save: {type(e).__name__}"
        for key, fn in (("heading", lambda: compass.read_bearing(img)),
                        ("at_table", lambda: bool(table_prompt.at_table(img)))):
            try:
                row[key] = fn()
            except Exception:
                row[key] = None
        try:
            place, score, margin = places.identify(img)
            row["place"] = place
            row["score"] = round(float(score), 4)
            row["margin"] = round(float(margin), 4)
        except Exception:
            row["place"] = row["score"] = row["margin"] = None
        return row, img

    def _loop(self):
        period = 1.0 / self.hz
        while not self._stop.is_set():
            started = time.time()
            try:
                row, _ = self._capture_row()
            except Exception as e:                      # never kill the walk
                row = {"kind": "frame", "t": round(time.time() - self.t0, 3),
                       "error": f"{type(e).__name__}: {e}"}
            self._write(row)
            self._stop.wait(max(0.0, period - (time.time() - started)))


def load(session_dir):
    """Read a session's index back as a list of rows, in time order."""
    path = os.path.join(session_dir, "index.jsonl")
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("t", 0.0))
    return rows


def sessions(root=SESSION_ROOT):
    if not os.path.isdir(root):
        return []
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
